"""Tests for svg_raster.py (headless PNG), label_curve.py (text on path), region_draw draw options, render_world --fit.
  python illustrator/generators/test_svg_raster.py"""
import os
import sys
import tempfile
import types
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import label_curve as lcv  # noqa: E402
import region_draw as rd  # noqa: E402
import svg_raster as sr  # noqa: E402

SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="200pt" height="100pt" viewBox="0 0 200 100">
<style><![CDATA[ .wall { fill: none; stroke: #000000; stroke-width: 2; } .faint { fill:none; stroke:#ff0000; stroke-width:4; stroke-opacity:0.25; stroke-dasharray: 6 6; } ]]></style>
<g id="LINES"><path id="a" class="wall" d="M10,10 L90,10 L90,40 Z"/><path id="b" class="faint" d="M10,60 L190,60"/></g>
<g id="Labels - Hidden"><path class="wall" d="M0,95 L200,95"/></g>
<g id="LABELS"><path id="tp" d="M20,90 L100,70 L180,90" fill="none" stroke="none"/>
<text id="t1" font-size="12" text-anchor="middle" style="fill:#0000ff"><textPath href="#tp" xlink:href="#tp" startOffset="50%">Curved Street</textPath></text></g>
</svg>"""


class T(unittest.TestCase):
    def render(self, svg=SVG, **kw):
        with tempfile.TemporaryDirectory() as t:
            p, q = os.path.join(t, "a.svg"), os.path.join(t, "a.png")
            open(p, "w", encoding="utf-8").write(svg)
            sr.rasterise(p, q, **kw)
            return np.array(Image.open(q).convert("RGB")).astype(int)

    def test_lines_dash_opacity_hidden_and_textpath(self):
        a = self.render(dpi=72, ss=1, bg="#ffffff")
        self.assertEqual(a.shape[:2], (100, 200))
        self.assertLess(a[10, 50].sum(), 100)                          # black wall stroke
        row = a[60]
        pink = [(row[x] != 255).any() for x in range(10, 190)]
        self.assertTrue(any(pink) and not all(pink))                   # dashed
        self.assertGreater(row[14][1], 150)                            # 25 % red over white is light, not solid
        self.assertEqual(tuple(a[95, 100]), (255, 255, 255))           # hidden layer skipped
        blue = (a[:, :, 2] > 150) & (a[:, :, 0] < 100) & (a[:, :, 1] < 100)
        self.assertGreater(blue.sum(), 25)                             # the textPath glyphs were drawn (blue text)
        ys, xs = np.nonzero(blue)
        self.assertTrue(xs.min() > 20 and xs.max() < 180 and ys.max() < 90)

    def test_base_image_goes_under_lines(self):
        with tempfile.TemporaryDirectory() as t:
            Image.new("RGBA", (10, 10), (0, 255, 0, 255)).save(os.path.join(t, "b.png"))
            open(os.path.join(t, "a.svg"), "w").write(SVG)
            sr.rasterise(os.path.join(t, "a.svg"), os.path.join(t, "o.png"), 72, 1, "#ffffff", [(os.path.join(t, "b.png"), [0, 0, 100, 50])])
            a = np.array(Image.open(os.path.join(t, "o.png")).convert("RGB")).astype(int)
        self.assertEqual(tuple(a[30, 20]), (0, 255, 0))
        self.assertEqual(tuple(a[80, 150]), (255, 255, 255))

    def test_curved_path_only_when_bent(self):
        v = types.SimpleNamespace(margin=0.0, k=1.0, x0=0.0, y0=0.0, px=lambda p: (p[0], p[1]))
        straight = [(0, 100), (200, 100)]
        self.assertIsNone(lcv.curved_path(straight, (100, 100), 60, v))
        bent = [(0, 100), (80, 100), (120, 140), (200, 140)]
        r = lcv.curved_path(bent, (100, 120), 120, v, offset_ft=5.0)
        self.assertIsNotNone(r)
        d, turn = r
        self.assertGreater(turn, 12)
        import re
        pts = [tuple(map(float, m)) for m in re.findall(r"(-?[\d.]+),(-?[\d.]+)", d)]
        self.assertLess(pts[0][0], pts[-1][0])                         # runs left to right: upright text
        rr = lcv.curved_path(list(reversed(bent)), (100, 120), 120, v, offset_ft=5.0)
        p2 = [tuple(map(float, m)) for m in re.findall(r"(-?[\d.]+),(-?[\d.]+)", rr[0])]
        self.assertLess(p2[0][0], p2[-1][0])                           # same for the reversed centreline
        self.assertLess(pts[0][1], 100)                                # offset toward the page top (y down)

    def test_draw_opts(self):
        self.assertNotIn("lots", rd.draw_opts(None, 20))
        self.assertIn("lots", rd.draw_opts(None, 40))
        self.assertIn("lots", rd.draw_opts("lots,trees", 10))
        self.assertEqual(rd.draw_opts("none", 40), set())
        self.assertEqual(rd.draw_opts("trees", 20), {"trees"})

    def test_fit_bounds_and_nice(self):
        import render_world as rw
        m = {"place": {"id": "x", "bounds": {"width_ft": 100, "height_ft": 80}}, "buildings": [{"id": "b", "kind": "house", "geometry": {"type": "polygon", "points": [[10, 10], [30, 10], [30, 40]]}}],
             "streets": [{"id": "s", "kind": "lane", "geometry": {"type": "polyline", "points": [[5, 20], [60, 50]], "width_ft": 10}}]}
        self.assertEqual(rw.fit_bounds(m, "buildings"), [5, 10, 60, 50])
        self.assertEqual(rw.fit_bounds(m, "all"), [0.0, 0.0, 100.0, 80.0])
        self.assertEqual(rw._nice_fit(103), 120)
        self.assertEqual(rw._nice_fit(96), 100)

    def test_curved_host_mode_straight_fallback_and_sidecar_items(self):
        import label_style as lst
        import lib_svg
        st = lst.Style()
        rec = lst.Rec("str_x_label", "Labels - Streets", ["Bend Lane"], 100, 100, 50, 10, 0.0, 8.0, st, path="M10.00,90.00 L50.00,80.00 L90.00,90.00")
        for mode in ("host", "svg"):
            lst.curved_begin(mode)
            tree = lib_svg.LayerTree([("Labels - Streets", [])], 3, 3)
            lst.emit(tree, rec)
            out = os.path.join(tempfile.mkdtemp(), "t.svg")
            tree.write(out)
            svg = open(out, encoding="utf-8").read()
            if mode == "host":
                self.assertNotIn("textPath", svg)                               # Illustrator would flatten it and show a dialog
                self.assertIn("Bend Lane", svg)                                 # straight fallback is there
                self.assertEqual(len(lst.CURVED["items"]), 1)
                it = lst.CURVED["items"][0]
                self.assertEqual((it["id"], len(it["points"]), it["text"]), ("str_x_label", 3, "Bend Lane"))
            else:
                self.assertIn("textPath", svg)
                self.assertEqual(lst.CURVED["items"], [])
        lst.curved_begin("host")

    def test_panelio_fit(self):
        import panelio
        a = types.SimpleNamespace(place="bridgehollow", what="buildings", preset="town", view="town", page="17x11", fit_margin=0.0)
        r = panelio.cmd_fit(a)
        self.assertGreater(r["scale_ft_per_in"], 0)
        self.assertEqual(len(r["focus_ft"]), 2)
        b = r["bounds_ft"]
        self.assertAlmostEqual(r["focus_ft"][0], (b[0] + b[2]) / 2, delta=0.2)
        a.what = "all"
        self.assertGreaterEqual(panelio.cmd_fit(a)["scale_ft_per_in"], r["scale_ft_per_in"])


if __name__ == "__main__":
    unittest.main()
