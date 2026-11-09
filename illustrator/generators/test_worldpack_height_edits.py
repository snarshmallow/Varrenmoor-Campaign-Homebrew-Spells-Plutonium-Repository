"""Height-edit consistency in the world pack exporter (temp copy of world/bridgehollow; nothing in world/ is touched).
Cached per-vertex heights (streets' elevations_ft, ...) were graded against the unedited terrain: after a painted raise they must follow it.
  python illustrator/generators/test_worldpack_height_edits.py"""
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heightmap_paint as hp  # noqa: E402
import worldio  # noqa: E402
import worldpack as wp  # noqa: E402

TS = "2026-01-01T00:00:00+00:00"
TMP = tempfile.mkdtemp(prefix="wphe_")
WORLD = os.path.join(TMP, "world")
RAISE = 20.0


def _export(out):
    wp.export_world("bridgehollow", out, world_root=WORLD, timestamp=TS, lod=(4,), log=lambda m: None, copy_textures=False)
    with open(os.path.join(out, "entities", "roads.json"), encoding="utf-8") as f, open(os.path.join(out, "manifest.json"), encoding="utf-8") as g:
        return json.load(f), json.load(g)


def _roads(doc):
    return doc["items"]


def setUpModule():
    shutil.copytree(os.path.join(wp.REPO, "world", "bridgehollow"), os.path.join(WORLD, "bridgehollow"),
                    ignore=shutil.ignore_patterns("panel_state.json", "patch_preview", "export"))


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class HeightEditRoads(unittest.TestCase):
    def test_roads_follow_edits_and_unchanged_without(self):
        base_doc, base_man = _export(os.path.join(TMP, "a"))
        self.assertNotIn("height_edits", base_man["terrain"])
        self.assertNotIn("height_edits", base_man["sources"])
        base_again, _ = _export(os.path.join(TMP, "a2"))
        self.assertEqual(base_doc, base_again)
        roads = _roads(base_doc)
        r = next(x for x in roads if x["bridge"] is None and len(x["points"]) >= 3 and not x["fords"])
        h, meta = worldio.load_terrain("bridgehollow", root=WORLD, edits=False)
        cell = float(meta["cell_ft"])
        mx, my = np.mean([p[0] for p in r["points"]]), np.mean([p[1] for p in r["points"]])
        d = np.zeros_like(h, np.float32)
        ii, jj = np.mgrid[0:h.shape[0], 0:h.shape[1]]
        dist = np.hypot(jj * cell - mx, ii * cell - my)
        d[dist < 60] = RAISE
        hp.save_layer(os.path.join(WORLD, "bridgehollow"), d, {"strokes": [{"tool": "test"}]}, cell)
        edoc, eman = _export(os.path.join(TMP, "b"))
        te = eman["terrain"]["height_edits"]
        self.assertGreater(te["strokes"], 0)
        self.assertTrue(te["hash"])
        self.assertTrue(eman["sources"]["height_edits"]["applied"])
        h2, _ = worldio.load_terrain("bridgehollow", root=WORLD)
        r2 = next(x for x in _roads(edoc) if x["id"] == r["id"])
        raised = 0
        for p0, p1 in zip(r["points"], r2["points"]):
            dz = float(wp.bilinear(d, cell, p0[0], p0[1]))
            self.assertAlmostEqual(p1[2] - p0[2], dz, delta=0.01)       # cached grade carried over the edit delta (grading preserved)
            raised += dz > 1
        self.assertGreater(raised, 0)
        # roads away from the edit are untouched
        for a, b in zip(_roads(base_doc), _roads(edoc)):
            if a["id"] != r["id"] and all(wp.bilinear(d, cell, p[0], p[1]) == 0 for p in a["points"]):
                self.assertEqual(a["points"], b["points"])

    def test_stale_hash_trusted_cache(self):
        """_edit_shift: delta of edited vs unedited terrain; None when nothing changed / no baseline."""
        h = np.zeros((5, 5), np.float32)
        h0 = h - 10
        sh = wp._edit_shift(h, h0, 10.0)
        self.assertAlmostEqual(sh(5, 5), 10.0)
        self.assertIsNone(wp._edit_shift(h, h.copy(), 10.0))
        self.assertIsNone(wp._edit_shift(h, None, 10.0))


if __name__ == "__main__":
    unittest.main()
