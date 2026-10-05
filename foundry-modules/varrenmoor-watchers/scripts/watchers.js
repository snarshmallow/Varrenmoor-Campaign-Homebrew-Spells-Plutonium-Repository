// Varrenmoor Watchers: turns eyeballs toward the nearest player token, client-side (every user sees their own view).
//
// Convention (see foundry-3d/generators/ossuary_watcher_painting.py): inside a 3D Canvas tile's glTF, nodes named
// "watcher_eye_*" (extras: watcher=1, maxAngle=degrees) are separate meshes whose origin is the eyeball centre and whose
// local +Z points out of the front of the painting at rest. We rotate each toward the nearest player-owned token the
// viewer can see, limited to maxAngle from the rest pose, smoothed, and only ~20 times a second while the 3D canvas
// is active. No per-frame allocations beyond a few vectors; with no watchers in the scene the loop does nothing.
//
// Uses only objects 3D Canvas already exposes: game.Levels3DPreview.{tiles,tokens,_active,_ready}, Tile3D.mesh, Token3D.mesh.

const MOD = "varrenmoor-watchers";
const INTERVAL_MS = 50;          // ~20 Hz
const RANGE = 3.0;               // 3D units; 1 grid square (100 px) = 0.1 units, so 30 squares
const HEAD_UP = 0.07;            // aim a little above the token's mesh position (about head height)
const SMOOTH = 0.22;             // fraction of the remaining turn applied per update

let eyes = [];                   // { o, restQ, max }
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
      if (o.userData?.watcher || (o.name && o.name.startsWith("watcher_eye"))) {
        eyes.push({ o, restQ: o.quaternion.clone(), max: ((o.userData?.maxAngle ?? 45) * Math.PI) / 180 });
      }
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
  const { o, restQ, max } = e;
  const V = o.position.constructor;
  const Q = o.quaternion.constructor;
  const pos = o.getWorldPosition(new V());
  let best = null;
  let bestD = RANGE;
  for (const p of targets) {
    const d = pos.distanceTo(p);
    if (d < bestD) { bestD = d; best = p; }
  }
  let desired = restQ;
  if (best) {
    const dir = new V(best.x, best.y + HEAD_UP, best.z).sub(pos).normalize();
    const parentInv = o.parent.getWorldQuaternion(new Q()).invert();
    const local = dir.applyQuaternion(parentInv).normalize();
    const forwardRest = new V(0, 0, 1).applyQuaternion(restQ);
    const angle = forwardRest.angleTo(local);
    desired = new Q().setFromUnitVectors(new V(0, 0, 1), local);
    if (angle > max) desired = restQ.clone().slerp(desired, max / angle);   // keep the pupils inside the sockets
  }
  o.quaternion.slerp(desired, SMOOTH);
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
