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
            self.assertEqual(len(dn), 0 if pid == "town_gatehouse" else 1, pid)    # the one door leaf stays a separate node (the gatehouse has an open carriage arch instead)
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

    def test_tower_walls_run_through_the_roof(self):
        """The stave tower is one shaft from the floor posts through the roof; no roof sheet passes through the tower volume (parish tower: same cut)."""
        for pid in ("stave_church", "parish_church"):
            pk = pack()
            e, m, _ = build(pid)
            S = e["_style"]
            zf = (e["base_elevation_ft"] - pk.frame.z_origin_ft) * FT
            zt = zf + e["wall_height_ft"] * FT
            R = bsg.Roof(wm.Ctx(pk), e).zt(zt)
            holes = bsg.tower_holes(R, S)
            self.assertTrue(holes, pid)
            for (l0, l1, w0, w1) in holes:
                V = m.V
                L = (V[:, 0] - R.cxm) * R.ex[0] + (V[:, 1] - R.cym) * R.ex[1]
                W = (V[:, 0] - R.cxm) * R.ey[0] + (V[:, 1] - R.cym) * R.ey[1]
                eps = 1e-3
                rm = e["roof"]["surface"]["material"]
                rf = m.subs[rm]
                pts = [((l0 + l1) / 2 + fl * (l1 - l0) * 0.4, (w0 + w1) / 2 + fw * (w1 - w0) * 0.4) for fl in (-1, 0, 1) for fw in (-1, 0, 1)]
                for f in rf:
                    if V[f, 2].mean() > R.zr + 0.05 or V[f, 2].mean() < zt + 0.3:
                        continue                                  # skirts, spire and the eave strip are not the main roof sheet
                    a, b_, c_ = [np.array([L[i], W[i]]) for i in f]
                    den = (b_[1] - c_[1]) * (a[0] - c_[0]) + (c_[0] - b_[0]) * (a[1] - c_[1])
                    if abs(den) < 1e-12:
                        continue
                    for (pl, pw_) in pts:
                        u = ((b_[1] - c_[1]) * (pl - c_[0]) + (c_[0] - b_[0]) * (pw_ - c_[1])) / den
                        v = ((c_[1] - a[1]) * (pl - c_[0]) + (a[0] - c_[0]) * (pw_ - c_[1])) / den
                        self.assertFalse(u > 1e-6 and v > 1e-6 and 1 - u - v > 1e-6, f"{pid}: roof sheet passes through the tower footprint")
                # the walls reach the plate (stave: the posts reach the floor) and rise above the ridge
                on = (np.abs(L - l0) < eps) | (np.abs(L - l1) < eps)
                on &= (W > w0 - eps) & (W < w1 + eps)
                zs = V[on, 2]
                self.assertLessEqual(zs.min(), zt + 1e-6, pid)
                self.assertGreater(zs.max(), R.zr + 2 * FT, pid)
                if pid == "stave_church":
                    self.assertLessEqual(zs.min(), zf + 1e-6)
                    self.assertGreater(len(zs[(zs > zt + 0.1) & (zs < R.zr - 0.1)]), 0)       # wall vertices between plate and ridge: the shaft passes the roof plane

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
            self.assertEqual(len(dn), 0 if pid == "town_gatehouse" else 1, pid)
            self.assertIn("mat_glass", m.subs, pid)
            if dn:
                self.assertEqual(len(dn[0]["mesh"].subs), 1, pid)                   # the door node stays one material

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


