# Bridgehollow v8: calmer shading, readable contours, clean margins

Before/after images (top v7, bottom v8): `bridgehollow_v8_before_after_bowl.png`, `bridgehollow_v8_before_after_town.png`.
Files: `bridgehollow_town_v8_calm_bowl.ai/.png` (200 ft/in), `bridgehollow_town_v8_calm_town.ai/.png` (100 ft/in), `bridgehollow_town_v8_calm_z40.ai/.png` (40 ft/in check),
built by panel jobs `v8_calm_bowl|town|z40` (Illustrator 2024, all steps ok, rasters embedded; no existing .ai overwritten). Raw layers `*_shading_*.png`, `*_fills_*_fills/`.

## What was wrong (v7)
Saturated greens (grass #6f9a48 at full strength), scree and rock as high-contrast blotches (slope thresholds jittered +-6 deg at 70 ft scale, slope field unsmoothed,
speckled texture), hillshade 0.35 on top, contours 0.3-0.85 pt brown with no separation from dark green/rock, and the page grid showing around the map in the margin.

## Changes
- `shading.py`: global `muted` control {saturation, contrast, tint, tint_strength, pivot} (CLI `--muted-*`, `--no-muted`; panel Shading tab "Muted (map-calm)"); per-phase `texture_contrast`
  and `texture_brightness`; `slope_smooth_ft` (smooth the slope field before thresholding); `--phases` defaults to `alpine_steep_calm`.
- Presets: a `<name>_calm.json` for alpine_steep, temperate_valley, dry_hills, ink_wash, parchment, coastal_basin (originals unchanged, still available by name).
  Calm values (alpine): saturation 0.62, contrast 0.86, warm tint #d9cba3 at 0.12, slope smoothing 12 ft, noise scale 120 ft and jitter x0.5, slope blend >= 5 deg and elevation blend >= 50 ft
  (snow 100 ft / rock more gradual), scree opacity 0.7 at brightness 0.78 and texture contrast 0.4, hillshade 0.36 / ambient 0.38. Panel default preset and region default (`temperate_valley_calm`) switched to calm.
- Contours: casing path (cream, `<id>_halo`) under every contour, strength chosen per piece from the median luminance of the shading under it (dark ground 0.70-0.80 opacity, light 0.25-0.35),
  brown line 0.35 pt minor / 1.1 pt index. `--contour-shading PRESET|none`, `--no-contour-halo`; panel Contours tab checkbox.
- Grid: drawn only inside the map window (place bounds), lighter (0.3 pt at 38% / 0.5 pt at 55% neutral grey); `--grid-full-page` / `grid_extent: "page"` / panel Scale tab checkbox for the old full-page grid.
  The Grid layer sits under the fill/shading images (existing layer order), so inside the map it is visible with the shading layers hidden (placing the images below GUIDES was tried: Illustrator would not
  move a placed layer below the bottom layer, so it was reverted). The margin around the map is now clean paper.

## Check (looked at in Illustrator exports)
Bowl: grass/farmland, olive forest, grey scree band, dark rock and light snow are all distinct but muted; no hard blotches; contours read over forest, rock and snow; margin is clean.
Town (100 ft/in): same, buildings/streets/fields stand out more against the quieter terrain. 40 ft/in: valley floor is uniform muted green (it is flat at that scale), contours sparse.
Tests: test_shading_tiling, test_lighting, test_terrain_smooth, test_worldpack, test_label_style, new test_calm.py, panel run_mock.js (114 passed).
