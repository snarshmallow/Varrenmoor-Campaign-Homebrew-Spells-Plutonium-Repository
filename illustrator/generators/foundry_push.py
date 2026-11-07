"""Push the world model and an exported view of it from Illustrator to Foundry (scenes, walls, drawings, tokens, actors, items).

All Foundry access goes through foundry-bridge/bridge.ps1 (relay on this PC). Everything this tool creates carries the pipeline flag
flags.varrenmoor.pipelineId, so a second push UPDATES the same documents (no duplicates) and delete/prune only ever touches flagged ones.
Needs the Varrenmoor Bridge module >= 0.3.0 on the Foundry server (see foundry-bridge/DEPLOY_MODULE.md); older modules give a clear error.
Every command prints log lines, then ONE final JSON line on stdout ({"ok": true, ...} or {"ok": false, "error": ...}).

  status                                   bridge + module version
  places                                   world/<place> folders
  list [--kinds scenes,actors,items,journals] [--scene-uuid U]      read-only pickers (name + uuid), tiles of a scene
  export-info  --place P --view V ...      page/view calibration (feet <-> page px) for the panel's export_view
  push-scene   --place P --image PNG (--scene-name N | --scene-uuid U) [--yes] [--walls/--no-walls] [--drawings roads,water]
               [--tile-image PNG --tile-id layer] [--max-px 8192] [--ft-per-grid F] [--dry-run]
  push-token   --scene-uuid U --actor-uuid A (--at bld_id|str_id|x,y | --px sx,sy) [--image F] [--size-ft 5] [--key K] [--yes]
  push-actor   (--spec npc.json | --actor-uuid U) [--image F] [--portrait F --token F] [--yes]
  push-item    (--spec item.json | --name N) [--description T] [--image F] [--item-uuid U] [--yes]
  delete-scene --scene-uuid U              delete a pipeline-flagged scene (module refuses anything else)
View flags (same as render_world.py): --view --preset --scale --grid --page. Image calibration: the exported PNG is the whole page; the map
window (page minus margin) is cropped, resampled so one grid square = grid.size px, and stored as scene.flags.varrenmoor.calib.
"""
import argparse
import datetime
import json
import math
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
BRIDGE_PS1 = os.path.join(REPO, "foundry-bridge", "bridge.ps1")
MIN_PROTOCOL = 3
MODULE_MIN = "0.3.0"
FLAG = "varrenmoor"
LOG = lambda m: print(m, flush=True)  # noqa: E731


class PushError(Exception):
    pass


class NeedsModule(PushError):
    pass


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "x"


