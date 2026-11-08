# Verification pass (2026-11-08)

Scratch places `qa_place` / `qa_bridge` were created under `world/` and deleted afterwards. Foundry scene `ZZ Bridge Test` (Scene.umSwyrt2sZYMAWvF) remains; its model files are under `art/qa_bridge` on the share. `ZZ Panel Push Test` was created from the panel and deleted. Other ZZ scenes untouched.

## 1. Live panel QA (CDP, port 8088, installed extension is a symlink to illustrator/panel)
| Item | Result | Evidence |
|---|---|---|
| All 16 tabs render (Scale, Terrain, Contours, Labels, Shading, Lighting, Water, Town, Buildings, Regions, Foliage, Padding, Bridges, Places, Layers, Foundry) | PASS | no console errors/exceptions/log errors while cycling all tabs (script `qa.mjs` logic, run twice incl. after reload) |
| Layout at 340 / 440 / 900 px | PASS | Emulation width override: no horizontal scroll or overflowing element on 8 tabs; tab bar 73 px tall at 340, 49 at 440, 25 at 900 (wraps) |
| Panel window resizable | manifest only | manifest MinSize 340x300, MaxSize 4000; CDP has no Browser.* domain in CEP, real window drag not testable |
| Places: validate, generate small draft place `qa_place` (1600 ft, pop 150, Draft on) | PASS | job logs; world/qa_place written, preview PNG |
| Buildings: apply style town_mill to all of the copy place | PASS | 5 buildings changed, verified in JSON |
| Foliage: use town / scatter / stats / preview | PASS (ran, 0 items) | the draft place has no scatter zones worth planting; no errors |
| Bridges: detect list, auto-fix | PASS after fix | see bugs 1 and 2 |
| Padding: generate preview (no push) | PASS | job log, padding_apron_albedo.jpg |
| Foundry tab: Check connection, Refresh from Foundry | PASS | "Read 66 scenes, 94 actors, 48 items, 7 journals" |
| Foundry tab write: Push models to NEW scene "ZZ Panel Push Test", then delete | PASS | 11 tiles created; scene deleted with foundry_push.py delete-scene |
| Foundry tab Push scene / Export view (needs the active Illustrator document) | NOT TESTED | only open doc is the unsaved recovered one; deliberately not touched |
| Regions tab live flow (opens a new Illustrator document) | NOT TESTED live | covered by test_region_extract.py (prints OK) and run_mock.js region jobs; not run in Illustrator to avoid touching documents |

## 2. Bridge tile in Foundry (ZZ Bridge Test) : PASS
Place `qa_bridge` (seed 13, draft): one real water crossing, 101 ft timber truss bridge (bridge_maker apply -> worldpack_split split -> `push-models` to create scene -> `push-scene-3d`, verify: no problems). In the GM client (own tab): model loads, 1444x2097 px tile = 72x105 ft, ends meet the cobble road ribbons, the river passes under the deck with open clearance (side view shows water and bank beneath the trusses). Minor: small triangular gaps between deck corners and the road ends (skewed crossing). Screenshots: `foundry_screens/bridge_overhead.jpg`, `bridge_ground.jpg`. An under-the-deck camera shot was not obtained (camera went below terrain).

## 3. Tests (each run alone; final results after the fixes)
test_foliage OK; test_worldpack 18 tests OK (twice); test_region_extract OK; test_building_styles 17 OK; test_bridge_maker 22 OK; test_place_create all passed; test_padding_heightmap 14 OK; test_foundry_push 22 OK; test_interiors 11 OK; test_worldpack_pbr 10 OK; test_worldpack_detail 7 OK; test_svg_raster 7 OK; test_label_declutter / offset / style OK; test_town_area OK; test_town_gen OK; test_lighting 0 fails; test_foundry_lighting 3 OK; new test_door_compress OK; panel/test/test_*.js (7 files) all pass; panel/test/run_mock.js 131 passed, 0 failed. No failures without a fix applied (the failures below were found by live use, not by the suites).

## 4. Remaining gaps
* (a) Interior door swing in Foundry: PASS (rotation check, not visual). In ZZ Bridge Test the exterior and 4 interior door nodes are detected (isDoor with mesh on the same node); setting tile flag `modelDoors.<id>.ds = 1` rotates the leaf +90 degrees about Y (quaternion 0,0.707,0,0.707) for exterior and interior doors alike. worldpack_interiors builds the leaf along the wall direction with the room side on the left normal, and +90 deg about the vertical axis turns the direction onto that normal: it swings to the intended room side. No screenshot.
* (b) Merged/optimised GLB doors: FIXED + test. `merge_export(compress=...)` now skips gltfpack for files containing door nodes (`doors` count and `compression: "none (has doors)"` in placements.json); other files still compress. Test `test_door_compress.py`.
* (c) Padding apron: colour border FIXED (the albedo faded the near terrain colour over 80 ft but the apron is 200 ft, leaving a dark conifer ring; fade now runs over the apron length, `padding_apron_albedo.jpg` is smooth). The faint vertical streaks in the apron in the overhead view (ZZ Bridge Test) were not found or fixed: they look like texture/heightmap banding (8-bit heightmap step 0.88 ft) rather than the albedo; not verified.
* (d) Region extract from the panel: see section 1 (not live).
* (e) Foundry write button: see section 1 (Push models PASS; Push scene not tested).

## Bugs found and fixed
1. Panel: after generating a place the place selects (`#place`, `#fPlace`) did not contain it, so the selector went blank (main.js switchPlace now adds missing options).
2. town_gen: a main road that merely brushed the river bank margin became a "bridge" piece that did not touch water (draft place had a floating 29 ft bridge beside the river). Bridges now need a real intersection with the river polygon.
3. place_create: draft cell size (15 ft) did not divide the place size, so every export failed validation ("(n-1)*cell_ft does not equal size_ft"); cell is snapped to a divisor of both sides (`snap_cell`).
4. bridge_maker detect: unexported place gave a raw FileNotFoundError traceback; now a clear message.
5. foundry_push push-scene-3d: a new place without a skybox aborted at the end; the sky is now generated (skybox.py generate) when missing.
6. worldpack_split merge: npm gltfpack on Windows sometimes dies on exit (libuv assertion, 0xC0000409) after writing a good file, aborting the merge; paths normalised, 3 retries, valid output accepted on the last. (foliage.py has the same call and was not changed.)
7. Door nodes vs gltfpack, padding colour border: see 4(b), 4(c).

Not mine / left alone: `terrain.py` and `worldpack.py` have uncommitted changes (the foliage id line in worldpack.py is not from this pass); Foundry still shows the "Varrenmoor Bridge connected" toast repeatedly.
