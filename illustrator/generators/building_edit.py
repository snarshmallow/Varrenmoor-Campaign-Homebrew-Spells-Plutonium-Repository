#!/usr/bin/env python3
"""Building geometry and property editing for world/<place>/buildings/<id>.json (delete, add, move, rotate, resize, reshape, duplicate, rename,
properties, front door, Illustrator footprint sync, undo). Pure functions plus a backup stack; the command line lives in object_edit.py
(delete-building, add-building, move-building, rotate-building, resize-building, set-footprint, duplicate-building, rename-building, set-building-props,
set-door, apply-building-paths, draw-buildings, restore-buildings, svg-absent).

Rules
  * Every writing call first copies each file it will touch to world/<place>/buildings_backups/<stamp>/ (plus a manifest naming the files that did not
    exist yet); restore-buildings puts the newest backup back (one step per call) and removes it. The newest 30 backups are kept.
  * Every check runs before a single byte is written (BuildingError); --dry runs every check and reports what would change, writing nothing.
  * Files written atomically (tmp + os.replace).
  * Derived data:
      move / rotate (rigid): the footprint, the stored interior (rooms, doors, layout walls / windows / fixtures / lights) and the details.json doors,
        roofs and chimneys of the building move with it (lot and fences only with --with-lot). Cached heights (elevation_ft, site_slope,
        site_relief_ft) are dropped: the exporter samples the terrain again.
      resize / reshape (not rigid): the stored interior (rooms, doors, layout) and the details.json doors / roofs / chimneys of the building are dropped:
        the exporter derives a street-facing front door (worldpack.derive_street_doors) and generates the interior on the fly (interiors.py). Lot and fences stay.
      delete: the building json, its details.json entries (doors, roofs, chimneys, lots, fences) and its label override go; region.json id_map forgets it.
      rename (id): file name, the id, every id inside the json that starts with the old id (rooms, doors, layout), details.json entries, label_overrides.json
        key, region.json id_map / snapshot / interiors entries.
  * Validation: a footprint is a simple polygon (no self-crossing), 3..200 points, finite numbers, each side of its minimum rotated rectangle 6..400 ft,
    centre inside the place (bounds +- 200 ft). Footprints are stored counter-clockwise as seen on the map (y down; negative shoelace sum, like 94 % of
    the existing buildings). Overlaps with other buildings (> 1 sq ft) and with road surfaces (> 4 sq ft) are WARNINGS (listed in the result), not refusals.
  * Illustrator: the helper layer "Building Footprints" holds one closed path per building named by its id (draw_svg); apply-building-paths reads closed
    paths back (named by an id = reshape that building, other names = new buildings).
"""
import copy
import datetime
import json
import math
import os
import re
import shutil

FOOTPRINT_LAYER = "Building Footprints"
KINDS = ["house", "farmhouse", "shop", "inn", "tavern", "barn", "shed", "stable", "craft", "workshop", "smithy", "mill", "warehouse",
         "civic", "hall", "temple", "church", "tower", "gatehouse"]
STATUS = ["proposed", "canon", "built", "ruined"]
MIN_SIDE, MAX_SIDE = 6.0, 400.0
MAX_POINTS = 200
OUT_MARGIN_FT = 200.0
KEEP_BACKUPS = 30
STALE = ("elevation_ft", "site_slope", "site_relief_ft")
INTERIOR = ("rooms", "doors", "layout")
DETAIL_RIGID = ("doors", "roofs", "chimneys")
DETAIL_LOT = ("lots", "fences")
ID_RE = re.compile(r"^bld_[a-z0-9]+(?:_[a-z0-9]+)*$")
ROAD_OVERLAP_WARN = 4.0
BLD_OVERLAP_WARN = 1.0
TEXT_PROPS = ("name", "notes", "description", "owner")


class BuildingError(SystemExit):
    pass


def fail(msg):
    raise BuildingError(msg)


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jsave(p, d, indent=1):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


# ------------------------------------------------------------------ files
def bdir(wdir):
    return os.path.join(wdir, "buildings")


def backup_root(wdir):
    return os.path.join(wdir, "buildings_backups")


def load_all(wdir):
    """-> {id: (path, dict)} for every building json of the place."""
    d = bdir(wdir)
    out = {}
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.endswith(".json"):
            p = os.path.join(d, fn)
            b = _jload(p)
            if isinstance(b, dict) and b.get("id"):
                out[b["id"]] = (p, b)
    return out


def need(allb, ids, what="edit"):
    ids = list(dict.fromkeys(i.strip() for i in ids if i and i.strip()))
    if not ids:
        fail(f"{what}: no building ids given")
    miss = [i for i in ids if i not in allb]
    if miss:
        fail("unknown building id(s): " + ", ".join(miss))
    return ids


def _opt_json(wdir, name):
    p = os.path.join(wdir, name)
    return (p, _jload(p)) if os.path.exists(p) else (p, None)


