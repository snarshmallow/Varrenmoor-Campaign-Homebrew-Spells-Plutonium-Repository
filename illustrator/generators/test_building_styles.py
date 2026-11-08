"""Tests for building style presets (python test_building_styles.py): preset files, deterministic variation, materials/textures, world scale of
the timber frame, no beams across openings, every preset builds through the real detailed-building pipeline, assign CLI on a temp world copy."""
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import building_styles as bs  # noqa: E402
import building_styles_geo as bsg  # noqa: E402
import building_styles_preview as bsp  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

FT = wm.FT
PACK = os.path.join(HERE, "..", "..", "world", "bridgehollow__dyers_walk_local", "export")
WORLD = os.path.join(HERE, "..", "..", "world")
_pack = {}


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def pack():
    if "p" not in _pack:
        _pack["p"] = wp.load_pack(PACK)
        pbr.prepare(_pack["p"].materials)
    return _pack["p"]


def build(pid, bid=None):
    pk = pack()
    e = bsp.sample_entity(pk, pid, pk.list("buildings")[0])
    if bid:
        e["id"] = bid
    e = bs.apply_style(e)
    m, dn = wd.build_building_detailed(wm.Ctx(pk), e)
    return e, m, dn


class PresetFiles(unittest.TestCase):
    def test_counts_and_required_keys(self):
        ps = bs.load_presets()
        self.assertGreaterEqual(len(ps), 20)
        cats = {}
        for p in ps.values():
            for k in ("id", "name", "description", "category", "culture", "wall", "roof", "windows", "kinds", "preview"):
                self.assertIn(k, p, p["id"])
            cats[p["category"]] = cats.get(p["category"], 0) + 1
            self.assertTrue(p["preview"].endswith(p["id"] + ".png"))
        self.assertGreaterEqual(cats["house"], 4)
        self.assertGreaterEqual(cats["town"], 9)
        self.assertGreaterEqual(cats["church"], 3)
        for must in ("tudor", "danish_fachwerk", "falu_cottage", "hanseatic_brick", "niedersachsen_halle", "norse_log", "stave_church", "parish_church", "windmill"):
            self.assertIn(must, ps)

    def test_resolve_is_deterministic_and_varies(self):
        a = bs.resolve("danish_fachwerk", "bld_a")
        self.assertEqual(json.dumps(a, sort_keys=True, default=list), json.dumps(bs.resolve("danish_fachwerk", "bld_a"), sort_keys=True, default=list))
        cols = {bs.resolve("danish_fachwerk", f"bld_{i}")["wall"]["color"] for i in range(40)}
        self.assertGreater(len(cols), 2)                                    # ochre / falu red / white wash variants
        pitches = {round(bs.resolve("tudor", f"b{i}")["roof"]["pitch"], 3) for i in range(20)}
        self.assertGreater(len(pitches), 10)
        self.assertIsNone(bs.resolve("no_such", "x"))

    def test_default_style_by_kind_and_district(self):
        k = lambda kind, dist, i: bs.default_style(kind, dist, i)
        self.assertEqual(k("house", "d1", "b1"), k("house", "d1", "b1"))
        self.assertIn(bs.load_presets()[k("inn", "d1", "b9")]["id"], bs.load_presets())
        same = [k("house", "dis_x", f"b{i}") for i in range(60)]
        top = max(set(same), key=same.count)
        self.assertGreater(same.count(top), 60 * 0.4)                      # a district prefers one look
        self.assertEqual(bs.load_presets()[k("church", "d", "c1")]["category"], "church")
        self.assertIn(k("windmill", None, "w"), ("windmill",))


