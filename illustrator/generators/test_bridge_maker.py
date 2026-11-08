"""Tests for the bridge maker (python test_bridge_maker.py): presets, clearance never intersected, deck continuity, determinism, scale 10-200 ft,
stable ids, road trimming, detection of the floating-road bug, pack injection."""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge_maker as bm  # noqa: E402

FT = bm.FT
PRESETS = [p["id"] for p in bm.list_presets()]


def mesh_hash(m):
    return hash((m.V.round(5).tobytes(), tuple((k, m.subs[k].tobytes()) for k in sorted(m.subs))))


class PresetTests(unittest.TestCase):
    def test_five_presets_valid(self):
        self.assertEqual(set(PRESETS), {"stone_arch", "brick_arch", "flat_cut_stone", "wooden_truss", "plank_footbridge"})
        for p in bm.list_presets():
            self.assertEqual(bm.validate_preset(p), [])

    def test_materials_are_few_and_known(self):
        import worldpack_pbr as pbr
        for pid in PRESETS:
            m, plan = bm.build_local(bm.sample_entity(pid, 60.0))
            self.assertLessEqual(len(m.subs), 5, pid)
            for mid in m.subs:
                self.assertTrue(mid.startswith("mat_"), mid)
                info = pbr.info(mid)
                self.assertGreater(info["tile"], 0)


class ClearanceTests(unittest.TestCase):
    def test_envelope_never_intersected_all_scales(self):
        for pid in PRESETS:
            for span, drop in ((10, 6), (14, 8), (24, 10), (40, 12), (60, 14), (90, 20), (130, 26), (200, 40)):
                for water in (True, False):
                    ent = bm.sample_entity(pid, span, drop, water=water)
                    m, plan = bm.build_local(ent)
                    if plan["ok"]:
                        self.assertEqual(bm.check_clearance(m, plan), 0, f"{pid} {span} ft water={water}")
                    self.assertGreater(m.tri_count, 0)

    def test_arches_fit_when_room_exists(self):
        for pid in ("stone_arch", "brick_arch"):
            for span in (20, 60, 100):
                plan = bm.make_plan(bm.sample_entity(pid, span, 16.0))
                self.assertTrue(plan["ok"], (pid, span, plan["notes"]))
                self.assertGreaterEqual(len(plan["arches"]), 1)

    def test_piers_stay_out_of_envelopes(self):
        plan = bm.make_plan(bm.sample_entity("stone_arch", 120.0, 30.0))
        for s in plan["solids"][1:-1]:
            for e in plan["envelopes"]:
                self.assertFalse(s["u0"] < e["u1"] and s["u1"] > e["u0"], "pier inside an envelope")
        plan = bm.make_plan(bm.sample_entity("wooden_truss", 150.0, 30.0))
        for s in plan["supports"]:
            if s["kind"] == "bent":
                for e in plan["envelopes"]:
                    self.assertFalse(e["u0"] < s["u"] < e["u1"])

    def test_road_envelope_uses_default_clearance(self):
        ent = bm.sample_entity("stone_arch", 40.0, 14.0, water=False)
        env = bm.envelopes_of(ent)
        self.assertEqual(len(env), 1)
        self.assertAlmostEqual(env[0]["z_top_ft"], ent["context"]["others"][0]["z_ft"] + 8.0, places=3)
        self.assertGreaterEqual(env[0]["u1_ft"] - env[0]["u0_ft"], 12.0 - 1e-6)

    def test_clearance_override_changes_envelope(self):
        ent = bm.sample_entity("flat_cut_stone", 30.0, 12.0, water=False)
        ent["params"] = {"clearance_h_ft": 10.0, "clearance_w_ft": 16.0}
        env = bm.envelopes_of(ent)[0]
        self.assertAlmostEqual(env["z_top_ft"], ent["context"]["others"][0]["z_ft"] + 10.0, places=3)
        self.assertGreaterEqual(env["u1_ft"] - env["u0_ft"], 16.0 - 1e-6)


