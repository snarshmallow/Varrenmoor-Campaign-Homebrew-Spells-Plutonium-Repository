# Road grading (roads vs terrain), 2026-11-08

## Root causes (Dyers Walk)
1. **Sparse road vertices vs a fine terrain mesh.** Road centrelines have a vertex about every 13 ft; the terrain mesh has 2.5 ft cells. The ribbon is linear between its vertices, the terrain is not, so the ground rises through the road between vertices.
2. **Authored heights, not ground heights.** The road z comes from the street generator (`elevations_ft`, a design profile with cut/fill intent), not from the exported terrain, so it floats where the ground falls away and sits under it where it rises.
3. **The old conform only pulled the terrain to the centreline** (`worldpack._conform`, 10 ft falloff, bilinear raster, last road wins at crossings). It did not guarantee anything at the road edges or between vertices, and overlapping roads overwrote each other.
4. **Flat cross section.** One z per station for both edges, so on a side slope one edge is buried and the other floats.
5. **Terrain triangles vs raster.** The old audit used bilinear raster heights; the mesh splits each cell on the b-c diagonal, which differs by up to a few tenths of a foot.
6. Lift (0.25 m = 0.82 ft) is fine but was applied on top of all of the above.

## Method (generators/road_grade.py, used by worldpack_mesh.build_parts / build_road)
* Resample every road (and every piece between bridge gaps) every terrain cell (2.5 ft). Ground is read from the **actual terrain triangles** (`mesh_height`, same diagonal as `build_terrain`).
* Profile = (1 - smooth) * ground + smooth * moving average (50 ft window) + lift.
* Pins: bridge-deck road ends and gap ends of trimmed roads keep the authored deck height (cosine blend over 30 ft); junctions and crossings of two roads meet at the same height (T: the ending road meets the through road; X: both rise to the higher). Bridge decks themselves are untouched.
* Cross slope: the edges follow the ground at the edges, tilted at most `cross_deg` (10 deg); each ribbon has a left and a right height.
* No burial: the centre height is raised until the ribbon is >= lift above the terrain mesh at the edges, quarter points and centre of every station and every mid-station.
* Max grade: raise-only forward/backward envelope, so the road never goes under ground. Warnings go to the export report: ground steeper than the limit (road raised clear by more than 3 ft), road standing far above ground, a road end that had to rise above a bridge deck end, ground steeper than 1.5x the limit over 5% of the length.
* Skirt (default on): a flared apron from each ribbon edge down to 0.1 m below the ground (flare grows with the drop, max 1.8 m), same road material. Never above the edge.
* Cut/fill (default off): terrain under half width + 0.5 ft shoulder is set to road surface minus lift and blended to natural ground over 12 ft (smoothstep), local windows per road run. The cross section is flat in this mode. If overlapping beds leave a road under the changed ground the roads are re-draped on the modified terrain (raise only) and a warning says so. Old centreline conform is not used when grading is on; `--road-grade off` restores the old behaviour.

## Settings
CLI (`worldpack_split.py split|reexport`): `--road-grade on|off`, `--road-smooth 0..1` (0.5), `--road-max-grade deg` (14), `--road-cross-deg` (10), `--no-road-skirt`, `--road-cutfill`.
Panel: Foundry tab, "Roads (3D)" block under the 3D models buttons: Smoothing slider + number, Max grade slider + number, Skirt checkbox, Cut/fill checkbox. State key `roads`, passed by Export split models. Python API: `build_parts(pack, road_grade=True | False | {smooth, max_grade_deg, cross_deg, skirt, cutfill})`.
Report: `placements.json` key `road_grade` (params, stats, warnings, cutfill max cut/fill) and a log line per warning.

## Numbers, Dyers Walk (6 roads, terrain 2.5 ft)
Before (road_height_audit.py on exported points vs raw heights, from the earlier agent): float up to 3.4 ft, buried up to 1.6 ft (str_016, str_020); after old conform str_014 buried up to 1.8 ft at 20 % of samples, str_008 floats up to 2.9 ft.

Real built meshes (`road_height_audit.py --mesh legacy|graded`: deck triangle vertices, edge midpoints and centroids vs terrain mesh; depth = deck minus terrain, ft):

| road | legacy min / max, buried | graded (defaults) min / max, buried | graded + cut/fill min / max |
|---|---|---|---|
| str_008 | 0.82 / 3.50, 0 % | 0.45 / 2.49, 0 % | 0.23 / 2.42 |
| str_014 | -1.57 / 3.66, 6.5 % | 0.20 / 3.55, 0 % | 0.03 / 3.32 |
| str_016 | 0.75 / 4.40, 0 % | 0.29 / 3.05, 0 % | 0.31 / 2.88 |
| str_018 | 0.79 / 1.36, 0 % | 0.82 / 1.69, 0 % | 0.72 / 1.43 |
| str_019 | 0.79 / 1.36, 0 % | 0.41 / 2.25, 0 % | 0.81 / 1.34 |
| str_020 | -0.36 / 1.35, 2.6 % | 0.25 / 2.26, 0 % | 0.19 / 1.55 |

Buried samples: 0 on every road. Grade report for Dyers Walk: no warnings (max raise 0.34 ft, max float over centre ground 0.71 ft).

## Honest limits
* "Floating" above the low edge on side slopes is still up to ~3.5 ft (cross slope limited to 10 deg); the skirt covers it. A higher `--road-cross-deg` or cut/fill reduces it.
* Mesh checks use the step-1 terrain. Coarser terrain LODs (merge LOD files, cluster decimation) can still cut through roads at distance.
* Cut/fill changes the terrain under buildings/foliage/fields near roads too (as the old conform did); foliage.py still uses the old `road_conformed_heights` for tree heights, so trees by a cut/fill road may be a few feet off.
* Crossings are detected by station proximity; two roads that run parallel close together get a pin only at their closest point.
* Bridge approaches: the road is pinned to the authored deck end, then raised if the ground needs it; a raise above the deck end > 0.25 ft is warned, not corrected. Bridge geometry and `bridge_maker` are unchanged; with grading on, terrain under bridge approaches is no longer conformed to the road (it stays natural unless cut/fill is on).
* Foundry: the new split models were pushed to `ZZ Dyers Walk 3D Test` (Scene.sFd94FxO1JX8dlJg, 28 tiles updated, optimized/layer_v006 merged) but the verifying screenshot could not be taken: after the push a hard reload of the GM tab dropped the Foundry session to the login page and entering a password is not something the agent may do. Only a "before" oblique shot exists (`foundry_screens/roads_before_oblique.jpg`, old geometry, no top view; the 3D camera could not be set to top view with the available input). Ctrl+F5 by the user will load the new models.
* Skybox flag was not re-applied after push-models; if the sky is missing, run `skybox.py set-flag` as in foundry_live_test_notes.md.

## Tests
`generators/test_road_grade.py` (14: no vertex under the terrain mesh at smoothing 0/0.5/1, built ribbon vs terrain triangles, why sparse points bury, grade limit 6/12/20, steep ground warns, smoothing reduces roughness, skirt at or below ground, params, cut/fill continuity and untouched far terrain, T junction, bridge gap ends, bridge road untouched, Dyers Walk pack has no buried road), `panel/test/test_roads_jobs.js`. test_worldpack.py (18) and test_bridge_maker.py (32) pass.
