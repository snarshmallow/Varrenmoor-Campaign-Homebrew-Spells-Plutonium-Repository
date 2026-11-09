"""Session 14, B3: The Dusty Terminal and the Cold Door (interior, 45 x 30 ft). Spec: gm-guide/Session_14_Scenes_Spec.md B3.
Pell Ostry's forgotten pneumatic station at the end of the shafts' south dogleg: a brass receiver on a granite plinth with a
lever and pipes into the dark, a capsule rack and timetable board, Pell's iron rail along the north wall with his counterweighted
chair, Haddo/Quill/Pell's workbench, and the COLD DOOR in the east wall (iron service door, carved stone frame, threshold glyph on
the lintel, the anchor stone in the right-hand jamb, frost rime and a low cold mist). The snowy exterior strip beyond the door is a
separate model (ossuary_cold_door_exterior.py) so it can be hidden.
Coordinates: feet from the NW corner (x east, y south) converted by P(); model x east, y north. Two tiny corner markers pin the
bounding box to (-0.1, 0.1) .. (13.816, -9.244) m so the exterior tile can be placed exactly beside it.
"""
from _props import F, Shop
from _runes import put

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Session 14 Scene 7. Entry west (from the shafts' south dogleg). Pell's terminal NW; the cold door east (anchor stone in its south jamb)."

FT = 0.3048
W_FT, H_FT = 45.0, 30.0
T, H = 0.45, 3.4


def P(x, y):
    return x * FT, -y * FT


# lights in model metres (pre-centring); run.py shifts them. 3 lights max per spec.
LIGHTS = [
    dict(x=12 * FT, y=-6 * FT, z=2.6, dim=22, bright=6, color="#ffc78a"),                          # dim lamp over the terminal
    dict(x=45 * FT - T - 0.2, y=-18 * FT, z=1.0, dim=6, bright=2, color="#9fd0ff", hidden=True),   # anchor stone glow: off until T1
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    frost = k.mat("frost_rime", (0.78, 0.86, 0.95), roughness=0.35)
    mist = k.mat("cold_mist", (0.70, 0.78, 0.88), roughness=1.0)
    dust = k.mat("dust", (0.42, 0.40, 0.36), roughness=1.0)

    def sep(o, name):
        o.name = name
        o["separate"] = 1
        return o

    X1, Y1 = W_FT * FT, -H_FT * FT                       # 13.716, -9.144
    # bbox markers
    B(-0.1, -0.09, 0.09, 0.1, 0, 0.01, M["soot"], "bbox_marker")
    B(X1 + 0.09, X1 + 0.1, Y1 - 0.1, Y1 - 0.09, 0, 0.01, M["soot"], "bbox_marker")

    B(0, X1, Y1, 0, 0, F, M["paving"], "floor")
    ey = -15 * FT
    # walls inside the footprint
    W.wall("y", T / 2, Y1, 0, T, H, [(ey, 1.6, 0, 2.4)], M["ashlar"], name="wall_w")          # entry from the dogleg, 1.6 m
    W.wall("x", -T / 2, T, X1 - T, T, H, [], M["ashlar"], name="wall_n")
    W.wall("x", Y1 + T / 2, T, X1 - T, T, H, [], M["ashlar"], name="wall_s")
    W.wall("y", X1 - T / 2, Y1, 0, T, H, [(ey, 1.6, 0, 2.3)], M["ashlar"], name="wall_e")
    W.frame("y", X1 - T / 2, T, ey, 1.6, 0, 2.3, mat=M["granite"], j=0.2)                     # carved stone frame
    for x in (2.5, 5.5, 8.5, 11.5):
        B(x - 0.15, x + 0.15, Y1 + T, -T, H - 0.35, H - 0.05, M["coak"], "beam", 0.01)

    # THE COLD DOOR: iron service door, 5 ft wide, opens inward (west)
    d = k.door(1.5, 2.25, hinge=(X1 - T / 2, ey + 0.75, F), yaw_deg=-90, swing=(-1, 0), leaf_mat=M["iron"], trim_mat=M["iron"], door_id="cold_door")
    d.name = "Cold_Door"
    # threshold glyph on the lintel (west face), carved dark
    g = put(k, M["soot"], "ingwaz", (X1 - T - 0.22, ey, F + 2.55), "w", h=0.32, width=0.04, thick=0.015)
    sep(B(X1 - T - 0.215, X1 - T - 0.205, ey - 0.35, ey + 0.35, F + 2.38, F + 2.72, M["slate"], "lintel_panel"), "Lintel_Threshold_Glyph")
    # anchor stone: right-hand jamb (south) at waist height, just proud of the wall
    sep(B(X1 - T - 0.24, X1 - T - 0.2, ey - 1.15, ey - 0.85, F + 0.85, F + 1.15, M["granite"], "anchor"), "Anchor_Stone")
    # frost rime around the frame and a low mist pooled at the threshold
    for (y0, y1, z0, z1) in ((ey + 0.82, ey + 0.95, 0.1, 2.6), (ey - 0.95, ey - 0.82, 0.1, 2.6), (ey - 0.95, ey + 0.95, 2.45, 2.62)):
        B(X1 - T - 0.26, X1 - T - 0.23, y0, y1, z0, z1, frost, "frost_rime")
    for i, (dx, dy, r) in enumerate(((-0.5, 0.2, 0.55), (-1.0, -0.4, 0.5), (-1.5, 0.3, 0.45), (-0.7, -0.9, 0.4), (-2.0, -0.1, 0.35))):
        k.sphere(r, loc=(X1 - T + dx, ey + dy, F + 0.04), scale=(1.4, 1.0, 0.12), material=mist, name="cold_mist", segments=10)
    B(X1 - T - 1.2, X1 - T - 0.02, ey - 0.8, ey + 0.8, F, F + 0.012, frost, "frost_floor")

    # THE DUSTY TERMINAL at (12, 6): plinth, brass receiver, cap, pipes up, lever
    tx, ty = P(12, 6)
    B(tx - 0.7, tx + 0.7, ty - 0.45, ty + 0.45, F, F + 0.6, M["granite"], "terminal_plinth", 0.02)
    sep(k.cylinder(0.24, 1.0, loc=(tx, ty, F + 1.1), material=M["brass"], name="t", verts=16), "Dusty_Terminal")
    k.cylinder(0.29, 0.09, loc=(tx, ty, F + 1.64), material=M["brass"], name="terminal_cap", verts=16)
    B(tx - 0.16, tx + 0.16, ty - 0.27, ty - 0.22, F + 0.85, F + 1.2, M["iron"], "capsule_slot")
    for dx in (-0.12, 0.12):                                             # pipes up into the dark
        k.cylinder(0.07, H - 1.7, loc=(tx + dx, ty + 0.05, F + 1.7 + (H - 1.7) / 2), material=M["brass"], name="pipe", verts=10)
    k.cylinder(0.06, 4.0, loc=(tx + 2.0, ty + 0.05, H - 0.2), rot=(0, 90, 0), material=M["brass"], name="pipe_run", verts=10)
    sep(B(tx + 0.5, tx + 0.56, ty - 0.03, ty + 0.03, F + 0.6, F + 1.3, M["iron"], "lever", rot=(0, 18, 0)), "Terminal_Lever")
    k.sphere(0.06, loc=(tx + 0.66, ty, F + 1.3), material=M["iron"], name="lever_knob", segments=8)
    # capsule plinth with a cubby of old capsules
    cx, cy = P(17, 6)
    sep(B(cx - 0.4, cx + 0.4, cy - 0.35, cy + 0.35, F, F + 0.9, M["granite"], "cplinth", 0.02), "Capsule_Plinth")
    for i in range(3):
        k.cylinder(0.06, 0.32, loc=(cx - 0.2 + 0.2 * i, cy - 0.38, F + 0.35), rot=(90, 0, 0), material=M["dbone"], name="old_capsule", verts=10)
    k.cylinder(0.07, 0.34, loc=(cx, cy, F + 0.97), rot=(0, 90, 0), material=M["brass"], name="capsule_on_plinth", verts=12)
    # capsule rack on the west wall and timetable board on the north wall
    S.shelf_unit(T, T + 0.45, -3.2, -1.2, 2.0, "e", rows=4, items="boxes")
    bx, _ = P(24, 0)
    B(bx - 1.0, bx + 1.0, -T - 0.05, -T - 0.01, F + 1.3, F + 2.4, M["board"], "timetable_board")
    for r in range(5):
        B(bx - 0.9, bx + 0.9, -T - 0.07, -T - 0.05, F + 1.4 + 0.2 * r, F + 1.46 + 0.2 * r, M["paper"], "timetable_row")
    # dust on the floor and on the plinth
    for (x, y, sx, sy) in ((10, 9, 1.8, 1.0), (20, 12, 1.2, 0.8), (6, 22, 1.6, 1.1), (26, 4, 1.4, 0.6), (36, 26, 1.0, 0.7)):
        px, py = P(x, y)
        k.sphere(1.0, loc=(px, py, F + 0.002), scale=(sx, sy, 0.006), material=dust, name="dust", segments=10)

    # PELL'S RAIL along the north wall, x 5..30 ft, with his counterweighted chair
    r0, _ = P(5, 0)
    r1, _ = P(30, 0)
    ry = -T - 0.5
    sep(k.cylinder(0.04, r1 - r0, loc=((r0 + r1) / 2, ry, F + 2.0), rot=(0, 90, 0), material=M["iron"], name="rail", verts=8), "Pell_Rail")
    for x in (r0, (r0 + r1) / 2, r1):
        B(x - 0.03, x + 0.03, -T - 0.02, ry + 0.03, F + 1.97, F + 2.03, M["iron"], "rail_bracket")
    chx, _ = P(9, 0)
    S.chair(chx, ry - 0.1, face="n")
    for dx in (-0.18, 0.18):
        B(chx + dx - 0.01, chx + dx + 0.01, ry - 0.01, ry + 0.01, F + 0.95, F + 2.0, M["iron"], "chair_hanger")
    k.cylinder(0.05, 0.12, loc=(chx, ry, F + 2.1), material=M["iron"], name="rail_trolley", verts=8)
    k.cylinder(0.12, 0.35, loc=(chx + 0.55, -T - 0.15, F + 1.2), material=M["iron"], name="counterweight", verts=10)
    B(chx + 0.54, chx + 0.56, -T - 0.16, -T - 0.14, F + 1.38, F + 2.0, M["iron"], "counterweight_chain")

    # WORKBENCH at (30, 24): braided line coil, gorge frost jar, Quill's chisels
    wx, wy = P(30, 24)
    S.table(wx - 1.1, wx + 1.1, wy - 0.45, wy + 0.45, h=0.9, mat=M["doak"])
    sep(B(wx - 1.12, wx + 1.12, wy - 0.47, wy + 0.47, F + 0.96, F + 0.99, M["oak"], "wb_top"), "Workbench")
    sep(k.cylinder(0.24, 0.14, loc=(wx - 0.6, wy, F + 1.06), material=M["linen"], name="coil", verts=16), "Braided_Line_Coil")
    sep(k.cylinder(0.09, 0.24, loc=(wx + 0.1, wy + 0.1, F + 1.11), material=frost, name="jar", verts=12), "Gorge_Frost_Jar")
    k.cylinder(0.07, 0.03, loc=(wx + 0.1, wy + 0.1, F + 1.245), material=M["iron"], name="jar_lid", verts=12)
    for i in range(4):
        B(wx + 0.45 + 0.1 * i, wx + 0.47 + 0.1 * i, wy - 0.25, wy + 0.05, F + 0.99, F + 1.01, M["iron"], "chisel")
    S.stool(wx, wy + 0.85)
    S.crate(*P(40, 4))
    S.crate(*P(41.5, 4), 0.45)
    S.barrel(*P(3, 26))
    S.lantern(tx, ty, H - 0.6, hang=0.4)
    S.finish()
