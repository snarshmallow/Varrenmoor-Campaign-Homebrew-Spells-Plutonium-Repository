"""Door leaves keep their hinge translation in 3D Canvas (merged layer tiles) and roof textures/ridges have no light line.
3D Canvas helpers.applyTransforms() bakes the local matrix of every LEAF mesh (a mesh without children) into its geometry and zeroes the node: a door leaf
that is a leaf loses its hinge and swings about the tile origin. write_glb therefore gives each door node an empty child (`<door>_hinge`).
  python illustrator/generators/test_door_hinge.py"""
import json
import math
import os
import struct
import sys
import tempfile
import unittest

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402


def box(x0, x1, y0, y1, z0, z1, mat="mat_door_wood"):
    V = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0], [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    F = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6], [0, 5, 1], [0, 4, 5], [1, 6, 2], [1, 5, 6], [2, 7, 3], [2, 6, 7], [3, 4, 0], [3, 7, 4]])
    return wm.Mesh(V, np.zeros((8, 2)), {mat: F}, False)


MATS = {"mat_door_wood": {"base_color": [0.4, 0.3, 0.2], "roughness": 0.8}}


def gjson(path):
    raw = open(path, "rb").read()
    return json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])


def simulate_apply_transforms(g):
    """The module's applyTransforms on the node tree: which mesh nodes would lose their translation (leaf mesh nodes with a non-identity matrix)."""
    baked = []
    for n in g["nodes"]:
        if "mesh" in n and not n.get("children") and any(k in n for k in ("translation", "rotation", "scale")):
            baked.append(n["name"])
    return baked


class DoorHinge(unittest.TestCase):
    def write(self, path, hinge):
        nodes = [("merged", box(0, 4, 0, 4, 0, 3, "mat_door_wood"), {"merged": ["a"]}),
                 ("bld_x_door1", box(0, 0.05, 0, 1, 0, 2), {"isDoor": True, "doorId": "bld_x_door1", "doorStyle": 1, "doorAnimateAngle": 1.5708, "_t": hinge})]
        wm.write_glb(path, nodes, MATS, textures="none")

    def test_door_has_child_and_keeps_translation(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.glb")
            self.write(p, (-35.88, 12.5, 0.7))
            g = gjson(p)
            door = next(n for n in g["nodes"] if n["name"] == "bld_x_door1")
            self.assertAlmostEqual(door["translation"][0], -35.88, 4)
            self.assertAlmostEqual(door["translation"][1], 0.7, 4)                  # Blender z -> glTF y
            self.assertAlmostEqual(door["translation"][2], -12.5, 4)
            self.assertEqual(len(door.get("children", [])), 1, "the door leaf needs a child so applyTransforms does not bake its hinge")
            self.assertTrue(door["extras"]["isDoor"])
            self.assertEqual(simulate_apply_transforms(g), [], "no leaf mesh may carry a transform")
            roots = g["scenes"][0]["nodes"]
            self.assertNotIn(door["children"][0], roots)
            self.assertNotIn("mesh", g["nodes"][door["children"][0]])

    def test_merge_roundtrip_keeps_hinge(self):
        """merge_export reads every door with read_glb and writes it again: the translation (the hinge) must survive and no marker may be read as a mesh."""
        with tempfile.TemporaryDirectory() as d:
            p, q = os.path.join(d, "a.glb"), os.path.join(d, "b.glb")
            self.write(p, (3.25, -7.5, 1.1))
            nodes, _ = wm.read_glb(p)
            self.assertEqual([n[0] for n in nodes], ["merged", "bld_x_door1"])
            ex = nodes[1][1]
            self.assertAlmostEqual(ex["_t"][0], 3.25, 4)
            self.assertAlmostEqual(ex["_t"][1], -7.5, 4)
            self.assertAlmostEqual(ex["_t"][2], 1.1, 4)
            wm.write_glb(q, [(n, m, ex) for n, ex, m in nodes], MATS, textures="none")
            g = gjson(q)
            self.assertEqual(simulate_apply_transforms(g), [])
            self.assertEqual(sum(1 for n in g["nodes"] if n["name"].endswith("_hinge")), 1)
            # the door mesh stays hinge-local (its geometry is not shifted by the node translation)
            self.assertLess(max(abs(v) for v in g["accessors"][g["meshes"][1]["primitives"][0]["attributes"]["POSITION"]]["max"]), 3.0)


class RoofSeam(unittest.TestCase):
    ROOF = ("shingle", "slate", "red_tile", "thatch", "timber_roof", "w_roof_slate", "w_roof_red", "w_roof_thatch", "w_roof_timber", "w_roof_snow")

    def test_wrap_is_no_harder_than_a_course_edge(self):
        """Both axes: the step across the wrap (last row/col against the first) may not exceed the largest step inside the texture (a course edge is
        a real edge; the wrap must not be a worse one)."""
        d = os.path.join(HERE, "..", "presets", "textures")
        for n in self.ROOF:
            a = np.asarray(Image.open(os.path.join(d, n + ".png")).convert("RGB"), float)
            L = pbr._lum(a)
            for ax in (1, 0):
                edge = np.abs(np.take(L, 0, ax) - np.take(L, -1, ax)).mean()
                inner = np.abs(np.diff(L, axis=ax)).mean(axis=1 - ax).max()
                self.assertLessEqual(edge, inner * 1.05 + 1.0, f"{n} axis {ax}: wrap step {edge:.1f} vs largest inner step {inner:.1f}")

    def test_ridge_lands_on_darkest_row(self):
        for mat in ("mat_shingle", "mat_slate", "mat_thatch"):
            ph = wm.ridge_phase(mat)
            a = np.asarray(pbr.base_texture(mat)[0], float)
            prof = pbr._lum(a).mean(1)
            row = int(ph * len(prof))
            self.assertLess(prof[row], np.percentile(prof, 40), mat)
        # a sloped face: its highest vertex gets exactly that v phase
        pts = [(0, 0, 0), (10, 0, 0), (10, 5, 3), (0, 5, 3)]
        for ph in (0.06, 0.5):
            uv = wm.world_uv(pts, 4.0, (0.3, 0.77), 0.0, anchor_v=ph)
            top = max(range(4), key=lambda i: pts[i][2])
            diff = (uv[top][1] - ph) % 1.0
            self.assertLess(min(diff, 1.0 - diff), 1e-6)
        flat = wm.world_uv([(0, 0, 1), (4, 0, 1), (4, 4, 1)], 4.0, anchor_v=0.5)
        self.assertEqual(flat, wm.world_uv([(0, 0, 1), (4, 0, 1), (4, 4, 1)], 4.0))   # flat faces ignore the anchor


class TerrainUV(unittest.TestCase):
    def test_uv_stay_inside_the_image(self):
        """A height grid wider than the frame gave UV up to 1.02; with the clamping albedo sampler that smeared one texel over the strip (east edge streaks)."""
        from types import SimpleNamespace as NS
        h = np.zeros((6, 7))                    # 7 columns x 2.5 ft = 15 ft reach, frame only 14.5 ft wide
        cx = NS(pack=NS(cell_ft=2.5), h=h, fr=NS(width_ft=14.5, height_ft=12.0, z_origin_ft=0.0))
        m = wm.build_terrain(cx)
        self.assertLessEqual(float(m.UV.max()), 1.0)
        self.assertGreaterEqual(float(m.UV.min()), 0.0)
        east = m.V[:, 0] >= m.V[:, 0].max() - 1e-9
        self.assertGreater(float(m.UV[east, 0].min()), 0.9)       # folded back, not wrapped to 0


if __name__ == "__main__":
    unittest.main(verbosity=2)
