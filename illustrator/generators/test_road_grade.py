"""Tests for road grading (python test_road_grade.py): no road vertex under the terrain mesh, grade limit (or warning), skirt reaches ground,
cut/fill keeps the terrain continuous, bridge ends and junctions blend, and the real Dyers Walk pack has no buried road."""
import math
import os
import sys
import types
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import road_grade as rg  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

CELL, FT = 2.5, wp.FT_M
ZO = 80.0


def terrain(n=160, seed=3):
    """Rolling ground with a ridge and a gully across the roads, 2.5 ft cells (the pack's terrain resolution)."""
    rng = np.random.RandomState(seed)
    Y, X = np.mgrid[0:n, 0:n] * CELL
    h = 100 + 6 * np.sin(X / 37.0) * np.cos(Y / 29.0) + 0.8 * rng.randn(n, n) + 14 * np.exp(-((X - 200) / 18.0) ** 2) - 12 * np.exp(-((Y - 150) / 12.0) ** 2)
    return h.astype(np.float32)


def road(rid, pts, width=14.0, **kw):
    r = {"id": rid, "class": "street", "width_ft": width, "points": [list(map(float, p)) for p in pts], "bridge": None,
         "surface": {"material": "mat_road", "tile_ft": 10}}
    r.update(kw)
    return r


def synth(h, roads):
    pk = types.SimpleNamespace(heights=h, cell_ft=CELL, place="synthetic", entities={"roads": roads, "bridges": []})
    pk.list = lambda t=None: pk.entities.get(t, [])
    pk.frame = wp.Frame(h.shape[1] * CELL, h.shape[0] * CELL, ZO)
    return pk


