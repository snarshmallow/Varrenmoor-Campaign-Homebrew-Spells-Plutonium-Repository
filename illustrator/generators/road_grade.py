"""Road grading for the 3D world pack: road surface heights that follow the real terrain mesh, never sit under it, and obey a grade limit.

Pure numpy. Used by worldpack_mesh.build_parts (roads + optional terrain cut/fill) and checked by road_height_audit.py.

Method (all heights feet, pack frame; y down like the heightmap):
 1. Each road (bridge decks excluded; bridge gaps split a road into runs) is resampled every `step_ft` (default = terrain cell), far denser than the
    authored points (about 13 ft), because the terrain mesh has 2.5 ft cells and a ribbon that interpolates between sparse points cuts through it.
 2. Ground under the centreline is read from the actual terrain triangles (mesh_height, same diagonal as build_terrain), not bilinear.
 3. Profile = (1 - smooth) * ground + smooth * moving average of the ground (window `smooth_window_ft`), pinned to bridge-deck ends and to the
    other roads at junctions (cosine blend over `blend_ft`), so a road never steps where it meets a bridge or another road.
 4. Cross slope: the ribbon's left/right edges follow the ground at the edges, tilted at most `cross_deg`.
 5. No burial: the profile is raised until every lateral sample (edges, quarter points, centre) at every station and mid-station is at least `lift` above
    the terrain mesh.  (With cut/fill on, the terrain is changed to fit instead and the cross section is flat.)
 6. Grade: the profile is made Lipschitz with tan(max_grade) by raising only (forward/backward envelope), so the road never goes under ground.
    Warnings: a road floating more than `float_warn_ft` above ground because of the grade limit, a bridge end the road had to rise above,
    and a ground slope steeper than the limit that the road cuts across (reported, the road itself is within the limit).
 7. Optional cut/fill (cutfill_heights): terrain under and beside the road is set to the road bed and blended back to natural ground over
    `cutfill_falloff_ft`, per road run with local windows, so the terrain stays continuous.
"""
import math

import numpy as np

import worldpack as wp

FT_M = wp.FT_M
DEFAULTS = {"enabled": True, "smooth": 0.5, "max_grade_deg": 14.0, "skirt": True, "cutfill": False,
            "cross_deg": 10.0, "smooth_window_ft": 50.0, "cutfill_falloff_ft": 12.0, "blend_ft": 30.0, "float_warn_ft": 3.0,
            "lift_m": 0.25, "step_ft": None}
LATERAL = (-1.0, -0.5, 0.0, 0.5, 1.0)


def params(p=None):
    """Merge user settings (dict, True, False/None -> disabled) over DEFAULTS and clamp."""
    D = dict(DEFAULTS)
    if p is False:
        D["enabled"] = False
        return D
    if isinstance(p, dict):
        D.update({k: v for k, v in p.items() if v is not None})
    D["smooth"] = float(min(1.0, max(0.0, D["smooth"])))
    D["max_grade_deg"] = float(min(60.0, max(1.0, D["max_grade_deg"])))
    D["cross_deg"] = float(min(45.0, max(0.0, D["cross_deg"])))
    return D


ROAD_OVERRIDE_KEYS = ("smooth", "max_grade_deg", "cross_deg", "cutfill")


def road_params(P, r):
    """Effective settings of one road: the global P with the road's optional `grade_override` {smooth, max_grade_deg, cross_deg, cutfill} on top
    (clamped like params()). No override (the default) returns the global values unchanged. P['ignore_road_overrides'] disables the overrides."""
    out = {"smooth": P["smooth"], "max_grade_deg": P["max_grade_deg"], "cross_deg": P["cross_deg"], "cutfill": bool(P["cutfill"])}
    ov = r.get("grade_override") if not P.get("ignore_road_overrides") else None
    if isinstance(ov, dict):
        for k in ROAD_OVERRIDE_KEYS:
            if ov.get(k) is not None:
                out[k] = ov[k]
        out["smooth"] = float(min(1.0, max(0.0, out["smooth"])))
        out["max_grade_deg"] = float(min(60.0, max(1.0, out["max_grade_deg"])))
        out["cross_deg"] = float(min(45.0, max(0.0, out["cross_deg"])))
        out["cutfill"] = bool(out["cutfill"])
    return out


