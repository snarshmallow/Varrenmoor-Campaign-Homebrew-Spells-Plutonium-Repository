"""Geometry for building styles (see building_styles.py): raised timber frames, plinths, window bars and shutters, eaves and barge boards,
ridge caps, chimneys, stepped gables, church towers and spires, stave tiers, windmills. Everything is built from real boxes in world scale
(a beam is 4-5 in wide and 2.4 in proud of the wall); nothing relies on a texture for structure. No coplanar overlaps: boxes skip the face that
lies against the wall, studs and braces skip the faces that abut rails, beams subtract the (expanded) window and door holes.

Entry point `decorate(...)`, called by worldpack_detail.build_building_detailed after the walls are built (faces below the wall top join the shell, faces above it
join the roof node when the interior pass splits the mesh).
"""
import math

import numpy as np

import worldpack_mesh as wm
import building_styles_arch as bsa

FT = wm.FT
BEAM_TILE = 3.0
RAIL_H, MIN_PIECE = 0.40, 0.45
CLOSE_STUD_FT = 1.15      # close studding: stud centres (gaps 0.7-0.8 ft between 4-5 in studs)


def _minus(rects, holes, mg):
    """Subtract expanded holes {u0,u1,z0,z1} from rects (u0,u1,z0,z1), all metres."""
    out = list(rects)
    for h in holes:
        hu0, hu1, hz0, hz1 = h["u0"] - mg, h["u1"] + mg, h["z0"] - mg, h["z1"] + mg
        nxt = []
        for (u0, u1, z0, z1) in out:
            if u1 <= hu0 or u0 >= hu1 or z1 <= hz0 or z0 >= hz1:
                nxt.append((u0, u1, z0, z1))
                continue
            if u0 < hu0:
                nxt.append((u0, hu0, z0, z1))
            if u1 > hu1:
                nxt.append((hu1, u1, z0, z1))
            m0, m1 = max(u0, hu0), min(u1, hu1)
            if z0 < hz0:
                nxt.append((m0, m1, z0, hz0))
            if z1 > hz1:
                nxt.append((m0, m1, hz1, z1))
        out = nxt
    return out


def _hits(rect, holes, mg):
    u0, u1, z0, z1 = rect
    return any(not (u1 <= h["u0"] - mg or u0 >= h["u1"] + mg or z1 <= h["z0"] - mg or z0 >= h["z1"] + mg) for h in holes)


class Ctx:
    def __init__(self, b, S, off, zf):
        self.b, self.S, self.off, self.zf = b, S, off, zf

    # ---- generic faces
    def uvface(self, mat, pts, tile_ft):
        self.b.face(mat, pts, wm.world_uv(pts, tile_ft, self.off, self.zf))

    def prism(self, X, mat, quad, d, axis=(1.0, 0.0), skip=(), tile_ft=BEAM_TILE):
        """Raised bar on a wall: `quad` = 4 (u, z) corners in order (bottom-left, bottom-right, top-right, top-left); front face at v = -d (outward),
        side faces back to the wall (v = 0). UV: along `axis` (a unit vector in the (u, z) plane) and across it, so grain follows the bar."""
        T = tile_ft * FT
        au, az = axis

        def uv(u, v, z):
            return ((u * au + z * az) / T, (-u * az + z * au + v) / T)
        front = [X(u, -d, z) for u, z in quad]
        self.b.face(mat, front, [uv(u, -d, z) for u, z in quad])
        for k in range(4):
            if k in skip:
                continue
            (ua, za), (ub, zb) = quad[k], quad[(k + 1) % 4]
            pts = [X(ua, 0, za), X(ub, 0, zb), X(ub, -d, zb), X(ua, -d, za)]
            self.b.face(mat, pts, [uv(ua, 0, za), uv(ub, 0, zb), uv(ub, -d, zb), uv(ua, -d, za)])

    def rect(self, X, mat, u0, u1, z0, z1, d, vertical=False, skip=(), tile_ft=BEAM_TILE):
        quad = [(u0, z0), (u1, z0), (u1, z1), (u0, z1)]
        self.prism(X, mat, quad, d, (0.0, 1.0) if vertical else (1.0, 0.0), skip, tile_ft)


# ------------------------------------------------------------------ walls
def _corner_info(P, D, i):
    """True when the corner at the START of edge i is a convex ~90 degree corner (the post is extended to cover the notch)."""
    n = len(P)
    a, c = D[i - 1], D[i]
    cross = a[0] * c[1] - a[1] * c[0]
    dot = a[0] * c[0] + a[1] * c[1]
    return cross > 0.5 and abs(dot) < 0.5


def wall_frame(g, i, X, L, holes, P, D, zf, zt, floors, S, z0):
    """Timber frame / corner boards on edge i."""
    W = S["wall"]
    sysm = W["system"]
    if sysm not in ("halftimber", "corners"):
        return
    mat = S["beam_mat"]
    bw, d = W["beam_w_ft"] * FT, W["beam_depth_ft"] * FT
    cw = W["corner_ft"] * FT
    rh = RAIL_H * FT
    ph = (S["plinth"]["height_ft"] * FT) if S.get("plinth") else 0.0
    sh = (zt - zf) / floors
    jet = W["jetty_ft"] * FT
    mg = 0.4 * FT + 0.04
    ext = d if _corner_info(P, D, i) else 0.0
    zbot = zf + ph
    zt = zt - (d * S["roof"]["pitch"] + 0.03)            # the roof surface is lower at the beams' outward position: keep the top plate under it
    zg = S.get("_zg")                                    # stone / brick ground storey (preset wall.upper): the frame starts on top of it
    if zg is not None:
        zbot = max(zbot, zg)
        if zt - zbot < 2.0 * FT:
            return
    ztop_all = zt
    # corner posts (full height), a notch filler at the start corner
    g.rect(X, mat, -ext, cw, zbot, ztop_all, d, True, skip=(0,))
    g.rect(X, mat, L - cw, L, zbot, ztop_all, d, True, skip=(0,))
    # rails: (lo, hi, depth) accepted by priority with minimum spacing
    cand = [(zbot, zbot + rh, d, 0), (zt - rh, zt, d, 0)]
    for s in range(1, floors):
        zb = zf + s * sh
        if jet > 0:
            cand.append((zb, zb + 0.8 * FT, d + jet, 1))
        else:
            cand.append((zb - 0.22 * FT, zb + 0.22 * FT, d, 0))
    if sysm == "halftimber":
        for s in range(floors):
            zs = zf + s * sh
            cand.append((zs + 2.55 * FT, zs + 2.55 * FT + rh, d, 0))
            cand.append((zs + 7.5 * FT, zs + 7.5 * FT + rh, d, 0))
    if zg is not None:
        cand = [c for c in cand if c[0] >= zbot - 1e-6]
    acc = []
    for lo, hi, dd, jt in cand:
        if all(lo >= a[1] + 1.1 * FT or hi <= a[0] - 1.1 * FT for a in acc):
            acc.append((lo, hi, dd, jt))
    acc.sort()
    u_a, u_b = cw, L - cw
    for lo, hi, dd, jt in acc:
        for (ua, ub, za, zb_) in _minus([(u_a, u_b, lo, hi)], holes, mg):
            if ub - ua > MIN_PIECE * FT:
                g.rect(X, mat, ua, ub, za, zb_, dd, False)
        if jt:     # joist ends under a jetty bressummer
            n = max(2, int((u_b - u_a) / (1.0 * FT)))
            for k in range(n):
                uc = u_a + (u_b - u_a) * (k + 0.5) / n
                if not _hits((uc - 0.15 * FT, uc + 0.15 * FT, lo - 0.5 * FT, lo), holes, mg):
                    g.rect(X, mat, uc - 0.15 * FT, uc + 0.15 * FT, lo - 0.5 * FT, lo, dd - 0.06 * FT, False)
    if sysm != "halftimber":
        return
    pat = W["pattern"]
    sp = (CLOSE_STUD_FT if pat == "close" else W["spacing_ft"]) * FT
    n = max(1, int(round((u_b - u_a) / sp)))
    xs = [u_a + (u_b - u_a) * k / n for k in range(n + 1)]
    rows = [(a[1], b[0]) for a, b in zip(acc, acc[1:]) if b[0] - a[1] > 0.5 * FT]
    for (zl, zh) in rows:
        for x in xs[1:-1]:
            for (ua, ub, za, zb_) in _minus([(x - bw / 2, x + bw / 2, zl, zh)], holes, mg):
                if zb_ - za > MIN_PIECE * FT:
                    g.rect(X, mat, ua, ub, za, zb_, d, True, skip=(0, 2))
        if pat == "braced" and zh - zl > 1.6 * FT:
            for k in range(n):
                ua, ub = xs[k] + (bw / 2 if k > 0 else 0), xs[k + 1] - (bw / 2 if k < n - 1 else 0)
                ua += 0.0 if k > 0 else (0.0)
                cell = (xs[k], xs[k + 1], zl, zh)
                if _hits(cell, holes, mg) or ub - ua < 1.0 * FT or ub - ua > 7 * FT:
                    continue
                if wm_hash(S["id"], i, k, zl) > 0.62:
                    continue
                left = (xs[k] + xs[k + 1]) / 2 < L / 2
                dz, du = zh - zl, ub - ua
                ln = math.hypot(du, dz)
                wh = bw * ln / dz
                if left:
                    quad = [(ua, zl), (ua + wh, zl), (ub, zh), (ub - wh, zh)]
                    axis = (du / ln, dz / ln)
                else:
                    quad = [(ub - wh, zl), (ub, zl), (ua + wh, zh), (ua, zh)]
                    axis = (-du / ln, dz / ln)
                g.prism(X, mat, quad, d, axis, skip=(0, 2))


