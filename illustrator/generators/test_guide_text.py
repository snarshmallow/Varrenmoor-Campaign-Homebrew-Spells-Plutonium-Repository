"""Draw-grid option (grid_show / --no-grid) and the map text blocks (title, notes, key) wrapped to the map width and placed outside the map.
  python illustrator/generators/test_guide_text.py"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import redirect_stdout

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_text as gt  # noqa: E402
import render_world as R  # noqa: E402
import viewcfg  # noqa: E402
import label_declutter as D  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"


def render(view, out, cfg_over=None, preset="handout"):
    pre = D.preset(preset)
    model = R.load_place("bridgehollow")
    with redirect_stdout(io.StringIO()):
        R.render(model, view, out, None, cfg_over or {"scale": 200}, {**pre["label_offset"]}, [pre["label_style"]], D.merge(pre["declutter"]))
    root = ET.parse(out).getroot()
    layers = {e.get("id"): e for e in root.iter(NS + "g") if e.get("id")}
    return root, layers


def texts(layer):
    out = []
    for e in layer.iter(NS + "text"):
        out.append((e.get("id"), float(e.get("x")), float(e.get("y")), float(e.get("font-size")), (e.text or ""),
                    e.get("font-weight") == "bold" or "bold" in (e.get("style") or "")))
    return out


def page_size(root):
    return (float(re.match(r"[\d.]+", root.get("width")).group(0)), float(re.match(r"[\d.]+", root.get("height")).group(0)))


class WrapTests(unittest.TestCase):
    def test_wrap_fits_width_and_keeps_words(self):
        s = "The quick brown fox jumps over the lazy dog " * 8
        lines = gt.wrap(s, 9, 200)
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(gt.text_w(ln, 9) <= 200 for ln in lines))
        self.assertEqual(" ".join(lines).split(), s.split())
        long_word = gt.wrap("X" * 200, 9, 100)                    # an over-long word is split, never overflows
        self.assertTrue(all(gt.text_w(ln, 9) <= 100 for ln in long_word))

    def test_top_block_shrinks_into_the_margin_and_reports_need(self):
        paras = [("a", "word " * 150, 11, True), ("b", "note", 7, False)]
        lines, need = gt.top_block(paras, 700, 1.0, avail_pt=36)
        self.assertTrue(all(gt.text_w(t, sz, b) <= 700 for _, t, sz, b, _y in lines))
        _, need_big = gt.top_block(paras, 700, 1.0, avail_pt=None)
        self.assertGreater(need_big, 36)                          # without shrinking it would not fit: render grows the margin instead
        _, need_s = gt.top_block([("t", "Title", 11, True)], 700, 1.0, avail_pt=36)
        self.assertLess(need_s, 36)

    def test_size_factor_scales_with_page_not_map(self):
        self.assertEqual(gt.size_factor(17, 11), 1.0)
        self.assertEqual(gt.size_factor(8.5, 5.5), 1.0)
        self.assertAlmostEqual(gt.size_factor(34, 22), 2.0)

    def test_key_band_columns_wrap_inside_width(self):
        ents = [(i, "A rather long numbered callout name number %d with a long suffix to force wrapping" % i) for i in range(1, 30)]
        rows, w, h = gt.key_band(ents, 7, 500, "Key")
        self.assertLessEqual(w, 500 + 1e-6)
        for dx, dy, t, bold in rows:
            self.assertLessEqual(dx + gt.text_w(t, 7, bold), 500 + 2, t)
            self.assertLessEqual(dy, h)


class ViewCfgTests(unittest.TestCase):
    def test_default_shown_and_override(self):
        self.assertTrue(viewcfg.load("bridgehollow", "town")["grid_show"])
        self.assertFalse(viewcfg.load("bridgehollow", "town", grid_show=False)["grid_show"])
        self.assertTrue(viewcfg.load("bridgehollow", "town", grid_show=None)["grid_show"])


class RenderTests(unittest.TestCase):
    def test_grid_option(self):
        tmp = tempfile.mkdtemp()
        _, g = render("bowl", os.path.join(tmp, "a.svg"))
        self.assertGreater(len(list(g["Grid"])), 0, "grid drawn by default")
        _, g = render("bowl", os.path.join(tmp, "b.svg"), {"scale": 200, "grid_show": False})
        self.assertEqual(len(list(g["Grid"])), 0, "grid_show false: nothing in the Grid layer")
        self.assertGreater(len(list(g["Bounds"])), 0)
        self.assertGreater(len(list(g["Scale bar"])), 0)            # the other guides are unaffected
        self.assertIn("no grid", " ".join(t[4] for t in texts(g["NOTES"])))

    def test_notes_outside_map_and_in_width(self):
        tmp = tempfile.mkdtemp()
        root, g = render("bowl", os.path.join(tmp, "n.svg"))
        W, H = page_size(root)
        m = 36.0
        for id_, x, y, sz, t, bold in texts(g["NOTES"]):
            w = gt.text_w(t, sz, bold)
            self.assertLessEqual(y, m + 1e-6, id_)                  # baseline inside the top margin: above the map window
            self.assertGreaterEqual(y - sz, 0, id_)
            self.assertGreaterEqual(x, 0)
            self.assertLessEqual(x + w, W - m + 1, id_)
        for id_, x, y, sz, t, bold in texts(g["Scale bar"]):
            self.assertGreaterEqual(y - sz * 0.8, 11 * 72 - m - 1, id_)  # scale bar captions sit in the bottom margin of the map page
        for id_, x, y, sz, t, bold in texts(g["North arrow"]):
            self.assertGreaterEqual(y - sz, 11 * 72 - m - 1, id_)

    def test_long_title_grows_margin_not_overflow(self):
        paras = R.note_paras("T " + "very long place name " * 40)
        lines, need = gt.top_block(paras, 17 * 72 - 72, 1.0, avail_pt=36)
        self.assertGreater(need, 36 + 1e-6)                          # compute_view then raises margin_in so the notes stay outside the map
        model = R.load_place("bridgehollow")
        model["place"]["name"] = "Very long place name " * 40
        v, cfg, title, kind, ident = R.compute_view(model, "bowl", {"scale": 200})
        self.assertGreater(cfg["margin_in"], 0.5)
        self.assertEqual(v.margin, cfg["margin_in"])

    def test_key_band_below_map(self):
        tmp = tempfile.mkdtemp()
        root, g = render("bowl", os.path.join(tmp, "k.svg"))
        W, H = page_size(root)
        leg = texts(g["Legend"])
        self.assertGreaterEqual(len(leg), 5)
        self.assertGreater(H, 11 * 72, "the page grows below the map to hold the key")
        for id_, x, y, sz, t, bold in leg:
            self.assertGreaterEqual(y - sz, 11 * 72 - 1, id_)        # entirely below the map page (and its bottom margin)
            self.assertLessEqual(y, H, id_)
            self.assertGreaterEqual(x, 36 - 1e-6)
            self.assertLessEqual(x + gt.text_w(t, sz, bold), W - 36 + 2, id_)
        root2, g2 = render("bowl", os.path.join(tmp, "k2.svg"), {"scale": 200, "grid_show": False})   # the grid option is independent of the key
        self.assertEqual(len(texts(g2["Legend"])), len(leg))

    def test_big_page_scales_text(self):
        tmp = tempfile.mkdtemp()
        root, g = render("bowl", os.path.join(tmp, "big.svg"), {"scale": 400, "page": "34x22"})
        sizes = {t[0]: t[3] for t in texts(g["NOTES"])}
        self.assertGreater(max(sizes.values()), 15)                  # text follows the page size, so it stays readable on a big sheet


class ImportTests(unittest.TestCase):
    def test_import_image_no_grid(self):
        from PIL import Image
        import foundry_import as fi
        tmp = tempfile.mkdtemp()
        img = os.path.join(tmp, "a.png")
        Image.new("RGB", (400, 300), (200, 190, 170)).save(img)
        root = os.path.join(tmp, "root")
        for i, (kw, want) in enumerate((({}, True), ({"no_grid": True}, False), ({"grid_ft": 0}, False), ({"grid_ft": 50}, True))):
            r = fi.import_image(img, "G%d" % i, None, 5.0, root=root, log=lambda *a: None, **kw)
            vs = json.load(open(os.path.join(r["dir"], "view_settings.json")))
            self.assertEqual(vs.get("grid_show", True), want, kw)
            self.assertEqual(r["grid_show"], want)


class FoundryHideGridTests(unittest.TestCase):
    def test_flag_and_default_off(self):
        src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "foundry_push.py"), encoding="utf-8").read()
        self.assertIn('"--hide-grid"', src)
        self.assertIn('data={"grid": {"alpha": 0}}', src)
        self.assertIn('getattr(a, "hide_grid", False)', src)      # default: grid untouched


if __name__ == "__main__":
    unittest.main()
