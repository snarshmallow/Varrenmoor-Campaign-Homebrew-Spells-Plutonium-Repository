"""Checks for town_area.py (run: python illustrator/generators/test_town_area.py). Uses the Bridgehollow terrain."""
import json
import os
import sys

import numpy as np
from shapely.geometry import Point, Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import town_area as ta  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
TP = json.load(open(os.path.join(REPO, "world", "bridgehollow", "town_params.json"), encoding="utf-8"))
H, META, WATER = ta.load_inputs("bridgehollow", {})
P = dict({"seed": 1103, "slope_limit": 0.15, "target_area_ft2": None}, **{k: v for k, v in TP.get("area_auto", {}).items() if k != "centre"})
CENTRE = TP["ring_spec"]["centre"]
RINGS = TP["ring_spec"]["rings"]


def run(**kw):
    return ta.build(H, META, WATER, dict(P, **kw), CENTRE, None, RINGS)


def test_deterministic():
    a, b = run(), run()
    assert a["area_ft"] == b["area_ft"] and a["rings_ft"] == b["rings_ft"]
    assert run(seed=5)["area_ft"] != a["area_ft"]
    print("ok deterministic")


def test_valid_smooth_within_slope():
    r = run()
    poly = Polygon(r["area_ft"])
    assert poly.is_valid and poly.contains(Point(CENTRE)), "area must be a valid polygon holding the centre"
    st = r["stats"]
    assert st["max_turn_deg"] < 45, f"corner of {st['max_turn_deg']} deg: boundary is not smooth"
    angs = ta.turn_angles(r["area_ft"])
    assert not any(70 < a < 110 for a in angs), "near-right angle in the outline"
    assert st["frac_over_limit"] < 0.08, f"{st['frac_over_limit']:.1%} of the area is steeper than the limit"
    assert st["compactness"] > 0.4, "outline is too spiky"
    # no straight runs: any 4 consecutive vertices must bend by a visible amount somewhere in every 5
    pts = np.array(r["area_ft"])
    n = len(pts)
    straight = 0
    for i in range(n):
        a, b = pts[i], pts[(i + 4) % n]
        mid = pts[(i + 2) % n]
        dev = abs((b - a)[0] * (mid - a)[1] - (b - a)[1] * (mid - a)[0]) / max(np.linalg.norm(b - a), 1e-6)
        straight += dev < 0.5
    assert straight < 0.1 * n, "too many straight runs"
    print(f"ok smooth/slope: {st['vertices']} vertices, max turn {st['max_turn_deg']} deg, {st['frac_over_limit']:.1%} over limit")


def test_slope_limit_controls_extent():
    lo, hi = run(slope_limit=0.08)["stats"]["area_ft2"], run(slope_limit=0.17)["stats"]["area_ft2"]
    assert lo < hi, (lo, hi)
    t = run(target_area_ft2=300000)["stats"]["area_ft2"]
    assert 200000 < t < 400000, t
    print(f"ok slope limit {lo} < {hi}; target 300000 -> {t}")


def test_rings_nested_in_area():
    r = run()
    area = Polygon(r["area_ft"]).buffer(1)
    a, c = Polygon(r["rings_ft"]["authority"]).buffer(0), Polygon(r["rings_ft"]["commoner"]).buffer(0)
    assert c.difference(area).area < 0.002 * c.area and c.buffer(1).contains(a) and a.area < c.area < area.area
    print("ok rings nested")


def test_snap_pulls_lasso_onto_terrain():
    box = TP.get("_area_ft_v4_box") or [[640, 360], [1780, 360], [1780, 1300], [640, 1300]]
    r = ta.build(H, META, WATER, P, CENTRE, box)
    poly = Polygon(r["area_ft"])
    assert poly.is_valid and r["stats"]["frac_over_limit"] < 0.08
    assert r["stats"]["max_turn_deg"] < 45
    assert poly.area < Polygon(box).area * 0.8, "snap should drop the steep ground the rough lasso covered"
    print(f"ok snap: {Polygon(box).area:.0f} -> {poly.area:.0f} ft2")


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            v()
    print("all passed")
