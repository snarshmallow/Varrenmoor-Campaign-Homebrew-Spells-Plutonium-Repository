# SESSION 14: FOUNDRY BUILD CHECKLIST (NPC ACTORS)
*For the agent building the actors. Source of truth for content: `Session_14_New_NPCs_Spec.md`. Scenes are in `Session_14_Scenes_Spec.md`.*

## General (applies to every actor)
- **Actor folder:** `Ossuary` (create it if missing; the user asked for "the Ossuary folder"). If the world already uses an actor folder named "The Ossuary Exchange", put a subfolder `Ossuary` inside it rather than creating a duplicate top-level folder, and say which you did.
- **Type:** `npc`. **img:** `icons/svg/mystery-man.svg` (placeholder). **prototypeToken.texture.src:** same placeholder.
- **3D token model path (placeholder until models exist):** `assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens/token_<id>.glb` in `prototypeToken.flags.levels-3d-preview.model3d`, scale 1.0.
- **Builder:** `foundry-json/fvtt.py` helpers (`npc()`, `feat()`, `utility()`, `weapon()`, `save()`), same pattern as `foundry-json/quest_content.py`. Templates clone Mottle/Mavis exports from the Vega share, so the shape matches this world's dnd5e. Item and Activity `_id`s are 16-character hex (via `hid()`); the bridge audits that.
- **source.custom:** `Varrenmoor DM Guide, Part 7 (Session 14)`.
- **NPC Features:** feat items with **no activities**, description HTML from the spec sections (snapshot, voice, sample dialogue with tags, lore, quest, stock). Keep the [ASK]/[EARN] tags in the text.
- **Biography (`system.details.biography.value`):** 1 paragraph summary + 1 paragraph "GM notes (Part 7)" with the key DCs. Mark Thaw membership as GM-only (biography `public` stays empty).
- **prototypeToken:** `actorLink: false`, `displayName: 30`, disposition as listed, width/height 1.
- **ideal / bond / flaw** (`system.details`): fill from the lines below.
- **environment:** `Ossuary Exchange — Lower Ring` (match existing).
- **Skeletal NPCs:** `details.type.value: "undead"`, subtype `"sentient skeleton"`, `dv: ["bludgeoning"]`, `di: ["poison"]`, `ci: ["exhaustion", "poisoned"]`, darkvision 60.
- **Do not activate scenes or move any PC items.** No changes to existing actors (Quill etc.).

---

## 1. Sabeline Nock
| Field | Value |
|---|---|
| Actor name | `Sabeline Nock, Night Custody Clerk` |
| id / model | `sabeline_nock` / `token_sabeline_nock.glb` |
| CR / size / type | 0.25 / `med` / undead, `sentient skeleton` |
| alignment | lawful neutral |
| HP / formula / AC | 13 / `3d8` / 12 natural |
| abilities (str..cha) | 8, 12, 10, 16, 14, 11 |
| saves proficient | int, wis |
| skills (value 1) | his, ins, inv |
| movement | walk 30 |
| senses | darkvision 60 |
| traits | dv bludgeoning; di poison; ci exhaustion, poisoned |
| languages | common (custom: "reads old Eirwyn script") |
| tools | calligrapher (`system.tools.calligrapher`: value 1, ability int) |
| disposition | 0 (neutral) |
| ideal / bond / flaw | "Three records must agree." / "The night ledger, and the claim she has copied forward four times." / "Would rather be correct than safe." |

**Items**
1. feat `Copied Forward` (advantage recalling/finding entries she copied).
2. feat `Contracted Staff` (cannot be bought, sold or claimed; wards protect her).
3. feat `Ledger Hand` (10-minute certified copy of an Exchange page).
4. weapon `Pen Jab` (dex, +3 to hit, 1 piercing, reach 5): `weapon(A, "Pen Jab", html, sort, "dex", 0, 1, "piercing", bonus="1")`.
5. utility `Call the Desk` (action, `uses=(1, "day")`): two custodians arrive in 1d4 rounds, inside thresholds only.
6. feat `GM Reference: Sabeline Nock, Voice and Night Desk`
7. feat `Lore Reference: The Open Claim`
8. feat `Side Quest: The Outstanding Tag`
9. feat `GM Reference: Lil' Apostrophe at the Night Desk`

