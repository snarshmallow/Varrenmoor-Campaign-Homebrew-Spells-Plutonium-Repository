"""Eirwitch Camp (Night): a purpose-built winter mountain place outside Bridgehollow, rebuilt end to end by one idempotent script.

A clearing of about 130 ft high in the mountains with ONE campfire exactly at its centre, a tall narrow two-storey stave church at the north edge
facing the fire, dense snowy pine forest all round, a dirt road from the west edge that dead-ends in the clearing, and a steep-walled fjord-like river
gorge east of the clearing (about 100 ft deep, water at the bottom, emptying into a fjord arm in the south-east) crossed by a rope bridge whose west
landing is a short footpath to the clearing. Layout and numbers: illustrator/out/eirwitch_camp_notes.md.

  python illustrator/generators/eirwitch_camp.py design  [--dry-run]   place, terrain (edit layer), water, roads, church, foliage (light, < 1 min)
  python illustrator/generators/eirwitch_camp.py build   [--dry-run]   world pack export -> rope bridge -> split -> merge (winter foliage) -> campfire + lights -> night sky
                                                                        (needs >= 3 GB free RAM)
  python illustrator/generators/eirwitch_camp.py push    [--dry-run]   NEW Foundry scene 'Eirwitch Camp (Night)' (push-models, then push-scene-3d), via the bridge
  python illustrator/generators/eirwitch_camp.py verify                read-only scene summary + scene-audit
  python illustrator/generators/eirwitch_camp.py all     [--dry-run]   design + build + push + verify

Feet, place frame: origin top-left (north-west), x east, y SOUTH (down the page), z up. Every step rewrites its own files from the constants below,
so running it twice gives the same place (the foliage scatter is seeded). Only world/eirwitch_camp and its own export are written.
"""
import argparse
import glob
import json
import math
import os
import re
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

PLACE = "eirwitch_camp"
NAME = "Eirwitch Camp"
SCENE_NAME = "Eirwitch Camp (Night)"
SIZE = (1200.0, 900.0)
CELL = 6.0
SEED = 1713
PX_PER_FT = 10.0                      # 5 ft grid = 50 px (playable scale)

# ---- layout (feet)
CLEAR_C = (560.0, 470.0)              # clearing centre = campfire
CLEAR_R = 65.0                        # level clearing radius
CLEAR_Z = 3200.0                      # clearing level (ft above the datum)
FIRE = CLEAR_C
CHURCH = {"id": "bld_eirwitch_church", "name": "Eirwitch Stave Church", "center": (560.0, 422.0), "width": 14.0, "depth": 20.0, "floors": 2,
          "style": "eirwitch_stave_church"}
ROAD = {"id": "str_witch_road", "name": "Witch Road", "width": 12.0,
        "points": [(0.0, 655.0), (70.0, 640.0), (150.0, 655.0), (230.0, 632.0), (300.0, 603.0), (370.0, 585.0), (430.0, 560.0), (480.0, 528.0), (520.0, 494.0)]}
PATH = {"id": "str_gorge_path", "name": "Gorge Footpath", "width": 4.0,
        "points": [(626.0, 470.0), (680.0, 470.0), (734.0, 470.0), (790.0, 470.0), (852.0, 470.0), (900.0, 478.0), (960.0, 505.0), (1040.0, 540.0), (1120.0, 568.0), (1200.0, 590.0)]}
PATH_EAST = 4                         # index of the first footpath vertex east of the gorge (the east landing)
PATH_SPAN = (734.0, 852.0)            # x range of the footpath carried by the rope bridge (rim to rim + anchors)
GORGE = [(775.0, -20.0), (762.0, 150.0), (772.0, 300.0), (790.0, 470.0), (815.0, 600.0), (868.0, 718.0), (955.0, 798.0), (1050.0, 850.0), (1110.0, 880.0)]
GORGE_BED_HALF = 18.0                 # flat floor half width
GORGE_WALL = 34.0                     # horizontal run of the walls (rim at 52 ft from the axis)
GORGE_BED_Z = (3112.0, 3074.0)        # floor level at the north edge -> at the fjord
RIVER_W = 24.0
FJORD = {"c": (1140.0, 900.0), "r": (250.0, 160.0), "level": 3072.0, "floor": 3040.0, "wall": 45.0}
LEDGE = (868.0, 470.0)                # rocky landing east of the gorge
LIGHT_K = 1800

FOREST_MIX = [{"species": "spruce", "weight": 4.0}, {"species": "scots_pine", "weight": 3.0}, {"species": "fir", "weight": 2.0}]
UNDER_MIX = [{"species": "juniper", "weight": 2.0}, {"species": "boulder", "weight": 1.0}]

G = os.path.join("illustrator", "generators")


def LOG(*a):
    print(*a, file=sys.stderr, flush=True)


def world_dir(root=None):
    return os.path.join(root or os.path.join(REPO, "world"), PLACE)