# ------------------------------------------------------------------ bridge transport
class PsBridge:
    """Calls foundry-bridge/bridge.ps1 with the payload in a temp JSON file (no quoting or length limits). Never prints settings or tokens."""
    LISTY = {"list", "find_by_flag"}

    def call(self, op, **args):
        fd, path = tempfile.mkstemp(suffix=".json", prefix="vbpush_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(args, f)
            r = subprocess.run(["powershell", "-NoProfile", "-File", BRIDGE_PS1, "-Op", op, "-ArgsFile", path], capture_output=True)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        out = r.stdout.decode("utf-8", "ignore").strip()
        if r.returncode != 0:
            msg = (r.stderr.decode("utf-8", "ignore") or out)
            m = re.search(r"failed: (.*)", msg)
            raise PushError(f"bridge {op}: {(m.group(1) if m else msg).strip()[:300]}")
        val = json.loads(out) if out else None
        if op in self.LISTY:   # PowerShell unrolls one-element arrays and drops empty ones
            val = [] if val is None else (val if isinstance(val, list) else [val])
        return val


def require_module(br):
    """Raise NeedsModule with a clear message unless the Foundry module has the pipeline ops (>= 0.3.0)."""
    try:
        v = br.call("version")
    except PushError as e:
        if "unknown op" in str(e):
            raise NeedsModule(f"The Varrenmoor Bridge module on the Foundry server is older than {MODULE_MIN} and has no pipeline ops. "
                              "Deploy it as described in foundry-bridge/DEPLOY_MODULE.md, then reload the GM tab.")
        raise
    if (v or {}).get("protocol", 0) < MIN_PROTOCOL:
        raise NeedsModule(f"Module protocol {(v or {}).get('protocol')} is older than {MIN_PROTOCOL}; deploy foundry-bridge/DEPLOY_MODULE.md.")
    return v


# ------------------------------------------------------------------ assets (the shared folder Foundry serves)
def assets_dir():
    d = os.environ.get("FOUNDRY_ASSETS_DIR")
    envf = os.path.join(REPO, "foundry-3d", ".env")
    if not d and os.path.exists(envf):
        for ln in open(envf, encoding="utf-8-sig"):
            m = re.match(r"\s*FOUNDRY_ASSETS_DIR\s*=\s*(.+?)\s*$", ln)
            if m:
                d = m.group(1)
    return d or r"\\VEGA\varrenmoor-3d"


def encode_image(img, fmt):
    import io
    b = io.BytesIO()
    if fmt == "png":
        img.save(b, "PNG", optimize=True)
    else:
        img.save(b, "WEBP", quality=92, method=4)
    return b.getvalue()


def publish_image(img, rel_dir, stem, root, fmt="webp", dry=False):
    """Write <root>/<rel_dir>/<stem>_vNNN.<fmt> with the next version number (Foundry and browsers cache by path).
    If the newest existing version is byte-identical the push reuses it, so re-pushing an unchanged view adds no files.
    Returns (version, foundry_path)."""
    data = encode_image(img, fmt)
    d = os.path.join(root, *rel_dir.split("/"))
    pat = re.compile(re.escape(stem) + r"_v(\d+)\." + fmt + "$")
    have = sorted((int(m.group(1)), f) for f in (os.listdir(d) if os.path.isdir(d) else []) for m in [pat.match(f)] if m)
    ver = have[-1][0] if have else 0
    if have:
        with open(os.path.join(d, have[-1][1]), "rb") as f:
            same = f.read() == data
    else:
        same = False
    if same:
        return ver, f"assets/varrenmoor-3d/{rel_dir}/{have[-1][1]}"
    ver += 1
    name = f"{stem}_v{ver:03d}.{fmt}"
    if not dry:
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    return ver, f"assets/varrenmoor-3d/{rel_dir}/{name}"


def publish_file(path, rel_dir, stem, root, dry=False):
    from PIL import Image
    img = Image.open(path)
    img.load()
    return publish_image(img.convert("RGBA") if img.mode in ("P", "LA") else img, rel_dir, stem, root, "webp", dry)


# ------------------------------------------------------------------ world model and view calibration
def load_view(place, view="town", preset=None, scale=None, grid=None, page=None, major=None):
    import render_world as rw
    model = rw.load_place(place)
    over = {"preset": preset, "scale": scale, "grid": grid, "page": page, "major_every": major}
    v, cfg, title, kind, ident = rw.compute_view(model, view, over)
    return model, v, cfg


def calibrate(v, cfg, img_size, max_px=8192, ft_per_grid=None, padding=0.0):
    """Exported page PNG -> scene. Returns calib dict (crop box in source px, target size, ppf = scene px per ft, grid)."""
    pw, ph = cfg["page_in"]
    m = cfg.get("margin_in", 0.5)
    D = img_size[0] / pw                                       # source px per page inch
    if abs(img_size[1] - ph * D) > 3:
        raise PushError(f"image {img_size[0]}x{img_size[1]} does not match the page {pw}x{ph} in; export the whole artboard (export_view)")
    fpi = cfg["scale_ft_per_in"]
    native = D / fpi                                           # source px per foot
    grid_ft = float(ft_per_grid or cfg["grid_ft"])
    f = min(1.0, max_px / (max(v.wf, v.hf) * native))
    gp = int(round(native * f * grid_ft))
    if gp < 50:
        raise PushError(f"grid would be {gp}px per square (Foundry minimum is 50): export at a higher dpi or use a smaller --ft-per-grid")
    ppf = gp / grid_ft
    W, H = int(round(v.wf * ppf)), int(round(v.hf * ppf))
    if max(W, H) > max_px + 50:
        raise PushError(f"scene would be {W}x{H}px, over the {max_px}px limit: lower --max-px or use a bigger --ft-per-grid")
    sx = int(math.ceil(W * padding / gp) * gp) if padding else 0
    sy = int(math.ceil(H * padding / gp) * gp) if padding else 0
    return {"crop": [int(round(m * D)), int(round(m * D)), int(round((pw - m) * D)), int(round((ph - m) * D))],
            "x0": v.x0, "y0": v.y0, "w_ft": v.wf, "h_ft": v.hf, "ppf": ppf, "grid_px": gp, "grid_ft": grid_ft,
            "width": W, "height": H, "padding": padding, "sceneX": sx, "sceneY": sy, "src_dpi": D}


def to_scene_px(c, x_ft, y_ft):
    return c["sceneX"] + (x_ft - c["x0"]) * c["ppf"], c["sceneY"] + (y_ft - c["y0"]) * c["ppf"]


def crop_resize(img, c):
    from PIL import Image
    im = img.crop(tuple(c["crop"]))
    if im.size != (c["width"], c["height"]):
        im = im.resize((c["width"], c["height"]), Image.LANCZOS)
    return im


def clip_segment(p, q, box):
    """Liang-Barsky: clip segment p-q to box (x0,y0,x1,y1); None if outside."""
    x0, y0, x1, y1 = box
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pp == 0:
            if qq < 0:
                return None
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return None
    return (p[0] + t0 * dx, p[1] + t0 * dy), (p[0] + t1 * dx, p[1] + t1 * dy)


WALL = {"move": 20, "sense": 20, "light": 20, "sound": 20, "dir": 0, "door": 0, "ds": 0}


def build_walls(model, c):
    """One wall per building edge (and per room edge when rooms carry polygons). id = wall:<entity>:<n>."""
    box = (c["x0"], c["y0"], c["x0"] + c["w_ft"], c["y0"] + c["h_ft"])
    items = []

    def ring(eid, pts):
        n = len(pts)
        for i in range(n):
            seg = clip_segment(pts[i], pts[(i + 1) % n], box)
            if not seg or math.dist(*seg) < 0.5:
                continue
            (ax, ay), (bx, by) = (to_scene_px(c, *seg[0]), to_scene_px(c, *seg[1]))
            items.append({"id": f"wall:{eid}:{i}", "data": {"c": [round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1)], **WALL}})

    for b in sorted(model["buildings"], key=lambda b: b["id"]):
        g = b.get("geometry", {})
        if g.get("type") == "polygon" and len(g.get("points", [])) >= 3:
            ring(b["id"], g["points"])
        for r in b.get("rooms", []) or []:
            rg = (r.get("geometry") or {}) if isinstance(r, dict) else {}
            if rg.get("type") == "polygon" and len(rg.get("points", [])) >= 3:
                ring(f"{b['id']}.{r.get('id', 'room')}", rg["points"])
    return items


