import * as Pair from './pairing.js';
import * as Crypto from './seccrypto.js';

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
  game.settings.register(MOD, 'relayUrl', { name: 'Relay URL (manual token fallback)', hint: 'e.g. wss://name.trycloudflare.com/module. Leave at the default: the relay is then looked for beside Foundry (this page\'s own host, relay port below). Only used with the Module token below.', scope: 'client', config: true, type: String, default: 'ws://127.0.0.1:3030/module', onChange: () => connect() });
  game.settings.register(MOD, 'token', { name: 'Module token (fallback, not needed when paired)', hint: 'BRIDGE_MODULE_TOKEN from the relay. Pairing replaces this: nothing to copy.', scope: 'client', config: true, type: String, default: '', onChange: () => connect() });
  game.settings.register(MOD, 'relayPort', { name: 'Relay port', hint: 'Port the relay listens on (default 3030). With no address typed, the relay is expected on this page\'s own host at this port, e.g. Foundry at http://10.0.0.5:30000 means relay 10.0.0.5:3030.', scope: 'client', config: true, type: Number, default: 3030 });
  game.settings.register(MOD, 'pairHost', { name: 'Relay address (optional)', hint: 'Only if the relay is NOT on the Foundry PC: host or host:port of the relay PC, e.g. 10.0.0.20:3030. Blank: found automatically beside Foundry; the Pair button also scans this PC\'s /24 network.', scope: 'client', config: true, type: String, default: '' });
  game.settings.register(MOD, 'autoPair', { name: 'Ask for pairing automatically', hint: 'When this browser is not paired, ask the relay (if it allows auto-requests) as soon as the GM page loads and show a code to confirm on the Illustrator panel or relay window. Needs the Foundry page opened as http://<host>:30000.', scope: 'client', config: true, type: Boolean, default: true });
  game.settings.register(MOD, 'clientId', { name: 'Browser id (internal)', scope: 'client', config: false, type: String, default: '' });
  game.settings.register(MOD, 'deviceAuth', { name: 'Paired device (internal)', scope: 'client', config: false, type: String, default: '' });
  game.settings.register(MOD, 'allowWrites', { name: 'Allow writes', hint: 'Permit create/update requests, and delete of documents that carry the pipeline flag (flags.varrenmoor.pipelineId) only. Leave off for read-only.', scope: 'world', config: true, type: Boolean, default: false });
});

Hooks.once('ready', () => {
  try { const m = game.modules.get(MOD); if (m) m.api = { pair: (o) => startPairing({ scan: true, ...o }), unpair: () => forgetDevice(), status: () => ({ paired: !!readDevice(), connected: !!(socket && socket.readyState === 1) }) }; } catch { /* no api */ }
  if (!game.user.isGM) return;
  connect();
  // Not paired and no manual token: look for the relay beside Foundry (this page's own host, relay port) or at the typed address and, when the relay allows auto-requests,
  // ask for pairing right away. Never scans the network on its own; one attempt per page load.
  if (!readDevice() && !game.settings.get(MOD, 'token') && game.settings.get(MOD, 'autoPair') !== false) startPairing({ scan: false, silent: true, auto: true });
});

// ---- LAN pairing (0.5.0, encrypted handshake): no tokens to type. The relay (panel / relay window) shows "Approve this device?" with the same code this browser shows; the per-device
// secret it issues arrives sealed under a key only this browser and the relay derive, and is kept in this browser's client-scoped setting 'deviceAuth' only. It is never sent again:
// every connection proves it with an HMAC challenge-response. The manual Module token path below keeps working as a fallback.
Hooks.on?.('renderSettingsConfig', (app, html) => {
  try {
    const root = html instanceof HTMLElement ? html : html[0] ?? html;
    const input = root.querySelector(`[name="${MOD}.pairHost"]`);
    if (!input || root.querySelector('.vb-pair-buttons')) return;
    const row = document.createElement('div'); row.className = 'form-group vb-pair-buttons';
    row.innerHTML = '<label>Pairing</label><div class="form-fields"><button type="button" data-vb="pair"><i class="fa-solid fa-link"></i> Pair with relay</button> <button type="button" data-vb="unpair">Forget pairing</button></div><p class="hint">Pair: finds the relay beside Foundry and asks for approval (Illustrator panel or relay window). No token is typed.</p>';
    row.querySelector('[data-vb="pair"]').addEventListener('click', () => startPairing({ scan: true }));
    row.querySelector('[data-vb="unpair"]').addEventListener('click', () => forgetDevice());
    (input.closest('.form-group') ?? input).after(row);
  } catch { /* settings UI differs: the console API still works */ }
});

