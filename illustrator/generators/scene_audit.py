"""Duplicate / stale pipeline model tiles of a Foundry scene (pure functions on a scene document, no bridge writes).

One representation rule: every source model (a building id, a layer, a foliage cell) is drawn by exactly ONE pipeline tile. A plan (placements.json of a
pack: individual entity files or a merged layer pack) decides which tile that is; a tile of ours (flags.varrenmoor.pipelineId = model:<place>:...) that
draws the same source ids under a different pipeline id is SUPERSEDED and is removed by push-models, and `scene-audit` lists all such problems with a repair plan.
Only documents carrying our pipeline flag are ever considered; tiles you made yourself and the padding apron (no layer) are never touched."""
import re

FLAG = "varrenmoor"
L3D = "levels-3d-preview"
POS_TOL_PX = 2.0
ELEV_TOL_FT = 0.05
PRUNE_LIMIT = 5          # push-models refuses to delete more than this many stale tiles without --prune


def src(i):
    """Source model of a member id: bld_house_041_int_f0 / bld_house_041_roof -> bld_house_041 (a building and its parts are one source)."""
    m = re.match(r"^([a-z]+_[a-z]+_\d+)(_|$)", i)
    return m.group(1) if m else i


def tile_uuid(scene, t):
    return t.get("uuid") or f"{scene.get('uuid', 'Scene.?')}.Tile.{t.get('_id') or t.get('id')}"


def info(scene, t):
    f = (t.get("flags") or {}).get(FLAG) or {}
    m3 = ((t.get("flags") or {}).get(L3D) or {}).get("model3d") or ""
    v = re.search(r"_v(\d+)\.[a-z0-9]+$", m3)
    return {"uuid": tile_uuid(scene, t), "pid": f.get("pipelineId"), "layer": f.get("layer"), "ids": sorted({src(x) for x in f.get("ids") or []}), "sha": f.get("sha256"),
            "model": m3, "version": int(v.group(1)) if v else None, "stem": re.sub(r"_v\d+(\.[a-z0-9]+)$", r"\1", m3.split("/")[-1]) if m3 else None,
            "x": t.get("x"), "y": t.get("y"), "w": t.get("width"), "elev": t.get("elevation"), "hidden": bool(t.get("hidden"))}


def our_tiles(scene, place=None):
    """Model tiles of the pipeline (pipelineId model:<place>:*)."""
    pre = f"model:{place}:" if place else "model:"
    return [i for i in (info(scene, t) for t in scene.get("tiles", [])) if i["pid"] and i["pid"].startswith(pre)]


def plan_index(items):
    """Pushed items -> (set of pipeline ids, {source id: tile pipeline id}, set of layers)."""
    pids, by_src, layers = set(), {}, set()
    for it in items:
        pids.add(it["id"])
        f = (it["data"].get("flags") or {}).get(FLAG) or {}
        if f.get("layer"):
            layers.add(f["layer"])
        for s in {src(x) for x in f.get("ids") or []}:
            by_src.setdefault(s, it["id"])
    return pids, by_src, layers


def representation(items):
    """Which tile draws each source model of a plan: {layer: {"tiles": n, "merged": [tile ids drawing > 1 model], "individual": n, "sources": n}}."""
    out = {}
    for it in items:
        f = (it["data"].get("flags") or {}).get(FLAG) or {}
        r = out.setdefault(f.get("layer") or "?", {"tiles": 0, "sources": 0, "merged": []})
        n = len({src(x) for x in f.get("ids") or []})
        r["tiles"] += 1
        r["sources"] += n
        if n > 1:
            r["merged"].append(it["id"])
    for r in out.values():
        r["representation"] = "merged" if r["merged"] else "individual"
    return out


def check_plan_unique(items):
    """A plan must draw every source id once; returns the list of problems (empty = ok)."""
    seen, bad = {}, []
    for it in items:
        for s in {src(x) for x in ((it["data"].get("flags") or {}).get(FLAG) or {}).get("ids") or []}:
            if s in seen and seen[s] != it["id"]:
                bad.append(f"{s} is drawn by both {seen[s]} and {it['id']}")
            seen.setdefault(s, it["id"])
    return bad


def stale_tiles(scene, items, place):
    """Tiles of ours that a push of `items` must replace -> [(uuid, pipelineId, reason)].
    superseded: draws a source id the plan draws with another tile (the other representation: merged layer <-> individual buildings, split <-> merge foliage).
    not-in-plan: same layer as the plan's tiles but not in it (e.g. a house that no longer exists). Tiles of other layers (padding apron, foliage when pushing
    the layers) are never stale."""
    pids, by_src, layers = plan_index(items)
    out = []
    for t in our_tiles(scene, place):
        if t["pid"] in pids:
            continue
        if any(s in by_src and by_src[s] != t["pid"] for s in t["ids"]):
            out.append((t["uuid"], t["pid"], "superseded"))
        elif t["layer"] in layers:
            out.append((t["uuid"], t["pid"], "not-in-plan"))
    return out


