# World pack (varrenmoor-world-pack v1)

A versioned, deterministic export of one place (`world/<place>/export/`) for the 3D pipeline (Blender, GLB, AI image-to-3D, Foundry 3D Canvas). Every entity keeps the stable id it has in `world/<place>/*.json`, so Illustrator items, 3D models and Foundry documents stay linked. Nothing in `world/` is modified by exporting; the export is cheap (about 15 s) and meant to be re-run whenever the world changes (for example after a new town generation).

```
python illustrator/generators/worldpack.py export   --place bridgehollow      # the pack (data + terrain + textures)
python illustrator/generators/worldpack.py validate --place bridgehollow      # JSON Schema + integrity (checksums, ids, materials)
python illustrator/generators/worldpack_split.py split --place bridgehollow   # per-model GLBs + export/placements.json
```
Panel: Foundry tab, "3D models (world pack)" (Export world pack, Export split models, Merge/compress, Push models, Publish) and a Town tab toggle "Export world pack (3D) after Accept" (default off).

## Layout
```
export/
  manifest.json            schema version, place, generated (UTC timestamp + git commit), units, axes + exact transforms, extent, z_origin_ft, sea level,
                           scale presets and grid (from view_settings.json), Foundry calibration, terrain description, entity index, sha256 of every file
  materials.json           material id -> texture (relative path, source in the repo, sha256, mean colour), Foundry pipelineId
  textures/                the texture PNGs the pack references (copied from illustrator/presets/textures)
  terrain/                 heightmap_f32.npy|.bin (float32, signed feet), heightmap_16.png, slope.png, normal.png, albedo.png (baked shading phases),
                           splat_0.png, splat_1.png (phase weights), terrain_lod<N>.glb (mesh at step N cells)
  entities/<type>.json     roads, buildings, plazas, fields, districts, water, fences, foliage, props, lights, labels ({"items": [...]})
  placements.json          (after `split`) one entry per model file: ids, pivot, size, Foundry tile, tags, lods
  models/                  (after `split`) GLBs (+ models/textures/); optimized/<preset>_vNNN/ (after `merge`, git-ignored)
```
Schema: `world/schema/world-pack.schema.json` (`$defs`: manifest, entityFile, materialsFile, road, building, areaEntity, waterEntity, fence, foliage, label). `validate_pack()` uses `jsonschema` when installed, otherwise a built-in subset validator.

