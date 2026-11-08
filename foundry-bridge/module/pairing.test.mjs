// Module-side pairing against a REAL in-process relay on an ephemeral port (throwaway tokens), with a fake Foundry and fake WebSocket.
//   node --test foundry-bridge/module/pairing.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import * as Pair from './varrenmoor-bridge/scripts/pairing.js';
import { createRelay } from '../relay/server.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const API = 'a'.repeat(32), MOD = 'm'.repeat(32);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function relay(auto = 'approve') {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vmodp-'));
  const server = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: path.join(dir, 'paired.json') });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const seen = [];
  server.pairing.on('request', (r) => { seen.push(r); if (auto === 'approve') setTimeout(() => server.pairing.approve(r.id, { days: 30 }), 50); else if (auto === 'deny') setTimeout(() => server.pairing.deny(r.id), 50); });
  return { server, seen, host: `127.0.0.1:${server.address().port}`, close: async () => { server.closeAllConnections?.(); await new Promise((r) => server.close(r)); fs.rmSync(dir, { recursive: true, force: true }); } };
}

test('candidateHosts / probe / findRelay / runPairing (approve and deny)', async () => {
  assert.deepEqual(Pair.candidateHosts({ pairHost: '10.0.0.20', relayUrl: 'ws://127.0.0.1:3030/module' }), ['10.0.0.20:3030']);
  assert.deepEqual(Pair.candidateHosts({ pairHost: '10.0.0.20:3031', relayUrl: 'wss://x.example/module', stored: { host: '10.0.0.9:3030' } }), ['10.0.0.9:3030', '10.0.0.20:3031', 'x.example:3030']);
  const r = await relay();
  try {
    assert.equal(await Pair.probe('127.0.0.1:1', (...a) => fetch(...a), 300), null);
    const j = await Pair.probe(r.host, (...a) => fetch(...a)); assert.equal(j.service, 'varrenmoor-bridge-relay');
    assert.ok(await Pair.findRelay({ candidates: ['127.0.0.1:1', r.host] }, (...a) => fetch(...a)));
    assert.equal(await Pair.findRelay({ candidates: [r.host], relayId: 'r_other' }, (...a) => fetch(...a)), null);
    const codes = [];
    const res = await Pair.runPairing({ host: r.host, device: Pair.describeDevice({ user: { name: 'Trent', id: 'u1' }, world: { id: 'w' }, location: { origin: 'http://vega:30000' }, ua: 'Windows' }), fetchFn: (...a) => fetch(...a), pollMs: 100, hooks: { onCode: (c) => codes.push(c.code) } });
    assert.ok(res.ok && res.token && res.deviceId, JSON.stringify({ ...res, token: '' }));
    assert.equal(codes[0], r.seen[0].code.replace(/(\d{3})(\d{3})/, '$1 $2'), 'device shows the same code the relay shows');
    assert.equal(r.seen[0].name, 'Foundry GM Trent (Windows browser)');
    r.seen.length = 0; r.server.pairing.coolUntil.clear();
  } finally { await r.close(); }
  const d = await relay('deny');
  try { const res = await Pair.runPairing({ host: d.host, device: { deviceName: 'x' }, fetchFn: (...a) => fetch(...a), pollMs: 100 }); assert.equal(res.ok, false); assert.match(res.reason, /denied/); } finally { await d.close(); }
  const n = await relay('none');
  try {
    let n2 = 0; const res = await Pair.runPairing({ host: n.host, device: { deviceName: 'x' }, fetchFn: (...a) => fetch(...a), pollMs: 50, hooks: { cancelled: () => ++n2 > 3 } });
    assert.deepEqual([res.ok, res.reason], [false, 'cancelled']);
  } finally { await n.close(); }
});

test('bridge.js: auto-offer pairing, store the device token, connect with it, rotate, and forget on 4005 (revoked)', async () => {
  const r = await relay();
  const hooks = {}, notes = [], sockets = [], store = { enabled: true, autoUrl: false, relayUrl: 'ws://127.0.0.1:1/module', token: '', pairHost: r.host, autoPair: true, deviceAuth: '', allowWrites: false };
  class FakeWS { constructor(url) { this.url = url; this.sent = []; this.readyState = 1; sockets.push(this); } send(m) { this.sent.push(JSON.parse(m)); } close() {} }
  Object.assign(globalThis, {
    Hooks: { once: (n, f) => { hooks[n] = f; }, on: () => {} },
    game: { settings: { register() {}, get: (m, k) => store[k], set: async (m, k, v) => { store[k] = v; } }, user: { isGM: true, name: 'Trent', id: 'u1' }, world: { id: 'varrenmoor' }, modules: { get: () => ({ version: 'test' }) } },
    ui: { notifications: { info: (m) => notes.push(['info', m]), warn: (m) => notes.push(['warn', m]) } },
    WebSocket: FakeWS, location: { hostname: '127.0.0.1', origin: 'http://vega:30000' }, foundry: {},
  });
  Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'Windows' }, configurable: true });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vmodb_')), tmp = path.join(dir, 'bridge.mjs');
  fs.writeFileSync(tmp, fs.readFileSync(path.join(here, 'varrenmoor-bridge/scripts/bridge.js'), 'utf8').replace('./pairing.js', './pairing.mjs'));
  fs.copyFileSync(path.join(here, 'varrenmoor-bridge/scripts/pairing.js'), path.join(dir, 'pairing.mjs'));
  try {
    await import(pathToFileURL(tmp).href);
    await hooks.ready();
    for (let i = 0; i < 80 && !store.deviceAuth; i++) await sleep(100);
    const dev = JSON.parse(store.deviceAuth);
    assert.equal(dev.host, r.host); assert.ok(dev.deviceId.startsWith('d_')); assert.ok(dev.token.length >= 40);
    assert.ok(notes.some((n) => /paired with the relay/.test(n[1])));
    assert.ok(!notes.some((n) => n[1].includes(dev.token)), 'token never shown');
    await sleep(100);
    const ws = sockets.at(-1);
    assert.equal(ws.url, `ws://${r.host}/module`); ws.onopen();
    assert.deepEqual(ws.sent[0], { type: 'hello', deviceId: dev.deviceId, deviceToken: dev.token }, 'hello uses the device token, not the manual one');
    // rotation message replaces the stored token
    await ws.onmessage({ data: JSON.stringify({ type: 'welcome', rotate: { token: 'N'.repeat(43), expiresAt: '2030-01-01T00:00:00.000Z' } }) });
    assert.equal(JSON.parse(store.deviceAuth).token, 'N'.repeat(43)); assert.equal(JSON.parse(store.deviceAuth).deviceId, dev.deviceId);
    // revoked: 4005 clears the pairing, warns, and does not reconnect
    const n0 = sockets.length;
    ws.onclose({ code: 4005, reason: 'device revoked' });
    await sleep(50);
    assert.equal(store.deviceAuth, ''); assert.ok(notes.some((n) => n[0] === 'warn' && /no longer accepts/.test(n[1])));
    await sleep(1300); assert.equal(sockets.length, n0, 'no reconnect after 4005');
  } finally { await r.close(); }
});
