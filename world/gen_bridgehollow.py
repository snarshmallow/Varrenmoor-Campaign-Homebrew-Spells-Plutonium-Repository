"""Regenerate the DRAFT Bridgehollow world model (all entities `proposed`; no canon layout exists).

  python world/gen_bridgehollow.py [--seed N] [--detail 1|2|3]

1. writes water.json (the river; the stand-in until illustrator/generators/water.py supplies hydrology),
2. writes place.json (bounds, sea level, links),
3. runs illustrator/generators/town_gen.py with world/bridgehollow/town_params.json, which writes streets.json,
   districts.json, buildings/*.json, town_gen_report.json (deterministic by seed).
Terrain comes from world/bridgehollow/terrain_spec.json (illustrator/generators/terrain.py); scale/grid from
view_settings.json. Coordinates are feet, origin top-left, y down. The old boxy grid layout was replaced by this.
"""
import argparse
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "illustrator", "generators"))
OUT = os.path.join(HERE, "bridgehollow")
W, H = 2400, 1500


def river_cx(y):
    return 1200 + 60 * math.sin(y / 230.0)


def river_w(y):
    return 60 + 8 * math.sin(y / 130.0)


def r1(v):
    return round(v, 1)


def save(rel, data):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")


def links():
    return {"foundry_scene": None, "model3d": None, "ai_layer": None}


def write_water():
    ys = range(-50, 1551, 50)
    cl = [[r1(river_cx(y)), y] for y in ys]
    left = [[r1(river_cx(y) - river_w(y) / 2), y] for y in ys]
    right = [[r1(river_cx(y) + river_w(y) / 2), y] for y in ys]
    river = {"id": "wat_river", "name": "The river (name not canon)", "kind": "river", "status": "proposed",
             "geometry": {"type": "polygon", "points": left + right[::-1]},
             "notes": "Flows north to south through the hollow and out by the southern pass. Width 52-68 ft.",
             "links": links(), "centerline": cl, "width_ft": 60, "depth_ft": 6, "flow": "south"}
    save("water.json", {"place": "bridgehollow", "water": [river]})


def write_place():
    pp = os.path.join(OUT, "place.json")
    place = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {}
    place.update({"id": "bridgehollow", "name": "Bridgehollow (draft)", "kind": "town", "status": "proposed",
                  "units": "feet", "origin": "top-left, y down", "bounds": {"width_ft": W, "height_ft": H},
                  "sea_level_ft": 0.0, "population_estimate": 600,
                  "view_focus": {"town": [1200, 750]}, "links": links()})
    place.pop("scales", None)          # scale presets now live in view_settings.json
    save("place.json", place)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--detail", type=int)
    a = ap.parse_args()
    write_water()
    write_place()
    import town_gen
    g = town_gen.generate(os.path.join(OUT, "town_params.json"), {"seed": a.seed, "detail": a.detail})
    g.write()