class RoseWindowIsReal(unittest.TestCase):
    """The gable rose is an opening in the gable (no wall triangle covers it), glazed, and trefoil / quatrefoil are optional outlines."""

    def _build(self, foil=None):
        import building_styles_arch as bsa
        pk = pack()
        e = bsp.sample_entity(pk, "parish_church", pk.list("buildings")[0])
        e = bs.apply_style(e)
        if foil:
            e["_style"] = dict(e["_style"], special=dict(e["_style"]["special"], rose=dict(e["_style"]["special"]["rose"], foil=foil)))
        cx = wm.Ctx(pk)
        m, dn = wd.build_building_detailed(cx, e)
        R = bsg.Roof(cx, e)
        return e, m, R, bsa

    def _gable_tris(self, m, R, end, zr_guess=None):
        V = m.V
        L = (V[:, 0] - R.cxm) * R.ex[0] + (V[:, 1] - R.cym) * R.ex[1]
        W = (V[:, 0] - R.cxm) * R.ey[0] + (V[:, 1] - R.cym) * R.ey[1]
        out = []
        for mat, F in m.subs.items():
            if mat == "mat_glass" or "glass" in mat:
                continue
            for f in F:
                if np.all(np.abs(L[f] - end * R.hl) < 1e-4) and (V[f, 2].max() - V[f, 2].min()) > 1e-6:
                    out.append((mat, np.stack([end * W[f], V[f, 2]], 1)))
        return out

    @staticmethod
    def _inside(P, q):
        sg = lambda a, b, c: (a[0] - c[0]) * (b[1] - c[1]) - (b[0] - c[0]) * (a[1] - c[1])
        d = [sg(q, P[0], P[1]), sg(q, P[1], P[2]), sg(q, P[2], P[0])]
        return not (any(x < -1e-9 for x in d) and any(x > 1e-9 for x in d))

    def test_gable_is_cut_and_glass_fills_the_hole(self):
        for foil in (None, "trefoil", "quatrefoil"):
            e, m, R, bsa = self._build(foil)
            spec = e["_style"]["special"]["rose"]
            zmax = max(float(V_) for V_ in m.V[:, 2])
            R.zt(zmax - R.rise)
            zt = R.zt_
            rp = bsa.rose_params(R, e["_style"], zt, spec)
            self.assertIsNotNone(rp, foil)
            end, r, zc, ring, hole = rp
            tris = self._gable_tris(m, R, end)
            self.assertTrue(tris, foil)
            for q in [(0.0, zc), (0.4 * r, zc), (0.0, zc + 0.4 * r), (-0.3 * r, zc - 0.3 * r)]:
                self.assertFalse(any(self._inside(P, q) for mat, P in tris if abs(P[:, 1].max() - P[:, 1].min()) > 0 and _tri_area(P) > 1e-9), (foil, q))
            glass = [f for f in m.subs.get("mat_glass", [])]
            self.assertTrue(glass)

    def _build_no_rose(self):
        import building_styles_arch as bsa
        pk = pack()
        e = bsp.sample_entity(pk, "parish_church", pk.list("buildings")[0])
        e = bs.apply_style(e)
        e["_style"] = dict(e["_style"], special={k: v for k, v in e["_style"]["special"].items() if k != "rose"})
        cx = wm.Ctx(pk)
        m, dn = wd.build_building_detailed(cx, e)
        return e, m, bsg.Roof(cx, e), bsa

    def test_cut_area_matches_the_opening(self):
        import building_styles_arch as bsa
        e, m, R, _ = self._build("quatrefoil")
        e0, m0, R0, _ = self._build_no_rose()
        zmax = float(m.V[:, 2].max())
        R.zt(zmax - R.rise)
        spec = e["_style"]["special"]["rose"]
        end, r, zc, ring, hole = bsa.rose_params(R, e["_style"], R.zt_, spec)
        R0.zt(float(m0.V[:, 2].max()) - R0.rise)
        a1 = sum(_tri_area(P) for mat, P in self._gable_tris(m, R, end))
        a0 = sum(_tri_area(P) for mat, P in self._gable_tris(m0, R0, end))
        hole_area = 0.5 * abs(sum(hole[k][0] * hole[(k + 1) % len(hole)][1] - hole[(k + 1) % len(hole)][0] * hole[k][1] for k in range(len(hole))))
        self.assertAlmostEqual(a0 - a1, hole_area, delta=0.02 * hole_area + 1e-4)

    def test_foil_outlines(self):
        import building_styles_arch as bsa
        circ = bsa.rose_outline(2.0, None)
        tre = bsa.rose_outline(2.0, "trefoil")
        qua = bsa.rose_outline(2.0, "quatrefoil")
        rr = lambda o: [math.hypot(*p) for p in o]
        self.assertAlmostEqual(max(rr(circ)), 2.0, places=6)
        self.assertAlmostEqual(min(rr(circ)), 2.0, places=6)
        for o in (tre, qua):
            self.assertLessEqual(max(rr(o)), 2.0 + 1e-6)
            self.assertGreater(max(rr(o)) - min(rr(o)), 0.2)                           # lobes and notches
            self.assertGreater(min(rr(o)), 0.5)                                       # one connected opening
        self.assertEqual(sum(1 for k in range(len(tre)) if rr(tre)[k] > rr(tre)[k - 1] and rr(tre)[k] >= rr(tre)[(k + 1) % len(tre)]), 3)


