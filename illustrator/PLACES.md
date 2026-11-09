# Places: pushing to Foundry, importing scenes, creating new places

For the DM. A **place** is a folder `world/<id>/` (terrain, rivers, streets, districts, buildings). Every tool (maps, shading, 3D export, Foundry push)
works on whichever place is selected in the panel (or `--place <id>` on the command line).

## 1. How the push to Foundry works

Everything goes through `illustrator/generators/foundry_push.py` and the bridge (`foundry-bridge/`, relay on this PC, Foundry GM tab open, world setting
"Allow writes" on). The panel's Foundry tab only starts this tool.

**Scene (the 2D map).** Export the current view from Illustrator, then *Push scene*. It creates (or updates) a scene with the map as background,
the grid set so one square = the view's grid feet, walls built from building outlines (optionally road / water drawings and an overlay tile of label layers).
The scene is stamped with a hidden flag (`flags.varrenmoor.pipelineId`) and a calibration block (feet <-> pixels).

**New or existing scene.**
- *New scene*: give a name. The first push creates it; a second push with the same name finds it by the flag and **updates it in place** (no duplicate).
  If a scene with that name already exists but was not made by the pipeline, the push refuses and tells you to pick it as an existing scene.
- *Existing scene*: pick it in the list (Refresh from Foundry first). Scenes the pipeline made are updated silently. A scene you made yourself is only
  touched after you confirm once; only the background, grid, and pipeline-flagged walls / drawings change. Your own walls, lights, tokens and notes on it are never deleted.
- A place imported from a scene (section 2) remembers it: *Push scene* with no name goes back to that scene.

**Everything else uses the same flag rule** (update, never duplicate; delete only touches flagged documents):
- *Tokens, actors, items*: `push-actor`, `push-item`, `push-token` create or update by key; tokens are placed at a building id or x,y feet.
- *3D models*: world pack export -> split / merge -> *Push models* = one 3D Canvas tile per model (terrain, buildings, roads ...) on the scene.
- *Padding and skybox*: the Padding tab publishes a heightmap, table tile and apron mesh so the 3D scene has surroundings beyond the map; `skybox.py` makes
  a horizon image from the real terrain and sets it as a scene flag (dry run unless `--apply`). Snow and tree lines follow the place's own relief.
- *Lights*: `push-lights` creates ambient lights from the lighting tab.

## 2. Selecting and importing existing Foundry scenes

Foundry tab -> *Refresh from Foundry* lists scenes, actors, items. Pick a scene in **Existing scene** to push to it.

To turn a scene into a place (read-only on Foundry, nothing is written there): Places tab -> *Import a Foundry scene as a place* (or the *Import scene as place*
button in the Foundry tab), or `python illustrator/generators/foundry_push.py import-scene --scene-uuid Scene.xxxx [--place-id id] [--include walls,lights,tokens,notes]`.
You get `world/<id>/` with:
- the scale from the scene grid (pixels per foot = grid size / grid distance; metres, km, miles are converted);
- the background image copied (shared assets folder) or downloaded into `underlay/` as a PNG, to be placed locked below the line art;
- Foundry walls as lines on a WALLS layer; closed loops of walls stay plain wall outlines (choose "label rooms" for labelled `Imported room N` building outlines); lights are yellow dots and tokens blue dots on the locked layer FOUNDRY MARKERS (set `import.light_rings` true in place.json for a dashed bright-radius ring); the 5 ft grid sits above the underlay and below lines/labels; no background and no terrain = flat sheet (no shading PNG);
- optional lights, tokens and notes as feet coordinates;
- `links.foundry_scene` = the scene, so later pushes return to it.
Limits: no terrain (a flat stub is written), no streets or water; walls are only as good as the scene's walls.
`--dry-run` shows what would be made; use `--force` to overwrite.

### 2b. Importing a plain base map image (no Foundry)

