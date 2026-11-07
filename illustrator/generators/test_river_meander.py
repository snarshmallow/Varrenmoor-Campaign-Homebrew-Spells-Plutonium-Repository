"""Checks for river_meander.py and the meandered Bridgehollow river (run: python illustrator/generators/test_river_meander.py)."""
import copy
import json
import os
import sys

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import river_meander as rm  # noqa: E402
import terrain  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
SPEC = json.load(open(os.path.join(REPO, "world", "bridgehollow", "terrain_spec.json"), encoding="utf-8"))
VALLEY = next(v for v in SPEC["valleys"] if v.get("river"))


def valley(preset, **kw):
    v = copy.deepcopy(VALLEY)
    v["meander"] = dict({"preset": preset}, **kw)
    return v


def test_sinuosity_ordering_and_deterministic():
    s = {p: rm.sinuosity(rm.river_geometry(valley(p))["centerline"])[0] for p in ("straight", "gentle", "lazy")}
    assert s["straight"] < s["gentle"] < s["lazy"], s
    assert 1.04 < s["gentle"] < 1.15 and s["lazy"] < 1.25, s
    assert rm.river_geometry(valley("gentle"))["centerline"] == rm.river_geometry(valley("gentle"))["centerline"]
    assert rm.river_geometry(valley("gentle", seed=5))["centerline"] != rm.river_geometry(valley("gentle"))["centerline"]
    print("ok sinuosity", {k: round(v, 3) for k, v in s.items()})


def test_ends_fixed_and_widths():
    for p in ("gentle", "lazy"):
        g = rm.river_geometry(valley(p))
        base = rm.river_geometry(valley("straight"))
        assert np.allclose(g["centerline"][0], base["centerline"][0], atol=0.5) and np.allclose(g["centerline"][-1], base["centerline"][-1], atol=0.5)
        w = np.array(g["widths"])
        assert w.min() > 25 and w.max() < 100 and w[:8].mean() < w[-8:].mean(), "gorge must be narrower than the floor"
    print("ok ends and widths")


def test_bed_monotone_downhill_in_generated_terrain():
    for p in ("gentle", "lazy"):
        spec = copy.deepcopy(SPEC)
        next(v for v in spec["valleys"] if v.get("river"))["meander"] = {"preset": p, "seed": 1103}
        h, meta = terrain.generate(spec)
        c = np.array(rm.river_geometry(next(v for v in spec["valleys"] if v.get("river")))["centerline"])
        c = c[(c[:, 1] >= 0) & (c[:, 1] <= 1500)]
        z = ndi.map_coordinates(h.astype(float), [c[:, 1] / 10, c[:, 0] / 10], order=1)
        assert np.diff(z).max() <= 0.05, f"{p}: river climbs {np.diff(z).max():.2f} ft"
        assert z[0] > 800 and z[-1] < 620, (z[0], z[-1])
    print("ok bed monotone, ~812 ft -> ~612 ft")


def test_world_water_matches_spec():
    w = json.load(open(os.path.join(REPO, "world", "bridgehollow", "water.json"), encoding="utf-8"))["water"][0]
    g = rm.river_geometry(VALLEY)
    assert w["centerline"] == g["centerline"], "water.json is stale: run python world/gen_bridgehollow.py"
    print("ok water.json matches the spec meander")


if __name__ == "__main__":
    test_sinuosity_ordering_and_deterministic()
    test_ends_fixed_and_widths()
    test_bed_monotone_downhill_in_generated_terrain()
    test_world_water_matches_spec()
    print("all passed")
