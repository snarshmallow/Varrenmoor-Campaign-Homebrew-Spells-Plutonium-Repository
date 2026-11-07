"""2D floor plan renderer for generated interiors (SVG + PNG, room scale: default 20 px/ft = 5 ft per 100 px = 5 ft/in at 100 dpi).

  render_building(building_json, out_prefix, px_per_ft=20)   one sheet per building, one panel per storey  -> <prefix>.png / .svg
  render_street(buildings, roads, out_prefix, px_per_ft)     ground floors in true map position            -> <prefix>.png / .svg
  render_place(place, out_dir, world_root, px_per_ft)        every building of a world place + the street sheet

Primitives are collected once and written to both SVG (text stays text, usable as an Illustrator layer) and PNG (Pillow).
"""
import json
import math
import os

from PIL import Image, ImageDraw, ImageFont

import interiors as I

C = {"bg": "#f4efe3", "wall": "#2b2622", "floor": "#e8dcc0", "part": "#3b332c", "win": "#7fb4d6", "door": "#6b4a2b", "stair": "#b9a47c", "ink": "#2b2622",
     "hole": "#d8cfba", "room": {"hall": "#ecdcb6", "common": "#ecdcb6", "kitchen": "#e6d2a8", "bedroom": "#dfe3cf", "storeroom": "#d9d0be", "shop": "#e9d9c0",
                                 "office": "#dfe0d0", "loft": "#e3d8b0", "landing": "#e6dcc4", "none": "#e8dcc0"},
     "fx": {"hearth": "#6e6a64", "table": "#9a7448", "bench": "#a98457", "shelf": "#7b5a3a", "bed": "#a45a5a", "chest": "#7b5a3a", "barrel": "#8a6a44", "crate": "#a8834f",
            "counter": "#9a7448", "workbench": "#8a6a44", "hay": "#cdb96e", "desk": "#9a7448"}}


class Sheet:
    def __init__(self, w, h):
        self.w, self.h, self.ops = int(w), int(h), []

    def poly(self, pts, fill=None, stroke=None, sw=1.0):
        self.ops.append(("poly", list(pts), fill, stroke, sw))

    def line(self, pts, color, sw, closed=False):
        self.ops.append(("line", list(pts), color, sw, closed))

    def text(self, p, s, size, color=C["ink"], anchor="middle"):
        self.ops.append(("text", p, s, size, color, anchor))

    def svg(self):
        o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}">', f'<rect width="{self.w}" height="{self.h}" fill="{C["bg"]}"/>']
        for op in self.ops:
            if op[0] == "poly":
                _, pts, fill, stroke, sw = op
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                o.append(f'<polygon points="{d}" fill="{fill or "none"}"' + (f' stroke="{stroke}" stroke-width="{sw:.1f}"' if stroke else "") + "/>")
            elif op[0] == "line":
                _, pts, color, sw, closed = op
                d = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
                tag = "polygon" if closed else "polyline"
                o.append(f'<{tag} points="{d}" fill="none" stroke="{color}" stroke-width="{sw:.1f}" stroke-linecap="butt"/>')
            else:
                _, p, s, size, color, anchor = op
                s = s.replace("&", "&amp;").replace("<", "&lt;")
                o.append(f'<text x="{p[0]:.1f}" y="{p[1]:.1f}" font-family="sans-serif" font-size="{size}" fill="{color}" text-anchor="{anchor}">{s}</text>')
        o.append("</svg>")
        return "\n".join(o)

    def png(self, path):
        im = Image.new("RGB", (self.w, self.h), C["bg"])
        dr = ImageDraw.Draw(im)
        for op in self.ops:
            if op[0] == "poly":
                _, pts, fill, stroke, sw = op
                dr.polygon(pts, fill=fill, outline=None)
                if stroke:
                    dr.line(pts + [pts[0]], fill=stroke, width=max(1, round(sw)), joint="curve")
            elif op[0] == "line":
                _, pts, color, sw, closed = op
                dr.line(pts + ([pts[0]] if closed else []), fill=color, width=max(1, round(sw)), joint="curve")
            else:
                _, p, s, size, color, anchor = op
                try:
                    f = ImageFont.load_default(size=int(size))
                except TypeError:
                    f = ImageFont.load_default()
                dr.text(p, s, fill=color, font=f, anchor="ms" if anchor == "middle" else "ls")
        im.save(path)


