"""Harrowgate Restorations (Session 14, Scene 4: T3 Violet's living strand, T4 Betsy's vessel). Ysolde Harrowgate's licensed
restoration shop, Lower Ossuary. 50 x 40 ft interior, one floor (spec: gm-guide/Session_14_Scenes_Spec.md, B1).
  front room (south, 50 x 15 ft): street door at (25, 40); counter at y = 30 (linen rolls, distilled-water flasks, ledger, bell);
                                  two waiting benches; framed licence on the wall
  work room (north-west 25 x 25): door from the front room at (12, 25); washbasin, steel-topped table, instrument cabinet,
                                  glass case with the mycelium culture on a stand at (6, 6)
  vessel room (north-east 25 x 25): locked door from the work room at (25, 12); covered vessel on a raised table at (37, 12)
                                  under white linen; unlit brazier stand, rack of boundary-rune tiles, 'Stable / Strained' slate
Spec coordinates are feet from the NW corner (x east, y south); converted here to centred metres (x east, y north).
Named interaction objects are kept as their own glTF nodes (custom property `separate`). No emissive materials.
"""
from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Session 14"
SCENE_NOTE = ("Harrowgate Restorations. Vessel room door is locked (Ysolde has the key). Counter drawer (Investigation DC 12): "
              "Wren's file [suggested]. Ysolde at the work table (12, 12); Pimm, if called, by the culture case.")

WFT, HFT = 50.0, 40.0
FT = 0.3048
IX, IY, T, H = WFT * FT / 2, HFT * FT / 2, 0.5, 3.4


def X(xf):
    return -IX + xf * FT


def Y(yf):
    return IY - yf * FT


