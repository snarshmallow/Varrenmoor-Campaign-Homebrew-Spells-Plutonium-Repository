"""Heightmap painting: brush maths, the non-destructive edit layer, previews. Shared by the panel (Terrain paint tab) and the tests.

The edit layer is a separate file pair next to the generated terrain, never the terrain itself:
  world/<place>/heightmap_edits.npz    delta (float32 feet, same shape as the terrain worldio hands out: node (i,j) at x=j*cell, y=i*cell, y down)
  world/<place>/heightmap_edits.json   version, shape, cell_ft, updated, stroke log (the recipe: replayable), summary
worldio.load_terrain adds `delta` to the loaded heights (every source: base / patched / carved), so regenerating terrain.py output keeps the edits.
Painting works on a WORKING copy (illustrator/out/panel/<place>/heightmap_paint/); `save` copies it into the world folder (the layer the pipeline sees),
`discard` throws the working copy away, `reset` empties the layer.  Set VB_HEIGHT_EDITS=0 to make worldio ignore the layer.

  python heightmap_paint.py apply-strokes --place P --strokes strokes.json [--mode append|replace|replay|undo-last]
  python heightmap_paint.py export-preview --place P [--max-px 512] [--contour-ft 10] [--png out.png] [--bin-dir DIR] [--layer work|saved|base]
  python heightmap_paint.py stats --place P [--layer work|saved]
  python heightmap_paint.py save --place P         | discard --place P | reset --place P [--layer work|saved|both]
Every command prints one JSON object. Stroke JSON (feet, x east, y south):
  {"tool": raise|lower|smooth|flatten|noise|set|ridge|valley|river, "points": [[x,y],...], "radius_ft": 30, "strength": 0.5 (0..1),
   "falloff": smooth|linear|sharp|round|constant, "hardness": 0..1 (inner plateau), "height_ft": target (flatten: default = height at the first point; set: required;
   ridge / valley: crest height / depth, default 15), "rate_ft": raise / lower / noise amplitude per dab (default 2), "depth_ft": river (default 6),
   "bank_slope": river bank rise per foot (default 0.6), "noise_scale_ft": default radius/2, "seed": int, "spacing": dab spacing as a fraction of the radius (default 0.25)}
"""
import argparse
import json
import os
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

VERSION = 1
TOOLS = ("raise", "lower", "smooth", "flatten", "noise", "set", "ridge", "valley", "river")
FALLOFFS = ("smooth", "linear", "sharp", "round", "constant")
DAB_TOOLS = ("raise", "lower", "smooth", "flatten", "set")
EDITS_NAME = "heightmap_edits"
MAX_SEGMENTS = 400
MAX_POINTS = 5000


# ------------------------------------------------------------------ brush maths
def falloff_weight(d, radius, hardness=0.0, falloff="smooth"):
    """Brush weight 0..1 at distance d (array ok): 1 inside hardness*radius, then the falloff curve down to 0 at radius."""
    if radius <= 0:
        raise ValueError("radius must be positive")
    hardness = min(max(float(hardness), 0.0), 0.999)
    t = np.clip(np.asarray(d, float) / radius, 0.0, None)
    u = np.clip((t - hardness) / (1.0 - hardness), 0.0, 1.0)
    if falloff == "smooth":
        w = 1.0 - u * u * (3.0 - 2.0 * u)
    elif falloff == "linear":
        w = 1.0 - u
    elif falloff == "sharp":
        w = (1.0 - u) ** 2
    elif falloff == "round":
        w = np.sqrt(np.clip(1.0 - u * u, 0.0, 1.0))
    elif falloff == "constant":
        w = np.where(t <= 1.0, 1.0, 0.0)
    else:
        raise ValueError(f"unknown falloff {falloff!r}; have {', '.join(FALLOFFS)}")
    return w


