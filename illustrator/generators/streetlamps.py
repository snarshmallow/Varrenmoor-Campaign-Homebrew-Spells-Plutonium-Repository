#!/usr/bin/env python3
"""Toggleable street lamps along the roads of a world pack: lamp posts as one 3D props tile (layer `streetlamps`) plus one AmbientLight (kind `lamp`) per lamp.

  streetlamps.py styles                                       JSON: the lamp styles (presets/streetlamps/styles.json)
  streetlamps.py plan   --place P [--config F] [options]      dry run: counts, per road, skipped by reason, light estimate (writes nothing)
  streetlamps.py apply  --place P [--config F] [--placements F ...] [options]
                                                              writes models/streetlamps/streetlamps.glb + a `streetlamps` placements entry + `lamp` lights into each placements.json
                                                              (enabled false = removes them again: the per-scene toggle). Idempotent: same input = same bytes.
  streetlamps.py preview [--out DIR] [--style S ...]          thumbnail PNG of every style (panel style picker)
  foundry_push.py set-streetlamps --scene-uuid U [--on|--off] [--light-config F] [--apply]
                                                              hide / show the lamp tile + lamp lights of an existing scene and retune the lamp lights in place (dry run unless --apply)

Placement (plan_lamps): for every road centreline (graded, per-vertex z) stations every `spacing_ft` (centred on the road, `end_margin_ft` clear at the ends), lamp on the left / right /
alternating / both sides at road half width + `offset_ft`. Road class: `dirt` = unpaved surface (dirt, mud, gravel, packed earth, sand), `side` = lane / alley, `main` = road / street;
only the ticked classes get lamps. Skipped: near a junction (`skip_junction_ft`), on or near bridges, near an exterior door (`skip_doors_ft`), inside a building footprint; a road that
would get fewer than `min_lamps` lamps gets none. Per-road override: street `edit.lamps` {on, style, spacing_ft} (object_edit set-road --set lamps.on=false ...) wins over the scene settings.
Heights: the graded road centreline z at the station (`ground: road`, default; the road ribbon is built from the same graded heights) or the raw terrain (`ground: terrain`); the footing is
buried 1 ft so a slope never shows a gap. Deterministic: ids lamp_<road>_<nnn>, jitter from a hash of seed + road + index.
Lights: kind `lamp` (priority 80 in the light budget, foundry_lightbudget.py), colour from a colour temperature (K) or a hex override, `dim_ft` / `bright_ft` radii, intensity, flicker
(Foundry light animation `torch`), shadows off by default (a shadow-casting light costs 6 extra scene passes, see FOUNDRY_3D_CANVAS_NOTES.md section 11).
Collision on, sight off (foundry_collision.py: layer `streetlamps`); posts are thin, they must not block vision.
"""
import argparse
import colorsys
import hashlib
import json
import math
import os
import random
import struct
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FT = 0.3048
LAYER = "streetlamps"
FILE_REL = "models/streetlamps/streetlamps.glb"
ENTRY_ID_SUFFIX = "streetlamps/streetlamps"
STYLES_PATH = os.path.join(HERE, "..", "presets", "streetlamps", "styles.json")
SIDES = ("left", "right", "alternating", "both")
CLASSES = ("main", "side", "dirt")
UNPAVED = ("mat_dirt", "mat_mud", "mat_packed_earth", "mat_sand")          # gravel streets count by their class (main / side)
SIDE_CLASS = ("lane", "alley", "path", "track")

DEFAULTS = {
    "enabled": False, "style": "wooden_oil", "spacing_ft": 60.0, "side": "alternating", "offset_ft": 1.5, "height_ft": 0.0,
    "classes": ["main", "side", "dirt"], "skip_junction_ft": 20.0, "skip_doors_ft": 8.0, "skip_bridges": True, "jitter_ft": 0.0, "seed": 7, "min_lamps": 2, "centre_short": False,
    "end_margin_ft": 6.0, "ground": "road", "wall_reach_ft": 14.0, "chunk_ft": 0.0,
    "light": {"enabled": True, "kelvin": 0, "color": "", "dim_ft": 0.0, "bright_ft": 0.0, "intensity": 0.0, "flicker": True, "shadows": False},
}
LIMITS = {"spacing_ft": (8.0, 400.0), "offset_ft": (0.0, 20.0), "height_ft": (0.0, 40.0), "skip_junction_ft": (0.0, 200.0), "skip_doors_ft": (0.0, 60.0), "jitter_ft": (0.0, 40.0),
          "min_lamps": (0, 50), "end_margin_ft": (0.0, 100.0), "wall_reach_ft": (2.0, 40.0), "chunk_ft": (0.0, 5000.0)}
LIGHT_LIMITS = {"kelvin": (0, 10000), "dim_ft": (0.0, 300.0), "bright_ft": (0.0, 200.0), "intensity": (0.0, 1.0)}


