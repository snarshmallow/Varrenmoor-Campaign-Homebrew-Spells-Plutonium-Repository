# Ossuary Exchange: Grand Layout

*Where every Ossuary scene sits on one plan. Picture: `illustrator/out/ossuary_grand_layout.png`. Illustrator place: `ossuary_exchange_grand`.*

**How to open it in Illustrator:** panel > Places tab > pick **Ossuary Exchange: Grand Layout** (`ossuary_exchange_grand`) > *Open selected in Illustrator*. Every footprint is a building named exactly like its Foundry scene (id `osc_<slug>`); landmarks are `lm_<slug>`. Each footprint's notes say existing/new, what it connects to, and the source of its position.

**Rebuild after scenes change:** `python illustrator/generators/ossuary_grand.py` (reads the live Foundry scene list read-only; `--offline` uses the built-in table; `--dry-run` prints positions only). It rewrites the footprints, streets and districts and re-renders the PNG.

**Reading the plan.** North is up. Feet are measured from **the Exchange junction** (the centre of the market plaza), x east, y south. Grey = existing scene, gold = new Session 14 scene, dashed lilac = landmark with no scene of its own. Footprints of existing scenes are their **scene canvas** size (scene px / 100 x 5 ft), which includes empty margin around the 3D model, so they look bigger than the rooms really are. The shafts, the annex and the dusty terminal are **below ground**; they are drawn south of the tavern so they do not hide it. The cold door is a **threshold**: the gap between the terminal and the Cold Door Landing on the plan is symbolic, not walking distance (the landing is on a mountain road above Bridgehollow). Every position marked **APPROXIMATE** is my placement where canon gives no direction.

## Scenes

