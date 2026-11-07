# Panel live test 2026-11-07 (Illustrator 2024 v28.2, job-file driven, scratch documents)

| Action | Result | Notes |
|---|---|---|
| ping | PASS | version 28.2.0 |
| new_document | PASS | |
| place_svg (mode open) | PASS, but see BUG 1 | before fix the SVG opened as one "Layer 1": no layers existed |
| nested sublayers (LABELS/Leaders, LINES/Terrain/Contours, Blocks, ART-*) | FAIL before, PASS after fix | after fix top-level = NOTES, LABELS, ART-Top/Fills/Textures/Masks, LINES, GUIDES; nested names resolved via recursive lookup |
| set_visible LABELS / Leaders | PASS | PNG diff: LABELS off changes 6871 px; Leaders off changes 586 px (only near leaders); restored |
| lock_layers (nested, GUIDES) | PASS | |
| get_selection | PASS with `layer` fallback (88 closed paths, ids exact after fix); selection path NOT tested | cannot select via script; "no path selected" error text correct |
| place_image (rock.png into ART - Textures) | PASS | 28000 px changed in export |
| apply_fills on bld_barn_003 / Roads ^sqr_ | FAIL before, PASS after fix | BUG 2 |
| replace_layer (Buildings, Leaders) | PASS | 104 items; refuses ART layer (error text ok); missing layer reports error. NOTE: the target doc must not be the SVG itself (app.open returns the already-open doc and closing it kills the test doc); real use is on an .ai |
| save_ai / export_png | PASS | outputs paneltest_*.ai / png |
| render_world (panel flags, --label-offset, contours) | PASS | run from shell with args built by VBCore.jobScaleApply, output paneltest_all.svg (python-spawning steps run only inside the GUI runner, not from job files) |
| town_gen / terrain patch / water | NOT RUN live | covered by test_town_gen, test_terrain_patch, test_worldio, panel/test/run_mock.js (52 passed) |
| get_layer_tree (new) | NOT TESTABLE until panel reload | added to host.jsx; panel loads host.jsx once |

## Bugs found and fixed
1. SVG layers were never layers in Illustrator (`inkscape:groupmode` is ignored; everything landed in "Layer 1", so set_visible, lock_layers and replace_layer failed on real docs). Fix: generators/lib_svg.py now writes `xmlns:i` and `i:layer="yes"` on every layer group (nested too).
2. Illustrator turns `_` in SVG ids into spaces, so item names became "bld warden hall" and apply_fills `^bld_`/`^sqr_`/`^fld_` matched nothing. Fix: ids are emitted with `_x5F_` (Illustrator decodes it back to `_`; verified exact names), plus host.jsx apply_fills also matches the space-normalised name for old files.
3. (Desktop operator, GUI) Tab clicks on Terrain and Layers did not switch content. Could not reproduce from here; panel_state ui.tab stayed "scale", suggesting the handler never ran. Fix: delegated pointerdown/mousedown/click handler on the nav, DOM updated before saving, errors surfaced in the red error line. Possible cause also: click coordinates going stale when the header reflowed (item 4).
4. Header wrapped onto two rows while a job ran. Fix: single-row header (nowrap), status text gets ellipsis, controls fixed size.

## Reload
index.html, main.js and host.jsx are read when the panel loads: close and reopen the panel (Window > Extensions > Varrenmoor Bridge) or restart Illustrator. The panel's own "Reload" button only re-reads view_settings.json.
