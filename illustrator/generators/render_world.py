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
import glob
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from lib_svg import LayerTree  # noqa: E402
import contours as ct  # noqa: E402
import viewcfg  # noqa: E402
import terrain as tr  # noqa: E402
import label_offset as lbo  # noqa: E402
import worldio  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PAGE_W_IN, PAGE_H_IN, MARGIN_IN = 17, 11, 0.5   # defaults; the active view_settings page/margin are used per render

SPEC = [
    ("NOTES", []),
    ("LABELS", ["Leaders", "Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", ct.LAYER_LABELS]),
    ("ART - Top", []),
    ("ART - Fills", []),
    ("ART - Textures", []),
    ("ART - Masks", []),
    ("LINES", ["Walls", "Buildings", "Blocks", "Roads", "Water", ("Terrain", [ct.LAYER_MINOR, ct.LAYER_INDEX]), "Fences"]),
    ("GUIDES", ["Grid", "Scale bar", "North arrow", "Bounds"]),
]

CSS = """\
path { fill: none; }
.guide-line { fill: none; stroke: #7a7a7a; stroke-width: 0.35; }
.guide-major { fill: none; stroke: #5a5a5a; stroke-width: 0.6; }
.field { fill: none; stroke: #5d7a3a; stroke-width: 0.4; }
.guide-major { fill: none; stroke: #5a5a5a; stroke-width: 0.6; }
.field { fill: none; stroke: #5d7a3a; stroke-width: 0.4; }
.wall { fill: none; stroke: #000000; stroke-width: 1.25; }
.road { fill: none; stroke: #000000; stroke-width: 0.75; }
.water { fill: none; stroke: #1a4f8a; stroke-width: 0.75; }
.proposed { stroke-dasharray: 3 1.5; }
text { fill: #000000; stroke: none; font-family: Arial, sans-serif; }
.leader { fill: none; stroke: #000000; }
.leader-dot { stroke: none; fill: #000000; }
""" + ct.CSS


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


def street_label(t, v, e, size, fpi):
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
    t.add("Labels - Streets", text(f"lbl_{e['id']}", x, y, e["name"] + " *", size, rot=ang))
    return x, y, e["name"] + " *", size, ang


def compute_view(model, view_arg, cfg_over=None):
    """-> (View, cfg, title, kind, ident). Shared by render() and panelio.py (page <-> feet conversion for the panel)."""
    place = model["place"]
    bw, bh = place["bounds"]["width_ft"], place["bounds"]["height_ft"]
    kind, _, ident = view_arg.partition(":")
    streets = {s["id"]: s for s in model["streets"]}
    blds = {b["id"]: b for b in model["buildings"]}
    o = cfg_over or {}
    cfg = viewcfg.load(place["id"], o.get("preset") or kind, scale=o.get("scale"), grid=o.get("grid"),
                       page=o.get("page"), major_every=o.get("major_every"))
    fpi, grid_ft, major_n = cfg["scale_ft_per_in"], cfg["grid_ft"], cfg["grid_major_every"]
    pw, ph = cfg["page_in"]
    margin = cfg["margin_in"]
    W, H = pw * 72.0, ph * 72.0

    focus = cfg.get("focus", "center")
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
        title = f"{place['name']} - {'whole bowl' if kind == 'bowl' else 'town view'}"
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