def _poly_drawing(eid, kind, pts, c, fill, stroke):
    sp = [to_scene_px(c, *p) for p in pts]
    xs, ys = [p[0] for p in sp], [p[1] for p in sp]
    ox, oy = min(xs), min(ys)
    return {"id": f"draw:{kind}:{eid}", "data": {
        "x": round(ox, 1), "y": round(oy, 1), "elevation": 0, "sort": 0, "hidden": False, "locked": True,
        "shape": {"type": "p", "width": round(max(xs) - ox, 1), "height": round(max(ys) - oy, 1), "radius": None,
                  "points": [round(v, 1) for p in sp for v in (p[0] - ox, p[1] - oy)]},
        "fillType": 1, "fillColor": fill, "fillAlpha": 0.55, "strokeWidth": 2, "strokeColor": stroke, "strokeAlpha": 1.0}}


def build_drawings(model, c, kinds):
    import render_world as rw
    box = (c["x0"], c["y0"], c["x0"] + c["w_ft"], c["y0"] + c["h_ft"])
    out = []
    if "roads" in kinds:
        for s in sorted(model["streets"], key=lambda s: s["id"]):
            poly = rw.clip_poly(rw.entity_polygon(s), *box)
            if poly and len(poly) >= 3:
                out.append(_poly_drawing(s["id"], "road", poly, c, "#b79b6b", "#6b5636"))
    if "water" in kinds:
        for w in sorted(model["water"], key=lambda w: w["id"]):
            g = w.get("geometry", {})
            if g.get("type") == "polygon":
                poly = rw.clip_poly([tuple(p) for p in g["points"]], *box)
                if poly and len(poly) >= 3:
                    out.append(_poly_drawing(w["id"], "water", poly, c, "#7fa6c8", "#3b6a97"))
    return out


