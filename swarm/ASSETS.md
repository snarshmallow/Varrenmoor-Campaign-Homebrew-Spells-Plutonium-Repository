# Next-session cast: source images for ai3d.ps1

Inventory date: 2026-11-06 (3D pipeline). No generation was run for this list.

Source images in the repo: `foundry-3d/ai/characters/` only. They are SDXL concepts from `ai/characters.py`, three seeds per character (`<name>_3/_17/_29.png`) on a plain grey background with full body showing, which suits SF3D. None of the seeds has been reviewed or picked yet. The `2026 Campaign` concept PNGs that AI-SETUP.md mentions (e.g. `ossuary clerk.png`) live on the Foundry PC or share, not in the repo.

| Asset | Source image | Needs Gemini image | Notes |
|---|---|---|---|
| Quill (skeleton runecrafter) | `foundry-3d/ai/characters/quill_{3,17,29}.png` | Only if the seeds are off-model | Prompt: ivory bones, ink-stained hooded robe, chalk and slate, spectacles |
| Brokka (dwarf smith) | `brokka_{3,17,29}.png` | Only if off-model | Check the missing two fingers on the left hand; SF3D won't keep that detail anyway |
| Doctor Pimm (goblin surgeon) | `pimm_{3,17,29}.png` | Maybe | `sheet.png` shows SDXL drift: one candidate has horns and looks like a dwarf. Pick carefully or have Gemini make one |
| Pimm's pets/specimens? | `pimm_s_fish_0.png`, `pimm_s_salamander_{0,29}.png` (untracked) | Unknown | Purpose unclear. Probably Pimm's specimens. User to confirm whether they're wanted. Used `pimm_s_salamander_0` as the SF3D smoke test, which worked |
| Mottle (skeleton innkeeper) | `mottle_{3,17,29}.png` | Only if off-model | |
| Gerald (soft-shelled turtle) | `gerald_{3,17,29}.png` | Maybe | Four legs with extra climbing toes, plus a long grippy tongue (Coordinator correction). `ai/characters.py` prompted "six legs", so the seeds may show six. Use one only if it reads as four-legged |
| Dunmore Kell (night porter) | `dunmore_kell_{3,17,29}.png` | Only if off-model | Cap, cream apron, lantern |
| Tobias Wren (old gravewright) | `tobias_wren_{3,17,29}.png` | Only if off-model | Frock coat, shovel |
| Lil' Apostrophe | none | **Yes** | No concept in the repo. Need a description from the campaign notes for the Gemini prompt |
| Mavis | none | **Yes** | No concept. Need a description |
| Pringus | none | **Yes** | No concept. Need a description |
| Skeleton Exchange staff | none (closest: `mottle_*`, `quill_*` skeleton bases) | **Yes** | One generic skeleton clerk/porter in Exchange uniform; reuse it for several tokens. `foundry-3d/textures/painting_clerk.jpg` is a wall-painting texture, not a token source. `ossuary clerk.png` may be in `2026 Campaign`; check the share before asking Gemini |
| Stolen Shard greatsword | none | **Yes** | Prop, about 6 ft (use `-Height 1.83`). Rhime-ice cold steel: pale blue-white frosted blade. Ask for a flat side-on view, blade vertical, plain background. SF3D handles a thin blade poorly, so a Blender-modelled blade with a Gemini texture may beat image-to-3D |

## Suggested next step
1. Pick one seed per existing character. This costs no Claude tokens if the user or the Desktop operator looks at the PNGs. Then run `ai3d.ps1` on each.
2. Gemini jobs: Lil' Apostrophe, Mavis, Pringus, skeleton Exchange staff and the greatsword, plus Pimm and Gerald if their seeds fail. Style for 3D input: single subject, full body, front or three-quarter view, plain light background, even lighting, no cast shadow.
