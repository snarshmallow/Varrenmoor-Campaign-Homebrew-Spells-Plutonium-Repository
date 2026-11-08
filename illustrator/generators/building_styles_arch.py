"""Arched and circular openings for building styles: real geometry in the wall, not a texture.

A hole dict from worldpack_detail.plan_holes ({u0,u1,z0,z1,kind[,door]}) gets `shape` ("round_arch" | "pointed" | "rose") and `zs` (springing line,
or the circle centre for "rose"). The wall builder keeps cutting the bounding rectangle (u0..u1 x z0..z1) and this module fills the corners
(spandrels) on both wall faces, so the opening seen from outside is the arch; then it adds the reveals (jambs, curved soffit), the stone surround
(jambs + voussoirs), the glass pane and the door leaf outline.

  round_arch  semicircle, radius = width / 2
  pointed     equilateral two-centred arch (gothic lancet): each half is an arc of radius = width centred on the opposite springing point
  rose        circle of diameter = width (square bounding box)

All faces are oriented by a point they must face (away from the stone, toward the open side), so single-sided materials draw correctly.
Windows stay in `edge_holes` as kind "window" (glass material mat_glass), so the split exporter and the interior layout see the same hole list.
"""
import math

import worldpack_mesh as wm

FT = wm.FT
SHAPES = ("rect", "round_arch", "pointed", "rose", "triple_lancet")
N_HALF = 6                      # segments per half arch
SQ3 = math.sqrt(3.0) / 2.0


def rise_of(shape, w):
    if shape == "round_arch":
        return w / 2.0
    if shape == "pointed":
        return SQ3 * w
    return w                    # rose: the bounding square


def _dedupe(pts, eps=1e-7):
    out = []
    for p in pts:
        if not out or math.dist(out[-1], p) > eps:
            out.append(p)
    if len(out) > 1 and math.dist(out[0], out[-1]) <= eps:
        out.pop()
    return out


def curve(u0, u1, zs, shape, d=0.0, n=N_HALF):
    """Arch outline from the left to the right springing point as [(u, z)], offset outward by d (d < 0 = inside)."""
    w = u1 - u0
    if shape == "round_arch":
        c, r = (u0 + u1) / 2, w / 2 + d
        return [(c + r * math.cos(math.pi * (1 - k / (2 * n))), zs + r * math.sin(math.pi * (1 - k / (2 * n)))) for k in range(2 * n + 1)]
    R = w + d                                   # pointed
    th_a = math.acos(-(w / 2) / R) if R > w / 2 else math.pi / 2
    left = [(u1 + R * math.cos(math.pi + (th_a - math.pi) * k / n), zs + R * math.sin(math.pi + (th_a - math.pi) * k / n)) for k in range(n + 1)]
    right = [(u0 + R * math.cos((math.pi - th_a) * (1 - k / n)), zs + R * math.sin((math.pi - th_a) * (1 - k / n))) for k in range(n + 1)]
    return left + right[1:]


