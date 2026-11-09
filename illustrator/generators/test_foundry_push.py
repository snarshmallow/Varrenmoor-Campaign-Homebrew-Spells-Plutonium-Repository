"""Tests for foundry_push.py with an in-memory fake of the bridge (mirrors the module's pipeline ops). Run: python illustrator/generators/test_foundry_push.py"""
import argparse
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
        return ("Wall", "Drawing", "Tile", "Token", "AmbientLight")

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
        parts = uuid.split(".")
        if len(parts) == 4:        # embedded document: Scene.<id>.Tile.<id>
            d = self.emb.get(parts[1], {}).get(parts[2], {})
            if not self._pid(d.get(parts[3], {})):
                raise fp.PushError("refusing to delete a document without the pipeline flag")
            del d[parts[3]]
            return {"deleted": uuid}
        kind, i = parts
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


def make_glb(path, positions=True, extensions_required=(), extensions_used=(), accessor_count=3, truncate=False):
    """Smallest GLB with one triangle (3 floats x 3 vertices) for the glb_check tests."""
    import struct
    bin_ = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    prim = {"attributes": {"POSITION": 0} if positions else {}}
    j = {"asset": {"version": "2.0"}, "buffers": [{"byteLength": len(bin_)}], "bufferViews": [{"buffer": 0, "byteLength": len(bin_)}],
         "accessors": [{"bufferView": 0, "componentType": 5126, "count": accessor_count, "type": "VEC3"}], "meshes": [{"primitives": [prim]}]}
    if extensions_required:
        j["extensionsRequired"] = list(extensions_required)
    if extensions_used or extensions_required:
        j["extensionsUsed"] = list(set(extensions_used) | set(extensions_required))
    js = json.dumps(j).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    body = struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(bin_), 0x004E4942) + bin_
    data = struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body
    with open(path, "wb") as f:
        f.write(data[: len(data) - 20] if truncate else data)
    return path


class GlbCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def p(self, n):
        return os.path.join(self.tmp, n)

    def test_plain_ok(self):
        import glb_check
        self.assertEqual(glb_check.validate_glb(make_glb(self.p("a.glb"))), [])

    def test_rejects_what_3d_canvas_cannot_load(self):
        import glb_check
        self.assertTrue(glb_check.validate_glb(make_glb(self.p("q.glb"), extensions_required=["KHR_mesh_quantization"])))
        self.assertEqual(glb_check.validate_glb(make_glb(self.p("q2.glb"), extensions_required=["KHR_mesh_quantization"]), allow_quantized=True), [])
        self.assertTrue(glb_check.validate_glb(make_glb(self.p("m.glb"), extensions_required=["EXT_meshopt_compression"])))
        self.assertTrue(glb_check.validate_glb(make_glb(self.p("n.glb"), positions=False)))
        self.assertTrue(glb_check.validate_glb(make_glb(self.p("z.glb"), accessor_count=0)))
        self.assertTrue(glb_check.validate_glb(make_glb(self.p("t.glb"), truncate=True)))
        with open(self.p("junk.glb"), "wb") as f:
            f.write(b"not a glb at all, but long enough to read a header")
        self.assertTrue(glb_check.validate_glb(self.p("junk.glb")))
        self.assertTrue(glb_check.validate_glb(self.p("missing.glb")))

    def test_verify_models_missing_unserved_and_ok(self):
        root = self.tmp
        d = os.path.join(root, "art", "p", "models", "s")
        os.makedirs(d)
        make_glb(os.path.join(d, "a_v001.glb"))
        good = "assets/varrenmoor-3d/art/p/models/s/a_v001.glb"
        gone = "assets/varrenmoor-3d/art/p/models/foliage_v002/c0_0_v001.glb"      # the 2026-11-08 failure: tile path with no file behind it
        self.assertEqual(fp.verify_models([good, "baileywiki-content/x.glb"], root), [])
        bad = fp.verify_models([good, gone], root)
        self.assertEqual(len(bad), 1)
        self.assertIn("not found", bad[0])
        size = os.path.getsize(os.path.join(d, "a_v001.glb"))
        self.assertEqual(fp.verify_models([good], root, "http://x", getter=lambda u: (200, size)), [])
        self.assertIn("HTTP 404", fp.verify_models([good], root, "http://x", getter=lambda u: (404, 0))[0])
        self.assertIn("bytes", fp.verify_models([good], root, "http://x", getter=lambda u: (200, size + 1))[0])


