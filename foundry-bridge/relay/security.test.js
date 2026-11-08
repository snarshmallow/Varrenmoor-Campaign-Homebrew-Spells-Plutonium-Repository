// Security regression tests for the review findings F1-F13 (illustrator/out/pairing_security_review.md). Throwaway tokens, in-process relay on an ephemeral loopback port.
//   node --test foundry-bridge/relay/security.test.js
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import http from 'node:http';
import path from 'node:path';
import { WebSocket } from 'ws';
import { createRelay } from './server.js';
import { Pairing, isAllowedOrigin, isLanHostname } from './pairing.js';
import { makeAdminVerifier, signAdmin } from './adminauth.js';
import * as X from './seccrypto.js';

const API = 'a'.repeat(32), MOD = 'm'.repeat(32);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const INFO = { deviceName: 'Vega GM', worldId: 'w', userId: 'u', userName: 'T', hostOrigin: 'http://vega:30000' };

async function boot(opts = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vsec-'));
  const origLog = console.log, logs = []; console.log = (...a) => logs.push(a.join(' '));
  const server = createRelay({ apiToken: API, moduleToken: MOD, pairingFile: path.join(dir, 'paired-devices.json'), ...opts });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const port = server.address().port;
  // low-level request so Host and Origin can be chosen freely
  const req = (method, p, { body, headers = {} } = {}) => new Promise((resolve, reject) => {
    const data = body === undefined ? '' : JSON.stringify(body);
    const r = http.request({ host: '127.0.0.1', port, method, path: p, headers: { ...(data ? { 'content-type': 'application/json', 'content-length': Buffer.byteLength(data) } : {}), ...headers } }, (res) => {
      let b = ''; res.on('data', (c) => { b += c; }); res.on('end', () => { let j = null; try { j = JSON.parse(b); } catch { /* none */ } resolve({ status: res.statusCode, headers: res.headers, body: j }); });
    });
    r.on('error', reject); r.end(data);
  });
  const admin = (p, body, headers = {}) => { const raw = JSON.stringify(body || {}); return req('POST', p, { body: body || {}, headers: { 'x-vb-auth': signAdmin({ token: API, method: 'POST', url: p, body: raw }), ...headers } }); };
  const alive = async () => (await req('GET', '/health')).body.ok === true;
  const close = async () => { console.log = origLog; server.pairing.flush(); await new Promise((r) => { server.close(r); server.closeAllConnections?.(); }); fs.rmSync(dir, { recursive: true, force: true }); };
  return { server, port, req, admin, alive, close, logs, dir };
}
async function device(t, headers = { origin: 'http://vega:30000' }) {
  const kp = X.newKeypair(), n = X.randomBytes(16);
  const rq = await t.req('POST', '/pair/request', { body: { commit: X.commitment(kp.pk, n) }, headers });
  assert.equal(rq.status, 200, JSON.stringify(rq.body));
  const rpk = X.unb64u(rq.body.relayPk), rn = X.unb64u(rq.body.relayNonce), key = X.pairKey(kp.sk, rpk, kp.pk, rpk, n, rn);
  const rv = await t.req('POST', '/pair/reveal', { body: { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret, pk: X.b64u(kp.pk), nonce: X.b64u(n), info: X.sealJson(key, INFO, 'vb-info|' + rq.body.requestId) }, headers });
  assert.equal(rv.status, 200);
  return { rq: rq.body, code: X.sas(kp.pk, rpk, n, rn).replace(' ', ''), key };
}
const wsOpen = (port) => new Promise((res, rej) => { const ws = new WebSocket(`ws://127.0.0.1:${port}/module`); ws.on('open', () => res(ws)); ws.on('error', rej); });

test('F1: non-object / junk WebSocket frames never crash the relay, before or after authentication', async () => {
  const t = await boot();
  try {
    for (const frame of ['null', '[]', '"x"', '5', 'true', '{', '{"type":null}', '{"type":"hello"}', '{"type":"hello","deviceId":1}', '{"type":"auth"}', '\u0000\u0001']) {
      const ws = await wsOpen(t.port); ws.send(frame); await sleep(30); ws.close();
    }
    assert.ok(await t.alive(), 'relay survived pre-auth junk');
    const ws = await wsOpen(t.port); const welcomed = new Promise((r) => ws.once('message', r));
    ws.send(JSON.stringify({ type: 'hello', token: MOD })); await welcomed;
    for (const frame of ['null', '[]', '"x"', '5', '{"id":{"a":1}}', '{"id":null,"result":1}']) ws.send(frame);
    await sleep(60); assert.ok(await t.alive(), 'relay survived junk from an authenticated module');
    // an oversized frame before authentication is refused
    const big = await wsOpen(t.port); const closed = new Promise((r) => big.on('close', r)); big.send('x'.repeat(10000)); assert.equal(await closed, 4003);
    ws.close();
  } finally { await t.close(); }
});

