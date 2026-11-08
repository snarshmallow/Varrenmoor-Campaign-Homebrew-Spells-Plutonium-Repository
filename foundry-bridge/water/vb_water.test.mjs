// vb_water.js without Foundry: runs the script body against a fake game and, when the 3D Canvas module's own three.js (r132) is reachable
// (\\VEGA share, read only), patches a real MeshStandardMaterial and checks that every injection point exists in the real shader chunks.
//   node --test foundry-bridge/water/vb_water.test.mjs         (env THREE_PATH = path of levels-3d-preview/scripts/lib/three.module.js to override)
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const body = fs.readFileSync(path.join(HERE, 'vb_water.js'), 'utf8');
const THREE_PATH = process.env.THREE_PATH || '//VEGA/C/FoundryVTT resources/Data/modules/levels-3d-preview/scripts/lib/three.module.js';
const have = fs.existsSync(THREE_PATH);

test('body compiles as a function body and does nothing without a model', () => {
  const fn = new Function('delta', body);
  globalThis.game = { Levels3DPreview: null };
  assert.doesNotThrow(() => fn.call({ isObject3D: false }, 0));
  assert.doesNotThrow(() => fn.call(undefined, 0));
});

test('stays small enough to store in every water tile', () => {
  const stripped = body.split('\n').filter((l) => l.trim() && !l.trim().startsWith('//')).join('\n');
  assert.ok(stripped.length < 12000, `script is ${stripped.length} bytes`);
});

test('patches a real r132 physical material (needs the module three.js)', { skip: !have && 'levels-3d-preview three.module.js not reachable' }, async () => {
  const dir = fs.mkdtempSync(path.join(process.env.TEMP || '/tmp', 'vbw-'));
  const copy = path.join(dir, 'three132.mjs');
  fs.copyFileSync(THREE_PATH, copy);
  const T = await import(pathToFileURL(copy).href);
  assert.equal(T.REVISION, '132');
  globalThis.game = { Levels3DPreview: { THREE: T, tiles: {} } };
  globalThis.performance = globalThis.performance || { now: () => Date.now() };
  const root = new T.Group();
  const geo = new T.BufferGeometry();
  geo.setAttribute('position', new T.BufferAttribute(new Float32Array(9), 3));
  const mesh = new T.Mesh(geo, new T.MeshStandardMaterial({ name: 'VB_water_river' }));
  const other = new T.Mesh(geo, new T.MeshStandardMaterial({ name: 'mat_terrain' }));
  root.add(mesh); root.add(other);
  const child = new T.Group(); root.add(child);
  const fn = new Function('delta', body);
  fn.call(child, 0);
  const S = root.userData.vbWaterState;
  assert.ok(S.ok && S.meshes.length === 1, 'only the VB_water_ mesh is patched');
  assert.notEqual(mesh.material, undefined);
  assert.equal(other.material.onBeforeCompile.toString(), new T.MeshStandardMaterial().onBeforeCompile.toString(), 'other materials are untouched');
  assert.equal(mesh.material.transparent, true);
  assert.equal(mesh.material.depthWrite, false);
  const sh = { uniforms: {}, vertexShader: T.ShaderLib.physical.vertexShader, fragmentShader: T.ShaderLib.physical.fragmentShader };
  mesh.material.onBeforeCompile(sh);
  for (const u of ['vbTime', 'vbMode', 'vbP0', 'vbP1', 'vbShallow', 'vbDeep']) assert.ok(sh.uniforms[u], u);
  const resolve = (s) => { let prev; do { prev = s; s = s.replace(/^[ \t]*#include +<([\w\d./]+)>/gm, (_, n) => T.ShaderChunk[n]); } while (s !== prev); return s; };
  const vs = resolve(sh.vertexShader), fs_ = resolve(sh.fragmentShader);
  for (const k of ['attribute vec4 _vbwater', 'vbUv = uv; vbData = _vbwater;']) assert.ok(vs.includes(k), k);
  for (const k of ['vec3 vbPerturb(', 'vbPattern(', 'diffuseColor.rgb = mix(vbCol', 'normal = vbPerturb(-vViewPosition', 'diffuseColor.a = clamp(mix(vbAlpha', 'roughnessFactor = mix(roughnessFactor']) assert.ok(fs_.includes(k), k);
  // balanced braces in what we injected
  assert.equal((fs_.match(/{/g) || []).length, (fs_.match(/}/g) || []).length);
  assert.equal((vs.match(/{/g) || []).length, (vs.match(/}/g) || []).length);
  // parameters: tile flag -> uniforms, force wins over the material preset
  S.tile = { tile: { document: { flags: { varrenmoor: { water: { force: 'ocean', presets: {
    river: { flow_speed: 1, mode: 'flow' },
    ocean: { flow_speed: 2, wave_height: 1, wave_scale: 8, foam: 0.6, transparency: 0.35, depth_tint: 0.8, wind_dir: 270, mode: 'wind', slope_speed: 0, shallow_color: '#4f9bb0', deep_color: '#0f3a63' } } } } } } } };
  S.frame = 29;
  fn.call(child, 0);
  const U = S.meshes[0].U;
  assert.equal(U.vbMode.value, 1);
  assert.ok(Math.abs(U.vbP0.value.x - 0.2) < 1e-6 && Math.abs(U.vbP0.value.z - 3.2) < 1e-6);
  assert.ok(Math.abs(U.vbP1.value.w - Math.PI * 1.5) < 1e-6);
  const t0 = U.vbTime.value;
  S.t0 -= 1000;
  fn.call(child, 0);
  assert.ok(U.vbTime.value >= t0 + 0.9, 'time advances every frame');
  // bad numbers fall back to defaults instead of NaN
  S.tile.tile.document.flags.varrenmoor.water.presets.ocean.flow_speed = 'x';
  S.frame = 29;
  fn.call(child, 0);
  assert.ok(Number.isFinite(U.vbP0.value.x));
});
