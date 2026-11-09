"""Ossuary Exchange: Grand Layout (place world/ossuary_exchange_grand).

A schematic plan of the whole Ossuary Exchange with one building footprint per Foundry scene (existing + Session 14), the landmarks from
canon, districts, and the connecting ways (streets, the overhead trolley line, the pneumatic tube run, the cold-door threshold link).
Idempotent: rewrites streets.json, districts.json and buildings/osc_*.json / lm_*.json every run (other files untouched).

  python illustrator/generators/ossuary_grand.py [--dry-run] [--offline] [--png PATH]

Scene sizes: read live from Foundry (read-only `list` + `get` through foundry-bridge) unless --offline; fallback = the built-in table
(values read 2026-11-09). Footprint ft = scene px / grid.size * grid.distance (the scene CANVAS, which includes empty margin around
the 3D model), except where the canon gives the real building size (the hallway 30 x 150 ft, the Session 14 spec sizes).

Coordinates: feet, origin top-left, x east, y south (up = north), like every place. The market plaza is the hub; shop angles come from
the market generator's plan (foundry-3d/generators/ossuary_market_new.py, SCENE_NOTE: CCW from east). See gm-guide/Ossuary_Grand_Layout.md.
"""
import argparse
import json
import math
import os
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PLACE = "ossuary_exchange_grand"
PDIR = os.path.join(ROOT, "world", PLACE)
BRIDGE = os.path.join(ROOT, "foundry-bridge", "bridge.ps1")

MX, MY = 640.0, 470.0      # market plaza centre ("the Exchange junction")
PLAZA_R = 75.0             # 150-ft plaza (handoff: circular patio 150-ft usable diameter)

# name -> (uuid or None, w_ft, h_ft) fallback from Foundry 2026-11-09 (all 5-ft grid, 100 px)
FALLBACK = {
    "Brokka's Forge": ("Scene.DfVC08aOlUXg9kQ1", 100, 80),
    "Lower Market Warehouse": ("Scene.zOY5zJ6WgGd3kTFE", 120, 95),
    "Ossuary Exchange Conveyor Shafts + Annex": ("Scene.JSt608S3TkmcBAzS", 160, 130),
    "Ossuary Exchange Market": ("Scene.p7Id2gr9TF5dN1Iz", 200, 150),
    "Ossuary Exchange Tavern": ("Scene.LO9YAwP85R74V3tB", 110, 80),
    "Ossuary Exchange Upstairs": ("Scene.KuSqU8GKwpee7eG4", 160, 85),
    "Pimm's Clinic": ("Scene.DB8SFIbpKIQg2NJE", 105, 85),
    "Quill's Rune Workshop": ("Scene.is4fru586eHliLJ4", 90, 80),
    "The Clerk's Room": ("Scene.9FXgTuuLHDgm5Zs9", 100, 75),
    "The Hallway": ("Scene.WQh8sMDG7aexrRb6", 200, 150),
    "Estate exterior": ("Scene.qeyU7cygquu3EE4S", 200, 200),
    "Estate *interior": ("Scene.ShsYfH88NeYoxcSU", 200, 200),
    # Session 14 (spec sizes; scenes built by the sibling agents)
    "Harrowgate Restorations": (None, 50, 40),
    "Night Custody Office": (None, 40, 30),
    "Dusty Terminal and the Cold Door": (None, 55, 30),
    "Ropewalk and Signal Loft": (None, 80, 30),
    "Cold Door Landing": (None, 60, 40),
}


