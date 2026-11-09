"""Bridge maker: detect crossings (floating decks, rivers, roads over roads), build parametric bridges sized to the clearance below, write them
into the world pack as entities of type `bridges`.

  python illustrator/generators/bridge_maker.py presets
  python illustrator/generators/bridge_maker.py fix-elevations --place bridgehollow__dyers_walk_local        # repair clipped streets' per-vertex road bed (the floating-road bug)
  python illustrator/generators/bridge_maker.py detect --place P [--pack DIR] [--float-ft 4] [--level-ft 3] [--out report.json]
  python illustrator/generators/bridge_maker.py apply  --place P [--pack DIR] [--only id,id] [--preset NAME] [--no-export]   # detect -> world/P/bridges.json -> pack entities
  python illustrator/generators/bridge_maker.py inject --place P [--pack DIR]                                    # re-apply world/P/bridges.json to a freshly exported pack
  python illustrator/generators/bridge_maker.py remove --place P --id brg_x_1
  python illustrator/generators/bridge_maker.py audit --place P [--out audit.json]                               # every foot / the deck of the saved bridges vs the terrain TRIANGLES
  python illustrator/generators/bridge_maker.py sample --preset stone_arch --span-ft 60 --out out.glb          # a free-standing bridge for the style sheet

Every function prints/returns JSON-able data. Units: feet in files, metres inside the meshes (bridge_geo). See illustrator/out/bridges_notes.md.
"""
import argparse
import datetime
import glob
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WORLD = os.path.join(REPO, "world")
PRESETS = os.path.join(HERE, "..", "presets", "bridges")
FT = 0.3048
LIFT_M = 0.25                       # same lift as worldpack_mesh.LIFT["roads"]: the deck ends meet the road ribbons exactly
SCHEMA = 1
DEFAULTS = {"float_ft": 4.0, "level_ft": 3.0, "min_span_ft": 8.0, "merge_gap_ft": 24.0, "abut_margin_ft": 5.0, "bank_ft": 3.0, "sample_ft": 2.0,
            "ground_over_ft": 0.5, "max_lift_ft": 6.0, "lift_slope": 0.12, "ramp_slope": 0.10}


def log(m):
    print(m, file=sys.stderr, flush=True)


# ------------------------------------------------------------------ presets
def list_presets():
    out = []
    for f in sorted(glob.glob(os.path.join(PRESETS, "*.json"))):
        out.append(_jload(f))
    return out


def load_preset(name):
    p = os.path.join(PRESETS, name + ".json")
    if not os.path.exists(p):
        raise KeyError(f"unknown bridge preset {name!r}; have {[x['id'] for x in list_presets()]}")
    return _jload(p)


def validate_preset(pr):
    errs = []
    for k in ("id", "family", "params", "materials"):
        if k not in pr:
            errs.append(f"{pr.get('id')}: missing {k}")
    if pr.get("family") not in ("arch", "flat", "timber", "log", "covered", "rope"):
        errs.append(f"{pr.get('id')}: family {pr.get('family')}")
    for k in ("width_ft", "max_span_ft"):
        if not (pr.get("params", {}).get(k, 0) > 0):
            errs.append(f"{pr.get('id')}: params.{k} must be > 0")
    return errs


# ------------------------------------------------------------------ road geometry
def road_arrays(points):
    P = np.asarray(points, float)
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P[:, :2], axis=0).T))])
    return s, P[:, 0], P[:, 1], P[:, 2]


def road_at(points, s_ft):
    s, x, y, z = road_arrays(points)
    return float(np.interp(s_ft, s, x)), float(np.interp(s_ft, s, y)), float(np.interp(s_ft, s, z))


def trim_runs(points, gaps):
    """Road polyline pieces left after removing the gap intervals [{s0_ft, s1_ft}] (arc length along the road); cut points are interpolated."""
    s, x, y, z = road_arrays(points)
    L = s[-1]
    cuts = sorted((max(0.0, g["s0_ft"]), min(L, g["s1_ft"])) for g in gaps)
    keep, a = [], 0.0
    for c0, c1 in cuts:
        if c0 - a > 0.5:
            keep.append((a, c0))
        a = max(a, c1)
    if L - a > 0.5:
        keep.append((a, L))
    runs = []
    for k0, k1 in keep:
        ss = [k0] + [v for v in s if k0 < v < k1] + [k1]
        runs.append([[float(np.interp(v, s, x)), float(np.interp(v, s, y)), float(np.interp(v, s, z))] for v in ss])
    return runs


def conformed_heights(pack, h=None, falloff_ft=10.0):
    """worldpack.road_conformed_heights with the bridge spans removed: the terrain under a bridge keeps its own shape (gully, river bed)."""
    import worldpack as wp
    lines = []
    for r in pack.list("roads"):
        if r.get("bridge"):
            continue
        runs = trim_runs(r["points"], r["gaps"]) if r.get("gaps") else [r["points"]]
        for run in runs:
            if len(run) < 2:
                continue
            lines.append((np.array([p[:2] for p in run], float), np.array([p[2] for p in run], float), np.full(len(run), r["width_ft"] / 2)))
    return wp._conform(pack.heights if h is None else h, pack.cell_ft, lines, falloff_ft, "set")


def final_heights(pack, graded=True):
    """The terrain the bridges are planned against = what worldpack_mesh.build_parts builds. With road grading on (the default) the roads are draped on the
    carved terrain and the terrain is NOT conformed to them, so the carved heights are the truth; `graded=False` is the old conformed terrain (road grading off)."""
    import worldpack as wp
    h = wp.carved_heights(pack)
    return h if graded else conformed_heights(pack, h)


# ------------------------------------------------------------------ detection
def _poly_runs(mask, s, min_len):
    runs, i, n = [], 0, len(mask)
    while i < n:
        if mask[i]:
            j = i
            while j + 1 < n and mask[j + 1]:
                j += 1
            runs.append([float(s[i]), float(s[j])])
            i = j + 1
        else:
            i += 1
    return runs


def _merge(runs, gap):
    out = []
    for a, b in sorted(runs):
        if out and a - out[-1][1] <= gap:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def detect(pack, float_ft=None, level_ft=None, min_span_ft=None, h_raw=None, classes=None):
    """Crossings of the pack's roads: floating decks over a depression ('gully'), roads over water ('water'), roads over roads at a different level
    ('road'), and the pack's existing deck-only bridge roads ('existing'). Returns a list of dicts (see the report fields in bridges_notes.md)."""
    import worldpack as wp
    from shapely.geometry import LineString, Point
    D = dict(DEFAULTS)
    if float_ft is not None:
        D["float_ft"] = float_ft
    if level_ft is not None:
        D["level_ft"] = level_ft
    if min_span_ft is not None:
        D["min_span_ft"] = min_span_ft
    h = wp.carved_heights(pack) if h_raw is None else h_raw
    cell = pack.cell_ft
    roads = [r for r in pack.list("roads")]
    found = []
    water = pack.list("water")
    for r in roads:
        pts = np.asarray(r["points"], float)
        s, x, y, z = road_arrays(pts)
        L = float(s[-1])
        if L < 4:
            continue
        ss = np.arange(0.0, L + 1e-6, D["sample_ft"])
        if ss[-1] < L - 1e-6:
            ss = np.append(ss, L)
        px, py, pz = np.interp(ss, s, x), np.interp(ss, s, y), np.interp(ss, s, z)
        g = np.array([wp.bilinear(h, cell, a, b) for a, b in zip(px, py)])
        above = pz - g
        runs = []
        if r.get("bridge"):                                    # the pack's deck-only bridge road: the whole road becomes the modelled bridge
            runs.append(("existing", [0.0, L], {}))
        # floating deck: runs where the road bed is more than float_ft above the (carved, unconformed) terrain
        for a, b in ([] if r.get("bridge") else _poly_runs(above > D["float_ft"], ss, 0)):
            ia, ib = int(np.searchsorted(ss, a)), int(np.searchsorted(ss, b))
            while ia > 0 and above[ia] > D["float_ft"] * 0.45:
                ia -= 1
            while ib < len(ss) - 1 and above[ib] > D["float_ft"] * 0.45:
                ib += 1
            runs.append(("gully", [float(ss[ia]), float(ss[ib])], {}))
        # water
        ls = LineString(np.c_[px, py])
        for w in water:
            from shapely.geometry import Polygon
            pg = Polygon(w["polygon"]).buffer(0) if w.get("polygon") else None
            if pg is None or pg.is_empty:
                continue
            it = ls.intersection(pg)
            segs = [it] if it.geom_type == "LineString" else list(getattr(it, "geoms", []))
            for sg in segs:
                if sg.geom_type != "LineString" or sg.length < 1.0:
                    continue
                a, b = ls.project(Point(sg.coords[0])), ls.project(Point(sg.coords[-1]))
                a, b = min(a, b), max(a, b)
                zs = None
                if w.get("surface_elevations_ft") and w.get("centerline"):
                    mid = ls.interpolate(0.5 * (a + b))
                    k = int(np.argmin([math.hypot(c[0] - mid.x, c[1] - mid.y) for c in w["centerline"]]))
                    zs = w["surface_elevations_ft"][k]
                elif w.get("level_ft") is not None:
                    zs = w["level_ft"]
                runs.append(("water", [a - D["bank_ft"] - D["abut_margin_ft"], b + D["bank_ft"] + D["abut_margin_ft"]],
                             {"water": w["id"], "wet": [a, b], "surface_ft": zs, "freeboard_ft": None}))
        # roads over / under roads
        for o in roads:
            if o["id"] == r["id"] or o.get("bridge") or r.get("bridge"):
                continue
            lo = LineString([p[:2] for p in o["points"]])
            it = ls.intersection(lo)
            pts_i = [it] if it.geom_type == "Point" else [q for q in getattr(it, "geoms", []) if q.geom_type == "Point"]
            for q in pts_i:
                sa = ls.project(q)
                sb = lo.project(q)
                za = float(np.interp(sa, s, z))
                so, zo = road_arrays(o["points"]), None
                zb = float(np.interp(sb, so[0], so[3]))
                wa, wb = r["width_ft"], o["width_ft"]
                # a junction, not a crossing: the other road ends (or this one does) close to the intersection
                if min(sa, L - sa) < wa or min(sb, so[0][-1] - sb) < wb:
                    continue
                dz = za - zb
                if abs(dz) <= D["level_ft"]:
                    continue
                if dz < 0:
                    continue                                    # the other road is the upper one; it gets its own entry when it is `r`
                da = np.array(lo.interpolate(min(sb + 1.0, lo.length)).coords[0]) - np.array(lo.interpolate(max(sb - 1.0, 0.0)).coords[0])
                db = np.array(ls.interpolate(min(sa + 1.0, L)).coords[0]) - np.array(ls.interpolate(max(sa - 1.0, 0.0)).coords[0])
                cosang = abs(float(da @ db)) / (np.linalg.norm(da) * np.linalg.norm(db) + 1e-9)
                ang = math.degrees(math.acos(min(1.0, cosang)))
                sin_t = max(math.sin(math.radians(ang)), 0.25)
                cw = max(12.0, wb + 4.0)
                half = cw / 2 / sin_t + wb / 2 * 0 + D["abut_margin_ft"]
                runs.append(("road", [sa - half, sa + half], {"under": o["id"], "u_ft": sa, "angle_deg": ang, "under_z_ft": zb, "under_width_ft": wb, "dz_ft": dz}))
        if not runs:
            continue
        # merge overlapping runs of any type into one span per road; remember what is under it
        runs.sort(key=lambda t: t[1][0])
        groups = []
        for t, (a, b), info in runs:
            a, b = max(0.0, a), min(L, b)
            if groups and a - groups[-1]["s1"] <= D["merge_gap_ft"]:
                groups[-1]["s1"] = max(groups[-1]["s1"], b)
                groups[-1]["items"].append((t, info))
            else:
                groups.append({"s0": a, "s1": b, "items": [(t, info)]})
        for n, gp in enumerate(groups, 1):
            a, b = gp["s0"], gp["s1"]
            if b - a < D["min_span_ft"]:
                mid = 0.5 * (a + b)
                a, b = max(0.0, mid - D["min_span_ft"] / 2), min(L, mid + D["min_span_ft"] / 2)
            types = [t for t, _ in gp["items"]]
            typ = "water" if "water" in types else ("road" if "road" in types else ("existing" if "existing" in types else "gully"))
            m = (ss >= a) & (ss <= b)
            found.append(dict(type=typ, road=r["id"], s0_ft=round(a, 2), s1_ft=round(b, 2), span_ft=round(b - a, 2), n=n, road_class=r["class"], width_ft=r["width_ft"],
                              ring=r.get("ring"), deck_above_ground_ft=round(float(above[m].max()), 2) if m.any() else 0.0,
                              others=[dict(kind=t, **i) for t, i in gp["items"] if t not in ("gully", "existing")],
                              clearance_needed=dict(w_ft=12.0, h_ft=8.0)))
    # stable ordering and ids
    cnt = {}
    for c in found:
        c["span_ft"] = round(c["s1_ft"] - c["s0_ft"], 2)
        c["id"] = bridge_id(c["road"], cnt.setdefault(c["road"], 0) + 1)
        cnt[c["road"]] += 1
        if c["type"] == "water":
            c["clearance_needed"] = dict(kind="water", freeboard_ft=4.0, note="water surface + banks + freeboard")
        elif c["type"] == "road":
            o = c["others"][0]
            c["clearance_needed"] = dict(w_ft=max(12.0, o["under_width_ft"] + 4.0), h_ft=8.0, projected_w_ft=round(max(12.0, o["under_width_ft"] + 4.0) / max(math.sin(math.radians(o["angle_deg"])), 0.25), 1))
    return found


