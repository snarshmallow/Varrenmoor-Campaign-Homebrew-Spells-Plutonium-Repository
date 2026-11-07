"""2D cast shadows and light glow for the map (sun and placed lights), georeferenced like shading.py / fills_raster.py.

  python lighting.py --place bridgehollow --view town --scale 40 --dpi 150 --config lighting.json --out-dir out/lighting [--vector]

CONVENTIONS (feet, y down, as everywhere in world/):
  Sun azimuth is the compass bearing OF the sun, clockwise from north: 0 = sun in the north, 90 = east, 180 = south, 270 = west.
  North is up the page (-y). A sun at azimuth 225 (south-west) casts shadows toward the north-east. Altitude is degrees above
  the horizon (0 = horizon, 90 = overhead); shadow length = height / tan(altitude).
  Point lights sit at (x, y) in feet on the map, `height` ft above the ground there; shadows fall away from the light.

HEIGHT FIELD: terrain (signed feet, worldio) + building extrusions (footprint polygons, height from building json height_ft or
presets/building_heights.json, optional gable roofs) + optional world/<place>/casters.json props. Shadows are found by marching
that single field, so buildings shade terrain, roofs and each other and hills shade the town.
  Sun: the field is resampled in a frame whose rows run along the light direction and swept once with a running "shadow ceiling"
       (exact, no per-pixel ray loop; terrain outside the view still casts into it).
  Point light: per-pixel ray march toward the light (<=250 steps) inside the light radius.
Soft shadows: penumbra widths grow with distance from the caster (light size). All maths is deterministic (no RNG except a fixed
dither seed).

LIGHTING MODEL: illumination I = ambient + (1 - ambient) * clamp(sum_k intensity_k * visibility_k * falloff_k * slope_k).
Shadow layer: RGBA, colour = shadow colour, alpha = shadow_opacity * (1 - I)  (multiply-style dark translucent, transparent where lit).
Glow layer: RGBA, colour = intensity-weighted mix of the light colours, alpha = glow_opacity * clamp(sum of light contribution)
(point lights; for the sun only when `tint` > 0 = lit-side tint). Both are clipped by shadows.
"""
import argparse
import json
import math
import os
import sys
import zlib

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ILL = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(ILL, ".."))
HEIGHTS_FILE = os.path.join(ILL, "presets", "building_heights.json")

DEFAULT_CFG = {
    "enabled": True,
    "ambient": 0.35,
    "height_scale": 1.0,
    "roof_pitch": True,            # gable roofs from presets/building_heights.json (false = flat tops)
    "terrain_smooth_ft": 12.0,     # gaussian sigma applied to the heightmap before shadowing (0 = raw)
    "terrain_shade": 0.5,          # 0..1: slopes turned away from the light darken even without a cast shadow
    "shadow": {"color": "#141a2e", "opacity": 0.55, "blur_ft": 0.4, "max_length_ft": 300.0, "terrain": True, "buildings": True},
    "glow": {"enabled": True, "opacity": 0.6},
    "vector": False,               # also emit building shadow polygons (LINES/Shadows) as an editable SVG
    "lights": [{"id": "sun", "type": "sun", "enabled": True, "azimuth": 225.0, "altitude": 30.0, "color": "#fff1d0",
                "intensity": 1.0, "softness": 0.3, "tint": 0.0}],
}
LIGHT_DEFAULTS = {"enabled": True, "color": "#fff1d0", "intensity": 1.0, "softness": 0.3}
SUN_SOFT_DEG = 6.0        # softness 1.0 = sun disc of this angular radius
POINT_SOFT_FT = 3.0       # softness 1.0 = point light of this radius (ft)
MAX_FIELD_PX = 22_000_000
MAX_RAY_WORK = 3.0e8      # pixels x steps per point light


def deep_merge(a, b):
    o = json.loads(json.dumps(a))
    for k, v in (b or {}).items():
        o[k] = deep_merge(o[k], v) if isinstance(v, dict) and isinstance(o.get(k), dict) else v
    return o


def load_config(src):
    """dict or path -> full config (defaults filled in; lights keep their own defaults)."""
    if isinstance(src, str):
        with open(src, encoding="utf-8") as f:
            src = json.load(f)
    cfg = deep_merge(DEFAULT_CFG, {k: v for k, v in (src or {}).items() if k != "lights"})
    lights = (src or {}).get("lights", DEFAULT_CFG["lights"])
    cfg["lights"] = [{**LIGHT_DEFAULTS, **l} for l in lights]
    return cfg


