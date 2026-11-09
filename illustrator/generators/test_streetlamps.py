"""Street lamps: spacing, edge placement, counts, junction/door/bridge skipping, determinism, on/off, per-road override, light kinds, scene toggle plan.
  python illustrator/generators/test_streetlamps.py        (light: synthetic roads; the pack test copies only placements.json to a temp folder)"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import streetlamps as sl  # noqa: E402
import streetlamps_scene as sc  # noqa: E402
import foundry_lightbudget as flb  # noqa: E402

PACK = os.path.join(HERE, "..", "..", "world", "bridgehollow__dyers_walk_local", "export")


def road(rid, pts, w=16.0, cls="street", mat="mat_gravel", **kw):
    return {"id": rid, "points": [[x, y, 100.0 + 0.01 * x] for x, y in pts], "width_ft": w, "class": cls, "surface": {"material": mat}, **kw}


def cfg(**kw):
    return {"enabled": True, "min_lamps": 1, **kw}


MAIN = road("str_a", [(0, 0), (400, 0)])


class Placement(unittest.TestCase):
    def test_spacing_exact_and_centred(self):
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=50, side="left", skip_junction_ft=0))
        xs = sorted(l["x"] for l in r["lamps"])
        self.assertEqual(len(xs), 8)                                   # (400-12)/50 -> 7 gaps -> 8 lamps
        gaps = [b - a for a, b in zip(xs, xs[1:])]
        self.assertTrue(all(abs(g - 50) < 0.01 for g in gaps), gaps)
        self.assertAlmostEqual((xs[0] + xs[-1]) / 2, 200, 1)

    def test_on_road_edge_plus_offset(self):
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=50, side="both", offset_ft=2.5))
        for l in r["lamps"]:
            self.assertAlmostEqual(abs(l["y"]), 8.0 + 2.5, 2)
        self.assertEqual({l["side"] for l in r["lamps"]}, {"left", "right"})

    def test_sides(self):
        n = lambda side: len(sl.plan_lamps([MAIN], [], cfg(spacing_ft=40, side=side))["lamps"])
        self.assertEqual(n("left"), n("right"))
        self.assertEqual(n("both"), 2 * n("left"))
        self.assertEqual(n("alternating"), n("left"))
        alt = sl.plan_lamps([MAIN], [], cfg(spacing_ft=40, side="alternating"))["lamps"]
        self.assertEqual([l["side"] for l in alt[:4]], ["left", "right", "left", "right"])

    def test_height_and_arm_faces_road(self):
        l = sl.plan_lamps([MAIN], [], cfg(spacing_ft=100, side="left", height_ft=12))["lamps"][0]
        self.assertEqual(l["height_ft"], 12)
        self.assertAlmostEqual(math.sin(math.radians(l["rot_deg"])), -math.copysign(1, l["y"]), 3)       # arm points back to y = 0
        self.assertAlmostEqual(l["z"], 100.0 + 0.01 * l["station_ft"], 1)                               # sits on the graded road height

    def test_classes(self):
        dirt = road("str_d", [(0, 100), (300, 100)], mat="mat_packed_earth")
        lane = road("str_l", [(0, 200), (300, 200)], cls="lane")
        both = [MAIN, dirt, lane]
        self.assertEqual({sl.road_class(r) for r in both}, {"main", "dirt", "side"})
        only = lambda c: {l["road"] for l in sl.plan_lamps(both, [], cfg(spacing_ft=60, classes=[c]))["lamps"]}
        self.assertEqual(only("main"), {"str_a"})
        self.assertEqual(only("dirt"), {"str_d"})
        self.assertEqual(only("side"), {"str_l"})
        self.assertEqual(len(sl.plan_lamps(both, [], cfg(classes=[]))["lamps"]), 0)

    def test_junction_skip(self):
        t = road("str_t", [(200, 0), (200, 150)])                      # T junction in the middle of MAIN
        with_skip = sl.plan_lamps([MAIN, t], [], cfg(spacing_ft=20, side="both", skip_junction_ft=15))
        without = sl.plan_lamps([MAIN, t], [], cfg(spacing_ft=20, side="both", skip_junction_ft=0))
        self.assertGreater(with_skip["skipped"]["junction"], 0)
        self.assertLess(len(with_skip["lamps"]), len(without["lamps"]))
        for l in with_skip["lamps"]:
            self.assertGreaterEqual(math.hypot(l["x"] - 200, l["y"] - 0), 8 + 15 - 0.01)

    def test_bridge_and_doors_and_buildings(self):
        br = road("str_br", [(0, 100), (200, 100)], bridge={"deck_elevations_ft": []})
        r = sl.plan_lamps([MAIN, br], [], cfg(spacing_ft=40))
        self.assertTrue(all(l["road"] != "str_br" for l in r["lamps"]))
        self.assertEqual(sl.plan_lamps([br], [], cfg(skip_bridges=False, spacing_ft=40))["lamps"][0]["road"], "str_br")
        door = {"id": "b1", "polygon": [[150, 30], [190, 30], [190, 60], [150, 60]], "doors": [{"kind": "exterior", "point": [190, -9.5]}]}
        free = sl.plan_lamps([MAIN], [], cfg(spacing_ft=20, side="both", skip_junction_ft=0, skip_doors_ft=0))
        skip = sl.plan_lamps([MAIN], [door], cfg(spacing_ft=20, side="both", skip_junction_ft=0, skip_doors_ft=8))
        self.assertGreater(skip["skipped"]["door"], 0)
        self.assertLess(len(skip["lamps"]), len(free["lamps"]))
        bld = {"id": "b2", "polygon": [[0, 8], [400, 8], [400, 30], [0, 30]], "doors": []}      # a building right at the road edge: lamps would stand in it
        self.assertGreater(sl.plan_lamps([MAIN], [bld], cfg(spacing_ft=40, side="left", offset_ft=1.0))["skipped"]["building"], 0)

    def test_min_lamps_and_short_road(self):
        short = road("str_s", [(0, 0), (40, 0)])
        self.assertEqual(len(sl.plan_lamps([short], [], cfg(spacing_ft=60, min_lamps=2))["lamps"]), 0)
        self.assertEqual(len(sl.plan_lamps([short], [], cfg(spacing_ft=60, min_lamps=1, end_margin_ft=6))["lamps"]), 1)

    def test_centre_short_and_state(self):
        short = road("str_s", [(0, 0), (10, 0)])
        r = sl.plan_lamps([short], [], cfg(spacing_ft=60, min_lamps=2))
        self.assertEqual(len(r["lamps"]), 0)
        r = sl.plan_lamps([short], [], cfg(spacing_ft=60, min_lamps=2, centre_short=True))
        self.assertEqual(len(r["lamps"]), 1)
        self.assertAlmostEqual(r["lamps"][0]["station_ft"], 5.0, places=1)
        self.assertEqual(r["roads"]["str_s"]["lamps"], 1)
        # on but every position skipped by a junction: never a plain "on"
        cross = road("str_x", [(50, -50), (50, 50)])
        r = sl.plan_lamps([road("str_s", [(0, 0), (100, 0)]), cross], [], cfg(spacing_ft=60, min_lamps=1, skip_junction_ft=200))
        st = r["roads"]["str_s"]["state"]
        self.assertTrue(st == "on" or st.startswith("on ("), st)
        if not r["roads"]["str_s"]["lamps"]:
            self.assertIn("0 lamps", st)
        # forced-on road too short for its margins reports that
        tiny = road("str_t", [(0, 0), (8, 0)], edit={"lamps": {"on": True}})
        self.assertEqual(sl.plan_lamps([tiny], [], cfg(spacing_ft=60))["roads"]["str_t"]["state"], "too short for 1 lamp(s)")

    def test_apply_default_keeps_stored_switch(self):
        class A:
            pass
        d = tempfile.mkdtemp()
        try:
            self.assertTrue(sl._stored_enabled([os.path.join(d, "none.json")]))
            p = os.path.join(d, "placements.json")
            with open(p, "w") as f:
                json.dump({"streetlamps": {"enabled": False, "config": {"enabled": False}}}, f)
            self.assertFalse(sl._stored_enabled([p]))
            with open(p, "w") as f:
                json.dump({"streetlamps": {"enabled": True, "config": {"enabled": True}}}, f)
            self.assertTrue(sl._stored_enabled([p]))
        finally:
            shutil.rmtree(d, ignore_errors=True)
        a = sl.build_parser().parse_args(["apply", "--centre-short", "on"])
        self.assertTrue(sl._cfg_from_args(a)["centre_short"])
        self.assertNotIn("enabled", sl._cfg_from_args(a))

    def test_determinism_and_jitter(self):
        a = sl.plan_lamps([MAIN], [], cfg(spacing_ft=30, jitter_ft=6, seed=3))
        b = sl.plan_lamps([MAIN], [], cfg(spacing_ft=30, jitter_ft=6, seed=3))
        c = sl.plan_lamps([MAIN], [], cfg(spacing_ft=30, jitter_ft=6, seed=4))
        z = sl.plan_lamps([MAIN], [], cfg(spacing_ft=30, jitter_ft=0))
        self.assertEqual(json.dumps(a["lamps"]), json.dumps(b["lamps"]))
        self.assertNotEqual(json.dumps(a["lamps"]), json.dumps(c["lamps"]))
        self.assertNotEqual(json.dumps(a["lamps"]), json.dumps(z["lamps"]))
        for l in a["lamps"]:
            self.assertAlmostEqual(abs(l["y"]), 8 + 1.5, 2)             # jitter moves lamps along the road only

    def test_disabled_gives_nothing(self):
        self.assertEqual(sl.plan_lamps([MAIN], [], {"enabled": False})["lamps"], [])

    def test_per_road_override(self):
        other = road("str_b", [(0, 100), (400, 100)])
        off = dict(MAIN, edit={"lamps": {"on": False}})
        r = sl.plan_lamps([off, other], [], cfg(spacing_ft=50))
        self.assertEqual({l["road"] for l in r["lamps"]}, {"str_b"})
        st = dict(other, edit={"lamps": {"style": "torch_post", "spacing_ft": 100}})
        r = sl.plan_lamps([MAIN, st], [], cfg(spacing_ft=50, style="wooden_oil"))
        self.assertEqual({l["style"] for l in r["lamps"] if l["road"] == "str_b"}, {"torch_post"})
        self.assertEqual({l["style"] for l in r["lamps"] if l["road"] == "str_a"}, {"wooden_oil"})
        nb = lambda rid: len([l for l in r["lamps"] if l["road"] == rid])
        self.assertLess(nb("str_b"), nb("str_a"))
        forced = dict(road("str_f", [(0, 0), (300, 0)], mat="mat_packed_earth"), edit={"lamps": {"on": True}})
        self.assertGreater(len(sl.plan_lamps([forced], [], cfg(classes=["main"], spacing_ft=50))["lamps"]), 0)       # on = forced even when the class is not ticked

    def test_wall_bracket(self):
        b = {"id": "b3", "polygon": [[100, 12], [180, 12], [180, 40], [100, 40]], "doors": []}
        r = sl.plan_lamps([MAIN], [b], cfg(style="bracket_wall", spacing_ft=20, side="left", height_ft=9))
        self.assertGreater(len(r["lamps"]), 0)
        self.assertGreater(r["skipped"]["no_wall"], 0)
        for l in r["lamps"]:
            self.assertLess(abs(l["y"] - 12.0), 0.2)
            self.assertEqual(l["building"], "b3")

    def test_validation(self):
        for bad in ({"style": "nope"}, {"side": "up"}, {"spacing_ft": 1}, {"classes": ["x"]}, {"light": {"color": "red"}}):
            with self.assertRaises(ValueError):
                sl.normalize_config(bad)


class Lights(unittest.TestCase):
    def test_light_kind_and_fields(self):
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=50, style="torch_post"))
        ls = sl.lamp_lights(r["lamps"], r["config"])
        self.assertEqual(len(ls), len(r["lamps"]))
        for l, lamp in zip(ls, r["lamps"]):
            self.assertEqual(l["type"], "lamp")
            self.assertEqual(flb.priority_of(l["type"]), 80)               # high priority in the budget
            self.assertGreater(l["z_abs_ft"], lamp["z"] + 5)
            self.assertEqual(l["animation"], "torch")
            self.assertFalse(l["shadows"])
            self.assertTrue(l["color"].startswith("#"))
        off = sl.normalize_config({"enabled": True, "light": {"enabled": False}})
        self.assertEqual(sl.lamp_lights(r["lamps"], off), [])

    def test_colour_temperature_and_overrides(self):
        warm, cool = sl.kelvin_to_hex(1800), sl.kelvin_to_hex(6500)
        self.assertGreater(int(warm[1:3], 16), int(warm[5:7], 16) + 100)       # candle: red far above blue
        self.assertGreater(int(cool[5:7], 16), 240)
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=100, light={"kelvin": 4000, "dim_ft": 60, "bright_ft": 20, "intensity": 0.8, "flicker": False, "shadows": True}))
        l = sl.lamp_lights(r["lamps"], r["config"])[0]
        self.assertEqual((l["dim_ft"], l["bright_ft"], l["intensity"], l["animation"], l["shadows"], l["color"]), (60, 20, 0.8, None, True, sl.kelvin_to_hex(4000)))
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=100, light={"color": "#88ccff"}))
        self.assertEqual(sl.lamp_lights(r["lamps"], r["config"])[0]["color"], "#88ccff")

    def test_push_light_doc(self):
        import foundry_push as fp
        r = sl.plan_lamps([MAIN], [], cfg(spacing_ft=100))
        doc = {"place": "p", "frame": {"z_origin_ft": 0}, "lights": sl.lamp_lights(r["lamps"], r["config"]), "files": []}
        items = fp.build_light_docs(doc, {"ppf": 20, "sceneX": 0, "sceneY": 0, "x0": 0, "y0": 0}, None, None)
        self.assertEqual(len(items), len(r["lamps"]))
        d = items[0]["data"]
        self.assertEqual(d["config"]["animation"]["type"], "torch")
        self.assertIs(d["flags"]["levels-3d-preview"]["castShadow"], False)
        self.assertEqual(d["flags"]["varrenmoor"]["type"], "lamp")
        self.assertEqual(items[0]["id"].split(":")[0], "light")


class Meshes(unittest.TestCase):
    def test_every_style_has_a_mesh(self):
        st = sl.load_styles()
        self.assertEqual(set(st["styles"]), set(sl.BUILDERS))
        for k, v in st["styles"].items():
            m = sl.style_mesh(k, v["height_ft"])
            self.assertTrue(40 < m.tri_count < 600, (k, m.tri_count))
            if v["mount"] == "post":
                self.assertGreater(m.V[:, 2].max(), v["height_ft"] * 0.9)
                self.assertLess(m.V[:, 2].min(), 0.01)


@unittest.skipUnless(os.path.exists(os.path.join(PACK, "placements.json")), "no Dyers pack")
class PackApply(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vblamps-")
        shutil.copy(os.path.join(PACK, "placements.json"), self.tmp)
        self.pp = os.path.join(self.tmp, "placements.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cli(self, *a):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = sl.main(["apply", "--place", "bridgehollow__dyers_walk_local", "--placements", self.pp, *a])
        return rc, json.loads(buf.getvalue())

    def load(self):
        with open(self.pp, encoding="utf-8") as f:
            return json.load(f)

    def glb(self):
        return os.path.join(self.tmp, *sl.FILE_REL.split("/"))

    def h(self):
        out = []
        for p in (self.pp, self.glb()):
            with open(p, "rb") as f:
                out.append(hashlib.sha256(f.read()).hexdigest())
        return tuple(out)

    def test_on_off_idempotent(self):
        with open(self.pp, encoding="utf-8") as f:
            n_files0 = len(json.load(f)["files"])
        args = ("--enabled", "on", "--style", "wrought_iron", "--spacing", "30", "--skip-junction", "8", "--min-lamps", "1")
        rc, r = self.run_cli(*args)
        self.assertEqual(rc, 0, r)
        self.assertGreater(r["lamps"], 3)
        h1 = self.h()
        self.run_cli(*args)
        self.assertEqual(h1, self.h(), "second run must be byte-identical")
        d = self.load()
        self.assertEqual(len(d["files"]), n_files0 + 1)
        e = [x for x in d["files"] if x["layer"] == "streetlamps"][0]
        self.assertEqual(e["file"], sl.FILE_REL)
        self.assertEqual(sum(1 for l in d["lights"] if l["type"] == "lamp"), r["lamps"])
        self.assertEqual(d["streetlamps"]["lamps"], r["lamps"])
        self.assertTrue(any(l["type"] == "hearth" for e in d["files"] for l in e.get("lights", [])))          # other (per-file) lights untouched
        import glb_check
        self.assertEqual(glb_check.validate_glb(self.glb(), False), [])
        self.run_cli("--enabled", "off")
        d = self.load()
        self.assertEqual(len(d["files"]), n_files0)
        self.assertFalse(any(l.get("type") == "lamp" for l in d.get("lights", [])))
        self.assertFalse(os.path.exists(self.glb()))
        self.assertEqual(d["streetlamps"]["enabled"], False)
        self.assertTrue(any(l["type"] == "hearth" for e in d["files"] for l in e.get("lights", [])))

    def test_collision_sight_defaults(self):
        import foundry_collision as fc
        self.assertIn("streetlamps", fc.parse_collision(None))
        self.assertNotIn("streetlamps", fc.parse_sight(None))

    def test_tile_flags(self):
        import foundry_push as fp
        self.run_cli("--enabled", "on", "--spacing", "30", "--skip-junction", "8", "--min-lamps", "1")
        d = self.load()
        a = argparse.Namespace(layers="streetlamps", ids=None, lod=None, collision=None, collision_lod=None, sight=None, roofs_hidden=False)
        items = fp.build_model_tiles(d, {"ppf": 20.0, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0}, a, None)
        self.assertEqual(len(items), 1)
        f = items[0]["data"]["flags"]["levels-3d-preview"]
        self.assertTrue(f["collision"])
        self.assertFalse(f["sight"])
        self.assertEqual(items[0]["data"]["flags"]["varrenmoor"]["layer"], "streetlamps")


class SceneToggle(unittest.TestCase):
    def scene(self):
        F = "varrenmoor"
        cfg0 = {"dim": 30, "bright": 10, "alpha": 0.5, "color": "#ffffff", "animation": {"type": None}}
        return {"name": "ZZ", "tiles": [{"uuid": "T1", "hidden": False, "flags": {F: {"layer": "streetlamps", "pipelineId": "model:p:streetlamps/streetlamps"}}},
                                         {"uuid": "T2", "hidden": False, "flags": {F: {"layer": "buildings", "pipelineId": "model:p:b"}}}],
                "lights": [{"hidden": False, "config": dict(cfg0), "flags": {F: {"type": "lamp", "pipelineId": "light:p:lamp_1"}}},
                           {"hidden": True, "config": dict(cfg0), "flags": {F: {"type": "lamp", "pipelineId": "light:p:lamp_2", "budgetHidden": True}}},
                           {"hidden": False, "config": dict(cfg0), "flags": {F: {"type": "hearth", "pipelineId": "light:p:h1"}}}]}

    def test_off_on_only_lamps(self):
        s = self.scene()
        p = sc.plan(s, False)
        self.assertEqual(p["tile_updates"], [("T1", {"hidden": True})])
        self.assertEqual([i["id"] for i in p["light_items"]], ["light:p:lamp_1"])
        self.assertIs(p["light_items"][0]["data"]["hidden"], True)
        s["tiles"][0]["hidden"] = True
        s["lights"][0]["hidden"] = True
        s["lights"][0]["flags"]["varrenmoor"]["lampHidden"] = True
        p = sc.plan(s, True)
        self.assertEqual(p["tile_updates"], [("T1", {"hidden": False})])
        self.assertIs(p["light_items"][0]["data"]["hidden"], False)
        self.assertEqual(len(p["light_items"]), 1)                       # the budget-hidden lamp stays hidden

    def test_idempotent_and_retune(self):
        s = self.scene()
        self.assertEqual(sc.plan(s, True)["tile_updates"], [])
        self.assertEqual(sc.plan(s, True)["light_items"], [])
        w = sc.light_wanted({"kelvin": 2700, "dim_ft": 50, "intensity": 0.7, "flicker": True, "shadows": False})
        p = sc.plan(s, None, w)
        self.assertEqual(len(p["light_items"]), 2)                       # both lamp lights, never the hearth
        d = p["light_items"][0]["data"]
        self.assertEqual((d["config"]["dim"], d["config"]["alpha"], d["config"]["animation"]["type"], d["config"]["color"]), (50.0, 0.7, "torch", sl.kelvin_to_hex(2700)))
        self.assertNotIn("light:p:h1", [i["id"] for i in p["light_items"]])
        for l in s["lights"]:
            l["config"].update(dim=50.0, alpha=0.7, color=sl.kelvin_to_hex(2700), animation={"type": "torch"})
        self.assertEqual(sc.plan(s, None, w)["light_items"], [])


class EditPlumbing(unittest.TestCase):
    def test_worldpack_road_edit_keeps_lamps(self):
        import worldpack as wp
        self.assertEqual(wp.road_edit({"edit": {"lamps": {"on": False, "style": "torch_post", "spacing_ft": 40, "junk": 1}, "kerb": True}}),
                         {"kerb": True, "lamps": {"on": False, "style": "torch_post", "spacing_ft": 40.0}})
        self.assertEqual(wp.road_edit({"edit": {"lamps": {"on": "yes"}}}), {})

    def test_object_edit_lamps(self):
        import object_edit as oe
        tx = oe.textures()
        self.assertIs(oe._coerce("lamps.on", "false", oe.ROAD_EDIT["lamps.on"], tx), False)
        self.assertEqual(oe._coerce("lamps.style", "torch_post", oe.ROAD_EDIT["lamps.style"], tx), "torch_post")
        self.assertEqual(oe._coerce("lamps.spacing_ft", "45", oe.ROAD_EDIT["lamps.spacing_ft"], tx), 45.0)
        with self.assertRaises(SystemExit):
            oe._coerce("lamps.style", "gold", oe.ROAD_EDIT["lamps.style"], tx)
        with self.assertRaises(SystemExit):
            oe._coerce("lamps.spacing_ft", "2", oe.ROAD_EDIT["lamps.spacing_ft"], tx)
        self.assertIn("torch_post", oe.choices()["lamp_styles"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
