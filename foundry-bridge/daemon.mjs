// Managed relay process. Started detached and hidden by bridgectl.mjs (never needs a console window).
//   node daemon.mjs --env <env file> --state <dir> [--console] [--mode hidden|window|wt]
// --console (used by the visible relay window): also prints every log line to the console and lets you approve/deny pairing requests with the A / D keys.
// Logs to <state>/relay.log by itself (appendFileSync, so nothing is lost if the process is killed), writes <state>/relay.pid.json,
// serves /health on the relay port. No tunnel: use start.bat for the Cloudflare quick-tunnel mode.
import fs from 'node:fs';
import path from 'node:path';
import util from 'node:util';
import { pathToFileURL } from 'node:url';
import { root, loadEnv, bindFor, paths, lanIp, hardenAcl } from './lib/config.mjs';
import { publishClient } from './lib/publish.mjs';
import { attachPairingConsole } from './lib/pairing-console.mjs';

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
// Errors caused by remote input (a malformed frame, an aborted request) must never stop the relay. Before it is listening any error is fatal (bad config, port in use); afterwards it is
// logged (tokens scrubbed) and the process carries on, unless errors keep coming (more than 20 in a minute = something is really wrong: exit so it can be restarted clean).
let listening = false, secretsToScrub = [];
const recent = [];
const scrub = (t) => secretsToScrub.reduce((x, sec) => (sec ? x.split(sec).join('***') : x), String(t));
const survive = (kind, e) => {
  const text = scrub(e?.stack || e);
  if (!listening) return die(kind + ': ' + text);
  const t = Date.now(); recent.push(t); while (recent.length && t - recent[0] > 60000) recent.shift();
  out(new Date().toISOString(), 'ERROR (relay keeps running)', kind + ':', text.split(String.fromCharCode(10)).slice(0, 4).join(' | '));
  if (recent.length > 20) die('too many errors in one minute, exiting');
};
process.on('uncaughtException', (e) => survive('uncaught exception', e));
process.on('unhandledRejection', (e) => survive('unhandled rejection', e));

try { fs.unlinkSync(P.stop); } catch { /* none */ }
const env = loadEnv(envFile, { create: true });
process.env.BRIDGE_API_TOKEN = env.BRIDGE_API_TOKEN;
process.env.BRIDGE_MODULE_TOKEN = env.BRIDGE_MODULE_TOKEN;
secretsToScrub = [env.BRIDGE_API_TOKEN, env.BRIDGE_MODULE_TOKEN];
// Windows ignores file mode 0600: restrict the secret files to this account (best effort; BRIDGE_HARDEN_ACL=off in .env skips it)
const acl = hardenAcl([envFile, P.dir], { env: { ...process.env, BRIDGE_HARDEN_ACL: env.BRIDGE_HARDEN_ACL || process.env.BRIDGE_HARDEN_ACL } });
if (acl.length) out(new Date().toISOString(), 'file permissions:', acl.map((a) => (a.ok ? 'restricted ' : 'not changed (' + a.reason + ') ') + path.basename(a.target)).join(', '));
const PORT = Number(env.PORT) || 3030;
const BIND = bindFor(env);

const { createRelay } = await import(pathToFileURL(path.join(root, 'relay', 'server.js')).href);
const pairingOn = (env.BRIDGE_PAIRING || 'on') !== 'off';
// pairing: on by default (BRIDGE_PAIRING=off in .env starts it switched off); it can be switched on/off live from the Illustrator panel (admin endpoint /pair/config)
// tunnel: this launcher never starts one, but PUBLIC_URL in .env means something public points here: then pairing and admin endpoints stay off (fail closed)
const server = createRelay({ pairingFile: P.paired, pairingEnabled: pairingOn, tunnel: !!env.PUBLIC_URL });
await new Promise((res, rej) => { server.once('error', rej); server.listen(PORT, BIND, res); })
  .catch((e) => die(e.code === 'EADDRINUSE' ? `port ${PORT} is already in use (another relay running?)` : String(e)));

listening = true;
fs.writeFileSync(P.pid, JSON.stringify({ pid: process.pid, port: PORT, bind: BIND, mode: MODE, startedAt: new Date().toISOString(), envFile }, null, 1) + '\n');
const published = publishClient({ publicUrl: '', apiToken: env.BRIDGE_API_TOKEN, dir: env.CLIENT_CONFIG_DIR, fallbackDir: root, localUrl: `http://127.0.0.1:${PORT}` });
out(new Date().toISOString(), `Varrenmoor bridge relay (managed) pid ${process.pid} listening on ${BIND}:${PORT}${BIND === '0.0.0.0' ? ` (LAN ${lanIp() || 'unknown'})` : ''}; client.json ${published.ok ? 'written' : 'not written (' + published.reason + ')'}`);

// Pairing prompts. The log always gets the facts (never a secret); the visible window also gets a loud banner and A / D keys.
const pairing = server.pairing;
const stamp = () => new Date().toISOString();
attachPairingConsole(pairing, out, { interactive: CONSOLE, onSigint: () => process.emit('SIGINT') });
out(stamp(), `relay window mode: ${MODE}; pairing ${pairing.enabled ? 'on' : 'OFF (switch on in the Illustrator panel)'} (paired devices file: ${P.paired})`);

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
