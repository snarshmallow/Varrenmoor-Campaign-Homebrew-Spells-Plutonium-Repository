"""Light budget, lighting mode and 3D lighting flags for the 3D Canvas scenes (command `set-lighting`; helpers used by foundry_push.py push-lights / push-scene-3d).

What costs what in 3D Canvas 9.0.29 (source read on Vega, FOUNDRY_3D_CANVAS_NOTES.md section 11):
  * Every AmbientLight with `renderSceneLights` on becomes a three.js PointLight (Light3D). three.js r132 shades forward: EVERY visible point light is looped over for EVERY lit
    fragment of EVERY material, and a change of the light count recompiles the shaders. So cost grows with (number of visible lights) x (pixels): it is the main light cost.
    A hidden light (AmbientLight.hidden) has `light3d.visible = false` and is skipped, which is how the budget switches lights off without deleting them.
  * Light shadows: per-light flag `levels-3d-preview.castShadow` (default OFF) AND the client setting `shadowQuality` > 0. A shadow-casting point light renders the scene
    6 more times per frame into a cube map of 256 x shadowQuality px per face: by far the most expensive per light. The pipeline leaves it off.
  * Sun: one DirectionalLight, shadow map 1024 x shadowQuality (client setting, 0 = no sun shadows). There is NO scene flag for shadow quality or a light cap.
  * "Global illumination" in this module = the scene flag `ambientLightIntensity` / `ambientLightColor` (one THREE.AmbientLight, constant cost) plus the sun (`sunPosition`,
    `sunTilt`, `exposure`, `sceneTint`) and the HDRI (`exr`). Cost does not depend on the light count.
Modes: lights = pipeline point lights (optionally capped), global = no pipeline point lights, ambient raised, hybrid = a capped set of the most important lights + moderate ambient.
Everything here is dry-run by default; only documents flagged flags.varrenmoor.pipelineId `light:*` are ever touched; lights switched off by the budget are marked
flags.varrenmoor.budgetHidden so a later run can switch them on again without touching lights the GM hid by hand.
"""
import argparse
import json
import math
import sys

FLAG = "varrenmoor"
L3D = "levels-3d-preview"
MODES = ("lights", "global", "hybrid", "auto")

# importance when the budget is short: plazas, street lamps, doors, hearths, then windows (higher = kept first)
PRIORITY = {"plaza": 100, "square": 100, "lamp": 80, "streetlamp": 80, "street_lamp": 80, "point2d": 75, "door": 70, "gate": 70, "hearth": 60, "torch": 55, "window": 30}
DEFAULT_PRIORITY = 50

HYBRID_MAX = 16               # hybrid with no explicit --max-lights
GLOBAL_AMBIENT = 0.55         # ambient strength used by mode global when none is given
HYBRID_AMBIENT = 0.45
AUTO_HYBRID_ABOVE = 64        # auto: more pipeline lights than this -> hybrid
AUTO_GLOBAL_ABOVE = 256       # auto: more than this -> global
# estimated relative cost (1.0 = the empty scene with sun + ambient); constants from the live measurements, FOUNDRY_3D_CANVAS_NOTES.md section 11
COST_PER_LIGHT = 0.02
COST_PER_SHADOW_LIGHT = 0.6
COST_LEVELS = ((1.25, "low"), (2.0, "medium"), (4.0, "high"))

# time of day: sun bearing/altitude (same numbers as the panel's Lighting presets) + colour, exposure (= sun strength) and ambient
TIME_OF_DAY = {
    "dawn": {"azimuth": 95, "altitude": 18, "color": "#ffd9a8", "exposure": 0.9, "ambient": 0.42},
    "noon": {"azimuth": 180, "altitude": 68, "color": "#fffbe8", "exposure": 1.0, "ambient": 0.40},
    "dusk": {"azimuth": 285, "altitude": 7, "color": "#ff9c5a", "exposure": 0.75, "ambient": 0.30},
    "night": {"azimuth": 120, "altitude": 40, "color": "#a8b8ff", "exposure": 0.25, "ambient": 0.14},
}


# ------------------------------------------------------------------ pure helpers (no Foundry calls)
def _data(l):
    return l.get("data", l)


