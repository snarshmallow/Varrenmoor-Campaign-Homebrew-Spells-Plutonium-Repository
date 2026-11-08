import * as Pair from './pairing.js';

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
  game.settings.register(MOD, 'pairHost', { name: 'Relay address for pairing', hint: 'host or host:port of the PC running the relay on your LAN, e.g. 10.0.0.20:3030. Blank: the Pair button scans this PC\'s /24 network.', scope: 'client', config: true, type: String, default: '' });
  game.settings.register(MOD, 'autoPair', { name: 'Offer pairing when not set up', hint: 'On startup, if there is no token and no pairing, look for the relay at the address above and offer to pair.', scope: 'client', config: true, type: Boolean, default: true });
  game.settings.register(MOD, 'deviceAuth', { name: 'Paired device (internal)', scope: 'client', config: false, type: String, default: '' });
  game.settings.register(MOD, 'allowWrites', { name: 'Allow writes', hint: 'Permit create/update requests, and delete of documents that carry the pipeline flag (flags.varrenmoor.pipelineId) only. Leave off for read-only.', scope: 'world', config: true, type: Boolean, default: false });
});

Hooks.once('ready', () => {
  try { const m = game.modules.get(MOD); if (m) m.api = { pair: (o) => startPairing({ scan: true, ...o }), unpair: () => forgetDevice(), status: () => ({ paired: !!readDevice(), connected: !!(socket && socket.readyState === 1) }) }; } catch { /* no api */ }
  if (!game.user.isGM) return;
  connect();
  // No token and no pairing yet: look for a relay at the configured address and offer to pair (never scans the network on its own).
  if (game.settings.get(MOD, 'enabled') && !readDevice() && !game.settings.get(MOD, 'token') && game.settings.get(MOD, 'autoPair') !== false) startPairing({ scan: false, silent: true });
});

// ---- LAN pairing (0.4.0): no tokens to type. The relay shows "Approve this device?" with the same code this browser shows; the device token it issues is
// kept in this browser's client-scoped setting 'deviceAuth' only. The manual Module token path below keeps working as a fallback.
Hooks.on?.('renderSettingsConfig', (app, html) => {
  try {
    const root = html instanceof HTMLElement ? html : html[0] ?? html;
    const input = root.querySelector(`[name="${MOD}.pairHost"]`);
    if (!input || root.querySelector('.vb-pair-buttons')) return;
    const row = document.createElement('div'); row.className = 'form-group vb-pair-buttons';
    row.innerHTML = '<label>Pairing</label><div class="form-fields"><button type="button" data-vb="pair"><i class="fa-solid fa-link"></i> Pair with relay</button> <button type="button" data-vb="unpair">Forget pairing</button></div><p class="hint">Pair: asks the relay PC for approval (relay window or Illustrator panel). No token is typed.</p>';
    row.querySelector('[data-vb="pair"]').addEventListener('click', () => startPairing({ scan: true }));
    row.querySelector('[data-vb="unpair"]').addEventListener('click', () => forgetDevice());
    (input.closest('.form-group') ?? input).after(row);
  } catch { /* settings UI differs: the console API still works */ }
});

const readDevice = () => { try { const d = JSON.parse(game.settings.get(MOD, 'deviceAuth') || 'null'); return d && d.host && d.deviceId && d.token ? d : null; } catch { return null; } };
const saveDevice = (d) => game.settings.set(MOD, 'deviceAuth', d ? JSON.stringify(d) : '');
async function forgetDevice() { await saveDevice(null); notify('info', 'unpaired', 'Varrenmoor Bridge: pairing forgotten on this browser (revoke it on the relay too, in the Illustrator panel).', true); connect(); }

const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let pairingRun = null, codeDialog = null;
function showCode({ code, host }, state) {
  const body = `<p>Pairing with the relay at <b>${escapeHtml(host)}</b>.</p><p>Look at the relay window or the Illustrator panel. It must show this exact code, and only then press <b>Approve</b> there:</p><p style="font-size:2em;letter-spacing:.15em;text-align:center"><b>${escapeHtml(code)}</b></p><p class="hint">If the code differs, press Deny there: someone else on the network is asking.</p>`;
  try {
    const D = foundry.applications.api.DialogV2;
    codeDialog = new D({ window: { title: 'Pair Varrenmoor Bridge' }, content: body, buttons: [{ action: 'cancel', label: 'Cancel', default: true, callback: () => { state.cancelled = true; } }], rejectClose: false });
    codeDialog.render({ force: true });
  } catch { notify('info', 'pair-code', `Varrenmoor Bridge pairing code ${code}: approve on the relay only if it shows the same code.`, true); }
}
async function startPairing({ scan = false, silent = false } = {}) {
  if (!game.user?.isGM) { if (!silent) notify('warn', 'pair-gm', 'Only a GM can pair the bridge.', true); return { ok: false, reason: 'not a GM' }; }
  if (pairingRun) return { ok: false, reason: 'already pairing' };
  const state = pairingRun = { cancelled: false };
  try {
    const found = await Pair.findRelay({ candidates: Pair.candidateHosts({ pairHost: game.settings.get(MOD, 'pairHost'), relayUrl: game.settings.get(MOD, 'relayUrl'), stored: readDevice() }), hostname: location.hostname, scan }, (...a) => fetch(...a));
    if (!found) { if (!silent) notify('warn', 'pair-none', 'Varrenmoor Bridge: no relay found. Is it running (Launch Bridge in Illustrator)? You can type its address (host:3030) in the setting "Relay address for pairing".', true); return { ok: false, reason: 'no relay found' }; }
    const res = await Pair.runPairing({ host: found.host, device: Pair.describeDevice({ user: game.user, world: game.world, location, ua: navigator.userAgent }), fetchFn: (...a) => fetch(...a),
      hooks: { onCode: (c) => showCode(c, state), cancelled: () => state.cancelled } });
    try { codeDialog?.close({ animate: false }); } catch { /* already closed */ } codeDialog = null;
    if (!res.ok) { notify('warn', 'pair-fail', `Varrenmoor Bridge pairing: ${res.reason}.`, true); return res; }
    await saveDevice({ host: res.host, relayId: res.relayId, deviceId: res.deviceId, token: res.token, expiresAt: res.expiresAt });
    await game.settings.set(MOD, 'enabled', true);
    notify('info', 'paired', 'Varrenmoor Bridge paired with the relay. No token needed from now on.', true);
    connect();
    return { ok: true };
  } finally { pairingRun = null; }
}

