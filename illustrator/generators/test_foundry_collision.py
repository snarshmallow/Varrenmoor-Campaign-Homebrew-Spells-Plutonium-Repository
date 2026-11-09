"""Tests for foundry_collision.py (collision per layer, set-collision, push-walls). Run: python illustrator/generators/test_foundry_collision.py"""
import argparse
import json
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_collision as fc  # noqa: E402
import foundry_push as fp  # noqa: E402

CAL = {"x0": 0.0, "y0": 0.0, "ppf": 2.0, "sceneX": 100, "sceneY": 50, "place": "t"}


class Fake:
    """Minimal bridge: one scene with tiles/walls, update with dotted flag keys, upsert_many with prune."""
    def __init__(self, tiles=(), walls=()):
        self.scene = {"_id": "S", "flags": {"varrenmoor": {"calib": CAL}}, "tiles": [dict(t) for t in tiles], "walls": [dict(w) for w in walls]}
        self.writes = []

    def call(self, op, **a):
        return getattr(self, "op_" + op)(**a)

    def op_world_info(self):
        return {"foundry": "14", "world": "w", "modules": [{"id": "varrenmoor-bridge", "version": "0.3.0"}]}

    def op_version(self):
        return {"module": "0.3.0", "protocol": 3, "ops": []}

    def op_get(self, uuid):
        return json.loads(json.dumps(self.scene))

    def op_update(self, uuid, data):
        self.writes.append((uuid, data))
        t = next(t for t in self.scene["tiles"] if uuid.endswith(t["_id"]))
        for k, v in data.items():
            cur = t
            parts = k.split(".")
            for p in parts[:-1]:
                cur = cur.setdefault(p, {})
            cur[parts[-1]] = v
        return {"uuid": uuid}

    def op_upsert_many(self, documentName, parentUuid, items, prefix=None, prune=False):
        have = {w["flags"]["varrenmoor"]["pipelineId"]: w for w in self.scene["walls"]}
        c = u = 0
        for it in items:
            w = {"_id": it["id"], **it["data"], "flags": {"varrenmoor": {**(it["data"].get("flags") or {}).get("varrenmoor", {}), "pipelineId": it["id"]}}}
            if it["id"] in have:
                have[it["id"]].update(w)
                u += 1
            else:
                self.scene["walls"].append(w)
                c += 1
        keep = {i["id"] for i in items}
        before = len(self.scene["walls"])
        if prune:
            self.scene["walls"] = [w for w in self.scene["walls"] if not (w["flags"]["varrenmoor"]["pipelineId"].startswith(prefix) and w["flags"]["varrenmoor"]["pipelineId"] not in keep)]
        return {"created": c, "updated": u, "deleted": before - len(self.scene["walls"])}


def tile(i, layer, coll=False, pid=None):
    return {"_id": i, "flags": {"varrenmoor": {"pipelineId": pid or f"model:t:{i}", "layer": layer}, "levels-3d-preview": {"collision": coll}}}


def run(br, *argv):
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fp.main(list(argv), bridge=br)
    return json.loads(buf.getvalue().strip().splitlines()[-1]), code


