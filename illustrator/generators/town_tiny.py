"""Tiny settlements (fewer than 20 people) for place_create.py: a lone farmstead, a hunter's cabin / lodge, a roadside inn, a homestead / hamlet cluster.

town_gen.py is built for towns (rings, districts, plazas, lots); below ~20 people it has nothing sensible to work with, so place_create routes small
populations here. This writes the same files town_gen writes (streets.json, districts.json, buildings/*.json, town_gen_report.json) in the same formats,
so every other tool (render_world, shading, fills, worldpack export, foundry_push) treats the result like any generated place:

  track    one lane (kind "lane", 10 ft; a cabin path is 7 ft) from the map edge to the yard; a roadside inn sits on a road (kind "road", 16 ft) that crosses
           the whole map. A track that crosses a river becomes a ford in the 3D pack (worldpack does that for every non-bridge street).
  yard     a small square (kind "square") in front of the buildings (worldpack paves it like a plaza)
  buildings farmhouse / house / cabin / inn + barn, shed, stable and a well (a 7 ft well house), placed round the yard, off water and steep ground
  fields   fenced paddocks (district kind "field"; worldpack fences every field)
  district one district round the steading (ring "core") so labels and district tools have something to name

No market, plaza, walls or gates. Deterministic: same inputs + seed = same output.

kinds (spec town.settlement; "auto" picks from the population):
  farmstead  1-5 people   farmhouse, barn, shed (3+ people), well, yard, 2-3 fields
  cabin      1-3 people   a hunter's / woodcutter's cabin and a woodshed on a footpath, no fields
  lodge      1-8 people   a hunter's lodge: lodge house, stable, woodshed, a small yard
  inn        2-19 people  roadside inn, stable, shed, well, yard, on a through road
  hamlet     6-19 people  2-4 houses and 1-2 barns along a lane round a yard with a well, 3-4 fields (2-6 buildings)
"""
import json
import math
import os
import random

import numpy as np

KINDS = ("auto", "farmstead", "cabin", "lodge", "inn", "hamlet")


def pick_kind(pop, kind="auto"):
    if kind and kind != "auto":
        return kind
    return "farmstead" if pop <= 5 else "hamlet"


def default_size(pop, kind):
    """Small default place size (ft) for a tiny settlement; both sides multiples of 50 so a 10 ft heightmap cell divides them."""
    k = pick_kind(pop, kind)
    if pop <= 0:
        return [600, 400]
    return {"cabin": [400, 300], "lodge": [500, 400], "farmstead": [600, 450], "inn": [600, 450], "hamlet": [800, 600]}.get(k, [600, 450])


def _rect(c, u, v, L, D):
    """Rectangle centred at c, length L along unit u, depth D along unit v -> 4 points."""
    cx, cy = c
    hl, hd = L / 2.0, D / 2.0
    return [[round(cx + u[0] * a + v[0] * b, 1), round(cy + u[1] * a + v[1] * b, 1)] for a, b in ((-hl, -hd), (hl, -hd), (hl, hd), (-hl, hd))]


class _Site:
    def __init__(self, h, cell, W, H, water_mask, sea):
        self.h, self.cell, self.W, self.H, self.wm, self.sea = h, cell, W, H, water_mask, sea

    def z(self, x, y):
        h, c = self.h, self.cell
        j = min(max(int(round(x / c)), 0), h.shape[1] - 1)
        i = min(max(int(round(y / c)), 0), h.shape[0] - 1)
        return float(h[i, j])

    def wet(self, x, y):
        if self.z(x, y) <= self.sea + 1:
            return True
        if self.wm is None:
            return False
        c = self.cell
        j = min(max(int(round(x / c)), 0), self.wm.shape[1] - 1)
        i = min(max(int(round(y / c)), 0), self.wm.shape[0] - 1)
        return bool(self.wm[i, j])

    def samples(self, pts, step=None):
        from shapely.geometry import Point, Polygon
        pg = Polygon(pts)
        step = step or max(self.cell / 2.0, 3.0)
        x0, y0, x1, y1 = pg.bounds
        out = []
        for x in np.arange(x0, x1 + step, step):
            for y in np.arange(y0, y1 + step, step):
                if pg.contains(Point(x, y)):
                    out.append((x, y))
        return out or [tuple(pg.centroid.coords[0])]

    def fits(self, pts, margin=8.0, max_relief=9.0):
        if any(p[0] < margin or p[1] < margin or p[0] > self.W - margin or p[1] > self.H - margin for p in pts):
            return False
        s = self.samples(pts)
        if any(self.wet(x, y) for x, y in s):
            return False
        zz = [self.z(x, y) for x, y in s]
        return (max(zz) - min(zz)) <= max_relief