def wm_hash(*a):
    import hashlib
    return int(hashlib.md5("|".join(map(str, a)).encode()).hexdigest()[:6], 16) / 0xFFFFFF


def plinth(g, i, X, L, holes, P, D, zf, z0, S):
    pl = S.get("plinth")
    if not pl:
        return
    ph = pl["height_ft"] * FT
    pd = 0.14 * FT
    ext = pd if _corner_info(P, D, i) else 0.0
    mat = S["plinth_mat"]
    tile = 4.0
    for (ua, ub, za, zb_) in _minus([(-ext, L, z0, zf + ph)], holes, 0.4 * FT + 0.02):
        if ub - ua > 0.2 * FT:
            g.prism(X, mat, [(ua, za), (ub, za), (ub, zb_), (ua, zb_)], pd, (1.0, 0.0), skip=(0,), tile_ft=tile)
    # note: prism uses the beam UV; brick plinth uses world UVs instead, rebuilt below for the front faces' texture density
    # (the beam UV is already planar in feet / tile, which is what the brick texture needs)


# ------------------------------------------------------------------ windows
def window_extras(g, i, X, h, t, S, L=None, others=()):
    Wd = S["windows"]
    typ = Wd["type"]
    u0, u1, za, zb_ = h["u0"], h["u1"], h["z0"], h["z1"]
    bar = S["trim_mat"] if Wd.get("frame_color") is None else S["trim_mat"]
    bm = S.get("bar_mat") or bar
    vm = t / 2
    th = 0.025
    cols, rows = max(1, Wd["cols"]), max(1, Wd["rows"])
    w = (u1 - u0)
    hgt = (zb_ - za)

    def bx(mat, ua, ub, zlo, zhi, thick):
        g.rect(X, mat, ua, ub, zlo, zhi, 0.0, False) if False else _inbox(g, X, mat, ua, ub, vm - thick, vm + thick, zlo, zhi)
    if typ in ("casement", "leaded", "sash"):
        main = 0.05 if typ == "casement" else 0.035
        fine = 0.012
        nc, nr = (cols, rows) if typ != "leaded" else (2, 2)
        for k in range(1, nc):
            uc = u0 + w * k / nc
            bx(bm, uc - main, uc + main, za, zb_, th)
        for k in range(1, nr):
            zc = za + hgt * k / nr
            bx(bm, u0, u1, zc - main * 0.8, zc + main * 0.8, th)
        if typ == "leaded":     # fine lattice of lead cames in every pane
            fc, fr = cols * 2, rows * 2
            for k in range(1, fc):
                if k % 2:
                    uc = u0 + w * k / fc
                    bx(bm, uc - fine, uc + fine, za, zb_, 0.012)
            for k in range(1, fr):
                if k % 2:
                    zc = za + hgt * k / fr
                    bx(bm, u0, u1, zc - fine, zc + fine, 0.012)
    elif typ == "slit":
        pass
    if Wd["shutters"] and S.get("shutter_mat"):
        sw = w / 2
        tw = 0.4 * FT
        if Wd.get("shutter_clear") and L is not None and not shutter_fits(h, others, L):
            return
        gp = 0.03 * FT if Wd.get("shutter_clear") else 0.0          # a hair clear of the trim (no shared side faces)
        for (a, c) in ((u0 - tw - gp - sw, u0 - tw - gp), (u1 + tw + gp, u1 + tw + gp + sw)):
            g.rect(X, S["shutter_mat"], a, c, za, zb_ + tw, Wd.get("shutter_d_ft", 0.05) * FT, True, tile_ft=4.5)


def shutter_fits(h, holes, L):
    """Both shutter leaves (half the window width each, beside the 0.4 ft trim) lie inside the wall, clear of the corner posts and of the other openings."""
    tw, sw = 0.4 * FT, (h["u1"] - h["u0"]) / 2
    a, b = h["u0"] - tw - sw - 0.1 * FT, h["u1"] + tw + sw + 0.1 * FT
    if a < 0.75 * FT or b > L - 0.75 * FT:
        return False
    return not any(o is not h and o["u0"] - tw < b and o["u1"] + tw > a and o["z0"] < h["z1"] + tw and o["z1"] > h["z0"] for o in holes)


def _inbox(g, X, mat, ua, ub, va, vb, za, zb_):
    """Box in wall coordinates (v measured inward), all six faces, UV along the longest axis."""
    c = lambda u, v, z: X(u, v, z)
    faces = [[c(ua, va, za), c(ub, va, za), c(ub, va, zb_), c(ua, va, zb_)], [c(ua, vb, za), c(ub, vb, za), c(ub, vb, zb_), c(ua, vb, zb_)],
             [c(ua, va, za), c(ua, vb, za), c(ua, vb, zb_), c(ua, va, zb_)], [c(ub, va, za), c(ub, vb, za), c(ub, vb, zb_), c(ub, va, zb_)],
             [c(ua, va, za), c(ub, va, za), c(ub, vb, za), c(ua, vb, za)], [c(ua, va, zb_), c(ub, va, zb_), c(ub, vb, zb_), c(ua, vb, zb_)]]
    for pts in faces:
        g.b.face(mat, pts, wm.world_uv(pts, 3.0, g.off, g.zf))


# ------------------------------------------------------------------ roof frame of reference
class Roof:
    def __init__(self, cx, e):
        o = e["obb"]
        self.cxm, self.cym = cx.B(o["center"][0], o["center"][1])
        ang = math.radians(o["angle_deg"])
        self.ex = (math.cos(ang), -math.sin(ang))
        self.ey = (-self.ex[1], self.ex[0])
        r = e["roof"]
        self.ov = r.get("overhang_ft", 1.0) * FT
        self.hl, self.hw = o["length_ft"] * FT / 2, o["width_ft"] * FT / 2
        self.Lh, self.Wh = self.hl + self.ov, self.hw + self.ov
        self.rise = r["ridge_height_ft"] * FT
        self.hip = r["type"] == "hip"
        self.slope = self.rise / max(self.hw, 1e-6)

    def zt(self, zt):
        self.zt_ = zt
        self.ze = zt - self.ov * self.slope
        self.zr = zt + self.rise
        return self

    def P(self, l, w, z):
        return (self.cxm + self.ex[0] * l + self.ey[0] * w, self.cym + self.ex[1] * l + self.ey[1] * w, z)

    def roof_z(self, l, w):
        """Roof surface height at (l, w) (gable: ridge along l; hip: min of the two slopes)."""
        z = self.zt_ + self.rise - abs(w) * self.slope
        if self.hip:
            rh = max(self.hl - self.hw, 0)
            ld = max(abs(l) - rh, 0)
            z = min(z, self.zt_ + self.rise - ld * self.slope)
        return z


