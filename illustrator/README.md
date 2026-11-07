# Illustrator bridge

Claude writes layered line-art SVGs (`generators/`) and, optionally, drops job files that a small CEP panel in Illustrator 2024 executes.

## Without the panel
Run `python illustrator/generators/test_guide.py`, then open `illustrator/out/test_guide.svg` in Illustrator. Each `<g id="...">` becomes a layer.

## Install the panel
1. `powershell -File illustrator\install.ps1` (symlinks `panel/` into `%APPDATA%\Adobe\CEP\extensions\VarrenmoorBridge`, copies if symlinks are not allowed). No registry changes.
2. Read, then run once: `powershell -File illustrator\enable-debug.ps1`. It sets `HKCU\Software\Adobe\CSXS.11` and `CSXS.12` `PlayerDebugMode` = "1" (needed for unsigned extensions).
3. Restart Illustrator, then Window > Extensions > Varrenmoor Bridge. The panel shows the jobs folder and status.

## Test
1. Panel open. Copy the `ping` job below to `illustrator/jobs/t1.json`.
2. Within ~2 s it moves to `jobs/done/t1.json` and `jobs/done/t1.result.json` appears with `"ok": true` and the Illustrator version.
3. Then run the full example (new doc, layers, place the test SVG, save, PNG preview).

## Job format
File `jobs/<id>.json`; `actions` run in order and stop at the first failure unless `"continue_on_error": true`. Relative paths resolve from the repo root.

```json
{"actions": [{"action": "ping"}]}
```

```json
{
  "id": "test_guide",
  "actions": [
    {"action": "new_document", "width_in": 17, "height_in": 11, "landscape": true},
    {"action": "ensure_layers", "names": ["Grid","Roads","Walls","Buildings","Water","Labels","Notes"]},
    {"action": "place_svg", "path": "illustrator/out/test_guide.svg"},
    {"action": "save_ai", "path": "illustrator/out/test_guide.ai"},
    {"action": "export_png", "path": "illustrator/out/test_guide.png", "scale": 100}
  ]
}
```

`place_svg` opens the SVG, copies each layer's items into the active document's same-named layer, and closes the SVG. With `"mode": "open"` (or no open document) it just leaves the SVG open as its own document.

Result file: `{"id","ok","finished","results":[{"action","ok","error"?,...}]}`.

## World model and layered town SVG
- `python world/gen_bridgehollow.py` writes the river (`water.json`), `place.json`, then runs the town generator (below), which writes `streets.json`, `districts.json`, `buildings/*.json`, `town_gen_report.json`. Everything is `proposed`; deterministic by seed.
- `python illustrator/generators/render_world.py --view town` writes `illustrator/out/bridgehollow_town.svg` with the layer tree from DESIGN.md section 3. Views: `town`, `bowl`, `street:<street_id>`, `building:<building_id>`; output defaults to `illustrator/out/bridgehollow_<view>.svg` (`--out` overrides).
- Every shape is a closed path with `id` = entity id; strokes use classes `guide-line`, `wall`, `road`, `water`, `proposed`.

## Map scale and grid (`world/<place>/view_settings.json`)
Feet are the model unit; the view settings only change the drawing. `presets`: `town` 1 in = 100 ft (grid 100, major every 5), `bowl` 1 in = 200 ft (whole 2400 x 1500 ft place on 17x11), `street` 1 in = 20 ft, `room` 1 in = 5 ft (grid 5 ft = one Foundry square). Keys: `scale_ft_per_in`, `grid_ft`, `grid_major_every`, `focus` ([x,y] | `center` | `entity`), `scale_bar_ft`; file level: `units`, `page_in` [w,h], `margin_in`, `min_street_width_ft`, `contour_mask {enabled, include[]}`.
`render_world.py` options: `--preset town|bowl|street|room`, `--scale FT_PER_IN`, `--grid FT`, `--grid-major N`, `--page 17x11`. Grid lines (minor plus a heavier major path), scale bar, view window and label sizes (point sizes scale with sqrt(100/scale), clamped 0.6x to 1.6x) follow the scale. `viewcfg.py` is the loader; the town generator reads the same file.

## Town generator (`generators/town_gen.py`, params in `world/<place>/town_params.json`)
`python illustrator/generators/town_gen.py [--place P] [--params PATH] [--seed N] [--detail 1|2|3] [--preset ..] [--scale ..] [--dry-run]` or `python world/gen_bridgehollow.py`.
Pipeline: heightmap grids (slope, water, below-datum) -> A* main road from the entry (grade cap gives switchbacks; river crossing costs per foot so the bridge lands at a narrow, convenient spot) -> tensor field (ring tangent + overall grid + main road + river bank + contour direction weighted by slope + noise) -> streamlines per ring spacing, grade-capped by turning toward the contour, joined and pruned to the connected network -> plazas -> blocks (area minus streets, plazas, water margin) -> lots by oriented-box recursive cutting (idea from the Watabou TownGeneratorOS, GPL-3; fresh implementation, repository private and not distributed) -> buildings, fields, farmsteads, named buildings by lot scoring.
Output entities carry `elevation_ft` (streets also `elevations_ft` per vertex from the graded road bed, and `grade_max` over a 40 ft window; buildings `site_slope`, `site_relief_ft`). Elevations are signed feet against `sea_level_ft` (terrain meta, default 0): ground below the datum counts as water unless inside `limits.dry_basin_polys`.
Scale and detail: `detail` 1 = streets, squares, civic and named buildings only; 2 = plus houses, fields, farmsteads (default); 3 = plus sheds and finer street polylines. Street and lot sizes are always feet. The view scale only sets the street-polyline simplification tolerance (about 2.5 ft x scale/100); `min_street_width_ft` comes from view_settings.
Water enters only through `load_water()` (reads `water.json`: rivers as polygon and/or `centerline` + `width_ft`; lakes and sea as polygons with optional `elevation_ft`) and the `Water` class; replace that function to use another source.

