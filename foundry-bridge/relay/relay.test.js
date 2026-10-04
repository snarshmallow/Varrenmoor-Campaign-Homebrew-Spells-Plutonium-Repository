import test from 'node:test';
import assert from 'node:assert';
import { WebSocket } from 'ws';
import { createRelay } from './server.js';

const API = 'a'.repeat(32), MOD = 'm'.repeat(32);

test('rpc round trip, auth, and disconnect handling', async () => {
  const server = createRelay({ apiToken: API, moduleToken: MOD, timeoutMs: 500 });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  const base = `127.0.0.1:${server.address().port}`;
  const rpc = (op, token = API) => fetch(`http://${base}/rpc`, {
    method: 'POST', headers: { authorization: `Bearer ${token}` }, body: JSON.stringify({ op }),
  });

  assert.equal((await rpc('ping')).status, 503);

  const ws = new WebSocket(`ws://${base}/module`);
  await new Promise((r) => ws.on('open', r));
  ws.send(JSON.stringify({ type: 'hello', token: MOD }));
  await new Promise((r) => ws.once('message', r));
  ws.on('message', (d) => {
    const m = JSON.parse(d);
    ws.send(JSON.stringify({ id: m.id, result: { pong: m.op } }));
  });

  assert.equal((await rpc('ping', 'wrong')).status, 401);
  const ok = await rpc('ping');
  assert.equal(ok.status, 200);
  assert.deepEqual((await ok.json()).result, { pong: 'ping' });

  const bad = new WebSocket(`ws://${base}/module`);
  await new Promise((r) => bad.on('open', r));
  bad.send(JSON.stringify({ type: 'hello', token: API }));
  const code = await new Promise((r) => bad.on('close', r));
  assert.equal(code, 4003);

  ws.close();
  await new Promise((r) => setTimeout(r, 100));
  assert.equal((await rpc('ping')).status, 503);
  server.close();
});
