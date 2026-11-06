"""Render a world/<place> JSON model to a layered SVG for Illustrator.

  python illustrator/generators/render_world.py [--place bridgehollow] [--view town|street:<id>|building:<id>] [--out PATH]
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
import terrain as tr  # noqa: E402
from xml.sax.saxutils import escape  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PAGE_W_IN, PAGE_H_IN, MARGIN_IN = 17, 11, 0.5

SPEC = [
    ("NOTES", []),
    ("LABELS", ["Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", ct.LAYER_LABELS]),
    ("ART - Top", []),
    ("ART - Fills", []),
    ("ART - Textures", []),
    ("ART - Masks", []),
    ("LINES", ["Walls", "Buildings", "Roads", "Water", ("Terrain", [ct.LAYER_MINOR, ct.LAYER_INDEX]), "Fences"]),
    ("GUIDES", ["Grid", "Scale bar", "North arrow", "Bounds"]),
]

CSS = """\
path { fill: none; }
.guide-line { fill: none; stroke: #7a7a7a; stroke-width: 0.35; }
.wall { fill: none; stroke: #000000; stroke-width: 1.25; }
.road { fill: none; stroke: #000000; stroke-width: 0.75; }
.water { fill: none; stroke: #1a4f8a; stroke-width: 0.75; }
.proposed { stroke-dasharray: 3 1.5; }
text { fill: #000000; stroke: none; font-family: Arial, sans-serif; }
""" + ct.CSS


# ------------------------------------------------------------------ model
def load_place(name):
    root = os.path.join(REPO, "world", name)
    rd = lambda f: json.load(open(os.path.join(root, f), encoding="utf-8"))
    m = {"place": rd("place.json"), "districts": rd("districts.json")["districts"],
         "streets": rd("streets.json")["streets"], "water": rd("water.json")["water"], "buildings": []}
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


# ------------------------------------------------------------------ view
class View:
    def __init__(self, fpi, cx, cy):
        self.fpi = fpi
        self.k = 72.0 / fpi                       # points per foot
        self.wf = (PAGE_W_IN - 2 * MARGIN_IN) * fpi   # window size in feet
        self.hf = (PAGE_H_IN - 2 * MARGIN_IN) * fpi
        self.x0, self.y0 = cx - self.wf / 2, cy - self.hf / 2
        self.x1, self.y1 = cx + self.wf / 2, cy + self.hf / 2

    def px(self, p):
        return (MARGIN_IN * 72 + (p[0] - self.x0) * self.k, MARGIN_IN * 72 + (p[1] - self.y0) * self.k)

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
def render(model, view_arg, out_path, topts=None):
    place = model["place"]
    bw, bh = place["bounds"]["width_ft"], place["bounds"]["height_ft"]
    kind, _, ident = view_arg.partition(":")
    streets = {s["id"]: s for s in model["streets"]}
    blds = {b["id"]: b for b in model["buildings"]}

    if kind == "town":
        v = View(place["scales"]["town"]["feet_per_inch"], *place["view_focus"]["town"])
        grid_ft, title = 100, f"{place['name']} - town view"
    elif kind == "street":
        if ident not in streets:
            sys.exit(f"unknown street id: {ident}")
        poly = entity_polygon(streets[ident])
        v = View(place["scales"]["street"]["feet_per_inch"], *centroid(poly))
        grid_ft, title = 20, f"{place['name']} - street: {streets[ident]['name']}"
    elif kind == "building":
        if ident not in blds:
            sys.exit(f"unknown building id: {ident}")
        v = View(place["scales"]["building"]["feet_per_inch"], *centroid(entity_polygon(blds[ident])))
        grid_ft, title = 5, f"{place['name']} - building: {blds[ident]['name']}"
    else:
        sys.exit("--view must be town, street:<id> or building:<id>")

    t = LayerTree(SPEC, PAGE_W_IN, PAGE_H_IN, css=CSS, locked=["GUIDES", "Grid", "Scale bar", "North arrow", "Bounds"])
    base = {"building": "wall", "street": "road", "bridge": "road", "road": "road", "river": "water"}

    def draw(layer, e, cls):
        poly = v.clip(entity_polygon(e))
        if not poly:
            return None
        c = cls + (" proposed" if e.get("status") == "proposed" else "")
        t.add(layer, path(e["id"], v.d([poly]), c))
        return poly

    # LINES
    for e in model["water"]:
        draw("Water", e, "water")
    for e in model["districts"]:
        draw("Terrain", e, "guide-line")
    for e in model["streets"]:
        draw("Roads", e, "wall" if e["kind"] == "bridge" else "road")
    for e in model["buildings"]:
        draw("Buildings", e, "wall")
        if kind == "building" and e["id"] == ident:
            for r in e.get("rooms", []):
                draw("Walls", r, "wall")
            for dr in e.get("doors", []):
                if "geometry" in dr:
                    draw("Walls", dr, "guide-line")

    # TERRAIN contours + elevation labels (heightmap from world/<place>/terrain/)
    if topts is not None:
        h, meta = tr.load_heightmap(place["id"])
        mask = []
        if topts["use_mask"]:
            from shapely.geometry import Polygon
            for e in model["buildings"] + model["streets"]:
                pg = entity_polygon(e)
                if len(pg) >= 3:
                    mask.append(Polygon(pg).buffer(0))
        frame = ct.Frame(v.x0, v.y0, v.x1, v.y1, v.k, MARGIN_IN * 72, MARGIN_IN * 72)
        cp = ct.ContourParams(minor=topts["minor"], index=topts["index"], font_size=topts["label_size"],
                              units=topts["units"], use_mask=topts["use_mask"])
        cs = ct.build(h, meta["cell_ft"], frame, cp, mask)
        ct.emit(t, cs)
        print(f"contours: {len(cs.pieces)} paths, {len(cs.labels)} labels, relief {meta['elev_min']:.0f}-{meta['elev_max']:.0f} ft")

    # LABELS
    def anchor(poly):
        return centroid(poly)

    lab = lambda layer, e, s, size, bold=False, rot=None: _label(t, v, layer, e, s, size, bold, rot)
    for e in model["districts"]:
        lab("Labels - Districts", e, e["name"].upper() if e["kind"] == "district" else e["name"], 9 if e["kind"] == "district" else 7, True)
    if kind in ("town", "street"):
        for e in model["streets"]:
            pts = e["geometry"]["points"]
            segs = list(zip(pts, pts[1:]))
            a, b = max(segs, key=lambda s: math.hypot(s[1][0] - s[0][0], s[1][1] - s[0][1]))
            mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            vertical = abs(b[1] - a[1]) > abs(b[0] - a[0])
            if v.inside(mid):
                # offset the label so it sits beside the road centerline
                off = e["geometry"]["width_ft"] / 2 + 5
                m2 = (mid[0] + (off if vertical else 0), mid[1] - (0 if vertical else off))
                x, y = v.px(m2)
                t.add("Labels - Streets", text(f"lbl_{e['id']}", x, y, e["name"] + " *", 6, rot=-90 if vertical else None))
    for e in model["buildings"]:
        if kind == "town" and e["kind"] == "house":
            continue
        if kind == "street" and e["kind"] == "house":
            continue
        size = 7 if kind != "building" else 10
        lab("Labels - Buildings", e, e["name"] + " *", size)
    # Labels - Rooms: empty until rooms exist
    if kind == "building":
        for r in blds[ident].get("rooms", []):
            lab("Labels - Rooms", r, r["name"], 8)

    # GUIDES
    k = v.k
    first_x = math.ceil(v.x0 / grid_ft) * grid_ft
    first_y = math.ceil(v.y0 / grid_ft) * grid_ft
    px0, py0 = v.px((v.x0, v.y0)); px1, py1 = v.px((v.x1, v.y1))
    segs = []
    x = first_x
    while x <= v.x1:
        sx = v.px((x, 0))[0]
        segs.append(f"M{sx:.2f},{py0:.2f} L{sx:.2f},{py1:.2f}")
        x += grid_ft
    y = first_y
    while y <= v.y1:
        sy = v.px((0, y))[1]
        segs.append(f"M{px0:.2f},{sy:.2f} L{px1:.2f},{sy:.2f}")
        y += grid_ft
    t.add("Grid", path(f"grid_{grid_ft}ft", " ".join(segs), "guide-line"))

    # scale bar: 5 segments, two rows of alternating rectangles drawn as 2 compound paths
    bar_ft = {100: 500, 20: 100, 5: 25}[grid_ft]
    seg_ft = bar_ft / 5.0
    bx, by, bh_pt = 36 + 4, 792 - 26, 5
    even, odd = [], []
    for i in range(5):
        x0 = bx + seg_ft * i * k
        r = f"M{x0:.2f},{by:.2f} L{x0 + seg_ft * k:.2f},{by:.2f} L{x0 + seg_ft * k:.2f},{by + bh_pt:.2f} L{x0:.2f},{by + bh_pt:.2f} Z"
        (even if i % 2 == 0 else odd).append(r)
    t.add("Scale bar", path("scalebar_a", " ".join(even), "wall"))
    t.add("Scale bar", path("scalebar_b", " ".join(odd), "guide-line"))
    for i in range(6):
        t.add("Scale bar", text(f"scalebar_t{i}", bx + seg_ft * i * k, by + 16, f"{seg_ft * i:g}", 7))
    t.add("Scale bar", text("scalebar_unit", bx + bar_ft * k + 10, by + 5, f"ft   (1 in = {v.fpi:g} ft)", 8, anchor="start"))

    ax, ay = 1224 - 60, 792 - 40
    t.add("North arrow", path("north_arrow", f"M{ax:.2f},{ay - 28:.2f} L{ax + 7:.2f},{ay + 6:.2f} L{ax:.2f},{ay:.2f} L{ax - 7:.2f},{ay + 6:.2f} Z", "wall"))
    t.add("North arrow", text("north_label", ax, ay - 33, "N", 9, bold=True))

    # Bounds: place bounds intersected with the view window
    b = clip_poly([(0, 0), (bw, 0), (bw, bh), (0, bh)], v.x0, v.y0, v.x1, v.y1)
    if b:
        t.add("Bounds", path("bounds_place", v.d([b]), "guide-line"))
    t.add("Bounds", path("bounds_view", v.d([[(v.x0, v.y0), (v.x1, v.y0), (v.x1, v.y1), (v.x0, v.y1)]]), "wall"))

    # NOTES
    t.add("NOTES", text("note_title", 36, 22, title, 11, bold=True, anchor="start"))
    t.add("NOTES", text("note_status", 36, 34, "DRAFT - every entity is PROPOSED (no canon layout). * = proposed. Dashed strokes = proposed.", 7, anchor="start"))
    t.add("NOTES", text("note_regen", 1224 - 36, 22, "GEN layers are rewritten on regeneration; draw in ART layers.", 7, anchor="end"))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    t.write(out_path)
    print("wrote", out_path)


def _label(t, v, layer, e, s, size, bold, rot):
    poly = entity_polygon(e)
    c = centroid(poly)
    if not v.inside(c):
        return
    x, y = v.px(c)
    t.add(layer, text(f"lbl_{e['id']}", x, y + size * 0.35, s, size, rot=rot, bold=bold))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--out")
    ap.add_argument("--terrain", action="store_true", help="regenerate heightmap + hillshade preview, overlay contours")
    ap.add_argument("--contours", action="store_true", help="overlay contours and elevation labels")
    ap.add_argument("--no-contour-mask", action="store_true", help="do not subtract buildings/streets from contours")
    ap.add_argument("--contour-interval", type=float, default=10.0)
    ap.add_argument("--index-interval", type=float, default=50.0)
    ap.add_argument("--label-size", type=float, default=6.0)
    ap.add_argument("--units", choices=["ft", "m"], default="ft")
    a = ap.parse_args()
    topts = None
    if a.terrain or a.contours:
        troot = os.path.join(REPO, "world", a.place)
        if a.terrain or not os.path.exists(os.path.join(troot, "terrain", "heightmap.npy")):
            hm, meta = tr.generate(tr.load_spec(os.path.join(troot, "terrain_spec.json")), verbose=True)
            tr.save(hm, meta, os.path.join(troot, "terrain"))
            tr.save_preview(hm, meta, os.path.join(REPO, "illustrator", "out", f"{a.place}_height.png"))
        topts = {"minor": a.contour_interval, "index": a.index_interval, "label_size": a.label_size,
                 "units": a.units, "use_mask": not a.no_contour_mask}
    suffix = "terrain" if topts and a.view == "town" else a.view.replace(":", "_")
    out = a.out or os.path.join(REPO, "illustrator", "out", f"{a.place}_{suffix}.svg")
    render(load_place(a.place), a.view, out, topts)
