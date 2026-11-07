"""Terrain-fitted town area ("auto lasso") and nested ring zones (deterministic by seed).

  python illustrator/generators/town_area.py --place bridgehollow [--mode auto|snap] [--params PATH] [--seed N]
        [--slope-limit 0.13] [--river-buffer 14] [--smoothing 55] [--min-width 90] [--noise 22] [--target-area 900000]
        [--out area.json] [--svg area.svg --view town ...] [--write-params]

auto : buildable mask (slope under a limit, not floodplain, river corridor kept so the town spans both banks) ->
       connected region round the centre, trimmed by a terrain-cost distance so it hugs the flat valley floor ->
       morphological open/close -> Gaussian-smoothed signed distance field + low-frequency boundary wobble ->
       marching-squares contour at zero -> arclength resample + Chaikin -> an organic closed polygon with no straight
       runs or corners (bulges into bays, pinches at narrow spots, follows the foot of the valley sides).
snap : the same machinery applied to a rough user lasso: the lasso (slightly grown) is intersected with the buildable
       mask and re-smoothed, so a hand-drawn shape settles onto the terrain contours.
A lasso drawn by hand is otherwise used as is by town_gen.py (`area_mode: "manual"`, the default when `area_ft` is set).

Rings: `ring_field` is a terrain-cost geodesic distance from the town centre (steeper ground costs more, so rings
stretch along the flat floor and pinch against the valley sides) with low-frequency noise. Ring polygons are contours of
that field (authority core, commoners' ring) clipped to the area; the farm fringe is the remainder of the area. town_gen
uses the same field for ring assignment (`ring_spec.mode: "terrain"`), so streets, lots and fields follow these shapes.
Everything is feet, y down.
"""
import argparse
import json
import math
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from scipy import sparse
from scipy.sparse import csgraph
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

DEFAULTS = {
    "seed": 1,
    "centre": None,               # [x, y] ft; defaults to ring_spec.centre or the middle of the flat floor
    "slope_limit": 0.13,          # max smoothed slope (rise/run) that counts as buildable
    "slope_sigma_ft": 15.0,       # heightmap smoothing before the slope is taken
    "river_buffer_ft": 14.0,      # water + this buffer stays inside the area (the town spans the river via bridges)
    "flood_rise_ft": 0.8,         # ground lower than the nearby water surface + this is floodplain: excluded
    "flood_reach_ft": 90.0,
    "gorge_buffer_ft": 20.0,      # keep this far from ground steeper than `hard_slope`
    "hard_slope": 0.30,
    "smoothing_ft": 55.0,         # Gaussian sigma of the signed-distance smoothing (bigger = rounder)
    "min_width_ft": 150.0,         # necks narrower than this are removed
    "noise_ft": 22.0,             # amplitude of the boundary wobble
    "noise_period_ft": 260.0,
    "area_scale": 1.0,            # multiplies target_area_ft2 (2.0 = twice the town area, as far as the buildable ground reaches)
    "target_area_ft2": 900000.0,  # outer extent is trimmed to about this area (None: no trim)
    "slope_cost": 1.4,            # extra terrain cost per (slope/limit)^2 when growing outward from the centre
    "vertex_spacing_ft": 36.0,    # editable outline vertex spacing
    "grow_ft": 45.0,              # snap mode: how far a rough lasso may grow outward onto buildable ground
}


# ====================================================================== grids
def _smooth_noise(rng, shape, period_cells):
    ny, nx = shape
    gy, gx = int(ny / period_cells) + 3, int(nx / period_cells) + 3
    g = rng.uniform(-1, 1, (gy, gx))
    z = ndi.zoom(g, (ny / (gy - 1), nx / (gx - 1)), order=3, mode="nearest")[:ny, :nx]
    if z.shape != shape:
        z = np.pad(z, ((0, ny - z.shape[0]), (0, nx - z.shape[1])), mode="edge")
    m = np.abs(z).max()
    return z / m if m else z