def _tri_area(P):
    return 0.5 * abs((P[1][0] - P[0][0]) * (P[2][1] - P[0][1]) - (P[2][0] - P[0][0]) * (P[1][1] - P[0][1]))


class GatehouseCarriageArch(unittest.TestCase):
    @staticmethod
    def _ray_hits(m, o, d):
        V = m.V
        n = 0
        for F in m.subs.values():
            F = np.asarray(F)
            A, B, C = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
            e1, e2 = B - A, C - A
            pv = np.cross(d, e2)
            det = (e1 * pv).sum(1)
            ok = np.abs(det) > 1e-12
            inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
            tv = o - A
            u = (tv * pv).sum(1) * inv
            qv = np.cross(tv, e1)
            v = (qv * d).sum(1) * inv
            t = (qv * e2).sum(1) * inv
            n += int((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0)).sum())
        return n

    def _gate(self, with_arch=True):
        pk = pack()
        e = bsp.sample_entity(pk, "town_gatehouse", pk.list("buildings")[0])
        e = bs.apply_style(e)
        if not with_arch:
            e["_style"] = dict(e["_style"], special={k: v for k, v in e["_style"]["special"].items() if k != "carriage_arch"})
        cx = wm.Ctx(pk)
        m, dn = wd.build_building_detailed(cx, e)
        return e, m, dn, cx

    def test_passage_is_open_end_to_end(self):
        import building_styles_arch as bsa
        e, m, dn, cx = self._gate(True)
        e0, m0, dn0, _ = self._gate(False)
        self.assertEqual(e["_style"]["special"]["carriage_arch"]["width_ft"], 10.0)
        self.assertEqual(len(dn), 0)
        self.assertEqual(len(dn0), 1)
        P = [cx.B(p[0], p[1]) for p in e["polygon"]]
        if sum(P[k][0] * P[(k + 1) % len(P)][1] - P[(k + 1) % len(P)][0] * P[k][1] for k in range(len(P))) < 0:
            P.reverse()
        holes = [[] for _ in P]
        zf = (e["base_elevation_ft"] - cx.fr.z_origin_ft) * FT
        info = bsa.carriage_arch(holes, P, e["_style"]["special"], zf)
        self.assertIsNotNone(info)
        for k in (info["i"], info["j"]):
            car = [h for h in holes[k] if h.get("carriage")]
            self.assertEqual(len(car), 1)
            self.assertEqual(car[0]["shape"], "round_arch")
            self.assertAlmostEqual(car[0]["u1"] - car[0]["u0"], 10.0 * FT, places=3)
        i = info["i"]
        a, b = np.array(P[i]), np.array(P[(i + 1) % 4])
        d = (b - a) / np.linalg.norm(b - a)
        nrm = np.array([-d[1], d[0]])
        if np.dot(nrm, np.mean(P, axis=0) - a) < 0:
            nrm = -nrm
        c = a + d * (info["u0"] + info["u1"]) / 2
        o = np.array([c[0] - nrm[0] * 3.0, c[1] - nrm[1] * 3.0, zf + 3.0 * FT])      # 3 ft above the floor, starting 3 m outside the front wall
        dirv = np.array([nrm[0], nrm[1], 0.0])
        self.assertEqual(self._ray_hits(m, o, dirv), 0)                                 # straight through: no wall, no door
        self.assertGreaterEqual(self._ray_hits(m0, o, dirv), 2)                         # without the arch the ray hits both walls

    def test_no_arch_when_not_requested(self):
        import building_styles_arch as bsa
        holes = [[] for _ in range(4)]
        self.assertIsNone(bsa.carriage_arch(holes, [(0, 0), (6, 0), (6, 5), (0, 5)], {}, 0.0))
        self.assertIsNone(bsa.carriage_arch(holes, [(0, 0), (1, 0), (1, 1)], {"carriage_arch": {}}, 0.0))


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