class DeckTests(unittest.TestCase):
    def test_deck_ends_meet_road_ends(self):
        for pid in PRESETS:
            ent = bm.sample_entity(pid, 50.0)
            plan = bm.make_plan(ent)
            d = plan["deck"]
            z0, z1 = ent["context"]["deck"][0][1] * FT, ent["context"]["deck"][-1][1] * FT
            self.assertAlmostEqual(d[0][1], z0, places=3, msg=pid)
            self.assertAlmostEqual(d[-1][1], z1, places=3, msg=pid)
            m, _ = bm.build_local(ent)
            top = m.V[:, 2].max()
            self.assertGreaterEqual(top, z0 - 1e-6)

    def test_arch_hump_slope_is_bounded(self):
        plan = bm.make_plan(bm.sample_entity("stone_arch", 60.0))
        d = np.array(plan["deck"])
        slope = np.abs(np.diff(d[:, 1]) / np.diff(d[:, 0])).max()
        self.assertLess(slope, 0.13)

    def test_trim_runs(self):
        pts = [[0, 0, 10], [50, 0, 12], [100, 0, 14]]
        runs = bm.trim_runs(pts, [{"s0_ft": 30, "s1_ft": 70}])
        self.assertEqual(len(runs), 2)
        self.assertAlmostEqual(runs[0][-1][0], 30)
        self.assertAlmostEqual(runs[0][-1][2], 11.2)
        self.assertAlmostEqual(runs[1][0][0], 70)
        self.assertEqual(bm.trim_runs(pts, [{"s0_ft": 0, "s1_ft": 100}]), [])


class DeterminismTests(unittest.TestCase):
    def test_same_input_same_mesh(self):
        for pid in PRESETS:
            a = bm.build_local(bm.sample_entity(pid, 50.0, seed=3))[0]
            b = bm.build_local(bm.sample_entity(pid, 50.0, seed=3))[0]
            self.assertEqual(mesh_hash(a), mesh_hash(b), pid)

    def test_seed_changes_rough_variation(self):
        a = bm.build_local(bm.sample_entity("wooden_truss", 50.0, seed=1))[0]
        b = bm.build_local(bm.sample_entity("wooden_truss", 50.0, seed=2))[0]
        self.assertNotEqual(mesh_hash(a), mesh_hash(b))

    def test_vertex_count_sane(self):
        for pid in PRESETS:
            for span in (10, 60, 200):
                m, _ = bm.build_local(bm.sample_entity(pid, span, max(6, span / 5)))
                self.assertLess(m.tri_count, 60000, (pid, span))

    def test_no_degenerate_triangles(self):
        for pid in PRESETS:
            m, _ = bm.build_local(bm.sample_entity(pid, 60.0))
            for F in m.subs.values():
                a, b, c = m.V[F[:, 0]], m.V[F[:, 1]], m.V[F[:, 2]]
                area = np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2
                self.assertLess(float((area < 1e-9).mean()), 0.02, pid)


class DetectTests(unittest.TestCase):
    """Detection on a synthetic pack: a road 11 ft above a depression, a road crossing another at a different level, a river."""

    @classmethod
    def setUpClass(cls):
        import worldpack as wp
        cls.wp = wp
        n, cell = 80, 5.0
        X, Y = np.meshgrid(np.arange(n) * cell, np.arange(n) * cell)
        h = 100.0 + 0.0 * X
        h -= 14.0 * np.exp(-((X - 200) ** 2) / (2 * 25.0 ** 2))                       # a gully along y at x = 200
        cls.h = h.astype(np.float32)
        cls.cell = cell

        def road(i, pts, zs, w=16.0, cls_="street"):
            return {"id": i, "class": cls_, "width_ft": w, "points": [[x, y, z] for (x, y), z in zip(pts, zs)], "bridge": None, "ring": "commoner",
                    "surface": {"material": "mat_cobble", "tile_ft": 7}}
        pts = [(40, 200), (150, 200), (250, 200), (360, 200)]
        cls.roads = [road("r_gully", pts, [100, 100, 100, 100]),
                     road("r_low", [(300, 40), (300, 150), (300, 360)], [88, 88, 88], 12.0, "lane")]
        cls.pack = types_pack(cls.roads, cls.h, cell, [])

    def test_floating_deck_is_found(self):
        found = bm.detect(self.pack, h_raw=self.h)
        g = [c for c in found if c["type"] == "gully"]
        self.assertEqual(len(g), 1)
        self.assertEqual(g[0]["road"], "r_gully")
        self.assertGreater(g[0]["deck_above_ground_ft"], 10.0)
        self.assertEqual(g[0]["id"], "brg_r_gully_1")
        self.assertTrue(90 < g[0]["s0_ft"] < 160 < g[0]["s1_ft"] < 240)

    def test_road_over_road_found_and_junction_ignored(self):
        found = bm.detect(self.pack, h_raw=self.h)
        r = [c for c in found if c["type"] == "road"]
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["road"], "r_gully")
        self.assertEqual(r[0]["others"][0]["under"], "r_low")
        self.assertGreaterEqual(r[0]["clearance_needed"]["w_ft"], 12.0)

    def test_ids_stable_across_runs(self):
        a = [c["id"] for c in bm.detect(self.pack, h_raw=self.h)]
        b = [c["id"] for c in bm.detect(self.pack, h_raw=self.h)]
        self.assertEqual(a, b)

    def test_entity_from_crossing_builds(self):
        found = bm.detect(self.pack, h_raw=self.h)
        c = [c for c in found if c["type"] == "gully"][0]
        for pid in PRESETS:
            e = bm.make_entity(self.pack, c, self.h, preset=pid)
            m, plan = bm.build_local(e)
            self.assertGreater(m.tri_count, 100, pid)
            self.assertEqual(e["id"], "brg_r_gully_1")
            self.assertEqual(e["span"]["start"][2], 100.0)
            if plan["ok"]:
                self.assertEqual(bm.check_clearance(m, plan), 0, pid)

    def test_conform_leaves_gap_unfilled(self):
        c = [c for c in bm.detect(self.pack, h_raw=self.h) if c["type"] == "gully"][0]
        pk = types_pack(copy.deepcopy(self.roads), self.h, self.cell, [])
        full = bm.conformed_heights(pk, self.h)
        pk.entities["roads"][0]["gaps"] = [{"bridge": "x", "s0_ft": c["s0_ft"], "s1_ft": c["s1_ft"]}]
        gapped = bm.conformed_heights(pk, self.h)
        j, i = int(200 / self.cell), int(200 / self.cell)
        self.assertGreater(full[i, j], 98.0)                      # without the gap the road bed would fill the gully
        self.assertLess(gapped[i, j], 90.0)                       # with it the gully stays


