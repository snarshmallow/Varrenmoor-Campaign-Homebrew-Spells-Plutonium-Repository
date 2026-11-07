# Swarm Board
Each member edits only its own rows. Status: `todo`, `doing`, `blocked`, `done`.

| ID | Owner | Task | Status | Notes / output |
|---|---|---|---|---|
| S1 | DND Coordinator | Set up protocol, board, member contact | doing | swarm/PROTOCOL.md |
| S2 | 3D pipeline | Confirm messaging | done | Reply received |
| S3 | Foundry bridge | S3c: move relay + GM client to Arcturus | blocked | Done: launcher `start.bat --local` (no tunnel, listens on LAN so a http://VEGA:30000 page can reach it), client.json for local bridge.ps1, README topology section; tested on Vega scratch copy. Blocked: Vega relay still running (stopping it needs user approval in the Vega session); Arcturus steps (start relay, GM settings, RPC test, share check) must run on Arcturus. In the Arcturus GM client turn "Use launcher relay URL" OFF. |
| S4 | User | Start the Desktop operator session (Claude desktop app, Computer use on) | todo | See PROTOCOL.md |
| S5 | Desktop operator | Confirm ChatGPT and Gemini apps open and signed in | todo | |
| S6 | 3D pipeline | Verify AI image-to-3D install (AI-SETUP.md) | done | Already installed; smoke test 2026-11-06: SF3D 46 s, 7.7 GB peak VRAM, Blender cleanup 7 s, 12.7k-tri GLB. Use `foundry-3d/ai3d.ps1` |
| G01-G05 | DND Coordinator | Gemini source images (swarm/jobs) | blocked | ON HOLD by user to save quota. Do not run. |
| S7 | Illustrator bridge | Build Illustrator CEP panel + local relay so Claude can send line-art layout jobs (towns, maps) straight into Illustrator 2024 | done | Tested 2026-11-06: panel loads, ping + full job OK (new doc, layers, place SVG, .ai save, PNG export). Install: illustrator/install.ps1 + enable-debug.ps1. See illustrator/README.md |
