"""Padding heightmap + apron mesh + ground textures for Foundry 3D Canvas scenes (the distant surroundings of a place), and the push to a scene.

  python illustrator/generators/padding_heightmap.py presets
  python illustrator/generators/padding_heightmap.py generate --place bridgehollow__dyers_walk_local --preset bowl-ridge [--texture summer] [--blend 300] [--seed 7] [--out DIR]
  python illustrator/generators/padding_heightmap.py push --place ... --scene-uuid Scene.xxx --preset bowl-ridge [--dry-run]     (also: foundry_push.py push-padding ...)
  python illustrator/generators/padding_heightmap.py save-preset --from bowl-ridge --name my-hills --set ridge_amp_ft=200

How 3D Canvas builds the "table" (measured live on Foundry 14.360 / levels-3d-preview 9.0.29, see illustrator/out/padding_notes.md):
  tableHeightmap = image resampled to 128 x 128 (8-bit RED channel, a 16-bit PNG is read as its high byte) over a 200 x 200 unit box, 100 x 100 cells.
  1 unit = 1000 canvas px = 1000/ppf ft.  Vertex height above the table plane =
      r/255 * 10 * tableHeightmapScale units * clamp((distance from canvas centre - R) / 10, 0, 1),   R = max(canvas w, h) / 2000 units,
  the plane lies 11 px below the scene ground plus the level's elevation.bottom (ft). So inside the circle of radius R the table is FLAT, rises over the next
  10 units, and the last vertex row/column (x or z = +100) is never displaced. This module inverts that formula to reproduce a chosen surface, and adds
  an "apron" mesh (a real, textured GLB tile with graded resolution) between the terrain tile's edge and the table so the ground has no seam.
"""
import argparse
import glob
import io
import json
import math
import os
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PRESET_DIR = os.path.join(REPO, "illustrator", "presets", "padding")
USER_PRESET_DIR = os.path.join(REPO, "illustrator", "presets", "padding", "user")

# ---- measured 3D Canvas constants (main.js createTable / helpers/applyHeightmap.js)
FACTOR = 1000.0            # canvas px per world unit
TABLE_UNITS = 200.0        # side of the heightmap table box (matcustom + heightmap)
TABLE_DIV = 100            # cells per side
IMG = 128                  # the heightmap is drawn into a 128 x 128 canvas
HEIGHT_UNITS = 10.0        # units of displacement at scale 1, pixel value 255
RAMP_UNITS = 10.0          # displacement ramps in over this many units beyond R
TOP_OFFSET_PX = 11.0       # table top is 0.011 units below the level's bottom
SCALE_MIN, SCALE_MAX = 0.01, 10.0
CAMERA_FAR_UNITS = 100.0   # without fog
FT_M = 0.3048


# =============================================================================== scale math
def ft_per_unit(ppf):
    return FACTOR / ppf


def scale_for_max(max_ft, ppf):
    """Smallest tableHeightmapScale (0.01 steps) whose pixel value 255 reaches max_ft above the table base."""
    s = math.ceil(max(max_ft, 0.0) / (HEIGHT_UNITS * ft_per_unit(ppf)) * 100 - 1e-9) / 100.0
    return float(min(SCALE_MAX, max(SCALE_MIN, s)))


def max_height_ft(scale, ppf):
    """Height in ft of pixel value 255 at `scale`, beyond the ramp."""
    return HEIGHT_UNITS * scale * ft_per_unit(ppf)


def canvas_dims(scene_w, scene_h, padding, grid_px):
    """Foundry canvas size in px for a scene (padding rounded up to whole grid squares). Returns (cw, ch, sceneX, sceneY)."""
    px = math.ceil(scene_w * padding / grid_px - 1e-9) * grid_px if padding else 0
    py = math.ceil(scene_h * padding / grid_px - 1e-9) * grid_px if padding else 0
    return scene_w + 2 * px, scene_h + 2 * py, px, py


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


# =============================================================================== the module's table, simulated
class TableModel:
    """Exact prediction of the table surface 3D Canvas builds. Heights are ft relative to the table plane (base_ft + sim - top offset = scene elevation)."""

    def __init__(self, ppf, canvas_w, canvas_h, scale, image=None, centre_ft=(0.0, 0.0), base_ft=0.0):
        self.ppf, self.cw, self.ch, self.scale = float(ppf), float(canvas_w), float(canvas_h), float(scale)
        self.centre, self.base_ft = centre_ft, float(base_ft)
        self.R = max(canvas_w, canvas_h) / FACTOR / 2.0
        self.K = max_height_ft(scale, ppf)
        self.image = np.zeros((IMG, IMG), np.uint8) if image is None else np.asarray(image, np.uint8)
        idx = np.arange(TABLE_DIV + 1)
        self.vu = -TABLE_UNITS / 2 + idx * (TABLE_UNITS / TABLE_DIV)               # vertex coordinate in units
        self.cols = np.array([min(IMG, math.floor((2 * i / TABLE_UNITS) * IMG)) for i in idx])   # floor(u*128), as the module computes it (u = (x - min)/(max - min))
        UX, UZ = np.meshgrid(self.vu, self.vu)                                    # [iz, ix]
        self.ramp = np.clip((np.hypot(UX, UZ) - self.R) / RAMP_UNITS, 0, 1)
        r = np.zeros((TABLE_DIV + 1, TABLE_DIV + 1))
        ok = self.cols < IMG                                                      # u = 1 reads outside the canvas: stays 0
        rr = self.image[np.ix_(self.cols[ok], self.cols[ok])].astype(float)
        r[np.ix_(ok, ok)] = rr
        self.r = r
        self.vz = r / 255.0 * self.K * self.ramp                                  # [iz, ix] ft above the plane

    def top_ft(self):
        return TOP_OFFSET_PX / self.ppf

    def vertex_xy_ft(self):
        fu = ft_per_unit(self.ppf)
        return self.centre[0] + self.vu * fu, self.centre[1] + self.vu * fu       # x per column, y per row

    def surface(self, x_ft, y_ft):
        """Scene elevation (ft) of the table at place coordinates (triangles of BoxGeometry: diagonal from (ix, iz+1) to (ix+1, iz))."""
        fu = ft_per_unit(self.ppf)
        u = (np.asarray(x_ft, float) - self.centre[0]) / fu
        v = (np.asarray(y_ft, float) - self.centre[1]) / fu
        step = TABLE_UNITS / TABLE_DIV
        gx = np.clip((u + TABLE_UNITS / 2) / step, 0, TABLE_DIV - 1e-9)
        gz = np.clip((v + TABLE_UNITS / 2) / step, 0, TABLE_DIV - 1e-9)
        ix, iz = gx.astype(int), gz.astype(int)
        fx, fz = gx - ix, gz - iz
        a, b, c, d = self.vz[iz, ix], self.vz[iz + 1, ix], self.vz[iz + 1, ix + 1], self.vz[iz, ix + 1]
        h = np.where(fx + fz <= 1, a + fx * (d - a) + fz * (b - a), c + (1 - fx) * (b - c) + (1 - fz) * (d - c))
        return self.base_ft - self.top_ft() + h


def make_image(target_ft, model_kw):
    """Pixel image (128 x 128 uint8) whose table realises `target_ft` (ft above the base, BEFORE the ramp) at the 101 x 101 vertices. Returns (image, scale)."""
    ppf = model_kw["ppf"]
    T = np.clip(np.asarray(target_ft, float), 0, None)
    scale = scale_for_max(T[:-1, :-1].max(), ppf)
    K = max_height_ft(scale, ppf)
    r = np.clip(np.round(T / K * 255.0), 0, 255).astype(np.uint8)
    cols = np.array([min(IMG, math.floor((2 * i / TABLE_UNITS) * IMG)) for i in range(TABLE_DIV + 1)])
    img = np.zeros((IMG, IMG), np.uint8)
    used = np.full(IMG, False)
    for i in range(TABLE_DIV):
        for j in range(TABLE_DIV):
            img[cols[j], cols[i]] = r[j, i]
        used[cols[i]] = True
    for c in range(IMG):                                   # columns / rows no vertex reads: copy the previous used one (never sampled)
        if not used[c]:
            prev = c - 1
            while prev >= 0 and not used[prev]:
                prev -= 1
            img[c, :] = img[max(prev, 0), :]
            img[:, c] = img[:, max(prev, 0)]
    return img, scale


