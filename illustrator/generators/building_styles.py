"""Building style presets for the 3D world pack: wall system, roof, plinth, windows, door, chimney, trim, eaves, jetty, per building.

Presets live in `illustrator/presets/building_styles/*.json` (one file per style: name, description, category, culture, kinds weights and the
parameter blocks below). A building opts in with a `style` key in its world json (`world/<place>/buildings/<id>.json`):
  * absent / null  -> the legacy look (kind based wall + roof picked by worldpack_pbr.restyle_building), nothing changes;
  * "<preset id>"  -> that preset, parameters varied deterministically per building id (colours, proportions, pattern, pitch);
  * "auto"         -> a preset chosen from the building's kind and its district (`default_style`), consistent inside a district.

API: `load_presets()`, `list_presets()`, `resolve(style_id, building_id)` (concrete parameter dict), `default_style(kind, district, bid)`,
`apply_style(e)` (-> entity copy with wall/roof surfaces, `_style` carrying the resolved parameters), `register_materials(materials, style)`,
`material_record(mid)` / `info(mid)` / `gen_texture(mid)` for the dynamic materials `mat_s_<kind>_<hex>` and `mat_s_tint_<base>_<hex>`.
Geometry (timber frames, plinths, windows, chimneys, roofs, towers) is in building_styles_geo.py and is called from worldpack_detail.

World scale: a half-timber panel is 3-4 ft wide and 2-4.5 ft tall, studs about 3 ft apart (close studding 1.1 ft), beams 4-5 in wide and
2.4 in proud of the plaster, brick 8.5 in x 2.8 in with mortar, boards 6-8 in. Beams are real boxes on the wall (not a texture).
"""
import hashlib
import json
import math
import os
import re

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
STYLE_DIR = os.path.join(HERE, "..", "presets", "building_styles")
_CACHE = {}


# ------------------------------------------------------------------ presets and deterministic variation
def load_presets(force=False):
    if force or "p" not in _CACHE:
        out = {}
        if os.path.isdir(STYLE_DIR):
            for fn in sorted(os.listdir(STYLE_DIR)):
                if fn.endswith(".json"):
                    with open(os.path.join(STYLE_DIR, fn), encoding="utf-8") as f:
                        d = json.load(f)
                    d.setdefault("id", fn[:-5])
                    out[d["id"]] = d
        _CACHE["p"] = out
    return _CACHE["p"]


def list_presets():
    """[{id, name, description, category, culture, kinds, preview}] for the panel."""
    out = []
    for p in load_presets().values():
        out.append({k: p.get(k) for k in ("id", "name", "description", "category", "culture", "kinds", "preview")})
    return out


