"""Natural terrain pipeline (v2) for terrain.py. Enabled by a "natural" block in the terrain spec.

Everything is deterministic from spec seed (sub-streams are derived from the seed, not from call order).

natural block (all keys optional, defaults shown):
  smooth_step_ft 8        Catmull-Rom resampling step for ridge / valley / pass / spur polylines
  wander_ft 55            lateral wander amplitude of non-river polylines; wander_wavelength_ft 750
  width_var 0.3           +-fraction of half-width variation along a ridge; height_var 0.14 crest height variation
  union_p 4               p-norm used to merge ridges/spurs (smooth union, no creases); 0 = hard max
  crest_round 1.0         ridge profile (1-t^2)^(k*crest_round): rounded crest instead of a knife edge
  spurs {count_per_1000ft 2.4, length_ft [220,430], height_frac [0.35,0.62], width_ft [90,150], inward 0.85,
         clear_river_ft 160, clear_points [[x,y,r],...]}      enabled per ridge with "spurs": true
  rugged {octaves 6, gain 0.5, lacunarity 2.1, scale_ft, amp_ft} multifractal ridged noise, rotated per octave
  plateaus [{name, polygon [[x,y],..], elev_ft (absolute) | rel_ft (above base plane), tilt [dx,dy], edge_ft 70,
             noise_ft 3, strength 0.95}]   irregular (Chaikin + warp) benches blended into the terrain
  terraces {period_ft 26, strength 0.4, min_slope 0.28, max_slope 0.7}  benches on steep faces
  hydraulic {iterations 28, K 0.06, m 0.5, Kc 1.4, deposit 0.55, max_incise_ft 38, diffusion 0.08}
  thermal {iterations 140, talus_low 0.68, talus_high 1.15, rate 0.5, jitter 0.22}   angle of repose 34 deg at the foot
  hills_south {y_start 1150, amp_ft 26, scale_ft 300}  rounded rolling foothills at the south
  basin {amp_ft 3.2, scale_ft 260, mounds 16, mound_ft [1.5,5], bowl_ft 7, fan {x,y,radius_ft,height_ft,spread_deg}}
  keep_clear [[x,y,radius_ft],...]  areas that keep gentle relief (authority rise)
  river_bed true          valleys flagged "river": true get a monotone (never climbing) bed enforced at the end
  final_smooth_cells 0.8
"""
import math

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

import terrain as T

TAU = 2 * math.pi
MIN_PERIOD = [35.0]   # ft: octaves with a shorter period than ~3.5 cells are skipped (aliasing)
WARP_PAD = [0.0]
STAGES = {}     # filled when natural.debug_stages is true (name -> heightmap copy)


def sstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sub_rng(seed, *key):
    return np.random.default_rng([int(seed) & 0x7FFFFFFF] + [int(k) for k in key])


# ------------------------------------------------------------- noise
def _lattice(rng, X, Y, period):
    gx, gy = X / period, Y / period
    ox, oy = int(np.floor(gx.min())) - 3, int(np.floor(gy.min())) - 3
    nx, ny = int(np.ceil(gx.max())) + 4 - ox, int(np.ceil(gy.max())) + 4 - oy
    grid = rng.uniform(-1, 1, (ny, nx))
    return ndi.map_coordinates(grid, [gy - oy, gx - ox], order=3, mode="nearest")


def fbm(rng, X, Y, scale, octaves=5, lac=2.0, gain=0.5, rotate=True):
    """Smooth fractal noise in about [-1,1]; each octave gets its own rotation to hide lattice axes."""
    tot, amp, norm, f = np.zeros_like(X), 1.0, 0.0, 1.0
    cx, cy = X.mean(), Y.mean()
    for _ in range(octaves):
        if scale / f < MIN_PERIOD[0]:
            break
        a = rng.uniform(0, TAU) if rotate else 0.0
        c, s = math.cos(a), math.sin(a)
        Xr = c * (X - cx) - s * (Y - cy) + rng.uniform(0, 1000)
        Yr = s * (X - cx) + c * (Y - cy) + rng.uniform(0, 1000)
        tot += amp * _lattice(rng, Xr, Yr, scale / f)
        norm += amp
        amp *= gain
        f *= lac
    tot /= norm
    m = np.abs(tot).max()
    return tot / m if m > 0 else tot


def ridged_multifractal(rng, X, Y, scale, octaves=6, lac=2.1, gain=0.5, warp=0.0):
    """Ridged multifractal: crests are sharp, detail concentrates on the crests (weight feedback)."""
    cx, cy = X.mean(), Y.mean()
    tot, amp, norm, f, wgt = np.zeros_like(X), 1.0, 0.0, 1.0, np.ones_like(X)
    for _ in range(octaves):
        if scale / f < MIN_PERIOD[0]:
            break
        a = rng.uniform(0, TAU)
        c, s = math.cos(a), math.sin(a)
        Xr = c * (X - cx) - s * (Y - cy) + rng.uniform(0, 1000)
        Yr = s * (X - cx) + c * (Y - cy) + rng.uniform(0, 1000)
        n = _lattice(rng, Xr, Yr, scale / f)
        sig = (1.0 - np.abs(n)) ** 2
        sig *= wgt
        wgt = np.clip(sig * 1.8, 0.0, 1.0)
        tot += amp * sig
        norm += amp
        amp *= gain
        f *= lac
    tot = tot / norm
    tot -= np.median(tot)
    m = np.abs(tot).max()
    return tot / m if m > 0 else tot


