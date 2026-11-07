"""Textured raster fills for the town generator output ('full map' style).

Rasterises every street, plaza, building, field and water polygon of world/<place> at the view's dpi, fills each with the texture
of its type (data-driven: presets/town_styles/<style>.json 'types'), and writes world-aligned RGBA PNGs, one per category, covering
exactly the SVG 'Bounds' window of the view (same georeferencing idea as shading.py):

  fill_fields.png    -> layer 'ART - Fill Fields'
  fill_water.png     -> layer 'ART - Fill Water'      (water texture, shallows, foam, banks)
  fill_streets.png   -> layer 'ART - Fill Streets'    (streets, bridges, plazas)
  fill_buildings.png -> layer 'ART - Fill Buildings'  (roofs with ridge shading, eaves, drop shadow)
  fills.json         -> sidecar: bounds in feet, dpi, layers, and the flat-colour groups used for vector swatches

  python fills_raster.py --place bridgehollow --view town --out-dir illustrator/out/fills [--style full_map] [--dpi 200]
         [--scale FT_PER_IN] [--preset ..] [--grid ..] [--page 17x11] [--model-dir DIR] [--only fields,water,streets,buildings]

Textures are the seamless tiles in presets/textures (make_fill_textures.py adds cobble, gravel, slate, thatch, tilled, water ...),
sampled with the same anti-tiling approach as the shading (low-frequency domain warp, two blended copies) but using world-aligned
noise so neighbouring shapes of one type join without seams. Roofs and fields are rotated to the shape's long axis.
"""
import argparse
import json
import math
import os
import re
import sys
import zlib

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shading as sh  # noqa: E402

ILL = os.path.abspath(os.path.join(HERE, ".."))
STYLE_DIR = os.path.join(ILL, "presets", "town_styles")
CATS = ("fields", "water", "streets", "buildings")
LAYER = {"fields": "ART - Fill Fields", "water": "ART - Fill Water", "streets": "ART - Fill Streets", "buildings": "ART - Fill Buildings"}
PART = {"streets": ("Streets", "Roads"), "plazas": ("Plazas", "Roads"), "buildings": ("Roofs", "Buildings"),
        "fields": ("Fields", "Fences"), "water": ("Water", "Water")}
STRUCTURED = {"plank", "timber_roof", "stone_slab", "slate", "shingle", "red_tile", "tilled", "wheat", "crop_green"}
SS = 3   # mask supersampling (anti-aliased edges)


def load_style(name):
    p = name if os.path.exists(name) else os.path.join(STYLE_DIR, name if name.endswith(".json") else name + ".json")
    d = json.load(open(p, encoding="utf-8"))
    if "types" not in d:
        raise SystemExit(f"style {name} has no 'types' map (only 'full map' styles can be rasterised)")
    return d


def seed_of(*a):
    return zlib.crc32("|".join(str(x) for x in a).encode()) & 0x7fffffff


def hexrgb(h):
    return sh.parse_color(h)


