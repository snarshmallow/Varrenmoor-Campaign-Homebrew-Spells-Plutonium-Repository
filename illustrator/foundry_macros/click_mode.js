// Varrenmoor: Click mode - click a ROOF in the 3D canvas to hide/show just that roof (GM), and click a DOOR to open/close it on any layer. ONE macro, toggles on/off.
// Install: python illustrator/generators/foundry_push.py install-click-macros   (or paste this text into a new Script macro). Nothing is saved except the roof tile's own `hidden` flag.
//
// ROOFS (GM only). Roof tiles carry flags.varrenmoor.roof = {mode, buildings, ...} (written by push-models). A click raycasts through the 3D Canvas camera (Levels3DPreview.THREE)
//   against the roof tiles only, finds the glTF node `<building>_roof` under the cursor and:
//   * per_building mode (one tile per building): toggles that tile's `hidden` (saved with the scene, every player sees it; the GM sees a hidden roof as a 50% ghost and can click the ghost to show it again).
//   * per_scene mode (one tile holds every roof): a plain click hides THAT building's roof node on THIS GM screen only (outlined, nothing saved, restored when the mode is switched off).
//     Shift+click toggles the whole roof tile for everybody (the same as the "Roofs: toggle all" macro).
// DOORS. Level 3D Canvas already opens a door on a left click, but only while the Tokens layer is active and (for players) a controlled token is within 3 squares. In click mode a click on a door node
//   (extras isDoor) also works from the other layers, through the module's own Socket.toggleDoor (same permission checks: the user needs the WALL_DOORS permission, the game must not be paused for players).
// A short click only (moved < 5 px, left button, no Ctrl/Alt). Re-running the macro switches the mode off.
const MODE_KEY = "__vbClickMode";
const root = (typeof window !== "undefined" ? window : globalThis);
const L0 = game.Levels3DPreview;

// ---- pure helpers (unit tested in click_mode.test.mjs; they take plain objects) ----
const core = {
  roofName: (n) => { const m = /^(.+)_roof$/.exec(n || ""); return m ? m[1] : null; },
  // chain = [hit object, parent, ..., tile root]; every element {name, userData}. -> {kind:'door'|'roof', ...} or null
  classify(chain, tileFlags) {
    const door = chain.find((o) => o.userData && o.userData.isDoor);
    if (door) return { kind: "door", doorId: door.userData.doorId ?? null };
    const roofFlag = tileFlags && tileFlags.roof;
    if (!roofFlag) return null;
    const node = chain.find((o) => core.roofName(o.name) !== null);
    const building = node ? core.roofName(node.name) : null;
    const nb = (roofFlag.buildings || []).length;
    const whole = roofFlag.mode === "per_building" || roofFlag.scope === "building" || nb === 1 || !node;
    return { kind: "roof", building, node: node || null, whole };
  },
  // hits sorted by distance [{distance, chain, tileFlags, ...}] -> first classified hit
  pick(hits, skipDoors) {
    for (const h of hits.slice().sort((a, b) => a.distance - b.distance)) {
      const c = core.classify(h.chain, h.tileFlags);
      if (!c) continue;
      if (c.kind === "door" && skipDoors) continue;
      return { ...c, hit: h };
    }
    return null;
  },
  isShortClick: (down, up, tol = 5) => !!down && Math.hypot(up.x - down.x, up.y - down.y) < tol,
};

if (root[MODE_KEY]) {                                   // second run: switch off
  root[MODE_KEY].off();
  return ui.notifications.info("Click mode OFF.");
}
if (!L0 || !L0.interactionManager || !L0.renderer) return ui.notifications.warn("Click mode needs a scene in 3D Canvas mode.");

const dom = L0.renderer.domElement;
const peeks = new Map();                                // per_scene local hides: node uuid -> {node, helper}
let down = null;

const tileOf = (obj) => { let o = obj; while (o) { if (o.userData && o.userData.entity3D) return o.userData.entity3D; o = o.parent; } return null; };
const chainOf = (obj) => { const c = []; let o = obj; while (o) { c.push(o); o = o.parent; } return c; };

