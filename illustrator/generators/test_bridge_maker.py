"""Tests for the bridge maker (python test_bridge_maker.py): presets, clearance never intersected, deck continuity, determinism, scale 10-200 ft,
stable ids, road trimming, detection of the floating-road bug, pack injection."""
import copy
import math
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
        self.assertEqual(set(PRESETS), {"stone_arch", "brick_arch", "flat_cut_stone", "wooden_truss", "plank_footbridge", "rough_log", "covered_timber", "rope_plank"})
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
            R = plan["rope"]["raise_m"] if pid == "rope_plank" else 0.0                # a rope bridge's anchors may be raised (ramp up to them)
            self.assertAlmostEqual(d[0][1], z0 + R, places=3, msg=pid)
            self.assertAlmostEqual(d[-1][1], z1 + R, places=3, msg=pid)
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


class NewStyleTests(unittest.TestCase):
    def test_rough_log_is_irregular_and_rests_on_rocks(self):
        plan = bm.make_plan(bm.sample_entity("rough_log", 18.0, 6.0, wall_slope=1.0))
        logs = plan["logs"]
        self.assertGreaterEqual(len(logs), 3)
        self.assertLessEqual(len(logs), 6)
        self.assertGreater(len({round(l["r"], 3) for l in logs}), 2)                 # different diameters
        self.assertGreater(len({round(l["a"], 3) for l in logs}), 2)                 # different lengths / ends
        self.assertAlmostEqual(sum(2 * l["r"] for l in logs), plan["W"], places=6)  # side by side, filling the width
        self.assertEqual(len(plan["rocks"]), 4)
        self.assertLessEqual(len(plan["trestle_u"]), 1)
        self.assertTrue(plan["ok"])

    def test_rough_log_trestles_for_long_spans(self):
        FTm = FT
        for span, drop in ((28, 10), (40, 12), (56, 14), (60, 14), (66, 14)):
            ent = bm.sample_entity("rough_log", float(span), float(drop), wall_slope=0.9)
            m, plan = bm.build_local(ent)
            self.assertTrue(plan["ok"], (span, plan["notes"]))
            self.assertGreaterEqual(len(plan["trestles"]), 1, span)
            self.assertLessEqual(plan["log_max_m"], 26.0 * FTm + 1e-6, span)             # no log longer than 26 ft
            self.assertEqual(bm.check_clearance(m, plan), 0, span)
            tr_u = sorted(t["u"] for t in plan["trestles"])
            for lg in plan["logs"]:                                                      # the lane is covered end to end (a joint per trestle, 6 cm gap)
                segs = lg["segs"]
                self.assertEqual(len(segs), len(tr_u) + 1)
                self.assertAlmostEqual(segs[0][0], lg["a"])
                self.assertAlmostEqual(segs[-1][1], lg["b"])
                for (a0, b0), (a1, b1) in zip(segs[:-1], segs[1:]):
                    self.assertAlmostEqual(a1 - b0, 0.06, places=6)
            gl = bm.Prof([(u * FTm, g * FTm) for u, g in ent["context"]["ground_lo"]])
            for tr in plan["trestles"]:
                self.assertEqual(len(tr["legs"]), 4)
                for lgx in tr["legs"]:
                    self.assertLess(lgx["base"], float(gl(lgx["u"])) - 1.5 * FTm + 1e-6)     # legs end below the bed / ground
        self.assertFalse(bm.make_plan(bm.sample_entity("rough_log", 90.0, 14.0))["ok"])  # beyond ~70 ft even trestles do not help
        p28 = bm.make_plan(bm.sample_entity("rough_log", 28.0, 10.0, wall_slope=0.9))
        self.assertTrue(p28["ok"], p28["notes"])                                         # the old failing case (28 ft vs a 26 ft limit)

    def test_covered_variants_piles_and_piers(self):
        for sup in ("piles", "piers"):
            for roof in ("shingle", "tile"):
                ent = bm.sample_entity("covered_timber", 70.0, 14.0, wall_slope=0.5)
                ent["params"] = {"support": sup, "roof": roof, "flower_boxes": sup == "piles"}
                m, plan = bm.build_local(ent)
                self.assertTrue(plan["ok"], plan["notes"])
                kinds = {s["kind"] for s in plan["supports"]}
                self.assertIn("pier" if sup == "piers" else "bent", kinds)
                self.assertEqual(bm.check_clearance(m, plan), 0)
                self.assertTrue(any(k.startswith("mat_s_tint_" + ("red_tile" if roof == "tile" else "shingle")) for k in m.subs), list(m.subs))
                self.assertGreater(m.V[:, 2].max() - ent["context"]["deck"][0][1] * FT, 2.5)     # a roof stands well above the deck

    def test_rope_sag_clamped_above_ground(self):
        for span, drop, ws in ((40, 8, 0.35), (60, 22, 0.35), (120, 24, 0.3), (60, 10, 0.9), (30, 4, 0.9)):
            ent = bm.sample_entity("rope_plank", span, drop, wall_slope=ws)
            plan = bm.make_plan(ent)
            gh = bm.Prof([(u * FT, g * FT) for u, g in ent["context"]["ground_hi"]])
            D = bm.Prof(plan["deck"])
            us = np.linspace(0.12 * plan["L"], 0.88 * plan["L"], 80)
            gap = D(us) - gh(us)
            self.assertGreaterEqual(float(gap.min()), 0.099, (span, drop))              # never into the ground
            if not plan["rope"]["clamped"]:
                self.assertAlmostEqual(plan["rope"]["sag_m"], plan["rope"]["wanted_m"], places=6)
            self.assertLessEqual(plan["rope"]["sag_m"], plan["rope"]["wanted_m"] + 1e-9)
        shallow = bm.make_plan(bm.sample_entity("rope_plank", 60.0, 22.0, wall_slope=0.35))
        tight = bm.make_plan(bm.sample_entity("rope_plank", 60.0, 14.0, wall_slope=0.9))
        self.assertGreaterEqual(shallow["rope"]["sag_m"], tight["rope"]["sag_m"] - 1e-9)  # less room = less (or equal) sag; the anchors rise first
        self.assertGreaterEqual(tight["rope"]["raise_m"], shallow["rope"]["raise_m"])

    def test_rope_sag_is_visible_and_scales_with_span(self):
        """Sag is 8-12 % of the span: the anchors are raised so it is reached, the clamp is a last resort and is reported."""
        for span, drop in ((40, 10), (64, 10), (100, 14)):
            ent = bm.sample_entity("rope_plank", float(span), float(drop), wall_slope=0.9)
            plan = bm.make_plan(ent)
            rp = plan["rope"]
            self.assertGreaterEqual(rp["wanted_m"] / plan["L"], 0.0999, span)
            self.assertLessEqual(rp["wanted_m"] / plan["L"], 0.1201, span)
            if not rp["clamped"]:
                self.assertAlmostEqual(rp["sag_m"], rp["wanted_m"], places=6)
                self.assertGreater(rp["sag_m"] / FT, 0.08 * span - 0.2, span)                # visible sag, not 1.3 ft
            else:
                self.assertAlmostEqual(rp["raise_m"], rp["raise_max_m"], places=6)         # clamped only after the anchors reached their maximum height
                self.assertTrue(any("clamped" in n for n in plan["notes"]))
            D = bm.Prof(plan["deck"])
            mid = float(D(plan["L"] / 2))
            ends = 0.5 * (float(D(0.0)) + float(D(plan["L"])))
            self.assertGreater((ends - mid) / FT, 3.0, span)                                # the middle hangs well below the ends
            self.assertGreater(plan["lift_ends"][0], 0.0 if rp["raise_m"] > 0 else -1)
            self.assertGreaterEqual(min(p["top"] for p in plan["posts"]) - float(D(0.0)), plan["p"]["rail_h"] + 0.9)   # tall anchor posts

    def test_rope_has_missing_and_broken_planks_and_sway(self):
        import bridge_geo as bg
        ent = bm.sample_entity("rope_plank", 64.0, 10.0, seed=11, wall_slope=0.9)
        plan = bm.make_plan(ent)
        m0 = bg.build(plan)
        plan2 = bm.make_plan(ent, {"decay": 0.0})
        m1 = bg.build(plan2)
        self.assertGreater(m1.tri_count - m0.tri_count, 40)                              # the decayed bridge loses at least a few planks / ropes
        v = m0.V
        inside = (v[:, 0] > 0.3 * plan["L"]) & (v[:, 0] < 0.7 * plan["L"])
        self.assertGreater(float(np.abs(v[inside, 1]).max()), plan["W"] / 2 + 0.1)       # the deck sways sideways (and ropes with it)

    def test_rope_planks_seeded_decay(self):
        a = bm.build_local(bm.sample_entity("rope_plank", 60.0, 22.0, seed=1, wall_slope=0.35))[0]
        b = bm.build_local(bm.sample_entity("rope_plank", 60.0, 22.0, seed=1, wall_slope=0.35))[0]
        c = bm.build_local(bm.sample_entity("rope_plank", 60.0, 22.0, seed=2, wall_slope=0.35))[0]
        self.assertEqual(mesh_hash(a), mesh_hash(b))
        self.assertNotEqual(mesh_hash(a), mesh_hash(c))
        ent = bm.sample_entity("rope_plank", 60.0, 22.0, seed=4, wall_slope=0.35)
        ent["params"] = {"decay": 0.0}
        m0 = bm.build_local(ent)[0]
        ent["params"] = {"decay": 0.4}
        m1 = bm.build_local(ent)[0]
        self.assertGreater(m0.tri_count, m1.tri_count)                                   # rot removes planks and ropes


