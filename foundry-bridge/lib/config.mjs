// Shared config helpers for the managed relay (daemon.mjs, bridgectl.mjs). Never logs token values.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';

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
  return { dir: stateDir, pid: path.join(stateDir, 'relay.pid.json'), log: path.join(stateDir, 'relay.log') };
}