def _rj(p, d=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return d


def _wj(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def _py(args, env=None):
    e = dict(os.environ)
    e.update(env or {})
    LOG("$ python " + " ".join(args))
    r = subprocess.run([sys.executable] + args, cwd=REPO, env=e, capture_output=True, text=True)
    last = None
    for ln in (r.stdout or "").splitlines():
        if ln.startswith("{"):
            try:
                last = json.loads(ln)
            except ValueError:
                pass
    if r.returncode != 0:
        tail = "\n".join(((r.stdout or "") + (r.stderr or "")).splitlines()[-25:])
        raise RuntimeError(f"{os.path.basename(args[0])} failed ({r.returncode}):\n{tail}")
    return last if last is not None else {}


# ------------------------------------------------------------------ geometry helpers
def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def polyline_dist(X, Y, pts):
    """Distance from (X, Y) arrays to a polyline, and the arc length of the nearest point."""
    P = np.asarray(pts, float)
    best = np.full(np.shape(X), np.inf)
    sbest = np.zeros(np.shape(X))
    s0 = 0.0
    for (ax, ay), (bx, by) in zip(P[:-1], P[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        t = np.clip(((X - ax) * dx + (Y - ay) * dy) / L2, 0, 1)
        d = np.hypot(X - (ax + t * dx), Y - (ay + t * dy))
        m = d < best
        best = np.where(m, d, best)
        sbest = np.where(m, s0 + t * math.sqrt(L2), sbest)
        s0 += math.sqrt(L2)
    return best, sbest, s0


def gauss_blur(a, sigma):
    from scipy import ndimage as ndi
    return ndi.gaussian_filter(a, sigma, mode="nearest")


def fjord_q(X, Y):
    (cx, cy), (rx, ry) = FJORD["c"], FJORD["r"]
    return np.hypot((X - cx) / rx, (Y - cy) / ry)


def design_heights(base, cell=CELL):
    """The designed terrain (absolute feet) from the blank place's highland_ridge heightmap (used only for its natural roughness)."""
    ny, nx = base.shape
    X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
    b = base.astype(np.float64)
    large = gauss_blur(b, 120.0 / cell)
    small = b - gauss_blur(b, 36.0 / cell)                    # rock-scale roughness, a few ft
    lg = (large - large.mean()) / max(large.std(), 1e-6)
    E = CLEAR_Z + 22.0 * lg + 0.9 * small
    E += 250.0 * smoothstep((330.0 - Y) / 330.0)              # mountains rise to the north
    for (px, py, a, r) in ((110.0, 60.0, 230.0, 240.0), (470.0, -50.0, 150.0, 210.0), (1110.0, 80.0, 270.0, 240.0), (1210.0, 260.0, 110.0, 170.0),
                           (60.0, 380.0, 90.0, 170.0)):
        E += a * np.exp(-((X - px) ** 2 + (Y - py) ** 2) / (2 * r * r))
    E -= 45.0 * smoothstep((420.0 - X) / 420.0) * smoothstep((Y - 430.0) / 280.0)     # the road comes up from the lower south-west
    E -= 60.0 * smoothstep((Y - 640.0) / 260.0) * smoothstep((X - 560.0) / 500.0)      # slope down to the fjord
    # the clearing sits at the natural level of its surroundings (no pit): shift the macro relief so the ring 60-160 ft round the fire averages CLEAR_Z
    rc0 = np.hypot(X - CLEAR_C[0], Y - CLEAR_C[1])
    ring = (rc0 > 60.0) & (rc0 < 160.0)
    E += CLEAR_Z - float(np.mean(E[ring]))
    # east shoulder: a gentler bench of ground beyond the gorge so the footpath can climb away from the bridge
    rs = np.hypot(X - 960.0, Y - 520.0)
    E = E + (CLEAR_Z + 8.0 + 0.5 * (E - CLEAR_Z) * 0.3 - E) * 0.9 * (1.0 - smoothstep((rs - 90.0) / 130.0))
    # road bench: follow a smoothed profile within the corridor, ending at the clearing level
    E = _bench(E, X, Y, ROAD["points"], ROAD["width"], end_z=CLEAR_Z, cell=cell)
    # east footpath bench from the rocky ledge to the east edge
    E = _bench(E, X, Y, PATH["points"][PATH_EAST:], PATH["width"] + 4.0, start_z=CLEAR_Z + 3.0, cell=cell, margin=18.0)
    # clearing: level, blended out over 45 ft
    rc = np.hypot(X - CLEAR_C[0], Y - CLEAR_C[1])
    wc = 1.0 - smoothstep((rc - CLEAR_R) / 70.0)
    E = E + (CLEAR_Z + 0.25 * small - E) * wc
    # footpath shelf from the clearing to the gorge rim, and the rocky ledge beyond it
    d_p, _, _ = polyline_dist(X, Y, PATH["points"][:3])
    E = E + (CLEAR_Z - E) * (1.0 - smoothstep((d_p - 6.0) / 22.0))
    rl = np.hypot(X - LEDGE[0], Y - LEDGE[1])
    E = E + (CLEAR_Z + 3.0 + 0.6 * small - E) * (1.0 - smoothstep((rl - 30.0) / 35.0))
    # gorge: steep walls (cliff at the rim, talus at the foot), floor descending to the fjord
    d_g, s_g, L_g = polyline_dist(X, Y, GORGE)
    jag = 5.0 * small / max(np.abs(small).max(), 1e-6) * 2.0
    bed = GORGE_BED_Z[0] + (GORGE_BED_Z[1] - GORGE_BED_Z[0]) * (s_g / L_g)
    t = np.clip((d_g + jag - GORGE_BED_HALF) / GORGE_WALL, 0.0, 1.0)
    f = 0.55 * np.sqrt(1.0 - t) + 0.45 * (1.0 - t)
    E = np.where(E > bed, E - (E - bed) * f, E)
    # fjord arm in the south-east corner
    q = fjord_q(X, Y)
    rmin = min(FJORD["r"])
    tq = np.clip((q - 1.0) * rmin / FJORD["wall"], 0.0, 1.0)
    fq = 0.55 * np.sqrt(1.0 - tq) + 0.45 * (1.0 - tq)
    E = np.where(E > FJORD["floor"], E - (E - FJORD["floor"]) * fq, E)
    return E.astype(np.float32)


def _bench(E, X, Y, pts, width, cell=CELL, start_z=None, end_z=None, margin=26.0):
    """Cut / fill a corridor along a polyline to a smoothed profile of the ground (box filter over ~90 ft), pinned at start_z / end_z."""
    import worldpack as wp
    d, s, L = polyline_dist(X, Y, pts)
    ss = np.linspace(0, L, 200)
    rp = _resample(pts, ss)
    prof = np.array([wp.bilinear(E, cell, x, y) for x, y in rp])
    k = 31
    prof = np.convolve(np.pad(prof, k // 2, mode="edge"), np.ones(k) / k, mode="valid")
    if end_z is not None:
        prof[-12:] = np.linspace(prof[-12], end_z, 12)
    if start_z is not None:
        prof[:60] = np.linspace(start_z, prof[59], 60)
    z = np.interp(s, ss, prof)
    w = 1.0 - smoothstep((d - width / 2 - 4.0) / margin)
    return E + (z - E) * w


def _resample(pts, ss):
    P = np.asarray(pts, float)
    seg = np.hypot(*np.diff(P, axis=0).T)
    cum = np.r_[0, np.cumsum(seg)]
    return np.c_[np.interp(ss, cum, P[:, 0]), np.interp(ss, cum, P[:, 1])]


# ------------------------------------------------------------------ data files
def gorge_centerline(step=6.0):
    P = np.asarray(GORGE, float)
    seg = np.hypot(*np.diff(P, axis=0).T)
    L = float(seg.sum())
    ss = np.arange(0.0, L + 1e-6, step)
    pts = _resample(GORGE, ss)
    keep = (pts[:, 1] >= 0) & (pts[:, 0] <= SIZE[0]) & (fjord_q(pts[:, 0], pts[:, 1]) > 0.95)
    return [[round(float(x), 2), round(float(y), 2)] for x, y in pts[keep]]


def water_doc():
    from shapely.geometry import LineString, Point, Polygon, box
    cl = gorge_centerline()
    river = LineString(cl).buffer(RIVER_W / 2, cap_style=2)
    rect = box(0, 0, SIZE[0], SIZE[1])
    (cx, cy), (rx, ry) = FJORD["c"], FJORD["r"]
    ell = Polygon([(cx + rx * 1.1 * math.cos(a), cy + ry * 1.1 * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 72, endpoint=False)]).intersection(rect)
    rp = river.intersection(rect).difference(ell)
    if rp.geom_type != "Polygon":
        rp = max(rp.geoms, key=lambda g: g.area)
    ring = lambda g: [[round(x, 2), round(y, 2)] for x, y in list(g.exterior.coords)[:-1]]
    return {"place": PLACE, "water": [
        {"id": "wat_gorge_river", "name": "Gorge river", "kind": "river", "status": "proposed", "geometry": {"type": "polygon", "points": ring(rp)},
         "notes": "eirwitch_camp.py: river at the floor of the gorge, flows south into the fjord arm", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
         "centerline": cl, "widths_ft": [RIVER_W] * len(cl), "width_ft": RIVER_W, "depth_ft": 2.5, "flow": "downstream along the centreline", "surface_ft": None},
        {"id": "wat_fjord", "name": "Fjord arm", "kind": "lake", "status": "proposed", "geometry": {"type": "polygon", "points": ring(ell)},
         "notes": "eirwitch_camp.py: still fjord water below the gorge mouth", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
         "level_ft": FJORD["level"], "depth_ft": FJORD["level"] - FJORD["floor"]},
    ]}


def streets_doc(h, edits_hash=None):
    import worldpack as wp
    road = {"id": ROAD["id"], "name": ROAD["name"], "kind": "lane", "status": "proposed",
            "geometry": {"type": "polyline", "points": [list(p) for p in ROAD["points"]], "width_ft": ROAD["width"]},
            "edit": {"class": "lane", "surface": "dirt", "kerb": False},
            "notes": "eirwitch_camp.py: dirt road from the west edge, dead-ends in the clearing"}
    zs = []
    xa, xb = PATH_SPAN
    za = float(wp.bilinear(h, CELL, xa, 470.0))
    zb = float(wp.bilinear(h, CELL, xb, 470.0))
    pts = path_points_dense()
    for x, y in pts:
        if xa < x < xb:
            zs.append(round(za + (zb - za) * (x - xa) / (xb - xa), 2))
        else:
            zs.append(round(float(wp.bilinear(h, CELL, x, y)), 2))
    path = {"id": PATH["id"], "name": PATH["name"], "kind": "lane", "status": "proposed",
            "geometry": {"type": "polyline", "points": pts, "width_ft": PATH["width"]},
            "edit": {"class": "lane", "surface": "dirt", "kerb": False}, "elevations_ft": zs, "elevation_ft": round(float(np.mean(zs)), 2), "elevations_edits_hash": edits_hash,
            "notes": "eirwitch_camp.py: footpath from the clearing over the gorge (rope bridge) to the east edge"}
    return {"place": PLACE, "streets": [road, path]}


def path_points_dense(step=12.0):
    """Footpath vertices every ~12 ft on land (so its bed follows the ground), the span over the gorge kept as one straight run."""
    out = []
    P = PATH["points"]
    for (ax, ay), (bx, by) in zip(P[:-1], P[1:]):
        L = math.hypot(bx - ax, by - ay)
        n = 1 if PATH_SPAN[0] <= min(ax, bx) and max(ax, bx) <= PATH_SPAN[1] else max(1, int(round(L / step)))
        for k in range(n):
            out.append([round(ax + (bx - ax) * k / n, 2), round(ay + (by - ay) * k / n, 2)])
    out.append([P[-1][0], P[-1][1]])
    return out


def church_footprint():
    (cx, cy), w, d = CHURCH["center"], CHURCH["width"], CHURCH["depth"]
    return [[cx - w / 2, cy - d / 2], [cx + w / 2, cy - d / 2], [cx + w / 2, cy + d / 2], [cx - w / 2, cy + d / 2]]


def church_doc(h):
    import worldpack as wp
    pts = church_footprint()
    zz = [float(wp.bilinear(h, CELL, x, y)) for x, y in pts]
    return {"id": CHURCH["id"], "name": CHURCH["name"], "kind": "church", "status": "proposed",
            "geometry": {"type": "polygon", "points": pts}, "notes": "The supposed eirwitch's stave church: tall, narrow, two storeys, door facing the campfire (south).",
            "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": CHURCH["floors"], "rooms": [],
            "doors": [], "style": CHURCH["style"], "elevation_ft": round(max(zz), 2), "site_slope": 0.0, "site_relief_ft": round(max(zz) - min(zz), 2)}


def details_doc():
    """Front door on the south gable (edge 2 of the footprint: (x+w/2, y+d/2) -> (x-w/2, y+d/2)), facing the fire."""
    return {"doors": [{"building": CHURCH["id"], "edge": 2, "pos": 0.5, "width_ft": 3.5}]}


# ------------------------------------------------------------------ foliage
def forest_zones():
    """Forest polygons: the place minus the clearing (cut into 4 simply connected quarters so no polygon has a hole). Roads, water and the church are
    avoided by the scatter itself; steep gorge walls by slope_max."""
    from shapely.geometry import Point, box
    rect = box(0, 0, SIZE[0], SIZE[1])
    hole = Point(CLEAR_C).buffer(CLEAR_R + 6.0, 48)
    cx, cy = CLEAR_C
    quads = [box(0, 0, cx, cy), box(cx, 0, SIZE[0], cy), box(0, cy, cx, SIZE[1]), box(cx, cy, SIZE[0], SIZE[1])]
    out = []
    for k, q in enumerate(quads):
        g = q.intersection(rect).difference(hole)
        out.append([[round(x, 1), round(y, 1)] for x, y in list(g.exterior.coords)[:-1]])
    return out


def foliage_params():
    zones = []
    base = {"size_var": 0.45, "pattern": "uniform", "avoid_buildings": True, "avoid_roads": True, "avoid_water": True, "clearance_building_ft": 12,
            "clearance_road_ft": 5, "slope_max_deg": 40, "replace_zone": True}
    for k, poly in enumerate(forest_zones()):
        zones.append({**base, "zone": f"ec_forest_{k + 1}", "name": f"Dense pines {k + 1}", "polygon": poly, "mix": FOREST_MIX, "density_per_ha": 360,
                      "seed": SEED + k, "max_instances": 1400})
        zones.append({**base, "zone": f"ec_under_{k + 1}", "name": f"Juniper and boulders {k + 1}", "polygon": poly, "mix": UNDER_MIX, "density_per_ha": 18,
                      "seed": SEED + 50 + k, "max_instances": 120, "pattern": "uniform", "slope_max_deg": 50})
    return zones


def foliage_violations(items):
    """Trees that break the layout rules (inside the clearing or on the road / path corridor). -> list of ids."""
    bad = []
    for it in items:
        x, y = it["x"], it["y"]
        if math.hypot(x - CLEAR_C[0], y - CLEAR_C[1]) < CLEAR_R:
            bad.append(it.get("id"))
            continue
        for st, w in ((ROAD, ROAD["width"]), (PATH, PATH["width"])):
            d, _, _ = polyline_dist(np.array([x]), np.array([y]), st["points"])
            if d[0] < w / 2 + 3.0:
                bad.append(it.get("id"))
                break
    return bad


def run_foliage(dry=False):
    zones = foliage_params()
    if dry:
        return {"zones": len(zones)}
    wd = world_dir()
    _wj(os.path.join(wd, "eirwitch_foliage_params.json"), {"zones": zones})
    out = {}
    for z in zones:
        pf = os.path.join(wd, f"_scatter_{z['zone']}.json")
        _wj(pf, z)
        try:
            r = _py([os.path.join(G, "foliage.py"), "scatter", "--place", PLACE, "--params", pf])
            out[z["zone"]] = r.get("added", r.get("total"))
        finally:
            if os.path.exists(pf):
                os.remove(pf)
    fp = os.path.join(wd, "foliage.json")
    doc = _rj(fp, {})
    items = doc.get("items", [])
    bad = set(foliage_violations(items))
    if bad:
        doc["items"] = [i for i in items if i.get("id") not in bad]
        _wj(fp, doc)
    _py([os.path.join(G, "foliage.py"), "export", "--place", PLACE])
    trees = [i for i in doc.get("items", []) if i.get("species") in ("spruce", "scots_pine", "fir")]
    return {"zones": out, "removed_rule_breakers": len(bad), "items": len(doc.get("items", [])), "trees": len(trees)}


# ------------------------------------------------------------------ design step
def design(dry=False):
    import heightmap_paint as hp
    wd = world_dir()
    res = {"place": PLACE, "dry_run": dry}
    if not os.path.exists(os.path.join(wd, "place.json")):
        args = [os.path.join(G, "place_create.py"), "create-blank", "--name", NAME, "--id", PLACE, "--size-ft", str(int(SIZE[0])), str(int(SIZE[1])),
                "--recipe", "highland_ridge", "--relief-ft", "160", "--cell-ft", str(CELL), "--seed", str(SEED)] + (["--dry-run"] if dry else [])
        res["create"] = _py(args)
        if dry:
            res["note"] = "place does not exist yet: the dry run stops after the create-blank check"
            return res
    base = np.load(os.path.join(wd, "terrain", "heightmap.npy"))
    h = design_heights(base)
    res["terrain"] = {"min": round(float(h.min()), 1), "max": round(float(h.max()), 1), "clearing": round(float(h[int(CLEAR_C[1] / CELL), int(CLEAR_C[0] / CELL)]), 1)}
    if dry:
        res["plan"] = {"water": [w["id"] for w in water_doc()["water"]], "streets": [ROAD["id"], PATH["id"]], "buildings": [CHURCH["id"]],
                       "foliage_zones": len(foliage_params())}
        return res
    delta = (h - base.astype(np.float32)).astype(np.float32)
    hp.save_layer(wd, delta, {"strokes": [], "source": "eirwitch_camp.py design_heights (whole-map designed terrain as one edit layer)"}, CELL)
    # remove stale working copies of the paint layer so the panel shows the saved one
    _wj(os.path.join(wd, "water.json"), water_doc())
    _wj(os.path.join(wd, "streets.json"), streets_doc(h, hp.delta_hash(delta)))   # elevations are against the edited terrain already
    bdir = os.path.join(wd, "buildings")
    os.makedirs(bdir, exist_ok=True)
    for f in glob.glob(os.path.join(bdir, "*.json")):
        if os.path.basename(f) != CHURCH["id"] + ".json":
            os.remove(f)
    _wj(os.path.join(bdir, CHURCH["id"] + ".json"), church_doc(h))
    _py([os.path.join(G, "object_edit.py"), "set-door", "--place", PLACE, "--ids", CHURCH["id"], "--edge", "2", "--pos", "0.5", "--door-width", "3.5"])
    import shutil
    shutil.rmtree(os.path.join(wd, "buildings_backups"), ignore_errors=True)      # set-door's undo copies: the script itself is the recipe
    _wj(os.path.join(wd, "districts.json"), {"place": PLACE, "districts": []})
    pl = _rj(os.path.join(wd, "place.json"), {})
    pl["name"] = NAME
    pl["notes"] = ("Supposed camp of a lone ancient eirwitch in the mountains outside Bridgehollow (winter night): clearing with one campfire, tall stave church, "
                   "dense pines, dirt road dead-ending in the clearing, river gorge with a rope bridge. Built by illustrator/generators/eirwitch_camp.py.")
    pl["view_focus"] = {"town": [CLEAR_C[0], CLEAR_C[1]]}
    pl.setdefault("defaults", {}).update({"shading_preset": "alpine_winter", "padding_preset": "fjord-walls", "foliage_mix": "spruce_forest", "season": "winter",
                                          "fills_style": "winter"})
    pl["season"] = "winter"
    _wj(os.path.join(wd, "place.json"), pl)
    st = _rj(os.path.join(wd, "panel_state.json"), {}) or {}
    st.setdefault("shading", {})["preset"] = "alpine_winter"
    st.setdefault("town", {}).setdefault("fills", {})["style"] = "winter"
    _wj(os.path.join(wd, "panel_state.json"), st)
    res["foliage"] = run_foliage()
    res["layout"] = layout_report(h)
    return res


def layout_report(h=None):
    import worldpack as wp
    if h is None:
        import worldio
        h, _ = worldio.load_terrain(PLACE)
    z = lambda x, y: round(float(wp.bilinear(h, CELL, x, y)), 1)
    d_g = lambda x, y: float(polyline_dist(np.array([x]), np.array([y]), GORGE)[0][0])
    gx = 790.0
    return {"fire": list(FIRE), "fire_z": z(*FIRE), "clearing_r": CLEAR_R, "church_center": list(CHURCH["center"]), "church_front_to_fire_ft": round(FIRE[1] - (CHURCH["center"][1] + CHURCH["depth"] / 2), 1),
            "road_end": list(ROAD["points"][-1]), "road_end_to_fire_ft": round(math.hypot(ROAD["points"][-1][0] - FIRE[0], ROAD["points"][-1][1] - FIRE[1]), 1),
            "road_start_z": z(*ROAD["points"][0]), "gorge_floor_at_bridge": z(gx, 470.0), "gorge_rim_w": z(PATH_SPAN[0], 470.0), "gorge_rim_e": z(PATH_SPAN[1], 470.0),
            "gorge_depth_at_bridge_ft": round(min(z(PATH_SPAN[0], 470.0), z(PATH_SPAN[1], 470.0)) - z(gx, 470.0), 1),
            "bridge_span_ft": PATH_SPAN[1] - PATH_SPAN[0], "clearing_edge_to_gorge_axis_ft": round(d_g(CLEAR_C[0] + CLEAR_R, CLEAR_C[1]), 1)}


# ------------------------------------------------------------------ campfire prop + lights (written into the placements after the merge)
CAMPFIRE_LAYER = "props"
CAMPFIRE_REL = "models/props/eirwitch_campfire.glb"


def campfire_mesh():
    """Campfire in feet around its base (origin = fire centre on the ground): a ring of 11 stones, a teepee of 6 split logs, a bed of glowing embers and three
    emissive flame cones (no particles), about 2 ft tall; two log benches at 8 ft."""
    import streetlamps as sl
    b = sl.LB()
    rng = np.random.default_rng(SEED)
    for k in range(11):
        a = 2 * math.pi * k / 11 + rng.uniform(-0.08, 0.08)
        r = 2.2 + rng.uniform(-0.1, 0.1)
        s = 0.55 + rng.uniform(-0.1, 0.12)
        b.prism(r * math.cos(a), r * math.sin(a), -0.15, s * 0.65, s * 0.55, s * 0.35, 6, "mat_lamp_stone", a)
    b.prism(0, 0, -0.05, 0.12, 1.75, 1.6, 10, "mat_lamp_glow")                 # ember bed
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.3
        b.beam((1.45 * math.cos(a), 1.45 * math.sin(a), 0.1), (0.15 * math.cos(a), 0.15 * math.sin(a), 1.7), 0.32, "mat_lamp_wood_old")
    b.pyramid(0, 0, 0.1, 2.3, 0.75, 7, "mat_lamp_flame")
    b.pyramid(0.35, 0.2, 0.1, 1.6, 0.45, 6, "mat_lamp_glow")
    b.pyramid(-0.3, -0.25, 0.1, 1.45, 0.42, 6, "mat_lamp_glow")
    for a in (math.radians(200), math.radians(340)):                          # two log benches
        cx, cy = 8.0 * math.cos(a), 8.0 * math.sin(a)
        t = a + math.pi / 2
        b.beam((cx - 3 * math.cos(t), cy - 3 * math.sin(t), 0.55), (cx + 3 * math.cos(t), cy + 3 * math.sin(t), 0.55), 1.1, "mat_lamp_wood_old")
    return b.mesh()


def church_light_points():
    """Faint warm glow at three church windows (east and west long walls, upper storey on the west), 1 ft outside the wall, plus the door (south)."""
    (cx, cy), w, d = CHURCH["center"], CHURCH["width"], CHURCH["depth"]
    return [("win_e", cx + w / 2 + 1.0, cy, 7.0), ("win_w", cx - w / 2 - 1.0, cy - 3.0, 17.0), ("win_s", cx, cy + d / 2 + 1.0, 15.0)]


def lights_for(h):
    import streetlamps as sl
    import worldpack as wp
    zf = float(wp.bilinear(h, CELL, *FIRE))
    out = [{"id": "eirwitch_campfire", "type": "lamp", "style": "campfire", "road": None, "building": None, "point": [FIRE[0], FIRE[1]], "z_abs_ft": round(zf + 2.5, 2),
            "dim_ft": 50, "bright_ft": 15, "color": sl.kelvin_to_hex(LIGHT_K), "kelvin": LIGHT_K, "intensity": 0.8, "animation": "torch", "shadows": True}]
    zc = float(wp.bilinear(h, CELL, *CHURCH["center"]))
    for lid, x, y, dz in church_light_points():
        out.append({"id": f"eirwitch_church_{lid}", "type": "window", "building": CHURCH["id"], "point": [round(x, 2), round(y, 2)], "z_abs_ft": round(zc + dz, 2),
                    "dim_ft": 12, "bright_ft": 3, "color": "#ffb060", "kelvin": 2200, "intensity": 0.35, "shadows": False})
    return out


def apply_props(pack_dir, placements_paths):
    """Campfire tile (layer props) + the scene's 4 lights into each placements.json; every other light is dropped (the pack's derived interior lights)."""
    import hashlib
    import streetlamps as sl
    import worldpack as wp
    import worldpack_mesh as wm
    import worldpack_split as ws
    pack = wp.load_pack(pack_dir)
    h = wp.carved_heights(pack)
    styles = sl.load_styles()
    zf = float(wp.bilinear(h, pack.cell_ft, *FIRE))
    out = []
    for doc_path in placements_paths:
        base = os.path.dirname(os.path.abspath(doc_path))
        doc = _rj(doc_path)
        doc["files"] = [e for e in doc.get("files", []) if e.get("file") != CAMPFIRE_REL]
        m = campfire_mesh().transformed(sl.FT, 0.0, pack.frame.to_blender(FIRE[0], FIRE[1], zf))
        pv = sl._PackView(pack, styles)
        part = {"id": "eirwitch_campfire", "layer": CAMPFIRE_LAYER, "group": CAMPFIRE_LAYER, "instance": None, "mesh": m, "pivot": wm._pivot(m),
                "tags": {"layer": CAMPFIRE_LAYER, "group": CAMPFIRE_LAYER, "id": "eirwitch_campfire"}, "extras": {}}
        e = ws._entry(pv, CAMPFIRE_REL[len("models/"):], [part], set(), base, "external")
        p = os.path.join(base, *CAMPFIRE_REL.split("/"))
        sl._patch_emissive(p, pv.materials)
        with open(p, "rb") as f:
            raw = f.read()
        e["sha256"], e["bytes"] = hashlib.sha256(raw).hexdigest(), len(raw)
        e["ids"] = ["eirwitch_campfire"]
        doc["files"] = sorted(doc["files"] + [e], key=lambda x: x["file"])
        for f_ in doc["files"]:
            f_.pop("lights", None) if f_.get("lights") is not None else None
        doc["lights"] = lights_for(h)
        _wj(doc_path, doc)
        out.append({"placements": os.path.relpath(doc_path, REPO), "campfire_tris": e.get("tris"), "lights": len(doc["lights"])})
    return out


# ------------------------------------------------------------------ build (heavy, local)
def free_gb():
    try:
        import psutil
        return psutil.virtual_memory().available / 2 ** 30
    except Exception:
        return None


def latest_opt(preset="layer"):
    ds = sorted(glob.glob(os.path.join(world_dir(), "export", "optimized", f"{preset}_v*")), key=lambda d: int(re.sub(r"\D", "", d.rsplit("_v", 1)[1]) or 0))
    return ds[-1] if ds else None


EXPORT_ARGS = ["--roof-mode", "per_scene", "--interior-style", "plain", "--style", "winter",
               "--phases", os.path.join("illustrator", "presets", "terrain_phases", "alpine_winter.json")]


def build(dry=False, min_free_gb=3.0):
    steps = [
        [os.path.join(G, "worldpack.py"), "export", "--place", PLACE] + EXPORT_ARGS,
        "RM_BRIDGES",
        [os.path.join(G, "bridge_maker.py"), "apply", "--place", PLACE, "--preset", "rope_plank", "--set", "width_ft=3.5", "--no-export"],
        [os.path.join(G, "worldpack_split.py"), "split", "--place", PLACE, "--roof-mode", "per_scene"],
        [os.path.join(G, "worldpack_split.py"), "merge", "--place", PLACE, "--preset", "layer", "--compress", "none", "--foliage", "--foliage-impostor-ft", "320"],
        [os.path.join(G, "skybox.py"), "generate", "--place", PLACE, "--presets", "night", "--lighting-presets", "night"],
    ]
    if dry:
        return {"dry_run": True, "steps": [(" ".join(["python"] + s) if isinstance(s, list) else "delete world/eirwitch_camp/bridges.json") for s in steps] + ["(campfire tile + 4 lights into export/placements.json and the merged set)"]}
    g = free_gb()
    if g is not None and g < min_free_gb:
        raise RuntimeError(f"only {g:.1f} GB free RAM (< {min_free_gb} GB): run `python illustrator/generators/eirwitch_camp.py build` later")
    res = {}
    for s in steps:
        if s == "RM_BRIDGES":                                  # bridges.json entries are locked once applied: start fresh so a layout change is picked up
            bp = os.path.join(world_dir(), "bridges.json")
            if os.path.exists(bp):
                os.remove(bp)
            continue
        r = _py(s, env={"VB_FOLIAGE_SEASON": "winter"})
        res[os.path.basename(s[0]) + ":" + s[1]] = {k: r.get(k) for k in list(r)[:8]} if isinstance(r, dict) else r
    opt = latest_opt()
    if not opt:
        raise RuntimeError("merge wrote no optimized/layer_v* folder")
    pd = os.path.join(world_dir(), "export")
    res["props"] = apply_props(pd, [os.path.join(pd, "placements.json"), os.path.join(opt, "placements.json")])
    res["optimized"] = os.path.relpath(opt, REPO).replace("\\", "/")
    d = _rj(os.path.join(opt, "placements.json"))
    res["files"] = len(d["files"])
    res["layers"] = sorted({e.get("layer") for e in d["files"]})
    res["tris"] = int(sum(e.get("tris", 0) for e in d["files"]))
    res["bridges"] = [e["file"] for e in d["files"] if e.get("layer") == "bridges"]
    return res


# ------------------------------------------------------------------ push + verify (Foundry, via the bridge)
SKY, SUN = "night", "night"
PADDING_ARGS = ["--scene-padding=0.1", "--preset=fjord-walls", "--texture=winter", "--blend=80"]
SCENE_FLAGS = ["shadowBias=-0.0003"]


def _fp(args):
    return _py([os.path.join(G, "foundry_push.py")] + args)


def find_scene(br):
    import foundry_push as fpm
    hit = br.call("find_by_flag", documentName="Scene", id=f"scene:{PLACE}:{fpm.slug(SCENE_NAME)}")
    return hit[0]["uuid"] if hit else None


def push(dry=False):
    import foundry_push as fpm
    br = fpm.PsBridge()
    opt = latest_opt()
    if not opt:
        raise RuntimeError("no merged pack: run build first")
    pp = os.path.join(opt, "placements.json")
    full = os.path.join(world_dir(), "export", "placements.json")
    before = [s["name"] for s in br.call("list", collection="Scene")]
    uuid = find_scene(br)
    if not uuid and any(n.lower() == SCENE_NAME.lower() for n in before):
        raise RuntimeError(f"a scene named {SCENE_NAME} exists and was not created by this script: refusing")
    res = {"scene_name": SCENE_NAME, "scenes_before": len(before)}
    r = _fp(["push-models", "--place", PLACE, "--placements", pp, "--px-per-ft", str(PX_PER_FT), "--scene-mode", "3d"]
            + (["--scene-uuid", uuid, "--prune"] if uuid else ["--scene-name", SCENE_NAME]) + (["--dry-run"] if dry else []))
    if dry:
        res.update(dry_run=True, tiles=r.get("tiles"), exists=bool(uuid))
        return res
    uuid = r.get("scene_uuid") or uuid or find_scene(br)
    res["scene_uuid"] = uuid
    s3 = ["push-scene-3d", "--place", PLACE, "--scene-uuid", uuid, "--placements", pp, "--px-per-ft", str(PX_PER_FT), "--skybox-preset", SKY, "--sun-preset", SUN,
          "--with-lights", "--lighting-mode", "lights", "--max-lights", "6", "--lights-placements", full] + [f"--padding-arg={x}" for x in PADDING_ARGS] \
         + [f"--scene-flag={x}" for x in SCENE_FLAGS]
    r3 = _fp(s3)
    res["push_scene_3d"] = {"ok": r3.get("ok"), "order": r3.get("order"), "problems": r3.get("problems")}
    try:
        rr = _fp(["set-collision", "--scene-uuid", uuid, "--apply"])
        res["set_collision"] = {k: rr.get(k) for k in ("ok", "changed", "updated") if k in rr}
    except RuntimeError as e:
        res["set_collision"] = {"ok": False, "error": str(e)[-300:]}
    after = [s["name"] for s in br.call("list", collection="Scene")]
    res["scenes_after"] = len(after)
    res["scenes_removed"] = sorted(set(before) - set(after))
    res["scenes_added"] = sorted(set(after) - set(before))
    pl = _rj(os.path.join(world_dir(), "place.json"))
    pl.setdefault("links", {})["foundry_scene"] = uuid
    _wj(os.path.join(world_dir(), "place.json"), pl)
    return res


def verify():
    import foundry_push as fpm
    br = fpm.PsBridge()
    uuid = find_scene(br)
    if not uuid:
        return {"status": "not pushed"}
    sc = br.call("get", uuid=uuid)
    F, L3 = "varrenmoor", "levels-3d-preview"
    layers, coll, sight = {}, 0, 0
    bridges = []
    for t in sc.get("tiles", []):
        f = t.get("flags") or {}
        lay = (f.get(F) or {}).get("layer") or "other"
        layers[lay] = layers.get(lay, 0) + 1
        coll += bool((f.get(L3) or {}).get("collision"))
        sight += bool((f.get(L3) or {}).get("sight"))
        m = (f.get(L3) or {}).get("model3d") or ""
        if lay == "bridges" or "brg_" in m:
            bridges.append({"model": m.rsplit("/", 1)[-1], "collision": bool((f.get(L3) or {}).get("collision")), "layer": lay})
    lights = sc.get("lights", []) or []
    f3 = (sc.get("flags") or {}).get(L3) or {}
    res = {"scene_uuid": uuid, "name": sc.get("name"), "tiles": len(sc.get("tiles", [])), "layers": layers, "collision_tiles": coll, "sight_tiles": sight,
           "bridge_tiles": bridges, "lights": [{"id": ((l.get("flags") or {}).get(F) or {}).get("lightId"), "dim": (l.get("config") or {}).get("dim"),
                                                "anim": ((l.get("config") or {}).get("animation") or {}).get("type"),
                                                "shadow": ((l.get("flags") or {}).get(L3) or {}).get("castShadow")} for l in lights],
           "grid": {k: (sc.get("grid") or {}).get(k) for k in ("size", "distance")}, "size_px": [sc.get("width"), sc.get("height")],
           "flags": {k: f3.get(k) for k in ("auto3d", "exr", "fogColor", "fogNear", "fogFar", "ambientLightIntensity", "shadowBias", "sunPosition") if k in f3}}
    opt = latest_opt()
    if opt:
        try:
            a = _fp(["scene-audit", "--scene-uuid", uuid, "--placements", os.path.join(opt, "placements.json")])
            res["audit"] = {"clean": a.get("clean"), "counts": a.get("counts"), "missing": len(a.get("missing") or [])}
        except RuntimeError as e:
            res["audit"] = {"clean": False, "error": str(e)[-300:]}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["design", "build", "push", "verify", "layout", "all"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    out = {}
    if a.cmd in ("design", "all"):
        out["design"] = design(a.dry_run)
    if a.cmd == "layout":
        out["layout"] = layout_report()
    if a.cmd in ("build", "all"):
        out["build"] = build(a.dry_run)
    if a.cmd in ("push", "all"):
        out["push"] = push(a.dry_run)
    if a.cmd in ("verify",) or (a.cmd == "all" and not a.dry_run):
        out["verify"] = verify()
    print(json.dumps({"ok": True, **out}, default=str))


if __name__ == "__main__":
    main()
