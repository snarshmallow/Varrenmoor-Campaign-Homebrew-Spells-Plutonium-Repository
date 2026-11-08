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
  push-models  --placements P (--scene-uuid U | --scene-name N) [--layers L] [--ids I] [--lod 0|1|2] [--px-per-ft F] [--prune] [--dry-run]
               one 3D Canvas tile per model of a world pack (worldpack_split.py), upserted by pipelineId model:<place>:<id>
  import-scene --scene-uuid U [--place-id ID] [--include walls,lights,tokens,notes] [--no-image] [--closed-as buildings|lines] [--force] [--dry-run] [--scene-json F]
               READ-ONLY on Foundry: create a place from an existing scene (calibration from the grid, background as underlay, walls as WALLS lines / building
               outlines, links.foundry_scene = the scene). See foundry_import.py. push-scene with no --scene-uuid/--scene-name then goes back to that scene.
  delete-scene --scene-uuid U              delete a pipeline-flagged scene (module refuses anything else)
  link-region  --place CHILD (--parent-scene-uuid U | --parent-scene-name N) [--child-scene-uuid U] [--apply]
               region children (region_extract.py): outline Drawing of the region on the parent scene (pipelineId draw:region:<child>), flagged with the
               child place and scene. Prints the planned document and writes NOTHING unless --apply.
  A scene pushed for a region child (--place world/<parent>__<region>, --view region) also carries flags.varrenmoor.region = {parent, polygon, transform}
  and a default scene name (--scene-name omitted) of "<region name> (district)".
