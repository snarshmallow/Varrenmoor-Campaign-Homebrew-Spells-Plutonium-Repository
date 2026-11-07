# 3D street exterior: materials, textures, skyboxes (2026-11-07)

Test pack: `world/bridgehollow__dyers_walk_local/export/` (25 hollow houses, 6 roads, kerbs, terrain strip). Renders: Blender 5.2 headless, `foundry-3d/blender/street_preview.py`.
Before/after (same cameras): `illustrator/out/3d_materials/compare_street.png`, `compare_aerial.png`, `compare_door.png` (full-size originals stay local in `before/`, `after/`, not committed).
New texture overview: `illustrator/out/3d_materials/texture_sheet.png`. Skyboxes: `illustrator/out/skybox/{clear_day,overcast,dusk,winter,night}_preview.png` + `sheet.png`;
street with skybox as Blender world: local only, `illustrator/out/3d_materials/sky/`.

## 1. UV scale and orientation (worldpack_mesh.py `world_uv`)
Old: wall UVs in the detailed builder used `(x + y) / tile` (wrong on any wall not at 45 degrees, stretched on diagonals), gables and roofs used plan coordinates `(l, w)`
(roof shingles were stretched by the pitch and the texture rows ignored the slope), the tile size was whatever the style table said (8 ft planks, 14 ft shingles).
New: one function gives every planar face constant texel density, **one image repeat = `tile_ft` feet on every face**:
* `u` runs along the horizontal direction of the face (plank/shingle/stone courses stay level, also on hip ends and gable triangles);
* `v` runs down the steepest slope of the face, in true slope length (roof rows advance by real length; thatch strands and board-and-batten run down the slope);
* walls take their texture origin at the floor (`v0 = floor z`), so the timber-frame rail sits on the floor line; gables use the same origin as the wall below them;
* near-horizontal faces use plan `(x, -y)`; each building gets a stable random offset (`uv_offset(id)`), so neighbours do not show the same board at the same spot.
Tile sizes now come from the material table (`worldpack_pbr.CATALOG`): clapboard 5 ft per repeat (about 7 in boards), stone 7 ft, plaster 6 ft, timber frame 10 ft (one storey),
roofs the style's tile x 0.65 (a course is about 0.6 ft instead of 0.9 ft). Tests: `test_worldpack_pbr.py::UVTests` (density, level courses, slope length, upright gables).