# ------------------------------------------------------------------ foundry reads
def pipe_id(doc):
    return ((doc or {}).get("flags") or {}).get(FLAG, {}).get("pipelineId")


def cmd_status(br, a):
    out = {"ok": True, "connected": False}
    try:
        br.call("ping")
        out["connected"] = True
        wi = br.call("world_info")
        out["foundry"], out["world"] = wi.get("foundry"), wi.get("world")
        mods = {m["id"]: m["version"] for m in wi.get("modules", [])}
        out["module"] = mods.get("varrenmoor-bridge")
    except PushError as e:
        out["ok"], out["error"] = False, str(e)
        return out
    try:
        v = br.call("version")
        out["protocol"], out["pipeline_ops"] = v.get("protocol"), True
    except PushError as e:
        out["pipeline_ops"] = False
        out["warning"] = f"module {out.get('module')} lacks pipeline ops (need >= {MODULE_MIN}); see foundry-bridge/DEPLOY_MODULE.md" if "unknown op" in str(e) else str(e)
    return out


def cmd_places(br, a):
    root = os.path.join(REPO, "world")
    return {"ok": True, "places": sorted(n for n in os.listdir(root) if os.path.exists(os.path.join(root, n, "place.json")))}


COLLS = {"scenes": "Scene", "actors": "Actor", "items": "Item", "journals": "JournalEntry"}


def cmd_list(br, a):
    out = {"ok": True, "fetched": datetime.datetime.now().isoformat(timespec="seconds"), "lists": {}}
    for k in [x for x in (a.kinds or "scenes,actors,items,journals").split(",") if x]:
        if k == "tiles":
            continue
        if k not in COLLS:
            raise PushError(f"unknown kind {k}")
        rows = br.call("list", collection=COLLS[k])
        if k == "scenes":    # mark scenes the pipeline made (needs the new module; absent marks are just false)
            try:
                flagged = {r["uuid"] for r in br.call("find_by_flag", documentName="Scene", prefix="")}
            except PushError:
                flagged = set()
            for r in rows:
                r["pipeline"] = r["uuid"] in flagged
        out["lists"][k] = rows
    if a.scene_uuid:     # tiles/tokens/walls of one scene, via get (works on any module version)
        sc = br.call("get", uuid=a.scene_uuid)
        out["lists"]["tiles"] = [{"uuid": f"{a.scene_uuid}.Tile.{t.get('_id')}", "name": pipe_id(t) or (t.get("texture", {}).get("src") or "")[-40:], "pipeline": bool(pipe_id(t))} for t in sc.get("tiles", [])]
        out["scene"] = {"name": sc.get("name"), "pipelineId": pipe_id(sc), "walls": len(sc.get("walls", [])), "tokens": len(sc.get("tokens", [])),
                        "calib": (sc.get("flags", {}).get(FLAG, {}) or {}).get("calib")}
    return out


