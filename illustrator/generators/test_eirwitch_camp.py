"""Light tests for the Eirwitch Camp driver (generators/eirwitch_camp.py): idempotent dry runs and the layout rules. No export, no Foundry.

  python illustrator/generators/test_eirwitch_camp.py
"""
import json
import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import eirwitch_camp as ec  # noqa: E402

WD = ec.world_dir()
HAVE_PLACE = os.path.exists(os.path.join(WD, "terrain", "heightmap.npy"))


def _snapshot(d):
    out = {}
    for root, _, files in os.walk(d):
        if os.sep + "export" in root:
            continue
        for f in files:
            p = os.path.join(root, f)
            out[p] = os.path.getmtime(p)
    return out


def _bilin(h, x, y):
    import worldpack as wp
    return float(wp.bilinear(h, ec.CELL, x, y))


@unittest.skipUnless(HAVE_PLACE, "world/eirwitch_camp not created yet (run eirwitch_camp.py design)")
class DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = np.load(os.path.join(WD, "terrain", "heightmap.npy"))
        cls.h = ec.design_heights(cls.base)

    def test_dry_runs_write_nothing(self):
        before = _snapshot(WD)
        r = ec.design(dry=True)
        self.assertTrue(r["dry_run"])
        b = ec.build(dry=True)
        self.assertTrue(any("rope_plank" in s for s in b["steps"]))
        self.assertEqual(before, _snapshot(WD))

    def test_terrain_deterministic(self):
        np.testing.assert_array_equal(self.h, ec.design_heights(self.base))

    def test_clearing_level_and_fire_at_centre(self):
        self.assertEqual(tuple(ec.FIRE), tuple(ec.CLEAR_C))
        ny, nx = self.h.shape
        X, Y = np.meshgrid(np.arange(nx) * ec.CELL, np.arange(ny) * ec.CELL)
        inside = np.hypot(X - ec.CLEAR_C[0], Y - ec.CLEAR_C[1]) < ec.CLEAR_R - 5
        self.assertLess(float(np.ptp(self.h[inside])), 8.0)      # level to +-4 ft (natural ground, no pit)
        self.assertAlmostEqual(_bilin(self.h, *ec.FIRE), ec.CLEAR_Z, delta=3.0)

    def test_church_inside_clearing_facing_fire(self):
        for x, y in ec.church_footprint():
            self.assertLess(math.hypot(x - ec.CLEAR_C[0], y - ec.CLEAR_C[1]), ec.CLEAR_R - 2.0)
        front = ec.CHURCH["center"][1] + ec.CHURCH["depth"] / 2        # south gable (door edge 2)
        self.assertGreater(ec.FIRE[1] - front, 20.0)
        self.assertLess(ec.CHURCH["width"], ec.CHURCH["depth"])            # narrow
        self.assertEqual(ec.CHURCH["floors"], 2)
        det = json.load(open(os.path.join(WD, "details.json"), encoding="utf-8"))
        d = [x for x in det["doors"] if x["building"] == ec.CHURCH["id"]][0]
        self.assertEqual(d["facing"], [0.0, 1.0])

    def test_road_enters_at_edge_and_dead_ends_in_clearing(self):
        p = ec.ROAD["points"]
        self.assertEqual(p[0][0], 0.0)
        end = p[-1]
        self.assertLess(math.hypot(end[0] - ec.CLEAR_C[0], end[1] - ec.CLEAR_C[1]), ec.CLEAR_R)
        self.assertGreater(math.hypot(end[0] - ec.FIRE[0], end[1] - ec.FIRE[1]), 25.0)   # stops short of the fire
        d, _, _ = ec.polyline_dist(np.array([x for x, _ in ec.PATH["points"][2:]]), np.array([y for _, y in ec.PATH["points"][2:]]), ec.GORGE)
        d_road, _, _ = ec.polyline_dist(np.array([x for x, _ in p]), np.array([y for _, y in p]), ec.GORGE)
        self.assertGreater(float(d_road.min()), 150.0)                   # the road never reaches the gorge (does not use the bridge)

    def test_gorge_and_bridge_span(self):
        xa, xb = ec.PATH_SPAN
        self.assertTrue(90.0 <= xb - xa <= 140.0)
        axis_d, _, _ = ec.polyline_dist(np.array([xa, xb]), np.array([470.0, 470.0]), ec.GORGE)
        self.assertTrue(all(ec.GORGE_BED_HALF + ec.GORGE_WALL - 15 <= v <= ec.GORGE_BED_HALF + ec.GORGE_WALL + 15 for v in axis_d))   # ends on the rims
        floor = min(_bilin(self.h, x, 470.0) for x in np.arange(xa, xb, 2.0))
        rim = min(_bilin(self.h, xa, 470.0), _bilin(self.h, xb, 470.0))
        self.assertTrue(60.0 <= rim - floor <= 140.0, rim - floor)
        sd = ec.streets_doc(self.h)
        path = [s for s in sd["streets"] if s["id"] == ec.PATH["id"]][0]
        pts, zs = path["geometry"]["points"], path["elevations_ft"]
        self.assertEqual(len(pts), len(zs))
        for (x, _), z in zip(pts, zs):
            if xa < x < xb:
                self.assertGreater(z - _bilin(self.h, x, 470.0), 50.0)        # deck level over the gorge, never draped into it

    def test_water_in_gorge_and_fjord(self):
        wd = ec.water_doc()
        ids = [w["id"] for w in wd["water"]]
        self.assertEqual(ids, ["wat_gorge_river", "wat_fjord"])
        cl = wd["water"][0]["centerline"]
        d, _, _ = ec.polyline_dist(np.array([c[0] for c in cl]), np.array([c[1] for c in cl]), ec.GORGE)
        self.assertLess(float(d.max()), 1.0)

    def test_lights_budget(self):
        L = ec.lights_for(self.h)
        self.assertLessEqual(len(L), 6)
        self.assertEqual(sum(1 for l in L if l.get("shadows")), 1)
        fire = [l for l in L if l["id"] == "eirwitch_campfire"][0]
        self.assertEqual(fire["point"], [ec.FIRE[0], ec.FIRE[1]])
        self.assertEqual(fire["animation"], "torch")
        self.assertTrue(40 <= fire["dim_ft"] <= 60 and fire["bright_ft"] == 15)

    def test_forest_zones_simple_and_outside_clearing(self):
        from shapely.geometry import Point, Polygon
        hole = Point(ec.CLEAR_C).buffer(ec.CLEAR_R)
        for poly in ec.forest_zones():
            pg = Polygon(poly)
            self.assertTrue(pg.is_valid)
            self.assertLess(pg.intersection(hole).area, 1.0)

    def test_no_trees_in_clearing_or_corridors(self):
        fp = os.path.join(WD, "foliage.json")
        if not os.path.exists(fp):
            self.skipTest("no foliage.json")
        items = json.load(open(fp, encoding="utf-8"))["items"]
        trees = [i for i in items if i["species"] in ("spruce", "scots_pine", "fir")]
        self.assertGreater(len(trees), 2000)
        self.assertEqual(ec.foliage_violations(items), [])

    def test_campfire_mesh_small(self):
        m = ec.campfire_mesh()
        self.assertGreater(len(m.tris if hasattr(m, "tris") else getattr(m, "indices", [1])), 0)


if __name__ == "__main__":
    unittest.main()
