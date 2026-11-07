"""Anti-terracing / anti-saw-tooth finishing for generated heightmaps (float32 feet, any cell size).

Root causes of the stair-steps in the v6 Bridgehollow map (measured, see out/bridgehollow_v7_notes.md):
  1. enforce_river(): the carve target used the nearest-river-point arc position (hence bed height) at every cell, so across
     the medial axis of each bend and past the river ends the target jumped by 10-70 ft in one cell: horizontal creases
     up to 800 ft from the river that shade and cast shadows as saw-tooth cliff edges. Fixed at source in terrain_natural.py.
  2. terraces(): deliberate 26 ft benches on steep faces (default strength 0.4) quantise elevation on exactly the faces
     that show up as terracing; default is now 0 (the knob stays).
This module is the safety net for any terrain (new places, patches):
  terrace_metrics(h, cell)        numbers + terrace_ok against TERRACE_LIMITS
  finish(h, cell, cfg, keep=None, seed=0)
        tangential (along-contour) edge-preserving diffusion weighted by slope, slope-weighted removal of the
        cell-scale component, low-amplitude noise on steep faces (so cliffs are not planar), and extrema restoration so ridge
        and peak elevations stay where the spec put them.
"""
import numpy as np
from scipy import ndimage as ndi

DEFAULTS = dict(
    enabled=True,
    slope_lo=0.45, slope_hi=1.0,        # smoothing weight ramps in over this rise/run range
    tangential_iters=6, tangential_k=0.22,
    hf_sigma_cells=1.2, hf_strength=0.55,   # remove the cell-scale component on steep ground only
    cliff_noise_ft=2.5, cliff_noise_ft_scale=55.0, cliff_slope_lo=0.7, cliff_slope_hi=1.3,
    keep_extrema=True,
)


def _sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _grad(h, cell):
    gy, gx = np.gradient(h, cell)
    return gx, gy


TERRACE_LIMITS = dict(slope_jump_p999=1.0, steep_d2_p99_ft=8.0, bin_score=0.30)


def terrace_metrics(h, cell, min_slope=0.5):
    """Terracing / stair-step / crease numbers (limits in TERRACE_LIMITS; v6 Bridgehollow: 3.19 / 20.7 / 0.136, fixed: 0.41 / 3.7 / 0.13).

    slope_jump_p999   99.9th percentile of the change of slope (rise/run) between neighbouring cells, whole map. A smooth
                      surface changes slope gently; a stair edge or a carve crease swings it by whole units in one cell.
    steep_d2_p99_ft   99th percentile of the second difference of elevation (ft per cell step) on slopes steeper than min_slope:
                      cell-scale terracing and saw-tooth faces show up here directly.
    bin_score         bench test: share of steep cells in the busiest of 8 bins of (elevation mod period) over periods
                      8..40 ft (0.125 = uniform; real benches / quantised elevations push it above 0.3).
    """
    h = np.asarray(h, dtype=np.float64)
    gx, gy = _grad(h, cell)
    s = np.hypot(gx, gy)
    ds = np.maximum(np.abs(np.diff(s, axis=0))[:, 1:], np.abs(np.diff(s, axis=1))[1:, :])
    d2y = np.abs(h[2:, 1:-1] - 2 * h[1:-1, 1:-1] + h[:-2, 1:-1])
    d2x = np.abs(h[1:-1, 2:] - 2 * h[1:-1, 1:-1] + h[1:-1, :-2])
    dd = np.maximum(d2y, d2x)
    steep = s[1:-1, 1:-1] > min_slope
    out = dict(steep_frac=float(steep.mean()), slope_jump_p999=float(np.percentile(ds, 99.9)),
               steep_d2_p99_ft=float(np.percentile(dd[steep], 99)) if steep.sum() > 20 else 0.0)
    best, bp = 0.125, 0.0
    z = h[1:-1, 1:-1][steep]
    if z.size > 20:
        for per in np.arange(8.0, 40.5, 2.0):
            c = np.histogram(np.mod(z, per) / per, bins=8, range=(0, 1))[0]
            f = c.max() / c.sum()
            if f > best:
                best, bp = f, per
    out.update(bin_score=float(best), bin_period_ft=float(bp))
    out["terrace_score"] = out["slope_jump_p999"]
    out["terrace_ok"] = bool(all(out[k] <= v for k, v in TERRACE_LIMITS.items()))
    return out