def mesh_height(h, cell, x, y):
    """Height of the exported terrain mesh at (x, y) feet. build_terrain triangulates each cell (a,c,b) and (b,c,d) with a=(i,j), b=(i,j+1), c=(i+1,j),
    d=(i+1,j+1): the diagonal runs b-c. Arrays or scalars, clamped to the grid. This is the surface the player sees, not the bilinear raster."""
    ny, nx = h.shape
    fx = np.clip(np.asarray(x, float) / cell, 0, nx - 1)
    fy = np.clip(np.asarray(y, float) / cell, 0, ny - 1)
    j0, i0 = np.minimum(fx.astype(int), nx - 2), np.minimum(fy.astype(int), ny - 2)
    u, v = fx - j0, fy - i0
    a, b, c, d = h[i0, j0], h[i0, j0 + 1], h[i0 + 1, j0], h[i0 + 1, j0 + 1]
    z = np.where(u + v <= 1.0, a + u * (b - a) + v * (c - a), d + (1 - u) * (c - d) + (1 - v) * (b - d))
    return float(z) if np.ndim(z) == 0 else z


def _arc(P):
    return np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])


def _resample(P, step):
    """Polyline (x, y, z) -> stations every <= step feet, original vertices kept as stations so corners are not cut."""
    s = _arc(P)
    L = float(s[-1])
    n = max(1, int(math.ceil(L / step)))
    ss = np.unique(np.concatenate([np.linspace(0, L, n + 1), s]))
    ss = ss[np.concatenate([[True], np.diff(ss) > 1e-6])]
    return ss, np.interp(ss, s, P[:, 0]), np.interp(ss, s, P[:, 1]), np.interp(ss, s, P[:, 2])


def _normals(x, y):
    """Left-side unit normal in the pack frame (y down), matching worldpack_mesh._ribbon: L = P + n_left * hw in the Blender frame becomes (ty, -tx)."""
    n = len(x)
    t = np.zeros((n, 2))
    dx, dy = np.diff(x), np.diff(y)
    ln = np.maximum(np.hypot(dx, dy), 1e-9)
    seg = np.stack([dx / ln, dy / ln], 1)
    t[0], t[-1] = seg[0], seg[-1]
    for i in range(1, n - 1):
        m = seg[i - 1] + seg[i]
        nm = np.hypot(*m)
        t[i] = m / nm if nm > 1e-9 else seg[i]
    return np.stack([t[:, 1], -t[:, 0]], 1)


def _smooth(g, ds, window_ft):
    if len(g) < 3 or window_ft <= ds:
        return g.copy()
    k = max(1, int(round(window_ft / ds / 2)))
    pad = np.concatenate([np.full(k, g[0]), g, np.full(k, g[-1])])        # edge padding keeps the ends on the ground
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    return np.convolve(pad, ker, mode="valid")


def _lipschitz_up(z, s, g):
    """Raise z so |dz/ds| <= g everywhere (never lowers)."""
    z = z.copy()
    for i in range(1, len(z)):
        z[i] = max(z[i], z[i - 1] - g * (s[i] - s[i - 1]))
    for i in range(len(z) - 2, -1, -1):
        z[i] = max(z[i], z[i + 1] - g * (s[i + 1] - s[i]))
    return z


class Run:
    """One graded piece of a road: dense stations with per-side surface heights (zl, zr; the centre is their mean)."""

    def __init__(self, rid, x, y, z, zl, zr, hw, s, gap_ends):
        self.id, self.x, self.y, self.z, self.zl, self.zr, self.hw, self.s, self.gap_ends = rid, x, y, z, zl, zr, hw, s, gap_ends

    def points(self):
        return np.stack([self.x, self.y, self.z], 1)


def _ground_cross(h, cell, x, y, nrm, hw, ofs):
    """Terrain mesh height at lateral offsets (fractions of the half width, +1 = left edge) for every station -> array [n, len(ofs)]."""
    return np.stack([mesh_height(h, cell, x + nrm[:, 0] * hw * u, y + nrm[:, 1] * hw * u) for u in ofs], 1)


def _require(h, cell, x, y, nrm, hw, delta, lift, lat=LATERAL):
    """Minimum centre height so that the ribbon (z + delta*u across) is >= lift above the terrain at every lateral sample."""
    G = _ground_cross(h, cell, x, y, nrm, hw, lat)
    return np.max(G + lift - delta[:, None] * np.asarray(lat)[None, :], axis=1)


