"""Import an existing Foundry scene as a place (READ-ONLY on Foundry: only `get` / `list` calls, nothing is written there).

  python illustrator/generators/foundry_push.py import-scene --scene-uuid Scene.xxxx [--place-id ID] [--include walls,lights,tokens,notes] [--no-image]
         [--closed-as buildings|lines] [--force] [--dry-run] [--scene-json FILE]

What it makes (world/<id>/, every file the pipeline expects, so render_world / shading / lighting / worldpack / foundry_push work with --place <id>):
  place.json             name, bounds (scene size in feet), links.foundry_scene = the scene uuid, `import` block (grid, scene px size, scene offset, source image, time)
  underlay/background.png (+ the original file)   the scene background, copied from the shared assets folder or downloaded; place it as a locked underlay
  walls.json / foundry_walls.json   Foundry walls as feet polylines (layer WALLS); closed loops become building outlines (default) or stay lines
  foundry_lights.json, foundry_tokens.json, foundry_notes.json   with --include
  terrain/ (a flat stub so every tool runs), districts.json, streets.json, water.json (empty), buildings/ (closed wall loops), view_settings.json
Calibration: pixels per foot = grid.size / grid.distance (ft; m, km, mi converted). Origin = the top-left of the scene rectangle (scene px (sceneX, sceneY)),
y down, so a later `push-scene` of this place lands on the same scene: `push-scene` with no --scene-uuid / --scene-name uses links.foundry_scene (the scene is
not pipeline-flagged, so it asks for --yes once, as for any scene the pipeline did not create).
"""
import json
import math
import os
import re
import shutil
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
UNIT_FT = {"ft": 1.0, "feet": 1.0, "foot": 1.0, "'": 1.0, "m": 3.28084, "meter": 3.28084, "meters": 3.28084, "metre": 3.28084, "metres": 3.28084, "km": 3280.84, "mi": 5280.0, "miles": 5280.0,
           "yd": 3.0, "yards": 3.0, "in": 1 / 12.0, "cm": 0.0328084}


def slug(s):
    return (re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "scene")[:40]


def jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


def background_src(sc):
    """Background image path of a scene across Foundry versions (v11 img, v12 background.src, v13/v14 levels[].background.src)."""
    for cand in ((sc.get("background") or {}).get("src"), sc.get("img")):
        if cand:
            return cand
    for lv in sc.get("levels") or []:
        s = (lv.get("background") or {}).get("src")
        if s:
            return s
    return None


def calibration(sc):
    g = sc.get("grid") or {}
    size = float(g.get("size") or 100)
    dist = float(g.get("distance") or 5)
    unit = str(g.get("units") or "ft").strip().lower()
    warn = None
    k = UNIT_FT.get(unit)
    if k is None:
        k, warn = 1.0, f"grid units {unit!r} not recognised: treated as feet"
    ppf = size / (dist * k)
    W, H = float(sc.get("width") or 0), float(sc.get("height") or 0)
    pad = float(sc.get("padding") or 0)
    # Foundry rounds the padding UP to whole grid squares (same rule as foundry_push.calibrate); python round() was banker's rounding and could be a square off
    sx = math.ceil(W * pad / size - 1e-9) * size if size else 0
    sy = math.ceil(H * pad / size - 1e-9) * size if size else 0
    if g.get("type") not in (None, 0, 1):
        warn = (warn + "; " if warn else "") + f"grid type {g.get('type')} is not square: imported as a square grid (hex scenes keep their size but not the hex layout)"
    return {"grid_px": size, "grid_dist": dist, "grid_units": unit, "grid_ft": dist * k, "ppf": ppf, "width": W, "height": H, "padding": pad, "sceneX": sx, "sceneY": sy,
            "width_ft": W / ppf, "height_ft": H / ppf, "warning": warn}


SCENE3D_KEYS = ("auto3d", "renderTable", "tableTex", "tableColor", "tableHeightmap", "tableHeightmapScale", "exr", "skybox", "renderBackground", "sunPosition", "sunDistance",
                "ambientLightIntensity", "ambientLightColor", "enableFog", "fogColor", "fogDistance", "exposure", "sceneTint", "timeSync", "maxElevation", "grounding")


