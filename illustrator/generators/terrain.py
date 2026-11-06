"""Deterministic heightmap generator from artist constraints.

  python illustrator/generators/terrain.py [--place bridgehollow] [--cell 10] [--seed N] [--spec PATH] [--out DIR]

Spec (JSON, feet, origin top-left, y down; see world/bridgehollow/terrain_spec.json):
  size_ft [W, H], cell_ft, seed,
  base_elevation_ft  elevation of the base plane at the map centre
  base_tilt          [ft per ft in x, ft per ft in y] (negative y tilt = ground falls toward the south)
  ridges   [{points:[[x,y,h,(w)],...], width_ft, sharpness}]   h = height above the base plane, w optional per-point half width
  peaks    [{x,y,height,radius_ft,sharpness,mode:"max"|"add"}]  "add" makes a rise on top of everything else
  valleys / passes [{points:[[x,y,rel,(side_slope)],...], core_ft, side_slope}]
                   carve to floor = base plane + rel, walls rising at side_slope (ft/ft); rel is relative to the base plane
  noise    {scale_ft, octaves, lacunarity, gain, ridged_amp_ft, base_amp_ft, warp_ft, warp_scale_ft}
  erosion  {thermal_iterations, talus_slope, rate, smooth_sigma_cells}
Output: heightmap.npy (float32 feet, shape [ny, nx], node (i,j) at x=j*cell, y=i*cell, nx=W/cell+1),
heightmap_16.png (16-bit, linearly scaled between terrain_meta.json elev_min/elev_max) and terrain_meta.json.
Same spec + seed + cell size => identical output.
"""
import argparse
import json
import os
import sys
import time

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# ---------------------------------------------------------------- noise
def _value_noise(rng, X, Y, period_ft):
    """Smooth lattice noise in about [-1, 1] sampled at arbitrary (warped) coordinates."""
    gx, gy = X / period_ft, Y / period_ft
    nx, ny = int(np.ceil(gx.max())) + 4, int(np.ceil(gy.max())) + 4
    ox, oy = int(np.floor(min(gx.min(), 0))) - 2, int(np.floor(min(gy.min(), 0))) - 2
    nx, ny = nx - ox, ny - oy
    grid = rng.uniform(-1, 1, (ny, nx))
    return ndi.map_coordinates(grid, [gy - oy, gx - ox], order=3, mode="nearest")


def _fbm(rng, X, Y, scale, octaves, lac, gain, ridged):
    total, amp, f, norm = np.zeros_like(X), 1.0, 1.0, 0.0
    for _ in range(octaves):
        n = _value_noise(rng, X, Y, scale / f)
        if ridged:
            n = (1.0 - np.abs(n)) ** 2
        total += amp * n
        norm += amp
        amp *= gain
        f *= lac
    total /= norm
    total -= total.mean()
    m = np.abs(total).max()
    return total / m if m > 0 else total


# ---------------------------------------------------------------- feature fields
def _polyline_fields(X, Y, pts, ncols):
    """Distance from each cell to the polyline and the interpolated extra columns (pts[:,2:])."""
    P = np.asarray(pts, float)
    best = np.full(X.shape, np.inf)
    cols = [np.zeros(X.shape) for _ in range(ncols)]
    for a, b in zip(P[:-1], P[1:]):
        ab = b[:2] - a[:2]
        L2 = float(ab @ ab) or 1e-9
        t = np.clip(((X - a[0]) * ab[0] + (Y - a[1]) * ab[1]) / L2, 0, 1)
        d = np.hypot(X - (a[0] + t * ab[0]), Y - (a[1] + t * ab[1]))
        m = d < best
        best = np.where(m, d, best)
        for k in range(ncols):
            cols[k] = np.where(m, a[2 + k] + t * (b[2 + k] - a[2 + k]), cols[k])
    return best, cols




def _ridge_field(X, Y, r):
    pts = []
    default_w = r.get("width_ft", 350.0)
    for p in r["points"]:
        pts.append([p[0], p[1], p[2], p[3] if len(p) > 3 else default_w])
    d, (h, w) = _polyline_fields(X, Y, pts, 2)
    t = d / np.maximum(w, 1e-6)
    return h * (1.0 - np.clip(t, 0, 1)) ** r.get("sharpness", 1.4)


