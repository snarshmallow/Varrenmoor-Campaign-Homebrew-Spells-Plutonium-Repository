"""Procedurally generate the DRAFT town of Bridgehollow model (fixed seed, reproducible).

Everything is status "proposed": there is no canon layout. Run:  python world/gen_bridgehollow.py
Coordinates are feet, origin top-left, y down.
"""
import json
import math
import os
import random

SEED = 1103
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridgehollow")
W, H = 2400, 1500
rnd = random.Random(SEED)

ST = 24          # ordinary street width
PIL = 30         # Pilgrim Road width
BRIDGE_Y = 700
EW = [400, 500, 600, 700, 800, 900, 1000]            # east-west street y (700 = Pilgrim Road)
WEST_X = [760, 860, 960, 1060]
EAST_X = [1350, 1450, 1550, 1650]


def river_cx(y):
    return 1200 + 60 * math.sin(y / 230.0)


def river_w(y):
    return 60 + 8 * math.sin(y / 130.0)


def r1(v):
    return round(v, 1)


def rect(x, y, w, d):
    return [[r1(x), r1(y)], [r1(x + w), r1(y)], [r1(x + w), r1(y + d)], [r1(x), r1(y + d)]]


def links():
    return {"foundry_scene": None, "model3d": None, "ai_layer": None}


def ent(id_, name, kind, geometry, notes="", **extra):
    e = {"id": id_, "name": name, "kind": kind, "status": "proposed", "geometry": geometry,
         "notes": notes, "links": links()}
    e.update(extra)
    return e


def save(rel, data):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")


def poly(points):
    return {"type": "polygon", "points": points}


def line(points, width):
    return {"type": "polyline", "points": points, "width_ft": width}


# ---------------------------------------------------------------- water
cl = [[r1(river_cx(y)), y] for y in range(-50, 1551, 50)]
left = [[r1(river_cx(y) - river_w(y) / 2), y] for y in range(-50, 1551, 50)]
right = [[r1(river_cx(y) + river_w(y) / 2), y] for y in range(-50, 1551, 50)]
water = [ent("wat_river", "The river (name not canon)", "river",
             poly(left + right[::-1]), "Flows north to south through the hollow. Width varies 52-68 ft.",
             centerline=cl)]
save("water.json", {"place": "bridgehollow", "water": water})

# ---------------------------------------------------------------- streets
streets = []
bw = river_w(BRIDGE_Y)
xl = river_cx(BRIDGE_Y) - bw / 2 - 14
xr = river_cx(BRIDGE_Y) + bw / 2 + 14
west_pts = [[0, 590], [250, 600], [520, 660], [700, BRIDGE_Y], [r1(xl), BRIDGE_Y]]
east_pts = [[r1(xr), BRIDGE_Y], [1700, BRIDGE_Y], [1950, 720], [2200, 800], [2400, 830]]
streets.append(ent("str_pilgrim_road_west", "Pilgrim Road (west approach)", "road", line(west_pts, PIL),
                   "Enters the hollow from the west; gate watch post stands on it."))
streets.append(ent("str_pilgrim_bridge", "Pilgrim Bridge", "bridge", line([[r1(xl), BRIDGE_Y], [r1(xr), BRIDGE_Y]], 26),
                   "The one main stone bridge over the river.", material="stone"))
streets.append(ent("str_pilgrim_road_east", "Pilgrim Road (east)", "road", line(east_pts, PIL),
                   "Continues east past the market square."))
names_ew = {400: "North Row", 500: "Ledger Street", 600: "Warden Street", 800: "Cartwright Street",
            900: "Tanners Row", 1000: "South Row"}
for bank, xs, tag in (("west", WEST_X, "w"), ("east", EAST_X, "e")):
    for y in EW:
        if y == BRIDGE_Y:
            continue
        streets.append(ent(f"str_ew_{y}_{tag}", f"{names_ew[y]} ({bank})", "street",
                           line([[xs[0], y], [xs[-1], y]], ST), "Orderly grid street."))
    for i, x in enumerate(xs):
        streets.append(ent(f"str_ns_{tag}{i}", f"{bank.title()} Lane {i + 1}", "street",
                           line([[x, EW[0]], [x, EW[-1]]], ST), "Orderly grid street."))
save("streets.json", {"place": "bridgehollow", "streets": streets})

# ---------------------------------------------------------------- buildings
buildings = []
reserved = set()


def blk_origin(bank, col, row):
    xs = WEST_X if bank == "w" else EAST_X
    return xs[col] + 15, EW[row] + 15


def add(id_, name, kind, pts, notes="", floors=1):
    buildings.append(ent(id_, name, kind, poly(pts), notes, floors=floors, rooms=[], doors=[]))


def civic(bank, col, row, id_, name, kind, w, d, dx=0, dy=0, notes=""):
    ox, oy = blk_origin(bank, col, row)
    reserved.add((bank, col, row))
    add(id_, name, kind, rect(ox + (70 - w) / 2 + dx, oy + (70 - d) / 2 + dy, w, d), notes, floors=2 if w * d > 2000 else 1)