def _box(g, R, mat, l0, l1, w0, w1, z0, z1, tile=4.0, skip=()):
    """Box in the roof frame (axis aligned to the building's obb)."""
    c = lambda l, w, z: R.P(l, w, z)
    faces = {"w0": [c(l0, w0, z0), c(l1, w0, z0), c(l1, w0, z1), c(l0, w0, z1)], "w1": [c(l0, w1, z0), c(l1, w1, z0), c(l1, w1, z1), c(l0, w1, z1)],
             "l0": [c(l0, w0, z0), c(l0, w1, z0), c(l0, w1, z1), c(l0, w0, z1)], "l1": [c(l1, w0, z0), c(l1, w1, z0), c(l1, w1, z1), c(l1, w0, z1)],
             "z0": [c(l0, w0, z0), c(l1, w0, z0), c(l1, w1, z0), c(l0, w1, z0)], "z1": [c(l0, w0, z1), c(l1, w0, z1), c(l1, w1, z1), c(l0, w1, z1)]}
    for k, pts in faces.items():
        if k not in skip:
            g.uvface(mat, pts, tile)


def tower_holes(R, S):
    """Footprints (l0, l1, w0, w1) in the roof frame of towers that rise THROUGH the roof: the roof sheet is cut away there (clip_roof),
    the ridge cap and barge board stop at the tower wall, so no roof surface passes through the tower volume."""
    out = []
    sp = S["special"]
    if sp.get("tiers"):
        h = tier_half(R, 0)
        out.append((-h, h, -h, h))
    t = sp.get("tower")
    if t:
        ts = t.get("size_ft", 9.0) * FT
        lc = (1 if t.get("end", 1) >= 0 else -1) * (R.hl + ts * 0.15)
        out.append((lc - ts / 2, lc + ts / 2, -ts / 2, ts / 2))
    return out


def tier_half(R, k):
    return min(R.hw * 2, R.hl * 2) * 0.62 * (0.78 ** k) / 2


def _clip(poly, ax, val, side):
    """Sutherland-Hodgman against the half-plane (x[ax] <= val if side < 0 else >= val); vertices are arrays [l, w, z, u, v]."""
    out = []
    for i, a in enumerate(poly):
        b = poly[(i + 1) % len(poly)]
        da, db = (a[ax] - val) * side, (b[ax] - val) * side
        if da >= 0:
            out.append(a)
        if (da > 0 and db < 0) or (da < 0 and db > 0):
            out.append(a + (b - a) * (da / (da - db)))
    return out


def _area3(pa):
    return sum(np.linalg.norm(np.cross(pa[i, :3] - pa[0, :3], pa[i + 1, :3] - pa[0, :3])) for i in range(1, len(pa) - 1))


def clip_roof(mesh, R, S):
    """Cut the single-skin roof (and gable triangles) away inside every tower footprint; pieces keep winding, UVs and material."""
    holes = tower_holes(R, S)
    if not holes:
        return mesh
    V = mesh.V
    L = (V[:, 0] - R.cxm) * R.ex[0] + (V[:, 1] - R.cym) * R.ex[1]
    W = (V[:, 0] - R.cxm) * R.ey[0] + (V[:, 1] - R.cym) * R.ey[1]
    A = np.stack([L, W, V[:, 2], mesh.UV[:, 0], mesh.UV[:, 1]], 1)
    newv, subs = [], {}
    nv = len(V)
    for mat, F in mesh.subs.items():
        for f in F:
            tri = [A[k] for k in f]
            pieces = [tri]
            for (l0, l1, w0, w1) in holes:
                nxt = []
                for pc in pieces:
                    ls = [p[0] for p in pc]
                    ws = [p[1] for p in pc]
                    if max(ls) <= l0 + 1e-9 or min(ls) >= l1 - 1e-9 or max(ws) <= w0 + 1e-9 or min(ws) >= w1 - 1e-9:
                        nxt.append(pc)
                    elif max(ls) - min(ls) < 1e-6:                                 # vertical triangle in a plane l = const (gable end)
                        nxt += [_clip(pc, 1, w0, -1), _clip(pc, 1, w1, 1)]
                    elif max(ws) - min(ws) < 1e-6:
                        nxt.append(pc)
                    else:
                        rest = _clip(pc, 0, l0, 1)
                        mid = _clip(rest, 0, l1, -1)
                        nxt += [_clip(pc, 0, l0, -1), _clip(rest, 0, l1, 1), _clip(mid, 1, w0, -1), _clip(mid, 1, w1, 1)]
                pieces = [q for q in nxt if len(q) >= 3]
            if len(pieces) == 1 and pieces[0] is tri:
                subs.setdefault(mat, []).append(tuple(int(x) for x in f))
                continue
            for pc in pieces:
                pa = np.array(pc)
                if _area3(pa) < 1e-8:
                    continue
                ids = list(range(nv, nv + len(pa)))
                nv += len(pa)
                newv.append(pa)
                for i in range(1, len(ids) - 1):
                    subs.setdefault(mat, []).append((ids[0], ids[i], ids[i + 1]))
    if not newv:
        return mesh
    add = np.concatenate(newv)
    xyz = np.stack([R.cxm + R.ex[0] * add[:, 0] + R.ey[0] * add[:, 1], R.cym + R.ex[1] * add[:, 0] + R.ey[1] * add[:, 1], add[:, 2]], 1)
    return wm.Mesh(np.concatenate([V, xyz]), np.concatenate([mesh.UV, add[:, 3:5]]), subs, mesh.smooth)


def roof_collar(g, R, h, mat):
    """Flashing band where a tower leaves the roof: an upstand that follows the roof surface (sunk 0.12 ft in, 0.5 ft proud), with a flat top ledge."""
    pad, sink, up = 0.28 * FT, 0.12 * FT, 0.5 * FT
    xs = [-h - pad, -h, 0.0, h, h + pad]
    ring = [(-h - pad, w) for w in xs] + [(l, h + pad) for l in xs[1:]] + [(h + pad, w) for w in xs[::-1][1:]] + [(l, -h - pad) for l in xs[::-1][1:-1]]
    cl = lambda v: max(-h, min(h, v))
    n = len(ring)
    for i in range(n):
        (l0, w0), (l1, w1) = ring[i], ring[(i + 1) % n]
        z0_, z1_ = R.roof_z(l0, w0), R.roof_z(l1, w1)
        g.uvface(mat, [R.P(l0, w0, z0_ - sink), R.P(l1, w1, z1_ - sink), R.P(l1, w1, z1_ + up), R.P(l0, w0, z0_ + up)], 3.0)
        i0, i1 = (cl(l0), cl(w0)), (cl(l1), cl(w1))
        if i0 != i1:
            g.uvface(mat, [R.P(l0, w0, z0_ + up), R.P(l1, w1, z1_ + up), R.P(i1[0], i1[1], z1_ + up), R.P(i0[0], i0[1], z0_ + up)], 3.0)


def roof_extras(g, R, e, S, zt, zf, z0):
    Rf = S["roof"]
    mat = S["roof_mat"]
    fm = S.get("fascia_mat") or S["trim_mat"]
    th = Rf["thickness_ft"] * FT
    if th > 0:        # thick roof edge (thatch, turf): vertical fascia under the eave line
        sides = [(-R.Lh, R.Lh, -R.Wh), (R.Lh, -R.Lh, R.Wh)]
        for a, b_, w in sides:
            pts = [R.P(a, w, R.ze), R.P(b_, w, R.ze), R.P(b_, w, R.ze - th), R.P(a, w, R.ze - th)]
            g.uvface(mat, pts, 9.0)
        if R.hip:
            for l, wa, wb in ((R.Lh, -R.Wh, R.Wh), (-R.Lh, R.Wh, -R.Wh)):
                pts = [R.P(l, wa, R.ze), R.P(l, wb, R.ze), R.P(l, wb, R.ze - th), R.P(l, wa, R.ze - th)]
                g.uvface(mat, pts, 9.0)
    holes = tower_holes(R, S)
    if Rf["barge"] and not R.hip:       # barge boards under the rake of a gable roof (they stop at a gable-end tower)
        bh = 0.4 * FT
        for sg in (1, -1):
            a = 0.0
            for (l0, l1, w0, w1) in holes:
                if l0 - 0.05 <= sg * R.Lh <= l1 + 0.05:
                    a = max(a, w1)
            for ws in (-1, 1):
                za = R.zr - (R.zr - R.ze) * a / R.Wh
                pts = [R.P(sg * R.Lh, ws * R.Wh, R.ze), R.P(sg * R.Lh, ws * a, za), R.P(sg * R.Lh, ws * a, za - bh), R.P(sg * R.Lh, ws * R.Wh, R.ze - bh)]
                g.b.face(fm, pts, wm.world_uv(pts, 3.0, g.off, 0.0))
    cap = Rf.get("ridge_cap")
    if cap:
        cm = S.get("cap_mat")
        hw_ = 0.5 * FT
        hgt = 0.34 * FT
        rl = (R.Lh if not R.hip else max(R.Lh - R.Wh, 0.5))
        z = R.zr
        sl = R.slope * hw_
        segs = [(-rl, rl)]
        for (l0, l1, w0, w1) in holes:             # the ridge cap stops at a tower rising through the ridge
            nxt = []
            for a, b_ in segs:
                if b_ <= l0 or a >= l1:
                    nxt.append((a, b_))
                    continue
                if a < l0:
                    nxt.append((a, l0))
                if b_ > l1:
                    nxt.append((l1, b_))
            segs = nxt
        for a, b_ in segs:
            for s in (-1, 1):
                pts = [R.P(a, s * hw_, z - sl), R.P(b_, s * hw_, z - sl), R.P(b_, 0, z + hgt), R.P(a, 0, z + hgt)]
                g.uvface(cm, pts, 3.0)
            for l in (a, b_):
                if any(abs(l - h[0]) < 1e-9 or abs(l - h[1]) < 1e-9 for h in holes):
                    continue                           # the end against a tower wall is hidden
                pts = [R.P(l, -hw_, z - sl), R.P(l, hw_, z - sl), R.P(l, 0, z + hgt)]
                g.uvface(cm, pts, 3.0)


