"""Home interior style presets (interior_styles.py, presets/interiors/presets.json, worldpack_interiors.py).
  python illustrator/generators/test_interior_styles.py"""
import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import interior_styles as ist  # noqa: E402
import interior_styles_preview as isp  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_interiors as wi  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

STYLES = ["plain", "rustic_cottage", "farmhouse", "burgher_townhouse", "poor_hovel"]


class PresetTable(unittest.TestCase):
    def test_required_styles(self):
        self.assertEqual(ist.names(), STYLES)
        self.assertEqual(ist.choices()[0], "auto")

    def test_materials_exist(self):
        for nm in STYLES:
            for role, mid in ist.get(nm)["mats"].items():
                if mid is None:
                    continue
                self.assertTrue(mid in wd.DETAIL_MATS or mid in pbr.CATALOG, f"{nm}.{role} -> {mid} unknown to the pack")
        for mid in ("mat_pottery", "mat_herb", "mat_linen", "mat_int_rug", "mat_int_plank", "mat_int_lime"):
            self.assertIn(mid, wd.DETAIL_MATS)

    def test_new_generators_tile(self):
        for g in ("rplank", "lime", "rug"):
            alb, h = pbr.GENERATORS[g]()
            self.assertEqual(alb.shape[:2], h.shape)
            self.assertEqual(alb.shape[2], 3)
            self.assertTrue(np.isfinite(alb).all() and np.isfinite(h).all())

    def test_resolution_order(self):
        self.assertEqual(ist.resolve_name({"kind": "house"}), "rustic_cottage")
        self.assertEqual(ist.resolve_name({"kind": "farmhouse"}), "farmhouse")
        self.assertEqual(ist.resolve_name({"kind": "tenement"}), "poor_hovel")
        self.assertEqual(ist.resolve_name({"kind": "townhouse"}), "burgher_townhouse")
        self.assertEqual(ist.resolve_name({}), "rustic_cottage")                       # no kind = a plain home
        for k in ("inn", "tavern", "shop", "barn", "civic", "mill"):
            self.assertEqual(ist.resolve_name({"kind": k}), "plain", k)               # only homes change
        self.assertEqual(ist.resolve_name({"kind": "house"}, "farmhouse"), "farmhouse")        # scene setting beats the kind default
        self.assertEqual(ist.resolve_name({"kind": "house"}, "plain"), "plain")
        self.assertEqual(ist.resolve_name({"kind": "house", "interior_style": "poor_hovel"}, "farmhouse"), "poor_hovel")   # building beats scene
        self.assertEqual(ist.resolve_name({"kind": "house", "interior_style": "nonsense"}, "bogus"), "rustic_cottage")     # unknown -> auto
        self.assertEqual(ist.resolve_name({"kind": "inn"}, "rustic_cottage"), "rustic_cottage")                              # a scene style applies to every building with an interior

    def test_scene_style_from_manifest(self):
        pk = types.SimpleNamespace(manifest={"foundry": {"interior_style": "farmhouse"}})
        self.assertEqual(ist.scene_style(pk), "farmhouse")
        self.assertEqual(ist.scene_style(types.SimpleNamespace(manifest={})), "auto")
        self.assertEqual(ist.scene_style(types.SimpleNamespace()), "auto")

    def test_cli_choices_match_presets(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            wp.main(["export", "-h"])
        for nm in ist.choices():
            self.assertIn(nm, buf.getvalue())

    def test_set_interior_style_writes_manifest(self):
        with tempfile.TemporaryDirectory() as t:
            with open(os.path.join(t, "manifest.json"), "w") as f:
                json.dump({"foundry": {"roof_mode": "none"}}, f)
            self.assertEqual(wp.set_interior_style(t, "Rustic_Cottage"), "rustic_cottage")
            with open(os.path.join(t, "manifest.json")) as f:
                m = json.load(f)
            self.assertEqual(m["foundry"]["interior_style"], "rustic_cottage")
            self.assertEqual(m["foundry"]["roof_mode"], "none")
            self.assertEqual(wp.set_interior_style(t, "bogus"), "auto")


class Geometry(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = {}
        for floors in (1, 2):
            for nm in STYLES:
                nodes, e = isp.build_sample(nm, floors)
                cls.res[(nm, floors)] = (nodes, e, isp.stats(nodes))

    def test_all_styles_build_with_interior_nodes(self):
        for (nm, f), (nodes, e, st) in self.res.items():
            names = [n for n, _, _ in nodes]
            self.assertIn("bld_sample_int_f0", names, (nm, f))
            self.assertIn("bld_sample_roof", names, (nm, f))
            self.assertTrue(any("_props_" in n for n in names), (nm, f))

    def test_plain_is_unchanged_look(self):
        st = self.res[("plain", 1)][2]["materials"]
        self.assertIn("mat_plaster", st)
        self.assertIn("mat_interior_floor", st)
        self.assertFalse([m for m in st if m.startswith("mat_int_")])

    def test_styles_use_their_materials(self):
        for nm in STYLES[1:]:
            mats = set(self.res[(nm, 1)][2]["materials"])
            M = ist.get(nm)["mats"]
            self.assertIn(M["floor"], mats, nm)
            self.assertIn(M["wall"], mats, nm)
            self.assertNotIn("mat_interior_floor", mats, nm)

    def test_rustic_features(self):
        mats = self.res[("rustic_cottage", 1)][2]["materials"]
        for m in ("mat_int_plank", "mat_int_frame", "mat_int_rug", "mat_pottery", "mat_herb", "mat_straw", "mat_int_stone"):
            self.assertIn(m, mats, m)

    def test_poor_hovel_is_sparse_earth_and_straw(self):
        mats = self.res[("poor_hovel", 1)][2]["materials"]
        self.assertIn("mat_int_earth", mats)
        self.assertIn("mat_straw", mats)
        self.assertNotIn("mat_int_rug", mats)
        self.assertLess(self.res[("poor_hovel", 1)][2]["interior_tris"], self.res[("plain", 1)][2]["interior_tris"])

    def test_triangle_budget(self):
        for f in (1, 2):
            base = self.res[("plain", f)][2]["total_tris"]
            for nm in STYLES[1:]:
                tot = self.res[(nm, f)][2]["total_tris"]
                self.assertLess(tot, base * 1.8, (nm, f))                       # whole building incl. shell + roof: at most 1.8x the plain one
                self.assertLess(self.res[(nm, f)][2]["interior_tris"], 3500 * f, (nm, f))

    def test_geometry_finite_and_inside_footprint(self):
        cx = isp.make_ctx()
        for (nm, f), (nodes, e, st) in self.res.items():
            xs = [p[0] for p in e["polygon"]]
            ys = [p[1] for p in e["polygon"]]
            lo = np.array(cx.B(min(xs), min(ys)))
            hi = np.array(cx.B(max(xs), max(ys)))
            bx0, bx1 = sorted((lo[0], hi[0]))
            by0, by1 = sorted((lo[1], hi[1]))
            for n, mm, ex in nodes:
                self.assertTrue(np.isfinite(mm.V).all(), (nm, n))
                if "interior" in (ex.get("tags") or []):
                    pad = 0.35
                    self.assertGreaterEqual(mm.V[:, 0].min(), bx0 - pad, (nm, n))
                    self.assertLessEqual(mm.V[:, 0].max(), bx1 + pad, (nm, n))
                    self.assertGreaterEqual(mm.V[:, 1].min(), by0 - pad, (nm, n))
                    self.assertLessEqual(mm.V[:, 1].max(), by1 + pad, (nm, n))

    def test_deterministic(self):
        a = isp.stats(isp.build_sample("rustic_cottage", 2)[0])
        b = isp.stats(isp.build_sample("rustic_cottage", 2)[0])
        self.assertEqual(a, b)

    def test_scene_and_building_selection_reaches_mesh(self):
        cx = isp.make_ctx()
        e = isp.sample_entity(1, "house")                                  # no per-building key: kind default
        m, dn = wd.build_building_detailed(cx, e)
        self.assertIn("mat_int_plank", wi.add_interior(cx, e, m, dn)[0].subs)
        cx.pack.manifest = {"foundry": {"interior_style": "plain"}}        # scene setting
        m, dn = wd.build_building_detailed(cx, e)
        self.assertIn("mat_interior_floor", wi.add_interior(cx, e, m, dn)[0].subs)
        e["interior_style"] = "poor_hovel"                                 # per building wins
        m, dn = wd.build_building_detailed(cx, e)
        self.assertIn("mat_int_earth", wi.add_interior(cx, e, m, dn)[0].subs)

    def test_non_home_kinds_stay_plain(self):
        nodes, e = isp.build_sample(None, 1, kind="inn")
        self.assertIn("mat_interior_floor", isp.stats(nodes)["materials"])

    def test_inner_skin_uses_style_wall(self):
        nodes, e = isp.build_sample("farmhouse", 1)
        shell = [mm for n, mm, ex in nodes if "shell" in (ex.get("tags") or [])][0]
        self.assertIn("mat_int_lime", shell.subs)


if __name__ == "__main__":
    unittest.main()
