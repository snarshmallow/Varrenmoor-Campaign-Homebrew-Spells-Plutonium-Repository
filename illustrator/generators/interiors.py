"""House interior layout generator (rooms, partition walls, interior doors, stairs, windows, furniture, light hints).

Pure Python + shapely, deterministic from the entity id (seed = sha1("interior:" + id)). Everything is in world feet (x east, y south, same frame as
world/<place>/buildings/*.json); nothing here is canon: a layout is `generated: true, canon: false` until a human edits it.

  layout = generate_layout(building, doors)         # building: id, kind, floors, polygon (+ obb); doors: [{id, point, width_ft, facing}]
  apply_layout(building_json, layout)               # writes rooms / doors / layout into a world building JSON (dict)
  python illustrator/generators/interiors.py generate --place bridgehollow__dyers_walk_local [--only ID] [--force]
  python illustrator/generators/interiors.py plans --place P --out DIR        floor plan PNG/SVG per building + a street sheet (interiors_render.py)

Layout model (see illustrator/out/interiors_notes.md): the footprint's inner polygon (exterior wall 0.75 ft) is cut by a seeded binary partition into
cells in the building's oriented-bounding-box frame; each cell clipped to the footprint is a room. Upper storeys reuse the ground cells (walls stack).
The room holding the exterior door is the entry room (hall / common room / shop). One straight stair (steep 'cottage' stair, 16 risers of 7.5 in)
goes in a ground room, keeps clear of the door swing and has 2.5 ft free beside it for stepping on and off; its footprint is a hole in the upper slab.
Interior doors form a spanning tree over the rooms (plus a loop for big houses). Windows follow the exterior rule used by worldpack_detail.plan_holes
(about one per 8 ft of free wall per storey, 3 x 3.5 ft, sill 3.5 ft) minus those that would land on a partition end or behind the stair.
"""
import hashlib
import json
import math
import os
import random
import sys

from shapely.geometry import LineString, Point, Polygon
from shapely.geometry import box as sbox
from shapely.ops import unary_union

WALL_T = 0.75           # exterior wall thickness (matches worldpack_detail.WALL_T_FT)
PART_T = 0.40           # partition wall thickness
STOREY_H = 10.0         # floor to floor
SLAB_T = 0.6            # upper floor slab thickness
DOOR_W, DOOR_H = 3.0, 6.8
MIN_CELL = 6.0
STAIR_SPECS = ((9.0, 3.0, 16), (7.5, 2.8, 16), (5.0, 2.4, 16))     # (run ft, width ft, risers); riser = 10 ft / 16 = 7.5 in
WIN_W, WIN_H, WIN_SILL, WIN_SPACING, END_MARGIN = 3.0, 3.5, 3.5, 8.0, 1.5
SIDE_CLEAR = 2.5

KINDS = {   # kind -> (entry name, other room names in order of decreasing size (ground), upper room names, min rooms for area>=110)
    "house": ("Hall", ["Bedroom", "Kitchen", "Storeroom", "Pantry"], ["Bedroom", "Bedroom", "Study", "Closet"], 1),
    "cottage": ("Hall", ["Bedroom", "Kitchen", "Storeroom", "Pantry"], ["Bedroom", "Bedroom", "Closet"], 1),
    "inn": ("Common room", ["Kitchen", "Cellar stair", "Storeroom", "Parlour"], ["Guest room", "Guest room", "Guest room", "Guest room"], 3),
    "tavern": ("Common room", ["Kitchen", "Storeroom", "Parlour"], ["Guest room", "Guest room", "Guest room"], 3),
    "workshop": ("Shop floor", ["Back room", "Storeroom", "Office"], ["Loft", "Bedroom", "Storeroom"], 2),
    "shop": ("Shop floor", ["Back room", "Storeroom", "Office"], ["Bedroom", "Bedroom", "Storeroom"], 2),
    "mill": ("Mill floor", ["Storeroom", "Office"], ["Grain loft", "Storeroom"], 1),
    "barn": ("Barn floor", ["Tack room", "Stall"], ["Hayloft", "Hayloft"], 1),
    "stable": ("Stable floor", ["Tack room", "Stall"], ["Hayloft", "Hayloft"], 1),
    "civic": ("Hall", ["Office", "Archive", "Council room"], ["Office", "Archive", "Council room"], 3),
    "default": ("Hall", ["Bedroom", "Kitchen", "Storeroom", "Pantry"], ["Bedroom", "Bedroom", "Closet"], 1),
}
KIND_ALIAS = {"hall": "civic", "guildhall": "civic", "temple": "civic", "chapel": "civic", "manor": "house", "townhouse": "house", "tenement": "house"}


def seed_for(bid):
    return int(hashlib.sha1(("interior:" + str(bid)).encode()).hexdigest()[:12], 16)


def r2(v):
    return round(float(v), 3)