def scene3d(sc):
    """The levels-3d-preview scene settings worth keeping (table texture, skybox, sun ...), or None for a plain 2D scene."""
    f = ((sc.get("flags") or {}).get("levels-3d-preview")) or {}
    if not f:
        return None
    return {k: f[k] for k in SCENE3D_KEYS if k in f}


def import_tiles(sc, c):
    """Tiles as feet rectangles (top-left origin) with the image path and, for 3D tiles, the model path / depth. Not fetched: references only."""
    out = []
    for i, t in enumerate(sc.get("tiles") or []):
        l3 = ((t.get("flags") or {}).get("levels-3d-preview")) or {}
        x, y = to_ft(c, t.get("x", 0) or 0, t.get("y", 0) or 0)
        src = (t.get("texture") or {}).get("src")
        rec = {"id": f"ftile_{i + 1:03d}", "foundry_id": t.get("_id"), "point": [x, y], "size_ft": [round((t.get("width") or 0) / c["ppf"], 2), round((t.get("height") or 0) / c["ppf"], 2)],
               "rotation": t.get("rotation", 0), "elevation": t.get("elevation", 0), "alpha": t.get("alpha", 1), "hidden": bool(t.get("hidden")), "src": src}
        if l3.get("model3d"):
            rec["model3d"] = l3.get("model3d")
            rec["depth"] = l3.get("depth")
        if src and "levels-3d-preview/assets/blank" in src:
            rec["blank"] = True   # carrier tile for a 3D model, no picture of its own
        out.append(rec)
    return out


def import_regions(sc, c):
    out = []
    for i, r in enumerate(sc.get("regions") or []):
        shapes = []
        for sh in r.get("shapes") or []:
            t = sh.get("type")
            if t == "rectangle":
                shapes.append({"type": t, "point": to_ft(c, sh.get("x", 0), sh.get("y", 0)), "size_ft": [round((sh.get("width") or 0) / c["ppf"], 2), round((sh.get("height") or 0) / c["ppf"], 2)], "rotation": sh.get("rotation", 0)})
            elif t in ("circle", "ellipse"):
                shapes.append({"type": t, "point": to_ft(c, sh.get("x", 0), sh.get("y", 0)), "radius_ft": [round((sh.get("radiusX", sh.get("radius", 0)) or 0) / c["ppf"], 2), round((sh.get("radiusY", sh.get("radius", 0)) or 0) / c["ppf"], 2)]})
            elif t == "polygon":
                pts = sh.get("points") or []
                shapes.append({"type": t, "points": [to_ft(c, pts[k], pts[k + 1]) for k in range(0, len(pts) - 1, 2)]})
            else:
                shapes.append({"type": t})
        out.append({"id": f"freg_{i + 1:03d}", "name": r.get("name"), "color": r.get("color"), "behaviors": len(r.get("behaviors") or []), "shapes": shapes})
    return out


def to_ft(c, x, y):
    return [round((x - c["sceneX"]) / c["ppf"], 2), round((y - c["sceneY"]) / c["ppf"], 2)]


def _key(p):
    return (round(p[0], 1), round(p[1], 1))


def chain_walls(segs, tol=0.6):
    """Join wall segments (each [[x,y],[x,y]], feet) that share end points into polylines. -> [{points, closed, door}]; deterministic."""
    segs = [s for s in segs if s["pts"][0] != s["pts"][1]]
    snap = {}

    def sn(p):
        k = (round(p[0] / tol), round(p[1] / tol))
        return snap.setdefault(k, tuple(p))
    ends = {}
    for i, s in enumerate(segs):
        for e in (0, 1):
            ends.setdefault(sn(s["pts"][e]), []).append((i, e))
    used, out = set(), []
    for i in range(len(segs)):
        if i in used:
            continue
        used.add(i)
        pts = [sn(segs[i]["pts"][0]), sn(segs[i]["pts"][1])]
        door = segs[i]["door"]
        grown = True
        while grown:
            grown = False
            for end in (1, 0):
                tip = pts[-1] if end == 1 else pts[0]
                for j, e in ends.get(tip, []):
                    if j in used:
                        continue
                    used.add(j)
                    other = sn(segs[j]["pts"][1 - e])
                    pts = pts + [other] if end == 1 else [other] + pts
                    door = door or segs[j]["door"]
                    grown = True
                    break
                if grown:
                    break
        closed = len(pts) > 3 and pts[0] == pts[-1]
        out.append({"points": [list(p) for p in (pts[:-1] if closed else pts)], "closed": closed, "door": door})
    return out


