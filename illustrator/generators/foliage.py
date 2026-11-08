"""Foliage: data model (world/<place>/foliage.json), rule-based scatter, 2D symbols, performance merge for Foundry 3D Canvas.

  python foliage.py species                                   # library (presets/foliage/*.json) with triangle counts per LOD
  python foliage.py scatter  --place P --params params.json   # polygon / line scatter -> foliage.json (zone replaced, hand-placed trees kept)
  python foliage.py add      --place P --species oak --x 120 --y 80 [--scale 1.1 --rot 30]
  python foliage.py clear    --place P --polygon poly.json [--all | --zone Z | --species a,b]
  python foliage.py stats    --place P                         # counts per species, triangles / draw calls unmerged
  python foliage.py draw     --place P [--view town --preset .. --scale .. --page WxH --out-dir D]   # 2D symbol SVG for the 'DETAILS - Foliage' layer
  python foliage.py preview  --place P [--out png]             # top-down preview PNG (terrain shade, buildings, roads, water, symbols)
  python foliage.py export   --place P                         # world/<place>/scatter/foliage.json (feeds the world pack 'foliage' entities, same ids)
  python foliage.py merge    --place P [--pack DIR] [--chunk-ft 150] [--budget TRIS] [--impostor-beyond-ft F] [--lod1-beyond-ft F] [--compress none|quant|meshopt]
  python foliage.py publish  --place P --scene-uuid Scene.x [--dry-run]

Everything is feet in the repo frame (x east, y SOUTH, z up) in the file; meshes are metres in the pack's Blender frame (worldpack.Frame).
Entity ids are stable: fol_<zone>_<nnnn>, counters are kept in the file and never reused, so regenerating or clearing never renames a neighbour.
The merge writes per-chunk GLBs (all species of a spatial cell as ONE mesh and ONE material), see WORLD_PACK.md and out/foliage_notes.md.
"""
import argparse
import json
import math
import os
import shutil
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foliage_mesh as fm  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FORMAT = "varrenmoor-foliage"
FT = 0.3048
HA_FT2 = 107639.1


def _jload(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        if d is not None:
            return d
        raise


def _jdump(p, o):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1)
        f.write("\n")
    os.replace(tmp, p)


def slug(t):
    import re
    return re.sub(r"[^a-z0-9_]+", "_", str(t).lower()).strip("_") or "x"


def h01(*parts):
    return (zlib.crc32("|".join(str(p) for p in parts).encode()) & 0xFFFFFFFF) / 4294967296.0


# ------------------------------------------------------------------ data model
class FoliageDoc:
    """world/<place>/foliage.json: {format, version, place, units, counters{zone:n}, zones[{id,name,params,seed,count}], items[...]}.
    item: {id, species, x, y, z, scale, rot, variant, zone, src: generated|hand, locked?}"""

    def __init__(self, place, path=None, data=None):
        self.place = place
        self.path = path or os.environ.get("VB_FOLIAGE_JSON") or os.path.join(REPO, "world", place, "foliage.json")
        d = data if data is not None else _jload(self.path, {})
        self.counters = dict(d.get("counters", {}))
        self.zones = {z["id"]: z for z in d.get("zones", [])}
        self.items = {i["id"]: i for i in d.get("items", [])}

    def to_json(self):
        return {"format": FORMAT, "version": 1, "place": self.place, "units": "ft", "frame": "world feet: x east, y south, z up (elevation)",
                "counters": dict(sorted(self.counters.items())), "zones": sorted(self.zones.values(), key=lambda z: z["id"]),
                "items": sorted(self.items.values(), key=lambda i: i["id"])}

    def save(self):
        _jdump(self.path, self.to_json())
        return self.path

    def next_id(self, zone):
        n = self.counters.get(zone, 0) + 1
        self.counters[zone] = n
        return f"fol_{zone}_{n:04d}"

    def add_items(self, zone, items, src="generated"):
        out = []
        for it in items:
            it = dict(it)
            it["id"] = it.get("id") or self.next_id(zone)
            it["zone"], it["src"] = zone, it.get("src", src)
            self.items[it["id"]] = it
            out.append(it)
        return out

    def zone_items(self, zone, src=None):
        return [i for i in self.items.values() if i["zone"] == zone and (src is None or i["src"] == src)]

    def remove(self, ids):
        n = 0
        for i in list(ids):
            if self.items.pop(i, None) is not None:
                n += 1
        return n

    def clear(self, polygon=None, zone=None, species=None, include_hand=False):
        """Remove items inside `polygon` (feet), optionally of one zone / species list; hand-placed ones stay unless include_hand."""
        from shapely.geometry import Polygon
        import shapely
        sel = [i for i in self.items.values() if (zone is None or i["zone"] == zone) and (not species or i["species"] in species) and (include_hand or i["src"] != "hand")
               and not i.get("locked")]
        if polygon is not None and sel:
            pg = Polygon(polygon).buffer(0)
            m = shapely.contains_xy(pg, np.array([i["x"] for i in sel]), np.array([i["y"] for i in sel]))
            sel = [i for i, k in zip(sel, m) if k]
        return self.remove([i["id"] for i in sel])

    def stats(self, lib, lod=0):
        per, tris, prims = {}, 0, 0
        for i in self.items.values():
            per[i["species"]] = per.get(i["species"], 0) + 1
            tris += lib.tris(i["species"], lod)
            prims += lib.prims(i["species"], lod)
        return {"items": len(self.items), "per_species": dict(sorted(per.items())), "triangles": int(tris), "draw_calls_unmerged": int(prims),
                "zones": {z: sum(1 for i in self.items.values() if i["zone"] == z) for z in sorted({i["zone"] for i in self.items.values()})},
                "hand_placed": sum(1 for i in self.items.values() if i["src"] == "hand")}


# ------------------------------------------------------------------ environment (rules read from here)
def _bilin(g, cell, x, y):
    ny, nx = g.shape
    fx = np.clip(np.asarray(x, float) / cell, 0, nx - 1)
    fy = np.clip(np.asarray(y, float) / cell, 0, ny - 1)
    j0, i0 = np.minimum(fx.astype(int), nx - 2), np.minimum(fy.astype(int), ny - 2)
    tx, ty = fx - j0, fy - i0
    return g[i0, j0] * (1 - tx) * (1 - ty) + g[i0, j0 + 1] * tx * (1 - ty) + g[i0 + 1, j0] * (1 - tx) * ty + g[i0 + 1, j0 + 1] * tx * ty