class CollisionPolicy(unittest.TestCase):
    def test_default_and_specs(self):
        d = fc.parse_collision(None)
        self.assertTrue({"buildings", "roads", "bridges", "plazas", "walls", "fences", "props", "terrain"} <= d)
        self.assertFalse({"foliage", "water", "roofs"} & d)
        self.assertEqual(fc.parse_collision("all"), set(fc.COLLISION_LAYERS))
        self.assertEqual(fc.parse_collision("none"), set())
        self.assertEqual(fc.parse_collision("roads,terrain"), {"roads", "terrain"})
        self.assertEqual(fc.parse_collision("+water,-terrain"), (d | {"water"}) - {"terrain"})
        with self.assertRaises(ValueError):
            fc.parse_collision("buildingz")
        self.assertEqual(fc.parse_lod("terrain=0.5"), {"terrain": 0.5})

    def test_collision_for_mixed(self):
        on = fc.parse_collision(None)
        self.assertTrue(fc.collision_for(["buildings"], on))
        self.assertFalse(fc.collision_for(["buildings", "roofs"], on))
        self.assertFalse(fc.collision_for([], on))

    def test_build_model_tiles_flags(self):
        def entry(layer, n):
            return {"id": f"model:t:{n}", "file": f"models/{n}.glb", "sha256": "x", "kind": "mesh", "layer": layer, "layers": [layer], "ids": [n],
                    "size_ft": [10, 10, 10], "pivot": {"x_ft": 5, "y_ft": 5, "rel_z_ft": 0}, "tile": {"rotation": 0}}
        doc = {"place": "t", "frame": {"z_origin_ft": 0}, "files": [entry(l, l) for l in ("terrain", "buildings", "foliage", "water", "roofs", "roads")]}
        c = {"ppf": 1.0, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0}
        a = argparse.Namespace(layers=None, ids=None, lod=0, roofs_hidden=False, collision=None, collision_lod="terrain=0.5")
        items = {i["id"].split(":")[-1]: i["data"]["flags"]["levels-3d-preview"] for i in fp.build_model_tiles(doc, c, a, None)}
        self.assertEqual({k: v["collision"] for k, v in items.items()}, {"terrain": True, "buildings": True, "roads": True, "foliage": False, "water": False, "roofs": False})
        self.assertEqual(items["terrain"]["sightMeshComplexity"], 0.5)
        self.assertNotIn("sightMeshComplexity", items["buildings"])
        self.assertEqual({k: v["sight"] for k, v in items.items()}, {"terrain": False, "buildings": True, "roads": False, "foliage": True, "water": False, "roofs": False})   # sight: buildings, walls, foliage
        a.sight = "none"
        self.assertTrue(all(i["data"]["flags"]["levels-3d-preview"]["sight"] is False for i in fp.build_model_tiles(doc, c, a, None)))
        a.sight = "+roofs"
        self.assertTrue(next(i for i in fp.build_model_tiles(doc, c, a, None) if "roofs" in i["id"])["data"]["flags"]["levels-3d-preview"]["sight"])
        a.sight, a.collision = None, "+water"
        self.assertTrue(next(i for i in fp.build_model_tiles(doc, c, a, None) if "water" in i["id"])["data"]["flags"]["levels-3d-preview"]["collision"])


class SetCollision(unittest.TestCase):
    def setUp(self):
        self.br = Fake([tile("a", "buildings", False), tile("b", "terrain", False), tile("c", "foliage", True), tile("d", "roofs", False), tile("e", "mixed", False),
                        {"_id": "z", "flags": {}}])

    def test_dry_run_writes_nothing_then_apply_idempotent(self):
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--sight", "keep")
        self.assertTrue(r["ok"] and not r["applied"])
        self.assertEqual(r["changes"], 3)                      # buildings on, terrain on, foliage off; roofs already right; mixed skipped; foreign tile ignored
        self.assertEqual(r["skipped"], ["model:t:e"])
        self.assertEqual(self.br.writes, [])
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--sight", "keep", "--apply")
        self.assertTrue(r["applied"])
        self.assertEqual(len(self.br.writes), 3)
        self.assertTrue(all(list(d)[0] == "flags.levels-3d-preview.collision" for _, d in self.br.writes))
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--sight", "keep", "--apply")
        self.assertEqual((r["changes"], r["unchanged"]), (0, 5 - 1))
        self.assertEqual(len(self.br.writes), 3)               # second run wrote nothing

    def test_sight_defaults_written_and_idempotent(self):
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--apply")
        self.assertEqual(r["sight_on"], ["buildings", "foliage", "walls"])
        got = {t["_id"]: t["flags"]["levels-3d-preview"]["sight"] for t in self.br.scene["tiles"] if t["_id"] in "abcd"}
        self.assertEqual(got, {"a": True, "b": False, "c": True, "d": False})         # buildings, foliage on; terrain, roofs off
        n = len(self.br.writes)
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--apply")
        self.assertEqual((r["changes"], len(self.br.writes)), (0, n))
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--sight", "none", "--apply")
        self.assertEqual(r["changes"], 2)
        self.assertFalse(any(t["flags"]["levels-3d-preview"].get("sight") for t in self.br.scene["tiles"] if t["_id"] in "abcd"))

    def test_custom_layers_and_lod(self):
        r, _ = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--collision", "all", "--collision-lod", "terrain=0.4", "--apply")
        got = {t["_id"]: t["flags"]["levels-3d-preview"]["collision"] for t in self.br.scene["tiles"] if t["_id"] in "abcd"}
        self.assertEqual(got, {"a": True, "b": True, "c": True, "d": True})
        self.assertEqual(self.br.scene["tiles"][1]["flags"]["levels-3d-preview"]["sightMeshComplexity"], 0.4)

    def test_bad_layer(self):
        r, code = run(self.br, "set-collision", "--scene-uuid", "Scene.S", "--collision", "nope")
        self.assertFalse(r["ok"])


