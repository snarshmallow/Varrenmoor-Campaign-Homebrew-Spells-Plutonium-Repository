#!/usr/bin/env python3
"""Per-object editing of buildings and roads (the Illustrator panel's Buildings tab > "Edit selected building(s)" and Roads tab call this as a job).

  object_edit.py list-buildings --place P                 JSON: id, kind, floors, style, interior_style, edit, has_layout
  object_edit.py list-roads     --place P                 JSON: id, name, kind, class, width_ft, edit
  object_edit.py choices        --place P                 JSON: allowed values (road classes, textures, interior styles, roof types)
  object_edit.py set-building   --place P --ids a,b [--set key=value ...] [--clear key ...] [--dry]
  object_edit.py set-road       --place P --ids a,b [--set key=value ...] [--clear key ...] [--dry]
  object_edit.py reset-building --place P --ids a,b       remove every per-object override (edit block, interior_style; style stays: use building_styles.py)
  object_edit.py reset-road     --place P --ids a,b       remove the edit block (width_ft stays as it is)

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
             "grade.cross_deg": (0.0, 45.0), "grade.cutfill": "bool"}
ROAD_TOP = {"width_ft": (2.0, 120.0)}
ROAD_CLASSES = ["road", "street", "lane", "alley"]          # "bridge" roads are made by the Bridges tab


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


def choices(place=None):
    return {"road_classes": ROAD_CLASSES, "textures": textures(), "interior_styles": interior_styles(), "roof_types": ROOF_TYPES, "building_styles": building_style_ids()}


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
        _jsave(p, doc, 1)
    return {"place": place, "changed": changed, "count": len(changed), "dry": dry}


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
    else:
        out = reset_road(a.place, ids, a.dry)
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
