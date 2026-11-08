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


def table_tile(P, n=1024, seed=11, ppf_ft_per_px=None):
    """Seamless (periodic) ground tile: patches of meadow, forest and rock as a mountainside seen from a distance; returns (uint8 RGB, mean sRGB hex)."""
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


def apron_albedo(height_fn, bbox, px, P, seed=5, seam=None, terrain_albedo=None, terrain_box=None, blend_ft=80.0, far_mean=None, apron_len=None):
    """Baked colour map of the apron mesh. height_fn(X, Y) -> absolute elevation ft (vectorised); bbox = (x0, y0, x1, y1) ft; px = (w, h).
    seam(X, Y) -> (s, qx, qy): distance to the terrain rectangle and the nearest point on it (for the colour fade). terrain_albedo = RGB uint8 image covering
    terrain_box (x0, y0, x1, y1) ft; near the seam the colour continues the terrain's own colour and fades to the palette over blend_ft."""
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
        tcol = srgb_to_lin(_soft_terrain(terrain_albedo, terrain_box)[iy, ix, :3])
        t = np.clip(s / blend_ft, 0, 1)
        t = (t * t * (3 - 2 * t))[..., None]
        # the terrain colour carries its own value variation; keep the palette's fine grain on top so the extension is not a smear
        col = tcol * (0.92 + 0.16 * fine)[..., None] * (1 - t) + col * t
    if far_mean is not None and seam is not None and apron_len:        # the outer part of the apron fades to the table tile's mean colour (the tiled table cannot follow the height)
        s = seam(X, Y)[0]
        f = smoothstep01((s - 0.45 * apron_len) / (0.55 * apron_len))[..., None]
        fm = _lin(far_mean)[None, None, :] * (0.88 + 0.24 * fine)[..., None]
        col = col * (1 - f) + fm * f
    return to_u8(col), float(Z.min()), float(Z.max())
