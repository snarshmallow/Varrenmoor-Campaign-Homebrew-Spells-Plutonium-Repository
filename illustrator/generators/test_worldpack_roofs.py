"""Roof modes (worldpack_roofs.py): none / per_building / per_scene through split, merge and the Foundry tile flags. Small draft place in a temp world root.
  python illustrator/generators/test_worldpack_roofs.py"""
import argparse
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import place_create as pc  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_split as ws  # noqa: E402

TMP = tempfile.mkdtemp(prefix="roofs_")
quiet = lambda m: None  # noqa: E731


def glb(path):
    with open(path, "rb") as f:
        raw = f.read()
    return json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])


CEIL = ("mat_ceiling", "mat_int_plank", "mat_int_lime", "mat_int_boards", "mat_int_slab")      # ceiling materials of the interior styles (plank also = floor: compare, do not assume zero)


def mat_tris(path, mats=CEIL, node_filter=lambda n: True):
    """Triangles of the given materials in the nodes of a GLB accepted by node_filter(node name)."""
    j = glb(path)
    t = 0
    for n in j["nodes"]:
        if "mesh" in n and node_filter(n["name"]):
            for pr in j["meshes"][n["mesh"]]["primitives"]:
                if j["materials"][pr["material"]]["name"] in mats:
                    t += j["accessors"][pr["indices"]]["count"] // 3
    return t


def outside_roof_tris(pack, doc):
    """Ceiling-material triangles in the building files outside the `_roof` node."""
    return sum(mat_tris(os.path.join(pack, e["file"]), CEIL, lambda n: not n.endswith("_roof")) for e in doc["files"] if e["layer"] == "buildings")


def house(pdir, bid, x0, y0, door):
    sq = [[x0, y0], [x0 + 40, y0], [x0 + 40, y0 + 25], [x0, y0 + 25]]
    json.dump({"id": bid, "name": bid, "kind": "house", "status": "proposed", "geometry": {"type": "polygon", "points": sq}, "notes": "",
               "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": 1, "rooms": [{"id": "rm_a", "name": "A"}], "doors": [], "elevation_ft": 100.0,
               "site_slope": 0.0, "site_relief_ft": 1.0}, open(os.path.join(pdir, "buildings", bid + ".json"), "w"))
    return {"id": f"door_{bid}", "building": bid, "point": door, "width_ft": 3.5}


