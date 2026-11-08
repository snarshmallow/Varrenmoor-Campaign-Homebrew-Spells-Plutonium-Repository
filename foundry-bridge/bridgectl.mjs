// Start / stop / restart / status / probe / info / logs for the Varrenmoor relay: launches it (visible window by default, hidden optional) OR attaches to one
// that is already running, without restarting it.
//   node bridgectl.mjs <start|stop|restart|status|local|closelocal|probe|info|logs> [--env F] [--state D] [--node EXE] [--lines N] [--json] [--secrets]
//        [--target host[:port]|URL]  attach/inspect a relay at that address (default: this PC, port from .env)
//        local / closelocal: find / stop ONLY a relay on this PC (node.exe only; --target is ignored)
//        [--hidden]                  no window at all (detached node, no console)         [--terminal auto|wt|conhost]
//        [--cim]                     (hidden mode) start through WMI to escape a host's Job Object
// Modes: window (default) = a visible console that does not freeze: Windows Terminal if installed, else a conhost window with QuickEdit OFF
// (relay-window.ps1), logs scroll live and are also written to run/relay.log. hidden = `node daemon.mjs` detached with no console.
// Window launches always go through WMI (Win32_Process.Create): the new process is parented to the WMI service, not to us, so it is outside
// the caller's process tree and Job Object and survives the caller (Illustrator) exiting. Tokens are only ever printed by `info --secrets`.
import fs from 'node:fs';
import os from 'node:os';
import http from 'node:http';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { root, loadEnv, bindFor, lanIp, paths } from './lib/config.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const win = process.platform === 'win32';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const WINDOW_TITLE = 'Varrenmoor Bridge relay (close = stop relay)';

// "", "host", "host:port", "http://host:port", "ws://host:port/module" -> { host, port|null }
export function parseTarget(s) {
  s = String(s || '').trim();
  if (!s) return { host: '', port: null };
  const m = s.replace(/^[a-z]+:\/\//i, '').split('/')[0].match(/^(\[[^\]]+\]|[^:]+)(?::(\d+))?$/);
  if (!m) return { host: '', port: null };
  return { host: m[1].replace(/^\[|\]$/g, ''), port: m[2] ? Number(m[2]) : null };
}
export function isLocalHost(host) {
  if (!host) return true;
  const h = host.toLowerCase();
  if (h === 'localhost' || h === '::1' || /^127\./.test(h) || h === os.hostname().toLowerCase()) return true;
  return Object.values(os.networkInterfaces()).flat().some((a) => a && a.address === h);
}
// where is Windows Terminal? (not installed on every PC)
export function findWt() {
  if (!win) return null;
  const c = [path.join(process.env.LOCALAPPDATA || '', 'Microsoft', 'WindowsApps', 'wt.exe')];
  for (const d of String(process.env.PATH || '').split(path.delimiter)) if (d) c.push(path.join(d, 'wt.exe'));
  return c.find((f) => { try { return fs.statSync(f).size >= 0; } catch { return false; } }) || null;
}
// the command line the window runs (exported for tests): wrapper script + relay args
export function windowArgs({ node, envFile, stateDir, mode }) {
  return ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', path.join(here, 'relay-window.ps1'), '-Node', node, '-Daemon', path.join(here, 'daemon.mjs'), '-EnvFile', envFile, '-State', stateDir, '-Title', WINDOW_TITLE, '-Mode', mode];
}
export function wtArgs(psArgs) { return ['-w', 'new', '--title', WINDOW_TITLE, '--suppressApplicationTitle', 'powershell.exe', ...psArgs]; }

// image name of a pid (Windows tasklist); null when the pid does not exist
export function imageName(pid) {
  if (!win) { try { return fs.readFileSync(`/proc/${pid}/comm`, 'utf8').trim(); } catch { return null; } }
  try {
    const l = execFileSync('tasklist', ['/FI', `PID eq ${pid}`, '/FO', 'CSV', '/NH'], { encoding: 'utf8', windowsHide: true }).trim().split(/\r?\n/)[0];
    const m = l.match(/^"([^"]+)","(\d+)"/);
    return m && Number(m[2]) === Number(pid) ? m[1] : null;
  } catch { return null; }
}
// the only thing this launcher may ever kill is a node process
export const isNodeName = (n) => /^node(\.exe)?$/i.test(String(n || ''));

