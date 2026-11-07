"""Hydrology on a signed-elevation heightmap: sea, lakes, rivers, carving, crossings, SVG layer data.

  python water.py analyze   --place bridgehollow [--threshold-cells 150] [--outlet-width 60] [--delta] ...
  python water.py carve     --place bridgehollow [--bank-ft 12]
  python water.py add-river --place bridgehollow --points "x,y;x,y;..." [--join wat_id] [--width 10] [--depth 1.5] [--flow 8] [--carve]
  python water.py add-lake  --place bridgehollow (--circle x,y,r | --polygon "x,y;...") [--level ft] [--depth ft]
  python water.py crossings --place bridgehollow [--street id | --polyline "x,y;..."]
  python water.py svg       --place bridgehollow [--feet-per-inch 100]
  python water.py verify    --place bridgehollow
  python water.py selftest

Units are feet, signed elevation against `sea_level_ft` (terrain_meta.json, default 0); negative elevations are normal.
Grid convention is terrain.py's: h[i, j] at x = j*cell, y = i*cell (y down).
The base heightmap and world/<place>/water.json are never overwritten (unless --inplace for water.json); results go to
illustrator/out/water/<place>/ : water.json (working file), heightmap_carved.npy, water_depth.npy/png, flow_acc.npy,
previews, crossings.json, water_fragment.svgfrag.

Library use from render_world.py later:
    import water
    water.add_water_to_tree(tree, water_entries, px)   # px(x_ft, y_ft) -> (x_pt, y_pt); adds to LayerTree layer "Water"
    css += water.WATER_CSS
"""
import argparse
import heapq
import json
import math
import os
import sys

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_ROOT = os.path.join(HERE, "..", "out", "water")

NB8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

# hydraulic geometry: width = W_COEF * Q^0.5, depth = D_COEF * Q^0.4  (Q in cfs, feet)
W_COEF, D_COEF = 4.0, 0.35


# ------------------------------------------------------------------ small helpers
class Grid:
    """Heightmap plus geometry helpers."""

    def __init__(self, h, cell, sea_level=0.0):
        self.h = np.asarray(h, dtype=float)
        self.cell = float(cell)
        self.ny, self.nx = self.h.shape
        self.sea = float(sea_level)
        self.W, self.H = (self.nx - 1) * self.cell, (self.ny - 1) * self.cell

    def sample(self, pts, arr=None):
        a = self.h if arr is None else arr
        p = np.asarray(pts, float).reshape(-1, 2)
        return ndi.map_coordinates(a, [p[:, 1] / self.cell, p[:, 0] / self.cell], order=1, mode="nearest")

    def xy(self, idx):
        i, j = divmod(int(idx), self.nx)
        return j * self.cell, i * self.cell

    def coords(self):
        y, x = np.mgrid[0:self.ny, 0:self.nx]
        return x * self.cell, y * self.cell

    def mask_polygon(self, poly):
        """Boolean raster of cells whose node lies inside a shapely polygon."""
        from PIL import Image, ImageDraw
        s = 4
        img = Image.new("L", (self.nx * s, self.ny * s), 0)
        d = ImageDraw.Draw(img)
        polys = list(poly.geoms) if isinstance(poly, MultiPolygon) else [poly]
        for p in polys:
            d.polygon([(x / self.cell * s + s / 2, y / self.cell * s + s / 2) for x, y in p.exterior.coords], fill=255)
            for r in p.interiors:
                d.polygon([(x / self.cell * s + s / 2, y / self.cell * s + s / 2) for x, y in r.coords], fill=0)
        a = np.asarray(img)[s // 2::s, s // 2::s][:self.ny, :self.nx]
        return a > 127


def load_grid(place, root=None, sea_level=None, offset=0.0):
    if root is None:   # shared loader: carve and analyse the patched terrain (never the carved result itself)
        sys.path.insert(0, HERE)
        import worldio
        h, meta = worldio.load_terrain(place, source="patched")
        h = h.astype(float) + offset
    else:
        d = os.path.join(root, place, "terrain")
        h = np.load(os.path.join(d, "heightmap.npy")).astype(float) + offset
        meta = json.load(open(os.path.join(d, "terrain_meta.json"), encoding="utf-8"))
    sl = meta.get("sea_level_ft", 0.0) if sea_level is None else sea_level
    return Grid(h, meta["cell_ft"], sl), meta


def parse_pts(s):
    return [[float(v) for v in p.split(",")] for p in s.replace(" ", "").split(";") if p]


def r1(v, n=2):
    return round(float(v), n)


def arclen(pts):
    p = np.asarray(pts, float)
    return np.concatenate([[0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))]) if len(p) > 1 else np.zeros(1)


def resample(pts, step):
    p = np.asarray(pts, float)
    s = arclen(p)
    if s[-1] < 1e-9:
        return p
    n = max(2, int(round(s[-1] / step)) + 1)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, p[:, 0]), np.interp(t, s, p[:, 1])], 1)


def chaikin(pts, n=3):
    p = np.asarray(pts, float)
    for _ in range(n):
        if len(p) < 3:
            break
        q = 0.75 * p[:-1] + 0.25 * p[1:]
        r = 0.25 * p[:-1] + 0.75 * p[1:]
        mid = np.stack([q, r], 1).reshape(-1, 2)
        p = np.vstack([p[:1], mid, p[-1:]])
    return p


def normals(p):
    t = np.gradient(p, axis=0)
    n = np.stack([-t[:, 1], t[:, 0]], 1)
    return n / np.maximum(np.hypot(n[:, 0], n[:, 1]), 1e-9)[:, None]


def running_min(a):
    return np.minimum.accumulate(a)


def monotone_surface(z, end_floor=None):
    """Non-increasing water surface from raw elevations ordered upstream -> downstream.
    Forward running minimum, then (if the mouth must sit at or above end_floor) a backward running maximum."""
    s = running_min(np.asarray(z, float))
    if end_floor is not None:
        s = np.maximum(s, end_floor)
        s = np.maximum.accumulate(s[::-1])[::-1]   # keeps non-increasing downstream
    return s


# ------------------------------------------------------------------ hydrology core
def priority_flood(h, eps=1e-3):
    """Barnes priority-flood with epsilon. Returns (filled, receiver flat index or -1 at outlets, pop order).
    Every border cell is an outlet (water may leave the map there)."""
    ny, nx = h.shape
    filled = h.copy()
    closed = np.zeros(h.shape, bool)
    recv = -np.ones(h.size, np.int64)
    heap = []
    for i in range(ny):
        for j in range(nx):
            if i in (0, ny - 1) or j in (0, nx - 1):
                closed[i, j] = True
                heapq.heappush(heap, (h[i, j], i * nx + j))
    order = []
    while heap:
        z, idx = heapq.heappop(heap)
        order.append(idx)
        i, j = divmod(idx, nx)
        for di, dj in NB8:
            a, b = i + di, j + dj
            if 0 <= a < ny and 0 <= b < nx and not closed[a, b]:
                closed[a, b] = True
                n = a * nx + b
                nz = max(h[a, b], z + eps)
                filled[a, b] = nz
                recv[n] = idx
                heapq.heappush(heap, (nz, n))
    return filled, recv, np.array(order, np.int64)


def accumulate_d8(recv, order, weight):
    acc = weight.astype(float).ravel().copy()
    for idx in order[::-1]:
        r = recv[idx]
        if r >= 0:
            acc[r] += acc[idx]
    return acc


