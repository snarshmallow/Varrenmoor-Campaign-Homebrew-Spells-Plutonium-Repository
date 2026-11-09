# SESSION 14: FOUNDRY SCENES SPEC
*Companion to `Session_14_Cladis_Return_Conspiracy.md` (Part 7). Lists the scenes Session 14 needs, which existing ones to reuse, and the new ones to build. The Eirwitch Camp scene is being built separately and is not specified here.*

**Folder for new scenes:** Foundry scene folder **Act 2 > The Ossuary Exchange > Session 14** (a new sub-folder inside the existing "The Ossuary Exchange" folder). Do not duplicate any existing scene.

**Conventions (from the existing Ossuary builds):** 5-ft grid; 100 px = 1.524 m = 5 ft; 3D Canvas tiles are centred and scenes use rotation 180 (north up); no NPC geometry, no emissive materials, lights as Foundry AmbientLights only and **few** of them; doors are real glTF door nodes (extras isDoor/doorId); named, selectable interaction objects. Coordinates below are in feet from the north-west corner, x east, y south.

---

## A. EXISTING SCENES TO REUSE (no rebuild)
| Existing scene | Used in | What to add (props or notes only, optional) |
|---|---|---|
| **Ossuary Exchange Upstairs** | Scene 1: Europa wakes in **Room 208** | Nothing required. Optional: a frost-rimed blanket prop on the 208 bed. |
| **Ossuary Exchange Tavern** | Scene 1 breakfast; Scene 3 **Table Seven** (corner table by the hearth) | Optional: a scene note pinned at Table Seven ("knock four slow"). |
| **Quill's Rune Workshop** | Scene 2: the slip and the map | Nothing. |
| **Brokka's Forge** | Scene 4, T2: the wire | Optional loot: four iron bars (one clean, two Hunger-tainted, one Stone) on the anvil bench. |
| **The Clerk's Room** | Scene 6, T5: Pringus's Reconciliation Audit | Nothing. |
| **Pimm's Clinic** | Only if Betsy fetches Pimm | Nothing. |
| **Ossuary Exchange Conveyor S...** (shafts + annex) | Route to the dusty terminal (south dogleg) | The new terminal scene (B3) picks up where the dogleg ends. |
| **Ossuary Exchange Market** | Travel between shops; Nan's loft is visible above the rails | Nothing. |
| **The Hallway** | Sabeline's office door opens off it (flavor only) | Nothing. |
| **Eirwitch Camp (Night)** (other agent) | Session end: where the cold door lets out, and Session 15 | Ask its builder to mark the **west road end** as "Cold door landing". |

---

## B. NEW SCENES

