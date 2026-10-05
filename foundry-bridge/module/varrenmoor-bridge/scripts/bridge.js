const MOD = 'varrenmoor-bridge';
const COLLECTIONS = new Set(['Actor', 'Item', 'Scene', 'JournalEntry', 'Macro', 'RollTable', 'Playlist', 'Folder']);   // Folder: list/get/create/update only (no delete op exists)
const ACTIVITY_ID = /^[A-Za-z0-9]{16}$/;
const MAX_LIST = 500;

Hooks.once('init', () => {
  game.settings.register(MOD, 'enabled', { name: 'Connect to relay', hint: 'Only this GM client connects. Off by default.', scope: 'client', config: true, type: Boolean, default: false, onChange: () => connect() });
  game.settings.register(MOD, 'autoUrl', { name: 'Use launcher relay URL', hint: 'Read the current tunnel URL that start.bat writes into this module folder (relay-url.json), so quick-tunnel restarts need no re-pasting. Falls back to Relay URL below.', scope: 'client', config: true, type: Boolean, default: true, onChange: () => connect() });
  game.settings.register(MOD, 'relayUrl', { name: 'Relay URL', hint: 'e.g. wss://name.trycloudflare.com/module. Used when the launcher file is missing or the option above is off.', scope: 'client', config: true, type: String, default: 'ws://127.0.0.1:3030/module', onChange: () => connect() });
  game.settings.register(MOD, 'token', { name: 'Module token', hint: 'BRIDGE_MODULE_TOKEN from the relay.', scope: 'client', config: true, type: String, default: '', onChange: () => connect() });
  game.settings.register(MOD, 'allowWrites', { name: 'Allow writes', hint: 'Permit create/update requests. Never allows delete. Leave off for read-only.', scope: 'world', config: true, type: Boolean, default: false });
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

const ops = {
  ping: () => 'pong',

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
    if (!COLLECTIONS.has(documentName) && !['ActiveEffect', 'Wall', 'AmbientLight', 'Token', 'Tile'].includes(documentName)) throw new Error(`not allowed: ${documentName}`);
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
