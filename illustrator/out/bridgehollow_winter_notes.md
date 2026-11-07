# Bridgehollow winter map (snowy mountains, legible labels)

Files (Illustrator 2024 via panel jobs `winter_bowl|town|z40`, all steps ok, rasters embedded, no existing .ai overwritten):
`bridgehollow_winter_bowl.ai/.png` (200 ft/in), `bridgehollow_winter_town.ai/.png` (100 ft/in), `bridgehollow_winter_z40.ai/.png` (40 ft/in). PNGs are 200 dpi page exports (2448 px wide).
Raw layers: `bridgehollow_winter_shading_*.png`, `bridgehollow_winter_fills_*_fills/`, `bridgehollow_winter_light_*/` (shadows.png, light_glow.png, lighting_cfg.json). Dev iterations: `out/winter/`.

Layer order (checked in the job layer tree): LINES, labels (separate sublayers, Leaders separate, Label Backing), ART - Light Glow, ART - Shadows, ART - Fill Buildings, Streets, Water, Fields, ART - Shading. Only actions that work in the old host.jsx were used (new_document-free place_svg open, place_image x7, get_layer_tree, save_ai, export_png).

## Commands
    python illustrator/generators/make_fill_textures.py --only w_snow,...   # 22 new seamless w_* tiles (snow, frost grass, frozen earth, ice, conifer, rock, scree, snow roofs, snow cobble, slush, packed snow, furrows, open water)
    python illustrator/generators/winter_build.py bowl|town|z40 [--tag dev]  # svg + fills + shading + lighting + panel job (out/winter/job_<view>.json)
    copy the job to illustrator/jobs/ (out/winter/runjob.sh does it and waits)
winter_build runs: render_world.py --view V --contours --label-preset winter_legible --contour-shading <preset> (contours recoloured cool blue-grey, white casing),
fills_raster.py --style winter, shading.py --phases alpine_winter (bowl) | town_winter (town, z40), lighting.py --config (sun az 200 alt 17, cool shadow #1a2a4c, softness 0.7, building shadows only,
warm glow points #ffb45a at the inn, warden hall, magistrate court, meeting hall, treasury, smithy; shadow/glow PNGs clipped to the terrain extent).

## Presets
- `presets/terrain_phases/alpine_winter.json`, `town_winter.json` (valley floor with a patchy snow blanket 0.6 / 0.8): frozen farmland, dead frosty grass, snow from ~700 ft (blend 100 ft) up to 42 deg, dark snow-dusted conifer floor 810-890 ft, snow-dusted scree 28-40 deg, dark rock > 40 deg; hillshade az 200 alt 24 strength 0.8 exag 1.6; muted cool tint #aebfd8.
- `presets/town_styles/winter.json`: roofs by type (houses white/blue-grey snow, thatch with snow, timber; inn/tavern red tile with snow patches; civic and some craft dark slate; mill/barn/stable dark timber), ridge 0.34, eaves 0.5, 30% soot-stained chimneys; roads/streets slush, lanes packed white, alleys grey slush, plazas cobbles through snow, bridges snowy planks; fields snow furrow / frozen plough / snowy pasture / stubble; river open dark channel with ice from the banks (ice 30 ft, noisy edge), snow banks.
- `fills_raster.py` additions (all optional keys, defaults unchanged): shadow `color`, buildings `ridge`, `light`, `chimney`, water `ice`.
- `presets/label_presets.json` `winter_legible`: navy #0b1730 text on an 86% white box (districts bold 10.5 pt with 90% box, buildings/streets bold ~6.5 pt with white halo), leaders white with navy casing 2 pt, weights building/road 3.0, plaza/junction 1.5, water 8.0, area_move 0.05, collision "number" with a Key legend (labels that find no clear spot become numbered markers), tiers districts/plazas <=1000 ft/in, civic <=300, streets <=120, houses <=45.
- Panel: the Shading preset and Town fills style dropdowns list the preset folders, so "alpine_winter", "town_winter" and "Winter (snow)" appear without code changes; label preset available by name (Labels tab, Apply preset / `--label-preset winter_legible`). `panel/test/run_mock.js`: 124 passed.

## Label QA (label_declutter.py, features = buildings, plazas, roads, water)
| view | shown | hidden (scale / collision) | numbered | text over features | labels > 25% | label overlaps | leaders crossing labels |
|---|---|---|---|---|---|---|---|
| bowl 200 ft/in | 19 | 136 / 0 | 2 | 0.1% | 0 | 0 | 0 |
| town 100 ft/in | 22 | 133 / 8 | 3 | 3.7% (building 0.4, road 3.2) | 1 (Court Square, small plaza, 43% road) | 0 | 0 |
| z40 | 59 | 0 / 50 (small houses) | 0 | 1.9% | 0 | 0 | 0 |
Over water: 0% in all three. The v8 working preset had 22.9% / 14 labels over 25% / 1 crossing at town 100. Hidden-by-collision are street names and house names in dense blocks (kept in `Labels - Hidden`); civic buildings never disappear (numbered in the Key when crowded).
Looked at every PNG at 100%: text is readable over snow, rock, forest, roofs and roads; boxes keep it clear.

## Notes / limits
Bowl labels: 2 civic numbered (Warden's Hall, Lockup). The warm glow is subtle (visible as gold flecks on the lit roofs at 100 and 40 ft/in). Valley-floor frost grass shows as khaki patches by design (dead grass). Hillshade on steep slopes makes the high ground grey, not white; lower `hillshade.strength` in the preset for whiter peaks.
