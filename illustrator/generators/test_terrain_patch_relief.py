"""Synthetic tests for the natural-relief mountain patch (terrain_patch.py + terrain_relief.py).
  python test_terrain_patch_relief.py     (also collected by pytest; ~30 s)
Checks: multi-scale relief spectrum (energy at ~1500 / 500 / 150 ft), roughness 0 smooth vs 1 rough, relief scales detail,
seed determinism, seam-free border / outside bit-identical, Max/Avg still exact, stream erosion param, every raise type."""
import os, sys
import numpy as np
from scipy import ndimage as ndi
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_patch as tp
import terrain_relief as TR

CELL = 25.0
META = {"cell_ft": CELL}
# ~5000 ft wide 9-point lasso
POLY = [[1500, 1200], [3200, 900], [5000, 1500], [5600, 3200], [5200, 5000], [3500, 5600], [1800, 5200], [1000, 3400], [1100, 2000]]
SHAPE = (300, 300)


def ground():
    Y, X = np.mgrid[0:SHAPE[0], 0:SHAPE[1]] * CELL
    return (600 + 20 * np.sin(X / 2300.0) + 15 * np.cos(Y / 1900.0)).astype(np.float32)


def run(**p):
    base = dict(terrain_type="mountain", max_height_ft=1500, avg_height_ft=1000, steepness=0.5, feather_ft=250,
                roughness=0.4, seed=1)
    base.update(p)
    return tp.apply_patch(ground(), META, POLY, base, return_info=True)


def band_std(h, inside, lam_hi, lam_lo):
    """std of the difference-of-gaussians band between wavelengths lam_hi (coarser) and lam_lo (finer), inside the patch core."""
    sg = lambda lam: lam / (2 * np.pi) / CELL * 1.3
    b = ndi.gaussian_filter(h.astype(float), sg(lam_lo)) - ndi.gaussian_filter(h.astype(float), sg(lam_hi))
    return float(b[inside].std())


def core():
    _, _, _, inside, sd = tp.polygon_fields(POLY, SHAPE, CELL)
    return inside & (sd > 300)


def test_spectrum_has_energy_at_several_scales():
    h, info = run()
    c = core()
    s = [band_std(h, c, 3000, 900), band_std(h, c, 900, 330), band_std(h, c, 330, 100)]
    print("  band std (ft) 1500/500/150:", [round(x, 1) for x in s])
    assert all(x > 4.0 for x in s), s                       # real relief at every scale, not one noise wavelength
    assert s[2] > 0.04 * s[0], s                             # fine scales are not a rounding error next to the coarse ones
    assert info["max"] > 1499.0 and abs(info["mean"] - 1000) < 5


def test_roughness_zero_is_smooth_and_one_is_rougher():
    c = core()
    fine = lambda r: band_std(run(roughness=r)[0], c, 260, 90)
    f0, f4, f1 = fine(0.0), fine(0.4), fine(1.0)
    print("  fine-band std rough 0/0.4/1:", round(f0, 2), round(f4, 2), round(f1, 2))
    assert f0 < 0.25 * f1 and f0 < f4 < f1
    # also the slope: rougher = larger local gradient
    g = lambda r: float(np.abs(np.diff(run(roughness=r)[0], axis=1))[c[:, 1:]].mean())
    assert g(0.0) < g(1.0)


def test_detail_scales_with_relief():
    c = core()
    lo = band_std(run(max_height_ft=900, avg_height_ft=700)[0], c, 900, 100)
    hi = band_std(run(max_height_ft=2100, avg_height_ft=1300)[0], c, 900, 100)
    print("  detail band std relief 300 / 1500:", round(lo, 1), round(hi, 1))
    assert hi > 2.5 * lo


def test_seed_determinism():
    a, b = run(seed=4)[0], run(seed=4)[0]
    assert np.array_equal(a, b)
    assert not np.array_equal(a, run(seed=5)[0])


def test_seam_free_and_outside_unchanged():
    g = ground()
    h, _ = run()
    chk = tp.seam_check(g, h, META, POLY)
    assert chk["outside_max_change"] == 0.0
    assert chk["dgrad_ratio"] < 0.05 or chk["boundary_dgrad"] < 0.05, chk
    _, _, _, inside, _ = tp.polygon_fields(POLY, SHAPE, CELL)
    assert np.array_equal(g[~inside], h[~inside])


def test_max_and_avg_exact_for_typical_and_plateau_cases():
    for mx, av in ((1500, 1000), (1300, 900), (1500, 1200)):
        h, info = run(max_height_ft=mx, avg_height_ft=av)
        assert abs(info["max"] - mx) < 1.5 and abs(info["mean"] - av) < 5, (mx, av, info["max"], info["mean"])


def test_erosion_parameter_changes_the_shape():
    a, b = run(erosion=0)[0], run(erosion=14)[0]
    assert not np.array_equal(a, b)
    _, _, _, inside, _ = tp.polygon_fields(POLY, SHAPE, CELL)
    assert np.array_equal(b[~inside], ground()[~inside])


def test_all_raise_types_hit_the_max():
    for t in sorted(tp.RAISE):
        h, info = run(terrain_type=t, max_height_ft=1400, avg_height_ft=950)
        assert abs(info["max"] - 1400) < 2 or info["warnings"], (t, info["max"])
        assert np.isfinite(h).all()


def test_relief_field_lib():
    f = TR.relief_field(np.random.default_rng(1), (128, 128), 20.0, 1200.0)
    assert abs(float(f.std()) - 1.0) < 1e-6 and abs(float(f.mean())) < 1e-6
    e = TR.stream_erode(f * 100, 20.0, 3)
    assert e.shape == f.shape and np.isfinite(e).all()
    m = np.zeros(f.shape)
    m[40:80, 40:80] = 1
    e2 = TR.stream_erode(f * 100, 20.0, 3, mask=m)
    assert np.array_equal(e2[m == 0], (f * 100)[m == 0])


if __name__ == "__main__":
    n = 0
    for k, v in sorted(globals().items()):
        if k.startswith("test_") and callable(v):
            v()
            print("ok  ", k)
            n += 1
    print("ALL OK (%d)" % n)