let socket = null;
let retry = 1000;
let timer = null;
let generation = 0;
let unreachable = 0, lastRelocate = 0;
let evicted = false;       // true after the relay closed us with 4002 ("replaced"): another GM tab took over, so do NOT auto-reconnect
const lastNotice = new Map();
const NOTICE_GAP_MS = 60000;

// Rate-limited notification: the same key is shown at most once per NOTICE_GAP_MS (a reconnect loop must never spam the GM).
function notify(level, key, msg, force = false) {
  const now = Date.now();
  if (!force && now - (lastNotice.get(key) ?? -Infinity) < NOTICE_GAP_MS) return false;
  lastNotice.set(key, now);
  try { ui.notifications[level](msg); } catch { /* UI not ready */ }
  return true;
}

// start.bat writes the live tunnel URL here; Foundry serves it from the module folder (same origin).
async function launcherUrl() {
  try {
    const r = await fetch(`modules/${MOD}/relay-url.json?t=${Date.now()}`, { cache: 'no-store' });
    if (!r.ok) return null;
    const { url } = await r.json();
    return typeof url === 'string' && /^wss?:\/\//.test(url) ? url : null;
  } catch { return null; }
}

// connect() is the single entry point; settings changes call it too, which also clears the "evicted" state (user intent).
async function connect() {
  clearTimeout(timer);
  evicted = false;
  const gen = ++generation;
  if (socket) { socket.onclose = null; socket.close(); socket = null; }
  if (!game.user?.isGM || !game.settings.get(MOD, 'enabled')) return;
  const token = game.settings.get(MOD, 'token');
  const dev = readDevice();   // a paired-device token wins over the manual token; the manual token stays as the fallback when not paired
  const url = dev ? Pair.wsUrlFor(dev.host) : (game.settings.get(MOD, 'autoUrl') && await launcherUrl()) || game.settings.get(MOD, 'relayUrl');
  if (gen !== generation || !url || !(dev || token)) return;
  const ws = new WebSocket(url);
  socket = ws;
  let welcomed = false;
  ws.onopen = () => ws.send(JSON.stringify(dev ? { type: 'hello', deviceId: dev.deviceId, deviceToken: dev.token } : { type: 'hello', token }));
  ws.onmessage = async (ev) => {
    const m = JSON.parse(ev.data);
    if (m.type === 'welcome') {
      retry = 1000; welcomed = true; unreachable = 0;
      // the relay rotates the device token near expiry or on request from the panel; keep the new one (the old one works for 5 more minutes)
      if (m.rotate && m.rotate.token && dev) saveDevice({ ...dev, token: m.rotate.token, expiresAt: m.rotate.expiresAt || dev.expiresAt });
      // Rate-limited (once per minute): a flapping link must not spam 'connected'.
      notify('info', 'connected', 'Varrenmoor Bridge connected.');
      return;
    }
    if (!m.id) return;
    try { ws.send(JSON.stringify({ id: m.id, result: await handle(m.op, m.args ?? {}) })); }
    catch (e) { ws.send(JSON.stringify({ id: m.id, error: String(e?.message ?? e) })); }
  };
  ws.onclose = (ev) => {
    if (socket === ws) socket = null;
    // 4002 = the relay replaced this client with a newer GM tab. Reconnecting would evict that tab in turn and both would
    // fight forever (one "connected" notice per second). Stay disconnected; reloading this tab (F5) or toggling the
    // settings takes the connection back on purpose.
    if (ev && ev.code === 4002) {
      evicted = true;
      notify('warn', 'evicted', 'Varrenmoor Bridge: another GM tab took over the connection, so this tab disconnected. Close the extra GM tab, or press F5 here to take it back.');
      return;
    }
    // 4005 = the relay does not accept this device any more (revoked, expired, or the relay was reset). Forget it and stop: retrying cannot help.
    if (dev && ev && ev.code === 4005) {
      evicted = true; saveDevice(null);
      notify('warn', 'revoked', 'Varrenmoor Bridge: the relay no longer accepts this browser (' + (ev.reason || 'revoked or expired') + '). Pair again in the module settings, or enter the module token.', true);
      return;
    }
    if (ev && ev.code === 4008) retry = 30000;     // locked out for a minute after repeated failures
    // paired, but the relay never answered several times in a row: its LAN address may have changed. Look for the same relay id nearby (opt-in scan, at most once per 10 min).
    if (dev && !welcomed && ++unreachable >= 3 && Date.now() - lastRelocate > 600000) {
      lastRelocate = Date.now();
      Pair.findRelay({ candidates: [], hostname: location.hostname, scan: true, relayId: dev.relayId }, (...a) => fetch(...a)).then((f) => { if (f && f.host !== dev.host) { saveDevice({ ...dev, host: f.host }); retry = 1000; } }).catch(() => {});
    }
    timer = setTimeout(connect, retry); retry = Math.min(retry * 2, 30000);
  };
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
