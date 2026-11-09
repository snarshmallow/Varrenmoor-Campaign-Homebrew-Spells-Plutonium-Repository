"""Bridgehollow street scenes: one winter 3D Foundry scene per named street (and the two squares), cut out of the town with region_extract.py.

  python illustrator/generators/bridgehollow_streets.py list                       street list, windows (ft), parts, child ids, scene names (reads only)
  python illustrator/generators/bridgehollow_streets.py extract --street ID|all [--dry-run] [--force]
        world/bridgehollow__street_<slug>[_part_N]: region_extract (rect window, local origin, 5 ft grid, details doors/roofs/chimneys/lots/fences/kerbs),
        then winter twins of the ring styles (bh_* -> bh_*_winter; other buildings keep their look), the parent's winter foliage inside the window
        (world/<child>/foliage.json + scatter/foliage.json, shifted to the child origin). Idempotent: skipped when region.json has the same window and
        parent fingerprint (unless --force).
  python illustrator/generators/bridgehollow_streets.py build   --street ID|all     world pack export (roofs per_building, winter style/phases) -> split -> merge
        (layer preset, winter foliage chunks attached) -> street lamps (old_wooden_lantern, spacing from 100 ft up until <= 8 lamps). Needs >= 3 GB free RAM.
  python illustrator/generators/bridgehollow_streets.py push    --street ID|all [--dry-run]   NEW scene 'Bridgehollow - <Name> (Winter)' (push-models, 10 px/ft,
        5 ft grid) -> push-scene-3d (winter sky, overcast sun/fog, hybrid lights <= 32, small winter apron) -> set-collision -> sync-doors -> verify
  python illustrator/generators/bridgehollow_streets.py verify  --street ID|all     read-only: tiles per layer, foliage tiles, lights, flags, scene-audit -> status table
  python illustrator/generators/bridgehollow_streets.py run     --street ID|all     extract + build + push + verify

ID = a street key from `list` (warden_street, cooper_row, market_square, ...) or a part id (warden_street_part_1).
Status table: illustrator/out/bridgehollow_street_scenes.md (+ .json). Every command prints ONE final JSON line.
Street list rules (streets.json): 'Alley N' lanes are skipped; 'X 2' joins 'X' when the two touch (<= 40 ft), else it is its own street named after
its compass side ('Weavers Walk South'), or plain 'X' when there is no 'X'; a bridge joins the road it touches. Window = street buffered 120 ft
(100 ft when that fits), at most 650 ft square; a longer street is cut in two at the junction nearest its middle ('Part 1', 'Part 2').
"""
import argparse
import datetime
import glob
import json
import math
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PARENT = "bridgehollow"
BUFFER_FT, MIN_BUFFER_FT, CAP_FT = 120.0, 100.0, 650.0
MERGE_FT = 40.0
DETAIL = "doors,roofs,chimneys,lots,fences,kerbs"          # no generated detail trees: the town's winter scatter is the foliage
PRIORITY = ["warden_street", "cooper_row", "market_square", "court_square", "pilgrim_road"]
SQUARES = {"market_square": "sqr_market", "court_square": "sqr_court"}
PX_PER_FT, GRID_FT = 10.0, 5.0
MAX_LAMPS, LAMP_STYLE, LAMP_SPACING = 8, "old_wooden_lantern", 100.0
MAX_LIGHTS = 32
SKY, SUN = "winter", "overcast"
PADDING_ARGS = ["--scene-padding=0.1", "--preset=rolling-hills", "--texture=winter", "--blend=80"]
STATUS_MD = os.path.join(REPO, "illustrator", "out", "bridgehollow_street_scenes.md")
STATUS_JSON = os.path.join(REPO, "illustrator", "out", "bridgehollow_street_scenes.json")
LOG = lambda m: print(m, flush=True)  # noqa: E731


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_")


