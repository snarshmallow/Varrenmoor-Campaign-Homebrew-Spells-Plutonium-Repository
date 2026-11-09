"""Sun, shadows, fog and sky for 3D Canvas scenes (command `set-sun`; presets in illustrator/presets/lighting/*.json). Dry run unless --apply.

Why Dyers looked flat (FOUNDRY_3D_CANVAS_NOTES.md section 12): the sun flags WERE on the scene, but (1) the sun only casts shadows when the CLIENT setting
3D Canvas "shadowQuality" is above 0 (it was 0: no scene flag can change that), and (2) sun strength = exposure = 1 against an ambient flag of 0.35 plus the
image-based light of the skybox (exr) leaves almost no contrast. This command writes the scene flags that make the sun read: sun direction (sunPosition/sunTilt/
sunDistance, timeSync off), sun colour (sceneTint), sun strength (exposure), a LOW ambient (ambientLightIntensity/Color), shadowBias, fog (enableFog/fogColor/fogDistance),
and optionally the sky image (exr). The client shadow quality is returned as an instruction (every player sets it once; it is per browser).

Fog facts (3D Canvas 9.0.29 main.js 846-910): linear THREE.Fog(fogColor, near = 1 unit = 1000 scene px, far = fogDistance px); enableFog also replaces the scene
background with the flat fog colour (the skybox image is then only used as light, not shown), so a fog colour should match the sky horizon.
Restore: the first apply stores the previous values in flags.varrenmoor.sunBackup; `set-sun --restore` puts them back (keys that did not exist are removed).
"""
import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PRESET_DIR = os.path.join(REPO, "illustrator", "presets", "lighting")
L3D = "levels-3d-preview"
FLAG = "varrenmoor"
DEFAULT_PRESET = "afternoon"
PX_PER_UNIT = 1000.0          # scene px per three.js unit (main.js factor)
FOG_MIN_FAR = 4000            # fogDistance also becomes camera.far; below this the town itself is cut off
SHADOW_QUALITY = {0: "off", 2: "low (2048 px map)", 4: "medium (4096 px map)", 8: "high (8192 px map, may not exist on small GPUs)"}
# flags this command may write (and therefore back up / restore)
FLAG_KEYS = ("sunPosition", "sunTilt", "sunDistance", "timeSync", "sceneTint", "exposure", "ambientLightIntensity", "ambientLightColor", "shadowBias",
             "enableFog", "fogColor", "fogDistance", "exr", "skybox")
GROUND_RE = ("terrain", "roads", "plazas", "padding", "apron")


def load_presets(folder=None):
    out = {}
    for p in sorted(glob.glob(os.path.join(folder or PRESET_DIR, "*.json"))):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        out[d.get("id") or os.path.splitext(os.path.basename(p))[0]] = d
    return out


def get_preset(name, folder=None):
    ps = load_presets(folder)
    if name not in ps:
        raise ValueError(f"lighting preset {name!r} is not one of {', '.join(ps)}")
    return json.loads(json.dumps(ps[name]))


def apply_overrides(p, a):
    """Merge explicit options (argparse namespace or dict-like attrs) over a preset dict -> new preset dict."""
    g = lambda k: getattr(a, k, None)
    p = json.loads(json.dumps(p))
    for key, grp, name in (("sun_azimuth", "sun", "azimuth"), ("sun_altitude", "sun", "altitude"), ("sun_strength", "sun", "strength"), ("sun_color", "sun", "color"),
                           ("ambient", "ambient", "intensity"), ("ambient_color", "ambient", "color"), ("shadow_bias", "shadows", "bias"),
                           ("shadow_quality", "shadows", "quality"), ("fog_color", "fog", "color"), ("fog_far", "fog", "far_px")):
        if g(key) is not None:
            p.setdefault(grp, {})[name] = g(key)
    if g("shadows") in ("on", "off"):
        p.setdefault("shadows", {})["on"] = g("shadows") == "on"
    if g("fog") in ("on", "off"):
        p.setdefault("fog", {})["enabled"] = g("fog") == "on"
    return p


def preset_flags(p):
    """The levels-3d-preview scene flags that realise a preset dict (pure)."""
    import foundry_lighting as fl
    s, am, sh, fg = p.get("sun", {}), p.get("ambient", {}), p.get("shadows", {}), p.get("fog", {})
    f = {**fl.sun_to_3d(float(s.get("azimuth", 235)), float(s.get("altitude", 38))), "sunDistance": 10, "timeSync": "off",
         "sceneTint": s.get("color", "#ffffff"), "exposure": round(float(s.get("strength", 1.2)), 3),
         "ambientLightIntensity": round(float(am.get("intensity", 0.1)), 3), "ambientLightColor": am.get("color", "#ffffff"),
         "shadowBias": float(sh.get("bias", -0.0003)),
         "enableFog": bool(fg.get("enabled", False))}
    if fg.get("enabled") or fg.get("color"):
        f["fogColor"] = fg.get("color", "#c9dcee")
        f["fogDistance"] = int(max(FOG_MIN_FAR, float(fg.get("far_px", 30000))))
    return f


