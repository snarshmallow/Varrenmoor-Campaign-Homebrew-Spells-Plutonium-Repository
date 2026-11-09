# Varrenmoor Town Center and Varrenmoor Town 3D (2026-11-08/09)

Built entirely through the plugin pipeline: place folder -> `worldpack.py export` -> `worldpack_split.py split/merge` -> `foundry_push.py push-scene` + `push-scene-3d`.
Scripts: `illustrator/generators/varrenmoor_build.py` (map digitising, calibration, overlay, error measurement), `varrenmoor_trees.py` (tree scatter from the map).

## Which town
Varrenmoor, not Bridgehollow (ChatGPT in the "Dnd Campaign 2026" project, answering from the DM guide / handoff: Varrenmoor is the ~58 resident starting village; Bridgehollow is a
separate town 80-100 miles away by Pilgrim's Road, the map shows "To Bridgehollow" at its west edge). Canon labels on the map: Varrenmoor (big hall), Hollow Oak, Pilgrim's Road,
Churchyard, Father Hakon's House, Stables, Granary Mill, Thorne Farm, Fenn Family Farm. Not in sources: inn, post office, smithy, market. So the big hall is "Big hall" (not inn or
meeting house) and the plazas are only the Hollow Oak green, the churchyard and the hall green.
No paved roads: every road is dirt, no kerbs, plazas are grass.

## Source of truth and calibration
Foundry scene "Map" (`Scene.2SFc6y3Ej8k0Ey0l`, background `assets/map v2.png`, 1448 x 1086 px, copy: `illustrator/out/foundry_screens/varrenmoor_original_map.png`). It has no walls, notes, tiles or
drawings (only a Group token), and the scene grid (25 px = 5 ft) is a default, not real. The map's own scale bar (0..1000 ft = 130 px) gives **7.69 ft per map pixel**. The model window is map px
x 0..1100, y 160..960 (8460 x 6150 ft), origin map px (0,160). All positions are digitised map pixels converted with that one transform.
The map is a painted oblique view with symbolic roofs (a roof symbol is about 15-20 px = 120-150 ft at the scale bar). Real 30-60 ft buildings placed at the symbol centres therefore look
small and far apart; positions match the map, sizes do not (map symbols are not to scale).