def tangential_diffuse(h, cell, weight, iters, k):
    """Diffuse only along the contour direction (h_tt), so slopes across a face are kept (cliffs stay steep) while
    jagged contour lines and cell-scale stair edges are ironed out. weight in 0..1 per cell."""
    h = h.copy()
    for _ in range(int(iters)):
        gx, gy = _grad(h, cell)
        hxx = np.gradient(gx, cell, axis=1)
        hyy = np.gradient(gy, cell, axis=0)
        hxy = 0.5 * (np.gradient(gx, cell, axis=0) + np.gradient(gy, cell, axis=1))
        g2 = gx * gx + gy * gy + 1e-4
        htt = (hxx * gy * gy - 2 * hxy * gx * gy + hyy * gx * gx) / g2     # curvature along the contour
        h += k * cell * cell * htt * weight
    return h


def _fbm(shape, cell, scale_ft, seed):
    rng = np.random.default_rng(seed)
    out = np.zeros(shape)
    amp, tot = 1.0, 0.0
    for o in range(3):
        sig = max(scale_ft / cell / (2 ** o) / 2.0, 0.6)
        n = ndi.gaussian_filter(rng.standard_normal(shape), sig, mode="wrap")
        n /= max(n.std(), 1e-9)
        out += amp * n
        tot += amp * amp
        amp *= 0.5
    return out / np.sqrt(tot)


def finish(h, cell, cfg=None, keep=None, seed=0):
    c = dict(DEFAULTS)
    c.update(cfg or {})
    if not c["enabled"]:
        return h
    h0 = np.asarray(h, dtype=np.float64)
    lo0, hi0 = h0.min(), h0.max()
    gx, gy = _grad(ndi.gaussian_filter(h0, 0.8, mode="nearest"), cell)
    s = np.hypot(gx, gy)
    w = _sstep((s - c["slope_lo"]) / max(c["slope_hi"] - c["slope_lo"], 1e-6))
    if keep is not None:
        w = w * (0.35 + 0.65 * np.clip(keep, 0, 1))
    w = ndi.gaussian_filter(w, 1.0, mode="nearest")
    h1 = tangential_diffuse(h0, cell, w, c["tangential_iters"], c["tangential_k"])
    if c["hf_strength"] > 0:
        lp = ndi.gaussian_filter(h1, c["hf_sigma_cells"], mode="nearest")
        h1 = h1 - c["hf_strength"] * w * (h1 - lp)                          # high-frequency part only, weighted by slope
    if c["cliff_noise_ft"] > 0:
        cw = _sstep((s - c["cliff_slope_lo"]) / max(c["cliff_slope_hi"] - c["cliff_slope_lo"], 1e-6))
        h1 = h1 + c["cliff_noise_ft"] * cw * _fbm(h1.shape, cell, c["cliff_noise_ft_scale"], seed + 4141)
    if c["keep_extrema"]:
        # smoothing shaves crests and fills hollows slightly: pull the extremes back to where the spec put them
        q_hi, q_lo = np.percentile(h1, 85), np.percentile(h1, 15)
        if h1.max() < hi0 - 0.01 and h1.max() > q_hi:
            h1 = h1 + (hi0 - h1.max()) * _sstep((h1 - q_hi) / (h1.max() - q_hi))
        if h1.min() > lo0 + 0.01 and h1.min() < q_lo:
            h1 = h1 - (h1.min() - lo0) * _sstep((q_lo - h1) / (q_lo - h1.min()))
        h1 = np.clip(h1, lo0, hi0)
    return h1.astype(np.asarray(h).dtype)