def _thick(a, b, t):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / L * t / 2, dx / L * t / 2
    return [(a[0] + nx, a[1] + ny), (b[0] + nx, b[1] + ny), (b[0] - nx, b[1] - ny), (a[0] - nx, a[1] - ny)]


def _door(sh, T, p, d, w, color=C["door"], ppf=20):
    """Door leaf + swing arc at world point p along wall direction d (unit)."""
    h = (p[0] - d[0] * w / 2, p[1] - d[1] * w / 2)
    n = (-d[1], d[0])
    free = (h[0] + d[0] * w, h[1] + d[1] * w)
    tip = (h[0] + n[0] * w, h[1] + n[1] * w)
    sh.line([T(h), T(tip)], color, max(2, ppf * 0.14))
    arc = []
    for k in range(0, 10):
        a = k / 9 * math.pi / 2
        c, s = math.cos(a), math.sin(a)
        arc.append(T((h[0] + w * (d[0] * c + n[0] * s), h[1] + w * (d[1] * c + n[1] * s))))
    sh.line(arc, "#9c8a6a", 1.2)
    return free


def draw_storey(sh, T, b, floor, ppf, ox=0, labels=True):
    """Draw one storey of building json b (needs b['polygon'] or geometry points, b['rooms'], b['layout'])."""
    lay = b["layout"]
    poly = (b.get("geometry") or {}).get("points") or b["polygon"]
    wt = I.WALL_T
    # floor fills
    for r in b["rooms"]:
        if r["floor"] == floor:
            sh.poly([T(p) for p in r["polygon"]], fill=C["room"].get(r.get("use", "none"), C["floor"]))
    # stair hole on upper floors
    for s in lay["stairs"]:
        if s["to_floor"] == floor:
            sh.poly([T(p) for p in s["hole"]], fill=C["hole"], stroke="#8a7c62", sw=1)
    # exterior wall ring (outer polygon minus rooms outline)
    from shapely.geometry import Polygon
    pg = Polygon(poly)
    inner = pg.buffer(-wt, join_style=2, mitre_limit=5.0)
    ring = pg.difference(inner)
    for g in (ring.geoms if hasattr(ring, "geoms") else [ring]):
        if g.geom_type == "Polygon":
            ext = [T(p) for p in list(g.exterior.coords)[:-1]]
            holes = [[T(p) for p in list(i.coords)[:-1]] for i in g.interiors]
            sh.poly(ext, fill=C["wall"])
            for h in holes:
                sh.poly(h, fill=C["room"]["none"])
    for r in b["rooms"]:
        if r["floor"] == floor:
            sh.poly([T(p) for p in r["polygon"]], fill=C["room"].get(r.get("use", "none"), C["floor"]))
    # stairs
    for s in lay["stairs"]:
        if s["from_floor"] == floor or s["to_floor"] == floor:
            pts = s["polygon"]
            sh.poly([T(p) for p in pts], fill=C["stair"], stroke=C["ink"], sw=1.2)
            a, e = s["start"], s["end"]
            L = math.dist(a, e) or 1
            d = ((e[0] - a[0]) / L, (e[1] - a[1]) / L)
            n = s["risers"] - 1
            for k in range(1, n):
                q = (a[0] + d[0] * L * k / n, a[1] + d[1] * L * k / n)
                nn = (-d[1], d[0])
                hw = s["width_ft"] / 2
                sh.line([T((q[0] - nn[0] * hw, q[1] - nn[1] * hw)), T((q[0] + nn[0] * hw, q[1] + nn[1] * hw))], "#7c6a48", 1.0)
            sh.line([T(a), T(e)], C["ink"], 1.6)
            tip = T(e)
            if s["from_floor"] == floor:
                nn = (-d[1], d[0])
                for sg in (-1, 1):
                    sh.line([tip, T((e[0] - d[0] * 0.9 + nn[0] * 0.5 * sg, e[1] - d[1] * 0.9 + nn[1] * 0.5 * sg))], C["ink"], 1.6)
                sh.text(T(((a[0] + e[0]) / 2, (a[1] + e[1]) / 2)), "UP", ppf * 0.45, C["ink"])
            else:
                sh.text(T(((a[0] + e[0]) / 2, (a[1] + e[1]) / 2)), "DN", ppf * 0.45, C["ink"])
    # fixtures
    for f in lay["fixtures"]:
        if f["floor"] != floor:
            continue
        sx, sy, _ = f["size_ft"]
        a = math.radians(f["angle_deg"])
        c, s_ = math.cos(a), math.sin(a)
        cx, cy = f["point"]
        pts = [(cx + x * c - y * s_, cy + x * s_ + y * c) for x, y in ((-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2))]
        sh.poly([T(p) for p in pts], fill=C["fx"].get(f["type"], "#999"), stroke=C["ink"], sw=0.8)
    # partitions
    doors = {d["id"]: d for d in b["doors"]}
    for w in lay["walls"]:
        if w["floor"] != floor:
            continue
        a, c = w["a"], w["b"]
        L = math.dist(a, c)
        d = ((c[0] - a[0]) / L, (c[1] - a[1]) / L)
        cuts = sorted((((doors[i]["point"][0] - a[0]) * d[0] + (doors[i]["point"][1] - a[1]) * d[1]), doors[i]["width_ft"]) for i in w["doors"])
        cur = 0.0
        for u, dw in cuts:
            if u - dw / 2 > cur:
                sh.poly([T(p) for p in _thick((a[0] + d[0] * cur, a[1] + d[1] * cur), (a[0] + d[0] * (u - dw / 2), a[1] + d[1] * (u - dw / 2)), I.PART_T)], fill=C["part"])
            cur = u + dw / 2
        if cur < L:
            sh.poly([T(p) for p in _thick((a[0] + d[0] * cur, a[1] + d[1] * cur), c, I.PART_T)], fill=C["part"])
        for i in w["doors"]:
            _door(sh, T, doors[i]["point"], d, doors[i]["width_ft"], ppf=ppf)
    # exterior doors and windows
    if floor == 0:
        for d in b["doors"]:
            if d["kind"] != "exterior":
                continue
            p = d["point"]
            nrm = d.get("facing") or [0, 1]
            L = math.hypot(*nrm) or 1
            dd = (-nrm[1] / L, nrm[0] / L)
            w = d["width_ft"]
            sh.poly([T(q) for q in _thick((p[0] - dd[0] * w / 2, p[1] - dd[1] * w / 2), (p[0] + dd[0] * w / 2, p[1] + dd[1] * w / 2), wt * 1.05)], fill=C["room"]["none"])
            sh.line([T((p[0] - dd[0] * w / 2, p[1] - dd[1] * w / 2)), T((p[0] + dd[0] * w / 2, p[1] + dd[1] * w / 2))], C["door"], max(2, ppf * 0.16))
    for w in lay["windows"]:
        if w["floor"] != floor:
            continue
        a = math.radians(w["angle_deg"])
        d = (math.cos(a), math.sin(a))
        p = w["point"]
        sh.poly([T(q) for q in _thick((p[0] - d[0] * w["width_ft"] / 2, p[1] - d[1] * w["width_ft"] / 2), (p[0] + d[0] * w["width_ft"] / 2, p[1] + d[1] * w["width_ft"] / 2), wt)], fill=C["win"], stroke=C["ink"], sw=0.8)
    if labels:
        from shapely.geometry import Polygon as P
        for r in b["rooms"]:
            if r["floor"] == floor:
                c = P(r["polygon"]).representative_point()
                sh.text(T((c.x, c.y - 0.2)), r["name"], ppf * 0.62, C["ink"])
                sh.text(T((c.x, c.y + 1.0)), f"{r['area_ft2']:.0f} sq ft", ppf * 0.48, "#6b6256")


