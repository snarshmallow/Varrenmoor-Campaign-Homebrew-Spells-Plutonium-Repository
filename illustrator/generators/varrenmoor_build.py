#!/usr/bin/env python3
"""Build world/varrenmoor/ from the campaign map (Foundry scene "Map", assets/map v2.png, 1448 x 1086 px).

Everything is placed from digitised MAP PIXELS with one calibration (the map's own scale bar: 0..1000 ft = 130 px, so 7.69 ft per px) and one offset
(window origin = map pixel (0, 160)), so the feet <-> pixel transform is exact and can be inverted for the overlay / error measurement
(`overlay` and `measure`).  Terrain and the river come from the plugin's terrain generator (terrain.py / place_terrain.py) driven by a terrain spec derived
from the map; streets, buildings, districts and fields are hand-placed from the map; styles, interiors, export, split, merge and push are the normal pipeline.
No paved roads exist in Varrenmoor: every street carries edit {surface: dirt, kerb: false} and the place uses the town style `varrenmoor`
(dirt roads, grass plazas).

  python illustrator/generators/varrenmoor_build.py build [--no-terrain]
  python illustrator/generators/varrenmoor_build.py overlay      # -> illustrator/out/foundry_screens/varrenmoor_map_vs_model.png
  python illustrator/generators/varrenmoor_build.py measure      # placement error report -> illustrator/out/varrenmoor_error.json
"""
import argparse
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
PID = "varrenmoor"
PDIR = os.path.join(REPO, "world", PID)
MAP_PNG = os.path.join(REPO, "illustrator", "out", "foundry_screens", "varrenmoor_original_map.png")

S = 7.69                     # ft per map pixel (map scale bar: 0 ... 1000 ft spans 130 px)
X0, Y0 = 0.0, 160.0          # map pixel at the top-left corner of the model window
W_FT, H_FT = 8460.0, 6150.0  # model window = map px x 0..1100, y 160..960


def ft(px, py):
    return [round((px - X0) * S, 1), round((py - Y0) * S, 1)]


def px_of(x, y):
    return x / S + X0, y / S + Y0


# ---------------------------------------------------------------- digitised from the map (pixels)
RIVER = [(430, 20), (380, 60), (350, 110), (310, 175), (255, 220), (205, 265), (178, 320), (182, 370), (185, 405), (150, 440), (85, 490), (35, 535), (8, 590), (-30, 650)]
PILGRIM = [(-20, 390), (60, 398), (110, 410), (150, 432), (180, 455), (220, 473), (263, 490), (290, 503), (347, 512), (367, 530), (377, 550), (393, 570), (433, 583),
           (463, 587), (497, 603), (533, 622), (580, 632), (620, 653), (660, 675), (700, 700), (715, 740), (740, 775), (790, 800), (830, 822), (860, 870), (880, 935), (885, 965)]
OAK = (492, 500)
CHURCH = (700, 335)


def circle(c, r, n=28, a0=0.0, close=False):
    pts = [(c[0] + r * math.cos(a0 + 2 * math.pi * i / n), c[1] + r * math.sin(a0 + 2 * math.pi * i / n)) for i in range(n)]
    return pts + [pts[0]] if close else pts


# (id, name, class, width_ft, points px).  class is the exporter's road class (road/street/lane/alley)
ROADS = [
    ("str_pilgrim_road", "Pilgrim's Road", "road", 20, PILGRIM),
    ("str_oak_ring", "Hollow Oak ring", "lane", 11, circle(OAK, 42, 30, 0.9, True)),
    ("str_oak_link", "Oak lane", "lane", 11, [(470, 541), (462, 562), (448, 584)]),
    ("str_hollow_east", "East Hollow lane", "lane", 10, [(533, 622), (535, 598), (528, 575), (535, 545), (530, 515), (534, 468)]),
    ("str_church_path", "Churchyard path", "lane", 10, [(497, 603), (540, 560), (560, 500), (555, 440), (565, 380), (575, 345), (610, 322), (645, 312)]),
    ("str_church_ring", "Churchyard lane", "alley", 8, circle(CHURCH, 62, 30, 0.2, True)),
    ("str_stables_path", "Stables path", "alley", 8, [(642, 300), (590, 290), (545, 280), (522, 285)]),
    ("str_mill_path", "Mill path", "alley", 8, [(722, 276), (752, 240), (764, 205), (766, 192)]),
    ("str_hakon_path", "Hakon's lane", "lane", 10, [(700, 700), (745, 650), (790, 600), (825, 545), (838, 512)]),
    ("str_west_lane", "West lane", "lane", 11, [(263, 490), (280, 530), (292, 580), (292, 604)]),
    ("str_west_loop", "West loop", "alley", 8, [(292, 640), (250, 650), (228, 615), (240, 585), (262, 575)]),
    ("str_west_link", "Big hall link", "lane", 10, [(292, 640), (330, 645), (370, 632), (393, 592)]),
    ("str_thorne_lane", "Thorne Farm lane", "lane", 11, [(830, 822), (790, 855), (740, 872), (690, 885), (650, 890)]),
    ("str_fenn_lane", "Fenn Farm lane", "lane", 11, [(700, 700), (770, 692), (850, 684), (930, 690), (1000, 712), (1060, 740), (1090, 790)]),
]