View flags (same as render_world.py): --view --preset --scale --grid --page. Image calibration: the exported PNG is the whole page; the map
window (page minus margin) is cropped, resampled so one grid square = grid.size px, and stored as scene.flags.varrenmoor.calib.
"""
import argparse
import datetime
import io
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


# Scene modes (see illustrator/FOUNDRY_3D_CANVAS_NOTES.md). 3D Canvas keeps its scene settings in flags.levels-3d-preview. Only the keys listed here are written,
# everything else keeps the module default. The "3d" values are copied from the working 3D scenes (Ossuary Market template, ZZ Tile Rotation Inspect).
L3D = "levels-3d-preview"
SCENE_MODES = {
    "flat": {"auto3d": False, "enablePlayers": False, "renderBackground": False},
    "3d": {"auto3d": True, "enablePlayers": True, "object3dSight": True, "enableGameCamera": True, "enableFogOfWar": True, "enableRuler": True,
           "renderBackground": False, "renderTable": "matcustom", "tableTex": "baileywiki-content/assets/modules/baileywiki-3d/models/black-tone-pure.webp",
           "tableColor": "#341f0f", "exr": "assets/ossuary-exchange-skybox3.webp", "skybox": "", "maxElevation": 100000, "timeSync": "darkness", "sunPosition": 9,
           "ambientLightIntensity": 0, "showSceneWalls": True, "showSceneDoors": True, "showSceneFloors": True, "renderSceneLights": True, "mirrorLevels": True},
}


def scene_mode_flags(mode, overrides=None):
    """{"levels-3d-preview": {...}} for --scene-mode flat|3d; overrides = ["key=value", ...] (value parsed as JSON, else kept as a string)."""
    if mode not in SCENE_MODES:
        raise PushError(f"--scene-mode must be flat or 3d, not {mode}")
    f = dict(SCENE_MODES[mode])
    for o in overrides or []:
        k, sep, v = o.partition("=")
        if not sep or not k:
            raise PushError(f"--scene-flag needs key=value, got {o}")
        try:
            f[k] = json.loads(v)
        except ValueError:
            f[k] = v
    return {L3D: f}


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


def calibrate(v, cfg, img_size, max_px=8192, ft_per_grid=None, padding=0.0, upscale=1.0):
    """Exported page PNG -> scene. Returns calib dict (crop box in source px, target size, ppf = scene px per ft, grid)."""
    pw, ph = cfg["page_in"]
    m = cfg.get("margin_in", 0.5)
    D = img_size[0] / pw                                       # source px per page inch
    if abs(img_size[1] - ph * D) > 3:
        raise PushError(f"image {img_size[0]}x{img_size[1]} does not match the page {pw}x{ph} in; export the whole artboard (export_view)")
    fpi = cfg["scale_ft_per_in"]
    native = D / fpi * float(upscale or 1.0)                   # scene px per foot before the max_px limit (upscale > 1 resamples a low-dpi export up so a 5 ft grid reaches Foundry's 50 px minimum)
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


def region_flags(place):
    """flags.varrenmoor.region for a region child (parent link, polygon in PARENT feet, transform), None for an ordinary place."""
    import region_extract as rx
    r = rx._rj(os.path.join(rx.child_dir(place), "region.json"))
    if not r:
        return None
    return {"parent": r["parent"], "child": r["child"], "name": r["name"], "polygon_parent_ft": r["region"]["polygon_parent_ft"], "transform": r["transform"],
            "parent_commit": (r.get("parent_source") or {}).get("git_commit"), "parent_sha1": (r.get("parent_source") or {}).get("content_sha1"),
            "extracted_at": r.get("extracted_at")}


def cmd_push_scene(br, a):
    from PIL import Image
    if not a.scene_uuid and not a.scene_name:                 # a place imported from (or pushed with --link to) a scene goes back to that scene by default
        lk = place_link(a.place)
        if lk:
            a.scene_uuid = lk
            LOG(f"no scene given: using the scene linked to the place ({lk})")
    model, v, cfg = load_view(a.place, a.view, a.preset, a.scale, a.grid, a.page, a.major)
    img = Image.open(a.image)
    img.load()
    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img
    c = calibrate(v, cfg, img.size, a.max_px, a.ft_per_grid, a.padding, a.upscale)
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
        rf0 = region_flags(a.place)
        if not name and rf0:
            name = f"{rf0['name']} (district)"
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
    rf = region_flags(a.place)
    extra = {"region": rf} if rf else {}
    sdata = {"name": name, "width": c["width"], "height": c["height"], "padding": c["padding"], "navigation": False,
             "grid": {"type": 1, "size": c["grid_px"], "distance": c["grid_ft"], "units": "ft"},
             "flags": {FLAG: {"worldId": a.place, "calib": calib, **extra}}}
    if a.lighting and sc is None:                       # flat scene: the map image already carries the baked sun shadows; Foundry gets plain global light, no darkness
        import foundry_lighting as flt
        sdata["environment"] = flt.flat_environment(flt.load_lighting(a.lighting))
    mode = a.scene_mode or "flat"
    if a.scene_mode or sc is None and not a.scene_uuid:     # explicit --scene-mode, or a brand-new scene (default flat); never silently re-flag an existing one
        sdata["flags"].update(scene_mode_flags(mode, a.scene_flag))
        result["scene_mode"] = mode
    if sc is not None and not pipe_id(sc):          # confirmed adoption of an existing scene: change only what we manage
        br.call("update", uuid=a.scene_uuid, data={"flags": {FLAG: {"pipelineId": pid, "worldId": a.place, "calib": calib, **extra}}})
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
    if getattr(a, "link", False):
        place_link(a.place, uuid)
        result["linked"] = True
    return result


def cmd_link_region(br, a):
    """Outline of a region child drawn on its PARENT scene (same calibration as the parent push). Dry unless --apply."""
    rf = region_flags(a.place)
    if not rf:
        raise PushError(f"{a.place} is not a region child (no region.json)")
    require_module(br)
    uuid = a.parent_scene_uuid
    if not uuid and a.parent_scene_name:
        hit = br.call("find_by_flag", documentName="Scene", id=f"scene:{rf['parent']}:{slug(a.parent_scene_name)}")
        if not hit:
            raise PushError(f"no pipeline scene for parent {rf['parent']} named {a.parent_scene_name}")
        uuid = hit[0]["uuid"]
    if not uuid:
        raise PushError("give --parent-scene-uuid or --parent-scene-name")
    sc = br.call("get", uuid=uuid)
    calib = (sc.get("flags", {}).get(FLAG, {}) or {}).get("calib")
    if not calib:
        raise PushError("the parent scene has no pipeline calibration (push it with this tool first)")
    doc = _poly_drawing(rf["child"].replace("/", "_"), "region", [tuple(p) for p in rf["polygon_parent_ft"]], calib, "#d4202a", "#d4202a")
    doc["data"]["fillAlpha"] = 0.12
    doc["data"]["flags"] = {FLAG: {"childPlace": rf["child"], "childScene": a.child_scene_uuid, "region": rf["name"]}}
    cx = sum(p[0] for p in rf["polygon_parent_ft"]) / len(rf["polygon_parent_ft"])
    cy = sum(p[1] for p in rf["polygon_parent_ft"]) / len(rf["polygon_parent_ft"])
    res = {"ok": True, "parent_scene": uuid, "centroid_ft": [round(cx, 1), round(cy, 1)], "drawing": doc, "applied": bool(a.apply)}
    if not a.apply:
        res["note"] = "dry run: nothing written; add --apply to create/update the flagged outline drawing on the parent scene"
        return res
    res["ops"] = br.call("upsert_many", documentName="Drawing", parentUuid=uuid, items=[doc], prefix="draw:region:", prune=False)
    return res


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


# ------------------------------------------------------------------ 3D models (world pack placements -> 3D Canvas tiles)
def publish_glb(src, rel, set_name, place, root, dry=False):
    """Copy a model into <root>/art/<place>/models/<set_name>/<rel with _vNNN>. A byte-identical newest version is reused (no clutter, Foundry caches by path).
    The shared textures folder (models/textures) is copied next to it, so the GLB relative texture uris resolve. Returns the Foundry path."""
    import shutil
    base = os.path.join(root, "art", place, "models", set_name)
    stem, ext = os.path.splitext(rel)
    d = os.path.join(base, os.path.dirname(rel))
    bn = os.path.basename(stem)
    pat = re.compile(re.escape(bn) + r"_v(\d+)" + re.escape(ext) + "$")
    have = sorted((int(m.group(1)), f) for f in (os.listdir(d) if os.path.isdir(d) else []) for m in [pat.match(f)] if m)
    with open(src, "rb") as f:
        data = f.read()
    with open(os.path.join(d, have[-1][1]), "rb") if have else io.BytesIO(b"") as f0:
        same = bool(have) and f0.read() == data
    if same:
        name = have[-1][1]
    else:
        name = f"{bn}_v{(have[-1][0] if have else 0) + 1:03d}{ext}"
        if not dry:
            os.makedirs(d, exist_ok=True)
            with open(os.path.join(d, name), "wb") as f:
                f.write(data)
    tex = os.path.join(os.path.dirname(os.path.abspath(src)), *([".."] * rel.count("/")), "textures")
    if not dry and os.path.isdir(tex):
        shutil.copytree(tex, os.path.join(base, "textures"), dirs_exist_ok=True)
    sub = os.path.dirname(rel)
    return f"assets/varrenmoor-3d/art/{place}/models/{set_name}/" + (sub + "/" if sub else "") + name


def build_model_tiles(doc, scene_calib, a, publish=None):
    """placements.json -> [{"id", "data"}] Tile items for upsert_many. scene_calib: {ppf, x0, y0, sceneX, sceneY}; sizes scale by ppf so models keep
    their true size on a scene whose px-per-foot differs from the pack. publish(entry, rel) -> foundry path. Tile x,y = pivot (centre), elevation in ft."""
    c = scene_calib
    ppf = c["ppf"]
    place = doc["place"]
    want_l = set(a.layers.split(",")) if a.layers else None
    want_i = set(a.ids.split(",")) if a.ids else None
    items = []
    for e in doc["files"]:
        if want_l and not (set(e.get("layers", [e["layer"]])) & want_l):
            continue
        if want_i and not (want_i & set(e["ids"])):
            continue
        rel = e["file"]
        if a.lod and e.get("lods"):
            lod = next((l for l in e["lods"] if l["lod"] == a.lod), None)
            if lod:
                rel = lod["file"]
        path = publish(e, rel) if publish else rel
        sz = e["size_ft"]
        rot0 = e["tile"]["rotation"] + e.get("rotation_deg", 0.0)
        flags = lambda extra: {"levels-3d-preview": {"model3d": path, "autoGround": True, "autoCenter": False, "collision": False, "sight": False, **extra},
                               FLAG: {"modelFile": e["file"], "sha256": e["sha256"], "layer": e["layer"], "ids": e["ids"][:50]}}
        if e["kind"] == "instances":
            for ins in e["instances"]:
                px, py = c["sceneX"] + (ins["pivot_ft"][0] - c["x0"]) * ppf, c["sceneY"] + (ins["pivot_ft"][1] - c["y0"]) * ppf
                s = ins["scale"]
                items.append({"id": f"model:{place}:{ins['id']}", "data": {
                    "x": round(px), "y": round(py), "width": max(4, round(sz[0] * s * ppf)), "height": max(4, round(sz[1] * s * ppf)),
                    "elevation": round(ins["pivot_ft"][2] - doc["frame"]["z_origin_ft"], 2), "rotation": rot0 + ins["rotation_deg"],
                    "texture": {"src": "modules/levels-3d-preview/assets/blank.webp"}, "flags": flags({"depth": max(2, round(sz[2] * s * ppf))})}})
            continue
        px, py = c["sceneX"] + (e["pivot"]["x_ft"] - c["x0"]) * ppf, c["sceneY"] + (e["pivot"]["y_ft"] - c["y0"]) * ppf
        sc = e.get("scale", 1.0)
        items.append({"id": e["id"], "data": {
            "x": round(px), "y": round(py), "width": max(4, round(sz[0] * sc * ppf)), "height": max(4, round(sz[1] * sc * ppf)), "elevation": e["pivot"]["rel_z_ft"],
            "rotation": rot0, "texture": {"src": "modules/levels-3d-preview/assets/blank.webp"}, "flags": flags({"depth": max(2, round(sz[2] * sc * ppf))})}})
    return items


ASSET_PREFIX = "assets/varrenmoor-3d/"


def local_asset_path(foundry_path, root):
    """Foundry path assets/varrenmoor-3d/<rest> -> <assets root>/<rest> (None for paths outside our share)."""
    if not foundry_path or not foundry_path.startswith(ASSET_PREFIX):
        return None
    return os.path.join(root, *foundry_path[len(ASSET_PREFIX):].split("/"))


def http_status(url, timeout=30):
    """(status, size) of a GET, (None, reason) on a connection problem."""
    import urllib.request
    import urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, len(r.read())
    except urllib.error.HTTPError as e:
        return e.code, 0
    except Exception as e:      # noqa: BLE001 - report, do not crash a push over a probe
        return None, str(e)


def verify_models(paths, root, serve_url=None, allow_quantized=False, getter=None):
    """Every model path must exist in the shared assets folder (where Foundry serves it from), be a GLB 3D Canvas can load (glb_check) and, with serve_url
    (e.g. http://10.0.0.15:30000), answer HTTP 200 with the same size. Returns a list of problem strings (empty = fine)."""
    import glb_check
    getter = getter or http_status
    bad, seen = [], set()
    for p in paths:
        if not p or p in seen:
            continue
        seen.add(p)
        lp = local_asset_path(p, root)
        if lp is None:
            continue                                   # a module/world asset path we do not manage (baileywiki etc.)
        if not os.path.isfile(lp):
            bad.append(f"{p}: not found in the assets folder {root} (Foundry would log 'File format not supported or missing')")
            continue
        if p.lower().endswith((".glb", ".gltf")):
            bad += glb_check.validate_glb(lp, allow_quantized)
        if serve_url:
            st, size = getter(serve_url.rstrip("/") + "/" + p)
            if st != 200:
                bad.append(f"{p}: HTTP {st} from {serve_url} ({size if st is None else 'not served'})")
            elif size != os.path.getsize(lp):
                bad.append(f"{p}: served {size} bytes, file is {os.path.getsize(lp)}")
    return bad


def _tex_flags(a):
    """--scene-flag list plus the baked ground texture (--table-texture): renderTable matcustom + tableTex, renderBackground off."""
    fl = list(a.scene_flag or [])
    if getattr(a, "lighting", None):
        import foundry_lighting as flt
        fl = [f"{k}={json.dumps(v)}" for k, v in flt.scene_light_flags(flt.load_lighting(a.lighting)).items()] + fl
    if getattr(a, "table_texture", None):
        fl = ["renderTable=\"matcustom\"", "renderBackground=false", "tableTex=" + json.dumps(a.table_texture)] + fl
    return fl


def cmd_bake_texture(br, a):
    """OFFLINE (no Foundry call): turn a rendered map PNG into the ground texture of a 3D Canvas scene. Drawings, labels and fills do not render
    in 3D Canvas, so the finished 2D map is baked into the table texture instead. Writes a versioned image + bake.json (the exact scene flags and
    the footprint in feet) and prints them; a later `push-models --table-texture <path>` (or --scene-flag tableTex=...) applies it."""
    from PIL import Image
    if not a.image or not os.path.exists(a.image):
        raise PushError("give --image <rendered map png>")
    img = Image.open(a.image)
    img.load()
    if a.crop_margin_pt:      # drop the paper margin of a page export (pt * dpi/72): --crop-margin-pt 36 --dpi 120; --window then names the cropped area
        m = int(round(float(a.crop_margin_pt) * float(a.dpi or 72.0) / 72.0))
        img = img.crop((m, m, img.size[0] - m, img.size[1] - m))
    w, h = img.size
    if a.window:
        x0, y0, x1, y1 = [float(v) for v in a.window.split(",")]
        ppf = w / (x1 - x0)
        if abs(h / (y1 - y0) - ppf) / ppf > 0.02:
            raise PushError(f"image {w}x{h}px does not match window {a.window} (px/ft differs by axis): crop the paper margin (--crop-margin-pt) or re-render the same window")
    elif a.px_per_ft:
        ppf, x0, y0 = float(a.px_per_ft), 0.0, 0.0
        x1, y1 = x0 + w / ppf, y0 + h / ppf
    else:
        raise PushError("give --px-per-ft or --window x0,y0,x1,y1 (ft) of the image")
    if img.mode != "RGB":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.getchannel("A") if "A" in img.getbands() else None)
        img = bg
    max_px = int(a.max_px or 8192)
    if max(img.size) > max_px:
        f = max_px / max(img.size)
        img = img.resize((int(w * f), int(h * f)), Image.LANCZOS)
        ppf *= f
        w, h = img.size
    out = a.out_dir or os.path.join(REPO, "world", a.place, "export", "baked")
    root = (a.assets_dir or assets_dir()) if a.publish else out
    ver, path = publish_image(img, f"art/{a.place}/maps", a.name or "ground", root, a.format, False)
    tex = a.table_texture_path or path
    flags = {"renderBackground": False, "renderTable": "matcustom", "tableTex": tex}
    doc = {"ok": True, "place": a.place, "image": os.path.join(root, *path.split("assets/varrenmoor-3d/", 1)[1].split("/")), "foundry_path": tex, "version": ver,
           "size_px": [w, h], "px_per_ft": round(ppf, 4), "footprint_ft": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
           "size_ft": [round(w / ppf, 2), round(h / ppf, 2)], "published": bool(a.publish), "scene_flags": {L3D: flags},
           "scene_flag_args": [f"--scene-flag={k}={json.dumps(v)}" for k, v in flags.items()],
           "notes": ["No live push was made. tableTex is shown tiled/stretched by 3D Canvas over the padded table: check scale in the scene [TEST], "
                     "see FOUNDRY_3D_CANVAS_NOTES.md section 7.",
                     "Keep the terrain GLB at the same footprint or leave it out; do not also enable renderBackground (z-fighting)."]}
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "bake.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1)
    LOG(f"baked {w}x{h}px ground texture, {doc['size_ft'][0]} x {doc['size_ft'][1]} ft at {doc['px_per_ft']} px/ft -> {path}")
    return doc