def raster_poly(geom, nx, ny, cell):
    from PIL import Image, ImageDraw
    img = Image.new("L", (nx, ny), 0)
    d = ImageDraw.Draw(img)
    for g in getattr(geom, "geoms", [geom]):
        if g.is_empty or not isinstance(g, Polygon):
            continue
        d.polygon([(x / cell, y / cell) for x, y in g.exterior.coords], fill=1)
        for hole in g.interiors:
            d.polygon([(x / cell, y / cell) for x, y in hole.coords], fill=0)
    return np.array(img, dtype=bool)


def terrain_grids(h, cell, wet, P):
    """slope (smoothed), buildable mask, floodplain mask. `wet` = bool raster of water."""
    hs = ndi.gaussian_filter(h.astype(float), max(P["slope_sigma_ft"] / cell, 0.5), mode="nearest")
    gy, gx = np.gradient(hs, cell)
    slope = np.hypot(gx, gy)
    ok = slope < P["slope_limit"]
    # gorge walls: keep a buffer off really steep ground
    if P["gorge_buffer_ft"] > 0:
        steep = slope > P["hard_slope"]
        ok &= ndi.distance_transform_edt(~steep) * cell > P["gorge_buffer_ft"]
    # floodplain: low ground beside the water surface (surface = nearest wet cell height)
    flood = np.zeros_like(ok)
    if wet.any() and P["flood_rise_ft"] > 0:
        d, idx = ndi.distance_transform_edt(~wet, return_indices=True)
        surf = ndi.gaussian_filter(h.astype(float), 1.0)[idx[0], idx[1]]
        flood = (d * cell < P["flood_reach_ft"]) & (hs < surf + P["flood_rise_ft"]) & ~wet
    # the river corridor stays available (town spans it); its carved banks are steep so force it in
    keep = ndi.distance_transform_edt(~wet) * cell <= P["river_buffer_ft"] if wet.any() else np.zeros_like(ok)
    ok = (ok & ~flood) | keep
    slope = np.where(keep, np.minimum(slope, 0.5 * P["slope_limit"]), slope)      # bridged river corridor: cheap to cross
    return hs, slope, ok, flood


def cost_grid(slope, P):
    return 1.0 + P["slope_cost"] * np.clip(slope / P["slope_limit"], 0, 4.0) ** 2