# ------------------------------------------------------------- polylines
def catmull(P, step):
    """Uniform Catmull-Rom through the rows of P (x, y, extras...), resampled about every `step` ft."""
    P = np.asarray(P, float)
    if len(P) < 3:
        n = max(2, int(np.hypot(*(P[-1, :2] - P[0, :2])) / step))
        t = np.linspace(0, 1, n)[:, None]
        return P[0] * (1 - t) + P[-1] * t
    Q = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    for i in range(1, len(Q) - 2):
        p0, p1, p2, p3 = Q[i - 1], Q[i], Q[i + 1], Q[i + 2]
        L = float(np.hypot(*(p2[:2] - p1[:2])))
        n = max(2, int(math.ceil(L / step)))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    R = np.vstack(out + [P[-1:]])
    if P.shape[1] > 2:
        R[:, 2:] = np.clip(R[:, 2:], P[:, 2:].min(0), P[:, 2:].max(0))
    return R


def smooth_noise_1d(s, rng, wavelength, terms=3):
    """Smooth 1D noise in about [-1,1]; the shortest term has wavelength/4.8, so slopes stay gentle."""
    out, amp, tot = np.zeros_like(s), 1.0, 0.0
    for k in range(terms):
        lam = wavelength / (2.2 ** k)
        out += amp * np.sin(TAU * s / lam + rng.uniform(0, TAU))
        tot += amp
        amp *= 0.5
    return out / tot


def arclen(R):
    return np.concatenate([[0], np.cumsum(np.hypot(*np.diff(R[:, :2], axis=0).T))])


def naturalize(P, rng, nat, ncols, default_cols=None, wander=True, vary=True):
    """Smooth a constraint polyline and add low-frequency wander, width and height variation."""
    P = np.asarray(P, float)
    R = catmull(P, nat["smooth_step_ft"])
    s = arclen(R)
    if wander and nat["wander_ft"] > 0:
        d = np.gradient(R[:, :2], axis=0)
        nrm = np.stack([-d[:, 1], d[:, 0]], 1)
        nrm /= np.maximum(np.hypot(nrm[:, 0], nrm[:, 1]), 1e-9)[:, None]
        off = nat["wander_ft"] * smooth_noise_1d(s, rng, nat["wander_wavelength_ft"])
        R[:, :2] += nrm * off[:, None]
    if vary and ncols >= 2:
        R[:, 3] *= 1.0 + nat["width_var"] * smooth_noise_1d(s, rng, nat["wander_wavelength_ft"] * 0.9)
        R[:, 2] *= 1.0 + nat["height_var"] * smooth_noise_1d(s, rng, nat["wander_wavelength_ft"] * 0.7)
    return R


def densify(R, step=6.0):
    """Linear resample to a dense set for nearest-sample distance queries."""
    s = arclen(R)
    n = max(2, int(s[-1] / step))
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, R[:, k]) for k in range(R.shape[1])], 1)