class Tx:
    """Collects the writes of one operation; commit() backs every touched file up first (one backup folder), then writes them atomically."""

    def __init__(self, wdir, op):
        self.wdir, self.op = wdir, op
        self.writes, self.deletes = {}, set()

    def write(self, path, data):
        self.writes[os.path.abspath(path)] = data
        self.deletes.discard(os.path.abspath(path))

    def delete(self, path):
        self.deletes.add(os.path.abspath(path))
        self.writes.pop(os.path.abspath(path), None)

    def files(self):
        return sorted(set(self.writes) | self.deletes)

    def commit(self, info=None):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        root = backup_root(self.wdir)
        dst = os.path.join(root, stamp)
        os.makedirs(dst, exist_ok=True)
        man = {"op": self.op, "at": stamp, "info": info or {}, "files": []}
        for i, p in enumerate(self.files()):
            rel = os.path.relpath(p, self.wdir).replace("\\", "/")
            if rel.startswith(".."):
                fail(f"refusing to touch a file outside the place: {p}")
            ent = {"rel": rel, "existed": os.path.exists(p)}
            if ent["existed"]:
                ent["copy"] = f"f{i:04d}.json"
                shutil.copyfile(p, os.path.join(dst, ent["copy"]))
            man["files"].append(ent)
        _jsave(os.path.join(dst, "manifest.json"), man)
        for p, d in self.writes.items():
            os.makedirs(os.path.dirname(p), exist_ok=True)
            _jsave(p, d)
        for p in self.deletes:
            if os.path.exists(p):
                os.remove(p)
        for old in list_backups(self.wdir)[:-KEEP_BACKUPS]:
            shutil.rmtree(os.path.join(root, old), ignore_errors=True)
        return stamp


def list_backups(wdir):
    r = backup_root(wdir)
    return sorted(d for d in os.listdir(r) if os.path.isfile(os.path.join(r, d, "manifest.json"))) if os.path.isdir(r) else []


def restore(wdir, dry=False):
    bl = list_backups(wdir)
    if not bl:
        fail("nothing to undo: no buildings backup exists for this place")
    name = bl[-1]
    src = os.path.join(backup_root(wdir), name)
    man = _jload(os.path.join(src, "manifest.json"))
    plan = []
    for ent in man.get("files", []):
        p = os.path.normpath(os.path.join(wdir, ent["rel"]))
        if not os.path.abspath(p).startswith(os.path.abspath(wdir)):
            fail(f"backup {name} names a file outside the place: {ent['rel']}")
        if ent.get("existed"):
            c = os.path.join(src, ent["copy"])
            _jload(c)                                     # refuse a damaged backup before touching anything
            plan.append(("copy", c, p))
        else:
            plan.append(("delete", None, p))
    if not dry:
        for kind, c, p in plan:
            if kind == "copy":
                os.makedirs(os.path.dirname(p), exist_ok=True)
                tmp = p + ".tmp"
                shutil.copyfile(c, tmp)
                os.replace(tmp, p)
            elif os.path.exists(p):
                os.remove(p)
        shutil.rmtree(src)
    return {"restored": name, "op": man.get("op"), "info": man.get("info"), "files": [os.path.relpath(p, wdir).replace("\\", "/") for _k, _c, p in plan],
            "remaining": len(bl) - (0 if dry else 1), "dry": dry}


# ------------------------------------------------------------------ geometry
def _num(v, what):
    try:
        f = float(v)
    except (TypeError, ValueError):
        fail(f"{what}: {v!r} is not a number")
    if not math.isfinite(f):
        fail(f"{what}: {v!r} is not finite")
    return f


def parse_xy(text, what="point"):
    parts = [t for t in str(text).replace(";", ",").replace(" ", ",").split(",") if t != ""]
    if len(parts) != 2:
        fail(f"{what}: expected x,y, got {text!r}")
    return [_num(parts[0], what), _num(parts[1], what)]


def parse_points(text):
    out = []
    for part in str(text).replace("\n", ";").split(";"):
        if part.strip():
            out.append(parse_xy(part, "point"))
    return out


def read_points_file(path):
    if not os.path.exists(path):
        fail(f"points file not found: {path}")
    d = _jload(path)
    if isinstance(d, dict):
        d = d.get("points")
    if not isinstance(d, list):
        fail("points file must hold a list of [x, y] or {\"points\": [...]}")
    return d


def shoelace(pts):
    return sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def _poly(pts):
    from shapely.geometry import Polygon
    return Polygon([tuple(p[:2]) for p in pts])


def obb(pts):
    """(centre [x, y], angle deg of the long side from +x toward +y, long side, short side) of the minimum rotated rectangle."""
    g = _poly(pts).buffer(0)
    r = g.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        c = list(g.centroid.coords)[0]
        return [c[0], c[1]], 0.0, 0.0, 0.0
    c = list(r.exterior.coords)[:4]
    e0 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e1 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l0, l1 = math.hypot(*e0), math.hypot(*e1)
    d = e0 if l0 >= l1 else e1
    ang = math.degrees(math.atan2(d[1], d[0]))
    ctr = list(r.centroid.coords)[0]
    return [ctr[0], ctr[1]], ang, max(l0, l1), min(l0, l1)


def centroid(pts):
    c = _poly(pts).buffer(0).centroid
    return [c.x, c.y]


def bounds_of(wdir):
    try:
        b = _jload(os.path.join(wdir, "place.json")).get("bounds") or {}
        return (float(b["width_ft"]), float(b["height_ft"]))
    except Exception:
        return None


def clean_footprint(pts, bounds=None, what="footprint"):
    """Validate + normalise: finite, rounded to 0.01 ft, closing duplicate and repeated points dropped, simple, 6..400 ft sides, inside the place,
    counter-clockwise on the map (negative shoelace sum, y down)."""
    if not isinstance(pts, (list, tuple)):
        fail(f"{what}: points must be a list of [x, y]")
    out = []
    for p in pts:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            fail(f"{what}: bad point {p!r}")
        if not (math.isfinite(x) and math.isfinite(y)):
            fail(f"{what}: point {p!r} is not finite")
        x, y = round(x, 2), round(y, 2)
        if out and math.hypot(x - out[-1][0], y - out[-1][1]) < 0.05:
            continue
        out.append([x, y])
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 0.05:
        out.pop()
    if len(out) < 3:
        fail(f"{what}: a footprint needs at least 3 different points")
    if len(out) > MAX_POINTS:
        fail(f"{what}: {len(out)} points is more than {MAX_POINTS}")
    g = _poly(out)
    if not g.is_valid or g.area < 1.0:
        fail(f"{what}: the outline crosses itself (or has no area); draw a simple closed shape")
    _c, _a, lng, sht = obb(out)
    if sht < MIN_SIDE:
        fail(f"{what}: {sht:.1f} ft wide; a building must be at least {MIN_SIDE:g} ft on each side")
    if lng > MAX_SIDE:
        fail(f"{what}: {lng:.1f} ft long; at most {MAX_SIDE:g} ft")
    if bounds:
        c = g.centroid
        if c.x < -OUT_MARGIN_FT or c.y < -OUT_MARGIN_FT or c.x > bounds[0] + OUT_MARGIN_FT or c.y > bounds[1] + OUT_MARGIN_FT:
            fail(f"{what}: centre {c.x:.0f},{c.y:.0f} is outside the place ({bounds[0]:g} x {bounds[1]:g} ft); wrong view mapping?")
    if shoelace(out) > 0:
        out.reverse()
    return out


