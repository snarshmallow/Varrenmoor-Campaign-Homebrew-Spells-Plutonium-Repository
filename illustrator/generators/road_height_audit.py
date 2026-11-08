"""Quantify road vs terrain height in an exported world pack: for every road vertex (and points every few ft along each segment) the road bed height
(+ the ribbon lift) minus the exported terrain height. Negative = terrain covers the road, large positive = road floats.
  python illustrator/generators/road_height_audit.py --place bridgehollow__dyers_walk_local [--step-ft 4] [--json out.json]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge_maker as bm  # noqa: E402


def audit(pack, step_ft=4.0):
    import worldpack as wp
    rows = []
    for r in pack.list("roads"):
        if r.get("bridge") or not r.get("points"):
            continue
        P = np.asarray(r["points"], float)
        s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
        ss = np.unique(np.concatenate([s, np.arange(0, s[-1], step_ft)]))
        x, y, z = np.interp(ss, s, P[:, 0]), np.interp(ss, s, P[:, 1]), np.interp(ss, s, P[:, 2])
        g = np.array([wp.bilinear(pack.heights, pack.cell_ft, a, b) for a, b in zip(x, y)])
        d = z + bm.LIFT_M / bm.FT - g
        grade = np.abs(np.diff(z) / np.maximum(np.diff(ss), 1e-6))
        rows.append(dict(id=r["id"], cls=r["class"], width_ft=r["width_ft"], n=int(len(ss)), min_ft=round(float(d.min()), 2), mean_ft=round(float(d.mean()), 2), max_ft=round(float(d.max()), 2),
                         buried_pct=round(100.0 * float((d < 0.05).mean()), 1), floating_pct=round(100.0 * float((d > 1.0).mean()), 1), max_grade_deg=round(float(np.degrees(np.arctan(grade.max()))) if len(grade) else 0, 1)))
    return rows


if __name__ == "__main__":
    import worldpack as wp
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--pack")
    ap.add_argument("--step-ft", type=float, default=4.0)
    ap.add_argument("--json")
    a = ap.parse_args()
    pack = wp.load_pack(a.pack or os.path.join(bm.WORLD, a.place, "export"))
    rows = audit(pack, a.step_ft)
    print(f"terrain cell {pack.cell_ft} ft; {len(rows)} roads")
    for r in rows:
        print(f"{r['id']:<28}{r['cls']:<8} diff min {r['min_ft']:>6} mean {r['mean_ft']:>6} max {r['max_ft']:>6} ft  buried {r['buried_pct']:>5}%  floating {r['floating_pct']:>5}%  max grade {r['max_grade_deg']} deg")
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)