def hexrgb(s):
    s = str(s).lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], float)


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def sun_to_light(azimuth):
    """Unit world vector (x east, y south) pointing from the ground TOWARD a sun at this compass azimuth (clockwise from north)."""
    a = math.radians(azimuth)
    return np.array([math.sin(a), -math.cos(a)])


# ---------------------------------------------------------------- grids
class Grid:
    """Raster frame: pixel (row, col) centre = origin + (col+.5)/ppf*ex + (row+.5)/ppf*ey (world feet). ex, ey orthonormal."""

    def __init__(self, origin, ex, ey, nx, ny, ppf):
        self.o = np.asarray(origin, float)
        self.ex, self.ey = np.asarray(ex, float), np.asarray(ey, float)
        self.nx, self.ny, self.ppf = int(nx), int(ny), float(ppf)

    @classmethod
    def window(cls, x0, y0, x1, y1, ppf):
        return cls((x0, y0), (1, 0), (0, 1), max(1, int(round((x1 - x0) * ppf))), max(1, int(round((y1 - y0) * ppf))), ppf)

    def world(self):
        u = ((np.arange(self.nx) + 0.5) / self.ppf)[None, :]
        v = ((np.arange(self.ny) + 0.5) / self.ppf)[:, None]
        X = self.o[0] + u * self.ex[0] + v * self.ey[0]
        Y = self.o[1] + u * self.ex[1] + v * self.ey[1]
        return X.astype(np.float32), Y.astype(np.float32)

    def to_pix(self, x, y):
        """world -> continuous (col, row) pixel coordinates (pixel k spans [k, k+1))."""
        dx, dy = np.asarray(x, float) - self.o[0], np.asarray(y, float) - self.o[1]
        return (dx * self.ex[0] + dy * self.ex[1]) * self.ppf, (dx * self.ey[0] + dy * self.ey[1]) * self.ppf


