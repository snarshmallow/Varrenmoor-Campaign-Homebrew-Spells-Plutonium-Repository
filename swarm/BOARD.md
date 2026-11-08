# Swarm Board
Each member edits only its own rows. Status: `todo`, `doing`, `blocked`, `done`.

| ID | Owner | Task | Status | Notes / output |
|---|---|---|---|---|
| S1 | DND Coordinator | Set up protocol, board, member contact | doing | swarm/PROTOCOL.md |
| S2 | 3D pipeline | Confirm messaging | done | Reply received |
| S3 | Foundry bridge | S3c: relay location | done | SUPERSEDED 2026-11-08 by the user: the relay runs on always-on Vega in LAN mode (start.mjs --local, 0.0.0.0:3030, Startup shortcut). Arcturus must NOT run its own relay; the panel Foundry tab attaches to http://10.0.0.15:3030 and foundry_push.py reads the VEGA client.json. Remaining: Arcturus GM browser needs the Vega module token (per-browser setting); module 0.4.0 (pairing) not yet deployed to Vega (0.3.0 installed). Foundry is also published at https://foundry.varrenmoor.com via Cloudflare Tunnel + Access. |
| S4 | User | Start the Desktop operator session (Claude desktop app, Computer use on) | todo | See PROTOCOL.md |
| S5 | Desktop operator | Confirm ChatGPT and Gemini apps open and signed in | todo | |
| S6 | 3D pipeline | Verify AI image-to-3D install (AI-SETUP.md) | done | Already installed; smoke test 2026-11-06: SF3D 46 s, 7.7 GB peak VRAM, Blender cleanup 7 s, 12.7k-tri GLB. Use `foundry-3d/ai3d.ps1` |
| G01-G05 | DND Coordinator | Gemini source images (swarm/jobs) | blocked | ON HOLD by user to save quota. Do not run. |
| S7 | Illustrator bridge | Build Illustrator CEP panel + local relay so Claude can send line-art layout jobs (towns, maps) straight into Illustrator 2024 | done | Tested 2026-11-06: panel loads, ping + full job OK (new doc, layers, place SVG, .ai save, PNG export). Install: illustrator/install.ps1 + enable-debug.ps1. See illustrator/README.md |
| IL1 | Illustrator maps | Region/label/panel bug-fix pass (2026-11-07): detail layers (DETAILS - Trees/Lots), headless PNG (svg_raster.py), curved street/river text, Court Square + house leaders, --fit framing, area_scale | done | illustrator/out/bugfix_notes.md. Panel changes load on panel reopen; host.jsx close_docs safe version needs a reopen. Not verified in live Illustrator. |
| IL2 | World pack | worldpack_split: manifest hashes refreshed after split, merge keeps door/hinge nodes (tested on dyers_walk pack) | done | illustrator/WORLD_PACK.md; test_worldpack_detail.py. Door opening in Foundry still unverified; nothing pushed. |
| IL3 | Regions / Foundry 3D | Bake finished 2D map into 3D ground texture: `foundry_push.py bake-texture` (offline) + `push-models --table-texture` | done | FOUNDRY_3D_CANVAS_NOTES.md section 7; live scale of tableTex still to TEST. netsec: not touched by this pass. |
| T01 | Desktop operator (ChatGPT) | Player onboarding one-pager for foundry.varrenmoor.com (swarm/jobs/T01-player-onboarding.md) | doing | Dispatched 2026-11-08; output swarm/out/player_onboarding.md |
| T02 | Desktop operator (Gemini) | 4 tileable padding texture candidates (swarm/jobs/T02-padding-textures.md). G01-G05 hold LIFTED by the user 2026-11-08 | doing | Output swarm/out/textures/ |
| V1 | Vega Foundry (sub-coordinator) | Vega-side jobs go through the Vega session (user rule). Done: bridge 0.5.1 live, tunnel, Access, cleanup. Next: read-only inventory of Foundry assets/varrenmoor-3d (stale versions, sizes) and disk space report | todo | Report only, no deletions without approval |
| L1 | Live verification agent | Foundry live check of latest map work (graded foliage, apron fix, road blending, bridge carve, church/walls) on the two ZZ scenes | doing | illustrator/out/unfinished_work.md "Live verification 2" |
| R1 | Security review agent | Independent read-only review of LAN pairing/encrypted handshake | doing | illustrator/out/pairing_security_review.md |
| D1 | Docs agent | Consolidated plugin user guide | doing | illustrator/PLUGIN_GUIDE.md |