## Measured placement error (`varrenmoor_build.py measure`, `illustrator/out/varrenmoor_error.json`; overlay `illustrator/out/foundry_screens/varrenmoor_map_vs_model.png`)
* Roads (14 digitised polylines, 16 pieces after the bridge split): model road vs digitised vertices: max 1.7 ft (0 ft except Pilgrim's Road where the bridge cut resamples it).
* Buildings (36): centre vs map symbol centre: mean 3.1 ft (0.4 px), p90 12 ft, max 36 ft (4.7 px; pushed off a road or the river by the collision nudge).
* River: generated centreline vs the river polyline I traced: mean 26.6 ft (3.5 px), max 42 ft (5.5 px). The terrain generator meanders the river, so it only follows the traced line.
* Not measured: the digitising itself (my reading of road and symbol positions from the image, probably +-5 px = +-40 ft), vertical oblique distortion of the map (a uniform scale is assumed;
  the scale bar sits in the far corner, so foreground distances are probably overstated), and elevation (the map gives none; terrain is a designed valley: river west, Greyspine ridge north-east).
* Stored in `world/varrenmoor/place.json` `map_calibration`.

## What was built
* Place `varrenmoor` (whole town): terrain from place_terrain/terrain.py spec derived from the map, river Elva with a timber bridge where Pilgrim's Road crosses (map west edge), 14 dirt roads/lanes,
  36 buildings, 3 grass plazas, 4 fields, 4640 trees from the map canopy (+ a 3.2x hero oak at Hollow Oak).
* Place `varrenmoor__town_center` (region extract, rect map px 230..600 x 440..670, 7.5 ft terrain cells, doors/roofs/chimneys detail): 27 buildings, 289 trees.
* Trees: canopy fraction per 64 px block of the map (dark pixels) gives relative density; species follow the model terrain height (spruce/Scots pine/fir high, birch/oak/beech/alder low,
  alder/willow by the river). Absolute density is scaled to a 6000 tree budget (21 per ha at full canopy; a real forest is 200+ per ha), so the pattern matches the map but the count is a
  performance budget. Same `foliage.json` feeds `push-walls --foliage-json` for tree stands (not run: collision/walls were left to the default push-scene-3d behaviour).
* New styles (preset files + tests): town style `varrenmoor` (dirt roads, grass plazas, no paving), building styles `moorland_cottage` (weathered plank, drystone plinth, mossy steep shingle),
  `long_timber_hall` (the big hall). `test_varrenmoor.py` covers the town style, both presets, the calibration and the kerb rule. `test_building_styles.py` still passes (22 tests).
* Generator rule: roads on unpaved surfaces (dirt/mud/gravel/packed earth/sand) get no kerb unless `edit.kerb` is true (`worldpack.drop_unpaved_kerbs`, `UNPAVED_MATERIALS`).
* Fix found on the way: `worldpack_pbr.detail_terrain` allocated a 26000 x 31000 FFT for a 4600 ft region (hung 30+ min, 4 GB); noise array capped at 4096 per side (region split now 28 s).
* Interiors: rustic_cottage default (`--interior-style rustic_cottage`, houses `rustic_cottage`, farmhouses `farmhouse`).

## Foundry scenes (both new, top level, no folder)
| Scene | uuid | pack | roofs | mode |
|---|---|---|---|---|
| Varrenmoor Town 3D | Scene.aD31GqrK3XkMi4bG | layer-merged (`optimized/layer_v004`): 54 tiles, foliage as 46 chunk files with LOD, 330 k tris of foliage after budget | per_scene (one roof tile, one toggle) | 3d, padding 0.25, skybox clear_day |
| Varrenmoor Town Center | Scene.1JiEYww58bED0798 | individual buildings (`individual_v002`): 69 tiles incl. 12 foliage chunks, 129 door/hinge nodes | per_building (27 roof tiles) | 3d, padding 0.25, skybox clear_day |
Order used: push-scene (background + calibration, 3d flags) -> push-scene-3d (geometry/padding scene rect, models, padding apron, flags + skybox, verify). Whole town: 8180 x 5113 px at 0.83 px/ft (grid 100 ft = 83 px).
Center: 3611 x 2342 px at 1.22 px/ft (grid 50 ft = 61 px). Roof choice: per_scene for the 8460 ft town (one roof tile, fewer draws, nobody walks into a house at that scale), per_building
for the center where individual houses are entered.

## Screenshots (`illustrator/out/foundry_screens/varrenmoor_*`)
`varrenmoor_original_map.png`, `varrenmoor_map_vs_model.png` (model drawn over the map), Center: `varrenmoor_center_oblique.jpg`, `varrenmoor_center_overhead.jpg`, `varrenmoor_center_overhead_oak.jpg`,
`varrenmoor_center_street_oak_green.jpg` (low street level). Town 3D: `varrenmoor_town3d_oblique.jpg`, `varrenmoor_town3d_overhead.jpg`, `varrenmoor_town3d_oblique_high.jpg`.
No true street-level shot of the whole town: the 3D camera snapped back when set by script.

## Tests
* scene-audit (read-only): both scenes clean (no stale or duplicate tiles; the one extra tile is the padding apron).
* Roofs: `foundry_push.py roofs --roof-state hide|show` worked on both (1 tile / 27 tiles).
* Kerbs: pack roads 0 with kerbs; unit test for the rule passes. Python: `test_varrenmoor.py` 10 tests, `test_building_styles.py` 22 tests pass.
* Load/memory (Chrome GM tab, 3D Canvas): Center JS heap about 1.0 GB right after load, Town 3D about 0.66 GB after 25 s; FPS 59 (Foundry's own counter) in both; scene switch back to the
  Ossuary Exchange Market left 0.9 GB. This is a sanity check, not a benchmark.
* Padding and skybox pushed by push-scene-3d; verify step reported no problems (every model file exists and answers over HTTP).
* Collision: whatever push-scene-3d does by default; the dedicated `push-walls` with tree stands was NOT run.

## Unverified or imperfect
* Door opening in these scenes, interior lights (none authored), click-mode macros, per-scene roof toggle by click: not tried live.
* Whole town has 0 door nodes (the base place has no region detail pass; doors only exist in Town Center).
* Building count vs canon: 36 buildings (25 houses) against about 58 residents; they follow the roof symbols on the map, not the population.
* Fenn farmstead is not drawn on the map; its house and barn are placed beside the label (marked approximate). Mill stream, stream near the Granary Mill, graveyard wall, field fences and paths beyond the
  digitised ones are not modelled. The Hollow Oak is the generic oak species at 3.2x, not a bespoke hollow tree.
* Houses look small against the map because of the scale-bar calibration (see above); if the DM prefers the houses to read at map-symbol size, change `S` and the building sizes together.
* Terrain elevation is invented; north-east ridge and Greyspine peaks are only the part inside the window.
* The first scenes pushed with an old foliage zone naming collided in the push duplicate guard (zone ids with digits and underscores); `varrenmoor_trees.py` now writes letter-only zone ids.
* Gemini was not used: the existing `dirt` and `grass` textures are used by the new town style. ChatGPT was used for the naming/canon check and the 3-line style brief only.

## Pine density (2026-11-09)
`varrenmoor_trees.py scatter` has `--pine-density` (default 1.5), `--hill-boost` (default 0.6: pines x (1 + 0.6 x relative height)), `--max-trees` (default 12000, caps the expected count; 0 = no cap) and `--dry-run`. `--pine-density 1 --hill-boost 0` reproduces the old scatter exactly.
Counts (varrenmoor): before 4642 trees (pines 1516 = scots_pine 885 + spruce 516 + fir 115); after 6090 trees (pines 2939 = 1644 + 1039 + 256; broadleaf unchanged +-1 %), +31 % trees, pines x1.94. Foundry load: the foliage merge writes one GLB per 150 ft chunk with a triangle budget, LOD and impostors, so tile count follows the area, not the tree count; only the thinning budget and LOD2 impostor cards see more trees. Rough estimate: +31 % foliage triangles before thinning, nothing after the budget bites. foliage.json 1.38 MB, scatter pack 1.27 MB. Re-merge / push the foliage layer to see it in Foundry (not done here).