# =============================================================================== presets
def list_presets():
    out = {}
    for d in (PRESET_DIR, USER_PRESET_DIR):
        for p in sorted(glob.glob(os.path.join(d, "*.json"))):
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
            out[j.get("name") or os.path.splitext(os.path.basename(p))[0]] = dict(j, _file=p, _user=(d == USER_PRESET_DIR))
    return out


def load_preset(name):
    allp = list_presets()
    if name not in allp:
        raise KeyError(f"unknown padding preset {name!r}; have {sorted(allp)}")
    return {k: v for k, v in allp[name].items() if not k.startswith("_")}


def save_preset(name, preset, overwrite=True):
    os.makedirs(USER_PRESET_DIR, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in name).strip("-") or "preset"
    p = os.path.join(USER_PRESET_DIR, safe + ".json")
    if os.path.exists(p) and not overwrite:
        raise FileExistsError(p)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(dict({k: v for k, v in preset.items() if not k.startswith("_")}, name=name), f, indent=1)
    return p


# =============================================================================== place data
class Noise:
    """Tileable value noise sampled by world coordinates (feet). `wavelength_ft` is the dominant feature size; two layers with incommensurate periods hide the repeat."""

    def __init__(self, seed, wavelength_ft, beta=2.4, kmin=2, n=384):
        import worldpack_pbr as pbr
        self.n = n
        beta = max(beta, 4.3)          # below ~4 the field has more slope variance at the grid scale than at the feature scale: facets and speckle
        self.layers = []
        for k, (ratio, w) in enumerate(((1.0, 0.62), (1.618, 0.38))):
            a = pbr.fbm(n, seed * 7 + k, beta, kmin).astype(np.float64)
            self.layers.append((float(wavelength_ft) * kmin * 2.0 * ratio, (a - a.mean()) / max(a.std(), 1e-9), w))

    def _one(self, a, period, x, y):
        n = self.n
        fx = (np.asarray(x, float) / period % 1.0) * n
        fy = (np.asarray(y, float) / period % 1.0) * n
        i0, j0 = np.floor(fy).astype(int) % n, np.floor(fx).astype(int) % n
        tx, ty = fx - np.floor(fx), fy - np.floor(fy)
        i1, j1 = (i0 + 1) % n, (j0 + 1) % n
        return a[i0, j0] * (1 - tx) * (1 - ty) + a[i0, j1] * tx * (1 - ty) + a[i1, j0] * (1 - tx) * ty + a[i1, j1] * tx * ty

    def __call__(self, x, y, ridged=False):
        v = sum(w * self._one(a, per, x, y) for per, a, w in self.layers)      # roughly unit variance
        v = np.clip(v / 2.2, -1, 1)                                             # -1..1 (2.2 sigma)
        return 1.0 - 2.0 * np.abs(v) if ridged else v


def terrain_stats(h, cell):
    """Statistics of a heightmap used to match the procedural continuation: relief (p5..p95), rms slope (deg), spectral exponent beta."""
    h = np.asarray(h, float)
    gy, gx = np.gradient(h, cell)
    F = np.abs(np.fft.fftshift(np.fft.fft2(h - h.mean()))) ** 2
    ny, nx = h.shape
    fy, fx = np.meshgrid(np.fft.fftshift(np.fft.fftfreq(ny)), np.fft.fftshift(np.fft.fftfreq(nx)), indexing="ij")
    r = np.hypot(fx * nx, fy * ny)
    sel = (r >= 2) & (r <= min(nx, ny) / 4)
    beta = 2.4
    if sel.sum() > 20:
        lr, lp = np.log(r[sel]), np.log(F[sel] + 1e-9)
        beta = float(np.clip(-np.polyfit(lr, lp, 1)[0], 1.2, 3.4))
    return {"relief_ft": float(np.percentile(h, 95) - np.percentile(h, 5)), "slope_rms_deg": float(np.degrees(np.arctan(np.sqrt(np.mean(gx ** 2 + gy ** 2))))),
            "beta": beta, "min_ft": float(h.min()), "max_ft": float(h.max())}


def _bilinear(h, cell, x, y):
    ny, nx = h.shape
    fx = np.clip(np.asarray(x, float) / cell, 0, nx - 1.000001)
    fy = np.clip(np.asarray(y, float) / cell, 0, ny - 1.000001)
    j, i = fx.astype(int), fy.astype(int)
    tx, ty = fx - j, fy - i
    return h[i, j] * (1 - tx) * (1 - ty) + h[i, j + 1] * tx * (1 - ty) + h[i + 1, j] * (1 - tx) * ty + h[i + 1, j + 1] * tx * ty


class Place:
    """The terrain a place exports (the exact heights of the GLB tile) plus the parent bowl heightmap in the same frame."""

    def __init__(self, place, world_root=None, terrain_source="export"):
        import worldio
        self.id = place
        self.root = world_root or os.path.join(REPO, "world")
        pdir = os.path.join(self.root, place)
        man = os.path.join(pdir, "export", "manifest.json")
        self.manifest = json.load(open(man, encoding="utf-8")) if os.path.exists(man) else {}
        f32 = os.path.join(pdir, "export", "terrain", "heightmap_f32.npy")
        T = self.manifest.get("terrain", {})
        if terrain_source == "export" and os.path.exists(f32):
            self.h = np.load(f32).astype(np.float64)
            self.cell = float(T.get("cell_ft", 2.5))
            self.source = "export/heightmap_f32.npy"
        else:
            h, meta = worldio.load_terrain(place, root=self.root)
            self.h, self.cell, self.source = np.asarray(h, np.float64), float(meta["cell_ft"]), "worldio:" + meta.get("source", "base")
        ny, nx = self.h.shape
        self.W, self.H = (nx - 1) * self.cell, (ny - 1) * self.cell                # tile footprint (the GLB covers exactly this)
        self.glb_dev_ft = 0.0
        zo = self.manifest.get("z_origin_ft")
        self.z_origin = float(zo) if zo is not None else math.floor(float(self.h.min()) / 10.0) * 10.0
        if terrain_source == "export":
            self._adopt_glb(pdir)
        self.ppf = float(self.manifest.get("foundry", {}).get("px_per_ft", 20.0))
        self.window = [float(v) for v in (self.manifest.get("extent", {}).get("min", [0, 0]) + self.manifest.get("extent", {}).get("max", [self.W, self.H]))]
        self.offset, self.bowl, self.bowl_cell, self.bowl_id = self._chain()

    def _adopt_glb(self, pdir):
        """The exported terrain.glb is the mesh the scene really shows: roads are conformed/carved into it, so its heights differ from heightmap_f32 in places (also at the edge).
        Use the GLB's own vertex heights for the seam. Silently keeps the heightmap when the GLB or placements are missing or do not match the grid."""
        g, pl = os.path.join(pdir, "export", "models", "terrain.glb"), os.path.join(pdir, "export", "placements.json")
        if not (os.path.exists(g) and os.path.exists(pl)):
            return
        try:
            P = read_glb_positions(g)
            doc = json.load(open(pl, encoding="utf-8"))
            ent = next(f for f in doc["files"] if f["file"] == "models/terrain.glb")
            ny, nx = self.h.shape
            if len(P) != ny * nx:
                return
            x = P[:, 0] / FT_M + self.W / 2
            y = P[:, 2] / FT_M + self.H / 2
            j, i = np.rint(x / self.cell).astype(int), np.rint(y / self.cell).astype(int)
            z = P[:, 1] / FT_M + float(ent["pivot"]["rel_z_ft"]) + self.z_origin
            if i.min() < 0 or j.min() < 0 or i.max() >= ny or j.max() >= nx or len(set(zip(i.tolist(), j.tolist()))) != len(P):
                return
            h = np.empty_like(self.h)
            h[i, j] = z
            self.glb_dev_ft = float(np.abs(h - self.h).max())
            self.h = h
            self.source += "+terrain.glb"
        except (OSError, ValueError, KeyError, StopIteration):
            return

    def _chain(self):
        """Sum the region.json origins up to the root place; load the root heightmap (the bowl) -> (offset in bowl frame, heights, cell, id)."""
        import worldio
        ox = oy = 0.0
        cur = self.id
        for _ in range(8):
            rj = os.path.join(self.root, cur, "region.json")
            if not os.path.exists(rj):
                break
            r = json.load(open(rj, encoding="utf-8"))
            o = (r.get("transform") or {}).get("origin_ft") or [0.0, 0.0]
            ox, oy = ox + float(o[0]), oy + float(o[1])
            cur = r.get("parent") or cur
            if not r.get("parent"):
                break
        try:
            h, meta = worldio.load_terrain(cur)
            return (ox, oy), np.asarray(h, np.float64), float(meta["cell_ft"]), cur
        except Exception:                                   # no bowl: the place terrain alone
            return (0.0, 0.0), self.h, self.cell, self.id

    # --- terrain tile queries (place frame, absolute ft)
    def tile_h(self, x, y):
        return _bilinear(self.h, self.cell, x, y)

    def rect_dist(self, x, y):
        """(s, qx, qy, nx, ny): distance outside the tile rectangle, nearest rectangle point, outward unit normal (0 when inside)."""
        x, y = np.asarray(x, float), np.asarray(y, float)
        qx, qy = np.clip(x, 0, self.W), np.clip(y, 0, self.H)
        dx, dy = x - qx, y - qy
        s = np.hypot(dx, dy)
        sn = np.where(s > 1e-9, s, 1.0)
        nxv, nyv = np.where(s > 1e-9, dx / sn, 0.0), np.where(s > 1e-9, dy / sn, 0.0)
        return s, qx, qy, nxv, nyv