def sparse_roads(h):
    out = []
    for rid, p0, p1 in (("a", (20, 40), (340, 120)), ("b", (30, 330), (360, 300)), ("c", (200, 20), (210, 380))):
        n = int(math.dist(p0, p1) // 13) + 1
        xs, ys = np.linspace(p0[0], p1[0], n), np.linspace(p0[1], p1[1], n)
        zs = [wp.bilinear(h, CELL, x, y) + 2.0 * math.sin(i) for i, (x, y) in enumerate(zip(xs, ys))]     # authored heights float/bury like the real ones
        out.append(road(rid, list(zip(xs, ys, zs))))
    return out


def deck_samples(pk, m):
    T = m.subs["mat_road"]
    V = m.V[T]
    nz = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    nz = nz[:, 2] / np.maximum(np.linalg.norm(nz, axis=1), 1e-12)
    D = V[nz > 0.8]
    S = np.concatenate([D, D.mean(1, keepdims=True), (D[:, 0:1] + D[:, 1:2]) / 2], 1).reshape(-1, 3)
    return S[:, 0] / FT, pk.frame.height_ft - S[:, 1] / FT, S[:, 2] / FT + ZO


class GradeTests(unittest.TestCase):
    def setUp(self):
        self.h = terrain()
        self.pk = synth(self.h, sparse_roads(self.h))

    def test_stations_never_under_terrain_mesh(self):
        for smooth in (0.0, 0.5, 1.0):
            runs, rep = rg.grade_roads(self.pk, self.h, {"smooth": smooth})
            mn, mx, bad, n = rg.verify(self.h, CELL, runs, 0.0)
            self.assertEqual(bad, 0, f"smooth {smooth} min depth {mn}")

    def test_deck_mesh_vertices_not_under_terrain(self):
        """The built ribbon triangles (not just the station heights) against the terrain triangles."""
        runs, rep = rg.grade_roads(self.pk, self.h, {})
        cx = wm.Ctx(self.pk)
        worst = 1e9
        for r in self.pk.list("roads"):
            m = wm.build_road(cx, dict(r, _grade={"runs": runs[r["id"]], "skirt": False}))
            x, y, z = deck_samples(self.pk, m)
            worst = min(worst, float((z - rg.mesh_height(self.h, CELL, x, y)).min()))
        self.assertGreaterEqual(worst, -0.01)

    def test_old_sparse_points_do_bury(self):
        """Why: linear interpolation between the authored 13 ft points goes under the terrain mesh."""
        pts = np.array(self.pk.list("roads")[0]["points"])
        s = np.concatenate([[0], np.cumsum(np.hypot(*np.diff(pts[:, :2], axis=0).T))])
        ss = np.arange(0, s[-1], 1.0)
        d = np.interp(ss, s, pts[:, 2]) + 0.82 - rg.mesh_height(self.h, CELL, np.interp(ss, s, pts[:, 0]), np.interp(ss, s, pts[:, 1]))
        self.assertLess(d.min(), 0.0)

    def test_grade_limit(self):
        for lim in (6.0, 12.0, 20.0):
            runs, rep = rg.grade_roads(self.pk, self.h, {"max_grade_deg": lim})
            for rs in runs.values():
                for r in rs:
                    g = np.degrees(np.arctan(np.abs(np.diff(r.z)) / np.diff(r.s)))
                    self.assertLessEqual(g.max(), lim + 0.01, lim)
            self.assertFalse([w for w in rep["warnings"] if "could not be met" in w])

    def test_steep_ground_warns(self):
        h = self.h.copy()
        h[:, 70:] += 60.0          # a cliff across the roads
        pk = synth(h, self.pk.list("roads"))
        runs, rep = rg.grade_roads(pk, h, {"max_grade_deg": 10.0})
        self.assertTrue(any("steeper" in w or "raised" in w for w in rep["warnings"]), rep["warnings"])
        mn, mx, bad, n = rg.verify(h, CELL, runs, 0.0)
        self.assertEqual(bad, 0)

    def test_smoothing_reduces_roughness(self):
        def rough(smooth):
            runs, _ = rg.grade_roads(self.pk, self.h, {"smooth": smooth, "max_grade_deg": 40, "cross_deg": 45})
            return sum(float(np.abs(np.diff(r.z, 2)).sum()) for rs in runs.values() for r in rs)
        self.assertLess(rough(1.0), rough(0.0))

    def test_skirt_reaches_ground(self):
        runs, rep = rg.grade_roads(self.pk, self.h, {"smooth": 1.0, "cross_deg": 3.0})   # stiff road: stands above the ground in places
        cx = wm.Ctx(self.pk)
        r = self.pk.list("roads")[0]
        m = wm.build_road(cx, dict(r, _grade={"runs": runs[r["id"]], "skirt": True}))
        m0 = wm.build_road(cx, dict(r, _grade={"runs": runs[r["id"]], "skirt": False}))
        self.assertGreater(len(m.V), len(m0.V))
        extra = m.V[len(m0.V):]                                  # the apron's outer vertices (built after the deck's)
        z = extra[:, 2] / FT + ZO
        g = rg.mesh_height(self.h, CELL, extra[:, 0] / FT, self.pk.frame.height_ft - extra[:, 1] / FT)
        self.assertLessEqual(float((z - g).max()), 1e-6)         # every apron foot is at or below ground
        # and the apron closes a real gap: somewhere the deck edge stands clear of the ground
        x, y, zd = deck_samples(self.pk, m0)
        self.assertGreater(float((zd - rg.mesh_height(self.h, CELL, x, y)).max()), 1.0)

    def test_params(self):
        self.assertTrue(rg.params(True)["skirt"])
        self.assertFalse(rg.params({"skirt": False})["skirt"])
        self.assertFalse(rg.params(False)["enabled"])
        self.assertFalse(rg.params({"cutfill": None})["cutfill"])
        self.assertEqual(rg.params({"smooth": 5})["smooth"], 1.0)


class CutFillTests(unittest.TestCase):
    def test_terrain_continuous_and_road_bed_set(self):
        h = terrain()
        pk = synth(h, sparse_roads(h))
        h2, runs, rep = rg.grade_and_cutfill(pk, h, {"cutfill": True, "smooth": 1.0})
        self.assertIn("max_fill_ft", rep["cutfill"])
        self.assertEqual(h2.shape, h.shape)
        self.assertTrue(np.isfinite(h2).all())
        dh = h2.astype(float) - h
        self.assertGreater(float(np.abs(dh).max()), 0.5)               # something changed
        # continuity: neighbouring cells never differ by more than the roads' own cut/fill step allows (no cliff at the falloff edge)
        self.assertLess(float(np.abs(np.diff(dh, axis=1)).max()), 6.0)
        self.assertLess(float(np.abs(np.diff(dh, axis=0)).max()), 6.0)
        self.assertLess(float(np.abs(np.diff(h2.astype(float), axis=1) - np.diff(h.astype(float), axis=1)).max()), 6.0)
        self.assertEqual(float(dh[0, 0]), 0.0)                         # far from every road the terrain is untouched
        self.assertEqual(float(dh[-1, 0]), 0.0)
        mn, mx, bad, n = rg.verify(h2, CELL, runs, 0.0)
        self.assertEqual(bad, 0, mn)

    def test_cutfill_off_by_default(self):
        self.assertFalse(rg.params({})["cutfill"])


class JunctionBridgeTests(unittest.TestCase):
    def test_t_junction_meets_through_road(self):
        h = terrain()
        thru = road("t", [(20, 200, 0), (180, 200, 0), (340, 200, 0)])
        side = road("s", [(180, 200, 0), (180, 260, 0), (180, 330, 0)])
        runs, _ = rg.grade_roads(synth(h, [thru, side]), h, {"smooth": 0.5})
        j = int(np.argmin(np.abs(runs["t"][0].x - 180)))
        self.assertLess(abs(runs["s"][0].z[0] - runs["t"][0].z[j]), 0.6)

    def test_bridge_gap_ends_blend_to_deck(self):
        h = terrain()
        r = road("g", [(20, 100, 120.0), (120, 100, 120.0), (220, 100, 120.0), (320, 100, 120.0)], gaps=[{"bridge": "x", "s0_ft": 110.0, "s1_ft": 190.0}])
        runs, rep = rg.grade_roads(synth(h, [r]), h, {})
        self.assertEqual(len(runs["g"]), 2)
        a, b = runs["g"]
        self.assertTrue(a.gap_ends[1] and b.gap_ends[0])
        self.assertAlmostEqual(float(a.x[-1]), 130.0, 3)
        self.assertAlmostEqual(float(b.x[0]), 210.0, 3)
        for end in (a.z[-1], b.z[0]):          # the road meets the deck end, or the raise is reported
            self.assertTrue(abs(end - 120.0) < 0.3 or any("bridge" in w for w in rep["warnings"]), (end, rep["warnings"]))

    def test_bridge_road_untouched_by_grading(self):
        h = terrain()
        r = road("deck", [(20, 100, 130.0), (120, 100, 130.0)], bridge={"x": 1})
        runs, _ = rg.grade_roads(synth(h, [r]), h, {})
        self.assertNotIn("deck", runs)


class ParallelAndLodTests(unittest.TestCase):
    def test_parallel_roads_blend_along_the_shared_stretch(self):
        h = terrain()
        y0 = 120.0
        ra = road("pa", [(20, y0, 0), (180, y0, 0), (340, y0, 0)], width=10.0)
        rb = road("pb", [(20, y0 + 9, 0), (180, y0 + 9, 0), (340, y0 + 9, 0)], width=10.0)     # 9 ft apart: a long shared stretch
        pk = synth(h, [ra, rb])
        runs, rep = rg.grade_roads(pk, h, {"smooth": 0.5})
        a, b = runs["pa"][0], runs["pb"][0]
        self.assertGreaterEqual(rep["stats"]["parallel_stretches"], 1)
        self.assertTrue(any("side by side" in w for w in rep["warnings"]), rep["warnings"])
        xs = np.linspace(60, 300, 40)
        za, zb = np.interp(xs, a.x, a.z), np.interp(xs, b.x, b.z)
        # the old behaviour pinned one point: elsewhere the two roads 9 ft apart could differ by the ground's cross slope; blended they stay together
        old = []
        import road_grade as rgm
        P0 = rgm.PARALLEL_MIN_STATIONS
        try:
            rgm.PARALLEL_MIN_STATIONS = 10 ** 6
            r0, _ = rg.grade_roads(pk, h, {"smooth": 0.5})
        finally:
            rgm.PARALLEL_MIN_STATIONS = P0
        zo = np.abs(np.interp(xs, r0["pa"][0].x, r0["pa"][0].z) - np.interp(xs, r0["pb"][0].x, r0["pb"][0].z))
        self.assertLessEqual(float(np.abs(za - zb).max()), float(zo.max()) + 1e-6)
        mn, mx, bad, n = rg.verify(h, CELL, runs, 0.0)
        self.assertEqual(bad, 0)                                       # blending only raised or kept roads above the ground

    def test_lod_pokes_found_and_fixed(self):
        h = terrain()
        r = road("g", [(20, 150, 0), (340, 150, 0)], width=12.0)         # runs along the gully (y = 150): a coarse mesh cannot follow it
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {"smooth": 0.0})
        mn, mx, bad, n = rg.verify(h, CELL, runs, 0.0)
        self.assertEqual(bad, 0)
        before = rg.lod_pokes(h, CELL, runs, 4)
        self.assertGreater(before["g"]["max_poke_ft"], 0.05)
        h2, info = rg.lod_safe_heights(h, CELL, runs, 4)
        after = rg.lod_pokes(h2, CELL, runs, 4, tol_ft=0.0)
        self.assertEqual(after["g"]["poking"], 0, (before, after, info))
        self.assertGreater(info["lowered_vertices"], 0)
        self.assertTrue(bool((h2 <= h + 1e-6).all()))
        changed = np.argwhere(h2 != h)
        self.assertTrue(bool(((changed % 4) == 0).all()))               # only LOD vertices were touched

    def test_lod_report_in_build_terrain_heights(self):
        h = terrain()
        pk = synth(h, [road("g", [(20, 150, 0), (340, 150, 0)], width=12.0)])
        pk.entities["buildings"] = []
        old = wm.LOD_CHECK_STEPS
        try:
            wm.LOD_CHECK_STEPS = (8,)
            wm.terrain_heights(pk, carve=False, conform=True, road_grade=True)
        finally:
            wm.LOD_CHECK_STEPS = old
        rep = wm.LAST_ROAD_GRADE
        self.assertIn("lod", rep)
        self.assertTrue(any("terrain LOD step 8" in w for w in rep["warnings"]))


