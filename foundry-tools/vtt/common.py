"""Shared helpers for the vtt tools: paths, the Foundry bridge, lookups, and the model-metre -> scene-pixel mapping.

Conventions learned building the Ossuary Exchange (all verified in Foundry unless marked):
  * 1 m = 100/1.524 px (K = 65.617). A model tile's x,y is its CENTRE; width = model X, height = model plan-Y, depth = model Z (all in px).
  * Plan north is canvas-up at tile rotation 0. Blender -Y is the front of a token model; +Y is the front of a wall plate.
  * Elevation is in feet: 1 m = 3.281 ft; model tiles sit at elevation 0.0995. Floor top in our generators is 0.1 m (F).
  * Browsers cache models by file name: a rebuilt model needs a NEW file name (or Ctrl+F5).
  * ground_and_centre() recentres every model, so scene coordinates = generator coordinates + the sidecar "shift".
"""
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "foundry-tools"
BRIDGE = ROOT / "foundry-bridge" / "bridge.ps1"
G3D = ROOT / "foundry-3d"
OUT = G3D / "out"
GEN = G3D / "generators"
TEXTURES = G3D / "textures"
GUIDE = ROOT / "gm-guide"
K = 100 / 1.524
FT = 3.281
BASE_ELEV = 0.0995
DEFAULT_FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
MODELS = "assets/varrenmoor-3d/" + DEFAULT_FOLDER


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def bridge(op, **args):
    """Call foundry-bridge/bridge.ps1 (the relay must be running). Returns parsed JSON."""
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(BRIDGE), "-Op", op, "-Args", json.dumps(args)], capture_output=True)
    out = r.stdout.decode("utf-8", "ignore").strip()
    if r.returncode != 0 or not out:
        raise RuntimeError(f"bridge {op} failed: {r.stderr.decode('utf-8', 'ignore')[-300:]}")
    return json.loads(out)


def uuid_id(u):
    return u.split(".")[-1]


def find(collection, name_or_id, kind=None):
    """Find a document in a collection by exact name (case-insensitive) or id/uuid. Returns the listing row."""
    rows = bridge("list", collection=collection)
    key = name_or_id.lower()
    for r in rows:
        if kind and r.get("type") != kind:
            continue
        if r["name"].lower() == key or r["uuid"] == name_or_id or uuid_id(r["uuid"]) == name_or_id:
            return r
    raise LookupError(f"{collection} not found: {name_or_id}")


def folder_id(path, ftype, create=True):
    """Folder id by name (or 'A/B' path, matched on the last part) and document type; created if missing."""
    name = path.split("/")[-1]
    for r in bridge("list", collection="Folder"):
        if r["name"].lower() == name.lower() and r.get("type") == ftype:
            return uuid_id(r["uuid"])
    if not create:
        raise LookupError(f"folder not found: {path}")
    return uuid_id(bridge("create", documentName="Folder", data={"name": name, "type": ftype})["uuid"])


# ---------------------------------------------------------------- scene geometry
def scene_frame(scene_uuid):
    """Mapping from model metres to scene pixels for a scene's main model tile (the first tile whose model has a .scene.json sidecar)."""
    sc = bridge("get", uuid=scene_uuid)
    for t in sc.get("tiles", []):
        f = t.get("flags", {}).get("levels-3d-preview", {})
        m = f.get("model3d") or ""
        if not m.endswith(".glb"):
            continue
        stem = Path(m).stem
        found = list(OUT.rglob(stem + ".scene.json"))
        if not found:
            continue
        side = json.loads(found[0].read_text())
        sx, sy, sz = side["size_m"]
        shift = side.get("shift", [0, 0, 0])
        return dict(scene=sc, tile=t, cx=t["x"], cy=t["y"], pxm_x=t["width"] / sx, pxm_y=t["height"] / sy,
                    pxm_z=(f.get("depth") or sz * K) / sz, shift=shift, base_elev=t.get("elevation", BASE_ELEV), model=stem)
    raise LookupError("no model tile with a sidecar found in that scene; pass --px x,y instead")


def to_scene(frame, x, y, z=0.1):
    """Generator/model coordinates (metres; z = surface height above the model's base) -> (px, py, elevation_ft)."""
    sh = frame["shift"]
    px = frame["cx"] + (x + sh[0]) * frame["pxm_x"]
    py = frame["cy"] - (y + sh[1]) * frame["pxm_y"]
    ft_per_m = FT * frame["pxm_z"] / K
    return round(px), round(py), round(frame["base_elev"] + (z + sh[2]) * ft_per_m, 2)


def parse_at(s):
    v = [float(x) for x in s.split(",")]
    return (v + [0.1])[:3] if len(v) == 2 else v[:3]
