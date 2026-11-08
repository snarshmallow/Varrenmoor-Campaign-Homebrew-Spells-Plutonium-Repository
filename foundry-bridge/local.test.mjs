// Local-relay detection and "Close bridge": finds only a relay on THIS PC, closes only node.exe, never follows a remote --target.
// Throwaway port / tokens / state dir; never touches the real .env or the real (Vega) relay.
//   node --test foundry-bridge/local.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { makeCtl, isNodeName, imageName } from './bridgectl.mjs';

const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '0.0.0.0', () => s.close(() => res(from))); });
const MOD = 'throwaway-module-token-0123456789', API = 'throwaway-api-token-abcdefghijklm';
const alive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; } };

test('isNodeName accepts only node / node.exe', () => {
  assert.ok(isNodeName('node.exe') && isNodeName('NODE.EXE') && isNodeName('node'));
  for (const n of ['notepad.exe', 'node.exe.bak', 'nodejs.exe', 'chrome.exe', '', null, undefined, 'cmd.exe']) assert.ok(!isNodeName(n), String(n));
});

test('detect, refuse non-node, ignore a remote target, then close only the local node relay', async () => {
  const port = await freePort(8799);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vlocal-'));
  const envFile = path.join(dir, 'e.env');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n`);
  const state = path.join(dir, 'run');
  const real = makeCtl({ envFile, stateDir: state, hidden: true });
  let pid = null;
  try {
    let l = await real.localStatus();
    assert.equal(l.found, false, 'nothing local at first');
    assert.deepEqual((await real.closeLocal()).action, 'not-running');

    const a = await real.start(); pid = a.pid;
    l = await real.localStatus();
    assert.equal(l.found, true);
    assert.equal(l.port, port);
    assert.equal(l.pid, pid);
    assert.equal(l.managed, true);
    assert.match(l.how, /managed, hidden/);
    assert.ok(l.isNode && isNodeName(l.imageName), 'it is a node process: ' + l.imageName);
    assert.ok(!JSON.stringify(l).includes(MOD) && !JSON.stringify(l).includes(API), 'no tokens in the report');

    // a controller that points at a REMOTE relay still reports the local one and closes nothing remote
    const withRemote = makeCtl({ envFile, stateDir: state, hidden: true, target: 'http://10.255.255.1:3030' });
    assert.equal((await withRemote.localStatus()).pid, pid, 'local detection ignores the remote target');

    // guard: a process that is not node.exe is never killed
    const wrong = makeCtl({ envFile, stateDir: state, procName: () => 'notepad.exe' });
    await assert.rejects(() => wrong.closeLocal(), /not node\.exe; refusing to kill it/);
    assert.ok(alive(pid), 'relay still running after the refused close');
    assert.equal((await real.localStatus()).found, true);

    // the real close (through a controller that carries a remote target: still local only)
    const r = await withRemote.closeLocal();
    assert.equal(r.action, 'stopped');
    assert.equal(r.pid, pid);
    assert.equal(r.local.found, false);
    assert.ok(!alive(pid), 'node relay is gone');
    assert.deepEqual((await real.closeLocal()).action, 'not-running');
  } finally {
    try { if (pid && alive(pid)) process.kill(pid); } catch { /* gone */ }
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('imageName reports a live pid and null for a dead one', () => {
  assert.ok(isNodeName(imageName(process.pid)));
  assert.equal(imageName(999999), null);
});