def rect(cx, cy, w, d, rot_deg=0.0):
    """Rectangle footprint: centre, width along the rotated x axis, depth along the rotated y axis, rotation degrees (from +x toward +y, clockwise on the map)."""
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    pts = []
    for ux, uy in ((-w / 2, -d / 2), (w / 2, -d / 2), (w / 2, d / 2), (-w / 2, d / 2)):
        pts.append([cx + ux * ca - uy * sa, cy + ux * sa + uy * ca])
    return pts


# ------------------------------------------------------------------ transforms of a building and its derived data
POINT_KEYS = ("point", "a", "b")
POLY_KEYS = ("polygon", "points", "ridge", "geometry")
VEC_KEYS = ("facing", "outward")


def _is_xy(v):
    return isinstance(v, (list, tuple)) and len(v) >= 2 and all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in v[:2])


def _xf_tree(o, f, rot, deg):
    """Apply the rigid map f to every coordinate in o (dicts / lists of the layout, rooms, doors, details), rotate direction vectors by rot, add deg to angles."""
    if isinstance(o, dict):
        for k, v in list(o.items()):
            if k in POINT_KEYS and _is_xy(v):
                o[k] = _r(f(v)) + list(v[2:])
            elif k in POLY_KEYS and isinstance(v, list) and v and all(_is_xy(p) for p in v):
                o[k] = [_r(f(p)) + list(p[2:]) for p in v]
            elif k in VEC_KEYS and _is_xy(v):
                o[k] = [round(x, 3) for x in rot(v)]
            elif k == "angle_deg" and isinstance(v, (int, float)) and not isinstance(v, bool):
                o[k] = round((v + deg + 180.0) % 360.0 - 180.0, 3) if deg else v
            elif isinstance(v, (dict, list)):
                _xf_tree(v, f, rot, deg)
    elif isinstance(o, list):
        for v in o:
            if isinstance(v, (dict, list)):
                _xf_tree(v, f, rot, deg)


def _r(p):
    return [round(float(p[0]), 3), round(float(p[1]), 3)]


def rigid(dx=0.0, dy=0.0, deg=0.0, about=(0.0, 0.0)):
    a = math.radians(deg)
    ca, sa = math.cos(a), math.sin(a)
    cx, cy = about

    def f(p):
        x, y = p[0] - cx, p[1] - cy
        return [cx + x * ca - y * sa + dx, cy + x * sa + y * ca + dy]

    def rot(v):
        return [v[0] * ca - v[1] * sa, v[0] * sa + v[1] * ca]
    return f, rot


def transform_building(b, f, rot, deg):
    b["geometry"]["points"] = [[round(x, 2), round(y, 2)] for x, y in (f(p) for p in b["geometry"]["points"])]
    for k in INTERIOR:
        if k in b:
            _xf_tree(b[k], f, rot, deg)
    for k in STALE:
        b.pop(k, None)


def drop_interior(b):
    gone = [k for k in INTERIOR if b.get(k)]
    for k in INTERIOR:
        b.pop(k, None)
    for k in STALE:
        b.pop(k, None)
    return gone


# ------------------------------------------------------------------ context: districts, roads, other buildings
def district_of(wdir, pts):
    p, d = _opt_json(wdir, "districts.json")
    if not d:
        return None
    from shapely.geometry import Point
    c = Point(*centroid(pts))
    best = None
    for e in d.get("districts", []):
        gp = (e.get("geometry") or {}).get("points") or []
        if len(gp) < 3:
            continue
        g = _poly(gp).buffer(0)
        if g.contains(c) and (best is None or g.area < best[0]):
            best = (g.area, e["id"])
    return best[1] if best else None


def district_ids(wdir):
    _p, d = _opt_json(wdir, "districts.json")
    return [e["id"] for e in (d or {}).get("districts", []) if e.get("id")]


def warnings_for(wdir, allb, bid, pts):
    """Overlap warnings for one footprint: other buildings (> 1 sq ft) and road surfaces (> 4 sq ft)."""
    from shapely.geometry import LineString
    g = _poly(pts).buffer(0)
    out = []
    for oid, (_p, ob) in allb.items():
        if oid == bid:
            continue
        op = (ob.get("geometry") or {}).get("points") or []
        if len(op) < 3:
            continue
        try:
            a = g.intersection(_poly(op).buffer(0)).area
        except Exception:
            continue
        if a > BLD_OVERLAP_WARN:
            out.append(f"{bid} overlaps building {oid} by {a:.0f} sq ft")
    _sp, sd = _opt_json(wdir, "streets.json")
    for s in (sd or {}).get("streets", []):
        gp = (s.get("geometry") or {}).get("points") or []
        if len(gp) < 2:
            continue
        try:
            a = g.intersection(LineString([tuple(p[:2]) for p in gp]).buffer(float((s.get("geometry") or {}).get("width_ft", 10.0)) / 2, cap_style=2)).area
        except Exception:
            continue
        if a > ROAD_OVERLAP_WARN:
            out.append(f"{bid} overlaps road {s['id']} ({s.get('name', '')}) by {a:.0f} sq ft")
    return out


