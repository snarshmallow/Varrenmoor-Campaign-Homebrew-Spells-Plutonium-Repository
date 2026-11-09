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
        self.assertEqual(self.st["types"]["plazas"]["default"]["texture"], "moor_grass")

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

class MoorPalette(unittest.TestCase):
    """Ground tiles match the map palette (dark olive / brown), not the bright stock green."""

    def test_moor_tiles_not_bright_green(self):
        import numpy as np
        from PIL import Image
        tex = os.path.join(os.path.dirname(HERE), "presets", "textures") if "HERE" in globals() else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "presets", "textures")
        for n in ("moor_grass", "moor_pasture", "moor_crop_green", "moor_wheat", "moor_tilled", "moor_farmland", "moor_forest_floor"):
            m = np.asarray(Image.open(os.path.join(tex, n + ".png")).convert("RGB"), float).reshape(-1, 3).mean(0)
            self.assertLess(m[1] - m[0], 12, n)                  # stock grass is G-R = 43; the map is ~ -11..0
            self.assertLess(m.max(), 135, n)

    def test_style_uses_moor_tiles(self):
        txt = json.dumps(self.st if hasattr(self, "st") else json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "presets", "town_styles", "varrenmoor.json"))))
        for bad in ('"grass"', '"pasture"', '"crop_green"', '"tilled"'):
            self.assertNotIn('"texture": ' + bad, txt)


class TreeDensity(unittest.TestCase):
    def test_pine_boost_only_touches_pines(self):
        import varrenmoor_trees as vt
        mix = vt.mix_for(0, 0.8, False)                       # high ground: mostly pines
        m, fac = vt.boosted_mix(mix, 2.0)
        self.assertGreater(fac, 1.0)
        base = sum(x["weight"] for x in mix)
        # total density x pine share of the new mix = 2 x the old pine share; broadleaf share x total unchanged
        def share(mx, group, inv=False):
            t = sum(x["weight"] for x in mx)
            return sum(x["weight"] for x in mx if (x["species"] in vt.PINES) != inv) / t
        self.assertAlmostEqual(fac * share(m, vt.PINES), 2.0 * share(mix, vt.PINES), places=6)
        self.assertAlmostEqual(fac * share(m, vt.PINES, True), share(mix, vt.PINES, True), places=6)
        self.assertEqual(vt.boosted_mix(mix, 1.0), (mix, 1.0))
        self.assertEqual(vt.boosted_mix([{"species": "oak", "weight": 1}], 3.0)[1], 1.0)
        self.assertGreater(base, 0)

    def test_hills_denser_and_defaults(self):
        import varrenmoor_trees as vt
        self.assertEqual(vt.pine_multiplier(0.0, 1.0, 0.0), 1.0)                     # old scatter reproducible
        self.assertGreater(vt.DEFAULT_PINE_DENSITY, 1.0)
        self.assertGreater(vt.pine_multiplier(1.0), vt.pine_multiplier(0.0))
        self.assertAlmostEqual(vt.pine_multiplier(5.0), vt.pine_multiplier(1.0))     # clamped
        self.assertGreater(vt.DEFAULT_MAX_TREES, 0)


if __name__ == "__main__":
    unittest.main()
