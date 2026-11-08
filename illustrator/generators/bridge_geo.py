"""Bridge meshes (pure numpy, no bpy): stone/brick arch, flat cut stone, rough-hewn log truss and plank footbridge.

Local frame (metres): u along the span (0..L, travel direction), v across (+ = left of travel), z absolute (feet-derived, no origin removed).
`build(plan)` returns (Mesh, info). `plan` comes from bridge_maker.make_plan (resolved preset + crossing context). Rules kept everywhere:
* every face is emitted once; hidden contact faces are omitted (a slab sits on a pier whose top face is not generated), so nothing is coplanar-overlapping;
* only a handful of materials, so a bridge merges into one node;
* nothing but abutments/piers/foundations may stand inside the clearance envelopes (checked by bridge_maker.check_clearance).
"""
import math

import numpy as np

import worldpack_mesh as wm

FT = 0.3048


# ------------------------------------------------------------------ small helpers
class Prof:
    """Piecewise-linear function of u from [(u, value)] (clamped at the ends)."""

    def __init__(self, pts):
        a = np.asarray(sorted(pts), float)
        self.u, self.v = a[:, 0], a[:, 1]

    def __call__(self, u):
        return np.interp(u, self.u, self.v)


def _tile_ft(mid):
    import worldpack_pbr as pbr
    return pbr.tile_ft(mid, 6.0)


