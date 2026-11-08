// Pairing tests (protocol 2, encrypted handshake): commit/reveal, matching confirmation codes, sealed secret hand-over once, HMAC challenge-response login, revoke,
// deny, runtime enable/disable (admin endpoint), signed admin requests, non-private source refusal, proxy/tunnel refusal, rate limits, expiry and rotation,
// no secret on the wire or in logs. Throwaway tokens, in-process relay on an ephemeral port, a stand-in for the module written with node:crypto.
//   node --test foundry-bridge/relay/pairing.test.js
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { WebSocket } from 'ws';
import { createRelay } from './server.js';
import { Pairing, isPrivateIp } from './pairing.js';
import { signAdmin } from './adminauth.js';
import * as X from './seccrypto.js';

const API = 'a'.repeat(32), MOD = 'm'.repeat(32);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const INFO = { deviceName: 'Vega GM', worldId: 'varrenmoor', userId: 'u1', userName: 'Trent', hostOrigin: 'http://vega:30000' };

async function boot(opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair-'));
  const file = path.join(dir, 'paired-devices.json');
  const ref = { ip: '127.0.0.1' };
  const logs = []; const origLog = console.log; console.log = (...a) => logs.push(a.join(' '));
  const server = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: file, peerIp: () => ref.ip, ...opts });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `127.0.0.1:${server.address().port}`;
  const wire = [];     // everything the "device" and the "admin" sent/received, to prove no secret is on the wire
  const post = async (p, body, { admin = false, signed = false, headers = {} } = {}) => {
    const raw = JSON.stringify(body || {});
    const h = { 'content-type': 'application/json', ...headers };
    if (admin) h.authorization = `Bearer ${API}`;
    if (signed) h['x-vb-auth'] = signAdmin({ token: API, method: 'POST', url: p, body: raw });
    wire.push(['>', p, raw, JSON.stringify(h)]);
    const r = await fetch(`http://${base}${p}`, { method: 'POST', headers: h, body: raw });
    const text = await r.text(); wire.push(['<', p, text]);
    return { status: r.status, body: JSON.parse(text) };
  };
  const close = async () => { console.log = origLog; server.pairing.flush(); await new Promise((r) => { server.close(r); server.closeAllConnections?.(); }); fs.rmSync(dir, { recursive: true, force: true }); };
  return { server, base, ref, file, logs, post, close, dir, wire };
}
// the device side of the protocol, written against node:crypto (the module has its own pure-JS implementation; module/pairing.test.mjs runs that one)
async function startDevice(t, info = INFO) {
  const kp = X.newKeypair(), n = X.randomBytes(16);
  const rq = await t.post('/pair/request', { commit: X.commitment(kp.pk, n) }, { headers: { origin: 'http://vega:30000' } });
  if (rq.status !== 200) return { rq };
  const rpk = X.unb64u(rq.body.relayPk), rn = X.unb64u(rq.body.relayNonce);
  const key = X.pairKey(kp.sk, rpk, kp.pk, rpk, n, rn);
  const rv = await t.post('/pair/reveal', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret, pk: X.b64u(kp.pk), nonce: X.b64u(n), info: X.sealJson(key, info, 'vb-info|' + rq.body.requestId) });
  return { rq: rq.body, rv, key, code: X.sas(kp.pk, rpk, n, rn), poll: () => t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret }) };
}
const finish = async (t, dev, days = 90) => {
  const l = await t.post('/pair/list', {}, { admin: true });
  const p = l.body.pending.find((x) => x.code === dev.code.replace(' ', '')); assert.ok(p, 'the approver sees the same code the device computed');
  assert.equal((await t.post('/pair/approve', { id: p.id, days }, { admin: true })).status, 200);
  const got = await dev.poll(); assert.equal(got.body.state, 'approved');
  const cred = X.openJson(dev.key, got.body.sealed, 'vb-dev|' + dev.rq.requestId + '|' + got.body.deviceId);
  assert.ok(cred && cred.secret, 'device opens the sealed credential');
  return { deviceId: got.body.deviceId, secret: X.unb64u(cred.secret), cred, got };
};
const pair = async (t, info) => { const dev = await startDevice(t, info); assert.equal(dev.rv.status, 200); return finish(t, dev); };
// WebSocket login by challenge-response
const login = async (base, d, { secret = d.secret } = {}) => {
  const ws = new WebSocket(`ws://${base}/module`);
  const closed = new Promise((r) => ws.on('close', (c) => r(c)));
  await new Promise((r, j) => { ws.on('open', r); ws.on('error', j); });
  const next = () => Promise.race([new Promise((r) => ws.once('message', (x) => r(JSON.parse(x)))), closed.then((c) => ({ closed: c }))]);
  const cn = X.b64u(X.randomBytes(16));
  ws.send(JSON.stringify({ type: 'hello', deviceId: d.deviceId, cn }));
  const ch = await next(); if (ch.closed) return { ws, closed, first: ch };
  ws.send(JSON.stringify({ type: 'auth', mac: X.clientMac(secret, d.deviceId, cn, ch.rn) }));
  const first = await next();
  return { ws, closed, first, cn, rn: ch.rn };
};

