// Pairing tests: request -> approve -> token hand-over once -> connect with the device token -> revoke closes the socket; deny; expiry and rotation;
// non-private source refusal; proxy-header refusal; rate limits; hashed storage; no token in logs. Throwaway tokens, in-process relay on an ephemeral port.
//   node --test foundry-bridge/relay/pairing.test.js
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { WebSocket } from 'ws';
import { createRelay } from './server.js';
import { Pairing, isPrivateIp } from './pairing.js';

const API = 'a'.repeat(32), MOD = 'm'.repeat(32);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function boot(opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair-'));
  const file = path.join(dir, 'paired-devices.json');
  const ref = { ip: '127.0.0.1' };
  const logs = []; const origLog = console.log; console.log = (...a) => logs.push(a.join(' '));
  const server = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: file, peerIp: () => ref.ip, ...opts });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `127.0.0.1:${server.address().port}`;
  const post = async (p, body, { admin = false, headers = {} } = {}) => {
    const r = await fetch(`http://${base}${p}`, { method: 'POST', headers: { 'content-type': 'application/json', ...(admin ? { authorization: `Bearer ${API}` } : {}), ...headers }, body: JSON.stringify(body || {}) });
    return { status: r.status, body: await r.json() };
  };
  const close = async () => { console.log = origLog; server.pairing.flush(); await new Promise((r) => { server.close(r); server.closeAllConnections?.(); }); fs.rmSync(dir, { recursive: true, force: true }); };
  return { server, base, ref, file, logs, post, close, dir };
}
const connect = async (base, hello) => {
  const ws = new WebSocket(`ws://${base}/module`);
  const closed = new Promise((r) => ws.on('close', (c) => r(c)));
  await new Promise((r, j) => { ws.on('open', r); ws.on('error', j); });
  ws.send(JSON.stringify(hello));
  const first = await Promise.race([new Promise((r) => ws.once('message', (d) => r(JSON.parse(d)))), closed.then((c) => ({ closed: c }))]);
  return { ws, closed, first };
};
const pair = async (t, name = 'GM tab', days = 90) => {
  const rq = await t.post('/pair/request', { deviceName: name, worldId: 'varrenmoor', userId: 'u1', userName: 'Trent', hostOrigin: 'http://vega:30000' }, { headers: { origin: 'http://vega:30000' } });
  assert.equal(rq.status, 200);
  const ap = await t.post('/pair/approve', { id: rq.body.requestId, days }, { admin: true });
  assert.equal(ap.status, 200);
  const pl = await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret });
  assert.equal(pl.body.state, 'approved');
  return { rq: rq.body, ap: ap.body, token: pl.body.token, deviceId: pl.body.deviceId };
};

test('isPrivateIp', () => {
  for (const a of ['127.0.0.1', '10.0.0.15', '192.168.1.5', '172.16.0.1', '172.31.255.1', '::1', '::ffff:10.1.2.3', 'fd12::1', 'fe80::1', '169.254.1.1']) assert.ok(isPrivateIp(a), a);
  for (const a of ['8.8.8.8', '172.32.0.1', '172.15.0.1', '100.64.0.1', '0.0.0.0', '2606:4700::1', '', undefined, '999.1.1.1', 'abc', '::ffff:8.8.8.8']) assert.ok(!isPrivateIp(a), String(a));
});

