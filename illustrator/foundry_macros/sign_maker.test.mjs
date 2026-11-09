// Pure functions of sign_maker.js without Foundry: text wrapping / fitting, flag schema, texture sizing, tile data, wall rotation, and the tile's onAnimation script on a fake THREE.
//   node --test illustrator/foundry_macros/sign_maker.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const body = fs.readFileSync(path.join(HERE, 'sign_maker.js'), 'utf8');
const presets = JSON.parse(fs.readFileSync(path.join(HERE, '..', 'presets', 'signs', 'styles.json'), 'utf8'));
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

const pan = (w, h, m) => ({ w, h, safe: [m / w, m / h, 1 - m / w, 1 - m / h], px: h < w ? [1024, Math.round((1024 * h) / w / 8) * 8] : [Math.round((1024 * w) / h / 8) * 8, 1024] });
const styles = {
  street_post: { label: 'Post', kind: 'street', mount: 'ground', file: 'street_post_x.glb', size_m: [0.772, 0.182, 2.596], arms: 0, outward: null, mount_ft: 0, panels: { VB_sign_f: pan(0.76, 0.2, 0.03), VB_sign_b: pan(0.76, 0.2, 0.03) } },
  street_wall: { label: 'Wall', kind: 'street', mount: 'wall', file: 'street_wall_x.glb', size_m: [0.716, 0.051, 0.256], arms: 0, outward: [0, 1], mount_ft: 7, panels: { VB_sign_f: pan(0.7, 0.24, 0.034) } },
  fingerpost_2: { label: 'Finger', kind: 'street', mount: 'ground', file: 'fp2_x.glb', size_m: [1.032, 0.164, 3.214], arms: 2, outward: null, mount_ft: 0,
    panels: { VB_sign_a1f: { ...pan(0.95, 0.2, 0), safe: [0.12, 0.1, 0.97, 0.9] }, VB_sign_a1b: { ...pan(0.95, 0.2, 0), safe: [0.03, 0.1, 0.88, 0.9] }, VB_sign_a2f: { ...pan(0.95, 0.2, 0), safe: [0.12, 0.1, 0.97, 0.9] }, VB_sign_a2b: { ...pan(0.95, 0.2, 0), safe: [0.03, 0.1, 0.88, 0.9] } } },
  hanging_bracket: { label: 'Bracket', kind: 'hanging', mount: 'wall', file: 'hb_x.glb', size_m: [1.014, 0.1, 0.717], arms: 0, outward: [1, 0], mount_ft: 7, panels: { VB_sign_f: pan(0.62, 0.46, 0.034), VB_sign_b: pan(0.62, 0.46, 0.034) } },
};
const data = { version: 1, styles, presets };

async function loadCore() {
  const win = { __VB_SIGN_TEST: true };
  await new AsyncFunction('window', 'game', 'ui', 'canvas', body)(win, undefined, undefined, undefined);
  return win.__vbSignCore;
}
const core = await loadCore();
const measure = (t, size) => t.length * size * 0.5;                  // monospace stand-in: every glyph is half the font size wide

test('wrapText: words, explicit newlines, hard split of an over-long word', () => {
  const m = (t) => t.length * 10;
  assert.deepEqual(core.wrapText(m, 'Market Square', 129), ['Market', 'Square']);
  assert.deepEqual(core.wrapText(m, 'Market Square', 130), ['Market Square']);
  assert.deepEqual(core.wrapText(m, 'a\nb c', 1000), ['a', 'b c']);
  const long = core.wrapText(m, 'Supercalifragilistic', 80);
  assert.ok(long.length >= 3 && long.every((l) => m(l) <= 80), JSON.stringify(long));
  assert.deepEqual(core.wrapText(m, '', 100), ['']);
});

