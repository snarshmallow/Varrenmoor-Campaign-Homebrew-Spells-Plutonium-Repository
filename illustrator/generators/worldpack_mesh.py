"""Pure-numpy mesh builders and glTF I/O for world packs (no bpy, no scipy, no PIL), shared by the Blender importer, the split exporter
and the merge/compress tool.

All meshes are built in the pack's Blender frame (metres, x east, y north, z up, z measured from the pack's z_origin_ft), see
WORLD_PACK.md. UVs are stored glTF style (v grows downward). A Part is one placeable thing:
  {id, layer, type, group, tags, mesh (absolute frame), pivot (x,y,z metres, absolute frame), members: [ids], instance: None | {template, scale, rot_deg}}
Pivot rule: horizontal centre of the mesh bounding box, at the mesh's lowest z. Localised meshes (mesh - pivot) are what GLBs hold.
"""
import json
import math
import os
import struct

import numpy as np

import worldpack as wp
import road_grade as wg

FT = wp.FT_M
LIFT = {"fields": 0.15, "plazas": 0.20, "roads": 0.25}      # metres above the terrain (no coplanar overlaps)
BRIDGE_THICK_M = 0.55
WALL_CAP_DROP_M = 0.02


# ------------------------------------------------------------------ mesh container
class Mesh:
    def __init__(self, V, UV, subs, smooth=False, N=None, C=None):
        # N: optional explicit per-vertex normals (z-up frame, foliage crowns use spherical normals); C: optional per-vertex RGBA 0..1 (COLOR_0, AO / tint)
        self.N = None if N is None else np.asarray(N, float).reshape(-1, 3)
        self.C = None if C is None else np.asarray(C, float).reshape(-1, 4)
        self.V = np.asarray(V, float).reshape(-1, 3)
        self.UV = np.asarray(UV, float).reshape(-1, 2)
        self.subs = {k: np.asarray(v, np.int64).reshape(-1, 3) for k, v in subs.items() if len(v)}
        self.smooth = smooth

    @property
    def tri_count(self):
        return int(sum(len(f) for f in self.subs.values()))

    def bbox(self):
        return self.V.min(0), self.V.max(0)

    def translated(self, d):
        return Mesh(self.V + np.asarray(d, float), self.UV, self.subs, self.smooth, self.N, self.C)

    def transformed(self, scale=1.0, rot_deg=0.0, offset=(0, 0, 0)):
        c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
        V = self.V * scale
        V = np.stack([V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c, V[:, 2]], 1)
        N = None
        if self.N is not None:
            N = np.stack([self.N[:, 0] * c - self.N[:, 1] * s, self.N[:, 0] * s + self.N[:, 1] * c, self.N[:, 2]], 1)
        return Mesh(V + np.asarray(offset, float), self.UV, self.subs, self.smooth, N, self.C)


def merge_meshes(meshes):
    V, UV, subs, off, smooth = [], [], {}, 0, True
    for m in meshes:
        V.append(m.V)
        UV.append(m.UV)
        for k, f in m.subs.items():
            subs.setdefault(k, []).append(f + off)
        off += len(m.V)
        smooth = smooth and m.smooth
    if not V:
        return Mesh(np.zeros((0, 3)), np.zeros((0, 2)), {})
    return Mesh(np.concatenate(V), np.concatenate(UV), {k: np.concatenate(v) for k, v in subs.items()}, smooth)


class Builder:
    def __init__(self, smooth=False):
        self.V, self.UV, self.subs, self.smooth = [], [], {}, smooth

    def vert(self, p, uv):
        self.V.append(p)
        self.UV.append(uv)
        return len(self.V) - 1

    def tri(self, mat, a, b, c):
        self.subs.setdefault(mat, []).append((a, b, c))

    def quad(self, mat, a, b, c, d):
        self.tri(mat, a, b, c)
        self.tri(mat, a, c, d)

    def face(self, mat, pts, uvs):
        """One flat polygon (convex fan), vertices unshared."""
        ids = [self.vert(p, u) for p, u in zip(pts, uvs)]
        for i in range(1, len(ids) - 1):
            self.tri(mat, ids[0], ids[i], ids[i + 1])

    def build(self):
        return Mesh(np.array(self.V).reshape(-1, 3), np.array(self.UV).reshape(-1, 2), self.subs, self.smooth)


def earclip(pts):
    """Triangulate a simple polygon given as [(x, y)...] (any winding). Returns CCW triangles as index triples."""
    n = len(pts)
    if n < 3:
        return []
    idx = list(range(n))
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0:
        idx.reverse()
    cross = lambda a, b, c: (pts[b][0] - pts[a][0]) * (pts[c][1] - pts[a][1]) - (pts[b][1] - pts[a][1]) * (pts[c][0] - pts[a][0])

    def inside(p, a, b, c):
        return cross(a, b, p) >= -1e-12 and cross(b, c, p) >= -1e-12 and cross(c, a, p) >= -1e-12
    out, guard = [], 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            a, b, c = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            if cross(a, b, c) <= 1e-12:
                continue
            if any(inside(p, a, b, c) for p in idx if p not in (a, b, c)):
                continue
            out.append((a, b, c))
            del idx[k]
            break
        else:
            out.append((idx[0], idx[1], idx[2]))     # degenerate polygon: drop a vertex to terminate
            del idx[1]
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def subdivide(P, T, max_edge):
    """1-to-4 split triangles until every edge <= max_edge (units of P). P list of (x,y); returns (P, T)."""
    P = [tuple(p) for p in P]
    cache = {}

    def mid(a, b):
        k = (min(a, b), max(a, b))
        if k not in cache:
            P.append(((P[a][0] + P[b][0]) / 2, (P[a][1] + P[b][1]) / 2))
            cache[k] = len(P) - 1
        return cache[k]
    work = list(T)
    done = []
    while work:
        a, b, c = work.pop()
        e = max(math.dist(P[a], P[b]), math.dist(P[b], P[c]), math.dist(P[c], P[a]))
        if e <= max_edge:
            done.append((a, b, c))
            continue
        ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
        work += [(a, ab, ca), (ab, b, bc), (ca, bc, c), (ab, bc, ca)]
    return P, done