def cmd_push_models(br, a):
    pp = a.placements or os.path.join(REPO, "world", a.place, "export", "placements.json")
    with open(pp, encoding="utf-8") as f:
        doc = json.load(f)
    base = os.path.dirname(pp)
    place = doc["place"]
    fr = doc["frame"]
    set_name = a.set_name or ("split" if "merge" not in doc else doc["merge"]["preset"] + "_" + os.path.basename(base).rsplit("_", 1)[-1])
    sc, uuid, calib = None, a.scene_uuid, None
    if not a.dry_run:
        require_module(br)
    if uuid:
        sc = br.call("get", uuid=uuid)
        calib = (sc.get("flags", {}).get(FLAG, {}) or {}).get("calib")
        if not pipe_id(sc) and not a.yes:
            return {"ok": False, "needs_confirm": True, "scene_uuid": uuid,
                    "summary": f"Scene {sc['name']} was not created by the pipeline; tiles flagged model:* will be added to it (existing tiles untouched)."}
    ppf = float(a.px_per_ft or (calib or {}).get("ppf") or fr["px_per_ft"])
    c = {"ppf": ppf, "x0": (calib or {}).get("x0", 0.0), "y0": (calib or {}).get("y0", 0.0), "sceneX": (calib or {}).get("sceneX", 0), "sceneY": (calib or {}).get("sceneY", 0)}
    root = a.assets_dir or assets_dir()
    pub = lambda e, rel: publish_glb(os.path.join(base, rel), rel[len("models/"):], set_name, place, root, a.dry_run)
    items = build_model_tiles(doc, c, a, pub)
    LOG(f"{len(items)} model tiles for {len(doc['files'])} files at {ppf:g} px/ft ({'calibration of the scene' if calib else 'pack default'})")
    result = {"ok": True, "tiles": len(items), "px_per_ft": ppf, "set": set_name, "dry_run": bool(a.dry_run), "sample": items[0] if items else None}
    if a.dry_run:
        return result
    if not uuid:
        if not a.scene_name:
            raise PushError("give --scene-uuid or --scene-name")
        pid = f"scene:{place}:{slug(a.scene_name)}"
        hit = br.call("find_by_flag", documentName="Scene", id=pid)
        if hit:
            uuid = hit[0]["uuid"]
        else:
            if any(r["name"].lower() == a.scene_name.lower() for r in br.call("list", collection="Scene")):
                raise PushError(f"a scene named {a.scene_name} exists and was not created by the pipeline; pass its uuid with --scene-uuid")
            W, H = round(fr["width_ft"] * ppf), round(fr["height_ft"] * ppf)
            cal = {"x0": 0.0, "y0": 0.0, "ppf": ppf, "grid_px": round(5 * ppf), "grid_ft": 5.0, "width": W, "height": H, "sceneX": 0, "sceneY": 0, "place": place, "view": "models"}
            r = br.call("upsert_by_flag", documentName="Scene", id=pid, data={"name": a.scene_name, "width": W, "height": H, "padding": 0, "navigation": False,
                                                                           "grid": {"type": 1, "size": round(5 * ppf), "distance": 5, "units": "ft"},
                                                                           "flags": {FLAG: {"worldId": place, "calib": cal}, **scene_mode_flags(a.scene_mode or "3d", _tex_flags(a))}})
            uuid = r["uuid"]
            result["scene_mode"] = a.scene_mode or "3d"
    if a.scene_mode and not result.get("scene_mode"):        # explicit mode on an existing scene: merge only the mode keys
        br.call("update", uuid=uuid, data={"flags": scene_mode_flags(a.scene_mode, _tex_flags(a))})
        result["scene_mode"] = a.scene_mode
    bad = verify_models([i["data"]["flags"][L3D]["model3d"] for i in items], root, getattr(a, "serve_url", None) or os.environ.get("FOUNDRY_URL"), getattr(a, "allow_quantized", False))
    if bad:        # never create tiles Foundry cannot load: one failing tile breaks the 3D render loop of the whole scene
        raise PushError(f"{len(bad)} model problem(s), no tiles were written:\n  " + "\n  ".join(bad[:25]))
    r = br.call("upsert_many", documentName="Tile", parentUuid=uuid, items=items, prefix="model:", prune=bool(a.prune))
    LOG(f"tiles: {r}")
    result.update(scene_uuid=uuid, tile_ops=r)
    return result


