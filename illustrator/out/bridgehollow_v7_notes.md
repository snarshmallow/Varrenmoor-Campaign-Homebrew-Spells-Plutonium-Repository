# Bridgehollow v7: stair-step terracing removed at the source, phased shading

## Root cause (measured)
The saw-tooth cliff edges and tooth-shaped shadows were NOT elevation quantisation (heightmap is float32 end to end, cell 10 ft) but creases in the terrain from `terrain_natural.enforce_river()`: the carve target used the bed height at the nearest river point, so across the medial axis of every bend and past the river ends the target jumped by 10-70 ft in one 10 ft cell, as horizontal creases up to 800 ft from the river (the cone cut reached -115 ft). Second contributor: `terraces()` (deliberate 26 ft benches, default strength 0.4) quantises elevation on steep faces. Erosion, thermal and the gaussian passes were innocent (stage by stage the map was smooth until the river step: max second difference 16.8 ft before, 76.8 ft after).

## Fix (generation pipeline, all places and patches that use the natural pipeline)
- `terrain_natural.py`: bed field blended to a heavily smoothed version away from the banks (60-280 ft); the carve (cut) field is smoothed beyond 150-250 ft from the channel (banks and the floodplain next to the town keep the designed cut, which is why the town stayed buildable); `terraces` default strength 0 (the knob stays); new `natural.smooth` block calls `terrain_smooth.finish()` just before the river bed is enforced.
- NEW `generators/terrain_smooth.py`: `terrace_metrics()` (+ `TERRACE_LIMITS`), `finish()` = along-contour (tangential) diffusion weighted by slope (edge preserving: slopes across a face are kept, cliffs stay steep), slope-weighted removal of the cell-scale component, low-amplitude noise on steep faces (2.5 ft, 55 ft scale, so faces are not planar), extrema restoration (peaks/lows stay as specified). Keys in `terrain_smooth.DEFAULTS`, overridable in the spec `natural.smooth` (`enabled:false` turns it off).
- `terrain.py` untouched. `terrain_patch.py` untouched: patches do not quantise (float64 maths, no benches); the base map they sit on is what was fixed.
- `terrain_check.py`: `metrics()` now has a `terracing` block and the CLI exits 1 with FAIL if `terrace_ok` is false. New test `generators/test_terrain_smooth.py`.

## Metrics, v6 -> v7
| | v6 | v7 | limit |
|---|---|---|---|
| slope_jump_p999 (slope change between neighbouring cells, 99.9th pct) | 3.19 | 0.50 | 1.0 |
| steep_d2_p99_ft (2nd difference on slopes > 0.5) | 20.7 | 4.3 | 8.0 |
| p99.9 second difference, all cells | 56 ft | 5.7 ft | |
| bin_score (bench test over periods 8-40 ft) | 0.136 | 0.132 | 0.30 |
| Elevation | 612.0 .. 1070.5 | 612.0 .. 1071.2 (relief 459.2) | spec 612..1071 |
| Wall slope p50 / p95 (y < 300) | 0.48 / 1.29 | 0.49 / 1.29 | cliffs still steep |
| River bed north / south | 812.3 / 612.4 | 812.7 / 612.4 | monotone (max climb 0.0 ft) |
| Rise slope mean / p95 / max near the rise | 0.114 / 0.36 / 2.15 | 0.118 / 0.35 / 1.03 | |
| Town area slope p90 / over limit | 0.115 / 2.5% | 0.117 / 2.6% | |
Without the cut smoothing limit the town area got steeper (p90 0.150, 6.4% over limit, 95 buildings): the 150 ft start keeps v6 buildability.

## Town
The terrain changed a few feet around the town (median 0.3 ft, rms 1.8 ft, max 16 ft at the old creases), so the deterministic town generator was re-run (`python world/gen_bridgehollow.py --terrain`, same seed, gentle meander, params unchanged): streets 29 -> 27, buildings 136 -> 148, fields 9 -> 10, plazas 3, graded street bed max 0.063 (cap 0.08 held, 0 over cap), report issues/warnings none. The street graded beds are computed from the new terrain, so they match it. Water/river centreline unchanged (same meander).
Backups in `world/bridgehollow/`: `terrain/heightmap_v6.npy`, `heightmap_16_v6.png`, `terrain_meta_v6.json`, `terrain_spec_v6.json`, `water_v6.json`, `town_params_v6.json`, `town_gen_report_v6.json`. Child regions made from v6 need "Refresh from parent"; Foundry scenes, lighting and world packs built from v6 need regenerating (`world/bridgehollow/export` not regenerated).

## Renders (looked at)
- `bridgehollow_v7_hillshade_before_after.png`: top v6, bottom v7, low sun (25 deg). The horizontal saw-tooth ledges and the rippled bands are gone; cliffs keep their shading and the fine rock noise.
- `bridgehollow_v7_lowsun_before_after.png`: `lighting.py` low sun (az 250, alt 9), top v6, bottom v7: cast shadow edges of the walls are smooth, no tooth shapes.
- Phased shading: `shading.py --phases alpine_steep` (farmland / grass / forest / scree / rock / snow by elevation and slope, hillshade strength 0.35, ambient 0.3 = the lighter defaults). The previous samples had the phase layer missing; it is now placed first on `ART - Shading` under LINES, so the order top to bottom is LINES, ART - Fill Buildings, Streets, Water, Fields, ART - Shading (checked in the job's layer tree). Shading rect aligned to the contours/river in the PNGs.
- Files: `bridgehollow_town_v7.svg` (bowl), `bridgehollow_town_v7_town.svg`, `bridgehollow_town_v7_fills_bowl.ai/.png` (200 ft/in) and `bridgehollow_town_v7_fills_town.ai/.png` (100 ft/in), built by panel jobs `v7_bowl`, `v7_town` (jobs/done; Illustrator 2024, 0 failed steps); raw layers `*_shading_bowl.png`, `*_shading_town.png`, `*_fills_*_fills/`. Labels use the new halo defaults. No existing .ai overwritten.
