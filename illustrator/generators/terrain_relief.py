"""Shared natural-relief building blocks for terrain_patch.py (mountain & co) and terrain_basemap.py (base terrain).

Pure numpy/scipy, deterministic for a given numpy Generator.

  band_noise(rng, shape, cell, wavelength_ft)   band-pass gaussian noise (FFT), std 1, energy only near that wavelength
  relief_field(...)                             multi-octave ridged/smooth fBm with domain warp and slope-damped detail
                                                (derivative-damped octaves give valley floors / smooth flanks, i.e. an
                                                'eroded' look); returns std-1, zero-mean field
  stream_erode(h, cell, iters, ...)             stream-power erosion on a D8 flow-accumulation graph + thermal creep
                                                (carves dendritic gullies; pure python accumulation loop, crop first)
"""
import numpy as np
from scipy import ndimage as ndi

_KCACHE = {}


def _kgrid(shape, cell):
    key = (shape, float(cell))
    k = _KCACHE.get(key)
    if k is None:
        ny, nx = shape
        fy = np.fft.fftfreq(ny, d=cell)[:, None]
        fx = np.fft.rfftfreq(nx, d=cell)[None, :]
        k = np.sqrt(fx * fx + fy * fy)
        if len(_KCACHE) > 3:
            _KCACHE.clear()
        _KCACHE[key] = k
    return k


def band_noise(rng, shape, cell, wavelength_ft):
    """Gaussian noise band-passed around `wavelength_ft` (peak at wavelength), normalised to std 1. Periodic."""
    ny, nx = shape
    w = rng.standard_normal(shape)
    F = np.fft.rfft2(w)
    ks = _kgrid(shape, cell) * max(float(wavelength_ft), 2.0 * cell)
    F *= ks * np.exp(-0.5 * ks * ks)
    n = np.fft.irfft2(F, s=shape)
    return n / (n.std() + 1e-12)


def _std01(f):
    f = f - f.mean()
    return f / (f.std() + 1e-12)


def warp(field, dx_cells, dy_cells):
    ny, nx = field.shape
    Y, X = np.mgrid[0:ny, 0:nx].astype(np.float64)
    return ndi.map_coordinates(field, [Y + dy_cells, X + dx_cells], order=1, mode="reflect")


def relief_field(rng, shape, cell, lam_max, lam_min=None, hurst=0.9, ridge_mix=0.7, warp_frac=0.35, damp=0.8,
                 octaves=9, weights=None, return_octaves=False):
    """Multi-scale relief with std 1.
    lam_max / lam_min: largest / smallest wavelength (ft); octave i has wavelength lam_max/2^i (>= max(lam_min, 4 cells)).
    hurst: amplitude of octave i = (1/2^i)**hurst   (1.0 => constant slope per scale, <1 rougher fine scales).
    ridge_mix 0..1: share of ridged (sharp crest) vs smooth noise in every octave.
    warp_frac: domain-warp displacement as a fraction of lam_max.
    damp: >0 reduces finer octaves where the accumulated surface is already steep (smooth flanks, detailed flats).
    weights: optional per-octave multipliers (list)."""
    lam_floor = max(float(lam_min or 0.0), 4.0 * cell)
    acc = np.zeros(shape)
    lam = float(lam_max)
    amp = 1.0
    gref = None
    octs = []
    i = 0
    if warp_frac > 0:
        wl = lam_max * 1.2
        wdx, wdy = band_noise(rng, shape, cell, wl), band_noise(rng, shape, cell, wl)
    while i < octaves and lam >= lam_floor:
        n = band_noise(rng, shape, cell, lam)
        if warp_frac > 0:       # bend each octave by a smooth shared field, displacement proportional to its wavelength
            k = 0.3 * warp_frac * lam / cell      # 1-sigma displacement gradient ~1.5*warp_frac (< 1 keeps the map fold-free)
            n = warp(n, wdx * k, wdy * k)
            n = n / (n.std() + 1e-12)
        if ridge_mix > 0:
            r = _std01(1.0 - np.abs(n) * 0.9)       # sharp crests along the zero set of n
            n = (1 - ridge_mix) * n + ridge_mix * r
            n = n / (n.std() + 1e-12)
        wgt = amp * (1.0 if weights is None or i >= len(weights) else weights[i])
        if damp > 0 and i > 0:
            gy, gx = np.gradient(acc, cell)
            g2 = gx * gx + gy * gy
            if gref is None:
                gref = float(g2.mean()) + 1e-18
            wgt = wgt / (1.0 + damp * g2 / gref)     # field (array) multiplier, ~1 on gentle ground
        o = wgt * n
        acc += o
        if return_octaves:
            octs.append((lam, float(np.std(o))))
        amp *= 0.5 ** hurst
        lam *= 0.5
        i += 1
        if i == 1 and damp > 0:
            gy, gx = np.gradient(acc, cell)
            gref = float((gx * gx + gy * gy).mean()) + 1e-18
    out = _std01(acc)
    return (out, octs) if return_octaves else out