def shadow_notes(p):
    q = int((p.get("shadows") or {}).get("quality", 4))
    on = bool((p.get("shadows") or {}).get("on", True))
    return {"scene_flag": None, "client_setting": "3D Canvas > shadowQuality (per browser)", "recommended_quality": q if on else 0, "label": SHADOW_QUALITY.get(q, str(q)),
            "cost": "sun shadows only: measured +0.6 ms GPU (12.9 -> 13.5 ms) at quality 4 on the Dyers scene (see notes section 12)",
            "instruction": (f"Each player: Configure Settings > Module Settings > 3D Canvas > Shadow Quality = {q} (Medium is 4), or the performance preset Medium/High. "
                            "Quality 0 shows NO shadows for that player." if on else "Shadows are off in this preset.")}


def sky_flags(p, place, br_dry=True, make=False, fp=None):
    """-> (flag dict, info) for the preset's sky image `sun_<id>.webp` in world/<place>/export/skybox. Does nothing unless the image exists (or make=True builds it)."""
    sky = p.get("sky") or {}
    if not sky.get("preset"):
        return {}, {"sky": "none"}
    name = "sun_" + p["id"]
    d = os.path.join(REPO, "world", place, "export", "skybox")
    src = os.path.join(d, name + ".webp")
    info = {"sky_image": src, "sky_exists": os.path.exists(src)}
    if not os.path.exists(src) and make:
        import skybox
        h, cell = skybox.load_heights(place)
        img, _ = skybox.render(place, sky["preset"], None, 2048, 0.0, h=h, cell=cell, sun={"sun_az": float(sky.get("sun_bearing", 235)) - 90.0, "sun_el": float(sky.get("sun_alt", 30))})
        skybox.save(img, d, name, preview=True)
        info["sky_exists"] = True
        info["sky_built"] = True
        del img
    if not os.path.exists(src):
        info["sky"] = "image missing: run again with --make-sky (about 1 minute, 150 MB RAM)"
        return {}, info
    ver, path = fp.publish_file(src, f"art/{place}/skybox", name, fp.assets_dir(), dry=br_dry)
    info.update({"sky": path, "sky_version": ver})
    return {"exr": path, "skybox": ""}, info


def estimate_cost(p):
    on = bool((p.get("shadows") or {}).get("on", True)) and int((p.get("shadows") or {}).get("quality", 4)) > 0
    q = int((p.get("shadows") or {}).get("quality", 4))
    ms = 0.6 * (q / 4.0) if on else 0.0           # measured: quality 4 = +0.6 ms; map size grows with quality, rough linear guide
    return {"extra_gpu_ms": round(ms, 2), "label": "none" if not on else ("low" if ms <= 0.8 else "medium")}


def _bridge():
    import foundry_push as fp
    return fp


def _backup_of(cur, keys):
    return {k: cur.get(k, None) for k in keys}