# ------------------------------------------------------------------ frame
class Frame:
    """World <-> local (oriented bounding box) frame; local u along the long axis, v across. Orientation preserving (det = +1)."""

    def __init__(self, b):
        pg = Polygon(b["polygon"]).buffer(0)
        o = b.get("obb")
        if o:
            self.c, self.a = tuple(o["center"]), math.radians(o["angle_deg"])
        else:
            r = pg.minimum_rotated_rectangle
            cs = list(r.exterior.coords)[:4]
            e = [(cs[(i + 1) % 4][0] - cs[i][0], cs[(i + 1) % 4][1] - cs[i][1]) for i in range(2)]
            d = e[0] if math.hypot(*e[0]) >= math.hypot(*e[1]) else e[1]
            self.c, self.a = (r.centroid.x, r.centroid.y), math.atan2(d[1], d[0])
        self.eu = (math.cos(self.a), math.sin(self.a))
        self.ev = (-self.eu[1], self.eu[0])

    def loc(self, p):
        dx, dy = p[0] - self.c[0], p[1] - self.c[1]
        return (dx * self.eu[0] + dy * self.eu[1], dx * self.ev[0] + dy * self.ev[1])

    def wld(self, q):
        return (self.c[0] + q[0] * self.eu[0] + q[1] * self.ev[0], self.c[1] + q[0] * self.eu[1] + q[1] * self.ev[1])

    def wld_poly(self, pts):
        return [[r2(x), r2(y)] for x, y in (self.wld(q) for q in pts)]


def _ring(g):
    if g.is_empty:
        return []
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda x: x.area)
    return list(g.exterior.coords)[:-1]


# ------------------------------------------------------------------ partition
def _target_rooms(kind, area, short):
    entry, others, upper, minr = KINDS[kind]
    n = 1 if area < 110 else 2 if area < 215 else 3 if area < 330 else 4
    if area >= 110:
        n = max(n, minr)
    if kind in ("barn", "stable", "mill"):
        n = min(n, 2 if area > 300 else 1)
    if area >= 430:
        n = max(n, 5 if kind in ("inn", "tavern", "civic") else n)
    return max(1, min(n, len(others) + 1))


def _split(cell, n, rng, door_l, cuts):
    u0, u1, v0, v1 = cell
    if n <= 1:
        return [cell]
    du, dv = u1 - u0, v1 - v0
    axis = 0 if du >= dv else 1
    lo, hi = (u0, u1) if axis == 0 else (v0, v1)
    if hi - lo < 2 * MIN_CELL:
        return [cell]
    n1 = n // 2 if n % 2 == 0 else (n // 2 if rng.random() < 0.5 else n - n // 2)
    frac = max(0.3, min(0.7, n1 / n + rng.uniform(-0.07, 0.07)))
    c = lo + frac * (hi - lo)
    if door_l is not None:                        # keep the cut off the exterior door (door at the cell edge across the cut)
        d_along = door_l[axis]
        d_perp = door_l[1 - axis]
        pl, ph = (v0, v1) if axis == 0 else (u0, u1)
        if min(abs(d_perp - pl), abs(d_perp - ph)) < 2.0 and abs(c - d_along) < DOOR_W / 2 + 1.6:
            for cand in (d_along + DOOR_W / 2 + 1.7, d_along - DOOR_W / 2 - 1.7):
                if lo + MIN_CELL <= cand <= hi - MIN_CELL:
                    c = cand
                    break
    c = max(lo + MIN_CELL, min(hi - MIN_CELL, c))
    a, b = ((u0, c, v0, v1), (c, u1, v0, v1)) if axis == 0 else ((u0, u1, v0, c), (u0, u1, c, v1))
    cuts.append((axis, c))
    return _split(a, n1, rng, door_l, cuts) + _split(b, n - n1, rng, door_l, cuts)


def _shared(a, b, F):
    """Shared wall segment (local coords) between two rect cells clipped to the footprint F, or None."""
    for ax in (0, 1):
        i0, i1 = (0, 1) if ax == 0 else (2, 3)          # cell as (u0,u1,v0,v1): axis 0 cuts at u
        j0, j1 = (2, 3) if ax == 0 else (0, 1)
        for ca, cb in ((a[i1], b[i0]), (b[i1], a[i0])):
            if abs(ca - cb) < 1e-6:
                lo, hi = max(a[j0], b[j0]), min(a[j1], b[j1])
                if hi - lo > 0.5:
                    seg = LineString([(ca, lo), (ca, hi)] if ax == 0 else [(lo, ca), (hi, ca)])
                    g = seg.intersection(F)
                    if g.is_empty or g.geom_type not in ("LineString", "MultiLineString"):
                        continue
                    if g.geom_type == "MultiLineString":
                        g = max(g.geoms, key=lambda x: x.length)
                    return g
    return None


