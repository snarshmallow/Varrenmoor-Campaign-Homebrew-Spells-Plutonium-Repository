"""Tests for interiors.py (layout generator), worldpack_interiors.py (3D) and interiors_render.py.
  python illustrator/generators/test_interiors.py"""
import json
import math
import os
import sys
import tempfile
import unittest

import numpy as np
from shapely.geometry import LineString, Point, Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import interiors as I  # noqa: E402
import interiors_render as ir  # noqa: E402
import test_worldpack_detail as twd  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_interiors as wi  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

REPO = os.path.dirname(os.path.dirname(HERE))
FT = wm.FT


def bld(bid="bld_t", floors=1, kind="house", poly=None, door=(42, 34)):
    poly = poly or [[30, 20], [54, 20], [54, 34], [30, 34]]
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    return {"id": bid, "kind": kind, "floors": floors, "polygon": poly, "obb": {"center": [cx, cy], "angle_deg": 0.0}}, [{"id": bid + "_door1", "point": list(door), "width_ft": 3.5, "facing": [0, 1]}]


CASES = [dict(floors=1), dict(floors=2), dict(floors=2, poly=[[30, 20], [44, 20], [44, 29], [30, 29]], door=(37, 29)),
         dict(floors=3, kind="inn", poly=[[10, 10], [40, 12], [39, 32], [11, 30]], door=(25, 31)),
         dict(floors=1, kind="workshop", poly=[[0, 0], [26, 6], [22, 20], [-4, 14]], door=(11, 17)), dict(floors=1, kind="barn", poly=[[0, 0], [30, 0], [30, 16], [0, 16]], door=(15, 16)),
         dict(floors=2, bid="bld_x_77", poly=[[5, 5], [20, 9], [17, 20], [3, 15]], door=(11, 17.5))]


def layouts():
    for c in CASES:
        b, d = bld(**c)
        yield b, d, I.generate_layout(b, d)


class LayoutTests(unittest.TestCase):
    def test_room_coverage(self):
        for b, d, L in layouts():
            F = Polygon(b["polygon"]).buffer(-I.WALL_T, join_style=2, mitre_limit=5.0)
            for s in range(b["floors"]):
                rs = [Polygon(r["polygon"]) for r in L["rooms"] if r["floor"] == s]
                self.assertTrue(rs, b["id"])
                self.assertAlmostEqual(sum(r.area for r in rs), F.area, delta=F.area * 0.02, msg=f"{b['id']} floor {s}")
                for i in range(len(rs)):
                    for j in range(i + 1, len(rs)):
                        self.assertLess(rs[i].intersection(rs[j]).area, 0.05)
                    self.assertGreater(rs[i].area, 20)

    def test_doors_connected(self):
        for b, d, L in layouts():
            ext = [x for x in L["doors"] if x["kind"] == "exterior"]
            self.assertEqual(len(ext), len(d))
            self.assertEqual(ext[0]["id"], d[0]["id"])
            self.assertEqual(ext[0]["rooms"][0], L["entry_room"])
            for s in range(b["floors"]):
                ids = [r["id"] for r in L["rooms"] if r["floor"] == s]
                g = {i: set() for i in ids}
                for x in L["doors"]:
                    if x["kind"] == "interior" and x["floor"] == s:
                        a, c = x["rooms"]
                        g[a].add(c)
                        g[c].add(a)
                seen, todo = {ids[0]}, [ids[0]]
                while todo:
                    for n in g[todo.pop()]:
                        if n not in seen:
                            seen.add(n)
                            todo.append(n)
                self.assertEqual(seen, set(ids), f"{b['id']} floor {s} rooms not all connected")
            walls = {w["id"]: w for w in L["walls"]}
            for x in L["doors"]:
                if x["kind"] == "interior":
                    w = walls[x["wall"]]
                    self.assertLess(LineString([w["a"], w["b"]]).distance(Point(x["point"])), 0.05)
                    self.assertLessEqual(x["width_ft"] / 2, math.dist(w["a"], w["b"]) / 2 + 1e-6)

    def test_stairs_reach_every_floor(self):
        for b, d, L in layouts():
            self.assertEqual(len(L["stairs"]), b["floors"] - 1)
            rooms = {r["id"]: r for r in L["rooms"]}
            for st in L["stairs"]:
                self.assertEqual(rooms[st["room_lower"]]["floor"], st["from_floor"])
                self.assertEqual(rooms[st["room_upper"]]["floor"], st["to_floor"])
                sp = Polygon(st["polygon"])
                for rid in (st["room_lower"], st["room_upper"]):
                    self.assertTrue(Polygon(rooms[rid]["polygon"]).buffer(0.05).contains(sp), f"{b['id']} stair outside room")
                self.assertEqual(st["risers"] * 0.625, st["rise_ft"])
            self.assertEqual({st["to_floor"] for st in L["stairs"]}, set(range(1, b["floors"])))
            for x in L["doors"]:
                for st in L["stairs"]:
                    if x["floor"] == st["from_floor"]:
                        self.assertGreater(Polygon(st["polygon"]).distance(Point(x["point"])), 0.2)

    def test_fixtures_and_windows(self):
        for b, d, L in layouts():
            rooms = {r["id"]: Polygon(r["polygon"]) for r in L["rooms"]}
            hole = {st["to_floor"]: Polygon(st["hole"]) for st in L["stairs"]}
            for f in L["fixtures"]:
                self.assertTrue(rooms[f["room"]].buffer(0.1).contains(Point(f["point"])), f["id"])
                if f["floor"] in hole:
                    self.assertFalse(hole[f["floor"]].contains(Point(f["point"])))
            outer = Polygon(b["polygon"]).exterior
            for w in L["windows"]:
                self.assertLess(outer.distance(Point(w["point"])), 0.05)

    def test_deterministic_and_seeded(self):
        b, d = bld()
        a1, a2 = I.generate_layout(b, d), I.generate_layout(b, d)
        self.assertEqual(json.dumps(a1, sort_keys=True), json.dumps(a2, sort_keys=True))
        self.assertEqual(I.seed_for("bld_t"), I.seed_for("bld_t"))
        self.assertNotEqual(I.seed_for("bld_t"), I.seed_for("bld_other"))

    def test_real_pack_buildings(self):
        root = os.path.join(REPO, "world", "bridgehollow__dyers_walk_local")
        if not os.path.isdir(root):
            self.skipTest("no test place")
        dets = json.load(open(os.path.join(root, "details.json")))["doors"]
        bd = os.path.join(root, "buildings")
        n = 0
        for f in sorted(os.listdir(bd)):
            bj = json.load(open(os.path.join(bd, f)))
            L = I.generate_layout(I.building_for_layout(bj), [x for x in dets if x["building"] == bj["id"]])
            self.assertEqual(len(L["stairs"]), bj.get("floors", 1) - 1, bj["id"])
            n += 1
        self.assertGreaterEqual(n, 20)

    def test_apply_layout_json_roundtrip(self):
        b, d = bld(floors=2)
        L = I.generate_layout(b, d)
        bj = {"id": "bld_t", "rooms": [], "doors": []}
        I.apply_layout(bj, L)
        again = json.loads(json.dumps(bj))
        self.assertEqual(len(again["rooms"]), len(L["rooms"]))
        self.assertEqual(again["layout"]["entry_room"], L["entry_room"])


