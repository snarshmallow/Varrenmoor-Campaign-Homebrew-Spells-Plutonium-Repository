"""Texture tests: conditioning (seams, macro blotches), wet variants, and the four procedural padding tiles (meadow, forest_floor, scree, heather_moor).
Light: 256 px tiles, one at a time.   python test_textures.py"""
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import padding_textures as pt  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

NEW = ("meadow", "forest_floor", "scree", "heather_moor")


def edge_ratio(img):
    """Step across the wrap / p90 of the interior per-line steps (pbr.seam_ratio); about 1 or less = the wrap is invisible."""
    return pbr.seam_ratio(img)


class T(unittest.TestCase):
    def test_make_seamless(self):
        rng = np.random.RandomState(1)
        a = np.cumsum(np.cumsum(rng.randn(128, 128), 0), 1)              # a ramp-like field: huge seam
        a3 = np.stack([a, a * 0.5, a * 0.2], -1)
        self.assertGreater(pbr.seam_ratio(a3), 5)
        b, = pbr.make_seamless(a3)
        self.assertLess(pbr.seam_ratio(b), 1.5)
        self.assertAlmostEqual(float(b.mean()), float(a3.mean()), delta=abs(float(a3.std())) * 0.05)

    def test_condition_keeps_structured_generators(self):
        alb, h = pbr.gen_timberframe(128)
        a2, h2 = pbr.condition(alb, h, fix_seam=False, flatten=False)
        self.assertEqual(float(np.abs(a2 - alb).max()), 0.0)           # the frame is untouched
        self.assertLessEqual(float(np.abs(h2 - h).max()), 0.04)         # only the fine height grain

    def test_low_density_boost(self):
        a, h = pbr.base_texture("mat_dirt")
        a0, _ = pbr.base_texture("mat_dirt", raw=True)
        self.assertEqual(a.shape[0], a0.shape[0] * 2)
        self.assertAlmostEqual(float(a.mean()), float(a0.mean()), delta=4.0)      # same overall colour

    def test_presets_seamless_after_conditioning(self):
        for mid in ("mat_cobble", "mat_gravel", "mat_dirt"):
            alb, h = pbr.base_texture(mid)
            self.assertLess(pbr.seam_ratio(alb), pbr.SEAM_LIMIT, mid)

    def test_wet_variant(self):
        self.assertIn("mat_cobble_wet", pbr.CATALOG)
        dry, _ = pbr.base_texture("mat_cobble")
        wet, h = pbr.base_texture("mat_cobble_wet")
        self.assertLess(wet.mean(), dry.mean() * 0.8)
        mr = pbr.mr_map(h, 0.3, 0.3, 0.0, wet=True)
        self.assertLess(mr[..., 1].mean() / 255, pbr.mr_map(h, 0.3, 0.3, 0.0)[..., 1].mean() / 255 + 1e-9)

    def test_new_padding_presets(self):
        have = pt.list_texture_presets()
        for k in NEW:
            self.assertIn(k, have)
            img, mean = pt.table_tile(have[k], n=256, seed=5)
            self.assertEqual(img.shape, (256, 256, 3))
            self.assertLess(edge_ratio(img), 1.35, k)                    # numerically seamless
            self.assertGreater(img.astype(float).std(), 6, k)            # not flat
            self.assertRegex(mean, r"^#[0-9a-f]{6}$")

    def test_new_presets_differ(self):
        have = pt.list_texture_presets()
        means = [pt.table_tile(have[k], n=128, seed=5)[0].reshape(-1, 3).mean(0) for k in NEW]
        for i in range(4):
            for j in range(i + 1, 4):
                self.assertGreater(np.abs(means[i] - means[j]).sum(), 20)


if __name__ == "__main__":
    unittest.main()
