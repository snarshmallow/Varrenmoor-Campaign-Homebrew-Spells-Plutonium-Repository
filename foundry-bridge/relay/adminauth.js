// Signed admin requests: the panel proves it knows the API token WITHOUT sending it (a plain-http LAN sniffer then never sees the token).
//   X-VB-Auth: v1 ts=<ms> n=<nonce> sig=<base64url HMAC-SHA256(apiToken, "vb-admin-v1\nMETHOD\nURL\nts\nn\nsha256hex(body)")>
// Accepted within +-5 minutes of the relay clock, each nonce once (replay protection). A plain "Authorization: Bearer <token>" still works for scripts (bridge.ps1).
import crypto from 'node:crypto';
import fs from 'node:fs';

export const signAdmin = ({ token, method, url, body = '', ts = Date.now(), nonce = crypto.randomBytes(12).toString('base64url') }) => {
  const sig = crypto.createHmac('sha256', token).update(['vb-admin-v1', method.toUpperCase(), url, String(ts), nonce, crypto.createHash('sha256').update(body).digest('hex')].join('\n')).digest('base64url');
  return `v1 ts=${ts} n=${nonce} sig=${sig}`;
};

// Replay protection across restarts: the nonce cache is in memory, so a captured request could be replayed right after the relay restarts. A signed request is therefore only
// accepted when its timestamp is NEWER than both this process's start time and the newest timestamp ever accepted (kept in `stateFile`, written at most every 2 s).
export function makeAdminVerifier({ apiToken, now = () => Date.now(), skewMs = 300000, stateFile = null }) {
  const seen = new Map();
  let high = 0, saved = 0, lastWrite = 0;
  if (stateFile) { try { high = Number(JSON.parse(fs.readFileSync(stateFile, 'utf8')).highTs) || 0; } catch { /* first run */ } }
  const floor = Math.max(now(), high + 2000);       // +2 s: the last accepted timestamp may not have reached the disk before a crash
  const persist = (force) => {
    if (!stateFile || high === saved || (!force && now() - lastWrite < 2000)) return;
    try { fs.writeFileSync(stateFile, JSON.stringify({ highTs: high })); saved = high; lastWrite = now(); } catch { /* best effort */ }
  };
  const bearerOk = (h) => { const a = crypto.createHash('sha256').update(h).digest(), b = crypto.createHash('sha256').update(apiToken).digest(); return crypto.timingSafeEqual(a, b); };
  // -> { ok, via: 'bearer'|'signed', reason? }
  function verify(req, rawBody) {
    const auth = req.headers.authorization || '';
    if (auth.startsWith('Bearer ')) return bearerOk(auth.slice(7)) ? { ok: true, via: 'bearer' } : { ok: false, reason: 'unauthorized' };
    const h = String(req.headers['x-vb-auth'] || '');
    const m = h.match(/^v1 ts=(\d{10,16}) n=([A-Za-z0-9_-]{8,64}) sig=([A-Za-z0-9_-]{40,50})$/);
    if (!m) return { ok: false, reason: 'unauthorized' };
    const t = now(), ts = Number(m[1]);
    if (Math.abs(t - ts) > skewMs) return { ok: false, reason: 'clock differs by more than 5 minutes between the two PCs' };
    if (ts < floor) return { ok: false, reason: 'request is older than the relay start (or a previous request); sign it again' };
    const expect = signAdmin({ token: apiToken, method: req.method, url: req.url, body: rawBody, ts, nonce: m[2] }).split('sig=')[1];
    const a = Buffer.from(expect), b = Buffer.from(m[3]);
    if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return { ok: false, reason: 'unauthorized' };
    for (const [k, v] of seen) if (t - v > skewMs * 2) seen.delete(k);
    if (seen.has(m[2])) return { ok: false, reason: 'replayed request' };
    seen.set(m[2], t);
    if (ts > high) { high = ts; persist(false); }
    return { ok: true, via: 'signed' };
  }
  verify.flush = () => persist(true);
  return verify;
}
