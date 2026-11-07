# Foundry 3D Canvas (levels-3d-preview): how it renders our pushes

Written 2026-11-07. Evidence labels: **[doc]** = official wiki (github.com/theripper93/canvas3dcompendium/wiki, pages Scene-Configuration, Tiles, Tokens, Walls, Supported-File-Formats), **[live]** = read through the bridge from the running world (scenes `Ossuary Market` Scene.q8ifAtUP2duXgbfY and `ZZ Tile Rotation Inspect` Scene.LqW1Tts9ap2qTvQl), **[repo]** = earlier notes/tests in this repo, **[infer]** = reasoned, **[TEST]** = must be checked in the live world. The module source itself and wiki.theripper93.com could not be fetched from here (rate limited / not public), so flag names beyond the live dump are not confirmed against source.

## 1. Scene flags (flags.levels-3d-preview)

Live dump of both working scenes (identical): `auto3d true, object3dSight true, enablePlayers true, exr "assets/ossuary-exchange-skybox3.webp", skybox "", renderBackground false, exposure 1, enableGameCamera true, enableFogOfWar true, grounding "", maxElevation 100000, enableRuler true, enableAnimationScripts true, renderTable "matcustom", tableTex "baileywiki-content/assets/modules/baileywiki-3d/models/black-tone-pure.webp", tableHeightmap "", tableHeightmapScale 1, tableColor "#341f0f", enableFog false, fogDistance 3000, sceneTint "#ffffff", timeSync "darkness", sunPosition 9, sunDistance 10, sunTilt 0, ambientLightIntensity 0, shadowBias -1.8e-05, showSceneWalls true, showSceneDoors true, showSceneFloors true, renderSceneLights true, mirrorLevels true, pp.enabled false, bloom false` [live].

Mapping to UI labels [doc]: `auto3d` = "Enable 3D on Load" (scene opens in 3D mode); `enablePlayers` = "Enable for Players"; `renderBackground` = "Display Background" (scene background image shown "as a flat surface"); `renderTable` + `tableTex`/`tableColor` = "Display Table" / "Table Texture" ("the table will be the size of the padding"); `exr` = HDRI (background when no skybox; lighting/reflections when a skybox is set); `skybox` = six-file cube map; `showSceneWalls/Doors/Floors`, `renderSceneLights` = "Render Walls / Doors / Tiles / Scene Lights"; `object3dSight` = "Use 3D Geometry for sight calculations"; `mirrorLevels` = "Mirror Levels Tile Visibility"; `sunPosition` 0 dawn .. 180 dusk, `timeSync` automatic sun from world time or darkness. `enable3d`, `grounding`, `maxElevation`, heightmap keys: names seen live; their semantics are not on the wiki page [infer: heightmap scale/`tableHeightmap` reshape the table; `maxElevation` caps token/tile elevation].

**Important [doc]:** "Turning on 3D will not make any changes to your original 2D Scene". 3D is a *view* toggled by the "Toggle 3D Mode" button under Token Controls; every scene can be viewed in 3D. A scene created without any levels-3d-preview flags has module defaults (`auto3d` off, so it opens 2D), but its 3D view still works if toggled. In 2D mode a model tile is only its placeholder 2D texture, which is why the white squares appeared: our tiles use `texture.src = modules/levels-3d-preview/assets/blank.webp` (a white image) with the model in `flags...model3d` [live, repo]. The wiki says exactly this: "the tile gets a placeholder 2D image, which Levels needs for visibility". So white squares in 2D are expected and not a bug; the cure for a clean 2D view is to not show model tiles in a flat scene [infer: also set tile `hidden`/`alpha 0` or keep model tiles only in the 3D scene].

Scene-level 3D defaults / "scene defaults": a new scene copies **no** 3D flags unless a template does; module-wide settings (graphics quality) are per-user client settings [doc]. If the user's world has a default scene template or a "Scene defaults" module that injects `auto3d: true`, the 2D map scene would open in 3D [TEST: create a scene with the bridge and read flags back].

