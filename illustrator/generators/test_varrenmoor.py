"""Tests for the Varrenmoor additions (python test_varrenmoor.py): the `varrenmoor` town style (dirt roads, grass plazas, no paving), the two building style
presets, and the map calibration helpers of varrenmoor_build.py (feet <-> map pixels round trip). Does not need Illustrator, Foundry or a built place."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import building_styles as bs  # noqa: E402
import varrenmoor_build as vb  # noqa: E402

PRESETS = os.path.join(HERE, "..", "presets")


class TownStyle(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(PRESETS, "town_styles", "varrenmoor.json"), encoding="utf-8") as f:
            self.st = json.load(f)

    def test_no_paving(self):
        bad = {"cobble", "w_cobble", "stone_slab", "gravel", "slate"}
        streets = self.st["types"]["streets"]
        for k in ("road", "street", "lane", "alley"):
            self.assertNotIn(streets[k]["texture"], bad, k)
            self.assertEqual(streets[k]["texture"], "dirt")
        self.assertEqual(streets["bridge"]["texture"], "plank")

    def test_plaza_is_grass(self):
        self.assertEqual(self.st["types"]["plazas"]["default"]["texture"], "grass")

    def test_textures_exist(self):
        for t in ("dirt", "grass", "plank"):
            self.assertTrue(os.path.exists(os.path.join(PRESETS, "textures", t + ".png")), t)


class Styles(unittest.TestCase):
    def test_presets_registered(self):
        have = bs.load_presets()
        for sid in ("moorland_cottage", "long_timber_hall"):
            self.assertIn(sid, have)
            p = have[sid]
            self.assertEqual(p["id"], sid)
            self.assertTrue(p["preview"].endswith(sid + ".png"))
            self.assertTrue(p["kinds"])

    def test_every_build_style_exists(self):
        have = set(bs.load_presets())
        for bd in vb.B:
            self.assertIn(bd["style"], have, bd["id"])


class Calibration(unittest.TestCase):
    def test_scale_bar(self):
        self.assertAlmostEqual(1000.0 / 130.0, vb.S, 1)       # map scale bar: 1000 ft = 130 px

    def test_round_trip(self):
        for px, py in ((0, 160), (492, 500), (1100, 960)):
            x, y = vb.ft(px, py)
            qx, qy = vb.px_of(x, y)
            self.assertAlmostEqual(px, qx, delta=0.01)
            self.assertAlmostEqual(py, qy, delta=0.01)

    def test_window(self):
        self.assertEqual(vb.ft(0, 160), [0.0, 0.0])
        self.assertAlmostEqual(vb.ft(1100, 960)[0], vb.W_FT, delta=3.0)
        self.assertAlmostEqual(vb.ft(1100, 960)[1], vb.H_FT, delta=3.0)

    def test_roads_unpaved(self):
        self.assertTrue(vb.ROADS)
        for sid, name, cls, wid, pts in vb.ROADS:
            self.assertIn(cls, ("road", "street", "lane", "alley"))
            self.assertGreaterEqual(len(pts), 2)


class KerbRule(unittest.TestCase):
    def test_dirt_has_no_kerb_by_default(self):
        import worldpack as wp
        roads = [{"id": "a", "surface": {"material": "mat_dirt"}}, {"id": "b", "surface": {"material": "mat_cobble"}}, {"id": "c", "surface": {"material": "mat_mud"}},
                 {"id": "d", "surface": {"material": "mat_gravel"}}, {"id": "e", "surface": {"material": "mat_dirt"}}]
        streets = [{"id": "e", "edit": {"kerb": True}}]
        out = wp.drop_unpaved_kerbs({"a", "b", "c", "d", "e"}, roads, streets)
        self.assertEqual(out, {"b", "e"})                  # paved keeps its kerb, an explicit kerb=true on a dirt road is honoured


if __name__ == "__main__":
    unittest.main()
