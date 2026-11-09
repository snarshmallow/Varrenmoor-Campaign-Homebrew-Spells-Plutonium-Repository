# Do we need Foundry wall documents in 3D scenes? (3D Canvas 9.0.29 source + live probes, 2026-11-09)

Short answer: **No, not for vision, light or sound polygons and not for 3D collision.** In our 3D scenes (object3dSight on, fog of war on, multithreading on) the vision/light/sound polygons are built by a web worker from the tile meshes that have the tile flag `sight: true`. **Wall documents are ignored by that worker** (live proof below), so the `push-walls` output does not clip a single light or vision polygon today. Tile `collision` already blocks token movement (GM and players) and respects open/closed model doors. Wall documents only remain useful for core movement blocking when a tile has collision off, door-icon UI, the single-thread fallback and terrain walls.

Source files are `Data/modules/levels-3d-preview/scripts/` on Vega (read over HTTP, nothing run on the server). All line numbers are from that 9.0.29 copy.

## 1. Doors
* A door = a glTF node with extras `isDoor`, `doorId`, `doorStyle`, `doorAnimateAngle` (radians) found by `Tile3D.setUpDoors` (`entities/tile3d.js:445-480`). The state lives in the tile flag `flags.levels-3d-preview.modelDoors.<doorId>.ds` ("0" closed, "1" open, "2" locked); whole-tile doors use `doorState` (tile3d.js:432-440).
* `setDoorsMaterials` (tile3d.js:485-575) reads the flag, animates the leaf (rotation/slide, `doorAnimationDuration`), and sets per node `userData.isOpen`, `userData.sight = isOpen ? false : tile.sight`, `userData.collision = isOpen ? false : tile.collision` (lines 500-507). Then `sendToWorker()` (574) re-sends the WHOLE tile to the vision worker.
* Opening: native left click `Tile3D._onClickLeft` (tile3d.js:2065-2080) only on the Tokens layer with a controlled token within range (`isToFar`, error `toofarfromdoor`) -> `Socket.toggleDoor`. `Socket.toggleDoor` (`main.js:1914-1950`) runs only on a GM client (a player's call is forwarded; warns if no GM is connected), requires `user.can("WALL_DOORS")`, refuses when the game is paused for non-GM, refuses a locked door (ds 2: plays the `lock` sound), otherwise `tile.setFlag(... modelDoors.<id>.ds, 0<->1)` and plays the open/close sound from `CONFIG.Wall.doorSounds[tile flag doorSound]`. GM right click toggles locked (tile3d.js:2100+). Secret doors (`doorType 2`) are hidden from players' clicks.
* Verified live (Dyers): toggleDoor flips the flag "0"<->"1" and the 3D leaf, see section 4.

## 2. Sight / vision / light / sound for 3D objects
* Tile flag `sight` (default true in the module, our pack tiles are pushed false: `tile3d.js:409`). `object3dSight` is a SCENE flag (`main.js:828`, our `3d` mode writes it, `foundry_push.py SCENE_MODES`).
* `ClockwiseSweepPolygon._compute` is wrapped for every polygon type except `universal` (`wrappers.js:26`, `computePolygonDispatch` 203-210). So **sight, light and sound** polygons (token vision, AmbientLight shapes, AmbientSound shapes) all go through it. With `object3dSight` + fog of war (`main.js:772`) + `CONFIG.useMultithreading` (`main.js:274`, default true) the wrapper calls `wrapped()` (the wall-based polygon), then **overwrites `this.points`** with the worker's result (`_computePolygonMultithreaded`, wrappers.js:212-262): 100 rays per source (`raycastWorker.js:124`), 160 ms budget (133).
* The worker only knows tile meshes: `sendToWorker` (tile3d.js:222-252) sends a tile when `sight` is true (or it has glTF tags and is a door tile); `workers.enabled` = `useMultithreading && object3dSight` (`helpers/workers.js:15-17`). Non-door tiles are merged into one BVH mesh (`raycastWorker.js:200-215`), door tiles are kept unmerged and raycast per call (`raycastWorker.js:82-93,190`). **Wall documents are never sent to the worker.**
* Per door node: in the worker `child.userData.sight = !child.userData.isOpen` (raycastWorker.js:72-73), so an open model door lets the ray through; main-thread rays use the same userData (tile3d.js:506).
* Main-thread fallback (client with multithreading off): per-angle `computeSightCollision` against `_sightCollisions.sight` which contains tile meshes with sight AND wall meshes with `document.sight >= 10` (`handlers/interactionManager.js:60-120`, wall at 109-110). Only in this fallback do wall documents occlude vision/light/sound.
* `forceSightCollisions` (`interactionManager.js:35`) is the un-debounced `generateSightCollisions` (rebuilds the move/sight/camera mesh arrays; ~0.005 ms measured). `sightMeshComplexity` (tile3d.js:370, `helpers.getSightMesh` 270-299): each tile gets a cloned "sight mesh" (always, flag or not); complexity < 1 decimates it (`simplify.modify`) at load time, and that proxy is what the move and sight rays hit.
* `containsWrapper` (wrappers.js:34-53): after the core test, token-vs-token detection additionally ray-tests `computeSightCollision(origin, target, "sight"|"move")` against the 3D sets.
* The visible fog/"explored" masks are drawn from the vision polygons (`systems/Fog.js:105`, `canvas.masks.vision`), so tile sight also drives fog exploration. The 3D scene's own lighting is separate: `Light3D` is a three.js light, `castShadow` only if the light flag and the client setting `shadowQuality` > 0 (`entities/light3d.js:149`), which uses real geometry irrespective of `sight`.
* AmbientSound: same polygon path (type "sound"), so by code tile `sight` clips sound radii too. NOT tested (the Dyers scene has no AmbientSound).

## 3. Movement
* `collision` flag (tile3d.js:407, default true; pack was false, now default on per layer): the sight mesh joins the `move` set (`interactionManager.js:100,111`). Used by: `Scene.testSurfaceCollision` wrapper (`wrappers.js:627-669`, modes any/all/closest, combined with the core wall test) which core token movement calls for **GM and players**; keyboard moves (`wrappers.js:417-460`); player drags (`token3d.js:600-626`, only `!isGM`) ; token grounding raycast (`token3d.js:1750-1770`); GM drag snapping to the surface under the cursor (`interactionManager.js:980-1016`). The scene flag `object3dSight` gates it.
* Open model doors set the node's `collision` false (tile3d.js:507), so the tile alone passes a token through an open door.

## 4. Live measurements (ZZ Dyers Walk 3D Test, GM tab, 14 merged layer tiles + 9 foliage chunks; everything restored)
Light shape area = polygon area / disc area, the 16 interior hearth lights, 100-ray worker polygons.
| state | result |
|---|---|
| baseline: 175 wall documents (closed), all sight flags false | all 72 lights are full 100-point discs (ratio 1.00), although 16 sit inside houses behind closed walls and extend past them. **Walls do not occlude light.** |
| buildings tile `sight:true`, no wall change | the 16 interior lights clip to 0.53 - 0.90 of the disc (mean 0.69). |
| 9 foliage tiles `sight:true` | lights clip too (min ratio 0.67); worker polygon mean 0.7 ms, max 1.7 ms (72 polygons). Heap 664 -> 739 MB while on. |
| buildings `sight:true` worker cost | 72 polygons: mean 3.2 ms, max 6.0 ms each, in the worker (not the render thread); off: 0.0 ms. JS heap 717 -> 744 MB. Main-thread sight ray (550 meshes in the set) 2.0 ms. |
| door toggle with sight on a merged tile | the whole tile is re-serialised for the worker: `toJSONClean` 19.7 ms on the main thread, 5.7 MB JSON (226 meshes, 72.6k tris) per toggle. Per-building tiles would be about 1/25 of that (estimate). |
| main-thread sight ray, token eye, outside -> through door | closed: hit at 64 % of the path (the leaf); model door opened: no hit; closed again: hit. So an open door lets vision through. |
| light polygon vs door state (worker) | NOT confirmed: one interior light's area stayed 0.659 closed/open (that light's ray fan is cut by walls elsewhere; I did not find a light with a clean line through the door). Needs a token with vision. |
| render thread | `renderer.render` CPU 0.29 ms (before) vs 0.37 ms (collision + 175 walls); flags do not change drawing cost. |
| 175 walls vs tile flags | walls: +177 geometries and wall meshes in the move set WITHOUT a BVH (move ray 1.1 -> 1.7 ms together with collision), zero effect on vision/light. Linear in wall count: a few thousand walls would be several ms per ray (extrapolation, not measured). Tile flags: no per-ray growth (BVH per tile). |