def bridge_id(road_id, n):
    return f"brg_{road_id}_{n}"


# ------------------------------------------------------------------ preset choice
RUSTIC_CULTURES = ("scandinavian", "fantasy_generic")          # log / timber building traditions (rough logs, log trusses)
BRICK_CULTURES = ("english", "danish_german")                   # brick towns
COVERED_CULTURES = ("danish_german", "english", "scandinavian")  # covered timber bridges are a northern timber tradition
RUSTIC_RINGS = ("outskirts", "commoner", "wild", "rural", "farm", "farms")
BUILT_UP_RINGS = ("authority", "merchant", "market")
LOG_MAX_SPAN_FT = 70.0            # rough_log trestles
TRUSS_MAX_SPAN_FT = 60.0          # wooden_truss
ARCH_MAX_SPAN_FT = 26.0           # one stone / brick arch (longer crossings get several)
ROPE_MIN_DROP_FT = 16.0           # a rope bridge only makes sense over a real drop


def choose_preset(c, road_class=None, culture=None, override=None):
    """Pick a bridge preset for one crossing. General rules, no place names. Inputs: span (ft), clearance below the deck (c['deck_above_ground_ft']: how
    far the ground drops, the water depth is not known here), road class, crossing type, ring (district) and culture (c['culture'] or `culture`).
      paths/footpaths: short -> plank_footbridge (rough_log in rustic settings), long deep gaps -> rope_plank, mid spans -> rough_log (rustic) or wooden_truss
      lanes/alleys:    short -> flat_cut_stone, long -> wooden_truss (up to 60 ft), longer -> covered_timber (timber cultures) or stone_arch
      streets/roads:   short water crossings -> flat_cut_stone; very tall or very long crossings -> covered_timber (stone arches stop at 90 ft clearance);
                       rustic cultures cross 26-60 ft gaps on wooden_truss; otherwise stone_arch, brick_arch in brick cultures / built-up rings
    `override` (a preset id) wins over everything (the panel's manual choice)."""
    if override:
        return override
    cls = (road_class or c.get("road_class") or "street")
    cls = "street" if cls == "bridge" else cls
    span = float(c["span_ft"])
    drop = float(c.get("deck_above_ground_ft") or 0.0)
    ring = str(c.get("ring") or "")
    cul = culture or c.get("culture") or ""
    water = c.get("type") == "water"
    rustic = cul in RUSTIC_CULTURES or ring in RUSTIC_RINGS
    h3 = int(hashlib.md5(c["id"].encode()).hexdigest(), 16) % 3
    if cls in ("path", "footpath"):
        if span <= 18:
            return "rough_log" if rustic and span <= 26 and h3 != 0 else "plank_footbridge"
        if drop >= ROPE_MIN_DROP_FT and span >= 28:
            return "rope_plank"
        if rustic and span <= LOG_MAX_SPAN_FT:
            return "rough_log"
        if span <= TRUSS_MAX_SPAN_FT:
            return "wooden_truss"
        return "rope_plank" if drop >= ROPE_MIN_DROP_FT else "covered_timber"
    if cls in ("lane", "alley"):
        if span <= 16:
            return "flat_cut_stone"
        if span > TRUSS_MAX_SPAN_FT or drop > 90:
            return "covered_timber" if cul in COVERED_CULTURES or drop > 90 else "stone_arch"
        return "wooden_truss" if water and span > 40 else ("wooden_truss" if rustic and span > 26 else "stone_arch")
    if water and span <= 14:
        return "flat_cut_stone"
    if drop > 90 or span > 90:                                    # beyond a stone arch's clearance / a sensible stack of arches
        return "covered_timber"
    if cul in COVERED_CULTURES and span > 60 and water:
        return "covered_timber"
    if rustic and 26 < span <= TRUSS_MAX_SPAN_FT and ring not in BUILT_UP_RINGS:
        return "wooden_truss"
    brick = ring in BUILT_UP_RINGS or (cul in BRICK_CULTURES and h3 != 0) or h3 == 0
    return "brick_arch" if brick else "stone_arch"


# ------------------------------------------------------------------ building the crossing context (spec)
def _chord(road, s0, s1):
    x0, y0, z0 = road_at(road["points"], s0)
    x1, y1, z1 = road_at(road["points"], s1)
    return (x0, y0, z0), (x1, y1, z1)


def deck_baseline(us, deck_ft, family):
    """The deck line the mesh builder starts from (feet): arches keep the road's own profile (plus a hump that only raises it); the other families run straight
    between the ends on spans under 120 ft."""
    us, deck_ft = np.asarray(us, float), np.asarray(deck_ft, float)
    if family == "arch" or us[-1] >= 120:
        return deck_ft
    return np.linspace(deck_ft[0], deck_ft[-1], len(us))


def compute_lift(us, base_ft, gh_ft, margin_ft=None, slope=None, max_ft=None):
    """How far (ft) the deck must be raised so it clears the highest terrain under its footprint by `margin_ft` everywhere (terrain never pokes through the
    deck at the abutments or on a hillside), as a slope-limited profile so the deck stays smooth. Returns (lift list, clipped_ft): clipped_ft > 0 when the
    cap (max_lift_ft) was hit and terrain still rises above the deck (the caller warns)."""
    margin = DEFAULTS["ground_over_ft"] if margin_ft is None else margin_ft
    slope = DEFAULTS["lift_slope"] if slope is None else slope
    cap = DEFAULTS["max_lift_ft"] if max_ft is None else max_ft
    us = np.asarray(us, float)
    need = np.maximum(0.0, np.asarray(gh_ft, float) + margin - np.asarray(base_ft, float))
    lift = np.zeros_like(need)
    for j in np.nonzero(need > 1e-6)[0]:
        lift = np.maximum(lift, need[j] - slope * np.abs(us - us[j]))
    lift = np.maximum(lift, 0.0)
    over = float(max(0.0, lift.max() - cap)) if len(lift) else 0.0
    return np.minimum(lift, cap), over


def deck_with_lift_ft(ctx):
    """Profile of the deck (feet) including the terrain-clearance lift stored in the entity (absent in old entities = 0)."""
    d = Prof(ctx["deck"])
    if not ctx.get("deck_lift"):
        return d
    lf = Prof(ctx["deck_lift"])
    us = np.array(sorted(set([u for u, _ in ctx["deck"]] + [u for u, _ in ctx["deck_lift"]])))
    return Prof([(u, float(d(u) + lf(u))) for u in us])


def make_entity(pack, c, h_final, preset=None, overrides=None, seed=None, provenance=None):
    """A bridge entity (feet) from one detected crossing: chord, deck ends from the road, ground profile under the deck from the final terrain."""
    import worldpack as wp
    road = pack.get(c["road"])
    pr_name = preset or choose_preset(c)
    pr = load_preset(pr_name)
    P = dict(pr["params"])
    P.update({k: v for k, v in (overrides or {}).items() if v is not None})
    (x0, y0, z0), (x1, y1, z1) = _chord(road, c["s0_ft"], c["s1_ft"])
    L = math.hypot(x1 - x0, y1 - y0)
    d = np.array([x1 - x0, y1 - y0]) / L
    lf = np.array([d[1], -d[0]])                          # left of travel in the y-down world frame (x east, y south)
    W = float(overrides["width_ft"]) if overrides and overrides.get("width_ft") is not None else max(float(P["width_ft"]) if road["width_ft"] < 1 else float(road["width_ft"]), 4.0)
    n = max(8, int(math.ceil(L / 2.0)))
    us = np.linspace(0.0, L, n + 1)
    gh, gl = [], []
    for u in us:
        vals = [wp.bilinear(h_final, pack.cell_ft, x0 + d[0] * u + lf[0] * v, y0 + d[1] * u + lf[1] * v) for v in np.linspace(-W / 2 - 2.0, W / 2 + 2.0, 9)]
        gh.append(float(max(vals)))
        gl.append(float(min(vals)))
    # deck: the road's own profile along the span (so the ends meet the ribbons), plus the lift the ribbons have
    s_r, _, _, z_r = road_arrays(road["points"])
    zr = np.interp(c["s0_ft"] + us * (c["s1_ft"] - c["s0_ft"]) / L, s_r, z_r)
    deck = [[round(float(u), 3), round(float(z + LIFT_M / FT), 3)] for u, z in zip(us, zr)]
    base = deck_baseline(us, [d_[1] for d_ in deck], pr["family"])
    lift, over = compute_lift(us, base, gh)
    deck_lift = [[round(float(u), 3), round(float(v), 3)] for u, v in zip(us, lift)] if lift.max() > 0.02 else []
    others = []
    for o in c.get("others", []):
        if o["kind"] == "water":
            wa, wb = o["wet"]
            u0, u1 = (wa - c["s0_ft"]) * L / (c["s1_ft"] - c["s0_ft"]), (wb - c["s0_ft"]) * L / (c["s1_ft"] - c["s0_ft"])
            others.append(dict(kind="water", id=o["water"], u0_ft=round(u0, 2), u1_ft=round(u1, 2), surface_ft=o.get("surface_ft")))
        elif o["kind"] == "road":
            u = (o["u_ft"] - c["s0_ft"]) * L / (c["s1_ft"] - c["s0_ft"])
            others.append(dict(kind="road", id=o["under"], u_ft=round(u, 2), angle_deg=round(o["angle_deg"], 1), z_ft=round(o["under_z_ft"] + LIFT_M / FT, 2), width_ft=o["under_width_ft"]))
    ent = {
        "id": c["id"], "name": f"Bridge on {road.get('name', c['road'])}" + (f" ({c['n']})" if c.get("n", 1) > 1 else ""), "kind": "bridge", "status": "proposed",
        "notes": f"Generated by bridge_maker.py ({c['type']} crossing, {c['span_ft']:.0f} ft).", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
        "source": "bridge_maker", "road": c["road"], "crossing": c["type"], "preset": pr_name,
        "seed": int(seed if seed is not None else int(hashlib.md5(c["id"].encode()).hexdigest()[:6], 16)),
        "params": {k: v for k, v in (overrides or {}).items() if v is not None},
        "span": {"s0_ft": c["s0_ft"], "s1_ft": c["s1_ft"], "length_ft": round(L, 2), "start": [round(x0, 2), round(y0, 2), round(z0, 3)], "end": [round(x1, 2), round(y1, 2), round(z1, 3)],
                 "width_ft": W, "road_class": c["road_class"], "road_width_ft": road["width_ft"]},
        "context": {"deck": deck, "deck_lift": deck_lift, "terrain_over_deck_ft": round(over, 2), "ground_hi": [[round(float(u), 3), round(g, 3)] for u, g in zip(us, gh)], "ground_lo": [[round(float(u), 3), round(g, 3)] for u, g in zip(us, gl)],
                    "others": others, "deck_above_ground_ft": c.get("deck_above_ground_ft"), "deck_material": road["surface"]["material"], "deck_tile_ft": road["surface"].get("tile_ft") or 8.0,
                    "clearance": c.get("clearance_needed")},
        "foundry": {"pipelineId": f"world:{pack.place}:{c['id']}"},
        "provenance": dict(provenance or {}, tool="bridge_maker.py", schema=SCHEMA),
    }
    if over > 0.05:
        ent["provenance"].setdefault("warnings", []).append(f"terrain rises {over:.1f} ft above the deck even after the maximum {DEFAULTS['max_lift_ft']:.0f} ft lift; trim the terrain under the bridge")
    return ent


