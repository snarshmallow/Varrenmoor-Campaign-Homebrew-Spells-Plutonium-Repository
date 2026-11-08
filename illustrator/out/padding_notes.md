# Padding (distant surroundings) for Foundry 3D Canvas, 2026-11-08

Tool: `illustrator/generators/padding_heightmap.py` (+ `padding_textures.py`), push: `foundry_push.py push-padding` (same code), panel tab "Padding", presets `illustrator/presets/padding/*.json` (+ `textures/*.json`, user presets in `presets/padding/user/`), tests `test_padding_heightmap.py` (14) and `panel/test/test_padding_jobs.js` (13).
Foundry 14.360, levels-3d-preview 9.0.29 (source read from `Data/modules/levels-3d-preview/scripts/main.js createTable()` and `helpers/applyHeightmap.js`, then every number below checked on the live test scene `ZZ Padding Test` Scene.SZUxMHLV8pN7ZHg8).

## 1. What the scene "3D" settings do (flags.levels-3d-preview)
| Flag | Meaning (measured / read) | Range |
|---|---|---|
| `renderTable` | `none`, `table`, `matpaper/wood/cloth/blueprint` (module textures), `matcustom` (your `tableTex`/`tableColor`). With a heightmap and any `mat*` option the table is a 200 x 200 unit box with 100 x 100 cells. | |
| `tableTex` | tiled texture on the table. UV repeats 20x over the 200 units when a heightmap is set (1 repeat = 10 units = 500 ft at 20 px/ft), 200x without. NOT alignable to the heightmap. Multiplied by `tableColor`. | |
| `tableColor` | multiplies the texture (`#ffffff` = texture as is; the old `#341f0f` darkens it; the black-tone texture made the black horizon band) | |
| `tableHeightmap` | image path. Drawn into a 128 x 128 canvas, **8-bit red channel** only (a 16-bit PNG is read as its high byte: measured). Row 0 = north (min z), col 0 = west. | |
| `tableHeightmapScale` | multiplier of the displacement | 0.01 to 10, step 0.01 |
| `enableFog`, `fogColor`, `fogDistance` | linear THREE.Fog from 1 unit to `fogDistance` px; **also sets camera.far = fogDistance** (otherwise far = 100 units = 5000 ft at 20 px/ft, where the table is cut off and the sky shows) | |
| scene `padding` | canvas = scene + padding rounded **up** to whole grid squares per side (6130 x 7236, 0.25, grid 100 -> 9330 x 11036, scene at 1600,1900: measured). It only changes the canvas centre and R below. | |
| Level `elevation.bottom` (scene.levels[0]) | lifts the table plane by that many ft (measured: bottom 10 -> table +0.2 units at 20 px/ft). Not a scene flag; set through the bridge `update` with `levels: [{_id: defaultLevel0000, elevation: {bottom, top}}]`. | any |

## 2. The scale formula (measured on the live mesh; model error 4e-6 units, and every vertex of the pushed image matches the prediction exactly)
Units: 1 world unit = 1000 canvas px = `1000/ppf` ft (ppf = grid px / grid ft, 20 for our pushes -> 50 ft).
Table: box 200 x 200 units centred on the canvas centre, 100 x 100 cells (vertex spacing 2 units = 100 ft at 20 px/ft), top face `0.011 units = 11 px` below the level's bottom. For vertex i, j (u = i/100): pixel = `image[floor(v*128)][floor(u*128)]` (nearest, no interpolation; the image is exactly 128 so there is no resampling).

    height above the table plane [units] = r/255 * 10 * tableHeightmapScale * clamp((d - R) / 10, 0, 1)
    d = distance of the vertex from the canvas centre [units];  R = max(canvas w, canvas h) / 2000 [units]
    scene elevation [ft] = level.bottom - 11/ppf + height * 1000/ppf