def load_styles(path=None):
    with open(path or STYLES_PATH, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ settings
def kelvin_to_hex(k):
    """Colour temperature (1000..10000 K) -> #rrggbb (Tanner Helland approximation). 2000 K = oil flame, 1800 K = candle / torch, 6500 K = daylight."""
    t = max(1000.0, min(10000.0, float(k))) / 100.0
    r = 255.0 if t <= 66 else 329.698727446 * ((t - 60) ** -0.1332047592)
    g = 99.4708025861 * math.log(t) - 161.1195681661 if t <= 66 else 288.1221695283 * ((t - 60) ** -0.0755148492)
    b = 255.0 if t >= 66 else (0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307)
    c = [int(round(max(0.0, min(255.0, v)))) for v in (r, g, b)]
    return "#%02x%02x%02x" % tuple(c)


def _num(v, lo, hi, key):
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{key}: expected a number, got {v!r}")
    if f != f or f < lo or f > hi:
        raise ValueError(f"{key}: {f:g} outside {lo:g}..{hi:g}")
    return f


def normalize_config(cfg=None, styles=None):
    """Defaults + validation (ValueError with a plain message). Unknown keys are ignored. Returns a new dict."""
    styles = styles or load_styles()
    cfg = cfg or {}
    out = json.loads(json.dumps(DEFAULTS))
    for k in DEFAULTS:
        if k == "light" or k not in cfg or cfg[k] is None:
            continue
        v = cfg[k]
        if k in ("enabled", "skip_bridges", "centre_short"):
            out[k] = bool(v)
        elif k == "style":
            if v not in styles["styles"]:
                raise ValueError(f"style {v!r} is not one of {', '.join(styles['styles'])}")
            out[k] = v
        elif k == "side":
            if v not in SIDES:
                raise ValueError(f"side {v!r} is not one of {', '.join(SIDES)}")
            out[k] = v
        elif k == "classes":
            cl = [c.strip() for c in (v.split(",") if isinstance(v, str) else v) if str(c).strip()]
            bad = [c for c in cl if c not in CLASSES]
            if bad:
                raise ValueError(f"road class {bad[0]!r} is not one of {', '.join(CLASSES)}")
            out[k] = cl
        elif k == "ground":
            if v not in ("road", "terrain"):
                raise ValueError("ground is road or terrain")
            out[k] = v
        elif k == "seed":
            out[k] = int(_num(v, -1e9, 1e9, k))
        elif k == "min_lamps":
            out[k] = int(_num(v, *LIMITS[k], k))
        else:
            out[k] = _num(v, *LIMITS[k], k)
    lt = cfg.get("light") or {}
    for k in ("kelvin", "dim_ft", "bright_ft", "intensity"):
        if lt.get(k) is not None:
            out["light"][k] = _num(lt[k], *LIGHT_LIMITS[k], "light." + k) if k != "kelvin" or float(lt[k]) == 0 else _num(lt[k], 1000, 10000, "light.kelvin")
    for k in ("enabled", "flicker", "shadows"):
        if lt.get(k) is not None:
            out["light"][k] = bool(lt[k])
    if lt.get("color") not in (None, ""):
        c = str(lt["color"])
        if not (len(c) == 7 and c[0] == "#" and all(x in "0123456789abcdefABCDEF" for x in c[1:])):
            raise ValueError(f"light.color {c!r} is not #rrggbb")
        out["light"]["color"] = c.lower()
    return out


def road_class(r):
    """main / side / dirt for a road entity (see module docstring)."""
    mat = (r.get("surface") or {}).get("material")
    if mat in UNPAVED:
        return "dirt"
    if (r.get("class") or r.get("kind")) in SIDE_CLASS:
        return "side"
    return "main"


def road_override(r):
    """Per-road lamp override from the road entity `edit.lamps` (validated): {on: bool, style, spacing_ft}."""
    lp = ((r.get("edit") or {}).get("lamps")) if isinstance(r.get("edit"), dict) else None
    out = {}
    if isinstance(lp, dict):
        if isinstance(lp.get("on"), bool):
            out["on"] = lp["on"]
        if isinstance(lp.get("style"), str) and lp["style"]:
            out["style"] = lp["style"]
        if isinstance(lp.get("spacing_ft"), (int, float)) and not isinstance(lp["spacing_ft"], bool) and LIMITS["spacing_ft"][0] <= lp["spacing_ft"] <= LIMITS["spacing_ft"][1]:
            out["spacing_ft"] = float(lp["spacing_ft"])
    return out


# ------------------------------------------------------------------ geometry helpers (feet, world frame x east, y south)
def _cum(pts):
    c = [0.0]
    for a, b in zip(pts, pts[1:]):
        c.append(c[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return c


def _at(pts, cum, s):
    """(x, y, z, tx, ty) at arc length s of a polyline [[x, y, z]...]."""
    s = max(0.0, min(cum[-1], s))
    i = 1
    while i < len(cum) - 1 and cum[i] < s:
        i += 1
    a, b = pts[i - 1], pts[i]
    seg = cum[i] - cum[i - 1] or 1e-9
    u = (s - cum[i - 1]) / seg
    tx, ty = (b[0] - a[0]) / seg, (b[1] - a[1]) / seg
    za, zb = (a[2] if len(a) > 2 else 0.0), (b[2] if len(b) > 2 else 0.0)
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, za + (zb - za) * u, tx, ty


def _seg_dist(p, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    u = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    qx, qy = ax + u * dx, ay + u * dy
    return math.hypot(p[0] - qx, p[1] - qy), (qx, qy)


def poly_dist(p, pts):
    return min(_seg_dist(p, a, b)[0] for a, b in zip(pts, pts[1:])) if len(pts) > 1 else math.inf


def _in_poly(p, poly):
    x, y, ins = p[0], p[1], False
    n = len(poly)
    for i in range(n):
        x1, y1, x2, y2 = poly[i][0], poly[i][1], poly[(i + 1) % n][0], poly[(i + 1) % n][1]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            ins = not ins
    return ins


def _seg_cross(a, b, c, d):
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    den = r[0] * s[1] - r[1] * s[0]
    if abs(den) < 1e-9:
        return None
    t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den
    u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
    return (a[0] + t * r[0], a[1] + t * r[1]) if 0 <= t <= 1 and 0 <= u <= 1 else None


def junctions(roads):
    """[(x, y, radius_ft)]: where two roads meet or cross (an end within the other's half width + 3 ft, or crossing segments). radius = the wider half width."""
    out = []
    for i, ra in enumerate(roads):
        pa, wa = ra["points"], ra.get("width_ft", 12.0)
        for rb in roads[i + 1:]:
            pb, wb = rb["points"], rb.get("width_ft", 12.0)
            rad = max(wa, wb) / 2.0
            found = []
            for ends, other, wo in ((pa[:1] + pa[-1:], pb, wb), (pb[:1] + pb[-1:], pa, wa)):
                for e in ends:
                    if poly_dist(e, other) <= wo / 2.0 + 3.0:
                        found.append((e[0], e[1], rad))
            for a, b in zip(pa, pa[1:]):
                for c, d in zip(pb, pb[1:]):
                    x = _seg_cross(a, b, c, d)
                    if x:
                        found.append((x[0], x[1], rad))
            out.extend(found)
    return out


# ------------------------------------------------------------------ placement
def _rng(seed, rid, i, salt=""):
    return random.Random(hashlib.sha256(f"{seed}:{rid}:{i}:{salt}".encode()).digest())


def _stations(L, spacing, margin):
    usable = L - 2 * margin
    if usable < 0:
        return []
    n = int(usable // spacing) + 1
    s0 = margin + (usable - (n - 1) * spacing) / 2.0
    return [s0 + i * spacing for i in range(n)]


def _wall_point(p, buildings, reach):
    """Nearest point on any building wall within reach of p -> (x, y, nx, ny, building id) (n = outward normal toward p), else None."""
    best = None
    for b in buildings:
        poly = b["polygon"]
        n = len(poly)
        for k in range(n):
            a, c = poly[k], poly[(k + 1) % n]
            if math.hypot(c[0] - a[0], c[1] - a[1]) < 4.0:
                continue
            d, q = _seg_dist(p, a, c)
            if d <= reach and (best is None or d < best[0]):
                nx, ny = (p[0] - q[0]), (p[1] - q[1])
                ln = math.hypot(nx, ny)
                if ln < 1e-6:                              # on the wall line: use the edge normal pointing away from the building centre
                    cx = sum(v[0] for v in poly) / n
                    cy = sum(v[1] for v in poly) / n
                    nx, ny = q[0] - cx, q[1] - cy
                    ln = math.hypot(nx, ny) or 1.0
                best = (d, q[0], q[1], nx / ln, ny / ln, b["id"])
    return best[1:] if best else None


def plan_lamps(roads, buildings=None, cfg=None, ground=None, styles=None):
    """Pure placement. roads / buildings = world-pack entity dicts (roads: points [x, y, z], width_ft, class, surface, bridge, edit; buildings: polygon, doors [{point, kind}], id).
    ground(x, y) -> terrain z in ft (only with cfg ground = terrain). Returns {"lamps": [...], "skipped": {reason: n}, "roads": {id: {...}}, "config": cfg}.
    Each lamp: id, road, style, x, y, z (base, ft), rot_deg (direction of the arm / bracket in the world frame, atan2(dy, dx)), height_ft, mount, side, station_ft."""
    styles = styles or load_styles()
    cfg = normalize_config(cfg, styles)
    buildings = buildings or []
    sk = {"junction": 0, "bridge": 0, "door": 0, "building": 0, "no_wall": 0}
    res = {"lamps": [], "skipped": sk, "roads": {}, "config": cfg}
    if not cfg["enabled"]:
        res["note"] = "disabled"
        return res
    doors = [d["point"] for b in buildings for d in (b.get("doors") or []) if d.get("kind", "exterior") == "exterior" and d.get("point")]
    drive = [r for r in roads if len(r.get("points") or []) >= 2]
    jx = junctions(drive)
    bridges = [r for r in drive if r.get("bridge")] if cfg["skip_bridges"] else []
    for r in sorted(drive, key=lambda x: x["id"]):
        ov = road_override(r)
        cls = road_class(r)
        on = ov.get("on")
        info = {"class": cls, "length_ft": 0.0, "lamps": 0, "state": "on" if on else "off" if on is False else "class"}
        res["roads"][r["id"]] = info
        pts = r["points"]
        cum = _cum(pts)
        L = cum[-1]
        info["length_ft"] = round(L, 1)
        if on is False or (on is None and cls not in cfg["classes"]):
            info["state"] = "off" if on is False else "class not ticked"
            continue
        if r.get("bridge") and cfg["skip_bridges"]:
            info["state"] = "bridge"
            sk["bridge"] += 1
            continue
        style_id = ov.get("style") or cfg["style"]
        if style_id not in styles["styles"]:
            raise ValueError(f"road {r['id']}: lamp style {style_id!r} is not one of {', '.join(styles['styles'])}")
        st = styles["styles"][style_id]
        spacing = ov.get("spacing_ft") or cfg["spacing_ft"]
        height = cfg["height_ft"] or st["height_ft"]
        half = r.get("width_ft", 12.0) / 2.0
        sts = _stations(L, spacing, cfg["end_margin_ft"])
        centred = False
        if len(sts) < max(cfg["min_lamps"], 1) and not (on and sts):
            if cfg["centre_short"] and L >= 4.0:
                sts, centred = [L / 2.0], True                      # centre_short: a road too short for the margins / min_lamps gets one lamp in the middle
            else:
                info["state"] = f"too short for {max(cfg['min_lamps'], 1)} lamp(s)"
                continue
        cand = []
        for i, s in enumerate(sts):
            if cfg["jitter_ft"] > 0:
                s = max(cfg["end_margin_ft"], min(L - cfg["end_margin_ft"], s + _rng(cfg["seed"], r["id"], i).uniform(-1, 1) * min(cfg["jitter_ft"], spacing / 3.0)))
            sides = {"left": [1], "right": [-1], "both": [1, -1], "alternating": [1 if i % 2 == 0 else -1]}[cfg["side"]]
            for sd in sides:
                cand.append((i, s, sd))
        n_road = 0
        for i, s, sd in cand:
            x, y, z, tx, ty = _at(pts, cum, s)
            nx, ny = -ty * sd, tx * sd                               # left of travel = rotate the tangent +90 degrees in the world frame
            dist = half + cfg["offset_ft"]
            px, py = x + nx * dist, y + ny * dist
            lamp = {"id": f"lamp_{r['id']}_{len(res['lamps']) + 1:03d}", "road": r["id"], "style": style_id, "mount": st["mount"], "side": "left" if sd > 0 else "right",
                    "station_ft": round(s, 2), "height_ft": height, "z_road": z}
            if st["mount"] == "wall":
                w = _wall_point((px, py), buildings, cfg["wall_reach_ft"])
                if not w:
                    sk["no_wall"] += 1
                    continue
                px, py = w[0] + w[2] * 0.15, w[1] + w[3] * 0.15
                lamp["rot_deg"] = math.degrees(math.atan2(w[3], w[2]))
                lamp["building"] = w[4]
            else:
                lamp["rot_deg"] = math.degrees(math.atan2(-ny, -nx))      # arm points toward the road centre
                if cfg["jitter_ft"] > 0:
                    lamp["rot_deg"] += _rng(cfg["seed"], r["id"], i, "yaw").uniform(-1, 1) * 6.0
            if any(math.hypot(px - jx_, py - jy_) < jr + cfg["skip_junction_ft"] for jx_, jy_, jr in jx):
                sk["junction"] += 1
                continue
            if any(poly_dist((px, py), b["points"]) < b.get("width_ft", 12.0) / 2.0 + cfg["skip_junction_ft"] for b in bridges):
                sk["bridge"] += 1
                continue
            if cfg["skip_doors_ft"] > 0 and any(math.hypot(px - d[0], py - d[1]) < cfg["skip_doors_ft"] for d in doors):
                sk["door"] += 1
                continue
            if st["mount"] != "wall" and any(_in_poly((px, py), b["polygon"]) for b in buildings):
                sk["building"] += 1
                continue
            lamp["x"], lamp["y"] = round(px, 3), round(py, 3)
            lamp["z"] = round(ground(px, py) if (cfg["ground"] == "terrain" and ground) else z, 3)
            n_road += 1
            res["lamps"].append(lamp)
        info["lamps"] = n_road
        if info["state"] == "class":
            info["state"] = "on"
        if 0 < n_road < cfg["min_lamps"] and not on and not centred:
            res["lamps"] = [l for l in res["lamps"] if l["road"] != r["id"]]
            info["lamps"], info["state"] = 0, f"fewer than {cfg['min_lamps']} lamps fit after skips"
        elif n_road == 0 and info["state"] == "on":                 # never report a plain "on" for a road that got nothing
            info["state"] = "on (too short: 0 lamps)" if not sts else f"on (0 lamps: all {len(cand)} position(s) skipped)"
    cnt = {}                                                    # stable ids after skips: lamp_<road>_<nnn> counted per road

    for l in res["lamps"]:
        cnt[l["road"]] = cnt.get(l["road"], 0) + 1
        l["id"] = f"lamp_{l['road']}_{cnt[l['road']]:03d}"
    return res


def lamp_lights(lamps, cfg, styles=None):
    """Light hints (placements.json `lights` entries, type `lamp`) for planned lamps."""
    styles = styles or load_styles()
    lc = cfg["light"]
    out = []
    if not lc["enabled"]:
        return out
    for l in lamps:
        st = styles["styles"][l["style"]]
        sl = st["light"]
        k = lc["kelvin"] or sl["kelvin"]
        col = lc["color"] or ((sl.get("color") or "") if not lc["kelvin"] else "") or kelvin_to_hex(k)
        a = math.radians(l["rot_deg"])
        scale = (l["height_ft"] / st["height_ft"]) if st["mount"] == "post" and st["height_ft"] else 1.0
        dz = (l["height_ft"] - sl["dz_from_top_ft"] if "dz_from_top_ft" in sl else sl["dz_ft"] * scale) if st["mount"] == "post" else l["height_ft"] - (st["height_ft"] - sl["dz_ft"])
        dx = sl["dx_ft"]
        out.append({"id": l["id"], "type": "lamp", "road": l["road"], "style": l["style"], "building": l.get("building"),
                    "point": [round(l["x"] + math.cos(a) * dx, 3), round(l["y"] + math.sin(a) * dx, 3)], "z_abs_ft": round(l["z"] + dz, 3),
                    "dim_ft": lc["dim_ft"] or sl["dim_ft"], "bright_ft": lc["bright_ft"] or sl["bright_ft"], "color": col, "kelvin": k,
                    "intensity": lc["intensity"] or sl["intensity"], "animation": "torch" if (lc["flicker"] and sl["flicker"]) else None, "shadows": bool(lc["shadows"])})
    return out


# ------------------------------------------------------------------ meshes (built in feet around the base, +x = arm direction, scaled to metres at the end)
GLOW_MATS = ("mat_lamp_glow", "mat_lamp_gas_glow", "mat_lamp_flame")


class LB:
    """Small solid builder: prisms, boxes, pyramids and beams, faces unshared so the lamp is flat shaded."""

    def __init__(self):
        import worldpack_mesh as wm
        self.b = wm.Builder()
        self.wm = wm

    def _poly(self, mat, pts):
        self.b.face(mat, pts, [(0, 0)] * len(pts))

    def prism(self, cx, cy, z0, z1, r0, r1, n, mat, rot=0.0, cap_top=True, cap_bot=True, ax=1.0, ay=1.0):
        ring = lambda r, z: [(cx + ax * r * math.cos(rot + 2 * math.pi * k / n), cy + ay * r * math.sin(rot + 2 * math.pi * k / n), z) for k in range(n)]
        a, b = ring(r0, z0), ring(r1, z1)
        for k in range(n):
            self._poly(mat, [a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]])
        if cap_top and r1 > 0:
            self._poly(mat, b[::-1])
        if cap_bot and r0 > 0:
            self._poly(mat, a)

    def box(self, cx, cy, z0, sx, sy, sz, mat, rot_deg=0.0):
        r = math.hypot(sx, sy) / 2.0
        a0 = math.atan2(sy, sx)
        c, s = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
        pts = []
        for ang in (a0, math.pi - a0, math.pi + a0, -a0):
            lx, ly = r * math.cos(ang), r * math.sin(ang)
            pts.append((cx + lx * c - ly * s, cy + lx * s + ly * c))
        for k in range(4):
            (x1, y1), (x2, y2) = pts[k], pts[(k + 1) % 4]
            self._poly(mat, [(x1, y1, z0), (x2, y2, z0), (x2, y2, z0 + sz), (x1, y1, z0 + sz)])
        self._poly(mat, [(x, y, z0 + sz) for x, y in pts])
        self._poly(mat, [(x, y, z0) for x, y in pts][::-1])

    def pyramid(self, cx, cy, z0, z1, r, n, mat, rot=0.0, top_r=0.0):
        self.prism(cx, cy, z0, z1, r, top_r, n, mat, rot, cap_top=top_r > 0, cap_bot=True)

    def beam(self, p0, p1, w, mat):
        p0, p1 = np.array(p0, float), np.array(p1, float)
        u = p1 - p0
        L = np.linalg.norm(u)
        if L < 1e-9:
            return
        u /= L
        ref = np.array([0.0, 0.0, 1.0]) if abs(u[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        a = np.cross(u, ref)
        a /= np.linalg.norm(a)
        b = np.cross(u, a)
        co = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
        r0 = [tuple(p0 + a * x * w / 2 + b * y * w / 2) for x, y in co]
        r1 = [tuple(p1 + a * x * w / 2 + b * y * w / 2) for x, y in co]
        for k in range(4):
            self._poly(mat, [r0[k], r0[(k + 1) % 4], r1[(k + 1) % 4], r1[k]])
        self._poly(mat, r1[::-1])
        self._poly(mat, r0)

    def arc(self, c, r, a0, a1, w, mat, n=8, plane="xz", y=0.0):
        """Polyline of beams along a circular arc in the xz plane (centre c = (x, z))."""
        pts = [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)), y, c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]
        for p, q in zip(pts, pts[1:]):
            self.beam(p, q, w, mat)

    def lantern(self, x, z0, size, mat_frame="mat_lamp_iron", roof="mat_lamp_iron", tall=1.0):
        """Square glazed lantern: base plate, four corner posts, glowing body, pyramid roof, finial ring. Origin at the centre of the base, height about 1.6 * size * tall."""
        h = 1.15 * size * tall
        s = size
        self.box(x, 0, z0, s * 1.15, s * 1.15, s * 0.12, mat_frame)
        self.box(x, 0, z0 + s * 0.12, s * 0.8, s * 0.8, h * 0.9, "mat_lamp_glow")
        for sx in (-1, 1):
            for sy in (-1, 1):
                self.box(x + sx * s * 0.45, sy * s * 0.45, z0 + s * 0.12, s * 0.1, s * 0.1, h * 0.95, mat_frame)
        self.box(x, 0, z0 + s * 0.12 + h * 0.95, s * 1.1, s * 1.1, s * 0.08, mat_frame)
        self.pyramid(x, 0, z0 + s * 0.2 + h * 0.95, z0 + s * 0.2 + h * 0.95 + s * 0.55, s * 0.78, 4, roof, math.pi / 4)
        self.prism(x, 0, z0 + s * 0.75 + h * 0.95, z0 + s * 0.88 + h * 0.95, s * 0.09, s * 0.09, 6, mat_frame)
        return z0 + s * 0.88 + h * 0.95

    def lprism(self, c0, c1, z0, z1, r0, r1, n, mat, rot=0.0, cap_top=True, cap_bot=True):
        """Prism whose axis leans from c0 = (x, y) at z0 to c1 at z1."""
        ring = lambda c, r, z: [(c[0] + r * math.cos(rot + 2 * math.pi * k / n), c[1] + r * math.sin(rot + 2 * math.pi * k / n), z) for k in range(n)]
        a, b = ring(c0, r0, z0), ring(c1, r1, z1)
        for k in range(n):
            self._poly(mat, [a[k], a[(k + 1) % n], b[(k + 1) % n], b[k]])
        if cap_top and r1 > 0:
            self._poly(mat, b[::-1])
        if cap_bot and r0 > 0:
            self._poly(mat, a)

    def fluted(self, z0, z1, r0, r1, n, mat, depth=0.16):
        """Round post with n flutes: a 2n-gon alternating between the full radius and (1 - depth) of it. Open at the bottom, capped on top."""
        def ring(r, z):
            return [((r if k % 2 == 0 else r * (1 - depth)) * math.cos(math.pi * k / n), (r if k % 2 == 0 else r * (1 - depth)) * math.sin(math.pi * k / n), z) for k in range(2 * n)]
        a, b = ring(r0, z0), ring(r1, z1)
        m = 2 * n
        for k in range(m):
            self._poly(mat, [a[k], a[(k + 1) % m], b[(k + 1) % m], b[k]])
        self._poly(mat, b[::-1])

    def sink(self, r, top, mat):
        """Buried foot in the post's own material (no separate grey base): the post goes half a foot into the ground."""
        self.prism(0, 0, -0.5, top, r, r, 8, mat, math.pi / 8, cap_top=False)

    def mesh(self):
        return self.b.build()


def _s_wrought_iron(h):
    b = LB()
    b.sink(0.5, 0.15, "mat_lamp_iron")
    b.prism(0, 0, 0.15, 0.95, 0.5, 0.3, 8, "mat_lamp_iron", math.pi / 8)
    b.prism(0, 0, 0.95, 1.2, 0.3, 0.3, 8, "mat_lamp_iron", math.pi / 8)
    top = h - 1.7
    b.prism(0, 0, 1.2, top, 0.17, 0.11, 8, "mat_lamp_iron", math.pi / 8, cap_bot=False)
    b.prism(0, 0, 4.2, 4.6, 0.22, 0.22, 8, "mat_lamp_iron", math.pi / 8)
    b.beam((-0.7, 0, top - 0.8), (0.7, 0, top - 0.8), 0.07, "mat_lamp_iron")
    b.arc((0.7, top - 1.35), 0.55, 90, 270, 0.06, "mat_lamp_iron", 6)
    b.arc((-0.7, top - 1.35), 0.55, -90, 90, 0.06, "mat_lamp_iron", 6)
    b.box(0, 0, top, 1.0, 1.0, 0.12, "mat_lamp_iron")
    b.lantern(0, top + 0.12, 0.95)
    return b.mesh()


def _s_wooden_oil(h):
    b = LB()
    b.box(0, 0, -0.5, 0.36, 0.36, h + 0.5, "mat_lamp_wood")
    arm_z = h - 0.45
    b.beam((0, 0, arm_z), (2.0, 0, arm_z), 0.22, "mat_lamp_wood")
    b.beam((0, 0, h - 2.4), (1.6, 0, arm_z - 0.05), 0.18, "mat_lamp_wood")
    b.beam((1.9, 0, arm_z - 0.1), (1.9, 0, arm_z - 1.0), 0.04, "mat_lamp_iron")
    b.lantern(1.9, arm_z - 1.85, 0.6, "mat_lamp_iron")
    return b.mesh()


def _s_stone_pillar(h):
    b = LB()
    b.box(0, 0, -0.5, 1.45, 1.45, h - 0.6, "mat_lamp_stone")
    b.box(0, 0, h - 1.1, 1.95, 1.95, 0.28, "mat_lamp_stone")
    b.box(0, 0, h - 0.82, 1.1, 1.1, 0.08, "mat_lamp_iron")
    b.box(0, 0, h - 0.74, 0.8, 0.8, 0.9, "mat_lamp_glow")
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box(sx * 0.5, sy * 0.5, h - 0.74, 0.12, 0.12, 0.95, "mat_lamp_iron")
    b.pyramid(0, 0, h + 0.2, h + 0.75, 0.95, 4, "mat_lamp_stone", math.pi / 4)
    return b.mesh()


def _s_bracket_wall(h):
    b = LB()
    b.box(-0.05, 0, h - 1.4, 0.1, 0.5, 1.8, "mat_lamp_iron")
    b.beam((0, 0, h - 0.2), (1.6, 0, h - 0.2), 0.09, "mat_lamp_iron")
    b.beam((0, 0, h - 1.3), (1.5, 0, h - 0.25), 0.08, "mat_lamp_iron")
    b.arc((1.5, h - 0.55), 0.35, 270, 360, 0.06, "mat_lamp_iron", 5)
    b.beam((1.6, 0, h - 0.2), (1.6, 0, h - 0.6), 0.04, "mat_lamp_iron")
    b.lantern(1.6, h - 1.45, 0.62)
    return b.mesh()


def _s_torch_post(h):
    b = LB()
    b.prism(0, 0, -0.5, h, 0.24, 0.18, 8, "mat_lamp_wood", cap_bot=False)
    b.prism(0, 0, h - 1.4, h - 1.25, 0.3, 0.3, 8, "mat_lamp_iron")
    b.prism(0, 0, h - 0.55, h, 0.28, 0.55, 8, "mat_lamp_iron", cap_top=False)
    for k in range(6):
        a = 2 * math.pi * k / 6
        b.beam((0.52 * math.cos(a), 0.52 * math.sin(a), h - 0.05), (0.62 * math.cos(a), 0.62 * math.sin(a), h + 0.35), 0.06, "mat_lamp_iron")
    b.prism(0, 0, h, h + 0.5, 0.2, 0.17, 6, "mat_lamp_wood")
    b.pyramid(0, 0, h + 0.5, h + 1.55, 0.4, 6, "mat_lamp_glow", 0.0, 0.05)
    return b.mesh()


def _s_shepherd_crook(h):
    b = LB()
    b.prism(0, 0, -0.5, 0.5, 0.35, 0.18, 8, "mat_lamp_iron", cap_bot=False)
    b.prism(0, 0, 0.5, h - 0.9, 0.09, 0.07, 8, "mat_lamp_iron", cap_bot=False)
    b.arc((0.9, h - 0.9), 0.9, 180, 20, 0.07, "mat_lamp_iron", 10)
    xe = 0.9 + 0.9 * math.cos(math.radians(20))
    ze = h - 0.9 + 0.9 * math.sin(math.radians(20))
    b.beam((xe, 0, ze), (xe, 0, ze - 0.35), 0.04, "mat_lamp_iron")
    b.lantern(xe, ze - 1.1, 0.5)
    return b.mesh()


# old wooden lantern post: weathered timber, braced cross-arm, iron straps, a hook with a hanging cage lantern (flame core visible)
OWL_FROM_TOP = 2.55      # flame centre this far below the post top (light.dz_from_top_ft)
OWL_ARM_X = 2.2          # flame x offset from the post axis, in the local frame (light.dx_ft)


def _s_old_wooden_lantern(h):
    b = LB()
    W, WD, IR, MO = "mat_lamp_wood_old", "mat_lamp_wood", "mat_lamp_iron", "mat_lamp_moss"
    lean = (-0.14, 0.12)                                                  # the top of the post is out of true
    ax = lambda z: (lean[0] * z / h, lean[1] * z / h)                    # axis position at height z
    rad = lambda z: 0.3 - 0.1 * (z - 0.2) / (h - 0.2)                    # post radius at height z
    b.lprism(ax(-0.5), ax(h), -0.5, h, 0.3, 0.2, 8, W, math.pi / 8, cap_bot=False)   # post goes straight into the ground
    b.lprism(ax(0.0), ax(1.9), 0.0, 1.9, rad(0.0) + 0.02, rad(1.9) + 0.02, 8, MO, math.pi / 8, cap_top=False, cap_bot=False)   # moss creeping up the foot
    for z in (1.5, 4.3, h - 1.8):                                         # iron straps
        cx, cy = ax(z)
        r = rad(z) + 0.035
        b.prism(cx, cy, z - 0.13, z + 0.13, r, r, 8, IR, math.pi / 8, cap_top=False, cap_bot=False)
    tx, ty = ax(h)
    b.prism(tx, ty, h - 0.05, h + 0.14, 0.26, 0.19, 8, WD, math.pi / 8)  # weathered cap
    arm_z = h - 0.65
    b.beam((tx - 0.9, ty, arm_z + 0.05), (tx + 2.45, ty, arm_z), 0.26, W)     # cross-arm, tail behind the post
    b.beam((tx + 0.1, ty, h - 3.0), (tx + 1.7, ty, arm_z - 0.05), 0.2, W)     # diagonal brace
    b.beam((tx - 0.1, ty, h - 2.5), (tx - 0.85, ty, arm_z - 0.1), 0.14, W)    # short back brace
    b.box(tx + 0.12, ty, h - 3.0, 0.1, 0.34, 0.2, IR)                         # iron plates at the brace joints
    b.box(tx + 1.7, ty, arm_z - 0.45, 0.1, 0.34, 0.2, IR)
    hx = tx + OWL_ARM_X
    top = arm_z - 0.2
    b.beam((hx, ty, arm_z - 0.05), (hx, ty, top - 0.1), 0.07, IR)             # hook peg through the arm
    z0 = h - OWL_FROM_TOP - 0.45                                              # lantern base plate; flame centre = z0 + 0.45
    for k in range(3):                                                        # chain links
        b.box(hx, ty, top - 0.1 - 0.27 * (k + 1) + 0.1, 0.09, 0.05, 0.27, IR)
    ring_z = z0 + 1.2
    b.prism(hx, ty, ring_z, ring_z + 0.07, 0.11, 0.11, 6, IR)                 # hanger ring
    b.box(hx, ty, z0 + 1.0, 0.8, 0.8, 0.08, IR)                               # top plate
    b.pyramid(hx, ty, z0 + 1.08, z0 + 1.2, 0.42, 4, IR, math.pi / 4)          # little roof
    b.box(hx, ty, z0, 0.74, 0.74, 0.1, IR)                                    # base plate
    b.pyramid(hx, ty, z0 - 0.28, z0, 0.2, 6, IR)                              # drip cone under it
    for sx in (-1, 1):
        for sy in (-1, 1):
            b.box(hx + sx * 0.3, ty + sy * 0.3, z0 + 0.1, 0.07, 0.07, 0.9, IR)
    for sg in (-1, 1):                                                        # glass panes, open slot top and bottom so the flame shows
        b.box(hx + sg * 0.29, ty, z0 + 0.2, 0.03, 0.46, 0.66, "mat_lamp_glow")
        b.box(hx, ty + sg * 0.29, z0 + 0.2, 0.46, 0.03, 0.66, "mat_lamp_glow")
    b.prism(hx, ty, z0 + 0.1, z0 + 0.3, 0.1, 0.08, 6, IR)                     # oil pot
    b.prism(hx, ty, z0 + 0.3, z0 + 0.6, 0.075, 0.03, 6, "mat_lamp_flame")      # the flame, centre at z0 + 0.45
    return b.mesh()


def _gas_geometry(h):
    top = h - 1.9                       # shaft top / lantern seat
    gz = top + 0.35                     # bottom of the glass
    return top, gz, 1.55                # glass height 1.55


def _s_antique_gas_lantern(h):
    b = LB()
    IR, GL = "mat_lamp_iron_cast", "mat_lamp_gas_glow"
    top, gz, gh = _gas_geometry(h)
    b.prism(0, 0, -0.5, 0.0, 0.66, 0.66, 8, IR, math.pi / 8, cap_top=False)           # cast-iron foot, buried half a foot
    b.prism(0, 0, 0.0, 1.0, 0.66, 0.5, 8, IR, math.pi / 8, cap_top=False, cap_bot=False)   # flared foot
    b.prism(0, 0, 1.0, 1.2, 0.54, 0.54, 8, IR, math.pi / 8)
    b.prism(0, 0, 1.2, 2.5, 0.46, 0.32, 8, IR, math.pi / 8, cap_bot=False)           # tapering pedestal
    b.prism(0, 0, 2.5, 2.7, 0.4, 0.4, 8, IR, math.pi / 8)
    b.prism(0, 0, 2.7, 3.0, 0.3, 0.3, 8, IR, math.pi / 8)                             # base collar ring
    b.fluted(3.0, top - 0.5, 0.25, 0.19, 8, IR)                                        # fluted column
    b.prism(0, 0, top - 0.5, top - 0.3, 0.27, 0.27, 8, IR, math.pi / 8)                # collar rings under the lantern
    b.prism(0, 0, top - 0.3, top - 0.18, 0.2, 0.2, 8, IR, math.pi / 8)
    lz = top - 1.5
    b.beam((0, -0.75, lz), (0, 0.75, lz), 0.06, IR)                                    # ladder bar
    for sg in (-1, 1):
        b.prism(0, sg * 0.78, lz - 0.07, lz + 0.07, 0.09, 0.09, 6, IR)
    for sg in (-1, 1):                                                                 # scrolled brackets either side of the shaft
        b.arc((sg * 0.55, top - 0.75), 0.55, 90 if sg < 0 else 90, 180 if sg < 0 else 0, 0.06, IR, 6)
    b.prism(0, 0, top - 0.18, top, 0.34, 0.5, 8, IR, math.pi / 8)                      # seat flare
    b.box(0, 0, top, 1.0, 1.0, 0.1, IR, 45.0)                                          # lantern base plate
    b.pyramid(0, 0, top + 0.1, gz, 0.4, 4, IR, math.pi / 4, top_r=0.34)                # burner housing
    b.prism(0, 0, gz, gz + gh, 0.36, 0.6, 4, GL, math.pi / 4, cap_top=False, cap_bot=False)  # tapered glass, wider at the top
    for k in range(4):                                                                 # frame posts along the corners
        a = math.pi / 4 + k * math.pi / 2
        b.beam((0.36 * math.cos(a) * 1.0, 0.36 * math.sin(a), gz), (0.6 * math.cos(a), 0.6 * math.sin(a), gz + gh), 0.07, IR)
    b.prism(0, 0, gz + 0.45, gz + 0.9, 0.09, 0.16, 6, "mat_lamp_flame")                # gas mantle, centre at gz + 0.675
    b.box(0, 0, gz + gh, 1.55, 1.55, 0.09, IR, 45.0)                                   # top rim
    b.pyramid(0, 0, gz + gh + 0.09, gz + gh + 0.7, 0.95, 4, IR, math.pi / 4, top_r=0.2)  # cap
    b.prism(0, 0, gz + gh + 0.7, gz + gh + 0.84, 0.24, 0.24, 6, IR)                    # vent collar
    b.pyramid(0, 0, gz + gh + 0.84, gz + gh + 1.1, 0.14, 6, IR)                        # finial
    return b.mesh()


BUILDERS = {"wrought_iron": _s_wrought_iron, "wooden_oil": _s_wooden_oil, "stone_pillar": _s_stone_pillar, "bracket_wall": _s_bracket_wall,
            "torch_post": _s_torch_post, "shepherd_crook": _s_shepherd_crook,
            "old_wooden_lantern": _s_old_wooden_lantern, "antique_gas_lantern": _s_antique_gas_lantern}
_CACHE = {}


def style_mesh(style, height_ft):
    """Unit mesh of a style at its height in FEET (local frame, origin at the base, arm along +x), cached."""
    key = (style, round(height_ft, 3))
    if key not in _CACHE:
        _CACHE[key] = BUILDERS[style](height_ft)
    return _CACHE[key]


def lamp_mesh(lamp, to_blender):
    """The lamp as a Mesh in the pack's Blender frame (metres). to_blender(x_ft, y_ft, z_ft) -> (bx, by, bz). The local +x axis is rotated to the lamp's world direction."""
    import worldpack_mesh as wm
    m = style_mesh(lamp["style"], lamp["height_ft"])
    bx, by, bz = to_blender(lamp["x"], lamp["y"], lamp["z"])
    # world y is south, Blender y north: a world direction angle a becomes -a
    return m.transformed(FT, -lamp["rot_deg"], (bx, by, bz))


# ------------------------------------------------------------------ pack I/O
def _pack_roads_buildings(pack):
    roads = [r for r in pack.list("roads")]
    return roads, [b for b in pack.list("buildings")]


class _PackView:
    """The real pack with the lamp materials added (write_glb looks them up by id)."""

    def __init__(self, pack, styles):
        self._p = pack
        self.materials = dict(pack.materials)
        self.materials.update(styles["materials"])

    def __getattr__(self, k):
        return getattr(self._p, k)


def _patch_emissive(path, materials):
    """write_glb knows no emissive: add emissiveFactor to the glTF materials listed with an `emissive` colour (JSON chunk rewritten, binary untouched)."""
    with open(path, "rb") as f:
        data = f.read()
    jl = struct.unpack_from("<I", data, 12)[0]
    js = json.loads(data[20:20 + jl])
    for m in js.get("materials", []):
        e = (materials.get(m.get("name")) or {}).get("emissive")
        if e:
            m["emissiveFactor"] = [int(e[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    nj = json.dumps(js, separators=(",", ":"), sort_keys=True).encode()
    nj += b" " * (-len(nj) % 4)
    rest = data[20 + jl:]
    out = data[:8] + struct.pack("<I", 12 + 8 + len(nj) + len(rest)) + struct.pack("<I4s", len(nj), b"JSON") + nj + rest
    with open(path, "wb") as f:
        f.write(out)


def _strip(doc, base_dir):
    """Remove every streetlamp trace (file entry, lights, GLB) from a placements doc. Returns what was removed."""
    n_files = len(doc.get("files", []))
    doc["files"] = [e for e in doc.get("files", []) if e.get("layer") != LAYER]
    removed_l = len([l for l in doc.get("lights", []) if l.get("type") == "lamp"])
    if "lights" in doc:
        doc["lights"] = [l for l in doc["lights"] if l.get("type") != "lamp"]
    doc.pop("streetlamps", None)
    p = os.path.join(base_dir, *FILE_REL.split("/"))
    if os.path.exists(p):
        os.remove(p)
    return {"files": n_files - len(doc["files"]), "lights": removed_l}


def build_entry(pack, lamps, base_dir, styles):
    """Write models/streetlamps/streetlamps.glb under base_dir and return the placements entry (one merged tile; layer streetlamps)."""
    import worldpack_mesh as wm
    import worldpack_split as ws
    fr = pack.frame
    meshes = [lamp_mesh(l, fr.to_blender) for l in lamps]
    merged = wm.merge_meshes(meshes)
    pv = _PackView(pack, styles)
    part = {"id": LAYER, "layer": LAYER, "group": LAYER, "instance": None, "mesh": merged, "pivot": wm._pivot(merged), "tags": {"layer": LAYER, "group": LAYER, "id": LAYER},
            "extras": {"lamps": len(lamps)}}
    e = ws._entry(pv, FILE_REL[len("models/"):], [part], set(), base_dir, "external")
    _patch_emissive(os.path.join(base_dir, *FILE_REL.split("/")), pv.materials)
    import hashlib as _h
    with open(os.path.join(base_dir, *FILE_REL.split("/")), "rb") as f:
        raw = f.read()
    e["sha256"], e["bytes"] = _h.sha256(raw).hexdigest(), len(raw)
    e["members"] = [{"id": l["id"], "layer": LAYER, "tags": {"road": l["road"], "style": l["style"]}, "offset_m": [0, 0, 0]} for l in lamps][:400]
    e["ids"] = [l["id"] for l in lamps][:400]
    return e


def chunk_lamps(lamps, chunk_ft):
    if not chunk_ft:
        return [("all", lamps)]
    g = {}
    for l in lamps:
        g.setdefault((int(l["x"] // chunk_ft), int(l["y"] // chunk_ft)), []).append(l)
    return [(f"{k[0]}_{k[1]}", v) for k, v in sorted(g.items())]


def apply_to_placements(pack, doc_path, plan, styles, log=print):
    """Write (or remove, when the plan has no lamps) the streetlamps tile + lights in one placements.json. Idempotent."""
    base = os.path.dirname(os.path.abspath(doc_path))
    with open(doc_path, encoding="utf-8") as f:
        doc = json.load(f)
    removed = _strip(doc, base)
    lamps = plan["lamps"]
    cfg = plan["config"]
    res = {"placements": doc_path, "removed": removed, "lamps": len(lamps), "lights": 0}
    if cfg["enabled"] and lamps:
        entry = build_entry(pack, lamps, base, styles)
        doc["files"] = sorted(doc["files"] + [entry], key=lambda e: e["file"])
        lights = lamp_lights(lamps, cfg, styles)
        doc.setdefault("lights", [])
        doc["lights"] = doc["lights"] + lights
        res["lights"] = len(lights)
        res.update(file=entry["file"], bytes=entry["bytes"], tris=entry["tris"], size_ft=entry["size_ft"])
    doc["streetlamps"] = {"enabled": bool(cfg["enabled"]), "lamps": len(lamps), "lights": res["lights"], "config": cfg}
    if not (cfg["enabled"] and lamps):
        doc["streetlamps"]["lamps"] = 0
    tmp = doc_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, doc_path)
    return res


def pack_light_counts(doc):
    out = {}
    for l in list(doc.get("lights", [])) + [x for e in doc.get("files", []) for x in e.get("lights", [])]:
        if l.get("type") != "lamp":
            out[l.get("type", "light")] = out.get(l.get("type", "light"), 0) + 1
    return out


def summarize(plan, lights, other_lights=None):
    by_class, by_style = {}, {}
    for l in plan["lamps"]:
        by_style[l["style"]] = by_style.get(l["style"], 0) + 1
        c = plan["roads"][l["road"]]["class"]
        by_class[c] = by_class.get(c, 0) + 1
    return {"lamps": len(plan["lamps"]), "lights": len(lights), "by_class": by_class, "by_style": by_style, "skipped": plan["skipped"], "roads": plan["roads"],
            "other_lights": other_lights or {}, "total_lights": len(lights) + sum((other_lights or {}).values())}


# ------------------------------------------------------------------ preview thumbnails
def render_thumb(style, path, height_ft=None, size=220, styles=None):
    """Flat-shaded orthographic render of one style (PIL + numpy, 2x supersampled, soft warm glow around the flame) for the panel's style picker."""
    from PIL import Image, ImageDraw, ImageFilter
    styles = styles or load_styles()
    st = styles["styles"][style]
    h = height_ft or st["height_ft"]
    m = style_mesh(style, h)
    V = m.V
    ang = math.radians(32)
    c, s = math.cos(ang), math.sin(ang)
    X = V[:, 0] * c - V[:, 1] * s
    Y = V[:, 0] * s + V[:, 1] * c
    Z = V[:, 2]
    big = size * 2
    scale = (big * 0.84) / max(Z.max() + 0.6, (X.max() - X.min()) * 1.1, 1.0)
    ox = big / 2 - (X.max() + X.min()) / 2 * scale
    oy = big * 0.93
    img = Image.new("RGB", (big, big), (74, 86, 112))
    d = ImageDraw.Draw(img)
    d.rectangle([0, oy + 0.0, big, big], fill=(58, 66, 54))                      # ground
    cols = {k: tuple(int(v["mean_color"][i:i + 2], 16) for i in (1, 3, 5)) for k, v in styles["materials"].items()}
    cols["mat_lamp_iron"] = (46, 48, 54)
    tris, gx, gz, gn = [], 0.0, 0.0, 0
    for mid, F in m.subs.items():
        for f in F:
            P = V[f]
            n = np.cross(P[1] - P[0], P[2] - P[0])
            ln = np.linalg.norm(n)
            if ln < 1e-9:
                continue
            n = n / ln
            wn = np.array([n[0] * c - n[1] * s, n[0] * s + n[1] * c, n[2]])
            lit = 0.55 + 0.45 * abs(float(np.dot(wn, np.array([-0.4, -0.6, 0.7]) / 0.9)))
            tris.append((float(Y[f].mean()), f, mid, 1.0 if mid in GLOW_MATS else lit))
            if mid in GLOW_MATS:
                gx += float(X[f].mean())
                gz += float(Z[f].mean())
                gn += 1
    tris.sort(key=lambda t: -t[0])
    for _, f, mid, lit in tris:
        col = cols.get(mid, (160, 160, 160))
        d.polygon([(ox + X[i] * scale, oy - Z[i] * scale) for i in f], fill=tuple(min(255, int(v * lit)) for v in col))
    if gn:
        cx, cy = ox + gx / gn * scale, oy - gz / gn * scale
        halo = Image.new("RGB", (big, big), (0, 0, 0))
        r = big * 0.16
        ImageDraw.Draw(halo).ellipse([cx - r, cy - r, cx + r, cy + r], fill=(150, 88, 24))
        halo = halo.filter(ImageFilter.GaussianBlur(big * 0.07))
        img = Image.fromarray(np.clip(np.asarray(img, dtype=np.int16) + np.asarray(halo, dtype=np.int16), 0, 255).astype("u1"))
    img = img.resize((size, size), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    img.save(path)
    return path


# ------------------------------------------------------------------ command line
def _load_pack(a):
    import worldpack as wp
    pd = a.pack or os.path.join(HERE, "..", "..", "world", a.place, "export")
    return wp.load_pack(pd), pd


def _cfg_from_args(a, base=None):
    cfg = dict(base or {})
    if getattr(a, "config", None):
        with open(a.config, encoding="utf-8") as f:
            cfg.update(json.load(f))
    lt = dict(cfg.get("light") or {})
    m = {"enabled": a.enabled, "style": a.style, "spacing_ft": a.spacing, "side": a.side, "offset_ft": a.offset, "height_ft": a.height, "classes": a.classes,
         "skip_junction_ft": a.skip_junction, "skip_doors_ft": a.skip_doors, "jitter_ft": a.jitter, "seed": a.seed, "min_lamps": a.min_lamps, "centre_short": a.centre_short}
    for k, v in m.items():
        if v is not None:
            cfg[k] = (v == "on") if k in ("enabled", "centre_short") else v
    for k, v in (("kelvin", a.kelvin), ("dim_ft", a.dim), ("bright_ft", a.bright), ("intensity", a.intensity)):
        if v is not None:
            lt[k] = v
    for k, v in (("flicker", a.flicker), ("shadows", a.shadows)):
        if v is not None:
            lt[k] = v == "on"
    cfg["light"] = lt
    return cfg


def _stored_enabled(paths):
    """The scene switch stored by the last apply in the first existing placements file; True when never applied."""
    for p in paths:
        try:
            with open(p, encoding="utf-8") as f:
                return bool(((json.load(f).get("streetlamps") or {}).get("config") or {}).get("enabled", True))
        except (OSError, ValueError):
            continue
    return True


def cmd_plan(a, write=False):
    styles = load_styles()
    pack, pd = _load_pack(a)
    cfg = _cfg_from_args(a)
    if not write:
        cfg["enabled"] = True                                         # a dry run plans "what would it do if on" (the readout)
    elif "enabled" not in cfg:
        cfg["enabled"] = _stored_enabled(a.placements or [os.path.join(pd, "placements.json")])   # apply without --enabled / config: keep the stored switch (first run: on, like plan)
    roads, blds = _pack_roads_buildings(pack)
    plan = plan_lamps(roads, blds, normalize_config(cfg, styles), ground=pack.elevation_at, styles=styles)
    lights = lamp_lights(plan["lamps"], plan["config"], styles)
    pp = os.path.join(pd, "placements.json")
    other = {}
    if os.path.exists(pp):
        with open(pp, encoding="utf-8") as f:
            other = pack_light_counts(json.load(f))
    out = {"ok": True, "place": pack.place, **summarize(plan, lights, other), "config": plan["config"]}
    if not write:
        out["note"] = "dry run: nothing written"
        return out
    targets = a.placements or [pp]
    out["written"] = [apply_to_placements(pack, t, plan, styles) for t in targets]
    if os.path.abspath(os.path.dirname(os.path.abspath(targets[0]))) == os.path.abspath(pd):
        import worldpack as wp
        ch, ad, dr = wp.refresh_manifest_files(pd)
        out["manifest_files"] = {"rehashed": ch, "added": ad, "dropped": dr}
    return out


def build_parser():
    ap = argparse.ArgumentParser(prog="streetlamps.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("styles", "plan", "apply", "preview"):
        s = sub.add_parser(n)
        if n in ("plan", "apply"):
            s.add_argument("--place", default="bridgehollow", help="place id (world/<place>/export is the pack unless --pack)")
            s.add_argument("--pack", help="pack folder (default world/<place>/export)")
            s.add_argument("--config", help="JSON file with the settings (the panel writes one); the options below override it")
            s.add_argument("--enabled", choices=["on", "off"], help="scene toggle: off removes the lamp layer and lamp lights from the placements. Omitted: apply keeps the setting stored by the last apply (on the first run: on), plan is always a dry run as if on")
            s.add_argument("--style", help="wrought_iron | wooden_oil | stone_pillar | bracket_wall | torch_post | shepherd_crook | old_wooden_lantern | antique_gas_lantern")
            s.add_argument("--spacing", type=float, help="distance between lamps along the road, ft")
            s.add_argument("--side", choices=list(SIDES), help="left | right | alternating | both")
            s.add_argument("--offset", type=float, help="distance from the road edge, ft")
            s.add_argument("--height", type=float, help="post height ft (0 = style default; wall bracket: mounting height)")
            s.add_argument("--classes", help="road classes that get lamps: main,side,dirt")
            s.add_argument("--skip-junction", dest="skip_junction", type=float, help="no lamp within this distance of a junction, ft")
            s.add_argument("--skip-doors", dest="skip_doors", type=float, help="no lamp within this distance of an exterior door, ft (0 = off)")
            s.add_argument("--jitter", type=float, help="random shift along the road, ft (0 = regular)")
            s.add_argument("--seed", type=int, help="jitter seed")
            s.add_argument("--min-lamps", dest="min_lamps", type=int, help="a road that fits fewer lamps than this gets none")
            s.add_argument("--centre-short", dest="centre_short", choices=["on", "off"], help="a road too short for min-lamps / the end margins gets one centred lamp (default off)")
            s.add_argument("--kelvin", type=float, help="light colour temperature K (0 = style default)")
            s.add_argument("--dim", type=float, help="light dim radius ft (0 = style default)")
            s.add_argument("--bright", type=float, help="light bright radius ft (0 = style default)")
            s.add_argument("--intensity", type=float, help="light strength 0..1 (0 = style default)")
            s.add_argument("--flicker", choices=["on", "off"], help="flame flicker animation")
            s.add_argument("--shadows", choices=["on", "off"], help="light shadows (default off, costly)")
        if n == "apply":
            s.add_argument("--placements", action="append", help="placements.json to write (repeatable: the full export and the merged optimized set); default export/placements.json")
        if n == "preview":
            s.add_argument("--out", help="folder for the PNGs (default presets/streetlamps/thumbs)")
            s.add_argument("--style", action="append", help="only these styles")
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        if a.cmd == "styles":
            out = {"ok": True, **{k: v for k, v in load_styles().items() if k != "materials"}, "sides": list(SIDES), "classes": list(CLASSES), "defaults": DEFAULTS}
        elif a.cmd == "preview":
            styles = load_styles()
            d = a.out or os.path.join(HERE, "..", "presets", "streetlamps", "thumbs")
            sel = a.style or list(styles["styles"])
            out = {"ok": True, "thumbs": {s: render_thumb(s, os.path.join(d, s + ".png"), styles=styles) for s in sel}}
        else:
            out = cmd_plan(a, write=a.cmd == "apply")
    except (ValueError, OSError, KeyError) as e:
        out = {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    print(json.dumps(out), flush=True)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