def duplicate_ids(scene, place=None):
    seen, out = {}, []
    for t in our_tiles(scene, place):
        if t["pid"] in seen:
            out.append(t)
        seen.setdefault(t["pid"], t)
    return out


def audit(scene, items, place, local_newest=None):
    """Read-only audit of `scene` against the plan `items` (build_model_tiles output of every intended placements file).
    local_newest(model3d path) -> newest published version number or None. Returns {"findings", "delete", "repush", "keep", "ok"}."""
    want = {it["id"]: it for it in items}
    pids, by_src, layers = plan_index(items)
    fi, delete, repush, keep = [], {}, set(), []
    ours = our_tiles(scene, place)
    dup = {t["uuid"] for t in duplicate_ids(scene, place)}
    for t in ours:
        if t["uuid"] in dup:
            fi.append({"kind": "duplicate_id", "tile": t["pid"], "uuid": t["uuid"], "msg": "second tile with the same pipeline id"})
            delete[t["uuid"]] = (t["pid"], "duplicate pipeline id")
    for uuid, pid, why in stale_tiles(scene, items, place):
        if uuid in delete:
            continue
        t = next(x for x in ours if x["uuid"] == uuid)
        if why == "superseded":
            over = sorted({by_src[s] for s in t["ids"] if s in by_src})
            fi.append({"kind": "duplicate_representation", "tile": pid, "uuid": uuid, "msg": f"draws {len(t['ids'])} source model(s) that the plan draws with {over[:3]}"})
        else:
            fi.append({"kind": "orphan", "tile": pid, "uuid": uuid, "msg": f"layer {t['layer']} tile that is not in the plan"})
        delete[uuid] = (pid, why)
    for t in ours:
        if t["uuid"] in delete:
            continue
        w = want.get(t["pid"])
        if not w:
            keep.append((t["uuid"], t["pid"], "not part of the audited plan (other layer or pack)"))
            continue
        d, bad = w["data"], []
        if t["x"] is not None and (abs(t["x"] - d["x"]) > POS_TOL_PX or abs(t["y"] - d["y"]) > POS_TOL_PX):
            bad.append({"kind": "moved", "tile": t["pid"], "uuid": t["uuid"], "msg": f"tile at ({t['x']}, {t['y']}), plan says ({d['x']}, {d['y']}): dx {d['x'] - t['x']:+g}, dy {d['y'] - t['y']:+g} px"})
        if t["elev"] is not None and abs(t["elev"] - d["elevation"]) > ELEV_TOL_FT:
            bad.append({"kind": "elevation", "tile": t["pid"], "uuid": t["uuid"], "msg": f"elevation {t['elev']} ft, plan says {d['elevation']} ft"})
        psha = ((d.get("flags") or {}).get(FLAG) or {}).get("sha256")
        if psha and t["sha"] and psha != t["sha"]:
            bad.append({"kind": "model_changed", "tile": t["pid"], "uuid": t["uuid"], "msg": "model bytes differ from the plan's (sha256)"})
        if local_newest and t["version"] is not None:
            nv = local_newest(t["model"])
            if nv and nv > t["version"]:
                bad.append({"kind": "old_version", "tile": t["pid"], "uuid": t["uuid"], "msg": f"model v{t['version']:03d}, newest published v{nv:03d}"})
        if bad:
            fi += bad
            repush.add(t["uuid"])
        else:
            keep.append((t["uuid"], t["pid"], "matches the plan"))
    missing = sorted(pids - {t["pid"] for t in ours})
    for m in missing:
        fi.append({"kind": "missing", "tile": m, "uuid": None, "msg": "in the plan, not in the scene (push-models creates it)"})
    return {"findings": fi, "delete": [(u,) + v for u, v in delete.items()], "repush": sorted(repush), "keep": keep, "missing": missing, "ok": not fi}


def repair_plan(res, scene_uuid, plan_args):
    """Plain-text repair plan for an audit result."""
    L = []
    if res["ok"]:
        return ["scene is clean: nothing to repair"]
    L.append(f"DELETE {len(res['delete'])} tile(s) (ours only, flagged pipelineId):")
    for u, pid, why in res["delete"]:
        L.append(f"  - {pid}  [{why}]  {u}")
    if res["repush"]:
        L.append(f"RE-PUSH {len(res['repush'])} tile(s) whose position/elevation/model differs from the plan (an id-keyed push updates them in place).")
    if res["missing"]:
        L.append(f"CREATE {len(res['missing'])} missing tile(s) (the same push creates them).")
    L.append(f"KEEP {len(res['keep'])} tile(s).")
    L.append(f"Then: foundry_push.py push-scene-3d --scene-uuid {scene_uuid} {plan_args} --prune   (delete list above is exactly what --prune removes; dry-run first)")
    return L