export function makeCtl({ envFile = path.join(root, '.env'), stateDir, node = process.execPath, cim = false, hidden = false, terminal = 'auto', target = '', procName = imageName } = {}) {
  envFile = path.resolve(envFile);
  const P = paths(stateDir ? path.resolve(stateDir) : undefined);
  const T = typeof target === 'string' ? parseTarget(target) : target;
  const remote = !!T.host && !isLocalHost(T.host);

  const readPid = () => { try { return JSON.parse(fs.readFileSync(P.pid, 'utf8')); } catch { return null; } };
  const alive = (pid) => { try { process.kill(pid, 0); return true; } catch (e) { return e.code === 'EPERM'; } };
  const isNode = (pid) => isNodeName(procName(pid));
  // GET /health; only a Varrenmoor relay counts (ok:true), so some other web server on the port is not mistaken for one
  const health = (port, host = '127.0.0.1') => new Promise((res) => {
    const req = http.get({ host, port, path: '/health', timeout: 1500 }, (r) => {
      let b = ''; r.on('data', (c) => b += c);
      r.on('end', () => { try { const j = JSON.parse(b); res(j && j.ok === true ? j : null); } catch { res(null); } });
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
    if (remote) {   // a relay on another PC: we can only look at it
      const port = T.port || envPort(), h = await health(port, T.host);
      return { running: !!h, managed: false, unmanaged: !!h, attached: !!h, remote: true, host: T.host, mode: h ? 'attached (remote)' : 'stopped', pid: h?.pid ?? null, port, bind: null, startedAt: h?.startedAt || null,
        moduleConnected: !!h?.moduleConnected, replacedLastMinute: h?.replacedLastMinute ?? 0, pairing: h?.pairing || null, logFile: null, pidFile: null, envFile };
    }
    const rec = readPid();
    const port = T.port || rec?.port || envPort();
    const h = await health(port);
    const pidAlive = !!(rec && alive(rec.pid) && isNode(rec.pid));
    const managed = !!(rec && h && h.pid === rec.pid);
    const running = !!h;
    const unmanaged = running && !managed;
    return {
      running, managed, unmanaged, attached: unmanaged, remote: false, host: '127.0.0.1', mode: !running ? 'stopped' : managed ? `managed (${rec.mode || 'hidden'})` : 'attached (unmanaged)', terminal: managed ? rec.mode || 'hidden' : null,
      stalePidFile: !!rec && !pidAlive, pid: managed ? rec.pid : (h?.pid ?? listenerPid(port) ?? null), pidAlive,
      port, bind: rec?.bind || bindFor(loadEnv(envFile)), startedAt: h?.startedAt || rec?.startedAt || null,
      moduleConnected: !!h?.moduleConnected, replacedLastMinute: h?.replacedLastMinute ?? 0, pairing: h?.pairing || null, logFile: P.log, pidFile: P.pid, envFile,
    };
  }

  // Look for relays: this PC (loopback + LAN address, port from .env) plus any extra host[:port] candidates. Read-only.
  async function probe(extra = []) {
    const port = envPort(), c = [];
    const add = (host, p) => { if (host && !c.some((x) => x.host === host && x.port === p)) c.push({ host, port: p }); };
    add('127.0.0.1', T.port || port);
    const lan = lanIp(); if (lan) add(lan, T.port || port);
    for (const e of extra) { const t = parseTarget(e); add(t.host, t.port || port); }
    if (T.host) add(T.host, T.port || port);
    return Promise.all(c.map(async (x) => { const h = await health(x.port, x.host); return { host: x.host, port: x.port, running: !!h, local: isLocalHost(x.host), moduleConnected: !!h?.moduleConnected, pid: h?.pid ?? null, pairing: h?.pairing || null }; }));
  }

  function rotateLog() {
    try { if (fs.statSync(P.log).size > 2 * 1024 * 1024) fs.renameSync(P.log, P.log + '.1'); } catch { /* no log yet */ }
  }

  // wait until a healthy relay is listening AND the PID file (written by the daemon itself) belongs to a live process
  async function waitHealthy(port, ms, pid) {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      const h = await health(port);
      const rec = readPid();
      if (h && rec && h.pid === rec.pid && (!pid || h.pid === pid)) return h;
      if (pid && !alive(pid)) return null;
      await sleep(150);
    }
    return null;
  }

  const q = (x) => `"${x}"`;
  // Win32_Process.Create via PowerShell/CIM: the new process is a child of the WMI service, so it is outside our process tree and any Job Object.
  function cimCreate(cmdline, { show = false, title = '' } = {}) {
    const esc = (x) => x.replace(/'/g, "''");
    const ps = `$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]${show ? 1 : 0}; Title='${esc(title)}'}; ` +
      `$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{CommandLine='${esc(cmdline)}'; CurrentDirectory='${esc(here)}'; ProcessStartupInformation=$si}; if ($r.ReturnValue -ne 0) { exit 1 }; $r.ProcessId`;
    const o = execFileSync('powershell', ['-NoProfile', '-WindowStyle', 'Hidden', '-Command', ps], { encoding: 'utf8', windowsHide: true });
    return Number(String(o).trim().split(/\s+/).pop()) || 0;
  }

  async function start() {
    if (remote) throw new Error(`cannot start a relay on another PC (${T.host}); attach to it instead`);
    const s = await status();
    if (s.managed) return { action: 'already-running', ...s };
    if (s.unmanaged) return { action: 'attached', ...s };      // something healthy is already there: attach, never restart it
    if (s.stalePidFile) { try { fs.unlinkSync(P.pid); } catch { /* ok */ } }
    const env = loadEnv(envFile, { create: true });   // creates tokens only when missing
    const port = Number(env.PORT) || 3030;
    fs.mkdirSync(P.dir, { recursive: true });
    rotateLog();
    try { fs.unlinkSync(P.stop); } catch { /* none */ }
    const hiddenMode = hidden || !win;
    let how = hiddenMode ? 'hidden' : null;
    if (hiddenMode) {
      const dargs = [path.join(here, 'daemon.mjs'), '--env', envFile, '--state', P.dir, '--mode', 'hidden'];
      let pid = 0;
      if (win) pid = cimCreate([q(node), ...dargs.map(q)].join(' '));
      else { const child = spawn(node, dargs, { cwd: here, detached: true, stdio: 'ignore', windowsHide: true }); child.on('error', () => {}); pid = child.pid; child.unref(); }
      if (!(await waitHealthy(port, 12000, pid))) throw new Error(`relay did not come up on port ${port}: ${(await logTail(8)).join(' | ')}`);
    } else {
      const wt = terminal === 'conhost' ? null : findWt();
      const tries = [];
      if (wt) tries.push('wt');
      if (terminal !== 'wt' || !wt) tries.push('window');
      for (const t of tries) {
        const psArgs = windowArgs({ node, envFile, stateDir: P.dir, mode: t });
        const cmdline = t === 'wt' ? [q(wt), ...wtArgs(psArgs).map(q)].join(' ') : [q('powershell.exe'), ...psArgs.map(q)].join(' ');
        cimCreate(cmdline, { show: true, title: WINDOW_TITLE });
        if (await waitHealthy(port, t === 'wt' ? 10000 : 15000)) { how = t; break; }
      }
      if (!how) throw new Error(`the relay window did not come up on port ${port}: ${(await logTail(8)).join(' | ')}`);
    }
    return { action: 'started', how, ...(await status()) };
  }

  // Is a relay running on THIS PC? Looks at the PID file, the listening sockets (netstat) and /health on localhost for the configured port, the
  // port in the PID file, 3030 and any local --target port. Ignores a remote --target completely: this never looks at or touches another PC.
  async function localStatus() {
    const rec = readPid(), ports = [];
    for (const p of [rec?.port, envPort(), 3030, (!remote && T.port) || null]) if (p && !ports.includes(p)) ports.push(p);
    const hits = [];
    for (const port of ports) {
      const h = await health(port);
      const lp = listenerPid(port);
      if (h || lp) hits.push({ port, health: h, listenerPid: lp });
    }
    const hit = hits.find((x) => x.health) || null;
    const managed = !!(rec && hit && hit.health.pid === rec.pid);
    const pid = hit ? (hit.health.pid ?? hit.listenerPid ?? null) : (rec && alive(rec.pid) && isNode(rec.pid) ? rec.pid : null);
    const name = pid ? procName(pid) : null;
    const found = !!hit || !!(rec && pid);
    const how = !found ? null : managed ? (rec.mode === 'hidden' ? 'managed, hidden (no window)' : `managed, ${rec.mode === 'wt' ? 'Windows Terminal window' : 'console window'}`) : 'not started from the panel (start.bat or by hand)';
    return {
      found, running: !!hit, port: hit ? hit.port : (rec?.port ?? null), pid, imageName: name, isNode: isNodeName(name), managed, unmanaged: !!hit && !managed,
      mode: !found ? null : managed ? (rec.mode || 'hidden') : 'unmanaged', how, moduleConnected: !!hit?.health?.moduleConnected, startedAt: hit?.health?.startedAt || rec?.startedAt || null,
      stalePidFile: !!rec && !(alive(rec.pid) && isNode(rec.pid)), otherListeners: hits.filter((x) => !x.health && x.listenerPid).map((x) => ({ port: x.port, pid: x.listenerPid, imageName: procName(x.listenerPid) })), pidFile: P.pid, checkedPorts: ports,
    };
  }

  // Stops ONLY the relay on this PC, and only when the process is node. Never looks at --target, so it can never touch another PC.
  async function closeLocal() {
    const s = await localStatus();
    if (!s.found || !s.pid) {
      try { if (s.stalePidFile) fs.unlinkSync(P.pid); } catch { /* ok */ }
      return { action: 'not-running', local: s };
    }
    if (!isNodeName(s.imageName)) throw new Error(`pid ${s.pid} on port ${s.port} is ${s.imageName || 'not a known process'}, not node.exe; refusing to kill it`);
    try { fs.mkdirSync(P.dir, { recursive: true }); fs.writeFileSync(P.stop, String(Date.now())); } catch { /* the window then waits for a key; harmless */ }
    try { process.kill(s.pid); } catch (e) { if (e.code !== 'ESRCH') throw e; }
    const end = Date.now() + 8000;
    while (Date.now() < end && (alive(s.pid) || await health(s.port))) await sleep(150);
    if (alive(s.pid)) throw new Error(`pid ${s.pid} did not exit`);
    try { fs.unlinkSync(P.pid); } catch { /* already removed */ }
    return { action: 'stopped', pid: s.pid, wasManaged: s.managed, local: await localStatus() };
  }

  async function stop() {
    if (remote) throw new Error(`cannot stop a relay on another PC (${T.host})`);
    const s = await status();
    const rec = readPid();
    const target = s.managed ? rec.pid : (s.running ? (s.pid || listenerPid(s.port)) : null);
    if (!target) {
      if (rec) { try { fs.unlinkSync(P.pid); } catch { /* ok */ } }
      return { action: 'not-running', ...(await status()) };
    }
    if (!isNode(target)) throw new Error(`pid ${target} on port ${s.port} is not a node process; refusing to kill it`);
    try { fs.mkdirSync(P.dir, { recursive: true }); fs.writeFileSync(P.stop, String(Date.now())); } catch { /* the window then waits for a key; harmless */ }
    try { process.kill(target); } catch (e) { if (e.code !== 'ESRCH') throw e; }
    const end = Date.now() + 8000;
    while (Date.now() < end && (alive(target) || await health(s.port))) await sleep(150);
    if (alive(target)) throw new Error(`pid ${target} did not exit`);
    try { fs.unlinkSync(P.pid); } catch { /* already removed */ }
    return { action: 'stopped', pid: target, wasManaged: s.managed, ...(await status()) };
  }

  async function restart() {
    const was = await stop();
    await sleep(600);   // let a closing relay window finish before the next one opens
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

  // Everything the GM module needs. Tokens only when `secrets` is true AND the relay is on this PC (its .env is the source; for a relay on another PC the
  // panel asks for a manually entered token, kept in memory only).
  async function info({ secrets = false } = {}) {
    const s = await status(); const env = remote ? {} : loadEnv(envFile);
    const lan = remote ? T.host : (s.bind === '0.0.0.0' ? lanIp() : null);
    const localhost = remote ? null : `ws://127.0.0.1:${s.port}/module`, lanUrl = lan ? `ws://${lan}:${s.port}/module` : null;
    const listenMode = remote ? `relay on another PC (${T.host})` : (s.bind === '0.0.0.0' ? 'LAN (all interfaces)' : 'localhost only');
    const out = {
      status: s, listenMode,
      urls: { localhost, lan: lanUrl, http: `http://${remote ? T.host : '127.0.0.1'}:${s.port}`, health: `http://${remote ? T.host : '127.0.0.1'}:${s.port}/health` },
      moduleSettings: {
        'Connect to relay': 'ON', 'Use launcher relay URL': 'OFF (that file lives on the Foundry server PC)',
        'Relay URL': lanUrl || localhost, 'Module token': secrets ? env.BRIDGE_MODULE_TOKEN || '' : '(masked)', 'Allow writes': 'OFF until you push',
      },
      note: remote ? 'This relay runs on another PC: its tokens are not on this PC. Type them in manually (kept in memory only), or pair the Foundry module (no token needed).'
        : s.bind === '0.0.0.0' ? 'A GM page served from http://<foundry-pc>:30000 cannot open ws://127.0.0.1, so use the LAN URL in the module settings.' : 'Loopback only: the Foundry GM browser must run on this PC and the page must be opened from localhost.',
      logTail: await logTail(20),
    };
    if (secrets && !remote) out.secrets = { moduleToken: env.BRIDGE_MODULE_TOKEN || '', apiToken: env.BRIDGE_API_TOKEN || '' };
    return out;
  }

  return { status, localStatus, closeLocal, probe, start, stop, restart, info, logTail, paths: P };
}

// ---- CLI ---------------------------------------------------------------------------------------------------------------
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const a = process.argv.slice(2), cmd = a[0];
  const opt = (n, d) => { const i = a.indexOf(n); return i > 0 && a[i + 1] ? a[i + 1] : d; };
  const json = a.includes('--json');
  const ctl = makeCtl({ envFile: opt('--env', path.join(root, '.env')), stateDir: opt('--state'), node: opt('--node', process.execPath), cim: a.includes('--cim'), hidden: a.includes('--hidden'), terminal: opt('--terminal', 'auto'), target: opt('--target', '') });
  try {
    let r;
    if (cmd === 'start') r = await ctl.start();
    else if (cmd === 'stop') r = await ctl.stop();
    else if (cmd === 'restart') r = await ctl.restart();
    else if (cmd === 'status') r = await ctl.status();
    else if (cmd === 'local') r = await ctl.localStatus();
    else if (cmd === 'closelocal') r = await ctl.closeLocal();
    else if (cmd === 'probe') r = { found: await ctl.probe(a.filter((x, i) => a[i - 1] === '--also')) };
    else if (cmd === 'info') r = await ctl.info({ secrets: a.includes('--secrets') });
    else if (cmd === 'logs') r = { lines: await ctl.logTail(Number(opt('--lines', 40))) };
    else { console.error('usage: node bridgectl.mjs <start|stop|restart|status|local|closelocal|probe|info|logs> [--env F] [--state D] [--node EXE] [--target host[:port]] [--hidden] [--terminal auto|wt|conhost] [--cim] [--json] [--secrets]'); process.exit(2); }
    if (json) console.log(JSON.stringify(r));
    else if (r.lines) console.log(r.lines.join('\n'));
    else if (r.found) console.log(r.found.map((x) => `${x.host}:${x.port} ${x.running ? 'RELAY RUNNING' : 'nothing'}`).join('\n'));
    else if (cmd === 'info') console.log(JSON.stringify(r, null, 2));
    else if (cmd === 'local' || cmd === 'closelocal') console.log(r.action ? r.action : r.found ? `local relay: pid ${r.pid} (${r.imageName}), port ${r.port}, ${r.how}` : 'No local bridge running');
    else console.log(`${r.action || (r.running ? 'running' : 'not running')}: ${r.running ? `healthy on ${r.host}:${r.port}, pid ${r.pid ?? '?'}, ${r.mode}, module ${r.moduleConnected ? 'connected' : 'not connected'}` : 'relay not running'}`);
  } catch (e) {
    if (json) console.log(JSON.stringify({ error: String(e.message || e) })); else console.error('ERROR:', e.message || e);
    process.exit(1);
  }
}
