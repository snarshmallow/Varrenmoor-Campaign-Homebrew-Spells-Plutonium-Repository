"""Checks for terrain_smooth.py and the stair-step fix (run: python illustrator/generators/test_terrain_smooth.py)."""
import copy
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain  # noqa: E402
import terrain_smooth as TS  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SPEC = json.load(open(os.path.join(REPO, "world", "bridgehollow", "terrain_spec.json"), encoding="utf-8"))


def staircase():
    y, x = np.mgrid[0:150, 0:240] * 10.0
    ramp = 0.9 * y + 40 * np.sin(x / 300.0)
    return (np.floor(ramp / 26.0) * 26.0 + 600).astype(np.float64)


def test_metric_flags_stairs_and_passes_smooth():
    st = TS.terrace_metrics(staircase(), 10)
    assert not st["terrace_ok"], st
    y, x = np.mgrid[0:150, 0:240] * 10.0
    sm = TS.terrace_metrics(600 + 0.9 * y + 40 * np.sin(x / 300.0), 10)
    assert sm["terrace_ok"], sm
    print("ok metric", round(st["slope_jump_p999"], 2), round(sm["slope_jump_p999"], 2))


def test_finish_reduces_stairs_keeps_slope_and_extrema():
    h = staircase()
    f = TS.finish(h, 10, {"cliff_noise_ft": 0}).astype(float)
    a, b = TS.terrace_metrics(h, 10), TS.terrace_metrics(f, 10)
    assert b["steep_d2_p99_ft"] < a["steep_d2_p99_ft"] * 0.8, (a, b)
    assert abs(f.max() - h.max()) < 1e-3 and abs(f.min() - h.min()) < 1e-3
    gy, _ = np.gradient(f, 10)
    assert 0.6 < np.median(gy[20:-20]) < 1.2, "cliff must stay steep"
    print("ok finish", round(a["steep_d2_p99_ft"], 1), "->", round(b["steep_d2_p99_ft"], 1))


def test_bridgehollow_terrain_has_no_stair_steps_and_keeps_spec():
    h, meta = terrain.generate(copy.deepcopy(SPEC))
    m = TS.terrace_metrics(h, meta["cell_ft"])
    assert m["terrace_ok"], m
    assert h.dtype == np.float32
    assert 611 < h.min() < 613 and 1070 < h.max() < 1072.5, (h.min(), h.max())
    assert abs((h.max() - h.min()) - 459) < 3
    print("ok bridgehollow", {k: round(v, 3) for k, v in m.items() if isinstance(v, float)})


def test_no_far_field_creases_after_river_enforcement():
    h, meta = terrain.generate(copy.deepcopy(SPEC))
    d2 = np.abs(h[2:, 1:-1] - 2 * h[1:-1, 1:-1] + h[:-2, 1:-1])
    assert np.percentile(d2, 99.9) < 10, np.percentile(d2, 99.9)   # v6: 56 ft


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("all ok")