test('pair, approve, token handed over once, device connects, revoke closes the socket', async () => {
  const t = await boot();
  try {
    const disc = await fetch(`http://${t.base}/discover`); const dj = await disc.json();
    assert.equal(dj.service, 'varrenmoor-bridge-relay'); assert.ok(dj.relayId); assert.ok(!JSON.stringify(dj).includes(MOD) && !JSON.stringify(dj).includes(API));
    assert.equal(disc.headers.get('access-control-allow-origin'), '*');

    const rq = await t.post('/pair/request', { deviceName: 'Vega GM', worldId: 'w', userId: 'u', userName: 'Trent', hostOrigin: 'http://vega:30000' }, { headers: { origin: 'http://vega:30000' } });
    assert.equal(rq.status, 200); assert.match(rq.body.code, /^\d{3} \d{3}$/);
    // admin list needs the API token and shows the same code the device was given
    assert.equal((await t.post('/pair/list', {})).status, 401);
    const l = await t.post('/pair/list', {}, { admin: true });
    assert.equal(l.body.pending.length, 1); assert.equal(l.body.pending[0].code.replace(' ', ''), rq.body.code.replace(' ', ''));
    assert.equal(l.body.pending[0].name, 'Vega GM'); assert.equal(l.body.pending[0].ip, '127.0.0.1'); assert.equal(l.body.pending[0].origin, 'http://vega:30000'); assert.equal(l.body.pending[0].originMismatch, false);
    // not approved yet: poll says pending and leaks nothing; wrong secret is "unknown"
    assert.deepEqual((await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret })).body, { state: 'pending' });
    assert.equal((await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: 'nope' })).body.state, 'unknown');
    assert.equal((await t.post('/pair/approve', { id: rq.body.requestId }, {})).status, 401, 'approve needs the API token');
    assert.equal((await t.post('/pair/approve', { id: rq.body.requestId, days: 30 }, { admin: true })).status, 200);
    const got = await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret });
    assert.equal(got.body.state, 'approved'); assert.ok(got.body.token.length >= 40); assert.ok(got.body.deviceId.startsWith('d_'));
    assert.equal((await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret })).body.state, 'delivered', 'token only once');

    // stored hashed, never plain
    t.server.pairing.flush();
    const disk = fs.readFileSync(t.file, 'utf8');
    assert.ok(!disk.includes(got.body.token), 'token must not be on disk'); assert.ok(disk.includes('"hash"'));
    // device token connects (and the manual token still works)
    const d = await connect(t.base, { type: 'hello', deviceId: got.body.deviceId, deviceToken: got.body.token });
    assert.equal(d.first.type, 'welcome');
    assert.equal(JSON.parse(await (await fetch(`http://${t.base}/health`)).text()).moduleConnected, true);
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.devices[0].lastSeen !== null, true);
    // revoke closes the live socket with 4005 and the token no longer works
    assert.equal((await t.post('/pair/revoke', { deviceId: got.body.deviceId }, { admin: true })).status, 200);
    assert.equal(await d.closed, 4005);
    const again = await connect(t.base, { type: 'hello', deviceId: got.body.deviceId, deviceToken: got.body.token });
    assert.equal(await again.closed, 4005);
    const manual = await connect(t.base, { type: 'hello', token: MOD });
    assert.equal(manual.first.type, 'welcome', 'manual token path still works'); manual.ws.close();
    assert.ok(!t.logs.join('\n').includes(got.body.token) && !t.logs.join('\n').includes(rq.body.pollSecret) && !t.logs.join('\n').includes(MOD), 'no secrets in the log');
  } finally { await t.close(); }
});

test('deny, and a denied address cools down', async () => {
  const t = await boot();
  try {
    const rq = await t.post('/pair/request', { deviceName: 'x' });
    assert.equal((await t.post('/pair/deny', { id: rq.body.requestId }, { admin: true })).status, 200);
    assert.equal((await t.post('/pair/poll', { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret })).body.state, 'denied');
    assert.equal((await t.post('/pair/approve', { id: rq.body.requestId }, { admin: true })).status, 404, 'denied request cannot be approved later');
    assert.equal((await t.post('/pair/request', { deviceName: 'x' })).status, 429, 'cool-down after deny');
  } finally { await t.close(); }
});

test('refuses non-private source addresses and proxied requests', async () => {
  const t = await boot();
  try {
    t.ref.ip = '8.8.8.8';
    for (const [p, b] of [['/pair/request', { deviceName: 'x' }], ['/pair/poll', {}], ['/pair/list', {}]]) { const r = await t.post(p, b, { admin: true }); assert.equal(r.status, 403, p); }
    assert.equal((await fetch(`http://${t.base}/discover`)).status, 403);
    t.ref.ip = '::ffff:203.0.113.9';
    assert.equal((await t.post('/pair/request', { deviceName: 'x' })).status, 403);
    t.ref.ip = '127.0.0.1';
    // through a tunnel (Cloudflare) the source is loopback but the proxy headers give it away
    for (const h of ['cf-connecting-ip', 'x-forwarded-for']) {
      assert.equal((await t.post('/pair/request', { deviceName: 'x' }, { headers: { [h]: '1.2.3.4' } })).status, 403, h);
      assert.equal((await t.post('/pair/approve', { id: 'p_x' }, { admin: true, headers: { [h]: '1.2.3.4' } })).status, 403, 'tunnelled admin call refused: ' + h);
    }
    assert.equal((await t.post('/pair/list', {}, { admin: true })).body.pending.length, 0, 'nothing got through');
    // device-token WebSocket hello from a public address is closed
    const dev = await pair(t); t.ref.ip = '8.8.4.4';
    assert.equal(await (await connect(t.base, { type: 'hello', deviceId: dev.deviceId, deviceToken: dev.token })).closed, 4003);
  } finally { await t.close(); }
});

