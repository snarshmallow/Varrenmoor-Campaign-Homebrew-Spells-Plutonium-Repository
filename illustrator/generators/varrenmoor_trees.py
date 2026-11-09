#!/usr/bin/env python3
"""Tree scatter for Varrenmoor derived from the TREES on the 2D campaign map (assets/map v2.png, copy in illustrator/out/foundry_screens/).

The map is dense forest with clearings (village, roads, fields).  Per 64 px block of the map the canopy fraction (dark pixels) gives the RELATIVE density; the
species mix follows the terrain height of the model (pine / spruce / fir high, birch / alder / oak / beech low, alder and willow near the river).  The absolute
density is scaled so the whole place carries about `--target` trees (a real forest has 200+ per hectare, far too many for 3D Canvas): the pattern of dense and open
ground matches the map, the count is a performance budget.  The result is world/<place>/foliage.json (the plugin's foliage pipeline, same file the
`foundry_push.py push-walls` tree stands read).

  python illustrator/generators/varrenmoor_trees.py scatter --place varrenmoor [--target 6000] [--seed 208] [--rect x0,y0,x1,y1]
  python illustrator/generators/varrenmoor_trees.py report  --place varrenmoor
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foliage as fol  # noqa: E402
import varrenmoor_build as vb  # noqa: E402

BLK = 64                      # map pixels per block
DARK = 62.0                   # luminance below this = canopy


def canopy_grid():
    from PIL import Image
    lum = np.asarray(Image.open(vb.MAP_PNG).convert("RGB"), float).mean(2)
    out = {}
    for by in range(int(vb.Y0), int(vb.Y0 + vb.H_FT / vb.S), BLK):
        for bx in range(int(vb.X0), int(vb.X0 + vb.W_FT / vb.S), BLK):
            blk = lum[by:by + BLK, bx:bx + BLK]
            if blk.size:
                out[(bx, by)] = float((blk < DARK).mean())
    return out


def mix_for(z, zr, near_water):
    """Species mix by relative height zr (0 low .. 1 high) of the model terrain."""
    if near_water:
        return [{"species": "alder", "weight": 3}, {"species": "willow", "weight": 1}, {"species": "birch", "weight": 2}, {"species": "spruce", "weight": 1}]
    if zr > 0.55:
        return [{"species": "spruce", "weight": 4}, {"species": "scots_pine", "weight": 4}, {"species": "fir", "weight": 2}, {"species": "birch", "weight": 1}]
    if zr > 0.25:
        return [{"species": "scots_pine", "weight": 3}, {"species": "spruce", "weight": 2}, {"species": "birch", "weight": 2}, {"species": "beech", "weight": 1}, {"species": "oak", "weight": 1}]
    return [{"species": "birch", "weight": 3}, {"species": "oak", "weight": 2}, {"species": "beech", "weight": 2}, {"species": "alder", "weight": 2}, {"species": "scots_pine", "weight": 1}]


def scatter(place, target=6000, seed=208, rect=None):
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    pdir = os.path.join(vb.REPO, "world", place)
    env = fol.Env.from_place(place)
    lib = fol._lib()
    doc = fol.FoliageDoc(place, None)
    grid = canopy_grid()
    ld = lambda f: json.load(open(os.path.join(vb.PDIR, f), encoding="utf-8"))
    keep_out = []
    for d in ld("districts.json")["districts"]:
        if d["kind"] in ("square", "field"):
            keep_out.append(Polygon(d["geometry"]["points"]).buffer(25))
    keep_out = unary_union(keep_out)
    # forest-edge clearings around the village: no trees inside 120 ft of a building
    win = box(*rect) if rect else box(0, 0, vb.W_FT, vb.H_FT)
    zs = env.h
    zlo, zhi = float(np.percentile(zs, 5)), float(np.percentile(zs, 95))
    wsum = sum(max(0.0, (c - 0.35) / 0.6) ** 1.5 for c in grid.values())
    scale = target / max(1e-9, wsum * ((BLK * vb.S) ** 2 / fol.HA_FT2))
    total = 0
    report = []
    water = env.water
    for (bx, by), c in sorted(grid.items()):
        rel = max(0.0, (c - 0.35) / 0.6) ** 1.5
        if rel <= 0.001:
            continue
        x0, y0 = vb.ft(bx, by)
        x1, y1 = vb.ft(bx + BLK, by + BLK)
        cell = box(x0, y0, x1, y1).intersection(win).difference(keep_out)
        if cell.is_empty:
            continue
        parts = [cell] if cell.geom_type == "Polygon" else [g for g in cell.geoms if g.geom_type == "Polygon" and g.area > 4000]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        zr = (float(env.z(cx, cy)) - zlo) / max(1.0, zhi - zlo)
        nearw = (not water.is_empty) and water.distance(cell) < 150
        dens = rel * scale
        for k, g in enumerate(parts):
            zone = f"m_{bx}_{by}_{k}"
            pts = [[round(x, 1), round(y, 1)] for x, y in list(g.exterior.coords)[:-1]]
            r = fol.run_scatter(doc, env, lib, {"zone": zone, "name": f"map canopy {c:.2f}", "polygon": pts, "mix": mix_for(cx, zr, nearw), "density_per_ha": round(dens, 3),
                                                "seed": seed + bx * 7 + by, "pattern": "cluster", "cluster_size": 6, "cluster_radius_ft": 90, "clearance_building_ft": 60,
                                                "clearance_road_ft": 14, "slope_max_deg": 40, "max_instances": 4000})
            total += r["added"]
            report.append({"block_px": [bx, by], "canopy": round(c, 2), "density_per_ha": round(dens, 2), "zr": round(zr, 2), "added": r["added"]})
    doc.save()
    fol.export_pack_scatter(doc, lib)
    res = {"place": place, "trees": total, "blocks": len(report), "scale_density_per_ha_at_full_canopy": round(scale, 3),
           "per_species": doc.stats(lib).get("per_species") or doc.stats(lib)}
    with open(os.path.join(vb.REPO, "illustrator", "out", f"{place}_tree_report.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": res, "blocks": report}, f, indent=1)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scatter", "report"])
    ap.add_argument("--place", default="varrenmoor")
    ap.add_argument("--target", type=int, default=6000)
    ap.add_argument("--seed", type=int, default=208)
    ap.add_argument("--rect")
    a = ap.parse_args()
    if a.cmd == "scatter":
        rect = [float(v) for v in a.rect.split(",")] if a.rect else None
        print(json.dumps(scatter(a.place, a.target, a.seed, rect)))
    else:
        rep = json.load(open(os.path.join(vb.REPO, "illustrator", "out", f"{a.place}_tree_report.json"), encoding="utf-8"))
        print(json.dumps(rep["summary"], indent=1))


if __name__ == "__main__":
    main()