test('fitText: biggest size that fits, never exceeds the box, wraps before shrinking below min', () => {
  const specs = core.lineSpecs('High Street', 'equal');
  const r = core.fitText(measure, specs, 400, 100, { maxSize: 80 });
  assert.ok(r.fits && r.size <= 80 && r.w <= 400 && r.h <= 100);
  assert.ok(r.size > 60, 'one short line takes the max size region');
  const long = core.fitText(measure, core.lineSpecs('The Gilded Flagon and Lodging House of Bridgehollow', 'equal'), 400, 120, { maxSize: 90 });
  assert.ok(long.fits && long.lines.length >= 2, 'long text wraps to several lines');
  const tiny = core.fitText(measure, core.lineSpecs('x'.repeat(200), 'equal'), 50, 20, { minSize: 6 });
  assert.equal(tiny.size >= 6, true);
});

test('lineSpecs: subtitle style shrinks later lines, drops trailing blanks', () => {
  assert.deepEqual(core.lineSpecs('A\nB\nC', 'subtitle').map((s) => s.rel), [1, 0.6, 0.6]);
  assert.deepEqual(core.lineSpecs('A\nB\n', 'equal').map((s) => s.text), ['A', 'B']);
  assert.deepEqual(core.lineSpecs('', 'equal'), []);
});

test('normalize: defaults, clamps, schemes, arms, bad input never throws', () => {
  const s = core.normalize({}, data);
  assert.equal(s.v, 1); assert.equal(s.style, 'street_post'); assert.equal(s.text, 'High Street'); assert.equal(s.quality, 1024); assert.equal(s.back, 'same');
  const h = core.normalize({ style: 'hanging_bracket', size: 9, weather: -3, scheme: 'nope', icon: 'mug' }, data);
  assert.equal(h.size, 2); assert.equal(h.weather, 0); assert.equal(h.scheme, 'cream'); assert.equal(h.iconPos, 'top'); assert.equal(h.mountFt, 7);
  const c = core.normalize({ style: 'street_post', scheme: 'custom', paint: '#112233', ink: 'red', trim: '#abcdef' }, data);
  assert.equal(c.paint, '#112233'); assert.equal(c.ink, presets.schemes.custom.ink); assert.equal(c.trim, '#abcdef');
  const f = core.normalize({ style: 'fingerpost_2', arms: [{ text: 'X', dir: -1, yaw: 999 }] }, data);
  assert.equal(f.arms.length, 2); assert.equal(f.arms[0].dir, -1); assert.equal(f.arms[0].yaw, 60); assert.equal(f.arms[1].dir, 1);
  assert.equal(core.normalize({ style: 'zzz', text: 'a'.repeat(5000) }, data).text.length, 400);
  assert.equal(core.normalize({ text: Array(20).fill('x').join('\n') }, data).text.split('\n').length, 6);
  assert.equal(core.normalize(null, data).style, 'street_post');
  // idempotent: normalising a normalised sign changes nothing
  const a = core.normalize({ style: 'hanging_bracket', text: 'A\nB', icon: 'key' }, data);
  assert.deepEqual(core.normalize(a, data), a);
  // JSON round trip (flags are stored as JSON)
  assert.deepEqual(core.normalize(JSON.parse(JSON.stringify(a)), data), a);
});

test('flag schema: stored keys are exactly the documented ones', () => {
  const s = core.normalize({ style: 'street_post' }, data);
  const keys = Object.keys(s).sort();
  assert.deepEqual(keys, ['back', 'backText', 'finish', 'font', 'icon', 'iconPos', 'ink', 'lineStyle', 'mountFt', 'paint', 'quality', 'scheme', 'seed', 'size', 'spacing', 'style', 'text', 'trim', 'v', 'weather'].sort());
});

test('textureSize + panelRect', () => {
  assert.deepEqual(core.textureSize([1024, 270], 512), [512, 136]);
  assert.deepEqual(core.textureSize([1024, 760], 2048), [2048, 1520]);
  assert.ok(core.textureSize([1024, 8], 512)[1] >= 64);
  const r = core.panelRect(1000, 200, [0.1, 0.1, 0.9, 0.9], true); assert.ok([r.x - 100, r.y - 20, r.w - 800, r.h - 160].every((d) => Math.abs(d) < 1e-9));
  const l = core.panelRect(1000, 200, [0.1, 0.1, 0.9, 0.9], false); assert.ok(Math.abs(l.x - 100) < 1e-9 && Math.abs(l.w - 800) < 1e-9);
  const asym = core.panelRect(1000, 200, [0.12, 0.1, 0.97, 0.9], false); assert.ok(Math.abs(asym.x - 30) < 1e-9 && Math.abs(asym.w - 850) < 1e-9, 'tip-left mirrors the safe rectangle');
});

