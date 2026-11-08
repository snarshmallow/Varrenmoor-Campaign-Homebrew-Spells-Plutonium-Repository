// LAN pairing client for the Varrenmoor Bridge module (0.4.0). Pure functions with injected fetch/sleep so they can be tested outside Foundry
// (foundry-bridge/module/pairing.test.mjs). Protocol: see foundry-bridge/README.md "Pairing".
//   discover  GET  http://<host:port>/discover        -> { service, relayId, ... }   (no secrets)
//   request   POST /pair/request {deviceName,...}      -> { requestId, code, pollSecret }
//   poll      POST /pair/poll {requestId, pollSecret}  -> { state: pending|approved|denied|expired|delivered|unknown, deviceId?, token? }
// The relay refuses non-LAN callers. Tokens are only ever sent in POST bodies / the WebSocket hello, never in URLs, and never logged here.

export const DEFAULT_PORT = 3030;
const withPort = (h) => (/:\d+$/.test(h) ? h : `${h}:${DEFAULT_PORT}`);
const hostOf = (s) => { try { return new URL(/^[a-z]+:\/\//i.test(s) ? s : `http://${s}`).host; } catch { return ''; } };

// host[:port] candidates to probe, most specific first (no loopback unless the user typed it: on the Foundry PC it would only find nothing)
export function candidateHosts({ pairHost = '', relayUrl = '', stored = null } = {}) {
  const out = [];
  const add = (h) => { h = String(h || '').trim(); if (!h) return; h = withPort(hostOf(h) || h); if (!out.includes(h)) out.push(h); };
  add(stored && stored.host); add(pairHost);
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
    return j && j.service === 'varrenmoor-bridge-relay' && j.pairing ? j : null;
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

// Full flow. hooks: onCode({code, host, expiresAt}), onState(state), cancelled() -> bool. Resolves { ok, deviceId, token, expiresAt, relayId, host } or { ok:false, reason }.
export async function runPairing({ host, device, fetchFn, sleep = (ms) => new Promise((r) => setTimeout(r, ms)), hooks = {}, pollMs = 1500, timeoutMs = 130000 }) {
  const rq = await post(fetchFn, host, '/pair/request', device);
  if (rq.status !== 200) return { ok: false, reason: rq.body.error || `relay answered ${rq.status}` };
  hooks.onCode && hooks.onCode({ code: rq.body.code, host, expiresAt: rq.body.expiresAt });
  const end = Date.now() + timeoutMs;
  while (Date.now() < end) {
    if (hooks.cancelled && hooks.cancelled()) return { ok: false, reason: 'cancelled' };
    await sleep(pollMs);
    let p;
    try { p = await post(fetchFn, host, '/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret }); } catch { continue; }
    if (p.status === 429) { await sleep(3000); continue; }
    if (p.status !== 200) return { ok: false, reason: p.body.error || `relay answered ${p.status}` };
    const s = p.body.state;
    hooks.onState && hooks.onState(s);
    if (s === 'approved') return { ok: true, deviceId: p.body.deviceId, token: p.body.token, expiresAt: p.body.expiresAt || null, relayId: p.body.relayId, host };
    if (s === 'denied') return { ok: false, reason: 'denied on the relay' };
    if (s === 'expired' || s === 'unknown' || s === 'delivered') return { ok: false, reason: s === 'expired' ? 'nobody approved it in time' : 'the request is no longer valid' };
  }
  return { ok: false, reason: 'timed out waiting for approval' };
}

// what the relay shows the human next to the code
export function describeDevice({ user = {}, world = {}, location = {}, ua = '' } = {}) {
  const os = /Windows/i.test(ua) ? 'Windows' : /Mac/i.test(ua) ? 'macOS' : /Linux/i.test(ua) ? 'Linux' : 'browser';
  return { deviceName: `Foundry GM ${user.name || '?'} (${os} browser)`, worldId: world.id || '', userId: user.id || '', userName: user.name || '', hostOrigin: location.origin || '' };
}
