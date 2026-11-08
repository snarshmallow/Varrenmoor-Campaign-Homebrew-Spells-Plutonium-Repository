# Textures: audit and update, 2026-11-08

Everything is procedural and offline (our own pipeline: `generators/worldpack_pbr.py`, `padding_textures.py`). No Gemini/ChatGPT/Chrome. Art assets are called textures from here on.

## Audit (`generators/textures_audit.py`)
Run: `python textures_audit.py --raw --tag before`, `python textures_audit.py --tag after`, `python textures_audit.py --padding`. Output in `out/textures_audit/`: `sheet_before.png`, `sheet_after.png` (each texture as a 2x2 repeat), `metrics_before.json`, `metrics_after.json`, `padding_tiles_sheet.png`, `padding_tiles_metrics.json`.
Metrics: seam (step across the wrap / p90 of the interior per-line steps; about 1 = invisible), macro (spread of 8x8 block means / pixel spread; high = large blotches that make the repeat obvious), texels per foot at the catalogue tile size, normal-map tilt, roughness-map spread. 33 textures: walls (12), roofs (7), roads (7), ground (5), water (3).

Findings (before):
* Seams: no texture shows a real seam to the eye. The metric flags wall_frame, s_board, s_clap, s_log (53, 39, 30, 10) because their edges are structural (frame posts, boards, lap lines), not seams; shingle/slate/red_tile/roof_snow (1.8 to 3.3) are course lines. A cross-fade seam fixer was tried and made rubble/frame/shingle worse (ghosting, washed frame), so it is only a safety net now (fires above 6.0, image-sourced textures only; nothing currently triggers it).
* Texel density (px per ft at the catalogue tile size) was very uneven: walls 50 to 128, roads 24 to 43, roofs 28, rock 19, water 21, grass/dirt/snow 24. Ground, rock and water were the weakest.
* Repetition: image-sourced ground textures (dirt, packed earth, grass, rock, snow, w_snow) have the strongest macro blotches (0.56 to 0.73), the easiest repeat to spot from above. Generated plaster too (0.58 to 0.75).
* PBR: only 8 textures have a roughness map, and it was a copy of the height field. Normal maps on dirt, grass, snow, water, ice were almost flat (tilt 0.012 to 0.03). Wet variants did not exist.
* w_plank (image) looks camouflage-like; not changed (needs a new source texture, not a generator fix).

## What changed (general, not place-specific)
* `condition()` in worldpack_pbr (applied by `base_texture`, `raw=True` skips it):
  - macro flattening on image textures and plaster/style textures: divides out a share (max 0.6) of the large-scale brightness; image blotchiness dirt 0.56 to 0.46, grass 0.64 to 0.50, rock 0.62 to 0.47, plaster 0.58 to 0.47;
  - density boost for image textures under 32 px/ft: 2x bicubic upsample plus periodic fine grain (grass/dirt/snow 24 to 48 px/ft, rock 19 to 38, water 21 to 43, roofs 28 to 57, w_rock 26 to 51);
  - fine height grain in every height field so flat areas still catch light in the normal map (dirt/grass tilt about +40%, roofs +25%);
  - seam fade only as a safety net.
  Structured generators (timber frame, rubble, boards, clapboard, logs) are left alone: their edges are the design. Note wall_frame is one framed panel per tile by design, so a 2x2 view reads as a window grid.
* `mr_map`: periodic roughness noise (`micro`) so highlights break up; `wet=True` makes low spots smooth (puddles).
* New wet variants in the catalogue: `mat_cobble_wet`, `mat_dirt_wet`, `mat_gravel_wet` (darker, cooler, glossier, roughness map). Not assigned to any road yet; use them as the material id.
* Existing exported packs in `world/*` were NOT regenerated; the new look appears at the next split/export.

## Four new padding texture presets (`presets/padding/textures/`)
`meadow`, `forest_floor`, `scree`, `heather_moor` (each a full palette plus `"tile_kind"`, generated in `padding_textures.TILE_KINDS`: periodic fbm / periodic Voronoi). Pick them where summer/autumn/winter/overcast are picked. They are our own procedural textures (the Gemini candidates were neither used nor fetched).
Seamless check at 1024 px (seam metric, about 1 or less = invisible): meadow 0.99, forest_floor 0.98, scree 1.06, heather_moor 0.94 (existing summer 1.46, autumn 1.24). Tiles are periodic by construction (FFT noise, wrapped Voronoi). Visual: `out/textures_audit/padding_tiles_sheet.png`.
Limits: meadow is smooth at 500 ft per repeat; scree reads as fine gravel at that scale; forest_floor shade was raised to 1.3 (first version was near black).

## Labels
"art"/"artwork" as a label became "textures": panel Foundry tooltip (push actor: portrait/token textures), DESIGN.md token and portrait line, 3d materials note. Not changed (code/names): `ART - ...` layer names, `art/<place>` asset paths, "brush artwork" (vector brushes).

## Tests
`test_textures.py` (7), `test_worldpack_pbr.py` (10), `test_padding_heightmap.py` (14), `panel/test/test_padding_jobs.js` (13): pass. Not run: full test_worldpack.py (by instruction), live Foundry/Illustrator.
