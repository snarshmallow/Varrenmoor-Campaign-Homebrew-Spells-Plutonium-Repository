"""Tile-repeat check: sample a texture over a large flat area at 150 dpi / 100 ft-per-in, compute the normalised
autocorrelation and report the highest off-origin peak at lags near the tile period. Run: python generators/test_shading_tiling.py"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shading as S


def peak(img, lo):
    g = img.mean(-1); g = g - g.mean()
    F = np.fft.rfft2(g); ac = np.fft.irfft2(F * np.conj(F), s=g.shape)
    ac /= ac[0, 0]
    ys = np.minimum(np.arange(g.shape[0]), g.shape[0] - np.arange(g.shape[0]))[:, None]
    xs = np.minimum(np.arange(g.shape[1]), g.shape[1] - np.arange(g.shape[1]))[None, :]
    return ac[np.hypot(ys, xs) >= lo].max()   # ignore the central lobe (lags < lo px)


def main():
    ppf, tile_ft = 1.5, 40.0
    tile = np.asarray(__import__("PIL.Image", fromlist=["x"]).open(os.path.join(S.TEX_DIR, "grass.png")).convert("RGB"), float)
    X, Y = np.meshgrid((np.arange(1500) + .5) / ppf, (np.arange(1000) + .5) / ppf)
    old = S.sample_tile(tile, X, Y, tile_ft)
    new = S.sample_tile_nt(tile, X, Y, tile_ft, ppf, 7)
    lo = tile_ft * ppf * 0.5
    po, pn = peak(old, lo), peak(new, lo)
    print(f"autocorrelation peak at lags >= {lo:.0f}px: old {po:.3f}, new {pn:.3f}")
    assert pn < 0.5 * po and pn < 0.15, "tiling still visible"
    print("OK")


if __name__ == "__main__":
    main()
