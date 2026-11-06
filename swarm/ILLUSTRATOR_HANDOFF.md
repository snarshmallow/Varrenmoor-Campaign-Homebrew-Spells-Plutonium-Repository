# Illustrator bridge: handoff

Goal: Claude generates line-format guides (towns, maps, floorplans) that the user illustrates over in Adobe Illustrator 2024 (installed at `C:\Program Files\Adobe\Adobe Illustrator 2024`). Python and Node are available.

## Plan
1. **Generators** (`illustrator/generators/`, Python or Node) write layered SVG: layers Grid, Roads, Walls, Buildings, Water, Labels, Notes; thin unfilled strokes; scale bar. Works with no plugin, so deliver this first.
2. **CEP panel** (`illustrator/panel/`), a small Illustrator extension (UXP is not available for Illustrator 2024, so use CEP). It watches a job folder `illustrator/jobs/` (or a localhost WebSocket relay), runs ExtendScript via `CSInterface.evalScript`, and can: create artboards and layers, place or import an SVG, set swatches, save `.ai`, export PNG preview to `illustrator/out/`, and write a result file.
3. **Dev install**: unsigned CEP needs registry `HKCU\Software\Adobe\CSXS.11` (and .12) `PlayerDebugMode`=1 (string "1"), and the extension folder symlinked into `%APPDATA%\Adobe\CEP\extensions\`. Tell the user before changing the registry.
4. **Messaging**: same protocol as swarm/PROTOCOL.md. Send to "DND Swarm Coordinator", first line `[Illustrator bridge] verb: subject`.

## Rules
- Edit only row S7 on swarm/BOARD.md. `git pull --rebase` before push, branch `claude/adoring-shannon-yjixst`.
- No secrets in files or messages. Keep long output in repo files.
- First target is not yet chosen: ask the coordinator (town, dungeon/tavern plan, or region map; page size; scale).
