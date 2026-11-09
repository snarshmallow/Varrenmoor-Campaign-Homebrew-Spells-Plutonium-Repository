# Terrain patch tool (`generators/terrain_patch.py`)

Lasso a polygon (feet, heightmap frame: origin top-left, y down) and reshape the heightmap there. The base
`heightmap.npy` is never touched; patches are listed in `world/<place>/terrain/patches.json` and replayed in `order`
onto the base to produce `heightmap_patched.npy` (+ `heightmap_patched_16.png`, `terrain_meta_patched.json`).

```
python generators/terrain_patch.py preview --place bridgehollow --polygon polygon.json --params params.json [--out DIR]
python generators/terrain_patch.py apply   --place bridgehollow --polygon polygon.json --params params.json
python generators/terrain_patch.py undo|redo|list --place bridgehollow
python generators/terrain_patch.py remove --id patch_002 | reorder --id patch_001 --order 5
```
`preview` replays the saved patches, applies the new one in memory, prints fit and seam-check numbers and writes
`preview_hillshade.png` (polygon in red, white line = 0 ft datum, blue ramp = below datum) and `preview_diff.png`
(red raised, blue lowered) into `--out` (default `terrain/patch_preview/`); nothing is saved. `--root` points at an
alternative worlds directory. Python API: `apply_patch(heightmap, meta, polygon_ft, params)`, `replay`, `seam_check`.
`generators/test_terrain_patch.py` runs the Bridgehollow checks (targets, seams, determinism, negative cases).

## Params
| key | meaning |
|---|---|
| `terrain_type` | raise: `mountain`, `rolling_hills`, `mesa`, `plateau`, `dunes`, `rocky_crags`, `ridge_line`. Depress: `bowl` (alias `basin`), `valley`, `trench`, `sinkhole`, `seabed_shelf` |
| `max_height_ft` | raise types: highest elevation inside the polygon (fitted exactly) |
| `min_height_ft` | depression types: lowest elevation inside the polygon (fitted exactly) |
| `avg_height_ft` | target mean elevation over the polygon (all nodes inside, feather included) |
| `steepness` 0-1 | rounded dome to sharp cone; mesa/sinkhole/trench wall steepness |
| `feather_ft` | edge blend width (quintic smootherstep of signed distance, C2) |
| `seed`, `roughness` 0-1, `erosion` (thermal iterations) | deterministic detail |
| `angle_deg`, `width_ft`, `wavelength_ft` | axis for ridge_line/valley/trench/dunes (0 = +x, 90 = +y), half-width, dune spacing |

## How it fits
Shape = function of an interior distance transform (exact distance to the polygon boundary, lightly smoothed
inside, so the peak follows the polygon's medial axis) times type-specific features. Result
`F = E + w*(P - E)` with `P = local_base + A*shape^k` (minus for depressions), `w` = 0 at/after the boundary. The local
base is a smooth extrapolation of the surroundings, so the patch follows sloping ground; the original detail is
kept near the edge and fades toward the smooth base. `A` is solved so the extreme hits `max/min_height_ft`, then `k`
(monotone remap) is solved so the mean hits `avg_height_ft`. If the mean is unreachable it is clamped and a warning
is returned.

Heights are absolute: the new shape rises from the local ground to the requested extreme (`P = base + (ext - base)*shape^k`,
`ext` = `max_height_ft` or `min_height_ft`), and the extreme is fitted on the crest of the shape inside the core (blend
weight >= 0.9), so rugged ground near the border that already exceeds `max_height_ft` cannot cancel the relief (this made a
"mountain" come out as just a smoothed copy of the ground, `A` = 0). The result `info` and the warnings are actionable:
`avg_range` (achievable mean for that max), `needed_ext` ("avg 800 needs max height >= 1025"), `before_mean`, `max_rise_ft`,
`max_drop_ft`, `mean_change_ft`, `peak_core_ft`; a note when existing ground still exceeds the requested max, and when
`min_height_ft` is given to a raise type (ignored). Tests: `generators/test_terrain_patch_absolute.py`.

## Signed elevations
Elevations are signed feet relative to `sea_level_ft` in terrain meta (default 0, only used for previews). Nothing is
clamped at zero; targets may be negative or span zero. Depression types take `min_height_ft`. Verified with a -60 ft
basin and a trench on a coastal copy of Bridgehollow (ground shifted by -650 ft).

## Limits
Targets only reachable if feasible: a deep depression with a wide feather cannot have a mean near its floor (the
feather ring counts toward the mean); very steep shapes with a short feather give steep edges (still C1). Patches
only touch nodes inside the polygon; outside is bit-identical. Not wired into render_world/contours yet: consumers
should load `heightmap_patched.npy` when it exists.