B = []


def b(i, name, kind, fl, x, y, L, Wd, style, note=""):
    B.append(dict(id=i, name=name, kind=kind, floors=fl, px=(x, y), L=L, W=Wd, style=style, note=note))


S_HOUSE = "moorland_cottage"
b("bld_big_hall", "Big hall (west)", "hall", 2, 292, 607, 62, 30, "long_timber_hall", "Largest building of the west cluster on the map. DM guide / project sources: formal name and function not in sources, so it is NOT labelled inn or meeting house.")
b("bld_church", "Varrenmoor Church", "church", 2, 700, 332, 70, 28, "parish_church", "Churchyard on the map: spired church inside a round wall.")
b("bld_hakon_house", "Father Hakon's House", "house", 2, 838, 506, 36, 24, "norse_log", "Labelled on the map.")
b("bld_stables", "Stables", "stable", 1, 521, 286, 60, 24, "town_barn", "Labelled on the map.")
b("bld_granary_mill", "Granary Mill", "mill", 2, 765, 186, 44, 34, "town_mill", "Labelled on the map; stands beside a mill stream (stream not modelled).")
b("bld_hollow_longhouse", "Long building at the Hollow", "house", 2, 413, 543, 58, 30, "moorland_cottage", "The big long building north of Pilgrim's Road at the Hollow; role not in sources (no inn is canon).")
b("bld_thorne_farmhouse", "Thorne Farmhouse", "farmhouse", 2, 638, 888, 44, 26, "farm_longhouse", "Thorne Farm on the map.")
b("bld_thorne_barn", "Thorne Barn", "barn", 1, 684, 925, 56, 30, "town_barn")
b("bld_thorne_shed", "Thorne Shed", "shed", 1, 712, 892, 22, 16, "norse_log")
b("bld_fenn_farmhouse", "Fenn Farmhouse", "farmhouse", 2, 1002, 775, 44, 26, "farm_longhouse", "Fenn Family Farm label on the map; the farmstead itself is not drawn. Location approximate.")
b("bld_fenn_barn", "Fenn Barn", "barn", 1, 1030, 802, 56, 30, "town_barn", "Location approximate.")
for n, (x, y, k) in enumerate([(385, 552, "house"), (440, 557, "house"), (405, 582, "house"), (455, 592, "house"), (478, 576, "house"), (447, 470, "shed"), (470, 462, "shed"),
                               (520, 468, "shed"), (545, 500, "house")], 1):
    b(f"bld_hollow_{n:02d}", f"Hollow house {n}" if k == "house" else f"Hollow outbuilding {n}", k, 1, x, y, 30 if k == "house" else 18, 20 if k == "house" else 14, S_HOUSE)
for n, (x, y) in enumerate([(503, 566), (520, 574), (538, 566), (512, 592), (532, 598), (552, 588)], 1):
    b(f"bld_east_{n:02d}", f"East Hollow house {n}", "house", 1, x, y, 30, 20, S_HOUSE)
for n, (x, y) in enumerate([(262, 584), (318, 586), (338, 624), (252, 640), (300, 656), (348, 598), (276, 566), (225, 612), (372, 617), (395, 598)], 1):
    b(f"bld_west_{n:02d}", f"West house {n}", "house", 1, x, y, 30, 20, S_HOUSE)