def _rj(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _wj(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1, ensure_ascii=False)
        f.write("\n")


def world_dir(place, root=None):
    return os.path.join(root or os.path.join(REPO, "world"), place)


# ------------------------------------------------------------------ street list
def _compass(dx, dy):
    if abs(dx) >= abs(dy):
        return "East" if dx > 0 else "West"
    return "South" if dy > 0 else "North"


def street_groups(streets):
    """streets.json entries -> ordered [{key, name, ids, kind}] of the named streets (see module doc)."""
    from shapely.geometry import LineString
    line = {s["id"]: LineString(s["geometry"]["points"]) for s in streets}
    base = {}
    for s in streets:
        n = s["name"].strip()
        if re.match(r"(?i)^alley\b", n) or s.get("kind") == "bridge":
            continue
        b = re.sub(r"\s+\d+$", "", n)
        base.setdefault(b, []).append(s)
    groups = []
    for b, ss in base.items():
        ss.sort(key=lambda s: (s["name"].strip() != b, s["id"]))      # the un-numbered one first
        main = [ss[0]]
        rest = []
        for s in ss[1:]:
            if min(line[s["id"]].distance(line[m["id"]]) for m in main) <= MERGE_FT:
                main.append(s)
            else:
                rest.append(s)
        groups.append({"name": b, "ids": [s["id"] for s in main]})
        for s in rest:
            c0, c1 = line[main[0]["id"]].centroid, line[s["id"]].centroid
            groups.append({"name": f"{b} {_compass(c1.x - c0.x, c1.y - c0.y)}", "ids": [s["id"]]})
    for s in streets:                                              # bridges join the road they touch
        if s.get("kind") == "bridge":
            for g in groups:
                if any(line[s["id"]].distance(line[i]) <= 1.0 for i in g["ids"]):
                    g["ids"].append(s["id"])
                    break
    for g in groups:
        g["key"], g["kind"] = slug(g["name"]), "street"
    return groups


def square_groups(districts):
    out = []
    for key, did in SQUARES.items():
        d = next((x for x in districts if x["id"] == did), None)
        if d:
            out.append({"key": key, "name": d.get("name") or key.replace("_", " ").title(), "ids": [did], "kind": "square"})
    return out


def _clamp_rect(r, W, H, cap=CAP_FT):
    """Crop a rect to at most cap x cap round its centre, then into the place [0,W]x[0,H]."""
    x0, y0, x1, y1 = r
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if x1 - x0 > cap:
        x0, x1 = cx - cap / 2, cx + cap / 2
    if y1 - y0 > cap:
        y0, y1 = cy - cap / 2, cy + cap / 2
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(float(W), x1), min(float(H), y1)
    return [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)]


def _rect_of(geom, buf):
    return list(geom.buffer(buf).bounds)


def _fits(r, cap=CAP_FT):
    return r[2] - r[0] <= cap + 1e-6 and r[3] - r[1] <= cap + 1e-6


def window_parts(geom, W, H, junctions=(), buffer=BUFFER_FT, min_buffer=MIN_BUFFER_FT, cap=CAP_FT):
    """-> [rect] (one, or two for a long street). geom: shapely line(s) or polygon in parent feet; junctions: points where other streets meet it."""
    from shapely.geometry import LineString, Point
    from shapely.ops import linemerge, substring
    for b in (buffer, min_buffer):
        r = _rect_of(geom, b)
        if _fits(r, cap):
            return [_clamp_rect(r, W, H, cap)]
    if geom.geom_type == "MultiLineString":
        m = linemerge(geom)
        geom = m if m.geom_type == "LineString" else max(m.geoms, key=lambda g: g.length)
    if geom.geom_type != "LineString":
        return [_clamp_rect(_rect_of(geom, min_buffer), W, H, cap)]
    L = geom.length
    cands = [geom.project(Point(p)) for p in junctions]
    cands = [s for s in cands if 0.2 * L < s < 0.8 * L]
    s = min(cands, key=lambda v: abs(v - L / 2)) if cands else L / 2
    out = []
    for a, b in ((0.0, s), (s, L)):
        part = substring(geom, a, b)
        r = None
        for bb in (buffer, min_buffer):
            r = _rect_of(part, bb)
            if _fits(r, cap):
                break
        out.append(_clamp_rect(r, W, H, cap))
    return out