def circle(uc, zc, r, n=16):
    return [(uc + r * math.cos(2 * math.pi * k / n), zc + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def prep(h, shape):
    """Mark a hole as arched / round. Window and door heights stay the hole's z0..z1; the arch occupies the top `rise`."""
    w = h["u1"] - h["u0"]
    h["shape"] = shape
    if shape == "rose":
        h["z1"] = h["z0"] + w
        h["zs"] = h["z0"] + w / 2          # centre
    else:
        rise = min(rise_of(shape, w), (h["z1"] - h["z0"]) * 0.8)
        h["zs"] = h["z1"] - rise
    return h


# ------------------------------------------------------------------ helpers
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _oriented(face, mat, pts, toward):
    """Emit `pts` (convex polygon) with its normal pointing to the side of the point `toward`."""
    pts = list(pts)
    if len(pts) < 3:
        return
    n = (0.0, 0.0, 0.0)
    for k in range(1, len(pts) - 1):
        c = _cross(_sub(pts[k], pts[0]), _sub(pts[k + 1], pts[0]))
        n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
    if sum(n[i] * (toward[i] - pts[0][i]) for i in range(3)) < 0:
        pts.reverse()
    face(mat, pts)


def _away(face, mat, pts, centre):
    pts = list(pts)
    n = (0.0, 0.0, 0.0)
    for k in range(1, len(pts) - 1):
        c = _cross(_sub(pts[k], pts[0]), _sub(pts[k + 1], pts[0]))
        n = (n[0] + c[0], n[1] + c[1], n[2] + c[2])
    if sum(n[i] * (pts[0][i] - centre[i]) for i in range(3)) < 0:
        pts.reverse()
    face(mat, pts)


def _opening_curve(h):
    u0, u1, zs = h["u0"], h["u1"], h["zs"]
    if h["shape"] == "rose":
        return circle((u0 + u1) / 2, zs, (u1 - u0) / 2)
    return curve(u0, u1, zs, h["shape"])


# ------------------------------------------------------------------ wall infill (the corners around the opening) on one face
def infill(face, X, h, v, mat, toward_v):
    u0, u1, z1 = h["u0"], h["u1"], h["z1"]
    tw = X((u0 + u1) / 2, toward_v, (h["z0"] + z1) / 2)
    if h["shape"] == "rose":
        uc, zc, r = (u0 + u1) / 2, h["zs"], (u1 - u0) / 2
        n = 16
        c = [(uc + r * math.cos(2 * math.pi * k / n), zc + r * math.sin(2 * math.pi * k / n)) for k in range(n + 1)]
        for k in range(n):
            a0, a1 = 2 * math.pi * k / n, 2 * math.pi * (k + 1) / n
            s = []
            for a in (a0, a1):
                m = max(abs(math.cos(a)), abs(math.sin(a)))
                s.append((uc + r * math.cos(a) / m, zc + r * math.sin(a) / m))
            quad = _dedupe([c[k], c[k + 1], s[1], s[0]])        # 22.5 degree steps: a corner is always a segment boundary
            _oriented(face, mat, [X(u, v, z) for u, z in quad], tw)
        return
    cv = curve(u0, u1, h["zs"], h["shape"])
    for k in range(len(cv) - 1):
        quad = _dedupe([cv[k], cv[k + 1], (cv[k + 1][0], z1), (cv[k][0], z1)])
        _oriented(face, mat, [X(u, v, z) for u, z in quad], tw)


# ------------------------------------------------------------------ reveals
def reveals(face, X, h, t, mat="mat_plaster"):
    """Jambs (rect part), curved soffit, and the sill is left to the caller."""
    u0, u1, za, zs = h["u0"], h["u1"], h["z0"], h["zs"]
    cen = X((u0 + u1) / 2, t / 2, (za + h["z1"]) / 2)
    if h["shape"] == "rose":
        cv = circle((u0 + u1) / 2, zs, (u1 - u0) / 2)
        for k in range(len(cv)):
            a, b = cv[k], cv[(k + 1) % len(cv)]
            _oriented(face, mat, [X(a[0], 0, a[1]), X(b[0], 0, b[1]), X(b[0], t, b[1]), X(a[0], t, a[1])], cen)
        return
    if zs - za > 1e-6:
        _oriented(face, mat, [X(u0, 0, za), X(u0, t, za), X(u0, t, zs), X(u0, 0, zs)], cen)
        _oriented(face, mat, [X(u1, 0, za), X(u1, t, za), X(u1, t, zs), X(u1, 0, zs)], cen)
    cv = curve(u0, u1, zs, h["shape"])
    for k in range(len(cv) - 1):
        a, b = cv[k], cv[k + 1]
        _oriented(face, mat, [X(a[0], 0, a[1]), X(b[0], 0, b[1]), X(b[0], t, b[1]), X(a[0], t, a[1])], cen)


# ------------------------------------------------------------------ stone surround
def surround(face, box, X, h, tw, to, mat="mat_trim"):
    """Dressed jambs (rect part) and a ring of voussoirs; alternate stones stand proud (relief). `box(mat,u0,u1,v0,v1,za,zb,skip)` is the wall builder's."""
    u0, u1, za, zs = h["u0"], h["u1"], h["z0"], h["zs"]
    if h["shape"] == "rose":
        inn = circle((u0 + u1) / 2, zs, (u1 - u0) / 2)
        out = circle((u0 + u1) / 2, zs, (u1 - u0) / 2 + tw)
        closed = True
    else:
        if zs - za > 1e-6:
            box(mat, u0 - tw, u0, -to, 0, za, zs, ("v1", "z1"))
            box(mat, u1, u1 + tw, -to, 0, za, zs, ("v1", "z1"))
        inn = curve(u0, u1, zs, h["shape"])
        out = curve(u0, u1, zs, h["shape"], tw)
        closed = False
    n = len(inn) if closed else len(inn) - 1
    for k in range(n):
        j = (k + 1) % len(inn)
        d = to * (1.0 if k % 2 == 0 else 1.9)
        ia, ib, oa, ob = inn[k], inn[j], out[k], out[j]
        cen = X((ia[0] + ob[0]) / 2, -d / 2, (ia[1] + ob[1]) / 2)
        front = [X(ia[0], -d, ia[1]), X(ib[0], -d, ib[1]), X(ob[0], -d, ob[1]), X(oa[0], -d, oa[1])]
        _away(face, mat, front, cen)
        _away(face, mat, [X(ia[0], 0, ia[1]), X(ib[0], 0, ib[1]), X(ib[0], -d, ib[1]), X(ia[0], -d, ia[1])], cen)          # inner lip
        _away(face, mat, [X(oa[0], 0, oa[1]), X(ob[0], 0, ob[1]), X(ob[0], -d, ob[1]), X(oa[0], -d, oa[1])], cen)          # outer edge
        _away(face, mat, [X(ia[0], 0, ia[1]), X(oa[0], 0, oa[1]), X(oa[0], -d, oa[1]), X(ia[0], -d, ia[1])], cen)          # stone joint (start)
        _away(face, mat, [X(ib[0], 0, ib[1]), X(ob[0], 0, ob[1]), X(ob[0], -d, ob[1]), X(ib[0], -d, ib[1])], cen)          # stone joint (end)


# ------------------------------------------------------------------ glass
def glass(face, X, h, t, mat="mat_glass"):
    u0, u1, za, zs = h["u0"], h["u1"], h["z0"], h["zs"]
    if h["shape"] == "rose":
        poly = circle((u0 + u1) / 2, zs, (u1 - u0) / 2)
    else:
        poly = [(u0, za), (u1, za)] + list(reversed(curve(u0, u1, zs, h["shape"])))
    pts = [X(u, t / 2, z) for u, z in poly]
    face(mat, pts)
    face(mat, list(reversed(pts)))               # glass is seen from both sides


# ------------------------------------------------------------------ tracery bars (in the glass plane)
def _band(g, X, mat, a, b, hw, vm, th):
    """Flat bar from point a to b (u, z) of half width hw, thickness th about the plane v = vm, as a thin box (4 long faces + ends)."""
    dx, dz = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dz)
    if L < 1e-6:
        return
    nx, nz = -dz / L * hw, dx / L * hw
    p = [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz), (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)]
    front = [X(u, vm - th, z) for u, z in p]
    back = [X(u, vm + th, z) for u, z in p]
    cen = X((a[0] + b[0]) / 2, vm, (a[1] + b[1]) / 2)
    f = lambda m, pts: g.b.face(m, pts, wm.world_uv(pts, 3.0, g.off, g.zf))
    _away(f, mat, front, cen)
    _away(f, mat, back, cen)
    for k in range(4):
        _away(f, mat, [front[k], front[(k + 1) % 4], back[(k + 1) % 4], back[k]], cen)