test('panels: board front/back, back modes, arms with tip sides', () => {
  const s = core.normalize({ style: 'street_post', text: 'Front', back: 'text', backText: 'Back' }, data);
  const p = core.panels(s, styles.street_post);
  assert.deepEqual(p.map((x) => [x.id, x.text]), [['f', 'Front'], ['b', 'Back']]);
  assert.equal(core.panels({ ...s, back: 'blank' }, styles.street_post)[1].text, '');
  assert.equal(core.panels({ ...s, back: 'same' }, styles.street_post)[1].text, 'Front');
  assert.equal(core.panels(core.normalize({ style: 'street_wall' }, data), styles.street_wall).length, 1);
  const f = core.normalize({ style: 'fingerpost_2', arms: [{ text: 'A', dir: 1 }, { text: 'B', dir: -1 }] }, data);
  const a = core.panels(f, styles.fingerpost_2);
  assert.deepEqual(a.map((x) => x.id), ['a1f', 'a1b', 'a2f', 'a2b']);
  assert.deepEqual(a.map((x) => x.tipRight), [true, false, false, true], 'front faces of a left arm show the tip on the left, back faces the opposite');
  assert.ok(a.every((x) => x.w >= 64 && x.h >= 64));
});

test('rotationFor: wall normal -> tile rotation (outward direction in scene px axes, y south)', () => {
  assert.equal(core.rotationFor([0, 1], { x: 0, y: 1 }), 0);        // plaque faces south, wall faces south
  assert.equal(core.rotationFor([0, 1], { x: -1, y: 0 }), 90);      // wall faces west -> rotate clockwise 90
  assert.equal(core.rotationFor([0, 1], { x: 0, y: -1 }), 180);
  assert.equal(core.rotationFor([0, 1], { x: 1, y: 0 }), 270);
  assert.equal(core.rotationFor([1, 0], { x: 1, y: 0 }), 0);        // bracket projects east, wall faces east
  assert.equal(core.rotationFor([1, 0], { x: 0, y: 1 }), 90);
  // rotating the outward vector by the result gives the normal
  for (const o of [[0, 1], [1, 0]]) for (const n of [{ x: 0.6, y: 0.8 }, { x: -0.8, y: -0.6 }]) {
    const th = (core.rotationFor(o, n) * Math.PI) / 180, rx = o[0] * Math.cos(th) - o[1] * Math.sin(th), ry = o[0] * Math.sin(th) + o[1] * Math.cos(th);
    assert.ok(Math.hypot(rx - n.x, ry - n.y) < 0.02, JSON.stringify([o, n, rx, ry]));
  }
});

test('tileData: ground vs wall, size multiplier, units, pipeline id, flags', () => {
  const g = core.normalize({ style: 'street_post', seed: 'abc12345', size: 1.5 }, data);
  const t = core.tileData({ ...g, base: core.basePaths() }, styles.street_post, { x: 100, y: 200 }, 65.6, { rotation: 30 });
  assert.equal(t.x, 100); assert.equal(t.y, 200); assert.equal(t.rotation, 30); assert.equal(t.elevation, 0);
  assert.ok(Math.abs(t.width - 0.772 * 65.6 * 1.5) < 1e-9 && Math.abs(t.flags['levels-3d-preview'].depth - 2.596 * 65.6 * 1.5) < 1e-9);
  const f3 = t.flags['levels-3d-preview'];
  assert.equal(f3.autoGround, true); assert.equal(f3.autoCenter, false); assert.equal(f3.collision, false); assert.equal(f3.sight, false); assert.equal(f3.castShadow, true);
  assert.equal(f3.model3d, 'assets/varrenmoor-signs/models/street_post_x.glb');
  assert.equal(t.flags.varrenmoor.pipelineId, 'sign:abc12345');
  const w = core.normalize({ style: 'hanging_bracket', seed: 's1', mountFt: 9 }, data);
  const tw = core.tileData(w, styles.hanging_bracket, { x: 0, y: 0 }, 100, { unitsPerFt: 0.3048 });
  assert.equal(tw.elevation, 2.74); assert.equal(tw.flags['levels-3d-preview'].autoGround, false);
  assert.equal(core.ftToUnits('m'), 0.3048); assert.equal(core.ftToUnits('ft'), 1); assert.equal(core.ftToUnits(undefined), 1);
  assert.doesNotThrow(() => JSON.stringify(t));
  const rz = core.resizeData({ ...g, size: 2 }, styles.street_post, 50, 1);
  assert.equal(rz.width, 0.772 * 50 * 2); assert.equal(rz['flags.levels-3d-preview.depth'], 2.596 * 50 * 2);
});

