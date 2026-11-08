// Launcher test on a throwaway port with a throwaway token in a temp config; never touches the real .env / relay.
//   node --test foundry-bridge/bridgectl.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { createRequire } from 'node:module';
import { makeCtl } from './bridgectl.mjs';

const { WebSocket } = createRequire(import.meta.url)('./relay/node_modules/ws');
const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '0.0.0.0', () => s.close(() => res(from))); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const MOD = 'throwaway-module-token-0123456789', API = 'throwaway-api-token-abcdefghijklm';

test('start / status / second start / info / 4002 / restart / stop on a temp port', async () => {
  const port = await freePort(8799);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vbridge-'));
  const envFile = path.join(dir, 'e.env');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n`);
  const ctl = makeCtl({ envFile, stateDir: path.join(dir, 'run') });
  try {
    let s = await ctl.status();
    assert.equal(s.running, false);

    const a = await ctl.start();
    assert.equal(a.action, 'started');
    assert.equal(a.managed, true);
    assert.equal(a.port, port);
    assert.ok(fs.existsSync(ctl.paths.pid), 'pid file written');
    const rec = JSON.parse(fs.readFileSync(ctl.paths.pid, 'utf8'));
    assert.equal(rec.pid, a.pid);
    assert.ok(fs.readFileSync(ctl.paths.log, 'utf8').includes(`listening on 127.0.0.1:${port}`), 'log written by the daemon');

    const b = await ctl.start();
    assert.equal(b.action, 'already-running');
    assert.equal(b.pid, a.pid);

    const i = await ctl.info();
    assert.equal(i.listenMode, 'localhost only');
    assert.equal(i.urls.localhost, `ws://127.0.0.1:${port}/module`);
    assert.equal(i.moduleSettings['Module token'], '(masked)');
    assert.ok(!JSON.stringify(i).includes(MOD) && !JSON.stringify(i).includes(API), 'no tokens without secrets');
    const sec = await ctl.info({ secrets: true });
    assert.equal(sec.secrets.moduleToken, MOD); assert.equal(sec.secrets.apiToken, API);
    assert.ok(!fs.readFileSync(ctl.paths.log, 'utf8').includes(MOD), 'token never in the log');

    // two module clients: the second evicts the first with 4002, health and log show it
    const connect = async () => {
      const ws = new WebSocket(`ws://127.0.0.1:${port}/module`);
      const closed = new Promise((r) => ws.on('close', (c) => r(c)));
      await new Promise((r) => ws.on('open', r));
      ws.send(JSON.stringify({ type: 'hello', token: MOD }));
      await new Promise((r) => ws.once('message', r));
      return { ws, closed };
    };
    const c1 = await connect(), c2 = await connect();
    assert.equal(await c1.closed, 4002);
    await sleep(100);
    s = await ctl.status();
    assert.equal(s.moduleConnected, true);
    assert.equal(s.replacedLastMinute, 1);
    assert.ok((await ctl.logTail(20)).some((l) => /closed 4002/.test(l)));
    c2.ws.close();

    const r = await ctl.restart();
    assert.equal(r.action, 'restarted');
    assert.notEqual(r.pid, a.pid);
    await sleep(200);
    assert.equal((await ctl.status()).managed, true);

    const st = await ctl.stop();
    assert.equal(st.action, 'stopped');
    s = await ctl.status();
    assert.equal(s.running, false);
    assert.ok(!fs.existsSync(ctl.paths.pid), 'pid file removed');
    assert.equal((await ctl.stop()).action, 'not-running');
  } finally {
    await ctl.stop().catch(() => {});
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('stale pid file is cleaned on start', async () => {
  const port = await freePort(8810);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vbridge-'));
  const envFile = path.join(dir, 'e.env');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n`);
  const ctl = makeCtl({ envFile, stateDir: path.join(dir, 'run') });
  try {
    fs.mkdirSync(ctl.paths.dir, { recursive: true });
    fs.writeFileSync(ctl.paths.pid, JSON.stringify({ pid: 999999, port }));
    assert.equal((await ctl.status()).stalePidFile, true);
    assert.equal((await ctl.start()).action, 'started');
  } finally {
    await ctl.stop().catch(() => {});
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
