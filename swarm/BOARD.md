# Swarm Board
Each member edits only its own rows. Status: `todo`, `doing`, `blocked`, `done`.

| ID | Owner | Task | Status | Notes / output |
|---|---|---|---|---|
| S1 | DND Coordinator | Set up protocol, board, member contact | doing | swarm/PROTOCOL.md |
| S2 | 3D pipeline | Confirm messaging | done | Reply received |
| S3 | Foundry bridge | Confirm messaging and report bridge state | done | Messaging OK. Foundry v14.360 world new-campaign-2026 (dnd5e 5.3.1), module v0.2.0. Module is connected to the relay on Arcturus (GPU PC), per user. This session runs on Vega (Foundry host); Vega's own relay (Startup shortcut, tunnel generators-enzyme-stress-pray) has no module and has different tokens, which caused the 9:38 AM "bad token". Vega relay-url.json still points at Vega's tunnel, so with "Use launcher relay URL" on the GM client would switch back to Vega. Pick one relay. |
| S4 | User | Start the Desktop operator session (Claude desktop app, Computer use on) | todo | See PROTOCOL.md |
| S5 | Desktop operator | Confirm ChatGPT and Gemini apps open and signed in | todo | |
| S6 | 3D pipeline | Verify AI image-to-3D install (AI-SETUP.md) | done | Already installed; smoke test 2026-11-06: SF3D 46 s, 7.7 GB peak VRAM, Blender cleanup 7 s, 12.7k-tri GLB. Use `foundry-3d/ai3d.ps1` |
| G01-G05 | DND Coordinator | Gemini source images (swarm/jobs) | blocked | ON HOLD by user to save quota. Do not run. |
| S7 | Illustrator bridge | Build Illustrator CEP panel + local relay so Claude can send line-art layout jobs (towns, maps) straight into Illustrator 2024 | todo | See swarm/ILLUSTRATOR_HANDOFF.md. Needs user to start the session. |