def beam_over_roof(e, m, tol_m=0.02):
    """Largest height (m) by which a timber-frame vertex above the wall top rises over the roof surface (same Roof model the builder uses)."""
    S = e["_style"]
    cxo = wm.Ctx(pack())
    zt = (e["base_elevation_ft"] - cxo.fr.z_origin_ft + e["wall_height_ft"]) * FT
    R = bsg.Roof(cxo, e).zt(zt)
    F = m.subs.get(S["beam_mat"])
    if F is None or not len(F):
        return 0.0
    V = np.unique(m.V[F.ravel()], axis=0)
    V = V[V[:, 2] > zt + 1e-4]
    worst = 0.0
    for x, y, z in V:
        dx, dy = x - R.cxm, y - R.cym
        l, w = dx * R.ex[0] + dy * R.ex[1], dx * R.ey[0] + dy * R.ey[1]
        worst = max(worst, z - R.roof_z(l, w))
    return worst


class TimberStaysUnderRoof(unittest.TestCase):
    """Half-timber / corner-board geometry that rises above the wall top (gable studs, tie beam, rake rafters) must stay under the roof surface: no frame members
    poking through thatch or tiles (user report: dark diagonal timbers through the roof of the yellow Dyers house)."""

    def test_every_preset_gable_and_hip(self):
        pk = pack()
        checked = 0
        for pid, pre in bs.load_presets().items():
            if pre["wall"]["system"] not in ("halftimber", "corners") or pid == "stave_church":      # plain walls have no frame; the stave church's tiers are meant to rise above the roof
                continue
            for rtype, pitch in (("gable", 0.45), ("gable", 0.9), ("hip", 0.6)):
                e = bsp.sample_entity(pk, pid, pk.list("buildings")[0])
                e["roof"] = dict(e["roof"], type=rtype, ridge_height_ft=e["obb"]["width_ft"] / 2 * pitch)
                e = bs.apply_style(e)
                m, _ = wd.build_building_detailed(wm.Ctx(pk), e)
                self.assertLessEqual(beam_over_roof(e, m), 0.05, f"{pid} {rtype} pitch {pitch}")     # 5 cm: ridge caps / barge boards are roof trim
                checked += 1
        self.assertGreaterEqual(checked, 12)


BH_PACK = os.path.join(HERE, "..", "..", "world", "bridgehollow", "export")
BH_PRESETS = ("bh_inner_house", "bh_warden_house", "bh_warden_civic", "bh_ring_outbuilding")
BH_TRI_BUDGET = {"bh_inner_house": 3500, "bh_warden_house": 5000, "bh_warden_civic": 6500, "bh_ring_outbuilding": 1800}     # per building, snow included


def _read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def coplanar_pairs(m, mats, min_area=2e-4):
    """Pairs of triangles in the same plane with overlapping area (m^2), where at least one triangle uses one of `mats`."""
    from shapely.geometry import Polygon
    V = m.V
    groups = {}
    for mat, F in m.subs.items():
        for f in np.asarray(F):
            a, b, c = V[f]
            n = np.cross(b - a, c - a)
            ln = np.linalg.norm(n)
            if ln < 1e-10:
                continue
            n = n / ln
            if n[np.argmax(np.abs(n))] < 0:
                n = -n
            groups.setdefault((tuple(np.round(n, 3)), round(float(n @ a), 3)), []).append((mat, V[f], n, float(n @ a)))
    bad = []
    for G in groups.values():
        if len(G) < 2 or not any(t[0] in mats for t in G):
            continue
        n = G[0][2]
        u = np.cross(n, [1.0, 0, 0] if abs(n[0]) < 0.9 else [0, 1.0, 0])
        u /= np.linalg.norm(u)
        v = np.cross(n, u)
        P = [Polygon([(p @ u, p @ v) for p in t[1]]) for t in G]
        for i in range(len(G)):
            for j in range(i + 1, len(G)):
                if (G[i][0] in mats or G[j][0] in mats) and abs(G[i][3] - G[j][3]) < 2e-4 and P[i].intersection(P[j]).area > min_area:
                    bad.append((G[i][0], G[j][0]))
    return bad


