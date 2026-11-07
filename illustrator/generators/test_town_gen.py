"""Checks for town_gen.py (run: python illustrator/generators/test_town_gen.py). Uses the Bridgehollow params."""
import copy
import glob
import json
import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import town_gen as tg  # noqa: E402
import terrain as tr  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PARAMS = os.path.join(REPO, "world", "bridgehollow", "town_params.json")


def model_of(g):
    streets, districts = g.to_model(), g.district_ents()
    return streets, districts, [b["e"] for b in g.buildings]


def test_deterministic():
    a = model_of(tg.generate(PARAMS, verbose=False))
    b = model_of(tg.generate(PARAMS, verbose=False))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True), "same seed must give identical output"
    c = model_of(tg.generate(PARAMS, {"seed": 7}, verbose=False))
    assert json.dumps(a, sort_keys=True) != json.dumps(c, sort_keys=True), "different seed must differ"
    print("ok deterministic")


def test_constraints_and_ids():
    g = tg.generate(PARAMS, verbose=False)
    streets, districts, blds = model_of(g)
    ids = [e["id"] for e in streets + districts + blds]
    assert len(ids) == len(set(ids)), "duplicate entity ids"
    wp = g.water.polygon
    for b in g.buildings:
        assert not b["poly"].intersects(wp), b["e"]["id"] + " in water"
        assert b["e"]["site_slope"] <= g.L["max_build_slope"] + 1e-9, b["e"]["id"] + " too steep"
        assert "elevation_ft" in b["e"]
    assert all("elevations_ft" in s and s["status"] == "proposed" for s in streets)
    banned = ("church", "gerald", "dunmore", "kell", "tobias", "wren")
    text = json.dumps([streets, districts, blds]).lower()
    assert not any(w in text for w in banned), "banned name present"
    assert sum(1 for s in streets if s["kind"] == "bridge") == 1, "expected exactly one bridge"
    print("ok constraints:", len(streets), "streets,", len(blds), "buildings")


def test_negative_elevation():
    h, meta = tr.load_heightmap("bridgehollow")
    h2 = (h - 700.0).astype(np.float32)               # whole bowl floor now between about -80 and 0 ft
    m2 = dict(meta, elev_min=float(h2.min()), elev_max=float(h2.max()), sea_level_ft=0.0)
    try:
        n_wet = len(tg.generate(PARAMS, verbose=False, heightmap=(h2, m2)).buildings)
    except SystemExit:
        n_wet = 0                                    # no dry route at all: everything is below the datum
    p = tg.load_params(PARAMS)
    p["limits"]["dry_basin_polys"] = [p["area_ft"]]
    p["_heightmap"] = (h2, m2)
    g2 = tg.TownGen(p, os.path.dirname(PARAMS), False).run()
    assert n_wet < len(g2.buildings) * 0.25, f"below-datum ground must not be built on ({n_wet} vs dry basin {len(g2.buildings)})"
    assert min(b["e"]["elevation_ft"] for b in g2.buildings) < 0, "negative elevations must be kept as is"
    print("ok negative elevation:", n_wet, "buildings below datum vs", len(g2.buildings), "in a declared dry basin")


def test_switchbacks():
    """Narrow corridor up a 30% slope: with a 6% grade cap the A* route must zig-zag (length >> straight line)."""
    h, meta = tr.load_heightmap("bridgehollow")
    p = tg.load_params(PARAMS)
    g = tg.TownGen(p, os.path.dirname(PARAMS), False)
    yy, xx = np.mgrid[0:g.ny, 0:g.nx]
    slope_h = (g.Y * 0.25).astype(float)                # +25 ft per 100 ft toward the south
    g.hroad = slope_h
    g.slope = np.full_like(slope_h, 0.25)
    g.wet[:] = False
    g.wet_river[:] = False
    g.area_mask[:] = True
    g.L["hard_slope"] = 1.0
    path = g.astar((1200, 200), (1200, 500), 0.08, 5.0)
    L = sum(np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path[:-1], path[1:]))
    assert L > 700, f"expected a long switchback route, got {L:.0f} ft for a 300 ft climb"
    gr = max(abs(g.hroad[int(b[1] / 10), int(b[0] / 10)] - g.hroad[int(a[1] / 10), int(a[0] / 10)]) /
             np.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path[:-1], path[1:]))
    assert gr <= 0.0801, gr
    print(f"ok switchbacks: {L:.0f} ft route for a 300 ft straight climb, max step grade {gr:.3f}")


def test_svg_valid():
    import render_world as rw
    out = os.path.join(REPO, "illustrator", "out", "_test_town.svg")
    rw.render(rw.load_place("bridgehollow"), "town", out, None)
    root = ET.parse(out).getroot()
    ids = [e.get("id") for e in root.iter() if e.get("id")]
    assert len(ids) == len(set(ids)), "duplicate SVG ids: " + str([i for i in ids if ids.count(i) > 1][:5])
    os.remove(out)
    print("ok svg ids unique:", len(ids))


if __name__ == "__main__":
    for t in (test_deterministic, test_constraints_and_ids, test_negative_elevation, test_switchbacks, test_svg_valid):
        t()
    print("all passed")
