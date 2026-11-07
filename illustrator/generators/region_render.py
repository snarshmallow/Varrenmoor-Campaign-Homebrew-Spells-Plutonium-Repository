"""Render a region child (see REGIONS.md) with the normal pipeline at district scale, and write the Illustrator job.

  python illustrator/generators/region_render.py --child ID [--out-dir DIR] [--name PREFIX] [--scale 20] [--grid 5] [--page WxH]
        [--contour-interval 2] [--index-interval 10] [--no-contours] [--no-fills] [--shading PRESET|none] [--dpi 120] [--style full_map]
        [--max-fill-px 36000000] [--label-style-b64 B64] [--job] [--job-id ID] [--png-scale 100] [-- extra render_world args]

Steps: render_world.py (--view region, contours at the finer interval, labels) -> SVG; shading.py --window (only the page window, never the
whole padded frame); fills_raster.py at a dpi capped so the raster stays under --max-fill-px (memory); then ONE final JSON line with
the files and the host actions (place_svg open, place_image per raster layer below LINES, save_ai, export_png). With --job the actions are
written to illustrator/jobs/<id>.json (the open panel polls that folder). An existing .ai is never overwritten (a numeric suffix is added).
"""
import argparse
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldio  # noqa: E402

REPO = worldio.REPO
FILL_ORDER = ["ART - Shading", "ART - Fill Shapes", "ART - Fill Fields", "ART - Fill Water", "ART - Fill Streets", "ART - Fill Buildings",
              "ART - Shadows", "ART - Light Glow"]


def run(script, args):
    print("> " + os.path.basename(script) + " " + " ".join(args), flush=True)
    r = subprocess.run([sys.executable, "-X", "utf8", os.path.join(HERE, script)] + args, capture_output=True, text=True, encoding="utf-8")
    for line in (r.stdout or "").splitlines():
        print("  " + line, flush=True)
    if r.returncode != 0:
        print((r.stderr or "").strip()[-1500:], file=sys.stderr)
        raise SystemExit(f"{script} failed (exit {r.returncode})")


def free_path(p):
    base, ext = os.path.splitext(p)
    n, q = 1, p
    while os.path.exists(q):
        n += 1
        q = f"{base}_{n}{ext}"
    return q


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--child", required=True)
    ap.add_argument("--out-dir")
    ap.add_argument("--name")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--page")
    ap.add_argument("--contour-interval", type=float, default=2.0)
    ap.add_argument("--index-interval", type=float, default=10.0)
    ap.add_argument("--no-contours", action="store_true")
    ap.add_argument("--no-fills", action="store_true")
    ap.add_argument("--shading", default="temperate_valley_calm")
    ap.add_argument("--dpi", type=float, default=120.0)
    ap.add_argument("--style", default="full_map")
    ap.add_argument("--max-fill-px", type=float, default=36e6)
    ap.add_argument("--label-style-b64")
    ap.add_argument("--job", action="store_true")
    ap.add_argument("--job-id")
    ap.add_argument("--png-scale", type=float, default=100.0)
    a, extra = ap.parse_known_args(argv)
    extra = [x for x in extra if x != "--"]
    import render_world as rw
    child = a.child
    prefix = a.name or "region_" + child.replace("/", "_")
    out = os.path.abspath(a.out_dir or os.path.join(REPO, "illustrator", "out", prefix + "_files"))
    os.makedirs(out, exist_ok=True)
    cfg = {"preset": None, "scale": a.scale, "grid": a.grid, "page": a.page}
    model = rw.load_place(child)
    v, vcfg, title, kind, ident = rw.compute_view(model, "region", cfg)
    vflags = ["--view", "region"] + (["--scale", str(a.scale)] if a.scale else []) + (["--grid", str(a.grid)] if a.grid else []) + (["--page", a.page] if a.page else [])
    svg = os.path.join(out, prefix + ".svg")
    rargs = ["--place", child] + vflags + ["--out", svg]
    if not a.no_contours:
        rargs += ["--contours", "--contour-interval", str(a.contour_interval), "--index-interval", str(a.index_interval), "--label-spacing", "150",
                  "--min-contour-len", "30"]
    if a.label_style_b64:
        rargs += ["--label-style-b64", a.label_style_b64]
    run("render_world.py", rargs + extra)
    win = [v.x0, v.y0, v.x1, v.y1]
    wft, hft = v.x1 - v.x0, v.y1 - v.y0
    layers = []
    m = v.margin * 72
    k = v.k
    rect_of = lambda b: [m + (b["x_min"] - v.x0) * k, m + (b["y_min"] - v.y0) * k, m + (b["x_max"] - v.x0) * k, m + (b["y_max"] - v.y0) * k]  # noqa: E731
    ppf_cap = math.sqrt(a.max_fill_px / (wft * hft))
    dpi = min(a.dpi, ppf_cap * v.fpi)
    if dpi < a.dpi:
        print(f"fill dpi lowered {a.dpi:g} -> {dpi:.0f} to keep the raster under {a.max_fill_px:.3g} px")
    if a.shading and a.shading != "none":
        png = os.path.join(out, prefix + "_shading.png")
        run("shading.py", ["--place", child, "--phases", a.shading, "--scale-ft-per-in", str(v.fpi), "--dpi", str(dpi), "--out", png, "--hillshade",
                           "--window", ",".join(f"{x:.2f}" for x in win)])
        info = json.load(open(os.path.splitext(png)[0] + ".json"))
        layers.append({"path": png, "rect": rect_of(info["bounds_ft"]), "layer": "ART - Shading", "name": "shading_png"})
    if not a.no_fills:
        fd = os.path.join(out, prefix + "_fills")
        run("fills_raster.py", ["--place", child] + vflags + ["--out-dir", fd, "--style", a.style, "--dpi", str(dpi)])
        info = json.load(open(os.path.join(fd, "fills.json")))
        for L in info["layers"]:
            layers.append({"path": os.path.join(fd, L["png"]), "rect": rect_of(info["bounds_ft"]), "layer": L["layer"], "name": L["name"]})
    layers.sort(key=lambda L: FILL_ORDER.index(L["layer"]) if L["layer"] in FILL_ORDER else 99)
    ai = free_path(os.path.join(out, prefix + ".ai"))
    png_out = free_path(os.path.join(out, prefix + ".png"))
    rel = lambda p: os.path.relpath(p, REPO).replace("\\", "/")  # noqa: E731
    actions = [{"action": "place_svg", "path": rel(svg), "mode": "open"}]
    for L in layers:
        actions.append({"action": "place_image", "path": rel(L["path"]), "rect": [round(x, 3) for x in L["rect"]], "layer": L["layer"], "below": "LINES",
                        "name": L["name"], "lock": True})
    actions += [{"action": "save_ai", "path": rel(ai)}, {"action": "export_png", "path": rel(png_out), "scale": a.png_scale}]
    jid = a.job_id or prefix
    res = {"ok": True, "child": child, "svg": svg, "scale_ft_per_in": v.fpi, "page_in": list(v.page), "window_ft": win, "fill_dpi": dpi,
           "ai": ai, "png": png_out, "layers": [L["layer"] for L in layers], "job": {"id": jid, "actions": actions}}
    if a.job:
        jd = os.path.join(REPO, "illustrator", "jobs")
        os.makedirs(jd, exist_ok=True)
        jp = os.path.join(jd, jid + ".json")
        json.dump(res["job"], open(jp, "w"), indent=1)
        res["job_file"] = jp
        print("wrote job", jp)
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        if e.code not in (0, None):
            print(json.dumps({"ok": False, "error": str(e.code)}))
            sys.exit(1)
        raise