# =============================================================================== the surrounding surface
class FarField:
    """Desired surroundings C(x, y) in absolute ft (place frame), from the real bowl heightmap and the preset's procedural continuation."""

    def __init__(self, place, preset, seed=7, height_scale=1.0, base_abs=None):
        self.p, self.pr, self.seed, self.hs = place, dict(preset), int(seed), float(height_scale)
        st = terrain_stats(place.bowl, place.bowl_cell)
        self.stats = st
        beta = st["beta"] if str(self.pr.get("beta", "auto")) == "auto" else float(self.pr["beta"])
        self.beta = beta
        e = np.concatenate([place.h[0], place.h[-1], place.h[:, 0], place.h[:, -1]])
        self.edge_mean = float(e.mean())
        self.base_abs = float(base_abs) if base_abs is not None else self.edge_mean
        P = self.pr
        self.n_hill = Noise(self.seed, float(P.get("hills_wavelength_ft", 2500)), beta, 2)
        self.n_ridge = Noise(self.seed + 1, float(P.get("ridge_wavelength_ft", 2200)), beta - 0.4, 3)
        self.n_ridge2 = Noise(self.seed + 4, float(P.get("ridge_wavelength_ft", 2200)) / 2.3, beta - 0.4, 3)
        self.n_det = Noise(self.seed + 2, float(P.get("detail_wavelength_ft", 120)), 1.8, 3)
        self.n_wall = Noise(self.seed + 6, 900.0, 2.4, 2)
        # bowl extension beyond its rim: nearest values of a slightly blurred bowl
        from scipy import ndimage
        self.bowl_s = ndimage.gaussian_filter(place.bowl, 2.0, mode="nearest")
        self.bW, self.bH = (place.bowl.shape[1] - 1) * place.bowl_cell, (place.bowl.shape[0] - 1) * place.bowl_cell
        self.amp_scale = max(0.4, min(2.0, st["relief_ft"] / 280.0))              # larger bowls make taller continuations (matching statistics)

    def _bowl(self, X, Y):
        p = self.p
        bx, by = X + p.offset[0], Y + p.offset[1]
        cx, cy = np.clip(bx, 0, self.bW), np.clip(by, 0, self.bH)
        from scipy import ndimage
        c = p.bowl_cell
        v = ndimage.map_coordinates(p.bowl, [cy / c, cx / c], order=1, mode="nearest")
        vs = ndimage.map_coordinates(self.bowl_s, [cy / c, cx / c], order=1, mode="nearest")
        dist = np.hypot(bx - cx, by - cy)
        return v, vs, dist

    def _synthetic(self, X, Y, level, dist_ft):
        P = self.pr
        a = self.amp_scale
        z = np.full(np.shape(X), float(level))
        if P.get("hills_amp_ft"):
            z += P["hills_amp_ft"] * self.hs * self.n_hill(X, Y)
        if P.get("ridge_amp_ft"):
            r = 0.65 * self.n_ridge(X, Y, ridged=True) + 0.35 * self.n_ridge2(X, Y, ridged=True)
            r = np.clip(0.2 + 0.8 * r, 0, 1)
            z += P["ridge_amp_ft"] * self.hs * a * r * smoothstep((dist_ft - P.get("ridge_start_ft", 0)) / max(P.get("ridge_ramp_ft", 1500), 1))
        if P.get("wall_height_ft"):
            th = math.radians(P.get("wall_axis_deg", 0.0))
            cxp, cyp = self.p.W / 2, self.p.H / 2
            u = -(X - cxp) * math.sin(th) + (Y - cyp) * math.cos(th)                # across the valley axis
            w = smoothstep((np.abs(u) - P["wall_half_gap_ft"]) / max(P["wall_ramp_ft"], 1))
            z += P["wall_height_ft"] * self.hs * w * (0.8 + 0.4 * self.n_wall(X, Y))
        return z

    def abs_height(self, X, Y):
        """Absolute elevation (ft) of the surroundings, ignoring the table's flat zone and the apron (those are applied by the builders)."""
        P, p = self.pr, self.p
        X, Y = np.asarray(X, float), np.asarray(Y, float)
        s, _, _, _, _ = p.rect_dist(X, Y)
        mode = P.get("real", "all")
        base = self.base_abs + P.get("level_offset_ft", 0.0)
        if P.get("flat"):
            z = np.full(X.shape, base)
        elif mode == "all":
            v, vs, dist = self._bowl(X, Y)
            outside = smoothstep(dist / 250.0)
            ext = vs + P.get("rise_ft", 0.0) * self.hs * smoothstep(dist / max(P.get("rise_dist_ft", 1500), 1))
            z = v * (1 - outside) + ext * outside
            syn = self._synthetic(X, Y, 0.0, dist) * outside                       # relief only (level 0) beyond the rim
            z = z + syn
        else:
            v, vs, dist = self._bowl(X, Y)
            syn = self._synthetic(X, Y, base, s)
            if mode == "near":
                w = 1.0 - smoothstep((s - P.get("real_radius_ft", 500.0)) / max(P.get("real_fade_ft", 800.0), 1))
                z = v * w + syn * (1 - w)
            else:
                z = syn
        if P.get("detail_ft"):
            z = z + P["detail_ft"] * self.n_det(X, Y) * smoothstep(s / 60.0)
        return z


