# water.py - hydrology on the signed heightmap

`illustrator/generators/water.py`. Feet, signed elevation against `sea_level_ft` (terrain_meta.json, default 0). Grid convention as terrain.py (`h[i,j]` at x=j*cell, y=i*cell, y down). Never overwrites the base heightmap or `world/<place>/water.json` (unless `--inplace`). Results go to `illustrator/out/water/<place>/`.

## Commands
```
python water.py analyze   --place bridgehollow --outlet-width 60 --threshold-cells 400 --inflow 1200,0,30 [--delta] [--no-meander] [--sea-level N]
python water.py add-river --place bridgehollow --points "x,y;x,y" [--join wat_id] --width 10 [--width-end 14] --depth 1.5 --flow 8 [--meander 0.4] [--carve]
python water.py add-lake  --place bridgehollow (--circle x,y,r | --polygon "x,y;...") [--level ft] [--depth 6] [--kind pond]
python water.py carve     --place bridgehollow [--bank-ft 12]      # heightmap_carved.npy, base untouched
python water.py crossings --place bridgehollow [--street id | --polyline "x,y;..."]
python water.py svg       --place bridgehollow [--feet-per-inch 100]
python water.py verify    --place bridgehollow                     # no water runs uphill
python water.py selftest                                           # synthetic terrain with a basin below 0 ft
```
`analyze` keeps non-auto entries from the base water.json (the hand-made river), replaces earlier `origin:auto` ones, and writes the working file `out/<place>/water.json`. `add-*`/`carve` read the working file (falling back to the world file).
`--inflow x,y,acres` adds off-map catchment (the gorge at the north edge); `--outlet-width` calibrates flow so the biggest river is that wide at its mouth. `--elev-offset` shifts the heightmap (testing negatives).

## Method
- Priority-flood (Barnes, epsilon) fills depressions; each border cell is an outlet. Flow = the D8 tree it produces; accumulation by reverse pop order. D-infinity accumulation is also written (`flow_acc_dinf.npy`).
- Sea = cells below the datum connected to the map border. Closed basins below the datum are not sea (dry ground or lakes).
- Natural lakes = depressions the flood had to fill (>= `min-lake-depth` ft, >= 8 cells), level = spill level, shoreline from the contour at that level.
- Rivers = cells with accumulation >= threshold, split into main stem (max-accumulation path) and tributaries (own entries, `tributary_of`, `confluence`). Chaikin smoothing, then a low-amplitude lateral wobble that is rejected where it would climb out of the valley. width = 4*Q^0.5, depth = 0.35*Q^0.4 (cfs, ft). Water surface = running minimum of the conditioned terrain (non-increasing downstream), tributary mouths floored at the parent's surface, lake outlets starting at the lake level, mouths at sea level.
- User rivers: drawn order is flow direction (auto-reversed if drawn uphill, unless `--join`), surface made monotone, `max_cut_ft` reports how deep the channel must cut through terrain. `--join` snaps the end onto the parent centreline.
- User lakes: the polygon as drawn, flat surface at `level` (default = lowest rim point), bowl depth = min(max_depth, shore_slope*distance from shore); a warning is stored if the rim is more than 1 ft below the level (spill).
- Carve: channel bed `surface - depth*(1-(d/hw)^2)`, banks blend to terrain with a smoothstep of `max(bank_ft, 2.5*depth)`; only ever lowers terrain.

## water.json entry schema (per entity; `water` array, place-level keys `place`, `sea_level_ft`)
Common: `id`, `name`, `kind` (river | lake | pond | sea | spring), `status: "proposed"`, `origin` (auto | user | absent for hand-made), `geometry`, `links{foundry_scene,model3d,ai_layer}`.
- River: `geometry {type:"polygon", points}` (closed outline), `centerline [[x,y]...]` upstream to downstream, parallel arrays `width_ft`, `depth_ft`, `flow_cfs`, `surface_ft` (water surface, non-increasing), `elevation_ft {start,end}`, `length_ft`; optional `tributary_of`, `confluence [x,y]`, `ends_in` (sea | map_edge | lake id), `starts_from` (lake id), `distributary_of`, `is_main`, `max_cut_ft`. Hand-made rivers lacking the arrays are filled in on read (widths from the polygon, `flow` estimated).
- Lake/pond/sea: `geometry {type:"polygon", points, holes}`, `elevation_ft` (water level), `max_depth_ft`, `area_sqft`, `spill [x,y]`; user lakes add `shore_slope`, `rim_below_level_fraction`, `warning`.
- Spring: `geometry {type:"point", points:[[x,y]]}`, `elevation_ft`, `feeds`, `flow_cfs`.

## Other outputs
- `water_depth.npy` (float32 ft, 0 = dry) + `water_depth_16.png` (+ `_meta.json`: scale) for shading phases. `heightmap_carved.npy`, `flow_acc.npy`, `flow_acc_dinf.npy`, `crossings.json`, previews.
- `crossings.json`: `{road, water_id, point, width_ft, bank_elevation_ft, depth_ft, flow_cfs, surface_ft, suggestion: ford|bridge|avoid, span_ft, deck_elevation_ft, existing_bridge, note}`. Ford if depth <= 2 ft, Q <= 150 cfs, crossing <= 40 ft; else bridge with 6 ft abutments, span rounded up to 5 ft, deck 3 ft above the higher of bank/water.
- SVG for render_world (not wired in): `water.add_water_to_tree(tree, water, px, layer="Water")`, `water.water_svg_items`, `water.water_fragment`, `water.WATER_CSS` (add to the page CSS). `px(x_ft, y_ft) -> (x_pt, y_pt)`. Closed `.water-body` paths (evenodd for lake holes) carry the entity ids; optional `_centre` paths and spring dots.

## Bridgehollow river meander (v6)
The hand-made river is not derived by `analyze`: it is the `meander` block of the river valley in `world/bridgehollow/terrain_spec.json`, computed by `generators/river_meander.py` and shared by terrain (valley, floodplain, monotone bed) and `water.json`. Regenerate with `python world/gen_bridgehollow.py --terrain --no-town --meander gentle|lazy|straight [--meander-amplitude FT --meander-wavelength FT --meander-seed N --width-var F]` or the panel Water tab block "River meander". Test: `python illustrator/generators/test_river_meander.py`.
