"""Organic, terrain-following town generator (deterministic by seed).

  python illustrator/generators/town_gen.py [--place bridgehollow] [--params PATH] [--seed N] [--detail 1|2|3]
                                            [--preset town|bowl|street|room] [--scale FT_PER_IN] [--dry-run]

Reads   world/<place>/town_params.json  (one JSON per generation; schema in README), the heightmap
        (world/<place>/terrain/), world/<place>/water.json (existing schema only, see `load_water`),
        world/<place>/view_settings.json (scale; min street width).
Writes  world/<place>/streets.json, districts.json, buildings/bld_*.json, place.json (merged), town_gen_report.json.
Everything is feet, y down, signed elevations against sea_level_ft (terrain_meta.json, default 0). All status "proposed".

Method (ideas from Parish/Muller procedural cities, Chen et al. tensor-field street modelling, and Oleg
Dolya's "Medieval Fantasy City Generator" / TownGeneratorOS, GPL-3, github.com/watabou/TownGeneratorOS; the block
subdivision here follows its oriented-bounding-box recursive cutting. This file is a fresh implementation, GPL-3
terms apply if it were ever distributed; this repository is private and not distributed):
  1. grids: heights, slope, water/below-datum mask, distance to water, noisy ring radius.
  2. main road: A* from the entry over a cost grid (grade cap => switchbacks, bridge cost over rivers).
  3. tensor field: ring tangent + main road + river bank + contour direction (weight grows with slope) + noise.
  4. streamlines of that field (major = along contours/rings, minor = across), spaced per ring, grade capped by
     rotating the heading toward the contour direction, joined to neighbours, pruned to the connected network.
  5. plazas (count from area size), blocks = area - streets - plazas - water margin.
  6. blocks cut into lots (OBB recursion); lots become houses / civic / fields / farmsteads by ring and terrain.
  7. named civic buildings placed by scoring lots; mill at the water edge; gate watch on the road.
"""
import argparse
import heapq
import json
import math
import os
import random
import re
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box
from shapely.ops import nearest_points, unary_union
from shapely.strtree import STRtree

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain as tr  # noqa: E402
import viewcfg  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

DEFAULTS = {
    "place": None, "seed": 1, "detail": 2, "view_preset": "town",
    "naming_set": None,         # presets/naming/<id>.json: street / building / district-note names (None: bridgehollow_legacy for places called bridgehollow*, else fantasy_generic)
    "area_ft": None,
    "area_mode": "manual",      # manual (area_ft as drawn) | auto (terrain-fitted, town_area.py) | snap (area_ft settled onto the terrain)
    "area_auto": {},            # town_area.DEFAULTS overrides (slope_limit, river_buffer_ft, smoothing_ft, min_width_ft, noise_ft, target_area_ft2...)
    "output": {"streets": True, "plazas": True, "blocks": False, "buildings": True, "fields": True, "districts": True},
    "limits": {"max_street_grade": 0.09, "max_main_grade": 0.07, "max_build_slope": 0.17, "max_build_relief_ft": 5.0,
               "max_field_slope": 0.13, "hard_slope": 0.30, "water_margin_ft": 14.0, "bank_margin_ft": 8.0,
               "below_datum_is_water": True, "dry_basin_polys": [], "flood_ft": 60.0, "min_street_width_ft": 10.0,
               "bank_fill_ft": 45.0, "max_cut_fill_ft": 3.0},
    "entry": {"point": None, "via": [], "name": None, "id": "main_road", "width_ft": 30.0,
              "bridge_width_ft": 26.0, "bridge_cost_per_ft": 6.0,
              "grade_weight": 0.8, "grade_exp": 2.0},
    "ring_spec": {
        "centre": None, "aspect": [1.0, 1.0], "noise": 0.12, "noise_period_ft": 320, "feather_ft": 90,
        "rings": [
            {"id": "core", "name": "Civic Quarter", "kind": "civic", "r_max": 170, "street_width": 24,
             "dsep": [80, 95], "lot_area": [2600, 6000], "build_prob": 0.95},
            {"id": "town", "name": "Town", "kind": "residential", "r_max": 480, "street_width": 18,
             "dsep": [85, 100], "lot_area": [1000, 2300], "build_prob": 0.85},
            {"id": "farm", "name": "Farmland", "kind": "farm", "r_max": 1e9, "street_width": 13,
             "dsep": [210, 300], "lot_area": [28000, 85000], "build_prob": 0.30},
        ]},
    "streets": {"step_ft": 10.0, "min_length_ft": 70.0, "snap_ft": 70.0, "seed_jitter": 0.35, "noise_angle_deg": 35, "grid_weight": 0.9,
                "contour_weight": 3.0, "slope_lo": 0.03, "slope_hi": 0.10, "road_weight": 2.0, "road_decay_ft": 150,
                "river_weight": 2.0, "river_decay_ft": 80, "ring_weight": 0.7, "simplify_ft": None, "chaikin": 1,
                "cross_dsep_factor": 1.0,
                "trace_grade_margin": 1.0, "stub_min_ft": 0.0, "loop_max_area_ft2": 0.0, "loop_compact": 0.3, "split_steep_factor": 0.0, "smooth_sigma_ft": 0.0},
    "plazas": {"enabled": True, "min_area_ft2": 150000, "per_area_ft2": 450000, "max": 4, "radius_ft": [38, 62],
               "min_sep_ft": 260, "anchors": []},
    "lots": {"spread": 0.18, "angle_jitter_deg": 8, "min_frontage_ft": 14, "front_setback_ft": [2, 6],
             "house_fill_w": [0.62, 0.88], "house_fill_d": [0.5, 0.8], "min_house_ft": [16, 14],
             "field_bend_ft": 18, "field_hedge_ft": 2.0, "farmstead_prob": 0.4, "floors": [1, 1, 1, 2],
             "max_house_ft": [90, 90], "backland_ft": 0.0, "backland_min_area_ft2": 400, "shed_detail": 3, "shed_min_area_ft2": 1500, "shed_prob": 0.4},
    "named": {},
}


NAMING_DIR = os.path.join(REPO, "illustrator", "presets", "naming")


def load_naming(params):
    """Naming set for streets, named buildings and district notes (presets/naming/*.json). `naming` in the params may override single
    keys (deep merge), e.g. {"buildings": {"inn": {"name": "The Salted Cod"}}}."""
    nid = params.get("naming_set")
    if not nid:
        nid = "bridgehollow_legacy" if str(params.get("place") or "").startswith("bridgehollow") else "fantasy_generic"
    path = os.path.join(NAMING_DIR, nid + ".json")
    if not os.path.exists(path):
        raise SystemExit(f"unknown naming_set {nid!r}; have {sorted(f[:-5] for f in os.listdir(NAMING_DIR) if f.endswith('.json'))}")
    with open(path, encoding="utf-8") as f:
        base = json.load(f)
    return deep_merge(base, params.get("naming") or {})


def deep_merge(a, b):
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def smoothstep(t):
    t = min(max(t, 0.0), 1.0)
    return t * t * (3 - 2 * t)


def r1(v):
    return round(float(v), 1)


def unit(v):
    n = math.hypot(v[0], v[1]) or 1.0
    return (v[0] / n, v[1] / n)


# ====================================================================== water boundary (swappable)
class Water:
    """Everything the town generator needs to know about water; fill it from any source.

    polygon        shapely geometry of all water surfaces (rivers + lakes + sea + wetlands)
    river_polygon  rivers only (bridgeable)
    rivers         [(LineString centreline downstream-ordered, width_ft, depth_ft or None)]
    lake_levels    [(Polygon, surface elevation ft)] used to flag low ground near lakes as flooded
    """

    def __init__(self):
        self.polygon = Polygon()
        self.river_polygon = Polygon()
        self.rivers = []
        self.lake_levels = []


def load_water(place_dir, path=None):
    """Read world/<place>/water.json (existing schema: entities with id/name/kind/geometry, rivers with `centerline`
    and polygon geometry or width_ft, lakes/sea with polygon geometry and optional `elevation_ft`)."""
    w = Water()
    path = path or os.path.join(place_dir, "water.json")
    if not os.path.exists(path):
        return w
    ents = json.load(open(path, encoding="utf-8")).get("water", [])
    rv, al = [], []
    for e in ents:
        kind, g = e.get("kind", "river"), e.get("geometry", {})
        is_river = kind in ("river", "stream", "creek", "brook")
        poly = None
        cl = e.get("centerline") or (g.get("points") if g.get("type") == "polyline" else None)
        width = e.get("width_ft") or g.get("width_ft")
        if g.get("type") == "polygon" and len(g.get("points", [])) >= 3:
            poly = Polygon(g["points"]).buffer(0)
        elif cl:
            ws = e.get("widths_ft") or ([width] * len(cl) if isinstance(width, (int, float)) else width) or [40] * len(cl)
            poly = unary_union([LineString([cl[i], cl[i + 1]]).buffer(max(ws[i], ws[i + 1]) / 2, cap_style=1)
                                for i in range(len(cl) - 1)])
        if poly is None or poly.is_empty:
            continue
        al.append(poly)
        if is_river:
            rv.append(poly)
            if cl:
                wavg = float(np.mean(e.get("widths_ft") or [width or 40]))
                if not e.get("widths_ft") and not width and g.get("type") == "polygon":
                    wavg = float(poly.area / max(LineString(cl).length, 1.0))     # polygon-only rivers: mean width
                w.rivers.append((LineString(cl), wavg, e.get("depth_ft")))
        elif e.get("elevation_ft", e.get("level_ft")) is not None:
            w.lake_levels.append((poly, float(e.get("elevation_ft", e.get("level_ft")))))
    w.polygon = unary_union(al) if al else Polygon()
    w.river_polygon = unary_union(rv) if rv else Polygon()
    return w


# ====================================================================== raster helpers
def raster_poly(geom, nx, ny, cell):
    img = Image.new("L", (nx, ny), 0)
    d = ImageDraw.Draw(img)
    for g in getattr(geom, "geoms", [geom]):
        if g.is_empty or not isinstance(g, Polygon):
            continue
        d.polygon([(x / cell, y / cell) for x, y in g.exterior.coords], fill=1)
        for hole in g.interiors:
            d.polygon([(x / cell, y / cell) for x, y in hole.coords], fill=0)
    return np.array(img, dtype=bool)


def smooth_noise(rng, shape, period_cells):
    ny, nx = shape
    gy, gx = int(ny / period_cells) + 3, int(nx / period_cells) + 3
    g = rng.uniform(-1, 1, (gy, gx))
    z = ndi.zoom(g, (ny / (gy - 1) * 1.0, nx / (gx - 1) * 1.0), order=3, mode="nearest")[:ny, :nx]
    if z.shape != shape:
        z = np.pad(z, ((0, ny - z.shape[0]), (0, nx - z.shape[1])), mode="edge")
    m = np.abs(z).max()
    return z / m if m else z


def polys_of(g, min_area=0.0):
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g] if g.area >= min_area else []
    return [p for gg in getattr(g, "geoms", []) for p in polys_of(gg, min_area)]


def lines_of(g):
    if g.is_empty:
        return []
    if isinstance(g, LineString):
        return [g]
    return [l for gg in getattr(g, "geoms", []) for l in lines_of(gg)]


