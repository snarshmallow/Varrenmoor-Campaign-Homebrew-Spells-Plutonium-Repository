"""Deleted roads must leave the map (python test_road_map_refresh.py). User report: 'deleting ticked roads and redrawing them doesn't remove them from the
map in Illustrator'. On a temp COPY of a small region place: delete-road -> render_world (what the Roads tab map refresh runs) -> the SVG holds the
deleted street id in no layer (Roads outline, kerbs on Details, off-map arrow on Bounds, labels, halos ...); other places that name the road (details.json
kerbs, markers.json, label_overrides.json) are cleaned with the same backup, and restore-streets brings every file back byte for byte. Join drops the
second road's entries the same way. Never touches world/."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import road_edit as re_  # noqa: E402

PLACE, GONE = "bridgehollow__dyers_walk_local", "str_020"
INK = "{http://www.inkscape.org/namespaces/inkscape}"


def layer_ids(svg_path, needle):
    """{layer label: [item ids containing needle]} over every layer of the SVG (Illustrator id encoding _x5F_ decoded)."""
    out = {}

    def walk(e, layer):
        if e.get(INK + "groupmode") == "layer":
            layer = e.get(INK + "label")
        i = (e.get("id") or "").replace("_x5F_", "_")
        if re.search(r"(^|_)" + re.escape(needle) + r"($|_)", i):
            out.setdefault(layer, []).append(i)
        for c in e:
            walk(c, layer)
    walk(ET.parse(svg_path).getroot(), None)
    return out


class DeleteLeavesTheMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.wd = os.path.join(cls.tmp, PLACE)
        src = os.path.join(REPO, "world", PLACE)
        os.makedirs(cls.wd)
        for f in os.listdir(src):
            if f.endswith(".json"):
                shutil.copyfile(os.path.join(src, f), os.path.join(cls.wd, f))
        shutil.copytree(os.path.join(src, "buildings"), os.path.join(cls.wd, "buildings"))
        cls.env = dict(os.environ, VB_WORLD_ROOT=cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def render(self, name):
        out = os.path.join(self.tmp, name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "render_world.py"), "--place", PLACE, "--out", out], env=self.env, cwd=REPO,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        return out

    def test_delete_then_render_has_no_id_and_undo_restores(self):
        files = ("streets.json", "details.json", "markers.json")
        orig = {f: Path(self.wd, f).read_bytes() for f in files}
        before = layer_ids(self.render("before.svg"), GONE)
        self.assertIn("Roads", before)                      # the case of the report: the road outline is on the map
        self.assertTrue(set(before) - {"Roads"}, before)    # ... and on other layers (region kerbs / off-map arrow)
        r = re_.op_delete(self.wd, [GONE])
        self.assertEqual(r["deleted"], [GONE])
        self.assertTrue(r["references_removed"].get("details.json") and r["references_removed"].get("markers.json"), r)
        after = layer_ids(self.render("after.svg"), GONE)
        self.assertEqual(after, {}, "deleted road still drawn on: %s" % after)
        self.assertIn("Roads", layer_ids(os.path.join(self.tmp, "after.svg"), "str_016"))
        res = re_.restore(self.wd)
        self.assertEqual(sorted(res["restored_files"]), sorted(files))
        for f in files:
            self.assertEqual(Path(self.wd, f).read_bytes(), orig[f], f)
        self.assertFalse(os.path.isdir(re_.side_dir(self.wd, res["restored"])))
        self.assertEqual(layer_ids(self.render("undo.svg"), GONE).keys(), before.keys())


class References(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wd = self.tmp

        def w(f, d):
            with open(os.path.join(self.wd, f), "w", encoding="utf-8") as fh:
                json.dump(d, fh)
        w("streets.json", {"place": "p", "streets": [{"id": "str_a", "kind": "lane", "geometry": {"type": "polyline", "points": [[0, 0], [50, 0]], "width_ft": 10}},
                                                     {"id": "str_b", "kind": "lane", "geometry": {"type": "polyline", "points": [[50, 0], [90, 0]], "width_ft": 10}},
                                                     {"id": "str_c", "kind": "lane", "geometry": {"type": "polyline", "points": [[0, 40], [90, 40]], "width_ft": 10}}]})
        w("details.json", {"kerbs": [{"id": "str_b_kerb1", "street": "str_b"}, {"id": "str_c_kerb1", "street": "str_c"}], "doors": [{"id": "d1"}]})
        w("markers.json", {"markers": [{"id": "mk_b", "street": "str_b", "parent_street": "str_b"}, {"id": "mk_c", "street": "str_c"}]})
        w("label_overrides.json", {"_note": "x", "labels": {"str_b": {"x_ft": 1, "y_ft": 2}, "str_c": {"x_ft": 3, "y_ft": 4}, "str_bb": {"x_ft": 0, "y_ft": 0}}})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def j(self, f):
        with open(os.path.join(self.wd, f), encoding="utf-8") as fh:
            return json.load(fh)

    def test_join_drops_the_second_roads_entries_and_undo(self):
        r = re_.op_join(self.wd, "str_a", "str_b")
        self.assertEqual(r["references_removed"], {"details.json": 1, "markers.json": 1, "label_overrides.json": 1})
        self.assertEqual([k["id"] for k in self.j("details.json")["kerbs"]], ["str_c_kerb1"])
        self.assertEqual(self.j("details.json")["doors"], [{"id": "d1"}])
        self.assertEqual([m["id"] for m in self.j("markers.json")["markers"]], ["mk_c"])
        self.assertEqual(sorted(self.j("label_overrides.json")["labels"]), ["str_bb", "str_c"])   # exact ids only
        re_.restore(self.wd)
        self.assertEqual(len(self.j("details.json")["kerbs"]), 2)
        self.assertIn("str_b", self.j("label_overrides.json")["labels"])
        self.assertEqual(len(self.j("streets.json")["streets"]), 3)

    def test_delete_without_references_writes_only_streets(self):
        r = re_.op_delete(self.wd, ["str_a"])
        self.assertEqual(r["references_removed"], {})
        self.assertFalse(os.path.isdir(re_.side_dir(self.wd, r["backup"])))

    def test_dry_run_writes_nothing(self):
        snap = {f: Path(self.wd, f).read_bytes() for f in os.listdir(self.wd)}
        r = re_.op_delete(self.wd, ["str_c"], dry=True)
        self.assertEqual(r["references_removed"]["details.json"], 1)
        self.assertEqual({f: Path(self.wd, f).read_bytes() for f in os.listdir(self.wd) if os.path.isfile(os.path.join(self.wd, f))}, snap)

    def test_old_backups_pruned_with_their_side_folder(self):
        for _ in range(re_.KEEP_BACKUPS + 2):
            re_.backup(self.wd, ["details.json"])
        self.assertEqual(len(re_.backups(self.wd)), re_.KEEP_BACKUPS)
        sides = [f for f in os.listdir(re_.backup_dir(self.wd)) if f.endswith(".side")]
        self.assertEqual(len(sides), re_.KEEP_BACKUPS)


if __name__ == "__main__":
    unittest.main()
