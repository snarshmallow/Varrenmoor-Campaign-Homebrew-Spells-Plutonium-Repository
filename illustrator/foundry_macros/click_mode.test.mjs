// click_mode.js without Foundry: runs the macro body against a fake game / canvas / three and drives it with synthetic pointer events.
//   node --test illustrator/foundry_macros/click_mode.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const body = fs.readFileSync(path.join(HERE, 'click_mode.js'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function node(name, userData = {}, parent = null) { return { name, userData, parent, visible: true, uuid: 'u' + Math.random() }; }
function makeEnv({ isGM = true, layer = 'Tile', roofFlag, hitsFor }) {
  const handlers = {}; const updates = []; const toggles = []; const notes = [];
  const dom = { addEventListener: (t, f) => (handlers[t] = f), removeEventListener: (t) => delete handlers[t], getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }) };
  class V2 { constructor(x, y) { this.x = x; this.y = y; } }
  const tileDoc = { id: 'T1', hidden: false, flags: { varrenmoor: roofFlag ? { roof: roofFlag } : {} } };
  const tile3d = { document: tileDoc, mesh: null };
  const mesh = node('tilemesh', { entity3D: tile3d }); tile3d.mesh = mesh;
  const THREE = { Vector2: V2, Raycaster: class { setFromCamera() {} intersectObjects(m) { return hitsFor(mesh, m); } },
    Box3: class { setFromObject() { return this; } }, Box3Helper: class { constructor() { this.parent = null; } }, Color: class {} };
  const scene = { children: [], add(h) { h.parent = { remove() {} }; } };
  const env = {
    game: { user: { isGM, id: 'U1' }, Levels3DPreview: { THREE, camera: {}, scene, renderer: { domElement: dom }, interactionManager: {}, tiles: { T1: tile3d },
      socket: { toggleDoor: (a) => toggles.push(a) } } },
    canvas: { activeLayer: { options: { objectClass: { embeddedName: layer } } }, scene: { id: 'S1', tiles: { get: () => tileDoc },
      updateEmbeddedDocuments: async (n, u) => { updates.push(u); tileDoc.hidden = u[0].hidden; } } },
    ui: { notifications: { info: (m) => notes.push(m), warn: (m) => notes.push('W ' + m) } },
    window: {},
  };
  const run = () => new AsyncFunction('game', 'canvas', 'ui', 'window', body)(env.game, env.canvas, env.ui, env.window);
  const click = async (x = 10, y = 10, extra = {}) => { handlers.pointerdown({ button: 0, clientX: x, clientY: y }); handlers.pointerup({ button: 0, clientX: x, clientY: y, ...extra }); await new Promise((r) => setTimeout(r, 5)); };
  return { env, run, click, handlers, updates, toggles, notes, tileDoc, mesh };
}

test('core: classify, pick, short click', async () => {
  const e = makeEnv({ roofFlag: { mode: 'per_building', buildings: ['bld_a'] }, hitsFor: () => [] });
  await e.run();
  const core = e.env.window.__vbClickMode.core;
  assert.equal(core.roofName('bld_a_roof'), 'bld_a'); assert.equal(core.roofName('bld_a_door1'), null);
  assert.deepEqual(core.classify([{ name: 'x', userData: { isDoor: 1, doorId: 'd1' } }], null), { kind: 'door', doorId: 'd1' });
  const c = core.classify([{ name: 'mesh', userData: {} }, { name: 'bld_a_roof', userData: {} }], { roof: { mode: 'per_scene', buildings: ['a', 'b'] } });
  assert.equal(c.building, 'bld_a'); assert.equal(c.whole, false);
  assert.equal(core.classify([{ name: 'bld_a_roof', userData: {} }], { roof: { mode: 'per_building', buildings: ['bld_a'] } }).whole, true);
  assert.equal(core.classify([{ name: 'wall', userData: {} }], {}), null);
  const hits = [{ distance: 5, chain: [{ name: 'g', userData: {} }], tileFlags: {} }, { distance: 9, chain: [{ name: 'q_roof', userData: {} }], tileFlags: { roof: { mode: 'per_building', buildings: ['q'] } } },
    { distance: 7, chain: [{ name: 'doorleaf', userData: { isDoor: 1, doorId: 'dd' } }], tileFlags: {} }];
  assert.equal(core.pick(hits, false).kind, 'door'); assert.equal(core.pick(hits, true).kind, 'roof');
  assert.ok(core.isShortClick({ x: 0, y: 0 }, { x: 2, y: 2 })); assert.ok(!core.isShortClick({ x: 0, y: 0 }, { x: 20, y: 0 })); assert.ok(!core.isShortClick(null, { x: 0, y: 0 }));
  e.env.window.__vbClickMode.off();
});