const readDevice = () => { try { const d = JSON.parse(game.settings.get(MOD, 'deviceAuth') || 'null'); return d && d.host && d.deviceId && d.secret ? d : null; } catch { return null; } };
const pageIsHttps = () => String(globalThis.location?.protocol || 'http:').toLowerCase() === 'https:';
const relayPort = () => Number(game.settings.get(MOD, 'relayPort')) || Pair.DEFAULT_PORT;
async function clientId() { let id = game.settings.get(MOD, 'clientId'); if (!id) { id = Crypto.b64u(Crypto.randomBytes(12)); try { await game.settings.set(MOD, 'clientId', id); } catch { /* not persisted: still unique for this page load */ } } return id; }
const saveDevice = (d) => game.settings.set(MOD, 'deviceAuth', d ? JSON.stringify(d) : '');
async function forgetDevice() { await saveDevice(null); notify('info', 'unpaired', 'Varrenmoor Bridge: pairing forgotten on this browser (revoke it on the relay too, in the Illustrator panel).', true); connect(); }

// Strings that come from the relay (error text, close reasons) are untrusted: only plain characters, short, before they go into a notification.
const safeText = (s) => String(s ?? '').replace(/[^A-Za-z0-9 .,:;_()\/-]/g, '').slice(0, 100);
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let pairingRun = null, codeDialog = null;
function showCode({ code, host }, state) {
  state.codeInfo = { code, host };
  if (codeDialog) { try { codeDialog.render({ force: true }); return; } catch { codeDialog = null; } }
  const body = `<p>Pairing with the relay at <b>${escapeHtml(host)}</b> (encrypted handshake).</p><p>Open the Illustrator panel (Foundry tab) or look at the relay window. It must show this exact code, and only then press <b>Approve</b> there:</p><p style="font-size:2em;letter-spacing:.15em;text-align:center"><b>${escapeHtml(code)}</b></p><p class="hint">If the code differs, press Deny there: someone else on the network is asking.</p>`;
  try {
    const D = foundry.applications.api.DialogV2;
    codeDialog = new D({ window: { title: 'Pair Varrenmoor Bridge' }, content: body, buttons: [{ action: 'cancel', label: 'Cancel', default: true, callback: () => { state.cancelled = true; } }], rejectClose: false });
    codeDialog.render({ force: true });
  } catch { notify('info', 'pair-code', `Varrenmoor Bridge pairing code ${code}: approve on the relay only if it shows the same code.`, true); }
}
async function startPairing({ scan = false, silent = false, auto = false } = {}) {
  if (!game.user?.isGM) { if (!silent) notify('warn', 'pair-gm', 'Only a GM can pair the bridge.', true); return { ok: false, reason: 'not a GM' }; }
  // one request per browser at a time: a Pair click while the automatic request is still waiting shows the SAME code again instead of filing a second request
  if (pairingRun) { if (pairingRun.codeInfo && !silent) showCode(pairingRun.codeInfo, pairingRun); return { ok: false, reason: 'already pairing', reused: true }; }
  // players and the Cloudflare route use https://foundry.<domain>: the relay refuses pairing from there on purpose, and an https page cannot reach it anyway (mixed content)
  if (pageIsHttps()) { if (!silent) notify('warn', 'pair-https', 'Varrenmoor Bridge: pairing is only possible from a Foundry page opened over the local network as http://<foundry-PC>:30000, not through the https/Cloudflare address. Open that LAN address and press Pair again.', true); return { ok: false, reason: 'https page' }; }
  try { Crypto.selfTest(); } catch (e) { if (!silent) notify('warn', 'pair-crypto', 'Varrenmoor Bridge: ' + (e?.message || e) + '. Pairing is disabled; re-copy the module files.', true); return { ok: false, reason: 'crypto self-test failed' }; }
  const state = pairingRun = { cancelled: false };
  try {
    const found = await Pair.findRelay({ candidates: Pair.candidateHosts({ pairHost: game.settings.get(MOD, 'pairHost'), relayUrl: game.settings.get(MOD, 'relayUrl'), stored: readDevice(), pageHost: location.hostname, pageProtocol: location.protocol, relayPort: relayPort() }), hostname: location.hostname, scan }, (...a) => fetch(...a));
    if (!found) { if (!silent) notify('warn', 'pair-none', `Varrenmoor Bridge: no relay found beside Foundry (${location.hostname}:${relayPort()}). Is it running? If it is on another PC, type its address (host:3030) in the setting "Relay address".`, true); return { ok: false, reason: 'no relay found' }; }
    if (!found.info.pairing) { if (!silent) notify('warn', 'pair-off', `Varrenmoor Bridge: the relay at ${found.host} is running but pairing is switched off. Switch it on in the Illustrator panel (Foundry tab > Pairing), then press Pair again.`, true); return { ok: false, reason: 'pairing is off' }; }
    if (auto && !found.info.autoRequest) return { ok: false, reason: 'relay does not allow auto-requests' };
    const res = await Pair.runPairing({ host: found.host, device: Pair.describeDevice({ user: game.user, world: game.world, location, ua: navigator.userAgent, clientId: await clientId() }), fetchFn: (...a) => fetch(...a),
      hooks: { onCode: (c) => showCode(c, state), cancelled: () => state.cancelled } });
    try { codeDialog?.close({ animate: false }); } catch { /* already closed */ } codeDialog = null;
    if (!res.ok) { notify('warn', 'pair-fail', `Varrenmoor Bridge pairing: ${safeText(res.reason)}.`, true); return res; }
    await saveDevice({ host: res.host, relayId: res.relayId, deviceId: res.deviceId, secret: res.secret, expiresAt: res.expiresAt });
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
let candidateHost = null;  // a relay found by the relocation scan: tried ONCE, and only saved as the new host after it proved it knows the device secret
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
  const dev = readDevice();   // a paired device wins over the manual token; the manual token stays as the fallback when not paired
  // manual-token URL: the launcher file, else a relay URL the user typed, else (zero config) the relay beside Foundry: this page's own host at the relay port (plain-http pages only)
  const typed = String(game.settings.get(MOD, 'relayUrl') || '').trim(), typedIsDefault = !typed || /^wss?:\/\/(127\.0\.0\.1|localhost|\[::1\]):3030\/module$/i.test(typed);
  const derived = Pair.deriveRelayHost({ pageHost: globalThis.location?.hostname, pageProtocol: globalThis.location?.protocol, relayPort: relayPort() });
  const tryHost = dev ? candidateHost : null; candidateHost = null;
  const url = dev ? Pair.wsUrlFor(tryHost || dev.host) : (game.settings.get(MOD, 'autoUrl') && await launcherUrl()) || (typedIsDefault && derived ? Pair.wsUrlFor(derived) : typed);
  if (gen !== generation || !url || !(dev || token)) return;
  const ws = new WebSocket(url);
  socket = ws;
  let welcomed = false;
  const auth = dev ? Pair.deviceAuth(dev) : null;
  ws.onopen = () => ws.send(JSON.stringify(dev ? auth.hello() : { type: 'hello', token }));
  ws.onmessage = async (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (!m || typeof m !== 'object' || Array.isArray(m)) return;
    if (m.type === 'challenge' && auth) { ws.send(JSON.stringify(auth.answer(m))); return; }
    if (m.type === 'welcome') {
      if (auth) {
        const w = auth.welcome(m);
        if (!w.ok) { evicted = true; try { ws.close(); } catch { /* closed */ } notify('warn', 'proof', 'Varrenmoor Bridge: ' + w.reason + '. Not connecting to it.', true); return; }
        // the relay rotates the device secret near expiry or on request from the panel (sealed under a key only we and the relay derive); keep the new one (the old works for 5 more minutes)
        // a relocated relay is adopted only now: it just proved it knows the device secret
        if (w.secret || tryHost) saveDevice({ ...dev, ...(tryHost ? { host: tryHost } : {}), ...(w.secret ? { secret: w.secret, expiresAt: w.expiresAt || dev.expiresAt } : {}) });
      }
      retry = 1000; welcomed = true; unreachable = 0;
      // Rate-limited (once per minute): a flapping link must not spam 'connected'.
      notify('info', 'connected', 'Varrenmoor Bridge connected.');
      return;
    }
    // Nothing is executed until the relay has been welcomed (paired mode: with a valid proof that it knows the device secret). A server that skips that sends ops straight away: drop it.
    if (!welcomed) { if (m.id) { notify('warn', 'no-welcome', 'Varrenmoor Bridge: the server sent a request before it proved itself. Closing the connection.', false); try { ws.close(); } catch { /* closed */ } } return; }
    if (!m.id || typeof m.op !== 'string') return;
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
    // The pairing is forgotten only when the close came over a relay-authenticated session (revoked while connected). A 4005 before the welcome is not proof of anything (a stranger
    // at that address can send it), so the credential is kept; the notice tells the GM to press "Pair with relay" (which replaces it) if the relay really is the right one.
    if (dev && ev && ev.code === 4005) {
      evicted = true;
      if (welcomed) { if (readDevice()?.deviceId === dev.deviceId) saveDevice(null); else return; }
      notify('warn', 'revoked', 'Varrenmoor Bridge: the relay no longer accepts this browser (' + safeText(ev.reason || 'revoked or expired') + '). ' + (welcomed ? 'Pair again in the module settings, or enter the module token.' : 'If you revoked it, press "Pair with relay" in the module settings (or "Forget pairing" first).'), true);
      return;
    }
    if (ev && ev.code === 4008) retry = 30000;     // locked out for a minute after repeated failures
    // paired, but the relay never answered several times in a row: its LAN address may have changed. Look for the same relay id nearby (opt-in scan, at most once per 10 min).
    if (dev && !welcomed && ++unreachable >= 3 && Date.now() - lastRelocate > 600000) {
      lastRelocate = Date.now();
      Pair.findRelay({ candidates: [], hostname: location.hostname, scan: true, relayId: dev.relayId }, (...a) => fetch(...a)).then((f) => { if (f && f.host !== dev.host) { candidateHost = f.host; retry = 1000; } }).catch(() => {});
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