def scene_plan(root=None):
    """Every scene to build: [{key, part_key, name, scene_name, child, rect, ids, kind, part, parts}] in priority order."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    wd = world_dir(PARENT, root)
    streets = _rj(os.path.join(wd, "streets.json"))["streets"]
    districts = _rj(os.path.join(wd, "districts.json"))["districts"]
    b = _rj(os.path.join(wd, "place.json"))["bounds"]
    W, H = b["width_ft"], b["height_ft"]
    sl = {s["id"]: LineString(s["geometry"]["points"]) for s in streets}
    out = []
    for g in street_groups(streets) + square_groups(districts):
        if g["kind"] == "square":
            d = next(x for x in districts if x["id"] == g["ids"][0])
            geom, junc = Polygon(d["geometry"]["points"]), []
        else:
            geom = unary_union([sl[i] for i in g["ids"]])
            junc = []
            for sid, ln in sl.items():
                if sid in g["ids"]:
                    continue
                x = geom.intersection(ln.buffer(1.0))
                if not x.is_empty:
                    c = x.centroid
                    junc.append((c.x, c.y))
        rects = window_parts(geom, W, H, junc)
        for n, r in enumerate(rects, 1):
            multi = len(rects) > 1
            pk = g["key"] + (f"_part_{n}" if multi else "")
            nm = g["name"] + (f" Part {n}" if multi else "")
            out.append({"key": g["key"], "part_key": pk, "name": nm, "scene_name": f"Bridgehollow - {nm} (Winter)", "child": f"{PARENT}__street_{pk}",
                        "rect": r, "size_ft": [round(r[2] - r[0]), round(r[3] - r[1])], "ids": g["ids"], "kind": g["kind"], "part": n, "parts": len(rects)})
    rank = {k: i for i, k in enumerate(PRIORITY)}
    first = {}
    for i, p in enumerate(out):
        first.setdefault(p["key"], i)
    out.sort(key=lambda p: (rank.get(p["key"], len(rank)), first[p["key"]], p["part"]))
    return out


# 2026-11-09: the user does not want a submap per road: only the districts larger than the recommended size, and overlapping duplicates were deleted.
# 'all' therefore means this KEEP set (these still cover every Bridgehollow building); name any other street explicitly with --scenes KEY, or use 'every'.
KEEP_SCENES = ["market_square", "court_square", "warden_street_part_1", "pilgrim_road_part_1", "pilgrim_road_part_2", "cobbler_row",
               "weavers_walk_south_part_2", "thatchers_way"]


def select(plan, which):
    if which == "every":
        return plan
    if which in (None, "", "all"):
        return [p for p in plan if p["part_key"] in KEEP_SCENES or p["key"] in KEEP_SCENES]
    want = [w.strip() for w in which.split(",") if w.strip()]
    sel = [p for p in plan if p["key"] in want or p["part_key"] in want or p["child"] in want]
    if not sel:
        raise SystemExit(f"no street {which!r}; keys: " + ", ".join(sorted({p['key'] for p in plan})))
    return sel


# ------------------------------------------------------------------ extract
def winter_styles(cdir, presets=None):
    """bh_* style keys of the child buildings -> their *_winter twin (when that preset exists). -> number changed."""
    if presets is None:
        import building_styles as bs
        presets = bs.load_presets()
    n = 0
    for p in sorted(glob.glob(os.path.join(cdir, "buildings", "*.json"))):
        b = _rj(p)
        s = b.get("style")
        if isinstance(s, str) and s.startswith("bh_") and not s.endswith("_winter") and s + "_winter" in presets:
            b["style"] = s + "_winter"
            _wj(p, b)
            n += 1
    return n


def copy_foliage(parent_dir, cdir, rect, origin):
    """The parent's foliage.json items inside rect, shifted by -origin -> child foliage.json (+ scatter/foliage.json). -> item count."""
    src = _rj(os.path.join(parent_dir, "foliage.json"), {}) or {}
    x0, y0, x1, y1 = rect
    ox, oy = origin
    items = []
    for it in src.get("items", []):
        if x0 <= it["x"] <= x1 and y0 <= it["y"] <= y1:
            it = dict(it)
            it["x"], it["y"] = round(it["x"] - ox, 2), round(it["y"] - oy, 2)
            items.append(it)
    zones_used = {i.get("zone") for i in items}
    doc = {"format": src.get("format", "varrenmoor-foliage"), "version": 1, "place": os.path.basename(cdir), "units": "ft",
           "frame": "world feet: x east, y south, z up (elevation)", "counters": src.get("counters", {}),
           "zones": [z for z in src.get("zones", []) if z["id"] in zones_used], "items": sorted(items, key=lambda i: i["id"])}
    _wj(os.path.join(cdir, "foliage.json"), doc)
    try:
        import foliage
        fd = foliage.FoliageDoc(os.path.basename(cdir), os.path.join(cdir, "foliage.json"))
        foliage.export_pack_scatter(fd, foliage._lib(), place=os.path.basename(cdir), root=cdir)
    except Exception as e:                                    # scatter is derived data; a missing species library must not lose the foliage.json
        LOG(f"  scatter export skipped: {e}")
    return len(items)


