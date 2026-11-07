# Illustrator + world model design

## Goal
One persistent spatial model of the world (town > district > street > building > room) that drives line-art guides in Illustrator, 3D assets and Foundry scenes, at any scale. The user draws and styles over the guides in their own layers; regenerating guides never touches the user's art.

## 1. Source of truth: `world/` JSON in the repo
- One coordinate system per place, in **feet**, origin top-left of the place, y down.
- Hierarchy of files: `world/<place>/place.json` (bounds, scale presets), `districts.json`, `streets.json`, `water.json`, `buildings/<id>.json` (footprint polygon, floors, rooms with polygons, doors), later `terrain.json`.
- Every entity has: `id` (stable snake_case, e.g. `bld_warden_hall`), `name`, `kind`, `status` (`canon` | `proposed`), `geometry` (closed polygons for areas, polylines with a `width_ft` for roads), `notes`, and `links` (`foundry_scene`, `model3d`, `ai_layer`).
- The same ids are used by the 3D generators and Foundry scenes, so a building is one thing everywhere.
- `status: proposed` items are drawn with a distinct stroke style and tagged in labels. Canon comes only from the user.

## 2. Scales (same model, different views)
| View | Scale | Page | Use |
|---|---|---|---|
| Town | 1 in = 100 ft | 17x11 | whole settlement |
| Street / block | 1 in = 20 ft | 17x11 | one street |
| Building / room | 1 in = 5 ft (one Foundry square) | 17x11 or larger | floorplans, battle maps |
The generator takes `--view town|bowl|street:<id>|building:<id>` and crops/scales from the model. Presets, grid and page size live in `world/<place>/view_settings.json` (including a `bowl` preset, 1 in = 200 ft, for the whole place) and can be overridden with `--scale/--grid/--page`.

## 3. Illustrator file structure (top to bottom)
Everything toggles from the Layers panel. Only the layers marked GEN are rewritten by the generator.
1. `NOTES` (GEN): design notes, "proposed" flags.
2. `LABELS` (GEN) with sublayers `Labels - Districts`, `Labels - Streets`, `Labels - Buildings`, `Labels - Rooms`, `Labels - Elevation`, `Leaders` and `Label Backing` (halo copies / boxes, toggleable). Text and its backing only, so one eye icon hides them all.
3. `ART - Top` (USER, empty): effects, lettering, props.
4. `ART - Fills` (USER, empty), `ART - Textures` (USER, empty), `ART - Masks` (USER, empty).
5. `LINES` (GEN) with sublayers `Walls`, `Buildings`, `Roads`, `Water`, `Terrain`, `Fences`. Each shape is a **closed path or compound path named by its entity id**, so it can be used directly as a clipping mask, Live Paint region or fill target.
6. `GUIDES` (GEN, locked): `Grid` (5/20/100 ft depending on view), `Scale bar`, `North arrow`, `Bounds`. Grid lines are real Illustrator guides where practical.
Rules: no unnamed objects; no open-path area outlines; strokes use named Graphic Styles (`guide-line`, `wall`, `proposed`, `road`, `water`) so the user can restyle everything from one place (graphic styles come from a seeded template, see section 8); Swatches named by purpose (`water`, `stone`, `timber`, `road`, `grass`).

## 4. Regeneration rule
The panel gets a `replace_layer` action: it clears and redraws only GEN layers, leaving ART layers untouched. User edits made to GEN layers are lost on regeneration; to keep a hand-edit, move it to an ART layer.

## 5. Prompt workflow
User says what they want ("add a tannery by the mill, 30x40 ft"); the model JSON is edited, then the generator and panel redraw. Questions about the layout are answered from the JSON, so understanding persists across sessions and between Claude sessions.

## 6. Foundry and 3D
`links.foundry_scene` and `links.model3d` are filled as scenes and models get made. A building's room polygons feed the 5 ft grid battle map and the 3D generators.

## Out of scope for now
Reading hand edits back from Illustrator into JSON (possible later through a panel `export_geometry` action).