# ------------------------------------------------------------------ sampler
class Sampler:
    """World-aligned anti-tiled texture sampling over the view window."""

    def __init__(self, x0, y0, wf, hf, ppf, min_tile_px, seed):
        self.x0, self.y0, self.wf, self.hf, self.ppf, self.min_tile_px, self.seed = x0, y0, wf, hf, ppf, min_tile_px, seed
        self.tex, self.noise = {}, {}

    def texture(self, spec):
        if spec not in self.tex:
            tile, flat = sh.load_texture(spec if spec.startswith('#') or os.path.splitext(spec)[1] else spec + '.png', sh.TEX_DIR)
            mips = None
            if tile is not None:
                mips = [tile]
                while mips[-1].shape[0] > 16:
                    t = mips[-1]
                    h = t.shape[0] // 2 * 2
                    mips.append(t[:h].reshape(h // 2, 2, h, 3).mean(1)[:, :h].reshape(h // 2, h // 2, 2, 3).mean(2))
            mean = flat if tile is None else tile.reshape(-1, 3).mean(0)
            self.tex[spec] = (tile, flat, mips, mean)
        return self.tex[spec]

    def mean(self, spec):
        return self.texture(spec)[3]

    def field(self, key, scale_ft, X, Y):
        """Smooth noise ~[-1,1] at world coords, feature size scale_ft (cached over the window)."""
        k = (key, round(scale_ft, 1))
        if k not in self.noise:
            rng = np.random.default_rng(seed_of(self.seed, *k))
            gx, gy = int(self.wf / scale_ft) + 4, int(self.hf / scale_ft) + 4
            fine = ndi.zoom(rng.uniform(-1, 1, (gy, gx)), 6, order=3)
            self.noise[k] = (np.clip(fine, -1, 1), scale_ft / 6.0, scale_ft)
        fine, cell, sc = self.noise[k]
        return ndi.map_coordinates(fine, [(Y - self.y0 + sc) / cell, (X - self.x0 + sc) / cell], order=1, mode="nearest")

    def sample(self, spec, X, Y, tile_ft, warp=None, rot=0.0, cx=0.0, cy=0.0, off=(0.0, 0.0), key="a", vary=0.06):
        tile, flat, mips, mean = self.texture(spec)
        te = max(float(tile_ft), self.min_tile_px / self.ppf)
        if tile is None:
            n = self.field(key + "g", max(te / 3, 2.0), X, Y)
            return flat[None, None, :] * (1 + 0.10 * n[..., None])
        if warp is None:
            warp = 0.0 if spec in STRUCTURED else 0.5
        th = math.radians(rot)
        c, s = math.cos(th), math.sin(th)
        dx, dy = X - cx, Y - cy
        u, v = c * dx + s * dy + off[0], -s * dx + c * dy + off[1]
        lvl = int(np.clip(math.floor(math.log2(max(tile.shape[0] / (te * self.ppf), 1e-6))), 0, len(mips) - 1))
        m = mips[lvl]
        if warp > 0:
            wx = self.field("wx" + key, te * 2.7, X, Y) * te * warp
            wy = self.field("wy" + key, te * 2.7, X, Y) * te * warp
            a = sh.sample_tile(m, u + wx, v + wy, te)
            th2 = math.radians(31.0)
            c2, s2 = math.cos(th2), math.sin(th2)
            b = sh.sample_tile(m, c2 * u - s2 * v + 0.37 * te + wy, s2 * u + c2 * v + 0.61 * te - wx, te * 1.31)
            w = sh.smoothstep(self.field("tw" + key, te * 3.3, X, Y) * 0.7 + 0.5)[..., None]
            mm = mean
            out = mm + ((a - mm) * (1 - w) + (b - mm) * w) / np.sqrt((1 - w) ** 2 + w ** 2)
        else:
            out = sh.sample_tile(m, u, v, te)
        if vary:
            out = out * (1 + vary * self.field("vr" + key, te * 3.0, X, Y))[..., None]
        return out


# ------------------------------------------------------------------ raster helpers
class Canvas:
    def __init__(self, nx, ny):
        self.p = np.zeros((ny, nx, 4), np.float32)   # premultiplied RGB + alpha

    def over(self, ix0, iy0, rgb, alpha):
        h, w = alpha.shape
        sl = self.p[iy0:iy0 + h, ix0:ix0 + w]
        a = alpha[..., None].astype(np.float32)
        sl[..., :3] = rgb * a + sl[..., :3] * (1 - a)
        sl[..., 3:] = a + sl[..., 3:] * (1 - a)

    def to_rgba(self):
        a = self.p[..., 3:]
        rgb = np.where(a > 1e-4, self.p[..., :3] / np.maximum(a, 1e-4), 0)
        return np.dstack([np.clip(rgb, 0, 255), np.clip(a * 255, 0, 255)]).astype(np.uint8)


class Grid:
    def __init__(self, x0, y0, wf, hf, ppf):
        self.x0, self.y0, self.wf, self.hf, self.ppf = x0, y0, wf, hf, ppf
        self.nx, self.ny = int(round(wf * ppf)), int(round(hf * ppf))

    def crop(self, bounds, pad_ft=0.0):
        """Pixel box (ix0, iy0, w, h) of a world bbox, clipped to the window; None if outside."""
        a, b, c, d = bounds
        ix0 = max(0, int(math.floor((a - pad_ft - self.x0) * self.ppf)))
        iy0 = max(0, int(math.floor((b - pad_ft - self.y0) * self.ppf)))
        ix1 = min(self.nx, int(math.ceil((c + pad_ft - self.x0) * self.ppf)))
        iy1 = min(self.ny, int(math.ceil((d + pad_ft - self.y0) * self.ppf)))
        if ix1 <= ix0 or iy1 <= iy0:
            return None
        return ix0, iy0, ix1 - ix0, iy1 - iy0

    def coords(self, box):
        ix0, iy0, w, h = box
        X, Y = np.meshgrid(self.x0 + (ix0 + np.arange(w) + 0.5) / self.ppf, self.y0 + (iy0 + np.arange(h) + 0.5) / self.ppf)
        return X, Y

    def mask(self, geom, box):
        """Anti-aliased coverage 0..1 of a shapely (multi)polygon inside the pixel box."""
        from PIL import Image, ImageDraw
        ix0, iy0, w, h = box
        im = Image.new("L", (w * SS, h * SS), 0)
        dr = ImageDraw.Draw(im)
        tr = lambda ring: [((x - self.x0) * self.ppf * SS - ix0 * SS, (y - self.y0) * self.ppf * SS - iy0 * SS) for x, y in ring]
        for g in getattr(geom, "geoms", [geom]):
            if g.is_empty or g.geom_type != "Polygon":
                continue
            dr.polygon(tr(g.exterior.coords), fill=255)
            for i in g.interiors:
                dr.polygon(tr(i.coords), fill=0)
        im = im.resize((w, h), Image.BOX)
        return np.asarray(im, np.float32) / 255.0


def long_axis(poly):
    """(angle deg of the long side, length, width, centre) of the minimum rotated rectangle."""
    r = poly.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return 0.0, 1.0, 1.0, (poly.centroid.x, poly.centroid.y)
    c = list(r.exterior.coords)[:4]
    e = [(c[(i + 1) % 4][0] - c[i][0], c[(i + 1) % 4][1] - c[i][1]) for i in range(2)]
    l0, l1 = math.hypot(*e[0]), math.hypot(*e[1])
    d = e[0] if l0 >= l1 else e[1]
    return math.degrees(math.atan2(d[1], d[0])), max(l0, l1), min(l0, l1), (r.centroid.x, r.centroid.y)


def pick(cfg, rng):
    """cfg: {'texture': name} or {'textures': [[name, weight], ...] | [name, ...]} -> texture name."""
    if "textures" in cfg:
        ts = [(t, 1.0) if isinstance(t, str) else (t[0], float(t[1])) for t in cfg["textures"]]
        w = np.array([t[1] for t in ts])
        return ts[int(rng.choice(len(ts), p=w / w.sum()))][0]
    return cfg["texture"]


def tint(rgb, rng, k):
    """Per-entity brightness and slight hue jitter (+-k)."""
    if not k:
        return rgb
    f = 1 + rng.uniform(-k, k)
    return rgb * np.array([f * (1 + rng.uniform(-k, k) * 0.4), f, f * (1 + rng.uniform(-k, k) * 0.4)])


def edge_darken(canvas, ppf, ft, dark):
    a = canvas.p[..., 3] > 0.5
    d = ndi.distance_transform_edt(a) / ppf
    f = 1 - dark * np.exp(-np.maximum(d - 0.5 / ppf, 0) / max(ft, 1.0 / ppf))
    canvas.p[..., :3] *= (f * a + (~a))[..., None].astype(np.float32)


def soft_shadow(grid, canvas, geoms, dx_ft, dy_ft, blur_ft, alpha):
    """Drop shadow of the union of geoms (offset +x right, +y down, like the light from the north-west)."""
    from shapely.ops import unary_union
    from shapely import affinity
    if not geoms:
        return
    u = affinity.translate(unary_union(geoms), dx_ft, dy_ft)
    box = grid.crop(u.bounds, blur_ft * 3)
    if not box:
        return
    m = grid.mask(u, box)
    m = ndi.gaussian_filter(m, blur_ft * grid.ppf)
    canvas.over(box[0], box[1], np.zeros(m.shape + (3,), np.float32), np.clip(m * alpha, 0, 1))


# ------------------------------------------------------------------ categories
def classify_street(e, cfg):
    k = e.get("kind", "street")
    if k == "bridge":
        return "bridge"
    if k == "road":
        return "road"
    cl = cfg.get("classify", {})
    w = e["geometry"]["width_ft"]
    if re.search(cl.get("alley_name", r"^Alley\b"), e.get("name", "")) and w <= cl.get("alley_max_width_ft", 12.5):
        return "alley"
    if w <= cl.get("alley_max_width_ft", 12.5) and cl.get("narrow_is_alley", True):
        return "alley"
    return k if k in cfg else "street"


def street_dir(e):
    p = e["geometry"]["points"]
    return math.degrees(math.atan2(p[-1][1] - p[0][1], p[-1][0] - p[0][0]))


class Ctx:
    def __init__(self, model, v, style, dpi, seed, log=print):
        self.model, self.v, self.style, self.log = model, v, style, log
        raster = style.get("raster", {})
        self.ppf = dpi / v.fpi
        self.seed = seed if seed is not None else int(style.get("seed", 1))
        self.grid = Grid(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0, self.ppf)
        self.smp = Sampler(v.x0, v.y0, v.x1 - v.x0, v.y1 - v.y0, self.ppf, float(raster.get("min_tile_px", 40)), self.seed)
        self.types = style["types"]
        self.flat = {}    # (part, texture) -> {"mean": rgb, "ids": []}

    def note(self, part, tex, rgb, eid):
        g = self.flat.setdefault((part, tex), {"rgb": [], "ids": []})
        g["rgb"].append(rgb)
        g["ids"].append(eid)

    def rng(self, *a):
        return np.random.default_rng(seed_of(self.seed, *a))


def build_streets(cx):
    from shapely.geometry import Polygon
    import render_world as rw
    cfg, pcfg = cx.types.get("streets", {}), cx.types.get("plazas", {})
    grid, cv = cx.grid, Canvas(cx.grid.nx, cx.grid.ny)
    shapes = rw.street_shapes(cx.model["streets"])
    items = []
    for e in cx.model["streets"]:
        sh_ = shapes[e["id"]]
        if sh_.is_empty:
            continue
        cls = classify_street(e, cfg)
        items.append((e, sh_, cls, "streets", cfg.get(cls) or cfg.get("street")))
    bridges = [i for i in items if i[2] == "bridge"]
    others = [i for i in items if i[2] != "bridge"]
    plazas = []
    for e in cx.model["districts"]:
        if e["kind"] == "square" and pcfg:
            pg = Polygon(rw.entity_polygon(e)).buffer(0)
            plazas.append((e, pg, "plaza", "plazas", pcfg.get("default") or next(iter(pcfg.values()))))
    bs = cfg.get("bridge_shadow", {"dx_ft": 2.5, "dy_ft": 2.5, "blur_ft": 2.0, "alpha": 0.35})
    for group in (others, plazas, bridges):
        if group is bridges and bridges and bs:
            soft_shadow(grid, cv, [g for _, g, *_ in bridges], bs["dx_ft"], bs["dy_ft"], bs["blur_ft"], bs["alpha"])
        for e, geom, cls, part, tc in group:
            box = grid.crop(geom.bounds, 1.0)
            if not box:
                continue
            rng = cx.rng(e["id"])
            spec = pick(tc, rng)
            X, Y = grid.coords(box)
            ctr = geom.centroid
            rot = street_dir(e) + 90 if cls == "bridge" and tc.get("align", "across") == "across" else tc.get("rot", 0.0)
            off = (rng.uniform(0, 200), rng.uniform(0, 200))
            rgb = cx.smp.sample(spec, X, Y, tc.get("tile_ft", 24), tc.get("warp"), rot, ctr.x, ctr.y, off, key=spec)
            rgb = tint(rgb, rng, tc.get("tint", 0.05))
            cv.over(box[0], box[1], rgb.astype(np.float32), grid.mask(geom, box))
            cx.note(part, spec, tint(cx.smp.mean(spec), rng, 0), e["id"])
    eg = cfg.get("edge", {"ft": 2.0, "dark": 0.25})
    edge_darken(cv, cx.ppf, eg["ft"], eg["dark"])
    return cv


def build_buildings(cx):
    from shapely.geometry import Polygon
    import render_world as rw
    cfg = cx.types.get("buildings", {})
    grid, cv = cx.grid, Canvas(cx.grid.nx, cx.grid.ny)
    geoms = []
    for b in cx.model["buildings"]:
        pg = Polygon(rw.entity_polygon(b)).buffer(0)
        if not pg.is_empty and grid.crop(pg.bounds, 6):
            geoms.append((b, pg))
    sd = cfg.get("shadow", {"dx_ft": 3.0, "dy_ft": 3.0, "blur_ft": 1.6, "alpha": 0.38})
    if sd:
        soft_shadow(grid, cv, [g for _, g in geoms], sd["dx_ft"], sd["dy_ft"], sd["blur_ft"], sd["alpha"])
    eave = cfg.get("eave", {"ft": 1.1, "dark": 0.38})
    gable = float(cfg.get("gable", 0.22))
    for b, pg in geoms:
        tc = cfg.get(b.get("kind", ""), cfg.get("default", {"texture": "shingle"}))
        rng = cx.rng(b["id"])
        spec = pick(tc, rng)
        box = grid.crop(pg.bounds, 0.5)
        if not box:
            continue
        X, Y = grid.coords(box)
        ang, L, W, (cxx, cyy) = long_axis(pg)
        off = (rng.uniform(0, 100), rng.uniform(0, 100))
        rgb = cx.smp.sample(spec, X, Y, tc.get("tile_ft", 14), tc.get("warp"), ang, cxx, cyy, off, key=spec, vary=tc.get("vary", 0.04))
        rgb = tint(rgb, rng, tc.get("tint", 0.10))
        a = grid.mask(pg, box)
        th = math.radians(ang)
        vperp = -math.sin(th) * (X - cxx) + math.cos(th) * (Y - cyy)          # signed distance across the ridge (ft)
        ndir = (-math.sin(th), math.cos(th))
        light = ndir[0] * -0.7071 + ndir[1] * -0.7071                           # facet normal . direction to the light (NW)
        side = np.tanh(vperp / 0.8)
        k = gable * (0.5 + 0.5 * abs(light) * 1.4) * (1 if light >= 0 else -1)
        rgb = rgb * (1 + k * side)[..., None]
        ridge = np.exp(-(vperp / 0.5) ** 2)
        rgb = rgb * (1 - 0.16 * ridge)[..., None]
        d = ndi.distance_transform_edt(np.pad(a > 0.5, 1, mode='edge'))[1:-1, 1:-1] / cx.ppf
        e_ft = max(eave["ft"], 1.2 / cx.ppf)
        rgb = rgb * (1 - eave["dark"] * np.exp(-np.maximum(d - 0.5 / cx.ppf, 0) / e_ft))[..., None]
        cv.over(box[0], box[1], rgb.astype(np.float32), a)
        cx.note("buildings", spec, cx.smp.mean(spec), b["id"])
    return cv


def build_fields(cx):
    from shapely.geometry import Polygon
    import render_world as rw
    cfg = cx.types.get("fields", {})
    grid, cv = cx.grid, Canvas(cx.grid.nx, cx.grid.ny)
    border = cfg.get("border", {"color": "#4d6b30", "ft": 2.5, "alpha": 0.55})
    for e in cx.model["districts"]:
        if e["kind"] != "field":
            continue
        pg = Polygon(rw.entity_polygon(e)).buffer(0)
        box = grid.crop(pg.bounds, 0.5)
        if pg.is_empty or not box:
            continue
        rng = cx.rng(e["id"])
        crop = e.get("crop") or pick({"textures": cfg.get("choose", [["tilled", 1]])}, rng)
        tc = (cfg.get("crops") or {}).get(crop, {"texture": crop})
        spec = pick(tc, rng)
        X, Y = grid.coords(box)
        ang, L, W, (cxx, cyy) = long_axis(pg)
        ang += tc.get("rot_jitter_deg", 6.0) * rng.uniform(-1, 1)
        off = (rng.uniform(0, 100), rng.uniform(0, 100))
        rgb = cx.smp.sample(spec, X, Y, tc.get("tile_ft", 40), tc.get("warp"), ang, cxx, cyy, off, key=spec, vary=tc.get("vary", 0.05))
        rgb = tint(rgb, rng, tc.get("tint", 0.07))
        a = grid.mask(pg, box)
        if border:
            d = ndi.distance_transform_edt(np.pad(a > 0.5, 1, mode='edge'))[1:-1, 1:-1] / cx.ppf
            hb = np.exp(-(d / max(border["ft"], 1.2 / cx.ppf)) ** 2)[..., None] * border["alpha"]
            rgb = rgb * (1 - hb) + hexrgb(border["color"]) * hb
        cv.over(box[0], box[1], rgb.astype(np.float32), a)
        cx.note("fields", spec, cx.smp.mean(spec), e["id"])
    return cv


def build_water(cx):
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    import render_world as rw
    cfg = cx.types.get("water", {})
    grid, cv = cx.grid, Canvas(cx.grid.nx, cx.grid.ny)
    bank = cfg.get("bank", {"texture": "mud", "ft": 10.0, "tile_ft": 30, "alpha": 0.9, "wet": 0.35})
    kinds = {}
    for e in cx.model["water"]:
        kinds.setdefault(e.get("kind", "river"), []).append(e)
    for kind, ents in kinds.items():
        tc = cfg.get(kind) or cfg.get("default") or {"texture": "water"}
        geom = unary_union([Polygon(rw.entity_polygon(e)).buffer(0) for e in ents])
        box = grid.crop(geom.bounds, bank["ft"] + 3 if bank else 3)
        if not box:
            continue
        spec = pick(tc, cx.rng(kind))
        X, Y = grid.coords(box)
        a = grid.mask(geom, box)
        ins = ndi.distance_transform_edt(np.pad(a > 0.5, 1, mode='edge'))[1:-1, 1:-1] / cx.ppf
        out = ndi.distance_transform_edt(np.pad(a <= 0.5, 1, mode='edge'))[1:-1, 1:-1] / cx.ppf
        if bank:
            bt = bank["ft"]
            ba = (1 - sh.smoothstep(out / bt)) * bank.get("alpha", 0.9) * (out > 0)
            brgb = cx.smp.sample(bank["texture"], X, Y, bank.get("tile_ft", 30), None, 0, 0, 0, (0, 0), key="bank")
            wet = np.exp(-out / 2.0)[..., None] * bank.get("wet", 0.35)
            brgb = brgb * (1 - wet)
            cv.over(box[0], box[1], brgb.astype(np.float32), np.clip(ba * (1 - a), 0, 1).astype(np.float32))
        hw = float(np.mean([e.get("width_ft", 40) for e in ents])) / 2
        rgb = cx.smp.sample(spec, X, Y, tc.get("tile_ft", 40), tc.get("warp", 0.35), tc.get("rot", 0), 0, 0, (0, 0), key=spec, vary=0.03)
        t = sh.smoothstep(ins / max(0.45 * hw, 3.0))[..., None]
        rgb = rgb * (1.10 - 0.28 * t)
        rgb = rgb * t + (rgb * 0.65 + hexrgb(tc.get("shallow", "#9fd0d0")) * 0.35) * (1 - t)
        foam = np.exp(-(ins / max(1.1, 1.2 / cx.ppf))) [..., None] * tc.get("foam", 0.5)
        rgb = rgb * (1 - foam) + hexrgb(tc.get("foam_color", "#e8f2f0")) * foam
        cv.over(box[0], box[1], rgb.astype(np.float32), a)
        for e in ents:
            cx.note("water", spec, cx.smp.mean(spec), e["id"])
    return cv


BUILDERS = {"fields": build_fields, "water": build_water, "streets": build_streets, "buildings": build_buildings}


def render_fills(model, v, style, out_dir, dpi=None, seed=None, only=None, log=print):
    from PIL import Image
    dpi = float(dpi or style.get("raster", {}).get("dpi", 200))
    cx = Ctx(model, v, style, dpi, seed)
    if cx.grid.nx * cx.grid.ny > 80_000_000:
        raise SystemExit(f"{cx.grid.nx}x{cx.grid.ny} px is too large; lower the fills dpi")
    os.makedirs(out_dir, exist_ok=True)
    layers = []
    for cat in CATS:
        if only and cat not in only:
            continue
        cv = BUILDERS[cat](cx)
        rgba = cv.to_rgba()
        fn = f"fill_{cat}.png"
        Image.fromarray(rgba, "RGBA").save(os.path.join(out_dir, fn), dpi=(dpi, dpi))
        layers.append({"category": cat, "png": fn, "layer": LAYER[cat], "name": f"fill_{cat}_png"})
        log(f"  {cat:9s} {fn} {rgba.shape[1]}x{rgba.shape[0]} px, {(rgba[..., 3] > 0).mean() * 100:.1f}% covered")
    flat = []
    for (part, tex), g in sorted(cx.flat.items()):
        label, layer = PART[part]
        mean = np.mean(g["rgb"], 0)
        flat.append({"part": part, "swatch": f"VB {label} - {tex}", "layer": layer, "rgb": [int(round(c)) for c in mean], "ids": g["ids"]})
    info = {"style": style.get("name"), "dpi": dpi, "ppf": cx.ppf, "scale_ft_per_in": v.fpi, "size_px": [cx.grid.nx, cx.grid.ny],
            "bounds_ft": {"x_min": v.x0, "y_min": v.y0, "x_max": v.x1, "y_max": v.y1}, "y_axis": "down",
            "layers": layers, "flat": flat}
    json.dump(info, open(os.path.join(out_dir, "fills.json"), "w"), indent=1)
    return info


def add_args(ap):
    ap.add_argument("--style", default="full_map", help="town_styles preset name or JSON path (needs a 'types' map)")
    ap.add_argument("--fills-dpi", "--dpi", dest="fills_dpi", type=float, help="raster dpi (default from the style, 200)")
    ap.add_argument("--fills-seed", type=int)
    ap.add_argument("--only", help="comma list of fields,water,streets,buildings")


def run(a, model, view_arg="town"):
    import render_world as rw
    v, cfg, title, kind, ident = rw.compute_view(model, view_arg, {"preset": getattr(a, "preset", None), "scale": getattr(a, "scale", None),
                                                                     "grid": getattr(a, "grid", None), "page": getattr(a, "page", None),
                                                                     "major_every": getattr(a, "grid_major", None)})
    style = load_style(a.style)
    out = a.out_dir
    print(f"fills: style '{style.get('name')}', window {v.x0:.0f},{v.y0:.0f} - {v.x1:.0f},{v.y1:.0f} ft at 1 in = {v.fpi:g} ft")
    only = set(a.only.split(",")) if a.only else None
    info = render_fills(model, v, style, out, a.fills_dpi, a.fills_seed, only)
    print("wrote", os.path.join(out, "fills.json"))
    return info


def main():
    import render_world as rw
    import worldio
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--grid-major", type=int)
    ap.add_argument("--page")
    ap.add_argument("--model-dir")
    ap.add_argument("--water-source", choices=["world", "working"])
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"])
    ap.add_argument("--out-dir", required=True)
    add_args(ap)
    a = ap.parse_args()
    worldio.set_source(a.terrain_source, a.water_source)
    run(a, rw.load_place(a.place, a.model_dir), a.view)


if __name__ == "__main__":
    main()
