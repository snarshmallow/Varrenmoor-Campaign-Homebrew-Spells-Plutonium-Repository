// LAN device pairing for the Varrenmoor relay. Pure logic (no HTTP), so it is unit-testable; server.js exposes it over HTTP/WebSocket.
//
// Flow: a device (the Foundry module in a GM browser) files a pairing request; the relay shows it to the human (relay window + Illustrator
// panel) with a 6-digit confirmation code that the device displays too; on approval the relay issues a per-device token. Only a SHA-256
// hash of the token is stored (paired-devices.json, git-ignored, mode 0600); the token itself is handed over exactly once, to whoever
// holds the poll secret from the original request. Nothing here ever logs or returns a token except that one hand-over.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { EventEmitter } from 'node:events';

const sha = (s) => crypto.createHash('sha256').update(String(s)).digest('hex');
const eq = (a, b) => { const x = Buffer.from(String(a || '')), y = Buffer.from(String(b || '')); return x.length === y.length && crypto.timingSafeEqual(x, y); };
const rand = (n = 32) => crypto.randomBytes(n).toString('base64url');
const clip = (v, n = 80) => String(v ?? '').replace(/[\u0000-\u001f\u007f]/g, ' ').slice(0, n);

// RFC1918 + loopback + link-local + unique-local IPv6 (also IPv4-mapped). Anything else (public, CGNAT, unspecified, junk) is refused.
export function isPrivateIp(addr) {
  let a = String(addr || '').trim().toLowerCase();
  if (a.startsWith('::ffff:')) a = a.slice(7);
  const m = a.match(/^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/);
  if (m) {
    const [o1, o2, o3, o4] = m.slice(1).map(Number);
    if ([o1, o2, o3, o4].some((n) => n > 255)) return false;
    return o1 === 10 || o1 === 127 || (o1 === 192 && o2 === 168) || (o1 === 172 && o2 >= 16 && o2 <= 31) || (o1 === 169 && o2 === 254);
  }
  if (a === '::1') return true;
  if (/^f[cd][0-9a-f]{2}:/.test(a)) return true;       // fc00::/7
  if (/^fe[89ab][0-9a-f]:/.test(a)) return true;       // fe80::/10
  return false;
}

export class Pairing extends EventEmitter {
  constructor({ file, now = () => Date.now(), pendingTtlMs = 120000, rotateWithinDays = 14, limits = {} } = {}) {
    super();
    this.file = file || null; this.now = now; this.pendingTtlMs = pendingTtlMs; this.rotateWithinMs = rotateWithinDays * 86400000;
    this.limits = { requestsPerWindow: 5, requestWindowMs: 600000, maxPending: 5, maxPendingPerIp: 2, denyCooldownMs: 60000, pollsPerMin: 90, authFailsPerMin: 10, ...limits };
    this.pending = new Map();      // requestId -> { id, code, secretHash, ip, origin, info, createdAt, expiresAt, status, token?, deviceId?, days }
    this.hits = new Map();         // "kind|ip" -> [timestamps]
    this.coolUntil = new Map();    // ip -> ms
    this.data = { version: 1, relayId: 'r_' + crypto.randomBytes(6).toString('hex'), devices: [] };
    this.lastSave = 0; this.dirty = false;
    this.load();
  }

  get enabled() { return !!this.file; }
  get relayId() { return this.data.relayId; }

  load() {
    if (!this.file) return;
    try {
      const d = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      if (d && Array.isArray(d.devices)) this.data = { version: 1, relayId: d.relayId || this.data.relayId, devices: d.devices };
    } catch { /* first run or unreadable: start empty */ }
    this.save(true);
  }

  save(force = false) {
    if (!this.file) return;
    this.dirty = true;
    if (!force && this.now() - this.lastSave < 60000) return;
    try {
      fs.mkdirSync(path.dirname(this.file), { recursive: true });
      const tmp = this.file + '.tmp';
      fs.writeFileSync(tmp, JSON.stringify(this.data, null, 1) + '\n', { mode: 0o600 });
      fs.renameSync(tmp, this.file);
      this.dirty = false; this.lastSave = this.now();
    } catch { /* keep in memory; retried on the next change */ }
  }
  flush() { if (this.dirty) this.save(true); }