## 7. Push to Foundry (built 2026-11-07)
All Foundry reads and writes run in `generators/foundry_push.py` (the panel just spawns it) through `foundry-bridge/bridge.ps1`. The module side only has generic, flag-keyed primitives (module 0.3.0, `foundry-bridge/DEPLOY_MODULE.md`).
- **Pipeline flag:** every document we create carries `flags.varrenmoor.pipelineId` (stable string: `scene:<place>:<name slug>`, `wall:<building>:<n>`, `draw:road:<id>`, `tile:<layer>`, `token:<actor>:<where>`, `npc:<place>:<slug>`, `item:<place>:<slug>`). Re-push = upsert by that id, so the same scene updates in place; stale pipeline walls and drawings are pruned; documents without the flag are never updated by upserts, never pruned and never deleted (the module enforces this). Scenes also store `flags.varrenmoor.worldId` and `.calib` (x0, y0, px per ft, grid px, size) so tokens can be placed from world-model feet later.
- **Files:** copied to `\\VEGA\varrenmoor-3d\art\<place>\scene_<name>_vNNN.webp` (seen by Foundry as `assets/varrenmoor-3d/art/...`; share from `foundry-3d/.env` `FOUNDRY_ASSETS_DIR`). Each push takes the next version number, but a byte-identical image reuses the newest version (no clutter). Token and portrait art goes to `art/<place>/actors/`, item art to `art/<place>/items/`.
- **Calibration:** the panel `export_view` host action exports the whole artboard at N dpi (px per ft = dpi / scale_ft_per_in). The tool crops to the map window (page minus margin, from `render_world.compute_view`), downsizes only if over `--max-px` (8192), and sets `grid.size` = px per ft x grid_ft with `grid.distance` = grid_ft (default the view grid; `--ft-per-grid` overrides). Scene padding is 0 by default (sceneX/sceneY offsets are applied if `--padding` is used). Foundry's minimum grid size is 50 px: the tool errors with advice when the dpi is too low for the grid.
- **Walls:** one per building edge (and per room polygon edge when rooms carry geometry), clipped to the window. Doors are not generated yet. Optional Drawings: roads (street outlines) and water polygons.
- **Targets:** a new scene (name field; refuses a name that matches a scene we did not make) or an existing scene from the picker. For an existing scene without our flag the panel shows what will change (background, grid, size) and needs a confirm; walls, drawings and tiles made by hand are untouched. v14 note: the background lives on the scene Level (`levels[].background.src`), handled by `set_scene_background`.
- **Actors, items, tokens:** `push-actor --spec npc.json` builds a dnd5e NPC with the existing `foundry-tools/vtt/npc.py build_actor` and upserts it flagged; `--actor-uuid` + `--image` updates portrait and prototype token art of an existing actor (confirm first). `push-item` does the same for items (`vtt/item.py build_item_doc`, no 3D model). `push-token` places an actor token on a pipeline scene at a building, street or water id centroid, or at `x,y` feet (default 5 ft wide).
- **Panel (Foundry tab):** place picker, scene/actor/item pickers (lists read from Foundry and cached in panel_state `foundry.cache`; works offline with a stale warning), new-or-existing target, dpi, feet per grid, walls/drawings/overlay-tile options, Export view, Push scene, Push tiles (scene plus a transparent overlay tile of the chosen layers, default the label layers), status line and log. **Auto-push on save** is opt-in: CEP has no dependable Illustrator save event, so the panel polls the open document file time every 3 s and pushes 6 s after it stops changing; it turns itself off if the target needs a manual confirm.
- **Degrades:** until the Vega module is 0.3.0, push actions stop with "module older than 0.3.0" (the `version` op is missing); status, list and export still work.
- **Not done:** 3D model tiles (convention: `foundry-3d/make-scene.ps1` and `vtt/scene.py`, Levels 3D Preview flags), doors, lights, notes, per-layer tiles other than the single overlay tile.

## 8. Symbols, scatter, brushes and styles (what scripting can and cannot do)
- **Can:** create symbols (`doc.symbols.add`), place symbol instances, create swatches, apply existing brushes and styles by name.
- **Cannot:** create new brushes, graphic styles or pattern swatches from a script.
- **Symbols from prompts:** assets are generated as vector code (seeded variants, e.g. oak_a/b/c, pine_dead) into `world/assets/<library>.json` plus an SVG per variant. Panel action `define_symbol` imports each SVG as a named symbol.
- **Scatter:** panel action `scatter` places instances of named symbols in a polygon (area id from the model) with density, min spacing, random scale/rotation and a fixed seed. Instances go on a GEN layer (`LINES/Vegetation`), never an ART layer. Each placement list is saved to `world/<place>/scatter/<area>.json` so 3D generators and Foundry can use the same positions.
- **Brushes:** brush artwork is generated as vector shapes in a `BRUSH ARTWORK` document. The user drags each into the Brushes panel once and picks the brush type; a numbered checklist is written next to the artwork. After that, strokes can be assigned by brush name.
- **Styles:** a template file `illustrator/templates/varrenmoor.ait` carries the graphic styles and base swatches; new documents are created from it.
- **Not used:** Illustrator's own random scatter brushes cannot be set from a script; our `scatter` action replaces them and is reproducible.