test('isPrivateIp', () => {
  for (const a of ['127.0.0.1', '10.0.0.15', '192.168.1.5', '172.16.0.1', '172.31.255.1', '::1', '::ffff:10.1.2.3', 'fd12::1', 'fe80::1', '169.254.1.1']) assert.ok(isPrivateIp(a), a);
  for (const a of ['8.8.8.8', '172.32.0.1', '172.15.0.1', '100.64.0.1', '0.0.0.0', '2606:4700::1', '', undefined, '999.1.1.1', 'abc', '::ffff:8.8.8.8']) assert.ok(!isPrivateIp(a), String(a));
});

test('encrypted pairing end to end: codes match, secret sealed once, challenge-response login, revoke, nothing secret on the wire or in logs', async () => {
  const t = await boot();
  try {
    const dj = await (await fetch(`http://${t.base}/discover`)).json();
    assert.equal(dj.service, 'varrenmoor-bridge-relay'); assert.equal(dj.protocol, 2); assert.equal(dj.pairing, true); assert.equal(dj.autoRequest, true); assert.ok(!JSON.stringify(dj).includes(MOD) && !JSON.stringify(dj).includes(API));
    const dev = await startDevice(t);
    assert.equal(dev.rv.status, 200); assert.match(dev.code, /^\d{3} \d{3}$/);
    // the request is only listed after the reveal; the panel/relay shows the same code the device computed on its own
    assert.equal((await t.post('/pair/list', {})).status, 401);
    const l = await t.post('/pair/list', {}, { admin: true });
    assert.equal(l.body.pending.length, 1); assert.equal(l.body.pending[0].code, dev.code.replace(' ', ''));
    assert.equal(l.body.pending[0].name, 'Vega GM'); assert.equal(l.body.pending[0].origin, 'http://vega:30000'); assert.equal(l.body.pending[0].originMismatch, false);
    assert.equal(l.body.enabled, true);
    assert.deepEqual((await dev.poll()).body, { state: 'pending' });
    assert.equal((await t.post('/pair/poll', { requestId: dev.rq.requestId, pollSecret: 'nope' })).body.state, 'unknown');
    assert.equal((await t.post('/pair/approve', { id: l.body.pending[0].id }, {})).status, 401, 'approve needs the API token');
    const d = await finish(t, dev, 30);
    assert.equal((await dev.poll()).body.state, 'delivered', 'credential only once');
    // the sealed credential is useless to anyone without the handshake key
    assert.equal(X.openJson(X.randomBytes(32), d.got.body.sealed, 'vb-dev|' + dev.rq.requestId + '|' + d.deviceId), null);
    // login: wrong secret refused, right secret welcomed with a relay proof the device can verify, manual token still works
    const proofOk = (r) => r.first.proof === X.relayMac(d.secret, d.deviceId, r.cn, r.rn);
    const good = await login(t.base, d); assert.equal(good.first.type, 'welcome'); assert.ok(proofOk(good), 'relay proves it knows the secret');
    assert.equal(JSON.parse(await (await fetch(`http://${t.base}/health`)).text()).moduleConnected, true);
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.devices[0].lastSeen !== null, true);
    // revoke closes the live socket with 4005 and the credential no longer works
    assert.equal((await t.post('/pair/revoke', { deviceId: d.deviceId }, { admin: true })).status, 200);
    assert.equal(await good.closed, 4005);
    assert.equal(await (await login(t.base, d)).closed, 4005);
    const manual = await new Promise((res) => { const ws = new WebSocket(`ws://${t.base}/module`); ws.on('open', () => ws.send(JSON.stringify({ type: 'hello', token: MOD }))); ws.on('message', (x) => res({ ws, m: JSON.parse(x) })); });
    assert.equal(manual.m.type, 'welcome', 'manual token path still works'); manual.ws.close();
    // sniffer's view: nothing in any request/response (or in the log) contains the credential, the poll-less secret or the handshake key
    const all = t.wire.map((w) => w.join(' ')).join('\n') + '\n' + t.logs.join('\n');
    for (const secret of [X.b64u(d.secret), X.b64u(dev.key), MOD]) assert.ok(!all.includes(secret), 'secret on the wire/log');
    assert.ok(!t.wire.filter((w) => /^\/pair\/(request|reveal|poll)$/.test(w[1])).map((w) => w.join(' ')).join(' ').includes('Vega GM'), 'device description travels sealed (only the admin list shows it)');
    assert.ok(!t.logs.join('\n').includes(dev.rq.pollSecret) && !t.logs.join('\n').includes(MOD) && !t.logs.join('\n').includes(dev.code), 'no secrets or codes in the log');
    // stored secrets file holds no handshake material and no admin tokens
    t.server.pairing.flush(); const disk = fs.readFileSync(t.file, 'utf8'); assert.ok(!disk.includes(API) && !disk.includes(MOD));
  } finally { await t.close(); }
});

