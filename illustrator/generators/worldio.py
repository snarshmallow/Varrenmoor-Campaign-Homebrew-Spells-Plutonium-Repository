"""One shared loader so every generator reads the same current terrain and water.

  import worldio
  h, meta = worldio.load_terrain(place)            # source from env / panel_state.json / "auto"
  worldio.water_path(place)                          # water.json to read (world file or the panel's working file)
  worldio.status(place)                              # which terrain files exist, mtimes, which source is in use

Terrain sources (heights in signed feet, same grid convention as terrain.py):
  base     world/<place>/terrain/heightmap.npy (never edited by patches)
  patched  heightmap_patched.npy when present (terrain_patch.py replays patches.json onto the base), else base
  carved   illustrator/out/water/<place>/heightmap_carved.npy (water.py carve; made from the patched map) when present, else patched
  auto     carved if panel_state.json water.use_carved is true, else patched
Resolution order: explicit `source` argument, env VB_TERRAIN_SOURCE (set by the generators' --terrain-source flag),
panel_state.json terrain.source, then auto. Water: env VB_WATER_SOURCE (world|working), else panel_state water.use_working
(default false = world/<place>/water.json).
"""
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SOURCES = ("auto", "base", "patched", "carved")


def world_dir(place, root=None):
    return os.path.join(root or os.path.join(REPO, "world"), place)


def state_path(place, root=None):
    return os.path.join(world_dir(place, root), "panel_state.json")


def load_state(place, root=None):
    p = state_path(place, root)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def set_source(source=None, water=None):
    """Called by CLIs for --terrain-source / --water-source; later loads in this process follow it."""
    if source:
        if source not in SOURCES:
            raise SystemExit(f"--terrain-source must be one of {SOURCES}")
        os.environ["VB_TERRAIN_SOURCE"] = source
    if water:
        if water not in ("world", "working"):
            raise SystemExit("--water-source must be world or working")
        os.environ["VB_WATER_SOURCE"] = water


def _paths(place, root=None):
    d = os.path.join(world_dir(place, root), "terrain")
    wd = os.path.join(REPO, "illustrator", "out", "water", place)
    return dict(dir=d, base=os.path.join(d, "heightmap.npy"), meta=os.path.join(d, "terrain_meta.json"),
                patched=os.path.join(d, "heightmap_patched.npy"), patched_meta=os.path.join(d, "terrain_meta_patched.json"),
                carved=os.path.join(wd, "heightmap_carved.npy"), water_dir=wd, water_work=os.path.join(wd, "water.json"),
                water_world=os.path.join(world_dir(place, root), "water.json"))


def resolve_source(place, source=None, root=None):
    s = source or os.environ.get("VB_TERRAIN_SOURCE")
    st = load_state(place, root)
    if not s:
        s = st.get("terrain", {}).get("source") or "auto"
    if s == "auto":
        s = "carved" if st.get("water", {}).get("use_carved") else "patched"
    return s


def load_terrain(place, source=None, root=None):
    """-> (heights float32 [ny,nx], meta dict). meta gains `source` (the file kind really used) and `sea_level_ft` (default 0)."""
    P = _paths(place, root)
    want = resolve_source(place, source, root)
    used, path = "base", P["base"]
    if want in ("patched", "carved") and os.path.exists(P["patched"]):
        used, path = "patched", P["patched"]
    if want == "carved" and os.path.exists(P["carved"]):
        used, path = "carved", P["carved"]
    h = np.load(path)
    mp = P["patched_meta"] if used != "base" and os.path.exists(P["patched_meta"]) else P["meta"]
    with open(mp, encoding="utf-8") as f:
        meta = json.load(f)
    if used == "carved":
        meta = dict(meta)
        meta["elev_min"], meta["elev_max"] = float(h.min()), float(h.max())
        meta["relief_ft"] = meta["elev_max"] - meta["elev_min"]
        if os.path.exists(P["patched"]) and os.path.getmtime(P["carved"]) < os.path.getmtime(P["patched"]):
            meta["warning"] = "heightmap_carved.npy is older than heightmap_patched.npy: run the carve again"
    meta.setdefault("sea_level_ft", 0.0)
    o = meta.get("origin_ft")
    if o and (o[0] or o[1]):      # region child: the file is a crop at origin_ft; pad it (edge values) so node (i,j) is again at x=j*cell, y=i*cell
        c = float(meta["cell_ft"])
        pj, pi = int(round(o[0] / c)), int(round(o[1] / c))
        if h.shape[0] + pi > 6000 or h.shape[1] + pj > 6000:
            raise SystemExit("child terrain frame too large to pad: use --local-origin when extracting far from the parent origin")
        h = np.pad(h, ((pi, 0), (pj, 0)), mode="edge")
        meta = dict(meta)
        meta["padded_origin_ft"], meta["origin_ft"] = list(o), [0.0, 0.0]
        meta["nx"], meta["ny"] = int(h.shape[1]), int(h.shape[0])
        meta["size_ft"] = [(h.shape[1] - 1) * c, (h.shape[0] - 1) * c]
    meta["source"] = used
    meta["source_file"] = path
    return h, meta


def water_path(place, source=None, root=None):
    s = source or os.environ.get("VB_WATER_SOURCE")
    if not s:
        s = "working" if load_state(place, root).get("water", {}).get("use_working") else "world"
    P = _paths(place, root)
    if s == "working" and os.path.exists(P["water_work"]):
        return P["water_work"]
    return P["water_world"]


def status(place, root=None):
    P = _paths(place, root)
    mt = lambda p: os.path.getmtime(p) if os.path.exists(p) else None
    out = {k: {"path": P[k], "exists": os.path.exists(P[k]), "mtime": mt(P[k])}
           for k in ("base", "patched", "carved", "water_world", "water_work")}
    out["terrain_source"] = resolve_source(place, None, root)
    out["water_path"] = water_path(place, None, root)
    return out


if __name__ == "__main__":
    import sys
    pl = sys.argv[1] if len(sys.argv) > 1 else "bridgehollow"
    h, m = load_terrain(pl)
    print(json.dumps({"shape": list(h.shape), "source": m["source"], "elev": [float(h.min()), float(h.max())],
                      "status": status(pl)}, indent=1))
