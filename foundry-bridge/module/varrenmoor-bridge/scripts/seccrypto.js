// Crypto for LAN pairing and device authentication, module side (0.5.0). Pure JS on purpose: the Foundry GM page is served over plain http://<LAN host>:30000,
// which is NOT a secure context, so WebCrypto (crypto.subtle) does not exist there. Primitives come from the vendored, audited @noble libraries
// (scripts/vendor/noble-bundle.js, MIT, no network access); randomness from crypto.getRandomValues (available on http pages).
// The relay (relay/seccrypto.js) implements the same functions with node:crypto; foundry-bridge/module/seccrypto.test.mjs proves they interoperate.
//   X25519 key agreement, HKDF-SHA256, ChaCha20-Poly1305 (12-byte nonce, 16-byte tag), HMAC-SHA256, SHA-256. All wire values are base64url strings.
import { x25519, chacha20poly1305, sha256 as nobleSha256, hmac as nobleHmac, hkdf as nobleHkdf } from './vendor/noble-bundle.js';

const te = new TextEncoder(), td = new TextDecoder();
const toBytes = (v) => (typeof v === 'string' ? te.encode(v) : v instanceof Uint8Array ? v : new Uint8Array(v));
// length-prefixed concatenation so ("ab","c") and ("a","bc") hash differently
function frame(parts) {
  const bs = parts.map(toBytes); let n = 0; for (const b of bs) n += 2 + b.length;
  const out = new Uint8Array(n); let o = 0;
  for (const b of bs) { out[o++] = (b.length >> 8) & 255; out[o++] = b.length & 255; out.set(b, o); o += b.length; }
  return out;
}
export const b64u = (u8) => { let s = ''; for (const c of u8) s += String.fromCharCode(c); return btoa(s).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''); };
export const unb64u = (s) => { const t = String(s || '').replace(/-/g, '+').replace(/_/g, '/'); const bin = atob(t + '==='.slice((t.length + 3) % 4)); const u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return u; };
export const randomBytes = (n) => { const u = new Uint8Array(n); globalThis.crypto.getRandomValues(u); return u; };
export const eq = (a, b) => { a = toBytes(a); b = toBytes(b); if (a.length !== b.length) return false; let d = 0; for (let i = 0; i < a.length; i++) d |= a[i] ^ b[i]; return d === 0; };
export const sha256 = (...parts) => nobleSha256(frame(parts));
export const hmac = (key, ...parts) => nobleHmac(nobleSha256, toBytes(key), frame(parts));

export function newKeypair() { const sk = randomBytes(32); return { sk, pk: x25519.getPublicKey(sk) }; }
// X25519 + HKDF-SHA256. Refuses an all-zero shared secret (low-order peer key).
export function sharedKey(sk, peerPk, salt, info) {
  const peer = toBytes(peerPk); if (peer.length !== 32) throw new Error('bad public key');
  const shared = x25519.getSharedSecret(sk, peer);
  if (shared.every((b) => b === 0)) throw new Error('bad public key');
  return nobleHkdf(nobleSha256, shared, toBytes(salt), toBytes(info), 32);
}
export const hkdf = (ikm, salt, info, len = 32) => nobleHkdf(nobleSha256, toBytes(ikm), toBytes(salt), toBytes(info), len);
// seal -> base64url(nonce12 || ciphertext || tag16); open -> Uint8Array or null (any failure, never throws)
export function seal(key, plain, aad) {
  const nonce = randomBytes(12), ct = chacha20poly1305(key, nonce, toBytes(aad || '')).encrypt(toBytes(plain));
  const out = new Uint8Array(12 + ct.length); out.set(nonce); out.set(ct, 12); return b64u(out);
}
export function open(key, sealed, aad) {
  try { const u = unb64u(sealed); if (u.length < 28) return null; return chacha20poly1305(key, u.slice(0, 12), toBytes(aad || '')).decrypt(u.slice(12)); } catch { return null; }
}
export const sealJson = (key, obj, aad) => seal(key, JSON.stringify(obj), aad);
export const openJson = (key, sealed, aad) => { const p = open(key, sealed, aad); if (!p) return null; try { return JSON.parse(td.decode(p)); } catch { return null; } };

