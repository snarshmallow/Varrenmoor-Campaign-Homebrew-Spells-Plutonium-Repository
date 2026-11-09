"""Collision flag per layer + sight/sound/light walls for the 3D Canvas scenes (commands `set-collision`, `push-walls`; helpers used by foundry_push.py).

What the 3D Canvas `collision` tile flag does (3D Canvas 9.0.29 source, read on Vega; details in FOUNDRY_3D_CANVAS_NOTES.md section 10):
  * a tile with collision true puts its (sight) mesh into the "move" raycast set (InteractionManager.generateSightCollisions) and into the set a dragged token is
    raycast against (buildCollisionGeos). So: tokens snap to the HEIGHT of collision tiles under the cursor (terrain relief, roads, floors); a player's token
    cannot be moved through a collision mesh when the scene flag object3dSight is on; tokens ground themselves downward against it; the 3D door click is enabled.
  * it costs no render time. Meshes are BVH-accelerated (three-mesh-bvh), the BVH and the cloned sight mesh exist whether the flag is on or off, a move check
    is one ray. The only flag-dependent costs are two array builds (cheap) and, for glTF with node extras (doors), a per-node clone on each tile update.
  * `sight` (a different flag, left OFF) is the expensive one: it sends the whole mesh to the 3D vision worker.
Collision default (COLLISION_DEFAULT): ON for buildings bridges roads plazas walls fences props fields terrain; OFF for foliage water roofs (a roof or tree canopy
under the cursor would catch the dragged token from a top-down camera; water has no standing surface).

Walls: Foundry Wall documents tagged flags.varrenmoor.pipelineId `wall3d:<kind>:<entity>:<n>` (the 2D push-scene walls are `wall:`; the two never touch each other).
Profiles (WALL_PROFILES): buildings full block (move/sight/light/sound normal) with exterior doors as door walls; walls (town walls) full; fences movement only;
trees limited sight+sound (a ray that passes through a stand crosses two limited walls = blocked, a ray from outside to the edge is not), movement free;
water limited sound only (a limited sight loop would make every 40 ft river opaque across; override with --wall-profile water:sight=10).
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FLAG = "varrenmoor"
L3D = "levels-3d-preview"
NONE, LIMITED, NORMAL = 0, 10, 20

COLLISION_LAYERS = ("padding", "terrain", "water", "roads", "plazas", "fields", "fences", "walls", "bridges", "buildings", "roofs", "foliage", "props", "streetlamps")
COLLISION_DEFAULT = ("terrain", "roads", "plazas", "fields", "fences", "walls", "bridges", "buildings", "props", "streetlamps")
# `sight` tile flag = the mesh blocks token vision, fog exploration, AmbientLight and AmbientSound polygons (3D Canvas vision worker, see out/vision_walls_research.md).
# Buildings (an open model door lets it through) and town walls block; tree/foliage chunks block at eye height (trunks, hedges) while tokens still walk through (collision off).
# OFF: terrain/roads/plazas/fields/bridges/props/padding (ground), water, fences (open), roofs (the GM hides them, they sit above eye height, a hidden roof must not block).
SIGHT_DEFAULT = ("buildings", "walls", "foliage")

WALL_LAYERS = ("buildings", "walls", "fences", "trees", "water")
WALL_DEFAULT = ("buildings", "walls")      # opt-in fallback (tile sight does the work in 3D scenes); fences/trees/water walls only when named with --wall-layers
WALL_PROFILES = {
    "buildings": {"move": NORMAL, "sight": NORMAL, "light": NORMAL, "sound": NORMAL},
    "walls": {"move": NORMAL, "sight": NORMAL, "light": NORMAL, "sound": NORMAL},
    "fences": {"move": NORMAL, "sight": NONE, "light": NONE, "sound": NONE},
    "trees": {"move": NONE, "sight": LIMITED, "light": NONE, "sound": LIMITED},
    "water": {"move": NONE, "sight": NONE, "light": NONE, "sound": LIMITED},
}
TREE_LINK_FT = 30.0         # trees closer than this belong to one stand
TREE_MIN = 5                # a stand needs this many trees (one tree is not a wall)
TREE_PAD_FT = 8.0           # hull grown by this much
MAX_RING_PTS = 14           # trees: hull vertices per stand
SIMPLIFY_FT = {"buildings": 0.4, "walls": 1.0, "fences": 1.5, "water": 4.0}
DOOR_GAP_MIN_FT = 2.0


# ------------------------------------------------------------------ collision
def parse_collision(spec, default=None):
    """None/''/'default' -> the default set. 'all' / 'none'. 'a,b,c' = exactly these layers. '+water,-terrain' (or 'default,+water') edits the default (`default` = tuple to start from, collision's by default)."""
    on = set(COLLISION_DEFAULT if default is None else default)
    if spec is None or str(spec).strip() in ("", "default"):
        return on
    toks = [t.strip() for t in str(spec).split(",") if t.strip()]
    if toks == ["all"]:
        return set(COLLISION_LAYERS)
    if toks == ["none"]:
        return set()
    if not any(t[0] in "+-" or t == "default" for t in toks):
        on = set()
    for t in toks:
        if t in ("default", "all", "none") and t != "default":
            raise ValueError("'all' / 'none' stand alone")
        if t == "default":
            continue
        name = t.lstrip("+-")
        if name not in COLLISION_LAYERS:
            raise ValueError(f"unknown collision layer {name!r} (known: {', '.join(COLLISION_LAYERS)})")
        (on.discard if t[0] == "-" else on.add)(name)
    return on


def parse_sight(spec):
    """Same grammar as parse_collision, default SIGHT_DEFAULT."""
    return parse_collision(spec, SIGHT_DEFAULT)


def parse_lod(spec):
    """'terrain=0.5,roads=0.6' -> {layer: complexity}. 3D Canvas sightMeshComplexity (1 = full mesh, lower = simplified collision proxy; costs load time)."""
    out = {}
    for t in [x for x in str(spec or "").split(",") if x.strip()]:
        k, _, v = t.partition("=")
        if k.strip() not in COLLISION_LAYERS or not 0.05 <= float(v) <= 1:
            raise ValueError(f"bad collision lod {t!r}")
        out[k.strip()] = float(v)
    return out


def collision_for(layers, on):
    """True when every layer a tile draws has collision on (a mixed tile with roofs/foliage in it stays off)."""
    layers = [l for l in (layers if isinstance(layers, (list, tuple, set)) else [layers]) if l]
    return bool(layers) and all(l in on for l in layers)


def tile_layer(tile):
    """Pipeline layer of a pushed tile document (flags.varrenmoor.layer), None for tiles the pipeline did not create or mixed tiles."""
    f = (tile.get("flags") or {}).get(FLAG) or {}
    pid = f.get("pipelineId") or ""
    if not pid.startswith("model:"):
        return None
    l = f.get("layer")
    return l if l in COLLISION_LAYERS else None


def collision_updates(scene, on, lod=None, sight=None):
    """[(tile uuid, name, layer, wanted collision, current collision, lod, wanted sight, current sight)] for the pipeline tiles of a scene document that need a change; plus the skipped list.
    sight = set of layers whose tiles get sight true (None = leave the sight flag alone)."""
    ups, skipped, same = [], [], 0
    for t in scene.get("tiles", []):
        l = tile_layer(t)
        pid = ((t.get("flags") or {}).get(FLAG) or {}).get("pipelineId") or ""
        if not pid.startswith("model:"):
            continue
        if l is None:
            skipped.append(pid)
            continue
        fl = (t.get("flags") or {}).get(L3D) or {}
        want, cur = l in on, fl.get("collision")
        lw, lc = (lod or {}).get(l), fl.get("sightMeshComplexity")
        sw, sc_ = ((l in sight) if sight is not None else None), fl.get("sight")
        if cur is want and (lw is None or lc == lw) and (sw is None or sc_ is sw):
            same += 1
            continue
        u = t.get("uuid") or f"{scene['uuid']}.Tile.{t.get('_id') or t.get('id')}"
        ups.append((u, pid, l, want, cur, lw, sw, sc_))
    return ups, skipped, same


# ------------------------------------------------------------------ geometry
def _dp_open(pts, tol):
    """Douglas-Peucker on an open polyline (iterative)."""
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = pts[a]
        dx, dy = pts[b][0] - ax, pts[b][1] - ay
        L = math.hypot(dx, dy) or 1e-9
        best, bi = -1.0, -1
        for i in range(a + 1, b):
            d = abs((pts[i][0] - ax) * dy - (pts[i][1] - ay) * dx) / L
            if d > best:
                best, bi = d, i
        if best > tol:
            keep.add(bi)
            stack += [(a, bi), (bi, b)]
    return [pts[i] for i in sorted(keep)]


def _dp(pts, tol, closed):
    if len(pts) < 3:
        return list(pts)
    if not closed:
        return _dp_open(pts, tol)
    far = max(range(len(pts)), key=lambda i: math.dist(pts[i], pts[0]))
    a = _dp_open(pts[:far + 1], tol)
    b = _dp_open(pts[far:] + [pts[0]], tol)
    return a[:-1] + b[:-1]


def simplify_ring(pts, tol):
    """Closed ring (no repeated end point): drop duplicates, merge collinear vertices within tol."""
    pts = [tuple(map(float, p[:2])) for p in pts]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    out = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
    return _dp(out, tol, True) if len(out) >= 4 else out


def simplify_line(pts, tol):
    pts = [tuple(map(float, p[:2])) for p in pts]
    out = [p for i, p in enumerate(pts) if i == 0 or math.dist(p, pts[i - 1]) > 1e-6]
    return _dp(out, tol, False) if len(out) >= 3 else out


def hull(points):
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts
    cr = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cr(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cr(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return lo[:-1] + up[:-1]


def clusters(points, link):
    """Single-linkage clusters of points closer than `link` (grid hash, O(n))."""
    cell = {}
    for i, p in enumerate(points):
        cell.setdefault((int(p[0] // link), int(p[1] // link)), []).append(i)
    seen, out = set(), []
    for i in range(len(points)):
        if i in seen:
            continue
        seen.add(i)
        stack, grp = [i], []
        while stack:
            k = stack.pop()
            grp.append(k)
            cx, cy = int(points[k][0] // link), int(points[k][1] // link)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for j in cell.get((cx + dx, cy + dy), ()):
                        if j not in seen and math.dist(points[k], points[j]) <= link:
                            seen.add(j)
                            stack.append(j)
        out.append(grp)
    return out


def tree_rings(points, link=TREE_LINK_FT, min_trees=TREE_MIN, pad=TREE_PAD_FT, max_pts=MAX_RING_PTS):
    """Tree points -> [ring]: one convex hull (grown by pad, at most max_pts vertices) per stand of >= min_trees trees."""
    rings = []
    for grp in clusters(points, link):
        if len(grp) < min_trees:
            continue
        h = hull([points[i] for i in grp])
        if len(h) < 3:
            continue
        cx, cy = sum(p[0] for p in h) / len(h), sum(p[1] for p in h) / len(h)
        g = []
        for x, y in h:
            d = math.hypot(x - cx, y - cy) or 1.0
            g.append((x + (x - cx) / d * pad, y + (y - cy) / d * pad))
        tol = 1.0
        while len(g) > max_pts and tol < 200:
            g = simplify_ring(g, tol)
            tol *= 1.6
        rings.append(g)
    return rings


# ------------------------------------------------------------------ walls
class Plan:
    def __init__(self, calib):
        self.c = calib
        self.items, self.counts = [], {}

    def px(self, p):
        c = self.c
        return (c["sceneX"] + (p[0] - c["x0"]) * c["ppf"], c["sceneY"] + (p[1] - c["y0"]) * c["ppf"])

    def seg(self, layer, eid, n, a, b, prof, door=None, extra=None):
        if math.dist(a, b) < 0.25:
            return
        (ax, ay), (bx, by) = self.px(a), self.px(b)
        d = {"c": [round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1)], **prof, "dir": 0, "door": 1 if door else 0, "ds": 0}
        if door:
            d["flags"] = {FLAG: {"doorId": door}}
        self.items.append({"id": f"wall3d:{layer}:{eid}:{n}", "data": d})
        self.counts[layer] = self.counts.get(layer, 0) + 1

    def ring(self, layer, eid, pts, prof, doors=()):
        """Closed ring as segments; every door = a gap on the nearest edge, made a door wall (closed)."""
        n = len(pts)
        cuts = {}                                   # edge index -> [(t0, t1, doorId)]
        for door in doors:
            px_, w = door["point"], max(float(door.get("width_ft", 3.5)), DOOR_GAP_MIN_FT)
            best = None
            for i in range(n):
                a, b = pts[i], pts[(i + 1) % n]
                dx, dy = b[0] - a[0], b[1] - a[1]
                L2 = dx * dx + dy * dy
                if L2 < 1e-9:
                    continue
                t = max(0.0, min(1.0, ((px_[0] - a[0]) * dx + (px_[1] - a[1]) * dy) / L2))
                d = math.dist((a[0] + t * dx, a[1] + t * dy), px_)
                if best is None or d < best[0]:
                    best = (d, i, t, math.sqrt(L2))
            if best is None:
                continue
            _, i, t, L = best
            h = min(w, L * 0.9) / 2 / L
            t0, t1 = max(0.0, t - h), min(1.0, t + h)
            cuts.setdefault(i, []).append((t0, t1, door["id"]))
        k = 0
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            lerp = lambda t: (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)  # noqa: E731
            t = 0.0
            for t0, t1, did in sorted(cuts.get(i, [])):
                if t0 < t:
                    continue
                self.seg(layer, eid, k, lerp(t), lerp(t0), prof)
                k += 1
                self.seg(layer, eid, k, lerp(t0), lerp(t1), prof, door=did)
                k += 1
                t = t1
            self.seg(layer, eid, k, lerp(t), b, prof)
            k += 1

    def line(self, layer, eid, pts, prof, closed=False, door=False):
        seq = list(pts) + ([pts[0]] if closed else [])
        for i in range(len(seq) - 1):
            self.seg(layer, eid, i, seq[i], seq[i + 1], prof, door=eid if door else None)


def _items(base, name):
    p = os.path.join(base, "entities", name + ".json")
    if not os.path.isfile(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f).get("items", [])


LOW_PLANTS = ("bush", "shrub", "hedge", "grass", "flower", "reed", "fern", "crop")      # not tall enough to block sight


def tree_points(place_dir, foliage_json=None):
    """Tree positions (ft): --foliage-json file, else world/<place>/foliage.json items, else scatter/foliage.json instances, else the pack's foliage entities. Low plants are skipped."""
    cands = [(foliage_json, "items")] if foliage_json else []
    cands += [(os.path.join(place_dir, rel), key) for rel, key in (("foliage.json", "items"), (os.path.join("scatter", "foliage.json"), "instances"), (os.path.join("export", "entities", "foliage.json"), "items"))]
    for p, key in cands:
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                its = json.load(f).get(key) or []
            pts = [(float(i["x"]), float(i["y"])) for i in its if "x" in i and "y" in i and not any(w in str(i.get("species", "")).lower() for w in LOW_PLANTS)]
            if pts:
                return pts
    return []


def build_walls(place_dir, calib, layers, profiles=None, foliage_json=None):
    """-> (items for upsert_many prefix 'wall3d:', {layer: count}). place_dir = world/<place>; reads <place_dir>/export/entities/*.json."""
    base = os.path.join(place_dir, "export")
    prof = {k: dict(v) for k, v in WALL_PROFILES.items()}
    for k, v in (profiles or {}).items():
        prof.setdefault(k, {}).update(v)
    plan = Plan(calib)
    layers = set(layers)
    if "buildings" in layers:
        for b in sorted(_items(base, "buildings"), key=lambda b: b["id"]):
            poly = b.get("polygon")
            if not poly or len(poly) < 3:
                continue
            ring = simplify_ring(poly, SIMPLIFY_FT["buildings"])
            doors = [d for d in (b.get("doors") or []) if d.get("kind") == "exterior" and d.get("point")]
            plan.ring("buildings", b["id"], ring, prof["buildings"], doors)
    for layer in ("walls", "fences"):
        if layer not in layers:
            continue
        for e in sorted(_items(base, layer), key=lambda e: e["id"]):
            pts = [tuple(p[:2]) for p in (e.get("points") or e.get("polygon") or [])]
            if len(pts) < 2:
                continue
            closed = bool(e.get("closed")) or (e.get("polygon") is not None and "points" not in e)
            gate = "gate" in str(e.get("kind", "")).lower()
            pts = simplify_ring(pts, SIMPLIFY_FT[layer]) if closed else simplify_line(pts, SIMPLIFY_FT[layer])
            plan.line(layer, e["id"], pts, prof[layer], closed=closed, door=gate)
    if "water" in layers:
        for w in sorted(_items(base, "water"), key=lambda w: w["id"]):
            poly = w.get("polygon")
            if poly and len(poly) >= 3:
                plan.ring("water", w["id"], simplify_ring(poly, SIMPLIFY_FT["water"]), prof["water"])
    if "trees" in layers:
        for i, r in enumerate(tree_rings(tree_points(place_dir, foliage_json))):
            plan.ring("trees", f"stand{i:03d}", r, prof["trees"])
    return plan.items, plan.counts


def parse_profiles(specs):
    """['water:sight=10,sound=10', ...] -> {'water': {'sight': 10, 'sound': 10}}"""
    out = {}
    for s in specs or []:
        layer, _, rest = s.partition(":")
        if layer not in WALL_PROFILES:
            raise ValueError(f"unknown wall layer {layer!r}")
        for kv in rest.split(","):
            k, _, v = kv.partition("=")
            if k not in ("move", "sight", "light", "sound") or int(v) not in (0, 10, 20):
                raise ValueError(f"bad wall profile {s!r} (keys move/sight/light/sound, values 0 none, 10 limited, 20 normal)")
            out.setdefault(layer, {})[k] = int(v)
    return out


# ------------------------------------------------------------------ commands
def _bridge():
    import foundry_push as fp
    return fp


def cmd_set_collision(br, a):
    fp = _bridge()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    try:
        on, lod = parse_collision(a.collision), parse_lod(a.collision_lod)
        sight = None if a.sight == "keep" else parse_sight(a.sight)
    except ValueError as e:
        raise fp.PushError(str(e))
    sc = br.call("get", uuid=a.scene_uuid)
    sc.setdefault("uuid", a.scene_uuid)
    ups, skipped, same = collision_updates(sc, on, lod, sight)
    fp.LOG(f"collision on for: {', '.join(sorted(on)) or 'nothing'}; sight on for: {', '.join(sorted(sight)) if sight is not None else '(unchanged)'}; {len(ups)} tile(s) to change, {same} already right, {len(skipped)} skipped (not a single-layer pipeline tile)")
    res = {"ok": True, "applied": False, "layers_on": sorted(on), "sight_on": sorted(sight) if sight is not None else None, "changes": len(ups), "unchanged": same, "skipped": skipped,
           "plan": [{"pipelineId": p, "layer": l, "collision": w, "was": c, "sight": sw, "sight_was": sc_} for _, p, l, w, c, _, sw, sc_ in ups]}
    if not a.apply or a.dry_run:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    for u, _, _, want, _, lw, sw, _s in ups:
        data = {f"flags.{L3D}.collision": want}
        if sw is not None:
            data[f"flags.{L3D}.sight"] = sw
        if lw is not None:
            data[f"flags.{L3D}.sightMeshComplexity"] = lw
        br.call("update", uuid=u, data=data)
    res["applied"] = True
    return res


def cmd_push_walls(br, a):
    fp = _bridge()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    layers = [x for x in (a.wall_layers or ",".join(WALL_DEFAULT)).split(",") if x and x != "none"]
    bad = [x for x in layers if x not in WALL_LAYERS]
    if bad:
        raise fp.PushError(f"unknown wall layer(s) {bad} (known: {', '.join(WALL_LAYERS)}, none)")
    try:
        profiles = parse_profiles(a.wall_profile)
    except ValueError as e:
        raise fp.PushError(str(e))
    sc = br.call("get", uuid=a.scene_uuid)
    calib = ((sc.get("flags") or {}).get(FLAG) or {}).get("calib")
    if not calib:
        raise fp.PushError("the scene carries no varrenmoor calibration (push models / push-scene first)")
    place = a.place or calib.get("place")
    items, counts = build_walls(os.path.join(fp.REPO, "world", place), calib, layers, profiles, a.foliage_json)
    old = [w for w in sc.get("walls", []) if (((w.get("flags") or {}).get(FLAG) or {}).get("pipelineId") or "").startswith("wall3d:")]
    keep = {i["id"] for i in items}
    stale = [w for w in old if w["flags"][FLAG]["pipelineId"] not in keep]
    fp.LOG(f"{len(items)} wall(s) planned {counts}; {len(old)} existing pipeline 3D wall(s), {len(stale)} stale")
    res = {"ok": True, "applied": False, "walls": len(items), "by_layer": counts, "existing": len(old), "stale": len(stale), "layers": layers,
           "doors": sum(1 for i in items if i["data"]["door"])}
    if not a.apply or a.dry_run:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    r = br.call("upsert_many", documentName="Wall", parentUuid=a.scene_uuid, items=items, prefix="wall3d:", prune=True)
    res.update(applied=True, wall_ops=r)
    return res


def door_plan(scene):
    """Reconcile wall doors with model doors. -> [("wall", wall uuid-id, ds)] / [("tile", tile id, doorId, "ds")]. The model state wins when the tile lists the door; a wall door
    the model does not know yet (flag absent) is written to the model only when it is not closed."""
    tiles = scene.get("tiles", [])
    model = {}
    for t in tiles:
        for did, v in (((t.get("flags") or {}).get(L3D) or {}).get("modelDoors") or {}).items():
            model[did] = (t, str((v or {}).get("ds", "0")))
    plan = []
    for w in scene.get("walls", []):
        did = ((w.get("flags") or {}).get(FLAG) or {}).get("doorId")
        if not did or not (w.get("door") or 0) > 0:
            continue
        cur = int(w.get("ds") or 0)
        if did in model:
            want = {"1": 1, "2": 2}.get(model[did][1], 0)
            if want != cur:
                plan.append(("wall", w.get("_id") or w.get("id"), did, want, cur))
        elif cur != 0:
            owner = next((t for t in tiles if any(did.startswith(str(i) + "_") for i in (((t.get("flags") or {}).get(FLAG) or {}).get("ids") or []))), None)
            if owner is not None:
                plan.append(("tile", owner.get("_id") or owner.get("id"), did, str(cur), None))
    return plan


def cmd_sync_doors(br, a):
    fp = _bridge()
    if not a.scene_uuid:
        raise fp.PushError("give --scene-uuid")
    sc = br.call("get", uuid=a.scene_uuid)
    plan = door_plan(sc)
    fp.LOG(f"{len(plan)} door(s) out of step")
    res = {"ok": True, "applied": False, "changes": len(plan),
           "plan": [{"set": k, "id": i, "door": d, "to": t, "was": w} for k, i, d, t, w in plan]}
    if not a.apply or a.dry_run:
        res["note"] = "dry run: nothing written, repeat with --apply"
        return res
    fp.require_module(br)
    for k, i, d, t, _ in plan:
        if k == "wall":
            br.call("update", uuid=f"{a.scene_uuid}.Wall.{i}", data={"ds": t})
        else:
            br.call("update", uuid=f"{a.scene_uuid}.Tile.{i}", data={f"flags.{L3D}.modelDoors.{d}.ds": t})
    res["applied"] = True
    return res


def cmd_install_door_sync(br, a):
    """Create/update the 'Door sync' Script macro (id macro:door_sync) from foundry_macros/door_sync.js."""
    fp = _bridge()
    with open(os.path.join(os.path.dirname(HERE), "foundry_macros", "door_sync.js"), encoding="utf-8") as f:
        data = {"name": "Door sync: wall doors <-> model doors (toggle)", "type": "script", "img": "icons/svg/door.svg", "scope": "global", "command": f.read()}
    if a.dry_run:
        return {"ok": True, "dry_run": True, "macros": ["macro:door_sync"]}
    fp.require_module(br)
    r = br.call("upsert_by_flag", documentName="Macro", id="macro:door_sync", data=data)
    return {"ok": True, "macros": [r.get("uuid")]}


def parser():
    ap = argparse.ArgumentParser(prog="foundry_push.py")
    ap.add_argument("cmd", choices=["set-collision", "push-walls", "sync-doors", "install-door-sync"])
    ap.add_argument("--scene-uuid")
    ap.add_argument("--place")
    ap.add_argument("--collision", help="set-collision: layers with collision on: default | all | none | a,b,c | +water,-terrain")
    ap.add_argument("--sight", default=None, help="set-collision: layers whose tiles block vision, light and sound: default (buildings,walls,foliage) | all | none | a,b | +water,-foliage | keep (leave the flag alone)")
    ap.add_argument("--collision-lod", dest="collision_lod", help="set-collision: simplified collision proxies, e.g. terrain=0.5 (3D Canvas sightMeshComplexity)")
    ap.add_argument("--wall-layers", dest="wall_layers", help="push-walls: comma list of " + ",".join(WALL_LAYERS) + " (default buildings,walls; 'none' removes every pipeline 3D wall)")
    ap.add_argument("--wall-profile", dest="wall_profile", action="append", default=[], help="push-walls: layer:key=val,... (values 0/10/20), e.g. water:sight=10")
    ap.add_argument("--foliage-json", dest="foliage_json", help="push-walls: foliage.json with the tree positions (default world/<place>/foliage.json, scatter/foliage.json or the pack entities)")
    ap.add_argument("--apply", action="store_true", help="really write (default is a dry run)")
    ap.add_argument("--dry-run", action="store_true")
    return ap


def main(argv=None, bridge=None):
    fp = _bridge()
    a = parser().parse_args(argv)
    try:
        res = {"set-collision": cmd_set_collision, "push-walls": cmd_push_walls, "sync-doors": cmd_sync_doors, "install-door-sync": cmd_install_door_sync}[a.cmd](bridge or fp.PsBridge(), a)
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except fp.PushError as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