def chimney(g, R, e, S, zt, z0):
    ch = S.get("chimney")
    if not ch:
        return
    for end in ((1, -1) if ch.get("both") else (ch["end"],)):
        _chimney_at(g, R, S, ch, end, zt, z0)


def _chimney_at(g, R, S, ch, end, zt, z0):
    mat = ch["mat"]
    cwid = ch["width_ft"] * FT
    rise = ch["rise_ft"] * FT
    if ch["type"] == "gable":
        l0, l1 = end * (R.hl - 0.35 * FT), end * (R.hl + 1.7 * FT)
        l0, l1 = min(l0, l1), max(l0, l1)
        top = R.zr + rise
        _box(g, R, mat, l0, l1, -cwid / 2, cwid / 2, z0, top, 4.0, skip=("z0", "z1"))       # the wider cap covers the stack top (no touching faces)
        # shoulder: a tapered set-off about 1/3 up
        for a, b_ in ((0.1 * FT, 0.08 * FT),):
            pass
        sw = cwid / 2 + 0.2 * FT
        lo, hi = (l0 - 0.2 * FT, l1 + 0.2 * FT) if True else (l0, l1)
        _box(g, R, mat, lo, hi, -sw, sw, top, top + 0.3 * FT, 4.0)
        pots = ("mat_s_flat_3a3a3e",)
    else:
        lc = end * R.hl * 0.55
        l0, l1 = lc - cwid * 0.4, lc + cwid * 0.4
        top = R.zr + rise
        _box(g, R, mat, l0, l1, -cwid * 0.45, cwid * 0.45, zt, top, 4.0, skip=("z0", "z1"))
        _box(g, R, mat, l0 - 0.18 * FT, l1 + 0.18 * FT, -cwid * 0.45 - 0.18 * FT, cwid * 0.45 + 0.18 * FT, top, top + 0.28 * FT, 4.0)


def stepped_gable(g, R, e, S, zt):
    Rf = S["roof"]
    if not Rf["stepped_gable"] or R.hip:
        return
    mat = S["wall_mat"]
    cap = S.get("step_cap") or mat
    n = max(3, int(R.hw / (1.15 * FT)))
    step_w = R.hw / n
    for sg in (1, -1):
        for side in (-1, 1):
            for k in range(n):
                w0, w1 = side * step_w * k, side * step_w * (k + 1)
                wa, wb = min(w0, w1), max(w0, w1)
                wo = max(abs(w0), abs(w1))               # outer edge: lowest roof height under this step
                zroof = zt + R.rise - (wo - step_w) * R.slope if wo - step_w > 0 else zt + R.rise
                top = zt + R.rise - (abs(w0)) * R.slope + 0.65 * FT
                top = max(top, zt + 0.4 * FT)
                lo, hi = (sg * (R.hl - 0.6 * FT), sg * (R.hl + 0.12 * FT))
                lo, hi = min(lo, hi), max(lo, hi)
                _box(g, R, mat, lo, hi, wa, wb, zt, top, 4.0, skip=("z0",))
                _box(g, R, cap, lo - 0.06 * FT, hi + 0.06 * FT, wa, wb, top, top + 0.16 * FT, 4.0, skip=("z0",))


ROOF_INSET_FT = 0.1       # timber that rises into the roof zone stays this far under the roof surface


def gable_timber(g, R, e, S, zt):
    """Timber on the gable triangles (close studs, tie beam, rafters) of a half-timbered gable roof."""
    W = S["wall"]
    if W["system"] not in ("halftimber", "corners") or R.hip:
        return
    mat = S["beam_mat"]
    bw, d = W["beam_w_ft"] * FT, W["beam_depth_ft"] * FT
    for sg in (1, -1):
        def X(u, v, z, sg=sg):
            return R.P(sg * (R.hl - v), sg * u, z)       # u across the gable (w), v<0 outward along +-l
        # tie beam at the wall top (a continuous plate; also hides the seam)
        g.rect(X, mat, -R.hw + 0.5 * FT, R.hw - 0.5 * FT, zt, zt + RAIL_H * FT, d, False)
        if W["system"] != "halftimber":
            continue
        sp = (1.15 if W["pattern"] == "close" else W["spacing_ft"]) * FT
        n = max(2, int(round(2 * R.hw / sp)))
        rails = []
        if W.get("gable_rails"):            # collar rails across the gable every ~3.9 ft (studs are split at them: no crossing beams)
            zr_ = zt + RAIL_H * FT + 3.9 * FT
            while True:
                hu = (zt + R.rise - zr_ - RAIL_H * FT - 0.35 * FT) / R.slope - 0.15 * FT
                edges_ = [abs(-R.hw + 2 * R.hw * k / n) + bw / 2 for k in range(1, n)]
                hu = max([x for x in edges_ if x <= hu] or [0.0])          # the rail ends flush with the outer face of a stud (no stud half across it)
                if hu < 1.6 * FT:
                    break
                rails.append((zr_, zr_ + RAIL_H * FT, hu))
                g.rect(X, mat, -hu, hu, zr_, zr_ + RAIL_H * FT, d, False)
                zr_ += RAIL_H * FT + 3.9 * FT
        for k in range(1, n):
            u = -R.hw + 2 * R.hw * k / n
            top = zt + R.rise - abs(u) * R.slope - 0.35 * FT
            zlo_ = zt + RAIL_H * FT
            for (ra, rb, hu) in rails + [(None, None, None)]:
                if ra is not None and abs(u) + bw / 2 <= hu + 1e-9:
                    if ra - zlo_ > 0.5 * FT:
                        g.rect(X, mat, u - bw / 2, u + bw / 2, zlo_, ra, d, True, skip=(0, 2))
                    zlo_ = rb
                    continue
                if top - zlo_ > 0.5 * FT:
                    g.rect(X, mat, u - bw / 2, u + bw / 2, zlo_, top, d, True, skip=(0,))
                break
        # rafter beams along the rake: parallelograms under the roof sheet (top edge ROOF_INSET below the roof surface, bottom edge one beam-width lower), so they
        # never poke through the thatch / tiles; they run from the tie beam end up to the apex
        wh = bw * math.sqrt(1 + R.slope ** 2)
        inset = ROOF_INSET_FT * FT
        for s in (-1, 1):
            ua = s * (R.hw - 0.5 * FT)
            top = lambda u: zt + R.rise - abs(u) * R.slope - inset
            quad = [(ua, top(ua) - wh), (0.0, top(0.0) - wh), (0.0, top(0.0)), (ua, top(ua))]
            if s < 0:                                              # keep the winding (right-bottom, left-bottom, left-top, right-top) on both rakes
                quad = [quad[1], quad[0], quad[3], quad[2]]
            ang = math.atan2(top(0.0) - top(ua), -ua)
            g.prism(X, mat, quad, d * 0.8, (math.cos(ang), math.sin(ang)), skip=())


