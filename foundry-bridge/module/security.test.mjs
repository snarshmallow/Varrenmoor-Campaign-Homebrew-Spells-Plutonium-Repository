// Module security regressions (review findings F3, F10): no op is executed before the relay is welcomed (with a valid proof when paired), junk frames are ignored,
// a 4005 before the welcome does not delete the credential, relay-supplied text is sanitised, and a relocated relay is adopted only after it proved the device secret.
// Run: node --test foundry-bridge/module/security.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const tick = () => new Promise((r) => setImmediate(r));

async function load(extra = {}) {
  const hooks = {}, notes = [], timers = [], sockets = [];
  const settings = { enabled: true, autoUrl: false, relayUrl: 'ws://127.0.0.1:1/module', token: '', allowWrites: false, autoPair: false, relayPort: 3030, pairHost: '', clientId: 'c1', deviceAuth: '', ...extra };
  class FakeWS {
    constructor(url) { this.url = url; this.sent = []; this.closed = false; sockets.push(this); }
    send(m) { this.sent.push(JSON.parse(m)); }
    close() { this.closed = true; }
  }
  Object.assign(globalThis, {
    Hooks: { once: (n, f) => { hooks[n] = f; } },
    game: { settings: { register() {}, get: (m, k) => settings[k], set: async (m, k, v) => { settings[k] = v; } }, user: { isGM: true, name: 'T', id: 'u' }, world: { id: 'w' }, modules: { get: () => ({ version: 'test' }) } },
    ui: { notifications: { info: (m) => notes.push(['info', m]), warn: (m) => notes.push(['warn', m]) } },
    WebSocket: FakeWS, location: { hostname: '10.0.0.5', protocol: 'http:', origin: 'http://10.0.0.5:30000' },
    setTimeout: (f, ms) => { if (ms === 700 || ms === 1200 || ms === 4000) return 0; timers.push({ f, ms }); return timers.length; }, clearTimeout: () => {},
  });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'bridge_sec_'));
  fs.cpSync(path.join(here, 'varrenmoor-bridge', 'scripts'), dir, { recursive: true }); fs.writeFileSync(path.join(dir, 'package.json'), '{"type":"module"}');
  await import(pathToFileURL(path.join(dir, 'bridge.js')).href + '?t=' + Math.random());
  const C = await import(pathToFileURL(path.join(dir, 'seccrypto.js')).href);
  return { hooks, notes, timers, sockets, settings, C };
}

test('token mode: ops before the welcome are dropped and close the socket; after it they run; junk frames are ignored', async () => {
  const t = await load({ token: 'x'.repeat(30) });
  await t.hooks.ready(); await tick(); await tick();
  const ws = t.sockets[0]; ws.onopen();
  for (const junk of ['null', '[]', '"x"', '5', '{']) await ws.onmessage({ data: junk });
  await ws.onmessage({ data: JSON.stringify({ id: '1', op: 'ping', args: {} }) });
  assert.equal(ws.sent.filter((m) => m.id).length, 0, 'no answer before the welcome');
  assert.equal(ws.closed, true, 'socket dropped');
  await ws.onmessage({ data: JSON.stringify({ type: 'welcome' }) });
  await ws.onmessage({ data: JSON.stringify({ id: '2', op: 'ping', args: {} }) });
  assert.deepEqual(ws.sent.find((m) => m.id === '2'), { id: '2', result: 'pong' });
});

test('paired mode: a server without the device secret cannot get any op executed, with or without a fake welcome', async () => {
  const secret = 'A'.repeat(43);
  const t = await load({ deviceAuth: JSON.stringify({ host: '10.0.0.15:3030', relayId: 'r_1', deviceId: 'd_1', secret }) });
  await t.hooks.ready(); await tick(); await tick();
  const ws = t.sockets[0]; ws.onopen();
  assert.equal(ws.sent[0].type, 'hello');
  await ws.onmessage({ data: JSON.stringify({ id: '1', op: 'world_info', args: {} }) });            // straight away
  await ws.onmessage({ data: JSON.stringify({ type: 'welcome', proof: 'forged' }) });              // forged proof
  await ws.onmessage({ data: JSON.stringify({ id: '2', op: 'ping', args: {} }) });
  assert.equal(ws.sent.filter((m) => m.id).length, 0, 'nothing was executed or answered');
  // a real relay (knows the secret) is welcomed and then served
  const t2 = await load({ deviceAuth: JSON.stringify({ host: '10.0.0.15:3030', relayId: 'r_1', deviceId: 'd_1', secret }) });
  await t2.hooks.ready(); await tick(); await tick();
  const w2 = t2.sockets[0]; w2.onopen(); const cn = w2.sent[0].cn, rn = 'RN' + 'x'.repeat(20);
  await w2.onmessage({ data: JSON.stringify({ type: 'challenge', rn }) });
  assert.equal(w2.sent[1].mac, t2.C.clientMac(t2.C.unb64u(secret), 'd_1', cn, rn));
  await w2.onmessage({ data: JSON.stringify({ type: 'welcome', proof: t2.C.relayMac(t2.C.unb64u(secret), 'd_1', cn, rn) }) });
  await w2.onmessage({ data: JSON.stringify({ id: '3', op: 'ping', args: {} }) });
  assert.deepEqual(w2.sent.at(-1), { id: '3', result: 'pong' });
});

