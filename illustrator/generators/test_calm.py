"""Tests for the muted control, calm presets, grid window and contour casing. Run: python generators/test_calm.py"""
import json
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import shading as sh  # noqa: E402
import contours as ct  # noqa: E402


class T(unittest.TestCase):
    def test_muted_identity_and_desaturate(self):
        img = np.random.default_rng(1).uniform(0, 255, (8, 8, 3))
        self.assertTrue(np.allclose(sh.apply_muted(img, None), img))
        self.assertTrue(np.allclose(sh.apply_muted(img, {"saturation": 1, "contrast": 1}), img))
        g = sh.apply_muted(img, {"saturation": 0.0, "contrast": 1})
        self.assertLess(np.abs(g[..., 0] - g[..., 1]).max(), 1e-6)
        c = sh.apply_muted(img, {"saturation": 1, "contrast": 0.5})
        self.assertLess(c.std(), img.std())
        t = sh.apply_muted(np.full((2, 2, 3), 128.0), {"tint": "#ff0000", "tint_strength": 0.5})
        self.assertGreater(t[0, 0, 0], t[0, 0, 2])

    def test_presets_have_calm_versions(self):
        for n in ("alpine_steep", "temperate_valley", "dry_hills", "ink_wash", "parchment", "coastal_basin"):
            self.assertTrue(os.path.exists(os.path.join(sh.PRESET_DIR, n + ".json")))
            d = sh.load_phase_file(os.path.join(sh.PRESET_DIR, n + "_calm.json"))
            self.assertIn("muted", d)
            self.assertLessEqual(d["muted"]["saturation"], 1.0)
        self.assertEqual(sh.DEFAULT_PRESET, "alpine_steep_calm")

    def test_texture_contrast_reduces_variation(self):
        rng = np.random.default_rng(2)
        h = ndi_smooth(rng)
        meta = {"cell_ft": 10, "size_ft": [320, 320], "seed": 3}
        ph = [{"id": "g", "texture": "grass.png", "tile_scale_ft": 40}]
        a, _ = sh.render(h, meta, ph, 0.5, sh.TEX_DIR, None, 3, verbose=False)
        ph[0]["texture_contrast"] = 0.3
        b, _ = sh.render(h, meta, ph, 0.5, sh.TEX_DIR, None, 3, verbose=False)
        self.assertLess(b.astype(float).std(), a.astype(float).std())

    def test_contour_tone_classes(self):
        cs = ct.ContourSet()
        cs.pieces = [{"id": "contour_1_1", "elev": 1, "index": True, "datum": False, "pts": [(0, 0), (10, 0), (20, 0)], "closed": False},
                     {"id": "contour_2_1", "elev": 2, "index": False, "datum": False, "pts": [(0, 5), (10, 5), (20, 5)], "closed": False}]
        ct.classify_tone(cs, lambda x, y: np.where(y < 1, 0.1, 0.9))
        self.assertEqual([p["tone"] for p in cs.pieces], ["dark", "light"])


def ndi_smooth(rng):
    from scipy import ndimage as ndi
    return 700 + 80 * ndi.gaussian_filter(rng.standard_normal((32, 32)), 4)


if __name__ == "__main__":
    unittest.main()
