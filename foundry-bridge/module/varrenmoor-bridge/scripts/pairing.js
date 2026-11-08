// LAN pairing client for the Varrenmoor Bridge module (0.5.0). Pure functions with injected fetch/sleep so they can be tested outside Foundry
// (foundry-bridge/module/pairing.test.mjs). Protocol 2 (encrypted handshake), see foundry-bridge/README.md "Pairing and its threat model":
//   discover  GET  http://<host:port>/discover            -> { service, protocol, relayId, pairing, autoRequest }   (no secrets)
//   request   POST /pair/request {commit}                 -> { requestId, pollSecret, relayPk, relayNonce }        (commitment to our key + nonce)
//   reveal    POST /pair/reveal {requestId, pollSecret, pk, nonce, info(sealed)}                                   (relay can now compute the code)
//   poll      POST /pair/poll {requestId, pollSecret}     -> { state, deviceId?, sealed? }                         (credential arrives sealed under the handshake key)
// Both sides show the same 6-digit code, derived from both public keys and both nonces; the human approves only when they match.
// The relay refuses non-LAN callers. Secrets are only ever sent sealed, or used as an HMAC key, and never logged here. Pure JS crypto (no WebCrypto: an http page has none).
import * as C from './seccrypto.js';

export const DEFAULT_PORT = 3030;
const withPort = (h) => (/:\d+$/.test(h) ? h : `${h}:${DEFAULT_PORT}`);
const hostOf = (s) => { try { return new URL(/^[a-z]+:\/\//i.test(s) ? s : `http://${s}`).host; } catch { return ''; } };

// Where the relay normally runs: beside Foundry, same host, relay port. Only for plain-http pages (an https page cannot reach ws:// / http:// anyway: mixed content,
// and that is the Cloudflare/player route where pairing is refused on purpose). Returns "host:port" or null.
export function deriveRelayHost({ pageHost = '', pageProtocol = 'http:', relayPort = DEFAULT_PORT } = {}) {
  const h = String(pageHost || '').trim();
  if (!h || String(pageProtocol).toLowerCase() === 'https:') return null;
  return `${h}:${Number(relayPort) > 0 ? Number(relayPort) : DEFAULT_PORT}`;
}

// host[:port] candidates to probe, most specific first: the stored pairing, a typed address, the page's own host (zero config), then a non-loopback relay URL setting.
export function candidateHosts({ pairHost = '', relayUrl = '', stored = null, pageHost = '', pageProtocol = 'http:', relayPort = DEFAULT_PORT } = {}) {
  const out = [];
  const add = (h) => { h = String(h || '').trim(); if (!h) return; h = withPort(hostOf(h) || h); if (!out.includes(h)) out.push(h); };
  add(stored && stored.host); add(pairHost); add(deriveRelayHost({ pageHost, pageProtocol, relayPort }));
  if (relayUrl && !/^wss?:\/\/(127\.|localhost|\[::1\])/i.test(relayUrl)) add(relayUrl);
  return out;
}

async function timed(fetchFn, url, init, ms) {
  const ac = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const t = ac ? setTimeout(() => ac.abort(), ms) : null;
  try { return await fetchFn(url, { ...init, signal: ac?.signal, cache: 'no-store' }); } finally { if (t) clearTimeout(t); }
}

// returns the /discover document when a Varrenmoor relay answers, else null
export async function probe(hostPort, fetchFn, ms = 1200) {
  try {
    const r = await timed(fetchFn, `http://${withPort(hostPort)}/discover`, {}, ms);
    if (!r.ok) return null;
    const j = await r.json();
    return j && j.service === 'varrenmoor-bridge-relay' ? j : null;   // pairing may be off: the caller reads j.pairing and explains
  } catch { return null; }
}

// Opt-in /24 scan around an IPv4 address (the Foundry host's own address), port 3030, small concurrency, short timeouts.
export async function scanLan(ip, fetchFn, { ms = 700, concurrency = 24, port = DEFAULT_PORT, skip = [] } = {}) {
  const m = String(ip || '').match(/^(\d+\.\d+\.\d+)\.\d+$/);
  if (!m) return [];
  const todo = []; for (let i = 1; i < 255; i++) { const h = `${m[1]}.${i}:${port}`; if (!skip.includes(h)) todo.push(h); }
  const found = [];
  await Promise.all(Array.from({ length: concurrency }, async () => {
    while (todo.length) { const h = todo.shift(); const j = await probe(h, fetchFn, ms); if (j) found.push({ host: h, info: j }); }
  }));
  return found;
}

// First relay that answers among the candidates; optionally (scan) the /24 of `hostname`.
export async function findRelay({ candidates = [], hostname = '', scan = false, relayId = '' }, fetchFn) {
  for (const h of candidates) { const j = await probe(h, fetchFn); if (j && (!relayId || j.relayId === relayId)) return { host: h, info: j }; }
  if (scan) { const f = (await scanLan(hostname, fetchFn, { skip: candidates })).filter((x) => !relayId || x.info.relayId === relayId); if (f.length) return f[0]; }
  return null;
}

const post = async (fetchFn, hostPort, p, body, ms = 4000) => {
  const r = await timed(fetchFn, `http://${withPort(hostPort)}${p}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }, ms);
  let j = {}; try { j = await r.json(); } catch { /* empty */ }
  return { status: r.status, body: j };
};

export const wsUrlFor = (hostPort) => `ws://${withPort(hostPort)}/module`;

// Full flow. hooks: onCode({code, host, expiresAt}), onState(state), cancelled() -> bool. Resolves { ok, deviceId, secret, expiresAt, relayId, host } or { ok:false, reason }.
export async function runPairing({ host, device, fetchFn, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), hooks = {}, pollMs = 1500, timeoutMs = 130000 }) {
  const kp = C.newKeypair(), nonce = C.randomBytes(16);
  const rq = await post(fetchFn, host, '/pair/request', { commit: C.commitment(kp.pk, nonce) });
  if (rq.status !== 200) return { ok: false, reason: rq.body.error || `relay answered ${rq.status}` };
  let relayPk, relayNonce, key;
  try { relayPk = C.unb64u(rq.body.relayPk); relayNonce = C.unb64u(rq.body.relayNonce); key = C.pairKey(kp.sk, relayPk, kp.pk, relayPk, nonce, relayNonce); }
  catch { return { ok: false, reason: 'the relay sent an invalid key' }; }
  const id = rq.body.requestId;
  const rv = await post(fetchFn, host, '/pair/reveal', { requestId: id, pollSecret: rq.body.pollSecret, pk: C.b64u(kp.pk), nonce: C.b64u(nonce), info: C.sealJson(key, device, 'vb-info|' + id) });
  if (rv.status !== 200) return { ok: false, reason: rv.body.error || `relay answered ${rv.status}` };
  // computed from OUR copy of both keys and nonces: a man in the middle who swapped keys makes this differ from the code the relay shows
  hooks.onCode && hooks.onCode({ code: C.sas(kp.pk, relayPk, nonce, relayNonce), host, expiresAt: rq.body.expiresAt });
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (hooks.cancelled && hooks.cancelled()) { post(fetchFn, host, '/pair/cancel', { requestId: id, pollSecret: rq.body.pollSecret }).catch(() => {}); return { ok: false, reason: 'cancelled' }; }
    await sleep(pollMs);
    let p;
    try { p = await post(fetchFn, host, '/pair/poll', { requestId: id, pollSecret: rq.body.pollSecret }); } catch { continue; }
    if (p.status === 429) { await sleep(3000); continue; }
    if (p.status !== 200) return { ok: false, reason: p.body.error || `relay answered ${p.status}` };
    const s = p.body.state;
    hooks.onState && hooks.onState(s);
    if (s === 'approved') {
      const cred = C.openJson(key, p.body.sealed, 'vb-dev|' + id + '|' + p.body.deviceId);
      if (!cred || !cred.secret) return { ok: false, reason: 'could not decrypt the credential (something other than the relay answered)' };
      return { ok: true, deviceId: p.body.deviceId, secret: cred.secret, expiresAt: cred.expiresAt || null, relayId: cred.relayId || p.body.relayId, host };
    }
    if (s === 'denied') return { ok: false, reason: 'denied on the relay' };
    if (s === 'expired' || s === 'unknown' || s === 'delivered') return { ok: false, reason: s === 'expired' ? 'nobody approved it in time' : 'the request is no longer valid' };
  }
  return { ok: false, reason: 'timed out waiting for approval' };
}

// WebSocket login for a paired device: HMAC challenge-response, the secret never leaves this browser.
//   const a = deviceAuth(dev); ws.onopen -> send(a.hello()); on 'challenge' -> send(a.answer(m)); on 'welcome' -> a.welcome(m) = { ok, secret?, expiresAt? }
export function deviceAuth(dev) {
  const cn = C.b64u(C.randomBytes(16)); let rn = null; const secret = C.unb64u(dev.secret);
  return {
    hello: () => ({ type: 'hello', deviceId: dev.deviceId, cn }),
    answer: (m) => { rn = String(m.rn || ''); return { type: 'auth', mac: C.clientMac(secret, dev.deviceId, cn, rn) }; },
    welcome: (m) => {
      if (!rn || m.proof !== C.relayMac(secret, dev.deviceId, cn, rn)) return { ok: false, reason: 'the relay did not prove it knows the device secret' };
      const out = { ok: true };
      if (m.rotate && m.rotate.sealed) {
        const r = C.openJson(C.rotationKey(secret, dev.deviceId, cn, rn), m.rotate.sealed, 'vb-rot|' + dev.deviceId);
        if (r && r.secret) { out.secret = r.secret; out.expiresAt = r.expiresAt || null; }
      }
      return out;
    },
  };
}

// what the relay shows the human next to the code
export function describeDevice({ user = {}, world = {}, location = {}, ua = '', clientId = '' } = {}) {
  const os = /Windows/i.test(ua) ? 'Windows' : /Mac/i.test(ua) ? 'macOS' : /Linux/i.test(ua) ? 'Linux' : 'browser';
  return { deviceName: `Foundry GM ${user.name || '?'} (${os} browser)`, worldId: world.id || '', userId: user.id || '', userName: user.name || '', hostOrigin: location.origin || '', clientId: String(clientId || '') };
}