`town_params.json` schema (all keys optional except `place`, `area_ft`, `entry.point`; defaults in `town_gen.DEFAULTS`):
- `seed`, `detail`, `view_preset`, `scale_ft_per_in` (override), `area_ft` (list of [x,y] feet; or `area_file`: path to such a JSON list, e.g. exported from a drawn closed path on a TOWN AREA layer).
- `output`: `streets, plazas, blocks` (block outlines, default off), `buildings, fields, districts` booleans.
- `limits`: `max_street_grade, max_main_grade` (rise/run), `max_build_slope, max_build_relief_ft, max_field_slope, hard_slope, water_margin_ft, bank_margin_ft, bank_fill_ft, below_datum_is_water, dry_basin_polys, flood_ft, min_street_width_ft`.
- `entry`: `point` [x,y], `via` [[x,y]..] waypoints, `name`, `id`, `width_ft`, `bridge_width_ft`, `bridge_cost_per_ft`, `smooth_samples`.
- `ring_spec`: `centre`, `aspect`, `noise`, `noise_period_ft`, `feather_ft`, `rings[]` of `{id, name, kind: civic|residential|farm, r_max, street_width, dsep: [along-contour, across], lot_area: [min, max], build_prob}` (values blend across the feather band; fields come from the `farm` ring lots).
- `streets`: `step_ft, min_length_ft, snap_ft, seed_jitter, noise_angle_deg, grid_weight, ring_weight, contour_weight, slope_lo, slope_hi, road_weight, road_decay_ft, river_weight, river_decay_ft, simplify_ft, chaikin`.
- `plazas`: `enabled, min_area_ft2` (no plaza below it), `per_area_ft2` (one more per this much area), `max`, `radius_ft`, `min_sep_ft`, `anchors[]` of `{id, name, type: road|road_end|junction, near}`.
- `lots`: `spread, angle_jitter_deg, min_frontage_ft, front_setback_ft, house_fill_w, house_fill_d, min_house_ft, field_bend_ft, field_hedge_ft, farmstead_prob, floors`.
- `named`: sizes for `warden_hall, magistrate_court, tax_office, lockup, inn, stables, meeting_hall, smithy, mill`, plus `market_plaza`, `court_plaza` ids.

Checks: `python illustrator/generators/test_town_gen.py` (determinism, unique ids, nothing in water or over the slope limit, one bridge, negative elevations, switchback route). `generators/preview_svg.py in.svg out.png` rasterises our SVGs with PIL for a quick look.
Bridgehollow v2: `illustrator/out/bridgehollow_town_v2.svg` (1 in = 200 ft, whole bowl) and `bridgehollow_town_v2_100.svg` (1 in = 100 ft), both with terrain contours masked under buildings, streets and plazas, made with `render_world.py --view bowl|town --contours`.

## Terrain and contours (step 1; all proposed)
- `world/bridgehollow/terrain_spec.json`: artist constraints (ridges, peaks, valleys, passes as polylines with heights, base plane, noise, erosion, seed).
- `python illustrator/generators/terrain.py [--cell 10]` writes `world/bridgehollow/terrain/heightmap.npy` (float32 feet), `heightmap_16.png` (16-bit, scaled by `terrain_meta.json`) and `terrain_meta.json`. Deterministic; about 0.2 s at 10 ft cells.
- `generators/contours.py`: contourpy lines (smoothed, Chaikin), minor/index intervals, collision-aware elevation labels on index contours, optional mask polygons.
- `python illustrator/generators/render_world.py --terrain` (regenerates heightmap + `out/bridgehollow_height.png` hillshade, overlays contours) or `--contours` (reuses the saved heightmap). Options: `--contour-mask` / `--no-contour-mask` (default from view_settings `contour_mask.enabled`; mask polygons = building footprints + street polygons + plazas, `include` selects), `--contour-interval 10`, `--index-interval 50`, `--label-size 6`, `--units ft|m`. Output `out/bridgehollow_terrain.svg`. Contour levels count from `sea_level_ft` (signed: negative levels and labels work, minus sign configurable, the datum contour is drawn with class `contour-datum`).
- New layers (always present, empty without the flags): `LINES/Terrain/Contours - Minor`, `LINES/Terrain/Contours - Index`, `LABELS/Labels - Elevation`. `LayerTree` now supports nested sublayers. The panel's `replace_layer` has not been tested on the third nesting level.

## More panel actions
- `replace_layer`: `{"action":"replace_layer","path":"illustrator/out/bridgehollow_town.svg","names":["Roads","Buildings","Labels - Buildings","NOTES"]}`. Opens the SVG, and for each named layer (sublayers are named individually, parents are not recursed) clears that layer's own items and redraws them from the SVG, creating the layer if missing. Layers named `ART ...` are refused and never touched. Lock state and visibility of the target layer are restored afterwards (`"restore_lock": false` leaves it unlocked). Fails if a name is not in the SVG unless `"strict": false`.
- `lock_layers`: `{"action":"lock_layers","names":["GUIDES","Grid"],"locked":true}` (`locked` defaults to true; false unlocks). Works on layers and sublayers.

## Status
Tested 2026-11-06 in Illustrator 28.2.0: ping and the full test_guide job succeed.

replace_layer and lock_layers are written but not yet tested in Illustrator.