def _elev(site, pts):
    s = site.samples(pts)
    zz = [site.z(x, y) for x, y in s]
    return round(float(np.median(zz)), 1), round(float(max(zz) - min(zz)), 1)


def generate(pdir, spec, h, cell, sea, water_mask, centre, entry, names=None):
    """Write the tiny settlement into pdir. -> report dict (counts, kind, warnings)."""
    from shapely.geometry import LineString, Polygon
    from shapely.ops import unary_union
    tw = spec["town"]
    pop = int(tw["population"])
    kind = pick_kind(pop, tw.get("settlement", "auto"))
    W, H = spec["size_ft"]
    seed = int(spec["seed"])
    rnd = random.Random(seed * 31 + 7)
    site = _Site(h, cell, W, H, water_mask, sea)
    warns = []
    pid = spec["id"]
    cx, cy = float(centre[0]), float(centre[1])
    ex, ey = float(entry[0]), float(entry[1])
    d = np.array([cx - ex, cy - ey])
    if np.hypot(*d) < 1:
        d = np.array([0.0, -1.0])
    u = d / np.hypot(*d)                        # along the track, towards the steading
    v = np.array([-u[1], u[0]])                 # across
    links = {"foundry_scene": None, "model3d": None, "ai_layer": None}
    culture = spec.get("culture", "fantasy_generic")
    lane_name = {"scandinavian": "Gardsvegen", "danish_german": "Hofweg", "english": "Farm Lane"}.get(culture, "Farm Track")
    if kind in ("cabin", "lodge"):
        lane_name = {"scandinavian": "Stien", "danish_german": "Pfad", "english": "Footpath"}.get(culture, "Hunter's Path")
    road_name = {"scandinavian": "Kongevegen", "danish_german": "Landstrasse", "english": "The High Road"}.get(culture, "The Old Road")

    # ---- track / road: wavering polyline from the entry edge to the yard (inn: edge to edge through the centre)
    def wavy(p0, p1, amp):
        a, b = np.array(p0, float), np.array(p1, float)
        L = float(np.hypot(*(b - a)))
        n = max(int(L / 30.0), 2)
        dd = (b - a) / max(L, 1e-9)
        nn = np.array([-dd[1], dd[0]])
        ph = rnd.uniform(0, 2 * math.pi)
        pts = []
        for i in range(n + 1):
            t = i / n
            w = amp * math.sin(ph + t * math.pi * 1.6) * math.sin(math.pi * t)
            q = a + (b - a) * t + nn * w
            pts.append([round(min(max(q[0], 0.0), W), 1), round(min(max(q[1], 0.0), H), 1)])
        return pts

    yard_L, yard_D = {"cabin": (30, 24), "lodge": (44, 34), "inn": (70, 46), "hamlet": (64, 54)}.get(kind, (56, 44))
    yard_c = np.array([cx, cy])
    streets = []
    if kind == "inn":
        far = np.array([cx, cy]) + u * max(W, H) * 2
        far = [min(max(far[0], 0), W), min(max(far[1], 0), H)]
        road = wavy([ex, ey], [cx, cy], 12)[:-1] + wavy([cx, cy], far, 12)
        streets.append({"id": "str_main_road", "name": road_name, "kind": "road", "w": 16, "pts": road})
        yard_c = np.array([cx, cy]) + v * (16 / 2 + yard_D / 2 + 4)       # the inn yard opens off the road
    else:
        end = np.array([cx, cy]) - u * (yard_D / 2)
        if kind == "hamlet":
            end = np.array([cx, cy]) + u * (yard_D / 2 + 40)                # the lane runs on past the yard between the houses
        streets.append({"id": "str_track", "name": lane_name, "kind": "lane", "w": 7 if kind == "cabin" else 10, "pts": wavy([ex, ey], end, 10 if kind != "cabin" else 16)})

    # ---- buildings round the yard
    plan = []    # (id, name, kind, L, D, place-fn candidates)
    yu, yv = u, v
    if kind == "inn":                     # frame: along the road, away from it
        yu, yv = u, v

    def spot(along, across, L, D):
        c = yard_c + yu * along + yv * across
        return c, L, D

    names = names or {}
    if kind == "farmstead":
        plan = [("bld_farmhouse", names.get("farmhouse", "Farmhouse"), "farmhouse", spot(yard_D / 2 + 13, 0, 36, 22)),
                ("bld_barn", "Barn", "barn", spot(0, yard_L / 2 + 16, 46, 28)),
                ("bld_well", "Well", "well", spot(0, -8, 7, 7))]
        if pop >= 3:
            plan.insert(2, ("bld_shed_001", "Shed", "shed", spot(0, -(yard_L / 2 + 10), 18, 14)))
        if pop >= 5:
            plan.insert(3, ("bld_shed_002", "Byre", "stable", spot(-(yard_D / 2 + 12), yard_L / 2 - 6, 30, 18)))
    elif kind == "cabin":
        plan = [("bld_cabin", names.get("cabin", "Hunter's Cabin"), "house", spot(yard_D / 2 + 9, 0, 22, 16)),
                ("bld_woodshed", "Woodshed", "shed", spot(4, yard_L / 2 + 6, 10, 8))]
    elif kind == "lodge":
        plan = [("bld_lodge", names.get("lodge", "Hunter's Lodge"), "house", spot(yard_D / 2 + 13, 0, 38, 24)),
                ("bld_stable", "Stable", "stable", spot(0, yard_L / 2 + 12, 30, 18)),
                ("bld_woodshed", "Woodshed", "shed", spot(0, -(yard_L / 2 + 7), 12, 9))]
    elif kind == "inn":
        plan = [("bld_inn", names.get("inn", "Roadside Inn"), "inn", spot(0, yard_D / 2 + 19, 58, 34)),
                ("bld_stables", "Stables", "stable", spot(yard_L / 2 + 13, 0, 22, 40)),
                ("bld_shed_001", "Shed", "shed", spot(-(yard_L / 2 + 9), 4, 14, 12)),
                ("bld_well", "Well", "well", spot(-yard_L / 4, -yard_D / 4 + 4, 7, 7))]
    else:   # hamlet: houses both sides of the lane round the yard, barns behind
        n_h = int(min(4, max(2, round(pop / 5.0))))
        n_b = 1 if pop < 12 else 2
        slots = [(yard_D / 2 + 14, -26), (yard_D / 2 + 14, 26), (0, -(yard_L / 2 + 14)), (0, yard_L / 2 + 14), (-(yard_D / 2 + 14), -30), (-(yard_D / 2 + 14), 30)]
        plan = []
        for i in range(n_h):
            a, b = slots[i]
            plan.append((f"bld_house_{i + 1:03d}", f"House {i + 1}", "house", spot(a, b, 30 + rnd.uniform(-4, 6), 20 + rnd.uniform(-2, 4))))
        for i in range(n_b):
            a, b = slots[n_h + i] if n_h + i < len(slots) else (-(yard_D / 2 + 50), 0)
            plan.append((f"bld_barn_{i + 1:03d}", f"Barn {i + 1}", "barn", spot(a, b, 42, 26)))
        plan.append(("bld_well", "Well", "well", spot(0, 0, 7, 7)))

    placed, polys = [], []
    road_geom = unary_union([LineString(s["pts"]).buffer(s["w"] / 2 + 3) for s in streets])
    for bid, nm, bk, (c, L, D) in plan:
        ok_pts = None
        for k in range(14):                       # nudge outward / sideways until it fits (dry, inside the map, not too steep, no overlap)
            off = [(0, 0), (6, 0), (-6, 0), (0, 6), (0, -6), (12, 0), (0, 12), (-12, 0), (0, -12), (18, 8), (-18, -8), (8, 18), (-8, -18), (24, 0)][k]
            cc = c + yu * off[0] + yv * off[1]
            # long side faces the yard: buildings on the across axis turn 90 degrees
            to = cc - yard_c
            along_axis = abs(float(np.dot(to, yu))) >= abs(float(np.dot(to, yv)))
            pts = _rect(cc, yv if along_axis else yu, yu if along_axis else yv, L, D)
            pg = Polygon(pts)
            if any(pg.buffer(4).intersects(q) for q in polys):
                continue
            if bk != "well" and pg.intersects(road_geom):
                continue
            if site.fits(pts, max_relief=12.0 if bk != "well" else 20.0):
                ok_pts = pts
                break
        if ok_pts is None:
            if not placed and bk != "well":       # the main building always goes in (the centre was chosen on dry flat ground)
                to = c - yard_c
                along_axis = abs(float(np.dot(to, yu))) >= abs(float(np.dot(to, yv)))
                ok_pts = _rect(c, yv if along_axis else yu, yu if along_axis else yv, L, D)
                warns.append(f"{nm}: no level dry spot found nearby; placed at the plan position")
            else:
                warns.append(f"{nm}: skipped (no level dry spot near the yard)")
                continue
        z, rel = _elev(site, ok_pts)
        b = {"id": bid, "name": nm, "kind": bk, "status": "proposed", "geometry": {"type": "polygon", "points": ok_pts}, "notes": "", "links": dict(links),
             "floors": 2 if bk == "inn" else 1, "rooms": [], "doors": [], "elevation_ft": z, "site_relief_ft": rel}
        if bk == "well":
            b["notes"] = "Well (a small well house in the 3D pack)."
            b["height_ft"] = 9
        placed.append(b)
        polys.append(Polygon(ok_pts))

    # ---- yard (square) and the district round the steading
    yard_pts = _rect(yard_c, yv, yu, yard_L, yard_D)
    districts = []
    yz, _ = _elev(site, yard_pts)
    yard_name = {"inn": "Inn Yard", "hamlet": {"english": "The Green", "scandinavian": "Tunet", "danish_german": "Dorfplatz"}.get(culture, "Village Yard")}.get(kind, "Yard")
    if kind != "cabin":
        districts.append({"id": "sqr_yard", "name": yard_name, "kind": "square", "status": "proposed", "geometry": {"type": "polygon", "points": yard_pts}, "notes": "", "links": dict(links), "elevation_ft": yz})
    core = unary_union(polys + [Polygon(yard_pts)]).convex_hull.buffer(22).simplify(4)
    core = core.intersection(Polygon([(0, 0), (W, 0), (W, H), (0, H)]))
    dname = {"farmstead": "Farmstead", "cabin": "Clearing", "lodge": "Lodge", "inn": "Inn", "hamlet": "Hamlet"}[kind]
    if not core.is_empty and core.geom_type == "Polygon":
        lp = core.representative_point()
        districts.append({"id": "dis_core", "name": spec.get("name") or dname, "kind": "district", "status": "proposed",
                          "geometry": {"type": "polygon", "points": [[round(x, 1), round(y, 1)] for x, y in list(core.exterior.coords)[:-1]]},
                          "notes": f"The {dname.lower()} ({pop} people).", "links": dict(links), "ring": "core", "label_point": [round(lp.x, 1), round(lp.y, 1)], "elevation_ft": yz})

    # ---- fenced fields
    n_f = {"farmstead": 2 if pop < 4 else 3, "hamlet": 3 if pop < 12 else 4, "inn": 1, "lodge": 0, "cabin": 0}[kind]
    if tw.get("farmland") is False:
        n_f = 0
    taken = unary_union(polys + [Polygon(yard_pts), road_geom]).buffer(14)
    fields = []
    base_ang = math.atan2(u[1], u[0])
    tries = 0
    while len(fields) < n_f and tries < 200:
        tries += 1
        ang = base_ang + rnd.uniform(-math.pi, math.pi)
        big = tries < 80                                # first try full-size paddocks, then smaller ones
        L = rnd.uniform(90, 180) if big else rnd.uniform(60, 110)
        D = rnd.uniform(60, 120) if big else rnd.uniform(45, 80)
        L, D = min(L, W * 0.35), min(D, H * 0.3)
        r = rnd.uniform(0.5 * max(L, D) + 40, max(0.5 * max(L, D) + 60, 0.5 * min(W, H)))
        fc = yard_c + np.array([math.cos(ang), math.sin(ang)]) * r
        rot = base_ang + rnd.choice([0, math.pi / 2]) + rnd.uniform(-0.15, 0.15)
        fu, fv = np.array([math.cos(rot), math.sin(rot)]), np.array([-math.sin(rot), math.cos(rot)])
        pts = _rect(fc, fu, fv, L, D)
        pg = Polygon(pts)
        if pg.intersects(taken) or not site.fits(pts, margin=6.0, max_relief=40.0):
            continue
        fid = f"fld_{len(fields) + 1:03d}"
        fields.append({"id": fid, "name": "Field " + fid[-3:], "kind": "field", "status": "proposed", "geometry": {"type": "polygon", "points": pts},
                       "notes": "Fenced paddock.", "links": dict(links), "elevation_ft": _elev(site, pts)[0]})
        taken = unary_union([taken, pg.buffer(10)])
    if len(fields) < n_f:
        warns.append(f"{n_f - len(fields)} field(s) did not fit (water, steep ground or the map edge)")
    districts += fields

    # ---- streets.json in town_gen's format (elevations sampled from the terrain)
    out_streets = []
    for s in streets:
        pts = s["pts"]
        z = [round(site.z(p[0], p[1]), 1) for p in pts]
        L = sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))
        gmax = max((abs(z[i + 1] - z[i]) / max(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]), 1e-6) for i in range(len(pts) - 1)), default=0.0)
        out_streets.append({"id": s["id"], "name": s["name"], "kind": s["kind"], "status": "proposed", "geometry": {"type": "polyline", "points": pts, "width_ft": s["w"]},
                            "notes": "Track to the steading." if s["kind"] == "lane" else "Through road past the inn.", "links": dict(links),
                            "elevations_ft": z, "elevation_ft": z[0], "grade_max": round(gmax, 3), "length_ft": round(L, 1)})

    # ---- write
    bdir = os.path.join(pdir, "buildings")
    os.makedirs(bdir, exist_ok=True)
    for f in os.listdir(bdir):
        if f.endswith(".json"):
            os.remove(os.path.join(bdir, f))
    for b in placed:
        _jsave(os.path.join(bdir, b["id"] + ".json"), b)
    _jsave(os.path.join(pdir, "streets.json"), {"place": pid, "streets": out_streets})
    _jsave(os.path.join(pdir, "districts.json"), {"place": pid, "districts": districts})
    counts = {"buildings": len(placed), "streets": len(out_streets), "fields": len(fields), "squares": sum(1 for x in districts if x["kind"] == "square"), "districts": sum(1 for x in districts if x["kind"] == "district")}
    rep = {"generator": "town_tiny.py", "kind": kind, "population": pop, "counts": counts, "warnings": warns, "issues": []}
    _jsave(os.path.join(pdir, "town_gen_report.json"), rep)
    return rep


def _jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")
