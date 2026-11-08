# Foundry 3D test scene: red background, missing foliage GLB, low FPS (2026-11-08)

Scene `ZZ Dyers Walk 3D Test` (Scene.sFd94FxO1JX8dlJg), Foundry 14, 3D Canvas 9.0.29.

## Root causes

1. **Missing foliage files (the error notification).** All 9 foliage tiles pointed at
   `.../models/foliage_v002/foliage/cX_Y_v001.glb`. HTTP GET of each: 404. The files only existed under
   `.../models/foliage_merged/foliage/` (an older publish); `foliage_v002` was never uploaded, although the tiles were created.
   `\\VEGA\varrenmoor-3d` does resolve and is the same folder Foundry serves (`FOUNDRY_ASSETS_DIR` in `foundry-3d/.env` is right);
   nothing was wrong with the share. Re-running `push-models` for `optimized/foliage_v002/placements.json` uploaded the chunks (HTTP 200, sizes match).
2. **Red-orange flood.** Console: every 404 tile logged "File format not supported or missing", then
   `3D Canvas: An Error Occured in the Rendering Loop TypeError ... sendToWorker` (tile with no model) and three-mesh-bvh
   `countNodes ... reading 'count'` in the raycast worker. The module's render loop threw every frame, so the canvas showed only its clear
   colour (the red) and the HUD showed FPS 4. The skybox flag was intact the whole time (`exr` = clear_day_v002.webp, HTTP 200, blue sky image).
   After the files existed: no render-loop errors, sky and mountains render again.
3. **Padding step without padding (found while verifying).** The test scene had `padding 0` and calib `sceneX/sceneY = 0`. `push-padding` generated a heightmap table for
   an unpadded scene (table raised over the town: only table texture visible, camera pushed up to y 20), and model tiles are positioned from `calib.sceneX/Y`, which changes
   when padding is set (1600/1900 px at padding 0.25). Fixed by a geometry step first (set padding, update calib), then models.
4. **GLB features:** all 38 tile models + padding apron validated as loadable (no quantization, no meshopt, POSITION on every primitive). The quantized-foliage suspicion is
   not the cause here, but quantized GLBs are now rejected anyway (the module's BVH worker builds from raw `position`).

## FPS (honest)

- In-tab `requestAnimationFrame` runs at about 1 Hz in this remote Chrome (also in the other GM tab, also with the 3D loop switched off), so `canvas.app.ticker.FPS` and
  `game.time.averageFPS` are not usable. While a screenshot is being taken the HUD shows 13 to 15 FPS.
- CPU per frame is small (animation loop about 8 ms, composer submit 6 ms, 443k triangles, 1399 meshes, 72 point lights).
- GPU time per frame (EXT_disjoint_timer_query, RTX 3080 via ANGLE/D3D11) is very noisy, 27 to 350 ms, and does **not** change when the 9 foliage tiles are hidden,
  when point lights are hidden, when the canvas is rendered at quarter resolution, or with shadows off. So foliage budget/impostor settings were not changed (no evidence they help).
  The >= 30 fps target is **not verified**; the bottleneck is unidentified (candidates: GPU clocked down while the window is occluded, a second 3D client on the same GPU, the 4 OutlinePasses).

## Fixes in code

- `glb_check.py`: loader-compat validation (container, JSON/BIN chunks, extensionsRequired, quantization, meshopt, POSITION, accessors, external uris).
- `foundry_push.verify_models`: before any tile is created, every model path must exist in the assets folder, validate, and (with `--serve-url`/`FOUNDRY_URL`) answer HTTP 200 with the right size.
  Failure aborts with the list; no tiles are written (push-models and push-scene-3d).
- `foundry_push.py push-scene-3d`: geometry (padding + calib) -> models -> foliage -> padding -> lights -> skybox + sun/ambient/tint flags (one final update) -> verify
  (flags read back, all tile models + exr fetched). Idempotent (versioned byte-identical reuse, id-keyed upserts).
  Example: `python foundry_push.py push-scene-3d --place P --scene-uuid Scene.x --foliage-placements world/P/export/optimized/foliage_vNNN/placements.json --lighting P --with-lights --yes` with `FOUNDRY_URL=http://10.0.0.15:30000`.
- `foliage.py publish` and `worldpack_split.py publish --foliage`: if quantized chunks fail the load check they are re-merged uncompressed.
- Tests: `test_foundry_push.py` (GlbCheckTests, Scene3DTests: step order, flags last, skybox restored after a step resets it, idempotence, invalid GLB creates no tiles, dry run).

## Screenshots

`foundry_screens/fix_overhead.jpg` (O key), `foundry_screens/fix_ground.jpg` (ground level, sky, mountains, foliage).