  // sliding-window counter; returns true when the call is allowed
  allow(kind, ip, limit, windowMs) {
    const key = kind + '|' + ip, t = this.now(), arr = (this.hits.get(key) || []).filter((x) => t - x < windowMs);
    if (arr.length >= limit) { this.hits.set(key, arr); return false; }
    arr.push(t); this.hits.set(key, arr);
    if (this.hits.size > 2000) for (const [k, v] of this.hits) if (!v.length || t - v[v.length - 1] > 3600000) this.hits.delete(k);
    return true;
  }

  sweep() {
    const t = this.now();
    for (const [id, p] of this.pending) {
      if (p.status === 'pending' && t > p.expiresAt) { p.status = 'expired'; this.emit('expired', this.publicRequest(p)); }
      if (t > p.expiresAt + 5 * 60000) this.pending.delete(id);   // keep finished ones a little so polls can read the outcome
    }
  }

  publicRequest(p) {
    return { id: p.id, code: p.code, ip: p.ip, origin: p.origin, name: p.info.deviceName, claimedOrigin: p.info.hostOrigin, originMismatch: !!(p.origin && p.info.hostOrigin && p.origin !== p.info.hostOrigin),
      worldId: p.info.worldId, userId: p.info.userId, userName: p.info.userName, createdAt: new Date(p.createdAt).toISOString(), expiresAt: new Date(p.expiresAt).toISOString(), status: p.status };
  }

  // ---- device side ------------------------------------------------------------------------------------------------------------
  request({ ip, origin = '', info = {} }) {
    if (!this.enabled) return { status: 404, error: 'pairing is not enabled on this relay' };
    this.sweep();
    const t = this.now();
    if ((this.coolUntil.get(ip) || 0) > t) return { status: 429, error: 'a request from this address was denied a moment ago; wait a minute' };
    if (!this.allow('request', ip, this.limits.requestsPerWindow, this.limits.requestWindowMs)) return { status: 429, error: 'too many pairing requests from this address; try again later' };
    const live = [...this.pending.values()].filter((p) => p.status === 'pending');
    if (live.length >= this.limits.maxPending) return { status: 429, error: 'too many pairing requests are already waiting for approval' };
    if (live.filter((p) => p.ip === ip).length >= this.limits.maxPendingPerIp) return { status: 429, error: 'this address already has pairing requests waiting' };
    let code; do { code = String(crypto.randomInt(0, 1000000)).padStart(6, '0'); } while (live.some((p) => p.code === code));
    const secret = rand(32), id = 'p_' + crypto.randomBytes(6).toString('hex');
    const p = { id, code, secretHash: sha(secret), ip, origin: clip(origin, 120), createdAt: t, expiresAt: t + this.pendingTtlMs, status: 'pending',
      info: { deviceName: clip(info.deviceName || 'unnamed device', 60), worldId: clip(info.worldId, 60), userId: clip(info.userId, 40), userName: clip(info.userName, 60), hostOrigin: clip(info.hostOrigin, 120) } };
    this.pending.set(id, p);
    this.emit('request', this.publicRequest(p));
    return { status: 200, requestId: id, code: p.code.replace(/(\d{3})(\d{3})/, '$1 $2'), pollSecret: secret, expiresAt: new Date(p.expiresAt).toISOString() };
  }

  poll(requestId, pollSecret, ip) {
    if (!this.allow('poll', ip, this.limits.pollsPerMin, 60000)) return { status: 429, error: 'polling too fast' };
    this.sweep();
    const p = this.pending.get(String(requestId));
    if (!p || !eq(sha(pollSecret), p.secretHash)) return { status: 200, state: 'unknown' };
    if (p.status === 'approved' && p.token) {
      const out = { status: 200, state: 'approved', deviceId: p.deviceId, token: p.token, expiresAt: p.deviceExpiresAt, relayId: this.relayId };
      delete p.token; p.status = 'delivered';       // hand the token over exactly once
      return out;
    }
    return { status: 200, state: p.status };       // pending | denied | expired | delivered
  }