class TerrainClearanceTests(unittest.TestCase):
    """B: the deck never sits under the highest terrain beneath it; C: every foot ends below the sampled ground."""

    @classmethod
    def setUpClass(cls):
        DetectTests.setUpClass()
        cls.pack, cls.cell = DetectTests.pack, DetectTests.cell
        cls.h0 = DetectTests.h
        cls.c = [c for c in bm.detect(cls.pack, h_raw=cls.h0) if c["type"] == "gully"][0]
        x0 = cls.pack.get("r_gully")["points"][0][0] + cls.c["s0_ft"]
        X, Y = np.meshgrid(np.arange(cls.h0.shape[1]) * cls.cell, np.arange(cls.h0.shape[0]) * cls.cell)
        cls.bump = cls.h0 + (5.0 * np.exp(-((X - x0) ** 2 + (Y - 200) ** 2) / (2 * 9.0 ** 2))).astype(np.float32)     # terrain rising 5 ft above the road at the start abutment

    def test_deck_clears_terrain_at_ends_all_styles(self):
        for pid in PRESETS:
            ent = bm.make_entity(self.pack, self.c, self.bump, preset=pid)
            plan = bm.make_plan(ent)
            self.assertGreater(plan["lift_ends"][0], 0.05, pid)                           # the start end had to be lifted
            D = bm.Prof(plan["deck"])
            gh = bm.Prof([(u * FT, g * FT) for u, g in ent["context"]["ground_hi"]])
            us = np.linspace(0, plan["L"], 200)
            self.assertGreaterEqual(float((D(us) - gh(us)).min()), 0.09, pid)             # deck above the highest terrain (>= 0.1 m)
            m, _ = bm.build_local(ent)
            self.assertLess(m.V[:, 0].min(), -0.3, pid)                                   # an approach ramp / posts beyond the start

    def test_flat_terrain_needs_no_lift(self):
        for pid in PRESETS:
            ent = bm.make_entity(self.pack, self.c, self.h0, preset=pid)
            self.assertFalse(ent["context"]["deck_lift"], pid)

    def test_lift_is_slope_limited_and_capped(self):
        us = np.linspace(0, 100, 51)
        gh = np.zeros(51)
        gh[0:3] = 20.0
        lift, over = bm.compute_lift(us, np.zeros(51), gh)
        self.assertLessEqual(float(lift.max()), bm.DEFAULTS["max_lift_ft"])
        self.assertGreater(over, 0)
        self.assertLessEqual(float(np.abs(np.diff(lift) / np.diff(us)).max()), bm.DEFAULTS["lift_slope"] + 1e-9)

    def _check_feet(self, ent, margin_ft=1.5):
        plan = bm.make_plan(ent)
        gl = bm.Prof([(u * FT, g * FT) for u, g in ent["context"]["ground_lo"]])
        self.assertTrue(plan["feet"])
        for ft in plan["feet"]:
            self.assertLessEqual(ft["z"], float(gl(ft["u"])) - margin_ft * FT + 1e-6, (ent["preset"], ft))
        return plan

    def test_foot_bottoms_below_bumpy_ground_all_styles(self):
        rng = np.random.RandomState(3)
        for pid in PRESETS:
            for span in (14, 40, 90):
                ent = bm.sample_entity(pid, span, 12.0, wall_slope=0.6, seed=span)
                n = len(ent["context"]["ground_hi"])
                noise = rng.uniform(-1.2, 1.2, n)
                for key in ("ground_hi", "ground_lo"):
                    ent["context"][key] = [[u, g + float(e)] for (u, g), e in zip(ent["context"][key], noise)]
                self._check_feet(ent)

    def test_foot_bottoms_below_real_terrain_samples(self):
        import worldpack as wp
        for pid in PRESETS:
            ent = bm.make_entity(self.pack, self.c, self.bump, preset=pid)
            plan = self._check_feet(ent)
            sx, sy, _ = ent["span"]["start"]
            ex, ey, _ = ent["span"]["end"]
            L = math.hypot(ex - sx, ey - sy)
            d = np.array([ex - sx, ey - sy]) / L
            lf = np.array([d[1], -d[0]])
            for ft in plan["feet"]:
                u = min(max(ft["u"] / FT, 0.0), L)
                vals = [wp.bilinear(self.bump, self.cell, sx + d[0] * u + lf[0] * v, sy + d[1] * u + lf[1] * v) for v in np.linspace(-ent["span"]["width_ft"] / 2, ent["span"]["width_ft"] / 2, 5)]
                self.assertLessEqual(ft["z"] / FT, min(vals) - 1.4, (pid, ft))


    def test_feet_and_deck_against_terrain_mesh_triangles_all_styles(self):
        """The final mesh, not the raster: audit_mesh samples road_grade.mesh_height (the build_terrain triangulation)."""
        for pid in PRESETS:
            ent = bm.make_entity(self.pack, self.c, self.bump, preset=pid)
            a = bm.audit_mesh(ent, self.bump, self.cell)
            self.assertTrue(a["feet"], pid)
            self.assertGreaterEqual(a["min_foot_margin_ft"], 1.4, (pid, [f for f in a["feet"] if f["margin_ft"] < 1.4][:2]))
            self.assertGreaterEqual(a["deck_clear_min_ft"], 0.3, pid)                    # deck above the terrain triangles everywhere ...
            self.assertGreaterEqual(a["deck_clear_ends_ft"], 0.3, pid)                   # ... and at both ends

    def test_audit_catches_a_foot_above_the_ground(self):
        ent = bm.make_entity(self.pack, self.c, self.bump, preset="stone_arch")
        plan = bm.make_plan(ent)
        plan["feet"] = [dict(f, z=f["z"] + 30.0) for f in plan["feet"]]               # lift every foot 30 m: must be reported
        a = bm.audit_mesh(ent, self.bump, self.cell, plan)
        self.assertLess(a["min_foot_margin_ft"], 0.0)

    def test_final_heights_match_the_built_terrain_when_graded(self):
        import types
        pk = types.SimpleNamespace(heights=self.h0, cell_ft=self.cell, place="x", list=lambda t=None: [], entities={})
        import worldpack as wp
        orig = wp.carved_heights
        try:
            wp.carved_heights = lambda pack: self.h0 + 1.0
            self.assertTrue(np.allclose(bm.final_heights(pk), self.h0 + 1.0))             # graded: the carved terrain itself (no conform)
        finally:
            wp.carved_heights = orig