test('commitment is enforced; a man in the middle gets different codes; protocol-1 clients get a clear message', async () => {
  const t = await boot();
  try {
    // wrong reveal (key not matching the commitment) is rejected
    const kp = X.newKeypair(), n = X.randomBytes(16), other = X.newKeypair();
    const rq = await t.post('/pair/request', { commit: X.commitment(kp.pk, n) });
    const key = X.pairKey(other.sk, X.unb64u(rq.body.relayPk), other.pk, X.unb64u(rq.body.relayPk), n, X.unb64u(rq.body.relayNonce));
    const rv = await t.post('/pair/reveal', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret, pk: X.b64u(other.pk), nonce: X.b64u(n), info: X.sealJson(key, INFO, 'vb-info|' + rq.body.requestId) });
    assert.equal(rv.status, 400); assert.match(rv.body.error, /commitment/);
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.pending.length, 0);
    t.ref.ip = '10.0.0.77'; t.server.pairing.coolUntil.clear();
    // MITM: the device talks to the attacker (keys m1), the attacker talks to the relay (keys m2): the codes differ
    const dKp = X.newKeypair(), dN = X.randomBytes(16), m1 = X.newKeypair(), m1n = X.randomBytes(16);
    const m2 = X.newKeypair(), m2n = X.randomBytes(16);
    const rq2 = await t.post('/pair/request', { commit: X.commitment(m2.pk, m2n) });
    const rpk = X.unb64u(rq2.body.relayPk), rn = X.unb64u(rq2.body.relayNonce), mkey = X.pairKey(m2.sk, rpk, m2.pk, rpk, m2n, rn);
    assert.equal((await t.post('/pair/reveal', { requestId: rq2.body.requestId, pollSecret: rq2.body.pollSecret, pk: X.b64u(m2.pk), nonce: X.b64u(m2n), info: X.sealJson(mkey, INFO, 'vb-info|' + rq2.body.requestId) })).status, 200);
    const relayShows = (await t.post('/pair/list', {}, { admin: true })).body.pending[0].code, deviceShows = X.sas(dKp.pk, m1.pk, dN, m1n).replace(' ', '');
    assert.notEqual(relayShows, deviceShows, 'the human sees different codes and presses Deny');
    // an old (0.4.x) module that sends no commitment
    t.ref.ip = '10.0.0.78'; const old = await t.post('/pair/request', { deviceName: 'old module' });
    assert.equal(old.status, 400); assert.match(old.body.error, /update the Foundry module/);
  } finally { await t.close(); }
});

