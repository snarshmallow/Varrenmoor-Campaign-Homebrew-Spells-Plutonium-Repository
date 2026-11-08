"""Tests for the 3D water pipeline: presets, river / lake meshes with the _VBWATER attribute, GLB round trip, push decoration, install-water / set-water
against an in-memory bridge. Small synthetic data only (no pack, no Foundry). Run: python illustrator/generators/test_water.py"""
import json
import os
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import water_presets as wpz  # noqa: E402
import worldpack_water as ww  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import foundry_water as fw  # noqa: E402
import foundry_push as fp  # noqa: E402

FT = wm.FT


def river(n=12, drop_ft=30.0):
    """straight river going east along y = 0 (Blender frame), 400 ft long, 30 ft wide, surface falling drop_ft."""
    xs = np.linspace(0, 400 * FT, n)
    pts = [(float(x), 0.0) for x in xs]
    zs = list(np.linspace(drop_ft * FT, 0, n))
    return ww.build_ribbon(pts, [30 * FT] * n, zs, "VB_water_river")


class Presets(unittest.TestCase):
    def test_kinds_and_clamp(self):
        self.assertEqual(wpz.preset_for_kind("stream"), "river")
        self.assertEqual(wpz.preset_for_kind("sea"), "ocean")
        self.assertEqual(wpz.preset_for_kind("weird"), wpz.table()["default_preset"])
        p = wpz.resolve("river", {"flow_speed": 99, "wave_scale": -3, "foam": "x", "shallow_color": "red"})
        self.assertEqual(p["flow_speed"], 4)
        self.assertEqual(p["wave_scale"], 0.25)
        self.assertEqual(p["foam"], wpz.table()["presets"]["river"]["foam"])
        self.assertEqual(p["shallow_color"], wpz.table()["presets"]["river"]["shallow_color"])
        self.assertEqual(p["mode"], "flow")

    def test_settings_force(self):
        s = {"preset": "pond", "force": True, "values": {"pond": {"wave_height": 1.5}, "river": {"foam": 1}}}
        self.assertEqual(wpz.settings_for("river", s)["preset"], "pond")
        self.assertEqual(wpz.settings_for("river", s)["wave_height"], 1.5)
        s["force"] = False
        self.assertEqual(wpz.settings_for("river", s)["foam"], 1)
        self.assertEqual(wpz.settings_for("lake", s)["preset"], "lake")

    def test_every_preset_in_range(self):
        t = wpz.table()
        for name, pr in t["presets"].items():
            for k, spec in t["params"].items():
                self.assertTrue(spec["min"] <= pr[k] <= spec["max"], (name, k))
            self.assertIn(pr["mode"], ("flow", "wind"))