def _region_current(cdir, p, fp):
    reg = _rj(os.path.join(cdir, "region.json"))
    if not reg:
        return False
    r = reg.get("region", {})
    same_rect = r.get("kind") == "rect" and [round(float(v), 1) for v in r.get("rect", [])] == [round(float(v), 1) for v in p["rect"]]
    src = reg.get("parent_source") or {}
    return same_rect and (fp is None or src.get("content_sha1") == fp.get("content_sha1"))


def extract_one(p, dry=False, force=False, root=None, out_root=None):
    import region_extract as rx
    cdir = world_dir(p["child"], out_root)
    res = {"child": p["child"], "rect": p["rect"], "size_ft": p["size_ft"]}
    fp = None
    try:
        fp = rx.parent_fingerprint(PARENT, root)
    except Exception:
        fp = None
    if dry:
        from shapely.geometry import box
        model = rx.load_parent(PARENT, root)
        reg = box(*p["rect"])
        coll, _, dropped, _ = rx.clip_model(model, reg, reg, {})
        pf = _rj(os.path.join(world_dir(PARENT, root), "foliage.json"), {}) or {}
        x0, y0, x1, y1 = p["rect"]
        trees = sum(1 for i in pf.get("items", []) if x0 <= i["x"] <= x1 and y0 <= i["y"] <= y1)
        styled = {}
        for b in coll["buildings"]:
            s = b.get("style") or "(default)"
            styled[s] = styled.get(s, 0) + 1
        res.update(dry_run=True, exists=os.path.exists(os.path.join(cdir, "region.json")), up_to_date=_region_current(cdir, p, fp),
                   buildings=len(coll["buildings"]), streets=len(coll["streets"]), trees=trees, styles=styled)
        return res
    if not force and _region_current(cdir, p, fp):
        res["skipped"] = "up to date (same window and parent)"
    else:
        r = rx.extract(PARENT, {"kind": "rect", "rect": p["rect"]}, name=p["name"], root=root, out_root=out_root, margin=0.0, scale=20.0, grid=GRID_FT,
                       detail=DETAIL, local_origin=True, child_id=p["child"], log=LOG)
        res["extract"] = r["report"]
    reg = _rj(os.path.join(cdir, "region.json"))
    origin = reg["transform"]["origin_ft"]
    res["winter_styles"] = winter_styles(cdir)
    res["trees"] = copy_foliage(world_dir(PARENT, root), cdir, p["rect"], origin)
    pl = _rj(os.path.join(cdir, "place.json"))
    pl.setdefault("links", {})["scene_name"] = p["scene_name"]
    pl["season"] = "winter"
    pl["street"] = {"key": p["key"], "part": p["part"], "parts": p["parts"], "street_ids": p["ids"], "generated_by": "bridgehollow_streets.py"}
    _wj(os.path.join(cdir, "place.json"), pl)
    res["street_trees"] = street_trees(p["child"], p["size_ft"], out_root)
    styles = {}
    for f in glob.glob(os.path.join(cdir, "buildings", "*.json")):
        s = _rj(f).get("style") or "(default)"
        styles[s] = styles.get(s, 0) + 1
    res.update(buildings=sum(styles.values()), styles=styles, origin_ft=origin)
    return res


STREET_TREE_MIX = [{"species": "oak", "weight": 1.0}, {"species": "birch", "weight": 1.2}, {"species": "rowan", "weight": 1.0}, {"species": "maple", "weight": 0.6},
                   {"species": "alder", "weight": 0.5}, {"species": "spruce", "weight": 0.9}, {"species": "fir", "weight": 0.5}, {"species": "scots_pine", "weight": 0.4}]
HEDGE_MIX = [{"species": "hedge", "weight": 2.0}, {"species": "bush", "weight": 1.0}, {"species": "juniper", "weight": 0.8}]


