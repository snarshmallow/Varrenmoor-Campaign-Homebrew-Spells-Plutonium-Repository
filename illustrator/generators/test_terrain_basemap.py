"""Tests for terrain_basemap.py (scale-aware base terrain for feature-less / image-imported specs).
Run: python illustrator/generators/test_terrain_basemap.py   (coarse cells, a few seconds)"""
import copy
import json
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain as T  # noqa: E402
import terrain_basemap as TB  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
# the spec the panel writes for an image-imported base map (nested noise / erosion keys)
PANEL = {"seed": 1103, "cell_ft": 10, "base_elevation_ft": 660, "size_ft": [11205.4, 16005.0],
         "noise": {"ridged_amp_ft": 110, "scale_ft": 420},
         "erosion": {"thermal_iterations": 60, "smooth_sigma_cells": 1}}
CELL = 60


def gen(spec, **kw):
    return T.generate(spec, CELL, **kw)


class Basemap(unittest.TestCase):
    def test_panel_spec_is_not_flat(self):
        h, m = gen(PANEL)
        self.assertGreater(m["relief_ft"], 200)          # was 5 ft with the v1 pipeline
        self.assertEqual(m["recipe"], "rolling_hills")

    def test_old_pipeline_was_flat(self):
        _, m = T.generate_v1(PANEL, CELL)
        self.assertLess(m["relief_ft"], 20)

    def test_relief_follows_relief_ft(self):
        lo = gen(dict(PANEL, relief_ft=200))[1]["relief_ft"]
        hi = gen(dict(PANEL, relief_ft=800))[1]["relief_ft"]
        self.assertGreater(hi, lo + 400)
        self.assertGreater(lo, 150)

    def test_default_relief_is_scale_aware(self):
        small = dict(PANEL, size_ft=[1500.0, 1500.0])
        self.assertLess(TB.default_relief(1500, 1500), TB.default_relief(11205, 16005))
        self.assertGreater(gen(PANEL)[1]["relief_ft"], gen(small)[1]["relief_ft"])
        self.assertGreater(TB.default_relief(11205, 16005), 300)

    def test_amplitude_noise_scale_seed_erosion_smoothing_are_honoured(self):
        base = gen(PANEL)[0]
        for name, spec in [
            ("amp", dict(copy.deepcopy(PANEL), noise={"ridged_amp_ft": 10, "scale_ft": 420})),
            ("scale", dict(copy.deepcopy(PANEL), noise={"ridged_amp_ft": 110, "scale_ft": 1500})),
            ("seed", dict(PANEL, seed=7)),
            ("erosion", dict(PANEL, erosion={"thermal_iterations": 60, "talus_slope": 0.1, "smooth_sigma_cells": 1})),
            ("smooth", dict(PANEL, erosion={"thermal_iterations": 60, "smooth_sigma_cells": 4})),
            ("base", dict(PANEL, base_elevation_ft=100)),
        ]:
            self.assertFalse(np.array_equal(base, gen(spec)[0]), name)
        # detail amplitude: a rougher surface has a larger local gradient
        g = lambda s: np.abs(np.diff(gen(s)[0], axis=1)).mean()
        self.assertGreater(g(PANEL), g(dict(PANEL, noise={"ridged_amp_ft": 10, "scale_ft": 420})))
        self.assertAlmostEqual(float(gen(dict(PANEL, base_elevation_ft=100))[0].mean()) + 560, float(base.mean()), delta=5)

    def test_deterministic(self):
        self.assertTrue(np.array_equal(gen(PANEL)[0], gen(copy.deepcopy(PANEL))[0]))

    def test_recipes_differ_and_shape(self):
        hs = {r: gen(dict(PANEL, recipe=r))[0] for r in TB.RECIPES}
        self.assertFalse(np.array_equal(hs["valley"], hs["highland_ridge"]))
        for r, h in hs.items():
            self.assertGreater(float(h.max() - h.min()), 200, r)
        # valley: centre column lower than the edges; ridge: higher (map is taller than wide, axis runs north-south, wandering)
        ny, nx = hs["valley"].shape
        band = lambda h, a, b: float(h[:, int(nx * a):int(nx * b)].mean())
        self.assertLess(band(hs["valley"], .3, .7), band(hs["valley"], 0, .15) + band(hs["valley"], .85, 1))
        self.assertGreater(band(hs["highland_ridge"], .3, .7), band(hs["highland_ridge"], 0, .15))

    def test_unknown_recipe_rejected(self):
        with self.assertRaises(ValueError):
            gen(dict(PANEL, recipe="volcano"))

    def test_image_blend_off_by_default_and_gentle(self):
        from PIL import Image
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "img.png")
        a = np.zeros((80, 60), np.uint8)
        a[:, 30:] = 255                                  # dark west half, light east half
        Image.fromarray(a).save(p)
        off = gen(dict(PANEL, image_path=p))[0]          # blend unset: image ignored
        self.assertTrue(np.array_equal(off, gen(PANEL)[0]))
        on = gen(dict(PANEL, image_path=p, image_blend=0.5))[0]
        self.assertFalse(np.array_equal(off, on))
        self.assertGreater(float(on[:, -10:].mean() - off[:, -10:].mean()), float(on[:, :10].mean() - off[:, :10].mean()))
        self.assertLess(float(np.abs(on - off).max()), 0.5 * TB.default_relief(11205, 16005) + 1)

    def test_missing_image_is_ignored(self):
        h = gen(dict(PANEL, image_path="nope.png", image_blend=0.5))[0]
        self.assertTrue(np.array_equal(h, gen(PANEL)[0]))