def build_light_docs(doc, c, only_types=None, animation=None):
    """placements.json "lights" (interior hints from worldpack_interiors) -> AmbientLight Tile-style items for upsert_many.
    dim/bright are in ft (the scenes use a 5 ft grid with distance in ft); elevation relative to the pack z origin."""
    ppf, place, z0 = c["ppf"], doc["place"], doc["frame"]["z_origin_ft"]
    out = []
    for lt in list(doc.get("lights", [])) + [x for e in doc.get("files", []) for x in e.get("lights", [])]:     # per-file entries (worldpack_split) or a top-level list
        if only_types and lt["type"] not in only_types:
            continue
        px, py = c["sceneX"] + (lt["point"][0] - c["x0"]) * ppf, c["sceneY"] + (lt["point"][1] - c["y0"]) * ppf
        l3d = {"enableParticle": False}      # never torch/smoke/fire particle presets (house rule); plain point light, optional --light-animation
        out.append({"id": f"light:{place}:{lt['id']}", "data": {
            "x": round(px), "y": round(py), "elevation": round(lt.get("z_abs_ft", z0 + lt.get("z_ft", 5.0)) - z0, 2), "rotation": 0, "walls": False, "vision": False,
            "config": {"dim": lt.get("dim_ft", 10), "bright": lt.get("bright_ft", 4), "color": lt.get("color", "#ffffff"), "alpha": min(0.9, max(0.1, lt.get("intensity", 0.5))),
                       "luminosity": 0.5, "animation": {"type": animation or None, "speed": 2, "intensity": 2}},
            "flags": {"levels-3d-preview": l3d, FLAG: {"lightId": lt["id"], "building": lt.get("building"), "type": lt["type"]}}}})
    return out