# ------------------------------------------------------------------ builders (absolute Blender frame)
class Ctx:
    """Shared state for the builders: the pack, the terrain used for draping (possibly conformed/carved) and conversions."""

    def __init__(self, pack, heights=None):
        self.pack = pack
        self.fr = pack.frame
        self.h = pack.heights if heights is None else heights

    def B(self, x, y, z=None):
        return self.fr.to_blender(x, y, z)

    def ground_m(self, x_ft, y_ft):
        return (wp.bilinear(self.h, self.pack.cell_ft, x_ft, y_ft) - self.fr.z_origin_ft) * FT


def uv_offset(key):
    """Stable per-entity texture offset (in repeats) so neighbouring houses do not show the same board at the same place."""
    import hashlib
    d = hashlib.md5(str(key).encode()).digest()
    return (d[0] / 255.0, d[1] / 255.0)


def world_uv(pts, tile_ft, off=(0.0, 0.0), v0_m=0.0):
    """UVs for one planar polygon (Blender frame, metres) at constant texel density: one image repeat = tile_ft feet on every face.
    Orientation: u runs along the horizontal direction of the face (course direction: planks, shingle rows, stone courses), v runs DOWN the
    face's steepest slope (image row 0 = up-slope), so thatch strands and board-and-batten follow the slope and gable triangles are upright.
    Near-horizontal faces use plan (x, -y). v0_m shifts walls so a texture's rails sit on the floor line (z of the floor)."""
    P = np.asarray(pts, float)
    n = np.zeros(3)
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        n += np.array([(a[1] - b[1]) * (a[2] + b[2]), (a[2] - b[2]) * (a[0] + b[0]), (a[0] - b[0]) * (a[1] + b[1])])
    ln = np.linalg.norm(n)
    n = n / ln if ln > 1e-12 else np.array([0, 0, 1.0])
    t = float(tile_ft) * FT
    if abs(n[2]) > 0.95:
        u, s = np.array([1.0, 0, 0]), np.array([0, -1.0, 0])
        v0 = 0.0
    else:
        u = np.cross([0, 0, 1.0], n)
        u /= np.linalg.norm(u)
        s = np.cross(n, u)
        if s[2] < 0:
            s = -s
        v0 = v0_m
    return [((float(p @ u)) / t + off[0], -(float(p @ s) - v0) / t + off[1]) for p in P]


def uv_ft(x_ft, y_ft, tile_ft):
    t = float(tile_ft or 10.0)
    return (x_ft / t, y_ft / t)


def build_terrain(cx, step=1):
    pk, h, fr = cx.pack, cx.h, cx.fr
    ny, nx = h.shape
    cell = pk.cell_ft
    ii = np.unique(np.append(np.arange(0, ny, step), ny - 1))
    jj = np.unique(np.append(np.arange(0, nx, step), nx - 1))
    X, Y = np.meshgrid(jj * cell, ii * cell)
    Z = h[np.ix_(ii, jj)].astype(float)
    V = np.stack([X * FT, (fr.height_ft - Y) * FT, (Z - fr.z_origin_ft) * FT], -1).reshape(-1, 3)
    UV = np.stack([X / fr.width_ft, Y / fr.height_ft], -1).reshape(-1, 2)
    ni, nj = len(ii), len(jj)
    a = (np.arange(ni - 1)[:, None] * nj + np.arange(nj - 1)[None, :]).reshape(-1)
    b, c, d = a + 1, a + nj, a + nj + 1
    # a=(i,j) b=(i,j+1) c=(i+1,j) (south of a): in the y-up Blender frame a->b is east, a->c is south, so (a,c,b) is counter-clockwise
    tri = np.concatenate([np.stack([a, c, b], 1), np.stack([b, c, d], 1)])
    return Mesh(V, UV, {"mat_terrain_albedo": tri}, smooth=True)