class NaturalRelief(unittest.TestCase):
    """The base terrain is multi-scale (fBm + ridged mix, domain warp, stream-power erosion), not one wormy ridged scale."""

    def _bands(self, h, lams):
        from scipy import ndimage as ndi
        sg = lambda lam: lam / (2 * np.pi) / CELL * 1.3
        g = [ndi.gaussian_filter(h.astype(float), sg(l)) for l in lams]
        return [float((g[i + 1] - g[i]).std()) for i in range(len(lams) - 1)]

    def test_relief_has_energy_at_several_scales_no_single_dominant_wavelength(self):
        # the user's spec: noise.scale_ft 200, ridged_amp_ft 110 (this was a uniform maze of worm-like ridges at one scale)
        spec = dict(PANEL, noise={"ridged_amp_ft": 110, "scale_ft": 200})
        h = gen(spec)[0]
        b = self._bands(h, [12000, 4000, 1500, 600, 240])
        print("  band std (ft), wavelengths 12000>4000>1500>600>240:", [round(x, 1) for x in b])
        self.assertTrue(all(x > 1.0 for x in b[:3]), b)          # kilometre / mile / valley scale landforms exist
        self.assertLess(max(b) / sum(b), 0.7, b)                   # no single scale holds the relief

    def test_slopes_are_natural_not_cliffs_everywhere(self):
        h = gen(dict(PANEL, noise={"ridged_amp_ft": 110, "scale_ft": 200}))[0]
        gy, gx = np.gradient(h.astype(float), CELL)
        slope = np.hypot(gx, gy)
        self.assertLess(float(np.median(slope)), 0.6)

    def test_stream_erosion_key_is_honoured_and_deterministic(self):
        a = gen(PANEL)[0]
        off = gen(dict(PANEL, erosion={"thermal_iterations": 60, "smooth_sigma_cells": 1, "stream_iterations": 0}))[0]
        self.assertFalse(np.array_equal(a, off))
        self.assertTrue(np.array_equal(a, gen(copy.deepcopy(PANEL))[0]))
        self.assertAlmostEqual(float(a.std()), float(off.std()), delta=0.25 * float(off.std()))   # erosion keeps the spread

    def test_no_periodic_tiling_in_the_detail(self):
        # a tiled pattern shows as a strong secondary peak in the autocorrelation of the detail band
        spec = dict(PANEL, noise={"ridged_amp_ft": 110, "scale_ft": 200}, size_ft=[8000.0, 8000.0])
        h = T.generate(spec, 20)[0].astype(float)
        from scipy import ndimage as ndi
        d = h - ndi.gaussian_filter(h, 6)
        d = d[:, :] - d.mean()
        F = np.fft.rfft2(d)
        ac = np.fft.irfft2(F * np.conj(F), s=d.shape)
        ac /= ac[0, 0]
        ky = np.minimum(np.arange(d.shape[0]), d.shape[0] - np.arange(d.shape[0]))[:, None]
        kx = np.minimum(np.arange(d.shape[1]), d.shape[1] - np.arange(d.shape[1]))[None, :]
        far = np.hypot(ky, kx) >= 40                                # beyond 800 ft: ignore the natural short-range correlation
        print("  detail autocorrelation beyond 800 ft: max |r| = %.3f" % float(np.abs(ac[far]).max()))
        self.assertLess(float(np.abs(ac[far]).max()), 0.3)


class ExistingPlacesUnchanged(unittest.TestCase):
    """Specs with features must keep going through their original pipelines, byte for byte."""

    def _check(self, rel):
        path = os.path.join(REPO, "world", rel)
        if not os.path.exists(path):
            self.skipTest(rel)
        spec = T.load_spec(path)
        self.assertFalse(TB.wants_basemap(spec), rel)
        h, _ = T.generate(spec, 60)
        if "natural" in spec:
            import terrain_natural
            ref, _ = terrain_natural.generate(spec, 60, None, False)
        else:
            ref, _ = T.generate_v1(spec, 60)
        self.assertEqual(h.tobytes(), ref.tobytes(), rel)

    def test_varrenmoor(self):
        self._check("varrenmoor/terrain_spec.json")

    def test_bridgehollow(self):
        self._check("bridgehollow/terrain_spec.json")

    def test_bridgehollow_v1(self):
        self._check("bridgehollow/terrain_spec_v1.json")

    def test_feature_spec_with_explicit_recipe_key_only_when_asked(self):
        spec = T.load_spec(os.path.join(REPO, "world", "varrenmoor", "terrain_spec.json"))
        self.assertFalse(TB.wants_basemap(spec))


if __name__ == "__main__":
    unittest.main()
