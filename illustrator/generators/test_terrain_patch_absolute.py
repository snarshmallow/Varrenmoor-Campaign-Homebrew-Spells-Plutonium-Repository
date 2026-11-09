"""Deterministic synthetic tests for terrain_patch absolute max/avg fitting (the 'mountain just smoothed' bug).
  python test_terrain_patch_absolute.py     (also collected by pytest)
Bug: the extreme was fitted over ALL nodes inside the polygon, so rugged ground already above max_height_ft near the
border (or a spatially varying base) drove the added relief to 0 and the avg was 'clamped': result = smoothed ground."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import terrain_patch as tp

CELL = 40.0
META = {"cell_ft": CELL}
POLY = [[2000, 1500], [4000, 1300], [5400, 2500], [5200, 4200], [3500, 5200], [1800, 4600], [1300, 3000]]


def ground(kind="flat"):
    ny, nx = 160, 180
    Y, X = np.mgrid[0:ny, 0:nx] * CELL
    rng = np.random.default_rng(5)
    n = np.zeros((ny, nx))
    from scipy import ndimage as ndi
    n = ndi.gaussian_filter(rng.standard_normal((ny, nx)), 6)
    n = n / np.abs(n).max()
    if kind == "flat":                      # ~650 ft with +-40 ft undulation
        return (650 + 40 * n).astype(np.float32)
    # valley-like: slopes 450..940 ft across the polygon, rugged (user's varrenmoor_base situation)
    return (450 + 490 * np.clip((X + Y * 0.3) / 7000.0, 0, 1) + 60 * n).astype(np.float32)


def run(h, **p):
    base = dict(terrain_type="mountain", max_height_ft=900, avg_height_ft=800, steepness=0.5, feather_ft=80,
                roughness=0.4, seed=1)
    base.update(p)
    return tp.apply_patch(h, META, POLY, base, return_info=True)


def _outside_unchanged(h, after):
    _, _, _, inside, sd = tp.polygon_fields(POLY, h.shape, CELL)
    assert np.array_equal(h[~inside], after[~inside])


def test_mountain_on_flat_ground_reaches_max_and_mean():
    h = ground("flat")
    after, info = run(h, avg_height_ft=780)
    assert not info["warnings"], info["warnings"]
    assert abs(info["peak_core_ft"] - 900) < 1.0
    assert abs(info["mean"] - 780) < 3.0
    assert info["max_rise_ft"] > 200 and info["mean_change_ft"] > 100
    _outside_unchanged(h, after)


def test_user_degenerate_case_is_fixed():
    h = ground("slope")
    _, _, _, inside, _ = tp.polygon_fields(POLY, h.shape, CELL)
    assert h[inside].max() > 900 * 0.97 and h[inside].mean() < 760      # ground already near/above the max
    after, info = run(h)
    assert info["A"] > 0.5, info["A"]                                   # was ~0 (patch collapsed)
    assert abs(info["mean"] - 800) < 3.0, info["mean"]
    assert 899 < info["peak_core_ft"] < 925          # crest at 900; smooth ground >900 elsewhere is reported, not fought
    assert any("still reaches" in x for x in info["warnings"])
    assert info["max_rise_ft"] > 150
    assert info["avg_range"][0] < 800 < info["avg_range"][1]
    _outside_unchanged(h, after)
    chk = tp.seam_check(h, after, META, POLY)
    assert chk["outside_max_change"] == 0


def test_feather_blend_is_exact_zero_at_edge_and_outside():
    h = ground("flat")
    after, _ = run(h, feather_ft=200)
    d = np.abs(after.astype(float) - h)
    _, _, _, inside, sd = tp.polygon_fields(POLY, h.shape, CELL)
    assert d[inside & (sd < 30)].max() < 8.0          # eases in from the border
    assert d[inside & (sd > 400)].max() > 100.0        # full effect in the core


def test_unreachable_avg_reports_range_and_needed_height():
    h = ground("flat")
    after, info = run(h, max_height_ft=700, avg_height_ft=800)
    w = " ".join(info["warnings"])
    assert "outside achievable range" in w and "needs max height >=" in w
    need = info["needed_ext"]
    assert need > 800
    _, info2 = run(h, max_height_ft=need + 2, avg_height_ft=800)
    assert abs(info2["mean"] - 800) < 4.0, info2["mean"]


def test_ignored_param_warns_and_depression_works():
    h = ground("flat")
    _, info = run(h, min_height_ft=600, avg_height_ft=780)
    assert any("min_height_ft is ignored" in x for x in info["warnings"])
    after, info = run(h, terrain_type="bowl", min_height_ft=500, max_height_ft=None, avg_height_ft=600)
    assert abs(info["min"] - 500) < 2.0 and abs(info["mean"] - 600) < 3.0, info
    assert info["max_drop_ft"] < -100


def test_deterministic():
    h = ground("slope")
    a, _ = run(h)
    b, _ = run(h)
    assert np.array_equal(a, b)


if __name__ == "__main__":
    fails = 0
    for k, f in sorted(globals().items()):
        if k.startswith("test_"):
            try:
                f(); print("ok  ", k)
            except AssertionError as e:
                fails += 1; print("FAIL", k, e)
    print("ALL OK" if not fails else "FAILURES")
    sys.exit(1 if fails else 0)
