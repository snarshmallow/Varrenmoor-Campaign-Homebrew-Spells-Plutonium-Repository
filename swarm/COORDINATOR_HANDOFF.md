# Coordinator Handoff (cloud -> local terminal)

The cloud coordinator (`session_01HJDDq1ddvku7yohXSHTW4U`) is retired. A local terminal session on the user's PC takes over as **DND Coordinator**. Read `swarm/PROTOCOL.md` and `swarm/BOARD.md` first.

## Members and how to reach them
Local sessions on the same PC can use `ListAgents` and `SendMessage` by name. The session ids are for reference.

| Name | Session id | State |
|---|---|---|
| 3D pipeline | session_01UuYwuftg1tFbVbPMV9TAA3 | Idle. Image-to-3D verified (SF3D on RTX 3080, about 46 s per model; entry `foundry-3d\ai3d.ps1 -Image <png> -Name <name> -Folder "<campaign folder>"`). Waiting for the user to pick SDXL seeds. |
| Foundry bridge | session_0176XLXCQR66jiZgcozn6qTz | Never replied to the intro message. Re-contact it. |
| Desktop operator setup | session_01UuYwufWKrHcQQBHm2YCTVM | Standing by. ChatGPT windows capture blank and Gemini ignores clicks. The recommended fix is Claude in Chrome on chatgpt.com and gemini.google.com. The user has not chosen yet. |

## Open items
1. **Gemini jobs G01-G05** (`swarm/jobs/`) are ON HOLD by the user to save quota. Do not run them.
2. **SDXL seeds:** the user must pick one per character (Quill, Brokka, Pimm, Mottle, Gerald, Kell, Wren). See `swarm/ASSETS.md`. One Pimm seed drifted to horns and a dwarf look. Gerald is a four-legged soft-shelled turtle with extra climbing toes.
3. **Permission prompts:** PC sessions run in prompting mode. The user can switch each to Auto mode with Shift+Tab, or add `.claude/settings.json` allow rules. The cloud session was blocked from writing that file.
4. **ChatGPT/Gemini path:** browser path (Claude in Chrome) vs full-screen control of the desktop apps. This is the user's decision.
5. **Codex:** later, overflow coding only.

## Other recent work (for context)
- `recap/` holds the campaign recap prompt pack and the corrected history chart. The recap page is a claude.ai artifact.
- `gm-guide/Varrenmoor_NPC_Dialogue_GM_Reference.md` has Part 6 side quests and the Ossuary note-lead consolidation. These are mirrored to the Google Doc "current dm guide 2026 Varrenmoor campaign", tab "Part 6: Ossuary Exchange".
