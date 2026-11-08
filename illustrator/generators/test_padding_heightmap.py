"""Tests for padding_heightmap.py. Run: python illustrator/generators/test_padding_heightmap.py   (about 40 s; uses the Dyers Walk pack)"""
import hashlib
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import padding_heightmap as ph  # noqa: E402

PLACE = "bridgehollow__dyers_walk_local"
SCENE = {"width": 6130, "height": 7236, "padding": 0.25, "grid": {"size": 100, "distance": 5}, "flags": {"varrenmoor": {"calib": {"ppf": 20}}}}
HAVE = os.path.exists(os.path.join(ph.REPO, "world", PLACE, "export", "manifest.json"))


class ScaleMath(unittest.TestCase):
    def test_units(self):
        self.assertAlmostEqual(ph.ft_per_unit(20), 50.0)
        self.assertAlmostEqual(ph.max_height_ft(1.0, 20), 500.0)          # measured live: scale 1, pixel 255 -> 10 units = 10000 px
        self.assertAlmostEqual(ph.max_height_ft(2.5, 20), 1250.0)
        self.assertAlmostEqual(ph.max_height_ft(1.0, 10), 1000.0)
        self.assertEqual(ph.scale_for_max(500, 20), 1.0)
        self.assertEqual(ph.scale_for_max(501, 20), 1.01)
        self.assertEqual(ph.scale_for_max(1e9, 20), 10.0)
        self.assertEqual(ph.scale_for_max(0, 20), 0.01)

    def test_canvas_dims_match_foundry(self):
        # measured: a 6130 x 7236 scene with padding 0.25 and 100 px grid is a 9330 x 11036 canvas, scene at (1600, 1900)
        self.assertEqual(ph.canvas_dims(6130, 7236, 0.25, 100), (9330, 11036, 1600, 1900))

    def test_ramp_matches_live_measurement(self):
        # live: flat 255 image, scale 1, canvas 9330 x 11036 -> heights (units) along z = 0 at x = 2..18: 0, 0, .482, 2.482, 4.482, 6.482, 8.482, 10, 10
        t = ph.TableModel(20, 9330, 11036, 1.0, np.full((128, 128), 255, np.uint8))
        row = t.vz[50, 51:60] / 50.0
        np.testing.assert_allclose(row, [0, 0, 0.482, 2.482, 4.482, 6.482, 8.482, 10, 10][:9], atol=0.002)
        self.assertEqual(t.vz[:, -1].max(), 0.0)                         # the last row/column (u = 1) is never displaced

    def test_image_roundtrip(self):
        rng = np.random.RandomState(1)
        target = rng.rand(101, 101) * 300
        img, scale = ph.make_image(target, {"ppf": 20})
        t = ph.TableModel(20, 1e5, 1e5, scale, img)                      # R huge -> compare r*K directly via a ramp-free model
        t.vz = t.r / 255.0 * t.K
        err = np.abs(t.vz[:-1, :-1] - target[:-1, :-1]).max()
        self.assertLessEqual(err, ph.max_height_ft(scale, 20) / 255.0 / 2 + 1e-6)


class Presets(unittest.TestCase):
    def test_builtin_and_roundtrip(self):
        names = ph.list_presets()
        for n in ("bowl-ridge", "rolling-hills", "coastal-flats", "fjord-walls", "flat-plain", "none"):
            self.assertIn(n, names)
        with tempfile.TemporaryDirectory() as d:
            old = ph.USER_PRESET_DIR
            ph.USER_PRESET_DIR = d
            try:
                pr = dict(ph.load_preset("bowl-ridge"), ridge_amp_ft=123, name="x")
                p = ph.save_preset("My Hills!", pr)
                self.assertTrue(os.path.exists(p))
                back = ph.load_preset("My Hills!")
                self.assertEqual(back["ridge_amp_ft"], 123)
                self.assertTrue(ph.list_presets()["My Hills!"]["_user"])
            finally:
                ph.USER_PRESET_DIR = old

    def test_texture_presets(self):
        import padding_textures as pt
        for n in ("summer", "autumn", "winter", "overcast"):
            self.assertIn(n, pt.list_texture_presets())