test('rate limits: requests per address, pending per address, polling, bad device tokens', async () => {
  const t = await boot({ pairingLimits: { requestsPerWindow: 5, maxPendingPerIp: 3, maxPending: 10, pollsPerMin: 5, authFailsPerMin: 3 } });
  try {
    const codes = [];
    for (let i = 0; i < 3; i++) { const r = await t.post('/pair/request', { deviceName: 'n' + i }); assert.equal(r.status, 200); codes.push(r.body.code); }
    assert.equal((await t.post('/pair/request', { deviceName: 'n3' })).status, 429, 'pending per address');
    const l = await t.post('/pair/list', {}, { admin: true });
    for (const p of l.body.pending) await t.post('/pair/deny', { id: p.id }, { admin: true });
    t.server.pairing.coolUntil.clear();
    assert.equal((await t.post('/pair/request', { deviceName: 'n4' })).status, 200);
    assert.equal((await t.post('/pair/request', { deviceName: 'n5' })).status, 429, 'window limit (5 per window, refused attempts count)');
    let last; for (let i = 0; i < 7; i++) last = await t.post('/pair/poll', { requestId: 'p_x', pollSecret: 'y' });
    assert.equal(last.status, 429, 'poll limit');
    Object.assign(t.server.pairing.limits, { requestsPerWindow: 99, pollsPerMin: 99, maxPendingPerIp: 99 }); t.server.pairing.coolUntil.clear();
    const dev = await pair(t);
    const codesSeen = [];
    for (let i = 0; i < 3; i++) codesSeen.push(await (await connect(t.base, { type: 'hello', deviceId: dev.deviceId, deviceToken: 'wrong' + i })).closed);
    assert.deepEqual(codesSeen, [4005, 4005, 4005]);
    assert.equal(await (await connect(t.base, { type: 'hello', deviceId: dev.deviceId, deviceToken: dev.token })).closed, 4008, 'locked out after repeated failures, even with the right token');
  } finally { await t.close(); }
});

test('pending requests expire; spoofed origin is flagged', async () => {
  let now = 1_000_000; const p = new Pairing({ file: null, now: () => now });
  assert.equal(p.request({ ip: '10.0.0.2' }).status, 404, 'disabled without a file');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair2-')); const file = path.join(dir, 'p.json');
  try {
    const q = new Pairing({ file, now: () => now, pendingTtlMs: 1000 });
    const r = q.request({ ip: '10.0.0.2', origin: 'http://evil.example', info: { deviceName: 'GM', hostOrigin: 'http://vega:30000' } });
    assert.equal(q.list().pending[0].originMismatch, true);
    now += 2000;
    assert.equal(q.approve(r.requestId).status, 404, 'expired');
    assert.equal(q.poll(r.requestId, r.pollSecret, '10.0.0.2').state, 'expired');
    assert.equal(q.list().pending.length, 0);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('device expiry and token rotation (old token has a short grace window)', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vpair3-')); const file = path.join(dir, 'p.json');
  let now = Date.parse('2026-01-01T00:00:00Z');
  const day = 86400000;
  try {
    const p = new Pairing({ file, now: () => now });
    const r = p.request({ ip: '10.0.0.2', info: { deviceName: 'GM' } });
    p.approve(r.requestId, { days: 30 });
    const got = p.poll(r.requestId, r.pollSecret, '10.0.0.2');
    let a = p.authenticate(got.deviceId, got.token, '10.0.0.2');
    assert.ok(a.ok && !a.rotate, 'fresh token is not rotated');
    now += 20 * day;                                    // 10 days left (< 14): rotates on connect
    a = p.authenticate(got.deviceId, got.token, '10.0.0.2');
    assert.ok(a.ok && a.rotate && a.rotate.token !== got.token);
    assert.ok(Date.parse(a.rotate.expiresAt) > now + 29 * day, 'expiry extended by the lifetime');
    now += 60000; assert.ok(p.authenticate(got.deviceId, got.token, '10.0.0.2').ok, 'old token still works within the grace window');
    now += 10 * 60000; assert.equal(p.authenticate(got.deviceId, got.token, '10.0.0.2').ok, false, 'old token dead after the grace window');
    assert.ok(p.authenticate(got.deviceId, a.rotate.token, '10.0.0.2').ok, 'new token works');
    // explicit rotate request from the panel
    p.rotate(got.deviceId); const b = p.authenticate(got.deviceId, a.rotate.token, '10.0.0.2');
    assert.ok(b.rotate && b.rotate.token !== a.rotate.token);
    // expiry
    now += 31 * day; const c = p.authenticate(got.deviceId, b.rotate.token, '10.0.0.2');
    assert.equal(c.ok, false); assert.equal(c.reason, 'expired');
    // never-expiring device
    const r2 = p.request({ ip: '10.0.0.3', info: { deviceName: 'perm' } }); p.approve(r2.requestId, { days: 0 });
    const g2 = p.poll(r2.requestId, r2.pollSecret, '10.0.0.3'); now += 3650 * day;
    assert.ok(p.authenticate(g2.deviceId, g2.token, '10.0.0.3').ok);
    // file is 0600-style JSON without any token
    p.flush(); const disk = fs.readFileSync(file, 'utf8');
    for (const tok of [got.token, a.rotate.token, b.rotate.token, g2.token]) assert.ok(!disk.includes(tok));
    // survives a restart
    const p2 = new Pairing({ file, now: () => now });
    assert.equal(p2.relayId, p.relayId); assert.ok(p2.authenticate(g2.deviceId, g2.token, '10.0.0.3').ok);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
