"""River meander + width model shared by the terrain generator and the water generator (one source of truth).

The river valley in terrain_spec.json (`valleys[]` entry with "river": true) holds the coarse route as [x, y, rel_floor_ft, side_slope]
points. An optional `"meander"` block turns that route into a gently sinuous centreline:

  "meander": {"preset": "gentle",            # straight | gentle | lazy (fills the numbers below; explicit numbers win)
              "amplitude_ft": 40,            # peak lateral offset of the bends from the coarse route (0 = no meander)
              "wavelength_ft": 640,          # main bend-to-bend wavelength; two weaker harmonics add small bends
              "seed": 1103,                  # phases of the harmonics (same seed = same river)
              "gorge_damp": 0.8,             # how much the bends are suppressed in the steep gorge (0..1)
              "width_floor_ft": 66, "width_gorge_ft": 34,   # mean channel width on the flat floor / in the gorge
              "width_var": 0.18,             # pool/riffle width noise (fraction of the width)
              "bars": true}                  # point-bar (sandbar) hints on inner bends

The bends die out at both map edges so the river enters and leaves where the spec says, and the bed stays the monotone profile
terrain_natural.enforce_river already builds (it follows the same dense path, so the carved valley and floodplain follow it).
Pure functions of the valley dict: terrain_natural and gen_bridgehollow both call `river_points(v)` / `river_geometry(v)`.
"""
import math

import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import CubicSpline

PRESETS = {
    "straight": dict(amplitude_ft=0.0, wavelength_ft=640.0, width_var=0.08),
    "gentle": dict(amplitude_ft=40.0, wavelength_ft=640.0, width_var=0.18),
    "lazy": dict(amplitude_ft=75.0, wavelength_ft=760.0, width_var=0.26),
}
DEFAULTS = dict(preset="gentle", seed=1103, gorge_damp=0.8, width_floor_ft=66.0, width_gorge_ft=34.0, bars=True, step_ft=25.0)


def resolve(m):
    """Merged meander parameters (preset < explicit numbers). `m` may be None/{} (-> gentle) or {'preset': 'straight'}."""
    m = dict(m or {})
    p = dict(DEFAULTS)
    pre = m.get("preset", p["preset"])
    p.update(PRESETS.get(pre, PRESETS["gentle"]))
    p.update({k: v for k, v in m.items() if v is not None})
    p["preset"] = pre
    return p


def _smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _dense(P, step):
    """Smooth dense route through the rows of P (x, y, rel, side) with ~`step` ft spacing."""
    P = np.asarray(P, float)
    seg = np.hypot(*np.diff(P[:, :2], axis=0).T)
    t = np.concatenate([[0], np.cumsum(seg)])
    cs = CubicSpline(t, P[:, :2], bc_type="natural")
    n = max(2, int(round(t[-1] / step)))
    tt = np.linspace(0, t[-1], n + 1)
    xy = cs(tt)
    rel = np.interp(tt, t, P[:, 2])
    side = np.interp(tt, t, P[:, 3])
    return np.c_[xy, rel, side]


def _normals(xy):
    d = np.gradient(xy, axis=0)
    n = np.stack([-d[:, 1], d[:, 0]], 1)
    return n / np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-9)[:, None]


def river_points(v):
    """Dense [x, y, rel, side] river route (step_ft apart) of a valley dict, meander applied. Deterministic."""
    ds = v.get("side_slope", 0.3)
    P = np.array([[p[0], p[1], p[2], p[3] if len(p) > 3 else ds] for p in v["points"]], float)
    m = resolve(v.get("meander"))
    R = _dense(P, m["step_ft"])
    amp = float(m["amplitude_ft"])
    if amp <= 0 or not v.get("meander"):
        return R
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(R[:, :2], axis=0).T))])
    rng = np.random.default_rng([int(m["seed"]) & 0x7FFFFFFF, 41])
    L = float(m["wavelength_ft"])
    off = np.zeros(len(s))
    for k, (wl, wt) in enumerate(((1.0, 1.0), (0.52, 0.34), (0.29, 0.12))):
        wlk = L * wl * rng.uniform(0.88, 1.14)
        off += wt * np.sin(2 * math.pi * s / wlk + rng.uniform(0, 2 * math.pi))
    off /= 1.1
    # bends fade out at both ends of the route (the river enters / leaves where the spec says) and are damped in the steep gorge
    env = _smooth((s) / 220.0) * _smooth((s[-1] - s) / 220.0)
    flat = ndi.gaussian_filter1d(_smooth((0.6 - R[:, 3]) / 0.4), 4, mode="nearest")
    env = env * (1.0 - float(m["gorge_damp"]) * (1.0 - flat))
    R = R.copy()
    R[:, :2] += _normals(R[:, :2]) * (amp * env * off)[:, None]
    return R


