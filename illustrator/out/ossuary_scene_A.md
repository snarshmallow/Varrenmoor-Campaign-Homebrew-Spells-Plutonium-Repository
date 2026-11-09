# Ossuary Session 14 scenes: agent A (Harrowgate, Night Custody)

Built with the Ossuary interior pipeline (foundry-3d generator -> Blender GLB copied to `\\VEGA\varrenmoor-3d` -> `foundry-bridge/make-scene.ps1 -FolderId`), the same way as the existing Ossuary interiors (Clinic, Forge, Rune Workshop): one 3D Canvas tile (rotation 0, centred), market scene settings cloned, 5 ft grid at 100 px, AmbientLights only, no emissive materials, real glTF doors. Not an illustrator place: this pipeline matches the existing Ossuary scenes and shipped fastest.

Folder: Act 2 > The Ossuary Exchange > Session 14 = `Folder.OgwTUoD6FzPcsH2g` (created by agent A under the push lock).

| scene | uuid | source | status | notes |
|---|---|---|---|---|
| Harrowgate Restorations | `Scene.1b5q3kkFove7vk6Z` | `foundry-3d/generators/ossuary_harrowgate.py` -> `.../Session 14/ossuary_harrowgate.glb` | IN FOUNDRY 2026-11-09 17:42, not activated | 50 x 40 ft (16.2 x 13.2 m with walls), 1 tile, 3 lights (#ffc78a counter, #fff2d8 work table, #cfe6ff vessel room). Doors: street, work_room, Vessel_Room_Door (lock it in Foundry if wanted). Named nodes: Mycelium_Culture_Case, Vessel_Table, Vessel_Linen, Linen_Rolls, Distilled_Water_Flasks, Rune_Tile_Rack, Counter_Ledger. |
| Night Custody Office | `Scene.M3QYxMNlFcXtK0l0` | `foundry-3d/generators/ossuary_custody_office.py` -> `.../Session 14/ossuary_custody_office.glb` | IN FOUNDRY 2026-11-09 17:42, not activated | 40 x 30 ft (13.2 x 10.2 m with walls), 1 tile, 2 lights (#ffd9a0 desk lamp, #9fb7d6 door spill). Door: Office_Door. Named nodes: Sabeline_Desk, Open_Claim_Ledger, Copy_Table, Custody_Shelves, Rolling_Ladder, Notice_Board, Night_Desk_Bell, Open_Claim_Volume_Misshelved (the DC 13 red volume). Scene environment copied from the market (not darkened for night). |

Rebuild: `cd foundry-3d; .\make.ps1 ossuary_harrowgate` (or `ossuary_custody_office`), then Ctrl+F5 in Foundry (same model path, no re-push needed).
