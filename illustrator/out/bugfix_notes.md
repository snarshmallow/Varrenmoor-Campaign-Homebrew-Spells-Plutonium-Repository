# Bug-fix pass (2026-11-07): done / not done

Verified with python tests (test_region_extract, test_worldpack, test_worldpack_detail, test_svg_raster, test_foundry_push, label tests) and panel/test/run_mock.js + test_host_reroute.js. Nothing was run in live Illustrator or Foundry; nothing pushed to Foundry.

| # | Item | Status |
|---|---|---|
| 1 | Detail clutter | DONE. Layers `DETAILS - Trees` (one faint ring, no centre dot) and `DETAILS - Lots` (faint, off at <=20 ft/in); `--details` flag on render_world/region_render; panel checkboxes (Regions tab, "Drawn on the map") + mock tests. region_extract keeps `--detail` for generation. |
| 2 | Stale manifest after split | DONE (`worldpack.refresh_manifest_files`, called by split_export into the pack dir). Test on the dyers_walk pack copy. |
| 3 | Merge collapsing doors | DONE. Door nodes never merged, hinge position/extras preserved, all presets. Test compares hinge positions before/after for layer, all, district. Not done: Blender importer is still not taught door nodes. |
| 4 | Kerbs/fences faint | DONE at <=25 ft/in (0.9 / 1.0 pt strokes). |
| 5 | Headless region PNG | DONE (`svg_raster.py`; region_render writes `<prefix>.png`, Illustrator job kept, exports `<prefix>_ai.png`). Limits: PIL rendering, no curves other than polylines, fonts Arial from Windows fonts; look differs slightly from Illustrator. |
| 6 | Court Square 43-56% | DONE: plazas tier `max_cover 0.22`, size 0.8. At 200/100/60/40 ft/in the label is placed with 0% on features (was 56% on road at 100). |
| 7 | Curved street/river text | DONE in SVG generation: `<textPath>` along the centreline where the street bends > 12 deg (`label_curve.py`, `declutter.curved_streets` now on, left-to-right/upright), river name along the river centreline. lib_svg encodes `href="#id"` like ids and declares xmlns:xlink. Illustrator should import textPath as type on a path; NOT verified live, and no host job was added (SVG fallback is the delivery path). Straight rotated labels remain for straight streets. |
| 8 | House leaders at 40 ft/in | DONE: houses tier now `leader: true, max_cover 0.5`; `working` preset uses `collision: number` + legend. At 40 ft/in hidden-by-collision went 78 -> 3 (75 with leader, 6 numbered with a key). |
| 9 | Town fills small part of bowl | PARTLY. Added `--fit buildings|area|all` framing (nice scale + centre) and `town_area --area-scale` (relaxes slope, multiplies target area). The buildable ground limits the auto area (597k -> 652k ft2 at 1.6); a larger town needs a hand lasso or terrain edits. world/bridgehollow was not touched, no town regenerated. Panel UI for these two is not added. |
| 10 | Bake to texture | DONE offline: `foundry_push.py bake-texture` + `push-models --table-texture` (FOUNDRY_3D_CANVAS_NOTES.md section 7, tests). Not done: live check of how tableTex is scaled/tiled. |
| 11 | host.jsx close_docs | DONE: names required, unsaved docs skipped unless `discard:true`, never saves; mock test added. main.js already reloads host.jsx via `$.evalFile` at startup and on `unknown action`. Flaky mock: see below. |
| 12 | BOARD.md | DONE (rows IL1-IL3). |

## Panel mock flake
`panel/test/run_mock.js` (now 131 checks) was run 3 times to completion while other agents loaded the machine: 131 passed, 0 failed each time (runs 4 and 5 were still going when this was written). The flake did NOT reproduce, so no cause was found. Each run takes 5+ minutes because the mock executes the real generators; under load a run can exceed a 2 minute tool timeout, which looks like a hang (that is what I hit first). Suspects if it appears: runs sharing world/_region_test and the OS temp dir. Do not start two copies at once.

## Things to know
* The panel and host.jsx changes load when the panel is reopened (Illustrator keeps the old host.jsx until then).
* Labels: with `curved_streets` on, QA still measures the straight candidate box; curved text follows the street so its real coverage can differ slightly.
* `illustrator/out/test_guide.svg` and `generators/terrain.py` were left uncommitted (not mine). World files under world/bridgehollow__dyers_walk_local are being changed by another agent; not committed here.