def envelopes_of(ent, params=None):
    """Clearance envelopes in feet (u from the bridge start): [{u0_ft, u1_ft, z_top_ft, kind}]."""
    pr = load_preset(ent["preset"])
    P = dict(pr["params"])
    P.update(ent.get("params") or {})
    if params:
        P.update(params)
    ctx = ent["context"]
    L = ent["span"]["length_ft"]
    deck = deck_with_lift_ft(ctx)
    gh = Prof(ctx["ground_hi"])
    env = []
    for o in ctx["others"]:
        if o["kind"] == "water":
            zs = o.get("surface_ft")
            if zs is None:
                zs = float(min(g for _, g in ctx["ground_hi"])) + 1.0
            u0, u1 = max(0.0, o["u0_ft"] - DEFAULTS["bank_ft"]), min(L, o["u1_ft"] + DEFAULTS["bank_ft"])
            dmin = float(deck(np.linspace(u0, u1, 30)).min())
            struct = {"arch": 3.0, "flat": 1.2, "timber": 3.0, "log": 1.3, "covered": 3.0, "rope": 0.5}.get(pr["family"], 3.0)
            fb = max(0.5, min(P["freeboard_ft"], dmin - zs - struct))        # the deck is what it is: use the freeboard the road level leaves (never less than 0.5 ft)
            env.append(dict(kind="water", u0_ft=u0, u1_ft=u1, z_top_ft=zs + fb, freeboard_ft=round(fb, 2), wanted_ft=P["freeboard_ft"]))
        else:
            cw = P["clearance_w_ft"] if P.get("clearance_w_ft") else 12.0
            cw = max(cw, o["width_ft"] + 2.0)
            half = cw / 2 / max(math.sin(math.radians(o["angle_deg"])), 0.25)
            env.append(dict(kind="road", u0_ft=max(0.0, o["u_ft"] - half), u1_ft=min(L, o["u_ft"] + half), z_top_ft=o["z_ft"] + P["clearance_h_ft"]))
    if not env:                                               # a gully or a deck over open ground: keep the low middle passable (people, stock, a path)
        us = np.linspace(0, L, 81)
        gap = deck(us) - gh(us)
        need = P["clearance_h_ft"] + 2.0
        m = gap >= need
        if m.any():
            u0, u1 = float(us[m][0]), float(us[m][-1])
            env.append(dict(kind="gully", u0_ft=u0, u1_ft=u1, z_top_ft=float(gh(np.linspace(u0, u1, 40)).max()) + P["clearance_h_ft"]))
    return env


class Prof:
    def __init__(self, pts):
        a = np.asarray(sorted(pts), float)
        self.u, self.v = a[:, 0], a[:, 1]

    def __call__(self, u):
        return np.interp(u, self.u, self.v)


# ------------------------------------------------------------------ planning
def _params_m(P):
    out = {}
    for k, v in P.items():
        if k.endswith("_ft") and isinstance(v, (int, float)):
            out[k[:-3]] = v * FT
        else:
            out[k] = v
    out["voussoir_m"] = P.get("voussoir_ft", 1.5) * FT
    out["station_m"] = P.get("station_ft", 4.0) * FT
    out["ring_proud"] = P.get("ring_proud_ft", 0.3) * FT
    return out


def _nudge_supports(cands, envs, half, lo, hi, min_gap):
    """Support centres that stay out of the envelopes (u metres); a support whose nudged spot is too close to its neighbour is dropped."""
    out = []
    for c in cands:
        for _ in range(4):
            moved = False
            for a, b in envs:
                if a - half < c < b + half:
                    c = a - half if abs(c - (a - half)) <= abs(b + half - c) else b + half
                    moved = True
            if not moved:
                break
        out.append(c)
    out = sorted(set(round(c, 4) for c in out if lo + min_gap <= c <= hi - min_gap))
    res = []
    for c in out:
        if not res or c - res[-1] >= min_gap:
            res.append(c)
    return res