class Scene3DTests(unittest.TestCase):
    """push-scene-3d: order of the steps, idempotence, refusal to create tiles for unloadable models."""
    PLACE = "bridgehollow__dyers_walk_local"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.assets = os.path.join(self.tmp, "assets")
        import tile_rotation_inspect as tri
        tri.build()
        self.pl = os.path.join(tri.OUT, "placements.json")
        self.events = []
        self.br = FakeBridge()
        outer = self
        orig_call = self.br.call

        def call(op, **a):
            outer.events.append(("bridge", op))
            return orig_call(op, **a)
        self.br.call = call
        fp.PADDING_PUSH = lambda args: (outer.events.append(("padding", tuple(args))), 0)[1]

    def tearDown(self):
        fp.PADDING_PUSH = None

    run_cmd = PushTests.run_cmd

    def go(self, *extra):
        return self.run_cmd(self.br, "push-scene-3d", "--place", self.PLACE, "--scene-uuid", "Scene.s0", "--placements", self.pl, "--yes", *extra)

    def kinds(self):
        return [e[0] if e[0] == "padding" else e[1] for e in self.events]

    def test_order_flags_last_and_idempotent(self):
        r, code = self.go("--set-name", "t", "--scene-flag", "sunPosition=15.5")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["order"], ["geometry", "models", "padding", "flags", "verify"])
        self.assertEqual(r["steps"]["geometry"], {"padding": 0.25, "sceneX": 100, "sceneY": 100})   # 100 px scene, 100 px grid: padding rounds up to one square
        k = self.kinds()
        self.assertLess(k.index("upsert_many"), k.index("padding"))                          # models before padding
        last_update = len(k) - 1 - k[::-1].index("update")
        self.assertLess(k.index("padding"), last_update)                                       # skybox / lighting flags after padding
        self.assertNotIn("upsert_many", k[last_update:])                                       # nothing that could overwrite them afterwards
        f = self.br.docs["Scene"]["s0"]["flags"]["levels-3d-preview"]
        self.assertTrue(f["exr"].startswith("assets/varrenmoor-3d/art/%s/skybox/clear_day_v" % self.PLACE))
        self.assertEqual((f["skybox"], f["sunPosition"]), ("", 15.5))
        tiles1 = sorted(t["_id"] for t in self.br.emb["s0"]["Tile"].values())
        r2, _ = self.go("--set-name", "t", "--scene-flag", "sunPosition=15.5")
        self.assertTrue(r2["ok"], r2)
        self.assertEqual(tiles1, sorted(t["_id"] for t in self.br.emb["s0"]["Tile"].values()))      # no duplicates
        self.assertEqual(self.br.docs["Scene"]["s0"]["flags"]["levels-3d-preview"]["exr"], f["exr"])  # same skybox version reused

    def test_skybox_survives_a_flag_resetting_step(self):
        """A step that resets exr (what push-models --scene-mode 3d does) is undone by the final flag write."""
        fp.PADDING_PUSH = lambda args: (self.br.op_update("Scene.s0", {"flags": {"levels-3d-preview": {"exr": "assets/ossuary-exchange-skybox3.webp"}}}), 0)[1]
        r, _ = self.go("--set-name", "t")
        self.assertTrue(r["ok"], r)
        self.assertIn("clear_day", self.br.docs["Scene"]["s0"]["flags"]["levels-3d-preview"]["exr"])

    def test_unservable_model_fails_the_push(self):
        r, code = self.go("--set-name", "t", "--serve-url", "http://127.0.0.1:9")     # nothing answers there: reported, not a crash
        self.assertFalse(r["ok"])
        self.assertNotEqual(code, 0)

    def test_invalid_glb_creates_no_tiles(self):
        import glob
        r, _ = self.go("--set-name", "t")
        self.assertTrue(r["ok"], r)
        for g in glob.glob(os.path.join(self.assets, "art", "*", "models", "t", "**", "*.glb"), recursive=True):
            with open(g, "wb") as f:
                f.write(b"glTF-but-truncated")
        n = len(self.br.emb["s0"]["Tile"])
        # a changed source makes publish_glb write new versions (the broken ones are only reused when byte-identical), so break the source instead
        import json as _j
        src = _j.load(open(self.pl, encoding="utf-8"))
        base = os.path.dirname(self.pl)
        with open(os.path.join(base, src["files"][0]["file"]), "wb") as f:
            f.write(b"glTF-but-truncated")
        r2, code = self.go("--set-name", "t")
        self.assertFalse(r2["ok"])
        self.assertIn("model problem", r2["error"])
        self.assertEqual(n, len(self.br.emb["s0"]["Tile"]))


    def _seed_lights(self, n=3):
        self.br.emb.setdefault("s0", {}).setdefault("AmbientLight", {})
        for i in range(n):
            self.br.emb["s0"]["AmbientLight"][f"l{i}"] = {"_id": f"l{i}", "flags": {"varrenmoor": {"pipelineId": f"light:x:{i}"}}}
        self.br.emb["s0"]["AmbientLight"]["mine"] = {"_id": "mine", "flags": {}}

    def test_with_lights_zero_plan_keeps_existing_lights(self):
        """A layer set has no lights: --with-lights must fail early, write nothing and keep the scene's lights."""
        self._seed_lights()
        before = len(self.br.emb["s0"]["AmbientLight"])
        lp = os.path.join(self.tmp, "lighting.json")          # self-contained: world/<place>/panel_state.json is untracked and absent on a clean clone
        with open(lp, "w", encoding="utf-8") as f:
            json.dump({"lighting": {"sun": {"azimuth": 200, "altitude": 40}, "ambient": 0.4}}, f)
        r, code = self.go("--set-name", "t", "--with-lights", "--lighting", lp, "--lights-placements", self.pl)
        self.assertFalse(r["ok"], r)
        self.assertIn("0 lights", r["error"])
        self.assertEqual(before, len(self.br.emb["s0"]["AmbientLight"]))
        self.assertNotIn("upsert_many", self.kinds())          # failed before any write

    def test_push_lights_zero_plan_needs_explicit_prune(self):
        self._seed_lights()
        r, _ = self.run_cmd(self.br, "push-lights", "--place", self.PLACE, "--scene-uuid", "Scene.s0", "--placements", self.pl, "--lights-placements", self.pl)
        self.assertFalse(r["ok"], r)
        self.assertEqual(4, len(self.br.emb["s0"]["AmbientLight"]))
        r, _ = self.run_cmd(self.br, "push-lights", "--place", self.PLACE, "--scene-uuid", "Scene.s0", "--placements", self.pl, "--lights-placements", self.pl, "--prune-lights")
        self.assertTrue(r["ok"], r)
        self.assertEqual(["mine"], list(self.br.emb["s0"]["AmbientLight"]))      # only pipeline-flagged lights were removed

    def test_bad_lighting_name_fails_before_writes(self):
        r, _ = self.go("--set-name", "t", "--lighting", "no_such_place_zz")
        self.assertFalse(r["ok"])
        self.assertIn("lighting", r["error"])
        self.assertNotIn("upsert_many", self.kinds())

    def test_models_prune_empty_push_keeps_tiles(self):
        r, _ = self.go("--set-name", "t")
        n = len(self.br.emb["s0"]["Tile"])
        self.assertGreater(n, 0)
        self.br.emb["s0"]["Tile"]["foreign"] = {"_id": "foreign", "flags": {"varrenmoor": {"pipelineId": "model:otherplace:x"}}}
        r, _ = self.run_cmd(self.br, "push-models", "--place", self.PLACE, "--scene-uuid", "Scene.s0", "--placements", self.pl, "--yes", "--set-name", "t", "--prune")
        self.assertIn("foreign", self.br.emb["s0"]["Tile"])        # another place's pipeline tile survives --prune

    def test_dry_run_writes_nothing(self):
        r, _ = self.go("--set-name", "t", "--dry-run")
        self.assertTrue(r["ok"], r)
        self.assertNotIn("update", self.kinds())