class RealPackTests(unittest.TestCase):
    def test_dyers_walk_has_no_buried_road(self):
        d = os.path.join(wp.REPO, "world", "bridgehollow__dyers_walk_local", "export")
        if not os.path.exists(os.path.join(d, "manifest.json")):
            self.skipTest("no Dyers Walk pack")
        import road_height_audit as ra
        rows = ra.mesh_audit(wp.load_pack(d), True)
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["buried_pct"], 0.0, r)
            self.assertGreater(r["min_ft"], 0.0, r)


class SkirtTexture(unittest.TestCase):
    def test_skirt_uv_continues_the_road_texture(self):
        """The skirt used u = 0 for its outer edge, so one texel column was stretched down the flank (a pale vertical band)."""
        b = wm.Builder()
        pts = [(0.0, float(i)) for i in range(5)]
        wm._ribbon(b, "m", pts, [4.0] * 5, [2.0] * 5, 10.0, skirt={"ground": lambda x, y: 0.0})
        m = b.build()
        u = m.UV[:, 0]
        self.assertGreater(float(u.max()), 4.0 / FT / 10.0 + 1e-6)          # left flank continues past the road's right-hand u
        self.assertLess(float(u.min()), -1e-6)                              # right flank continues below u = 0
        self.assertEqual(len(np.unique(np.round(u, 6))) > 3, True)


