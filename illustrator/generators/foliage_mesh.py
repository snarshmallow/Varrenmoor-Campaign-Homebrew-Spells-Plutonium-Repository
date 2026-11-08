"""Procedural low-poly foliage meshes + the shared texture atlas (pure numpy/PIL, no Blender).

  lib = FoliageLibrary()                       # species from illustrator/presets/foliage/*.json
  m = lib.mesh("birch", variant=0, lod=0)      # worldpack_mesh.Mesh in metres, z up, origin at the trunk base; subs 'bark' / 'leaf'
  lib.tris("birch", 1)                         # triangle count of an LOD
  write_atlas(path, season="summer")           # textures/fol_atlas.png (2048x1536: painted alpha-cut leaf sprays, bark, rock, impostors)

v2 (crossed-card crowns): trunk + limb skeleton (tapered bark tubes) carrying clusters of alpha-cut leaf-spray cards (2 per cluster, in the outer
part of the crown so sky and branches show through), spherical per-vertex normals and COLOR_0 (baked AO + per-cluster tint).

LOD 0 = full (blobs, tiers, leaf cards), LOD 1 = fewer rings/tiers/blobs, LOD 2 = two crossed billboard quads with a baked impostor tile
(ground cover has no LOD 2: it is dropped at that distance). Every tile lives in ONE atlas so a merged chunk is one material (one draw call).
UVs are unit (0..1 inside a tile, never repeating), so an atlas works here, unlike the pack's tiling ground textures.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack_mesh as wm  # noqa: E402
import foliage_tex as ft  # noqa: E402

FT = 0.3048
PRESETS = os.path.abspath(os.path.join(HERE, "..", "presets", "foliage"))
IMPORTED = os.path.join(PRESETS, "imported")
ATLAS_MAT = "fol_atlas"
COLS, ROWS, TILE_PX = 8, 6, 256
TILES = ["bark", "bark_birch", "bark_dark", "core", "rock", "needle", "needle_dark", "juniper",
         "leaf_oak", "leaf_birch", "leaf_beech", "leaf_willow", "leaf_rowan", "leaf_maple", "bush", "ivy",
         "grass", "reed", "fern", "flower", "imp_conifer", "imp_broad", "twig", "unused23",
         "bw_leaf_a", "bw_leaf_b", "bw_leaf_c", "bw_leaf_d", "bw_bark_beech", "bw_bark_ash", "bw_bush", "unused31",
         "bw_leaf_ash_a", "bw_leaf_ash_b", "bw_leaf_ash_c", "bw_leaf_ash_d"] + [f"free{i}" for i in range(36, 48)]
# tiles bigger than one slot: name -> (col, row, cols, rows); used by tile_uv (imported Baileywiki textures are resized into 2x2 slots)
TILE_RECT = {"bw_leaf_a": (0, 3, 2, 2), "bw_leaf_ash_a": (2, 3, 2, 2)}
ALPHA_TILES = {"grass", "reed", "fern", "flower", "imp_conifer", "imp_broad", "needle", "needle_dark", "juniper", "leaf_oak", "leaf_birch", "leaf_beech",
               "leaf_willow", "leaf_rowan", "leaf_maple", "bush", "ivy", "twig", "bw_leaf_a", "bw_leaf_ash_a"}
LOD_SUGGESTED_M = [0, 60, 160]


def tile_uv(tile, u, v):
    """Atlas UV of (u, v) inside `tile`; v is top-down like glTF (v=0 top of the tile image). A 1.5 px gutter stops mip bleeding."""
    if tile in TILE_RECT:
        c, r, wc, hc = TILE_RECT[tile]
    else:
        i = TILES.index(tile)
        c, r, wc, hc = i % COLS, i // COLS, 1, 1
    pu, pv = 1.5 / (COLS * TILE_PX), 1.5 / (ROWS * TILE_PX)
    return (c / COLS + pu + u * (wc / COLS - 2 * pu), r / ROWS + pv + v * (hc / ROWS - 2 * pv))


# ------------------------------------------------------------------ atlas
IMPORT_TEXTURES = {"bw_leaf_a": "beech_leaf_D.png", "bw_bark_beech": "beech_bark_A.png", "bw_leaf_ash_a": "ash_canopy_A.png", "bw_bark_ash": "ash_bark_A.png",
                   "bw_bush": "bush_A.png"}


def write_atlas(path, seed=11, season="summer"):
    """Paint the shared atlas (foliage_tex.py). season: summer | autumn | winter (leaf colour / bare twigs)."""
    from PIL import Image
    rng = np.random.default_rng(seed)
    S = TILE_PX
    atlas = Image.new("RGBA", (COLS * S, ROWS * S), (0, 0, 0, 0))
    sp = lambda n: ft.paint_leaf_spray(S, rng, n, season)
    paint = {
        "bark": lambda: ft.paint_bark(S, rng, "bark"), "bark_birch": lambda: ft.paint_bark(S, rng, "bark_birch"), "bark_dark": lambda: ft.paint_bark(S, rng, "bark_dark"),
        "core": lambda: ft.paint_bark(S, rng, "core"), "rock": lambda: ft.paint_rock(S, rng),
        "needle": lambda: ft.paint_pine(S, rng, season), "needle_dark": lambda: ft.paint_spruce(S, rng, season, True),
        "juniper": lambda: ft.paint_spruce(S, rng, season, False, True),
        "leaf_oak": lambda: sp("leaf_oak"), "leaf_birch": lambda: sp("leaf_birch"), "leaf_beech": lambda: sp("leaf_beech"),
        "leaf_willow": lambda: ft.paint_willow(S, rng, season), "leaf_rowan": lambda: sp("leaf_rowan"), "leaf_maple": lambda: sp("leaf_maple"),
        "bush": lambda: sp("bush"), "ivy": lambda: sp("ivy"),
        "grass": lambda: ft.paint_grass(S, rng, season), "reed": lambda: ft.paint_grass(S, rng, season, True), "fern": lambda: ft.paint_fern(S, rng, season),
        "flower": lambda: ft.paint_flower(S, rng, season), "imp_conifer": lambda: ft.paint_imp_conifer(S, rng, season),
        "imp_broad": lambda: ft.paint_imp_broad(S, rng, season), "twig": lambda: ft.paint_twig(S, rng),
    }
    for name, fn in paint.items():
        i = TILES.index(name)
        atlas.paste(Image.fromarray(fn(), "RGBA"), ((i % COLS) * S, (i // COLS) * S))
    # imported third-party textures (Baileywiki), resized into their slots when the converted files exist
    for name, fn in IMPORT_TEXTURES.items():
        p = os.path.join(IMPORTED, fn)
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGBA")
        if name in TILE_RECT:
            c, r, wc, hc = TILE_RECT[name]
        else:
            i = TILES.index(name)
            c, r, wc, hc = i % COLS, i // COLS, 1, 1
        im = im.resize((wc * S, hc * S), Image.LANCZOS)
        atlas.paste(im, (c * S, r * S))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    atlas.save(path, optimize=True)
    return path


def atlas_material():
    return {ATLAS_MAT: {"id": ATLAS_MAT, "mean_color": "#5c7a46", "texture": f"textures/{ATLAS_MAT}.png", "roughness": 0.9, "metallic": 0.0, "uv": "unit"}}


def patch_glb_alpha_mask(path, cutoff=0.5, names=(ATLAS_MAT,)):
    """write_glb knows only BLEND: rewrite the JSON chunk so the atlas material is alpha-cut (MASK, no sorting problems, cheap)."""
    import struct
    raw = open(path, "rb").read()
    jl = struct.unpack_from("<I", raw, 12)[0]
    g = json.loads(raw[20:20 + jl])
    for m in g.get("materials", []):
        if m.get("name") in names:
            m["alphaMode"], m["alphaCutoff"], m["doubleSided"] = "MASK", cutoff, True
            m["extras"] = {"foliage": True}
    js = json.dumps(g, separators=(",", ":"), sort_keys=True).encode()
    js += b" " * (-len(js) % 4)
    rest = raw[20 + jl:]
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + len(rest)))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(rest)


# ------------------------------------------------------------------ mesh builder with normals + vertex colour
class _B:
    def __init__(self):
        self.V, self.UV, self.N, self.C, self.subs = [], [], [], [], {}

    def vert(self, p, uv, n=None, c=(1, 1, 1)):
        self.V.append(tuple(float(x) for x in p))
        self.UV.append(uv)
        self.N.append(None if n is None else tuple(float(x) for x in n))
        self.C.append((float(c[0]), float(c[1]), float(c[2]), 1.0))
        return len(self.V) - 1

    def tri(self, sub, a, b, c):
        self.subs.setdefault(sub, []).append((a, b, c))

    def quad(self, sub, a, b, c, d):
        self.tri(sub, a, b, c)
        self.tri(sub, a, c, d)

    def build(self):
        V = np.array(self.V, float).reshape(-1, 3)
        N = np.zeros_like(V)
        have = np.array([n is not None for n in self.N], bool)
        if have.any():
            N[have] = np.array([n for n in self.N if n is not None])
        if (~have).any() and self.subs:                       # smooth normals for primitives built without explicit ones (rocks, logs)
            F = np.concatenate([np.asarray(f, np.int64) for f in self.subs.values()])
            sn = wm._smooth_normals(V, F)
            N[~have] = sn[~have]
        ln = np.linalg.norm(N, axis=1, keepdims=True)
        ln[ln == 0] = 1
        return wm.Mesh(V, np.array(self.UV, float).reshape(-1, 2), self.subs, True, N / ln, np.array(self.C, float).reshape(-1, 4))


def _norm(v):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / n if n > 1e-9 else np.array([0.0, 0.0, 1.0])


def _frame(d):
    ref = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.95 else np.array([1.0, 0.0, 0.0])
    u = _norm(np.cross(d, ref))
    return u, np.cross(d, u)


def _tube(b, sub, tile, pts, radii, n, colfn=None, wob=None):
    """Tapered tube through `pts` with per-point radii; bark UV: u around (n+1 verts, no seam), v along (1 at the start .. 0 at the end)."""
    pts = [np.asarray(p, float) for p in pts]
    rings = []
    tot = sum(np.linalg.norm(pts[i + 1] - pts[i]) for i in range(len(pts) - 1)) or 1.0
    acc = 0.0
    for i, p in enumerate(pts):
        t = _norm(pts[min(i + 1, len(pts) - 1)] - pts[max(i - 1, 0)])
        u, v = _frame(t)
        if i:
            acc += np.linalg.norm(pts[i] - pts[i - 1])
        vv = 1.0 - acc / tot
        ring = []
        for k in range(n + 1):
            a = 2 * math.pi * k / n
            rr = radii[i] * (1.0 + (wob[k % n] if wob is not None and i == 0 else 0.0))
            dirv = math.cos(a) * u + math.sin(a) * v
            q = p + dirv * rr
            c = colfn(q) if colfn else (1, 1, 1)
            ring.append(b.vert(q, tile_uv(tile, k / n, max(0.0, min(1.0, vv))), dirv, c))
        rings.append(ring)
    for i in range(len(rings) - 1):
        for k in range(n):
            b.quad(sub, rings[i][k], rings[i][k + 1], rings[i + 1][k + 1], rings[i + 1][k])
    return rings


def _card(b, tile, base, d, hint, w, L, droop=0.0, segs=2, colfn=None, nfn=None, flip=False, sub="leaf"):
    """Alpha-cut spray card: base-centre at `base`, grows along unit `d` for length L, width w, bending down by `droop` (fraction of L) at the tip.
    The texture's bottom edge sits at the base unless `flip` (willow strands hang from the tile top)."""
    d = _norm(d)
    s = np.cross(d, hint)
    s = _norm(s) if np.linalg.norm(s) > 1e-6 else _frame(d)[0]
    rows = []
    for j in range(segs + 1):
        t = j / segs
        c = np.asarray(base, float) + d * (L * t) + np.array([0, 0, -droop * L * t * t])
        ids = []
        for sg, u in ((-1, 0.0), (1, 1.0)):
            q = c + s * (sg * w / 2)
            fn = nfn(q, d, s, t) if nfn else _norm(np.cross(s, d))
            col = colfn(q, t) if colfn else (1, 1, 1)
            ids.append(b.vert(q, tile_uv(tile, u, (t if flip else 1 - t)), fn, col))
        rows.append(ids)
    for j in range(segs):
        b.quad(sub, rows[j][0], rows[j][1], rows[j + 1][1], rows[j + 1][0])