def value_noise(x, y, seed=0, scale=20.0, octaves=2):
    """Deterministic value noise in [-1, 1] at world coordinates (feet): same place, same value, whatever the stroke."""
    x = np.asarray(x, float) / scale
    y = np.asarray(y, float) / scale
    out = np.zeros(np.broadcast(x, y).shape)
    amp, tot = 1.0, 0.0
    with np.errstate(over="ignore"):
        for o in range(octaves):
            xi, yi = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
            fx, fy = x - xi, y - yi
            sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)

            def lat(ix, iy):
                n = ((ix & 0xFFFFFFFF).astype(np.uint32) * np.uint32(374761393) + (iy & 0xFFFFFFFF).astype(np.uint32) * np.uint32(668265263)
                     + np.uint32((seed * 2246822519 + o * 3266489917) & 0xFFFFFFFF))
                n = (n ^ (n >> np.uint32(13))) * np.uint32(1274126177)
                n = n ^ (n >> np.uint32(16))
                return n.astype(np.float64) / 4294967295.0 * 2.0 - 1.0
            v = (lat(xi, yi) * (1 - sx) + lat(xi + 1, yi) * sx) * (1 - sy) + (lat(xi, yi + 1) * (1 - sx) + lat(xi + 1, yi + 1) * sx) * sy
            out += v * amp
            tot += amp
            amp *= 0.5
            x, y = x * 2.0, y * 2.0
    return out / tot


def validate_stroke(s):
    """-> normalised stroke dict (raises ValueError with a readable message)."""
    if not isinstance(s, dict):
        raise ValueError("a stroke is an object")
    tool = s.get("tool")
    if tool not in TOOLS:
        raise ValueError(f"unknown tool {tool!r}; have {', '.join(TOOLS)}")
    pts = s.get("points")
    if not isinstance(pts, list) or not pts:
        raise ValueError("a stroke needs points [[x, y], ...]")
    if len(pts) > MAX_POINTS:
        raise ValueError(f"stroke has {len(pts)} points; the limit is {MAX_POINTS}")
    P = []
    for p in pts:
        if not (isinstance(p, (list, tuple)) and len(p) >= 2 and all(isinstance(v, (int, float)) and np.isfinite(v) for v in p[:2])):
            raise ValueError("every point is [x, y] in feet")
        P.append([float(p[0]), float(p[1])])
    r = float(s.get("radius_ft", 30.0))
    if not (r > 0):
        raise ValueError("radius_ft must be positive")
    fo = s.get("falloff", "smooth")
    if fo not in FALLOFFS:
        raise ValueError(f"unknown falloff {fo!r}; have {', '.join(FALLOFFS)}")
    out = dict(s)
    out.update(tool=tool, points=P, radius_ft=r, falloff=fo, strength=min(max(float(s.get("strength", 0.5)), 0.0), 1.0),
               hardness=min(max(float(s.get("hardness", 0.0)), 0.0), 1.0))
    if tool == "set" and s.get("height_ft") is None:
        raise ValueError("the set-height brush needs height_ft")
    for k in ("height_ft", "rate_ft", "depth_ft", "bank_slope", "noise_scale_ft", "spacing"):
        if s.get(k) is not None:
            out[k] = float(s[k])
    if s.get("seed") is not None:
        out["seed"] = int(s["seed"])
    return out


def _resample(pts, step):
    """Points along the polyline at about `step` spacing (keeps the end points) -> (n,2) array."""
    P = np.asarray(pts, float)
    if len(P) == 1:
        return P
    seg = np.hypot(*(P[1:] - P[:-1]).T)
    L = np.concatenate([[0.0], np.cumsum(seg)])
    if L[-1] <= 1e-9:
        return P[:1]
    n = max(int(np.ceil(L[-1] / step)), 1)
    s = np.linspace(0.0, L[-1], n + 1)
    return np.stack([np.interp(s, L, P[:, 0]), np.interp(s, L, P[:, 1])], -1)


def _window(shape, cell, pts, pad):
    P = np.asarray(pts, float)
    i0 = max(int(np.floor((P[:, 1].min() - pad) / cell)), 0)
    i1 = min(int(np.ceil((P[:, 1].max() + pad) / cell)) + 1, shape[0])
    j0 = max(int(np.floor((P[:, 0].min() - pad) / cell)), 0)
    j1 = min(int(np.ceil((P[:, 0].max() + pad) / cell)) + 1, shape[1])
    if i1 <= i0 or j1 <= j0:
        return None
    return i0, i1, j0, j1


def _grid(win, cell):
    i0, i1, j0, j1 = win
    return np.meshgrid(np.arange(j0, j1) * cell, np.arange(i0, i1) * cell)