# ---------------------------------------------------------------- scene
class Scene:
    """terrain heights (signed ft, node (i,j) at x=j*cell, y=i*cell) + casters (polygons with a height)."""

    def __init__(self, h, cell_ft, casters=(), pitch=True, smooth_ft=0.0):
        self.h = np.asarray(h, np.float32)
        self.cell = float(cell_ft)
        if smooth_ft > 0:          # tame stair-stepped cliffs in the 10 ft grid (they would cast a row of tooth-shaped shadows)
            self.h = ndi.gaussian_filter(self.h, float(smooth_ft) / self.cell, mode="nearest").astype(np.float32)
        self.casters = sorted(casters, key=lambda c: c["height"])
        self.pitch = pitch

    # terrain, sampled cubic on a coarse lattice then bilinearly filled in (the terrain is smooth; saves seconds on big grids)
    def terrain(self, g, stride=None):
        s = stride or max(1, int(round(2.0 * g.ppf)))
        nyc, nxc = (g.ny + s - 1) // s + 2, (g.nx + s - 1) // s + 2
        cols, rows = np.arange(nxc) * s, np.arange(nyc) * s
        u, v = cols[None, :] / g.ppf, rows[:, None] / g.ppf
        X = g.o[0] + u * g.ex[0] + v * g.ey[0]
        Y = g.o[1] + u * g.ex[1] + v * g.ey[1]
        L = ndi.map_coordinates(self.h, [Y / self.cell, X / self.cell], order=3, mode="nearest").astype(np.float32)
        if s == 1:
            return L[:g.ny, :g.nx]
        r = (np.arange(g.ny) + 0.5) / s - 0.5 + 0.5      # lattice node k sits at pixel coord k*s: centre of pixel i is (i+.5)
        r = (np.arange(g.ny) + 0.5) / s
        c = (np.arange(g.nx) + 0.5) / s
        r0, c0 = np.floor(r).astype(int), np.floor(c).astype(int)
        wr, wc = (r - r0).astype(np.float32), (c - c0).astype(np.float32)
        A = L[r0] * (1 - wr)[:, None] + L[r0 + 1] * wr[:, None]
        return A[:, c0] * (1 - wc)[None, :] + A[:, c0 + 1] * wc[None, :]

    def height_field(self, g, T=None):
        """-> (T terrain, H terrain + casters) on grid g, float32."""
        if T is None:
            T = self.terrain(g)
        H = T.copy()
        ss = 3
        for c in self.casters:
            pts = np.asarray(c["poly"], float)
            col, row = g.to_pix(pts[:, 0], pts[:, 1])
            c0, c1 = int(max(0, math.floor(col.min()) - 1)), int(min(g.nx, math.ceil(col.max()) + 1))
            r0, r1 = int(max(0, math.floor(row.min()) - 1)), int(min(g.ny, math.ceil(row.max()) + 1))
            if c1 <= c0 or r1 <= r0:
                continue
            from PIL import Image, ImageDraw
            w, hh = c1 - c0, r1 - r0
            im = Image.new("L", (w * ss, hh * ss), 0)
            ImageDraw.Draw(im).polygon([((x - c0) * ss, (y - r0) * ss) for x, y in zip(col, row)], fill=255)
            cov = np.asarray(im, np.float32).reshape(hh, ss, w, ss).mean((1, 3)) / 255.0
            if not cov.any():
                continue
            Tc = T[r0:r1, c0:c1]
            m = cov > 0.5
            base = float(Tc[m].mean() if m.any() else Tc.mean())
            top = base + self._profile(c, g, c0, c1, r0, r1)
            Hc = H[r0:r1, c0:c1]
            H[r0:r1, c0:c1] = np.maximum(Hc, Tc + cov * np.maximum(top - Tc, 0.0))
        return T, H

    def _profile(self, c, g, c0, c1, r0, r1):
        height = float(c["height"])
        pitch = float(c.get("pitch", 0.0)) if self.pitch else 0.0
        if pitch <= 0:
            return np.full((r1 - r0, c1 - c0), height, np.float32)
        from shapely.geometry import Polygon
        rect = Polygon(c["poly"]).minimum_rotated_rectangle
        q = np.asarray(rect.exterior.coords)[:4]
        e1, e2 = q[1] - q[0], q[2] - q[1]
        long_e, short_len = (e1, np.hypot(*e2)) if np.hypot(*e1) >= np.hypot(*e2) else (e2, np.hypot(*e1))
        d = long_e / (np.hypot(*long_e) or 1.0)
        n = np.array([-d[1], d[0]])
        hw = max(short_len / 2.0, 1e-3)
        rise = min(hw * math.tan(math.radians(pitch)), 0.45 * height)
        cx, cy = q.mean(0)[0], q.mean(0)[1]
        u = ((np.arange(c0, c1) + 0.5) / g.ppf)[None, :]
        v = ((np.arange(r0, r1) + 0.5) / g.ppf)[:, None]
        X = g.o[0] + u * g.ex[0] + v * g.ey[0]
        Y = g.o[1] + u * g.ex[1] + v * g.ey[1]
        s = np.abs((X - cx) * n[0] + (Y - cy) * n[1])
        return (height - rise + rise * (1.0 - np.clip(s / hw, 0, 1))).astype(np.float32)


def load_heights_table():
    with open(HEIGHTS_FILE, encoding="utf-8") as f:
        return json.load(f)


def pick(rng_range, key):
    lo, hi = float(rng_range[0]), float(rng_range[1])
    return lo + (hi - lo) * ((zlib.crc32(key.encode()) % 10007) / 10006.0)


def casters_from_model(model, height_scale=1.0, place_dir=None):
    """Footprint polygons with heights: buildings (height_ft or preset by id/kind) + optional casters.json props."""
    tab = load_heights_table()
    out = []
    for b in model.get("buildings", []):
        g = b.get("geometry", {})
        if g.get("type") != "polygon":
            continue
        bid, kind = b.get("id", ""), b.get("kind", "")
        spec = None
        for k, v in tab.get("by_id_contains", {}).items():
            if k in bid:
                spec = v
                break
        spec = spec or tab.get("by_kind", {}).get(kind) or tab["default"]
        hgt = float(b["height_ft"]) if b.get("height_ft") else pick(spec["height_ft"], bid)
        out.append({"id": bid, "poly": [tuple(p) for p in g["points"]], "height": hgt * height_scale,
                    "pitch": float(b.get("roof_pitch_deg", spec.get("roof_pitch_deg", 0.0))), "kind": kind})
    if place_dir:
        p = os.path.join(place_dir, "casters.json")
        if os.path.exists(p):
            out += props_from_file(p, tab, height_scale)
    return out