def poly_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def fetch_asset(src, dest_dir, assets_root=None, base_url=None, log=print):
    """Copy or download the scene background into dest_dir. -> (path or None, how)."""
    os.makedirs(dest_dir, exist_ok=True)
    name = os.path.basename(src.split("?")[0]) or "background"
    dest = os.path.join(dest_dir, "original_" + name)
    if re.match(r"^https?://", src):
        urls = [src]
    else:
        urls = []
        if os.path.isabs(src) and os.path.exists(src):     # a local file (import-image)
            shutil.copyfile(src, dest)
            return dest, "copied from a local file"
        rel = src.lstrip("/")
        local = None
        if assets_root and rel.startswith("assets/varrenmoor-3d/"):
            local = os.path.join(assets_root, rel[len("assets/varrenmoor-3d/"):])
        if local and os.path.exists(local):
            shutil.copyfile(local, dest)
            return dest, "copied from the shared assets folder"
        if os.path.exists(os.path.join(REPO, rel)):
            shutil.copyfile(os.path.join(REPO, rel), dest)
            return dest, "copied from the repository"
        if base_url:
            from urllib.parse import quote
            urls = [base_url.rstrip("/") + "/" + quote(rel)]
    import urllib.request
    for u in urls:
        try:
            with urllib.request.urlopen(u, timeout=20) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
            return dest, "downloaded " + u
        except Exception as e:  # noqa: BLE001 - network / http errors all mean "not available"
            log(f"download failed ({u}): {e}")
    return None, "not available"


def foundry_base_url():
    env = os.path.join(REPO, "foundry-3d", ".env")
    if os.environ.get("FOUNDRY_URL"):
        return os.environ["FOUNDRY_URL"]
    if os.path.exists(env):
        for ln in open(env, encoding="utf-8-sig"):
            m = re.match(r"\s*FOUNDRY_URL\s*=\s*(\S+)", ln)
            if m:
                return m.group(1).strip("'\"")
    return None


