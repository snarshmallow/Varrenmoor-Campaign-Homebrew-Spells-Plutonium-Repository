// door_sync.js without Foundry: fake Hooks / scene, drives both directions and the loop guard.   node --test illustrator/foundry_macros/door_sync.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const body = fs.readFileSync(path.join(HERE, 'door_sync.js'), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;

function env({ gm = true, active = true } = {}) {
  const hooks = {}; const notes = []; const win = {};
  const wall = { id: 'W1', door: 1, ds: 0, flags: { varrenmoor: { doorId: 'd1' } }, parent: null };
  const tile = { id: 'T1', flags: { 'levels-3d-preview': { modelDoors: { d1: { ds: '0' } } } }, parent: null, updates: [],
    async update(d, o) { this.updates.push([d, o]); const k = Object.keys(d)[0].split('.'); this.flags['levels-3d-preview'].modelDoors[k[3]] = { ds: Object.values(d)[0] }; } };
  const scene = { id: 'S1', walls: { contents: [wall] }, tiles: { contents: [tile] }, wallUpdates: [],
    async updateEmbeddedDocuments(n, ups, o) { this.wallUpdates.push([ups, o]); for (const u of ups) wall.ds = u.ds; } };
  wall.parent = tile.parent = scene;
  const Hooks = { on: (n, f) => { hooks[n] = f; return n; }, off: (n) => delete hooks[n] };
  const game = { user: { isGM: gm }, users: { activeGM: { isSelf: active } }, Levels3DPreview: { tiles: {} } };
  return { hooks, notes, win, wall, tile, scene, args: { game, canvas: { scene }, ui: { notifications: { info: (m) => notes.push(m), warn: (m) => notes.push('W ' + m) } }, Hooks, window: win } };
}
const run = (e, scope) => new AsyncFunction('game', 'canvas', 'ui', 'Hooks', 'window', 'scope', body)(e.args.game, e.args.canvas, e.args.ui, e.args.Hooks, e.args.window, scope);

test('model door -> wall door, with loop guard', async () => {
  const e = env(); await run(e);
  await e.hooks.updateTile(e.tile, { flags: { 'levels-3d-preview': { modelDoors: { d1: { ds: '1' } } } } }, {});
  assert.equal(e.wall.ds, 1); assert.equal(e.scene.wallUpdates[0][1].vbDoorSync, true);
  await e.hooks.updateTile(e.tile, { 'flags.levels-3d-preview.modelDoors.d1.ds': '1' }, {});         // already in step: no second write
  assert.equal(e.scene.wallUpdates.length, 1);
  await e.hooks.updateTile(e.tile, { flags: { 'levels-3d-preview': { modelDoors: { d1: { ds: '0' } } } } }, { vbDoorSync: true });   // our own write is ignored
  assert.equal(e.wall.ds, 1);
  await e.hooks.updateTile(e.tile, { flags: { 'levels-3d-preview': { modelDoors: { d1: { ds: '2' } } } } }, {});
  assert.equal(e.wall.ds, 2);
});

test('wall door -> model door', async () => {
  const e = env(); await run(e);
  e.wall.ds = 1; await e.hooks.updateWall(e.wall, { ds: 1 }, {});
  assert.equal(e.tile.flags['levels-3d-preview'].modelDoors.d1.ds, '1');
  assert.equal(e.tile.updates[0][1].vbDoorSync, true);
  await e.hooks.updateWall(e.wall, { ds: 1 }, {});                                              // same state: nothing written
  assert.equal(e.tile.updates.length, 1);
  await e.hooks.updateWall(e.wall, { c: [0, 0, 1, 1] }, {});                                    // not a door state change
  assert.equal(e.tile.updates.length, 1);
  e.wall.ds = 0; await e.hooks.updateWall(e.wall, { ds: 0 }, {});
  assert.equal(e.tile.flags['levels-3d-preview'].modelDoors.d1.ds, '0');
});

test('only the active GM acts; run again = off; mode on never toggles off', async () => {
  const e = env({ active: false }); await run(e);
  await e.hooks.updateTile(e.tile, { flags: { 'levels-3d-preview': { modelDoors: { d1: { ds: '1' } } } } }, {});
  assert.equal(e.scene.wallUpdates.length, 0);
  await run(e, { mode: 'on' }); assert.ok(e.win.__vbDoorSync);
  await run(e); assert.equal(e.win.__vbDoorSync, undefined); assert.deepEqual(Object.keys(e.hooks), []);
  const p = env({ gm: false }); await run(p); assert.ok(!p.win.__vbDoorSync);
});