def props_from_file(path, tab, height_scale=1.0):
    """casters.json: {"casters":[{"type":"line","kind":"wall","points":[[x,y],..],"width_ft":1.5,"height_ft":7},
    {"type":"polygon","points":[..],"height_ft":..}, {"type":"circle","kind":"tree","x":..,"y":..,"radius_ft":6,"height_ft":30}]}"""
    from shapely.geometry import LineString, Point, Polygon
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    out = []
    for i, c in enumerate(d.get("casters", [])):
        kind = c.get("kind", c.get("type"))
        rng = tab.get("props", {}).get(kind, {}).get("height_ft", [8, 8])
        hgt = float(c["height_ft"]) if c.get("height_ft") else pick(rng, f"{kind}{i}")
        if c["type"] == "line":
            geom = LineString(c["points"]).buffer(float(c.get("width_ft", 1.5)) / 2.0, cap_style=2)
        elif c["type"] == "circle":
            geom = Point(c["x"], c["y"]).buffer(float(c.get("radius_ft", 4.0)), 8)
        else:
            geom = Polygon(c["points"])
        if geom.is_empty:
            continue
        out.append({"id": f"caster_{i}", "poly": list(geom.exterior.coords)[:-1], "height": hgt * height_scale, "pitch": 0.0, "kind": kind})
    return out


# ---------------------------------------------------------------- slope term
def slope_factor(T, ppf, to_light3, flat_dot):
    """Terrain Lambert term normalised to flat ground: 1 = as lit as flat, 0 = turned away. to_light3: (lx, ly, lz) per pixel or constants."""
    gy, gx = np.gradient(T, 1.0 / ppf)
    inv = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
    ndl = (-gx * to_light3[0] - gy * to_light3[1] + to_light3[2]) * inv
    return np.clip(ndl / np.maximum(flat_dot, 0.05), 0.0, 1.0).astype(np.float32)


# ---------------------------------------------------------------- sun
def sun_visibility(scene, win, light, max_len_ft=300.0, use_terrain=True, use_buildings=True, T_win=None):
    """-> vis (win.ny, win.nx) float32 in 0..1 (1 = lit by the sun, 0 = in cast shadow)."""
    alt = max(float(light["altitude"]), 0.5)
    if alt >= 89.5:
        return np.ones((win.ny, win.nx), np.float32)
    tl = sun_to_light(light["azimuth"])
    ey = -tl                                    # rows run away from the sun
    ex = np.array([-ey[1], ey[0]])
    x0, y0 = win.o
    corners = np.array([[x0, y0], [x0 + win.nx / win.ppf, y0], [x0, y0 + win.ny / win.ppf], [x0 + win.nx / win.ppf, y0 + win.ny / win.ppf]])
    # window corners in world axes (window is axis aligned when built with Grid.window)
    a, b = corners @ ey, corners @ ex
    margin = min(float(max_len_ft), 600.0)
    ppf = win.ppf
    for _ in range(3):
        a_min, a_max, b_min, b_max = a.min() - margin, a.max(), b.min(), b.max()
        ny, nx = int(math.ceil((a_max - a_min) * ppf)) + 2, int(math.ceil((b_max - b_min) * ppf)) + 2
        if nx * ny <= MAX_FIELD_PX:
            break
        ppf *= 0.75
    g = Grid(a_min * ey + b_min * ex, ex, ey, nx, ny, ppf)
    T = scene.terrain(g)
    if not use_terrain:
        T = np.full_like(T, float(T.mean()))
    if use_buildings:
        _, H = scene.height_field(g, T)
    else:
        H = T
    tan_alt = math.tan(math.radians(alt))
    step = 1.0 / ppf
    drop = step * tan_alt
    spread = (math.tan(math.radians(min(alt + SUN_SOFT_DEG * float(light.get("softness", 0.3)), 89.0)))
              - math.tan(math.radians(max(alt - SUN_SOFT_DEG * float(light.get("softness", 0.3)), 0.2)))) / 2.0
    eps = 0.6 * drop
    max_len = float(max_len_ft)
    vis = np.empty((ny, nx), np.float32)
    c = np.full(nx, -np.inf, np.float32)
    age = np.zeros(nx, np.float32)
    for i in range(ny):
        row = H[i]
        cd = c - drop
        ad = age + step
        cd[ad > max_len] = -np.inf
        pen = ad * spread
        s = np.clip((cd - row + pen) / (2.0 * (pen + eps)), 0.0, 1.0)
        s *= np.clip((max_len - ad) / (0.25 * max_len), 0.0, 1.0)
        vis[i] = 1.0 - s * s * (3 - 2 * s)
        newer = row >= cd
        c = np.where(newer, row, cd)
        age = np.where(newer, 0.0, ad)
    X, Y = win.world()
    dx, dy = X - g.o[0], Y - g.o[1]
    col = (dx * ex[0] + dy * ex[1]) * ppf - 0.5
    rw = (dx * ey[0] + dy * ey[1]) * ppf - 0.5
    return ndi.map_coordinates(vis, [rw, col], order=1, mode="nearest").astype(np.float32)