def _ring(b, cx, cy, z, r, n, tile, v=0.5, rot=0.0):
    out = []
    for k in range(n):
        a = rot + 2 * math.pi * k / n
        out.append(b.vert((cx + r * math.cos(a), cy + r * math.sin(a), z), tile_uv(tile, k / n, v)))
    return out


def _cyl(b, sub, tile, x, y, z0, z1, r0, r1, n, cap=False):
    a = _ring(b, x, y, z0, r0, n, tile, 1.0)
    c = _ring(b, x, y, z1, r1, n, tile, 0.0)
    for k in range(n):
        j = (k + 1) % n
        b.tri(sub, a[k], a[j], c[j])
        b.tri(sub, a[k], c[j], c[k])
    if cap:
        t = b.vert((x, y, z1), tile_uv(tile, 0.5, 0.0))
        for k in range(n):
            b.tri(sub, c[k], c[(k + 1) % n], t)


def _blob(b, sub, tile, c, rx, ry, rz, rings, seg, rng, jit=0.12, rot=0.0, col=(1, 1, 1)):
    """Low-poly ellipsoid: rings-1 latitude rings + two pole fans, jittered; explicit outward normals."""
    cx, cy, cz = c
    top = b.vert((cx, cy, cz + rz * (1 + rng.uniform(-jit, jit) * 0.5)), tile_uv(tile, 0.5, 0.0), (0, 0, 1), col)
    bot = b.vert((cx, cy, cz - rz * 0.8), tile_uv(tile, 0.5, 1.0), (0, 0, -1), col)
    rs = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        z = cz + rz * math.cos(phi)
        r = math.sin(phi)
        ring = []
        for k in range(seg):
            a = rot + 2 * math.pi * k / seg
            j = 1 + rng.uniform(-jit, jit)
            ring.append(b.vert((cx + rx * r * j * math.cos(a), cy + ry * r * j * math.sin(a), z), tile_uv(tile, k / seg, i / rings),
                               (r * math.cos(a) / max(rx, 1e-3), r * math.sin(a) / max(ry, 1e-3), math.cos(phi) / max(rz, 1e-3)), col))
        rs.append(ring)
    for k in range(seg):
        n = (k + 1) % seg
        b.tri(sub, top, rs[0][k], rs[0][n])
        for i in range(len(rs) - 1):
            b.quad(sub, rs[i][k], rs[i + 1][k], rs[i + 1][n], rs[i][n])
        b.tri(sub, bot, rs[-1][n], rs[-1][k])