Token movement test (core `TokenDocument.move`, a temporary token, "Unconstrained Movement" ghost toggle switched OFF for the test, ON again afterwards; start 6 ft outside the door of bld_house_041, destination 3 ft inside; open-ground control moved 200/200 px):
| tile collision | wall door | model door | result |
|---|---|---|---|
| on | closed | closed | BLOCK 0/180 |
| on | OPEN | closed | BLOCK 0/180 (the 3D door leaf blocks) |
| on | closed | OPEN | BLOCK 119/180 (stopped at the wall door) |
| on | OPEN | OPEN | PASS 180/180 |
| off (walls only) | closed | closed | BLOCK 119/180 (stopped at the door wall) |
| off | OPEN | closed | PASS (model door looks closed, wall let it through) |
| off | closed | OPEN | BLOCK 119/180 |
| off | OPEN | OPEN | PASS |
| on, plain house wall (3D only raycast, token eye) | - | - | blocked; open ground: not blocked |
So tile collision alone blocks closed doors and plain walls and lets an open model door through (rows 2 and 4 are the "no wall documents" cases). The wall documents add nothing on top when collision is on, and when collision is off they create a model/wall mismatch (row 6). The GM is blocked too (this is the core move path), the ghost toggle bypasses all of it.
Cleanup done: temp token deleted, ghost toggle back ON, tile sight flags all false, model and wall doors closed, buildings collision true, active scene untouched, no reload.

