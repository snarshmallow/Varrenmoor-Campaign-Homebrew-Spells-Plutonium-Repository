"""Create a complete, generic place (terrain, water, streets, districts, buildings, view settings) from a JSON spec.

  python illustrator/generators/place_create.py create   SPEC.json [--id ID] [--draft] [--force] [--no-town] [--dry-run] [--out-root DIR]
  python illustrator/generators/place_create.py validate SPEC.json
  python illustrator/generators/place_create.py prompt-help            # schema + vocabulary + templates (hand this to Claude, who writes the spec from plain words)
  python illustrator/generators/place_create.py from-text "walled coastal town of 800 people with a big river, Danish style, hilly" [--out spec.json] [--create]
  python illustrator/generators/place_create.py templates [--show NAME]   # the presets/places/*.json starting points
  python illustrator/generators/place_create.py regen --place ID [--terrain] [--no-town] [--meander straight|gentle|lazy] [--draft]
  python illustrator/generators/place_create.py write-schema         # rewrite world/schema/place-spec.schema.json from the schema in this file

Output (world/<id>/): place.json, terrain_spec.json, terrain/ (heightmap.npy, heightmap_16.png, terrain_meta.json), water.json, town_params.json,
streets.json, districts.json, buildings/*.json, town_gen_report.json, view_settings.json, walls.json (walled towns), place_spec.json (the spec as run),
create_report.json. Every existing tool (render_world, shading, lighting, region_extract, worldpack, foundry_push, padding, skybox, foliage) takes
--place <id> and works on it. Nothing here is specific to Bridgehollow: naming comes from presets/naming/*.json (culture), the terrain from
place_terrain.py recipes, the town structure from the spec's town block, elevation-banded presets are mapped onto the place's own relief
(place.json phase_elevation = percentile).

Same spec + seed => identical output. Last stdout line is a JSON result for the panel's runner. Progress lines start with "PROGRESS ".
"""
import argparse
import copy
import hashlib
import json
import math
import os
import re
import shutil
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ILL = os.path.join(REPO, "illustrator")
PLACE_PRESETS = os.path.join(ILL, "presets", "places")
NAMING_DIR = os.path.join(ILL, "presets", "naming")
SCHEMA_PATH = os.path.join(REPO, "world", "schema", "place-spec.schema.json")

LAYOUTS = ("organic", "radial", "grid", "linear", "walled")
CULTURES = ("fantasy_generic", "scandinavian", "danish_german", "english")
CLIMATES = ("temperate", "cold", "dry", "coastal")
SEASONS = ("summer", "autumn", "winter")
FEATURES = ("market", "green", "temple", "castle", "none")
SIDES = ("auto", "north", "south", "east", "west")
LIMITS_DEFAULT = {"max_buildings": 1200, "max_area_ft2": 3000000, "max_place_ft": 9000, "allow_large": False, "draft": False}

SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://varrenmoor.local/schema/place-spec.schema.json",
    "title": "varrenmoor place spec v1",
    "description": "Input of illustrator/generators/place_create.py. Everything but `name` or `id` is optional; omitted fields take the defaults printed by `place_create.py prompt-help`.",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "$schema": {"type": "string"},
        "_note": {"type": "string"},
        "id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9_]{1,40}$", "description": "folder name world/<id>/ (lower case, digits, underscore). Default: slug of name."},
        "name": {"type": "string", "description": "display name. Default: generated from the culture's name parts and the seed."},
        "seed": {"type": "integer", "description": "same spec + seed = same place. Default: derived from the id."},
        "culture": {"enum": list(CULTURES), "description": "naming set (streets, buildings, districts) from presets/naming/*.json, and default building styles"},
        "size_ft": {"type": "array", "items": {"type": "number", "minimum": 800, "maximum": 12000}, "minItems": 2, "maxItems": 2,
                    "description": "[width, height] of the place in feet. Default: from the population (about 2200 x 1400 for 600 people)."},
        "cell_ft": {"type": "number", "minimum": 4, "maximum": 40, "description": "heightmap cell size, default 10"},
        "terrain": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "recipe": {"enum": ["flat", "rolling", "hills", "valley", "bowl", "coastal", "island", "pass", "fjord", "mountain"]},
                "relief_ft": {"type": "number", "minimum": 0, "maximum": 3000, "description": "height of ridges / hills above the base plane"},
                "ruggedness": {"type": "number", "minimum": 0, "maximum": 1},
                "base_elevation_ft": {"type": "number", "description": "elevation of the base plane at the map centre (default per recipe)"},
                "sea_level_ft": {"type": "number", "description": "datum; ground below it is water (default 0)"},
                "sea_side": {"enum": ["north", "south", "east", "west"], "description": "which map edge is the sea (coastal / fjord)"},
                "rivers": {"type": "integer", "minimum": 0, "maximum": 3, "description": "number of rivers (the first is the main one)"},
                "river_meander": {"enum": ["straight", "gentle", "lazy"]},
                "river_width_ft": {"type": "number", "minimum": 8, "maximum": 300},
                "river_meander_params": {"type": "object", "description": "explicit meander numbers: amplitude_ft, wavelength_ft, seed, width_var, bars (see river_meander.py)"},
                "lakes": {"type": "integer", "minimum": 0, "maximum": 4},
                "cell_ft": {"type": "number", "minimum": 4, "maximum": 40}}},
        "town": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "population": {"type": "integer", "minimum": 20, "maximum": 12000},
                "layout": {"enum": list(LAYOUTS), "description": "street pattern: organic (default), radial, grid, linear (along the main road), walled (compact rings + wall and gates)"},
                "districts": {"description": "'auto' or a list of 1-4 {name?, kind: civic|residential} from the centre outward; a farmland ring is always added last",
                              "oneOf": [{"const": "auto"}, {"type": "array", "minItems": 1, "maxItems": 4,
                                                           "items": {"type": "object", "additionalProperties": False, "properties": {"name": {"type": "string"}, "kind": {"enum": ["civic", "residential"]}}}}]},
                "centre": {"description": "'auto' (best flat ground) or [x, y] feet", "oneOf": [{"const": "auto"}, {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}]},
                "entry_side": {"enum": list(SIDES), "description": "which map edge the main road comes in from (auto = from the recipe)"},
                "central_feature": {"enum": list(FEATURES), "description": "market square (default), village green, temple / church beside the square, castle keep, or nothing"},
                "wall": {"type": "boolean", "description": "town wall round the built-up districts with gates where roads cross (implied by layout walled)"},
                "gates": {"type": "integer", "minimum": 1, "maximum": 6},
                "extra_civic": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "size": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}, "floors": {"type": "integer"}, "notes": {"type": "string"}}, "required": ["name"]}},
                "farmland": {"type": "boolean", "description": "farm fringe round the town (default true)"}}},
        "styles": {"description": "'auto' (from the culture) or {building kind: [style preset ids]} (presets/building_styles)",
                   "oneOf": [{"const": "auto"}, {"type": "object", "additionalProperties": {"type": "array", "items": {"type": "string"}}}]},
        "climate": {"enum": list(CLIMATES)},
        "season": {"enum": list(SEASONS)},
        "foliage": {"type": "object", "properties": {"mix": {"type": "string"}, "density": {"type": "number"}}, "additionalProperties": False},
        "limits": {"type": "object", "additionalProperties": False, "properties": {
            "max_buildings": {"type": "integer"}, "max_area_ft2": {"type": "number"}, "max_place_ft": {"type": "number"},
            "allow_large": {"type": "boolean", "description": "lift the caps (a very big town can take minutes and a lot of memory)"},
            "draft": {"type": "boolean", "description": "draft quality: coarse terrain, civic buildings only (no houses): seconds instead of a minute"}}},
        "foundry": {"type": "object", "description": "links.foundry_scene etc. when the place came from a Foundry scene (import-scene)"},
    },
}

