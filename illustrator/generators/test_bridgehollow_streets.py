"""Tests for bridgehollow_streets.py (light: no world pack export, no Foundry).  python -m pytest illustrator/generators/test_bridgehollow_streets.py"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridgehollow_streets as bs  # noqa: E402


def st(i, name, pts, kind="street", w=18.0):
    return {"id": i, "name": name, "kind": kind, "geometry": {"type": "polyline", "points": pts, "width_ft": w}}


class StreetGroups(unittest.TestCase):
    def test_alleys_skipped_numbered_joined_or_split(self):
        ss = [st("a", "Weavers Walk", [[0, 0], [100, 0]]), st("b", "Weavers Walk 2", [[100, 0], [200, 0]]),       # touches -> same street
              st("c", "Brook Lane", [[0, 0], [0, 100]]), st("d", "Brook Lane 2", [[0, 600], [0, 700]]),            # far -> own street, south
              st("e", "Tanners Row 2", [[500, 0], [600, 0]]), st("f", "Alley 9", [[0, 0], [5, 5]], "lane"),
              st("g", "Pilgrim Bridge", [[200, 0], [250, 0]], "bridge")]
        g = {x["key"]: x["ids"] for x in bs.street_groups(ss)}
        self.assertEqual(g["weavers_walk"], ["a", "b", "g"])
        self.assertEqual(g["brook_lane"], ["c"])
        self.assertEqual(g["brook_lane_south"], ["d"])
        self.assertEqual(g["tanners_row"], ["e"])
        self.assertFalse(any("alley" in k for k in g))

    def test_real_street_list(self):
        plan = bs.scene_plan()
        keys = [p["key"] for p in plan]
        for k in ("warden_street", "cooper_row", "market_square", "court_square", "pilgrim_road", "dyers_walk", "tanners_row", "cartwright_lane", "hedge_lane"):
            self.assertIn(k, keys)
        self.assertEqual(keys[0], "warden_street")
        self.assertEqual([k for k in dict.fromkeys(keys)][:5], bs.PRIORITY)
        pr = [p for p in plan if p["key"] == "pilgrim_road"]
        self.assertTrue(all("str_pilgrim_road_bridge" in p["ids"] for p in pr))
        for p in plan:
            self.assertLessEqual(p["size_ft"][0], bs.CAP_FT + 1)
            self.assertLessEqual(p["size_ft"][1], bs.CAP_FT + 1)
            self.assertTrue(p["scene_name"].startswith("Bridgehollow - ") and p["scene_name"].endswith(" (Winter)"))
            self.assertTrue(p["child"].startswith("bridgehollow__street_"))
        self.assertEqual(len({p["child"] for p in plan}), len(plan))


class Windows(unittest.TestCase):
    def test_short_street_one_window_with_buffer(self):
        from shapely.geometry import LineString
        r = bs.window_parts(LineString([(500, 500), (700, 500)]), 2400, 1500)
        self.assertEqual(r, [[380.0, 380.0, 820.0, 620.0]])

    def test_long_street_split_at_junction(self):
        from shapely.geometry import LineString
        g = LineString([(500, 300), (500, 1100)])
        r = bs.window_parts(g, 2400, 1500, junctions=[(500, 700)])
        self.assertEqual(len(r), 2)
        self.assertAlmostEqual(r[0][3], 700 + 120, delta=1)       # part 1 ends at the junction + buffer
        self.assertAlmostEqual(r[1][1], 700 - 120, delta=1)
        for x in r:
            self.assertLessEqual(x[3] - x[1], bs.CAP_FT)

    def test_clamped_to_place(self):
        self.assertEqual(bs._clamp_rect([-50, -10, 100, 2000], 300, 1500), [0.0, 670.0, 100.0, 1320.0])     # 650 ft round the centre, then into the place


class ExtractHelpers(unittest.TestCase):
    def test_winter_styles_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "buildings"))
            for i, s in enumerate(["bh_inner_house", "bh_inner_house_winter", None, "chapel"]):
                b = {"id": f"b{i}"}
                if s:
                    b["style"] = s
                json.dump(b, open(os.path.join(d, "buildings", f"b{i}.json"), "w"))
            pres = {"bh_inner_house": {}, "bh_inner_house_winter": {}, "chapel": {}}
            self.assertEqual(bs.winter_styles(d, pres), 1)
            self.assertEqual(bs.winter_styles(d, pres), 0)
            got = [json.load(open(os.path.join(d, "buildings", f"b{i}.json"))).get("style") for i in range(4)]
            self.assertEqual(got, ["bh_inner_house_winter", "bh_inner_house_winter", None, "chapel"])

    def test_copy_foliage_window_and_origin(self):
        with tempfile.TemporaryDirectory() as d:
            par, ch = os.path.join(d, "p"), os.path.join(d, "bridgehollow__street_x")
            os.makedirs(par)
            os.makedirs(ch)
            json.dump({"counters": {"z": 3}, "zones": [{"id": "z"}, {"id": "q"}], "items": [
                {"id": "fol_z_0001", "species": "spruce", "x": 150, "y": 150, "z": 600, "scale": 1, "rot": 0, "zone": "z", "src": "generated"},
                {"id": "fol_z_0002", "species": "spruce", "x": 900, "y": 150, "z": 600, "scale": 1, "rot": 0, "zone": "z", "src": "generated"}]},
                open(os.path.join(par, "foliage.json"), "w"))
            n = bs.copy_foliage(par, ch, [100, 100, 300, 300], [100, 100])
            self.assertEqual(n, 1)
            f = json.load(open(os.path.join(ch, "foliage.json")))
            self.assertEqual((f["items"][0]["x"], f["items"][0]["y"]), (50, 50))
            self.assertEqual([z["id"] for z in f["zones"]], ["z"])

    def test_region_current(self):
        p = {"rect": [1, 2, 3, 4]}
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(bs._region_current(d, p, None))
            json.dump({"region": {"kind": "rect", "rect": [1, 2, 3, 4]}, "parent_source": {"content_sha1": "abc"}}, open(os.path.join(d, "region.json"), "w"))
            self.assertTrue(bs._region_current(d, p, {"content_sha1": "abc"}))
            self.assertFalse(bs._region_current(d, p, {"content_sha1": "def"}))
            self.assertFalse(bs._region_current(d, {"rect": [1, 2, 3, 5]}, {"content_sha1": "abc"}))

    def test_dry_run_writes_nothing(self):
        plan = bs.select(bs.scene_plan(), "court_square")
        with tempfile.TemporaryDirectory() as d:
            r = bs.extract_one(plan[0], dry=True, out_root=d)
            self.assertTrue(r["dry_run"])
            self.assertGreater(r["buildings"], 0)
            self.assertEqual(os.listdir(d), [])

    def test_select(self):
        plan = bs.scene_plan()
        self.assertEqual({p["part_key"] for p in bs.select(plan, "warden_street")}, {"warden_street_part_1", "warden_street_part_2"})
        self.assertEqual(len(bs.select(plan, "every")), len(plan))
        self.assertEqual(sorted(p["part_key"] for p in bs.select(plan, "all")), sorted(bs.KEEP_SCENES))     # "all" = the districts that are kept, not every road
        with self.assertRaises(SystemExit):
            bs.select(plan, "nope")


class SceneCounts(unittest.TestCase):
    def test_counts(self):
        sc = {"tiles": [{"flags": {"varrenmoor": {"layer": "foliage"}, "levels-3d-preview": {"sight": True}}},
                        {"flags": {"varrenmoor": {"layer": "buildings"}, "levels-3d-preview": {"collision": True, "sight": True}}, "hidden": False}],
              "lights": [{"flags": {"varrenmoor": {"type": "lamp"}}}], "grid": {"size": 50, "distance": 5}, "flags": {"levels-3d-preview": {"auto3d": True}}}
        c = bs.scene_counts(sc, "x")
        self.assertEqual((c["tiles"], c["foliage_tiles"], c["collision_tiles"], c["sight_tiles"], c["lights"]), (2, 1, 1, 2, 1))
        self.assertEqual(c["light_types"], {"lamp": 1})


if __name__ == "__main__":
    unittest.main()
