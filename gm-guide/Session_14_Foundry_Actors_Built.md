# SESSION 14: FOUNDRY ACTORS BUILT
*Built 2026-11-09 from `Session_14_New_NPCs_Spec.md` and `Session_14_Foundry_Build_Checklist.md` by `foundry-json/session14_npcs.py`. World `new-campaign-2026`, Foundry 14.360, dnd5e 5.3.1. Every row below was read back through the bridge after the write.*

**Folder:** all six are in the existing actor folder **Ossuary Exchange** (`Folder.ae9wu7eMHFRxi43Q`), the same folder as Quill, Mottle, Brokka, Pimm, Pringus and Mavis. No new folder was made (the checklist's "Ossuary" folder is this one).

| Actor | UUID | Folder | CR | HP / AC | Items (feat / weapon / loot) | Status | Notes |
|---|---|---|---|---|---|---|---|
| Sabeline Nock, Night Custody Clerk | `Actor.xzXrPpS2eDUMKfMl` | Ossuary Exchange | 1/4 | 13 (3d8) / 12 | 15 (8 / 1 / 6) | Built, verified | Undead (sentient skeleton), darkvision 60, dv bludgeoning, di poison, ci exhaustion/poisoned. Saves Int, Wis. History, Insight, Investigation. Calligrapher's supplies. Call the Desk 1/day. Neutral. |
| Ysolde Harrowgate, Licensed Restorer | `Actor.YcOArVHpAcZ2qu6y` | Ossuary Exchange | 1/2 | 22 (4d8+4) / 11 | 16 (10 / 1 / 5) | Built, verified | Medicine expertise, Nature, Insight. Save Wis. Herbalism kit. Restorer's Kit 3/long rest (heal in the text, no heal activity). Steady Hands reaction 1/long rest. Friendly. |
| Haddo Rook, Trolley Ropewright | `Actor.eFEgfkVNMfVA1MIe` | Ossuary Exchange | 1/2 | 32 (5d8+10) / 12 | 16 (7 / 2 / 7) | Built, verified | Climb 20. Athletics, Sleight of Hand. Weaver's tools. Multiattack, Rope Hook, Lasso (no damage; restrained, escape DC 13 in the text). Neutral. |
| Pell Ostry, Keeper of the Dusty Terminal | `Actor.jBuofUnpwjn6zr1a` | Ossuary Exchange | 1/8 | 9 (2d8) / 11 | 13 (7 / 1 / 5) | Built, verified | Undead (sentient skeleton), darkvision 60, skeleton traits. Walk 10 (40 ft on his rail is in the biography and the GM Reference). Perception, Stealth. Tinker's tools. Loot includes Jar of Gorge Frost (player text only). Neutral. |
| Corvin Tallis, Inspector of Thresholds | `Actor.H0xvdNNVtKatA37D` | Ossuary Exchange | 1 | 27 (5d8+5) / 13 | 14 (8 / 1 / 5) | Built, verified | Insight expertise, Investigation, Perception. Saves Int, Wis. Cartographer's tools. Notice of Irregularity 1/day. Measuring Chain reach 10. Neutral, not hostile. |
| Nan Gristle, Trolley Signalwoman | `Actor.2FVjx5UYlGX9Wx8J` | Ossuary Exchange | 0 | 11 (2d8+2) / 10 | 11 (5 / 1 / 5) | Built, verified | Half-orc, darkvision 60, Common and Orc. Perception, Persuasion. Signal Bell and Trumpet 1/long rest. Signal Flag Swat flat 1. Friendly. |
| Quillibus "Quill" Scratch (existing) | `Actor.PsjbmI1M64DINQmV` | Ossuary Exchange (unchanged) | 1/2 (unchanged) | unchanged | 6 → 7 | One feature added | Added `Lore Reference: Cladis's Trail` (`...Item.tNGqJySm2kE3FOgO`, no activities). Backups `foundry-3d/ai/characters/session14/quill_before.json` and `quill_after.json`; a diff shows every other field and the six old items unchanged. |
| Venfyura (existing canon NPC) | none | none | none | none | none | **Not in the world, not built** | No actor, item or journal entry in the live world mentions "Venfyura" (actor/item name search, and full-text search of all 7 journal entries). Per the checklist, no stat block was invented. Raise with the GM before Session 15. |

## Common to all six
- `type: npc`, img and token texture `icons/svg/mystery-man.svg` (placeholder), `source.custom` "Varrenmoor DM Guide, Part 7 (Session 14)", habitat "Ossuary Exchange — Lower Ring", ideal/bond/flaw from the checklist.
- NPC features are feat items with no activities (GM Reference / Lore Reference / Side Quest / Training Reference / Merchant Reference / Lil' Apostrophe), text from the spec with the [COMMON]/[ASK]/[EARN]/[SECRET] tags kept. Inventory and stock are simple loot items (stock prices on Ysolde's and Haddo's).
- Biography: one summary paragraph plus "GM notes (Part 7)" with the key DCs; Thaw membership marked [SECRET]; `biography.public` empty.
- Prototype token: name without the title, 1x1, `actorLink: false`, disposition as the checklist, vision on (darkvision 60 for the skeletons and Nan, basic for the rest), as on the existing Ossuary NPCs.
- Upserted by `flags.varrenmoor.pipelineId = npc:ossuary:s14:<id>`, so re-running `python foundry-json/session14_npcs.py --push` updates rather than duplicates.
- Bridge `audit_activities`: 0 bad activity ids in the world after the build.

## Not done / still to do
- **3D token models:** `prototypeToken.flags.levels-3d-preview.model3d` is deliberately **unset** (no `token_<id>.glb` exists yet; a missing path would break the 3D token). When models exist, set it to `assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens/token_<id>.glb` (ids: sabeline_nock, ysolde_harrowgate, haddo_rook, pell_ostry, corvin_tallis, nan_gristle).
- **Portraits:** not generated (the GPU was busy with another job). The art prompts are in the spec; `foundry-3d/ai/characters.py` is the generator used for the other quest NPCs.
- **Token display name:** the checklist asks for `displayName: 30` (hover). This world sets it to 20 (owner hover) on create and on update, like every other NPC; it stayed at 20.
- **Schema notes:** weapon damage leaves the ability modifier to dnd5e (for example Rope Hook = 1d6 + Str). Pen Jab and Signal Flag Swat use a custom flat formula "1"; check in play that dnd5e does not add the modifier on top.
- Optional Session 14 quest items (folder "Quest Items (Session 14)") were not built in this pass. **Update:** they are now built as 14 world items in the Item folder `Quest Items (Side Quests) / Session 14: The Thaw`; see `Session_14_Foundry_Items_Built.md`. No actor was changed for them.