class RoofModes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pc.create({"name": "Roof Test", "id": "roof_test", "culture": "english", "size_ft": [1200, 1200], "seed": 5}, out_root=TMP, force=True, draft=True, no_town=True)
        pdir = os.path.join(TMP, "roof_test")
        os.makedirs(os.path.join(pdir, "buildings"), exist_ok=True)
        d1 = house(pdir, "bld_roof_a", 560, 560, [580, 560])       # has a door -> detailed building with generated interior layout
        house(pdir, "bld_roof_b", 640, 560, None)                   # no door -> plain single-skin building
        json.dump({"doors": [d1]}, open(os.path.join(pdir, "details.json"), "w"))
        cls.pack = os.path.join(TMP, "pack")
        wp.export_world("roof_test", cls.pack, world_root=TMP, timestamp="2026-01-01T00:00:00+00:00", lod=(4,), log=quiet)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)

    def split(self, mode):
        return ws.split_export(self.pack, log=quiet, roof_mode=mode, split=ws.parse_split(None, "default", mode))

    def tris(self, doc, layers):
        return sum(e["tris"] for e in doc["files"] if e["layer"] in layers)

    def test_modes(self):
        base = self.split("none")
        self.assertEqual(base["roof_mode"], "none")
        self.assertFalse([e for e in base["files"] if e["layer"] == "roofs"])
        total = self.tris(base, {"buildings"})
        self.assertGreater(total, 0)
        # mode none: no roof toggle tile; the top ceiling stays in the building file, but inside the toggle-able `_roof` node (hide that node for the cutaway)
        rn = sum(mat_tris(os.path.join(self.pack, e["file"]), CEIL, lambda n: n.endswith("_roof")) for e in base["files"] if e["layer"] == "buildings")
        self.assertGreater(rn, 0, "top ceiling plate is in the _roof node")
        out0 = outside_roof_tris(self.pack, base)

        pb = self.split("per_building")
        roofs = [e for e in pb["files"] if e["layer"] == "roofs"]
        self.assertEqual(sorted(e["file"] for e in roofs), ["models/roofs/bld_roof_a_roof.glb", "models/roofs/bld_roof_b_roof.glb"])
        for e in roofs:
            self.assertEqual(e["roof"]["mode"], "per_building")
            self.assertEqual(len(e["roof"]["buildings"]), 1)
            self.assertTrue(os.path.exists(os.path.join(self.pack, e["file"])))
            nd = glb(os.path.join(self.pack, e["file"]))["nodes"]
            self.assertTrue(nd[0]["extras"]["isRoof"])
            self.assertGreater(e["pivot"]["rel_z_ft"], 0, "roof tile sits at the eaves, not on the ground")
        self.assertEqual(self.tris(pb, {"buildings"}) + self.tris(pb, {"roofs"}), total, "no triangle lost or duplicated")
        self.assertGreater(self.tris(pb, {"roofs"}), 0)
        rc = sum(mat_tris(os.path.join(self.pack, e["file"])) for e in roofs)
        self.assertEqual(rc, rn, "per_building: the roof tile holds exactly the ceiling triangles of the _roof node")
        self.assertEqual(outside_roof_tris(self.pack, pb), out0, "per_building: building files keep only floors / lower ceilings, no top ceiling")
        self.assertEqual(wp._jload(os.path.join(self.pack, "manifest.json"))["foundry"]["roof_mode"], "per_building")
        names = {n["name"] for e in pb["files"] if e["layer"] == "buildings" for n in glb(os.path.join(self.pack, e["file"]))["nodes"]}
        self.assertFalse([n for n in names if n.endswith("_roof")], "roof nodes left the building files")

        # merge keeps every roof file separate, whatever the preset
        for preset in ("layer", "all"):
            doc, rep = ws.merge_export(self.pack, preset, out_dir=os.path.join(TMP, "opt_" + preset), log=quiet)
            mr = [e for e in doc["files"] if e["layer"] == "roofs"]
            self.assertEqual(len(mr), 2, preset)
            self.assertTrue(all(e["roof"]["mode"] == "per_building" and glb(os.path.join(TMP, "opt_" + preset, e["file"]))["nodes"][0]["extras"]["isRoof"] for e in mr))
            self.assertFalse([e for e in doc["files"] if e["layer"] == "mixed" and "roofs" in e["layers"]], preset)

        # tile flags + the roofs command
        calib = {"ppf": 20.0, "x0": 0.0, "y0": 0.0, "sceneX": 0, "sceneY": 0}
        a = argparse.Namespace(layers=None, ids=None, lod=0, roofs_hidden=True)
        items = fp.build_model_tiles(pb, calib, a, None)
        rt = [i for i in items if "roofs/" in i["data"]["flags"][fp.FLAG]["modelFile"]]
        self.assertEqual(len(rt), 2)
        self.assertTrue(all(i["data"]["hidden"] and i["data"]["flags"][fp.FLAG]["roof"]["scope"] == "building" for i in rt))
        self.assertFalse([i for i in items if "roof" in i["data"]["flags"][fp.FLAG] and i not in rt])
        sc = {"uuid": "Scene.x", "tiles": [{"_id": f"t{n}", "hidden": n == 0, "flags": {fp.FLAG: i["data"]["flags"][fp.FLAG]}} for n, i in enumerate(rt)] + [{"_id": "tb", "flags": {fp.FLAG: {}}}]}
        self.assertEqual({d["hidden"] for _, d in fp.roof_tile_updates(sc, "toggle")}, {True})     # one visible -> hide all
        self.assertEqual(fp.roof_tile_updates(sc, "show")[0][1], {"hidden": False})
        self.assertEqual(len(fp.roof_tile_updates(sc, "hide", ["bld_roof_a"])), 1)

        ps = self.split("per_scene")
        roofs = [e for e in ps["files"] if e["layer"] == "roofs"]
        self.assertEqual([e["file"] for e in roofs], ["models/roofs.glb"])
        self.assertEqual(sorted(roofs[0]["roof"]["buildings"]), ["bld_roof_a", "bld_roof_b"])
        self.assertEqual(len(glb(os.path.join(self.pack, "models/roofs.glb"))["nodes"]), 1, "ONE roof mesh for the whole scene")
        self.assertFalse(os.path.exists(os.path.join(self.pack, "models", "roofs")), "old per-building roof files removed")
        self.assertEqual(self.tris(ps, {"buildings"}) + self.tris(ps, {"roofs"}), total)
        self.assertEqual(mat_tris(os.path.join(self.pack, "models/roofs.glb")), rc, "per_scene: the same ceiling triangles sit in the merged roofs tile")
        self.assertEqual(outside_roof_tris(self.pack, ps), out0)
        self.assertEqual(ps["split"]["roofs"], "layer")

        # reexport of one building keeps the mode
        rx = ws.split_export(self.pack, split=ps["split"], only=["bld_roof_a"], log=quiet)
        self.assertEqual(rx["roof_mode"], "per_scene")
        self.assertEqual([e["file"] for e in rx["files"] if e["layer"] == "roofs"], ["models/roofs.glb"])
        self.split("none")                                           # back to default; roof files gone
        self.assertFalse(os.path.exists(os.path.join(self.pack, "models", "roofs.glb")))


if __name__ == "__main__":
    unittest.main(verbosity=1)