def _fix_mid(h, cell, x, y, nrm, hw, delta, lift, z, iters=4):
    """Stations are checked at their midpoints too: where the linear ribbon between two stations is under the terrain, raise both stations."""
    z = z.copy()
    mx, my = (x[1:] + x[:-1]) / 2, (y[1:] + y[:-1]) / 2
    mn = (nrm[1:] + nrm[:-1])
    ln = np.maximum(np.hypot(mn[:, 0], mn[:, 1]), 1e-9)
    mn = mn / ln[:, None]
    mh = (hw[1:] + hw[:-1]) / 2
    md = (delta[1:] + delta[:-1]) / 2
    req = _require(h, cell, mx, my, mn, mh, md, lift)
    for _ in range(iters):
        d = req - (z[1:] + z[:-1]) / 2
        bad = d > 1e-6
        if not bad.any():
            break
        idx = np.nonzero(bad)[0]
        np.maximum.at(z, idx, z[idx] + d[idx])
        np.maximum.at(z, idx + 1, z[idx + 1] + d[idx])
    return z


def _win(s, s0, blend_ft):
    """Cosine window: 1 at arc length s0, 0 beyond blend_ft."""
    Lb = min(blend_ft, max(s[-1] * 0.9, 1e-6))
    return np.where(np.abs(s - s0) >= Lb, 0.0, 0.5 * (1 + np.cos(np.pi * np.clip(np.abs(s - s0) / Lb, 0, 1))))


PARALLEL_MIN_STATIONS = 4        # a shared stretch of at least ~10 ft (4 stations of 2.5 ft) is "parallel", not a junction


def _blend_stretch(z, s, idx, delta, blend_ft):
    """Add `delta` (one value per station in idx, interpolated between them) along the stretch and fade it to zero over blend_ft beyond both ends (cosine)."""
    idx = np.asarray(idx)
    o = np.argsort(s[idx])
    ss, dd = s[idx][o], np.asarray(delta, float)[o]
    c = np.interp(s, ss, dd)
    lo, hi = ss[0], ss[-1]
    Lb = max(min(blend_ft, s[-1] * 0.9), 1e-6)
    d_out = np.where(s < lo, lo - s, np.where(s > hi, s - hi, 0.0))
    w = np.where(d_out >= Lb, 0.0, 0.5 * (1 + np.cos(np.pi * np.clip(d_out / Lb, 0, 1))))
    return z + c * w


def _blend_at(z, s, s0, target, blend_ft, end=None):
    """Add (target - z at s0) with a cosine falloff of blend_ft either side of arc length s0 (one-sided when s0 is a run end)."""
    return z + (target - float(np.interp(s0, s, z))) * _win(s, s0, blend_ft)




def surface_at(run, x, y):
    """Road surface height at (x, y) from the nearest station of `run` with its cross tilt (same rule as worldpack_mesh.kerb_heights)."""
    X, Y = np.asarray(run.x, float), np.asarray(run.y, float)
    i = int(np.argmin((X - x) ** 2 + (Y - y) ** 2))
    nx, ny = np.gradient(X)[i], np.gradient(Y)[i]
    nl = max(math.hypot(nx, ny), 1e-9)
    lat = (x - X[i]) * (-ny / nl) + (y - Y[i]) * (nx / nl)
    u = float(np.clip(lat / max(float(run.hw[i]), 1e-6), -1.0, 1.0))
    return float(run.z[i] + (run.zr[i] - run.zl[i]) / 2 * u)       # pack frame is y-down: the ribbon's left side (zl) is lat < 0 in this formula


def footprint(run):
    from shapely.geometry import Polygon
    nx, ny = np.gradient(run.x), np.gradient(run.y)
    nl = np.maximum(np.hypot(nx, ny), 1e-9)
    lx, ly = -ny / nl, nx / nl
    L = np.stack([run.x + lx * run.hw, run.y + ly * run.hw], 1)
    R = np.stack([run.x - lx * run.hw, run.y - ly * run.hw], 1)
    return Polygon(np.concatenate([L, R[::-1]])).buffer(0)


def _ground_max(h, cell, x, y, r=2.5):
    """Highest terrain mesh height within r ft of (x, y): the floor under a welded vertex (the mesh audit samples inside the triangles)."""
    a = np.linspace(0, 2 * math.pi, 8, endpoint=False)
    return float(np.max(mesh_height(h, cell, np.concatenate([[x], x + r * np.cos(a)]), np.concatenate([[y], y + r * np.sin(a)]))))