class G:
    """Geometry accumulator with outward-oriented faces and plane-projected UVs (one texture repeat = tile_ft feet)."""

    def __init__(self):
        self.b = wm.Builder()
        self.tiles = {}

    def tile(self, mid):
        if mid not in self.tiles:
            self.tiles[mid] = _tile_ft(mid) * FT if not mid.startswith("road:") else 8.0 * FT
        return self.tiles[mid]

    def poly(self, mid, pts, out, uvmode=None, tile=None):
        """Convex polygon (fan). `out` = a vector the face normal must point towards; the winding is flipped if needed."""
        P = [np.asarray(p, float) for p in pts]
        n = np.zeros(3)
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
        if np.linalg.norm(n) < 1e-12:
            return
        if np.dot(n, out) < 0:
            P = P[::-1]
            n = -n
        t = tile if tile else self.tile(mid)
        nn = n / np.linalg.norm(n)
        mode = uvmode or ("z" if abs(nn[2]) > 0.7 else ("u" if abs(nn[0]) > abs(nn[1]) else "v"))
        ids = []
        for p in P:
            if mode == "z":
                uv = (p[0] / t, -p[1] / t)
            elif mode == "u":
                uv = (p[1] / t, -p[2] / t)
            elif mode == "road":
                uv = (p[1] / t, p[0] / t)
            else:
                uv = (p[0] / t, -p[2] / t)
            ids.append(self.b.vert(tuple(p), uv))
        for i in range(1, len(ids) - 1):
            self.b.tri(mid, ids[0], ids[i], ids[i + 1])

    def box(self, mid, lo, hi, skip=(), tile=None):
        x0, y0, z0 = lo
        x1, y1, z1 = hi
        F = {"-u": ([(x0, y0, z0), (x0, y1, z0), (x0, y1, z1), (x0, y0, z1)], (-1, 0, 0)),
             "+u": ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], (1, 0, 0)),
             "-v": ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], (0, -1, 0)),
             "+v": ([(x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)], (0, 1, 0)),
             "-z": ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1)),
             "+z": ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], (0, 0, 1))}
        for k, (pts, nrm) in F.items():
            if k not in skip:
                self.poly(mid, pts, nrm, tile=tile)

    def log(self, mid, a, b, r0, r1=None, n=6, rng=None, jit=0.08, caps=True, phase=None, square=False):
        """A prism from a to b (rough-hewn log: n sides, radius jitter per vertex ring)."""
        a, b = np.asarray(a, float), np.asarray(b, float)
        ax = b - a
        ln = float(np.linalg.norm(ax))
        if ln < 1e-6:
            return
        t = ax / ln
        up = np.array([0, 0, 1.0]) if abs(t[2]) < 0.95 else np.array([1.0, 0, 0])
        e1 = np.cross(up, t)
        e1 /= np.linalg.norm(e1)
        e2 = np.cross(t, e1)
        r1 = r0 if r1 is None else r1
        rng = rng or np.random.RandomState(1)
        ph = (math.pi / n if square else 0.0) if phase is None else phase
        ang = [ph + 2 * math.pi * k / n for k in range(n)]
        rings = []
        for end, r in ((a, r0), (b, r1)):
            ring = []
            for k in range(n):
                rr = r * (1.0 + (0 if square else rng.uniform(-jit, jit))) * (math.sqrt(2) if square else 1.0)
                ring.append(end + rr * (math.cos(ang[k]) * e1 + math.sin(ang[k]) * e2))
            rings.append(ring)
        t_len = self.tile(mid)
        circ = 2 * math.pi * max(r0, r1)
        for k in range(n):
            k2 = (k + 1) % n
            mid_dir = (rings[0][k] + rings[0][k2] + rings[1][k] + rings[1][k2]) / 4 - (a + b) / 2
            quad = [rings[0][k], rings[1][k], rings[1][k2], rings[0][k2]]
            nrm = np.cross(quad[1] - quad[0], quad[3] - quad[0])
            if np.dot(nrm, mid_dir) < 0:
                quad = quad[::-1]
            u0, u1 = 0.0, ln / t_len
            v0, v1 = k / n * circ / t_len, (k + 1) / n * circ / t_len
            # quad order after orientation may be reversed; assign uv by which ring each vertex belongs to
            ids = []
            for p in quad:
                on_b = np.dot(p - a, t) > ln * 0.5
                ids.append(self.b.vert(tuple(p), (u1 if on_b else u0, 0.0)))
            # v coordinate by position around the ring
            for i, p in enumerate(quad):
                kk = None
                for ring in rings:
                    for j, q in enumerate(ring):
                        if q is p:
                            kk = j
                vv = v0 if kk == k else v1
                self.b.UV[ids[i]] = (self.b.UV[ids[i]][0], vv)
            self.b.tri(mid, ids[0], ids[1], ids[2])
            self.b.tri(mid, ids[0], ids[2], ids[3])
        if caps:
            for ring, d in ((rings[0], -t), (rings[1], t)):
                self._cap(mid, ring, d, t_len)

    def _cap(self, mid, ring, d, t_len):
        c = sum(ring) / len(ring)
        ids = [self.b.vert(tuple(p), (p[0] / t_len, p[1] / t_len)) for p in ring]
        ic = self.b.vert(tuple(c), (c[0] / t_len, c[1] / t_len))
        for i in range(len(ring)):
            tri = [ic, ids[i], ids[(i + 1) % len(ring)]]
            n = np.cross(ring[i] - c, ring[(i + 1) % len(ring)] - c)
            if np.dot(n, d) < 0:
                tri = [ic, tri[2], tri[1]]
            self.b.tri(mid, *tri)

    def mesh(self):
        return self.b.build()


def _strip_quads(g, mid, lows, highs, out, flip_hint=None):
    """Quads between two polylines of 3D points (same count): a vertical face strip."""
    for i in range(len(lows) - 1):
        a, b, c, d = lows[i], lows[i + 1], highs[i + 1], highs[i]
        if np.linalg.norm(np.asarray(a) - np.asarray(b)) < 1e-7 and np.linalg.norm(np.asarray(c) - np.asarray(d)) < 1e-7:
            continue
        g.poly(mid, [a, b, c, d] if np.linalg.norm(np.asarray(a) - np.asarray(b)) > 1e-7 else [a, c, d], out)


# ------------------------------------------------------------------ arch bridges
def _base(sd, u):
    """Foundation level of a solid (pier/abutment) at u: constant, or following the ground ('bprof') for the end blocks."""
    if "bprof" in sd:
        b = np.asarray(sd["bprof"], float)
        return float(np.interp(u, b[:, 0], b[:, 1]))
    return sd["base"]


