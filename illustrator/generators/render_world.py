"""Render a world/<place> JSON model to a layered SVG for Illustrator.

  python illustrator/generators/render_world.py [--place bridgehollow] [--view town|bowl|street:<id>|building:<id>] [--out PATH]
      [--preset town|bowl|street|room] [--scale FT_PER_IN] [--grid FT] [--grid-major N] [--page WxH]   (defaults: world/<place>/view_settings.json)
      [--terrain] [--contours] [--no-contour-mask] [--contour-interval 10] [--index-interval 50] [--label-size 6] [--units ft|m]
  --terrain regenerates world/<place>/terrain/ from terrain_spec.json and writes illustrator/out/<place>_height.png (hillshade);
  --terrain or --contours overlays contours + elevation labels (default output illustrator/out/<place>_terrain.svg for the town view).

Default output for the town view: illustrator/out/bridgehollow_town.svg
Layer tree: see illustrator/DESIGN.md section 3. GEN layers are rewritten; ART layers are emitted empty.
"""
import argparse
import base64
import glob
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib_svg import LayerTree  # noqa: E402
import contours as ct  # noqa: E402
import viewcfg  # noqa: E402
import terrain as tr  # noqa: E402
import label_offset as lbo  # noqa: E402
import label_style as lst  # noqa: E402
import label_declutter as ld  # noqa: E402
import dataclasses as _dc  # noqa: E402
import label_curve as lcv  # noqa: E402
import region_draw as rdraw  # noqa: E402
import worldio  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PAGE_W_IN, PAGE_H_IN, MARGIN_IN = 17, 11, 0.5   # defaults; the active view_settings page/margin are used per render

SPEC = [
    ("NOTES", []),
    ("LABELS", [ld.LAYER_LEGEND, ld.LAYER_MARKERS, lbo.LAYER_ANCHORS, lbo.LAYER_LEADERS, "Labels - Districts", "Labels - Streets", "Labels - Buildings",
                "Labels - Rooms", ld.LAYER_HIDDEN, ct.LAYER_LABELS, lst.LAYER_BACKING]),
    ("ART - Top", []),
    ("ART - Fills", []),
    ("ART - Textures", []),
    ("ART - Masks", []),
    ("LINES", ["Walls", "Buildings", "Blocks", "Roads", "Water", ("Terrain", [ct.LAYER_MINOR, ct.LAYER_INDEX]), "Fences"] + rdraw.LAYERS),
    ("GUIDES", ["Grid", "Scale bar", "North arrow", "Bounds"]),
]

CSS = """\
path { fill: none; }
.guide-line { fill: none; stroke: #7a7a7a; stroke-width: 0.35; }
.guide-major { fill: none; stroke: #5a5a5a; stroke-width: 0.6; }
.grid-minor { fill: none; stroke: #7a766c; stroke-width: 0.3; stroke-opacity: 0.38; }
.grid-major { fill: none; stroke: #6c685e; stroke-width: 0.5; stroke-opacity: 0.55; }
.field { fill: none; stroke: #5d7a3a; stroke-width: 0.4; }
.guide-major { fill: none; stroke: #5a5a5a; stroke-width: 0.6; }
.field { fill: none; stroke: #5d7a3a; stroke-width: 0.4; }
.wall { fill: none; stroke: #000000; stroke-width: 1.25; }
.road { fill: none; stroke: #000000; stroke-width: 0.75; }
.water { fill: none; stroke: #1a4f8a; stroke-width: 0.75; }
.bar { fill: none; stroke: #9c8556; stroke-width: 0.4; }
.proposed { stroke-dasharray: 3 1.5; }
text { fill: #000000; stroke: none; font-family: Arial, sans-serif; }
.leader { fill: none; }
.leader-casing { fill: none; }
""" + ct.CSS + rdraw.CSS


# ------------------------------------------------------------------ model
def load_place(name, model_dir=None):
    """model_dir: read place/districts/streets/buildings from this folder instead of world/<place> (panel town candidate).
    Water always comes from worldio.water_path (world file, or the panel's working water file when enabled)."""
    root = model_dir or os.path.join(REPO, "world", name)
    rd = lambda f: json.load(open(os.path.join(root, f), encoding="utf-8"))
    m = {"place": rd("place.json"), "districts": rd("districts.json")["districts"],
         "streets": rd("streets.json")["streets"],
         "water": json.load(open(worldio.water_path(name), encoding="utf-8"))["water"], "buildings": []}
    for f in sorted(glob.glob(os.path.join(root, "buildings", "*.json"))):
        m["buildings"].append(json.load(open(f, encoding="utf-8")))
    if os.path.exists(os.path.join(root, "walls.json")):       # town wall + gates written by place_create.py (walled towns); drawn on the Walls layer
        m["walls"] = json.load(open(os.path.join(root, "walls.json"), encoding="utf-8"))
    for k_ in ("details", "markers"):        # region children (region_extract.py): generated detail + off-map markers, absent for normal places
        if os.path.exists(os.path.join(root, k_ + ".json")):
            m[k_] = json.load(open(os.path.join(root, k_ + ".json"), encoding="utf-8"))
    return m


# ------------------------------------------------------------------ geometry
def offset_polygon(pts, width):
    """Closed outline of a polyline with the given width (mitered, miter limited)."""
    hw = width / 2.0
    n = len(pts)
    left, right = [], []
    for i in range(n):
        if i == 0:
            d = _unit(pts[0], pts[1]); nx, ny = -d[1], d[0]; s = 1.0
        elif i == n - 1:
            d = _unit(pts[-2], pts[-1]); nx, ny = -d[1], d[0]; s = 1.0
        else:
            d0, d1 = _unit(pts[i - 1], pts[i]), _unit(pts[i], pts[i + 1])
            nx, ny = -(d0[1] + d1[1]), d0[0] + d1[0]
            ln = math.hypot(nx, ny) or 1.0
            nx, ny = nx / ln, ny / ln
            cos = max(nx * -d0[1] + ny * d0[0], 0.4)
            s = 1.0 / cos
        left.append((pts[i][0] + nx * hw * s, pts[i][1] + ny * hw * s))
        right.append((pts[i][0] - nx * hw * s, pts[i][1] - ny * hw * s))
    return left + right[::-1]


