// Module-side pairing against a REAL in-process relay on an ephemeral port (throwaway tokens): the module's pure-JS crypto talks to the relay's node:crypto,
// over real HTTP and a real WebSocket. Fake Foundry globals only. Covers zero-config relay discovery from the page host, https refusal, auto-request,
// approval through the admin API from a different "PC", the sealed credential, challenge-response login, rotation, revoke, fake relay detection.
//   node --test foundry-bridge/module/pairing.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import { WebSocket as RealWS } from '../relay/node_modules/ws/wrapper.mjs';
import { createRelay } from '../relay/server.js';
import { signAdmin } from '../relay/adminauth.js';
import { loadModuleScripts } from './seccrypto.test.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const API = 'a'.repeat(32), MOD = 'm'.repeat(32);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function relay({ auto = null, pairingEnabled, autoRequest } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vmodp-'));
  const logs = []; const origLog = console.log; console.log = (...a) => logs.push(a.join(' '));
  const server = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: path.join(dir, 'paired.json'), pairingEnabled, autoRequest });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const seen = [];
  server.pairing.on('request', (r) => { seen.push(r); if (auto === 'approve') setTimeout(() => server.pairing.approve(r.id, { days: 30 }), 50); else if (auto === 'deny') setTimeout(() => server.pairing.deny(r.id), 50); });
  const port = server.address().port;
  // the approver is "another PC": signed admin calls (no token on the wire)
  const admin = async (p, body = {}) => { const raw = JSON.stringify(body); const r = await fetch(`http://127.0.0.1:${port}${p}`, { method: 'POST', headers: { 'content-type': 'application/json', origin: 'http://arcturus:8080', 'x-vb-auth': signAdmin({ token: API, method: 'POST', url: p, body: raw }) }, body: raw }); return { status: r.status, body: await r.json() }; };
  return { server, seen, port, logs, admin, host: `127.0.0.1:${port}`, close: async () => { console.log = origLog; server.closeAllConnections?.(); await new Promise((r) => server.close(r)); fs.rmSync(dir, { recursive: true, force: true }); } };
}
const f = (...a) => fetch(...a);

test('candidateHosts: page host derivation, https refusal, typed address wins order', async () => {
  const { dir } = await loadModuleScripts(); const Pair = await import(pathToFileURL(path.join(dir, 'pairing.js')).href);
  assert.equal(Pair.deriveRelayHost({ pageHost: '10.0.0.15', pageProtocol: 'http:' }), '10.0.0.15:3030');
  assert.equal(Pair.deriveRelayHost({ pageHost: 'pc-two', pageProtocol: 'http:', relayPort: 4040 }), 'pc-two:4040');
  assert.equal(Pair.deriveRelayHost({ pageHost: 'foundry.example.com', pageProtocol: 'https:' }), null, 'https/Cloudflare page: refused');
  assert.equal(Pair.deriveRelayHost({ pageHost: '', pageProtocol: 'http:' }), null);
  assert.deepEqual(Pair.candidateHosts({ pairHost: '10.0.0.20', relayUrl: 'ws://127.0.0.1:3030/module' }), ['10.0.0.20:3030']);
  assert.deepEqual(Pair.candidateHosts({ pairHost: '10.0.0.20:3031', relayUrl: 'wss://x.example/module', stored: { host: '10.0.0.9:3030' }, pageHost: '10.0.0.5', pageProtocol: 'http:' }), ['10.0.0.9:3030', '10.0.0.20:3031', '10.0.0.5:3030', 'x.example:3030']);
  assert.deepEqual(Pair.candidateHosts({ pageHost: 'foundry.example.com', pageProtocol: 'https:' }), []);
});