def make_plan(ent, params=None):
    """Resolve a bridge entity into a plan (metres): deck profile, supports, arches, materials. Pure function of the entity (deterministic)."""
    pr = load_preset(ent["preset"])
    P = dict(pr["params"])
    P.update({k: v for k, v in (ent.get("params") or {}).items() if v is not None})
    if params:
        P.update(params)
    ctx = ent["context"]
    Lft = ent["span"]["length_ft"]
    P["width_ft"] = ent["span"].get("width_ft", P["width_ft"])
    Pm = _params_m(P)
    L = Lft * FT
    W = P["width_ft"] * FT
    fam = pr["family"]
    # deck profile (metres, absolute): road profile + humpback for arches
    deck = Prof(ctx["deck"])
    lf = Prof(ctx["deck_lift"]) if ctx.get("deck_lift") else (lambda u: np.zeros_like(np.asarray(u, float)))      # terrain-clearance lift (compute_lift)
    ug = np.linspace(0, Lft, max(9, int(Lft / 3)) + 1)
    hump = P.get("crown_rise_ft", 0.0)
    hump = min(hump, 0.03 * Lft) if fam == "arch" else 0.0
    zd = deck(ug) + hump * 4 * (ug / Lft) * (1 - ug / Lft)
    if fam != "arch":
        zd = np.linspace(float(deck(0.0)), float(deck(Lft)), len(ug)) if Lft < 120 else deck(ug)
    zd = zd + lf(ug)
    dprof = [(float(u * FT), float(z * FT)) for u, z in zip(ug, zd)]
    D = Prof(dprof)
    gh = Prof([(u * FT, g * FT) for u, g in ctx["ground_hi"]])
    gl = Prof([(u * FT, g * FT) for u, g in ctx["ground_lo"]])
    envs = [dict(u0=max(e["u0_ft"] * FT, 0.35), u1=min(e["u1_ft"] * FT, L - 0.35), z=e["z_top_ft"] * FT, kind=e["kind"]) for e in envelopes_of(ent, params)]   # an abutment is at least 0.35 m thick
    envs = [e for e in envs if e["u1"] > e["u0"]]
    M = dict(pr["materials"])
    if M.get("deck") == "road":
        M["deck"] = ctx["deck_material"]
    wide = max([e["u1"] - e["u0"] for e in envs] + [0.0])
    plan = dict(family=fam, L=L, W=W, deck=dprof, p=Pm, mats=M, seed=int(ent["seed"]), envelopes=envs, ok=True, notes=[], deficit_m=0.0, ground_hi=[(u * FT, g * FT) for u, g in ctx["ground_hi"]],
                deck_tile_ft=ctx.get("deck_tile_ft", 8.0), lift_ends=(float(lf(0.0)) * FT, float(lf(Lft)) * FT), supports=[], feet=[])
    if wide > Pm["max_clear"] > 0:                                # an opening wider than the preset can structurally span
        plan["ok"] = False
        plan["deficit_m"] = wide - Pm["max_clear"]
        plan["notes"].append(f"clear opening {wide / FT:.0f} ft is wider than this preset spans ({Pm['max_clear'] / FT:.0f} ft)")
    found = max(Pm["found"], 1.5 * FT)                         # every foot goes at least 1.5 ft below the lowest ground under it
    ab = Pm.get("abutment_t", 0.9)
    ev = [(e["u0"], e["u1"]) for e in envs]
    abL = ab if not envs else min(ab, max(0.35, min(e["u0"] for e in envs) - 0.05))     # short spans: the abutments shrink rather than enter an envelope
    abR = ab if not envs else min(ab, max(0.35, L - max(e["u1"] for e in envs) - 0.05))
    uu = np.linspace(0, L, 161)
    if fam == "arch":
        pier = Pm["pier_t"]
        maxs, mins = Pm["max_span"], Pm["min_span"]
        n_fix = P.get("n_arches")
        for extra in (0.0, 0.6, 1.2, 1.9, 2.8, 4.0, 5.5):                   # a higher threshold shortens the window (more solid abutment) until the arches fit
            plan["ok"], plan["notes"], plan["deficit_m"] = (wide <= Pm["max_clear"] or Pm["max_clear"] <= 0), ([] if wide <= Pm["max_clear"] or Pm["max_clear"] <= 0 else plan["notes"]), (plan["deficit_m"] if wide > Pm["max_clear"] > 0 else 0.0)
            # the usable window: where there is room under the deck for an opening; beyond it the ground runs up to the deck and the abutments are solid
            need = Pm["ring_t"] + Pm["fill"] + 0.9 + extra
            room = D(uu) - gh(uu) - need
            okw = np.where(room >= 0)[0]
            wa, wb = (float(uu[okw[0]]), float(uu[okw[-1]])) if len(okw) else (abL, L - abR)
            for e in envs:                                                      # the envelopes must be inside the window
                wa, wb = min(wa, e["u0"]), max(wb, e["u1"])
            i0 = max(abL, wa - 0.6)
            i1 = min(L - abR, wb + 0.6)
            if i1 - i0 < mins:
                i0, i1 = abL, L - abR
            inner = i1 - i0
            N = int(n_fix) if n_fix else max(1, int(math.ceil((inner + pier) / (maxs + pier))))
            # envelopes wider than max_span push N down (an arch must clear the whole envelope in one opening)
            while True:
                s = (inner - (N - 1) * pier) / N
                cands = [i0 + k * s + (k - 0.5) * pier for k in range(1, N)]
                cs = _nudge_supports(cands, ev, pier / 2 + 0.05, i0, i1, mins + pier) if not n_fix else cands
                if s < mins and N > 1 and not n_fix:
                    N -= 1
                    continue
                break
            edges = [i0] + [x for c in cs for x in (c - pier / 2, c + pier / 2)] + [i1]
            solids = [dict(u0=0.0, u1=i0)]
            arches = []
            for i in range(0, len(edges) - 1, 2):
                arches.append(dict(ua=edges[i], ub=edges[i + 1]))
                if i + 2 < len(edges):
                    solids.append(dict(u0=edges[i + 1], u1=edges[i + 2]))
            solids.append(dict(u0=i1, u1=L))
            t, fill, gclr = Pm["ring_t"], Pm["fill"], Pm["ground_clear"]
            for a in arches:
                ua, ub = a["ua"], a["ub"]
                s_ = ub - ua
                xs = np.linspace(ua, ub, 61)
                best = None
                rho = P["rise_ratio"]
                while rho >= P["min_rise_ratio"] - 1e-9:
                    rise = rho * s_
                    uc, R = 0.5 * (ua + ub), (s_ * s_ / 4 + rise * rise) / (2 * rise)
                    hin = np.sqrt(np.maximum(R * R - (xs - uc) ** 2, 0)) - (R - rise)
                    hex_ = np.sqrt(np.maximum((R + t) ** 2 - (xs - uc) ** 2, 0)) - (R - rise)
                    req = (gh(xs) + gclr) - hin
                    for e in envs:
                        m = (xs >= e["u0"] - 1e-9) & (xs <= e["u1"] + 1e-9)
                        if m.any():
                            req = np.maximum(req, np.where(m, e["z"] - hin, -1e9))
                    zs = float(req.max())
                    fits = bool(np.all(zs + hex_ + fill <= D(xs)))
                    if fits:
                        best = (rho, zs, True)
                        break
                    rho -= 0.04
                if best is None:
                    rho = P["min_rise_ratio"]
                    rise = rho * s_
                    uc, R = 0.5 * (ua + ub), (s_ * s_ / 4 + rise * rise) / (2 * rise)
                    hex_ = np.sqrt(np.maximum((R + t) ** 2 - (xs - uc) ** 2, 0)) - (R - rise)
                    zs = float(np.min(D(xs) - fill - hex_))
                    best = (rho, zs, False)
                    plan["ok"] = False
                    plan["deficit_m"] = max(plan["deficit_m"], float(req.max() - zs))
                    plan["notes"].append(f"arch {ua / FT:.1f}-{ub / FT:.1f} ft: not enough height under the deck for the required clearance; raise the deck or lower what is below")
                a["rise"], a["zs"] = best[0] * s_, best[1]
            for k, sd in enumerate(solids):
                lo = float(gl(np.linspace(sd["u0"], sd["u1"], 7)).min())
                sd["base"] = min(lo - found, min(a["zs"] for a in arches) - 0.6)
                if k in (0, len(solids) - 1):                                   # end blocks follow the rising ground
                    sd["bprof"] = [(float(u), float(gl(u)) - found) for u in np.linspace(sd["u0"], sd["u1"], 9)]
            if plan["ok"]:
                break
        plan["solids"], plan["arches"] = solids, arches
    elif fam == "flat":
        pier = Pm["pier_t"]
        maxs = Pm["max_span"]
        N = max(1, int(math.ceil((L - 2 * ab * 0 ) / maxs)))
        cands = [L * k / N for k in range(1, N)]
        cs = _nudge_supports(cands, ev, pier / 2 + 0.1, abL + 0.5, L - abR - 0.5, 2.5)
        sup = [dict(u0=0.0, u1=abL)] + [dict(u0=c - pier / 2, u1=c + pier / 2) for c in cs] + [dict(u0=L - abR, u1=L)]
        spans = [0.5 * (sup[i + 1]["u0"] + sup[i + 1]["u1"]) - 0.5 * (sup[i]["u0"] + sup[i]["u1"]) for i in range(len(sup) - 1)]
        t = max(Pm["min_slab_t"], max(spans) * Pm["slab_ratio"] if "slab_ratio" in Pm else 0.3)
        t = float(min(t, 1.1))
        # clearance: the slab underside must clear every envelope; thinner (down to 0.25 m) if that is what it takes
        need_t = t
        for e in envs:
            m = (uu >= e["u0"]) & (uu <= e["u1"])
            if m.any():
                room = float(np.min(D(uu[m]) - e["z"]))
                need_t = min(need_t, room)
        if need_t < t:
            if need_t < 0.22:
                plan["ok"] = False
                plan["deficit_m"] = 0.22 - need_t
                plan["notes"].append("flat slab: deck is less than 0.22 m above the required clearance; raise the deck or lower what is below")
                t = 0.22
            else:
                t = need_t
        plan["slab_t"] = t
        for sd in sup:
            lo = float(gl(np.linspace(sd["u0"], sd["u1"], 7)).min())
            sd["base"] = lo - found
        plan["supports"] = sup
        Pm["slab_w_m"] = P["slab_w_ft"] * FT
        plan["p"] = Pm
    elif fam == "log":
        _plan_log(plan, P, Pm, D, gl, envs, L, W, found)
    elif fam == "covered":
        _plan_covered(plan, P, Pm, D, gl, envs, ev, L, W, found)
    elif fam == "rope":
        _plan_rope(plan, P, Pm, D, gh, gl, envs, L, W, found)
    else:                                                      # timber: bents carry stringers, truss sides or rails
        maxs = Pm["max_span"]
        Pm["stringer_every"] = P.get("stringer_every_ft", 3.0) * FT
        Pm["plank_w"], Pm["plank_gap"], Pm["plank_t"] = P["plank_w_ft"] * FT, P["plank_gap_ft"] * FT, P["plank_t_ft"] * FT
        Pm["post_every"], Pm["rail_h"], Pm["kingpost_max_m"] = P["post_every_ft"] * FT, P["rail_h_ft"] * FT, P["kingpost_max_ft"] * FT
        Pm["truss_depth_ratio"], Pm["side"] = P["truss_depth_ratio"], P["side"]
        N = max(1, int(math.ceil(L / maxs)))
        cands = [L * k / N for k in range(1, N)]
        cs = _nudge_supports(cands, ev, 0.9, 1.5, L - 1.5, 3.0)
        us_ = [0.0] + cs + [L]
        sup = [dict(u=u, kind="abut" if i in (0, len(us_) - 1) else "bent", base=float(gl(np.linspace(max(0.0, u - 1.2), min(L, u + 1.2), 7)).min()) - found) for i, u in enumerate(us_)]
        plan["supports"] = sup
        plan["p"] = Pm
        # clearance of stringers / cap beams
        worst = 1e9
        for i in range(len(us_) - 1):
            ls = us_[i + 1] - us_[i]
            r = float(np.clip(0.10 + 0.0045 * ls, 0.11, 0.30))
            for e in envs:
                lo_, hi_ = max(e["u0"], us_[i]), min(e["u1"], us_[i + 1])
                if hi_ > lo_:
                    x = np.linspace(lo_, hi_, 20)
                    worst = min(worst, float(np.min(D(x) - Pm["plank_t"] - 2 * r - 0.03 - e["z"])))
        if worst < 0:
            plan["ok"] = False
            plan["deficit_m"] = -worst
            plan["notes"].append(f"timber: stringers are {-worst:.2f} m too low for the clearance below")
    if fam == "flat":
        plan["p"]["slab_w_m"] = P["slab_w_ft"] * FT
    plan["feet"] = plan_feet(plan, gl)
    return plan


def _timber_bits(P, Pm):
    Pm["stringer_every"] = P.get("stringer_every_ft", 3.0) * FT
    Pm["plank_w"], Pm["plank_gap"], Pm["plank_t"] = P["plank_w_ft"] * FT, P["plank_gap_ft"] * FT, P["plank_t_ft"] * FT


def _plan_log(plan, P, Pm, D, gl, envs, L, W, found):
    """Raw logs side by side: diameters/lengths/heights from the seed; bank rocks under both ends. A log is at most `max_log` long (26 ft); a longer crossing
    gets log TRESTLES (lashed A-frame legs standing in the water / on the ground, feet below the bed, a cap log across) and every lane is several logs laid
    end to end, joints on the trestle caps."""
    rng = np.random.RandomState(plan["seed"] + 101)
    d0, var = Pm["log_d"], float(P.get("log_d_var", 0.35))
    ds = []
    while sum(ds) < W - 0.45 * d0 or len(ds) < 3:
        ds.append(d0 * rng.uniform(1 - var, 1 + var))
    ds = np.array(ds) * (W / sum(ds))                              # they exactly fill the width, touching
    vs = -W / 2 + np.cumsum(ds) - ds / 2
    tall = int(np.argmax(ds))
    logs = []
    for k, (v, dd) in enumerate(zip(vs, ds)):
        logs.append(dict(v=float(v), r=float(dd / 2), off=-0.04 if k == tall else float(rng.uniform(0.0, 0.16)),
                         a=-float(Pm["bear_min"] + rng.uniform(0, Pm["bear_var"])), b=float(L + Pm["bear_min"] + rng.uniform(0, Pm["bear_var"])),
                         taper=float(rng.uniform(0.86, 1.0)), tip0=bool(rng.rand() < 0.4), tip1=bool(rng.rand() < 0.4)))
    # how many bays? (logs never longer than max_log)
    lmax = Pm.get("max_log", 26.0 * FT)
    bA, bB = max(-l["a"] for l in logs), max(l["b"] - L for l in logs)
    cap_end, cap_mid = lmax - 0.1 - bA, lmax - 0.1
    cap_end_b = lmax - 0.1 - bB
    N = 1
    if L + bA + bB > lmax:
        N = 2
        while cap_end + cap_end_b + (N - 2) * cap_mid < L and N < 8:
            N += 1
    cs = []
    if N > 1:
        w_ = [cap_end] + [cap_mid] * (N - 2) + [cap_end_b]
        sc = L / sum(w_)
        pos = np.cumsum([x * sc for x in w_])[:-1]
        ev_dry = [(e["u0"], e["u1"]) for e in envs if e["kind"] != "water"]      # a trestle may stand in the water, not in a road / path below
        cs = _nudge_supports([float(x) for x in pos], ev_dry, 0.9, 0.0, L, 1.0)
        edges = [0.0] + cs + [L]
        bays = [edges[i + 1] - edges[i] for i in range(len(edges) - 1)]
        bad = len(cs) != N - 1 or bays[0] + bA > lmax + 1e-6 or bays[-1] + bB > lmax + 1e-6 or any(x > lmax - 0.05 for x in bays[1:-1])
        if bad:
            plan["ok"] = False
            plan["deficit_m"] = max(plan["deficit_m"], 0.5)
            plan["notes"].append("log bridge: a trestle would have to stand in the clearance below (road / path); no arrangement of logs <= %.0f ft fits" % (lmax / FT))
    plan["trestle_u"] = cs
    for lg in logs:                                                  # segments: end to end, joints on the trestle caps (+-6 cm so both logs rest on the cap)
        a_, segs = lg["a"], []
        for c in cs:
            j = c + float(rng.uniform(-0.06, 0.06))
            segs.append((a_, j - 0.03))
            a_ = j + 0.03
        segs.append((a_, lg["b"]))
        lg["segs"] = segs
    plan["logs"] = logs
    plan["log_max_m"] = max(b_ - a_ for lg in logs for a_, b_ in lg["segs"])
    plan["wade"] = []
    if L > Pm["max_span"]:
        plan["ok"] = False
        plan["deficit_m"] = max(plan["deficit_m"], L - Pm["max_span"])
        plan["notes"].append(f"log bridge: {L / FT:.0f} ft is longer than a log trestle bridge can span ({Pm['max_span'] / FT:.0f} ft)")
    elif N > 1:
        plan["notes"].append(f"log bridge: {len(cs) + 1} bays on {len(cs)} log trestle(s), longest log {plan['log_max_m'] / FT:.1f} ft (limit {lmax / FT:.0f} ft)")
    worst = 1e9
    for e in envs:
        x = np.linspace(e["u0"], e["u1"], 20)
        for lg in logs:
            worst = min(worst, float(np.min(D(x) - lg["off"] - 2.15 * lg["r"] - e["z"])))
    if worst < 0:
        plan["ok"] = False
        plan["deficit_m"] = max(plan["deficit_m"], -worst)
        plan["notes"].append(f"log bridge: the logs hang {-worst:.2f} m into the clearance below")
    # trestles: cap log under the lowest log underside; four lashed legs (two bents), cross brace; feet below the lowest ground under each leg
    slope = (float(D(L)) - float(D(0.0))) / L
    z0 = float(D(0.0))
    capr = 0.16
    trest = []
    for c in cs:
        under = min(z0 + slope * c - lg["off"] - 2 * lg["r"] for lg in logs)
        zc = under - capr - 0.02                                      # cap centre line; the logs' lowest underside sits 2 cm over its top
        legs = []
        for sd in (-1, 1):
            v = sd * (W / 2 - 0.3)
            hgt = zc - float(gl(np.linspace(c - 1.2, c + 1.2, 9)).min())
            sp = float(np.clip(0.14 * hgt, 0.35, 1.3))
            for sg in (-1, 1):
                ul = c + sg * sp
                base = float(gl(np.linspace(ul - 0.6, ul + 0.6, 7)).min()) - found
                legs.append(dict(u=ul, v=v, base=base, u_top=c + sg * 0.12, top=zc - 0.05))
        trest.append(dict(u=c, zc=zc, capr=capr, legs=legs, chocks=[
            dict(v=lg["v"], z0=zc + capr * 0.9, z1=z0 + slope * c - lg["off"] - 2 * lg["r"]) for lg in logs]))
        plan["wade"].append((c - 1.5, c + 1.5))
    plan["trestles"] = trest
    rocks = []
    rr = Pm["rock_r"]
    for end, u in ((0, -0.35), (1, L + 0.35)):
        for fr in (-0.28, 0.28):
            v = fr * W
            lg = min(logs, key=lambda q: abs(q["v"] - v))
            top = float(D(0.0 if end == 0 else L)) - lg["off"] - 2 * lg["r"] + 0.14
            win = (-0.9, 0.2) if end == 0 else (L - 0.2, L + 0.9)
            base = float(gl(np.linspace(win[0], win[1], 7)).min()) - found
            rocks.append(dict(u=u, v=v, r=rr * (0.9 + 0.2 * rng.rand()), base=base, top=max(top, base + 0.5)))
    plan["rocks"] = rocks


