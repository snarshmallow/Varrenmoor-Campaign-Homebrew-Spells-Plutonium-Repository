// Relay-side crypto for LAN pairing and device authentication, on node:crypto (OpenSSL). The module side (module/varrenmoor-bridge/scripts/seccrypto.js)
// implements the same functions in pure JS (vendored @noble libraries) because an http:// Foundry page has no WebCrypto; foundry-bridge/module/seccrypto.test.mjs
// proves both sides produce identical keys, codes, MACs and ciphertexts. Wire values are base64url strings.
//   X25519 key agreement, HKDF-SHA256, ChaCha20-Poly1305 (12-byte nonce, 16-byte tag), HMAC-SHA256, SHA-256.
import crypto from 'node:crypto';

const te = new TextEncoder();
const toBuf = (v) => (typeof v === 'string' ? Buffer.from(te.encode(v)) : Buffer.from(v));
function frame(parts) {      // length-prefixed concatenation (same as the module)
  const bs = parts.map(toBuf); const out = [];
  for (const b of bs) { out.push(Buffer.from([(b.length >> 8) & 255, b.length & 255]), b); }
  return Buffer.concat(out);
}
export const b64u = (u8) => Buffer.from(u8).toString('base64url');
export const unb64u = (s) => new Uint8Array(Buffer.from(String(s || ''), 'base64url'));
export const randomBytes = (n) => new Uint8Array(crypto.randomBytes(n));
export const eq = (a, b) => { const x = toBuf(a), y = toBuf(b); return x.length === y.length && crypto.timingSafeEqual(x, y); };
export const sha256 = (...parts) => new Uint8Array(crypto.createHash('sha256').update(frame(parts)).digest());
export const hmac = (key, ...parts) => new Uint8Array(crypto.createHmac('sha256', toBuf(key)).update(frame(parts)).digest());

const SPKI = Buffer.from('302a300506032b656e032100', 'hex'), PKCS8 = Buffer.from('302e020100300506032b656e04220420', 'hex');
export function newKeypair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync('x25519');
  return { pk: new Uint8Array(publicKey.export({ format: 'der', type: 'spki' }).subarray(-32)), sk: privateKey };
}
// import a raw 32-byte private key (tests / known-answer vectors)
export const privateFromRaw = (raw) => crypto.createPrivateKey({ key: Buffer.concat([PKCS8, toBuf(raw)]), format: 'der', type: 'pkcs8' });
export const publicOf = (sk) => new Uint8Array(crypto.createPublicKey(sk).export({ format: 'der', type: 'spki' }).subarray(-32));
export function sharedKey(sk, peerPk, salt, info) {
  const peer = toBuf(peerPk); if (peer.length !== 32) throw new Error('bad public key');
  let shared; try { shared = crypto.diffieHellman({ privateKey: sk, publicKey: crypto.createPublicKey({ key: Buffer.concat([SPKI, peer]), format: 'der', type: 'spki' }) }); } catch { throw new Error('bad public key'); }
  if (shared.every((b) => b === 0)) throw new Error('bad public key');
  return new Uint8Array(crypto.hkdfSync('sha256', shared, toBuf(salt), toBuf(info), 32));
}
export const hkdf = (ikm, salt, info, len = 32) => new Uint8Array(crypto.hkdfSync('sha256', toBuf(ikm), toBuf(salt), toBuf(info), len));
export function seal(key, plain, aad) {
  const nonce = crypto.randomBytes(12), c = crypto.createCipheriv('chacha20-poly1305', toBuf(key), nonce, { authTagLength: 16 });
  c.setAAD(toBuf(aad || ''));
  const ct = Buffer.concat([c.update(toBuf(plain)), c.final(), c.getAuthTag()]);
  return Buffer.concat([nonce, ct]).toString('base64url');
}
export function open(key, sealed, aad) {
  try {
    const u = Buffer.from(String(sealed || ''), 'base64url'); if (u.length < 28) return null;
    const d = crypto.createDecipheriv('chacha20-poly1305', toBuf(key), u.subarray(0, 12), { authTagLength: 16 });
    d.setAAD(toBuf(aad || '')); d.setAuthTag(u.subarray(u.length - 16));
    return new Uint8Array(Buffer.concat([d.update(u.subarray(12, u.length - 16)), d.final()]));
  } catch { return null; }
}
export const sealJson = (key, obj, aad) => seal(key, JSON.stringify(obj), aad);
export const openJson = (key, sealed, aad) => { const p = open(key, sealed, aad); if (!p) return null; try { return JSON.parse(Buffer.from(p).toString('utf8')); } catch { return null; } };

// ---- pairing protocol pieces (identical to the module; see README "Pairing and its threat model") ----
export const commitment = (pk, nonce) => b64u(sha256('vb-commit-v1', pk, nonce));
export function sas(pk, relayPk, nonce, relayNonce) {
  const h = sha256('vb-sas-v1', pk, relayPk, nonce, relayNonce), n = ((h[0] << 24) | (h[1] << 16) | (h[2] << 8) | h[3]) >>> 0;
  const s = String(n % 1000000).padStart(6, '0'); return s.slice(0, 3) + ' ' + s.slice(3);
}
export const pairKey = (sk, peerPk, pk, relayPk, nonce, relayNonce) => sharedKey(sk, peerPk, frame([nonce, relayNonce]), frame(['vb-pair-v1', pk, relayPk]));
export const clientMac = (secret, deviceId, cn, rn) => b64u(hmac(secret, 'vb-ws-client-v1', deviceId, cn, rn));
export const relayMac = (secret, deviceId, cn, rn) => b64u(hmac(secret, 'vb-ws-relay-v1', deviceId, cn, rn));
export const rotationKey = (secret, deviceId, cn, rn) => hkdf(secret, frame([cn, rn]), frame(['vb-ws-rotate-v1', deviceId]));
