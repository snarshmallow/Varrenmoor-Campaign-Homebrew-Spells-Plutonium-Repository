"""Small helpers the Illustrator panel calls (all print one JSON object on stdout).

  python panelio.py textures                                   # presets/textures with mean colours (for fills / swatches)
  python panelio.py view --place P [--view town] [--preset ..] [--scale ..] [--grid ..] [--page 17x11] [--major N]
                                                               # window in feet + points-per-foot, to map page points <-> feet
  python panelio.py town-accept --place P [--candidate DIR]    # copy the candidate town model over world/<place>
  python panelio.py town-reject --place P [--candidate DIR]    # delete the candidate (the world model was never touched)
  python panelio.py status --place P                           # terrain/water sources (worldio.status)
"""
import argparse
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldio  # noqa: E402

REPO = worldio.REPO
ILL = os.path.join(REPO, "illustrator")
TEX_DIR = os.path.join(ILL, "presets", "textures")
MODEL_FILES = ("streets.json", "districts.json", "place.json", "town_gen_report.json")


def default_candidate(place):
    return os.path.join(ILL, "out", "panel", place, "town_candidate")


def cmd_textures(a):
    import numpy as np
    from PIL import Image
    out = []
    for f in sorted(os.listdir(TEX_DIR)) if os.path.isdir(TEX_DIR) else []:
        if not f.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        im = np.asarray(Image.open(os.path.join(TEX_DIR, f)).convert("RGB"), float)
        rgb = [int(round(v)) for v in im.reshape(-1, 3).mean(0)]
        out.append({"name": os.path.splitext(f)[0], "file": f, "rgb": rgb, "hex": "#%02x%02x%02x" % tuple(rgb)})
    return {"textures": out}


def cmd_view(a):
    import render_world as rw
    model = rw.load_place(a.place)
    v, cfg, title, kind, ident = rw.compute_view(model, a.view, {"preset": a.preset, "scale": a.scale, "grid": a.grid,
                                                                  "page": a.page, "major_every": a.major})
    return {"place": a.place, "view": a.view, "fpi": v.fpi, "k": v.k, "x0": v.x0, "y0": v.y0, "x1": v.x1, "y1": v.y1,
            "margin_in": v.margin, "page_in": list(v.page), "grid_ft": cfg["grid_ft"], "grid_major_every": cfg["grid_major_every"],
            "units": cfg.get("units", "ft"), "bounds_ft": [model["place"]["bounds"]["width_ft"], model["place"]["bounds"]["height_ft"]],
            "title": title}


def cmd_fit(a):
    """Framing for the page: {scale_ft_per_in, grid_ft, focus_ft, bounds_ft} that makes --what (buildings|area|all) fill the page.
    The panel stores scale/grid/focus in view_settings.json (preset) so every generator uses the same frame."""
    import render_world as rw
    import viewcfg
    what = a.what or "buildings"
    model = rw.load_place(a.place)
    cfg = viewcfg.load(a.place, a.preset or a.view, page=a.page)
    fb = rw.fit_bounds(model, what)
    pw, ph = cfg["page_in"]
    m = cfg.get("margin_in", 0.5)
    pad = float(a.fit_margin or 0.0)
    fw, fh = fb[2] - fb[0] + 2 * pad, fb[3] - fb[1] + 2 * pad
    need = max(fw / max(pw - 2 * m, 1e-6), fh / max(ph - 2 * m, 1e-6)) * 1.04
    fpi = rw._nice_fit(need)
    return {"what": what, "bounds_ft": [round(x, 1) for x in fb], "scale_ft_per_in": fpi, "grid_ft": max(viewcfg._nice(fpi), 5),
            "focus_ft": [round((fb[0] + fb[2]) / 2.0, 1), round((fb[1] + fb[3]) / 2.0, 1)], "page_in": [pw, ph],
            "area_ft2": round(fw * fh)}


def cmd_accept(a):
    cand = a.candidate or default_candidate(a.place)
    dst = os.path.join(REPO, "world", a.place)
    if not os.path.isdir(cand) or not os.path.exists(os.path.join(cand, "streets.json")):
        raise SystemExit(f"no candidate town model at {cand}")
    copied = []
    for f in MODEL_FILES:
        if os.path.exists(os.path.join(cand, f)):
            shutil.copy2(os.path.join(cand, f), os.path.join(dst, f))
            copied.append(f)
    bsrc, bdst = os.path.join(cand, "buildings"), os.path.join(dst, "buildings")
    if os.path.isdir(bsrc):
        os.makedirs(bdst, exist_ok=True)
        for f in os.listdir(bdst):
            if f.startswith("bld_") and f.endswith(".json"):
                os.remove(os.path.join(bdst, f))
        n = 0
        for f in os.listdir(bsrc):
            if f.endswith(".json"):
                shutil.copy2(os.path.join(bsrc, f), os.path.join(bdst, f))
                n += 1
        copied.append(f"buildings/ ({n})")
    pr = os.path.join(os.path.dirname(cand), "town_params_run.json")
    if os.path.exists(pr):
        shutil.copy2(pr, os.path.join(dst, "town_params.json"))
        copied.append("town_params.json")
    shutil.rmtree(cand, ignore_errors=True)
    return {"accepted": True, "copied": copied}


def cmd_reject(a):
    cand = a.candidate or default_candidate(a.place)
    existed = os.path.isdir(cand)
    shutil.rmtree(cand, ignore_errors=True)
    return {"rejected": True, "existed": existed}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["textures", "view", "fit", "town-accept", "town-reject", "status"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--major", type=int)
    ap.add_argument("--page")
    ap.add_argument("--candidate")
    ap.add_argument("--what", choices=["buildings", "area", "all"])
    ap.add_argument("--fit-margin", type=float, default=0.0)
    a = ap.parse_args(argv)
    f = {"textures": cmd_textures, "view": cmd_view, "fit": cmd_fit, "town-accept": cmd_accept, "town-reject": cmd_reject,
         "status": lambda a: worldio.status(a.place)}[a.cmd]
    print(json.dumps(f(a)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