* pixel 255 at scale 1 = 10 units = **500 ft at 20 px/ft** (1000 ft at 10 px/ft); `tableHeightmapScale = max_ft / (10 * 1000/ppf)`. 8-bit steps: max_ft/255 (3 ft for 765 ft).
* Inside the circle R the table is FLAT; relief ramps in linearly over the next 10 units (500 ft). Triangles: BoxGeometry diagonal from (ix, iz+1) to (ix+1, iz).
* The last vertex row and column (x or z = +100) are never displaced (u = 1 reads outside the canvas): a flat rim, beyond the camera far plane in practice.
* So the module cannot make the table meet a terrain mesh at its edge: inside R it is a plane. Hence the apron below.

## 3. How the surroundings are built (`padding_heightmap.py`)
Frames: place feet (x east, y south), elevation = ft above `z_origin_ft` (same datum as the GLB tiles and Foundry tile elevations). The terrain tile heights are read **from the exported `models/terrain.glb`** (road conforming makes it differ from heightmap_f32 by up to 15 ft at the Dyers Walk edges). The parent bowl heightmap (`world/bridgehollow`, 10 ft cells) is sampled through the region.json origin chain (child = parent - origin).
1. Desired surroundings C(x,y): real bowl inside the bowl, preset continuation outside (ridged noise whose amplitude scales with the bowl's measured relief, spectral exponent clamped for smoothness), preset can fade to synthetic hills / walls / flats.
2. Table plane level B = lowest tile vertex (or `--base`), so the table is never above the terrain tile. Image: `r = (C - B)/(10 * scale * 1000/ppf) * 255`, zeroed in every table cell touching the apron (+ a 500 ft taper), so the table under and around the apron is exactly flat.
3. Apron: graded-ring GLB tile (2.5 ft nodes at the terrain edge growing to 12 ft; rings joined by a zipper so there are no T-junctions) from the terrain edge outward `--blend` ft. Height = quintic Hermite from the tile edge (height, slope, curvature of the tile along the outward normal, smoothed along the edge) to the exact table surface + 0.02 ft at the outer ring, plus detail noise that is zero at both ends. Tile: autoGround false, elevation = lowest vertex, pivot = bbox centre.
4. Texture: height/slope colour model of the skybox mountains (meadow, conifer, rock, snow line) baked into one apron map aligned to the mesh, blended to the terrain tile's own (blurred) colour at the seam and to the table tile's mean colour at the outer edge; the tiled table texture is a periodic fbm landscape tile with the same palette. Fog colour = the sky preset's haze colour.

Verified numbers (Dyers Walk, bowl-ridge, blend 200 ft): apron edge vs terrain.glb edge nodes max step **0.000 m** (the test compares the GLB vertices), apron outer ring vs table **0.006 m** (the 0.02 ft delta; limit 0.05 m); slope jump at the seam up to 0.24 (the tile's own edge slope is noisy at its 2.5 ft nodes; the shape follows the smoothed profile). Without the apron the tile edge is 62 ft above the table (that is the "skirt" seen before). Texture colour step at the apron/table border is visible in the overhead shot.

## 4. Flags set by a push (`push-padding`, dry run by default in the panel)
`renderTable matcustom`, `tableTex`, `tableColor #ffffff`, `renderBackground false`, `tableHeightmap`, `tableHeightmapScale` (or empty when the preset is flat), `enableFog`, `fogColor`, `fogDistance`; level `elevation.bottom` = B; tile `model:<place>:padding_apron`; assets under `assets/varrenmoor-3d/art/<place>/padding/` (versioned `_vNNN`). Optional `--scene-padding`. Nothing else in the scene is touched.

## 5. Screens (illustrator/out/foundry_screens/)
`padding_overhead.jpg` (apron ring around the terrain tile, table beyond), `padding_ground_west.jpg`, `padding_ground_north.jpg` (ground level: bowl mountains behind the apron, no black band). The old band was the black-tone `tableTex` with `tableColor`.

## 6. Not verified / known limits
* Table texture repeats every 500 ft (cannot be changed; no flag); fog and far-colour match to the skybox were only eyeballed; the sky in the test scene looked flat blue (skybox flag not re-checked here).
* The padding relief is only as good as the module's 100 ft vertex spacing; near the town the apron carries all the detail.
* Colour at the apron/table border is a mean-colour match, not a seamless blend.
* Heights past the bowl rim are synthetic; the bowl edge itself is clamped (mild straight-line streaks in the plan preview).
* Tested live only on `ZZ Padding Test` (GM view; I called `scene.view()` on it, the GM tab is left on that scene). Players' view, performance with the full 28-tile pack, and non-20 px/ft scenes (maths covered by tests) not tested live.
* Terrain tile edge is flat-shaded to the 8-bit table: relief steps of about 3 ft.

## 7. Streak fix (2026-11-08)
Cause: the apron colour near the seam copied the terrain colour of the NEAREST edge texel along the outward ray, so colour bands along the edge (roads, tree patches) were extruded into radial streaks, strongest where the apron is steep and seen from above. Fix in `padding_textures.apron_albedo` (`streak_fix=True`, default): the lookup blur widens with distance (45 ft to 160 ft), the lookup point is warped along the edge by noise that grows with distance, and slopes above about 18 degrees fade to the per-pixel height/slope palette (never stretched) sooner. Offline check: `test_padding_streaks.py` (synthetic edge bands, tangential colour variation 12.0 -> 3.5 on the apron) and the before/after render `illustrator/out/padding_streaks_before_after.png`. Not yet seen live in Foundry (needs a padding push of Dyers Walk).

## 8. Apron ring fixes (2026-11-08, offline)
`Apron(edge_fade_ft=110, edge_wide_ft=400)`: edge features narrower than the wide smoothing (river channels, road cuts) fade out over 110 ft (quintic) into the edge profile smoothed along each side (1D tables, sampled every cell, soft corner blend); exact tile heights at the seam. `apron_albedo(table_tile=..., tile_ft=...)`: the outer ring uses the table tile at its own density instead of a flat mean colour; inside, tile luminance mottling x0.5 from 60 ft. Test: `test_padding_streaks.ChannelFade`. Before/after: `out/apron_fix/`.

## 9. Terrain edge, seam normals, slope easing (2026-11-08, offline)
* River cliff at the map edge: `terrain_edge.ease_carve_at_edge` (called from `worldpack_mesh.terrain_heights`, kwarg `carve_edge_ease_ft`, default 100, 0 = off): the carve (`wp.carved_heights`) is faded back to the authored bank heights over the last 100 ft (quintic, exact bank height on the boundary). The water keeps its level and goes under the rising bed (natural shoreline, no flat cut visible); interior carve, road grading, bridge carving and pads are untouched (they run after). So the terrain edge heights are the bank level and the apron no longer inherits a 17.5 ft trench. If the base heightmap itself already has a valley at the edge (the bridge scratch has a 10 ft authored one) that valley stays at the seam and the apron fades it (section 8).
* Lip at the seam: terrain edge vertex normals are one-sided area-weighted, the apron's ring 0 averaged only its own faces (up to 62 deg apart at the channel, 13 deg on Dyers). `write_outputs` now sets ring 0 normals to the terrain mesh's own edge normals (`terrain_edge_normals`, `grid_vertex_normals`), difference 0. No skirt/underside exists; heights match exactly (table offset 0.02 ft only at the outer ring).
* Slope smears: `Apron(relief_ease=0.75)` mixes the straight ramp into the quintic (equal at both ends, so seam and table slopes are kept); the wide edge profile is now ONE periodic table around the boundary (smoothing runs across the corners; the corner fan wedges on Dyers are gone) with a softer side blend.
* Numbers (tools/apron_fix2_render.py; max apron slope beyond 20 / 40 ft from the seam): bridge scratch 56.9 / 51.2 deg -> 22.4 / 15.0; Dyers 63.9 / 63.9 -> 40.8 / 30.8 (the rest is the tile's own 38 deg edge slope and the hill dropping to the table). Previews `out/apron_fix2/<place>_{before,ease0,after}_{overhead,slope,oblique}.png` (before = old code, ease0 = new apron without the carve ease, after = everything; my crude painter's renderer, white hairlines are its gaps). Tests: `test_terrain_edge.py`.
* Not done: water mesh still ends at the tile boundary (buried under the bed there); triplanar texturing on steep apron parts (not needed after easing, not tried). Needs a pack re-export + split/merge + push to see live.