def _plan_covered(plan, P, Pm, D, gl, envs, ev, L, W, found):
    _timber_bits(P, Pm)
    Pm["roof_oh"], Pm["wall_h"], Pm["post_h"], Pm["rise"] = P["roof_overhang_ft"] * FT, P["wall_h_ft"] * FT, P["post_h_ft"] * FT, float(P["roof_rise_ratio"])
    Pm["post_every"] = P["post_every_ft"] * FT
    piers = str(P.get("support", "piles")) == "piers"
    plan["piers"] = piers
    plan["roof_mat"] = plan["mats"].get("roof_tile") if str(P.get("roof", "shingle")) == "tile" else plan["mats"].get("roof")
    N = max(1, int(math.ceil(L / Pm["max_span"])))
    half = (Pm["pier_t"] / 2 + 0.15) if piers else 1.7
    ev_dry = [(e["u0"], e["u1"]) for e in envs if e["kind"] != "water"]        # bents / piers may stand IN the river (that is what they are for), never in a road / path below
    cs = _nudge_supports([L * k / N for k in range(1, N)], ev_dry, half, 1.5, L - 1.5, 3.0)
    plan["wade"] = [(c - half - 0.3, c + half + 0.3) for c in cs]
    us_ = [0.0] + cs + [L]
    sup = []
    for i, u in enumerate(us_):
        end = i in (0, len(us_) - 1)
        win = (0.0, 1.2) if i == 0 else ((L - 1.2, L) if end else (u - half, u + half))
        sup.append(dict(u=u, kind="abut" if end else ("pier" if piers else "bent"), half=half, base=float(gl(np.linspace(win[0], win[1], 7)).min()) - found))
    plan["supports"] = sup
    worst = 1e9
    for i in range(len(us_) - 1):
        r = float(np.clip(0.10 + 0.0045 * (us_[i + 1] - us_[i]), 0.11, 0.30))
        for e in envs:
            lo_, hi_ = max(e["u0"], us_[i]), min(e["u1"], us_[i + 1])
            if hi_ > lo_:
                x = np.linspace(lo_, hi_, 20)
                worst = min(worst, float(np.min(D(x) - Pm["plank_t"] - 2 * r - 0.03 - e["z"])))
    if worst < 0:
        plan["ok"] = False
        plan["deficit_m"] = -worst
        plan["notes"].append(f"covered bridge: the beams are {-worst:.2f} m too low for the clearance below")


def sag_shape(t, k=2.2):
    """Catenary-like shape: 0 at both ends, 1 in the middle."""
    t = np.asarray(t, float)
    return (np.cosh(k / 2) - np.cosh(k * (t - 0.5))) / (np.cosh(k / 2) - 1.0)


def _plan_rope(plan, P, Pm, D, gh, gl, envs, L, W, found):
    """Sagging deck between two raised anchors. The sag wanted is `sag_ratio` x span (8-12 %); to let it hang that far and still clear the ground / water /
    road envelopes the whole rope line is RAISED by `raise` (the anchor towers at both ends get taller and a ramp climbs from the road to the deck end).
    The raise is the smallest that works, capped at `raise_max_ft`; only when even that is not enough is the sag clamped (reported in plan.notes)."""
    _timber_bits(P, Pm)
    Pm["rail_h"], Pm["post_h"] = P["rail_h_ft"] * FT, P["post_h_ft"] * FT
    t = np.linspace(0.02, 0.98, 97)
    uu_ = t * L
    lin = D(uu_)
    f = np.maximum(sag_shape(t), 1e-3)
    wgt = np.clip((0.5 - np.abs(t - 0.5) - 0.06) / 0.2, 0.0, 1.0)  # comfort clearance fades in away from the banks (the ground rises to the deck there)
    soft = gh(uu_) + 0.1 + (Pm["min_clear"] - 0.1) * wgt
    for e in envs:
        m = (uu_ >= e["u0"]) & (uu_ <= e["u1"])
        soft = np.where(m, np.maximum(soft, e["z"]), soft)

    def allowed_at(R):
        return float(np.min((lin + R - (Pm["plank_t"] + 0.35 * wgt) - soft) / f))
    wanted = max(P["sag_ratio"] * L, 0.6)
    rmax = float(P.get("raise_max_ft", 8.0)) * FT
    allowed0 = allowed_at(0.0)
    R = 0.0
    if allowed0 < wanted:
        if allowed_at(rmax) < wanted:
            R = rmax
        else:
            lo_, hi_ = 0.0, rmax
            for _ in range(40):
                mid_ = 0.5 * (lo_ + hi_)
                lo_, hi_ = (mid_, hi_) if allowed_at(mid_) < wanted else (lo_, mid_)
            R = hi_
        R = min(rmax, math.ceil(R / 0.1) * 0.1)                      # tidy 0.1 m steps
    allowed = allowed_at(R)
    sag = float(np.clip(allowed, 0.0, wanted))
    plan["rope"] = dict(sag_m=sag, wanted_m=wanted, allowed_m=allowed, clamped=allowed < wanted - 1e-9, raise_m=R, raise_max_m=rmax)
    if R > 1e-6:
        plan["notes"].append(f"rope bridge: anchors raised {R / FT:.1f} ft above the road so the deck can sag {sag / FT:.1f} ft and still clear the ground/water")
    if allowed < wanted - 1e-9:
        plan["notes"].append(f"rope sag clamped to {sag / FT:.1f} ft (wanted {wanted / FT:.1f} ft) to stay {Pm['min_clear'] / FT:.1f} ft above the ground/water, even with the maximum {rmax / FT:.0f} ft raise")
    uf = np.array([u for u, _ in plan["deck"]])
    zf = np.array([z for _, z in plan["deck"]]) + R - sag * sag_shape(uf / L)
    plan["deck"] = [(float(u), float(z)) for u, z in zip(uf, zf)]
    if R > 1e-6:                                                   # a ramp from the road up to the raised deck end (steeper than a road: a log stair-ramp)
        l0, l1 = plan.get("lift_ends") or (0.0, 0.0)
        plan["lift_ends"] = (l0 + R, l1 + R)
    plan["ramp_slope"] = float(P.get("rope_ramp_slope", 0.22))
    D2 = Prof(plan["deck"])
    hard = gh(uu_) + 0.1                                           # the real obstacles (no comfort margin): ground + 0.1 m, envelopes
    for e in envs:
        m = (uu_ >= e["u0"]) & (uu_ <= e["u1"])
        hard = np.where(m, np.maximum(hard, e["z"]), hard)
    miss = float(np.max(hard - (D2(uu_) - Pm["plank_t"])))
    if miss > 0:
        plan["ok"] = False
        plan["deficit_m"] = max(plan["deficit_m"], miss)
        plan["notes"].append(f"rope bridge: the deck cannot clear the ground/clearance below even without sag (short by {miss:.2f} m)")
    posts, backs = [], []
    for end, u in ((0, -0.9), (1, L + 0.9)):
        win = (-0.9, 0.9) if end == 0 else (L - 0.9, L + 0.9)
        base = float(gl(np.linspace(win[0], win[1], 7)).min()) - found
        zt = float(D2(0.0 if end == 0 else L)) + Pm["rail_h"] + 1.0     # tall anchor posts: the ropes tie in near the top
        for sd in (-1, 1):
            posts.append(dict(u=u, v=sd * (W / 2 + 0.3), base=base, top=zt, end=end))
            ub = u + (-1.0 if end == 0 else 1.0) * (0.35 * (zt - base) + 0.6)    # a raking back-leg (A-frame) behind each post, footed below the ground
            baseb = float(gl(np.linspace(min(L, max(0.0, ub)) - 0.6, min(L, max(0.0, ub)) + 0.6, 7)).min()) - found
            backs.append(dict(u=ub, v=sd * (W / 2 + 0.3), base=baseb, u_top=u, top=zt - 0.3, end=end))
    plan["posts"], plan["backs"] = posts, backs


def plan_feet(plan, gl):
    """Every foot that should reach the ground: [{kind, u, z}] with z the bottom of the foot (metres). Tests compare z with the sampled ground."""
    feet = []
    fam = plan["family"]
    if fam == "arch":
        for sd in plan["solids"]:
            for u in np.linspace(sd["u0"], sd["u1"], 5):
                z = float(np.interp(u, np.asarray(sd["bprof"], float)[:, 0], np.asarray(sd["bprof"], float)[:, 1])) if "bprof" in sd else sd["base"]
                feet.append(dict(kind="arch_solid", u=float(u), z=z))
    elif fam == "flat":
        for sd in plan["supports"]:
            for u in (sd["u0"], 0.5 * (sd["u0"] + sd["u1"]), sd["u1"]):
                feet.append(dict(kind="pier", u=float(u), z=sd["base"]))
    elif fam == "log":
        for r in plan["rocks"]:
            feet.append(dict(kind="rock", u=r["u"], z=r["base"]))
        for tr in plan.get("trestles", []):
            for lgx in tr["legs"]:
                feet.append(dict(kind="trestle", u=lgx["u"], z=lgx["base"]))
    elif fam == "rope":
        for r in plan["posts"]:
            feet.append(dict(kind="anchor_post", u=r["u"], z=r["base"]))
        for r in plan.get("backs", []):
            feet.append(dict(kind="anchor_back", u=r["u"], z=r["base"]))
    else:
        for sd in plan["supports"]:
            feet.append(dict(kind=sd["kind"], u=sd["u"], z=sd["base"]))
    return feet


# ------------------------------------------------------------------ meshes
def build_local(ent, params=None):
    """(Mesh in the local frame, plan). Local frame: x = u along the span, y = v left, z absolute metres (feet * 0.3048)."""
    import bridge_geo as bg
    plan = make_plan(ent, params)
    g_tiles = None
    mesh = bg.build(plan)
    return mesh, plan