def cmd_set_sun(br, a):
    fp = _bridge()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    sc = br.call("get", uuid=a.scene_uuid)
    cur = ((sc.get("flags") or {}).get(L3D)) or {}
    mine = (sc.get("flags") or {}).get(FLAG) or {}
    if a.restore:
        bk = mine.get("sunBackup")
        if not bk:
            raise fp.PushError("this scene has no stored sun backup (set-sun --apply has not been run on it)")
        upd = {k: (v if v is not None else None) for k, v in bk.items() if cur.get(k) != v}
        data_l3d = {(k if v is not None else "-=" + k): v for k, v in upd.items()}
        res = {"ok": True, "applied": False, "scene": sc.get("name"), "restore": True, "flag_changes": upd}
        if a.apply and not a.dry_run:
            fp.require_module(br)
            if data_l3d:
                br.call("update", uuid=a.scene_uuid, data={"flags": {L3D: data_l3d}})
            br.call("update", uuid=a.scene_uuid, data={"flags": {FLAG: {"-=sunBackup": None}}})
            res["applied"] = True
        else:
            res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    try:
        p = apply_overrides(get_preset(a.preset or DEFAULT_PRESET), a)
    except ValueError as e:
        raise fp.PushError(str(e))
    flags = preset_flags(p)
    sky_info = {}
    if a.sky != "off":
        sf, sky_info = sky_flags(p, a.place, br_dry=not (a.apply and not a.dry_run), make=bool(a.make_sky), fp=fp)
        flags.update(sf)
    changes = {k: v for k, v in flags.items() if cur.get(k) != v}
    res = {"ok": True, "applied": False, "scene": sc.get("name"), "preset": p["id"], "description": p.get("description", ""), "flags": flags, "flag_changes": changes,
           "shadows": shadow_notes(p), "cost": estimate_cost(p), "sky": sky_info}
    if flags.get("enableFog"):
        res["note_fog"] = "fog is on: 3D Canvas then shows the flat fog colour as the sky (the sky image still lights the scene); pick a fog colour equal to the sky horizon."
    # ground tiles: flat ground does not need to cast shadows (default is casting ON for every tile)
    tile_ops = []
    if a.ground_cast in ("on", "off"):
        want = a.ground_cast == "on"
        for t in sc.get("tiles", []):
            name = ((t.get("flags") or {}).get(L3D) or {}).get("model3d") or ""
            if any(k in os.path.basename(name).lower() for k in GROUND_RE):
                if ((t.get("flags") or {}).get(L3D) or {}).get("castShadow", True) != want:
                    tile_ops.append((t.get("_id") or t.get("id"), want))
    res["ground_tiles_to_change"] = len(tile_ops)
    if not a.apply or a.dry_run:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    data = dict(changes)
    if "sunBackup" not in mine and changes:     # first apply: remember what was there (None = key did not exist)
        br.call("update", uuid=a.scene_uuid, data={"flags": {FLAG: {"sunBackup": _backup_of(cur, FLAG_KEYS)}}})
    if data:
        br.call("update", uuid=a.scene_uuid, data={"flags": {L3D: data}})
    for tid, want in tile_ops:
        br.call("update", uuid=f"{a.scene_uuid}.Tile.{tid}", data={"flags": {L3D: {"castShadow": want}}})
    res["applied"] = True
    return res


def add_sun_args(ap):
    ap.add_argument("--scene-uuid")
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--preset", help="lighting preset id (illustrator/presets/lighting/*.json): dawn morning noon afternoon dusk night foggy_morning warm_sunset; default afternoon")
    ap.add_argument("--sun-azimuth", dest="sun_azimuth", type=float, help="sun compass bearing, degrees (0 N, 90 E, 180 S, 270 W)")
    ap.add_argument("--sun-altitude", dest="sun_altitude", type=float, help="sun height above the horizon, degrees")
    ap.add_argument("--sun-strength", dest="sun_strength", type=float, help="sun strength (scene flag exposure, also the tone-mapping exposure)")
    ap.add_argument("--sun-color", dest="sun_color", help="sun colour #rrggbb (sceneTint)")
    ap.add_argument("--ambient", type=float, help="ambient strength 0..1 (ambientLightIntensity); keep low (0.05-0.15) so the sun reads")
    ap.add_argument("--ambient-color", dest="ambient_color", help="ambient colour #rrggbb")
    ap.add_argument("--shadows", choices=["on", "off"], help="sun shadows on/off (informational + client instruction; the scene has no flag)")
    ap.add_argument("--shadow-quality", dest="shadow_quality", type=int, choices=[0, 2, 4, 8], help="recommended client shadow quality (cost hint only)")
    ap.add_argument("--shadow-bias", dest="shadow_bias", type=float, help="scene flag shadowBias (default preset -0.0003; more negative = less acne, more peter-panning)")
    ap.add_argument("--fog", choices=["on", "off"], help="scene flag enableFog")
    ap.add_argument("--fog-color", dest="fog_color", help="fog colour #rrggbb (also the flat sky colour while fog is on)")
    ap.add_argument("--fog-far", dest="fog_far", type=int, help="fog far distance in scene px (fogDistance); fog starts at 1000 px, linear. 7000 = dense, 30000 = faint")
    ap.add_argument("--sky", choices=["preset", "off"], default="preset", help="write the preset's sky image (exr) if it exists; off = leave the sky alone")
    ap.add_argument("--make-sky", dest="make_sky", action="store_true", help="build the preset's sky image from skybox.py first (about 1 minute)")
    ap.add_argument("--ground-cast", dest="ground_cast", choices=["leave", "on", "off"], default="leave", help="castShadow flag of terrain / roads / plazas / padding tiles (default casting is on)")
    ap.add_argument("--restore", action="store_true", help="put the scene's sun/fog/sky flags back to what they were before the first set-sun --apply")
    ap.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
    ap.add_argument("--dry-run", action="store_true")


def parser():
    ap = argparse.ArgumentParser(prog="foundry_push.py")
    ap.add_argument("cmd", choices=["set-sun"])
    add_sun_args(ap)
    return ap


def main(argv=None, bridge=None):
    fp = _bridge()
    a = parser().parse_args(argv)
    try:
        res = cmd_set_sun(bridge or fp.PsBridge(), a)
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except fp.PushError as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