def _unit(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ln = math.hypot(dx, dy) or 1.0
    return dx / ln, dy / ln


def clip_poly(poly, x0, y0, x1, y1):
    """Sutherland-Hodgman against an axis-aligned rectangle."""
    def clip(pts, inside, inter):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(inter(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(inter(prev, cur))
        return out

    def ix(xc):
        return lambda a, b: (xc, a[1] + (b[1] - a[1]) * (xc - a[0]) / (b[0] - a[0]))

    def iy(yc):
        return lambda a, b: (a[0] + (b[0] - a[0]) * (yc - a[1]) / (b[1] - a[1]), yc)

    pts = [tuple(p) for p in poly]
    for inside, inter in ((lambda p: p[0] >= x0, ix(x0)), (lambda p: p[0] <= x1, ix(x1)),
                          (lambda p: p[1] >= y0, iy(y0)), (lambda p: p[1] <= y1, iy(y1))):
        if not pts:
            return []
        pts = clip(pts, inside, inter)
    return pts if len(pts) >= 3 else []


def centroid(poly):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def entity_polygon(e):
    g = e["geometry"]
    if g["type"] == "polyline":
        return offset_polygon(g["points"], g["width_ft"])
    return [tuple(p) for p in g["points"]]


def street_shapes(streets):
    """Non-overlapping street outlines {id: shapely geometry}: wider streets win at junctions, so the drawn curbs
    tile the road area and organic (curved) streets have no self-crossing mitres. Bridges keep their own outline."""
    from shapely.geometry import LineString
    from shapely.ops import unary_union
    order = sorted(streets, key=lambda e: (e["kind"] != "bridge", -e["geometry"]["width_ft"], e["id"]))
    out, taken = {}, None
    for e in order:
        g = e["geometry"]
        sh = LineString(g["points"]).buffer(g["width_ft"] / 2, cap_style=2, join_style=1, resolution=4)
        if e["kind"] != "bridge" and taken is not None:
            sh = sh.difference(taken)
        out[e["id"]] = sh
        taken = sh if taken is None else unary_union([taken, sh])
    return out


def shape_rings(sh):
    polys = []
    for g in getattr(sh, "geoms", [sh]):
        if g.is_empty or g.geom_type != "Polygon" or g.area < 1.0:
            continue
        polys.append([tuple(p) for p in g.exterior.coords][:-1])
        polys += [[tuple(p) for p in i.coords][:-1] for i in g.interiors]
    return polys


# ------------------------------------------------------------------ view
class View:
    def __init__(self, fpi, cx, cy, page=(PAGE_W_IN, PAGE_H_IN), margin=MARGIN_IN):
        self.fpi = fpi
        self.page, self.margin = page, margin
        self.k = 72.0 / fpi                       # points per foot
        self.wf = (page[0] - 2 * margin) * fpi    # window size in feet
        self.hf = (page[1] - 2 * margin) * fpi
        self.x0, self.y0 = cx - self.wf / 2, cy - self.hf / 2
        self.x1, self.y1 = cx + self.wf / 2, cy + self.hf / 2

    def px(self, p):
        return (self.margin * 72 + (p[0] - self.x0) * self.k, self.margin * 72 + (p[1] - self.y0) * self.k)

    def inside(self, p):
        return self.x0 <= p[0] <= self.x1 and self.y0 <= p[1] <= self.y1

    def clip(self, poly):
        return clip_poly(poly, self.x0, self.y0, self.x1, self.y1)

    def d(self, polys):
        parts = []
        for poly in polys:
            q = [self.px(p) for p in poly]
            parts.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in q) + " Z")
        return " ".join(parts)


def path(id_, d, cls):
    return f'<path id="{id_}" class="{cls}" fill="none" d="{d}"/>'


def text(id_, x, y, s, size, rot=None, bold=False, anchor="middle"):
    tr = f' transform="rotate({rot:g} {x:.2f} {y:.2f})"' if rot else ""
    w = ' font-weight="bold"' if bold else ""
    return (f'<text id="{id_}" x="{x:.2f}" y="{y:.2f}" font-size="{size:g}" text-anchor="{anchor}"{w}{tr}>'
            f'{escape(s)}</text>')


# ------------------------------------------------------------------ render
CIVIC_SKIP = {"house", "shed", "farmhouse", "barn"}


def street_label(v, e, size, fpi, name):
    """-> (x, y, angle) page-pt anchor of the street name (baseline point, rotated along the street) or None."""
    from shapely.geometry import LineString
    ln = LineString(e["geometry"]["points"])
    if ln.length < max(2.0 * fpi, 40):
        return
    best = None
    for f in (0.5, 0.35, 0.65, 0.25, 0.75):
        p = ln.interpolate(f, normalized=True)
        if v.inside((p.x, p.y)):
            best = f
            break
    if best is None:
        return
    d = ln.length * best
    a, m, b = ln.interpolate(max(d - 12, 0)), ln.interpolate(d), ln.interpolate(min(d + 12, ln.length))
    ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
    if ang > 90 or ang <= -90:
        ang = (ang + 180 + 180) % 360 - 180
    th = math.radians(ang)
    off = e["geometry"]["width_ft"] / 2 + size / v.k * 0.7
    nx_, ny_ = -math.sin(th), math.cos(th)
    if ny_ > 0:                      # keep the label on the upper side of the street on the page
        nx_, ny_ = -nx_, -ny_
    x, y = v.px((m.x + nx_ * off, m.y + ny_ * off))
    return x, y, ang


def street_label_cands(v, e, size, fpi, name):
    """All usable street-name positions [(x, y, angle)] (page pt, rotated along the street), best first; [] when the street is too short."""
    from shapely.geometry import LineString
    ln = LineString(e["geometry"]["points"])
    if ln.length < max(2.0 * fpi, 40):
        return []
    out = []
    for f in (0.5, 0.35, 0.65, 0.25, 0.75):
        p = ln.interpolate(f, normalized=True)
        if not v.inside((p.x, p.y)):
            continue
        d = ln.length * f
        a, m, b = ln.interpolate(max(d - 12, 0)), ln.interpolate(d), ln.interpolate(min(d + 12, ln.length))
        ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        if ang > 90 or ang <= -90:
            ang = (ang + 180 + 180) % 360 - 180
        th = math.radians(ang)
        off = e["geometry"]["width_ft"] / 2 + size / v.k * 0.7
        nx_, ny_ = -math.sin(th), math.cos(th)
        if ny_ > 0:                      # keep the label on the upper side of the street on the page
            nx_, ny_ = -nx_, -ny_
        x, y = v.px((m.x + nx_ * off, m.y + ny_ * off))
        out.append((x, y, ang))
    return out


def cut_d(rings, cut, closed=True):
    """Path data for rings (page pt) with the parts under `cut` removed (real geometry: open sub-paths, no clipping paths)."""
    from shapely.geometry import LineString
    from shapely.ops import linemerge
    parts, changed = [], False
    for ring in rings:
        pts = list(ring) + ([ring[0]] if closed else [])
        ls = LineString(pts)
        if not ls.intersects(cut):
            parts.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in ring) + (" Z" if closed else ""))
            continue
        changed = True
        diff = ls.difference(cut)
        segs = [diff] if diff.geom_type == "LineString" else [g for g in getattr(diff, "geoms", []) if g.geom_type == "LineString"]
        if len(segs) > 1:
            m = linemerge(segs)
            segs = [m] if m.geom_type == "LineString" else list(m.geoms)
        for g in segs:
            if g.length >= 0.4 and not g.is_empty:
                parts.append("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in g.coords))
    return " ".join(parts), changed


def _nice_fit(v):
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 7.5, 10):
        if v <= m * e * 1.0001:
            return round(m * e, 4)
    return v


