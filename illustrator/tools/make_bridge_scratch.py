"""Regenerate the bridge test place `world/zz_bridge_scratch` (8 east-west lanes across one straight N-S channel) from a lane table, so the Foundry
comparison of the bridge styles can be repeated. The place itself (800 x 800 ft, 4 ft heightmap cells) must already exist (place_create.py); this
rewrites its terrain heightmap, water.json (centerline + widths_ft matching the heightmap channel) and the per-lane street elevations (deck hump),
and drops the old bridges.json. Then:

  python illustrator/tools/make_bridge_scratch.py
  python illustrator/generators/worldpack.py export --place zz_bridge_scratch
  for each lane:  python illustrator/generators/bridge_maker.py apply --place zz_bridge_scratch --only brg_str_zzN_1 --preset P [--set k=v] --no-export
  python illustrator/generators/bridge_maker.py inject --place zz_bridge_scratch        (see out/bridges_notes.md for split / merge / push)

Lane table: (street id suffix, preset, params, water width ft, hump ft). The two arch lanes and the two covered-timber lanes share one crossing size so the
styles can be compared side by side. No place-specific logic lives in the bridge generators; this file is only test data.
"""
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
PLACE = os.path.join(REPO, "world", "zz_bridge_scratch")
CX = 380.0                                           # channel centre line x (ft)
CELL = 4.0
N = 201
LANES = [  # (n, y_ft, preset, params, water_ft, hump_ft)
    (1, 60, "rough_log", {}, 40, 2.0),
    (2, 155, "flat_cut_stone", {}, 12, 0.0),
    (3, 250, "stone_arch", {}, 36, 7.0),
    (4, 345, "brick_arch", {}, 36, 7.0),
    (5, 440, "covered_timber", {}, 52, 3.0),
    (6, 535, "covered_timber", {"support": "piers", "roof": "tile"}, 52, 3.0),
    (7, 630, "rope_plank", {}, 44, 2.0),
    (8, 725, "wooden_truss", {}, 48, 3.0),
]
DEPTH = 10.0                                         # bed below the banks (ft)
SLOPE_RUN = 12.0                                     # horizontal run of the bank slope (ft)


def bank_z(y):
    return 518.8 - 0.02 * (y - 60.0)


def water_width(y):
    """Channel (surface) width along y: a plateau of +-35 ft around each lane, linear in between."""
    ys = []
    ws = []
    for _, yl, _, _, wd, _ in LANES:
        ys += [yl - 35.0, yl + 35.0]
        ws += [wd, wd]
    return float(np.interp(y, [min(ys[0], 0.0)] + ys + [max(ys[-1], 800.0)], [ws[0]] + ws + [ws[-1]]))


def main():
    sys.path.insert(0, os.path.join(REPO, "illustrator", "generators"))
    ys = np.arange(N) * CELL
    xs = np.arange(N) * CELL
    h = np.zeros((N, N), np.float32)
    for i, y in enumerate(ys):
        wd = water_width(y)
        bed_half = max(wd / 2 - 6.0, 2.0)
        top_half = bed_half + SLOPE_RUN
        dep = DEPTH * np.clip((top_half - np.abs(xs - CX)) / SLOPE_RUN, 0.0, 1.0)
        h[i] = bank_z(y) - dep
    np.save(os.path.join(PLACE, "terrain", "heightmap.npy"), h)
    meta_p = os.path.join(PLACE, "terrain", "terrain_meta.json")
    meta = json.load(open(meta_p, encoding="utf-8"))
    meta.update(elev_min=round(float(h.min()), 1), elev_max=round(float(h.max()), 1), relief_ft=round(float(h.max() - h.min()), 1))
    json.dump(meta, open(meta_p, "w", encoding="utf-8"), indent=1)
    # water: centreline + widths, polygon = centreline +- width/2
    wp_ = os.path.join(PLACE, "water.json")
    wd_ = json.load(open(wp_, encoding="utf-8"))
    w = wd_["water"][0]
    ws = [round(water_width(y), 2) for y in ys]
    w["centerline"] = [[CX, float(y)] for y in ys]
    w["widths_ft"] = ws
    left = [[round(CX - wv / 2, 2), float(y)] for y, wv in zip(ys, ws)]
    right = [[round(CX + wv / 2, 2), float(y)] for y, wv in zip(ys, ws)]
    w["geometry"] = {"type": "polygon", "points": left + right[::-1]}
    w["width_ft"] = round(float(np.mean(ws)), 2)
    w.pop("bed_elevations_ft", None)
    json.dump(wd_, open(wp_, "w", encoding="utf-8"), indent=1)
    # streets: constant bank level per lane + a cosine hump over the channel
    sp = os.path.join(PLACE, "streets.json")
    sd = json.load(open(sp, encoding="utf-8"))
    for st in sd["streets"]:
        n = int(st["id"][-1])
        lane = [l for l in LANES if l[0] == n][0]
        _, yl, preset, params, wdt, hump = lane
        st["name"] = f"Test lane {preset}" + (" " + params["support"] if params.get("support") else "")
        z = []
        for x, y in st["geometry"]["points"]:
            d = abs(x - CX) / 38.0
            z.append(round(bank_z(yl) + (hump * 0.5 * (1 + math.cos(math.pi * d)) if d < 1 else 0.0), 2))
        st["elevations_ft"] = z
        st["elevation_ft"] = round(float(np.mean(z)), 2)
    json.dump(sd, open(sp, "w", encoding="utf-8"), indent=1)
    bp = os.path.join(PLACE, "bridges.json")
    if os.path.exists(bp):
        os.remove(bp)
    print(json.dumps({"ok": True, "lanes": [(l[0], l[2], l[3], l[4], l[5]) for l in LANES], "elev": [meta["elev_min"], meta["elev_max"]]}))


if __name__ == "__main__":
    main()