test('per_building: click roof toggles that tile hidden, click again shows; macro twice = off', async () => {
  const e = makeEnv({ roofFlag: { mode: 'per_building', buildings: ['bld_a'] }, hitsFor: (mesh) => [{ distance: 3, object: node('m', {}, node('bld_a_roof', {}, mesh)) }] });
  await e.run();
  assert.ok(e.handlers.pointerup);
  await e.click(); assert.deepEqual(e.updates[0], [{ _id: 'T1', hidden: true }]);
  await e.click(); assert.deepEqual(e.updates[1], [{ _id: 'T1', hidden: false }]);
  await e.click(10, 10, { ctrlKey: true }); assert.equal(e.updates.length, 2);
  e.handlers.pointerdown({ button: 0, clientX: 0, clientY: 0 }); e.handlers.pointerup({ button: 0, clientX: 50, clientY: 0 });
  await new Promise((r) => setTimeout(r, 5)); assert.equal(e.updates.length, 2, 'a drag is not a click');
  await e.run(); assert.equal(e.handlers.pointerup, undefined);
});

test('per_scene: plain click hides only the node locally; shift toggles the whole tile; non-GM does nothing', async () => {
  const roofFlag = { mode: 'per_scene', buildings: ['a', 'b'] };
  let roofNode;
  const e = makeEnv({ roofFlag, hitsFor: (mesh) => { roofNode = roofNode || node('a_roof', {}, mesh); return [{ distance: 2, object: node('m', {}, roofNode) }]; } });
  await e.run();
  await e.click(); assert.equal(e.updates.length, 0); assert.equal(roofNode.visible, false);
  await e.click(); assert.equal(roofNode.visible, true);
  await e.click(10, 10, { shiftKey: true }); assert.deepEqual(e.updates[0], [{ _id: 'T1', hidden: true }]);
  await e.click(); assert.equal(roofNode.visible, false);
  e.env.window.__vbClickMode.off(); assert.equal(roofNode.visible, true);
  const p = makeEnv({ isGM: false, roofFlag, hitsFor: () => [] }); await p.run(); await p.click(); assert.equal(p.updates.length, 0);
});

test('door: click toggles via module socket on non-token layer; token layer left to the module; roof tiles not raycast for players', async () => {
  const e = makeEnv({ layer: 'Tile', hitsFor: (mesh) => [{ distance: 1, object: node('leaf', { isDoor: true, doorId: 'bld_1_door1' }, mesh) }] });
  await e.run(); await e.click();
  assert.deepEqual(e.toggles, [{ tileId: 'T1', sceneId: 'S1', userId: 'U1', subDoorId: 'bld_1_door1' }]);
  const t = makeEnv({ layer: 'Token', hitsFor: (mesh, m) => (m.length ? [{ distance: 1, object: node('leaf', { isDoor: true, doorId: 'd' }, mesh) }] : []) });
  await t.run(); await t.click(); assert.equal(t.toggles.length, 0);
  const p = makeEnv({ isGM: false, layer: 'Tile', roofFlag: { mode: 'per_building', buildings: ['x'] }, hitsFor: (mesh, m) => (m.length ? [{ distance: 1, object: node('leaf', { isDoor: true, doorId: 'd' }, mesh) }] : []) });
  await p.run(); await p.click(); assert.equal(p.toggles.length, 0);
});
