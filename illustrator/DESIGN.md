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