# =============================================================================== the apron field and mesh
def hermite5(t, e0, g0, k0, e1, L):
    t = np.clip(t, 0, 1)
    t3, t4, t5 = t ** 3, t ** 4, t ** 5
    h00 = 1 - 10 * t3 + 15 * t4 - 6 * t5
    h10 = t - 6 * t3 + 8 * t4 - 3 * t5
    h20 = 0.5 * t * t - 1.5 * t3 + 1.5 * t4 - 0.5 * t5
    h01 = 10 * t3 - 15 * t4 + 6 * t5
    return e0 * h00 + L * g0 * h10 + L * L * k0 * h20 + e1 * h01


class Apron:
    """Surface between the terrain tile's edge (exact heights, slope and curvature of the tile) and the table (exact predicted height) over `blend_ft`."""

    DELTA_FT = 0.02

    def __init__(self, place, table, blend_ft, detail_ft=1.5, seed=7, edge_fade_ft=110.0, edge_wide_ft=400.0):
        """edge_fade_ft: distance over which the narrow features of the tile edge (a carved river channel, a road cut, 5 to 60 ft wide) fade out of the apron; the apron then
        continues from the edge profile smoothed over edge_wide_ft. 0 = old behaviour (the channel is extruded out into the apron as a trench/ladder streak)."""
        self.edge_fade, self.edge_wide = float(edge_fade_ft), float(edge_wide_ft)
        self.p, self.t, self.L = place, table, float(blend_ft)
        self.detail = detail_ft
        self.nz = Noise(seed + 9, 150.0, 2.2, 3)
        self.dprobe = 10.0

    def edge_profile(self, qx, qy, nx, ny):
        """Terrain height, outward slope and curvature at the edge points (one-sided differences along the inward normal)."""
        p, d = self.p, self.dprobe
        f0 = p.tile_h(qx, qy)
        f1 = p.tile_h(qx - nx * d, qy - ny * d)
        f2 = p.tile_h(qx - nx * 2 * d, qy - ny * 2 * d)
        g0 = -(-3 * f0 + 4 * f1 - f2) / (2 * d)                                   # outward derivative
        k0 = (f0 - 2 * f1 + f2) / (d * d)
        return f0, np.clip(g0, -0.9, 0.9), np.clip(k0, -0.006, 0.006)

    def _wide_profile(self, qx, qy, nx, ny):
        """Edge profile (height, outward slope, curvature) smoothed along the edge over edge_wide_ft, from 1D tables sampled every cell on each of the four sides
        (a continuous smoothing: a sparse sample comb would print the channel position as bars)."""
        from scipy import ndimage
        p = self.p
        if not hasattr(self, "_wt"):
            self._wt = {}
            sig = max(self.edge_wide / 2.0 / p.cell, 0.5)
            for side, (L, fixed, nxv, nyv, horiz) in {"N": (p.W, 0.0, 0.0, -1.0, True), "S": (p.W, p.H, 0.0, 1.0, True),
                                                      "W": (p.H, 0.0, -1.0, 0.0, False), "E": (p.H, p.W, 1.0, 0.0, False)}.items():
                u = np.arange(0.0, L + 1e-6, p.cell)
                qx_, qy_ = (u, np.full_like(u, fixed)) if horiz else (np.full_like(u, fixed), u)
                prof = self.edge_profile(qx_, qy_, np.full_like(u, nxv), np.full_like(u, nyv))
                self._wt[side] = (u, [ndimage.gaussian_filter1d(v, sig, mode="nearest") for v in prof])
        out, wsum = [np.zeros(np.shape(qx)) for _ in range(3)], np.zeros(np.shape(qx))
        d = np.abs(ny) - np.abs(nx)                                   # > 0: north/south side dominates; soft over the corner diagonal so no seam line shows
        wv = 1.0 / (1.0 + np.exp(-d * 12.0))
        for side, w, coord in (("N", wv * (ny < 0), qx), ("S", wv * (ny >= 0), qx), ("W", (1 - wv) * (nx < 0), qy), ("E", (1 - wv) * (nx >= 0), qy)):
            u, vals = self._wt[side]
            wsum += w
            for o, v in zip(out, vals):
                o += w * np.interp(coord, u, v)
        out = [o / np.maximum(wsum, 1e-9) for o in out]
        return out

    def table_target(self, X, Y):
        return self.t.surface(X, Y) + self.DELTA_FT

    def height(self, X, Y):
        """Scene elevation (ft above z_origin) of the apron at place coordinates."""
        p = self.p
        s, qx, qy, nx, ny = p.rect_dist(X, Y)
        e0x, g0x, k0x = self.edge_profile(qx, qy, nx, ny)             # exact tile edge heights (used at the seam itself)
        # the shape uses the edge profile smoothed along the edge (the tile's 2.5 ft nodes carry detail whose slope would fan out as ridges); the residual dies in ~12 ft
        tx, ty = -ny, nx
        acc = [np.zeros(np.shape(X)) for _ in range(3)]
        wsum = 0.0
        for o in (-24, -12, -6, 0, 6, 12, 24):
            w = math.exp(-0.5 * (o / 12.0) ** 2)
            qq = (np.clip(qx + tx * o, 0, p.W), np.clip(qy + ty * o, 0, p.H))
            for a_, v_ in zip(acc, self.edge_profile(qq[0], qq[1], nx, ny)):
                a_ += w * v_
            wsum += w
        e0s, g0, k0 = (a_ / wsum for a_ in acc)
        if self.edge_fade > 0:                                        # fade narrow edge features (river channel, road cut) out over edge_fade ft: continue from the wide-smoothed edge
            wacc = self._wide_profile(qx, qy, nx, ny)
            ww = 1.0
            tt = np.clip(s / self.edge_fade, 0, 1)
            keep = (1 - (3 * tt * tt - 2 * tt ** 3)) ** 2             # 1 at the seam, 0 from edge_fade on
            e0s, g0, k0 = (wv / ww + (nv - wv / ww) * keep for wv, nv in zip(wacc, (e0s, g0, k0)))
        res = np.exp(-np.clip(s, 0, None) / 10.0)
        e0 = e0s + (e0x - e0s) * res - p.z_origin
        g0 = g0 + (g0x - g0) * 0.0
        e1 = self.table_target(X, Y)
        t = s / self.L
        z = hermite5(t, e0, g0, k0, e1, self.L)
        z = z + self.detail * self.nz(X, Y) * (4 * np.clip(t, 0, 1) * (1 - np.clip(t, 0, 1))) ** 1.5
        z = np.where(t >= 1, e1, z)
        return np.maximum(z, e1 if np.ndim(e1) else e1)                          # never below the table (+delta)


def ring_schedule(cell, L, rate=0.06):
    offs, d = [0.0], 0.0
    while d < L - 1e-6:
        step = max(cell, rate * d)
        d = min(L, d + step)
        offs.append(d)
    spac = [max(cell, rate * o) for o in offs]
    return offs, spac


def ring_loop(W, H, d, s):
    """Vertices of the rectangle [-d, W+d] x [-d, H+d], clockwise from its top-left corner (y down); tau in [0, 4) is the side coordinate (corners are integers)."""
    nxs, nys = max(1, int(round((W + 2 * d) / s))), max(1, int(round((H + 2 * d) / s)))
    pts, tau = [], []
    for k in range(nxs):
        pts.append((-d + (W + 2 * d) * k / nxs, -d)); tau.append(k / nxs)
    for k in range(nys):
        pts.append((W + d, -d + (H + 2 * d) * k / nys)); tau.append(1 + k / nys)
    for k in range(nxs):
        pts.append((W + d - (W + 2 * d) * k / nxs, H + d)); tau.append(2 + k / nxs)
    for k in range(nys):
        pts.append((-d, H + d - (H + 2 * d) * k / nys)); tau.append(3 + k / nys)
    return np.array(pts, float), np.array(tau, float)


