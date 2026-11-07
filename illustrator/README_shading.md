# Terrain shading phases (shading.py)

    python generators/shading.py --place bridgehollow --phases alpine_steep_calm \
        --scale-ft-per-in 100 --dpi 150 --out out/bridgehollow_shading.png [--masks] [--vector out/x.svg]

Inputs: `world/<place>/terrain/heightmap.npy` + `terrain_meta.json` (reads `cell_ft`, `size_ft`, `seed`, optional `sea_level_ft`, default 0),
and a phase file (path, or preset name from `presets/terrain_phases/`).
`--phases` defaults to `alpine_steep_calm` (the map-calm default for new renders; the original presets stay available by name).
Other flags: `--reverse`, `--order id1,id2,..` (reorder without editing), `--hillshade/--no-hillshade --azimuth --altitude --strength --exaggeration`,
`--seed`, `--sea-level FT`, `--elev-offset FT` (shift heights, e.g. to test below-datum), `--vector-cell FT`, `--make-textures`.

Output PNG is `size_ft * dpi / scale_ft_per_in` pixels (ppf = dpi/scale px per foot), saved with dpi metadata so it places at
`size_ft/scale_ft_per_in` inches. Sidecars: `<name>.json` (bounds in feet, ppf, page size in inches, y axis down, phase order) and
`<name>.pgw` (world file, pixel size in feet, +y down). `--masks` writes `<name>_masks/mask_<id>.png` (0-255 weights) for use as opacity masks.

## Phase file
```
{ "name": "...", "base_color": "#6f9a48",
  "hillshade": {"enabled": true, "azimuth": 315, "altitude": 40, "strength": 0.5, "exaggeration": 1.0},
  "phases": [ {phase}, ... ] }          (a bare list of phases is also accepted)
```
Phases are painted in list order; later phases composite over earlier ones (`out = lerp(out, tex, weight*opacity)`). Reorder the list to change who wins.

| field | default | meaning |
|---|---|---|
| id, name | | id names masks and SVG ids |
| texture | #808080 | `#rrggbb` flat colour (with grain noise) or image path (relative to the JSON, then presets/textures); tiled in world coordinates |
| tile_scale_ft | 40 | world width of one texture tile |
| elev_min, elev_max | null | signed feet (negative OK, null = unbounded) |
| slope_min_deg, slope_max_deg | 0, 90 | slope window; 0/90 = unbounded |
| elev_blend_ft, slope_blend_deg | 20, 5 | total smoothstep width centred on each edge |
| opacity | 1 | max weight |
| noise_jitter | 0.5 | 0..1+: noise shifts thresholds by up to +-40 ft elevation / +-8 deg slope |
| noise_scale_ft | 70 | feature size of that noise |
| grain | 0.06 | brightness noise for flat colours |
| texture_contrast | 1 | 0..1: pull the texture toward its own mean colour (calm presets use 0.4-0.7) |
| texture_brightness | 1 | multiplies the texture colour (calm scree 0.78) |
| enabled | true | skip phase |
| below_datum | false | if `elev_max` unset, sets it to `sea_level_ft` |
| water_depth | null | `{shallow, deep, max_depth_ft}`: replaces the texture with a colour gradient by depth below the datum (implies below_datum) |

Elevations are signed feet against the datum (`sea_level_ft`, default 0); no value is assumed positive.

## Vector output
`--vector f.svg`: per phase, polygons where weight >= 0.5 (contourpy filled contours), `<g id="phase_<id>">` with `<path id="phase_<id>_<n>">`,
filled with the texture's mean colour, painted in phase order, coordinates in output pixels (same size as the PNG). Hard edges, no blend.

## Presets (presets/terrain_phases)
temperate_valley, dry_hills, alpine_steep (Bridgehollow default), ink_wash, parchment, coastal_basin (below-datum). Elevation thresholds are
absolute feet tuned to Bridgehollow's ~620-1050 ft range (coastal_basin to about -180..250 ft); edit `elev_*` for other maps.
Textures in presets/textures are procedural tileable PNGs, regenerable with `--make-textures`.

## Calm presets and the muted control
Every preset has a `<name>_calm` twin (alpine_steep_calm is the default): the same elevation/slope phases with a top-level `muted` block,
`slope_smooth_ft` (the slope field is smoothed so scree/rock masks are not speckled), larger noise scale and lower jitter, wider blends
(snow and rock change gradually), softer scree (opacity 0.7, darker, flatter texture) and a lighter hillshade (0.36 / ambient 0.38).
`muted` = `{saturation 0..1, contrast 0..1, tint "#rrggbb", tint_strength, pivot}`: applied after the phases, before hillshade
(1 / 1 / no tint = unchanged). CLI: `--muted-saturation --muted-contrast --muted-tint --muted-tint-strength` override the preset's block,
`--no-muted` ignores it. The panel Shading tab has the same fields (they do not edit the preset file).

## Contours over shading, grid
`render_world.py --contours` samples the (calm default) shading luminance under every contour and writes a cream casing path (`<id>_halo`,
classes contour-halo-*) under the brown line, stronger over dark ground; index contours are 1.1 pt, minor 0.35 pt. `--contour-shading PRESET|none`,
`--no-contour-halo` for the plain lines. The grid is drawn only inside the map window (place bounds) in light lines; `--grid-full-page`
(panel Scale tab, or `grid_extent: "page"` in view_settings.json) restores the full-page grid. Note the Grid layer sits under the fill/shading
images (layer order), so inside the map it shows when the shading layers are hidden.
