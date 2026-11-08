"""Terrain and water recipes for place_create.py: a few words (recipe, relief, sea, rivers, lakes) -> a terrain_spec.json for terrain.py
plus the water.json entities (rivers from river_meander.py, sea and lakes from contours of the finished heightmap).

Every recipe is written in a canonical frame (width cw, height ch, the sea / low end at the bottom = +y) and then rotated onto the
wanted side, so one description gives coastal-south, coastal-east, ...  Everything is feet, y down, deterministic by seed.

  spec, info = build_terrain_spec(terrain_dict, W, H, seed)        info: sea (bool), sea_side, rivers [valley dicts], lakes [..], hint {...}
  water = build_water(spec, info, heightmap, meta)                 list of water.json entities (rivers, sea, lakes)
"""
import math
import random

import numpy as np

RECIPES = ("flat", "rolling", "hills", "valley", "bowl", "coastal", "island", "pass", "fjord", "mountain")
SIDES = ("north", "south", "east", "west")

# default relief (ft of ridge / peak height above the base plane) per recipe
RELIEF = {"flat": 6, "rolling": 40, "hills": 130, "valley": 240, "bowl": 280, "coastal": 90, "island": 160, "pass": 360, "fjord": 330, "mountain": 520}


def _rot(side, W, H):
    """Canonical frame (cw, ch) and the map (x, y) -> world transform for a sea / low end on `side`."""
    if side == "south":
        return W, H, (lambda x, y: (x, y)), (lambda tx, ty: (tx, ty))
    if side == "north":
        return W, H, (lambda x, y: (x, H - y)), (lambda tx, ty: (tx, -ty))
    if side == "east":
        return H, W, (lambda x, y: (y, x)), (lambda tx, ty: (ty, tx))
    return H, W, (lambda x, y: (W - y, x)), (lambda tx, ty: (-ty, tx))        # west


def _river_route(rnd, cw, ch, x0, x1, y_end, rel, step=260.0, wiggle=0.07):
    """Coarse route [x, y, rel, side] from above the top edge (x0) to y_end (x1 at the end); gently wandering."""
    n = max(int((y_end + 100) / step), 4)
    pts = []
    ph = rnd.uniform(0, 6.28)
    for i in range(n + 1):
        t = i / n
        y = -100 + t * (y_end + 100)
        x = x0 + (x1 - x0) * t + math.sin(ph + t * 5.0) * cw * wiggle * math.sin(math.pi * min(t * 1.2, 1))
        pts.append([round(x, 1), round(y, 1), rel, 0.22])
    return pts