| Scene (Foundry name) | Status | Position from the junction | Connects to | Source of the position |
|---|---|---|---|---|
| Ossuary Exchange Market | existing | 0 (the junction): 150-ft circular plaza | every shop door; Eastern Gate (E); Arrival Portal (S); overhead trolley hub | Handoff (150-ft circular patio) + market plan |
| Brokka's Forge | existing | NE, 146 ft E, 123 ft N | Market (street door) | Market plan angle 30-50 deg (`ossuary_market_new.py`) |
| Pimm's Clinic | existing | NW, 124 ft W, 148 ft N | Market (street door) | Market plan angle 120-140 deg |
| Quill's Rune Workshop | existing | W, 172 ft W | Market (street door) | Market plan angle 170-190 deg |
| Ossuary Exchange Tavern (Mottle's Mugs) | existing | S-SE, 63 ft E, 172 ft S | Market; west door to the Exchange hallway; bar drop-tube down to the shafts; stair up | Market plan angle 280-300 deg; `ossuary_tavern.py` (hallway door on the west wall) |
| Ossuary Exchange Upstairs | existing | the floor above the tavern (tag drawn just east of it) | Tavern stair; rooms 201-208, Room 208 | GM reference (inn upstairs rooms) |
| Lower Market Warehouse | existing | E-SE, 188 ft E, 68 ft S | Market; the amended warehouse door | Market plan angle 330-350 deg |
| The Hallway | existing | SW, 175 ft W, 285 ft S (30 x 150 ft, E-W) | west: double doors to the Clerk's Room; east: exit to the Arrival Portal; office doors incl. Night Custody Office | Handoff (30 x 150 ft, double doors left, exit right). **Orientation and position APPROXIMATE** |
| The Clerk's Room | existing | SW, 315 ft W, 285 ft S | The Hallway (double doors); FEMORAL INTAKE (Pringus) | Handoff (intake plaque) + the hallway's double doors. **Side APPROXIMATE** |
| Ossuary Exchange Conveyor Shafts + Annex | existing | S, 93 ft E, 370 ft S (below ground) | Tavern bar drop-tube; Lost Property annex; south dogleg to the terminal | GM reference Quest 2 + Session 14 scenes spec. **APPROXIMATE** (under the tavern) |
| Estate exterior | existing | E, 610 ft E, 40 ft N | Eastern Gate by Mavis's Road | Canon: beyond the eastern gate, outside Exchange jurisdiction. **Distance APPROXIMATE** |
| Estate *interior | existing | inside the estate (house 80 x 60 ft) | Estate exterior | Handoff (main block 16 x 12 grids) |
| Harrowgate Restorations | **new** | W-NW, 140 ft W, 74 ft N | Market (street door) | Spec: connects to the Market. **Angle APPROXIMATE** (between the clinic and the rune shop) |
| Ropewalk and Signal Loft | **new** | S-SW, 47 ft W, 146 ft S | Market; signal window onto the trolley rails | Spec: connects to the Market. **Angle APPROXIMATE** |
| Night Custody Office | **new** | SW, 195 ft W, 252 ft S (north side of the hallway) | The Hallway (door in its south wall) | Spec B2 (door in the office's south wall). **Spot along the hall APPROXIMATE** |
| Dusty Terminal and the Cold Door | **new** | S, 133 ft E, 480 ft S (below ground) | West: shafts' south dogleg; east wall: the cold door | Spec B3 |
| Cold Door Landing | **new** | beyond the cold door (drawn 490 ft E, 430 ft S) | The cold door (threshold); Mountain Road east to the Eirwitch Camp | Spec B5. **Map distance symbolic, APPROXIMATE** |
| Ossuary Market- OLD BACKUP | ignored | not drawn | | |

## Landmarks (no scene of their own)

| Landmark | Position from the junction | Source |
|---|---|---|
| Eastern Gate | E, 107 ft (east edge of the plaza) | Market plan (gate 0 deg); handoff eastern exit (road to Mavis) |
| Arrival Portal | S, 95 ft | Market plan (arrival 270 deg, "Exchange hallway") |
| Exchange Guildhall | N, 152 ft | Market plan (70-100 deg) |
| Post Office | SW, 135 ft W, 88 ft S | Market plan (210-230 deg). Foundry's "Postal Office Interior" may be this; not confirmed |
| Cladis Memorial | SW, 232 ft W, 319 ft S | Canon: in the Exchange. **Spot APPROXIMATE** (near intake) |
| Intake Hall | SW, 315 ft W, 360 ft S | Canon: Ossuary intake with Pringus. **APPROXIMATE** |
| Three-Ledger Offices | SW, 135 ft W, 330 ft S | Canon: intake ledger, custody ledger, physical tag. **APPROXIMATE** |
| The Cold Door | east wall of the Dusty Terminal | Spec B3 |
| Eirwitch Camp (Night) | east end of the Mountain Road (separate place `eirwitch_camp`) | Spec A. **APPROXIMATE** |

## Ways

- **Market Ring**: the street in front of every shop door.
- **Mavis's Road**: Eastern Gate east to the estate.
- **Arrival Passage**: Arrival Portal south to the hallway's east exit (**APPROXIMATE**). **Tavern West Door**: the tavern's door to the hallway.
- **Overhead bone trolley line** (red dashes): hub over the plaza, spokes to the hallway and the north-west, and a line down past the shafts to the dusty terminal (the last trolley of the night passes the cold door). **Routes APPROXIMATE**.
- **Pneumatic tube run** (blue dots): from the tavern wall (Mottle's rumour 3) to the dusty terminal. **APPROXIMATE**.
- **Shafts South Dogleg**: shafts to the terminal's west entry (spec B3).
- **Cold Door Threshold** (light blue dashes): one minute at the usual time; then the **Mountain Road** east up the slope to the Eirwitch camp.

## Sources

Foundry scene data (read-only: names, sizes, grid, tokens; none of the Ossuary scenes have background images, walls or map notes, so they give sizes but no directions); `foundry-3d/generators/ossuary_market_new.py` (shop angles around the plaza), `ossuary_tavern.py`, `ossuary_forge.py`, `ossuary_clinic.py`, `ossuary_rune_shop.py` (street doors face south onto the plaza); `Varrenmoor_Campaign_Full_Handoff.md` (grand hall 30 x 150 ft, eastern exit to Mavis's road, estate plan, 150-ft plaza); `gm-guide/Varrenmoor_NPC_Dialogue_GM_Reference.md` (Lower market, memorial, shafts, annex, upstairs rooms); `gm-guide/Session_14_Scenes_Spec.md` and `Session_14_Cladis_Return_Conspiracy.md` (new scenes, sizes and connections).

## Places for each existing scene

Imported read-only from Foundry (`foundry_push.py import-scene --include tokens`): `ossuary_existing_brokkas_forge`, `ossuary_existing_lower_market_warehouse`, `ossuary_existing_conveyor_shafts`, `ossuary_existing_market`, `ossuary_existing_tavern`, `ossuary_existing_upstairs`, `ossuary_existing_pimms_clinic`, `ossuary_existing_quills_workshop`, `ossuary_existing_clerks_room`, `ossuary_existing_hallway`, `ossuary_existing_estate_exterior`, `ossuary_existing_estate_interior`. They are 3D Canvas scenes with no 2D background, so each place is a blank sheet at the scene's size with its grid and token dots (no underlay). The two estate scenes list a background (`assets/3graveyards-heightmap.webp`, a heightmap) that could not be fetched.