def weld_junctions(pairs, h=None, cell=2.5, lift=0.0):
    """Clean T joins: for every (minor, major) Run pair, every minor surface vertex (centre, left, right edge of each station) inside the major road's
    footprint is set to exactly the major surface height (no step, no gap at the mouth) and the footprint is remembered on the minor Run (`cover`);
    worldpack_mesh.build_road then leaves out every minor deck triangle that lies inside the major road, so nothing overlaps or z-fights there.
    Returns the number of stations changed."""
    from shapely.geometry import Point
    changed = 0
    for A, B in pairs:
        fp = footprint(B)
        A.cover = list(getattr(A, "cover", [])) + [fp]
        nx, ny = np.gradient(A.x), np.gradient(A.y)
        nl = np.maximum(np.hypot(nx, ny), 1e-9)
        lx, ly = -ny / nl, nx / nl
        for i in range(len(A.x)):
            hit = False
            for name, sgn in (("zl", 1.0), ("z", 0.0), ("zr", -1.0)):
                px, py = A.x[i] + sgn * lx[i] * A.hw[i], A.y[i] + sgn * ly[i] * A.hw[i]
                pt = Point(px, py)
                arr = getattr(A, name)
                if fp.contains(pt):
                    zb = surface_at(B, px, py)
                    arr[i] = zb                                                 # exactly the major surface: no step, no gap
                    hit = True
            changed += hit
    return changed