def _leaf_tile(sp):
    """Atlas tile of the species' leaf spray (presets name it via tiles.leaf)."""
    t = sp["tiles"]["leaf"]
    return t if t in TILES else "leaf_oak"


def _tint(rng, warm=0.07, val=0.12):
    v = rng.uniform(1 - val, 1 + val * 0.6)
    t = rng.uniform(-warm, warm)
    return (v * (1 + t), v, v * (1 - 1.3 * t))


class _Crown:
    """Shading helpers for an ellipsoidal crown: outward (spherical) normals blended with up, AO darker inside and low."""

    def __init__(self, c, rx, rz, zb, zt, tint=(1, 1, 1), ao_min=0.5):
        self.c, self.rx, self.rz, self.zb, self.zt, self.tint, self.ao_min = np.asarray(c, float), rx, rz, zb, zt, tint, ao_min

    def rho(self, p):
        q = (np.asarray(p) - self.c) / np.array([self.rx, self.rx, self.rz])
        return float(np.linalg.norm(q))

    def col(self, p, t=0.0):
        rho = min(1.0, self.rho(p))
        hz = max(0.0, min(1.0, (p[2] - self.zb) / max(self.zt - self.zb, 1e-3)))
        ao = (self.ao_min + (1 - self.ao_min) * rho ** 0.85) * (0.8 + 0.2 * hz)
        return (ao * self.tint[0], ao * self.tint[1], ao * self.tint[2])

    def nrm(self, p, d=None, s=None, t=0.0):
        return _norm((np.asarray(p) - self.c) / np.array([self.rx, self.rx, self.rz]) + np.array([0, 0, 0.25]))


