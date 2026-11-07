# Regions: zoom-in child maps of a district

A **region child** is a place of its own (`world/<parent>__<region>/`) that holds the part of a parent place (town, bowl) inside a region or
district, with finer terrain and optional generated detail, so a player-scale map and scene can be made per district (street 20 ft/in, 5 ft grid).
Nothing is scaled geometrically: the zoom is the **view scale**. The child keeps the parent's foot coordinates (unless you ask for a local
origin) and the parent's stable entity ids, so Illustrator layers, 3D models and Foundry scenes keep linking.

Code: `generators/region_extract.py` (library + CLI), `region_render.py` (render + Illustrator job), `region_draw.py` (drawing of the extras),
`panel/lib/regions.js` + `panel/regions_ui.js` (Regions tab), `foundry_push.py` (`push-scene` flags, `link-region`). Tests:
`generators/test_region_extract.py`, `node panel/test/run_mock.js --only regions`.

## Workflow

1. Build the parent (Town tab). Choose the region: a district / ring / field / square id from the model, a lasso (closed path in Illustrator,
   press **Capture lasso**; **Preview extent** draws the region as an editable named path on layer `REGIONS` of the parent document), or a rectangle.
2. Set margin, target scale (preset or custom ft/in and grid), terrain cell, contour interval, detail toggles, seed.
3. **Create region map**: extract -> render at district scale (contours, shading, fills, labels, lights use the normal pipeline) -> new Illustrator
   document with the same layer tree (+ `LINES/Details`, `LINES/Vegetation`, `REGIONS` outline in `GUIDES/Bounds`). Saved as `<name>.ai` (an existing file is never overwritten).
4. Draw in the ART layers of the child. **Refresh from parent** re-extracts and keeps hand edits (see below); ART layers live in the document and are never touched.
5. **Push region scene to Foundry**, optionally **Link on parent scene** (outline drawing; dry run unless you tick the checkbox).
6. **Sync back (diff)** shows what you changed in the child that also exists in the parent; **Apply diff to parent** writes only after a second click.

CLI equivalents:

```
python illustrator/generators/region_extract.py extract --parent bridgehollow --district dis_authority --name "Authority Ward" --margin 40 \
       --scale 20 --grid 5 --terrain-cell 2.5 --detail all --seed 7            # -> world/bridgehollow__authority_ward/
python illustrator/generators/region_render.py --child bridgehollow__authority_ward --job     # SVG + shading + fills + illustrator/jobs/<id>.json (panel polls it)
python illustrator/generators/region_extract.py list --parent bridgehollow
python illustrator/generators/region_extract.py refresh --child bridgehollow__authority_ward
python illustrator/generators/region_extract.py sync --child bridgehollow__authority_ward        # diff only
python illustrator/generators/region_extract.py sync --child bridgehollow__authority_ward --apply
python illustrator/generators/render_world.py --place bridgehollow__authority_ward --view region --contours --contour-interval 2 --scale 20
python illustrator/generators/foundry_push.py push-scene --place bridgehollow__authority_ward --view region --image export.png     # scene "<name> (district)"
```
`--sandbox` writes under `world/_region_test/` (git-ignored; the child id becomes `_region_test/<parent>__<region>`), `--parent-root DIR` reads the parent from
a frozen copy of `world/` (tests use this, because the parent keeps changing while the town is being regenerated).

## Data model (`world/<parent>__<region>/`)