def import_scene(sc, scene_uuid, place_id=None, include=("walls",), closed_as="lines", no_image=False, force=False, dry_run=False, root=None, assets_root=None,
                 base_url=None, log=print):
    """Write world/<id>/ from a scene document (dict as returned by the bridge `get`). Never talks to Foundry."""
    root = root or os.path.join(REPO, "world")
    c = calibration(sc)
    if c["width"] <= 0 or c["height"] <= 0:
        raise ValueError("the scene has no width/height")
    name = sc.get("name") or "Imported scene"
    pid = place_id or slug(name)
    pdir = os.path.join(root, pid)
    if os.path.exists(os.path.join(pdir, "place.json")) and not force and not dry_run:
        raise ValueError(f"world/{pid} already exists (use --place-id for another id, or --force to overwrite)")
    W_ft, H_ft = round(c["width_ft"], 1), round(c["height_ft"], 1)
    segs, kinds = [], {}
    for w in sc.get("walls") or []:
        cc = w.get("c") or []
        if len(cc) < 4:
            continue
        a, b = to_ft(c, cc[0], cc[1]), to_ft(c, cc[2], cc[3])
        door = int(w.get("door") or 0)
        segs.append({"pts": [a, b], "door": door})
    chains = chain_walls(segs)
    lines, loops = [], []
    for ch in chains:
        if ch["closed"] and closed_as == "buildings" and 40 <= poly_area(ch["points"]) <= 60000:
            loops.append(ch)
        else:
            lines.append(ch)
    warnings = [c["warning"]] if c["warning"] else []
    tiles = import_tiles(sc, c) if "tiles" in include else []
    regions = import_regions(sc, c) if "regions" in include else []
    s3d = scene3d(sc)
    levels = [{"id": lv.get("_id"), "name": lv.get("name"), "elevation": lv.get("elevation")} for lv in (sc.get("levels") or [])]
    if len(levels) > 1:
        warnings.append(f"scene has {len(levels)} levels: only the first level's background is used; walls/lights/tokens of all levels are merged")
    if not background_src(sc):
        warnings.append("no background image" + (" (the scene is drawn by tiles / 3D models; nothing to underlay)" if tiles else ""))
    summary = {"place_id": pid, "name": name, "scene_uuid": scene_uuid, "size_ft": [W_ft, H_ft], "px_per_ft": round(c["ppf"], 4), "grid": {"size_px": c["grid_px"], "distance": c["grid_dist"], "units": c["grid_units"]},
               "walls": len(segs), "wall_polylines": len(lines), "closed_loops": len(loops) + sum(1 for ch in lines if ch["closed"]), "rooms_as_buildings": len(loops), "background": background_src(sc), "include": list(include), "dry_run": bool(dry_run),
               "tiles": len(tiles), "regions": len(regions), "levels": len(levels), "scene_3d": s3d, "warnings": warnings}
    if c["warning"]:
        summary["warning"] = c["warning"]
    if dry_run:
        return summary
    os.makedirs(pdir, exist_ok=True)
    # terrain stub: flat, coarse, so every tool that wants a heightmap works
    import numpy as np
    cell = float(max(10, int(max(W_ft, H_ft) / 300)))
    nx, ny = int(W_ft / cell) + 1, int(H_ft / cell) + 1
    tdir = os.path.join(pdir, "terrain")
    os.makedirs(tdir, exist_ok=True)
    np.save(os.path.join(tdir, "heightmap.npy"), np.zeros((ny, nx), dtype=np.float32))
    jsave(os.path.join(tdir, "terrain_meta.json"), {"size_ft": [W_ft, H_ft], "cell_ft": cell, "nx": nx, "ny": ny, "seed": 0, "elev_min": 0.0, "elev_max": 0.0, "relief_ft": 0.0, "units": "feet",
                                                   "pipeline": "flat_stub", "node_convention": "h[i,j] at x=j*cell_ft, y=i*cell_ft (y down)", "sea_level_ft": -1000.0})
    # underlay
    underlay = None
    src = background_src(sc)
    if src and not no_image:
        got, how = fetch_asset(src, os.path.join(pdir, "underlay"), assets_root, base_url or foundry_base_url(), log)
        if got:
            try:
                from PIL import Image
                im = Image.open(got)
                im.load()
                png = os.path.join(pdir, "underlay", "background.png")
                im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB").save(png)
                underlay = {"png": "underlay/background.png", "original": os.path.relpath(got, pdir).replace("\\", "/"), "px": list(im.size), "how": how,
                            "rect_ft": [0, 0, W_ft, H_ft], "note": "scene px (sceneX, sceneY) = place (0, 0); place the PNG over rect_ft, locked, below LINES"}
            except Exception as e:  # noqa: BLE001
                underlay = {"error": f"could not convert the image: {e}", "original": os.path.relpath(got, pdir).replace("\\", "/")}
        else:
            underlay = {"error": f"background {src} could not be fetched ({how}); set FOUNDRY_ASSETS_DIR / FOUNDRY_URL or copy it to underlay/background.png"}
    summary["underlay"] = underlay
    # walls -> files
    wpoly = [{"id": f"fw_{i + 1:03d}", "kind": "door" if ch["door"] else "wall", "points": ch["points"] + ([ch["points"][0]] if ch["closed"] else []), "closed": False} for i, ch in enumerate(lines)]
    jsave(os.path.join(pdir, "foundry_walls.json"), {"place": pid, "layer": "WALLS", "units": "ft", "origin": "scene top-left, y down", "walls": wpoly})
    jsave(os.path.join(pdir, "walls.json"), {"place": pid, "walls": [{"id": w["id"], "name": "Foundry wall", "kind": "foundry_wall", "status": "imported",
                                                                       "geometry": {"type": "polyline", "points": w["points"], "width_ft": 1.0}} for w in wpoly], "gates": []})
    bdir = os.path.join(pdir, "buildings")
    os.makedirs(bdir, exist_ok=True)
    for f in os.listdir(bdir):
        if f.startswith("bld_imp_"):
            os.remove(os.path.join(bdir, f))
    for i, lp in enumerate(loops):
        bid = f"bld_imp_{i + 1:03d}"
        jsave(os.path.join(bdir, bid + ".json"), {"id": bid, "name": f"Imported room {i + 1}", "kind": "imported", "status": "imported", "geometry": {"type": "polygon", "points": lp["points"]},
                                                  "notes": "Closed loop of Foundry walls.", "links": {"foundry_scene": scene_uuid, "model3d": None, "ai_layer": None}, "floors": 1,
                                                  "rooms": [], "doors": [], "elevation_ft": 0.0})
    inc = set(include)
    if "lights" in inc:
        L = [{"id": f"fl_{i + 1:03d}", "point": to_ft(c, l.get("x", 0), l.get("y", 0)), "bright_ft": round(float((l.get("config") or {}).get("bright") or 0), 1),
              "dim_ft": round(float((l.get("config") or {}).get("dim") or 0), 1), "color": (l.get("config") or {}).get("color"),
              "elevation": l.get("elevation"), "alpha": (l.get("config") or {}).get("alpha")} for i, l in enumerate(sc.get("lights") or [])]
        jsave(os.path.join(pdir, "foundry_lights.json"), {"place": pid, "lights": L})
        summary["lights"] = len(L)
    if "tokens" in inc:
        T = [{"id": f"ft_{i + 1:03d}", "name": t.get("name"), "point": to_ft(c, (t.get("x", 0) or 0) + (t.get("width", 1) or 1) * c["grid_px"] / 2, (t.get("y", 0) or 0) + (t.get("height", 1) or 1) * c["grid_px"] / 2),
              "actor_id": t.get("actorId"), "elevation": t.get("elevation"), "size_squares": [t.get("width", 1), t.get("height", 1)]} for i, t in enumerate(sc.get("tokens") or [])]
        jsave(os.path.join(pdir, "foundry_tokens.json"), {"place": pid, "tokens": T})
        summary["tokens"] = len(T)
    if "notes" in inc:
        N = [{"id": f"fn_{i + 1:03d}", "point": to_ft(c, n.get("x", 0), n.get("y", 0)), "text": n.get("text"), "entry_id": n.get("entryId")} for i, n in enumerate(sc.get("notes") or [])]
        jsave(os.path.join(pdir, "foundry_notes.json"), {"place": pid, "notes": N})
        summary["notes"] = len(N)
    if "tiles" in inc:
        jsave(os.path.join(pdir, "foundry_tiles.json"), {"place": pid, "units": "ft", "origin": "scene top-left, y down", "tiles": tiles})
    if "regions" in inc:
        jsave(os.path.join(pdir, "foundry_regions.json"), {"place": pid, "regions": regions})
    # model files
    for sub, key in (("districts", "districts"), ("streets", "streets")):
        jsave(os.path.join(pdir, sub + ".json"), {key: []})
    jsave(os.path.join(pdir, "water.json"), {"place": pid, "water": []})
    # Page sized so the town view is EXACTLY the scene rectangle (a later push-scene then reproduces the scene's size, not a bigger window around it)
    fpi = next((f for f in (1, 2, 2.5, 5, 10, 20, 25, 40, 50, 100, 200, 250, 500, 1000, 2000, 5000) if max(W_ft, H_ft) / f <= 14.0), 10000.0)
    page_in = [round(W_ft / fpi + 1.0, 4), round(H_ft / fpi + 1.0, 4)]
    vs = {"_note": "Written by import-scene. page_in is sized so the 'town' view covers exactly the scene; export it at >= grid_px/grid_ft px per foot x scale_ft_per_in dpi "
                   "(import.native_export_dpi in place.json) to keep the scene's own grid size.", "units": "ft", "page_in": page_in, "margin_in": 0.5, "min_street_width_ft": 10, "default_preset": "town",
          "contour_mask": {"enabled": True, "include": ["buildings", "streets", "plazas"]},
          "presets": {"town": {"scale_ft_per_in": fpi, "grid_ft": c["grid_ft"], "grid_major_every": 5, "focus": "center", "scale_bar_ft": 5 * fpi},
                      "bowl": {"scale_ft_per_in": fpi * 2, "grid_ft": c["grid_ft"] * 2, "grid_major_every": 5, "focus": "center", "scale_bar_ft": 10 * fpi},
                      "street": {"scale_ft_per_in": 20, "grid_ft": 20, "grid_major_every": 5, "focus": "entity", "scale_bar_ft": 100},
                      "room": {"scale_ft_per_in": 5, "grid_ft": 5, "grid_major_every": 5, "focus": "entity", "scale_bar_ft": 25}}}
    jsave(os.path.join(pdir, "view_settings.json"), vs)
    place = {"id": pid, "name": name, "kind": "scene", "status": "imported", "units": "feet", "origin": "scene top-left, y down", "bounds": {"width_ft": W_ft, "height_ft": H_ft},
             "notes": f"Imported from Foundry scene {scene_uuid} by import-scene (read-only). Grid {c['grid_dist']:g} {c['grid_units']} = {c['grid_px']:g} px.",
             "files": {"districts": "districts.json", "streets": "streets.json", "water": "water.json", "buildings": "buildings/", "view_settings": "view_settings.json", "terrain": "terrain/"},
             "view_focus": {"town": [round(W_ft / 2), round(H_ft / 2)]}, "links": {"foundry_scene": scene_uuid, "model3d": None, "ai_layer": None},
             "generated_by": "foundry_import.py", "sea_level_ft": -1000.0, "phase_elevation": "percentile",
             "import": {"scene_uuid": scene_uuid, "scene_name": name, "scene_px": [c["width"], c["height"]], "scene_offset_px": [c["sceneX"], c["sceneY"]], "padding": c["padding"],
                        "grid": {"size": c["grid_px"], "distance": c["grid_dist"], "units": c["grid_units"]}, "px_per_ft": c["ppf"], "native_export_dpi": round(c["ppf"] * fpi, 2), "background": src,
                        "underlay": (underlay or {}).get("png"), "imported": time.strftime("%Y-%m-%dT%H:%M:%S"), "levels": levels, "scene_3d": s3d, "warnings": warnings, "counts": {"tiles": len(tiles), "regions": len(regions), "walls": len(segs), "tokens": len(sc.get("tokens") or []),
                                                                                                                         "lights": len(sc.get("lights") or []), "notes": len(sc.get("notes") or [])}}}
    jsave(os.path.join(pdir, "place.json"), place)
    summary["dir"] = pdir
    summary["job"] = underlay_job(pid, underlay, pdir) if underlay and underlay.get("png") else None
    return summary