def light_kind(l):
    return ((_data(l).get("flags") or {}).get(FLAG) or {}).get("type") or "light"


def light_xy(l):
    d = _data(l)
    return float(d.get("x", 0)), float(d.get("y", 0))


def light_key(l):
    return l.get("id") or ((_data(l).get("flags") or {}).get(FLAG) or {}).get("pipelineId") or str(light_xy(l))


def priority_of(kind):
    return PRIORITY.get(str(kind).lower(), DEFAULT_PRIORITY)


def select_lights(lights, max_lights):
    """Keep at most max_lights (None/0 = all). Most important kinds first; inside a kind that does not fit entirely, farthest-point sampling
    (each pick maximises its distance to everything already kept) so the survivors are spread evenly instead of clumped. Deterministic. -> (keep, drop)."""
    lights = list(lights)
    if not max_lights or max_lights < 0 or len(lights) <= max_lights:
        return lights, []
    tiers = {}
    for l in lights:
        tiers.setdefault(priority_of(light_kind(l)), []).append(l)
    keep = []
    for pr in sorted(tiers, reverse=True):
        room = max_lights - len(keep)
        if room <= 0:
            break
        tier = sorted(tiers[pr], key=light_key)
        if len(tier) <= room:
            keep += tier
            continue
        pool = list(tier)
        if not keep:                                   # seed: the light farthest from the tier centroid, then spread from it
            cx = sum(light_xy(l)[0] for l in pool) / len(pool)
            cy = sum(light_xy(l)[1] for l in pool) / len(pool)
            first = max(pool, key=lambda l: ((light_xy(l)[0] - cx) ** 2 + (light_xy(l)[1] - cy) ** 2, light_key(l)))
            keep.append(first)
            pool.remove(first)
            room -= 1
        dmin = {light_key(l): min(math.dist(light_xy(l), light_xy(k)) for k in keep) for l in pool}
        for _ in range(room):
            best = max(pool, key=lambda l: (dmin[light_key(l)], light_key(l)))
            pool.remove(best)
            keep.append(best)
            for l in pool:
                dmin[light_key(l)] = min(dmin[light_key(l)], math.dist(light_xy(l), light_xy(best)))
    ks = {light_key(l) for l in keep}
    return [l for l in lights if light_key(l) in ks], [l for l in lights if light_key(l) not in ks]


def resolve_mode(mode, n_lights, max_lights=0):
    """-> {"mode": effective mode, "max": cap or 0, "reason": plain-language why}. 'auto' picks by the number of pipeline lights."""
    mode = mode or "lights"
    if mode not in MODES:
        raise ValueError(f"lighting mode {mode!r} is not one of {', '.join(MODES)}")
    max_lights = int(max_lights or 0)
    if mode == "auto":
        if n_lights > AUTO_GLOBAL_ABOVE:
            return {"mode": "global", "max": 0, "reason": f"auto: {n_lights} lights is more than {AUTO_GLOBAL_ABOVE}, so global illumination is used instead of point lights"}
        if n_lights > AUTO_HYBRID_ABOVE:
            cap = max_lights or HYBRID_MAX
            return {"mode": "hybrid", "max": cap, "reason": f"auto: {n_lights} lights is more than {AUTO_HYBRID_ABOVE}, so only the {cap} most important are kept and ambient light fills in"}
        return {"mode": "lights", "max": max_lights, "reason": f"auto: {n_lights} lights is at most {AUTO_HYBRID_ABOVE}, so every light is kept"}
    if mode == "global":
        return {"mode": "global", "max": 0, "reason": "global: no point lights, ambient + sun only"}
    if mode == "hybrid":
        return {"mode": "hybrid", "max": max_lights or HYBRID_MAX, "reason": f"hybrid: the {max_lights or HYBRID_MAX} most important lights + ambient"}
    return {"mode": "lights", "max": max_lights, "reason": "lights: " + (f"capped at {max_lights}" if max_lights else "every light kept")}


def estimate_cost(n_lights, n_shadow=0):
    """Relative render cost: 1.0 = scene with sun + ambient and no point lights. A rough guide."""
    c = 1.0 + COST_PER_LIGHT * n_lights + COST_PER_SHADOW_LIGHT * n_shadow
    label = next((lb for lim, lb in COST_LEVELS if c <= lim), "very high")
    return {"relative": round(c, 2), "label": label}