def build_terrain_spec(t, W, H, seed):
    """t: the spec's terrain block (recipe, relief_ft, sea_level_ft, base_elevation_ft, sea_side, rivers, river_meander, river_width_ft, lakes, ruggedness, cell_ft)."""
    recipe = t.get("recipe", "rolling")
    if recipe not in RECIPES:
        raise ValueError(f"unknown terrain recipe {recipe!r}; have {', '.join(RECIPES)}")
    rnd = random.Random(int(seed) * 7919 + 13)
    sea_side = t.get("sea_side") or "south"
    cw, ch, F, FT = _rot(sea_side, W, H)
    relief = float(t.get("relief_ft") or RELIEF[recipe])
    rug = float(t.get("ruggedness", 0.5))
    sea_level = float(t.get("sea_level_ft", 0.0))
    base_el = t.get("base_elevation_ft")
    n_riv = int(t.get("rivers", 0 if recipe in ("island", "fjord") else 1) if not isinstance(t.get("rivers"), dict) else t["rivers"].get("count", 1))
    ridges, peaks, valleys, passes = [], [], [], []
    tilt = (0.0, 0.0)
    sea = False
    hint = {"centre": (0.5, 0.5), "entry": "south"}   # canonical fractions, entry side in the canonical frame
    nat = {"defaults_version": 2, "rough_ft": 1.5 + 5 * rug, "final_smooth_cells": 0.8}
    noise = {"scale_ft": 420, "octaves": 5, "lacunarity": 2.0, "gain": 0.5, "ridged_amp_ft": 0, "base_amp_ft": 2.0, "warp_ft": 120, "warp_scale_ft": 700,
             "feature_warp_ft": 160, "feature_warp_scale_ft": 750}
    erosion = {"thermal_iterations": 30, "talus_slope": 1.0, "rate": 0.5, "smooth_sigma_cells": 1.0}
    river_rel, river_end = -6.0, ch + 250.0
    river_x0, river_x1 = cw * rnd.uniform(0.40, 0.60), cw * rnd.uniform(0.40, 0.60)
    lakes_n = int(t.get("lakes", 0))

    def edge_ridge(side, hgt, wid, name, pts=7, jitter=0.18):
        """A ridge along one edge (canonical frame), wavering in height and offset."""
        out = []
        for i in range(pts):
            f = i / (pts - 1)
            hh = hgt * (0.65 + 0.55 * rnd.random())
            off = wid * 0.35 + rnd.uniform(-jitter, jitter) * wid * 0.4
            if side == "n":
                out.append([cw * (-0.06 + 1.12 * f), off - wid * 0.25, hh])
            elif side == "s":
                out.append([cw * (-0.06 + 1.12 * f), ch - off + wid * 0.25, hh])
            elif side == "w":
                out.append([off - wid * 0.25, ch * (-0.06 + 1.12 * f), hh])
            else:
                out.append([cw - off + wid * 0.25, ch * (-0.06 + 1.12 * f), hh])
        return {"name": name, "width_ft": round(wid), "sharpness": 1.5, "points": [[round(a, 1), round(b, 1), round(c_, 1)] for a, b, c_ in out], "spurs": relief > 150}

    if recipe == "flat":
        base_el = 55.0 if base_el is None else base_el
        tilt = (0.0, -0.004)
        noise.update(base_amp_ft=2.6, warp_ft=60)
        nat.update(rough_ft=1.0)
        for _ in range(3):
            peaks.append({"name": "swell", "x": round(rnd.uniform(0.1, 0.9) * cw), "y": round(rnd.uniform(0.1, 0.9) * ch), "height": round(relief * rnd.uniform(0.6, 1.3), 1), "radius_ft": round(rnd.uniform(0.18, 0.3) * cw), "mode": "add"})
        hint["entry"] = "south"
    elif recipe == "rolling":
        base_el = 120.0 if base_el is None else base_el
        tilt = (0.0, -0.02)
        noise.update(ridged_amp_ft=0, base_amp_ft=relief * 0.25, scale_ft=520)
        for _ in range(int(7 + cw / 500)):
            peaks.append({"name": "rise", "x": round(rnd.uniform(0.0, 1.0) * cw), "y": round(rnd.uniform(0.0, 1.0) * ch), "height": round(relief * rnd.uniform(0.35, 1.0), 1),
                          "radius_ft": round(rnd.uniform(0.12, 0.25) * cw), "mode": "add"})
    elif recipe == "hills":
        base_el = 220.0 if base_el is None else base_el
        tilt = (0.0, -0.03)
        noise.update(ridged_amp_ft=relief * 0.35, base_amp_ft=4, scale_ft=480)
        for _ in range(int(8 + cw / 400)):
            peaks.append({"name": "hill", "x": round(rnd.uniform(0.0, 1.0) * cw), "y": round(rnd.uniform(0.0, 0.95) * ch), "height": round(relief * rnd.uniform(0.35, 1.0), 1),
                          "radius_ft": round(rnd.uniform(0.10, 0.22) * cw), "sharpness": 1.2, "mode": "add"})
        ridges.append({"name": "back hills", "width_ft": round(cw * 0.22), "sharpness": 1.4, "spurs": True,
                       "points": [[round(cw * (-0.1 + 0.3 * i), 1), round(ch * (0.02 + 0.06 * rnd.random()), 1), round(relief * (0.9 + 0.4 * rnd.random()), 1)] for i in range(5)]})
        nat["rugged"] = {"scale_ft": 360, "amp_ft": relief * 0.25, "octaves": 5}
        hint["centre"] = (0.5, 0.55)
    elif recipe in ("valley", "bowl"):
        base_el = 520.0 if base_el is None else base_el
        tilt = (0.0, -0.035)
        noise.update(ridged_amp_ft=relief * 0.3, base_amp_ft=3, scale_ft=420)
        ridges.append(edge_ridge("w", relief, cw * 0.17, "west wall"))
        ridges.append(edge_ridge("e", relief, cw * 0.17, "east wall"))
        if recipe == "bowl":
            ridges.append(edge_ridge("n", relief * 1.15, ch * 0.30, "north wall"))
            ridges.append({"name": "south shoulders", "width_ft": round(cw * 0.12), "sharpness": 1.4, "spurs": False,
                           "points": [[round(-cw * 0.05), round(ch * 0.97), round(relief * 0.5)], [round(cw * 0.30), round(ch * 0.93), round(relief * 0.35)]]})
            ridges.append({"name": "south shoulders E", "width_ft": round(cw * 0.12), "sharpness": 1.4, "spurs": False,
                           "points": [[round(cw * 0.70), round(ch * 0.93), round(relief * 0.35)], [round(cw * 1.05), round(ch * 0.97), round(relief * 0.5)]]})
            passes.append({"name": "outlet", "core_ft": round(cw * 0.04), "side_slope": 0.3, "points": [[round(cw * 0.5), round(ch * 0.85), -8, 0.25], [round(cw * 0.5), round(ch * 1.05), -10, 0.35]]})
        nat["rugged"] = {"scale_ft": 330, "amp_ft": relief * 0.4, "octaves": 6}
        nat["spurs"] = {"clear_points": [[round(cw * 0.5), round(ch * 0.5), round(cw * 0.15)]]}
        nat["keep_clear"] = [[round(cw * 0.5), round(ch * 0.5), round(cw * 0.12)]]
        nat["hydraulic"] = {"iterations": 24, "K": 0.08, "max_incise_ft": 40}
        hint["centre"] = (0.5, 0.52)
        hint["entry"] = "south"
    elif recipe == "coastal":
        sea = True
        tilt = (0.0, -0.028)
        yc = ch * 0.74
        base_el = (0.028 * (yc - ch / 2)) if base_el is None else base_el
        noise.update(ridged_amp_ft=relief * 0.18, base_amp_ft=3.5, scale_ft=520)
        for _ in range(int(5 + cw / 500)):
            peaks.append({"name": "down", "x": round(rnd.uniform(0.0, 1.0) * cw), "y": round(rnd.uniform(0.0, 0.6) * ch), "height": round(relief * rnd.uniform(0.4, 1.0), 1),
                          "radius_ft": round(rnd.uniform(0.12, 0.24) * cw), "mode": "add"})
        ridges.append({"name": "inland hills", "width_ft": round(cw * 0.2), "sharpness": 1.3, "spurs": relief > 120,
                       "points": [[round(cw * (-0.1 + 0.3 * i), 1), round(ch * (0.0 + 0.06 * rnd.random()), 1), round(relief * (0.8 + 0.5 * rnd.random()), 1)] for i in range(5)]})
        # a headland and a bay along the shore
        peaks.append({"name": "headland", "x": round(cw * rnd.choice([0.15, 0.85])), "y": round(yc + ch * 0.04), "height": round(relief * 0.35 + 20, 1), "radius_ft": round(cw * 0.1), "mode": "add"})
        river_end = yc + 70
        hint["centre"] = (0.5, 0.62)
        hint["entry"] = "north"
        hint["coast_y"] = yc
        nat["rugged"] = {"scale_ft": 360, "amp_ft": relief * 0.2, "octaves": 5}
    elif recipe == "island":
        sea = True
        base_el = -(relief * 0.18 + 8) if base_el is None else base_el
        tilt = (0.0, 0.0)
        r_isl = min(cw, ch) * 0.46
        peaks.append({"name": "island mass", "x": round(cw * 0.5), "y": round(ch * 0.5), "height": round(relief + abs(base_el) + 10, 1), "radius_ft": round(r_isl), "sharpness": 0.9, "mode": "add"})
        for _ in range(3):
            peaks.append({"name": "knoll", "x": round(cw * rnd.uniform(0.3, 0.7)), "y": round(ch * rnd.uniform(0.3, 0.7)), "height": round(relief * rnd.uniform(0.2, 0.5), 1),
                          "radius_ft": round(r_isl * rnd.uniform(0.25, 0.45)), "mode": "add"})
        noise.update(ridged_amp_ft=relief * 0.1, base_amp_ft=3, scale_ft=400)
        hint["centre"] = (0.5, 0.60)
        hint["entry"] = "south"
        n_riv = min(n_riv, 1)
        river_x0, river_x1 = cw * 0.5, cw * 0.55
        river_end = ch * 0.5 + r_isl * 0.9
        nat["rugged"] = {"scale_ft": 300, "amp_ft": relief * 0.15, "octaves": 5}
    elif recipe == "pass":
        # a high range top and bottom with a pass running left -> right (canonical x); fort-town at the narrows
        base_el = 1500.0 if base_el is None else base_el
        tilt = (0.0, 0.0)
        ridges.append({"name": "north range", "width_ft": round(ch * 0.5), "sharpness": 1.5, "spurs": True,
                       "points": [[round(cw * (-0.1 + 0.3 * i), 1), round(ch * (0.02 + 0.1 * rnd.random()), 1), round(relief * (0.8 + 0.5 * rnd.random()), 1)] for i in range(5)]})
        ridges.append({"name": "south range", "width_ft": round(ch * 0.5), "sharpness": 1.5, "spurs": True,
                       "points": [[round(cw * (-0.1 + 0.3 * i), 1), round(ch * (0.98 - 0.1 * rnd.random()), 1), round(relief * (0.8 + 0.5 * rnd.random()), 1)] for i in range(5)]})
        # the pass floor: east-west valley, narrowest in the middle
        pp = [[round(-cw * 0.1), round(ch * 0.55), -6, 0.45], [round(cw * 0.3), round(ch * 0.50), -10, 0.6], [round(cw * 0.5), round(ch * 0.48), -10, 0.75],
              [round(cw * 0.7), round(ch * 0.52), -10, 0.6], [round(cw * 1.1), round(ch * 0.5), -6, 0.45]]
        valleys.append({"name": "the pass", "core_ft": round(max(ch * 0.27, 320)), "side_slope": 0.6, "points": pp, "river": n_riv > 0,
                        "meander": {"preset": t.get("river_meander") or "gentle", "seed": int(seed), "width_floor_ft": float(t.get("river_width_ft") or 30), "width_gorge_ft": 16}})
        nat["rugged"] = {"scale_ft": 320, "amp_ft": relief * 0.35, "octaves": 6}
        nat["keep_clear"] = [[round(cw * 0.5), round(ch * 0.48), round(ch * 0.12)]]
        nat["hydraulic"] = {"iterations": 24, "K": 0.08, "max_incise_ft": 45}
        noise.update(ridged_amp_ft=relief * 0.3)
        hint["centre"] = (0.5, 0.49)
        hint["entry"] = "west"
        n_riv = 0   # the pass valley itself carries the stream
    elif recipe == "fjord":
        sea = True
        base_el = 30.0 if base_el is None else base_el
        tilt = (0.0, -0.012)
        yh = ch * 0.34                                         # head of the fjord
        ridges.append(edge_ridge("w", relief, cw * 0.30, "west wall"))
        ridges.append(edge_ridge("e", relief, cw * 0.30, "east wall"))
        ridges.append(edge_ridge("n", relief * 0.9, ch * 0.28, "head wall"))
        cx = cw * 0.5
        valleys.append({"name": "fjord (sea inlet)", "core_ft": round(cw * 0.07), "side_slope": 1.1,
                        "points": [[round(cx, 1), round(ch * 1.1), -140, 1.1], [round(cx + cw * 0.01), round(ch * 0.8), -120, 1.1], [round(cx - cw * 0.02), round(ch * 0.55), -80, 0.9],
                                   [round(cx, 1), round(yh), -26, 0.5]]})
        nat["rugged"] = {"scale_ft": 330, "amp_ft": relief * 0.3, "octaves": 6}
        noise.update(ridged_amp_ft=relief * 0.3)
        river_x0, river_x1, river_end = cx, cx, yh + 20
        n_riv = min(n_riv, 1) if t.get("rivers") is not None else 1
        hint["centre"] = (0.5, 0.40)
        hint["entry"] = "north"
        hint["fjord_head_y"] = yh
    elif recipe == "mountain":
        base_el = 1800.0 if base_el is None else base_el
        tilt = (0.0, -0.05)
        ridges.append(edge_ridge("w", relief, cw * 0.22, "west range"))
        ridges.append(edge_ridge("e", relief, cw * 0.22, "east range"))
        ridges.append(edge_ridge("n", relief * 1.2, ch * 0.35, "high range"))
        for _ in range(4):
            peaks.append({"name": "peak", "x": round(rnd.uniform(0.15, 0.85) * cw), "y": round(rnd.uniform(0.02, 0.3) * ch), "height": round(relief * rnd.uniform(0.3, 0.6), 1),
                          "radius_ft": round(rnd.uniform(0.06, 0.12) * cw), "mode": "add"})
        nat["rugged"] = {"scale_ft": 300, "amp_ft": relief * 0.45, "octaves": 6}
        nat["keep_clear"] = [[round(cw * 0.5), round(ch * 0.55), round(cw * 0.12)]]
        nat["spurs"] = {"clear_points": [[round(cw * 0.5), round(ch * 0.55), round(cw * 0.16)]]}
        nat["hydraulic"] = {"iterations": 28, "K": 0.1, "max_incise_ft": 55}
        noise.update(ridged_amp_ft=relief * 0.3, base_amp_ft=4)
        hint["centre"] = (0.5, 0.58)
        hint["entry"] = "south"
        river_x0, river_x1 = cw * 0.5, cw * 0.52

    rivers = []
    mean = t.get("river_meander") or "gentle"
    rw = float(t.get("river_width_ft") or 0)
    for k in range(max(n_riv, 0)):
        x0 = river_x0 + (k * cw * 0.28 * (1 if k % 2 == 0 else -1) if k else 0)
        x1 = river_x1 + (k * cw * 0.28 * (1 if k % 2 == 0 else -1) if k else 0)
        x0, x1 = min(max(x0, cw * 0.12), cw * 0.88), min(max(x1, cw * 0.12), cw * 0.88)
        pts = _river_route(rnd, cw, ch, x0, x1, river_end if k == 0 else river_end - ch * 0.1, river_rel)
        # canonical -> world
        wpts = [[*F(p[0], p[1]), p[2], p[3]] for p in pts]
        creek = k > 0 or rw and rw < 40
        meander = {"preset": mean, "seed": int(seed) + 31 * k}
        wf = rw if rw else (24 if creek else 54)
        meander.update(width_floor_ft=wf, width_gorge_ft=round(wf * 0.55, 1))
        meander.update({kk: vv for kk, vv in (t.get("river_meander_params") or {}).items() if vv is not None})
        rivers.append({"name": "river" if k == 0 else f"stream {k}", "core_ft": 18 if creek else 25, "side_slope": 0.22, "points": wpts, "river": True, "meander": meander})
    # canonical -> world for everything else
    def wpt(p):
        x, y = F(p[0], p[1])
        return [round(x, 1), round(y, 1)] + list(p[2:])
    ridges = [dict(r, points=[wpt(p) for p in r["points"]]) for r in ridges]
    for pk in peaks:
        pk["x"], pk["y"] = (round(v, 1) for v in F(pk["x"], pk["y"]))
    for v in valleys + passes:
        v["points"] = [wpt(p) for p in v["points"]]
    if nat.get("keep_clear"):
        nat["keep_clear"] = [[*(round(v, 1) for v in F(c[0], c[1])), c[2]] for c in nat["keep_clear"]]
    if nat.get("spurs", {}).get("clear_points"):
        nat["spurs"]["clear_points"] = [[*(round(v, 1) for v in F(c[0], c[1])), c[2]] for c in nat["spurs"]["clear_points"]]
    # lakes: a shallow dish carved by a negative "add" peak, water polygon taken from the finished map (build_water)
    lakes = []
    for i in range(lakes_n):
        lx, ly = rnd.uniform(0.2, 0.8) * cw, rnd.uniform(0.15, 0.8) * ch
        rad = rnd.uniform(0.07, 0.12) * min(cw, ch)
        x, y = F(lx, ly)
        peaks.append({"name": f"lake basin {i + 1}", "x": round(x, 1), "y": round(y, 1), "height": -round(rnd.uniform(14, 24), 1), "radius_ft": round(rad), "sharpness": 0.8, "mode": "add"})
        lakes.append({"x": round(x, 1), "y": round(y, 1), "radius_ft": round(rad)})
    tx, ty = FT(*tilt)
    spec = {"_note": "Written by place_create.py from the place spec (terrain recipe %s). Heights are feet above sea level; ridge heights above the base plane." % recipe,
            "size_ft": [W, H], "cell_ft": float(t.get("cell_ft") or 10), "seed": int(seed),
            "base_elevation_ft": round(float(base_el), 2), "base_tilt": [round(tx, 5), round(ty, 5)],
            "ridges": ridges, "peaks": peaks, "valleys": rivers + valleys, "passes": passes, "noise": noise, "erosion": erosion,
            "natural": nat, "sea_level_ft": sea_level}
    cf = hint["centre"]
    cx_w, cy_w = F(cf[0] * cw, cf[1] * ch)
    ent_map = {"south": (0.5, 1.0), "north": (0.5, 0.0), "west": (0.0, 0.5), "east": (1.0, 0.5)}
    ex, ey = ent_map[hint["entry"]]
    ent_w = F(ex * cw, ey * ch)
    # entry side in world terms
    es = ["west" if ent_w[0] < W * 0.25 else "east" if ent_w[0] > W * 0.75 else None, "north" if ent_w[1] < H * 0.25 else "south" if ent_w[1] > H * 0.75 else None]
    info = {"sea": sea, "sea_side": sea_side if sea else None, "rivers": rivers, "lakes": lakes, "recipe": recipe,
            "hint": {"centre": [round(cx_w), round(cy_w)], "entry_xy": [round(min(max(ent_w[0], 0), W)), round(min(max(ent_w[1], 0), H))], "entry_side": next((s for s in es if s), "south")},
            "coast_note": hint.get("coast_y")}
    return spec, info


