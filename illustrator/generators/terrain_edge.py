"""Terrain edge easing: a carved river bed / valley that runs off the tile must not end in a cliff at the map boundary.

`ease_carve_at_edge` lerps the carved heights back to the authored (natural bank) heights over the last `ease_ft` of the tile, so the terrain edge heights
are the natural bank level and the apron (padding_heightmap.Apron) continues from bank level instead of a 17 ft deep, 24 ft wide trench. The water surface keeps
its level and simply goes under the rising bed (a natural shoreline; no flat cut is visible from above). Only the cells the carve changed are touched,
the interior carve and everything done after it (road grading, bridge carving, building pads) are unchanged.
"""
import numpy as np

DEFAULT_EASE_FT = 100.0


def ease_carve_at_edge(h_carved, h_orig, cell, ease_ft=DEFAULT_EASE_FT):
    """h_carved, h_orig: (ny, nx) heights in ft on the same grid, cell in ft. -> h_carved with the carve faded out towards the tile boundary (exactly h_orig on the boundary)."""
    if not ease_ft or ease_ft <= 0:
        return h_carved
    ny, nx = h_carved.shape
    x = np.arange(nx) * cell
    y = np.arange(ny) * cell
    d = np.minimum(np.minimum(x[None, :], (nx - 1) * cell - x[None, :]), np.minimum(y[:, None], (ny - 1) * cell - y[:, None]))
    t = np.clip(d / float(ease_ft), 0.0, 1.0)
    w = t * t * t * (t * (6 * t - 15) + 10)                 # quintic: zero slope at the boundary and at ease_ft
    return (h_orig + (h_carved - h_orig) * w).astype(h_carved.dtype)


def soften_edge_albedo(img, size_ft, edge_ft=DEFAULT_EASE_FT, sigma_ft=25.0, border_ft=10.0):
    """Bank walls / rock wedges at the map boundary: the baked terrain colour paints a steep carved bank grey, but the apron (which eases the relief away beyond the
    boundary) continues as grass, so the grey wedge ends in a hard step at the seam. Within edge_ft of the boundary, non-grass (grey, low green dominance) pixels are
    replaced by the local grass colour (normalised convolution of the grass pixels), weight rising smoothly to 1 at the boundary. img uint8 (h, w, 3|4); size_ft = (W, H).
    Returns a new uint8 array; interior pixels are untouched."""
    from scipy import ndimage
    a = np.asarray(img)
    rgb = a[..., :3].astype(np.float32) / 255.0
    h, w = rgb.shape[:2]
    ppf = w / float(size_ft[0])
    gdom = rgb[..., 1] - np.maximum(rgb[..., 0] * 0.85, rgb[..., 2])               # grass: green clearly above red and blue
    ref = float(np.percentile(gdom, 70))
    if ref <= 0.02:
        return a.copy()                                                              # no green ground to borrow (rock / snow place): leave alone
    grass = np.clip((gdom - 0.35 * ref) / (0.45 * ref), 0, 1)
    x = (np.arange(w) + 0.5) / ppf
    y = (np.arange(h) + 0.5) / (h / float(size_ft[1]))
    d = np.minimum(np.minimum(x[None, :], size_ft[0] - x[None, :]), np.minimum(y[:, None], size_ft[1] - y[:, None]))
    t = np.clip(1.0 - d / max(edge_ft, 1e-6), 0, 1)
    t = t * t * (3 - 2 * t)
    s = max(sigma_ft * ppf, 0.5)
    num = np.stack([ndimage.gaussian_filter(rgb[..., c] * grass, s) for c in range(3)], -1)
    den = ndimage.gaussian_filter(grass, s)[..., None]
    fill = num / np.maximum(den, 1e-4)
    ok = (den[..., 0] > 0.02)[..., None]
    fill = np.where(ok, fill, rgb)
    amt = (t * (1.0 - grass))[..., None]
    out = rgb * (1 - amt) + fill * amt
    # texture wrap: the terrain albedo is sampled with RepeatWrapping, so at the tile border (and at every coarser mip level) the filter blends the opposite edge's texels in,
    # which shows as a thin band of streaks along the edge (seen live on the Dyers east edge). Fade the outermost border_ft to ONE global grass colour so both sides match.
    if border_ft and border_ft > 0:
        gm = (rgb * grass[..., None]).sum((0, 1)) / max(float(grass.sum()), 1e-6)
        tb = np.clip(1.0 - d / border_ft, 0, 1)
        tb = (tb * tb * (3 - 2 * tb))[..., None]
        out = out * (1 - tb) + gm[None, None, :] * tb
    res = a.copy()
    res[..., :3] = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
    return res