def arch_geometry(ua, ub, zs, rise):
    """Circle through the springing points (ua, zs), (ub, zs) with the given rise. Returns (uc, zc, R)."""
    s = ub - ua
    rise = min(rise, s / 2)
    R = (s * s / 4 + rise * rise) / (2 * rise)
    return 0.5 * (ua + ub), zs + rise - R, R


def build_arch(plan):
    g = G()
    P = plan["p"]
    rng = np.random.RandomState(plan["seed"])
    L, W = plan["L"], plan["W"]
    d = Prof(plan["deck"])
    M = plan["mats"]
    hw = W / 2
    pt, ph, ct, co = P["parapet_t"], P["parapet_h"], P["coping_t"], P["coping_over"]
    solids, arches = plan["solids"], plan["arches"]          # solids: [{u0,u1,base}]; arches: [{ua,ub,zs,rise}]
    deck_mat = M["deck"]
    # ---- stations along u (shared by the wall faces, parapet, coping and the deck top)
    st = []                                                  # (u, B) lower boundary of the side wall; B None = same as previous (station only)
    items = sorted([("s", s["u0"], s) for s in solids] + [("a", a["ua"], a) for a in arches], key=lambda t: t[1])
    step = P.get("station_m", 1.2)
    ring_pts = {}
    for kind, _, it in items:
        if kind == "s":
            n = max(1, int(math.ceil((it["u1"] - it["u0"]) / step)))
            for k in range(n + 1):
                uk = it["u0"] + (it["u1"] - it["u0"]) * k / n
                st.append((uk, _base(it, uk)))
        else:
            uc, zc, R = arch_geometry(it["ua"], it["ub"], it["zs"], it["rise"])
            t = P["ring_t"]
            phi = math.asin(min(1.0, (it["ub"] - it["ua"]) / 2 / R))
            K = max(7, int(2 * phi * R / P["voussoir_m"]) | 1)
            th = np.linspace(-phi, phi, K + 1)
            It = np.stack([uc + R * np.sin(th), zc + R * np.cos(th)], 1)
            Et = np.stack([uc + (R + t) * np.sin(th), zc + (R + t) * np.cos(th)], 1)
            ring_pts[id(it)] = (th, It, Et, uc, zc, R, K)
            st.append((it["ua"], zc + math.sqrt(max((R + t) ** 2 - (it["ua"] - uc) ** 2, 0.0))))
            for k in range(1, K):
                if it["ua"] + 1e-6 < Et[k, 0] < it["ub"] - 1e-6:
                    st.append((Et[k, 0], Et[k, 1]))
            st.append((it["ub"], zc + math.sqrt(max((R + t) ** 2 - (it["ub"] - uc) ** 2, 0.0))))
    # remove duplicated (u, B) neighbours
    S = [st[0]]
    for s_ in st[1:]:
        if abs(s_[0] - S[-1][0]) < 1e-9 and abs(s_[1] - S[-1][1]) < 1e-9:
            continue
        S.append(s_)
    U = np.array([s_[0] for s_ in S])
    Bz = np.array([s_[1] for s_ in S])
    D = d(U)
    wall = M["wall"]
    for side in (1, -1):
        low = [(U[i], side * hw, Bz[i]) for i in range(len(S))]
        top = [(U[i], side * hw, D[i] + ph - ct) for i in range(len(S))]
        _strip_quads(g, wall, low, top, (0, side, 0))
        # parapet inner face
        lo_i = [(U[i], side * (hw - pt), D[i]) for i in range(len(S))]
        hi_i = [(U[i], side * (hw - pt), D[i] + ph - ct) for i in range(len(S))]
        _strip_quads(g, wall, lo_i, hi_i, (0, -side, 0))
        # coping: top, outer, inner faces + two overhang undersides
        yo, yi = side * (hw + co), side * (hw - pt - co)
        for i in range(len(S) - 1):
            if U[i + 1] - U[i] < 1e-7:
                continue
            za, zb = D[i] + ph, D[i + 1] + ph
            g.poly(M["coping"], [(U[i], yi, za), (U[i + 1], yi, zb), (U[i + 1], yo, zb), (U[i], yo, za)], (0, 0, 1))
            g.poly(M["coping"], [(U[i], yo, za - ct), (U[i + 1], yo, zb - ct), (U[i + 1], yo, zb), (U[i], yo, za)], (0, side, 0))
            g.poly(M["coping"], [(U[i], yi, za - ct), (U[i + 1], yi, zb - ct), (U[i + 1], yi, zb), (U[i], yi, za)], (0, -side, 0))
            g.poly(M["coping"], [(U[i], side * hw, za - ct), (U[i + 1], side * hw, zb - ct), (U[i + 1], yo, zb - ct), (U[i], yo, za - ct)], (0, 0, -1))
            g.poly(M["coping"], [(U[i], side * (hw - pt), za - ct), (U[i + 1], side * (hw - pt), zb - ct), (U[i + 1], yi, zb - ct), (U[i], yi, za - ct)], (0, 0, -1))
        for u_, sgn in ((U[0], -1), (U[-1], 1)):             # end faces of parapet + coping
            z_d, z_t = float(d(u_)), float(d(u_)) + ph
            g.poly(wall, [(u_, side * (hw - pt), z_d), (u_, side * hw, z_d), (u_, side * hw, z_t - ct), (u_, side * (hw - pt), z_t - ct)], (sgn, 0, 0))
            g.poly(M["coping"], [(u_, yi, z_t - ct), (u_, yo, z_t - ct), (u_, yo, z_t), (u_, yi, z_t)], (sgn, 0, 0))
    # deck top (road surface): between the inner parapet faces
    for i in range(len(S) - 1):
        if U[i + 1] - U[i] < 1e-7:
            continue
        g.poly(deck_mat, [(U[i], -(hw - pt), D[i]), (U[i + 1], -(hw - pt), D[i + 1]), (U[i + 1], hw - pt, D[i + 1]), (U[i], hw - pt, D[i])], (0, 0, 1), uvmode="road")
    # end walls (abutment faces) from base to deck
    for u_, sgn, s_ in ((0.0, -1, solids[0]), (L, 1, solids[-1])):
        b_ = _base(s_, u_)
        g.poly(wall, [(u_, -hw, b_), (u_, hw, b_), (u_, hw, float(d(u_))), (u_, -hw, float(d(u_)))], (sgn, 0, 0))
    # ---- piers/abutment flanks facing the openings, soffits, rings, cutwaters
    for a in arches:
        uc, zc, R = arch_geometry(a["ua"], a["ub"], a["zs"], a["rise"])
        th, It, Et, uc, zc, R, K = ring_pts[id(a)]
        t = P["ring_t"]
        for u_, sgn in ((a["ua"], 1), (a["ub"], -1)):
            for s_ in solids:
                if abs(s_["u1"] - u_) < 1e-6 or abs(s_["u0"] - u_) < 1e-6:
                    b_ = _base(s_, u_)
                    g.poly(wall, [(u_, -hw, b_), (u_, hw, b_), (u_, hw, a["zs"]), (u_, -hw, a["zs"])], (sgn, 0, 0))
        dep = {sd: rng.uniform(P["ring_proud"] * 0.45, P["ring_proud"], K) for sd in (1, -1)}
        for k in range(K):
            mat_r = M["ring"]
            if P.get("springers") and (k < 2 or k >= K - 2 or k == K // 2):
                mat_r = M["springer"]
            elif P.get("ring_alt") and k % 2:
                mat_r = M["ring2"]
            i0, i1, e0, e1 = It[k], It[k + 1], Et[k], Et[k + 1]
            wsd = max(abs(i0[0] - uc), abs(i1[0] - uc))
            for side in (1, -1):
                y = side * (hw + dep[side][k])
                g.poly(mat_r, [(i0[0], y, i0[1]), (i1[0], y, i1[1]), (e1[0], y, e1[1]), (e0[0], y, e0[1])], (0, side, 0))
                g.poly(M["soffit"], [(i0[0], side * hw, i0[1]), (i1[0], side * hw, i1[1]), (i1[0], y, i1[1]), (i0[0], y, i0[1])], (0, 0, -1)) if dep[side][k] > 1e-4 else None
                # extrados return (top of the proud block, against the wall)
                g.poly(mat_r, [(e0[0], side * hw, e0[1]), (e1[0], side * hw, e1[1]), (e1[0], y, e1[1]), (e0[0], y, e0[1])], (0, 0, 1))
                # step to the next block
                if k + 1 < K:
                    y2 = side * (hw + dep[side][k + 1])
                    if abs(y2 - y) > 1e-4:
                        lo_, hi_ = (y, y2) if abs(y) < abs(y2) else (y2, y)
                        # the face of the block that is proud at the joint, radial plane at th[k+1]
                        big = y if abs(y) > abs(y2) else y2
                        small = y2 if big == y else y
                        nrm = (math.cos(th[k + 1]), 0, -math.sin(th[k + 1]))
                        mat_s = mat_r
                        g.poly(mat_s, [(i1[0], small, i1[1]), (i1[0], big, i1[1]), (e1[0], big, e1[1]), (e1[0], small, e1[1])],
                               (nrm[0] if abs(y) > abs(y2) else -nrm[0], 0, nrm[2] if abs(y) > abs(y2) else -nrm[2]))
            # soffit strip between the two sides
            g.poly(M["soffit"], [(i0[0], -hw, i0[1]), (i1[0], -hw, i1[1]), (i1[0], hw, i1[1]), (i0[0], hw, i0[1])], (0, 0, -1))
    # cutwaters on the pier faces (pointed prisms, facing outward in v)
    if P.get("cutwaters"):
        for s_ in solids[1:-1]:
            u0, u1 = s_["u0"], s_["u1"]
            zt = min((a["zs"] for a in arches if abs(a["ub"] - u0) < 1e-6 or abs(a["ua"] - u1) < 1e-6), default=s_["base"] + 1.0) - 0.15
            if zt - s_["base"] < 0.5:
                continue
            for side in (1, -1):
                y0, ya = side * hw, side * (hw + 0.75 * (u1 - u0))
                uc_ = 0.5 * (u0 + u1)
                g.poly(wall, [(u0, y0, s_["base"]), (uc_, ya, s_["base"]), (uc_, ya, zt), (u0, y0, zt)], (-1, side, 0))
                g.poly(wall, [(uc_, ya, s_["base"]), (u1, y0, s_["base"]), (u1, y0, zt), (uc_, ya, zt)], (1, side, 0))
                g.poly(M["coping"], [(u0, y0, zt), (uc_, ya, zt), (u1, y0, zt)], (0, 0, 1))
    return g.mesh()


# ------------------------------------------------------------------ flat cut stone
def build_flat(plan):
    g = G()
    P, M = plan["p"], plan["mats"]
    L, W = plan["L"], plan["W"]
    d = Prof(plan["deck"])
    hw = W / 2
    t = plan["slab_t"]
    sup = plan["supports"]                                     # [{u0,u1,base}] piers/abutments (u extents), slabs between their centres
    rng = np.random.RandomState(plan["seed"])
    n_across = max(1, int(round(W / P["slab_w_m"])))
    gap = 0.012
    edges = [s_ for s_ in sup]
    for i in range(len(sup) - 1):
        ua, ub = 0.5 * (sup[i]["u0"] + sup[i]["u1"]), 0.5 * (sup[i + 1]["u0"] + sup[i + 1]["u1"])
        if i == 0:
            ua = 0.0
        if i == len(sup) - 2:
            ub = L
        za, zb = float(d(ua)), float(d(ub))
        for j in range(n_across):
            v0 = -hw + W * j / n_across + (gap if j else 0)
            v1 = -hw + W * (j + 1) / n_across - (gap if j < n_across - 1 else 0)
            lo_a, lo_b = za - t, zb - t
            for kk, (x0, x1) in enumerate([(ua + (gap if i else 0), ub - (gap if i < len(sup) - 2 else 0))]):
                g.poly(M["deck"], [(x0, v0, za), (x1, v0, zb), (x1, v1, zb), (x0, v1, za)], (0, 0, 1), uvmode="z")
                g.poly(M["slab"], [(x0, v0, lo_a), (x0, v1, lo_a), (x1, v1, lo_b), (x1, v0, lo_b)], (0, 0, -1), uvmode="z")
                g.poly(M["slab"], [(x0, v0, lo_a), (x1, v0, lo_b), (x1, v0, zb), (x0, v0, za)], (0, -1, 0)) if j == 0 else g.poly(M["slab"], [(x0, v0, lo_a), (x1, v0, lo_b), (x1, v0, zb), (x0, v0, za)], (0, -1, 0))
                g.poly(M["slab"], [(x0, v1, lo_a), (x1, v1, lo_b), (x1, v1, zb), (x0, v1, za)], (0, 1, 0))
                g.poly(M["slab"], [(x0, v0, lo_a), (x0, v1, lo_a), (x0, v1, za), (x0, v0, za)], (-1, 0, 0))
                g.poly(M["slab"], [(x1, v0, lo_b), (x1, v1, lo_b), (x1, v1, zb), (x1, v0, zb)], (1, 0, 0))
    # piers / abutments: coursed cut-stone blocks (no top face: the slab sits on it)
    for s_ in sup:
        zt = float(d(0.5 * (s_["u0"] + s_["u1"]))) - t
        px = P.get("pier_over_m", 0.0)
        g.box(M["pier"], (s_["u0"], -hw + px, s_["base"]), (s_["u1"], hw - px, zt), skip=("+z",))
    # low parapet / kerb
    ph, pt = P["parapet_h"], P["parapet_t"]
    if ph > 0.05:
        pts_u = sorted(set([0.0, L] + [0.5 * (s_["u0"] + s_["u1"]) for s_ in sup]))
        for side in (1, -1):
            for i in range(len(pts_u) - 1):
                a, b = pts_u[i] + (0.0), pts_u[i + 1]
                za, zb = float(d(a)), float(d(b))
                y0, y1 = side * (hw - pt), side * hw
                g.poly(M["slab"], [(a, y1, za), (b, y1, zb), (b, y1, zb + ph), (a, y1, za + ph)], (0, side, 0))
                g.poly(M["slab"], [(a, y0, za), (b, y0, zb), (b, y0, zb + ph), (a, y0, za + ph)], (0, -side, 0))
                g.poly(M["coping"], [(a, y0, za + ph), (b, y0, zb + ph), (b, y1, zb + ph), (a, y1, za + ph)], (0, 0, 1))
            for u_, sg in ((0.0, -1), (L, 1)):
                z0_ = float(d(u_))
                g.poly(M["slab"], [(u_, side * (hw - pt), z0_), (u_, side * hw, z0_), (u_, side * hw, z0_ + ph), (u_, side * (hw - pt), z0_ + ph)], (sg, 0, 0))
    return g.mesh()


# ------------------------------------------------------------------ timber (truss + footbridge)
def build_timber(plan):
    g = G()
    P, M = plan["p"], plan["mats"]
    L, W = plan["L"], plan["W"]
    d = Prof(plan["deck"])
    rng = np.random.RandomState(plan["seed"])
    hw = W / 2
    pt = P["plank_t"]
    sup = plan["supports"]                                      # [{u, base, kind: 'abut'|'bent'}]
    pw, gap = P["plank_w"], P["plank_gap"]
    sr_ = lambda ls: float(np.clip(0.10 + 0.0045 * ls, 0.11, 0.30))
    nstr = max(2, int(round(W / P["stringer_every"])) + 1)
    vs = np.linspace(-hw + 0.28, hw - 0.28, nstr)
    # planks
    nplank = max(1, int((L + gap) / (pw + gap)))
    pw_eff = (L - gap * (nplank - 1)) / nplank
    for k in range(nplank):
        a = k * (pw_eff + gap)
        b = a + pw_eff
        top = float(d(0.5 * (a + b)))
        jt = rng.uniform(-0.004, 0.004)
        ln = hw + rng.uniform(-0.03, 0.03)
        g.box(M["deck"], (a, -ln, top - pt + jt), (b, ln, top + jt), tile=None)
    # stringers per bay
    for i in range(len(sup) - 1):
        ua, ub = sup[i]["u"], sup[i + 1]["u"]
        ls = ub - ua
        r = sr_(ls)
        ex = 0.3 if i == 0 else 0.0
        ey = 0.3 if i == len(sup) - 2 else 0.0
        for v in vs:
            za, zb = float(d(ua - ex)) - pt - r - 0.012, float(d(ub + ey)) - pt - r - 0.012
            g.log(M["log"], (ua - ex, v, za), (ub + ey, v, zb), r, r, n=6, rng=rng, jit=0.07)
    # supports
    for s_ in sup:
        u = s_["u"]
        r = sr_(6.0)
        zc = float(d(u)) - pt - 2 * sr_(6.0) - 0.024 - 0.12                    # cap beam centre under the stringers
        if s_["kind"] == "abut":
            # log crib: sill + two layers of cross logs
            base = s_["base"]
            nlay = max(2, int(math.ceil((zc + 0.12 - base) / 0.30)))
            zz = base + 0.15
            for lay in range(nlay):
                zl = min(zz + lay * 0.30, zc)
                sg = -1.0 if u < 0.5 * L else 1.0                         # the crib sits behind the abutment line (outside the span)
                if lay % 2 == 0:
                    g.log(M["log"], (u + sg * 0.3, -hw - 0.25, zl), (u + sg * 0.3, hw + 0.25, zl), 0.15, 0.15, n=6, rng=rng, jit=0.1)
                else:
                    for v in (-hw + 0.1, hw - 0.1):
                        g.log(M["log"], (u + sg * 0.75, v, zl), (u - sg * 0.15, v, zl), 0.15, 0.15, n=6, rng=rng, jit=0.1)
        else:
            base = s_["base"]
            pv = [-hw + 0.4, hw - 0.4] if W < 3.2 else list(np.linspace(-hw + 0.4, hw - 0.4, 3))
            for v in pv:
                g.log(M["log"], (u + (0.0 if abs(v) < 1e-6 else 0.0), v * 1.0 + np.sign(v) * 0.12, base), (u, v, zc), 0.2, 0.17, n=7, rng=rng, jit=0.08)
            g.log(M["log"], (u, -hw - 0.1, zc + 0.12), (u, hw + 0.1, zc + 0.12), 0.14, 0.14, n=6, rng=rng, jit=0.08)
            for a_, b_ in zip(pv[:-1], pv[1:]):
                zm = base + 0.45 * (zc - base)
                g.log(M["log"], (u - 0.04, a_ + 0.12, base + 0.3), (u + 0.04, b_ - 0.12, zc - 0.1), 0.07, 0.07, n=5, rng=rng, jit=0.1)
                g.log(M["log"], (u + 0.04, a_ + 0.12, zc - 0.1), (u - 0.04, b_ - 0.12, base + 0.3), 0.07, 0.07, n=5, rng=rng, jit=0.1) if False else None
    # sides: truss or simple railing
    style = P.get("side", "rail")
    for side in (1, -1):
        y = side * (hw + 0.14)
        if style == "rail":
            nposts = max(2, int(L / P["post_every"]) + 1)
            for k in range(nposts):
                u = L * k / (nposts - 1)
                z0 = float(d(u))
                g.log(M["log"], (u, y, z0 - 0.05), (u, y, z0 + P["rail_h"]), 0.07, 0.065, n=5, rng=rng, jit=0.12)
            for hh in (P["rail_h"], P["rail_h"] * 0.55):
                g.log(M["log"], (0.0, y + side * 0.05, float(d(0.0)) + hh), (L, y + side * 0.05, float(d(L)) + hh), 0.055, 0.055, n=5, rng=rng, jit=0.1)
        else:
            for i in range(len(sup) - 1):
                ua, ub = sup[i]["u"], sup[i + 1]["u"]
                ls = ub - ua
                ht = float(np.clip(ls * P["truss_depth_ratio"], 1.0, 3.4))
                rc = float(np.clip(0.07 + 0.003 * ls, 0.08, 0.17))
                za, zb = float(d(ua)) + 0.02, float(d(ub)) + 0.02
                g.log(M["log"], (ua, y, za), (ub, y, zb), rc, rc, n=6, rng=rng, jit=0.06)              # bottom chord
                kp = ls <= P["kingpost_max_m"]
                if kp:
                    um = 0.5 * (ua + ub)
                    zm = 0.5 * (za + zb)
                    g.log(M["log"], (ua, y, za + 0.85), (um, y, zm + ht), rc * 0.9, rc * 0.9, n=6, rng=rng, jit=0.06)
                    g.log(M["log"], (um, y, zm + ht), (ub, y, zb + 0.85), rc * 0.9, rc * 0.9, n=6, rng=rng, jit=0.06)
                    g.log(M["log"], (um, y + side * 0.0, zm), (um, y, zm + ht), rc * 0.8, rc * 0.8, n=6, rng=rng, jit=0.06)
                    g.log(M["log"], (ua + 0.3, y, za + 0.1), (um, y, zm + ht * 0.55), rc * 0.55, rc * 0.55, n=5, rng=rng, jit=0.08)
                    g.log(M["log"], (ub - 0.3, y, zb + 0.1), (um, y, zm + ht * 0.55), rc * 0.55, rc * 0.55, n=5, rng=rng, jit=0.08)
                    g.log(M["log"], (ua, y, za + 0.02), (ua, y, za + 0.85), rc * 0.7, rc * 0.7, n=6, rng=rng, jit=0.06)
                    g.log(M["log"], (ub, y, zb + 0.02), (ub, y, zb + 0.85), rc * 0.7, rc * 0.7, n=6, rng=rng, jit=0.06)
                else:
                    g.log(M["log"], (ua, y, za + ht), (ub, y, zb + ht), rc, rc, n=6, rng=rng, jit=0.06)  # top chord
                    npan = max(2, int(round(ls / (ht * 1.1))))
                    pu = [ua + ls * k / npan for k in range(npan + 1)]
                    for k, u in enumerate(pu):
                        zl_, zt_ = float(d(u)) + 0.02, float(d(u)) + 0.02 + ht
                        g.log(M["log"], (u, y + side * 0.002 * (k % 2), zl_), (u, y + side * 0.002 * (k % 2), zt_), rc * 0.75, rc * 0.75, n=6, rng=rng, jit=0.07)
                    for k in range(npan):
                        u0_, u1_ = pu[k], pu[k + 1]
                        z00, z01 = float(d(u0_)) + 0.02, float(d(u1_)) + 0.02
                        # X braces in the two planes (offset by half a log so they do not intersect each other's faces)
                        g.log(M["log"], (u0_, y + side * (rc * 0.9), z00 + 0.1), (u1_, y + side * (rc * 0.9), z01 + ht - 0.1), rc * 0.5, rc * 0.5, n=5, rng=rng, jit=0.08)
                        g.log(M["log"], (u0_, y - side * (rc * 0.9), z00 + ht - 0.1), (u1_, y - side * (rc * 0.9), z01 + 0.1), rc * 0.5, rc * 0.5, n=5, rng=rng, jit=0.08)
    return g.mesh()


BUILDERS = {"arch": build_arch, "flat": build_flat, "timber": build_timber}


def build(plan):
    return BUILDERS[plan["family"]](plan)