Places tab -> *Import base map image* (image file / *Browse image*, place name, place id, *Feet per pixel*, optional *Rotate* and *Guide grid (ft)*; *Check image import (dry run)*, then *Import base map image*), or
`python illustrator/generators/place_create.py import-image IMAGE --name "My base" --id my_base --ft-per-px 4.669 [--rotate DEG] [--grid-ft 100] [--dry-run] [--force]`
(code: `foundry_import.import_image`, which feeds a synthetic one-image scene through the same importer as 2, so the result is laid out the same way). You get `world/<id>/` with:
- `place.json` kind `basemap`, `bounds` = image pixels x feet per pixel, `import.source` = `image`, `import.ft_per_px`, `import.px_per_ft`, `links.foundry_scene` = null;
- the image as `underlay/background.png` (plus `underlay/original_<name>`), placed locked on the layer UNDERLAY by *Open selected in Illustrator* / `place_render.py --job` exactly like a scene background;
- a flat terrain stub (`terrain/`, height 0, `pipeline: flat_stub`; contours are skipped for it), empty `streets.json`, `districts.json`, `water.json`, `buildings/`, and `view_settings.json` whose town view covers the whole image (guide grid = *Guide grid*, default 100 ft).
Orientation: origin = the image's top-left corner, x right, y down, **up in the picture = north**, feet; place (x, y) ft = image pixel (x, y) x feet per pixel (after the optional rotation, which grows the canvas). It refuses to overwrite an existing folder without `--force`. Nothing else is generated: trace roads and rivers yourself (PLUGIN_GUIDE.md, chapter "make a map from a 2D base map"). Oblique pictures must be rectified first (`generators/rectify_map.py`, PLUGIN_GUIDE.md 2.24).
Example: `varrenmoor_base` = `illustrator/out/varrenmoor_overhead_map.png` at 4.6689 ft per pixel (2400 x 3428 px = 11205 x 16005 ft).

## 3. Creating a new place

**From scratch (empty).** *Blank place (from scratch)*: section 3b. **Tiny (under 20 people)**: section 3a.

