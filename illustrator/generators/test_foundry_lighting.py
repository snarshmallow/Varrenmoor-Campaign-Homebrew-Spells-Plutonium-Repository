"""Sun/ambient mapping and light documents (no Foundry). Run: python illustrator/generators/test_foundry_lighting.py"""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foundry_lighting as fl  # noqa: E402
import foundry_push as fp  # noqa: E402


def sun_vec(time_h, tilt):
    """Direction to the sun (E, U, S) from the 3D Canvas rig model: d*(sin t, -cos t cos f, -cos t sin f)."""
    t = fl.ANGLE_AT[int(time_h)] + (time_h - int(time_h)) * (fl.ANGLE_AT[int(time_h) + 1] - fl.ANGLE_AT[int(time_h)])
    f = tilt * math.pi / 2
    return (math.sin(t), -math.cos(t) * math.cos(f), -math.cos(t) * math.sin(f))


class Lighting(unittest.TestCase):
    def test_round_trip(self):
        for az, alt in ((225, 30), (180, 45), (90, 20), (300, 60), (45, 15)):
            f = fl.sun_to_3d(az, alt)
            E, U, S = sun_vec(f["sunPosition"], f["sunTilt"])
            self.assertAlmostEqual(U, math.sin(math.radians(alt)), delta=0.03)
            self.assertAlmostEqual(E, math.sin(math.radians(az)) * math.cos(math.radians(alt)), delta=0.03)
            self.assertAlmostEqual(S, -math.cos(math.radians(az)) * math.cos(math.radians(alt)), delta=0.03)

    def test_default_config_and_skybox(self):
        c = fl.load_lighting({"sun": {"azimuth": 225, "altitude": 30}, "ambient": 0.35, "lights": []})
        f = fl.scene_light_flags(c)
        self.assertEqual(f["timeSync"], "off")
        self.assertEqual(f["ambientLightIntensity"], 0.35)
        self.assertEqual(fl.sun_for_skybox(225, 30), {"sun_az": 135.0, "sun_el": 30})

    def test_no_particles(self):
        doc = {"place": "p", "frame": {"z_origin_ft": 600.0}, "files": [{"lights": [{"id": "l1", "type": "hearth", "point": [10, 20], "z_abs_ft": 605, "animation": "torch", "color": "#ff9a3c"}]}]}
        items = fp.build_light_docs(doc, {"ppf": 20, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0})
        d = items[0]["data"]
        self.assertFalse(d["flags"]["levels-3d-preview"].get("enableParticle"))
        # interior (hearth/window) lights stay non-animated even if the hint carries "torch"; only lamps honour the hint, or an explicit --light-animation
        self.assertIsNone(d["config"]["animation"]["type"])
        forced = fp.build_light_docs(doc, {"ppf": 20, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0}, animation="pulse")
        self.assertEqual(forced[0]["data"]["config"]["animation"]["type"], "pulse")
        self.assertEqual((d["x"], d["y"], d["elevation"]), (200, 400, 5.0))
        c = fl.load_lighting({"sun": {}, "lights": [{"id": "a", "x": 740, "y": 720, "radius": 40, "height": 8}]})
        p = fl.point_light_docs(c, [730, 710], 20)[0]["data"]
        self.assertEqual((p["x"], p["y"]), (200, 200))
        self.assertFalse(p["flags"]["levels-3d-preview"]["enableParticle"])

    def test_hearth_null_lamp_torch(self):
        cc = {"ppf": 20, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0}
        lights = [{"id": "h", "type": "hearth", "point": [1, 2], "animation": "torch"},
                  {"id": "w", "type": "window", "point": [1, 2], "animation": "torch"},
                  {"id": "l", "type": "lamp", "point": [1, 2], "animation": "torch"}]
        items = fp.build_light_docs({"place": "p", "frame": {"z_origin_ft": 0}, "lights": lights}, cc)
        got = {i["data"]["flags"]["varrenmoor"]["type"]: i["data"]["config"]["animation"]["type"] for i in items}
        self.assertEqual(got, {"hearth": None, "window": None, "lamp": "torch"})

    def test_light_height_is_rangetop(self):
        """3D Canvas renders a light at (flags.levels.rangeTop ?? 1 + elevation) / 2; without rangeTop a lamp at 35 ft sat at 18 ft, under the road."""
        doc = {"place": "p", "frame": {"z_origin_ft": 630.0}, "lights": [{"id": "lamp1", "type": "lamp", "point": [1, 2], "z_abs_ft": 665.43}]}
        d = fp.build_light_docs(doc, {"ppf": 20, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0})[0]["data"]
        self.assertEqual(d["elevation"], 35.43)
        self.assertEqual(d["flags"]["levels"]["rangeTop"], d["elevation"])
        c = fl.load_lighting({"sun": {}, "lights": [{"id": "a", "x": 740, "y": 720, "radius": 40, "height": 8}]})
        p = fl.point_light_docs(c, [730, 710], 20)[0]["data"]
        self.assertEqual(p["flags"]["levels"]["rangeTop"], p["elevation"])


if __name__ == "__main__":
    unittest.main()
