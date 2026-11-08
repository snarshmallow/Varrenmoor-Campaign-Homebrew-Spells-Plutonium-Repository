// Managed relay process. Started detached and hidden by bridgectl.mjs (never needs a console window).
//   node daemon.mjs --env <env file> --state <dir>
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

const out = (...a) => { try { fs.appendFileSync(P.log, util.format(...a) + '\n'); } catch { /* disk full etc: nothing sane to do */ } };
console.log = (...a) => out(...a); console.error = (...a) => out('ERR', ...a); console.warn = (...a) => out('WARN', ...a);
const die = (msg, code = 1) => { out(new Date().toISOString(), 'FATAL', msg); try { if (JSON.parse(fs.readFileSync(P.pid, 'utf8')).pid === process.pid) fs.unlinkSync(P.pid); } catch { /* none */ } process.exit(code); };
process.on('uncaughtException', (e) => die(e?.stack || String(e)));
process.on('unhandledRejection', (e) => die('unhandled rejection: ' + (e?.stack || e)));

const env = loadEnv(envFile, { create: true });
process.env.BRIDGE_API_TOKEN = env.BRIDGE_API_TOKEN;
process.env.BRIDGE_MODULE_TOKEN = env.BRIDGE_MODULE_TOKEN;
const PORT = Number(env.PORT) || 3030;
const BIND = bindFor(env);

const { createRelay } = await import(pathToFileURL(path.join(root, 'relay', 'server.js')).href);
const server = createRelay();
await new Promise((res, rej) => { server.once('error', rej); server.listen(PORT, BIND, res); })
  .catch((e) => die(e.code === 'EADDRINUSE' ? `port ${PORT} is already in use (another relay running?)` : String(e)));

fs.writeFileSync(P.pid, JSON.stringify({ pid: process.pid, port: PORT, bind: BIND, startedAt: new Date().toISOString(), envFile }, null, 1) + '\n');
const published = publishClient({ publicUrl: '', apiToken: env.BRIDGE_API_TOKEN, dir: env.CLIENT_CONFIG_DIR, fallbackDir: root, localUrl: `http://127.0.0.1:${PORT}` });
out(new Date().toISOString(), `Varrenmoor bridge relay (managed) pid ${process.pid} listening on ${BIND}:${PORT}${BIND === '0.0.0.0' ? ` (LAN ${lanIp() || 'unknown'})` : ''}; client.json ${published.ok ? 'written' : 'not written (' + published.reason + ')'}`);

let stopping = false;
const stop = (sig) => {
  if (stopping) return; stopping = true;
  out(new Date().toISOString(), 'stopping on', sig);
  try { fs.unlinkSync(P.pid); } catch { /* gone */ }
  server.close(); setTimeout(() => process.exit(0), 300).unref();
};
process.on('SIGINT', () => stop('SIGINT')); process.on('SIGTERM', () => stop('SIGTERM')); process.on('SIGBREAK', () => stop('SIGBREAK'));
setInterval(() => out(new Date().toISOString(), 'alive'), 15 * 60 * 1000).unref();