class CoveredSupportTests(unittest.TestCase):
    """Bents and piers stand in the river at spacing, from below the bed up to the deck, and the two variants look different."""

    def _plan(self, sup, span=70.0):
        ent = bm.sample_entity("covered_timber", span, 14.0, wall_slope=0.5, seed=5)
        ent["params"] = {"support": sup, "roof": "tile" if sup == "piers" else "shingle", "flower_boxes": sup == "piles"}
        m, plan = bm.build_local(ent)
        return ent, m, plan

    def _verts(self, m, mat_pred, u0, u1):
        sel = []
        for k, F in m.subs.items():
            if mat_pred(k):
                sel.append(m.V[np.unique(F.ravel())])
        V = np.concatenate(sel) if sel else np.zeros((0, 3))
        return V[(V[:, 0] >= u0) & (V[:, 0] <= u1)]

    def test_supports_stand_in_the_water_at_spacing(self):
        for sup, kind in (("piles", "bent"), ("piers", "pier")):
            ent, m, plan = self._plan(sup)
            self.assertTrue(plan["ok"], plan["notes"])
            inner = [s for s in plan["supports"] if s["kind"] == kind]
            self.assertGreaterEqual(len(inner), 2, sup)
            wet = [e for e in plan["envelopes"] if e["kind"] == "water"][0]
            self.assertTrue(any(wet["u0"] < s["u"] < wet["u1"] for s in inner), (sup, "no support stands in the water"))
            us = [0.0] + [s["u"] for s in inner] + [plan["L"]]
            self.assertLessEqual(max(np.diff(us)), plan["p"]["max_span"] + 1e-6, sup)     # spacing never above the preset bay
            self.assertEqual(bm.check_clearance(m, plan), 0, sup)
            self.assertEqual(len(plan["wade"]), len(inner))
            gl = bm.Prof([(u * FT, g * FT) for u, g in ent["context"]["ground_lo"]])
            for s in inner:
                self.assertLess(s["base"], float(gl(s["u"])) - 1.5 * FT + 1e-6)           # foot below the bed
                zs = wet["z"]
                stone = lambda k: k == "mat_wall_stone"
                wood = lambda k: k.startswith("mat_s_log")
                V = self._verts(m, stone if sup == "piers" else wood, s["u"] - s["half"] - 0.05, s["u"] + s["half"] + 0.05)
                self.assertGreater(len(V), 8, (sup, s["u"]))
                self.assertLess(V[:, 2].min(), float(gl(s["u"])) - 1.0 * FT, sup)         # reaches below the bed
                self.assertGreater(V[:, 2].max(), zs + 1.0, sup)                           # rises well above the water to the deck

    def test_variants_differ_clearly(self):
        _, m1, p1 = self._plan("piles")
        _, m2, p2 = self._plan("piers")
        stone_support_faces = lambda m, p: sum(
            int(((m.V[F[:, 0]][:, 0] > s["u"] - s["half"] - 0.4) & (m.V[F[:, 0]][:, 0] < s["u"] + s["half"] + 0.4) & (m.V[F[:, 0]][:, 2] < p["deck"][0][1] - 2.0)).sum())
            for k, F in m.subs.items() if k == "mat_wall_stone" for s in p["supports"] if s["kind"] in ("bent", "pier"))
        self.assertEqual(stone_support_faces(m1, p1), 0)                                   # bents are all timber
        self.assertGreater(stone_support_faces(m2, p2), 10)                                # piers are stone (with cutwaters)
        self.assertNotEqual(mesh_hash(m1), mesh_hash(m2))
        self.assertTrue(p1["supports"][1]["kind"] == "bent" and p2["supports"][1]["kind"] == "pier")

    def test_supports_stay_out_of_a_road_below(self):
        ent = bm.sample_entity("covered_timber", 70.0, 14.0, water=False)
        m, plan = bm.build_local(ent)
        for s in plan["supports"]:
            if s["kind"] in ("bent", "pier"):
                for e in plan["envelopes"]:
                    self.assertFalse(e["kind"] != "water" and e["u0"] < s["u"] < e["u1"])
        self.assertEqual(bm.check_clearance(m, plan), 0)