def street_tree_params(size_ft, seed):
    """Two foliage.py scatter zones over the whole street window: st_trees (bare broadleaf + conifers in yards, behind houses, on commons and
    square edges, kept off buildings and road beds) and st_hedges (hedges / bushes along plots). Caps scale with the window area (about 2-3 trees per
    100 ft of street frontage on a 400 ft window)."""
    w, h = float(size_ft[0]), float(size_ft[1])
    poly = [[0, 0], [w, 0], [w, h], [0, h]]
    area = w * h
    cap_t = int(max(12, min(70, round(area / 3800))))
    cap_h = int(max(6, min(30, round(area / 9000))))
    base = {"polygon": poly, "size_var": 0.35, "pattern": "uniform", "avoid_buildings": True, "avoid_roads": True, "avoid_water": True,
            "slope_max_deg": 36, "moisture_bias": 0.0, "replace_zone": True, "edge_ft": 0, "line_jitter": 0.15}
    trees = {**base, "zone": "st_trees", "name": "Street and yard trees (winter)", "mix": STREET_TREE_MIX, "density_per_ha": 34, "seed": seed,
             "clearance_building_ft": 6, "clearance_road_ft": 5, "max_instances": cap_t}
    hedges = {**base, "zone": "st_hedges", "name": "Hedges and bushes", "mix": HEDGE_MIX, "density_per_ha": 22, "seed": seed + 1, "pattern": "clustered",
              "cluster_radius_ft": 18, "cluster_size": 4, "clearance_building_ft": 3, "clearance_road_ft": 3, "max_instances": cap_h}
    return [trees, hedges]


def street_trees(child, size_ft, out_root=None):
    """Scatter the street trees into world/<child>/foliage.json (zones replaced, the town's copied trees kept) and re-export scatter/foliage.json.
    Params are written next to the place (street_trees.json) so a rerun is identical. -> {zone: count}."""
    if out_root:                                               # foliage.py works on the repo world/ only; tests pass out_root and skip this
        return {}
    import zlib
    cdir = world_dir(child)
    out = {}
    zones = street_tree_params(size_ft, zlib.crc32(child.encode()) % 100000)
    _wj(os.path.join(cdir, "street_trees.json"), {"zones": zones})
    for z in zones:
        pf = os.path.join(cdir, f"_scatter_{z['zone']}.json")
        _wj(pf, z)
        try:
            r = _py([os.path.join("illustrator", "generators", "foliage.py"), "scatter", "--place", child, "--params", pf])
            out[z["zone"]] = r.get("added", r.get("total"))
        finally:
            try:
                os.remove(pf)
            except OSError:
                pass
    return out


# ------------------------------------------------------------------ build (local, one heavy step at a time)
def free_gb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2 ** 30
    except Exception:
        return None


def _py(args, env=None, log=True):
    e = dict(os.environ)
    e.update(env or {})
    LOG("$ python " + " ".join(args))
    r = subprocess.run([sys.executable] + args, cwd=REPO, env=e, capture_output=True, text=True)
    last = None
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    if r.returncode != 0:
        tail = "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-25:])
        raise RuntimeError(f"{os.path.basename(args[0])} failed ({r.returncode}):\n{tail}")
    return last if last is not None else {}


def latest_opt(child, preset="layer"):
    ds = sorted(glob.glob(os.path.join(world_dir(child), "export", "optimized", f"{preset}_v*")), key=lambda d: int(re.sub(r"\D", "", d.rsplit("_v", 1)[1]) or 0))
    return ds[-1] if ds else None


def build_one(p, min_free_gb=3.0):
    G = os.path.join("illustrator", "generators")
    c = p["child"]
    g = free_gb()
    if g is not None and g < min_free_gb:
        raise RuntimeError(f"only {g:.1f} GB free RAM (< {min_free_gb} GB): close something or run on Vega")
    res = {"child": c}
    _py([os.path.join(G, "worldpack.py"), "export", "--place", c, "--roof-mode", "per_building", "--interior-style", "auto", "--style", "winter",
         "--phases", os.path.join("illustrator", "presets", "terrain_phases", "town_winter.json")])
    _py([os.path.join(G, "worldpack_split.py"), "split", "--place", c, "--roof-mode", "per_building"])
    _py([os.path.join(G, "worldpack_split.py"), "merge", "--place", c, "--preset", "layer", "--compress", "none", "--foliage"], env={"VB_FOLIAGE_SEASON": "winter"})
    opt = latest_opt(c)
    if not opt:
        raise RuntimeError("merge wrote no optimized/layer_v* folder")
    res["optimized"] = os.path.relpath(opt, REPO).replace("\\", "/")
    full = os.path.join(world_dir(c), "export", "placements.json")
    lamps = None
    spacing = LAMP_SPACING
    for _ in range(8):                                         # widen the spacing until the street has at most MAX_LAMPS lamps
        r = _py([os.path.join(G, "streetlamps.py"), "plan", "--place", c, "--style", LAMP_STYLE, "--spacing", str(spacing), "--classes", "main,side"])
        lamps = r.get("lamps", 0)
        if lamps <= MAX_LAMPS:
            break
        spacing = round(spacing * max(1.15, lamps / MAX_LAMPS), 1)
    r = _py([os.path.join(G, "streetlamps.py"), "apply", "--place", c, "--enabled", "on", "--style", LAMP_STYLE, "--spacing", str(spacing), "--classes", "main,side",
             "--placements", full, "--placements", os.path.join(opt, "placements.json")])
    res["lamps"], res["lamp_spacing_ft"] = r.get("lamps", lamps), spacing
    d = _rj(os.path.join(opt, "placements.json"))
    res["files"] = len(d.get("files", []))
    res["tris"] = int(sum(e.get("tris", 0) for e in d.get("files", [])))
    res["foliage_files"] = sum(1 for e in d.get("files", []) if e.get("layer") == "foliage")
    res["lights_in_pack"] = len(d.get("lights", [])) + sum(len(e.get("lights", [])) for e in d.get("files", []))
    return res