def _ribbon(b, mat, pts, widths_m, zs, tile_ft, lift=0.0, thick=0.0, miter=2.0, zls=None, zrs=None, skirt=None):
    """pts: [(x_m, y_m)] centreline in the Blender frame; zs metres. Optional deck thickness (sides + underside).
    zls / zrs: per-side surface heights (road grading: the ribbon tilts across to follow the ground). skirt: {ground(x_m, y_m) -> z_m, ...} adds a flared apron
    from each edge down to the ground so a road standing above the terrain has no gap under it (road_grade.py)."""
    n = len(pts)
    P = np.array(pts, float)
    d = np.diff(P, axis=0)
    ln = np.linalg.norm(d, axis=1)
    ln[ln == 0] = 1e-9
    t = d / ln[:, None]
    tv = np.zeros((n, 2))
    tv[0], tv[-1] = t[0], t[-1]
    for i in range(1, n - 1):
        m = t[i - 1] + t[i]
        nm = np.linalg.norm(m)
        tv[i] = m / nm if nm > 1e-9 else t[i]
    nrm = np.stack([-tv[:, 1], tv[:, 0]], 1)
    cosk = np.ones(n)
    for i in range(1, n - 1):
        cosk[i] = max(np.dot(tv[i], t[i]), 1.0 / miter)
    hw = np.asarray(widths_m, float) / 2 / cosk
    L = P + nrm * hw[:, None]
    R = P - nrm * hw[:, None]
    cum = np.concatenate([[0], np.cumsum(ln)]) / FT
    Li, Ri = [], []
    for i in range(n):
        zl_ = (zls[i] if zls is not None else zs[i]) + lift
        zr_ = (zrs[i] if zrs is not None else zs[i]) + lift
        wv = widths_m[i] / FT
        Li.append(b.vert((L[i, 0], L[i, 1], zl_), (wv / float(tile_ft or 10), cum[i] / float(tile_ft or 10))))
        Ri.append(b.vert((R[i, 0], R[i, 1], zr_), (0.0, cum[i] / float(tile_ft or 10))))
    for i in range(n - 1):
        b.quad(mat, Ri[i], Ri[i + 1], Li[i + 1], Li[i])
    if skirt:
        tl = float(tile_ft or 10)
        for side, S, ids, zz in ((1, L, Li, zls if zls is not None else zs), (-1, R, Ri, zrs if zrs is not None else zs)):
            O = []
            for i in range(n):
                ze = zz[i] + lift
                ge = skirt["ground"](S[i, 0], S[i, 1])
                drop = max(ze - ge, 0.0)
                off = min(0.7 * drop + 0.12, 1.8)                         # flares outward as the road stands higher (m), capped
                ox, oy = S[i, 0] + side * nrm[i, 0] * off, S[i, 1] + side * nrm[i, 1] * off
                go = skirt["ground"](ox, oy)
                zo = min(go - skirt.get("sink_m", 0.1), ze - 0.02)
                O.append(b.vert((ox, oy, zo), (0.0, cum[i] / tl)))
            for i in range(n - 1):
                if side == 1:
                    b.quad(mat, ids[i], ids[i + 1], O[i + 1], O[i])       # outward + down on the left of travel
                else:
                    b.quad(mat, ids[i + 1], ids[i], O[i], O[i + 1])
    if thick:
        for i in range(n - 1):
            for side, S in ((1, L), (-1, R)):
                z0, z1 = zs[i] + lift, zs[i + 1] + lift
                a0 = b.vert((S[i, 0], S[i, 1], z0), (cum[i] / float(tile_ft), 0))
                a1 = b.vert((S[i + 1, 0], S[i + 1, 1], z1), (cum[i + 1] / float(tile_ft), 0))
                a2 = b.vert((S[i + 1, 0], S[i + 1, 1], z1 - thick), (cum[i + 1] / float(tile_ft), thick / FT / float(tile_ft)))
                a3 = b.vert((S[i, 0], S[i, 1], z0 - thick), (cum[i] / float(tile_ft), thick / FT / float(tile_ft)))
                if side == 1:
                    b.quad(mat, a1, a0, a3, a2)      # outward = left of travel
                else:
                    b.quad(mat, a0, a1, a2, a3)
            bl0 = b.vert((L[i, 0], L[i, 1], zs[i] + lift - thick), (0, 0))
            bl1 = b.vert((L[i + 1, 0], L[i + 1, 1], zs[i + 1] + lift - thick), (0, 1))
            br0 = b.vert((R[i, 0], R[i, 1], zs[i] + lift - thick), (1, 0))
            br1 = b.vert((R[i + 1, 0], R[i + 1, 1], zs[i + 1] + lift - thick), (1, 1))
            b.quad(mat, br0, bl0, bl1, br1)          # underside faces down


def build_road(cx, e):
    b = Builder()
    pts = [cx.B(p[0], p[1]) for p in e["points"]]
    zs = [(p[2] - cx.fr.z_origin_ft) * FT for p in e["points"]]
    br = bool(e.get("bridge"))
    if e.get("_grade"):                                                # ROAD GRADING (road_grade.py): dense draped runs, per-side heights, optional skirt
        sk = None
        if e["_grade"].get("skirt"):
            fr = cx.fr
            sk = {"ground": lambda xm, ym: (wg.mesh_height(cx.h, cx.pack.cell_ft, np.asarray(xm) / FT, fr.height_ft - np.asarray(ym) / FT) - fr.z_origin_ft) * FT}
        for run in e["_grade"]["runs"]:
            z0 = cx.fr.z_origin_ft
            _ribbon(b, e["surface"]["material"], [cx.B(x, y) for x, y in zip(run.x, run.y)], [e["width_ft"] * FT] * len(run.x), [(v - z0) * FT for v in run.z],
                    e["surface"]["tile_ft"], 0.0, 0.0, 2.0, [(v - z0) * FT for v in run.zl], [(v - z0) * FT for v in run.zr], sk)
        if e.get("kerbs"):
            _add_kerbs(cx, b, e)
        return b.build()
    if e.get("gaps"):                                                  # BRIDGES: the ribbon is removed under a modelled bridge (bridge_maker.py), ends stay on the road bed
        import bridge_maker as _bm
        for run in _bm.trim_runs(e["points"], e["gaps"]):
            if len(run) < 2:
                continue
            _ribbon(b, e["surface"]["material"], [cx.B(p[0], p[1]) for p in run], [e["width_ft"] * FT] * len(run), [(p[2] - cx.fr.z_origin_ft) * FT for p in run],
                    e["surface"]["tile_ft"], LIFT["roads"], 0.0)
        return b.build()
    _ribbon(b, e["surface"]["material"], pts, [e["width_ft"] * FT] * len(pts), zs, e["surface"]["tile_ft"], 0.0 if br else LIFT["roads"],
            BRIDGE_THICK_M if br else 0.0)
    if e.get("kerbs"):
        _add_kerbs(cx, b, e)
    return b.build()


