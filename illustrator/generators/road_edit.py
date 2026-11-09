#!/usr/bin/env python3
"""Road geometry editing for world/<place>/streets.json (delete, add, reshape, split, join, Illustrator centreline sync, undo).
Pure functions plus a small backup stack; the command line lives in object_edit.py (delete-road, add-road, set-road-points, split-road, join-roads,
apply-paths, draw-roads, restore-streets). Nothing here edits terrain or buildings.

Rules
  * Every writing call first copies streets.json to world/<place>/streets_backups/streets_<stamp>.json (newest 30 kept); restore-streets pops the newest.
  * Deleting a road (delete-road, or join-roads dropping the second road) also removes what other place files hold for it: region kerbs (details.json),
    off-map markers (markers.json) and pinned label positions (label_overrides.json). Those files are backed up in streets_<stamp>.side/ with the same
    backup and restore-streets puts them back together with streets.json. Per-road caches (elevations_ft ...) and `edit` blocks live inside the street and go with it.
    world/<place>/export (the 3D pack, roads.json) is only rebuilt by Export world pack.
  * Bridges (kind "bridge") are never edited, deleted, split or joined here (Bridges tab). A road that bridges.json names cannot be deleted.
  * Any validation failure raises RoadError before a single byte is written.
  * Changing a road's points drops its cached per-vertex heights (elevations_ft, elevation_ft, grade_max, grade_raw_max, cut_fill_ft): the exporter then samples the
    terrain along the new line (worldpack uses elevations_ft only when present, so a stale array of the wrong length must never survive).
  * Illustrator side: the layer "Road Centerlines" holds one open path per road named by its street id (draw_svg). The Roads layer of the town drawing holds the
    street OUTLINES (closed rings), which cannot be read back as a centreline; apply-paths refuses closed paths.
"""
import datetime
import json
import math
import os
import re
import shutil

CENTERLINE_LAYER = "Road Centerlines"
KINDS = ["road", "street", "lane", "alley"]
WIDTH = (2.0, 120.0)
MAX_POINTS = 5000
OUT_MARGIN_FT = 2000.0              # points further outside the place bounds than this are refused (almost always a wrong page <-> feet mapping)
STALE = ("elevations_ft", "elevation_ft", "grade_max", "grade_raw_max", "cut_fill_ft")
KEEP_BACKUPS = 30


class RoadError(SystemExit):
    pass


def fail(msg):
    raise RoadError(msg)


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jsave(p, d, indent=1):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=indent, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


# ------------------------------------------------------------------ files and backups
def streets_path(wdir):
    return os.path.join(wdir, "streets.json")


def backup_dir(wdir):
    return os.path.join(wdir, "streets_backups")


def load(wdir):
    p = streets_path(wdir)
    if not os.path.exists(p):
        fail(f"no streets.json in {wdir}")
    return _jload(p)


def backups(wdir):
    d = backup_dir(wdir)
    return sorted(f for f in os.listdir(d) if f.startswith("streets_") and f.endswith(".json")) if os.path.isdir(d) else []


def side_dir(wdir, name):
    """Folder next to a streets backup holding the other place files that the same change rewrote (SIDE_FILES); restored together by restore()."""
    return os.path.join(backup_dir(wdir), name[:-5] + ".side")


def backup(wdir, side=()):
    """Copy streets.json (and each existing file named in `side`) to the backup stack. Returns the backup file name."""
    d = backup_dir(wdir)
    os.makedirs(d, exist_ok=True)
    name = "streets_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".json"
    shutil.copyfile(streets_path(wdir), os.path.join(d, name))
    side = [f for f in side if os.path.exists(os.path.join(wdir, f))]
    if side:
        sd = side_dir(wdir, name)
        os.makedirs(sd, exist_ok=True)
        for f in side:
            shutil.copyfile(os.path.join(wdir, f), os.path.join(sd, f))
    for old in backups(wdir)[:-KEEP_BACKUPS]:
        os.remove(os.path.join(d, old))
        shutil.rmtree(side_dir(wdir, old), ignore_errors=True)
    return name


def save(wdir, doc, extra=None):
    """Backup then write. Call only after every check passed. extra = {file name in wdir: new json doc} written in the same step (backed up with it)."""
    extra = extra or {}
    name = backup(wdir, sorted(extra))
    _jsave(streets_path(wdir), doc)
    for f, d in sorted(extra.items()):
        _jsave(os.path.join(wdir, f), d)
    return name


