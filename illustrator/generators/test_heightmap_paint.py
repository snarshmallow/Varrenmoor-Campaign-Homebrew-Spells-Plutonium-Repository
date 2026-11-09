"""Brush maths, edit-layer overlay (worldio hook), undo, CLI.   python -m unittest illustrator/generators/test_heightmap_paint.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import heightmap_paint as hp  # noqa: E402
import worldio  # noqa: E402

CELL = 2.0


def flat(n=81, v=100.0):
    return np.full((n, n), v, np.float64)


def stroke(tool, pts, **k):
    d = {"tool": tool, "points": pts, "radius_ft": 20, "strength": 1.0, "falloff": "linear", "hardness": 0.0}
    d.update(k)
    return d


class Brushes(unittest.TestCase):
    def test_falloff_curves(self):
        for fo in ("smooth", "linear", "sharp", "round"):
            w = hp.falloff_weight(np.array([0, 5, 10, 20, 30]), 20, 0.0, fo)
            self.assertAlmostEqual(w[0], 1.0)
            self.assertAlmostEqual(w[3], 0.0)
            self.assertEqual(w[4], 0.0)
            self.assertTrue(np.all(np.diff(w) <= 1e-12))
        w = hp.falloff_weight(np.array([0, 10, 10.1, 20]), 20, 0.5, "linear")       # plateau out to half the radius
        self.assertEqual(w[1], 1.0)
        self.assertLess(w[2], 1.0)
        self.assertEqual(hp.falloff_weight(np.array([19.9, 20.1]), 20, 0, "constant").tolist(), [1.0, 0.0])

    def test_raise_lower(self):
        h = flat()
        hp.apply_stroke(h, CELL, stroke("raise", [[80, 80]], rate_ft=3))
        self.assertAlmostEqual(h[40, 40], 103.0, places=3)
        self.assertEqual(h[0, 0], 100.0)
        self.assertGreater(h[40, 40], h[40, 45])
        hp.apply_stroke(h, CELL, stroke("lower", [[80, 80]], rate_ft=3))
        self.assertTrue(np.allclose(h, 100.0))

    def test_strength_scales(self):
        a, b = flat(), flat()
        hp.apply_stroke(a, CELL, stroke("raise", [[80, 80]], strength=1.0))
        hp.apply_stroke(b, CELL, stroke("raise", [[80, 80]], strength=0.25))
        self.assertAlmostEqual((b[40, 40] - 100) * 4, a[40, 40] - 100, places=6)

    def test_smooth_reduces_roughness(self):
        rng = np.random.RandomState(1)
        h = flat() + rng.rand(81, 81) * 6
        far = h[0:10, 0:10].copy()
        before = np.abs(np.diff(h[30:50, 30:50], axis=1)).mean()
        hp.apply_stroke(h, CELL, stroke("smooth", [[70, 80], [90, 80]], radius_ft=30, falloff="constant"))
        self.assertLess(np.abs(np.diff(h[30:50, 30:50], axis=1)).mean(), before * 0.5)
        self.assertTrue(np.array_equal(h[0:10, 0:10], far))

    def test_flatten_and_set(self):
        h = flat() + np.linspace(0, 20, 81)[None, :]
        hp.apply_stroke(h, CELL, stroke("flatten", [[80, 80]], radius_ft=25, falloff="constant", height_ft=105))
        self.assertTrue(np.allclose(h[38:43, 38:43], 105.0))
        g = flat()
        hp.apply_stroke(g, CELL, stroke("set", [[80, 80]], radius_ft=10, falloff="constant", height_ft=130, strength=0.5))
        self.assertAlmostEqual(g[40, 40], 115.0)
        with self.assertRaises(ValueError):
            hp.validate_stroke(stroke("set", [[1, 1]]))
        h2 = flat() + np.linspace(0, 20, 81)[None, :]       # flatten with no height: level of the first point
        v0 = h2[40, 40]
        hp.apply_stroke(h2, CELL, stroke("flatten", [[80, 80], [100, 80]], radius_ft=6, falloff="constant"))
        self.assertAlmostEqual(h2[40, 44], v0, places=3)

    def test_noise_is_deterministic_and_bounded(self):
        a, b = flat(), flat()
        s = stroke("noise", [[60, 80], [100, 80]], rate_ft=4, seed=5, falloff="constant")
        hp.apply_stroke(a, CELL, s)
        hp.apply_stroke(b, CELL, s)
        self.assertTrue(np.array_equal(a, b))
        self.assertGreater(np.abs(a - 100).max(), 0.5)
        self.assertLessEqual(np.abs(a - 100).max(), 4.0 + 1e-9)
        self.assertLess(abs((a - 100)[a != 100].mean()), 1.5)
        c = flat()
        hp.apply_stroke(c, CELL, dict(s, seed=6))
        self.assertFalse(np.array_equal(a, c))

    def test_ridge_valley(self):
        h = flat()
        hp.apply_stroke(h, CELL, stroke("ridge", [[40, 80], [120, 80]], radius_ft=14, height_ft=12))
        self.assertAlmostEqual(h[40, 40], 112.0, places=3)
        self.assertGreater(h[40, 40], h[44, 40])
        self.assertEqual(h[60, 40], 100.0)
        hp.apply_stroke(h, CELL, stroke("valley", [[40, 80], [120, 80]], radius_ft=14, height_ft=12))
        self.assertTrue(np.allclose(h, 100.0))
        g = flat()      # a path crossing itself does not stack (one field per stroke)
        hp.apply_stroke(g, CELL, stroke("ridge", [[40, 80], [120, 80], [120, 82], [40, 82], [40, 80]], radius_ft=10, height_ft=10))
        self.assertLessEqual(g.max(), 110.0 + 1e-9)

    def test_river_carves_monotone_bed(self):
        h = flat() + np.linspace(30, 0, 81)[None, :] + np.sin(np.linspace(0, 9, 81))[None, :] * 3     # slopes east with bumps
        h0 = h.copy()
        hp.apply_stroke(h, CELL, stroke("river", [[10, 80], [150, 80]], radius_ft=16, depth_ft=5, hardness=0.5, falloff="smooth"))
        self.assertTrue(np.all(h <= h0 + 1e-9))
        bed = h[40, 8:75]
        self.assertLessEqual(np.diff(np.minimum.accumulate(bed)).max(), 0.0)
        self.assertGreater((h0[40, 8:75] - h[40, 8:75]).min(), 0.0)           # every cell on the line was cut
        self.assertGreater((h0[40, 8:75] - h[40, 8:75]).mean(), 3.0)
        self.assertEqual(h[0, 40], h0[0, 40])                                  # far away untouched
        self.assertGreater(h[46, 40], h[40, 40])                               # banks rise away from the bed

    def test_validate(self):
        for bad in ({"tool": "nope", "points": [[0, 0]]}, {"tool": "raise", "points": []}, {"tool": "raise", "points": [[0, "a"]]},
                    {"tool": "raise", "points": [[0, 0]], "radius_ft": 0}, {"tool": "raise", "points": [[0, 0]], "falloff": "x"}):
            with self.assertRaises(ValueError):
                hp.validate_stroke(bad)
        s = hp.validate_stroke({"tool": "raise", "points": [[0, 0]], "strength": 5, "hardness": -1})
        self.assertEqual((s["strength"], s["hardness"]), (1.0, 0.0))

    def test_edges_clip(self):
        h = flat(21)
        hp.apply_stroke(h, CELL, stroke("raise", [[-5, -5], [200, 200]], radius_ft=30))      # partly / fully off the grid: no crash
        self.assertGreater(h[0, 0], 100)
        hp.apply_stroke(h, CELL, stroke("raise", [[1000, 1000]], radius_ft=5))


class FakePlace(unittest.TestCase):
    """A throw-away world root with a small base terrain; worldio and the layer code use it through root=."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "world")
        T = os.path.join(self.root, "pl", "terrain")
        os.makedirs(T)
        self.base = (100 + np.add.outer(np.linspace(0, 10, 61), np.linspace(0, 20, 71))).astype(np.float32)
        np.save(os.path.join(T, "heightmap.npy"), self.base)
        with open(os.path.join(T, "terrain_meta.json"), "w") as f:
            json.dump({"cell_ft": CELL, "nx": 71, "ny": 61, "elev_min": float(self.base.min()), "elev_max": float(self.base.max()), "size_ft": [140, 120], "origin_ft": [0, 0]}, f)
        self.work = os.path.join(self.tmp.name, "work")
        os.environ.pop("VB_HEIGHT_EDITS", None)

    def tearDown(self):
        self.tmp.cleanup()

    def load(self, **k):
        return worldio.load_terrain("pl", root=self.root, **k)

    def test_no_layer_changes_nothing(self):
        h, m = self.load()
        self.assertTrue(np.array_equal(h, self.base))
        self.assertNotIn("height_edits", m)

    def test_working_copy_is_not_seen_until_saved(self):
        r = hp.apply_strokes("pl", [stroke("raise", [[70, 60]], rate_ft=5, radius_ft=15)], "append", self.root, self.work)
        self.assertTrue(r["ok"])
        self.assertGreater(r["summary"]["max_raise_ft"], 4.9)
        self.assertTrue(np.array_equal(self.load()[0], self.base))                 # saved layer still absent
        hp.save("pl", self.root, self.work)
        h, m = self.load()
        self.assertAlmostEqual(float(h[30, 35] - self.base[30, 35]), 5.0, places=3)
        self.assertEqual(m["height_edits"]["strokes"], 1)
        self.assertAlmostEqual(m["elev_max"], float(h.max()), places=3)
        self.assertTrue(np.array_equal(self.load(edits=False)[0], self.base))      # opt-out argument
        os.environ["VB_HEIGHT_EDITS"] = "0"
        try:
            self.assertTrue(np.array_equal(self.load()[0], self.base))             # opt-out env
        finally:
            os.environ.pop("VB_HEIGHT_EDITS")
        self.assertTrue(np.array_equal(np.load(os.path.join(self.root, "pl", "terrain", "heightmap.npy")), self.base))   # the generated file is never touched

    def test_edits_survive_regeneration(self):
        hp.apply_strokes("pl", [stroke("raise", [[70, 60]], rate_ft=5, radius_ft=15)], "append", self.root, self.work)
        hp.save("pl", self.root, self.work)
        np.save(os.path.join(self.root, "pl", "terrain", "heightmap.npy"), (self.base + 7).astype(np.float32))     # "regenerated" terrain
        h, _ = self.load()
        self.assertAlmostEqual(float(h[30, 35]), float(self.base[30, 35]) + 7 + 5, places=3)

    def test_replay_reruns_recipe_on_new_base(self):
        s = stroke("flatten", [[70, 60]], radius_ft=10, falloff="constant", height_ft=150)
        hp.apply_strokes("pl", [s], "append", self.root, self.work)
        np.save(os.path.join(self.root, "pl", "terrain", "heightmap.npy"), (self.base + 7).astype(np.float32))
        hp.apply_strokes("pl", [], "replay", self.root, self.work)
        hp.save("pl", self.root, self.work)
        self.assertAlmostEqual(float(self.load()[0][30, 35]), 150.0, places=3)     # replay reaches 150 on the new base too

    def test_append_builds_on_previous_and_undo_replays(self):
        s1 = stroke("raise", [[70, 60]], rate_ft=5, radius_ft=15)
        s2 = stroke("flatten", [[20, 20], [60, 20]], radius_ft=10, falloff="constant", height_ft=90)
        hp.apply_strokes("pl", [s1], "append", self.root, self.work)
        r = hp.apply_strokes("pl", [s2], "append", self.root, self.work)
        self.assertEqual(r["strokes_total"], 2)
        d2, info = hp.load_layer(self.work)
        self.assertEqual(len(info["strokes"]), 2)
        r = hp.apply_strokes("pl", [], "undo-last", self.root, self.work)
        self.assertEqual(r["strokes_total"], 1)
        d1, _ = hp.load_layer(self.work)
        only1 = hp.run_strokes(self.base, CELL, None, [hp.validate_stroke(s1)])
        self.assertTrue(np.allclose(d1, only1, atol=1e-5))
        self.assertFalse(np.allclose(d1, d2))
        self.assertTrue(hp.stats("pl", self.root, self.work)["unsaved"])
        hp.apply_strokes("pl", [], "undo-last", self.root, self.work)
        self.assertEqual(hp.summarize(hp.load_layer(self.work)[0])["changed_cells"], 0)
        self.assertFalse(hp.stats("pl", self.root, self.work)["unsaved"])   # back to zero strokes with nothing saved reads clean
        with self.assertRaises(ValueError):
            hp.apply_strokes("pl", [], "undo-last", self.root, self.work)

    def test_reset_and_discard(self):
        hp.apply_strokes("pl", [stroke("raise", [[70, 60]])], "append", self.root, self.work)
        hp.save("pl", self.root, self.work)
        hp.apply_strokes("pl", [stroke("lower", [[70, 60]])], "append", self.root, self.work)
        self.assertTrue(hp.stats("pl", self.root, self.work)["unsaved"])
        hp.discard("pl", self.root, self.work)
        self.assertFalse(os.path.exists(hp.layer_paths(self.work)[0]))
        self.assertGreater(hp.stats("pl", self.root, self.work)["summary"]["changed_cells"], 0)    # falls back to the saved layer
        hp.reset("pl", self.root, self.work, "both")
        self.assertTrue(np.array_equal(self.load()[0], self.base))
        self.assertFalse(os.path.exists(hp.layer_paths(os.path.join(self.root, "pl"))[1]))

    def test_resample_when_shape_differs(self):
        hp.apply_strokes("pl", [stroke("raise", [[70, 60]], rate_ft=5, radius_ft=15)], "append", self.root, self.work)
        hp.save("pl", self.root, self.work)
        big = np.kron(self.base, np.ones((2, 2), np.float32))
        np.save(os.path.join(self.root, "pl", "terrain", "heightmap.npy"), big)
        h, m = self.load()
        self.assertEqual(h.shape, big.shape)
        self.assertIn("height_edits_warning", m)
        self.assertGreater(float((h - big).max()), 3.0)

    def test_save_empty_layer_removes_saved(self):
        hp.apply_strokes("pl", [stroke("raise", [[70, 60]])], "append", self.root, self.work)
        hp.save("pl", self.root, self.work)
        hp.apply_strokes("pl", [], "undo-last", self.root, self.work)
        r = hp.save("pl", self.root, self.work)
        self.assertFalse(r["saved"])
        self.assertFalse(os.path.exists(hp.layer_paths(os.path.join(self.root, "pl"))[0]))

    def test_preview_exports(self):
        hp.apply_strokes("pl", [stroke("raise", [[70, 60]], rate_ft=8, radius_ft=15)], "append", self.root, self.work)
        png, bd = os.path.join(self.tmp.name, "p.png"), os.path.join(self.tmp.name, "bin")
        r = hp.export_preview("pl", self.root, self.work, max_px=32, contour_ft=2, png=png, bin_dir=bd, show_delta=True)
        self.assertEqual(r["factor"], 3)
        self.assertEqual((r["pw"], r["ph"]), (24, 21))
        self.assertTrue(os.path.getsize(png) > 100)
        arr = np.fromfile(os.path.join(bd, "preview_h.bin"), "<f4")
        self.assertEqual(arr.size, 24 * 21)
        self.assertLessEqual(float(arr.max()), r["elev_max"] + 1e-4)   # stride sampling can miss the single highest node
        self.assertTrue(r["edited"])
        rb = hp.export_preview("pl", self.root, self.work, layer="base")
        self.assertFalse(rb["edited"])
        self.assertLessEqual(rb["elev_max"], r["elev_max"])

    def test_cli(self):
        sj = os.path.join(self.tmp.name, "s.json")
        with open(sj, "w") as f:
            json.dump({"strokes": [stroke("raise", [[70, 60]], rate_ft=2)]}, f)
        base = [sys.executable, os.path.join(HERE, "heightmap_paint.py")]
        common = ["--place", "pl", "--world-root", self.root, "--work-dir", self.work]

        def run(*a):
            p = subprocess.run(base + list(a) + common, capture_output=True, text=True)
            return p.returncode, json.loads(p.stdout)
        rc, o = run("apply-strokes", "--strokes", sj)
        self.assertEqual((rc, o["ok"], o["strokes_total"]), (0, True, 1))
        rc, o = run("stats")
        self.assertTrue(o["unsaved"] and o["strokes"] == 1)
        rc, o = run("save")
        self.assertTrue(o["saved"])
        rc, o = run("export-preview", "--max-px", "16", "--layer", "saved")
        self.assertTrue(o["ok"])
        rc, o = run("reset")
        self.assertEqual(rc, 0)
        rc, o = run("apply-strokes", "--mode", "undo-last")
        self.assertEqual((rc, o["ok"]), (1, False))