KERB_H_FT = 0.5


def _add_kerbs(cx, b, e):
    """Raised stone kerb bands (e['kerbs'] rings in feet): top at road surface + 0.5 ft, vertical sides, heights follow the road centreline profile."""
    cl = np.array([[p[0], p[1]] for p in e["points"]], float)
    zc = np.array([p[2] for p in e["points"]], float)
    seg = np.diff(cl, axis=0)
    sl2 = np.maximum((seg ** 2).sum(1), 1e-9)

    def zroad(x, y):
        t = np.clip(((x - cl[:-1, 0]) * seg[:, 0] + (y - cl[:-1, 1]) * seg[:, 1]) / sl2, 0, 1)
        d = np.hypot(cl[:-1, 0] + t * seg[:, 0] - x, cl[:-1, 1] + t * seg[:, 1] - y)
        i = int(np.argmin(d))
        return zc[i] + t[i] * (zc[i + 1] - zc[i])
    mat, tile = "mat_kerb", 4.0
    for ring in e["kerbs"]:
        P = [tuple(p) for p in ring]
        # densify long edges so the kerb follows the road profile
        D = []
        for i, p in enumerate(P):
            q = P[(i + 1) % len(P)]
            n = max(1, int(math.dist(p, q) / 6.0))
            D += [(p[0] + (q[0] - p[0]) * k / n, p[1] + (q[1] - p[1]) * k / n) for k in range(n)]
        Bp = [(x, cx.fr.height_ft - y) for x, y in D]
        zb = [(zroad(x, y) - cx.fr.z_origin_ft) * FT + LIFT["roads"] for x, y in D]
        top = [b.vert((x * FT, yb * FT, z + KERB_H_FT * FT), (x / tile, yb / tile)) for (x, yb), z in zip(Bp, zb)]
        for t in earclip(Bp):
            b.tri(mat, *[top[i] for i in t])
        for i in range(len(D)):
            j = (i + 1) % len(D)
            a0 = b.vert((Bp[i][0] * FT, Bp[i][1] * FT, zb[i] + 0.002), (0, 0))
            a1 = b.vert((Bp[j][0] * FT, Bp[j][1] * FT, zb[j] + 0.002), (1, 0))
            b.quad(mat, a0, a1, top[j], top[i])


def build_water(cx, e):
    b = Builder()
    mat, tile = e["surface"]["material"], e["surface"]["tile_ft"]
    if e.get("centerline"):
        pts = [cx.B(p[0], p[1]) for p in e["centerline"]]
        zs = [(z - cx.fr.z_origin_ft) * FT for z in e["surface_elevations_ft"]]
        _ribbon(b, mat, pts, [w * FT for w in e["widths_ft"]], zs, tile, 0.0)
    else:
        P = [cx.B(*p[:2]) for p in e["polygon"]]
        z = (e["level_ft"] - cx.fr.z_origin_ft) * FT
        for t in earclip(P):
            ids = [b.vert((P[i][0], P[i][1], z), (P[i][0] / FT / tile, -P[i][1] / FT / tile)) for i in t]
            b.tri(mat, *ids)
    return b.build()


def build_drape(cx, e, lift, max_edge_ft=25.0):
    """A textured polygon laid on the terrain (plazas, fields): triangulated, subdivided, heights sampled from the terrain + lift."""
    b = Builder(smooth=False)
    mat, tile = e["surface"]["material"], e["surface"]["tile_ft"]
    P = [tuple(p[:2]) for p in e["polygon"]]
    # triangulate in the Blender frame (y flipped) so earclip's CCW output is up-facing there
    Bp = [(x, cx.fr.height_ft - y) for x, y in P]
    T = earclip(Bp)
    Q, T = subdivide(Bp, T, max_edge_ft)
    ids = []
    for (x, yb) in Q:
        y = cx.fr.height_ft - yb
        ids.append(b.vert((x * FT, yb * FT, cx.ground_m(x, y) + lift), (x / tile, y / tile)))
    for t in T:
        b.tri(mat, *[ids[i] for i in t])
    return b.build()


