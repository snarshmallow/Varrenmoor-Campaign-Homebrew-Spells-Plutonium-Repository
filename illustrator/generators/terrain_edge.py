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
