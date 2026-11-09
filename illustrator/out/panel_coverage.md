# Panel coverage matrix (generators / CLI vs Illustrator panel)

Audit date 2026-11-08, branch claude/adoring-shannon-yjixst. Method: read every argparse block of the generators and grepped the panel (`panel/lib/*.js`, `*_ui.js`, `main.js`, `index.html`) for each flag.
Status: **OK** = working control with default and wiring; **NEW** = added in this pass; **PARTIAL** = reachable but limited; **CLI only** = no panel control (reason given).
"Verified live" = loaded in the real Illustrator panel (reload over the CEP debug port) and the DOM interaction checked; no job was run from the live panel (that would write the user's world files).

## World pack, split, merge, push (Foundry tab "3D models")

| Feature | CLI flag | Panel control | Status |
|---|---|---|---|
| Export pack | `worldpack.py export --place` | Export world pack (3D) | OK |
| Roof mode | `--roof-mode` (export/split) | Roof mode select | OK |
| Interior style per scene | `--interior-style` | Home interior style select | OK |
| Terrain source, LOD, style, phases, px-per-ft, z-origin, timestamp, no-textures | `export --terrain-source/--lod/--style/--phases/...` | none | CLI only (rarely changed; defaults right) |
| Split granularity | `split --split` | Split (layer=entity\|group\|layer) text box | OK |
| Split preset | `--split-preset` | More pack options > Split preset | NEW |
| Textures mode, terrain step | `--textures`, `--step` | none | CLI only (embed/none are debugging options) |
| Carve river beds | `--no-carve` | More pack options > Carve river beds | NEW |
| Conform terrain to roads | `--no-conform` | More pack options > Conform terrain | NEW |
| Road smoothing / max grade / skirt / cut-fill | `--road-smooth/--road-max-grade/--no-road-skirt/--road-cutfill` | Roads (3D) block | OK |
| Road cross slope | `--road-cross-deg` | Roads (3D) > Max cross slope | NEW |
| Road grading off | `--road-grade off` | Roads (3D) > Road grading on | NEW |
| Per-road grading (smooth, max grade, cross slope, cut/fill) | road `edit.grade` (road_grade.road_params) | Roads tab | NEW (generator + panel) |
| Merge preset | `merge --preset` | Merge preset select | OK |
| Compression | `merge --compress` | More pack options > Compression (state existed, no control before) | NEW |
| Hidden-face removal | `merge --no-hidden-removal` | none | CLI only (always wanted) |
| Foliage merge | `merge --foliage --foliage-chunk-ft --foliage-budget --foliage-impostor-ft` | Foliage tab merge group | OK |
| Keep one building as its own model through a merge | building `edit.keep_individual` | Buildings tab editor | NEW (generator + panel) |
| Reexport one entity | `reexport --id` | none | CLI only (Blender round trip; use Export split models) |
| Layers to push, LOD | `push-models --layers/--lod` | Layers to push, LOD | OK |
| Push dry run | `push-models --dry-run` | Push models (dry run) | NEW |
| Prune stale tiles | `--prune` | Prune stale tiles on push | NEW |
| Roof tiles hidden on create | `--roofs-hidden` | Create roof tiles hidden | NEW |
| Scene mode flat/3d | `--scene-mode` | Scene mode on push | NEW |
| Allow quantized GLBs | `--allow-quantized` | automatic when Compression is quant | NEW |
| Roof macros / hide / show | `install-roof-macros`, `roofs` | three buttons | OK |
| Scene audit | `scene-audit` | Audit scene tiles (read-only) | NEW |
| Interior lights | `push-lights` (+ `--dry-run`) | Lights (dry run), Push interior lights | NEW |
| Light animation, light-type filter, `--lighting`, `--lights-placements` | `push-lights` options | none | CLI only (default none is deliberate) |
| Publish (merge + push) | `worldpack_split.py publish` | Publish button | OK |
| One-shot 3D scene incl. sky, padding, lights, foliage | `push-scene-3d` | none (the tabs do the steps separately) | CLI only (convenience wrapper; the separate Skybox, Padding, Foliage tabs cover it) |
| Texture bake for the table | `bake-texture` | none | CLI only (needs a rendered image window; check in a later pass) |
| Serve URL, assets dir, px-per-ft override, set-name, table-texture | push-models options | none | CLI only |
| Delete scene | `delete-scene` | none | CLI only (destructive on purpose) |

## Scene (2D) and Foundry documents

| Feature | CLI flag | Panel control | Status |
|---|---|---|---|
| Push scene / tiles, dpi, grid, walls, drawings, tile layers | `push-scene ...` | Scene block | OK |
| `--upscale`, `--padding`, `--max-px`, `--format`, `--link` | push-scene | none | CLI only (defaults) |
| Plan (dry run) | `--dry-run` | Plan (dry run) | OK |
| Actors, items, tokens | `push-actor/item/token` | Actors, items, tokens block | OK |
| Import scene as place | `import-scene` (+ `--include/--closed-as/--force/--no-image`) | Foundry tab button and Places tab | OK (include / closed-as: Places tab fields) |
| Region link | `link-region` | Regions tab | OK |
| Bridge connection, pairing, tokens | relay | Bridge section | OK |

## Per-object editing (the gap the user hit)

| Feature | Where stored | Panel control | Status |
|---|---|---|---|
| Building style preset | building json `style` | Buildings tab | OK |
| Building interior style | building json `interior_style` | Buildings > Edit selected buildings | NEW |
| Storeys | `floors` | same | NEW (refused when a generated interior layout has another storey count) |
| Roof type, pitch, overhang, material | `edit.roof_*` | same | NEW |
| Wall material | `edit.wall_material` | same | NEW |
| No windows | `edit.no_windows` | same | NEW |
| Keep individual | `edit.keep_individual` | same | NEW |
| Door on/off, door width, per-building storey height, per-building colour | - | none | MISSING (doors come from the region detail pass; storey height is fixed at 10 ft in the mesh builders) |
| Road class, surface material, kerb on/off, width | street `edit`, `geometry.width_ft` | Roads tab | NEW |
| Road sidewalk | - | none | MISSING (the exporter has no sidewalk geometry; only kerbs) |
| Select by Illustrator selection | item names `bld_*`, `str_*` | Use Illustrator selection buttons | OK (needs the items to keep their generated names) |

## Other generators

| Feature | Panel | Status |
|---|---|---|
| Terrain base + patches (`terrain.py`, `terrain_patch.py`) | Terrain tab | OK |
| Contours, labels, label_declutter, label_offset, shading, lighting (2D) | respective tabs | OK |
| Water (river meander, carve, 3D presets, `foundry_water.py`) | Water tab | OK |
| Town generation, area, rings | Town tab | OK |
| Regions (`region_extract.py`, region_render) | Regions tab | OK |
| Foliage scatter / preview / stats / publish | Foliage tab | OK |
| Padding (`padding_heightmap.py`: preset, texture picker, blend, taper, seed, height scale, base, apron, tex px, push, scene padding) | Padding tab (texture picker present) | OK |
| `terrain_edge.py` (edge ease) | applied automatically; reported by Padding tab | OK |
| Skybox (`skybox.py`: presets, width, viewer, lighting sun, import, apply) | Skybox tab | OK |
| Bridges (`bridge_maker.py`: detect, apply, presets, preview, audit, params) | Bridges tab | OK |
| Kerbs, doors, chimneys, lots (region detail pass) | Regions tab detail toggles | OK (per region, not per road/building) |
| Places (`place_create.py`, from-text, validate) | Places tab | OK |
| Building styles (`building_styles.py`) | Buildings tab | OK |
| Interior styles preview, glb_check, textures_audit, road_height_audit, terrain_check, building_ground_audit, tile_rotation_inspect, make_fill_textures | none | CLI only (developer audits and one-off tools) |

## What is still missing (summary)

Door toggles per building, per-building storey height, road sidewalks (generator support does not exist), `bake-texture`, `push-scene-3d`, `delete-scene`, push-scene `--upscale/--padding/--link`, and the developer audit scripts. Everything else a GM would want has a labelled control.