| File | Content |
|---|---|
| `place.json` | normal place file: `kind: district`, `parent: {place, region}`, `bounds` (max extent in child feet), `window_ft` (the extracted window), `links.parent_place` |
| `region.json` | provenance: `parent`, `region` (kind/id/rect + `polygon_parent_ft`), `work_area_polygon_parent_ft` (region + margin), `transform` (`origin_ft`, scale 1), `parent_source` (git commit, dirty flag, SHA-1 of the parent model + heightmap files), `extracted_at`, `params`, `id_map` (parent id -> child ids), `dropped`, `counts`, `snapshot` (hash of every extracted entity, for refresh), `interiors` (building id -> parent interior json), `terrain` report |
| `districts.json streets.json water.json buildings/*.json` | extracted entities, same schema as the parent; each has `region: {parent_id, clipped, edge, inside_frac, continues_off_map, part}` |
| `terrain/` | cropped, up-resolved heightmap + `terrain_meta.json` (`origin_ft`, `parent_cell_ft`, `upres_factor`, `max_node_dev_ft`, seed) |
| `view_settings.json` | parent presets + `district` preset (scale, grid, focus, page fitted to the window); `default_preset: district` |
| `details.json` | generated detail, **not canon** (`canon: false`, every item `detail: true`, note "detail: generated at district scale") |
| `markers.json` | `continues_off_map` arrows and the region outline |

### Coordinates and ids
Child feet = parent feet minus `transform.origin_ft`. Default origin is 0,0 (same coordinates; `terrain_meta.origin_ft` says where the heightmap crop
starts and `worldio.load_terrain` pads the crop back to the full frame with edge values, so contours, shading, lighting and the world pack need no change).
`--local-origin` shifts the child to a 10 ft grid corner of the window (smaller frame, same ids). Entity ids are never renamed; a street cut into
several pieces keeps the id on the longest piece and uses `<id>__p2`, `<id>__p3` for the others (all listed in `id_map`).

### What is kept
* **Buildings**: kept whole when the centroid or more than 50% of the area is inside the work area (region + margin), flagged `edge` when they cross the edge;
  `--clip-buildings` clips them instead (flag `clipped`). Mostly-outside buildings are listed in `dropped`.
* **Streets**: clipped to the work area with flat end caps; `region.continues_off_map {start,end}` and a marker arrow (`markers.json`, drawn in `GUIDES/Bounds`)
  at each cut end. Water, districts, fields, squares: clipped polygons (ids kept, `clipped` flag).
* **Rooms/interiors**: building json (rooms, doors, links) is copied unchanged; `region.json.interiors` links each building with rooms to the parent file.

### Terrain up-resolve
`upres_terrain`: crop to the work window plus 2 coarse cells; cubic interpolating spline to `terrain_cell_ft` (integer factor of the parent cell, 10 -> 2.5 ft = x4);
band-limited multi-octave noise (periods from 2 coarse cells to 4 fine cells, more amplitude on slopes) is made **zero at every coarse node** (the noise minus its own
spline through the coarse nodes), so the coarse heights are reproduced exactly (`max_node_dev_outside_pads_ft` ~ 0). Detail fades to zero in road beds (road beds stay as graded in the
parent), under building pads and 6 ft around them, and is 25% in water. Building pads (footprint +1 ft) are flattened to their mean with a 5 ft blend; the node deviation under pads is reported
as `max_node_dev_ft`; `--no-flatten-pads` gives an exact match everywhere. Negative elevations, `sea_level_ft`, rivers and lakes carry over (the parent heightmap already holds the beds). Deterministic: same parent
+ region + seed + cell = identical bytes.

### Detail pass (generated, marked, optional per kind)
`doors` (on the footprint edge facing the nearest street), `roofs` (gable/hip ridge along the long axis), `chimneys`, `lots` (yards trimmed against streets and
neighbours), `fences` (lot outline with gaps at the street), `kerbs` (3 ft sidewalk strips on streets 14 ft+), `trees` (Poisson scatter favouring yards and field edges).
Drawn on `LINES/Details`, `LINES/Fences`, `LINES/Vegetation`. The parent never sees them.

