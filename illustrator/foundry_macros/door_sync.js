// Varrenmoor: Door sync - keeps the Foundry WALL doors (push-walls, flags.varrenmoor.doorId) and the 3D MODEL doors (tile flag levels-3d-preview.modelDoors.<doorId>.ds) in step, both ways.
// Install: python illustrator/generators/foundry_push.py install-door-sync   (or the Foundry tab button). Run the macro once per GM session to switch on, again to switch off;
// Click mode switches it on by itself. The hooks live in the GM browser tab that ran it (they vanish on a reload: run the macro again). Only the ACTIVE GM acts, so two GM tabs do not fight.
//   model door opened/closed (native click, Click mode, a flag edit)  -> the wall door with the same doorId gets ds OPEN(1)/CLOSED(0)/LOCKED(2)
//   wall door opened/closed (door control, wall config)               -> the model door flag ds is set ("1"/"0"/"2"); the 3D tile animates the door by itself
// Loop guard: our own writes carry the option vbDoorSync; every write is skipped when the other side already has the wanted state.
// One-shot reconcile of state that already exists: foundry_push.py sync-doors --scene-uuid U --apply (model state wins; an open wall door with no model entry opens the model door).
// Macro run with {mode:"on"} only ever switches ON (used by Click mode).
const KEY = "__vbDoorSync";
const root = (typeof window !== "undefined" ? window : globalThis);
const MODEL = "levels-3d-preview";

const core = {
  // model ds ("0" closed, "1" open, "2" locked) -> wall ds (CONST.WALL_DOOR_STATES CLOSED 0, OPEN 1, LOCKED 2)
  wallDs: (ds) => { const n = Number(ds); return n === 1 ? 1 : n === 2 ? 2 : 0; },
  modelDs: (ds) => String(Number(ds) === 1 ? 1 : Number(ds) === 2 ? 2 : 0),
  // update `changes` of a Tile -> {doorId: ds} for the modelDoors entries it touches (nested or flattened keys)
  modelChanges(changes) {
    const out = {};
    const md = changes?.flags?.[MODEL]?.modelDoors;
    if (md) for (const [id, v] of Object.entries(md)) if (v && v.ds !== undefined) out[id] = v.ds;
    for (const [k, v] of Object.entries(changes || {})) {
      const m = /^flags\.levels-3d-preview\.modelDoors\.(.+)\.ds$/.exec(k);
      if (m) out[m[1]] = v;
    }
    return out;
  },
};

if (root[KEY]) {
  if (typeof scope !== "undefined" && scope && scope.mode === "on") return;
  root[KEY].off();
  return ui.notifications.info("Door sync OFF.");
}
if (!game.user.isGM) return ui.notifications.warn("Door sync is a GM tool.");

const isActiveGM = () => !game.users.activeGM || game.users.activeGM.isSelf;
const walls = (scene, doorId) => scene.walls.contents.filter((w) => w.door > 0 && w.flags?.varrenmoor?.doorId === doorId);
// the tile that owns a door id: the one whose flag already lists it, else the 3D tile with a door node of that id
function tileFor(scene, doorId) {
  const L = game.Levels3DPreview;
  const withFlag = scene.tiles.contents.find((t) => t.flags?.[MODEL]?.modelDoors?.[doorId]);
  if (withFlag) return withFlag;
  for (const t3 of Object.values(L?.tiles || {})) {
    let hit = false;
    t3.mesh?.traverse?.((o) => { if (o.userData?.isDoor && o.userData.doorId === doorId) hit = true; });
    if (hit) return t3.document || t3.tile;
  }
  return null;
}

async function onTile(tile, changes, options) {
  if (options?.vbDoorSync || !isActiveGM() || tile.parent?.id !== canvas.scene?.id) return;
  for (const [id, ds] of Object.entries(core.modelChanges(changes))) {
    const want = core.wallDs(ds);
    const ups = walls(tile.parent, id).filter((w) => w.ds !== want).map((w) => ({ _id: w.id, ds: want }));
    if (ups.length) await tile.parent.updateEmbeddedDocuments("Wall", ups, { vbDoorSync: true });
  }
}

async function onWall(wall, changes, options) {
  if (options?.vbDoorSync || !isActiveGM() || changes.ds === undefined || wall.parent?.id !== canvas.scene?.id) return;
  const id = wall.flags?.varrenmoor?.doorId;
  if (!id || !(wall.door > 0)) return;
  const tile = tileFor(wall.parent, id);
  if (!tile) return;
  const want = core.modelDs(wall.ds);
  if (String(tile.flags?.[MODEL]?.modelDoors?.[id]?.ds ?? "0") === want) return;
  await tile.update({ [`flags.${MODEL}.modelDoors.${id}.ds`]: want }, { vbDoorSync: true });
}

const hT = Hooks.on("updateTile", (...a) => onTile(...a).catch((e) => console.error("vb door sync", e)));
const hW = Hooks.on("updateWall", (...a) => onWall(...a).catch((e) => console.error("vb door sync", e)));
root[KEY] = { core, off() { Hooks.off("updateTile", hT); Hooks.off("updateWall", hW); delete root[KEY]; } };
ui.notifications.info("Door sync ON: wall doors and model doors follow each other (this GM tab only; run the macro again after a reload).");
