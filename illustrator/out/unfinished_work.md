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

## D. Live Illustrator checks (2026-11-08, real panel over CDP 8088, scratch places/docs only; screenshots out/panel_ui/live_*.png)
Setup: panel place before = `bridgehollow` (restored at the end), panel width 823 restored. Scratch place zz_live_export (draft hamlet made via the Places tab), imports zz_import_tavern / zz_import_dyers; all scratch places, docs and renders deleted afterwards. The recovered doc was never touched.

CHECKED, pass
* Places > Generate (draft) + "Also write the Illustrator job": opens a new doc and places the SVG; panel switched to the new place.
* Foundry tab > Export view: job runs, writes illustrator/out/foundry/<place>/view_export.png (2550x1650 at 150 dpi, frame, grid, scale bar ok); panel shows "Exported ... (WxH px)". NOTE: this button only writes a PNG, nothing under world/<place>/export.
* Export world pack (3D) (wp_export) on the scratch place: writes world/<place>/export (entities/*.json, terrain/*, textures, manifest, materials; 37 files, 2.3 MB), panel log "validate: OK"; `worldpack.py validate --place` -> valid.
* Import scene (real button), tavern Scene.LO9YAwP85R74V3tB with lights+tokens: 110 x 80 ft, 4 tiles, 3D settings, 8 lights, 7 tokens; panel switched to the new place; files foundry_lights/tokens/tiles/regions.json written.
* Import scene, ZZ Dyers Walk 2D Test: 310 x 360 ft, 100 walls, 25 closed loops, background copied from the shared assets folder ("copied from the shared assets folder", underlay/background.png 3348x3888; the HTTP path was not exercised). Open in Illustrator: underlay lands exactly on the frame (rect 36,36,594,684 pt at 40 ft/in), locked, below LINES.
* Push scene DRY RUN (CLI, the panel button has no dry-run and applies, so it was NOT pressed): dyers import -> 3348x3888 px, grid 54 px = 5 ft, 100 walls = identical to the source scene. Nothing written to Foundry.
* Window resize: `panel_ui_audit.mjs --real` 340/600/900 on places, foundry, scale: no findings, no horizontal scroll, resizeContent reached each width (restored to 823).

FAILED / fixed here
* Export view on a place imported from a 2D scene used the panel default 150 dpi, so push-scene refused ("grid would be 19px per square (Foundry minimum is 50)"). Fixed in panel/main.js fExport: uses place.json import.native_export_dpi (432 here) when higher than the panel dpi (log line says so). Verified after panel reload: 3780x4320 px, dry-run push ok.
* `foundry_push.py push-scene` without --image crashed with an AttributeError traceback; now returns a JSON error.

FAILED / not fixed (repro) -- STATUS (offline-tested, fixed 2026-11-08; each still needs one live look):
1. FIXED (panel/main.js loadState/saveNow + VB.fresherCache: lists now also kept in world/panel_foundry_cache.json, the fresher copy wins on every place switch; test_places_jobs.js). Scene picker is empty after switching place: Places tab "scene" select is filled from the CURRENT place's foundry.cache (panel_state per place). Repro: import a scene (panel switches to the new place), open Places tab: picker shows only "(pick a scene ...)" until Foundry tab > Refresh again. Fix idea: keep the Foundry lists cache global (world/panel_last_place.json neighbour) or copy it on switchPlace.
2. FIXED (fRefresh now calls VBPlacesUI.paint(); static test). Foundry tab refresh does not repaint the Places picker if the Places tab was already painted (set scene right after refresh -> value ""); call VBPlacesUI.paint() at the end of fRefresh.
3. FIXED for imported places (place_render.py: rasters placed below GUIDES, so the grid shows above underlay/shading, below lines and labels; not changed for normal places). Grid is hidden by the underlay/shading: GUIDES is the bottom layer, so on an imported 2D scene (and the tavern with its shading PNG) the 5 ft grid is not visible in Illustrator. Design decision needed (move Grid above the underlay for imported places).
4. FIXED (closed loops now stay plain wall outlines by default; Places tab "Closed wall loops" = "label rooms" restores Imported room buildings; lights = yellow dots (optional dashed bright ring via place.json import.light_rings), tokens = blue dots on the locked layer FOUNDRY MARKERS in render_world.py; test_place_create.py test_import_markers_render). Imported closed wall loops render as "Imported room N *" buildings with big white-haloed labels and a Key box (cluttered; 25 labels on Dyers).
5. FIXED (flat imports with no background and a flat-stub terrain skip the shading PNG; import warnings now always include "no background image"; markers drawn, see 4). Tavern import (3D scene, no background, no entities): the render gets an all-over grass shading PNG; lights and tokens (foundry_lights/tokens.json) are NOT drawn as markers in Illustrator at all (no layer renders them), and import `warnings` is empty although there is no background.
6. FIXED (Foundry tab: new "Plan (dry run)" button prints size/grid/wall counts and writes nothing; Push scene and Push tiles now ask the in-panel modal first, naming scene, place and that it writes to Foundry; auto-push unchanged; mock/static tests only, no Foundry contact). Panel "Push scene" has no dry-run option (only the CLI has); push dry-run in the panel is untestable without applying.

UNTESTED
* Real Push scene / push-models apply (not allowed), HTTP background download, Regions extract flow, bridges, interior doors (sections A.3, A.5, A.6 still open).

## Live verification 2 (2026-11-08, head 16b479e, ZZ Dyers Walk 3D Test + ZZ Bridge Test only)
Flow: `worldpack.py export` -> `worldpack_split.py split` -> `merge --preset layer --compress none` (layer_v007) -> foliage merged from `out/foliage/dyers_foliage.json` with the new pack ground (foliage_v003, 19 trees dropped as on road beds/footprints: hedges, yard trees) -> `push-scene-3d` (geometry, models, foliage, padding, lights, flags, verify: no problems) with `//VEGA/C/FoundryVTT resources/Data/assets/varrenmoor-3d`. Bridge scratch: export, `bridge_maker.py inject`, split, merge layer_v004, `push-scene-3d --skybox-preset clear_day --prune`. Screenshots `out/foundry_screens/verify2_*.jpg`. View restored to Ossuary Exchange Market, interface unhidden.

VERIFIED (looked at the screenshots)
* Roads sit on the terrain (no floating/buried stretch visible in overhead and oblique), no tree standing on a road or plaza; foliage on graded ground.
* Apron colour: no radial colour streaks from the terrain edge in the Dyers overhead (verify2_dyers_overhead.jpg); the new `meadow` padding texture (verify2_dyers_overhead_meadow.jpg) is lighter and finer-grained, less contrasty than summer; table tile and apron blend.
* Mountains present in the oblique; skybox flag `exr` set (clear_day_v002) after the padding push and read back by verify. Sky itself was only checked via the flag (all shots look downward).
* Bridge scene: all 8 bridges load, decks meet the road ribbons, rope bridge, covered bridges with piers, arch bridges look right; terrain carving left no visible hole or poke-through (verify2_bridge_overhead.jpg, verify2_bridge_oblique.jpg).

PROBLEMS
* `push-scene-3d --with-lights` with `--lighting bridgehollow` pushed "0 lights" and DELETED the 72 existing lights (lights come from the pack placements, which the layer set does not carry). Re-created with `push-lights --lighting bridgehollow` (72 created). Open bug: --with-lights must not prune when it found 0 lights.
* Remaining apron streaks: horizontal smears on the west and east apron/table of Dyers Walk, and the carved river channel of the bridge scratch is extruded into a streaked "ladder" on the north and south apron. These are the steep heightmap slopes stretching the texture (not the albedo seam fix) and a channel running off the terrain edge; not radial from the seam any more.
* A tree canopy overhangs the road at the north end of Dyers (top-left, canopy only, trunk is off the road).

STILL UNTESTED
* Church rose window / trefoil / gatehouse arch and town walls (no place with those was pushed; Brinkburg walls inject on a scratch copy not tried), parallel-road blending (no warning appeared in the Dyers export, so no live case), heather_moor/forest_floor/scree presets (only meadow looked at), sky from a low camera, door files.
* The scratch scene padding is now `meadow` on Dyers (was summer); harmless.

## Fixes after Live verification 2 (offline only, nothing pushed, needs a live look)
* DONE (offline, tests): `--with-lights` found 0 lights because the layer set (`push-scene-3d --placements <layer_vNNN>`) carries no light entities (lights live in the full pack placements; the 'bridgehollow' lighting preset itself is fine, it has sun/ambient and 0 point lights). Now: lights come from `--lights-placements`, else `--placements` if it has lights, else `world/<place>/export/placements.json`; a plan with 0 lights aborts push-scene-3d before any write and push-lights refuses unless `--prune-lights`; bad lighting name fails early listing available place ids; model `--prune` only touches `model:<place>:*` pipeline tiles and is ignored on an empty push. The bridge already only deletes flagged documents (pipelineId prefix).
* DONE (offline preview, not seen live): apron streaks. Causes: (a) channel ladder on N/S = the apron mesh (not the terrain mesh, not the table) continued the carved channel (17 ft deep, 24 ft wide at the terrain edge, 30 ft bank vs table at -4) as a trench with the edge slope/curvature clipped at 0.9, so it dived 40 ft out as a ladder of 62-67 degree walls; (b) soft smear over the whole ring = the apron albedo faded to a FLAT mean colour from 90 ft out and used 45-160 ft blurred terrain colour near the seam, so the ring had no ground detail; (c) the outer strips are the table tile (500 ft repeat, cannot be changed). Fix: `Apron(edge_fade_ft=110, edge_wide_ft=400)`: narrow edge features fade into the apron profile smoothed along the edge, exact at the seam; apron albedo now tiles the table's own ground tile (same texel density, continuous with the table) and its light/dark mottling inside the ring. Previews `out/apron_fix/bridge_{before,after}_overhead_slope.png` (left lit overhead, right slope map) and `bridge_{before,after}_oblique.png`. Terrain texel density: terrain albedo 0.5 px/ft, apron albedo 1.7 px/ft (2048 px over 1200 ft), table tile 2 px/ft. NOT done: terrain mesh edge itself (channel still ends in a cliff at the tile edge, water ends flat; fading it would change the pack export), triplanar/slope easing of the west/east Dyers apron (not re-rendered for Dyers), and the 'lip' in the oblique shot (edge heights match exactly; likely normal/lighting discontinuity at the seam, unverified).
* DONE (test): foliage canopy clearance (`foliage.clear_canopies`, `merge_foliage(canopy_min_ft=8, canopy_overhang=0.3)`): crowns of radius >= 8 ft may overhang a road bed by at most 30% of R; offenders are shifted away from the centreline (<= 1.5 R) or dropped. Re-merge of Dyers foliage needed to take effect.

## Building ground audit / buildings sunk into the ground (offline, nothing pushed, needs a live look)
* NEW `generators/building_ground_audit.py` (`--place P [--no-mesh] [--json]`): per building, on the terrain MESH as the exporter builds it (`final_heights`, same sampler as road_height_audit): base used, min/max ground under the footprint, wall burial, floating gap, skirt shortfall, door sill vs ground at each door and 2 ft in front, lowest roof vertex above ground. Dyers Walk pack (25 buildings) BEFORE: wall burial 0.0 ft everywhere, worst gap 0.80 ft (bld_house_062), door clearance only 0.10 ft, lowest roof 7.6 ft above ground (bld_house_107/078, danish/niedersachsen), skirts always deeper than the gap. So the exported pack geometry (terrain.glb == final heights, placements elevations consistent, LOD4 tile within 0.3 ft) does NOT bury any wall or roof; the sunken look in the screenshots is not in the pack numbers. Suspects that need a LIVE look: Foundry tile elevation rounding/scaling (terrain tile elevation 9.603 ft vs building tiles 11.1, 27.8 ...; a 0.5 ft quantisation would bury 0.1 ft sills), an older push, or which terrain tile/LOD is shown.
* NEW `generators/building_ground.py` + `test_building_ground.py` (9 tests): `resolve` (base kept unless a wall floats more than 1.5 ft or the cut would exceed 3 ft; skirt always reaches 1 ft below the lowest wall ground), `pad_heights` (level pads for ALL buildings, not only interiors, to base - 0.15 ft, plus a 5 ft door apron in front of each door, cut only), `eave_clearance`. Wired in: `worldpack.export_world` (base + skirt), `worldpack_interiors.pad_buildings` (delegates), `worldpack_mesh.terrain_heights` (pads for every pack with buildings). Door sill clearance now 0.15 ft (was 0.10). Re-export Dyers to take effect (world/* not touched).
* NOT done: a visible step/ramp where the ground in front of a door is LOWER than the sill by more than ~1 ft (only reported by the audit); style roofs with very long eaves are only checked by the audit (lowest eave on Dyers is 7.6 ft up, so none reach the ground).

## Terrain edge / seam fix (2026-11-08, offline, needs re-export + live look)
* DONE (tests `test_terrain_edge.py`, previews `out/apron_fix2/`): carved river bed eased to bank level over the last 100 ft before the map boundary (`terrain_edge.py`, `terrain_heights(carve_edge_ease_ft=100)`); apron ring-0 normals = terrain edge normals; apron relief easing + periodic edge profile (corner wedges gone). See padding_notes.md section 9.
* TO DO live: re-export the pack (worldpack.py export) and re-push terrain + padding for the bridge scratch and Dyers, check the river end, the seam lip and the west/east slopes. Bridge/roads near an edge are planned on `bridge_maker.final_heights` (carved without the ease) but the mesh uses the eased bed: only matters for a bridge within 100 ft of the boundary.