def to_blender(mesh, ent, frame):
    """Local mesh -> pack Blender frame (metres, x east, y north, z from z_origin)."""
    import worldpack_mesh as wm
    sx, sy, _ = ent["span"]["start"]
    ex, ey, _ = ent["span"]["end"]
    d = np.array([ex - sx, -(ey - sy)], float)
    d /= np.linalg.norm(d)
    lf = np.array([-d[1], d[0]])
    V = mesh.V
    X = sx * FT + V[:, 0] * d[0] + V[:, 1] * lf[0]
    Y = (frame.height_ft - sy) * FT + V[:, 0] * d[1] + V[:, 1] * lf[1]
    Z = V[:, 2] - frame.z_origin_ft * FT
    N = None
    return wm.Mesh(np.stack([X, Y, Z], 1), mesh.UV, mesh.subs, mesh.smooth)


def heading_deg(ent):
    sx, sy, _ = ent["span"]["start"]
    ex, ey, _ = ent["span"]["end"]
    return round(math.degrees(math.atan2(-(ey - sy), ex - sx)), 3)


def check_clearance(mesh, plan, eps=0.04):
    """Count mesh sample points (vertices, edge midpoints, centroids) inside any clearance envelope (above the highest ground, below its z_top)."""
    V = mesh.V
    pts = [V]
    for F in mesh.subs.values():
        a, b, c = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
        pts += [(a + b + c) / 3, (a + b) / 2, (b + c) / 2, (a + c) / 2]
    Pt = np.concatenate(pts)
    gh = Prof(plan["ground_hi"])
    bad = 0
    for e in plan["envelopes"]:
        m = (Pt[:, 0] > e["u0"] + eps) & (Pt[:, 0] < e["u1"] - eps) & (Pt[:, 2] < e["z"] - eps) & (Pt[:, 2] > gh(Pt[:, 0]) + eps)
        if e["kind"] == "water":                       # piers / bents / trestles may stand IN the water (only there); the beams between them must still clear it
            for w0, w1 in plan.get("wade", []):
                m &= ~((Pt[:, 0] >= w0) & (Pt[:, 0] <= w1))
        bad += int(m.sum())
    return bad


def audit_mesh(ent, h, cell, plan=None):
    """Final-MESH check of one bridge against the terrain TRIANGLES (road_grade.mesh_height, the same triangulation as build_terrain; `h` = the heights the
    mesh is built from, see final_heights): every foot (min terrain over the foot's footprint, +-0.3 ft in u, across the deck width +-1 ft) and the deck (top minus the
    HIGHEST terrain across the deck width, everywhere along the span and in the first/last 8 ft). Feet: margin_ft = ground - foot bottom (want >= 1.5);
    deck: clear_ft = deck top - terrain (want >= 0.3; the planner keeps 0.5 on the raster). Returns {feet: [...], min_foot_margin_ft, deck_clear_min_ft, deck_clear_ends_ft}."""
    import road_grade as rg
    plan = plan or make_plan(ent)
    sx, sy, _ = ent["span"]["start"]
    ex, ey, _ = ent["span"]["end"]
    L = math.hypot(ex - sx, ey - sy)
    d = np.array([ex - sx, ey - sy]) / L
    lf = np.array([d[1], -d[0]])
    W = plan["W"] / FT

    def at(u, v):
        return rg.mesh_height(h, cell, sx + d[0] * u + lf[0] * v, sy + d[1] * u + lf[1] * v)
    vs = np.linspace(-W / 2 - 1.0, W / 2 + 1.0, 7)
    feet = []
    for ft in plan["feet"]:
        u = min(max(ft["u"] / FT, -4.0), L + 4.0)
        g = min(float(at(uu, vv)) for uu in (u - 0.3, u, u + 0.3) for vv in vs)
        feet.append(dict(kind=ft["kind"], u_ft=round(ft["u"] / FT, 2), bottom_ft=round(ft["z"] / FT, 2), ground_ft=round(g, 2), margin_ft=round(g - ft["z"] / FT, 2)))
    D = Prof([(u / FT, z / FT) for u, z in plan["deck"]])
    us = np.linspace(0.0, L, int(L / 1.0) + 1)
    vd = np.linspace(-W / 2, W / 2, 7)
    clear = np.array([float(D(u)) - max(float(at(u, v)) for v in vd) for u in us])
    ends = (us <= 8.0) | (us >= L - 8.0)
    return dict(feet=feet, min_foot_margin_ft=min([f["margin_ft"] for f in feet] or [99.0]), deck_clear_min_ft=round(float(clear.min()), 2),
                deck_clear_ends_ft=round(float(clear[ends].min()), 2) if ends.any() else None)


# ------------------------------------------------------------------ terrain carving under bridges (mesh level)
STRUCT_FT = {"arch": 3.0, "flat": 1.2, "timber": 3.0, "log": 1.3, "covered": 3.0, "rope": 0.5}      # depth of the deck structure below the road surface, per family
CARVE_DECK_CLEAR_FT = 0.3                                                                          # audit_mesh wants the deck at least this far above the terrain