class KerbFlush(unittest.TestCase):
    def test_kerb_embedded_and_flush_with_graded_edge(self):
        """Kerb base must be below the terrain (no hovering over the skirt) and the kerb top must sit KERB_H above the graded road surface at its inner edge."""
        from shapely.geometry import LineString
        h = terrain()
        r = road("k", [(30, 60, 100.0), (300, 140, 100.0)], width=16.0)
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {})
        ring = LineString([(30, 60), (300, 140)]).buffer(8.7, cap_style=2).difference(LineString([(30, 60), (300, 140)]).buffer(8.0, cap_style=2))
        rings = [[list(p) for p in list(g.exterior.coords)[:-1]] for g in getattr(ring, "geoms", [ring])]
        e = dict(r, _grade={"runs": runs["k"], "skirt": True}, kerbs=rings)
        cx = wm.Ctx(pk)
        b = wm.Builder()
        wm._add_kerbs(cx, b, e)
        m = b.build()
        V = m.V[m.subs["mat_kerb"]].reshape(-1, 3)
        x, y, z = V[:, 0] / FT, pk.frame.height_ft - V[:, 1] / FT, V[:, 2] / FT + ZO
        g = rg.mesh_height(h, CELL, x, y)
        run = runs["k"][0]
        surf, _ = wm.kerb_heights(cx, e, list(zip(x, y)))
        low = z < surf + wm.KERB_H_FT - 0.05                                  # base vertices (not the top face)
        self.assertTrue(low.any())
        self.assertLessEqual(float((z[low] - g[low]).max()), -wm.KERB_SINK_FT + 0.02)     # all base vertices sit below the ground
        top = ~low
        self.assertLess(float(np.abs(z[top] - surf[top] - wm.KERB_H_FT).max()), 0.02)
        # inner-edge kerb top vs the road ribbon edge height (cross-slope aware): within 0.1 ft
        i = len(run.x) // 2
        d = np.hypot(x - run.x[i], y - run.y[i])
        tx, ty = np.gradient(run.x)[i], np.gradient(run.y)[i]
        lon = np.abs((x - run.x[i]) * tx + (y - run.y[i]) * ty) / math.hypot(tx, ty)
        near = top & (d < 10.0) & (lon < 0.8)
        edge = np.maximum(run.zl[i], run.zr[i]) + wm.KERB_H_FT
        edgel = np.minimum(run.zl[i], run.zr[i]) + wm.KERB_H_FT
        self.assertTrue(near.any())
        self.assertTrue(np.all((z[near] <= edge + 0.1) & (z[near] >= edgel - 0.1)))