# ------------------------------------------------------------------ push + verify (Foundry, via the bridge)
def _fp(args):
    return _py([os.path.join("illustrator", "generators", "foundry_push.py")] + args)


def find_scene(br, p):
    import foundry_push as fpm
    pid = f"scene:{p['child']}:{fpm.slug(p['scene_name'])}"
    hit = br.call("find_by_flag", documentName="Scene", id=pid)
    return hit[0]["uuid"] if hit else None


def push_one(p, dry=False, prune=False):
    import foundry_push as fpm
    br = fpm.PsBridge()
    c = p["child"]
    opt = latest_opt(c)
    if not opt:
        raise RuntimeError(f"{c}: no merged pack, run build first")
    pp = os.path.join(opt, "placements.json")
    before = [s["name"] for s in br.call("list", collection="Scene")]
    clash = [n for n in before if n.lower() == p["scene_name"].lower()]
    uuid = find_scene(br, p)
    if clash and not uuid:
        raise RuntimeError(f"a scene named {p['scene_name']} exists and was not created for {c}: refusing")
    res = {"child": c, "scene_name": p["scene_name"], "scenes_before": len(before)}
    r = _fp(["push-models", "--place", c, "--placements", pp, "--px-per-ft", str(PX_PER_FT), "--scene-mode", "3d"]
            + (["--scene-uuid", uuid] if uuid else ["--scene-name", p["scene_name"]]) + (["--prune"] if prune and uuid else []) + (["--dry-run"] if dry else []))
    if dry:
        res.update(dry_run=True, tiles=r.get("tiles"), exists=bool(uuid))
        return res
    uuid = r.get("scene_uuid") or uuid or find_scene(br, p)
    res["scene_uuid"] = uuid
    res["created"] = not bool(clash)
    s3 = ["push-scene-3d", "--place", c, "--scene-uuid", uuid, "--placements", pp, "--px-per-ft", str(PX_PER_FT), "--skybox-preset", SKY, "--sun-preset", SUN,
          "--with-lights", "--lighting-mode", "hybrid", "--max-lights", str(MAX_LIGHTS), "--lights-placements", os.path.join(world_dir(c), "export", "placements.json")] + [f"--padding-arg={x}" for x in PADDING_ARGS]
    try:
        r3 = _fp(s3)
    except RuntimeError as e:
        if "the plan has 0 lights" in str(e):
            r3 = _fp([x for x in s3 if x not in ("--with-lights",)])
        else:
            raise
    res["push_scene_3d"] = {"ok": r3.get("ok"), "order": r3.get("order"), "problems": r3.get("problems")}
    for cmd in (["set-collision", "--scene-uuid", uuid, "--apply"], ["sync-doors", "--scene-uuid", uuid, "--apply"]):
        try:
            rr = _fp(cmd)
            res[cmd[0]] = {k: rr.get(k) for k in ("ok", "changed", "updated", "doors", "applied") if k in rr}
        except RuntimeError as e:
            res[cmd[0]] = {"ok": False, "error": str(e)[-300:]}
    after = [s["name"] for s in br.call("list", collection="Scene")]
    res["scenes_after"] = len(after)
    res["scenes_removed"] = sorted(set(before) - set(after))
    pl = _rj(os.path.join(world_dir(c), "place.json"))
    pl.setdefault("links", {})["foundry_scene"] = uuid
    _wj(os.path.join(world_dir(c), "place.json"), pl)
    return res


