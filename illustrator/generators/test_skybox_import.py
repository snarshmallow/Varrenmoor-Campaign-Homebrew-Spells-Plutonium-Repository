"""Import a sky from an existing Foundry scene (mocked scene document, no Foundry, no network). Run: python illustrator/generators/test_skybox_import.py"""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skybox as sb  # noqa: E402
from PIL import Image  # noqa: E402

SCENE = {"_id": "abc123", "name": "Ossuary Exchange", "flags": {"levels-3d-preview": {
    "exr": "assets/ossuary-exchange-skybox3.webp", "skybox": "", "sunPosition": 9, "timeSync": "darkness", "ambientLightIntensity": 0.2,
    "tableColor": "#341f0f", "renderTable": "matcustom"}}}


class ImportSky(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vbsky-")
        self.src = os.path.join(self.tmp, "src.webp")
        Image.new("RGB", (64, 32), (40, 90, 160)).save(self.src, "WEBP")
        self.asked = []

    def resolver(self, src, dest):
        self.asked.append(src)
        return self.src, "mock"

    def test_import_copies_image_and_flags(self):
        r = sb.import_scene_sky(SCENE, "Scene.abc123", "p", world_root=self.tmp, resolver=self.resolver)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.asked, ["assets/ossuary-exchange-skybox3.webp"])
        self.assertEqual(r["name"], "imported_ossuary_exchange")
        d = os.path.join(self.tmp, "p", "export", "skybox")
        for f in ("imported_ossuary_exchange.webp", "imported_ossuary_exchange_preview.png", "imported_ossuary_exchange.json"):
            self.assertTrue(os.path.exists(os.path.join(d, f)), f)
        self.assertEqual(Image.open(os.path.join(d, "imported_ossuary_exchange_preview.png")).size, (1024, 512))
        meta = json.load(open(os.path.join(d, "imported_ossuary_exchange.json")))
        self.assertEqual(meta["source"]["scene_uuid"], "Scene.abc123")
        self.assertEqual(meta["lighting_flags"], {"sunPosition": 9, "timeSync": "darkness", "ambientLightIntensity": 0.2})   # only light keys, not tableColor etc.
        self.assertFalse(r["warnings"])

    def test_listed_after_import(self):
        sb.import_scene_sky(SCENE, "Scene.abc123", "p", name="Night Sky", world_root=self.tmp, resolver=self.resolver)
        _, rows = sb.list_skies("p", self.tmp)
        names = [x["name"] for x in rows]
        self.assertEqual(names[:len(sb.PRESETS)], list(sb.PRESETS))
        self.assertIn("night_sky", names)
        row = [x for x in rows if x["name"] == "night_sky"][0]
        self.assertTrue(row["exists"] and row["preview"] and not row["builtin"] and row["lighting_flags"]["sunPosition"] == 9)
        self.assertFalse([x for x in rows if x["builtin"] and x["exists"]])

    def test_no_exr_cube_only(self):
        sc = {"name": "Cube", "flags": {"levels-3d-preview": {"exr": "", "skybox": "assets/sky/{face}.png"}}}
        r = sb.import_scene_sky(sc, "Scene.x", "p", world_root=self.tmp, resolver=self.resolver)
        self.assertFalse(r["ok"])
        self.assertIn("cube", r["error"])
        self.assertEqual(self.asked, [])

    def test_missing_image_and_builtin_name(self):
        r = sb.import_scene_sky(SCENE, "Scene.abc123", "p", world_root=self.tmp, resolver=lambda s, d: (None, "not available"))
        self.assertFalse(r["ok"])
        self.assertIn("could not read", r["error"])
        with self.assertRaises(ValueError):
            sb.import_scene_sky(SCENE, "Scene.abc123", "p", name="overcast", world_root=self.tmp, resolver=self.resolver)

    def test_never_calls_a_writing_bridge_op(self):
        class Br:
            ops = []

            def call(self, op, **kw):
                self.ops.append(op)
                return SCENE
        import argparse
        a = argparse.Namespace(place="p", scene_uuid="Scene.abc123", scene_json=None, name=None, image=self.src, assets_dir=None)
        old = sb.skybox_dir
        sb.skybox_dir = lambda place, world_root=None: os.path.join(self.tmp, place, "export", "skybox")
        try:
            sb.cmd_import_scene(a, bridge=Br())
        finally:
            sb.skybox_dir = old
        self.assertEqual(Br.ops, ["get"])


if __name__ == "__main__":
    unittest.main()