def check_kind(kind, allb=None):
    known = set(KINDS) | {b.get("kind") for _p, b in (allb or {}).values() if b.get("kind")}
    k = str(kind or "").strip()
    if k not in known:
        fail(f"kind {k!r} not one of {', '.join(sorted(known))}")
    return k


def check_floors(v):
    f = _num(v, "floors")
    if f != int(f) or not (1 <= f <= 12):
        fail(f"floors must be a whole number 1..12, got {v!r}")
    return int(f)


def check_id(new, allb):
    if not ID_RE.match(new or "") or len(new) > 64:
        fail(f"building id {new!r} must look like bld_<words> (lower-case letters, digits, single underscores, at most 64 characters)")
    if new in allb:
        fail(f"building id {new} already exists")
    return new


def free_id(allb, kind, taken=()):
    k = re.sub(r"[^a-z0-9]+", "", str(kind).lower()) or "building"
    used = set(allb) | set(taken)
    n = 1
    for i in used:
        m = re.match(rf"^bld_{k}_(\d+)$", i)
        if m:
            n = max(n, int(m.group(1)) + 1)
    while f"bld_{k}_{n:03d}" in used:
        n += 1
    return f"bld_{k}_{n:03d}"


# ------------------------------------------------------------------ details.json / labels / region helpers
def _details(wdir):
    return _opt_json(wdir, "details.json")


def details_of(det, bid, kinds):
    return [(k, e) for k in kinds for e in (det or {}).get(k, []) if isinstance(e, dict) and e.get("building") == bid]


def _drop_details(det, ids, kinds):
    n = 0
    for k in kinds:
        if isinstance(det.get(k), list):
            keep = [e for e in det[k] if not (isinstance(e, dict) and e.get("building") in ids)]
            n += len(det[k]) - len(keep)
            det[k] = keep
    return n


def _label_overrides(wdir):
    return _opt_json(wdir, "label_overrides.json")


def _region(wdir):
    return _opt_json(wdir, "region.json")


# ------------------------------------------------------------------ operations (each returns a result dict; writes only when not dry)
def _done(tx, dry, out, info=None):
    out["files"] = [os.path.relpath(p, tx.wdir).replace("\\", "/") for p in tx.files()]
    out["backup"] = None if dry else tx.commit(info or {"ids": out.get("changed", []) + out.get("added", []) + out.get("deleted", [])})
    out["dry"] = dry
    return out


def op_delete(wdir, ids, dry=False):
    allb = load_all(wdir)
    ids = need(allb, ids, "delete")
    tx = Tx(wdir, "delete")
    for i in ids:
        tx.delete(allb[i][0])
    dp, det = _details(wdir)
    nd = 0
    if det:
        nd = _drop_details(det, set(ids), DETAIL_RIGID + DETAIL_LOT)
        if nd:
            tx.write(dp, det)
    lp, lo = _label_overrides(wdir)
    if lo and any(i in (lo.get("labels") or {}) for i in ids):
        for i in ids:
            lo["labels"].pop(i, None)
        tx.write(lp, lo)
    rp, rg = _region(wdir)
    if rg and isinstance(rg.get("id_map"), dict):
        hit = False
        for k in list(rg["id_map"]):
            v = rg["id_map"][k]
            if isinstance(v, list) and any(i in v for i in ids):
                rg["id_map"][k] = [x for x in v if x not in ids]
                hit = True
                if not rg["id_map"][k]:
                    del rg["id_map"][k]
                    rg.setdefault("dropped", []).append({"id": k, "reason": "deleted in the Buildings tab (building_edit.py)"})
        if hit:
            tx.write(rp, rg)
    return _done(tx, dry, {"deleted": ids, "count": len(ids), "details_removed": nd, "remaining": len(allb) - len(ids)})


def _new_building(allb, bid, name, kind, pts, floors, wdir, district=None, style=None, notes=""):
    b = {"id": bid, "name": name, "kind": kind, "status": "proposed", "geometry": {"type": "polygon", "points": pts}, "notes": notes or "",
         "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": floors}
    d = district if district is not None else district_of(wdir, pts)
    if d:
        b["district"] = d
    if style:
        b["style"] = style
    return b


def footprint_from_args(center=None, width=None, depth=None, rotation=0.0, points=None):
    if points is not None:
        if center is not None or width is not None or depth is not None:
            fail("give a rectangle (--center --width --depth [--rotation]) or --points, not both")
        return points
    if center is None or width is None or depth is None:
        fail("a new footprint needs --center x,y --width --depth (and --rotation), or --points")
    w, d = _num(width, "width"), _num(depth, "depth")
    return rect(center[0], center[1], w, d, _num(rotation or 0.0, "rotation"))


def op_add(wdir, name, kind, pts, floors=1, wanted_id=None, district=None, style=None, notes="", dry=False):
    allb = load_all(wdir)
    kind = check_kind(kind or "house", allb)
    fl = check_floors(floors if floors is not None else 1)
    pts = clean_footprint(pts, bounds_of(wdir), "new building")
    bid = check_id(wanted_id, allb) if wanted_id else free_id(allb, kind)
    if district not in (None, ""):
        if district not in district_ids(wdir):
            fail(f"unknown district {district!r}; known: {', '.join(district_ids(wdir)) or '(none)'}")
    if style:
        _check_style(style)
    nm = str(name or "").strip() or f"{kind.capitalize()} {bid.rsplit('_', 1)[-1].lstrip('0') or '0'}"
    b = _new_building(allb, bid, nm, kind, pts, fl, wdir, district or None, style, notes)
    warn = warnings_for(wdir, allb, bid, pts)
    tx = Tx(wdir, "add")
    tx.write(os.path.join(bdir(wdir), bid + ".json"), b)
    _c, _a, lng, sht = obb(pts)
    return _done(tx, dry, {"added": [bid], "count": 1, "name": nm, "district": b.get("district"), "size_ft": [round(lng, 1), round(sht, 1)],
                           "area_ft2": round(_poly(pts).area, 1), "warnings": warn})