class RoadCheck(unittest.TestCase):
    """check / conform-roads: which roads an edit layer endangers, and the undoable stroke that flattens the layer across them."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "world")
        d = os.path.join(self.root, "pl")
        os.makedirs(os.path.join(d, "terrain"))
        os.makedirs(os.path.join(d, "buildings"))
        self.base = (100.0 + 0.02 * np.add.outer(np.arange(81.0), np.arange(81.0))).astype(np.float32)
        np.save(os.path.join(d, "terrain", "heightmap.npy"), self.base)
        with open(os.path.join(d, "terrain", "terrain_meta.json"), "w") as f:
            json.dump({"cell_ft": CELL, "nx": 81, "ny": 81, "origin_ft": [0.0, 0.0], "elev_min": 100.0, "elev_max": 200.0, "relief_ft": 100.0}, f)
        with open(os.path.join(d, "streets.json"), "w") as f:      # one road east-west at y=60, one far away at y=140
            json.dump({"streets": [{"id": "r1", "name": "Near", "geometry": {"points": [[20, 60], [80, 60], [140, 60]], "width_ft": 16}},
                                   {"id": "r2", "name": "Far", "geometry": {"points": [[20, 140], [140, 140]], "width_ft": 16}}]}, f)
        with open(os.path.join(d, "buildings", "b1.json"), "w") as f:
            json.dump({"id": "b1", "geometry": {"points": [[60, 100], [75, 100], [75, 112], [60, 112]]}}, f)
        self.work = os.path.join(self.tmp.name, "work")

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self):
        return hp.check("pl", self.root, self.work)

    def test_no_edits_no_warnings(self):
        r = self.run_check()
        self.assertEqual((r["ok"], r["warnings"], r["roads"], r["flagged_roads"]), (True, [], [], []))

    def test_edge_raise_is_flagged_but_uniform_shift_is_not(self):
        hp.apply_strokes("pl", [stroke("raise", [[80, 52]], rate_ft=12, radius_ft=8)], "append", self.root, self.work)      # raises the north edge only
        r = self.run_check()
        self.assertEqual(r["flagged_roads"], ["r1"])
        road = next(x for x in r["roads"] if x["id"] == "r1")
        self.assertGreater(road["edge_delta_diff_ft"], 3.0)
        self.assertGreater(road["cross_slope_after_deg"], road["cross_slope_before_deg"] + 5)
        self.assertIn("Road r1", r["warnings"][0])
        self.assertIn("skirt", r["warnings"][0])
        hp.reset("pl", self.root, self.work, "work")
        hp.apply_strokes("pl", [stroke("raise", [[80, 60], [80, 60]], rate_ft=12, radius_ft=60, falloff="constant")], "append", self.root, self.work)   # all of road r1 up the same amount
        r = self.run_check()
        self.assertEqual(r["flagged_roads"], [])
        self.assertGreater(next(x for x in r["roads"] if x["id"] == "r1")["mean_shift_ft"], 10.0)

    def test_building_tilt_is_reported(self):
        hp.apply_strokes("pl", [stroke("raise", [[75, 106]], rate_ft=8, radius_ft=10)], "append", self.root, self.work)
        r = self.run_check()
        self.assertTrue(any(b["id"] == "b1" for b in r["buildings"]))
        self.assertTrue(any(w.startswith("Building b1") for w in r["warnings"]))

    def test_conform_roads_flattens_the_layer_across_the_road(self):
        hp.apply_strokes("pl", [stroke("raise", [[80, 52]], rate_ft=12, radius_ft=8)], "append", self.root, self.work)
        r = hp.conform_roads("pl", "flagged", self.root, self.work)
        self.assertEqual((r["ok"], r["conformed"], r["strokes_total"]), (True, ["r1"], 2))
        after = self.run_check()
        self.assertEqual(after["flagged_roads"], [])
        road = next(x for x in after["roads"] if x["id"] == "r1")
        self.assertLess(road["edge_delta_diff_ft"], 1.5)
        d, info = hp.load_layer(self.work)
        far = np.abs(d[int(140 / CELL) - 3: int(140 / CELL) + 4]).max()               # the far road is untouched
        self.assertEqual(far, 0.0)
        self.assertEqual(info["strokes"][-1]["tool"], "conform-roads")
        r = hp.apply_strokes("pl", [], "undo-last", self.root, self.work)               # undoable, replayable
        self.assertEqual(self.run_check()["flagged_roads"], ["r1"])
        r = hp.apply_strokes("pl", [], "replay", self.root, self.work)
        self.assertEqual(r["strokes_total"], 1)

    def test_conform_with_nothing_flagged_is_a_no_op(self):
        r = hp.conform_roads("pl", "flagged", self.root, self.work)
        self.assertEqual((r["ok"], r["conformed"]), (True, []))
        self.assertFalse(os.path.exists(hp.layer_paths(self.work)[0]))

    def test_stroke_validation(self):
        with self.assertRaises(ValueError):
            hp.validate_stroke({"tool": "conform-roads", "roads": []})
        with self.assertRaises(ValueError):
            hp.validate_stroke({"tool": "conform-roads", "roads": [{"id": "x", "points": [[1, 2]]}]})

    def test_cli(self):
        base = [sys.executable, os.path.join(HERE, "heightmap_paint.py")]
        common = ["--place", "pl", "--world-root", self.root, "--work-dir", self.work]
        sj = os.path.join(self.tmp.name, "s.json")
        with open(sj, "w") as f:
            json.dump({"strokes": [stroke("raise", [[80, 52]], rate_ft=12, radius_ft=8)]}, f)

        def run(*a):
            p = subprocess.run(base + list(a) + common, capture_output=True, text=True)
            return p.returncode, json.loads(p.stdout)
        run("apply-strokes", "--strokes", sj)
        rc, o = run("check")
        self.assertEqual((rc, o["flagged_roads"]), (0, ["r1"]))
        rc, o = run("conform-roads", "--roads", "r1", "--falloff-ft", "10")
        self.assertEqual((rc, o["conformed"]), (0, ["r1"]))
        self.assertEqual(run("check")[1]["flagged_roads"], [])


REAL = "bridgehollow__dyers_walk_local"


@unittest.skipUnless(os.path.exists(os.path.join(worldio.REPO, "world", REAL, "terrain", "heightmap.npy")), "Dyers Walk terrain missing")
class ConformJunction(unittest.TestCase):
    """Two roads meeting in a T: conforming one must not move the ground under the other."""
    def setUp(self):
        n = 121
        Y, X = np.mgrid[0:n, 0:n] * CELL
        self.h0 = 100.0 + 0.05 * X + 3.0 * np.sin(X / 25.0)                 # gentle ground, bumpy along x
        self.main = {"id": "m", "points": [[20.0, 120.0], [220.0, 120.0]], "width_ft": 14.0}
        self.side = {"id": "s", "points": [[120.0, 120.0], [120.0, 20.0]], "width_ft": 12.0}
        self.h = self.h0.copy()
        hp.apply_stroke(self.h, CELL, stroke("raise", [[60, 120], [90, 120]], radius_ft=14, rate_ft=6.0))

    def _run(self, protect):
        h = self.h.copy()
        st = {"tool": "conform-roads", "roads": [self.main], "protect": [self.side] if protect else []}
        hp.apply_stroke(h, CELL, st)
        return h

    def test_protected_neighbour_keeps_its_ground(self):
        yy, xx = np.mgrid[0:self.h.shape[0], 0:self.h.shape[1]] * CELL
        foot = (np.abs(xx - 120.0) <= 6.0) & (yy <= 105.0) & (yy >= 25.0)       # the side road's footprint clear of the main road's own strip
        raw, prot = self._run(False), self._run(True)
        self.assertGreater(np.abs(raw - self.h)[foot].max(), 0.2)               # without protection the blend runs into the side road ...
        self.assertLess(np.abs(prot - self.h)[foot].max(), 1e-6)                # ... with it the side road's ground is untouched

    def test_conformed_road_is_still_levelled(self):
        prot = self._run(True)
        yy, xx = np.mgrid[0:self.h.shape[0], 0:self.h.shape[1]] * CELL
        cross = prot[(np.abs(yy - 120.0) <= 6.0) & (np.abs(xx - 80.0) < 1.0)]
        self.assertLess(cross.max() - cross.min(), 0.05)

    def test_deterministic_and_validate_keeps_protect(self):
        a, b = self._run(True), self._run(True)
        self.assertTrue(np.array_equal(a, b))
        v = hp.validate_stroke({"tool": "conform-roads", "roads": [self.main], "protect": [self.side, {"id": "bad", "points": [[1, 2]]}]})
        self.assertEqual([x["id"] for x in v["protect"]], ["s"])

    def test_neighbours_to_protect_picks_nearby_roads_only(self):
        far = {"id": "far", "points": [[400.0, 400.0], [450.0, 400.0]], "width_ft": 10.0}
        got = hp.neighbours_to_protect([self.main, self.side, far], [self.main])
        self.assertEqual([x["id"] for x in got], ["s"])


class RealPlace(unittest.TestCase):
    def test_real_place_working_layer_only(self):
        base, meta = hp.base_terrain(REAL)
        with tempfile.TemporaryDirectory() as w:
            r = hp.apply_strokes(REAL, [stroke("raise", [[100, 100], [150, 120]], radius_ft=20, rate_ft=3)], "append", None, w)
            self.assertTrue(r["ok"])
            self.assertEqual(hp.stats(REAL, None, w)["shape"], list(base.shape))
            if not os.path.exists(hp.layer_paths(worldio.world_dir(REAL))[0]):     # nothing was written into the world folder
                self.assertTrue(np.array_equal(worldio.load_terrain(REAL)[0], base))


if __name__ == "__main__":
    unittest.main()