def carve_under(ent, h, cell, side_ft=2.5, falloff_ft=5.0, end_ft=6.0, extra_ft=0.3):
    """Heights `h` with the ground cleared through the span envelope of one bridge: inside the footprint (deck width + side_ft each side, smooth falloff over
    falloff_ft) the terrain is capped at deck top - structure depth - extra_ft, ramped in over end_ft at both abutments so the ground still meets the approach.
    Only ever lowers. Returns (h2, max_cut_ft, cells_changed)."""
    fam = load_preset(ent["preset"])["family"]
    sx, sy, _ = ent["span"]["start"]
    ex, ey, _ = ent["span"]["end"]
    L = math.hypot(ex - sx, ey - sy)
    d = np.array([ex - sx, ey - sy]) / L
    lf = np.array([d[1], -d[0]])
    W = float(ent["span"].get("width_ft") or 6.0)
    pl = make_plan(ent)                                            # the planned deck (a rope bridge sags below the road line)
    D = Prof([(u / FT, z / FT) for u, z in pl["deck"]])
    deck = D
    ny, nx = h.shape
    reach = W / 2 + side_ft + falloff_ft
    x0, x1 = min(sx, ex) - reach, max(sx, ex) + reach
    y0, y1 = min(sy, ey) - reach, max(sy, ey) + reach
    j0, j1 = max(0, int(x0 // cell)), min(nx - 1, int(x1 // cell) + 1)
    i0, i1 = max(0, int(y0 // cell)), min(ny - 1, int(y1 // cell) + 1)
    if j1 <= j0 or i1 <= i0:
        return h, 0.0, 0
    X, Y = np.meshgrid(np.arange(j0, j1 + 1) * cell, np.arange(i0, i1 + 1) * cell)
    u = (X - sx) * d[0] + (Y - sy) * d[1]
    v = (X - sx) * lf[0] + (Y - sy) * lf[1]
    inside_u = (u > 0.0) & (u < L)
    uc = np.clip(u, 0.0, L)
    ramp = np.clip(np.minimum(uc, L - uc) / max(end_ft, 1e-6), 0.0, 1.0)
    ramp = ramp * ramp * (3 - 2 * ramp)
    lat = np.clip((W / 2 + side_ft + falloff_ft - np.abs(v)) / falloff_ft, 0.0, 1.0)
    lat = lat * lat * (3 - 2 * lat)
    k = np.where(inside_u, ramp * lat, 0.0)
    cap = deck(uc) - STRUCT_FT.get(fam, 3.0) - extra_ft
    sub = h[i0:i1 + 1, j0:j1 + 1].astype(float)
    new = np.where(sub > cap, sub - k * (sub - cap), sub)
    out = h.copy()
    out[i0:i1 + 1, j0:j1 + 1] = new.astype(h.dtype)
    cut = sub - new
    return out, float(cut.max()), int((cut > 0.01).sum())


def carve_under_bridges(pack, h, mode="auto"):
    """Terrain carving for every bridge of the pack. mode: 'auto' (default) = only bridges whose deck clearance check against the terrain triangles fails
    (audit_mesh deck_clear_min < 0.3 ft or terrain_over_deck_ft > 0), True = all bridges, False = none. Returns (h, report [{id, carved, reason, max_cut_ft, cells}])."""
    rep = []
    if mode in (False, "off", None):
        return h, rep
    for ent in pack.list("bridges"):
        reason = "forced"
        if mode == "auto":
            try:
                a = audit_mesh(ent, h, pack.cell_ft)
                bad = a["deck_clear_min_ft"] < CARVE_DECK_CLEAR_FT or float(ent["context"].get("terrain_over_deck_ft") or 0.0) > 0.05
                reason = f"deck clearance {a['deck_clear_min_ft']} ft" if bad else ""
            except Exception as ex:                                 # a bridge we cannot audit is left alone
                bad, reason = False, f"audit failed: {ex}"
            if not bad:
                rep.append(dict(id=ent["id"], carved=False, reason="clearance ok" if not reason.startswith("audit") else reason))
                continue
        h, cut, n = carve_under(ent, h, pack.cell_ft)
        rep.append(dict(id=ent["id"], carved=n > 0, reason=reason, max_cut_ft=round(cut, 2), cells=n))
    return h, rep


# ------------------------------------------------------------------ pack integration
def add_bridge_parts(pack, cx, parts, add, want=True, roof_list=None):
    """Hook for worldpack_mesh.build_parts: one Part per bridge entity (layer 'bridges'). roof_list (a list, given when the split's roof_mode is not
    'none'): the roof of a covered bridge goes there as (entity, mesh) and becomes a 'roofs' Part like a building roof: collision off (a token dragged
    from a top-down camera lands on the deck, not on the roof), hideable by the roof toggle."""
    import worldpack_mesh as wm
    for e in pack.list("bridges"):
        m, plan = build_local(e)
        mesh = to_blender(m, e, cx.fr)
        if roof_list is not None and plan.get("roof_mat") and plan["roof_mat"] in mesh.subs:
            import worldpack_roofs as wr
            body, roof = wr.split_mesh(mesh, plan["roof_mat"], float("inf"))
            if roof.tri_count and body.tri_count:
                mesh = body
                roof_list.append((e, roof))
        for mid in plan["mats"].values():
            if mid not in pack.materials:
                try:
                    import building_styles as bs
                    r = bs.material_record(mid) if mid.startswith("mat_s_") else None
                except Exception:
                    r = None
                if r:
                    pack.materials[mid] = r
        add(e, "bridges", mesh)
    return parts


def bridge_gaps(bridges):
    """{road id: [{bridge, s0_ft, s1_ft}]}"""
    out = {}
    for b in bridges:
        out.setdefault(b["road"], []).append({"bridge": b["id"], "s0_ft": b["span"]["s0_ft"], "s1_ft": b["span"]["s1_ft"]})
    return out


def _read(p):
    with open(p, "rb") as f:
        return f.read()


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jdump(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1, ensure_ascii=False)
        f.write("\n")


def bridges_path(place, world_root=None):
    return os.path.join(world_root or WORLD, place, "bridges.json")


def load_bridges(place, world_root=None):
    p = bridges_path(place, world_root)
    return _jload(p) if os.path.exists(p) else {"place": place, "schema": SCHEMA, "bridges": [], "removed": []}


def inject(pack_dir, place, world_root=None, doc=None):
    """Write the bridges of world/<place>/bridges.json into an exported pack: entities/bridges.json, manifest entry, road gaps."""
    doc = doc or load_bridges(place, world_root)
    removed = set(doc.get("removed") or [])
    bridges = [b for b in doc.get("bridges", []) if b["id"] not in removed]
    ent_dir = os.path.join(pack_dir, "entities")
    mp = os.path.join(pack_dir, "manifest.json")
    man = _jload(mp)
    roads_p = os.path.join(ent_dir, "roads.json")
    roads = _jload(roads_p)
    gaps = bridge_gaps(bridges)
    for r in roads["items"]:
        r.pop("gaps", None)
        if r["id"] in gaps:
            r["gaps"] = gaps[r["id"]]
            r.setdefault("derived", [])
            if "bridge_gaps" not in r["derived"]:
                r["derived"].append("bridge_gaps")
    _jdump(roads_p, roads)
    fn = os.path.join(ent_dir, "bridges.json")
    items = []
    for b in bridges:
        b = dict(b)
        b["tags"] = {"layer": "bridges", "subtype": b.get("preset", "bridge"), "district": None, "ring": None, "group": "bridges", "id": b["id"]}
        items.append(b)
    _jdump(fn, {"format": roads.get("format"), "schema_version": roads.get("schema_version"), "type": "bridges", "units": roads.get("units", "feet"), "items": items})
    rel = "entities/bridges.json"
    man.setdefault("entities", {})["bridges"] = {"file": rel, "count": len(bridges), "sha256": hashlib.sha256(_read(fn)).hexdigest()}
    man.setdefault("files", {})[rel] = "pending"
    _jdump(mp, man)
    import worldpack as wp
    wp.refresh_manifest_files(pack_dir)                                 # roads.json changed (gaps) and bridges.json is new: re-hash
    return {"bridges": len(bridges), "roads_with_gaps": sorted(gaps)}


KEEP_ON_REFRESH = ("name", "status", "notes", "links", "locked", "seed", "from_parent")


def refresh_for_export(pack_dir, place, world_root=None, log=print):
    """Called by worldpack.export_world after every export: the export wipes entities/, so the bridges of world/<place>/bridges.json are put back here.
    Each saved bridge is rebuilt against the FRESH pack (same id, preset, params, seed) so a re-graded or rescaled town gets a bridge that fits its new
    road ends and terrain; a saved bridge whose crossing is no longer detected is kept as saved (warning). bridges.json itself is not rewritten.
    Returns None when the place has no bridges, else {bridges, rebuilt, kept_as_saved, roads_with_gaps}."""
    import worldpack as wp
    doc = load_bridges(place, world_root)
    removed = set(doc.get("removed") or [])
    saved = [b for b in doc.get("bridges", []) if b["id"] not in removed]
    if not saved:
        return None
    pack = wp.load_pack(pack_dir)
    for r in pack.list("roads"):
        r.pop("gaps", None)
    found = {c["id"]: c for c in detect(pack, **{k: (doc.get("thresholds") or {}).get(k) for k in ("float_ft", "level_ft")})}
    match, used = {}, set()
    for b in saved:                                                  # same id first
        if b["id"] in found:
            match[b["id"]] = found[b["id"]]
            used.add(b["id"])
    for b in saved:                                                  # then the same road (or a clipped part of it, `<id>__pN`) and the same place on the map
        if b["id"] in match:
            continue
        sx, sy = b["span"]["start"][:2]
        ex, ey = b["span"]["end"][:2]
        mx, my, tol = 0.5 * (sx + ex), 0.5 * (sy + ey), max(20.0, 0.3 * float(b["span"].get("length_ft") or 0.0))
        best = None
        for c in found.values():
            if c["id"] in used or c["road"].split("__")[0] != str(b["road"]).split("__")[0]:
                continue
            cx_, cy_, _ = road_at(pack.get(c["road"])["points"], 0.5 * (c["s0_ft"] + c["s1_ft"]))
            d = math.hypot(cx_ - mx, cy_ - my)
            if d <= tol and (best is None or d < best[0]):
                best = (d, c)
        if best:
            match[b["id"]] = best[1]
            used.add(best[1]["id"])
    tmp = {}
    for b in saved:
        c = match.get(b["id"])
        if c:
            tmp.setdefault(c["road"], []).append({"s0_ft": c["s0_ft"], "s1_ft": c["s1_ft"]})
    for r in pack.list("roads"):
        if r["id"] in tmp:
            r["gaps"] = tmp[r["id"]]
    h_final = final_heights(pack) if tmp else None
    out, rebuilt, kept = [], [], []
    for b in saved:
        c = match.get(b["id"])
        if c is None:
            kept.append(b["id"])
            log(f"  bridges: {b['id']} no longer matches a detected crossing; kept as saved (re-apply it in the Bridges tab)")
            out.append(b)
            continue
        try:
            ent = make_entity(pack, c, h_final, preset=b["preset"], overrides=b.get("params") or None, seed=b.get("seed"), provenance=dict(b.get("provenance") or {}))
        except Exception as ex:                                      # never lose a bridge on export
            log(f"  bridges: {b['id']} rebuild failed ({ex}); kept as saved")
            kept.append(b["id"])
            out.append(b)
            continue
        for k in KEEP_ON_REFRESH:
            if k in b:
                ent[k] = b[k]
        out.append(ent)
        rebuilt.append(b["id"])
    res = inject(pack_dir, place, world_root, dict(doc, bridges=out, removed=sorted(removed)))
    res.update(rebuilt=rebuilt, kept_as_saved=kept)
    log(f"  bridges: {res['bridges']} from bridges.json ({len(rebuilt)} rebuilt on the new terrain, {len(kept)} kept as saved)")
    return res


def apply(place, pack_dir=None, only=None, preset=None, overrides=None, export=True, world_root=None, float_ft=None, level_ft=None, merge=True, seed=None):
    """detect -> bridges.json (provenance) -> re-export the pack -> inject. `merge` keeps manual entries already in bridges.json (same id wins from the file
    unless `only` lists it)."""
    import worldpack as wp
    root = world_root or WORLD
    pack_dir = pack_dir or os.path.join(root, place, "export")
    if export:
        wp.export_world(place, pack_dir) if world_root is None else wp.export_world(place, pack_dir, world_root=world_root)
    pack = wp.load_pack(pack_dir)
    old = load_bridges(place, root)
    # detection must see the roads without earlier gaps
    for r in pack.list("roads"):
        r.pop("gaps", None)
    found = detect(pack, float_ft=float_ft, level_ft=level_ft)
    if only:
        found = [c for c in found if c["id"] in only]
    keep = {b["id"]: b for b in old.get("bridges", []) if merge and b.get("locked") and (not only or b["id"] not in only)}   # `locked`: set by the panel's Apply-to-selected (hand-tuned)
    new = []
    # first pass with the planned gaps so the ground under each span is the final terrain
    tmp = {}
    for c in found:
        tmp.setdefault(c["road"], []).append({"s0_ft": c["s0_ft"], "s1_ft": c["s1_ft"]})
    for r in pack.list("roads"):
        if r["id"] in tmp:
            r["gaps"] = tmp[r["id"]]
    h_final = final_heights(pack)
    culture = (_jload(os.path.join(root, place, "place.json")) if os.path.exists(os.path.join(root, place, "place.json")) else {}).get("culture")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for c in found:
        if c["id"] in keep:
            continue
        prov = {"generated_at": now, "crossing": {k: c[k] for k in ("type", "span_ft", "deck_above_ground_ft")}}
        ent = None
        c.setdefault("culture", culture)
        first = choose_preset(c, override=preset)
        order = [first] if preset else [first] + [n for n in ("stone_arch", "brick_arch", "covered_timber", "flat_cut_stone", "wooden_truss", "plank_footbridge", "rough_log", "rope_plank") if n != first]
        best = None
        for k, name in enumerate(order):                               # the first preset whose plan meets the clearance wins; otherwise the one that misses least
            cand = make_entity(pack, c, h_final, preset=name, overrides=overrides, seed=seed, provenance=dict(prov))
            pl = make_plan(cand)
            if pl["ok"]:
                if k:
                    cand["provenance"]["fallback_from"] = order[0]
                best = cand
                break
            cand["provenance"]["clearance_deficit_m"] = round(pl["deficit_m"], 2)
            cand["provenance"]["warnings"] = pl["notes"]
            if best is None or pl["deficit_m"] < best["provenance"]["clearance_deficit_m"] - 1e-6:
                best = cand
        ent = best
        notes = str(pack.get(c["road"]).get("notes") or "").lower()
        for word, fams in (("stone", ("stone_arch", "flat_cut_stone")), ("brick", ("brick_arch",)), ("wood", ("wooden_truss", "plank_footbridge")), ("timber", ("wooden_truss", "plank_footbridge"))):
            if word in notes and ent["preset"] not in fams and not preset:
                ent["provenance"].setdefault("warnings", []).append(f"canon notes mention a {word} bridge but the clearance only fits {ent['preset']}; use --preset to override (the deck level is canon)")
                break
        if only or overrides or preset or seed is not None:
            ent["locked"] = True
        new.append(ent)
    bridges = list(keep.values()) + new
    bridges.sort(key=lambda b: b["id"])
    doc = {"place": place, "schema": SCHEMA, "generated_by": "bridge_maker.py", "generated_at": now, "status": "proposed",
           "notes": "Generated bridges; canon street data is untouched. Delete an entry (or list its id in `removed`) to drop it.", "thresholds": {k: v for k, v in DEFAULTS.items()},
           "removed": old.get("removed", []), "bridges": bridges}
    _jdump(bridges_path(place, root), doc)
    res = inject(pack_dir, place, root, doc)
    res.update(found=len(found), new=[b["id"] for b in new], report=found)
    return res


def remove(place, bid, world_root=None):
    doc = load_bridges(place, world_root)
    doc["bridges"] = [b for b in doc.get("bridges", []) if b["id"] != bid]
    if bid not in doc.setdefault("removed", []):
        doc["removed"].append(bid)
    _jdump(bridges_path(place, world_root), doc)
    return doc




def entity_for(place, bid, pack_dir=None, preset=None, overrides=None, world_root=None):
    """The entity for crossing/bridge `bid` with the given preset/overrides applied, without writing anything (preview). Uses world/<place>/bridges.json
    when the bridge exists there, otherwise detects it in the pack."""
    import worldpack as wp
    root = world_root or WORLD
    doc = load_bridges(place, root)
    ent = next((copy_deep(b) for b in doc.get("bridges", []) if b["id"] == bid), None)
    if ent is None:
        pack = wp.load_pack(pack_dir or os.path.join(root, place, "export"))
        for r in pack.list("roads"):
            r.pop("gaps", None)
        c = next((c for c in detect(pack) if c["id"] == bid), None)
        if c is None:
            raise KeyError(f"no crossing or bridge {bid!r} in {place}")
        tmp = {}
        for q in detect(pack):
            tmp.setdefault(q["road"], []).append({"s0_ft": q["s0_ft"], "s1_ft": q["s1_ft"]})
        for r in pack.list("roads"):
            if r["id"] in tmp:
                r["gaps"] = tmp[r["id"]]
        ent = make_entity(pack, c, final_heights(pack), preset=preset or choose_preset(c), overrides=overrides)
    if preset:
        ent["preset"] = preset
    if overrides:
        ent["params"] = dict(ent.get("params") or {}, **{k: v for k, v in overrides.items() if v is not None})
        if overrides.get("width_ft") is not None:
            ent["span"]["width_ft"] = float(overrides["width_ft"])
    return ent


def copy_deep(o):
    return json.loads(json.dumps(o))

# ------------------------------------------------------------------ 2D map symbol
def symbol_rings(ent):
    """The bridge as closed outlines in place feet (x east, y south), for the SVG map: [(suffix, ring, css class)]. Double parapet lines, pier/arch
    rectangles across the deck, plank hatch for timber bridges."""
    plan = make_plan(ent)
    sx, sy, _ = ent["span"]["start"]
    ex, ey, _ = ent["span"]["end"]
    L = math.hypot(ex - sx, ey - sy)
    d = np.array([ex - sx, ey - sy]) / L
    lf = np.array([d[1], -d[0]])

    def rect(u0, u1, v0, v1):
        return [[round(sx + d[0] * u / FT + lf[0] * v / FT, 2), round(sy + d[1] * u / FT + lf[1] * v / FT, 2)] for u, v in ((u0, v0), (u1, v0), (u1, v1), (u0, v1))]
    W = plan["W"]
    out = [("outline", rect(0, plan["L"], -W / 2, W / 2), "wall")]
    pt = plan["p"].get("parapet_t", 0.0)
    if plan["family"] in ("arch", "flat") and pt > 0:
        out.append(("inner", rect(0, plan["L"], -(W / 2 - pt), W / 2 - pt), "road"))
    if plan["family"] == "arch":
        for k, sd in enumerate(plan["solids"][1:-1], 1):
            out.append((f"pier{k}", rect(sd["u0"], sd["u1"], -W / 2, W / 2), "wall"))
        for k, a in enumerate(plan["arches"], 1):                                  # springing lines of every opening (hatch)
            out.append((f"arch{k}a", rect(a["ua"] - 0.05, a["ua"] + 0.05, -W / 2, W / 2), "road"))
            out.append((f"arch{k}b", rect(a["ub"] - 0.05, a["ub"] + 0.05, -W / 2, W / 2), "road"))
    elif plan["family"] == "flat":
        for k, sd in enumerate(plan["supports"][1:-1], 1):
            out.append((f"pier{k}", rect(sd["u0"], sd["u1"], -W / 2, W / 2), "wall"))
    else:
        for k, sd in enumerate(plan["supports"][1:-1], 1):
            out.append((f"bent{k}", rect(sd["u"] - 0.25, sd["u"] + 0.25, -W / 2, W / 2), "wall"))
        step = 1.8
        n = int(plan["L"] / step)
        for k in range(1, n):
            out.append((f"plank{k}", rect(k * plan["L"] / n - 0.03, k * plan["L"] / n + 0.03, -W / 2, W / 2), "road"))
    return out


def symbols_for_place(place, world_root=None):
    """[(entity id, suffix, ring, class)] for every bridge in world/<place>/bridges.json (not removed). Empty when there is none."""
    p = bridges_path(place, world_root)
    if not os.path.exists(p):
        return []
    doc = _jload(p)
    removed = set(doc.get("removed") or [])
    res = []
    for b in doc.get("bridges", []):
        if b["id"] in removed:
            continue
        try:
            for suf, ring, cls in symbol_rings(b):
                res.append((b["id"], suf, ring, cls))
        except Exception as e:                                  # a bad entry must not break the map
            log(f"bridge symbol {b.get('id')}: {e}")
    return res

# ------------------------------------------------------------------ street elevation repair (the floating-road bug)
def fix_elevations(place, world_root=None):
    """Child places extracted before region_extract.clip_vertex_values existed carry the parent's per-vertex elevations on clipped streets. Re-sample
    them from the parent street (matched by id, shifted by the region origin) so len(elevations_ft) == len(points) and the bed follows the road."""
    from shapely.geometry import LineString, Point
    root = world_root or WORLD
    pdir = os.path.join(root, place)
    sp = os.path.join(pdir, "streets.json")
    doc = _jload(sp)
    rg = os.path.join(pdir, "region.json")
    fixed = []
    parent_doc = org = None
    if os.path.exists(rg):
        reg = _jload(rg)
        pp = os.path.join(root, reg["parent"], "streets.json")
        if os.path.exists(pp):
            parent_doc = {s["id"]: s for s in _jload(pp)["streets"]}
            org = reg["transform"]["origin_ft"]
    for s in doc["streets"]:
        pts = s["geometry"]["points"]
        el = s.get("elevations_ft")
        if not el or len(el) == len(pts):
            continue
        pid = (s.get("region") or {}).get("parent_id") or s["id"].split("__")[0]
        if parent_doc and pid in parent_doc and len(parent_doc[pid].get("elevations_ft") or []) == len(parent_doc[pid]["geometry"]["points"]):
            ppts = parent_doc[pid]["geometry"]["points"]
            pel = parent_doc[pid]["elevations_ft"]
        else:                                                  # no parent to ask: the samples are uniform along the unclipped line, so spread them over the points
            ppts = pts
            pel = None
        if pel is not None:
            P = np.asarray(ppts, float)
            d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
            line = LineString(ppts)
            new = np.interp([line.project(Point(q[0] + org[0], q[1] + org[1])) for q in pts], d, pel)
        else:
            P = np.asarray(pts, float)
            d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(P, axis=0).T))])
            new = np.interp(d / max(d[-1], 1e-9), np.linspace(0, 1, len(el)), el)
        s["elevations_ft"] = [round(float(v), 1) for v in new]
        s["elevation_ft"] = round(float(np.mean(new)), 1)
        fixed.append(s["id"])
    if fixed:
        _jdump(sp, doc)
    return fixed