class KerbSkirt(unittest.TestCase):
    def _build(self, pts, width=16.0):
        from shapely.geometry import LineString
        h = terrain()
        r = road("c", pts, width=width)
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {})
        ls = LineString([(p[0], p[1]) for p in pts])
        outline = ls.buffer(width / 2, cap_style=2)
        band = outline.buffer(0.7, join_style=2).difference(outline)
        e = dict(r, _grade={"runs": runs["c"], "skirt": True}, kerbs=[[list(p) for p in list(band.exterior.coords)[:-1]]],
                 outline=[list(p) for p in list(outline.exterior.coords)[:-1]])
        cx = wm.Ctx(pk)
        b = wm.Builder()
        wm._add_kerbs(cx, b, e)
        return h, pk, runs["c"], e, b.build()

    def test_kerb_height_is_four_inches(self):
        self.assertAlmostEqual(wm.KERB_H_FT, 0.33, places=2)

    def test_annulus_has_no_lid_over_the_road(self):
        h, pk, run, e, m = self._build([(30, 60, 100.0), (300, 140, 100.0)])
        V = m.V[m.subs["mat_kerb"]]
        x = V[:, :, 0] / FT
        y = pk.frame.height_ft - V[:, :, 1] / FT
        from shapely.geometry import Polygon, Point
        road_poly = Polygon(e["outline"]).buffer(-0.5)
        c = np.stack([x.mean(1), y.mean(1)], 1)
        self.assertFalse(any(road_poly.contains(Point(p)) for p in c), "a kerb triangle lies over the road surface")

    def test_kerb_wall_columns_bury_below_dense_terrain(self):
        """Sloped and curved roads: every wall base point, and points between the 3 ft vertices, lies below the terrain sampled densely (0.5 ft)."""
        for pts in ([(30, 60, 100.0), (300, 140, 100.0)], [(40, 300, 98.0), (120, 220, 103.0), (200, 230, 101.0), (280, 120, 108.0), (340, 90, 106.0)]):
            h, pk, run, e, m = self._build([tuple(p) for p in pts])
            T = m.subs["mat_kerb"]
            V = m.V
            worst = -1e9
            n = 0
            colmin, colmax = {}, {}
            for t in T:
                for i in t:
                    k = (round(V[i][0], 4), round(V[i][1], 4))
                    colmin[k] = min(colmin.get(k, 1e9), V[i][2])
                    colmax[k] = max(colmax.get(k, -1e9), V[i][2])
            for t in T:
                P = V[list(t)]
                bs = [p for p in P if abs(p[2] - colmin[(round(p[0], 4), round(p[1], 4))]) < 1e-6 and p[2] < colmax[(round(p[0], 4), round(p[1], 4))] - 0.1]
                if len(bs) != 2:
                    continue                          # not a wall triangle with a base edge
                p0, p1 = bs
                for u in np.linspace(0, 1, 9):
                    q = p0 + (p1 - p0) * u
                    x, y = q[0] / FT, pk.frame.height_ft - q[1] / FT
                    g = float(rg.mesh_height(h, CELL, np.array([x]), np.array([y]))[0])
                    worst = max(worst, q[2] / FT + ZO - g)
                    n += 1
            self.assertGreater(n, 100)
            self.assertLess(worst, -0.1, f"a kerb base sits {worst:.2f} ft relative to terrain (must stay below)")