def tower(g, R, e, S, zt, z0):
    sp = S["special"].get("tower")
    if not sp:
        return
    end = 1 if sp.get("end", 1) >= 0 else -1
    ts = sp.get("size_ft", 9.0) * FT
    th = sp.get("height_ft", 26.0) * FT
    mat = S["wall_mat"]
    lc = end * (R.hl + ts * 0.15)
    l0, l1 = lc - ts / 2, lc + ts / 2
    top = zt + th
    _box(g, R, mat, l0, l1, -ts / 2, ts / 2, z0, top, 5.0, skip=("z0", "z1"))
    # string course and parapet cap
    bm = S.get("beam_mat") or mat
    _box(g, R, bm, l0 - 0.12 * FT, l1 + 0.12 * FT, -ts / 2 - 0.12 * FT, ts / 2 + 0.12 * FT, top - 0.45 * FT, top, 4.0, skip=("z0",))
    # belfry openings (dark louvres) on the four faces
    dark = "mat_s_flat_1c1a18"
    ow, oh = 1.6 * FT, 4.2 * FT
    zb_ = top - 8.0 * FT
    for (lw, ww, nl, nw) in ((l1, 0.0, 1, 0), (l0, 0.0, -1, 0), (lc, ts / 2, 0, 1), (lc, -ts / 2, 0, -1)):
        pa, pb = ((lw + nl * 0.02, -ow / 2), (lw + nl * 0.02, ow / 2)) if nl else ((lc - ow / 2, ww + nw * 0.02), (lc + ow / 2, ww + nw * 0.02))
        pts = [R.P(pa[0], pa[1], zb_), R.P(pb[0], pb[1], zb_), R.P(pb[0], pb[1], zb_ + oh), R.P(pa[0], pa[1], zb_ + oh)]
        g.b.face(dark, pts, [(0, 1), (1, 1), (1, 0), (0, 0)])
    sh = sp.get("spire_ft", 0.0) * FT
    sm = S["roof_mat"] if sp.get("spire_mat") is None else sp["spire_mat"]
    if sh > 0:
        h2 = ts / 2 + 0.3 * FT
        apex = R.P(lc, 0, top + sh)
        corners = [R.P(lc - h2, -h2, top), R.P(lc + h2, -h2, top), R.P(lc + h2, h2, top), R.P(lc - h2, h2, top)]
        for k in range(4):
            pts = [corners[k], corners[(k + 1) % 4], apex]
            g.uvface(sm, pts, 9.0)
        # finial: a thin pole and a cross arm
        _box(g, R, S.get("beam_mat") or mat, lc - 0.05 * FT, lc + 0.05 * FT, -0.05 * FT, 0.05 * FT, top + sh, top + sh + 2.2 * FT, 3.0)
        _box(g, R, S.get("beam_mat") or mat, lc - 0.05 * FT, lc + 0.05 * FT, -0.5 * FT, 0.5 * FT, top + sh + 1.2 * FT, top + sh + 1.45 * FT, 3.0)
    else:
        pts = [R.P(lc - ts / 2, -ts / 2, top), R.P(lc + ts / 2, -ts / 2, top), R.P(lc + ts / 2, ts / 2, top), R.P(lc - ts / 2, ts / 2, top)]
        g.uvface(mat, pts, 5.0)


def tiers(g, R, e, S, zt, z0):
    """Stave-church tower: one continuous square shaft. Four corner posts stand on the floor and carry the open central bay up to the wall plate, the board-clad
    tower walls start there and rise THROUGH the roof (the roof sheet is cut away inside the footprint, see clip_roof) with a flashing band at the junction.
    Above the ridge it steps in tier by tier: each tier's walls end under a skirt roof that rises to the next, narrower tier; the last tier carries the spire."""
    sp = S["special"].get("tiers")
    if not sp:
        return
    n = int(sp.get("count", 2))
    wall = S["wall_mat"]
    roof = S["roof_mat"]
    bm = S.get("beam_mat") or wall
    ov = 0.9 * FT
    pitch = 1.1
    h0 = tier_half(R, 0)
    # open central bay: four corner posts floor -> wall plate (the walls above begin exactly at the plate: no overlap)
    pw = 0.7 * FT
    for sl in (-1, 1):
        for sw in (-1, 1):
            la, lb = sorted((sl * h0, sl * (h0 - pw)))
            wa, wb = sorted((sw * h0, sw * (h0 - pw)))
            _box(g, R, wall, la, lb, wa, wb, g.zf, zt, 4.0, skip=("z0", "z1"))
    roof_collar(g, R, h0, S.get("fascia_mat") or S["trim_mat"])
    zb = zt                                                    # bottom of the walls of this tier
    for k in range(n):
        h = tier_half(R, k)
        top = (R.zr if k == 0 else zb) + sp.get("base_ft", 4.0) * FT * (0.9 ** k)
        _box(g, R, wall, -h, h, -h, h, zb, top, 4.5, skip=("z0", "z1"))
        ro = h + ov
        cs = [R.P(-ro, -ro, top), R.P(ro, -ro, top), R.P(ro, ro, top), R.P(-ro, ro, top)]
        ic = [R.P(-h, -h, top), R.P(h, -h, top), R.P(h, h, top), R.P(-h, h, top)]
        for q in range(4):                                     # soffit under the overhang (faces down)
            g.uvface(wall, [cs[q], ic[q], ic[(q + 1) % 4], cs[(q + 1) % 4]], 5.0)
        if k < n - 1:                                          # skirt roof up to the next tier's walls
            h1 = tier_half(R, k + 1)
            zj = top + (ro - h1) * pitch
            inner = [R.P(-h1, -h1, zj), R.P(h1, -h1, zj), R.P(h1, h1, zj), R.P(-h1, h1, zj)]
            for q in range(4):
                g.uvface(roof, [cs[q], cs[(q + 1) % 4], inner[(q + 1) % 4], inner[q]], 9.0)
            zb = zj
        else:                                                  # spire
            apex_z = top + ro * 2.6
            ap = R.P(0, 0, apex_z)
            for q in range(4):
                g.uvface(roof, [cs[q], cs[(q + 1) % 4], ap], 9.0)
            _box(g, R, bm, -0.06 * FT, 0.06 * FT, -0.06 * FT, 0.06 * FT, apex_z - 0.1 * FT, apex_z + 3.0 * FT, 3.0)
    # dragon-head finials on the gable apexes: two crossed boards and a pointed head
    for sg in (1, -1):
        for s in (-1, 1):
            pts = [R.P(sg * R.Lh, 0, R.zr), R.P(sg * R.Lh, s * 1.4 * FT, R.zr + 1.9 * FT), R.P(sg * R.Lh, s * 1.1 * FT, R.zr + 2.1 * FT), R.P(sg * R.Lh, 0, R.zr + 0.35 * FT)]
            g.b.face(bm, pts, wm.world_uv(pts, 3.0, g.off, 0.0))


def windmill(g, R, e, S, zt, z0):
    sp = S["special"].get("windmill")
    if not sp:
        return
    r0 = math.hypot(R.hl, R.hw) * 1.03
    r1 = r0 * 0.7
    top = zt + sp.get("height_ft", 16.0) * FT
    mat = S["wall_mat"]
    n = 8
    ring0 = [R.P(r0 * math.cos(2 * math.pi * k / n + math.pi / 8), r0 * math.sin(2 * math.pi * k / n + math.pi / 8), z0) for k in range(n)]
    ring1 = [R.P(r1 * math.cos(2 * math.pi * k / n + math.pi / 8), r1 * math.sin(2 * math.pi * k / n + math.pi / 8), top) for k in range(n)]
    for k in range(n):
        pts = [ring0[k], ring0[(k + 1) % n], ring1[(k + 1) % n], ring1[k]]
        g.uvface(mat, pts, 5.0)
    # cap: cone
    capm = S["roof_mat"]
    rc = r1 * 1.12
    ap = R.P(0, 0, top + r1 * 0.9)
    ringc = [R.P(rc * math.cos(2 * math.pi * k / n + math.pi / 8), rc * math.sin(2 * math.pi * k / n + math.pi / 8), top) for k in range(n)]
    for k in range(n):
        g.uvface(capm, [ringc[k], ringc[(k + 1) % n], ap], 9.0)
    # sails: four lattice arms on the +l face, rotated 20 deg
    bm = S.get("beam_mat") or mat
    hub = (r1 * 1.0 + 0.3 * FT, 0.0, top - 1.2 * FT)
    arm = sp.get("sail_ft", 17.0) * FT
    for q in range(4):
        a = math.radians(20 + 90 * q)
        du, dz = math.cos(a), math.sin(a)
        nu, nz = -dz, du
        def pt(s, t, o=0.0):
            return R.P(hub[0] + o, s * du + t * nu, hub[2] + s * dz + t * nz)
        # spar
        for t0, t1 in ((-0.12 * FT, 0.12 * FT),):
            pts = [pt(1.2 * FT, t0), pt(arm, t0), pt(arm, t1), pt(1.2 * FT, t1)]
            g.b.face(bm, pts, wm.world_uv(pts, 3.0, g.off, 0.0))
        # slatted sail panel on one side of the spar
        wid = 3.6 * FT
        for k in range(8):
            s0 = 2.2 * FT + (arm - 2.4 * FT) * k / 8
            s1 = s0 + (arm - 2.4 * FT) / 8 * 0.7
            pts = [pt(s0, 0.2 * FT), pt(s1, 0.2 * FT), pt(s1, 0.2 * FT + wid), pt(s0, 0.2 * FT + wid)]
            g.b.face(S.get("sail_mat") or "mat_s_flat_d9d0b8", pts, wm.world_uv(pts, 3.0, g.off, 0.0))