## Coordinates and scale (exact)
| Frame | x | y | z | origin | unit |
|---|---|---|---|---|---|
| **World** (every number in entities/*.json, terrain rows) | east | south (down the page) | up, absolute elevation | north-west corner | feet |
| **Blender** (Z-up, what `import_worldpack.py` builds) | east | north | up | south-west corner at `z_origin_ft` | metres |
| **glTF** (inside GLB files) | east | up | south | (Blender frame) | metres |
| **Foundry scene px** | right | down | elevation field, ft | scene offset | `px_per_ft` |

```
Blender:  X = x_ft * 0.3048      Y = (height_ft - y_ft) * 0.3048      Z = (z_ft - z_origin_ft) * 0.3048
glTF:     (X, Y, Z)_gltf = (X, Z, -Y)_blender                                   (Blender's importer undoes this)
Foundry:  px = sceneX + (x_ft - x0) * px_per_ft      py = sceneY + (y_ft - y0) * px_per_ft      (pack default 20 px/ft = 100 px per 5 ft square)
```
`z_origin_ft` is the terrain minimum floored to 10 ft (Bridgehollow: 610), so Blender Z stays small. Terrain grid: `h[i][j]` is at `x = j*cell_ft`, `y = i*cell_ft` (y south, row 0 north edge); `(nx-1)*cell_ft = width_ft`.

Worked example (the synthetic test house, 40 x 30 ft, 2 floors, centre (1020, 715) ft, floor at 700 ft):
- size: 40 ft = **12.192 m**, 30 ft = **9.144 m** (`worldpack.ft_to_m`)
- Blender position of the centre at floor level: (310.896, 239.268, 27.432) m, because 1020 x 0.3048, (1500 - 715) x 0.3048 and (700 - 610) x 0.3048
- Foundry px at 20 px/ft: (20400, 14300); on a scene calibrated at 3.4 px/ft: (3468, 2431) and the building is 136 x 102 px
- the Blender object's `location` equals the model's pivot in `placements.json` and `wp_origin_m`.

Foundry 3D Canvas conventions (from `foundry-3d/README.md`, `foundry-bridge/make-scene.ps1`, `foundry-tools/vtt/item.py`): tile `x, y` is its centre; width = model X, height = model Y, depth = model Z in px (100 px = 1.524 m, i.e. 20 px/ft); `elevation` is in feet; flags `levels-3d-preview.model3d`, `depth`, `autoGround`, `autoCenter`. `foundry-3d/README.md` says a tile appears turned 180 degrees at rotation 0 (use 180), while `make-scene.ps1`/`item.py` say rotation 0 puts plan north at the canvas top. The pack takes the second (`foundry.tile_rotation_deg: 0` in the manifest, copied into every tile). **Check once with `foundry-3d/generators/orientation_test.py`** and change the manifest value (or `rotation_deg` per model) if your Foundry disagrees.

## Entities (what each carries)
Every item: `id`, `name`, `kind`, `status` (canon|proposed), `notes`, `links`, `source` (repo file), `foundry.pipelineId` (`world:<place>:<id>`), `tags` {`layer`, `subtype`, `district`, `ring`, `group`, `id`}.
- **roads**: `points` [x,y,z] (graded centreline, per-vertex elevation), `width_ft`, `class` (road/street/lane/alley/bridge, same classifier as the map fills), `surface` {material, tile_ft} from the style table, `grade_max`, `cut_fill_ft`, `outline` (offset polygon), `bridge` {deck_elevations_ft, water_surface_ft, clearance_ft} for bridges, `fords` (stretches that cross water without a bridge).
- **buildings**: `polygon`, `area_ft2`, `floors`, `base_elevation_ft` (floor), `skirt_depth_ft` (foundation below ground), `wall_height_ft`, `height_ft`, `obb` {centre, angle_deg, length, width}, `roof` {type, pitch, ridge_axis_deg, ridge_height_ft, overhang_ft, surface}, `wall.surface`, `district`, `interior` {json, room_ids, door_ids} and the `rooms`/`doors` arrays. Roof and wall data do not exist in the world JSON yet, so they are **derived** (listed in `derived`): 10 ft per storey, roof type/pitch by kind, roof material picked with the same seeded choice as the 2D fills (the roof in 3D matches the roof on the map), wall material by kind (`WALLS` in worldpack.py).
- **plazas** (districts of kind `square`), **fields** (`crop`, surface), **districts** (rings): `polygon`, `area_ft2`, `elevation_ft`.
- **water**: `polygon`, `centerline`, per-vertex `widths_ft` (measured from the polygon), `surface_elevations_ft` (derived: terrain along the centreline, never rising downstream), `bed_elevations_ft`, `depth_ft`, `flow`; lakes carry `level_ft`. In the GLB (`worldpack_water.py`) every water surface is one mesh with the material `VB_water_<preset>` (river / pond / lake / ocean, from the water `kind`: river|stream = river, pond, lake, sea = ocean; the panel's Water group can force one preset), UVs in 10 ft units (river: u across, v downstream; lake/pond/sea: u east, v south), no textures, and the custom vertex attribute `_VBWATER` (VEC4 float: shore 0..1 from the bank, slope 0..1, heading/360 of +v, marker 0.5). Rivers have 9 vertex rows across so the shore factor has interior values; lakes are subdivided. The node extras carry `vbWater` {kind, preset, mode, flow_speed, wave_height, wave_scale, transparency, depth_tint, foam, wind_dir, slope_speed, shallow_color, deep_color}; presets live in `presets/water/presets.json`, per-place values in the panel state (`water3d`). The 3D Canvas shader that animates it is `foundry-bridge/water/vb_water.js`, pushed as the tile flag `onAnimation` (see FOUNDRY_3D_CANVAS_NOTES.md section 9). Gltfpack / merge: keep the water layer out of gltfpack (it drops or quantises custom attributes); `merge_export` keeps `_VBWATER` only when every merged mesh has it.
- **fences**: derived from field boundaries (`points`, `height_ft` 3.5, closed). **foliage**: one entry per instance from `world/<place>/scatter/*.json` (`species`, `points`, `scale`, `rotation_deg`, `height_ft`); an empty list when no scatter exists (Bridgehollow has none yet). **lights**: from `lighting.json`/`lights.json`/panel_state `lighting` when present (empty otherwise). **props**: reserved. **labels**: one 3D tag anchor per named entity (`text`, `entity`, `anchor` x,y,z).
- **terrain splat**: `terrain.splat` lists the phase channels (`base` + the shading phases of panel_state, else `alpine_steep`) per RGBA PNG; weights sum to 1 (painter-order composited exactly like the 2D shading), so a shader can blend rock/grass/farmland/snow textures listed in `terrain.splat.phases[].material`. `albedo.png` is the same blend baked at 0.5 px/ft for tools that want one texture (UV = x/width, y/height).

## Python API (`illustrator/generators/worldpack.py`)
`export_world(place, out_dir, lod=(1,4), world_root=None, terrain_source=None, ...)`, `load_pack(path)` -> `WorldPack` with `.manifest .entities .materials .frame .heights`, `.list(type)`, `.get(id)`, `.polygon(id, with_z)`, `.elevation_at(x, y)` (bilinear), `.to_blender()`, `.from_blender()`, `.to_foundry_px()`, `.polygon_blender(id)`; module helpers `ft_to_m`, `m_to_ft`, `polygon_area`, `carved_heights(pack)` (river bed cut), `road_conformed_heights(pack)`, `validate_pack(path)`. The loader needs only numpy.

## How the 3D pipeline consumes it
1. **Whole scene in Blender**: `blender -b --factory-startup --python foundry-3d/blender/import_worldpack.py -- world/bridgehollow/export --blend scene.blend [--glb scene.glb] [--layers terrain,buildings] [--no-carve] [--no-conform]`. One Collection per layer (`buildings/dis_authority`, `roads/street`, `foliage/oak`, ...), every object named by its entity id, origin at its pivot, custom properties `wp_id, wp_layer, wp_type, wp_subtype, wp_group, wp_district, wp_pipelineId, wp_file, wp_origin_ft, wp_origin_m, wp_scale_m_per_ft`; scene properties `wp_*` and metric units. Roads are ribbons on the graded centrelines (terrain is pulled to the road bed, ribbons float 0.25 m above, so nothing is coplanar), bridges have a deck with thickness, rivers carve the bed, buildings are extruded footprints with gable/hip roofs.
2. **Edit** objects individually in Blender (save the .blend).
3. **Split export**: `python illustrator/generators/worldpack_split.py split --place bridgehollow [--split buildings=entity,roads=group]` writes the GLBs and `placements.json` from the pack (pure Python), or write your Blender edits back with `blender -b scene.blend --python foundry-3d/blender/export_worldpack_split.py -- <pack> [--ids bld_x]`: same file names, ids and pivots, so re-exporting one edited object never moves it or renames it. Granularity per layer: `layer` (one file), `group` (per tags.group, e.g. buildings by district), `entity` (one file per id), `species` (foliage: one template GLB + many instances), `none`. Presets: `--split-preset default|layers|districts|individual`. Default: terrain/water/roads/plazas/fields/fences one file each, buildings one per id, foliage per species.
4. **Merge/compress** (below), then **push**: `python illustrator/generators/foundry_push.py push-models --placements world/bridgehollow/export/placements.json --scene-name "ZZ Model Push Test" [--layers buildings] [--lod 1] [--dry-run]`.
5. **AI image-to-3D / other tools**: use `terrain/*`, `textures/` and the entity JSON directly; every file is in feet with the transforms above.

### Models and placements (`placements.json`)
Meshes are in object-local space around the **pivot** (horizontal bbox centre, lowest z). Per file: `id` (pipelineId `model:<place>:<path>`), `file`, `kind` (mesh|instances), `layer(s)`, `group`, `ids` (entities inside; multi-entity files keep each as its own node named by id), `pivot` {x_ft, y_ft, z_ft, blender_m, foundry_px, rel_z_ft}, `rotation_deg`, `scale`, `size_m`/`size_ft`, `tile` {x, y, width, height, depth, elevation_ft, rotation} at the pack's px/ft, `members` (offsets of each id inside the file), `instances` (foliage), `tris`, `bytes`, `sha256`, `lods`. `push-models` converts with the **target scene's** calibration (`flags.varrenmoor.calib`: ppf, x0, y0, sceneX/Y written by `push-scene`) so models land on the map pushed from Illustrator at true size, else the pack default. Tiles are upserted by pipelineId (`model:<place>:<id>`; each tree is `model:<place>:<tree id>`), so a second push updates in place; `--prune` removes pipeline model tiles not in the push; documents without our flag are never touched. GLBs are copied to `<assets>/art/<place>/models/<set>/<name>_vNNN.glb` (the next version, or the existing one when byte-identical) with the shared `textures/` folder beside them (GLB texture URIs are relative). Foundry elevation is `pivot z - z_origin` in feet with `autoGround`; `autoCenter` is off because the pivot is the centre.

### Authoring -> Blender editing -> split export -> merge/compress -> Foundry
```
 Illustrator / world JSON (feet, ids)
        | worldpack.py export                  (Panel: Export world pack (3D); optional after Accept)
        v
 world/<place>/export  (pack)  ---> AI image-to-3D, shaders, other tools
        | import_worldpack.py  (Blender: collections per layer, objects = ids)
        v
 edit in Blender (save .blend)
        | export_worldpack_split.py (edited objects)   or   worldpack_split.py split (from the pack)
        v
 export/models/*.glb + placements.json   <- individual sources, never overwritten by merge
        | worldpack_split.py merge --preset layer|district|all|individual
        v
 export/optimized/<preset>_vNNN/ (merged GLBs, LOD files, merge_report.json)
        | foundry_push.py push-models   (or worldpack_split.py publish)
        v
 Foundry 3D Canvas tiles (flag pipelineId, upsert)
```
Commands in order: `worldpack.py export` -> `blender ... import_worldpack.py` -> edit -> `blender scene.blend ... export_worldpack_split.py -- <pack>` -> `worldpack_split.py merge --preset layer` -> `foundry_push.py push-models --placements <optimized dir>/placements.json --scene-uuid ...`. One command for the last two: `worldpack_split.py publish --preset layer --scene-uuid Scene.xxx [--dry-run]`.

### Merge / compress (`worldpack_split.py merge`)
Presets `all`, `layer` (all terrain, all buildings, all foliage ...), `district` (layer x district), `individual` (no merge). Each merged group is one GLB with one primitive per material (draw calls = materials, not objects), a `members` lookup (id, layer, source file, position) so picking and links still work, and LOD variants (`lod1`, `lod2`: vertex-clustering decimation, `lods[].suggested_distance_m`; 3D Canvas has no automatic LOD, choose with `push-models --lod 1`). The report (`merge_report.json`, also printed) gives files, triangles, draw-call estimate (primitives; foliage instances count one each), texture memory (unique textures as RGBA with mips) and GLB size before and after. Faces that lie entirely below the terrain are dropped (buildings have no floor caps, so nothing is removed from a pristine pack; it matters for edited models). Output goes to `optimized/<preset>_vNNN` (new version each run); sources are only read.
Not done, and why: **texture atlases** (the pack's textures are seamless tiles with repeating UVs, which an atlas cannot repeat; they are shared per material instead, so merging already collapses materials), **KTX2/WebP texture compression** (`gltfpack` 1.3 is now installed, but the npm build has no BasisU or WebP encoder and no `basisu`/`toktx` is on PATH; 3D Canvas also does not appear to load KTX2, see the compatibility section), **GPU instancing** (foliage is one template GLB with one tile per tree, which shares the geometry in memory; `EXT_mesh_gpu_instancing` is not used).

### Foundry/3D Canvas compatibility (glTF features)
Source checked (2026-11-07): the public source of the module (`theripper93/levels-3d-preview`, module.json version 9.0.0, Foundry v14; the manual says "supports lighting and animated models" and nothing else about formats) and the bundled three.js `GLTFLoader` in its `index.js`. **Not verified in your running Foundry**: the installed copy on Vega was not readable from here, so confirm with the test below.

| Feature | Status | Basis |
|---|---|---|
| Plain glTF 2.0 / GLB, external relative textures (PNG/JPG) | works | standard three.js loader; used by the existing pipeline |
| `KHR_draco_mesh_compression` | **supported** | the module's own `GLTFLoader` wrapper calls `setDRACOLoader`, decoder fetched from `https://www.gstatic.com/draco/versioned/decoders/1.5.7/` (the Foundry client needs internet access) |
| `EXT_meshopt_compression` | **probably not** | no `setMeshoptDecoder` call found; three.js throws "setMeshoptDecoder must be called before loading compressed files" for files that *require* it |
| `KHR_texture_basisu` (KTX2) | **probably not** | no `setKTX2Loader` call found |
| `KHR_mesh_quantization`, `KHR_texture_transform`, `EXT_texture_webp`, `EXT_mesh_gpu_instancing` | decoded by three.js core, so should load | built into the bundled loader (webp needs a browser with WebP, i.e. all current ones); instancing inside one GLB is not used by the pipeline |
| Animations | supported (`AnimationMixer` in the module; module page says animated models) | not used by the pack |
| LODs | none automatic | choose with `push-models --lod N` |
| Max texture size | the GPU limit (usually 8192 or 16384); the module reads `maxTextureSize` | keep textures at or under 4096 for memory |
| Triangle / draw-call budget | not published | pack default: ~300k triangles, ~150 draw calls in view (own estimate) |
| `scenes` | the module keeps **one** scene: if a GLB has several scenes it uses `scenes[2]` when present, else `scenes[0]` | our GLBs have one scene |

Tile mapping (from the repo notes, not re-verified here): tile `x, y` is the centre in scene px; width = model X, height = model Y, depth (flag) = model Z, all in px at 20 px/ft; `elevation` is feet above the ground with `autoGround`; `autoCenter` is off because the pack pivot already is the centre; tile `rotation` is degrees (see the orientation conflict above; `illustrator/generators/tile_rotation_inspect.py` pushes the inspection scene "ZZ Tile Rotation Inspect").

**gltfpack measurements** (1.3, on `terrain.glb`, 72 000 triangles, 2.03 MB, one material; triangle counts are unchanged by every variant; flags used by the script: `-kn -km -tr -vp 16`):

| Variant | Size | Required extensions |
|---|---|---|
| source | 2.03 MB | none |
| `-noq` (plain floats, nodes/materials kept) | 1.60 MB | none |
| `quant` (quantised, no meshopt) | 1.02 MB | `KHR_mesh_quantization` |
| `-cf` (meshopt with uncompressed fallback buffer) | 361 KB | `KHR_mesh_quantization` (meshopt optional) |
| `meshopt` (`-cc`) | 265 KB (7.7x smaller) | `KHR_mesh_quantization`, `EXT_meshopt_compression` |
| `-cc -noq` (meshopt, floats) | 721 KB | `EXT_meshopt_compression` |

`roads.glb` (908 triangles, 5 materials): 52.9 KB -> 12 KB with plain `-cc` (but that merges the 29 named nodes into one and drops the names, so `-kn -km` is required: 25 KB), 35 KB quantised only. A 16-triangle building: 2.7 KB -> 3.1 KB (tiny files grow; do not compress individual buildings). Quantised files use `KHR_texture_transform` to rescale the repeating UVs (fine for three.js). Texture compression (`-tc`, `-tw`) is unavailable in the npm gltfpack; textures stay PNG (use `-ts`/`-tl` only after resizing elsewhere).

**Recommended preset order** (`worldpack_split.py merge --compress ...`, per-file via gltfpack):
1. **`none` (default, safe).** Plain glTF, no extensions; always loads.
2. **`quant`.** Only `KHR_mesh_quantization` (core three.js); about half the size. Test one file first.
3. **`meshopt-fallback`.** Meshopt with a fallback buffer; a loader without a meshopt decoder should use the uncompressed fallback, a loader with one uses the small data. Larger than `meshopt`; test once.
4. **`meshopt`.** Smallest; only after the check below shows 3D Canvas loads `EXT_meshopt_compression`.
5. Draco is supported by the module but gltfpack cannot write it (use `gltf-transform draco`); it needs internet at the table and decodes slowly, so it is not offered.
6. KTX2/WebP textures: not available here; skip.

Check once: `worldpack_split.py merge --place bridgehollow --preset layer --compress quant` (and `meshopt`), `push-models` the result into `ZZ Model Push Test`, and see whether the terrain tile appears; an unsupported extension shows as an empty tile and a console error. Record the verdict here. The script passes `-vp 16` (16-bit positions) to keep terrain heights precise.

### Recommended Foundry scene budget (starting point, not measured on 3D Canvas)
About 300k triangles and 150 draw calls in view, texture memory under 256 MB, one file per terrain/water/roads layer, buildings merged by district for the town view and individual only where you edit or animate. Bridgehollow split (136 buildings, no foliage): 79k triangles, 311 draw calls individually, 19 after `merge --preset layer`. Measure with the report and adjust once you see the frame rate.

## Versioning and conventions
`schema_version` 1.x is additive (new optional fields); a major change bumps `format` consumers' check in `load_pack`. Output is deterministic (sorted, rounded to 0.001, no clock except `generated.timestamp`; `--timestamp` pins it). `export` clears `terrain/ entities/ textures/` only; `models/` and `placements.json` are yours (re-run `split` after a new export, or use `reexport --id ...`, which rebuilds only the files containing those ids and keeps every other entry). Tests: `python illustrator/generators/test_worldpack.py` (round trip, scale, determinism, tags, placements, idempotent re-export, merge lookup, push-models mock, Blender import/edit/re-export when Blender is installed).

## Roof modes (`worldpack_roofs.py`)
`worldpack.py export --roof-mode`, `worldpack_split.py split|reexport --roof-mode` (placements.json `roof_mode`, manifest `foundry.roof_mode`; split uses the manifest value when the flag is omitted):
* `none` (default): roofs stay in the building mesh; behaviour unchanged.
* `per_building`: layer `roofs`, one model per building `models/roofs/<id>_roof.glb` (node `<id>_roof`, extras `isRoof`, `roofMode`, `roofOf`). Buildings with a layout lose their `<id>_roof` node (roof + top ceiling plate + beams) to this file; other buildings are split by the interiors rule (roof material, or a vertex above the wall top: gables, chimneys, towers, trim). Placements entry has `roof: {mode, buildings, chunk}`.
* `per_scene`: all roofs merged into ONE node in `models/roofs.glb` (when over 300 000 roof triangles: one file per district `models/roofs/roofs_<district>.glb`).
* `merge` never merges a roofs file with anything (every preset keeps each roofs file as is, extras kept), so the toggle survives Merge/compress. Roof files are written without unused vertices (bbox and tile elevation are the roof's own).
* Push: `push-models` adds `flags.varrenmoor.roof = {mode, buildings, scope, chunk}` to roof tiles (`--roofs-hidden` creates them hidden) and removes stale roof tiles of another mode (full pushes only). `foundry_push.py roofs --scene-uuid U --roof-state hide|show|toggle [--ids bld_a]` and `install-roof-macros` (source `illustrator/foundry_macros/*.js`) hide/show them; hiding = tile `hidden` (3D Canvas: `mesh.visible = !hidden || GM`, GM sees a 50% ghost). No module change needed. Test: `test_worldpack_roofs.py`.
* Cost on `bridgehollow__dyers_walk_local` (25 houses, 82 k triangles): none 28 tiles / 196 nodes / 624 est. draw calls; per_building 53 tiles / 196 nodes / 624 draws, identical triangles (+25 tiles, 5 554 roof triangles, 0.4 MB); per_scene 29 tiles / 172 nodes / 521 draws (roofs 319 KB in one file).

## Home interior styles (`interior_styles.py`, `presets/interiors/presets.json`)
Buildings that carry a generated `layout` (a door; `interiors.py`) get a style. Resolution: entity key `interior_style` (copied from the building JSON) > manifest `foundry.interior_style` (`worldpack.py export --interior-style`, `worldpack_split.py split|reexport --interior-style`; applied when the meshes are built, so re-split to change it) > `kind_map` (`auto`, the default: house/cottage/no kind = `rustic_cottage`, farmhouse = `farmhouse`, townhouse/manor = `burgher_townhouse`, tenement/hovel = `poor_hovel`, every other kind = `plain`). An explicit scene style applies to every building with an interior. Unknown names fall back to `auto`.
* `plain`: the original look (byte-identical geometry to before the presets).
* `rustic_cottage`: `mat_int_plank` floor and ceiling, `mat_int_frame` (timber-frame plaster panel) walls on the inner shell skin and partitions, 0.6 x 0.85 ft beams every 4 ft, timber posts at partition ends and door jambs, `mat_int_stone` chimney breast with a mantel beam and a cauldron, trestle table with goods, two stools, rag rug (`mat_int_rug`) under the table, drying rod with herb bundles and a pot over the hearth, shelves with jars, iron-strapped chests, straw-tick box bed.
* `farmhouse`: as rustic but `mat_int_flag` flagstone floor, `mat_int_lime` lime-washed walls, two drying rods.
* `burgher_townhouse`: plank floor, lime walls and ceiling, fine 3 ft joists, legged table with candle and jug, shelf goods, canopy bed, mantel; no posts, stools or hanging goods.
* `poor_hovel`: `mat_int_earth` floor with straw patches, `mat_int_boards` walls, one stool, straw pallet bed, shelves/desks/counters dropped and every second minor prop thinned out.
Geometry stays merged per storey (`_int_f<s>`, `_props_f<s>`, `_roof` nodes unchanged); decor is placed with rejection tests (inside the room, clear of other props and the stairs) and is deterministic per building. New materials: textured `mat_int_plank`, `mat_int_lime`, `mat_int_rug` (generators in `worldpack_pbr.py`), `mat_int_frame/stone/boards` (existing generators under their own ids), `mat_int_flag/slab/earth` (preset images), flat `mat_pottery`, `mat_herb`, `mat_linen`. Preview and stats: `interior_styles_preview.py` (writes `illustrator/out/interior_styles/`). Tests: `test_interior_styles.py`.

## Split / merge and the manifest (2026-11-07)
* `worldpack_split.py split|reexport` into the pack folder now re-hashes `manifest.files` (listed files re-hashed, vanished ones dropped, `placements.json` and `models/**/*.glb` added), so `worldpack.py validate` passes after a split.
* `merge` keeps door leaves (glTF nodes with `isDoor`) out of every merge group: each stays its own node in its building's merged file (hinge position and extras preserved, `read_glb` now reports the node translation as extras `_t`), for every preset. Test: `test_worldpack_detail.py::SplitMergeDoors` on a copy of `bridgehollow__dyers_walk_local/export`. LOD files do not carry doors.