def _box_blur(g, r):
    if r < 1:
        return g
    p = np.pad(g, r, mode="edge")
    c = np.cumsum(np.cumsum(p, 0), 1)
    c = np.pad(c, ((1, 0), (1, 0)))
    k = 2 * r + 1
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


class Env:
    """Terrain + obstacles for the rules. All feet. heights[i,j] at x=j*cell, y=i*cell."""

    def __init__(self, width_ft, height_ft, heights=None, cell_ft=2.5, buildings=(), roads=(), water=(), water_lines=()):
        from shapely.geometry import LineString, Polygon
        from shapely.ops import unary_union
        self.width, self.height = float(width_ft), float(height_ft)
        if heights is None:
            nx, ny = int(self.width / cell_ft) + 2, int(self.height / cell_ft) + 2
            heights = np.zeros((ny, nx))
        self.h, self.cell = np.asarray(heights, float), float(cell_ft)
        gy, gx = np.gradient(self.h, self.cell)
        self.slope = np.degrees(np.arctan(np.hypot(gx, gy)))
        r = max(1, int(round(40.0 / self.cell)))
        self.hollow = np.clip((_box_blur(self.h, r) - self.h) / 5.0, 0, 1)
        self.buildings = unary_union([Polygon(p).buffer(0) for p in buildings]) if buildings else Polygon()
        self.roads = unary_union([LineString(p).buffer(w / 2.0, cap_style=2) for p, w in roads]) if roads else Polygon()
        self.water = unary_union([Polygon(p).buffer(0) for p in water]) if water else Polygon()
        self.has_water = not self.water.is_empty
        self._geoms = {}

    @classmethod
    def from_place(cls, place, root=None):
        import worldio
        base = root or os.path.join(REPO, "world", place)
        pl = _jload(os.path.join(base, "place.json"))
        h, meta = worldio.load_terrain(place) if root is None else (np.load(os.path.join(base, "terrain", "heightmap.npy")), _jload(os.path.join(base, "terrain", "terrain_meta.json")))
        b = pl["bounds"]
        blds, roads, water = [], [], []
        import glob
        for f in sorted(glob.glob(os.path.join(base, "buildings", "*.json"))):
            e = _jload(f)
            if e.get("geometry", {}).get("points"):
                blds.append([tuple(p) for p in e["geometry"]["points"]])
        for s in _jload(os.path.join(base, "streets.json"), {"streets": []})["streets"]:
            g = s["geometry"]
            if g.get("points") and len(g["points"]) > 1:
                roads.append(([tuple(p) for p in g["points"]], float(g.get("width_ft", 10))))
        wp_ = worldio.water_path(place) if root is None else os.path.join(base, "water.json")
        for w in _jload(wp_, {"water": []}).get("water", []):
            g = w.get("geometry", {})
            if g.get("type") == "polygon" and len(g.get("points", [])) > 2:
                water.append([tuple(p) for p in g["points"]])
        return cls(b["width_ft"], b["height_ft"], h, float(meta["cell_ft"]), blds, roads, water)

    def z(self, x, y):
        return _bilin(self.h, self.cell, x, y)

    def _dist(self, name, geom, x, y):
        import shapely
        if geom.is_empty:
            return np.full(np.shape(x), 1e9)
        return shapely.distance(geom, shapely.points(np.asarray(x, float), np.asarray(y, float)))

    def d_buildings(self, x, y):
        return self._dist("b", self.buildings, x, y)

    def d_roads(self, x, y):
        return self._dist("r", self.roads, x, y)

    def d_water_signed(self, x, y):
        """Distance to the water edge: negative inside the water body."""
        import shapely
        if self.water.is_empty:
            return np.full(np.shape(x), 1e9)
        d = self._dist("w", self.water, x, y)
        inside = shapely.contains_xy(self.water, np.asarray(x, float), np.asarray(y, float))
        return np.where(inside, -self._dist("wb", self.water.boundary, x, y), d)

    def moisture(self, x, y):
        dw = self.d_water_signed(x, y)
        m = np.exp(-np.maximum(dw, 0) / 60.0) if self.has_water else np.zeros(np.shape(x))
        return np.maximum(m, 0.8 * _bilin(self.hollow, self.cell, x, y))


# ------------------------------------------------------------------ scatter
DEFAULTS = {"zone": "z1", "mix": [{"species": "spruce", "weight": 1}], "density_per_ha": 200, "size_var": 0.5, "seed": 1, "pattern": "uniform",
            "cluster_radius_ft": 45, "cluster_size": 12, "edge_ft": 40, "row_spacing_ft": 0, "row_angle_deg": 0, "line_spacing_ft": 0, "line_jitter": 0.15,
            "avoid_buildings": True, "avoid_roads": True, "avoid_water": True, "clearance_building_ft": None, "clearance_road_ft": None,
            "slope_max_deg": 38, "elev_min_ft": None, "elev_max_ft": None, "moisture_bias": 0.0, "max_instances": 20000, "replace_zone": True}


