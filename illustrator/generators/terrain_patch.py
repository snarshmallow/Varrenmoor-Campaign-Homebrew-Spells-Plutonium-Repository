"""Terrain patch tool: lasso an area and reshape the heightmap (max/avg height, steepness, type).

  python terrain_patch.py preview|apply|undo|redo|list|remove|reorder --place bridgehollow
         [--polygon polygon.json] [--params params.json] [--root world_dir] [--out preview_dir]

Elevations are signed feet relative to a datum (terrain_meta.json "sea_level_ft", default 0). Negative
values are fully supported; nothing clamps at 0 or assumes positive values.

Polygon JSON: [[x_ft, y_ft], ...] (or {"polygon_ft": [...]}), origin top-left, y down (heightmap frame).

Params (all feet absolute elevations unless noted):
  terrain_type   mountain | rolling_hills | mesa | plateau | dunes | rocky_crags | ridge_line      (raise types)
                 bowl (alias basin) | valley | trench | sinkhole | seabed_shelf                    (depression types)
  max_height_ft  raise types: elevation of the highest point inside the polygon (fitted exactly)
  min_height_ft  depression types: elevation of the lowest point inside the polygon (fitted exactly)
  avg_height_ft  target mean elevation over the polygon area (fitted by a monotone remap of the shape)
  steepness      0..1: dome/rounded -> cone/sharp apex, steep flanks (mesa wall, trench/sinkhole wall)
  feather_ft     width of the edge blend (smoothstep of signed distance; C1 into the surroundings)
  seed           int, deterministic
  roughness      0..1 amount of fractal detail (0 = only the broad massif / coarse ridges, 1 = rock-scale breakup)
  erosion        mountain / rocky_crags / ridge_line: stream-power erosion passes that carve dendritic gullies
                 (0 = automatic, 6 passes when roughness > 0; max 24). Other types: thermal erosion iterations
  angle_deg      axis direction for ridge_line / valley / trench / dunes (0 = +x east, 90 = +y south)
  width_ft       optional ridge/trench half-width; wavelength_ft optional dune wavelength

Patch history: world/<place>/terrain/patches.json  {"version":1,"patches":[{id,order,enabled,polygon_ft,params,seed}],
"undone":[...]}. The base heightmap.npy is never modified; the replayed result is heightmap_patched.npy
(+ heightmap_patched_16.png, terrain_meta_patched.json).
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

import terrain_relief as TR

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

RAISE = {"mountain", "rolling_hills", "mesa", "plateau", "dunes", "rocky_crags", "ridge_line"}
DEPRESS = {"bowl", "valley", "trench", "sinkhole", "seabed_shelf"}
ALIASES = {"basin": "bowl", "hills": "rolling_hills", "crags": "rocky_crags", "ridge": "ridge_line",
           "seabed": "seabed_shelf", "pit": "sinkhole"}
NATURAL = {"mountain", "rocky_crags", "ridge_line"}     # stream-power erosion + multi-octave ridged detail
DEFAULTS = dict(terrain_type="mountain", steepness=0.5, feather_ft=120.0, seed=1, roughness=0.4, erosion=0,
                angle_deg=0.0)


def sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sea_level(meta):
    return float(meta.get("sea_level_ft", 0.0))


# ------------------------------------------------------------------ noise
def _fbm(rng, shape, cell, scale_ft, octaves=5, ridged=False):
    """Zero-mean-ish fractal field in about [-1,1], grid-global so a patch is independent of polygon bounds."""
    out = np.zeros(shape)
    amp, tot, sc = 1.0, 0.0, scale_ft
    for _ in range(octaves):
        n = ndi.gaussian_filter(rng.standard_normal(shape), max(sc / cell / 2.0, 0.6), mode="wrap")
        n /= (n.std() + 1e-9)
        if ridged:
            n = 1.0 - np.abs(np.tanh(n * 0.9)) * 2.0 + 0.0  # ridges at zero crossings, range ~[-1,1]
        out += amp * n
        tot += amp
        amp *= 0.5
        sc *= 0.5
    out /= tot
    return out / (np.abs(out).max() + 1e-9)


def _thermal(h, cell, iters, talus=0.7, rate=0.4):
    h = h.copy()
    lim = talus * cell
    for _ in range(int(iters)):
        d = np.zeros_like(h)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = np.roll(h, (dy, dx), (0, 1))
            diff = h - nb
            m = diff > lim
            mv = np.where(m, (diff - lim) * rate * 0.25, 0.0)
            d -= mv
            d += np.roll(mv, (-dy, -dx), (0, 1))
        h += d
    return h


# ------------------------------------------------------------------ geometry
def _grid(meta):
    cell = float(meta["cell_ft"])
    ny, nx = (int(meta["ny"]), int(meta["nx"])) if "ny" in meta else (None, None)
    return cell, ny, nx


def polygon_fields(poly_ft, shape, cell):
    """Exact inside mask and distance-to-boundary (ft) for each node."""
    import shapely
    from shapely.geometry import Polygon
    P = Polygon(poly_ft)
    if not P.is_valid:
        P = P.buffer(0)
    ny, nx = shape
    X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
    inside = shapely.contains_xy(P, X, Y)
    sd = np.zeros(shape)
    if inside.any():
        pts = shapely.points(X[inside], Y[inside])
        sd[inside] = shapely.distance(P.boundary, pts)
    return P, X, Y, inside, sd


def _local_base(E, inside, cell, sigma_cells):
    """Smooth extrapolation of the surroundings into the polygon (normalised convolution of outside nodes)."""
    m = (~inside).astype(float)
    num = ndi.gaussian_filter(E * m, sigma_cells, mode="nearest")
    den = ndi.gaussian_filter(m, sigma_cells, mode="nearest")
    ring = ndi.binary_dilation(inside, iterations=2) & ~inside
    fallback = E[ring].mean() if ring.any() else E.mean()
    base = np.where(den > 1e-3, num / np.maximum(den, 1e-3), fallback)
    # nodes where the support is weak lean on the ring mean
    wgt = sstep(den / 0.15)
    return wgt * base + (1 - wgt) * fallback


# ------------------------------------------------------------------ natural relief detail
def _crop_slices(inside, margin):
    ys, xs = np.where(inside)
    ny, nx = inside.shape
    return (slice(max(ys.min() - margin, 0), min(ys.max() + margin + 1, ny)),
            slice(max(xs.min() - margin, 0), min(xs.max() + margin + 1, nx)))


_DETAIL = dict(
    mountain=dict(lam=1 / 2.2, hurst=1.0, mix=0.3, spokes=True, a0=0.50, a1=0.55, erode=True),
    rocky_crags=dict(lam=1 / 3.2, hurst=0.9, mix=0.6, spokes=False, a0=0.45, a1=0.45, erode=True),
    ridge_line=dict(lam=1 / 2.6, hurst=1.0, mix=0.35, spokes=False, a0=0.20, a1=0.35, erode=True),
    rolling_hills=dict(lam=1 / 3.0, hurst=1.0, mix=0.0, spokes=False, a0=0.0, a1=0.18, erode=False),
    mesa=dict(lam=1 / 3.0, hurst=0.9, mix=0.4, spokes=False, a0=0.03, a1=0.14, erode=False),
    plateau=dict(lam=1 / 3.0, hurst=0.9, mix=0.4, spokes=False, a0=0.03, a1=0.12, erode=False))


def _detail(kind, env, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft):
    """Natural relief detail for one patch (arrays are the polygon's bounding crop). Returns (D, a): D in [-1, 1]
    (zero mean over the inside nodes) and the gain a, so that shape = env**k + a*D*env**(k/2) (see _fit).
    Multi-octave ridged/smooth fBm with domain warp (wavelengths from ~patch diameter/2 down to ~4 cells; octaves finer
    than diameter/8 are scaled by roughness**0.6, so roughness 0 leaves only coarse ridges), radial ridge lines from the crest
    (mountain), then a stream-power erosion pass that cuts dendritic valleys down the envelope's slope.
    `env` is the smooth massif envelope (0..1): erosion needs its large-scale slope to route water."""
    steep = float(np.clip(p["steepness"], 0, 1))
    rough = float(np.clip(p["roughness"], 0, 1))
    shape = d.shape
    rc = rough ** 0.6
    sp = _DETAIL[kind]
    lam = max(2 * rad_ft * sp["lam"], 10 * cell)
    wts = [1, 1, 1] + [rc] * 16
    D0 = TR.relief_field(rng, shape, cell, lam, None, hurst=sp["hurst"] - 0.3 * rough, ridge_mix=sp["mix"], warp_frac=0.2,
                         damp=0.0, octaves=9, weights=wts)
    if sp["spokes"]:
        th = np.arctan2(Y - centre_xy[1], X - centre_xy[0])
        rr = np.hypot(X - centre_xy[0], Y - centre_xy[1]) / max(rad_ft, 1.0)
        m = int(rng.integers(5, 9))
        n1, n2 = TR.band_noise(rng, shape, cell, lam * 0.9), TR.band_noise(rng, shape, cell, lam * 1.6)
        wob = np.clip(rr * 2.0, 0, 1) ** 2 * (0.5 * n1 + 0.7 * n2)                  # wandering spokes (radians), straight at the crest
        R = 1.0 - np.abs(np.sin(0.5 * m * th + rng.uniform(0, 6.28) + wob))            # 1 on a ridge line
        R = (R - R[inside].mean()) / (R[inside].std() + 1e-9)
        wr = sstep((rr - 0.10) / 0.35) * (1.0 - 0.5 * np.clip(rr, 0, 1))
        D0 = D0 + (0.30 + 0.45 * steep) * R * wr
    sg = (1.0 - rc) ** 4 * lam / 14.0 / cell          # low roughness: round off the ridge cusps (crest kinks carry fine-scale energy)
    if sg > 0.3:
        D0 = ndi.gaussian_filter(D0, sg)
    Dn = (D0 - D0[inside].mean()) / (D0[inside].std() + 1e-9)
    if sp["erode"] and rough > 0:
        n_it = int(p.get("erosion") or 0)
        n_it = 6 if n_it <= 0 else min(n_it, 24)
        Z0 = (env + 0.28 * np.clip(Dn, -3, 3) / 3.0 * (0.5 + steep * 0.3)) * relief_ft
        Z1 = TR.stream_erode(Z0, cell, n_it, strength=1.0 + 1.2 * rough, talus=1.1, a_ref_frac=0.02)
        Dn = (Z1 - env * relief_ft) / relief_ft
        Dn = (Dn - Dn[inside].mean()) / (Dn[inside].std() + 1e-9)
    sc = np.percentile(np.abs(Dn[inside]), 99.0) + 1e-9
    D = np.clip(Dn / sc, -1.0, 1.0)
    a = float(np.clip(sp["a0"] + sp["a1"] * rough, 0.0, 0.85))
    if rough == 0 and sp["erode"]:
        a = sp["a0"] * 0.6                                  # a coarse massif only (fine octaves are weighted 0)
    return D, a


def _with_detail(kind, env, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft):
    sl = _crop_slices(inside, 3)
    Dc, a = _detail(kind, env[sl], d[sl], X[sl], Y[sl], inside[sl], cell, p, rng, centre_xy, rad_ft, relief_ft)
    D = np.zeros(d.shape)
    D[sl] = Dc
    return D, a


# ------------------------------------------------------------------ shapes (depth/height fraction g in 0..1)
def build_shape(ttype, d, sd, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft=300.0, want_detail=False):
    """Base shape s (0..1). With want_detail=True returns (s, D, a): the patch shape is s**k + a*D*s**(k/2) (see _fit);
    D is None for types without natural detail (the legacy single-scale noise is then part of s)."""
    steep = float(np.clip(p["steepness"], 0, 1))
    rough = float(np.clip(p["roughness"], 0, 1))
    shape = d.shape
    diam = max(2 * rad_ft, 4 * cell)
    ang = np.radians(p["angle_deg"])
    ux, uy = np.cos(ang), np.sin(ang)
    u = (X - centre_xy[0]) * ux + (Y - centre_xy[1]) * uy       # along axis
    v = -(X - centre_xy[0]) * uy + (Y - centre_xy[1]) * ux      # across axis
    env = sstep(d / 0.25)
    D, a = None, 0.0
    dd = d
    nat = want_detail and ttype in ("mountain", "rocky_crags")
    if nat:   # organic footprint: perturb the distance-to-edge by a large-scale noise (stays 0 at the boundary)
        nz = TR.band_noise(rng, shape, cell, max(diam / 2.0, 8 * cell))
        dd = np.clip(d * (1 + 0.22 * np.clip(nz, -2, 2) / 2.0), 0, 1)
    prof = (1 - steep) * sstep(dd) + steep * dd ** (0.85)          # dome -> cone
    if ttype == "mountain":
        if want_detail:
            s = prof
            D, a = _with_detail("mountain", prof, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
        else:
            r = _fbm(rng, shape, cell, diam / 4, 5, ridged=True)
            s = prof * (1 - 0.55 * rough + 0.55 * rough * (0.5 + 0.5 * r)) * 1.0
            s = prof ** (1 + steep) * 0.4 + s * 0.6 if steep > 0 else s
    elif ttype == "rolling_hills":
        n = _fbm(rng, shape, cell, max(diam / 3.5, 8 * cell), 3)
        hills = 0.5 + 0.5 * n
        s = sstep(d / 0.3) * ((0.3 - 0.15 * rough) * prof + (0.7 + 0.15 * rough) * hills)
        if want_detail and rough > 0:
            D, a = _with_detail("rolling_hills", s, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
    elif ttype in ("mesa", "sinkhole"):
        wf = 0.12 + 0.45 * (1 - steep) ** 1.5
        n = _fbm(rng, shape, cell, diam / 5, 4)
        s = sstep(d / wf) * (1 + 0.04 * rough * n)
        if ttype == "mesa" and want_detail and rough > 0:
            D, a = _with_detail("mesa", s, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
    elif ttype in ("plateau", "seabed_shelf"):
        wf = 0.2 + 0.55 * (1 - steep)
        n = _fbm(rng, shape, cell, diam / 4, 4)
        s = sstep(d / wf) * (0.88 + 0.12 * prof) * (1 + 0.05 * rough * n)
        if ttype == "plateau" and want_detail and rough > 0:
            D, a = _with_detail("plateau", s, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
    elif ttype == "dunes":
        lam = float(p.get("wavelength_ft") or max(diam / 5, 6 * cell))
        warp = _fbm(rng, shape, cell, lam * 2, 3) * lam * 0.6
        ph = (u + warp) / lam + 0.15 * _fbm(rng, shape, cell, lam * 1.3, 2)
        wave = 0.5 + 0.5 * (np.sin(2 * np.pi * ph) + 0.3 * np.sin(4 * np.pi * ph + 0.8)) / 1.3
        s = sstep(d / 0.2) * (0.35 + 0.65 * wave) * (0.6 + 0.4 * prof)
    elif ttype == "rocky_crags":
        if want_detail:
            s = env * (0.45 * prof + 0.55) * (0.7 + 0.3 * prof)
            D, a = _with_detail("rocky_crags", s, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
        else:
            r = _fbm(rng, shape, cell, diam / 6, 6, ridged=True)
            s = env * (0.3 * prof + 0.7 * np.clip(0.5 + 0.5 * r, 0, 1) ** (1 + steep * 1.5)) * (0.7 + 0.3 * prof)
    elif ttype in ("ridge_line", "valley", "trench"):
        W = float(p.get("width_ft") or (0.6 * rad_ft if ttype != "trench" else 0.25 * rad_ft))
        if ttype == "trench":
            W *= (1.2 - 0.7 * steep)
        cross = np.clip(1 - np.abs(v) / max(W, cell), 0, 1)
        cross = (1 - steep) * sstep(cross) + steep * cross ** 0.9 if ttype == "ridge_line" else sstep(cross * (1 + 2 * steep))
        n = _fbm(rng, shape, cell, max(diam / 4, 6 * cell), 3)
        s = np.sqrt(sstep(d / 0.2)) * cross * (0.85 + 0.15 * n * (0.3 + rough))
        if ttype == "ridge_line" and want_detail:
            D, a = _with_detail("ridge_line", s, d, X, Y, inside, cell, p, rng, centre_xy, rad_ft, relief_ft)
    elif ttype == "bowl":
        n = _fbm(rng, shape, cell, diam / 4, 3)
        s = prof * (1 + 0.1 * rough * n)
    else:
        raise ValueError("unknown terrain_type " + ttype)
    s = np.where(inside, np.maximum(s, 0), 0)
    # smooth, lightly rounded
    s = ndi.gaussian_filter(s, 0.8) * (sd > 0)
    if want_detail:
        return s, (None if D is None else np.where(inside, D, 0.0)), a
    return s


# ------------------------------------------------------------------ main op
def _fit(E, base, w, s, inside, sign, ext_target, avg_target, core_w=0.9, D=None, a=0.0, ramp=None):
    """F = E + w*(base + sign*A*T_k - E). T_k is the shape remapped by k:  T_k = s**k  (legacy types), or
    s**k + a*D*s**(k/2) for natural-relief types (D in [-1, 1]: ridges/valleys ride on the massif envelope, so the exponent k
    that fixes the mean reshapes the massif but does not flatten the ridges the way a plain remap of the noisy shape would).
    Solve A,k so the extreme (max for sign>0, min for sign<0) and mean hit targets.
    The extreme is fitted on the CREST of T_k (nodes with T_k >= 0.93 of its core peak) inside the patch CORE (blend weight
    >= core_w, i.e. farther than ~0.7 feather from the edge), excluding nodes where the smooth ground already reaches the
    target. Existing ground inside the feather band is bounded by the seam-free edge blend and must not decide the fit:
    before this, rugged ground already above the requested max near the border drove A to 0 and the patch silently
    degraded to a smoothing of the old ground.
    Returns (shape, A, k, warn, diag) with diag = achievable mean range and limiting info."""
    Ei, wi, bi, si = E[inside], w[inside], base[inside], s[inside]
    smax = si.max()
    si = si / smax if smax > 0 else si
    Di = None if D is None else D[inside]
    # ABSOLUTE elevations: the shape rises from the local smooth ground (base) to the requested extreme, so
    # the peak lands on max_height_ft (not base + a constant, which pinned it to wherever the ground was highest)
    amp0 = np.maximum(sign * (ext_target - bi), 0.0)
    core = wi >= core_w
    if not core.any():
        core = wi >= wi.max() * 0.999
    tcache = {}
    edge = sstep(si / 0.3)        # detail fades to 0 toward the polygon edge (no sqrt-cusp / slope jump at the seam)

    def T_of(k):
        t = tcache.get(k)
        if t is None:
            t = si ** k
            if Di is not None:       # detail rides on the envelope but keeps ~sqrt of it on the low flanks (gullies run down to the foot)
                ka = a * min(1.0, (k + 0.15) / 0.65)             # a flat-topped massif (small k) carries proportionally less relief
                r = ka * Di * edge / np.sqrt(np.maximum(t, 1e-6))   # relative gully depth; saturate the cut so valleys keep >= 15 % of
                r = np.where(r < 0, -0.85 * np.tanh(-r / 0.85), r)  # the local envelope (no flat 'puddles' at the base level)
                t = t * (1.0 + r)
                if ramp is not None:
                    t = t * ramp[inside]       # shape grows from 0 over the feather band, so the seam gradient stays small for any k
            t = t / max(float(t[core].max()), 1e-12)
            tcache.clear()
            tcache[k] = t
        return t

    crest0 = core & (si >= 0.95)

    def crest_of(k):
        if Di is None:                       # legacy: crest of the unremapped shape
            return crest0 if crest0.any() else core
        t = T_of(k)
        c = core & (t >= 0.93) & (amp0 > 0)
        return c if c.any() else core

    def F_of(A, k):
        return Ei + wi * (bi + sign * A * amp0 * T_of(k) - Ei)

    def solve_A(k, tgt_ext=None):
        tgt_ext = ext_target if tgt_ext is None else tgt_ext
        t = T_of(k)
        c = crest_of(k)
        Ec, wc, bc, tc = Ei[c], wi[c], bi[c], t[c]
        a0 = np.maximum(sign * (tgt_ext - bi[c]), 0.0)
        lo, hi = 0.0, 1.0
        f = (lambda A: (Ec + wc * (bc + A * a0 * tc - Ec)).max()) if sign > 0 else \
            (lambda A: -(Ec + wc * (bc - A * a0 * tc - Ec)).min())
        tgt = tgt_ext if sign > 0 else -tgt_ext
        if f(0.0) >= tgt:          # ground already reaches the target in the core: nothing to add
            return 0.0
        # f is non-decreasing in A (sign*A*s*w moves the extreme outward)
        while f(hi) < tgt and hi < 4.0:     # A is a correction factor around 1 (w<1 at the peak of small patches)
            hi *= 2
        for _ in range(50):
            mid = 0.5 * (lo + hi)
            if f(mid) < tgt:
                lo = mid
            else:
                hi = mid
        return 0.5 * (lo + hi)

    def mean_of(k):
        # mean of F for the k with its own A (uses the A for the ORIGINAL ext target)
        A = solve_A(k)
        return F_of(A, k).mean(), A

    kl, kh = 0.02, 14.0
    ml = mean_of(kl)[0]
    mh = mean_of(kh)[0]
    lo_r, hi_r = min(ml, mh), max(ml, mh)
    # mean decreases with k for raise (increasing for depress)
    if sign > 0:
        target_k = kl if avg_target >= ml else kh if avg_target <= mh else None
    else:
        target_k = kl if avg_target <= ml else kh if avg_target >= mh else None
    warn = None
    diag = dict(avg_range=[float(lo_r), float(hi_r)], ext_target=float(ext_target), avg_target=float(avg_target))
    if target_k is not None:
        k = target_k
        word = "max" if sign > 0 else "min"
        direction = (avg_target > hi_r) if sign > 0 else (avg_target < lo_r)
        gc = crest_of(kl)
        gnd = float(F_of(0.0, kl)[gc].max()) if sign > 0 else float(F_of(0.0, kl)[gc].min())
        if solve_A(kl) == 0.0:
            why = "existing ground in the patch core already reaches %.1f ft (beyond the requested %s %.1f), so no %s was added" % (
                gnd, word, ext_target, "relief" if sign > 0 else "depth")
        else:
            why = "with %s %.1f the mean can only span this range (feather %s blend and the flat-top limit)" % (
                word, ext_target, "edge")
        need = None
        if direction and sign > 0 or (not direction and sign < 0):
            # extreme needed so a flat-topped shape reaches the requested mean
            lo_e, hi_e = ext_target, (ext_target + 4000.0 if sign > 0 else ext_target - 4000.0)
            for _ in range(30):
                mid = 0.5 * (lo_e + hi_e)
                A = solve_A(kl, mid)
                a1 = np.maximum(sign * (mid - bi), 0.0)
                m = (Ei + wi * (bi + sign * A * a1 * T_of(kl) - Ei)).mean()
                if (m < avg_target) == (sign > 0):
                    lo_e = mid
                else:
                    hi_e = mid
            need = 0.5 * (lo_e + hi_e)
            diag["needed_ext"] = float(need)
        warn = "avg_height_ft %.1f outside achievable range [%.1f, %.1f]; clamped. %s." % (avg_target, lo_r, hi_r, why)
        if need is not None:
            warn += " avg %.0f needs %s height %s %.0f" % (avg_target, word, ">=" if sign > 0 else "<=", need)
    else:
        a_, b_ = kl, kh
        for _ in range(40):
            m = 0.5 * (a_ + b_)
            mm = mean_of(m)[0]
            if (mm > avg_target) == (sign > 0):
                a_ = m
            else:
                b_ = m
        k = 0.5 * (a_ + b_)
    A = solve_A(k)
    full = np.zeros_like(E)
    full[inside] = amp0 * T_of(k)
    return full, A, k, warn, diag


def apply_patch(heightmap, meta, polygon_ft, params, return_info=False):
    """Return a new heightmap with the patch applied on top of `heightmap` (not modified)."""
    p = dict(DEFAULTS)
    p.update({k: v for k, v in params.items() if v is not None})
    ttype = ALIASES.get(p["terrain_type"], p["terrain_type"])
    if ttype not in RAISE | DEPRESS:
        raise ValueError("unknown terrain_type %r" % p["terrain_type"])
    sign = 1 if ttype in RAISE else -1
    E = np.asarray(heightmap, dtype=np.float64)
    cell = float(meta["cell_ft"])
    P, X, Y, inside, sd = polygon_fields(polygon_ft, E.shape, cell)
    info = {"nodes_inside": int(inside.sum()), "warnings": []}
    if inside.sum() < 4:
        info["warnings"].append("polygon covers fewer than 4 nodes; unchanged")
        out = E.astype(np.float32)
        return (out, info) if return_info else out
    sdm = sd.max()
    # medial weight: distance transform normalised, lightly smoothed in the interior only (boundary stays exact)
    d = sd / sdm
    sig = max(0.05 * 2 * sdm / cell, 1.0)
    ds = ndi.gaussian_filter(d, sig) * 1.0
    bl = sstep(sd / max(3 * cell, 1e-6))
    d = (1 - bl) * d + bl * ds
    d = np.where(inside, d / max(d.max(), 1e-9), 0)
    # peak position = max of medial weight
    iy, ix = np.unravel_index(np.argmax(d), d.shape)
    centre = (X[iy, ix], Y[iy, ix])
    rng = np.random.default_rng(int(p["seed"]))
    base = _local_base(E, inside, cell, max(sdm / cell * 0.5, 6))
    sign_ext = float(p["max_height_ft"] if sign > 0 else p["min_height_ft"])
    relief_est = max(abs(sign_ext - float(base[inside].mean())), 30.0)
    s, Dn, a_gain = build_shape(ttype, d, sd, X, Y, inside, cell, p, rng, centre, sdm, relief_est, want_detail=True)
    if p["erosion"] and ttype not in NATURAL:
        amp = 100.0
        s = _thermal(s * amp, cell, p["erosion"]) / amp
        s = np.where(inside, np.maximum(s, 0), 0)
    feather = max(float(p["feather_ft"]), cell)
    # keep the original detail near the edge (equals E at the boundary), fading to the smooth base inside
    r = 1 - sstep(sd / (2 * feather))
    base = base * (1 - r) + E * r
    t_ = np.clip(sd / feather, 0, 1)
    w = t_ ** 3 * (t_ * (6 * t_ - 15) + 10)   # smootherstep: C2, 0 at boundary with zero slope/curvature; exactly 0 outside
    avg = float(p["avg_height_ft"])
    if sign > 0:
        ext = float(p["max_height_ft"])
    else:
        ext = float(p["min_height_ft"])
    g, A, k, warn, diag = _fit(E, base, w, s, inside, sign, ext, avg, D=Dn, a=a_gain, ramp=sstep(sd / (1.0 * feather)) if ttype in NATURAL else None)
    unused = "min_height_ft" if sign > 0 else "max_height_ft"
    if p.get(unused) is not None:
        info["warnings"].append("%s is ignored for %s patches (use %s)" % (
            unused, ttype, "max_height_ft" if sign > 0 else "min_height_ft"))
    if warn:
        info["warnings"].append(warn)
    elif k < 0.2 and ttype in NATURAL | {"rolling_hills"}:
        info["warnings"].append("avg_height_ft %.0f is close to max_height_ft %.0f (achievable %.0f..%.0f): most of the polygon sits near the top, "
                                "so the shape is a high massif/plateau with ridges rather than distinct peaks; lower the average for more relief" % (
                                    avg, ext, diag["avg_range"][0], diag["avg_range"][1]))
    if ttype in NATURAL:
        # keep the existing ground texture on the low flanks (it fades out where the new relief takes over), instead of a
        # smooth skirt around the massif
        f_new = np.clip(A * g / max(relief_est, 1.0), 0.0, 1.0)
        hf = E - ndi.gaussian_filter(E, max(200.0 / cell, 3.0), mode="nearest")      # zero-mean texture only (keeps Max/Avg exact)
        base = base + hf * (1.0 - r) * (1.0 - f_new) ** 2
    F = E + w * (base + sign * A * g - E)
    gx = F[inside].max() if sign > 0 else F[inside].min()
    if (sign > 0 and gx > ext + 2) or (sign < 0 and gx < ext - 2):
        info["warnings"].append("existing ground inside the polygon still reaches %.1f ft, %s the requested %s %.1f "
                                "(the peak of the new shape is at the requested height)" % (
                                    gx, "above" if sign > 0 else "below", "max" if sign > 0 else "min", ext))
    info.update(A=float(A), k=float(k), type=ttype, centre_ft=[float(centre[0]), float(centre[1])],
                max=float(F[inside].max()), min=float(F[inside].min()), mean=float(F[inside].mean()))
    dl = (F - E)[inside]
    info.update(diag, before_mean=float(E[inside].mean()), before_max=float(E[inside].max()), before_min=float(E[inside].min()),
                max_rise_ft=float(dl.max()), max_drop_ft=float(dl.min()), mean_change_ft=float(dl.mean()),
                peak_core_ft=float(F[inside][w[inside] >= 0.9].max() if (w[inside] >= 0.9).any() else F[inside].max()),
                feather_ft=feather)
    out = F.astype(np.float32)
    return (out, info) if return_info else out


# ------------------------------------------------------------------ history
def _paths(place, root=None):
    d = os.path.join(root or os.path.join(REPO, "world"), place, "terrain")
    return dict(dir=d, base=os.path.join(d, "heightmap.npy"), meta=os.path.join(d, "terrain_meta.json"),
                patches=os.path.join(d, "patches.json"), patched=os.path.join(d, "heightmap_patched.npy"),
                patched_meta=os.path.join(d, "terrain_meta_patched.json"),
                patched_png=os.path.join(d, "heightmap_patched_16.png"))


def load_base(place, root=None):
    P = _paths(place, root)
    return np.load(P["base"]), json.load(open(P["meta"], encoding="utf-8"))


def load_history(path):
    if os.path.exists(path):
        return json.load(open(path, encoding="utf-8"))
    return {"version": 1, "patches": [], "undone": []}


def save_history(path, hist):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(hist, f, indent=1)
        f.write("\n")


def replay(base, meta, patches, upto_id=None):
    h = np.asarray(base, dtype=np.float32)
    infos = []
    for pt in sorted((x for x in patches if x.get("enabled", True)), key=lambda x: x["order"]):
        h, info = apply_patch(h, meta, pt["polygon_ft"], pt["params"], return_info=True)
        info["id"] = pt["id"]
        infos.append(info)
        if upto_id and pt["id"] == upto_id:
            break
    return h, infos


def write_patched(h, meta, P):
    from PIL import Image
    np.save(P["patched"], h)
    m = dict(meta)
    m["elev_min"], m["elev_max"] = float(h.min()), float(h.max())
    m["relief_ft"] = m["elev_max"] - m["elev_min"]
    m.setdefault("sea_level_ft", 0.0)
    m["patched"] = True
    json.dump(m, open(P["patched_meta"], "w", encoding="utf-8"), indent=1)
    a = np.round((h - m["elev_min"]) / max(m["relief_ft"], 1e-6) * 65535).astype(np.uint16)
    Image.fromarray(a).save(P["patched_png"])


def rebuild(place, root=None):
    P = _paths(place, root)
    base, meta = load_base(place, root)
    hist = load_history(P["patches"])
    h, infos = replay(base, meta, hist["patches"])
    write_patched(h, meta, P)
    return h, infos


# ------------------------------------------------------------------ previews / checks
def hillshade(h, cell, azimuth=315.0, altitude=50.0, exag=0.6):
    gy, gx = np.gradient(h * exag, cell)
    az, alt = np.radians(azimuth), np.radians(altitude)
    lx, ly, lz = np.sin(az) * np.cos(alt), -np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(gx ** 2 + gy ** 2 + 1)
    return np.clip((-gx * lx - gy * ly + lz) / nrm, 0, 1)


def _color(h, sea, lo, hi):
    """Above datum: green->tan->grey->white. Below datum: blue ramp (deeper = darker)."""
    up = np.clip((h - sea) / max(hi - sea, 1e-6), 0, 1)
    stops = np.array([0, .12, .45, .75, 1.0])
    cols = np.array([[70, 125, 70], [140, 170, 90], [170, 150, 105], [150, 140, 135], [250, 250, 250]], float)
    rgb = np.stack([np.interp(up, stops, cols[:, k]) for k in range(3)], -1)
    dn = np.clip((sea - h) / max(sea - lo, 1e-6), 0, 1)
    blue = np.stack([np.interp(dn, [0, 1], [c0, c1]) for c0, c1 in ((120, 10), (170, 40), (215, 110))], -1)
    return np.where((h < sea)[..., None], blue, rgb)


def save_preview(h, meta, path, polygon_ft=None, zoom=4):
    from PIL import Image, ImageDraw
    cell, sea = float(meta["cell_ft"]), sea_level(meta)
    hs = hillshade(h, cell)
    shade = np.clip(0.9 + (hs - np.sin(np.radians(50))) * 1.1, 0.4, 1.15)
    img = _color(h, sea, min(h.min(), sea - 1), max(h.max(), sea + 1)) * shade[..., None]
    img = ndi.zoom(img, (zoom, zoom, 1), order=1)
    hz = ndi.zoom(h, zoom, order=1)
    # datum shoreline: pixels where the elevation crosses sea level
    cross = (np.sign(hz[:, 1:] - sea) != np.sign(hz[:, :-1] - sea))[:-1] | (np.sign(hz[1:, :] - sea) != np.sign(hz[:-1, :] - sea))[:, :-1]
    img[:-1, :-1][cross] = (255, 255, 255)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    if polygon_ft is not None:
        dr = ImageDraw.Draw(im)
        pts = [(x / cell * zoom, y / cell * zoom) for x, y in polygon_ft]
        dr.line(pts + [pts[0]], fill=(255, 40, 40), width=2)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    im.save(path)


def save_diff(before, after, meta, path, polygon_ft=None, zoom=4):
    from PIL import Image, ImageDraw
    cell = float(meta["cell_ft"])
    d = after.astype(float) - before.astype(float)
    m = max(np.abs(d).max(), 1e-6)
    t = d / m
    img = np.full(d.shape + (3,), 245.0)
    pos, neg = np.clip(t, 0, 1)[..., None], np.clip(-t, 0, 1)[..., None]
    img = img * (1 - pos) + np.array([200, 40, 30]) * pos
    img = img * (1 - neg) + np.array([30, 80, 200]) * neg
    img = ndi.zoom(img, (zoom, zoom, 1), order=1)
    im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(im)
    if polygon_ft is not None:
        pts = [(x / cell * zoom, y / cell * zoom) for x, y in polygon_ft]
        dr.line(pts + [pts[0]], fill=(0, 0, 0), width=1)
    dr.text((6, 6), "diff red=raised %+.0f ft  blue=lowered %+.0f ft" % (d.max(), d.min()), fill=(0, 0, 0))
    im.save(path)


def seam_check(before, after, meta, polygon_ft):
    """Gradient discontinuity at the patch boundary. Returns dict (all in ft/ft unless noted).
    outside_max_change: max |after-before| outside the polygon (must be 0).
    boundary_dgrad: max |grad(after)-grad(before)| over nodes within 1 cell of the boundary; dgrad_ratio = that / max over the patch (small => C1, no seam).
    boundary_dh: max |after-before| within 1 cell of the boundary (ft).
    max_patch_slope: max slope inside; step_ratio: max gradient jump between adjacent nodes near the boundary / max_patch_slope."""
    cell = float(meta["cell_ft"])
    P, X, Y, inside, sd = polygon_fields(polygon_ft, before.shape, cell)
    from shapely.geometry import Point
    import shapely
    dist = np.abs(shapely.distance(P.boundary, shapely.points(X.ravel(), Y.ravel()))).reshape(X.shape)
    band = dist <= cell
    near = dist <= cell
    d = after.astype(float) - before.astype(float)
    gy, gx = np.gradient(after.astype(float), cell)
    by, bx = np.gradient(before.astype(float), cell)
    dg = np.hypot(gx - bx, gy - by)
    slope = np.hypot(gx, gy)
    gjump = np.maximum(np.abs(np.diff(slope, axis=0, append=slope[-1:])), np.abs(np.diff(slope, axis=1, append=slope[:, -1:])))
    interior_dg = float(dg[inside].max())
    return dict(interior_max_dgrad=interior_dg, dgrad_ratio=float(dg[band].max() / max(interior_dg, 1e-9)),
                outside_max_change=float(np.abs(d[~inside & (dist > 0)]).max()) if (~inside).any() else 0.0,
                boundary_dgrad=float(dg[band].max()), boundary_dh=float(np.abs(d[near]).max()),
                max_patch_slope=float(slope[inside].max()),
                step_ratio=float(gjump[band].max() / max(slope[inside].max(), 1e-9)))


# ------------------------------------------------------------------ CLI
def _load_json(path):
    j = json.load(open(path, encoding="utf-8"))
    return j.get("polygon_ft", j.get("polygon", j)) if isinstance(j, dict) else j


def _next_id(hist):
    ids = [int(x["id"].split("_")[-1]) for x in hist["patches"] + hist.get("undone", []) if x["id"].startswith("patch_")]
    return "patch_%03d" % (max(ids + [0]) + 1)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["preview", "apply", "undo", "redo", "list", "remove", "reorder", "rebuild", "json"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--root", help="worlds directory (default <repo>/world)")
    ap.add_argument("--polygon")
    ap.add_argument("--params")
    ap.add_argument("--out", help="preview output directory")
    ap.add_argument("--id")
    ap.add_argument("--order", type=int)
    a = ap.parse_args(argv)
    P = _paths(a.place, a.root)
    base, meta = load_base(a.place, a.root)
    hist = load_history(P["patches"])
    if a.cmd == "list":
        for x in sorted(hist["patches"], key=lambda x: x["order"]):
            print(x["id"], x["order"], "on" if x.get("enabled", True) else "off", x["params"].get("terrain_type"))
        return 0
    if a.cmd == "json":     # machine-readable history for the panel
        print(json.dumps(hist))
        return 0
    if a.cmd == "rebuild":  # replay patches onto the (possibly regenerated) base heightmap
        h, infos = rebuild(a.place, a.root)
        print("rebuilt", len(infos), "patches; elevation %.0f..%.0f ft" % (h.min(), h.max()))
        return 0
    if a.cmd in ("preview", "apply"):
        poly = _load_json(a.polygon)
        params = json.load(open(a.params, encoding="utf-8"))
        before, _ = replay(base, meta, hist["patches"])
        after, info = apply_patch(before, meta, poly, params, return_info=True)
        chk = seam_check(before, after, meta, poly)
        print(json.dumps(dict(info=info, seam=chk), indent=1))
        if a.cmd == "preview":
            out = a.out or os.path.join(P["dir"], "patch_preview")
            os.makedirs(out, exist_ok=True)
            save_preview(after, meta, os.path.join(out, "preview_hillshade.png"), poly)
            save_diff(before, after, meta, os.path.join(out, "preview_diff.png"), poly)
            print("wrote previews to", out)
        else:
            order = max([x["order"] for x in hist["patches"]] + [0]) + 1
            hist["patches"].append(dict(id=_next_id(hist), order=order, enabled=True, polygon_ft=poly,
                                        params=params, seed=params.get("seed", DEFAULTS["seed"])))
            hist["undone"] = []
            save_history(P["patches"], hist)
            write_patched(after, meta, P)
            print("applied", hist["patches"][-1]["id"])
        return 0
    if a.cmd == "undo":
        if not hist["patches"]:
            print("nothing to undo")
            return 1
        last = max(hist["patches"], key=lambda x: x["order"])
        hist["patches"].remove(last)
        hist.setdefault("undone", []).append(last)
        print("undid", last["id"])
    elif a.cmd == "redo":
        if not hist.get("undone"):
            print("nothing to redo")
            return 1
        last = hist["undone"].pop()
        last["order"] = max([x["order"] for x in hist["patches"]] + [0]) + 1
        hist["patches"].append(last)
        print("redid", last["id"])
    elif a.cmd == "remove":
        hit = [x for x in hist["patches"] if x["id"] == a.id]
        if not hit:
            print("no such id")
            return 1
        hist["patches"].remove(hit[0])
        hist.setdefault("undone", []).append(hit[0])
        print("removed", a.id)
    elif a.cmd == "reorder":
        hit = [x for x in hist["patches"] if x["id"] == a.id]
        if not hit or a.order is None:
            print("need --id and --order")
            return 1
        hit[0]["order"] = a.order
    save_history(P["patches"], hist)
    rebuild(a.place, a.root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
