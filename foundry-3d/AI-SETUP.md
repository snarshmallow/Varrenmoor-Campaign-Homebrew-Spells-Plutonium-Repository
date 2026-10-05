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

## Status: installed (2026-10-04)
- Env: `ai/.venv` (Python 3.11 via uv, torch 2.11+cu128, transformers pinned 4.49 and diffusers <0.33; newer transformers breaks the Hunyuan DINOv2 weights). `ai/repo` is a clone of Hunyuan3D-2. Both are gitignored.
- Shape stage: `ai/shape.py` with Hunyuan3D-2mini, fp16, loaded straight onto the GPU (the repo's `enable_model_cpu_offload` is broken, and isn't needed: peak is low on the 10 GB 3080). About 15 s per shape after weights are cached.
- Texture: `ai/cleanup.py` in Blender decimates (default 30k tris), scales to `-Height` metres (default 1.8), bases at Z=0, front-projects the source image, bakes to a 2048 UV texture, exports GLB and .blend. Back of the model gets the stretched front projection; hand-paint if it matters.
- Entry point: `.\ai3d.ps1 -Image <png> -Name <name> -Folder "<campaign folder>" [-Tris 30000] [-Height 1.8]`.
- No nvcc, so no CUDA extensions were built; shape-only path used. Verified end to end with a synthetic image only.

## Update: Stable Fast 3D is now the default engine
- Compared on the ossuary clerk: Hunyuan shape plus front projection came out near-black and smeared; SF3D gave a clearly better textured result and a recognisable back. `ai3d.ps1` now defaults to `-Engine sf3d`; `-Engine hunyuan` keeps the old path.
- Installed in `ai/.venv` from `ai/sf3d/` (gitignored clone). Weights are gated: the HF account must have accepted the licence, and a read token is stored by `hf auth login`. SF3D is non-commercial under US$1M revenue; see the model card.
- `uv_unwrapper` and `texture_baker` were built CPU-only (no nvcc) from a VS 2022 Build Tools prompt with `USE_NATIVE_ARCH=0 USE_CUDA=0 DISTUTILS_USE_SDK=1` and `--no-build-isolation`. The installed `texture_baker/baker.py` in the venv is patched to move tensors to CPU for rasterize/interpolate and back. Rebuilding the venv means redoing that patch.
- Peak VRAM about 8 GB of the 10 GB.

- SF3D GLBs come out fully metallic with roughness 0 (glTF's default when metallic is absent), which renders near-black. cleanup.py now forces Metallic 0 and Roughness 0.85 on every material.