class _Hash:
    def __init__(self, cell=24.0):
        self.c, self.g = cell, {}

    def near(self, x, y, r):
        cx, cy, k = int(x // self.c), int(y // self.c), int(r // self.c) + 1
        for i in range(cx - k, cx + k + 1):
            for j in range(cy - k, cy + k + 1):
                for q in self.g.get((i, j), ()):
                    yield q

    def free(self, x, y, rad):
        return all((x - qx) ** 2 + (y - qy) ** 2 >= (rad + qr) ** 2 for qx, qy, qr in self.near(x, y, rad + 20))

    def add(self, x, y, rad):
        self.g.setdefault((int(x // self.c), int(y // self.c)), []).append((x, y, rad))


def _norm_mix(lib, mix):
    out = []
    for m in mix:
        if isinstance(m, (list, tuple)):
            m = {"species": m[0], "weight": m[1]}
        w = float(m.get("weight", 1))
        if w > 0:
            lib.get(m["species"])
            out.append((m["species"], w))
    if not out:
        raise ValueError("empty species mix")
    return out


def _sp_clear(sp, p, kind):
    v = p.get("clearance_building_ft" if kind == "b" else "clearance_road_ft")
    if v is not None:
        return float(v)
    v = sp.get("clearance_building_ft" if kind == "b" else "clearance_road_ft")
    if v is not None:
        return float(v)
    crown = float(np.mean(sp["height_ft"])) * float(sp["crown_ratio"])
    if sp["kind"] in ("ground", "prop", "rock"):
        return 1.0 if kind == "r" else 2.0
    return max(3.0, crown * (0.55 if kind == "b" else 0.35))


def _pattern_points(pat, region, n, rng, p, parents, env):
    """n raw candidate (x, y) for the pattern inside `region` (shapely polygon)."""
    x0, y0, x1, y1 = region.bounds
    xs, ys = rng.uniform(x0, x1, n), rng.uniform(y0, y1, n)
    if pat == "cluster" and parents is not None and len(parents):
        k = rng.integers(0, len(parents), n)
        s = float(p["cluster_radius_ft"]) / 2.0
        xs, ys = parents[k, 0] + rng.normal(0, s, n), parents[k, 1] + rng.normal(0, s, n)
    return xs, ys


def scatter(env, lib, params, existing=(), polygon=None, path=None):
    """Rule-based scatter -> list of item dicts (no ids). Deterministic in params (seed). `existing`: items that must keep their spacing (hand-placed, other zones)."""
    import shapely
    from shapely.geometry import LineString, Polygon
    p = {**DEFAULTS, **{k: v for k, v in params.items() if v is not None}}
    polygon = polygon if polygon is not None else p.get("polygon")
    path = path if path is not None else p.get("path")
    mix = _norm_mix(lib, p["mix"])
    wsum = sum(w for _, w in mix)
    rng = np.random.default_rng(int(p["seed"]) & 0xFFFFFFFF)
    pat = p["pattern"]
    out, grid = [], _Hash()
    for q in existing:
        sp_ = lib.species.get(q["species"])
        grid.add(q["x"], q["y"], (sp_["spacing_ft"] / 2.0) if sp_ else 2.0)
    if pat in ("hedge_line", "tree_line", "line") or (polygon is None and path):
        if not path or len(path) < 2:
            raise ValueError("line pattern needs a path of at least two points")
        return _scatter_line(env, lib, p, mix, path, grid, rng)
    if not polygon or len(polygon) < 3:
        raise ValueError("scatter needs a polygon (>= 3 points) or a path")
    region = Polygon([tuple(q) for q in polygon]).buffer(0)
    if region.is_empty:
        raise ValueError("degenerate polygon")
    free = region
    if p["avoid_buildings"] and not env.buildings.is_empty:
        free = free.difference(env.buildings.buffer(4.0))
    if p["avoid_roads"] and not env.roads.is_empty:
        free = free.difference(env.roads.buffer(1.0))
    if p["avoid_water"] and not env.water.is_empty:
        free = free.difference(env.water)
    area_ha = max(free.area, 0.0) / HA_FT2
    n_total = min(int(round(p["density_per_ha"] * area_ha)), int(p["max_instances"]))
    shore_area = None
    parents = None
    if pat == "cluster":
        npar = max(1, int(round(n_total / max(float(p["cluster_size"]), 1))))
        x0, y0, x1, y1 = region.bounds
        px, py = rng.uniform(x0, x1, npar * 6), rng.uniform(y0, y1, npar * 6)
        ok = shapely.contains_xy(region, px, py)
        parents = np.stack([px[ok][:npar], py[ok][:npar]], 1)
    for sid, w in mix:
        sp = lib.get(sid)
        n_i = int(round(n_total * w / wsum))
        shore = bool(sp.get("shore"))
        if shore:                                               # shore species count over the shore band, not the whole polygon
            band = env.water.buffer(6.0).difference(env.water.buffer(-1.5)).intersection(region) if env.has_water else Polygon()
            n_i = int(round(p["density_per_ha"] * w / wsum * band.area / HA_FT2))
        if n_i <= 0:
            continue
        got, tries = 0, 0
        spacing = float(sp["spacing_ft"])
        cb, cr = _sp_clear(sp, p, "b"), _sp_clear(sp, p, "r")
        smax = min(float(p["slope_max_deg"]), float(sp.get("slope_max_deg", 90)))
        mo = sp.get("moisture") or {}
        emin = [v for v in (p["elev_min_ft"], (sp.get("elev_ft") or [None, None])[0]) if v is not None]
        emax = [v for v in (p["elev_max_ft"], (sp.get("elev_ft") or [None, None])[1]) if v is not None]
        if pat == "orchard":
            cand_iter = _orchard_points(region, float(p["row_spacing_ft"]) or spacing * 1.6, float(p["row_angle_deg"]), rng)
        else:
            cand_iter = None
        while got < n_i and tries < 14:
            tries += 1
            if cand_iter is not None:
                xs, ys = cand_iter
                tries = 99
            else:
                xs, ys = _pattern_points(pat, region, max(200, int(6 * (n_i - got))), rng, p, parents, env)
            m = shapely.contains_xy(region, xs, ys)
            if shore:
                m &= shapely.contains_xy(band, xs, ys)
            xs, ys = xs[m], ys[m]
            if not len(xs):
                continue
            ok = np.ones(len(xs), bool)
            if p["avoid_buildings"]:
                ok &= env.d_buildings(xs, ys) >= cb
            if p["avoid_roads"]:
                ok &= env.d_roads(xs, ys) >= cr
            if env.has_water and not shore and p["avoid_water"]:
                ok &= env.d_water_signed(xs, ys) >= 1.5
            if shore:
                dw = env.d_water_signed(xs, ys)
                ok &= (dw >= -2.0) & (dw <= 6.0)
            ok &= _bilin(env.slope, env.cell, xs, ys) <= smax
            zz = env.z(xs, ys)
            if emin:
                ok &= zz >= max(emin)
            if emax:
                ok &= zz <= min(emax)
            if mo and not shore:
                mm = np.clip(env.moisture(xs, ys) + float(p["moisture_bias"]), 0, 1)
                ok &= (mm >= float(mo.get("min", 0))) & (mm <= float(mo.get("max", 1)))
            if pat == "forest_edge":
                d = shapely.distance(region.boundary, shapely.points(xs, ys))
                ok &= rng.random(len(xs)) < (0.22 + 0.78 * np.exp(-d / max(float(p["edge_ft"]), 1.0)))
            xs, ys, zz = xs[ok], ys[ok], zz[ok]
            for x, y, z in zip(xs, ys, zz):
                if got >= n_i:
                    break
                if not grid.free(x, y, spacing / 2.0):
                    continue
                grid.add(x, y, spacing / 2.0)
                out.append(_make_item(sp, lib, p, rng, x, y, z, 0.0))
                got += 1
    return out


def _orchard_points(region, step, ang, rng):
    x0, y0, x1, y1 = region.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = math.hypot(x1 - x0, y1 - y0) / 2
    n = int(r / step) + 2
    g = np.arange(-n, n + 1) * step
    gx, gy = np.meshgrid(g, g)
    c, s = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    xs, ys = cx + gx.ravel() * c - gy.ravel() * s, cy + gx.ravel() * s + gy.ravel() * c
    j = step * 0.06
    return xs + rng.uniform(-j, j, len(xs)), ys + rng.uniform(-j, j, len(xs))


def _make_item(sp, lib, p, rng, x, y, z, rot_hint):
    lo, hi = sp["height_ft"]
    mid = (lo + hi) / 2.0
    hgt = mid + (rng.uniform(lo, hi) - mid) * float(p["size_var"]) * 2.0
    hgt = min(max(hgt, lo * 0.8), hi * 1.2)
    return {"species": sp["id"], "x": round(float(x), 2), "y": round(float(y), 2), "z": round(float(z), 2), "scale": round(hgt / mid, 3),
            "rot": round(float(rot_hint if rot_hint else rng.uniform(0, 360)), 1), "variant": int(rng.integers(0, max(1, int(sp.get("variants", 1)))))}


def _scatter_line(env, lib, p, mix, path, grid, rng):
    pts = np.asarray(path, float)
    seg = np.hypot(*(pts[1:] - pts[:-1]).T)
    cum = np.concatenate([[0], np.cumsum(seg)])
    total = float(cum[-1])
    names, ws = [m[0] for m in mix], np.array([m[1] for m in mix], float)
    out = []
    t = 0.0
    hedge = p["pattern"] == "hedge_line"
    while t <= total:
        sid = names[int(rng.choice(len(names), p=ws / ws.sum()))]
        sp = lib.get(sid)
        step = float(p["line_spacing_ft"]) or float(sp["spacing_ft"]) * (1.0 if hedge else 1.4)
        k = min(int(np.searchsorted(cum, t, side="right") - 1), len(seg) - 1)
        u = (t - cum[k]) / max(seg[k], 1e-9)
        pos = pts[k] + (pts[k + 1] - pts[k]) * u
        tan = (pts[k + 1] - pts[k]) / max(seg[k], 1e-9)
        j = float(p["line_jitter"]) * step
        off = rng.uniform(-j, j)
        x, y = pos[0] - tan[1] * off, pos[1] + tan[0] * off
        t += step * rng.uniform(0.9, 1.1)
        if p["avoid_buildings"] and env.d_buildings(np.array([x]), np.array([y]))[0] < _sp_clear(sp, p, "b") * 0.5:
            continue
        if p["avoid_water"] and env.has_water and env.d_water_signed(np.array([x]), np.array([y]))[0] < 1.0:
            continue
        if _bilin(env.slope, env.cell, x, y) > float(p["slope_max_deg"]):
            continue
        out.append(_make_item(sp, lib, p, rng, x, y, env.z(x, y), math.degrees(math.atan2(tan[1], tan[0])) if hedge else 0.0))
    return out


def run_scatter(doc, env, lib, params):
    """Apply a scatter request to `doc` (replace the zone's generated items, keep hand-placed + other zones' spacing). Returns a summary dict."""
    zone = slug(params.get("zone") or DEFAULTS["zone"])
    p = {**DEFAULTS, **params, "zone": zone}
    replaced = 0
    if p.get("replace_zone", True):
        replaced = doc.remove([i["id"] for i in doc.zone_items(zone, "generated") if not i.get("locked")])
    existing = list(doc.items.values())
    items = scatter(env, lib, p, existing=existing)
    new = doc.add_items(zone, items)
    doc.zones[zone] = {"id": zone, "name": params.get("name") or zone, "params": {k: v for k, v in p.items() if k not in ("polygon",)}, "polygon": p.get("polygon"),
                       "path": p.get("path"), "count": len(doc.zone_items(zone))}
    tris = sum(lib.tris(i["species"], 0) for i in new)
    return {"zone": zone, "added": len(new), "replaced": replaced, "triangles_added": int(tris), "total_items": len(doc.items),
            "per_species": {s: sum(1 for i in new if i["species"] == s) for s in sorted({i["species"] for i in new})}}


def add_single(doc, env, lib, species, x, y, scale=None, rot=None, zone="hand", variant=None):
    sp = lib.get(species)
    mid = float(np.mean(sp["height_ft"]))
    it = {"species": species, "x": round(float(x), 2), "y": round(float(y), 2), "z": round(float(env.z(x, y)) if env else 0.0, 2),
          "scale": round(float(scale) if scale else 1.0, 3), "rot": round(float(rot) if rot is not None else h01(species, x, y) * 360, 1),
          "variant": int(variant) if variant is not None else int(h01("v", x, y) * max(1, int(sp.get("variants", 1)))), "height_ft": round(mid * (float(scale) if scale else 1.0), 1)}
    it.pop("height_ft")
    return doc.add_items(slug(zone), [it], src="hand")[0]


def export_pack_scatter(doc, lib, place=None, root=None):
    """world/<place>/scatter/foliage.json: the list worldpack.py reads into the 'foliage' entities (same ids as foliage.json)."""
    place = place or doc.place
    out = []
    for i in sorted(doc.items.values(), key=lambda i: i["id"]):
        sp = lib.get(i["species"])
        out.append({"id": i["id"], "species": i["species"], "x": i["x"], "y": i["y"], "z": i.get("z"), "scale": i["scale"], "rotation": i["rot"],
                    "height_ft": round(float(np.mean(sp["height_ft"])) * i["scale"], 2), "kind": sp["kind"]})
    p = os.path.join(root or os.path.join(REPO, "world", place), "scatter", "foliage.json")
    _jdump(p, {"instances": out})
    return p, len(out)


# ------------------------------------------------------------------ 2D symbols
def symbol_d(style, x, y, r, rot, seed, k=1.0):
    """SVG path data (page units after `k` points per foot is applied by the caller via px) as a list of polylines in feet: [(pts, closed)]."""
    a0 = math.radians(rot)
    P = lambda dx, dy: (x + dx * math.cos(a0) - dy * math.sin(a0), y + dx * math.sin(a0) + dy * math.cos(a0))
    rng = np.random.default_rng(int(seed * 4294967296) & 0xFFFFFFFF)
    out = []
    if style == "conifer":
        n = 8
        out.append(([P(r * (1 if i % 2 == 0 else 0.5) * math.cos(math.pi * i / n * 2), r * (1 if i % 2 == 0 else 0.5) * math.sin(math.pi * i / n * 2)) for i in range(n * 2)][: n * 2], True))
        out.append(([P(0, 0), P(r * 0.12, 0)], False))
    elif style in ("broad", "shrub"):
        n = 10 if style == "broad" else 7
        pts = []
        for i in range(n):
            for t in range(4):
                a = 2 * math.pi * (i + t / 4) / n
                rr = r * (0.82 + 0.18 * math.sin(math.pi * t / 4 * 1.0 + 0.0) ** 0.6)
                pts.append(P(rr * math.cos(a), rr * math.sin(a)))
        out.append((pts, True))
        if style == "broad":
            out.append(([P(-r * 0.07, 0), P(r * 0.07, 0)], False))
    elif style == "hedge":
        L, W = r * 1.15, r * 0.42
        out.append(([P(-L, -W), P(L, -W), P(L, W), P(-L, W)], True))
    elif style in ("reed", "grass"):
        for i in range(3 if style == "grass" else 4):
            dx = (i - 1) * r * 0.5
            out.append(([P(dx, r * 0.4), P(dx + r * 0.2 * (1 if i % 2 else -1), -r * 0.6)], False))
    elif style == "fern":
        for i in range(5):
            a = math.pi * (0.1 + 0.8 * i / 4) + math.pi
            out.append(([P(0, 0), P(r * math.cos(a), r * math.sin(a))], False))
    elif style == "flower":
        out.append(([P(r * 0.7 * math.cos(2 * math.pi * i / 6), r * 0.7 * math.sin(2 * math.pi * i / 6)) for i in range(6)], True))
    elif style == "stump":
        out.append(([P(r * math.cos(2 * math.pi * i / 10), r * math.sin(2 * math.pi * i / 10)) for i in range(10)], True))
        out.append(([P(r * 0.45 * math.cos(2 * math.pi * i / 8), r * 0.45 * math.sin(2 * math.pi * i / 8)) for i in range(8)], True))
    elif style == "log":
        out.append(([P(-r * 0.9, -r * 0.18), P(r * 0.9, -r * 0.18), P(r * 0.9, r * 0.18), P(-r * 0.9, r * 0.18)], True))
    else:                                                              # rock
        n = 7
        out.append(([P(r * rng.uniform(0.7, 1.0) * math.cos(2 * math.pi * i / n), r * rng.uniform(0.7, 1.0) * math.sin(2 * math.pi * i / n)) for i in range(n)], True))
    return out


LAYER_FOLIAGE = "DETAILS - Foliage"


def draw_svg(doc, lib, out_svg, view, only_bounds=True):
    """2D symbols (one path per entity, id = entity id) on layer 'DETAILS - Foliage', in the page frame of `view` (render_world.View)."""
    from lib_svg import LayerTree
    css = [".fol { fill: none; stroke-width: 0.45; }"]
    for sid, sp in lib.species.items():
        css.append(f".fol-{sid} {{ stroke: {sp['symbol']['color']}; }}")
        if sp["symbol"]["style"] in ("stump", "rock", "log", "flower"):
            css.append(f".fol-{sid} {{ fill: none; }}")
    t = LayerTree([(LAYER_FOLIAGE, [])], view.page[0], view.page[1], css="\n".join(css))
    n = 0
    for i in sorted(doc.items.values(), key=lambda i: i["id"]):
        if not (view.x0 - 30 <= i["x"] <= view.x1 + 30 and view.y0 - 30 <= i["y"] <= view.y1 + 30):
            continue
        sp = lib.get(i["species"])
        r = max(lib.crown_r_ft(i["species"]) * i["scale"], 0.6 if sp["kind"] != "ground" else 0.9)
        if sp["symbol"]["style"] == "log":
            r = float(sp.get("length_ft", 9)) / 2 * i["scale"]
        d = []
        for pts, closed in symbol_d(sp["symbol"]["style"], i["x"], i["y"], r, i["rot"], h01(i["id"])):
            q = [view.px(p) for p in pts]
            d.append("M" + " L".join("%.2f,%.2f" % p for p in q) + (" Z" if closed else ""))
        t.add(LAYER_FOLIAGE, f'<path id="{i["id"]}" class="fol fol-{i["species"]}" fill="none" d="{" ".join(d)}"/>')
        n += 1
    t.write(out_svg)
    return n


def preview_png(doc, lib, env, out_png, scale_px_per_ft=None, max_px=1500, zone=None):
    from PIL import Image, ImageDraw
    W, H = env.width, env.height
    s = scale_px_per_ft or min(max_px / W, max_px / H)
    w, h = int(W * s) + 1, int(H * s) + 1
    ys, xs = np.mgrid[0:h, 0:w]
    X, Y = xs / s, ys / s
    z = env.z(X, Y)
    gy, gx = np.gradient(z, 1.0 / s)
    shade = np.clip(0.62 + 0.9 * (-(gx * 0.7) + (gy * 0.7)) / 2.0 * 0.5, 0.2, 1.0) if z.std() > 0 else np.full(z.shape, 0.7)
    img = np.dstack([np.full(z.shape, 196.0), np.full(z.shape, 204.0), np.full(z.shape, 164.0)]) * shade[:, :, None]
    im = Image.fromarray(np.clip(img, 0, 255).astype("uint8"), "RGB")
    dr = ImageDraw.Draw(im)
    def polys(g):
        if g.is_empty:
            return []
        return list(g.geoms) if hasattr(g, "geoms") else [g]
    for g in polys(env.water):
        dr.polygon([(a * s, b * s) for a, b in g.exterior.coords], fill=(120, 160, 205))
    for g in polys(env.roads):
        dr.polygon([(a * s, b * s) for a, b in g.exterior.coords], fill=(190, 170, 130))
    for g in polys(env.buildings):
        dr.polygon([(a * s, b * s) for a, b in g.exterior.coords], fill=(120, 108, 100), outline=(60, 50, 45))
    order = {"ground": 0, "rock": 0, "prop": 0, "shrub": 1, "hedge": 1, "tree": 2}
    for i in sorted(doc.items.values(), key=lambda i: (order.get(lib.get(i["species"])["kind"], 2), i["y"])):
        if zone and i["zone"] != zone:
            continue
        sp = lib.get(i["species"])
        r = max(lib.crown_r_ft(i["species"]) * i["scale"] * s, 1.2)
        c = sp["symbol"]["color"]
        col = tuple(int(c[k:k + 2], 16) for k in (1, 3, 5))
        x, y = i["x"] * s, i["y"] * s
        dr.ellipse([x - r, y - r, x + r, y + r], fill=col + (), outline=tuple(int(v * 0.6) for v in col))
    os.makedirs(os.path.dirname(os.path.abspath(out_png)), exist_ok=True)
    im.save(out_png)
    return out_png


# ------------------------------------------------------------------ merge for Foundry
def _next_version_dir(base, name):
    os.makedirs(base, exist_ok=True)
    n = 1
    while os.path.exists(os.path.join(base, f"{name}_v{n:03d}")):
        n += 1
    return os.path.join(base, f"{name}_v{n:03d}")


class Ground:
    """Frame + heights used to ground the instances in the pack (so trees sit on the mesh the pack exports)."""

    def __init__(self, frame, heights, cell_ft):
        self.frame, self.h, self.cell = frame, heights, cell_ft

    @classmethod
    def from_pack(cls, pack_dir):
        import worldpack as wp
        pack = wp.load_pack(pack_dir)
        h = pack.heights
        try:
            h = wp.road_conformed_heights(pack, wp.carved_heights(pack))
        except Exception:
            pass
        return cls(pack.frame, h, pack.cell_ft)

    def z(self, x, y):
        return _bilin(self.h, self.cell, x, y)


def plan(doc, lib, chunk_ft, budget=None, impostor_beyond_ft=None, lod1_beyond_ft=None, focus=None):
    """-> (chunks {(ix,iy): {"items":[...], "lod": n}}, dropped list). Thins to `budget` triangles (lowest priority + stable hash first; hand-placed last)."""
    items = sorted(doc.items.values(), key=lambda i: i["id"])
    if focus is None and items:
        focus = (np.mean([i["x"] for i in items]), np.mean([i["y"] for i in items]))
    chunks = {}
    for i in items:
        chunks.setdefault((int(i["x"] // chunk_ft), int(i["y"] // chunk_ft)), []).append(i)
    out = {}
    for k, its in chunks.items():
        cx, cy = (k[0] + 0.5) * chunk_ft, (k[1] + 0.5) * chunk_ft
        d = math.hypot(cx - focus[0], cy - focus[1]) if focus else 0.0
        lod = 2 if (impostor_beyond_ft and d > impostor_beyond_ft) else 1 if (lod1_beyond_ft and d > lod1_beyond_ft) else 0
        out[k] = {"items": its, "lod": lod}
    dropped = []
    tri = lambda i, lod: lib.tris(i["species"], lod)
    total = sum(tri(i, c["lod"]) for c in out.values() for i in c["items"])
    if budget and total > budget:
        def key(i):
            sp = lib.get(i["species"])
            return (1 if i["src"] == "hand" else 0, sp.get("priority") or 0, h01("thin", i["id"]))
        order = sorted(((key(i), k, i) for k, c in out.items() for i in c["items"]), key=lambda t: t[0])
        gone = set()
        for _, k, i in order:
            if total <= budget:
                break
            t = tri(i, out[k]["lod"])
            if t == 0:
                continue
            gone.add(i["id"])
            dropped.append(i["id"])
            total -= t
        for k in list(out):
            out[k]["items"] = [i for i in out[k]["items"] if i["id"] not in gone]
            if not out[k]["items"]:
                del out[k]
    return out, dropped


def _chunk_mesh(lib, its, ground, lod, sink_ft=0.25):
    fr = ground.frame
    parts = []
    for i in its:
        t = lib.mesh(i["species"], i.get("variant", 0), lod)
        z = ground.z(i["x"], i["y"]) - sink_ft
        bx, by, bz = fr.to_blender(i["x"], i["y"], z)
        parts.append((t, float(i["scale"]), float(i["rot"]), (bx, by, bz), 1.0))
    return fm.merge_instances(parts)


def baseline_stats(doc, lib, tmp_dir):
    """What the unmerged (one template GLB per species, one tile per tree) layout costs: files, tiles, triangles, primitives (= draw calls), GLB bytes."""
    import worldpack_mesh as wm
    per = {}
    for i in doc.items.values():
        per[i["species"]] = per.get(i["species"], 0) + 1
    by = 0
    os.makedirs(tmp_dir, exist_ok=True)
    for sid in per:
        m = lib.mesh(sid, 0, 0)
        mm = wm.Mesh(m.V, m.UV, {fm.ATLAS_MAT: np.concatenate(list(m.subs.values()))}, True)
        p = os.path.join(tmp_dir, sid + ".glb")
        wm.write_glb(p, [(sid, mm, {})], fm.atlas_material(), textures="external", tex_root=tmp_dir)
        by += os.path.getsize(p)
    n = len(doc.items)
    return {"files": len(per), "tiles": n, "triangles": int(sum(lib.tris(s, 0) * c for s, c in per.items())),
            "draw_calls": int(sum(lib.prims(s, 0) * c for s, c in per.items())), "glb_bytes": by, "atlas_bytes": 0}


def merge_foliage(doc, lib, ground, place, out_dir, chunk_ft=150.0, budget=None, impostor_beyond_ft=None, lod1_beyond_ft=None, focus=None, compress="none",
                  lods=(1, 2), px_per_ft=None, attach_placements=None, log=print, season=None):
    """Write merged foliage chunks into out_dir/models/foliage/ and return (placements doc, report). attach_placements: existing placements.json (dict) whose
    foliage-layer entries are replaced by the chunk entries."""
    import worldpack_mesh as wm
    import worldpack_split as ws
    fr = ground.frame
    os.makedirs(os.path.join(out_dir, "models", "textures"), exist_ok=True)
    fm.write_atlas(os.path.join(out_dir, "models", "textures", fm.ATLAS_MAT + ".png"), season=season or os.environ.get("VB_FOLIAGE_SEASON", "summer"))
    chunks, dropped = plan(doc, lib, chunk_ft, budget, impostor_beyond_ft, lod1_beyond_ft, focus)
    base = baseline_stats(doc, lib, os.path.join(out_dir, "_baseline_tmp"))
    shutil.rmtree(os.path.join(out_dir, "_baseline_tmp"), ignore_errors=True)
    mats = fm.atlas_material()
    entries, tris_after, written = [], 0, []
    for (ix, iy), c in sorted(chunks.items()):
        its = c["items"]
        name = f"c{ix}_{iy}" if ix >= 0 and iy >= 0 else f"c{ix}_{iy}".replace("-", "m")
        meshes = {lod: _chunk_mesh(lib, its, ground, lod) for lod in (0, 1, 2)}
        base_mesh = meshes[0]
        if not base_mesh.tri_count:
            continue
        pivot = wm._pivot(base_mesh)
        lo, hi = base_mesh.bbox()
        files, lodinfo = {}, []
        for lod in (0,) + tuple(lods):
            m = meshes[lod]
            if not m.tri_count:
                continue
            rel = f"foliage/{name}.glb" if lod == 0 else f"foliage/{name}.lod{lod}.glb"
            full = os.path.join(out_dir, "models", rel)
            wm.write_glb(full, [(name if lod == 0 else f"{name}_lod{lod}", m.translated([-pivot[0], -pivot[1], -pivot[2]]), {"foliage_chunk": [ix, iy], "lod": lod})], mats,
                         textures="external", tex_root=os.path.join(out_dir, "models", "textures"), tex_prefix="../textures/")
            fm.patch_glb_alpha_mask(full)
            files[lod] = (rel, full, m.tri_count)
            lodinfo.append({"lod": lod, "file": f"models/{rel}", "tris": int(m.tri_count), "suggested_distance_m": fm.LOD_SUGGESTED_M[lod]})
        prim = c["lod"] if c["lod"] in files else 0
        written += [f[1] for f in files.values()]
        rel, full, tcount = files[prim]
        pf = fr.from_blender(*pivot)
        size_m = [float(v) for v in (hi - lo)]
        size_ft = [round(v / fm.FT, 3) for v in size_m]
        px = lambda x, y: [round(v, 3) for v in fr.to_foundry_px(x, y)]
        entries.append({
            "id": f"model:{place}:foliage_{name}", "file": f"models/{rel}", "kind": "mesh", "layer": "foliage", "layers": ["foliage"], "group": f"foliage:{name}",
            "ids": [i["id"] for i in its], "lod": prim, "chunk": [ix, iy], "instances": len(its),
            "pivot": {"x_ft": round(pf[0], 3), "y_ft": round(pf[1], 3), "z_ft": round(pf[2], 3), "blender_m": [round(v, 4) for v in pivot], "foundry_px": px(pf[0], pf[1]),
                      "rel_z_ft": round(pivot[2] / fm.FT, 3)},
            "rotation_deg": 0.0, "scale": 1.0, "size_m": [round(v, 4) for v in size_m], "size_ft": size_ft,
            "tile": {"x": px(pf[0], pf[1])[0], "y": px(pf[0], pf[1])[1], "width": round(size_ft[0] * fr.px_per_ft, 2), "height": round(size_ft[1] * fr.px_per_ft, 2),
                     "depth": round(size_ft[2] * fr.px_per_ft, 2), "elevation_ft": round(pivot[2] / fm.FT, 3), "rotation": 0},
            "tris": int(tcount), "bytes": os.path.getsize(full), "sha256": ws._sha(full), "lods": lodinfo})
        tris_after += tcount
    if compress != "none":
        exe = shutil.which("gltfpack")
        if not exe:
            log("compress: gltfpack not installed; files stay uncompressed")
        else:
            import subprocess
            for p in written:
                subprocess.run([exe, "-i", p, "-o", p + ".tmp.glb"] + ws.GLTFPACK_FLAGS[compress], check=True, capture_output=True)
                os.replace(p + ".tmp.glb", p)
            for e in entries:
                e["bytes"], e["sha256"], e["compression"] = os.path.getsize(os.path.join(out_dir, e["file"])), ws._sha(os.path.join(out_dir, e["file"])), compress
    size_all = sum(os.path.getsize(p) for p in written)
    size_primary = sum(e["bytes"] for e in entries)
    after = {"files": len(entries), "tiles": len(entries), "instances": sum(e["instances"] for e in entries), "triangles": int(tris_after), "draw_calls": len(entries),
             "glb_bytes_primary": int(size_primary), "glb_bytes_with_lods": int(size_all), "atlas_bytes": os.path.getsize(os.path.join(out_dir, "models", "textures", fm.ATLAS_MAT + ".png")),
             "dropped_by_budget": len(dropped)}
    pk = (attach_placements or {})
    fdoc = {"format": ws.PLACEMENTS_FORMAT, "schema_version": "1.0", "place": place, "pack": pk.get("pack", {"dir": ".", "generated": None, "git_commit": None}),
            "frame": pk.get("frame") or {"px_per_ft": fr.px_per_ft, "z_origin_ft": fr.z_origin_ft, "height_ft": fr.height_ft, "width_ft": fr.width_ft, "tile_rotation_deg": 0,
                                        "note": "tile.x/y = pivot px at the pack's px_per_ft; push-models rescales to the target scene's calibration"},
            "split": pk.get("split", {"foliage": "chunk"}), "textures": "external", "merge": {"preset": "foliage", "chunk_ft": chunk_ft, "budget": budget, "compress": compress,
                                                                                         "impostor_beyond_ft": impostor_beyond_ft, "lod1_beyond_ft": lod1_beyond_ft},
            "files": sorted(entries, key=lambda e: e["file"])}
    if attach_placements is not None:
        keep = [e for e in pk.get("files", []) if e.get("layer") != "foliage" and "foliage" not in (e.get("layers") or [])]
        fdoc = {**pk, "files": sorted(keep + entries, key=lambda e: e["file"]), "merge": {**pk.get("merge", {}), "foliage": fdoc["merge"]}}
    _jdump(os.path.join(out_dir, "placements.json"), fdoc)
    rep = {"place": place, "before": base, "after": after, "chunk_ft": chunk_ft, "chunks": len(entries), "out": out_dir,
           "settings": {"budget": budget, "impostor_beyond_ft": impostor_beyond_ft, "lod1_beyond_ft": lod1_beyond_ft, "compress": compress}}
    _jdump(os.path.join(out_dir, "foliage_merge_report.json"), rep)
    log(f"foliage merge: {base['tiles']} tiles / {base['draw_calls']} draw calls / {base['triangles']} tris -> {after['files']} chunk files / {after['draw_calls']} draw calls / "
        f"{after['triangles']} tris ({len(dropped)} thinned), GLB {size_primary // 1024} KB (+LODs {size_all // 1024} KB) -> {out_dir}")
    return fdoc, rep


def attach_to_optimized(place, pack_dir, out_dir, chunk_ft=150.0, budget=None, impostor_beyond_ft=None, lod1_beyond_ft=None, compress="none", log=print):
    """worldpack_split merge/publish --foliage: replace the foliage-layer entries of out_dir/placements.json (one tile per tree) with merged chunk entries from
    world/<place>/foliage.json. Buildings, doors and every other entry are left exactly as they are."""
    doc = FoliageDoc(place)
    if not doc.items:
        log("foliage: no world/%s/foliage.json items; foliage-layer entries left as they are" % place)
        return None
    pk = _jload(os.path.join(out_dir, "placements.json"))
    fdoc, rep = merge_foliage(doc, _lib(), Ground.from_pack(pack_dir), place, out_dir, chunk_ft, budget, impostor_beyond_ft, lod1_beyond_ft, None, compress, attach_placements=pk, log=log)
    return rep


# ------------------------------------------------------------------ CLI
def _lib():
    return fm.FoliageLibrary()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["species", "presets-sync", "scatter", "add", "clear", "stats", "draw", "preview", "export", "merge", "publish", "atlas"])
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--params")
    ap.add_argument("--polygon")
    ap.add_argument("--species")
    ap.add_argument("--zone")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--x", type=float)
    ap.add_argument("--y", type=float)
    ap.add_argument("--scale", type=float)
    ap.add_argument("--rot", type=float)
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--page")
    ap.add_argument("--out")
    ap.add_argument("--out-dir")
    ap.add_argument("--pack")
    ap.add_argument("--chunk-ft", type=float, default=150.0)
    ap.add_argument("--budget", type=int)
    ap.add_argument("--impostor-beyond-ft", type=float)
    ap.add_argument("--lod1-beyond-ft", type=float)
    ap.add_argument("--compress", choices=["none", "quant", "meshopt", "meshopt-fallback"], default="none")
    ap.add_argument("--scene-uuid")
    ap.add_argument("--scene-name")
    ap.add_argument("--lod", type=int, default=0)
    ap.add_argument("--season", choices=["summer", "autumn", "winter"], default=None, help="leaf colour of the atlas (default summer; env VB_FOLIAGE_SEASON)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--terrain-source")
    ap.add_argument("--water-source")
    ap.add_argument("--grid")
    ap.add_argument("--grid-major")
    ap.add_argument("--grid-full-page", action="store_true")
    a = ap.parse_args(argv)
    if a.season:
        os.environ["VB_FOLIAGE_SEASON"] = a.season
    lib = _lib()
    if a.terrain_source or a.water_source:
        import worldio
        worldio.set_source(a.terrain_source, a.water_source)
    out = {}
    if a.cmd == "species":
        out = {"species": [{"id": s["id"], "name": s["name"], "kind": s["kind"], "height_ft": s["height_ft"], "density_per_ha": s["density_per_ha"], "spacing_ft": s["spacing_ft"],
                            "color": s["symbol"]["color"], "style": s["symbol"]["style"], "tris": [lib.tris(s["id"], l) for l in (0, 1, 2)], "moisture": s.get("moisture")}
                           for s in lib.species.values()], "mixes": lib.mixes}
    elif a.cmd == "presets-sync":                                  # store the triangle counts in the preset files (the panel reads them without python)
        out = {"updated": fm.sync_preset_tris()}
    elif a.cmd == "atlas":
        out = {"atlas": fm.write_atlas(a.out or os.path.join(REPO, "illustrator", "out", "foliage", "fol_atlas.png"), season=a.season or "summer")}
    else:
        doc = FoliageDoc(a.place, os.environ.get("VB_FOLIAGE_JSON") or None)          # VB_FOLIAGE_JSON: tests / scratch runs never touch world/
        export = (lambda *x: None) if os.environ.get("VB_FOLIAGE_JSON") else export_pack_scatter
        if a.cmd == "scatter":
            params = _jload(a.params)
            env = Env.from_place(a.place)
            out = run_scatter(doc, env, lib, params)
            doc.save()
            export(doc, lib)
            out["stats"] = doc.stats(lib)
        elif a.cmd == "add":
            env = Env.from_place(a.place)
            it = add_single(doc, env, lib, a.species, a.x, a.y, a.scale, a.rot, a.zone or "hand")
            doc.save()
            export(doc, lib)
            out = {"added": it, "total_items": len(doc.items)}
        elif a.cmd == "clear":
            poly = _jload(a.polygon) if a.polygon else None
            n = doc.clear(poly, a.zone, a.species.split(",") if a.species else None, include_hand=a.all)
            doc.save()
            export(doc, lib)
            out = {"removed": n, "total_items": len(doc.items)}
        elif a.cmd == "stats":
            out = doc.stats(lib)
            out["triangles_lod1"] = doc.stats(lib, 1)["triangles"]
        elif a.cmd == "export":
            p, n = export_pack_scatter(doc, lib)
            out = {"scatter": p, "instances": n}
        elif a.cmd == "preview":
            env = Env.from_place(a.place)
            png = preview_png(doc, lib, env, a.out or os.path.join(REPO, "illustrator", "out", "panel", a.place, "foliage_preview.png"), zone=a.zone)
            out = {"png": png, "items": len(doc.items)}
        elif a.cmd == "draw":
            import render_world as rw
            model = rw.load_place(a.place)
            over = {"preset": a.preset, "page": a.page}
            if a.scale:
                over["scale"] = a.scale
            if a.grid:
                over["grid"] = float(a.grid)
            v, cfg, *_ = rw.compute_view(model, a.view, over)
            od = a.out_dir or os.path.join(REPO, "illustrator", "out", "panel", a.place, "foliage")
            os.makedirs(od, exist_ok=True)
            n = draw_svg(doc, lib, os.path.join(od, "foliage.svg"), v)
            out = {"svg": "foliage.svg", "dir": od, "layer": LAYER_FOLIAGE, "symbols": n}
        elif a.cmd in ("merge", "publish"):
            pack = a.pack or os.path.join(REPO, "world", a.place, "export")
            ground = Ground.from_pack(pack)
            od = a.out_dir or _next_version_dir(os.path.join(pack, "optimized"), "foliage")
            fdoc, rep = merge_foliage(doc, lib, ground, a.place, od, a.chunk_ft, a.budget, a.impostor_beyond_ft, a.lod1_beyond_ft, None, a.compress)
            out = rep
            if a.cmd == "publish":
                import foundry_push
                args = ["push-models", "--place", a.place, "--placements", os.path.join(od, "placements.json"), "--lod", str(a.lod)]
                for flag, val in (("--scene-uuid", a.scene_uuid), ("--scene-name", a.scene_name)):
                    if val:
                        args += [flag, val]
                if a.dry_run:
                    args.append("--dry-run")
                if a.yes:
                    args.append("--yes")
                rc = foundry_push.main(args)
                out["push_rc"] = rc
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