# ------------------------------------------------------------------ stairs
def _place_stair(rooms_l, order, rng, door_pt, Fl, accept=None):
    """Find a stair rect (local frame). Returns dict or None. rooms_l: {idx: shapely poly (local)}."""
    door_zone = Point(door_pt).buffer(3.0) if door_pt else None
    for ri in order:
        R = rooms_l[ri]
        for run, w, risers in STAIR_SPECS:
            cands = []
            minx, miny, maxx, maxy = R.bounds
            for axis in (0, 1):
                for wall_side in (0, 1):
                    for rise_dir in (1, -1):
                        for inset in (0.0, 0.25, 0.6, 1.0, 1.5):
                            cands.append((axis, wall_side, rise_dir, inset))
            rng.shuffle(cands)
            cands.sort(key=lambda c: c[3])
            for axis, wall_side, rise_dir, inset in cands:
                # stair along `axis`, against the wall at the min (0) or max (1) side of the cross axis, flush with the start end
                for start_end in (0, 1):
                    if axis == 0:
                        x0 = minx + inset if start_end == 0 else maxx - inset - run
                        y0 = miny + inset if wall_side == 0 else maxy - inset - w
                        rect = sbox(x0, y0, x0 + run, y0 + w)
                        side = sbox(x0, y0 + w, x0 + run, y0 + w + SIDE_CLEAR) if wall_side == 0 else sbox(x0, y0 - SIDE_CLEAR, x0 + run, y0)
                        ext = sbox(x0, y0 - (1.0 if wall_side == 0 else 0), x0 + run, y0 + w + (1.0 if wall_side == 1 else 0))
                    else:
                        y0 = miny + inset if start_end == 0 else maxy - inset - run
                        x0 = minx + inset if wall_side == 0 else maxx - inset - w
                        rect = sbox(x0, y0, x0 + w, y0 + run)
                        side = sbox(x0 + w, y0, x0 + w + SIDE_CLEAR, y0 + run) if wall_side == 0 else sbox(x0 - SIDE_CLEAR, y0, x0, y0 + run)
                        ext = sbox(x0 - (1.0 if wall_side == 0 else 0), y0, x0 + w + (1.0 if wall_side == 1 else 0), y0 + run)
                    Rb = R.buffer(0.03)
                    if not (Rb.contains(rect) and Rb.contains(side)):
                        continue
                    if door_zone is not None and door_zone.intersects(rect):
                        continue
                    hole = unary_union([rect, ext.intersection(R)])      # hole touches the wall so the slab polygon has no inner ring
                    hole = hole.buffer(0)
                    if R.difference(hole).geom_type != "Polygon" or list(R.difference(hole).interiors):
                        continue
                    if accept is not None and not accept(hole):
                        continue
                    direction = (rise_dir, 0.0) if axis == 0 else (0.0, rise_dir)
                    return {"room": ri, "rect": rect, "hole": hole, "axis": axis, "dir": direction, "run": run, "width": w, "risers": risers,
                            "open_side": side}
    return None


# ------------------------------------------------------------------ furniture
FURN = {   # type: (size x along wall, size y out from wall, height ft, material)
    "hearth": (4.5, 1.8, 3.2, "mat_hearth_stone"), "table": (4.5, 2.6, 2.5, "mat_furn_wood"), "bench": (4.0, 1.0, 1.5, "mat_furn_wood"),
    "shelf": (3.6, 0.9, 6.0, "mat_furn_wood"), "bed": (3.8, 6.6, 2.0, "mat_fabric"), "chest": (3.0, 1.6, 1.8, "mat_furn_wood"),
    "barrel": (1.8, 1.8, 2.8, "mat_furn_wood"), "crate": (2.0, 2.0, 2.0, "mat_furn_wood"), "counter": (6.0, 2.0, 3.2, "mat_furn_wood"),
    "workbench": (5.0, 2.4, 3.0, "mat_furn_wood"), "hay": (3.0, 2.0, 2.2, "mat_straw"), "desk": (4.0, 2.2, 2.6, "mat_furn_wood"),
}
PLANS = {   # room use -> list of (type, mode) mode: wall | free | wall_ext (prefer exterior wall)
    "hall": [("hearth", "wall_ext"), ("table", "free"), ("bench", "table"), ("bench", "table"), ("shelf", "wall"), ("barrel", "wall"), ("chest", "wall")],
    "kitchen": [("hearth", "wall_ext"), ("table", "free"), ("shelf", "wall"), ("shelf", "wall"), ("barrel", "wall"), ("crate", "wall")],
    "bedroom": [("bed", "wall"), ("bed", "wall2"), ("chest", "wall"), ("shelf", "wall")],
    "storeroom": [("crate", "wall"), ("crate", "wall"), ("barrel", "wall"), ("barrel", "wall"), ("shelf", "wall"), ("crate", "wall")],
    "shop": [("counter", "free"), ("shelf", "wall"), ("shelf", "wall"), ("crate", "wall"), ("workbench", "wall"), ("barrel", "wall")],
    "common": [("hearth", "wall_ext"), ("table", "free"), ("bench", "table"), ("bench", "table"), ("counter", "wall"), ("barrel", "wall"), ("barrel", "wall")],
    "office": [("desk", "wall"), ("shelf", "wall"), ("chest", "wall")],
    "loft": [("hay", "wall"), ("crate", "wall"), ("barrel", "wall"), ("chest", "wall")],
    "landing": [("chest", "wall"), ("shelf", "wall")],
    "none": [],
}
USE = {"Hall": "hall", "Common room": "common", "Kitchen": "kitchen", "Bedroom": "bedroom", "Guest room": "bedroom", "Storeroom": "storeroom", "Pantry": "storeroom",
       "Closet": "storeroom", "Shop floor": "shop", "Back room": "storeroom", "Office": "office", "Study": "office", "Archive": "storeroom", "Council room": "hall",
       "Parlour": "hall", "Loft": "loft", "Grain loft": "loft", "Hayloft": "loft", "Mill floor": "shop", "Barn floor": "loft", "Stable floor": "loft",
       "Tack room": "storeroom", "Stall": "loft", "Cellar stair": "storeroom", "Landing": "landing", "Upper hall": "landing"}