def cmd_push_lights(br, a):
    pp = a.placements or os.path.join(REPO, "world", a.place, "export", "placements.json")
    with open(pp, encoding="utf-8") as f:
        doc = json.load(f)
    if not a.scene_uuid:
        raise PushError("give --scene-uuid")
    sc = br.call("get", uuid=a.scene_uuid)
    calib = (sc.get("flags", {}).get(FLAG, {}) or {}).get("calib") or {}
    c = {"ppf": float(a.px_per_ft or calib.get("ppf") or doc["frame"]["px_per_ft"]), "x0": calib.get("x0", 0.0), "y0": calib.get("y0", 0.0),
         "sceneX": calib.get("sceneX", 0), "sceneY": calib.get("sceneY", 0)}
    items = build_light_docs(doc, c, set(a.layers.split(",")) if a.layers else None, a.light_animation)      # --layers = light types (hearth,window)
    if a.lighting:                                                                 # the 2D lights of the Illustrator lighting config, same positions
        import foundry_lighting as fl
        rg = os.path.join(REPO, "world", a.place, "region.json")
        org = (json.load(open(rg, encoding="utf-8")).get("transform", {}).get("origin_ft") if os.path.exists(rg) else None) or [0.0, 0.0]
        items += fl.point_light_docs(fl.load_lighting(a.lighting), org, c["ppf"], (c["sceneX"], c["sceneY"]), c["x0"], c["y0"], doc["place"])
    LOG(f"{len(items)} lights")
    if a.dry_run:
        return {"ok": True, "lights": len(items), "sample": items[:1]}
    r = br.call("upsert_many", documentName="AmbientLight", parentUuid=a.scene_uuid, items=items, prefix="light:", prune=True)
    return {"ok": True, "scene_uuid": a.scene_uuid, "light_ops": r}