def build_building(cx, e):
    import worldpack_pbr as pbr
    b = Builder()
    z0 = (e["base_elevation_ft"] - e["skirt_depth_ft"] - cx.fr.z_origin_ft) * FT
    zf = (e["base_elevation_ft"] - cx.fr.z_origin_ft) * FT
    zt = zf + e["wall_height_ft"] * FT
    P = [cx.B(p[0], p[1]) for p in e["polygon"]]
    area2 = sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P)))
    if area2 < 0:
        P.reverse()
    wm_, wt = e["wall"]["surface"]["material"], pbr.tile_ft(e["wall"]["surface"]["material"], e["wall"]["surface"].get("tile_ft") or 8)
    off = uv_offset(e["id"])

    def F(mat, pts, tile, v0=0.0):
        b.face(mat, pts, world_uv(pts, tile, off, v0))
    for i in range(len(P)):
        p, q = P[i], P[(i + 1) % len(P)]
        F(wm_, [(p[0], p[1], z0), (q[0], q[1], z0), (q[0], q[1], zt), (p[0], p[1], zt)], wt, zf)
    cap = [b.vert((p[0], p[1], zt - WALL_CAP_DROP_M), (p[0] / FT / wt, -p[1] / FT / wt)) for p in P]
    for t in earclip(P):
        b.tri(wm_, *[cap[i] for i in t])
    # roof on the oriented bounding box
    o = e["obb"]
    cxm, cym = cx.B(o["center"][0], o["center"][1])
    ang = math.radians(o["angle_deg"])
    ex = (math.cos(ang), -math.sin(ang))          # long axis in the Blender frame (y flipped)
    ey = (-ex[1], ex[0])
    r = e["roof"]
    ov = r.get("overhang_ft", 1.0) * FT
    Lh, Wh = o["length_ft"] * FT / 2 + ov, o["width_ft"] * FT / 2 + ov
    rise = r["ridge_height_ft"] * FT
    ze = zt - ov * (rise / max(o["width_ft"] * FT / 2, 1e-6))
    zr = zt + rise
    rm, rt = r["surface"]["material"], (r["surface"].get("tile_ft") or 14) * pbr.ROOF_TEXEL_SCALE

    def Pt(l, w, z):
        return (cxm + ex[0] * l + ey[0] * w, cym + ex[1] * l + ey[1] * w, z)

    def R(mat, tile, *lwz):
        F(mat, [Pt(*a) for a in lwz], tile)
    if r["type"] == "hip":
        rh = max(Lh - Wh, 0.0)
        R(rm, rt, (-Lh, -Wh, ze), (Lh, -Wh, ze), (rh, 0, zr), (-rh, 0, zr))
        R(rm, rt, (Lh, Wh, ze), (-Lh, Wh, ze), (-rh, 0, zr), (rh, 0, zr))
        R(rm, rt, (Lh, -Wh, ze), (Lh, Wh, ze), (rh, 0, zr))
        R(rm, rt, (-Lh, Wh, ze), (-Lh, -Wh, ze), (-rh, 0, zr))
    else:
        R(rm, rt, (-Lh, -Wh, ze), (Lh, -Wh, ze), (Lh, 0, zr), (-Lh, 0, zr))
        R(rm, rt, (Lh, Wh, ze), (-Lh, Wh, ze), (-Lh, 0, zr), (Lh, 0, zr))
        hl, hw_ = o["length_ft"] * FT / 2, o["width_ft"] * FT / 2
        for g in ([(hl, -hw_, zt), (hl, hw_, zt), (hl, 0, zr)], [(-hl, hw_, zt), (-hl, -hw_, zt), (-hl, 0, zr)]):   # gable triangles: wall material, level courses, apex up
            F(wm_, [Pt(*a) for a in g], wt, zf)
    return b.build()


def build_fence(cx, e):
    b = Builder()
    P = [cx.B(p[0], p[1]) for p in e["points"]]
    Z = [(p[2] - cx.fr.z_origin_ft) * FT for p in e["points"]]
    if e.get("closed"):
        P, Z = P + [P[0]], Z + [Z[0]]
    hgt = e["height_ft"] * FT
    cum = 0.0
    for i in range(len(P) - 1):
        L = math.dist(P[i], P[i + 1]) / FT
        v0 = b.vert((P[i][0], P[i][1], Z[i]), (cum / 8, hgt / FT / 8))
        v1 = b.vert((P[i + 1][0], P[i + 1][1], Z[i + 1]), ((cum + L) / 8, hgt / FT / 8))
        v2 = b.vert((P[i + 1][0], P[i + 1][1], Z[i + 1] + hgt), ((cum + L) / 8, 0))
        v3 = b.vert((P[i][0], P[i][1], Z[i] + hgt), (cum / 8, 0))
        b.quad("mat_plank", v0, v1, v2, v3)
        b.quad("mat_plank", v1, v0, v3, v2)              # visible from both sides
        cum += L
    return b.build()


def tree_template(height_m=7.0):
    """A low-poly conifer-ish proxy at the origin: 6-sided trunk + 8-sided crown (about 28 triangles)."""
    b = Builder()
    s = height_m / 7.0
    def ring(r, z, n, mat):
        return [b.vert((r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), z), (k / n, z)) for k in range(n)]
    r0, r1 = ring(0.16 * s, 0.0, 6, "mat_tree_bark"), ring(0.16 * s, 2.0 * s, 6, "mat_tree_bark")
    for k in range(6):
        b.quad("mat_tree_bark", r0[k], r0[(k + 1) % 6], r1[(k + 1) % 6], r1[k])
    c0 = ring(1.7 * s, 1.6 * s, 8, "mat_tree_leaf")
    top = b.vert((0, 0, height_m), (0.5, 1))
    for k in range(8):
        b.tri("mat_tree_leaf", c0[k], c0[(k + 1) % 8], top)
    ctr = b.vert((0, 0, 1.6 * s), (0.5, 0))
    for k in range(8):
        b.tri("mat_tree_leaf", c0[(k + 1) % 8], c0[k], ctr)
    return b.build()


# ------------------------------------------------------------------ parts
def _pivot(mesh):
    lo, hi = mesh.bbox()
    return ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])


LAST_ROAD_GRADE = {}      # report of the last build_parts road grading (params, stats, warnings, cut/fill), read by worldpack_split