def _check_style(style):
    try:
        import building_styles as bs
        known = ["auto"] + sorted(bs.load_presets().keys())
    except Exception:
        return style
    if style not in known:
        fail(f"unknown building style {style!r}")
    return style


def _rigid_op(wdir, ids, opname, make, with_lot=False, dry=False):
    allb = load_all(wdir)
    ids = need(allb, ids, opname)
    bnd = bounds_of(wdir)
    tx = Tx(wdir, opname)
    dp, det = _details(wdir)
    det_hit = False
    warn = []
    for i in ids:
        p, b = allb[i]
        f, rot, deg = make(b)
        transform_building(b, f, rot, deg)
        b["geometry"]["points"] = clean_footprint(b["geometry"]["points"], bnd, i)
        for _k, e in details_of(det, i, DETAIL_RIGID + (DETAIL_LOT if with_lot else ())):
            _xf_tree(e, f, rot, deg)
            det_hit = True
        if b.get("district") is not None:
            nd = district_of(wdir, b["geometry"]["points"])
            if nd and nd != b["district"]:
                warn.append(f"{i}: now inside district {nd} (was {b['district']}); set it with Properties if wanted")
        tx.write(p, b)
    if det_hit:
        tx.write(dp, det)
    for i in ids:
        warn += warnings_for(wdir, allb, i, allb[i][1]["geometry"]["points"])
    return _done(tx, dry, {"changed": ids, "count": len(ids), "warnings": warn})


def op_move(wdir, ids, dx=None, dy=None, to=None, with_lot=False, dry=False):
    if to is not None and (dx or dy):
        fail("give --dx/--dy or --to, not both")
    if to is None and not dx and not dy:
        fail("move needs --dx / --dy (feet) or --to x,y (new centre)")
    if to is not None and len(ids) != 1:
        fail("--to moves exactly one building (use --dx/--dy for several)")
    ddx, ddy = _num(dx or 0, "dx"), _num(dy or 0, "dy")

    def make(b):
        if to is not None:
            c = centroid(b["geometry"]["points"])
            f, rot = rigid(to[0] - c[0], to[1] - c[1])
        else:
            f, rot = rigid(ddx, ddy)
        return f, rot, 0.0
    return _rigid_op(wdir, ids, "move", make, with_lot, dry)


def op_rotate(wdir, ids, deg, with_lot=False, dry=False):
    deg = _num(deg, "deg")
    if abs(deg) > 360:
        fail("--deg must be -360..360")

    def make(b):
        f, rot = rigid(deg=deg, about=centroid(b["geometry"]["points"]))
        return f, rot, deg
    return _rigid_op(wdir, ids, "rotate", make, with_lot, dry)


def _reshape_one(wdir, allb, det, tx, bid, newpts, bnd):
    p, b = allb[bid]
    pts = clean_footprint(newpts, bnd, bid)
    b["geometry"]["points"] = pts
    gone = drop_interior(b)
    nd = _drop_details(det, {bid}, DETAIL_RIGID) if det else 0
    tx.write(p, b)
    return gone, nd


def op_resize(wdir, ids, width=None, depth=None, scale=None, dry=False):
    if scale is None and width is None and depth is None:
        fail("resize needs --width and / or --depth (feet), or --scale")
    if scale is not None and (width is not None or depth is not None):
        fail("give --scale or --width / --depth, not both")
    allb = load_all(wdir)
    ids = need(allb, ids, "resize")
    bnd = bounds_of(wdir)
    dp, det = _details(wdir)
    tx = Tx(wdir, "resize")
    warn, info = [], {}
    for i in ids:
        pts = allb[i][1]["geometry"]["points"]
        c, ang, lng, sht = obb(pts)
        if scale is not None:
            s = _num(scale, "scale")
            if not (0.1 <= s <= 10):
                fail("--scale must be 0.1..10")
            sx = sy = s
        else:
            sx = (_num(width, "width") / lng) if width is not None and lng > 0 else 1.0
            sy = (_num(depth, "depth") / sht) if depth is not None and sht > 0 else 1.0
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        new = []
        for x, y in pts:
            u, v = (x - c[0]) * ca + (y - c[1]) * sa, -(x - c[0]) * sa + (y - c[1]) * ca
            u, v = u * sx, v * sy
            new.append([c[0] + u * ca - v * sa, c[1] + u * sa + v * ca])
        gone, nd = _reshape_one(wdir, allb, det, tx, i, new, bnd)
        _c2, _a2, l2, s2 = obb(allb[i][1]["geometry"]["points"])
        info[i] = {"before_ft": [round(lng, 1), round(sht, 1)], "after_ft": [round(l2, 1), round(s2, 1)], "interior_dropped": gone, "details_dropped": nd}
    if det and any(v["details_dropped"] for v in info.values()):
        tx.write(dp, det)
    for i in ids:
        warn += warnings_for(wdir, allb, i, allb[i][1]["geometry"]["points"])
    return _done(tx, dry, {"changed": ids, "count": len(ids), "sizes": info, "warnings": warn})