def render_building(b, out_prefix, ppf=20.0, margin=3.0):
    poly = (b.get("geometry") or {}).get("points") or b["polygon"]
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    minx, miny, maxx, maxy = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
    floors = b["layout"]["floors"]
    pw, ph = (maxx - minx) * ppf, (maxy - miny) * ppf
    title_h = ppf * 2.6
    sh = Sheet(pw * floors + (floors - 1) * ppf, ph + title_h)
    for f in range(floors):
        ox = f * (pw + ppf)

        def T(p, ox=ox):
            return (ox + (p[0] - minx) * ppf, title_h + (p[1] - miny) * ppf)
        draw_storey(sh, T, b, f, ppf, ox)
        sh.text((ox + pw / 2, ppf * 1.7), f"{b.get('name', b['id'])}  -  {'Ground floor' if f == 0 else 'Floor ' + str(f + 1)}   (generated, not canon; north = up)", ppf * 0.8, C["ink"])
    # scale bar 10 ft
    sh.line([(ppf, sh.h - ppf * 0.8), (ppf * 11, sh.h - ppf * 0.8)], C["ink"], 3)
    sh.text((ppf * 6, sh.h - ppf * 1.1), "10 ft", ppf * 0.55, C["ink"])
    os.makedirs(os.path.dirname(os.path.abspath(out_prefix)), exist_ok=True)
    sh.png(out_prefix + ".png")
    with open(out_prefix + ".svg", "w", encoding="utf-8") as fh:
        fh.write(sh.svg())
    return sh


