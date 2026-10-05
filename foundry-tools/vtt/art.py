"""The 2D -> 3D pipeline wrapped for tokens: concept image (SDXL) -> Stable Fast 3D -> turn to face -Y -> copied to the Foundry share."""
import os
import subprocess
import sys

from .common import G3D, MODELS, OUT, DEFAULT_FOLDER, run_stream, slug

VENV_PY = G3D / "ai" / ".venv" / "Scripts" / "python.exe"


def concept(name, prompt, seed=29, seq_offload=True, neg=""):
    """Generate the concept image. Returns the image path. Slow (about 10 min with --seq-offload, 1-2 min without)."""
    cmd = [str(VENV_PY), str(G3D / "ai" / "concept.py"), "--name", slug(name), "--prompt", prompt, "--seed", str(seed)]
    if seq_offload:
        cmd.append("--seq-offload")
    if neg:
        cmd += ["--neg", neg]
    run_stream(cmd, cwd=str(G3D / "ai"))
    return G3D / "ai" / "characters" / f"{slug(name)}_{seed}.png"


def model_from_image(image, name, height_m, tris=9000, folder=DEFAULT_FOLDER + "/Tokens", turn=True):
    """Run SF3D on an image. Returns the file name (e.g. 'token_pimm_ai.glb'). The model is turned 180 degrees (SF3D faces +Y, tokens must face -Y)."""
    fname = f"token_{slug(name)}_ai"
    run_stream(["powershell", "-NoProfile", "-File", str(G3D / "ai3d.ps1"), "-Image", str(image), "-Name", fname, "-Folder", folder,
                "-Tris", str(tris), "-Height", str(height_m)], cwd=str(G3D))
    glb = OUT / folder.replace("/", os.sep) / f"{fname}.glb"
    if turn:
        subprocess.run([_blender(), "-b", "--factory-startup", "--python", str(G3D / "blender" / "turn180.py"), "--", str(glb)], check=True, capture_output=True)
        _copy_to_share(glb, folder)
    return f"{fname}.glb"


def _env():
    cfg = {}
    for l in (G3D / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in l:
            k, v = l.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def _blender():
    return _env()["BLENDER_PATH"]


def _copy_to_share(glb, folder):
    import shutil
    dest = os.path.join(_env()["FOUNDRY_ASSETS_DIR"], folder.replace("/", os.sep))
    os.makedirs(dest, exist_ok=True)
    shutil.copy(glb, dest)


def model_path(file, folder=DEFAULT_FOLDER + "/Tokens"):
    return f"assets/varrenmoor-3d/{folder}/{file}"