def cmd_export_info(br, a):
    model, v, cfg = load_view(a.place, a.view, a.preset, a.scale, a.grid, a.page, a.major)
    return {"ok": True, "page_in": cfg["page_in"], "margin_in": cfg["margin_in"], "scale_ft_per_in": cfg["scale_ft_per_in"], "grid_ft": cfg["grid_ft"],
            "window_ft": [v.x0, v.y0, v.wf, v.hf], "px_per_ft_at_dpi": {str(d): d / cfg["scale_ft_per_in"] for d in (72, 150, 300)}}


# ------------------------------------------------------------------ push scene
def scene_summary(sc, c, new_name):
    bg = ((sc.get("levels") or [{}])[0].get("background") or {}).get("src")
    g = sc.get("grid", {})
    return [f"Scene \"{sc.get('name')}\" was not created by the pipeline.",
            f"Its background ({bg or 'none'}) will be replaced by the pushed view {c['width']}x{c['height']}px.",
            f"Grid {g.get('size')}px / {g.get('distance')} {g.get('units')} becomes {c['grid_px']}px / {c['grid_ft']:g} ft; scene size {sc.get('width')}x{sc.get('height')} becomes {c['width']}x{c['height']}.",
            "Walls, drawings and tiles you made yourself are NOT touched; only pipeline-flagged ones are added/updated/pruned. The scene will be flagged as pipeline-managed."]


def cmd_push_scene(br, a):
    from PIL import Image
    model, v, cfg = load_view(a.place, a.view, a.preset, a.scale, a.grid, a.page, a.major)
    img = Image.open(a.image)
    img.load()
    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
    c = calibrate(v, cfg, img.size, a.max_px, a.ft_per_grid, a.padding)
    LOG(f"view window {v.wf:g} x {v.hf:g} ft -> scene {c['width']}x{c['height']}px, grid {c['grid_px']}px = {c['grid_ft']:g} ft, {c['ppf']:.3f} px/ft")
    walls = build_walls(model, c) if a.walls else []
    drawings = build_drawings(model, c, [k for k in (a.drawings or "").split(",") if k]) if a.drawings else []
    LOG(f"{len(walls)} walls, {len(drawings)} drawings")
    if not a.dry_run:
        require_module(br)
    pid = None
    sc = None
    if a.scene_uuid:
        sc = br.call("get", uuid=a.scene_uuid)
        pid = pipe_id(sc)
        if not pid and not a.yes:
            return {"ok": False, "needs_confirm": True, "scene_uuid": a.scene_uuid, "summary": scene_summary(sc, c, None)}
        name = sc["name"]
    else:
        name = a.scene_name
        if not name:
            raise PushError("give --scene-name (new scene) or --scene-uuid (existing scene)")
        pid = f"scene:{a.place}:{slug(name)}"
        if not a.dry_run:
            hit = br.call("find_by_flag", documentName="Scene", id=pid)
            if hit:
                a.scene_uuid = hit[0]["uuid"]
            else:
                clash = [r for r in br.call("list", collection="Scene") if r["name"].lower() == name.lower()]
                if clash:
                    raise PushError(f"a scene named \"{name}\" exists and was not created by the pipeline: choose it in the scene picker instead (uuid {clash[0]['uuid']}) or use another name")
    pid = pid or f"scene:{a.place}:{slug(name)}"
    scene_stem = slug(name)
    ver, src = publish_image(crop_resize(img, c), f"art/{a.place}", f"scene_{scene_stem}", assets_dir() if not a.assets_dir else a.assets_dir, a.format, a.dry_run)
    LOG(f"background {src}")
    tile = None
    if a.tile_image:
        timg = Image.open(a.tile_image)
        timg.load()
        tv, tsrc = publish_image(crop_resize(timg.convert("RGBA"), c), f"art/{a.place}", f"tile_{scene_stem}_{slug(a.tile_id)}", assets_dir() if not a.assets_dir else a.assets_dir, "webp", a.dry_run)
        tile = {"id": f"tile:{a.tile_id}", "data": {"x": c["sceneX"], "y": c["sceneY"], "width": c["width"], "height": c["height"], "elevation": 0, "sort": 10,
                                                      "locked": True, "texture": {"src": tsrc}}}
    calib = {k: c[k] for k in ("x0", "y0", "ppf", "grid_px", "grid_ft", "width", "height", "sceneX", "sceneY")}
    calib.update(place=a.place, view=a.view, version=ver, pushed=datetime.datetime.now().isoformat(timespec="seconds"))
    result = {"ok": True, "scene_name": name, "pipelineId": pid, "version": ver, "image": src, "grid": {"size": c["grid_px"], "distance": c["grid_ft"]},
              "width": c["width"], "height": c["height"], "walls": len(walls), "drawings": len(drawings), "dry_run": bool(a.dry_run)}
    if a.dry_run:
        return result
    sdata = {"name": name, "width": c["width"], "height": c["height"], "padding": c["padding"], "navigation": False,
             "grid": {"type": 1, "size": c["grid_px"], "distance": c["grid_ft"], "units": "ft"},
             "flags": {FLAG: {"worldId": a.place, "calib": calib}}}
    if sc is not None and not pipe_id(sc):          # confirmed adoption of an existing scene: change only what we manage
        br.call("update", uuid=a.scene_uuid, data={"flags": {FLAG: {"pipelineId": pid, "worldId": a.place, "calib": calib}}})
        result["created"] = False
    else:
        r = br.call("upsert_by_flag", documentName="Scene", id=pid, data=sdata)
        a.scene_uuid, result["created"] = r["uuid"], r["created"]
    uuid = a.scene_uuid
    br.call("set_scene_background", uuid=uuid, src=src, width=c["width"], height=c["height"], padding=c["padding"])
    br.call("set_scene_grid", uuid=uuid, size=c["grid_px"], distance=c["grid_ft"], units="ft")
    if a.walls:
        r = br.call("upsert_many", documentName="Wall", parentUuid=uuid, items=walls, prefix="wall:", prune=True)
        result["wall_ops"] = r
        LOG(f"walls: {r}")
    if drawings or a.drawings is not None:
        r = br.call("upsert_many", documentName="Drawing", parentUuid=uuid, items=drawings, prefix="draw:", prune=True)
        result["drawing_ops"] = r
        LOG(f"drawings: {r}")
    if tile:
        r = br.call("upsert_many", documentName="Tile", parentUuid=uuid, items=[tile])
        result["tile_ops"] = r
    result["scene_uuid"] = uuid
    LOG(f"scene {'created' if result.get('created') else 'updated'}: {uuid}")
    return result


