// The managed relay (daemon.mjs) keeps running when remote input misbehaves (review F1/F2), refuses pairing when PUBLIC_URL is set (F6), and the ACL helper is best effort (F9).
// Throwaway port 8830+, temp env, throwaway tokens, BRIDGE_HARDEN_ACL=off so no permissions are touched.   node --test foundry-bridge/daemon.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { WebSocket } from './relay/node_modules/ws/wrapper.mjs';
import { hardenAcl } from './lib/config.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '127.0.0.1', () => s.close(() => res(from))); });
const API = 'throwaway-api-token-abcdefghijklm', MOD = 'throwaway-module-token-0123456789';

async function run(extraEnv, fn) {
  const port = await freePort(8830), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vdmn-'));
  const envFile = path.join(dir, 'e.env'), state = path.join(dir, 'run');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n${extraEnv}`);
  const child = spawn(process.execPath, [path.join(here, 'daemon.mjs'), '--env', envFile, '--state', state], { stdio: 'ignore', windowsHide: true, env: { ...process.env, BRIDGE_HARDEN_ACL: 'off' } });
  const health = async () => { try { return await (await fetch(`http://127.0.0.1:${port}/health`)).json(); } catch { return null; } };
  try {
    let h = null; for (let i = 0; i < 50 && !h; i++) { await sleep(150); h = await health(); }
    assert.ok(h && h.ok, 'daemon up');
    await fn({ port, health, h, state, child });
  } finally { child.kill(); await sleep(300); fs.rmSync(dir, { recursive: true, force: true }); }
}

test('daemon survives a null WebSocket frame and an aborted POST (same pid afterwards); log holds no token', async () => {
  await run('', async ({ port, health, h, state }) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}/module`); await new Promise((r) => ws.on('open', r)); ws.send('null'); ws.send('[]'); await sleep(100); ws.close();
    await new Promise((res) => { const s = net.connect(port, '127.0.0.1', () => { s.write('POST /pair/request HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Length: 400\r\n\r\n{"x":'); setTimeout(() => { s.destroy(); res(); }, 50); }); });
    await sleep(200);
    const h2 = await health(); assert.ok(h2 && h2.ok, 'still answering'); assert.equal(h2.pid, h.pid, 'same process: no crash and restart');
    const log = fs.readFileSync(path.join(state, 'relay.log'), 'utf8'); assert.ok(!log.includes(API) && !log.includes(MOD), 'no token in the log'); assert.ok(!/FATAL/.test(log));
  });
});

test('PUBLIC_URL in .env: /discover and /pair/* are refused (fail closed)', async () => {
  await run('PUBLIC_URL=https://example.trycloudflare.com\n', async ({ port }) => {
    assert.equal((await fetch(`http://127.0.0.1:${port}/discover`)).status, 403);
  });
});

test('hardenAcl: only on Windows, restricts to the current user, never throws', () => {
  const calls = [], dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vacl-')), f = path.join(dir, 'x.env'); fs.writeFileSync(f, 'a');
  try {
    assert.deepEqual(hardenAcl([f], { platform: 'linux', exec: () => assert.fail('not on linux') }), []);
    assert.deepEqual(hardenAcl([f], { platform: 'win32', env: { BRIDGE_HARDEN_ACL: 'off' }, exec: () => assert.fail('opted out') }), []);
    const r = hardenAcl([f, dir, path.join(dir, 'missing')], { platform: 'win32', env: { USERDOMAIN: 'PC' }, exec: (c, a) => { calls.push([c, ...a]); } });
    assert.equal(calls.length, 2); assert.equal(calls[0][0], 'icacls'); assert.ok(calls[0].includes('/inheritance:r')); assert.match(calls[0].at(-1), /:F$/); assert.match(calls[1].at(-1), /\(OI\)\(CI\)F$/);
    assert.deepEqual(r.map((x) => x.ok), [true, true, false]);
    const bad = hardenAcl([f], { platform: 'win32', env: { USERDOMAIN: 'PC' }, exec: () => { throw new Error('boom'); } }); assert.equal(bad[0].ok, false);
  } finally { fs.rmSync(dir, { recursive: true, force: true }); }
});
void pathToFileURL;
