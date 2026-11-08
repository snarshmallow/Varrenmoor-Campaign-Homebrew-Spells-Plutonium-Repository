// Shared config helpers for the managed relay (daemon.mjs, bridgectl.mjs). Never logs token values.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

export function parseEnv(file) {
  const env = {};
  if (fs.existsSync(file)) {
    for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*?)\s*$/);
      if (m) env[m[1]] = m[2];
    }
  }
  return env;
}

export function saveEnv(file, env) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, Object.entries(env).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join('\n') + '\n', { mode: 0o600 });
}

// Loads the env file; when `create` is set, fills in missing tokens/port (existing values are never changed).
export function loadEnv(file, { create = false } = {}) {
  const env = parseEnv(file);
  if (create) {
    const before = JSON.stringify(env);
    const rand = () => crypto.randomBytes(24).toString('base64url');
    env.BRIDGE_API_TOKEN ||= rand();
    env.BRIDGE_MODULE_TOKEN ||= rand();
    env.PORT ||= '3030';
    if (JSON.stringify(env) !== before) saveEnv(file, env);
  }
  return env;
}

// Listen address: BIND_HOST wins; TUNNEL=off ("local mode", GM browser on another machine/LAN) listens on all interfaces; otherwise loopback.
export function bindFor(env) { return env.BIND_HOST || (env.TUNNEL === 'off' ? '0.0.0.0' : '127.0.0.1'); }

export function lanIp() {
  return Object.values(os.networkInterfaces()).flat()
    .find((a) => a && a.family === 'IPv4' && !a.internal && /^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(a.address))?.address || null;
}

export function paths(stateDir = path.join(root, 'run')) {
  return { dir: stateDir, pid: path.join(stateDir, 'relay.pid.json'), log: path.join(stateDir, 'relay.log'), stop: path.join(stateDir, 'relay.stop'), paired: path.join(stateDir, 'paired-devices.json') };
}

// Windows ignores the 0600 file mode, so secret files inherit the folder's ACL (often readable by every local account). Best effort, never throws:
// remove inherited rights and grant only the current user. Folders get (OI)(CI) so files the relay creates later (paired-devices.json.tmp -> renamed) are covered too.
// Not applied to client.json: it is read from other PCs over a share on purpose (see README, "Windows file permissions").
export function hardenAcl(targets, { exec = execFileSync, platform = process.platform, env = process.env } = {}) {
  const res = [];
  if (platform !== 'win32' || env.BRIDGE_HARDEN_ACL === 'off') return res;
  let user = ''; try { user = (env.USERDOMAIN ? env.USERDOMAIN + String.fromCharCode(92) : '') + os.userInfo().username; } catch { /* unknown */ }
  if (!user) return res;
  for (const t of targets) {
    try {
      if (!fs.existsSync(t)) { res.push({ target: t, ok: false, reason: 'missing' }); continue; }
      const isDir = fs.statSync(t).isDirectory();
      exec('icacls', [t, '/inheritance:r', '/grant:r', isDir ? `${user}:(OI)(CI)F` : `${user}:F`], { windowsHide: true, timeout: 8000, stdio: 'ignore' });
      res.push({ target: t, ok: true });
    } catch (e) { res.push({ target: t, ok: false, reason: String((e && e.code) || (e && e.message) || e).slice(0, 80) }); }
  }
  return res;
}
