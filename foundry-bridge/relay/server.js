import http from 'node:http';
import crypto from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { WebSocketServer } from 'ws';
import { Pairing, isPrivateIp } from './pairing.js';
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
export function createRelay({ apiToken = API_TOKEN, moduleToken = MODULE_TOKEN, timeoutMs = TIMEOUT_MS, pairingFile = process.env.BRIDGE_PAIRING_FILE || null, pairingEnabled, autoRequest, pairingLimits = {}, peerIp = (req) => req.socket.remoteAddress } = {}) {
  if (apiToken.length < 24 || moduleToken.length < 24) {
    throw new Error('BRIDGE_API_TOKEN and BRIDGE_MODULE_TOKEN must each be at least 24 characters.');
  }
  if (apiToken === moduleToken) throw new Error('API and module tokens must differ.');

  const same = (a, b) => {
    const ha = crypto.createHash('sha256').update(a).digest();
    const hb = crypto.createHash('sha256').update(b).digest();
    return crypto.timingSafeEqual(ha, hb);
  };

  const pairing = new Pairing({ file: pairingFile, enabled: pairingEnabled, autoRequest, limits: pairingLimits });
  const verifyAdmin = makeAdminVerifier({ apiToken });
  let moduleSocket = null;
  let moduleDeviceId = null;   // set when the current module socket authenticated as a paired device
  const startedAt = new Date().toISOString();
  const replacedAt = [];   // times of 4002 evictions (two GM tabs fighting), for /health
  const pending = new Map();

  // ---- LAN pairing endpoints -------------------------------------------------------------------------------------------------------
  // Device endpoints (/discover, /pair/request, /pair/reveal, /pair/poll): the handshake is encrypted (see pairing.js); only from private source addresses and never through a proxy/tunnel.
  // Admin endpoints (/pair/list|approve|deny|revoke|rotate|config): API token (Bearer, or a signed X-VB-Auth header that never sends the token) + the same source restriction,
  // so a tunnelled caller (Claude over Cloudflare) cannot approve devices or switch pairing on.
  const readJson = async (req, max = 8192) => {
    let raw = '';
    for await (const chunk of req) { raw += chunk; if (raw.length > max) return { raw: '', json: null }; }
    try { const j = JSON.parse(raw || '{}'); return { raw, json: j && typeof j === 'object' ? j : null }; } catch { return { raw, json: null }; }
  };
  const ADMIN = new Set(['/pair/list', '/pair/approve', '/pair/deny', '/pair/revoke', '/pair/rotate', '/pair/config']);
  const DEVICE = new Set(['/pair/request', '/pair/reveal', '/pair/poll', '/pair/cancel']);
  async function pairRoutes(req, res) {
    const url = req.url, ip = peerIp(req) || '';
    const cors = { 'access-control-allow-origin': '*', 'access-control-allow-methods': 'GET, POST, OPTIONS', 'access-control-allow-headers': 'content-type, authorization, x-vb-auth', 'access-control-allow-private-network': 'true', 'access-control-max-age': '600' };
    const out = (code, body) => { res.writeHead(code, { 'content-type': 'application/json', ...cors }); res.end(JSON.stringify(body)); };
    if (!(url === '/discover' || DEVICE.has(url) || ADMIN.has(url))) return false;
    if (req.method === 'OPTIONS') { res.writeHead(204, cors); res.end(); return true; }
    if (!isPrivateIp(ip)) { log('pairing: refused', url, 'from non-private address', ip); out(403, { error: 'pairing is only available from the local network' }); return true; }
    if (PROXY_HEADERS.some((h) => req.headers[h])) { log('pairing: refused', url, 'request that came through a proxy or tunnel'); out(403, { error: 'pairing is not available through a proxy or tunnel' }); return true; }
    if (url === '/discover') {
      if (req.method !== 'GET') { out(405, { error: 'GET only' }); return true; }
      if (!pairing.allow('discover', ip, 120, 60000)) { out(429, { error: 'slow down' }); return true; }
      out(200, { service: 'varrenmoor-bridge-relay', protocol: 2, relayId: pairing.relayId, pairing: pairing.enabled, canEnable: pairing.canEnable, autoRequest: pairing.enabled && pairing.autoRequest, wsPath: '/module' });
      return true;
    }
    if (req.method !== 'POST') { out(405, { error: 'POST only' }); return true; }
    const { raw, json: body } = await readJson(req);
    if (!body) { out(400, { error: 'invalid or oversized JSON' }); return true; }
    if (ADMIN.has(url)) {
      const a = verifyAdmin(req, raw);
      if (!a.ok) { out(401, { error: a.reason || 'unauthorized' }); return true; }
    } else if (!pairing.enabled) { out(404, { error: 'pairing is not enabled on this relay' }); return true; }
    let r;
    if (url === '/pair/request') {
      r = pairing.request({ ip, origin: req.headers.origin || '', commit: body.commit });
      if (r.status === 200) log(`pairing: request ${r.requestId} from ${ip}`); else log('pairing: request refused:', r.error);
    } else if (url === '/pair/reveal') {
      r = pairing.reveal({ requestId: body.requestId, pollSecret: body.pollSecret, pk: body.pk, nonce: body.nonce, info: body.info, ip });
      if (r.status !== 200) log('pairing: reveal refused:', r.error);
    } else if (url === '/pair/cancel') r = pairing.cancel(body.requestId, body.pollSecret);
    else if (url === '/pair/poll') r = pairing.poll(body.requestId, body.pollSecret, ip);
    else if (url === '/pair/list') r = { status: 200, ...pairing.list() };
    else if (url === '/pair/config') { r = (typeof body.enabled === 'boolean' || typeof body.autoRequest === 'boolean') ? pairing.configure(body) : { status: 200, ...pairing.list(), pending: undefined, devices: undefined }; if (r.status === 200 && ('enabled' in body || 'autoRequest' in body)) log(`pairing: ${pairing.enabled ? 'ENABLED' : 'DISABLED'}, auto-request ${pairing.autoRequest ? 'on' : 'off'} (set by ${ip})`); }
    else if (url === '/pair/approve') { r = pairing.approve(body.id, { days: body.days }); if (r.status === 200) log('pairing: approved', r.deviceId); }
    else if (url === '/pair/deny') { r = pairing.deny(body.id); if (r.status === 200) log('pairing: denied', body.id); }
    else if (url === '/pair/revoke') { r = pairing.revoke(body.deviceId); if (r.status === 200) log('pairing: revoked', body.deviceId); }
    else r = pairing.rotate(body.deviceId);
    const { status, ...rest } = r;
    out(status, rest);
    return true;
  }

  const server = http.createServer(async (req, res) => {
    const send = (code, body) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method === 'GET' && req.url === '/health') {
      const cut = Date.now() - 60000;
      while (replacedAt.length && replacedAt[0] < cut) replacedAt.shift();
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
    for await (const chunk of req) {
      raw += chunk;
      if (raw.length > MAX_BODY) return send(413, { error: 'body too large' });
    }
    let msg;
    try { msg = JSON.parse(raw); } catch { return send(400, { error: 'invalid JSON' }); }
    if (typeof msg.op !== 'string') return send(400, { error: 'op required' });

    const id = crypto.randomUUID();
    const result = new Promise((resolve) => {
      const timer = setTimeout(() => { pending.delete(id); resolve({ error: 'timeout waiting for Foundry' }); }, timeoutMs);
      pending.set(id, { resolve, timer });
    });
    moduleSocket.send(JSON.stringify({ id, op: msg.op, args: msg.args ?? {} }));
    const out = await result;
    send(out.error ? 502 : 200, out);
  });

  const wss = new WebSocketServer({ server, path: '/module', maxPayload: MAX_BODY });
  const log = (...a) => console.log(new Date().toLocaleTimeString(), ...a);
  wss.on('connection', (ws, req) => {
    log('module socket opened from', req.socket.remoteAddress, 'origin', req.headers.origin || '-');
    let authed = false, deviceId = null, challenge = null;
    const deadline = setTimeout(() => { if (!authed) ws.close(4001, 'auth timeout'); }, 5000);
    const accept = (devId, extra) => {
      authed = true; deviceId = devId; clearTimeout(deadline);
      if (moduleSocket && moduleSocket !== ws) { replacedAt.push(Date.now()); moduleSocket.close(4002, 'replaced'); log('WARN replacing an existing module client (4002): two GM tabs are open?'); }
      moduleSocket = ws; moduleDeviceId = devId;
      ws.send(JSON.stringify({ type: 'welcome', ...extra }));
    };
    ws.on('message', (data) => {
      let m;
      try { m = JSON.parse(data.toString()); } catch { return; }
      if (!authed) {
        const ip = peerIp(req) || '';
        const lan = isPrivateIp(ip) && !PROXY_HEADERS.some((h) => req.headers[h]);
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
      const p = pending.get(m.id);
      if (!p) return;
      clearTimeout(p.timer);
      pending.delete(m.id);
      p.resolve(m.error ? { error: m.error } : { result: m.result });
    });
    ws.on('close', (code) => {
      log('module socket closed', code);
      clearTimeout(deadline);
      if (moduleSocket === ws) { moduleSocket = null; moduleDeviceId = null; }
    });
  });

  pairing.on('revoked', ({ id, replaced }) => { if (!replaced && moduleSocket && moduleDeviceId === id) moduleSocket.close(4005, 'device revoked'); });
  server.pairing = pairing;
  server.on('close', () => pairing.flush());
  return server;
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  createRelay().listen(PORT, HOST, () => console.log(`Varrenmoor bridge relay on ${HOST}:${PORT}`));
}
