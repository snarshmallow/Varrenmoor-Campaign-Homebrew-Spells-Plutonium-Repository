# Swarm Board
Each member edits only its own rows. Status: `todo`, `doing`, `blocked`, `done`.

| ID | Owner | Task | Status | Notes / output |
|---|---|---|---|---|
| S1 | DND Coordinator | Set up protocol, board, member contact | doing | swarm/PROTOCOL.md |
| S2 | 3D pipeline | Confirm messaging | done | Reply received |
| S3 | Foundry bridge | S3c: move relay + GM client to Arcturus | blocked | Repo side done (c51c2fd): `start.bat --local` (no tunnel, LAN listen), README topology. Vega relay STOPPED 2026-11-07 (user-approved): node + cloudflared ended, Startup shortcut and Vega relay-url.json/client.json moved to a backup. Waiting on Arcturus steps (start relay --local, GM settings, RPC test, share check). Bridge launcher (no cmd): foundry-bridge/bridgectl.mjs + daemon.mjs, panel Foundry tab "Bridge relay" block; module 0.3.1 stops the 4002 reconnect loop (needs redeploy on Vega, see DEPLOY_MODULE.md). The live relay on 3030 was NOT restarted; use Launch Bridge in the panel to switch to the managed one. |
| S4 | User | Start the Desktop operator session (Claude desktop app, Computer use on) | todo | See PROTOCOL.md |
| S5 | Desktop operator | Confirm ChatGPT and Gemini apps open and signed in | todo | |
| S6 | 3D pipeline | Verify AI image-to-3D install (AI-SETUP.md) | done | Already installed; smoke test 2026-11-06: SF3D 46 s, 7.7 GB peak VRAM, Blender cleanup 7 s, 12.7k-tri GLB. Use `foundry-3d/ai3d.ps1` |
| G01-G05 | DND Coordinator | Gemini source images (swarm/jobs) | blocked | ON HOLD by user to save quota. Do not run. |
| S7 | Illustrator bridge | Build Illustrator CEP panel + local relay so Claude can send line-art layout jobs (towns, maps) straight into Illustrator 2024 | done | Tested 2026-11-06: panel loads, ping + full job OK (new doc, layers, place SVG, .ai save, PNG export). Install: illustrator/install.ps1 + enable-debug.ps1. See illustrator/README.md |
| IL1 | Illustrator maps | Region/label/panel bug-fix pass (2026-11-07): detail layers (DETAILS - Trees/Lots), headless PNG (svg_raster.py), curved street/river text, Court Square + house leaders, --fit framing, area_scale | done | illustrator/out/bugfix_notes.md. Panel changes load on panel reopen; host.jsx close_docs safe version needs a reopen. Not verified in live Illustrator. |
| IL2 | World pack | worldpack_split: manifest hashes refreshed after split, merge keeps door/hinge nodes (tested on dyers_walk pack) | done | illustrator/WORLD_PACK.md; test_worldpack_detail.py. Door opening in Foundry still unverified; nothing pushed. |
| IL3 | Regions / Foundry 3D | Bake finished 2D map into 3D ground texture: `foundry_push.py bake-texture` (offline) + `push-models --table-texture` | done | FOUNDRY_3D_CANVAS_NOTES.md section 7; live scale of tableTex still to TEST. netsec: not touched by this pass. |