def time_of_day_flags(name):
    import foundry_lighting as fl
    t = TIME_OF_DAY.get(name)
    if not t:
        raise ValueError(f"time of day {name!r} is not one of {', '.join(TIME_OF_DAY)}")
    return {**fl.sun_to_3d(t["azimuth"], t["altitude"]), "sunDistance": 10, "timeSync": "off", "sceneTint": t["color"], "exposure": t["exposure"], "ambientLightIntensity": t["ambient"]}


def scene_flag_changes(a, mode):
    """The levels-3d-preview scene flags `set-lighting` will write. Order: time of day, then the mode's minimum ambient (global/hybrid never darker than that),
    then explicit overrides. Mode 'lights' with nothing asked writes no flag."""
    f = {}
    if getattr(a, "time_of_day", None):
        f.update(time_of_day_flags(a.time_of_day))
    floor = {"global": GLOBAL_AMBIENT, "hybrid": HYBRID_AMBIENT}.get(mode)
    if floor is not None:
        f["ambientLightIntensity"] = round(max(f.get("ambientLightIntensity", 0), floor), 3)
    if getattr(a, "ambient", None) is not None:
        f["ambientLightIntensity"] = round(float(a.ambient), 3)
    if getattr(a, "ambient_color", None):
        f["ambientLightColor"] = a.ambient_color
    if getattr(a, "sun_strength", None) is not None:
        f["exposure"] = round(float(a.sun_strength), 3)
    if getattr(a, "sun_color", None):
        f["sceneTint"] = a.sun_color
    if getattr(a, "render_scene_lights", None):
        f["renderSceneLights"] = a.render_scene_lights == "on"
    return f


def plan_lights_on_scene(scene_lights, *, mode="lights", max_lights=0, radius_scale=1.0, intensity_scale=1.0, exclude_types=(), light_shadows=None):
    """Decide, for the pipeline lights already in a scene, which stay on and what each document should look like. scene_lights = AmbientLight dicts.
    Returns {"mode", "items": [{id, data}] for upsert_many (changed lights only), "on", "off", "by_kind_on", "unchanged", ...}.
    Idempotent: the radius/intensity scale is applied to the stored base values (flags.varrenmoor.base), never compounded."""
    pipe = [l for l in scene_lights if str(((l.get("flags") or {}).get(FLAG) or {}).get("pipelineId") or "").startswith("light:")]
    # lights the GM hid by hand (hidden, not by us) are left alone and do not count against the budget
    mine = [l for l in pipe if not (l.get("hidden") and not ((l.get("flags") or {}).get(FLAG) or {}).get("budgetHidden"))]
    eff = resolve_mode(mode, len(mine), max_lights)
    excl = set(exclude_types)
    wrapped = [{"id": l["flags"][FLAG]["pipelineId"], **l} for l in mine if light_kind(l) not in excl]
    keep, _ = ([], wrapped) if eff["mode"] == "global" else select_lights(wrapped, eff["max"])
    keep_ids = {w["id"] for w in keep}
    shadow_ids = set()
    if light_shadows not in ("off", "", None):
        n = len(keep) if light_shadows == "on" else int(light_shadows)
        shadow_ids = {w["id"] for w in sorted(keep, key=lambda w: (-priority_of(light_kind(w)), light_key(w)))[:n]}
    items, by_kind_on = [], {}
    for l in mine:
        fl = (l.get("flags") or {}).get(FLAG) or {}
        pid = fl["pipelineId"]
        cfg = l.get("config") or {}
        base = fl.get("base") or {"dim": cfg.get("dim", 0), "bright": cfg.get("bright", 0), "alpha": cfg.get("alpha", 0.5)}
        off = pid not in keep_ids
        want_cfg = {"dim": round(base["dim"] * radius_scale, 2), "bright": round(base["bright"] * radius_scale, 2), "alpha": round(min(1.0, max(0.0, base["alpha"] * intensity_scale)), 3)}
        data = {}
        if not off:
            by_kind_on[light_kind(l)] = by_kind_on.get(light_kind(l), 0) + 1
        if bool(l.get("hidden")) != off:
            data["hidden"] = off
        if any(cfg.get(k) != v for k, v in want_cfg.items()):
            data["config"] = want_cfg
        want_flags = {}
        if bool(fl.get("budgetHidden")) != off:
            want_flags[FLAG] = {"budgetHidden": off}
        if not fl.get("base") and "config" in data:          # remember the unscaled values the first time a scale touches a light
            want_flags.setdefault(FLAG, {})["base"] = base
        if light_shadows is not None and bool(((l.get("flags") or {}).get(L3D) or {}).get("castShadow")) != (pid in shadow_ids):
            want_flags[L3D] = {"castShadow": pid in shadow_ids}
        if want_flags:
            data["flags"] = want_flags
        if data:
            items.append({"id": pid, "data": data})
    return {"mode": eff["mode"], "max": eff["max"], "reason": eff["reason"], "items": items, "on": len(keep), "off": len(mine) - len(keep),
            "by_kind_on": by_kind_on, "unchanged": len(mine) - len(items), "hand_hidden": len(pipe) - len(mine), "shadow": len(shadow_ids), "pipeline": len(pipe)}


