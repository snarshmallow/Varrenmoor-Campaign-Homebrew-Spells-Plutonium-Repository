"""Tests for world-scale UVs, procedural PBR textures and the terrain-derived skybox (python test_worldpack_pbr.py)."""
import math
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skybox  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

FT = wm.FT


class UVTests(unittest.TestCase):
    def test_wall_density_and_orientation(self):
        # a 10 ft wide, 8 ft tall wall along a diagonal: u advances 10/tile along the wall regardless of direction, v runs down (-z)
        a = np.array([0.0, 0.0])
        L = 10 * FT
        d = np.array([3.0, 4.0]) / 5.0
        p0, p1 = a, a + d * L
        pts = [(p0[0], p0[1], 0), (p1[0], p1[1], 0), (p1[0], p1[1], 8 * FT), (p0[0], p0[1], 8 * FT)]
        uv = wm.world_uv(pts, 5.0)
        self.assertAlmostEqual(abs(uv[1][0] - uv[0][0]), 2.0, 5)             # 10 ft / 5 ft tile
        self.assertAlmostEqual(uv[0][1] - uv[3][1], 8 / 5.0, 5)              # v grows downward: base is 8 ft below the top
        self.assertAlmostEqual(uv[0][1], uv[1][1], 6)                        # courses stay level

    def test_roof_v_is_slope_length(self):
        run, rise, ridge = 4.0 * FT, 3.0 * FT, 10 * FT                       # 5 ft slope length
        pts = [(0, 0, 0), (ridge, 0, 0), (ridge, run, rise), (0, run, rise)]
        uv = wm.world_uv(pts, 5.0)
        self.assertAlmostEqual(abs(uv[3][1] - uv[0][1]), 1.0, 5)             # 5 ft of slope over a 5 ft tile
        self.assertAlmostEqual(uv[0][1], uv[1][1], 6)
        self.assertGreater(uv[0][1], uv[3][1])                               # eave is further down the image than the ridge

    def test_gable_triangle_is_upright(self):
        pts = [(0, -2, 3.0), (0, 2, 3.0), (0, 0, 5.0)]
        uv = wm.world_uv(pts, 4.0 / FT)
        self.assertLess(uv[2][1], uv[0][1])
        self.assertAlmostEqual(uv[0][1], uv[1][1], 6)


class PbrTests(unittest.TestCase):
    def test_prepare_idempotent_and_adds_materials(self):
        mats = {"mat_cobble": {"id": "mat_cobble", "texture": "textures/cobble.png", "roughness": 0.9, "metallic": 0.0}}
        pbr.prepare(mats)
        snap = {k: dict(v) for k, v in mats.items()}
        pbr.prepare(mats)
        self.assertEqual(snap, mats)
        self.assertTrue(mats["mat_cobble"]["normal"] and mats["mat_cobble"]["mr"])
        self.assertLess(mats["mat_cobble"]["roughness"], 0.9)
        self.assertLess(mats["mat_glass"]["alpha"], 0.5)
        for m in ("mat_wall_stone", "mat_wall_frame", "mat_wall_batten", "mat_plaster", "mat_door_wood", "mat_kerb"):
            self.assertIn(m, mats)

    def test_generators_and_normals(self):
        for name, g in pbr.GENERATORS.items():
            a, h = g(128)
            self.assertEqual(a.shape, (128, 128, 3))
            self.assertTrue(np.isfinite(h).all() and np.isfinite(a).all())
            n = pbr.normal_map(h, 2.0)
            self.assertEqual(n.shape, (128, 128, 3))
            self.assertGreater(n[..., 2].min(), 100)                          # normals point out of the surface

    def test_tileable_noise(self):
        f = pbr.fbm(64, 1)
        d_edge = np.abs(f[:, 0] - f[:, -1]).mean()
        d_inner = np.abs(f[:, 31] - f[:, 32]).mean()
        self.assertLess(d_edge, d_inner * 3 + 0.05)

    def test_restyle_is_stable_and_varied(self):
        e = {"id": "bld_x", "kind": "house", "wall": {"surface": {"material": "mat_plank", "tile_ft": 8}}}
        self.assertEqual(pbr.restyle_building(e)["wall"], pbr.restyle_building(e)["wall"])
        picks = {pbr.restyle_building(dict(e, id=f"b{i}"))["wall"]["surface"]["material"] for i in range(60)}
        self.assertGreaterEqual(len(picks), 3)
        w = {"id": "b", "kind": "house", "wall": {"surface": {"material": "mat_w_plank", "tile_ft": 8}}}
        self.assertEqual(pbr.restyle_building(w)["wall"]["surface"]["material"], "mat_w_plank")

    def test_glb_has_normal_texture(self):
        mats = {"mat_plank": {"id": "mat_plank", "texture": "textures/plank.png", "mean_color": "#aa8855"}}
        pbr.prepare(mats)
        b = wm.Builder()
        b.face("mat_plank", [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)], [(0, 1), (1, 1), (1, 0), (0, 0)])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.glb")
            wm.write_glb(p, [("n", b.build(), {})], mats, textures="external", tex_root=d)
            _, g = wm.read_glb(p)
            m = g["materials"][0]
            self.assertIn("normalTexture", m)
            self.assertTrue(any(i.get("uri", "").endswith("mat_plank_n.png") for i in g["images"]))


class SkyboxTests(unittest.TestCase):
    def test_horizon_follows_terrain_peak(self):
        h = np.zeros((101, 101))
        yy, xx = np.mgrid[0:101, 0:101]
        h += 400 * np.exp(-((xx - 90) ** 2 + (yy - 50) ** 2) / 60.0)         # a peak east of the middle, 400 ft high
        mc = skybox.march_columns(h, 10.0, 500.0, 500.0, 360)
        prof = np.degrees(mc["M"][:, -1])
        east = prof[180]                                                    # column 180 = image centre = east
        self.assertGreater(east, 20)
        self.assertLess(prof[0], east / 2)                                  # west is flat
        self.assertLessEqual(abs(int(np.argmax(prof)) - 180), 2)

    def test_render_small(self):
        h = np.zeros((61, 61))
        h[:, :8] = np.linspace(300, 0, 8)
        for name in ("clear_day", "night"):
            img, info = skybox.render("x", name, None, 256, h=h, cell=10.0)
            self.assertEqual(img.shape, (128, 256, 3))
            self.assertEqual(img.dtype, np.uint8)
        self.assertGreater(float(img.mean()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=1)