def _polyline_dist(X, Y, pts):
    """Distance from every (X, Y) to the polyline, and the arc-length parameter (in points-index units, fractional) of the nearest point."""
    P = np.asarray(pts, float)
    if len(P) == 1:
        return np.hypot(X - P[0, 0], Y - P[0, 1]), np.zeros_like(X)
    best = np.full(X.shape, np.inf)
    par = np.zeros(X.shape)
    for k in range(len(P) - 1):
        ax, ay = P[k]
        bx, by = P[k + 1]
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = np.zeros(X.shape) if l2 <= 1e-12 else np.clip(((X - ax) * dx + (Y - ay) * dy) / l2, 0.0, 1.0)
        d = np.hypot(X - (ax + t * dx), Y - (ay + t * dy))
        m = d < best
        best = np.where(m, d, best)
        par = np.where(m, k + t, par)
    return best, par


def _decimate(pts, cell, radius):
    P = _resample(pts, max(cell, radius * 0.25))
    if len(P) - 1 > MAX_SEGMENTS:
        P = P[np.linspace(0, len(P) - 1, MAX_SEGMENTS + 1).round().astype(int)]
    return P


def _bilinear(h, cell, P):
    from scipy import ndimage as ndi
    return ndi.map_coordinates(h, [P[:, 1] / cell, P[:, 0] / cell], order=1, mode="nearest")


def apply_stroke(h, cell, stroke):
    """Apply one stroke to the height array `h` (float, in place) and return it. `cell` in feet; node (i,j) is at x=j*cell, y=i*cell."""
    from scipy import ndimage as ndi
    s = validate_stroke(stroke)
    tool, r, st = s["tool"], s["radius_ft"], s["strength"]
    hard, fo = s["hardness"], s["falloff"]
    rate = s.get("rate_ft", 2.0)
    pts = s["points"]
    if tool in DAB_TOOLS:
        step = max(cell * 0.5, r * s.get("spacing", 0.25))
        P = _resample(pts, step)
        target = s.get("height_ft")
        if tool == "flatten" and target is None:
            target = float(_bilinear(h, cell, P[:1])[0])
        for x, y in P:
            win = _window(h.shape, cell, [[x, y]], r)
            if win is None:
                continue
            i0, i1, j0, j1 = win
            X, Y = _grid(win, cell)
            w = falloff_weight(np.hypot(X - x, Y - y), r, hard, fo) * st
            sub = h[i0:i1, j0:j1]
            if tool == "raise":
                sub += w * rate
            elif tool == "lower":
                sub -= w * rate
            elif tool in ("flatten", "set"):
                sub += w * (target - sub)
            else:      # smooth: blend towards a blurred copy of the neighbourhood
                sig = max(r / cell / 3.0, 0.8)
                pad = int(np.ceil(sig * 3))
                big = h[max(i0 - pad, 0):i1 + pad, max(j0 - pad, 0):j1 + pad]
                bl = ndi.gaussian_filter(big, sig, mode="nearest")
                oi, oj = i0 - max(i0 - pad, 0), j0 - max(j0 - pad, 0)
                sub += w * (bl[oi:oi + sub.shape[0], oj:oj + sub.shape[1]] - sub)
        return h
    # stroke-wide tools: one field from the distance to the whole polyline (no build-up where the path overlaps itself)
    P = _decimate(pts, cell, r)
    win = _window(h.shape, cell, P, r)
    if win is None:
        return h
    i0, i1, j0, j1 = win
    X, Y = _grid(win, cell)
    dist, par = _polyline_dist(X, Y, P)
    w = falloff_weight(dist, r, hard, fo)
    sub = h[i0:i1, j0:j1]
    if tool == "noise":
        nz = value_noise(X, Y, s.get("seed", 0), s.get("noise_scale_ft", max(r / 2.0, cell * 2)))
        sub += st * rate * w * nz
    elif tool in ("ridge", "valley"):
        amp = abs(s.get("height_ft", 15.0))
        sub += (1 if tool == "ridge" else -1) * st * amp * w
    elif tool == "river":
        depth = s.get("depth_ft", 6.0)
        slope = max(s.get("bank_slope", 0.6), 0.0)
        R = _resample(pts, max(cell, 1.0))
        if len(R) < 2:
            R = np.vstack([R, R])
        z = _bilinear(h, cell, R)
        sig = max(r / max(cell, 1e-6) * 0.5, 1.0) if len(R) > 3 else 0.5
        z = ndi.gaussian_filter1d(z, sig, mode="nearest")
        z = np.minimum.accumulate(z) - depth          # a bed that never climbs downstream (first point = upstream)
        # nearest-point parameter refers to the decimated polyline; map it onto the resampled bed by arc length
        seg = np.hypot(*(P[1:] - P[:-1]).T) if len(P) > 1 else np.zeros(1)
        Lp = np.concatenate([[0.0], np.cumsum(seg)])
        s_arc = np.interp(par, np.arange(len(Lp)), Lp)
        seg2 = np.hypot(*(R[1:] - R[:-1]).T)
        Lr = np.concatenate([[0.0], np.cumsum(seg2)])
        scale = Lr[-1] / Lp[-1] if Lp[-1] > 1e-9 else 0.0
        bed = np.interp(s_arc * scale, Lr, z)
        bed_half = 0.5 * hard * r
        target = bed + slope * np.maximum(dist - bed_half, 0.0)
        sub -= np.maximum(sub - target, 0.0) * np.clip(w * st, 0.0, 1.0)
    return h