## 2. What renders in 3D mode

| Element | In 3D view | Basis |
|---|---|---|
| Scene background image | Only with `renderBackground` true ("Display Background"), drawn as a flat plane at ground level. With it false the ground is the table (or nothing/skybox). Both can be on; the table is sized by `padding`. | [doc] |
| Table | Optional textured ground plane sized to the padding; `renderTable` values seen: `matcustom` (custom texture + `tableColor`). Heightmap table via `tableHeightmap` + `tableHeightmapScale` | [live], [doc] |
| 3D tiles (`model3d`) | Rendered as models: tile width/height = model X/Y footprint (fill type Fit/Stretch/Repeat), `depth` = Z, `elevation` in grid units/ft, `autoGround` drops it to the ground below, `autoCenter` re-centres the model | [doc]+[repo] |
| 2D image tiles | Rendered as flat planes at the level's bottom elevation (the wiki: "2D tiles sit at the bottom elevation set through Levels"). Background-type tiles render but the author says they flicker/pop when overlapping the background; prefer one background image or merge them (DF Architect) | [doc] |
| Drawings | **Not documented anywhere** in the wiki pages read. Our `Drawing` documents (road/water polygons, text labels) are 2D PIXI objects; assume they are **not** drawn in the 3D view [infer; TEST] | none |
| Walls | Rendered as 3D slabs if `showSceneWalls`; height from Wall Height top/bottom, thickness in the wall's 3D tab; our auto walls will show as thin untextured boxes (set `showSceneWalls false` on a map scene whose walls are only for vision) | [doc] |
| Lights | `renderSceneLights` shows Foundry ambient lights as 3D point lights (shadows are costly; per-light toggle) | [doc] |
| Grid | `Enable Grid` shows the grid on the 3D table/ground ("Show the grid in the 3D Scene") | [doc] |
| Tokens | A 3D model if set, else the token texture as a flat standing 2D figure ("standup"); `Scale` sets model size independent of grid size (not documented how) | [doc] |
| Templates | Measured templates have a 3D version (wiki page Measured-Templates, not read) | [infer] |
| Notes, regions | Not documented [TEST] | |

## 3. What our 2D details do in 3D, and workarounds

* **Drawings (roads, water, labels)**: likely invisible in 3D. Workarounds, best first: (1) bake roads/water/labels into the 2D background/table texture (our Illustrator export already is the full map image); (2) put them in the terrain/roads/water GLBs (world pack has roads.glb, water.glb with 3D geometry); (3) keep Drawings for the flat 2D scene only. [infer]
* **Background image**: in a 3D scene set `renderBackground: true` *only* if no terrain GLB tile covers the ground; the plane is flat at elevation 0 and would z-fight with a terrain GLB at the same height (see feedback on coplanar overlaps). With a terrain tile, use `renderBackground false`, and either bake shading into the terrain GLB's texture or use the shaded map as `tableTex`.
* **Table**: `tableTex` is a *tiled* texture path (the live value is a repeating black tone from the baileywiki module, not the map). A one-off full-map table texture needs scaling checks [TEST]. Heightmap table: black = high, white = low [doc, Tiles heightmap]; needs `tableHeightmap` path and scale [infer].
* **White placeholder squares**: expected in 2D mode (blank.webp). Leave as is on 3D scenes; do not push model tiles into the flat map scene.
* **Z-fighting**: roads/overlays on top of terrain need a real vertical gap (>= 0.05 m at map scale), not coplanar.
* **Second 2D scene variant** is the simplest reliable way to keep the flat Illustrator map with drawings and walls; `--scene-mode flat` below.

## 4. Scale, camera, tile conventions

