"""Tests for per-building / per-road editing (python test_object_edit.py): object_edit.py functions on a temp world, the validated `edit` blocks the
exporter reads, per-road grading overrides (road_grade.road_params), window switch (worldpack_detail.plan_holes). Defaults must stay unchanged.
Set VB_HEAVY=1 to also run one real export of the Dyers Walk place into a temp folder (about 15 s, a few hundred MB)."""
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import object_edit as oe  # noqa: E402
import road_grade as rg  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import test_road_grade as trg  # noqa: E402


def make_world(root, place="p"):
    d = os.path.join(root, place)
    os.makedirs(os.path.join(d, "buildings"))
    b1 = {"id": "bld_house_001", "kind": "house", "floors": 1, "geometry": {"type": "polygon", "points": [[0, 0], [10, 0], [10, 8], [0, 8]]}}
    b2 = {"id": "bld_house_002", "kind": "house", "floors": 1, "geometry": {"type": "polygon", "points": [[20, 0], [30, 0], [30, 8], [20, 8]]},
          "rooms": [{"id": "r0", "floor": 0}]}
    for b in (b1, b2):
        with open(os.path.join(d, "buildings", b["id"] + ".json"), "w") as f:
            json.dump(b, f)
    st = {"place": place, "streets": [{"id": "str_001", "kind": "street", "geometry": {"type": "polyline", "points": [[0, 20], [50, 20]], "width_ft": 16.0}},
                                      {"id": "str_002", "kind": "lane", "geometry": {"type": "polyline", "points": [[0, 30], [50, 30]], "width_ft": 10.0}}]}
    with open(os.path.join(d, "streets.json"), "w") as f:
        json.dump(st, f)
    return d


class EditCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = make_world(self.tmp)
        os.environ["VB_WORLD_ROOT"] = self.tmp

    def tearDown(self):
        os.environ.pop("VB_WORLD_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def bld(self, i="bld_house_001"):
        with open(os.path.join(self.dir, "buildings", i + ".json")) as f:
            return json.load(f)

    def streets(self):
        with open(os.path.join(self.dir, "streets.json")) as f:
            return json.load(f)["streets"]

    def test_set_and_clear_building(self):
        r = oe.set_building("p", ["bld_house_001"], ["roof_type=hip", "roof_pitch=0.8", "no_windows=true", "keep_individual=true", "wall_material=stone_slab",
                                                      "interior_style=poor_hovel", "floors=2", "style=auto"])
        self.assertEqual(r["count"], 1)
        b = self.bld()
        self.assertEqual(b["edit"], {"roof_type": "hip", "roof_pitch": 0.8, "no_windows": True, "keep_individual": True, "wall_material": "stone_slab"})
        self.assertEqual((b["floors"], b["interior_style"], b["style"]), (2, "poor_hovel", "auto"))
        oe.set_building("p", ["bld_house_001"], ["no_windows=false"], ["roof_type", "interior_style"])
        b = self.bld()
        self.assertNotIn("no_windows", b["edit"])
        self.assertNotIn("roof_type", b["edit"])
        self.assertNotIn("interior_style", b)
        oe.reset_building("p", ["bld_house_001"])
        self.assertNotIn("edit", self.bld())
        self.assertEqual(self.bld()["floors"], 2)                               # reset removes overrides, never the authored floors

    def test_validation_and_untouched_files(self):
        before = open(os.path.join(self.dir, "buildings", "bld_house_002.json")).read()
        for bad in (["roof_type=dome"], ["roof_pitch=9"], ["wall_material=nope"], ["bogus=1"], ["no_windows=maybe"], ["interior_style=castle"]):
            with self.assertRaises(SystemExit, msg=bad):
                oe.set_building("p", ["bld_house_001"], bad)
        with self.assertRaises(SystemExit):
            oe.set_building("p", ["bld_nope"], ["no_windows=true"])
        self.assertEqual(open(os.path.join(self.dir, "buildings", "bld_house_002.json")).read(), before)
        self.assertNotIn("edit", self.bld())

    def test_floors_guard_with_layout(self):
        with self.assertRaises(SystemExit):
            oe.set_building("p", ["bld_house_002"], ["floors=3"])
        oe.set_building("p", ["bld_house_002"], ["floors=1"])                  # same count as the layout: fine

    def test_set_road(self):
        oe.set_road("p", ["str_001"], ["class=lane", "surface=cobble", "kerb=true", "width_ft=22", "grade.smooth=0.9", "grade.max_grade_deg=8", "grade.cutfill=true"])
        s = self.streets()[0]
        self.assertEqual(s["geometry"]["width_ft"], 22.0)
        self.assertEqual(s["edit"], {"class": "lane", "surface": "cobble", "kerb": True, "grade": {"smooth": 0.9, "max_grade_deg": 8.0, "cutfill": True}})
        self.assertNotIn("edit", self.streets()[1])
        oe.set_road("p", ["str_001"], [], ["grade.smooth", "grade.max_grade_deg", "grade.cutfill", "kerb"])
        self.assertEqual(self.streets()[0]["edit"], {"class": "lane", "surface": "cobble"})
        oe.reset_road("p", ["str_001"])
        self.assertNotIn("edit", self.streets()[0])
        with self.assertRaises(SystemExit):
            oe.set_road("p", ["str_001"], ["class=bridge"])
        with self.assertRaises(SystemExit):
            oe.set_road("p", ["str_001"], ["width_ft=500"])

    def test_dry_run_writes_nothing(self):
        oe.set_road("p", ["str_001"], ["kerb=true"], dry=True)
        oe.set_building("p", ["bld_house_001"], ["no_windows=true"], dry=True)
        self.assertNotIn("edit", self.bld())
        self.assertNotIn("edit", self.streets()[0])

    def test_lists(self):
        oe.set_building("p", ["bld_house_001"], ["roof_type=hip"])
        lb = {b["id"]: b for b in oe.list_buildings("p")}
        self.assertEqual(lb["bld_house_001"]["edit"], {"roof_type": "hip"})
        self.assertTrue(lb["bld_house_002"]["has_layout"])
        self.assertEqual({r["id"] for r in oe.list_roads("p")}, {"str_001", "str_002"})
        self.assertIn("cobble", oe.choices()["textures"])


class ExporterBlocks(unittest.TestCase):
    def test_building_edit_validation(self):
        self.assertEqual(wp.building_edit({}), {})
        self.assertEqual(wp.building_edit({"edit": {"roof_type": "dome", "roof_pitch": 99, "no_windows": False, "x": 1, "keep_individual": True}}),
                         {"roof_pitch": 2.0, "keep_individual": True})

    def test_road_edit_validation(self):
        self.assertEqual(wp.road_edit({}), {})
        self.assertEqual(wp.road_edit({"edit": {"class": "lane", "kerb": False, "grade": {"smooth": 0.2, "bogus": 1, "max_grade_deg": None}, "z": 1}}),
                         {"class": "lane", "kerb": False, "grade": {"smooth": 0.2}})


class PerRoadGrade(unittest.TestCase):
    def setUp(self):
        self.h = trg.terrain()

    def roads(self, **ov):
        rs = trg.sparse_roads(self.h)
        for r in rs:
            if r["id"] in ov:
                r["grade_override"] = ov[r["id"]]
        return rs

    def test_default_unchanged(self):
        base, _ = rg.grade_roads(trg.synth(self.h, trg.sparse_roads(self.h)), self.h, {})
        same, rep1 = rg.grade_roads(trg.synth(self.h, self.roads()), self.h, {})
        for k in base:
            for a, b in zip(base[k], same[k]):
                np.testing.assert_array_equal(a.z, b.z)
        self.assertEqual(rep1["cutfill_ids"], [])
        self.assertEqual(rep1["overridden"], [])

    def test_override_affects_that_road(self):
        base, _ = rg.grade_roads(trg.synth(self.h, trg.sparse_roads(self.h)), self.h, {})
        ov, rep = rg.grade_roads(trg.synth(self.h, self.roads(b={"smooth": 1.0, "max_grade_deg": 4.0})), self.h, {})
        self.assertEqual(rep["overridden"], ["b"])
        self.assertFalse(np.allclose(base["b"][0].z, ov["b"][0].z))
        r = ov["b"][0]
        g = np.degrees(np.arctan(np.abs(np.diff(r.z)) / np.maximum(np.diff(r.s), 1e-6))).max()
        self.assertTrue(g <= 4.05 or any(w.startswith("b") and "grade limit" in w for w in rep["warnings"]), g)

    def test_per_road_cutfill_off_by_default_and_opt_in(self):
        h2, _, rep = rg.grade_and_cutfill(trg.synth(self.h, self.roads(a={"cutfill": True})), self.h, {})
        self.assertEqual(rep["cutfill_ids"], ["a"])
        self.assertIn("cutfill", rep)
        self.assertGreater(float(np.abs(h2 - self.h).max()), 0.0)
        h3, _, rep3 = rg.grade_and_cutfill(trg.synth(self.h, trg.sparse_roads(self.h)), self.h, {})
        np.testing.assert_array_equal(h3, self.h)                                # no override and no global switch: terrain untouched
        self.assertNotIn("cutfill", rep3)

    def test_global_cutfill_with_road_opt_out(self):
        _, _, rep = rg.grade_and_cutfill(trg.synth(self.h, self.roads(a={"cutfill": False})), self.h, {"cutfill": True})
        self.assertEqual(rep["cutfill_ids"], ["b", "c"])

    def test_params_clamped(self):
        P = rg.params({})
        r = rg.road_params(P, {"grade_override": {"smooth": 5, "max_grade_deg": 500, "cross_deg": -3}})
        self.assertEqual((r["smooth"], r["max_grade_deg"], r["cross_deg"]), (1.0, 60.0, 0.0))
        self.assertEqual(rg.road_params(P, {})["max_grade_deg"], 14.0)


class WindowSwitch(unittest.TestCase):
    def test_no_windows(self):
        P = [(0, 0), (10, 0), (10, 8), (0, 8)]
        a = wd.plan_holes(P, {}, 1, 0.0)
        b = wd.plan_holes(P, {}, 1, 0.0, no_windows=True)
        self.assertTrue(any(h["kind"] == "window" for e in a for h in e))
        self.assertFalse(any(h["kind"] == "window" for e in b for h in e))


@unittest.skipUnless(os.environ.get("VB_HEAVY"), "set VB_HEAVY=1 for the real export")
class RealExport(unittest.TestCase):
    def test_export_honours_edits(self):
        place = "bridgehollow__dyers_walk_local"
        src = os.path.join(HERE, "..", "..", "world", place)
        tmp = tempfile.mkdtemp()
        try:
            shutil.copytree(src, os.path.join(tmp, place), ignore=shutil.ignore_patterns("export"))
            os.environ["VB_WORLD_ROOT"] = tmp
            bid = sorted(f[:-5] for f in os.listdir(os.path.join(tmp, place, "buildings")))[0]
            with open(os.path.join(tmp, place, "streets.json")) as f:
                sid = json.load(f)["streets"][0]["id"]
            oe.set_building(place, [bid], ["roof_type=hip", "roof_pitch=0.9", "keep_individual=true", "no_windows=true", "wall_material=stone_slab"])
            oe.set_road(place, [sid], ["class=alley", "grade.smooth=1"])
            out = os.path.join(tmp, "pack")
            wp.export_world(place, out_dir=out, world_root=tmp, log=lambda *_: None)
            p = wp.load_pack(out)
            b = p.get(bid)
            self.assertEqual((b["roof"]["type"], b["roof"]["pitch"], b["keep_individual"]), ("hip", 0.9, True))
            self.assertEqual(b["wall"]["surface"]["material"], "mat_stone_slab")
            r = p.get(sid)
            self.assertEqual(r["class"], "alley")
            self.assertEqual(r["grade_override"], {"smooth": 1.0})
        finally:
            os.environ.pop("VB_WORLD_ROOT", None)
            shutil.rmtree(tmp, ignore_errors=True)


@unittest.skipUnless(os.environ.get("VB_HEAVY"), "set VB_HEAVY=1 (splits and merges a copy of the Dyers Walk pack)")
class MergeKeepIndividual(unittest.TestCase):
    def test_flagged_building_keeps_its_own_file(self):
        import worldpack_split as ws
        pk0 = os.path.join(HERE, "..", "..", "world", "bridgehollow__dyers_walk_local", "export")
        tmp = tempfile.mkdtemp()
        try:
            pk = os.path.join(tmp, "export")
            shutil.copytree(pk0, pk)
            ep = os.path.join(pk, "entities", "buildings.json")
            doc = wp._jload(ep)
            bid = doc["items"][0]["id"]
            doc["items"][0]["keep_individual"] = True
            with open(ep, "w") as f:
                json.dump(doc, f)
            ws.split_export(pk, log=lambda m: None)
            out = os.path.join(tmp, "opt")
            res, _rep = ws.merge_export(pk, "layer", out_dir=out, lods=(), log=lambda m: None)
            files = [e["file"] for e in res["files"]]
            self.assertTrue(any(bid in f for f in files), files)
            ent = [e for e in res["files"] if bid in e["file"]][0]
            self.assertIn(bid, ent["ids"])
            self.assertEqual(len(ent["ids"]), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class RoadGeometry(unittest.TestCase):
    """delete / add / reshape / split / join / apply-paths / draw / undo on a temp world (road_edit.py through object_edit.main)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.dir = make_world(self.tmp)
        with open(os.path.join(self.dir, "place.json"), "w") as f:
            json.dump({"id": "p", "bounds": {"width_ft": 1000, "height_ft": 800}}, f)
        os.environ["VB_WORLD_ROOT"] = self.tmp
        # a stale per-vertex height array must never survive a reshape
        d = self.doc()
        d["streets"][0]["elevations_ft"] = [1.0, 2.0]
        d["streets"][0]["elevation_ft"] = 1.5
        d["streets"].append({"id": "str_br", "kind": "bridge", "geometry": {"type": "polyline", "points": [[0, 50], [40, 50]], "width_ft": 10.0}})
        self.save(d)

    def tearDown(self):
        os.environ.pop("VB_WORLD_ROOT", None)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def doc(self):
        with open(os.path.join(self.dir, "streets.json")) as f:
            return json.load(f)

    def save(self, d):
        with open(os.path.join(self.dir, "streets.json"), "w") as f:
            json.dump(d, f)

    def raw(self):
        with open(os.path.join(self.dir, "streets.json"), "rb") as f:
            return f.read()

    def ids(self):
        return [s["id"] for s in self.doc()["streets"]]

    def nbackups(self):
        d = os.path.join(self.dir, "streets_backups")
        return len(os.listdir(d)) if os.path.isdir(d) else 0

    def run_cli(self, *a):
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            oe.main(["--world-root", self.tmp] + list(a))
        return json.loads(buf.getvalue())

    def refuses(self, *a):
        before, nb = self.raw(), self.nbackups()
        with self.assertRaises(SystemExit) as cm:
            self.run_cli(*a)
        self.assertEqual(self.raw(), before, "a refusal must write nothing")
        self.assertEqual(nb, self.nbackups(), "a refusal must not leave a backup")
        return str(cm.exception)

    def jfile(self, name, data):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as f:
            json.dump(data, f)
        return p

    def test_delete_and_undo(self):
        before = self.raw()
        r = self.run_cli("delete-road", "--place", "p", "--ids", "str_002")
        self.assertEqual(r["deleted"], ["str_002"])
        self.assertNotIn("str_002", self.ids())
        r = self.run_cli("restore-streets", "--place", "p")
        self.assertEqual(r["remaining"], 0)
        self.assertEqual(self.raw(), before)
        self.assertIn("nothing to restore", self.refuses("restore-streets", "--place", "p"))

    def test_delete_refusals(self):
        self.assertIn("unknown road", self.refuses("delete-road", "--place", "p", "--ids", "str_001,str_nope"))
        self.assertIn("bridge", self.refuses("delete-road", "--place", "p", "--ids", "str_br"))
        with open(os.path.join(self.dir, "bridges.json"), "w") as f:
            json.dump({"bridges": [{"id": "brg1", "street": "str_002"}]}, f)
        self.assertIn("bridges.json", self.refuses("delete-road", "--place", "p", "--ids", "str_002"))

    def test_add_road(self):
        r = self.run_cli("add-road", "--place", "p", "--name", "Mill Lane", "--kind", "lane", "--width", "12", "--points", "10,10;60,20;120,25")
        self.assertEqual(r["added"], ["str_mill_lane"])
        s = self.doc()["streets"][-1]
        self.assertEqual((s["kind"], s["geometry"]["width_ft"], len(s["geometry"]["points"])), ("lane", 12.0, 3))
        r = self.run_cli("add-road", "--place", "p", "--name", "Mill Lane", "--points", "10,10;60,20")
        self.assertEqual(r["added"], ["str_mill_lane_2"])
        self.run_cli("restore-streets", "--place", "p")
        self.assertNotIn("str_mill_lane_2", self.ids())
        self.assertIn("str_mill_lane", self.ids())

    def test_add_refusals(self):
        base = ["add-road", "--place", "p", "--name", "X"]
        self.assertIn("at least 2", self.refuses(*base, "--points", "1,1"))
        self.assertIn("same place", self.refuses(*base, "--points", "1,1;1,1"))
        self.assertIn("bad point", self.refuses(*base, "--points", "1,1;a,b"))
        self.assertIn("far outside", self.refuses(*base, "--points", "1,1;90000,1"))
        self.assertIn("not one of", self.refuses(*base, "--kind", "bridge", "--points", "1,1;50,1"))
        self.assertIn("outside", self.refuses(*base, "--width", "500", "--points", "1,1;50,1"))
        self.assertIn("already exists", self.refuses(*base, "--id", "str_001", "--points", "1,1;50,1"))
        self.assertIn("must look like", self.refuses(*base, "--id", "bad id", "--points", "1,1;50,1"))
        self.assertIn("needs --points", self.refuses(*base))

    def test_set_points_drops_stale_heights(self):
        r = self.run_cli("set-road-points", "--place", "p", "--ids", "str_001", "--points", "0,20;25,30;50,20")
        self.assertEqual(r["points_after"], 3)
        s = self.doc()["streets"][0]
        self.assertEqual(s["geometry"]["points"], [[0, 20], [25, 30], [50, 20]])
        self.assertNotIn("elevations_ft", s)
        self.assertNotIn("elevation_ft", s)
        self.assertEqual(s["geometry"]["width_ft"], 16.0)

    def test_simplify_and_smooth_existing(self):
        d = self.doc()
        d["streets"][0]["geometry"]["points"] = [[0, 20], [10, 20.2], [20, 19.9], [30, 20.1], [50, 20]]
        self.save(d)
        r = self.run_cli("set-road-points", "--place", "p", "--ids", "str_001", "--simplify", "1")
        self.assertEqual(r["points_after"], 2)
        d = self.doc()
        d["streets"][0]["geometry"]["points"] = [[0, 0], [10, 40], [20, 0], [30, 40], [40, 0]]
        self.save(d)
        self.run_cli("set-road-points", "--place", "p", "--ids", "str_001", "--smooth", "3")
        p = self.doc()["streets"][0]["geometry"]["points"]
        self.assertEqual((p[0], p[-1], len(p)), ([0, 0], [40, 0], 5))
        self.assertLess(p[1][1], 40)
        self.assertIn("give --points", self.refuses("set-road-points", "--place", "p", "--ids", "str_001"))
        self.assertIn("exactly one", self.refuses("set-road-points", "--place", "p", "--ids", "str_001,str_002", "--simplify", "1"))
        self.assertIn("bridge", self.refuses("set-road-points", "--place", "p", "--ids", "str_br", "--points", "0,0;9,9"))

    def test_split_and_join(self):
        d = self.doc()
        d["streets"][0]["geometry"]["points"] = [[0, 20], [10, 20], [20, 20], [30, 20], [50, 20]]
        self.save(d)
        r = self.run_cli("split-road", "--place", "p", "--ids", "str_001", "--at", "2")
        self.assertEqual(r["added"], ["str_001_2"])
        a, b = self.doc()["streets"][0], self.doc()["streets"][1]
        self.assertEqual((len(a["geometry"]["points"]), len(b["geometry"]["points"])), (3, 3))
        self.assertEqual(a["geometry"]["points"][-1], b["geometry"]["points"][0])
        self.assertIn("--at", self.refuses("split-road", "--place", "p", "--ids", "str_001", "--at", "0"))
        r = self.run_cli("join-roads", "--place", "p", "--ids", "str_001,str_001_2")
        self.assertEqual(r["deleted"], ["str_001_2"])
        self.assertEqual(len(self.doc()["streets"][0]["geometry"]["points"]), 5)
        self.assertIn("a lane", self.refuses("join-roads", "--place", "p", "--ids", "str_001,str_002"))
        d = self.doc()
        d["streets"][1]["kind"] = "street"
        self.save(d)
        self.assertIn("apart", self.refuses("join-roads", "--place", "p", "--ids", "str_001,str_002", "--join-tol", "5"))
        self.assertIn("exactly two", self.refuses("join-roads", "--place", "p", "--ids", "str_001"))

    def test_apply_paths(self):
        f = self.jfile("paths.json", {"paths": [{"name": "str_x5F_001", "points": [[0, 20], [20, 25], [50, 20]], "closed": False},
                                                {"name": "Path 7", "points": [[100, 100], [150, 120]], "closed": False}]})
        self.assertIn("not named", self.refuses("apply-paths", "--place", "p", "--file", f, "--mode", "reshape"))
        r = self.run_cli("apply-paths", "--place", "p", "--file", f, "--mode", "sync", "--kind", "alley", "--width", "9", "--name", "Back Way")
        self.assertEqual((r["changed"], r["added"]), (["str_001"], ["str_back_way"]))
        s = self.doc()["streets"]
        self.assertEqual(s[0]["geometry"]["points"][1], [20, 25])
        self.assertEqual((s[-1]["kind"], s[-1]["geometry"]["width_ft"], s[-1]["name"]), ("alley", 9.0, "Back Way"))
        self.assertEqual(self.nbackups(), 1)
        self.run_cli("restore-streets", "--place", "p")
        self.assertNotIn("str_back_way", self.ids())
        self.assertEqual(self.doc()["streets"][0]["geometry"]["points"], [[0, 20], [50, 20]])

    def test_apply_paths_refusals(self):
        pts = [[0, 20], [50, 20]]

        def ref(paths, mode):
            return self.refuses("apply-paths", "--place", "p", "--file", self.jfile("pp.json", {"paths": paths}), "--mode", mode)
        self.assertIn("closed path", ref([{"name": "str_001", "points": pts, "closed": True}], "sync"))
        self.assertIn("already road", ref([{"name": "str_001", "points": pts}], "add"))
        self.assertIn("twice", ref([{"name": "str_001", "points": pts}, {"name": "str_001_casing", "points": pts}], "reshape"))
        self.assertIn("bridge", ref([{"name": "str_br", "points": pts}], "reshape"))
        self.assertIn("at least 2", ref([{"name": "str_001", "points": [[1, 1]]}], "reshape"))
        # a good path followed by a bad one: nothing is written (refuses() checks the file is byte-identical)
        self.assertIn("at least 2", ref([{"name": "str_001", "points": pts}, {"name": "str_002", "points": [[1, 1]]}], "reshape"))
        self.assertIn("no paths", ref([], "sync"))

    def test_road_id_from_name(self):
        import road_edit as re_
        ids = {"str_oak", "str_oak_ring", "str_001"}
        self.assertEqual(re_.road_id_from_name("str_x5F_oak_x5F_ring", ids), "str_oak_ring")
        self.assertEqual(re_.road_id_from_name("str_oak_ring_casing", ids), "str_oak_ring")
        self.assertEqual(re_.road_id_from_name("str_oak_lane", ids), "str_oak")
        self.assertIsNone(re_.road_id_from_name("str_oakx", ids))
        self.assertIsNone(re_.road_id_from_name("bld_house_001", ids))

    def test_draw_svg_matches_view_mapping(self):
        view = self.jfile("view.json", {"x0": 0.0, "y0": 0.0, "k": 2.0, "margin_in": 0.5, "page_in": [17, 11]})
        out = os.path.join(self.tmp, "roads.svg")
        r = self.run_cli("draw-roads", "--place", "p", "--view-file", view, "--out", out)
        self.assertEqual(r["roads"], 2)                                  # the bridge is not drawn
        txt = open(out, encoding="utf-8").read()
        self.assertIn('id="Road Centerlines"', txt)
        self.assertIn('id="str_x5F_001"', txt)
        self.assertIn("M36.00,76.00 L136.00,76.00", txt)                 # (0,20) ft -> 36 + 0, 36 + 20 * 2
        self.assertNotIn("str_x5F_br", txt)

    def test_set_road_keeps_a_backup(self):
        before = self.raw()
        self.run_cli("set-road", "--place", "p", "--ids", "str_001", "--set", "kerb=true")
        self.run_cli("restore-streets", "--place", "p")
        self.assertEqual(self.raw(), before)

    def test_dry_writes_nothing(self):
        before = self.raw()
        r = self.run_cli("delete-road", "--place", "p", "--ids", "str_001", "--dry")
        self.assertTrue(r["dry"])
        self.assertEqual(self.raw(), before)
        self.assertEqual(self.nbackups(), 0)


if __name__ == "__main__":
    unittest.main()
