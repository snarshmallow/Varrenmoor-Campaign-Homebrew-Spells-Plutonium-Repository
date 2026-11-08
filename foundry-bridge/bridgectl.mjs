// Start / stop / restart / status / info / logs for the managed Varrenmoor relay. No cmd window involved.
//   node bridgectl.mjs <start|stop|restart|status|info|logs> [--env F] [--state D] [--node EXE] [--lines N] [--cim] [--json] [--secrets]
// How it stays alive: the relay runs as `node daemon.mjs`, spawned detached with no console (windowsHide) and its stdio
// closed, so it does not depend on the launching shell, a cmd window, or a console's selection mode. It writes its own log file
// (<state>/relay.log) and PID file (<state>/relay.pid.json). `--cim` starts it through WMI instead (Win32_Process.Create), which also
// escapes a parent's Windows Job Object (use it if a host such as a CEP panel kills its children on exit).
// Tokens are only ever printed by `info --secrets` (used by the Illustrator panel; kept in memory there).
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { root, loadEnv, bindFor, lanIp, paths } from './lib/config.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const win = process.platform === 'win32';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export function makeCtl({ envFile = path.join(root, '.env'), stateDir, node = process.execPath, cim = false } = {}) {
  envFile = path.resolve(envFile);
  const P = paths(stateDir ? path.resolve(stateDir) : undefined);

  const readPid = () => { try { return JSON.parse(fs.readFileSync(P.pid, 'utf8')); } catch { return null; } };
  const alive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; } };
  const isNode = (pid) => {
    if (!win) return alive(pid);
    try { return /node(\.exe)?/i.test(execFileSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], { encoding: 'utf8', windowsHide: true })); } catch { return false; }
  };
  const health = (port, host = '127.0.0.1') => new Promise((res) => {
    const req = http.get({ host, port, path: '/health', timeout: 1500 }, (r) => {
      let b = ''; r.on('data', (c) => b += c);
      r.on('end', () => { try { res(JSON.parse(b)); } catch { res(null); } });
    });
    req.on('error', () => res(null)); req.on('timeout', () => { req.destroy(); res(null); });
  });
  // pid listening on a TCP port (Windows netstat); used to stop a relay that was started by start.bat and has no PID file
  const listenerPid = (port) => {
    if (!win) return null;
    try {
      const t = execFileSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8', windowsHide: true });
      for (const l of t.split(/\r?\n/)) {
        const m = l.trim().match(/^TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)$/i);
        if (m && Number(m[1]) === port) return Number(m[2]);
      }
    } catch { /* none */ }
    return null;
  };
  const envPort = () => Number(loadEnv(envFile).PORT) || 3030;

  async function status() {
    const rec = readPid();
    const port = rec?.port || envPort();
    const h = await health(port);
    const pidAlive = !!(rec && alive(rec.pid) && isNode(rec.pid));
    const managed = !!(rec && h && h.pid === rec.pid);
    const running = !!h;
    const unmanaged = running && !managed;
    return {
      running, managed, unmanaged, stalePidFile: !!rec && !pidAlive, pid: managed ? rec.pid : (h?.pid ?? listenerPid(port) ?? null), pidAlive,
      port, bind: rec?.bind || bindFor(loadEnv(envFile)), startedAt: h?.startedAt || rec?.startedAt || null,
      moduleConnected: !!h?.moduleConnected, replacedLastMinute: h?.replacedLastMinute ?? 0, logFile: P.log, pidFile: P.pid, envFile,
    };
  }

  function rotateLog() {
    try { if (fs.statSync(P.log).size > 2 * 1024 * 1024) fs.renameSync(P.log, P.log + '.1'); } catch { /* no log yet */ }
  }

  async function waitHealthy(port, pid, ms) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const h = await health(port);
      if (h && (h.pid === pid || !pid)) return h;
      if (pid && !alive(pid)) return null;
      await sleep(150);
    }
    return null;
  }

  async function start() {
    const s = await status();
    if (s.managed) return { action: 'already-running', ...s };
    if (s.unmanaged) throw new Error(`a relay not started by this launcher is already listening on port ${s.port}${s.pid ? ` (pid ${s.pid})` : ''}. Use restart to replace it.`);
    if (s.stalePidFile) { try { fs.unlinkSync(P.pid); } catch { /* ok */ } }
    const env = loadEnv(envFile, { create: true });   // creates tokens only when missing
    const port = Number(env.PORT) || 3030;
    fs.mkdirSync(P.dir, { recursive: true });
    rotateLog();
    const dargs = [path.join(here, 'daemon.mjs'), '--env', envFile, '--state', P.dir];
    let pid = 0;
    if (cim && win) {
      const q = (x) => `"${x}"`;
      const cmdline = [q(node), ...dargs.map(q)].join(' ');
      const ps = `$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='${cmdline.replace(/'/g, "''")}'; CurrentDirectory='${here.replace(/'/g, "''")}'}; if ($r.ReturnValue -ne 0) { exit 1 }; $r.ProcessId`;
      const o = execFileSync('powershell', ['-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps], { encoding: 'utf8', windowsHide: true });
      pid = Number(String(o).trim().split(/\s+/).pop()) || 0;
    } else {
      const child = spawn(node, dargs, { cwd: here, detached: true, stdio: 'ignore', windowsHide: true });
      child.on('error', () => {});
      pid = child.pid; child.unref();
    }
    const h = await waitHealthy(port, pid, 12000);
    if (!h) {
      const tail = (await logTail(8)).join(' | ');
      throw new Error(`relay did not come up on port ${port}${tail ? `: ${tail}` : ''}`);
    }
    return { action: 'started', ...(await status()) };
  }

  async function stop() {
    const s = await status();
    const rec = readPid();
    const target = s.managed ? rec.pid : (s.running ? (s.pid || listenerPid(s.port)) : null);
    if (!target) {
      if (rec) { try { fs.unlinkSync(P.pid); } catch { /* ok */ } }
      return { action: 'not-running', ...(await status()) };
    }
    if (!isNode(target)) throw new Error(`pid ${target} on port ${s.port} is not a node process; refusing to kill it`);
    try { process.kill(target); } catch (e) { if (e.code !== 'ESRCH') throw e; }
    const end = Date.now() + 8000;
    while (Date.now() < end && (alive(target) || await health(s.port))) await sleep(150);
    if (alive(target)) throw new Error(`pid ${target} did not exit`);
    try { fs.unlinkSync(P.pid); } catch { /* already removed */ }
    return { action: 'stopped', pid: target, wasManaged: s.managed, ...(await status()) };
  }

  async function restart() {
    const was = await stop();
    const s = await start();
    return { ...s, action: 'restarted', previous: was.action };
  }

  async function logTail(n = 20) {
    try {
      const fd = fs.openSync(P.log, 'r'); const size = fs.fstatSync(fd).size; const len = Math.min(size, 64 * 1024);
      const buf = Buffer.alloc(len); fs.readSync(fd, buf, 0, len, size - len); fs.closeSync(fd);
      return buf.toString('utf8').split(/\r?\n/).filter(Boolean).slice(-n);
    } catch { return []; }
  }

  // Everything the GM module needs. Tokens only when `secrets` is true.
  async function info({ secrets = false } = {}) {
    const s = await status(); const env = loadEnv(envFile);
    const lan = s.bind === '0.0.0.0' ? lanIp() : null;
    const localhost = `ws://127.0.0.1:${s.port}/module`, lanUrl = lan ? `ws://${lan}:${s.port}/module` : null;
    const out = {
      status: s, listenMode: s.bind === '0.0.0.0' ? 'LAN (all interfaces)' : 'localhost only',
      urls: { localhost, lan: lanUrl, http: `http://127.0.0.1:${s.port}`, health: `http://127.0.0.1:${s.port}/health` },
      moduleSettings: {
        'Connect to relay': 'ON', 'Use launcher relay URL': 'OFF (that file lives on the Foundry server PC)',
        'Relay URL': lanUrl || localhost, 'Module token': secrets ? env.BRIDGE_MODULE_TOKEN || '' : '(masked)', 'Allow writes': 'OFF until you push',
      },
      note: s.bind === '0.0.0.0' ? 'A GM page served from http://VEGA:30000 cannot open ws://127.0.0.1, so use the LAN URL in the module settings.' : 'Loopback only: the Foundry GM browser must run on this PC and the page must be opened from localhost.',
      logTail: await logTail(20),
    };
    if (secrets) out.secrets = { moduleToken: env.BRIDGE_MODULE_TOKEN || '', apiToken: env.BRIDGE_API_TOKEN || '' };
    return out;
  }

  return { status, start, stop, restart, info, logTail, paths: P };
}

// ---- CLI ---------------------------------------------------------------------------------------------------------------
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const a = process.argv.slice(2), cmd = a[0];
  const opt = (n, d) => { const i = a.indexOf(n); return i > 0 && a[i + 1] ? a[i + 1] : d; };
  const json = a.includes('--json');
  const ctl = makeCtl({ envFile: opt('--env', path.join(root, '.env')), stateDir: opt('--state'), node: opt('--node', process.execPath), cim: a.includes('--cim') });
  try {
    let r;
    if (cmd === 'start') r = await ctl.start();
    else if (cmd === 'stop') r = await ctl.stop();
    else if (cmd === 'restart') r = await ctl.restart();
    else if (cmd === 'status') r = await ctl.status();
    else if (cmd === 'info') r = await ctl.info({ secrets: a.includes('--secrets') });
    else if (cmd === 'logs') r = { lines: await ctl.logTail(Number(opt('--lines', 40))) };
    else { console.error('usage: node bridgectl.mjs <start|stop|restart|status|info|logs> [--env F] [--state D] [--node EXE] [--cim] [--json] [--secrets]'); process.exit(2); }
    if (json) console.log(JSON.stringify(r));
    else if (r.lines) console.log(r.lines.join('\n'));
    else if (cmd === 'info') console.log(JSON.stringify(r, null, 2));
    else console.log(`${r.action || (r.running ? 'running' : 'not running')}: ${r.running ? `healthy on port ${r.port}, pid ${r.pid ?? '?'}, ${r.managed ? 'managed' : r.unmanaged ? 'UNMANAGED (started elsewhere)' : ''}, module ${r.moduleConnected ? 'connected' : 'not connected'}` : 'relay not running'}`);
  } catch (e) {
    if (json) console.log(JSON.stringify({ error: String(e.message || e) })); else console.error('ERROR:', e.message || e);
    process.exit(1);
  }
}