def bridges_in_window(p, root=None):
    """Ids of the parent's modelled bridges (bridges.json) whose deck midpoint lies in the scene window (region_extract.carry_bridges uses the same test)."""
    doc = _rj(os.path.join(world_dir(PARENT, root), "bridges.json"), {}) or {}
    x0, y0, x1, y1 = p["rect"]
    out = []
    for b in doc.get("bridges", []):
        if b["id"] in set(doc.get("removed") or []):
            continue
        (sx, sy, *_), (ex, ey, *_) = b["span"]["start"], b["span"]["end"]
        mx, my = (sx + ex) / 2, (sy + ey) / 2
        if x0 <= mx <= x1 and y0 <= my <= y1:
            out.append(b["id"])
    return out


def scene_counts(sc, place):
    """Read-only summary of a scene document: tiles per layer (pipeline tiles of `place`), foliage tiles, lights, flags."""
    F, L3 = "varrenmoor", "levels-3d-preview"
    layers, coll, sight, hidden = {}, 0, 0, 0
    for t in sc.get("tiles", []):
        f = (t.get("flags") or {})
        lay = (f.get(F) or {}).get("layer") or "other"
        layers[lay] = layers.get(lay, 0) + 1
        coll += bool((f.get(L3) or {}).get("collision"))
        sight += bool((f.get(L3) or {}).get("sight"))
        hidden += bool(t.get("hidden"))
    br_tiles, br_roofs = 0, 0
    for t in sc.get("tiles", []):
        f = (t.get("flags") or {}).get(F) or {}
        ids = f.get("ids") or []
        if f.get("layer") == "bridges" or any(str(i).startswith("brg_") for i in ids if f.get("layer") != "roofs"):
            br_tiles += 1
        if f.get("layer") == "roofs" and any(str(i).startswith("roof:brg_") or str(i).startswith("brg_") for i in ids):
            br_roofs += 1
    lights = sc.get("lights", []) or []
    lt = {}
    for l in lights:
        k = ((l.get("flags") or {}).get(F) or {}).get("type") or "other"
        lt[k] = lt.get(k, 0) + 1
    f3 = (sc.get("flags") or {}).get(L3) or {}
    return {"tiles": len(sc.get("tiles", [])), "layers": layers, "foliage_tiles": layers.get("foliage", 0), "collision_tiles": coll, "sight_tiles": sight,
            "hidden_tiles": hidden, "bridge_tiles": br_tiles, "bridge_roof_tiles": br_roofs, "lights": len(lights), "light_types": lt, "grid": {k: (sc.get("grid") or {}).get(k) for k in ("size", "distance")},
            "size_px": [sc.get("width"), sc.get("height")], "padding": sc.get("padding"),
            "flags": {k: f3.get(k) for k in ("auto3d", "exr", "fogColor", "fogNear", "fogFar", "ambientLightIntensity", "shadowBias") if k in f3}}


def verify_one(p):
    import foundry_push as fpm
    br = fpm.PsBridge()
    uuid = find_scene(br, p)
    if not uuid:
        return {"child": p["child"], "status": "not pushed"}
    sc = br.call("get", uuid=uuid)
    res = {"child": p["child"], "scene_uuid": uuid, **scene_counts(sc, p["child"])}
    opt = latest_opt(p["child"])
    if opt:
        try:
            a = _fp(["scene-audit", "--scene-uuid", uuid, "--placements", os.path.join(opt, "placements.json")])
            res["audit"] = {"clean": a.get("clean"), "counts": a.get("counts"), "missing": len(a.get("missing") or [])}
        except RuntimeError as e:
            res["audit"] = {"clean": False, "error": str(e)[-300:]}
        d = _rj(os.path.join(opt, "placements.json"))
        res["tris"] = int(sum(e.get("tris", 0) for e in d.get("files", [])))
    ok = res["foliage_tiles"] > 0 or not _rj(os.path.join(world_dir(p["child"]), "foliage.json"), {}).get("items")
    want = bridges_in_window(p)
    carried = [b["id"] for b in (_rj(os.path.join(world_dir(p["child"]), "bridges.json"), {}) or {}).get("bridges", [])]
    res["bridges"] = {"in_window": want, "carried": carried, "tiles": res["bridge_tiles"], "roof_tiles": res["bridge_roof_tiles"]}
    bridge_ok = not want or (res["bridge_tiles"] > 0 and len(carried) >= len(want))
    probs = [m for c, m in ((ok, "no foliage tile"), (res["lights"] <= 64, "over 64 lights"), (res.get("audit", {}).get("clean", True), "audit not clean"),
                            (bridge_ok, f"bridge missing ({len(want)} in window, {len(carried)} carried, {res['bridge_tiles']} tiles)")) if not c]
    res["status"] = "verified" if not probs else "check: " + "; ".join(probs)
    return res


