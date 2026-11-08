"""Build the WINTER map layers (any place, default bridgehollow) and the Illustrator panel job for one view (bowl | town | z40).

  python illustrator/generators/winter_build.py bowl|town|z40 [--place ID] [--skip svg,fills,shading,light] [--name <place>_winter]

Writes (illustrator/out/):  <name>_<view>.svg (layered line art, label preset winter_legible, cool contour colours),
<name>_fills_<view>_fills/ (textured fills, style winter), <name>_shading_<view>.png (phase shading, preset alpine_winter / town_winter),
<name>_light_<view>/ (low winter sun shadows + warm window glow), and illustrator/jobs/winter_<view>.json (panel job: place the SVG, rasters
below LINES in the layer order  LINES > Fill Buildings > Streets > Water > Fields > Shading, shadows and glow above the fills, save .ai, export .png).
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ILL = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(ILL, ".."))
OUT = os.path.join(ILL, "out")
PY = sys.executable

def views(place):
    """view -> (render_world args, scale ft/in, shading window (ft) or None = whole terrain, shading dpi, fills dpi, shading preset).
    Windows come from the place size: the town window is the middle two thirds, z40 is 640 x 400 ft round view_focus.town (Bridgehollow: the old numbers)."""
    pj = json.load(open(os.path.join(REPO, "world", place, "place.json"), encoding="utf-8"))
    W, H = pj["bounds"]["width_ft"], pj["bounds"]["height_ft"]
    fx, fy = (pj.get("view_focus") or {}).get("town") or [W / 2, H / 2]
    town = (round(W / 6), round(H / 6), round(W * 5 / 6), round(H * 5 / 6))
    z40 = (round(fx - 320), round(fy - 200), round(fx + 320), round(fy + 200))
    return {
        "bowl": (["--view", "bowl"], 200, None, 200, 200, "alpine_winter"),
        "town": (["--view", "town"], 100, town, 200, 200, "town_winter"),
        "z40": (["--view", "town", "--scale", "40", "--grid", "20", "--grid-major", "5"], 40, z40, 150, 120, "town_winter"),
    }


CONTOUR_COLOURS = {"#7d5226": "#4d647e", "#6b4220": "#31465e", "#f6edd2": "#f4f8fd", "#6b4423": "#27415f"}

def glow_sources(place):
    """Warm window / lantern glow at the inn, smithy and civic buildings: [(id, x, y, strength)] from world/<place>/buildings (centre of the footprint)."""
    d = os.path.join(REPO, "world", place, "buildings")
    rows = []
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        e = json.load(open(os.path.join(d, fn), encoding="utf-8"))
        k = (e.get("kind") or "")
        w = {"inn": 1.0, "craft": 0.5, "civic": 0.6}.get(k)
        if w is None or e.get("id", "").endswith(("mill", "gate_watch")):
            continue
        pts = e["geometry"]["points"]
        rows.append((e["id"], round(sum(p[0] for p in pts) / len(pts)), round(sum(p[1] for p in pts) / len(pts)), w))
    return rows[:10]


def lighting_cfg(place):
    lights = [{"id": "sun", "type": "sun", "azimuth": 200.0, "altitude": 17.0, "color": "#dbe8ff", "intensity": 1.0, "softness": 0.7, "tint": 0.0}]
    for i, (bid, x, y, k) in enumerate(glow_sources(place)):
        lights.append({"id": f"glow_{bid}", "type": "point", "x": x, "y": y, "height": 34.0, "radius": 30.0, "color": "#ffb45a",
                       "intensity": 0.35 * k, "softness": 0.6})
    return {"enabled": True, "ambient": 0.42, "terrain_shade": 0.22, "terrain_smooth_ft": 12.0,
            "shadow": {"color": "#1a2a4c", "opacity": 0.36, "blur_ft": 0.8, "max_length_ft": 380.0, "terrain": False, "buildings": True},
            "glow": {"enabled": True, "opacity": 0.5}, "lights": lights}


def run(cmd):
    print("$", " ".join(cmd[1:]))
    r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8")
    sys.stdout.write(r.stdout[-3500:])
    if r.returncode:
        sys.stderr.write(r.stderr[-3000:])
        raise SystemExit(r.returncode)
    return r.stdout


def clip_to_terrain(light_dir, b, place="bridgehollow"):
    """The terrain (and so the shadow field) ends at the heightmap edge; fade the shadow / glow PNGs to nothing outside it (bowl view: the page margin)."""
    import numpy as np
    from PIL import Image
    meta = json.load(open(os.path.join(REPO, "world", place, "terrain", "terrain_meta.json"), encoding="utf-8"))
    W, H = meta["size_ft"]
    for fn in ("shadows.png", "light_glow.png"):
        p = os.path.join(light_dir, fn)
        im = Image.open(p).convert("RGBA")
        a = np.asarray(im).copy()
        ppf = a.shape[1] / (b["x_max"] - b["x_min"])
        xs = b["x_min"] + (np.arange(a.shape[1]) + 0.5) / ppf
        ys = b["y_min"] + (np.arange(a.shape[0]) + 0.5) / ppf
        m = ((xs >= 0) & (xs <= W))[None, :] & ((ys >= 0) & (ys <= H))[:, None]
        a[..., 3] = np.where(m, a[..., 3], 0)
        Image.fromarray(a, "RGBA").save(p, dpi=im.info.get("dpi"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("view", choices=["bowl", "town", "z40"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--name", default=None)
    ap.add_argument("--skip", default="")
    ap.add_argument("--label-preset", default="winter_legible")
    ap.add_argument("--style", default="winter")
    ap.add_argument("--tag", default="", help="dev build: the job saves illustrator/out/winter/dev_<view>_<tag>.ai/.png instead of the final names")
    a = ap.parse_args()
    skip = set(a.skip.split(","))
    a.name = a.name or f"{a.place}_winter"
    rw_args, fpi, win, sdpi, fdpi, preset = views(a.place)[a.view]
    rw_args = ["--place", a.place] + rw_args
    v = a.view
    svg = os.path.join(OUT, f"{a.name}_{v}.svg")
    fills = os.path.join(OUT, f"{a.name}_fills_{v}_fills")
    shade = os.path.join(OUT, f"{a.name}_shading_{v}.png")
    light = os.path.join(OUT, f"{a.name}_light_{v}")
    g = lambda s: os.path.join(HERE, s)
    if "svg" not in skip:
        run([PY, g("render_world.py"), *rw_args, "--contours", "--label-preset", a.label_preset, "--contour-shading", preset, "--out", svg])
        t = open(svg, encoding="utf-8").read()
        for k, c in CONTOUR_COLOURS.items():
            t = t.replace(k, c)
        open(svg, "w", encoding="utf-8").write(t)
    if "fills" not in skip:
        run([PY, g("fills_raster.py"), *rw_args, "--style", a.style, "--fills-dpi", str(fdpi), "--out-dir", fills])
    info = json.load(open(os.path.join(fills, "fills.json")))
    b = info["bounds_ft"]
    if "shading" not in skip:
        cmd = [PY, g("shading.py"), "--place", a.place, "--phases", preset, "--scale-ft-per-in", str(fpi), "--dpi", str(sdpi), "--out", shade]
        if win:
            cmd += ["--window", ",".join(str(x) for x in win)]
        run(cmd)
    if "light" not in skip:
        os.makedirs(light, exist_ok=True)
        cfgp = os.path.join(light, "lighting_cfg.json")
        json.dump(lighting_cfg(a.place), open(cfgp, "w"), indent=1)
        run([PY, g("lighting.py"), *rw_args, "--config", cfgp, "--dpi", "150", "--out-dir", light])
        clip_to_terrain(light, b, a.place)
    # panel job
    sj = json.load(open(shade[:-4] + ".json"))
    sb = sj["bounds_ft"]
    px = lambda ft, o: 36.0 + (ft - o) / fpi * 72.0
    full = [36.0, 36.0, 36.0 + (b["x_max"] - b["x_min"]) / fpi * 72.0, 36.0 + (b["y_max"] - b["y_min"]) / fpi * 72.0]
    srect = [px(sb["x_min"], b["x_min"]), px(sb["y_min"], b["y_min"]), px(sb["x_max"], b["x_min"]), px(sb["y_max"], b["y_min"])]
    rel = lambda p: os.path.relpath(p, REPO).replace("\\", "/")

    def img(path, rect, layer, name):
        return {"action": "place_image", "path": rel(path), "rect": [round(x, 2) for x in rect], "layer": layer, "below": "LINES",
                "name": name, "lock": True, "embed": True}
    stem = f"winter/dev_{v}_{a.tag}" if a.tag else f"{a.name}_{v}"
    acts = [{"action": "place_svg", "path": rel(svg), "mode": "open"},
            img(shade, srect, "ART - Shading", "shading_png")]
    for cat, layer in (("fields", "ART - Fill Fields"), ("water", "ART - Fill Water"), ("streets", "ART - Fill Streets"), ("buildings", "ART - Fill Buildings")):
        acts.append(img(os.path.join(fills, f"fill_{cat}.png"), full, layer, f"fill_{cat}_png"))
    acts.append(img(os.path.join(light, "shadows.png"), full, "ART - Shadows", "shadows_png"))
    acts.append(img(os.path.join(light, "light_glow.png"), full, "ART - Light Glow", "light_glow_png"))
    acts += [{"action": "get_layer_tree"},
             {"action": "save_ai", "path": f"illustrator/out/{stem}.ai"},
             {"action": "export_png", "path": f"illustrator/out/{stem}.png", "scale": 200}]
    job = {"id": f"winter_{v}{'_' + a.tag if a.tag else ''}", "continue_on_error": False, "actions": acts}
    jp = os.path.join(OUT, "winter", f"job_{v}{a.tag}.json")
    os.makedirs(os.path.dirname(jp), exist_ok=True)
    json.dump(job, open(jp, "w"), indent=1)
    print("job written:", rel(jp), "(copy to illustrator/jobs/ to run)")


if __name__ == "__main__":
    main()