class JunctionWeld(unittest.TestCase):
    """T and Y junctions: the minor road ends on the major road; where their decks overlap the minor must never show above the major, and at the
    major's edge both surfaces meet at the same height (no step, no gap)."""

    def _decks(self, h, roads):
        pk = synth(h, roads)
        runs, rep = rg.grade_roads(pk, h, {})
        cx = wm.Ctx(pk)
        out = {}
        for r in roads:
            m = wm.build_road(cx, dict(r, _grade={"runs": runs[r["id"]], "skirt": True}))
            V = m.V[m.subs["mat_road"]]
            nz = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])[:, 2]
            out[r["id"]] = V[nz > 0]
        return pk, runs, out

    @staticmethod
    def _z_in(tris, x, y):
        for V in tris:
            A = np.array([[V[0][0], V[1][0], V[2][0]], [V[0][1], V[1][1], V[2][1]], [1, 1, 1]])
            try:
                b = np.linalg.solve(A, [x, y, 1])
            except np.linalg.LinAlgError:
                continue
            if (b >= -1e-9).all():
                return float(b @ V[:, 2])
        return None

    @staticmethod
    def _gentle(n=160):
        Y, X = np.mgrid[0:n, 0:n] * CELL
        return (100 + 0.02 * X + 0.012 * Y + 0.6 * np.sin(X / 45.0)).astype(np.float32)

    def _check(self, roads):
        from shapely.geometry import Point
        h = self._gentle()
        pk, runs, decks = self._decks(h, roads)
        major_run, minor_run = runs["major"][0], runs["minor"][0]
        fp = rg.footprint(major_run)
        H = pk.frame.height_ft
        minor = decks["minor"]
        # 1. clean cut: no minor deck triangle lies inside the major road (no overlap, no coplanar z-fighting faces)
        inside = [V for V in minor if fp.buffer(-0.05).contains(Point(V[:, 0].mean() / FT, H - V[:, 1].mean() / FT))]
        self.assertEqual(len(inside), 0, f"{len(inside)} minor deck triangles overlap the major road")
        # 2. heights equal at the join: minor stations inside the footprint sit on the major surface (<= 0.05 ft)
        worst = 0.0
        n = 0
        for i in range(len(minor_run.x)):
            if fp.contains(Point(minor_run.x[i], minor_run.y[i])):
                worst = max(worst, abs(minor_run.z[i] - rg.surface_at(major_run, minor_run.x[i], minor_run.y[i])))
                n += 1
        self.assertGreater(n, 0, "the minor road does not reach the major road")
        self.assertLess(worst, 0.05)
        # 3. no gap: every point of the minor centreline is covered by the minor deck or the major road footprint
        from shapely.geometry import Polygon
        tris = [Polygon(np.stack([V[:, 0] / FT, H - V[:, 1] / FT], 1)) for V in minor]
        from shapely.ops import unary_union
        deck = unary_union([t.buffer(0.02) for t in tris if t.area > 0]).union(fp.buffer(0.02))
        s_ = np.arange(0.0, float(minor_run.s[-1]), 0.5)
        gaps = [float(sv) for sv in s_ if not deck.contains(Point(np.interp(sv, minor_run.s, minor_run.x), np.interp(sv, minor_run.s, minor_run.y)))]
        self.assertEqual(gaps, [], f"gap along the minor road centreline at s = {gaps[:3]}")

    def test_t_junction_meets_through_road(self):
        h = terrain()
        thru = road("t", [(20, 200, 0), (180, 200, 0), (340, 200, 0)])
        side = road("s", [(180, 200, 0), (180, 260, 0), (180, 330, 0)])
        runs, _ = rg.grade_roads(synth(h, [thru, side]), h, {"smooth": 0.5})
        j = int(np.argmin(np.abs(runs["t"][0].x - 180)))
        self.assertLess(abs(runs["s"][0].z[0] - runs["t"][0].z[j]), 0.6)

    def test_bridge_gap_ends_blend_to_deck(self):
        h = terrain()
        r = road("g", [(20, 100, 120.0), (120, 100, 120.0), (220, 100, 120.0), (320, 100, 120.0)], gaps=[{"bridge": "x", "s0_ft": 110.0, "s1_ft": 190.0}])
        runs, rep = rg.grade_roads(synth(h, [r]), h, {})
        self.assertEqual(len(runs["g"]), 2)
        a, b = runs["g"]
        self.assertTrue(a.gap_ends[1] and b.gap_ends[0])
        self.assertAlmostEqual(float(a.x[-1]), 130.0, 3)
        self.assertAlmostEqual(float(b.x[0]), 210.0, 3)
        for end in (a.z[-1], b.z[0]):          # the road meets the deck end, or the raise is reported
            self.assertTrue(abs(end - 120.0) < 0.3 or any("bridge" in w for w in rep["warnings"]), (end, rep["warnings"]))

    def test_bridge_road_untouched_by_grading(self):
        h = terrain()
        r = road("deck", [(20, 100, 130.0), (120, 100, 130.0)], bridge={"x": 1})
        runs, _ = rg.grade_roads(synth(h, [r]), h, {})
        self.assertNotIn("deck", runs)