def _clusters_on_shell(rng, c, rx, rz, n, rho_lo, rho_hi, zmin=-0.3):
    out = []
    for _ in range(n):
        u = rng.uniform(zmin, 1.0)
        phi = rng.uniform(0, 2 * math.pi)
        s = math.sqrt(max(0.0, 1 - u * u))
        rho = rng.uniform(rho_lo, rho_hi)
        d = np.array([s * math.cos(phi), s * math.sin(phi), u])
        out.append((np.asarray(c) + d * np.array([rx, rx, rz]) * rho, d))
    return out


def _trunk(b, bt, rng, h_clear, tr, lean, n, flare=1.7, roots=5, lod=0):
    """Tapered, gently curving trunk with a root flare and buttress roots; returns the top point."""
    ang = rng.uniform(0, 2 * math.pi)
    zs = [0.0, 0.3, h_clear * 0.3, h_clear * 0.65, h_clear]
    pts = []
    for z in zs:
        k = (z / max(h_clear, 1e-3)) ** 2 * lean
        pts.append((k * math.cos(ang) + 0.04 * math.sin(z * 1.7), k * math.sin(ang) + 0.04 * math.cos(z * 1.3), z))
    rad = [tr * flare, tr * (1 + (flare - 1) * 0.5), tr * 1.0, tr * 0.9, tr * 0.78]
    wob = [rng.uniform(-0.18, 0.18) for _ in range(n)]
    ao = lambda q: (0.55 + 0.45 * min(1.0, q[2] / max(h_clear, 1.0)),) * 3
    _tube(b, "bark", bt, pts, rad, n, colfn=ao, wob=wob)
    if roots and lod == 0:
        for i in range(roots):
            a = 2 * math.pi * i / roots + rng.uniform(-0.3, 0.3)
            L = tr * rng.uniform(2.0, 3.0)
            p0 = np.array([pts[0][0] + math.cos(a) * tr * 0.8, pts[0][1] + math.sin(a) * tr * 0.8, 0.8 * tr])
            p1 = p0 + np.array([math.cos(a) * L * 0.6, math.sin(a) * L * 0.6, -tr * 0.5])
            _tube(b, "bark", bt, [p0, p1], [tr * 0.42, tr * 0.12], 4, colfn=ao)
    return np.array(pts[-1])