# ------------------------------------------------------------------ burgher-house features (Bridgehollow tiers; all optional preset keys, see building_styles.resolve)
SKIN_D_FT = 0.05          # plaster skin of the timber-framed upper storey, proud of the stone / brick ground-storey shell
TRIM_CLEAR_FT = 0.43      # skins and quoins stop this far from an opening: clear of the 0.4 ft window / door trim (no touching faces)
BAND_H_FT, BAND_D_FT = 0.5, 0.26


def gable_edges(R, P):
    """Edge i -> True when it is a gable end of a gable roof (perpendicular to the ridge, at one end of the obb)."""
    out = []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        L = math.dist(a, b) or 1.0
        along = abs((b[0] - a[0]) * R.ex[0] + (b[1] - a[1]) * R.ex[1]) / L
        lm = ((a[0] + b[0]) / 2 - R.cxm) * R.ex[0] + ((a[1] + b[1]) / 2 - R.cym) * R.ex[1]
        out.append((not R.hip) and along < 0.3 and abs(lm) > 0.6 * R.hl)
    return out


def upper_skin(g, i, X, L, holes, P, D, zg, ztop, S, gable, on_band):
    """Plaster skin of the upper storeys over the stone ground-storey shell (the timber frame sits on it). Cut around every opening and its trim."""
    sd = SKIN_D_FT * FT
    ext = sd if _corner_info(P, D, i) else 0.0
    mg = TRIM_CLEAR_FT * FT
    U0 = -ext
    end_convex = _corner_info(P, D, (i + 1) % len(P))
    pieces = [p for p in _minus([(U0, L, zg, ztop)], holes, mg) if p[1] - p[0] > 1e-6 and p[3] - p[2] > 1e-6]
    eps = 1e-5

    def inside_hole(u, z):
        return any(h["u0"] - mg < u < h["u1"] + mg and h["z0"] - mg < z < h["z1"] + mg for h in holes)

    for (ua, ub, za, zb_) in pieces:
        # side k of the quad: 0 bottom, 1 right, 2 top, 3 left. Draw it only where the piece borders a cut (reveal) or the skin's own outline:
        # sides shared with a neighbouring piece are inside the skin, and the bottom on a string course / the top under a gable skin touch other solids.
        skip = []
        for k, (um, zm, du, dz) in enumerate((((ua + ub) / 2, za, 0, -1), (ub, (za + zb_) / 2, 1, 0), ((ua + ub) / 2, zb_, 0, 1), (ua, (za + zb_) / 2, -1, 0))):
            pu, pz = um + du * eps, zm + dz * eps
            outer = pu < U0 or pu > L or pz < zg or pz > ztop
            if outer:
                if (k == 0 and on_band) or (k == 2 and gable) or (k == 1 and end_convex):
                    skip.append(k)                                  # (the next wall's skin notch covers the end face)
            elif not inside_hole(pu, pz):
                skip.append(k)
        g.prism(X, S["upper_mat"], [(ua, za), (ub, za), (ub, zb_), (ua, zb_)], sd, (1.0, 0.0), skip=tuple(skip), tile_ft=6.0)


def gable_skin(g, R, S, zbase, on_wall_skin):
    """Plaster pentagon on each gable (wall top -> under the rakes, ROOF_INSET below the roof surface), proud of the stone gable by SKIN_D_FT."""
    if R.hip:
        return
    sd = SKIN_D_FT * FT
    ins = 0.03 * FT
    hw = R.hw
    zc = R.zt_ + R.rise - hw * R.slope - ins
    apex = R.zt_ + R.rise - ins
    for sg in (1, -1):
        def X(u, v, z, sg=sg):
            return R.P(sg * (R.hl - v), sg * u, z)
        poly = [(-hw, zbase), (hw, zbase), (hw, zc), (0.0, apex), (-hw, zc)]
        front = [X(u, -sd, z) for u, z in poly]
        g.uvface(S["upper_mat"], front, 6.0)
        for k in range(5):
            if k == 0 and on_wall_skin:
                continue                                            # rests on the wall skin's top (both skipped: no touching faces)
            (ua, za), (ub, zb_) = poly[k], poly[(k + 1) % 5]
            g.uvface(S["upper_mat"], [X(ua, 0, za), X(ub, 0, zb_), X(ub, -sd, zb_), X(ua, -sd, za)], 6.0)


def string_course(g, i, X, L, holes, P, D, zc, S):
    """Weathered stone band under the storey line zc: front, soffit, top sloping down outward (its back edge 0.02 ft under zc, so nothing above touches it)."""
    bd, bh = BAND_D_FT * FT, BAND_H_FT * FT
    ext = bd if _corner_info(P, D, i) else 0.0
    m = S.get("band_mat") or S["trim_mat"]
    z0_, z1b, z1f = zc - bh, zc - 0.02 * FT, zc - 0.1 * FT
    for (ua, ub, za, zb_) in _minus([(-ext, L, z0_, z1b)], holes, TRIM_CLEAR_FT * FT):
        if ub - ua < 0.2 * FT:
            continue
        g.uvface(m, [X(ua, -bd, z0_), X(ub, -bd, z0_), X(ub, -bd, z1f), X(ua, -bd, z1f)], 4.0)
        g.uvface(m, [X(ua, -bd, z1f), X(ub, -bd, z1f), X(ub, 0, z1b), X(ua, 0, z1b)], 4.0)
        g.uvface(m, [X(ua, 0, z0_), X(ub, 0, z0_), X(ub, -bd, z0_), X(ua, -bd, z0_)], 4.0)
        for u in (ua, ub):
            g.uvface(m, [X(u, 0, z0_), X(u, -bd, z0_), X(u, -bd, z1f), X(u, 0, z1b)], 4.0)


def quoins(g, X_of, P, D, edge_holes, zlo, zhi, S, on_plinth, bands=()):
    """Dressed corner stones on every convex corner, long and short faces alternating across the corner, 0.035 ft joints between courses."""
    Q = S.get("quoins")
    if not Q:
        return
    n = len(P)
    qd, ch, gap = Q["depth_ft"] * FT, Q["course_ft"] * FT, 0.035 * FT
    lo_, sh_ = Q["long_ft"] * FT, Q["short_ft"] * FT
    m = S["quoin_mat"]
    for c in range(n):
        if not _corner_info(P, D, c):
            continue
        ip = (c - 1) % n
        Lp = math.dist(P[ip], P[c])
        Xa, Xb = X_of(c), X_of(ip)
        k, z = 0, zlo
        while z + ch * 0.6 < zhi:
            z1 = min(z + ch - gap, zhi)
            la, lb = (lo_, sh_) if k % 2 == 0 else (sh_, lo_)
            clear = not any(z < b1 and z1 > b0 for b0, b1 in bands)          # no stone in a string course (its faces would meet the band's)
            if clear and not _hits((0.0, la, z, z1), edge_holes[c], 0.35 * FT) and not _hits((Lp - lb, Lp, z, z1), edge_holes[ip], 0.35 * FT):
                sk = (0,) if (on_plinth and k == 0) else ()
                g.rect(Xa, m, -qd, la, z, z1, qd, False, skip=sk, tile_ft=4.0)
                g.rect(Xb, m, Lp - lb, Lp, z, z1, qd, False, skip=sk, tile_ft=4.0)
            z += ch
            k += 1


def _rbox(g, R, s, mat, l0, l1, w0, w1, z0, z1, tile=3.0, skip=()):
    """_box with w mirrored to side s (w0 < w1 given for side +1)."""
    wa, wb = sorted((s * w0, s * w1))
    sk = tuple({"w0": "w1", "w1": "w0"}.get(k, k) if s < 0 else k for k in skip)
    _box(g, R, mat, l0, l1, wa, wb, z0, z1, tile, skip=sk)