def accumulate_dinf(filled, cell, weight):
    """Tarboton D-infinity flow accumulation on a depression-filled DEM (proportions split over two neighbours)."""
    ny, nx = filled.shape
    pad = np.pad(filled, 1, mode="edge") - 1.0     # outside the map is lower: border cells drain off-map
    z0 = pad[1:-1, 1:-1]
    facets = [((0, 1), (-1, 1)), ((-1, 0), (-1, 1)), ((-1, 0), (-1, -1)), ((0, -1), (-1, -1)),
              ((0, -1), (1, -1)), ((1, 0), (1, -1)), ((1, 0), (1, 1)), ((0, 1), (1, 1))]
    dd = cell * math.sqrt(2)
    best_s = np.full(z0.shape, -1e9)
    best = np.zeros(z0.shape + (4,))   # e1 di, dj, e2 di, dj ; plus prop
    prop = np.zeros(z0.shape)
    pa = np.zeros(z0.shape, int), np.zeros(z0.shape, int), np.zeros(z0.shape, int), np.zeros(z0.shape, int)
    for e1, e2 in facets:
        z1 = pad[1 + e1[0]:1 + e1[0] + ny, 1 + e1[1]:1 + e1[1] + nx]
        z2 = pad[1 + e2[0]:1 + e2[0] + ny, 1 + e2[1]:1 + e2[1] + nx]
        s1 = (z0 - z1) / cell
        s2 = (z1 - z2) / cell
        r = np.arctan2(s2, s1)
        s = np.hypot(s1, s2)
        lo = r < 0
        hi = r > math.pi / 4
        r = np.where(lo, 0, np.where(hi, math.pi / 4, r))
        s = np.where(lo, s1, np.where(hi, (z0 - z2) / dd, s))
        up = s > best_s
        best_s = np.where(up, s, best_s)
        prop = np.where(up, r / (math.pi / 4), prop)        # share to e2
        for k, v in enumerate((e1[0], e1[1], e2[0], e2[1])):
            pa[k][...] = np.where(up, v, pa[k])
    acc = weight.astype(float).copy()
    ii, jj = np.mgrid[0:ny, 0:nx]
    order = np.argsort(-filled, axis=None, kind="stable")
    for idx in order:
        i, j = divmod(int(idx), nx)
        if best_s[i, j] <= 0:
            continue
        p2 = prop[i, j]
        a1, b1 = i + pa[0][i, j], j + pa[1][i, j]
        a2, b2 = i + pa[2][i, j], j + pa[3][i, j]
        v = acc[i, j]
        if 0 <= a1 < ny and 0 <= b1 < nx:
            acc[a1, b1] += v * (1 - p2)
        if 0 <= a2 < ny and 0 <= b2 < nx:
            acc[a2, b2] += v * p2
    return acc


def sea_mask(g):
    """Cells below the datum connected to the map border (open sea). Basins below the datum that do not
    reach the border are dry basin ground (or lakes, if they hold water)."""
    below = g.h < g.sea
    lab, n = ndi.label(below, structure=np.ones((3, 3)))
    if n == 0:
        return np.zeros(g.h.shape, bool)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    border = border[border > 0]
    return np.isin(lab, border)


def find_lakes(g, filled, recv, sea, min_depth=1.0, min_cells=8):
    """Natural lakes = depressions the priority flood had to fill. Returns list of dicts incl. 'mask'."""
    dep = (filled - g.h) >= min_depth
    dep &= ~sea
    lab, n = ndi.label(dep, structure=np.ones((3, 3)))
    lakes = []
    for k in range(1, n + 1):
        m = lab == k
        if m.sum() < min_cells:
            continue
        level = float(filled[m].max())
        idxs = np.flatnonzero(m.ravel())
        spill = None
        for idx in idxs:
            r = recv[idx]
            if r >= 0 and not m.ravel()[r]:
                spill = g.xy(r)
                break
        lakes.append({"mask": m, "level": level, "depth": float(level - g.h[m].min()),
                      "area_sqft": float(m.sum() * g.cell ** 2), "spill": spill})
    lakes.sort(key=lambda L: -L["area_sqft"])
    return lakes


def mask_to_polygon(g, mask, level_field, pad_mode="edge"):
    """Smooth shoreline polygon(s) of `mask` using the contour of level_field (h - level) at 0, clipped to the map."""
    import contourpy
    dil = ndi.binary_dilation(mask, structure=np.ones((3, 3)))
    f = np.where(dil, level_field, 50.0)
    fp = np.pad(f, 1, mode=pad_mode)
    xs = (np.arange(-1, g.nx + 1)) * g.cell
    ys = (np.arange(-1, g.ny + 1)) * g.cell
    cg = contourpy.contour_generator(xs, ys, fp)
    rings = [np.asarray(l) for l in cg.lines(0.0)]
    polys = []
    for r in rings:
        if len(r) >= 4 and np.allclose(r[0], r[-1]):
            pg = Polygon(r).buffer(0)
            if not pg.is_empty:
                polys.append(pg)
    polys.sort(key=lambda p: -p.area)
    res = None
    for p in polys:
        res = p if res is None else res.symmetric_difference(p)
    if res is None:
        return None
    return res.intersection(box(0, 0, g.W, g.H))


def poly_to_json(pg):
    """shapely (Multi)Polygon -> list of {points, holes}."""
    out = []
    for p in (list(pg.geoms) if isinstance(pg, MultiPolygon) else [pg]):
        if p.is_empty or not isinstance(p, Polygon):
            continue
        pts = [[r1(x, 1), r1(y, 1)] for x, y in list(p.exterior.coords)[:-1]]
        holes = [[[r1(x, 1), r1(y, 1)] for x, y in list(r.coords)[:-1]] for r in p.interiors]
        out.append({"points": pts, "holes": holes})
    return out


def poly_from_geom(geom):
    pts = geom["points"]
    return Polygon(pts, geom.get("holes") or None).buffer(0)


# ------------------------------------------------------------------ river construction
def river_outline(center, width):
    p = np.asarray(center, float)
    n = normals(p)
    hw = (np.asarray(width, float) / 2.0)[:, None]
    poly = Polygon(np.vstack([p + n * hw, (p - n * hw)[::-1]]))
    if not poly.is_valid:
        poly = poly.buffer(0)
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda q: q.area)
    return poly


def meander(p, g, width_mean, rng, amp_w=0.5, wavelength_w=9.0, step=None):
    """Low-amplitude lateral wobble that is rejected where it would climb out of the valley."""
    n = len(p)
    if n < 6 or amp_w <= 0:
        return p
    step = step or g.cell
    wl = max(wavelength_w * width_mean, 6 * step)
    sigma = max(wl / step / 4.0, 1.5)
    noise = ndi.gaussian_filter1d(rng.standard_normal(n + 40), sigma)[20:20 + n]
    noise /= max(np.abs(noise).max(), 1e-9)
    taper = np.minimum(1.0, np.minimum(np.arange(n), np.arange(n)[::-1]) / max(3.0, wl / step / 2))
    amp = amp_w * width_mean
    nrm = normals(p)
    base_z = g.sample(p)
    out = p.copy()
    for k in range(1, n - 1):
        off = amp * noise[k] * taper[k]
        for _ in range(5):
            q = p[k] + nrm[k] * off
            if 0 <= q[0] <= g.W and 0 <= q[1] <= g.H and g.sample(q)[0] <= base_z[k] + 2.0 + 0.1 * width_mean:
                out[k] = q
                break
            off *= 0.5
    return out


def build_river(g, filled, cells_path, acc_cells_path, rid, params, rng, parent=None, end_floor=None,
                start_floor=None):
    """cells_path: list of flat idx (upstream -> downstream) incl. the joining cell. Returns a river entry dict."""
    raw = np.array([g.xy(i) for i in cells_path], float)
    raw_acc = np.asarray(acc_cells_path, float)
    if len(raw) < 2:
        return None
    sm = chaikin(raw, 3)
    sm = resample(sm, g.cell)
    t_raw = arclen(raw)
    t_raw = t_raw / max(t_raw[-1], 1e-9)
    acc = np.interp(np.linspace(0, 1, len(sm)), t_raw, raw_acc)
    q = acc * g.cell ** 2 / 43560.0 * params["runoff_cfs_per_acre"] * params["flow_scale"]
    q = np.maximum.accumulate(q)
    width = np.maximum(W_COEF * np.sqrt(q), params["min_width_ft"])
    depth = np.maximum(D_COEF * q ** 0.4, 0.3)
    if params.get("meander", True):
        sm = meander(sm, g, float(width.mean()), rng, params["meander_amp"], params["meander_wavelength"])
    z = g.sample(sm, filled)
    z = ndi.gaussian_filter1d(z, 1.5, mode="nearest")
    surf = monotone_surface(z, end_floor)
    if start_floor is not None:
        surf = np.maximum(surf, start_floor)  # lake outlet: surface cannot start below the lake
        surf = monotone_surface(surf, end_floor)
    return make_river_entry(rid, sm, width, depth, q, surf, origin="auto", kind="river")


