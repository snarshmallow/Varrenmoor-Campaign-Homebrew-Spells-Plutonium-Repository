"""Ground colour for the distant padding: palette presets (summer/autumn/winter/overcast), the height/slope colour model shared with skybox.py's mountains
(meadow / conifer / rock / snow line), a seamless tiling table texture and the baked colour map of the apron mesh.

The 3D Canvas table texture is TILED (about one repeat per 10 world units, see padding_notes.md), so it cannot be aligned to the heightmap: `table_tile`
makes a periodic texture whose mean colour matches the palette. The apron mesh (padding_heightmap.py) is a real mesh, so `apron_albedo` bakes the
height/slope colour into one map aligned to it, fading to the near terrain's own albedo at the seam.
"""
import glob
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
import worldpack_pbr as pbr  # noqa: E402
from skybox import hexrgb, lin_to_srgb, srgb_to_lin  # noqa: E402

TEX_DIR = os.path.join(REPO, "illustrator", "presets", "padding", "textures")


def list_texture_presets(user_dir=None):
    out = {}
    for d in (TEX_DIR, user_dir):
        for p in sorted(glob.glob(os.path.join(d, "*.json"))) if d and os.path.isdir(d) else []:
            with open(p, encoding="utf-8") as f:
                j = json.load(f)
            out[j.get("name") or os.path.splitext(os.path.basename(p))[0]] = j
    return out


def load_texture_preset(name, user_dir=None):
    allp = list_texture_presets(user_dir)
    if name not in allp:
        raise KeyError(f"unknown texture preset {name!r}; have {sorted(allp)}")
    return allp[name]


def _lin(c):
    return srgb_to_lin(hexrgb(c))


def ground_colour(elev, slope, n1, n2, P):
    """Linear RGB (h, w, 3) for absolute elevation (ft), slope (deg) and two 0..1 noise fields. Same model as the skybox's mountains (skybox.render)."""
    meadow, meadow2, forest_c, rock, rock2, snowc, soil = (_lin(P[k]) for k in ("meadow", "meadow2", "forest", "rock", "rock2", "snow", "soil"))
    elev = elev + (n1 - 0.5) * 18
    treeline = P["treeline_ft"] - slope * 3.0 + (n2 - 0.5) * 80
    forest = np.clip((treeline - elev) / 120.0, 0, 1) * np.clip((44 - slope) / 14.0, 0, 1) * P.get("forest_cover", 1.0)
    low = np.clip((760 - elev) / 220.0, 0, 1) * np.clip((22 - slope) / 14.0, 0, 1)
    col = rock[None, None, :] * (1 - n2[..., None] * 0.5) + rock2[None, None, :] * (n2[..., None] * 0.5)
    grass = meadow[None, None, :] * (1 - n1[..., None]) + meadow2[None, None, :] * n1[..., None]
    grass = grass * (1 - 0.18 * np.clip(n2 - 0.6, 0, 1)[..., None] * 2.5) + soil * 0.18 * np.clip(n2 - 0.6, 0, 1)[..., None] * 2.5
    tree = forest_c * (0.7 + 0.6 * n1[..., None]) * (1 - 0.25 * low[..., None]) + grass * low[..., None] * 0.5
    meadow_w = np.clip((900 - elev) / 200.0, 0, 1) * np.clip((32 - slope) / 12.0, 0, 1) * (1 - forest)
    col = col * (1 - forest[..., None]) + tree * forest[..., None]
    col = col * (1 - meadow_w[..., None]) + grass * meadow_w[..., None]
    snowline = P["snowline_ft"] - slope * 4.0 + (n2 - 0.5) * 70
    snow = np.clip((elev - snowline) / 45.0, 0, 1) * np.clip((62 - slope) / 14.0, 0, 1)
    if P.get("snow_all"):
        snow = np.clip(0.55 + (1 - np.clip(slope / 55.0, 0, 1)) * 0.5 + (n2 - 0.5) * 0.35, 0, 1) * (slope < 70)
    col = col * (1 - snow[..., None]) + snowc * snow[..., None]
    return col * _lin(P["tint"])[None, None, :] * P.get("shade", 1.0)