test('F2: an aborted POST body on /pair/* and /rpc does not crash the relay', async () => {
  const t = await boot();
  try {
    for (const p of ['/pair/request', '/pair/approve', '/rpc']) {
      await new Promise((res) => { const s = net.connect(t.port, '127.0.0.1', () => { s.write(`POST ${p} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer ${API}\r\nContent-Type: application/json\r\nContent-Length: 500\r\n\r\n{"commit":"ab`); setTimeout(() => { s.destroy(); res(); }, 40); }); });
    }
    await sleep(100); assert.ok(await t.alive());
    assert.equal((await t.req('POST', '/rpc', { body: null, headers: { authorization: `Bearer ${API}` } })).status, 503);   // no module: 503 (and no TypeError)
    const ws = await wsOpen(t.port); const w = new Promise((r) => ws.once('message', r)); ws.send(JSON.stringify({ type: 'hello', token: MOD })); await w;
    assert.equal((await t.req('POST', '/rpc', { body: null, headers: { authorization: `Bearer ${API}` } })).status, 400, 'JSON null body is a 400, not a crash');
    ws.close();
  } finally { await t.close(); }
});

test('F5: CORS is an allow-list, never *; admin endpoints reject any Origin and send no CORS headers; non-browser clients still work', async () => {
  const t = await boot();
  try {
    const evil = { origin: 'https://evil.example' };
    for (const p of ['/pair/request', '/pair/reveal', '/pair/poll', '/pair/cancel']) { const r = await t.req('POST', p, { body: {}, headers: evil }); assert.equal(r.status, 403, p); assert.equal(r.headers['access-control-allow-origin'], undefined); }
    assert.equal((await t.req('GET', '/discover', { headers: evil })).status, 403);
    assert.equal((await t.req('GET', '/discover', { headers: { origin: 'http://10.0.0.99:8080' } })).status, 403, 'right host, wrong port');
    assert.equal((await t.req('GET', '/discover', { headers: { origin: 'http://foundry.example.com:30000' } })).status, 403, 'public name, right port');
    const ok = await t.req('GET', '/discover', { headers: { origin: 'http://vega:30000' } });
    assert.equal(ok.status, 200); assert.equal(ok.headers['access-control-allow-origin'], 'http://vega:30000'); assert.equal(ok.headers['access-control-allow-private-network'], undefined);
    const pre = await t.req('OPTIONS', '/pair/request', { headers: { origin: 'http://10.0.0.5:30000', 'access-control-request-method': 'POST', 'access-control-request-private-network': 'true' } });
    assert.equal(pre.status, 204); assert.equal(pre.headers['access-control-allow-origin'], 'http://10.0.0.5:30000'); assert.equal(pre.headers['access-control-allow-private-network'], 'true');
    assert.equal((await t.req('OPTIONS', '/pair/request', { headers: { origin: 'https://evil.example' } })).headers['access-control-allow-origin'], undefined);
    assert.equal((await t.req('GET', '/discover')).status, 200, 'no Origin header (non-browser client): fine');
    const a = await t.admin('/pair/list', {}, { origin: 'http://vega:30000' }); assert.equal(a.status, 403); assert.equal(a.headers['access-control-allow-origin'], undefined);
    assert.equal((await t.admin('/pair/list', {})).status, 200);
    assert.equal((await t.req('OPTIONS', '/pair/list', { headers: { origin: 'http://vega:30000' } })).headers['access-control-allow-origin'], undefined);
  } finally { await t.close(); }
  const t2 = await boot({ allowedOrigins: ['https://foundry.lan.example:8443'] });
  try { assert.equal((await t2.req('GET', '/discover', { headers: { origin: 'https://foundry.lan.example:8443' } })).status, 200, 'configured origin accepted'); } finally { await t2.close(); }
  assert.equal(isAllowedOrigin('null'), false); assert.equal(isAllowedOrigin('file:///x'), false);
  assert.equal(isLanHostname('8.8.8.8'), false); assert.equal(isLanHostname('abc.trycloudflare.com'), false); assert.equal(isLanHostname('vega'), true); assert.equal(isLanHostname('[::1]'), true);
});

