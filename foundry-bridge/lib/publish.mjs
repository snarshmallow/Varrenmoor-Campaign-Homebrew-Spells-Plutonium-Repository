// Publishes the relay's public URL + API token to <Foundry dataPath>\bridge\client.json so a Claude Code session on
// another PC on the LAN (reading \\<host>\C\FoundryVTT resources\bridge\client.json) configures itself.
// The file lives OUTSIDE Foundry's Data folder on purpose: Foundry serves Data/ over HTTP to every connected player.
import fs from 'node:fs';
import path from 'node:path';

export function foundryDataPath() {
  try {
    const opts = JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA || '', 'FoundryVTT', 'Config', 'options.json'), 'utf8'));
    return opts.dataPath || '';
  } catch { return ''; }
}

export function publishClient({ publicUrl, apiToken, dir = process.env.CLIENT_CONFIG_DIR || '', fallbackDir = '', localUrl = '' }) {
  if (!publicUrl || !apiToken) return { ok: false, reason: 'no public URL or token yet' };
  const usingFallback = !dir && !foundryDataPath();
  if (usingFallback && localUrl) publicUrl = localUrl;   // same-PC client: skip the tunnel (its DNS name can lag locally)
  // Relay on the Foundry PC: <dataPath>\bridge. Relay on any other PC: next to the launcher (git-ignored), which
  // bridge.ps1 on that same PC reads first.
  const base = dir || (foundryDataPath() && path.join(foundryDataPath(), 'bridge')) || fallbackDir;
  if (!base) return { ok: false, reason: 'Foundry dataPath not found (set CLIENT_CONFIG_DIR in .env)' };
  fs.mkdirSync(base, { recursive: true });
  const file = path.join(base, 'client.json');
  fs.writeFileSync(file, JSON.stringify({ url: publicUrl, token: apiToken, updated: new Date().toISOString() }, null, 2) + '\n');
  return { ok: true, file };
}