class Materials(unittest.TestCase):
    def test_dynamic_ids_and_textures(self):
        for mid in ("mat_s_plaster_dacd9f", "mat_s_brick_9b4a36", "mat_s_board_8e2f22", "mat_s_clap_c9c0a8", "mat_s_log_6b4a2e", "mat_s_beam_231b15", "mat_s_turf_5f7a34",
                    "mat_s_tint_thatch_8a7a55", "mat_s_tint_red_tile_9c5238", "mat_s_tint_wall_stone_8f8a7e", "mat_s_flat_1c1a18"):
            self.assertTrue(bs.is_dynamic(mid), mid)
            c = pbr.info(mid)
            self.assertEqual(c["gen"], "style", mid)
            alb, h = pbr.base_texture(mid)
            self.assertEqual(alb.shape[2], 3)
            self.assertTrue(np.isfinite(alb).all() and 0 <= h.min() and h.max() <= 1.0001, mid)
            self.assertGreater(pbr.tile_ft(mid), 1.0)
            rec = bs.material_record(mid)
            self.assertEqual(rec["texture"], f"textures/{mid[4:]}.png")
        self.assertFalse(bs.is_dynamic("mat_plank"))

    def test_brick_scale(self):
        # 4 ft per repeat, 16 courses -> 3 in courses; 6 bricks per course -> 8 in bricks
        self.assertEqual(bs.KINDS["brick"][0], 4.0)
        alb, h = bs.gen_texture("mat_s_brick_9b4a36")
        rows = (h > 0.5).mean(axis=1)
        mortar_rows = int((rows < 0.3).sum())
        self.assertGreaterEqual(mortar_rows, 16 * 2)                       # ~3+ px of mortar line per course at 512 px


class Geometry(unittest.TestCase):
    def test_timber_frame_world_scale(self):
        """Beams 4-6 in wide, studs 2.5-4 ft apart (close studding 1.1 ft), panels at most 4.6 ft tall; nothing inside an opening."""
        S = bs.resolve("tudor", "bld_scale")
        S.update(beam_mat="mat_s_beam_231b15", plinth=None, trim_mat="mat_trim", roof_mat="mat_x")
        for pat, lo, hi in (("braced", 2.4, 4.0), ("square", 2.4, 4.0), ("close", 0.9, 1.4)):
            S["wall"] = dict(S["wall"], pattern=pat, spacing_ft=3.0, jetty_ft=0.0)
            rects = []

            class G:
                def rect(s, X, mat, u0, u1, z0, z1, d, vertical=False, **kw):
                    rects.append((u0, u1, z0, z1, vertical))

                def prism(s, X, mat, quad, d, axis=(1, 0), **kw):
                    rects.append(("brace", quad))
            L = 20 * FT
            holes = [{"u0": 8 * FT, "u1": 11 * FT, "z0": 3.5 * FT, "z1": 7.0 * FT, "kind": "window"}]
            P = [(0, 0), (L, 0), (L, 10), (0, 10)]
            D = [(1, 0), (0, 1), (-1, 0), (0, -1)]
            bsg.wall_frame(G(), 0, lambda u, v, z: (u, v, z), L, holes, P, D, 0.0, 10 * FT, 1, S, -0.3)
            studs = sorted(r for r in rects if r[0] != "brace" and r[4] and r[1] - r[0] < 0.2 * FT * 2.5 and 3.0 * FT < (r[3] - r[2]))
            widths = [(r[1] - r[0]) / FT for r in studs]
            self.assertTrue(all(0.3 <= w <= 0.5 for w in widths), (pat, widths))        # 3.6 - 6 in
            xs = sorted({round((r[0] + r[1]) / 2 / FT, 2) for r in studs if (r[0] + r[1]) / 2 < 8 * FT - 1 or (r[0] + r[1]) / 2 > 11 * FT + 1})
            gaps = [b - a for a, b in zip(xs, xs[1:]) if b - a < 6]
            self.assertTrue(gaps and all(lo <= g <= hi for g in gaps), (pat, gaps))
            for r in rects:
                if r[0] == "brace":
                    continue
                u0, u1, z0, z1, _ = r
                inside = u0 > 8 * FT and u1 < 11 * FT and z0 > 3.5 * FT and z1 < 7 * FT
                self.assertFalse(inside, (pat, r))

    def test_every_preset_builds(self):
        pk = pack()
        for pid in bs.load_presets():
            e, m, dn = build(pid)
            self.assertGreater(m.tri_count, 100, pid)
            self.assertTrue(np.isfinite(m.V).all() and np.isfinite(m.UV).all(), pid)
            mats = set(m.subs)
            S = e["_style"]
            self.assertIn(S["roof_mat"], mats, pid)
            self.assertIn(S["wall_mat"], mats, pid)
            for mid in mats:
                if mid.startswith("mat_s_"):
                    self.assertIsNotNone(bs.material_record(mid), mid)
            if S["wall"]["system"] == "halftimber":
                self.assertIn(S["beam_mat"], mats, pid)
            if S["plinth"]:
                self.assertIn(S["plinth_mat"], mats, pid)
            self.assertEqual(len(dn), 1, pid)                              # the one door leaf stays a separate node
            self.assertLess(m.tri_count, 20000, pid)
            bs.register_materials(pk.materials, S)

    def test_no_style_is_legacy_look(self):
        pk = pack()
        e0 = pk.list("buildings")[0]
        e = dict(e0)
        e.pop("style", None)
        self.assertIs(bs.apply_style(e), e)                                 # no style key: the very same entity (nothing changes)
        e["style"] = "bogus"
        self.assertIs(bs.apply_style(e), e)

    def test_stepped_gable_and_tower_rise_above_roof(self):
        e, m, _ = build("hanseatic_brick")
        zt = (e["base_elevation_ft"] - pack().frame.z_origin_ft + e["wall_height_ft"]) * FT
        self.assertGreater(m.V[:, 2].max(), zt + e["roof"]["ridge_height_ft"] * FT)       # chimney and steps above the ridge
        e, m, _ = build("parish_church")
        self.assertGreater(m.V[:, 2].max(), (e["base_elevation_ft"] - pack().frame.z_origin_ft + 10 + 22 + 24) * FT - 0.5)     # tower + spire

    def test_variation_between_buildings(self):
        _, m1, _ = build("tudor", "bld_alpha")
        _, m2, _ = build("tudor", "bld_beta")
        self.assertNotEqual(m1.tri_count, m2.tri_count)


