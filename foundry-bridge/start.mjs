// One-command launcher: installs deps, creates/loads .env (tokens), starts the relay,
// starts a Cloudflare quick tunnel, self-tests, and prints exactly what to enter where.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import { spawn, spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = path.dirname(fileURLToPath(import.meta.url));
const relayDir = path.join(root, 'relay');
const envFile = path.join(root, '.env');
const win = process.platform === 'win32';

// --- .env ---------------------------------------------------------------
const env = {};
if (fs.existsSync(envFile)) {
  for (const line of fs.readFileSync(envFile, 'utf8').split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);
    if (m) env[m[1]] = m[2];
  }
}
const rand = () => crypto.randomBytes(24).toString('base64url');
env.BRIDGE_API_TOKEN ||= rand();
env.BRIDGE_MODULE_TOKEN ||= rand();
env.PORT ||= '3030';
const save = () => fs.writeFileSync(envFile, Object.entries(env).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join('\n') + '\n', { mode: 0o600 });
save();
const PORT = Number(env.PORT);

// --- deps ---------------------------------------------------------------
if (!fs.existsSync(path.join(relayDir, 'node_modules', 'ws'))) {
  console.log('Installing relay dependencies...');
  const r = spawnSync(win ? 'npm.cmd' : 'npm', ['install', '--omit=dev'], { cwd: relayDir, stdio: 'inherit', shell: win });
  if (r.status !== 0) { console.error('npm install failed'); process.exit(1); }
}

// --- relay (in-process, IPv4 loopback only; the tunnel is the only way in) --
process.env.BRIDGE_API_TOKEN = env.BRIDGE_API_TOKEN;
process.env.BRIDGE_MODULE_TOKEN = env.BRIDGE_MODULE_TOKEN;
const { createRelay } = await import(pathToFileURL(path.join(relayDir, 'server.js')).href);
const server = createRelay();
await new Promise((res, rej) => { server.once('error', rej); server.listen(PORT, '127.0.0.1', res); })
  .catch((e) => { console.error(e.code === 'EADDRINUSE' ? `Port ${PORT} is already in use (an old relay still running? close it, or set PORT in .env).` : e); process.exit(1); });
const health = () => new Promise((res) => {
  http.get({ host: '127.0.0.1', port: PORT, path: '/health' }, (r) => { let b = ''; r.on('data', (c) => b += c); r.on('end', () => res(b)); }).on('error', () => res(null));
});
console.log(`Relay listening on 127.0.0.1:${PORT}  health=${await health()}`);

// --- tunnel -------------------------------------------------------------
let publicUrl = env.PUBLIC_URL || '';
let tunnel = null;
if (!env.PUBLIC_URL) {
  const probe = spawnSync(win ? 'cloudflared.exe' : 'cloudflared', ['--version'], { shell: win });
  if (probe.error || probe.status !== 0) {
    console.log('\ncloudflared not found. Install it (Windows: `winget install Cloudflare.cloudflared`; mac: `brew install cloudflared`; linux: see Cloudflare docs), then re-run.');
    console.log('The relay is still running locally, but Claude cannot reach it without a tunnel.\n');
  } else {
    tunnel = spawn('cloudflared', ['tunnel', '--no-autoupdate', '--url', `http://127.0.0.1:${PORT}`], { shell: win });
    publicUrl = await new Promise((res) => {
      const t = setTimeout(() => res(''), 30000);
      const on = (d) => { const m = d.toString().match(/https:\/\/[a-z0-9-]+\.trycloudflare\.com/); if (m) { clearTimeout(t); res(m[0]); } };
      tunnel.stdout.on('data', on); tunnel.stderr.on('data', on);
    });
  }
}

// --- report ---------------------------------------------------------------
const host = publicUrl ? new URL(publicUrl).host : '(no tunnel)';
if (publicUrl) {
  // quick tunnels can take a few seconds before the edge routes to them
  let ok = false;
  for (let i = 0; i < 10 && !ok; i++) {
    ok = await fetch(`${publicUrl}/health`).then((r) => r.ok).catch(() => false);
    if (!ok) await new Promise((r) => setTimeout(r, 2000));
  }
  console.log(`Tunnel self-test (${publicUrl}/health): ${ok ? 'OK' : 'FAILED - tunnel not routing yet'}`);
}
const line = '='.repeat(70);
console.log(`
${line}
A) FOUNDRY (GM browser tab) -> Game Settings > Manage Modules > Varrenmoor Bridge
   Connect to relay : ON
   Relay URL        : ${publicUrl ? publicUrl.replace('https://', 'wss://') + '/module' : `ws://127.0.0.1:${PORT}/module`}
   Module token     : ${env.BRIDGE_MODULE_TOKEN}
   Allow writes     : OFF (turn on only when you want me to create/update)
   (If Foundry runs on this same PC you may use ws://127.0.0.1:${PORT}/module instead.)

B) CLAUDE ENVIRONMENT (claude.ai/code > environment settings)
   Secret  FOUNDRY_BRIDGE_TOKEN = ${env.BRIDGE_API_TOKEN}
   Secret/var FOUNDRY_BRIDGE_URL = ${publicUrl || '(needs tunnel)'}
   Allowed domain               = ${host}
   (Quick-tunnel hostnames change on every restart; update B each time, or use a named tunnel and set PUBLIC_URL in .env.)

Keys are saved in ${envFile} (git-ignored). Keep this window open. Ctrl+C to stop.
${line}`);

const stop = () => { tunnel?.kill(); server.close(); process.exit(0); };
process.on('SIGINT', stop); process.on('SIGTERM', stop);
setInterval(async () => console.log(new Date().toLocaleTimeString(), 'health', await health()), 60000).unref?.();