function raycast(ev) {
  const L = game.Levels3DPreview, T = L.THREE;
  const r = dom.getBoundingClientRect();
  const ndc = new T.Vector2(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
  const rc = new T.Raycaster();
  rc.setFromCamera(ndc, L.camera);
  const meshes = [], seen = new Set();
  for (const id of Object.keys(L.tiles)) {
    const t = L.tiles[id]; const doc = t.document || t.tile; const f = doc?.flags?.varrenmoor;
    if (!t.mesh || seen.has(t.mesh)) continue;
    const tokenLayer = canvas.activeLayer?.options?.objectClass?.embeddedName === "Token";     // the module itself handles door clicks there
    const isRoof = !!f?.roof;
    if (isRoof ? game.user.isGM : !tokenLayer) { meshes.push(t.mesh); seen.add(t.mesh); }
  }
  const hits = [];
  for (const h of rc.intersectObjects(meshes, true)) {
    if (!h.object.visible) continue;
    const t3 = tileOf(h.object); if (!t3) continue;
    const doc = t3.document || t3.tile;
    hits.push({ distance: h.distance, object: h.object, tile3d: t3, doc, chain: chainOf(h.object).slice(0, chainOf(h.object).indexOf(t3.mesh) + 1), tileFlags: doc?.flags?.varrenmoor });
  }
  return hits;
}

function setPeek(node, hide) {
  const T = game.Levels3DPreview.THREE;
  const cur = peeks.get(node.uuid);
  if (!hide) { if (cur) { node.visible = true; cur.helper?.parent?.remove(cur.helper); peeks.delete(node.uuid); } return; }
  if (cur) return;
  node.visible = false;
  let helper = null;
  try { node.visible = true; helper = new T.Box3Helper(new T.Box3().setFromObject(node), new T.Color(0xffb000)); node.visible = false; game.Levels3DPreview.scene.add(helper); } catch (e) { node.visible = false; }
  peeks.set(node.uuid, { node, helper });
}

async function onClick(ev) {
  const L = game.Levels3DPreview;
  const picked = core.pick(raycast(ev), canvas.activeLayer?.options?.objectClass?.embeddedName === "Token");
  if (!picked) return;
  const { hit } = picked;
  if (picked.kind === "door") {
    return L.socket.toggleDoor({ tileId: hit.doc.id, sceneId: canvas.scene.id, userId: game.user.id, subDoorId: picked.doorId });
  }
  if (!game.user.isGM) return;
  if (picked.whole || ev.shiftKey) {
    const tile = canvas.scene.tiles.get(hit.doc.id);
    await canvas.scene.updateEmbeddedDocuments("Tile", [{ _id: tile.id, hidden: !tile.hidden }]);
    ui.notifications.info(`${tile.hidden ? "Hid" : "Showed"} ${picked.building ?? "roof tile"}.`);
  } else {
    const hidden = peeks.has(picked.node.uuid);
    setPeek(picked.node, !hidden);
    ui.notifications.info(`${hidden ? "Showed" : "Hid on your screen only"}: ${picked.building} (per_scene roofs are one tile; Shift+click hides the whole tile for everyone).`);
  }
}

const onDown = (ev) => { down = ev.button === 0 ? { x: ev.clientX, y: ev.clientY } : null; };
const onUp = (ev) => {
  const d = down; down = null;
  if (ev.button !== 0 || ev.ctrlKey || ev.altKey || !core.isShortClick(d, { x: ev.clientX, y: ev.clientY })) return;
  onClick(ev).catch((e) => console.error("vb click mode", e));
};
dom.addEventListener("pointerdown", onDown, true);
dom.addEventListener("pointerup", onUp, true);
root[MODE_KEY] = {
  core, peeks,
  off() { dom.removeEventListener("pointerdown", onDown, true); dom.removeEventListener("pointerup", onUp, true); for (const p of [...peeks.values()]) setPeek(p.node, false); delete root[MODE_KEY]; },
};
ui.notifications.info("Click mode ON: click a roof to hide/show it (GM), click a door to open/close it. Run the macro again to switch off.");
