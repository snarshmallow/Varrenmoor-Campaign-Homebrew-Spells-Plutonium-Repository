// The module's pure-JS crypto (vendored @noble) against the relay's node:crypto implementation: both directions, known-answer self-test, tamper checks.
//   node --test foundry-bridge/module/seccrypto.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
import * as R from '../relay/seccrypto.js';

const here = path.dirname(fileURLToPath(import.meta.url));
// the module folder has no package.json (Foundry serves the files as ES modules); copy it to a temp dir marked as ESM for Node
export async function loadModuleScripts() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'vmodsc-'));
  fs.cpSync(path.join(here, 'varrenmoor-bridge', 'scripts'), dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'package.json'), '{"type":"module"}');
  return { dir, M: await import(pathToFileURL(path.join(dir, 'seccrypto.js')).href), pairing: pathToFileURL(path.join(dir, 'pairing.js')).href };
}

test('known-answer self-test passes; a tampered library fails it', async () => {
  const { dir, M } = await loadModuleScripts();
  assert.equal(M.selfTest(), true);
  // a library whose output differs from the known answers (simulated by editing the expected code) must make the self-test throw
  const f = path.join(dir, 'seccrypto-bad.js');
  fs.writeFileSync(f, fs.readFileSync(path.join(dir, 'seccrypto.js'), 'utf8').replace("sas: '543 183'", "sas: '000 000'"));
  const bad = await import(pathToFileURL(f).href);
  assert.throws(() => bad.selfTest(), /self-test failed \(code\)/);
});

test('module (pure JS) and relay (node:crypto) agree: keys, shared key, code, commitment, MACs, AEAD both ways', async () => {
  const { M } = await loadModuleScripts();
  for (let i = 0; i < 5; i++) {
    const dev = M.newKeypair(), rel = R.newKeypair();
    assert.deepEqual([...R.publicOf(rel.sk)], [...rel.pk]);
    const n = M.randomBytes(16), rn = R.randomBytes(16);
    const kDev = M.pairKey(dev.sk, rel.pk, dev.pk, rel.pk, n, rn), kRel = R.pairKey(rel.sk, dev.pk, dev.pk, rel.pk, n, rn);
    assert.equal(M.b64u(kDev), R.b64u(kRel), 'same session key');
    assert.equal(M.sas(dev.pk, rel.pk, n, rn), R.sas(dev.pk, rel.pk, n, rn), 'same confirmation code');
    assert.match(M.sas(dev.pk, rel.pk, n, rn), /^\d{3} \d{3}$/);
    assert.equal(M.commitment(dev.pk, n), R.commitment(dev.pk, n));
    // module seals, relay opens; relay seals, module opens; wrong aad / wrong key / bit flip fail
    const s1 = M.sealJson(kDev, { secret: 'x', n: i }, 'aad'); assert.deepEqual(R.openJson(kRel, s1, 'aad'), { secret: 'x', n: i });
    const s2 = R.sealJson(kRel, { secret: 'y', n: i }, 'aad'); assert.deepEqual(M.openJson(kDev, s2, 'aad'), { secret: 'y', n: i });
    assert.equal(R.openJson(kRel, s1, 'other'), null); assert.equal(M.openJson(kDev, s2, 'other'), null);
    const flipped = s1.slice(0, 20) + (s1[20] === 'A' ? 'B' : 'A') + s1.slice(21);
    assert.equal(R.openJson(kRel, flipped, 'aad'), null); assert.equal(M.openJson(M.randomBytes(32), s1, 'aad'), null);
    assert.equal(M.clientMac(kDev, 'd_1', 'cn', 'rn'), R.clientMac(kRel, 'd_1', 'cn', 'rn'));
    assert.equal(M.b64u(M.rotationKey(kDev, 'd_1', 'cn', 'rn')), R.b64u(R.rotationKey(kRel, 'd_1', 'cn', 'rn')));
    assert.notEqual(M.clientMac(kDev, 'd_1', 'cn', 'rn'), M.relayMac(kDev, 'd_1', 'cn', 'rn'), 'the two directions use different labels');
  }
  assert.throws(() => M.sharedKey(M.randomBytes(32), new Uint8Array(32), new Uint8Array(1), 'x'), /bad public key|invalid/, 'all-zero peer key is refused (module)');
  assert.throws(() => R.sharedKey(R.newKeypair().sk, new Uint8Array(32), new Uint8Array(1), 'x'), /bad public key/, 'all-zero peer key is refused (relay)');
});

test('man in the middle: swapped keys give different codes on the two sides', async () => {
  const { M } = await loadModuleScripts();
  const dev = M.newKeypair(), rel = R.newKeypair(), mitm1 = M.newKeypair(), mitm2 = M.newKeypair();
  const n = M.randomBytes(16), rn = R.randomBytes(16);
  const deviceSees = M.sas(dev.pk, mitm1.pk, n, rn), relaySees = R.sas(mitm2.pk, rel.pk, n, rn);
  assert.notEqual(deviceSees, relaySees);
});
