# foundry-tools: quick commands for Varrenmoor content

One command each to make an NPC (with a generated 3D token), a loot item (with a 3D prop), a scene, or an encounter, put it into Foundry, place it, and document it
in the GM guide and on GitHub. Run from the repo root on the GPU PC (the bridge relay `foundry-bridge/start.bat` must be running for anything that touches Foundry).

```
python foundry-tools/vtt.py <command> ...        (or foundry-tools\vtt.cmd <command> ...)
```

Every command takes `--dry` where it can (prints what it would do, changes nothing). Use `--at=-9.5,-4` (with `=`) for negative coordinates.

## GUI

`foundry-toolstt_gui.cmd` (or `python foundry-tools/vtt_gui.py`) opens a window with a tab per tool: **NPC, Item, Scene, Encounter, Place / Where, Publish**.
It connects to Foundry on start (File > Refresh reloads the lists), so scenes, actors, items, folders and playlists are picked from drop-downs. Each create tab has a
**Dry run** beside the create button, **Load / Save spec** (the same JSON the command line uses), and a "Document in the GM guide" tick. The NPC tab has a
**Generate concept image** button that shows the picture before you commit to the 3D step. Long jobs run in the background and stream to the log at the bottom.

## Commands

| Command | What it does |
|---|---|
| `npc <spec> [--scene S --at x,y] [--doc]` | dnd5e NPC actor (full HP, features, attacks) in the folder you name; with `art` in the spec: concept image (SDXL) -> Stable Fast 3D -> turned to face the camera -> token model attached. Optionally places a token. |
| `item <spec> [--scene S --at x,y,z] [--wall] [--doc]` | Loot item (player-facing text only) with a procedural 3D prop (paper, book, tag, tin, box, wall plate; text is printed on the face). Optionally places it as a model tile. |
| `scene <generator> --name N [--folder F --playlist P --door-sound K]` | Builds `foundry-3d/generators/<generator>.py` and creates the scene (tile, lights, vision off, folder, playlist, door sounds). Never touches existing scenes. |
| `encounter <spec> [--dry] [--doc]` | Places groups of existing actors as tokens and writes a GM-only journal (setup, tactics, rewards, GM notes). |
| `place --actor A \| --item I --scene S --at x,y[,z]` | Place an existing actor or item. |
| `where --scene S --at x,y,z` | Convert generator metres to scene pixels (to check a spot). |
| `doc "message"` | `git add` the guide, tools, generators, textures; commit; push. |

`--template` on `npc`, `item`, `encounter` prints a spec to start from (`examples/` has copies). `--set key=value` overrides a field (`--set hp=30 --set art.height=1.2`).
`--doc` appends the entry to `gm-guide/Varrenmoor_Generated_Content.md` (the main guide gets one pointer line) so the secrets live in the guide, never on a player-draggable item.

## Typical runs

```
# a new NPC with art, placed in the forge, documented
python foundry-tools/vtt.py npc myguy.json --scene "Brokka's Forge" --at=-1.4,1.0 --doc
# a clue on a desk (z = desk top height) and one on a wall
python foundry-tools/vtt.py item note.json --scene "Ossuary Exchange Tavern" --at 3.6,-9.55,1.07 --doc
python foundry-tools/vtt.py item plate.json --scene "Ossuary Exchange Upstairs" --at=-8.5,-1.5,1.55 --wall
# a whole new place from a generator
python foundry-tools/vtt.py scene ossuary_forge --name "Brokka's Forge v2" --playlist "Ossuary Forge" --doc
# then publish
python foundry-tools/vtt.py doc "Add Mara and her ledger"
```

NPC spec fields: `name, cr, size (tiny/sm/med/lg/huge), type, subtype, alignment, hp, hp_formula, ac, abilities[6], speed, senses, languages, bio (player-facing), gm_notes,
features[{name,text}], attacks[{name,ability,dice,dtype,bonus,reach}], disposition, named, folder, art{prompt|image|model, height, seed, tris, seq_offload, scale}`.
Item spec fields: `name, description (player-facing only), gm_notes, shape, w, d, h, color, text, wall, folder, rev`.

## Hard-won rules (why the tools behave as they do)

* **Scale/origin.** 1 m = 100/1.524 px. A model tile's x,y is its centre; width = model X, height = model plan-Y, depth = model Z. Token models: origin at floor centre, **front toward Blender -Y**.
  SF3D output faces +Y, so the pipeline always runs `blender/turn180.py`. Largest dimension fills the token square; use the token `scale` flag for small creatures.
* **Heights.** Elevation is in feet (1 m = 3.281 ft). The floor top in the generators is 0.1 m, model tiles sit at 0.0995 ft. Items rest at `surface height`: floor 0.1, a desk top is its table height.
  Models are recentred when built; `where` and `place` use the sidecar `shift` so you can think in generator coordinates.
* **Browser cache.** Foundry caches models by file name. A rebuilt model needs a new name (`rev` in an item spec, or a new `--name`) or the user needs Ctrl+F5.
* **No coplanar faces, no z-fighting.** Faces that share a plane flicker. Offset by a few mm or let boxes overlap.
* **3D Canvas has no Item drop target.** Items with a `model3d` flag can be dropped on a 3D scene only because the `varrenmoor-watchers` module adds that handler.
* **Bridge limits.** The relay can list/get/create/update but has no delete. Delete test documents by hand. New embedded types must be allowed in
  `foundry-bridge/module/varrenmoor-bridge/scripts/bridge.js` (then reload Foundry on the host).
* **Memory.** The PC can run short; image generation uses `--seq-offload` by default (slow, about 10 min, small RAM). Close heavy programs first if it is killed.
* **Never place the six painting tokens** (the GM does it by hand), never activate scenes unasked, and keep GM notes out of item descriptions.
* **Downloads** (music, icons): CC0 or credited CC-BY only; no ripping from YouTube. Credits go in the playlist description or `textures/icons/CREDITS.txt`.

## Layout

```
foundry-tools/vtt.py          entry point            vtt/common.py   bridge, lookups, metres->pixels
vtt/npc.py  item.py  scene.py  encounter.py  docs.py  art.py (2D->3D)   cli.py
foundry-3d/ai/concept.py      SDXL concept image     foundry-3d/blender/turn180.py   turn a token model
foundry-3d/generators/_items.py   generic props      foundry-json/fvtt.py   dnd5e actor/item builders
```
