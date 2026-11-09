"""Tests for foundry_sun.py (presets, set-sun, restore) and sun_preview.py. Run: python illustrator/generators/test_foundry_sun.py"""
import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import foundry_sun as fs  # noqa: E402
import foundry_lighting as fl  # noqa: E402


class Fake:
    def __init__(self, flags=None, tiles=None):
        self.scene = {"_id": "S", "name": "Test", "flags": {"levels-3d-preview": dict(flags or {"exposure": 1, "sunPosition": 15.34})}, "tiles": tiles or []}
        self.updates = []

    def call(self, op, **a):
        if op == "version":
            return {"module": "0.3.0", "protocol": 3, "ops": []}
        if op == "get":
            return copy.deepcopy(self.scene)
        if op == "update":
            self.updates.append(a)
            self.merge(self.scene, a["data"], a["uuid"])
            return {}
        raise AssertionError(op)

    def merge(self, scene, data, uuid):
        if ".Tile." in uuid:
            tid = uuid.split(".Tile.")[1]
            for t in scene["tiles"]:
                if t["_id"] == tid:
                    self.rec(t, data)
            return
        self.rec(scene, data)

    def rec(self, dst, src):
        for k, v in src.items():
            if k.startswith("-="):
                dst.pop(k[2:], None)
            elif isinstance(v, dict) and isinstance(dst.get(k), dict):
                self.rec(dst[k], v)
            else:
                dst[k] = copy.deepcopy(v)