FIELDS = [
    ("fld_fenn_a", "Fenn field A", "tilled", [(775, 722), (850, 692), (893, 728), (818, 766)]),
    ("fld_fenn_b", "Fenn field B", "wheat", [(842, 818), (915, 790), (978, 824), (902, 854)]),
    ("fld_fenn_c", "Fenn field C", "crop_green", [(925, 884), (1010, 852), (1095, 900), (1010, 940)]),
    ("fld_thorne_paddock", "Thorne paddock", "pasture", [(620, 842), (740, 830), (770, 868), (748, 902), (632, 905)]),
]
DISTRICTS = [
    ("dis_varrenmoor", "Varrenmoor village", "district", "core", circle((400, 560), 190, 24)),
    ("dis_farms", "Farmland", "district", "farm", [(600, 820), (1100, 640), (1100, 960), (600, 960)]),
    ("sqr_hollow_oak", "Hollow Oak green", "square", None, circle(OAK, 34, 24)),
    ("sqr_churchyard", "Churchyard", "square", None, circle(CHURCH, 50, 24)),
    ("sqr_meeting_green", "Big hall green", "square", None, circle((292, 622), 24, 20)),
]


def jsave(p, d):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")


# ---------------------------------------------------------------- terrain
def terrain():
    import place_terrain as PT
    import terrain as T
    spec = json.load(open(os.path.join(PDIR, "place_spec.json"), encoding="utf-8"))
    tcfg = dict(spec["terrain"])
    tcfg["cell_ft"] = 15.0
    tspec, info = PT.build_terrain_spec(tcfg, W_FT, H_FT, int(spec["seed"]))
    tspec["size_ft"] = [W_FT, H_FT]
    tspec["cell_ft"] = 15.0
    tspec["base_elevation_ft"] = 700.0
    tspec["base_tilt"] = [0.0, 0.0]
    river = [ft(*p) for p in RIVER]
    n = len(river)
    tspec["valleys"] = [{"name": "river (map: stream from the Greyspine foothills down the west side)", "core_ft": 25, "side_slope": 0.22,
                         "points": [[r[0], r[1], round(-6 + 70 * (1 - i / (n - 1)) ** 1.5, 1), 0.22] for i, r in enumerate(river)], "river": True,
                         "meander": {"preset": "gentle", "seed": 208, "width_floor_ft": 40.0, "width_gorge_ft": 28.0}}]
    tspec["ridges"] = [
        {"name": "Greyspine massif (north-east)", "width_ft": 1200, "sharpness": 1.4, "points": [ft(640, 60) + [120], ft(850, 90) + [240], ft(1100, 170) + [420]], "spurs": True},
        {"name": "Eastern Ridge (cliffs)", "width_ft": 600, "sharpness": 2.0, "points": [ft(980, 300) + [200], ft(1050, 470) + [210], ft(1100, 640) + [170]], "spurs": True},
        {"name": "west hills", "width_ft": 900, "sharpness": 1.2, "points": [ft(20, 200) + [120], ft(60, 330) + [60], ft(40, 760) + [70], ft(80, 950) + [90]], "spurs": True},
        {"name": "south hills", "width_ft": 900, "sharpness": 1.2, "points": [ft(200, 940) + [60], ft(520, 960) + [90], ft(700, 960) + [60]], "spurs": True},
    ]
    tspec["peaks"] = [{"name": "stables hill", "x": ft(520, 230)[0], "y": ft(520, 230)[1], "height": 60, "radius_ft": 700, "mode": "add"},
                      {"name": "churchyard rise", "x": ft(700, 335)[0], "y": ft(700, 335)[1], "height": 10, "radius_ft": 500, "mode": "add"},
                      {"name": "Hakon's knoll", "x": ft(838, 480)[0], "y": ft(838, 480)[1], "height": 30, "radius_ft": 400, "mode": "add"}]
    tspec["passes"] = []
    nat = tspec.get("natural", {})
    kc = [ft(400, 560) + [1500], ft(700, 335) + [550], ft(838, 505) + [350]]
    nat["keep_clear"] = kc
    nat["spurs"] = {"clear_points": [p[:2] + [700] for p in kc]}
    tspec["natural"] = nat
    h, meta = T.generate(tspec)
    os.makedirs(os.path.join(PDIR, "terrain"), exist_ok=True)
    jsave(os.path.join(PDIR, "terrain_spec.json"), tspec)
    T.save(h, meta, os.path.join(PDIR, "terrain"))
    wents = PT.build_water(tspec, info, h, meta, PID, {"river_names": ["Elva"]})
    jsave(os.path.join(PDIR, "water.json"), {"place": PID, "water": wents})
    return h, meta, wents