def op_set_footprint(wdir, bid, pts, dry=False):
    allb = load_all(wdir)
    need(allb, [bid], "reshape")
    dp, det = _details(wdir)
    tx = Tx(wdir, "reshape")
    gone, nd = _reshape_one(wdir, allb, det, tx, bid, pts, bounds_of(wdir))
    if nd:
        tx.write(dp, det)
    return _done(tx, dry, {"changed": [bid], "count": 1, "interior_dropped": gone, "details_dropped": nd,
                           "warnings": warnings_for(wdir, allb, bid, allb[bid][1]["geometry"]["points"])})


def op_duplicate(wdir, ids, dx=20.0, dy=20.0, dry=False):
    allb = load_all(wdir)
    ids = need(allb, ids, "duplicate")
    bnd = bounds_of(wdir)
    tx = Tx(wdir, "duplicate")
    added, warn, taken = [], [], []
    f, _rot = rigid(_num(dx, "dx"), _num(dy, "dy"))
    for i in ids:
        src = allb[i][1]
        nb = copy.deepcopy(src)
        for k in INTERIOR + STALE + ("region",):
            nb.pop(k, None)
        nid = free_id(allb, src.get("kind") or "house", taken)
        taken.append(nid)
        nb["id"] = nid
        nb["name"] = (src.get("name") or i) + " (copy)"
        nb["status"] = "proposed"
        nb["links"] = {"foundry_scene": None, "model3d": None, "ai_layer": None}
        nb["geometry"] = {"type": "polygon", "points": clean_footprint([f(p) for p in src["geometry"]["points"]], bnd, nid)}
        d = district_of(wdir, nb["geometry"]["points"])
        if d:
            nb["district"] = d
        elif "district" in nb:
            nb.pop("district")
        tx.write(os.path.join(bdir(wdir), nid + ".json"), nb)
        added.append(nid)
    allb2 = dict(allb)
    for nid in added:
        nb = tx.writes[os.path.abspath(os.path.join(bdir(wdir), nid + ".json"))]
        warn += warnings_for(wdir, allb2, nid, nb["geometry"]["points"])
        allb2[nid] = (None, nb)
    return _done(tx, dry, {"added": added, "count": len(added), "from": ids, "warnings": warn})


def _swap_prefix(o, old, new):
    """Every string equal to old or starting with old + '_' gets the new prefix (ids inside rooms / doors / layout / details entries)."""
    if isinstance(o, dict):
        return {k: _swap_prefix(v, old, new) for k, v in o.items()}
    if isinstance(o, list):
        return [_swap_prefix(v, old, new) for v in o]
    if isinstance(o, str) and (o == old or o.startswith(old + "_")):
        return new + o[len(old):]
    return o


def op_rename(wdir, bid, new_id=None, name=None, dry=False):
    allb = load_all(wdir)
    need(allb, [bid], "rename")
    if not new_id and name is None:
        fail("rename needs --new-id and / or --name")
    p, b = allb[bid]
    tx = Tx(wdir, "rename")
    refs = []
    if name is not None:
        nm = str(name).strip()
        if not nm:
            fail("the name cannot be empty")
        if len(nm) > 120:
            fail("the name is longer than 120 characters")
        b["name"] = nm
    out_id = bid
    if new_id and new_id != bid:
        check_id(new_id, allb)
        out_id = new_id
        reg = b.get("region")
        b = _swap_prefix({k: v for k, v in b.items() if k != "region"}, bid, new_id)
        if reg is not None:
            b["region"] = reg                                    # parent_id names the PARENT place's building: unchanged
        tx.delete(p)
        tx.write(os.path.join(bdir(wdir), new_id + ".json"), b)
        dp, det = _details(wdir)
        if det:
            hit = False
            for k in DETAIL_RIGID + DETAIL_LOT:
                for j, e in enumerate(det.get(k) or []):
                    if isinstance(e, dict) and e.get("building") == bid:
                        det[k][j] = _swap_prefix(e, bid, new_id)
                        hit = True
            if hit:
                tx.write(dp, det)
                refs.append("details.json")
        lp, lo = _label_overrides(wdir)
        if lo and bid in (lo.get("labels") or {}):
            lo["labels"][new_id] = lo["labels"].pop(bid)
            tx.write(lp, lo)
            refs.append("label_overrides.json")
        rp, rg = _region(wdir)
        if rg:
            hit = False
            for k, v in list((rg.get("id_map") or {}).items()):
                if isinstance(v, list) and bid in v:
                    rg["id_map"][k] = [new_id if x == bid else x for x in v]
                    hit = True
            for sect in ("interiors",):
                if isinstance(rg.get(sect), dict) and bid in rg[sect]:
                    rg[sect][new_id] = rg[sect].pop(bid)
                    hit = True
            if hit:
                tx.write(rp, rg)
                refs.append("region.json")
    else:
        tx.write(p, b)
    return _done(tx, dry, {"changed": [out_id], "renamed": {bid: out_id} if out_id != bid else {}, "name": b.get("name"), "count": 1, "references": refs})