def _fixture_poly(cx, cy, sx, sy, ang):
    c, s = math.cos(ang), math.sin(ang)
    pts = [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]
    return Polygon([(cx + x * c - y * s, cy + x * s + y * c) for x, y in pts])


def _furnish(R, use, rng, keepouts, F_ext, tall_keep=None):
    """-> [{type, centre(local), size, angle (local rad), poly}]; R local room polygon."""
    items, placed = [], []
    plan = PLANS.get(use, [])
    ring = list(R.exterior.coords)
    edges = []
    for i in range(len(ring) - 1):
        p, q = ring[i], ring[i + 1]
        L = math.dist(p, q)
        if L < 1.5:
            continue
        d = ((q[0] - p[0]) / L, (q[1] - p[1]) / L)
        n = (-d[1], d[0])                                       # R is CCW (positive area) so this points inward
        mid = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
        ext = F_ext.distance(Point(mid)) < 0.35
        edges.append({"p": p, "d": d, "n": n, "L": L, "ext": ext})
    clear = unary_union(keepouts) if keepouts else None
    wall_used = 0
    last_table = None
    table_poly = None
    for typ, mode in plan:
        sx, sy, hz, mat = FURN[typ]
        ok = None
        for attempt in range(60):
            if mode in ("wall", "wall_ext", "wall2"):
                pool = [e for e in edges if e["ext"]] if (mode == "wall_ext" and attempt < 40) else edges
                if not pool:
                    continue
                e = rng.choices(pool, weights=[x["L"] for x in pool])[0]
                if typ == "bed":
                    wx, wy = sx, sy                                 # bed: short (head) side against the wall
                else:
                    wx, wy = sx, sy
                if e["L"] < wx + 0.4:
                    continue
                t = rng.uniform(wx / 2 + 0.2, e["L"] - wx / 2 - 0.2)
                cx = e["p"][0] + e["d"][0] * t + e["n"][0] * (wy / 2 + 0.05)
                cy = e["p"][1] + e["d"][1] * t + e["n"][1] * (wy / 2 + 0.05)
                ang = math.atan2(e["d"][1], e["d"][0])
            elif mode == "table" and last_table is not None:
                tc, ta, tsx, tsy = last_table
                side = 1 if len(items) % 2 == 0 else -1
                off = tsy / 2 + sy / 2 + 0.25
                cx = tc[0] - math.sin(ta) * off * side
                cy = tc[1] + math.cos(ta) * off * side
                ang = ta
                wx, wy = sx, sy
            else:
                c = R.centroid
                cx, cy = c.x + rng.uniform(-1.5, 1.5), c.y + rng.uniform(-1.0, 1.0)
                ang = rng.choice([0.0, math.pi / 2])
                wx, wy = sx, sy
            poly = _fixture_poly(cx, cy, wx, wy, ang)
            if not R.buffer(0.02).contains(poly):
                continue
            if clear is not None and clear.intersects(poly):
                continue
            if tall_keep is not None and typ in ("hearth", "shelf") and tall_keep.intersects(poly):
                continue
            if any(p is not table_poly and p.buffer(0.3).intersects(poly) for p in placed):
                continue
            if mode != "table" and table_poly is not None and table_poly.buffer(0.3).intersects(poly):
                continue
            ok = (cx, cy, ang, wx, wy, poly)
            break
        if ok is None:
            continue
        cx, cy, ang, wx, wy, poly = ok
        placed.append(poly)
        if typ in ("table", "counter") and mode == "free":
            last_table = ((cx, cy), ang, wx, wy)
            table_poly = poly
        items.append({"type": typ, "centre": (cx, cy), "size": (wx, wy, hz), "angle": ang, "mat": mat, "poly": poly})
    return items