def slug(s):
    out = "".join(c.lower() if c.isalnum() else "_" for c in s)
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def bridge(op, args):
    r = subprocess.run(["powershell", "-NoProfile", "-File", BRIDGE, "-Op", op, "-Args", json.dumps(args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)
    return json.loads(r.stdout)


def live_sizes():
    """Read-only: list scenes, get the ones we know (and the Session 14 ones by name prefix match). Returns name -> (uuid, w, h)."""
    out = {}
    scenes = bridge("list", {"collection": "Scene"})
    for s in scenes:
        nm = s.get("name") or ""
        key = next((k for k in FALLBACK if nm == k or (FALLBACK[k][0] is None and k.lower() in nm.lower())), None)
        if not key:
            continue
        d = bridge("get", {"uuid": s["uuid"]})
        if isinstance(d, dict) and isinstance(d.get("data"), dict):
            d = d["data"]
        g = d.get("grid") or {}
        size, dist = g.get("size") or 100, g.get("distance") or 5
        w, h = d.get("width"), d.get("height")
        if w and h:
            if FALLBACK[key][0] is None:   # new scenes: keep the spec size of the room itself, record the uuid
                out[key] = (s["uuid"], FALLBACK[key][1], FALLBACK[key][2])
            else:
                out[key] = (s["uuid"], round(w / size * dist), round(h / size * dist))
    return out


def polar(ang_deg, r):
    a = math.radians(ang_deg)
    return MX + r * math.cos(a), MY - r * math.sin(a)


def ring_centre(ang, w, h, gap=32.0):
    """Centre of a w x h box sitting just outside the ring street at angle ang (CCW from east)."""
    a = math.radians(ang)
    ux, uy = math.cos(a), -math.sin(a)
    # half-extent of the box along the radial direction
    ext = abs(ux) * w / 2 + abs(uy) * h / 2
    r = PLAZA_R + 20 + gap + ext
    return MX + r * ux, MY + r * uy


def rect(cx, cy, w, h):
    x0, y0, x1, y1 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    return [[round(x0, 1), round(y0, 1)], [round(x1, 1), round(y0, 1)], [round(x1, 1), round(y1, 1)], [round(x0, 1), round(y1, 1)]]


def circle(cx, cy, r, n=36):
    return [[round(cx + r * math.cos(2 * math.pi * i / n), 1), round(cy + r * math.sin(2 * math.pi * i / n), 1)] for i in range(n)]


def build_layout(sizes):
    B = []   # buildings / footprints

    def add(name, kind, status, cx, cy, w, h, district, connects, source, notes="", ident=None, uuid=None, shape=None, label_at=None):
        B.append(dict(id=ident or "osc_" + slug(name), name=name, kind=kind, status=status, cx=cx, cy=cy, w=w, h=h,
                      district=district, connects=connects, source=source, notes=notes, uuid=uuid, shape=shape, label_at=label_at))

    def sz(name):
        u, w, h = sizes.get(name, FALLBACK[name])
        return u, w, h

    EV_PLAN = "evidence: market plan angles (ossuary_market_new.py SCENE_NOTE)"
    # --- Lower market ring (angles CCW from east) -----------------------------------------------------------------
    u, w, h = sz("Ossuary Exchange Market")
    add("Ossuary Exchange Market", "plaza", "existing", MX, MY, 2 * PLAZA_R, 2 * PLAZA_R, "Lower Market",
        "every shop door; Eastern Gate (E); arrival portal to The Hallway (S); trolley hub overhead",
        "evidence: handoff (150-ft circular patio) + market plan", "The junction: 150-ft circular plaza, overhead trolley hub-and-spoke. Scene canvas %dx%d ft." % (w, h),
        uuid=u, shape="circle")
    for name, ang, kind, conn in [
        ("Brokka's Forge", 40, "smithy", "Market (south street door)"),
        ("Pimm's Clinic", 130, "shop", "Market (south street door)"),
        ("Quill's Rune Workshop", 180, "shop", "Market (south street door)"),
        ("Ossuary Exchange Tavern", 290, "inn", "Market (plaza side); west door to The Hallway; bar drop-tube down to the Conveyor Shafts; stair to Upstairs"),
        ("Lower Market Warehouse", 340, "warehouse", "Market; the amended warehouse door (Quest 1)"),
    ]:
        u, w, h = sz(name)
        cx, cy = ring_centre(ang, w, h)
        add(name, kind, "existing", cx, cy, w, h, "Lower Market", conn, EV_PLAN + " (%d deg)" % ang,
            "Footprint = scene canvas %dx%d ft." % (w, h), uuid=u)
    # Upstairs: same building as the tavern, one floor up -> drawn as an inset outline on the tavern footprint
    t = next(b for b in B if b["name"] == "Ossuary Exchange Tavern")
    u, w, h = sz("Ossuary Exchange Upstairs")
    add("Ossuary Exchange Upstairs", "inn", "existing", t["cx"] + t["w"] / 2 + 60, t["cy"] + 10, 70, 34, "Lower Market",
        "Tavern (stair); rooms 201-208, Room 208 (Europa, Session 14)", "evidence: GM reference (inn upstairs rooms)",
        "Floor ABOVE the tavern; drawn as a tag below the tavern so both stay visible. Scene canvas %dx%d ft." % (w, h), uuid=u)
    # Session 14 on the market ring
    u, w, h = sz("Harrowgate Restorations")
    cx, cy = ring_centre(152, w, h)
    add("Harrowgate Restorations", "shop", "new", cx, cy, w, h, "Lower Market", "Market (street door, south side of the front room)",
        "spec: connects to Market; angle 152 deg between the clinic and the rune shop [APPROXIMATE]", "Spec size 50x40 ft.", uuid=u)
    u, w, h = sz("Ropewalk and Signal Loft")
    cx, cy = ring_centre(252, w, h)
    add("Ropewalk and Signal Loft", "workshop", "new", cx, cy, w, h, "Lower Market", "Market (Market_Doors); signal window onto the trolley rails",
        "spec: connects to Market, loft overlooks the rails; angle 252 deg (house plots 230-260) [APPROXIMATE]", "Spec size 80x30 ft, E-W.", uuid=u)
    # landmarks on the ring
    gx, gy = polar(0, PLAZA_R + 32)
    add("Eastern Gate", "gate", "landmark", gx, gy, 16, 46, "Lower Market", "Market; Mavis's road east (outside Exchange jurisdiction)",
        "evidence: market plan (gate 0 deg = east), handoff eastern exit (-Z road/Mavis)", ident="lm_eastern_gate")
    cx, cy = ring_centre(85, 70, 45)
    add("Exchange Guildhall", "civic", "landmark", cx, cy, 70, 45, "Lower Market", "Market (north side)", EV_PLAN + " (70-100 deg)",
        "No Foundry scene.", ident="lm_guildhall")
    cx, cy = ring_centre(213, 55, 40)
    add("Post Office", "civic", "landmark", cx, cy, 55, 40, "Lower Market", "Market", EV_PLAN + " (210-230 deg)",
        "Foundry has 'Postal Office Interior' (not in the Ossuary folder; not confirmed to be this one).", ident="lm_post_office")
    ax, ay = polar(270, PLAZA_R + 20)
    add("Arrival Portal", "gate", "landmark", ax, ay, 30, 14, "Lower Market", "Market (S) <-> The Hallway", EV_PLAN + " (arrival 270 deg)",
        ident="lm_arrival_portal")

    # --- Exchange core (south of the market): hallway, intake, custody, memorial ---------------------------------------
    hx0, hx1, hy = MX - 250, MX - 100, MY + 285          # hallway 150 ft E-W
    u, w, h = sz("The Hallway")
    add("The Hallway", "hall", "existing", (hx0 + hx1) / 2, hy, 150, 30, "Exchange Core",
        "west: large double doors to The Clerk's Room / intake; east: exit to the arrival portal and Market; 20 office doors incl. Night Custody Office",
        "evidence: handoff (grand hall 30x150 ft, double doors left, exit right); orientation and position [APPROXIMATE]",
        "Real hall 30x150 ft (scene canvas %dx%d ft)." % (w, h), uuid=u)
    u, w, h = sz("The Clerk's Room")
    add("The Clerk's Room", "civic", "existing", hx0 - 15 - w / 2, hy, w, h, "Exchange Core",
        "The Hallway (double doors); FEMORAL INTAKE (Pringus); Session 14 Reconciliation Audit",
        "evidence: handoff (FEMORAL INTAKE plaque in the clerk room) + hallway double doors; side [APPROXIMATE]",
        "Footprint = scene canvas %dx%d ft." % (w, h), uuid=u)
    u, w, h = sz("Night Custody Office")
    add("Night Custody Office", "office", "new", hx0 + 55, hy - 15 - 3 - h / 2, w, h, "Exchange Core", "The Hallway (door in its south wall)",
        "spec B2: door from The Hallway in its south wall (so it sits on the hall's north side); position along the hall [APPROXIMATE]",
        "Spec size 40x30 ft. Custody ledger, open claim.", uuid=u)
    add("Cladis Memorial", "monument", "landmark", hx0 + 18, hy + 34, 18, 18, "Exchange Core",
        "The Hallway / intake (Session 12: memorial, Stolen Shard, concealed Eirwitch passage)",
        "canon: memorial is in the Exchange (GM ref); exact spot [APPROXIMATE]", ident="lm_cladis_memorial")
    add("Intake Hall", "civic", "landmark", hx0 - 15 - 50, hy + 75, 70, 30, "Exchange Core",
        "The Clerk's Room; where arrivals are entered (entry anatomy / provenance)", "canon: Ossuary intake with Pringus (Session 12); spot [APPROXIMATE]",
        ident="lm_intake")
    add("Three-Ledger Offices", "office", "landmark", hx0 + 115, hy + 45, 60, 40, "Exchange Core",
        "The Hallway (office doors): intake ledger, custody ledger, physical tags",
        "canon: three records (Session 14 7.2); offices along the hall [APPROXIMATE]", ident="lm_ledger_offices")

    # --- Service ways: shafts, annex, dusty terminal, cold door ----------------------------------------------------------
    u, w, h = sz("Ossuary Exchange Conveyor Shafts + Annex")
    tav = next(b for b in B if b["name"] == "Ossuary Exchange Tavern")
    scx, scy = tav["cx"] + 30, MY + 370
    add("Ossuary Exchange Conveyor Shafts + Annex", "service", "existing", scx, scy, w, h, "Service Ways",
        "Tavern (bar drop-tube to the cellar); Lost Property annex; south dogleg to the Dusty Terminal",
        "evidence: GM ref Quest 2 (drop-tube from the bar into the Exchange shafts) + spec (south dogleg to B3); placed BELOW the tavern, drawn south of it [APPROXIMATE]",
        "Underground (below the market level). Footprint = scene canvas %dx%d ft." % (w, h), uuid=u)
    u, w, h = sz("Dusty Terminal and the Cold Door")
    tcx, tcy = scx + 40, scy + 130 / 2 + 45
    add("Dusty Terminal and the Cold Door", "service", "new", tcx, tcy, w, h, "Service Ways",
        "west entry: Conveyor Shafts south dogleg; east wall: the COLD DOOR (one minute at the usual time) -> Cold Door Landing",
        "spec B3: entry continues the shafts' south dogleg, cold door in the east wall", "Spec size 45x30 interior + 10x30 exterior strip.", uuid=u)
    add("The Cold Door", "gate", "landmark", tcx + w / 2 - 5, tcy, 8, 14, "Service Ways", "Dusty Terminal (east wall) <-> Cold Door Landing (threshold)",
        "spec B3 (east wall at (45,15))", ident="lm_cold_door")

    # --- Eastern road and Mavis's estate ------------------------------------------------------------------------------
    u, w, h = sz("Estate exterior")
    ecx, ecy = 1250.0, MY - 40
    add("Estate exterior", "manor", "existing", ecx, ecy, w, h, "Mavis Bracken's Estate", "Eastern Gate via Mavis's road; Estate *interior",
        "canon: estate beyond the eastern gate (GM ref, Session 12); distance east [APPROXIMATE]", "Scene canvas %dx%d ft." % (w, h), uuid=u)
    u, w2, h2 = sz("Estate *interior")
    add("Estate *interior", "manor", "existing", ecx, ecy + 20, 80, 60, "Mavis Bracken's Estate", "Estate exterior (front hall)",
        "handoff: main block 16x12 grids = 80x60 ft (seven rooms + conservatory)", "House drawn at its real 80x60 ft; scene canvas %dx%d ft." % (w2, h2), uuid=u)

    # --- Mountain road beyond the cold door ----------------------------------------------------------------------------
    u, w, h = sz("Cold Door Landing")
    lcx, lcy = 1130.0, 900.0
    add("Cold Door Landing", "landmark", "new", lcx, lcy, w, h, "Mountain Road (beyond the cold door)",
        "Cold door (threshold, not walking distance); road east up the slope to the Eirwitch Camp",
        "spec B5; the cold door is a threshold, so the map distance is SYMBOLIC [APPROXIMATE]",
        "Spec size 60x40 ft. Snowy road above Bridgehollow.", uuid=u)
    add("Eirwitch Camp (Night)", "landmark", "landmark", 1440, 840, 60, 40, "Mountain Road (beyond the cold door)",
        "Cold Door Landing (road west end = 'Cold door landing')", "spec A (Eirwitch Camp scene, other place world/eirwitch_camp); off-map in reality [APPROXIMATE]",
        ident="lm_eirwitch_camp")
    return B


def build_ways(B):
    by = {b["name"]: b for b in B}

    def c(n):
        return [round(by[n]["cx"], 1), round(by[n]["cy"], 1)]

    tav, shafts, term = by["Ossuary Exchange Tavern"], by["Ossuary Exchange Conveyor Shafts + Annex"], by["Dusty Terminal and the Cold Door"]
    hall = by["The Hallway"]
    gate = by["Eastern Gate"]
    est = by["Estate exterior"]
    arr = by["Arrival Portal"]
    land, camp, door = by["Cold Door Landing"], by["Eirwitch Camp (Night)"], by["The Cold Door"]
    ring = circle(MX, MY, PLAZA_R + 10, 48)
    ring.append(ring[0])
    hx1 = hall["cx"] + hall["w"] / 2
    W = [
        ("str_market_ring", "Market Ring", "street", ring, 18, "street ring in front of the shop doors"),
        ("str_mavis_road", "Mavis's Road", "road", [[gate["cx"] + 8, gate["cy"]], [900, MY - 10], [1060, MY - 40], [est["cx"] - est["w"] / 2, est["cy"]]], 16,
         "eastern gate to the estate (outside Exchange jurisdiction)"),
        ("str_arrival_passage", "Arrival Passage", "lane", [[arr["cx"], arr["cy"] + 7], [arr["cx"], hall["cy"] - 40], [hx1 + 30, hall["cy"]], [hx1, hall["cy"]]], 12,
         "arrival portal (market south) to the hallway's east exit [APPROXIMATE]"),
        ("str_tavern_hall_door", "Tavern West Door", "path", [[tav["cx"] - tav["w"] / 2, tav["cy"]], [arr["cx"] + 8, tav["cy"] + 25], [arr["cx"] + 6, hall["cy"] - 60]], 6,
         "ossuary_tavern.py: door to the Exchange hallway under the mezzanine (west wall)"),
        ("str_trolley_line", "Overhead Bone Trolley Line", "trolley",
         [[MX - 60, MY - 50], [MX, MY], [MX + 70, MY + 40], [shafts["cx"] + 40, shafts["cy"] - 20], [term["cx"] + 10, term["cy"] - 18], [term["cx"] + 70, term["cy"] - 40]], 4,
         "overhead hub over the plaza; the last trolley of the night passes the cold door [route APPROXIMATE]"),
        ("str_trolley_west", "Trolley Line West", "trolley", [[MX - 60, MY - 50], [MX - 150, MY - 120], [MX - 230, MY - 120]], 4, "spoke to the north-west houses [APPROXIMATE]"),
        ("str_trolley_hall", "Trolley Line to the Hallway", "trolley", [[MX, MY], [MX - 30, MY + 120], [hall["cx"], hall["cy"]]], 4,
         "12 overhead carriers in the hall (handoff) [route APPROXIMATE]"),
        ("str_pneumatic", "Pneumatic Tube Run", "pneumatic", [[tav["cx"] + 30, tav["cy"] + 20], [tav["cx"] + 45, shafts["cy"]], [term["cx"] - 10, term["cy"]]], 3,
         "tubes heard through the tavern wall (Mottle rumour 3) to the dusty terminal [route APPROXIMATE]"),
        ("str_shaft_dogleg", "Shafts South Dogleg", "path", [[shafts["cx"], shafts["cy"] + shafts["h"] / 2], [shafts["cx"], term["cy"]], [term["cx"] - term["w"] / 2, term["cy"]]], 5,
         "spec B3: the terminal's west entry continues the shafts' south dogleg"),
        ("str_cold_door_link", "Cold Door Threshold (one minute, the usual time)", "threshold", [[door["cx"] + 4, door["cy"]], [land["cx"] - land["w"] / 2, land["cy"]]], 3,
         "threshold link, not a walkable road"),
        ("str_mountain_road", "Mountain Road", "road", [[land["cx"] - land["w"] / 2, land["cy"] + 5], [land["cx"] + 80, land["cy"] - 10], [1300, 870], [camp["cx"] - camp["w"] / 2, camp["cy"]]], 12,
         "snowy road east up the slope to the Eirwitch camp"),
    ]
    streets = []
    for sid, name, kind, pts, wft, note in W:
        cls = {"trolley": "path", "pneumatic": "path", "threshold": "path"}.get(kind, kind)
        streets.append({"id": sid, "name": name, "kind": cls if cls in ("street", "road", "lane", "path") else "lane", "status": "proposed",
                        "geometry": {"type": "polyline", "points": [[round(p[0], 1), round(p[1], 1)] for p in pts], "width_ft": float(wft)},
                        "edit": {"class": cls, "surface": "dirt" if kind == "road" else "cobble", "kerb": False},
                        "ossuary_way": kind, "notes": "ossuary_grand.py: " + note})
    return streets


DISTRICTS = [
    ("dis_lower_market", "Lower Market", [[290, 240], [960, 240], [960, 700], [560, 700], [560, 655], [290, 655]]),
    ("dis_exchange_core", "Exchange Core", [[240, 655], [560, 655], [560, 700], [640, 700], [640, 880], [240, 880]]),
    ("dis_service_ways", "Service Ways (below ground)", [[640, 700], [960, 700], [960, 1000], [640, 1000]]),
    ("dis_mavis_estate", "Mavis Bracken's Estate", [[1080, 230], [1500, 230], [1500, 640], [1080, 640]]),
    ("dis_mountain_road", "Mountain Road (beyond the cold door)", [[1020, 760], [1560, 760], [1560, 1060], [1020, 1060]]),
]


def write_place(B, streets, dry):
    files = {}
    files["streets.json"] = {"place": PLACE, "streets": streets}
    files["districts.json"] = {"place": PLACE, "districts": [
        {"id": i, "name": n, "kind": "district", "status": "proposed", "geometry": {"type": "polygon", "points": p}} for i, n, p in DISTRICTS]}
    bld = {}
    for b in B:
        pts = circle(b["cx"], b["cy"], b["w"] / 2) if b["shape"] == "circle" else rect(b["cx"], b["cy"], b["w"], b["h"])
        bld[b["id"]] = {"id": b["id"], "name": b["name"], "kind": b["kind"], "status": "proposed",
                        "geometry": {"type": "polygon", "points": pts},
                        "notes": "%s scene. %s Connects: %s. Source: %s" % (b["status"].upper(), b["notes"], b["connects"], b["source"]),
                        "links": {"foundry_scene": b["uuid"], "model3d": None, "ai_layer": None},
                        "floors": 1, "rooms": [], "doors": [],
                        "ossuary": {"status": b["status"], "district": b["district"], "connects": b["connects"], "source": b["source"],
                                    "approximate": "APPROXIMATE" in b["source"]}}
    if dry:
        print(json.dumps({"buildings": len(bld), "streets": len(streets), "districts": len(DISTRICTS)}))
        for b in B:
            print("  %-42s %-8s (%.0f, %.0f) %gx%g" % (b["name"], b["status"], b["cx"], b["cy"], b["w"], b["h"]))
        return
    bdir = os.path.join(PDIR, "buildings")
    os.makedirs(bdir, exist_ok=True)
    for f in os.listdir(bdir):   # idempotent: drop our own old footprints
        if (f.startswith("osc_") or f.startswith("lm_")) and f.endswith(".json") and f[:-5] not in bld:
            os.remove(os.path.join(bdir, f))
    for i, d in bld.items():
        json.dump(d, open(os.path.join(bdir, i + ".json"), "w", encoding="utf-8"), indent=1)
    for fn, d in files.items():
        json.dump(d, open(os.path.join(PDIR, fn), "w", encoding="utf-8"), indent=1)
    pj = os.path.join(PDIR, "place.json")
    p = json.load(open(pj, encoding="utf-8"))
    p["notes"] = ("Grand layout of the Ossuary Exchange: one footprint per Foundry scene (grey = existing, gold = Session 14), landmarks, "
                  "districts, trolley / pneumatic / threshold links. Built by illustrator/generators/ossuary_grand.py; legend in gm-guide/Ossuary_Grand_Layout.md.")
    p.setdefault("view_focus", {})["town"] = [800.0, 560.0]
    json.dump(p, open(pj, "w", encoding="utf-8"), indent=1)
    json.dump([{k: b[k] for k in ("id", "name", "status", "cx", "cy", "w", "h", "district", "connects", "source", "uuid")} for b in B],
              open(os.path.join(PDIR, "ossuary_layout.json"), "w", encoding="utf-8"), indent=1)
    print("wrote %d footprints, %d ways, %d districts to %s" % (len(bld), len(streets), len(DISTRICTS), PDIR))


# ------------------------------------------------------------------------------------------------------------------------
def render_png(B, streets, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon, Circle, FancyArrow, Patch
    from matplotlib.lines import Line2D

    COL = {"existing": ("#c9c6c0", "#55524c"), "new": ("#f2b632", "#8a5a00"), "landmark": ("#e9e2f3", "#6b5a8a")}
    DCOL = {"dis_lower_market": "#f4efe4", "dis_exchange_core": "#e8edf3", "dis_service_ways": "#ece8e1", "dis_mavis_estate": "#e7f0e2",
            "dis_mountain_road": "#e6eef6"}
    fig = plt.figure(figsize=(20, 14), dpi=110)
    ax = fig.add_axes([0.005, 0.01, 0.76, 0.93])
    ax.set_xlim(180, 1600)
    ax.set_ylim(1090, 200)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.add_patch(Polygon([[0, 0], [1600, 0], [1600, 1100], [0, 1100]], closed=True, fc="#faf8f3", ec="#999", lw=1))
    for i, n, p in DISTRICTS:
        ax.add_patch(Polygon(p, closed=True, fc=DCOL[i], ec="#8f8a80", lw=1.2, ls="--", zorder=1))
        xs, ys = [q[0] for q in p], [q[1] for q in p]
        ax.text(min(xs) + 8, min(ys) + 14, n.upper(), fontsize=11, color="#6d675c", weight="bold", va="top", zorder=2)
    WSTY = {"street": ("#bfb6a3", 1.0, "-"), "road": ("#a88f63", 1.0, "-"), "lane": ("#bfb6a3", 1.0, "-"), "path": ("#b9ad95", 1.0, "-"),
            "trolley": ("#b23a2a", 1.0, (0, (6, 3))), "pneumatic": ("#2a6fb2", 1.0, (0, (2, 2))), "threshold": ("#5ab0e0", 1.0, (0, (8, 4)))}
    for s in streets:
        k = s["ossuary_way"]
        col, _, ls = WSTY[k]
        pts = s["geometry"]["points"]
        lw = max(1.5, s["geometry"]["width_ft"] * 0.55) if k in ("street", "road", "lane", "path") else 2.6
        ax.plot([p[0] for p in pts], [p[1] for p in pts], color=col, lw=lw, ls=ls, zorder=3 if k in ("street", "road", "lane", "path") else 6,
                solid_capstyle="round")
    for s in streets:
        if s["id"] in ("str_mavis_road", "str_mountain_road", "str_cold_door_link"):
            pts = s["geometry"]["points"]
            m = len(pts) // 2
            a, b = pts[m - 1], pts[m]
            ang = math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))
            ax.text((a[0] + b[0]) / 2, (a[1] + b[1]) / 2 - 10, s["name"], fontsize=9, color="#5a4a2a", rotation=ang, ha="center", va="bottom", zorder=7,
                    style="italic")
    for b in B:
        fc, ec = COL[b["status"]]
        if b["shape"] == "circle":
            ax.add_patch(Circle((b["cx"], b["cy"]), b["w"] / 2, fc="#efe8d6" if b["status"] == "existing" else fc, ec=ec, lw=2, zorder=4))
        else:
            ax.add_patch(Polygon(rect(b["cx"], b["cy"], b["w"], b["h"]), closed=True, fc=fc, ec=ec, lw=2 if b["status"] != "landmark" else 1.2,
                                 ls="-" if b["status"] != "landmark" else (0, (3, 2)), zorder=5))
    LBL = {  # label offsets (dx, dy) for crowded names
        "Ossuary Exchange Market": (0, 22), "Quill's Rune Workshop": (0, 0), "Ossuary Exchange Upstairs": (12, 34), "Eastern Gate": (0, -36), "Arrival Portal": (52, 2),
        "The Cold Door": (0, 34), "Cladis Memorial": (0, 22), "Estate *interior": (0, 0), "Estate exterior": (0, -80),
    }
    for b in B:
        dx, dy = LBL.get(b["name"], (0, 0))
        nm = b["name"].replace("Ossuary Exchange ", "Ossuary Exchange\n").replace(" and the ", "\nand the ").replace(" + ", " +\n").replace("Quill's Rune Workshop", "Quill's Rune\nWorkshop")
        if b["name"] == "Ossuary Exchange Market":
            nm = "OSSUARY EXCHANGE MARKET\n(the junction, 150-ft plaza)"
        if b["name"] == "Ossuary Exchange Tavern":
            nm = "Ossuary Exchange Tavern\n(Mottle's Mugs)"
        if b["name"] == "Ossuary Exchange Upstairs":
            nm = "Upstairs (floor above\nthe tavern, Room 208)"
        tag = " *" if "APPROXIMATE" in b["source"] else ""
        fs = 10 if b["status"] != "landmark" else 8.5
        ax.text(b["cx"] + dx, b["cy"] + dy, nm + tag, fontsize=fs, ha="center", va="center", zorder=9,
                weight="bold" if b["status"] != "landmark" else "normal", color="#1d1b18" if b["status"] != "landmark" else "#4a3d63",
                bbox=dict(boxstyle="round,pad=0.18", fc=(1, 1, 1, 0.72), ec="none"))
    # north arrow
    ax.add_patch(FancyArrow(1540, 230, 0, -80, width=10, head_width=34, head_length=30, color="#333", zorder=10))
    ax.text(1540, 255, "N", fontsize=18, ha="center", va="center", weight="bold", zorder=10)
    # scale bar 100 ft
    x0, y0 = 250, 1060
    for i in range(4):
        ax.add_patch(Polygon([[x0 + i * 25, y0], [x0 + (i + 1) * 25, y0], [x0 + (i + 1) * 25, y0 + 10], [x0 + i * 25, y0 + 10]], closed=True,
                             fc="#333" if i % 2 == 0 else "#fff", ec="#333", lw=1, zorder=10))
    ax.add_patch(Polygon([[x0 + 100, y0], [x0 + 200, y0], [x0 + 200, y0 + 10], [x0 + 100, y0 + 10]], closed=True, fc="#fff", ec="#333", zorder=10))
    for v in (0, 100, 200):
        ax.text(x0 + v, y0 - 6, "%d ft" % v, fontsize=9, ha="center", va="bottom", zorder=10)
    leg = [Patch(fc=COL["existing"][0], ec=COL["existing"][1], label="Existing Foundry scene (footprint = scene canvas)"),
           Patch(fc=COL["new"][0], ec=COL["new"][1], label="NEW Session 14 scene (spec size)"),
           Patch(fc=COL["landmark"][0], ec=COL["landmark"][1], ls="--", label="Landmark (no scene of its own)"),
           Line2D([0], [0], color="#bfb6a3", lw=6, label="Street / passage"),
           Line2D([0], [0], color="#a88f63", lw=6, label="Road"),
           Line2D([0], [0], color="#b23a2a", lw=2.6, ls=(0, (6, 3)), label="Overhead bone trolley line"),
           Line2D([0], [0], color="#2a6fb2", lw=2.6, ls=(0, (2, 2)), label="Pneumatic tube run"),
           Line2D([0], [0], color="#5ab0e0", lw=2.6, ls=(0, (8, 4)), label="Cold-door threshold (not walking distance)"),
           Patch(fc="none", ec="none", label="*  = position APPROXIMATE\n    (see gm-guide/Ossuary_Grand_Layout.md)")]
    ax.legend(handles=leg, loc="center left", bbox_to_anchor=(1.005, 0.5), fontsize=11, framealpha=0.95, title="Legend", title_fontsize=12)
    fig.suptitle("Ossuary Exchange: Grand Layout (schematic, north up)", fontsize=20, weight="bold", y=0.985)
    fig.text(0.5, 0.945, "Every Ossuary scene placed on one plan. Shops sit at their angles around the market plaza; the shafts and dusty terminal are below "
             "ground; the cold door is a threshold to the mountain road.", ha="center", fontsize=11, color="#444")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=110, facecolor="#ffffff", bbox_inches="tight", pad_inches=0.2)
    plt.close(fig)
    print("png", path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline", action="store_true", help="do not read Foundry; use the built-in table")
    ap.add_argument("--png", default=os.path.join(ROOT, "illustrator", "out", "ossuary_grand_layout.png"))
    a = ap.parse_args()
    sizes = {}
    if not a.offline:
        try:
            sizes = live_sizes()
            print("live Foundry sizes for %d scenes" % len(sizes))
        except Exception as e:  # noqa: BLE001
            print("Foundry not reachable (%s); using the built-in table" % e)
    B = build_layout(sizes)
    streets = build_ways(B)
    write_place(B, streets, a.dry_run)
    if not a.dry_run and a.png:
        render_png(B, streets, a.png)


if __name__ == "__main__":
    sys.exit(main())