def sun_fields(scene, win, light, cfg, T_win):
    sh = cfg["shadow"]
    vis = sun_visibility(scene, win, light, sh["max_length_ft"], sh.get("terrain", True), sh.get("buildings", True))
    alt = math.radians(max(float(light["altitude"]), 0.5))
    tl = sun_to_light(light["azimuth"])
    slope = slope_factor(T_win, win.ppf, (tl[0] * math.cos(alt), tl[1] * math.cos(alt), math.sin(alt)), math.sin(alt))
    ts = float(cfg.get("terrain_shade", 0.5))
    return vis, np.float32(1.0) * (1.0 - ts + ts * slope)


# ---------------------------------------------------------------- point lights
def point_fields(scene, win, light, cfg, T_win=None):
    """-> (vis, falloff*slope) on the window grid (zeros outside the light radius)."""
    R = float(light["radius"])
    lx, ly = float(light["x"]), float(light["y"])
    pc = win.ppf
    n = 2 * R * pc
    if n * n > MAX_FIELD_PX:
        pc *= math.sqrt(MAX_FIELD_PX) / n
    K = int(min(250, max(24, R * pc)))
    # keep (pixels in disc) x steps bounded
    while math.pi * (R * pc) ** 2 * K > MAX_RAY_WORK and pc > 0.2:
        pc *= 0.85
        K = int(min(250, max(24, R * pc)))
    g = Grid((lx - R, ly - R), (1, 0), (0, 1), int(math.ceil(2 * R * pc)) + 1, int(math.ceil(2 * R * pc)) + 1, pc)
    T = scene.terrain(g)
    sh = cfg["shadow"]
    if not sh.get("terrain", True):
        T = np.full_like(T, float(T.mean()))
    if sh.get("buildings", True):
        _, H = scene.height_field(g, T)
    else:
        H = T
    X, Y = g.world()
    x0, y0 = win.o
    x1, y1 = x0 + win.nx / win.ppf, y0 + win.ny / win.ppf
    r2 = (X - lx) ** 2 + (Y - ly) ** 2
    mask = (r2 < R * R) & (X >= x0) & (X <= x1) & (Y >= y0) & (Y <= y1)
    out_vis = np.zeros((g.ny, g.nx), np.float32)
    out_fall = np.zeros((g.ny, g.nx), np.float32)
    idx = np.flatnonzero(mask)
    if idx.size:
        t0 = float(ndi.map_coordinates(scene.h, [[ly / scene.cell], [lx / scene.cell]], order=3, mode="nearest")[0])
        zl = t0 + float(light.get("height", 6.0))
        rl = POINT_SOFT_FT * float(light.get("softness", 0.3))
        Hf = H.ravel()
        flatH = H
        for s0 in range(0, idx.size, 200_000):
            ii = idx[s0:s0 + 200_000]
            px, py = X.ravel()[ii].astype(np.float64), Y.ravel()[ii].astype(np.float64)
            z0 = Hf[ii].astype(np.float64)
            dz = zl - z0
            D = np.hypot(lx - px, ly - py) + 1e-6
            eps = 0.5 / pc * (1.0 + np.abs(dz) / D)
            vis = np.ones(ii.size)
            for k in range(1, K):
                t = k / K
                sx, sy = px + (lx - px) * t, py + (ly - py) * t
                cc = np.clip(((sx - g.o[0]) * pc).astype(np.int64), 0, g.nx - 1)
                rr = np.clip(((sy - g.o[1]) * pc).astype(np.int64), 0, g.ny - 1)
                cl = (z0 + dz * t) - Hf[rr * g.nx + cc]
                pen = rl * t
                s = np.clip((-cl + pen) / (2.0 * (pen + eps)), 0.0, 1.0)
                vis = np.minimum(vis, 1.0 - s * s * (3 - 2 * s))
            out_vis.ravel()[ii] = vis
            rr_ = np.sqrt(r2.ravel()[ii]) / R
            out_fall.ravel()[ii] = np.clip(1.0 - rr_ * rr_, 0, 1) ** 2
        # slope (terrain Lambert, normalised to flat) toward the light
        L3 = np.sqrt((lx - X) ** 2 + (ly - Y) ** 2 + (zl - T) ** 2) + 1e-6
        flat_dot = np.clip((zl - T) / L3, 0.05, 1.0)
        gy, gx = np.gradient(T, 1.0 / pc)
        inv = 1.0 / np.sqrt(1.0 + gx * gx + gy * gy)
        ndl = (-gx * (lx - X) / L3 - gy * (ly - Y) / L3 + (zl - T) / L3) * inv
        slope = np.clip(ndl / flat_dot, 0, 1)
        ts = float(cfg.get("terrain_shade", 0.5))
        out_fall = out_fall * (1.0 - ts + ts * slope)
    # onto the window grid
    Xw, Yw = win.world()
    col, row = g.to_pix(Xw, Yw)
    inside = (col >= 0) & (col <= g.nx) & (row >= 0) & (row <= g.ny)
    vis_w = ndi.map_coordinates(out_vis, [row - 0.5, col - 0.5], order=1, mode="constant", cval=0.0)
    fall_w = ndi.map_coordinates(out_fall, [row - 0.5, col - 0.5], order=1, mode="constant", cval=0.0)
    vis_w = np.where(inside, vis_w, 0.0).astype(np.float32)
    fall_w = np.where(inside, fall_w, 0.0).astype(np.float32)
    return vis_w, fall_w