def segment_field(X, Y, R, fn, radius, combine="max", step=14.0, grid=None):
    """Evaluate fn(d, c0, c1) per polyline segment (d = exact distance to the segment, c = linearly interpolated
    columns) and combine over segments with max/min. Each term is continuous, so the result has no seams
    (nearest-sample attribute lookup jumps across medial axes)."""
    D = densify(R, step)
    GX, GY = grid if grid is not None else (X, Y)      # regular grid used for windowing (X, Y may be warped)
    ny, nx = X.shape
    x0, y0 = GX[0, 0], GY[0, 0]
    cx, cy = GX[0, 1] - GX[0, 0], GY[1, 0] - GY[0, 0]
    out = np.full(X.shape, -np.inf if combine == "max" else np.inf)
    for a, b in zip(D[:-1], D[1:]):
        lo = np.minimum(a[:2], b[:2]) - radius
        hi = np.maximum(a[:2], b[:2]) + radius
        j0, j1 = max(0, int((lo[0] - x0) // cx)), min(nx, int((hi[0] - x0) // cx) + 2)
        i0, i1 = max(0, int((lo[1] - y0) // cy)), min(ny, int((hi[1] - y0) // cy) + 2)
        if j0 >= j1 or i0 >= i1:
            continue
        xs, ys = X[i0:i1, j0:j1], Y[i0:i1, j0:j1]
        ab = b[:2] - a[:2]
        L2 = float(ab @ ab) or 1e-9
        t = np.clip(((xs - a[0]) * ab[0] + (ys - a[1]) * ab[1]) / L2, 0, 1)
        d = np.hypot(xs - (a[0] + t * ab[0]), ys - (a[1] + t * ab[1]))
        v = fn(d, a[2] + t * (b[2] - a[2]), a[3] + t * (b[3] - a[3]))
        w = out[i0:i1, j0:j1]
        out[i0:i1, j0:j1] = np.maximum(w, v) if combine == "max" else np.minimum(w, v)
    return out


def ridge_height(d, h, w, k):
    t = np.clip(d / np.maximum(w, 1e-6), 0, 1)
    return h * (1.0 - t * t) ** k


# ------------------------------------------------------------- spurs
def make_spurs(R, cfg, rng, centre, river_pts, avoid, size):
    """Side ridges off the main wall polyline R (columns x,y,h,w)."""
    D = densify(R, 20.0)
    s = arclen(D)
    d = np.gradient(D[:, :2], axis=0)
    tang = d / np.maximum(np.hypot(d[:, 0], d[:, 1]), 1e-9)[:, None]
    W, H = size
    inside = (D[:, 0] > -50) & (D[:, 0] < W + 50) & (D[:, 1] > -50) & (D[:, 1] < H + 50)
    L = float(np.sum(inside)) * 20.0
    n = max(0, int(round(L / 1000.0 * cfg["count_per_1000ft"])))
    idxs = np.where(inside)[0]
    if len(idxs) < 4 or n == 0:
        return []
    # jittered even spacing along the inside part
    pos = (np.arange(n) + rng.uniform(0.15, 0.85, n)) / n
    picks = idxs[(pos * (len(idxs) - 1)).astype(int)]
    rtree = cKDTree(river_pts) if len(river_pts) else None
    out = []
    for i in picks:
        t = tang[i]
        nrm = np.array([-t[1], t[0]])
        to_c = centre - D[i, :2]
        if nrm @ to_c < 0:
            nrm = -nrm
        if rng.uniform() > cfg["inward"]:
            nrm = -nrm
        ang = math.radians(rng.uniform(-38, 38))
        c, sn = math.cos(ang), math.sin(ang)
        dirv = np.array([c * nrm[0] - sn * nrm[1], sn * nrm[0] + c * nrm[1]])
        Ls = rng.uniform(*cfg["length_ft"])
        hf = rng.uniform(*cfg["height_frac"])
        w0 = rng.uniform(*cfg["width_ft"])
        npts = max(4, int(Ls / 55))
        u = np.linspace(0, 1, npts)
        pts = [D[i, :2] + 0.0]
        heading = math.atan2(dirv[1], dirv[0])
        bend = rng.uniform(-0.5, 0.5)
        pos_ = D[i, :2].copy()
        steps = Ls / (npts - 1)
        arr = []
        for k in range(npts):
            arr.append(pos_.copy())
            heading += bend * 0.35 + rng.normal(0, 0.12)
            pos_ = pos_ + steps * np.array([math.cos(heading), math.sin(heading)])
        arr = np.array(arr)
        h0 = D[i, 2] * hf
        hs = h0 * (1 - u) ** 1.5 * (1 + 0.08 * rng.normal(size=npts))
        ws = w0 * (1.0 - 0.45 * u)
        sp = np.c_[arr, hs, ws]
        if rtree is not None and rtree.query(sp[:, :2])[0].min() < cfg["clear_river_ft"]:
            continue
        if any(np.hypot(sp[:, 0] - ax, sp[:, 1] - ay).min() < ar for ax, ay, ar in avoid):
            continue
        out.append(sp)
    return out


# ------------------------------------------------------------- erosion
def _neighbours(ny, nx):
    N = ny * nx
    idx = np.arange(N).reshape(ny, nx)
    dirs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 2 ** 0.5), (-1, 1, 2 ** 0.5), (1, -1, 2 ** 0.5), (1, 1, 2 ** 0.5)]
    nbr = np.full((8, N), -1, dtype=np.int64)
    dist = np.zeros(8)
    for k, (dy, dx, dd) in enumerate(dirs):
        dist[k] = dd
        a = np.full((ny, nx), -1, dtype=np.int64)
        ys = slice(max(0, -dy), ny - max(0, dy))
        xs = slice(max(0, -dx), nx - max(0, dx))
        yd = slice(max(0, dy), ny - max(0, -dy))
        xd = slice(max(0, dx), nx - max(0, -dx))
        a[ys, xs] = idx[yd, xd]
        nbr[k] = a.ravel()
    return nbr, dist


def hydraulic_erosion(h, cell, cfg, protect, keep):
    """Stream-power incision with sediment transport: gullies on flanks, fans where slope breaks."""
    ny, nx = h.shape
    N = ny * nx
    nbr, dist = _neighbours(ny, nx)
    edge = np.zeros((ny, nx), bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    edge = edge.ravel()
    ar = np.arange(N)
    pr = (protect * keep).ravel()
    kp = keep.ravel()
    incised = np.zeros(N)
    h = h.copy()
    K, m, Kc, dep_f = cfg["K"], cfg["m"], cfg["Kc"], cfg["deposit"]
    for _ in range(int(cfg["iterations"])):
        hf = h.ravel()
        S = np.full((8, N), -1e9)
        for k in range(8):
            v = nbr[k] >= 0
            S[k, v] = (hf[v] - hf[nbr[k][v]]) / (dist[k] * cell)
        kb = S.argmax(0)
        Sb = S[kb, ar]
        rec = np.where(Sb > 0, nbr[kb, ar], ar)
        order = np.argsort(-hf, kind="stable")
        A = [1.0] * N
        rl, ol = rec.tolist(), order.tolist()
        for i in ol:
            r = rl[i]
            if r != i:
                A[r] += A[i]
        A = np.array(A)
        Sc = np.maximum(Sb, 0)
        e = K * A ** m * Sc * pr
        e = np.minimum(e, 0.35 * np.maximum(hf - hf[rec], 0))
        e = np.minimum(e, np.maximum(cfg["max_incise_ft"] - incised, 0))
        cap = Kc * K * A ** m * Sc
        e_l, c_l, k_l, ed = e.tolist(), cap.tolist(), kp.tolist(), edge.tolist()
        load = [0.0] * N
        dep = [0.0] * N
        for i in ol:
            l = load[i] + e_l[i]
            r = rl[i]
            if r == i:
                if not ed[i]:
                    dep[i] = l * k_l[i]
                    l -= dep[i]
                else:
                    l = 0.0
            elif l > c_l[i]:
                d = (l - c_l[i]) * dep_f * k_l[i]
                dep[i] = d
                l -= d
            if r != i:
                load[r] += l
        dep = np.array(dep)
        incised += e
        h = (hf - e + dep).reshape(ny, nx)
        if cfg["diffusion"]:
            h = h + cfg["diffusion"] * (ndi.laplace(h, mode="nearest")) * keep * (0.4 + 0.6 * protect)
    return h


def thermal(h, cell, iters, talus, rate=0.5):
    """Thermal erosion with a per-cell angle of repose (talus is rise/run, array or scalar)."""
    h = h.copy()
    offs = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
            (-1, -1, 2 ** 0.5), (-1, 1, 2 ** 0.5), (1, -1, 2 ** 0.5), (1, 1, 2 ** 0.5)]
    ny, nx = h.shape
    c = rate / 8.0
    for _ in range(iters):
        pad = np.pad(h, 1, mode="edge")
        delta = np.zeros_like(pad)
        core = pad[1:-1, 1:-1]
        for dy, dx, dist in offs:
            nb = pad[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
            f = c * np.maximum(core - nb - talus * cell * dist, 0.0)
            delta[1:-1, 1:-1] -= f
            delta[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx] += f
        h += delta[1:-1, 1:-1]
    return h


def slope_of(h, cell, sigma=0.0):
    hh = ndi.gaussian_filter(h, sigma, mode="nearest") if sigma else h
    gy, gx = np.gradient(hh, cell)
    return np.hypot(gx, gy)


def terraces(h, cell, rng, X, Y, cfg, mask_extra):
    per = cfg["period_ft"]
    sl = slope_of(h, cell, 1.0)
    m = sstep((sl - cfg["min_slope"]) / max(cfg["max_slope"] - cfg["min_slope"], 1e-6))
    var = 0.5 + 0.5 * fbm(rng, X, Y, 520, 3, 2.0, 0.5)            # some faces have no benches
    var = sstep((var - 0.25) / 0.5)
    jitter = fbm(rng, X, Y, 160, 3, 2.0, 0.5) * per * 0.7
    sv = (h + jitter) / per
    f = sv - np.floor(sv)
    p = sstep((f - 0.35) / 0.5)
    ht = (np.floor(sv) + p) * per - jitter
    w = cfg["strength"] * m * var * mask_extra
    return h + w * (ht - h)


# ------------------------------------------------------------- main
def _defaults(nz):
    d = dict(smooth_step_ft=8.0, wander_ft=55.0, wander_wavelength_ft=750.0, width_var=0.3, height_var=0.14,
             union_p=4.0, crest_round=1.0,
             spurs=dict(count_per_1000ft=2.4, length_ft=[220, 430], height_frac=[0.35, 0.62], width_ft=[90, 150],
                        inward=0.85, clear_river_ft=160, clear_points=[]),
             rugged=dict(octaves=6, gain=0.5, lacunarity=2.1),
             plateaus=[], terraces=dict(period_ft=26.0, strength=0.4, min_slope=0.28, max_slope=0.7),
             hydraulic=dict(iterations=28, K=0.06, m=0.5, Kc=1.4, deposit=0.55, max_incise_ft=38.0, diffusion=0.08),
             thermal=dict(iterations=140, talus_low=0.68, talus_high=1.15, rate=0.5, jitter=0.22),
             hills_south=dict(y_start=1150.0, amp_ft=26.0, scale_ft=300.0),
             basin=dict(amp_ft=3.2, scale_ft=260.0, mounds=16, mound_ft=[1.5, 5.0], bowl_ft=7.0, fan=None),
             keep_clear=[], river_bed=True, final_smooth_cells=0.8)
    for k, v in nz.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            d[k].update(v)
        else:
            d[k] = v
    return d


def _chaikin(P, n=3):
    P = np.asarray(P, float)
    for _ in range(n):
        a, b = P, np.roll(P, -1, axis=0)
        out = np.empty((2 * len(a), 2))
        out[0::2], out[1::2] = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
        P = out
    return P


def _river_P(v):
    """River route [x, y, rel, side]: the spec points, or the dense meandered route when the valley has a "meander" block
    (river_meander.py, shared with the water generator so the carved valley and the drawn river are the same line)."""
    ds = v.get("side_slope", 0.3)
    if v.get("meander"):
        import river_meander
        return river_meander.river_points(v)
    return np.array([[p[0], p[1], p[2], p[3] if len(p) > 3 else ds] for p in v["points"]], float)


def generate(spec, cell_ft=None, seed=None, verbose=False):
    import time
    t0 = time.time()
    W, H = spec["size_ft"]
    cell = float(cell_ft or spec.get("cell_ft", 10))
    seed = int(spec.get("seed", 1) if seed is None else seed)
    nz = spec.get("noise", {})
    nat = _defaults(spec["natural"])
    MIN_PERIOD[0] = 3.5 * cell
    nx, ny = int(round(W / cell)) + 1, int(round(H / cell)) + 1
    X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
    tx, ty = spec.get("base_tilt", [0, 0])
    base = spec.get("base_elevation_ft", 0.0) + tx * (X - W / 2) + ty * (Y - H / 2)
    centre = np.array([W / 2, H / 2])
    scale = nz.get("scale_ft", 500.0)

    # ---- river polylines (kept exact; the bed is enforced at the end)
    river_polys = []
    for v in spec.get("valleys", []):
        if v.get("river"):
            river_polys.append(naturalize(_river_P(v), sub_rng(seed, 9), nat, 2, wander=False, vary=False)[:, :2])
    river_pts = np.vstack([densify(np.c_[r, np.zeros(len(r))], 25.0)[:, :2] for r in river_polys]) if river_polys else np.zeros((0, 2))
    avoid = [tuple(a) for a in nat["spurs"].get("clear_points", [])]
    avoid += [tuple(a) for a in nat["keep_clear"]]

    # ---- warped frame for features
    fw = nz.get("feature_warp_ft", 0.0)
    rw = sub_rng(seed, 1)
    if fw:
        fs = nz.get("feature_warp_scale_ft", 900.0)
        fw = min(fw, 0.07 * fs)          # warp gradient must stay < ~0.7 or the frame folds into stripes
        FX = X + fw * fbm(rw, X, Y, fs, 2, 2.0, 0.4)
        FY = Y + fw * fbm(rw, X, Y, fs, 2, 2.0, 0.4)
    else:
        FX, FY = X, Y
    WARP_PAD[0] = 2.0 * float(np.abs(FX - X).max() + np.abs(FY - Y).max())

    # ---- ridges, spurs
    crest_k = 1.5 * nat["crest_round"]
    fields = []
    for ri, r in enumerate(spec.get("ridges", [])):
        dw = r.get("width_ft", 350.0)
        P = np.array([[p[0], p[1], p[2], p[3] if len(p) > 3 else dw] for p in r["points"]], float)
        rng = sub_rng(seed, 2, ri)
        R = naturalize(P, rng, nat, 2)
        k = r.get("sharpness", 1.4) * 1.05 * nat["crest_round"]
        fields.append(segment_field(FX, FY, R, lambda d, h_, w_: ridge_height(d, h_, w_, k), R[:, 3].max() + WARP_PAD[0], grid=(X, Y)))
        sp_cfg = r.get("spurs")
        if sp_cfg:
            cfg = dict(nat["spurs"])
            if isinstance(sp_cfg, dict):
                cfg.update(sp_cfg)
            for si, sp in enumerate(make_spurs(R, cfg, sub_rng(seed, 3, ri), centre, river_pts, avoid, (W, H))):
                Rs = catmull(sp, 8.0)
                fields.append(segment_field(FX, FY, Rs, lambda d, h_, w_: ridge_height(d, h_, w_, 1.3), Rs[:, 3].max() + WARP_PAD[0], grid=(X, Y)))
    for pi, pk in enumerate(spec.get("peaks", [])):
        if pk.get("mode", "max") == "max":
            fields.append(T._peak_field(FX, FY, pk))
    if fields:
        p = nat["union_p"]
        st = np.stack(fields)
        F = np.max(st, 0) if p <= 0 else (np.sum(np.maximum(st, 0) ** p, 0)) ** (1.0 / p)
    else:
        F = np.zeros_like(X)
    for pk in spec.get("peaks", []):
        if pk.get("mode") == "add":
            F = F + T._peak_field(FX, FY, pk)
    fmax = max(F.max(), 1e-6)
    mass = np.clip(F / (0.6 * fmax), 0, 1)
    mass = mass ** 1.2

    # keep-clear mask (authority rise): 0 inside, 1 outside
    keep = np.ones_like(X)
    for cx, cy, cr in nat["keep_clear"]:
        keep = np.minimum(keep, sstep((np.hypot(X - cx, Y - cy) - cr * 0.6) / (cr * 0.9)))
    keep_soft = 0.2 + 0.8 * keep

    h = base + F
    if nat.get('debug_stages'):
        STAGES['F'] = h.copy()

    # ---- multi-scale domain-warped ridged multifractal + smooth detail
    rn = sub_rng(seed, 4)
    wf = nz.get("warp_ft", 0.0)
    ws = nz.get("warp_scale_ft", scale * 1.4)
    wf = min(wf, 0.07 * ws)
    Xw = X + wf * fbm(rn, X, Y, ws, 2, 2.0, 0.4)
    Yw = Y + wf * fbm(rn, X, Y, ws, 2, 2.0, 0.4)
    rg = nat["rugged"]
    rid = ridged_multifractal(rn, Xw, Yw, rg.get("scale_ft", scale), rg["octaves"], rg["lacunarity"], rg["gain"])
    smo = fbm(rn, Xw, Yw, scale * 0.7, 5, 2.0, 0.5)
    amp = rg.get("amp_ft", nz.get("ridged_amp_ft", 90.0))
    # mid-height flanks get the strongest rugged detail, summits a little less
    mid = np.clip(4 * mass * (1 - 0.6 * mass), 0, 1)
    h = h + mass * (0.35 + 0.65 * mid) * amp * rid + (nz.get("base_amp_ft", 3.0) + 0.3 * mass * amp) * smo * keep_soft

    if nat.get('debug_stages'):
        STAGES['noise'] = h.copy()
    # ---- plateaus / benches
    for pi, pl in enumerate(nat["plateaus"]):
        rng = sub_rng(seed, 5, pi)
        poly = _chaikin(pl["polygon"], 3)
        from shapely.geometry import Polygon
        import shapely
        PG = Polygon(poly).buffer(0)
        ew = pl.get("edge_wobble_ft", 55.0)                      # ragged, non-polygonal outline
        EX = FX + ew * fbm(rng, X, Y, 260, 3, 2.0, 0.5)
        EY = FY + ew * fbm(rng, X, Y, 260, 3, 2.0, 0.5)
        inside = shapely.contains_xy(PG, EX.ravel(), EY.ravel()).reshape(X.shape).astype(float)
        edge = pl.get("edge_ft", 70.0)
        sd = ndi.distance_transform_edt(inside) - ndi.distance_transform_edt(1 - inside)
        sd = sd * cell + 0.0
        w = sstep(sd / edge + 0.5) * pl.get("strength", 0.95)
        cxp, cyp = PG.centroid.x, PG.centroid.y
        tdx, tdy = pl.get("tilt", [0.0, 0.0])
        if "elev_ft" in pl:
            elev = pl["elev_ft"]
        elif "rel_ft" in pl:
            elev = base + pl["rel_ft"]
        else:                                    # default: bench at the mean height under the polygon (balanced cut and fill)
            elev = float(h[inside > 0.5].mean()) + pl.get("lift_ft", 0.0) if (inside > 0.5).any() else float(h.mean())
        top = elev + tdx * (X - cxp) + tdy * (Y - cyp) \
            + pl.get("noise_ft", 3.0) * (fbm(rng, X, Y, 140, 4, 2.0, 0.55) + 0.5 * fbm(rng, X, Y, 420, 2, 2.0, 0.5))
        h = h + w * (top - h)

    # ---- south: rounded rolling foothills
    hs = nat["hills_south"]
    if hs.get("amp_ft", 0) > 0:
        rs = sub_rng(seed, 6)
        roll = fbm(rs, X, Y, hs["scale_ft"], 4, 2.0, 0.5)
        zone = sstep((Y - hs["y_start"]) / 300.0)
        h = h + zone * hs["amp_ft"] * (0.35 + 0.65 * np.abs(roll)) * np.sign(roll + 0.15) * 0.6 + zone * hs["amp_ft"] * 0.4 * np.abs(roll)

    # ---- valleys & passes (hanging valleys are just valleys with a high floor)
    for vi, v in enumerate(spec.get("valleys", []) + spec.get("passes", [])):
        ds = v.get("side_slope", 0.3)
        is_river = bool(v.get("river"))
        P = _river_P(v) if is_river else np.array([[p[0], p[1], p[2], p[3] if len(p) > 3 else ds] for p in v["points"]], float)
        rng = sub_rng(seed, 7, vi)
        local = dict(nat)
        local["wander_ft"] = 0.0 if is_river else nat["wander_ft"] * 0.5
        R = naturalize(P, rng, local, 2, wander=not is_river, vary=False)
        core = v.get("core_ft", 20.0)
        cw = v.get("carve_width_ft", 420.0 if is_river else 300.0)       # influence fades out: no planar cone cuts
        rr = v.get("round_ft", 18.0)
        kk = v.get("soft_ft", 7.0)

        def vfn(d, rel, sl, core=core, rr=rr, cw=cw):
            dd = np.maximum(d - core, 0.0)
            # shallow-sided stretches only affect a narrow strip; steep gorges reach further (no planar cuts)
            reach = core + 70.0 + (cw - 70.0) * np.clip((sl - 0.2) / 0.3, 0, 1)
            fade = 900.0 * sstep((d - 0.6 * reach) / (0.4 * reach))
            return rel + sl * (np.hypot(dd, rr) - rr) + fade
        rel_t = segment_field(X, Y, R, vfn, cw + core + 60, combine="min")
        d = segment_field(X, Y, R, lambda d, a_, b_: d, cw + core + 60, combine="min")
        d = np.where(np.isfinite(d), d, 1e9)
        target = base + np.where(np.isfinite(rel_t), rel_t, 1e6)
        hmin = -kk * np.log(np.exp(-h / kk) + np.exp(-np.minimum(target, h + 500) / kk))   # smooth minimum
        h = hmin

    if nat.get('debug_stages'):
        STAGES['valleys'] = h.copy()
    # ---- terraces / benches on steep faces (before erosion, so scree softens the risers)
    tz = nat["terraces"]
    if tz["strength"] > 0:
        h = terraces(h, cell, sub_rng(seed, 8), X, Y, tz, np.clip(mass * 3, 0, 1) * keep)

    if nat.get('debug_stages'):
        STAGES['terr'] = h.copy()
    # ---- hydraulic erosion
    hy = nat["hydraulic"]
    protect = sstep(mass * 2.2) * 0.9 + 0.1
    if hy["iterations"]:
        h = hydraulic_erosion(h, cell, hy, protect, keep)

    if nat.get('debug_stages'):
        STAGES['hydro'] = h.copy()
    # ---- thermal erosion with a height dependent angle of repose + noisy talus => scree aprons
    th = nat["thermal"]
    if th["iterations"]:
        rel = (h - base)
        hi = sstep(rel / max(0.55 * fmax, 1.0))
        talus = th["talus_low"] + (th["talus_high"] - th["talus_low"]) * hi
        talus = talus * (1.0 + th["jitter"] * fbm(sub_rng(seed, 10), X, Y, 230, 3, 2.0, 0.5))
        h = thermal(h, cell, int(th["iterations"]), talus, th["rate"])

    if nat.get('debug_stages'):
        STAGES['thermal'] = h.copy()
    # ---- fine rock roughness back onto steep faces
    sl = slope_of(h, cell, 0.8)
    rough = fbm(sub_rng(seed, 11), X, Y, 70, 3, 2.0, 0.55)
    h = h + rough * nat.get('rough_ft', 6.0) * sstep((sl - 0.2) / 0.5) * keep

    # ---- basin micro-relief
    b = nat["basin"]
    basin_w = (1.0 - sstep(mass * 2.5)) * (1.0 - 0.0 * keep)
    rb = sub_rng(seed, 12)
    swale = -(1 - np.abs(fbm(rb, X, Y, b["scale_ft"], 4, 2.0, 0.5))) ** 3
    swale = swale - swale.mean()
    undul = fbm(rb, X, Y, b["scale_ft"] * 2.4, 3, 2.0, 0.5)
    micro = b["amp_ft"] * (1.2 * swale + 0.9 * undul)
    # low mounds
    mr = sub_rng(seed, 13)
    mounds = np.zeros_like(X)
    for _ in range(int(b["mounds"])):
        mx, my = mr.uniform(0.28 * W, 0.78 * W), mr.uniform(0.18 * H, 0.9 * H)
        rad, ht = mr.uniform(45, 120), mr.uniform(*b["mound_ft"]) * mr.choice([1, 1, -0.6])
        mounds += ht * np.exp(-((X - mx) ** 2 + (Y - my) ** 2) / (2 * (rad * 0.5) ** 2))
    micro = (micro + mounds) * basin_w * (0.15 + 0.85 * keep)
    # gentle bowl toward the walls
    micro = micro + b["bowl_ft"] * ((X - W / 2) / (W * 0.4)) ** 2 * basin_w * 0.6
    h = h + micro
    if b.get("fan"):
        fcfg = b["fan"]
        fx, fy = fcfg["x"], fcfg["y"]
        dx, dy = X - fx, Y - fy
        r = np.hypot(dx, dy)
        ang = np.degrees(np.arctan2(dx, dy))                    # 0 = south
        wob = 0.18 * fbm(sub_rng(seed, 14), X, Y, 140, 3, 2.0, 0.5)
        radial = np.clip(1 - r / (fcfg["radius_ft"] * (1 + wob)), 0, 1)
        angular = np.exp(-(ang / fcfg.get("spread_deg", 48)) ** 2)
        h = h + fcfg["height_ft"] * radial ** 1.4 * angular * (0.8 + 0.2 * keep)

    if nat.get('debug_stages'):
        STAGES['micro'] = h.copy()
    # ---- final smoothing then river bed enforcement
    if nat["final_smooth_cells"]:
        h = ndi.gaussian_filter(h, nat["final_smooth_cells"], mode="nearest")
    if nat["river_bed"]:
        for vi, v in enumerate(spec.get("valleys", [])):
            if v.get("river"):
                h = enforce_river(h, X, Y, base, v, sub_rng(seed, 7, vi), nat, cell)

    h = h.astype(np.float32)
    meta = {"size_ft": [W, H], "cell_ft": cell, "nx": nx, "ny": ny, "seed": seed,
            "elev_min": float(h.min()), "elev_max": float(h.max()),
            "relief_ft": float(h.max() - h.min()), "units": "feet", "pipeline": "natural_v2",
            "node_convention": "h[i,j] at x=j*cell_ft, y=i*cell_ft (y down)"}
    if verbose:
        print(f"terrain(natural) {nx}x{ny} cells at {cell:g} ft, seed {seed}, "
              f"{meta['elev_min']:.0f}..{meta['elev_max']:.0f} ft (relief {meta['relief_ft']:.0f}), {time.time() - t0:.1f}s")
    return h, meta


def river_bed_profile(base_fn, v, nat):
    """Dense river centreline (x,y) and a bed elevation that never rises downstream."""
    R = catmull(_river_P(v), 6.0)
    bed = base_fn(R[:, 0], R[:, 1]) + R[:, 2]
    # flow direction = order of points (north to south here); enforce non-climbing
    bed = np.minimum.accumulate(bed)
    return R, bed


def enforce_river(h, X, Y, base, v, rng, nat, cell):
    ny, nx = h.shape
    # base plane is linear: rebuild as a function from the grid via least squares planes
    A = np.c_[X.ravel(), Y.ravel(), np.ones(X.size)]
    co = np.linalg.lstsq(A, base.ravel(), rcond=None)[0]
    base_fn = lambda x, y: co[0] * x + co[1] * y + co[2]
    R, bed_spec = river_bed_profile(base_fn, v, nat)
    # bed follows the actual ground along the river (never a raised channel): local floor minus a depth, then forced
    # to be non-increasing downstream (the river never climbs)
    zc = ndi.map_coordinates(h, [np.clip(R[:, 1] / cell, 0, ny - 1), np.clip(R[:, 0] / cell, 0, nx - 1)], order=1, mode="nearest")
    zf = ndi.uniform_filter1d(zc, 17, mode="nearest")
    bed_s = np.minimum.accumulate(zf - v.get("bed_depth_ft", 5.0))
    tree = cKDTree(R[:, :2])
    P = np.c_[X.ravel(), Y.ravel()]
    _, i = tree.query(P)
    sl = arclen(R)
    best_d = np.full(len(P), np.inf)
    best_s = np.zeros(len(P))
    for da, db in ((-1, 0), (0, 1)):               # exact projection on the two segments around the nearest sample
        ia, ib = np.clip(i + da, 0, len(R) - 1), np.clip(i + db, 0, len(R) - 1)
        ab = R[ib, :2] - R[ia, :2]
        L2 = np.maximum(np.sum(ab * ab, 1), 1e-9)
        t = np.clip(np.sum((P - R[ia, :2]) * ab, 1) / L2, 0, 1)
        dd = np.hypot(*(P - (R[ia, :2] + t[:, None] * ab)).T)
        m = dd < best_d
        best_d = np.where(m, dd, best_d)
        best_s = np.where(m, sl[ia] + t * (sl[ib] - sl[ia]), best_s)
    d = best_d.reshape(X.shape)
    bedg = np.interp(best_s, sl, bed_s).reshape(X.shape)
    side = np.interp(best_s, sl, ndi.uniform_filter1d(R[:, 3], 90, mode="nearest")).reshape(X.shape)           # spec side slope at this reach of the river
    tb = sstep((0.45 - side) / 0.22)                                    # 0 in the gorge .. 1 in the basin (continuous)
    bank = side * (1 - 0.65 * tb)                                       # gentle (<=0.1) banks in the basin, steep in the gorge
    reach = 260.0 * (70.0 / 260.0) ** (1 - tb)                          # the gorge walls themselves come from the valley carve
    outer = 0.35 * (3.0 / 0.35) ** (1 - tb)
    core = v.get("core_ft", 20.0)
    dd = np.maximum(d - 0.5 * core, 0.0)
    tgt = bedg + bank * np.minimum(dd, reach) + np.maximum(bank, outer) * np.maximum(dd - reach, 0.0)   # no cliffs: slope only increases
    k = 3.0
    hn = -k * np.log(np.exp(-h / k) + np.exp(-np.minimum(tgt, h + 200) / k))        # cut only, no levees
    wc = 1.0 - sstep((d - 0.35 * core) / (0.4 * core + 6.0))
    out = hn * (1 - wc) + bedg * wc                                   # exact bed in the channel core
    # relax grid stair-steps around the channel without moving the bed noticeably
    wr = 1.0 - sstep((d - core) / 70.0)
    sm = ndi.gaussian_filter(out, 1.2, mode="nearest")
    return out + 0.7 * wr * (sm - out)
