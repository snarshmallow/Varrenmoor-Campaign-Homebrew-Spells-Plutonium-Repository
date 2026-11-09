"""Padding apron colour: no radial streaks on steep slopes (python test_padding_streaks.py). Synthetic place, small maps, writes a preview PNG next to the test
when PADDING_STREAK_PREVIEW is set (before | after)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import padding_textures as pt  # noqa: E402

W = H = 400.0
BLEND = 200.0


def setup():
    P = pt.load_texture_preset("summer")
    rng = np.random.RandomState(3)
    stripes = (np.sin(np.arange(256) * 2 * np.pi / (240.0 / (W / 256))) * 0.5 + 0.5) * np.ones((256, 1))   # colour bands along the edge (roads, tree patches), 240 ft wavelength
    alb = np.zeros((256, 256, 3), np.uint8)
    alb[..., 0] = (50 + 150 * stripes).astype(np.uint8)
    alb[..., 1] = (90 + 40 * rng.rand(256, 256)).astype(np.uint8)
    alb[..., 2] = 50

    def rect_dist(X, Y):
        qx, qy = np.clip(X, 0, W), np.clip(Y, 0, H)
        return np.hypot(X - qx, Y - qy), qx, qy
    cx, cy = W / 2, H / 2

    def hfn(X, Y):
        s = rect_dist(X, Y)[0]
        return 700.0 + s * 1.3 + 6 * np.sin(X / 40.0)                                           # about 52 degree apron
    return P, alb, rect_dist, hfn


def streak_index(img, rect_dist, bbox, blend=BLEND):
    """Energy of the colour gradient ALONG the edge (tangential) over the energy ALONG the ray (radial), apron strip on the north side only."""
    x0, y0, x1, y1 = bbox
    h, w = img.shape[:2]
    xs = x0 + (np.arange(w) + 0.5) * (x1 - x0) / w
    ys = y0 + (np.arange(h) + 0.5) * (y1 - y0) / h
    X, Y = np.meshgrid(xs, ys)
    s = rect_dist(X, Y)[0]
    m = (Y < 0) & (X > 40) & (X < W - 40) & (s > 15) & (s < blend * 0.9)                         # north apron: radial = y, tangential = x
    from scipy import ndimage
    g = ndimage.gaussian_filter(img.astype(float)[..., 0], 4.0)                                  # low-pass: the grain is isotropic, the bands are what streaks are
    sel = m[:, :]
    rows = np.nonzero(sel.any(1))[0]
    tang = np.mean([g[r][sel[r]].std() for r in rows])                                           # colour variation along the edge at constant distance
    return 0.0, float(tang)


class Streaks(unittest.TestCase):
    def build(self, fix, px=(256, 256)):
        P, alb, rect_dist, hfn = setup()
        bb = (-BLEND, -BLEND, W + BLEND, H + BLEND)
        im, _, _ = pt.apron_albedo(hfn, bb, px, P, 5, lambda X, Y: rect_dist(X, Y), alb, (0, 0, W, H), blend_ft=BLEND, far_mean="#6a7a4a", apron_len=BLEND, streak_fix=fix)
        return im, rect_dist, bb

    def test_fix_removes_radial_streaks(self):
        a, rd, bb = self.build(False)
        b, _, _ = self.build(True)
        ia, ea = streak_index(a, rd, bb)
        ib, eb = streak_index(b, rd, bb)
        print(f"streak index (tangential/radial gradient): before {ia:.2f}, after {ib:.2f}; tangential energy {ea:.2f} -> {eb:.2f}")
        self.assertGreater(ea, 8.0)                  # the old lookup really does carry the edge bands out as streaks
        self.assertLess(eb, ea * 0.5)

    def test_seam_colour_still_continues_the_terrain(self):
        a, rd, bb = self.build(True, (512, 512))
        P, alb, _, _ = setup()
        h, w = a.shape[:2]
        iy = int((0 - bb[1]) / (bb[3] - bb[1]) * h) - 2                 # just outside the north edge
        row = a[iy, int(w * 0.35):int(w * 0.65)].astype(float).mean()
        ref = alb[:3, 90:170].astype(float).mean()
        self.assertLess(abs(row - ref), 70)

    def test_preview(self):
        out = os.environ.get("PADDING_STREAK_PREVIEW")
        if not out:
            self.skipTest("set PADDING_STREAK_PREVIEW=file.png")
        from PIL import Image
        a, _, _ = self.build(False, (512, 512))
        b, _, _ = self.build(True, (512, 512))
        Image.fromarray(np.concatenate([a, np.full((a.shape[0], 8, 3), 255, np.uint8), b], 1)).save(out)


class SeamMatch(unittest.TestCase):
    def test_grain_and_brightness_match_terrain_at_the_seam(self):
        P = pt.load_texture_preset("meadow")
        rng = np.random.RandomState(1)
        alb = (np.clip(0.45 + 0.07 * rng.randn(200, 200, 1), 0, 1) * np.array([0.9, 1.2, 0.6])[None, None, :] * 255).astype(np.uint8)   # 7 % grain
        box = (0, 0, W, H)
        mean_t, rel_t = pt.terrain_edge_stats(alb, box)
        self.assertGreater(rel_t, 0.05)
        from skybox import srgb_to_lin
        h = w = 320
        yy, xx = np.mgrid[0:h, 0:w]
        s = np.maximum(0.0, np.abs(xx - w / 2) - 100)                    # synthetic distance field (ft ~ px)
        fine = np.random.RandomState(2).rand(h, w).astype(np.float32) * 0.3 + 0.35
        base = np.full((h, w, 3), 0.2, np.float32)
        out = pt.seam_colour_match(base, s, fine, alb, box, match_ft=110.0, gain=1.12)
        near, far = out[s < 5], out[s > 120]
        self.assertGreater(float(near.mean(-1).std() / near.mean()), 0.8 * 0.052)      # grain added at the seam (apron was flat)
        self.assertAlmostEqual(float(near.mean() / 0.2), 1.12, delta=0.12)             # brightness gain at the seam
        self.assertTrue(np.allclose(far, 0.2, atol=1e-6))                              # untouched beyond match_ft


class ChannelFade(unittest.TestCase):
    """A river channel carved into the tile edge must not be extruded into the apron (north/south 'ladder' streak)."""

    class FakePlace:
        W = H = 400.0
        cell = 4.0
        z_origin = 0.0

        def __init__(self):
            x = np.arange(0, 401, 4.0)
            self.h = np.full((101, 101), 30.0)
            self.h[:, (np.abs(x - 200) < 12)] = 12.5                          # 24 ft wide, 17.5 ft deep channel running off the north and south edge

        def tile_h(self, x, y):
            import padding_heightmap as ph
            return ph._bilinear(self.h, self.cell, x, y)

        def rect_dist(self, x, y):
            import padding_heightmap as ph
            return ph.Place.rect_dist(self, x, y)

    class Table:
        def surface(self, X, Y):
            return np.full(np.shape(X), -4.0)

    def depth_at(self, fade, d):
        import padding_heightmap as ph
        ap = ph.Apron(self.FakePlace(), self.Table(), 200.0, detail_ft=0.0, edge_fade_ft=fade)
        return float(ap.height(np.array([200.0]), np.array([-d]))[0] - ap.height(np.array([300.0]), np.array([-d]))[0])

    def test_channel_fades_out(self):
        for d in (110, 140, 190):
            self.assertLess(abs(self.depth_at(110.0, d)), 1.0, d)            # faded: channel and bank line agree
        self.assertLess(abs(self.depth_at(110.0, 0.0) - (12.5 - 30.0)), 0.5)   # exact at the seam
        self.assertGreater(abs(self.depth_at(0.0, 60.0)), 2.0)               # without the fade the trench is still there (the old behaviour)


if __name__ == "__main__":
    unittest.main()