def fit_bounds(model, what="buildings"):
    """Bounds [x0,y0,x1,y1] (ft) of what the page should frame: buildings (+ streets) | area (town_params area_ft lasso) | all (the place)."""
    pts = []
    if what == "area":
        try:
            tp = json.load(open(os.path.join(REPO, "world", model["place"]["id"], "town_params.json"), encoding="utf-8"))
            pts = [tuple(p) for p in tp.get("area_ft") or []]
        except (OSError, ValueError):
            pts = []
    if what == "buildings" or (what == "area" and not pts):
        for b in model["buildings"]:
            pts += [tuple(p) for p in entity_polygon(b)]
        for e in model["streets"]:
            if e.get("kind") != "road":                  # the long through-roads leave the town: not what we frame
                pts += [tuple(p) for p in e["geometry"]["points"]]
    if what == "all" or not pts:
        w = model["place"]["bounds"]
        return [0.0, 0.0, float(w["width_ft"]), float(w["height_ft"])]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def compute_view(model, view_arg, cfg_over=None):
    """-> (View, cfg, title, kind, ident). Shared by render() and panelio.py (page <-> feet conversion for the panel)."""
    place = model["place"]
    bw, bh = place["bounds"]["width_ft"], place["bounds"]["height_ft"]
    kind, _, ident = view_arg.partition(":")
    streets = {s["id"]: s for s in model["streets"]}
    blds = {b["id"]: b for b in model["buildings"]}
    o = dict(cfg_over or {})
    if kind in ("region", "district"):          # the zoomed-in view of a region child: a town-style view with the 'district' preset
        kind = "town"
        o["preset"] = o.get("preset") or "district"
    cfg = viewcfg.load(place["id"], o.get("preset") or kind, scale=o.get("scale"), grid=o.get("grid"),
                       page=o.get("page"), major_every=o.get("major_every"), grid_extent=o.get("grid_extent"))
    fpi, grid_ft, major_n = cfg["scale_ft_per_in"], cfg["grid_ft"], cfg["grid_major_every"]
    pw, ph = cfg["page_in"]
    margin = cfg["margin_in"]
    W, H = pw * 72.0, ph * 72.0

    focus = cfg.get("focus", "center")
    fit = o.get("fit")
    if fit and kind in ("town", "bowl"):                  # framing: scale and centre chosen so the built-up area fills the page
        fb = fit_bounds(model, fit)
        if fb:
            padft = float(o.get("fit_margin") or 0.0)
            fw, fh = fb[2] - fb[0] + 2 * padft, fb[3] - fb[1] + 2 * padft
            need = max(fw / max(pw - 2 * margin, 1e-6), fh / max(ph - 2 * margin, 1e-6)) * 1.04
            if not o.get("scale"):
                fpi = _nice_fit(need)
                cfg["scale_ft_per_in"] = fpi
                cfg.pop("scale_bar_ft", None)
                cfg["scale_bar_ft"] = viewcfg._nice(5 * fpi)
                if not o.get("grid"):
                    cfg["grid_ft"] = max(viewcfg._nice(fpi), 5)
            focus = [(fb[0] + fb[2]) / 2.0, (fb[1] + fb[3]) / 2.0]
            cfg["fit_bounds_ft"] = [round(x, 1) for x in fb]
    ent_poly = None
    if kind == "street":
        if ident not in streets:
            sys.exit(f"unknown street id: {ident}")
        ent_poly, title = entity_polygon(streets[ident]), f"{place['name']} - street: {streets[ident]['name']}"
    elif kind == "building":
        if ident not in blds:
            sys.exit(f"unknown building id: {ident}")
        ent_poly, title = entity_polygon(blds[ident]), f"{place['name']} - building: {blds[ident]['name']}"
    elif kind in ("town", "bowl"):
        title = f"{place['name']} - {'whole bowl' if kind == 'bowl' else 'district view' if place.get('parent') else 'town view'}"
    else:
        sys.exit("--view must be town, bowl, street:<id> or building:<id>")
    if isinstance(focus, list):
        fx, fy = focus
    elif focus == "entity" and ent_poly:
        fx, fy = centroid(ent_poly)
    else:
        fx, fy = bw / 2, bh / 2
    v = View(fpi, fx, fy, (pw, ph), margin)
    title += f"  (1 in = {fpi:g} ft, grid {grid_ft:g} ft)"
    return v, cfg, title, kind, ident


def shading_luma(h, meta, phases="auto", ppf=0.4):
    """Luminance (0..1) of the terrain shading at ppf px/ft over the whole terrain -> (array, ppf). Picks contour colour/casing."""
    import numpy as np
    import shading as sh
    name = sh.DEFAULT_PRESET if phases in (None, "", "auto") else phases
    pp = name if os.path.exists(name) else os.path.join(sh.PRESET_DIR, name if name.endswith(".json") else name + ".json")
    doc = sh.load_phase_file(pp)
    img, _ = sh.render(h, meta, doc["phases"], ppf, os.path.dirname(os.path.abspath(pp)), doc.get("hillshade"), None,
                       doc.get("base_color", "#808080"), verbose=False, muted=sh.muted_from(doc),
                       slope_smooth_ft=float(doc.get("slope_smooth_ft") or 0.0))
    return (img.astype(float) @ np.array([0.299, 0.587, 0.114])) / 255.0, ppf