def cmd_delete_scene(br, a):
    require_module(br)
    return {"ok": True, **br.call("delete", uuid=a.scene_uuid)}


# ------------------------------------------------------------------ tokens, actors, items
def entity_point(place, ref):
    """bld_*/str_* id -> centroid in feet from the world model, or 'x,y' feet."""
    if re.match(r"^-?[\d.]+\s*,\s*-?[\d.]+$", ref):
        x, y = (float(t) for t in ref.split(","))
        return x, y
    import render_world as rw
    model = rw.load_place(place)
    for e in model["buildings"] + model["streets"] + model["water"]:
        if e["id"] == ref:
            return rw.centroid(rw.entity_polygon(e) if e["geometry"]["type"] == "polyline" else [tuple(p) for p in e["geometry"]["points"]])
    raise PushError(f"no building/street/water with id {ref}")


def _images(a, br, place, stem, dry):
    """--image F (portrait and token), or --portrait/--token separately -> (portrait_src, token_src)."""
    root = a.assets_dir or assets_dir()
    p = t = None
    if getattr(a, "image", None):
        _, p = publish_file(a.image, f"art/{place}/actors", f"{stem}", root, dry)
        t = p
    if getattr(a, "portrait", None):
        _, p = publish_file(a.portrait, f"art/{place}/actors", f"{stem}_portrait", root, dry)
    if getattr(a, "token", None):
        _, t = publish_file(a.token, f"art/{place}/actors", f"{stem}_token", root, dry)
    return p, t


