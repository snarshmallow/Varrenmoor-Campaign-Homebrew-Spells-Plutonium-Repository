"""Scale-aware base terrain for places that have no hand-placed features (image-imported base maps).

terrain.generate() routes a spec here when it has no ridges / peaks / valleys / passes / natural block
(the v1 pipeline multiplies its ridged noise by a feature mask, so such a spec came out flat: relief of a few feet).
Specs that do have features never come here, so existing places are unchanged.

Spec keys (all optional; the panel's Base terrain block writes them):
  seed, cell_ft, base_elevation_ft   elevation of the middle of the relief range
  recipe        "rolling_hills" (default) | "valley" | "highland_ridge"
  relief_ft     overall broad-landform relief; default scale-aware: 3 % of the shorter map side, clamped 60..900 ft
  noise.scale_ft        LARGEST wavelength of the detail band (default 420); detail runs from there down to ~4 cells
  noise.ridged_amp_ft   amplitude of that detail band (default 60), added on top
                        of the landform; a natural multi-octave ridged + smooth fBm with domain warp (finer octaves have less
                        amplitude), no longer a single-scale ridged noise.
                        Its standard deviation is 0.22 * amp, capped at 0.025 * scale_ft so huge amp on a short wavelength cannot
                        make cliffs everywhere (amp 110 @ 200 ft -> 5 ft std, not 24)
  noise.base_amp_ft     extra smooth undulation (default 3)
  noise.landform_ft     amplitude of the mid-scale landform band between the broad hills (map/3) and the detail band
                        (default 0.3 * relief); wavelength map/4 down to noise.scale_ft
  erosion.stream_iterations  stream-power erosion passes (D8 flow routing, default 8, 0 = off) that cut dendritic valleys through
                        the landform; erosion.stream_strength (default 0.6)
  erosion.thermal_iterations / talus_slope / rate / smooth_sigma_cells   as in terrain.py (applied after the stream erosion)
  image_blend   0..1 (default 0 = off): gentle bias of the elevation by the base image's blurred luminance (light = higher)
  image_path    set by terrain.py from the place's underlay when image_blend > 0
Broad landform wavelength is proportional to the map (shorter side / 3), so a multi-mile map gets mile-scale hills.
"""
import os
import time

import numpy as np
from scipy import ndimage as ndi

import terrain as T
import terrain_relief as TR

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

    # natural multi-scale relief. 1) landform band: wavelengths map/4 down to noise.scale_ft (smooth + ridged fBm, warped)
    scale = float(nz.get("scale_ft", 420.0))
    amp = float(nz.get("ridged_amp_ft", 60.0))
    mass = 0.35 + 0.65 * broad
    lf_amp = float(nz.get("landform_ft", 0.3 * relief))
    lam_lf = max(short / 4.0, scale * 2.0)
    if lf_amp > 0:
        lf = TR.relief_field(rng, (ny, nx), cell, lam_lf, scale, hurst=1.0, ridge_mix=0.3, warp_frac=0.3, damp=0.0, octaves=7)
        h = h + lf_amp * 0.5 * (0.6 + 0.4 * broad) * lf
    # 2) detail band: largest wavelength noise.scale_ft, amplitude noise.ridged_amp_ft (octaves halve in wavelength; amplitude
    #    falls with hurst 0.85), stronger on higher ground
    wf = nz.get("warp_ft", 0.0)
    det = TR.relief_field(rng, (ny, nx), cell, scale, None, hurst=1.25, ridge_mix=0.2, warp_frac=0.25 + (0.15 if wf else 0.0),
                          damp=0.6, octaves=int(nz.get("octaves", 6)) + 2)
    sm = TR.relief_field(rng, (ny, nx), cell, scale * 1.4, None, hurst=1.0, ridge_mix=0.0, warp_frac=0.2, damp=0.0, octaves=3)
    det_sd = min(amp * 0.22, 0.025 * scale)       # std of the detail band; capped so its steepest scale stays walkable (rms slope <~ 0.16)
    h = h + mass ** 1.5 * det_sd * det + (nz.get("base_amp_ft", 3.0) + 0.08 * mass * amp) * sm

    # 3) stream-power erosion: dendritic valleys / ridges out of the combined surface (worked on a <=~300k-node grid,
    #    the change is then added back at full resolution so fine detail stays)
    n_st = int(er.get("stream_iterations", 8) or 0)
    if n_st > 0:
        sd0 = float(h.std())
        f = 1
        while (ny // f) * (nx // f) > 300000:
            f += 1
        hc = ndi.gaussian_filter(h, f * 0.5)[::f, ::f] if f > 1 else h
        he = TR.stream_erode(hc, cell * f, n_st, strength=float(er.get("stream_strength", 0.6)), talus=0.5)
        dlt = he - hc
        if f > 1:
            dlt = ndi.zoom(dlt, (ny / dlt.shape[0], nx / dlt.shape[1]), order=1)[:ny, :nx]
        h = h + dlt
        h = h.mean() + (h - h.mean()) * (sd0 / max(float(h.std()), 1e-9))     # erosion trims relief; keep the requested spread

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
