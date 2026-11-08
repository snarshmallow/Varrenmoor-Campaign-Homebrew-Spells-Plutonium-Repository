# Swarm Board
Each member edits only its own rows. Status: `todo`, `doing`, `blocked`, `done`.

| ID | Owner | Task | Status | Notes / output |
|---|---|---|---|---|
| S1 | DND Coordinator | Set up protocol, board, member contact | doing | swarm/PROTOCOL.md |
| S2 | 3D pipeline | Confirm messaging | done | Reply received |
| S3 | Foundry bridge | Bridge relay on Vega (LAN), handed off to coordinator 2026-11-08 | blocked | Relay on Vega 0.0.0.0:3030 (TUNNEL=off, autostarts). Vega GM tab authenticated 4:41 PM. Arcturus GM tab has an old token: copy moduleToken from \\VEGA\C\FoundryVTT resources\bridge\client.json (fd68222), then F5. Module 0.3.0 installed; 0.4.0 in repo not deployed. Vega session handed off. |
| S4 | User | Start the Desktop operator session (Claude desktop app, Computer use on) | todo | See PROTOCOL.md |
| S5 | Desktop operator | Confirm ChatGPT and Gemini apps open and signed in | todo | |
| S6 | 3D pipeline | Verify AI image-to-3D install (AI-SETUP.md) | done | Already installed; smoke test 2026-11-06: SF3D 46 s, 7.7 GB peak VRAM, Blender cleanup 7 s, 12.7k-tri GLB. Use `foundry-3d/ai3d.ps1` |
| G01-G05 | DND Coordinator | Gemini source images (swarm/jobs) | blocked | ON HOLD by user to save quota. Do not run. |
| S7 | Illustrator bridge | Build Illustrator CEP panel + local relay so Claude can send line-art layout jobs (towns, maps) straight into Illustrator 2024 | done | Tested 2026-11-06: panel loads, ping + full job OK (new doc, layers, place SVG, .ai save, PNG export). Install: illustrator/install.ps1 + enable-debug.ps1. See illustrator/README.md |
| IL1 | Illustrator maps | Region/label/panel bug-fix pass (2026-11-07): detail layers (DETAILS - Trees/Lots), headless PNG (svg_raster.py), curved street/river text, Court Square + house leaders, --fit framing, area_scale | done | illustrator/out/bugfix_notes.md. Panel changes load on panel reopen; host.jsx close_docs safe version needs a reopen. Not verified in live Illustrator. |
| IL2 | World pack | worldpack_split: manifest hashes refreshed after split, merge keeps door/hinge nodes (tested on dyers_walk pack) | done | illustrator/WORLD_PACK.md; test_worldpack_detail.py. Door opening in Foundry still unverified; nothing pushed. |
| IL3 | Regions / Foundry 3D | Bake finished 2D map into 3D ground texture: `foundry_push.py bake-texture` (offline) + `push-models --table-texture` | done | FOUNDRY_3D_CANVAS_NOTES.md section 7; live scale of tableTex still to TEST. netsec: not touched by this pass. |
