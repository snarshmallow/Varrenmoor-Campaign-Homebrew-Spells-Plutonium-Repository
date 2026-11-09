"""Where a building stands on the terrain: base choice, foundation skirt depth and the terrain pad (all measured on the terrain MESH, road_grade.mesh_height).
 - resolve(poly, doors, base, h, cell) -> (base, skirt_depth): keeps the source base unless a wall would float more than max_float_ft or the ground would need
   a cut deeper than max_cut_ft; the skirt always reaches below the lowest ground under the walls (no daylight under a downhill wall).
 - pad_heights(pack, h) -> h': every building (not just interiors) gets a level pad at base - sill_ft under the footprint + eaves, blended out over a few cells,
   and a door apron in front of each exterior door, so no ground rises through walls, roofs or door sills. Cut only (never fills).
 - eave_z / eave_clearance: lowest roof edge above the ground.
Defaults are DEFAULTS; a pack may override them in manifest/building entity "ground" dicts (entity wins)."""
import math

import numpy as np

import road_grade as rg

DEFAULTS = {
    "sill_ft": 0.15,           # door sill / floor line stays at least this far above the pad (pad height = base - sill_ft)
    "max_float_ft": 1.5,       # a downhill wall may stand this far above the lowest ground before the base is lowered
    "max_cut_ft": 3.0,         # the uphill ground may be cut this deep below the base; deeper -> the base is raised (within max_float_ft)
    "skirt_extra_ft": 1.0,     # the foundation skirt reaches this far below the lowest ground under the walls
    "pad_full_cells": 1.5,     # terrain fully levelled this many cells beyond the footprint (covers the roof overhang)
    "pad_blend_cells": 4.0,    # then blended back to the natural ground over this many cells from the footprint
    "door_apron_ft": 5.0,      # door apron: level out to this distance in front of a door ...
    "door_blend_ft": 5.0,      # ... then blend out over this
    "min_eave_ft": 3.0,        # roofs must clear the ground by this much (audit/warning only)
}
FT = 0.3048


def cfg_for(e=None, base=None):
    c = dict(DEFAULTS)
    c.update(base or {})
    c.update((e or {}).get("ground") or {})
    return c


def _samples(poly, step=2.0):
    from shapely.geometry import Polygon
    import shapely
    pg = Polygon(poly)
    x0, y0, x1, y1 = pg.bounds
    X, Y = np.meshgrid(np.arange(x0, x1 + step, step), np.arange(y0, y1 + step, step))
    P = np.stack([X.ravel(), Y.ravel()], 1)
    inside = shapely.contains_xy(pg, P[:, 0], P[:, 1])
    P = P[inside] if inside.any() else np.array([pg.centroid.coords[0]])
    Q = np.asarray(poly, float)
    out = []
    for i in range(len(Q)):
        a, b = Q[i], Q[(i + 1) % len(Q)]
        n = max(1, int(math.ceil(math.hypot(*(b - a)) / 1.0)))
        out += [a + (b - a) * k / n for k in range(n)]
    return P, np.array(out)


def door_fronts(doors, dist=2.0):
    """[(x, y, fx, fy)] door points with a unit outward direction (zero when unknown)."""
    out = []
    for d in doors or []:
        px, py = d["point"]
        f = d.get("facing") or [0.0, 0.0]
        n = math.hypot(*f)
        out.append((float(px), float(py), f[0] / n if n else 0.0, f[1] / n if n else 0.0))
    return out


def resolve(poly, doors, base, h, cell, cfg=None):
    """-> (base_ft, skirt_depth_ft, report). h = terrain heights (the pad cuts later, so this is the natural ground)."""
    c = cfg_for(None, cfg)
    G, W = _samples(poly)
    tw = rg.mesh_height(h, cell, W[:, 0], W[:, 1])
    tmin, tmax = float(tw.min()), float(tw.max())
    new = float(base)
    note = None
    if new > tmin + c["max_float_ft"]:                       # wall floats too far over the downhill ground: lower the base
        new = tmin + c["max_float_ft"]
        note = "lowered (float cap)"
    if new < tmax - c["max_cut_ft"]:                         # uphill ground would need a deeper cut than allowed: raise as far as the float cap lets us
        new = max(new, min(tmax - c["max_cut_ft"], tmin + c["max_float_ft"]))
        note = "raised (cut cap)" if new > base else note
    new = round(new, 3)
    skirt = round(max(c["skirt_extra_ft"], new - tmin + c["skirt_extra_ft"]), 3)
    return new, skirt, {"changed": abs(new - base) > 1e-6, "note": note, "terrain_min_ft": round(tmin, 2), "terrain_max_ft": round(tmax, 2)}