### B1. Harrowgate Restorations **(MUST)**
- **Purpose:** Scene 4: T3 (Violet's living strand) and T4 (Betsy's vessel). NPC: Ysolde Harrowgate (Pimm optional).
- **Size:** 50 x 40 ft (10 x 8 squares). Indoor, one floor.
- **Layout:**
  - **Front room (south, 50 x 15 ft):** street door at (25, 40). Counter across the room at y = 30 with linen rolls, flasks of distilled water, a ledger, a bell. Two waiting benches. Licence certificate framed on the wall.
  - **Work room (north-west, 25 x 25 ft):** door from the front room at (12, 25). Washbasin, a long steel-topped table, instrument cabinet, a **glass case holding the mycelium culture** on a stand at (6, 6) (Violet's T3 object).
  - **Vessel room (north-east, 25 x 25 ft):** door from the work room at (25, 12) with a lock (Ysolde has the key). A **covered vessel on a raised table** at (37, 12) under white linen: a lawful construct frame with early grown tissue (keep it covered; no gore). A brazier stand (unlit), a rack of boundary-rune tiles, a small slate with "Stable / Strained" chalk marks (T4 tracker).
- **Interaction objects (named):** `Mycelium_Culture_Case`, `Vessel_Table`, `Vessel_Linen`, `Linen_Rolls`, `Distilled_Water_Flasks`, `Rune_Tile_Rack`, `Counter_Ledger`, `Vessel_Room_Door` (lockable).
- **Lighting:** day or evening, warm. 3 lights: front counter lamp (warm #ffc78a), work-room lamp over the table (neutral #fff2d8), a dim cool lamp in the vessel room (#cfe6ff).
- **Mood / audio:** clean, quiet, smell of salt and lye; dripping tap; distant trolley rumble.
- **Hidden:** nothing secret; the vessel room is simply locked. A drawer in the counter (Investigation DC 12) holds Wren's file **[SUGGESTED]**.
- **NPC positions:** Ysolde at the work table (12, 12); Pimm (if called) by the culture case.
- **Connects to:** Ossuary Exchange Market (street door).
- **Build:** interior-only scene with `foundry-3d/generators/` in the pattern of `ossuary_clinic.py` / `ossuary_warehouse.py` (interior GLB + `.scene.json`, real doors). Alternative: illustrator blank place 60 x 50 ft + `building_edit` with an interior. Reuse the clinic's materials.

### B2. The Night Custody Office **(MUST)**
- **Purpose:** Scene 5 (Inspector Tallis) and Scene 3B (Sabeline's approach if Quill's test fails); where the open-claim page lives. NPCs: Sabeline Nock, Corvin Tallis, Pringus (visiting).
- **Size:** 40 x 30 ft (8 x 6 squares). Indoor.
- **Layout:**
  - Door from The Hallway at (20, 30) (south wall).
  - **Ledger stacks** along the north and west walls: tall shelves of numbered custody volumes, a rolling ladder on the north wall.
  - **Sabeline's desk** at (20, 10): green-shaded lamp, open ledger, pen tray, brass knock-block, tea tin and kettle.
  - **Copy table** at (32, 18): two copied volumes side by side (the open claim in each, copied forward).
  - **Visitor chairs** (two) facing the desk; a **notice board** by the door with blank notice forms (Tallis's).
  - A **night desk bell** on the desk (Sabeline's Call the Desk).
- **Interaction objects:** `Sabeline_Desk`, `Open_Claim_Ledger`, `Copy_Table`, `Custody_Shelves`, `Rolling_Ladder`, `Notice_Board`, `Night_Desk_Bell`, `Office_Door`.
- **Lighting:** night. 2 lights: the desk lamp (green-shaded, warm #ffd9a0) and a dim corridor spill by the door (#9fb7d6).
- **Mood / audio:** paper rustle, pen scratch, a clock; very quiet.
- **Hidden:** the volume holding the open claim is shelved one place out of order (Investigation DC 13 to find it without Sabeline). Behind it, a folded **copied custody page** (the Thaw's copy).
- **NPC positions:** Sabeline at the desk; Tallis enters at the door and measures it with his chain; Pringus, if present, at the copy table.
- **Connects to:** The Hallway.
- **Build:** interior-only scene via `foundry-3d/generators/` (pattern of the clerk-room/rune-shop scripts; reuse the clerk room's shelves and ledger props from `Ossuary_Exchange_Individual_Assets_v1`). Small; under 30 objects.

### B3. The Dusty Terminal and the Cold Door **(MUST)**
- **Purpose:** Scene 7 (the usual time, T1 the anchor, T6 the test pull, the capsule, the exit). NPCs: Pell Ostry, Quill, Sabeline; Tallis possibly.
- **Size:** 45 x 30 ft (9 x 6 squares) interior, plus a **10 x 30 ft exterior strip** beyond the cold door (snowy mountain road edge). Total 55 x 30 ft.
- **Layout:**
  - **Entry** at (0, 15) on the west wall: continues the shafts' south dogleg (match the Conveyor scene's corridor width, 1.6 m).
  - **The dusty terminal** at (12, 6): brass pneumatic receiver with a capsule plinth, dust, a lever, pipes up into the ceiling. Single clunk when a capsule lands.
  - **Pell's rail:** a short iron rail along the north wall from x = 5 to x = 30, with his counterweighted chair.
  - **The cold door** in the east wall at (45, 15): an old iron service door, 5 ft wide, with a carved stone frame. **Threshold glyph on the lintel** (for Stellan to study). The **anchor stone** set in the right-hand jamb at waist height (T1's object).
  - **A workbench** at (30, 24): Haddo's coiled braided line, Pell's **jar of gorge frost**, Quill's chisels.
  - **Beyond the door (exterior strip, x 45 to 55):** packed snow, the edge of a dark pine road, a few trees, night sky. Visible only when the door is open.
- **Interaction objects:** `Dusty_Terminal`, `Capsule_Plinth`, `Terminal_Lever`, `Pell_Rail`, `Cold_Door` (real door node), `Anchor_Stone`, `Lintel_Threshold_Glyph`, `Workbench`, `Braided_Line_Coil`, `Gorge_Frost_Jar`.
- **Lighting:** night. 3 lights: a dim warm lamp over the terminal (#ffc78a), a faint cool glow on the anchor stone (#9fd0ff, small radius; turn it on only after T1 succeeds), cold blue moonlight outside the door (#a8c4ff, exterior strip only). No other lights.
- **Mood / audio:** dust, a slow drip, pipes ticking. When the door opens: wind, pine smell, a distant bell (only on the real night). Suggest a short wind ambience on a sound object at the door.
- **Hidden:** the anchor stone looks like ordinary masonry until read (Perception DC 13 or Read Inscription). The capsule plinth has a cubby with old capsules (EARN, Pell's letters).
- **NPC positions:** Pell in his chair on the rail by the terminal; Quill at the anchor stone; Sabeline by the workbench.
- **Connects to:** Ossuary Exchange Conveyor S... (west entry); the Eirwitch Camp (Night) scene (through the cold door, west road end).
- **Build:** interior scene via `foundry-3d/generators/` (extend the style of `ossuary_shafts.py`; reuse its pipes and terminal parts), with the exterior strip as a separate tile group so it can be hidden. The cold door must be a real door node so it can open on cue.

### B4. Ropewalk and Signal Loft **(MUST, or fold into the Market scene)**
- **Purpose:** Scene 4 (braid prep, Nan's gossip), T6 braid, borrowing Nan's signal bell. NPCs: Haddo Rook, Nan Gristle.
- **Size:** 80 x 30 ft (16 x 6 squares). Indoor, long and narrow, two levels (ground and a loft along the north side).
- **Layout:**
  - **Ground floor:** a long ropewalk (the floor of a rope-maker's shop) running east-west, with a **twisting wheel** at the west end (5, 15) and a **traveller sledge** on rails down the middle. Rope coils, tar buckets, a bench of iron bar stock at (70, 22), Haddo's workbench at (60, 8).
  - **Signal loft:** a 10-ft-deep timber gallery along the north wall at the east end (x 50 to 80), reached by a ladder at (50, 10). **Nan's chair, the signal bell on a post** at (72, 4), signal flags, a window onto the trolley rails.
  - Big double doors at (40, 30) to the market.
- **Interaction objects:** `Twisting_Wheel`, `Traveller_Sledge`, `Iron_Bar_Bench` (four bars), `Haddo_Workbench`, `Loft_Ladder`, `Signal_Bell` (portable), `Signal_Window`, `Market_Doors`.
- **Lighting:** day/evening. 3 lights: two warm work lamps over the ropewalk (#ffc78a), one by Nan's window (#ffe6b8).
- **Mood / audio:** creak of twisting rope, tar smell, trolley baskets rattling past the window, Nan shouting through her trumpet.
- **Hidden:** nothing.
- **NPC positions:** Haddo at the twisting wheel or workbench; Nan in the loft.
- **Connects to:** Ossuary Exchange Market.
- **Build:** interior via `foundry-3d/generators/` (simple long hall + gallery), or illustrator blank place 90 x 40 ft + `building_edit` with an interior. **If time is short:** skip it and run Haddo and Nan in the Market scene beneath the rails (Nan's loft is a trolley pylon platform).

### B5. Cold Door Landing, Mountain Road (Night) **(NICE)**
- **Purpose:** the last beat of Session 14 (stepping through) if the Eirwitch Camp scene does not cover the road end. Otherwise skip and use the camp scene's west road end.
- **Size:** 60 x 40 ft (12 x 8 squares). Outdoor, night, snow.
- **Layout:** a rock face on the west edge with the **outside of the cold door** set into it (a plain iron door in a stone frame, no handle on this side); a snowy dirt road running east up the slope; pines both sides; an orange glow of a distant fire to the north-east (a light, not a model); a cairn by the door with a bell carved on its top stone (the courier's mark).
- **Interaction objects:** `Cold_Door_Outside`, `Courier_Cairn`, `Road`.
- **Lighting:** 2 lights: moonlight (#a8c4ff), the faint distant fire glow at the edge (#ff9a4a, large dim).
- **Mood / audio:** wind, creaking pines, very quiet.
- **Connects to:** B3 (the cold door); Eirwitch Camp (Night) (road east).
- **Build:** illustrator blank place 60 x 40 ft with terrain + foliage (reuse the Eirwitch camp's foliage params), or a cropped region of the camp place. Do not duplicate the camp itself.

---

## C. PRIORITY SUMMARY
| Scene | Priority | Folder |
|---|---|---|
| B1 Harrowgate Restorations | Must | The Ossuary Exchange > Session 14 |
| B2 The Night Custody Office | Must | The Ossuary Exchange > Session 14 |
| B3 The Dusty Terminal and the Cold Door | Must | The Ossuary Exchange > Session 14 |
| B4 Ropewalk and Signal Loft | Must (or fold into Market) | The Ossuary Exchange > Session 14 |
| B5 Cold Door Landing | Nice (skip if the camp scene covers it) | The Ossuary Exchange > Session 14 |
