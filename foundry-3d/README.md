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

## Writing a generator
Make `generators/<name>.py` with a `build(k)` function. `k` provides `mat()`, `box()`, `cylinder()`, `cone()`, `sphere()`, `cloth()`, `jitter()` and a seeded `rng`. See `ossuary_stall.py`.
