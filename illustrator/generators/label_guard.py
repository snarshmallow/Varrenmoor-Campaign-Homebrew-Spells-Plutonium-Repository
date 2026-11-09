"""Label guard: keeps pathological label content out of the SVG render_world.py writes (Illustrator imports SVG with no
progress or cancel, so a broken label must be dropped or simplified here, not discovered as an Application Hang).

  recs, rep = label_guard.guard(recs, page_w, page_h, budget=600)
      - drops labels with NaN / inf / empty text / font size out of range, and labels whose centre is off the page
      - drops duplicated ids and exact duplicates (same layer, text, position): no doubled halo / backing shapes
      - rounds positions and sizes to 0.01 pt
      - curved baselines (rec.path): non-finite or off-page -> straight label; more than MAX_CURVE_POINTS -> Douglas-Peucker
      - label budget: at most `budget` labels in total; the cut goes Hidden, Elevation, Rooms, Buildings, Streets, Districts
        (hidden-by-scale labels first, district names last); a layer cap (`layer_cap`) applies on top of that
    rep: {"dropped": {reason: n}, "simplified": n, "kept": n, "budget": n, "cut": {layer: n}} ; warnings(rep) -> printable lines

  simplify(points, max_points) and path_points / points_path for 'M x,y L x,y ...' path data.
"""
import math
import re
from dataclasses import replace as _replace

DEFAULT_BUDGET = 600
HIDDEN_CAP = 250                 # labels hidden by scale (display:none layer) still become text frames in Illustrator
MAX_CURVE_POINTS = 40
FONT_MIN, FONT_MAX = 0.5, 400.0
# cut order for the budget: first entry loses labels first
CUT_ORDER = ["Labels - Hidden", "Labels - Elevation", "Labels - Rooms", "Labels - Buildings", "Labels - Streets", "Labels - Districts"]

_PT = re.compile(r"(-?[\d.]+(?:[eE][-+]?\d+)?|nan|inf|-inf),(-?[\d.]+(?:[eE][-+]?\d+)?|nan|inf|-inf)", re.I)


def finite(*xs):
    try:
        return all(math.isfinite(float(x)) for x in xs)
    except (TypeError, ValueError):
        return False


def path_points(d):
    return [(float(a), float(b)) for a, b in _PT.findall(d or "")]


def points_path(pts):
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts) if pts else ""


def _dp(pts, tol):
    if len(pts) < 3:
        return list(pts)
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        bx, by = pts[b]
        dx, dy = bx - ax, by - ay
        L = math.hypot(dx, dy)
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / L if L > 1e-12 else math.hypot(px - ax, py - ay)
            if d > best:
                best, bi = d, i
        if bi > 0 and best > tol:
            keep[bi] = True
            stack += [(a, bi), (bi, b)]
    return [p for p, k in zip(pts, keep) if k]


def simplify(pts, max_points=MAX_CURVE_POINTS, tol=0.05):
    """Douglas-Peucker with a growing tolerance until at most max_points remain (end points always kept)."""
    pts = list(pts)
    if len(pts) <= max_points:
        return pts
    out = _dp(pts, tol)
    while len(out) > max_points:
        tol *= 1.6
        out = _dp(pts, tol)
    return out


def _r(x):
    return round(float(x), 2)


def guard(recs, page_w, page_h, budget=DEFAULT_BUDGET, layer_cap=None, hidden_cap=HIDDEN_CAP):
    rep = {"dropped": {}, "simplified": 0, "straightened": 0, "kept": 0, "budget": budget, "cut": {}, "in": len(recs)}

    def drop(why):
        rep["dropped"][why] = rep["dropped"].get(why, 0) + 1

    out, seen_id, seen_key = [], set(), set()
    for r in recs:
        txt = " ".join(str(x) for x in (r.lines or [])).strip()
        if not txt:
            drop("empty text")
            continue
        if not finite(r.cx, r.cy, r.w, r.h, r.size) or (r.rot is not None and not finite(r.rot)):
            drop("NaN / inf")
            continue
        if not (FONT_MIN <= float(r.size) <= FONT_MAX):
            drop("font size")
            continue
        if not (0.0 <= r.cx <= page_w and 0.0 <= r.cy <= page_h):
            drop("off the page")
            continue
        if r.id in seen_id:
            drop("duplicate id")
            continue
        key = (r.layer, txt, round(r.cx, 1), round(r.cy, 1))
        if key in seen_key:
            drop("duplicate label")
            continue
        seen_id.add(r.id)
        seen_key.add(key)
        path = r.path or ""
        if path:
            pts = path_points(path)
            if len(pts) < 2 or not all(finite(x, y) for x, y in pts) or any(not (-page_w <= x <= 2 * page_w and -page_h <= y <= 2 * page_h) for x, y in pts) \
                    or re.search(r"nan|inf", path, re.I):
                path = ""
                rep["straightened"] += 1
            else:
                if len(pts) > MAX_CURVE_POINTS:
                    pts = simplify(pts, MAX_CURVE_POINTS)
                    rep["simplified"] += 1
                path = points_path(pts)
        out.append(_replace(r, cx=_r(r.cx), cy=_r(r.cy), w=_r(r.w), h=_r(r.h), rot=(_r(r.rot) if r.rot is not None else None), size=_r(r.size), path=path))
    # budget: cut from the least important layer first, keeping each layer's own order (placement priority)
    by_layer = {}
    for r in out:
        by_layer.setdefault(r.layer, []).append(r)
    caps = {}
    if hidden_cap is not None and len(by_layer.get("Labels - Hidden", [])) > hidden_cap:
        caps["Labels - Hidden"] = hidden_cap
    if layer_cap:
        for ly, rs in by_layer.items():
            if len(rs) > layer_cap:
                caps[ly] = min(caps.get(ly, layer_cap), layer_cap)
    total = sum(min(len(rs), caps.get(ly, len(rs))) for ly, rs in by_layer.items())
    if budget and total > budget:
        over = total - budget
        order = CUT_ORDER + [ly for ly in by_layer if ly not in CUT_ORDER]
        for ly in order:
            if over <= 0:
                break
            have = min(len(by_layer.get(ly, [])), caps.get(ly, len(by_layer.get(ly, []))))
            take = min(have, over)
            if take:
                caps[ly] = have - take
                over -= take
    keep_ids = set()
    for ly, rs in by_layer.items():
        n = caps.get(ly, len(rs))
        if n < len(rs):
            rep["cut"][ly] = len(rs) - n
        keep_ids.update(id(r) for r in rs[:n])
    final = [r for r in out if id(r) in keep_ids]
    rep["kept"] = len(final)
    return final, rep


def warnings(rep):
    out = []
    if rep["dropped"]:
        out.append("label guard: dropped " + ", ".join(f"{n} ({k})" for k, n in rep["dropped"].items()))
    if rep["straightened"]:
        out.append(f"label guard: {rep['straightened']} curved label(s) with a broken baseline set straight")
    if rep["simplified"]:
        out.append(f"label guard: {rep['simplified']} curved baseline(s) simplified to <= {MAX_CURVE_POINTS} points")
    if rep["cut"]:
        out.append(f"WARNING label budget {rep['budget']}: {rep['in']} labels, kept {rep['kept']}; cut " + ", ".join(f"{k} {n}" for k, n in rep["cut"].items())
                   + " (raise it with --label-budget N; 0 = no budget)")
    return out