# ------------------------------------------------------------------ water entities
def _contour_polys(h, cell, level, bounds=None):
    """Polygons (list of point lists, feet) where h < level, from contourpy."""
    import contourpy
    ny, nx = h.shape
    gen = contourpy.contour_generator(np.arange(nx) * cell, np.arange(ny) * cell, h, fill_type=contourpy.FillType.OuterOffset)
    verts, offs = gen.filled(-1e9, level)
    polys = []
    for v, o in zip(verts, offs):
        for a, b in zip(o[:-1], o[1:]):
            ring = np.asarray(v[a:b])
            if len(ring) >= 4:
                polys.append(ring)
    return polys


def build_water(spec, info, h, meta, place_id, names):
    """-> list of water.json entities. names: naming-set dict (river_names)."""
    import river_meander as rm
    from shapely.geometry import Polygon
    cell = float(meta["cell_ft"])
    sea_level = float(meta.get("sea_level_ft", 0.0))
    ents = []
    rn = list(names.get("river_names") or ["The river"])
    for k, v in enumerate([x for x in spec["valleys"] if x.get("river")]):
        g = rm.river_geometry(v)
        cl = g["centerline"]
        sinu, length = rm.sinuosity(cl, -1e9, 1e9)
        m = g["params"]
        e = {"id": "wat_river" if k == 0 else f"wat_river_{k + 1}", "name": rn[k % len(rn)] if k < len(rn) else f"{rn[0]} {k + 1}", "kind": "river", "status": "proposed",
             "geometry": {"type": "polygon", "points": g["outline"]},
             "notes": "Generated by place_create.py (meander preset %s, %g ft wavelength)." % (m["preset"], m["wavelength_ft"]),
             "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "centerline": cl, "widths_ft": g["widths"],
             "width_ft": round(sum(g["widths"]) / len(g["widths"]), 1), "depth_ft": 5, "flow": "downstream along the centreline",
             "length_ft": round(length, 1), "sinuosity": round(sinu, 3),
             "meander": {kk: m[kk] for kk in ("preset", "amplitude_ft", "wavelength_ft", "seed", "width_var")}}
        if g["bars"]:
            e["bars"] = g["bars"]
        ents.append(e)
    if info["sea"]:
        # the sea = the biggest connected below-datum region touching a map edge, simplified
        from scipy import ndimage as ndi
        wet = h < sea_level
        lab, n = ndi.label(wet)
        keep = np.zeros_like(wet)
        for i in range(1, n + 1):
            m_ = lab == i
            if m_[0, :].any() or m_[-1, :].any() or m_[:, 0].any() or m_[:, -1].any() or m_.sum() > 0.01 * wet.size:
                keep |= m_
        if keep.any():
            hh = np.where(keep, h, sea_level + 50.0)
            hh = ndi.gaussian_filter(np.where(keep, h - sea_level, 50.0), 0.8, mode="nearest")
            polys = sorted(_contour_polys(hh, cell, 0.0), key=lambda r: -Polygon(r).area if len(r) > 3 else 0)
            for i, ring in enumerate(polys[:3]):
                poly = Polygon(ring).buffer(0).simplify(cell * 0.35)
                if poly.is_empty or poly.area < 4000:
                    continue
                ge = poly if poly.geom_type == "Polygon" else max(poly.geoms, key=lambda g_: g_.area)
                ents.append({"id": f"wat_sea_{i + 1:02d}", "name": "The sea" if i == 0 else f"Bay {i}", "kind": "sea", "status": "proposed",
                             "geometry": {"type": "polygon", "points": [[round(x, 1), round(y, 1)] for x, y in list(ge.exterior.coords)[:-1]]},
                             "elevation_ft": sea_level, "notes": "Below-datum water traced from the heightmap by place_create.py.",
                             "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}})
    for i, lk in enumerate(info["lakes"]):
        # level = the lowest rim elevation on a ring round the basin; water = connected cells below it around the basin floor
        ring_r = lk["radius_ft"] * 1.05
        ang = np.linspace(0, 2 * np.pi, 48, endpoint=False)
        gx = np.clip((lk["x"] + ring_r * np.cos(ang)) / cell, 0, h.shape[1] - 1.001)
        gy = np.clip((lk["y"] + ring_r * np.sin(ang)) / cell, 0, h.shape[0] - 1.001)
        rim = h[gy.astype(int), gx.astype(int)]
        level = float(np.percentile(rim, 20)) - 0.6
        from scipy import ndimage as ndi
        lab, _ = ndi.label(h < level)
        ci, cj = int(lk["y"] / cell), int(lk["x"] / cell)
        win = lab[max(ci - 3, 0):ci + 4, max(cj - 3, 0):cj + 4]
        ids = [v for v in np.unique(win) if v]
        if not ids:
            continue
        m_ = np.isin(lab, ids)
        hh = ndi.gaussian_filter(np.where(m_, h - level, 20.0), 0.7)
        polys = sorted(_contour_polys(hh, cell, 0.0), key=lambda r: -Polygon(r).area)
        if not polys:
            continue
        poly = Polygon(polys[0]).buffer(0).simplify(cell * 0.3)
        if poly.is_empty or poly.area < 1500:
            continue
        ge = poly if poly.geom_type == "Polygon" else max(poly.geoms, key=lambda g_: g_.area)
        ents.append({"id": f"wat_lake_{i + 1:02d}", "name": "Lake" if i == 0 else f"Lake {i + 1}", "kind": "lake" if poly.area > 20000 else "pond", "status": "proposed",
                     "geometry": {"type": "polygon", "points": [[round(x, 1), round(y, 1)] for x, y in list(ge.exterior.coords)[:-1]]}, "elevation_ft": round(level, 1),
                     "notes": "Lake in a shallow basin (place_create.py).", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}})
    return ents
