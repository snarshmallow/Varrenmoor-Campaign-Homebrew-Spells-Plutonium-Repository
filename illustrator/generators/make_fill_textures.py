"""Procedural, seamless 256 px tiles for the town 'full map' fills (roads, roofs, fields, water).

  python illustrator/generators/make_fill_textures.py [--out presets/textures] [--only cobble,slate] [--check]

Every tile is built from wrapped (periodic) noise, periodic Voronoi cells or integer-period patterns, so it tiles with no seam;
fills_raster.py samples them with the same anti-tiling warp as the terrain shading. `--check` prints a seam score per tile
(mean edge-to-edge difference relative to the mean difference between neighbouring pixels: ~1 means no visible seam).
Re-running overwrites the files, so hand-painted replacements should use a different name.
"""
import argparse
import os

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import cKDTree

HERE = os.path.dirname(os.path.abspath(__file__))
TEX_DIR = os.path.abspath(os.path.join(HERE, "..", "presets", "textures"))
S = 256


def col(h):
    h = h.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float)


def sm(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def pn(rng, sy, sx=None, size=S):
    """Periodic Gaussian noise, unit std."""
    n = ndi.gaussian_filter(rng.standard_normal((size, size)), (sy, sx if sx is not None else sy), mode="wrap")
    return n / (n.std() + 1e-9)


def paint(base, n, k):
    """base colour x (1 + k*n) broadcast to HxWx3."""
    return col(base)[None, None, :] * (1 + k * n[..., None])


def mixc(a, b, t):
    return a * (1 - t[..., None]) + b * t[..., None]


def voronoi(rng, n_per_side, jitter=0.4):
    """Periodic jittered-grid Voronoi: returns (cell id, d1, d2) per pixel (px units)."""
    g = (np.arange(n_per_side) + 0.5) * S / n_per_side
    gx, gy = np.meshgrid(g, g)
    pts = np.stack([gx.ravel(), gy.ravel()], 1) + (rng.random((n_per_side ** 2, 2)) - 0.5) * jitter * 2 * S / n_per_side
    pts %= S
    yy, xx = np.mgrid[0:S, 0:S]
    q = np.stack([xx.ravel() + 0.5, yy.ravel() + 0.5], 1)
    d, i = cKDTree(pts, boxsize=S).query(q, k=2)
    return i[:, 0].reshape(S, S), d[:, 0].reshape(S, S), d[:, 1].reshape(S, S), len(pts)


def rows_pattern(rng, rows, per_row, offsets=True, jitter=0.0):
    """Row/course pattern (bricks, slates, shingles, ashlar). Returns (cell id, u, v, row index) with u,v in 0..1 inside a cell.
    per_row: int or list of ints; jitter>0 gives uneven block widths."""
    rh = S / rows
    cid = np.zeros((S, S), int)
    U = np.zeros((S, S))
    V = np.zeros((S, S))
    R = np.zeros((S, S), int)
    xs = np.arange(S) + 0.5
    base = 0
    for r in range(rows):
        y0, y1 = int(round(r * rh)), int(round((r + 1) * rh))
        n = per_row if isinstance(per_row, int) else per_row[r % len(per_row)]
        w = 1 + (rng.random(n) - 0.5) * 2 * jitter
        edges = np.concatenate([[0], np.cumsum(w / w.sum() * S)])
        off = (rng.random() * S if jitter else (0.5 if (offsets and r % 2) else 0.0) * S / n)
        xr = (xs - off) % S
        idx = np.clip(np.searchsorted(edges, xr, side="right") - 1, 0, n - 1)
        u = (xr - edges[idx]) / (edges[idx + 1] - edges[idx])
        for yy in range(y0, y1):
            cid[yy] = base + idx
            U[yy] = u
            V[yy] = (yy + 0.5 - y0) / (y1 - y0)
            R[yy] = r
        base += n
    return cid, U, V, R


def to_img(a):
    return np.clip(a, 0, 255).astype(np.uint8)


# ------------------------------------------------------------------ textures
def t_cobble(rng):
    cid, d1, d2, n = voronoi(rng, 12, 0.38)
    de = d2 - d1
    tone = rng.random(n)[cid]
    base = mixc(col("#8c8579"), col("#a69d8c"), tone)
    warm = rng.random(n)[cid]
    base = mixc(base, col("#9a8d7c"), warm * 0.4)
    bevel = sm(de / 5.0)                                      # 0 in the mortar, 1 in the stone body
    lit = 0.82 + 0.28 * sm(de / 11.0)                         # rounded top of each stone
    img = base * (lit * (0.9 + 0.1 * pn(rng, 1.0)))[..., None]
    img = img * (0.78 + 0.22 * bevel)[..., None] + col("#403a32")[None, None, :] * (1 - bevel)[..., None] * 0.35
    img *= (1 + 0.05 * pn(rng, 6))[..., None]
    return img


def t_gravel(rng):
    n1, n2, n3 = pn(rng, 0.7), pn(rng, 1.4), pn(rng, 12)
    peb = sm((n1 - 0.9) / 0.5)
    dark = sm((-n2 - 0.9) / 0.5)
    img = paint("#a39a88", n3, 0.07) * (1 + 0.10 * n1)[..., None]
    img = mixc(img, col("#d8d0bd"), peb * 0.6)
    img = mixc(img, col("#4f4a40"), dark * 0.55)
    return img


def t_packed_earth(rng):
    n = pn(rng, 22) * 0.6 + pn(rng, 7) * 0.4
    img = paint("#9c7d57", n, 0.10) * (1 + 0.06 * pn(rng, 0.9))[..., None]
    peb = sm((pn(rng, 1.1) - 1.5) / 0.4)
    img = mixc(img, col("#c7b393"), peb * 0.6)
    pat = sm((pn(rng, 9) - 0.9) / 0.6)
    img = mixc(img, col("#6e5538"), pat * 0.4)
    return img


def t_mud(rng):
    n = pn(rng, 14) * 0.6 + pn(rng, 4) * 0.4
    img = paint("#5f4731", n, 0.12)
    wet = sm((pn(rng, 10) - 0.7) / 0.5)
    img = mixc(img, col("#3c2c1f"), wet * 0.6)
    sheen = sm((pn(rng, 2.0) - 1.6) / 0.35) * wet
    img = mixc(img, col("#8d7a5c"), sheen * 0.5)
    img *= (1 + 0.05 * pn(rng, 0.9))[..., None]
    return img


def _planks(rng, nplank, base_a, base_b, grain=0.14, gap="#2a2118", butt=True):
    """Horizontal boards with grain, gaps and staggered butt joints."""
    ph = S / nplank
    yy = np.arange(S)[:, None] + 0.5 + np.zeros((1, S))
    xs = np.arange(S)[None, :] + 0.5
    pid = np.minimum((yy / ph).astype(int), nplank - 1)
    tone = rng.random(nplank)[pid]
    img = mixc(col(base_a) + np.zeros((S, S, 3)), col(base_b), tone)
    gr = pn(rng, 0.6, 38) * 0.6 + pn(rng, 2.2, 90) * 0.4
    img *= (1 + grain * gr)[..., None]
    knot = sm((pn(rng, 3.5, 5) - 2.0) / 0.5)
    img = mixc(img, col(gap), knot * 0.35)
    v = (yy / ph) % 1.0
    edge = np.minimum(v, 1 - v) * ph
    img = mixc(img, col(gap), sm(1.0 - edge / 1.4) * 0.85)
    img *= (0.9 + 0.1 * sm(edge / 4.0))[..., None]
    if butt:
        for p in range(nplank):
            x = rng.random() * S
            dx = np.abs(((xs - x + S / 2) % S) - S / 2)
            m = sm(1.0 - dx / 1.1) * (pid == p)
            img = mixc(img, col(gap), m * 0.8)
    return img


def t_plank(rng):
    return _planks(rng, 8, "#8a6b45", "#a9885c")


def t_timber_roof(rng):
    return _planks(rng, 10, "#5f5546", "#7c6e5a", grain=0.18, gap="#231d16")


def t_stone_slab(rng):
    rows = 8
    cid, u, v, r = rows_pattern(rng, rows, 4, jitter=0.35)
    n = cid.max() + 1
    tone = rng.random(n)[cid]
    img = mixc(col("#8a8a86") + np.zeros((S, S, 3)), col("#aaa79e"), tone)
    img = mixc(img, col("#9a8f80"), rng.random(n)[cid] * 0.35)
    img *= (1 + 0.10 * pn(rng, 5) + 0.05 * pn(rng, 0.8))[..., None]
    e = np.minimum.reduce([u * S / 4, (1 - u) * S / 4, v * S / rows, (1 - v) * S / rows])
    # distance from the cell edge in px (u spans ~S/4 wide)
    img = mixc(img, col("#4d4a44"), sm(1.0 - e / 1.6) * 0.8)
    img *= (0.88 + 0.12 * sm(e / 5.0))[..., None]
    return img


def _overlap(rng, rows, per, base_a, base_b, edge_col, tone_k=0.35, round_bottom=0.0, grain=0.05, shade=0.30):
    cid, u, v, r = rows_pattern(rng, rows, per, offsets=True)
    n = cid.max() + 1
    tone = rng.random(n)[cid]
    img = mixc(col(base_a) + np.zeros((S, S, 3)), col(base_b), tone)
    img *= (1 + tone_k * (rng.random(n)[cid] - 0.5))[..., None]
    img *= (1 + grain * pn(rng, 0.9) + 0.06 * pn(rng, 8))[..., None]
    # light on the upper (exposed) part of each slate, a shadow line where the next course overlaps it
    img *= (1 + shade * (0.5 - v) * 0.8)[..., None]
    rh = S / rows
    vb = (1 - v) * rh
    if round_bottom:
        vb = vb + round_bottom * rh * (np.abs(u - 0.5) * 2) ** 2          # rounded/pointed tails
    img = mixc(img, col(edge_col), sm(1.0 - vb / 2.0) * 0.75)
    side = np.minimum(u, 1 - u) * (S / (per if isinstance(per, int) else per[0]))
    img = mixc(img, col(edge_col), sm(1.0 - side / 1.0) * 0.45)
    return img


def t_slate(rng):
    return _overlap(rng, 16, 8, "#4a525c", "#6a7480", "#1d2229", tone_k=0.30)


def t_shingle(rng):
    return _overlap(rng, 16, 16, "#6a4d36", "#8f6d4a", "#241a12", tone_k=0.45, round_bottom=0.22, grain=0.09)


def t_red_tile(rng):
    img = _overlap(rng, 16, 8, "#9b4b34", "#bf6a45", "#3b1a12", tone_k=0.30, shade=0.35)
    xs = np.arange(S)[None, :] + np.zeros((S, 1))
    img *= (1 + 0.10 * np.sin(2 * np.pi * xs * 16 / S))[..., None]          # barrel curve
    return img


def t_thatch(rng):
    n = pn(rng, 22, 0.9) * 0.6 + pn(rng, 6, 0.8) * 0.4
    img = paint("#b39a58", n, 0.14)
    hi = sm((pn(rng, 9, 0.7) - 0.6) / 0.7)
    img = mixc(img, col("#d9c27d"), hi * 0.45)
    dk = sm((pn(rng, 12, 0.6) + 0.4) / 0.9)
    img = mixc(img, col("#6e5a30"), (1 - dk) * 0.5)
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    band = 0.5 + 0.5 * np.cos(2 * np.pi * yy * 8 / S)                        # courses of straw
    img *= (0.88 + 0.12 * band)[..., None]
    img *= (1 + 0.05 * pn(rng, 0.8))[..., None]
    return img


def t_tilled(rng):
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    ph = 2 * np.pi * yy * 16 / S + pn(rng, 20, 20) * 0.5                       # slightly wavy furrows
    prof = 0.5 + 0.5 * np.sin(ph)
    img = mixc(col("#5a4029") + np.zeros((S, S, 3)), col("#8a6a45"), prof)
    clod = sm((pn(rng, 1.3) - 0.9) / 0.5)
    img = mixc(img, col("#b09a78"), clod * 0.35)
    img *= (1 + 0.10 * pn(rng, 0.8) + 0.06 * pn(rng, 10))[..., None]
    return img


def t_wheat(rng):
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    prof = 0.5 + 0.5 * np.sin(2 * np.pi * yy * 21 / S + pn(rng, 20, 20) * 0.4)
    img = mixc(col("#bd9b3f") + np.zeros((S, S, 3)), col("#e2c568"), prof)
    ear = pn(rng, 0.7, 2.4)
    img *= (1 + 0.14 * ear + 0.07 * pn(rng, 10))[..., None]
    img = mixc(img, col("#7e6122"), sm(1.0 - prof * 1.5) * 0.3)
    return img


def t_crop_green(rng):
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    xx = np.arange(S)[None, :] + np.zeros((S, 1))
    rows = 16
    prof = np.sin(np.pi * ((yy * rows / S) % 1.0)) ** 1.2
    bump = 0.5 + 0.5 * np.sin(2 * np.pi * (xx * 32 / S + (np.floor(yy * rows / S) % 2) * 0.5))
    plant = prof * (0.55 + 0.45 * bump)
    img = mixc(col("#6b5436") + np.zeros((S, S, 3)), col("#5c9a3a"), sm(plant * 1.3))
    img = mixc(img, col("#9bc96b"), sm((plant - 0.8) * 4) * 0.5)
    img *= (1 + 0.10 * pn(rng, 0.9) + 0.07 * pn(rng, 9))[..., None]
    return img


def t_pasture(rng):
    n = pn(rng, 16) * 0.55 + pn(rng, 5) * 0.45
    img = paint("#7aa648", n, 0.14)
    cl = sm((pn(rng, 3) - 0.7) / 0.5)
    img = mixc(img, col("#98c15a"), cl * 0.5)
    fl = sm((pn(rng, 1.0) - 2.0) / 0.3)                                       # a few pale flowers
    img = mixc(img, col("#e8e29a"), fl * 0.6)
    img *= (1 + 0.08 * pn(rng, 0.8))[..., None]
    return img


def t_water(rng):
    n = pn(rng, 12) * 0.6 + pn(rng, 4) * 0.4
    img = paint("#4d82ab", n, 0.10)
    a = pn(rng, 3.5, 7.0)
    ridge = 1.0 - np.abs(a)                                                  # thin bright wave crests where noise crosses zero
    crest = sm((ridge - 0.93) / 0.07)
    img = mixc(img, col("#b4d6e8"), crest * 0.55)
    b = pn(rng, 8, 3.0)
    trough = sm((1.0 - np.abs(b) - 0.95) / 0.05)
    img = mixc(img, col("#2c5679"), trough * 0.35)
    return img


# ------------------------------------------------------------------ winter set (Bridgehollow winter map; names prefixed w_)
SNOW = "#eef3f8"
SNOW_SH = "#c9d6e4"


def _snow_base(rng, drift=0.045, ripple=0.03):
    n = pn(rng, 16) * 0.6 + pn(rng, 5) * 0.4
    img = mixc(col(SNOW) + np.zeros((S, S, 3)), col(SNOW_SH), sm(0.5 - n * 0.5))
    img *= (1 + drift * pn(rng, 24))[..., None]
    wind = pn(rng, 1.6, 9.0)
    img = mixc(img, col("#ffffff"), sm((wind - 1.2) / 0.6) * 0.5)
    img = mixc(img, col("#b4c4d6"), sm((-wind - 1.3) / 0.6) * 0.3)
    spark = sm((pn(rng, 0.6) - 2.3) / 0.25)
    img = mixc(img, col("#ffffff"), spark * 0.7)
    return img * (1 + ripple * pn(rng, 0.9))[..., None]


def t_w_snow(rng):
    return _snow_base(rng)


def t_w_frost_grass(rng):
    n = pn(rng, 18) * 0.55 + pn(rng, 5) * 0.45
    img = paint("#a8a487", n, 0.10)
    blades = pn(rng, 0.7, 4.5)
    img = mixc(img, col("#c9c4a2"), sm((blades - 0.7) / 0.7) * 0.5)
    img = mixc(img, col("#6f6c55"), sm((-blades - 0.9) / 0.7) * 0.4)
    frost = sm((pn(rng, 2.5) - 0.2) / 0.8) * 0.55 + sm((pn(rng, 0.8) - 1.4) / 0.4) * 0.35
    img = mixc(img, col("#e6edf2"), np.clip(frost, 0, 0.8))
    return img


def t_w_frozen_earth(rng):
    n = pn(rng, 20) * 0.6 + pn(rng, 6) * 0.4
    img = paint("#9b8a76", n, 0.10)
    clod = sm((pn(rng, 1.4) - 0.8) / 0.5)
    img = mixc(img, col("#b9aa95"), clod * 0.4)
    img = mixc(img, col("#6e5f50"), sm((pn(rng, 3) - 0.9) / 0.5) * 0.35)
    frost = sm((pn(rng, 0.8) - 1.3) / 0.4) * 0.55 + sm((pn(rng, 9) - 0.6) / 0.6) * 0.22
    img = mixc(img, col("#e2e8ee"), np.clip(frost, 0, 0.75))
    return img


def t_w_ice(rng):
    n = pn(rng, 10) * 0.6 + pn(rng, 3.5) * 0.4
    img = paint("#a9cfe0", n, 0.05)
    img = mixc(img, col("#e3f1f8"), sm((pn(rng, 6, 12) - 0.4) / 0.8) * 0.5)
    cid, d1, d2, k = voronoi(rng, 5, 0.5)
    crack = sm(1.0 - (d2 - d1) / 1.6)
    img = mixc(img, col("#f4fafc"), crack * 0.55)
    img = mixc(img, col("#6f9bb5"), sm(1.0 - (d2 - d1) / 0.7) * 0.3)
    bub = sm((pn(rng, 1.1) - 2.0) / 0.3)
    img = mixc(img, col("#ffffff"), bub * 0.6)
    return img


def t_w_conifer(rng):
    """Dark conifer crowns with a dusting of snow on the lit side."""
    cid, d1, d2, k = voronoi(rng, 9, 0.45)
    tone = rng.random(k)[cid]
    base = mixc(col("#2b4233") + np.zeros((S, S, 3)), col("#3f5a45"), tone)
    crown = sm(d1 / 11.0)                                    # 0 at the crown centre, 1 in the gaps
    img = base * (1.1 - 0.45 * crown)[..., None]
    img = mixc(img, col("#1c2620"), crown * 0.5)
    img *= (1 + 0.12 * pn(rng, 0.9))[..., None]
    snow = sm((pn(rng, 3.5) - 0.2) / 0.7) * 0.55 * (1 - crown * 0.5) + sm((pn(rng, 0.8) - 1.5) / 0.4) * 0.1
    return mixc(img, col("#dfe8ee"), np.clip(snow, 0, 0.8))


def t_w_rock(rng):
    """Dark grey-blue rock face, snow only in a few crevices."""
    n = pn(rng, 14) * 0.5 + pn(rng, 4) * 0.5
    img = paint("#5f6670", n, 0.14)
    strata = pn(rng, 1.8, 14.0)
    img = mixc(img, col("#3d434c"), sm((strata - 0.3) / 0.8) * 0.5)
    img = mixc(img, col("#8d96a1"), sm((-strata - 0.8) / 0.7) * 0.35)
    img = mixc(img, col("#dfe8ee"), sm((pn(rng, 4) - 1.1) / 0.5) * 0.65)
    return img * (1 + 0.07 * pn(rng, 0.8))[..., None]


def t_w_scree(rng):
    n = pn(rng, 10) * 0.5 + pn(rng, 3) * 0.5
    img = paint("#8b8e92", n, 0.14)
    peb = sm((pn(rng, 0.9) - 1.0) / 0.5)
    img = mixc(img, col("#b9bcc0"), peb * 0.5)
    img = mixc(img, col("#4e5258"), sm((-pn(rng, 1.4) - 1.0) / 0.5) * 0.5)
    return mixc(img, col("#dfe8ee"), sm((pn(rng, 5) - 0.1) / 0.7) * 0.45)


def _snow_over(rng, img, amount, scale=12.0, soft=0.7):
    """Lay snow over `img`; amount ~ fraction covered (0.4 = patchy, 0.75 = mostly covered)."""
    cover = sm((pn(rng, scale) * 0.7 + pn(rng, scale / 3.0) * 0.3 + (amount * 3.0 - 1.5)) / soft)
    return mixc(img, _snow_base(rng, 0.03, 0.02), cover * 0.97)


def _roof_snow(rng, rows, per, amount, base_a, base_b, edge, round_bottom=0.0, tone_k=0.3):
    roof = _overlap(rng, rows, per, base_a, base_b, edge, tone_k=tone_k, round_bottom=round_bottom)
    return _snow_over(rng, roof, amount, 10.0, 0.5)


def t_w_roof_snow(rng):
    """Snow-covered roof: white / pale blue-grey with faint courses showing through."""
    cid, u, v, r = rows_pattern(rng, 16, 14, offsets=True)
    n = cid.max() + 1
    tone = rng.random(n)[cid]
    img = mixc(col("#f1f5f9") + np.zeros((S, S, 3)), col("#d5e0ec"), tone * 0.8)
    img *= (1 + 0.03 * pn(rng, 6))[..., None]
    img *= (1 + 0.16 * (0.5 - v) * 0.8)[..., None]
    img = mixc(img, col("#9fb0c4"), sm(1.0 - (1 - v) * (S / 16) / 2.2) * 0.35)
    return mixc(img, col("#ffffff"), sm((pn(rng, 3) - 0.6) / 0.6) * 0.35)


def t_w_roof_thatch(rng):
    """Thatch with snow lying on it (straw yellow shows at the edges of the drifts)."""
    return _snow_over(rng, t_thatch(rng), 0.6, 9.0, 0.45)


def t_w_roof_slate(rng):
    """Civic slate: dark slate with patchy snow."""
    return _roof_snow(rng, 16, 8, 0.4, "#3f4650", "#5d6874", "#161a20")


def t_w_roof_red(rng):
    """Inn / tavern: red tile, snow patched so the warm colour still reads."""
    r = _overlap(rng, 16, 8, "#9b4b34", "#bf6a45", "#3b1a12", tone_k=0.3, shade=0.35)
    return _snow_over(rng, r, 0.38, 9.0, 0.5)


def t_w_roof_timber(rng):
    """Mill / barn / shed: dark timber boards, snow in drifts along the boards."""
    pl = _planks(rng, 10, "#554b3f", "#74664f", grain=0.18, gap="#1e1812")
    return _snow_over(rng, pl, 0.45, 8.0, 0.55)


def t_w_cobble(rng):
    """Cobbles showing through trampled snow (snow packed in the joints and on some stone tops)."""
    cb = t_cobble(rng)
    cid, d1, d2, k = voronoi(rng, 12, 0.38)
    joint = 1.0 - sm((d2 - d1) / 4.5)
    cover = np.clip(joint * 0.95 + sm((pn(rng, 6) - 0.3) / 0.6) * 0.45, 0, 0.92)
    sn = _snow_base(rng, 0.03, 0.02) * 0.93
    return mixc(cb * 0.97, sn, cover)


def t_w_slush(rng):
    """Trampled snow / slush on the main streets: grey-white with brown wheel-track streaks."""
    n = pn(rng, 14) * 0.6 + pn(rng, 4) * 0.4
    img = mixc(col("#dfe3e7") + np.zeros((S, S, 3)), col("#aeb2b6"), sm(0.5 - n * 0.45))
    streak = pn(rng, 1.6, 12.0)
    img = mixc(img, col("#8f8579"), sm((streak - 0.5) / 0.6) * 0.45)
    img = mixc(img, col("#f4f7fa"), sm((pn(rng, 3) - 0.8) / 0.6) * 0.45)
    img = mixc(img, col("#6f685f"), sm((pn(rng, 0.9) - 1.7) / 0.35) * 0.4)
    return img * (1 + 0.05 * pn(rng, 0.8))[..., None]


def t_w_packed(rng):
    """Packed white lane: clean snow with faint blue ruts."""
    img = _snow_base(rng, 0.03, 0.02) * 0.97
    ruts = pn(rng, 2.2, 14.0)
    return mixc(img, col("#a9bad0"), sm((ruts - 0.6) / 0.7) * 0.35)


def t_w_alley(rng):
    n = pn(rng, 10) * 0.6 + pn(rng, 3) * 0.4
    img = mixc(col("#bdbfc0") + np.zeros((S, S, 3)), col("#8f8c86"), sm(0.5 - n * 0.5))
    img = mixc(img, col("#eef2f6"), sm((pn(rng, 3) - 0.5) / 0.6) * 0.4)
    return img * (1 + 0.05 * pn(rng, 0.8))[..., None]


def t_w_plank(rng):
    pl = _planks(rng, 8, "#6f5a42", "#8d7656")
    cover = sm((pn(rng, 3, 12) - 0.1) / 0.6) * 0.55
    return mixc(pl, _snow_base(rng, 0.03, 0.02) * 0.95, cover)


def t_w_furrow(rng):
    """Snowy ploughland: white with the furrow lines in blue-grey shadow, dark soil peeking."""
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    ph = 2 * np.pi * yy * 16 / S + pn(rng, 20, 20) * 0.5
    prof = 0.5 + 0.5 * np.sin(ph)
    img = mixc(col("#aebfd2") + np.zeros((S, S, 3)), col("#f3f7fa"), sm(prof * 1.2))
    soil = sm((pn(rng, 1.3) - 1.3) / 0.4) * sm(1.0 - prof * 1.4)
    img = mixc(img, col("#6d5c4b"), soil * 0.6)
    img *= (1 + 0.04 * pn(rng, 0.8) + 0.03 * pn(rng, 10))[..., None]
    return img


def t_w_plough(rng):
    """Frozen ploughed earth: pale brown ridges with frost."""
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    ph = 2 * np.pi * yy * 14 / S + pn(rng, 20, 20) * 0.6
    prof = 0.5 + 0.5 * np.sin(ph)
    img = mixc(col("#7d6b58") + np.zeros((S, S, 3)), col("#b2a18b"), prof)
    img = mixc(img, col("#e3e9ee"), sm((pn(rng, 0.9) - 1.0) / 0.5) * 0.55 * prof)
    img = mixc(img, col("#eef2f6"), sm((pn(rng, 8) - 0.5) / 0.6) * 0.3)
    img *= (1 + 0.07 * pn(rng, 0.8))[..., None]
    return img


def t_w_stubble(rng):
    yy = np.arange(S)[:, None] + np.zeros((1, S))
    prof = 0.5 + 0.5 * np.sin(2 * np.pi * yy * 20 / S + pn(rng, 20, 20) * 0.4)
    img = mixc(col("#b5a77f") + np.zeros((S, S, 3)), col("#d6c9a2"), prof)
    img = mixc(img, col("#eef2f6"), sm((pn(rng, 6) - 0.2) / 0.7) * 0.5)
    img *= (1 + 0.10 * pn(rng, 0.7, 2.2))[..., None]
    return img


def t_w_pasture(rng):
    n = pn(rng, 16) * 0.55 + pn(rng, 5) * 0.45
    img = paint("#b4b08f", n, 0.10)
    img = mixc(img, col("#ecf1f5"), sm((pn(rng, 5) - 0.0) / 0.6) * 0.65)
    tuft = sm((pn(rng, 0.9) - 1.5) / 0.35)
    img = mixc(img, col("#8b8667"), tuft * 0.5)
    return img * (1 + 0.04 * pn(rng, 0.8))[..., None]


def t_w_water(rng):
    """Open winter water: dark steel blue with thin pale ripples."""
    n = pn(rng, 12) * 0.6 + pn(rng, 4) * 0.4
    img = paint("#3a6a8a", n, 0.09)
    a = pn(rng, 3.5, 7.0)
    crest = sm(((1.0 - np.abs(a)) - 0.93) / 0.07)
    img = mixc(img, col("#8fb2c6"), crest * 0.45)
    b = pn(rng, 8, 3.0)
    img = mixc(img, col("#1b3a52"), sm(((1.0 - np.abs(b)) - 0.95) / 0.05) * 0.4)
    return img


MAKERS = {
    "cobble": t_cobble, "gravel": t_gravel, "packed_earth": t_packed_earth, "mud": t_mud,
    "plank": t_plank, "timber_roof": t_timber_roof, "stone_slab": t_stone_slab,
    "slate": t_slate, "shingle": t_shingle, "red_tile": t_red_tile, "thatch": t_thatch,
    "tilled": t_tilled, "wheat": t_wheat, "crop_green": t_crop_green, "pasture": t_pasture, "water": t_water,
    "w_snow": t_w_snow, "w_frost_grass": t_w_frost_grass, "w_frozen_earth": t_w_frozen_earth, "w_ice": t_w_ice,
    "w_conifer": t_w_conifer, "w_rock": t_w_rock, "w_scree": t_w_scree,
    "w_roof_snow": t_w_roof_snow, "w_roof_thatch": t_w_roof_thatch, "w_roof_slate": t_w_roof_slate, "w_roof_red": t_w_roof_red,
    "w_roof_timber": t_w_roof_timber, "w_cobble": t_w_cobble, "w_slush": t_w_slush, "w_packed": t_w_packed, "w_alley": t_w_alley,
    "w_plank": t_w_plank, "w_furrow": t_w_furrow, "w_plough": t_w_plough, "w_stubble": t_w_stubble, "w_pasture": t_w_pasture,
    "w_water": t_w_water,
}


def seam_score(img):
    f = img.astype(float)
    wrap = np.abs(f[:, 0] - f[:, -1]).mean() + np.abs(f[0] - f[-1]).mean()
    inner = np.abs(f[:, 1:] - f[:, :-1]).mean() + np.abs(f[1:] - f[:-1]).mean()
    return wrap / (inner + 1e-9)


def make(out=TEX_DIR, only=None, check=False):
    from PIL import Image
    os.makedirs(out, exist_ok=True)
    names = []
    for k, (name, fn) in enumerate(MAKERS.items()):
        if only and name not in only:
            continue
        rng = np.random.default_rng(7000 + k)
        arr = to_img(fn(rng))
        Image.fromarray(arr).save(os.path.join(out, name + ".png"))
        names.append(name)
        if check:
            print(f"  {name:13s} mean {arr.reshape(-1, 3).mean(0).round(0)}  seam score {seam_score(arr):.2f}")
    return names


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=TEX_DIR)
    ap.add_argument("--only")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    print("textures:", ", ".join(make(a.out, set(a.only.split(",")) if a.only else None, a.check)))