def bil(h, cell, x, y):
    j = min(max(x / cell, 0), h.shape[1] - 1.001)
    i = min(max(y / cell, 0), h.shape[0] - 1.001)
    i0, j0 = int(i), int(j)
    fi, fj = i - i0, j - j0
    return float((1 - fi) * ((1 - fj) * h[i0, j0] + fj * h[i0, j0 + 1]) + fi * ((1 - fj) * h[i0 + 1, j0] + fj * h[i0 + 1, j0 + 1]))


def build(no_terrain=False):
    from shapely.geometry import LineString, Point, Polygon, box
    from shapely import affinity
    from shapely.ops import unary_union
    if not no_terrain:
        h, meta, wents = terrain()
    else:
        h = np.load(os.path.join(PDIR, "terrain", "heightmap.npy"))
        meta = json.load(open(os.path.join(PDIR, "terrain", "terrain_meta.json")))
        wents = json.load(open(os.path.join(PDIR, "water.json")))["water"]
    cell = float(meta["cell_ft"])
    link = {"foundry_scene": None, "model3d": None, "ai_layer": None}
    river_poly = Polygon(wents[0]["geometry"]["points"]).buffer(0)
    streets = []
    for sid, name, cls, wid, pts in ROADS:
        P = [ft(*p) for p in pts]
        e = {"id": sid, "name": name, "kind": {"road": "road", "street": "street", "lane": "lane", "alley": "lane"}[cls], "status": "proposed",
             "geometry": {"type": "polyline", "points": P, "width_ft": wid}, "notes": "Digitised from the campaign map (Foundry scene Map). Dirt track.",
             "links": link, "edit": {"class": cls, "surface": "dirt", "kerb": False}}
        if sid == "str_pilgrim_road":
            ls = LineString(P)
            ix = ls.intersection(river_poly.buffer(14))
            if not ix.is_empty:
                g = ix if ix.geom_type == "LineString" else max(ix.geoms, key=lambda q: q.length)
                a, bb = sorted([ls.project(Point(g.coords[0])), ls.project(Point(g.coords[-1]))])
                west = [list(ls.interpolate(d).coords[0]) for d in np.linspace(0, a, max(2, int(a // 40) + 1))]
                first_e = list(ls.interpolate(bb).coords[0])
                mid = [list(ls.interpolate(d).coords[0]) for d in np.linspace(a, bb, 4)]
                east_v = [first_e] + [q for q in P if ls.project(Point(q)) > bb + 1]
                rnd = lambda pl: [[round(v, 1) for v in q] for q in pl]
                e["geometry"]["points"] = rnd(west)
                e["id"] = "str_pilgrim_road_west"
                streets.append(e)
                streets.append({"id": "str_pilgrim_bridge", "name": "Pilgrim's Bridge", "kind": "bridge", "status": "proposed",
                                "geometry": {"type": "polyline", "points": rnd(mid), "width_ft": 18},
                                "notes": "Timber bridge where Pilgrim's Road crosses the river at the map's west edge (a small structure is drawn there).", "links": link,
                                "material": "timber"})
                streets.append({"id": "str_pilgrim_road", "name": "Pilgrim's Road", "kind": "road", "status": "proposed",
                                "geometry": {"type": "polyline", "points": rnd(east_v), "width_ft": wid},
                                "notes": "Digitised from the campaign map. Dirt track; leads off-map west to Bridgehollow.", "links": link,
                                "edit": {"class": "road", "surface": "dirt", "kerb": False}})
                continue
        streets.append(e)
    for s in streets:
        zs = [round(bil(h, cell, p[0], p[1]), 1) for p in s["geometry"]["points"]]
        s["elevations_ft"] = zs
        s["elevation_ft"] = round(float(np.mean(zs)), 1)
    jsave(os.path.join(PDIR, "streets.json"), {"place": PID, "streets": streets})
    road_geoms = [(LineString(s["geometry"]["points"]), s["geometry"]["width_ft"]) for s in streets if s["kind"] != "bridge"]
    road_union = unary_union([g.buffer(w / 2 + 5) for g, w in road_geoms])
    for f in glob.glob(os.path.join(PDIR, "buildings", "*.json")):
        os.remove(f)
    os.makedirs(os.path.join(PDIR, "buildings"), exist_ok=True)
    placed = []
    obstacles = road_union.union(river_poly.buffer(25))
    for bd in B:
        cx, cy = ft(*bd["px"])
        rng = np.random.default_rng(int(hashlib.md5(bd["id"].encode()).hexdigest()[:6], 16))
        pt = Point(cx, cy)
        best = min(road_geoms, key=lambda gw: gw[0].distance(pt))
        ang = float(rng.uniform(0, 180))
        if best[0].distance(pt) < 120:
            d0 = best[0].project(pt)
            a, c = best[0].interpolate(max(0, d0 - 5)), best[0].interpolate(min(best[0].length, d0 + 5))
            ang = math.degrees(math.atan2(c.y - a.y, c.x - a.x)) + float(rng.normal(0, 7))
        rect = None
        for k in range(40):
            dx = dy = 0.0
            if k:
                th = rng.uniform(0, 2 * math.pi)
                dx, dy = math.cos(th) * 3 * k, math.sin(th) * 3 * k
            r = affinity.rotate(box(cx + dx - bd["L"] / 2, cy + dy - bd["W"] / 2, cx + dx + bd["L"] / 2, cy + dy + bd["W"] / 2), ang, origin=(cx + dx, cy + dy))
            if not r.intersects(obstacles) and not any(r.buffer(6).intersects(q) for q in placed):
                rect = r
                break
        if rect is None:
            rect = affinity.rotate(box(cx - bd["L"] / 2, cy - bd["W"] / 2, cx + bd["L"] / 2, cy + bd["W"] / 2), ang, origin=(cx, cy))
        placed.append(rect)
        pts = [[round(x, 1), round(y, 1)] for x, y in list(rect.exterior.coords)[:-1]]
        el = round(float(np.mean([bil(h, cell, x, y) for x, y in pts])), 1)
        rec = {"id": bd["id"], "name": bd["name"], "kind": bd["kind"], "status": "proposed", "geometry": {"type": "polygon", "points": pts},
               "notes": bd["note"] or "Placed at a roof symbol of the campaign map.", "links": link, "floors": bd["floors"], "rooms": [], "doors": [], "elevation_ft": el,
               "style": bd["style"], "map_px": list(bd["px"]), "angle_deg": round(ang, 1)}
        if bd["kind"] in ("house", "farmhouse", "cottage"):
            rec["interior_style"] = "farmhouse" if bd["kind"] == "farmhouse" else "rustic_cottage"
        jsave(os.path.join(PDIR, "buildings", bd["id"] + ".json"), rec)
    ds = []
    for did, name, kind, ring, pts in DISTRICTS:
        P = [ft(*p) for p in pts]
        e = {"id": did, "name": name, "kind": kind, "status": "proposed", "geometry": {"type": "polygon", "points": P}, "notes": "Digitised from the campaign map.", "links": link,
             "elevation_ft": round(float(np.mean([bil(h, cell, p[0], p[1]) for p in P])), 1)}
        if ring:
            e["ring"] = ring
        e["label_point"] = [round(float(v), 1) for v in np.mean(P, 0)]
        ds.append(e)
    for fid, name, crop, pts in FIELDS:
        P = [ft(*p) for p in pts]
        ds.append({"id": fid, "name": name, "kind": "field", "status": "proposed", "crop": crop, "geometry": {"type": "polygon", "points": P},
                   "notes": "Field outline traced from the map.", "links": link, "elevation_ft": round(float(np.mean([bil(h, cell, p[0], p[1]) for p in P])), 1)})
    jsave(os.path.join(PDIR, "districts.json"), {"place": PID, "districts": ds})
    pj = json.load(open(os.path.join(PDIR, "place.json"), encoding="utf-8"))
    pj["bounds"] = {"width_ft": W_FT, "height_ft": H_FT}
    pj["name"] = "Varrenmoor"
    pj["notes"] = ("Varrenmoor, placed from the campaign map (Foundry scene 'Map', assets/map v2.png): 7.69 ft per map pixel (map scale bar), window origin = map px (0,160). "
                   "Streets, buildings, plazas and fields are digitised from the map; terrain is generated to suit it. No paved roads: dirt tracks, grass green. All entities proposed.")
    pj["generated_by"] = "varrenmoor_build.py"
    pj["map_calibration"] = {"source": "illustrator/out/foundry_screens/varrenmoor_original_map.png", "ft_per_px": S, "origin_px": [X0, Y0], "size_px": [1448, 1086]}
    pj["view_focus"] = {"town": ft(*OAK)}
    pj.setdefault("defaults", {})["fills_style"] = "varrenmoor"
    pj["defaults"]["interior_style"] = "rustic_cottage"
    jsave(os.path.join(PDIR, "place.json"), pj)
    print(json.dumps({"ok": True, "buildings": len(B), "streets": len(streets), "districts": len(ds), "elev": [float(h.min()), float(h.max())]}))


# ---------------------------------------------------------------- overlay / measurement
def overlay(out=None):
    from PIL import Image, ImageDraw
    im = Image.open(MAP_PNG).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    ld = lambda f: json.load(open(os.path.join(PDIR, f), encoding="utf-8"))
    for s in ld("streets.json")["streets"]:
        d.line([px_of(*p) for p in s["geometry"]["points"]], fill=(255, 60, 60, 255) if s["kind"] != "bridge" else (255, 255, 0, 255), width=2)
    for w in ld("water.json")["water"]:
        d.line([px_of(*p) for p in w["centerline"]], fill=(0, 200, 255, 255), width=2)
        d.polygon([px_of(*p) for p in w["geometry"]["points"]], outline=(0, 140, 255, 255))
    for dd in ld("districts.json")["districts"]:
        col = (80, 255, 80, 255) if dd["kind"] == "square" else (255, 160, 0, 255) if dd["kind"] == "field" else (200, 200, 200, 120)
        d.polygon([px_of(*p) for p in dd["geometry"]["points"]], outline=col)
    for f in glob.glob(os.path.join(PDIR, "buildings", "*.json")):
        b_ = json.load(open(f, encoding="utf-8"))
        d.polygon([px_of(*p) for p in b_["geometry"]["points"]], outline=(255, 255, 255, 255), fill=(255, 255, 255, 110))
    x1, y1 = px_of(W_FT, H_FT)
    d.rectangle([X0, Y0, x1 - 1, y1 - 1], outline=(255, 0, 255, 255), width=2)
    out = out or os.path.join(REPO, "illustrator", "out", "foundry_screens", "varrenmoor_map_vs_model.png")
    Image.alpha_composite(im, ov).convert("RGB").save(out)
    return out


def measure():
    """Placement error: building centres vs the digitised map symbols (after collision nudges), river centreline vs digitised river, road polylines vs digitised."""
    from shapely.geometry import LineString, Point
    res = {"ft_per_map_px": S}
    err = []
    for f in glob.glob(os.path.join(PDIR, "buildings", "*.json")):
        b_ = json.load(open(f, encoding="utf-8"))
        c = np.array(b_["geometry"]["points"]).mean(0)
        err.append(float(np.hypot(*(c - np.array(ft(*b_["map_px"]))))))
    res["buildings_n"] = len(err)
    res["building_centre_offset_ft"] = {"mean": round(float(np.mean(err)), 1), "p90": round(float(np.percentile(err, 90)), 1), "max": round(float(np.max(err)), 1)}
    res["building_centre_offset_map_px"] = {"mean": round(float(np.mean(err)) / S, 2), "max": round(float(np.max(err)) / S, 2)}
    w = json.load(open(os.path.join(PDIR, "water.json"), encoding="utf-8"))["water"][0]
    cl = LineString(w["centerline"])
    dv = [cl.distance(Point(ft(*p))) for p in RIVER if 0 <= ft(*p)[0] <= W_FT and 0 <= ft(*p)[1] <= H_FT]
    res["river_centreline_vs_map_ft"] = {"mean": round(float(np.mean(dv)), 1), "max": round(float(np.max(dv)), 1)}
    res["river_centreline_vs_map_px"] = {"mean": round(float(np.mean(dv)) / S, 2), "max": round(float(np.max(dv)) / S, 2)}
    st = json.load(open(os.path.join(PDIR, "streets.json"), encoding="utf-8"))["streets"]
    rd = {}
    for sid, name, cls, wid, pts in ROADS:
        lines = [LineString(s["geometry"]["points"]) for s in st if s["id"].startswith(sid) and len(s["geometry"]["points"]) > 1]
        dd = [min(l.distance(Point(ft(*p))) for l in lines) for p in pts if 0 <= ft(*p)[0] <= W_FT and 0 <= ft(*p)[1] <= H_FT]
        rd[sid] = round(float(max(dd)), 2) if dd else None
    res["road_vertex_to_model_road_max_ft"] = rd
    jsave(os.path.join(REPO, "illustrator", "out", "varrenmoor_error.json"), res)
    return res


def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    b_ = sp.add_parser("build")
    b_.add_argument("--no-terrain", action="store_true")
    sp.add_parser("overlay")
    sp.add_parser("measure")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.no_terrain)
    elif a.cmd == "overlay":
        print(overlay())
    else:
        print(json.dumps(measure(), indent=1))


if __name__ == "__main__":
    main()