# ------------------------------------------------------------------ status table
def update_status(p, **kw):
    st = _rj(STATUS_JSON, {}) or {}
    row = st.get(p["part_key"], {})
    row.update({"scene_name": p["scene_name"], "child": p["child"], "size_ft": p["size_ft"], "rect": p["rect"]}, **kw)
    row["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    st[p["part_key"]] = row
    _wj(STATUS_JSON, st)
    write_md(st)


def _bcell(r):
    b = r.get("bridges")
    if not isinstance(b, dict):
        return ""
    return f"{len(b.get('in_window', []))} in window, {b.get('tiles', 0)} tile(s), {b.get('roof_tiles', 0)} roof"


def write_md(st):
    plan = {p["part_key"]: p for p in scene_plan()}
    lines = ["# Bridgehollow street scenes (winter)", "",
             "Generated by `illustrator/generators/bridgehollow_streets.py` (status also in bridgehollow_street_scenes.json). "
             "Finish any row with: `python illustrator/generators/bridgehollow_streets.py run --street <key>`.", "",
             "| scene | key | uuid | size ft | buildings | tiles | foliage tiles | trees | bridges | lights | tris | status |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k, p in plan.items():
        r = st.get(k, {})
        sz = "x".join(str(v) for v in p["size_ft"])
        lines.append(f"| {p['scene_name']} | {k} | {r.get('scene_uuid', '')} | {sz} | {r.get('buildings', '')} | {r.get('tiles', '')} | {r.get('foliage_tiles', '')} | "
                     f"{r.get('trees', '')} | {_bcell(r)} | {r.get('lights', '')} | {r.get('tris', '')} | {r.get('status', 'todo')} |")
    lines.append("")
    os.makedirs(os.path.dirname(STATUS_MD), exist_ok=True)
    with open(STATUS_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["list", "extract", "build", "push", "verify", "run", "refresh"])
    ap.add_argument("--street", "--scenes", dest="street", default=None, help="comma list of street / part keys, or all")
    ap.add_argument("--all", action="store_true", help="every street scene (same as --street all)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    plan = scene_plan()
    out = {"ok": True, "cmd": a.cmd}
    if a.all:
        a.street = "all"
    if a.cmd == "refresh":                                     # re-cut from the parent, re-export, push to the SAME scene (found by its pipeline flag), prune stale tiles
        a.force = True
    if a.cmd == "list":
        out["scenes"] = select(plan, a.street)
        print(json.dumps(out))
        return 0
    if not a.street:
        raise SystemExit("give --street KEY or --street all")
    rows = []
    for p in select(plan, a.street):
        row = {"part_key": p["part_key"]}
        try:
            if a.cmd in ("extract", "run", "refresh"):
                r = extract_one(p, dry=a.dry_run, force=a.force)
                row["extract"] = r
                if not a.dry_run:
                    update_status(p, buildings=r.get("buildings"), trees=r.get("trees"), status="extracted")
            if a.cmd in ("build", "run", "refresh") and not a.dry_run:
                r = build_one(p)
                row["build"] = r
                update_status(p, tris=r["tris"], lamps=r["lamps"], status="built")
            if a.cmd in ("push", "run", "refresh"):
                r = push_one(p, dry=a.dry_run, prune=a.cmd == "refresh")
                row["push"] = r
                if not a.dry_run:
                    update_status(p, scene_uuid=r["scene_uuid"], status="pushed")
            if a.cmd in ("verify", "run", "refresh") and not a.dry_run:
                r = verify_one(p)
                row["verify"] = r
                update_status(p, **{k: r.get(k) for k in ("scene_uuid", "tiles", "foliage_tiles", "lights", "tris", "status", "audit", "light_types", "bridges") if k in r})
        except Exception as e:                                    # one street failing must not stop the others
            row["error"] = str(e)[-1500:]
            out["ok"] = False
            if not a.dry_run:
                update_status(p, status="failed: " + str(e).splitlines()[0][:120])
        rows.append(row)
        LOG(json.dumps(row)[:3000])
    out["rows"] = rows
    print(json.dumps(out))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
