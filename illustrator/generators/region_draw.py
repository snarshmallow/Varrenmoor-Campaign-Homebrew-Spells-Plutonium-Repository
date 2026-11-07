"""Drawing of region-child extras for render_world.py (details.json, markers.json): doors, roof ridges, chimneys, lots, fences, kerbs,
trees, continues-off-map arrows and the region outline. Kept out of render_world.py so that file only gets a hook.

  CSS                       extra classes
  LAYERS                    sublayers to add under LINES (Details, Vegetation)
  emit(t, v, model, path)   t = LayerTree, v = View, path(id, d, cls) = render_world.path
"""
import math

CSS = """\
.fence { fill: none; stroke: #6b4a2a; stroke-width: 0.7; stroke-dasharray: 2.2 1.2; }
.kerb { fill: none; stroke: #5a5a5a; stroke-width: 0.35; }
.lot { fill: none; stroke: #7a7a7a; stroke-width: 0.3; stroke-dasharray: 5 3; }
.roof { fill: none; stroke: #444444; stroke-width: 0.4; }
.chimney { fill: none; stroke: #000000; stroke-width: 0.5; }
.door { fill: none; stroke: #000000; stroke-width: 0.9; }
.tree { fill: none; stroke: #3d6b2a; stroke-width: 0.5; }
.offmap { fill: none; stroke: #b02020; stroke-width: 0.9; }
.region-outline { fill: none; stroke: #d4202a; stroke-width: 1.1; stroke-dasharray: 6 3; }
"""
LAYERS = ["Details", "Vegetation"]


def _near(v, pts):
    return any(v.x0 - 30 <= p[0] <= v.x1 + 30 and v.y0 - 30 <= p[1] <= v.y1 + 30 for p in pts)


def _poly(v, pts):
    q = [v.px(p) for p in pts]
    return "M" + " L".join("%.2f,%.2f" % p for p in q) + " Z"


def _line(v, pts):
    q = [v.px(p) for p in pts]
    return "M" + " L".join("%.2f,%.2f" % p for p in q)


def _circle(v, x, y, r, n=14):
    return _poly(v, [(x + r * math.cos(2 * math.pi * i / n), y + r * math.sin(2 * math.pi * i / n)) for i in range(n)])


def emit(t, v, model, path):
    D, M = model.get("details") or {}, model.get("markers") or {}
    n = 0
    for d in D.get("kerbs", []):
        if _near(v, d["geometry"]):
            t.add("Details", path(d["id"], _poly(v, d["geometry"]), "kerb")); n += 1
    for d in D.get("lots", []):
        if _near(v, d["geometry"]):
            t.add("Details", path(d["id"], _poly(v, d["geometry"]), "lot")); n += 1
    for d in D.get("roofs", []):
        if _near(v, d["ridge"]):
            t.add("Details", path(d["id"], _line(v, d["ridge"]), "roof")); n += 1
    for d in D.get("chimneys", []):
        if _near(v, d["geometry"]):
            t.add("Details", path(d["id"], _poly(v, d["geometry"]), "chimney")); n += 1
    for d in D.get("doors", []):
        px, py = d["point"]
        if not _near(v, [d["point"]]):
            continue
        fx, fy = d["facing"]
        tx, ty = -fy, fx
        hw = d["width_ft"] / 2.0
        a = [(px - tx * hw, py - ty * hw), (px + tx * hw, py + ty * hw)]
        b = [(px + tx * hw + fx * 1.4, py + ty * hw + fy * 1.4), (px - tx * hw + fx * 1.4, py - ty * hw + fy * 1.4)]
        t.add("Details", path(d["id"], _poly(v, a + b), "door")); n += 1
    for d in D.get("fences", []):
        if _near(v, d["points"]):
            t.add("Fences", path(d["id"], _line(v, d["points"]), "fence")); n += 1
    for d in D.get("trees", []):
        if _near(v, [(d["x"], d["y"])]):
            t.add("Vegetation", path(d["id"], _circle(v, d["x"], d["y"], d["r_ft"]) + " " + _circle(v, d["x"], d["y"], 0.5, 6), "tree")); n += 1
    for m in M.get("markers", []):
        if not _near(v, [m["point"]]):
            continue
        x, y = m["point"]
        dx, dy = m["dir"]
        nx, ny = -dy, dx
        w = m.get("width_ft", 16) / 2.0
        tip = (x + dx * 14, y + dy * 14)
        pts = [(x - nx * w * 0.6 + dx * 4, y - ny * w * 0.6 + dy * 4), tip, (x + nx * w * 0.6 + dx * 4, y + ny * w * 0.6 + dy * 4)]
        t.add("Bounds", path(m["id"], _line(v, pts), "offmap")); n += 1
    ro = M.get("region_outline")
    if ro and len(ro) >= 3:
        t.add("Bounds", path("region_outline", _poly(v, ro), "region-outline"))
    return n
