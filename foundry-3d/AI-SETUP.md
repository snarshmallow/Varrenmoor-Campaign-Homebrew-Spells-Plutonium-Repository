# AI image-to-3D on the GPU PC (RTX 3080), plan

Goal: turn a concept image (the PNGs already in `2026 Campaign`, e.g. `ossuary clerk.png`) into a textured, Foundry-ready `.glb` for 3D Canvas tokens and tiles. Output is filed the same way as the Blender generators (`FOLDER` mirrors the 2026 Campaign layout, copied to `\\VEGA\varrenmoor-3d`).

## Constraints
- RTX 3080: check `nvidia-smi` for 10 GB or 12 GB. Windows 10 host.
- Hunyuan3D 2.1: geometry needs about 10 GB (fits); its texture stage needs about 29 GB (does not fit).
- TRELLIS.2 needs 24 GB and has no Windows support. The original TRELLIS needs about 16 GB. Skip both.

## Pipeline
1. **Shape:** Hunyuan3D shape model (2.1, or 2mini if 10 GB is tight), using its low-VRAM / CPU-offload options. Image goes in; untextured mesh comes out.
2. **Texture:** with the full Hunyuan paint stage out of reach, either
   - project the source image onto the mesh in Blender (front projection plus mirrored back, then bake to one texture), or
   - try Stable Fast 3D (about 6 GB, textured output) for small props and NPCs where speed matters more than detail.
3. **Clean-up in Blender** (`foundry-3d/blender/`): decimate to about 20-40k triangles for tokens, merge to one mesh, base at Z=0, apply transforms, export GLB. Reuse `run.py` conventions.
4. **File:** write to `out/<FOLDER>/<name>.glb` and `.blend`, then copy to the share, as `make.ps1` does.

## Setup notes for the session doing the install
- Use a dedicated venv (or conda env) under `foundry-3d/ai/.venv`; never install into system Python.
- Match the PyTorch CUDA build to the installed NVIDIA driver.
- Hunyuan3D's custom CUDA extensions may need Visual Studio Build Tools (C++) and the CUDA toolkit; if a build fails, prefer the shape-only path, which doesn't need them.
- Model weights download from Hugging Face (several GB); keep them in the default HF cache and out of git.
- Deliver a single entry point: `.\ai3d.ps1 -Image <png> -Name <name> -Folder "<campaign folder>"`.
- Add `foundry-3d/ai/` venv and weights paths to `.gitignore`.
