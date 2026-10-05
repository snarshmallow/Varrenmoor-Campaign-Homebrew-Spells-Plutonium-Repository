// Run on the Foundry (host) PC if the relay is already running and you don't want to restart it:
//   node publish-client.mjs
// Reads the API token from .env and the live tunnel URL from the module's relay-url.json, writes bridge\client.json.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { foundryDataPath, publishClient } from './lib/publish.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const env = {};
for (const line of fs.readFileSync(path.join(root, '.env'), 'utf8').split(/\r?\n/)) {
  const m = line.match(/^\s*([A-Z_]+)\s*=\s*(.*)\s*$/);
  if (m) env[m[1]] = m[2];
}
const urlFile = path.join(foundryDataPath(), 'Data', 'modules', 'varrenmoor-bridge', 'relay-url.json');
const wss = JSON.parse(fs.readFileSync(urlFile, 'utf8')).url;               // wss://name.trycloudflare.com/module
const publicUrl = env.PUBLIC_URL || wss.replace(/^wss:/, 'https:').replace(/^ws:/, 'http:').replace(/\/module$/, '');
const r = publishClient({ publicUrl, apiToken: env.BRIDGE_API_TOKEN, dir: env.CLIENT_CONFIG_DIR });
console.log(r.ok ? `Wrote ${r.file}\nurl: ${publicUrl}` : `Not written: ${r.reason}`);
