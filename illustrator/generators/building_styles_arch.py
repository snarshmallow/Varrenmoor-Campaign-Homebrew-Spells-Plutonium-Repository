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


# ------------------------------------------------------------------ rose window on a gable (a real opening: clip_rose cuts the gable, gable_rose adds ring, reveal, glass, tracery)
ROSE_N = 24
FOILS = {"trefoil": 3, "quatrefoil": 4}


def rose_outline(r, foil=None, n=ROSE_N):
    """Opening outline [(u, z)] relative to the centre, radius r. foil None = circle; "trefoil" / "quatrefoil" = k overlapping lobes (union of k circles of radius
    0.55 r centred 0.45 r out; star-shaped about the centre). A lobe points up (trefoil: up, lower left, lower right)."""
    k = FOILS.get(foil)
    if not k:
        return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    nn = max(n, 12 * k)
    a, d = 0.55 * r, 0.45 * r
    pts = []
    for i in range(nn):
        th = 2 * math.pi * i / nn
        best = 0.0
        for j in range(k):
            phi = math.pi / 2 + 2 * math.pi * j / k
            dl = th - phi
            s_ = d * math.sin(dl)
            if abs(s_) <= a:
                best = max(best, d * math.cos(dl) + math.sqrt(a * a - s_ * s_))
        pts.append((best * math.cos(th), best * math.sin(th)))
    return pts


def rose_params(R, S, zt, spec):
    """(end, r, zc, ring, outline) of the gable rose, or None when the gable is too small. Ring and opening fit inside the gable triangle."""
    end = spec.get("end")
    if end is None:
        tw_ = S["special"].get("tower")
        end = -1 if (tw_ and tw_.get("end", 1) >= 0) else 1
    end = 1 if end >= 0 else -1
    ring = 0.5 * FT
    zc = zt + R.rise * 0.45
    hw_at = R.hw * (1.0 - (zc - zt) / max(R.rise, 1e-9))
    d_slant = hw_at * R.rise / math.hypot(R.rise, R.hw)                       # distance from the centre to a slanted gable edge
    r = min(spec.get("diameter_ft", 4.5) / 2 * FT, R.rise * 0.34, d_slant - ring - 0.25 * FT, (zc - zt) - ring - 0.25 * FT)
    if r < 0.9 * FT:
        return None
    return end, r, zc, ring, rose_outline(r, spec.get("foil"))


def _inside_tri(P, pt):
    def sg(a, b, c):
        return (a[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (a[1] - c[1])
    d1, d2, d3 = sg(pt, P[0], P[1]), sg(pt, P[1], P[2]), sg(pt, P[2], P[0])
    return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))


def _ray_tri(o, d, P):
    """First intersection of the ray o + t d (t > 0) with the triangle boundary (o inside the triangle)."""
    best = None
    for k in range(3):
        a, b = P[k], P[(k + 1) % 3]
        e = (b[0] - a[0], b[1] - a[1])
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-12:
            continue
        t = ((a[0] - o[0]) * e[1] - (a[1] - o[1]) * e[0]) / den
        s_ = ((a[0] - o[0]) * d[1] - (a[1] - o[1]) * d[0]) / den
        if t > 1e-9 and -1e-9 <= s_ <= 1 + 1e-9 and (best is None or t < best):
            best = t
    return (o[0] + d[0] * best, o[1] + d[1] * best)