# ------------------------------------------------------------------ free-standing sample (style sheet, tests)
def sample_entity(preset, span_ft=60.0, drop_ft=14.0, water=True, width_ft=None, seed=7, road_class="street", name="sample", wall_slope=0.9):
    """A synthetic crossing: a straight deck over a V-shaped valley, a stream (or a road) in the bottom. Pure data, no pack needed."""
    pr = load_preset(preset)
    W = width_ft or pr["params"]["width_ft"]
    n = max(9, int(span_ft / 2) + 1)
    us = np.linspace(0, span_ft, n)
    wet = min(span_ft * 0.3, 18.0)
    c = span_ft / 2
    deck_z = 100.0 + LIFT_M / FT
    ground = (deck_z - LIFT_M / FT - drop_ft) + np.array([min(drop_ft, max(0.0, abs(u - c) - wet / 2) * wall_slope) for u in us])
    others = []
    if water:
        others.append(dict(kind="water", id="stream", u0_ft=c - wet / 2, u1_ft=c + wet / 2, surface_ft=float(deck_z - LIFT_M / FT - drop_ft + 0.8)))
    else:
        others.append(dict(kind="road", id="lane", u_ft=c, angle_deg=90.0, z_ft=float(deck_z - LIFT_M / FT - drop_ft + 0.3), width_ft=10.0))
    ent = {"id": f"brg_{name}_1", "kind": "bridge", "preset": preset, "seed": seed, "params": {}, "road": "sample", "crossing": "water" if water else "road",
           "span": {"s0_ft": 0.0, "s1_ft": span_ft, "length_ft": span_ft, "start": [0.0, 0.0, deck_z], "end": [span_ft, 0.0, deck_z], "width_ft": W, "road_class": road_class, "road_width_ft": W},
           "context": {"deck": [[float(u), deck_z] for u in us], "ground_hi": [[float(u), float(v)] for u, v in zip(us, ground)], "ground_lo": [[float(u), float(v) - 0.3] for u, v in zip(us, ground)],
                       "others": others, "deck_material": "mat_cobble", "deck_tile_ft": 7.0}}
    return ent


def mesh_stats(ent):
    m, plan = build_local(ent)
    return dict(tris=m.tri_count, verts=len(m.V), materials=sorted(m.subs), ok=plan["ok"], notes=plan["notes"], clearance_violations=check_clearance(m, plan))


# ------------------------------------------------------------------ CLI
def _pack(a):
    import worldpack as wp
    path = a.pack or os.path.join(WORLD, a.place, "export")
    if not os.path.exists(os.path.join(path, "manifest.json")):
        sys.exit(f"bridge_maker: {a.place} has no exported world pack ({path}). Export the 3D pack first (worldpack.py export --place {a.place}, or the Export tab), then detect.")
    return wp.load_pack(path)


def _overrides(pairs):
    ov = {}
    for kv in pairs or []:
        k, v = kv.split("=", 1)
        try:
            ov[k] = json.loads(v)
        except ValueError:
            ov[k] = v
    return ov


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("presets")
    for name in ("detect", "apply", "inject", "remove", "fix-elevations"):
        s = sub.add_parser(name)
        s.add_argument("--place", required=True)
        s.add_argument("--pack")
        s.add_argument("--out")
        s.add_argument("--float-ft", type=float)
        s.add_argument("--level-ft", type=float)
        s.add_argument("--only")
        s.add_argument("--preset")
        s.add_argument("--set", action="append", default=[], help="key=value parameter override (width_ft, clearance_h_ft, parapet_h_ft, n_arches, rise_ratio...)")
        s.add_argument("--no-export", action="store_true")
        s.add_argument("--id")
        s.add_argument("--seed", type=int)
    au = sub.add_parser("audit")
    au.add_argument("--place", required=True)
    au.add_argument("--pack")
    au.add_argument("--out")
    en = sub.add_parser("entity")
    en.add_argument("--place", required=True)
    en.add_argument("--pack")
    en.add_argument("--id", required=True)
    en.add_argument("--preset")
    en.add_argument("--set", action="append", default=[])
    en.add_argument("--out")
    sm = sub.add_parser("sample")
    sm.add_argument("--preset", required=True)
    sm.add_argument("--span-ft", type=float, default=60.0)
    sm.add_argument("--drop-ft", type=float, default=14.0)
    sm.add_argument("--road", action="store_true", help="a road passes under instead of a stream")
    a = ap.parse_args(argv)
    if a.cmd == "presets":
        print(json.dumps([{k: p[k] for k in ("id", "name", "family", "description")} for p in list_presets()], indent=1))
    elif a.cmd == "fix-elevations":
        print(json.dumps({"fixed": fix_elevations(a.place)}))
    elif a.cmd == "detect":
        res = detect(_pack(a), a.float_ft, a.level_ft)
        if a.out:
            _jdump(a.out, res)
        print(json.dumps({"ok": True, "crossings": res}))
    elif a.cmd == "audit":
        import worldpack as wp
        pack = _pack(a)
        for r in pack.list("roads"):
            r.pop("gaps", None)
        h = final_heights(pack)
        res = []
        for e in load_bridges(a.place)["bridges"]:
            au_ = audit_mesh(e, h, pack.cell_ft)
            res.append(dict(id=e["id"], preset=e["preset"], min_foot_margin_ft=au_["min_foot_margin_ft"], deck_clear_min_ft=au_["deck_clear_min_ft"], deck_clear_ends_ft=au_["deck_clear_ends_ft"],
                            feet=au_["feet"]))
        if a.out:
            _jdump(a.out, res)
        print(json.dumps({"ok": True, "bridges": [{k: v for k, v in r.items() if k != "feet"} for r in res]}, indent=1))
    elif a.cmd == "entity":
        ent = entity_for(a.place, a.id, a.pack, a.preset, _overrides(a.set))
        if a.out:
            _jdump(a.out, ent)
        print(json.dumps({"ok": True, "entity": {k: ent[k] for k in ("id", "preset", "crossing", "span", "params")}, "stats": mesh_stats(ent)}))
    elif a.cmd == "apply":
        ov = _overrides(a.set)
        res = apply(a.place, a.pack, set(a.only.split(",")) if a.only else None, a.preset, ov or None, export=not a.no_export, float_ft=a.float_ft, level_ft=a.level_ft, seed=a.seed)
        print(json.dumps({"ok": True, **res}))
    elif a.cmd == "inject":
        print(json.dumps({"ok": True, **inject(a.pack or os.path.join(WORLD, a.place, "export"), a.place)}))
    elif a.cmd == "remove":
        remove(a.place, a.id)
        print(json.dumps({"ok": True, "removed": a.id}))
    elif a.cmd == "sample":
        print(json.dumps({"ok": True, **mesh_stats(sample_entity(a.preset, a.span_ft, a.drop_ft, not a.road))}))


if __name__ == "__main__":
    main()
