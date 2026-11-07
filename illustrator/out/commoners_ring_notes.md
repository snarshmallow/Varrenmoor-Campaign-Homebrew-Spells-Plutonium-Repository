# Commoners' Ring / Dyers Walk: districts + region feature end-to-end test (2026-11-07)

## What was done
1. **District child map.** `dis_commoner` ("Commoners' Ring") extracted from `bridgehollow` -> `world/bridgehollow__commoners_ring/`
   (margin 40 ft, 2.5 ft terrain cell, all detail kinds, seed 7). 142 buildings, 25 street parts, 1 water, 14 districts kept, 6 buildings dropped, 4 continues-off-map markers.
   Rendered at **40 ft/in**, 5 ft grid, 5 ft contours, regular calm style, via the Illustrator panel job (panel was open): `illustrator/out/commoners_ring.png` (+ `.ai`, `.svg`, fills/shading folders).
   Note: the Ring is an annulus around the Authority Ward, so the 775 x 723 ft window also shows the ward, the river and Market Square.
2. **Street child map.** Dyers Walk (`str_016`, 17 doors fronting it, most of any street) extracted from the Ring child (a child of a child works):
   `world/bridgehollow__commoners_ring__dyers_walk/`, 25 buildings. Rendered at **20 ft/in** with lots, doors, fences, kerbs, house labels:
   `illustrator/out/commoners_ring_dyers_walk.png` (+ `.ai`). A second extract with `--local-origin` (`world/bridgehollow__dyers_walk_local/`, 306 x 362 ft frame) is the source for the 3D pack.
3. **3D exterior.** `world/bridgehollow__dyers_walk_local/export/` (world pack + split GLBs + `placements.json`, NOT pushed to Foundry). Previews in `illustrator/out/commoners_ring_3d/dyers_walk_{aerial,street,door,open}.png`
   (Blender 5.2 headless, `foundry-3d/blender/street_preview.py`). `_open.png` rotates the door leaf node 100 degrees to prove it is a separate movable node.

## 3D contents (real vs missing)
Real: terrain strip (2.5 ft heightmap, 306 x 362 ft), 6 road meshes + 1 plaza, **kerb bands** on 6 streets (0.7 ft wide, 0.5 ft high, trimmed where roads cross),
25 hollow houses: wall thickness 0.75 ft (mitred inner polygon), a ground-floor door hole each (3.5 x 7 ft, from the region detail doors) and windows (3 x 3.5 ft, sill 3.5 ft,
103 total, derived: ~1 per 8 ft of free wall per storey) with reveals, trim frames (0.4 ft, proud 0.15 ft), sill ledges, glass panes (alpha 0.45) with mullion/transom,
interior floor, gable roofs with overhang. **Doors are separate glTF nodes** (origin on the hinge, extras `isDoor`, `doorId`, `doorStyle` 1, `doorAnimateAngle` 90), 25 in total.
QA: 25 buildings, 10 648 building tris (~430 each), 49 051 tris / 28 GLBs total, largest building GLB 44 KB, `worldpack.py validate` OK right after export.
Door leaf opening in Foundry 3D Canvas is UNVERIFIED (follows the README door convention; sign of `doorAnimateAngle` untested). Not pushed.

Missing (interiors): there is **no room data for these houses** (`rooms: []`, `doors: []` in every building JSON; the doors exist only as generated, non-canon detail points).
What exists behind a door is one empty hollow shell (floor + open rafters, no ceiling, no interior walls, no furniture). Needed for real interiors:
(a) rooms/doors in the building JSON (a floor-plan generator for houses), (b) an interior mesh builder in `worldpack_detail.py` that cuts partition walls and inner doors (as more `isDoor` nodes),
(c) a ceiling/upper-floor slab (windows already repeat per storey), (d) lighting/walls for Foundry (`foundry_push` wall generation per room).
Other limits: windows are not in the pack data (derived at mesh time); window shutters, chimneys, porches, steps are missing (chimneys exist in 2D details only); no fences/trees in 3D (fences exist in 2D details; the pack's `fences` layer is field fences only); `worldpack_split.py merge` would collapse door nodes (not tested, use the split GLBs); `foundry-3d/blender/import_worldpack.py` has not been taught the door nodes.

## Bugs found in the region feature
* **Fixed: `--local-origin` children crashed the world pack** (`worldio.load_terrain`: `ValueError: index can't contain negative values`; the cropped heightmap's `origin_ft` is a cell or two negative after the shift). It now drops the rows/cols before x/y = 0. Test: `test_worldpack_detail.py::NegativeOriginTerrain`.
* Not fixed: the `.png` of a region render exists only through the Illustrator job (no SVG rasteriser path without Illustrator); `region_render.py` prints the actions but the PNG is produced by the panel.
* Not fixed: street-scale kerbs and fences are faint in the 2D render (hairlines), doors are tiny squares; fine at 5 ft grid but easy to miss.
* Not fixed (observation): `worldpack_split.py split` after `worldpack.py export` leaves `manifest.files` hashes stale for `placements.json`/GLBs, so `validate` then reports checksum mismatches (also true for `bridgehollow`). Validate before splitting.
* Child-of-child re-runs the detail pass (doors, lots, fences regenerated with the new seed), so detail is not inherited from the first child; the Ring child's doors are not the Dyers Walk child's doors (same positions here only because the seed and geometry match).
* Housekeeping accident: a relative output path in my first Blender run created a stray `C:\illustrator\out\commoners_ring_3d\` folder (Blender treats a path without drive as drive-root relative). Harmless; delete it by hand (the sandbox refused my rm). The script now needs absolute paths (documented in the usage line).

## Code changes
`illustrator/generators/worldpack_detail.py` (new), `worldpack_mesh.py` (road kerbs, door nodes, glTF node translation, material alpha), `worldpack_split.py` (door nodes in GLBs),
`worldpack.py` (openings + kerbs in pack entities, detail materials), `worldio.py` (negative origin), `test_worldpack_detail.py` (5 tests; `test_worldpack.py`, `test_worldio.py`, `test_region_extract.py` still pass),
`foundry-3d/blender/street_preview.py` (new).