class ParallelAndLodTests(unittest.TestCase):
    def test_parallel_roads_blend_along_the_shared_stretch(self):
        h = terrain()
        y0 = 120.0
        ra = road("pa", [(20, y0, 0), (180, y0, 0), (340, y0, 0)], width=10.0)
        rb = road("pb", [(20, y0 + 9, 0), (180, y0 + 9, 0), (340, y0 + 9, 0)], width=10.0)     # 9 ft apart: a long shared stretch
        pk = synth(h, [ra, rb])
        runs, rep = rg.grade_roads(pk, h, {"smooth": 0.5})
        a, b = runs["pa"][0], runs["pb"][0]
        self.assertGreaterEqual(rep["stats"]["parallel_stretches"], 1)
        self.assertTrue(any("side by side" in w for w in rep["warnings"]), rep["warnings"])
        xs = np.linspace(60, 300, 40)
        za, zb = np.interp(xs, a.x, a.z), np.interp(xs, b.x, b.z)
        # the old behaviour pinned one point: elsewhere the two roads 9 ft apart could differ by the ground's cross slope; blended they stay together
        old = []
        import road_grade as rgm
        P0 = rgm.PARALLEL_MIN_STATIONS
        try:
            rgm.PARALLEL_MIN_STATIONS = 10 ** 6
            r0, _ = rg.grade_roads(pk, h, {"smooth": 0.5})
        finally:
            rgm.PARALLEL_MIN_STATIONS = P0
        zo = np.abs(np.interp(xs, r0["pa"][0].x, r0["pa"][0].z) - np.interp(xs, r0["pb"][0].x, r0["pb"][0].z))
        self.assertLessEqual(float(np.abs(za - zb).max()), float(zo.max()) + 1e-6)
        mn, mx, bad, n = rg.verify(h, CELL, runs, 0.0)
        self.assertEqual(bad, 0)                                       # blending only raised or kept roads above the ground

    def test_lod_pokes_found_and_fixed(self):
        h = terrain()
        r = road("g", [(20, 150, 0), (340, 150, 0)], width=12.0)         # runs along the gully (y = 150): a coarse mesh cannot follow it
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {"smooth": 0.0})
        mn, mx, bad, n = rg.verify(h, CELL, runs, 0.0)
        self.assertEqual(bad, 0)
        before = rg.lod_pokes(h, CELL, runs, 4)
        self.assertGreater(before["g"]["max_poke_ft"], 0.05)
        h2, info = rg.lod_safe_heights(h, CELL, runs, 4)
        after = rg.lod_pokes(h2, CELL, runs, 4, tol_ft=0.0)
        self.assertEqual(after["g"]["poking"], 0, (before, after, info))
        self.assertGreater(info["lowered_vertices"], 0)
        self.assertTrue(bool((h2 <= h + 1e-6).all()))
        changed = np.argwhere(h2 != h)
        self.assertTrue(bool(((changed % 4) == 0).all()))               # only LOD vertices were touched

    def test_lod_report_in_build_terrain_heights(self):
        h = terrain()
        pk = synth(h, [road("g", [(20, 150, 0), (340, 150, 0)], width=12.0)])
        pk.entities["buildings"] = []
        old = wm.LOD_CHECK_STEPS
        try:
            wm.LOD_CHECK_STEPS = (8,)
            wm.terrain_heights(pk, carve=False, conform=True, road_grade=True)
        finally:
            wm.LOD_CHECK_STEPS = old
        rep = wm.LAST_ROAD_GRADE
        self.assertIn("lod", rep)
        self.assertTrue(any("terrain LOD step 8" in w for w in rep["warnings"]))


class RealPackTests(unittest.TestCase):
    def test_dyers_walk_has_no_buried_road(self):
        d = os.path.join(wp.REPO, "world", "bridgehollow__dyers_walk_local", "export")
        if not os.path.exists(os.path.join(d, "manifest.json")):
            self.skipTest("no Dyers Walk pack")
        import road_height_audit as ra
        rows = ra.mesh_audit(wp.load_pack(d), True)
        self.assertTrue(rows)
        for r in rows:
            self.assertEqual(r["buried_pct"], 0.0, r)
            self.assertGreater(r["min_ft"], 0.0, r)


class SkirtTexture(unittest.TestCase):
    def test_skirt_uv_continues_the_road_texture(self):
        """The skirt used u = 0 for its outer edge, so one texel column was stretched down the flank (a pale vertical band)."""
        b = wm.Builder()
        pts = [(0.0, float(i)) for i in range(5)]
        wm._ribbon(b, "m", pts, [4.0] * 5, [2.0] * 5, 10.0, skirt={"ground": lambda x, y: 0.0})
        m = b.build()
        u = m.UV[:, 0]
        self.assertGreater(float(u.max()), 4.0 / FT / 10.0 + 1e-6)          # left flank continues past the road's right-hand u
        self.assertLess(float(u.min()), -1e-6)                              # right flank continues below u = 0
        self.assertEqual(len(np.unique(np.round(u, 6))) > 3, True)


class KerbFlush(unittest.TestCase):
    def test_kerb_embedded_and_flush_with_graded_edge(self):
        """Kerb base must be below the terrain (no hovering over the skirt) and the kerb top must sit KERB_H above the graded road surface at its inner edge."""
        from shapely.geometry import LineString
        h = terrain()
        r = road("k", [(30, 60, 100.0), (300, 140, 100.0)], width=16.0)
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {})
        ring = LineString([(30, 60), (300, 140)]).buffer(8.7, cap_style=2).difference(LineString([(30, 60), (300, 140)]).buffer(8.0, cap_style=2))
        rings = [[list(p) for p in list(g.exterior.coords)[:-1]] for g in getattr(ring, "geoms", [ring])]
        e = dict(r, _grade={"runs": runs["k"], "skirt": True}, kerbs=rings)
        cx = wm.Ctx(pk)
        b = wm.Builder()
        wm._add_kerbs(cx, b, e)
        m = b.build()
        V = m.V[m.subs["mat_kerb"]].reshape(-1, 3)
        x, y, z = V[:, 0] / FT, pk.frame.height_ft - V[:, 1] / FT, V[:, 2] / FT + ZO
        g = rg.mesh_height(h, CELL, x, y)
        run = runs["k"][0]
        surf, _ = wm.kerb_heights(cx, e, list(zip(x, y)))
        low = z < surf + wm.KERB_H_FT - 0.05                                  # base vertices (not the top face)
        self.assertTrue(low.any())
        self.assertLessEqual(float((z[low] - g[low]).max()), -wm.KERB_SINK_FT + 0.02)     # all base vertices sit below the ground
        top = ~low
        self.assertLess(float(np.abs(z[top] - surf[top] - wm.KERB_H_FT).max()), 0.02)
        # inner-edge kerb top vs the road ribbon edge height (cross-slope aware): within 0.1 ft
        i = len(run.x) // 2
        d = np.hypot(x - run.x[i], y - run.y[i])
        tx, ty = np.gradient(run.x)[i], np.gradient(run.y)[i]
        lon = np.abs((x - run.x[i]) * tx + (y - run.y[i]) * ty) / math.hypot(tx, ty)
        near = top & (d < 10.0) & (lon < 0.8)
        edge = np.maximum(run.zl[i], run.zr[i]) + wm.KERB_H_FT
        edgel = np.minimum(run.zl[i], run.zr[i]) + wm.KERB_H_FT
        self.assertTrue(near.any())
        self.assertTrue(np.all((z[near] <= edge + 0.1) & (z[near] >= edgel - 0.1)))


