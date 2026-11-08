# import-scene live test (2026-11-08)

Source: the ORIGINAL scene "Ossuary Exchange Tavern" (Scene.LO9YAwP85R74V3tB); no duplicate existed in the connected world. Read-only: only list / get /
import-scene (bridge `get`), plus a `push-scene --dry-run` plan. Nothing was written to Foundry. Scratch places world/zz_import_tavern and a stray
world/ossuary_exchange_tavern (see bug 1) were deleted afterwards. Render kept: illustrator/out/zz_import_tavern_town_files/.

## What the scene is
Foundry v14, 3D Canvas scene: 2200 x 1600 px, grid 100 px = 5 ft (square), padding 0.25, ONE level with no background image, 0 walls, 8 lights, 7 tokens,
0 notes, 0 regions, 4 tiles (two big 3D "carrier" tiles using blank.webp + model3d flags, two small item model tiles), levels-3d-preview flags (tableTex,
tableColor, skybox/exr, sun, fog ...), plus module flags (wall-height, multi-token-edit).

## Extracted by import-scene (before my changes)
110 x 80 ft at 20 px/ft, grid, 8 lights (feet, bright/dim/colour), 7 tokens (feet), 0 walls, no background (none exists). Place JSON/render/worldpack validate OK
(`worldpack.py validate` on an export of the imported place: valid). Place shows in the Places tab as "(Foundry import)", linked.
Lost before: tiles, regions, 3D settings (tableTex etc.), level list, light/token elevation, any warning about what was skipped.

## Bugs found and fixed
1. Panel "Check (dry run)" was NOT a dry run: the panel set dry_run, started the job, and reset dry_run before the (later) step built its arguments, so
   `--dry-run` was never passed and a real place was written (world/ossuary_exchange_tavern). Fixed in panel/lib/places.js: all import options are snapshotted when the job is built. Test added (test_places_jobs.js, 24 pass).
2. Round trip did not reproduce the scene: the imported place's 'town' view was a 17x11 in page at 20 ft/in = 320 x 200 ft window, so push-scene gave a 320x200 ft
   scene (grid 60 px at upscale) instead of 110 x 80 ft. Now view_settings.page_in is sized so the view is exactly the scene rectangle (nice scale
   ft/in, page = size/scale + 1 in margins), and place.json import.native_export_dpi says what export dpi keeps the scene's own px/ft (here 200).
   Dry run after fix: 110 x 80 ft -> 2200 x 1600 px, grid 100 px = 5 ft, i.e. identical to the source scene.
3. place_render.py failed on any place whose view window starts negative (the common case for a small imported scene centred on a big page):
   shading.py `--window -105.00,...` was parsed as an option. Now `--window=...`.
4. Scene padding offset used Python round() (banker's rounding, ties-to-even, and nearest) while Foundry and foundry_push.calibrate round UP to whole squares;
   scenes whose padding*size is not a whole number of squares got an origin off by one square (e.g. width 1700, padding 0.25, grid 100: 400 vs 500 px). Now ceil.
5. Not a crash but silently lossy: tiles, regions, 3D scene flags, levels, light/token elevation, non-square grid were dropped without a word. Now:
   foundry_tiles.json (feet rect, rotation, elevation, src, model3d/depth, blank flag), foundry_regions.json (rect/circle/ellipse/polygon in feet),
   place.json import.scene_3d (tableTex, tableColor, exr, sun, fog, ...) and import.levels, light/token elevation, and `warnings` (multiple levels, hex/gridless grid,
   no background). The CLI default include is now walls,tiles,regions; the panel always sends them (lights/tokens/notes stay checkboxes).

Tests: generators/test_place_create.py (new test_import_scene_tiles_3d with a mocked 2D battle map: walls/lights/tile/regions, and a mocked 3D scene: levels,
tableTex, model tiles, hex grid, ceil padding, page sizing), panel/test/test_places_jobs.js.

## Panel flow (CDP 8088, panel reloaded once to pick up the fix)
Foundry tab refresh -> 67 scenes in the Places scene picker -> select tavern -> "Check (dry run)" now logs `--dry-run`, "would import ...: 110 x 80 ft, 0 walls, 0 closed
loops, 4 tiles, 3D settings" and writes nothing. The place list showed the imported scratch place as "(Foundry import)" + "linked". Selecting/opening was not
exercised with a real switch (would change the panel's current place).

## Still lost / approximate on import
- Tile images and 3D models are only referenced (paths), not fetched or recreated; the 3D tableTex/skybox are recorded but no tool applies them to the place.
- No background here (3D scene); for 2D scenes the background comes from the shared //VEGA assets folder or HTTP download (FOUNDRY_ASSETS_DIR / FOUNDRY_URL), not exercised live (the tavern has none).
- Walls: 0 in this scene. Multi-level scenes: only the first level's background; everything merged. Hex grids imported as square. Foundry padding is not
  written back by push-scene unless `--padding 0.25` is passed (scene would otherwise have padding 0).
- No terrain, streets, water (flat stub). Token actors only by actorId; light animation/angle, wall doors' state/sense flags, drawings, sounds, journal pins beyond notes, module flags are not imported.
- Push is an update of the original scene's background/grid/walls only if applied; the round trip was a plan only (dry-run).

## Needs a live check
- An import of a 2D scene with a real background image and walls (e.g. ZZ Dyers Walk 2D Test) after these changes, and the panel "Import" (non dry-run) switch to the new place.
- Opening the imported place in Illustrator (open job) and placing the underlay.