# ------------------------------------------------------------------ main generator
def _edge_windows(poly_w, doors_w, blocked_pts, stair_poly_w):
    """Exterior windows per storey-independent position: [(edge idx, point_w, u_ft, edge angle, outward normal)] following worldpack_detail.plan_holes."""
    n = len(poly_w)
    area2 = sum(poly_w[i][0] * poly_w[(i + 1) % n][1] - poly_w[(i + 1) % n][0] * poly_w[i][1] for i in range(n))
    pts = list(poly_w) if area2 > 0 else list(reversed(poly_w))      # CCW in the y-down frame (interior on the left in the y-up view is irrelevant here)
    out = []
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        L = math.dist(a, b)
        if L < 1e-6:
            continue
        d = ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        nrm = (d[1], -d[0])                                          # outward for this winding
        holes = []
        for dp, dw in doors_w:
            u = (dp[0] - a[0]) * d[0] + (dp[1] - a[1]) * d[1]
            v = -(dp[0] - a[0]) * d[1] + (dp[1] - a[1]) * d[0]
            if -0.2 <= u <= L + 0.2 and abs(v) < 0.6:
                dw = min(dw, 6.0)
                u = min(max(u, dw / 2 + END_MARGIN), L - dw / 2 - END_MARGIN)
                holes.append((u - dw / 2, u + dw / 2))
        free = [(END_MARGIN, L - END_MARGIN)]
        for h0, h1 in sorted(holes):
            nf = []
            for lo, hi in free:
                for seg in ((lo, min(hi, h0 - END_MARGIN)), (max(lo, h1 + END_MARGIN), hi)):
                    if seg[1] - seg[0] > 0:
                        nf.append(seg)
            free = nf
        for lo, hi in free:
            span = hi - lo
            cnt = int(span / WIN_SPACING)
            used = []
            for k in range(cnt):
                uc0 = lo + span * (k + 0.5) / cnt
                # keep the window by sliding it along the free wall until it clears partition ends / the stair (instead of dropping it)
                for off in (0.0, 0.5, -0.5, 1.0, -1.0, 1.5, -1.5, 2.0, -2.0, 2.5, -2.5, 3.0, -3.0, 4.0, -4.0):
                    uc = uc0 + off
                    if uc - WIN_W / 2 < lo or uc + WIN_W / 2 > hi or any(abs(uc - q) < WIN_W + 0.6 for q in used):
                        continue
                    p = (a[0] + d[0] * uc, a[1] + d[1] * uc)
                    if any(math.dist(p, q) < WIN_W / 2 + PART_T / 2 + 0.7 for q in blocked_pts):
                        continue
                    if stair_poly_w is not None and stair_poly_w.distance(Point(p)) < WIN_W / 2 + 0.2 + WALL_T:
                        continue
                    used.append(uc)
                    out.append((i, p, uc, math.degrees(math.atan2(d[1], d[0])), nrm))
                    break
    return out


def _pick_door(g, rng, keep, relax=False):
    """Door position on the shared wall segment g (local coords) clear of the `keep` polygon -> (point, t, width) or None."""
    L = g.length
    w = min(DOOR_W, max(2.2, L - 0.9))
    margin = w / 2 + 0.45
    a, c = g.coords[0], g.coords[-1]
    offs = [0.0]
    for k in range(1, 12):
        offs += [k * 0.7, -k * 0.7]
    jit = rng.uniform(-0.12, 0.12) * L
    for off in offs:
        t = L / 2 + jit + off
        if t < margin - 1e-6 or t > L - margin + 1e-6:
            continue
        pt = (a[0] + (c[0] - a[0]) * t / L, a[1] + (c[1] - a[1]) * t / L)
        if keep is not None and Point(pt).buffer(w / 2 + 0.3).intersects(keep):
            continue
        return (pt, t, w)
    if relax:
        t = min(max(L / 2, margin), max(margin, L - margin))
        return ((a[0] + (c[0] - a[0]) * t / L, a[1] + (c[1] - a[1]) * t / L), t, w)
    return None