def render(model, view_arg, out_path, topts=None, cfg_over=None, lopts=None, lstyle=None, dopts=None):
    place = model["place"]
    bw, bh = place["bounds"]["width_ft"], place["bounds"]["height_ft"]
    streets = {s["id"]: s for s in model["streets"]}
    blds = {b["id"]: b for b in model["buildings"]}
    v, cfg, title, kind, ident = compute_view(model, view_arg, cfg_over)
    fpi, grid_ft, major_n = cfg["scale_ft_per_in"], cfg["grid_ft"], cfg["grid_major_every"]
    pw, ph = cfg["page_in"]
    margin = cfg["margin_in"]
    W, H = pw * 72.0, ph * 72.0
    lf = min(max((100.0 / fpi) ** 0.5, 0.6), 1.6)     # label size factor follows the scale
    ls = lambda base: round(base * lf, 1)

    lock_leaders = bool((lopts if lopts is not None else cfg.get("label_offset") or {}).get("lock_leaders", True))
    t = LayerTree(SPEC, pw, ph, css=CSS, locked=["GUIDES", "Grid", "Scale bar", "North arrow", "Bounds"] + ([lbo.LAYER_LEADERS] if lock_leaders else []),
                  hidden=[ld.LAYER_HIDDEN])

    lcfg = lst.merge(viewcfg.label_style(place["id"]), *(lstyle if isinstance(lstyle, list) else [lstyle]))
    styles = {c_: lst.resolve(lcfg, c_) for c_ in lst.CATEGORIES}
    targets = set(lcfg.get("mask_targets") or [])
    backing = lst.LAYER_BACKING if lcfg.get("backing_layer", True) else None
    lines = []        # linework is written after the labels are placed, so label knock-outs can cut it

    def addpoly(layer, id_, poly, cls, status, target):
        poly = v.clip(poly)
        if not poly:
            return None
        c = cls + (" proposed" if status == "proposed" else "")
        lines.append((layer, id_, [poly], c, target))
        return poly

    # LINES
    for e in model["water"]:
        addpoly("Water", e["id"], entity_polygon(e), "water", None, "water")     # solid bank line: a dashed outline made the river read as a wide dashed band
    for e in model["water"]:
        for bi, bp in enumerate(e.get("bars", [])):          # point-bar / sandbar hints on the inner bends (water.json `bars`)
            addpoly("Water", "%s_bar%d" % (e["id"], bi + 1), [tuple(p) for p in bp], "bar", None, "water")
    for e in model["districts"]:
        k = e["kind"]
        layer, cls = {"square": ("Roads", "road"), "field": ("Fences", "field"),
                      "block": ("Blocks", "guide-line")}.get(k, ("Terrain", "guide-line"))
        addpoly(layer, e["id"], entity_polygon(e), cls, e.get("status"), {"Roads": "streets", "Fences": "fences"}.get(layer, "blocks"))
    shapes = street_shapes(model["streets"])
    for e in model["streets"]:
        rings = [r for r in (v.clip(r) for r in shape_rings(shapes[e["id"]])) if r]
        if rings:
            c = ("wall" if e["kind"] == "bridge" else "road") + (" proposed" if e.get("status") == "proposed" else "")
            lines.append(("Roads", e["id"], rings, c, "streets"))
    try:                                                    # BRIDGES: generated bridge symbols (bridge_maker.py, world/<place>/bridges.json): outline, parapets, piers/arch hatch
        import bridge_maker as _bm
        for _bid, _suf, _ring, _cls in _bm.symbols_for_place(place["id"]):
            _poly = v.clip([tuple(q) for q in _ring])
            if _poly:
                lines.append(("Roads", f"{_bid}_{_suf}", [_poly], _cls + " proposed", "streets"))
    except ImportError:
        pass
    wl = model.get("walls") or {}
    for e in wl.get("walls", []):
        pts_ = e["geometry"]["points"]
        if len(pts_) >= 2:
            rg_ = v.clip(offset_polygon([tuple(p) for p in pts_], float(e["geometry"].get("width_ft", 5))))
            if rg_:
                lines.append(("Walls", e["id"], [rg_], "wall proposed", "buildings"))
    for g_ in wl.get("gates", []):
        gx_, gy_ = g_["point"]
        hw_ = float(g_.get("width_ft", 16)) / 2 + 3
        rg_ = v.clip([(gx_ - hw_, gy_ - 5), (gx_ + hw_, gy_ - 5), (gx_ + hw_, gy_ + 5), (gx_ - hw_, gy_ + 5)])
        if rg_:
            lines.append(("Walls", g_["id"], [rg_], "wall", "buildings"))
    for e in model["buildings"]:
        addpoly("Buildings", e["id"], entity_polygon(e), "wall", e.get("status"), "buildings")
        if kind == "building" and e["id"] == ident:
            for r in e.get("rooms", []):
                addpoly("Walls", r["id"], entity_polygon(r), "wall", r.get("status"), "buildings")
            for dr in e.get("doors", []):
                if "geometry" in dr:
                    addpoly("Walls", dr["id"], entity_polygon(dr), "guide-line", dr.get("status"), "buildings")

    cs = None
    # TERRAIN contours + elevation labels (heightmap from world/<place>/terrain/)
    if topts is not None:
        h, meta = tr.load_heightmap(place["id"])     # worldio: patched / carved / base
        print(f"terrain source: {meta.get('source', 'base')}" + (f" WARNING: {meta['warning']}" if meta.get("warning") else ""))
        mask = []
        if topts["use_mask"]:
            from shapely.geometry import Polygon
            inc = set(cfg.get("contour_mask", {}).get("include", ["buildings", "streets", "plazas"]))
            if "buildings" in inc:
                for e in model["buildings"]:
                    pg = entity_polygon(e)
                    if len(pg) >= 3:
                        mask.append(Polygon(pg).buffer(0))
            if "streets" in inc:
                mask += [g for g in shapes.values() if not g.is_empty]
            if "plazas" in inc:
                for e in model["districts"]:
                    if e["kind"] == "square":
                        mask.append(Polygon(entity_polygon(e)).buffer(0))
        frame = ct.Frame(v.x0, v.y0, v.x1, v.y1, v.k, margin * 72, margin * 72)
        est = styles["elevation"]
        cp = ct.ContourParams(minor=topts["minor"], index=topts["index"], font_size=est.size or topts["label_size"] * lf,
                              halo_pt=est.knockout_pad if est.knock else 0.0,
                              units=topts["units"], use_mask=topts["use_mask"],
                              sea_level_ft=float(meta.get("sea_level_ft", 0.0)),
                              **{k_: topts[k_] for k_ in ("decimals", "label_spacing_ft", "min_len_ft", "follow_line",
                                                          "upright", "labels", "emphasize_datum") if k_ in topts})
        cs = ct.build(h, meta["cell_ft"], frame, cp, mask)
        cs.halo = topts.get("halo", True)
        if topts.get("shade_luma") != "none" and cs.halo:      # contour colour/casing follows the shading under it
            from scipy import ndimage as ndi_
            lum, lppf = shading_luma(h, meta, topts.get("shade_luma") or "auto")
            def luma_at(xp, yp, _l=lum, _f=frame, _p=lppf):
                return ndi_.map_coordinates(_l, [((yp - _f.oy) / _f.k + _f.y0) * _p, ((xp - _f.ox) / _f.k + _f.x0) * _p], order=1, mode="nearest")
            ct.classify_tone(cs, luma_at)
            tc = {k_: sum(1 for p_ in cs.pieces if p_.get("tone") == k_) for k_ in ("dark", "mid", "light")}
            print(f"contour tone by shading: {tc}")
        print(f"contours: {len(cs.pieces)} paths, {len(cs.labels)} labels, relief {meta['elev_min']:.0f}..{meta['elev_max']:.0f} ft, "
              f"mask={'on (%d polygons)' % len(mask) if mask else 'off'}")

    # LABELS (closed shapes get an offset + leader when the text does not fit inside; see label_offset.py).
    # Text styling, wrapping, halo / backing box / knock-out: label_style.py. Tiers, scale visibility, scoring, pinned positions,
    # numbered legend, QA: label_declutter.py
    from shapely import affinity as _aff
    from shapely.geometry import Polygon as _Poly, LineString as _Line
    dc = dopts if dopts is not None else ld.merge(viewcfg.declutter(place["id"]))
    lp = lbo.LabelParams.from_dict(lopts if lopts is not None else cfg.get("label_offset"))
    qf = 0.85 if dc.get("quiet") else 1.0
    if dc.get("quiet"):
        lp.stroke_width, lp.dash, lp.casing_width, lp.dot_radius = min(lp.stroke_width, 0.5), lp.dash or "0.9 1.6", min(lp.casing_width, 1.2), min(lp.dot_radius, 1.1)
    m_pt = margin * 72
    shapes_pt = []
    for e in model["buildings"] + [d for d in model["districts"] if d["kind"] == "square"]:
        pg = v.clip(entity_polygon(e))
        if pg:
            shapes_pt.append((e["id"], [v.px(q) for q in pg]))
    for sid, sh in shapes.items():                      # street outlines are avoided too (softly, like other shapes)
        for i_, ring in enumerate(shape_rings(sh)):
            rc = v.clip(ring)
            if rc:
                shapes_pt.append((f"{sid}#{i_}", [v.px(q) for q in rc]))
    placer = lbo.Placer(lp, frame=(m_pt, m_pt, W - m_pt, H - m_pt), shapes=shapes_pt)
    to_pt = [v.k, 0, 0, v.k, m_pt - v.x0 * v.k, m_pt - v.y0 * v.k]
    from shapely.geometry import box as _box
    win = _box(v.x0 - 50, v.y0 - 50, v.x1 + 50, v.y1 + 50)
    feats = {"building": [], "plaza": [], "road": [], "water": []}
    for e in model["buildings"]:
        g_ = _Poly(entity_polygon(e)).buffer(0)
        if g_.intersects(win):
            feats["building"].append((e["id"], _aff.affine_transform(g_, to_pt)))
    for e in model["districts"]:
        if e["kind"] == "square":
            feats["plaza"].append((e["id"], _aff.affine_transform(_Poly(entity_polygon(e)).buffer(0), to_pt)))
    for sid, sh in shapes.items():
        if not sh.is_empty and sh.intersects(win):
            feats["road"].append((sid, _aff.affine_transform(sh, to_pt)))
    for e in model["water"]:
        g_ = _Poly(entity_polygon(e)).buffer(0)
        if g_.intersects(win):
            feats["water"].append((e["id"], _aff.affine_transform(g_, to_pt)))
    junc = []
    sl_ = [(s_["id"], _Line(s_["geometry"]["points"])) for s_ in model["streets"] if len(s_["geometry"]["points"]) > 1]
    for i_ in range(len(sl_)):
        for j_ in range(i_ + 1, len(sl_)):
            x_ = sl_[i_][1].intersection(sl_[j_][1])
            for p_ in (x_.geoms if hasattr(x_, "geoms") else [x_]):
                if p_.geom_type == "Point" and v.inside((p_.x, p_.y)):
                    junc.append(v.px((p_.x, p_.y)))
    placer.set_features(feats, junc, dc.get("weights"))
    placer.score = bool(dc.get("score"))
    placer.move_thresh = float(dc.get("area_move", 0.30))
    overrides = ld.load_overrides(place["id"]) if dc.get("overrides") else {}
    abbr = lst.load_abbreviations(extra=dc.get("abbreviations"))
    sampler = ld.make_sampler(dc["contrast_png"]) if dc.get("contrast_png") else None
    ft_to_pt = lambda q: (m_pt + (q[0] - v.x0) * v.k, m_pt + (q[1] - v.y0) * v.k)
    recs = []                                           # every label as a lst.Rec
    est = styles["elevation"]
    contour_boxes = []
    if cs is not None:
        for lb in cs.labels:
            w_ = max(lst.measure(lb["text"], lb["size"], est), 1.0)
            rec = lst.Rec(lb["id"], ct.LAYER_LABELS, [lb["text"]], lb["x"], lb["y"], w_, lst.block_height(1, lb["size"], est),
                          lb["rot"], lb["size"], est, "contour-label")
            recs.append(rec)
            placer.add_fixed_box(lst.rec_box(rec).buffer(1.0))
            contour_boxes.append(lst.rec_box(rec))
    meta = {}                                           # entity id -> (layer, size, style, tier, text, kind)
    legacy_rows = []
    hidden_scale = []                                   # (id, layer, size, style, tier, text, (x, y)) too small for this view scale

    on_fail = dc.get("collision", "hide") if dc.get("enabled") else "keep"

    def tier_info(cat, e):
        tier = ld.tier_of(e.get("kind"), cat)
        tc = ld.tier_cfg(dc, tier)
        return tier, tc, (tc["priority"] if dc.get("enabled") else 0)

    def lab(cat, layer, e, s, size, auto_upper=False, ratio=1.0):
        pg = v.clip(entity_polygon(e))
        c = tuple(e["label_point"]) if e.get("label_point") else centroid(entity_polygon(e))
        if not pg or not v.inside(c):
            return
        st = styles[cat]
        tier, tc, pr = tier_info(cat, e)
        tf = (tc.get("size") or 1.0) if dc.get("enabled") else 1.0
        sz = round(st.size * ratio * tf * qf, 1) if st.size else round(size * tf * qf, 1)
        txt = lst.apply_case(s, st, auto_upper)
        if not ld.visible(dc, tier, fpi):
            hidden_scale.append((e["id"], layer, sz, st, tier, txt, v.px(c)))
            return
        meta[e["id"]] = (layer, sz, st, tier, txt, e.get("kind"))
        pp = [v.px(q) for q in pg]
        xs = [q[0] for q in pp]
        lays, offs = lst.build_layouts_ex(txt, st, sz, v.k, shape_w=max(xs) - min(xs), abbr=abbr)
        ov = None
        if e["id"] in overrides:
            o_ = overrides[e["id"]]
            cx_, cy_ = ft_to_pt((o_["x_ft"], o_["y_ft"]))
            if m_pt <= cx_ <= W - m_pt and m_pt <= cy_ <= H - m_pt:
                ov = {"cx": cx_, "cy": cy_, "anchor": ft_to_pt(o_["anchor_ft"]) if o_.get("anchor_ft") else None}
        mc = tc.get("max_cover") if dc.get("enabled") else None
        placer.add(e["id"], pp, s, sz, st.bold, None, point=v.px(c), layouts=lays, offset_layouts=offs, priority=pr,
                   on_fail=on_fail,
                   score_inside=(cat == "districts" and bool(dc.get("score"))), max_cover=mc, override=ov, leader=bool(tc.get("leader", True)) or not dc.get("enabled"), number=bool(tc.get("number")) and dc.get("enabled"))

    for e in model["districts"]:
        if e["kind"] == "district":
            if kind != "building":
                lab("districts", "Labels - Districts", e, e["name"], ls(9), True)
        elif e["kind"] == "square":
            lab("districts", "Labels - Districts", e, e["name"], ls(7), ratio=7 / 9)
    if kind in ("town", "street", "bowl"):
        sst = styles["streets"]
        for e in model["streets"]:
            if kind == "bowl" and e["geometry"]["width_ft"] < 22 and e["kind"] != "road":
                continue
            tier, tc, pr = tier_info("streets", e)
            tf = (tc.get("size") or 1.0) if dc.get("enabled") else 1.0
            sz = round((sst.size * tf if sst.size else ls(6) * tf) * qf, 1)
            txt = lst.apply_case(e["name"] + " *", sst)
            cands = street_label_cands(v, e, sz, fpi, txt)
            if not cands:
                continue
            w_, h_ = lst.measure(txt, sz, sst), lst.block_height(1, sz, sst)
            cl = []
            for (x_, y_, ang) in cands:
                th = math.radians(ang)
                cl.append((x_ + 0.35 * sz * math.sin(th), y_ - 0.35 * sz * math.cos(th), ang))
            if not ld.visible(dc, tier, fpi):
                hidden_scale.append((e["id"], "Labels - Streets", sz, sst, tier, txt, (cl[0][0], cl[0][1]), cl[0][2]))
                continue
            meta[e["id"]] = ("Labels - Streets", sz, sst, tier, txt, e.get("kind"))
            if not dc.get("enabled"):                    # legacy: first position, fixed, placed before everything else
                rec = lst.Rec(f"{e['id']}_label", "Labels - Streets", [txt], cl[0][0], cl[0][1], w_, h_, cl[0][2], sz, sst)
                recs.append(rec)
                placer.add_fixed_box(lst.rec_box(rec).buffer(1.0))
                legacy_rows.append({"id": e["id"], "text": txt, "tier": tier, "status": "placed", "why": None, "box": lst.rec_box(rec), "leader": None, "pinned": False})
                continue
            ov = None
            if e["id"] in overrides:
                o_ = overrides[e["id"]]
                cx_, cy_ = ft_to_pt((o_["x_ft"], o_["y_ft"]))
                ov = {"cx": cx_, "cy": cy_, "rot": cl[0][2]}
            placer.add_line(e["id"], cl, w_, h_, txt, sz, priority=pr, on_fail="hide" if on_fail == "number" else on_fail,
                            max_cover=tc.get("max_cover"), override=ov)
    for e in model["buildings"]:
        if kind != "building" and e["kind"] in CIVIC_SKIP and fpi >= 40 and not dc.get("scale_visibility"):
            continue
        lab("buildings", "Labels - Buildings", e, e["name"] + " *", ls(7) if kind != "building" else 10)
    if kind == "building":
        for r in blds[ident].get("rooms", []):
            lab("rooms", "Labels - Rooms", r, r["name"], 8)

    street_by_id = {e_['id']: e_ for e_ in model['streets']}
    results = placer.solve()
    for hs in hidden_scale:                              # too small for this scale: kept in the hidden sublayer at the label point
        id_, layer, sz, st, tier, txt, pt = hs[:7]
        hst = _dc.replace(st, mode="none", knockout=False)
        w_, h_ = lst.measure(txt, sz, hst), lst.block_height(1, sz, hst)
        recs.append(lst.Rec(f"{id_}_label", ld.LAYER_HIDDEN, [txt], pt[0], pt[1], w_, h_, hs[7] if len(hs) > 7 else None, sz, hst, "hidden-label"))
    numbered = []
    rows, manifest_labels = list(legacy_rows), {}
    n_off = n_hidden = n_pinned = 0
    for res in results:
        layer, sz, st, tier, txt, kd = meta[res.id]
        box_ = lbo.text_box(res.cx, res.cy, res.w, res.h, res.rot)
        row = {"id": res.id, "text": txt, "tier": tier, "status": res.status, "why": "collision" if res.status == "hidden" else None,
               "box": box_, "leader": res.leader, "pinned": res.pinned}
        rows.append(row)
        manifest_labels[res.id] = {"cx": round(res.cx, 2), "cy": round(res.cy, 2), "w": round(res.w, 2), "h": round(res.h, 2), "layer": layer, "tier": tier,
                                   "status": res.status, "text": txt, "anchor": [round(res.dot[0], 2), round(res.dot[1], 2)] if res.dot else None,
                                   "offset": bool(res.leader), "pinned": res.pinned}
        if res.status == "hidden":
            n_hidden += 1
            hst = _dc.replace(st, mode="none", knockout=False)
            recs.append(lst.Rec(f"{res.id}_label", ld.LAYER_HIDDEN, [txt], res.cx, res.cy, lst.measure(txt, sz, hst), lst.block_height(1, sz, hst), res.rot, sz, hst, "hidden-label"))
            continue
        if res.status == "numbered":
            numbered.append((res, sz, st, tier, txt))
            continue
        n_pinned += 1 if res.pinned else 0
        stx = st
        if sampler is not None and layer != ct.LAYER_LABELS:
            x0_, y0_ = (box_.bounds[0] - m_pt) / v.k + v.x0, (box_.bounds[1] - m_pt) / v.k + v.y0
            x1_, y1_ = (box_.bounds[2] - m_pt) / v.k + v.x0, (box_.bounds[3] - m_pt) / v.k + v.y0
            lum_ = sampler(x0_, y0_, x1_, y1_)
            if lum_ is not None and lum_ < 0.33 and st.mode in ("halo", "box"):
                stx = _dc.replace(st, color="#f7f4ea", halo_color="#14171a", box_color="#14171a", auto_contrast=False)
        rpath = ""
        if layer == "Labels - Streets" and dc.get("enabled") and dc.get("curved_streets") and not res.leader and res.id in street_by_id:
            se = street_by_id[res.id]
            cp = lcv.curved_path(se["geometry"]["points"], (res.cx, res.cy), res.w * 1.3, v, offset_ft=se["geometry"]["width_ft"] / 2 + 0.3 * sz / v.k,
                                 min_curve_deg=float(dc.get("min_curve_deg", 12.0)))
            if cp:
                rpath = cp[0]
        recs.append(lst.Rec(f"{res.id}_label", layer, res.lines, res.cx, res.cy, res.w, res.h, res.rot, sz, stx, path=rpath))
        if res.leader:
            n_off += 1
            for lay_, sv in lbo.leader_svg(res, lp, lst.text_color(stx)):
                t.add(lay_, sv)
    # river name: text on the centreline (always along the water, at the longest visible stretch)
    if dc.get("river_label", True) and kind in ("town", "bowl") and fpi <= 250:
        rst = styles["streets"]
        rsz = round((rst.size if rst.size else ls(6)) * 1.15 * qf, 1)
        for we in model["water"]:
            cl_ = we.get("centerline")
            if we.get("kind") != "river" or not cl_ or len(cl_) < 2 or not we.get("name"):
                continue
            from shapely.geometry import LineString as _LS
            ln_ = _LS([tuple(p_[:2]) for p_ in cl_])
            nm_ = re.sub(r"\s*\(.*?\)", "", we["name"]).strip()
            wid_ = lst.measure(nm_, rsz, rst) * 1.5
            best_ = None
            for f_ in (0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8):
                pc_ = ln_.interpolate(f_, normalized=True)
                if v.inside((pc_.x, pc_.y)):
                    best_ = v.px((pc_.x, pc_.y))
                    break
            if best_ is None or wid_ / v.k > ln_.length * 0.8:
                continue
            cp_ = lcv.curved_path([tuple(p_[:2]) for p_ in cl_], best_, wid_, v, offset_ft=-0.3 * rsz / v.k, always=True)
            if cp_:
                wst = _dc.replace(rst, italic=True, color="#1a4f8a", letter_spacing=max(rst.letter_spacing or 0, 1.5))
                lst.emit(t, lst.Rec(f"{we['id']}_name", "Labels - Streets", [nm_], best_[0], best_[1], wid_, rsz, 0.0, rsz, wst, path=cp_[0]), backing)
    # numbered callouts: marker circle on the map + a legend entry
    numbered.sort(key=lambda r_: (ld.tier_cfg(dc, r_[3])["priority"], round(r_[0].cy / 12), r_[0].cx))
    legend_entries = []
    for n_, (res, sz, st, tier, txt) in enumerate(numbered, 1):
        fs = lst.style_font_css(st) if hasattr(lst, "style_font_css") else "font-family:Arial, sans-serif"
        for sv in ld.marker_svg(res.id, res.marker[0], res.marker[1], res.w / 2, n_, max(sz * 0.8, 4.5), fs):
            t.add(ld.LAYER_MARKERS, sv)
        legend_entries.append((n_, txt))
        manifest_labels[res.id]["number"] = n_
    if legend_entries and dc.get("legend"):
        ls_ = styles["buildings"]
        lsz = 7.0 * qf
        fs = lst.style_font_css(ls_)
        wof = lambda s_: lst.measure(s_, lsz, ls_)
        rows_, lw_, lh_ = ld.legend_layout(legend_entries, lsz, wof, dc.get("legend_title") or "Key")
        # free margin: the part of the page outside the place bounds, else the emptiest corner of the map (with a backing)
        wf_ = place.get("window_ft") or [0, 0, bw, bh]
        bx0, by0 = ft_to_pt((wf_[0], wf_[1])); bx1, by1 = ft_to_pt((wf_[2], wf_[3]))
        spots = [(m_pt + 6, m_pt + 8, bx0 - m_pt - 12), (bx1 + 6, m_pt + 8, W - m_pt - bx1 - 12)]
        sx = next(((x_, y_) for x_, y_, aw in spots if aw >= lw_ + 4 and H - 2 * m_pt - 60 >= lh_), None)
        backing_ = None
        if sx is None:
            cands_ = [(m_pt + 8, m_pt + 8), (W - m_pt - lw_ - 8, m_pt + 8), (m_pt + 8, H - m_pt - lh_ - 8), (W - m_pt - lw_ - 8, H - m_pt - lh_ - 8)]
            sx = min(cands_, key=lambda c_: placer.cost_of(_box(c_[0], c_[1], c_[0] + lw_, c_[1] + lh_)) + sum(1 for r_ in rows if r_["status"] == "placed" and r_["box"].intersects(_box(c_[0], c_[1], c_[0] + lw_, c_[1] + lh_))))
            backing_ = ("#ffffff", 0.88)
        for sv in ld.legend_svg(rows_, sx[0], sx[1], lsz, fs, backing_, w=lw_, h=lh_):
            t.add(ld.LAYER_LEGEND, sv)
        print(f"label legend: {len(legend_entries)} numbered callouts")
    if lp.enabled:
        print(f"label offsets: {n_off} labels moved outside their shape with a leader")
    n_wrapped = sum(1 for r in recs if len(r.lines) > 1 and r.layer != ld.LAYER_HIDDEN)
    if n_wrapped:
        print(f"label wrapping: {n_wrapped} labels set on more than one line")
    n_abbr = sum(1 for res in results if res.status == "placed" and " ".join(res.lines or []) != " ".join(meta[res.id][4].split()))
    if n_abbr:
        print(f"label abbreviations: {n_abbr} labels abbreviated to fit")
    for sc_ in hidden_scale:
        rows.append({"id": sc_[0], "text": sc_[5], "tier": sc_[4], "status": "hidden", "why": "scale", "box": _box(0, 0, 0, 0), "leader": None, "pinned": False})
    if dc.get("qa"):
        qa = ld.qa_report(placer, rows, contour_boxes)
        print(ld.qa_text(qa))
        manifest = {"place": place["id"], "view": view_arg, "fpi": fpi, "k": v.k, "x0": v.x0, "y0": v.y0, "margin_pt": m_pt, "labels": manifest_labels, "qa": qa,
                    "declutter": {k_: dc[k_] for k_ in ("enabled", "scale_visibility", "collision", "score", "legend", "quiet")}}
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path + ".labels.json", "w", encoding="utf-8") as f_:
            json.dump(manifest, f_, indent=1)
        if "panel" in os.path.abspath(out_path).replace("\\", "/").split("/"):
          with open(os.path.join(os.path.dirname(out_path) or ".", "label_manifest.json"), "w", encoding="utf-8") as f_:     # the panel's Pin step reads this one
              json.dump(manifest, f_, indent=1)

    # knock-out: padded rounded boxes of the labels in mask mode (or with knockout on) cut the linework underneath
    from shapely.ops import unary_union
    cut = unary_union([lst.knock_geom(r) for r in recs if r.st.knock and r.layer != ct.LAYER_LABELS]) if any(
        r.st.knock and r.layer != ct.LAYER_LABELS for r in recs) else None
    if cut is not None and cut.is_empty:
        cut = None
    if cs is not None:
        n_c = ct.cut_pieces(cs, cut) if (cut is not None and "contours" in targets) else 0
        ct.emit(t, cs, labels=False, halo=getattr(cs, "halo", True))
        if n_c:
            print(f"label mask: {n_c} contour pieces cut under labels")
    n_l = 0
    for layer, id_, polys, c, target in lines:
        if cut is not None and target in targets:
            d_, changed = cut_d([[v.px(q) for q in poly] for poly in polys], cut)
            n_l += 1 if changed else 0
            if d_:
                t.add(layer, path(id_, d_, c))
        else:
            t.add(layer, path(id_, v.d(polys), c))
    if n_l:
        print(f"label mask: {n_l} line paths cut under labels")
    for rec in recs:
        lst.emit(t, rec, None if rec.layer in (ct.LAYER_LABELS, ld.LAYER_HIDDEN) else backing)

    # GUIDES: minor + major grid
    k = v.k
    # the grid covers the map window (the place bounds) only, so the paper margin around a small map stays clean;
    # grid_extent "page" (view_settings or --grid-full-page) keeps the old full-page grid
    wf0 = place.get("window_ft") or [0, 0, bw, bh]
    if (cfg.get("grid_extent") or "window") == "page":
        gx0, gy0, gx1, gy1 = v.x0, v.y0, v.x1, v.y1
    else:
        gx0, gy0, gx1, gy1 = max(v.x0, wf0[0]), max(v.y0, wf0[1]), min(v.x1, wf0[2]), min(v.y1, wf0[3])
    px0, py0 = v.px((gx0, gy0)); px1, py1 = v.px((gx1, gy1))
    minor, major = [], []
    major_ft = grid_ft * major_n
    nlines = (gx1 - gx0) / grid_ft + (gy1 - gy0) / grid_ft
    for axis, lo, hi in (("x", gx0, gx1), ("y", gy0, gy1)):
        g = math.ceil(lo / grid_ft)
        while g * grid_ft <= hi and gx1 > gx0 and gy1 > gy0:
            pos = g * grid_ft
            q = v.px((pos, pos))
            seg = ([(q[0], py0), (q[0], py1)] if axis == "x" else [(px0, q[1]), (px1, q[1])])
            (major if major_n and g % major_n == 0 else minor).append(seg)
            g += 1
    def grid_d(segs):
        if cut is not None and "grid" in targets:
            return cut_d(segs, cut, closed=False)[0]
        return " ".join("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in sg) for sg in segs)

    if minor and nlines < 900:
        t.add("Grid", path(f"grid_{grid_ft:g}ft", grid_d(minor), "grid-minor"))
    if major:
        t.add("Grid", path(f"grid_major_{major_ft:g}ft", grid_d(major), "grid-major"))

    bar_ft = cfg["scale_bar_ft"]
    seg_ft = bar_ft / 5.0
    bx, by, bh_pt = 36 + 4, H - 26, 5
    even, odd = [], []
    for i in range(5):
        x0 = bx + seg_ft * i * k
        r = (f"M{x0:.2f},{by:.2f} L{x0 + seg_ft * k:.2f},{by:.2f} L{x0 + seg_ft * k:.2f},{by + bh_pt:.2f} "
             f"L{x0:.2f},{by + bh_pt:.2f} Z")
        (even if i % 2 == 0 else odd).append(r)
    t.add("Scale bar", path("scalebar_a", " ".join(even), "wall"))
    t.add("Scale bar", path("scalebar_b", " ".join(odd), "guide-line"))
    for i in range(6):
        t.add("Scale bar", text(f"scalebar_t{i}", bx + seg_ft * i * k, by + 16, f"{seg_ft * i:g}", 7))
    t.add("Scale bar", text("scalebar_unit", bx + bar_ft * k + 10, by + 5, f"ft   (1 in = {fpi:g} ft)", 8, anchor="start"))

    ax, ay = W - 60, H - 40
    t.add("North arrow", path("north_arrow", f"M{ax:.2f},{ay - 28:.2f} L{ax + 7:.2f},{ay + 6:.2f} L{ax:.2f},{ay:.2f} L{ax - 7:.2f},{ay + 6:.2f} Z", "wall"))
    t.add("North arrow", text("north_label", ax, ay - 33, "N", 9, bold=True))

    n_det = rdraw.emit(t, v, model, path, model.get("_details_draw")) if (model.get("details") or model.get("markers")) else 0
    if n_det:
        print(f"region details drawn: {n_det} items")
    wf = place.get("window_ft") or [0, 0, bw, bh]
    b = clip_poly([(wf[0], wf[1]), (wf[2], wf[1]), (wf[2], wf[3]), (wf[0], wf[3])], v.x0, v.y0, v.x1, v.y1)
    if b:
        t.add("Bounds", path("bounds_place", v.d([b]), "guide-line"))
    t.add("Bounds", path("bounds_view", v.d([[(v.x0, v.y0), (v.x1, v.y0), (v.x1, v.y1), (v.x0, v.y1)]]), "wall"))

    # NOTES
    t.add("NOTES", text("note_title", 36, 22, title, 11, bold=True, anchor="start"))
    t.add("NOTES", text("note_status", 36, 34, "DRAFT - every entity is PROPOSED (no canon layout). * = proposed. Dashed strokes = proposed.", 7, anchor="start"))
    t.add("NOTES", text("note_regen", W - 36, 22, "GEN layers are rewritten on regeneration; draw in ART layers.", 7, anchor="end"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    t.write(out_path)
    cj = out_path + ".curved.json"
    if lst.CURVED["mode"] == "host" and lst.CURVED["items"]:
        with open(cj, "w", encoding="utf-8") as f_:
            json.dump({"svg": os.path.basename(out_path), "items": lst.CURVED["items"]}, f_)
        print(f"curved labels: {len(lst.CURVED['items'])} street/river names on a path -> {cj}")
    elif os.path.exists(cj):
        os.remove(cj)
    print("wrote", out_path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--label-offset", dest="label_offset", action="store_true", default=None,
                    help="offset labels with leader lines when the shape is too small (default from view_settings, on)")
    ap.add_argument("--no-label-offset", dest="label_offset", action="store_false")
    ap.add_argument("--leader-style", choices=["straight", "elbow"])
    ap.add_argument("--leader-width", type=float, help="leader stroke width (pt)")
    ap.add_argument("--label-fit-margin", type=float, help="spare room (percent) the text needs to stay inside its shape")
    ap.add_argument("--label-max-offset", type=float, help="max distance (page pt) outside the shape")
    ap.add_argument("--leader-dot", dest="leader_dot", action="store_true", default=None)
    ap.add_argument("--no-leader-dot", dest="leader_dot", action="store_false")
    ap.add_argument("--label-preset", help="named preset from presets/label_presets.json (label_style + label_offset + declutter)")
    ap.add_argument("--declutter", help="declutter options as JSON text or @file (see label_declutter.py DEFAULT)")
    ap.add_argument("--declutter-b64", help="same as --declutter, base64 of the JSON (used by the panel)")
    ap.add_argument("--no-declutter", action="store_true", help="legacy behaviour: no tiers, scale visibility or scoring")
    ap.add_argument("--leader-color", help="leader colour (default white)")
    ap.add_argument("--leader-b64", help="more leader options (casing, casing_color, casing_width, dot_ring, match_text, dash, lock_leaders) as base64 JSON (panel)")
    ap.add_argument("--label-style", help="label styling as JSON text or @file (see label_style.py): fonts, wrapping, halo/box/mask")
    ap.add_argument("--label-style-b64", help="same as --label-style, base64 of the JSON (used by the panel)")
    ap.add_argument("--view", default="town", help="town | bowl | street:<id> | building:<id>")
    ap.add_argument("--preset", help="view_settings preset (default follows --view)")
    ap.add_argument("--scale", type=float, help="feet per paper inch (overrides the preset)")
    ap.add_argument("--grid", type=float, help="minor grid in feet")
    ap.add_argument("--grid-major", type=int, help="major grid every N minor lines")
    ap.add_argument("--page", help="page size in inches, e.g. 17x11")
    ap.add_argument("--grid-full-page", action="store_true", help="draw the grid over the whole page (default: only inside the map window / place bounds)")
    ap.add_argument("--out")
    ap.add_argument("--terrain", action="store_true", help="regenerate heightmap + hillshade preview, overlay contours")
    ap.add_argument("--contours", action="store_true", help="overlay contours and elevation labels")
    ap.add_argument("--contour-mask", dest="mask", action="store_true", default=None,
                    help="subtract building footprints + street polygons from contours")
    ap.add_argument("--no-contour-mask", dest="mask", action="store_false")
    ap.add_argument("--contour-interval", type=float, default=10.0)
    ap.add_argument("--index-interval", type=float, default=50.0)
    ap.add_argument("--label-size", type=float, default=6.0)
    ap.add_argument("--units", choices=["ft", "m"], default="ft")
    ap.add_argument("--label-decimals", type=int, default=0)
    ap.add_argument("--label-spacing", type=float, default=500.0, help="target feet between labels on one contour")
    ap.add_argument("--min-contour-len", type=float, default=120.0, help="drop contour pieces shorter than this (ft)")
    ap.add_argument("--no-follow-line", action="store_true", help="horizontal labels instead of along the line")
    ap.add_argument("--no-upright", action="store_true", help="allow upside-down labels")
    ap.add_argument("--no-labels", action="store_true", help="contours only")
    ap.add_argument("--no-datum", action="store_true", help="do not emphasise the datum contour")
    ap.add_argument("--no-contour-halo", action="store_true", help="plain contour lines, no casing / no tone-by-shading")
    ap.add_argument("--contour-shading", default="auto", help="phase preset used to pick contour colour/casing per underlying shading luminance "
                    "(auto = the default calm preset, none = ignore shading)")
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"],
                    help="which heightmap to read (default: panel_state / auto = patched, or carved when water.use_carved)")
    ap.add_argument("--water-source", choices=["world", "working"])
    ap.add_argument("--fit", choices=["buildings", "area", "all"], help="frame the page on the built-up area: scale (next nice value) and centre follow the bounds of the buildings+streets, "
                    "the town_params area lasso, or the whole place (an explicit --scale is kept)")
    ap.add_argument("--curved-text", choices=["host", "svg"], default="host", help="street/river names on a curve: host = straight fallback in the SVG + <svg>.curved.json for host.jsx "
                    "(real type on a path in Illustrator, no import dialog); svg = <textPath> in the SVG (Illustrator flattens it and shows a dialog)")
    ap.add_argument("--fit-margin", type=float, default=0.0, help="extra feet around the --fit bounds")
    ap.add_argument("--details", help="region details to DRAW: auto (default; no lots at <=20 ft/in) | all | none | comma list of doors,roofs,chimneys,lots,fences,kerbs,trees")
    ap.add_argument("--model-dir", help="read the town model from this folder instead of world/<place> (candidate)")
    a = ap.parse_args()
    worldio.set_source(a.terrain_source, a.water_source)
    topts = None
    if a.terrain or a.contours:
        troot = os.path.join(REPO, "world", a.place)
        if a.terrain or not os.path.exists(os.path.join(troot, "terrain", "heightmap.npy")):
            hm, meta = tr.generate(tr.load_spec(os.path.join(troot, "terrain_spec.json")), verbose=True)
            tr.save(hm, meta, os.path.join(troot, "terrain"))
            tr.save_preview(hm, meta, os.path.join(REPO, "illustrator", "out", f"{a.place}_height.png"))
        use_mask = a.mask if a.mask is not None else viewcfg.load_raw(a.place).get("contour_mask", {}).get("enabled", True)
        topts = {"minor": a.contour_interval, "index": a.index_interval, "label_size": a.label_size,
                 "units": a.units, "use_mask": use_mask, "decimals": a.label_decimals,
                 "label_spacing_ft": a.label_spacing, "min_len_ft": a.min_contour_len,
                 "follow_line": not a.no_follow_line, "upright": not a.no_upright, "labels": not a.no_labels,
                 "emphasize_datum": not a.no_datum, "halo": not a.no_contour_halo, "shade_luma": a.contour_shading}
    suffix = "terrain" if topts and a.view == "town" else a.view.replace(":", "_")
    out = a.out or os.path.join(REPO, "illustrator", "out", f"{a.place}_{suffix}.svg")
    lopts = {"enabled": a.label_offset, "style": a.leader_style, "stroke_width": a.leader_width,
             "margin_pct": a.label_fit_margin, "max_offset_pt": a.label_max_offset, "dot": a.leader_dot}
    if a.leader_b64:
        lopts = {**json.loads(base64.b64decode(a.leader_b64).decode("utf-8")), **{k_: v_ for k_, v_ in lopts.items() if v_ is not None}}
    if a.leader_color:
        lopts["color"] = a.leader_color
    pre = ld.preset(a.label_preset) if a.label_preset else {}
    lopts = {**viewcfg.label_offset(a.place), **pre.get("label_offset", {}), **{k_: v_ for k_, v_ in lopts.items() if v_ is not None}}
    dcli = [ld.parse_cli(a.declutter), json.loads(base64.b64decode(a.declutter_b64).decode("utf-8")) if a.declutter_b64 else {}]
    if a.no_declutter:
        dcli.append({"enabled": False})
    dopts = ld.merge(viewcfg.declutter(a.place), pre.get("declutter"), *dcli)
    lst.curved_begin(a.curved_text)
    model_ = load_place(a.place, a.model_dir)
    model_["_details_draw"] = a.details
    render(model_, a.view, out, topts,
           {"preset": a.preset, "scale": a.scale, "grid": a.grid, "page": a.page, "major_every": a.grid_major, "grid_extent": "page" if a.grid_full_page else None, "fit": a.fit, "fit_margin": a.fit_margin}, lopts,
           [pre.get("label_style"), lst.parse_cli(a.label_style), lst.decode_b64(a.label_style_b64)], dopts)
