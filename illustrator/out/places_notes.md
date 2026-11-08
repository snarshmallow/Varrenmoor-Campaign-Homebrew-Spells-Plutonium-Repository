# Places work: notes

## Files added
generators: place_create.py (create / validate / prompt-help / from-text / templates / regen / write-schema), place_terrain.py (10 terrain recipes + river, sea, lake
water), place_text.py (keyword parser), place_stats.py (percentile elevation remap), place_render.py (headless render of any place), foundry_import.py (import-scene),
test_place_create.py. presets/naming/*.json (5 naming sets), presets/places/*.json (5 templates). world/schema/place-spec.schema.json. panel: lib/places.js, places_ui.js,
test/test_places_jobs.js, Places tab. Docs: PLACES.md, out/place_audit.md. Demo: out/places_demo/sheet.png (Bridgehollow vs generated coastal village and walled hill town; both also exported as validated world packs).

## Edited (all backward compatible, Bridgehollow byte-identical)
town_gen.py (naming sets, neutral defaults, centre from map, bridge name, single-ring district fix), terrain_natural.py (defaults_version, overflow fix), worldio.py + shading.py + skybox.py
(percentile elevation bands, skybox rim options), viewcfg.py, terrain_check.py, winter_build.py (--place), render_world.py (draws walls.json), foundry_push.py (import-scene,
default linked scene, --link), panel core.js / index.html / main.js (delimited Places blocks), label_abbreviations.json. terrain.py was NOT touched.

## Verified
- Bridgehollow regeneration: streets, districts, report, 148 buildings, heightmap byte-identical (test_place_create.test_bridgehollow_regression).
- 10 recipes produce finite terrain, sea / rivers where expected, sea rotates with sea_side; high ground no longer NaN.
- Hamlet and walled coastal town end to end: no Bridgehollow names, styles on every building, deterministic, render_world and worldpack export validate.
- import-scene against the real scene ZZ Dyers Walk 2D Test (Scene.1drJ8PFJ4p5aBctd), read-only: 100 walls -> 25 closed loops, 310x360 ft at 10.8 px/ft, background copied; render aligns outlines with the art.
- Node: 23 mock checks for the Places jobs. Existing python tests run (town_gen, foundry_push, worldio, calm, lighting) pass; panel run_mock.js not completed (slow).

## Limits / not done
- Plaza can fail on narrow pass floors; wall not in the 3D pack; layouts are parameter biases; from-text is keywords only; core.js UI defaults (seed 1103, entry 1290/1480) untouched (overwritten on load).
- Panel UI was not exercised in the live Illustrator panel (only node job tests); it needs a panel reload to appear.
- --out-root works only for --no-town / --dry-run (town generator and renderers read world/<id> from the repo).
- terrain.py had uncommitted user edits and was not touched.