class DeckEndsAfterLiftTests(unittest.TestCase):
    def test_plain_samples_keep_road_height_and_have_no_ramp(self):
        for pid in PRESETS:
            plan = bm.make_plan(bm.sample_entity(pid, 50.0, 14.0, wall_slope=0.5))
            self.assertEqual(plan["lift_ends"], (0.0, 0.0), pid)


class ChoosePresetTests(unittest.TestCase):
    def c(self, span, cls="street", drop=10.0, typ="water", ring="commoner", i="brg_x_1", **kw):
        return dict(id=i, span_ft=span, road_class=cls, deck_above_ground_ft=drop, type=typ, ring=ring, **kw)

    def test_every_choice_is_a_real_preset(self):
        for cls in ("path", "footpath", "lane", "alley", "street", "road", "bridge"):
            for span in (6, 16, 30, 55, 80, 150):
                for drop in (3, 20, 120):
                    for cul in ("", "scandinavian", "english", "danish_german", "fantasy_generic"):
                        self.assertIn(bm.choose_preset(self.c(span, cls, drop), culture=cul), PRESETS)

    def test_new_styles_are_reachable_by_general_rules(self):
        self.assertEqual(bm.choose_preset(self.c(40, "path", 6, "gully"), culture="scandinavian"), "rough_log")
        self.assertEqual(bm.choose_preset(self.c(90, "path", 40, "gully")), "rope_plank")
        self.assertEqual(bm.choose_preset(self.c(120, "road", 40), culture="english"), "covered_timber")
        self.assertEqual(bm.choose_preset(self.c(40, "street", 8), culture="scandinavian"), "wooden_truss")
        self.assertEqual(bm.choose_preset(self.c(12, "path"), culture="scandinavian", ), bm.choose_preset(self.c(12, "path"), culture="scandinavian"))
        seen = {bm.choose_preset(self.c(12, "path", 4, i=f"brg_{k}_1"), culture="scandinavian") for k in range(12)}
        self.assertEqual(seen, {"rough_log", "plank_footbridge"})

    def test_spans_respect_preset_limits(self):
        for span in range(6, 200, 7):
            for cls in ("path", "street", "lane"):
                name = bm.choose_preset(self.c(span, cls, 10), culture="scandinavian")
                pr = bm.load_preset(name)
                if pr["family"] == "log":
                    self.assertLessEqual(span, bm.LOG_MAX_SPAN_FT)
                if name == "wooden_truss":
                    self.assertLessEqual(span, bm.TRUSS_MAX_SPAN_FT)

    def test_road_class_and_culture_matter_not_place(self):
        a = bm.choose_preset(self.c(40, "street", 8, ring="district"), culture="english")
        b = bm.choose_preset(self.c(40, "street", 8, ring="district"), culture="scandinavian")
        self.assertNotEqual(a, b)
        self.assertEqual(bm.choose_preset(self.c(30, "lane", 5, ring="authority")), bm.choose_preset(self.c(30, "lane", 5, ring="authority")))

    def test_manual_override_wins(self):
        for name in PRESETS:
            self.assertEqual(bm.choose_preset(self.c(200, "path", 90), override=name), name)
        self.assertEqual(bm.choose_preset(self.c(200, "path", 90), culture="english", override="rough_log"), "rough_log")

    def test_old_defaults_unchanged_for_short_street_water(self):
        self.assertEqual(bm.choose_preset(self.c(10, "street")), "flat_cut_stone")
        self.assertIn(bm.choose_preset(self.c(22, "street", 8, ring="market")), ("brick_arch",))


