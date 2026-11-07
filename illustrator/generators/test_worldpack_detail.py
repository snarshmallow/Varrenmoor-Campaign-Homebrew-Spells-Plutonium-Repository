"""Tests for worldpack_detail (hollow buildings with openings, door leaf nodes) and for worldio's negative-origin terrain crop (--local-origin children).
  python illustrator/generators/test_worldpack_detail.py"""
import json
import math
import os
import struct
import sys
import tempfile
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldio  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

FT = wm.FT


def make_ctx():
    fr = wp.Frame(100, 80, 0.0)
    pack = types.SimpleNamespace(frame=fr, heights=np.zeros((9, 11), np.float32), cell_ft=10.0)
    return wm.Ctx(pack)


def building(floors=1, with_door=True):
    e = {"id": "bld_t", "polygon": [[30, 20], [54, 20], [54, 34], [30, 34]], "base_elevation_ft": 0.0, "skirt_depth_ft": 1.0, "floors": floors,
         "wall_height_ft": 10.0 * floors, "height_ft": 10.0 * floors + 4, "obb": {"center": [42, 27], "angle_deg": 0.0, "length_ft": 24, "width_ft": 14},
         "roof": {"type": "gable", "pitch": 0.6, "ridge_height_ft": 4.2, "overhang_ft": 1.0, "surface": {"material": "mat_shingle", "tile_ft": 14}},
         "wall": {"surface": {"material": "mat_plank", "tile_ft": 8}}}
    if with_door:
        e["openings"] = {"doors": [{"id": "bld_t_door1", "point": [42, 34], "width_ft": 3.5}]}
    return e


class DetailTests(unittest.TestCase):
    def test_openings_thickness_and_door_node(self):
        cx = make_ctx()
        e = building()
        mesh, doors = wd.build_building_detailed(cx, e)
        self.assertEqual(len(doors), 1)
        d = doors[0]
        self.assertEqual(d["extras"]["isDoor"], True)
        self.assertEqual(d["extras"]["doorId"], "bld_t_door1")
        lo, hi = d["mesh"].bbox()
        self.assertAlmostEqual(hi[0] - lo[0], (3.5 - 0.04 / 0.3048) * FT, delta=0.05)     # leaf width = opening minus gap
        self.assertAlmostEqual(lo[0], 0.0, places=3)                                      # origin on the hinge
        for mat in ("mat_plank", "mat_plaster", "mat_trim", "mat_glass", "mat_interior_floor", "mat_shingle"):
            self.assertIn(mat, mesh.subs)
        # wall thickness: some vertices lie 0.75 ft inside the outer wall plane (south wall y = 80-34 ft in Blender frame)
        ys = np.unique(np.round(mesh.V[:, 1] / FT, 3))
        outer = 80 - 34
        self.assertTrue(any(abs(y - (outer + wd.WALL_T_FT)) < 0.01 for y in ys))
        # no vertex of the door leaf sits outside the hole (it fits the 3.5 x 7 ft opening)
        self.assertLessEqual(hi[2] / FT, wd.DOOR_H_FT)

    def test_window_counts_per_storey(self):
        cx = make_ctx()
        m1, _ = wd.build_building_detailed(cx, building(1))
        m2, _ = wd.build_building_detailed(cx, building(2))
        g1, g2 = len(m1.subs["mat_glass"]), len(m2.subs["mat_glass"])
        self.assertGreater(g1, 0)
        self.assertEqual(g2, 2 * g1)               # same windows on both storeys (door only on the ground floor)

    def test_no_openings_uses_single_skin(self):
        cx = make_ctx()
        e = building(with_door=False)
        self.assertNotIn("mat_trim", wm.build_building(cx, e).subs)

    def test_glb_node_translation(self):
        cx = make_ctx()
        mesh, doors = wd.build_building_detailed(cx, building())
        with tempfile.TemporaryDirectory() as t:
            p = os.path.join(t, "b.glb")
            mats = {k: {"mean_color": v[0], "roughness": v[1], **({"alpha": v[2]} if v[2] else {})} for k, v in wd.DETAIL_MATS.items()}
            nodes = [("bld_t", mesh, {})] + [(doors[0]["id"], doors[0]["mesh"], {**doors[0]["extras"], "_t": (1.0, 2.0, 3.0)})]
            wm.write_glb(p, nodes, mats, textures="none")
            b = open(p, "rb").read()
            n = struct.unpack("<I", b[12:16])[0]
            j = json.loads(b[20:20 + n])
        door = [x for x in j["nodes"] if x["name"] == "bld_t_door1"][0]
        self.assertEqual(door["translation"], [1.0, 3.0, -2.0])           # glTF Y-up
        self.assertTrue(door["extras"]["isDoor"])
        self.assertNotIn("_t", door["extras"])
        self.assertTrue(any(m.get("alphaMode") == "BLEND" for m in j["materials"]))


class NegativeOriginTerrain(unittest.TestCase):
    def test_crop_starting_before_the_frame(self):
        with tempfile.TemporaryDirectory() as t:
            pl = os.path.join(t, "p", "terrain")
            os.makedirs(pl)
            h = np.arange(12, dtype=np.float32).reshape(3, 4)
            np.save(os.path.join(pl, "heightmap.npy"), h)
            json.dump({"cell_ft": 2.5, "nx": 4, "ny": 3, "origin_ft": [-2.5, 5.0], "size_ft": [7.5, 5.0]}, open(os.path.join(pl, "terrain_meta.json"), "w"))
            json.dump({"id": "p"}, open(os.path.join(t, "p", "place.json"), "w"))
            out, meta = worldio.load_terrain("p", root=t)
        # first column is dropped (x < 0), two rows of padding (y offset 5 ft = 2 cells) are added on top
        self.assertEqual(out.shape, (3 + 2, 3))
        self.assertTrue(np.array_equal(out[2:], h[:, 1:]))
        self.assertEqual(meta["origin_ft"], [0.0, 0.0])


if __name__ == "__main__":
    unittest.main()
