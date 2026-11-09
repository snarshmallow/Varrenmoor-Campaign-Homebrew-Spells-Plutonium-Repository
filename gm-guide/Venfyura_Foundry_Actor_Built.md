# Venfyura: Foundry actor built

The GM confirmed that the existing Foundry actor **Fortune Teller** (the Market of Transients witch, Session 7) is **Venfyura**, Violet's grandmother and an Eirwitch. That actor was empty (no items, no biography). It has been renamed and built out in place as a native NPC, like the Ossuary and Session 14 NPCs.

- **UUID:** `Actor.afVUI68BonsDF1a7` (same document: only this actor was written)
- **Name:** Venfyura, Witch of the Market of Transients (prototype token name: **Venfyura**)
- **Folder:** unchanged (`OLuefHiZMZYoeS5z`)
- **Pipeline flag:** `flags.varrenmoor.pipelineId = npc:ossuary:venfyura`; each item is tagged `npc:ossuary:venfyura:<slug>` (spells `npc:ossuary:venfyura:spell:<slug>`), so a re-run updates items and adds no duplicates (checked: two runs, 23 items).
- **Builder:** `foundry-json/venfyura_npc.py` (`--push` updates the live actor). Built JSON: `foundry-json/actors/Venfyura_FoundryVTT.json`.
- **Backups:** `foundry-3d/ai/characters/venfyura/actor_backup_before.json` (the empty Fortune Teller, written once and never overwritten) and `actor_after.json` (read back after the build).

## Stat block (2024 style, CR 2, not a combatant)

| Field | Value |
|---|---|
| Type | Medium humanoid (elf (Eirwyn)), neutral |
| AC / HP / Speed | 12 / 45 (10d8) / 30 ft |
| Abilities | Str 8, Dex 14, Con 10, Int 16, Wis 18, Cha 13 |
| Saves | Int +5, Wis +6 |
| Skills | Arcana +5, History +5, Insight +8 (expertise), Medicine +6, Persuasion +3 |
| Tools | Herbalism kit, weaver's tools |
| Senses | Darkvision 60 ft (passive Perception 14) |
| Languages | Common, Elvish, Sylvan; custom: Old Eirwyn script |
| Spellcasting | Wisdom, save DC 14, +6 to hit |
| Legendary / lair | None |

**Spells** (real dnd5e 2024 spell items, cloned read-only from the copies on Stellan's and Violet's sheets because the bridge cannot list compendiums; the "Spellcasting" feature links each one with `@UUID`):
- At will: Detect Magic, Light, Mending, Starry Wisp (her only damage: 1d8 radiant, 60 ft)
- 2/day each (innate, item uses): Gentle Repose, Lesser Restoration, Sanctuary
- 1/day each (innate, item uses): Calm Emotions, Locate Object

The theme follows the Eirwyn notes (water, ice, light; weaving, healing, preservation; root runes Preserve, Mend, Reveal, Threshold). The list itself is a build choice, not canon.

## Items (23)

Traits and actions:
1. Fey Ancestry
2. Trance
3. Old Hands (tool feature): herbalism kit and weaver's tools
4. Spellcasting (the list above, linked)
5-13. The nine spell items

Reference features (feats with no activities, in the native pattern):
14. **GM Reference: Venfyura, Voice and Barks** (the quote, snapshot, voice, wants and fears, barks, Mavis's line about desertion, "not a combatant")
15. **GM Reference: Venfyura, Questions and Answers** (every Q&A line with its [ASK]/[EARN]/[SECRET]/[UNSETTLED] tag, the Old Ways [EARN] line, quick-finder rows)
16. **Lore Reference: The Four Lost Crafts** (Part 1.6; she knows all four; the Eirwyn relationship)
17. **Lore Reference: Mwooreth and the Old Ways** ("severance is a craft, not a sin")
18. **Lore Reference: Restoring Bones** (linen, water, a seed of life, a rune of boundary, needle, anchors; the Session 7 inventory)
19. **Lore Reference: The Seam-Wheel** ("a diagram, not a door")
20. **Lore Reference: The Egg and the Son of Håkon** ([EARN] "until he asks me properly")
21. **Lore Reference: Violet, the Amulet and the Chart** ("little one"; Spring Queen [SECRET]; withdrawal [UNSETTLED])
22. **GM Reference: The Woman at the Fire (Sessions 14-15)** (the camp, fire and bell, "V.", Pell's loyalty, the fungal culture, "She's looking", the far knot at the gorge, settled Cladis/Lakkar canon, the suggested "Not yet, little one")
23. **GM Reference: Session 7, the Market of Transients** (what she discussed there)

Biography: a short public part (who she is, where the party met her, "little one"; appearance "old/ancient, nothing further recorded") and GM notes in a Foundry secret block. Ideal, bond and flaw are filled in.

Prototype token: name Venfyura, disposition **Friendly**, sight on (darkvision 60). The token art (`systems/dnd5e/icons/svg/actors/npc.svg`) is unchanged. **The token already had a 3D model** (`canvas3dtokencompendium/.../MZ4250 - Barovian Witch.glb`, set earlier in the world). It was left in place rather than unset. A custom Venfyura model is still a TODO. The display name stays at 20 because the world forces that on every NPC.

**Not built (no canon for them):**
- No **Side Quest**: the guide gives her none. The far knot is main-line Session 15 work, and it is covered in the Sessions 14-15 reference.
- No **Merchant Reference** and no stock loot: canon records nothing she sold. The Session 7 iron-bell trade is Betsy's.

## Scene tokens (reported, not modified)

All 84 scenes were scanned. One token is linked to this actor:
- **Merchant Stalls** (`Scene.19TnOLHNKzLi20hT`), token `X6x6QhDtBrRgXqq5`: unlinked (actorLink false), still named **"Fortune Teller"**, disposition **hostile (-1)**, no delta overrides. It now inherits Venfyura's stats and items, but its name and disposition are token-level, so they stay as they are until the GM changes them (or drags a fresh token).

## Assumptions (the GM should confirm)
- **Species:** elf (Eirwyn). Violet is an elf, but canon only says "Eirwitch", "ancient" and "old woman".
- **Alignment** neutral; **languages** Common, Elvish, Sylvan and Old Eirwyn script. Sylvan and the script are guesses.
- **Numbers:** CR 2, AC 12, 45 HP, the ability scores and the spell list are all build choices.
- **Display name:** "Witch of the Market of Transients", because that is where the party met her.
- **Ideal, bond, flaw** are drawn from her quote, wants and voice, not stated canon.

## Open canon questions
1. **[UNSETTLED]** Venfyura's reason for leaving or withdrawing (Mavis: desertion). The GM Reference Part 5 #2 and Part 7 #22 still apply.
2. **[SECRET / later plan]** whether Violet (or Venfyura) held the Spring office.
3. **[SUGGESTED]** whether she put Europa to sleep ("Not yet, little one"), and why.
4. What she says about the egg once Stellan "asks properly".
5. Whether the Merchant Stalls token should be renamed, made friendly, or swapped for a fresh Venfyura token.
6. Whether she sold anything at the Market of Transients (if so, add a Merchant Reference).
7. Her appearance beyond "old/ancient".
