// Attach mode: the launcher detects a relay it did not start, shows it as attached (unmanaged), never restarts it on start, and can probe addresses.
// Throwaway port 8830+, temp env, throwaway tokens; never the real relay.   node --test foundry-bridge/attach.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { makeCtl, parseTarget, isLocalHost, windowArgs, wtArgs, findWt, WINDOW_TITLE } from './bridgectl.mjs';
import { lanIp } from './lib/config.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '0.0.0.0', () => s.close(() => res(from))); });
const MOD = 'throwaway-module-token-0123456789', API = 'throwaway-api-token-abcdefghijklm';

test('parseTarget / isLocalHost / window command lines', () => {
  assert.deepEqual(parseTarget(''), { host: '', port: null });
  assert.deepEqual(parseTarget('10.0.0.5'), { host: '10.0.0.5', port: null });
  assert.deepEqual(parseTarget('10.0.0.5:3031'), { host: '10.0.0.5', port: 3031 });
  assert.deepEqual(parseTarget('http://vega:3030/health'), { host: 'vega', port: 3030 });
  assert.deepEqual(parseTarget('ws://192.168.1.2:3030/module'), { host: '192.168.1.2', port: 3030 });
  assert.ok(isLocalHost('localhost') && isLocalHost('127.0.0.1') && isLocalHost('') && !isLocalHost('192.0.2.1'));
  const a = windowArgs({ node: 'C:\\n\\node.exe', envFile: 'C:\\e.env', stateDir: 'C:\\run', mode: 'window' });
  assert.ok(a.some((x) => x.endsWith('relay-window.ps1')));
  assert.ok(a.includes(WINDOW_TITLE) && /relay/i.test(WINDOW_TITLE));
  const w = wtArgs(a);
  assert.deepEqual(w.slice(0, 5), ['-w', 'new', '--title', WINDOW_TITLE, '--suppressApplicationTitle']);
  const f = findWt(); assert.ok(f === null || fs.existsSync(f));
});

test('attaches to a relay started elsewhere without restarting it; probe finds it; remote targets are read-only', async () => {
  const port = await freePort(8830);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vattach-'));
  const envFile = path.join(dir, 'e.env');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=0.0.0.0\n`);
  // a relay that this launcher did NOT start (plain child, like an old start.bat relay)
  const child = spawn(process.execPath, [path.join(here, 'relay', 'server.js')], { env: { ...process.env, PORT: String(port), HOST: '0.0.0.0', BRIDGE_API_TOKEN: API, BRIDGE_MODULE_TOKEN: MOD }, stdio: 'ignore', windowsHide: true });
  const ctl = makeCtl({ envFile, stateDir: path.join(dir, 'run'), hidden: true });
  try {
    for (let i = 0; i < 40 && !(await ctl.status()).running; i++) await sleep(150);
    const s = await ctl.status();
    assert.equal(s.running, true); assert.equal(s.managed, false); assert.equal(s.unmanaged, true); assert.equal(s.attached, true);
    assert.equal(s.mode, 'attached (unmanaged)'); assert.equal(s.pid, child.pid);
    const st = await ctl.start();
    assert.equal(st.action, 'attached', 'start must attach, not restart or fail');
    assert.equal((await ctl.status()).pid, child.pid, 'same process: nothing was restarted');
    assert.ok(!fs.existsSync(ctl.paths.pid), 'no PID file is invented for a relay we did not start');
    const i = await ctl.info({ secrets: true });
    assert.equal(i.secrets.moduleToken, MOD, 'tokens come from the local .env for a relay on this PC');
    assert.equal(i.urls.localhost, `ws://127.0.0.1:${port}/module`);
    const found = await ctl.probe();
    assert.ok(found.some((x) => x.host === '127.0.0.1' && x.port === port && x.running), JSON.stringify(found));
    const lan = lanIp();
    if (lan) assert.ok(found.some((x) => x.host === lan && x.running), 'also reachable on the LAN address (bound to 0.0.0.0)');
    // a foreign address is "another PC": nothing secret is returned and start/stop are refused
    const far = makeCtl({ envFile, stateDir: path.join(dir, 'run'), hidden: true, target: '192.0.2.1:' + port });
    await assert.rejects(far.start(), /another PC/); await assert.rejects(far.stop(), /another PC/);
    const fi = await far.info({ secrets: true });
    assert.equal(fi.secrets, undefined, 'no tokens for a relay on another PC'); assert.match(fi.urls.lan, /^ws:\/\/192\.0\.2\.1:/);
    // a foreign web server on the port is not mistaken for a relay
    const dummy = net.createServer((c) => { c.end('HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 2\r\n\r\n{}'); });
    const dport = await freePort(8850); await new Promise((r) => dummy.listen(dport, '127.0.0.1', r));
    assert.equal((await makeCtl({ envFile, stateDir: path.join(dir, 'run2'), target: '127.0.0.1:' + dport, hidden: true }).status()).running, false);
    dummy.close();
    // explicit stop of the attached relay still works (the panel asks for confirmation first)
    const sp = await ctl.stop();
    assert.equal(sp.action, 'stopped'); assert.equal(sp.wasManaged, false);
  } finally { try { child.kill(); } catch { /* gone */ } fs.rmSync(dir, { recursive: true, force: true }); }
});
