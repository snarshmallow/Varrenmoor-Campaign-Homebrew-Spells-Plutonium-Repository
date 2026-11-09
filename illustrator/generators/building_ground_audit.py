"""Quantify how every building sits on the terrain MESH of an exported world pack (the surface the player sees, same sampling as road_height_audit).
Per building: base elevation used, min/max terrain under the footprint (grid + outline), wall burial (terrain above the base along the walls), floating gap
(base above terrain along the walls, before the skirt), door sill vs terrain at each door and 2 ft in front of it, lowest roof/eave point above ground.
  python illustrator/generators/building_ground_audit.py --place bridgehollow__dyers_walk_local [--json out.json] [--no-mesh]
Eave clearance needs the built meshes (slower); --no-mesh skips it."""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

FT = 0.3048
NOT_ROOF = ("beam", "glass", "brick", "plaster", "ceiling", "joist", "floor", "hearth", "ember", "furn", "iron", "plank", "stone", "timber", "wood")


def _grid(poly, step=2.0):
    from shapely.geometry import Point, Polygon
    pg = Polygon(poly)
    x0, y0, x1, y1 = pg.bounds
    pts = [(x, y) for x in np.arange(x0, x1 + step, step) for y in np.arange(y0, y1 + step, step) if pg.contains(Point(x, y))]
    return np.array(pts if pts else [pg.centroid.coords[0]], float)


def _outline(poly, step=1.0):
    P = np.asarray(poly, float)
    out = []
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        n = max(1, int(math.ceil(math.hypot(*(b - a)) / step)))
        out += [a + (b - a) * k / n for k in range(n)]
    return np.array(out)


def audit_building(e, h, cell, rg):
    """One building against the terrain heights h (same grid as the pack). -> dict of numbers in feet."""
    base = float(e["base_elevation_ft"])
    poly = e["polygon"]
    G, W = _grid(poly), _outline(poly)
    tg, tw = rg.mesh_height(h, cell, G[:, 0], G[:, 1]), rg.mesh_height(h, cell, W[:, 0], W[:, 1])
    doors = []
    for d in (e.get("openings") or {}).get("doors", []):
        px, py = d["point"]
        f = d.get("facing") or [0.0, 0.0]
        n = math.hypot(*f) or 1.0
        t0 = float(rg.mesh_height(h, cell, px, py))
        t2 = float(rg.mesh_height(h, cell, px + f[0] / n * 2.0, py + f[1] / n * 2.0))
        doors.append({"id": d["id"], "terrain_ft": round(t0, 2), "sill_minus_terrain_ft": round(base - t0, 2), "front2ft_terrain_ft": round(t2, 2), "front_sill_minus_terrain_ft": round(base - t2, 2)})
    return {"id": e["id"], "style": e.get("style"), "roof": (e.get("roof") or {}).get("type"), "base_ft": round(base, 2), "skirt_ft": e.get("skirt_depth_ft"),
            "terr_min_ft": round(float(min(tg.min(), tw.min())), 2), "terr_max_ft": round(float(max(tg.max(), tw.max())), 2),
            "terr_mean_ft": round(float(tg.mean()), 2),
            "wall_burial_ft": round(float(max(0.0, (tw - base).max())), 2),             # terrain above the floor line along the walls (wall base hidden / door buried)
            "wall_gap_ft": round(float(max(0.0, (base - tw).max())), 2),                # floor line above terrain along the walls (the skirt must cover this)
            "skirt_short_ft": round(float(max(0.0, (base - tw).max() - float(e.get("skirt_depth_ft") or 0.0))), 2),   # gap deeper than the skirt: daylight under the wall
            "interior_burial_ft": round(float(max(0.0, (tg - base).max())), 2),
            "doors": doors, "min_door_clear_ft": round(min([d["sill_minus_terrain_ft"] for d in doors] + [d["front_sill_minus_terrain_ft"] for d in doors]), 2) if doors else None}