## 5. What only wall documents can still do
* Core token movement blocking without 3D collision (flat scenes, or tiles with collision off), door icons/controls and sounds on the canvas, secret/locked door UI, one-way/terrain/ethereal wall types, wall-based tools (module integrations that read Wall documents), and the vision/light/sound polygon on any client where multithreading is off. In our 3D scenes none of these is needed for buildings and trees.
* Fog "exploration" is not a wall feature: it follows the vision polygon, which follows tile `sight` (section 2).
* Terrain-type blocking (limited sight walls): the worker has no limited concept; tile meshes are fully opaque to rays at eye height. A tree stand is therefore opaque where there is geometry at token eye height (trunks, hedges, low foliage), transparent where a ray passes between trunks. That is realistic but not a "limited" wall.

## 6. Recommendation (hybrid-lite: per-tile flags, no wall documents by default)
1. **Buildings:** `collision:true` (already default) and `sight:true`. This gives walls + doors for movement, vision, light and (by code) sound with open/closed doors, without wall documents. Prefer per-building or per-district tiles (`--split-preset individual` / group) for the door toggle cost (20 ms and 5.7 MB per toggle on the merged 25-house tile versus an estimated ~1 ms on a single house); keep the merged tile only if doors are rarely used.
2. **Trees:** `sight:true` on the foliage chunks (measured: +75 MB browser heap, worker 0.7 ms per polygon) while `collision` stays false, so tokens walk through but cannot see through trunks and hedges. This replaces the tree-stand limited walls, which never had any effect on vision here.
3. **Water/fences:** sight off, collision per the existing defaults (water off). Town walls layer: sight true + collision true.
4. **push-walls:** make it opt-in (default layer list empty), keep it only as the fallback for clients with multithreading off and for scenes in flat mode; stop calling it for buildings and trees. If kept, drop the tree limited walls (no effect) and the water sound walls unless an AmbientSound test shows they matter.
5. **Door sync:** only needed while wall doors exist. With no wall documents the model flag is the single state (movement, sight, sound all follow it). Keep the macro and `sync-doors` for scenes that keep wall doors; do not install by default.
6. **Panel:** replace the "Walls" boxes with a per-layer "Sight (blocks vision, light, sound)" box list next to the collision boxes (default: buildings, walls, foliage on; others off), written as the tile flag `sight` by `push-models --sight a,b` and `set-collision --sight ...` (same code path as collision), plus an advanced "Also write Foundry walls (fallback)" checkbox. `sightMeshComplexity` stays optional.
7. Verify before shipping (needs a token with vision, not done here): token vision from outside a house through a closed and an open door, fog exploration, and one AmbientSound behind a building. Also check the per-building-tile door toggle time live.

Limits of this research: no player client, no token with vision, no AmbientSound, light-polygon-versus-door not isolated, foliage worker cost measured with 72 lights only (no token vision sources), merged vs per-building tile cost partly estimated.