def tracery(g, X, h, t, mat):
    """Simple window bars: a centre mullion, saddle bars, and for lancets an inner arch ring; for a rose, spokes and an inner ring."""
    u0, u1, za, zs, z1 = h["u0"], h["u1"], h["z0"], h["zs"], h["z1"]
    vm, th, hw = t / 2, 0.03, 0.035
    w = u1 - u0
    if h["shape"] == "rose":
        uc, r = (u0 + u1) / 2, w / 2
        for k in range(8):
            a = math.pi * k / 4 + math.pi / 8
            _band(g, X, mat, (uc + r * 0.32 * math.cos(a), zs + r * 0.32 * math.sin(a)), (uc + r * math.cos(a), zs + r * math.sin(a)), hw, vm, th)
        ring = circle(uc, zs, r * 0.32)
        for k in range(len(ring)):
            _band(g, X, mat, ring[k], ring[(k + 1) % len(ring)], hw, vm, th)
        return
    uc = (u0 + u1) / 2
    if w > 1.2 * FT:
        _band(g, X, mat, (uc, za), (uc, z1 - 0.02), hw, vm, th)                       # mullion up to the apex
    for zz in [za + (zs - za) * f for f in (0.33, 0.66)]:                             # saddle bars
        _band(g, X, mat, (u0, zz), (u1, zz), hw * 0.8, vm, th)
    if w > 1.4 * FT:
        ring = curve(u0 + 0.28 * w, u1 - 0.28 * w, zs, h["shape"])                    # inner arch ring (smaller arch on the same springing line)
        for k in range(len(ring) - 1):
            _band(g, X, mat, ring[k], ring[k + 1], hw * 0.8, vm, th)


