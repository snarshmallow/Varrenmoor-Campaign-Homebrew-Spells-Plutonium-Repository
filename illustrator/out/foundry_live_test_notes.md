# Foundry live test, 2026-11-07 (Foundry 14.360, levels-3d-preview 9.0.29, GM browser at 10.0.0.15:30000)

Scenes created (ours only): `ZZ Dyers Walk 3D Test` Scene.sFd94FxO1JX8dlJg (28 model tiles, 72 lights, skybox clear_day with the Illustrator sun), `ZZ Dyers Walk 2D Test` Scene.1drJ8PFJ4p5aBctd,
`ZZ Commoners Ring 2D Test` Scene.l3yIfUMh55JFEqQm. `ZZ Tile Rotation Inspect` deleted. Nothing else touched. The GM tab was left viewing the 3D test scene.

Commands (pack regenerated first: worldpack.py export, worldpack_split.py split, merge --preset layer --compress quant):
* `foundry_push.py push-models --place bridgehollow__dyers_walk_local --scene-name "ZZ Dyers Walk 3D Test" --scene-mode 3d --lighting bridgehollow`
* `skybox.py generate --place bridgehollow --viewer 883,891 --presets clear_day --lighting bridgehollow --out world/<place>/export/skybox`, then `skybox.py set-flag --scene-uuid ... --apply` (after push-models)
* `foundry_push.py push-lights --place bridgehollow__dyers_walk_local --scene-uuid ... --lighting bridgehollow`
* `foundry_push.py push-scene --place bridgehollow__commoners_ring__dyers_walk --view district --scale 20 --grid 5 --upscale 3 --image illustrator/out/commoners_ring_dyers_walk.png --scene-name "ZZ Dyers Walk 2D Test" --scene-mode flat --lighting bridgehollow`
* Commoners Ring: `--place bridgehollow__commoners_ring --scale 40 --grid 5 --ft-per-grid 10 --upscale 3` (5 ft would need 6x upscale, over the 8192 px limit, so the Foundry grid is 10 ft there).

Results: see FOUNDRY_3D_CANVAS_NOTES.md section 6 (verified/open) and 8 (lighting). Screenshots (JPEG, about 1555 px wide, UI hidden) in `illustrator/out/foundry_screens/`:
`2d_dyers_walk.jpg`, `2d_commoners_ring.jpg`, `3d_overhead_full.jpg`, `3d_overhead_close.jpg` (before lighting match), `3d_ground_street.jpg`, `3d_street_sun_sw.jpg`, `3d_ground_lit_shadows.jpg`.

Bugs found and fixed: door `doorAnimateAngle` degrees vs radians (leaf spun 90 rad); gltfpack temp file name `.tmp` rejected, extras dropped without `-ke`, UV precision warning (`-vt 16`); `_stats` could not read quantized GLBs; push-models reset the skybox flag; interior sparks (torch particles) drawn through roofs.
Observations: smoke-like particles from hearth lights were visible over roofs (removed); the black table shows as a dark band at the horizon (`tableColor` ignored with that texture); the terrain GLB edge has a stretched skirt; interior windows now 85 (was 52, old derived 103).