## 2. Ysolde Harrowgate
| Field | Value |
|---|---|
| Actor name | `Ysolde Harrowgate, Licensed Restorer` |
| id / model | `ysolde_harrowgate` / `token_ysolde_harrowgate.glb` |
| CR / size / type | 0.5 / `med` / humanoid, `human (leased body)` |
| alignment | neutral good |
| HP / formula / AC | 22 / `4d8+4` / 11 |
| abilities | 11, 12, 12, 15, 15, 12 |
| saves proficient | wis |
| skills | med 2 (expertise), nat 1, ins 1 |
| movement | walk 30 |
| senses | none |
| languages | common |
| tools | herb (value 1, wis) |
| disposition | 1 (friendly) |
| ideal / bond / flaw | "Do it properly or don't do it." / "Her restoration house and its receipts." / "Takes on one patient too many." |

**Items**
1. feat `Leased Body`
2. feat `Licensed Restorer`
3. utility `Restorer's Kit` (action, 3/day `lr`: stabilize + 1d4+2 HP; put the heal in the description; a heal activity is optional)
4. weapon `Scalpel` (dex, 1d4+1 slashing, reach 5)
5. utility `Steady Hands` (reaction, 1/day `lr`)
6. feat `GM Reference: Ysolde Harrowgate, Voice and Restoration House`
7. feat `Lore Reference: The Vessel`
8. feat `Training Reference: Choosing a Continuation`
9. feat `Side Quest: A Body That Warms From the Middle`
10. feat `Merchant Reference: Harrowgate's Counter`
11. feat `Lore Reference: Bones's Restoration`

## 3. Haddo Rook
| Field | Value |
|---|---|
| Actor name | `Haddo Rook, Trolley Ropewright` |
| id / model | `haddo_rook` / `token_haddo_rook.glb` |
| CR / size / type | 0.5 / `med` / humanoid, `human (spliced arms)` |
| alignment | neutral |
| HP / formula / AC | 32 / `5d8+10` / 12 |
| abilities | 16, 13, 14, 10, 11, 10 |
| saves proficient | none |
| skills | ath 1, slt 1 |
| movement | walk 30, climb 20 |
| languages | common |
| tools | weaver (value 1, dex) |
| disposition | 0 |
| ideal / bond / flaw | "Rope goes where it's tied." / "His ropewalk and both his arms." / "Buys iron off salvage carts without asking." |

**Items**
1. feat `Two Arms, Two Opinions`
2. feat `Ropewright`
3. utility `Multiattack` (two Rope Hook attacks)
4. weapon `Rope Hook` (str, 1d6+3 bludgeoning, reach 5)
5. save_feat or weapon `Lasso`: ranged weapon (dex, +3, range 15), effect restrained, escape DC 13 in text
6. feat `GM Reference: Haddo Rook, Voice and Ropewalk`
7. feat `Lore Reference: Three Strands`
8. feat `Side Quest: The Fraying Cable`
9. feat `Merchant Reference: Haddo's Stock`

## 4. Pell Ostry
| Field | Value |
|---|---|
| Actor name | `Pell Ostry, Keeper of the Dusty Terminal` |
| id / model | `pell_ostry` / `token_pell_ostry.glb` |
| CR / size / type | 0.125 / `med` / undead, `sentient skeleton` |
| alignment | neutral |
| HP / formula / AC | 9 / `2d8` / 11 |
| abilities | 8, 13, 10, 12, 14, 9 |
| skills | prc 1, ste 1 |
| movement | walk 10 (special in description: 40 ft along his rail) |
| senses | darkvision 60 |
| traits | dv bludgeoning; di poison; ci exhaustion, poisoned |
| languages | common |
| tools | tinker (value 1, int) |
| disposition | 0 |
| ideal / bond / flaw | "Usual time. Never early." / "The people on the other side of his door." / "Keeps other people's secrets better than his own job." |

