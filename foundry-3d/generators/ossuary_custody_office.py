"""The Night Custody Office (Session 14, Scene 5 Inspector Tallis; Scene 3B Sabeline's approach). Sabeline Nock's office off
The Hallway, where the open-claim page lives. 40 x 30 ft interior (spec: gm-guide/Session_14_Scenes_Spec.md, B2).
  door from The Hallway at (20, 30) in the south wall; ledger stacks (tall shelves of numbered custody volumes) along the north
  and west walls with a rolling ladder on the north wall; Sabeline's desk at (20, 10) with a green-shaded lamp, open ledger,
  pen tray, brass knock-block, tea tin, kettle and the night desk bell; copy table at (32, 18) with two copied volumes;
  two visitor chairs facing the desk; a notice board by the door with blank notice forms; a case clock.
Hidden: one volume on the north shelves is shelved one place out of order (Investigation DC 13); behind it, a folded copied
custody page (the Thaw's copy). Spec coordinates are feet from the NW corner (x east, y south), converted to centred metres.
Named interaction objects are kept as their own glTF nodes (custom property `separate`). No emissive materials.
"""
from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange/Session 14"
SCENE_NOTE = ("Night Custody Office. The open-claim volume is shelved one place out of order on the north shelves "
              "(Investigation DC 13 without Sabeline); behind it, a folded copied custody page (the Thaw's copy).")

WFT, HFT = 40.0, 30.0
FT = 0.3048
IX, IY, T, H = WFT * FT / 2, HFT * FT / 2, 0.5, 3.6


def X(xf):
    return -IX + xf * FT


def Y(yf):
    return IY - yf * FT