class ArchedOpenings(unittest.TestCase):
    def test_curves(self):
        import building_styles_arch as bsa
        c = bsa.curve(0.0, 2.0, 1.0, "round_arch")
        self.assertAlmostEqual(c[0][1], 1.0)
        self.assertAlmostEqual(max(z for _, z in c), 2.0, places=6)               # semicircle: rise = w/2
        p = bsa.curve(0.0, 2.0, 0.0, "pointed")
        self.assertAlmostEqual(max(z for _, z in p), math.sqrt(3), places=6)      # equilateral arch: rise = 0.866 w
        self.assertAlmostEqual(p[len(p) // 2][0], 1.0, places=6)                  # apex on the axis
        self.assertAlmostEqual(p[0][0], 0.0)
        self.assertAlmostEqual(p[-1][0], 2.0)
        o = bsa.curve(0.0, 2.0, 0.0, "pointed", 0.4)
        self.assertAlmostEqual(o[0][0], -0.4, places=6)                           # the surround starts exactly beside the jamb

    def test_church_windows_and_doors_are_arched(self):
        import building_styles_arch as bsa
        for pid, wshape, dshape in (("parish_church", ("pointed", "triple_lancet"), "pointed"), ("chapel", ("round_arch",), "pointed"), ("stave_church", ("round_arch",), "round_arch"),
                                    ("town_gatehouse", ("rect",), "round_arch"), ("town_guildhall", ("rect",), "round_arch")):
            e, m, dn = build(pid)
            W, D = e["_style"]["windows"], e["_style"]["door"]
            self.assertIn(W["shape"], wshape, pid)
            self.assertEqual(D["shape"], dshape, pid)
            self.assertEqual(len(dn), 1, pid)
            self.assertIn("mat_glass", m.subs, pid)
            self.assertEqual(len(dn[0]["mesh"].subs), 1, pid)                       # the door node stays one material

    def test_shape_holes_stay_inside_old_span_and_storey(self):
        import building_styles_arch as bsa
        zf = 0.0
        base = [[{"u0": 2.0, "u1": 2.0 + 3 * FT, "z0": 3.5 * FT, "z1": 7.0 * FT, "kind": "window"}, {"u0": 9.0, "u1": 9.0 + 3 * FT, "z0": 13.5 * FT, "z1": 17.0 * FT, "kind": "window"},
                 {"u0": 5.0, "u1": 5.0 + 3.5 * FT, "z0": 0.0, "z1": 7 * FT, "kind": "door"}]]
        for shape in ("pointed", "round_arch", "triple_lancet"):
            W = {"shape": shape, "width_ft": 1.9, "triple_width_ft": 4.8, "height_ft": 7.0, "sill_ft": 2.5}
            out = bsa.shape_holes([[dict(h) for h in base[0]]], W, zf)[0]
            wins = [h for h in out if h["kind"] == "window"]
            self.assertGreaterEqual(len(wins), 2)
            for h in wins:
                self.assertIn(h["shape"], ("pointed", "round_arch"))
                self.assertGreater(h["zs"], h["z0"])                                 # a straight part below the springing line
                storey = int((h["z0"] / FT + 0.01) // 10)
                self.assertLess(h["z1"] / FT, storey * 10 + 9.5)                     # stays under the storey line (interiors keep their floors)
                self.assertTrue(any(abs((h["u0"] + h["u1"]) / 2 - (b["u0"] + b["u1"]) / 2) < 3 * FT for b in base[0] if b["kind"] == "window"))
            spans = sorted((h["u0"], h["u1"]) for h in wins if h["z0"] < 10 * FT)
            for a, b in zip(spans, spans[1:]):
                self.assertLessEqual(a[1], b[0] + 1e-9)                              # no overlap between neighbouring lancets
            self.assertTrue(all(h["u0"] > 2.0 - 1.5 * FT and h["u1"] < 9.0 + 4.5 * FT for h in wins))
            self.assertEqual([h for h in out if h["kind"] == "door"][0]["z0"], 0.0)  # the door hole is untouched

    def test_interiors_layout_windows_get_arches_and_keep_partition_gap(self):
        import building_styles_arch as bsa
        holes = [[{"u0": 4.0, "u1": 4.0 + 3.0 * FT, "z0": 2.0 * FT, "z1": 5.0 * FT, "kind": "window"}]]
        out = bsa.shape_holes(holes, {"shape": "pointed", "width_ft": 1.9, "height_ft": 7.0, "sill_ft": 9.0}, 0.0, has_layout=True)[0]
        self.assertAlmostEqual(out[0]["z0"], 2.0 * FT)                               # layout sill is kept (sill_ft only applies to derived windows)
        self.assertLessEqual(out[0]["u1"] - out[0]["u0"], 3.0 * FT + 1e-9)            # never wider than the span the layout reserved

    def test_rose_window_and_arched_door_leaf(self):
        import building_styles_arch as bsa
        e, m, dn = build("parish_church")
        self.assertEqual(e["_style"]["special"]["rose"]["diameter_ft"], 4.6)
        o = bsa.leaf_outline(3.0, 7.0, "pointed")
        zs = [z for _, z in o]
        self.assertAlmostEqual(max(zs), 7.0, places=6)
        self.assertEqual(o[0], (0, 0))
        area2 = sum(o[k][0] * o[(k + 1) % len(o)][1] - o[(k + 1) % len(o)][0] * o[k][1] for k in range(len(o)))
        self.assertGreater(area2, 0)                                                # counter-clockwise outline
        e2 = dict(e)
        e2["_style"] = dict(e["_style"], special={k: v for k, v in e["_style"]["special"].items() if k != "rose"})
        m2, _ = wd.build_building_detailed(wm.Ctx(pack()), e2)
        self.assertGreater(m.tri_count, m2.tri_count)                                # the rose adds geometry


class AssignCli(unittest.TestCase):
    def test_assign_clear_and_filters(self):
        tmp = tempfile.mkdtemp()
        try:
            place = "bridgehollow__dyers_walk_local"
            os.makedirs(os.path.join(tmp, place, "buildings"))
            for f in os.listdir(os.path.join(WORLD, place, "buildings")):
                shutil.copy(os.path.join(WORLD, place, "buildings", f), os.path.join(tmp, place, "buildings", f))
            os.environ["VB_WORLD_ROOT"] = tmp
            r = bs.assign(place, "falu_cottage", ids=["bld_house_041"])
            self.assertEqual(r["changed"], ["bld_house_041"])
            b = _load(os.path.join(tmp, place, "buildings", "bld_house_041.json"))
            self.assertEqual(b["style"], "falu_cottage")
            self.assertEqual(_load(os.path.join(tmp, place, "buildings", "bld_house_044.json"))["style"], "hanseatic_brick")     # untouched
            self.assertEqual(bs.assign(place, "none", ids=["bld_house_041"])["count"], 1)
            self.assertNotIn("style", _load(os.path.join(tmp, place, "buildings", "bld_house_041.json")))
            self.assertEqual(bs.assign(place, "tudor", kind="house")["count"], 25)
            self.assertEqual(bs.assign(place, "tudor", kind="inn")["count"], 0)
            self.assertEqual(bs.assign(place, "auto", all_=True)["count"], 25)
            self.assertEqual(bs.assign(place, "auto")["count"], 0)             # no filter and no --all: nothing
            with self.assertRaises(SystemExit):
                bs.assign(place, "bogus", ids=["bld_house_041"])
            self.assertEqual(len(bs.summary(place)["buildings"]), 25)
        finally:
            os.environ.pop("VB_WORLD_ROOT", None)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