class Geometry(unittest.TestCase):
    def test_simplify_merges_collinear(self):
        ring = [(0, 0), (4, 0), (8, 0), (10, 0), (10, 5), (10, 10), (0, 10), (0, 5)]
        self.assertEqual(len(fc.simplify_ring(ring, 0.3)), 4)

    def test_tree_stands(self):
        stand = [(100 + 12 * (i % 4), 100 + 12 * (i // 4)) for i in range(12)]
        lone = [(900, 900), (905, 900)]
        rings = fc.tree_rings(stand + lone)
        self.assertEqual(len(rings), 1)                      # one stand, two stray trees give no wall
        self.assertLessEqual(len(rings[0]), fc.MAX_RING_PTS)
        xs = [p[0] for p in rings[0]]
        self.assertLess(min(xs), 100)                         # grown past the outer trees

    def test_ring_with_door(self):
        plan = fc.Plan(CAL)
        pts = [(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)]
        plan.ring("buildings", "b1", pts, fc.WALL_PROFILES["buildings"], [{"id": "b1_door", "point": [10.0, 0.4], "width_ft": 4.0}])
        doors = [i for i in plan.items if i["data"]["door"]]
        self.assertEqual(len(doors), 1)
        self.assertEqual(doors[0]["data"]["flags"]["varrenmoor"]["doorId"], "b1_door")
        self.assertEqual(doors[0]["data"]["ds"], 0)
        self.assertEqual(len(plan.items), 6)                  # top edge split in 3, three more edges
        d = doors[0]["data"]["c"]
        self.assertAlmostEqual(math.dist(d[:2], d[2:]), 4.0 * CAL["ppf"], 1)
        self.assertAlmostEqual(d[1], 50.0)                    # scene px: sceneY + y * ppf


class PushWalls(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        base = os.path.join(self.root, "world", "t", "export", "entities")
        os.makedirs(base)
        wr = lambda n, items: json.dump({"items": items}, open(os.path.join(base, n + ".json"), "w"))  # noqa: E731
        wr("buildings", [{"id": "bld_1", "polygon": [[10, 10], [30, 10], [30, 25], [10, 25]], "doors": [{"id": "bld_1_door1", "kind": "exterior", "point": [20, 10], "width_ft": 3.5},
                                                                                                           {"id": "bld_1_i1", "kind": "interior", "point": [20, 17], "width_ft": 3}]}])
        wr("fences", [{"id": "fnc_1", "closed": False, "points": [[0, 0, 5], [10, 0, 5], [20, 0, 5], [20, 30, 5]]}])
        wr("water", [{"id": "wat_1", "polygon": [[50, 0], [60, 0], [60, 100], [50, 100]]}])
        json.dump({"items": [{"id": f"t{i}", "x": 100 + 10 * (i % 3), "y": 100 + 10 * (i // 3)} for i in range(9)]}, open(os.path.join(self.root, "world", "t", "foliage.json"), "w"))
        self._repo = fp.REPO
        fp.REPO = self.root

    def tearDown(self):
        fp.REPO = self._repo

    def test_plan_layers_and_profiles(self):
        items, counts = fc.build_walls(os.path.join(self.root, "world", "t"), CAL, fc.WALL_LAYERS)
        self.assertEqual(counts["buildings"], 6)              # 4 edges, one split by the exterior door; the interior door is ignored
        self.assertEqual(counts["fences"], 2)                 # collinear fence points merged
        self.assertEqual(counts["trees"], 4)
        self.assertEqual(counts["water"], 4)
        by = {i["id"].split(":")[1]: i["data"] for i in items}
        self.assertEqual((by["trees"]["move"], by["trees"]["sight"], by["trees"]["sound"], by["trees"]["light"]), (0, 10, 10, 0))
        self.assertEqual((by["buildings"]["move"], by["buildings"]["sight"], by["buildings"]["light"], by["buildings"]["sound"]), (20, 20, 20, 20))
        self.assertEqual((by["fences"]["move"], by["fences"]["sight"]), (20, 0))
        self.assertEqual((by["water"]["sight"], by["water"]["sound"]), (0, 10))
        items2, _ = fc.build_walls(os.path.join(self.root, "world", "t"), CAL, ["water"], fc.parse_profiles(["water:sight=10"]))
        self.assertEqual(items2[0]["data"]["sight"], 10)
        self.assertEqual(len({i["id"] for i in items}), len(items))     # ids unique

    def test_command_dry_run_apply_prune_idempotent(self):
        br = Fake()
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S")
        self.assertTrue(r["ok"] and not r["applied"] and r["walls"] == 6 and r["doors"] == 1 and r["layers"] == ["buildings", "walls"])      # fallback default: buildings + town walls only, no trees/water/fences
        self.assertEqual(br.scene["walls"], [])
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S", "--wall-layers", "buildings,walls,fences,trees,water", "--apply")
        self.assertEqual(r["wall_ops"]["created"], 16)
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S", "--wall-layers", "buildings,walls,fences,trees,water", "--apply")
        self.assertEqual((r["wall_ops"]["created"], r["wall_ops"]["updated"], r["wall_ops"]["deleted"]), (0, 16, 0))
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S", "--apply")
        self.assertEqual((r["wall_ops"]["deleted"], len(br.scene["walls"])), (10, 6))       # layers not named are pruned
        # 2D push-scene walls (prefix wall:) are never touched
        br.scene["walls"].append({"_id": "w", "flags": {"varrenmoor": {"pipelineId": "wall:bld_x:0"}}})
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S", "--wall-layers", "none", "--apply")
        self.assertEqual([w["_id"] for w in br.scene["walls"]], ["w"])

    def test_needs_calibration(self):
        br = Fake()
        br.scene["flags"] = {}
        r, _ = run(br, "push-walls", "--scene-uuid", "Scene.S")
        self.assertFalse(r["ok"])


class DoorSync(unittest.TestCase):
    def scene(self):
        return Fake([{"_id": "T", "flags": {"varrenmoor": {"pipelineId": "model:t:b", "layer": "buildings", "ids": ["bld_1", "bld_2"]},
                                            "levels-3d-preview": {"collision": True, "modelDoors": {"bld_1_door1": {"ds": "1"}}}}}],
                    [{"_id": "W1", "door": 1, "ds": 0, "flags": {"varrenmoor": {"pipelineId": "wall3d:buildings:bld_1:1", "doorId": "bld_1_door1"}}},
                     {"_id": "W2", "door": 1, "ds": 1, "flags": {"varrenmoor": {"pipelineId": "wall3d:buildings:bld_2:1", "doorId": "bld_2_door1"}}},
                     {"_id": "W3", "door": 1, "ds": 0, "flags": {"varrenmoor": {"pipelineId": "wall3d:buildings:bld_3:1", "doorId": "bld_3_door1"}}},
                     {"_id": "W4", "door": 0, "ds": 0, "flags": {"varrenmoor": {"pipelineId": "wall3d:buildings:bld_1:0"}}}])

    def test_plan_model_wins_and_unknown_open_wall_opens_model(self):
        plan = fc.door_plan(self.scene().scene)
        self.assertEqual([(k, i, t) for k, i, d, t, w in plan], [("wall", "W1", 1), ("tile", "T", "1")])
        self.assertEqual(plan[1][2], "bld_2_door1")

    def test_command_dry_then_apply(self):
        br = Fake()
        br.scene = self.scene().scene
        br.op_update = lambda uuid, data: br.writes.append((uuid, data))
        r, _ = run(br, "sync-doors", "--scene-uuid", "Scene.S")
        self.assertTrue(r["ok"] and not r["applied"] and r["changes"] == 2 and br.writes == [])
        r, _ = run(br, "sync-doors", "--scene-uuid", "Scene.S", "--apply")
        self.assertEqual(br.writes, [("Scene.S.Wall.W1", {"ds": 1}), ("Scene.S.Tile.T", {"flags.levels-3d-preview.modelDoors.bld_2_door1.ds": "1"})])

    def test_install_macro_idempotent(self):
        calls = []
        class B:
            def call(self, op, **k):
                calls.append((op, k))
                return {"module": "0.3.0", "protocol": 3} if op == "version" else {"uuid": "Macro.m"}
        r, _ = run(B(), "install-door-sync")
        up = [k for op, k in calls if op == "upsert_by_flag"][0]
        self.assertTrue(r["ok"] and up["id"] == "macro:door_sync" and "__vbDoorSync" in up["data"]["command"])


if __name__ == "__main__":
    unittest.main()