def sinuosity(cl, y0=0.0, y1=1500.0):
    """Channel length / straight distance, for the part of a centreline inside the map band y0..y1."""
    c = np.asarray(cl, float)
    c = c[(c[:, 1] >= y0) & (c[:, 1] <= y1)]
    L = float(np.hypot(*np.diff(c, axis=0).T).sum())
    return L / max(float(np.hypot(*(c[-1] - c[0]))), 1e-9), L


def widths(v, R):
    """Channel width along the dense route: wide and slow on the flat floor, narrow in the gorge, plus pool/riffle noise."""
    m = resolve(v.get("meander"))
    flat = ndi.gaussian_filter1d(_smooth((0.6 - R[:, 3]) / 0.4), 4, mode="nearest")
    w = m["width_gorge_ft"] + (m["width_floor_ft"] - m["width_gorge_ft"]) * flat
    rng = np.random.default_rng([int(m["seed"]) & 0x7FFFFFFF, 43])
    n = rng.normal(size=len(R))
    n = ndi.gaussian_filter1d(n, 4.0, mode="wrap")          # ~100 ft pools / riffles
    n /= max(np.abs(n).max(), 1e-9)
    return w * (1.0 + float(m["width_var"]) * n)


def _spline_dense(xy, w, step=10.0):
    s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(xy, axis=0).T))])
    n = max(2, int(s[-1] / step))
    t = np.linspace(0, s[-1], n + 1)
    c = CubicSpline(s, xy, bc_type="natural")(t)
    return c, np.interp(t, s, w)


def river_geometry(v):
    """-> dict(centerline [[x,y]] step_ft apart, widths [ft], outline [[x,y]] closed organic bank polygon,
    bars [[[x,y]...]] point-bar polygons, surface rel [ft], params)."""
    from shapely.geometry import Polygon
    m = resolve(v.get("meander"))
    R = river_points(v)
    w = widths(v, R)
    c, wc = _spline_dense(R[:, :2], w, 10.0)
    nrm = _normals(c)
    rng = np.random.default_rng([int(m["seed"]) & 0x7FFFFFFF, 47])
    # independent low-amplitude bank wobble (~60-90 ft wavelength) so the banks are not parallel curves
    wl = ndi.gaussian_filter1d(rng.normal(size=len(c)), 5, mode="wrap")
    wr = ndi.gaussian_filter1d(rng.normal(size=len(c)), 5, mode="wrap")
    wob = 0.05 * float(m["width_floor_ft"]) / max(np.abs(wl).max(), 1e-9)
    left = c + nrm * ((wc / 2) + wl * wob)[:, None]
    right = c - nrm * ((wc / 2) + wr * wob)[:, None]
    outline = np.vstack([left, right[::-1]])
    poly = Polygon(outline)
    if not poly.is_valid:
        poly = poly.buffer(0)
        outline = np.array(poly.exterior.coords)[:-1]
    bars = []
    if m.get("bars") and m["amplitude_ft"] > 0:
        # inner-bank point bars: where the channel curves most, a lens of sand hugging the inside of the bend
        d1 = np.gradient(c, axis=0)
        d2 = np.gradient(d1, axis=0)
        k = (d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]) / np.maximum(np.hypot(d1[:, 0], d1[:, 1]) ** 3, 1e-9)
        ks = ndi.gaussian_filter1d(k, 6)
        flat = np.interp(np.arange(len(c)) * 10.0, np.arange(len(R)) * m["step_ft"], R[:, 3])
        for i in np.argsort(-np.abs(ks)):
            if abs(ks[i]) < 0.35 * np.abs(ks).max() or flat[i] > 0.35:
                continue
            if i < 12 or i > len(c) - 12 or any(abs(i - j) < 40 for j in bars_idx(bars)):
                continue
            ln = 9 + int(5 * rng.random())                              # half length in 10 ft samples
            idx = np.arange(i - ln, i + ln + 1)
            tt = np.linspace(-1, 1, len(idx))
            prof = (1 - tt ** 2) ** 0.8
            wid = wc[idx] / 2
            # nrm is the left normal and the left bank is c + n*w/2: the inner bank is the left one where the curvature is positive
            sgn = 1.0 if ks[i] > 0 else -1.0
            bank = c[idx] + sgn * nrm[idx] * (wid * 0.98)[:, None]
            tip = c[idx] + sgn * nrm[idx] * (wid * (0.98 - 0.42 * prof))[:, None]
            tip = tip + rng.normal(0, 0.5, tip.shape)
            bars.append((i, np.vstack([bank, tip[::-1]]).round(1).tolist()))
            if len(bars) >= 4:
                break
    rel = np.interp(np.arange(len(c)) * 10.0, np.arange(len(R)) * m["step_ft"], R[:, 2])
    return {"centerline": R[:, :2].round(1).tolist(), "widths": w.round(1).tolist(), "outline": outline.round(1).tolist(),
            "bars": [b for _, b in bars], "rel": rel, "params": m, "dense": c, "dense_w": wc}


def bars_idx(bars):
    return [b[0] if isinstance(b, tuple) else -9999 for b in bars]