def build_parts(pack, step=1, carve=True, conform=True, layers=None, drape_edge_ft=40.0, road_grade=True):
    """All meshable entities of a pack as Parts (see module doc), in a stable order. layers: optional set of layer names to keep."""
    import worldpack_pbr as pbr
    pbr.prepare(pack.materials)
    h = pack.heights
    if carve:
        h = wp.carved_heights(pack)
    runs = None
    LAST_ROAD_GRADE.clear()
    gp = wg.params(road_grade)
    if gp["enabled"] and conform and any(not r.get("bridge") for r in pack.list("roads")):
        # ROAD GRADING (road_grade.py): roads are draped on the terrain mesh with a lift, smoothed, grade-limited; the old centreline conform is replaced
        h, runs, rep = wg.grade_and_cutfill(pack, h, gp)
        LAST_ROAD_GRADE.update(rep)
    elif conform:
        if pack.list("bridges"):                                       # BRIDGES: terrain keeps its shape under the spans
            import bridge_maker as _bm
            h = _bm.conformed_heights(pack, h)
        else:
            h = wp.road_conformed_heights(pack, h)
    if any(b.get("layout") for b in pack.list("buildings")):          # interiors: level pads so the terrain stays below the floor plates
        import worldpack_interiors as wi
        h = wi.pad_buildings(pack, h)
    cx = Ctx(pack, h)
    want = lambda l: layers is None or l in layers
    parts = []

    def add(e, layer, mesh, **kw):
        t = e.get("tags") or {"layer": layer, "subtype": layer, "district": None, "ring": None, "group": layer, "id": e["id"]}
        parts.append({"id": e["id"], "layer": layer, "type": layer, "group": t["group"], "tags": t, "mesh": mesh, "pivot": _pivot(mesh) if mesh is not None else None,
                      "members": [e["id"]], "instance": None, "foundry": e.get("foundry", {}), "entity": e, **kw})
    if want("terrain"):
        tid = f"terrain_{pack.place}"
        t = {"layer": "terrain", "subtype": "terrain", "district": None, "ring": None, "group": "terrain", "id": tid}
        m = build_terrain(cx, step)
        parts.append({"id": tid, "layer": "terrain", "type": "terrain", "group": "terrain", "tags": t, "mesh": m, "pivot": _pivot(m), "members": [tid], "instance": None,
                      "foundry": {"pipelineId": f"world:{pack.place}:{tid}"}, "entity": {"id": tid, "name": "Terrain", "kind": "terrain", "tags": t}})
    for e in pack.list("water"):
        if want("water"):
            add(e, "water", build_water(cx, e))
    for e in pack.list("roads"):
        if want("roads"):
            if runs is not None and e["id"] in runs:
                e = dict(e, _grade={"runs": runs[e["id"]], "skirt": gp["skirt"]})
                if not e.get("gaps"):                                  # kerbs follow the graded centreline
                    r0 = runs[e["id"]][0]
                    e["points"] = [[float(a), float(b_), float(c) - gp["lift_m"] / FT] for a, b_, c in zip(r0.x, r0.y, r0.z)]   # _add_kerbs adds the road lift itself
            rm = build_road(cx, e)
            if e.get("gaps") and not rm.tri_count:                      # BRIDGES: the whole road is a bridge
                continue
            add(e, "roads", rm)
    if want("bridges") and pack.list("bridges"):                       # BRIDGES: modelled bridges (bridge_maker.py), one Part each
        import bridge_maker as _bm
        _bm.add_bridge_parts(pack, cx, parts, add)
    for e in pack.list("plazas"):
        if want("plazas"):
            add(e, "plazas", build_drape(cx, e, LIFT["plazas"], drape_edge_ft))
    for e in pack.list("fields"):
        if want("fields"):
            add(e, "fields", build_drape(cx, e, LIFT["fields"], drape_edge_ft))
    for e in pack.list("buildings"):
        if want("buildings"):
            import worldpack_pbr as pbr
            e = pbr.restyle_building(e)
            if e.get("style"):                                        # building style preset (building_styles.py); no style key = legacy look
                import building_styles as _bs
                e = _bs.apply_style(e)
                if e.get("_style"):
                    _bs.register_materials(pack.materials, e["_style"])
            if e.get("openings"):
                import worldpack_detail as wd
                m, dn = wd.build_building_detailed(cx, e)
                extra = {}
                if e.get("layout"):                                   # generated interior (interiors.py): storeys/roof/props as separate nodes
                    import worldpack_interiors as wi
                    m, dn, extra = wi.add_interior(cx, e, m, dn)
                add(e, "buildings", m, door_nodes=dn, **extra)
            else:
                add(e, "buildings", build_building(cx, e))
    for e in pack.list("fences"):
        if want("fences"):
            add(e, "fences", build_fence(cx, e))
    if want("foliage"):
        tmpl = {}
        for e in pack.list("foliage"):
            x, y, z = e["points"][0]
            hm = e["height_ft"] * FT
            key = (e["species"], round(hm / e["scale"], 3) if e["scale"] else hm)
            tm = tmpl.setdefault(e["species"], tree_template(7.0))
            px, py, pz = cx.B(x, y, z)
            parts.append({"id": e["id"], "layer": "foliage", "type": "foliage", "group": e["tags"]["group"], "tags": e["tags"], "mesh": None, "pivot": (px, py, pz),
                          "members": [e["id"]], "instance": {"template": e["species"], "mesh": tm, "scale": float(e["height_ft"] * FT / 7.0), "rot_deg": e["rotation_deg"]},
                          "foundry": e["foundry"], "entity": e})
    for e in pack.list("lights"):
        if want("lights") and e.get("position"):
            parts.append({"id": e["id"], "layer": "lights", "type": "lights", "group": "lights", "tags": e["tags"], "mesh": None,
                          "pivot": cx.B(*e["position"]), "members": [e["id"]], "instance": None, "foundry": e["foundry"], "entity": e})
    return parts


