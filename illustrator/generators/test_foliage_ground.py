"""Foliage on the FINAL terrain (python test_foliage_ground.py): Ground heights = the terrain build_parts builds (road grading / cut-fill), not the old conform;
trees on road beds, bridge decks and building footprints are left out of the merge."""
import os
import shutil
import sys
import tempfile
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foliage as fo  # noqa: E402
import foliage_mesh as fm  # noqa: E402
import road_grade as rg  # noqa: E402
import test_road_grade as trg  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

CELL = trg.CELL


def pack_with(h):
    r = trg.road("a", [(20, 200, 0), (120, 200, 0), (220, 200, 0), (330, 200, 0)], width=14.0)
    r["points"] = [[x, y, wp.bilinear(h, CELL, x, y) + 1.0] for x, y, _ in r["points"]]
    pk = trg.synth(h, [r])
    pk.entities["buildings"] = [{"id": "b1", "points": [[60, 60], [100, 60], [100, 100], [60, 100]]}]
    pk.entities["bridges"] = [{"id": "br1", "span": {"start": [250, 300, 100.0], "end": [320, 300, 100.0], "width_ft": 8.0}}]
    pk.entities["foliage"] = []
    old_list = pk.list
    pk.list = lambda t=None: old_list(t) if t else [e for v in pk.entities.values() for e in v]
    pk.get = lambda i: next(e for e in pk.list() if e["id"] == i)
    pk.polygon = lambda i: [p[:2] for p in pk.get(i)["points"]]
    pk.materials = {}
    return pk


class GroundTests(unittest.TestCase):
    def setUp(self):
        self.h = trg.terrain()
        self.pk = pack_with(self.h)

    def test_final_heights_match_graded_terrain(self):
        h_cf = wm.final_heights(self.pk, carve=False, road_grade={"cutfill": True})
        self.assertGreater(float(np.abs(h_cf - self.h).max()), 0.2)          # the cut/fill really changed the ground
        h_old = wp.road_conformed_heights(self.pk, self.h)
        xs = np.linspace(40, 300, 40)
        ys = np.full_like(xs, 200.0)
        zf, zo = rg.mesh_height(h_cf, CELL, xs, ys), rg.mesh_height(h_old, CELL, xs, ys)
        self.assertGreater(float(np.abs(zf - zo).max()), 0.05)               # old conform would put trees at other heights
        g = fo.Ground(self.pk.frame, h_cf, CELL)
        self.assertTrue(np.allclose(g.z(xs, ys), zf))

    def test_blocked_geometry(self):
        ko = fo.keep_out_geometry(self.pk)
        g = fo.Ground(self.pk.frame, self.h, CELL, ko)
        pts = {"road": (120, 203), "building": (80, 80), "deck": (285, 301), "free": (150, 100)}
        m = g.blocked([p[0] for p in pts.values()], [p[1] for p in pts.values()])
        self.assertEqual(list(m), [True, True, True, False])

    def test_merge_drops_blocked_trees(self):
        tmp = tempfile.mkdtemp()
        try:
            doc = fo.FoliageDoc("t", path=os.path.join(tmp, "f.json"), data={})
            lib = fm.FoliageLibrary()
            for k, (x, y) in enumerate([(120, 203), (80, 80), (285, 301), (150, 100), (200, 60)]):
                doc.items[f"i{k}"] = {"id": f"i{k}", "species": "oak", "x": x, "y": y, "z": 0, "scale": 1.0, "rot": 0.0, "variant": 0, "zone": "z", "src": "generated"}
            g = fo.Ground(self.pk.frame, self.h, CELL, fo.keep_out_geometry(self.pk))
            fdoc, rep = fo.merge_foliage(doc, lib, g, "t", os.path.join(tmp, "o"), chunk_ft=150, log=lambda *_: None)
            self.assertEqual(sorted(rep["keep_out_dropped_ids"]), ["i0", "i1", "i2"])
            self.assertEqual(rep["after"]["instances"], 2)
            self.assertEqual(len(doc.items), 5)                                # saved data untouched
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_canopy_clearance_off_the_road(self):
        from shapely.geometry import LineString
        lib = fm.FoliageLibrary()
        R = lib.crown_r_ft("oak")
        self.assertGreaterEqual(R, 8.0)
        g = fo.Ground(self.pk.frame, self.h, CELL, None, [(LineString([(0, 100), (400, 100)]), 5.0)])
        doc = fo.FoliageDoc("t", path=os.path.join(tempfile.mkdtemp(), "f.json"), data={})
        for k, (x, y) in enumerate([(50, 100 + 6), (150, 100 + 5 + R * 0.7 + 0.1), (250, 100), (300, 100 + 5 + R + 5)]):
            doc.items[f"i{k}"] = {"id": f"i{k}", "species": "oak", "x": x, "y": y, "z": 0, "scale": 1.0, "rot": 0.0, "variant": 0, "zone": "z", "src": "generated"}
        moved, dropped = fo.clear_canopies(doc, lib, g, 8.0, 0.3)
        self.assertIn("i0", moved)                                         # canopy over the bed: pushed out
        self.assertEqual(dropped, ["i2"])                                  # trunk on the centreline: too far to shift
        self.assertNotIn("i3", moved)                                      # already clear
        for i in doc.items.values():
            self.assertGreaterEqual(abs(i["y"] - 100), 5.0 + R * 0.7 - 0.01)
        doc2 = fo.FoliageDoc("t", path=os.path.join(tempfile.mkdtemp(), "f.json"), data={})
        doc2.items["a"] = {"id": "a", "species": "oak", "x": 10, "y": 106, "z": 0, "scale": 1.0, "rot": 0.0, "variant": 0, "zone": "z", "src": "generated"}
        self.assertEqual(fo.clear_canopies(doc2, lib, g, None), ([], []))     # rule off
        self.assertEqual(fo.clear_canopies(doc2, lib, fo.Ground(self.pk.frame, self.h, CELL), 8.0), ([], []))


if __name__ == "__main__":
    unittest.main()