class ScatterInstanceTilesTests(unittest.TestCase):
    """Regression: every instance tile of a shared scatter file (trees) used to list ALL ids of the file, so scene_audit.check_plan_unique saw each tree
    drawn by every tile and push-models refused with 'one source model must be drawn by one tile only'."""
    def test_instance_tiles_each_draw_only_their_own_id(self):
        import scene_audit as sa
        ids = [f"fol_trees_{i:04d}" for i in (1, 2, 3)]
        doc = {"place": "p", "frame": {"z_origin_ft": 0.0}, "files": [{
            "file": "models/foliage/oak.glb", "kind": "instances", "layer": "foliage", "ids": ids, "sha256": "x", "size_ft": [10, 10, 20],
            "tile": {"rotation": 0}, "instances": [{"id": i, "pivot_ft": [10.0 * n, 5.0, 0.0], "scale": 1.0, "rotation_deg": 0.0} for n, i in enumerate(ids)]}]}
        a = argparse.Namespace(layers=None, ids=None, lod=None, roofs_hidden=False)
        items = fp.build_model_tiles(doc, {"ppf": 1.0, "x0": 0.0, "y0": 0.0, "sceneX": 0, "sceneY": 0}, a, lambda e, rel: "assets/varrenmoor-3d/" + rel)
        self.assertEqual(3, len(items))
        for it, i in zip(items, ids):
            self.assertEqual([i], it["data"]["flags"]["varrenmoor"]["ids"])
        self.assertEqual([], sa.check_plan_unique(items))