civic("w", 2, 2, "bld_warden_hall", "Warden's Hall", "civic", 60, 50, notes="Seat of the wardens; beside the bridge. Layout proposed.")
civic("w", 2, 1, "bld_lockup", "Lockup", "civic", 36, 30, notes="Cells; kept near the warden's hall.")
civic("e", 0, 2, "bld_tax_office", "Tax and Permit Office", "civic", 50, 40, notes="Tolls, permits and levies, first stop east of the bridge.")
civic("e", 1, 2, "bld_magistrate_court", "Magistrate's Court", "civic", 62, 48)
civic("w", 0, 3, "bld_smithy", "Smithy", "craft", 40, 30)
civic("e", 1, 4, "bld_meeting_hall", "Meeting Hall", "civic", 60, 44, notes="Plain hall for town meetings; no religious use.")
reserved.add(("w", 1, 3))
ox, oy = blk_origin("w", 1, 3)
add("bld_inn", "Inn", "inn", rect(ox + 4, oy + 3, 62, 34), "Inn on Pilgrim Road near the bridge.", floors=2)
add("bld_stables", "Stables", "stable", rect(ox + 8, oy + 41, 54, 24), "Stables behind the inn.")
for b in ((("e", 0, 3)), ("e", 1, 3)):
    reserved.add(b)

# gate watch post on the west approach
add("bld_gate_watch", "Gate Watch Post", "civic", rect(590, 632, 26, 24), "Checks travelers entering on Pilgrim Road.")

# mill on the east bank, south of town
my = 1085
mx = river_cx(my + 16) + river_w(my + 16) / 2 + 12
add("bld_mill", "Mill", "craft", rect(mx, my, 44, 32), "Water mill on the east bank.", floors=2)

# houses
n = 0


def house(x, y, w, d):
    global n
    n += 1
    add(f"bld_house_{n:03d}", f"House {n}", "house", rect(x, y, w, d), floors=rnd.choice([1, 1, 1, 2]))


for bank in ("w", "e"):
    for col in range(3):
        for row in range(6):
            if (bank, col, row) in reserved:
                continue
            ox, oy = blk_origin(bank, col, row)
            for lx in (0, 35):
                for ly in (0, 35):
                    if rnd.random() > 0.95:
                        continue
                    w, d = rnd.randint(20, 29), rnd.randint(20, 28)
                    x = ox + lx + rnd.uniform(2, 33 - w + 2) if 33 - w + 2 > 2 else ox + lx + 2
                    y = oy + ly + rnd.uniform(2, 33 - d + 2) if 33 - d + 2 > 2 else oy + ly + 2
                    house(x, y, w, d)


def road_y(pts, x):
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1 and x1 > x0:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


for x, side in ((300, -1), (380, 1), (460, -1)):
    y = road_y(west_pts, x)
    house(x, y + (side * 40) - (28 if side < 0 else 0), 26, 24)
for x, side in ((1800, 1), (1960, -1), (2100, 1)):
    y = road_y(east_pts, x)
    house(x, y + (side * 40) - (26 if side < 0 else 0), 26, 24)

for b in buildings:
    save(f"buildings/{b['id']}.json", b)

# ---------------------------------------------------------------- districts
districts = [
    ent("dis_west_bank", "West Bank (Wardens' Ward)", "district", poly(rect(740, 380, 340, 640)),
        "Warden's hall, lockup, inn, smithy and homes."),
    ent("dis_east_bank", "East Bank (Market Ward)", "district", poly(rect(1330, 380, 340, 640)),
        "Tax office, court, market square, meeting hall and homes."),
    ent("dis_mill_reach", "Mill Reach", "district", poly(rect(1100, 1060, 220, 120)), "River frontage south of the town."),
    ent("sqr_market", "Market Square", "square", poly(rect(1365, 715, 170, 70)), "Open market, south of Pilgrim Road, east of the bridge."),
]
save("districts.json", {"place": "bridgehollow", "districts": districts})

# ---------------------------------------------------------------- place
place = {
    "id": "bridgehollow", "name": "Bridgehollow (draft)", "kind": "town", "status": "proposed",
    "units": "feet", "origin": "top-left, y down",
    "bounds": {"width_ft": W, "height_ft": H},
    "population_estimate": 600,
    "notes": "DRAFT layout generated by world/gen_bridgehollow.py, seed %d. No canon layout exists; every entity is proposed." % SEED,
    "scales": {
        "town": {"feet_per_inch": 100, "page_in": [17, 11]},
        "street": {"feet_per_inch": 20, "page_in": [17, 11]},
        "building": {"feet_per_inch": 5, "page_in": [17, 11]},
    },
    "files": {"districts": "districts.json", "streets": "streets.json", "water": "water.json", "buildings": "buildings/"},
    "view_focus": {"town": [1200, 750]},
    "links": links(),
}
save("place.json", place)
print("buildings:", len(buildings), "houses:", n)