# ------------------------------------------------------------------ layer files
def _jload(p, dflt=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return dflt


def _jsave(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, separators=(",", ":"))


def layer_paths(dirpath):
    return os.path.join(dirpath, EDITS_NAME + ".npz"), os.path.join(dirpath, EDITS_NAME + ".json")


def work_dir(place, root=None):
    return os.path.join(REPO, "illustrator", "out", "panel", place, "heightmap_paint")


def saved_dir(place, root=None):
    import worldio
    return worldio.world_dir(place, root)


def load_layer(dirpath):
    """-> (delta or None, info dict). info = {strokes: [...], ...}"""
    npz, js = layer_paths(dirpath)
    if not (os.path.exists(npz) and os.path.exists(js)):
        return None, {"version": VERSION, "strokes": []}
    with np.load(npz) as z:
        d = z["delta"].astype(np.float32)
    info = _jload(js, {"version": VERSION, "strokes": []})
    info.setdefault("strokes", [])
    return d, info


def save_layer(dirpath, delta, info, cell_ft):
    npz, js = layer_paths(dirpath)
    os.makedirs(dirpath, exist_ok=True)
    np.savez_compressed(npz, delta=np.asarray(delta, np.float32))
    info = dict(info)
    info.update(version=VERSION, shape=[int(delta.shape[0]), int(delta.shape[1])], cell_ft=float(cell_ft), updated=time.strftime("%Y-%m-%dT%H:%M:%S"), summary=summarize(delta))
    _jsave(js, info)
    return info


def summarize(delta):
    if delta is None or not delta.size:
        return {"changed_cells": 0, "max_raise_ft": 0.0, "max_lower_ft": 0.0, "mean_abs_ft": 0.0, "bbox_cells": None}
    nz = np.abs(delta) > 1e-4
    n = int(nz.sum())
    if not n:
        return {"changed_cells": 0, "max_raise_ft": 0.0, "max_lower_ft": 0.0, "mean_abs_ft": 0.0, "bbox_cells": None}
    ii, jj = np.where(nz)
    return {"changed_cells": n, "max_raise_ft": round(float(delta.max()), 3), "max_lower_ft": round(float(delta.min()), 3), "mean_abs_ft": round(float(np.abs(delta[nz]).mean()), 3),
            "bbox_cells": [int(jj.min()), int(ii.min()), int(jj.max()), int(ii.max())]}


def overlay(place, h, meta, root=None):
    """The worldio hook: add the SAVED edit layer to the loaded terrain. -> (h, meta). No file / VB_HEIGHT_EDITS=0: unchanged (same objects)."""
    if os.environ.get("VB_HEIGHT_EDITS", "1") in ("0", "false", "off"):
        return h, meta
    d, info = load_layer(saved_dir(place, root))
    if d is None or not np.any(d):
        return h, meta
    meta = dict(meta)
    if d.shape != h.shape:       # terrain regenerated at another size / cell: carry the layer over by resampling
        from scipy import ndimage as ndi
        d = ndi.zoom(d, (h.shape[0] / d.shape[0], h.shape[1] / d.shape[1]), order=1)[:h.shape[0], :h.shape[1]]
        if d.shape != h.shape:
            d = np.pad(d, ((0, h.shape[0] - d.shape[0]), (0, h.shape[1] - d.shape[1])), mode="edge")
        meta["height_edits_warning"] = f"edit layer was {info.get('shape')} but the terrain is {list(h.shape)}: resampled"
    h = (h.astype(np.float32) + d).astype(np.float32)
    meta["elev_min"], meta["elev_max"] = float(h.min()), float(h.max())
    meta["relief_ft"] = meta["elev_max"] - meta["elev_min"]
    meta["height_edits"] = {"strokes": len(info.get("strokes", [])), "updated": info.get("updated"), **(info.get("summary") or {}), "hash": delta_hash(d)}
    return h, meta


def delta_hash(d):
    """Short fingerprint of an edit layer (float32 delta bytes): lets cached heights say which terrain they were computed against."""
    import hashlib
    return hashlib.sha1(np.ascontiguousarray(d, np.float32).tobytes()).hexdigest()[:16]


def base_terrain(place, root=None):
    """Terrain exactly as worldio loads it but without the edit layer (the thing the layer is stacked on)."""
    import worldio
    old = os.environ.get("VB_HEIGHT_EDITS")
    os.environ["VB_HEIGHT_EDITS"] = "0"
    try:
        h, meta = worldio.load_terrain(place, root=root)
    finally:
        if old is None:
            os.environ.pop("VB_HEIGHT_EDITS", None)
        else:
            os.environ["VB_HEIGHT_EDITS"] = old
    return h.astype(np.float32), meta


def _working(place, root, wdir):
    """Working layer (delta, info); starts from the saved layer when there is no working copy yet."""
    d, info = load_layer(wdir)
    if d is None:
        d, info = load_layer(saved_dir(place, root))
    return d, info


def run_strokes(base, cell, delta, strokes):
    """Replay `strokes` on base+delta (in a float64 copy); -> new delta (float32). Pure: the unit-tested core."""
    cur = base.astype(np.float64) + (delta.astype(np.float64) if delta is not None else 0.0)
    for s in strokes:
        apply_stroke(cur, cell, s)
    return (cur - base).astype(np.float32)


def apply_strokes(place, strokes, mode="append", root=None, wdir=None):
    wdir = wdir or work_dir(place, root)
    base, meta = base_terrain(place, root)
    cell = float(meta["cell_ft"])
    strokes = [validate_stroke(s) for s in strokes]
    delta, info = _working(place, root, wdir)
    if delta is not None and delta.shape != base.shape:
        delta = None
        info = {"strokes": []}
    log = list(info.get("strokes", []))
    if mode == "append":
        new = run_strokes(base, cell, delta, strokes)
        log += strokes
    elif mode == "replace":        # start from nothing: the given strokes ARE the layer
        new = run_strokes(base, cell, None, strokes)
        log = list(strokes)
    elif mode == "replay":         # re-run the stored stroke log on the current base (after the terrain was regenerated)
        new = run_strokes(base, cell, None, log)
    elif mode == "undo-last":
        if not log:
            raise ValueError("nothing to undo")
        log = log[:-1]
        new = run_strokes(base, cell, None, log)
    else:
        raise ValueError(f"unknown mode {mode!r}")
    info = save_layer(wdir, new, dict(info, strokes=log, place=place), cell)
    return {"ok": True, "mode": mode, "strokes_applied": len(strokes) if mode in ("append", "replace") else 0, "strokes_total": len(log), "summary": info["summary"], "work_dir": wdir}


def save(place, root=None, wdir=None):
    wdir = wdir or work_dir(place, root)
    sd = saved_dir(place, root)
    wn, wj = layer_paths(wdir)
    if not os.path.exists(wn):
        raise ValueError("no working edits to save")
    sn, sj = layer_paths(sd)
    d, _ = load_layer(wdir)
    if not np.any(d):               # an empty layer is the same as none
        for p in (sn, sj):
            if os.path.exists(p):
                os.remove(p)
        return {"ok": True, "saved": False, "note": "the layer is empty: the saved edit layer was removed", "path": sd}
    shutil.copyfile(wn, sn)
    shutil.copyfile(wj, sj)
    return {"ok": True, "saved": True, "path": sn, "summary": _jload(sj, {}).get("summary")}


def discard(place, root=None, wdir=None):
    wdir = wdir or work_dir(place, root)
    n = 0
    for p in layer_paths(wdir):
        if os.path.exists(p):
            os.remove(p)
            n += 1
    return {"ok": True, "removed_files": n}


def reset(place, root=None, wdir=None, layer="both"):
    out = {"ok": True, "removed": []}
    if layer in ("work", "both"):
        wdir = wdir or work_dir(place, root)
        for p in layer_paths(wdir):
            if os.path.exists(p):
                os.remove(p)
                out["removed"].append(p)
    if layer in ("saved", "both"):
        for p in layer_paths(saved_dir(place, root)):
            if os.path.exists(p):
                os.remove(p)
                out["removed"].append(p)
    return out


def _unsaved(wd, sd):
    """Working layer differs from the saved layer. A missing saved layer counts as all zeros, so undoing back to no edits reads clean."""
    if wd is None:
        return False
    if sd is None:
        return bool(np.any(wd))
    return wd.shape != sd.shape or not np.array_equal(wd, sd)


def stats(place, root=None, wdir=None, layer="work"):
    base, meta = base_terrain(place, root)
    d, info = load_layer(wdir or work_dir(place, root)) if layer == "work" else load_layer(saved_dir(place, root))
    if d is None and layer == "work":
        d, info = load_layer(saved_dir(place, root))
    fin = base + d if (d is not None and d.shape == base.shape) else base
    sd, sinfo = load_layer(saved_dir(place, root))
    wd, winfo = load_layer(wdir or work_dir(place, root))
    return {"ok": True, "layer": layer, "shape": list(base.shape), "cell_ft": float(meta["cell_ft"]), "base_min_ft": round(float(base.min()), 3), "base_max_ft": round(float(base.max()), 3),
            "final_min_ft": round(float(fin.min()), 3), "final_max_ft": round(float(fin.max()), 3), "strokes": len(info.get("strokes", [])), "summary": summarize(d),
            "has_saved": sd is not None, "has_work": wd is not None, "saved_strokes": len(sinfo.get("strokes", [])),
            "unsaved": _unsaved(wd, sd), "source": meta.get("source")}


# ------------------------------------------------------------------ preview
def hillshade(h, cell, azimuth=315.0, altitude=40.0, exag=1.0):
    gy, gx = np.gradient(h.astype(np.float64) * exag, cell)
    az, alt = np.radians(azimuth), np.radians(altitude)
    lx, ly, lz = np.sin(az) * np.cos(alt), -np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(gx ** 2 + gy ** 2 + 1.0)
    return np.clip((-gx * lx - gy * ly + lz) / nrm, 0.0, 1.0)


def render_rgb(h, cell, lo, hi, contour_ft=0.0, exag=1.0, delta=None):
    """Shaded relief (hillshade over an elevation tint) with optional contour lines (every contour_ft, every 5th darker) and a red / blue delta tint."""
    hs = hillshade(h, cell, exag=exag)
    shade = np.clip(0.9 + (hs - np.sin(np.radians(40))) * 0.55, 0.55, 1.1)
    t = np.clip((h - lo) / max(hi - lo, 1e-6), 0, 1)
    stops = np.array([0, .12, .45, .75, 1.0])
    cols = np.array([[70, 125, 70], [140, 170, 90], [170, 150, 105], [150, 140, 135], [250, 250, 250]], float)
    rgb = np.stack([np.interp(t, stops, cols[:, k]) for k in range(3)], -1) * shade[..., None]
    if delta is not None:
        m = np.clip(np.abs(delta) / max(float(np.abs(delta).max()), 1e-6), 0, 1)[..., None] * (np.abs(delta) > 1e-4)[..., None]
        tint = np.where(delta[..., None] >= 0, np.array([230.0, 60, 40]), np.array([40.0, 90, 230]))
        rgb = rgb * (1 - 0.55 * m) + tint * 0.55 * m
    if contour_ft and contour_ft > 0:
        q = np.floor(h / contour_ft)
        edge = np.zeros(h.shape, bool)
        edge[:, :-1] |= q[:, :-1] != q[:, 1:]
        edge[:-1, :] |= q[:-1, :] != q[1:, :]
        idx = (np.where(edge, q, 0) % 5 == 0) & edge
        rgb[edge] *= 0.62
        rgb[idx] *= 0.7
    return np.clip(rgb, 0, 255).astype(np.uint8)


def export_preview(place, root=None, wdir=None, max_px=512, contour_ft=0.0, png=None, bin_dir=None, layer="work", exag=1.0, show_delta=False):
    base, meta = base_terrain(place, root)
    cell = float(meta["cell_ft"])
    d = None
    if layer == "work":
        d, _ = _working(place, root, wdir or work_dir(place, root))
    elif layer == "saved":
        d, _ = load_layer(saved_dir(place, root))
    if d is not None and d.shape != base.shape:
        d = None
    fin = base + d if d is not None else base
    f = max(int(np.ceil(max(fin.shape) / float(max_px))), 1)
    hp = np.ascontiguousarray(fin[::f, ::f])
    dp = np.ascontiguousarray(d[::f, ::f]) if d is not None else np.zeros_like(hp)
    lo, hi = float(fin.min()), float(fin.max())
    out = {"ok": True, "place": place, "layer": layer, "factor": f, "pw": int(hp.shape[1]), "ph": int(hp.shape[0]), "cell_ft": cell, "size_ft": [(fin.shape[1] - 1) * cell, (fin.shape[0] - 1) * cell],
           "shape": list(fin.shape), "elev_min": lo, "elev_max": hi, "base_min": float(base.min()), "base_max": float(base.max()), "edited": bool(d is not None and np.any(d)),
           "sea_level_ft": float(meta.get("sea_level_ft", 0.0))}
    if png:
        from PIL import Image
        os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
        Image.fromarray(render_rgb(hp, cell * f, lo, hi, contour_ft, exag, dp if show_delta else None)).save(png)
        out["png"] = png
    if bin_dir:
        os.makedirs(bin_dir, exist_ok=True)
        hp.astype("<f4").tofile(os.path.join(bin_dir, "preview_h.bin"))
        dp.astype("<f4").tofile(os.path.join(bin_dir, "preview_d.bin"))
        _jsave(os.path.join(bin_dir, "preview.json"), out)
        out["bin_dir"] = bin_dir
    return out


# ------------------------------------------------------------------ CLI
def _strokes_arg(a):
    if a.strokes_json:
        o = json.loads(a.strokes_json)
    else:
        with open(a.strokes, encoding="utf-8") as f:
            o = json.load(f)
    return o.get("strokes", []) if isinstance(o, dict) else o


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--place", required=True)
        p.add_argument("--world-root", help="folder holding the place folders (default <repo>/world)")
        p.add_argument("--work-dir", help="working edit-layer folder (default illustrator/out/panel/<place>/heightmap_paint)")
    s = sub.add_parser("apply-strokes")
    common(s)
    s.add_argument("--strokes", help="JSON file: a list of strokes or {strokes: [...]}")
    s.add_argument("--strokes-json", help="the same as a JSON string")
    s.add_argument("--mode", default="append", choices=["append", "replace", "replay", "undo-last"])
    s = sub.add_parser("reset")
    common(s)
    s.add_argument("--layer", default="both", choices=["work", "saved", "both"])
    s = sub.add_parser("export-preview")
    common(s)
    s.add_argument("--max-px", type=int, default=512)
    s.add_argument("--contour-ft", type=float, default=0.0)
    s.add_argument("--exag", type=float, default=1.0)
    s.add_argument("--png")
    s.add_argument("--bin-dir")
    s.add_argument("--layer", default="work", choices=["work", "saved", "base"])
    s.add_argument("--show-delta", action="store_true")
    s = sub.add_parser("stats")
    common(s)
    s.add_argument("--layer", default="work", choices=["work", "saved"])
    s = sub.add_parser("save")
    common(s)
    s = sub.add_parser("discard")
    common(s)
    a = ap.parse_args(argv)
    root = a.world_root
    try:
        if a.cmd == "apply-strokes":
            strokes = _strokes_arg(a) if (a.strokes or a.strokes_json) else []
            if a.mode in ("append", "replace") and not strokes:
                raise ValueError("give --strokes FILE or --strokes-json")
            r = apply_strokes(a.place, strokes, a.mode, root, a.work_dir)
        elif a.cmd == "reset":
            r = reset(a.place, root, a.work_dir, a.layer)
        elif a.cmd == "export-preview":
            r = export_preview(a.place, root, a.work_dir, a.max_px, a.contour_ft, a.png, a.bin_dir, a.layer, a.exag, a.show_delta)
        elif a.cmd == "stats":
            r = stats(a.place, root, a.work_dir, a.layer)
        elif a.cmd == "save":
            r = save(a.place, root, a.work_dir)
        else:
            r = discard(a.place, root, a.work_dir)
    except (ValueError, OSError, KeyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