# ------------------------------------------------------------------ door leaf outline
def leaf_outline(lw, lh, shape):
    """Outline (x, z) of a door leaf in leaf coordinates (origin at the hinge bottom): rectangle for the lower part and the arch on top."""
    if shape not in ("round_arch", "pointed"):
        return [(0, 0), (lw, 0), (lw, lh), (0, lh)]
    rise = min(rise_of(shape, lw), lh * 0.8)
    zs = lh - rise
    return [(0, 0), (lw, 0)] + _dedupe(list(reversed(curve(0.0, lw, zs, shape))))


# ------------------------------------------------------------------ window reshaping (post-pass over edge_holes)
def shape_holes(edge_holes, W, zf, has_layout=False, storey_ft=10.0):
    """Give every window of the style its arched shape. Windows only narrow inside the span they had (so interior partitions, which sit
    between the layout's windows, still clear them); a triple lancet widens up to 1.6x if the neighbouring holes leave room. Height grows upward from the sill."""
    shape = W.get("shape", "rect")
    if shape in (None, "rect"):
        return edge_holes
    out = []
    for holes in edge_holes:
        new = []
        for h in holes:
            if h["kind"] != "window":
                new.append(h)
                continue
            uc = (h["u0"] + h["u1"]) / 2
            w0 = h["u1"] - h["u0"]
            sw = (W.get("triple_width_ft", 4.8) if shape == "triple_lancet" else W.get("width_ft", 1.9)) * FT
            triple = shape == "triple_lancet"
            if triple:
                # widen toward the style width only into free wall
                others = [o for o in holes if o is not h]
                lo, hi = uc - sw / 2, uc + sw / 2
                for o in others:
                    if o["z0"] < h["z1"] and o["z1"] > h["z0"]:
                        if o["u1"] <= uc:
                            lo = max(lo, o["u1"] + 0.6 * FT)
                        elif o["u0"] >= uc:
                            hi = min(hi, o["u0"] - 0.6 * FT)
                lo, hi = min(lo, h["u0"]), max(hi, h["u1"])
                half = min(uc - lo, hi - uc)
                half = min(half, sw / 2, w0 * 0.8)
                width = 2 * half
            else:
                width = min(sw, w0)
            sill = h["z0"]
            if not has_layout and W.get("sill_ft") is not None:
                sill = zf + (round((h["z0"] - zf) / (storey_ft * FT) - 0.35) * storey_ft + W["sill_ft"]) * FT
            rel = ((sill - zf) / FT) % storey_ft
            top_rel = min(W.get("height_ft", 6.5), storey_ft - 0.9 - rel)
            hgt = max(top_rel, 3.0) * FT
            if triple and width >= 3.3 * FT:
                pier = 0.42 * FT
                lw = (width - 2 * pier) / 3
                u = uc - width / 2
                for k in range(3):
                    hh = dict(h)
                    hh.update(u0=u, u1=u + lw, z0=sill, z1=sill + (hgt if k == 1 else hgt * 0.82))
                    new.append(prep(hh, "pointed"))
                    u += lw + pier
                continue
            single = "pointed" if triple else shape
            if single == "rose":
                width = min(width, hgt)
                hh = dict(h)
                hh.update(u0=uc - width / 2, u1=uc + width / 2, z0=sill, z1=sill + width)
            else:
                hh = dict(h)
                hh.update(u0=uc - width / 2, u1=uc + width / 2, z0=sill, z1=sill + hgt)
            new.append(prep(hh, single))
        out.append(sorted(new, key=lambda h: (h["u0"], h["z0"])))
    return out