  // ---- admin side (human) -----------------------------------------------------------------------------------------------------
  list() {
    this.sweep();
    return {
      relayId: this.relayId,
      pending: [...this.pending.values()].filter((p) => p.status === 'pending').map((p) => this.publicRequest(p)),
      devices: this.data.devices.map((d) => ({ id: d.id, name: d.name, origin: d.origin, ip: d.ip, worldId: d.worldId, userName: d.userName, createdAt: d.createdAt, lastSeen: d.lastSeen || null, expiresAt: d.expiresAt || null, rotationPending: !!d.rotateRequested })),
    };
  }

  approve(id, { days = 90 } = {}) {
    this.sweep();
    const p = this.pending.get(String(id));
    if (!p || p.status !== 'pending') return { status: 404, error: 'no such pending request (expired or already handled)' };
    const token = rand(32), devId = 'd_' + crypto.randomBytes(6).toString('hex'), t = this.now();
    const life = Number(days) > 0 ? Math.min(Number(days), 3650) : 0;
    const expiresAt = life ? new Date(t + life * 86400000).toISOString() : null;
    this.data.devices.push({ id: devId, name: p.info.deviceName, origin: p.origin || p.info.hostOrigin, ip: p.ip, worldId: p.info.worldId, userId: p.info.userId, userName: p.info.userName,
      createdAt: new Date(t).toISOString(), lastSeen: null, lifetimeDays: life, expiresAt, hash: sha(token) });
    this.save(true);
    p.status = 'approved'; p.token = token; p.deviceId = devId; p.deviceExpiresAt = expiresAt;
    this.emit('approved', { id: devId, name: p.info.deviceName, ip: p.ip, expiresAt });
    return { status: 200, deviceId: devId, expiresAt };
  }

  deny(id) {
    const p = this.pending.get(String(id));
    if (!p || p.status !== 'pending') return { status: 404, error: 'no such pending request' };
    p.status = 'denied'; this.coolUntil.set(p.ip, this.now() + this.limits.denyCooldownMs);
    this.emit('denied', this.publicRequest(p));
    return { status: 200 };
  }

  revoke(deviceId) {
    const i = this.data.devices.findIndex((d) => d.id === deviceId);
    if (i < 0) return { status: 404, error: 'no such device' };
    const [d] = this.data.devices.splice(i, 1);
    this.save(true);
    this.emit('revoked', { id: d.id, name: d.name });
    return { status: 200 };
  }

  rotate(deviceId) {   // the device receives a fresh token the next time it connects
    const d = this.data.devices.find((x) => x.id === deviceId);
    if (!d) return { status: 404, error: 'no such device' };
    d.rotateRequested = true; this.save(true);
    return { status: 200 };
  }

  // ---- connect side: validates a device token for the WebSocket hello -----------------------------------------------------------
  authenticate(deviceId, token, ip) {
    const t = this.now();
    const d = this.data.devices.find((x) => x.id === deviceId);
    const h = sha(token);
    const fail = (reason) => {
      if (!this.allow('authfail', ip, this.limits.authFailsPerMin, 60000)) return { ok: false, reason: 'rate limited', limited: true };
      return { ok: false, reason };
    };
    if ((this.hits.get('authfail|' + ip) || []).filter((x) => t - x < 60000).length >= this.limits.authFailsPerMin) return { ok: false, reason: 'rate limited', limited: true };
    if (!d) return fail('unknown device');
    const main = eq(h, d.hash), prev = d.prevHash && t < (d.prevUntil || 0) && eq(h, d.prevHash);
    if (!main && !prev) return fail('bad token');
    if (d.expiresAt && t > Date.parse(d.expiresAt)) return { ok: false, reason: 'expired' };
    d.lastSeen = new Date(t).toISOString(); d.ip = ip || d.ip;
    const out = { ok: true, device: { id: d.id, name: d.name } };
    const dueByAge = d.expiresAt && d.lifetimeDays && Date.parse(d.expiresAt) - t < this.rotateWithinMs;
    if (main && (d.rotateRequested || dueByAge)) {
      const next = rand(32);
      d.prevHash = d.hash; d.prevUntil = t + 5 * 60000; d.hash = sha(next); d.rotateRequested = false;
      if (d.lifetimeDays) d.expiresAt = new Date(t + d.lifetimeDays * 86400000).toISOString();
      out.rotate = { token: next, expiresAt: d.expiresAt };
      this.save(true);
    } else this.save();
    return out;
  }
}
