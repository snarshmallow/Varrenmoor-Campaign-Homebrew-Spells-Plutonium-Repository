"""Tests for scene_audit.py and the stale-tile pruning of push-models / scene-audit, with mocked scene documents. Run: python illustrator/generators/test_scene_audit.py"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import scene_audit as sa  # noqa: E402
from test_foundry_push import FakeBridge, PushTests  # noqa: E402

PL = "p1"


def item(pid, ids, layer="buildings", x=100, y=100, elev=10.0, sha="a"):
    return {"id": pid, "data": {"x": x, "y": y, "width": 10, "height": 10, "elevation": elev,
                                "flags": {fp.FLAG: {"layer": layer, "ids": ids, "sha256": sha}}}}


def tile(uuid, pid, ids, layer="buildings", x=100, y=100, elev=10.0, sha="a", model="assets/varrenmoor-3d/art/p1/models/split/b/x_v001.glb"):
    return {"uuid": uuid, "x": x, "y": y, "width": 10, "elevation": elev,
            "flags": {fp.FLAG: {"pipelineId": pid, "layer": layer, "ids": ids, "sha256": sha}, fp.L3D: {"model3d": model}}}


def houses(n):
    return [f"bld_house_{i:03d}" for i in range(n)]


class AuditTests(unittest.TestCase):
    def merged_plan(self):
        return [item(f"model:{PL}:buildings", houses(8) + ["bld_house_001_roof", "bld_house_002_int_f0"]), item(f"model:{PL}:terrain", ["terrain_p1"], "terrain")]

    def scene_with_individuals(self, n=8):
        tiles = [tile(f"T.b{i}", f"model:{PL}:buildings_{h}", [h]) for i, h in enumerate(houses(n))]
        tiles += [tile("T.m", f"model:{PL}:buildings", houses(n)), tile("T.t", f"model:{PL}:terrain", ["terrain_p1"], "terrain"),
                  tile("T.pad", f"model:{PL}:padding_apron", [], None), tile("T.mine", None, []), tile("T.other", "model:other:x", ["x"])]
        return {"uuid": "Scene.s", "tiles": tiles}

    def test_building_parts_are_one_source(self):
        self.assertEqual(sa.src("bld_house_041_int_f0"), "bld_house_041")
        self.assertEqual(sa.src("bld_house_041_roof"), "bld_house_041")
        self.assertEqual(sa.src("str_008"), "str_008")

    def test_individuals_next_to_merged_layer_are_superseded(self):
        st = sa.stale_tiles(self.scene_with_individuals(), self.merged_plan(), PL)
        self.assertEqual(sorted(p for _, p, _ in st), sorted(f"model:{PL}:buildings_{h}" for h in houses(8)))
        self.assertTrue(all(r == "superseded" for _, _, r in st))

    def test_merged_next_to_individual_plan_is_superseded(self):
        plan = [item(f"model:{PL}:buildings_{h}", [h]) for h in houses(8)]
        sc = {"uuid": "Scene.s", "tiles": [tile("T.m", f"model:{PL}:buildings", houses(8))]}
        self.assertEqual([(p, r) for _, p, r in sa.stale_tiles(sc, plan, PL)], [(f"model:{PL}:buildings", "superseded")])

    def test_only_our_tiles_of_the_plan_layers_are_ever_stale(self):
        st = {p for _, p, _ in sa.stale_tiles(self.scene_with_individuals(), self.merged_plan(), PL)}
        for keep in (f"model:{PL}:padding_apron", "model:other:x", f"model:{PL}:terrain", f"model:{PL}:buildings", None):
            self.assertNotIn(keep, st)

    def test_orphan_in_a_plan_layer(self):
        sc = {"uuid": "Scene.s", "tiles": [tile("T.gone", f"model:{PL}:buildings_bld_house_099", ["bld_house_099"]), tile("T.f", f"model:{PL}:foliage_c0", ["oak"], "foliage")]}
        self.assertEqual([(p, r) for _, p, r in sa.stale_tiles(sc, [item(f"model:{PL}:buildings_bld_house_001", ["bld_house_001"])], PL)],
                         [(f"model:{PL}:buildings_bld_house_099", "not-in-plan")])

    def test_plan_with_two_representations_is_refused(self):
        bad = self.merged_plan() + [item(f"model:{PL}:buildings_bld_house_001", ["bld_house_001"])]
        self.assertTrue(sa.check_plan_unique(bad))
        self.assertFalse(sa.check_plan_unique(self.merged_plan()))

    def test_representation_summary(self):
        r = sa.representation(self.merged_plan())
        self.assertEqual(r["buildings"]["representation"], "merged")
        self.assertEqual(r["buildings"]["sources"], 8)
        self.assertEqual(sa.representation([item("a", ["bld_house_001"]), item("b", ["bld_house_002"])])["buildings"]["representation"], "individual")

    def test_audit_moved_elevation_sha_version_duplicates(self):
        plan = [item(f"model:{PL}:b1", ["bld_house_001"], x=300, y=400), item(f"model:{PL}:b2", ["bld_house_002"], elev=12.0), item(f"model:{PL}:b3", ["bld_house_003"], sha="new"),
                item(f"model:{PL}:b4", ["bld_house_004"]), item(f"model:{PL}:b5", ["bld_house_005"])]
        sc = {"uuid": "Scene.s", "tiles": [tile("T1", f"model:{PL}:b1", ["bld_house_001"]), tile("T2", f"model:{PL}:b2", ["bld_house_002"]), tile("T3", f"model:{PL}:b3", ["bld_house_003"]),
                                          tile("T4", f"model:{PL}:b4", ["bld_house_004"]), tile("T4b", f"model:{PL}:b4", ["bld_house_004"])]}
        r = sa.audit(sc, plan, PL, local_newest=lambda m: 3)
        kinds = {(f["kind"], f["tile"][-2:]) for f in r["findings"]}
        self.assertTrue({("moved", "b1"), ("elevation", "b2"), ("model_changed", "b3"), ("old_version", "b4"), ("duplicate_id", "b4"), ("missing", "b5")} <= kinds, kinds)
        self.assertEqual([d[0] for d in r["delete"]], ["T4b"])
        self.assertIn("T1", r["repush"])
        self.assertFalse(r["ok"])

    def test_clean_scene(self):
        plan = [item(f"model:{PL}:b1", ["bld_house_001"])]
        r = sa.audit({"uuid": "Scene.s", "tiles": [tile("T1", f"model:{PL}:b1", ["bld_house_001"])]}, plan, PL)
        self.assertTrue(r["ok"], r)
        self.assertEqual(sa.repair_plan(r, "Scene.s", ""), ["scene is clean: nothing to repair"])

    def test_repair_plan_lists_deletes(self):
        r = sa.audit(self.scene_with_individuals(), self.merged_plan(), PL)
        txt = "\n".join(sa.repair_plan(r, "Scene.s", "--placements x"))
        self.assertIn("DELETE 8 tile(s)", txt)
        self.assertIn("buildings_bld_house_003", txt)


class PushPruneTests(unittest.TestCase):
    """push-models / push-scene-3d against the fake bridge: the other representation is replaced, nothing else is."""

    def setUp(self):
        import tile_rotation_inspect as tri
        tri.build()
        self.pl = os.path.join(tri.OUT, "placements.json")
        self.tmp = tempfile.mkdtemp()
        self.assets = os.path.join(self.tmp, "assets")
        self.br = FakeBridge()
        self.run = lambda *a: PushTests.run_cmd(self, self.br, *a)
        self.place = json.load(open(self.pl))["place"]

    def seed(self, n, ids=("rot000",)):
        t = self.br.emb.setdefault("s0", {}).setdefault("Tile", {})
        for i in range(n):
            t[f"old{i}"] = {"_id": f"old{i}", "flags": {"varrenmoor": {"pipelineId": f"model:{self.place}:old_{i}", "layer": "inspect", "ids": list(ids) if i == 0 else [f"gone{i}"]}}}
        t["pad"] = {"_id": "pad", "flags": {"varrenmoor": {"pipelineId": f"model:{self.place}:padding_apron"}}}
        t["foreign"] = {"_id": "foreign", "flags": {"varrenmoor": {"pipelineId": "model:otherplace:x", "layer": "inspect", "ids": ["rot000"]}}}
        t["mine"] = {"_id": "mine", "flags": {}}

    def go(self, *extra):
        return self.run("push-models", "--place", "x", "--scene-uuid", "Scene.s0", "--placements", self.pl, "--yes", "--set-name", "t", *extra)

    def tiles(self):
        return set(self.br.emb["s0"]["Tile"])

    def test_dry_run_lists_stale_and_writes_nothing(self):
        self.seed(3)
        r, _ = self.go("--dry-run")
        self.assertTrue(r["ok"], r)
        self.assertEqual(sorted(x["pipelineId"][-5:] for x in r["stale_tiles"]), ["old_0", "old_1", "old_2"])
        self.assertEqual({x["reason"] for x in r["stale_tiles"] if x["pipelineId"].endswith("old_0")}, {"superseded"})
        self.assertEqual(r["representation"]["inspect"]["representation"], "individual")
        self.assertEqual(self.tiles(), {"old0", "old1", "old2", "pad", "foreign", "mine"})

    def test_superseded_is_removed_without_prune_others_kept(self):
        self.seed(3)
        r, _ = self.go()
        self.assertTrue(r["ok"], r)
        t = self.tiles()
        self.assertNotIn("old0", t)                                   # draws rot000, which the plan now draws itself
        self.assertTrue({"old1", "old2", "pad", "foreign", "mine"} <= t)    # merely absent from the plan: kept without --prune

    def test_prune_removes_absent_tiles_of_the_plan_layer_only(self):
        self.seed(3)
        r, _ = self.go("--prune")
        t = self.tiles()
        self.assertFalse({"old0", "old1", "old2"} & t)
        self.assertTrue({"pad", "foreign", "mine"} <= t)               # padding apron, another place, a hand-made tile

    def test_many_stale_tiles_refused_without_prune(self):
        self.seed(sa.PRUNE_LIMIT + 2)
        r, _ = self.go()
        self.assertFalse(r["ok"])
        self.assertIn("--prune", r["error"])
        self.assertNotIn("upsert_many", [c for c in self.br.calls])
        r, _ = self.go("--prune")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.tiles() & {f"old{i}" for i in range(sa.PRUNE_LIMIT + 2)}, set())

    def test_partial_push_never_removes_absent_tiles(self):
        self.seed(3)
        r, _ = self.go("--prune", "--ids", "rot000")
        self.assertTrue({"old1", "old2"} <= self.tiles())

    def test_scene_audit_command_is_read_only(self):
        self.seed(2)
        self.br.calls.clear()
        r, _ = self.run("scene-audit", "--place", "x", "--scene-uuid", "Scene.s0", "--placements", self.pl)
        self.assertTrue(r["ok"], r)
        self.assertFalse(r["clean"])
        self.assertEqual(set(self.br.calls), {"get"})
        self.assertEqual([d["pipelineId"][-5:] for d in r["delete"]], ["old_0", "old_1"])
        self.assertEqual(len(r["missing"]), 6)


if __name__ == "__main__":
    unittest.main()