LIGHTS = [
    dict(x=X(20.5), y=Y(9.5), z=1.4, dim=22, bright=7, color="#ffd9a0"),   # green-shaded desk lamp, warm
    dict(x=X(20), y=Y(28), z=2.4, dim=14, bright=3, color="#9fb7d6"),      # dim corridor spill by the door
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    M["lamp_green"] = k.mat("lamp_green_glass", (0.05, 0.30, 0.12), roughness=0.25)

    def named(nm, x0, x1, y0, y1, z0, z1, mat, bevel=0.0):
        o = B(x0, x1, y0, y1, z0, z1, mat, nm, bevel)
        o.name = nm
        o["separate"] = 1
        return o

    B(-IX, IX, -IY, IY, 0, F, M["floor_oak"], "floor")
    dx = X(20)
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, [(dx, 1.1, 0, 2.3)], M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, dx, 1.1, 0, 2.3)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [], M["ashlar"], name="ext")
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [], M["ashlar"], name="ext")
    W.wall("y", IX + T / 2, -IY, IY, T, H, [(Y(15), 1.2, 1.3, 2.5)], M["ashlar"], name="ext")
    W.window("y", IX + T / 2, T, Y(15), w=1.2, sill=1.3, head=2.5)
    for xf in (10, 20, 30):
        B(X(xf) - 0.15, X(xf) + 0.15, -IY, IY, H - 0.4, H - 0.05, M["coak"], "beam", 0.01)
    S.door("Office_Door", "x", -IY - T / 2, dx, swing=(0, 1), w=1.1)

    # ledger stacks: tall shelves of custody volumes along the north and west walls
    D = 0.45
    S.shelf_unit(X(1.5), X(19), IY - D, IY, 2.9, "s", rows=6, items="books")
    S.shelf_unit(X(21), X(38.5), IY - D, IY, 2.9, "s", rows=6, items="books")
    S.shelf_unit(-IX, -IX + D, Y(26), Y(1.5), 2.9, "e", rows=6, items="books")
    named("Custody_Shelves", X(19), X(21), IY - D, IY, F, F + 2.9, M["doak"], 0.01)   # centre bay end panel / label post
    B(X(19.4), X(20.6), IY - D - 0.02, IY - D, F + 1.6, F + 1.8, M["brass"], "shelf_label_plate")
    # the out-of-order volume (open claim) on the north shelves: a red volume a hand proud of its neighbours
    named("Open_Claim_Volume_Misshelved", X(12.1), X(12.5), IY - D - 0.24, IY - D - 0.02, F + 1.11, F + 1.42, M["red"])
    # rolling ladder on the north wall (rail + leaning ladder)
    B(X(2), X(38), IY - 0.06, IY - 0.02, F + 2.6, F + 2.66, M["brass"], "ladder_rail")
    lx = X(26)
    named("Rolling_Ladder", lx - 0.24, lx - 0.19, IY - D - 0.7, IY - D - 0.1, F, F + 2.6, M["oak"])
    B(lx + 0.19, lx + 0.24, IY - D - 0.7, IY - D - 0.1, F, F + 2.6, M["oak"], "ladder_side")
    for r in range(8):
        yy = IY - D - 0.68 + r * 0.075
        B(lx - 0.19, lx + 0.19, yy - 0.02, yy + 0.02, F + 0.25 + r * 0.3, F + 0.29 + r * 0.3, M["oak"], "ladder_rung")
    for sx in (-0.21, 0.21):
        k.cylinder(0.04, 0.03, loc=(lx + sx, IY - D - 0.65, F + 0.04), rot=(0, 90, 0), material=M["iron"], name="ladder_wheel", verts=10)

    # Sabeline's desk at (20, 10)
    ex, ey = X(20), Y(10)
    named("Sabeline_Desk", ex - 1.0, ex + 1.0, ey - 0.45, ey + 0.45, F + 0.76, F + 0.82, M["doak"], 0.01)
    B(ex - 0.98, ex - 0.55, ey - 0.43, ey + 0.43, F, F + 0.76, M["doak"], "desk_pedestal")
    B(ex + 0.55, ex + 0.98, ey - 0.43, ey + 0.43, F, F + 0.76, M["doak"], "desk_pedestal")
    B(ex - 0.55, ex + 0.55, ey + 0.38, ey + 0.43, F + 0.3, F + 0.76, M["doak"], "desk_modesty")
    top = F + 0.82
    named("Open_Claim_Ledger", ex - 0.3, ex + 0.3, ey - 0.2, ey + 0.2, top, top + 0.04, M["paper"])
    B(ex - 0.01, ex + 0.01, ey - 0.2, ey + 0.2, top + 0.04, top + 0.05, M["navy"], "ledger_gutter")
    B(ex + 0.4, ex + 0.7, ey - 0.25, ey - 0.13, top, top + 0.03, M["brass"], "pen_tray")
    B(ex + 0.45, ex + 0.65, ey - 0.21, ey - 0.17, top + 0.03, top + 0.04, M["soot"], "pens")
    B(ex - 0.75, ex - 0.6, ey - 0.3, ey - 0.15, top, top + 0.1, M["brass"], "knock_block")
    k.cylinder(0.05, 0.12, loc=(ex - 0.8, ey + 0.2, top + 0.06), material=M["red"], name="tea_tin", verts=10)
    k.cylinder(0.1, 0.16, loc=(ex - 0.55, ey + 0.22, top + 0.08), material=M["iron"], name="kettle", verts=12)
    k.cylinder(0.015, 0.1, loc=(ex - 0.43, ey + 0.22, top + 0.12), rot=(0, 60, 0), material=M["iron"], name="kettle_spout", verts=6)
    bell = k.cylinder(0.06, 0.07, loc=(ex + 0.78, ey + 0.02, top + 0.035), material=M["brass"], name="Night_Desk_Bell", verts=12)
    bell.name = "Night_Desk_Bell"
    bell["separate"] = 1
    k.sphere(0.06, loc=(ex + 0.78, ey + 0.02, top + 0.09), material=M["brass"], name="bell_dome", segments=8)
    # green-shaded lamp
    k.cylinder(0.08, 0.03, loc=(ex + 0.5, ey + 0.25, top + 0.015), material=M["brass"], name="lamp_foot", verts=10)
    k.cylinder(0.012, 0.35, loc=(ex + 0.5, ey + 0.25, top + 0.2), material=M["brass"], name="lamp_stem", verts=6)
    B(ex + 0.3, ex + 0.7, ey + 0.17, ey + 0.33, top + 0.33, top + 0.43, M["lamp_green"], "lamp_shade", 0.02)
    S.chair(ex, Y(7), face="n")                    # Sabeline's chair, behind the desk
    S.chair(X(17), Y(14), face="s")                # two visitor chairs facing the desk
    S.chair(X(23), Y(14), face="s")
    S.rug(X(14), X(26), Y(18), Y(6), M["navy"], M["linen"])

    # copy table at (32, 18): two copied volumes side by side, each open at the claim
    cx, cy = X(32), Y(18)
    S.table(cx - 1.1, cx + 1.1, cy - 0.5, cy + 0.5, h=0.78, mat=M["oak"])
    named("Copy_Table", cx - 1.1, cx + 1.1, cy - 0.5, cy + 0.5, F + 0.84, F + 0.86, M["oak"])
    for vx in (cx - 0.45, cx + 0.45):
        B(vx - 0.32, vx + 0.32, cy - 0.22, cy + 0.22, F + 0.86, F + 0.9, M["paper"], "copied_volume")
        B(vx - 0.01, vx + 0.01, cy - 0.22, cy + 0.22, F + 0.9, F + 0.91, M["green"], "volume_gutter")
    k.cylinder(0.04, 0.08, loc=(cx, cy + 0.32, F + 0.9), material=M["soot"], name="inkwell", verts=8)
    S.chair(cx, Y(20.5), face="s")

    # notice board by the door, on the south wall (inner face y = -IY), with blank notice forms (Tallis's)
    nx0, nx1 = X(24), X(28)
    named("Notice_Board", nx0, nx1, -IY + 0.01, -IY + 0.06, F + 1.2, F + 2.2, M["oak"])
    for i in range(5):
        x0 = nx0 + 0.1 + i * 0.22
        B(x0, x0 + 0.18, -IY + 0.06, -IY + 0.08, F + 1.45 + 0.08 * (i % 2), F + 1.85 + 0.08 * (i % 2), M["paper"], "notice_form")
    # case clock in the north-east corner, filing cabinet in the south-east
    B(IX - 0.55, IX - 0.05, IY - 0.45 - 0.5, IY - 0.45 - 0.05, F, F + 2.1, M["doak"], "case_clock", 0.01)
    k.cylinder(0.17, 0.02, loc=(IX - 0.3, IY - 0.96, F + 1.75), rot=(90, 0, 0), material=M["paper"], name="clock_face", verts=14)
    S.cabinet(IX - 0.5, IX, Y(26), Y(21), 1.3, face="w")
    S.finish()