## Scale math
`page_in = ceil2(window_ft / ft_per_in + 2 * margin_in)`, `ft_per_in` = the preset (20 = street, 5 grid). Example: a 400 x 300 ft region at 20 ft/in is a 21 x 16 in page
(20 x 15 in map + 0.5 in margins). 40 ft/in halves it. `--scale/--grid/--page` override on any render. Foundry: px/ft = dpi / ft_per_in, grid px = px/ft x grid_ft (80 px per 5 ft square = 320 dpi at 20 ft/in).
Memory: fills and shading are rasterised only for the page window (`shading.py --window`), the fill dpi is capped so the raster stays under 36 Mpx (`region_render.py --max-fill-px`); contours use the cropped fine heightmap.

## Refresh and sync rules
* **Refresh** = extract again with the stored parameters. Entities whose JSON differs from `region.json.snapshot` (you edited them) are kept as edited; entities that exist only in the child are kept;
  everything else is replaced by the parent's current data. Detail and terrain are regenerated (deterministic by seed). Illustrator ART layers are not touched.
* **Sync** compares shared attributes (`name kind status notes floors links` and, for unclipped entities, geometry shifted back by `origin_ft`). The default only prints the diff. `--apply` writes the
  changed attributes into the parent's files; child-only entities are reported but never added automatically. Never silent: the panel needs two clicks.

## Foundry
`foundry_push.py push-scene --place <child> --view region` uses the child's grid (5 ft) and the same pipelineId convention `scene:<child>:<name slug>`, walls `wall:<building>:<n>`;
the scene gets `flags.varrenmoor.region = {parent, child, name, polygon_parent_ft, transform, parent_commit, parent_sha1}`. `link-region` builds an outline Drawing (`draw:region:<child>`) in
the parent scene's calibration; it only prints unless `--apply`. Foundry module >= 0.3.0 (upsert_by_flag / upsert_many).

## 3D / world pack
The child is a normal place for `worldpack.py` (same ids, feet, terrain through `worldio`); `place.json.parent` and `region.json.transform` carry the parent link and the shift so a pack for the district
can be placed in the parent's frame. (Use a child id matching `[a-z0-9_]+`, i.e. not `--sandbox`, for the pack schema's pipelineId pattern.)

### Detailed buildings in the pack (2026-11-07)
When the place has `details.json` (any region child), `worldpack.py export` adds `openings` (the generated doors) to buildings and `kerbs` to streets; `worldpack_mesh.build_parts` then builds hollow
buildings (0.75 ft walls, door/window holes, trim, glass, floor, door leaves as separate hinge-origin nodes) via `worldpack_detail.py`. See `illustrator/out/commoners_ring_notes.md` for limits (no interiors).
`--local-origin` children now export (negative terrain origin fixed in `worldio.load_terrain`).

## Detail drawing, headless PNG, framing (2026-11-07 bug-fix pass)
* Generated details are drawn on their own layers under LINES: `Details` (kerbs, roofs, chimneys, doors), `DETAILS - Lots`, `DETAILS - Trees`, `Fences`. Trees are one faint ring (no centre dot); lots are a thin faint dashed outline and are **off at 20 ft/in and finer** unless asked for. Flags: `render_world.py --details auto|all|none|trees,lots,...`, `region_render.py --details ...` (same), panel Regions tab "Drawn on the map". `region_extract --detail` still decides what is *generated*; `--details` only what is drawn.
* Kerbs and fences use a heavier stroke at <= 25 ft/in (`kerb-hi`, `fence-hi`).
* `region_render.py` writes `<prefix>.png` headlessly (`svg_raster.py`, PIL) and still emits the Illustrator job (its export is `<prefix>_ai.png`). `--no-headless-png` skips it, `--png-dpi` sets the resolution.
* Framing: `render_world.py --fit buildings|area|all [--fit-margin ft]` picks the next nice scale (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5 x 10^n) and centres the page on the built-up area; an explicit `--scale` is kept. `town_area.py --area-scale 1.6` relaxes the buildable slope with the factor and multiplies the target area (Bridgehollow: 597k -> 652k ft2, the valley sides stop it; a hand lasso is used as drawn).