test('deny, and a denied address cools down', async () => {
  const t = await boot();
  try {
    const dev = await startDevice(t);
    const p = (await t.post('/pair/list', {}, { admin: true })).body.pending[0];
    assert.equal((await t.post('/pair/deny', { id: p.id }, { admin: true })).status, 200);
    assert.equal((await dev.poll()).body.state, 'denied');
    assert.equal((await t.post('/pair/approve', { id: p.id }, { admin: true })).status, 404, 'denied request cannot be approved later');
    assert.equal((await startDevice(t)).rq.status, 429, 'cool-down after deny');
  } finally { await t.close(); }
});

test('pairing can be switched on and off at runtime by the admin (no restart), also with a signed request; refused from elsewhere', async () => {
  const t = await boot({ pairingEnabled: false });
  try {
    assert.equal((await (await fetch(`http://${t.base}/discover`)).json()).pairing, false, 'discover still answers so the module can explain');
    assert.equal((await startDevice(t)).rq.status, 404, 'device endpoints are off');
    assert.equal(JSON.parse(await (await fetch(`http://${t.base}/health`)).text()).pairing.enabled, false);
    assert.equal((await t.post('/pair/config', { enabled: true })).status, 401, 'needs the admin token');
    const st = await t.post('/pair/config', {}, { signed: true }); assert.deepEqual([st.status, st.body.enabled, st.body.canEnable], [200, false, true], 'signed read of the state');
    assert.equal((await t.post('/pair/config', { enabled: true }, { signed: true })).body.enabled, true);
    assert.equal((await startDevice(t)).rv.status, 200, 'pairing works right after, no restart');
    // another "origin" (a different PC: browser Origin header and source address) can approve with the admin token
    t.ref.ip = '10.0.0.99'; const p = (await t.post('/pair/list', {}, { admin: true, headers: { origin: 'http://arcturus:8080' } })).body.pending;
    assert.equal(p.length, 1); assert.equal((await t.post('/pair/approve', { id: p[0].id }, { signed: true, headers: { origin: 'http://arcturus:8080' } })).status, 200);
    // persisted: a new Pairing on the same file keeps the setting
    assert.equal(new Pairing({ file: t.file, enabled: false }).enabled, true);
    assert.equal((await t.post('/pair/config', { enabled: false, autoRequest: false }, { admin: true })).body.autoRequest, false);
    assert.equal((await startDevice(t)).rq.status, 404);
    assert.equal((await (await fetch(`http://${t.base}/discover`)).json()).autoRequest, false);
    // proxied / public callers cannot switch it
    t.ref.ip = '8.8.8.8'; assert.equal((await t.post('/pair/config', { enabled: true }, { admin: true })).status, 403);
    t.ref.ip = '127.0.0.1'; assert.equal((await t.post('/pair/config', { enabled: true }, { admin: true, headers: { 'cf-connecting-ip': '1.2.3.4' } })).status, 403);
    assert.equal((await t.post('/pair/config', {}, { admin: true })).body.enabled, false, 'still off');
  } finally { await t.close(); }
  // a relay started without any pairing file cannot be switched on live: it says so plainly
  const logs = console.log; console.log = () => {};
  const bare = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: null }); await new Promise((r) => bare.listen(0, '127.0.0.1', r)); console.log = logs;
  try {
    const r = await fetch(`http://127.0.0.1:${bare.address().port}/pair/config`, { method: 'POST', headers: { authorization: `Bearer ${API}`, 'content-type': 'application/json' }, body: '{"enabled":true}' });
    assert.equal(r.status, 409); assert.match((await r.json()).error, /restart it once/);
  } finally { await new Promise((r) => { bare.close(r); bare.closeAllConnections?.(); }); }
});