def eave_clearance(pack, h, rows):
    """Lowest roof-slope vertex above the terrain mesh, from the real built building meshes (slow part)."""
    import worldpack_mesh as wm
    import road_grade as rg
    parts = wm.build_parts(pack, step=1, layers={"buildings"})
    fr = pack.frame
    by = {r["id"]: r for r in rows}
    for p in parts:
        if p["layer"] != "buildings" or p["mesh"] is None or p["id"] not in by:
            continue
        e = p["entity"]
        m = p["mesh"]
        T = np.concatenate(list(m.subs.values()))
        V = m.V[T]
        nrm = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
        nz = nrm[:, 2] / np.maximum(np.linalg.norm(nrm, axis=1), 1e-12)
        zf = (e["base_elevation_ft"] - fr.z_origin_ft) * FT
        zc = V[:, :, 2].mean(1)
        zt = zf + e["wall_height_ft"] * FT
        sel = np.zeros(len(T), bool)
        off = 0
        for k, tri in m.subs.items():                                                                      # roof planes: sloped faces at/above the wall top, not beams/glass/brick/plaster
            n = len(tri)
            if not any(w in k for w in NOT_ROOF):
                sel[off:off + n] = True
            off += n
        sel &= (np.abs(nz) > 0.15) & (np.abs(nz) < 0.95) & (zc > zt - 1.5 * FT)
        if not sel.any():
            continue
        Q = V[sel].reshape(-1, 3)
        x, y, z = Q[:, 0] / FT, fr.height_ft - Q[:, 1] / FT, Q[:, 2] / FT + fr.z_origin_ft
        d = z - rg.mesh_height(h, pack.cell_ft, x, y)
        by[p["id"]]["eave_clear_ft"] = round(float(d.min()), 2)
        by[p["id"]]["roof_low_z_above_base_ft"] = round(float(z.min() - e["base_elevation_ft"]), 2)


def audit(pack, with_mesh=True):
    import worldpack_mesh as wm
    import road_grade as rg
    h = wm.final_heights(pack)
    import building_ground as bg
    rows = [audit_building(bg.with_final_skirt(e, h, pack.cell_ft), h, pack.cell_ft, rg) for e in pack.list("buildings")]
    if with_mesh:
        eave_clearance(pack, h, rows)
    return rows


def summary_line(r):
    return (f"{r['id']:<18}{str(r['style']):<12}base {r['base_ft']:>7} terr {r['terr_min_ft']:>7}..{r['terr_max_ft']:<7} burial {r['wall_burial_ft']:>5} gap {r['wall_gap_ft']:>5} "
            f"skirt_short {r['skirt_short_ft']:>5} door_clear {r['min_door_clear_ft']}  eave {r.get('eave_clear_ft')}")


if __name__ == "__main__":
    import worldpack as wp
    import bridge_maker as bm
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True)
    ap.add_argument("--pack")
    ap.add_argument("--json")
    ap.add_argument("--no-mesh", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    pack = wp.load_pack(a.pack or os.path.join(bm.WORLD, a.place, "export"))
    rows = audit(pack, not a.no_mesh)
    print(f"{len(rows)} buildings; terrain cell {pack.cell_ft} ft")
    for title, key in (("worst wall burial", "wall_burial_ft"), ("worst floating gap", "wall_gap_ft"), ("worst interior burial", "interior_burial_ft")):
        print(f"-- {title}")
        for r in sorted(rows, key=lambda r: -r[key])[:a.top]:
            print("  " + summary_line(r))
    print("-- worst door clearance (sill - terrain, ft; < 0.15 = buried)")
    for r in sorted([r for r in rows if r["min_door_clear_ft"] is not None], key=lambda r: r["min_door_clear_ft"])[:a.top]:
        print("  " + summary_line(r))
    if not a.no_mesh:
        print("-- lowest eaves (roof vertex above terrain, ft)")
        for r in sorted([r for r in rows if "eave_clear_ft" in r], key=lambda r: r["eave_clear_ft"])[:a.top]:
            print("  " + summary_line(r))
    if a.json:
        json.dump(rows, open(a.json, "w"), indent=1)