def limit_new_lights(items, *, mode="lights", max_lights=0, exclude_types=(), radius_scale=1.0, intensity_scale=1.0):
    """For push-lights / push-scene-3d: thin the AmbientLight items a push would write. Returns (items, info). Over-budget lights are not created at all
    (and the push's prune deletes them from the scene)."""
    items = [i for i in items if light_kind(i) not in set(exclude_types)]
    eff = resolve_mode(mode, len(items), max_lights)
    keep = [] if eff["mode"] == "global" else select_lights(items, eff["max"])[0]
    out = []
    for i in keep:
        if radius_scale != 1.0 or intensity_scale != 1.0:
            i = json.loads(json.dumps(i))
            c = i["data"]["config"]
            c["dim"], c["bright"] = round(c["dim"] * radius_scale, 2), round(c["bright"] * radius_scale, 2)
            c["alpha"] = round(min(1.0, c["alpha"] * intensity_scale), 3)
        out.append(i)
    return out, {"mode": eff["mode"], "reason": eff["reason"], "planned": len(items), "kept": len(out), "dropped": len(items) - len(out)}


def budget_requested(a):
    """True when any budget option differs from the do-nothing default (so push-lights stays byte-identical to before when none is given)."""
    return bool(getattr(a, "max_lights", 0) or getattr(a, "exclude_types", "") or getattr(a, "light_radius_scale", 1.0) != 1.0
                or getattr(a, "light_intensity_scale", 1.0) != 1.0 or getattr(a, "lighting_mode", "lights") != "lights")


# ------------------------------------------------------------------ command
def _bridge():
    import foundry_push as fp
    return fp


def pack_light_counts(a, fp):
    """Lights the pack would create (from placements.json), by type: the estimate before anything is pushed. {} when no pack."""
    try:
        pa = argparse.Namespace(lights_placements=getattr(a, "lights_placements", None), placements=getattr(a, "placements", None), place=a.place)
        with open(fp.light_placements_path(pa), encoding="utf-8") as f:
            doc = json.load(f)
        ls = list(doc.get("lights", [])) + [x for e in doc.get("files", []) for x in e.get("lights", [])]
    except (OSError, ValueError, KeyError, TypeError):
        return {}
    out = {}
    for l in ls:
        out[l.get("type", "light")] = out.get(l.get("type", "light"), 0) + 1
    return out


