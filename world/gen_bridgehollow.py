"""Regenerate the DRAFT Bridgehollow world model (all entities `proposed`; no canon layout exists).

  python world/gen_bridgehollow.py [--seed N] [--detail 1|2|3] [--terrain] [--no-town]
         [--meander straight|gentle|lazy] [--meander-amplitude FT] [--meander-wavelength FT] [--meander-seed N] [--width-var F] [--no-bars]

1. writes water.json (the river: the meandered centreline of terrain_spec.json valleys[river], see river_meander.py),
2. writes place.json (bounds, sea level, links),
3. runs illustrator/generators/town_gen.py with world/bridgehollow/town_params.json, which writes streets.json,
   districts.json, buildings/*.json, town_gen_report.json (deterministic by seed).
Terrain comes from world/bridgehollow/terrain_spec.json (illustrator/generators/terrain.py); scale/grid from
view_settings.json. Coordinates are feet, origin top-left, y down. The old boxy grid layout was replaced by this.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "illustrator", "generators"))
OUT = os.path.join(HERE, "bridgehollow")
W, H = 2400, 1500


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


def river_valley(spec):
    return next(v for v in spec["valleys"] if v.get("river"))


def write_water(spec):
    """water.json river = the same meandered centreline the terrain valley is carved along (river_meander.py)."""
    import river_meander as rm
    v = river_valley(spec)
    g = rm.river_geometry(v)
    cl = g["centerline"]
    sinu, length = rm.sinuosity(cl)
    wmean = sum(g["widths"]) / len(g["widths"])
    m = g["params"]
    river = {"id": "wat_river", "name": "The river (name not canon)", "kind": "river", "status": "proposed",
             "geometry": {"type": "polygon", "points": g["outline"]},
             "notes": "Flows north to south through the hollow and out by the southern pass. Gentle meander (preset %s, amplitude %g ft, "
                      "wavelength %g ft); %d-%d ft wide: narrow in the gorge, wider and slower on the floor."
                      % (m["preset"], m["amplitude_ft"], m["wavelength_ft"], min(g["widths"]), max(g["widths"])),
             "links": links(), "centerline": cl, "widths_ft": g["widths"], "width_ft": r1(wmean), "depth_ft": 6, "flow": "south",
             "length_ft": r1(length), "sinuosity": round(sinu, 3),
             "meander": {k: m[k] for k in ("preset", "amplitude_ft", "wavelength_ft", "seed", "width_var")}}
    if g["bars"]:
        river["bars"] = g["bars"]
    save("water.json", {"place": "bridgehollow", "water": [river]})
    return river


def regen_terrain(spec):
    import terrain
    h, meta = terrain.generate(spec, verbose=True)
    terrain.save(h, meta, os.path.join(OUT, "terrain"))
    return h, meta


def write_place():
    pp = os.path.join(OUT, "place.json")
    place = json.load(open(pp, encoding="utf-8")) if os.path.exists(pp) else {}
    place.update({"id": "bridgehollow", "name": "Bridgehollow (draft)", "kind": "town", "status": "proposed",
                  "units": "feet", "origin": "top-left, y down", "bounds": {"width_ft": W, "height_ft": H},
                  "sea_level_ft": 0.0, "population_estimate": 600,
                  "view_focus": {"town": [1200, 750]}, "links": links()})
    place.pop("scales", None)          # scale presets now live in view_settings.json
    save("place.json", place)


def apply_meander_args(spec, a):
    """CLI / panel overrides go into the spec's river valley `meander` block (the single source of truth) and are saved."""
    v = river_valley(spec)
    m = v.setdefault("meander", {})
    for key, val in (("preset", a.meander), ("amplitude_ft", a.meander_amplitude), ("wavelength_ft", a.meander_wavelength),
                     ("seed", a.meander_seed), ("width_var", a.width_var)):
        if val is not None:
            m[key] = val
    if a.meander and a.meander_amplitude is None:
        m.pop("amplitude_ft", None)       # a preset name alone takes the preset's numbers
    if a.meander and a.meander_wavelength is None:
        m.pop("wavelength_ft", None)
    if a.meander and a.width_var is None:
        m.pop("width_var", None)
    if a.no_bars:
        m["bars"] = False
    return spec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int)
    ap.add_argument("--detail", type=int)
    ap.add_argument("--meander", choices=["straight", "gentle", "lazy"], help="river meander preset (terrain_spec.json valleys[river].meander)")
    ap.add_argument("--meander-amplitude", type=float, help="peak lateral offset of the bends, ft")
    ap.add_argument("--meander-wavelength", type=float, help="bend wavelength, ft")
    ap.add_argument("--meander-seed", type=int)
    ap.add_argument("--width-var", type=float, help="pool/riffle width variation, fraction")
    ap.add_argument("--no-bars", action="store_true", help="no point-bar hints")
    ap.add_argument("--terrain", action="store_true", help="regenerate the heightmap from terrain_spec.json (needed after any meander change)")
    ap.add_argument("--no-town", action="store_true", help="stop after terrain + water")
    a = ap.parse_args()
    spec_path = os.path.join(OUT, "terrain_spec.json")
    spec = json.load(open(spec_path, encoding="utf-8"))
    touched = any(x is not None and x is not False for x in (a.meander, a.meander_amplitude, a.meander_wavelength, a.meander_seed, a.width_var, a.no_bars))
    if touched:
        spec = apply_meander_args(spec, a)
        with open(spec_path, "w", encoding="utf-8") as f:
            json.dump(spec, f, indent=1)
            f.write("\n")
    if a.terrain or touched:
        regen_terrain(spec)
    write_water(spec)
    write_place()
    if not a.no_town:
        import town_gen
        g = town_gen.generate(os.path.join(OUT, "town_params.json"), {"seed": a.seed, "detail": a.detail})
        g.write()
