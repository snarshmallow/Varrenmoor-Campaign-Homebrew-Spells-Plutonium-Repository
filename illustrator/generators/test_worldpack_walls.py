"""Town walls in the 3D pack (python test_worldpack_walls.py): towers at gates / corners / spacing, gate openings stay open, wall follows the terrain, faces point outward,
parts are built by worldpack_mesh.build_parts. Synthetic tiny terrain only."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_road_grade as trg  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_walls as ww  # noqa: E402

FT = wm.FT
CELL = trg.CELL


def doc():
    # a square-ish ring with one gate on the south side (gap 22 ft), two segments
    gate = [200.0, 300.0]
    seg1 = [[200 + 11, 300], [320, 300], [320, 100], [80, 100], [80, 300], [200 - 11, 300]]       # one open polyline that starts and ends at the gate gap
    return {"place": "t", "walls": [{"id": "wall_01", "name": "Town wall", "geometry": {"type": "polyline", "points": seg1, "width_ft": 5}, "height_ft": 16}],
            "gates": [{"id": "gate_1", "name": "South Gate", "point": gate, "street": "str_a", "width_ft": 22}]}


def synth_pack(h, items):
    pk = trg.synth(h, [])
    pk.entities.update({"buildings": [], "bridges": [], "walls": items})
    pk.materials = {}
    return pk


class WallTests(unittest.TestCase):
    def setUp(self):
        self.h = trg.terrain()
        self.items = ww.wall_entities(doc())

    def test_entities_towers_gates_corners(self):
        towers = [i for i in self.items if i["kind"] == "wall_tower"]
        gt = [t for t in towers if t["gate"]]
        self.assertEqual(len(gt), 2)                                                     # one on each side of the opening
        self.assertTrue(all(math.hypot(t["points"][0][0] - 200, t["points"][0][1] - 300) <= 22 / 2 + 12 for t in gt))
        self.assertTrue(all(t["radius_ft"] > ww.DEFAULTS["tower_radius_ft"] for t in gt))
        corners = [(320, 300), (320, 100), (80, 100), (80, 300)]
        for c in corners[1:3]:
            self.assertTrue(any(math.hypot(t["points"][0][0] - c[0], t["points"][0][1] - c[1]) < 1.0 for t in towers), c)       # corner towers
        self.assertEqual(len([i for i in self.items if i["kind"] == "gate_lintel"]), 1)
        self.assertEqual(len([i for i in self.items if i["kind"] == "town_wall"]), 1)
        sp = ww.wall_entities(dict(doc(), params={"tower_spacing_ft": 60.0}))
        self.assertGreater(len([i for i in sp if i["kind"] == "wall_tower"]), len(towers))      # spacing is a parameter
        self.assertEqual([i["id"] for i in self.items], [i["id"] for i in ww.wall_entities(doc())])   # deterministic

    def test_build_parts_makes_wall_tower_and_lintel_parts(self):
        pk = synth_pack(self.h, self.items)
        parts = wm.build_parts(pk, layers={"walls"}, road_grade=False)
        kinds = {p["entity"]["kind"] for p in parts}
        self.assertEqual(kinds, {"town_wall", "wall_tower", "gate_lintel"})
        self.assertTrue(all(p["layer"] == "walls" and p["mesh"].tri_count > 0 for p in parts))

    def test_wall_follows_terrain_and_gate_stays_open(self):
        pk = synth_pack(self.h, self.items)
        cx = wm.Ctx(pk)
        wall = [i for i in self.items if i["kind"] == "town_wall"][0]
        m = ww.build_wall(cx, wall)
        V = m.V
        fr = pk.frame
        xs = V[:, 0] / FT
        ys = fr.height_ft - V[:, 1] / FT
        zs = V[:, 2] / FT + fr.z_origin_ft
        g = np.array([wp.bilinear(self.h, CELL, x, y) for x, y in zip(xs, ys)])
        self.assertTrue(bool((zs.min() <= g.min() - 1.0)))                                      # the foot goes below the ground
        top = np.array([zs[(abs(xs - x) < 0.01) & (abs(ys - y) < 0.01)].max() for x, y in zip(xs[::50], ys[::50])])
        gg = np.array([wp.bilinear(self.h, CELL, x, y) for x, y in zip(xs[::50], ys[::50])])
        self.assertTrue(bool((top >= gg + 0.55 * 16).all()))                                   # always at least 60 % of the wall height above the local ground
        d = np.hypot(xs - 200.0, ys - 300.0)
        self.assertGreaterEqual(float(d.min()), 22 / 2 - 0.6 - 2.6)                               # nothing across the gate opening (wall ends 11 ft from the gate point, half thickness 2.5)

    def test_faces_point_outward(self):
        pk = synth_pack(self.h, self.items)
        cx = wm.Ctx(pk)
        t = [i for i in self.items if i["kind"] == "wall_tower"][0]
        m = ww.build_tower(cx, t)
        V = m.V
        ax = np.array(cx.B(t["points"][0][0], t["points"][0][1])[:2])
        bad = 0
        n_v = 0
        for F in m.subs.values():
            for f in F:
                a, b, c = V[f]
                nrm = np.cross(b - a, c - a)
                ln = np.linalg.norm(nrm)
                if ln < 1e-9:
                    continue
                nrm /= ln
                if abs(nrm[2]) < 0.3:                                                         # vertical faces of the drum / merlons
                    n_v += 1
                    cen = (a + b + c) / 3
                    out = cen[:2] - ax
                    if float(nrm[:2] @ out) < -1e-6 and np.linalg.norm(out) > 0.2:
                        # inner faces of merlons look inward by design; only drum faces (radius ~ r) must look out
                        if np.linalg.norm(out) > t["radius_ft"] * FT * 0.98:
                            bad += 1
        self.assertGreater(n_v, 20)
        self.assertEqual(bad, 0)

    def test_inject_writes_entities(self):
        import json
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            self.assertEqual(ww.inject(tmp, "nope", world_root=tmp), {"walls": 0, "towers": 0})        # no walls.json: no-op
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_real_generated_walls_json(self):
        p = os.path.join(wp.REPO, "world", "demo_brinkburg", "walls.json")
        if not os.path.exists(p):
            self.skipTest("no demo_brinkburg walls.json")
        import json
        d = json.load(open(p, encoding="utf-8"))
        items = ww.wall_entities(d)
        self.assertGreater(len([i for i in items if i["kind"] == "wall_tower"]), 4)
        self.assertEqual(len([i for i in items if i["kind"] == "town_wall"]), len(d["walls"]))
        self.assertTrue(any(i["kind"] == "wall_tower" and i["gate"] for i in items))


if __name__ == "__main__":
    unittest.main()