def restore(wdir, dry=False):
    bl = backups(wdir)
    if not bl:
        fail("nothing to restore: no streets backup exists for this place")
    name = bl[-1]
    src = os.path.join(backup_dir(wdir), name)
    _jload(src)                                   # refuse a damaged backup before touching streets.json
    sd = side_dir(wdir, name)
    side = sorted(os.listdir(sd)) if os.path.isdir(sd) else []
    for f in side:
        _jload(os.path.join(sd, f))
    if not dry:
        tmp = streets_path(wdir) + ".tmp"
        shutil.copyfile(src, tmp)
        os.replace(tmp, streets_path(wdir))
        for f in side:                            # details / markers / label overrides rewritten by the same change
            tmp = os.path.join(wdir, f) + ".tmp"
            shutil.copyfile(os.path.join(sd, f), tmp)
            os.replace(tmp, os.path.join(wdir, f))
        os.remove(src)
        shutil.rmtree(sd, ignore_errors=True)
    return {"restored": name, "restored_files": ["streets.json"] + side, "remaining": len(bl) - (0 if dry else 1), "dry": dry}


# ------------------------------------------------------------------ other files that name a road
SIDE_FILES = ("details.json", "markers.json", "label_overrides.json")


def references(wdir, gone):
    """Entries in the other place files that belong to the roads in `gone` (deleted): region kerbs (details.json kerbs[].street), off-map markers
    (markers.json markers[].street / parent_street) and pinned label positions (label_overrides.json labels{<id>}). -> ({file: cleaned doc}, {file: n removed})"""
    gone = set(gone)
    out, counts = {}, {}
    for f in SIDE_FILES:
        p = os.path.join(wdir, f)
        if not os.path.exists(p):
            continue
        try:
            doc = _jload(p)
        except (OSError, ValueError):
            continue
        n = 0
        if f == "label_overrides.json":
            labels = doc.get("labels") if isinstance(doc, dict) else None
            if isinstance(labels, dict):
                for k in [k for k in labels if k in gone]:
                    del labels[k]
                    n += 1
        elif isinstance(doc, dict):
            for k, v in doc.items():
                if isinstance(v, list):
                    keep = [x for x in v if not (isinstance(x, dict) and (x.get("street") in gone or x.get("parent_street") in gone))]
                    n += len(v) - len(keep)
                    doc[k] = keep
        if n:
            out[f], counts[f] = doc, n
    return out, counts


# ------------------------------------------------------------------ points
def parse_points(text):
    """'x,y;x,y;...' -> [[x, y], ...]"""
    out = []
    for part in str(text).replace("\n", ";").split(";"):
        part = part.strip()
        if not part:
            continue
        xy = part.replace(" ", ",").split(",")
        xy = [t for t in xy if t != ""]
        if len(xy) != 2:
            fail(f"bad point {part!r}: expected x,y")
        try:
            out.append([float(xy[0]), float(xy[1])])
        except ValueError:
            fail(f"bad point {part!r}: not numbers")
    return out


def read_points_file(path):
    if not os.path.exists(path):
        fail(f"points file not found: {path}")
    d = _jload(path)
    if isinstance(d, dict):
        d = d.get("points", d.get("polyline"))
    if not isinstance(d, list):
        fail("points file must hold a list of [x, y] or {\"points\": [...]}")
    return d


def clean_points(pts, bounds=None, what="road"):
    """Validate and normalise a polyline: floats rounded to 0.1 ft, consecutive duplicates dropped, >= 2 points, length >= 2 ft, inside the place bounds +- margin."""
    if not isinstance(pts, (list, tuple)) or len(pts) < 2:
        fail(f"{what}: a road needs at least 2 points")
    if len(pts) > MAX_POINTS:
        fail(f"{what}: {len(pts)} points is more than {MAX_POINTS}; use --simplify")
    out = []
    for p in pts:
        try:
            x, y = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError):
            fail(f"{what}: bad point {p!r}")
        if not (math.isfinite(x) and math.isfinite(y)):
            fail(f"{what}: point {p!r} is not finite")
        x, y = round(x, 1), round(y, 1)
        if bounds:
            if x < -OUT_MARGIN_FT or y < -OUT_MARGIN_FT or x > bounds[0] + OUT_MARGIN_FT or y > bounds[1] + OUT_MARGIN_FT:
                fail(f"{what}: point {x:g},{y:g} is far outside the place ({bounds[0]:g} x {bounds[1]:g} ft); wrong view mapping?")
        if out and math.hypot(x - out[-1][0], y - out[-1][1]) < 0.05:
            continue
        out.append([x, y])
    if len(out) < 2:
        fail(f"{what}: all points are the same place")
    if length(out) < 2.0:
        fail(f"{what}: shorter than 2 ft")
    return out


