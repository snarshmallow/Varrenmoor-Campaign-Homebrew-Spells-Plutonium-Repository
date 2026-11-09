"""Headless render of any place (no Illustrator): line art + terrain shading + fills -> one PNG, and optionally the Illustrator job.

  python illustrator/generators/place_render.py --place ID [--view town|bowl] [--out-dir DIR] [--name PREFIX] [--scale FT_PER_IN] [--dpi 110]
        [--shading PRESET] [--style full_map] [--no-fills] [--no-contours] [--job] [--max-fill-px 30000000]

Same steps as region_render.py (render_world SVG -> shading.py --window -> fills_raster -> svg_raster) but for a whole place and its own defaults
(place.json defaults.shading_preset / fills_style). Last stdout line: JSON with the files and the host actions (place_svg open, place_image per
raster layer, save_ai, export_png); --job writes them to illustrator/jobs/<name>.json for the panel.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import region_render as rr  # noqa: E402
import worldio  # noqa: E402

REPO = worldio.REPO


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--place", required=True)
    ap.add_argument("--view", default="town")
    ap.add_argument("--out-dir")
    ap.add_argument("--name")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--dpi", type=float, default=110.0)
    ap.add_argument("--png-dpi", type=float, default=110.0)
    ap.add_argument("--shading")
    ap.add_argument("--style")
    ap.add_argument("--label-preset")
    ap.add_argument("--no-grid", action="store_true", help="draw no grid at all (default: the place's view_settings.json grid_show)")
    ap.add_argument("--no-fills", action="store_true")
    ap.add_argument("--no-contours", action="store_true")
    ap.add_argument("--max-fill-px", type=float, default=30e6)
    ap.add_argument("--job", action="store_true")
    ap.add_argument("--png-scale", type=float, default=100.0)
    a = ap.parse_args(argv)
    import render_world as rw
    pj = json.load(open(os.path.join(REPO, "world", a.place, "place.json"), encoding="utf-8"))
    dfl = pj.get("defaults", {})
    imp = pj.get("import") or {}
    underlay = os.path.join(REPO, "world", a.place, imp["underlay"]) if imp.get("underlay") and os.path.exists(os.path.join(REPO, "world", a.place, imp["underlay"])) else None
    flat_import = False                  # imported scene with no background and no terrain (flat stub heightmap): a plain flat sheet, no all-over shading PNG
    if imp and not underlay:
        try:
            flat_import = json.load(open(os.path.join(REPO, "world", a.place, "terrain", "terrain_meta.json"), encoding="utf-8")).get("pipeline") == "flat_stub"
        except (OSError, ValueError):
            flat_import = False
    try:                                 # a flat stub heightmap has nothing to contour (contouring a huge flat sheet takes minutes): skip contours for imports
        if imp and json.load(open(os.path.join(REPO, "world", a.place, "terrain", "terrain_meta.json"), encoding="utf-8")).get("pipeline") == "flat_stub":
            a.no_contours = True
    except (OSError, ValueError):
        pass
    shading = a.shading or ("none" if (underlay or flat_import) else dfl.get("shading_preset")) or "alpine_steep_calm"
    style = a.style or dfl.get("fills_style") or "full_map"
    prefix = a.name or f"{a.place}_{a.view}"
    out = os.path.abspath(a.out_dir or os.path.join(REPO, "illustrator", "out", prefix + "_files"))
    os.makedirs(out, exist_ok=True)
    model = rw.load_place(a.place)
    cfg = {"preset": None, "scale": a.scale, "grid": None, "page": None, "grid_show": False if a.no_grid else None}
    v, vcfg, title, kind, ident = rw.compute_view(model, a.view, cfg)
    vflags = ["--view", a.view] + (["--scale", str(a.scale)] if a.scale else [])
    svg = os.path.join(out, prefix + ".svg")
    rargs = ["--place", a.place] + vflags + (["--no-grid"] if a.no_grid else []) + ["--out", svg, "--label-preset", a.label_preset or dfl.get("label_preset", "working")]
    if not a.no_contours:
        rargs += ["--contours"]
    rr.run("render_world.py", rargs)
    win = [v.x0, v.y0, v.x1, v.y1]
    wft, hft = v.x1 - v.x0, v.y1 - v.y0
    m, k = v.margin * 72, v.k
    rect_of = lambda b: [m + (b["x_min"] - v.x0) * k, m + (b["y_min"] - v.y0) * k, m + (b["x_max"] - v.x0) * k, m + (b["y_max"] - v.y0) * k]  # noqa: E731
    dpi = min(a.dpi, math.sqrt(a.max_fill_px / (wft * hft)) * v.fpi)
    layers = []
    if underlay:                          # an imported Foundry scene: its background image is the base layer (locked underlay in Illustrator)
        layers.append({"path": underlay, "rect": rect_of({"x_min": 0, "y_min": 0, "x_max": pj["bounds"]["width_ft"], "y_max": pj["bounds"]["height_ft"]}), "layer": "UNDERLAY", "name": "foundry_background"})
    if shading != "none":
        png = os.path.join(out, prefix + "_shading.png")
        rr.run("shading.py", ["--place", a.place, "--phases", shading, "--scale-ft-per-in", str(v.fpi), "--dpi", str(dpi), "--out", png, "--hillshade",
                              "--window=" + ",".join(f"{x:.2f}" for x in win)])   # "=" form: a window starting with a negative number is otherwise read as an option
        info = json.load(open(os.path.splitext(png)[0] + ".json"))
        layers.append({"path": png, "rect": rect_of(info["bounds_ft"]), "layer": "ART - Shading", "name": "shading_png"})
    if not a.no_fills:
        fd = os.path.join(out, prefix + "_fills")
        rr.run("fills_raster.py", ["--place", a.place] + vflags + ["--out-dir", fd, "--style", style, "--dpi", str(dpi)])
        info = json.load(open(os.path.join(fd, "fills.json")))
        for L in info["layers"]:
            layers.append({"path": os.path.join(fd, L["png"]), "rect": rect_of(info["bounds_ft"]), "layer": L["layer"], "name": L["name"]})
    layers.sort(key=lambda L: rr.FILL_ORDER.index(L["layer"]) if L["layer"] in rr.FILL_ORDER else -1 if L["layer"] == "UNDERLAY" else 99)
    import svg_raster
    headless, size = svg_raster.rasterise(svg, os.path.join(out, prefix + ".png"), a.png_dpi, 2, "#faf7ee", [(L["path"], L["rect"]) for L in layers])
    print(f"headless PNG {headless} {size[0]}x{size[1]}px")
    def rel(p):
        try:
            return os.path.relpath(p, REPO).replace("\\", "/")
        except ValueError:                      # other drive: keep the absolute path
            return p.replace("\\", "/")
    ai = rr.free_path(os.path.join(out, prefix + ".ai"))
    # imported scene: rasters go beneath GUIDES (the bottom SVG layer) so the 5 ft grid stays visible above the underlay / shading, below lines and labels
    actions = [{"action": "place_svg", "path": rel(svg), "mode": "open"}]
    for L in layers:
        actions.append({"action": "place_image", "path": rel(L["path"]), "rect": [round(x, 3) for x in L["rect"]], "layer": L["layer"], "below": ["GUIDES", "LINES"] if imp else "LINES", "name": L["name"], "lock": True, "embed": True})
    actions += [{"action": "save_ai", "path": rel(ai)}, {"action": "export_png", "path": rel(os.path.join(out, prefix + "_ai.png")), "scale": a.png_scale}]
    res = {"ok": True, "place": a.place, "svg": svg, "png": headless, "scale_ft_per_in": v.fpi, "layers": [L["layer"] for L in layers], "ai": ai, "job": {"id": prefix, "actions": actions}}
    if a.job:
        jd = os.path.join(REPO, "illustrator", "jobs")
        os.makedirs(jd, exist_ok=True)
        jp = os.path.join(jd, prefix + ".json")
        json.dump(res["job"], open(jp, "w"), indent=1)
        res["job_file"] = jp
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
