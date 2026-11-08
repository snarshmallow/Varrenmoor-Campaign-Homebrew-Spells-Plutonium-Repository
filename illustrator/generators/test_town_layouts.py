"""Layout templates (python test_town_layouts.py): radial market town and linear river village are different street networks, not parameter biases.
Creates tiny draft places under world/zz_lay_* and removes them."""
import json
import math
import os
import shutil
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import place_create as pc  # noqa: E402
import place_text as ptx  # noqa: E402
import town_layouts as tl  # noqa: E402


def make(lay, seed=5):
    spec = {"id": f"zz_lay_{lay}", "name": "Test", "culture": "english", "terrain": {"recipe": "valley", "rivers": 1}, "town": {"population": 700, "layout": lay}, "seed": seed}
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        r = pc.create(spec, force=True, draft=True)
    d = r["dir"]
    st = json.load(open(os.path.join(d, "streets.json"), encoding="utf-8"))["streets"]
    bl = [json.load(open(os.path.join(d, "buildings", f), encoding="utf-8")) for f in os.listdir(os.path.join(d, "buildings"))]
    centre = np.array(json.load(open(os.path.join(d, "town_params.json"), encoding="utf-8"))["ring_spec"]["centre"], float)
    return d, st, bl, centre


class Templates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = {lay: make(lay) for lay in ("organic", "radial", "linear")}

    @classmethod
    def tearDownClass(cls):
        for d, *_ in cls.data.values():
            shutil.rmtree(d, ignore_errors=True)

    def test_templates_are_selected_by_layout(self):
        self.assertEqual(pc.LAYOUT_STREETS["radial"]["streets"]["template"], "radial_market")
        self.assertEqual(pc.LAYOUT_STREETS["linear"]["streets"]["template"], "linear_river")
        self.assertNotIn("template", pc.LAYOUT_STREETS["organic"]["streets"])
        self.assertEqual(set(tl.TEMPLATES), {"radial_market", "linear_river"})
        with self.assertRaises(ValueError):
            tl.generate("nope", None)

    def test_radial_has_spokes_and_a_ring(self):
        d, st, bl, c = self.data["radial"]
        self.assertTrue(bl)
        near = [s for s in st if np.min(np.hypot(*(np.array(s["geometry"]["points"]) - c).T)) < 110]
        self.assertGreaterEqual(len(near), 3)                                                  # streets converge on the centre
        spans = []
        for s in st:
            P = np.array(s["geometry"]["points"]) - c
            ang = np.unwrap(np.arctan2(P[:, 1], P[:, 0]))
            r = np.hypot(*P.T)
            if len(P) > 6 and r.std() < 0.25 * r.mean():                                         # a ring lane: nearly constant radius
                spans.append(float(ang.max() - ang.min()))
        self.assertTrue(spans and max(spans) > math.radians(150), spans)                      # winds around the centre

    def test_linear_is_elongated_along_its_high_street(self):
        _, _, bl_l, _ = self.data["linear"]
        _, _, bl_o, _ = self.data["organic"]

        def aniso(bl):
            P = np.array([np.mean(b["geometry"]["points"], axis=0) for b in bl if b.get("geometry", {}).get("points")])
            ev = np.linalg.eigvalsh(np.cov(P.T))
            return float(np.sqrt(ev[1] / ev[0]))
        self.assertGreater(aniso(bl_l), aniso(bl_o) + 0.15)
        d, st, bl, c = self.data["linear"]
        par = 0
        main = max(st, key=lambda s: s["geometry"].get("width_ft", 0))
        self.assertGreaterEqual(len(st), 8)                                                    # high street + back lanes + cross lanes

    def test_layouts_differ_and_are_deterministic(self):
        a = json.dumps([s["geometry"]["points"] for s in self.data["radial"][1]])
        b = json.dumps([s["geometry"]["points"] for s in self.data["linear"][1]])
        c = json.dumps([s["geometry"]["points"] for s in self.data["organic"][1]])
        self.assertEqual(len({a, b, c}), 3)
        d2, st2, _, _ = make("radial")
        self.assertEqual(json.dumps([s["geometry"]["points"] for s in st2]), a)


class Parser(unittest.TestCase):
    def test_keywords_and_numbers(self):
        s, _ = ptx.parse("a market town of 1.2k people on a river")
        self.assertEqual((s["town"]["population"], s["town"]["layout"], s["town"].get("central_feature")), (1200, "radial", "market"))
        s, _ = ptx.parse("a river village strung along the river, five hundred souls")
        self.assertEqual((s["town"]["population"], s["town"]["layout"]), (500, "linear"))
        s, _ = ptx.parse("small market town")
        self.assertEqual((s["town"]["population"], s["town"]["layout"]), (700, "radial"))
        s, _ = ptx.parse("crossroads hamlet with two thousand people")
        self.assertEqual((s["town"]["population"], s["town"]["layout"]), (2000, "radial"))
        s, _ = ptx.parse("walled coastal town of 800 people with a big river, Danish style, hilly")
        self.assertEqual((s["town"]["population"], s["town"]["layout"]), (800, "walled"))
        for t in ("a market town of 1.2k people on a river", "a river village", "crossroads town"):
            sp, _ = ptx.parse(t)
            e, _ = pc.validate(sp)
            self.assertFalse(e, (t, e))


if __name__ == "__main__":
    unittest.main()