def folder_for(br, name, ftype):
    if not name:
        return None
    for r in br.call("list", collection="Folder"):
        if r["name"].lower() == name.split("/")[-1].lower() and r.get("type") == ftype:
            return r["uuid"].split(".")[-1]
    return None


def confirm_needed(doc_uuid, doc, what, yes):
    if pipe_id(doc) or yes:
        return None
    return {"ok": False, "needs_confirm": True, "uuid": doc_uuid, "summary": [f"\"{doc.get('name')}\" was not created by the pipeline.", what, "Nothing else on it is changed."]}


def cmd_push_actor(br, a):
    place = a.place
    require_module(br)
    if a.actor_uuid:                       # update the images of an existing actor
        doc = br.call("get", uuid=a.actor_uuid)
        p, t = _images(a, br, place, slug(doc["name"]), False)
        if not (p or t):
            raise PushError("give --image (or --portrait / --token)")
        need = confirm_needed(a.actor_uuid, doc, f"Portrait -> {p or '(unchanged)'}, token art -> {t or '(unchanged)'}.", a.yes)
        if need:
            return need
        data = {}
        if p:
            data["img"] = p
        if t:
            data["prototypeToken"] = {"texture": {"src": t}}
        br.call("update", uuid=a.actor_uuid, data=data)
        return {"ok": True, "uuid": a.actor_uuid, "updated": sorted(data)}
    if not a.spec:
        raise PushError("give --spec <npc.json> (create/update from a spec) or --actor-uuid")
    spec = json.load(open(a.spec, encoding="utf-8"))
    sys.path.insert(0, os.path.join(REPO, "foundry-tools"))
    from vtt import npc as vnpc            # reuses the existing NPC spec -> dnd5e actor builder
    actor = vnpc.build_actor(spec)
    actor.pop("_id", None)
    p, t = _images(a, br, place, slug(spec["name"]), False)
    if p:
        actor["img"] = p
    if t:
        actor["prototypeToken"].setdefault("texture", {})["src"] = t
    fid = folder_for(br, spec.get("folder"), "Actor")
    if fid:
        actor["folder"] = fid
    r = br.call("upsert_by_flag", documentName="Actor", id=f"npc:{place}:{slug(spec['name'])}", data=actor)
    LOG(f"actor {'created' if r['created'] else 'updated'}: {r['uuid']}")
    return {"ok": True, **r}


def cmd_push_item(br, a):
    place = a.place
    require_module(br)
    if a.item_uuid:
        doc = br.call("get", uuid=a.item_uuid)
        data = {}
        if a.image:
            _, src = publish_file(a.image, f"art/{place}/items", slug(doc["name"]), a.assets_dir or assets_dir())
            data["img"] = src
        if a.description is not None:
            data["system"] = {"description": {"value": "<p>" + a.description + "</p>"}}
        need = confirm_needed(a.item_uuid, doc, "Updates: " + ", ".join(sorted(data)) + ".", a.yes)
        if need:
            return need
        br.call("update", uuid=a.item_uuid, data=data)
        return {"ok": True, "uuid": a.item_uuid, "updated": sorted(data)}
    spec = json.load(open(a.spec, encoding="utf-8")) if a.spec else {"name": a.name, "description": a.description or ""}
    if not spec.get("name"):
        raise PushError("give --spec <item.json> or --name")
    sys.path.insert(0, os.path.join(REPO, "foundry-tools"))
    from vtt import item as vitem
    doc = vitem.build_item_doc(spec, "")
    doc["flags"] = {}                     # no 3D model: drop the levels-3d-preview model flag build_item_doc adds
    if a.image:
        _, doc["img"] = publish_file(a.image, f"art/{place}/items", slug(spec["name"]), a.assets_dir or assets_dir())
    fid = folder_for(br, spec.get("folder"), "Item")
    if fid:
        doc["folder"] = fid
    r = br.call("upsert_by_flag", documentName="Item", id=f"item:{place}:{slug(spec['name'])}", data=doc)
    LOG(f"item {'created' if r['created'] else 'updated'}: {r['uuid']}")
    return {"ok": True, **r}