**From the Places tab (form).** Pick a template (coastal fishing village, river market town, mountain pass fort-town, walled hill town, farming hamlet;
tiny: lone farmstead, hunter's cabin, roadside inn, hamlet of 12) or fill in: name, culture (names and building looks), population, layout, terrain, rivers, lakes, climate, season. The line under the form estimates buildings and
area. **Draft quality** (default on) makes coarse terrain and civic buildings only, in seconds, and is safe to open. Full quality adds every house.
The size caps (about 1200 buildings, 3 million ft2 of town, 9000 ft place) stop a huge town freezing Illustrator; *Allow large* lifts them.
*Generate place* writes `world/<id>/`, switches to it and renders a preview PNG. *Open selected in Illustrator* writes a job that opens the map as a new document.

**From plain words.** Type e.g. `walled coastal town of 800 people with a big river, Danish style, hilly` and press *Fill form from words*.
This is a keyword table, not understanding: it finds known words (terrain, layout, size words, culture, river, lake, season) and ignores the rest, telling you which words
were ignored. Where two terrain words appear the first in this order wins: island, fjord, pass, coastal, mountain, bowl, valley, hills, rolling, flat.
Vocabulary: top of `place_text.py`.

**From a description given to Claude.** Ask Claude for a place in ordinary language. Claude reads `python illustrator/generators/place_create.py prompt-help`
(schema, vocabulary, templates), writes a spec JSON, checks it with `place_create.py validate spec.json`, and you paste it into *Paste a spec* (or run
`place_create.py create spec.json`). This route handles subtle requests (named districts, custom civic buildings, per-kind building styles).

**From a Foundry scene**: section 2.

Command line: `place_create.py create|create-blank|validate|prompt-help|from-text|templates|regen|import-image|write-schema`; schema `world/schema/place-spec.schema.json`.
Same spec + seed = same place. `create` refuses to overwrite an existing folder without `--force`. An empty spec `{}` is accepted: a name is generated.

### 3a. Tiny settlements (fewer than 20 people)
`town.population` 0 to 19 does not use the town generator; `generators/town_tiny.py` writes the same files (streets, districts, buildings, fields) for:

| `town.settlement` | People (auto) | What you get | Default size |
|---|---|---|---|
| `farmstead` | 1-5 | farmhouse, barn, shed (3+), byre (5+), well, yard, 2-3 fenced fields, a farm track from the map edge | 600 x 450 ft |
| `hamlet` | 6-19 | 2-4 houses and 1-2 barns round a yard / green with a well on a lane, 3-4 fields (2-6 buildings) | 800 x 600 ft |
| `cabin` | (choose) | hunter's / woodcutter's cabin and a woodshed on a footpath, no fields | 400 x 300 ft |
| `lodge` | (choose) | hunter's lodge, stable, woodshed, small yard | 500 x 400 ft |
| `inn` | (choose) | roadside inn, stables, shed, well, inn yard beside a road that crosses the whole map, one paddock | 600 x 450 ft |

`town.population: 0` = no settlement: terrain and water only. Rivers default to 0 for tiny places (ask for one with `terrain.rivers`). No market, plaza,
districts rings, walls or gates (layout, wall, gates, districts and central feature are ignored, with a warning). Templates: `lone_farmstead`, `hunters_cabin`,
`roadside_inn`, `hamlet_of_12`. Words: "a lone farmstead", "homestead", "a single house", "lone cabin", "hunter's lodge", "roadside inn", "hamlet of 12",
"a family of five", "no town" (a town / village / city word wins over these). Fields get fences in the 3D pack; a track over a river becomes a ford.
Limits: a fixed plan per kind; a building or field with no dry, level spot near the yard is skipped (listed in `create_report.json` town warnings); the
ground under buildings is not levelled; the well is a 7 ft well house.

### 3b. Blank place (from scratch)
`place_create.py create-blank --name N [--id ID] --size-ft W H --recipe flat|rolling_hills|valley|highland_ridge [--relief-ft R] [--cell-ft F] [--seed S]
[--scale-ft-per-in F] [--grid-ft G] [--underlay IMAGE] [--force] [--dry-run]` (panel: Places tab > *Blank place (from scratch)*). Writes `world/<id>/` of kind
`blank`: the terrain (flat at 100 ft, or the base-terrain generator `terrain_basemap.py`), `terrain_spec.json`, empty `streets.json`, `districts.json`,
`water.json` and `buildings/`, `view_settings.json` (town view = the whole place unless a scale is given) and `place.json`. An underlay image is stretched over
the whole place as the locked UNDERLAY layer. Then draw roads (Roads tab), add buildings (Buildings tools), paint terrain (Heightmap paint), add water (Water tab).
Preview, Open in Illustrator and the 3D world-pack export work on it with 0 buildings and 0 streets.

### 3c. Managing places (rename, duplicate, trash, edit)
`place_manage.py` (panel: Places tab > *Manage the selected place*):
`edit --place ID [--name] [--notes] [--kind] [--status] [--culture] [--season] [--units] [--focus X Y] [--scale-ft-per-in F] [--grid-ft G]`,
`rename --place OLD --new-id NEW [--include-export]`, `duplicate --place ID --new-id NEW [--name N] [--include-export]`, `trash --place ID`, `trash-list`,
`restore --entry E [--as NEW]`, `purge --entry E --confirm ID`, `check-id --id X`; every changing command takes `--dry-run`.
- Ids: lower-case letters, digits, underscore, 2-41 characters; not `schema`, `export`, `trash`, `world`, `panel`, `places` or a Windows device name; unique.
- Rename renames the folder and rewrites references (place.json id, `place` / `place_id` / `parent` fields and `world/<id>/` paths in the place's JSON files,
  region children's parent, `world/panel_last_place.json`, `illustrator/out/{panel,water,foundry,heightmap_paint}/<id>`, `illustrator/out/places/<id>_*`,
  `illustrator/out/<id>_*`). Not changed: `export/` (unless `--include-export`), the linked Foundry scene, the Foundry asset folder `art/<id>/`, region child
  folder names, entity ids. On any failure every finished step is undone in reverse order.
- Trash moves the folder to `world/.trash/<id>_<date-time>/` (git-ignored); restore moves it back; purge deletes a trash entry only, after the id is typed.
- The place open in the panel is refused for rename and trash (switch first). Foundry is never contacted.

### What a spec controls
Terrain recipes: flat, rolling, hills, valley, bowl, coastal, island, pass, fjord, mountain (relief, sea side, rivers 0-3 with bends and width, up to 4 lakes).
Town: population (0 = none, 1-19 = tiny settlement (3a), hamlet < 150 < village < 450 < town < 2500 < city), layout (organic, radial, grid, linear, walled), districts (names or automatic), centre feature
(market, green, temple, castle), wall and gates, extra civic buildings. Culture sets names and default building styles. Climate and season choose the shading preset.

### Honest limits
- Layouts are bias settings on one street generator; a "grid" town is grid-leaning, not a ruled lattice.
- On a narrow pass floor or a very steep place the market square can fail to fit (no square is drawn); the town still generates.
- The town wall appears in the 2D map and `walls.json`, not in the 3D export.
- Very large towns are slow and heavy on memory; Illustrator may take minutes to open their SVG. Start in draft.
- Generated places are "proposed" drafts; edit them like Bridgehollow (Town tab, terrain patches, regions).

## Varrenmoor ground palette (map colours)

The campaign map's open ground averages RGB (90,79,55) and its canopy (50,46,33): dark olive and brown, not bright green. `generators/make_moor_textures.py` recolours the stock grass / meadow / pasture / crop / wheat / tilled / farmland / forest-floor tiles to those means (presets/textures/moor_*.png). The town style `varrenmoor` (plazas, fields, field border), the terrain phase file `presets/terrain_phases/varrenmoor_moor.json` (the shading of world/varrenmoor and world/varrenmoor__town_center) and the padding texture preset `varrenmoor_moor` use them; every other place and style keeps the stock tiles unless it opts in. Re-run the fills/terrain export of the place to see it.