def length(pts):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _pd(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    d2 = dx * dx + dy * dy
    if d2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / d2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def simplify(pts, tol):
    """Douglas-Peucker; endpoints kept. tol in feet (0 = unchanged)."""
    if tol <= 0 or len(pts) < 3:
        return [list(p) for p in pts]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        best, bi = -1.0, None
        for k in range(i + 1, j):
            d = _pd(pts[k], pts[i], pts[j])
            if d > best:
                best, bi = d, k
        if bi is not None and best > tol:
            keep[bi] = True
            stack += [(i, bi), (bi, j)]
    return [list(p) for p, k in zip(pts, keep) if k]


def smooth(pts, iterations):
    """Laplacian smoothing (each inner point moves halfway to the mean of its neighbours), endpoints fixed. Point count unchanged."""
    q = [list(p) for p in pts]
    for _ in range(int(iterations)):
        n = [q[0]]
        for i in range(1, len(q) - 1):
            n.append([q[i][0] * 0.5 + (q[i - 1][0] + q[i + 1][0]) * 0.25, q[i][1] * 0.5 + (q[i - 1][1] + q[i + 1][1]) * 0.25])
        n.append(q[-1])
        q = n
    return [[round(x, 1), round(y, 1)] for x, y in q]


def shape(pts, simplify_ft=0.0, smooth_n=0):
    if simplify_ft < 0 or simplify_ft > 200:
        fail("--simplify must be 0..200 feet")
    if smooth_n < 0 or smooth_n > 50:
        fail("--smooth must be 0..50 iterations")
    out = smooth(pts, smooth_n) if smooth_n else [list(p) for p in pts]
    return simplify(out, simplify_ft)


# ------------------------------------------------------------------ helpers on the document
def bounds_of(wdir):
    try:
        b = _jload(os.path.join(wdir, "place.json")).get("bounds") or {}
        return (float(b["width_ft"]), float(b["height_ft"]))
    except Exception:
        return None


def by_id(doc):
    return {s["id"]: s for s in doc.get("streets", [])}


def need_editable(doc, ids, what="edit"):
    """Ids -> street dicts; refuses unknown ids and bridges."""
    m = by_id(doc)
    ids = list(dict.fromkeys(ids))
    if not ids:
        fail("no road ids given")
    miss = [i for i in ids if i not in m]
    if miss:
        fail("unknown road id(s): " + ", ".join(miss))
    br = [i for i in ids if m[i].get("kind") == "bridge"]
    if br:
        fail("cannot " + what + " a bridge here (use the Bridges tab): " + ", ".join(br))
    return [m[i] for i in ids]


def referenced_by_bridges(wdir, rid):
    p = os.path.join(wdir, "bridges.json")
    if not os.path.exists(p):
        return False
    try:
        txt = open(p, encoding="utf-8").read()
    except OSError:
        return False
    return ('"' + rid + '"') in txt


def drop_stale(s):
    for k in STALE:
        s.pop(k, None)


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    return s or "road"


def new_id(doc, name, wanted=None):
    ids = set(by_id(doc))
    if wanted:
        if not re.fullmatch(r"str_[A-Za-z0-9_]+", wanted):
            fail(f"road id {wanted!r} must look like str_name (letters, digits, underscore)")
        if wanted in ids:
            fail(f"road id {wanted} already exists")
        return wanted
    base = "str_" + slug(name)
    cand, n = base, 2
    while cand in ids:
        cand = f"{base}_{n}"
        n += 1
    return cand


def check_kind(kind):
    if kind not in KINDS:
        fail(f"kind {kind!r} not one of {', '.join(KINDS)} (bridges are made on the Bridges tab)")
    return kind


def check_width(w):
    try:
        w = float(w)
    except (TypeError, ValueError):
        fail(f"width {w!r} is not a number")
    if not (WIDTH[0] <= w <= WIDTH[1]):
        fail(f"width {w:g} outside {WIDTH[0]:g}..{WIDTH[1]:g} ft")
    return w


def make_street(doc, name, kind, width, pts, wanted_id=None):
    name = str(name or "").strip() or "New road"
    check_kind(kind)
    return {"id": new_id(doc, name, wanted_id), "name": name, "kind": kind, "status": "proposed",
            "geometry": {"type": "polyline", "points": pts, "width_ft": check_width(width)},
            "notes": "Added with the Roads tab (road_edit.py).", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}}


