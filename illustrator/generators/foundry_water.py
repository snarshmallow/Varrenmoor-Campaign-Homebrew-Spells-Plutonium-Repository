"""3D water for Foundry: install the 3D Canvas water shader on a scene's water tiles and change its parameters live.

The shader is foundry-bridge/water/vb_water.js. It runs as the tile flag flags.levels-3d-preview.onAnimation (3D Canvas calls it every frame for the tile;
scene flag enableAnimationScripts, default on), so nothing is installed in Foundry itself and no module is changed. The parameters live in
flags.varrenmoor.water = {"v": 1, "force": null | "river"..., "presets": {river: {...}, pond: {...}, lake: {...}, ocean: {...}}} on the same tile.
Which preset a mesh uses comes from its material name (VB_water_<preset>, set by the export from the water kind), or `force` for all of them.

  install-water --scene-uuid U [--place P] [--dry-run] [--enable-scripts]
        write the script and the parameters (from the panel's Water group, world/<place>/panel_state.json water3d, else the preset defaults) on every
        pipeline water tile of the scene. Idempotent: tiles that already carry the same script and parameters are left alone.
  set-water --scene-uuid U [--place P] [--preset river|pond|lake|ocean] [--force] [--set key=value ...] [--no-panel] [--dry-run]
        change the parameters live (the running shader picks them up within half a second; the tile reloads once). --preset NAME with --set edits that
        preset's values; with --force every water tile uses that preset. Keys: flow_speed wave_height wave_scale transparency depth_tint foam wind_dir
        slope_speed shallow_color deep_color. Only tiles flagged by the pipeline (flags.varrenmoor.pipelineId model:<place>:...) are touched.
push-models / push-scene-3d call decorate_items() so freshly pushed water tiles already carry the script and parameters.
Every command prints log lines, then ONE final JSON line on stdout.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
import water_presets as wpz  # noqa: E402

SCRIPT = os.path.join(REPO, "foundry-bridge", "water", "vb_water.js")
FLAG, L3D = "varrenmoor", "levels-3d-preview"
BLOCK_VERSION = 1


def script_body():
    """The onAnimation function body: vb_water.js without its full-line comments (the flag is stored in every water tile, keep it small)."""
    with open(SCRIPT, encoding="utf-8") as f:
        lines = f.read().replace("\r\n", "\n").split("\n")
    return "\n".join(l for l in lines if l.strip() and not l.lstrip().startswith("//")) + "\n"


def script_version(body=None):
    return hashlib.sha256((body or script_body()).encode()).hexdigest()[:12]


def settings_block(place, settings=None, world_root=None):
    """flags.varrenmoor.water for a place: every preset resolved (defaults + the panel's saved values) so the shader needs no table of its own."""
    s = wpz.load_place_settings(place, world_root) if settings is None else settings
    force = s.get("preset") if s.get("force") and s.get("preset") in wpz.preset_names() else None
    presets = {}
    for name in wpz.preset_names():
        p = wpz.resolve(name, (s.get("values") or {}).get(name))
        presets[name] = {k: v for k, v in p.items() if k not in ("preset",)}
    return {"v": BLOCK_VERSION, "force": force, "presets": presets}


def water_flags(place, settings=None, world_root=None):
    """The two flag fragments for a water tile: ({levels-3d-preview: {onAnimation}}, {varrenmoor: {water}})."""
    return {"onAnimation": script_body()}, {"water": settings_block(place, settings, world_root)}


def is_water_entry(e):
    return e.get("layer") == "water" or "water" in (e.get("layers") or [])


def decorate_items(items, doc, settings=None):
    """Add the shader script and parameters to the water tiles of a push (items = build_model_tiles output, doc = placements.json)."""
    place = doc.get("place")
    water_ids = {e["id"] for e in doc.get("files", []) if is_water_entry(e)}
    if not water_ids:
        return items
    l3, fl = water_flags(place, settings)
    for it in items:
        if it["id"] in water_ids:
            fs = it["data"].setdefault("flags", {})
            fs.setdefault(L3D, {}).update(l3)
            fs.setdefault(FLAG, {}).update(fl)
    return items


# ------------------------------------------------------------------ Foundry commands
def _coerce(k, v):
    spec = wpz.table()["params"].get(k)
    if k in ("shallow_color", "deep_color"):
        if wpz._color(v, None) is None:
            raise ValueError(f"{k}: not a #rrggbb colour: {v}")
        return v.lower()
    if spec is None and k != "slope_speed":
        raise ValueError(f"unknown water setting {k}; keys: {', '.join(list(wpz.table()['params']) + ['slope_speed', 'shallow_color', 'deep_color'])}")
    return float(v)


def apply_overrides(settings, preset=None, force=False, sets=()):
    """New place settings from the panel's with --preset/--force/--set applied (does not touch the file)."""
    s = json.loads(json.dumps(settings or {}))
    if preset:
        if preset not in wpz.preset_names():
            raise ValueError(f"unknown preset {preset}; one of {', '.join(wpz.preset_names())}")
        s["preset"] = preset
    if force:
        if not s.get("preset"):
            raise ValueError("--force needs --preset")
        s["force"] = True
    if sets:
        pre = s.get("preset")
        if not pre:
            raise ValueError("--set needs --preset (which preset's values to change)")
        vals = s.setdefault("values", {}).setdefault(pre, {})
        for kv in sets:
            if "=" not in kv:
                raise ValueError(f"--set expects key=value, got {kv}")
            k, v = kv.split("=", 1)
            vals[k.strip()] = _coerce(k.strip(), v.strip())
    return s


def water_tiles(br, scene_uuid, place, placements=None):
    """[(uuid, pipelineId)] of the scene's pipeline model tiles that are water (ids from placements.json when known, else the tile's layer flag)."""
    import foundry_push as fp
    rows = br.call("find_by_flag", documentName="Tile", parentUuid=scene_uuid, prefix=f"model:{place}:")
    ids = None
    pp = placements or os.path.join(REPO, "world", place, "export", "placements.json")
    if os.path.exists(pp):
        with open(pp, encoding="utf-8") as f:
            ids = {e["id"] for e in json.load(f).get("files", []) if is_water_entry(e)}
    out = []
    for r in rows:
        pid = r.get("pipelineId")
        if ids is not None:
            if pid in ids:
                out.append((r["uuid"], pid))
            continue
        d = br.call("get", uuid=r["uuid"])
        if ((d.get("flags") or {}).get(FLAG) or {}).get("layer") == "water":
            out.append((r["uuid"], pid))
    if not out:
        fp.LOG(f"no water tiles under model:{place}: in {scene_uuid}")
    return out


def _same(doc, l3, fl):
    a = ((doc.get("flags") or {}).get(L3D) or {}).get("onAnimation")
    b = ((doc.get("flags") or {}).get(FLAG) or {}).get("water")
    return a == l3["onAnimation"] and b == fl["water"]


def _run(br, a, install):
    import foundry_push as fp
    fp.require_module(br)
    scene = br.call("get", uuid=a.scene_uuid)
    place = a.place or ((scene.get("flags") or {}).get(FLAG) or {}).get("worldId")
    if not place:
        raise fp.PushError("give --place (the scene has no flags.varrenmoor.worldId)")
    settings = {} if a.no_panel else wpz.load_place_settings(place)
    settings = apply_overrides(settings, a.preset, a.force, a.set)
    l3, fl = water_flags(place, settings)
    tiles = water_tiles(br, a.scene_uuid, place, a.placements)
    res = {"ok": True, "scene": a.scene_uuid, "place": place, "script_version": script_version(l3["onAnimation"]), "script_bytes": len(l3["onAnimation"]),
           "water": fl["water"], "tiles": [], "dry_run": bool(a.dry_run), "warnings": []}
    if ((scene.get("flags") or {}).get(L3D) or {}).get("enableAnimationScripts") is False:
        if install and a.enable_scripts and not a.dry_run:
            br.call("update", uuid=a.scene_uuid, data={"flags": {L3D: {"enableAnimationScripts": True}}})
            res["scene_scripts_enabled"] = True
        else:
            res["warnings"].append("scene flag enableAnimationScripts is OFF: tile scripts will not run (pass --enable-scripts to install-water to switch it on)")
    for uuid, pid in tiles:
        doc = br.call("get", uuid=uuid)
        if _same(doc, l3, fl):
            res["tiles"].append({"uuid": uuid, "id": pid, "status": "unchanged"})
            continue
        if not a.dry_run:
            br.call("update", uuid=uuid, data={"flags": {L3D: l3, FLAG: fl}})
        res["tiles"].append({"uuid": uuid, "id": pid, "status": "would update" if a.dry_run else "updated"})
    return res


def parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["install-water", "set-water"])
    ap.add_argument("--scene-uuid", required=True)
    ap.add_argument("--place")
    ap.add_argument("--placements", help="placements.json that lists the water files (default world/<place>/export/placements.json)")
    ap.add_argument("--preset", choices=wpz.preset_names())
    ap.add_argument("--force", action="store_true", help="every water tile uses --preset (otherwise each uses the preset of its water kind)")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="set-water: a parameter of --preset, repeatable")
    ap.add_argument("--no-panel", action="store_true", help="ignore the panel's saved Water settings (preset defaults + --set only)")
    ap.add_argument("--enable-scripts", action="store_true", help="install-water: switch the scene flag enableAnimationScripts on if it is off")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None, bridge=None):
    import foundry_push as fp
    a = parser().parse_args(argv)
    try:
        res = _run(bridge or fp.PsBridge(), a, a.cmd == "install-water")
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except (fp.PushError, ValueError) as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