def clip_rose(mesh, R, S):
    """Cut the circular / foil opening out of the gable triangle (the single-skin roof builder makes a solid triangle): that triangle becomes the annulus between
    the opening and its outline, same winding, material and UV mapping. Every other triangle is untouched."""
    import numpy as np
    spec = (S.get("special") or {}).get("rose")
    if not spec:
        return mesh
    rp = rose_params(R, S, R.zt_, spec)
    if rp is None:
        return mesh
    end, r, zc, ring, hole = rp
    V = mesh.V
    L = (V[:, 0] - R.cxm) * R.ex[0] + (V[:, 1] - R.cym) * R.ex[1]
    W = (V[:, 0] - R.cxm) * R.ey[0] + (V[:, 1] - R.cym) * R.ey[1]
    target = None
    for mat, F in mesh.subs.items():
        for fi, f in enumerate(F):
            if np.all(np.abs(L[f] - end * R.hl) < 1e-4):
                P2 = np.stack([end * W[f], V[f, 2]], 1)                         # (u, z), u = end * w as in gable_rose's X()
                if _inside_tri(P2, (0.0, zc)) and (P2[:, 1].max() - P2[:, 1].min()) > 0.5 * R.rise:
                    target = (mat, fi, f, P2)
                    break
        if target:
            break
    if not target:
        return mesh
    mat, fi, f, P2 = target
    cen = (0.0, zc)
    hole_pts = [(u, zc + z) for u, z in hole]
    hole_ang = [math.atan2(z - zc, u) for u, z in hole_pts]
    outer = [(math.atan2(P2[k, 1] - zc, P2[k, 0]), (float(P2[k, 0]), float(P2[k, 1]))) for k in range(3)]
    for a in hole_ang:
        outer.append((a, _ray_tri(cen, (math.cos(a), math.sin(a)), P2)))
    seq = sorted([(a, "i", p) for a, p in zip(hole_ang, hole_pts)] + [(a, "o", p) for a, p in outer], key=lambda t: t[0])
    cur_i = max(k for k, t in enumerate(seq) if t[1] == "i")                   # close the loop: start from the last vertex of each ring
    cur_o = max(k for k, t in enumerate(seq) if t[1] == "o")
    tris = []
    for k, (a, kind, p) in enumerate(seq):
        if kind == "i":
            tris.append((seq[cur_i][2], p, seq[cur_o][2]))
            cur_i = k
        else:
            tris.append((seq[cur_o][2], seq[cur_i][2], p))
            cur_o = k

    def area2(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    orig_sign = 1.0 if area2(*P2) > 0 else -1.0
    uv0 = mesh.UV[f]
    Minv = np.linalg.inv(np.array([[P2[0, 0], P2[1, 0], P2[2, 0]], [P2[0, 1], P2[1, 1], P2[2, 1]], [1.0, 1.0, 1.0]]))
    newV, newUV, idx = [], [], []
    base = len(V)
    for (pa, pb, pc) in tris:
        ar = area2(pa, pb, pc)
        if abs(ar) < 1e-12:
            continue
        if ar * orig_sign < 0:
            pb, pc = pc, pb
        ids = []
        for (u, z) in (pa, pb, pc):
            bc = Minv @ np.array([u, z, 1.0])
            w_ = end * u
            newV.append((R.cxm + R.ex[0] * end * R.hl + R.ey[0] * w_, R.cym + R.ex[1] * end * R.hl + R.ey[1] * w_, z))
            newUV.append(tuple(bc @ uv0))
            ids.append(base + len(newV) - 1)
        idx.append(tuple(ids))
    if not idx:
        return mesh
    subs = {k: (np.delete(np.asarray(v), fi, axis=0) if k == mat else np.asarray(v)) for k, v in mesh.subs.items()}
    subs[mat] = np.concatenate([subs[mat], np.array(idx, dtype=subs[mat].dtype)])
    return wm.Mesh(np.concatenate([V, np.array(newV)]), np.concatenate([mesh.UV, np.array(newUV)]), subs, mesh.smooth)


def gable_rose(g, R, S, zt, spec):
    """Rose / trefoil / quatrefoil window on a gable, a real glazed opening (clip_rose cuts the gable triangle): stone ring with alternating proud voussoirs outside,
    a stone reveal through the wall, glass set in the reveal, spokes (circle) or bars into the lobes (foils). On the end opposite a tower unless spec.end.
    spec.foil: None | "trefoil" | "quatrefoil"."""
    rp = rose_params(R, S, zt, spec)
    if rp is None:
        return
    end, r, zc, ring, hole = rp
    foil = spec.get("foil") in FOILS
    mat_s = S.get("trim_mat") or S["wall_mat"]
    proud = 0.22 * FT
    depth = 0.45 * FT                                                        # wall thickness the reveal runs through
    gz = -0.14 * FT                                                          # glass plane, inside the reveal
    f = lambda m, pts: g.b.face(m, pts, wm.world_uv(pts, 3.0, g.off, g.zf))

    def X(u, v, z):                     # u across the gable, v outward from the gable plane
        return R.P(end * (R.hl + v), end * u, z)
    n = len(hole)
    inn = [(u, zc + z) for u, z in hole]
    out = []
    for u, z in inn:
        k_ = 1 + ring / max(math.hypot(u, z - zc), 1e-9)
        out.append((u * k_, zc + (z - zc) * k_))
    cen = X(0, proud / 2, zc)
    for k in range(n):
        j = (k + 1) % n
        ia, ib, oa, ob = inn[k], inn[j], out[k], out[j]
        d = proud if k % 2 == 0 else proud * 1.6
        _away(f, mat_s, [X(ia[0], d, ia[1]), X(ib[0], d, ib[1]), X(ob[0], d, ob[1]), X(oa[0], d, oa[1])], X(0, -1, zc))
        _away(f, mat_s, [X(oa[0], 0.02, oa[1]), X(ob[0], 0.02, ob[1]), X(ob[0], d, ob[1]), X(oa[0], d, oa[1])], cen)
        _oriented(f, mat_s, [X(ia[0], d, ia[1]), X(ib[0], d, ib[1]), X(ib[0], -depth, ib[1]), X(ia[0], -depth, ia[1])], X(0, 0.0, zc))   # reveal, facing the opening
    pts = [X(u, gz, z) for u, z in inn]
    f("mat_glass", pts)
    f("mat_glass", list(reversed(pts)))
    bm = S.get("bar_mat") or mat_s
    bv = gz + 0.045 * FT

    def bar(a0, a1, hw_=0.035):
        dx, dz = a1[0] - a0[0], a1[1] - a0[1]
        L = math.hypot(dx, dz)
        if L < 1e-9:
            return
        nx, nz = -dz / L * hw_, dx / L * hw_
        quad = [(a0[0] + nx, a0[1] + nz), (a1[0] + nx, a1[1] + nz), (a1[0] - nx, a1[1] - nz), (a0[0] - nx, a0[1] - nz)]
        _oriented(f, bm, [X(u, bv, z) for u, z in quad], X(0, 5, zc))
        _oriented(f, bm, [X(u, bv - 0.001, z) for u, z in quad][::-1], X(0, -5, zc))
    if foil:
        k = FOILS[spec["foil"]]
        for j in range(k):                                                   # a bar from the centre into every lobe
            phi = math.pi / 2 + 2 * math.pi * j / k
            bar((0.0, zc), (0.85 * r * math.cos(phi), zc + 0.85 * r * math.sin(phi)), 0.05)
    else:
        for k in range(8):
            a = math.pi * k / 4 + math.pi / 8
            bar((0.3 * r * math.cos(a), zc + 0.3 * r * math.sin(a)), (r * math.cos(a), zc + r * math.sin(a)))
        hub = circle(0.0, zc, 0.3 * r, 12)
        for k in range(len(hub)):
            bar(hub[k], hub[(k + 1) % len(hub)])


# ------------------------------------------------------------------ gatehouse carriage arch (a through passage, open at both ends)
def carriage_arch(edge_holes, P, special, zf):
    """Town gatehouse: on the two longest opposite walls of a four-sided footprint everything within the arch span is replaced by one wide round-arched opening
    (kind door, `carriage` True, no leaf) so a road can pass through; build_building_detailed adds the passage walls and barrel vault (carriage_tunnel).
    special = {"carriage_arch": {width_ft, height_ft}}. Returns {i, j, u0, u1, z0, zs, z1, depth} or None (not four-sided / too narrow)."""
    spec = (special or {}).get("carriage_arch")
    n = len(P)
    if not spec or n != 4:
        return None
    L = [math.dist(P[k], P[(k + 1) % n]) for k in range(n)]
    i = 0 if L[0] + L[2] >= L[1] + L[3] else 1
    j = i + 2
    w = min(spec.get("width_ft", 10.0) * FT, 0.6 * L[i])
    hgt = min(spec.get("height_ft", 12.0) * FT, 3.0 * w)
    if w < 6.0 * FT:
        return None
    info = None
    for k in (i, j):
        c = L[k] / 2.0
        u0, u1 = c - w / 2, c + w / 2
        keep = [h for h in edge_holes[k] if h["u1"] < u0 - 1.0 * FT or h["u0"] > u1 + 1.0 * FT]
        hole = {"u0": u0, "u1": u1, "z0": zf, "z1": zf + hgt, "kind": "door", "door": None, "carriage": True}
        prep(hole, "round_arch")
        edge_holes[k] = sorted(keep + [hole], key=lambda h: (h["u0"], h["z0"]))
        if k == i:
            info = {"i": i, "j": j, "u0": u0, "u1": u1, "z0": zf, "zs": hole["zs"], "z1": hole["z1"], "depth": L[(i + 1) % n]}
    return info


def carriage_tunnel(face, X, info, t, mat):
    """Passage side walls and barrel vault between the two carriage openings, in edge i's frame X(u, v, z) (v inward from the outside face). Faces look into the passage."""
    u0, u1, z0, zs = info["u0"], info["u1"], info["z0"], info["zs"]
    va, vb = t, info["depth"] - t
    if vb <= va:
        return
    mid = X((u0 + u1) / 2, (va + vb) / 2, (z0 + zs) / 2)
    face_ = lambda pts: _oriented(face, mat, pts, mid)
    for u in (u0, u1):                                                       # side walls up to the springing line
        face_([X(u, va, z0), X(u, vb, z0), X(u, vb, zs), X(u, va, zs)])
    cv = curve(u0, u1, zs, "round_arch")
    for a, b in zip(cv, cv[1:]):                                             # barrel vault
        face_([X(a[0], va, a[1]), X(a[0], vb, a[1]), X(b[0], vb, b[1]), X(b[0], va, b[1])])
