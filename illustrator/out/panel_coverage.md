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

## Strict parity audit (2026-11-08, second pass): "anything that relies on commands needs a matching GUI"

Machine-checked now: `illustrator/panel/lib/command_manifest.json` + `panel/test/test_command_parity.js` (fails when a command or flag of foundry_push, foundry_collision, foundry_water, worldpack, worldpack_split, object_edit, padding_heightmap, the audits or bridgectl has no manifest line, or names a control that does not exist). New controls live on the new **Tools** tab (`tools_ui.js`, `lib/tools.js`).

| Was CLI only / missing | Now |
|---|---|
| `delete-scene` | Tools > Delete scene: typed exact name arms the button, then a confirm; the scene leaves the list |
| `bake-texture` (+ `--window --crop-margin-pt --dpi --out-dir --table-texture-path --publish --name --format --px-per-ft`) | Tools > Bake ground texture, Fill from view, publish asks first |
| `push-scene-3d` (+ `--skybox-preset --no-skybox --no-padding --padding-arg --with-lights --prune-lights --foliage-placements --lights-placements`) | Tools > Push whole 3D scene (dry run / real with confirm) |
| push-scene `--upscale --padding --max-px --format --link` | Tools > Push options > Push scene (2D) |
| push-models `--ids --serve-url --assets-dir --px-per-ft --set-name --table-texture --lighting --collision-lod --scene-flag --yes` | Tools > Push options > Push models (advanced); `--yes` also for Publish |
| push-lights `--light-animation --lighting --lights-placements --prune-lights` | Tools > Push options > interior lights |
| push-walls `--wall-profile --foliage-json`, set-collision `--collision-lod` | Tools > Push options |
| push-token `--hidden --key --px`, push-actor `--portrait --token` | Tools > Push options |
| import-scene `--no-image --force --scene-json` | Tools > Push options (applied by the Places / Foundry import buttons) |
| worldpack export `--terrain-source --lod --style --phases --splat-cell-ft --albedo-px-per-ft --px-per-ft --z-origin-ft --timestamp --no-textures` | Tools > Advanced pack export |
| split `--textures --step`, merge `--no-hidden-removal`, `reexport --id`, `worldpack_split info`, `worldpack validate/info` | Tools > Advanced pack export, audits |
| `scene-audit`, `places`, `export-info` | Tools > Audits (results viewer) |
| building_ground_audit, road_height_audit, terrain_check, textures_audit | Tools > Audits with options and a results viewer |
| padding `--tex-px`, `--no-level` | Tools > Padding extras |
| object_edit `--dry`, `list-buildings`, `list-roads`, `choices` | Tools > Padding extras and per-object editing |
| macro installers scattered over tabs | Tools > Foundry macros (click mode, door sync, roofs, water shader) |

Remaining CLI-only, with reasons (all recorded in the manifest): `--placements / --pack / --out / --path / --assets-dir` (the panel always uses the pack folder; the override exists for tests), `--world-root` (tests), padding `--scene-json` (offline test input), `--kinds` (Refresh always reads every kind), `--tile-id` (always "labels"), link-region `--parent-scene-uuid / --child-scene-uuid` (found by name / last push), water `--enable-scripts / --no-panel / --placements`, bridgectl `--json / --lines`, audit `--json` file export (the viewer shows the report), terrain_check `--heightmap / --out`, tile_rotation_inspect (developer diagnostic), glb_check / scene_audit / foundry_import (libraries behind buttons), start.mjs (first-time relay setup on the Foundry PC, interactive), bridge.ps1, make-scene.ps1 (superseded), publish-client.mjs, survival-job.ps1, relay-window.ps1, and git.
Pending, tracked by the test: `set-lighting` and the light budget flags (`--max-lights --lighting-mode --exclude-types --light-radius-scale --light-intensity-scale --light-shadows --time-of-day --ambient --ambient-color --sun-strength --sun-color --render-scene-lights`) belong to the Lighting block being added in parallel; add their control ids to the manifest when it lands.
Still missing (no generator support, unchanged): per-building door on/off and storey height, road sidewalks.
Verified: node tests only (`test_command_parity.js`, `test_tools_jobs.js`, plus the existing objects / places / water job tests). Not verified in the real panel: DOM wiring of the Tools tab, the typed-name arming of Delete, the in-panel confirms, the results viewer layout, and any live Foundry call (nothing was pushed or deleted).

## Heightmap paint (2026-11)

| Feature | CLI | Panel control | Status |
|---|---|---|---|
| Paint strokes, undo/redo, save, discard, reset, stats, preview | `generators/heightmap_paint.py apply-strokes/export-preview/save/discard/reset/stats` | Terrain tab > Paint heightmap (collapsible section, was a separate Paint tab) | OK |