def zipper(tauA, tauB, offA, offB):
    """Triangles (as global vertex indices) joining closed loop A (inner) to loop B (outer); both start at tau 0."""
    nA, nB = len(tauA), len(tauB)
    i = j = 0
    tris = []
    while i < nA or j < nB:
        ta = tauA[i + 1] if i + 1 < nA else 4.0
        tb = tauB[j + 1] if j + 1 < nB else 4.0
        a0, a1 = offA + i % nA, offA + (i + 1) % nA
        b0, b1 = offB + j % nB, offB + (j + 1) % nB
        if i >= nA:
            tris.append((a0, b0, b1)); j += 1
        elif j >= nB:
            tris.append((a0, a1, b0)); i += 1
        elif ta <= tb:
            tris.append((a0, a1, b0)); i += 1
        else:
            tris.append((a0, b1, b0)); j += 1
    return tris


def build_apron_mesh(apron, rate=0.06):
    p = apron.p
    offs, spac = ring_schedule(p.cell, apron.L, rate)
    loops = [ring_loop(p.W, p.H, d, s) for d, s in zip(offs, spac)]
    P = np.concatenate([l[0] for l in loops])
    base, o = [], 0
    for l in loops:
        base.append(o); o += len(l[0])
    tris = []
    for k in range(len(loops) - 1):
        tris += zipper(loops[k][1], loops[k + 1][1], base[k], base[k + 1])
    tris = np.array(tris, np.int64)
    z = apron.height(P[:, 0], P[:, 1])
    V = np.column_stack([P[:, 0], P[:, 1], z])
    # orient every triangle so its normal points up (glTF: x east, y up, z south == place y)
    a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
    ny = (b[:, 2] - a[:, 2]) * 0 + ((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))      # sign of plan-area (x east, y south)
    flip = ny > 0                                     # with y south, a positive cross is clockwise seen from above; glTF front faces are counter-clockwise from above
    tris[flip] = tris[flip][:, [0, 2, 1]]
    return V, tris, {"rings": len(loops), "offsets": offs, "spacing": spac, "ring_start": base, "ring_len": [len(l[0]) for l in loops]}


