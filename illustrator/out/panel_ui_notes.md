# Panel UI pass (2026-11-08)

## Skybox tab (new)
- Files: panel/skybox_ui.js, panel/lib/skybox.js, tab in index.html, generators/skybox.py (new commands `list`, `import-scene`; `generate` and `set-flag` now end with a JSON line).
- Presets: clear_day, overcast, dusk, winter, night (the existing generator presets). The mountain ring is always the place's own terrain. Controls: width 1024/2048/4096, turn sky (-180..180 deg slider + number), viewer x,y, "sun follows Lighting tab", Regenerate, Rescan, preview thumbnail (2:1).
- Apply to scene: pick a scene (Refresh scenes = `foundry_push.py list --kinds scenes`, read-only) or paste a uuid. Dry run is ON by default; it only prints the flags. Real apply = `skybox.py set-flag --apply`, which touches only the scene named there.
- Import sky from existing scene: `skybox.py import-scene` does one bridge `get` (read-only), reads flags["levels-3d-preview"] (exr, skybox, sun/lighting keys), fetches the image (shared assets folder, repo, or http://vega:30000/assets/...), converts to webp and saves world/<place>/export/skybox/<name>.webp, _preview.png and <name>.json (source scene + lighting flags). The new sky appears in the Preset list ("Imported: ..."). "Also apply this sky's sun / lighting flags" (off by default) adds them as --scene-flag on Apply. Cube-only (six image) skies and EXR/HDR images are reported as not importable.
- Verified live against Foundry: imported the sky of "Ossuary Market- OLD BACKUP" (read-only get + http download), dry-run apply printed the flags; nothing was written to Foundry. The generated files were deleted afterwards.
- Tests: generators/test_skybox_import.py (mocked scene, asserts only the `get` op is used), panel/test/test_skybox_jobs.js.

## Resizing
- manifest.xml: Size 440x720, MinSize now 300x240 (was 340x300), MaxSize 4000x4000. Takes effect after Illustrator restarts (the manifest is read at start).
- Real resize works: `__adobe_cep__.resizeContent(w,h)` through CDP resized the live panel; the 340 min and 4000 max were enforced (asked 280 -> 340, asked 4500 -> 4000). tools/panel_ui_audit.mjs --real does this; it restores 440x720.
- Reflow: the page is a flex column, `main` scrolls, grids are auto-fill, nav and buttons wrap. Fixed: top bar (Place/View/status/Cancel/Log) now wraps instead of clipping at <= 330 px.

## Legibility audit (tools/panel_ui_audit.mjs)
Checks per tab and width (300, 340, 440, 700, 1000, plus real 340/520/700/1000/2000 and heights 300/720/1000): page/main horizontal scroll, controls poking out, clipped text, overlapping controls, inputs < 44 px, sliders < 80 px, fonts < 9.5 px, tables wider than the panel, nav/top overflow. Before: 59 findings (top bar at 300 px, Regions x0/y0/x1/y1 boxes 26 px wide, shading phase name box 29 px). After: none. Screenshots in illustrator/out/panel_ui/ (<tab>_<width>.png, audit_final.json).
CSS changes: `[hidden]` now really hides flex labels; labels/notes wrap long words; phase headers wrap; Regions rectangle uses auto-fit columns; Places table scrolls inside its box without breaking ids.

## Sliders
Only two places use range inputs: the shading phases (8 sliders per phase) and the new Skybox "Turn sky". All have explicit min/max/step (elev ft 1, slopes deg 1..90, blends 0-200 ft step 5 / 0-30 deg, opacity 0-1 step .05, jitter 0-1.5 step .05), live value in a number box (editable, two-way) with a unit, full width at every panel width. Every other numeric field is a number box with min/max/step already and was left alone (no sliders added to them: a number box is more precise for feet values). `main.js` now mirrors any controls bound to the same state path (slider + number pair) and coerces range values to numbers.

## Limits
- The audit is geometric (rects and overflow), not a visual review; I looked at screenshots of about a dozen tabs at 300/440 px. Dynamic content that is not on screen (long lists, error banners with long text, bridge crossing lists with many rows) was not exercised.
- Panel size changes are clamped by the manifest; docked width is also constrained by Illustrator's dock, which I did not drag.