test('probe sees a relay with pairing off; runPairing approve / deny / cancel with the pure-JS module crypto against the real relay', async () => {
  const { dir } = await loadModuleScripts(); const Pair = await import(pathToFileURL(path.join(dir, 'pairing.js')).href);
  const off = await relay({ pairingEnabled: false });
  try {
    const j = await Pair.probe(off.host, f); assert.equal(j.service, 'varrenmoor-bridge-relay'); assert.equal(j.pairing, false);
    const res = await Pair.runPairing({ host: off.host, device: { deviceName: 'x' }, fetchFn: f, pollMs: 50 }); assert.equal(res.ok, false); assert.match(res.reason, /not enabled/);
  } finally { await off.close(); }
  const r = await relay({ auto: 'approve' });
  try {
    assert.equal(await Pair.probe('127.0.0.1:1', f, 300), null);
    assert.equal((await Pair.probe(r.host, f)).pairing, true);
    assert.ok(await Pair.findRelay({ candidates: ['127.0.0.1:1', r.host] }, f));
    assert.equal(await Pair.findRelay({ candidates: [r.host], relayId: 'r_other' }, f), null);
    const codes = [];
    const res = await Pair.runPairing({ host: r.host, device: Pair.describeDevice({ user: { name: 'Trent', id: 'u1' }, world: { id: 'w' }, location: { origin: 'http://vega:30000' }, ua: 'Windows' }), fetchFn: f, pollMs: 100, hooks: { onCode: (c) => codes.push(c.code) } });
    assert.ok(res.ok && res.secret && res.deviceId, JSON.stringify({ ...res, secret: '' }));
    assert.equal(codes[0].replace(' ', ''), r.seen[0].code, 'device computed the same code the relay shows');
    assert.equal(r.seen[0].name, 'Foundry GM Trent (Windows browser)');
    const everything = r.logs.join('\n'); assert.ok(!everything.includes(res.secret));
  } finally { await r.close(); }
  const d = await relay({ auto: 'deny' });
  try { const res = await Pair.runPairing({ host: d.host, device: { deviceName: 'x' }, fetchFn: f, pollMs: 100 }); assert.equal(res.ok, false); assert.match(res.reason, /denied/); } finally { await d.close(); }
  const n = await relay({ auto: null });
  try { let n2 = 0; const res = await Pair.runPairing({ host: n.host, device: { deviceName: 'x' }, fetchFn: f, pollMs: 50, hooks: { cancelled: () => ++n2 > 3 } }); assert.deepEqual([res.ok, res.reason], [false, 'cancelled']); } finally { await n.close(); }
  // an impostor that answers /pair/poll with a credential sealed under a different key is rejected
  const imp = await relay({ auto: 'approve' });
  try {
    const realFetch = f; let revealed = false;
    const tampered = (url, init) => realFetch(url, init).then(async (resp) => {
      if (String(url).endsWith('/pair/poll')) { const j = await resp.clone().json(); if (j.sealed) { j.sealed = j.sealed.slice(0, -3) + (j.sealed.endsWith('AAA') ? 'BBB' : 'AAA'); return new Response(JSON.stringify(j), { status: 200 }); } }
      return resp;
    });
    const res = await Pair.runPairing({ host: imp.host, device: { deviceName: 'x' }, fetchFn: tampered, pollMs: 100 }); assert.equal(res.ok, false); assert.match(res.reason, /could not decrypt/); void revealed;
  } finally { await imp.close(); }
});

test('bridge.js end to end: zero-config (page host + relay port), auto-request, approve from another PC, sealed secret, challenge-response login, rotation, revoke', async () => {
  const r = await relay();
  const hooks = {}, notes = [], sockets = [], dialogs = [];
  const store = { enabled: false, autoUrl: false, relayUrl: 'ws://127.0.0.1:3030/module', token: '', pairHost: '', relayPort: r.port, autoPair: true, deviceAuth: '', allowWrites: false };
  class TWS extends RealWS { constructor(u) { super(u); sockets.push(this); } }
  Object.assign(globalThis, {
    Hooks: { once: (n, fn) => { hooks[n] = fn; }, on: () => {} },
    game: { settings: { register() {}, get: (m, k) => store[k], set: async (m, k, v) => { store[k] = v; } }, user: { isGM: true, name: 'Trent', id: 'u1' }, world: { id: 'varrenmoor' }, modules: { get: () => ({ version: 'test' }) } },
    ui: { notifications: { info: (m) => notes.push(['info', m]), warn: (m) => notes.push(['warn', m]) } },
    WebSocket: TWS, location: { hostname: '127.0.0.1', protocol: 'http:', origin: 'http://127.0.0.1:30000' },
    foundry: { applications: { api: { DialogV2: class { constructor(o) { this.o = o; dialogs.push(o); } render() {} close() {} } } } },
  });
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'Windows' }, configurable: true });
  const { dir } = await loadModuleScripts();
  try {
    await import(pathToFileURL(path.join(dir, 'bridge.js')).href);
    await hooks.ready();
    // no address typed anywhere: found at 127.0.0.1:<relay port> from the page host; the dialog shows the code
    for (let i = 0; i < 60 && !r.seen.length; i++) await sleep(100);
    assert.equal(r.seen.length, 1, 'the module asked for pairing on its own');
    const shown = (dialogs[0]?.content || '').match(/(\d{3} \d{3})/)?.[1];
    assert.equal(shown && shown.replace(' ', ''), r.seen[0].code, 'the device dialog shows the code the approver will see');
    // approver on a different PC lists pending requests and approves them with a signed request
    const list = await r.admin('/pair/list'); assert.equal(list.body.pending.length, 1); assert.equal(list.body.pending[0].code, r.seen[0].code);
    assert.equal((await r.admin('/pair/approve', { id: list.body.pending[0].id, days: 30 })).status, 200);
    for (let i = 0; i < 80 && !store.deviceAuth; i++) await sleep(100);
    const dev = JSON.parse(store.deviceAuth);
    assert.equal(dev.host, r.host); assert.ok(dev.deviceId.startsWith('d_')); assert.ok(dev.secret.length >= 40); assert.equal(store.enabled, true);
    assert.ok(notes.some((n) => /paired with the relay/.test(n[1]))); assert.ok(!notes.some((n) => n[1].includes(dev.secret)) && !JSON.stringify(dialogs).includes(dev.secret), 'secret never shown');
    // connects with challenge-response (real WebSocket): the relay sees a paired device, never the secret
    for (let i = 0; i < 60 && !(await (await fetch(`http://${r.host}/health`)).json()).moduleConnected; i++) await sleep(100);
    assert.equal((await (await fetch(`http://${r.host}/health`)).json()).moduleConnected, true);
    assert.ok(r.logs.some((l) => /paired device d_/.test(l)) && !r.logs.join('\n').includes(dev.secret));
    // rotation from the panel: the next connect delivers a sealed new secret and the module stores it (the socket is dropped so the module reconnects by itself)
    assert.equal((await r.admin('/pair/rotate', { deviceId: dev.deviceId })).status, 200);
    sockets.at(-1).close();
    for (let i = 0; i < 80 && JSON.parse(store.deviceAuth).secret === dev.secret; i++) await sleep(100);
    const rotated = JSON.parse(store.deviceAuth);
    assert.notEqual(rotated.secret, dev.secret, 'secret rotated and stored'); assert.equal(rotated.deviceId, dev.deviceId);
    for (let i = 0; i < 60 && !(await (await fetch(`http://${r.host}/health`)).json()).moduleConnected; i++) await sleep(100);
    assert.equal((await (await fetch(`http://${r.host}/health`)).json()).moduleConnected, true, 'connected again with the rotated secret');
    // revoke: 4005 closes the socket, the module forgets the pairing, warns and does not reconnect
    const n0 = sockets.length;
    assert.equal((await r.admin('/pair/revoke', { deviceId: dev.deviceId })).status, 200);
    for (let i = 0; i < 50 && store.deviceAuth; i++) await sleep(100);
    assert.equal(store.deviceAuth, ''); assert.ok(notes.some((n) => n[0] === 'warn' && /no longer accepts/.test(n[1])));
    await sleep(1500); assert.equal(sockets.length, n0, 'no reconnect after 4005');
  } finally { await r.close(); }
});

