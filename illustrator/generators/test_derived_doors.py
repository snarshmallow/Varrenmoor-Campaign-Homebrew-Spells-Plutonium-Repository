"""Generated towns (no details.json) must still get interior lights: worldpack export --derive-doors auto gives every building without a
details.json door a street-facing front door -> openings -> generated interior -> hearth / window light hints in placements.json.
Small draft place in a temp world root; nothing in world/ is touched.
  python illustrator/generators/test_derived_doors.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import place_create as pc  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_split as ws  # noqa: E402

TMP = tempfile.mkdtemp(prefix="derdoors_")
TS = "2026-01-01T00:00:00+00:00"
SQ = [[560, 560], [600, 560], [600, 585], [560, 585]]          # 40 x 25 ft house, street along its south side (y = 545)


def jl(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


class DerivedDoors(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pc.create({"name": "Derived Doors", "id": "der_test", "culture": "english", "size_ft": [1200, 1200], "seed": 5}, out_root=TMP, force=True, draft=True, no_town=True)
        cls.pdir = os.path.join(TMP, "der_test")
        os.makedirs(os.path.join(cls.pdir, "buildings"), exist_ok=True)
        json.dump({"id": "bld_der_house", "name": "Derived door house", "kind": "house", "status": "proposed", "geometry": {"type": "polygon", "points": SQ}, "notes": "",
                   "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": 2, "rooms": [], "doors": [], "elevation_ft": 100.0,
                   "site_slope": 0.0, "site_relief_ft": 1.0}, open(os.path.join(cls.pdir, "buildings", "bld_der_house.json"), "w"))
        sp = os.path.join(cls.pdir, "streets.json")
        st = jl(sp) if os.path.exists(sp) else {"streets": []}
        st["streets"] = [{"id": "st_der_1", "name": "Test lane", "kind": "lane", "status": "proposed", "geometry": {"type": "polyline", "points": [[500, 545], [660, 545]], "width_ft": 12}}]
        json.dump(st, open(sp, "w"))
        assert not os.path.exists(os.path.join(cls.pdir, "details.json"))   # a generated town has no details.json: the Bridgehollow case
        cls.auto = os.path.join(TMP, "pack_auto")
        wp.export_world("der_test", cls.auto, world_root=TMP, timestamp=TS, lod=(4,), log=lambda m: None, copy_textures=False, derive_doors="auto")
        ws.split_export(cls.auto, log=lambda m: None)
        cls.off = os.path.join(TMP, "pack_off")
        wp.export_world("der_test", cls.off, world_root=TMP, timestamp=TS, lod=(4,), log=lambda m: None, copy_textures=False, derive_doors="off")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_door_faces_the_street(self):
        b = {"id": "b", "kind": "house", "geometry": {"points": SQ}}
        d = wp.derive_street_doors([b], [{"geometry": {"points": [[500, 545], [660, 545]], "width_ft": 12}}])
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["point"], [580.0, 560.0])               # midpoint of the south edge
        self.assertEqual(d[0]["facing"], [0.0, -1.0])                 # outward, toward the street
        self.assertEqual(wp.derive_street_doors([b], [], have={"b"}), [])   # an existing details.json door wins

    def test_auto_export_has_interior_and_lights(self):
        b = [e for e in jl(os.path.join(self.auto, "entities", "buildings.json"))["items"] if e["id"] == "bld_der_house"][0]
        self.assertTrue(b.get("openings") and b.get("layout"))
        doc = jl(os.path.join(self.auto, "placements.json"))
        types = sorted({lt["type"] for e in doc["files"] for lt in e.get("lights", [])})
        self.assertIn("window", types)
        self.assertGreater(fp._count_lights(doc), 0)

    def test_off_keeps_old_behaviour(self):
        b = [e for e in jl(os.path.join(self.off, "entities", "buildings.json"))["items"] if e["id"] == "bld_der_house"][0]
        self.assertFalse(b.get("openings") or b.get("layout"))

    def test_zero_light_warning_names_the_real_cause(self):
        doc = {"place": "der_test", "frame": {"px_per_ft": 20, "z_origin_ft": 0}, "files": [{"file": "a.glb"}]}
        self.assertIn("re-export", fp.no_lights_hint(doc, full=True).lower())
        self.assertIn("--lights-placements", fp.no_lights_hint(doc, full=False))


if __name__ == "__main__":
    unittest.main(verbosity=1)