def shape_doors(edge_holes, D):
    shape = (D or {}).get("shape", "rect")
    if shape not in ("round_arch", "pointed"):
        return edge_holes
    for holes in edge_holes:
        for h in holes:
            if h["kind"] == "door":
                prep(h, shape)
    return edge_holes


# ------------------------------------------------------------------ rose window on a gable (blind: the gable wall behind it stays)
def gable_rose(g, R, S, zt, spec):
    """Round window on a gable: stone ring + glass disc + spokes, proud of the gable face. Placed on the end opposite a tower unless spec.end is given."""
    end = spec.get("end")
    if end is None:
        tw_ = S["special"].get("tower")
        end = -1 if (tw_ and tw_.get("end", 1) >= 0) else 1
    end = 1 if end >= 0 else -1
    r = min(spec.get("diameter_ft", 4.5) / 2 * FT, R.rise * 0.34)
    if r < 0.9 * FT:
        return
    zc = zt + R.rise * 0.45
    mat_s = S.get("trim_mat") or S["wall_mat"]
    ring = 0.5 * FT
    proud = 0.22 * FT
    f = lambda m, pts: g.b.face(m, pts, wm.world_uv(pts, 3.0, g.off, g.zf))

    def X(u, v, z):                     # u across the gable, v outward from the gable plane
        return R.P(end * (R.hl + v), end * u, z)
    n = 20
    inn = circle(0.0, zc, r, n)
    out = circle(0.0, zc, r + ring, n)
    cen = X(0, proud / 2, zc)
    for k in range(n):
        j = (k + 1) % n
        ia, ib, oa, ob = inn[k], inn[j], out[k], out[j]
        d = proud if k % 2 == 0 else proud * 1.6
        _away(f, mat_s, [X(ia[0], d, ia[1]), X(ib[0], d, ib[1]), X(ob[0], d, ob[1]), X(oa[0], d, oa[1])], X(0, -1, zc))
        _away(f, mat_s, [X(oa[0], 0.02, oa[1]), X(ob[0], 0.02, ob[1]), X(ob[0], d, ob[1]), X(oa[0], d, oa[1])], cen)
        _away(f, mat_s, [X(ia[0], 0.02, ia[1]), X(ib[0], 0.02, ib[1]), X(ib[0], d, ib[1]), X(ia[0], d, ia[1])], X(0, -5, zc))
    pts = [X(u, 0.04, z) for u, z in inn]
    f("mat_glass", pts)
    f("mat_glass", list(reversed(pts)))
    bm = S.get("bar_mat") or mat_s
    sp = 0.045 * FT * 1.0
    for k in range(8):
        a = math.pi * k / 4 + math.pi / 8
        a0 = (0.3 * r * math.cos(a), zc + 0.3 * r * math.sin(a))
        a1 = (r * math.cos(a), zc + r * math.sin(a))
        dx, dz = a1[0] - a0[0], a1[1] - a0[1]
        L = math.hypot(dx, dz)
        nx, nz = -dz / L * 0.035, dx / L * 0.035
        quad = [(a0[0] + nx, a0[1] + nz), (a1[0] + nx, a1[1] + nz), (a1[0] - nx, a1[1] - nz), (a0[0] - nx, a0[1] - nz)]
        _oriented(f, bm, [X(u, 0.08, z) for u, z in quad], X(0, 5, zc))
        _oriented(f, bm, [X(u, 0.08 - 0.001, z) for u, z in quad][::-1], X(0, -5, zc))
    hub = circle(0.0, zc, 0.3 * r, 12)
    for k in range(len(hub)):
        a, b = hub[k], hub[(k + 1) % len(hub)]
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dz)
        nx, nz = -dz / L * 0.035, dx / L * 0.035
        quad = [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz), (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)]
        _oriented(f, bm, [X(u, 0.08, z) for u, z in quad], X(0, 5, zc))
        _oriented(f, bm, [X(u, 0.08, z) for u, z in quad][::-1], X(0, -5, zc))