def entity(floors=1):
    e = twd.building(floors=floors)
    b, d = bld(floors=floors)
    L = I.generate_layout(b, d)
    e["id"] = "bld_t"
    e["openings"]["doors"] = d
    e["rooms"], e["doors"] = L["rooms"], L["doors"]
    e["layout"] = {k: v for k, v in L.items() if k not in ("rooms", "doors")}
    return e, L


class MeshTests(unittest.TestCase):
    def test_nodes_and_doors(self):
        cx = twd.make_ctx()
        for floors in (1, 2):
            e, L = entity(floors)
            m, dn = wd.build_building_detailed(cx, e)
            full, doors, extra = wi.add_interior(cx, e, m, dn)
            nodes = extra["layered_nodes"]
            names = [n for n, _, _ in nodes]
            for want in ("bld_t", "bld_t_roof", "bld_t_int_f0"):
                self.assertIn(want, names)
            props = [ex for n, _, ex in nodes if "_props_" in n]
            self.assertTrue(props)
            self.assertTrue(all("prop" in ex["tags"] for ex in props))
            if floors == 2:
                self.assertIn("bld_t_shell_f1", names)
                self.assertIn("bld_t_int_f1", names)
            self.assertEqual(len(doors), len(L["doors"]))
            self.assertTrue(all(x["extras"]["isDoor"] for x in doors))
            self.assertEqual({x["id"] for x in doors}, {x["id"] for x in L["doors"]})
            self.assertEqual(sum(mm.tri_count for _, mm, _ in nodes), full.tri_count)
            if floors == 2:
                z_split = (e["base_elevation_ft"] - cx.fr.z_origin_ft + 10.0) * FT
                lo0, hi0 = [mm for n, mm, _ in nodes if n == "bld_t"][0].bbox()
                lo1, hi1 = [mm for n, mm, _ in nodes if n == "bld_t_shell_f1"][0].bbox()
                self.assertLessEqual(hi0[2], z_split + 1e-6)
                self.assertGreaterEqual(lo1[2], z_split - 1e-6)

    def test_band_split_conserves_area(self):
        b = wm.Builder()
        b.face("m", [(0, 0, 0), (2, 0, 0), (2, 0, 6), (0, 0, 6)], [(0, 0), (1, 0), (1, 1), (0, 1)])
        parts = wi._band_split(b.build(), [2.0, 4.0])

        def area(m):
            a = 0.0
            for F in m.subs.values():
                for t in F:
                    p = m.V[t]
                    a += np.linalg.norm(np.cross(p[1] - p[0], p[2] - p[0])) / 2
            return a
        self.assertAlmostEqual(sum(area(p) for p in parts), 12.0, places=6)
        self.assertAlmostEqual(area(parts[1]), 4.0, places=6)

    def test_window_hook_builds(self):
        cx = twd.make_ctx()
        e, L = entity(1)
        m, dn = wd.build_building_detailed(cx, e)
        self.assertGreater(m.tri_count, 0)
        self.assertEqual(len(dn), 1)


class RenderTests(unittest.TestCase):
    def test_render_building(self):
        b, d = bld(floors=2)
        L = I.generate_layout(b, d)
        bj = {"id": "bld_t", "name": "T", "polygon": b["polygon"], "rooms": L["rooms"], "doors": L["doors"], "layout": {k: v for k, v in L.items() if k not in ("rooms", "doors")}}
        with tempfile.TemporaryDirectory() as td:
            ir.render_building(bj, os.path.join(td, "x"), 10.0)
            self.assertGreater(os.path.getsize(os.path.join(td, "x.png")), 1000)
            self.assertIn("Hall", open(os.path.join(td, "x.svg"), encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main()
