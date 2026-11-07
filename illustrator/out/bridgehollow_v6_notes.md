# Bridgehollow town v6 (gentle river meander, wider town settings)

Files: `bridgehollow_town_v6.svg` (bowl, contours), `_town.svg`, `_area.svg`, `bridgehollow_town_v6_fills_bowl.png` / `_fills_town.png` (dev composite: hillshade + 10/50 ft contours + textured fills), `bridgehollow_town_v6.ai` + `_ai.png` (panel job `v6_verify`: bowl SVG + the four fill rasters, save_ai, export_png; Illustrator 2024). v5 files untouched; backups `terrain/heightmap_v5.npy`, `heightmap_16_v5.png`, `terrain_meta_v5.json`, `terrain_spec_v5.json`, `water_v5.json`, `town_params_v5.json`, `town_gen_report_v5.json` in `world/bridgehollow/`.

## River
- One source of truth: `terrain_spec.json` valleys[river] now has `"meander": {"preset": "gentle", "seed": 1103}` (+ optional `amplitude_ft`, `wavelength_ft`, `width_var`, `gorge_damp`, `width_floor_ft`, `width_gorge_ft`, `bars`). `generators/river_meander.py` turns the coarse route into a dense sinuous centreline (three harmonics, bends fade out at the map edges and are damped in the gorge), the width profile (34 ft gorge -> 66 ft floor, pool/riffle noise), an organic bank outline (independent bank wobble, no dashes) and point-bar polygons (`bars`, drawn as thin sand outlines on the Water layer).
- `terrain_natural.py` (small hook `_river_P`) carves the valley, floodplain and the monotone bed along that same line; `world/gen_bridgehollow.py` writes `water.json` from it (`widths_ft`, `length_ft`, `sinuosity`, `meander`). `terrain.py` untouched. CLI: `python world/gen_bridgehollow.py --terrain [--no-town] [--meander straight|gentle|lazy] [--meander-amplitude FT] [--meander-wavelength FT] [--meander-seed N] [--width-var F] [--no-bars]` (flags are saved into the spec).
- Panel Water tab: "River meander (Bridgehollow)" block (preset, amplitude, wavelength, width variation, seed, sandbars) and button "Regenerate river + terrain" (job `water_river_meander`; state `water.rivergen`).
- Presets: straight 1.017, gentle 1.063 (used), lazy 1.114 sinuosity.
- Bridge: still the one auto-routed Pilgrim Bridge (town_gen A* over the new river), now ~73 ft of water crossed, deck 646 -> 648.8 ft, 26 ft wide.

## Metrics, v5 -> v6
| | v5 | v6 |
|---|---|---|
| Relief (terrain) | 458.8 ft | 458.5 ft |
| River length in map (y 0-1500) | 1526 ft | 1549 ft |
| Sinuosity | 1.017 | 1.063 |
| River width | 60 ft uniform | 33-78 ft (gorge narrow, floor wider, pools/riffles) |
| Bed at north edge / south edge | 816.8 / 611.8 ft | 812.3 / 612.4 ft, strictly downhill (max step -0.41 ft per 25 ft sample) |
| Town area | 615,317 ft2, slope limit 0.15 | 600,980 ft2, slope limit 0.17 |
| Buildings | 128 | 136 (113 houses, 10 civic, 3 farmhouses, 2 barns) |
| Streets / plazas / fields | 28 / 1 / 12 | 29 / 3 / 9 |
| Graded street bed max grade | 0.060 | 0.059 (cap main 0.04 / street 0.08 held) |
| Streets over 0.08 cap on raw terrain | 1 | 1 (raw max 0.092; graded bed has none) |
| Report issues / warnings | none | none |

## Town settings
`slope_limit` 0.17, `edge_fade_ft` 28 -> 12, plazas `per_area_ft2` 600k -> 200k with `extra_radius_ft` [30, 42] (new key: later squares are smaller), so a third small square lands in the commoners' ring (Court Square, Market Square, Square 3). Authority ring lots 1300-3000 ft2 (was 1800-4200) and four more named civic buildings via `named.extra_civic` (new key): Wardens' Barracks, Records House, Customs House, Town Treasury. The meeting hall may now use civic lots too (it failed to place once the third square took lots).

## Honest caveats
- The wider town did not materialise in area: the buildable valley floor is the limit, not the slope setting. 0.15 -> 0.17 adds only ~3.5% and even 0.25 gives ~660k ft2; the new river line also shifted the floor slightly (v6 is 2.3% below v5). Density is up (more buildings, three squares) rather than extent. More floor needs the terrain spec changed.
- `test_town_area.py` now builds with the production `area_auto` params (it used its own slope 0.15 / smoothing 55, which gave a 62 deg corner on the new terrain) and allows 0.2% sliver overlap between the ring and the area outline.
- The Court Square half-disc beside the river is clipped by the water, as before.
- Child regions created from v5 need "Refresh from parent". Foundry scenes, lighting and world packs built from v5 need regenerating; `illustrator/out/water/bridgehollow/*` (derived analysis files) were not regenerated.
- Sandbars are vector outlines only (not in the fill rasters).
