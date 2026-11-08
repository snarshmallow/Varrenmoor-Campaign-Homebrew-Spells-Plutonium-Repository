# Live QA notes (panel + Illustrator 2024, 2026-11-07)

Driven through `tools/panel_debug.mjs` and job files; nothing pushed to Foundry, no Foundry writes.

## Tested live
- All 11 tabs render, 134 buttons bound, no console errors. At 340 px Water (tables) and Regions (child list) overflowed: fixed in CSS (tables scroll, list items wrap); 340 and 900 px now clip nothing. Real window resizing could not be exercised from here (manifest MaxSize is 4000x4000, Type Panel); not verified by dragging.
- Labels (town z40 SVG): finalize_labels (33 callouts), read_label_positions, lock_leaders, move_item + reroute_leaders (anchor dot fixed, leader and casing re-routed to the moved callout, unchanged ones skipped), list_fonts, check_links, relink, embed_all.
- Regions: list, preview outline (district). Lighting: sun presets, night preset with placed lights, preview render. Foundry: connection check and list refresh (read-only, connected, 63 scenes). Details checkboxes: region_render with --details trees,lots opened and saved a Commoners Ring doc.
- Not run live: region extract (reg_create writes world/ children), Foundry writes.

## Bugs found and fixed
1. check_links / relink crashed: ExtendScript has no Array.map (also Array.indexOf in list_fonts). Fixed; relink also works when a missing link reports no path (falls back to item name + image extension).
2. place_image failed with "Target layer cannot be modified" whenever the active layer was locked (e.g. light glow layer relocked): the target layer is now made active, and a failed placement no longer leaves an empty placed item.
3. SVG import dialog "Text on Path will be Flattened" blocked the whole ExtendScript queue (a job hung until someone clicked OK). Cause: render_world emitted <textPath>. Now default `--curved-text host`: the SVG holds a straight fallback label and `<svg>.curved.json` lists the curved ones; host.jsx (place_svg and replace_layer) swaps each fallback + halo for real type on a path (verified: 8 street/river names, path type, no dialog). `--curved-text svg` keeps textPath (browsers, svg_raster tests). host.jsx also opens SVGs with alerts suppressed (app.userInteractionLevel) so no import warning can hang a job.
4. "Some files are missing or modified in the Links panel. Update now?" on reopen: region_render's place_image actions did not embed. They now do, and host place_image embeds by default (only `embed:false` links).

## Features added
- Town tab: "Frame the page" (buildings / lasso / whole place, margin) -> `panelio.py fit` writes nice scale, grid and focus into the preset of view_settings.json so every generator agrees; Area scale input (area_scale) in the lasso params. Mock test: panel/test/test_town_fit.js (5 checks).
- Bigger town: area_scale now also relaxes hard_slope (+0.2 per unit) and the gorge buffer (area_scale 2 -> 0.9M ft2, 3 -> 1.3M ft2 vs 0.6M at 1). The area limit is the bowl floor (662k ft2 whatever the target) and then the gorge test. Building count is driven by ring radii: sandbox world/bridgehollow_big (copy, not committed; canon untouched) with area_scale 3, authority r 300, commoner r 900 and relaxed build limits gave 302 buildings / 52 streets vs 148 / 27 canon. Render: out/qa/big_town.png (+svg).

## Remaining / unverified
- Resizing the panel window by dragging; region extract flow live; fills/shading/terrain tabs were not re-run live.
- Label QA still measures the straight candidate box for curved street text.
- Not mine: Blender door-node import, Foundry tableTex scaling check.
- Tests: run_mock.js 131/131, test_host_reroute, test_town_fit, test_svg_raster (+2), label_style/declutter/offset, town_area.