## 2. Surface types and PBR (new `worldpack_pbr.py`)
| Surface | Materials | Notes |
|---|---|---|
| Walls | `mat_plank` (horizontal clapboard), `mat_plaster` (whitewash, staining), `mat_wall_stone` (random-course rubble), `mat_wall_frame` (oak frame, diagonal brace, plaster panel), `mat_wall_batten` (vertical boards + battens) | picked per building by kind and seeded roll (`restyle_building`); winter styles keep `w_plank` |
| Roofs | shingle, thatch, slate, red tile, timber, winter variants (existing textures, unchanged art) | normal maps from the albedo, roughness 0.5 (slate/tile, with a roughness map) to 0.97 (thatch) |
| Doors, trim | `mat_door_wood` (boards, strap hinges, nails), `mat_trim` (worn paint) | the door leaf is now **one mesh with one material** (see Foundry below) |
| Glass | `mat_glass`: alpha 0.32, roughness 0.04, metallic 0.25 | blends; reflects the skybox through the environment map |
| Roads, kerbs | cobble (roughness 0.58 + metallicRoughness map: crevices rougher), `mat_kerb` (stone slab blocks, own material so the kerb is no longer the cobble texture) | |
| Ground | terrain albedo re-sampled to 4 px/ft with grass/soil/blade detail when the place is small (306 x 362 ft pack: 1224 x 1448 px); not done for big places (whole Bridgehollow stays at 0.5 px/ft, a 2400 ft map cannot carry ground detail in one 4096 texture) | |
| Water | alpha 0.82, roughness 0.06, normal map | |
Every textured material gets `<mat>_n.png` (tangent-space normal map, glTF +Y up) written next to `<mat>.png` in `models/textures/`; cobble, stone, slate, tile, kerb also `<mat>_mr.png` (G roughness, B metallic).
All PNG, 256 to 512 px (terrain 1224 x 1448), no extensions, no new attributes: gltfpack `quant` (KHR_mesh_quantization only) stays compatible; triangle counts are unchanged by the texture work
(wall/roof geometry is the same; the interiors agent's additions account for the rest of the triangle total).
How it plugs in: `worldpack.load_pack` calls `worldpack_pbr.prepare(materials)` (in memory only, `materials.json` on disk and `validate` are untouched); `worldpack_split.split_export` calls `worldpack_pbr.install(pack, models/textures)`;
`write_glb` writes `normalTexture` / `metallicRoughnessTexture` (external and embed modes); `merge` re-writes them from the same prepared records, no change needed.

## 3. What Foundry 3D Canvas honours (read from the installed module, `Data/modules/levels-3d-preview/scripts`, read-only)
* glTF materials are used as loaded by three.js (MeshStandardMaterial): base colour, **normal map, metallicRoughness map, roughness/metallic factors, alpha blend** are all kept. Per-tile flags `roughness` / `metalness` (default -0.01 = off) override the factors of every material in the tile; `transparency`, `alphaClip`, `sides`, `shading` exist too.
* Exception: tiles with the `ior` and `transmission` flags are converted to MeshPhysicalMaterial copying only map/colour/emissive/roughness/metalness: **do not set those flags on tiles whose normal maps matter**.
* Skybox: scene flag `exr` (any of .exr .jpg .png .webp, equirect) is loaded with PMREM: it is the **background and the image-based lighting/reflections** of the whole scene; `skybox` is the six-file cube alternative. Renderer uses ACES filmic tone mapping and the `exposure` flag (default 1).
* Doors: `setUpDoors` looks at `child.isMesh && child.userData.isDoor` and reads `child.material.transparent`: a door node with two materials becomes a Group of meshes and would not be seen as a door, so door leaves must have **one material**. Exterior leaves are one now (strap hinges are painted into the texture); the interiors module's inner doors still use `mat_door_wood` + `mat_iron` (their code, not changed here): worth making single-material as well.
* Not read in the module (so unknown): second UV set / detail maps (not used), vertex colours.

## 4. Skyboxes (new `generators/skybox.py`)
Format confirmed from the user's world: scenes use `flags.levels-3d-preview.exr` = 2:1 equirect (`assets/skybox_church.png` 1774 x 887, `assets/ossuary-exchange-skybox3.webp` 1774 x 887, canvas3dcompendium Beautiful-Sky 2K webp, violet star chart 4096 x 2048); 23 scenes have none.
`python illustrator/generators/skybox.py generate [--place bridgehollow] [--presets clear_day,overcast,dusk,winter,night] [--viewer X,Y] [--width 2048] [--yaw 0]`
writes `world/<place>/export/skybox/<preset>.webp` (+ preview png, `skybox_manifest.json`; 2048 x 1024, 40 to 65 KB each).
Mountains are the real terrain: per image column a ray runs across `world/bridgehollow/terrain/heightmap.npy` from the viewer (map centre, 6 ft eye height); the running maximum elevation angle is the true horizon
(here up to 25.3 degrees), and each pixel shows the first terrain sample above its angle, shaded by height/slope (meadow, conifer, rock, snow line, winter = snow everywhere), sun-lit and hazed.
Beyond the map rim, three procedural far ranges (ridged noise, never below 4 degrees, so the bowl stays closed) give the backdrop depth. Sky: gradient, sun/moon, fbm clouds, stars. Use `--viewer` for another vantage point (coordinates in the place's frame).
Set a scene (dry run unless `--apply`): `python illustrator/generators/skybox.py set-flag --scene-uuid Scene.xxx --preset clear_day [--scene-flag sunPosition=60] [--apply]`
copies the image to the versioned assets folder (`art/<place>/skybox/<preset>_vNNN.webp`) and sets `exr` (and clears `skybox`). Nothing was applied to Foundry.
Blender preview: `street_preview.py ... --sky <equirect>` uses the image as world (centre = Blender +X = east).

## 5. Untested in Foundry (TEST list)
1. Skybox azimuth: the image is written with centre = east and u growing clockwise from above (three.js equirect, scene x -> x, scene y -> z); if Foundry shows the mountains rotated or mirrored, use `--yaw` (and tell me which). Blender-verified only.
2. Normal/metallicRoughness maps on a real Foundry tile (expected from the code above) and the look of alpha-blended glass/water against the skybox reflections.
3. Brightness under ACES tone mapping + `exposure`; the skies were made for exposure 1.
4. Terrain GLB at 1224 x 1448 px with PMREM-lit scene (texture memory is small: about 7 MB RGBA).
5. Door leaf behaviour with the single-material leaf (still unverified from earlier work).
Not done: second-UV detail normal for the ground (the ground has baked colour detail only), roof underside/fascia, per-district colour variation of plaster, a real window-light emissive at night, texture compression.

## Files
New: `illustrator/generators/worldpack_pbr.py`, `skybox.py`, `test_worldpack_pbr.py` (10 tests). Changed: `worldpack_mesh.py` (world_uv, building/roof UVs, kerb material, glTF normal/MR, restyle/prepare hooks),
`worldpack_detail.py` (world UVs, single-material door leaf), `worldpack.py` (prepare hook in load_pack), `worldpack_split.py` (install hook), `foundry-3d/blender/street_preview.py` (`--sky`).
Tests run: `test_worldpack_pbr.py` OK, `test_worldpack_detail.py` OK, `test_worldio.py` OK; `test_worldpack.py`: 17 of 18 pass, `test_determinism` fails (compares the manifest file index with files on disk after the other agent's `refresh_manifest_files` started adding model GLBs to `manifest.files`; unrelated to materials).