test('F6: tunnel mode refuses /discover and /pair/* entirely; in local mode a public Host header is refused', async () => {
  const t = await boot({ tunnel: true });
  try {
    assert.equal((await t.req('GET', '/discover')).status, 403);
    assert.equal((await t.admin('/pair/list', {})).status, 403, 'even a valid signed admin call from loopback');
    assert.equal((await t.req('POST', '/pair/request', { body: {} })).status, 403);
    const h = await t.req('GET', '/health'); assert.equal(h.status, 200);
    // WebSocket device login is off too (the manual-token path is not touched)
    const ws = await wsOpen(t.port); const closed = new Promise((r) => ws.on('close', r)); ws.send(JSON.stringify({ type: 'hello', deviceId: 'd_x', cn: 'abc' })); assert.equal(await closed, 4003);
  } finally { await t.close(); }
  const l = await boot();
  try {
    for (const host of ['x.trycloudflare.com', 'relay.example.com:3030', '8.8.8.8:3030']) assert.equal((await l.req('GET', '/discover', { headers: { host } })).status, 403, host);
    assert.equal((await l.admin('/pair/list', {}, { host: 'x.trycloudflare.com' })).status, 403);
    for (const host of ['10.0.0.15:3030', 'localhost:3030', 'vega:3030', '[::1]:3030']) assert.equal((await l.req('GET', '/discover', { headers: { host } })).status, 200, host);
    assert.ok(l.logs.some((x) => /Host header is not a LAN address/.test(x)));
    // /health through a proxy shows nothing but "up"
    const hp = await l.req('GET', '/health', { headers: { 'cf-connecting-ip': '1.2.3.4' } }); assert.deepEqual(Object.keys(hp.body).sort(), ['ok', 'service']);
  } finally { await l.close(); }
});

test('F4: approval needs the code typed in; a wrong code is refused; 3 wrong tries deny; warnings flag a missing or odd origin', async () => {
  const t = await boot();
  try {
    const d = await device(t);
    const id = (await t.admin('/pair/list', {})).body.pending[0].id;
    assert.equal((await t.admin('/pair/approve', { id })).status, 400, 'no code');
    assert.equal((await t.admin('/pair/approve', { id, code: '' })).status, 400);
    const wrong = d.code === '000000' ? '111111' : '000000';
    assert.equal((await t.admin('/pair/approve', { id, code: wrong })).status, 403);
    assert.equal((await t.admin('/pair/list', {})).body.pending.length, 1, 'still waiting after one wrong code');
    const ok = await t.admin('/pair/approve', { id, code: d.code.slice(0, 3) + ' ' + d.code.slice(3) }); assert.equal(ok.status, 200, 'spaces are tolerated');
    // three wrong codes deny the request
    t.server.pairing.limits.requestsPerWindow = 99; t.server.pairing.limits.maxPendingPerIp = 9;
    const e = await device(t); const id2 = (await t.admin('/pair/list', {})).body.pending[0].id;
    await t.admin('/pair/approve', { id: id2, code: wrong }); await t.admin('/pair/approve', { id: id2, code: wrong });
    const last = await t.admin('/pair/approve', { id: id2, code: wrong }); assert.equal(last.status, 403); assert.match(last.body.error, /denied/);
    assert.equal((await t.admin('/pair/list', {})).body.pending.length, 0);
    // warnings
    t.server.pairing.coolUntil.clear();
    const f = await device(t, {}); const p = (await t.admin('/pair/list', {})).body.pending[0];
    assert.ok(p.warnings.some((w) => /no browser Origin/.test(w)), JSON.stringify(p.warnings)); void e; void f;
  } finally { await t.close(); }
});

test('F4: relay console approves only the request whose code was typed (A, digits, Enter)', async () => {
  const { attachPairingConsole } = await import('../lib/pairing-console.mjs');
  const { EventEmitter } = await import('node:events');
  const stdin = new EventEmitter(); stdin.isTTY = true; stdin.setRawMode = () => {}; stdin.resume = () => {};
  const pending = [{ id: 'p_1', code: '111222', name: 'one', ip: '10.0.0.2' }, { id: 'p_2', code: '333444', name: 'two', ip: '10.0.0.3' }];
  const calls = []; const pairing = Object.assign(new EventEmitter(), { canEnable: true, list: () => ({ pending, devices: [], enabled: true }), approve: (id, o) => { calls.push(['approve', id, o.code]); return { status: 200 }; }, deny: (id) => calls.push(['deny', id]) });
  const lines = []; attachPairingConsole(pairing, (...a) => lines.push(a.join(' ')), { interactive: true, stdin });
  const key = (k) => stdin.emit('data', Buffer.from(k));
  key('a'); assert.equal(calls.length, 0, 'A alone approves nothing');
  for (const c of '333444') key(c); key('\r');
  assert.deepEqual(calls, [['approve', 'p_2', '333444']], 'the typed code picks the request, not the oldest');
  key('a'); for (const c of '999999') key(c); key('\r'); assert.equal(calls.length, 1, 'unknown code approves nothing');
  assert.ok(lines.some((l) => /no waiting request has that code/.test(l)));
  key('a'); key('\u001b'); key('d'); assert.deepEqual(calls.at(-1), ['deny', 'p_1']);
});