# ---------------------------------------------------------------- compose
def render_fields(scene, win, cfg, log=print):
    """-> dict(illum, glow_w, glow_rgb, T) arrays on the window grid."""
    ny, nx = win.ny, win.nx
    T_win = scene.terrain(win)
    total = np.zeros((ny, nx), np.float32)
    gnum = np.zeros((ny, nx, 3), np.float32)
    gsum = np.zeros((ny, nx), np.float32)
    for L in cfg["lights"]:
        if not L.get("enabled", True):
            continue
        col = hexrgb(L.get("color", "#ffffff")) / 255.0
        inten = float(L.get("intensity", 1.0))
        if L["type"] == "sun":
            vis, slope = sun_fields(scene, win, L, cfg, T_win)
            contrib = inten * vis * slope
            tint = float(L.get("tint", 0.0))
            if tint > 0:
                g = tint * inten * vis
                gnum += g[..., None] * col
                gsum += g
            log(f"  sun az {L['azimuth']:g} alt {L['altitude']:g}: lit {float((vis > 0.5).mean()) * 100:.0f}%")
        else:
            vis, fall = point_fields(scene, win, L, cfg)
            contrib = inten * vis * fall
            gl = contrib
            gnum += gl[..., None] * col
            gsum += gl
            log(f"  point ({L['x']:g},{L['y']:g}) h {L.get('height', 6):g} r {L['radius']:g}: shadowed {float(((fall > 0.05) & (vis < 0.5)).sum()) / max(1, (fall > 0.05).sum()) * 100:.0f}% of its disc")
        total += contrib.astype(np.float32)
    amb = float(cfg.get("ambient", 0.35))
    illum = amb + (1.0 - amb) * np.clip(total, 0.0, 1.0)
    return {"illum": illum, "gsum": gsum, "gnum": gnum, "T": T_win}


