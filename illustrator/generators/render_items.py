"""Render only a few roads to a small SVG for the panel's fast map edits (host action replace_items; no render_world run, no whole-layer replace).

  python illustrator/generators/render_items.py --place P --ids a,b [--gone c,d] [--before-file streets_before.json] [--neighbours]
      [--view town] [--preset P] [--scale F] [--grid G] [--major N] [--no-grid] [--page WxH]  |  [--view-file view.json]
      [--layers "Roads,Road Centerlines"] --out roads_items.svg

Items (same ids, classes and page mapping as render_world.py / road_edit.draw_svg, so they replace the old items in place):
  Roads             street outline <id> (all rings in one path; wider streets win at junctions, exactly like render_world.street_shapes)
  Road Centerlines  open centreline <id> (not for bridges)
--neighbours  also redraw every street whose outline touches one of the --ids (new geometry) or of the --ids / --gone (old geometry, from
              --before-file): the junction cuts of those neighbours change when a road is added, moved or deleted.
Prints JSON {svg, drawn:[ids in the svg], neighbours:[ids], skipped:[ids not in streets.json], layers}. Nothing is written to the world.
"""
import argparse
import json
import os
import sys
from types import SimpleNamespace

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render_world as rw  # noqa: E402
from lib_svg import LayerTree  # noqa: E402

LAYERS = ["Roads", "Road Centerlines"]


def view_of(a):
    if a.view_file:
        with open(a.view_file, encoding="utf-8") as f:
            return json.load(f)
    import panelio
    return panelio.cmd_view(SimpleNamespace(place=a.place, view=a.view, preset=a.preset, scale=a.scale, grid=a.grid, page=a.page, major=a.major, no_grid=a.no_grid))


def _buf(s, pad=0.5):
    from shapely.geometry import LineString
    g = s["geometry"]
    return LineString(g["points"]).buffer(float(g["width_ft"]) / 2 + pad, cap_style=2)


def neighbours(streets, ids, before=None, gone=()):
    """Street ids (not in ids) whose outline touches the new outline of an id, or the old outline of an id / gone id."""
    cur = {s["id"]: s for s in streets}
    old = {s["id"]: s for s in (before or [])}
    probes = [_buf(cur[i]) for i in ids if i in cur] + [_buf(old[i]) for i in list(ids) + list(gone) if i in old]
    if not probes:
        return []
    from shapely.ops import unary_union
    u = unary_union(probes)
    return sorted(s["id"] for s in streets if s["id"] not in ids and len(s["geometry"]["points"]) >= 2 and _buf(s, 0.0).intersects(u))


def render(model, view, ids, out, layers=LAYERS):
    k, m = float(view["k"]), float(view["margin_in"]) * 72.0
    x0, y0, x1, y1 = (float(view[c]) for c in ("x0", "y0", "x1", "y1"))
    px = lambda p: (m + (p[0] - x0) * k, m + (p[1] - y0) * k)  # noqa: E731
    pw, ph = (float(x) for x in view["page_in"])
    t = LayerTree([("Road Centerlines", []), ("LINES", ["Roads"])], pw, ph, css=rw.CSS)
    streets = {s["id"]: s for s in model["streets"]}
    shapes = rw.street_shapes(model["streets"]) if "Roads" in layers else {}
    drawn = []
    for sid in ids:
        e = streets.get(sid)
        if not e:
            continue
        hit = False
        if "Roads" in layers:
            rings = [r for r in (rw.clip_poly(r, x0, y0, x1, y1) for r in rw.shape_rings(shapes[sid])) if r]
            if rings:
                c = ("wall" if e["kind"] == "bridge" else "road") + (" proposed" if e.get("status") == "proposed" else "")
                d = " ".join("M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in map(px, r)) + " Z" for r in rings)
                t.add("Roads", rw.path(sid, d, c))
                hit = True
        if "Road Centerlines" in layers and e.get("kind") != "bridge" and len(e["geometry"]["points"]) >= 2:
            d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in map(px, e["geometry"]["points"]))
            t.add("Road Centerlines", f'<path id="{sid}" fill="none" stroke="#d6336c" stroke-width="1.5" d="{d}"/>')
            hit = True
        if hit:
            drawn.append(sid)
    os.makedirs(os.path.dirname(os.path.abspath(out)) or ".", exist_ok=True)
    t.write(out)
    return drawn


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--place", required=True)
    ap.add_argument("--ids", default="", help="comma list of street ids to draw (changed / added roads)")
    ap.add_argument("--gone", default="", help="comma list of deleted street ids (only used to find their neighbours)")
    ap.add_argument("--before-file", help="streets.json content before the edit (old geometry for --neighbours)")
    ap.add_argument("--neighbours", action="store_true", help="also redraw the streets touching the changed / deleted ones (junction cuts)")
    ap.add_argument("--layers", default=",".join(LAYERS), help="Roads and / or Road Centerlines")
    ap.add_argument("--view-file", help="panelio.py view json (else the view flags below)")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--major", type=int)
    ap.add_argument("--no-grid", action="store_true")
    ap.add_argument("--page")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    ids = [x for x in a.ids.split(",") if x.strip()]
    gone = [x for x in a.gone.split(",") if x.strip()]
    layers = [x.strip() for x in a.layers.split(",") if x.strip()]
    bad = [x for x in layers if x not in LAYERS]
    if bad:
        ap.error("unknown layer(s): " + ", ".join(bad) + " (only " + ", ".join(LAYERS) + ")")
    model = rw.load_place(a.place)
    before = None
    if a.before_file:
        with open(a.before_file, encoding="utf-8") as f:
            before = json.load(f).get("streets", [])
    nb = neighbours(model["streets"], ids, before, gone) if a.neighbours else []
    have = {s["id"] for s in model["streets"]}
    want = [i for i in ids if i in have] + nb
    drawn = render(model, view_of(a), want, a.out, layers)
    print(json.dumps({"svg": a.out, "drawn": drawn, "neighbours": nb, "skipped": [i for i in ids if i not in have], "layers": layers}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
