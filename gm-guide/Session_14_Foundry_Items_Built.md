# SESSION 14: FOUNDRY QUEST ITEMS BUILT
*Built 2026-11-09 by `foundry-json/session14_items.py` from `Session_14_Foundry_Build_Checklist.md` (Optional quest items) and `Session_14_Cladis_Return_Conspiracy.md` (T1 to T6, 7.5 to 7.9). World `new-campaign-2026`, Foundry 14.360, dnd5e 5.3.1. Every row was read back through the bridge after the write (name, type, folder, icon, description, quantity, weight, price, ownership all match the script).*

**Folder:** new Item folder **Session 14: The Thaw** (`Folder.GrEj1VYujdWrL3kw`), made *inside* the existing **Quest Items (Side Quests)** folder (`Folder.yg6qh9wrlg1txdMu`, which holds the Part 6 Ossuary quest items). No top-level folder was added. The world had no other Ossuary item folder.

**Shape:** the same as the Part 6 quest items (`Rune Slip Signed 'Q.'`, `Capsule: 'Drop off at the usual time.'`): type `loot`, `system.type.value` gear, no activities, no uses or charges, rarity blank, `ownership.default` 0 (GM only until handed out), `source.custom` "Varrenmoor DM Guide, Part 7 (Session 14)". Icons are core Foundry icons (each path checked on Vega's install). Re-runs are safe: items are upserted by `flags.varrenmoor.pipelineId = item:ossuary:s14:<id>`, the folder by `folder:ossuary:s14:items`.

**Descriptions:** the player text first (the checklist's exact wording where it gives one), then a **GM note** in a Foundry secret block. Foundry shows secret blocks to the GM **and to whoever owns the copy**, so a player who holds an item can read its GM note. The notes say only who gives it, which task uses it and the DCs; the session's secrets (who V. is, the Goddess's name, which bars are tainted) stay in the actors' GM features and in this guide. Delete the secret block from a player's copy if you want it clean.

| Item | UUID | Folder | Type | Who has it / where found | Craft task | Notes |
|---|---|---|---|---|---|---|
| Copied Custody Page | `Item.Q9FnFRBepH00DgAJ` | Session 14: The Thaw | loot | Sabeline shows it at Table Seven (Scene 3, Clue E), or Pringus finds the line in an audit | T5 (custody record) | Checklist text. Sabeline's sheet already has a "Copied Open-Claim Page" (same text): use one or the other. |
| Outstanding Intake Tag | `Item.TvO6PSaevTF8ybhm` | Session 14: The Thaw | loot | Passage under the Cladis memorial (History DC 12). No PC sheet holds Session 12 intake tags (checked live), so it was built | T5 (the third record) | Checklist text. Rite of the Remaining Bone shows its claim; present to Pringus for the audit (public; Tallis reads it). |
| Mottle's Receipt (Room 208) | `Item.jvhp5PmkltObTsoT` | Session 14: The Thaw | loot | Mottle's ledger, Scene 1 (Clue B) | none (clue; with Europa's frost, Pell Insight DC 13) | Checklist text. |
| Capsule: Bell Silent | `Item.hJvJQTS8z23RfpgL` | Session 14: The Thaw | loot | Drops into the dusty terminal when the cold door opens (Scene 7, Clue H); Pell hands it over if the party refuses | T6 result | Checklist text. Reuses the existing 3D prop `Items/item_capsule.glb`. The Part 6 capsule ("Drop off at the usual time.", `Item.351lv0IQT7FCCbav`) already existed and was not touched. |
| Iron Bars (Haddo's Stock) | `Item.EaV0mFPhCenNsWLn` | Session 14: The Thaw | loot (qty 4) | Brokka's forge, anvil bench (from Haddo's stock) | T2 (Analyze DC 12 sorts them) | 2 lb and 5 sp each. One item, quantity 4, identical-looking; the bar results are in T2 and Haddo's Lore Reference, not on the item. Haddo's sheet also lists "Iron Bar Stock". |
| Iron Rune-Wire | `Item.nQNeP57KwY7yJzds` | Session 14: The Thaw | loot | Made at Brokka's forge (smith's tools DC 12) | T2 product; T1 material; T6 strand | 1 lb. |
| Jar of Gorge Frost | `Item.SFmyGizMEOqqZAd6` | Session 14: The Thaw | loot | Pell (workbench by the cold door) | T2 (frost match DC 14, one Rime dose) | Same player text as the jar on Pell's sheet: use one or the other. Also the slow sinker. |
| Rime Dose (Gorge Frost) | `Item.XrOSODrIH9ZGR8Wh` | Session 14: The Thaw | loot | Made by Dale (Extract Dose) from the jar | T2 (Apply Essence to the braid: 24 h preservation); T3 survival | Dale's Essencecrafting sheet governs it; the item adds no mechanics. See "Source conflict" below. |
| Burial Linen Strand (30 ft) | `Item.IkJ1VJE56oUq4nuw` | Session 14: The Thaw | loot | Ysolde's counter (burial linen 5 sp a yard; 10 yards = 5 gp) | T6 strand | 1 lb. |
| Living Fungal Strand (30 ft) | `Item.iKG6YEisH2Zh5Cue` | Session 14: The Thaw | loot | Grown at Ysolde's from the culture case (Quickening DC 13) | T3 product; T6 strand | 1 lb. The culture case stays at the near knot (scene object, not an item). |
| Braided Line (30 ft) | `Item.crM4xJIgeXkKqhMr` | Session 14: The Thaw | loot | Haddo's ropewalk; coiled on the workbench by the cold door (Scene 7) | T6 (braid DC 12, test pull DC 12) | Checklist text. 5 lb. The party carries the far end out. |
| Anchor Rune-Stone (Cold Door) | `Item.NubeJgP1nLNnVYxf` | Session 14: The Thaw | loot | Fixture in the cold door's right-hand jamb (map object `Anchor_Stone`) | T1 (Read Inscription DC 13, Repair Line x2 DC 14) | GM reference card, not a portable item; keep it off player sheets. |
| Seized Bell Clapper | `Item.94ZQFARDn0M6h6gY` | Session 14: The Thaw | loot | **Session 15:** Bridgehollow Customs House, held by the Iron Bailiffs | The far knot (Bell knock at the camp) | 8 lb. Built now because the capsule points at it. |
| Irregular-Transfer Permit | `Item.mYZfSMY0TDYVe0lI` | Session 14: The Thaw | loot | Scene 5, only if won (Persuasion DC 17 with the audit, or Pringus speaks) | T5 follow-on | Makes the later return legal. A delay or a lie does not earn it. |

## Not built, on purpose
- **Stolen Shard frost note:** not an item (checklist). The Stolen Shard (`Item.iRYnqNYFyvLImBB4`) was not edited; narrate LAKKAR, LADY OF ETERNAL HUNGER in Scene 7.
- **The camp bell (clapper missing):** a stave church bell at the Eirwitch camp, not something the party carries; it belongs to the camp scene (Session 15).
- **Nan's Signal Bell, Signal Flags, Speaking-Trumpet:** already loot on Nan Gristle's sheet; lend the bell from there for T6.
- **Pell's old letters / older capsules ("Bailiffs took the bell's tongue"):** already on Pell's sheet as "Old Letters From the Far Side" (EARN).
- **The vessel, the vessel linen, the culture case:** scene objects at Ysolde's house (players work on them, they do not carry them).
- **Tallis's Notice of Irregularity:** only appears if he posts (7.6); not built.
- **NPC inventories:** no items were added to any actor. The six Session 14 NPCs already carry the stock the spec lists.

## Source conflict to settle
- **How many Rime doses:** Pell's spec says the jar yields **1** dose and is then empty; 7.9 says Dale **keeps one extra** dose as a reward. The item is quantity 1. If you rule two (one for the braid, one kept), set the Rime Dose quantity to 2.

## Not done
- No 3D props except the capsule (it reuses `item_capsule.glb`). No new `.glb` was made for the other thirteen.