test('signed admin requests: the token is never sent; replay, tampering, stale clock and a wrong token are refused', async () => {
  const t = await boot();
  try {
    const raw = '{}', url = '/pair/list';
    const good = signAdmin({ token: API, method: 'POST', url, body: raw });
    const call = (hdr, body = raw) => fetch(`http://${t.base}${url}`, { method: 'POST', headers: { 'content-type': 'application/json', 'x-vb-auth': hdr }, body }).then(async (r) => ({ status: r.status, body: await r.json() }));
    assert.equal((await call(good)).status, 200);
    assert.equal((await call(good)).status, 401, 'replay of the same signed request');
    assert.equal((await call(signAdmin({ token: API, method: 'POST', url, body: raw }), '{"x":1}')).status, 401, 'body tampering');
    assert.equal((await call(signAdmin({ token: API, method: 'POST', url: '/pair/approve', body: raw }))).status, 401, 'signature for another path');
    assert.equal((await call(signAdmin({ token: 'b'.repeat(32), method: 'POST', url, body: raw }))).status, 401, 'wrong token');
    const old = await call(signAdmin({ token: API, method: 'POST', url, body: raw, ts: Date.now() - 20 * 60000 }));
    assert.equal(old.status, 401); assert.match(old.body.error, /clock/);
    assert.ok(!good.includes(API));
  } finally { await t.close(); }
});

test('refuses non-private source addresses and proxied requests', async () => {
  const t = await boot();
  try {
    t.ref.ip = '8.8.8.8';
    for (const [p, b] of [['/pair/request', {}], ['/pair/reveal', {}], ['/pair/poll', {}], ['/pair/list', {}], ['/pair/config', {}]]) { const r = await t.post(p, b, { admin: true }); assert.equal(r.status, 403, p); }
    assert.equal((await fetch(`http://${t.base}/discover`)).status, 403);
    t.ref.ip = '::ffff:203.0.113.9';
    assert.equal((await t.post('/pair/request', {})).status, 403);
    t.ref.ip = '127.0.0.1';
    // through a tunnel (Cloudflare) the source is loopback but the proxy headers give it away
    for (const h of ['cf-connecting-ip', 'cf-ray', 'x-forwarded-for', 'x-forwarded-host', 'forwarded', 'x-real-ip']) {
      assert.equal((await t.post('/pair/request', {}, { headers: { [h]: '1.2.3.4' } })).status, 403, h);
      assert.equal((await t.post('/pair/approve', { id: 'p_x' }, { admin: true, headers: { [h]: '1.2.3.4' } })).status, 403, 'tunnelled admin call refused: ' + h);
    }
    assert.equal((await fetch(`http://${t.base}/discover`, { headers: { 'cf-connecting-ip': '1.2.3.4' } })).status, 403);
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.pending.length, 0, 'nothing got through');
    // device login from a public address is closed
    const dev = await pair(t); t.ref.ip = '8.8.4.4';
    assert.equal(await (await login(t.base, dev)).closed, 4003);
  } finally { await t.close(); }
});

test('rate limits: requests per address, pending per address, polling, bad device logins', async () => {
  const t = await boot({ pairingLimits: { requestsPerWindow: 5, maxPendingPerIp: 3, maxPending: 10, pollsPerMin: 5, authFailsPerMin: 3 } });
  try {
    for (let i = 0; i < 3; i++) assert.equal((await startDevice(t)).rq.status, undefined);   // startDevice returns {rq: body}; a refusal returns the whole response
    assert.equal((await startDevice(t)).rq.status, 429, 'pending per address');
    for (const p of (await t.post('/pair/list', {}, { admin: true })).body.pending) await t.post('/pair/deny', { id: p.id }, { admin: true });
    t.server.pairing.coolUntil.clear();
    assert.equal((await startDevice(t)).rv.status, 200);
    assert.equal((await startDevice(t)).rq.status, 429, 'window limit (5 per window, refused attempts count)');
    let last; for (let i = 0; i < 7; i++) last = await t.post('/pair/poll', { requestId: 'p_x', pollSecret: 'y' });
    assert.equal(last.status, 429, 'poll limit');
    Object.assign(t.server.pairing.limits, { requestsPerWindow: 99, pollsPerMin: 99, maxPendingPerIp: 99 }); t.server.pairing.coolUntil.clear();
    for (const p of (await t.post('/pair/list', {}, { admin: true })).body.pending) await t.post('/pair/deny', { id: p.id }, { admin: true });
    t.server.pairing.coolUntil.clear();
    const dev = await pair(t);
    const seen = [];
    for (let i = 0; i < 3; i++) seen.push(await (await login(t.base, dev, { secret: X.randomBytes(32) })).closed);
    assert.deepEqual(seen, [4005, 4005, 4005]);
    assert.equal(await (await login(t.base, dev)).closed, 4008, 'locked out after repeated failures, even with the right secret');
  } finally { await t.close(); }
});