// ---- pairing protocol pieces (see foundry-bridge/README.md "Pairing and its threat model") ----
// The device commits to its public key + nonce BEFORE it sees the relay's, then reveals. With the commitment an attacker in the middle cannot grind keys until
// the 6-digit codes on the two sides agree: it must fix its keys on each side before it learns the other side's values.
export const commitment = (pk, nonce) => b64u(sha256('vb-commit-v1', pk, nonce));
// Short authentication string: 6 digits from a hash of BOTH public keys and BOTH nonces, "123 456".
export function sas(pk, relayPk, nonce, relayNonce) {
  const h = sha256('vb-sas-v1', pk, relayPk, nonce, relayNonce), n = ((h[0] << 24) | (h[1] << 16) | (h[2] << 8) | h[3]) >>> 0;
  const s = String(n % 1000000).padStart(6, '0'); return s.slice(0, 3) + ' ' + s.slice(3);
}
// sk = our private key, peerPk = the other side's public key; pk / relayPk = the device's / the relay's public key (so both sides bind the same transcript)
export const pairKey = (sk, peerPk, pk, relayPk, nonce, relayNonce) => sharedKey(sk, peerPk, frame([nonce, relayNonce]), frame(['vb-pair-v1', pk, relayPk]));

// ---- device authentication on the WebSocket: HMAC challenge-response keyed by the per-device secret; the secret itself is never sent ----
export const clientMac = (secret, deviceId, cn, rn) => b64u(hmac(secret, 'vb-ws-client-v1', deviceId, cn, rn));
export const relayMac = (secret, deviceId, cn, rn) => b64u(hmac(secret, 'vb-ws-relay-v1', deviceId, cn, rn));
export const rotationKey = (secret, deviceId, cn, rn) => hkdf(secret, frame([cn, rn]), frame(['vb-ws-rotate-v1', deviceId]));

// Known-answer self-test: the expected values below were produced independently with Node's OpenSSL (relay/seccrypto.js). Returns true, or throws when the
// vendored library is broken or has been tampered with; the module refuses to pair in that case.
const KAT = {
  pkA: 'pOCSkrZRwni5dyxWn1-puxPZBrRqtoyd-dwrRAn4ogk', pkB: 'zo060cy2M-x7cMF4FKXHbs0CloUFDTRHRboFhw5YfVk', key: 'ZKEJjeMHotLxsHjEmpeFDhLWT4WJvAZS7xCqnOi8y38',
  sas: '543 183', commit: 'cdzAOHJaWOctoByhNUQlQVPFJdVdtJxDkxPrXufq9mc', mac: 'liwXozrFi6noho0Q6wtPWRAn_2aML01v4uLqIGfi86o',
  hk: 'SzpnzHO8B0zaz72rJ5iBydaR5U_kl5PiC9LEUBbp5rLbNqJYeJ56Mig6', sealed: 'Em2295L_u_7wQ7ueN58ZDluj1ag3FvqgK6DBmamXEMb8f8MTdSj-iF6nWEA',
};
export function selfTest() {
  const a = new Uint8Array(32).fill(1), b = new Uint8Array(32).fill(2), n = new Uint8Array(16).fill(3), rn = new Uint8Array(16).fill(4);
  const pkA = x25519.getPublicKey(a), pkB = x25519.getPublicKey(b);
  const key = pairKey(a, pkB, pkA, pkB, n, rn);
  const bad = [];
  if (b64u(pkA) !== KAT.pkA || b64u(pkB) !== KAT.pkB) bad.push('x25519');
  if (b64u(key) !== KAT.key) bad.push('key agreement');
  if (sas(pkA, pkB, n, rn) !== KAT.sas) bad.push('code');
  if (commitment(pkA, n) !== KAT.commit) bad.push('commitment');
  if (clientMac(key, 'd_x', 'AAAA', 'BBBB') !== KAT.mac) bad.push('hmac');
  if (b64u(hkdf(a, b, 'info', 42)) !== KAT.hk) bad.push('hkdf');
  const o = open(key, KAT.sealed, 'aad-1');
  if (!o || td.decode(o) !== 'hello varrenmoor' || open(key, KAT.sealed, 'aad-2')) bad.push('chacha20-poly1305');
  if (bad.length) throw new Error('crypto self-test failed (' + bad.join(', ') + ')');
  return true;
}