def smoothstep01(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def to_u8(lin):
    return (np.clip(lin_to_srgb(lin / (1 + 0.04 * lin)), 0, 1) * 255 + 0.5).astype(np.uint8)


def _voronoi(n, cells, seed, shape_jitter=0.85):
    """Periodic Voronoi on an n x n raster: returns (cell id 0..cells^2-1, distance to the nearest point, distance to the second nearest) in cell units."""
    rng = np.random.RandomState(seed)
    pts = (np.stack(np.meshgrid(np.arange(cells), np.arange(cells), indexing="ij"), -1) + 0.5 + (rng.rand(cells, cells, 2) - 0.5) * shape_jitter)
    ys = (np.arange(n, dtype=np.float32) + 0.5) / n * cells
    cy = np.floor(ys).astype(int)
    d1 = np.full((n, n), 9.0, np.float32)
    d2 = np.full((n, n), 9.0, np.float32)
    cid = np.zeros((n, n), np.int32)
    for oy in (-1, 0, 1):
        for ox in (-1, 0, 1):
            iy = (cy[:, None] + oy) % cells
            ix = (cy[None, :] + ox) % cells
            iy, ix = np.broadcast_to(iy, (n, n)), np.broadcast_to(ix, (n, n))
            py = pts[iy, ix, 0] + (cy[:, None] + oy - iy)
            px = pts[iy, ix, 1] + (cy[None, :] + ox - ix)
            d = np.hypot(py - ys[:, None], px - ys[None, :]).astype(np.float32)
            new1 = d < d1
            d2 = np.where(new1, d1, np.minimum(d2, d))
            cid = np.where(new1, iy * cells + ix, cid)
            d1 = np.where(new1, d, d1)
    return cid, d1, d2


def _mixc(a, b, t):
    return a[None, None, :] * (1 - t[..., None]) + b[None, None, :] * t[..., None]


def _tile_meadow(P, n, seed):
    g1, g2, soil, rock = (_lin(P[k]) for k in ("meadow", "meadow2", "soil", "rock"))
    macro = pbr.fbm(n, seed, 2.4, 2)
    clump = pbr.fbm(n, seed + 1, 1.5, 9)
    blade = pbr.fbm(n, seed + 2, 0.9, 60)
    dry = np.clip((pbr.fbm(n, seed + 3, 2.6, 2) - 0.62) * 3.2, 0, 1)
    col = _mixc(g1, g2, smoothstep01((macro - 0.25) * 2.0))
    col = col * (0.78 + 0.44 * clump[..., None]) * (0.9 + 0.2 * blade[..., None])
    col = col * (1 - 0.35 * dry[..., None]) + soil[None, None, :] * 0.35 * dry[..., None]
    dots = pbr.fbm(n, seed + 4, 0.2, 90)                                          # near white noise -> sparse flower/seed-head speckle
    fl = np.clip((dots - 0.86) * 12, 0, 1) * (clump > 0.45)
    flower = np.array([0.8, 0.72, 0.3]) * 0.9
    col = col * (1 - fl[..., None] * 0.8) + flower[None, None, :] * fl[..., None] * 0.8
    return col


def _tile_forest_floor(P, n, seed):
    forest, soil, rock, g1 = (_lin(P[k]) for k in ("forest", "soil", "rock", "meadow"))
    macro = pbr.fbm(n, seed, 2.2, 2)
    litter = pbr.fbm(n, seed + 1, 1.2, 40)
    mid = pbr.fbm(n, seed + 2, 1.8, 8)
    moss = np.clip((pbr.fbm(n, seed + 3, 2.4, 3) - 0.55) * 3.0, 0, 1)
    col = _mixc(soil * 0.7, soil * 1.15, macro)
    col = col * (0.7 + 0.6 * litter[..., None]) * (0.85 + 0.3 * mid[..., None])
    col = col * (1 - moss[..., None] * 0.7) + forest[None, None, :] * 1.5 * (0.7 + 0.5 * mid[..., None]) * moss[..., None] * 0.7
    dapple = np.clip((pbr.fbm(n, seed + 4, 3.0, 2) - 0.6) * 2.5, 0, 1)          # patches of sun through the canopy
    col = col * (1 + 0.45 * dapple[..., None] * np.array([1.0, 0.95, 0.7])[None, None, :])
    twig = np.clip((pbr.fbm(n, seed + 5, 0.3, 120) - 0.93) * 14, 0, 1)
    col = col * (1 - 0.5 * twig[..., None])
    return col * 0.85


def _tile_scree(P, n, seed):
    r1, r2, soil = (_lin(P[k]) for k in ("rock", "rock2", "soil"))
    rng = np.random.RandomState(seed)
    cid, d1, d2 = _voronoi(n, 70, seed)
    tone = rng.rand(70 * 70)[cid]
    tilt = rng.randn(70 * 70, 2)[cid] * 0.35
    col = _mixc(r2, r1, tone)
    light = np.clip(0.85 + tilt[..., 0] * 0.5 - tilt[..., 1] * 0.5, 0.45, 1.3)                 # each fragment is a facet with its own tilt
    edge = np.clip((d2 - d1) * 9.0, 0, 1)                                                      # dark crevices between fragments
    boulders = _voronoi(n, 11, seed + 9)
    bt = rng.rand(11 * 11)[boulders[0]]
    bmask = (bt > 0.8) * np.clip((boulders[2] - boulders[1]) * 6, 0, 1)
    grain = pbr.fbm(n, seed + 1, 1.0, 50)
    lichen = np.clip((pbr.fbm(n, seed + 2, 2.4, 4) - 0.6) * 2.5, 0, 1)
    col = col * light[..., None] * (0.55 + 0.45 * edge[..., None]) * (0.88 + 0.24 * grain[..., None])
    col = col * (1 - 0.3 * lichen[..., None]) + soil[None, None, :] * 0.3 * lichen[..., None]
    col = col * (1 - bmask[..., None] * 0.25) * (1 + 0.15 * bmask[..., None])
    return col


def _tile_heather(P, n, seed):
    heath, grass, bil, peat = (_lin(P[k]) for k in ("meadow", "meadow2", "forest", "soil"))
    rock = _lin(P["rock"])
    macro = pbr.fbm(n, seed, 2.4, 2)
    cl = pbr.fbm(n, seed + 1, 1.5, 14)
    clump = smoothstep01((cl - 0.42) * 4.0)                                   # rounded heather hummocks
    fine = pbr.fbm(n, seed + 2, 0.9, 70)
    col = _mixc(peat, bil, smoothstep01((macro - 0.35) * 2.0) * 0.8)
    col = col * (1 - clump[..., None]) + _mixc(heath, grass, smoothstep01((pbr.fbm(n, seed + 3, 2.2, 3) - 0.35) * 2.2)) * (0.7 + 0.5 * cl[..., None]) * clump[..., None]
    col = col * (0.82 + 0.36 * fine[..., None])
    bare = np.clip((pbr.fbm(n, seed + 4, 2.6, 3) - 0.68) * 4.0, 0, 1)
    col = col * (1 - 0.55 * bare[..., None]) + rock[None, None, :] * 0.55 * bare[..., None]
    return col


TILE_KINDS = {"meadow": _tile_meadow, "forest_floor": _tile_forest_floor, "scree": _tile_scree, "heather": _tile_heather}


def table_tile(P, n=1024, seed=11, ppf_ft_per_px=None):
    """Seamless (periodic) ground tile; returns (uint8 RGB, mean sRGB hex). By default patches of meadow, forest and rock as a mountainside seen from a
    distance; a preset with `tile_kind` (meadow, forest_floor, scree, heather) gets a close-up ground texture of that kind instead, tinted by its palette."""
    kind = P.get("tile_kind")
    if kind in TILE_KINDS:
        col = TILE_KINDS[kind](P, n, seed) * _lin(P["tint"])[None, None, :] * P.get("shade", 1.0)
        img = to_u8(col)
        mean = img.reshape(-1, 3).mean(0)
        return img, "#%02x%02x%02x" % tuple(int(round(v)) for v in mean)
    m1 = pbr.fbm(n, seed, 2.6, 2)                 # macro patches
    m2 = pbr.fbm(n, seed + 1, 2.2, 3)
    fine = pbr.fbm(n, seed + 2, 1.6, 24)
    elev = 735 + (m1 - 0.5) * 2 * 230
    gy, gx = np.gradient(pbr.blur(m1, 3))
    slope = np.degrees(np.arctan(np.hypot(gx, gy) * n * 0.06))
    col = ground_colour(elev, slope, m2, fine, P)
    col *= (0.92 + 0.16 * fine)[..., None]
    img = to_u8(col)
    mean = img.reshape(-1, 3).mean(0)
    return img, "#%02x%02x%02x" % tuple(int(round(v)) for v in mean)


def _soft_terrain(alb, box, sigma_ft=45.0):
    """The terrain colour map, blurred so roads and detail do not smear into stripes when it is continued outward."""
    from scipy import ndimage
    px_per_ft = alb.shape[1] / (box[2] - box[0])
    a = alb[..., :3].astype(np.float32) / 255.0
    return np.stack([ndimage.gaussian_filter(a[..., c], sigma_ft * px_per_ft, mode="nearest") for c in range(3)], -1)


def apron_albedo(height_fn, bbox, px, P, seed=5, seam=None, terrain_albedo=None, terrain_box=None, blend_ft=80.0, far_mean=None, apron_len=None, streak_fix=True, table_tile=None, tile_ft=500.0):
    """Baked colour map of the apron mesh. height_fn(X, Y) -> absolute elevation ft (vectorised); bbox = (x0, y0, x1, y1) ft; px = (w, h).
    seam(X, Y) -> (s, qx, qy): distance to the terrain rectangle and the nearest point on it (for the colour fade). terrain_albedo = RGB uint8 image covering
    terrain_box (x0, y0, x1, y1) ft; near the seam the colour continues the terrain's own colour and fades to the palette over blend_ft.
    streak_fix (default on): the terrain colour is continued by projecting the nearest edge texel outward, which smears it into radial streaks, worst on steep apron
    slopes seen from above. With the fix the lookup uses a blur that widens with the distance from the seam (the colour along the edge averages out), the lookup point is
    warped along the edge by noise that grows with distance, and steep ground fades to the height/slope palette (computed per pixel, never stretched) sooner."""
    w, h = px
    x0, y0, x1, y1 = bbox
    xs = x0 + (np.arange(w) + 0.5) * (x1 - x0) / w
    ys = y0 + (np.arange(h) + 0.5) * (y1 - y0) / h
    X, Y = np.meshgrid(xs, ys)
    from scipy import ndimage
    hw, hh = max(32, w // 2), max(32, h // 2)                                     # heights on a half-resolution raster, zoomed up (memory)
    xh = x0 + (np.arange(hw) + 0.5) * (x1 - x0) / hw
    yh = y0 + (np.arange(hh) + 0.5) * (y1 - y0) / hh
    Xh, Yh = np.meshgrid(xh, yh)
    Z = ndimage.zoom(height_fn(Xh, Yh).astype(np.float32), (h / hh, w / hw), order=1)[:h, :w]
    gy, gx = np.gradient(Z, (y1 - y0) / h, (x1 - x0) / w)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    n1 = pbr.fbm(0, seed, 2.2, 6, shape=(h, w)).astype(np.float32)
    n2 = pbr.fbm(0, seed + 1, 2.0, 3, shape=(h, w)).astype(np.float32)
    fine = pbr.fbm(0, seed + 2, 1.5, 40, shape=(h, w)).astype(np.float32)
    col = ground_colour(Z, slope, n2, n1, P).astype(np.float32)
    col *= (0.88 + 0.24 * fine)[..., None]
    if seam is not None and terrain_albedo is not None:
        s, qx, qy = seam(X, Y)
        tx0, ty0, tx1, ty1 = terrain_box
        th, tw = terrain_albedo.shape[:2]
        ix = np.clip(((qx - tx0) / (tx1 - tx0) * tw).astype(int), 0, tw - 1)
        iy = np.clip(((qy - ty0) / (ty1 - ty0) * th).astype(int), 0, th - 1)
        soft = _soft_terrain(terrain_albedo, terrain_box)
        if streak_fix:
            soft2 = _soft_terrain(terrain_albedo, terrain_box, sigma_ft=160.0)
            sd = np.clip(s / max(blend_ft, 1.0), 0, 1)
            wide = smoothstep01((sd - 0.05) / 0.5)[..., None]
            tcol0 = soft[iy, ix, :3] * (1 - wide) + soft2[iy, ix, :3] * wide
            warp = (pbr.fbm(0, seed + 7, 1.8, 5, shape=(h, w)).astype(np.float32) - 0.5) * 2.0 * np.clip(s, 0, None) * 0.9       # ft, grows with distance
            nxp, nyp = (-(qy - Y), (qx - X))                                      # tangent to the edge (perpendicular to the lookup ray)
            ln = np.maximum(np.hypot(nxp, nyp), 1e-6)
            qx2, qy2 = qx + nxp / ln * warp, qy + nyp / ln * warp
            ix2 = np.clip(((qx2 - tx0) / (tx1 - tx0) * tw).astype(int), 0, tw - 1)
            iy2 = np.clip(((qy2 - ty0) / (ty1 - ty0) * th).astype(int), 0, th - 1)
            tcol1 = soft2[iy2, ix2, :3]
            tcol = srgb_to_lin(tcol0 * (1 - wide) + (tcol0 * 0.35 + tcol1 * 0.65) * wide)
            t = np.clip(s / blend_ft, 0, 1)
            steep = smoothstep01((slope - 18.0) / 24.0) * smoothstep01(s / 12.0)
            t = np.clip(np.maximum(t, steep * 0.7), 0, 1)
            t = (t * t * (3 - 2 * t))[..., None]
        else:
            tcol = srgb_to_lin(soft[iy, ix, :3])
            t = np.clip(s / blend_ft, 0, 1)
            t = (t * t * (3 - 2 * t))[..., None]
        # the terrain colour carries its own value variation; keep the palette's fine grain on top so the extension is not a smear
        col = tcol * (0.92 + 0.16 * fine)[..., None] * (1 - t) + col * t
    if far_mean is not None and seam is not None and apron_len:        # the outer part of the apron fades to the table tile's mean colour (the tiled table cannot follow the height)
        s = seam(X, Y)[0]
        f = smoothstep01((s - 0.45 * apron_len) / (0.55 * apron_len))[..., None]
        fm = _lin(far_mean)[None, None, :] * (0.88 + 0.24 * fine)[..., None]
        if table_tile is not None:       # real tiled ground detail (the same tile the table uses, same texel density, wrapped on place coordinates) instead of a flat mean-colour wash
            th_, tw_ = table_tile.shape[:2]
            ux = (np.mod(X, tile_ft) / tile_ft * tw_).astype(int) % tw_
            uy = (np.mod(Y, tile_ft) / tile_ft * th_).astype(int) % th_
            fm = srgb_to_lin(table_tile[uy, ux, :3].astype(np.float32) / 255.0)
            lum = fm.mean(-1, keepdims=True)
            rel = lum / max(float(lum.mean()), 1e-6)
            wd = (smoothstep01(s / 60.0) * (1 - f[..., 0]))[..., None]              # inside the ring: the tile's light/dark ground mottling, not a colour wash (full strength from 60 ft)
            col = col * (1 + 0.5 * wd * (rel - 1.0))
        col = col * (1 - f) + fm * f
    return to_u8(col), float(Z.min()), float(Z.max())