* Scene px vs 3D size: the 3D world uses grid units, `grid.size` px = one square = `grid.distance` ft. Repo convention: 100 px = 1.524 m (5 ft = 20 px/ft) [repo]; pushes at other ppf scale tile sizes by `ppf` so models keep true size (`build_model_tiles`). Scene `padding` enlarges the table beyond the scene rect; the 3D camera is free, so padding only affects table extent and camera bounds [doc/infer].
* Tile `x,y` is the model **centre** in scene px (footprint centre; `autoCenter false` because the pack pivot is the footprint centre; vertical origin at the model base, `autoGround true` lifts to the surface below) [repo, live: the L marker tile at 1000,800 is 591 px wide]. `width` = model X, `height` = model Y, `depth` flag = model Z, all px.
* Rotation: `foundry-3d/README.md` says rotation 0 shows the model turned 180 from plan view (use 180); `make-scene.ps1`/`item.py`/the pack manifest say 0. Unresolved: the inspect scene (4 tiles at 0/90/180/270 with a coloured L marker, RED = model +Y) was pushed and its flags now match; read RED on screen [TEST]. Until then keep `tile_rotation_deg 0` (manifest) as is.
* Terrain mesh from the world pack: a GLB tile centred on the scene (terrain.glb footprint = full map), `elevation 0`, `autoGround false` (nothing below it to snap to; true would drop it onto the table, usually the same result), `autoCenter false`, `collision true`/`sight true` only if tokens must walk on it. Heightmap table is the alternative for a *cheap* relief (one texture), but tokens and tiles then use `autoGround` against that relief; the GLB gives exact baked heights, roads cut and shaded textures [infer].
* Supported model formats: GLB, glTF, FBX [doc]. Draco yes; meshopt/KTX2 probably not (see WORLD_PACK.md).

## 5. Recommended push strategy

(a) **Flat 2D map scene** (`foundry_push.py push-scene ... --scene-mode flat`, the default for new scenes): `auto3d false, enablePlayers false, renderBackground false`; background image, calibrated grid, walls, Drawings (roads/water) as today. No model tiles. The 3D toggle still exists but the scene opens flat and nothing is changed by toggling.

(b) **3D scene** (`push-models ... --scene-mode 3d`, default for push-models): flags = the live template (`auto3d true, enablePlayers true, renderBackground false, renderTable matcustom + tableTex/tableColor, exr, showSceneWalls/Doors/Floors true, renderSceneLights true, mirrorLevels true, sunPosition 9, ambientLightIntensity 0, maxElevation 100000`, plus `object3dSight, enableGameCamera, enableFogOfWar, enableRuler`). Contents: terrain GLB tile + building GLB tiles; shading baked into the terrain texture; pass `--scene-flag renderBackground=true` only for a 2D-texture-only ground. Override any value with `--scene-flag key=json` (repeatable). Note `tableTex` and `exr` point to assets that live in the user's world (baileywiki module, assets folder); on another world override them.

Existing scenes are only re-flagged when `--scene-mode` is passed explicitly, so hand tuning is never overwritten silently.

## 6. To test live (priority order)
1. Does a Drawing (road polygon) show in 3D view of `ZZ Tile Rotation Inspect` (it has 7 text drawings)? Which labels are visible?
2. Rotation: with the four L markers, which rotation puts RED (north) toward screen-up in the 3D top-down view and in the 2D map? Update `foundry-3d/README.md`/manifest accordingly.
3. Create a scene via `push-scene` (flat) and read `flags.levels-3d-preview` back: confirm `auto3d false` sticks and no world/default template turns 3D on.
4. Background plane vs terrain GLB: toggle `renderBackground` on a scene with terrain.glb at elevation 0 to see z-fighting; try terrain `autoGround false`.
5. A full-map image as `tableTex`: is it tiled or stretched over the padded table, and is the scale equal to scene size?
6. Wall rendering of auto-generated building walls in 3D (set `showSceneWalls false` if ugly or if buildings are GLB tiles).
7. Do compressed GLBs (quant, meshopt) load (see WORLD_PACK.md check).
