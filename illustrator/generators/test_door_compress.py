"""gltfpack puts a mesh into a child of its node, which moves `isDoor` onto the parent: 3D Canvas (child.isMesh && userData.isDoor) would not find the door.
merge_export therefore leaves files that contain door nodes uncompressed. Small draft place in a temp world root; nothing in world/ is touched.
  python illustrator/generators/test_door_compress.py"""
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import place_create as pc  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_split as ws  # noqa: E402

TMP = tempfile.mkdtemp(prefix="doorcomp_")


def glb_json(path):
    raw = open(path, "rb").read()
    return json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]]), raw


class DoorCompress(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = {"name": "Door Test", "id": "door_test", "culture": "english", "size_ft": [1200, 1200], "seed": 5}
        pc.create(spec, out_root=TMP, force=True, draft=True, no_town=True)           # terrain and water only (the town generator reads the real world/)
        cls.pdir = os.path.join(TMP, "door_test")
        os.makedirs(os.path.join(cls.pdir, "buildings"), exist_ok=True)
        sq = [[560, 560], [600, 560], [600, 585], [560, 585]]
        cls.bid = "bld_door_test"
        json.dump({"id": cls.bid, "name": "Door test house", "kind": "house", "status": "proposed", "geometry": {"type": "polygon", "points": sq}, "notes": "",
                   "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": 1, "rooms": [{"id": "rm_a", "name": "A"}], "doors": [], "elevation_ft": 100.0,
                   "site_slope": 0.0, "site_relief_ft": 1.0}, open(os.path.join(cls.pdir, "buildings", cls.bid + ".json"), "w"))
        json.dump({"doors": [{"id": "door_t1", "building": cls.bid, "point": [580, 560], "width_ft": 3.5}]}, open(os.path.join(cls.pdir, "details.json"), "w"))
        cls.pack = os.path.join(TMP, "pack")
        wp.export_world("door_test", cls.pack, world_root=TMP, timestamp="2026-01-01T00:00:00+00:00", lod=(4,), log=lambda m: None)
        ws.split_export(cls.pack, log=lambda m: None)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def test_files_with_doors_stay_uncompressed(self):
        if not shutil.which("gltfpack"):
            self.skipTest("gltfpack not installed")
        out = os.path.join(TMP, "opt")
        doc, rep = ws.merge_export(self.pack, "layer", out_dir=out, compress="quant", log=lambda m: None)
        self.assertGreater(rep["door_nodes"], 0, "the test pack should contain a door node")
        self.assertEqual(rep["door_nodes"], sum(e.get("doors", 0) for e in doc["files"]))
        n_quant = 0
        for e in doc["files"]:
            g, raw = glb_json(os.path.join(out, e["file"]))
            if e.get("doors"):
                self.assertEqual(e["compression"], "none (has doors)")
                self.assertNotIn("KHR_mesh_quantization", json.dumps(g.get("extensionsUsed", [])))
                dn = [n for n in g["nodes"] if (n.get("extras") or {}).get("isDoor")]
                self.assertEqual(len(dn), e["doors"])
                self.assertTrue(all("mesh" in n for n in dn), "isDoor must sit on the node that owns the mesh")
            elif e.get("compression") == "quant":
                n_quant += 1
        self.assertGreater(n_quant, 0, "files without doors are still compressed")


if __name__ == "__main__":
    unittest.main(verbosity=1)
