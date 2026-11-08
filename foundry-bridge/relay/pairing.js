// LAN device pairing for the Varrenmoor relay. Pure logic (no HTTP), so it is unit-testable; server.js exposes it over HTTP/WebSocket.
//
// Flow (protocol 2, encrypted handshake): the device (the Foundry module in a GM browser) sends a COMMITMENT to its ephemeral X25519 public key + nonce;
// the relay answers with its own ephemeral public key + nonce; the device then reveals its key (and its description, sealed under the key both sides now derive).
// Both sides compute the same 6-digit code from both public keys and both nonces (short authentication string); the human approves only if the device screen
// and the approver (panel / relay window) show the same code. On approval the relay creates a per-device secret and hands it over ONCE, sealed
// (ChaCha20-Poly1305) under the handshake key, so a passive sniffer never sees it. Afterwards the device authenticates each WebSocket with an HMAC
// challenge-response keyed by that secret (the secret is never sent again). The relay keeps the device secrets in paired-devices.json (git-ignored, mode 0600).
// Nothing here ever logs or returns a secret except that one sealed hand-over.
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { EventEmitter } from 'node:events';
import * as X from './seccrypto.js';

const sha = (s) => crypto.createHash('sha256').update(String(s)).digest('hex');
const eq = X.eq;
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
  // file: where paired devices + settings are kept (omit = pairing impossible). enabled / autoRequest: initial state when the file has no saved setting (default on when a file is given).
  constructor({ file, enabled, autoRequest, now = () => Date.now(), pendingTtlMs = 120000, rotateWithinDays = 14, limits = {} } = {}) {
    super();
    this.file = file || null; this.now = now; this.pendingTtlMs = pendingTtlMs; this.rotateWithinMs = rotateWithinDays * 86400000;
    this.limits = { requestsPerWindow: 5, requestWindowMs: 600000, maxPending: 5, maxPendingPerIp: 2, denyCooldownMs: 60000, pollsPerMin: 90, authFailsPerMin: 10, ...limits };
    this.pending = new Map();      // requestId -> { id, secretHash, ip, origin, commit, rsk, rpk, rn, key, code, info, createdAt, expiresAt, status, sealed?, deviceId? }
    this.hits = new Map();         // "kind|ip" -> [timestamps]
    this.coolUntil = new Map();    // ip -> ms
    this.data = { version: 2, relayId: 'r_' + crypto.randomBytes(6).toString('hex'), devices: [], settings: {} };
    this.initial = { enabled: enabled !== false, autoRequest: autoRequest !== false };
    this.lastSave = 0; this.dirty = false;
    this.load();
  }

  get canEnable() { return !!this.file; }
  get enabled() { return !!this.file && (this.data.settings.enabled ?? this.initial.enabled) !== false; }
  get autoRequest() { return (this.data.settings.autoRequest ?? this.initial.autoRequest) !== false; }
  get relayId() { return this.data.relayId; }
  // runtime switch (admin endpoint / panel). Persisted in the pairing file so it survives a relay restart.
  configure({ enabled, autoRequest } = {}) {
    if (!this.file) return { status: 409, error: 'this relay was started without a pairing file, so pairing cannot be switched on; restart it once with the current start.bat' };
    if (typeof enabled === 'boolean') this.data.settings.enabled = enabled;
    if (typeof autoRequest === 'boolean') this.data.settings.autoRequest = autoRequest;
    this.save(true); this.emit('config', { enabled: this.enabled, autoRequest: this.autoRequest });
    return { status: 200, enabled: this.enabled, autoRequest: this.autoRequest };
  }

  load() {
    if (!this.file) return;
    try {
      const d = JSON.parse(fs.readFileSync(this.file, 'utf8'));
      // protocol-1 devices (hashed bearer token) cannot authenticate with challenge-response: dropped, they pair again
      if (d && Array.isArray(d.devices)) this.data = { version: 2, relayId: d.relayId || this.data.relayId, devices: d.devices.filter((x) => x && x.secret), settings: d.settings && typeof d.settings === 'object' ? d.settings : {} };
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
      if ((p.status === 'pending' || p.status === 'committed') && t > p.expiresAt) { const was = p.status; p.status = 'expired'; if (was === 'pending') this.emit('expired', this.publicRequest(p)); }
      if (t > p.expiresAt + 5 * 60000) this.pending.delete(id);   // keep finished ones a little so polls can read the outcome
    }
  }

  publicRequest(p) {
    return { id: p.id, code: p.code, ip: p.ip, origin: p.origin, name: p.info.deviceName, claimedOrigin: p.info.hostOrigin, originMismatch: !!(p.origin && p.info.hostOrigin && p.origin !== p.info.hostOrigin),
      worldId: p.info.worldId, userId: p.info.userId, userName: p.info.userName, createdAt: new Date(p.createdAt).toISOString(), expiresAt: new Date(p.expiresAt).toISOString(), status: p.status };
  }

  // ---- device side ------------------------------------------------------------------------------------------------------------
  // step 1: the device sends commit = SHA-256 of (its public key, its nonce); the relay answers with its own ephemeral key + nonce.
  request({ ip, origin = '', commit }) {
    if (!this.enabled) return { status: 404, error: 'pairing is not enabled on this relay' };
    this.sweep();
    const t = this.now();
    if (typeof commit !== 'string' || X.unb64u(commit).length !== 32) return { status: 400, error: 'protocol mismatch: update the Foundry module (0.5.0 or newer) on the Foundry PC' };
    if ((this.coolUntil.get(ip) || 0) > t) return { status: 429, error: 'a request from this address was denied a moment ago; wait a minute' };
    if (!this.allow('request', ip, this.limits.requestsPerWindow, this.limits.requestWindowMs)) return { status: 429, error: 'too many pairing requests from this address; try again later' };
    const live = [...this.pending.values()].filter((p) => p.status === 'pending' || p.status === 'committed');
    if (live.length >= this.limits.maxPending) return { status: 429, error: 'too many pairing requests are already waiting for approval' };
    if (live.filter((p) => p.ip === ip).length >= this.limits.maxPendingPerIp) return { status: 429, error: 'this address already has pairing requests waiting' };
    const secret = rand(32), id = 'p_' + crypto.randomBytes(6).toString('hex'), kp = X.newKeypair(), rn = X.randomBytes(16);
    this.pending.set(id, { id, secretHash: sha(secret), ip, origin: clip(origin, 120), createdAt: t, expiresAt: t + this.pendingTtlMs, status: 'committed', commit, rsk: kp.sk, rpk: kp.pk, rn, info: {} });
    return { status: 200, requestId: id, pollSecret: secret, relayPk: X.b64u(kp.pk), relayNonce: X.b64u(rn), expiresAt: new Date(t + this.pendingTtlMs).toISOString() };
  }

  // step 2: the device reveals its key and nonce (must match the commitment) and sends its description sealed under the handshake key. Only now does the human see it.
  reveal({ requestId, pollSecret, pk, nonce, info, ip }) {
    if (!this.enabled) return { status: 404, error: 'pairing is not enabled on this relay' };
    this.sweep();
    const p = this.pending.get(String(requestId));
    if (!p || !eq(sha(pollSecret), p.secretHash) || p.status !== 'committed' || p.ip !== ip) return { status: 404, error: 'no such pairing request (expired or already handled)' };
    let pkB, nB;
    try { pkB = X.unb64u(pk); nB = X.unb64u(nonce); } catch { pkB = new Uint8Array(0); }
    if (pkB.length !== 32 || !nB || nB.length < 16 || X.commitment(pkB, nB) !== p.commit) { p.status = 'failed'; return { status: 400, error: 'the revealed key does not match the commitment' }; }
    let key; try { key = X.pairKey(p.rsk, pkB, pkB, p.rpk, nB, p.rn); } catch { p.status = 'failed'; return { status: 400, error: 'bad public key' }; }
    const meta = X.openJson(key, info, 'vb-info|' + p.id);
    if (!meta || typeof meta !== 'object') { p.status = 'failed'; return { status: 400, error: 'could not decrypt the device description' }; }
    p.key = key; p.code = X.sas(pkB, p.rpk, nB, p.rn).replace(' ', '');
    p.info = { deviceName: clip(meta.deviceName || 'unnamed device', 60), worldId: clip(meta.worldId, 60), userId: clip(meta.userId, 40), userName: clip(meta.userName, 60), hostOrigin: clip(meta.hostOrigin, 120), clientId: clip(meta.clientId, 40) };
    // one live request per browser: an older waiting request from the same browser id is superseded (its code is no longer valid and drops out of the approver's list)
    if (p.info.clientId) for (const o of this.pending.values()) if (o !== p && o.info.clientId === p.info.clientId && (o.status === 'pending' || o.status === 'committed')) { o.status = 'expired'; delete o.key; }
    p.status = 'pending'; delete p.rsk;
    this.emit('request', this.publicRequest(p));
    return { status: 200 };
  }

  // the device gave up (dialog cancelled): its request leaves the approver's list at once
  cancel(requestId, pollSecret) {
    const p = this.pending.get(String(requestId));
    if (!p || !eq(sha(pollSecret), p.secretHash)) return { status: 200 };
    if (p.status === 'pending' || p.status === 'committed') { p.status = 'expired'; delete p.key; }
    return { status: 200 };
  }

  poll(requestId, pollSecret, ip) {
    if (!this.allow('poll', ip, this.limits.pollsPerMin, 60000)) return { status: 429, error: 'polling too fast' };
    this.sweep();
    const p = this.pending.get(String(requestId));
    if (!p || !eq(sha(pollSecret), p.secretHash)) return { status: 200, state: 'unknown' };
    if (p.status === 'approved' && p.sealed) {
      const out = { status: 200, state: 'approved', deviceId: p.deviceId, sealed: p.sealed, relayId: this.relayId };
      delete p.sealed; delete p.key; p.status = 'delivered';       // hand the secret over exactly once
      return out;
    }
    return { status: 200, state: p.status === 'committed' ? 'pending' : p.status === 'failed' ? 'denied' : p.status };       // pending | denied | expired | delivered
  }

  // ---- admin side (human) -----------------------------------------------------------------------------------------------------
  list() {
    this.sweep();
    return {
      relayId: this.relayId, enabled: this.enabled, autoRequest: this.autoRequest, canEnable: this.canEnable,
      pending: [...this.pending.values()].filter((p) => p.status === 'pending').map((p) => this.publicRequest(p)),
      devices: this.data.devices.map((d) => ({ id: d.id, clientId: d.clientId || '', name: d.name, origin: d.origin, ip: d.ip, worldId: d.worldId, userName: d.userName, createdAt: d.createdAt, lastSeen: d.lastSeen || null, expiresAt: d.expiresAt || null, rotationPending: !!d.rotateRequested })),
    };
  }

  approve(id, { days = 90 } = {}) {
    this.sweep();
    const p = this.pending.get(String(id));
    if (!p || p.status !== 'pending') return { status: 404, error: 'no such pending request (expired or already handled)' };
    const secret = X.randomBytes(32), devId = 'd_' + crypto.randomBytes(6).toString('hex'), t = this.now();
    const life = Number(days) > 0 ? Math.min(Number(days), 3650) : 0;
    const expiresAt = life ? new Date(t + life * 86400000).toISOString() : null;
    // one record per browser: approving again replaces the earlier record of the same browser (same browser id; for older modules without one: same name, user, world and origin)
    const same = (d) => (p.info.clientId && d.clientId === p.info.clientId) || (!d.clientId && !p.info.clientId && d.name === p.info.deviceName && d.userId === p.info.userId && d.worldId === p.info.worldId && d.origin === (p.origin || p.info.hostOrigin));
    const replaced = this.data.devices.filter(same); this.data.devices = this.data.devices.filter((d) => !same(d));
    for (const d of replaced) this.emit('revoked', { id: d.id, name: d.name, replaced: true });
    this.data.devices.push({ id: devId, clientId: p.info.clientId || '', name: p.info.deviceName, origin: p.origin || p.info.hostOrigin, ip: p.ip, worldId: p.info.worldId, userId: p.info.userId, userName: p.info.userName,
      createdAt: new Date(t).toISOString(), lastSeen: null, lifetimeDays: life, expiresAt, secret: X.b64u(secret) });
    this.save(true);
    p.sealed = X.sealJson(p.key, { secret: X.b64u(secret), expiresAt, relayId: this.relayId }, 'vb-dev|' + p.id + '|' + devId);
    p.status = 'approved'; p.deviceId = devId;
    this.emit('approved', { id: devId, name: p.info.deviceName, ip: p.ip, expiresAt });
    return { status: 200, deviceId: devId, expiresAt };
  }

  deny(id) {
    const p = this.pending.get(String(id));
    if (!p || p.status !== 'pending') return { status: 404, error: 'no such pending request' };
    p.status = 'denied'; delete p.key; this.coolUntil.set(p.ip, this.now() + this.limits.denyCooldownMs);
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

  rotate(deviceId) {   // the device receives a fresh secret (sealed) the next time it connects
    const d = this.data.devices.find((x) => x.id === deviceId);
    if (!d) return { status: 404, error: 'no such device' };
    d.rotateRequested = true; this.save(true);
    return { status: 200 };
  }

  // ---- connect side: HMAC challenge-response for the WebSocket ---------------------------------------------------------------
  // hello {deviceId, cn} -> challenge {rn}; auth {mac} -> welcome {proof, rotate?}. The secret is never on the wire after pairing.
  authenticate(deviceId, cn, rn, mac, ip) {
    const t = this.now();
    if ((this.hits.get('authfail|' + ip) || []).filter((x) => t - x < 60000).length >= this.limits.authFailsPerMin) return { ok: false, reason: 'rate limited', limited: true };
    const fail = (reason) => { this.allow('authfail', ip, this.limits.authFailsPerMin, 60000); return { ok: false, reason }; };
    const d = this.data.devices.find((x) => x.id === deviceId);
    if (!d) return fail('unknown device');
    const main = eq(mac, X.clientMac(X.unb64u(d.secret), d.id, cn, rn));
    const prev = !main && d.prevSecret && t < (d.prevUntil || 0) && eq(mac, X.clientMac(X.unb64u(d.prevSecret), d.id, cn, rn));
    if (!main && !prev) return fail('bad credentials');
    if (d.expiresAt && t > Date.parse(d.expiresAt)) return { ok: false, reason: 'expired' };
    d.lastSeen = new Date(t).toISOString(); d.ip = ip || d.ip;
    const used = X.unb64u(prev ? d.prevSecret : d.secret);
    const out = { ok: true, device: { id: d.id, name: d.name }, proof: X.relayMac(used, d.id, cn, rn) };
    const dueByAge = d.expiresAt && d.lifetimeDays && Date.parse(d.expiresAt) - t < this.rotateWithinMs;
    if (main && (d.rotateRequested || dueByAge)) {
      const next = X.randomBytes(32);
      d.prevSecret = d.secret; d.prevUntil = t + 5 * 60000; d.secret = X.b64u(next); d.rotateRequested = false;
      if (d.lifetimeDays) d.expiresAt = new Date(t + d.lifetimeDays * 86400000).toISOString();
      out.rotate = { sealed: X.sealJson(X.rotationKey(used, d.id, cn, rn), { secret: d.secret, expiresAt: d.expiresAt }, 'vb-rot|' + d.id), expiresAt: d.expiresAt };
      this.save(true);
    } else this.save();
    return out;
  }
}