@unittest.skipUnless(HAVE, "Dyers Walk pack not exported")
class Generate(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = ph.generate(PLACE, preset_name="bowl-ridge", scene=SCENE, blend_ft=200, apron_albedo_px=96, seed=7)

    def test_seam_steps(self):
        s = self.r["meta"]["seam"]
        self.assertLess(s["max_step_terrain_edge_m"], 0.05)               # apron ring 0 == the tile's edge nodes
        self.assertLess(s["max_step_table_m"], 0.05)                      # outer ring == table surface (+0.02 ft)
        self.assertGreater(s["table_only_step_ft"], 5.0)                  # without the apron the table is far below the tile edge

    def test_ring0_equals_exported_glb_edge(self):
        g = os.path.join(ph.REPO, "world", PLACE, "export", "models", "terrain.glb")
        if not os.path.exists(g):
            self.skipTest("no split terrain.glb")
        p, V, info = self.r["place"], self.r["V"], self.r["ring_info"]
        P = ph.read_glb_positions(g)
        x, y = P[:, 0] / ph.FT_M + p.W / 2, P[:, 2] / ph.FT_M + p.H / 2
        edge = (np.abs(x) < 1e-3) | (np.abs(x - p.W) < 1e-3) | (np.abs(y) < 1e-3) | (np.abs(y - p.H) < 1e-3)
        ring = V[info["ring_start"][0]:info["ring_start"][0] + info["ring_len"][0]]
        lookup = {(round(a, 2), round(b, 2)): c for a, b, c in ring}
        # compare through the heightmap the Place adopted from that same GLB
        d = [abs(lookup[(round(a, 2), round(b, 2))] - (p.tile_h(a, b) - p.z_origin)) for a, b in zip(x[edge], y[edge]) if (round(a, 2), round(b, 2)) in lookup]
        self.assertGreater(len(d), 400)
        self.assertLess(max(d) * ph.FT_M, 0.05)
        self.assertGreater(p.glb_dev_ft, 1.0)             # the GLB really differs from heightmap_f32 somewhere (road conforming), and we follow the GLB

    def test_table_never_above_tile(self):
        p, t = self.r["place"], self.r["table"]
        xs = np.linspace(0, p.W, 60)
        X, Y = np.meshgrid(xs, np.linspace(0, p.H, 60))
        self.assertTrue((t.surface(X, Y) <= p.tile_h(X, Y) - p.z_origin).all())

    def test_determinism(self):
        r2 = ph.generate(PLACE, preset_name="bowl-ridge", scene=SCENE, blend_ft=200, apron_albedo_px=96, seed=7)
        self.assertEqual(hashlib.sha1(self.r["image"].tobytes()).hexdigest(), hashlib.sha1(r2["image"].tobytes()).hexdigest())
        np.testing.assert_array_equal(self.r["V"], r2["V"])
        r3 = ph.generate(PLACE, preset_name="bowl-ridge", scene=SCENE, blend_ft=200, apron_albedo_px=96, seed=8)
        self.assertNotEqual(hashlib.sha1(self.r["image"].tobytes()).hexdigest(), hashlib.sha1(r3["image"].tobytes()).hexdigest())

    def test_mesh_is_watertight_and_up(self):
        V, tris = self.r["V"], self.r["tris"]
        edges = {}
        for a, b, c in tris:
            for u, v in ((a, b), (b, c), (c, a)):
                edges[(u, v)] = edges.get((u, v), 0) + 1
        self.assertTrue(all(n == 1 for n in edges.values()))              # each directed edge once (consistent orientation)
        n = ph.vertex_normals(V, tris)
        self.assertGreater(n[:, 1].min(), 0.0)                            # every normal points up

    def test_outputs_and_glb(self):
        with tempfile.TemporaryDirectory() as d:
            out = ph.write_outputs(self.r, d)
            for k in ("heightmap", "heightmap_16", "table_tile", "apron_glb", "apron_albedo", "preview", "meta"):
                self.assertTrue(os.path.exists(out[k]), k)
            P = ph.read_glb_positions(out["apron_glb"])
            self.assertEqual(len(P), len(self.r["V"]))
            from PIL import Image
            im = np.asarray(Image.open(out["heightmap"]))
            self.assertEqual(im.shape, (128, 128))

    def test_none_preset_is_flat(self):
        r = ph.generate(PLACE, preset_name="none", scene=SCENE, blend_ft=100, apron_albedo_px=64)
        self.assertFalse(r["meta"]["heightmap_used"])
        self.assertEqual(int(r["image"].max()), 0)


class FakeBridge:
    def __init__(self):
        self.calls = []

    def call(self, op, **a):
        self.calls.append((op, a))
        if op == "get":
            return dict(SCENE, name="s", flags=SCENE["flags"])
        return {}


@unittest.skipUnless(HAVE, "Dyers Walk pack not exported")
class PushDry(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        r = ph.generate(PLACE, preset_name="rolling-hills", scene=SCENE, blend_ft=100, apron_albedo_px=64)
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as assets:
            out = ph.write_outputs(r, d)
            br = FakeBridge()
            plan = ph.push(r, out, "Scene.x", br=br, dry_run=True, assets_root=assets)
            self.assertEqual(os.listdir(assets), [])                       # nothing published
            self.assertEqual([c[0] for c in br.calls], ["get"])            # read only
            fl = plan["flags"]["levels-3d-preview"]
            self.assertEqual(fl["renderTable"], "matcustom")
            self.assertIn("tableHeightmap", fl)
            self.assertTrue(0.01 <= fl["tableHeightmapScale"] <= 10)
            self.assertEqual(plan["tile"]["id"], f"model:{PLACE}:padding_apron")
            plan2 = ph.push(r, out, "Scene.x", br=br, dry_run=False, assets_root=assets)
            self.assertIn("tile_result", plan2)
            ops = [c[0] for c in br.calls]
            self.assertIn("update", ops)
            self.assertIn("upsert_many", ops)


if __name__ == "__main__":
    unittest.main()