def types_pack(roads, h, cell, water):
    import types
    import worldpack as wp
    pk = types.SimpleNamespace()
    pk.entities = {"roads": roads, "water": water, "bridges": []}
    pk.list = lambda t=None: pk.entities.get(t, [])
    pk.heights = h
    pk.cell_ft = cell
    pk.get = lambda i: [r for r in roads if r["id"] == i][0]
    pk.place = "synthetic"
    return pk


class FixElevationsTests(unittest.TestCase):
    def test_clip_vertex_values(self):
        import region_extract as rx
        pts = [[0, 0], [100, 0], [200, 0], [300, 0]]
        vals = [10.0, 20.0, 30.0, 40.0]
        cp = [[150, 0], [250, 0]]
        self.assertEqual(rx.clip_vertex_values(pts, vals, cp), [25.0, 35.0])

    def test_dyers_walk_streets_have_one_elevation_per_point(self):
        p = os.path.join(bm.WORLD, "bridgehollow__dyers_walk_local", "streets.json")
        if not os.path.exists(p):
            self.skipTest("no Dyers Walk data")
        for s in json.load(open(p, encoding="utf-8"))["streets"]:
            self.assertEqual(len(s["geometry"]["points"]), len(s["elevations_ft"]), s["id"])


class InjectTests(unittest.TestCase):
    def test_inject_into_pack_dir(self):
        src = os.path.join(bm.WORLD, "bridgehollow__dyers_walk_local", "export")
        if not os.path.exists(os.path.join(src, "manifest.json")):
            self.skipTest("no exported pack")
        import worldpack as wp
        with tempfile.TemporaryDirectory() as td:
            pk = os.path.join(td, "pack")
            os.makedirs(pk)
            for sub in ("entities", "terrain"):
                shutil.copytree(os.path.join(src, sub), os.path.join(pk, sub))
            for f in os.listdir(src):
                if os.path.isfile(os.path.join(src, f)):
                    shutil.copy(os.path.join(src, f), pk)
            road = bm._jload(os.path.join(pk, "entities", "roads.json"))["items"][0]
            ent = bm.sample_entity("stone_arch", 40.0)
            ent["road"] = road["id"]
            ent["span"]["s0_ft"], ent["span"]["s1_ft"] = 10.0, 50.0
            ent["id"] = "brg_%s_1" % road["id"]
            doc = {"place": "x", "bridges": [ent], "removed": []}
            res = bm.inject(pk, "x", doc=doc)
            self.assertEqual(res["bridges"], 1)
            pack = wp.load_pack(pk)
            self.assertEqual([b["id"] for b in pack.list("bridges")], [ent["id"]])
            self.assertEqual(pack.get(road["id"])["gaps"][0]["bridge"], ent["id"])
            self.assertEqual(pack.list("bridges")[0]["tags"]["layer"], "bridges")
            doc["removed"] = [ent["id"]]
            bm.inject(pk, "x", doc=doc)
            self.assertEqual(wp.load_pack(pk).list("bridges"), [])
            self.assertNotIn("gaps", wp.load_pack(pk).get(road["id"]))


if __name__ == "__main__":
    unittest.main(verbosity=1)