class BridgeCarveTests(unittest.TestCase):
    """Terrain carving under bridges (mesh level): ground that pokes through the span is cleared, only where the audit fails unless forced."""

    @classmethod
    def setUpClass(cls):
        TerrainClearanceTests.setUpClass.__func__(cls)
        X, Y = np.meshgrid(np.arange(cls.h0.shape[1]) * cls.cell, np.arange(cls.h0.shape[0]) * cls.cell)
        xm = cls.pack.get("r_gully")["points"][0][0] + (cls.c["s0_ft"] + cls.c["s1_ft"]) / 2
        cls.mound = (cls.h0 + 30.0 * np.exp(-((X - xm) ** 2 + (Y - 200) ** 2) / (2 * 8.0 ** 2))).astype(np.float32)   # a hump mid-span, higher than the deck

    def _pack(self, ent, h):
        import types
        pk = types.SimpleNamespace(heights=h, cell_ft=self.cell, place="x", entities={"bridges": [ent]})
        pk.list = lambda t=None: pk.entities.get(t, [])
        return pk

    def test_auto_leaves_a_passing_bridge_alone(self):
        for pid in ("stone_arch", "wooden_truss", "covered_timber"):
            ent = bm.make_entity(self.pack, self.c, self.h0, preset=pid)
            h2, rep = bm.carve_under_bridges(self._pack(ent, self.h0), self.h0, "auto")
            self.assertTrue(np.array_equal(h2, self.h0), pid)
            self.assertFalse(rep[0]["carved"], pid)

    def test_auto_carves_a_failing_bridge_and_the_audit_passes_after(self):
        for pid in PRESETS:
            ent = bm.make_entity(self.pack, self.c, self.h0, preset=pid)                        # planned on flat ground, terrain later rose under it
            before = bm.audit_mesh(ent, self.mound, self.cell)
            self.assertLess(before["deck_clear_min_ft"], 0.3, pid)
            h2, rep = bm.carve_under_bridges(self._pack(ent, self.mound), self.mound, "auto")
            self.assertTrue(rep[0]["carved"] and rep[0]["max_cut_ft"] > 1.0, (pid, rep))
            after = bm.audit_mesh(ent, h2, self.cell)
            self.assertGreaterEqual(after["deck_clear_min_ft"], 0.3, (pid, after["deck_clear_min_ft"]))
            self.assertTrue(bool((h2 <= self.mound + 1e-4).all()), pid)                          # only ever lowers
            far = (slice(0, 10), slice(0, 10))
            self.assertTrue(np.array_equal(h2[far], self.mound[far]), pid)                       # far terrain untouched

    def test_off_and_forced(self):
        ent = bm.make_entity(self.pack, self.c, self.h0, preset="stone_arch")
        pk = self._pack(ent, self.mound)
        self.assertTrue(np.array_equal(bm.carve_under_bridges(pk, self.mound, False)[0], self.mound))
        h2, rep = bm.carve_under_bridges(pk, self.h0 + 8.0, True)
        self.assertEqual(rep[0]["reason"], "forced")

    def test_build_parts_hook_uses_carving(self):
        import worldpack_mesh as wm
        ent = bm.make_entity(self.pack, self.c, self.h0, preset="stone_arch")
        pk = self._pack(ent, self.mound)
        pk.manifest = {}
        h_on = wm.terrain_heights(pk, carve=False, conform=False, road_grade=False)[0]
        h_off = wm.terrain_heights(pk, carve=False, conform=False, road_grade=False, carve_bridges=False)[0]
        self.assertLess(float(h_on.max()), float(h_off.max()) - 5.0)
        self.assertTrue(wm.LAST_BRIDGE_CARVE == [] or wm.LAST_BRIDGE_CARVE[0]["id"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