class BridgehollowTiers(unittest.TestCase):
    """Ring-tier styles of Bridgehollow (bridgehollow_styles.py, bh_* presets): presets, winter variants, budgets, no poke-through, no coplanar new geometry,
    every one of the 148 buildings gets a valid style (or stays legacy), tier counts."""

    @classmethod
    def setUpClass(cls):
        cls.bh = None
        if os.path.exists(os.path.join(BH_PACK, "manifest.json")):
            cls.bh = wp.load_pack(BH_PACK)
            pbr.prepare(cls.bh.materials)

    def test_presets_and_winter_variants(self):
        ps = bs.load_presets()
        for pid in BH_PRESETS:
            self.assertIn(pid, ps)
            w = ps[pid + "_winter"]
            self.assertEqual(w["special"]["snow"]["depth_ft"], 0.42)
            self.assertEqual(w["wall"], ps[pid]["wall"])                      # "extends": everything but the snow comes from the base preset
            self.assertNotIn("extends", w)
            self.assertEqual(ps[pid]["kinds"], {})                            # never picked by "auto": only the tier script assigns them
            self.assertTrue(os.path.exists(os.path.join(HERE, "..", "..", ps[pid]["preview"])), pid)
        S = bs.resolve("bh_warden_house", "bld_x")
        self.assertTrue(S["upper"] and S["quoins"] and S["string_course"] and S["finials"] and S["dormers"] and S["chimney"]["both"])
        self.assertEqual(S["door"]["shape"], "round_arch")
        self.assertTrue(bs.resolve("bh_warden_house_winter", "bld_x")["special"]["snow"])

    def _real(self, n_per_style=None):
        """[(entity with style applied, mesh)] for Bridgehollow buildings of every tier (one per style and floors count, or all with n_per_style=None)."""
        import bridgehollow_styles as bhs
        T = bhs.tiers("bridgehollow")
        cx = wm.Ctx(self.bh)
        seen, out = set(), []
        for e0 in self.bh.list("buildings"):
            if e0["id"] not in T:
                continue
            tier, kind = T[e0["id"]]
            st = bhs.style_for(tier, kind, "winter")
            if not st:
                continue
            key = (st, e0.get("floors", 1), e0["roof"]["type"])
            if n_per_style and key in seen:
                continue
            seen.add(key)
            e = dict(e0, style=st)
            e = bs.apply_style(e)
            m, dn = wd.build_building_detailed(cx, e)
            out.append((e, m, dn))
        return out

    def test_real_buildings_budget_roof_and_coplanar(self):
        if self.bh is None:
            self.skipTest("no Bridgehollow pack")
        cx = wm.Ctx(self.bh)
        rows = self._real(n_per_style=1)
        self.assertGreaterEqual(len(rows), 5)
        for e, m, dn in rows:
            S = e["_style"]
            base = S["id"].replace("_winter", "")
            self.assertLess(m.tri_count, BH_TRI_BUDGET[base], e["id"])
            self.assertEqual(len(dn), 1, e["id"])
            zt = (e["base_elevation_ft"] - cx.fr.z_origin_ft + e["wall_height_ft"]) * FT
            R = bsg.Roof(cx, e).zt(zt)
            # timber never pokes through the roof (gable studs, collar rails, rafters, frame)
            F = m.subs.get(S.get("beam_mat"))
            if F is not None and len(F):
                Vb = np.unique(m.V[np.asarray(F).ravel()], axis=0)
                for x, y, z in Vb[Vb[:, 2] > zt + 1e-4]:
                    l, w = (x - R.cxm) * R.ex[0] + (y - R.cym) * R.ex[1], (x - R.cxm) * R.ey[0] + (y - R.cym) * R.ey[1]
                    self.assertLessEqual(z - R.roof_z(l, w), 0.05, e["id"])
            # the snow sheet lies above the roof surface (never in it) and only up there
            Fs = m.subs.get(S.get("snow_mat"))
            self.assertTrue(Fs is not None and len(Fs), e["id"])
            Vs = np.unique(m.V[np.asarray(Fs).ravel()], axis=0)
            self.assertGreater(Vs[:, 2].min(), R.ze - 0.05)
            # no new geometry shares a plane with anything (skin, quoins, bands, dormers, snow)
            new = {S.get(k) for k in ("upper_mat", "quoin_mat", "snow_mat", "band_mat", "shutter_mat")} - {None}
            self.assertEqual(coplanar_pairs(m, new), [], e["id"])

    def test_tier_counts_and_every_building_valid(self):
        import bridgehollow_styles as bhs
        T = bhs.tiers("bridgehollow")
        self.assertEqual(len(T), len(os.listdir(os.path.join(WORLD, "bridgehollow", "buildings"))))
        cnt = {}
        for t, k in T.values():
            cnt[t] = cnt.get(t, 0) + 1
        self.assertEqual(cnt, {"warden": 19, "inner": 39, "other": 90})
        ps = bs.load_presets()
        for bid, (t, k) in T.items():
            st = bhs.style_for(t, k)
            if t == "other":
                self.assertIsNone(st)
            else:
                self.assertIn(st, ps, (bid, t, k))
                self.assertIn(bhs.style_for(t, k, "winter"), ps)
        self.assertEqual(T["bld_warden_hall"][0], "warden")
        self.assertEqual(T["bld_wardens_barracks"][0], "warden")

    def test_assign_dry_idempotent_season_clear(self):
        import bridgehollow_styles as bhs
        tmp = tempfile.mkdtemp()
        try:
            src = os.path.join(WORLD, "bridgehollow")
            os.makedirs(os.path.join(tmp, "bridgehollow", "buildings"))
            shutil.copy(os.path.join(src, "districts.json"), os.path.join(tmp, "bridgehollow", "districts.json"))
            for f in os.listdir(os.path.join(src, "buildings")):
                b = _load(os.path.join(src, "buildings", f))
                b.pop("style", None)
                with open(os.path.join(tmp, "bridgehollow", "buildings", f), "w", encoding="utf-8") as fh:
                    json.dump(b, fh, indent=1)
            os.environ["VB_WORLD_ROOT"] = tmp
            snap = lambda: {f: _read(os.path.join(tmp, "bridgehollow", "buildings", f)) for f in os.listdir(os.path.join(tmp, "bridgehollow", "buildings"))}
            before = snap()
            r = bhs.apply(dry=True)
            self.assertEqual(r["count"], 58)
            self.assertEqual(before, snap())                                                  # dry run writes nothing
            self.assertEqual(r["styles"], {"bh_warden_civic": 8, "bh_warden_house": 7, "bh_ring_outbuilding": 6, "bh_inner_house": 37})
            self.assertEqual(bhs.apply()["count"], 58)
            self.assertEqual(bhs.apply()["count"], 0)                                        # idempotent
            b = _load(os.path.join(tmp, "bridgehollow", "buildings", "bld_house_058.json"))
            b0 = _load(os.path.join(src, "buildings", "bld_house_058.json"))
            b0.pop("style", None)
            self.assertEqual({k: v for k, v in b.items() if k != "style"}, b0)                # only the style key is written
            self.assertEqual(b["style"], "bh_warden_house")
            # a hand-picked style is kept; winter swaps to the snow variants; clear removes only bh_* styles
            p = os.path.join(tmp, "bridgehollow", "buildings", "bld_house_101.json")
            b = _load(p)
            b["style"] = "tudor"
            with open(p, "w", encoding="utf-8") as fh:
                json.dump(b, fh, indent=1)
            r = bhs.apply(season="winter")
            self.assertEqual(r["count"], 57)
            self.assertEqual(_load(p)["style"], "tudor")
            self.assertEqual(_load(os.path.join(tmp, "bridgehollow", "buildings", "bld_inn.json"))["style"], "bh_warden_house_winter")
            self.assertEqual(bhs.apply(clear=True)["count"], 57)
            self.assertEqual(_load(p)["style"], "tudor")
            self.assertNotIn("style", _load(os.path.join(tmp, "bridgehollow", "buildings", "bld_inn.json")))
        finally:
            os.environ.pop("VB_WORLD_ROOT", None)
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=1)
