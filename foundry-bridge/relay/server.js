import http from 'node:http';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { WebSocketServer } from 'ws';
import { Pairing, isPrivateIp, isLanHostname, hostOfHeader, isAllowedOrigin } from './pairing.js';
import { makeAdminVerifier } from './adminauth.js';
import * as X from './seccrypto.js';

const PORT = Number(process.env.PORT) || 3030;
const HOST = process.env.HOST || '127.0.0.1';
const API_TOKEN = process.env.BRIDGE_API_TOKEN || '';
const MODULE_TOKEN = process.env.BRIDGE_MODULE_TOKEN || '';
const TIMEOUT_MS = Number(process.env.BRIDGE_TIMEOUT_MS) || 35000;
const MAX_BODY = 5 * 1024 * 1024;

const PROXY_HEADERS = ['cf-connecting-ip', 'cf-ray', 'x-forwarded-for', 'x-forwarded-host', 'forwarded', 'x-real-ip'];

// pairingFile: path of the git-ignored paired-devices.json (omit = pairing disabled). peerIp: how a request's source address is read (tests override it).
// tunnel: true when a tunnel / public reverse proxy is (or may be) in front of this relay (start.mjs without --local, PUBLIC_URL set). The pairing and admin endpoints then do not exist at all:
// a header blacklist alone is not a safe way to tell a tunnelled request from a local one. allowedOrigins: extra exact browser origins accepted for the device endpoints (env BRIDGE_ALLOWED_ORIGINS, comma separated).
export function createRelay({ apiToken = API_TOKEN, moduleToken = MODULE_TOKEN, timeoutMs = TIMEOUT_MS, pairingFile = process.env.BRIDGE_PAIRING_FILE || null, pairingEnabled, autoRequest, pairingLimits = {}, peerIp = (req) => req.socket.remoteAddress,
  tunnel = !!process.env.PUBLIC_URL, allowedOrigins = String(process.env.BRIDGE_ALLOWED_ORIGINS || '').split(',').map((x) => x.trim()).filter(Boolean), foundryPort = Number(process.env.FOUNDRY_PORT) || 30000, adminStateFile } = {}) {
  if (apiToken.length < 24 || moduleToken.length < 24) {
    throw new Error('BRIDGE_API_TOKEN and BRIDGE_MODULE_TOKEN must each be at least 24 characters.');
  }
  if (apiToken === moduleToken) throw new Error('API and module tokens must differ.');

  const same = (a, b) => {
    const ha = crypto.createHash('sha256').update(a).digest();
    const hb = crypto.createHash('sha256').update(b).digest();
    return crypto.timingSafeEqual(ha, hb);
  };

  const originOk = (origin, host = '') => isAllowedOrigin(origin, { extra: allowedOrigins, foundryPort, relayHost: host });
  const pairing = new Pairing({ file: pairingFile, enabled: pairingEnabled, autoRequest, limits: pairingLimits, originCheck: (o) => originOk(o) });
  const verifyAdmin = makeAdminVerifier({ apiToken, stateFile: adminStateFile !== undefined ? adminStateFile : pairingFile ? pairingFile.replace(/\.json$/, '') + '.admin-ts.json' : null });
  let moduleSocket = null;
  let moduleDeviceId = null;   // set when the current module socket authenticated as a paired device
  const startedAt = new Date().toISOString();
  const replacedAt = [];   // times of 4002 evictions (two GM tabs fighting), for /health
  const pending = new Map();
  const log = (...a) => console.log(new Date().toLocaleTimeString(), ...a);
  if (tunnel) log('WARNING: tunnel / public URL mode: pairing and admin endpoints are disabled. Use start.bat --local for pairing.');

  // ---- LAN pairing endpoints -------------------------------------------------------------------------------------------------------
  // Device endpoints (/discover, /pair/request, /pair/reveal, /pair/poll): the handshake is encrypted (see pairing.js); only from private source addresses and never through a proxy/tunnel.
  // Admin endpoints (/pair/list|approve|deny|revoke|rotate|config): API token (Bearer, or a signed X-VB-Auth header that never sends the token) + the same source restriction,
  // so a tunnelled caller (Claude over Cloudflare) cannot approve devices or switch pairing on.
  const readJson = async (req, max = 8192) => {
    let raw = '';
    try { for await (const chunk of req) { raw += chunk; if (raw.length > max) return { raw: '', json: null }; } } catch { return { raw: '', json: null, aborted: true }; }   // client reset the connection mid-body
    try { const j = JSON.parse(raw || '{}'); return { raw, json: j && typeof j === 'object' && !Array.isArray(j) ? j : null }; } catch { return { raw, json: null }; }
  };
  const ADMIN = new Set(['/pair/list', '/pair/approve', '/pair/deny', '/pair/revoke', '/pair/rotate', '/pair/config']);
  const DEVICE = new Set(['/pair/request', '/pair/reveal', '/pair/poll', '/pair/cancel']);
  async function pairRoutes(req, res) {
    const url = req.url, ip = peerIp(req) || '';
    if (!(url === '/discover' || DEVICE.has(url) || ADMIN.has(url))) return false;
    const origin = req.headers.origin || '', hostName = hostOfHeader(req.headers.host);
    // CORS only for the device endpoints and only for an allowed Foundry origin (echoed back, never '*'). Admin endpoints send no CORS headers: the panel is Node, not a browser.
    const cors = {};
    if (!ADMIN.has(url) && origin && originOk(origin, hostName)) {
      Object.assign(cors, { 'access-control-allow-origin': origin, vary: 'Origin', 'access-control-allow-methods': 'GET, POST, OPTIONS', 'access-control-allow-headers': 'content-type', 'access-control-max-age': '600' });
      if (req.headers['access-control-request-private-network']) cors['access-control-allow-private-network'] = 'true';
    }
    const out = (code, body) => { res.writeHead(code, { 'content-type': 'application/json', ...cors }); res.end(JSON.stringify(body)); };
    if (tunnel) { log('pairing: refused', url, '(relay started with a tunnel/public URL: pairing and admin endpoints are off)'); out(403, { error: 'pairing is off while the relay runs with a tunnel or public URL; start it with start.bat --local' }); return true; }
    if (!isPrivateIp(ip)) { log('pairing: refused', url, 'from non-private address', ip); out(403, { error: 'pairing is only available from the local network' }); return true; }
    if (PROXY_HEADERS.some((h) => req.headers[h])) { log('pairing: refused', url, 'request that came through a proxy or tunnel'); out(403, { error: 'pairing is not available through a proxy or tunnel' }); return true; }
    if (!isLanHostname(hostName)) { log('pairing: refused', url, 'Host header is not a LAN address'); out(403, { error: 'pairing is only available when addressed by a LAN host name or IP' }); return true; }
    if (origin && (ADMIN.has(url) || !originOk(origin, hostName))) { log('pairing: refused', url, 'from browser origin', origin.slice(0, 80)); out(403, { error: ADMIN.has(url) ? 'admin calls do not come from web pages' : 'this web page origin is not allowed to pair (expected the Foundry page, http://<Foundry PC>:30000)' }); return true; }
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return true; }
    if (url === '/discover') {
      if (req.method !== 'GET') { out(405, { error: 'GET only' }); return true; }
      if (!pairing.allow('discover', ip, 120, 60000)) { out(429, { error: 'slow down' }); return true; }
      out(200, { service: 'varrenmoor-bridge-relay', protocol: 2, relayId: pairing.relayId, pairing: pairing.enabled, canEnable: pairing.canEnable, autoRequest: pairing.enabled && pairing.autoRequest, wsPath: '/module' });
      return true;
    }
    if (req.method !== 'POST') { out(405, { error: 'POST only' }); return true; }
    const { raw, json: body, aborted } = await readJson(req);
    if (aborted) { try { res.destroy(); } catch { /* gone */ } return true; }
    if (!body) { out(400, { error: 'invalid or oversized JSON' }); return true; }
    if (ADMIN.has(url)) {
      if ((pairing.hits.get('adminfail|' + ip) || []).filter((x) => pairing.now() - x < 60000).length >= 20) { out(429, { error: 'too many failed admin calls; wait a minute' }); return true; }
      const a = verifyAdmin(req, raw);
      if (!a.ok) { pairing.allow('adminfail', ip, 1e9, 60000); out(401, { error: a.reason || 'unauthorized' }); return true; }
    } else if (!pairing.enabled) { out(404, { error: 'pairing is not enabled on this relay' }); return true; }
    let r;
    if (url === '/pair/request') {
      r = pairing.request({ ip, origin: req.headers.origin || '', commit: body.commit });
      if (r.status === 200) log(`pairing: request ${r.requestId} from ${ip}`); else log('pairing: request refused:', r.error);
    } else if (url === '/pair/reveal') {
      r = pairing.reveal({ requestId: body.requestId, pollSecret: body.pollSecret, pk: body.pk, nonce: body.nonce, info: body.info, ip });
      if (r.status !== 200) log('pairing: reveal refused:', r.error);
    } else if (url === '/pair/cancel') r = pairing.cancel(body.requestId, body.pollSecret, ip);
    else if (url === '/pair/poll') r = pairing.poll(body.requestId, body.pollSecret, ip);
    else if (url === '/pair/list') r = { status: 200, ...pairing.list() };
    else if (url === '/pair/config') { r = (typeof body.enabled === 'boolean' || typeof body.autoRequest === 'boolean') ? pairing.configure(body) : { status: 200, ...pairing.list(), pending: undefined, devices: undefined }; if (r.status === 200 && ('enabled' in body || 'autoRequest' in body)) log(`pairing: ${pairing.enabled ? 'ENABLED' : 'DISABLED'}, auto-request ${pairing.autoRequest ? 'on' : 'off'} (set by ${ip})`); }
    else if (url === '/pair/approve') { r = pairing.approve(body.id, { days: body.days, code: body.code }); if (r.status === 200) log('pairing: approved', r.deviceId); else log('pairing: approve refused:', r.error); }
    else if (url === '/pair/deny') { r = pairing.deny(body.id); if (r.status === 200) log('pairing: denied', body.id); }
    else if (url === '/pair/revoke') { r = pairing.revoke(body.deviceId); if (r.status === 200) log('pairing: revoked', body.deviceId); }
    else r = pairing.rotate(body.deviceId);
    const { status, ...rest } = r;
    out(status, rest);
    return true;
  }

  // Any error while serving one request (aborted body, bad input, a socket that went away) answers that request and never takes the relay down.
  const server = http.createServer((req, res) => {
    req.on('error', () => { /* client went away; the handler below sees it through its own reads */ });
    res.on('error', () => {});
    handle(req, res).catch((e) => {
      log('request error:', req.method, String(req.url || '').slice(0, 60), (e && e.code) || (e && e.name) || 'error');
      try { if (!res.headersSent) { res.writeHead(500, { 'content-type': 'application/json' }); res.end('{"error":"internal error"}'); } else res.destroy(); } catch { /* gone */ }
    });
  });
  async function handle(req, res) {
    const send = (code, body) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method === 'GET' && req.url === '/health') {
      const cut = Date.now() - 60000;
      while (replacedAt.length && replacedAt[0] < cut) replacedAt.shift();
      const ip = peerIp(req) || '', lan = isPrivateIp(ip) && !PROXY_HEADERS.some((h) => req.headers[h]);
      // outsiders (tunnel / public) only learn that the relay is up; the details are for the LAN
      if (!lan) return send(200, { ok: true, service: 'varrenmoor-bridge-relay' });
      return send(200, { ok: true, service: 'varrenmoor-bridge-relay', moduleConnected: !!moduleSocket, pid: process.pid, startedAt, replacedLastMinute: replacedAt.length,
        pairing: { enabled: pairing.enabled, canEnable: pairing.canEnable, autoRequest: pairing.autoRequest, pending: pairing.enabled ? pairing.list().pending.length : 0, devices: pairing.data.devices.length } });
    }
    if ((req.url || '') === '/discover' || (req.url || '').startsWith('/pair/')) {
      if (await pairRoutes(req, res)) return;
    }
    if (req.method !== 'POST' || req.url !== '/rpc') return send(404, { error: 'not found' });
    const auth = req.headers.authorization || '';
    if (!auth.startsWith('Bearer ') || !same(auth.slice(7), apiToken)) return send(401, { error: 'unauthorized' });
    if (!moduleSocket) return send(503, { error: 'Foundry module not connected (is a GM client open?)' });

    let raw = '';
    try { for await (const chunk of req) { raw += chunk; if (raw.length > MAX_BODY) return send(413, { error: 'body too large' }); } } catch { return res.destroy(); }
    let msg;
    try { msg = JSON.parse(raw); } catch { return send(400, { error: 'invalid JSON' }); }
    if (!msg || typeof msg !== 'object' || typeof msg.op !== 'string') return send(400, { error: 'op required' });

    const id = crypto.randomUUID();
    const result = new Promise((resolve) => {
      const timer = setTimeout(() => { pending.delete(id); resolve({ error: 'timeout waiting for Foundry' }); }, timeoutMs);
      pending.set(id, { resolve, timer });
    });
    try { moduleSocket.send(JSON.stringify({ id, op: msg.op, args: msg.args ?? {} })); }
    catch { clearTimeout(pending.get(id)?.timer); pending.delete(id); return send(503, { error: 'Foundry module connection dropped' }); }
    const out = await result;
    send(out.error ? 502 : 200, out);
  }

  const wss = new WebSocketServer({ server, path: '/module', maxPayload: MAX_BODY });
  wss.on('error', () => {});
  let unauthSockets = 0;       // sockets that have not authenticated yet: capped, and each may send only a small frame before it does
  wss.on('connection', (ws, req) => {
    ws.on('error', () => {});
    if (unauthSockets >= 16) { ws.close(4009, 'busy'); return; }
    unauthSockets++; let counted = true;
    const uncount = () => { if (counted) { counted = false; unauthSockets--; } };
    log('module socket opened from', req.socket.remoteAddress, 'origin', req.headers.origin || '-');
    let authed = false, deviceId = null, challenge = null;
    const deadline = setTimeout(() => { if (!authed) ws.close(4001, 'auth timeout'); }, 5000);
    const accept = (devId, extra) => {
      authed = true; deviceId = devId; clearTimeout(deadline); uncount();
      if (moduleSocket && moduleSocket !== ws) { replacedAt.push(Date.now()); moduleSocket.close(4002, 'replaced'); log('WARN replacing an existing module client (4002): two GM tabs are open?'); }
      moduleSocket = ws; moduleDeviceId = devId;
      ws.send(JSON.stringify({ type: 'welcome', ...extra }));
    };
    ws.on('message', (data) => {
      try {
      if (!authed && data.length > 4096) { ws.close(4003, 'bad auth'); return; }
      let m;
      try { m = JSON.parse(data.toString()); } catch { return; }
      if (!m || typeof m !== 'object' || Array.isArray(m)) return;     // 'null', numbers, strings, arrays: ignore (must never throw before authentication)
      if (!authed) {
        const ip = peerIp(req) || '';
        const lan = !tunnel && isPrivateIp(ip) && !PROXY_HEADERS.some((h) => req.headers[h]) && isLanHostname(hostOfHeader(req.headers.host));
        // paired device, step 1: hello {deviceId, cn} -> challenge {rn} (answered the same way for unknown ids, so ids cannot be probed)
        if (m.type === 'hello' && typeof m.deviceId === 'string' && typeof m.cn === 'string' && pairing.enabled) {
          if (!lan) { log('module rejected: device login from a non-LAN source'); ws.close(4003, 'bad auth'); return; }
          if (challenge) { ws.close(4003, 'bad auth'); return; }
          challenge = { deviceId: m.deviceId.slice(0, 40), cn: m.cn.slice(0, 64), rn: X.b64u(X.randomBytes(16)) };
          ws.send(JSON.stringify({ type: 'challenge', rn: challenge.rn }));
          return;
        }
        // paired device, step 2: auth {mac}
        if (m.type === 'auth' && challenge && typeof m.mac === 'string' && pairing.enabled) {
          const a = pairing.authenticate(challenge.deviceId, challenge.cn, challenge.rn, m.mac.slice(0, 100), ip);
          if (!a.ok) { log('module rejected: device', a.reason); ws.close(a.limited ? 4008 : 4005, a.limited ? 'rate limited' : 'device ' + a.reason); return; }
          accept(a.device.id, { proof: a.proof, ...(a.rotate ? { rotate: a.rotate } : {}) });
          log(`module authenticated (paired device ${a.device.id} "${a.device.name}"${a.rotate ? ', secret rotated' : ''})`);
          return;
        }
        if (m.type === 'hello' && typeof m.token === 'string' && same(m.token, moduleToken)) { accept(null, {}); log('module authenticated (manual token)'); }
        else { log('module rejected: bad token'); ws.close(4003, 'bad auth'); }
        return;
      }
      const p = typeof m.id === 'string' ? pending.get(m.id) : null;
      if (!p) return;
      clearTimeout(p.timer);
      pending.delete(m.id);
      p.resolve(m.error ? { error: String(m.error) } : { result: m.result });
      } catch (e) { log('module message error:', (e && e.name) || 'error'); try { ws.close(1011, 'error'); } catch { /* closed */ } }
    });
    ws.on('close', (code) => {
      log('module socket closed', code);
      clearTimeout(deadline); uncount();
      if (moduleSocket === ws) { moduleSocket = null; moduleDeviceId = null; }
    });
  });

  pairing.on('revoked', ({ id, replaced }) => { if (!replaced && moduleSocket && moduleDeviceId === id) moduleSocket.close(4005, 'device revoked'); });
  server.pairing = pairing;
  server.on('close', () => { pairing.flush(); verifyAdmin.flush(); });
  return server;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  createRelay().listen(PORT, HOST, () => console.log(`Varrenmoor bridge relay on ${HOST}:${PORT}`));
}
