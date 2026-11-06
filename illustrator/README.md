# Illustrator bridge

Claude writes layered line-art SVGs (`generators/`) and, optionally, drops job files that a small CEP panel in Illustrator 2024 executes.

## Without the panel
Run `python illustrator/generators/test_guide.py`, then open `illustrator/out/test_guide.svg` in Illustrator. Each `<g id="...">` becomes a layer.

## Install the panel
1. `powershell -File illustrator\install.ps1` (symlinks `panel/` into `%APPDATA%\Adobe\CEP\extensions\VarrenmoorBridge`, copies if symlinks are not allowed). No registry changes.
2. Read, then run once: `powershell -File illustrator\enable-debug.ps1`. It sets `HKCU\Software\Adobe\CSXS.11` and `CSXS.12` `PlayerDebugMode` = "1" (needed for unsigned extensions).
3. Restart Illustrator, then Window > Extensions > Varrenmoor Bridge. The panel shows the jobs folder and status.

## Test
1. Panel open. Copy the `ping` job below to `illustrator/jobs/t1.json`.
2. Within ~2 s it moves to `jobs/done/t1.json` and `jobs/done/t1.result.json` appears with `"ok": true` and the Illustrator version.
3. Then run the full example (new doc, layers, place the test SVG, save, PNG preview).

## Job format
File `jobs/<id>.json`; `actions` run in order and stop at the first failure unless `"continue_on_error": true`. Relative paths resolve from the repo root.

```json
{"actions": [{"action": "ping"}]}
```

```json
{
  "id": "test_guide",
  "actions": [
    {"action": "new_document", "width_in": 17, "height_in": 11, "landscape": true},
    {"action": "ensure_layers", "names": ["Grid","Roads","Walls","Buildings","Water","Labels","Notes"]},
    {"action": "place_svg", "path": "illustrator/out/test_guide.svg"},
    {"action": "save_ai", "path": "illustrator/out/test_guide.ai"},
    {"action": "export_png", "path": "illustrator/out/test_guide.png", "scale": 100}
  ]
}
```

`place_svg` opens the SVG, copies each layer's items into the active document's same-named layer, and closes the SVG. With `"mode": "open"` (or no open document) it just leaves the SVG open as its own document.

Result file: `{"id","ok","finished","results":[{"action","ok","error"?,...}]}`.

## World model and layered town SVG
- `world/gen_bridgehollow.py` (fixed seed) writes the DRAFT model in `world/bridgehollow/` (all entities `proposed`). Re-run it to reproduce the layout.
- `python illustrator/generators/render_world.py --view town` writes `illustrator/out/bridgehollow_town.svg` with the layer tree from DESIGN.md section 3. Other views: `--view street:<street_id>` (1 in = 20 ft), `--view building:<building_id>` (1 in = 5 ft); output defaults to `illustrator/out/bridgehollow_<view>.svg` (`--out` overrides).
- Every shape is a closed path with `id` = entity id; strokes use classes `guide-line`, `wall`, `road`, `water`, `proposed`.

## More panel actions
- `replace_layer`: `{"action":"replace_layer","path":"illustrator/out/bridgehollow_town.svg","names":["Roads","Buildings","Labels - Buildings","NOTES"]}`. Opens the SVG, and for each named layer (sublayers are named individually, parents are not recursed) clears that layer's own items and redraws them from the SVG, creating the layer if missing. Layers named `ART ...` are refused and never touched. Lock state and visibility of the target layer are restored afterwards (`"restore_lock": false` leaves it unlocked). Fails if a name is not in the SVG unless `"strict": false`.
- `lock_layers`: `{"action":"lock_layers","names":["GUIDES","Grid"],"locked":true}` (`locked` defaults to true; false unlocks). Works on layers and sublayers.

## Status
Tested 2026-11-06 in Illustrator 28.2.0: ping and the full test_guide job succeed.

replace_layer and lock_layers are written but not yet tested in Illustrator.
