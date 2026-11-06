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
The generator takes `--view town|street:<id>|building:<id>` and crops/scales from the model.

## 3. Illustrator file structure (top to bottom)
Everything toggles from the Layers panel. Only the layers marked GEN are rewritten by the generator.
1. `NOTES` (GEN): design notes, "proposed" flags.
2. `LABELS` (GEN) with sublayers `Labels - Districts`, `Labels - Streets`, `Labels - Buildings`, `Labels - Rooms`. Text only, so one eye icon hides them all.
3. `ART - Top` (USER, empty): effects, lettering, props.
4. `ART - Fills` (USER, empty), `ART - Textures` (USER, empty), `ART - Masks` (USER, empty).
5. `LINES` (GEN) with sublayers `Walls`, `Buildings`, `Roads`, `Water`, `Terrain`, `Fences`. Each shape is a **closed path or compound path named by its entity id**, so it can be used directly as a clipping mask, Live Paint region or fill target.
6. `GUIDES` (GEN, locked): `Grid` (5/20/100 ft depending on view), `Scale bar`, `North arrow`, `Bounds`. Grid lines are real Illustrator guides where practical.
Rules: no unnamed objects; no open-path area outlines; strokes use named Graphic Styles (`guide-line`, `wall`, `proposed`, `road`, `water`) so the user can restyle everything from one place; Swatches named by purpose (`water`, `stone`, `timber`, `road`, `grass`).

## 4. Regeneration rule
The panel gets a `replace_layer` action: it clears and redraws only GEN layers, leaving ART layers untouched. User edits made to GEN layers are lost on regeneration; to keep a hand-edit, move it to an ART layer.

## 5. Prompt workflow
User says what they want ("add a tannery by the mill, 30x40 ft"); the model JSON is edited, then the generator and panel redraw. Questions about the layout are answered from the JSON, so understanding persists across sessions and between Claude sessions.

## 6. Foundry and 3D
`links.foundry_scene` and `links.model3d` are filled as scenes and models get made. A building's room polygons feed the 5 ft grid battle map and the 3D generators.

## Out of scope for now
Reading hand edits back from Illustrator into JSON (possible later through a panel `export_geometry` action).

## 7. Push to Foundry (from the Foundry bridge's answer, 2026-11-06)
- **Files:** Arcturus writes to `\VEGA\varrenmoor-3d` (Vega's `Data\assets\varrenmoor-3d`), seen by Foundry as `assets/varrenmoor-3d/...`. Layout: `art/<worldId>/<layer>_v<NNN>.webp`. Bump the version number on every push, because Foundry and browsers cache by path.
- **Export size:** export at the target scene's `grid.size` px per 5 ft so one inch = one grid square. Read `grid.size` from the scene first. Keep sides at or under 8192 px (tiles nearer 4096). Use WebP or PNG; Foundry rasterises SVG at native size. Allow for scene padding (use sceneX/sceneY).
- **RPCs today:** list, get, create, update (any document by uuid; scene background or Tile `texture.src` can be set now). No delete, Drawing is not on the create list. Changes reach all clients live; no refresh needed. Writes need the world setting "Allow writes" on.
- **To add (Foundry bridge):** Drawing in create; `find_by_flag`; `upsert_by_flag` (Tile or Drawing keyed by `flags.varrenmoor.layerId`); delete restricted to pipeline-flagged documents; bulk walls from line art.
- **Mapping:** stored in Foundry as `scene.flags.varrenmoor.worldId` and `tile.flags.varrenmoor.layerId`. Foundry is the source of truth; `links.foundry_scene` in the model is an optional mirror.
- **Tile coordinates:** 2D tiles use top-left x,y; 3D Canvas tiles use the centre. One GM client connects at a time.
- **Panel actions to add:** `export_view` (layer set + px per ft, writes the versioned WebP/PNG to the share) and `push_scene` (writes a job for the Foundry bridge). On-save auto push comes last, after confirming the panel can hear Illustrator's save event.