def _build_broad(sp, g, rng, b, lod, h, r):
    lt, bt = _leaf_tile(sp), sp["tiles"]["bark"]
    habit = g.get("habit", "round")
    hi = lod == 0
    trunk_h = h * g.get("trunk", 0.4)
    tr = h * g.get("trunk_r", 0.02) + 0.05
    crown_bot = trunk_h * 0.92
    rz = (h - crown_bot) / 2
    if habit == "pine":
        crown_bot = h * 0.62
        rz = (h - crown_bot) / 2
    c = (0.0, 0.0, crown_bot + rz)
    top = _trunk(b, bt, rng, trunk_h, tr, g.get("lean", 0.5), 7 if hi else 5, lod=lod)
    crown = _Crown(c, r, rz, crown_bot, h, ao_min=g.get("ao", 0.5))
    nl = max(3, int(round(g.get("limbs", 6) * (1 if hi else 0.6))))
    sides = 5 if hi else 4
    anchors = []                                              # (point, outward dir, size factor)
    if habit == "pine":                                       # trunk continues to the top; short limbs only in the upper third
        _tube(b, "bark", bt, [top, top + np.array([0, 0, (h - trunk_h) * 0.5]), np.array([top[0] * 0.4, top[1] * 0.4, h * 0.985])],
              [tr * 0.75, tr * 0.5, tr * 0.08], 5 if hi else 4)
    for i in range(nl):
        az = i * 2.399963 + rng.uniform(-0.3, 0.3)
        if habit == "pine":
            z0 = trunk_h * rng.uniform(0.72, 1.0) + (h - trunk_h) * rng.uniform(0.0, 0.8) * i / nl
            el0, Lb, droop = rng.uniform(0.12, 0.5), r * rng.uniform(0.7, 1.2), 0.0
        elif habit == "weep":
            z0 = trunk_h * rng.uniform(0.85, 1.0) + rz * 0.5 * i / nl
            el0, Lb, droop = rng.uniform(0.7, 1.15), r * rng.uniform(0.6, 0.9), 0.8
        elif habit == "oval":
            z0 = trunk_h * rng.uniform(0.7, 1.0) + rz * 1.4 * i / nl
            el0, Lb, droop = rng.uniform(0.65, 1.1), r * rng.uniform(0.75, 1.0), 0.1
        else:
            z0 = trunk_h * rng.uniform(0.85, 1.0) + rz * 0.5 * i / nl
            el0, Lb, droop = rng.uniform(0.4, 0.95), max(r, rz * 0.8) * rng.uniform(0.85, 1.05), g.get("droop", 0.15)
        f = (min(z0, trunk_h) / max(trunk_h, 1e-3)) ** 2
        p0 = np.array([top[0] * f, top[1] * f, z0])
        d1 = np.array([math.cos(az) * math.cos(el0), math.sin(az) * math.cos(el0), math.sin(el0)])
        p1 = p0 + d1 * Lb * 0.5
        el1 = el0 * 0.55 - droop * 0.4
        az1 = az + rng.uniform(-0.35, 0.35)
        d2 = np.array([math.cos(az1) * math.cos(el1), math.sin(az1) * math.cos(el1), math.sin(el1)])
        p2 = p1 + d2 * Lb * 0.5
        ao = lambda q: (0.6 + 0.4 * min(1.0, float(np.linalg.norm(np.array(q[:2]))) / max(r, 1e-3)),) * 3
        _tube(b, "bark", bt, [p0, p1, p2], [tr * 0.46, tr * 0.28, tr * 0.08], sides, colfn=ao)
        anchors.append((p2, _norm(p2 - np.array(c)), 1.0))
        if hi or i % 2 == 0:
            for sgn in ((-1, 1) if hi else (1,)):
                azc = az + sgn * rng.uniform(0.7, 1.0)
                elc = el1 + rng.uniform(-0.1, 0.35)
                dc = np.array([math.cos(azc) * math.cos(elc), math.sin(azc) * math.cos(elc), math.sin(elc)])
                pc = p1 + dc * Lb * 0.42
                _tube(b, "bark", bt, [p1, pc], [tr * 0.2, tr * 0.05], 4 if hi else 3, colfn=ao)
                anchors.append((pc, _norm(pc - np.array(c)), 0.85))
    ncl = max(4, int(round(g.get("cards", 40) * (1 if hi else 0.55))))
    for p, d in _clusters_on_shell(rng, c, r, rz, ncl, g.get("rho_lo", 0.4), g.get("rho_hi", 0.85), zmin=-0.15 if habit != "pine" else 0.0):
        anchors.append((p, d, 1.0))
    Lc0 = g.get("card_len", 0.5) * r
    segs = 1
    for p, d, sz in anchors:
        crown.tint = _tint(rng)
        if habit == "weep":
            L = min(rz * rng.uniform(0.55, 1.0) * 1.6, h * 0.8)
            cf = lambda q, t: tuple(x * (0.75 + 0.35 * t) for x in crown.col(q))
            for k in range(2 if hi else 1):
                if k and rng.random() > 0.7:
                    continue
                a = rng.uniform(0, 6.28)
                _card(b, lt, p, np.array([d[0] * 0.15, d[1] * 0.15, -1.0]), np.array([math.cos(a), math.sin(a), 0]), Lc0 * 1.1, L * (1 - 0.2 * k),
                      segs=segs, colfn=cf, nfn=crown.nrm, flip=True)
            continue
        L = Lc0 * rng.uniform(0.8, 1.25) * sz
        if habit == "pine":
            for k in range(3):                                # star of three flat needle sprays
                a = rng.uniform(0, 6.28) + k * 2.09
                dd = _norm(np.array([math.cos(a), math.sin(a), rng.uniform(0.05, 0.35)]))
                _card(b, lt, p, dd, np.array([0, 0, 1.0]), L * 0.95, L, droop=0.25, segs=segs, colfn=lambda q, t: crown.col(q), nfn=crown.nrm)
            continue
        for k in range(2 if hi else 1):
            dd = _norm(d * 0.85 + np.array([0, 0, 0.3]) + np.array([rng.normal(0, 0.28), rng.normal(0, 0.28), rng.normal(0, 0.22)]))
            hint = _norm(np.array([rng.normal(), rng.normal(), rng.normal(0, 0.3)]))
            _card(b, lt, p, dd, hint, L * 0.95, L, droop=g.get("card_droop", 0.25) if p[2] < c[2] else 0.1, segs=segs, colfn=lambda q, t: crown.col(q), nfn=crown.nrm)