# ------------------------------------------------------------------ erosion
_NB = ((-1, -1, 1.41421356), (-1, 0, 1.0), (-1, 1, 1.41421356), (0, -1, 1.0), (0, 1, 1.0),
       (1, -1, 1.41421356), (1, 0, 1.0), (1, 1, 1.41421356))


def _receivers(h):
    """D8 steepest-descent receiver index (flat) per node, -1 for pits / outlets (boundary handled by edge padding)."""
    ny, nx = h.shape
    best = np.zeros(h.shape)
    recv = np.full(h.shape, -1, dtype=np.int64)
    idx = np.arange(h.size).reshape(h.shape)
    P = np.pad(h, 1, mode="edge")
    PI = np.pad(idx, 1, mode="edge")
    for dy, dx, dist in _NB:
        nb = P[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
        ni = PI[1 + dy:1 + dy + ny, 1 + dx:1 + dx + nx]
        slope = (h - nb) / dist
        m = slope > best
        best = np.where(m, slope, best)
        recv = np.where(m, ni, recv)
    return recv, best


def flow_accumulation(h, recv):
    """Upslope node count per node (each node contributes 1), flow along `recv`."""
    order = np.argsort(-h, axis=None, kind="stable")
    acc = np.ones(h.size)
    r = recv.ravel()
    for i in order.tolist():
        j = r[i]
        if j >= 0 and j != i:
            acc[j] += acc[i]
    return acc.reshape(h.shape)


def thermal(h, cell, iters, talus=0.7, rate=0.4):
    h = h.copy()
    lim = talus * cell
    for _ in range(int(iters)):
        d = np.zeros_like(h)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nb = np.roll(h, (dy, dx), (0, 1))
            diff = h - nb
            m = diff > lim
            mv = np.where(m, (diff - lim) * rate * 0.25, 0.0)
            d -= mv
            d += np.roll(mv, (-dy, -dx), (0, 1))
        h += d
    return h


def stream_erode(h, cell, iters, strength=1.0, mask=None, talus=0.9, m_exp=0.5, a_ref_frac=0.15, hill_sigma=0.55):
    """Stream-power erosion (implicit, unconditionally stable): each iteration finds D8 receivers, accumulates upslope
    area A and relaxes every node toward its receiver, h_i <- (h_i + F_i h_r) / (1 + F_i) with F_i = strength*0.12*
    min(A_i/(a_ref_frac N),1)^m_exp * dist-normalised, processed downstream first. High-flow channels are cut deep, divides stay, which
    grows a dendritic drainage pattern out of smooth noise. A little thermal creep follows each pass. `mask` (0..1)
    limits the change to a region (outside mask == 0 the field is untouched)."""
    h0 = np.asarray(h, dtype=np.float64)
    h = h0.copy()
    iters = int(iters)
    if iters <= 0 or strength <= 0:
        return h
    m = None if mask is None else np.asarray(mask, float)
    for _ in range(iters):
        recv, _slope = _receivers(h)
        A = flow_accumulation(h, recv)
        F = strength * 0.5 * np.minimum(A / (a_ref_frac * A.size), 1.0) ** m_exp
        order = np.argsort(h, axis=None, kind="stable").tolist()      # downstream (low) first
        hv = h.ravel().tolist()
        r = recv.ravel().tolist()
        Fv = F.ravel().tolist()
        for i in order:
            j = r[i]
            if j >= 0 and j != i:
                f = Fv[i]
                hv[i] = (hv[i] + f * hv[j]) / (1.0 + f)
        h = np.array(hv).reshape(h.shape)
        h = ndi.gaussian_filter(h, hill_sigma, mode="nearest")     # hillslope diffusion: widens the 1-cell D8 trenches into valleys
        h = thermal(h, cell, 2, talus=talus, rate=0.35)
    if m is not None:
        h = h0 + (h - h0) * m
    return h