test('deviceAuth: a relay that cannot prove it knows the secret is refused (fake relay); wrong challenge never leaks the secret', async () => {
  const { dir } = await loadModuleScripts(); const Pair = await import(pathToFileURL(path.join(dir, 'pairing.js')).href), C = await import(pathToFileURL(path.join(dir, 'seccrypto.js')).href);
  const secret = C.b64u(C.randomBytes(32)), dev = { deviceId: 'd_1', secret };
  const a = Pair.deviceAuth(dev), hello = a.hello(), ans = a.answer({ rn: 'RN' });
  assert.equal(hello.deviceId, 'd_1'); assert.ok(hello.cn); assert.ok(!JSON.stringify([hello, ans]).includes(secret), 'the secret is never sent');
  assert.equal(a.welcome({ proof: 'forged' }).ok, false);
  assert.equal(a.welcome({ proof: C.relayMac(C.unb64u(secret), 'd_1', hello.cn, 'RN') }).ok, true);
  assert.equal(Pair.deviceAuth(dev).welcome({ proof: 'x' }).ok, false, 'no challenge seen yet');
});

test('bridge.js on an https (Cloudflare/player) page: no pairing attempt, nothing sent to any relay', async () => {
  const hooks = {}, notes = [], fetched = [];
  const store = { enabled: false, autoUrl: false, relayUrl: 'ws://127.0.0.1:3030/module', token: '', pairHost: '10.0.0.5:3030', relayPort: 3030, autoPair: true, deviceAuth: '', allowWrites: false };
  const realFetch = globalThis.fetch;
  Object.assign(globalThis, {
    Hooks: { once: (n, fn) => { hooks[n] = fn; }, on: () => {} },
    game: { settings: { register() {}, get: (m, k) => store[k], set: async (m, k, v) => { store[k] = v; } }, user: { isGM: true, name: 'Trent', id: 'u1' }, world: { id: 'w' }, modules: { get: () => ({ version: 'test' }) } },
    ui: { notifications: { info: (m) => notes.push(['info', m]), warn: (m) => notes.push(['warn', m]) } },
    WebSocket: class { constructor() { throw new Error('no socket expected'); } }, location: { hostname: 'foundry.example.com', protocol: 'https:', origin: 'https://foundry.example.com' },
    fetch: (...a) => { fetched.push(a[0]); return Promise.reject(new Error('offline')); },
  });
  try {
    const { dir } = await loadModuleScripts();
    await import(pathToFileURL(path.join(dir, 'bridge.js')).href);
    await hooks.ready(); await sleep(200);
    assert.deepEqual(fetched.filter((u) => /discover|pair/.test(String(u))), [], 'no relay probing from an https page');
  } finally { globalThis.fetch = realFetch; }
});