def dormer_spots(R, S):
    """[(side, l_centre)] for the roof's dormers, plus the dormer dimensions; [] when the roof is too low or too small."""
    Dm = S.get("dormers")
    if not Dm or R.slope < 0.7:
        return [], None
    W, Hf, pd = Dm["width_ft"] * FT, Dm["height_ft"] * FT, Dm["pitch"]
    ovd, tk = 0.45 * FT, 0.12 * FT
    wf = R.hw - Dm["inset_ft"] * FT
    if wf < 3.2 * FT:
        return [], None
    zb = R.zt_ + R.rise - wf * R.slope
    Hf = min(Hf, R.zr - 1.0 * FT - W / 2 * pd - zb)
    if Hf < 2.8 * FT:
        return [], None
    ztop = zb + Hf
    zrd = ztop + W / 2 * pd
    w_r = (R.zt_ + R.rise - zrd) / R.slope
    half = W / 2 + ovd
    rh = max(R.hl - R.hw, 0.0) if R.hip else None
    lim = (rh + (R.hw - (wf + ovd)) - 0.4 * FT - half) if R.hip else (R.hl - 1.6 * FT - half)
    if lim < 0:
        return [], None
    n = Dm["count"]
    if n in (None, "auto"):
        n = 1 + int(2 * lim / (W + 6.0 * FT))
    n = max(1, min(int(n), 3))
    while n > 1 and (2 * lim + 2 * half) / n < W + 2.2 * FT:
        n -= 1
    span = 2 * lim + 2 * half
    ls = [-span / 2 + span * (k + 0.5) / n for k in range(n)]
    ch = S.get("chimney")                                  # a ridge chimney near the dormer's back end: keep clear of it
    blocked = []
    if ch and ch["type"] != "gable":
        cwid = ch["width_ft"] * FT
        if w_r < cwid * 0.45 + 0.4 * FT:
            for end in ((1, -1) if ch.get("both") else (ch["end"],)):
                lc = end * R.hl * 0.55
                blocked.append((lc - cwid * 0.4 - 0.3 * FT, lc + cwid * 0.4 + 0.3 * FT))
    ls = [l for l in ls if not any(l + half > a and l - half < b for a, b in blocked)]
    sides = (1, -1) if Dm["sides"] == 2 else (Dm["side"],)
    dims = {"W": W, "Hf": Hf, "pd": pd, "ovd": ovd, "tk": tk, "wf": wf, "zb": zb, "ztop": ztop, "zrd": zrd, "w_r": w_r, "half": half}
    return [(s, l) for s in sides for l in ls], dims


def _dormer_roof_polys(R, d, lc):
    """Top polygons [(l, w, z)] (side +1 frame) of the two dormer roof planes: ridge -> eave, front edge -> valley with the main roof."""
    out = []
    zr0 = R.zt_ + R.rise
    ze = d["zrd"] - d["half"] * d["pd"]
    wv = (zr0 - ze) / R.slope
    for x in (-1, 1):
        out.append([(lc, d["wf"] + d["ovd"], d["zrd"]), (lc + x * d["half"], d["wf"] + d["ovd"], ze), (lc + x * d["half"], wv, ze), (lc, d["w_r"], d["zrd"])])
    return out


def dormers(g, R, S):
    """Gabled dormers on the eave slopes: front wall with a glazed casement in a trim frame, slate-hung cheeks (roof material) buried 0.1 ft into the roof,
    a small gable roof (slab with fascia) whose back edges run down the valleys into the main roof."""
    spots, d = dormer_spots(R, S)
    if not spots:
        return
    W, wf, zb, ztop, zrd, tk = d["W"], d["wf"], d["zb"], d["ztop"], d["zrd"], d["tk"]
    sink = 0.1 * FT
    fm = S.get("upper_mat") or S["wall_mat"]
    cm, rm = S["roof_mat"], S["roof_mat"]
    tm = S.get("fascia_mat") or S["trim_mat"]
    frame = S["trim_mat"] if S["trim_mat"] != S.get("beam_mat") else (S.get("fascia_mat") or S["trim_mat"])
    zroof = lambda w: R.zt_ + R.rise - w * R.slope
    ww = min(2.2 * FT, W - 1.3 * FT)
    sill = zb + 0.75 * FT
    wtop = min(ztop - 0.45 * FT, sill + 3.0 * FT)
    for s, lc in spots:
        Pq = lambda l, w, z, s=s: R.P(l, s * w, z)
        l0, l1 = lc - W / 2, lc + W / 2
        a0, a1 = lc - ww / 2, lc + ww / 2
        # front wall around the window
        for (la, lb, za, zb_) in ((l0, a0, zb - sink, ztop), (a1, l1, zb - sink, ztop), (a0, a1, zb - sink, sill), (a0, a1, wtop, ztop)):
            g.uvface(fm, [Pq(la, wf, za), Pq(lb, wf, za), Pq(lb, wf, zb_), Pq(la, wf, zb_)], 6.0)
        g.uvface(fm, [Pq(l0, wf, ztop), Pq(l1, wf, ztop), Pq(lc, wf, zrd - tk * 0.5)], 6.0)
        # reveal and glass 0.25 ft back
        rv = 0.25 * FT
        for pts in ([Pq(a0, wf, sill), Pq(a1, wf, sill), Pq(a1, wf - rv, sill), Pq(a0, wf - rv, sill)], [Pq(a0, wf, wtop), Pq(a1, wf, wtop), Pq(a1, wf - rv, wtop), Pq(a0, wf - rv, wtop)],
                    [Pq(a0, wf, sill), Pq(a0, wf - rv, sill), Pq(a0, wf - rv, wtop), Pq(a0, wf, wtop)], [Pq(a1, wf, sill), Pq(a1, wf - rv, sill), Pq(a1, wf - rv, wtop), Pq(a1, wf, wtop)]):
            g.uvface(fm, pts, 6.0)
        g.uvface("mat_glass", [Pq(a0, wf - rv, sill), Pq(a1, wf - rv, sill), Pq(a1, wf - rv, wtop), Pq(a0, wf - rv, wtop)], 3.0)
        bm = frame                                               # not the beam material: frame members never rise above the roof (TimberStaysUnderRoof)
        lm, zm = (a0 + a1) / 2, (sill + wtop) / 2
        _rbox(g, R, s, bm, lm - 0.04 * FT, lm + 0.04 * FT, wf - rv - 0.05 * FT, wf - rv + 0.05 * FT, sill, wtop, skip=("z0", "z1"))
        _rbox(g, R, s, bm, a0, lm - 0.04 * FT, wf - rv - 0.04 * FT, wf - rv + 0.04 * FT, zm - 0.035 * FT, zm + 0.035 * FT, skip=("l0", "l1"))
        _rbox(g, R, s, bm, lm + 0.04 * FT, a1, wf - rv - 0.04 * FT, wf - rv + 0.04 * FT, zm - 0.035 * FT, zm + 0.035 * FT, skip=("l0", "l1"))
        # trim frame proud of the front (0.1 ft), sill board below
        fw = 0.22 * FT
        _rbox(g, R, s, frame, a0 - fw, a0, wf, wf + 0.1 * FT, sill, wtop + fw, skip=("w0", "z0"))      # jambs stand on the sill board
        _rbox(g, R, s, frame, a1, a1 + fw, wf, wf + 0.1 * FT, sill, wtop + fw, skip=("w0", "z0"))
        _rbox(g, R, s, frame, a0, a1, wf, wf + 0.1 * FT, wtop, wtop + fw, skip=("w0", "l0", "l1"))
        _rbox(g, R, s, frame, a0 - fw - 0.1 * FT, a1 + fw + 0.1 * FT, wf, wf + 0.2 * FT, sill - 0.18 * FT, sill, skip=("w0",))
        # cheeks: front edge -> where the dormer top meets the roof, bottom edge 0.1 ft under the roof surface
        wt = (R.zt_ + R.rise - ztop) / R.slope - sink / R.slope
        for l in (l0, l1):
            g.uvface(cm, [Pq(l, wf, zb - sink), Pq(l, wf, ztop), Pq(l, wt, ztop)], 6.0)
        # roof slabs
        for top in _dormer_roof_polys(R, d, lc):
            T = [Pq(l, w, z) for l, w, z in top]
            B = [Pq(l, w, z - tk) for l, w, z in top]
            g.uvface(rm, T, 9.0)
            g.uvface(rm, B[::-1], 9.0)
            for k in (0, 1):                                     # front fascia (ridge -> eave) and eave fascia (front -> valley)
                g.uvface(tm, [T[k], T[k + 1], B[k + 1], B[k]], 3.0)