def to_images(fields, cfg, seed=0):
    from PIL import Image
    sh, gl = cfg["shadow"], cfg["glow"]
    illum = fields["illum"]
    dark = np.clip(1.0 - illum, 0, 1) * float(sh["opacity"])
    blur = float(sh.get("blur_ft", 0.0)) * fields["ppf"]
    if blur > 0.3:
        dark = ndi.gaussian_filter(dark, blur)
    rng = np.random.default_rng(seed)
    ny, nx = dark.shape
    a = np.clip(dark * 255.0 + rng.random((ny, nx), dtype=np.float32) - 0.5, 0, 255).astype(np.uint8)
    rgb = np.empty((ny, nx, 4), np.uint8)
    rgb[..., :3] = np.clip(hexrgb(sh["color"]), 0, 255).astype(np.uint8)
    rgb[..., 3] = a
    shadows = Image.fromarray(rgb, "RGBA")
    glow = None
    if gl.get("enabled", True) and float(fields["gsum"].max()) > 1e-4:
        gs = fields["gsum"]
        col = fields["gnum"] / np.maximum(gs, 1e-6)[..., None]
        ga = np.clip(gs, 0, 1) * float(gl["opacity"])
        ga = smooth(ga / max(float(gl["opacity"]), 1e-6)) * float(gl["opacity"])
        ga8 = np.clip(ga * 255.0 + rng.random((ny, nx), dtype=np.float32) - 0.5, 0, 255).astype(np.uint8)
        im = np.empty((ny, nx, 4), np.uint8)
        im[..., :3] = np.clip(col * 255.0, 0, 255).astype(np.uint8)
        im[..., 3] = ga8
        glow = Image.fromarray(im, "RGBA")
    return shadows, glow


# ---------------------------------------------------------------- vector building shadows
def shadow_polygons(casters, cfg, win_box):
    """Union of ground shadow polygons of the building footprints (flat ground assumed), clipped to the window: shapely geometry."""
    from shapely.geometry import MultiPolygon, Polygon, box
    from shapely.ops import unary_union
    maxlen = float(cfg["shadow"]["max_length_ft"])
    parts = []
    for L in cfg["lights"]:
        if not L.get("enabled", True):
            continue
        for c in casters:
            pts = np.asarray(c["poly"], float)
            if L["type"] == "sun":
                alt = math.radians(max(float(L["altitude"]), 0.5))
                v = -sun_to_light(L["azimuth"]) * min(c["height"] / math.tan(alt), maxlen)
                disp = np.tile(v, (len(pts), 1))
            else:
                lx, ly, lz = float(L["x"]), float(L["y"]), float(L.get("height", 6.0))
                d = pts - np.array([lx, ly])
                dist = np.hypot(d[:, 0], d[:, 1]) + 1e-9
                h = c["height"]
                k = np.where(h < lz, h / np.maximum(lz - h, 1e-3), 1e9)
                ln = np.minimum(dist * k, np.minimum(maxlen, np.maximum(float(L["radius"]) - dist, 0)))
                disp = d / dist[:, None] * ln[:, None]
            try:
                poly = Polygon(pts).buffer(0)
                swept = [poly, Polygon(pts + disp).buffer(0)]
                n = len(pts)
                for i in range(n):
                    j = (i + 1) % n
                    swept.append(Polygon([pts[i], pts[j], pts[j] + disp[j], pts[i] + disp[i]]).buffer(0))
                shadow = unary_union(swept).difference(poly)
                if not shadow.is_empty:
                    parts.append(shadow)
            except Exception:
                continue
    if not parts:
        return Polygon()
    u = unary_union(parts).intersection(box(*win_box)).simplify(0.4)
    return u


def write_vector_svg(geom, view, path, cfg, w_in, h_in):
    from lib_svg import LayerTree
    t = LayerTree([("LINES", ["Shadows"])], w_in, h_in)
    polys = list(geom.geoms) if hasattr(geom, "geoms") else ([geom] if not geom.is_empty else [])
    col = "#%02x%02x%02x" % tuple(int(v) for v in hexrgb(cfg["shadow"]["color"]))
    n = 0
    for p in polys:
        if p.is_empty or p.geom_type != "Polygon" or p.area < 2.0:
            continue
        rings = [p.exterior] + list(p.interiors)
        d = " ".join("M" + " L".join("%.2f,%.2f" % view.px(q) for q in r.coords[:-1]) + " Z" for r in rings)
        n += 1
        t.add("Shadows", f'<path id="shadow_{n}" fill="{col}" fill-opacity="{float(cfg["shadow"]["opacity"]) * (1.0 - float(cfg.get("ambient", 0.35))):.2f}" fill-rule="evenodd" stroke="none" d="{d}"/>')
    t.write(path)
    return n


