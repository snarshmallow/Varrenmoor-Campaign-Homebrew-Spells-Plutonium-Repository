"""A river channel crossing the terrain boundary: bed eased to the bank, no steep wall beyond the seam, water buried at the edge, continuous seam normals."""
import math
import unittest

import numpy as np

import padding_heightmap as ph
import terrain_edge as te

CELL, N = 4.0, 201                                            # 800 ft tile
BANK, BED, WATER = 30.0, 12.5, 24.0


def tile(channel=True):
    x = np.arange(N) * CELL
    h = np.full((N, N), BANK)
    if channel:
        k = np.clip((12.0 + 12.0 - np.abs(x - 400)) / 12.0, 0, 1)          # 24 ft wide channel, 12 ft bank falloff, running off the north and south edge
        h = np.minimum(h, BANK - (BANK - BED) * (k * k * (3 - 2 * k))[None, :])
    return h


class Place:
    W = H = (N - 1) * CELL
    cell = CELL
    z_origin = 0.0

    def __init__(self, h):
        self.h = h.astype(float)

    def tile_h(self, x, y):
        return ph._bilinear(self.h, self.cell, x, y)

    def rect_dist(self, x, y):
        return ph.Place.rect_dist(self, x, y)


class Table:
    def surface(self, X, Y):
        return np.full(np.shape(X), -4.0)


def max_slope_deg(h, cell, rows):
    gy, gx = np.gradient(h, cell)
    return float(np.degrees(np.arctan(np.hypot(gx, gy)))[rows].max())


class EaseCarve(unittest.TestCase):
    def setUp(self):
        self.orig, self.carved = tile(False), tile(True)
        self.eased = te.ease_carve_at_edge(self.carved, self.orig, CELL, 100.0)

    def test_edge_is_bank_and_interior_untouched(self):
        np.testing.assert_allclose(self.eased[0], BANK)
        np.testing.assert_allclose(self.eased[-1], BANK)
        np.testing.assert_allclose(self.eased[:, 0], BANK)
        np.testing.assert_allclose(self.eased[75:-75], self.carved[75:-75])         # beyond 100 ft nothing changes
        np.testing.assert_allclose(self.eased[:, :20], BANK)

    def test_water_goes_under_the_bed_at_the_edge(self):
        centre = self.eased[:, 100]                                                 # channel centre column
        self.assertGreaterEqual(centre[0], WATER)                                   # bed above the water surface at the boundary: no flat cut of the water is visible
        self.assertLess(centre[60], WATER)                                          # and the water is still there in the interior
        self.assertTrue((np.diff(centre[:21]) <= 1e-9).all())                       # bed rises monotonically towards the edge

    def test_off_means_off(self):
        self.assertIs(te.ease_carve_at_edge(self.carved, self.orig, CELL, 0), self.carved)

    def test_no_cliff_along_the_channel(self):
        gy = np.abs(np.diff(self.eased[:21, 100])) / CELL
        self.assertLess(math.degrees(math.atan(gy.max())), 20.0)                   # along the channel the bed climbs gently (the old cut was vertical at the edge)


class ApronSeam(unittest.TestCase):
    def build(self, h):
        pl = Place(h)
        ap = ph.Apron(pl, Table(), 200.0, detail_ft=0.0)
        V, tris, info = ph.build_apron_mesh(ap)
        return pl, V, tris, info

    def apron_slope(self, V, tris, pl, beyond):
        a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
        fn = np.cross(b - a, c - a)
        sl = np.degrees(np.arccos(np.clip(np.abs(fn[:, 2]) / np.linalg.norm(fn, axis=1), 0, 1)))
        s = pl.rect_dist(*((a + b + c) / 3)[:, :2].T)[0]
        return float(sl[(s > beyond) & (s <= 150)].max())

    def test_no_steep_wall_beyond_the_seam(self):
        eased = te.ease_carve_at_edge(tile(True), tile(False), CELL, 100.0)
        pl, V, tris, _ = self.build(eased)
        self.assertLess(self.apron_slope(V, tris, pl, 20.0), 25.0)
        pl0, V0, t0, _ = self.build(tile(True))                                     # un-eased: the apron receives the true channel profile
        self.assertGreater(self.apron_slope(V0, t0, pl0, 5.0), 0.0)

    def test_seam_normals_are_continuous(self):
        eased = te.ease_carve_at_edge(tile(True), tile(False), CELL, 100.0)
        pl, V, tris, info = self.build(eased)
        r0 = np.arange(info["ring_start"][0], info["ring_start"][0] + info["ring_len"][0])
        plain = ph.vertex_normals(V, tris)[r0]
        tn = ph.terrain_edge_normals(pl, V[r0, 0], V[r0, 1])
        fixed = ph.vertex_normals(V, tris, (r0, tn))[r0]
        ang = lambda u, v: np.degrees(np.arccos(np.clip((u * v).sum(1), -1, 1)))
        self.assertLess(ang(fixed, tn).max(), 0.01)
        # terrain edge normals really are the mesh's: compare with a straight area-weighted accumulation on the full grid
        full = ph.grid_vertex_normals(pl.h, CELL)
        np.testing.assert_allclose(ph.terrain_edge_normals(pl, np.array([100.0, 100.0]), np.array([0.0, pl.H])), np.array([full[0, 25], full[-1, 25]]), atol=1e-9)
        self.assertGreaterEqual(ang(plain, tn).max(), 0.0)


if __name__ == "__main__":
    unittest.main()


class SoftenAlbedo(unittest.TestCase):
    def test_grey_wedge_at_the_edge_becomes_grass_interior_untouched(self):
        n = 200
        img = np.zeros((n, n, 3), np.uint8)
        img[...] = (100, 150, 70)                                    # grass
        img[0:40, 90:110] = (120, 120, 125)                          # grey bank wedge touching the north edge (ft = px here: size 200)
        img[100:140, 90:110] = (120, 120, 125)                       # grey patch in the middle of the map
        out = te.soften_edge_albedo(img, (200.0, 200.0), edge_ft=60.0, sigma_ft=10.0)
        g0 = int(out[2, 100, 1]) - int(out[2, 100, 0])               # at the boundary: green again
        self.assertGreater(g0, 30)
        self.assertTrue(np.array_equal(out[100:140, 90:110], img[100:140, 90:110]))     # interior untouched
        rng = np.random.RandomState(4)
        noisy = np.clip(np.array([100, 150, 70])[None, None, :] + rng.randn(n, n, 3) * 12, 0, 255).astype(np.uint8)
        o2 = te.soften_edge_albedo(noisy, (200.0, 200.0), edge_ft=40.0, border_ft=10.0)
        self.assertLess(float(np.abs(o2[:, 0].astype(float) - o2[:, -1].astype(float)).mean()), 3.0)      # opposite edges agree (no wrap bleed)
        self.assertLess(float(np.abs(o2[0].astype(float) - o2[-1].astype(float)).mean()), 3.0)
        flat = np.full((n, n, 3), 128, np.uint8)
        self.assertTrue(np.array_equal(te.soften_edge_albedo(flat, (200.0, 200.0)), flat))   # no green ground: unchanged
