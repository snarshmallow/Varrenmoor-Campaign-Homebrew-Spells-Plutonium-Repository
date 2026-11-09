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


def mesh_audit(pack, road_grade=True, step=1):
    """What the player sees: build the terrain and road meshes (worldpack_mesh.build_parts with the given road grading, False = old behaviour) and compare every
    road deck triangle (vertices, edge midpoints, centroid; faces with a mostly-up normal, so skirts are excluded) with the terrain mesh triangles.
    depth > 0: deck above terrain, < 0: terrain covers the road. Also reports the road grade in degrees along each centreline (from the deck heights)."""
    import worldpack_mesh as wm
    import road_grade as rg
    parts = wm.build_parts(pack, step=step, layers={"terrain", "roads"}, road_grade=(dict({} if road_grade is True else road_grade, skirt=False) if road_grade is not False else False))   # no apron: only the deck is compared
    fr = pack.frame
    t = next(p for p in parts if p["layer"] == "terrain")["mesh"]
    ny = len(np.unique(t.V[:, 1].round(4)))
    nx = len(t.V) // ny
    Z = (t.V[:, 2].reshape(ny, nx) / wm.FT) + fr.z_origin_ft
    cell = pack.cell_ft * step
    rows = []
    for p in parts:
        if p["layer"] != "roads" or p["mesh"] is None or not p["mesh"].tri_count:
            continue
        m = p["mesh"]
        T = np.concatenate([f for k, f in m.subs.items() if k != "mat_kerb"])        # the deck only: kerbs are deliberately buried at the base and may touch a cut bank
        V = m.V[T]                                           # [n, 3, 3] metres
        nz = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
        nz = nz[:, 2] / np.maximum(np.linalg.norm(nz, axis=1), 1e-12)
        V = V[np.abs(nz) > 0.8]
        S = np.concatenate([V, (V[:, 0:1] + V[:, 1:2]) / 2, (V[:, 1:2] + V[:, 2:3]) / 2, (V[:, 2:3] + V[:, 0:1]) / 2, V.mean(1, keepdims=True)], 1).reshape(-1, 3)
        x_ft, y_ft, z_ft = S[:, 0] / wm.FT, fr.height_ft - S[:, 1] / wm.FT, S[:, 2] / wm.FT + fr.z_origin_ft
        g = rg.mesh_height(Z, cell, x_ft, y_ft)
        d = z_ft - g
        e = p["entity"]
        rows.append(dict(id=e["id"], cls=e.get("class"), n=int(len(d)), min_ft=round(float(d.min()), 2), mean_ft=round(float(d.mean()), 2), max_ft=round(float(d.max()), 2),
                         buried_pct=round(100.0 * float((d < 0).mean()), 1), floating_pct=round(100.0 * float((d > 1.6).mean()), 1)))
    return rows


if __name__ == "__main__":
    import worldpack as wp
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--pack")
    ap.add_argument("--step-ft", type=float, default=4.0)
    ap.add_argument("--json")
    ap.add_argument("--mesh", choices=["legacy", "graded"], help="audit the real built meshes instead of the exported road points: legacy = old build, graded = road_grade.py defaults")
    ap.add_argument("--smooth", type=float)
    ap.add_argument("--max-grade", type=float)
    ap.add_argument("--cutfill", action="store_true")
    a = ap.parse_args()
    pack = wp.load_pack(a.pack or os.path.join(bm.WORLD, a.place, "export"))
    if a.mesh:
        rows = mesh_audit(pack, False if a.mesh == "legacy" else {"smooth": a.smooth, "max_grade_deg": a.max_grade, "cutfill": a.cutfill})
        print(f"mesh audit ({a.mesh}): terrain cell {pack.cell_ft} ft; {len(rows)} roads; depth = deck - terrain mesh, ft")
        for r in rows:
            print(f"{r['id']:<14}{str(r['cls']):<8} n {r['n']:>5}  min {r['min_ft']:>6} mean {r['mean_ft']:>6} max {r['max_ft']:>6}  buried {r['buried_pct']:>5}%  floating(>1.6ft) {r['floating_pct']:>5}%")
        if a.json:
            json.dump(rows, open(a.json, "w"), indent=1)
        sys.exit(0)
    rows = audit(pack, a.step_ft)
    print(f"terrain cell {pack.cell_ft} ft; {len(rows)} roads")
    for r in rows:
        print(f"{r['id']:<28}{r['cls']:<8} diff min {r['min_ft']:>6} mean {r['mean_ft']:>6} max {r['max_ft']:>6} ft  buried {r['buried_pct']:>5}%  floating {r['floating_pct']:>5}%  max grade {r['max_grade_deg']} deg")
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)