def chaikin(pts, n=1):
    pts = [tuple(p) for p in pts]
    for _ in range(n):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            out += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]),
                    (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        out.append(pts[-1])
        pts = out
    return pts


# ====================================================================== the generator
class TownGen:
    def __init__(self, params, place_dir, verbose=True, out_dir=None):
        self.P = params
        self.dir = out_dir or place_dir       # where write() puts the model (a candidate folder in the panel flow)
        self.place_dir = place_dir
        self.verbose = verbose
        self.seed = int(params["seed"])
        self.rng = np.random.default_rng(self.seed)
        self.rand = random.Random(self.seed)
        self.view = viewcfg.load(params["place"], params.get("view_preset", "town"),
                                 scale=params.get("scale_ft_per_in"))
        self.detail = int(params.get("detail", 2))
        self.warnings = []
        L = params["limits"]
        L["min_street_width_ft"] = max(L["min_street_width_ft"], float(self.view.get("min_street_width_ft", 10)))
        self.L = L

        h, meta = params.get("_heightmap") or tr.load_heightmap(params["place"])
        self.h, self.meta, self.cell = h.astype(float), meta, float(meta["cell_ft"])
        self.ny, self.nx = h.shape
        self.sea = float(meta.get("sea_level_ft", params.get("sea_level_ft", 0.0)))
        self.W, self.H = meta["size_ft"]
        if not params["ring_spec"].get("centre"):                      # no hard-coded centre: the middle of the place unless the params say otherwise
            params["ring_spec"]["centre"] = [round(self.W / 2.0), round(self.H / 2.0)]
        self.naming = load_naming(params)
        if not params["entry"].get("name"):
            params["entry"]["name"] = self.naming.get("entry_roads", ["Main Road"])[0]
        import worldio
        self.water = load_water(place_dir, worldio.water_path(params["place"]))
        self.area_info = {"mode": "manual"}
        self.area = self._make_area(params)
        if self.area.is_empty:
            raise SystemExit("town_params.area_ft is empty or invalid")
        self.names_used = set()
        # scale-aware drawing tolerance (the only place the drawing scale touches the model)
        k = float(self.view["scale_ft_per_in"]) / 100.0
        self.simplify = params["streets"].get("simplify_ft") or {1: 5.0, 2: 2.5, 3: 1.2}.get(self.detail, 2.5) * k
        self._grids()

    def _make_area(self, params):
        """area_mode: manual (default; area_ft is used as drawn), auto (terrain-fitted lasso from town_area.py, ignoring
        area_ft), snap (area_ft settled onto the buildable terrain). Parameters in params["area_auto"]."""
        import town_area as ta
        mode = params.get("area_mode") or "manual"
        if mode == "manual" and params.get("area_ft"):
            return Polygon(params["area_ft"]).buffer(0)
        ap = dict(params.get("area_auto") or {})
        ap.setdefault("seed", self.seed)
        rs = params.get("ring_spec") or {}
        user = params.get("area_ft") if mode == "snap" else None
        if mode == "snap" and not user:
            raise SystemExit("area_mode snap needs area_ft")
        res = ta.build(self.h, self.meta, self.water.polygon, ap, ap.get("centre") or rs.get("centre"), user)
        self.area_info = {"mode": mode, "stats": res["stats"], "area_ft": res["area_ft"]}
        return Polygon(res["area_ft"]).buffer(0)

    # ------------------------------------------------------------ grids
    def bil(self, arr, x, y):
        c = self.cell
        fx = min(max(x / c, 0.0), self.nx - 1.001)
        fy = min(max(y / c, 0.0), self.ny - 1.001)
        j, i = int(fx), int(fy)
        tx, ty = fx - j, fy - i
        return ((arr[i, j] * (1 - tx) + arr[i, j + 1] * tx) * (1 - ty) +
                (arr[i + 1, j] * (1 - tx) + arr[i + 1, j + 1] * tx) * ty)

    def height(self, x, y):
        return float(self.bil(self.h, x, y))

    def _grids(self):
        P, L, c = self.P, self.L, self.cell
        ny, nx = self.ny, self.nx
        ys, xs = np.mgrid[0:ny, 0:nx]
        self.X, self.Y = xs * c, ys * c
        self.hs = ndi.gaussian_filter(self.h, 1.5, mode="nearest")
        gy, gx = np.gradient(self.hs, c)
        self.gx, self.gy = gx, gy
        self.slope = np.hypot(gx, gy)
        self.slope_raw = np.hypot(*np.gradient(ndi.gaussian_filter(self.h, 0.7, mode="nearest"), c)[::-1])
        self.area_mask = raster_poly(self.area, nx, ny, c)
        wet_river = raster_poly(self.water.river_polygon, nx, ny, c)
        wet = raster_poly(self.water.polygon, nx, ny, c)
        if L["below_datum_is_water"]:
            dry = np.zeros_like(wet)
            for pts in L["dry_basin_polys"]:
                dry |= raster_poly(Polygon(pts), nx, ny, c)
            wet |= (self.h < self.sea) & ~dry
        for poly, lvl in self.water.lake_levels:
            near = ndi.distance_transform_edt(~raster_poly(poly, nx, ny, c)) * c <= L["flood_ft"]
            wet |= near & (self.h < lvl)
        self.wet, self.wet_river = wet, wet_river
        self.dwater = ndi.distance_transform_edt(~wet) * c
        # deck/bank height: heights with wet cells replaced by the nearest dry height
        dr = ndi.distance_transform_edt(~wet_river) * c
        dil = dr < L["bank_fill_ft"]        # the carved river trench is bridged/filled for road grades
        idx = ndi.distance_transform_edt(dil, return_distances=False, return_indices=True)
        self.hroad = self.hs[idx[0], idx[1]]
        self.hbed = self.h[idx[0], idx[1]]            # raw terrain with the river trench bridged: base for the graded road bed
        # ring radius with organic noise
        rs = self.P["ring_spec"]
        cx, cy = rs["centre"]
        ax, ay = rs.get("aspect", [1, 1])
        n = smooth_noise(self.rng, (ny, nx), rs["noise_period_ft"] / c)
        if rs.get("mode") == "terrain":
            import town_area as ta
            self.r_eff = ta.ring_field(self.h, c, self.wet, rs["centre"], ta.merged(dict(self.P.get("area_auto") or {}, seed=self.seed)),
                                       self.seed, rs["noise"], rs["noise_period_ft"])
        else:
            self.r_eff = np.hypot((self.X - cx) / ax, (self.Y - cy) / ay) * (1 + rs["noise"] * n)
        self.ang_noise = smooth_noise(self.rng, (ny, nx), 260 / c)

    # ------------------------------------------------------------ rings
    def ring_params(self, r):
        rs = self.P["ring_spec"]
        rings = rs["rings"]
        fw = rs["feather_ft"] / 2.0
        i = 0
        while i < len(rings) - 1 and r > rings[i]["r_max"]:
            i += 1
        cur = rings[i]
        out = {k: v for k, v in cur.items()}
        # blend numeric params with the neighbour across a feather band
        nb, t = None, 0.0
        if i < len(rings) - 1 and rings[i]["r_max"] - r < fw:
            nb, t = rings[i + 1], 0.5 * smoothstep((fw - (rings[i]["r_max"] - r)) / fw)
        elif i > 0 and r - rings[i - 1]["r_max"] < fw:
            nb, t = rings[i - 1], 0.5 * smoothstep((fw - (r - rings[i - 1]["r_max"])) / fw)
        if nb is not None:
            for k in ("street_width", "build_prob"):
                out[k] = cur[k] * (1 - t) + nb[k] * t
            for k in ("dsep", "lot_area"):
                out[k] = [cur[k][j] * (1 - t) + nb[k][j] * t for j in (0, 1)]
        out["index"] = i
        return out

    def r_at(self, x, y):
        return float(self.bil(self.r_eff, x, y))

    # ------------------------------------------------------------ main road (A*)
    def astar(self, start, goal, max_grade, bridge_cost, allow_bridge=True):
        c, ny, nx = self.cell, self.ny, self.nx
        si, sj = int(round(start[1] / c)), int(round(start[0] / c))
        gi, gj = int(round(goal[1] / c)), int(round(goal[0] / c))
        slope, hr = self.slope, self.hroad
        blocked = (self.wet & ~self.wet_river) | (self.slope > self.L["hard_slope"])
        if not allow_bridge:
            blocked = blocked | self.wet_river
        outside = ~self.area_mask
        gw, gp = float(self.P["entry"].get("grade_weight", 0.8)), float(self.P["entry"].get("grade_exp", 2.0))
        moves = [(di, dj) for di in range(-4, 5) for dj in range(-4, 5) if (di or dj) and math.gcd(abs(di), abs(dj)) == 1]
        INF = float("inf")
        g = np.full((ny, nx), INF)
        prev = {}
        g[si, sj] = 0.0
        pq = [(0.0, si, sj)]
        while pq:
            f, i, j = heapq.heappop(pq)
            if (i, j) == (gi, gj):
                break
            if f - math.hypot(gi - i, gj - j) * c > g[i, j] + 1e-6:
                continue
            for di, dj in moves:
                a, b = i + di, j + dj
                if not (0 <= a < ny and 0 <= b < nx) or blocked[a, b]:
                    continue
                ln = math.hypot(di, dj) * c
                wet_step = self.wet_river[a, b] or self.wet_river[i, j]
                gr = abs(hr[a, b] - hr[i, j]) / ln
                if gr > max_grade and not wet_step:
                    continue
                sm = 0.5 * (slope[a, b] + slope[i, j])
                m = 1.0 + 25.0 * sm * sm + gw * (gr / max_grade) ** gp
                if wet_step:
                    m += bridge_cost
                if outside[a, b]:
                    m *= 3.0
                ng = g[i, j] + ln * m
                if ng < g[a, b]:
                    g[a, b] = ng
                    prev[(a, b)] = (i, j)
                    heapq.heappush(pq, (ng + math.hypot(gi - a, gj - b) * c, a, b))
        if (gi, gj) not in prev and (si, sj) != (gi, gj):
            raise SystemExit(f"main road: no route from {start} to {goal} under grade {max_grade}")
        path, cur = [], (gi, gj)
        while cur != (si, sj):
            path.append((cur[1] * c, cur[0] * c))
            cur = prev[cur]
        path.append((sj * c, si * c))
        return path[::-1]

    def build_main_road(self):
        E, P = self.P["entry"], self.P
        cx, cy = P["ring_spec"]["centre"]
        pts_wp = [E["point"]] + [list(v) for v in E.get("via", [])] + [[cx, cy]]
        raw = []
        for a, b in zip(pts_wp[:-1], pts_wp[1:]):
            seg = self.astar(a, b, self.L["max_main_grade"], E["bridge_cost_per_ft"])
            raw += seg if not raw else seg[1:]
        ls = LineString(raw)
        n = max(int(ls.length // 10), 4)
        pts = np.array([ls.interpolate(i * ls.length / n).coords[0] for i in range(n + 1)])
        sig = self.P["entry"].get("smooth_samples", 10.0)
        pad = int(sig * 3)
        pp = np.pad(pts, ((pad, pad), (0, 0)), mode="reflect", reflect_type="odd")
        sm = np.stack([ndi.gaussian_filter1d(pp[:, k], sig) for k in (0, 1)], 1)[pad:-pad]
        sm[0], sm[-1] = pts[0], pts[-1]
        need = self.P["entry"]["width_ft"] / 2 + 3
        for _ in range(6):                     # keep the road bed off the bank (except where it crosses the river)
            moved = False
            for i in range(1, len(sm) - 1):
                dw = self.dwater_at(*sm[i])
                if 0.5 < dw < need:
                    gx_ = self.dwater_at(sm[i][0] + 4, sm[i][1]) - self.dwater_at(sm[i][0] - 4, sm[i][1])
                    gy_ = self.dwater_at(sm[i][0], sm[i][1] + 4) - self.dwater_at(sm[i][0], sm[i][1] - 4)
                    n_ = unit((gx_, gy_))
                    sm[i] = (sm[i][0] + n_[0] * (need - dw), sm[i][1] + n_[1] * (need - dw))
                    moved = True
            if not moved:
                break
            sm[1:-1] = np.stack([ndi.gaussian_filter1d(np.pad(sm[:, k], 6, mode="edge"), 1.5)[6:-6] for k in (0, 1)], 1)[1:-1]
        line = LineString(sm).simplify(1.5)
        # split into approach / bridge / approach at river crossings
        pieces = []  # (kind, points)
        riv = self.water.river_polygon.buffer(self.L["bank_margin_ft"] + 10.0) if not self.water.river_polygon.is_empty else None
        if riv is not None and line.intersects(riv):
            inter = lines_of(line.intersection(riv))
            spans = sorted((line.project(Point(g.coords[0])), line.project(Point(g.coords[-1]))) for g in inter)
            spans = [(min(a, b), max(a, b)) for a, b in spans]
            merged = []
            for a, b in spans:
                if merged and a - merged[-1][1] < 25:
                    merged[-1] = (merged[-1][0], b)
                else:
                    merged.append((a, b))
            merged = [(a, b) for a, b in merged if LineString(self._sub(line, a, b)).intersects(self.water.river_polygon)]   # only a real wet crossing needs a bridge: a road that merely brushes the bank margin stays a road
            pos = 0.0
            for a, b in merged:
                if a - pos > 5:
                    pieces.append(("road", self._sub(line, pos, a)))
                pa, pb = line.interpolate(a), line.interpolate(b)
                pieces.append(("bridge", [(pa.x, pa.y), (pb.x, pb.y)]))
                pos = b
            if line.length - pos > 5:
                pieces.append(("road", self._sub(line, pos, line.length)))
        else:
            pieces.append(("road", list(line.coords)))
        self.main_parts = pieces
        self.main_line = LineString([p for k, pts_ in pieces for p in pts_])
        self.main_lines_road = [LineString(p) for k, p in pieces if k == "road"]
        self.log(f"main road {self.main_line.length:.0f} ft, {sum(1 for k, _ in pieces if k == 'bridge')} bridge(s)")

    @staticmethod
    def _sub(line, a, b):
        pts = [line.interpolate(a).coords[0]]
        for x, y in line.coords:
            d = line.project(Point(x, y))
            if a < d < b:
                pts.append((x, y))
        pts.append(line.interpolate(b).coords[0])
        return pts

    # ------------------------------------------------------------ tensor field
    def build_field(self):
        S, c = self.P["streets"], self.cell
        cx, cy = self.P["ring_spec"]["centre"]
        ny, nx = self.ny, self.nx
        C2 = np.zeros((ny, nx))
        S2 = np.zeros((ny, nx))

        def add(theta, w):
            nonlocal C2, S2
            C2 = C2 + w * np.cos(2 * theta)
            S2 = S2 + w * np.sin(2 * theta)

        th_ring = np.arctan2(self.Y - cy, self.X - cx) + math.pi / 2
        th_ring = th_ring + math.radians(S["noise_angle_deg"]) * self.ang_noise
        add(th_ring, S["ring_weight"] * (0.2 + np.exp(-self.r_eff / 500.0)))
        # global grid aligned with the overall approach direction (entry -> centre), bent by the noise field
        e0 = self.P["entry"]["point"]
        th_grid = math.atan2(cy - e0[1], cx - e0[0]) + math.radians(S["noise_angle_deg"]) * self.ang_noise * 1.4
        add(th_grid, S.get("grid_weight", 0.9))

        def nearest_dir(lines, decay, weight):
            if not lines:
                return
            img = Image.new("F", (nx, ny), 999.0)
            mask = Image.new("L", (nx, ny), 0)
            dm = ImageDraw.Draw(mask)
            ang = np.full((ny, nx), 0.0)
            ang_img = Image.new("F", (nx, ny), 0.0)
            da = ImageDraw.Draw(ang_img)
            for ln in lines:
                pts = list(ln.coords)
                for a, b in zip(pts[:-1], pts[1:]):
                    th = math.atan2(b[1] - a[1], b[0] - a[0])
                    seg = [(a[0] / c, a[1] / c), (b[0] / c, b[1] / c)]
                    dm.line(seg, fill=1, width=1)
                    da.line(seg, fill=th, width=1)
            m = np.array(mask, dtype=bool)
            angs = np.array(ang_img)
            if not m.any():
                return
            dist, idx = ndi.distance_transform_edt(~m, return_indices=True)
            th = angs[idx[0], idx[1]]
            add(th, weight * np.exp(-dist * c / decay))

        nearest_dir(self.main_lines_road, S["road_decay_ft"], S["road_weight"])
        nearest_dir([r[0] for r in self.water.rivers], S["river_decay_ft"], S["river_weight"])
        th_c = np.arctan2(self.gy, self.gx) + math.pi / 2
        sl = np.clip((self.slope - S["slope_lo"]) / (S["slope_hi"] - S["slope_lo"]), 0, 1)
        add(th_c, S["contour_weight"] * sl * sl * (3 - 2 * sl))
        self.C2, self.S2 = C2, S2

    def heading(self, x, y, fam):
        a = 0.5 * math.atan2(self.bil(self.S2, x, y), self.bil(self.C2, x, y))
        if fam == 1:
            a += math.pi / 2
        return (math.cos(a), math.sin(a))

    def grade_limit(self, x, y, d, gmax):
        gx, gy = self.bil(self.gx, x, y), self.bil(self.gy, x, y)
        gm = math.hypot(gx, gy)
        if gm < 1e-9:
            return d
        dd = gx * d[0] + gy * d[1]
        if abs(dd) <= gmax:
            return d
        ux, uy = gx / gm, gy / gm
        tx, ty = -uy, ux
        if tx * d[0] + ty * d[1] < 0:
            tx, ty = -tx, -ty
        s = math.copysign(gmax / gm, dd)
        co = math.sqrt(max(1 - s * s, 0.0))
        return (co * tx + s * ux, co * ty + s * uy)

    # ------------------------------------------------------------ streamlines
    def ok_point(self, x, y, half_w):
        if not (0 <= x <= self.W and 0 <= y <= self.H):
            return False
        i, j = int(round(y / self.cell)), int(round(x / self.cell))
        i, j = min(i, self.ny - 1), min(j, self.nx - 1)
        if not self.area_mask[i, j] or self.wet[i, j] or self.dwater[i, j] < half_w + 3:
            return False
        return self.slope_raw[i, j] < self.L["hard_slope"]

    def trace_streams(self):
        S, L = self.P["streets"], self.L
        step = S["step_ft"]
        HS = 40.0
        hashg = {}

        def hkey(x, y):
            return int(x // HS), int(y // HS)

        def register(pts, fam, lid):
            for k, (x, y) in enumerate(pts):
                a, b = pts[max(k - 1, 0)], pts[min(k + 1, len(pts) - 1)]
                t = unit((b[0] - a[0], b[1] - a[1]))
                hashg.setdefault(hkey(x, y), []).append((x, y, fam, lid, k, t[0], t[1]))

        def near(x, y, fam, dtest, own, own_skip, main_dtest, dirv=None):
            kx, ky = hkey(x, y)
            rr = int(max(dtest, main_dtest) // HS) + 1
            best = None
            for a in range(kx - rr, kx + rr + 1):
                for b in range(ky - rr, ky + rr + 1):
                    for (px, py, f, lid, k, tx_, ty_) in hashg.get((a, b), ()):
                        d = math.hypot(px - x, py - y)
                        lim = main_dtest if f == 9 else (dtest if f == fam else 0)
                        if f != fam and f != 9 and dirv is not None and abs(tx_ * dirv[0] + ty_ * dirv[1]) > 0.88:
                            lim = dtest * 0.7          # a different family running parallel and close: merge, do not double up
                        if d < lim and (best is None or d < best[0]):
                            best = (d, px, py)
            if best is None and own is not None:
                for k, (px, py) in enumerate(own[:-own_skip] if own_skip else own):
                    if math.hypot(px - x, py - y) < dtest * 0.9:
                        return (0.0, px, py)
            return best

        # main road points act as family 9 (all families stop/join)
        mp = []
        for ln in self.main_lines_road:
            n = int(ln.length // step) + 1
            mp += [ln.interpolate(i * ln.length / max(n, 1)).coords[0] for i in range(n + 1)]
        register(mp, 9, -1)
        lines = []  # {pts, fam}

        def dsep_at(x, y, fam):
            rp = self.ring_params(self.r_at(x, y))
            return rp["dsep"][fam] * (S["cross_dsep_factor"] if fam == 1 else 1.0), rp

        def trace(p0, fam, sign):
            ds, rp = dsep_at(p0[0], p0[1], fam)
            pts = [p0]
            prev = None
            skip = int(3 * ds / step)
            for it in range(400):
                x, y = pts[-1]
                ds, rp = dsep_at(x, y, fam)
                gmax = L["max_street_grade"] * S.get("trace_grade_margin", 1.0)
                d = self.heading(x, y, fam)
                if prev is None:
                    d = (d[0] * sign, d[1] * sign)
                elif d[0] * prev[0] + d[1] * prev[1] < 0:
                    d = (-d[0], -d[1])
                d = self.grade_limit(x, y, d, gmax)
                xm, ym = x + d[0] * step / 2, y + d[1] * step / 2
                d2 = self.heading(xm, ym, fam)
                if d2[0] * d[0] + d2[1] * d[1] < 0:
                    d2 = (-d2[0], -d2[1])
                d2 = self.grade_limit(xm, ym, d2, gmax)
                nxp, nyp = x + d2[0] * step, y + d2[1] * step
                hw = rp["street_width"] / 2
                if not self.ok_point(nxp, nyp, hw):
                    return pts, "edge"
                hit = near(nxp, nyp, fam, 0.5 * ds, pts, skip, 0.45 * ds, d2)
                if hit is not None:
                    pts.append((hit[1], hit[2]))
                    return pts, "hit"
                pts.append((nxp, nyp))
                prev = d2
            return pts, "len"

        cx, cy = self.P["ring_spec"]["centre"]
        dmin = min(min(r["dsep"]) for r in self.P["ring_spec"]["rings"])
        sp = dmin * 0.5
        seeds = []
        gx0 = self.area.bounds
        jit = S["seed_jitter"]
        for yy in np.arange(gx0[1], gx0[3], sp):
            for xx in np.arange(gx0[0], gx0[2], sp):
                x = xx + self.rng.uniform(-jit, jit) * sp
                y = yy + self.rng.uniform(-jit, jit) * sp
                if self.area.contains(Point(x, y)):
                    seeds.append((self.r_at(x, y), x, y))
        seeds.sort()
        nid = 0
        for _, x, y in seeds:
            for fam in (0, 1):
                ds, rp = dsep_at(x, y, fam)
                if not self.ok_point(x, y, rp["street_width"] / 2):
                    continue
                if near(x, y, fam, ds, None, 0, 0.5 * ds) is not None:
                    continue
                fwd, why = trace((x, y), fam, 1)
                closed = why == "hit" and len(fwd) > 12 and math.hypot(fwd[-1][0] - x, fwd[-1][1] - y) < 2 * step and False
                bwd, _ = trace((x, y), fam, -1)
                pts = bwd[::-1] + fwd[1:]
                if len(pts) < 3:
                    continue
                ln = LineString(pts)
                if ln.length < max(S["min_length_ft"], 0.8 * ds):
                    continue
                nid += 1
                register(pts, fam, nid)
                lines.append({"pts": pts, "fam": fam, "w": rp["street_width"] * (1.0 if fam == 0 else 0.85)})
        self.log(f"streamlines: {len(lines)}")
        return lines

    # ------------------------------------------------------------ street assembly
    def assemble_streets(self, lines):
        S, L = self.P["streets"], self.L
        geoms = []
        for ln in lines:
            pts = list(LineString(ln["pts"]).simplify(self.simplify).coords)
            pts = chaikin(pts, S["chaikin"] + (1 if self.detail >= 3 else 0))
            geoms.append({"line": LineString(pts), "fam": ln["fam"], "w": max(L["min_street_width_ft"], ln["w"]),
                          "kind": "street"})
        # snap loose ends onto the nearest other line
        for i, g in enumerate(geoms):
            others = [o["line"] for j, o in enumerate(geoms) if j != i] + self.main_lines_road
            if not others:
                continue
            u = unary_union(others)
            pts = list(g["line"].coords)
            for end in (0, -1):
                p = Point(pts[end])
                if u.distance(p) < 0.5:
                    continue
                if not self.area.buffer(-6).contains(p):
                    continue
                q = nearest_points(u, p)[0]
                dist = p.distance(q)
                ds = self.ring_params(self.r_at(p.x, p.y))["dsep"][g["fam"]]
                dh = abs(float(self.bil(self.hs, q.x, q.y)) - float(self.bil(self.hs, p.x, p.y)))
                if dist < min(S["snap_ft"], 0.75 * ds) and self.dwater_at(q.x, q.y) > 4 and dh / max(dist, 1) <= L["max_street_grade"]:
                    if end == 0:
                        pts.insert(0, (q.x, q.y))
                    else:
                        pts.append((q.x, q.y))
            pts = self.trim_steep_ends(list(LineString(pts).segmentize(8.0).coords))
            g["line"] = self.smooth_line(LineString(pts).simplify(0.6), S.get("smooth_sigma_ft", 0.0))
        if not self.water.polygon.is_empty:           # streets never enter water (plus half their width and a margin)
            wb = self.water.polygon
            out = []
            for g in geoms:
                clipped = g["line"].difference(wb.buffer(g["w"] / 2 + 2.0))
                for part in lines_of(clipped):
                    out.append({**g, "line": part})
            geoms = out
        if S.get("edge_inset"):          # streets stop inside the organic boundary (their width never pokes out of it)
            out = []
            for g in geoms:
                if self.area.buffer(-(g["w"] / 2 + 2.0)).contains(g["line"]):
                    out.append(g)
                    continue
                for part in lines_of(g["line"].intersection(self.area.buffer(-(g["w"] / 2 + 2.0)))):
                    out.append({**g, "line": part})
            geoms = out
        geoms = [g for g in geoms if g["line"].length >= S["min_length_ft"] * 0.6]
        return geoms

    @staticmethod
    def smooth_line(ln, sigma_ft, step=5.0):
        """Gaussian-smooth a street centreline (ends pinned) to remove the zig-zag the heading search leaves on rough ground."""
        if not sigma_ft or ln.length < 4 * step:
            return ln
        n = int(ln.length // step) + 1
        ss = np.linspace(0.0, ln.length, n + 1)
        pts = np.array([ln.interpolate(v).coords[0] for v in ss])
        k = max(sigma_ft / (ln.length / n), 0.5)
        pad = int(k * 3) + 2
        pp = np.pad(pts, ((pad, pad), (0, 0)), mode="reflect", reflect_type="odd")
        sm = np.stack([ndi.gaussian_filter1d(pp[:, c], k) for c in (0, 1)], 1)[pad:-pad]
        sm[0], sm[-1] = pts[0], pts[-1]
        return LineString(sm).simplify(0.3)

    def trim_steep_ends(self, pts, win=40.0):
        """Drop end vertices while the last `win` feet climb steeper than 1.25x the street grade cap."""
        G = self.L["max_street_grade"] * 1.08
        pts = list(pts)
        for end in (0, -1):
            while len(pts) > 4:
                seq = pts if end == 0 else pts[::-1]
                acc, k = 0.0, 0
                while k < len(seq) - 1 and acc < win:
                    acc += math.hypot(seq[k + 1][0] - seq[k][0], seq[k + 1][1] - seq[k][1])
                    k += 1
                if acc < win * 0.6:
                    break
                dh = abs(float(self.bil(self.hbed, *seq[0])) - float(self.bil(self.hbed, *seq[k])))
                if dh / acc <= G:
                    break
                pts.pop(0 if end == 0 else -1)
        return pts

    def dwater_at(self, x, y):
        return float(self.bil(self.dwater, x, y))

    def prune_connected(self, geoms, extra):
        """Keep only streets connected (touching) to the main road / plazas."""
        roots = list(self.main_lines_road) + [LineString(b) for k, b in self.main_parts if k == "bridge"] + extra
        pieces = [g["line"] for g in geoms]
        n = len(pieces)
        parent = list(range(n + len(roots)))

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        allg = pieces + roots
        tree = STRtree(allg)
        for i, g in enumerate(allg):
            for j in tree.query(g.buffer(1.5) if i < n else g):
                if j != i and allg[j].distance(g) < 1.5:
                    parent[find(i)] = find(j)
        base = find(n) if roots else find(0)
        rootset = {find(n + k) for k in range(len(roots))}
        keep = [g for i, g in enumerate(geoms) if find(i) in rootset]
        self.log(f"streets kept {len(keep)}/{n} (connected to the main road)")
        return keep

    def split_steep(self, geoms, _depth=0):
        """Cut out interior stretches whose raw-terrain grade over 40 ft exceeds streets.split_steep_factor x cap (0 = off).
        What is left is stub-cleaned and re-pruned by the caller; a street never keeps a stretch the cut/fill limit cannot fix."""
        f = float(self.P["streets"].get("split_steep_factor", 0.0))
        if not f:
            return geoms
        lim = self.L["max_street_grade"] * f
        out, n = [], 0
        for g in geoms:
            ln = g["line"]
            ss = np.arange(0.0, ln.length + 1e-6, 5.0)
            if len(ss) < 10:
                out.append(g)
                continue
            el = np.array([float(self.bil(self.hbed, *ln.interpolate(v).coords[0])) for v in ss])
            bad = np.zeros(len(ss), bool)
            for i in range(len(ss) - 8):
                if abs(el[i + 8] - el[i]) / 40.0 > lim:
                    bad[i:i + 9] = True
            if not bad.any():
                out.append(g)
                continue
            n += 1
            i = 0
            while i < len(ss):
                if bad[i]:
                    i += 1
                    continue
                j = i
                while j < len(ss) and not bad[j]:
                    j += 1
                a, b = ss[i], ss[j - 1]
                if b - a >= max(self.P["streets"]["min_length_ft"] * 0.6, 40.0):
                    out.append({**g, "line": LineString([ln.interpolate(v).coords[0] for v in np.arange(a, b, 5.0)] + [ln.interpolate(b).coords[0]]).simplify(0.15)})
                i = j
        self.log(f"split {n} streets at steep stretches (raw grade over {lim:.3f})")
        return self.split_steep(out, _depth + 1) if n and _depth < 3 else out

    def clean_network(self, geoms, plaza_polys):
        """Remove stub streets (short, one free end) and thin loops/teardrops (small or very pointed faces) so the
        network reads as a grown street plan. streets.stub_min_ft / loop_max_area_ft2 / loop_compact; 0 disables."""
        from shapely.ops import polygonize
        S = self.P["streets"]
        smin, lmax = float(S.get("stub_min_ft", 0.0)), float(S.get("loop_max_area_ft2", 0.0))
        if not smin and not lmax:
            return geoms
        fixed = list(self.main_lines_road) + [LineString(b) for k, b in self.main_parts if k == "bridge"]
        fixed += [LineString(p.exterior.coords) for p in plaza_polys]
        inner = self.area.buffer(-10)
        geoms = list(geoms)
        removed = 0
        for _ in range(6):
            changed = False
            if smin:
                for i, g in enumerate(geoms):
                    ln = g["line"]
                    if ln.length >= smin:
                        continue
                    others = unary_union([o["line"] for j, o in enumerate(geoms) if j != i] + fixed)
                    ends = [Point(ln.coords[0]), Point(ln.coords[-1])]
                    dang = [others.distance(e) > 6.0 and inner.contains(e) for e in ends]
                    if any(dang):
                        geoms.pop(i)
                        changed = True
                        removed += 1
                        break
            if changed:
                continue
            if lmax:
                faces = list(polygonize(unary_union([g["line"] for g in geoms] + fixed)))
                for f in faces:
                    if f.area > lmax * 4 or any(p.intersects(f.buffer(-1)) for p in plaza_polys):
                        continue
                    compact = 4 * math.pi * f.area / max(f.length ** 2, 1.0)
                    if not (f.area < lmax or compact < S.get("loop_compact", 0.3)):
                        continue
                    cand = [(k, g) for k, g in enumerate(geoms) if g["line"].buffer(2.0).intersection(f.exterior).length > 12.0]
                    if not cand:
                        continue
                    k, _ = min(cand, key=lambda kg: kg[1]["line"].length)
                    geoms.pop(k)
                    changed = True
                    removed += 1
                    break
            if not changed:
                break
        self.log(f"network cleanup: removed {removed} stub/loop streets")
        return geoms

    def cut_main(self, poly):
        """The main road ends at the plaza edge instead of running through it."""
        new = []
        for kind, pts in self.main_parts:
            if kind == "road":
                rest = lines_of(LineString(pts).difference(poly.buffer(0.2)))
                new += [("road", list(l.coords)) for l in rest if l.length > 8]
            else:
                new.append((kind, pts))
        self.main_parts = new
        self.main_lines_road = [LineString(p) for k, p in new if k == "road"]

    # ------------------------------------------------------------ plazas
    def make_plazas(self, geoms):
        PZ = self.P["plazas"]
        out = []
        if not (PZ["enabled"] and self.P["output"]["plazas"]):
            return out
        area_ft2 = self.area.area
        if area_ft2 < PZ["min_area_ft2"]:
            self.log(f"area {area_ft2:.0f} ft2 below plaza threshold {PZ['min_area_ft2']}: no plazas")
            return out
        count = min(PZ["max"], 1 + int((area_ft2 - PZ["min_area_ft2"]) // PZ["per_area_ft2"]))
        nodes = []
        all_lines = [g["line"] for g in geoms]
        tree = STRtree(all_lines)
        for i, a in enumerate(all_lines):
            for j in tree.query(a):
                if j > i:
                    x = a.intersection(all_lines[j])
                    for pt in ([x] if isinstance(x, Point) else [p for p in getattr(x, "geoms", []) if isinstance(p, Point)]):
                        nodes.append((pt.x, pt.y))
        for ln in self.main_lines_road:
            for g in all_lines:
                x = ln.intersection(g)
                for pt in ([x] if isinstance(x, Point) else [p for p in getattr(x, "geoms", []) if isinstance(p, Point)]):
                    nodes.append((pt.x, pt.y))
        nodes = [n for n in nodes if self.slope[int(n[1] // self.cell), int(n[0] // self.cell)] < 0.05
                 and self.r_at(*n) < self.P["ring_spec"]["rings"][-2]["r_max"] and self.dwater_at(*n) > 50]
        anchors = list(PZ.get("anchors", []))
        cut_main_ids = self.cut_main_ids = []
        rmin, rmax = PZ["radius_ft"]
        placed = []
        for k in range(count):
            r = self.rand.uniform(rmin, rmax)
            if k >= len(anchors) and PZ.get("extra_radius_ft"):
                r = self.rand.uniform(*PZ["extra_radius_ft"])          # later squares (not the named anchors) can be smaller
            nm, pid, c = None, None, None
            if k < len(anchors):
                a = anchors[k]
                nm, pid = a["name"], a["id"]
                near_pt = Point(a["near"])
                if a.get("type") == "road_end":
                    c = tuple(self.main_line.coords[-1])
                    cut_main_ids.append(pid)
                elif a.get("type", "junction") == "road":
                    ml = unary_union(self.main_lines_road)
                    q = nearest_points(ml, near_pt)[0]
                    v = unit((near_pt.x - q.x, near_pt.y - q.y))
                    off = r + self.P["entry"]["width_ft"] / 2 + 3
                    c = (q.x + v[0] * off, q.y + v[1] * off)
                    # slide along the road if the spot is in water / out of area
                    for sh in (0, 40, -40, 80, -80, 120, -120):
                        t = unit((-v[1], v[0]))
                        cc = (c[0] + t[0] * sh, c[1] + t[1] * sh)
                        if self.ok_point(*cc, 2) and self.dwater_at(*cc) > r + 8:
                            c = cc
                            break
                else:
                    cand = [n for n in nodes if all(math.hypot(n[0] - p[0], n[1] - p[1]) > PZ["min_sep_ft"] * 0.6 for p in placed)]
                    c = min(cand, key=lambda n: math.hypot(n[0] - a["near"][0], n[1] - a["near"][1])) if cand else None
            else:
                nm, pid = f"Square {k + 1}", f"sqr_{k + 1}"
                cand = [n for n in nodes if all(math.hypot(n[0] - p[0], n[1] - p[1]) > PZ["min_sep_ft"] for p in placed)]
                if cand:
                    cx, cy = self.P["ring_spec"]["centre"]
                    # farthest-point style: maximise distance to the other plazas, mild pull toward the centre
                    c = max(cand, key=lambda n: min([math.hypot(n[0] - p[0], n[1] - p[1]) for p in placed] or [0])
                            - 0.3 * math.hypot(n[0] - cx, n[1] - cy))
            if c is None:
                continue
            m = 24
            nz = self.rng.uniform(-1, 1, m // 4 + 2)
            pts = []
            for i in range(m):
                ph = i / m * (len(nz) - 2)
                a0, f = int(ph), ph - int(ph)
                rn = nz[a0] * (1 - f) + nz[a0 + 1] * f
                ang = 2 * math.pi * i / m
                rr = r * (1 + 0.14 * rn)
                pts.append((c[0] + rr * math.cos(ang), c[1] + rr * math.sin(ang)))
            poly = Polygon(pts).buffer(0)
            poly = poly.difference(self.water.polygon.buffer(self.L["water_margin_ft"])).intersection(self.area)
            ps = polys_of(poly, 400)
            if not ps:
                continue
            poly = max(ps, key=lambda p: p.area)
            placed.append(c)
            out.append({"id": pid, "name": nm, "poly": poly, "centre": c})
        self.log(f"plazas: {[p['name'] for p in out]} (area {area_ft2:.0f} ft2)")
        return out

    # ------------------------------------------------------------ blocks / lots / buildings
    def street_polys(self, geoms):
        polys = []
        for g in geoms:
            polys.append(g["line"].buffer(g["w"] / 2, cap_style=2, join_style=1, resolution=4))
        for ln in self.main_lines_road:
            polys.append(ln.buffer(self.P["entry"]["width_ft"] / 2, cap_style=2, join_style=1, resolution=4))
        return polys

    def make_blocks(self, street_union, plazas):
        obst = [street_union] + [p["poly"] for p in plazas]
        if not self.water.polygon.is_empty:
            obst.append(self.water.polygon.buffer(self.L["water_margin_ft"]))
        free = self.area.difference(unary_union(obst))
        blocks = polys_of(free.buffer(-0.5).buffer(0.5), 250)
        blocks.sort(key=lambda p: (round(p.centroid.y), p.centroid.x))
        return blocks

    def split_piece(self, piece, amax, bend, spread, jitter):
        """Recursive OBB cutting. Yields leaf polygons."""
        out, stack = [], [(piece, 0)]
        while stack:
            p, depth = stack.pop()
            c = p.centroid
            rp = self.ring_params(self.r_at(c.x, c.y))
            lo, hi = rp["lot_area"]
            target = hi * (1 + self.rand.uniform(-0.1, 0.1))
            if p.area <= target or depth > 9:
                out.append(p)
                continue
            obb = p.minimum_rotated_rectangle
            co = list(obb.exterior.coords)[:4]
            e1, e2 = (co[1][0] - co[0][0], co[1][1] - co[0][1]), (co[2][0] - co[1][0], co[2][1] - co[1][1])
            if math.hypot(*e1) < math.hypot(*e2):
                e1, e2 = e2, e1
            u = unit(e1)
            ang = math.radians(self.rand.uniform(-jitter, jitter))
            u = (u[0] * math.cos(ang) - u[1] * math.sin(ang), u[0] * math.sin(ang) + u[1] * math.cos(ang))
            n = (-u[1], u[0])
            ctr = obb.centroid
            ln = math.hypot(*e1)
            s = self.rand.uniform(-spread, spread) * ln
            q = (ctr.x + u[0] * s, ctr.y + u[1] * s)
            B = 2000.0
            bd = self.rand.uniform(-bend, bend)
            P0 = (q[0] - n[0] * B, q[1] - n[1] * B)
            P1 = (q[0] + u[0] * bd, q[1] + u[1] * bd)
            P2 = (q[0] + n[0] * B, q[1] + n[1] * B)
            A = Polygon([P0, P1, P2, (P2[0] + u[0] * B, P2[1] + u[1] * B), (P0[0] + u[0] * B, P0[1] + u[1] * B)])
            Bp = Polygon([P0, P1, P2, (P2[0] - u[0] * B, P2[1] - u[1] * B), (P0[0] - u[0] * B, P0[1] - u[1] * B)])
            kids = polys_of(p.intersection(A), 1) + polys_of(p.difference(A), 1)
            kids = [k for k in kids if k.area > 1]
            if len(kids) < 2:
                out.append(p)
                continue
            for k in kids:
                stack.append((k, depth + 1))
        return out

    def footprint(self, lot, street_union, wf, df, setback, minsize=(16, 14), maxsize=(90, 90), fixed=None, rot_jit=3.0):
        """Rectangle inside `lot` facing the nearest street point. fixed=(w,d) overrides the fractions."""
        if lot.is_empty:
            return None
        inner = lot.buffer(-1.5, join_style=2)
        if not inner.is_empty:
            ps = polys_of(inner, 20)
            lot = max(ps, key=lambda p: p.area) if ps else lot
        obb = lot.minimum_rotated_rectangle
        co = list(obb.exterior.coords)[:4]
        e1, e2 = unit((co[1][0] - co[0][0], co[1][1] - co[0][1])), unit((co[2][0] - co[1][0], co[2][1] - co[1][1]))
        ctr = obb.centroid
        q = nearest_points(street_union, ctr)[0] if not street_union.is_empty else Point(ctr.x, ctr.y + 1)
        v = unit((q.x - ctr.x, q.y - ctr.y))
        axes = [(e1, 0), (e2, 1)]
        best = max(axes, key=lambda a: abs(a[0][0] * v[0] + a[0][1] * v[1]))
        f = best[0]
        if f[0] * v[0] + f[1] * v[1] < 0:
            f = (-f[0], -f[1])
        l = (-f[1], f[0])
        # extents of OBB along f (depth) and l (width)
        dl = math.hypot(co[1][0] - co[0][0], co[1][1] - co[0][1]); dm = math.hypot(co[2][0] - co[1][0], co[2][1] - co[1][1])
        Df, Wl = (dl, dm) if best[1] == 0 else (dm, dl)
        rp_ = lot.representative_point()
        for mode in ("front", "centre"):
            for shrink in (1.0, 0.92, 0.84, 0.76, 0.68, 0.6, 0.52, 0.45):
                if fixed:
                    w, d = min(fixed[0], Wl * 0.95) * shrink, min(fixed[1], Df * 0.95) * shrink
                else:
                    w = min(max(Wl * self.rand.uniform(*wf), minsize[0]), maxsize[0], Wl * 0.95) * shrink
                    d = min(max(Df * self.rand.uniform(*df), minsize[1]), maxsize[1], Df * 0.95) * shrink
                if w < minsize[0] * 0.7 or d < minsize[1] * 0.7:
                    break
                if mode == "front":
                    cb = (ctr.x + f[0] * (Df / 2 - setback - d / 2) + l[0] * self.rand.uniform(-1, 1) * max(Wl - w, 0) * 0.25,
                          ctr.y + f[1] * (Df / 2 - setback - d / 2) + l[1] * self.rand.uniform(-1, 1) * max(Wl - w, 0) * 0.25)
                else:
                    cb = (lot.centroid.x, lot.centroid.y) if lot.contains(lot.centroid) else (rp_.x, rp_.y)
                pts = [(cb[0] + sa * l[0] * w / 2 + sb * f[0] * d / 2, cb[1] + sa * l[1] * w / 2 + sb * f[1] * d / 2)
                       for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                rect = Polygon(pts)
                if rot_jit and mode == "front":
                    rect = affinity.rotate(rect, self.rand.uniform(-rot_jit, rot_jit), origin=(cb[0], cb[1]))
                if lot.buffer(0.3).contains(rect):
                    return rect
        return None

    def terrain_ok(self, poly, max_slope, max_relief, extra_margin=0.0):
        """No building on steep ground / in water (checks corners, edge midpoints and centre)."""
        pts = list(poly.exterior.coords)[:-1]
        samples = pts + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(pts, pts[1:] + pts[:1])]
        samples.append((poly.centroid.x, poly.centroid.y))
        hs_, sl = [], 0.0
        for x, y in samples:
            i, j = min(int(round(y / self.cell)), self.ny - 1), min(int(round(x / self.cell)), self.nx - 1)
            if self.wet[i, j] or not self.area_mask[i, j]:
                return None
            if self.dwater[i, j] < self.L["bank_margin_ft"] + extra_margin:
                return None
            sl = max(sl, float(self.slope_raw[i, j]))
            hs_.append(self.height(x, y))
        if sl > max_slope or (max(hs_) - min(hs_)) > max_relief:
            return None
        return {"site_slope": round(sl, 3), "relief": round(max(hs_) - min(hs_), 1), "elev": round(float(np.mean(hs_)), 1)}

    # ------------------------------------------------------------ main pipeline
    def log(self, *a):
        if self.verbose:
            print(*a)

    def run(self):
        P = self.P
        self.build_main_road()
        self.build_field()
        lines = self.trace_streams()
        geoms = self.assemble_streets(lines)
        plazas = self.make_plazas(geoms)
        # cut streets by plazas (streets end at the square edge)
        cut = []
        pz_union = unary_union([p["poly"] for p in plazas]) if plazas else None
        for g in geoms:
            ln = g["line"]
            if pz_union is not None and ln.intersects(pz_union):
                for part in lines_of(ln.difference(pz_union.buffer(0.2))):
                    if part.length >= 25:
                        cut.append({**g, "line": part})
            else:
                cut.append(g)
        for pl in plazas:
            if pl["id"] in getattr(self, "cut_main_ids", []):
                self.cut_main(pl["poly"])
        cut = self.clean_network(self.split_steep(cut), [p["poly"] for p in plazas])
        geoms = self.prune_connected(cut, [p["poly"] for p in plazas])
        # drop streets that mostly run through water margin / outside the area
        self.streets = geoms
        self.plazas = plazas
        spolys = self.street_polys(geoms)
        self.street_union = unary_union(spolys)
        self.blocks = self.make_blocks(self.street_union, plazas)
        self.log(f"blocks: {len(self.blocks)}")
        self.make_lots_and_buildings()
        return self

    # ------------------------------------------------------------ lots, fields, buildings
    def make_lots_and_buildings(self):
        LT, L = self.P["lots"], self.L
        self.lots, self.fields, self.buildings = [], [], []
        sset = self.street_union
        sbuf = sset.buffer(1.2)
        for blk in self.blocks:
            for lot in self.split_piece(blk, None, LT["field_bend_ft"], LT["spread"], LT["angle_jitter_deg"]):
                if lot.area < 150:
                    continue
                c = lot.centroid
                rp = self.ring_params(self.r_at(c.x, c.y))
                front = lot.boundary.intersection(sbuf).length
                self.lots.append({"poly": lot, "c": (c.x, c.y), "r": self.r_at(c.x, c.y), "kind": rp["kind"],
                                  "ring": rp["id"], "rp": rp, "front": front, "area": lot.area, "used": False})
        self.log(f"lots: {len(self.lots)}")
        self.place_named()
        self.place_houses()
        self.place_fields()

    # --- named buildings
    def lot_ok(self, lot, min_area=0, need_front=True):
        return (not lot["used"] and lot["area"] >= min_area and (lot["front"] >= LT_MIN(self) or not need_front)
                and lot["kind"] != "farm")

    def terr(self, poly):
        return self.terrain_ok(poly, self.L["max_build_slope"], self.L["max_build_relief_ft"])

    def add_building(self, id_, name, kind, poly, notes="", floors=1, extra=None):
        t = self.terr(poly) if (extra or {}).get("check", True) else {"site_slope": 0.0, "relief": 0.0, "elev": self.height(poly.centroid.x, poly.centroid.y)}
        if t is None:
            return None
        pts = [[r1(x), r1(y)] for x, y in list(poly.exterior.coords)[:-1]]
        e = {"id": id_, "name": name, "kind": kind, "status": "proposed",
             "geometry": {"type": "polygon", "points": pts}, "notes": notes,
             "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
             "floors": floors, "rooms": [], "doors": [], "elevation_ft": t["elev"], "site_slope": t["site_slope"],
             "site_relief_ft": t["relief"]}
        self.buildings.append({"e": e, "poly": poly})
        return e

    def place_named(self):
        N = self.P["named"]
        cx, cy = self.P["ring_spec"]["centre"]
        LT = self.P["lots"]
        su = self.street_union
        pz = [p for p in self.plazas]
        main_u = unary_union(self.main_lines_road)
        bridge_pts = [b[0] for k, b in self.main_parts if k == "bridge"]
        self.named_ids = {}

        def dist_c(l):
            return math.hypot(l["c"][0] - cx, l["c"][1] - cy)

        def place(key, id_, name, kind, size, cands, score, notes="", floors=1):
            """size=(w,d) target footprint; cands filtered lots; pick best score (lower is better)."""
            tries = sorted(cands, key=score)
            for lot in tries[:12]:
                fp = self.footprint(lot["poly"], su, (1, 1), (1, 1), self.rand.uniform(*LT["front_setback_ft"]),
                                    minsize=(8, 8), maxsize=(200, 200), fixed=size, rot_jit=0.0)
                if fp is None:
                    continue
                e = self.add_building(id_, name, kind, fp, notes, floors)
                if e is not None:
                    lot["used"] = True
                    self.named_ids[key] = (lot, e)
                    return lot, e
            self.warnings.append(f"could not place {id_}")
            return None, None

        def free(minarea, kinds=None, need_front=True):
            return [l for l in self.lots if not l["used"] and l["area"] >= minarea and l["kind"] != "farm"
                    and (l["front"] >= LT["min_frontage_ft"] or not need_front) and (kinds is None or l["kind"] in kinds)]

        def elev(l):
            return self.height(*l["c"])

        NB, road = self.naming["buildings"], self.P["entry"]["name"]
        skip = set(N.get("skip") or [])

        def nb(key):
            d = NB[key]
            return d["id"], d["name"], d.get("notes", "").replace("{road}", road)

        # town hall: biggest-lot class near the centre, highest ground
        s = N.get("warden_hall", {"size": [60, 50]})
        lot, hall_c = None, (cx, cy)
        if "hall" not in skip:
            i_, n_, t_ = nb("hall")
            lot, e = place("hall", i_, n_, "civic", s["size"],
                           free(s["size"][0] * s["size"][1] * 0.75),
                           lambda l: dist_c(l) - elev(l) * 0.6, t_, 2)
            hall_c = lot["c"] if lot else (cx, cy)
        s = N.get("magistrate_court", {"size": [62, 48]})
        cp = [p for p in pz if p["id"] == N.get("court_plaza", "sqr_court")]
        pc = cp[0]["poly"] if cp else Point(cx, cy)
        if "court" not in skip:
            i_, n_, t_ = nb("court")
            place("court", i_, n_, "civic", s["size"],
                  free(s["size"][0] * s["size"][1] * 0.75, ["civic", "residential"]),
                  lambda l: Point(l["c"]).distance(pc) + 0.2 * math.hypot(l["c"][0] - hall_c[0], l["c"][1] - hall_c[1]),
                  t_, 2)
        s = N.get("tax_office", {"size": [50, 40]})
        bp = bridge_pts[0] if bridge_pts else (cx, cy)
        if "tax" not in skip:
            i_, n_, t_ = nb("tax")
            place("tax", i_, n_, "civic", s["size"],
                  free(s["size"][0] * s["size"][1] * 0.75),
                  lambda l: Point(l["c"]).distance(main_u) + 0.3 * math.hypot(l["c"][0] - bp[0], l["c"][1] - bp[1]),
                  t_)
        s = N.get("lockup", {"size": [36, 30]})
        if "lockup" not in skip:
            i_, n_, t_ = nb("lockup")
            place("lockup", i_, n_, "civic", s["size"], free(s["size"][0] * s["size"][1] * 0.75),
                  lambda l: math.hypot(l["c"][0] - hall_c[0], l["c"][1] - hall_c[1]), t_)
        mk = [p for p in pz if p["id"] == N.get("market_plaza", "sqr_market")]
        mpoly = mk[0]["poly"] if mk else Point(cx, cy)
        s = N.get("inn", {"size": [62, 34]})
        lot = None
        if "inn" not in skip:
            i_, n_, t_ = nb("inn")
            lot, e = place("inn", i_, n_, "inn", s["size"], free(s["size"][0] * s["size"][1] * 0.8, ["residential", "civic"]),
                           lambda l: Point(l["c"]).distance(mpoly) + 1.5 * Point(l["c"]).distance(main_u), t_, 2)
        if lot and "stables" not in skip:
            s = N.get("stables", {"size": [54, 24]})
            i_, n_, t_ = nb("stables")
            place("stables", i_, n_, "stable", s["size"], free(s["size"][0] * s["size"][1] * 0.75),
                  lambda l: math.hypot(l["c"][0] - lot["c"][0], l["c"][1] - lot["c"][1]), t_)
        s = N.get("meeting_hall", {"size": [60, 44]})
        if "meeting" not in skip:
            i_, n_, t_ = nb("meeting")
            place("meeting", i_, n_, "civic", s["size"], free(s["size"][0] * s["size"][1] * 0.75, ["residential", "civic"]),
                  lambda l: Point(l["c"]).distance(mpoly) + 0.1 * dist_c(l), t_)
        s = N.get("smithy", {"size": [40, 30]})
        if "smithy" not in skip:
            i_, n_, t_ = nb("smithy")
            ring_ft = float(s.get("ring_ft", 300))
            place("smithy", i_, n_, "craft", s["size"], free(s["size"][0] * s["size"][1] * 0.75, ["residential"]),
                  lambda l: abs(dist_c(l) - ring_ft) * 0.5 + abs(self.dwater_at(*l["c"]) - 60), t_)
        for j, x in enumerate(N.get("extra_civic", [])):                  # more civic buildings round the hall: [{id,name,size,floors,notes,near}]
            sz = x.get("size", [44, 34])
            place("civic_%d" % j, x["id"], x["name"], "civic", sz, free(sz[0] * sz[1] * 0.75, ["civic", "residential"]),
                  lambda l, x=x: math.hypot(l["c"][0] - hall_c[0], l["c"][1] - hall_c[1]) + (Point(l["c"]).distance(pc) * 0.3 if x.get("near") == "court" else 0)
                  + (0 if su.distance(Point(l["c"])) < 30 else 60), x.get("notes", ""), x.get("floors", 1))
        # gate watch: beside the main road near the entry
        ent = Point(self.P["entry"]["point"])
        g0 = self.main_lines_road[0] if self.main_lines_road else None
        if g0 is not None and "gate" not in skip:
            for dd in (70, 90, 120, 160):
                q = g0.interpolate(dd)
                q2 = g0.interpolate(dd + 5)
                t = unit((q2.x - q.x, q2.y - q.y))
                nrm = (-t[1], t[0])
                for sd in (1, -1):
                    off = self.P["entry"]["width_ft"] / 2 + 8 + 12
                    cb = (q.x + nrm[0] * off * sd, q.y + nrm[1] * off * sd)
                    rect = Polygon([(cb[0] + a * t[0] * 13 + b * nrm[0] * 12, cb[1] + a * t[1] * 13 + b * nrm[1] * 12)
                                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
                    if rect.intersects(self.street_union) or self.water.polygon.distance(rect) < 10:
                        continue
                    if self.add_building(*nb("gate")[:2], "civic", rect, nb("gate")[2]) is not None:
                        self.named_ids["gate"] = (None, None)
                        break
                if "gate" in self.named_ids:
                    break
        if "mill" not in skip and self.water.rivers:
            self.place_mill()

    def place_mill(self):
        N = self.P["named"].get("mill", {"size": [44, 32]})
        size = N["size"]
        cx, cy = self.P["ring_spec"]["centre"]
        target_down = N.get("downstream_ft", 420)
        best = None
        for rl, wd, _ in self.water.rivers:
            pts_ = np.linspace(0, rl.length, int(rl.length // 20) + 1)
            for d in pts_:
                p, q = rl.interpolate(d), rl.interpolate(min(d + 8, rl.length))
                t = unit((q.x - p.x, q.y - p.y))
                nrm = (-t[1], t[0])
                for sd, extra in ((1, 14), (-1, 14), (1, 26), (-1, 26), (1, 40), (-1, 40)):
                    off = wd / 2 + extra + size[1] / 2
                    cb = (p.x + nrm[0] * off * sd, p.y + nrm[1] * off * sd)
                    rect = Polygon([(cb[0] + a * t[0] * size[0] / 2 + b * nrm[0] * size[1] / 2,
                                     cb[1] + a * t[1] * size[0] / 2 + b * nrm[1] * size[1] / 2)
                                    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
                    if not self.area.contains(rect) or rect.intersects(self.street_union):
                        continue
                    if any(rect.intersects(b["poly"].buffer(6)) for b in self.buildings):
                        continue
                    if any(rect.intersects(p_["poly"]) for p_ in self.plazas):
                        continue
                    if self.terrain_ok(rect, self.L["max_build_slope"], self.L["max_build_relief_ft"] * 1.4) is None:
                        continue
                    ds = math.hypot(cb[0] - cx, cb[1] - cy)
                    sd_ = self.street_union.distance(rect)
                    score = abs(cb[1] - (cy + target_down)) + 0.6 * sd_
                    if best is None or score < best[0]:
                        best = (score, rect)
        if best is None:
            self.warnings.append("could not place bld_mill")
            return
        t = self.terrain_ok(best[1], self.L["max_build_slope"], self.L["max_build_relief_ft"] * 1.4)
        pts = [[r1(x), r1(y)] for x, y in list(best[1].exterior.coords)[:-1]]
        mid_, mname_, mnote_ = self.naming["buildings"]["mill"]["id"], self.naming["buildings"]["mill"]["name"], self.naming["buildings"]["mill"].get("notes", "")
        e = {"id": mid_, "name": mname_, "kind": "craft", "status": "proposed",
             "geometry": {"type": "polygon", "points": pts}, "notes": mnote_,
             "links": self.links(), "floors": 2, "rooms": [], "doors": [], "elevation_ft": t["elev"],
             "site_slope": t["site_slope"], "site_relief_ft": t["relief"]}
        self.buildings.append({"e": e, "poly": best[1]})

    def place_houses(self):
        LT = self.P["lots"]
        if self.detail < 1 or not self.P["output"]["buildings"]:
            return
        su = self.street_union
        n = 0
        order = sorted([l for l in self.lots if not l["used"] and l["kind"] != "farm"], key=lambda l: (round(l["c"][1]), l["c"][0]))
        for lot in order:
            if self.detail == 1 and lot["kind"] != "civic":
                continue
            rp = lot["rp"]
            if lot["front"] < LT["min_frontage_ft"] and not (
                    LT["backland_ft"] and lot["area"] >= LT["backland_min_area_ft2"] and lot["poly"].distance(su) <= LT["backland_ft"]):
                continue
            bp = rp["build_prob"]
            if LT.get("edge_fade_ft") and lot["kind"] != "civic":       # lots thin out and break up toward the organic boundary
                bp *= 0.25 + 0.75 * smoothstep(self.area.exterior.distance(Point(lot["c"])) / LT["edge_fade_ft"])
            if self.rand.random() > bp:
                continue
            fp = self.footprint(lot["poly"], su, LT["house_fill_w"], LT["house_fill_d"],
                                self.rand.uniform(*LT["front_setback_ft"]), tuple(LT["min_house_ft"]),
                                maxsize=tuple(LT["max_house_ft"]))
            if fp is None:
                continue
            n += 1
            e = self.add_building(f"bld_house_{n:03d}", f"House {n}", "house", fp, floors=self.rand.choice(LT["floors"]))
            if e is None:
                n -= 1
                continue
            lot["used"] = True
            if self.detail >= LT["shed_detail"] and lot["area"] > LT["shed_min_area_ft2"] and self.rand.random() < LT["shed_prob"]:
                rest = lot["poly"].difference(fp.buffer(5))
                ps = polys_of(rest, 200)
                if ps:
                    sh = self.footprint(max(ps, key=lambda p: p.area), su, (0.3, 0.5), (0.3, 0.5), 2, (8, 8), (14, 14), rot_jit=0)
                    if sh is not None:
                        self.add_building(f"bld_shed_{n:03d}", f"Shed {n}", "shed", sh, floors=1)
        self.house_count = n

    def place_fields(self):
        LT, L = self.P["lots"], self.L
        if not self.P["output"]["fields"]:
            return
        su = self.street_union
        sbuf = su.buffer(38)
        gentle = self.gentle_polygon()
        n = 0
        fn = 0
        for lot in sorted([l for l in self.lots if not l["used"] and l["kind"] == "farm"], key=lambda l: (round(l["c"][1]), l["c"][0])):
            poly = lot["poly"]
            if poly.area < 5000:
                continue
            poly = poly.intersection(gentle)
            ps0 = polys_of(poly, 4000)
            if not ps0:
                continue
            poly = max(ps0, key=lambda p: p.area)
            fld = poly.buffer(-LT["field_hedge_ft"]).buffer(0)
            ps = polys_of(fld, 3000)
            if not ps:
                continue
            fld = max(ps, key=lambda p: p.area)
            # farmstead on the street-facing strip
            if self.detail >= 2 and self.P["output"]["buildings"] and lot["front"] > 40 and self.rand.random() < LT["farmstead_prob"] * lot["rp"]["build_prob"] / 0.3:
                strip = polys_of(fld.intersection(sbuf), 2500)
                if strip:
                    st = max(strip, key=lambda p: p.area)
                    fp = self.footprint(st, su, (0.2, 0.35), (0.3, 0.5), 8, (22, 24), (36, 36))
                    if fp is not None:
                        n += 1
                        e = self.add_building(f"bld_farm_{n:03d}", f"Farmhouse {n}", "farmhouse", fp, floors=self.rand.choice([1, 2]))
                        if e is not None:
                            rest = polys_of(st.difference(fp.buffer(10)), 1200)
                            if rest:
                                bf = self.footprint(max(rest, key=lambda p: p.area), su, (0.3, 0.5), (0.3, 0.5), 6, (24, 30), (46, 46))
                                if bf is not None:
                                    self.add_building(f"bld_barn_{n:03d}", f"Barn {n}", "barn", bf)
                            yard = unary_union([b["poly"] for b in self.buildings if b["e"]["id"].endswith(f"{n:03d}") and
                                                (b["e"]["id"].startswith("bld_farm_") or b["e"]["id"].startswith("bld_barn_"))]).buffer(10)
                            fl = polys_of(fld.difference(yard), 3000)
                            if fl:
                                fld = max(fl, key=lambda p: p.area)
            lot["used"] = True
            fn += 1
            self.fields.append({"id": f"fld_{fn:03d}", "poly": fld})
        self.log(f"fields: {len(self.fields)}, farmsteads: {n}")

    def gentle_polygon(self):
        """Polygon of ground flat enough for fields (slope, water, bank margin), from the raster."""
        import contourpy
        ok = (self.slope_raw < self.L["max_field_slope"]) & ~self.wet & (self.dwater > 8) & self.area_mask
        ok = ndi.binary_opening(ok, iterations=2)
        z = np.pad(ndi.gaussian_filter(ok.astype(float), self.L.get("field_smooth_cells", 0.0)) if self.L.get("field_smooth_cells") else ok.astype(float), 1)
        xs = (np.arange(self.nx + 2) - 1) * self.cell
        ys = (np.arange(self.ny + 2) - 1) * self.cell
        gen = contourpy.contour_generator(xs, ys, z, fill_type=contourpy.FillType.OuterCode)
        pts, codes = gen.filled(0.5, 1.5 if not self.L.get("field_smooth_cells") else 9.0)
        polys = []
        for pa, ca in zip(pts, codes):
            starts = [i for i, c in enumerate(ca) if c == 1] + [len(ca)]
            rings = [pa[starts[k]:starts[k + 1]] for k in range(len(starts) - 1)]
            rings = [r for r in rings if len(r) >= 4]
            if rings:
                polys.append(Polygon(rings[0], rings[1:]).buffer(0))
        g = unary_union(polys) if polys else Polygon()
        return g.buffer(-4).buffer(4).intersection(self.area)

    def cells_stats(self, poly):
        c = self.cell
        minx, miny, maxx, maxy = poly.bounds
        i0, i1 = max(int(miny // c), 0), min(int(maxy // c) + 2, self.ny)
        j0, j1 = max(int(minx // c), 0), min(int(maxx // c) + 2, self.nx)
        img = Image.new("L", (j1 - j0, i1 - i0), 0)
        d = ImageDraw.Draw(img)
        for g in polys_of(poly):
            d.polygon([(x / c - j0, y / c - i0) for x, y in g.exterior.coords], fill=1)
        m = np.array(img, dtype=bool)
        if not m.any():
            return 0.0, 1.0
        sl = self.slope_raw[i0:i1, j0:j1][m]
        wet = self.wet[i0:i1, j0:j1][m]
        ok = (~wet) & (sl < self.L["max_field_slope"]) & (self.dwater[i0:i1, j0:j1][m] > 6)
        return float(ok.mean()), float(sl.max())

    # ------------------------------------------------------------ outputs
    def street_name(self, ring, fam, idx):
        bank = self.naming["streets"][ring]
        k = 0
        while True:
            nm = bank[(idx + k) % len(bank)] + ("" if (idx + k) < len(bank) else f" {(idx + k) // len(bank) + 1}")
            if nm not in self.names_used:
                self.names_used.add(nm)
                return nm
            k += 1

    def elev_line(self, pts, bridge=False):
        if bridge:
            a, b = pts[0], pts[-1]
            ha, hb = float(self.bil(self.hroad, *a)), float(self.bil(self.hroad, *b))
            n = len(pts)
            return [r1(ha + (hb - ha) * i / max(n - 1, 1)) for i in range(n)]
        return [r1(float(self.bil(self.hroad, x, y))) for x, y in pts]    # graded road bed = smoothed terrain

    def bed_profile(self, pts):
        """Graded road bed: the terrain profile along the street (river trench bridged) smoothed over about 45 ft, with
        cut and fill limited to limits.max_cut_fill_ft. Returns (bed elevations at the vertices, terrain elevations at the
        vertices, max |cut or fill| in ft)."""
        d = [0.0]
        for a, b in zip(pts[:-1], pts[1:]):
            d.append(d[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        terr_v = [float(self.bil(self.hbed, x, y)) for x, y in pts]
        if d[-1] < 10:
            return terr_v, terr_v, 0.0
        ln = LineString(pts)
        ss = np.linspace(0.0, d[-1], max(int(d[-1] // 5) + 1, 3))
        terr = np.array([float(self.bil(self.hbed, *ln.interpolate(v).coords[0])) for v in ss])
        cut = float(self.L.get("max_cut_fill_ft", 3.0))
        b = terr.copy()
        for _ in range(30):
            b = ndi.uniform_filter1d(b, 9, mode="nearest")
            b = np.clip(b, terr - cut, terr + cut)
        bed_v = np.interp(d, ss, b)
        return [float(v) for v in bed_v], terr_v, float(np.abs(b - terr).max())

    @staticmethod
    def grade_of(pts, el, win=40.0):
        """Max grade over any `win`-ft stretch, profile resampled every 5 ft (vertex spacing would hide steep bits)."""
        d = [0.0]
        for a, b in zip(pts[:-1], pts[1:]):
            d.append(d[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        if d[-1] < win * 0.7:
            return 0.0
        ss = np.arange(0.0, d[-1] + 1e-6, 5.0)
        e = np.interp(ss, d, el)
        k = max(int(round(win / 5.0)), 1)
        if len(e) <= k:
            k = len(e) - 1
            if k < 1 or k * 5.0 < win * 0.7:
                return 0.0
        return round(float(np.abs(e[k:] - e[:-k]).max() / (k * 5.0)), 3)

    def links(self):
        return {"foundry_scene": None, "model3d": None, "ai_layer": None}

    def to_model(self):
        P = self.P
        sid = []
        E = P["entry"]
        ents = []
        for k, (kind, pts) in enumerate(self.main_parts):
            pts = [[r1(x), r1(y)] for x, y in pts]
            br = kind == "bridge"
            el = self.elev_line(pts, br)
            if not br:
                bed, terr_v, cutfill = self.bed_profile(pts)
                el = [r1(v) for v in bed]
            idn = f"str_{E['id']}_{k + 1}" if not br else f"str_{E['id']}_bridge" if sum(1 for q, _ in self.main_parts if q == "bridge") == 1 else f"str_{E['id']}_bridge_{k + 1}"
            nm = E["name"] + (" (bridge)" if br else "")
            if br:
                m_ = re.match(r"^(.*?)\s+(Road|Street|Way|Highway|Lane)$", E["name"])
                nm = E.get("bridge_name") or ((m_.group(1) + " Bridge") if m_ else nm)
            e = {"id": idn, "name": nm, "kind": "bridge" if br else "road", "status": "proposed",
                 "geometry": {"type": "polyline", "points": pts, "width_ft": E["bridge_width_ft"] if br else E["width_ft"]},
                 "notes": "Main road in from the entry." if not br else "The one stone bridge over the river.",
                 "links": self.links(), "elevations_ft": el, "elevation_ft": r1(float(np.mean(el))),
                 "grade_max": 0.0 if br else self.grade_of(pts, el)}
            if not br:
                e["grade_raw_max"] = self.grade_of(pts, [r1(v) for v in terr_v])
                e["cut_fill_ft"] = r1(cutfill)
            if br:
                e["material"] = "stone"
            ents.append(e)
        order = sorted(self.streets, key=lambda g: (round(g["line"].centroid.y / 60), g["line"].centroid.x))
        counters = {"civic": 0, "residential": 0, "farm": 0}
        for g in order:
            ln = g["line"]
            c = ln.interpolate(0.5, normalized=True)
            rp = self.ring_params(self.r_at(c.x, c.y))
            pts = [[r1(x), r1(y)] for x, y in ln.coords]
            el, terr_v, cutfill = self.bed_profile(pts)
            el = [r1(v) for v in el]
            counters[rp["kind"]] += 1
            n = len(ents) + 1
            nm = self.street_name(rp["kind"], g["fam"], counters[rp["kind"]] - 1) if ln.length > 120 else f"Alley {n}"
            kind = "street" if g["w"] >= 16 else "lane"
            ents.append({"id": f"str_{n:03d}", "name": nm, "kind": kind, "status": "proposed",
                         "geometry": {"type": "polyline", "points": pts, "width_ft": r1(g["w"])},
                         "notes": f"{rp['name']}; {'follows the contours' if g['fam'] == 0 else 'runs across the slope'}.",
                         "links": self.links(), "elevations_ft": el, "elevation_ft": r1(float(np.mean(el))),
                         "grade_max": self.grade_of(pts, el), "grade_raw_max": self.grade_of(pts, [r1(v) for v in terr_v]),
                         "cut_fill_ft": r1(cutfill), "ring": rp["id"]})
        self.street_ents = ents
        return ents

    def _label_pt(self, pg, toward=None):
        """Label anchor: representative point clear of the plazas; with `toward` (x, y), the point of the district
        nearest that spot, so a ring's label sits on its side of the ward instead of on top of the ward label."""
        pz = unary_union([p["poly"].buffer(45) for p in self.plazas]) if self.plazas else Polygon()
        g = pg.difference(pz)
        ps = polys_of(g, 500)
        big = max(ps, key=lambda p: p.area) if ps else pg
        if toward is not None:
            inner = big.buffer(-18)
            if not inner.is_empty:
                q = nearest_points(inner, Point(toward))[0]
                return [r1(q.x), r1(q.y)]
        q = big.representative_point()
        return [r1(q.x), r1(q.y)]

    def _ring_label_target(self, i, r):
        rs = self.P["ring_spec"]
        if i == 0 or r["kind"] == "farm":
            return None
        cx, cy = rs["centre"]
        ax = rs.get("aspect", [1, 1])[0]
        mid = 0.5 * (rs["rings"][i - 1]["r_max"] + r["r_max"])
        return (cx - mid * ax, cy)

    def district_ents(self):
        P = self.P
        out = []
        rs = P["ring_spec"]
        cx, cy = rs["centre"]
        import contourpy
        gen = contourpy.contour_generator(np.arange(self.nx) * self.cell, np.arange(self.ny) * self.cell,
                                          ndi.gaussian_filter(self.r_eff, 1.5))
        regions = {}
        for r in rs["rings"][:-1]:
            ls = gen.lines(r["r_max"])
            polys = [Polygon(a).buffer(0) for a in ls if len(a) > 8 and np.allclose(a[0], a[-1])]
            polys = [p for p in polys if p.contains(Point(cx, cy))]
            regions[r["id"]] = max(polys, key=lambda p: p.area).intersection(self.area) if polys else self.area    # no closed contour: the ring reaches past the area, so it is the whole area
        prev = None
        names = {r["id"]: r for r in rs["rings"]}
        for i, r in enumerate(rs["rings"]):
            if r["id"] in regions:
                g = regions[r["id"]]
                g_ = g.difference(prev) if prev is not None else g
                prev = g if prev is None else prev.union(g)
            else:
                g_ = self.area.difference(prev) if prev is not None else self.area
            ps = polys_of(g_.buffer(-0.5).buffer(0.5), 2000)
            if not ps:
                continue
            ps.sort(key=lambda p: -p.area)
            for k, pg in enumerate(ps[:3]):
                pg = pg.simplify(2.0)
                pts = [[r1(x), r1(y)] for x, y in list(pg.exterior.coords)[:-1]]
                out.append({"id": f"dis_{r['id']}" + ("" if k == 0 else f"_{k + 1}"), "name": r["name"], "kind": "district",
                            "status": "proposed", "geometry": {"type": "polygon", "points": pts},
                            "notes": self.naming["district_notes"][r["kind"]],
                            "links": self.links(), "ring": r["id"], "label_point": self._label_pt(pg, self._ring_label_target(i, r)) if k == 0 else self._label_pt(pg),
                            "elevation_ft": r1(self.height(*pg.representative_point().coords[0]))})
        for p in self.plazas:
            pts = [[r1(x), r1(y)] for x, y in list(p["poly"].simplify(0.8).exterior.coords)[:-1]]
            out.append({"id": p["id"], "name": p["name"], "kind": "square", "status": "proposed",
                        "geometry": {"type": "polygon", "points": pts}, "notes": "Open plaza grown at a junction.",
                        "links": self.links(), "elevation_ft": r1(self.height(*p["centre"]))})
        for f in self.fields:
            pts = [[r1(x), r1(y)] for x, y in list(f["poly"].simplify(1.0).exterior.coords)[:-1]]
            out.append({"id": f["id"], "name": "Field " + f["id"][-3:], "kind": "field", "status": "proposed",
                        "geometry": {"type": "polygon", "points": pts}, "notes": "Irregular field parcel.",
                        "links": self.links(), "elevation_ft": r1(self.height(*f["poly"].representative_point().coords[0]))})
        if P["output"]["blocks"]:
            for i, b in enumerate(self.blocks):
                if self.ring_params(self.r_at(b.centroid.x, b.centroid.y))["kind"] == "farm":
                    continue
                pts = [[r1(x), r1(y)] for x, y in list(b.simplify(0.8).exterior.coords)[:-1]]
                out.append({"id": f"blk_{i + 1:03d}", "name": f"Block {i + 1}", "kind": "block", "status": "proposed",
                            "geometry": {"type": "polygon", "points": pts}, "notes": "", "links": self.links(),
                            "elevation_ft": r1(self.height(b.centroid.x, b.centroid.y))})
        return out

    def write(self):
        d = self.dir
        streets = self.to_model()
        districts = self.district_ents()
        bdir = os.path.join(d, "buildings")
        os.makedirs(bdir, exist_ok=True)
        for f in os.listdir(bdir):
            if f.startswith("bld_") and f.endswith(".json"):
                os.remove(os.path.join(bdir, f))
        ids = set()
        for b in self.buildings:
            e = b["e"]
            assert e["id"] not in ids, e["id"]
            ids.add(e["id"])
            with open(os.path.join(bdir, e["id"] + ".json"), "w", encoding="utf-8") as f:
                json.dump(e, f, indent=1)
                f.write("\n")

        def save(name, data):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                json.dump(data, f, indent=1)
                f.write("\n")

        save("streets.json", {"place": self.P["place"], "streets": streets})
        save("districts.json", {"place": self.P["place"], "districts": districts})
        pp = os.path.join(d, "place.json")
        if not os.path.exists(pp) and os.path.exists(os.path.join(self.place_dir, "place.json")):
            pp = os.path.join(self.place_dir, "place.json")   # candidate folder: start from the world place.json
        place = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {"id": self.P["place"]}
        pp = os.path.join(d, "place.json")
        place.update({"notes": f"DRAFT organic town generated by illustrator/generators/town_gen.py from town_params.json "
                               f"(seed {self.seed}). No canon layout exists; every entity is proposed.",
                      "generated_by": "town_gen.py", "sea_level_ft": self.sea})
        place["files"] = {"districts": "districts.json", "streets": "streets.json", "water": "water.json",
                          "buildings": "buildings/", "view_settings": "view_settings.json", "terrain": "terrain/",
                          "params": "town_params.json"}
        save("place.json", place)
        rep = self.report(streets, districts)
        save("town_gen_report.json", rep)
        self.log(json.dumps(rep["counts"]))
        return rep

    def area_report(self):
        import town_area as ta
        st = ta.stats(self.h, self.cell, self.area, ta.merged(dict(self.P.get("area_auto") or {})))
        st["mode"] = self.area_info.get("mode", "manual")
        return st

    def report(self, streets, districts):
        bl = [b["poly"] for b in self.buildings]
        issues = []
        wp = self.water.polygon
        for b in self.buildings:
            e = b["e"]
            if not wp.is_empty and b["poly"].intersects(wp):
                issues.append(f"{e['id']} intersects water")
            if e["site_slope"] > self.L["max_build_slope"]:
                issues.append(f"{e['id']} slope {e['site_slope']}")
            if self.street_union.intersects(b["poly"]) and e["kind"] not in ("civic",):
                if self.street_union.intersection(b["poly"]).area > 1.0:
                    issues.append(f"{e['id']} overlaps a street")
        for s_ in streets:
            if s_["kind"] != "bridge" and not wp.is_empty:
                ln = LineString(s_["geometry"]["points"]).buffer(s_["geometry"]["width_ft"] / 2 - 1.0)
                if ln.intersects(wp) and ln.intersection(wp).area > 3.0:
                    issues.append(f"{s_['id']} runs into water ({ln.intersection(wp).area:.0f} ft2)")
        cap = self.L["max_street_grade"]
        over = [f"{s_['id']} {s_['grade_max']}" for s_ in streets if s_["kind"] != "bridge" and s_["grade_max"] > cap]
        if over:
            self.warnings.append("street grade (graded bed, 40 ft window) over cap %.3f: " % cap + ", ".join(over))
        rawo = [f"{s_['id']} {s_['grade_raw_max']}" for s_ in streets if s_["kind"] != "bridge" and s_.get("grade_raw_max", 0) > cap]
        mx = max([s["grade_max"] for s in streets if s["kind"] != "bridge"] or [0])
        mxr = max([s.get("grade_raw_max", 0) for s in streets if s["kind"] != "bridge"] or [0])
        slen = sum(LineString(s["geometry"]["points"]).length for s in streets if s["kind"] != "bridge")
        olen = sum(LineString(s["geometry"]["points"]).length for s in streets if s["kind"] != "bridge" and s["grade_max"] > cap)
        kinds = {}
        for b in self.buildings:
            kinds[b["e"]["kind"]] = kinds.get(b["e"]["kind"], 0) + 1
        return {"seed": self.seed, "detail": self.detail, "scale_ft_per_in": self.view["scale_ft_per_in"],
                "sea_level_ft": self.sea, "area": self.area_report(), "warnings": self.warnings, "issues": issues,
                "counts": {"streets": len(streets), "buildings": len(self.buildings), "fields": len(self.fields),
                           "plazas": len(self.plazas), "blocks": len(self.blocks), "by_kind": kinds},
                "street_grade_max": mx, "street_grade_raw_max": mxr, "street_grade_cap": cap,
                "streets_over_cap_bed": len(over), "streets_over_cap_raw": len(rawo), "street_length_ft": round(slen),
                "street_length_over_cap_ft": round(olen),
                "max_cut_fill_ft": max([s.get("cut_fill_ft", 0) for s in streets] or [0])}


def LT_MIN(g):
    return g.P["lots"]["min_frontage_ft"]


def load_params(path):
    user = json.load(open(path, encoding="utf-8"))
    p = deep_merge(DEFAULTS, user)
    if "area_file" in user:
        ap = user["area_file"] if os.path.isabs(user["area_file"]) else os.path.join(os.path.dirname(path), user["area_file"])
        p["area_ft"] = json.load(open(ap, encoding="utf-8"))
    p["_user_streets"] = user.get("streets", {})
    return p


def generate(params_path, overrides=None, verbose=True, heightmap=None, place_dir=None, out_dir=None):
    p = load_params(params_path)
    if heightmap is not None:
        p["_heightmap"] = heightmap
    for k, v in (overrides or {}).items():
        if v is not None:
            p[k] = v
    place_dir = place_dir or os.path.dirname(os.path.abspath(params_path))
    g = TownGen(p, place_dir, verbose, out_dir).run()
    return g


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--params")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--detail", type=int)
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-dir", help="write the model here instead of world/<place> (candidate; panel Accept copies it over)")
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"])
    ap.add_argument("--water-source", choices=["world", "working"])
    a = ap.parse_args()
    import worldio
    worldio.set_source(a.terrain_source, a.water_source)
    pp = a.params or os.path.join(REPO, "world", a.place, "town_params.json")
    g = generate(pp, {"seed": a.seed, "detail": a.detail, "view_preset": a.preset, "scale_ft_per_in": a.scale},
                 place_dir=os.path.join(REPO, "world", a.place), out_dir=a.out_dir)
    if not a.dry_run:
        g.write()