def _build_conifer(sp, g, rng, b, lod, h, r):
    lt, bt = _leaf_tile(sp), sp["tiles"]["bark"]
    hi = lod == 0
    tr = 0.011 * h + 0.05
    pts = [(0, 0, 0), (0, 0, h * 0.3), (0, 0, h * 0.7), (0, 0, h * 0.985)]
    ao = lambda q: (0.5 + 0.5 * q[2] / h,) * 3
    _tube(b, "bark", bt, pts, [tr * 1.7, tr * 1.0, tr * 0.55, tr * 0.04], 6 if hi else 4, colfn=ao)
    n = g.get("tiers", 7) if hi else max(3, g.get("tiers", 7) // 2)
    per = g.get("per", 7) if hi else 5
    crown = _Crown((0, 0, h * 0.55), r, h * 0.45, 0.1 * h, h, ao_min=0.45)
    segs = 1
    for i in range(n):
        t = i / max(n - 1, 1)
        z = h * (0.14 + 0.78 * t)
        R = r * (1.0 - 0.82 * t) + 0.25
        m = per if t < 0.8 else max(3, per - 2)
        for ring_i, (zdir, lenf, widf) in enumerate(((-0.1 + 0.3 * t, 1.0, 1.35), (-0.5, 0.78, 1.2))):
            if ring_i and not hi:
                continue
            off = rng.uniform(0, 6.28)
            for k in range(m):
                a = off + 2 * math.pi * k / m + rng.uniform(-0.2, 0.2)
                d = _norm(np.array([math.cos(a), math.sin(a), zdir]))
                Lb = R * lenf * rng.uniform(0.9, 1.2)
                crown.tint = _tint(rng, 0.04, 0.1)
                _card(b, lt, (0, 0, z + rng.uniform(-0.2, 0.2) - ring_i * h * 0.012), d, np.array([0, 0, 1.0]), Lb * widf, Lb, droop=0.35, segs=segs,
                      colfn=lambda q, tt: crown.col(q), nfn=crown.nrm)
    for k in range(2):                                        # leader tuft: two crossed vertical sprays
        a = 1.57 * k
        _card(b, lt, (0, 0, h * 0.84), np.array([0, 0, 1.0]), np.array([math.cos(a), math.sin(a), 0]), r * 0.5, h * 0.16, segs=1,
              colfn=lambda q, tt: crown.col(q), nfn=crown.nrm)
    if hi:                                                    # opaque core so the trunk zone does not look hollow
        rr = r * 0.22
        _blob(b, "bark", "core", (0, 0, h * 0.42), rr, rr, h * 0.3, 3, 6, rng, jit=0.1, col=(0.45, 0.5, 0.45))


def _build_shrub(sp, g, rng, b, lod, h, r, hedge=False):
    lt = _leaf_tile(sp)
    hi = lod == 0
    ln = g.get("long", 1.0)
    rx = max(r * 0.8, 0.05) * (ln if hedge else 1.0)
    ry = r * 0.8
    rz = h * 0.5
    crown = _Crown((0, 0, rz), rx, rz, 0.0, h, ao_min=0.55)
    _blob(b, "bark", "core", (0, 0, rz * 0.55), rx * 0.4, ry * 0.4, rz * 0.6, 4, 8 if hi else 6, rng, jit=0.1, col=(0.5, 0.56, 0.5))
    ncl = max(5, int(g.get("cards", 22) * (1 if hi else 0.55)))
    segs = 1
    for _ in range(ncl):
        u = rng.uniform(0.0, 0.9)
        phi = rng.uniform(0, 2 * math.pi)
        s = math.sqrt(1 - u * u)
        d = np.array([s * math.cos(phi), s * math.sin(phi), u])
        p = np.array([d[0] * rx * 0.25, d[1] * ry * 0.25, rz * (0.2 + 1.1 * d[2])])
        if hedge:
            p[0] = rng.uniform(-rx, rx) * 0.85
            d = _norm(np.array([0.0, d[1], d[2]]))
        crown.tint = _tint(rng, 0.08, 0.14)
        dd = _norm(d * np.array([1, 1, 0.8]) + np.array([0, 0, g.get("up", 0.35)]))
        L = r * g.get("card_len", 0.8) * rng.uniform(0.9, 1.3) + 0.05
        _card(b, lt, p, dd, _norm(np.array([rng.normal(), rng.normal(), rng.normal(0, 0.3)])), L * 1.15, L, droop=0.04, segs=segs,
              colfn=lambda q, t: crown.col(q), nfn=crown.nrm)


def _build_cards(sp, g, rng, b, lod, h):
    """Ground cover: tufts of fanned alpha cards from the base (grass, reeds, fern, flowers)."""
    lt = _leaf_tile(sp)
    nc = g.get("cards", 4) if lod == 0 else max(2, g.get("cards", 4) // 2)
    w = max(g.get("w", 0.6) * h * 0.9, 0.35)
    pitch0 = g.get("pitch", 0.15)
    for i in range(nc):
        a = math.pi * 2 * i / nc + rng.uniform(-0.3, 0.3)
        pitch = pitch0 * rng.uniform(0.7, 1.3)
        d = _norm(np.array([math.sin(pitch) * math.cos(a), math.sin(pitch) * math.sin(a), math.cos(pitch)]))
        tint = _tint(rng, 0.1, 0.12)
        _card(b, lt, (0.04 * math.cos(a), 0.04 * math.sin(a), 0), d, np.array([-math.sin(a), math.cos(a), 0]), w, h * rng.uniform(0.85, 1.0),
              droop=g.get("drooping", 0.25 if g.get("droop") else 0.0), segs=2 if lod == 0 else 1,
              colfn=lambda q, t, tint=tint: tuple((0.65 + 0.35 * t) * x for x in tint),
              nfn=lambda q, d_, s_, t: _norm(np.array([0, 0, 1.0]) + 0.3 * _norm(np.cross(s_, d_))))


# ------------------------------------------------------------------ species -> mesh
def build_species_mesh(sp, variant=0, lod=0):
    """Mesh of one species at its nominal height (mid of height_ft), LOD 0/1/2. Deterministic in (species, variant)."""
    import zlib
    rng = np.random.default_rng(zlib.crc32(f"{sp['id']}:{variant}".encode()))
    h = float(np.mean(sp["height_ft"])) * FT
    r = h * float(sp["crown_ratio"])
    g = dict(sp["gen"])
    b = _B()
    kind = g["type"]
    lt, bt = sp["tiles"]["leaf"], sp["tiles"]["bark"]
    if kind == "glb" and lod < 2:
        import foliage_import
        return foliage_import.load_imported(sp, lod)
    if lod >= 2:                                                       # impostor: two crossed billboards of the species silhouette
        if sp["kind"] in ("ground", "prop", "rock"):
            return wm.Mesh(np.zeros((0, 3)), np.zeros((0, 2)), {}, True)
        tile = "imp_conifer" if kind == "conifer" else "imp_broad"
        w = max(2 * r, 0.8) * (1.0 if tile == "imp_broad" else 1.1)
        for i in range(2):
            a = math.pi * i / 2
            ca, sa = math.cos(a), math.sin(a)
            ids = []
            for (x, u, v, z) in ((-w / 2, 1, 1, 0), (w / 2, 0, 1, 0), (w / 2, 0, 0, h), (-w / 2, 1, 0, h)):
                ids.append(b.vert((x * ca, x * sa, z), tile_uv(tile, 1 - u, v), (0, 0, 1), (0.9, 0.9, 0.9)))
            b.quad("leaf", *ids)
        return b.build()
    if kind == "conifer":
        _build_conifer(sp, g, rng, b, lod, h, r)
    elif kind in ("broad", "broadconifer", "willow"):
        if kind == "willow":
            g.setdefault("habit", "weep")
        if kind == "broadconifer":
            g.setdefault("habit", "pine")
        _build_broad(sp, g, rng, b, lod, h, r)
    elif kind == "shrub":
        _build_shrub(sp, g, rng, b, lod, h, r, hedge=sp["kind"] == "hedge")
    elif kind == "cards":
        _build_cards(sp, g, rng, b, lod, h)
    elif kind == "stump":
        _cyl(b, "bark", bt, 0, 0, 0, h, h * 0.28, h * 0.22, 7, cap=True)
    elif kind == "log":
        ln = sp.get("length_ft", 9) * FT
        rad = h * 0.4
        n = 6
        a = []
        for z_ in (-ln / 2, ln / 2):
            a.append([b.vert((z_, rad * math.cos(2 * math.pi * k / n), rad + rad * math.sin(2 * math.pi * k / n)), tile_uv(bt, k / n, 0.5)) for k in range(n)])
        for k in range(n):
            j = (k + 1) % n
            b.tri("bark", a[0][k], a[1][j], a[0][j])
            b.tri("bark", a[0][k], a[1][k], a[1][j])
        for end in (0, 1):
            c = b.vert((-ln / 2 if end == 0 else ln / 2, 0, rad), tile_uv(bt, 0.5, 0.5))
            for k in range(n):
                if end == 0:
                    b.tri("bark", c, a[end][k], a[end][(k + 1) % n])
                else:
                    b.tri("bark", c, a[end][(k + 1) % n], a[end][k])
    elif kind == "rock":
        _blob(b, "leaf", "rock", (0, 0, h * 0.35), h * 0.9, h * 0.75, h * 0.5, g.get("rings", 3), g.get("seg", 6), rng, jit=0.25)
    else:
        raise ValueError(f"unknown generator {kind}")
    return b.build()


class FoliageLibrary:
    def __init__(self, presets=PRESETS):
        self.species = {}
        self.mixes = {}
        for f in sorted(os.listdir(presets)):
            if not f.endswith(".json"):
                continue
            d = json.load(open(os.path.join(presets, f), encoding="utf-8"))
            for s in d.get("species", []):
                self.species[s["id"]] = s
            self.mixes.update(d.get("mixes", {}))
        self._cache = {}

    def imported_available(self, sid):
        """True when a species does not need third-party files or they are present (third_party/baileywiki may be removed before a public release)."""
        gen = (self.species.get(sid) or {}).get("gen") or {}
        if gen.get("type") != "glb":
            return True
        import foliage_import as fi
        return os.path.exists(os.path.join(fi.IMPORTED, gen["file"]))

    def climate_mix(self, climate, base=None, imported=True):
        """Species mix [(species, weight)] for a climate: the base mix (a mixes.json name or a list; default the climate's own mix) plus every species whose `biomes` lists
        the climate, weighted `mix_share` x the base total (hero models are heavy, so the shares are small). Imported (third-party) species are skipped when their files
        are missing or imported=False. Procedural-only libraries (no `biomes`) return the base mix unchanged."""
        from_name = {"temperate": "oak_beech_wood", "cold": "spruce_forest", "dry": "pine_heath", "coastal": "pine_heath"}
        b = base if base is not None else from_name.get(climate, "northern_mixed_forest")
        mix = [tuple(m) if isinstance(m, (list, tuple)) else (m["species"], m["weight"]) for m in (self.mixes[b] if isinstance(b, str) else b)]
        tot = sum(w for _, w in mix)
        have = {s for s, _ in mix}
        if imported:
            for sid, sp in self.species.items():
                if climate in (sp.get("biomes") or []) and sid not in have and self.imported_available(sid):
                    mix.append((sid, round(tot * float(sp.get("mix_share", 0.04)), 4)))
        return mix

    def get(self, sid):
        if sid not in self.species:
            raise KeyError(f"unknown foliage species {sid!r}")
        return self.species[sid]

    def mesh(self, sid, variant=0, lod=0):
        sp = self.get(sid)
        v = variant % max(1, int(sp.get("variants", 1)))
        k = (sid, v, lod)
        if k not in self._cache:
            self._cache[k] = build_species_mesh(sp, v, lod)
        return self._cache[k]

    def tris(self, sid, lod=0):
        return self.mesh(sid, 0, lod).tri_count

    def prims(self, sid, lod=0):
        return len(self.mesh(sid, 0, lod).subs)

    def nominal_h_ft(self, sid):
        return float(np.mean(self.get(sid)["height_ft"]))

    def crown_r_ft(self, sid):
        sp = self.get(sid)
        return self.nominal_h_ft(sid) * float(sp["crown_ratio"])


def instance_mesh(tmpl, scale, rot_deg, pos, zscale=1.0):
    """Template mesh -> placed copy (scale in xy, `zscale` multiplies the vertical scale, rotation about z, offset metres)."""
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    V = tmpl.V * np.array([scale, scale, scale * zscale])
    V = np.stack([V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c, V[:, 2]], 1) + np.asarray(pos, float)
    return V


def _rot_n(N, rot_deg):
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    return np.stack([N[:, 0] * c - N[:, 1] * s, N[:, 0] * s + N[:, 1] * c, N[:, 2]], 1)


def merge_instances(parts):
    """parts: [(template Mesh, scale, rot_deg, pos_m, zscale)] -> one Mesh with a single 'fol_atlas' sub (one primitive); normals + vertex colour kept."""
    Vs, UVs, Fs, Ns, Cs, off = [], [], [], [], [], 0
    for t, sc, rot, pos, zs in parts:
        if not t.V.size:
            continue
        Vs.append(instance_mesh(t, sc, rot, pos, zs))
        UVs.append(t.UV)
        Ns.append(_rot_n(t.N, rot) if t.N is not None else np.tile([0.0, 0.0, 1.0], (len(t.V), 1)))
        Cs.append(t.C if t.C is not None else np.ones((len(t.V), 4)))
        F = np.concatenate(list(t.subs.values())) if t.subs else np.zeros((0, 3), int)
        Fs.append(F + off)
        off += len(t.V)
    if not Vs:
        return wm.Mesh(np.zeros((0, 3)), np.zeros((0, 2)), {}, True)
    return wm.Mesh(np.concatenate(Vs), np.concatenate(UVs), {ATLAS_MAT: np.concatenate(Fs)}, True, np.concatenate(Ns), np.concatenate(Cs))


def sync_preset_tris(presets=PRESETS):
    """Write `tris` [lod0, lod1, lod2] and `prims` into each species of presets/foliage/*.json (the panel shows them without running python)."""
    lib = FoliageLibrary(presets)
    n = 0
    for f in sorted(os.listdir(presets)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(presets, f)
        d = json.load(open(p, encoding="utf-8"))
        if "species" not in d:
            continue
        for s in d["species"]:
            s["tris"] = [lib.tris(s["id"], l) for l in (0, 1, 2)]
            n += 1
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
            fh.write("\n")
    return n
