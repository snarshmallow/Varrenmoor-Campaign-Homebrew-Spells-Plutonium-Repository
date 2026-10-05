// Varrenmoor Watchers: turns eyeballs toward the nearest player token, client-side (every user sees their own view).
//
// Convention (see foundry-3d/generators/_painting.py): meshes named "watcher_eye_*" (glTF extras: watcher=1,
// maxAngle=degrees, lookDir=[x,y,z] = the direction the pupil faces at rest, in model/glTF space) can sit anywhere in
// a tile's model. 3D Canvas may bake node transforms into the geometry, so we never assume the node origin is the eye:
// each eye is rotated about its own geometric centre (bounding-sphere centre) and the position is corrected so that
// centre stays put. Rotation is limited to maxAngle from the rest direction, smoothed, and updated ~20 times a second
// only while the 3D canvas is active. With no watchers in the scene the loop does nothing.

const MOD = "varrenmoor-watchers";
const INTERVAL_MS = 50;          // ~20 Hz
const RANGE = 3.0;               // 3D units; 1 grid square (100 px) = 0.1 units, so 30 squares
const HEAD_UP = 0.07;            // aim a little above the token's mesh position (about head height)
const SMOOTH = 0.22;             // fraction of the remaining turn applied per update

let eyes = [];                   // { o, restPos, restQ, pivot, restForward, max }
let raf = 0;
let last = 0;

const lv = () => game.Levels3DPreview;

function collect() {
  eyes = [];
  const tiles = lv()?.tiles;
  if (!tiles) return;
  for (const tile of Object.values(tiles)) {
    const root = tile?.mesh;
    if (!root) continue;
    root.traverse((o) => {
      if (!o.isMesh || !(o.userData?.watcher || (o.name && o.name.startsWith("watcher_eye")))) return;
      const V = o.position.constructor;
      if (!o.geometry.boundingSphere) o.geometry.computeBoundingSphere();
      const look = o.userData?.lookDir ?? [0, 0, 1];
      eyes.push({
        o,
        restPos: o.position.clone(),
        restQ: o.quaternion.clone(),
        pivot: o.geometry.boundingSphere.center.clone(),                         // eye centre in the mesh's local space
        restForward: new V(look[0], look[1], look[2]).normalize(),
        max: ((o.userData?.maxAngle ?? 45) * Math.PI) / 180,
      });
    });
  }
}

function targetPositions() {
  const out = [];
  const tokens = lv()?.tokens;
  if (!tokens) return out;
  for (const t of canvas.tokens?.placeables ?? []) {
    if (!t.visible || !t.actor?.hasPlayerOwner) continue;
    const m = tokens[t.id]?.mesh;
    if (m) out.push(m.position);
  }
  return out;
}

function aim(e, targets) {
  const { o, restPos, restQ, pivot, restForward, max } = e;
  const V = o.position.constructor;
  const Q = o.quaternion.constructor;
  // eye centre in the world, from its rest transform (so aiming never drifts the eye)
  const centreLocal = pivot.clone().multiply(o.scale);                          // pivot in parent space offset (scaled)
  const centreRest = restPos.clone().add(centreLocal.clone().applyQuaternion(restQ));
  const centreWorld = o.parent.localToWorld(centreRest.clone());
  let best = null;
  let bestD = RANGE;
  for (const p of targets) {
    const d = centreWorld.distanceTo(p);
    if (d < bestD) { bestD = d; best = p; }
  }
  let turn = new Q();                                                           // identity = rest pose
  if (best) {
    const goal = new V(best.x, best.y + HEAD_UP, best.z);
    const dir = o.parent.worldToLocal(goal).sub(centreRest).normalize();        // direction in the parent's space
    const fwd = restForward.clone().applyQuaternion(restQ);                     // rest direction in the parent's space
    const angle = fwd.angleTo(dir);
    turn = new Q().setFromUnitVectors(fwd, dir);
    if (angle > max) turn = new Q().slerp(turn, max / angle);                   // keep the pupils inside the sockets
  }
  const q = turn.multiply(restQ);
  o.quaternion.slerp(q, SMOOTH);
  // rotate about the eye centre: keep that point fixed while the orientation changes
  const rotatedCentre = pivot.clone().multiply(o.scale).applyQuaternion(o.quaternion);
  o.position.copy(centreRest).sub(rotatedCentre);
}

function step(now) {
  raf = requestAnimationFrame(step);
  if (now - last < INTERVAL_MS) return;
  last = now;
  const L = lv();
  if (!L?._active || !L._ready || document.hidden) return;
  if (!eyes.length || eyes.some((e) => !e.o.parent)) {   // tiles were rebuilt (update/reload): look for the eyes again
    collect();
    if (!eyes.length) return;
  }
  const targets = targetPositions();
  for (const e of eyes) aim(e, targets);
}

function start() {
  if (raf || !game.settings.get(MOD, "enabled")) return;
  raf = requestAnimationFrame(step);
}

function stop() {
  cancelAnimationFrame(raf);
  raf = 0;
  eyes = [];
}

Hooks.once("init", () => {
  game.settings.register(MOD, "enabled", {
    name: "Eyes follow players",
    hint: "Turn off if you ever need every last frame; the effect is a few vector operations 20 times a second.",
    scope: "client", config: true, type: Boolean, default: true,
    onChange: (on) => (on ? (collect(), start()) : stop()),
  });
});

Hooks.on("3DCanvasSceneReady", () => { collect(); start(); });
Hooks.on("canvasTearDown", stop);
Hooks.on("updateTile", () => setTimeout(collect, 600));
Hooks.once("ready", () => {
  const mod = game.modules.get(MOD);
  if (mod) mod.api = { collect, eyes: () => eyes, targets: targetPositions };   // for debugging from the console
});
