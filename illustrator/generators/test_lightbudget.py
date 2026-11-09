"""Tests for foundry_lightbudget.py (light budget, lighting mode, set-lighting). Run: python illustrator/generators/test_lightbudget.py"""
import copy
import json
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_lightbudget as flb  # noqa: E402
import foundry_push as fp  # noqa: E402


def mk(i, kind, x, y, hidden=False, base_flags=None):
    pid = f"light:t:{kind}{i}"
    return {"_id": f"L{kind}{i}", "x": x, "y": y, "hidden": hidden, "config": {"dim": 20, "bright": 8, "alpha": 0.6},
            "flags": {"varrenmoor": {"pipelineId": pid, "type": kind, **(base_flags or {})}, "levels-3d-preview": {"enableParticle": False}}}


def town(n_h=40, n_w=100, n_lamp=10):
    ls = [mk(i, "hearth", (i % 8) * 100, (i // 8) * 100) for i in range(n_h)]
    ls += [mk(i, "window", (i % 10) * 80 + 7, (i // 10) * 80 + 7) for i in range(n_w)]
    ls += [mk(i, "lamp", i * 200, 500) for i in range(n_lamp)]
    return ls


class Fake:
    def __init__(self, lights, flags=None):
        self.scene = {"_id": "S", "name": "Test", "flags": {"levels-3d-preview": dict(flags or {})}, "lights": copy.deepcopy(lights)}
        self.calls = []

    def call(self, op, **a):
        self.calls.append(op)
        return getattr(self, "op_" + op)(**a)

    def op_world_info(self):
        return {"foundry": "14", "world": "w", "modules": [{"id": "varrenmoor-bridge", "version": "0.3.0"}]}

    def op_version(self):
        return {"module": "0.3.0", "protocol": 3, "ops": []}

    def op_get(self, uuid):
        return copy.deepcopy(self.scene)

    @staticmethod
    def merge(dst, src):
        for k, v in src.items():
            if isinstance(v, dict) and isinstance(dst.get(k), dict):
                Fake.merge(dst[k], v)
            else:
                dst[k] = copy.deepcopy(v)

    def op_upsert_many(self, documentName, parentUuid, items, prefix=None, prune=False):
        by = {l["flags"]["varrenmoor"]["pipelineId"]: l for l in self.scene["lights"] if l["flags"].get("varrenmoor")}
        for it in items:
            self.merge(by[it["id"]], it["data"])
        return {"created": 0, "updated": len(items), "deleted": 0}

    def op_update(self, uuid, data):
        self.merge(self.scene, data)
        return {}


def args(**kw):
    ns = flb.parser().parse_args(["set-lighting", "--scene-uuid", "Scene.S"])
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


class Select(unittest.TestCase):
    def test_no_cap_keeps_all(self):
        ls = town()
        keep, drop = flb.select_lights(ls, 0)
        self.assertEqual((len(keep), len(drop)), (len(ls), 0))
        keep, drop = flb.select_lights(ls, 500)
        self.assertEqual(len(drop), 0)

    def test_priority_order(self):
        ls = [{"id": "a", **mk(1, "window", 0, 0)}, {"id": "b", **mk(1, "plaza", 5000, 5000)}, {"id": "c", **mk(1, "hearth", 10, 10)}, {"id": "d", **mk(1, "lamp", 20, 20)}]
        keep, drop = flb.select_lights(ls, 2)
        kinds = sorted(flb.light_kind(k) for k in keep)
        self.assertEqual(kinds, ["lamp", "plaza"])
        self.assertEqual(sorted(flb.light_kind(k) for k in drop), ["hearth", "window"])

    def test_exact_count_and_deterministic(self):
        ls = [{"id": l["flags"]["varrenmoor"]["pipelineId"], **l} for l in town()]
        k1, _ = flb.select_lights(ls, 37)
        k2, _ = flb.select_lights(list(reversed(ls)), 37)
        self.assertEqual(len(k1), 37)
        self.assertEqual({flb.light_key(x) for x in k1}, {flb.light_key(x) for x in k2})

    def test_thinning_spreads(self):
        # 100 windows on a 10x10 grid: 4 survivors must be far apart (not 4 neighbours)
        ls = [{"id": f"w{i}", **mk(i, "window", (i % 10) * 100, (i // 10) * 100)} for i in range(100)]
        keep, _ = flb.select_lights(ls, 4)
        pts = [flb.light_xy(k) for k in keep]
        dmin = min(math.dist(a, b) for i, a in enumerate(pts) for b in pts[i + 1:])
        self.assertGreater(dmin, 400)


class Modes(unittest.TestCase):
    def test_resolve(self):
        self.assertEqual(flb.resolve_mode("lights", 500)["mode"], "lights")
        self.assertEqual(flb.resolve_mode("global", 5)["max"], 0)
        self.assertEqual(flb.resolve_mode("hybrid", 500)["max"], flb.HYBRID_MAX)
        self.assertEqual(flb.resolve_mode("hybrid", 500, 30)["max"], 30)
        self.assertEqual(flb.resolve_mode("auto", 64)["mode"], "lights")
        r = flb.resolve_mode("auto", 65)
        self.assertEqual((r["mode"], r["max"]), ("hybrid", flb.HYBRID_MAX))
        self.assertIn("65", r["reason"])
        self.assertEqual(flb.resolve_mode("auto", 150)["mode"], "hybrid")
        self.assertEqual(flb.resolve_mode("auto", 151)["mode"], "global")
        with self.assertRaises(ValueError):
            flb.resolve_mode("bogus", 1)

    def test_cost(self):
        self.assertEqual(flb.estimate_cost(0)["label"], "low")
        self.assertEqual(flb.estimate_cost(72), {"relative": 2.44, "label": "high"})
        self.assertEqual(flb.estimate_cost(4, 4)["label"], "high")

    def test_time_of_day_and_flags(self):
        f = flb.time_of_day_flags("dusk")
        self.assertEqual(f["sceneTint"], "#ff9c5a")
        self.assertEqual(f["timeSync"], "off")
        self.assertIn("sunPosition", f)
        night = flb.time_of_day_flags("night")
        self.assertLess(night["exposure"], f["exposure"])
        with self.assertRaises(ValueError):
            flb.time_of_day_flags("midnight")
        # lights mode, nothing asked: no flags
        self.assertEqual(flb.scene_flag_changes(args(), "lights"), {})
        # global raises ambient to its floor, an explicit --ambient wins, a time of day never lowers the floor
        self.assertEqual(flb.scene_flag_changes(args(), "global"), {"ambientLightIntensity": flb.GLOBAL_AMBIENT})
        self.assertEqual(flb.scene_flag_changes(args(ambient=0.2), "global")["ambientLightIntensity"], 0.2)
        self.assertEqual(flb.scene_flag_changes(args(time_of_day="night"), "global")["ambientLightIntensity"], flb.GLOBAL_AMBIENT)
        x = flb.scene_flag_changes(args(sun_strength=1.5, sun_color="#ffffff", ambient_color="#aabbcc", render_scene_lights="off"), "lights")
        self.assertEqual(x, {"exposure": 1.5, "sceneTint": "#ffffff", "ambientLightColor": "#aabbcc", "renderSceneLights": False})


class Plan(unittest.TestCase):
    def test_budget_hides_over_budget(self):
        p = flb.plan_lights_on_scene(town(), mode="lights", max_lights=30)
        self.assertEqual((p["on"], p["off"]), (30, 120))
        hidden = [i for i in p["items"] if i["data"].get("hidden")]
        self.assertEqual(len(hidden), 120)
        self.assertTrue(all(i["data"]["flags"]["varrenmoor"]["budgetHidden"] for i in hidden))
        # lamps (priority 80) all survive, then hearths
        self.assertEqual(p["by_kind_on"].get("lamp"), 10)
        self.assertNotIn("window", p["by_kind_on"])

    def test_global_hides_everything(self):
        p = flb.plan_lights_on_scene(town(), mode="global")
        self.assertEqual(p["on"], 0)
        self.assertEqual(len(p["items"]), 150)

    def test_exclude_types(self):
        p = flb.plan_lights_on_scene(town(), mode="lights", exclude_types=("window",))
        self.assertEqual(p["by_kind_on"], {"hearth": 40, "lamp": 10})

    def test_hand_hidden_untouched(self):
        ls = town(5, 5, 0)
        ls[0]["hidden"] = True            # the GM hid this one by hand
        p = flb.plan_lights_on_scene(ls, mode="global")
        self.assertEqual(p["hand_hidden"], 1)
        self.assertNotIn(ls[0]["flags"]["varrenmoor"]["pipelineId"], [i["id"] for i in p["items"]])

    def test_scale_is_idempotent_and_not_compounding(self):
        f = Fake(town(3, 0, 0))
        a = args(light_radius_scale=2.0, light_intensity_scale=0.5, apply=True)
        r = flb.cmd_set_lighting(f, a)
        self.assertTrue(r["applied"])
        for l in f.scene["lights"]:
            self.assertEqual((l["config"]["dim"], l["config"]["bright"], l["config"]["alpha"]), (40, 16, 0.3))
            self.assertEqual(l["flags"]["varrenmoor"]["base"]["dim"], 20)
        r2 = flb.cmd_set_lighting(f, a)           # second run: nothing to change
        self.assertEqual(r2["light_changes"], 0)
        a1 = args(light_radius_scale=1.0, light_intensity_scale=1.0, apply=True)
        flb.cmd_set_lighting(f, a1)                # back to scale 1 from the stored base
        for l in f.scene["lights"]:
            self.assertEqual((l["config"]["dim"], l["config"]["bright"], l["config"]["alpha"]), (20, 8, 0.6))

    def test_light_shadows_top_n(self):
        p = flb.plan_lights_on_scene(town(10, 0, 3), mode="lights", light_shadows="4")
        self.assertEqual(p["shadow"], 4)
        flagged = [i for i in p["items"] if i["data"].get("flags", {}).get("levels-3d-preview", {}).get("castShadow")]
        self.assertEqual(len(flagged), 4)
        self.assertEqual(sum("lamp" in i["id"] for i in flagged), 3)       # the 3 lamps outrank hearths
        off = flb.plan_lights_on_scene(town(2, 0, 0), mode="lights", light_shadows="off")
        self.assertEqual(off["items"], [])          # already false: nothing to write


class Command(unittest.TestCase):
    def test_dry_run_writes_nothing_then_apply_then_restore(self):
        f = Fake(town(), {"ambientLightIntensity": 0.35, "exposure": 1})
        before = copy.deepcopy(f.scene)
        r = flb.cmd_set_lighting(f, args(lighting_mode="hybrid"))
        self.assertFalse(r["applied"])
        self.assertEqual(f.scene, before)
        self.assertNotIn("upsert_many", f.calls)
        self.assertEqual((r["lights_on_after"], r["lights_off_after"], r["mode"]), (16, 134, "hybrid"))
        self.assertEqual(r["flag_changes"], {"ambientLightIntensity": flb.HYBRID_AMBIENT})
        r = flb.cmd_set_lighting(f, args(lighting_mode="hybrid", apply=True))
        self.assertTrue(r["applied"])
        self.assertEqual(sum(1 for l in f.scene["lights"] if not l["hidden"]), 16)
        self.assertEqual(f.scene["flags"]["levels-3d-preview"]["ambientLightIntensity"], flb.HYBRID_AMBIENT)
        self.assertEqual(flb.cmd_set_lighting(f, args(lighting_mode="hybrid", apply=True))["light_changes"], 0)       # idempotent
        # lights mode, no cap: every light we hid comes back, the ambient flag stays where the user left it
        flb.cmd_set_lighting(f, args(lighting_mode="lights", ambient=0.35, apply=True))
        self.assertEqual(sum(1 for l in f.scene["lights"] if l["hidden"]), 0)
        self.assertEqual(f.scene["flags"]["levels-3d-preview"]["ambientLightIntensity"], 0.35)

    def test_only_pipeline_lights_touched(self):
        f = Fake(town(5, 0, 0) + [{"_id": "GM", "x": 1, "y": 1, "hidden": False, "config": {"dim": 5, "bright": 2, "alpha": 0.5}, "flags": {}}])
        r = flb.cmd_set_lighting(f, args(lighting_mode="global", apply=True))
        gm = [l for l in f.scene["lights"] if l["_id"] == "GM"][0]
        self.assertFalse(gm["hidden"])
        self.assertEqual(r["pipeline_lights"], 5)

    def test_auto_small_scene_is_unchanged(self):
        f = Fake(town(10, 20, 2), {"ambientLightIntensity": 0.35})
        r = flb.cmd_set_lighting(f, args(lighting_mode="auto"))
        self.assertEqual((r["mode"], r["light_changes"], r["flag_changes"]), ("lights", 0, {}))

    def test_needs_scene(self):
        with self.assertRaises(fp.PushError):
            flb.cmd_set_lighting(Fake([]), flb.parser().parse_args(["set-lighting"]))

    def test_bad_time_is_an_error_not_a_traceback(self):
        a = args()
        a.time_of_day = "teatime"
        with self.assertRaises(fp.PushError):
            flb.cmd_set_lighting(Fake(town(1, 0, 0)), a)


class Push(unittest.TestCase):
    def test_limit_new_lights(self):
        items = [{"id": f"light:t:{l['flags']['varrenmoor']['type']}{i}", "data": {"x": l["x"], "y": l["y"], "config": dict(l["config"]), "flags": l["flags"]}}
                 for i, l in enumerate(town(20, 60, 5))]
        out, info = flb.limit_new_lights(items, mode="hybrid", max_lights=12)
        self.assertEqual((len(out), info["dropped"]), (12, 73))
        out, info = flb.limit_new_lights(items, mode="global")
        self.assertEqual(out, [])
        out, info = flb.limit_new_lights(items, mode="lights", exclude_types=("window",), radius_scale=2.0, intensity_scale=2.0)
        self.assertEqual(len(out), 25)
        self.assertEqual(out[0]["data"]["config"]["dim"], 40)
        self.assertEqual(out[0]["data"]["config"]["alpha"], 1.0)
        self.assertEqual(items[0]["data"]["config"]["dim"], 20)            # the input is not modified

    def test_budget_requested_default_is_off(self):
        ns = fp.parser().parse_args(["push-lights", "--scene-uuid", "Scene.S"])
        self.assertEqual((ns.max_lights, ns.lighting_mode), (0, "lights"))
        self.assertFalse(flb.budget_requested(ns))
        ns = fp.parser().parse_args(["push-lights", "--scene-uuid", "Scene.S", "--max-lights", "10"])
        self.assertTrue(flb.budget_requested(ns))
        ns = fp.parser().parse_args(["push-scene-3d", "--scene-uuid", "Scene.S", "--lighting-mode", "auto"])
        self.assertTrue(flb.budget_requested(ns))

    def test_set_lighting_routes_from_foundry_push(self):
        f = Fake(town(3, 0, 0))
        rc = fp.main(["set-lighting", "--scene-uuid", "Scene.S", "--lighting-mode", "global"], bridge=f)
        self.assertEqual(rc, 0)
        self.assertEqual(sum(1 for l in f.scene["lights"] if l["hidden"]), 0)       # dry run by default


if __name__ == "__main__":
    unittest.main()