def import_image(image, name, place_id=None, ft_per_px=1.0, rotate=0.0, grid_ft=100.0, force=False, dry_run=False, root=None, log=print):
    """Create a place from a plain 2D base-map image (no Foundry needed). Reuses import_scene with a synthetic scene whose single background is the image:
    1 image px = ft_per_px feet, origin = the image's top-left corner (x right, y down; up in the picture = north), flat terrain stub, image copied to
    underlay/ and used as the UNDERLAY layer exactly like an imported scene. rotate = degrees clockwise applied to the image first (canvas grows, corners white-transparent)."""
    from PIL import Image
    image = os.path.abspath(image)
    if not os.path.isfile(image):
        raise ValueError(f"image not found: {image}")
    if not ft_per_px or ft_per_px <= 0:
        raise ValueError("ft_per_px must be > 0")
    im = Image.open(image)
    im.load()
    w, h = im.size
    tmp = None
    if rotate and abs(rotate) % 360 > 1e-9:
        im = im.convert("RGBA").rotate(-float(rotate), expand=True, resample=Image.BICUBIC)
        w, h = im.size
        import tempfile
        tmp = os.path.join(tempfile.mkdtemp(prefix="vb_img_"), "rotated.png")
        im.save(tmp)
    src = tmp or image
    nm = name or os.path.splitext(os.path.basename(image))[0]
    # grid: grid_ft feet = grid_px pixels, so px_per_ft = grid_px / grid_ft = 1 / ft_per_px
    sc = {"name": nm, "width": w, "height": h, "padding": 0, "grid": {"size": grid_ft / float(ft_per_px), "distance": grid_ft, "units": "ft", "type": 1}, "background": {"src": src.replace("\\", "/")}}
    try:
        res = import_scene(sc, "image:" + os.path.basename(image), place_id or slug(nm), (), "lines", False, force, dry_run, root=root, assets_root=None, log=log)
    finally:
        if tmp:
            shutil.rmtree(os.path.dirname(tmp), ignore_errors=True)
    res.update(source_image=image, ft_per_px=float(ft_per_px), rotate_deg=float(rotate or 0), image_px=[w, h])
    if dry_run:
        return res
    pj_path = os.path.join(res["dir"], "place.json")
    pj = json.load(open(pj_path, encoding="utf-8"))
    pj.update({"kind": "basemap", "status": "base map", "origin": "image top-left, x right, y down (up in the picture = north)", "generated_by": "foundry_import.py import-image"})
    pj["notes"] = (f"Base map from image {image} ({w}x{h} px) at {ft_per_px:g} ft per pixel; rotate {rotate or 0} deg clockwise. Place (x, y) ft = image pixel (x, y) * {ft_per_px:g}. "
                   "Trace roads / rivers over the UNDERLAY layer; nothing else is generated.")
    pj["links"]["foundry_scene"] = None
    imp = pj["import"]
    imp.update({"scene_uuid": None, "scene_name": nm, "source": "image", "source_image": image, "ft_per_px": float(ft_per_px), "rotate_deg": float(rotate or 0), "background": os.path.basename(image)})
    imp.pop("levels", None)
    imp["warnings"] = [x for x in imp.get("warnings", []) if "no background" not in x]
    jsave(pj_path, pj)
    res["place_json"] = pj_path
    return res


