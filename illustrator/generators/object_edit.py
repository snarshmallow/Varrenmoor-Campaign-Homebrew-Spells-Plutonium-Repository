#!/usr/bin/env python3
"""Per-object editing of buildings and roads (the Illustrator panel's Buildings tab > "Edit selected building(s)" and Roads tab call this as a job).

  object_edit.py list-buildings --place P                 JSON: id, kind, floors, style, interior_style, edit, has_layout
  object_edit.py list-roads     --place P                 JSON: id, name, kind, class, width_ft, edit
  object_edit.py choices        --place P                 JSON: allowed values (road classes, textures, interior styles, roof types)
  object_edit.py set-building   --place P --ids a,b [--set key=value ...] [--clear key ...] [--dry]
  object_edit.py set-road       --place P --ids a,b [--set key=value ...] [--clear key ...] [--dry]
  object_edit.py reset-building --place P --ids a,b       remove every per-object override (edit block, interior_style; style stays: use building_styles.py)
  object_edit.py reset-road     --place P --ids a,b       remove the edit block (width_ft stays as it is)
Road geometry (logic in road_edit.py; every write first copies streets.json to world/<place>/streets_backups/; bridges are never touched):
  object_edit.py delete-road    --place P --ids a,b [--dry]
  object_edit.py add-road       --place P --name N --kind lane --width 14 (--points "x,y;x,y" | --points-file F) [--id str_x] [--simplify FT] [--smooth N] [--dry]
  object_edit.py set-road-points --place P --ids a (--points ... | --points-file F | only --simplify / --smooth on the existing line) [--dry]
  object_edit.py split-road     --place P --ids a --at VERTEX_INDEX      join-roads --place P --ids a,b [--join-tol 25]
  object_edit.py apply-paths    --place P --file paths.json --mode reshape|add|sync [--kind --width --name --simplify --smooth]   (Illustrator paths in feet)
  object_edit.py draw-roads     --place P --view-file view.json --out roads.svg     centrelines for the Illustrator layer "Road Centerlines"
  object_edit.py restore-streets --place P                undo the last road change (pops the newest backup)
Building geometry and properties (logic in building_edit.py; every write first copies the touched files to world/<place>/buildings_backups/<stamp>/):
  object_edit.py building-info      --place P            JSON: every building with name, kind, floors, district, size, centre, notes, tags; kinds; districts
  object_edit.py delete-building    --place P --ids a,b [--dry]          (details.json doors/roofs/lots, label override, region id_map go too)
  object_edit.py add-building       --place P [--name N] [--kind house] [--floors 1] (--center x,y --width W --depth D [--rotation DEG] | --points ...)
                                    [--district ID] [--style S] [--notes T] [--id bld_x] [--dry]
  object_edit.py move-building      --place P --ids a,b (--dx FT --dy FT | --to x,y) [--with-lot]     rotate-building --ids a --deg DEG [--with-lot]
  object_edit.py resize-building    --place P --ids a (--width FT --depth FT | --scale K)           set-footprint --ids a (--points ... | --points-file F)
  object_edit.py duplicate-building --place P --ids a [--dx 20 --dy 20]     rename-building --ids a [--new-id bld_new] [--name N]
  object_edit.py set-building-props --place P --ids a,b [--name --kind --floors --district --notes --description --owner --tags a,b --status]
  object_edit.py set-door           --place P --ids a --edge N [--pos 0.5] [--door-width FT]
  object_edit.py apply-building-paths --place P --file paths.json --mode reshape|add|sync [--name --kind --floors]   (closed Illustrator paths in feet)
  object_edit.py draw-buildings     --place P --view-file view.json --out f.svg    footprints for the Illustrator layer "Building Footprints"
  object_edit.py restore-buildings  --place P            undo the last building change (one step per call)
  object_edit.py svg-absent         --svg F --ids a,b    check a rendered map no longer contains these ids

Where it writes (nothing else is touched, only the listed files):
  buildings/<id>.json   floors, style, interior_style (top level, as before) and an `edit` block {roof_type, roof_pitch, roof_overhang_ft, roof_material,
                        wall_material, no_windows, keep_individual}
  streets.json          geometry.width_ft (the existing width key, so the 2D map follows) and an `edit` block {class, surface, kerb, grade{smooth,
                        max_grade_deg, cross_deg, cutfill}} on the street entry
The 3D exporter (worldpack.py: building_edit / road_edit, road_grade.road_params, worldpack_split merge) honours them the next time the pack is exported.
No key = the old behaviour. `--set key=value`: bool values true|false, numbers, text; `--clear key` (or the value none) removes a key.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

ROOF_TYPES = ["gable", "hip"]
BUILDING_EDIT = {"roof_type": "choice", "roof_pitch": (0.05, 2.0), "roof_overhang_ft": (0.0, 6.0), "roof_material": "texture", "wall_material": "texture",
                 "no_windows": "bool", "keep_individual": "bool"}
BUILDING_TOP = {"floors": (1, 12), "style": "style", "interior_style": "interior"}
ROAD_EDIT = {"class": "class", "surface": "texture", "kerb": "bool", "grade.smooth": (0.0, 1.0), "grade.max_grade_deg": (1.0, 60.0),
             "grade.cross_deg": (0.0, 45.0), "grade.cutfill": "bool", "lamps.on": "bool", "lamps.style": "lampstyle", "lamps.spacing_ft": (8.0, 400.0)}
ROAD_TOP = {"width_ft": (2.0, 120.0)}
ROAD_CLASSES = ["road", "street", "lane", "alley"]          # "bridge" roads are made by the Bridges tab


def _re():
    import road_edit
    return road_edit


def _root():
    return os.environ.get("VB_WORLD_ROOT") or os.path.join(HERE, "..", "..", "world")


def _wdir(place):
    return os.path.join(_root(), place)


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jsave(p, d, indent):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def textures():
    d = os.path.join(HERE, "..", "presets", "textures")
    return sorted(os.path.splitext(f)[0] for f in os.listdir(d) if f.lower().endswith(".png")) if os.path.isdir(d) else []


def interior_styles():
    try:
        import interior_styles as ist
        return ist.choices()
    except Exception:
        return ["auto", "plain", "rustic_cottage", "farmhouse", "burgher_townhouse", "poor_hovel"]


def building_style_ids():
    try:
        import building_styles as bs
        return ["auto"] + sorted(bs.load_presets().keys())
    except Exception:
        return ["auto"]


def _coerce(key, raw, rule, tx):
    """-> value or None (None = clear). Raises SystemExit on a bad value."""
    if raw is None or str(raw).strip().lower() in ("", "none", "null", "default"):
        return None
    v = str(raw).strip()
    if rule == "bool":
        if v.lower() in ("true", "1", "yes", "on"):
            return True
        if v.lower() in ("false", "0", "no", "off"):
            return False
        raise SystemExit(f"{key}: expected true or false, got {raw!r}")
    if isinstance(rule, tuple):
        try:
            f = float(v)
        except ValueError:
            raise SystemExit(f"{key}: expected a number, got {raw!r}")
        lo, hi = rule
        if f < lo or f > hi:
            raise SystemExit(f"{key}: {f:g} outside {lo:g}..{hi:g}")
        return int(round(f)) if key == "floors" else f
    if rule == "choice":
        if v not in ROOF_TYPES:
            raise SystemExit(f"{key}: {v!r} not one of {', '.join(ROOF_TYPES)}")
        return v
    if rule == "class":
        if v not in ROAD_CLASSES:
            raise SystemExit(f"{key}: {v!r} not one of {', '.join(ROAD_CLASSES)}")
        return v
    if rule == "lampstyle":
        import streetlamps
        names = list(streetlamps.load_styles()["styles"])
        if v not in names:
            raise SystemExit(f"{key}: {v!r} not one of {', '.join(names)}")
        return v
    if rule == "texture":
        if v not in tx:
            raise SystemExit(f"{key}: unknown texture {v!r} (illustrator/presets/textures/*.png)")
        return v
    if rule == "interior":
        if v not in interior_styles():
            raise SystemExit(f"{key}: unknown interior style {v!r}; known: {', '.join(interior_styles())}")
        return v
    if rule == "style":
        if v not in building_style_ids():
            raise SystemExit(f"{key}: unknown building style {v!r}")
        return v
    raise SystemExit(f"{key}: unsupported")


def _pairs(sets, clears, allowed):
    out = {}
    for s in sets or []:
        if "=" not in s:
            raise SystemExit(f"--set expects key=value, got {s!r}")
        k, v = s.split("=", 1)
        k = k.strip()
        if k not in allowed:
            raise SystemExit(f"unknown key {k!r}; allowed: {', '.join(sorted(allowed))}")
        out[k] = v
    for k in clears or []:
        if k not in allowed:
            raise SystemExit(f"unknown key {k!r}; allowed: {', '.join(sorted(allowed))}")
        out[k] = None
    return out


def _prune(d):
    for k in [k for k, v in d.items() if isinstance(v, dict)]:
        _prune(d[k])
        if not d[k]:
            del d[k]


def _building_files(place):
    d = os.path.join(_wdir(place), "buildings")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.endswith(".json"):
            p = os.path.join(d, fn)
            yield p, _jload(p)


def list_buildings(place):
    out = []
    for _p, b in _building_files(place):
        out.append({"id": b["id"], "kind": b.get("kind", ""), "floors": int(b.get("floors", 1) or 1), "style": b.get("style", ""),
                    "interior_style": b.get("interior_style", ""), "edit": b.get("edit") or {}, "has_layout": bool(b.get("rooms")), "name": b.get("name", "")})
    return out


def list_roads(place):
    p = os.path.join(_wdir(place), "streets.json")
    out = []
    if os.path.exists(p):
        try:
            import fills_raster as fr
            st = _jload(os.path.join(HERE, "..", "presets", "town_styles", "full_map.json"))["types"]["streets"]
        except Exception:
            fr, st = None, {}
        for s in _jload(p).get("streets", []):
            try:
                cls = fr.classify_street(s, st) if fr else s.get("kind", "street")
            except Exception:
                cls = s.get("kind", "street")
            out.append({"id": s["id"], "name": s.get("name", ""), "kind": s.get("kind", ""), "class": cls, "width_ft": (s.get("geometry") or {}).get("width_ft"),
                        "edit": s.get("edit") or {}})
    return out


def lamp_style_ids():
    try:
        import streetlamps
        return list(streetlamps.load_styles()["styles"])
    except Exception:
        return []


def choices(place=None):
    return {"road_classes": ROAD_CLASSES, "textures": textures(), "interior_styles": interior_styles(), "roof_types": ROOF_TYPES, "building_styles": building_style_ids(), "lamp_styles": lamp_style_ids()}


def set_building(place, ids, sets=None, clears=None, dry=False):
    want = set(ids)
    upd = _pairs(sets, clears, set(BUILDING_EDIT) | set(BUILDING_TOP))
    tx = textures()
    vals = {}
    for k, raw in upd.items():
        rule = BUILDING_EDIT.get(k) or BUILDING_TOP[k]
        vals[k] = None if raw is None else _coerce(k, raw, rule, tx)
    changed, found = [], set()
    for p, b in _building_files(place):
        if b["id"] not in want:
            continue
        found.add(b["id"])
        if "floors" in vals and vals["floors"] is not None and b.get("rooms"):
            have = 1 + max([int(r.get("floor", 0)) for r in b["rooms"]] or [0])
            if have != vals["floors"]:
                raise SystemExit(f"{b['id']}: has a generated interior layout for {have} storey(s); changing floors to {vals['floors']} would break it "
                                 f"(regenerate the interior, or edit another building)")
        ed = dict(b.get("edit") or {})
        for k, v in vals.items():
            if k in BUILDING_TOP:
                if v is None:
                    if k != "floors":
                        b.pop(k, None)
                else:
                    b[k] = v
            elif v is None or v is False and k in ("no_windows", "keep_individual"):
                ed.pop(k, None)
            else:
                ed[k] = v
        if ed:
            b["edit"] = ed
        else:
            b.pop("edit", None)
        changed.append(b["id"])
        if not dry:
            _jsave(p, b, 1)
    missing = sorted(want - found)
    if missing:
        raise SystemExit("unknown building id(s): " + ", ".join(missing))
    return {"place": place, "changed": changed, "count": len(changed), "dry": dry, "set": {k: v for k, v in vals.items()}}


def set_road(place, ids, sets=None, clears=None, dry=False):
    want = set(ids)
    upd = _pairs(sets, clears, set(ROAD_EDIT) | set(ROAD_TOP))
    tx = textures()
    vals = {}
    for k, raw in upd.items():
        rule = ROAD_EDIT.get(k) or ROAD_TOP[k]
        vals[k] = None if raw is None else _coerce(k, raw, rule, tx)
    p = os.path.join(_wdir(place), "streets.json")
    doc = _jload(p)
    changed = []
    for s in doc.get("streets", []):
        if s["id"] not in want:
            continue
        ed = dict(s.get("edit") or {})
        for k, v in vals.items():
            if k in ROAD_TOP:
                if v is not None:
                    s.setdefault("geometry", {})["width_ft"] = v
                continue
            if "." in k:
                a, b_ = k.split(".", 1)
                g = dict(ed.get(a) or {})
                if v is None:
                    g.pop(b_, None)
                else:
                    g[b_] = v
                ed[a] = g
            elif v is None:
                ed.pop(k, None)
            else:
                ed[k] = v
        _prune(ed)
        if ed:
            s["edit"] = ed
        else:
            s.pop("edit", None)
        changed.append(s["id"])
    missing = sorted(want - set(changed))
    if missing:
        raise SystemExit("unknown road id(s): " + ", ".join(missing))
    if not dry:
        _re().backup(_wdir(place))
        _jsave(p, doc, 1)
    return {"place": place, "changed": changed, "count": len(changed), "dry": dry, "set": vals}


def reset_building(place, ids, dry=False):
    want, changed = set(ids), []
    for p, b in _building_files(place):
        if b["id"] in want:
            b.pop("edit", None)
            b.pop("interior_style", None)
            changed.append(b["id"])
            if not dry:
                _jsave(p, b, 1)
    return {"place": place, "changed": changed, "count": len(changed), "dry": dry}


def reset_road(place, ids, dry=False):
    p = os.path.join(_wdir(place), "streets.json")
    doc = _jload(p)
    want, changed = set(ids), []
    for s in doc.get("streets", []):
        if s["id"] in want:
            s.pop("edit", None)
            changed.append(s["id"])
    if changed and not dry:
        _re().backup(_wdir(place))
        _jsave(p, doc, 1)
    return {"place": place, "changed": changed, "count": len(changed), "dry": dry}


def road_cmd(a, ids):
    re_ = _re()
    wd = _wdir(a.place)
    if not os.path.isdir(wd):
        raise SystemExit(f"unknown place {a.place!r}")
    if a.cmd == "restore-streets":
        out = re_.restore(wd)
    elif a.cmd == "delete-road":
        out = re_.op_delete(wd, ids, a.dry)
    elif a.cmd == "add-road":
        pts = _pts_arg(a)
        if pts is None:
            raise SystemExit("add-road needs --points or --points-file")
        out = re_.op_add(wd, a.name, a.kind, a.width, pts, a.id, a.simplify, a.smooth, a.dry)
    elif a.cmd == "set-road-points":
        if len(ids) != 1:
            raise SystemExit("set-road-points takes exactly one road id")
        out = re_.op_set_points(wd, ids[0], _pts_arg(a), a.simplify, a.smooth, a.dry)
    elif a.cmd == "split-road":
        if len(ids) != 1:
            raise SystemExit("split-road takes exactly one road id")
        out = re_.op_split(wd, ids[0], a.at, a.dry)
    elif a.cmd == "join-roads":
        if len(ids) != 2:
            raise SystemExit("join-roads takes exactly two road ids")
        out = re_.op_join(wd, ids[0], ids[1], a.join_tol, a.dry)
    elif a.cmd == "apply-paths":
        d = _jload(a.file) if os.path.exists(a.file) else re_.fail(f"paths file not found: {a.file}")
        out = re_.op_apply_paths(wd, d.get("paths") if isinstance(d, dict) else d, a.mode, a.kind, a.width, a.name, a.simplify, a.smooth, a.dry)
    else:
        out = re_.draw_svg(wd, _jload(a.view_file), a.out)
    out["place"] = a.place
    return out


BUILDING_CMDS = ("delete-building", "add-building", "move-building", "rotate-building", "resize-building", "set-footprint", "duplicate-building",
                 "rename-building", "set-building-props", "set-door", "apply-building-paths", "draw-buildings", "restore-buildings", "building-info", "svg-absent")
PROP_FLAGS = ("name", "kind", "floors", "district", "notes", "description", "owner", "tags", "status")


def _building_parsers(sub):
    """Building geometry / property commands (logic in building_edit.py; every write backs the touched files up to world/<place>/buildings_backups/<stamp>/)."""
    for n in ("delete-building", "add-building", "move-building", "rotate-building", "resize-building", "set-footprint", "duplicate-building",
              "rename-building", "set-building-props", "set-door", "apply-building-paths", "draw-buildings", "restore-buildings", "building-info", "svg-absent"):
        s = sub.add_parser(n)
        if n != "svg-absent":
            s.add_argument("--place", required=True)
        if n not in ("building-info", "draw-buildings", "svg-absent"):
            s.add_argument("--dry", action="store_true")
        if n not in ("add-building", "apply-building-paths", "draw-buildings", "restore-buildings", "building-info"):
            s.add_argument("--ids", required=True)
        if n in ("add-building", "set-footprint"):
            s.add_argument("--points", help="x,y;x,y;... footprint in feet")
            s.add_argument("--points-file", help="json list of [x, y] (or {points: [...]})")
        if n == "add-building":
            s.add_argument("--center", help="x,y centre of a rectangle footprint (feet)")
            s.add_argument("--width", type=float, help="rectangle width (ft, along the rotation)")
            s.add_argument("--depth", type=float, help="rectangle depth (ft)")
            s.add_argument("--rotation", type=float, default=0.0, help="rectangle rotation in degrees (clockwise on the map)")
            s.add_argument("--style", help="building style preset id (building_styles)")
            s.add_argument("--id", help="building id (default bld_<kind>_<next number>)")
        if n in ("add-building", "set-building-props", "apply-building-paths"):
            s.add_argument("--name")
            s.add_argument("--kind")
            s.add_argument("--floors")
        if n in ("add-building", "set-building-props"):
            s.add_argument("--district", help="district id; set-building-props: '' clears, auto = by containment")
            s.add_argument("--notes")
        if n == "set-building-props":
            s.add_argument("--description")
            s.add_argument("--owner")
            s.add_argument("--tags", help="comma list ('' clears)")
            s.add_argument("--status")
        if n in ("move-building", "duplicate-building"):
            s.add_argument("--dx", type=float, help="feet east (+x)")
            s.add_argument("--dy", type=float, help="feet south (+y, map y is down)")
        if n == "move-building":
            s.add_argument("--to", help="x,y new centre (one building)")
        if n in ("move-building", "rotate-building"):
            s.add_argument("--with-lot", action="store_true", help="also move the lot and fences of details.json")
        if n == "rotate-building":
            s.add_argument("--deg", type=float, required=True, help="degrees about the footprint centre (clockwise on the map)")
        if n == "resize-building":
            s.add_argument("--width", type=float, help="new long side (ft)")
            s.add_argument("--depth", type=float, help="new short side (ft)")
            s.add_argument("--scale", type=float, help="scale factor 0.1..10 (both sides)")
        if n == "rename-building":
            s.add_argument("--new-id", help="new id bld_... (references updated)")
            s.add_argument("--name")
        if n == "set-door":
            s.add_argument("--edge", type=int, required=True, help="footprint side index (0 = first point to second)")
            s.add_argument("--pos", type=float, default=0.5, help="0..1 along the side")
            s.add_argument("--door-width", type=float, help="ft (default 3.5, 6 for civic / inn / barn / stable / craft)")
        if n == "apply-building-paths":
            s.add_argument("--file", required=True, help="json {paths:[{name, points, closed}]} in feet")
            s.add_argument("--mode", default="sync", choices=["reshape", "add", "sync"])
        if n == "draw-buildings":
            s.add_argument("--view-file", required=True, help="panelio.py view json")
            s.add_argument("--out", required=True)
        if n == "svg-absent":
            s.add_argument("--svg", required=True, help="rendered SVG to check")


def building_cmd(a, ids):
    import building_edit as be
    if a.cmd == "svg-absent":
        return be.svg_absent(a.svg, ids)
    wd = _wdir(a.place)
    if not os.path.isdir(wd):
        raise SystemExit(f"unknown place {a.place!r}")
    one = lambda what: ids[0] if len(ids) == 1 else be.fail(f"{what} takes exactly one building id")
    dry = getattr(a, "dry", False)
    c = a.cmd
    if c == "building-info":
        out = {"buildings": be.info(wd), "kinds": sorted(set(be.KINDS) | {b.get("kind") for _p, b in be.load_all(wd).values() if b.get("kind")}),
               "districts": be.district_ids(wd), "backups": len(be.list_backups(wd))}
    elif c == "restore-buildings":
        out = be.restore(wd, dry)
    elif c == "delete-building":
        out = be.op_delete(wd, ids, dry)
    elif c == "add-building":
        pts = _bpts(a, be)
        ctr = be.parse_xy(a.center, "--center") if a.center else None
        fp = be.footprint_from_args(ctr, a.width, a.depth, a.rotation, pts)
        out = be.op_add(wd, a.name, a.kind or "house", fp, a.floors if a.floors is not None else 1, a.id, a.district, a.style, a.notes or "", dry)
    elif c == "move-building":
        out = be.op_move(wd, ids, a.dx, a.dy, be.parse_xy(a.to, "--to") if a.to else None, a.with_lot, dry)
    elif c == "rotate-building":
        out = be.op_rotate(wd, ids, a.deg, a.with_lot, dry)
    elif c == "resize-building":
        out = be.op_resize(wd, ids, a.width, a.depth, a.scale, dry)
    elif c == "set-footprint":
        pts = _bpts(a, be)
        if pts is None:
            be.fail("set-footprint needs --points or --points-file")
        out = be.op_set_footprint(wd, one("set-footprint"), pts, dry)
    elif c == "duplicate-building":
        out = be.op_duplicate(wd, ids, 20.0 if a.dx is None else a.dx, 20.0 if a.dy is None else a.dy, dry)
    elif c == "rename-building":
        out = be.op_rename(wd, one("rename-building"), a.new_id, a.name, dry)
    elif c == "set-building-props":
        props = {k: getattr(a, k) for k in PROP_FLAGS if getattr(a, k) is not None}
        out = be.op_set_props(wd, ids, props, dry)
    elif c == "set-door":
        out = be.op_set_door(wd, one("set-door"), a.edge, a.pos, a.door_width, dry)
    elif c == "apply-building-paths":
        d = _jload(a.file) if os.path.exists(a.file) else be.fail(f"paths file not found: {a.file}")
        out = be.op_apply_paths(wd, d.get("paths") if isinstance(d, dict) else d, a.mode, a.name, a.kind or "house", a.floors or 1, dry)
    else:
        out = be.draw_svg(wd, _jload(a.view_file), a.out)
    out["place"] = a.place
    return out


def _bpts(a, be):
    if a.points and a.points_file:
        be.fail("give --points or --points-file, not both")
    if a.points:
        return be.parse_points(a.points)
    if a.points_file:
        return be.read_points_file(a.points_file)
    return None


def _pts_arg(a):
    re_ = _re()
    if a.points and a.points_file:
        raise SystemExit("give --points or --points-file, not both")
    if a.points:
        return re_.parse_points(a.points)
    if a.points_file:
        return re_.read_points_file(a.points_file)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--world-root", help="folder holding the place folders (default: repo world/)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("list-buildings", "list-roads", "choices"):
        sub.add_parser(n).add_argument("--place", required=True)
    for n in ("set-building", "set-road", "reset-building", "reset-road"):
        s = sub.add_parser(n)
        s.add_argument("--place", required=True)
        s.add_argument("--ids", required=True)
        s.add_argument("--dry", action="store_true")
        if n.startswith("set"):
            s.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
            s.add_argument("--clear", action="append", default=[], metavar="KEY")
    sub.add_parser("restore-streets").add_argument("--place", required=True)
    _building_parsers(sub)
    for n in ("delete-road", "add-road", "set-road-points", "split-road", "join-roads", "apply-paths", "draw-roads"):
        s = sub.add_parser(n)
        s.add_argument("--place", required=True)
        s.add_argument("--dry", action="store_true")
        if n in ("delete-road", "set-road-points", "split-road", "join-roads"):
            s.add_argument("--ids", required=True)
        if n in ("add-road", "set-road-points", "apply-paths"):
            s.add_argument("--simplify", type=float, default=0.0, help="Douglas-Peucker tolerance in feet")
            s.add_argument("--smooth", type=int, default=0, help="smoothing iterations")
        if n in ("add-road", "set-road-points"):
            s.add_argument("--points", help="x,y;x,y;... in feet")
            s.add_argument("--points-file", help="json list of [x, y] (or {points: [...]})")
        if n in ("add-road", "apply-paths"):
            s.add_argument("--kind", default="lane")
            s.add_argument("--width", type=float, default=14.0)
            s.add_argument("--name")
        if n == "add-road":
            s.add_argument("--id")
        if n == "split-road":
            s.add_argument("--at", type=int, required=True, help="vertex index to split at (1..n-2)")
        if n == "join-roads":
            s.add_argument("--join-tol", type=float, default=25.0)
        if n == "apply-paths":
            s.add_argument("--file", required=True, help="json {paths:[{name, points, closed}]} in feet")
            s.add_argument("--mode", default="sync", choices=["reshape", "add", "sync"])
        if n == "draw-roads":
            s.add_argument("--view-file", required=True, help="panelio.py view json")
            s.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if a.world_root:
        os.environ["VB_WORLD_ROOT"] = a.world_root
    ids = [i for i in (getattr(a, "ids", "") or "").split(",") if i.strip()]
    if a.cmd == "list-buildings":
        out = {"buildings": list_buildings(a.place)}
    elif a.cmd == "list-roads":
        out = {"roads": list_roads(a.place)}
    elif a.cmd == "choices":
        out = choices(a.place)
    elif a.cmd == "set-building":
        out = set_building(a.place, ids, a.set, a.clear, a.dry)
    elif a.cmd == "set-road":
        out = set_road(a.place, ids, a.set, a.clear, a.dry)
    elif a.cmd == "reset-building":
        out = reset_building(a.place, ids, a.dry)
    elif a.cmd == "reset-road":
        out = reset_road(a.place, ids, a.dry)
    elif a.cmd in BUILDING_CMDS:
        out = building_cmd(a, ids)
    else:
        out = road_cmd(a, ids)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