test('hash / rng / uid are deterministic or well formed', () => {
  assert.equal(core.hash('abc'), core.hash('abc')); assert.notEqual(core.hash('abc'), core.hash('abd'));
  const a = core.rng('x'), b = core.rng('x'); assert.deepEqual([a(), a(), a()], [b(), b(), b()]);
  assert.match(core.uid(), /^[a-z0-9]{8}$/);
  assert.equal(core.summary({ text: 'A\nB' }), 'A'); assert.equal(core.summary({ arms: [{ text: 'X\ny' }, { text: 'Z' }] }), 'X | Z');
});

test('animationScript: compiles, finds the tile through the parent chain, textures materials by name, shows the left arm node', () => {
  const src = core.animationScript();
  assert.doesNotThrow(() => new Function('delta', 'tile3d', src));
  const loads = [];
  class Loader { load(u) { const t = { src: u, repeat: {}, offset: {} }; loads.push(u); return t; } }
  const THREE = { TextureLoader: Loader, RepeatWrapping: 1000, sRGBEncoding: 3001 };
  const mat = (name) => ({ name, clone() { return { ...this, color: this.color, cloned: true }; }, color: { set() {} }, needsUpdate: false });
  const meshes = [mat('VB_sign_f'), mat('sign_wood'), mat('sign_iron'), mat('other')].map((m, i) => ({ isMesh: true, material: m, name: 'm' + i }));
  const g = (name) => ({ name, visible: true, rotation: { y: 0 }, isMesh: false });
  const arm1 = g('arm1'), arm1L = g('arm1L'), arm2 = g('arm2'), arm2L = g('arm2L');
  const all = [...meshes, arm1, arm1L, arm2, arm2L];
  const t3 = { mesh: { traverse: (cb) => all.forEach(cb) }, tile: { document: { flags: { varrenmoor: { sign: {
    tex: { VB_sign_f: { src: 'a/f.webp', v: 'v1' } }, base: { wood: 'a/wood.jpg', iron: 'a/iron.jpg' }, arms: [{ dir: 1, yaw: 0 }, { dir: -1, yaw: 20 }] } } } } } };
  const child = { parent: { userData: { entity3D: t3 } } };
  const L = { THREE };
  const fn = new Function('delta', 'tile3d', 'game', src.replace(/game\./g, 'game.'));
  const call = () => new Function('game', 'delta', 'return (function(delta, tile3d){' + src + '}).call(this, delta)').call(child, { Levels3DPreview: L }, 0);
  call();
  assert.ok(meshes[0].material.cloned && meshes[0].material.map.src === 'a/f.webp?v=v1', 'lettering texture with cache-bust query');
  assert.equal(meshes[1].material.map.src, 'a/wood.jpg'); assert.equal(meshes[2].material.map.src, 'a/iron.jpg');
  assert.equal(meshes[3].material.map, undefined, 'unrelated material untouched');
  assert.deepEqual([arm1.visible, arm1L.visible, arm2.visible, arm2L.visible], [true, false, false, true]);
  assert.ok(Math.abs(arm2L.rotation.y + (20 * Math.PI) / 180) < 1e-9, 'yaw is clockwise seen from above (three y rotation is counter clockwise)');
  const n = loads.length; call(); assert.equal(loads.length, n, 'second frame does nothing (runs once per tile load)');
  void fn; void L;
});
