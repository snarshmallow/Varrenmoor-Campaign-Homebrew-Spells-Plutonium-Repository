const MOD = 'varrenmoor-bridge';
const COLLECTIONS = new Set(['Actor', 'Item', 'Scene', 'JournalEntry', 'Macro', 'RollTable', 'Playlist', 'Folder']);   // Folder: list/get/create/update only (no delete op exists)
const ACTIVITY_ID = /^[A-Za-z0-9]{16}$/;
const MAX_LIST = 500;
// Pipeline flag: every document the Illustrator/pipeline tools create carries flags.varrenmoor.pipelineId (a stable string key).
// Upserts match on it, and delete is only ever allowed for documents that bear it. Keeps the repo's existing flags.varrenmoor.* scope.
const FLAG_SCOPE = 'varrenmoor';
const FLAG_KEY = 'pipelineId';
const PROTOCOL = 3;   // bump when ops change; clients check this via the 'version' op
const EMBEDDED = { Wall: 'walls', Drawing: 'drawings', Tile: 'tiles', Token: 'tokens', AmbientLight: 'lights', AmbientSound: 'sounds', Note: 'notes' };
const PIPE_DOCS = new Set([...COLLECTIONS, ...Object.keys(EMBEDDED)]);

Hooks.once('init', () => {
  game.settings.register(MOD, 'enabled', { name: 'Connect to relay', hint: 'Only this GM client connects. Off by default.', scope: 'client', config: true, type: Boolean, default: false, onChange: () => connect() });
  game.settings.register(MOD, 'autoUrl', { name: 'Use launcher relay URL', hint: 'Read the current tunnel URL that start.bat writes into this module folder (relay-url.json), so quick-tunnel restarts need no re-pasting. Falls back to Relay URL below.', scope: 'client', config: true, type: Boolean, default: true, onChange: () => connect() });
  game.settings.register(MOD, 'relayUrl', { name: 'Relay URL', hint: 'e.g. wss://name.trycloudflare.com/module. Used when the launcher file is missing or the option above is off.', scope: 'client', config: true, type: String, default: 'ws://127.0.0.1:3030/module', onChange: () => connect() });
  game.settings.register(MOD, 'token', { name: 'Module token', hint: 'BRIDGE_MODULE_TOKEN from the relay.', scope: 'client', config: true, type: String, default: '', onChange: () => connect() });
  game.settings.register(MOD, 'allowWrites', { name: 'Allow writes', hint: 'Permit create/update requests, and delete of documents that carry the pipeline flag (flags.varrenmoor.pipelineId) only. Leave off for read-only.', scope: 'world', config: true, type: Boolean, default: false });
});

Hooks.once('ready', () => { if (game.user.isGM) connect(); });

let socket = null;
let retry = 1000;
let timer = null;
let generation = 0;