class FoliageOnlyPruneTests(unittest.TestCase):
    def test_foliage_only_push_keeps_roof_tiles(self):
        import foundry_push as fp

        class Br:
            def call(self, *a, **k):
                raise AssertionError("a foliage-only push must not even read the scene")
        items = [{"id": "model:p:foliage_c0", "data": {"flags": {"varrenmoor": {"layer": "foliage"}}}}]
        self.assertEqual(fp.prune_stale_roofs(Br(), "Scene.x", items, argparse.Namespace()), 0)


class ClickMacroInstallTests(unittest.TestCase):
    def run_install(self, dry=False):
        import foundry_push as fp
        calls = []

        class Br:
            def call(self, op, **k):
                calls.append((op, k))
                return {"version": "9.9.9", "protocol": 99} if op == "version" else {"uuid": "Macro." + k.get("id", "x")}
        return fp.cmd_install_click_macros(Br(), argparse.Namespace(dry_run=dry)), calls

    def test_installs_click_and_roof_macros_by_stable_id(self):
        r, calls = self.run_install()
        ups = [k for op, k in calls if op == "upsert_by_flag"]
        self.assertEqual([k["id"] for k in ups], ["macro:click_mode", "macro:roofs_toggle_all", "macro:roofs_toggle_pick", "macro:shadow_quality"])
        for k in ups:
            self.assertEqual(k["documentName"], "Macro")
            self.assertEqual(k["data"]["type"], "script")
            self.assertTrue(k["data"]["command"].strip())
        self.assertIn("__vbClickMode", ups[0]["data"]["command"])
        r2, calls2 = self.run_install()                       # idempotent: same ids, same payload
        self.assertEqual([k for op, k in calls2 if op == "upsert_by_flag"], ups)
        self.assertFalse({op for op, _ in calls} - {"version", "upsert_by_flag"})

    def test_dry_run_writes_nothing(self):
        r, calls = self.run_install(dry=True)
        self.assertTrue(r["dry_run"]); self.assertEqual(calls, [])
        self.assertIn("macro:click_mode", r["macros"])


if __name__ == "__main__":
    unittest.main()
