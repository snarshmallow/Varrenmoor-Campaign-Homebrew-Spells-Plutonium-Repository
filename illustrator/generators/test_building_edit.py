"""Building editing (building_edit.py via object_edit.py) on a temp copy of world/bridgehollow__dyers_walk_local: delete + undo, add, move, rotate, resize,
duplicate, rename with references, properties, door, Illustrator paths, validation refusals writing nothing, dry run, the SVG check after a delete.
    python -m pytest illustrator/generators/test_building_edit.py   (or python test_building_edit.py)"""
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import building_edit as be  # noqa: E402
import object_edit as oe  # noqa: E402

SRC = os.path.join(HERE, "..", "..", "world", "bridgehollow__dyers_walk_local")
PLACE = "bridgehollow__dyers_walk_local"


def snapshot(wd):
    out = {}
    for root, dirs, files in os.walk(wd):
        if "buildings_backups" in root:
            continue
        for f in files:
            p = os.path.join(root, f)
            out[os.path.relpath(p, wd)] = open(p, "rb").read()
    return out


@unittest.skipUnless(os.path.isdir(SRC), "fixture place missing")
class BuildingEdit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wd = os.path.join(self.tmp, PLACE)
        shutil.copytree(SRC, self.wd, ignore=shutil.ignore_patterns("export", "panel_state.json"))
        os.environ["VB_WORLD_ROOT"] = self.tmp
        self.before = snapshot(self.wd)

    def tearDown(self):
        os.environ.pop("VB_WORLD_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def cli(self, *a):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            oe.main(["--world-root", self.tmp] + list(a))
        return json.loads(buf.getvalue())

    def b(self, bid):
        return json.load(open(os.path.join(self.wd, "buildings", bid + ".json"), encoding="utf-8"))

    def det(self):
        return json.load(open(os.path.join(self.wd, "details.json"), encoding="utf-8"))

    def assertUnchanged(self):
        self.assertEqual(snapshot(self.wd), self.before)

    # ---- delete
    def test_delete_and_undo(self):
        r = self.cli("delete-building", "--place", PLACE, "--ids", "bld_house_041,bld_house_044")
        self.assertEqual(r["deleted"], ["bld_house_041", "bld_house_044"])
        self.assertFalse(os.path.exists(os.path.join(self.wd, "buildings", "bld_house_041.json")))
        txt = json.dumps(self.det())
        self.assertNotIn('"bld_house_041"', txt)
        self.assertNotIn("bld_house_041", json.dumps(json.load(open(os.path.join(self.wd, "region.json")))["id_map"]))
        u = self.cli("restore-buildings", "--place", PLACE)
        self.assertEqual(u["op"], "delete")
        self.assertUnchanged()
        with self.assertRaises(SystemExit):
            self.cli("restore-buildings", "--place", PLACE)

    def test_delete_refusals_write_nothing(self):
        for args in (["--ids", "bld_nope"], ["--ids", "bld_house_041,bld_nope"]):
            with self.assertRaises(SystemExit):
                self.cli("delete-building", "--place", PLACE, *args)
        self.assertUnchanged()
        self.assertFalse(os.path.isdir(os.path.join(self.wd, "buildings_backups")))

    def test_dry_run_writes_nothing(self):
        for a in (["delete-building", "--ids", "bld_house_041"], ["move-building", "--ids", "bld_house_041", "--dx", "4"], ["rename-building", "--ids", "bld_house_041", "--new-id", "bld_x_hall"],
                  ["add-building", "--center", "150,150", "--width", "20", "--depth", "14"], ["resize-building", "--ids", "bld_house_041", "--scale", "1.2"]):
            r = self.cli(a[0], "--place", PLACE, "--dry", *a[1:])
            self.assertTrue(r["dry"])
            self.assertIsNone(r["backup"])
        self.assertUnchanged()

    def test_render_after_delete_has_no_id(self):
        """render_world on the edited model (--model-dir) must not name the deleted building anywhere (map refresh check)."""
        self.cli("delete-building", "--place", PLACE, "--ids", "bld_house_041")
        svg = os.path.join(self.tmp, "map.svg")
        p = subprocess.run([sys.executable, os.path.join(HERE, "render_world.py"), "--place", PLACE, "--model-dir", self.wd, "--out", svg, "--svg-check", "warn"],
                           capture_output=True, text=True, cwd=HERE)
        self.assertEqual(p.returncode, 0, p.stderr[-800:])
        self.assertTrue(be.svg_absent(svg, ["bld_house_041"])["ok"], be.svg_absent(svg, ["bld_house_041"]))
        self.assertFalse(be.svg_absent(svg, ["bld_house_044"])["ok"])          # a kept building is still there (the check is real)

    # ---- add / validation
    def test_add_and_validation(self):
        r = self.cli("add-building", "--place", PLACE, "--name", "Test Shop", "--kind", "shop", "--center", "150,150", "--width", "20", "--depth", "14", "--rotation", "30", "--floors", "2")
        b = self.b(r["added"][0])
        self.assertEqual((b["name"], b["kind"], b["floors"]), ("Test Shop", "shop", 2))
        self.assertLess(be.shoelace(b["geometry"]["points"]), 0)                # counter-clockwise on the map (y down)
        self.assertAlmostEqual(r["size_ft"][0], 20.0, places=1)
        self.assertEqual(b.get("district"), be.district_of(self.wd, b["geometry"]["points"]))
        snap = snapshot(self.wd)
        bad = [["--center", "150,150", "--width", "3", "--depth", "14"], ["--center", "150,150", "--width", "500", "--depth", "14"],
               ["--center", "nan,1", "--width", "20", "--depth", "14"], ["--points", "0,0;10,10;10,0;0,10"], ["--center", "99999,5", "--width", "20", "--depth", "14"],
               ["--center", "150,150", "--width", "20", "--depth", "14", "--kind", "castle"], ["--center", "150,150", "--width", "20", "--depth", "14", "--id", "Bad Id"],
               ["--center", "150,150", "--width", "20", "--depth", "14", "--floors", "0"], ["--center", "150,150", "--width", "20", "--depth", "14", "--points", "0,0;9,0;9,9"]]
        for a in bad:
            with self.assertRaises(SystemExit, msg=str(a)):
                self.cli("add-building", "--place", PLACE, *a)
        self.assertEqual(snapshot(self.wd), snap)

    def test_overlap_warning(self):
        c = self.b("bld_house_041")["geometry"]["points"]
        cx, cy = sum(p[0] for p in c) / len(c), sum(p[1] for p in c) / len(c)
        r = self.cli("add-building", "--place", PLACE, "--center", f"{cx},{cy}", "--width", "10", "--depth", "8")
        self.assertTrue(any("bld_house_041" in w for w in r["warnings"]), r["warnings"])

    # ---- move / rotate / resize
    def test_move_rigid_keeps_interior(self):
        b0 = self.b("bld_house_041")
        d0 = [d for d in self.det()["doors"] if d["building"] == "bld_house_041"][0]
        self.cli("move-building", "--place", PLACE, "--ids", "bld_house_041", "--dx", "3", "--dy", "-2")
        b1 = self.b("bld_house_041")
        for p, q in zip(b0["geometry"]["points"], b1["geometry"]["points"]):
            self.assertAlmostEqual(q[0] - p[0], 3, places=1)
            self.assertAlmostEqual(q[1] - p[1], -2, places=1)
        self.assertAlmostEqual(b1["rooms"][0]["polygon"][0][0] - b0["rooms"][0]["polygon"][0][0], 3, places=2)
        self.assertAlmostEqual(b1["layout"]["windows"][0]["point"][1] - b0["layout"]["windows"][0]["point"][1], -2, places=2)
        self.assertNotIn("elevation_ft", b1)
        d1 = [d for d in self.det()["doors"] if d["building"] == "bld_house_041"][0]
        self.assertAlmostEqual(d1["point"][0] - d0["point"][0], 3, places=1)
        lot0 = [x for x in json.load(open(os.path.join(SRC, "details.json")))["lots"] if x["building"] == "bld_house_041"][0]
        self.assertEqual([x for x in self.det()["lots"] if x["building"] == "bld_house_041"][0], lot0)   # lot stays without --with-lot

    def test_rotate_and_resize(self):
        b0 = self.b("bld_house_041")
        c0, a0, l0, s0 = be.obb(b0["geometry"]["points"])
        self.cli("rotate-building", "--place", PLACE, "--ids", "bld_house_041", "--deg", "90")
        b1 = self.b("bld_house_041")
        c1, a1, l1, s1 = be.obb(b1["geometry"]["points"])
        self.assertAlmostEqual(l0, l1, places=1)
        self.assertAlmostEqual(c0[0], c1[0], places=1)
        self.assertAlmostEqual(abs(((a1 - a0) % 180) - 90), 0, places=0)
        self.assertIn("layout", b1)                                             # rigid: interior kept
        r = self.cli("resize-building", "--place", PLACE, "--ids", "bld_house_041", "--width", "30")
        b2 = self.b("bld_house_041")
        self.assertAlmostEqual(be.obb(b2["geometry"]["points"])[2], 30, places=1)
        for k in ("rooms", "layout", "doors"):
            self.assertNotIn(k, b2)                                             # not rigid: interior dropped
        self.assertFalse([d for d in self.det()["doors"] if d["building"] == "bld_house_041"])
        self.assertEqual(r["sizes"]["bld_house_041"]["after_ft"][0], 30.0)
        with self.assertRaises(SystemExit):
            self.cli("resize-building", "--place", PLACE, "--ids", "bld_house_041", "--depth", "2")
        for _ in range(2):
            self.cli("restore-buildings", "--place", PLACE)
        self.assertUnchanged()

    # ---- rename / properties / duplicate / door
    def test_rename_updates_references(self):
        lp = os.path.join(self.wd, "label_overrides.json")
        json.dump({"labels": {"bld_house_052": {"x_ft": 1, "y_ft": 2}}}, open(lp, "w"))
        self.before = snapshot(self.wd)
        r = self.cli("rename-building", "--place", PLACE, "--ids", "bld_house_052", "--new-id", "bld_dyers_hall", "--name", "Dyers Hall")
        self.assertEqual(r["renamed"], {"bld_house_052": "bld_dyers_hall"})
        b = self.b("bld_dyers_hall")
        self.assertEqual((b["id"], b["name"]), ("bld_dyers_hall", "Dyers Hall"))
        self.assertFalse(os.path.exists(os.path.join(self.wd, "buildings", "bld_house_052.json")))
        self.assertNotIn("bld_house_052", json.dumps({k: v for k, v in b.items() if k != "region"}))
        self.assertEqual(b["region"]["parent_id"], "bld_house_052")              # parent place id unchanged
        self.assertNotIn('"bld_house_052', json.dumps(self.det()))
        self.assertIn("bld_dyers_hall", json.load(open(lp))["labels"])
        self.assertIn(["bld_dyers_hall"], list(json.load(open(os.path.join(self.wd, "region.json")))["id_map"].values()))
        for bad in ("bld_house_044", "Bad", "bld__x"):
            with self.assertRaises(SystemExit):
                self.cli("rename-building", "--place", PLACE, "--ids", "bld_dyers_hall", "--new-id", bad)
        self.cli("restore-buildings", "--place", PLACE)
        self.assertUnchanged()

    def test_props_duplicate_door(self):
        self.cli("set-building-props", "--place", PLACE, "--ids", "bld_house_041,bld_house_044", "--tags", "guild, dyers", "--owner", "Mira", "--district", "auto")
        b = self.b("bld_house_044")
        self.assertEqual(b["tags"], ["dyers", "guild"])
        self.assertEqual(b["owner"], "Mira")
        self.cli("set-building-props", "--place", PLACE, "--ids", "bld_house_044", "--tags", "", "--district", "")
        self.assertNotIn("tags", self.b("bld_house_044"))
        self.assertNotIn("district", self.b("bld_house_044"))
        with self.assertRaises(SystemExit):
            self.cli("set-building-props", "--place", PLACE, "--ids", "bld_house_044", "--floors", "3")     # stored interior is 2 storeys
        with self.assertRaises(SystemExit):
            self.cli("set-building-props", "--place", PLACE, "--ids", "bld_house_041,bld_house_044", "--name", "Same")
        r = self.cli("duplicate-building", "--place", PLACE, "--ids", "bld_house_041")
        nb = self.b(r["added"][0])
        self.assertTrue(nb["name"].endswith("(copy)"))
        self.assertNotIn("layout", nb)
        r = self.cli("set-door", "--place", PLACE, "--ids", "bld_house_041", "--edge", "1", "--pos", "0.3")
        ds = [d for d in self.det()["doors"] if d["building"] == "bld_house_041"]
        self.assertEqual(len(ds), 1)
        self.assertEqual(ds[0]["edge"], 1)
        with self.assertRaises(SystemExit):
            self.cli("set-door", "--place", PLACE, "--ids", "bld_house_041", "--edge", "9")

    # ---- Illustrator paths / drawing
    def test_paths_and_draw(self):
        pts = self.b("bld_house_041")["geometry"]["points"]
        newsq = [[150, 150], [170, 150], [170, 166], [150, 166]]
        f = os.path.join(self.tmp, "paths.json")
        json.dump({"paths": [{"name": "bld_x5F_house_x5F_041", "closed": True, "points": [[x + 1, y] for x, y in pts]}, {"name": "Path 3", "closed": True, "points": newsq}]}, open(f, "w"))
        r = self.cli("apply-building-paths", "--place", PLACE, "--file", f, "--mode", "sync", "--kind", "barn")
        self.assertEqual(r["changed"], ["bld_house_041"])
        self.assertEqual(self.b(r["added"][0])["kind"], "barn")
        json.dump({"paths": [{"name": "x", "closed": False, "points": newsq}]}, open(f, "w"))
        with self.assertRaises(SystemExit):
            self.cli("apply-building-paths", "--place", PLACE, "--file", f, "--mode", "add")
        view = {"k": 2.0, "margin_in": 0.5, "x0": 0, "y0": 0, "page_in": [17, 11]}
        vf = os.path.join(self.tmp, "view.json")
        json.dump(view, open(vf, "w"))
        svg = os.path.join(self.tmp, "fp.svg")
        d = self.cli("draw-buildings", "--place", PLACE, "--view-file", vf, "--out", svg)
        self.assertEqual(d["buildings"], len(os.listdir(os.path.join(self.wd, "buildings"))))
        self.assertIn('inkscape:label="Building Footprints"', open(svg).read())
        self.assertIn("bld_x5F_house_x5F_041", open(svg).read())

    def test_backup_retention(self):
        for i in range(be.KEEP_BACKUPS + 3):
            self.cli("move-building", "--place", PLACE, "--ids", "bld_house_041", "--dx", "0.5")
        self.assertEqual(len(be.list_backups(self.wd)), be.KEEP_BACKUPS)


if __name__ == "__main__":
    unittest.main()
