"""The sun / moon drawn in the skybox, the 3D Canvas sun flags (sunPosition / sunTilt) and the preview all share ONE direction.   python illustrator/generators/test_sky_direction.py"""
import math
import os
import sys
import types
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_lighting as fl  # noqa: E402
import foundry_sun as fs  # noqa: E402
import skybox as sb  # noqa: E402

W = 1024


def peak(P):
    """(compass bearing, altitude) of the light body in the picture: the brightest pixel of (sky - the same sky with the body moved 180 degrees in azimuth), clouds and
    stars off so the difference is only the disc / glow."""
    Q = dict(P, cloud=0.0, stars=0.0, milky=0)
    R = dict(Q, sun_az=Q["sun_az"] + 180.0, moon_az=Q["sun_az"] + 180.0)
    lum = sb.sky_dome(Q, W)["sky"].sum(-1) - sb.sky_dome(R, W)["sky"].sum(-1)
    r, c = np.unravel_index(int(np.argmax(lum)), lum.shape)
    az_east = (c + 0.5) / W * 360.0 - 180.0
    return (az_east + 90.0) % 360.0, 90.0 - (r + 0.5) / (W // 2) * 180.0


def ang(a1, e1, a2, e2):
    v = lambda a, e: np.array([math.sin(math.radians(a)) * math.cos(math.radians(e)), -math.cos(math.radians(a)) * math.cos(math.radians(e)), math.sin(math.radians(e))])
    return math.degrees(math.acos(max(-1, min(1, float(v(a1, e1) @ v(a2, e2))))))


class T(unittest.TestCase):
    def test_3d_flag_round_trip(self):
        for az in range(0, 360, 15):
            for alt in (3, 10, 25, 45, 70, 85):
                f = fl.sun_to_3d(az, alt)
                a2, e2 = fl.sun_from_3d(f["sunPosition"], f["sunTilt"])
                self.assertLess(ang(az, alt, a2, e2), 0.6, (az, alt, f, a2, e2))

    def test_every_lighting_preset_sky_matches_light(self):
        for pid, p in fs.load_presets().items():
            with self.subTest(pid):
                self.assertTrue(p.get("sky", {}).get("preset") in sb.PRESETS, "sky preset must exist")
                chk = fs.direction_check(p)
                self.assertTrue(chk["agree"], chk)                              # drawn body vs the light that 3D Canvas casts from the flags
                b = fs.sky_body(p)
                P = sb.sky_params(b["preset"], {"sun_az": b["sky_az_from_east"], "sun_el": b["altitude"]})
                az, el = peak(P)                                               # where the picture really has its brightest point
                self.assertLess(ang(az, el, b["bearing"], b["altitude"]), 2.0, (pid, az, el, b["bearing"], b["altitude"]))

    def test_moon_follows_the_light(self):
        p = fs.get_preset("night")
        self.assertEqual(fs.sky_body(p)["body"], "moon")
        p = fs.apply_overrides(p, types.SimpleNamespace(sun_azimuth=300.0, sun_altitude=50.0))
        b = fs.sky_body(p)
        P = sb.sky_params(b["preset"], {"sun_az": b["sky_az_from_east"], "sun_el": b["altitude"]})
        self.assertEqual((P["moon_az"], P["moon_el"]), (P["sun_az"], P["sun_el"]))
        az, el = peak(P)
        self.assertLess(ang(az, el, 300, 50), 2.0, (az, el))
        a2, e2 = fl.sun_from_3d(**{"sun_position": fs.preset_flags(p)["sunPosition"], "sun_tilt": fs.preset_flags(p)["sunTilt"]})
        self.assertLess(ang(a2, e2, 300, 50), 0.6)                             # the moonlight shadows point away from the moon in the picture

    def test_default_moon_without_override_uses_its_own_position(self):
        P = sb.sky_params("night")
        self.assertEqual((P["sun_az"], P["sun_el"]), (P["moon_az"], P["moon_el"]))

    def test_override_changes_image_name_and_old_sky_keys_are_ignored(self):
        p = fs.get_preset("afternoon")
        n1 = fs.sky_name(p)
        p["sky"]["sun_bearing"], p["sky"]["sun_alt"] = 10, 80                   # legacy keys must not move the sun
        self.assertEqual(fs.sky_name(p), n1)
        p2 = fs.apply_overrides(p, types.SimpleNamespace(sun_azimuth=100.0, sun_altitude=20.0))
        self.assertNotEqual(fs.sky_name(p2), n1)
        self.assertIn("az100_el20", fs.sky_name(p2))

    def test_sky_preset_override(self):
        p = fs.apply_overrides(fs.get_preset("afternoon"), types.SimpleNamespace(sky_preset="storm"))
        self.assertEqual(fs.sky_body(p)["preset"], "storm")
        self.assertIn("storm", fs.sky_name(p))
        p = fs.apply_overrides(fs.get_preset("afternoon"), types.SimpleNamespace(sky_preset="nope"))
        with self.assertRaises(ValueError):
            fs.sky_body(p)

    def test_dramatic_presets_exist_and_differ(self):
        for n in ("high_mountain", "storm", "golden_hour", "foggy", "night", "overcast"):
            self.assertIn(n, sb.PRESETS)
        lum = {n: float(np.median(sb.sky_dome(sb.sky_params(n, {"sun_az": 0, "sun_el": 30}), 256)["sky"])) for n in ("high_mountain", "storm", "night", "foggy")}
        self.assertLess(lum["night"], lum["storm"] * 0.3)
        self.assertLess(lum["storm"], lum["high_mountain"])

    def test_set_sun_reports_direction(self):
        import test_foundry_sun as tfs
        f = tfs.Fake({})
        r = fs.cmd_set_sun(f, tfs.args(preset="storm", sky="off"))
        self.assertTrue(r["direction"]["agree"], r)
        self.assertEqual(r["flags"]["sunTilt"], fl.sun_to_3d(250, 16)["sunTilt"])


if __name__ == "__main__":
    unittest.main()