**Items**
1. feat `Knows the Time`
2. feat `Contracted Staff`
3. feat `Tube Keeper`
4. weapon `Lever Swing` (dex, 1d4+1 bludgeoning, reach 5)
5. feat `GM Reference: Pell Ostry, Voice and Terminal`
6. feat `Lore Reference: The Cold Door`
7. feat `Lore Reference: News From Bridgehollow`
8. feat `Side Quest: The Usual Time`
9. loot item (in actor inventory) `Jar of Gorge Frost` (player-facing: "A stoppered jar of frost that never fully melts." GM text in the feat, not the loot).

## 5. Corvin Tallis
| Field | Value |
|---|---|
| Actor name | `Corvin Tallis, Inspector of Thresholds` |
| id / model | `corvin_tallis` / `token_corvin_tallis.glb` |
| CR / size / type | 1 / `med` / humanoid, `human` |
| alignment | lawful neutral |
| HP / formula / AC | 27 / `5d8+5` / 13 |
| abilities | 10, 14, 12, 14, 16, 12 |
| saves proficient | int, wis |
| skills | ins 2 (expertise), inv 1, prc 1 |
| movement | walk 30 |
| languages | common |
| tools | cartographer (value 1, int) |
| disposition | 0 (neutral; he is NOT hostile) |
| ideal / bond / flaw | "A door that lies is how neutrality ends." / "His black book of openings." / "Cannot leave a discrepancy alone, even when it would be kinder." |

**Items**
1. feat `Reads Doors`
2. feat `Hard to Lie To` (Deception DC 16)
3. feat `Measuring Chain (tool)`
4. utility `Notice of Irregularity` (action, 1/day; charter procedure, not a spell)
5. weapon `Measuring Chain` (dex, 1d4+2 bludgeoning, reach 10; speed −10 ft in text)
6. feat `GM Reference: Corvin Tallis, Voice and Rounds`
7. feat `Lore Reference: What Tallis Knows`
8. feat `Side Quest: Forty-One Minutes`
9. feat `GM Reference: If Tallis Posts`

## 6. Nan Gristle
| Field | Value |
|---|---|
| Actor name | `Nan Gristle, Trolley Signalwoman` |
| id / model | `nan_gristle` / `token_nan_gristle.glb` |
| CR / size / type | 0 / `med` / humanoid, `half-orc` |
| alignment | chaotic good |
| HP / formula / AC | 11 / `2d8+2` / 10 |
| abilities | 13, 9, 12, 10, 13, 12 |
| skills | prc 1, per 1 |
| movement | walk 25 |
| senses | darkvision 60 |
| languages | common, orc |
| disposition | 1 (friendly) |
| ideal / bond / flaw | "Trolleys on time." / "Her loft, her bell, the duck afternoon." / "Cannot keep gossip in, only secrets she doesn't know." |

**Items**
1. feat `Signalwoman`
2. utility `Signal Bell and Trumpet` (1/night halt or delay a trolley up to 10 min; uses 1, `lr`)
3. weapon `Signal Flag Swat` (str, flat 1 bludgeoning: number 0, bonus 1, or describe)
4. feat `GM Reference: Nan Gristle, Voice and Signal Loft`
5. feat `Lore Reference: Trolley Times and Tallis's Rounds`
6. feat `GM Reference: Lil' Apostrophe at the Signal Loft`

---

## Optional quest items (folder "Quest Items (Session 14)", loot, player-facing text only)
| Item | Text |
|---|---|
| `Copied Custody Page` | "A certified copy of a custody ledger page. One entry: Named. Held: the place where even time cannot leave. Tag: outstanding." |
| `Capsule: Bell Silent` | "A capsule with a bone-style tag. The letter reads: Bell silent. Clapper taken to the Customs House. Bailiffs on the road." |
| `Mottle's Receipt (Room 208)` | "Paid in advance. Three nights. Instead of a signature, someone drew a bell." |
| `Outstanding Intake Tag` | "An old intake tag stamped with a crown mark. The number is very low." (Only if the party has not already got the Session 12 tags as items.) |
| `Braided Line (30 ft)` | "Three strands braided together: white linen, fine iron wire, and a pale living fungal thread." |

## Verify after building
- Each actor imports without the "newer core version" error; item and activity ids are 16 chars.
- Feature names match the spec; no feature grants charges or spell slots.
- Folder is `Ossuary`; nothing else in the world was changed.