def geodesic(cost, cell, src):
    """Terrain-cost distance (ft-equivalent) from grid cell `src`=(i,j) over a 16-neighbour graph (low anisotropy)."""
    ny, nx = cost.shape
    idx = np.arange(ny * nx).reshape(ny, nx)
    rows, cols, wts = [], [], []
    moves = [(0, 1), (1, 0), (1, 1), (1, -1), (1, 2), (2, 1), (1, -2), (2, -1)]
    for di, dj in moves:
        i0, i1 = max(0, -di), ny - max(0, di)
        if dj >= 0:
            j0, j1 = 0, nx - dj
        else:
            j0, j1 = -dj, nx
        a = idx[i0:i1, j0:j1]
        b = idx[i0 + di:i1 + di, j0 + dj:j1 + dj]
        w = 0.5 * (cost[i0:i1, j0:j1] + cost[i0 + di:i1 + di, j0 + dj:j1 + dj]) * math.hypot(di, dj) * cell
        rows.append(a.ravel()); cols.append(b.ravel()); wts.append(w.ravel())
    g = sparse.csr_matrix((np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(ny * nx, ny * nx))
    d = csgraph.dijkstra(g, directed=False, indices=int(idx[src]))
    return d.reshape(ny, nx)


def ring_field(h, cell, wet, centre, P, seed, noise=0.12, noise_period_ft=320.0, smooth_cells=3.0):
    """Terrain-cost distance from the centre, smoothed, times (1 + noise*n). Ring radii compare against this."""
    hs, slope, ok, flood = terrain_grids(h, cell, wet, P)
    cost = cost_grid(slope, P)
    ny, nx = h.shape
    src = (min(max(int(round(centre[1] / cell)), 0), ny - 1), min(max(int(round(centre[0] / cell)), 0), nx - 1))
    D = ndi.gaussian_filter(geodesic(cost, cell, src), smooth_cells, mode="nearest")
    rng = np.random.default_rng(int(seed) + 7919)
    n = _smooth_noise(rng, (ny, nx), noise_period_ft / cell)
    return D * (1.0 + noise * n)


# ====================================================================== contour -> polygon
def _polys_from_lines(lines):
    out = []
    for a in lines:
        if np.allclose(a[0], a[-1]) and len(a) > 5:
            p = Polygon(a).buffer(0)
            if not p.is_empty:
                out.append(p)
    return out


def _largest_containing(polys, pt):
    P = Point(pt)
    cont = [p for p in polys if p.contains(P)]
    pool = cont or polys
    return max(pool, key=lambda p: p.area) if pool else None


def smooth_ring(pts, n=1):
    pts = [tuple(p) for p in pts]
    for _ in range(n):
        m = len(pts)
        out = []
        for i in range(m):
            a, b = pts[i], pts[(i + 1) % m]
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        pts = out
    return pts


def resample_closed(pts, spacing):
    ring = LineString(list(pts) + [pts[0]])
    n = max(int(round(ring.length / spacing)), 8)
    return [ring.interpolate(i * ring.length / n).coords[0] for i in range(n)]


def outline(poly, spacing, chaikin=1):
    """Closed polygon -> editable vertex list, evenly spaced, Chaikin-smoothed, CCW-agnostic, no repeat vertex."""
    ext = list(poly.exterior.coords)[:-1]
    pts = resample_closed(ext, spacing * 0.6)
    pts = smooth_ring(pts, chaikin)
    pts = resample_closed(pts, spacing)
    return [(round(x, 1), round(y, 1)) for x, y in pts]


def _padded_lines(field, cell, level, pad_value, up=3):
    """Contour lines of `field` (upsampled x up) with a border of `pad_value` so regions touching the map edge close."""
    import contourpy
    pad = 3
    f = np.pad(field, pad, mode="constant", constant_values=pad_value)
    ny, nx = f.shape
    z = ndi.zoom(f, up, order=3, mode="nearest")
    xs = (np.arange(z.shape[1]) * ((nx - 1) / (z.shape[1] - 1)) - pad) * cell
    ys = (np.arange(z.shape[0]) * ((ny - 1) / (z.shape[0] - 1)) - pad) * cell
    return contourpy.contour_generator(xs, ys, z).lines(level)


def field_polygon(mask_sdf, cell, centre, spacing, up=3):
    """Zero contour of a signed-distance-like field (positive inside), upsampled x`up` for a smooth line."""
    p = _largest_containing(_polys_from_lines(_padded_lines(mask_sdf, cell, 0.0, -2.0 * cell, up)), centre)
    return None if p is None else Polygon(p.exterior)          # fill holes


# ====================================================================== area builders
def _sdf(mask, cell):
    return (ndi.distance_transform_edt(mask) - ndi.distance_transform_edt(~mask)) * cell


def _open_close(mask, cell, min_width_ft):
    r = max(int(round(min_width_ft / 2.0 / cell)), 1)
    st = ndi.generate_binary_structure(2, 1)
    st = ndi.iterate_structure(st, r)
    m = ndi.binary_opening(mask, st)
    m = ndi.binary_closing(m, ndi.iterate_structure(ndi.generate_binary_structure(2, 1), max(r // 2, 1)))
    return m


def _component_at(mask, centre, cell):
    lab, n = ndi.label(mask)
    if n == 0:
        return mask
    ci, cj = int(round(centre[1] / cell)), int(round(centre[0] / cell))
    ci, cj = min(max(ci, 0), mask.shape[0] - 1), min(max(cj, 0), mask.shape[1] - 1)
    l = lab[ci, cj]
    if l == 0:       # centre not buildable: nearest buildable cell
        d, ind = ndi.distance_transform_edt(lab == 0, return_indices=True)
        l = lab[ind[0][ci, cj], ind[1][ci, cj]]
    return lab == l


def default_centre(h, cell, ok):
    d = ndi.distance_transform_edt(ok) * cell
    d = ndi.gaussian_filter(d, 3)
    i, j = np.unravel_index(int(np.argmax(d)), d.shape)
    return [j * cell, i * cell]


def _finish(mask, h, cell, centre, P, rng_seed):
    """mask -> smoothed, wobbled, polygon (shapely) + vertex list."""
    ny, nx = mask.shape
    m = _component_at(_open_close(mask, cell, P["min_width_ft"]), centre, cell)
    m = ndi.binary_fill_holes(m)
    pd = 4
    sdf = _sdf(np.pad(m, pd, constant_values=False), cell)
    sdf = ndi.gaussian_filter(sdf, max(P["smoothing_ft"] / cell, 0.5), mode="nearest")[pd:-pd, pd:-pd]
    rng = np.random.default_rng(int(rng_seed) + 104729)
    sdf = sdf + P["noise_ft"] * _smooth_noise(rng, (ny, nx), P["noise_period_ft"] / cell)
    # re-open after the wobble so no thin tongue survives, then take the piece at the centre
    poly = field_polygon(sdf, cell, centre, P["vertex_spacing_ft"])
    if poly is None:
        raise SystemExit("terrain area: no buildable region found around the centre (raise slope_limit?)")
    pts = outline(poly, P["vertex_spacing_ft"])
    return Polygon(pts).buffer(0), pts


def auto_area(h, cell, wet, centre, P):
    """-> (polygon, vertex list, info). `centre` in ft."""
    hs, slope, ok, flood = terrain_grids(h, cell, wet, P)
    comp = _component_at(_open_close(ok, cell, P["min_width_ft"]), centre, cell)
    cost = cost_grid(slope, P)
    ny, nx = h.shape
    src = (min(max(int(round(centre[1] / cell)), 0), ny - 1), min(max(int(round(centre[0] / cell)), 0), nx - 1))
    D = geodesic(np.where(comp, cost, cost * 6.0), cell, src)
    mask = comp
    dcut = None
    if P.get("target_area_ft2"):
        tgt = float(P["target_area_ft2"]) * float(P.get("area_scale") or 1.0)
        lo, hi = 0.0, float(D[comp].max())
        if comp.sum() * cell * cell > tgt:
            for _ in range(28):
                mid = 0.5 * (lo + hi)
                if (comp & (D <= mid)).sum() * cell * cell > tgt:
                    hi = mid
                else:
                    lo = mid
            dcut = 0.5 * (lo + hi)
            mask = comp & (D <= dcut)
    poly, pts = _finish(mask, h, cell, centre, P, P["seed"])
    return poly, pts, {"buildable_ft2": float(ok.sum() * cell * cell), "component_ft2": float(comp.sum() * cell * cell),
                       "cost_cut": dcut}


def snap_area(h, cell, wet, user_pts, centre, P):
    """Settle a rough user lasso onto the buildable terrain."""
    ny, nx = h.shape
    hs, slope, ok, flood = terrain_grids(h, cell, wet, P)
    user = Polygon(user_pts).buffer(0)
    if P["grow_ft"] > 0:
        user = user.buffer(P["grow_ft"])
    um = raster_poly(user, nx, ny, cell)
    mask = um & ok
    if not mask.any():
        raise SystemExit("snap: the lasso covers no buildable ground")
    if centre is None or not Polygon(user_pts).contains(Point(centre)):
        c = Polygon(user_pts).buffer(0).representative_point()
        # prefer the buildable cell deepest inside the lasso
        d = ndi.distance_transform_edt(mask)
        i, j = np.unravel_index(int(np.argmax(d)), d.shape)
        centre = [j * cell, i * cell]
    poly, pts = _finish(mask, h, cell, centre, P, P["seed"])
    return poly, pts, {"lasso_ft2": float(Polygon(user_pts).area)}


def rings_from_field(R, cell, centre, area, rings, spacing):
    """Ring polygons (all but the last) as nested contours of R clipped to `area`. -> {ring_id: pts}"""
    Rs = ndi.gaussian_filter(R, 1.5)
    out = {}
    for r in rings[:-1]:
        p = _largest_containing(_polys_from_lines(_padded_lines(Rs, cell, float(r["r_max"]), float(Rs.max()) * 2)), centre)
        if p is None:
            continue
        p = Polygon(p.exterior).intersection(area)
        if p.geom_type != "Polygon":
            p = max(getattr(p, "geoms", []), key=lambda g: g.area, default=None)
        if p is None or p.is_empty:
            continue
        out[r["id"]] = [(round(x, 1), round(y, 1)) for x, y in resample_closed(list(p.exterior.coords)[:-1], spacing)]
    return out


# ====================================================================== high-level API
def merged(params):
    P = dict(DEFAULTS)
    P.update({k: v for k, v in (params or {}).items() if k in DEFAULTS and (v is not None or k in ("target_area_ft2", "centre"))})
    sc = float(P.get("area_scale") or 1.0)
    if sc > 1.0:       # a bigger town also has to climb the valley sides: relax the buildable slope with the scale (capped well below the gorge limit)
        P["slope_limit"] = min(P["slope_limit"] * sc, 0.28)
    return P


def build(h, meta, water_poly, params, centre=None, user_pts=None, rings=None):
    """-> dict(area_ft, rings_ft, centre, params, stats). water_poly: shapely geometry (may be empty).
    mode snap when user_pts is given."""
    cell = float(meta["cell_ft"])
    ny, nx = h.shape
    P = merged(params)
    sea = float(meta.get("sea_level_ft", 0.0))
    wet = raster_poly(water_poly, nx, ny, cell) if water_poly is not None and not water_poly.is_empty else np.zeros((ny, nx), bool)
    wet |= h < sea
    if centre is None:
        centre = P["centre"]
    if centre is None:
        centre = default_centre(h, cell, terrain_grids(h, cell, wet, P)[2])
    if user_pts:
        poly, pts, info = snap_area(h, cell, wet, user_pts, centre, P)
    else:
        poly, pts, info = auto_area(h, cell, wet, centre, P)
    out = {"area_ft": [list(p) for p in pts], "centre": [round(float(centre[0]), 1), round(float(centre[1]), 1)],
           "mode": "snap" if user_pts else "auto", "params": P, "info": info}
    if rings:
        R = ring_field(h, cell, wet, centre, P, P["seed"])
        out["rings_ft"] = {k: [list(p) for p in v] for k, v in rings_from_field(R, cell, centre, poly, rings, P["vertex_spacing_ft"]).items()}
    out["stats"] = stats(h, cell, poly, P)
    return out


def stats(h, cell, poly, P):
    hs = ndi.gaussian_filter(h.astype(float), max(P["slope_sigma_ft"] / cell, 0.5), mode="nearest")
    sl = np.hypot(*np.gradient(hs, cell))
    ny, nx = h.shape
    m = raster_poly(poly, nx, ny, cell)
    s = sl[m]
    pts = list(poly.exterior.coords)[:-1]
    return {"area_ft2": round(poly.area), "perimeter_ft": round(poly.length), "vertices": len(pts),
            "compactness": round(4 * math.pi * poly.area / poly.length ** 2, 3),
            "slope_mean": round(float(s.mean()), 3), "slope_p90": round(float(np.percentile(s, 90)), 3),
            "frac_over_limit": round(float((s > P["slope_limit"]).mean()), 3),
            "max_turn_deg": round(max_turn_deg(pts), 1), "bounds": [round(v) for v in poly.bounds]}


def turn_angles(pts):
    n = len(pts)
    out = []
    for i in range(n):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % n]
        v1, v2 = (b[0] - a[0], b[1] - a[1]), (c[0] - b[0], c[1] - b[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cs = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        out.append(math.degrees(math.acos(cs)))
    return out


def max_turn_deg(pts):
    t = turn_angles(pts)
    return max(t) if t else 0.0


# ====================================================================== io / cli
def load_inputs(place, params):
    import worldio
    import terrain as tr
    import town_gen as tg
    h, meta = tr.load_heightmap(place)
    water = tg.load_water(worldio.world_dir(place), worldio.water_path(place))
    return h.astype(float), meta, water.polygon


def svg_for_panel(res, view_args, path_out):
    """Write the editable 'TOWN AREA' layer (closed path 'Town area') plus an informational 'TOWN AREA RINGS' layer."""
    import render_world as rw
    from lib_svg import LayerTree
    model = rw.load_place(view_args["place"])
    v, cfg, title, kind, ident = rw.compute_view(model, view_args["view"], {k: view_args.get(k) for k in ("preset", "scale", "grid", "page", "major_every")})
    pw, ph = cfg["page_in"]
    t = LayerTree([("TOWN AREA RINGS", []), ("TOWN AREA", [])], pw, ph,
                  css="path { fill: none; } .area { fill: none; stroke: #c1272d; stroke-width: 1.25; } .ring { fill: none; stroke: #c1272d; stroke-width: 0.6; stroke-dasharray: 4 3; }")
    t.add("TOWN AREA", f'<path id="Town area" class="area" fill="none" d="{v.d([res["area_ft"]])}"/>')
    for k, pts in res.get("rings_ft", {}).items():
        t.add("TOWN AREA RINGS", f'<path id="Ring {k}" class="ring" fill="none" d="{v.d([pts])}"/>')
    t.write(path_out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--mode", choices=["auto", "snap"], default="auto")
    ap.add_argument("--params", help="town_params.json (centre, rings, area_auto, area_ft for snap)")
    ap.add_argument("--lasso", help="JSON file with a list of [x,y] (snap mode; default town_params area_ft)")
    ap.add_argument("--seed", type=int)
    for k, v in DEFAULTS.items():
        if k not in ("seed", "centre") and v is not None:
            ap.add_argument("--" + k.replace("_", "-"), type=float)
    ap.add_argument("--target-area", type=float, dest="target_area_ft2")
    ap.add_argument("--min-width", type=float, dest="min_width_ft")
    ap.add_argument("--smoothing", type=float, dest="smoothing_ft")
    ap.add_argument("--noise", type=float, dest="noise_ft")
    ap.add_argument("--river-buffer", type=float, dest="river_buffer_ft")
    ap.add_argument("--centre", type=float, nargs=2)
    ap.add_argument("--out")
    ap.add_argument("--svg")
    ap.add_argument("--write-params", action="store_true", help="store area_ft (+ area_auto params) back into town_params.json")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale")
    ap.add_argument("--grid")
    ap.add_argument("--grid-major", dest="major_every")
    ap.add_argument("--page")
    a = ap.parse_args()
    ppath = a.params or os.path.join(REPO, "world", a.place, "town_params.json")
    tp = json.load(open(ppath, encoding="utf-8")) if os.path.exists(ppath) else {}
    params = dict(tp.get("area_auto") or {})
    for k in DEFAULTS:
        v = getattr(a, k, None)
        if v is not None:
            params[k] = v
    if a.seed is None:
        params.setdefault("seed", tp.get("seed", 1))
    else:
        params["seed"] = a.seed
    h, meta, water = load_inputs(a.place, params)
    centre = a.centre or params.get("centre") or (tp.get("ring_spec") or {}).get("centre")
    user = None
    if a.mode == "snap":
        user = json.load(open(a.lasso, encoding="utf-8")) if a.lasso else tp.get("area_ft")
        if not user:
            raise SystemExit("snap needs a lasso (--lasso file or area_ft in the params)")
    rings = (tp.get("ring_spec") or {}).get("rings")
    res = build(h, meta, water, params, centre, user, rings)
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(res, open(a.out, "w", encoding="utf-8"), indent=1)
    if a.svg:
        svg_for_panel(res, {"place": a.place, "view": a.view, "preset": a.preset, "scale": a.scale, "grid": a.grid,
                            "page": a.page, "major_every": a.major_every}, a.svg)
    if a.write_params:
        tp["area_ft"] = res["area_ft"]
        tp["area_auto"] = {k: v for k, v in params.items() if k in DEFAULTS}
        tp["area_mode"] = "manual"          # the stored polygon is now the lasso
        json.dump(tp, open(ppath, "w", encoding="utf-8"), indent=1)
        open(ppath, "a").write("\n")
    print(json.dumps({k: res[k] for k in ("area_ft", "rings_ft", "centre", "mode", "stats") if k in res}))


if __name__ == "__main__":
    main()