def render_street(buildings, out_prefix, ppf=10.0, roads=None, margin=15.0):
    xs = [p[0] for b in buildings for p in ((b.get("geometry") or {}).get("points") or b["polygon"])]
    ys = [p[1] for b in buildings for p in ((b.get("geometry") or {}).get("points") or b["polygon"])]
    minx, miny, maxx, maxy = min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin
    sh = Sheet((maxx - minx) * ppf, (maxy - miny) * ppf)

    def T(p):
        return ((p[0] - minx) * ppf, (p[1] - miny) * ppf)
    for r in roads or []:
        sh.poly([T(p) for p in r], fill="#d9d2c0")
    for b in buildings:
        draw_storey(sh, T, b, 0, ppf, 0, labels=ppf >= 14)
        if ppf < 14:
            from shapely.geometry import Polygon as P
            c = P((b.get("geometry") or {}).get("points") or b["polygon"]).centroid
            sh.text(T((c.x, c.y)), b["id"].split("_")[-1], ppf * 1.0, "#6b2a2a")
    sh.png(out_prefix + ".png")
    with open(out_prefix + ".svg", "w", encoding="utf-8") as fh:
        fh.write(sh.svg())
    return sh


def _load_place(place, world_root=None):
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.join(world_root or os.path.join(repo, "world"), place)
    bd = os.path.join(root, "buildings")
    out = []
    for f in sorted(os.listdir(bd)):
        if f.endswith(".json"):
            with open(os.path.join(bd, f), encoding="utf-8") as fh:
                b = json.load(fh)
            if b.get("layout") and b.get("rooms"):
                out.append(b)
    roads = []
    rp = os.path.join(root, "export", "entities", "roads.json")
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as fh:
            roads = [r["outline"] for r in json.load(fh)["items"] if r.get("outline")]
    return out, roads


def render_place(place, out_dir, world_root=None, ppf=20.0, street_ppf=10.0):
    bs, roads = _load_place(place, world_root)
    os.makedirs(out_dir, exist_ok=True)
    for b in bs:
        render_building(b, os.path.join(out_dir, b["id"] + "_plan"), ppf)
    if bs:
        render_street(bs, os.path.join(out_dir, place + "_street_plan"), street_ppf, roads)
    print(f"floor plans: {len(bs)} buildings -> {out_dir}")
