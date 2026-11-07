# Bridgehollow full-feature sample (2026-11-07)

Files: `illustrator/out/bridgehollow_sample_full.ai` / `.png` (bowl, 1 in = 200 ft), `bridgehollow_sample_full_town.ai` / `.png` (town, 1 in = 100 ft), sources in `illustrator/out/sample/` (SVGs, shading PNGs with .json/.pgw sidecars, hide-LABELS / hide-Leaders exports). Jobs: `illustrator/jobs/done/sample_bowl2.*`, `sample_town.*` (`sample_bowl` was the first try, see below).

## How it was made
- `render_world.py --view bowl|town --preset bowl|town --contours --contour-mask --label-offset --leader-style elbow --terrain-source patched --water-source world` (water = `world/bridgehollow/water.json`, id `wat_river`; contours 10/50 ft with labels; town v4 generator output; grid, scale bar, north arrow from the preset).
- `shading.py --phases alpine_steep --scale-ft-per-in 200|100 --dpi 150` (default lighter hillshade strength 0.35, ambient 0.3). Bowl PNG 1800x1125 px, town PNG 3600x2250 px.
- Panel jobs: `place_svg mode open`, `place_image` (rect from `panelio.py view`: `[m+(x_min-x0)k, ...]`), `get_layer_tree`, `set_visible`, `save_ai`, `export_png`.

## Verified
- Georeferencing: shading rect (bowl) = [180,126,1044,666] pt = exactly the `bounds_place` path in the SVG GUIDES/Bounds layer; contours and rock/snow bands line up in the exported PNG.
- Layers in the saved doc (get_layer_tree): NOTES, LABELS (Leaders 24, Labels - Districts/Streets/Buildings/Rooms/Elevation 59), ART - Top/Fills/Textures/Masks, LINES (Walls, Buildings 139, Blocks, Roads 39, Water 1, Terrain/Contours - Minor 104 + Index 81, Fences 7), GUIDES (Grid, Scale bar, North arrow, Bounds), ART - Shading (locked, 1 image) at the bottom.
- LABELS off changes 4055 px of the export, Leaders off 507 px; both restored to visible before saving.
- `get_layer_tree` is known to the running panel (no reopen needed).

## Findings
1. `place_image` ignored `below` when the target layer already existed (e.g. after `ensure_layers`); with ART - Textures above LINES the opaque shading covered the linework. Fixed in `panel/jsx/host.jsx` (reposition existing layer; takes effect after the panel is reopened). The sample uses the panel's own `ART - Shading` layer created with `below: GUIDES`, which puts the image under linework and grid.
2. The SVG art is outline-only by design (water is a blue outline, streets and buildings dashed "proposed" outlines, no fills); Illustrator shows the same. Fills come from the panel's apply_fills.
3. At 100 ft/in the shading image is larger than the artboard (it covers the whole 2400x1500 ft place) and is cropped by the artboard in exports.