def op_set_props(wdir, ids, props, dry=False):
    """props: name, kind, floors, district ('' = clear, 'auto' = by containment), notes, description, owner, tags (comma list, '' = clear), status."""
    allb = load_all(wdir)
    ids = need(allb, ids, "properties")
    if not props:
        fail("nothing to set: give at least one of --name --kind --floors --district --notes --description --owner --tags --status")
    if "name" in props and len(ids) > 1:
        fail("--name sets one building's name; tick a single building")
    vals = {}
    for k, v in props.items():
        if k == "kind":
            vals[k] = check_kind(v, allb)
        elif k == "floors":
            vals[k] = check_floors(v)
        elif k == "status":
            if v not in STATUS:
                fail(f"status must be one of {', '.join(STATUS)}")
            vals[k] = v
        elif k == "district":
            v = str(v).strip()
            if v not in ("", "auto") and v not in district_ids(wdir):
                fail(f"unknown district {v!r}; known: {', '.join(district_ids(wdir)) or '(none)'}")
            vals[k] = v
        elif k == "tags":
            tags = [t.strip() for t in str(v).split(",") if t.strip()]
            for t in tags:
                if len(t) > 40:
                    fail(f"tag {t[:20]!r}... longer than 40 characters")
            vals[k] = sorted(dict.fromkeys(tags))
        elif k in TEXT_PROPS:
            s = str(v).strip()
            if k == "name" and not s:
                fail("the name cannot be empty")
            if len(s) > 2000:
                fail(f"{k} is longer than 2000 characters")
            vals[k] = s
        else:
            fail(f"unknown property {k!r}")
    tx = Tx(wdir, "props")
    warn = []
    for i in ids:
        p, b = allb[i]
        if "floors" in vals and b.get("rooms"):
            have = 1 + max([int(r.get("floor", 0)) for r in b["rooms"]] or [0])
            if have != vals["floors"]:
                fail(f"{i}: has a generated interior layout for {have} storey(s); changing floors to {vals['floors']} would break it "
                     f"(Resize or Reshape drops the interior; or edit another building)")
        for k, v in vals.items():
            if k == "district":
                d = district_of(wdir, b["geometry"]["points"]) if v == "auto" else v
                if d:
                    b["district"] = d
                else:
                    b.pop("district", None)
            elif k == "tags":
                if v:
                    b["tags"] = v
                else:
                    b.pop("tags", None)
            elif k in ("description", "owner") and v == "":
                b.pop(k, None)
            else:
                b[k] = v
        if "kind" in vals and (b.get("layout") or {}).get("kind") not in (None, vals["kind"]):
            warn.append(f"{i}: the stored interior was generated for kind {b['layout']['kind']}; Resize / Reshape (or a new interior) regenerates it")
        tx.write(p, b)
    return _done(tx, dry, {"changed": ids, "count": len(ids), "set": vals, "warnings": warn})


def op_set_door(wdir, bid, edge, pos=0.5, width=None, dry=False):
    """Front door of one building in details.json (the exporter's exterior opening): footprint edge index (0 = first point to second), position 0..1 along it."""
    allb = load_all(wdir)
    need(allb, [bid], "door")
    p, b = allb[bid]
    pts = b["geometry"]["points"]
    try:
        e = int(edge)
    except (TypeError, ValueError):
        fail(f"--edge must be a whole number 0..{len(pts) - 1}")
    if not (0 <= e < len(pts)):
        fail(f"--edge must be 0..{len(pts) - 1} ({bid} has {len(pts)} sides)")
    t = _num(pos, "pos")
    if not (0.0 <= t <= 1.0):
        fail("--pos must be 0..1 (0 = start of the side, 1 = its end)")
    a, q = pts[e], pts[(e + 1) % len(pts)]
    L = math.hypot(q[0] - a[0], q[1] - a[1])
    w = _num(width, "door width") if width is not None else (6.0 if b.get("kind") in ("civic", "inn", "barn", "stable", "craft") else 3.5)
    if not (2.0 <= w <= 16.0):
        fail("door width must be 2..16 ft")
    if L < w + 1.0:
        fail(f"side {e} is {L:.1f} ft long: too short for a {w:g} ft door")
    t = min(max(t, (w / 2 + 0.5) / L), 1 - (w / 2 + 0.5) / L)
    mid = [a[0] + (q[0] - a[0]) * t, a[1] + (q[1] - a[1]) * t]
    n = [(q[1] - a[1]) / L, -(q[0] - a[0]) / L]
    from shapely.geometry import Point
    if _poly(pts).buffer(0).contains(Point(mid[0] + n[0] * 0.5, mid[1] + n[1] * 0.5)):
        n = [-n[0], -n[1]]
    dp, det = _details(wdir)
    if det is None:
        det = {"canon": False, "note": "details written by building_edit.py (front doors set in the Buildings tab)", "doors": []}
    door = {"id": f"{bid}_door1", "building": bid, "edge": e, "point": [round(mid[0], 2), round(mid[1], 2)], "width_ft": w,
            "facing": [round(n[0], 3), round(n[1], 3)], "detail": True, "set_by": "building_edit"}
    det["doors"] = [d for d in det.get("doors", []) if not (isinstance(d, dict) and d.get("building") == bid)] + [door]
    tx = Tx(wdir, "door")
    tx.write(dp, det)
    warn = []
    if b.get("layout") or b.get("rooms"):
        drop_interior(b)
        tx.write(p, b)
        warn.append(f"{bid}: stored interior dropped (its entry room followed the old door); the exporter generates a new one")
    return _done(tx, dry, {"changed": [bid], "count": 1, "door": door, "warnings": warn})


def building_id_from_name(name, ids):
    """Illustrator item name -> building id ('_x5F_' decoded; suffixes such as _lot or ' 2' ignored). Longest matching id wins; None if none."""
    n = str(name or "").replace("_x5F_", "_").strip()
    if n in ids:
        return n
    for i in sorted(ids, key=len, reverse=True):
        if n.startswith(i) and n[len(i):len(i) + 1] in ("_", " ", "-"):
            return i
    return None