# ------------------------------------------------------------------ operations (each returns a result dict; write only when not dry)
def op_delete(wdir, ids, dry=False):
    doc = load(wdir)
    streets = need_editable(doc, ids, "delete")
    for s in streets:
        if referenced_by_bridges(wdir, s["id"]):
            fail(f"{s['id']} is named in bridges.json; remove that bridge first (Bridges tab)")
    gone = {s["id"] for s in streets}
    doc["streets"] = [s for s in doc["streets"] if s["id"] not in gone]
    extra, refs = references(wdir, gone)
    bk = None if dry else save(wdir, doc, extra)
    return {"deleted": sorted(gone), "count": len(gone), "remaining": len(doc["streets"]), "references_removed": refs, "backup": bk, "dry": dry}


def op_add(wdir, name, kind, width, pts, wanted_id=None, simplify_ft=0.0, smooth_n=0, dry=False):
    doc = load(wdir)
    pts = clean_points(shape(clean_points(pts, bounds_of(wdir)), simplify_ft, smooth_n), bounds_of(wdir))
    s = make_street(doc, name, kind, width, pts, wanted_id)
    doc["streets"].append(s)
    bk = None if dry else save(wdir, doc)
    return {"added": [s["id"]], "count": 1, "points": len(pts), "length_ft": round(length(pts), 1), "backup": bk, "dry": dry}


def op_set_points(wdir, rid, pts=None, simplify_ft=0.0, smooth_n=0, dry=False):
    doc = load(wdir)
    s = need_editable(doc, [rid], "reshape")[0]
    if pts is None:
        if not simplify_ft and not smooth_n:
            fail("give --points / --points-file, or --simplify / --smooth to reshape the existing line")
        pts = s["geometry"]["points"]
    new = clean_points(shape(clean_points(pts, bounds_of(wdir), rid), simplify_ft, smooth_n), bounds_of(wdir), rid)
    old = s["geometry"]["points"]
    s["geometry"]["points"] = new
    drop_stale(s)
    bk = None if dry else save(wdir, doc)
    return {"changed": [rid], "count": 1, "points_before": len(old), "points_after": len(new), "length_ft": round(length(new), 1), "backup": bk, "dry": dry}


def op_split(wdir, rid, at, dry=False):
    doc = load(wdir)
    s = need_editable(doc, [rid], "split")[0]
    pts = s["geometry"]["points"]
    if not isinstance(at, int) or at < 1 or at > len(pts) - 2:
        fail(f"--at must be a vertex index 1..{len(pts) - 2} ({rid} has {len(pts)} points, indices from 0)")
    b = json.loads(json.dumps(s))
    s["geometry"]["points"], b["geometry"]["points"] = pts[:at + 1], pts[at:]
    b["id"] = _free(doc, rid)
    drop_stale(s)
    drop_stale(b)
    i = doc["streets"].index(s)
    doc["streets"].insert(i + 1, b)
    bk = None if dry else save(wdir, doc)
    return {"changed": [rid], "added": [b["id"]], "count": 2, "backup": bk, "dry": dry}


def _free(doc, rid):
    ids = set(by_id(doc))
    n = 2
    while f"{rid}_{n}" in ids:
        n += 1
    return f"{rid}_{n}"


def op_join(wdir, a_id, b_id, tol=25.0, dry=False):
    doc = load(wdir)
    if a_id == b_id:
        fail("join needs two different roads")
    a, b = need_editable(doc, [a_id, b_id], "join")
    if a.get("kind") != b.get("kind"):
        fail(f"cannot join a {a.get('kind')} to a {b.get('kind')}: set the same class first")
    pa, pb = a["geometry"]["points"], b["geometry"]["points"]
    best = None
    for ra in (False, True):
        for rb in (False, True):
            qa, qb = (pa[::-1] if ra else pa), (pb[::-1] if rb else pb)
            d = math.hypot(qa[-1][0] - qb[0][0], qa[-1][1] - qb[0][1])
            if best is None or d < best[0]:
                best = (d, qa, qb)
    d, qa, qb = best
    if d > tol:
        fail(f"the nearest ends of {a_id} and {b_id} are {d:.1f} ft apart (limit {tol:g}); move one end or raise --join-tol")
    pts = qa + (qb[1:] if d < 0.05 else qb)
    a["geometry"]["points"] = clean_points(pts, bounds_of(wdir), a_id)
    drop_stale(a)
    doc["streets"] = [s for s in doc["streets"] if s["id"] != b_id]
    extra, refs = references(wdir, [b_id])
    bk = None if dry else save(wdir, doc, extra)
    return {"changed": [a_id], "deleted": [b_id], "count": 1, "gap_ft": round(d, 1), "references_removed": refs, "backup": bk, "dry": dry}