def pad_heights(pack, h, cfg=None):
    """Level pads under every building, cut only. Returns h itself when there is nothing to do."""
    from shapely.geometry import MultiPoint, Polygon
    import shapely
    from shapely.ops import unary_union
    out = None
    cell = float(pack.cell_ft)
    ny, nx = h.shape
    for e in pack.list("buildings"):
        if not e.get("polygon"):
            continue
        c = cfg_for(e, cfg)
        pg = Polygon(e["polygon"])
        d1 = c["pad_blend_cells"] * cell
        dfull = c["pad_full_cells"] * cell
        x0, y0, x1, y1 = pg.bounds
        fronts = door_fronts((e.get("openings") or {}).get("doors"))
        ar = c["door_apron_ft"] + c["door_blend_ft"]
        j0, j1 = max(0, int((x0 - max(d1, ar)) / cell)), min(nx - 1, int((x1 + max(d1, ar)) / cell) + 1)
        i0, i1 = max(0, int((y0 - max(d1, ar)) / cell)), min(ny - 1, int((y1 + max(d1, ar)) / cell) + 1)
        if out is None:
            out = np.array(h, copy=True)
        J, I = np.meshgrid(np.arange(j0, j1 + 1), np.arange(i0, i1 + 1))
        px, py = J * cell, I * cell
        d = shapely.distance(pg, shapely.points(px.ravel(), py.ravel())).reshape(px.shape)
        t = np.clip((d - dfull) / max(d1 - dfull, 1e-6), 0.0, 1.0)
        t = np.where(d > d1, 1.0, t * t * (3 - 2 * t))
        for fx_, fy_, ux, uy in fronts:                      # door apron: a disc in front of the door, level to the sill, then a blend
            dd = np.hypot(px - (fx_ + ux * c["door_apron_ft"] * 0.5), py - (fy_ + uy * c["door_apron_ft"] * 0.5))
            ta = np.clip((dd - c["door_apron_ft"] * 0.5) / max(c["door_blend_ft"], 1e-6), 0.0, 1.0)
            ta = ta * ta * (3 - 2 * ta)
            t = np.minimum(t, ta)
        fl = float(e["base_elevation_ft"]) - c["sill_ft"]
        cur = out[i0:i1 + 1, j0:j1 + 1]
        tgt = fl * (1 - t) + cur * t
        out[i0:i1 + 1, j0:j1 + 1] = np.where(tgt < cur, tgt, cur)
    return h if out is None else out


def final_skirt(e, h, cell, cfg=None):
    """Skirt depth (ft) against the FINAL terrain mesh h (after pads, door aprons, road grading and painted edits). resolve() only sees the natural ground, but the
    pad of a lower neighbour (or a painted cut) can lower the ground under this footprint afterwards; the skirt must reach below that too. Never shallower than e's."""
    c = cfg_for(e, cfg)
    G, W = _samples(e["polygon"])
    tmin = float(rg.mesh_height(h, cell, W[:, 0], W[:, 1]).min())
    need = float(e["base_elevation_ft"]) - tmin + c["skirt_extra_ft"]
    return round(max(float(e.get("skirt_depth_ft") or 0.0), need), 3)


def with_final_skirt(e, h, cell, cfg=None):
    """e itself when its skirt already reaches below the final ground, else a copy with the deeper skirt."""
    if not e.get("polygon"):
        return e
    s = final_skirt(e, h, cell, cfg)
    return e if s <= float(e.get("skirt_depth_ft") or 0.0) + 1e-6 else dict(e, skirt_depth_ft=s)


def eave_z(e):
    """Lowest roof edge (ft, absolute) of the plain building roof: the wall top minus the overhang drop. Style roofs may hang lower (see the audit)."""
    r = e.get("roof") or {}
    o = e.get("obb") or {}
    zt = float(e["base_elevation_ft"]) + float(e["wall_height_ft"])
    half = max(float(o.get("width_ft", 10.0)) / 2, 1e-6)
    return zt - float(r.get("overhang_ft", 1.0)) * float(r.get("ridge_height_ft", 0.0)) / half


def eave_clearance(e, h, cell):
    """Lowest roof edge above the highest ground within the footprint + overhang (ft)."""
    from shapely.geometry import Polygon
    ov = float((e.get("roof") or {}).get("overhang_ft", 1.0))
    G, W = _samples(list(Polygon(e["polygon"]).buffer(ov).exterior.coords)[:-1])
    return eave_z(e) - float(rg.mesh_height(h, cell, W[:, 0], W[:, 1]).max())
