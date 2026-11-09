"""Scale-aware base terrain for places that have no hand-placed features (image-imported base maps).

terrain.generate() routes a spec here when it has no ridges / peaks / valleys / passes / natural block
(the v1 pipeline multiplies its ridged noise by a feature mask, so such a spec came out flat: relief of a few feet).
Specs that do have features never come here, so existing places are unchanged.

Spec keys (all optional; the panel's Base terrain block writes them):
  seed, cell_ft, base_elevation_ft   elevation of the middle of the relief range
  recipe        "rolling_hills" (default) | "valley" | "highland_ridge"
  relief_ft     overall broad-landform relief; default scale-aware: 3 % of the shorter map side, clamped 60..900 ft
  noise.scale_ft        wavelength of the detail noise (default 420)
  noise.ridged_amp_ft   amplitude of the ridged detail noise at that wavelength (default 60), added on top of the landform
  noise.octaves/lacunarity/gain/warp_ft/base_amp_ft  as in terrain.py
  erosion.thermal_iterations / talus_slope / rate / smooth_sigma_cells   as in terrain.py
  image_blend   0..1 (default 0 = off): gentle bias of the elevation by the base image's blurred luminance (light = higher)
  image_path    set by terrain.py from the place's underlay when image_blend > 0
Broad landform wavelength is proportional to the map (shorter side / 3), so a multi-mile map gets mile-scale hills.
"""
import os
import time

import numpy as np
from scipy import ndimage as ndi

import terrain as T

RECIPES = ("rolling_hills", "valley", "highland_ridge")
FEATURE_KEYS = ("ridges", "peaks", "valleys", "passes", "natural")


def wants_basemap(spec):
    """True for a spec with no constraint features (or an explicit recipe), where v1 would be flat."""
    if "natural" in spec:
        return False
    return "recipe" in spec or not any(spec.get(k) for k in FEATURE_KEYS)


def default_relief(W, H):
    return float(np.clip(0.03 * min(W, H), 60.0, 900.0))


def _norm01(f):
    lo, hi = float(f.min()), float(f.max())
    return (f - lo) / (hi - lo) if hi > lo else np.zeros_like(f)


def _image_field(path, nx, ny):
    """Blurred luminance of the base image resampled to the grid, 0..1 (light = 1); None if unreadable."""
    try:
        from PIL import Image
        Image.MAX_IMAGE_PIXELS = None
        im = Image.open(path).convert("L")
        im.thumbnail((max(nx, 64), max(ny, 64)))
        a = np.asarray(im.resize((nx, ny), Image.BILINEAR), float) / 255.0
    except Exception:
        return None
    a = ndi.gaussian_filter(a, max(2.0, min(nx, ny) / 40.0), mode="nearest")
    return _norm01(a)


def generate(spec, cell_ft=None, seed=None, verbose=False):
    t0 = time.time()
    W, H = spec["size_ft"]
    cell = float(cell_ft or spec.get("cell_ft", 10))
    seed = int(spec.get("seed", 1) if seed is None else seed)
    rng = np.random.default_rng(seed)
    nx, ny = int(round(W / cell)) + 1, int(round(H / cell)) + 1
    X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
    nz, er = spec.get("noise", {}), spec.get("erosion", {})
    recipe = spec.get("recipe", "rolling_hills")
    if recipe not in RECIPES:
        raise ValueError("unknown terrain recipe %r (use one of %s)" % (recipe, ", ".join(RECIPES)))
    relief = float(spec.get("relief_ft") or default_relief(W, H))
    short = float(min(W, H))
    big = short / 3.0                                   # broad landform wavelength

    # broad landform, normalised to 0..1
    hills = T._fbm(rng, X, Y, big, 4, 2.0, 0.5, False)
    if recipe == "rolling_hills":
        broad = _norm01(hills)
    else:
        # a wandering axis along the long side (valley floor / ridge crest)
        wx = 0.25 * short * T._fbm(rng, X + 7000, Y, big * 1.3, 3, 2.0, 0.5, False)
        wy = 0.25 * short * T._fbm(rng, X, Y + 7000, big * 1.3, 3, 2.0, 0.5, False)
        d = np.abs(Y + wy - H / 2.0) if W >= H else np.abs(X + wx - W / 2.0)
        prof = T.smoothstep(d / (0.30 * short))         # 0 on the axis, 1 away from it
        if recipe == "valley":
            broad = _norm01(0.8 * prof + 0.2 * _norm01(hills))
        else:                                           # highland_ridge
            broad = _norm01(0.8 * (1.0 - prof) ** 1.3 + 0.2 * _norm01(hills))
    h = spec.get("base_elevation_ft", 0.0) + relief * (broad - 0.5)

    # detail: ridged noise at noise.scale_ft, stronger on higher ground; the amplitude is honoured as given
    scale = float(nz.get("scale_ft", 420.0))
    Xw, Yw = X, Y
    wf = nz.get("warp_ft", 0.0)
    if wf:
        ws = nz.get("warp_scale_ft", scale * 1.4)
        Xw = X + wf * T._fbm(rng, X, Y, ws, 3, 2.0, 0.5, False)
        Yw = Y + wf * T._fbm(rng, X + 5000, Y + 5000, ws, 3, 2.0, 0.5, False)
    amp = float(nz.get("ridged_amp_ft", 60.0))
    ridged = T._fbm(rng, Xw, Yw, scale, nz.get("octaves", 5), nz.get("lacunarity", 2.0), nz.get("gain", 0.5), True)
    smooth = T._fbm(rng, Xw, Yw, scale * 0.6, 4, 2.0, 0.5, False)
    mass = 0.35 + 0.65 * broad
    h = h + mass * amp * ridged + (nz.get("base_amp_ft", 3.0) + 0.35 * mass * amp) * smooth

    blend = float(spec.get("image_blend", 0) or 0)
    img_used = False
    if blend > 0 and spec.get("image_path") and os.path.exists(spec["image_path"]):
        f = _image_field(spec["image_path"], nx, ny)
        if f is not None:
            h = h + min(blend, 1.0) * relief * (f - 0.5)
            img_used = True

    if er.get("thermal_iterations", 0):
        h = T.thermal_erosion(h, cell, int(er["thermal_iterations"]), er.get("talus_slope", 1.0), er.get("rate", 0.5))
    if er.get("smooth_sigma_cells", 0):
        h = ndi.gaussian_filter(h, er["smooth_sigma_cells"], mode="nearest")

    h = h.astype(np.float32)
    meta = {"size_ft": [W, H], "cell_ft": cell, "nx": nx, "ny": ny, "seed": seed,
            "elev_min": float(h.min()), "elev_max": float(h.max()),
            "relief_ft": float(h.max() - h.min()), "units": "feet", "recipe": recipe,
            "node_convention": "h[i,j] at x=j*cell_ft, y=i*cell_ft (y down)"}
    if blend > 0:
        meta["image_blend"] = min(blend, 1.0) if img_used else 0.0
    if verbose:
        print(f"terrain {nx}x{ny} cells at {cell:g} ft, seed {seed}, recipe {recipe}, "
              f"{meta['elev_min']:.0f}..{meta['elev_max']:.0f} ft (relief {meta['relief_ft']:.0f}), {time.time() - t0:.1f}s")
    return h, meta