// start.bat writes the live tunnel URL here; Foundry serves it from the module folder (same origin).
async function launcherUrl() {
  try {
    const r = await fetch(`modules/${MOD}/relay-url.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return null;
    const { url } = await r.json();
    return typeof url === 'string' && /^wss?:\/\//.test(url) ? url : null;
  } catch { return null; }
}

async function connect() {
  clearTimeout(timer);
  const gen = ++generation;
  if (socket) { socket.onclose = null; socket.close(); socket = null; }
  if (!game.user?.isGM || !game.settings.get(MOD, 'enabled')) return;
  const token = game.settings.get(MOD, 'token');
  const url = (game.settings.get(MOD, 'autoUrl') && await launcherUrl()) || game.settings.get(MOD, 'relayUrl');
  if (gen !== generation || !url || !token) return;
  const ws = new WebSocket(url);
  socket = ws;
  ws.onopen = () => ws.send(JSON.stringify({ type: 'hello', token }));
  ws.onmessage = async (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === 'welcome') { retry = 1000; ui.notifications.info('Varrenmoor Bridge connected.'); return; }
    if (!m.id) return;
    try { ws.send(JSON.stringify({ id: m.id, result: await handle(m.op, m.args ?? {}) })); }
    catch (e) { ws.send(JSON.stringify({ id: m.id, error: String(e?.message ?? e) })); }
  };
  ws.onclose = () => { timer = setTimeout(connect, retry); retry = Math.min(retry * 2, 30000); };
}

const coll = (name) => {
  if (!COLLECTIONS.has(name)) throw new Error(`collection not allowed: ${name}`);
  return game.collections.get(name);
};

function requireWrites() {
  if (!game.settings.get(MOD, 'allowWrites')) throw new Error('writes disabled in module settings');
}

function activityProblems(item) {
  const acts = item.system?.activities;
  if (!acts) return [];
  const out = [];
  for (const [key, a] of acts.entries ? acts.entries() : Object.entries(acts)) {
    const id = a?.id ?? key;
    if (!ACTIVITY_ID.test(id)) out.push({ activity: a?.name ?? key, id, length: String(id).length });
  }
  return out;
}

const pipeId = (d) => d?.flags?.[FLAG_SCOPE]?.[FLAG_KEY] ?? null;   // direct read: getFlag() rejects scopes that are not a module/system id

function stamp(data, id) {
  const out = foundry.utils.deepClone(data ?? {});
  out.flags = { ...(out.flags ?? {}), [FLAG_SCOPE]: { ...(out.flags?.[FLAG_SCOPE] ?? {}), [FLAG_KEY]: id } };
  return out;
}

async function container(documentName, parentUuid) {
  if (!PIPE_DOCS.has(documentName)) throw new Error(`not allowed: ${documentName}`);
  if (EMBEDDED[documentName]) {
    if (!parentUuid) throw new Error(`${documentName} needs parentUuid (the scene)`);
    const parent = await fromUuid(parentUuid);
    if (!parent) throw new Error(`parent not found: ${parentUuid}`);
    return { parent, docs: [...parent[EMBEDDED[documentName]]], embedded: true };
  }
  return { parent: null, docs: [...coll(documentName)], embedded: false };
}

const createIn = (c, name, arr) => (c.embedded ? c.parent.createEmbeddedDocuments(name, arr) : getDocumentClass(name).createDocuments(arr));
const updateIn = (c, name, arr) => (c.embedded ? c.parent.updateEmbeddedDocuments(name, arr) : getDocumentClass(name).updateDocuments(arr));
const deleteIn = (c, name, ids) => (c.embedded ? c.parent.deleteEmbeddedDocuments(name, ids) : getDocumentClass(name).deleteDocuments(ids));
const brief = (d) => ({ uuid: d.uuid, name: d.name ?? null, pipelineId: pipeId(d) });

const ops = {
  ping: () => 'pong',

  // Capability query: clients use this to degrade with a clear message when the module on the Foundry server is older.
  version: () => ({ module: game.modules.get(MOD)?.version ?? null, protocol: PROTOCOL, flag: `flags.${FLAG_SCOPE}.${FLAG_KEY}`, ops: Object.keys(ops) }),

  find_by_flag: async ({ documentName, parentUuid, id, prefix }) => {
    const c = await container(documentName, parentUuid);
    const hit = c.docs.filter((d) => { const p = pipeId(d); return p && (id ? p === id : prefix ? String(p).startsWith(prefix) : true); });
    return hit.slice(0, MAX_LIST).map(brief);
  },

  upsert_by_flag: async ({ documentName, parentUuid, id, data }) => {
    requireWrites();
    if (!id) throw new Error('id required');
    const c = await container(documentName, parentUuid);
    const found = c.docs.find((d) => pipeId(d) === id);
    if (found) { await found.update(stamp(data, id)); return { uuid: found.uuid, created: false }; }
    const [made] = await createIn(c, documentName, [stamp(data, id)]);
    return { uuid: made.uuid, created: true };
  },

  // Bulk upsert (walls, drawings, tiles, tokens). items: [{id, data}]. prefix + prune: delete flagged docs under that prefix that are no longer in items.
  upsert_many: async ({ documentName, parentUuid, items, prefix, prune }) => {
    requireWrites();
    const c = await container(documentName, parentUuid);
    const byId = new Map(c.docs.filter((d) => pipeId(d)).map((d) => [pipeId(d), d]));
    const toCreate = [], toUpdate = [], seen = new Set();
    for (const it of items ?? []) {
      if (!it.id) throw new Error('every item needs an id');
      seen.add(it.id);
      const ex = byId.get(it.id);
      if (ex) toUpdate.push({ ...stamp(it.data, it.id), _id: ex.id }); else toCreate.push(stamp(it.data, it.id));
    }
    const stale = prune && prefix ? [...byId].filter(([k]) => String(k).startsWith(prefix) && !seen.has(k)).map(([, d]) => d.id) : [];
    if (toUpdate.length) await updateIn(c, documentName, toUpdate);
    if (toCreate.length) await createIn(c, documentName, toCreate);
    if (stale.length) await deleteIn(c, documentName, stale);
    return { created: toCreate.length, updated: toUpdate.length, deleted: stale.length };
  },

  // Delete is limited to documents bearing the pipeline flag.
  delete_by_flag: async ({ documentName, parentUuid, id, prefix }) => {
    requireWrites();
    if (!id && !prefix) throw new Error('id or prefix required');
    const c = await container(documentName, parentUuid);
    const ids = c.docs.filter((d) => { const p = pipeId(d); return p && (id ? p === id : String(p).startsWith(prefix)); }).map((d) => d.id);
    if (ids.length) await deleteIn(c, documentName, ids);
    return { deleted: ids.length };
  },

  delete: async ({ uuid }) => {
    requireWrites();
    const doc = await fromUuid(uuid);
    if (!doc) throw new Error(`not found: ${uuid}`);
    if (!pipeId(doc)) throw new Error('refusing to delete a document without the pipeline flag');
    await doc.delete();
    return { deleted: uuid };
  },

  // v14: the background image lives on a Level (scene.levels); older cores keep scene.background.src.
  set_scene_background: async ({ uuid, src, levelId, width, height, padding }) => {
    requireWrites();
    const scene = await fromUuid(uuid);
    if (!scene || scene.documentName !== 'Scene') throw new Error(`not a scene: ${uuid}`);
    const upd = {};
    if (width) upd.width = width;
    if (height) upd.height = height;
    if (padding !== undefined && padding !== null) upd.padding = padding;
    const lv = scene.levels;
    if (lv && lv.size) {
      const lvl = (levelId && lv.get(levelId)) || lv.get(scene.initialLevel) || lv.contents[0];
      upd.levels = [{ _id: lvl.id, background: { src } }];
    } else upd['background.src'] = src;
    await scene.update(upd);
    return { uuid: scene.uuid, src };
  },

  set_scene_grid: async ({ uuid, size, distance, units, type }) => {
    requireWrites();
    const scene = await fromUuid(uuid);
    if (!scene || scene.documentName !== 'Scene') throw new Error(`not a scene: ${uuid}`);
    const upd = {};
    if (size) upd['grid.size'] = size;
    if (distance) upd['grid.distance'] = distance;
    if (units) upd['grid.units'] = units;
    if (type !== undefined && type !== null) upd['grid.type'] = type;
    await scene.update(upd);
    return { uuid: scene.uuid, grid: upd };
  },

  world_info: () => ({
    foundry: game.version, system: game.system.id, systemVersion: game.system.version, world: game.world.id,
    activeScene: game.scenes.active?.name ?? null, viewedScene: canvas.scene?.name ?? null,
    modules: game.modules.filter((m) => m.active).map((m) => ({ id: m.id, version: m.version })),
  }),

  list: ({ collection, type, nameContains }) => {
    let docs = coll(collection).contents;
    if (type) docs = docs.filter((d) => d.type === type);
    if (nameContains) docs = docs.filter((d) => d.name.toLowerCase().includes(String(nameContains).toLowerCase()));
    return docs.slice(0, MAX_LIST).map((d) => ({ uuid: d.uuid, name: d.name, type: d.type ?? null }));
  },

  get: async ({ uuid }) => {
    const doc = await fromUuid(uuid);
    if (!doc) throw new Error(`not found: ${uuid}`);
    return doc.toObject();
  },

  audit_activities: () => {
    const bad = [];
    const check = (item, owner) => { const p = activityProblems(item); if (p.length) bad.push({ owner, item: item.name, uuid: item.uuid, problems: p }); };
    game.items.forEach((i) => check(i, 'world'));
    game.actors.forEach((a) => a.items.forEach((i) => check(i, a.name)));
    return { requiredPattern: '16 alphanumeric characters', badCount: bad.length, bad };
  },

  scene_stats: () => {
    const s = canvas.scene;
    if (!s) return null;
    return {
      name: s.name, tokens: s.tokens.size, walls: s.walls.size, lights: s.lights.size,
      tokenVision: s.tokenVision, fog: s.fog?.exploration ?? null, globalLight: s.environment?.globalLight?.enabled ?? null,
      renderer: canvas.app?.renderer?.name ?? canvas.app?.renderer?.constructor?.name ?? null,
      canvas3d: !!game.Levels3DPreview?._active,
    };
  },

  perf_sample: ({ ms = 5000 }) => new Promise((resolve) => {
    const dur = Math.min(Math.max(Number(ms) || 5000, 1000), 30000);
    // requestAnimationFrame counts real browser frames for both the PIXI canvas and 3D Canvas (three.js),
    // which renders on its own loop while the PIXI ticker sits idle.
    const gaps = [];
    let last = performance.now();
    let raf = 0;
    const tick = (now) => { gaps.push(now - last); last = now; raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    setTimeout(() => {
      cancelAnimationFrame(raf);
      const sorted = [...gaps].sort((a, b) => a - b);
      const sum = gaps.reduce((a, b) => a + b, 0);
      resolve({
        hidden: document.hidden, canvas3d: !!game.Levels3DPreview?._active,
        durationMs: Math.round(sum), frames: gaps.length, avgFps: sum ? +(gaps.length / (sum / 1000)).toFixed(1) : null,
        p95FrameMs: +(sorted[Math.floor(sorted.length * 0.95)] ?? 0).toFixed(1), maxFrameMs: +(sorted.at(-1) ?? 0).toFixed(1),
        framesOver50ms: gaps.filter((g) => g > 50).length,
      });
    }, dur);
  }),

  create: async ({ documentName, data, parentUuid }) => {
    requireWrites();
    if (!COLLECTIONS.has(documentName) && !['ActiveEffect', 'Wall', 'AmbientLight', 'AmbientSound', 'PlaylistSound', 'Token', 'Tile', 'Drawing', 'Note'].includes(documentName)) throw new Error(`not allowed: ${documentName}`);
    const parent = parentUuid ? await fromUuid(parentUuid) : null;
    const created = await getDocumentClass(documentName).create(data, parent ? { parent } : {});
    return { uuid: created.uuid };
  },

  update: async ({ uuid, data }) => {
    requireWrites();
    const doc = await fromUuid(uuid);
    if (!doc) throw new Error(`not found: ${uuid}`);
    await doc.update(data);
    return { uuid: doc.uuid };
  },
};

async function handle(op, args) {
  const fn = ops[op];
  if (!fn) throw new Error(`unknown op: ${op}`);
  return fn(args);
}
