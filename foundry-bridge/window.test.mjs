// Visible window mode on a throwaway port: titled window, QuickEdit switched off, logs also in the file, Stop closes the window. Opens a console window for
// a few seconds (or a Windows Terminal window when wt.exe is installed).   node --test foundry-bridge/window.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import net from 'node:net';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { makeCtl, WINDOW_TITLE } from './bridgectl.mjs';

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const freePort = (from) => new Promise((res) => { const s = net.createServer(); s.once('error', () => res(freePort(from + 1))); s.listen(from, '0.0.0.0', () => s.close(() => res(from))); });
const windows = () => {
  try { return execFileSync('powershell', ['-NoProfile', '-Command', "Get-Process | Where-Object { $_.MainWindowTitle -like 'Varrenmoor Bridge relay*' } | ForEach-Object { $_.Id }"], { encoding: 'utf8', windowsHide: true }).trim().split(/\s+/).filter(Boolean); } catch { return []; }
};

test('window mode: visible titled window, QuickEdit off, log file written, Stop closes it', { skip: process.platform !== 'win32' }, async () => {
  const port = await freePort(8840);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vwin-'));
  const envFile = path.join(dir, 'e.env');
  fs.writeFileSync(envFile, `BRIDGE_API_TOKEN=throwaway-api-token-abcdefghijklm\nBRIDGE_MODULE_TOKEN=throwaway-module-token-0123456789\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${dir.split(path.sep).join('/')}/client\n`);
  const ctl = makeCtl({ envFile, stateDir: path.join(dir, 'run') });
  const before = windows().length;
  try {
    const r = await ctl.start();
    assert.equal(r.action, 'started'); assert.match(r.mode, /managed \((window|wt)\)/);
    assert.equal(windows().length, before + 1, 'one new visible window titled "' + WINDOW_TITLE + '"');
    const log = fs.readFileSync(ctl.paths.log, 'utf8');
    if (r.how === 'window') assert.match(log, /console QuickEdit off/, 'QuickEdit disabled in the conhost window');
    assert.ok(log.includes(`listening on 127.0.0.1:${port}`));
    assert.ok(!log.includes('throwaway-module-token') && !log.includes('throwaway-api-token'));
    assert.equal((await ctl.start()).action, 'already-running');
    await ctl.stop(); await sleep(2500);
    assert.equal(windows().length, before, 'the window closes itself after a deliberate Stop');
  } finally { await ctl.stop().catch(() => {}); fs.rmSync(dir, { recursive: true, force: true }); }
});
