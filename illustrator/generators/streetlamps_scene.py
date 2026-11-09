"""`foundry_push.py set-streetlamps`: switch the street lamps of an EXISTING 3D scene on or off and retune their lights without a re-export or re-push.

  foundry_push.py set-streetlamps --scene-uuid U [--on | --off] [--light-config F | --kelvin K --dim FT --bright FT --intensity X --flicker on|off --shadows on|off] [--apply]

* --off / --on: the streetlamps tile (flags.varrenmoor.layer streetlamps) and every lamp AmbientLight (flags.varrenmoor.type lamp) are set hidden / visible. Lights the budget
  hid (flags.varrenmoor.budgetHidden) stay hidden when switched on: the budget (`set-lighting`) decides those. Nothing is deleted.
* light options: colour (kelvin or #rrggbb through --light-config), radius, strength, flicker (animation torch / none) and the per-light shadow flag are written to the lamp lights only.
  A value of 0 or an omitted option leaves that setting as it is.
Only documents flagged by the pipeline are touched; dry run unless --apply; idempotent (a second run changes nothing). Settings of the lamps themselves (style, spacing, side)
need `streetlamps.py apply` and a push of the layer.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FLAG = "varrenmoor"
L3D = "levels-3d-preview"


def _fp():
    import foundry_push as fp
    return fp


def lamp_tiles(scene):
    return [t for t in scene.get("tiles", []) if (((t.get("flags") or {}).get(FLAG) or {}).get("layer") == "streetlamps"
                                                    and str(((t.get("flags") or {}).get(FLAG) or {}).get("pipelineId") or "").startswith("model:"))]


def lamp_lights(scene):
    out = []
    for l in scene.get("lights", []):
        f = (l.get("flags") or {}).get(FLAG) or {}
        if f.get("type") == "lamp" and str(f.get("pipelineId") or "").startswith("light:"):
            out.append(l)
    return out


def light_wanted(cfg_light, kelvin=None):
    """Values to write on a lamp light from the light settings of a streetlamps config: {color, dim, bright, alpha, animation, castShadow}; only the ones that were asked for."""
    import streetlamps as sl
    want = {}
    lc = cfg_light or {}
    if lc.get("color"):
        want["color"] = lc["color"]
    elif lc.get("kelvin"):
        want["color"] = sl.kelvin_to_hex(lc["kelvin"])
    for k, dst in (("dim_ft", "dim"), ("bright_ft", "bright")):
        if lc.get(k):
            want[dst] = float(lc[k])
    if lc.get("intensity"):
        want["alpha"] = min(0.9, max(0.1, float(lc["intensity"])))
    if lc.get("flicker") is not None:
        want["animation"] = "torch" if lc["flicker"] else None
    if lc.get("shadows") is not None:
        want["castShadow"] = bool(lc["shadows"])
    return want


def plan(scene, on=None, want=None):
    """-> {"tile_updates": [(uuid, data)], "light_items": [{id, data}], counts}. Pure: tested without Foundry."""
    want = want or {}
    tiles, lights = lamp_tiles(scene), lamp_lights(scene)
    tu = []
    if on is not None:
        for t in tiles:
            if bool(t.get("hidden")) == bool(on):
                tu.append((t.get("uuid") or t.get("_id"), {"hidden": not on}))
    li = []
    for l in lights:
        f = (l.get("flags") or {}).get(FLAG) or {}
        data = {}
        if on is False and not l.get("hidden"):
            data["hidden"] = True
            data.setdefault("flags", {})[FLAG] = {"lampHidden": True}           # marks "hidden by the lamp toggle" so --on never un-hides a light the GM or the budget hid
        elif on is True and f.get("lampHidden"):
            if not f.get("budgetHidden"):
                data["hidden"] = False
            data.setdefault("flags", {})[FLAG] = {"lampHidden": False}
        cfg = l.get("config") or {}
        cw = {}
        for k in ("color", "dim", "bright", "alpha"):
            if k in want and cfg.get(k) != want[k]:
                cw[k] = want[k]
        if "animation" in want and ((cfg.get("animation") or {}).get("type") or None) != want["animation"]:
            cw["animation"] = {**(cfg.get("animation") or {"speed": 2, "intensity": 2}), "type": want["animation"]}
        if cw:
            data["config"] = cw
        if "castShadow" in want and bool(((l.get("flags") or {}).get(L3D) or {}).get("castShadow")) != want["castShadow"]:
            data.setdefault("flags", {}).setdefault(L3D, {})["castShadow"] = want["castShadow"]
        if data:
            li.append({"id": f["pipelineId"], "data": data})
    return {"tile_updates": tu, "light_items": li, "tiles": len(tiles), "lights": len(lights)}


def cmd(br, a):
    fp = _fp()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    on = True if a.on else False if a.off else None
    cfg = {}
    if a.light_config:
        with open(a.light_config, encoding="utf-8") as f:
            doc = json.load(f)
        cfg = dict(doc.get("light") or {})
    for k, v in (("kelvin", a.kelvin), ("dim_ft", a.dim), ("bright_ft", a.bright), ("intensity", a.intensity)):
        if v is not None:
            cfg[k] = v
    for k, v in (("flicker", a.flicker), ("shadows", a.shadows)):
        if v is not None:
            cfg[k] = v == "on"
    sc = br.call("get", uuid=a.scene_uuid)
    pl = plan(sc, on, light_wanted(cfg))
    res = {"ok": True, "applied": False, "scene": sc.get("name"), "lamp_tiles": pl["tiles"], "lamp_lights": pl["lights"], "tile_changes": len(pl["tile_updates"]), "light_changes": len(pl["light_items"]),
           "on": on}
    fp.LOG(f"streetlamps: {pl['tiles']} tile(s), {pl['lights']} lamp light(s); {len(pl['tile_updates'])} tile change(s), {len(pl['light_items'])} light change(s)")
    if pl["tiles"] == 0 and pl["lights"] == 0:
        res["warning"] = "this scene has no street lamp tile or lamp lights (apply the lamps, push the streetlamps layer and push-lights first)"
    if not a.apply:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    for u, data in pl["tile_updates"]:
        br.call("update", uuid=u, data=data)
    if pl["light_items"]:
        res["light_ops"] = br.call("upsert_many", documentName="AmbientLight", parentUuid=a.scene_uuid, items=pl["light_items"], prefix="light:", prune=False)
    res["applied"] = True
    return res


def parser():
    ap = argparse.ArgumentParser(prog="foundry_push.py")
    ap.add_argument("cmd", choices=["set-streetlamps"])
    ap.add_argument("--scene-uuid")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true", help="show the street lamp tile and lamp lights")
    g.add_argument("--off", action="store_true", help="hide the street lamp tile and lamp lights")
    ap.add_argument("--light-config", dest="light_config", help="JSON with a `light` block (the streetlamps config the panel writes): colour, radius, strength, flicker, shadows")
    ap.add_argument("--kelvin", type=float, help="lamp light colour temperature K")
    ap.add_argument("--dim", type=float, help="lamp light dim radius ft")
    ap.add_argument("--bright", type=float, help="lamp light bright radius ft")
    ap.add_argument("--intensity", type=float, help="lamp light strength 0..1")
    ap.add_argument("--flicker", choices=["on", "off"])
    ap.add_argument("--shadows", choices=["on", "off"])
    ap.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
    return ap


def main(argv=None, bridge=None):
    fp = _fp()
    a = parser().parse_args(argv)
    try:
        res = cmd(bridge or fp.PsBridge(), a)
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except (fp.PushError, ValueError, OSError) as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