test('F11: unrevealed handshakes expire fast and do not block real requests; poll/cancel are bound to the requesting address', () => {
  let now = 1000000; const p = new Pairing({ file: null, now: () => now }); p.initial.enabled = true; p.data.settings.enabled = true;
  Object.defineProperty(p, 'enabled', { get: () => true });
  const mk = (ip) => { const kp = X.newKeypair(), n = X.randomBytes(16); return { kp, n, r: p.request({ ip, commit: X.commitment(kp.pk, n) }) }; };
  p.limits.maxPendingPerIp = 99; p.limits.requestsPerWindow = 99;
  for (let i = 0; i < 8; i++) assert.equal(mk('10.0.0.' + (10 + i)).r.status, 200, 'unrevealed junk does not use the 5 approval slots');
  now += 21000; p.sweep(); assert.equal([...p.pending.values()].filter((x) => x.status === 'committed').length, 0, 'unrevealed handshakes are gone after ~20 s');
  const a = mk('10.0.0.2'); assert.equal(p.poll(a.r.requestId, a.r.pollSecret, '10.0.0.3').state, 'unknown', 'poll from another address learns nothing');
  assert.equal(p.poll(a.r.requestId, a.r.pollSecret, '10.0.0.2').state, 'pending');
  p.cancel(a.r.requestId, a.r.pollSecret, '10.0.0.9'); assert.equal(p.poll(a.r.requestId, a.r.pollSecret, '10.0.0.2').state, 'pending', 'cancel from another address ignored');
  p.cancel(a.r.requestId, a.r.pollSecret, '10.0.0.2'); assert.equal(p.poll(a.r.requestId, a.r.pollSecret, '10.0.0.2').state, 'expired');
});

test('F12: a captured signed admin call cannot be replayed after a relay restart; fresh ones still work', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vsec2-')), file = path.join(dir, 'admin-ts.json');
  try {
    let now = 5000000000000; const mkreq = (ts, n) => { const raw = '{}'; return { req: { method: 'POST', url: '/pair/config', headers: { 'x-vb-auth': signAdmin({ token: API, method: 'POST', url: '/pair/config', body: raw, ts, nonce: n }) } }, raw }; };
    const v1 = makeAdminVerifier({ apiToken: API, now: () => now, stateFile: file });
    const captured = mkreq(now + 10, 'nonce-captured-1'); now += 20;
    assert.equal(v1(captured.req, captured.raw).ok, true);
    assert.equal(v1(captured.req, captured.raw).reason, 'replayed request');
    now += 3000; v1.flush();
    // restart: empty nonce cache, later wall clock
    now += 60000;
    const v2 = makeAdminVerifier({ apiToken: API, now: () => now, stateFile: file });
    const rp = v2(captured.req, captured.raw); assert.equal(rp.ok, false); assert.match(rp.reason, /older/);
    const fresh = mkreq(now + 1, 'nonce-fresh-0001'); assert.equal(v2(fresh.req, fresh.raw).ok, true);
    // even without the file the process start time blocks anything signed before it
    const v3 = makeAdminVerifier({ apiToken: API, now: () => now + 100000 });
    assert.equal(v3(fresh.req, fresh.raw).ok, false);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});

test('F9/F13: prevSecret is removed from disk after its grace period; unknown and wrong-secret logins look the same', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vsec3-')), file = path.join(dir, 'p.json');
  try {
    let now = Date.parse('2026-01-01T00:00:00Z');
    const p = new Pairing({ file, now: () => now }); const secret = X.randomBytes(32);
    p.data.devices.push({ id: 'd_1', name: 'x', secret: X.b64u(secret), createdAt: new Date(now).toISOString(), rotateRequested: true });
    const cn = 'c'.repeat(22), rn = 'r'.repeat(22);
    const a = p.authenticate('d_1', cn, rn, X.clientMac(secret, 'd_1', cn, rn), '10.0.0.2'); assert.ok(a.ok && a.rotate);
    assert.ok(JSON.parse(fs.readFileSync(file, 'utf8')).devices[0].prevSecret, 'present during the grace period');
    now += 6 * 60000; p.list();
    const onDisk = JSON.parse(fs.readFileSync(file, 'utf8')).devices[0]; assert.equal(onDisk.prevSecret, undefined); assert.equal(onDisk.prevUntil, undefined);
    const u = p.authenticate('d_nope', cn, rn, 'x', '10.0.0.3'), w = p.authenticate('d_1', cn, rn, 'wrong', '10.0.0.4');
    assert.equal(u.reason, w.reason);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