def args(**kw):
    ns = fs.parser().parse_args(["set-sun", "--scene-uuid", "Scene.S"])
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class T(unittest.TestCase):
    def test_presets(self):
        ps = fs.load_presets()
        self.assertEqual(sorted(ps), sorted(["dawn", "morning", "noon", "afternoon", "dusk", "night", "foggy_morning", "warm_sunset"]))
        for p in ps.values():
            f = fs.preset_flags(p)
            self.assertEqual(f["timeSync"], "off")
            self.assertLessEqual(f["ambientLightIntensity"], 0.25)       # low ambient so the sun reads
            if "fogDistance" in f:
                self.assertGreaterEqual(f["fogDistance"], fs.FOG_MIN_FAR)

    def test_flags_sun(self):
        f = fs.preset_flags(fs.get_preset("afternoon"))
        self.assertEqual(f["sceneTint"], "#fff0cf")
        self.assertEqual(f["exposure"], 1.3)
        self.assertFalse(f["enableFog"])
        self.assertEqual(f["sunTilt"], fl.sun_to_3d(235, 38)["sunTilt"])

    def test_night_and_fog_presets(self):
        n, fg = fs.preset_flags(fs.get_preset("night")), fs.preset_flags(fs.get_preset("foggy_morning"))
        self.assertLess(n["exposure"], 0.6)
        self.assertEqual(fs.get_preset("night")["sky"]["preset"], "night")
        self.assertTrue(fg["enableFog"])
        self.assertLessEqual(fg["fogDistance"], 8000)
        self.assertTrue(fs.preset_flags(fs.get_preset("warm_sunset"))["enableFog"])
        self.assertLessEqual(fs.get_preset("warm_sunset")["sun"]["altitude"], 10)

    def test_overrides(self):
        p = fs.apply_overrides(fs.get_preset("noon"), args(sun_altitude=20.0, fog="on", fog_far=9000, ambient=0.3))
        f = fs.preset_flags(p)
        self.assertTrue(f["enableFog"])
        self.assertEqual(f["fogDistance"], 9000)
        self.assertEqual(f["ambientLightIntensity"], 0.3)
        self.assertEqual(fs.preset_flags(fs.apply_overrides(fs.get_preset("noon"), args(fog_far=100)))["fogDistance"], fs.FOG_MIN_FAR)

    def test_bad_preset(self):
        with self.assertRaises(fp.PushError):
            fs.cmd_set_sun(Fake(), args(preset="nope"))

    def test_dry_run_apply_idempotent_restore(self):
        f = Fake({"exposure": 1, "sunPosition": 15.34, "ambientLightIntensity": 0.35})
        r = fs.cmd_set_sun(f, args(preset="warm_sunset", sky="off"))
        self.assertTrue(r["ok"] and not r["applied"] and f.updates == [])
        self.assertIn("exposure", r["flag_changes"])
        self.assertIn("instruction", r["shadows"])
        before = copy.deepcopy(f.scene["flags"]["levels-3d-preview"])
        r = fs.cmd_set_sun(f, args(preset="warm_sunset", sky="off", apply=True))
        self.assertTrue(r["applied"])
        self.assertTrue(f.scene["flags"]["levels-3d-preview"]["enableFog"])
        self.assertIn("sunBackup", f.scene["flags"]["varrenmoor"])
        n_updates = len(f.updates)
        r = fs.cmd_set_sun(f, args(preset="warm_sunset", sky="off", apply=True))
        self.assertEqual(r["flag_changes"], {})
        self.assertEqual(len(f.updates), n_updates)
        r = fs.cmd_set_sun(f, args(restore=True, apply=True))
        self.assertTrue(r["applied"])
        self.assertEqual(f.scene["flags"]["levels-3d-preview"], before)
        self.assertNotIn("sunBackup", f.scene["flags"].get("varrenmoor", {}))

    def test_second_apply_keeps_first_backup(self):
        f = Fake({"exposure": 1})
        fs.cmd_set_sun(f, args(preset="dawn", sky="off", apply=True))
        fs.cmd_set_sun(f, args(preset="night", sky="off", apply=True))
        fs.cmd_set_sun(f, args(restore=True, apply=True))
        self.assertEqual(f.scene["flags"]["levels-3d-preview"], {"exposure": 1})

    def test_restore_without_backup(self):
        with self.assertRaises(fp.PushError):
            fs.cmd_set_sun(Fake(), args(restore=True))

    def test_ground_cast(self):
        tiles = [{"_id": "A", "flags": {"levels-3d-preview": {"model3d": "x/terrain_v001.glb"}}}, {"_id": "B", "flags": {"levels-3d-preview": {"model3d": "x/buildings_v001.glb"}}}]
        f = Fake(tiles=tiles)
        r = fs.cmd_set_sun(f, args(preset="noon", sky="off", ground_cast="off", apply=True))
        self.assertEqual(r["ground_tiles_to_change"], 1)
        self.assertFalse(f.scene["tiles"][0]["flags"]["levels-3d-preview"]["castShadow"])
        self.assertNotIn("castShadow", f.scene["tiles"][1]["flags"]["levels-3d-preview"])

    def test_routes_from_foundry_push(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = fp.main(["set-sun", "--scene-uuid", "Scene.S", "--preset", "dusk", "--sky", "off"], Fake())
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(buf.getvalue())["preset"], "dusk")

    def test_push_scene_3d_option_exists(self):
        self.assertEqual(fp.parser().parse_args(["push-scene-3d", "--sun-preset", "noon"]).sun_preset, "noon")


class Preview(unittest.TestCase):
    def test_preview_renders_and_low_sun_shades_more(self):
        import sun_preview as sp
        place = "bridgehollow__dyers_walk_local"
        if not os.path.exists(os.path.join(sp.REPO, "world", place, "export", "manifest.json")):
            self.skipTest("no pack")
        with tempfile.TemporaryDirectory() as t:
            lo = sp.render(place, fs.get_preset("noon"), os.path.join(t, "a.png"))
            hi = sp.render(place, fs.get_preset("warm_sunset"), os.path.join(t, "b.png"))
            self.assertGreater(os.path.getsize(os.path.join(t, "a.png")), 1000)
            self.assertEqual(lo["size"], [640, 400])
            self.assertGreater(hi["shadow_fraction"], lo["shadow_fraction"])


if __name__ == "__main__":
    unittest.main()