def render(model, view_arg, out_path, topts=None, cfg_over=None, lopts=None):
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

    t = LayerTree(SPEC, pw, ph, css=CSS, locked=["GUIDES", "Grid", "Scale bar", "North arrow", "Bounds"])

    def addpoly(layer, id_, poly, cls, status):
        poly = v.clip(poly)
        if not poly:
            return None
        c = cls + (" proposed" if status == "proposed" else "")
        t.add(layer, path(id_, v.d([poly]), c))
        return poly

    # LINES
    for e in model["water"]:
        addpoly("Water", e["id"], entity_polygon(e), "water", None)     # solid bank line: a dashed outline made the river read as a wide dashed band
    for e in model["districts"]:
        k = e["kind"]
        layer, cls = {"square": ("Roads", "road"), "field": ("Fences", "field"),
                      "block": ("Blocks", "guide-line")}.get(k, ("Terrain", "guide-line"))
        addpoly(layer, e["id"], entity_polygon(e), cls, e.get("status"))
    shapes = street_shapes(model["streets"])
    for e in model["streets"]:
        rings = [r for r in (v.clip(r) for r in shape_rings(shapes[e["id"]])) if r]
        if rings:
            c = ("wall" if e["kind"] == "bridge" else "road") + (" proposed" if e.get("status") == "proposed" else "")
            t.add("Roads", path(e["id"], v.d(rings), c))
    for e in model["buildings"]:
        addpoly("Buildings", e["id"], entity_polygon(e), "wall", e.get("status"))
        if kind == "building" and e["id"] == ident:
            for r in e.get("rooms", []):
                addpoly("Walls", r["id"], entity_polygon(r), "wall", r.get("status"))
            for dr in e.get("doors", []):
                if "geometry" in dr:
                    addpoly("Walls", dr["id"], entity_polygon(dr), "guide-line", dr.get("status"))

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
        cp = ct.ContourParams(minor=topts["minor"], index=topts["index"], font_size=topts["label_size"] * lf,
                              units=topts["units"], use_mask=topts["use_mask"],
                              sea_level_ft=float(meta.get("sea_level_ft", 0.0)),
                              **{k_: topts[k_] for k_ in ("decimals", "label_spacing_ft", "min_len_ft", "follow_line",
                                                          "upright", "labels", "emphasize_datum") if k_ in topts})
        cs = ct.build(h, meta["cell_ft"], frame, cp, mask)
        ct.emit(t, cs)
        print(f"contours: {len(cs.pieces)} paths, {len(cs.labels)} labels, relief {meta['elev_min']:.0f}..{meta['elev_max']:.0f} ft, "
              f"mask={'on (%d polygons)' % len(mask) if mask else 'off'}")

    # LABELS (closed shapes get an offset + leader when the text does not fit inside; see label_offset.py)
    lp = lbo.LabelParams.from_dict(lopts if lopts is not None else cfg.get("label_offset"))
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
    if cs is not None:
        for lb in cs.labels:
            w_, h_ = lbo.text_size(lb["text"], lb["size"])
            placer.add_fixed_box(lbo.text_box(lb["x"], lb["y"], w_, h_, lb["rot"]).buffer(1.0))
    layer_of = {}

    def lab(layer, e, s, size, bold=False, rot=None):
        pg = v.clip(entity_polygon(e))
        c = tuple(e["label_point"]) if e.get("label_point") else centroid(entity_polygon(e))
        if not pg or not v.inside(c):
            return
        layer_of[e["id"]] = (layer, bold, size)
        placer.add(e["id"], [v.px(q) for q in pg], s, size, bold, rot, point=v.px(c))

    for e in model["districts"]:
        if e["kind"] == "district":
            if kind != "building":
                lab("Labels - Districts", e, e["name"].upper(), ls(9), True)
        elif e["kind"] == "square":
            lab("Labels - Districts", e, e["name"], ls(7), True)
    if kind in ("town", "street", "bowl"):
        for e in model["streets"]:
            if kind == "bowl" and e["geometry"]["width_ft"] < 22 and e["kind"] != "road":
                continue
            r_ = street_label(t, v, e, ls(6), fpi)
            if r_:
                w_, h_ = lbo.text_size(r_[2], r_[3])
                placer.add_fixed_box(lbo.text_box(r_[0], r_[1], w_, h_, r_[4]).buffer(1.0))
    for e in model["buildings"]:
        if kind != "building" and e["kind"] in CIVIC_SKIP and fpi >= 40:
            continue
        lab("Labels - Buildings", e, e["name"] + " *", ls(7) if kind != "building" else 10)
    if kind == "building":
        for r in blds[ident].get("rooms", []):
            lab("Labels - Rooms", r, r["name"], 8)
    n_off = 0
    texts = {it.id: it.text for it in placer.items}
    for res in placer.solve():
        layer, bold, size = layer_of[res.id]
        t.add(layer, text(f"lbl_{res.id}", res.x, res.y, texts[res.id], size, rot=res.rot, bold=bold, anchor=res.anchor))
        if res.leader:
            n_off += 1
            for sv in lbo.leader_svg(res, lp.stroke_width):
                t.add("Leaders", sv)
    if lp.enabled:
        print(f"label offsets: {n_off} labels moved outside their shape with a leader")

    # GUIDES: minor + major grid
    k = v.k
    px0, py0 = v.px((v.x0, v.y0)); px1, py1 = v.px((v.x1, v.y1))
    minor, major = [], []
    major_ft = grid_ft * major_n
    nlines = (v.x1 - v.x0) / grid_ft + (v.y1 - v.y0) / grid_ft
    for axis, lo, hi in (("x", v.x0, v.x1), ("y", v.y0, v.y1)):
        g = math.ceil(lo / grid_ft)
        while g * grid_ft <= hi:
            pos = g * grid_ft
            q = v.px((pos, pos))
            seg = (f"M{q[0]:.2f},{py0:.2f} L{q[0]:.2f},{py1:.2f}" if axis == "x"
                   else f"M{px0:.2f},{q[1]:.2f} L{px1:.2f},{q[1]:.2f}")
            (major if major_n and g % major_n == 0 else minor).append(seg)
            g += 1
    if minor and nlines < 900:
        t.add("Grid", path(f"grid_{grid_ft:g}ft", " ".join(minor), "guide-line"))
    if major:
        t.add("Grid", path(f"grid_major_{major_ft:g}ft", " ".join(major), "guide-major"))

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

    b = clip_poly([(0, 0), (bw, 0), (bw, bh), (0, bh)], v.x0, v.y0, v.x1, v.y1)
    if b:
        t.add("Bounds", path("bounds_place", v.d([b]), "guide-line"))
    t.add("Bounds", path("bounds_view", v.d([[(v.x0, v.y0), (v.x1, v.y0), (v.x1, v.y1), (v.x0, v.y1)]]), "wall"))

    # NOTES
    t.add("NOTES", text("note_title", 36, 22, title, 11, bold=True, anchor="start"))
    t.add("NOTES", text("note_status", 36, 34, "DRAFT - every entity is PROPOSED (no canon layout). * = proposed. Dashed strokes = proposed.", 7, anchor="start"))
    t.add("NOTES", text("note_regen", W - 36, 22, "GEN layers are rewritten on regeneration; draw in ART layers.", 7, anchor="end"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    t.write(out_path)
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
    ap.add_argument("--view", default="town", help="town | bowl | street:<id> | building:<id>")
    ap.add_argument("--preset", help="view_settings preset (default follows --view)")
    ap.add_argument("--scale", type=float, help="feet per paper inch (overrides the preset)")
    ap.add_argument("--grid", type=float, help="minor grid in feet")
    ap.add_argument("--grid-major", type=int, help="major grid every N minor lines")
    ap.add_argument("--page", help="page size in inches, e.g. 17x11")
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
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"],
                    help="which heightmap to read (default: panel_state / auto = patched, or carved when water.use_carved)")
    ap.add_argument("--water-source", choices=["world", "working"])
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
                 "emphasize_datum": not a.no_datum}
    suffix = "terrain" if topts and a.view == "town" else a.view.replace(":", "_")
    out = a.out or os.path.join(REPO, "illustrator", "out", f"{a.place}_{suffix}.svg")
    lopts = {"enabled": a.label_offset, "style": a.leader_style, "stroke_width": a.leader_width,
             "margin_pct": a.label_fit_margin, "max_offset_pt": a.label_max_offset, "dot": a.leader_dot}
    lopts = {**viewcfg.label_offset(a.place), **{k: v_ for k, v_ in lopts.items() if v_ is not None}}
    render(load_place(a.place, a.model_dir), a.view, out, topts,
           {"preset": a.preset, "scale": a.scale, "grid": a.grid, "page": a.page, "major_every": a.grid_major}, lopts)
