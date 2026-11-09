#!/usr/bin/env python3
"""Tree scatter for Varrenmoor derived from the TREES on the 2D campaign map (assets/map v2.png, copy in illustrator/out/foundry_screens/).

The map is dense forest with clearings (village, roads, fields).  Per 64 px block of the map the canopy fraction (dark pixels) gives the RELATIVE density; the
species mix follows the terrain height of the model (pine / spruce / fir high, birch / alder / oak / beech low, alder and willow near the river).  The absolute
density is scaled so the whole place carries about `--target` trees (a real forest has 200+ per hectare, far too many for 3D Canvas): the pattern of dense and open
ground matches the map, the count is a performance budget.  The result is world/<place>/foliage.json (the plugin's foliage pipeline, same file the
`foundry_push.py push-walls` tree stands read).

Pine density (the map shows a dense pine forest): the pines (scots_pine, spruce, fir) of every block are multiplied by `--pine-density` (default 1.5), and
by a further hill factor `1 + --hill-boost * zr` (default 0.6; zr = relative terrain height 0 low .. 1 high), so the high ground carries up to 1.5 x 1.6 = 2.4 x the
old pine count while the broadleaf count stays as before.  `--pine-density 1 --hill-boost 0` reproduces the old scatter.  `--max-trees` (default 12000) caps the
EXPECTED tree count (area x density, before the building / road clearances remove some): every block density is scaled down uniformly when the expectation is
above it.  `--dry-run` counts and reports without writing foliage.json / the scatter pack.

  python illustrator/generators/varrenmoor_trees.py scatter --place varrenmoor [--target 6000] [--seed 208] [--rect x0,y0,x1,y1]
                         [--pine-density 1.5] [--hill-boost 0.6] [--max-trees 12000] [--dry-run]
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


PINES = ("scots_pine", "spruce", "fir")
DEFAULT_PINE_DENSITY = 1.5    # Varrenmoor default: denser pines than the first scatter (1.0)
DEFAULT_HILL_BOOST = 0.6      # extra pine factor at the highest ground (zr = 1)
DEFAULT_MAX_TREES = 12000     # cap on the expected tree count (3D Canvas instance budget)


def boosted_mix(mix, pine_mult):
    """(mix with the pine weights x pine_mult, total-density factor): the factor keeps the broadleaf density unchanged and multiplies only the pines."""
    tot = float(sum(m["weight"] for m in mix))
    pine = float(sum(m["weight"] for m in mix if m["species"] in PINES))
    if tot <= 0 or pine <= 0 or pine_mult == 1.0:
        return mix, 1.0
    out = [{**m, "weight": m["weight"] * pine_mult if m["species"] in PINES else m["weight"]} for m in mix]
    return out, 1.0 + (pine / tot) * (pine_mult - 1.0)


def pine_multiplier(zr, pine_density=DEFAULT_PINE_DENSITY, hill_boost=DEFAULT_HILL_BOOST):
    return max(0.0, float(pine_density)) * (1.0 + max(0.0, float(hill_boost)) * min(1.0, max(0.0, zr)))


def scatter(place, target=6000, seed=208, rect=None, pine_density=DEFAULT_PINE_DENSITY, hill_boost=DEFAULT_HILL_BOOST, max_trees=DEFAULT_MAX_TREES, dry_run=False):
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
    jobs = []
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
        mix, fac = boosted_mix(mix_for(cx, zr, nearw), pine_multiplier(zr, pine_density, hill_boost))
        dens = rel * scale * fac
        for k, g in enumerate(parts):
            jobs.append((bx, by, c, zr, k, g, mix, dens, cx))
    expected = sum(j[7] * j[5].area / fol.HA_FT2 for j in jobs)
    cap = min(1.0, max_trees / expected) if (max_trees and expected > 0) else 1.0
    for bx, by, c, zr, k, g, mix, dens, cx in jobs:
        dens *= cap
        zone = "mz" + "".join(chr(97 + int(ch)) for ch in f"{bx:04d}{by:04d}{k}")           # letters only: ids like fol_mzabcd_0001 (digits and underscores in a zone confused the push duplicate guard)
        pts = [[round(x, 1), round(y, 1)] for x, y in list(g.exterior.coords)[:-1]]
        r = fol.run_scatter(doc, env, lib, {"zone": zone, "name": f"map canopy {c:.2f}", "polygon": pts, "mix": mix, "density_per_ha": round(dens, 3),
                                            "seed": seed + bx * 7 + by, "pattern": "cluster", "cluster_size": 6, "cluster_radius_ft": 90, "clearance_building_ft": 60,
                                            "clearance_road_ft": 14, "slope_max_deg": 40, "max_instances": 4000})
        total += r["added"]
        report.append({"block_px": [bx, by], "canopy": round(c, 2), "density_per_ha": round(dens, 2), "zr": round(zr, 2), "added": r["added"]})
    if not dry_run:
        doc.save()
        fol.export_pack_scatter(doc, lib)
    stats = doc.stats(lib)
    res = {"place": place, "trees": total, "expected_before_clearances": round(expected), "cap_factor": round(cap, 3), "pine_density": pine_density, "hill_boost": hill_boost, "dry_run": dry_run, "blocks": len(report), "scale_density_per_ha_at_full_canopy": round(scale, 3),
           "per_species": stats.get("per_species") or stats}
    if dry_run:
        return res
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
    ap.add_argument("--pine-density", type=float, default=DEFAULT_PINE_DENSITY, help="pine (scots_pine, spruce, fir) density multiplier, 1 = the old scatter (default 1.5)")
    ap.add_argument("--hill-boost", type=float, default=DEFAULT_HILL_BOOST, help="extra pine factor 1 + boost x relative height, so hills are denser (default 0.6)")
    ap.add_argument("--max-trees", type=int, default=DEFAULT_MAX_TREES, help="cap on the expected tree count; 0 = no cap (default 12000)")
    ap.add_argument("--dry-run", action="store_true", help="count only: write nothing")
    a = ap.parse_args()
    if a.cmd == "scatter":
        rect = [float(v) for v in a.rect.split(",")] if a.rect else None
        print(json.dumps(scatter(a.place, a.target, a.seed, rect, a.pine_density, a.hill_boost, a.max_trees, a.dry_run)))
    else:
        rep = json.load(open(os.path.join(vb.REPO, "illustrator", "out", f"{a.place}_tree_report.json"), encoding="utf-8"))
        print(json.dumps(rep["summary"], indent=1))


if __name__ == "__main__":
    main()