# ---------------------------------------------------------------- driver
def render_window(scene, bounds, cfg, dpi, scale_ft_per_in, out_dir, casters=None, view=None, page=None, log=print):
    """bounds = (x0, y0, x1, y1) ft. Writes shadows.png, light_glow.png (if any), lighting.json (+ lighting_vector.svg)."""
    from PIL import Image
    x0, y0, x1, y1 = bounds
    ppf = float(dpi) / float(scale_ft_per_in)
    win = Grid.window(x0, y0, x1, y1, ppf)
    if win.nx * win.ny > 80_000_000:
        raise SystemExit(f"{win.nx}x{win.ny} px is too large; lower the dpi")
    os.makedirs(out_dir, exist_ok=True)
    fields = render_fields(scene, win, cfg, log)
    fields["ppf"] = ppf
    shadows, glow = to_images(fields, cfg)
    layers = []
    sp = os.path.join(out_dir, "shadows.png")
    shadows.save(sp, dpi=(dpi, dpi))
    layers.append({"png": "shadows.png", "layer": "ART - Shadows", "name": "shadows_png"})
    gp = os.path.join(out_dir, "light_glow.png")
    if glow is not None:
        glow.save(gp, dpi=(dpi, dpi))
        layers.append({"png": "light_glow.png", "layer": "ART - Light Glow", "name": "light_glow_png"})
    elif os.path.exists(gp):
        os.remove(gp)
    info = {"dpi": dpi, "ppf": ppf, "scale_ft_per_in": scale_ft_per_in, "size_px": [win.nx, win.ny],
            "bounds_ft": {"x_min": x0, "y_min": y0, "x_max": x1, "y_max": y1}, "y_axis": "down", "layers": layers,
            "vector": None, "stats": {"mean_darkness": float((1 - fields["illum"]).mean())}}
    if cfg.get("vector") and view is not None:
        geom = shadow_polygons(casters or [], cfg, bounds)
        vp = os.path.join(out_dir, "lighting_vector.svg")
        n = write_vector_svg(geom, view, vp, cfg, page[0], page[1])
        info["vector"] = {"svg": "lighting_vector.svg", "layer": "Shadows", "polygons": n}
        log(f"  vector shadows: {n} polygons")
    with open(os.path.join(out_dir, "lighting.json"), "w") as f:
        json.dump(info, f, indent=1)
    log(f"wrote {sp} {win.nx}x{win.ny} px ({ppf:g} px/ft)")
    return info, fields


def main(argv=None):
    sys.path.insert(0, HERE)
    import render_world as rw
    import worldio
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--view", default="town")
    ap.add_argument("--preset")
    ap.add_argument("--scale", type=float)
    ap.add_argument("--grid", type=float)
    ap.add_argument("--grid-major", type=int)
    ap.add_argument("--page")
    ap.add_argument("--model-dir")
    ap.add_argument("--water-source", choices=["world", "working"])
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"])
    ap.add_argument("--config", help="lighting JSON (see DEFAULT_CFG); default: the sun only")
    ap.add_argument("--dpi", type=float, default=150.0)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--vector", action="store_true", help="also write building shadow polygons as lighting_vector.svg (LINES/Shadows)")
    a = ap.parse_args(argv)
    worldio.set_source(a.terrain_source, a.water_source)
    cfg = load_config(a.config) if a.config else load_config({})
    if a.vector:
        cfg["vector"] = True
    model = rw.load_place(a.place, a.model_dir)
    v, vcfg, title, kind, ident = rw.compute_view(model, a.view, {"preset": a.preset, "scale": a.scale, "grid": a.grid, "page": a.page,
                                                                  "major_every": a.grid_major})
    h, meta = worldio.load_terrain(a.place)
    casters = casters_from_model(model, float(cfg["height_scale"]), os.path.join(REPO, "world", a.place)) if cfg["shadow"].get("buildings", True) else []
    scene = Scene(h, meta["cell_ft"], casters, bool(cfg.get("roof_pitch", True)), float(cfg.get("terrain_smooth_ft", 12.0)))
    print(f"lighting: terrain {meta['source']}, {len(casters)} casters, window {v.x0:.0f},{v.y0:.0f} - {v.x1:.0f},{v.y1:.0f} ft at 1 in = {v.fpi:g} ft")
    if not cfg.get("enabled", True):
        cfg["lights"] = []
    render_window(scene, (v.x0, v.y0, v.x1, v.y1), cfg, a.dpi, v.fpi, a.out_dir, casters, v, vcfg["page_in"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