class KerbSkirt(unittest.TestCase):
    def _build(self, pts, width=16.0):
        from shapely.geometry import LineString
        h = terrain()
        r = road("c", pts, width=width)
        pk = synth(h, [r])
        runs, rep = rg.grade_roads(pk, h, {})
        ls = LineString([(p[0], p[1]) for p in pts])
        outline = ls.buffer(width / 2, cap_style=2)
        band = outline.buffer(0.7, join_style=2).difference(outline)
        e = dict(r, _grade={"runs": runs["c"], "skirt": True}, kerbs=[[list(p) for p in list(band.exterior.coords)[:-1]]],
                 outline=[list(p) for p in list(outline.exterior.coords)[:-1]])
        cx = wm.Ctx(pk)
        b = wm.Builder()
        wm._add_kerbs(cx, b, e)
        return h, pk, runs["c"], e, b.build()

    def test_kerb_height_is_four_inches(self):
        self.assertAlmostEqual(wm.KERB_H_FT, 0.33, places=2)

    def test_annulus_has_no_lid_over_the_road(self):
        h, pk, run, e, m = self._build([(30, 60, 100.0), (300, 140, 100.0)])
        V = m.V[m.subs["mat_kerb"]]
        x = V[:, :, 0] / FT
        y = pk.frame.height_ft - V[:, :, 1] / FT
        from shapely.geometry import Polygon, Point
        road_poly = Polygon(e["outline"]).buffer(-0.5)
        c = np.stack([x.mean(1), y.mean(1)], 1)
        self.assertFalse(any(road_poly.contains(Point(p)) for p in c), "a kerb triangle lies over the road surface")

    def test_kerb_wall_columns_bury_below_dense_terrain(self):
        """Sloped and curved roads: every wall base point, and points between the 3 ft vertices, lies below the terrain sampled densely (0.5 ft)."""
        for pts in ([(30, 60, 100.0), (300, 140, 100.0)], [(40, 300, 98.0), (120, 220, 103.0), (200, 230, 101.0), (280, 120, 108.0), (340, 90, 106.0)]):
            h, pk, run, e, m = self._build([tuple(p) for p in pts])
            T = m.subs["mat_kerb"]
            V = m.V
            worst = -1e9
            n = 0
            colmin, colmax = {}, {}
            for t in T:
                for i in t:
                    k = (round(V[i][0], 4), round(V[i][1], 4))
                    colmin[k] = min(colmin.get(k, 1e9), V[i][2])
                    colmax[k] = max(colmax.get(k, -1e9), V[i][2])
            for t in T:
                P = V[list(t)]
                bs = [p for p in P if abs(p[2] - colmin[(round(p[0], 4), round(p[1], 4))]) < 1e-6 and p[2] < colmax[(round(p[0], 4), round(p[1], 4))] - 0.1]
                if len(bs) != 2:
                    continue                          # not a wall triangle with a base edge
                p0, p1 = bs
                for u in np.linspace(0, 1, 9):
                    q = p0 + (p1 - p0) * u
                    x, y = q[0] / FT, pk.frame.height_ft - q[1] / FT
                    g = float(rg.mesh_height(h, CELL, np.array([x]), np.array([y]))[0])
                    worst = max(worst, q[2] / FT + ZO - g)
                    n += 1
            self.assertGreater(n, 100)
            self.assertLess(worst, -0.1, f"a kerb base sits {worst:.2f} ft relative to terrain (must stay below)")


if __name__ == "__main__":
    unittest.main()
