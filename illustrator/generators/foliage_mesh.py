"""Procedural low-poly foliage meshes + the shared texture atlas (pure numpy/PIL, no Blender).

  lib = FoliageLibrary()                       # species from illustrator/presets/foliage/*.json
  m = lib.mesh("birch", variant=0, lod=0)      # worldpack_mesh.Mesh in metres, z up, origin at the trunk base; subs 'bark' / 'leaf'
  lib.tris("birch", 1)                         # triangle count of an LOD
  write_atlas(path)                            # textures/fol_atlas.png (opaque crown/bark tiles + alpha-cut cards)

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

FT = 0.3048
PRESETS = os.path.abspath(os.path.join(HERE, "..", "presets", "foliage"))
ATLAS_MAT = "fol_atlas"
COLS, ROWS, TILE_PX = 8, 4, 128
TILES = ["bark", "bark_birch", "needle", "needle_dark", "leaf_oak", "leaf_birch", "leaf_beech", "leaf_willow", "leaf_rowan", "juniper", "bush", "rock",
         "grass", "reed", "fern", "flower", "card_oak", "card_birch", "card_beech", "card_willow", "card_rowan", "imp_conifer", "imp_broad"]
ALPHA_TILES = {"grass", "reed", "fern", "flower", "imp_conifer", "imp_broad"} | {t for t in TILES if t.startswith("card_")}
LOD_SUGGESTED_M = [0, 60, 160]


def tile_uv(tile, u, v):
    """Atlas UV of (u, v) inside `tile`; v is top-down like glTF (v=0 top of the tile image). A 1.5 px gutter stops mip bleeding."""
    i = TILES.index(tile)
    c, r = i % COLS, i // COLS
    pu, pv = 1.5 / (COLS * TILE_PX), 1.5 / (ROWS * TILE_PX)
    return (c / COLS + pu + u * (1 / COLS - 2 * pu), r / ROWS + pv + v * (1 / ROWS - 2 * pv))


# ------------------------------------------------------------------ atlas
def _noise(rng, n, octaves=3):
    out = np.zeros((n, n))
    for o in range(octaves):
        k = 4 * 2 ** o
        g = rng.random((k, k))
        t = np.kron(g, np.ones((n // k + 1, n // k + 1)))[:n, :n]
        out += t / 2 ** o
    out -= out.min()
    return out / max(out.max(), 1e-9)


def write_atlas(path, seed=11):
    from PIL import Image, ImageDraw
    rng = np.random.default_rng(seed)
    atlas = Image.new("RGBA", (COLS * TILE_PX, ROWS * TILE_PX), (0, 0, 0, 0))
    S = TILE_PX
    base = {"bark": (92, 70, 50), "bark_birch": (214, 210, 196), "needle": (74, 108, 60), "needle_dark": (46, 82, 62), "leaf_oak": (86, 128, 54),
            "leaf_birch": (124, 160, 74), "leaf_beech": (84, 122, 62), "leaf_willow": (128, 160, 84), "leaf_rowan": (116, 148, 76), "juniper": (70, 100, 84),
            "bush": (92, 130, 62), "rock": (138, 136, 128)}
    for name in TILES:
        i = TILES.index(name)
        x0, y0 = (i % COLS) * S, (i // COLS) * S
        if name in base:
            n = _noise(rng, S)
            col = np.array(base[name], float)
            img = np.clip(col[None, None, :] * (0.72 + 0.5 * n[:, :, None]), 0, 255)
            if name == "bark_birch":                                 # dark horizontal birch marks
                for _ in range(10):
                    y = int(rng.integers(0, S))
                    img[y:y + 3, int(rng.integers(0, S // 2)):int(rng.integers(S // 2, S))] *= 0.25
            if name.startswith("leaf") or name in ("bush", "juniper", "needle", "needle_dark"):   # speckle of light leaf flecks
                sp = rng.random((S, S)) > 0.93
                img[sp] = np.clip(img[sp] * 1.25, 0, 255)
            rgba = np.dstack([img, np.full((S, S), 255.0)]).astype("uint8")
            atlas.paste(Image.fromarray(rgba, "RGBA"), (x0, y0))
            continue
        k = 3                                                          # alpha tiles drawn 3x supersampled
        T = Image.new("RGBA", (S * k, S * k), (0, 0, 0, 0))
        d = ImageDraw.Draw(T)
        G = lambda a, b: int(rng.integers(a, b))
        if name == "grass":
            for _ in range(11):
                bx, h = G(10, S - 10) * k, G(S // 3, S - 8) * k
                lean = G(-18, 18) * k
                g = (G(70, 110), G(120, 165), G(40, 70), 255)
                d.polygon([(bx - 3 * k, S * k), (bx + 3 * k, S * k), (bx + lean, S * k - h)], fill=g)
        elif name == "reed":
            for _ in range(8):
                bx, h = G(18, S - 18) * k, G(S // 2, S - 4) * k
                lean = G(-10, 10) * k
                d.polygon([(bx - 2 * k, S * k), (bx + 2 * k, S * k), (bx + lean, S * k - h)], fill=(G(110, 150), G(140, 170), G(60, 80), 255))
            for cx in (S * 0.4, S * 0.62):
                d.ellipse([cx * k - 4 * k, 14 * k, cx * k + 4 * k, 44 * k], fill=(96, 62, 36, 255))
                d.line([cx * k, 44 * k, cx * k, S * k], fill=(120, 140, 70, 255), width=2 * k)
        elif name == "fern":
            d.line([S * k // 2, S * k, S * k // 2, 8 * k], fill=(60, 100, 40, 255), width=2 * k)
            for t in np.linspace(0.12, 0.92, 9):
                y = S * k - t * (S - 10) * k
                w = (1 - t) * 0.46 * S * k + 6 * k
                for sgn in (-1, 1):
                    d.polygon([(S * k // 2, y), (S * k // 2 + sgn * w, y - 9 * k), (S * k // 2 + sgn * w * 0.9, y - 2 * k)], fill=(G(60, 90), G(120, 150), G(40, 60), 255))
        elif name == "flower":
            for cx, col in ((0.3, (220, 90, 160)), (0.55, (240, 220, 80)), (0.78, (240, 240, 240))):
                top = G(18, 50) * k
                d.line([cx * S * k, S * k, cx * S * k, top], fill=(70, 120, 50, 255), width=2 * k)
                d.ellipse([cx * S * k - 8 * k, top - 8 * k, cx * S * k + 8 * k, top + 8 * k], fill=col + (255,))
                d.ellipse([cx * S * k - 3 * k, top - 3 * k, cx * S * k + 3 * k, top + 3 * k], fill=(200, 150, 40, 255))
        elif name.startswith("card_"):
            tint = {"card_oak": (78, 128, 48), "card_birch": (128, 168, 70), "card_beech": (80, 124, 56), "card_willow": (132, 166, 84), "card_rowan": (118, 152, 72)}[name]
            willow = name == "card_willow"
            for _ in range(46):
                if willow:                                             # long hanging strands
                    x = G(8, S - 8)
                    ln = G(S // 2, S - 6)
                    d.line([x * k, 4 * k, (x + G(-6, 6)) * k, ln * k], fill=tuple(int(c * rng.uniform(0.8, 1.15)) for c in tint) + (255,), width=3 * k)
                else:
                    ang = rng.uniform(0, 2 * math.pi)
                    rr = math.sqrt(rng.random()) * 0.42 * S
                    x, y = S / 2 + rr * math.cos(ang), S / 2 + rr * math.sin(ang) * 0.9
                    ll = G(9, 15)
                    col = tuple(int(c * rng.uniform(0.75, 1.2)) for c in tint) + (255,)
                    d.ellipse([(x - ll / 2) * k, (y - ll / 3) * k, (x + ll / 2) * k, (y + ll / 3) * k], fill=col)
        elif name == "imp_conifer":
            for t in range(5):
                yb = S * 0.88 - t * S * 0.16
                w = S * (0.40 - t * 0.065)
                d.polygon([((S / 2 - w) * k, yb * k), ((S / 2 + w) * k, yb * k), (S / 2 * k, (yb - S * 0.34) * k)], fill=(52 + 4 * t, 92 + 5 * t, 60, 255))
            d.rectangle([(S / 2 - 3) * k, S * 0.88 * k, (S / 2 + 3) * k, (S - 1) * k], fill=(88, 66, 46, 255))
        elif name == "imp_broad":
            d.rectangle([(S / 2 - 4) * k, S * 0.6 * k, (S / 2 + 4) * k, (S - 1) * k], fill=(92, 70, 50, 255))
            for _ in range(60):
                ang = rng.uniform(0, 2 * math.pi)
                rr = math.sqrt(rng.random()) * 0.42 * S
                x, y = S / 2 + rr * math.cos(ang), S * 0.36 + rr * math.sin(ang) * 0.85
                r = G(8, 16)
                c = (G(70, 100), G(110, 150), G(50, 70), 255)
                d.ellipse([(x - r) * k, (y - r) * k, (x + r) * k, (y + r) * k], fill=c)
        T = T.resize((S, S), Image.LANCZOS)
        arr = np.asarray(T).copy()
        a = arr[:, :, 3] > 0
        if a.any():                                                   # colour the transparent texels with the mean opaque colour so mips/filtering do not fringe dark
            arr[~a, :3] = arr[a, :3].mean(0).astype("uint8")
        arr[:, :, 3] = np.where(arr[:, :, 3] > 100, 255, 0)           # hard alpha for alpha-cut (MASK) materials
        atlas.paste(Image.fromarray(arr, "RGBA"), (x0, y0))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    atlas.save(path, optimize=True)
    return path


def atlas_material():
    return {ATLAS_MAT: {"id": ATLAS_MAT, "mean_color": "#5c7a46", "texture": f"textures/{ATLAS_MAT}.png", "roughness": 0.95, "metallic": 0.0, "uv": "unit"}}


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


# ------------------------------------------------------------------ shape primitives (metres, z up)
class _B(wm.Builder):
    pass


def _ring(b, cx, cy, z, r, n, tile, v=0.5, rot=0.0, rng=None, jit=0.0):
    out = []
    for k in range(n):
        a = rot + 2 * math.pi * k / n
        rr = r * (1 + (rng.uniform(-jit, jit) if rng is not None and jit else 0))
        out.append(b.vert((cx + rr * math.cos(a), cy + rr * math.sin(a), z), tile_uv(tile, k / n, v)))
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


def _cone(b, sub, tile, x, y, z0, z1, r, n, rot=0.0):
    ring = _ring(b, x, y, z0, r, n, tile, 1.0, rot)
    apex = b.vert((x, y, z1), tile_uv(tile, 0.5, 0.0))
    for k in range(n):
        b.tri(sub, ring[k], ring[(k + 1) % n], apex)


def _blob(b, sub, tile, c, rx, ry, rz, rings, seg, rng, jit=0.12, rot=0.0):
    """Low-poly ellipsoid: rings-1 latitude rings + two pole fans, jittered so no two blobs look alike."""
    cx, cy, cz = c
    top = b.vert((cx, cy, cz + rz * (1 + rng.uniform(-jit, jit) * 0.5)), tile_uv(tile, 0.5, 0.0))
    bot = b.vert((cx, cy, cz - rz * 0.8), tile_uv(tile, 0.5, 1.0))
    rs = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        z = cz + rz * math.cos(phi)
        r = math.sin(phi)
        ring = []
        for k in range(seg):
            a = rot + 2 * math.pi * k / seg
            j = 1 + rng.uniform(-jit, jit)
            ring.append(b.vert((cx + rx * r * j * math.cos(a), cy + ry * r * j * math.sin(a), z), tile_uv(tile, k / seg, i / rings)))
        rs.append(ring)
    for k in range(seg):
        n = (k + 1) % seg
        b.tri(sub, top, rs[0][k], rs[0][n])
        for i in range(len(rs) - 1):
            b.quad(sub, rs[i][k], rs[i + 1][k], rs[i + 1][n], rs[i][n])
        b.tri(sub, bot, rs[-1][n], rs[-1][k])


def _card(b, sub, tile, x, y, z, w, h, ang, tilt=0.0):
    """Vertical alpha-cut quad whose bottom-centre is at (x, y, z); `tilt` leans the top outward (metres)."""
    ca, sa = math.cos(ang), math.sin(ang)
    pts = [(-w / 2, 0.0, 1.0, 1.0), (w / 2, 0.0, 0.0, 1.0), (w / 2, tilt, 0.0, 0.0), (-w / 2, tilt, 1.0, 0.0)]
    ids = []
    for lx, ly, u, v in pts:
        ids.append(b.vert((x + lx * ca - ly * sa, y + lx * sa + ly * ca, z + (h if v == 0.0 else 0.0)), tile_uv(tile, 1 - u, v)))
    b.quad(sub, ids[0], ids[1], ids[2], ids[3])


def _crossed(b, sub, tile, x, y, z, w, h, ang0=0.0, n=2):
    for i in range(n):
        _card(b, sub, tile, x, y, z, w, h, ang0 + math.pi * i / n)


# ------------------------------------------------------------------ species -> mesh
def _card_tile(sp):
    leaf = sp["tiles"]["leaf"]
    t = "card_" + leaf.split("_", 1)[1] if leaf.startswith("leaf_") else "card_oak"
    return t if t in TILES else "card_oak"


def _lodp(g, lod):
    """Detail parameters of generator dict `g` at `lod` (0 or 1)."""
    if lod == 0:
        return dict(g)
    q = dict(g)
    q["blobs"] = max(1, int(math.ceil(g.get("blobs", 1) / 2)))
    q["rings"] = max(3, g.get("rings", 4) - 1)
    q["seg"] = max(4, g.get("seg", 6) - 2)
    q["tiers"] = max(2, g.get("tiers", 5) - 3)
    q["cards"] = 0 if g["type"] != "cards" else max(2, g.get("cards", 4) // 2)
    return q


def build_species_mesh(sp, variant=0, lod=0):
    """Mesh of one species at its nominal height (mid of height_ft), LOD 0/1/2. Deterministic in (species, variant)."""
    import zlib
    rng = np.random.default_rng(zlib.crc32(f"{sp['id']}:{variant}".encode()))
    h = float(np.mean(sp["height_ft"])) * FT
    r = h * float(sp["crown_ratio"])
    g = _lodp(sp["gen"], min(lod, 1))
    b = wm.Builder(smooth=True)
    kind = g["type"]
    lt, bt = sp["tiles"]["leaf"], sp["tiles"]["bark"]
    if lod >= 2:                                                       # impostor: two crossed billboards of the species silhouette
        if sp["kind"] in ("ground", "prop"):
            return wm.Mesh(np.zeros((0, 3)), np.zeros((0, 2)), {}, True)
        tile = "imp_conifer" if kind in ("conifer", "broadconifer") else "imp_broad"
        w = max(2 * r, 0.8) * (1.0 if tile == "imp_broad" else 1.1)
        _crossed(b, "leaf", tile, 0, 0, 0, w, h)
        return b.build()
    if kind == "conifer":
        tr = 0.012 * h + 0.05
        _cyl(b, "bark", bt, 0, 0, 0, h * 0.22, tr * 1.3, tr, 5)
        n, seg = g["tiers"], g["seg"]
        for i in range(n):
            t = i / n
            z0 = h * (0.12 + 0.62 * t)
            z1 = h if i == n - 1 else z0 + h * (0.85 / n) * 1.85
            _cone(b, "leaf", lt, 0, 0, z0, min(z1, h), r * (1.0 - 0.78 * t) * rng.uniform(0.92, 1.08), seg, rot=rng.uniform(0, 1))
    elif kind in ("broad", "broadconifer", "willow"):
        tr = 0.02 * h + 0.06
        th = h * g.get("trunk", 0.4)
        _cyl(b, "bark", bt, 0, 0, 0, th, tr * 1.4, tr, 6)
        nb = g.get("blobs", 3)
        crown_z = th + (h - th) * (0.5 if kind != "broadconifer" else 0.6)
        crown_h = (h - th) * 0.62
        for i in range(nb):
            a = rng.uniform(0, 2 * math.pi) + i * 2.4
            off = r * 0.45 * (0 if nb == 1 else 1) * rng.uniform(0.5, 1.0)
            cz = crown_z + (i - (nb - 1) / 2) * crown_h * 0.3 * (1 if kind != "broadconifer" else 1.4)
            rr = r * (0.85 if nb > 1 else 1.1) * rng.uniform(0.85, 1.05)
            flat = 0.6 if kind == "broadconifer" else 0.95
            _blob(b, "leaf", lt, (off * math.cos(a), off * math.sin(a), cz), rr, rr, crown_h * flat, g.get("rings", 4), g.get("seg", 7), rng)
        nc = g.get("cards", 0)
        ct = _card_tile(sp)
        for i in range(nc):
            a = 2 * math.pi * i / max(nc, 1) + rng.uniform(0, 1)
            rad = r * 0.8
            if kind == "willow":
                _card(b, "leaf", ct, rad * math.cos(a), rad * math.sin(a), crown_z - crown_h * 0.9, r * 0.9, crown_h * 1.6, a + math.pi / 2)
            else:
                _card(b, "leaf", ct, rad * math.cos(a), rad * math.sin(a), crown_z - crown_h * 0.25, r * 0.9, crown_h * 0.9, a + math.pi / 2, tilt=0.15 * r)
    elif kind == "shrub":
        aspect, ln = g.get("aspect", 0.7), g.get("long", 1.0)
        nb = g.get("blobs", 2)
        for i in range(nb):
            if ln > 1:
                x = (i / max(nb - 1, 1) - 0.5) * (ln - 1) * r * 1.2
                y = 0.0
            else:
                a = rng.uniform(0, 2 * math.pi)
                x, y = 0.45 * r * math.cos(a) * (i > 0), 0.45 * r * math.sin(a) * (i > 0)
            _blob(b, "leaf", lt, (x, y, h * 0.5), r * (ln if (ln > 1 and nb == 1) else 1.0) * 0.8, r * 0.8, h * 0.5 * (1 + aspect * 0.2), g.get("rings", 3), g.get("seg", 6), rng, jit=0.15)
    elif kind == "cards":
        nc = g.get("cards", 4)
        w = g.get("w", 0.6) * h * 0.9
        for i in range(nc):
            a = math.pi * i / nc + rng.uniform(-0.2, 0.2)
            _card(b, "leaf", lt, 0, 0, 0, max(w, 0.35), h * rng.uniform(0.85, 1.0), a, tilt=(0.25 * h if g.get("droop") else 0.0))
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
        for end, flip in ((0, 1), (1, -1)):
            c = b.vert((a[end][0][0] if False else (-ln / 2 if end == 0 else ln / 2), 0, rad), tile_uv(bt, 0.5, 0.5))
            for k in range(n):
                b.tri("bark", c, a[end][k], a[end][(k + 1) % n]) if end == 0 else b.tri("bark", c, a[end][(k + 1) % n], a[end][k])
    elif kind == "rock":
        _blob(b, "leaf", lt, (0, 0, h * 0.35), h * 0.9, h * 0.75, h * 0.5, g.get("rings", 3), g.get("seg", 6), rng, jit=0.25)
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
    """Template mesh -> placed copy (scale in xy, `zscale` multiplies the vertical scale, rotation about z, offset metres). All subs collapse to the atlas material."""
    c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    V = tmpl.V * np.array([scale, scale, scale * zscale])
    V = np.stack([V[:, 0] * c - V[:, 1] * s, V[:, 0] * s + V[:, 1] * c, V[:, 2]], 1) + np.asarray(pos, float)
    return V


def merge_instances(parts):
    """parts: [(template Mesh, scale, rot_deg, pos_m, zscale)] -> one Mesh with a single 'fol_atlas' sub (one primitive)."""
    Vs, UVs, Fs, off = [], [], [], 0
    for t, sc, rot, pos, zs in parts:
        if not t.V.size:
            continue
        Vs.append(instance_mesh(t, sc, rot, pos, zs))
        UVs.append(t.UV)
        F = np.concatenate(list(t.subs.values())) if t.subs else np.zeros((0, 3), int)
        Fs.append(F + off)
        off += len(t.V)
    if not Vs:
        return wm.Mesh(np.zeros((0, 3)), np.zeros((0, 2)), {}, True)
    return wm.Mesh(np.concatenate(Vs), np.concatenate(UVs), {ATLAS_MAT: np.concatenate(Fs)}, True)


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