# ------------------------------------------------------------------ cli
def _scene_padding_arg(padding_args, default=0.25):
    for i, x in enumerate(padding_args or []):
        if x == "--scene-padding" and i + 1 < len(padding_args):
            return float(padding_args[i + 1])
        if x.startswith("--scene-padding="):
            return float(x.split("=", 1)[1])
    return default


SCENE_3D_ORDER = ["geometry", "models", "foliage", "padding", "lights", "flags", "verify"]     # skybox + lighting flags last: nothing after them may overwrite them
PADDING_PUSH = None          # tests replace this; default calls padding_heightmap.main(["push", ...])


def cmd_push_scene_3d(br, a):
    """One idempotent push of a whole 3D test scene: terrain/buildings -> foliage -> padding -> lights -> skybox + sun/ambient/tint flags (last) -> verification
    (files exist and load, scene flags read back). Re-running changes nothing that is byte-identical (versioned assets, id-keyed upserts)."""
    if not a.scene_uuid:
        raise PushError("give --scene-uuid")
    done, root = [], a.assets_dir or assets_dir()
    base = argparse.Namespace(**vars(a))

    def models(placements):
        b = argparse.Namespace(**vars(base))
        b.placements, b.prune, b.cmd, b.scene_mode, b.lighting, b.set_name = placements, False, "push-models", None, None, None
        b.assets_dir = root
        r = cmd_push_models(br, b)
        if not r.get("ok"):
            raise PushError(f"push-models failed: {r}")
        return {"tiles": r["tiles"], "set": r["set"]}

    steps = {}
    if not a.no_padding and not a.dry_run:        # geometry first: padding moves the scene rect (sceneX/Y), and every tile position is computed from it
        import padding_heightmap as ph
        sc0 = br.call("get", uuid=a.scene_uuid)
        pad = _scene_padding_arg(a.padding_args)
        gpx = (sc0.get("grid") or {}).get("size") or 100
        _, _, sx, sy = ph.canvas_dims(sc0["width"], sc0["height"], pad, gpx)
        br.call("update", uuid=a.scene_uuid, data={"padding": pad, "flags": {FLAG: {"calib": {"sceneX": sx, "sceneY": sy}}}})
        steps["geometry"] = {"padding": pad, "sceneX": sx, "sceneY": sy}
        done.append("geometry")
    steps["models"] = models(a.placements or os.path.join(REPO, "world", a.place, "export", "placements.json"))
    done.append("models")
    if a.foliage_placements:
        steps["foliage"] = models(a.foliage_placements)
        done.append("foliage")
    if not a.no_padding:
        args = ["push", "--place", a.place, "--scene-uuid", a.scene_uuid, "--assets-dir", root] + list(a.padding_args or [])
        if not any(x.startswith("--scene-padding") for x in args):      # the surroundings are generated for a padded scene; with padding 0 the heightmap table would cover the town
            args += ["--scene-padding", str(_scene_padding_arg(a.padding_args))]
        if a.dry_run:
            args.append("--dry-run")
        import padding_heightmap
        rc = (PADDING_PUSH or padding_heightmap.main)(args)
        if rc not in (0, None):
            raise PushError(f"padding push failed ({rc})")
        steps["padding"] = {"args": args}
        done.append("padding")
    if a.with_lights:
        b = argparse.Namespace(**vars(base))
        b.cmd, b.layers, b.px_per_ft = "push-lights", None, None
        steps["lights"] = cmd_push_lights(br, b)
        done.append("lights")
    flags = {}
    if not a.no_skybox:
        src = os.path.join(REPO, "world", a.place, "export", "skybox", f"{a.skybox_preset}.webp")
        if not os.path.exists(src):
            raise PushError(f"{src} not found; run skybox.py generate first")
        _, path = publish_file(src, f"art/{a.place}/skybox", a.skybox_preset, root, dry=bool(a.dry_run))
        flags.update({"exr": path, "skybox": ""})
    if a.lighting:
        import foundry_lighting as flt
        flags.update(flt.scene_light_flags(flt.load_lighting(a.lighting)))
    for o in a.scene_flag or []:
        k, _, v = o.partition("=")
        try:
            flags[k] = json.loads(v)
        except ValueError:
            flags[k] = v
    if flags and not a.dry_run:
        br.call("update", uuid=a.scene_uuid, data={"flags": {L3D: flags}})
    steps["flags"] = flags
    done.append("flags")
    problems = []
    if not a.dry_run:
        sc = br.call("get", uuid=a.scene_uuid)
        f3 = (sc.get("flags", {}) or {}).get(L3D, {}) or {}
        for k, v in flags.items():
            if f3.get(k) != v:
                problems.append(f"scene flag {k} is {f3.get(k)!r}, expected {v!r}")
        paths = [((t.get("flags", {}) or {}).get(L3D, {}) or {}).get("model3d") for t in sc.get("tiles", [])]
        problems += verify_models(paths + ([f3.get("exr")] if f3.get("exr") else []), root, a.serve_url or os.environ.get("FOUNDRY_URL"), a.allow_quantized)
    steps["verify"] = {"problems": problems}
    done.append("verify")
    res = {"ok": not problems, "order": done, "scene_uuid": a.scene_uuid, "steps": steps, "problems": problems}
    if problems:
        res["error"] = "; ".join(problems[:5])
    return res


def parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["status", "places", "list", "export-info", "push-scene", "push-token", "push-actor", "push-item", "push-models", "delete-scene", "link-region", "bake-texture", "push-lights", "import-scene", "push-scene-3d"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--page")
    ap.add_argument("--grid-major", "--major", dest="major", type=int)
    ap.add_argument("--kinds")
    ap.add_argument("--scene-uuid")
    ap.add_argument("--parent-scene-uuid")
    ap.add_argument("--parent-scene-name")
    ap.add_argument("--child-scene-uuid")
    ap.add_argument("--apply", action="store_true", help="link-region: really write (default is a dry run)")
    ap.add_argument("--scene-name")
    ap.add_argument("--image")
    ap.add_argument("--portrait")
    ap.add_argument("--token")
    ap.add_argument("--max-px", type=int, default=8192)
    ap.add_argument("--ft-per-grid", type=float)
    ap.add_argument("--upscale", type=float, default=1.0, help="push-scene: resample the image up by this factor (low-dpi exports)")
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
    ap.add_argument("--placements", help="push-models: placements.json (default world/<place>/export/placements.json)")
    ap.add_argument("--layers", help="push-models: only these layers (comma list)")
    ap.add_argument("--ids", help="push-models: only files containing these entity ids")
    ap.add_argument("--lod", type=int, default=0, help="push-models: 0 = full models, 1/2 = cheaper decimated variants from a merge")
    ap.add_argument("--px-per-ft", type=float, help="push-models: scene px per foot (default: the scene calibration, else the pack value)")
    ap.add_argument("--set-name", help="push-models: folder name under art/<place>/models/")
    ap.add_argument("--scene-mode", choices=["flat", "3d"], help="3D Canvas scene flags: flat = 2D map (auto3d off), 3d = terrain/model scene. Default: flat for push-scene, 3d for push-models; "
                    "applied to new scenes, and to existing ones only when given explicitly")
    ap.add_argument("--scene-flag", action="append", default=[], metavar="KEY=VALUE", help="override one levels-3d-preview scene flag (JSON value), repeatable")
    ap.add_argument("--table-texture", dest="table_texture", help="push-models: Foundry path of a baked ground texture (bake-texture output) used as the scene's tableTex")
    ap.add_argument("--window", help="bake-texture: map window x0,y0,x1,y1 in ft that the image covers (region_render prints window_ft)")
    ap.add_argument("--crop-margin-pt", type=float, help="bake-texture: crop this paper margin (pt) off every side of a page export (with --dpi)")
    ap.add_argument("--dpi", type=float, help="bake-texture: dpi of the image (for --crop-margin-pt)")
    ap.add_argument("--out-dir", dest="out_dir", help="bake-texture: where the baked image and bake.json go (default world/<place>/export/baked)")
    ap.add_argument("--table-texture-path", dest="table_texture_path", help="bake-texture: tableTex value to record (default: the asset path)")
    ap.add_argument("--publish", action="store_true", help="bake-texture: copy the image into the shared assets folder Foundry serves (otherwise only written locally)")
    ap.add_argument("--lighting", help="place id (panel_state.json lighting) or lighting JSON: sun/ambient -> scene flags (push-models), 2D point lights -> AmbientLights (push-lights)")
    ap.add_argument("--light-animation", dest="light_animation", help="push-lights: Foundry light animation type for interior hints (default none; never torch/smoke particles)")
    ap.add_argument("--prune", action="store_true", help="push-models: delete pipeline model tiles that are not in this push")
    ap.add_argument("--serve-url", dest="serve_url", help="push-models/push-scene-3d: Foundry base URL (default env FOUNDRY_URL); every model is fetched over HTTP and must answer 200 with the right size")
    ap.add_argument("--allow-quantized", action="store_true", help="push-models: accept KHR_mesh_quantization GLBs (default: rejected, see glb_check.py)")
    ap.add_argument("--foliage-placements", dest="foliage_placements", help="push-scene-3d: placements.json of a foliage merge (optimized/foliage_vNNN)")
    ap.add_argument("--skybox-preset", dest="skybox_preset", default="clear_day", help="push-scene-3d: world/<place>/export/skybox/<preset>.webp")
    ap.add_argument("--no-skybox", action="store_true")
    ap.add_argument("--no-padding", action="store_true", help="push-scene-3d: skip the padding apron / table heightmap step")
    ap.add_argument("--padding-arg", dest="padding_args", action="append", default=[], help="push-scene-3d: extra argument for padding_heightmap push (repeatable, use --padding-arg=--preset --padding-arg=bowl-ridge)")
    ap.add_argument("--with-lights", dest="with_lights", action="store_true", help="push-scene-3d: also push the interior point lights")
    # import-scene (foundry_import.py) and the place <-> scene link
    ap.add_argument("--place-id", help="import-scene: id of the new place (default: slug of the scene name)")
    ap.add_argument("--include", help="import-scene: extra data to import: walls (default), lights, tokens, notes (comma list)")
    ap.add_argument("--no-image", action="store_true", help="import-scene: do not fetch the background image")
    ap.add_argument("--closed-as", default="buildings", choices=["buildings", "lines"], help="import-scene: closed wall loops become building outlines (default) or stay lines")
    ap.add_argument("--force", action="store_true", help="import-scene: overwrite an existing world/<id>")
    ap.add_argument("--scene-json", help="import-scene: read the scene document from this JSON file instead of the bridge (offline / tests)")
    ap.add_argument("--link", action="store_true", help="push-scene: after a successful push store the scene uuid in place.json links.foundry_scene (later pushes default to it)")
    return ap


def cmd_import_scene(br, a):
    import foundry_import
    return foundry_import.cmd_import_scene(br, a)


def place_link(place, uuid=None):
    """links.foundry_scene of world/<place>/place.json; with `uuid` set it (create the key when missing). None when unset or unreadable."""
    p = os.path.join(REPO, "world", place, "place.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if uuid:
        d.setdefault("links", {})["foundry_scene"] = uuid
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1, ensure_ascii=False)
            f.write("\n")
    return (d.get("links") or {}).get("foundry_scene")


CMDS = {"status": cmd_status, "places": cmd_places, "list": cmd_list, "export-info": cmd_export_info, "push-scene": cmd_push_scene,
        "push-token": cmd_push_token, "push-actor": cmd_push_actor, "push-item": cmd_push_item, "push-models": cmd_push_models, "delete-scene": cmd_delete_scene,
        "link-region": cmd_link_region, "bake-texture": cmd_bake_texture, "push-lights": cmd_push_lights, "import-scene": cmd_import_scene, "push-scene-3d": cmd_push_scene_3d}


def main(argv=None, bridge=None):
    # --- padding (heightmap + apron + textures): own parser, see padding_heightmap.py
    _av = sys.argv[1:] if argv is None else list(argv)
    if _av and _av[0] == "push-padding":
        import padding_heightmap
        return padding_heightmap.main(["push"] + _av[1:])
    # --- end padding
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