def part_mesh(part):
    """Absolute-frame mesh of a part (instances: the scaled, rotated template at the instance position)."""
    i = part["instance"]
    if i:
        return i["mesh"].transformed(i["scale"], i["rot_deg"], part["pivot"])
    return part["mesh"]


# ------------------------------------------------------------------ glTF writer / reader
def _smooth_normals(V, F):
    n = np.zeros_like(V)
    a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(n, F[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln


def write_glb(path, nodes, materials, textures="external", tex_root=None, extras=None, tex_prefix="textures/"):
    """nodes: [(name, Mesh, extras_dict)]; materials: {mat_id: record from materials.json}. Meshes are in the Blender frame (z up) and are
    written Y-up as (x, z, -y). textures: 'external' (uri relative to the GLB: textures/<mat>.png), 'embed' or 'none'.
    tex_root: folder holding <mat_id>.png (external) or the source images (embed); records carry 'texture' relative to the pack."""
    blobs, views, acc, gmats, gimgs, gtex, gnodes, gmeshes = [], [], [], [], [], [], [], []
    off = [0]

    def view(data, target=None):
        pad = (-off[0]) % 4
        if pad:
            blobs.append(b"\0" * pad)
            off[0] += pad
        v = {"buffer": 0, "byteOffset": off[0], "byteLength": len(data)}
        if target:
            v["target"] = target
        blobs.append(data)
        off[0] += len(data)
        views.append(v)
        return len(views) - 1

    def accessor(data, comp, typ, count, target, mm=None):
        a = {"bufferView": view(data, target), "componentType": comp, "count": int(count), "type": typ}
        if mm:
            a["min"], a["max"] = mm
        acc.append(a)
        return len(acc) - 1
    mat_index = {}

    def material(mid):
        if mid in mat_index:
            return mat_index[mid]
        r = materials.get(mid)
        if r is None:                                           # dynamic building-style materials (building_styles.py) need no entry in the pack
            import building_styles as _bs
            r = _bs.material_record(mid) if mid.startswith("mat_s_") else None
        r = r or {}
        col = r.get("mean_color") or "#a0a0a0"
        rgb = [int(col[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        g = {"name": mid, "doubleSided": True, "pbrMetallicRoughness": {"baseColorFactor": [*rgb, 1.0], "metallicFactor": float(r.get("metallic", 0.0)),
                                                                           "roughnessFactor": float(r.get("roughness", 0.9))}}
        if r.get("alpha") is not None:
            g["alphaMode"] = "BLEND"
            g["pbrMetallicRoughness"]["baseColorFactor"][3] = float(r["alpha"])
        tex = r.get("texture")
        if tex and textures != "none":
            src = os.path.join(tex_root or "", tex if textures == "embed" else f"{mid}.png") if tex_root is not None else None
            img = {"name": mid, "mimeType": "image/png"}
            if textures == "embed":
                if src and os.path.exists(src):
                    with open(src, "rb") as f:
                        img["bufferView"] = view(f.read())
                else:
                    img = None
            else:
                img["uri"] = f"{tex_prefix}{mid}.png"
            if img:
                gimgs.append(img)
                samp = 33071 if r.get("uv") == "unit" else 10497
                gtex.append({"source": len(gimgs) - 1, "sampler": 0 if samp == 10497 else 1})
                g["pbrMetallicRoughness"]["baseColorTexture"] = {"index": len(gtex) - 1}
                g["pbrMetallicRoughness"]["baseColorFactor"] = [1, 1, 1, 1]
                for key, suffix, field in (("normal", "_n", "normalTexture"), ("mr", "_mr", "metallicRoughnessTexture")):
                    if not r.get(key):
                        continue
                    im2 = {"name": mid + suffix, "mimeType": "image/png"}
                    if textures == "embed":
                        p2 = os.path.join(tex_root or "", f"{mid}{suffix}.png")
                        if not os.path.exists(p2):
                            continue
                        with open(p2, "rb") as f:
                            im2["bufferView"] = view(f.read())
                    else:
                        im2["uri"] = f"{tex_prefix}{mid}{suffix}.png"
                    gimgs.append(im2)
                    gtex.append({"source": len(gimgs) - 1, "sampler": 0})
                    if field == "normalTexture":
                        g["normalTexture"] = {"index": len(gtex) - 1, "scale": 1.0}
                    else:
                        g["pbrMetallicRoughness"]["metallicRoughnessTexture"] = {"index": len(gtex) - 1}
                        g["pbrMetallicRoughness"]["metallicFactor"] = 1.0
                        g["pbrMetallicRoughness"]["roughnessFactor"] = 1.0
        gmats.append(g)
        mat_index[mid] = len(gmats) - 1
        return mat_index[mid]
    for name, m, ex in nodes:
        V = np.stack([m.V[:, 0], m.V[:, 2], -m.V[:, 1]], 1).astype("<f4")
        prims = []
        pos_acc = accessor(V.tobytes(), 5126, "VEC3", len(V), 34962, ([V.min(0).tolist(), V.max(0).tolist()] if len(V) else None))
        uv_acc = accessor(m.UV.astype("<f4").tobytes(), 5126, "VEC2", len(m.UV), 34962)
        nrm_acc = None
        col_acc = None
        if getattr(m, "N", None) is not None and m.subs:
            N = np.stack([m.N[:, 0], m.N[:, 2], -m.N[:, 1]], 1).astype("<f4")
            nrm_acc = accessor(N.tobytes(), 5126, "VEC3", len(N), 34962)
        elif m.smooth and m.subs:
            allf = np.concatenate(list(m.subs.values()))
            N = _smooth_normals(m.V, allf)
            N = np.stack([N[:, 0], N[:, 2], -N[:, 1]], 1).astype("<f4")
            nrm_acc = accessor(N.tobytes(), 5126, "VEC3", len(N), 34962)
        if getattr(m, "C", None) is not None and m.subs:
            cb = np.clip(np.round(m.C * 255), 0, 255).astype("u1")
            col_acc = accessor(cb.tobytes(), 5121, "VEC4", len(cb), 34962)
            acc[col_acc]["normalized"] = True
        for mid in sorted(m.subs):
            F = m.subs[mid].astype("<u4")
            at = {"POSITION": pos_acc, "TEXCOORD_0": uv_acc}
            if nrm_acc is not None:
                at["NORMAL"] = nrm_acc
            if col_acc is not None:
                at["COLOR_0"] = col_acc
            prims.append({"attributes": at, "indices": accessor(F.reshape(-1).tobytes(), 5125, "SCALAR", F.size, 34963), "material": material(mid)})
        gmeshes.append({"name": name, "primitives": prims})
        ex = dict(ex or {})
        tr = ex.pop("_t", None)                                   # node translation in Blender axes (metres): door leaves sit on their hinge
        gn = {"name": name, "mesh": len(gmeshes) - 1, "extras": ex}
        if tr is not None:
            gn["translation"] = [float(tr[0]), float(tr[2]), -float(tr[1])]
        gnodes.append(gn)
    g = {"asset": {"version": "2.0", "generator": "varrenmoor worldpack_mesh.py", "extras": extras or {}}, "scene": 0, "scenes": [{"nodes": list(range(len(gnodes)))}],
         "nodes": gnodes, "meshes": gmeshes, "materials": gmats, "accessors": acc, "bufferViews": views, "buffers": [{"byteLength": off[0]}],
         "samplers": [{"wrapS": 10497, "wrapT": 10497, "magFilter": 9729, "minFilter": 9987}, {"wrapS": 33071, "wrapT": 33071, "magFilter": 9729, "minFilter": 9987}]}
    if gimgs:
        g["images"], g["textures"] = gimgs, gtex
    js = json.dumps(g, separators=(",", ":"), sort_keys=True).encode()
    js += b" " * (-len(js) % 4)
    bn = b"".join(blobs)
    bn += b"\0" * (-len(bn) % 4)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(bn)))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(bn), b"BIN\0") + bn)


def read_glb(path):
    """Read a GLB written by write_glb -> [(name, extras, Mesh)] in the Blender frame (z up), plus the material names used."""
    with open(path, "rb") as f:
        raw = f.read()
    jl = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20:20 + jl])
    bn = raw[20 + jl + 8:]
    comp = {5126: "<f4", 5125: "<u4", 5123: "<u2"}
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}

    def arr(i):
        a = g["accessors"][i]
        v = g["bufferViews"][a["bufferView"]]
        n = ncomp[a["type"]]
        return np.frombuffer(bn, comp[a["componentType"]], a["count"] * n, v.get("byteOffset", 0)).reshape(-1, n)
    out = []
    for nd in g["nodes"]:
        m = g["meshes"][nd["mesh"]]
        V = UV = None
        subs = {}
        smooth = False
        for p in m["primitives"]:
            P = arr(p["attributes"]["POSITION"]).astype(float)
            V = np.stack([P[:, 0], -P[:, 2], P[:, 1]], 1)
            UV = arr(p["attributes"]["TEXCOORD_0"]).astype(float)
            smooth = "NORMAL" in p["attributes"]
            subs[g["materials"][p["material"]]["name"]] = arr(p["indices"]).reshape(-1, 3).astype(np.int64)
        ex = dict(nd.get("extras", {}))
        if nd.get("translation"):                       # inverse of write_glb: glTF (x, y up, z south) -> Blender metres; "_t" is popped again by write_glb
            tx, ty, tz = nd["translation"]
            ex["_t"] = (tx, -tz, ty)
        out.append((nd["name"], ex, Mesh(V if V is not None else np.zeros((0, 3)), UV if UV is not None else np.zeros((0, 2)), subs, smooth)))
    return out, g


def cluster_decimate(mesh, cell_m):
    """Vertex-clustering decimation: snap vertices to a cell_m grid, merge them (mean position/UV), drop degenerate triangles."""
    if mesh.tri_count == 0 or cell_m <= 0:
        return mesh
    key = np.floor(mesh.V / cell_m).astype(np.int64)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    n = inv.max() + 1
    cnt = np.bincount(inv, minlength=n).astype(float)
    V = np.zeros((n, 3))
    UV = np.zeros((n, 2))
    for k in range(3):
        V[:, k] = np.bincount(inv, mesh.V[:, k], n) / cnt
    for k in range(2):
        UV[:, k] = np.bincount(inv, mesh.UV[:, k], n) / cnt
    subs = {}
    for mid, F in mesh.subs.items():
        G = inv[F]
        ok = (G[:, 0] != G[:, 1]) & (G[:, 1] != G[:, 2]) & (G[:, 0] != G[:, 2])
        G = G[ok]
        if len(G):
            subs[mid] = G
    return Mesh(V, UV, subs, mesh.smooth)