def roof_snow(g, R, S):
    """Snow: the roof facets (gable or hip) and the dormer roofs raised by the snow depth (a separate sheet, never coplanar with the roof), closed at the eaves and verges.
    It covers the ridge cap (cap 0.34 ft < snow depth); chimneys, finials and dormer fronts rise through it."""
    sn = S["special"].get("snow")
    if not sn or not S.get("snow_mat"):
        return
    dz = sn.get("depth_ft", 0.4) * FT
    m = S["snow_mat"]
    Lh, Wh, zr = R.Lh + 0.06 * FT, R.Wh + 0.06 * FT, R.zr          # 0.06 ft past the roof edges: the verge / eave strips never share a plane with the ridge cap ends
    ze = zr - Wh * R.slope
    facets = []
    if R.hip:
        rh = max(R.hl - R.hw, 0.0)
        for s in (1, -1):
            facets.append([(-rh, 0.0, zr), (rh, 0.0, zr), (Lh, s * Wh, ze), (-Lh, s * Wh, ze)] if rh > 1e-6 else [(0.0, 0.0, zr), (Lh, s * Wh, ze), (-Lh, s * Wh, ze)])
            facets.append([(s * rh, 0.0, zr), (s * Lh, Wh, ze), (s * Lh, -Wh, ze)])
        edges = [((-Lh, -Wh), (Lh, -Wh)), ((Lh, -Wh), (Lh, Wh)), ((Lh, Wh), (-Lh, Wh)), ((-Lh, Wh), (-Lh, -Wh))]
        for (la, wa), (lb, wb) in edges:
            g.uvface(m, [R.P(la, wa, ze), R.P(lb, wb, ze), R.P(lb, wb, ze + dz), R.P(la, wa, ze + dz)], 6.0)
    else:
        for s in (1, -1):
            facets.append([(-Lh, 0.0, zr), (Lh, 0.0, zr), (Lh, s * Wh, ze), (-Lh, s * Wh, ze)])
            g.uvface(m, [R.P(-Lh, s * Wh, ze), R.P(Lh, s * Wh, ze), R.P(Lh, s * Wh, ze + dz), R.P(-Lh, s * Wh, ze + dz)], 6.0)
            for l in (-Lh, Lh):
                g.uvface(m, [R.P(l, 0.0, zr), R.P(l, s * Wh, ze), R.P(l, s * Wh, ze + dz), R.P(l, 0.0, zr + dz)], 6.0)
    spots, d = dormer_spots(R, S)
    for f in facets:
        g.uvface(m, [R.P(l, w, z + dz) for l, w, z in f], 6.0)
    for s, lc in spots:
        for top in _dormer_roof_polys(R, d, lc):
            g.uvface(m, [R.P(l, s * w, z + dz) for l, w, z in top], 6.0)
            (la, wa, za), (lb, wb, zb_) = top[1], top[2]
            g.uvface(m, [R.P(la, s * wa, za), R.P(lb, s * wb, zb_), R.P(lb, s * wb, zb_ + dz), R.P(la, s * wa, za + dz)], 6.0)
            (la, wa, za), (lb, wb, zb_) = top[0], top[1]
            g.uvface(m, [R.P(la, s * wa, za), R.P(lb, s * wb, zb_), R.P(lb, s * wb, zb_ + dz), R.P(la, s * wa, za + dz)], 6.0)


def finials(g, R, S):
    """Turned finial with a pendant at both gable apexes (one post through the barge apex, a knob on top)."""
    if not S.get("finials") or R.hip:
        return
    m = S.get("fascia_mat") or S["trim_mat"]
    a, k = 0.11 * FT, 0.2 * FT
    for sg in (1, -1):
        l = sg * R.Lh
        _box(g, R, m, l - a, l + a, -a, a, R.zr - 1.2 * FT, R.zr + 1.6 * FT, 3.0, skip=("z1",))
        _box(g, R, m, l - k, l + k, -k, k, R.zr + 1.6 * FT, R.zr + 2.0 * FT, 3.0)


# ------------------------------------------------------------------ entry point
def decorate(cx, e, g_builder, S, P, D, N, edge_holes, zf, zt, floors, X_of, t_wall, off):
    """Add the style's geometry to `g_builder` (the detailed shell's Builder).
    X_of(i) -> X(u, v, z) function of edge i, the same frame worldpack_detail uses (v measured inward)."""
    z0 = zf - e["skirt_depth_ft"] * FT
    g = Ctx(g_builder, S, off, zf)
    S["bar_mat"] = S.get("beam_mat") or S["trim_mat"]
    R = Roof(cx, e).zt(zt)
    up = S.get("upper")
    S["_zg"] = None
    zg_skin = None
    if up:                                                   # stone / brick ground storey (the shell), plaster + timber frame above it
        zg = zf + (zt - zf) / max(floors, 1) * up["ground_storeys"]
        S["_zg"] = zg
        if zt - zg > 4.0 * FT:
            zg_skin = zg
    gables = gable_edges(R, P)
    band = bool(S.get("string_course"))
    sd = SKIN_D_FT * FT
    ztop_skin = zt - sd * R.slope - 0.01
    ph = S["plinth"]["height_ft"] * FT if S.get("plinth") else 0.0
    all_fholes = []
    for i in range(len(P)):
        L = math.dist(P[i], P[(i + 1) % len(P)])
        X = X_of(i)
        holes = edge_holes[i]
        plinth(g, i, X, L, holes, P, D, zf, z0, S)
        fholes = holes
        if S["windows"].get("shutter_clear") and S["windows"]["shutters"]:     # frame members stop beside shutters instead of crossing them
            fholes = holes + [{"u0": h["u0"] - (h["u1"] - h["u0"]) / 2 - 0.45 * FT, "u1": h["u1"] + (h["u1"] - h["u0"]) / 2 + 0.45 * FT, "z0": h["z0"], "z1": h["z1"] + 0.4 * FT,
                               "kind": "shutter"} for h in holes if h["kind"] == "window" and shutter_fits(h, holes, L)]
        wall_frame(g, i, X, L, fholes, P, D, zf, zt, floors, S, z0)
        if zg_skin is not None:
            upper_skin(g, i, X, L, holes, P, D, zg_skin, ztop_skin, S, gables[i], band)
            if band:
                string_course(g, i, X, L, holes, P, D, zg_skin, S)
        elif band and floors > 1 and not up:                  # stone civic building: a band at every storey line
            for s in range(1, floors):
                string_course(g, i, X, L, holes, P, D, zf + (zt - zf) * s / floors, S)
        for h in holes:
            if h["kind"] == "window":
                if h.get("shape"):                           # arched / round window: tracery bars follow the outline (building_styles_arch.py)
                    bsa.tracery(g, X, h, t_wall, S["bar_mat"])
                elif S["windows"]["type"] != "plain" or S["windows"]["shutters"]:
                    window_extras(g, i, X, h, t_wall, S, L, holes)
        all_fholes.append(fholes)
    if S.get("quoins"):
        qd = S["quoins"]["depth_ft"] * FT
        if zg_skin is not None:
            zhi = zg_skin - ((BAND_H_FT + 0.05) * FT if band else 0.05 * FT)
        else:
            zhi = zt - qd * R.slope - 0.12 * FT
        bands = [(zf + (zt - zf) * s / floors - (BAND_H_FT + 0.05) * FT, zf + (zt - zf) * s / floors + 0.05 * FT) for s in range(1, floors)] if (band and not up) else []
        quoins(g, X_of, P, D, all_fholes, zf + ph if ph else zf, zhi, S, bool(ph), bands)
    if S["roof"].get("ridge_cap") and not S.get("cap_mat"):
        S["cap_mat"] = S["roof_mat"]
    roof_extras(g, R, e, S, zt, zf, z0)
    chimney(g, R, e, S, zt, z0)
    stepped_gable(g, R, e, S, zt)
    if up and up.get("gables") and S.get("upper_mat"):
        gable_skin(g, R, S, ztop_skin, zg_skin is not None)
    gable_timber(g, R, e, S, zt)
    dormers(g, R, S)
    finials(g, R, S)
    roof_snow(g, R, S)
    tower(g, R, e, S, zt, z0)
    if S["special"].get("rose"):
        bsa.gable_rose(g, R, S, zt, S["special"]["rose"])
    tiers(g, R, e, S, zt, z0)
    windmill(g, R, e, S, zt, z0)