def _peak_field(X, Y, pk):
    d = np.hypot(X - pk["x"], Y - pk["y"])
    return pk["height"] * (1.0 - smoothstep(d / pk["radius_ft"])) ** pk.get("sharpness", 1.0)


def _carve(h, X, Y, base, v):
    default_s = v.get("side_slope", 0.3)
    pts = [[p[0], p[1], p[2], p[3] if len(p) > 3 else default_s] for p in v["points"]]
    d, (rel, s) = _polyline_fields(X, Y, pts, 2)
    target = base + rel + s * np.maximum(d - v.get("core_ft", 20.0), 0.0)
    return np.minimum(h, target)


# ---------------------------------------------------------------- erosion
def thermal_erosion(h, cell, iterations, talus_slope, rate=0.5):
    """Move material from cells steeper than talus_slope (rise/run) to their lower neighbours."""
    h = h.copy()
    offs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 2 ** 0.5), (-1, 1, 2 ** 0.5), (1, -1, 2 ** 0.5), (1, 1, 2 ** 0.5)]
    ny, nx = h.shape
    c = rate / 8.0
    for _ in range(iterations):
        pad = np.pad(h, 1, mode="edge")
        delta = np.zeros_like(pad)
        core = pad[1:-1, 1:-1]
        for dy, dx, dist in offs:
            nb = pad[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
            f = c * np.maximum(core - nb - talus_slope * cell * dist, 0.0)
            delta[1:-1, 1:-1] -= f
            delta[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx] += f
        h += delta[1:-1, 1:-1]
    return h


# ---------------------------------------------------------------- generate
def load_spec(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate(spec, cell_ft=None, seed=None, verbose=False):
    t0 = time.time()
    W, H = spec["size_ft"]
    cell = float(cell_ft or spec.get("cell_ft", 10))
    seed = int(spec.get("seed", 1) if seed is None else seed)
    rng = np.random.default_rng(seed)
    nx, ny = int(round(W / cell)) + 1, int(round(H / cell)) + 1
    xs, ys = np.arange(nx) * cell, np.arange(ny) * cell
    X, Y = np.meshgrid(xs, ys)

    tx, ty = spec.get("base_tilt", [0, 0])
    base = spec.get("base_elevation_ft", 0.0) + tx * (X - W / 2) + ty * (Y - H / 2)

    # constraint features, sampled in a warped frame so ridge lines and foothills wander organically
    nz = spec.get("noise", {})
    scale = nz.get("scale_ft", 500.0)
    fw = nz.get("feature_warp_ft", 0.0)
    if fw:
        fs = nz.get("feature_warp_scale_ft", 900.0)
        FX = X + fw * _fbm(rng, X + 9000, Y, fs, 3, 2.0, 0.5, False)
        FY = Y + fw * _fbm(rng, X, Y + 9000, fs, 3, 2.0, 0.5, False)
    else:
        FX, FY = X, Y
    F = np.zeros_like(X)
    for r in spec.get("ridges", []):
        F = np.maximum(F, _ridge_field(FX, FY, r))
    for pk in spec.get("peaks", []):
        if pk.get("mode", "max") == "max":
            F = np.maximum(F, _peak_field(FX, FY, pk))
    for pk in spec.get("peaks", []):
        if pk.get("mode") == "add":
            F = F + _peak_field(FX, FY, pk)
    h = base + F

    # domain-warped ridged + smooth noise, strongest on high ground
    Xw, Yw = X, Y
    wf = nz.get("warp_ft", 0.0)
    if wf:
        ws = nz.get("warp_scale_ft", scale * 1.4)
        Xw = X + wf * _fbm(rng, X, Y, ws, 3, 2.0, 0.5, False)
        Yw = Y + wf * _fbm(rng, X + 5000, Y + 5000, ws, 3, 2.0, 0.5, False)
    ridged = _fbm(rng, Xw, Yw, scale, nz.get("octaves", 5), nz.get("lacunarity", 2.0), nz.get("gain", 0.5), True)
    smooth = _fbm(rng, Xw, Yw, scale * 0.6, 4, 2.0, 0.5, False)
    fmax = max(F.max(), 1e-6)
    mass = np.clip(F / (0.6 * fmax), 0, 1) ** 1.2
    h = h + mass * nz.get("ridged_amp_ft", 60.0) * ridged \
        + (nz.get("base_amp_ft", 3.0) + 0.35 * mass * nz.get("ridged_amp_ft", 60.0)) * smooth

    # carve valleys and passes after noise so river beds stay clean
    for v in spec.get("valleys", []) + spec.get("passes", []):
        h = _carve(h, X, Y, base, v)

    er = spec.get("erosion", {})
    if er.get("thermal_iterations", 0):
        h = thermal_erosion(h, cell, int(er["thermal_iterations"]), er.get("talus_slope", 1.0), er.get("rate", 0.5))
    if er.get("smooth_sigma_cells", 0):
        h = ndi.gaussian_filter(h, er["smooth_sigma_cells"], mode="nearest")

    h = h.astype(np.float32)
    meta = {"size_ft": [W, H], "cell_ft": cell, "nx": nx, "ny": ny, "seed": seed,
            "elev_min": float(h.min()), "elev_max": float(h.max()),
            "relief_ft": float(h.max() - h.min()), "units": "feet",
            "node_convention": "h[i,j] at x=j*cell_ft, y=i*cell_ft (y down)"}
    if verbose:
        print(f"terrain {nx}x{ny} cells at {cell:g} ft, seed {seed}, "
              f"{meta['elev_min']:.0f}..{meta['elev_max']:.0f} ft (relief {meta['relief_ft']:.0f}), {time.time() - t0:.1f}s")
    return h, meta


def save(h, meta, outdir):
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    np.save(os.path.join(outdir, "heightmap.npy"), h)
    lo, hi = meta["elev_min"], meta["elev_max"]
    a = np.round((h - lo) / max(hi - lo, 1e-6) * 65535).astype(np.uint16)
    Image.fromarray(a).save(os.path.join(outdir, "heightmap_16.png"))
    with open(os.path.join(outdir, "terrain_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")


def load_heightmap(place, root=None):
    d = os.path.join(root or os.path.join(REPO, "world"), place, "terrain")
    h = np.load(os.path.join(d, "heightmap.npy"))
    meta = json.load(open(os.path.join(d, "terrain_meta.json"), encoding="utf-8"))
    return h, meta


# ---------------------------------------------------------------- preview
def hillshade(h, cell, azimuth=315.0, altitude=40.0, exag=1.0):
    gy, gx = np.gradient(h * exag, cell)          # y down: gy is d/dy (south)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)                  # downhill direction, compass-ish with y down
    az, alt = np.radians(azimuth), np.radians(altitude)
    # light direction vector in x(east), y(south), z(up); azimuth measured clockwise from north
    lx, ly, lz = np.sin(az) * np.cos(alt), -np.cos(az) * np.cos(alt), np.sin(alt)
    nx_, ny_, nz_ = -gx, -gy, np.ones_like(gx)
    nrm = np.sqrt(nx_ ** 2 + ny_ ** 2 + nz_ ** 2)
    return np.clip((nx_ * lx + ny_ * ly + nz_ * lz) / nrm, 0, 1)


def save_preview(h, meta, path, zoom=4):
    from PIL import Image
    hs = hillshade(h, meta["cell_ft"], exag=1.0)
    shade = np.clip(0.85 + (hs - np.sin(np.radians(40))) * 1.1, 0.35, 1.15)
    t = (h - meta["elev_min"]) / max(meta["elev_max"] - meta["elev_min"], 1e-6)
    stops = np.array([0, .12, .45, .75, 1.0])
    cols = np.array([[70, 125, 70], [140, 170, 90], [170, 150, 105], [150, 140, 135], [250, 250, 250]], float)
    rgb = np.stack([np.interp(t, stops, cols[:, k]) for k in range(3)], -1)
    img = rgb * shade[..., None]
    img = ndi.zoom(img, (zoom, zoom, 1), order=1)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--spec")
    ap.add_argument("--cell", type=float)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    ap.add_argument("--preview", help="also write a hillshade PNG here")
    a = ap.parse_args()
    root = os.path.join(REPO, "world", a.place)
    spec = load_spec(a.spec or os.path.join(root, "terrain_spec.json"))
    h, meta = generate(spec, a.cell, a.seed, verbose=True)
    out = a.out or os.path.join(root, "terrain")
    save(h, meta, out)
    print("wrote", out)
    if a.preview:
        save_preview(h, meta, a.preview)
        print("wrote", a.preview)