def road_id_from_name(name, ids):
    """Illustrator item name -> street id ('_x5F_' decoded; suffixes such as _casing or ' 2' ignored). Longest matching id wins; None if no road."""
    n = str(name or "").replace("_x5F_", "_").strip()
    if n in ids:
        return n
    for i in sorted(ids, key=len, reverse=True):
        if n.startswith(i) and n[len(i):len(i) + 1] in ("_", " ", "-"):
            return i
    return None


def op_apply_paths(wdir, paths, mode="sync", kind="lane", width=14.0, name=None, simplify_ft=0.0, smooth_n=0, dry=False):
    """paths: [{name, points [[x,y]...] in feet, closed}]. mode reshape (every path must be an existing road), add (every path becomes a new road),
    sync (existing roads are reshaped, the rest are added). Everything is validated first; one backup; one write."""
    if mode not in ("reshape", "add", "sync"):
        fail("mode must be reshape, add or sync")
    if not isinstance(paths, list) or not paths:
        fail("no paths: select open paths in Illustrator (or draw them on the Road Centerlines layer)")
    doc = load(wdir)
    bnd = bounds_of(wdir)
    ids = set(by_id(doc))
    seen, plan = set(), []
    for k, p in enumerate(paths):
        nm = str(p.get("name") or "")
        if p.get("closed"):
            fail(f"{nm or 'path ' + str(k + 1)}: is a closed path. The Roads layer of the town drawing holds street outlines; edit the open centreline on the "
                 f"'{CENTERLINE_LAYER}' layer (button Redraw roads) or draw an open path")
        rid = road_id_from_name(nm, ids)
        if mode == "add" and rid:
            fail(f"{nm}: is already road {rid}; use Reshape, or rename the path")
        if mode == "reshape" and not rid:
            fail(f"{nm or 'path ' + str(k + 1)}: is not named like an existing road id (str_...)")
        if rid:
            if rid in seen:
                fail(f"road {rid} appears twice in the selection")
            seen.add(rid)
        plan.append((rid, nm, p.get("points")))
    if any(r for r, _n, _p in plan):
        need_editable(doc, [r for r, _n, _p in plan if r], "reshape")
    changed, added = [], []
    m = by_id(doc)
    n_new = sum(1 for r, _n, _p in plan if not r)
    for rid, nm, pts in plan:
        pts = clean_points(shape(clean_points(pts, bnd, nm or "path"), simplify_ft, smooth_n), bnd, nm or "path")
        if rid:
            m[rid]["geometry"]["points"] = pts
            drop_stale(m[rid])
            changed.append(rid)
        else:
            base = (name or nm or "New road").strip()
            if name and n_new > 1:
                base = f"{base} {len(added) + 1}"
            s = make_street(doc, base, kind, width, pts)
            doc["streets"].append(s)
            m[s["id"]] = s
            added.append(s["id"])
    bk = None if dry else save(wdir, doc)
    return {"changed": changed, "added": added, "count": len(changed) + len(added), "backup": bk, "dry": dry}


# ------------------------------------------------------------------ Illustrator drawing
def draw_svg(wdir, view, out_path, ids=None):
    """Centrelines of the editable roads as open paths on the layer 'Road Centerlines', in page points of `view` (the panelio.py `view` json:
    x0, y0, k points per foot, margin_in, page_in). Path names are the street ids. -> {path, roads}"""
    doc = load(wdir)
    k, m = float(view["k"]), float(view["margin_in"]) * 72.0
    x0, y0 = float(view["x0"]), float(view["y0"])
    pw, ph = float(view["page_in"][0]) * 72.0, float(view["page_in"][1]) * 72.0
    items, n = [], 0
    for s in doc.get("streets", []):
        if s.get("kind") == "bridge" or (ids and s["id"] not in ids):
            continue
        pts = [(m + (x - x0) * k, m + (y - y0) * k) for x, y in s["geometry"]["points"]]
        d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        items.append(f'    <path id="{s["id"]}" fill="none" stroke="#d6336c" stroke-width="1.5" d="{d}"/>')
        n += 1
    from lib_svg import _encode_ids
    svg = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/" '
           'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
           f'width="{pw:g}pt" height="{ph:g}pt" viewBox="0 0 {pw:g} {ph:g}">',
           f'  <g id="{CENTERLINE_LAYER}" inkscape:groupmode="layer" i:layer="yes" inkscape:label="{CENTERLINE_LAYER}">'] + items + ["  </g>", "</svg>"]
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(_encode_ids("\n".join(svg) + "\n"))
    return {"path": out_path, "roads": n, "layer": CENTERLINE_LAYER}
