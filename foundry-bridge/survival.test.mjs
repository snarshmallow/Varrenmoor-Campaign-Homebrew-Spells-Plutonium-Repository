// Does the relay outlive the process that launched it, even when that process dies inside a Job Object that kills its children (what a CEP panel host
// may do)? Windows only; throwaway port 8799+, temp env, throwaway tokens. A visible relay window opens briefly for the window case.
//   node --test foundry-bridge/survival.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { makeCtl } from './bridgectl.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '0.0.0.0', () => s.close(() => res(from))); });
const win = process.platform === 'win32';

async function scenario(flags, plain = false) {
  const port = await freePort(8820);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vsurv-'));
  const envFile = path.join(dir, 'e.env'), state = path.join(dir, 'run');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=throwaway-api-token-abcdefghijklm\nBRIDGE_MODULE_TOKEN=throwaway-module-token-0123456789\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n`);
  const parent = path.join(dir, 'parent.mjs');   // stands in for the Illustrator panel: launches the relay through bridgectl, then exits
  const plainParent = `import { spawn } from 'node:child_process';
await new Promise(r => setTimeout(r, 1500));
const c = spawn(process.execPath, [${JSON.stringify(path.join(here, 'daemon.mjs'))}, '--env', ${JSON.stringify(envFile)}, '--state', ${JSON.stringify(state)}], { detached: true, stdio: 'ignore', windowsHide: true });
c.unref();
await new Promise(r => setTimeout(r, 1500));
`;
  fs.writeFileSync(parent, plain ? plainParent : `import { execFileSync } from 'node:child_process';\nawait new Promise(r => setTimeout(r, 1500));\nconst o = execFileSync(process.execPath, [${JSON.stringify(path.join(here, 'bridgectl.mjs'))}, 'start', '--json', '--env', ${JSON.stringify(envFile)}, '--state', ${JSON.stringify(state)}, ...${JSON.stringify(flags)}], { encoding: 'utf8', windowsHide: true });\nconsole.log(o.slice(0, 80));\n`);
  const ctl = makeCtl({ envFile, stateDir: state });
  try {
    const out = execFileSync('powershell', ['-NoProfile', '-File', path.join(here, 'survival-job.ps1'), '-Node', process.execPath, '-Script', parent], { encoding: 'utf8', windowsHide: true, timeout: 120000 });
    assert.match(out, /parent-exited 0/, out);
    assert.match(out, /job-closed/);
    await sleep(500);
    return await ctl.status();
  } finally { await ctl.stop().catch(() => {}); await sleep(500); fs.rmSync(dir, { recursive: true, force: true }); }
}

test('visible window mode survives its parent exiting inside a kill-on-close Job Object', { skip: !win }, async () => {
  const s = await scenario([]);
  assert.equal(s.running, true, 'relay must still be running after the parent and its job are gone');
  assert.match(s.mode, /managed \((window|wt)\)/);
});

test('hidden mode with --cim survives the same way', { skip: !win }, async () => {
  const s = await scenario(['--hidden', '--cim']);
  assert.equal(s.running, true);
});

test('control: plain detached spawn inside the job does NOT survive (why WMI is used)', { skip: !win }, async () => {
  const s = await scenario([], true);
  assert.equal(s.running, false, 'if this ever survives, the control is moot but harmless');
});