def vertex_normals(V, tris):
    X = np.column_stack([V[:, 0], V[:, 2], V[:, 1]]) * FT_M                         # glTF: x, up, z(south)
    a, b, c = X[tris[:, 0]], X[tris[:, 1]], X[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    N = np.zeros_like(X)
    for k in range(3):
        np.add.at(N, tris[:, k], fn)
    n = np.linalg.norm(N, axis=1, keepdims=True)
    return N / np.maximum(n, 1e-12)


def write_glb(path, V, tris, uv, image_jpeg, name="padding_apron", extras=None):
    """One mesh, one material with an embedded JPEG base colour. Vertices V = (x_ft, y_ft, z_ft) in place coordinates; node-local coordinates are
    centred on the bounding box (x, y) with the lowest vertex at 0 (pivot convention of the world pack tiles). Returns the pivot dict."""
    x0, y0, z0 = V.min(0)
    x1, y1, z1 = V.max(0)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    P = np.column_stack([(V[:, 0] - cx) * FT_M, (V[:, 2] - z0) * FT_M, (V[:, 1] - cy) * FT_M]).astype(np.float32)
    N = vertex_normals(V, tris).astype(np.float32)
    UV = np.asarray(uv, np.float32)
    idx = tris.astype(np.uint32).reshape(-1)
    parts = []

    def add(b):
        off = sum(len(x) for x in parts)
        parts.append(b + b"\0" * (-len(b) % 4))
        return off, len(b)
    views, acc = [], []
    for arr, comp, typ, target in ((P, 5126, "VEC3", 34962), (N, 5126, "VEC3", 34962), (UV, 5126, "VEC2", 34962), (idx, 5125, "SCALAR", 34963)):
        off, ln = add(arr.tobytes())
        views.append({"buffer": 0, "byteOffset": off, "byteLength": ln, "target": target})
        a = {"bufferView": len(views) - 1, "componentType": comp, "count": int(len(arr)), "type": typ}
        if typ == "VEC3" and arr is P:
            a["min"], a["max"] = [float(v) for v in P.min(0)], [float(v) for v in P.max(0)]
        acc.append(a)
    off, ln = add(image_jpeg)
    views.append({"buffer": 0, "byteOffset": off, "byteLength": ln})
    g = {"asset": {"version": "2.0", "generator": "padding_heightmap.py"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "name": name, "extras": dict(extras or {})}],
         "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
         "materials": [{"name": "padding_ground", "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}, "metallicFactor": 0.0, "roughnessFactor": 1.0}}],
         "textures": [{"source": 0, "sampler": 0}], "images": [{"bufferView": len(views) - 1, "mimeType": "image/jpeg"}],
         "samplers": [{"magFilter": 9729, "minFilter": 9987, "wrapS": 33071, "wrapT": 33071}],
         "accessors": acc, "bufferViews": views, "buffers": [{"byteLength": sum(len(x) for x in parts)}]}
    js = json.dumps(g, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    bin_ = b"".join(parts)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(bin_)) + struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    with open(path, "wb") as f:
        f.write(out)
    return {"x_ft": float(cx), "y_ft": float(cy), "z_ft": float(z0), "size_ft": [float(x1 - x0), float(y1 - y0), float(z1 - z0)]}


def read_glb_positions(path):
    """POSITION accessor of the first primitive of a GLB (float32 or quantised), in the file's metres. Returns (N, 3)."""
    b = open(path, "rb").read()
    jl, = struct.unpack("<I", b[12:16])
    js = json.loads(b[20:20 + jl])
    off = 20 + jl
    bl, = struct.unpack("<I", b[off:off + 4])
    binc = b[off + 8:off + 8 + bl]
    acc = js["accessors"][js["meshes"][0]["primitives"][0]["attributes"]["POSITION"]]
    bv = js["bufferViews"][acc["bufferView"]]
    start = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    if acc["componentType"] == 5126:
        return np.frombuffer(binc, np.float32, acc["count"] * 3, start).reshape(-1, 3).astype(np.float64)
    raise ValueError("quantised GLB: use the unoptimised models/terrain.glb")


# =============================================================================== checks
def seam_report(place, apron, table, V, info, samples=4000):
    """Numbers for the two joins: terrain edge -> apron (ring 0 vs the tile's edge heights) and apron outer ring -> table surface, plus slope jump at the inner edge."""
    r0 = np.arange(info["ring_start"][0], info["ring_start"][0] + info["ring_len"][0])
    tile = place.tile_h(V[r0, 0], V[r0, 1]) - place.z_origin
    inner = float(np.max(np.abs(V[r0, 2] - tile)))
    last = np.arange(info["ring_start"][-1], info["ring_start"][-1] + info["ring_len"][-1])
    pts = V[last]
    nxt = np.roll(pts, -1, axis=0)
    mid = (pts + nxt) / 2                                  # between vertices the apron edge is a straight chord
    tab = table.surface(mid[:, 0], mid[:, 1]) + Apron.DELTA_FT
    outer = float(np.max(np.abs(mid[:, 2] - tab)))
    outer_v = float(np.max(np.abs(pts[:, 2] - (table.surface(pts[:, 0], pts[:, 1]) + Apron.DELTA_FT))))
    # slope continuity at the edge: apron slope away from the edge vs the tile's slope into it, sampled along the middle of each side
    ss = np.linspace(0.1, 0.9, 9)
    d = 2.0
    jumps = []
    for (qx, qy, nx, ny) in ((ss * place.W, 0 * ss, 0, -1), (ss * place.W, 0 * ss + place.H, 0, 1), (0 * ss, ss * place.H, -1, 0), (0 * ss + place.W, ss * place.H, 1, 0)):
        a1 = apron.height(qx + nx * d, qy + ny * d) - apron.height(qx, qy)
        t1 = place.tile_h(qx, qy) - place.tile_h(qx - nx * d, qy - ny * d)
        jumps.append(np.abs(a1 - t1) / d)
    return {"max_step_terrain_edge_ft": inner, "max_step_terrain_edge_m": inner * FT_M, "max_step_table_vertices_ft": outer_v, "max_step_table_chord_ft": outer,
            "max_step_table_m": max(outer, outer_v) * FT_M, "max_slope_jump_at_edge": float(np.max(jumps)),
            "table_only_step_ft": float(np.max(np.abs(edge_vs_table(place, table))))}


def edge_vs_table(place, table, n=400):
    """Without an apron: tile edge elevation minus the table surface along the tile outline (what the user would see as a cliff/skirt)."""
    t = np.linspace(0, 1, n)
    xs = np.concatenate([t * place.W, 0 * t + place.W, (1 - t) * place.W, 0 * t])
    ys = np.concatenate([0 * t, t * place.H, 0 * t + place.H, (1 - t) * place.H])
    return place.tile_h(xs, ys) - place.z_origin - table.surface(xs, ys)


# =============================================================================== generate
def scene_geometry(place, scene=None, padding=0.25, ppf=None):
    """Canvas geometry of the target scene: from a Foundry scene document (dict) if given, else from the place extent at ppf with `padding`."""
    ppf = float(ppf or place.ppf)
    if scene:
        calib = (scene.get("flags", {}).get("varrenmoor", {}) or {}).get("calib", {}) or {}
        gsz, gd = float(scene["grid"]["size"]), float(scene["grid"]["distance"])
        ppf = float(calib.get("ppf") or gsz / gd)
        cw, ch, sx, sy = canvas_dims(float(scene["width"]), float(scene["height"]), float(scene.get("padding", 0)), gsz)
        x0, y0 = float(calib.get("x0", 0.0)), float(calib.get("y0", 0.0))
        grid = gsz
    else:
        sw, sh = round((place.window[2] - place.window[0] if len(place.window) == 4 else place.W) * ppf), round((place.window[3] - place.window[1]) * ppf)
        grid = round(5 * ppf)
        cw, ch, sx, sy = canvas_dims(sw, sh, padding, grid)
        x0 = y0 = 0.0
    return {"ppf": ppf, "canvas_w": cw, "canvas_h": ch, "sceneX": sx, "sceneY": sy, "x0": x0, "y0": y0, "grid_px": grid,
            "centre_ft": (x0 + (cw / 2 - sx) / ppf, y0 + (ch / 2 - sy) / ppf)}


def generate(place_id, preset_name="bowl-ridge", texture="summer", out_dir=None, scene=None, padding=None, distance_ft=None, blend_ft=200.0, seed=7, height_scale=1.0,
             base_ft=None, apron=True, taper_ft=500.0, tex_px=2048, preset=None, ppf=None, world_root=None, progress=None, apron_albedo_px=None, user_texture_dir=None):
    """Build every artifact. Returns a dict with arrays/paths and the metrics (JSON-able parts under result['meta'])."""
    import padding_textures as pt
    from PIL import Image
    say = progress or (lambda m: None)
    place = Place(place_id, world_root)
    pr = dict(preset if preset is not None else load_preset(preset_name))
    tp = pt.load_texture_preset(texture or pr.get("texture", "summer"), user_texture_dir)
    halfdiag = math.hypot(place.W / 2, place.H / 2)
    geo = scene_geometry(place, scene, 0.25 if padding is None else padding, ppf)
    ppf = geo["ppf"]
    R_flat_ft = max(geo["canvas_w"], geo["canvas_h"]) / FACTOR / 2.0 * ft_per_unit(ppf)
    blend_req = blend_ft
    say("scene geometry")
    far = FarField(place, pr, seed, height_scale)
    # --- base level B (scene elevation ft of the table plane): mean of the surroundings within the flat zone R, blended with the tile edge mean
    R_ft = max(geo["canvas_w"], geo["canvas_h"]) / FACTOR / 2.0 * ft_per_unit(ppf)
    if base_ft is None:
        th = np.linspace(0, 2 * math.pi, 48, endpoint=False)
        cxp, cyp = place.W / 2, place.H / 2
        rr = np.hypot(place.W / 2, place.H / 2) + R_ft * 0.5
        ring = far.abs_height(cxp + rr * np.cos(th), cyp + rr * np.sin(th)) - place.z_origin
        edge = np.concatenate([place.h[0], place.h[-1], place.h[:, 0], place.h[:, -1]]) - place.z_origin
        base_ft = float(min(place.h.min() - place.z_origin, ring.min()))      # at or below every tile vertex, so the table never pokes through the terrain tile
        if pr.get("flat"):
            base_ft = float(place.h.min() - place.z_origin)
    # --- table image
    fu = ft_per_unit(ppf)
    vu = -TABLE_UNITS / 2 + np.arange(TABLE_DIV + 1) * (TABLE_UNITS / TABLE_DIV)
    cx0, cy0 = geo["centre_ft"]
    sub = np.array([-1, 0, 1]) * (2 * fu / 3.0)
    G = np.zeros((TABLE_DIV + 1, TABLE_DIV + 1))
    for dy in sub:
        for dx in sub:
            XX, YY = np.meshgrid(cx0 + vu * fu + dx, cy0 + vu * fu + dy)
            G += far.abs_height(XX, YY)
    G = G / 9.0 - place.z_origin - base_ft
    G = np.clip(G, 0, None)
    # the apron must meet a FLAT table: zero the pixels of every cell that touches the apron, then taper in (vertices are 2 units apart, a cell's diagonal is 2.83 units)
    VX, VY = np.meshgrid(cx0 + vu * fu, cy0 + vu * fu)
    sv = place.rect_dist(VX, VY)[0]
    zero_to = (blend_ft if apron else 0.0) + 2.83 * fu + 1.0
    taper = max(taper_ft, 2.0 * fu)
    G = G * smoothstep((sv - zero_to) / taper)
    if pr.get("flat") or G[:-1, :-1].max() < 0.5:
        img, scale = np.zeros((IMG, IMG), np.uint8), SCALE_MIN
        heightmap_used = False
    else:
        img, scale = make_image(G, {"ppf": ppf})
        heightmap_used = True
    table = TableModel(ppf, geo["canvas_w"], geo["canvas_h"], scale, img, geo["centre_ft"], base_ft)
    say("table heightmap")
    res = {"place": place, "far": far, "table": table, "geo": geo, "preset": pr, "texture_preset": tp, "image": img}
    # --- textures
    tile, mean_hex = pt.table_tile(tp, n=1024, seed=seed + 3)
    res["table_tile"], res["table_mean"] = tile, mean_hex
    say("table texture")
    meta = {"place": place_id, "preset": pr.get("name", preset_name), "texture": tp["name"], "seed": seed, "height_scale": height_scale, "ppf": ppf,
            "z_origin_ft": place.z_origin, "canvas_px": [geo["canvas_w"], geo["canvas_h"]], "scene_px": [geo["sceneX"], geo["sceneY"]], "centre_ft": list(geo["centre_ft"]),
            "tableHeightmapScale": scale, "heightmap_used": heightmap_used, "pixel255_ft": max_height_ft(scale, ppf), "quantisation_ft": max_height_ft(scale, ppf) / 255.0,
            "base_level_ft": base_ft, "base_above_tile_min": bool(base_ft > place.h.min() - place.z_origin + 1e-6), "R_units": table.R, "R_ft": R_ft, "ramp_ft": RAMP_UNITS * fu, "table_span_ft": TABLE_UNITS * fu, "camera_far_ft": CAMERA_FAR_UNITS * fu,
            "table_tile_ft": TABLE_UNITS * fu / (round(TABLE_UNITS / geo["grid_px"] * FACTOR) * 0.1 / 10.0),
            "terrain_stats": far.stats, "beta": far.beta, "tableColor": "#ffffff", "table_mean_colour": mean_hex, "apron": bool(apron), "blend_ft": blend_ft, "taper_ft": taper, "flat_zone_ft": zero_to, "scene_padding": geo.get("padding", padding if scene is None else scene.get("padding")),
            "halfdiag_ft": halfdiag,
            "fog": {"enableFog": bool(tp.get("fog", True)), "fogColor": tp["haze"], "fogDistance_px": int(min(CAMERA_FAR_UNITS * 0.98, tp.get("fog_ft", 14000) / fu) * FACTOR)}}
    if apron:
        ap = Apron(place, table, blend_ft, detail_ft=max(0.5, pr.get("detail_ft", 1.5)), seed=seed)
        V, tris, info = build_apron_mesh(ap)
        say(f"apron mesh {len(V)} vertices")
        rep = seam_report(place, ap, table, V, info)
        meta["seam"] = rep
        meta["apron_mesh"] = {"vertices": int(len(V)), "triangles": int(len(tris)), "rings": info["rings"], "outer_spacing_ft": info["spacing"][-1]}
        bb = (-blend_ft, -blend_ft, place.W + blend_ft, place.H + blend_ft)
        px = apron_albedo_px or tex_px
        w = px
        h = max(64, int(round(px * (place.H + 2 * blend_ft) / (place.W + 2 * blend_ft))))
        ta = None
        tap = os.path.join(world_root or os.path.join(REPO, "world"), place_id, "export", "terrain", "albedo.png")
        if os.path.exists(tap):
            ta = np.asarray(Image.open(tap).convert("RGB"))

        def hfn(X, Y):
            inside = (X >= 0) & (X <= place.W) & (Y >= 0) & (Y <= place.H)
            z = ap.height(X, Y) + place.z_origin
            return np.where(inside, place.tile_h(X, Y), z)

        def seamfn(X, Y):
            s, qx, qy, _, _ = place.rect_dist(X, Y)
            return s, qx, qy
        alb, zmin, zmax = pt.apron_albedo(hfn, bb, (w, h), tp, seed + 5, seamfn, ta, (0, 0, place.W, place.H), blend_ft=blend_ft, far_mean=mean_hex, apron_len=blend_ft, table_tile=tile, tile_ft=meta['table_tile_ft'])
        say("apron albedo")
        res.update(apron=ap, V=V, tris=tris, ring_info=info, apron_albedo=alb, apron_bbox=bb)
    res["meta"] = meta
    return res


def write_outputs(res, out_dir):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    m = res["meta"]
    out = {}
    hm = os.path.join(out_dir, "padding_heightmap.png")
    Image.fromarray(res["image"], "L").save(hm)
    out["heightmap"] = hm
    hm16 = os.path.join(out_dir, "padding_heightmap_16.png")
    Image.fromarray((res["image"].astype(np.uint16) * 257)).save(hm16)       # same data as 16 bit (the module reads the high byte only)
    out["heightmap_16"] = hm16
    tt = os.path.join(out_dir, "padding_table_tile.webp")
    Image.fromarray(res["table_tile"]).save(tt, "WEBP", quality=90)
    out["table_tile"] = tt
    if "apron" in res:
        V, tris, p = res["V"], res["tris"], res["place"]
        bb = res["apron_bbox"]
        uv = np.column_stack([(V[:, 0] - bb[0]) / (bb[2] - bb[0]), (V[:, 1] - bb[1]) / (bb[3] - bb[1])])
        b = io.BytesIO()
        Image.fromarray(res["apron_albedo"]).save(b, "JPEG", quality=90)
        alb = os.path.join(out_dir, "padding_apron_albedo.jpg")
        open(alb, "wb").write(b.getvalue())
        out["apron_albedo"] = alb
        glb = os.path.join(out_dir, "padding_apron.glb")
        piv = write_glb(glb, V, tris, uv, b.getvalue(), extras={"id": f"padding_apron_{p.id}", "layer": "padding"})
        out["apron_glb"] = glb
        m["apron_pivot"] = piv
    pv = os.path.join(out_dir, "padding_preview.png")
    preview(res).save(pv)
    out["preview"] = pv
    mp = os.path.join(out_dir, "padding_meta.json")
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(m, f, indent=1, default=lambda o: float(o) if isinstance(o, np.floating) else str(o))
    out["meta"] = mp
    return out


def preview(res, px=640):
    """Hillshaded colour plan of the realised surface (table + apron + tile) with the tile outline, for the GUI and the notes."""
    from PIL import Image, ImageDraw
    import padding_textures as pt
    table, p, geo = res["table"], res["place"], res["geo"]
    half = TABLE_UNITS / 2 * ft_per_unit(geo["ppf"]) * 0.62
    cx, cy = geo["centre_ft"]
    xs = np.linspace(cx - half, cx + half, px)
    ys = np.linspace(cy - half, cy + half, px)
    X, Y = np.meshgrid(xs, ys)
    Z = table.surface(X, Y)
    if "apron" in res:
        s, *_ = p.rect_dist(X, Y)
        ap = res["apron"]
        Za = ap.height(X, Y)
        use = (s > 0) & (s < ap.L)
        Z = np.where(use, Za, Z)
    inside = (X >= 0) & (X <= p.W) & (Y >= 0) & (Y <= p.H)
    Z = np.where(inside, p.tile_h(X, Y) - p.z_origin, Z)
    gy, gx = np.gradient(Z, ys[1] - ys[0], xs[1] - xs[0])
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    import worldpack_pbr as pbr
    n1 = pbr.fbm(0, 5, 2.2, 6, shape=(px, px))
    n2 = pbr.fbm(0, 6, 2.0, 3, shape=(px, px))
    col = pt.ground_colour(Z + p.z_origin, slope, n2, n1, res["texture_preset"])
    ndl = np.clip(0.55 + 0.9 * (-gx * 0.6 - gy * -0.5) * 1.2, 0.35, 1.25)
    img = pt.to_u8(col * ndl[..., None])
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    f = px / (2 * half)
    d.rectangle([(0 - (cx - half)) * f, (0 - (cy - half)) * f, (p.W - (cx - half)) * f, (p.H - (cy - half)) * f], outline=(255, 40, 40), width=2)
    return im


# =============================================================================== push
def scene_flags(res, asset_paths):
    m = res["meta"]
    tp = res["texture_preset"]
    fl = {"renderTable": "matcustom", "tableTex": asset_paths["table_tile"], "tableColor": "#ffffff", "renderBackground": False}
    if m["heightmap_used"]:
        fl.update(tableHeightmap=asset_paths["heightmap"], tableHeightmapScale=m["tableHeightmapScale"])
    else:
        fl.update(tableHeightmap="", tableHeightmapScale=1)
    if tp.get("fog", True):
        fl.update(enableFog=True, fogColor=tp["haze"], fogDistance=m["fog"]["fogDistance_px"])
    else:
        fl.update(enableFog=False)
    return fl


def apron_tile(res, glb_path, c):
    """Tile document data (x, y, size in px) for the apron GLB at the scene calibration c = {ppf, x0, y0, sceneX, sceneY}."""
    piv = res["meta"]["apron_pivot"]
    ppf = c["ppf"]
    return {"x": round(c["sceneX"] + (piv["x_ft"] - c["x0"]) * ppf), "y": round(c["sceneY"] + (piv["y_ft"] - c["y0"]) * ppf),
            "width": round(piv["size_ft"][0] * ppf), "height": round(piv["size_ft"][1] * ppf), "elevation": round(piv["z_ft"], 3), "rotation": 0,
            "texture": {"src": "modules/levels-3d-preview/assets/blank.webp"},
            "flags": {"levels-3d-preview": {"model3d": glb_path, "autoGround": False, "autoCenter": False, "collision": False, "sight": False,
                                            "depth": max(2, round(piv["size_ft"][2] * ppf))}, "varrenmoor": {"padding": True}}}


def push(res, out_files, scene_uuid, br=None, dry_run=True, assets_root=None, set_level=True, padding=None, log=print):
    """Publish the assets (versioned) and write scene flags / apron tile / level elevation. With dry_run nothing is written or sent (reads only)."""
    import foundry_push as fp
    from PIL import Image
    br = br or fp.PsBridge()
    root = assets_root or fp.assets_dir()
    place = res["place"].id
    plan = {"scene": scene_uuid, "dry_run": bool(dry_run), "assets": {}}
    sub = f"art/{place}/padding"
    hm = Image.open(out_files["heightmap"])
    v, plan["assets"]["heightmap"] = fp.publish_image(hm, sub, "padding_heightmap", root, "png", dry=dry_run)
    tt = Image.open(out_files["table_tile"])
    v, plan["assets"]["table_tile"] = fp.publish_image(tt, sub, "padding_table", root, "webp", dry=dry_run)
    if "apron_glb" in out_files:
        plan["assets"]["apron_glb"] = _publish_bytes(out_files["apron_glb"], sub, "padding_apron", ".glb", root, dry_run)
    flags = scene_flags(res, plan["assets"])
    plan["flags"] = {"levels-3d-preview": flags}
    plan["level_elevation_bottom_ft"] = round(res["meta"]["base_level_ft"], 3)
    if "apron_glb" in out_files:
        sc = br.call("get", uuid=scene_uuid)
        calib = (sc.get("flags", {}).get("varrenmoor", {}) or {}).get("calib", {}) or {}
        c = {"ppf": res["geo"]["ppf"], "x0": calib.get("x0", 0.0), "y0": calib.get("y0", 0.0), "sceneX": res["geo"]["sceneX"], "sceneY": res["geo"]["sceneY"]}
        plan["tile"] = {"id": f"model:{place}:padding_apron", "data": apron_tile(res, plan["assets"]["apron_glb"], c)}
    if dry_run:
        return plan
    data = {"flags": plan["flags"]}
    if padding is not None:
        data["padding"] = padding
    if set_level:
        data["levels"] = [{"_id": "defaultLevel0000", "elevation": {"bottom": plan["level_elevation_bottom_ft"], "top": plan["level_elevation_bottom_ft"] + 20}}]
    br.call("update", uuid=scene_uuid, data=data)
    if "tile" in plan:
        plan["tile_result"] = br.call("upsert_many", documentName="Tile", parentUuid=scene_uuid, items=[plan["tile"]], prefix="model:", prune=False)
    return plan


def _publish_bytes(path, rel_dir, stem, ext, root, dry):
    import re
    d = os.path.join(root, *rel_dir.split("/"))
    data = open(path, "rb").read()
    pat = re.compile(re.escape(stem) + r"_v(\d+)" + re.escape(ext) + "$")
    have = sorted((int(m.group(1)), f) for f in (os.listdir(d) if os.path.isdir(d) else []) for m in [pat.match(f)] if m)
    if have and open(os.path.join(d, have[-1][1]), "rb").read() == data:
        return f"assets/varrenmoor-3d/{rel_dir}/{have[-1][1]}"
    name = f"{stem}_v{(have[-1][0] if have else 0) + 1:03d}{ext}"
    if not dry:
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, name), "wb").write(data)
    return f"assets/varrenmoor-3d/{rel_dir}/{name}"


