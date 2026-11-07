// Unit test of the module's pipeline ops against a fake Foundry. Run: node --test foundry-bridge/module/module.test.mjs
import test from 'node:test';
import assert from 'node:assert';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));

class DocMap extends Map { *[Symbol.iterator]() { yield* this.values(); } }

function fakeFoundry() {
  const settings = { allowWrites: true };
  let n = 0;
  class Doc {
    constructor(data, parent, name) { Object.assign(this, structuredClone(data)); this.id = this._id = `id${String(++n).padStart(14, '0')}`; this.parent = parent; this.documentName = name; this.uuid = `${name}.${this.id}`; }
    async update(d) { const { levels, ...rest } = d; for (const [k, v] of Object.entries(rest)) { if (k.includes('.')) { const [a, b] = k.split('.'); this[a] = { ...this[a], [b]: v }; } else if (v && typeof v === 'object' && this[k] && typeof this[k] === 'object') Object.assign(this[k], v); else this[k] = v; } if (levels) for (const l of levels) Object.assign(this.levels.get(l._id), { background: { ...this.levels.get(l._id).background, ...l.background } }); }
    async delete() { (this.parent ? this.parent[`${this.documentName}s_`] : world[this.documentName]).delete(this.id); }
  }
  const world = { Scene: new DocMap(), Actor: new DocMap() };
  const mkScene = (data) => {
    const s = new Doc(data, null, 'Scene');
    const sub = (kind) => { const m = new Map(); m.contents = []; return m; };
    s.walls = new DocMap(); s.drawings = new DocMap(); s.tiles = new DocMap(); s.tokens = new DocMap();
    s.Walls_ = s.walls;
    const lv = new Map([['lvl', { id: 'lvl', background: { src: null } }]]); lv.contents = [...lv.values()]; s.levels = lv; s.initialLevel = 'lvl';
    s.WallDocs = s.walls; s.Wall_ = s.walls; s.Drawing_ = s.drawings;
    const kinds = { Wall: s.walls, Drawing: s.drawings, Tile: s.tiles, Token: s.tokens };
    s.createEmbeddedDocuments = async (k, arr) => arr.map((d) => { const x = new Doc(d, s, k); x.parent = { [`${k}s_`]: kinds[k] }; kinds[k].set(x.id, x); return x; });
    s.updateEmbeddedDocuments = async (k, arr) => { for (const u of arr) { const { _id, ...rest } = u; Object.assign(kinds[k].get(_id), rest); } };
    s.deleteEmbeddedDocuments = async (k, ids) => { ids.forEach((i) => kinds[k].delete(i)); };
    s.sub = (kind) => sub(kind);
    world.Scene.set(s.id, s);
    return s;
  };
  // iterable map-of-docs
  const hooks = {};
  const g = {
    Hooks: { once: (n_, f) => { hooks[n_] = f; } },
    game: {
      settings: { register() {}, get: (m, k) => settings[k] },
      modules: { get: () => ({ version: '0.3.0' }) },
      collections: new Map(),
      user: { isGM: true },
    },
    foundry: { utils: { deepClone: (o) => structuredClone(o) } },
    fromUuid: async (u) => { const [k, id] = u.split('.'); return world[k]?.get(id) ?? null; },
    getDocumentClass: (name) => ({
      create: async (d) => { const x = name === 'Scene' ? mkScene(d) : new Doc(d, null, name); if (name !== 'Scene') world[name].set(x.id, x); return x; },
      createDocuments: async (arr) => arr.map((d) => { const x = new Doc(d, null, name); world[name].set(x.id, x); return x; }),
      updateDocuments: async (arr) => { for (const u of arr) { const { _id, ...r } = u; Object.assign(world[name].get(_id), r); } },
      deleteDocuments: async (ids) => { ids.forEach((i) => world[name].delete(i)); },
    }),
  };
  g.game.collections.get = (n_) => world[n_];
  return { g, world, mkScene, settings };
}

async function loadModule(g) {
  Object.assign(globalThis, g);
  globalThis.canvas = {};
  const src = fs.readFileSync(path.join(here, 'varrenmoor-bridge', 'scripts', 'bridge.js'), 'utf8') + '\nexport { handle };\n';
  const tmp = path.join(os.tmpdir(), `bridge_test_${Date.now()}.mjs`);
  fs.writeFileSync(tmp, src);
  return import(pathToFileURL(tmp).href);
}

test('pipeline ops: version, upsert_many idempotent, prune, flag-guarded delete, scene background', async () => {
  const f = fakeFoundry();
  const { handle } = await loadModule(f.g);
  const v = await handle('version', {});
  assert.equal(v.module, '0.3.0');
  assert.ok(v.ops.includes('upsert_many'));

  const sc = f.mkScene({ name: 'ZZ' });
  const mine = await handle('upsert_by_flag', { documentName: 'Scene', id: 'scene:t:zz', data: { name: 'ZZ2' } });
  assert.equal(mine.created, true);
  const again = await handle('upsert_by_flag', { documentName: 'Scene', id: 'scene:t:zz', data: { name: 'ZZ3' } });
  assert.equal(again.created, false);
  assert.equal(again.uuid, mine.uuid);

  const items = [1, 2, 3].map((i) => ({ id: `wall:b:${i}`, data: { c: [0, 0, i, i] } }));
  const parent = sc.uuid;
  assert.deepEqual(await handle('upsert_many', { documentName: 'Wall', parentUuid: parent, items, prefix: 'wall:', prune: true }), { created: 3, updated: 0, deleted: 0 });
  assert.deepEqual(await handle('upsert_many', { documentName: 'Wall', parentUuid: parent, items: items.slice(0, 2), prefix: 'wall:', prune: true }), { created: 0, updated: 2, deleted: 1 });
  assert.equal(sc.walls.size, 2);
  assert.equal((await handle('find_by_flag', { documentName: 'Wall', parentUuid: parent, prefix: 'wall:' })).length, 2);

  // a hand-drawn wall (no flag) is never found, updated or pruned
  await sc.createEmbeddedDocuments('Wall', [{ c: [9, 9, 9, 9] }]);
  await handle('upsert_many', { documentName: 'Wall', parentUuid: parent, items: [], prefix: 'wall:', prune: true });
  assert.equal(sc.walls.size, 1);
  assert.deepEqual(await handle('delete_by_flag', { documentName: 'Wall', parentUuid: parent, prefix: 'wall:' }), { deleted: 0 });

  await assert.rejects(handle('delete', { uuid: sc.uuid }), /pipeline flag/);
  await handle('delete', { uuid: mine.uuid });
  assert.equal(f.world.Scene.has(mine.uuid.split('.')[1]), false);

  await handle('set_scene_background', { uuid: sc.uuid, src: 'assets/x_v001.webp', width: 500, height: 400, padding: 0 });
  assert.equal(sc.levels.get('lvl').background.src, 'assets/x_v001.webp');
  assert.equal(sc.width, 500);
  await handle('set_scene_grid', { uuid: sc.uuid, size: 120, distance: 100, units: 'ft' });
  assert.equal(sc.grid.size, 120);
  assert.equal(sc.grid.distance, 100);
});

test('writes disabled blocks pipeline ops', async () => {
  const f = fakeFoundry();
  f.settings.allowWrites = false;
  const { handle } = await loadModule(f.g);
  await assert.rejects(handle('upsert_by_flag', { documentName: 'Scene', id: 'x', data: {} }), /writes disabled/);
  await assert.rejects(handle('delete', { uuid: 'Scene.x' }), /writes disabled/);
});
