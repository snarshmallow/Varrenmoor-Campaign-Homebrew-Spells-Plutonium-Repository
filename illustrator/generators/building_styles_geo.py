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

FT = wm.FT
BEAM_TILE = 3.0
RAIL_H, MIN_PIECE = 0.40, 0.45


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
    sp = (1.15 if pat == "close" else W["spacing_ft"]) * FT
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
def window_extras(g, i, X, h, t, S):
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
        for (a, c) in ((u0 - tw - sw, u0 - tw), (u1 + tw, u1 + tw + sw)):
            g.rect(X, S["shutter_mat"], a, c, za, zb_ + tw, 0.05 * FT, True, tile_ft=4.5)


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
    if Rf["barge"] and not R.hip:       # barge boards under the rake of a gable roof
        bh = 0.4 * FT
        for sg in (1, -1):
            for ws in (-1, 1):
                pts = [R.P(sg * R.Lh, ws * R.Wh, R.ze), R.P(sg * R.Lh, 0, R.zr), R.P(sg * R.Lh, 0, R.zr - bh), R.P(sg * R.Lh, ws * R.Wh, R.ze - bh)]
                g.b.face(fm, pts, wm.world_uv(pts, 3.0, g.off, 0.0))
    cap = Rf.get("ridge_cap")
    if cap:
        cm = S.get("cap_mat")
        hw_ = 0.5 * FT
        hgt = 0.34 * FT
        rl = (R.Lh if not R.hip else max(R.Lh - R.Wh, 0.5))
        z = R.zr
        sl = R.slope * hw_
        for s in (-1, 1):
            pts = [R.P(-rl, s * hw_, z - sl), R.P(rl, s * hw_, z - sl), R.P(rl, 0, z + hgt), R.P(-rl, 0, z + hgt)]
            g.uvface(cm, pts, 3.0)
        for l in (-rl, rl):
            pts = [R.P(l, -hw_, z - sl), R.P(l, hw_, z - sl), R.P(l, 0, z + hgt)]
            g.uvface(cm, pts, 3.0)


def chimney(g, R, e, S, zt, z0):
    ch = S.get("chimney")
    if not ch:
        return
    mat = ch["mat"]
    cwid = ch["width_ft"] * FT
    rise = ch["rise_ft"] * FT
    end = ch["end"]
    if ch["type"] == "gable":
        l0, l1 = end * (R.hl - 0.35 * FT), end * (R.hl + 1.7 * FT)
        l0, l1 = min(l0, l1), max(l0, l1)
        top = R.zr + rise
        _box(g, R, mat, l0, l1, -cwid / 2, cwid / 2, z0, top, 4.0, skip=("z0",))
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
        _box(g, R, mat, l0, l1, -cwid * 0.45, cwid * 0.45, zt, top, 4.0, skip=("z0",))
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
        for k in range(1, n):
            u = -R.hw + 2 * R.hw * k / n
            top = zt + R.rise - abs(u) * R.slope - 0.35 * FT
            if top - (zt + RAIL_H * FT) > 0.5 * FT:
                g.rect(X, mat, u - bw / 2, u + bw / 2, zt + RAIL_H * FT, top, d, True, skip=(0,))
        # rafter beams along the rake (parallelograms)
        for s in (-1, 1):
            wh = bw * math.sqrt(1 + R.slope ** 2)
            ua, ub = s * R.hw, 0.0
            quad = [(ua, zt), (ua - s * 0.0, zt + wh), (ub, zt + R.rise), (ub, zt + R.rise - wh)] if False else None
            pa = (s * R.hw, zt + RAIL_H * FT)
            pb = (0.0, zt + R.rise)
            # lower edge of the rafter: offset down by wh
            quad = [(pa[0], pa[1] - 0.0), (pb[0], pb[1] - wh), (pb[0], pb[1]), (pa[0], pa[1] + wh)] if s > 0 else [(pb[0], pb[1] - wh), (pa[0], pa[1]), (pa[0], pa[1] + wh), (pb[0], pb[1])]
            ang = math.atan2(pb[1] - pa[1], pb[0] - pa[0]) if s > 0 else math.atan2(pb[1] - pa[1], pb[0] - pa[0])
            g.prism(X, mat, quad if s > 0 else quad, d * 0.8, (math.cos(ang), math.sin(ang)), skip=())


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
    """Stave-church style stacked roofs: square lantern bases with steep pyramidal roofs rising from the ridge, a spire and dragon finials."""
    sp = S["special"].get("tiers")
    if not sp:
        return
    n = int(sp.get("count", 2))
    wall = S["wall_mat"]
    roof = S["roof_mat"]
    size = min(R.hw * 2, R.hl * 2) * 0.62
    z = R.zr - 0.4 * FT
    for k in range(n):
        s = size * (0.78 ** k)
        bh = sp.get("base_ft", 4.0) * FT * (0.9 ** k)
        _box(g, R, wall, -s / 2, s / 2, -s / 2, s / 2, z, z + bh, 4.5, skip=("z0", "z1"))
        ov = 0.9 * FT
        ro = s / 2 + ov
        ap = R.P(0, 0, z + bh + (ro * 1.5 if k < n - 1 else ro * 2.6))
        zr0 = z + bh
        cs = [R.P(-ro, -ro, zr0), R.P(ro, -ro, zr0), R.P(ro, ro, zr0), R.P(-ro, ro, zr0)]
        for q in range(4):
            g.uvface(roof, [cs[q], cs[(q + 1) % 4], ap], 9.0)
        z = z + bh * 0.9
    top = z + 0.0
    bm = S.get("beam_mat") or wall
    _box(g, R, bm, -0.06 * FT, 0.06 * FT, -0.06 * FT, 0.06 * FT, top + size * 0.9, top + size * 0.9 + 3.0 * FT, 3.0)
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


# ------------------------------------------------------------------ entry point
def decorate(cx, e, g_builder, S, P, D, N, edge_holes, zf, zt, floors, X_of, t_wall, off):
    """Add the style's geometry to `g_builder` (the detailed shell's Builder).
    X_of(i) -> X(u, v, z) function of edge i, the same frame worldpack_detail uses (v measured inward)."""
    z0 = zf - e["skirt_depth_ft"] * FT
    g = Ctx(g_builder, S, off, zf)
    S["bar_mat"] = S.get("beam_mat") or S["trim_mat"]
    for i in range(len(P)):
        L = math.dist(P[i], P[(i + 1) % len(P)])
        X = X_of(i)
        holes = edge_holes[i]
        plinth(g, i, X, L, holes, P, D, zf, z0, S)
        wall_frame(g, i, X, L, holes, P, D, zf, zt, floors, S, z0)
        if S["windows"]["type"] != "plain" or S["windows"]["shutters"]:
            for h in holes:
                if h["kind"] == "window":
                    window_extras(g, i, X, h, t_wall, S)
    R = Roof(cx, e).zt(zt)
    if S["roof"].get("ridge_cap") and not S.get("cap_mat"):
        S["cap_mat"] = S["roof_mat"]
    roof_extras(g, R, e, S, zt, zf, z0)
    chimney(g, R, e, S, zt, z0)
    stepped_gable(g, R, e, S, zt)
    gable_timber(g, R, e, S, zt)
    tower(g, R, e, S, zt, z0)
    tiers(g, R, e, S, zt, z0)
    windmill(g, R, e, S, zt, z0)