def generate_layout(b, doors=None, kind=None):
    """Layout dict for one building (see module doc). Raises ValueError when the footprint is too small to hold a room."""
    bid = b["id"]
    kind = kind or b.get("kind") or "house"
    kind = KIND_ALIAS.get(kind, kind)
    if kind not in KINDS:
        kind = "default"
    floors = max(1, int(b.get("floors", 1)))
    rng = random.Random(seed_for(bid))
    fr = Frame(b)
    outer = Polygon([fr.loc(p) for p in b["polygon"]]).buffer(0)
    F = outer.buffer(-WALL_T, join_style=2, mitre_limit=5.0)
    if F.is_empty or F.area < 25:
        raise ValueError(f"{bid}: footprint too small for rooms")
    if F.geom_type == "MultiPolygon":
        F = max(F.geoms, key=lambda x: x.area)
    doors = list(doors or [])
    door_l = [(fr.loc(d["point"]), d) for d in doors]
    entry_door = door_l[0] if door_l else None
    u0, v0, u1, v1 = F.bounds
    entry_name, others, upper_names, _ = KINDS[kind]
    n_rooms = _target_rooms(kind, F.area, min(u1 - u0, v1 - v0))
    cuts = []
    cells = _split((u0, u1, v0, v1), n_rooms, rng, entry_door[0] if entry_door else None, cuts)
    # rooms (ground) = cell ∩ F
    cell_poly = []
    for c in cells:
        g = sbox(c[0], c[2], c[1], c[3]).intersection(F)
        if g.geom_type != "Polygon":
            g = max([x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon"], key=lambda x: x.area, default=Polygon())
        cell_poly.append(g)
    keep = [i for i, g in enumerate(cell_poly) if g.area >= 20]
    cells = [cells[i] for i in keep]
    cell_poly = [cell_poly[i] for i in keep]
    if not cells:
        raise ValueError(f"{bid}: no usable room cells")
    nc = len(cells)
    # entry room
    if entry_door:
        entry = min(range(nc), key=lambda i: cell_poly[i].distance(Point(entry_door[0])))
    else:
        entry = max(range(nc), key=lambda i: cell_poly[i].area)
    order_big = sorted((i for i in range(nc) if i != entry), key=lambda i: -cell_poly[i].area)
    # names
    names = {entry: entry_name}
    for k, i in enumerate(order_big):
        names[i] = others[min(k, len(others) - 1)]
        if k >= len(others):
            names[i] = others[-1]
    if floors == 1 and nc >= 2 and "Bedroom" not in names.values() and kind in ("house", "cottage", "default"):
        names[order_big[0]] = "Bedroom"
    # adjacency + interior doors
    adj = {}
    for i in range(nc):
        for j in range(i + 1, nc):
            g = _shared(cells[i], cells[j], F)
            if g is not None and g.length > 0.5:
                adj[(i, j)] = g
    # spanning tree from entry, preferring long segments
    connected, tree = {entry}, []
    while len(connected) < nc:
        best = None
        for (i, j), g in adj.items():
            if (i in connected) != (j in connected):
                if best is None or g.length > best[0]:
                    best = (g.length, (i, j))
        if best is None:
            raise ValueError(f"{bid}: rooms not connected")
        i, j = best[1]
        tree.append((i, j))
        connected |= {i, j}
    extra = [k for k, g in sorted(adj.items(), key=lambda kv: -kv[1].length) if k not in tree and g.length >= 6.5][:1 if nc >= 4 else 0]
    door_pairs = tree + extra
    # stair (storeys > 1)
    stairs = []
    stair = None
    if floors > 1:
        order = [entry] + order_big
        door_in = None
        if entry_door:
            dpt = entry_door[0]
            ctr = F.centroid
            vec = (ctr.x - dpt[0], ctr.y - dpt[1])
            L = math.hypot(*vec) or 1.0
            door_in = (dpt[0] + vec[0] / L * 1.0, dpt[1] + vec[1] / L * 1.0)
        def _accept(hole):
            keep = hole.buffer(0.6)
            return all(_pick_door(adj[p], random.Random(1), keep) is not None for p in door_pairs)
        stair = _place_stair({i: cell_poly[i] for i in range(nc)}, order, rng, door_in, F, _accept)
        if stair is None:
            raise ValueError(f"{bid}: no stair fits")
    ext_door_zone = None
    int_doors = []                      # {pair, point(local), width, axis('u' or 'v' wall), seg}
    for (i, j) in door_pairs:
        g = adj[(i, j)]
        pick = _pick_door(g, rng, stair["hole"].buffer(0.6) if stair else None, relax=True)
        a, c = g.coords[0], g.coords[-1]
        vertical = abs(a[0] - c[0]) < 1e-6          # wall runs along v (cut at constant u)
        int_doors.append({"pair": (i, j), "pt": pick[0], "w": pick[2], "vertical": vertical, "seg": (a, c)})
    # windows (exterior), consistent with worldpack_detail.plan_holes, minus partition ends and the stair
    blocked = []
    for g in adj.values():
        for p in (g.coords[0], g.coords[-1]):
            blocked.append(fr.wld(p))
    stair_w = Polygon([fr.wld(p) for p in stair["hole"].exterior.coords]) if stair else None
    poly_w = [tuple(p) for p in b["polygon"]]
    ext_doors_w = [(tuple(d["point"]), float(d.get("width_ft") or 3.5)) for d in doors]
    win_base = _edge_windows(poly_w, ext_doors_w, blocked, stair_w)
    # ---- assemble per storey
    rooms, door_out, walls, windows, fixtures, lights = [], [], [], [], [], []
    room_ids = {}
    for s in range(floors):
        for i in range(nc):
            if s == 0:
                nm = names[i]
            else:
                if stair and i == stair["room"]:
                    nm = "Upper hall" if nc > 1 or floors > 1 else "Loft"
                    nm = "Landing" if nc > 1 else "Loft bedroom"
                else:
                    k = [x for x in range(nc) if not (stair and x == stair["room"])].index(i)
                    nm = upper_names[min(k, len(upper_names) - 1)]
            rid = f"{bid}_r{s}_{i + 1}"
            room_ids[(s, i)] = rid
            poly = cell_poly[i]
            rings = _ring(poly)
            rooms.append({"id": rid, "name": nm, "floor": s, "polygon": fr.wld_poly(rings), "area_ft2": r2(poly.area), "use": USE.get(nm, "none"), "doors": [],
                          "entry": bool(s == 0 and i == entry), "stair": bool(stair and i == stair["room"])})
    rooms_by_id = {r["id"]: r for r in rooms}
    # exterior door
    ext_ids = []
    for d in doors:
        did = d.get("id") or f"{bid}_door1"
        pl = fr.loc(d["point"])
        ri = min(range(nc), key=lambda i: cell_poly[i].distance(Point(pl)))
        door_out.append({"id": did, "kind": "exterior", "floor": 0, "point": [r2(d["point"][0]), r2(d["point"][1])], "width_ft": float(d.get("width_ft") or 3.5),
                         "height_ft": 7.0, "rooms": [room_ids[(0, ri)], None], "facing": d.get("facing")})
        rooms_by_id[room_ids[(0, ri)]]["doors"].append(did)
        ext_ids.append(did)
    wall_serial = 0
    for s in range(floors):
        for k, (i, j) in enumerate(sorted(adj)):
            g = adj[(i, j)]
            a, c = g.coords[0], g.coords[-1]
            wid = f"{bid}_w{s}_{wall_serial}"
            wall_serial += 1
            wd = {"id": wid, "floor": s, "a": [r2(v) for v in fr.wld(a)], "b": [r2(v) for v in fr.wld(c)], "thickness_ft": PART_T, "rooms": [room_ids[(s, i)], room_ids[(s, j)]], "doors": []}
            for n_, idr in enumerate(int_doors):
                if idr["pair"] == (i, j):
                    did = f"{bid}_idoor_f{s}_{n_ + 1}"
                    pt = fr.wld(idr["pt"])
                    door_out.append({"id": did, "kind": "interior", "floor": s, "point": [r2(pt[0]), r2(pt[1])], "width_ft": r2(idr["w"]), "height_ft": DOOR_H,
                                     "rooms": [room_ids[(s, i)], room_ids[(s, j)]], "wall": wid})
                    wd["doors"].append(did)
                    rooms_by_id[room_ids[(s, i)]]["doors"].append(did)
                    rooms_by_id[room_ids[(s, j)]]["doors"].append(did)
            walls.append(wd)
    # stairs
    if stair:
        for s in range(floors - 1):
            rect = stair["rect"]
            dx, dy = stair["dir"]
            minx, miny, maxx, maxy = rect.bounds
            if stair["axis"] == 0:
                start = (minx if dx > 0 else maxx, (miny + maxy) / 2)
                end = (maxx if dx > 0 else minx, (miny + maxy) / 2)
            else:
                start = ((minx + maxx) / 2, miny if dy > 0 else maxy)
                end = ((minx + maxx) / 2, maxy if dy > 0 else miny)
            stairs.append({"id": f"{bid}_stair{s}", "from_floor": s, "to_floor": s + 1, "polygon": fr.wld_poly(list(rect.exterior.coords)[:-1]),
                           "hole": fr.wld_poly(_ring(stair["hole"])), "start": [r2(v) for v in fr.wld(start)], "end": [r2(v) for v in fr.wld(end)],
                           "run_ft": stair["run"], "width_ft": stair["width"], "risers": stair["risers"], "rise_ft": STOREY_H,
                           "room_lower": room_ids[(s, stair["room"])], "room_upper": room_ids[(s + 1, stair["room"])], "type": "straight"})
    # windows
    for s in range(floors):
        for k, (ei, p, uc, eang, nrm) in enumerate(win_base):
            pl = fr.loc(p)
            ri = min(range(nc), key=lambda i: cell_poly[i].distance(Point(pl)))
            windows.append({"id": f"{bid}_win{s}_{k + 1}", "floor": s, "room": room_ids[(s, ri)], "point": [r2(p[0]), r2(p[1])], "edge": ei, "u_ft": r2(uc),
                            "width_ft": WIN_W, "height_ft": WIN_H, "sill_ft": WIN_SILL + 0.0, "angle_deg": r2(eang), "outward": [r2(nrm[0]), r2(nrm[1])]})
    # furniture + light hints
    F_ext = outer.buffer(-WALL_T).exterior if not outer.buffer(-WALL_T).is_empty else F.exterior
    door_keep = []
    for d in door_out:
        pl = fr.loc(d["point"])
        door_keep.append((d["floor"], Point(pl).buffer(3.0)))
    tower_keep = None                      # stave-church style: the tower's corner posts and open bay stand in the middle of the nave (see building_styles_geo.tiers)
    try:
        import building_styles as _bs
        if b.get("style") and (_bs.load_presets().get(b["style"]) or {}).get("special", {}).get("tiers") and b.get("obb"):
            o = b["obb"]
            hh = min(o["length_ft"], o["width_ft"]) * 0.62 / 2 + 1.0
            c = fr.loc(o["center"])
            tower_keep = sbox(c[0] - hh, c[1] - hh, c[0] + hh, c[1] + hh)
    except Exception:
        tower_keep = None
    for s in range(floors):
        for i in range(nc):
            rid = room_ids[(s, i)]
            r = rooms_by_id[rid]
            R = cell_poly[i]
            if R.exterior.is_ccw is False:
                R = Polygon(list(R.exterior.coords)[::-1])
            keep = [g for f, g in door_keep if f == s]
            if tower_keep is not None and s == 0:
                keep.append(tower_keep)
            if stair:
                keep.append(stair["hole"].buffer(0.4))
                keep.append(stair["open_side"].buffer(0.0))
            wk = [Point(fr.loc(w["point"])).buffer(WIN_W / 2 + 0.6) for w in windows if w["floor"] == s]
            items = _furnish(R, r["use"], rng, keep, F_ext, unary_union(wk) if wk else None)
            for k, it in enumerate(items):
                wc = fr.wld(it["centre"])
                fixtures.append({"id": f"{bid}_fx{s}_{i + 1}_{k + 1}", "type": it["type"], "floor": s, "room": rid, "point": [r2(wc[0]), r2(wc[1])],
                                 "size_ft": [r2(it["size"][0]), r2(it["size"][1]), r2(it["size"][2])], "angle_deg": r2(math.degrees(it["angle"] + fr.a) % 360.0),
                                 "material": it["mat"]})
                if it["type"] == "hearth":
                    lights.append({"id": f"{bid}_light_hearth{s}_{i + 1}", "type": "hearth", "floor": s, "room": rid, "point": [r2(wc[0]), r2(wc[1])], "z_ft": 2.0,
                                   "color": "#ff9a3c", "bright_ft": 8, "dim_ft": 18, "intensity": 0.8, "animation": "torch"})
    wl_by_room = {}
    for w in windows:
        wl_by_room.setdefault((w["floor"], w["room"]), []).append(w)
    for (s, rid), ws in sorted(wl_by_room.items()):
        w = ws[0]
        lights.append({"id": f"{w['id']}_light", "type": "window", "floor": s, "room": rid,
                       "point": [r2(w["point"][0] - w["outward"][0] * 2.0), r2(w["point"][1] - w["outward"][1] * 2.0)], "z_ft": s * STOREY_H + WIN_SILL + WIN_H / 2,
                       "color": "#dfeaff", "bright_ft": 3, "dim_ft": 10, "intensity": 0.3, "animation": "none"})
    return {"version": 1, "generated": True, "canon": False, "seed": seed_for(bid), "kind": kind, "floors": floors, "storey_ft": STOREY_H, "slab_ft": SLAB_T,
            "exterior_wall_ft": WALL_T, "partition_ft": PART_T, "entry_room": room_ids[(0, entry)], "rooms": rooms, "doors": door_out, "walls": walls, "stairs": stairs,
            "windows": windows, "fixtures": fixtures, "lights": lights}


def apply_layout(bjson, layout):
    """Store a layout in a world building JSON dict: rooms/doors arrays (existing fields) + `layout` (walls, stairs, windows, fixtures, lights)."""
    bjson["rooms"] = layout["rooms"]
    bjson["doors"] = layout["doors"]
    bjson["layout"] = {k: v for k, v in layout.items() if k not in ("rooms", "doors")}
    return bjson


def attach_to_entity(e, b, region_doors):
    """World pack hook: put the building's layout (stored in its JSON, else generated on the fly for buildings that have exterior doors) on the pack entity `e`."""
    if b.get("layout") and b.get("rooms"):
        lay = dict(b["layout"], rooms=b["rooms"], doors=b.get("doors", []))
    else:
        try:
            lay = generate_layout({"id": e["id"], "kind": e.get("kind"), "floors": e.get("floors", 1), "polygon": e["polygon"], "obb": e.get("obb")}, region_doors)
        except ValueError:
            return None
    e["rooms"], e["doors"] = lay["rooms"], lay["doors"]
    e["layout"] = {k: v for k, v in lay.items() if k not in ("rooms", "doors")}
    e["interior"]["room_ids"] = [r["id"] for r in lay["rooms"]]
    e["interior"]["door_ids"] = [d["id"] for d in lay["doors"]]
    e["derived"].append("layout")
    return lay


def building_for_layout(bjson, region_doors=None):
    """World building JSON (geometry.points) -> the dict generate_layout wants."""
    pts = (bjson.get("geometry") or {}).get("points") or bjson.get("polygon")
    return {"id": bjson["id"], "kind": bjson.get("kind"), "floors": bjson.get("floors", 1), "polygon": pts}


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def generate_place(place, world_root=None, only=None, force=False, log=print):
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    root = os.path.join(world_root or os.path.join(repo, "world"), place)
    dp = os.path.join(root, "details.json")
    dets = _jload(dp).get("doors", []) if os.path.exists(dp) else []
    bd = os.path.join(root, "buildings")
    n = skipped = 0
    for f in sorted(os.listdir(bd)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(bd, f)
        bj = _jload(p)
        if only and bj["id"] not in only:
            continue
        if bj.get("layout") and not force:
            skipped += 1
            continue
        if bj.get("rooms") and not bj.get("layout", {}).get("generated", True) and not force:
            skipped += 1                                               # hand-authored rooms: never overwritten without --force
            continue
        b = building_for_layout(bj)
        try:
            lay = generate_layout(b, [d for d in dets if d.get("building") == bj["id"]])
        except ValueError as ex:
            log(f"skip {ex}")
            continue
        apply_layout(bj, lay)
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(bj, fh, indent=1, ensure_ascii=False)
            fh.write("\n")
        n += 1
    log(f"interiors: {n} layouts written, {skipped} kept ({place})")
    return n


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--place", required=True)
    g.add_argument("--world-root")
    g.add_argument("--only", nargs="*")
    g.add_argument("--force", action="store_true")
    pl = sub.add_parser("plans")
    pl.add_argument("--place", required=True)
    pl.add_argument("--world-root")
    pl.add_argument("--out", required=True)
    pl.add_argument("--px-per-ft", type=float, default=20.0)
    a = ap.parse_args()
    if a.cmd == "generate":
        generate_place(a.place, a.world_root, a.only, a.force)
    else:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import interiors_render as ir
        ir.render_place(a.place, a.out, a.world_root, a.px_per_ft)