def underlay_job(pid, underlay, pdir):
    """Host actions: open a blank document sized to the scene and place the underlay (locked) on a layer UNDERLAY; walls are drawn by render_world on Walls."""
    return {"id": f"import_{pid}", "actions": [{"action": "place_image", "path": os.path.join(pdir, underlay["png"]).replace("\\", "/"), "rect": None, "layer": "UNDERLAY", "name": "foundry_background",
                                                "lock": True, "embed": False, "note": "rect is filled in by the panel from the render_world page size"}]}


def cmd_import_scene(br, a):
    """foundry_push.py hook. READ-ONLY: br.call('get') only."""
    import foundry_push as fp
    if a.scene_json:
        sc = json.load(open(a.scene_json, encoding="utf-8"))
        uuid = a.scene_uuid or sc.get("uuid") or f"Scene.{sc.get('_id', 'x')}"
    else:
        if not a.scene_uuid:
            raise fp.PushError("import-scene needs --scene-uuid (pick one with `foundry_push.py list --kinds scenes`)")
        sc = br.call("get", uuid=a.scene_uuid)
        uuid = a.scene_uuid
    inc = [x for x in (a.include or "walls,tiles,regions").split(",") if x]
    try:
        try:
            assets_root = None if a.no_image else (a.assets_dir or fp.assets_dir())
        except Exception:  # noqa: BLE001 - no shared assets folder configured: fall back to the repository / download
            assets_root = None
        res = import_scene(sc, uuid, a.place_id, inc, a.closed_as, a.no_image, a.yes or a.force, a.dry_run, assets_root=assets_root, log=fp.LOG)
    except ValueError as e:
        raise fp.PushError(str(e))
    res["ok"] = True
    return res