def make_river_entry(rid, center, width, depth, flow, surf, origin, kind="river", name=None, extra=None):
    center = np.asarray(center, float)
    outline = river_outline(center, width)
    e = {
        "id": rid,
        "name": name or f"{'Stream' if np.max(flow) < 30 else 'River'} {rid.split('_')[-1]} (auto, not canon)",
        "kind": kind,
        "status": "proposed",
        "origin": origin,
        "geometry": {"type": "polygon", "points": [[r1(x, 1), r1(y, 1)] for x, y in list(outline.exterior.coords)[:-1]]},
        "centerline": [[r1(x, 1), r1(y, 1)] for x, y in center],
        "width_ft": [r1(v, 1) for v in width],
        "depth_ft": [r1(v, 2) for v in depth],
        "flow_cfs": [r1(v, 2) for v in flow],
        "surface_ft": [r1(v, 2) for v in surf],
        "elevation_ft": {"start": r1(surf[0], 2), "end": r1(surf[-1], 2)},
        "length_ft": r1(arclen(center)[-1], 1),
        "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
    }
    if extra:
        e.update(extra)
    return e


def extract_rivers(g, filled, recv, acc, params, sea, lake_mask, lake_ids, lakes, rng):
    """Stream network by accumulation threshold. Main stems and tributaries as separate entries.
    Returns (rivers, springs)."""
    n = g.h.size
    stream = (acc.reshape(g.h.shape) >= params["threshold_cells"]) & ~sea & ~lake_mask
    sflat = stream.ravel()
    recv_f = recv
    donors = {}
    for idx in np.flatnonzero(sflat):
        r = recv_f[idx]
        if r >= 0 and sflat[r]:
            donors.setdefault(int(r), []).append(int(idx))
    lakeflat = lake_ids.ravel()
    seaflat = sea.ravel()
    outlets = [int(i) for i in np.flatnonzero(sflat) if recv_f[i] < 0 or not sflat[recv_f[i]]]
    rivers, springs = [], []
    cnt = [0]
    id_to_entry = {}

    def new_id():
        cnt[0] += 1
        return f"wat_auto_river_{cnt[0]:02d}"

    # first pass: find every reach (list of cells downstream-ordered), recording parents by cell
    reaches = []
    stack = [(o, None) for o in outlets]
    while stack:
        cell, parent = stack.pop()
        path = [cell]
        c = cell
        while True:
            ds = donors.get(c, [])
            if not ds:
                break
            ds_sorted = sorted(ds, key=lambda k: -acc[k])
            for other in ds_sorted[1:]:
                stack.append((other, len(reaches)))   # joins this reach at cell c
            c = ds_sorted[0]
            path.append(c)
        # path is downstream -> upstream; reverse
        reaches.append({"cells": path[::-1], "parent": parent, "join": None})
    # joins: tributary's downstream-most cell's receiver is the parent's cell
    # (stack pushes carried reach index of the *parent being built*, valid since appended right after)
    # order so parents come first (outlet reaches first, tributaries after their parents)
    done_ids = {}
    # topological: process by depth from outlet
    depth_of = {}

    def depth(k):
        if k in depth_of:
            return depth_of[k]
        p = reaches[k]["parent"]
        depth_of[k] = 0 if p is None else depth(p) + 1
        return depth_of[k]
    order = sorted(range(len(reaches)), key=lambda k: (depth(k), -len(reaches[k]["cells"])))
    for k in order:
        rc = reaches[k]
        cells = rc["cells"]
        end_cell_recv = int(recv_f[cells[-1]])
        tail = None
        start_floor = None
        extra = {}
        # downstream end: parent, lake, sea or map edge
        end_floor = None
        if end_cell_recv >= 0:
            tail = end_cell_recv
            cells = cells + [tail]
            if seaflat[tail]:
                end_floor = g.sea
                extra["ends_in"] = "sea"
            elif lakeflat[tail] > 0:
                li = lakeflat[tail] - 1
                end_floor = lakes[li]["level"]
                extra["ends_in"] = lakes[li]["id"]
            elif rc["parent"] is not None:
                pid = done_ids[rc["parent"]]
                pe = id_to_entry[pid]
                pc = np.array(pe["centerline"])
                pt = np.array(g.xy(tail))
                j = int(np.argmin(np.hypot(*(pc - pt).T)))
                end_floor = pe["surface_ft"][j]
                extra["tributary_of"] = pid
                extra["confluence"] = pe["centerline"][j]
        else:
            extra["ends_in"] = "map_edge"
        # upstream end: lake outlet (a lake cell with large accumulation feeds the first stream cell)
        first = cells[0]
        up_lake = None
        for di, dj in NB8:
            i, j = g.xy(first)[1] / g.cell, g.xy(first)[0] / g.cell
            a, b = int(i) + di, int(j) + dj
            if 0 <= a < g.ny and 0 <= b < g.nx:
                nb = a * g.nx + b
                if lakeflat[nb] > 0 and recv_f[nb] == first:
                    up_lake = nb
        accs = [acc[c] for c in cells]
        if up_lake is not None:
            li = lakeflat[up_lake] - 1
            cells = [up_lake] + cells
            accs = [acc[up_lake]] + accs
            start_floor = lakes[li]["level"]
            extra["starts_from"] = lakes[li]["id"]
        rid = new_id()
        e = build_river(g, filled, cells, accs, rid, params, rng, end_floor=end_floor, start_floor=start_floor)
        if e is None:
            continue
        e.update(extra)
        if rc["parent"] is None and extra.get("ends_in") != "map_edge":
            e["is_main"] = True
        done_ids[k] = rid
        id_to_entry[rid] = e
        rivers.append(e)
        if up_lake is None:
            x, y = e["centerline"][0]
            springs.append({"id": f"wat_auto_spring_{len(springs) + 1:02d}", "name": "Spring (auto, not canon)",
                            "kind": "spring", "status": "proposed", "origin": "auto",
                            "geometry": {"type": "point", "points": [[x, y]]},
                            "elevation_ft": e["elevation_ft"]["start"], "feeds": rid, "flow_cfs": e["flow_cfs"][0],
                            "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}})
    return rivers, springs


def make_delta(g, river, n=3, spread_deg=28.0, rng=None):
    """Simple distributary fan at a river mouth that ends in the sea."""
    c = np.array(river["centerline"])
    if len(c) < 4:
        return []
    d = c[-1] - c[-4]
    d /= max(np.hypot(*d), 1e-9)
    w = river["width_ft"][-1]
    out = []
    angs = np.linspace(-spread_deg, spread_deg, n)
    for k, a in enumerate(angs):
        th = math.radians(a)
        dv = np.array([d[0] * math.cos(th) - d[1] * math.sin(th), d[0] * math.sin(th) + d[1] * math.cos(th)])
        L = 5 * w * (1.0 if k == n // 2 else 0.8)
        steps = max(4, int(L / g.cell))
        pts = np.array([c[-1] + dv * L * t / steps for t in range(steps + 1)])
        pts[:, 0] = np.clip(pts[:, 0], 0, g.W)
        pts[:, 1] = np.clip(pts[:, 1], 0, g.H)
        wd = w * (0.55 - 0.3 * np.linspace(0, 1, len(pts))) * 1.0
        wd = np.maximum(wd, 2.0)
        dep = np.full(len(pts), max(0.3, river["depth_ft"][-1] * 0.5))
        fl = np.full(len(pts), river["flow_cfs"][-1] / n)
        surf = np.full(len(pts), g.sea)
        e = make_river_entry(f"{river['id']}_dist{k + 1}", pts, wd, dep, fl, surf, origin="auto", kind="river",
                             name=f"Distributary {k + 1} of {river['id']} (auto)",
                             extra={"distributary_of": river["id"], "ends_in": "sea"})
        out.append(e)
    return out


# ------------------------------------------------------------------ user water
def user_river(g, filled, pts, rid, name, width, width_end, depth, flow, join=None, water=None, auto_direction=True,
               rng=None, meander_amp=0.0):
    p = np.asarray(pts, float)
    z0 = g.sample(p)
    if auto_direction and z0[0] < z0[-1] - 1.0 and not join:
        p = p[::-1]      # drawn uphill: flow from the high end to the low end
    extra = {}
    end_floor = None
    if join and water:
        pe = next((e for e in water if e["id"] == join and e.get("centerline")), None)
        if pe is None:
            raise SystemExit(f"--join: no river {join} with a centerline")
        pc = np.array(pe["centerline"])
        # snap the last point to the nearest point on the parent's centreline polyline
        ls = LineString(pc)
        s = ls.project(Point(p[-1]))
        sp = ls.interpolate(s)
        p[-1] = [sp.x, sp.y]
        j = int(np.argmin(np.hypot(*(pc - p[-1]).T)))
        end_floor = pe["surface_ft"][j]
        extra = {"tributary_of": join, "confluence": [r1(p[-1][0], 1), r1(p[-1][1], 1)]}
    sm = resample(chaikin(p, 2), g.cell)
    n = len(sm)
    wd = np.linspace(width, width_end if width_end else width, n)
    dp = np.full(n, depth)
    fl = np.linspace(flow, flow * (width_end / width) ** 2 if width_end else flow, n)
    if meander_amp > 0 and rng is not None:
        sm = meander(sm, g, float(wd.mean()), rng, meander_amp, 9.0)
    z = ndi.gaussian_filter1d(g.sample(sm, filled), 1.5, mode="nearest")
    surf = monotone_surface(z, end_floor)
    cut = g.sample(sm) - surf
    extra["max_cut_ft"] = r1(max(0.0, cut.max()), 1)
    return make_river_entry(rid, sm, wd, dp, fl, surf, origin="user", name=name, extra=extra)


def user_lake(g, poly, rid, name, level, depth, kind="lake", shore_slope=0.2):
    if level is None:
        # default: the lowest terrain on the rim, so nothing spills uphill
        rim = np.array(poly.exterior.coords)
        level = float(np.min(g.sample(rim)))
    rim_z = g.sample(np.array(poly.exterior.coords))
    low = float((rim_z < level - 1.0).mean())
    inside = g.mask_polygon(poly)
    spill = None
    if low > 0:
        k = int(np.argmin(rim_z))
        spill = [r1(poly.exterior.coords[k][0], 1), r1(poly.exterior.coords[k][1], 1)]
    e = {"id": rid, "name": name, "kind": kind, "status": "proposed", "origin": "user",
         "geometry": {"type": "polygon", **poly_to_json(poly)[0]},
         "elevation_ft": r1(level, 2), "max_depth_ft": r1(depth, 2), "shore_slope": shore_slope,
         "area_sqft": r1(poly.area, 0),
         "rim_below_level_fraction": r1(low, 3),
         "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}}
    if spill:
        e["warning"] = "part of the rim lies more than 1 ft below the water level: water would spill there"
        e["spill"] = spill
    return e


# ------------------------------------------------------------------ rasters
def normalise_entry(e):
    """Fill per-point arrays for entries lacking them (e.g. the hand-made legacy river)."""
    if e.get("kind") not in ("river", "stream") or not e.get("centerline"):
        return e
    if isinstance(e.get("width_ft"), list) and e.get("surface_ft"):
        return e
    c = np.array(e["centerline"], float)
    n = len(c)
    pg = poly_from_geom(e["geometry"]) if e.get("geometry", {}).get("points") else None
    if pg is not None and not pg.is_empty:
        b = pg.exterior
        w = np.array([2 * b.distance(Point(x, y)) for x, y in c])
        w = ndi.gaussian_filter1d(w, 1.0, mode="nearest")
    else:
        w = np.full(n, float(e.get("width_ft", 20)))
    e = dict(e)
    e["width_ft"] = [r1(v, 1) for v in w]
    e["flow_cfs"] = [r1((v / W_COEF) ** 2, 2) for v in w]
    e["depth_ft"] = [r1(max(0.5, 0.05 * v), 2) for v in w]
    e["_estimated"] = True
    return e


def entry_surface(g, e):
    """Surface profile for legacy entries: monotone running min of terrain along the centreline."""
    if e.get("surface_ft"):
        return np.array(e["surface_ft"], float)
    c = np.array(e["centerline"], float)
    return monotone_surface(ndi.gaussian_filter1d(g.sample(c), 1.5, mode="nearest"))


def _river_nearest(g, e, stats=("width", "depth", "surf")):
    c = np.array(e["centerline"], float)
    dense = resample(c, g.cell / 2.0)
    s = arclen(c)
    sd = arclen(dense)
    w = np.interp(sd, s, e["width_ft"])
    d = np.interp(sd, s, e["depth_ft"])
    z = np.interp(sd, s, entry_surface(g, e))
    return dense, w, d, z


def carve_heightmap(g, water, bank_ft=12.0):
    """Return a new heightmap with channels (rivers) and lake bowls cut into it. Base is never touched."""
    h = g.h.copy()
    X, Y = g.coords()
    cells = np.stack([X.ravel(), Y.ravel()], 1)
    for e0 in water:
        e = normalise_entry(e0)
        if e.get("kind") in ("river", "stream") and e.get("centerline"):
            dense, w, d, z = _river_nearest(g, e)
            hw_eff = np.maximum(w / 2.0, g.cell * 0.6)
            tree = cKDTree(dense)
            reach = hw_eff.max() + max(bank_ft, 2.5 * d.max())
            dist, k = tree.query(cells, distance_upper_bound=reach)
            ok = np.isfinite(dist)
            idx = np.flatnonzero(ok)
            kk = k[idx]
            dd = dist[idx]
            hwk, dk, zk = hw_eff[kk], d[kk], z[kk]
            cur = h.ravel()[idx]
            bank = np.maximum(bank_ft, 2.5 * dk)
            inside = dd <= hwk
            bed = zk - dk * (1 - (dd / hwk) ** 2)
            t = np.clip((dd - hwk) / bank, 0, 1)
            t = t * t * (3 - 2 * t)
            bank_t = zk + (cur - zk) * t
            tgt = np.where(inside, bed, np.where(cur > zk, bank_t, cur))
            h.ravel()[idx] = np.minimum(cur, tgt)
        elif e.get("kind") in ("lake", "pond") and e.get("origin") == "user":
            pg = poly_from_geom(e["geometry"])
            inside = g.mask_polygon(pg)
            dist = ndi.distance_transform_edt(inside) * g.cell
            dep = np.minimum(e["max_depth_ft"], dist * e.get("shore_slope", 0.2))
            lvl = e["elevation_ft"]
            h = np.where(inside, np.minimum(h, lvl - dep), h)
    return h


def depth_raster(g, water, sea, lake_masks, hc=None):
    """Water depth in feet on the grid (0 = dry). hc = heightmap to measure lake/sea depth against (carved if given)."""
    hh = g.h if hc is None else hc
    D = np.zeros(g.h.shape)
    D = np.where(sea, np.maximum(g.sea - hh, 0), D)
    X, Y = g.coords()
    cells = np.stack([X.ravel(), Y.ravel()], 1)
    for e0 in water:
        e = normalise_entry(e0)
        k = e.get("kind")
        if k in ("river", "stream") and e.get("centerline"):
            dense, w, d, z = _river_nearest(g, e)
            hw = np.maximum(w / 2.0, g.cell * 0.6)
            dist, kk = cKDTree(dense).query(cells, distance_upper_bound=hw.max())
            ok = np.isfinite(dist)
            idx = np.flatnonzero(ok)
            r = dist[idx] / hw[kk[idx]]
            val = np.where(r < 1, d[kk[idx]] * (1 - r ** 2), 0.0)
            flat = D.ravel()
            flat[idx] = np.maximum(flat[idx], val)
        elif k in ("lake", "pond"):
            if e.get("origin") == "user":
                pg = poly_from_geom(e["geometry"])
                inside = g.mask_polygon(pg)
                dist = ndi.distance_transform_edt(inside) * g.cell
                dep = np.minimum(e["max_depth_ft"], dist * e.get("shore_slope", 0.2))
                D = np.maximum(D, np.where(inside, dep, 0))
    for m, level in lake_masks:
        D = np.maximum(D, np.where(m, np.maximum(level - hh, 0), 0))
    return D


# ------------------------------------------------------------------ analysis driver
def analyze(g, params, seed=1, existing=None, delta=False, log=print):
    rng = np.random.default_rng(seed)
    filled, recv, order = priority_flood(g.h)
    sea = sea_mask(g)
    w = np.ones(g.h.shape)
    for (x, y, acres) in params.get("inflows", []):
        i, j = int(round(y / g.cell)), int(round(x / g.cell))
        w[min(max(i, 2), g.ny - 3), min(max(j, 2), g.nx - 3)] += acres * 43560.0 / g.cell ** 2
    acc = accumulate_d8(recv, order, w).reshape(g.h.shape)
    lakes = find_lakes(g, filled, recv, sea, params["min_lake_depth"], params["min_lake_cells"])
    lake_ids = np.zeros(g.h.shape, int)
    for k, L in enumerate(lakes):
        L["id"] = f"wat_lake_auto_{k + 1:02d}"
        lake_ids[L["mask"]] = k + 1
    lake_mask = lake_ids > 0
    # calibrate flow so the biggest river hits the requested width at its outlet
    st = (acc >= params["threshold_cells"]) & ~sea & ~lake_mask
    amax = acc[st].max() if st.any() else 1.0
    q_raw = amax * g.cell ** 2 / 43560.0 * params["runoff_cfs_per_acre"]
    params = dict(params)
    params["flow_scale"] = 1.0
    if params.get("outlet_width"):
        params["flow_scale"] = (params["outlet_width"] / W_COEF) ** 2 / max(q_raw, 1e-9)
    rivers, springs = extract_rivers(g, filled, recv, acc.ravel(), params, sea, lake_mask, lake_ids, lakes, rng)
    entries = []
    if delta:
        for r in list(rivers):
            if r.get("ends_in") == "sea":
                entries += make_delta(g, r)
    lake_entries = []
    for L in lakes:
        pg = mask_to_polygon(g, L["mask"], g.h - L["level"])
        if pg is None or pg.is_empty:
            continue
        j = poly_to_json(pg)
        lake_entries.append({
            "id": L["id"], "name": "Lake (auto, not canon)", "kind": "lake" if L["area_sqft"] > 20000 else "pond",
            "status": "proposed", "origin": "auto",
            "geometry": {"type": "polygon", **max(j, key=lambda q: len(q["points"]))},
            "elevation_ft": r1(L["level"], 2), "max_depth_ft": r1(L["depth"], 2),
            "area_sqft": r1(pg.area, 0), "spill": [r1(L["spill"][0], 1), r1(L["spill"][1], 1)] if L["spill"] else None,
            "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}})
    sea_entries = []
    if sea.any():
        pg = mask_to_polygon(g, sea, g.h - g.sea)
        if pg is not None and not pg.is_empty:
            for k, j in enumerate(poly_to_json(pg)):
                sea_entries.append({"id": f"wat_sea_{k + 1:02d}", "name": "Sea (auto, not canon)", "kind": "sea",
                                    "status": "proposed", "origin": "auto",
                                    "geometry": {"type": "polygon", **j}, "elevation_ft": r1(g.sea, 2),
                                    "max_depth_ft": r1(g.sea - g.h[sea].min(), 2),
                                    "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}})
    res = {"filled": filled, "acc": acc, "sea": sea, "lakes": lakes, "lake_ids": lake_ids,
           "rivers": rivers + entries, "springs": springs, "lake_entries": lake_entries, "sea_entries": sea_entries,
           "params": params, "q_raw": q_raw}
    return res


def default_params(**kw):
    p = {"threshold_cells": 150, "runoff_cfs_per_acre": 0.05, "min_width_ft": 3.0, "meander": True,
         "meander_amp": 0.5, "meander_wavelength": 9.0, "min_lake_depth": 1.0, "min_lake_cells": 8,
         "outlet_width": None, "inflows": []}
    p.update({k: v for k, v in kw.items() if v is not None})
    return p


# ------------------------------------------------------------------ verification
def verify(g, water, tol=0.011):
    """Checks water never runs uphill. Returns (list of problems, stats)."""
    problems = []
    byid = {e["id"]: e for e in water}
    nriv = 0
    for e in water:
        if e.get("kind") in ("river", "stream") and e.get("surface_ft"):
            nriv += 1
            s = np.array(e["surface_ft"])
            up = np.flatnonzero(np.diff(s) > tol)
            if len(up):
                problems.append(f"{e['id']}: surface rises {np.diff(s).max():.3f} ft at {len(up)} points")
            if len(e["centerline"]) != len(s):
                problems.append(f"{e['id']}: array length mismatch")
            fl = np.array(e["flow_cfs"])
            if np.any(np.diff(fl) < -1e-6) and e.get("origin") == "auto":
                problems.append(f"{e['id']}: flow decreases downstream")
            par = e.get("tributary_of")
            if par and par in byid:
                ps = np.array(byid[par]["surface_ft"])
                pc = np.array(byid[par]["centerline"])
                j = int(np.argmin(np.hypot(*(pc - np.array(e["confluence"])).T)))
                if s[-1] < ps[j] - 0.02:
                    problems.append(f"{e['id']}: mouth {s[-1]:.2f} below parent surface {ps[j]:.2f} (water would flow uphill into it)")
            ends = e.get("ends_in")
            if ends and ends in byid and byid[ends].get("elevation_ft") is not None:
                lv = byid[ends]["elevation_ft"]
                if s[-1] < lv - 0.02:
                    problems.append(f"{e['id']}: ends {s[-1]:.2f} below {ends} level {lv}")
            sf = e.get("starts_from")
            if sf and sf in byid and s[0] > byid[sf]["elevation_ft"] + 0.02:
                problems.append(f"{e['id']}: starts {s[0]:.2f} above its source lake {byid[sf]['elevation_ft']}")
    return problems, {"rivers_checked": nriv}


# ------------------------------------------------------------------ crossings
def crossings(g, water, streets, polyline=None, abut_ft=6.0, clearance_ft=3.0):
    roads = []
    if polyline:
        roads.append({"id": "polyline", "name": "polyline", "kind": "road", "pts": polyline})
    else:
        for s in streets:
            gm = s.get("geometry", {})
            if gm.get("type") == "polyline":
                roads.append({"id": s["id"], "name": s.get("name"), "kind": s.get("kind", "road"), "pts": gm["points"]})
    bridges = [(r["id"], LineString(r["pts"]).buffer(4.0)) for r in roads if r["kind"] == "bridge"]
    out = []
    for r in roads:
        line = LineString(r["pts"])
        for e0 in water:
            e = normalise_entry(e0)
            if not e.get("geometry", {}).get("points"):
                continue
            if e.get("geometry", {}).get("type") != "polygon":
                continue
            pg = poly_from_geom(e["geometry"])
            inter = line.intersection(pg)
            if inter.is_empty:
                continue
            parts = [inter] if inter.geom_type == "LineString" else [x for x in getattr(inter, "geoms", []) if x.geom_type == "LineString"]
            for part in parts:
                if part.length < 1e-6:
                    continue
                c = part.centroid
                a, b = part.coords[0], part.coords[-1]
                bank = float(max(g.sample([a])[0], g.sample([b])[0]))
                rec = {"road": r["id"], "road_name": r["name"], "water_id": e["id"], "water_kind": e["kind"],
                       "point": [r1(c.x, 1), r1(c.y, 1)], "width_ft": r1(part.length, 1),
                       "bank_elevation_ft": r1(bank, 1)}
                if e["kind"] in ("river", "stream") and e.get("centerline"):
                    cl = np.array(e["centerline"])
                    j = int(np.argmin(np.hypot(*(cl - np.array([c.x, c.y])).T)))
                    depth, q = e["depth_ft"][j], e["flow_cfs"][j]
                    surf = float(entry_surface(g, e)[j])
                    rec.update({"depth_ft": depth, "flow_cfs": q, "surface_ft": r1(surf, 2),
                                "river_width_ft": e["width_ft"][j]})
                    if depth <= 2.0 and q <= 150 and part.length <= 40:
                        rec["suggestion"] = "ford"
                        rec["note"] = f"shallow ({depth} ft) and modest flow; paved ford, stepping stones for pedestrians"
                    else:
                        span = math.ceil((part.length + 2 * abut_ft) / 5.0) * 5
                        rec["suggestion"] = "bridge"
                        rec["span_ft"] = span
                        rec["deck_elevation_ft"] = r1(max(bank, surf) + clearance_ft, 1)
                        rec["note"] = f"clear span {span} ft ({abut_ft:g} ft abutments each side)"
                else:
                    rec["depth_ft"] = e.get("max_depth_ft")
                    rec["suggestion"] = "avoid"
                    rec["note"] = "standing water: reroute, causeway or ferry"
                eb = [bid for bid, bp in bridges if bp.distance(c) < 1.0 and bid != r["id"]]
                if r["kind"] == "bridge":
                    rec["existing_bridge"] = r["id"]
                elif eb:
                    rec["existing_bridge"] = eb[0]
                out.append(rec)
    return out


# ------------------------------------------------------------------ SVG layer data
WATER_CSS = """
.water-body { fill: #cfe4f5; stroke: #1a4f8a; stroke-width: 0.5; fill-rule: evenodd; }
.water-centre { fill: none; stroke: #1a4f8a; stroke-width: 0.3; stroke-dasharray: 2 1.5; }
.water-spring { fill: #1a4f8a; stroke: none; }
.proposed.water-body { stroke-dasharray: 3 1.5; }
"""


def _d_ring(pts, px):
    q = [px(x, y) for x, y in pts]
    return "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in q) + " Z"


def water_svg_items(water, px, centerlines=False):
    """Returns [(kind, svg_string)] with kind in 'body', 'centre', 'spring'. Ids are entity ids (+ '_centre')."""
    items = []
    for e in water:
        gm = e.get("geometry", {})
        cls_extra = " proposed" if e.get("status") == "proposed" else ""
        if gm.get("type") == "polygon" and gm.get("points"):
            d = _d_ring(gm["points"], px) + "".join(" " + _d_ring(h, px) for h in gm.get("holes", []))
            items.append(("body", f'<path id="{e["id"]}" class="water-body{cls_extra}" fill-rule="evenodd" d="{d}"/>'))
        elif gm.get("type") == "point":
            x, y = px(*gm["points"][0])
            items.append(("spring", f'<circle id="{e["id"]}" class="water-spring" cx="{x:.2f}" cy="{y:.2f}" r="1.2"/>'))
        if centerlines and e.get("centerline"):
            d = "M" + " L".join("%.2f,%.2f" % px(x, y) for x, y in e["centerline"])
            items.append(("centre", f'<path id="{e["id"]}_centre" class="water-centre" d="{d}"/>'))
    return items


def add_water_to_tree(tree, water, px, layer="Water", centerlines=False, sublayers=None):
    """Add closed water polygons to a lib_svg.LayerTree. sublayers: optional {'body':name,'centre':name,'spring':name}
    mapping to layers that already exist in the tree; default puts everything in `layer`."""
    for kind, svg in water_svg_items(water, px, centerlines):
        tree.add((sublayers or {}).get(kind, layer), svg)


def water_fragment(water, px, centerlines=True):
    items = water_svg_items(water, px, centerlines)
    return '<g id="Water" inkscape:groupmode="layer" inkscape:label="Water">\n' + "\n".join(s for _, s in items) + "\n</g>\n"


# ------------------------------------------------------------------ previews
def preview(g, water, depth, path, acc=None, legacy=None, crossing=None, title=None, zoom=5, show_acc=False,
            sea=None):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, HERE)
    import terrain as T
    hs = T.hillshade(g.h, g.cell)
    shade = np.clip(0.85 + (hs - np.sin(np.radians(40))) * 1.1, 0.35, 1.15)
    lo, hi = g.h.min(), g.h.max()
    t = (g.h - lo) / max(hi - lo, 1e-6)
    stops = np.array([0, .12, .45, .75, 1.0])
    cols = np.array([[70, 125, 70], [140, 170, 90], [170, 150, 105], [150, 140, 135], [250, 250, 250]], float)
    rgb = np.stack([np.interp(t, stops, cols[:, k]) for k in range(3)], -1) * shade[..., None]
    if show_acc and acc is not None:
        a = np.log10(np.maximum(acc, 1))
        a = np.clip(a / max(a.max(), 1), 0, 1)
        rgb = rgb * (1 - a[..., None] * 0.9) + np.array([20, 70, 220]) * a[..., None] * 0.9
    dn = np.clip(depth / max(depth.max(), 3.0), 0, 1)
    wet = depth > 0.02
    blue = np.array([40, 110, 190])[None, None] * (1 - 0.0) + 0
    shallow, deep = np.array([140, 195, 235.0]), np.array([20, 60, 150.0])
    wc = shallow[None, None] * (1 - dn[..., None]) + deep[None, None] * dn[..., None]
    rgb = np.where(wet[..., None], wc, rgb)
    rgb = ndi.zoom(rgb, (zoom, zoom, 1), order=1)
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(img)
    f = zoom / g.cell

    def P(x, y):
        return (x * f, y * f)
    for e in water:
        gm = e.get("geometry", {})
        if gm.get("type") == "polygon" and gm.get("points") and not e.get("_legacy"):
            d.line([P(*p) for p in gm["points"] + [gm["points"][0]]], fill=(10, 50, 120), width=1)
        if e.get("centerline") and not e.get("_legacy"):
            col = (255, 220, 0) if e.get("origin") == "auto" else (255, 90, 200)
            d.line([P(*p) for p in e["centerline"]], fill=col, width=1)
        if gm.get("type") == "point":
            x, y = P(*gm["points"][0])
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(255, 255, 255), outline=(0, 0, 0))
    if legacy:
        for e in legacy:
            d.line([P(*p) for p in e["centerline"]], fill=(255, 40, 40), width=2)
    for c in crossing or []:
        x, y = P(*c["point"])
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=(255, 255, 255), width=2)
        if c["suggestion"] != "ford":
            d.text((x + 7, y - 6), f"{c['suggestion']} {c.get('span_ft', '')}", fill=(255, 255, 255))
    if title:
        d.rectangle([4, 4, 4 + 7 * len(title), 20], fill=(0, 0, 0))
        d.text((8, 7), title, fill=(255, 255, 255))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


# ------------------------------------------------------------------ IO / CLI
class Ctx:
    pass


def make_ctx(a):
    c = Ctx()
    c.place = a.place
    c.root = os.path.join(REPO, "world", a.place)
    c.g, c.meta = load_grid(a.place, sea_level=getattr(a, "sea_level", None), offset=getattr(a, "elev_offset", 0.0) or 0.0)
    c.out = os.path.abspath(getattr(a, "out", None) or os.path.join(OUT_ROOT, a.place))
    os.makedirs(c.out, exist_ok=True)
    c.base_water_path = os.path.join(c.root, "water.json")
    c.work_path = os.path.join(c.out, "water.json")
    c.inplace = getattr(a, "inplace", False)
    return c


def load_water(c, fresh=False):
    p = c.work_path if (os.path.exists(c.work_path) and not fresh) else c.base_water_path
    return json.load(open(p, encoding="utf-8"))["water"]


def save_water(c, water, extra_top=None):
    doc = {"place": c.place, "sea_level_ft": c.g.sea, "water": water}
    if extra_top:
        doc.update(extra_top)
    paths = [c.work_path] + ([c.base_water_path] if c.inplace else [])
    for p in paths:
        with open(p, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=1)
            f.write("\n")
    return paths


def lake_masks_from(g, water):
    return []


def outputs(c, water, res=None, tag="", legacy=None, crossing=None, carve=False, bank_ft=12.0, show_acc=False):
    g = c.g
    hc = carve_heightmap(g, water, bank_ft) if carve else None
    sea = res["sea"] if res else sea_mask(g)
    if res is not None:
        lmasks = [(L["mask"], L["level"]) for L in res["lakes"]]
    else:
        # recompute natural lake masks from base terrain
        filled, recv, _ = priority_flood(g.h)
        lmasks = [(L["mask"], L["level"]) for L in find_lakes(g, filled, recv, sea)]
        lmasks = [m for m in lmasks]
    D = depth_raster(g, water, sea, lmasks, hc)
    np.save(os.path.join(c.out, "water_depth.npy"), D.astype(np.float32))
    from PIL import Image
    Image.fromarray(np.clip(D / max(D.max(), 1e-6) * 65535, 0, 65535).astype(np.uint16)).save(
        os.path.join(c.out, "water_depth_16.png"))
    json.dump({"max_depth_ft": float(D.max()), "scaled_to": "uint16 = depth / max_depth_ft * 65535",
               "cell_ft": g.cell, "sea_level_ft": g.sea}, open(os.path.join(c.out, "water_depth_meta.json"), "w"), indent=1)
    if hc is not None:
        np.save(os.path.join(c.out, "heightmap_carved.npy"), hc.astype(np.float32))
    if res is not None:
        np.save(os.path.join(c.out, "flow_acc.npy"), res["acc"].astype(np.float32))
    return D, hc


def cmd_analyze(a):
    c = make_ctx(a)
    g = c.g
    p = default_params(threshold_cells=a.threshold_cells, outlet_width=a.outlet_width, meander=not a.no_meander,
                       min_lake_depth=a.min_lake_depth, runoff_cfs_per_acre=a.runoff,
                       inflows=[tuple(float(v) for v in s.split(",")) for s in (a.inflow or [])])
    base = load_water(c, fresh=True)
    res = analyze(g, p, seed=a.seed, delta=a.delta)
    legacy = [dict(e, _legacy=True) for e in base if e.get("centerline") and e.get("origin") != "auto"]
    keep = [e for e in base if e.get("origin") != "auto"]
    water = keep + res["sea_entries"] + res["lake_entries"] + res["rivers"] + res["springs"]
    save_water(c, water, {"derived_with": {k: v for k, v in res["params"].items() if k != "inflows"}})
    D, _ = outputs(c, water, res)
    # dinf raster for shading/flow-line preview (diffuse flow)
    dinf = accumulate_dinf(res["filled"], g.cell, np.ones(g.h.shape))
    np.save(os.path.join(c.out, "flow_acc_dinf.npy"), dinf.astype(np.float32))
    probs, st = verify(g, water)
    streets = json.load(open(os.path.join(c.root, "streets.json")))["streets"]
    cr = crossings(g, water, streets)
    json.dump(cr, open(os.path.join(c.out, "crossings.json"), "w"), indent=1)
    preview(g, water, D, os.path.join(c.out, "preview_water.png"), legacy=legacy, crossing=cr,
            title=f"{c.place}: water (auto rivers yellow, legacy river red)")
    preview(g, water, D, os.path.join(c.out, "preview_flow.png"), acc=res["acc"], show_acc=True,
            title=f"{c.place}: D8 flow accumulation (log)")
    # report
    autos = [r for r in res["rivers"] if not r.get("distributary_of")]
    print(f"grid {g.nx}x{g.ny} cell {g.cell} ft, elevation {g.h.min():.1f}..{g.h.max():.1f} ft, sea level {g.sea} ft")
    print(f"sea cells: {int(res['sea'].sum())}; natural lakes: {len(res['lakes'])}; "
          f"auto rivers/reaches: {len(autos)}; springs: {len(res['springs'])}; flow_scale {res['params']['flow_scale']:.3g}")
    for r in autos:
        print(f"  {r['id']}: len {r['length_ft']:.0f} ft, width {r['width_ft'][0]:.0f}->{r['width_ft'][-1]:.0f}, "
              f"depth {r['depth_ft'][0]}->{r['depth_ft'][-1]}, Q {r['flow_cfs'][0]}->{r['flow_cfs'][-1]} cfs, "
              f"surface {r['elevation_ft']['start']}->{r['elevation_ft']['end']}  "
              f"start({r['centerline'][0][0]:.0f},{r['centerline'][0][1]:.0f}) end({r['centerline'][-1][0]:.0f},{r['centerline'][-1][1]:.0f})"
              + (f" tributary_of {r['tributary_of']}" if r.get("tributary_of") else "")
              + (f" ends_in {r['ends_in']}" if r.get("ends_in") else ""))
    for L in res["lake_entries"]:
        print(f"  lake {L['id']}: level {L['elevation_ft']} ft, depth {L['max_depth_ft']}, area {L['area_sqft']:.0f} sqft")
    # compare with legacy river
    for le in legacy:
        lc = np.array(le["centerline"])
        allp = []
        for r in autos:
            cl = np.array(r["centerline"])
            allp.append(cl)
        allp = np.vstack(allp) if allp else np.zeros((0, 2))
        if len(allp):
            tree = cKDTree(allp)
            dd, _ = tree.query(lc)
            print(f"legacy {le['id']}: centreline to nearest auto river: mean {dd.mean():.1f} ft, median {np.median(dd):.1f}, "
                  f"max {dd.max():.1f}; within 60 ft for {100 * (dd <= 60).mean():.0f}% of points")
            ys = lc[:, 1]
            print(f"  legacy flows north->south (y increasing): {bool(np.all(np.diff(ys) > 0))}, "
                  f"y {ys[0]:.0f}->{ys[-1]:.0f}")
        z = g.sample(lc)
        print(f"  terrain under legacy centreline {z[0]:.1f} -> {z[-1]:.1f} ft; uphill steps (>0.5 ft): "
              f"{int((np.diff(z) > 0.5).sum())} of {len(z) - 1}")
        for r in autos:
            if r.get("is_main"):
                cl = np.array(r["centerline"])
                print(f"  auto main {r['id']}: y {cl[0][1]:.0f}->{cl[-1][1]:.0f}, ends at ({cl[-1][0]:.0f},{cl[-1][1]:.0f}), "
                      f"ends_in {r.get('ends_in')}")
    print("verify:", "OK, no uphill water" if not probs else probs)
    print(f"crossings of streets: {len(cr)}")
    for x in cr:
        print("  ", {k: x.get(k) for k in ("road", "water_id", "point", "width_ft", "suggestion", "span_ft", "existing_bridge")})
    print("outputs in", c.out)


def cmd_carve(a):
    c = make_ctx(a)
    water = load_water(c)
    hc = carve_heightmap(c.g, water, a.bank_ft)
    np.save(os.path.join(c.out, "heightmap_carved.npy"), hc.astype(np.float32))
    diff = c.g.h - hc
    print(f"carved: max cut {diff.max():.1f} ft, cells changed {int((diff > 0.01).sum())}; base untouched; "
          f"wrote {os.path.join(c.out, 'heightmap_carved.npy')}")
    D, _ = outputs(c, water, carve=True, bank_ft=a.bank_ft)
    preview(c.g, water, D, os.path.join(c.out, "preview_carved.png"), title="carved channels")
    # compare shaded relief of carved terrain
    save_carved_preview(c, hc)


def save_carved_preview(c, hc):
    g2 = Grid(hc, c.g.cell, c.g.sea)
    water = load_water(c)
    D = np.load(os.path.join(c.out, "water_depth.npy"))
    preview(g2, water, D, os.path.join(c.out, "preview_carved.png"), title="carved heightmap + water")


def cmd_add_river(a):
    c = make_ctx(a)
    g = c.g
    water = load_water(c)
    filled, _, _ = priority_flood(g.h)
    n = 1 + sum(1 for e in water if e["id"].startswith("wat_user_river_"))
    rid = f"wat_user_river_{n:02d}"
    rng = np.random.default_rng(a.seed + n)
    e = user_river(g, filled, parse_pts(a.points), rid, a.name or f"User stream {n}", a.width, a.width_end, a.depth,
                   a.flow, join=a.join, water=water, rng=rng, meander_amp=a.meander)
    water.append(e)
    save_water(c, water)
    print(f"added {rid}: len {e['length_ft']} ft, surface {e['elevation_ft']['start']}->{e['elevation_ft']['end']} ft, "
          f"max cut into terrain {e['max_cut_ft']} ft" + (f", joins {a.join}" if a.join else ""))
    probs, _ = verify(g, water)
    print("verify:", "OK" if not probs else probs)
    refresh(c, water, carve=a.carve, bank_ft=a.bank_ft, title=f"added {rid}")


def cmd_add_lake(a):
    c = make_ctx(a)
    g = c.g
    water = load_water(c)
    if a.circle:
        x, y, r = [float(v) for v in a.circle.split(",")]
        poly = Point(x, y).buffer(r, 24)
    else:
        poly = Polygon(parse_pts(a.polygon)).buffer(0)
    n = 1 + sum(1 for e in water if e["id"].startswith("wat_user_lake_"))
    rid = f"wat_user_lake_{n:02d}"
    e = user_lake(g, poly, rid, a.name or f"User lake {n}", a.level, a.depth, a.kind, a.shore_slope)
    water.append(e)
    save_water(c, water)
    print(f"added {rid}: level {e['elevation_ft']} ft, depth {e['max_depth_ft']}, area {e['area_sqft']:.0f} sqft"
          + (f"  WARNING: {e['warning']}" if e.get("warning") else ""))
    refresh(c, water, carve=True, bank_ft=12.0, title=f"added {rid}")


def refresh(c, water, carve=False, bank_ft=12.0, title=""):
    D, hc = outputs(c, water, carve=carve, bank_ft=bank_ft)
    sea = None
    legacy = [dict(e, _legacy=True) for e in water if e.get("centerline") and e.get("origin") not in ("auto", "user")]
    g = c.g if hc is None else Grid(hc, c.g.cell, c.g.sea)
    preview(g, water, D, os.path.join(c.out, "preview_edit.png"), legacy=legacy, title=title)
    print("wrote", os.path.join(c.out, "preview_edit.png"))


def cmd_crossings(a):
    c = make_ctx(a)
    water = load_water(c)
    streets = json.load(open(os.path.join(c.root, "streets.json")))["streets"]
    if a.street:
        streets = [s for s in streets if s["id"] == a.street]
    cr = crossings(c.g, water, streets, parse_pts(a.polyline) if a.polyline else None)
    json.dump(cr, open(os.path.join(c.out, "crossings.json"), "w"), indent=1)
    for x in cr:
        print(json.dumps(x))
    print(len(cr), "crossings ->", os.path.join(c.out, "crossings.json"))


def cmd_svg(a):
    c = make_ctx(a)
    water = load_water(c)
    place = json.load(open(os.path.join(c.root, "place.json")))
    fpi = a.feet_per_inch or place["scales"]["town"]["feet_per_inch"]
    x0, y0 = place["view_focus"]["town"]
    cx, cy = 17 * 72 / 2, 11 * 72 / 2
    px = lambda x, y: (cx + (x - x0) / fpi * 72.0, cy + (y - y0) / fpi * 72.0)
    frag = water_fragment(water, px)
    p = os.path.join(c.out, "water_fragment.svgfrag")
    open(p, "w", encoding="utf-8").write(frag)
    print("wrote", p, "(town view transform, %g ft/in); items: %d" % (fpi, frag.count("<path") + frag.count("<circle")))


def cmd_verify(a):
    c = make_ctx(a)
    water = load_water(c)
    probs, st = verify(c.g, water)
    print(st, "OK" if not probs else probs)
    sys.exit(1 if probs else 0)


def cmd_selftest(a):
    """Synthetic checks: sea level, basin below zero, shifted datum invariance, uphill checks."""
    ny, nx, cell = 101, 151, 10.0
    yy, xx = np.mgrid[0:ny, 0:nx]
    x, y = xx * cell, yy * cell
    h = 60 - 0.04 * y + 25 * np.exp(-((x - 750) ** 2) / 90000) * 0 + 8 * np.sin(x / 120.0)
    h += 40 * np.exp(-((x - 400) ** 2 + (y - 500) ** 2) / 20000)         # hill
    h -= 90 * np.exp(-((x - 1100) ** 2 + (y - 350) ** 2) / 15000)         # closed basin that dips below 0
    h -= 25 * np.exp(-((x - 700) ** 2) / 3000) * (y > 0)                  # valley
    g = Grid(h, cell, 0.0)
    assert g.h.min() < 0, "test terrain must have negatives"
    p = default_params(threshold_cells=60)
    r = analyze(g, p, seed=3, delta=True)
    pr, _ = verify(g, r["lake_entries"] and (r["rivers"] + r["lake_entries"]) or r["rivers"])
    print("rivers", len(r["rivers"]), "lakes", len(r["lakes"]), "sea cells", int(r["sea"].sum()),
          "min elev", round(float(g.h.min()), 1))
    assert not pr, pr
    # datum shift invariance (all elevations shifted by -500, sea level shifted with them)
    g2 = Grid(h - 500, cell, -500.0)
    r2 = analyze(g2, p, seed=3, delta=True)
    assert len(r2["rivers"]) == len(r["rivers"]) and len(r2["lakes"]) == len(r["lakes"])
    assert int(r2["sea"].sum()) == int(r["sea"].sum())
    # sea level raised above the low edge: sea appears and rivers end in it
    g3 = Grid(h, cell, float(np.percentile(h[-1], 40)))
    r3 = analyze(g3, p, seed=3, delta=True)
    pr3, _ = verify(g3, r3["rivers"] + r3["sea_entries"])
    assert r3["sea"].any() and not pr3, pr3
    # user lake in the sub-zero basin and carve
    poly = Point(1100, 350).buffer(60)
    lk = user_lake(g, poly, "wat_user_lake_01", "t", None, 10.0)
    water = r["rivers"] + [lk]
    hc = carve_heightmap(g, water)
    assert hc.min() <= g.h.min() + 1e-9 and np.all(hc <= g.h + 1e-9)
    D = depth_raster(g, water, r["sea"], [(L["mask"], L["level"]) for L in r["lakes"]], hc)
    assert np.isfinite(D).all() and D.min() >= 0
    print("selftest OK (negative basin, datum shift, sea level, carve, depth raster)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--place", default="bridgehollow")
        sp.add_argument("--out", help="output dir (default illustrator/out/water/<place>)")
        sp.add_argument("--sea-level", type=float, help="override sea_level_ft (default: terrain_meta or 0)")
        sp.add_argument("--elev-offset", type=float, default=0.0, help="shift the heightmap (testing negative elevations)")
        sp.add_argument("--inplace", action="store_true", help="also write world/<place>/water.json")
        sp.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("analyze"); common(s)
    s.add_argument("--threshold-cells", type=float, default=150)
    s.add_argument("--outlet-width", type=float, help="calibrate flow so the biggest river is this wide at its mouth (ft)")
    s.add_argument("--runoff", type=float, default=0.05, help="cfs per acre of catchment")
    s.add_argument("--inflow", action="append", help="x,y,acres of off-map catchment entering at a point (repeatable)")
    s.add_argument("--min-lake-depth", type=float, default=1.0)
    s.add_argument("--no-meander", action="store_true")
    s.add_argument("--delta", action="store_true")
    s.set_defaults(f=cmd_analyze)
    s = sub.add_parser("carve"); common(s)
    s.add_argument("--bank-ft", type=float, default=12.0)
    s.set_defaults(f=cmd_carve)
    s = sub.add_parser("add-river"); common(s)
    s.add_argument("--points", required=True)
    s.add_argument("--name")
    s.add_argument("--width", type=float, default=10)
    s.add_argument("--width-end", type=float)
    s.add_argument("--depth", type=float, default=1.5)
    s.add_argument("--flow", type=float, default=8)
    s.add_argument("--join", help="id of the river this one flows into")
    s.add_argument("--meander", type=float, default=0.0, help="meander amplitude in river widths")
    s.add_argument("--carve", action="store_true")
    s.add_argument("--bank-ft", type=float, default=12.0)
    s.set_defaults(f=cmd_add_river)
    s = sub.add_parser("add-lake"); common(s)
    s.add_argument("--circle")
    s.add_argument("--polygon")
    s.add_argument("--level", type=float)
    s.add_argument("--depth", type=float, default=8.0)
    s.add_argument("--name")
    s.add_argument("--kind", default="lake", choices=["lake", "pond"])
    s.add_argument("--shore-slope", type=float, default=0.2)
    s.set_defaults(f=cmd_add_lake)
    s = sub.add_parser("crossings"); common(s)
    s.add_argument("--street")
    s.add_argument("--polyline")
    s.set_defaults(f=cmd_crossings)
    s = sub.add_parser("svg"); common(s)
    s.add_argument("--feet-per-inch", type=float)
    s.set_defaults(f=cmd_svg)
    s = sub.add_parser("verify"); common(s)
    s.set_defaults(f=cmd_verify)
    s = sub.add_parser("selftest")
    s.set_defaults(f=cmd_selftest)
    a = ap.parse_args()
    if a.cmd in ("add-lake",) and not (a.circle or a.polygon):
        ap.error("add-lake needs --circle or --polygon")
    a.f(a)


if __name__ == "__main__":
    main()
