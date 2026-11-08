// Managed relay process. Started detached and hidden by bridgectl.mjs (never needs a console window).
//   node daemon.mjs --env <env file> --state <dir> [--console] [--mode hidden|window|wt]
// --console (used by the visible relay window): also prints every log line to the console and lets you approve/deny pairing requests with the A / D keys.
// Logs to <state>/relay.log by itself (appendFileSync, so nothing is lost if the process is killed), writes <state>/relay.pid.json,
// serves /health on the relay port. No tunnel: use start.bat for the Cloudflare quick-tunnel mode.
import fs from 'node:fs';
import path from 'node:path';
import util from 'node:util';
import { pathToFileURL } from 'node:url';
import { root, loadEnv, bindFor, paths, lanIp } from './lib/config.mjs';
import { publishClient } from './lib/publish.mjs';

const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const envFile = path.resolve(arg('--env', path.join(root, '.env')));
const P = paths(path.resolve(arg('--state', path.join(root, 'run'))));
fs.mkdirSync(P.dir, { recursive: true });

const CONSOLE = process.argv.includes('--console'), MODE = arg('--mode', CONSOLE ? 'window' : 'hidden');
const realWrite = process.stdout.write.bind(process.stdout);
const out = (...a) => {
  const line = util.format(...a);
  try { fs.appendFileSync(P.log, line + '\n'); } catch { /* disk full etc: nothing sane to do */ }
  if (CONSOLE) { try { realWrite(line + '\n'); } catch { /* console gone */ } }
};
console.log = (...a) => out(...a); console.error = (...a) => out('ERR', ...a); console.warn = (...a) => out('WARN', ...a);
const die = (msg, code = 1) => { out(new Date().toISOString(), 'FATAL', msg); try { if (JSON.parse(fs.readFileSync(P.pid, 'utf8')).pid === process.pid) fs.unlinkSync(P.pid); } catch { /* none */ } process.exit(code); };
process.on('uncaughtException', (e) => die(e?.stack || String(e)));
process.on('unhandledRejection', (e) => die('unhandled rejection: ' + (e?.stack || e)));

try { fs.unlinkSync(P.stop); } catch { /* none */ }
const env = loadEnv(envFile, { create: true });
process.env.BRIDGE_API_TOKEN = env.BRIDGE_API_TOKEN;
process.env.BRIDGE_MODULE_TOKEN = env.BRIDGE_MODULE_TOKEN;
const PORT = Number(env.PORT) || 3030;
const BIND = bindFor(env);

const { createRelay } = await import(pathToFileURL(path.join(root, 'relay', 'server.js')).href);
const pairingOn = (env.BRIDGE_PAIRING || 'on') !== 'off';
const server = createRelay({ pairingFile: pairingOn ? P.paired : null });
await new Promise((res, rej) => { server.once('error', rej); server.listen(PORT, BIND, res); })
  .catch((e) => die(e.code === 'EADDRINUSE' ? `port ${PORT} is already in use (another relay running?)` : String(e)));

fs.writeFileSync(P.pid, JSON.stringify({ pid: process.pid, port: PORT, bind: BIND, mode: MODE, startedAt: new Date().toISOString(), envFile }, null, 1) + '\n');
const published = publishClient({ publicUrl: '', apiToken: env.BRIDGE_API_TOKEN, dir: env.CLIENT_CONFIG_DIR, fallbackDir: root, localUrl: `http://127.0.0.1:${PORT}` });
out(new Date().toISOString(), `Varrenmoor bridge relay (managed) pid ${process.pid} listening on ${BIND}:${PORT}${BIND === '0.0.0.0' ? ` (LAN ${lanIp() || 'unknown'})` : ''}; client.json ${published.ok ? 'written' : 'not written (' + published.reason + ')'}`);

// Pairing prompts. The log always gets the facts (never a token); the visible window also gets a loud banner and A / D keys.
const pairing = server.pairing;
const stamp = () => new Date().toISOString();
if (pairing.enabled) {
  pairing.on('request', (r) => {
    out(stamp(), `PAIRING REQUEST ${r.id}: "${r.name}" from ${r.ip}, origin ${r.origin || '(none)'}, code ${r.code.replace(/(\d{3})(\d{3})/, '$1 $2')}`);
    if (CONSOLE) out(['', '  ============ APPROVE THIS DEVICE? ============',
      `   Device : ${r.name}   (user ${r.userName || '?'}, world ${r.worldId || '?'})`,
      `   From   : ${r.ip}   origin ${r.origin || '(none)'}${r.originMismatch ? '   WARNING: origin does not match what the device claims' : ''}`,
      `   Code   : ${r.code.replace(/(\d{3})(\d{3})/, '$1 $2')}   (it must be the SAME code shown on the Foundry screen)`,
      '   Press  A = approve (90 days)   D = deny      (or use the Illustrator panel)', '  ===============================================', ''].join('\n'));
  });
  for (const ev of ['approved', 'denied', 'revoked', 'expired']) pairing.on(ev, (x) => out(stamp(), `pairing ${ev}: ${x.name || x.id}`));
  if (CONSOLE && process.stdin.isTTY) {
    process.stdin.setRawMode(true); process.stdin.resume();
    process.stdin.on('data', (b) => {
      const k = String(b).toLowerCase();
      if (k === '\u0003') { process.emit('SIGINT'); return; }
      const first = pairing.list().pending[0];
      if ((k === 'a' || k === 'd') && !first) { out(stamp(), 'no pairing request is waiting'); return; }
      if (k === 'a') out(stamp(), pairing.approve(first.id, { days: 90 }).status === 200 ? `approved "${first.name}" (${first.code.replace(/(\d{3})(\d{3})/, '$1 $2')})` : 'approve failed');
      else if (k === 'd') { pairing.deny(first.id); }
      else if (k === 'l') { const l = pairing.list(); out(stamp(), `paired devices: ${l.devices.map((d) => d.name).join(', ') || 'none'}; waiting: ${l.pending.length}`); }
    });
  }
}
out(stamp(), `relay window mode: ${MODE}; pairing ${pairing.enabled ? 'on (paired devices file: ' + P.paired + ')' : 'off'}`);

let stopping = false;
const stop = (sig) => {
  if (stopping) return; stopping = true;
  out(new Date().toISOString(), 'stopping on', sig);
  try { fs.unlinkSync(P.pid); } catch { /* gone */ }
  try { pairing.flush(); } catch { /* ignore */ }
  server.close(); setTimeout(() => process.exit(0), 300).unref();
};
process.on('SIGINT', () => stop('SIGINT')); process.on('SIGTERM', () => stop('SIGTERM')); process.on('SIGBREAK', () => stop('SIGBREAK'));
setInterval(() => out(new Date().toISOString(), 'alive'), 15 * 60 * 1000).unref();
