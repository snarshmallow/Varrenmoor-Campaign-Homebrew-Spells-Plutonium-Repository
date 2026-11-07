# Bridgehollow town v5 (terrain-fitted irregular town area)

Files: `bridgehollow_town_v5.svg/.png` (bowl, contours), `bridgehollow_town_v5_town.svg` (town view), `bridgehollow_town_v5_area.svg` (the TOWN AREA / TOWN AREA RINGS layers the panel draws), `bridgehollow_town_v5_fills_town.png` / `_fills_bowl.png` (textured fills composite; red = area outline, blue = authority/commoner ring contours), `bridgehollow_town_v5.ai` + `bridgehollow_town_v5_ai.png` (built by panel job `v5_verify`: opened the town SVG, replace_layer of the TOWN AREA layers, save_ai, export_png; TOWN AREA holds 1 editable closed path). v4 files untouched. Seed 1103, detail 2, same terrain and water.

Regenerate: `python world/gen_bridgehollow.py`; render: `render_world.py --view bowl --contours --out illustrator/out/bridgehollow_town_v5.svg`. Re-fit the lasso: `python illustrator/generators/town_area.py --place bridgehollow --write-params` (auto) or `--mode snap` (settle the lasso already in town_params.json).

## What changed
- `generators/town_area.py` (new): buildable mask (smoothed slope < limit 0.15, floodplain beside the water excluded, gorge-wall buffer, river corridor kept so the town spans both banks) -> open/close by min width -> component at the centre -> optional trim by terrain-cost distance to a target area -> Gaussian-smoothed signed distance field + low-frequency wobble -> marching-squares zero contour -> arclength resample + Chaikin -> an editable closed polygon (~85 vertices, one per 36 ft). Parameters: slope_limit, river_buffer_ft, smoothing_ft, min_width_ft, noise_ft, target_area_ft2, seed (`town_params.json` `area_auto`). `--mode snap` settles a rough lasso (grown 45 ft, intersected with the mask, re-smoothed).
- Ring zones: `ring_spec.mode: "terrain"` makes the ring field a terrain-cost geodesic distance from the centre (steep ground costs more) with noise, so the authority and commoner zones stretch along the flat floor and pinch against the valley sides; the farm fringe is the rest of the area, so it feathers out along flat ground (south and south-east) and vanishes against the steep north and west. town_gen uses that field for ring assignment, plazas and district polygons; the nested ring polygons are also output by town_area (`rings_ft`) for the panel preview.
- `town_gen.py`: `area_mode` manual (default, area_ft as drawn, so a hand-drawn Illustrator lasso is used as is) / auto / snap; `streets.edge_inset` (streets stop inside the boundary with their full width), `lots.edge_fade_ft` (houses thin out toward the edge), `limits.field_smooth_cells` (field polygons no longer stair-step), report `area` metrics. Old params behave as before (all knobs default off); `test_town_gen.py` passes.
- Panel: Town tab has the area parameters, "Auto lasso from terrain" and "Smooth/snap my lasso" (job `town_area_auto` / `town_area_snap`, code in new `panel/lib/townarea.js`), drawing the outline on layers `TOWN AREA` (editable closed path named "Town area") and `TOWN AREA RINGS` (dashed guides). Edit with the Direct Selection tool, Capture lasso, Generate (candidate flow, Accept / Reject unchanged). Panel state keeps the area params in `town.aa`; `town_params.json` gets `area_auto` and `area_mode: manual`. Needs the panel reopened to load the new script.
- `world/bridgehollow/town_params.json`: `area_ft` is now the fitted outline (v4 18-point box kept as `_area_ft_v4_box`), rings 230 / 520 ft of terrain-cost distance, ring noise 0.2.

## Metrics, v4 -> v5
| | v4 | v5 |
|---|---|---|
| Lasso | 18 vertices, straight sides | 85 vertices, smooth contour |
| Lasso area | 1,079,900 ft2 (44% steeper than 0.15, mean slope 0.25, includes valley walls) | 615,317 ft2 (2.6% steeper than 0.15, mean slope 0.078, p90 0.106) |
| Max turn between vertices | 78 deg | 30 deg |
| Buildings | 139 (122 houses) | 128 (106 houses, 5 farmhouses, 3 barns) |
| Streets / plazas / fields | 37 / 2 / 7 | 28 / 1 / 12 |
| Street grade, graded bed max | 0.060 | 0.060 |
| Streets over the 0.08 cap, raw terrain (40 ft) | 1 (Pilgrim Road, 0.081) | 1 (same) |
| Report issues / warnings | none | none |

## Honest caveats
- Fewer buildings and one plaza fewer: the lasso no longer includes the steep valley sides, so the town is 43% smaller; the edge fade also thins the outermost lots. Raise `slope_limit` (0.17 widens onto the foot-slopes) or lower `edge_fade_ft` for more.
- The authority ring is mostly open ground around the Warden's Hall; the labels for the two rings overlap (label code is being changed elsewhere).
- The southern edge of the area stops about 40 ft inside the map edge; the entry road runs on out of it.
- Panel jobs `town_area_*` were exercised through node (job builds, params merge) and the equivalent host actions through a job file; the panel UI itself needs a reopen to show the new buttons.
