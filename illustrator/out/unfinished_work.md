# Unfinished work and live tests (2026-11-08)

Everything below needs a live Illustrator or Foundry session. Nothing here was checked live by the offline agents. Rules for the tester: never put credentials in notes; the Foundry GM tab must be signed in by you.

## A. Needs a live test (exact steps)

### 1. Push scene (2D flat and 3D)
1. Open Foundry as GM (signed in) and the Illustrator panel (Foundry tab).
2. Panel: choose place `bridgehollow__dyers_walk_local`, mode 3d, click "Push scene". Alternatively run `foundry_push.py push-scene-3d --place bridgehollow__dyers_walk_local --scene-name "ZZ Dyers Walk 3D Test"`.
3. Expect: scene `ZZ Dyers Walk 3D Test` updates, roads continuous, sky and table texture present. If sky or table texture is missing run `padding_heightmap.py push ...` then `skybox.py set-flag ... --apply` (push-models resets them).
4. Pass = no black table edge, no missing tiles, console clean. Report the failing step.

### 2. Export view
1. Panel, Render/Export tab, pick a view preset, click "Export view".
2. Expect a PNG/SVG in `illustrator/out/` with the framing of the preset (nice scale, grid).
3. Pass = file exists, labels not overlapping, frame matches the Frame-the-page margin.

### 3. Regions flow (region extract)
1. Regions tab: draw or pick a region, click Extract, then Render the child region.
2. Pass = child region folder appears under `world/`, trees from the parent are not wiped (own layer "DETAILS - Foliage"), no errors in the panel log.

### 4. Window drag-resize
1. Drag the panel window from 340 px to 900 px wide on every tab.
2. Pass = no horizontal scroll bars on the page, tables scroll inside their box, nothing is clipped. (Only checked at fixed widths so far.)

### 5. Interior door swing screenshot
1. After a Dyers Walk 3D push, in Foundry 3D view stand inside a building with an interior `isDoor` node, click the door.
2. Pass = leaf swings about its hinge by about 90 degrees (not 90 radians, not mirrored). Take a screenshot into `illustrator/out/foundry_screens/door_swing.jpg`. `doorAnimateAngle` sign for interior doors is untested.

### 6. New bridge and panel fields in a live Illustrator
1. Open the panel, Bridges tab: check the preset list now shows rough_log, covered_timber, rope_plank; click Detect, then Apply on a crossing.
2. Check the auto-picked preset suggestion changes with road class (path vs street) and the manual preset choice still overrides it.
3. Re-export the pack and split; in the export log look for a bridge carve report (`worldpack_mesh.LAST_BRIDGE_CARVE`; auto-carves only when the deck clearance check fails).
4. Map symbols for bridges in an actual Render were never seen. Pass = bridge symbols drawn on the bridge layer.
5. Dyers Walk currently has no bridges (audit returns an empty list), so the carve could not be tried on real data; use a place with bridges.

### 7. Other live checks still open (from older notes)
* Foliage: whether 3D Canvas renders alpha-cut atlas cards, COLOR_0 and quantized GLBs; fps not measured (foliage_notes.md).
* Foliage now stands on the final graded terrain and skips road beds, bridge decks and building footprints: look at a push of Dyers Walk foliage by a cut/fill road.
* Foundry tableTex scaling/tiling (bugfix_notes.md item 10); Blender door-node import.
* Lights in placements.json are not turned into Foundry light documents.
* Re-apply the skybox flag after any `push-models`.

## B. Status of `world/bridgehollow_big`
* What it is: a local sandbox copy of Bridgehollow (2400 x 1500 ft, 600 population, 302 buildings, 52 streets) made to test `area_scale` 3 and bigger ring radii (live_qa_notes.md). Not canon, every entity is `proposed`.
* Git: untracked (`??`), 1.7 MB. Decision: keep it as a local-only scratch place, do NOT commit it. Delete it when the bigger-town tuning is finished; regenerate any time from `town_gen.py` with `town_params.json` seed 7 and area_scale 3.
* Do not use it for 3D export; it has no export pack.

## C. Added after the offline passes (all offline-tested only)
Live checks for the second pass of work (each needs the user's Foundry GM tab signed in and a fresh export + push):
1. Padding streaks: run the padding push for Dyers Walk (`padding_heightmap.py push ...`, then `skybox.py set-flag ... --apply`), look at the apron from straight above: no radial colour streaks should run out from the terrain edge. Offline proof: `illustrator/out/padding_streaks_before_after.png`.
2. Rose window: build a parish church (`building_styles_preview.py` or any place with `parish_church`), look at the gable end: you should see sky/interior light through the glazed circle, with a stone reveal. Try `special.rose.foil` = `trefoil` / `quatrefoil` in the preset.
3. Gatehouse carriage arch: export a pack with a `town_gatehouse` building and walk a token through the arch in Foundry 3D; the gatehouse has no door node any more (check the interior layout generator is not asked for one).
4. Town walls: run `worldpack_walls.py inject --place <walled place>` after `worldpack.py export`, then `worldpack_split.py split`; layer `walls` should appear as one GLB; push and check towers at gates, lintel across each gate, wall following the slope. Never run on a real pack yet (only synthetic tests).
5. Bridges: Dyers Walk has no bridges, so the new auto terrain carving and the new preset choice were only tested on synthetic crossings; run Detect/Apply on a place with a river and re-export.
6. Foliage on the final graded terrain: after an export with road grading (cut/fill on) push the foliage and compare tree heights next to a cut/fill road; trees on road beds, bridge decks and building footprints are now skipped (report: `foliage_merge_report.json` -> `keep_out_dropped_ids`).
7. Climate mixes with the imported Baileywiki trees: scatter with `"climate": "temperate"`, merge, and check `triangle_report` / `lod_warnings` in `foliage_merge_report.json` (the beech hero is 30k triangles).
8. New place layouts: Places tab, layout `radial` and `linear`; look at the result on the map (sheet: `illustrator/out/layout_templates_sheet.png`).
9. Terrain LODs vs roads: `terrain_lod*.glb` written by `worldpack.py` (not changed, owned by another change set) can still cut roads at distance; use `worldpack_mesh.lod_terrain_heights` there (see road_grade_notes.md).