def _u(key, salt):
    """Deterministic 0..1 from (key, salt)."""
    return int(hashlib.md5(f"{key}|{salt}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _pick(seq, key, salt):
    if not seq:
        return None
    if not isinstance(seq, (list, tuple)):
        return seq
    return seq[min(int(_u(key, salt) * len(seq)), len(seq) - 1)]


def _rng(v, key, salt, default=None):
    """[lo, hi] -> deterministic value in range; scalar -> itself."""
    if v is None:
        return default
    if isinstance(v, (list, tuple)):
        return v[0] + (v[1] - v[0]) * _u(key, salt)
    return v


def default_style(kind, district, bid):
    """Preset id for style == "auto": weights by kind; a district prefers one preset (65 %) so a street looks coherent."""
    pres = load_presets()
    cand = [(p["id"], float((p.get("kinds") or {}).get(kind or "house", 0))) for p in pres.values()]
    cand = [c for c in cand if c[1] > 0] or [(p["id"], 1.0) for p in pres.values() if p.get("category") == "house"]
    if not cand:
        return None
    if _u(bid, "dist") < 0.65:
        key = district or "none"
    else:
        key = bid
    tot = sum(w for _, w in cand)
    r = _u(f"{key}|{kind}", "auto") * tot
    acc = 0.0
    for pid, w in cand:
        acc += w
        if r <= acc:
            return pid
    return cand[-1][0]


def resolve(style_id, bid, kind=None, district=None):
    """Concrete parameters of preset `style_id` for building `bid` (None when unknown). Pure function of (preset, id)."""
    pres = load_presets()
    if style_id == "auto":
        style_id = default_style(kind, district, bid)
    p = pres.get(style_id)
    if not p:
        return None
    k = bid
    w, pl, rf, wi, dr, ch = (p.get(x) or {} for x in ("wall", "plinth", "roof", "windows", "door", "chimney"))
    S = {"id": p["id"], "name": p.get("name"), "category": p.get("category"), "special": dict(p.get("special") or {})}
    # wall
    wsys = w.get("system", "plain")
    infill = _pick(w.get("colors") or ["#dcd2bb"], k, "infill")
    S["wall"] = {"system": wsys, "material": w.get("material", "plaster"), "color": infill,
                 "beam_color": _pick(w.get("beam_colors") or ["#2a2019"], k, "beam"),
                 "pattern": _pick(w.get("pattern") or ["braced"], k, "pattern"), "spacing_ft": _rng(w.get("spacing_ft") or [3.0, 3.6], k, "sp"),
                 "beam_w_ft": _rng(w.get("beam_w_ft") or [0.34, 0.42], k, "bw"), "beam_depth_ft": w.get("beam_depth_ft", 0.2),
                 "jetty_ft": w.get("jetty_ft", 0.0) if _u(k, "jetty") < w.get("jetty_prob", 1.0 if w.get("jetty_ft") else 0.0) else 0.0,
                 "trim_from_beam": bool(w.get("trim_from_beam", wsys == "halftimber")), "corner_ft": w.get("corner_ft", 0.45)}
    if pl:
        S["plinth"] = {"material": pl.get("material", "stone"), "color": _pick(pl.get("colors"), k, "plinth"), "height_ft": _rng(pl.get("height_ft", [1.5, 2.2]), k, "ph")}
    else:
        S["plinth"] = None
    # roof
    S["roof"] = {"type": rf.get("type"), "material": rf.get("material", "shingle"), "color": _pick(rf.get("colors"), k, "roofc"),
                 "pitch": _rng(rf.get("pitch", [0.6, 0.75]), k, "pitch"), "overhang_ft": _rng(rf.get("overhang_ft", [1.0, 1.3]), k, "ov"),
                 "thickness_ft": rf.get("thickness_ft", 0.0), "ridge_cap": rf.get("ridge_cap"), "barge": bool(rf.get("barge", False)),
                 "stepped_gable": bool(rf.get("stepped_gable", False)), "fascia_color": _pick(rf.get("fascia_colors"), k, "fascia")}
    # windows / door
    S["windows"] = {"type": wi.get("type", "plain"), "cols": int(round(_rng(wi.get("cols", [2, 2]), k, "wc"))), "rows": int(round(_rng(wi.get("rows", [2, 2]), k, "wr"))),
                    "shutters": _u(k, "shut") < wi.get("shutter_prob", 0.0), "shutter_color": _pick(wi.get("shutter_colors"), k, "shutc"),
                    "frame_color": _pick(wi.get("frame_colors"), k, "framec"), "bar_color": wi.get("bar_color", "#2b2b2d"), "hood": bool(wi.get("hood", False)),
                    "shape": _pick(wi.get("shape"), k, "wshape") if isinstance(wi.get("shape"), list) else wi.get("shape", "rect"),
                    "width_ft": _rng(wi.get("width_ft", 1.9), k, "ww"), "height_ft": _rng(wi.get("height_ft", 6.5), k, "wh"), "sill_ft": wi.get("sill_ft"), "triple_width_ft": wi.get("triple_width_ft", 4.8)}
    S["door"] = {"color": _pick(dr.get("colors"), k, "doorc"), "surround": bool(dr.get("surround", True)), "shape": dr.get("shape", "rect")}
    if ch.get("type", "none") != "none" and _u(k, "chim") < ch.get("prob", 1.0):
        S["chimney"] = {"type": ch["type"], "material": ch.get("material", "brick"), "color": _pick(ch.get("colors"), k, "chimc"), "width_ft": ch.get("width_ft", 2.4),
                        "rise_ft": ch.get("rise_ft", 3.0), "end": 1 if _u(k, "chend") < 0.5 else -1}
    else:
        S["chimney"] = None
    S["trim_color"] = _pick(p.get("trim_colors"), k, "trim")
    S["tile_scale"] = float(p.get("tile_scale", 1.0))
    return S


# ------------------------------------------------------------------ materials (dynamic ids, generated textures)
RE_S = re.compile(r"^mat_s_(plaster|brick|board|clap|log|beam|turf|flat)_([0-9a-f]{6})$")
RE_T = re.compile(r"^mat_s_tint_([a-z_]+?)_([0-9a-f]{6})$")
KINDS = {  # kind: tile ft per repeat, roughness, normal strength
    "plaster": (6.0, 0.93, 1.4), "brick": (4.0, 0.88, 3.2), "board": (4.5, 0.86, 2.8), "clap": (4.0, 0.84, 2.4), "log": (4.8, 0.88, 3.2),
    "beam": (3.0, 0.86, 2.0), "turf": (9.0, 0.97, 2.6), "flat": (3.0, 0.8, 0.0)}
TINT_BASES = {"thatch": (14.0, 0.97, 3.0), "shingle": (14.0, 0.85, 3.5), "slate": (14.0, 0.5, 3.5), "red_tile": (14.0, 0.55, 3.5), "timber_roof": (14.0, 0.85, 2.8),
              "door_wood": (3.5, 0.75, 2.4), "trim": (3.0, 0.7, 1.6), "wall_stone": (7.0, 0.85, 4.0), "plank": (5.0, 0.82, 2.2), "wall_batten": (6.0, 0.88, 2.6)}


def _hex(c):
    c = (c or "#808080").lstrip("#").lower()
    return c if re.fullmatch(r"[0-9a-f]{6}", c) else "808080"


def mid_for(kind, color):
    return f"mat_s_{kind}_{_hex(color)}"


def tint_mid(base, color):
    return f"mat_s_tint_{base}_{_hex(color)}"


def is_dynamic(mid):
    return bool(RE_S.match(mid) or RE_T.match(mid))


def info(mid):
    """pbr-style info dict for a dynamic material id, or None."""
    m = RE_S.match(mid)
    if m:
        t, r, n = KINDS[m.group(1)]
        return {"gen": "style", "tile": t, "rough": r, "n": n, "color": "#" + m.group(2)}
    m = RE_T.match(mid)
    if m and m.group(1) in TINT_BASES:
        t, r, n = TINT_BASES[m.group(1)]
        return {"gen": "style", "tile": t, "rough": r, "n": n, "color": "#" + m.group(2), "mr": m.group(1) in ("slate", "red_tile")}
    return None


def material_record(mid):
    c = info(mid)
    if c is None:
        return None
    rec = {"id": mid, "name": mid[4:], "kind": "image", "texture": f"textures/{mid[4:]}.png", "source": None, "sha256": None, "mean_color": c["color"],
           "roughness": c["rough"], "metallic": 0.0, "_pbr": True, "_generated": True}
    if c["n"] > 0:
        rec["normal"] = True
    if c.get("mr"):
        rec["mr"] = True
    return rec


def register_materials(materials, S):
    """Add the dynamic materials a resolved style uses to the pack's material table (idempotent)."""
    for mid in S.get("_mats", ()):
        if mid not in materials:
            materials[mid] = material_record(mid)


# ---- texture generators: (albedo float HxWx3 0..255, height 0..1)
def _P():
    import worldpack_pbr as p
    return p


def _tinted(base_alb, color):
    lum = base_alb @ np.array([0.3, 0.59, 0.11])
    lum = lum / max(lum.mean(), 1e-6)
    return np.clip(_P().hexrgb(color)[None, None, :] * (lum[..., None] ** 0.9), 0, 255)


def _gen_plaster(col, n=512):
    p = _P()
    low, mid, fine = p.fbm(n, 71, 3.0, 1), p.fbm(n, 72, 2.0, 4), p.fbm(n, 73, 1.0, 16)
    base = p.hexrgb(col)
    a = base * (0.92 + 0.1 * low[..., None] + 0.04 * (mid[..., None] - 0.5)) * (0.97 + 0.05 * fine[..., None])
    a = p.lerp(a, a * 0.8, 0.5 * np.clip(low - 0.65, 0, 1))
    return a, 0.5 * mid + 0.5 * fine


def _gen_brick(col, n=512):
    p = _P()
    rng = np.random.RandomState(81)
    base = p.hexrgb(col)
    rows, per = 16, 6
    rh = n // rows
    alb = np.zeros((n, n, 3))
    h = np.zeros((n, n))
    mortar = np.array([176.0, 168.0, 152.0])
    yy, xx = np.mgrid[0:n, 0:n]
    for r in range(rows):
        off = (r % 2) * (n // per) // 2
        for c in range(per + 1):
            x0 = c * (n // per) - off
            bw = n // per
            tone = base * rng.uniform(0.82, 1.14) * np.array([1, rng.uniform(.95, 1.05), rng.uniform(.93, 1.07)])
            ys = np.arange(r * rh + 3, (r + 1) * rh - 1) % n
            xs = np.arange(x0 + 3, x0 + bw - 2) % n
            if len(xs) == 0:
                continue
            alb[np.ix_(ys, xs)] = tone
            h[np.ix_(ys, xs)] = 1.0
    m = h < 0.5
    alb[m] = mortar
    cloud = p.fbm(n, 82, 2.5, 2)
    alb *= (0.9 + 0.2 * cloud[..., None])
    return alb, p.blur(h, 0.9) * 0.9 + 0.1 * p.fbm(n, 83, 1.0, 16)


def _gen_board(col, n=512):
    """Vertical boards with battens over the joints (falu / board and batten)."""
    p = _P()
    base = p.hexrgb(col)
    count = 7
    bw = n // count
    alb = np.zeros((n, n, 3))
    h = np.zeros((n, n))
    for k in range(count):
        x0 = k * bw
        g = p.fbm(n, 90 + k, 1.4, 1, shape=(n, bw))
        tone = base * (0.86 + 0.2 * g[..., None]) * np.random.RandomState(k).uniform(0.94, 1.06)
        alb[:, x0:x0 + bw] = tone
        h[:, x0:x0 + bw] = 0.7 + 0.2 * g
    bat = 22
    for k in range(count):
        xs = np.arange(k * bw - bat // 2, k * bw + bat // 2) % n
        alb[:, xs] = alb[:, xs] * 1.06
        h[:, xs] = 1.0
        sh = np.arange(k * bw + bat // 2, k * bw + bat // 2 + 5) % n
        alb[:, sh] *= 0.72
    return np.clip(alb, 0, 255), p.blur(h, 0.7)


def _gen_clap(col, n=512):
    p = _P()
    base = p.hexrgb(col)
    rows = 10
    rh = n // rows
    alb = np.zeros((n, n, 3))
    h = np.zeros((n, n))
    for r in range(rows):
        g = p.fbm(n, 100 + r, 1.5, 1, shape=(rh, n))
        y = np.arange(rh)[:, None]
        slope = 0.55 + 0.45 * (y / rh)
        tone = base * (0.86 + 0.22 * g[..., None]) * np.random.RandomState(r + 5).uniform(0.95, 1.05)
        tone = tone * (1.0 - 0.28 * np.clip((y - rh * 0.8) / (rh * 0.2), 0, 1))[..., None]
        alb[r * rh:(r + 1) * rh] = tone
        h[r * rh:(r + 1) * rh] = slope * (0.9 + 0.1 * g)
    return np.clip(alb, 0, 255), p.blur(h, 0.6)


def _gen_log(col, n=512):
    p = _P()
    base = p.hexrgb(col)
    rows = 6
    rh = n // rows
    alb = np.zeros((n, n, 3))
    h = np.zeros((n, n))
    for r in range(rows):
        g = p.fbm(n, 120 + r, 1.3, 1, shape=(rh, n))
        y = (np.arange(rh)[:, None] + 0.5) / rh
        prof = np.sin(np.pi * y)
        tone = base * (0.8 + 0.3 * g[..., None]) * (0.45 + 0.7 * prof[..., None]) * np.random.RandomState(r + 11).uniform(0.9, 1.08)
        alb[r * rh:(r + 1) * rh] = tone
        h[r * rh:(r + 1) * rh] = prof ** 0.6 * (0.9 + 0.1 * g)
    return np.clip(alb, 0, 255), p.blur(h, 0.8)


def _gen_beam(col, n=256):
    p = _P()
    base = p.hexrgb(col)
    g = p.fbm(n, 130, 1.0, 1, shape=(n, n))
    streak = p.blur(p.fbm(n, 131, 1.0, 1, shape=(n, n)), 0)
    gx = p.fbm(n, 132, 3.0, 1, shape=(n, n // 8))
    gr = np.repeat(gx, 8, axis=1)                        # stretched along x: grain runs along the image's horizontal axis? (stretch columns -> vertical)
    gr = gr.T if False else p.fbm(n, 133, 1.2, 1, shape=(n // 8, n))
    gr = np.repeat(gr, 8, axis=0)
    a = base * (0.7 + 0.6 * gr[..., None]) * (0.9 + 0.2 * g[..., None])
    return np.clip(a, 0, 255), 0.5 * gr + 0.5 * streak


def _gen_turf(col, n=512):
    p = _P()
    base = p.hexrgb(col)
    a, h = p.fbm(n, 140, 2.0, 2), p.fbm(n, 141, 1.0, 12)
    tone = base * (0.7 + 0.5 * a[..., None]) * (0.85 + 0.3 * h[..., None])
    tone = p.lerp(tone, p.hexrgb("#5a4a30"), 0.3 * np.clip(a - 0.7, 0, 1) * 3)
    return np.clip(tone, 0, 255), 0.5 * a + 0.5 * h


def _gen_flat(col, n=64):
    p = _P()
    return np.tile(p.hexrgb(col), (n, n, 1)), np.full((n, n), 0.5)


_GEN = {"plaster": _gen_plaster, "brick": _gen_brick, "board": _gen_board, "clap": _gen_clap, "log": _gen_log, "beam": _gen_beam, "turf": _gen_turf, "flat": _gen_flat}


def gen_texture(mid):
    """(albedo, height) for a dynamic material id."""
    m = RE_S.match(mid)
    if m:
        a, h = _GEN[m.group(1)]("#" + m.group(2))
        return a, np.clip(h, 0.0, 1.0)
    m = RE_T.match(mid)
    base = m.group(1)
    bt = _P().base_texture("mat_" + base)
    if bt is None:
        return _gen_flat("#" + m.group(2))
    alb, h = bt
    return _tinted(alb, "#" + m.group(2)), h


# ------------------------------------------------------------------ applying a style to a building entity
FLATS = ("mat_s_flat_3a3a3e", "mat_s_flat_1c1a18", "mat_s_flat_d9d0b8")
ROOF_BASE = {"thatch": "mat_thatch", "shingle": "mat_shingle", "slate": "mat_slate", "tile": "mat_red_tile", "red_tile": "mat_red_tile", "timber": "mat_timber_roof"}
ROOF_TILE = {"thatch": 14.0, "shingle": 14.0, "slate": 14.0, "tile": 14.0, "red_tile": 14.0, "timber": 14.0, "turf": 14.0}


def wall_mat(kind, color):
    if kind in ("stone", "wall_stone"):
        return tint_mid("wall_stone", color) if color else "mat_wall_stone"
    return mid_for(kind, color or "#d8d0bc")


def apply_style(e, district=None):
    """Entity copy with the style's wall/roof/proportions and `_style` (resolved parameters + the material ids it needs), or `e` itself when it has no style."""
    sid = e.get("style")
    if not sid:
        return e
    kind = e.get("kind") or (e.get("tags") or {}).get("subtype") or ""
    dist = district or e.get("district") or (e.get("tags") or {}).get("district")
    S = resolve(sid, e["id"], kind, dist)
    if S is None:
        return e
    W, R, PL = S["wall"], S["roof"], S["plinth"]
    mats = set()
    wm_id = wall_mat(W["material"], W["color"])
    mats.add(wm_id)
    # roof surface
    rb = R["material"]
    if rb == "turf":
        rm = mid_for("turf", R["color"] or "#6b7d3a")
    elif R["color"] and rb in ROOF_BASE:
        rm = tint_mid(ROOF_BASE[rb][4:], R["color"])
    else:
        rm = ROOF_BASE.get(rb, "mat_shingle")
    mats.add(rm)
    S["wall_mat"], S["roof_mat"] = wm_id, rm
    S["beam_mat"] = mid_for("beam", W["beam_color"]) if W["system"] in ("halftimber", "corners", "log") or W["beam_color"] else None
    S["_mats"] = mats
    out = dict(e)
    out["wall"] = {**e["wall"], "surface": {**e["wall"]["surface"], "material": wm_id, "tile_ft": (info(wm_id) or {}).get("tile", 6.0)}}
    r = dict(e["roof"])
    o = e["obb"]
    if R["type"] in ("gable", "hip"):
        r["type"] = R["type"]
    r["ridge_height_ft"] = round(o["width_ft"] / 2 * R["pitch"], 3)
    r["pitch"] = R["pitch"]
    r["overhang_ft"] = R["overhang_ft"]
    r["surface"] = {**r.get("surface", {}), "material": rm, "tile_ft": ROOF_TILE.get(rb, 14.0) * S["tile_scale"]}
    out["roof"] = r
    mm = {}
    tc = S["trim_color"]
    if W["trim_from_beam"] and S["beam_mat"]:
        mm["mat_trim"] = S["beam_mat"]
    elif tc:
        mm["mat_trim"] = tint_mid("trim", tc)
        mats.add(mm["mat_trim"])
    if S["door"]["color"]:
        mm["mat_door_wood"] = tint_mid("door_wood", S["door"]["color"])
        mats.add(mm["mat_door_wood"])
    S["mat_map"] = mm
    if PL:
        S["plinth_mat"] = wall_mat(PL["material"], PL["color"]) if PL["material"] != "stone" else wall_mat("stone", PL["color"])
        mats.add(S["plinth_mat"])
    if S["beam_mat"]:
        mats.add(S["beam_mat"])
    if S["chimney"]:
        S["chimney"]["mat"] = wall_mat(S["chimney"]["material"], S["chimney"]["color"] or "#8a4a3a") if S["chimney"]["material"] != "stone" else wall_mat("stone", S["chimney"]["color"])
        mats.add(S["chimney"]["mat"])
    if S["windows"]["shutters"]:
        S["shutter_mat"] = mid_for("board", S["windows"]["shutter_color"] or "#3a5a40")
        mats.add(S["shutter_mat"])
    if R.get("fascia_color"):
        S["fascia_mat"] = mid_for("board", R["fascia_color"])
        mats.add(S["fascia_mat"])
    S["trim_mat"] = mm.get("mat_trim", "mat_trim")
    for k in ("door_mat",):
        pass
    mats |= set(FLATS)
    S["_mats"] = mats | {v for v in mm.values() if is_dynamic(v)}
    S["_mats"] = {m for m in S["_mats"] if is_dynamic(m)}
    out["_style"] = S
    return out


def style_materials(entities):
    """Set of dynamic material ids used by styled entities (for tests and tools)."""
    s = set()
    for e in entities:
        s |= set((e.get("_style") or {}).get("_mats", ()))
    return s


# ------------------------------------------------------------------ CLI (the Illustrator panel's Buildings tab calls this as a job)
def _world_dir(place):
    root = os.environ.get("VB_WORLD_ROOT") or os.path.join(HERE, "..", "..", "world")      # VB_WORLD_ROOT: tests and --world-root point at a copy
    return os.path.join(root, place)


def _iter_buildings(place):
    d = os.path.join(_world_dir(place), "buildings")
    for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if fn.endswith(".json"):
            p = os.path.join(d, fn)
            with open(p, encoding="utf-8") as f:
                yield p, json.load(f)


def assign(place, style, ids=None, kind=None, district=None, dry=False, all_=False):
    """Write (or clear, style in (None, "", "none")) the `style` key of the selected buildings in world/<place>/buildings/*.json.
    Selection: explicit ids, and/or a kind, and/or a district (a building is selected when it matches every filter given). Returns {changed: [...], ...}."""
    if style in ("", "none", "legacy", "null"):
        style = None
    if style and style != "auto" and style not in load_presets():
        raise SystemExit(f"unknown style {style!r}; known: {', '.join(sorted(load_presets()))}")
    want = set(ids or [])
    changed = []
    dist_of = {}
    if district:                      # district membership comes from the exported/derived tags: point in polygon of districts.json
        dist_of = _district_of(place)
    for p, b in _iter_buildings(place):
        if want and b["id"] not in want:
            continue
        if kind and b.get("kind") != kind:
            continue
        if district and dist_of.get(b["id"]) != district and b.get("district") != district:
            continue
        if not (want or kind or district or all_):
            continue
        if style:
            b["style"] = style
        else:
            b.pop("style", None)
        changed.append(b["id"])
        if not dry:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(b, f, indent=1, ensure_ascii=False)
                f.write("\n")
    return {"place": place, "style": style, "changed": changed, "count": len(changed), "dry": dry}


def _district_of(place):
    try:
        from shapely.geometry import Point, Polygon
        with open(os.path.join(_world_dir(place), "districts.json"), encoding="utf-8") as f:
            ds = json.load(f)["districts"]
        polys = [(d["id"], Polygon(d["geometry"]["points"] if "geometry" in d else d["polygon"])) for d in ds if (d.get("geometry") or d.get("polygon"))]
        out = {}
        for p, b in _iter_buildings(place):
            pts = b["geometry"]["points"]
            c = Point(sum(q[0] for q in pts) / len(pts), sum(q[1] for q in pts) / len(pts))
            for did, pg in polys:
                if pg.contains(c):
                    out[b["id"]] = did
                    break
        return out
    except Exception:
        return {}


def summary(place):
    """{buildings: [{id, kind, floors, style, resolved}], presets: [...]} for the panel."""
    rows = []
    for p, b in _iter_buildings(place):
        rows.append({"id": b["id"], "kind": b.get("kind"), "floors": b.get("floors", 1), "style": b.get("style"), "district": b.get("district")})
    return {"place": place, "buildings": rows, "presets": list_presets()}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ap.add_argument("--world-root", help="folder holding the place folders (default: repo world/)")
    sub.add_parser("list")
    s = sub.add_parser("summary")
    s.add_argument("--place", required=True)
    s = sub.add_parser("assign")
    s.add_argument("--place", required=True)
    s.add_argument("--style", required=True, help="preset id, auto, or none")
    s.add_argument("--ids")
    s.add_argument("--kind")
    s.add_argument("--district")
    s.add_argument("--all", action="store_true", help="every building of the place")
    s.add_argument("--dry", action="store_true")
    s = sub.add_parser("resolve")
    s.add_argument("--style", required=True)
    s.add_argument("--id", default="bld_x")
    a = ap.parse_args(argv)
    if a.world_root:
        os.environ["VB_WORLD_ROOT"] = a.world_root
    if a.cmd == "list":
        out = {"presets": list_presets()}
    elif a.cmd == "summary":
        out = summary(a.place)
    elif a.cmd == "assign":
        out = assign(a.place, a.style, a.ids.split(",") if a.ids else None, a.kind, a.district, a.dry, a.all)
    else:
        out = resolve(a.style, a.id)
        out = {k: v for k, v in (out or {}).items() if k != "_mats"}
    print(json.dumps(out, ensure_ascii=False, default=list))


if __name__ == "__main__":
    main()
