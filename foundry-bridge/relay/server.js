import http from 'node:http';
import crypto from 'node:crypto';
import { WebSocketServer } from 'ws';

const PORT = Number(process.env.PORT) || 3030;
const HOST = process.env.HOST || '127.0.0.1';
const API_TOKEN = process.env.BRIDGE_API_TOKEN || '';
const MODULE_TOKEN = process.env.BRIDGE_MODULE_TOKEN || '';
const TIMEOUT_MS = Number(process.env.BRIDGE_TIMEOUT_MS) || 35000;
const MAX_BODY = 5 * 1024 * 1024;

export function createRelay({ apiToken = API_TOKEN, moduleToken = MODULE_TOKEN, timeoutMs = TIMEOUT_MS } = {}) {
  if (apiToken.length < 24 || moduleToken.length < 24) {
    throw new Error('BRIDGE_API_TOKEN and BRIDGE_MODULE_TOKEN must each be at least 24 characters.');
  }
  if (apiToken === moduleToken) throw new Error('API and module tokens must differ.');

  const same = (a, b) => {
    const ha = crypto.createHash('sha256').update(a).digest();
    const hb = crypto.createHash('sha256').update(b).digest();
    return crypto.timingSafeEqual(ha, hb);
  };

  let moduleSocket = null;
  const pending = new Map();

  const server = http.createServer(async (req, res) => {
    const send = (code, body) => {
      res.writeHead(code, { 'content-type': 'application/json' });
      res.end(JSON.stringify(body));
    };
    if (req.method === 'GET' && req.url === '/health') {
      return send(200, { ok: true, moduleConnected: !!moduleSocket });
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
  wss.on('connection', (ws) => {
    let authed = false;
    const deadline = setTimeout(() => { if (!authed) ws.close(4001, 'auth timeout'); }, 5000);
    ws.on('message', (data) => {
      let m;
      try { m = JSON.parse(data.toString()); } catch { return; }
      if (!authed) {
        if (m.type === 'hello' && typeof m.token === 'string' && same(m.token, moduleToken)) {
          authed = true;
          clearTimeout(deadline);
          if (moduleSocket && moduleSocket !== ws) moduleSocket.close(4002, 'replaced');
          moduleSocket = ws;
          ws.send(JSON.stringify({ type: 'welcome' }));
        } else ws.close(4003, 'bad auth');
        return;
      }
      const p = pending.get(m.id);
      if (!p) return;
      clearTimeout(p.timer);
      pending.delete(m.id);
      p.resolve(m.error ? { error: m.error } : { result: m.result });
    });
    ws.on('close', () => {
      clearTimeout(deadline);
      if (moduleSocket === ws) moduleSocket = null;
    });
  });

  return server;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  createRelay().listen(PORT, HOST, () => console.log(`Varrenmoor bridge relay on ${HOST}:${PORT}`));
}