def cmd_set_lighting(br, a):
    fp = _bridge()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    sc = br.call("get", uuid=a.scene_uuid)
    lights = sc.get("lights", [])
    try:
        plan = plan_lights_on_scene(lights, mode=a.lighting_mode, max_lights=a.max_lights, radius_scale=a.light_radius_scale, intensity_scale=a.light_intensity_scale,
                                    exclude_types=tuple(x for x in (a.exclude_types or "").split(",") if x), light_shadows=a.light_shadows)
        flags = scene_flag_changes(a, plan["mode"])
    except ValueError as e:
        raise fp.PushError(str(e))
    cur = ((sc.get("flags") or {}).get(L3D)) or {}
    flag_changes = {k: v for k, v in flags.items() if cur.get(k) != v}
    n_shadow_now = sum(1 for l in lights if (((l.get("flags") or {}).get(L3D) or {}).get("castShadow")) and not l.get("hidden"))
    res = {"ok": True, "applied": False, "scene": sc.get("name"), "mode": plan["mode"], "reason": plan["reason"],
           "lights_in_scene": len(lights), "pipeline_lights": plan["pipeline"], "lights_on_after": plan["on"], "lights_off_after": plan["off"], "kept_by_kind": plan["by_kind_on"],
           "hand_hidden_untouched": plan["hand_hidden"], "shadow_casters_after": plan["shadow"], "shadow_casters_now": n_shadow_now, "light_changes": len(plan["items"]),
           "light_unchanged": plan["unchanged"], "flag_changes": flag_changes, "cost_after": estimate_cost(plan["on"], plan["shadow"]),
           "cost_now": estimate_cost(sum(1 for l in lights if not l.get("hidden")), n_shadow_now), "pack_lights": pack_light_counts(a, fp)}
    fp.LOG(f"{plan['mode']}: {plan['on']} on / {plan['off']} off of {plan['pipeline']} pipeline lights, {len(plan['items'])} light change(s), {len(flag_changes)} scene flag change(s); {plan['reason']}")
    if not a.apply or a.dry_run:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    if plan["items"]:
        res["light_ops"] = br.call("upsert_many", documentName="AmbientLight", parentUuid=a.scene_uuid, items=plan["items"], prefix="light:", prune=False)
    if flag_changes:
        br.call("update", uuid=a.scene_uuid, data={"flags": {L3D: flag_changes}})
    res["applied"] = True
    return res


def add_light_args(ap):
    """The budget options, shared by set-lighting, push-lights and push-scene-3d (foundry_push.parser calls this too)."""
    ap.add_argument("--max-lights", dest="max_lights", type=int, default=0, help="light budget: keep at most N pipeline lights (0 = no limit); most important kinds first (plaza, lamp, door, hearth, window), spread by distance")
    ap.add_argument("--lighting-mode", dest="lighting_mode", choices=list(MODES), default="lights", help="lights = point lights (default), global = no point lights + ambient, hybrid = few lights + ambient, auto = choose by light count")
    ap.add_argument("--exclude-types", dest="exclude_types", default="", help="light kinds to leave out, comma list (e.g. window)")
    ap.add_argument("--light-radius-scale", dest="light_radius_scale", type=float, default=1.0, help="multiply every pipeline light's dim/bright radius")
    ap.add_argument("--light-intensity-scale", dest="light_intensity_scale", type=float, default=1.0, help="multiply every pipeline light's strength (alpha, capped at 1)")
    ap.add_argument("--light-shadows", dest="light_shadows", default=None, help="set-lighting: off | on | N = cast-shadow flag on none / every kept / the N most important lights (costly; needs client shadow quality above 0). Default: leave the flag alone")


def parser():
    ap = argparse.ArgumentParser(prog="foundry_push.py")
    ap.add_argument("cmd", choices=["set-lighting"])
    add_light_args(ap)
    ap.add_argument("--scene-uuid")
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--placements")
    ap.add_argument("--lights-placements", dest="lights_placements")
    ap.add_argument("--time-of-day", dest="time_of_day", choices=list(TIME_OF_DAY), help="set-lighting: sun position, colour, strength and ambient for dawn / noon / dusk / night")
    ap.add_argument("--ambient", type=float, help="set-lighting: global illumination strength (scene flag ambientLightIntensity, 0..1)")
    ap.add_argument("--ambient-color", dest="ambient_color", help="set-lighting: ambient colour (ambientLightColor), #rrggbb")
    ap.add_argument("--sun-strength", dest="sun_strength", type=float, help="set-lighting: sun strength (exposure, 0..3)")
    ap.add_argument("--sun-color", dest="sun_color", help="set-lighting: sun colour (sceneTint), #rrggbb")
    ap.add_argument("--render-scene-lights", dest="render_scene_lights", choices=["on", "off"], help="set-lighting: scene flag renderSceneLights (off = no 3D point lights at all)")
    ap.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None, bridge=None):
    fp = _bridge()
    a = parser().parse_args(argv)
    try:
        res = cmd_set_lighting(bridge or fp.PsBridge(), a)
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except fp.PushError as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
