"""Tests for foundry_push.py with an in-memory fake of the bridge (mirrors the module's pipeline ops). Run: python illustrator/generators/test_foundry_push.py"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
from PIL import Image  # noqa: E402


class FakeBridge:
    """Same semantics as module 0.3.0: flag-keyed upserts, prune, flag-guarded delete."""
    def __init__(self, protocol=3, old=False):
        self.docs = {"Scene": {}, "Actor": {"a1": {"_id": "a1", "name": "Old Man", "img": "x.png", "prototypeToken": {"name": "Old Man", "texture": {"src": "x.png"}, "width": 1}}},
                     "Item": {}, "Folder": {}}
        self.emb = {}      # scene id -> {"Wall": {...}, ...}
        self.old, self.protocol, self.n = old, protocol, 0
        self.calls = []
        self.docs["Scene"]["s0"] = {"_id": "s0", "name": "Existing Scene", "width": 100, "height": 100, "grid": {"size": 100, "distance": 5, "units": "ft"},
                                    "levels": [{"_id": "L", "background": {"src": "old.webp"}}], "flags": {}, "walls": [], "tokens": [], "tiles": []}

    def nid(self):
        self.n += 1
        return f"id{self.n:014d}"

    def call(self, op, **a):
        self.calls.append(op)
        new_ops = {"version", "find_by_flag", "upsert_by_flag", "upsert_many", "delete", "set_scene_background", "set_scene_grid"}
        if self.old and op in new_ops:
            raise fp.PushError("bridge " + op + ": unknown op: " + op)
        return getattr(self, "op_" + op)(**a)

    def op_ping(self):
        return "pong"

    def op_world_info(self):
        return {"foundry": "14", "world": "w", "modules": [{"id": "varrenmoor-bridge", "version": "0.2.0" if self.old else "0.3.0"}]}

    def op_version(self):
        return {"module": "0.3.0", "protocol": self.protocol, "ops": []}

    def op_list(self, collection, **k):
        return [{"uuid": f"{collection}.{i}", "name": d["name"], "type": d.get("type")} for i, d in self.docs[collection].items()]

    def _doc(self, uuid):
        parts = uuid.split(".")
        d = self.docs[parts[0]][parts[1]]
        return d

    def op_get(self, uuid):
        d = json.loads(json.dumps(self._doc(uuid)))
        sid = d["_id"]
        for kind, key in (("Wall", "walls"), ("Drawing", "drawings"), ("Tile", "tiles"), ("Token", "tokens")):
            if uuid.startswith("Scene"):
                d[key] = list(self.emb.get(sid, {}).get(kind, {}).values())
        return d

    def _flagged(self, name, parent):
        if name in self.emb_kinds():
            sid = parent.split(".")[1]
            return self.emb.setdefault(sid, {}).setdefault(name, {})
        return self.docs[name]

    @staticmethod
    def emb_kinds():
        return ("Wall", "Drawing", "Tile", "Token")

    @staticmethod
    def _pid(d):
        return d.get("flags", {}).get("varrenmoor", {}).get("pipelineId")

    def _stamp(self, data, id):
        d = json.loads(json.dumps(data))
        d.setdefault("flags", {}).setdefault("varrenmoor", {})["pipelineId"] = id
        return d

    @staticmethod
    def _merge(a, b):
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                FakeBridge._merge(a[k], v)
            else:
                a[k] = v

    def op_find_by_flag(self, documentName, parentUuid=None, id=None, prefix=None):
        coll = self._flagged(documentName, parentUuid)
        return [{"uuid": f"{documentName}.{i}", "name": d.get("name"), "pipelineId": self._pid(d)} for i, d in coll.items()
                if self._pid(d) and (id is None or self._pid(d) == id) and (prefix is None or self._pid(d).startswith(prefix))]

    def op_upsert_by_flag(self, documentName, id, data, parentUuid=None):
        coll = self._flagged(documentName, parentUuid)
        for i, d in coll.items():
            if self._pid(d) == id:
                self._merge(d, self._stamp(data, id))
                return {"uuid": f"{documentName}.{i}", "created": False}
        i = self.nid()
        coll[i] = {"_id": i, **self._stamp(data, id)}
        return {"uuid": f"{documentName}.{i}", "created": True}

    def op_upsert_many(self, documentName, parentUuid, items, prefix=None, prune=False):
        coll = self._flagged(documentName, parentUuid)
        by = {self._pid(d): i for i, d in coll.items() if self._pid(d)}
        c = u = 0
        seen = set()
        for it in items:
            seen.add(it["id"])
            if it["id"] in by:
                self._merge(coll[by[it["id"]]], self._stamp(it["data"], it["id"]))
                u += 1
            else:
                i = self.nid()
                coll[i] = {"_id": i, **self._stamp(it["data"], it["id"])}
                c += 1
        dele = [i for p, i in by.items() if prune and prefix and p.startswith(prefix) and p not in seen]
        for i in dele:
            del coll[i]
        return {"created": c, "updated": u, "deleted": len(dele)}

    def op_update(self, uuid, data):
        d = self._doc(uuid)
        for k, v in data.items():
            if isinstance(v, dict) and isinstance(d.get(k), dict):
                self._merge(d[k], v)
            else:
                d[k] = v
        return {"uuid": uuid}

    def op_set_scene_background(self, uuid, src, **k):
        d = self._doc(uuid)
        d["levels"] = [{"_id": "L", "background": {"src": src}}]
        d.update({x: k[x] for x in ("width", "height") if k.get(x)})
        return {"uuid": uuid}

    def op_set_scene_grid(self, uuid, size, distance, units):
        self._doc(uuid)["grid"] = {"size": size, "distance": distance, "units": units}
        return {"uuid": uuid}

    def op_delete(self, uuid):
        kind, i = uuid.split(".")
        if not self._pid(self.docs[kind][i]):
            raise fp.PushError("refusing to delete a document without the pipeline flag")
        del self.docs[kind][i]
        return {"deleted": uuid}


def make_png(path, d=60):
    Image.new("RGB", (17 * d, 11 * d), (240, 230, 200)).save(path)


class PushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, "view.png")
        make_png(self.png)
        self.assets = os.path.join(self.tmp, "assets")

    def run_cmd(self, br, *args):
        import io
        from contextlib import redirect_stdout
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fp.main(list(args) + ["--assets-dir", self.assets], bridge=br)
        return json.loads(buf.getvalue().strip().splitlines()[-1]), code

    def push(self, br, *extra):
        return self.run_cmd(br, "push-scene", "--place", "bridgehollow", "--image", self.png, "--scene-name", "ZZ Illustrator Push Test", *extra)

    def test_calibration(self):
        _, v, cfg = fp.load_view("bridgehollow", "town")
        c = fp.calibrate(v, cfg, (1020, 660))
        self.assertEqual(c["grid_px"], 60)                    # 0.6 px/ft * 100 ft
        self.assertEqual((c["width"], c["height"]), (960, 600))
        x, y = fp.to_scene_px(c, v.x0 + 100, v.y0 + 50)
        self.assertAlmostEqual(x, 60.0)
        self.assertAlmostEqual(y, 30.0)
        with self.assertRaises(fp.PushError):
            fp.calibrate(v, cfg, (340, 220))                  # grid under 50 px

    def test_idempotent_push(self):
        br = FakeBridge()
        r1, _ = self.push(br, "--drawings", "roads,water")
        self.assertTrue(r1["ok"], r1)
        self.assertTrue(r1["created"])
        self.assertGreater(r1["walls"], 50)
        r2, _ = self.push(br, "--drawings", "roads,water")
        self.assertTrue(r2["ok"])
        self.assertFalse(r2["created"])
        self.assertEqual(r2["wall_ops"]["created"], 0)
        self.assertEqual(r2["wall_ops"]["updated"], r1["wall_ops"]["created"])
        self.assertEqual(r2["version"], r1["version"])      # identical image: no new file
        scenes = [d for d in br.docs["Scene"].values() if br._pid(d)]
        self.assertEqual(len(scenes), 1)
        sid = scenes[0]["_id"]
        self.assertEqual(len(br.emb[sid]["Wall"]), r1["walls"])
        self.assertEqual(scenes[0]["grid"]["size"], 60)
        self.assertTrue(scenes[0]["levels"][0]["background"]["src"].endswith("scene_zz_illustrator_push_test_v001.webp"))

    def test_new_image_bumps_version_and_prunes(self):
        br = FakeBridge()
        self.push(br)
        Image.new("RGB", (17 * 60, 11 * 60), (10, 10, 10)).save(self.png)
        r2, _ = self.push(br, "--scale", "50")                 # different scale: fewer buildings in view, stale walls pruned
        self.assertEqual(r2["version"], 2)
        self.assertGreater(r2["wall_ops"]["deleted"], 0)

    def test_existing_scene_needs_confirm_then_adopts(self):
        br = FakeBridge()
        r, code = self.run_cmd(br, "push-scene", "--place", "bridgehollow", "--image", self.png, "--scene-uuid", "Scene.s0")
        self.assertTrue(r["needs_confirm"])
        self.assertEqual(code, 0)
        self.assertEqual(br.docs["Scene"]["s0"]["levels"][0]["background"]["src"], "old.webp")    # untouched
        r, _ = self.run_cmd(br, "push-scene", "--place", "bridgehollow", "--image", self.png, "--scene-uuid", "Scene.s0", "--yes")
        self.assertTrue(r["ok"], r)
        self.assertEqual(br.docs["Scene"]["s0"]["name"], "Existing Scene")
        self.assertTrue(br._pid(br.docs["Scene"]["s0"]))

    def test_name_clash_with_foreign_scene(self):
        br = FakeBridge()
        r, code = self.run_cmd(br, "push-scene", "--place", "bridgehollow", "--image", self.png, "--scene-name", "existing scene")
        self.assertFalse(r["ok"])
        self.assertIn("not created by the pipeline", r["error"])

    def test_old_module_degrades(self):
        br = FakeBridge(old=True)
        r, code = self.push(br)
        self.assertFalse(r["ok"])
        self.assertTrue(r["needs_module"])
        self.assertIn("DEPLOY_MODULE.md", r["error"])
        st, _ = self.run_cmd(br, "status")
        self.assertTrue(st["connected"])
        self.assertFalse(st["pipeline_ops"])

    def test_dry_run_touches_nothing(self):
        br = FakeBridge(old=True)
        r, _ = self.push(br, "--dry-run")
        self.assertTrue(r["ok"])
        self.assertFalse(os.path.exists(self.assets))
        self.assertEqual(br.calls, [])

    def test_token_and_actor_update(self):
        br = FakeBridge()
        s, _ = self.push(br)
        r, _ = self.run_cmd(br, "push-token", "--scene-uuid", s["scene_uuid"], "--actor-uuid", "Actor.a1", "--at", "bld_gate_watch", "--place", "bridgehollow")
        self.assertTrue(r["ok"], r)
        r2, _ = self.run_cmd(br, "push-token", "--scene-uuid", s["scene_uuid"], "--actor-uuid", "Actor.a1", "--at", "bld_gate_watch", "--place", "bridgehollow")
        self.assertFalse(r2["created"])
        sid = s["scene_uuid"].split(".")[1]
        self.assertEqual(len(br.emb[sid]["Token"]), 1)
        r3, _ = self.run_cmd(br, "push-actor", "--actor-uuid", "Actor.a1", "--image", self.png, "--place", "bridgehollow")
        self.assertTrue(r3["needs_confirm"])
        r4, _ = self.run_cmd(br, "push-actor", "--actor-uuid", "Actor.a1", "--image", self.png, "--place", "bridgehollow", "--yes")
        self.assertTrue(r4["ok"])
        self.assertTrue(br.docs["Actor"]["a1"]["img"].startswith("assets/varrenmoor-3d/art/bridgehollow/actors/old_man_v001"))

    def test_scene_mode_flags(self):
        f = fp.scene_mode_flags("flat")["levels-3d-preview"]
        self.assertIs(f["auto3d"], False)
        g = fp.scene_mode_flags("3d", ["renderBackground=true", "tableColor=#000000", "sunPosition=45"])["levels-3d-preview"]
        self.assertIs(g["auto3d"], True)
        self.assertIs(g["renderBackground"], True)
        self.assertEqual((g["tableColor"], g["sunPosition"]), ("#000000", 45))
        with self.assertRaises(fp.PushError):
            fp.scene_mode_flags("2d")
        with self.assertRaises(fp.PushError):
            fp.scene_mode_flags("3d", ["nokey"])

    def test_push_scene_default_flat_and_existing_untouched(self):
        br = FakeBridge()
        r1, _ = self.push(br)
        self.assertEqual(r1["scene_mode"], "flat")
        sc = next(d for d in br.docs["Scene"].values() if br._pid(d))
        self.assertIs(sc["flags"]["levels-3d-preview"]["auto3d"], False)
        sc["flags"]["levels-3d-preview"]["auto3d"] = True        # user switched it on by hand: a re-push must not undo that
        r2, _ = self.push(br)
        self.assertNotIn("scene_mode", r2)
        self.assertIs(sc["flags"]["levels-3d-preview"]["auto3d"], True)
        r3, _ = self.push(br, "--scene-mode", "flat")             # explicit: applied
        self.assertIs(sc["flags"]["levels-3d-preview"]["auto3d"], False)

    def test_push_models_scene_mode(self):
        import tile_rotation_inspect as tri
        doc = tri.build()
        pl = os.path.join(tri.OUT, "placements.json")
        br = FakeBridge()
        r, _ = self.run_cmd(br, "push-models", "--placements", pl, "--scene-name", "ZZ Mode Test", "--set-name", "t")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["scene_mode"], "3d")
        sc = next(d for d in br.docs["Scene"].values() if br._pid(d))
        self.assertIs(sc["flags"]["levels-3d-preview"]["auto3d"], True)
        self.assertIs(sc["flags"]["levels-3d-preview"]["renderBackground"], False)

    def test_delete_only_pipeline(self):
        br = FakeBridge()
        s, _ = self.push(br)
        r, _ = self.run_cmd(br, "delete-scene", "--scene-uuid", s["scene_uuid"])
        self.assertTrue(r["ok"])
        r, _ = self.run_cmd(br, "delete-scene", "--scene-uuid", "Scene.s0")
        self.assertFalse(r["ok"])

    def test_bake_texture_offline(self):
        with tempfile.TemporaryDirectory() as t:
            img = os.path.join(t, "map.png")
            Image.new("RGB", (700, 500), (120, 160, 90)).save(img)        # page export: 50 px paper margin on each side
            br = FakeBridge()
            r, _ = self.run_cmd(br, "bake-texture", "--place", "p", "--image", img, "--crop-margin-pt", "30", "--dpi", "120", "--window", "100,200,400,400",
                                "--out-dir", os.path.join(t, "o"), "--name", "g")
            self.assertTrue(r["ok"], r)
            self.assertEqual(br.calls, [])                                   # no Foundry call at all
            self.assertEqual(r["size_px"], [600, 400])
            self.assertAlmostEqual(r["px_per_ft"], 2.0)
            self.assertEqual(r["footprint_ft"], [100.0, 200.0, 400.0, 400.0])
            fl = r["scene_flags"]["levels-3d-preview"]
            self.assertEqual((fl["renderTable"], fl["renderBackground"]), ("matcustom", False))
            self.assertTrue(fl["tableTex"].endswith("/g_v001.webp"))
            self.assertTrue(os.path.exists(r["image"]))
            self.assertTrue(os.path.exists(os.path.join(t, "o", "bake.json")))
            r2, _ = self.run_cmd(br, "bake-texture", "--place", "p", "--image", img, "--px-per-ft", "2", "--out-dir", os.path.join(t, "o"), "--name", "g")
            self.assertEqual(r2["size_px"], [700, 500])

    def test_push_models_table_texture(self):
        import tile_rotation_inspect as tri
        tri.build()
        pl = os.path.join(tri.OUT, "placements.json")
        br = FakeBridge()
        r, _ = self.run_cmd(br, "push-models", "--placements", pl, "--scene-name", "ZZ Tex Test", "--set-name", "t", "--table-texture", "assets/x/g_v001.webp")
        self.assertTrue(r["ok"], r)
        sc = next(d for d in br.docs["Scene"].values() if br._pid(d))
        f = sc["flags"]["levels-3d-preview"]
        self.assertEqual((f["tableTex"], f["renderTable"], f["renderBackground"]), ("assets/x/g_v001.webp", "matcustom", False))


if __name__ == "__main__":
    unittest.main()