def op_apply_paths(wdir, paths, mode="sync", name=None, kind="house", floors=1, dry=False):
    """paths: [{name, points [[x,y]...] in feet, closed}]. reshape = every path names an existing building; add = every path becomes a new building;
    sync = named paths reshape, the rest are added. All validated first, one backup, one write."""
    if mode not in ("reshape", "add", "sync"):
        fail("mode must be reshape, add or sync")
    if not isinstance(paths, list) or not paths:
        fail(f"no paths: select closed paths in Illustrator (or draw them on the '{FOOTPRINT_LAYER}' layer)")
    allb = load_all(wdir)
    bnd = bounds_of(wdir)
    kind = check_kind(kind or "house", allb)
    fl = check_floors(floors or 1)
    ids = set(allb)
    seen, plan = set(), []
    for k, p in enumerate(paths):
        nm = str(p.get("name") or "")
        lab = nm or f"path {k + 1}"
        if not p.get("closed"):
            fail(f"{lab}: is an open path; a footprint must be a closed shape (Object > Path > Join, or draw with the Rectangle / Pen tool)")
        bid = building_id_from_name(nm, ids)
        if mode == "add" and bid:
            fail(f"{lab}: is already building {bid}; use Reshape, or rename the path")
        if mode == "reshape" and not bid:
            fail(f"{lab}: is not named like an existing building id (bld_...)")
        if bid:
            if bid in seen:
                fail(f"building {bid} appears twice in the selection")
            seen.add(bid)
        plan.append((bid, lab, clean_footprint(p.get("points"), bnd, lab)))
    dp, det = _details(wdir)
    tx = Tx(wdir, "paths_" + mode)
    changed, added, warn, nd = [], [], [], 0
    n_new = sum(1 for b, _l, _p in plan if not b)
    taken = []
    for bid, lab, pts in plan:
        if bid:
            _g, d = _reshape_one(wdir, allb, det, tx, bid, pts, bnd)
            nd += d
            changed.append(bid)
        else:
            nid = free_id(allb, kind, taken)
            taken.append(nid)
            base = (name or "").strip()
            nm = (f"{base} {len(added) + 1}" if n_new > 1 else base) if base else f"{kind.capitalize()} {nid.rsplit('_', 1)[-1].lstrip('0') or '0'}"
            b = _new_building(allb, nid, nm, kind, pts, fl, wdir)
            tx.write(os.path.join(bdir(wdir), nid + ".json"), b)
            allb[nid] = (os.path.join(bdir(wdir), nid + ".json"), b)
            added.append(nid)
    if nd:
        tx.write(dp, det)
    for i in changed + added:
        warn += warnings_for(wdir, allb, i, allb[i][1]["geometry"]["points"])
    return _done(tx, dry, {"changed": changed, "added": added, "count": len(changed) + len(added), "warnings": warn})


# ------------------------------------------------------------------ listing, drawing, checks
def info(wdir):
    out = []
    for bid, (_p, b) in load_all(wdir).items():
        pts = (b.get("geometry") or {}).get("points") or []
        row = {"id": bid, "name": b.get("name", ""), "kind": b.get("kind", ""), "floors": int(b.get("floors", 1) or 1), "style": b.get("style", ""),
               "district": b.get("district", ""), "status": b.get("status", ""), "notes": b.get("notes", ""), "description": b.get("description", ""),
               "owner": b.get("owner", ""), "tags": b.get("tags", []), "has_layout": bool(b.get("rooms") or b.get("layout")), "points": len(pts)}
        if len(pts) >= 3:
            try:
                c, ang, lng, sht = obb(pts)
                row.update({"center": [round(c[0], 1), round(c[1], 1)], "size_ft": [round(lng, 1), round(sht, 1)], "angle_deg": round(ang, 1),
                            "area_ft2": round(_poly(pts).buffer(0).area, 1)})
            except Exception:
                pass
        out.append(row)
    return out


def draw_svg(wdir, view, out_path, ids=None):
    """Footprints as closed paths on the layer 'Building Footprints', in page points of `view` (panelio.py view json). Path names are the building ids."""
    k, m = float(view["k"]), float(view["margin_in"]) * 72.0
    x0, y0 = float(view["x0"]), float(view["y0"])
    pw, ph = float(view["page_in"][0]) * 72.0, float(view["page_in"][1]) * 72.0
    items, n = [], 0
    for bid, (_p, b) in load_all(wdir).items():
        pts = (b.get("geometry") or {}).get("points") or []
        if len(pts) < 3 or (ids and bid not in ids):
            continue
        d = "M" + " L".join(f"{m + (x - x0) * k:.2f},{m + (y - y0) * k:.2f}" for x, y in (p[:2] for p in pts)) + " Z"
        items.append(f'    <path id="{bid}" fill="none" stroke="#1c7ed6" stroke-width="1" d="{d}"/>')
        n += 1
    from lib_svg import _encode_ids
    svg = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/" '
           'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
           f'width="{pw:g}pt" height="{ph:g}pt" viewBox="0 0 {pw:g} {ph:g}">',
           f'  <g id="{FOOTPRINT_LAYER}" inkscape:groupmode="layer" i:layer="yes" inkscape:label="{FOOTPRINT_LAYER}">'] + items + ["  </g>", "</svg>"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_encode_ids("\n".join(svg) + "\n"))
    return {"path": out_path, "buildings": n, "layer": FOOTPRINT_LAYER}


def svg_absent(svg_path, ids):
    """Which of ids still appear in an SVG (as the id itself, its Illustrator-encoded form bld_x5F_..., or an id with a suffix). -> {ok, present{id: n}}"""
    if not os.path.exists(svg_path):
        fail(f"svg not found: {svg_path}")
    txt = open(svg_path, encoding="utf-8").read()
    present = {}
    for i in ids:
        pats = [re.escape(i), re.escape(i.replace("_", "_x5F_"))]
        n = sum(len(re.findall(r'(?<![\w])' + p + r'(?![A-Za-z0-9])', txt)) for p in pats)
        if n:
            present[i] = n
    return {"ok": not present, "present": present, "checked": list(ids), "svg": svg_path}