test('pending requests expire; spoofed origin is flagged; disabled without a file', async () => {
  let now = 1_000_000; const p = new Pairing({ file: null, now: () => now });
  assert.equal(p.request({ ip: '10.0.0.2', commit: 'x' }).status, 404, 'disabled without a file');
  assert.equal(p.configure({ enabled: true }).status, 409);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair2-')); const file = path.join(dir, 'p.json');
  try {
    const q = new Pairing({ file, now: () => now, pendingTtlMs: 1000 });
    const kp = X.newKeypair(), n = X.randomBytes(16);
    const r = q.request({ ip: '10.0.0.2', origin: 'http://evil.example', commit: X.commitment(kp.pk, n) });
    const key = X.pairKey(kp.sk, X.unb64u(r.relayPk), kp.pk, X.unb64u(r.relayPk), n, X.unb64u(r.relayNonce));
    assert.equal(q.reveal({ requestId: r.requestId, pollSecret: r.pollSecret, pk: X.b64u(kp.pk), nonce: X.b64u(n), info: X.sealJson(key, { deviceName: 'GM', hostOrigin: 'http://vega:30000' }, 'vb-info|' + r.requestId), ip: '10.0.0.2' }).status, 200);
    assert.equal(q.list().pending[0].originMismatch, true);
    now += 2000;
    assert.equal(q.approve(q.list().pending[0]?.id || 'x').status, 404);
    assert.equal(q.poll(r.requestId, r.pollSecret, '10.0.0.2').state, 'expired');
    assert.equal(q.list().pending.length, 0);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('device expiry and secret rotation over the sealed channel (old secret has a short grace window)', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair3-')); const file = path.join(dir, 'p.json');
  let now = Date.parse('2026-01-01T00:00:00Z');
  const day = 86400000, IP = '10.0.0.2';
  try {
    const p = new Pairing({ file, now: () => now });
    const mk = (ip, days) => {
      const kp = X.newKeypair(), n = X.randomBytes(16), r = p.request({ ip, commit: X.commitment(kp.pk, n) });
      const key = X.pairKey(kp.sk, X.unb64u(r.relayPk), kp.pk, X.unb64u(r.relayPk), n, X.unb64u(r.relayNonce));
      p.reveal({ requestId: r.requestId, pollSecret: r.pollSecret, pk: X.b64u(kp.pk), nonce: X.b64u(n), info: X.sealJson(key, { deviceName: 'GM ' + ip }, 'vb-info|' + r.requestId), ip });
      const a = p.approve(p.list().pending[0].id, { days }), g = p.poll(r.requestId, r.pollSecret, ip);
      const cred = X.openJson(key, g.sealed, 'vb-dev|' + r.requestId + '|' + a.deviceId);
      return { id: a.deviceId, secret: X.unb64u(cred.secret) };
    };
    const auth = (d, secret = d.secret, ip = IP) => { const cn = X.b64u(X.randomBytes(16)), rn = X.b64u(X.randomBytes(16)); const a = p.authenticate(d.id, cn, rn, X.clientMac(secret, d.id, cn, rn), ip); return { a, cn, rn }; };
    const d = mk(IP, 30);
    let r = auth(d); assert.ok(r.a.ok && !r.a.rotate, 'fresh secret is not rotated');
    assert.equal(r.a.proof, X.relayMac(d.secret, d.id, r.cn, r.rn));
    now += 20 * day;                                    // 10 days left (< 14): rotates on connect
    r = auth(d); assert.ok(r.a.ok && r.a.rotate);
    const rot = X.openJson(X.rotationKey(d.secret, d.id, r.cn, r.rn), r.a.rotate.sealed, 'vb-rot|' + d.id);
    assert.ok(rot && rot.secret && rot.secret !== X.b64u(d.secret));
    assert.ok(Date.parse(r.a.rotate.expiresAt) > now + 29 * day, 'expiry extended by the lifetime');
    const next = { id: d.id, secret: X.unb64u(rot.secret) };
    now += 60000; assert.ok(auth(d).a.ok, 'old secret still works within the grace window');
    now += 10 * 60000; assert.equal(auth(d).a.ok, false, 'old secret dead after the grace window');
    assert.ok(auth(next).a.ok, 'new secret works');
    p.rotate(d.id); const b = auth(next); assert.ok(b.a.rotate, 'explicit rotate request from the panel');
    const next2 = { id: d.id, secret: X.unb64u(X.openJson(X.rotationKey(next.secret, d.id, b.cn, b.rn), b.a.rotate.sealed, 'vb-rot|' + d.id).secret) };
    now += 31 * day; const c = auth(next2); assert.equal(c.a.ok, false); assert.equal(c.a.reason, 'expired');
    const perm = mk('10.0.0.3', 0); now += 3650 * day;
    assert.ok(auth(perm, perm.secret, '10.0.0.3').a.ok, 'never-expiring device');
    // survives a restart; the setting and the devices are on disk
    p.flush(); const p2 = new Pairing({ file, now: () => now });
    assert.equal(p2.relayId, p.relayId); assert.equal(p2.data.devices.length, 2);
    // protocol-1 records (hashed token, no secret) are dropped on load
    fs.writeFileSync(file, JSON.stringify({ version: 1, relayId: 'r_old', devices: [{ id: 'd_old', hash: 'x' }] })); assert.equal(new Pairing({ file }).data.devices.length, 0);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('one live request and one record per browser: a second request supersedes the first, cancel clears it, re-approval replaces the old device (no duplicates)', async () => {
  const t = await boot({ pairingLimits: { requestsPerWindow: 50, maxPendingPerIp: 50, maxPending: 50 } });
  try {
    const info = { ...INFO, clientId: 'browser-1' };
    const a = await startDevice(t, info), b = await startDevice(t, info);
    const list = (await t.post('/pair/list', {}, { admin: true })).body.pending;
    assert.equal(list.length, 1, 'only the newest request from the same browser is listed');
    assert.equal(list[0].code, b.code.replace(' ', ''), 'the listed code is the live one');
    assert.notEqual(a.code, b.code); assert.equal((await a.poll()).body.state, 'expired', 'the superseded request is dead');
    // cancel (dialog closed) removes it at once
    const c = await startDevice(t, { ...INFO, clientId: 'browser-2' });
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.pending.length, 2);
    await t.post('/pair/cancel', { requestId: c.rq.requestId, pollSecret: c.rq.pollSecret });
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.pending.length, 1);
    // approve browser-1 twice (second pairing of the same browser): one record, newest id
    const d1 = await finish(t, b);
    const e = await startDevice(t, info); const d2 = await finish(t, e);
    const devs = (await t.post('/pair/list', {}, { admin: true })).body.devices;
    assert.equal(devs.length, 1); assert.equal(devs[0].id, d2.deviceId); assert.equal(devs[0].clientId, 'browser-1');
    assert.notEqual(d1.deviceId, d2.deviceId);
    // the replaced credential no longer logs in; the live one does; replacing does not close a live socket with 4005
    assert.equal(await (await login(t.base, d1)).closed, 4005);
    const live = await login(t.base, d2); assert.equal(live.first.type, 'welcome');
    const f = await startDevice(t, info); await finish(t, f);
    await sleep(150); assert.equal(live.ws.readyState, 1, 'an old live socket is not killed by the replacement');
    live.ws.close();
    // older modules without a browser id: same name/user/world/origin also collapses
    const g = await startDevice(t, INFO); await finish(t, g); const h = await startDevice(t, INFO); await finish(t, h);
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.devices.filter((x) => x.name === INFO.deviceName && !x.clientId).length, 1);
  } finally { await t.close(); }
});