def grade_roads(pack, h, p=None):
    """Grade every non-bridge road of the pack against terrain heights h (the raster the terrain mesh is built from).
    Returns (runs: {road_id: [Run]}, report: {warnings, stats, params}). Settings p: see DEFAULTS."""
    P = params(p)
    cell = pack.cell_ft
    step = float(P["step_ft"] or cell)
    lift = P["lift_m"] / FT_M
    cutfill_ids = set()
    import bridge_maker as bm
    roads = pack.list("roads")
    runs, warns = {}, []
    # ---- pass 1: dense ground, smoothed profile (before pins)
    work = []
    for r in roads:
        if r.get("bridge") or not r.get("points") or len(r["points"]) < 2:
            continue
        pts = np.asarray(r["points"], float)
        pieces = bm.trim_runs(r["points"], r["gaps"]) if r.get("gaps") else [pts.tolist()]
        for k, piece in enumerate(pieces):
            piece = np.asarray(piece, float)
            if len(piece) < 2 or _arc(piece)[-1] < 0.5:
                continue
            s, x, y, z0 = _resample(piece, step)
            nrm = _normals(x, y)
            hw = np.full(len(x), r["width_ft"] / 2.0)
            gc = mesh_height(h, cell, x, y)
            RP = road_params(P, r)
            if RP["cutfill"]:
                cutfill_ids.add(r["id"])
            prof = (1 - RP["smooth"]) * gc + RP["smooth"] * _smooth(gc, step, P["smooth_window_ft"])
            gap_ends = [bool(np.hypot(*(piece[0, :2] - pts[0, :2])) > 0.05), bool(np.hypot(*(piece[-1, :2] - pts[-1, :2])) > 0.05)]
            work.append(dict(id=r["id"], k=k, s=s, x=x, y=y, nrm=nrm, hw=hw, gc=gc, prof=prof + lift, gap_ends=gap_ends, z_auth=(piece[0, 2], piece[-1, 2]), cls=r.get("class"),
                             tang=math.tan(math.radians(RP["max_grade_deg"])), tcross=math.tan(math.radians(RP["cross_deg"])), cutfill=RP["cutfill"], max_grade=RP["max_grade_deg"], cross=RP["cross_deg"]))
    # ---- pins: bridge-deck ends (authored height, fixed), then every junction / crossing with another road (T: the ending road meets the through road;
    # end-to-end and X crossings: both move to the mean), each as a cosine-windowed correction along the road
    bridge_pts = [np.asarray(r["points"], float) for r in roads if r.get("bridge") and r.get("points")]
    tol = 4.0
    jpairs = []
    stats_par = [0]
    joins = []                                                          # (minor work index, major work index): a road ending on the body of another road
    stretches = []                                                      # (road a, stations of a, road b, matching stations of b): parallel runs
    pins = []                                                           # (work index, station index, target z, one-sided end or None)
    for wi, w in enumerate(work):
        for end in (0, 1):
            e = 0 if end == 0 else len(w["x"]) - 1
            ex, ey = w["x"][e], w["y"][e]
            if w["gap_ends"][end]:
                pins.append((wi, e, float(w["z_auth"][end]), end))
                continue
            for B in bridge_pts:                                          # road ends on a bridge-deck road: meet the deck end
                j = int(np.argmin(np.hypot(B[:, 0] - ex, B[:, 1] - ey)))
                if np.hypot(B[j, 0] - ex, B[j, 1] - ey) < max(tol, w["hw"][0]):
                    pins.append((wi, e, float(B[j, 2]), end))
    boxes = [(w["x"].min(), w["x"].max(), w["y"].min(), w["y"].max(), w["hw"][0]) for w in work]
    for ai in range(len(work)):
        for bi in range(ai + 1, len(work)):
            A, Bw = work[ai], work[bi]
            thr = max(tol, A["hw"][0], Bw["hw"][0])
            thr_box = max(thr, A["hw"][0] + Bw["hw"][0] + 2.0)
            a0, a1, a2, a3, _ = boxes[ai]
            b0, b1, b2, b3, _ = boxes[bi]
            if a1 + thr_box < b0 or b1 + thr_box < a0 or a3 + thr_box < b2 or b3 + thr_box < a2:
                continue
            D = np.hypot(A["x"][:, None] - Bw["x"][None, :], A["y"][:, None] - Bw["y"][None, :])
            thr_p = A["hw"][0] + Bw["hw"][0] + 2.0                                  # beds touching or overlapping
            nearp = np.nonzero(D.min(1) < thr_p)[0]
            if len(nearp) >= PARALLEL_MIN_STATIONS:
                for gp_ in np.split(nearp, np.nonzero(np.diff(nearp) > 3)[0] + 1):
                    if len(gp_) < PARALLEL_MIN_STATIONS:
                        continue
                    ibs = np.argmin(D[gp_], axis=1)
                    ta = np.stack([np.gradient(A["x"])[gp_], np.gradient(A["y"])[gp_]], 1)
                    tb = np.stack([np.gradient(Bw["x"])[ibs], np.gradient(Bw["y"])[ibs]], 1)
                    cosang = np.abs((ta * tb).sum(1) / np.maximum(np.hypot(*ta.T) * np.hypot(*tb.T), 1e-9))
                    if cosang.mean() > 0.9 and len(np.unique(ibs)) >= PARALLEL_MIN_STATIONS:     # roughly parallel (within ~25 deg), not a crossing
                        stretches.append((ai, gp_.copy(), bi, ibs.copy()))
                        length = float(A["s"][gp_[-1]] - A["s"][gp_[0]])
                        warns.append(f"{A['id']} and {Bw['id']} run side by side for {length:.0f} ft (beds touch): heights blended along the whole stretch")
            near = np.nonzero(D.min(1) < thr)[0]
            if not len(near):
                continue
            groups = np.split(near, np.nonzero(np.diff(near) > 3)[0] + 1)
            for gi in groups:
                ia = int(gi[np.argmin(D[gi].min(1))])
                ib = int(np.argmin(D[ia]))
                za, zb = A["prof"][ia], Bw["prof"][ib]
                jpairs.append((ai, ia, bi, ib))
                a_end = ia in (0, len(A["x"]) - 1) or gi[0] == 0 or gi[-1] == len(A["x"]) - 1
                b_end = ib in (0, len(Bw["x"]) - 1)
                if a_end and not b_end:
                    pins.append((ai, ia, float(zb), None))
                    joins.append((ai, bi))
                elif b_end and not a_end:
                    pins.append((bi, ib, float(za), None))
                    joins.append((bi, ai))
                else:
                    m = 0.5 * (za + zb)
                    pins.append((ai, ia, float(m), None))
                    pins.append((bi, ib, float(m), None))
    for wi, e, tgt, end in pins:
        w = work[wi]
        w["prof"] = _blend_at(w["prof"], w["s"], w["s"][e], tgt, P["blend_ft"], end)
    for ai, ga, bi, ibs in stretches:
        A, Bw = work[ai], work[bi]
        m = 0.5 * (A["prof"][ga] + Bw["prof"][ibs])
        A["prof"] = _blend_stretch(A["prof"], A["s"], ga, m - A["prof"][ga], P["blend_ft"])
        ub = np.unique(ibs)
        mb = np.array([m[ibs == u].mean() for u in ub])
        Bw["prof"] = _blend_stretch(Bw["prof"], Bw["s"], ub, mb - Bw["prof"][ub], P["blend_ft"])
        for k in range(0, len(ga), 4):                                  # the later "both rise to the higher" pass checks the stretch every ~10 ft
            jpairs.append((ai, int(ga[k]), bi, int(ibs[k])))
        stats_par[0] += 1
    # ---- pass 2: cross slope, no-burial, grade
    stats = {"roads": 0, "stations": 0, "max_raise_ft": 0.0, "max_float_ft": 0.0, "grade_limited_ft": 0.0, "parallel_stretches": 0}

    def finish(w):
        s, x, y, nrm, hw = w["s"], w["x"], w["y"], w["nrm"], w["hw"]
        cutfill, tang, tcross = w["cutfill"], w["tang"], w["tcross"]
        if "delta" not in w:
            if cutfill:
                w["delta"] = np.zeros(len(x))
            else:
                gl = mesh_height(h, cell, x + nrm[:, 0] * hw, y + nrm[:, 1] * hw)
                gr = mesh_height(h, cell, x - nrm[:, 0] * hw, y - nrm[:, 1] * hw)
                w["delta"] = _smooth(np.clip((gl - gr) / 2.0, -hw * tcross, hw * tcross), step, 20.0)
        delta = w["delta"]
        z = w["prof"].copy()
        if not cutfill:
            z = np.maximum(z, _require(h, cell, x, y, nrm, hw, delta, lift))
            z = _fix_mid(h, cell, x, y, nrm, hw, delta, lift, z)
        w["zpre"] = z.copy()
        z = _lipschitz_up(z, s, tang)
        if not cutfill:                                                    # the envelope only raises, but re-check the mid points against the raised profile
            z = _fix_mid(h, cell, x, y, nrm, hw, delta, lift, z)
            z = _lipschitz_up(z, s, tang)
        w["z"] = z

    for w in work:
        finish(w)
    for _ in range(3):                                                     # junctions / crossings: both roads rise to the higher of the two (raising never buries)
        moved = False
        for ai, ia, bi, ib in jpairs:
            A, Bw = work[ai], work[bi]
            za, zb = A["z"][ia], Bw["z"][ib]
            if abs(za - zb) < 0.05:
                continue
            t = max(za, zb)
            for w, i, zz in ((A, ia, za), (Bw, ib, zb)):
                if t - zz > 0.05:
                    w["prof"] = w["z"] + (t - zz) * _win(w["s"], w["s"][i], P["blend_ft"])
                    moved = True
        if not moved:
            break
        for w in work:
            finish(w)
    stats["parallel_stretches"] = stats_par[0]
    for w in work:
        s, x, y, hw, delta, z, zpre = w["s"], w["x"], w["y"], w["hw"], w["delta"], w["z"], w["zpre"]
        gc = w["gc"]
        # warnings
        fl = z - gc - lift
        w["max_float"] = float(fl.max())
        stats["roads"] += 1
        stats["stations"] += len(z)
        stats["max_raise_ft"] = max(stats["max_raise_ft"], float((z - w["prof"]).max()))
        stats["max_float_ft"] = max(stats["max_float_ft"], float(fl.max()))
        stats["grade_limited_ft"] = max(stats["grade_limited_ft"], float((z - zpre).max()))
        rid = f"{w['id']}" + (f"#{w['k']}" if w["k"] else "")
        ground_grade = np.abs(np.diff(gc)) / np.maximum(np.diff(s), 1e-6)
        if (z - zpre).max() > P["float_warn_ft"]:
            warns.append(f"{rid}: ground is steeper than the {w['max_grade']:.0f} deg grade limit; the road was raised up to {float((z - zpre).max()):.1f} ft clear of it (skirt closes the gap)")
        elif fl.max() > P["float_warn_ft"] * 1.6 and not w["cutfill"]:
            warns.append(f"{rid}: road stands up to {float(fl.max()):.1f} ft above the ground (cross-slope limit {w['cross']:.0f} deg / grade limit); skirt closes the gap")
        if ground_grade.size and np.degrees(np.arctan(np.percentile(ground_grade, 95))) > w["max_grade"] * 1.5:
            warns.append(f"{rid}: natural ground along the road is steeper than {w['max_grade'] * 1.5:.0f} deg over 5%+ of its length; consider switchbacks or cut/fill")
        for end in (0, 1):
            if w["gap_ends"][end]:
                zz = z[0] if end == 0 else z[-1]
                if zz - w["z_auth"][end] > 0.25:
                    warns.append(f"{rid}: road end at a bridge was raised {zz - w['z_auth'][end]:.1f} ft above the bridge deck end (terrain/grade limit); check the approach")
        gx = np.degrees(np.arctan(np.abs(np.diff(z)) / np.maximum(np.diff(s), 1e-6)))
        if gx.size and gx.max() > w["max_grade"] + 0.05:
            warns.append(f"{rid}: grade limit could not be met, max {gx.max():.1f} deg")
        zl, zr = z + delta, z - delta
        run_ = Run(w["id"], x, y, z, zl, zr, hw, s, w["gap_ends"])
        w["run"] = run_
        runs.setdefault(w["id"], []).append(run_)
    n_weld = weld_junctions([(work[a]["run"], work[b]["run"]) for a, b in joins if "run" in work[a] and "run" in work[b]], h, cell, lift)
    stats["junction_welds"] = n_weld
    overridden = sorted({r["id"] for r in roads if isinstance(r.get("grade_override"), dict) and not P.get("ignore_road_overrides")})
    return runs, {"cutfill_ids": sorted(cutfill_ids), "overridden": overridden, "warnings": warns, "stats": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in stats.items()}, "params": {k: P[k] for k in ("smooth", "max_grade_deg", "skirt", "cutfill", "cross_deg", "smooth_window_ft", "cutfill_falloff_ft")}}