LIGHTS = [
    dict(x=X(30), y=Y(29), z=2.6, dim=30, bright=10, color="#ffc78a"),     # front counter lamp, warm
    dict(x=X(12), y=Y(15), z=2.8, dim=28, bright=12, color="#fff2d8"),     # work-room lamp over the table
    dict(x=X(37), y=Y(12), z=2.6, dim=18, bright=5, color="#cfe6ff"),      # dim cool lamp, vessel room
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    M["steel"] = k.mat("steel_top", (0.55, 0.56, 0.58), roughness=0.35, metallic=0.6)
    M["glass_case"] = k.mat("case_glass", (0.55, 0.68, 0.72), roughness=0.05)
    M["culture"] = k.mat("mycelium", (0.78, 0.80, 0.70), roughness=0.9)
    M["white_linen"] = k.mat("white_linen", (0.86, 0.85, 0.80), roughness=0.95)

    def named(nm, x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
        o = B(x0, x1, y0, y1, z0, z1, mat, nm, bevel)
        o.name = nm
        o["separate"] = 1
        return o

    B(-IX, IX, -IY, IY, 0, F, M["floor_oak"], "floor")
    # exterior walls: street door + two windows on the south wall
    sx = X(25)
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, [(sx, 1.4, 0, 2.4), (X(8), 1.4, 1.0, 2.4), (X(42), 1.4, 1.0, 2.4)], M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, sx, 1.4, 0, 2.4)
    for xf in (8, 42):
        W.window("x", -IY - T / 2, T, X(xf), w=1.4, sill=1.0, head=2.4)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [], M["ashlar"], name="ext")
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [], M["ashlar"], name="ext")
    W.wall("y", IX + T / 2, -IY, IY, T, H, [], M["ashlar"], name="ext")
    for xf in (12.5, 25, 37.5):
        B(X(xf) - 0.15, X(xf) + 0.15, -IY, IY, H - 0.4, H - 0.05, M["coak"], "beam", 0.01)

    # partitions: E-W at y = 25 ft (door at x = 12), N-S at x = 25 ft from y 0..25 (vessel-room door at y = 12)
    P = 0.25
    W.wall("x", Y(25), -IX, IX, P, H, [(X(12), 1.0, 0, 2.2)], M["plaster"], name="part")
    W.frame("x", Y(25), P, X(12), 1.0, 0, 2.2)
    W.wall("y", X(25), Y(25) + P / 2, IY, P, H, [(Y(12), 1.0, 0, 2.2)], M["plaster"], name="part")
    W.frame("y", X(25), P, Y(12), 1.0, 0, 2.2)
    S.door("street", "x", -IY - T / 2, sx, swing=(0, 1), w=1.4)
    S.door("work_room", "x", Y(25), X(12), swing=(0, 1), w=1.0)
    S.door("Vessel_Room_Door", "y", X(25), Y(12), swing=(1, 0), w=1.0)

    # ---------------- front room
    cy0, cy1 = Y(31), Y(29)                       # counter, 2 ft deep, at y = 30 ft; open passage on the west (x < 16 ft)
    B(X(16), X(46), cy0, cy1, F, F + 1.0, M["doak"], "counter_body", 0.01)
    B(X(16) - 0.03, X(46) + 0.03, cy0 - 0.03, cy1 + 0.03, F + 1.0, F + 1.05, M["oak"], "counter_top", 0.01)
    for i, xf in enumerate((19, 25, 31, 37, 43)):  # drawer fronts on the staff (north) side; the DC 12 drawer is one of them
        B(X(xf) - 0.4, X(xf) + 0.4, cy1, cy1 + 0.02, F + 0.6, F + 0.85, M["oak"], "drawer_front")
        B(X(xf) - 0.05, X(xf) + 0.05, cy1 + 0.02, cy1 + 0.04, F + 0.7, F + 0.74, M["brass"], "drawer_pull")
    top = F + 1.05
    named("Counter_Ledger", X(24) - 0.25, X(24) + 0.25, Y(30) - 0.18, Y(30) + 0.18, top, top + 0.05, M["paper"])
    B(X(24) - 0.23, X(24) + 0.23, Y(30) - 0.16, Y(30) + 0.16, top + 0.05, top + 0.07, M["red"], "ledger_cover")
    lr = k.cylinder(0.11, 0.7, loc=(X(36), Y(30), top + 0.11), rot=(0, 90, 0), material=M["white_linen"], name="Linen_Rolls", verts=12)
    lr.name = "Linen_Rolls"
    lr["separate"] = 1
    for dy in (-0.25, 0.25):
        k.cylinder(0.1, 0.65, loc=(X(36), Y(30) + dy, top + 0.1), rot=(0, 90, 0), material=M["linen"], name="linen_roll", verts=12)
    fl = k.cylinder(0.07, 0.3, loc=(X(42), Y(30), top + 0.15), material=M["glass_case"], name="Distilled_Water_Flasks", verts=10)
    fl.name = "Distilled_Water_Flasks"
    fl["separate"] = 1
    for i in range(4):
        S.jar(X(43.2) + 0.18 * (i % 2), Y(30) - 0.15 + 0.3 * (i // 2), top, 1, "glass_b")
    k.cylinder(0.07, 0.08, loc=(X(29), Y(30.4), top + 0.04), material=M["brass"], name="counter_bell", verts=10)
    k.sphere(0.07, loc=(X(29), Y(30.4), top + 0.1), material=M["brass"], name="counter_bell_dome", segments=8)
    S.chair(X(30), Y(27.5), face="n")
    S.bench(X(2), X(9), Y(38.8), Y(37.4))
    S.bench(X(41), X(48), Y(38.8), Y(37.4))
    # framed licence certificate on the east wall (inner face x = IX)
    B(IX - 0.06, IX - 0.01, Y(35) - 0.45, Y(35) + 0.45, F + 1.4, F + 2.1, M["doak"], "licence_frame")
    B(IX - 0.08, IX - 0.06, Y(35) - 0.38, Y(35) + 0.38, F + 1.47, F + 2.03, M["paper"], "licence_certificate")
    S.rug(X(20), X(30), Y(39), Y(33), M["green"], M["linen"])

    # ---------------- work room (north-west)
    tx0, tx1, ty0, ty1 = X(6), X(18), Y(16.5), Y(13.5)   # long steel-topped table; Ysolde stands at (12, 12)
    B(tx0, tx1, ty0, ty1, F + 0.86, F + 0.92, M["steel"], "steel_table_top", 0.01)
    for lx in (tx0 + 0.1, (tx0 + tx1) / 2, tx1 - 0.1):
        for ly in (ty0 + 0.1, ty1 - 0.1):
            B(lx - 0.05, lx + 0.05, ly - 0.05, ly + 0.05, F, F + 0.86, M["iron"], "table_leg")
    B((tx0 + tx1) / 2 - 0.6, (tx0 + tx1) / 2 + 0.6, ty0 + 0.2, ty1 - 0.2, F + 0.92, F + 0.94, M["white_linen"], "table_cloth")
    for i in range(6):
        B(tx0 + 0.5 + i * 0.18, tx0 + 0.54 + i * 0.18, ty0 + 0.25, ty0 + 0.45, F + 0.92, F + 0.95, M["iron"], "instrument")
    k.cylinder(0.02, 0.9, loc=(X(12), Y(15), H - 0.5), material=M["iron"], name="lamp_stem", verts=6)
    k.cylinder(0.3, 0.1, loc=(X(12), Y(15), H - 1.0), material=M["brass"], name="lamp_shade", verts=14)
    # washbasin on the north wall
    B(X(14), X(18), Y(0) - 0.65, Y(0), F + 0.8, F + 0.88, M["granite"], "basin_top")
    B(X(14) + 0.1, X(18) - 0.1, Y(0) - 0.55, Y(0) - 0.1, F + 0.55, F + 0.8, M["water"], "basin_water")
    B(X(14), X(18), Y(0) - 0.65, Y(0), F, F + 0.55, M["doak"], "basin_base")
    k.cylinder(0.025, 0.35, loc=(X(16), Y(0) - 0.1, F + 1.05), material=M["brass"], name="tap", verts=6)
    # instrument cabinet on the west wall
    S.cabinet(-IX, -IX + 0.5, Y(22), Y(17), 1.9, face="e")
    S.shelf_unit(X(19), X(24), Y(0) - 0.45, Y(0), 2.2, "s", rows=3, items="jars", colors=("glass_a", "glass_b", "clay"))
    # the glass case with the mycelium culture on a stand at (6, 6)
    cx, cyy = X(6), Y(6)
    B(cx - 0.35, cx + 0.35, cyy - 0.35, cyy + 0.35, F, F + 0.9, M["doak"], "case_stand", 0.01)
    B(cx - 0.32, cx + 0.32, cyy - 0.32, cyy + 0.32, F + 0.9, F + 0.95, M["brass"], "case_base")
    named("Mycelium_Culture_Case", cx - 0.3, cx + 0.3, cyy - 0.3, cyy + 0.3, F + 0.95, F + 1.55, M["glass_case"])
    k.cylinder(0.2, 0.05, loc=(cx, cyy, F + 0.98), material=M["glass_b"], name="culture_dish", verts=14)
    # a living strand: a few pale threads rising inside the case (not emissive)
    for i, (dx, dy, h) in enumerate(((-0.08, 0.02, 0.25), (0.05, -0.06, 0.32), (0.1, 0.08, 0.2), (-0.02, -0.1, 0.28))):
        k.cylinder(0.012, h, loc=(cx + dx, cyy + dy, F + 1.0 + h / 2), material=M["culture"], name="culture_strand", verts=5)
    k.sphere(0.09, loc=(cx, cyy, F + 1.02), material=M["culture"], name="culture_mass", segments=8)
    S.stool(X(9), Y(17.5))

    # ---------------- vessel room (north-east, locked)
    vx, vy = X(37), Y(12)
    B(vx - 1.1, vx + 1.1, vy - 0.55, vy + 0.55, F, F + 0.25, M["slate"], "vessel_dais", 0.01)
    named("Vessel_Table", vx - 1.0, vx + 1.0, vy - 0.45, vy + 0.45, F + 0.25, F + 1.05, M["doak"], 0.01)
    # the covered vessel: a construct frame under white linen (kept covered, no gore): a long draped mound
    named("Vessel_Linen", vx - 0.95, vx + 0.95, vy - 0.42, vy + 0.42, F + 1.05, F + 1.32, M["white_linen"], 0.06)
    B(vx - 0.85, vx + 0.55, vy - 0.28, vy + 0.28, F + 1.32, F + 1.42, M["white_linen"], "linen_mound", 0.05)
    k.sphere(0.2, loc=(vx + 0.72, vy, F + 1.36), material=M["white_linen"], name="linen_head", segments=10)
    for dy in (-0.43, 0.43):                      # the linen hangs over the table edges
        B(vx - 0.95, vx + 0.95, vy + dy - 0.015, vy + dy + 0.015, F + 0.75, F + 1.3, M["white_linen"], "linen_drape")
    # unlit brazier stand
    bx, by = X(31), Y(5)
    k.cylinder(0.05, 0.9, loc=(bx, by, F + 0.45), material=M["iron"], name="brazier_stem", verts=8)
    k.cylinder(0.3, 0.06, loc=(bx, by, F + 0.03), material=M["iron"], name="brazier_foot", verts=12)
    k.cylinder(0.32, 0.15, loc=(bx, by, F + 0.97), material=M["iron"], name="brazier_bowl", verts=14)
    B(bx - 0.22, bx + 0.22, by - 0.22, by + 0.22, F + 1.0, F + 1.06, M["soot"], "brazier_ash")
    # rack of boundary-rune tiles on the east wall
    rx = IX
    named("Rune_Tile_Rack", rx - 0.4, rx - 0.02, Y(16), Y(9), F, F + 1.8, M["oak"], 0.01)
    for r in range(4):
        for i in range(6):
            yy = Y(15.5) + i * ((Y(9.5) - Y(15.5)) / 6)
            B(rx - 0.46, rx - 0.4, yy + 0.04, yy + 0.3, F + 0.25 + r * 0.4, F + 0.5 + r * 0.4, M["slate"], "rune_tile")
            B(rx - 0.475, rx - 0.46, yy + 0.12, yy + 0.22, F + 0.32 + r * 0.4, F + 0.42 + r * 0.4, M["chalk"], "rune_mark")
    # slate with 'Stable / Strained' chalk marks (T4 tracker), on the north wall
    sy_ = IY
    B(X(40), X(46), sy_ - 0.05, sy_ - 0.01, F + 1.2, F + 2.0, M["board"], "tracker_slate")
    B(X(42.9), X(43.1), sy_ - 0.07, sy_ - 0.05, F + 1.25, F + 1.95, M["chalk"], "tracker_divider")
    for i in range(3):
        B(X(40.6), X(42.4), sy_ - 0.07, sy_ - 0.05, F + 1.75 - i * 0.18, F + 1.78 - i * 0.18, M["chalk"], "tally_stable")
    B(X(43.6), X(45.4), sy_ - 0.07, sy_ - 0.05, F + 1.75, F + 1.78, M["chalk"], "tally_strained")
    S.crate(X(46), Y(3), 0.6)
    S.chair(X(33), Y(20), face="s")
    S.finish()