# =============================================================================== CLI
def _parse_sets(items):
    out = {}
    for it in items or []:
        k, _, v = it.partition("=")
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def _common(ap):
    ap.add_argument("--place", default="bridgehollow__dyers_walk_local")
    ap.add_argument("--preset", default="bowl-ridge")
    ap.add_argument("--texture", default=None, help="texture preset (default: the height preset's own)")
    ap.add_argument("--blend", type=float, default=200.0, help="apron width in ft: terrain edge -> table feather")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--height-scale", type=float, default=1.0, help="vertical multiplier of the surroundings' relief")
    ap.add_argument("--base", type=float, default=None, help="table plane level in ft above z_origin (default: auto from the edge and surroundings)")
    ap.add_argument("--padding", type=float, default=0.25, help="scene padding fraction when no scene is read")
    ap.add_argument("--taper", type=float, default=500.0, help="ft over which the surroundings' relief fades in beyond the apron (the table must stay flat under the apron)")
    ap.add_argument("--no-apron", action="store_true")
    ap.add_argument("--tex-px", type=int, default=2048)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a preset field, e.g. ridge_amp_ft=200")
    ap.add_argument("--out", default=None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("presets")
    g = sp.add_parser("generate")
    _common(g)
    g.add_argument("--scene-json", help="a Foundry scene document (JSON) giving the canvas geometry")
    pu = sp.add_parser("push")
    _common(pu)
    pu.add_argument("--scene-uuid", required=True)
    pu.add_argument("--dry-run", action="store_true")
    pu.add_argument("--scene-padding", type=float, default=None, help="also set the scene's padding to this fraction (default: keep; the apron shrinks to fit the flat zone, or "
                    "use --scene-padding auto-fit via the value printed as recommended_padding)")
    pu.add_argument("--no-level", action="store_true", help="do not set the level's elevation.bottom")
    pu.add_argument("--assets-dir")
    sv = sp.add_parser("save-preset")
    sv.add_argument("--from", dest="src", default="bowl-ridge")
    sv.add_argument("--name", required=True)
    sv.add_argument("--set", action="append", default=[])
    a = ap.parse_args(argv)
    if a.cmd == "presets":
        import padding_textures as pt
        print(json.dumps({"height": {k: {"description": v.get("description", ""), "user": v["_user"]} for k, v in list_presets().items()},
                          "texture": {k: v.get("description", "") for k, v in pt.list_texture_presets().items()}}, indent=1))
        return 0
    if a.cmd == "save-preset":
        pr = dict(load_preset(a.src), **_parse_sets(a.set))
        print(json.dumps({"saved": save_preset(a.name, pr)}))
        return 0
    pr = dict(load_preset(a.preset), **_parse_sets(a.set))
    scene = None
    if a.cmd == "push":
        import foundry_push as fp
        br = fp.PsBridge()
        scene = br.call("get", uuid=a.scene_uuid)
        if a.scene_padding is not None:
            scene = dict(scene, padding=a.scene_padding)
    elif getattr(a, "scene_json", None):
        scene = json.load(open(a.scene_json, encoding="utf-8"))
    out_dir = a.out or os.path.join(REPO, "world", a.place, "export", "padding")
    res = generate(a.place, preset=pr, texture=a.texture, scene=scene, padding=a.padding, blend_ft=a.blend, seed=a.seed, height_scale=a.height_scale,
                   base_ft=a.base, apron=not a.no_apron, taper_ft=a.taper, tex_px=a.tex_px, progress=lambda m: print("  " + m, flush=True))
    outs = write_outputs(res, out_dir)
    summary = {"ok": True, "out_dir": out_dir, "files": outs, **{k: res["meta"][k] for k in ("tableHeightmapScale", "base_level_ft", "pixel255_ft", "quantisation_ft", "heightmap_used")},
               "seam": res["meta"].get("seam")}
    if a.cmd == "push":
        plan = push(res, outs, a.scene_uuid, br=br, dry_run=a.dry_run, assets_root=a.assets_dir, set_level=not a.no_level, padding=a.scene_padding)
        summary["push"] = plan
    print(json.dumps(summary, default=lambda o: float(o) if isinstance(o, np.floating) else str(o)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