def cmd_push_token(br, a):
    require_module(br)
    sc = br.call("get", uuid=a.scene_uuid)
    calib = (sc.get("flags", {}).get(FLAG, {}) or {}).get("calib")
    if a.px:
        sx, sy = (float(t) for t in a.px.split(","))
        gp = sc["grid"]["size"]
        gft = sc["grid"]["distance"]
    else:
        if not calib:
            raise PushError("this scene has no pipeline calibration; push the scene first or give --px sx,sy")
        x, y = entity_point(calib.get("place") or a.place, a.at)
        sx, sy = to_scene_px(calib, x, y)
        gp, gft = calib["grid_px"], calib["grid_ft"]
    actor = br.call("get", uuid=a.actor_uuid)
    sq = max(0.25, a.size_ft / gft)
    tok = json.loads(json.dumps(actor.get("prototypeToken") or {}))
    tok.pop("_id", None)
    tok.update(name=tok.get("name") or actor["name"], actorId=actor["_id"], width=sq, height=sq, hidden=bool(a.hidden))
    if a.image:
        _, src = publish_file(a.image, f"art/{a.place}/actors", slug(actor["name"]) + "_token", a.assets_dir or assets_dir())
        tok.setdefault("texture", {})["src"] = src
    tok["x"], tok["y"] = round(sx - sq * gp / 2), round(sy - sq * gp / 2)
    key = a.key or f"{actor['_id']}:{a.at or a.px}"
    r = br.call("upsert_by_flag", documentName="Token", parentUuid=a.scene_uuid, id=f"token:{key}", data=tok)
    LOG(f"token {'placed' if r['created'] else 'moved'}: {r['uuid']} at {tok['x']},{tok['y']}")
    return {"ok": True, **r, "x": tok["x"], "y": tok["y"]}


# ------------------------------------------------------------------ cli
def parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["status", "places", "list", "export-info", "push-scene", "push-token", "push-actor", "push-item", "delete-scene"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--page")
    ap.add_argument("--grid-major", "--major", dest="major", type=int)
    ap.add_argument("--kinds")
    ap.add_argument("--scene-uuid")
    ap.add_argument("--scene-name")
    ap.add_argument("--image")
    ap.add_argument("--portrait")
    ap.add_argument("--token")
    ap.add_argument("--max-px", type=int, default=8192)
    ap.add_argument("--ft-per-grid", type=float)
    ap.add_argument("--padding", type=float, default=0.0)
    ap.add_argument("--walls", dest="walls", action="store_true", default=True)
    ap.add_argument("--no-walls", dest="walls", action="store_false")
    ap.add_argument("--drawings", default=None, help="comma list: roads,water ('' = prune all pipeline drawings)")
    ap.add_argument("--tile-image")
    ap.add_argument("--tile-id", default="overlay")
    ap.add_argument("--format", choices=["webp", "png"], default="webp")
    ap.add_argument("--assets-dir")
    ap.add_argument("--yes", action="store_true", help="confirm changes to documents the pipeline did not create")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--actor-uuid")
    ap.add_argument("--item-uuid")
    ap.add_argument("--spec")
    ap.add_argument("--name")
    ap.add_argument("--description")
    ap.add_argument("--at")
    ap.add_argument("--px")
    ap.add_argument("--size-ft", type=float, default=5.0)
    ap.add_argument("--key")
    ap.add_argument("--hidden", action="store_true")
    return ap


CMDS = {"status": cmd_status, "places": cmd_places, "list": cmd_list, "export-info": cmd_export_info, "push-scene": cmd_push_scene,
        "push-token": cmd_push_token, "push-actor": cmd_push_actor, "push-item": cmd_push_item, "delete-scene": cmd_delete_scene}


def main(argv=None, bridge=None):
    a = parser().parse_args(argv)
    try:
        res = CMDS[a.cmd](bridge or PsBridge(), a)
    except NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except PushError as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") or res.get("needs_confirm") else 1


if __name__ == "__main__":
    sys.exit(main())