test('F10: a 4005 before the welcome keeps the credential; one after it forgets it; relay text is sanitised', async () => {
  const dev = { host: '10.0.0.15:3030', relayId: 'r_1', deviceId: 'd_1', secret: 'A'.repeat(43) };
  const t = await load({ deviceAuth: JSON.stringify(dev) });
  await t.hooks.ready(); await tick(); await tick();
  const ws = t.sockets[0]; ws.onopen();
  ws.onclose({ code: 4005, reason: '<img src=x onerror=alert(1)> bad' });
  await tick();
  assert.ok(t.settings.deviceAuth, 'credential kept: a stranger can send 4005');
  const n = t.notes.at(-1)[1]; assert.ok(!/[<>=]/.test(n), 'no markup in the notice: ' + n); assert.match(n, /Pair with relay/);
  // revoked while connected (welcomed): forgotten
  const t2 = await load({ deviceAuth: JSON.stringify(dev) });
  await t2.hooks.ready(); await tick(); await tick();
  const w2 = t2.sockets[0]; w2.onopen(); const cn = w2.sent[0].cn, rn = 'RN' + 'y'.repeat(20);
  await w2.onmessage({ data: JSON.stringify({ type: 'challenge', rn }) });
  await w2.onmessage({ data: JSON.stringify({ type: 'welcome', proof: t2.C.relayMac(t2.C.unb64u(dev.secret), 'd_1', cn, rn) }) });
  w2.onclose({ code: 4005, reason: 'device revoked' }); await tick();
  assert.equal(t2.settings.deviceAuth, '');
});

test('F3: relocation by relayId alone does not adopt a host; only a host that proves the secret is saved', async () => {
  const secret = 'B'.repeat(43), dev = { host: '10.0.0.15:3030', relayId: 'r_1', deviceId: 'd_1', secret };
  const t = await load({ deviceAuth: JSON.stringify(dev) });
  const realFetch = globalThis.fetch;
  globalThis.fetch = async (url) => { const u = String(url); if (u.startsWith('http://10.0.0.5:3030/discover') || u.startsWith('http://10.0.0.77:3030/discover')) return { ok: true, json: async () => ({ service: 'varrenmoor-bridge-relay', relayId: 'r_1', pairing: true }) }; throw new Error('no route'); };
  try {
    await t.hooks.ready(); await tick(); await tick();
    let ws = t.sockets[0];
    for (let i = 0; i < 3; i++) { ws.onopen(); ws.onclose({ code: 1006 }); if (i < 2) { await t.timers.at(-1).f(); await tick(); await tick(); ws = t.sockets.at(-1); } }
    await new Promise((r) => realFetchWait(r)); await tick();
    assert.equal(JSON.parse(t.settings.deviceAuth).host, '10.0.0.15:3030', 'host not changed just because /discover looked right');
    // the next connect tries the candidate (10.0.0.5 answered first in the scan: the page host), but still does not save it
    await t.timers.at(-1).f(); await tick(); await tick();
    const cand = t.sockets.at(-1); assert.match(cand.url, /^ws:\/\/10\.0\.0\.\d+:3030\/module$/); assert.notEqual(cand.url, 'ws://10.0.0.15:3030/module');
    cand.onopen(); const cn = cand.sent[0].cn; await cand.onmessage({ data: JSON.stringify({ type: 'challenge', rn: 'RNRNRNRNRNRNRNRN' }) });
    await cand.onmessage({ data: JSON.stringify({ type: 'welcome', proof: 'forged' }) });
    assert.equal(JSON.parse(t.settings.deviceAuth).host, '10.0.0.15:3030', 'an impostor that cannot prove the secret is not adopted');
    const host = cand.url.replace('ws://', '').replace('/module', '');
    // the real relay (valid proof) at the same candidate address is adopted
    cand.onclose({ code: 1006 }); t.timers.length = 0;
    // run the scan again by hand: pretend the candidate was found, then welcome with a valid proof
    const t2 = await load({ deviceAuth: JSON.stringify(dev) });
    await t2.hooks.ready(); await tick(); await tick();
    let w = t2.sockets[0];
    for (let i = 0; i < 3; i++) { w.onopen(); w.onclose({ code: 1006 }); if (i < 2) { await t2.timers.at(-1).f(); await tick(); await tick(); w = t2.sockets.at(-1); } }
    await new Promise((r) => realFetchWait(r)); await tick();
    await t2.timers.at(-1).f(); await tick(); await tick();
    const c2 = t2.sockets.at(-1); c2.onopen(); const cn2 = c2.sent[0].cn, rn = 'RNRNRNRNRNRNRNRN';
    await c2.onmessage({ data: JSON.stringify({ type: 'challenge', rn }) });
    await c2.onmessage({ data: JSON.stringify({ type: 'welcome', proof: t2.C.relayMac(t2.C.unb64u(secret), 'd_1', cn2, rn) }) });
    assert.equal(JSON.parse(t2.settings.deviceAuth).host, c2.url.replace('ws://', '').replace('/module', ''), 'adopted after a valid proof'); void cn; void host;
  } finally { globalThis.fetch = realFetch; }
});
const realFetchWait = async (r) => { for (let i = 0; i < 300; i++) await new Promise((x) => setImmediate(x)); r(); };