# ------------------------------------------------------------------ culture data
STYLE_SETS = {
    "fantasy_generic": {"house": ["tudor", "danish_fachwerk", "falu_cottage"], "farmhouse": ["falu_cottage", "danish_fachwerk"], "barn": ["town_barn"], "shed": ["falu_cottage", "tarred_timber"],
                        "stable": ["town_barn"], "craft": ["tudor", "danish_fachwerk"], "civic": ["town_guildhall"], "inn": ["town_inn"]},
    "scandinavian": {"house": ["norse_log", "falu_cottage", "tarred_timber"], "farmhouse": ["norse_log", "falu_cottage"], "barn": ["town_barn"], "shed": ["tarred_timber", "norse_log"],
                     "stable": ["town_barn"], "craft": ["tarred_timber", "norse_log"], "civic": ["town_guildhall"], "inn": ["town_inn"]},
    "danish_german": {"house": ["danish_fachwerk", "hanseatic_brick"], "farmhouse": ["niedersachsen_halle", "danish_longhouse"], "barn": ["town_barn"], "shed": ["danish_fachwerk"],
                      "stable": ["town_barn"], "craft": ["danish_fachwerk", "hanseatic_brick"], "civic": ["hanseatic_brick", "town_guildhall"], "inn": ["town_inn"]},
    "english": {"house": ["tudor"], "farmhouse": ["tudor", "farm_longhouse"], "barn": ["town_barn"], "shed": ["tudor"], "stable": ["town_barn"], "craft": ["tudor"],
                "civic": ["town_guildhall"], "inn": ["town_inn"]},
}
STYLE_BY_NAMEKEY = {"hall": "town_guildhall", "court": "town_guildhall", "tax": "town_guildhall", "lockup": "town_watchhouse", "inn": "town_inn", "stables": "town_barn",
                    "meeting": "town_guildhall", "smithy": "town_smithy", "gate": "town_watchhouse", "mill": "watermill"}
CHURCH = {"fantasy_generic": ("Parish Church", "parish_church"), "scandinavian": ("Stave Church", "stave_church"), "danish_german": ("Parish Church (Kirche)", "parish_church"),
          "english": ("Parish Church", "parish_church")}
KEEP = {"fantasy_generic": "The Keep", "scandinavian": "The Hall of the Jarl", "danish_german": "The Burg", "english": "The Castle"}
GREEN = {"fantasy_generic": "Village Green", "scandinavian": "Bygdatunet", "danish_german": "Dorfanger", "english": "The Green"}
SQUARES = {"fantasy_generic": ("Market Square", "Court Square"), "scandinavian": ("Torget", "Tingplassen"), "danish_german": ("Marktplatz", "Rathausplatz"), "english": ("Market Place", "Guildhall Square")}
DISTRICT_NAMES = {   # first = centre outward
    "fantasy_generic": {"civic": ["Old Town", "Market Ward", "Crown Ward"], "residential": ["Weavers' Quarter", "Lower Town", "Brook Ward", "The Commons"], "farm": ["Farmland"]},
    "scandinavian": {"civic": ["Torget", "Tinget", "Hovedgard"], "residential": ["Havna", "Bryggekvartalet", "Nedre By", "Strandbyen"], "farm": ["Utmarka"]},
    "danish_german": {"civic": ["Altstadt", "Rathausviertel", "Markt"], "residential": ["Neustadt", "Fischerviertel", "Handwerkerviertel", "Vorstadt"], "farm": ["Feldmark"]},
    "english": {"civic": ["The Borough", "Cross Ward", "Guildhall Ward"], "residential": ["Tanners' Ward", "Bridge End", "Low Street", "Southgate"], "farm": ["The Commons"]},
}
PHASE_BY_CLIMATE = {"temperate": "temperate_valley_calm", "cold": "alpine_steep_calm", "dry": "dry_hills_calm", "coastal": "coastal_basin_calm"}
PADDING_BY_RECIPE = {"flat": "flat-plain", "rolling": "rolling-hills", "hills": "rolling-hills", "valley": "bowl-ridge", "bowl": "bowl-ridge", "coastal": "coastal-flats",
                     "island": "coastal-flats", "pass": "fjord-walls", "fjord": "fjord-walls", "mountain": "fjord-walls"}
FOLIAGE_BY_CLIMATE = {"temperate": "oak_beech_wood", "cold": "spruce_forest", "dry": "pine_heath", "coastal": "pine_heath"}


# ------------------------------------------------------------------ small helpers
def slug(s):
    s = re.sub(r"[^a-z0-9]+", "_", (s or "").lower().strip()).strip("_")
    return s[:40] or "place"


def jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def jsave(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


def nice_scale(v):
    for s in (10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 125, 150, 200, 250, 300, 400, 500, 600, 800, 1000):
        if v <= s:
            return s
    return 1000


def load_naming(culture):
    return jload(os.path.join(NAMING_DIR, culture + ".json"))


def category(pop):
    return "hamlet" if pop < 150 else "village" if pop < 450 else "town" if pop < 2500 else "city"


def say(i, n, msg):
    print(f"PROGRESS {i}/{n} {msg}", flush=True)


# ------------------------------------------------------------------ validation / normalisation
def _check(schema, val, path, errs):
    """A small JSON-schema subset checker (type, enum, const, min/max, items, properties, additionalProperties, oneOf, required, pattern); enough for place specs."""
    if "const" in schema:
        if val != schema["const"]:
            errs.append(f"{path}: must be {schema['const']!r}")
        return
    if "oneOf" in schema:
        trial = []
        for s in schema["oneOf"]:
            e = []
            _check(s, val, path, e)
            trial.append(e)
        if not any(not e for e in trial):
            errs.append(f"{path}: {trial[-1][0] if trial[-1] else 'no alternative matches'}")
        return
    if "enum" in schema and val not in schema["enum"]:
        errs.append(f"{path}: {val!r} is not one of {schema['enum']}")
        return
    t = schema.get("type")
    tmap = {"object": dict, "array": list, "string": str, "boolean": bool}
    if t in tmap and not isinstance(val, tmap[t]):
        errs.append(f"{path}: must be {t}")
        return
    if t == "integer" and (not isinstance(val, int) or isinstance(val, bool)):
        errs.append(f"{path}: must be an integer")
        return
    if t == "number" and (not isinstance(val, (int, float)) or isinstance(val, bool)):
        errs.append(f"{path}: must be a number")
        return
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if "minimum" in schema and val < schema["minimum"]:
            errs.append(f"{path}: {val} is below the minimum {schema['minimum']}")
        if "maximum" in schema and val > schema["maximum"]:
            errs.append(f"{path}: {val} is above the maximum {schema['maximum']}")
    if isinstance(val, str) and "pattern" in schema and not re.match(schema["pattern"], val):
        errs.append(f"{path}: {val!r} does not match {schema['pattern']}")
    if isinstance(val, list):
        if "minItems" in schema and len(val) < schema["minItems"]:
            errs.append(f"{path}: needs at least {schema['minItems']} items")
        if "maxItems" in schema and len(val) > schema["maxItems"]:
            errs.append(f"{path}: at most {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(val):
                _check(schema["items"], v, f"{path}[{i}]", errs)
    if isinstance(val, dict):
        props = schema.get("properties", {})
        for r in schema.get("required", []):
            if r not in val:
                errs.append(f"{path}: missing required {r!r}")
        for k, v in val.items():
            if k in props:
                _check(props[k], v, f"{path}.{k}", errs)
            elif isinstance(schema.get("additionalProperties"), dict):
                _check(schema["additionalProperties"], v, f"{path}.{k}", errs)
            elif schema.get("additionalProperties") is False and not k.startswith("_"):
                errs.append(f"{path}: unknown field {k!r} (allowed: {', '.join(sorted(props))})")


def validate(spec):
    """-> (errors, warnings). Errors stop creation; warnings are advice."""
    errs, warns = [], []
    if not isinstance(spec, dict):
        return ["spec must be a JSON object"], []
    _check(SPEC_SCHEMA, spec, "spec", errs)
    if not spec.get("id") and not spec.get("name"):
        errs.append("spec: give at least `name` or `id`")
    t = spec.get("terrain") or {}
    if t.get("recipe") in ("coastal", "fjord") and not t.get("sea_side") and t.get("recipe") == "coastal":
        warns.append("terrain.sea_side not given: the sea is on the south edge")
    if t.get("sea_side") and t.get("recipe") not in ("coastal", "fjord", None):
        warns.append("terrain.sea_side only matters for the coastal and fjord recipes")
    tw = spec.get("town") or {}
    if tw.get("layout") == "walled" and tw.get("wall") is False:
        warns.append("layout walled with wall false: no wall will be drawn")
    if spec.get("size_ft") and tw.get("population"):
        W, H = spec["size_ft"]
        if W * H < tw["population"] * 1000 * 2.5:
            warns.append(f"size_ft {W}x{H} is small for {tw['population']} people: the town will fill most of the place (try {round(math.sqrt(tw['population'] * 1000 * 6 * 1.6), -2)} ft wide)")
    pc = spec.get("culture")
    if pc and pc not in CULTURES:
        errs.append(f"culture {pc!r} unknown")
    st = spec.get("styles")
    if isinstance(st, dict):
        import building_styles as bs
        have = set(bs.load_presets())
        for k, lst in st.items():
            for s in lst:
                if s not in have:
                    errs.append(f"styles.{k}: unknown style preset {s!r}")
    return errs, warns


def normalise(spec, strict=True):
    """Fill every default; returns the full spec (what is saved as place_spec.json) and the derived numbers."""
    errs, warns = validate(spec)
    if errs and strict:
        raise SystemExit("invalid place spec:\n  " + "\n  ".join(errs))
    s = copy.deepcopy(spec)
    culture = s.setdefault("culture", "fantasy_generic")
    nm = load_naming(culture)
    pid = s.get("id") or slug(s.get("name"))
    s["id"] = pid
    if "seed" not in s:
        s["seed"] = int(hashlib.md5(pid.encode()).hexdigest()[:6], 16) % 9000 + 100
    seed = int(s["seed"])
    t = s.setdefault("terrain", {})
    t.setdefault("recipe", "rolling")
    tw = s.setdefault("town", {})
    tw.setdefault("population", 600)
    tw.setdefault("layout", "organic")
    tw.setdefault("districts", "auto")
    tw.setdefault("centre", "auto")
    tw.setdefault("entry_side", "auto")
    tw.setdefault("central_feature", "market")
    tw.setdefault("farmland", True)
    if tw["layout"] == "walled":
        tw.setdefault("wall", True)
    tw.setdefault("wall", False)
    tw.setdefault("gates", 2 if tw["population"] < 1500 else 3)
    pop = int(tw["population"])
    s.setdefault("styles", "auto")
    s.setdefault("climate", {"coastal": "coastal", "island": "coastal", "fjord": "cold", "mountain": "cold", "pass": "cold"}.get(t["recipe"], "temperate"))
    s.setdefault("season", "summer")
    s["limits"] = {**LIMITS_DEFAULT, **(s.get("limits") or {})}
    if "name" not in s:
        import random
        r = random.Random(seed)
        tn = nm["town_names"]
        s["name"] = r.choice(tn["prefix"]) + r.choice(tn["suffix"])
        s["name"] = s["name"][0].upper() + s["name"][1:]
    area = max(pop * 1000.0, 60000.0)
    if "size_ft" not in s:
        W = max(1600, round(math.sqrt(area * 6 * 1.6), -2))
        s["size_ft"] = [int(W), int(round(W / 1.6, -2))]
    s["_derived"] = {"category": category(pop), "target_area_ft2": area, "est_buildings": round(pop * 0.45) + (12 if tw["farmland"] else 0)}
    return s, warns


def check_caps(s, draft):
    """Refuse towns that would freeze the app unless limits.allow_large. -> list of problems."""
    L, d, out = s["limits"], s["_derived"], []
    if L["allow_large"]:
        return out
    W, H = s["size_ft"]
    if max(W, H) > L["max_place_ft"]:
        out.append(f"place {W}x{H} ft is larger than the {L['max_place_ft']} ft cap")
    if d["target_area_ft2"] > L["max_area_ft2"]:
        out.append(f"a town of {s['town']['population']} people needs about {d['target_area_ft2']:,.0f} ft2 (cap {L['max_area_ft2']:,.0f})")
    if d["est_buildings"] > L["max_buildings"] and not draft:
        out.append(f"about {d['est_buildings']} buildings (cap {L['max_buildings']}); use draft quality (civic buildings only) or limits.allow_large")
    return out


# ------------------------------------------------------------------ town parameters
def _ring_set(s, nm):
    """-> (rings list for ring_spec, R). Names from the spec, else the culture."""
    tw, cat = s["town"], s["_derived"]["category"]
    A = s["_derived"]["target_area_ft2"]
    R = math.sqrt(A / math.pi)
    dn = DISTRICT_NAMES[s["culture"]]
    dist = tw["districts"]
    if dist == "auto":
        kinds = {"hamlet": ["residential"], "village": ["residential"], "town": ["civic", "residential"], "city": ["civic", "residential", "residential"]}[cat]
        dist = [{"kind": k} for k in kinds]
    n = len(dist)
    radii = {1: [1.1], 2: [0.52, 1.19], 3: [0.4, 0.8, 1.2], 4: [0.3, 0.6, 0.9, 1.25]}[n]
    big = cat in ("hamlet", "village")
    prof = {"civic": dict(street_width=24, dsep=[70, 85], lot_area=[1300, 3000], build_prob=0.95),
            "residential": dict(street_width=16 if big else 18, dsep=[75, 95] if cat == "hamlet" else [62, 76] if not big else [68, 84],
                                lot_area=[700, 1700] if cat == "hamlet" else [420, 900] if not big else [550, 1200], build_prob=0.9 if big else 0.95)}
    rings, cnt = [], {"civic": 0, "residential": 0}
    for i, d in enumerate(dist):
        kind = d.get("kind", "residential")
        name = d.get("name") or (dn[kind][cnt[kind] % len(dn[kind])] if cnt[kind] < len(dn[kind]) else f"{dn[kind][0]} {cnt[kind] + 1}")
        cnt[kind] += 1
        rid = ("core" if i == 0 else f"ring{i + 1}")
        rings.append({"id": rid, "name": name, "kind": kind, "r_max": round(radii[i] * R), **prof[kind]})
    fn = dn["farm"][0]
    rings.append({"id": "farm", "name": fn, "kind": "farm", "r_max": 1000000000, "street_width": 13, "dsep": [150, 200], "lot_area": [16000, 48000], "build_prob": 0.3 if tw["farmland"] else 0.0})
    return rings, R


LAYOUT_STREETS = {
    "organic": {"streets": {}, "noise": 0.2, "aspect": [0.85, 0.95]},
    "radial": {"streets": {"ring_weight": 1.5, "grid_weight": 0.2, "contour_weight": 2.0}, "noise": 0.08, "aspect": [1.0, 1.0]},
    "grid": {"streets": {"grid_weight": 2.6, "ring_weight": 0.15, "noise_angle_deg": 6, "seed_jitter": 0.1, "contour_weight": 1.2, "chaikin": 0}, "noise": 0.03, "aspect": [1.0, 1.0]},
    "linear": {"streets": {"road_weight": 4.0, "road_decay_ft": 520, "ring_weight": 0.2, "grid_weight": 1.3}, "noise": 0.12, "aspect": "along_road"},
    "walled": {"streets": {"ring_weight": 1.0, "grid_weight": 0.8}, "noise": 0.06, "aspect": [1.0, 1.0]},
}


def build_params(s, centre, entry, via, nm, draft):
    """town_params.json for town_gen from the normalised spec."""
    tw = s["town"]
    cat = s["_derived"]["category"]
    rings, R = _ring_set(s, nm)
    lay = LAYOUT_STREETS[tw["layout"]]
    asp = lay["aspect"]
    if asp == "along_road":
        horiz = entry[0] <= 1 or entry[0] >= s["size_ft"][0] - 1
        asp = [1.8, 0.6] if horiz else [0.6, 1.8]
    sq_m, sq_c = SQUARES[s["culture"]]
    to_e = np.array(entry, float) - np.array(centre, float)
    to_e = to_e / max(np.hypot(*to_e), 1.0)
    core_r = rings[0]["r_max"]
    mk_near = [round(centre[0] + to_e[0] * core_r * 0.15), round(centre[1] + to_e[1] * core_r * 0.15)]
    feat = tw["central_feature"]
    anchors = []
    if feat != "none":
        anchors.append({"id": "sqr_market", "name": GREEN[s["culture"]] if feat == "green" else sq_m, "type": "road", "near": mk_near})
    if cat in ("town", "city") and feat != "green":
        anchors.append({"id": "sqr_court", "name": sq_c, "type": "road_end", "near": [round(centre[0]), round(centre[1])]})
    plazas = {"enabled": bool(anchors) or cat != "hamlet", "min_area_ft2": min(150000, int(0.3 * s["_derived"]["target_area_ft2"])), "per_area_ft2": 200000 if cat != "hamlet" else 400000,
              "max": {"hamlet": 1, "village": 2, "town": 4, "city": 6}[cat], "radius_ft": [38, 62] if cat != "hamlet" else [30, 48], "min_sep_ft": 260,
              "anchors": anchors, "extra_radius_ft": [30, 42]}
    skip = {"hamlet": ["hall", "court", "tax", "lockup", "stables", "gate"], "village": ["court", "lockup", "tax"], "town": [], "city": []}[cat]
    if feat in ("green",) or cat == "hamlet":
        skip = sorted(set(skip + ["court"]))
    named = {"market_plaza": "sqr_market", "court_plaza": "sqr_court", "skip": skip, "smithy": {"size": [40, 30], "ring_ft": round(rings[min(1, len(rings) - 2)]["r_max"] * 0.6)},
             "mill": {"size": [44, 32], "downstream_ft": round(R * 0.9)}}
    extra = []
    nb = nm["buildings"]
    if feat == "temple":
        cn, _ = CHURCH[s["culture"]]
        extra.append({"id": "bld_church", "name": cn, "size": [58, 34], "floors": 2, "near": "court", "notes": "Church beside the square."})
    if feat == "castle":
        extra.append({"id": "bld_keep", "name": KEEP[s["culture"]], "size": [80, 64], "floors": 3, "notes": "The lord's hold, on the best ground by the square."})
    for x in tw.get("extra_civic", []):
        extra.append({"id": "bld_" + slug(x["name"]), "name": x["name"], "size": x.get("size", [44, 34]), "floors": x.get("floors", 1), "notes": x.get("notes", "")})
    if cat == "city":
        extra += [{"id": "bld_treasury", "name": "Treasury", "size": [40, 34], "floors": 2, "near": "court", "notes": "Strong room for levies."},
                  {"id": "bld_barracks", "name": "Barracks", "size": [58, 34], "floors": 2, "notes": "Quarters of the town watch."}]
    named["extra_civic"] = extra
    ent_name = nm["entry_roads"][int(s["seed"]) % len(nm["entry_roads"])]
    p = {"_note": f"Written by place_create.py for {s['id']} (seed {s['seed']}, layout {tw['layout']}). Feet, y down. Edit and re-run town_gen.py.",
         "place": s["id"], "seed": int(s["seed"]) % 100000, "detail": 1 if draft else 2, "view_preset": "town",
         "naming_set": s["culture"], "area_mode": "auto", "area_ft": None,
         "area_auto": {"seed": int(s["seed"]), "slope_limit": 0.15, "smoothing_ft": 45, "target_area_ft2": s["_derived"]["target_area_ft2"], "centre": [round(centre[0]), round(centre[1])]},
         "output": {"streets": True, "plazas": True, "blocks": False, "buildings": True, "fields": bool(tw["farmland"]), "districts": True},
         "limits": {"max_street_grade": 0.09, "max_main_grade": 0.06, "max_build_slope": 0.19, "max_build_relief_ft": 6.0, "max_field_slope": 0.13, "water_margin_ft": 14,
                    "below_datum_is_water": True, "bank_fill_ft": 24, "field_smooth_cells": 1.0},
         "entry": {"point": [round(entry[0]), round(entry[1])], "via": via, "name": ent_name, "id": "main_road", "width_ft": 28 if cat in ("hamlet", "village") else 30,
                   "bridge_width_ft": 24, "grade_weight": 4.0, "grade_exp": 2.5},
         "ring_spec": {"centre": [round(centre[0]), round(centre[1])], "aspect": asp, "noise": lay["noise"], "noise_period_ft": 320, "feather_ft": 100, "rings": rings, "mode": "terrain"},
         "plazas": plazas, "named": named,
         "streets": {"trace_grade_margin": 0.6, "stub_min_ft": 110, "loop_max_area_ft2": 5000, "loop_compact": 0.3, "split_steep_factor": 1.0, "smooth_sigma_ft": 12, "edge_inset": True,
                     **lay["streets"]},
         "lots": {"min_frontage_ft": 10, "house_fill_w": [0.7, 0.92], "house_fill_d": [0.55, 0.85], "min_house_ft": [14, 12], "shed_detail": 2, "shed_min_area_ft2": 700, "shed_prob": 0.5,
                  "max_house_ft": [46, 38], "backland_ft": 32 if cat != "hamlet" else 0, "edge_fade_ft": 12}}
    if tw["layout"] == "grid":
        p["lots"].update(spread=0.05, angle_jitter_deg=2)
    return p


# ------------------------------------------------------------------ place selection helpers
def choose_centre(h, cell, sea, water_polys, R, hint, W, H):
    """Best flat, dry, central ground: highest fraction of buildable cells within radius R, near the recipe's hint and (a little) near water."""
    from scipy import ndimage as ndi
    hh = ndi.gaussian_filter(h.astype(float), 1.5)
    gy, gx = np.gradient(hh, cell)
    slope = np.hypot(gx, gy)
    ok = (slope < 0.10) & (h > sea + 5)
    dry = ndi.distance_transform_edt(~water_polys) * cell if water_polys is not None and water_polys.any() else np.full(h.shape, 1e4)
    ok &= dry > 30
    k = max(int(R * 0.8 / cell), 3)
    frac = ndi.uniform_filter(ok.astype(float), size=2 * k + 1, mode="constant")
    ny, nx = h.shape
    yy, xx = np.mgrid[0:ny, 0:nx] * cell
    d_hint = np.hypot(xx - hint[0], yy - hint[1]) / max(W, H)
    near_w = np.clip(1.0 - np.abs(dry - 250) / 600.0, 0, 1) * 0.08
    score = 1.5 * frac - 0.5 * d_hint + near_w
    margin = max(R * 0.75, 200)
    score[(xx < margin) | (xx > W - margin) | (yy < margin) | (yy > H - margin)] = -9
    i, j = np.unravel_index(int(np.argmax(score)), score.shape)
    return [float(j * cell), float(i * cell)], float(frac[i, j])


def fit_entry(h, cell, sea, want, W, H, side):
    """Entry point on the map edge nearest `want` whose ground is dry; returns (x, y) and a via list (none)."""
    pts = []
    for t in np.linspace(0.08, 0.92, 33):
        pts += [(t * W, 0), (t * W, H), (0, t * H), (W, t * H)]
    if side and side != "auto":
        keep = {"north": lambda p: p[1] == 0, "south": lambda p: p[1] == H, "west": lambda p: p[0] == 0, "east": lambda p: p[0] == W}[side]
        pts = [p for p in pts if keep(p)]

    def elev(p):
        return float(h[min(int(round(p[1] / cell)), h.shape[0] - 1), min(int(round(p[0] / cell)), h.shape[1] - 1)])
    dry = [p for p in pts if elev(p) > sea + 6] or pts
    best = min(dry, key=lambda p: math.hypot(p[0] - want[0], p[1] - want[1]))
    return best


# ------------------------------------------------------------------ walls
def make_walls(pid, place_dir, spec, gates_n):
    from shapely.geometry import LineString, MultiLineString, Point, Polygon
    from shapely.ops import unary_union
    ds = jload(os.path.join(place_dir, "districts.json"))["districts"]
    ring_kinds = {r["id"]: r["kind"] for r in jload(os.path.join(place_dir, "town_params.json"))["ring_spec"]["rings"]}
    polys = [Polygon(d["geometry"]["points"]).buffer(0) for d in ds if d.get("kind") == "district" and ring_kinds.get(d.get("ring")) not in (None, "farm")]
    if not polys:
        return None
    town = unary_union(polys).buffer(26).buffer(-10).simplify(8)
    if town.geom_type != "Polygon":
        town = max(town.geoms, key=lambda g: g.area)
    wall = LineString(list(town.exterior.coords))
    water = unary_union([Polygon(e["geometry"]["points"]).buffer(0) for e in jload(os.path.join(place_dir, "water.json"))["water"] if e["geometry"].get("type") == "polygon"] or [Polygon()])
    streets = jload(os.path.join(place_dir, "streets.json"))["streets"]
    gates = []
    cand = []
    for e in streets:
        if e["kind"] == "bridge":
            continue
        ln = LineString(e["geometry"]["points"])
        x = ln.intersection(wall)
        pts = [x] if x.geom_type == "Point" else list(x.geoms) if hasattr(x, "geoms") else []
        for p in pts:
            if p.geom_type == "Point" and water.distance(p) > 12:
                cand.append((0 if e["id"].startswith("str_main_road") else -e["geometry"].get("width_ft", 10), e, p))
    cand.sort(key=lambda c: c[0])
    chosen = []
    for _, e, p in cand:
        if all(p.distance(q[1]) > 150 for q in chosen):
            chosen.append((e, p))
        if len(chosen) >= gates_n:
            break
    gt_names = {"scandinavian": "Port", "danish_german": "Tor", "english": "Gate", "fantasy_generic": "Gate"}[spec["culture"]]
    for i, (e, p) in enumerate(chosen):
        gates.append({"id": f"gate_{i + 1}", "name": f"{e['name'].replace(' (bridge)', '')} {gt_names}" if spec["culture"] != "danish_german" else f"{e['name']}tor", "point": [round(p.x, 1), round(p.y, 1)], "street": e["id"],
                      "width_ft": e["geometry"].get("width_ft", 14) + 6})
    # the wall itself: cut at gates (gap = street width + 6) and where it would cross water
    cut = unary_union([Point(g["point"]).buffer(g["width_ft"] / 2 + 2) for g in gates] + ([water.buffer(8)] if not water.is_empty else []))
    parts = wall.difference(cut)
    segs = [parts] if parts.geom_type == "LineString" else list(parts.geoms) if hasattr(parts, "geoms") else []
    segs = [g for g in segs if g.length > 30]
    walls = [{"id": f"wall_{i + 1:02d}", "name": "Town wall" if len(segs) == 1 else f"Town wall (section {i + 1})", "kind": "town_wall", "status": "proposed",
              "geometry": {"type": "polyline", "points": [[round(x, 1), round(y, 1)] for x, y in g.coords], "width_ft": 5}, "height_ft": 16,
              "notes": "Proposed curtain wall round the built-up districts; gaps at the gates. Not exported to the 3D pack."} for i, g in enumerate(segs)]
    jsave(os.path.join(place_dir, "walls.json"), {"place": pid, "walls": walls, "gates": gates})
    return {"sections": len(walls), "gates": [g["name"] for g in gates], "length_ft": round(wall.length)}


# ------------------------------------------------------------------ styles
def assign_styles(place_dir, spec):
    import hashlib as hl
    import building_styles as bs
    have = set(bs.load_presets())
    ss = spec.get("styles")
    table = STYLE_SETS[spec["culture"]] if ss in (None, "auto") else {**STYLE_SETS[spec["culture"]], **ss}
    nm = load_naming(spec["culture"])
    id2key = {v["id"]: k for k, v in nm["buildings"].items()}
    ch_style = CHURCH[spec["culture"]][1]
    n = 0
    bd = os.path.join(place_dir, "buildings")
    for fn in sorted(os.listdir(bd)):
        if not fn.endswith(".json"):
            continue
        p = os.path.join(bd, fn)
        b = jload(p)
        key = id2key.get(b["id"])
        if key:
            st = STYLE_BY_NAMEKEY.get(key)
        elif b["id"] == "bld_church":
            st = ch_style
        elif b["id"] == "bld_keep":
            st = "town_gatehouse"
        else:
            lst = table.get(b.get("kind"), table.get("house"))
            st = lst[int(hl.md5((b["id"] + spec["id"]).encode()).hexdigest()[:6], 16) % len(lst)] if lst else None
        if st and st in have:
            b["style"] = st
            jsave(p, b)
            n += 1
    return n


# ------------------------------------------------------------------ main create
def create(spec_in, out_root=None, force=False, no_town=False, draft=None, dry_run=False, only_terrain=False, keep_spec=None):
    import terrain as T
    import place_terrain as PT
    spec, warns = normalise(spec_in)
    if draft is None:
        draft = bool(spec["limits"].get("draft"))
    problems = check_caps(spec, draft)
    if problems:
        raise SystemExit("place too big for the safe limits:\n  " + "\n  ".join(problems) + "\n  (set limits.allow_large true to override, or use draft quality)")
    pid = spec["id"]
    if out_root and not (no_town or only_terrain or dry_run):
        raise SystemExit("--out-root works with --no-town / --dry-run only (the town generator and renderers read world/<id> from the repository)")
    root = out_root or os.path.join(REPO, "world")
    pdir = os.path.join(root, pid)
    if dry_run:
        return {"ok": True, "dry_run": True, "id": pid, "dir": pdir, "warnings": warns, "derived": spec["_derived"], "size_ft": spec["size_ft"]}
    if os.path.exists(os.path.join(pdir, "place.json")) and not force:
        raise SystemExit(f"world/{pid} already exists (use --force to regenerate it; hand edits there are lost)")
    t0 = time.time()
    nm = load_naming(spec["culture"])
    N = 5 + (0 if no_town else 3)
    W, H = spec["size_ft"]
    seed = int(spec["seed"])
    tcfg = dict(spec["terrain"])
    cell = float(spec.get("cell_ft") or tcfg.get("cell_ft") or 10)
    if draft:
        cell = max(cell, 15.0)
    if (W / cell) * (H / cell) > 900 * 900:
        cell = math.ceil(math.sqrt(W * H / (900 * 900)))
    tcfg["cell_ft"] = cell
    say(1, N, "terrain recipe " + tcfg["recipe"])
    tspec, info = PT.build_terrain_spec(tcfg, W, H, seed)
    h, meta = T.generate(tspec)
    sea = float(meta.get("sea_level_ft", 0.0))
    os.makedirs(pdir, exist_ok=True)
    jsave(os.path.join(pdir, "terrain_spec.json"), tspec)
    T.save(h, meta, os.path.join(pdir, "terrain"))
    say(2, N, "water")
    wents = PT.build_water(tspec, info, h, meta, pid, nm)
    jsave(os.path.join(pdir, "water.json"), {"place": pid, "water": wents})
    # town centre / entry
    from shapely.geometry import Polygon
    from town_gen import raster_poly
    wp = None
    if wents:
        from shapely.ops import unary_union
        wpoly = unary_union([Polygon(e["geometry"]["points"]).buffer(0) for e in wents if e["geometry"].get("type") == "polygon"])
        wp = raster_poly(wpoly, h.shape[1], h.shape[0], cell)
    R = math.sqrt(spec["_derived"]["target_area_ft2"] / math.pi)
    tw = spec["town"]
    if tw["centre"] == "auto":
        centre, frac = choose_centre(h, cell, sea, wp, R, info["hint"]["centre"], W, H)
    else:
        centre, frac = [float(v) for v in tw["centre"]], 1.0
    side = tw["entry_side"] if tw["entry_side"] != "auto" else info["hint"]["entry_side"]
    entry = fit_entry(h, cell, sea, info["hint"]["entry_xy"], W, H, side)
    say(3, N, "place files")
    # place.json, view_settings
    town_fpi = nice_scale(max(2.5 * R * 1.2 / 15.5, 15))
    town_fpi = min(town_fpi, 250)
    bowl_fpi = nice_scale(max(W, H * 1.4) / 15.5)
    place = {"id": pid, "name": spec["name"], "kind": spec["_derived"]["category"], "status": "proposed", "units": "feet", "origin": "top-left, y down",
             "bounds": {"width_ft": W, "height_ft": H}, "population_estimate": spec["town"]["population"],
             "notes": f"DRAFT generated by place_create.py ({tcfg['recipe']} terrain, {tw['layout']} layout, {spec['culture']} names, seed {seed}). Every entity is proposed.",
             "files": {"districts": "districts.json", "streets": "streets.json", "water": "water.json", "buildings": "buildings/", "view_settings": "view_settings.json", "terrain": "terrain/", "params": "town_params.json"},
             "view_focus": {"town": [round(centre[0]), round(centre[1])]}, "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
             "generated_by": "place_create.py", "sea_level_ft": sea, "phase_elevation": "percentile", "culture": spec["culture"],
             "skybox": {"rim_min_deg": 4.0 if tcfg["recipe"] in ("bowl", "valley", "pass", "mountain", "fjord") else 0.0, "far_scale": 1.0 if tcfg["recipe"] in ("bowl", "valley", "pass", "mountain", "fjord", "hills") else 0.35 if tcfg["recipe"] not in ("island", "coastal") else 0.0},
             "defaults": {"shading_preset": "town_winter" if spec["season"] == "winter" else PHASE_BY_CLIMATE[spec["climate"]], "padding_preset": PADDING_BY_RECIPE[tcfg["recipe"]],
                          "foliage_mix": spec.get("foliage", {}).get("mix") or FOLIAGE_BY_CLIMATE[spec["climate"]], "season": spec["season"], "fills_style": "winter" if spec["season"] == "winter" else "full_map",
                          "label_preset": "working"}}
    if spec.get("foundry"):
        place["links"].update(spec["foundry"])
    jsave(os.path.join(pdir, "place.json"), place)
    vs = jload(os.path.join(REPO, "world", "bridgehollow", "view_settings.json")) if os.path.exists(os.path.join(REPO, "world", "bridgehollow", "view_settings.json")) else {}
    vs = {k: v for k, v in vs.items() if k not in ("presets", "_note")}
    vs["_note"] = "Drawing scale and grid for this place (written by place_create.py). Feet are the model unit; only the drawing changes with scale."
    vs["default_preset"] = "town"
    nice = lambda v: nice_scale(v)
    vs["presets"] = {"town": {"scale_ft_per_in": town_fpi, "grid_ft": 100 if town_fpi >= 80 else 50 if town_fpi >= 40 else 20, "grid_major_every": 5, "focus": [round(centre[0]), round(centre[1])], "scale_bar_ft": 5 * town_fpi},
                     "bowl": {"scale_ft_per_in": bowl_fpi, "grid_ft": 100 if bowl_fpi <= 250 else 200, "grid_major_every": 5, "focus": "center", "scale_bar_ft": 5 * bowl_fpi},
                     "street": {"scale_ft_per_in": 20, "grid_ft": 20, "grid_major_every": 5, "focus": "entity", "scale_bar_ft": 100},
                     "room": {"scale_ft_per_in": 5, "grid_ft": 5, "grid_major_every": 5, "focus": "entity", "scale_bar_ft": 25}}
    jsave(os.path.join(pdir, "view_settings.json"), vs)
    jsave(os.path.join(pdir, "place_spec.json"), {k: v for k, v in spec.items() if k != "_derived"})
    for sub in ("streets", "districts"):
        if not os.path.exists(os.path.join(pdir, sub + ".json")):
            jsave(os.path.join(pdir, sub + ".json"), {sub: []})
    os.makedirs(os.path.join(pdir, "buildings"), exist_ok=True)
    params = build_params(spec, centre, entry, [], nm, draft)
    jsave(os.path.join(pdir, "town_params.json"), params)
    report = {"id": pid, "name": spec["name"], "seed": seed, "size_ft": [W, H], "cell_ft": cell, "draft": draft, "centre": [round(c) for c in centre], "centre_buildable_fraction": round(frac, 2),
              "entry": [round(entry[0]), round(entry[1])], "terrain": {"recipe": tcfg["recipe"], "elev_min": round(float(h.min()), 1), "elev_max": round(float(h.max()), 1), "sea": info["sea"]},
              "water": [e["kind"] for e in wents], "warnings": list(warns), "category": spec["_derived"]["category"]}
    if not no_town and not only_terrain:
        say(4, N, "town (streets, lots, buildings)")
        import town_gen
        g = town_gen.generate(os.path.join(pdir, "town_params.json"), {}, verbose=False, place_dir=pdir)
        g.write()
        tr = jload(os.path.join(pdir, "town_gen_report.json"))
        report["town"] = {"counts": tr["counts"], "warnings": tr.get("warnings", [])[:8], "issues": tr.get("issues", [])[:8]}
        say(5, N, "styles and walls")
        report["styled_buildings"] = assign_styles(pdir, spec)
        if tw["wall"]:
            report["wall"] = make_walls(pid, pdir, spec, int(tw["gates"]))
        say(6, N, "done")
    report["seconds"] = round(time.time() - t0, 1)
    jsave(os.path.join(pdir, "create_report.json"), report)
    return {"ok": True, "id": pid, "dir": pdir, "report": report}


# ------------------------------------------------------------------ prompt help, templates
def templates():
    out = {}
    if os.path.isdir(PLACE_PRESETS):
        for fn in sorted(os.listdir(PLACE_PRESETS)):
            if fn.endswith(".json"):
                out[fn[:-5]] = jload(os.path.join(PLACE_PRESETS, fn))
    return out


def prompt_help():
    lines = ["PLACE SPEC (place_create.py) - write one JSON object that follows this schema; omit anything you do not need.", ""]
    lines.append("Vocabulary")
    lines.append("  terrain.recipe : flat | rolling | hills | valley | bowl | coastal | island | pass | fjord | mountain")
    lines.append("  terrain.sea_side: north | south | east | west (coastal, fjord)   terrain.rivers 0-3   terrain.lakes 0-4   terrain.river_meander straight|gentle|lazy")
    lines.append("  terrain.relief_ft: ridge/hill height (defaults: " + ", ".join(f"{k} {v}" for k, v in __import__("place_terrain").RELIEF.items()) + ")")
    lines.append("  culture        : " + " | ".join(CULTURES) + "   (street, building and district names; default building styles)")
    lines.append("  town.layout    : " + " | ".join(LAYOUTS) + "   town.central_feature: " + " | ".join(FEATURES))
    lines.append("  town.population: 20..12000 (hamlet <150, village <450, town <2500, city)   town.wall true/false   town.gates 1-6   town.entry_side auto|north|south|east|west")
    lines.append("  town.districts : 'auto' or [{\"name\": \"Harbour Ward\", \"kind\": \"civic\"|\"residential\"}, ...] centre outward (1-4); a farmland ring follows")
    lines.append("  climate        : " + " | ".join(CLIMATES) + "   season: " + " | ".join(SEASONS))
    lines.append("  styles         : 'auto' or {\"house\": [\"danish_fachwerk\"], \"civic\": [\"hanseatic_brick\"], ...} (ids in illustrator/presets/building_styles)")
    lines.append("  limits         : max_buildings 1200, max_area_ft2 3M, draft (civic buildings only, fast), allow_large (lift caps)")
    lines.append("")
    lines.append("How to answer a plain-words request: pick the nearest template below, change the fields the user named, choose a culture that matches the wording")
    lines.append("(Norse/Viking -> scandinavian, Hanse/Danish/German -> danish_german, English/Tudor -> english, anything else -> fantasy_generic), and keep the rest at defaults.")
    lines.append("Run `place_create.py validate spec.json` then `place_create.py create spec.json` (or the panel's Places tab).")
    lines.append("")
    lines.append("SCHEMA (JSON Schema):")
    lines.append(json.dumps(SPEC_SCHEMA, indent=1))
    lines.append("")
    lines.append("TEMPLATES (presets/places/*.json):")
    for k, v in templates().items():
        lines.append(f"--- {k}")
        lines.append(json.dumps(v))
    return "\n".join(lines)


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("create")
    c.add_argument("spec")
    c.add_argument("--id")
    c.add_argument("--seed", type=int)
    c.add_argument("--draft", action="store_true", help="draft quality: coarse terrain, civic buildings only (fast)")
    c.add_argument("--force", action="store_true")
    c.add_argument("--no-town", action="store_true", help="terrain and water only")
    c.add_argument("--dry-run", action="store_true", help="validate, apply caps, print the plan; write nothing")
    c.add_argument("--out-root", help="world root (default <repo>/world)")
    v = sp.add_parser("validate")
    v.add_argument("spec")
    sp.add_parser("prompt-help")
    sp.add_parser("write-schema")
    ft = sp.add_parser("from-text")
    ft.add_argument("text")
    ft.add_argument("--out")
    ft.add_argument("--create", action="store_true")
    ft.add_argument("--draft", action="store_true")
    ft.add_argument("--force", action="store_true")
    tp = sp.add_parser("templates")
    tp.add_argument("--show")
    rg = sp.add_parser("regen")
    rg.add_argument("--place", required=True)
    rg.add_argument("--terrain", action="store_true")
    rg.add_argument("--no-town", action="store_true")
    rg.add_argument("--meander", choices=["straight", "gentle", "lazy"])
    rg.add_argument("--meander-amplitude", type=float)
    rg.add_argument("--meander-wavelength", type=float)
    rg.add_argument("--meander-seed", type=int)
    rg.add_argument("--width-var", type=float)
    rg.add_argument("--no-bars", action="store_true")
    rg.add_argument("--seed", type=int)
    rg.add_argument("--draft", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "prompt-help":
        print(prompt_help())
        return 0
    if a.cmd == "write-schema":
        jsave(SCHEMA_PATH, SPEC_SCHEMA)
        print("wrote", SCHEMA_PATH)
        return 0
    if a.cmd == "templates":
        t = templates()
        if a.show:
            print(json.dumps(t[a.show], indent=1))
        else:
            for k, v in t.items():
                print(f"{k:24s} {v.get('_note', '')[:100]}")
        return 0
    if a.cmd == "validate":
        spec = jload(a.spec)
        errs, warns = validate(spec)
        for w in warns:
            print("warning:", w)
        for e in errs:
            print("error:", e)
        res = {"ok": not errs, "errors": errs, "warnings": warns}
        if not errs:
            s, _ = normalise(spec)
            res.update(id=s["id"], name=s["name"], size_ft=s["size_ft"], derived=s["_derived"], caps=check_caps(s, bool(s["limits"].get("draft"))))
            res["ok"] = not res["caps"]
        print(json.dumps(res))
        return 0 if res["ok"] else 2
    if a.cmd == "from-text":
        import place_text
        spec, notes = place_text.parse(a.text)
        for n in notes:
            print("note:", n)
        if a.out:
            jsave(a.out, spec)
            print("wrote", a.out)
        else:
            print(json.dumps(spec, indent=1))
        if a.create:
            r = create(spec, force=a.force, draft=a.draft or None)
            print(json.dumps(r))
        return 0
    if a.cmd == "create":
        spec = jload(a.spec)
        if a.id:
            spec["id"] = a.id
        if a.seed is not None:
            spec["seed"] = a.seed
        r = create(spec, out_root=a.out_root, force=a.force, no_town=a.no_town, draft=a.draft or None, dry_run=a.dry_run)
        print(json.dumps(r))
        return 0
    if a.cmd == "regen":
        pdir = os.path.join(REPO, "world", a.place)
        sp_ = os.path.join(pdir, "place_spec.json")
        if not os.path.exists(sp_):
            raise SystemExit(f"world/{a.place}/place_spec.json missing: only places made by place_create.py can be regenerated here")
        spec = jload(sp_)
        if a.meander:
            spec["terrain"]["river_meander"] = a.meander
        mp = dict(spec["terrain"].get("river_meander_params") or {})
        for key, val in (("amplitude_ft", a.meander_amplitude), ("wavelength_ft", a.meander_wavelength), ("seed", a.meander_seed), ("width_var", a.width_var)):
            if val is not None:
                mp[key] = val
        if a.no_bars:
            mp["bars"] = False
        if mp:
            spec["terrain"]["river_meander_params"] = mp
        if a.seed is not None:
            spec["seed"] = a.seed
        r = create(spec, force=True, no_town=a.no_town, draft=a.draft or None)
        print(json.dumps(r))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