class Meshes(unittest.TestCase):
    def test_river_attribute(self):
        m = river()
        X = m.X["_VBWATER"]
        self.assertEqual(len(X), len(m.V))
        self.assertTrue(np.allclose(X[:, 3], 0.5))
        rows = ww.ACROSS
        edge = X[0::rows, 0]
        mid = X[rows // 2::rows, 0]
        self.assertTrue(np.allclose(edge, 0, atol=1e-6) and np.allclose(mid, 1, atol=1e-6))            # 30 ft wide: half width 15 ft < 25 ft, so mid = 1
        self.assertTrue(X[:, 1].max() > 0.2)                                                           # 30 ft over 400 ft = 7.5 %: steep
        self.assertAlmostEqual(float(X[5, 2] * 360), 90.0, delta=1.0)                                  # flows east = bearing 90
        v = m.UV[rows // 2::rows, 1]
        self.assertTrue(np.all(np.diff(v) > 0))                                                        # v grows downstream
        self.assertAlmostEqual(float(v[-1]), 400 / ww.UV_FT, delta=0.5)
        self.assertEqual(m.tri_count, (12 - 1) * (rows - 1) * 2)

    def test_river_slope_zero_when_flat(self):
        X = river(drop_ft=0.0).X["_VBWATER"]
        self.assertTrue(np.allclose(X[:, 1], 0))

    def test_polygon_shore(self):
        P = [(0, 0), (400, 0), (400, 300), (0, 300)]
        m = ww.build_polygon(P, 0.0, "VB_water_lake", 300)
        X = m.X["_VBWATER"]
        self.assertGreater(len(m.V), 8)                                                                # subdivided: interior vertices exist
        self.assertLess(X[:, 0].min(), 1e-6)
        self.assertGreater(X[:, 0].max(), 0.99)                                                        # a 300 ft wide lake has open water > 25 ft from every bank
        self.assertTrue(np.allclose(X[:, 2] * 360, 180))
        self.assertAlmostEqual(float(m.UV[:, 0].max()), 400 / ww.UV_FT, places=4)
        self.assertAlmostEqual(float(m.UV[:, 1].max()), 300 / ww.UV_FT, places=4)                      # v = plan y (south)
        tri = m.subs["VB_water_lake"]
        P3 = m.V[tri]
        area = 0.5 * np.abs(np.cross(P3[:, 1] - P3[:, 0], P3[:, 2] - P3[:, 0])[:, 2]).sum()
        self.assertAlmostEqual(area / (FT * FT), 400 * 300, delta=1)                                   # the triangles tile the polygon exactly

    def test_glb_round_trip(self):
        m = river(6)
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "water.glb")
            wm.write_glb(path, [("wat_x", m.translated([0, 0, 0]), {"id": "wat_x", "vbWater": {"preset": "river"}})], {}, textures="none")
            nodes, g = wm.read_glb(path)
            self.assertIn("_VBWATER", g["meshes"][0]["primitives"][0]["attributes"])
            self.assertEqual(g["materials"][0]["name"], "VB_water_river")
            self.assertEqual(g["materials"][0]["alphaMode"], "BLEND")
            self.assertNotIn("images", g)                                                              # procedural: no texture files
            self.assertEqual(nodes[0][1]["vbWater"]["preset"], "river")
            self.assertTrue(np.allclose(nodes[0][2].X["_VBWATER"], m.X["_VBWATER"], atol=1e-6))
            import glb_check
            self.assertFalse(glb_check.validate_glb(path))

    def test_merge_keeps_attribute_only_when_all_have_it(self):
        a, b = river(4), river(4)
        self.assertIn("_VBWATER", wm.merge_meshes([a, b]).X)
        plain = wm.Mesh(np.zeros((3, 3)), np.zeros((3, 2)), {"m": [[0, 1, 2]]})
        self.assertNotIn("_VBWATER", wm.merge_meshes([a, plain]).X)

    def test_build_entity(self):
        class Fr:
            height_ft, z_origin_ft = 500.0, 0.0
            to_blender = staticmethod(lambda x, y, z=None: (x * FT, (500.0 - y) * FT))

        class Cx:
            fr = Fr()
            B = staticmethod(lambda x, y: (x * FT, (500.0 - y) * FT))
        e = {"id": "wat_a", "kind": "stream", "centerline": [[0, 100], [100, 100], [200, 110]], "widths_ft": [10, 10, 12], "surface_elevations_ft": [20, 15, 10]}
        m, ex = ww.build(Cx(), e, None)
        self.assertEqual(list(m.subs), ["VB_water_river"])
        self.assertEqual(ex["vbWater"]["preset"], "river")
        e2 = {"id": "wat_b", "kind": "pond", "polygon": [[0, 0], [60, 0], [60, 40], [0, 40]], "level_ft": 5}
        m2, ex2 = ww.build(Cx(), e2, {"preset": "ocean", "force": True})
        self.assertEqual(list(m2.subs), ["VB_water_ocean"])
        self.assertEqual(ex2["vbWater"]["mode"], "wind")


class FakeBridge:
    def __init__(self, scripts=True):
        self.calls = []
        self.scene = {"_id": "s1", "name": "T", "flags": {"varrenmoor": {"worldId": "zz_test"}, "levels-3d-preview": {"enableAnimationScripts": scripts}}}
        self.tiles = {"Scene.s1.Tile.w1": {"flags": {"varrenmoor": {"layer": "water", "pipelineId": "model:zz_test:water"}, "levels-3d-preview": {}}},
                      "Scene.s1.Tile.t1": {"flags": {"varrenmoor": {"layer": "terrain", "pipelineId": "model:zz_test:terrain_zz_test"}, "levels-3d-preview": {}}}}

    def call(self, op, **a):
        self.calls.append((op, a))
        if op == "version":
            return {"protocol": 9, "module": "0.5.2"}
        if op == "get":
            return self.scene if a["uuid"] == "Scene.s1" else json.loads(json.dumps(self.tiles[a["uuid"]]))
        if op == "find_by_flag":
            return [{"uuid": u, "pipelineId": d["flags"]["varrenmoor"]["pipelineId"]} for u, d in self.tiles.items()]
        if op == "update":
            d = self.tiles.get(a["uuid"], self.scene)
            for scope, v in a["data"]["flags"].items():
                d["flags"].setdefault(scope, {}).update(v)
            return {"uuid": a["uuid"]}
        raise AssertionError(op)


class Push(unittest.TestCase):
    def test_script_body(self):
        b = fw.script_body()
        self.assertNotIn("\n//", b)
        self.assertIn("VB_water_", b)
        self.assertLess(len(b), 12000)

    def test_decorate(self):
        doc = {"place": "zz_test", "files": [{"id": "model:zz_test:water", "layer": "water", "layers": ["water"]}, {"id": "model:zz_test:terrain", "layer": "terrain"}]}
        items = [{"id": "model:zz_test:water", "data": {"flags": {"levels-3d-preview": {"model3d": "x"}, "varrenmoor": {"layer": "water"}}}},
                 {"id": "model:zz_test:terrain", "data": {"flags": {"levels-3d-preview": {"model3d": "y"}, "varrenmoor": {"layer": "terrain"}}}}]
        fw.decorate_items(items, doc, {"preset": "river", "values": {"river": {"flow_speed": 2.5}}})
        w = items[0]["data"]["flags"]
        self.assertIn("onAnimation", w["levels-3d-preview"])
        self.assertEqual(w["levels-3d-preview"]["model3d"], "x")
        self.assertEqual(w["varrenmoor"]["water"]["presets"]["river"]["flow_speed"], 2.5)
        self.assertNotIn("onAnimation", items[1]["data"]["flags"]["levels-3d-preview"])

    def run_cmd(self, br, *args):
        import io
        import contextlib
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fw.main(list(args), br)
        return rc, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_install_idempotent_and_set(self):
        br = FakeBridge()
        rc, r = self.run_cmd(br, "install-water", "--scene-uuid", "Scene.s1", "--no-panel")
        self.assertEqual(rc, 0, r)
        self.assertEqual([t["status"] for t in r["tiles"]], ["updated"])                  # only the water tile; the terrain tile is untouched
        self.assertNotIn("onAnimation", br.tiles["Scene.s1.Tile.t1"]["flags"]["levels-3d-preview"])
        self.assertIn("onAnimation", br.tiles["Scene.s1.Tile.w1"]["flags"]["levels-3d-preview"])
        rc, r = self.run_cmd(br, "install-water", "--scene-uuid", "Scene.s1", "--no-panel")
        self.assertEqual([t["status"] for t in r["tiles"]], ["unchanged"])
        rc, r = self.run_cmd(br, "set-water", "--scene-uuid", "Scene.s1", "--no-panel", "--preset", "river", "--set", "flow_speed=3", "--set", "foam=0.9")
        self.assertEqual([t["status"] for t in r["tiles"]], ["updated"])
        wf = br.tiles["Scene.s1.Tile.w1"]["flags"]["varrenmoor"]["water"]
        self.assertEqual(wf["presets"]["river"]["flow_speed"], 3.0)
        self.assertEqual(wf["presets"]["river"]["foam"], 0.9)
        self.assertIsNone(wf["force"])
        rc, r = self.run_cmd(br, "set-water", "--scene-uuid", "Scene.s1", "--no-panel", "--preset", "ocean", "--force")
        self.assertEqual(br.tiles["Scene.s1.Tile.w1"]["flags"]["varrenmoor"]["water"]["force"], "ocean")

    def test_bad_input_and_dry_run(self):
        br = FakeBridge(scripts=False)
        rc, r = self.run_cmd(br, "set-water", "--scene-uuid", "Scene.s1", "--no-panel", "--set", "foam=1")
        self.assertEqual(rc, 1)
        self.assertIn("--preset", r["error"])
        rc, r = self.run_cmd(br, "set-water", "--scene-uuid", "Scene.s1", "--no-panel", "--preset", "river", "--set", "bogus=1")
        self.assertEqual(rc, 1)
        rc, r = self.run_cmd(br, "install-water", "--scene-uuid", "Scene.s1", "--no-panel", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual(r["tiles"][0]["status"], "would update")
        self.assertTrue(r["warnings"] and "enableAnimationScripts" in r["warnings"][0])
        self.assertFalse([c for c in br.calls if c[0] == "update"])                          # dry run writes nothing
        rc, r = self.run_cmd(br, "install-water", "--scene-uuid", "Scene.s1", "--no-panel", "--enable-scripts")
        self.assertTrue(r["scene_scripts_enabled"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
