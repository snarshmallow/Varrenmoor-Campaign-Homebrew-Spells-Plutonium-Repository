# Session 14 Ossuary scenes, agent B (B3, B4, B5)

## Status 2026-11-09 (before the 6:30 PM deadline)

Approach: the existing Ossuary scenes (Rune Workshop, Shafts + Annex, Clinic, Warehouse) are 3D Canvas scenes, each one Blender-generated
GLB tile from `foundry-3d/generators/` (rotation 0, grid 100 px = 5 ft, scene settings cloned from Quill's Rune Workshop). The new scenes
use the same pipeline (not an illustrator world place), so they match in scale, textures and lighting.

| Scene | Foundry uuid | Folder | Tiles | Lights |
|---|---|---|---|---|
| The Dusty Terminal and the Cold Door | `Scene.nuVW7YxDumRi6Wa3` (1800 x 1300) | Act 2 > The Ossuary Exchange > Session 14 | interior `ossuary_dusty_terminal.glb` (visible); exterior strip `ossuary_cold_door_exterior.glb` (HIDDEN) | warm lamp over the terminal #ffc78a (on); anchor-stone glow #9fd0ff (HIDDEN: turn on after T1); moonlight #a8c4ff over the exterior strip (HIDDEN) |
| Ropewalk and Signal Loft | `Scene.nlackHJHF82YaGwm` (2300 x 1300) | same | `ossuary_ropewalk.glb` | two warm work lamps #ffc78a, Nan's window #ffe6b8 |
| Cold Door Landing | not built (decision below) | | | |

Neither scene is activated. Built by `foundry-3d/make.ps1 <generator>` and pushed with `foundry-bridge/make_scene_s14.py` (takes the shared
push lock `swarm/locks/foundry_push.lock`, creates the Session 14 folder if missing, refuses duplicate names).

### B3 The Dusty Terminal and the Cold Door (`foundry-3d/generators/ossuary_dusty_terminal.py`, `ossuary_cold_door_exterior.py`)
- 45 x 30 ft interior, ashlar walls 3.4 m, no ceiling (beams only, like the other shops). West entry at (0, 15), 1.6 m wide.
- Dusty terminal at (12, 6): granite plinth, brass receiver + cap, capsule slot, two brass pipes up and a pipe run, a lever; capsule plinth at (17, 6)
  with a cubby of three old capsules and a capsule on top; capsule rack (shelf) on the west wall; timetable board on the north wall; dark dust patches.
- Pell's rail along the north wall x 5..30 ft with brackets, his chair hung from it and a counterweight.
- Cold door: real door node `door_cold_door` (isDoor, opens inward/west, iron leaf 1.5 m) in a carved granite frame at (45, 15); threshold glyph
  (Ingwaz, carved dark) on a slate lintel panel; anchor stone (granite block) in the south (right-hand) jamb at waist height; frost rime on the frame,
  frost on the floor and a low cold mist at the threshold.
- Workbench at (30, 24): braided line coil, gorge frost jar, four chisels, stool. A few crates and a barrel.
- Named separate nodes: `Dusty_Terminal`, `Terminal_Lever`, `Capsule_Plinth`, `Pell_Rail`, `Lintel_Threshold_Glyph`, `Anchor_Stone`, `Workbench`,
  `Braided_Line_Coil`, `Gorge_Frost_Jar` (+ the door node).
- Exterior strip (x 45..55 ft) is its own HIDDEN tile: packed snow, drifts against the wall, the dark road edge, four snowy pines, rocks.
  At the table: open the door, then unhide the exterior tile and the moonlight.

### B4 Ropewalk and Signal Loft (`foundry-3d/generators/ossuary_ropewalk.py`)
- 80 x 30 ft hall, walls 5.6 m, tie beams; south double doors (two real door nodes) to the market at (40, 30) with `Market_Doors` sign board; windows.
- Twisting wheel at (5, 15) on an A-frame with hooks and crank; sledge rails down the middle; traveller sledge with hooks at x 36 ft; three rope
  strands from the wheel to the sledge, carried on six T-posts; rope coils, tar buckets, a barrel.
- Haddo's workbench at (60, 8) with braid coils and a braid in progress; iron bar bench at (70, 22) with four separate bars `Iron_Bar_1..4`.
- Signal loft: timber gallery at 2.8 m, x 50..80 ft, y 0..10 ft, posts, rail and balusters; ladder at (50, 10) (`Loft_Ladder`); Nan's chair,
  `Signal_Bell` on a post at (72, 4), speaking trumpet, a line of seven signal flags, `Signal_Window` (north wall at x 75 ft) with a short run of
  trolley cable outside.

### B5 Cold Door Landing: skipped (decision)
The Eirwitch Camp (Night) scene (`Scene.r755aOD0XwiusHcw`) already has the west road end: the Witch Road enters at its west edge (0, 655 ft) through
snowy pines. Together with B3's exterior strip (snow, road edge, pines, moonlight beyond the open cold door) that covers the step-through beat, so B5
was not built (spec: "skip if the camp scene covers it"). Not done (not my scene): a "Cold door landing" note at the camp's west road end; the camp's
owner can add it.

### Approximate / not done
- Ladder is a leaning pair of rails with rungs, approximate geometry. Nan's loft is reached only by the ladder (no walls/levels in Foundry).
- No Foundry walls, sounds or notes were added (none in the template scenes either); no ambient sound at the door.
- Interaction objects are separate glTF nodes with the spec names; they are not Foundry tiles of their own.
- If the dust or any model changes are re-built, the GLB path stays the same: Ctrl+F5 in the browser.

### Commands to rebuild / redo
    cd foundry-3d; .\make.ps1 ossuary_dusty_terminal; .\make.ps1 ossuary_cold_door_exterior; .\make.ps1 ossuary_ropewalk
    # new scene (refuses if the name exists):
    python foundry-bridge/make_scene_s14.py --name "Ropewalk and Signal Loft" --model "foundry-3d/out/Act 2 Road to Bridgehollow/Ossuary Exchange/ossuary_ropewalk.glb"