def cutfill_heights(h, cell, runs, falloff_ft=12.0, lift_ft=0.82, shoulder_ft=0.5):
    """Terrain h with the road beds cut/filled in: under each run (road half width + shoulder) the terrain is set to the road surface minus the lift,
    and blended back to natural ground with a smoothstep over falloff_ft, so the heightfield stays continuous. Local windows: cost ~ road area.
    Returns (new heights, {max_cut_ft, max_fill_ft})."""
    h0 = h.astype(np.float64)
    out = h0.copy()
    ny, nx = h.shape
    cut = fill = 0.0
    for rid in sorted(runs):
        for run in runs[rid]:
            if len(run.x) < 2:
                continue
            hw = float(run.hw[0]) + shoulder_ft
            R = hw + falloff_ft
            x0, x1 = run.x.min() - R, run.x.max() + R
            y0, y1 = run.y.min() - R, run.y.max() + R
            j0, j1 = max(0, int(x0 // cell)), min(nx - 1, int(x1 // cell) + 1)
            i0, i1 = max(0, int(y0 // cell)), min(ny - 1, int(y1 // cell) + 1)
            X, Y = np.meshgrid(np.arange(j0, j1 + 1) * cell, np.arange(i0, i1 + 1) * cell)
            best = np.full(X.shape, np.inf)
            zt = np.zeros(X.shape)
            for a in range(len(run.x) - 1):
                px, py, qx, qy = run.x[a], run.y[a], run.x[a + 1], run.y[a + 1]
                dx, dy = qx - px, qy - py
                dd = dx * dx + dy * dy or 1e-9
                t = np.clip(((X - px) * dx + (Y - py) * dy) / dd, 0, 1)
                dist = np.hypot(X - (px + t * dx), Y - (py + t * dy))
                upd = dist < best
                best = np.where(upd, dist, best)
                zt = np.where(upd, run.z[a] * (1 - t) + run.z[a + 1] * t, zt)
            k = np.clip((hw + falloff_ft - best) / falloff_ft, 0, 1)
            k = k * k * (3 - 2 * k)
            win = out[i0:i1 + 1, j0:j1 + 1]
            new = np.where(k > 0, win * (1 - k) + (zt - lift_ft) * k, win)
            d = new - h0[i0:i1 + 1, j0:j1 + 1]
            fill, cut = max(fill, float(d.max())), max(cut, float(-d.min()))
            out[i0:i1 + 1, j0:j1 + 1] = new
    return out.astype(np.float32), {"max_cut_ft": round(cut, 2), "max_fill_ft": round(fill, 2)}


def verify(h, cell, runs, lift_ft=0.82, lat=LATERAL):
    """Depth of every run's ribbon above the terrain mesh at stations, mid-stations and lateral samples: (min, max, buried_count, n)."""
    mn, mx, bad, n = 1e9, -1e9, 0, 0
    for rid, rs in runs.items():
        for r in rs:
            nrm = _normals(r.x, r.y)
            delta = (r.zl - r.zr) / 2
            for xs, ys, zs, ns, hws, ds in ((r.x, r.y, r.z, nrm, r.hw, delta),):
                G = _ground_cross(h, cell, xs, ys, ns, hws, lat)
                D = zs[:, None] + ds[:, None] * np.asarray(lat)[None, :] - G
                mn, mx, bad, n = min(mn, D.min()), max(mx, D.max()), bad + int((D < 0).sum()), n + D.size
    return mn, mx, bad, n


def grade_and_cutfill(pack, h, p=None):
    """Grade the roads and, when p['cutfill'], cut/fill the terrain to them. Returns (heights, runs, report). If cut/fill left a road under the changed
    ground (beds of different roads overlapping), the roads are re-draped onto the modified terrain (raise only) and the report says so."""
    P = params(p)
    runs, rep = grade_roads(pack, h, P)
    if not rep.get("cutfill_ids"):
        return h, runs, rep
    cf_ids = set(rep["cutfill_ids"])                                    # all roads with the global switch, else only the roads that ask for it
    h2, cf = cutfill_heights(h, pack.cell_ft, {k: v for k, v in runs.items() if k in cf_ids}, P["cutfill_falloff_ft"], P["lift_m"] / FT_M)
    rep["cutfill"] = cf
    mn, mx, bad, n = verify(h2, pack.cell_ft, runs, 0.0)
    if bad:
        runs, rep2 = grade_roads(pack, h2, dict(P, cutfill=False, smooth=0.0, ignore_road_overrides=True))
        rep["warnings"] += ["cut/fill: roads were re-draped onto the modified terrain where road beds overlap"] + rep2["warnings"]
    return h2, runs, rep


# ------------------------------------------------------------------ coarse terrain LODs vs roads
def lod_pokes(h, cell, runs, step, tol_ft=0.05, lat=LATERAL):
    """How far the coarse terrain mesh (every `step`-th heightmap vertex, the LOD terrain tile) stands ABOVE each road ribbon: per road
    {stations, poking, max_poke_ft}. The full-resolution mesh is fine by construction (grading); a coarse mesh interpolates over the cut/valley the road sits in."""
    hl = np.ascontiguousarray(h[::step, ::step])
    # keep the last row / column like build_terrain (it appends them); only matters at the map edge, ignore: mesh_height clamps to the grid
    out = {}
    for rid, rs in runs.items():
        st = pk = 0
        mxp = 0.0
        for r in rs:
            nrm = _normals(r.x, r.y)
            delta = (r.zl - r.zr) / 2
            G = _ground_cross(hl, cell * step, r.x, r.y, nrm, r.hw, lat)
            D = G - (r.z[:, None] + delta[:, None] * np.asarray(lat)[None, :])
            st += D.size
            pk += int((D > tol_ft).sum())
            mxp = max(mxp, float(D.max()))
        out[rid] = {"stations": st, "poking": pk, "max_poke_ft": round(max(mxp, 0.0), 2)}
    return out


def lod_safe_heights(h, cell, runs, step, clearance_ft=0.3, iters=8, lat=LATERAL):
    """Heights h with the vertices of the `step` terrain LOD lowered where its triangles would cut through a road ribbon (only those vertices; at most
    `iters` passes). The full-resolution vertices that are not LOD vertices keep their values, so build the LOD tile from this array with step `step`.
    Returns (h2, report {lowered_vertices, max_lowered_ft, remaining_pokes})."""
    h2 = h.astype(np.float64).copy()
    ny, nx = h2.shape
    lowered = np.zeros(h2.shape, bool)
    maxl = 0.0
    for _ in range(iters):
        hl = np.ascontiguousarray(h2[::step, ::step])
        cl = cell * step
        any_bad = False
        for rid, rs in runs.items():
            for r in rs:
                nrm = _normals(r.x, r.y)
                delta = (r.zl - r.zr) / 2
                for u in lat:
                    x = r.x + nrm[:, 0] * r.hw * u
                    y = r.y + nrm[:, 1] * r.hw * u
                    g = mesh_height(hl, cl, x, y)
                    need = g - (r.z + delta * u - clearance_ft)
                    bad = np.nonzero(need > 0)[0]
                    if not len(bad):
                        continue
                    any_bad = True
                    for i in bad:
                        fx, fy = min(max(x[i] / cl, 0), hl.shape[1] - 1), min(max(y[i] / cl, 0), hl.shape[0] - 1)
                        j0, i0 = min(int(fx), hl.shape[1] - 2), min(int(fy), hl.shape[0] - 2)
                        for di in (0, 1):
                            for dj in (0, 1):
                                a, b = (i0 + di) * step, (j0 + dj) * step
                                if a < ny and b < nx:
                                    new = h2[a, b] - need[i]
                                    maxl = max(maxl, h2[a, b] - new)
                                    h2[a, b] = new
                                    lowered[a, b] = True
        if not any_bad:
            break
    rem = sum(v["poking"] for v in lod_pokes(h2, cell, runs, step, tol_ft=0.0).values())
    return h2.astype(h.dtype), {"lowered_vertices": int(lowered.sum()), "max_lowered_ft": round(float(maxl), 2), "remaining_pokes": int(rem)}
