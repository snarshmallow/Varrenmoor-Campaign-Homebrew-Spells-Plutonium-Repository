# Varrenmoor 3D models for Foundry (3D Canvas)

Python generators build models in Blender (headless) and export `.glb` files that 3D Canvas uses for tiles and tokens.

```
generators/*.py --(blender/run.py)--> out/*.glb --(optional copy)--> Foundry Data/assets/varrenmoor-3d/
```

## GPU PC setup (once)
1. Pull this repo, open PowerShell in `foundry-3d`, then run `.\setup.ps1`. It finds Blender, writes `.env` and builds the test model `out\ossuary_stall.glb`.
   - If PowerShell blocks scripts, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
2. Optional: run `host-setup.ps1` (repo root) on the Foundry PC to share its `assets\varrenmoor-3d` folder, then rerun setup with
   `.\setup.ps1 -FoundryAssetsDir '\\<FOUNDRY-PC>\varrenmoor-3d'` so models land in Foundry directly.

## Use
- `.\make.ps1` builds everything. `.\make.ps1 ossuary_stall -Seed 4` builds one model with a different random variation.
- In Foundry, on a 3D Canvas scene, create a Tile and pick the `.glb` as its 3D model.

## Conventions
- 1 Blender unit = 1 m; one grid square (5 ft) = 1.524 m. `run.py` prints each model's size in squares.
- Models are centred on their footprint with the base at Z=0. Modifiers are applied on export.
- Keep props small, under about 20k faces each; 3D Canvas renders every tile every frame.

## Filing
Set `FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"` in a generator to file its `.glb` and editable `.blend` under that path. On the Foundry PC, `Data\assets\varrenmoor-3d` also appears as `2026 Campaign\Generated 3D`; both are the same files. The `.blend` keeps parts separate; the `.glb` merges them into one mesh for fewer draw calls.

## Writing a generator
Make `generators/<name>.py` with a `build(k)` function. `k` provides `mat()`, `box()`, `cylinder()`, `cone()`, `sphere()`, `cloth()`, `jitter()` and a seeded `rng`. See `ossuary_stall.py`.

## 3D maps (scenes)
- `generators/ossuary_tavern.py` is a large interior (about 19 x 14 squares): Mottle's tavern, "The Last Respite Before Further Administrative Action". `ossuary_tavern_roof.py` is its roof, trusses, chandeliers and hanging conveyor, kept separate so it can be hidden. Place both tiles at the same position; the roof keeps its own height (`KEEP_Z = True` in a generator skips the drop-to-Z=0 step). Keep `IX, IY, T, WALL_H` and the hearth x in sync between the two files.
- Scenes use the Ossuary Exchange plaza's own PBR textures from `textures/` (pulled out of the plaza GLB with `textures/extract.py`). `Kit.tex(name, slug, tile=metres)` makes a textured material and `run.py` assigns world-aligned UVs, so large walls and floors tile at a constant scale.
- `blender/preview.py` renders review shots (top-down, interior views, outside) of one or more GLBs: `blender -b --factory-startup --python blender/preview.py -- a.glb [b.glb] <out_prefix>`.

## Doors, skulls, watchers
- **Doors:** `k.door(width, height, hinge, yaw_deg, swing, leaf_mat, trim_mat, door_id)` makes a swinging door as its own glTF node (origin on the hinge; extras `isDoor`, `doorId`, `doorStyle` 1, `doorAnimateAngle`). `run.py` keeps objects flagged `isDoor` or `separate` out of the export merge and writes custom properties as extras, which 3D Canvas reads to animate the door about its origin. No tile door flags are needed; clicking the door in the scene opens it.
- **Shared parts:** `generators/_parts.py` (lathe, bottle profiles, flame tongues, `Skulls` collector, `Walls` helper). Files starting with `_` are skipped by `make.ps1`.
- **Watchers:** `ossuary_watcher_painting.glb` has two separate nodes `watcher_eye_L/R`; the module in `foundry-modules/varrenmoor-watchers` (copy to Foundry `Data/modules/`, enable in the world) turns them toward the nearest player token.
- **Tile placement:** a 3D Canvas tile's `x, y` is its centre. Model-metre sizes convert at 100 px = 1.524 m; width = model X, height = model Y, depth = model Z. At tile rotation 0 the model appears turned 180 degrees from plan view, so scenes use rotation 180 (Blender north = canvas top). A painting's front faces canvas-up at rotation 0, down at 180, left at 270, right at 90.
- **Particles:** ambient-light flags `enableParticle`, `ParticleType: torch`, and a small `ParticleEmitterSizeMultiplier` (about 0.015) keep the flames at the fire; the default emitter radius is the light's whole radius.
