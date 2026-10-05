"""Brokka "Three-Fingers" Vell's forge, Lower Ossuary market: smith and Essencecrafter. 16 x 11 m interior (about 10 x 7 squares),
4 m ceiling, open top. South street door (double), rear yard door west, big hearth on the north wall, tool wall and essence-vial rack
east, plinth with the old hammer head whose Essence was removed (a Brokka hook in the handoff).
x east, y north.
"""
import math

from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Brokka Vell's forge. Rear door west leads to the yard; the hammer head on the plinth has had an Essence deliberately removed."

IX, IY, T, H = 8.0, 5.5, 0.5, 4.0
HX = -2.5          # hearth centre x

LIGHTS = [
    dict(x=HX, y=4.5, z=0.7, dim=45, bright=20, color="#ff8a2a", anim="torch", emitter=0.015),   # forge fire
    dict(x=-5.5, y=-2.5, z=3.0, dim=30, bright=10, color="#ffb066"),
    dict(x=3.0, y=-2.5, z=3.0, dim=30, bright=10, color="#ffb066"),
    dict(x=3.5, y=2.5, z=3.0, dim=30, bright=10, color="#ffb066"),
    dict(x=7.2, y=3.5, z=1.9, dim=14, bright=5, color="#66ddff"),                                 # essence vials glow
    dict(x=6.4, y=-2.6, z=1.6, dim=10, bright=3, color="#9a8cff"),                                # plinth
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B

    # shell
    B(-IX, IX, -IY, IY, 0, F, M["paving"], "floor")
    south = [(0, 2.0, 0, 2.6), (-5, 1.2, 1.3, 2.7), (5, 1.2, 1.3, 2.7)]
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, south, M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, 0, 2.0, 0, 2.6)
    for x in (-5, 5):
        W.window("x", -IY - T / 2, T, x, w=1.2, sill=1.3, head=2.7)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [], M["ashlar"], name="ext")
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [(-2.5, 1.0, 0, 2.3)], M["ashlar"], name="ext")
    W.frame("y", -IX - T / 2, T, -2.5, 1.0, 0, 2.3)
    W.wall("y", IX + T / 2, -IY, IY, T, H, [(-3.5, 1.2, 1.3, 2.7)], M["ashlar"], name="ext")
    W.window("y", IX + T / 2, T, -3.5, w=1.2, sill=1.3, head=2.7)
    for x in (-6, -3, 0, 3, 6):                                            # ceiling beams
        B(x - 0.16, x + 0.16, -IY, IY, H - 0.45, H - 0.05, M["coak"], "beam", 0.01)

    S.door("street_left", "x", -IY - T / 2, -0.5, swing=(0, 1), w=1.0)
    S.door("street_right", "x", -IY - T / 2, 0.5, swing=(0, 1), w=1.0, hinge_low=False)
    S.door("yard", "y", -IX - T / 2, -2.5, swing=(1, 0), w=1.0)

    # hearth on the north wall, with a tapering hood and chimney
    B(HX - 2.0, HX - 1.0, 3.7, IY, F, H - 0.5, M["granite"], "hearth_jamb")
    B(HX + 1.0, HX + 2.0, 3.7, IY, F, H - 0.5, M["granite"], "hearth_jamb")
    B(HX - 1.0, HX + 1.0, 3.7, IY, F + 1.5, F + 2.0, M["granite"], "hearth_lintel")
    for i, (wd, z0, z1) in enumerate(((1.7, F + 2.0, F + 2.6), (1.3, F + 2.6, F + 3.2), (0.9, F + 3.2, H - 0.5))):
        B(HX - wd, HX + wd, 4.2 + 0.25 * i, IY, z0, z1, M["granite"], "hood")
    B(HX - 1.0, HX + 1.0, 3.7, IY, F, F + 0.35, M["granite"], "hearth_floor")
    B(HX - 1.0, HX + 1.0, IY - 0.05, IY - 0.01, F + 0.35, F + 1.5, M["soot"], "soot")
    S.fire(HX, 4.7, F + 0.35, w=1.5)
    B(HX - 2.4, HX + 2.4, 2.9, 3.7, F, F + 0.1, M["slate"], "hearth_apron")

    # anvil on a log, with a hot bar; bellows, quench trough, grindstone
    S.k.cylinder(0.26, 0.62, loc=(HX, 1.8, F + 0.31), material=M["oak"], name="anvil_log", verts=12)
    B(HX - 0.4, HX + 0.4, 1.8 - 0.1, 1.8 + 0.1, F + 0.62, F + 0.74, M["iron"], "anvil_waist", 0.01)
    B(HX - 0.35, HX + 0.35, 1.8 - 0.14, 1.8 + 0.14, F + 0.74, F + 0.86, M["iron"], "anvil_face", 0.01)
    S.k.cone(0.12, 0.02, 0.35, loc=(HX + 0.55, 1.8, F + 0.8), rot=(0, 90, 0), material=M["iron"], name="anvil_horn", verts=8)
    B(HX - 0.25, HX + 0.15, 1.8 - 0.03, 1.8 + 0.03, F + 0.86, F + 0.9, M["hot"], "hot_bar")
    B(-5.4, -4.4, 4.3, 4.9, F + 0.5, F + 0.6, M["oak"], "bellows_board")
    S.k.cone(0.28, 0.04, 0.7, loc=(-4.9, 4.3, F + 0.9), rot=(-90, 0, 0), material=M["coak"], name="bellows_leather", verts=4)
    B(-5.2, -4.6, 4.9, 5.4, F + 0.2, F + 0.9, M["doak"], "bellows_frame")
    B(0.0, 1.9, 3.5, 4.4, F, F + 0.5, M["granite"], "trough")
    B(0.1, 1.8, 3.6, 4.3, F + 0.42, F + 0.46, M["water"], "trough_water")
    S.k.cylinder(0.42, 0.18, loc=(3.2, 4.8, F + 0.62), rot=(0, 90, 0), material=M["granite"], name="grindstone", verts=18)
    for sx in (-1, 1):
        B(3.2 + sx * 0.14 - 0.04, 3.2 + sx * 0.14 + 0.04, 4.5, 5.1, F, F + 0.62, M["doak"], "grind_frame")

    # east wall: tool racks, essence-vial rack, plinth with the old hammer head, workbench
    B(IX - 0.3, IX, -3.2, 1.5, F + 1.35, F + 1.4, M["oak"], "tool_rail")
    for i in range(12):
        y = -3.0 + i * 0.37
        if i % 3 == 0:                                                       # tongs: two arms
            B(IX - 0.28, IX - 0.22, y - 0.03, y + 0.01, F + 0.6, F + 1.35, M["iron"], "tongs")
            B(IX - 0.28, IX - 0.22, y + 0.01, y + 0.05, F + 0.6, F + 1.35, M["iron"], "tongs")
        else:                                                                # hammers: shaft + head
            B(IX - 0.27, IX - 0.23, y - 0.02, y + 0.02, F + 0.6, F + 1.35, M["oak"], "hammer_shaft")
            B(IX - 0.3, IX - 0.2, y - 0.07, y + 0.07, F + 0.5, F + 0.62, M["iron"], "hammer_head", 0.005)
    S.shelf_unit(IX - 0.5, IX, 2.0, 5.0, 2.4, "w", rows=4, items="vials")
    B(5.9, 6.7, -3.0, -2.2, F, F + 0.9, M["granite"], "plinth", 0.01)
    B(6.0, 6.6, -2.9, -2.3, F + 0.9, F + 1.0, M["iron"], "plinth_cap")
    B(6.15, 6.55, -2.8, -2.4, F + 1.0, F + 1.18, M["iron"], "old_hammer_head", 0.01)
    S.jar(6.45, -2.6, F + 1.18, 2, "glass_b", 1.0)                           # the empty vial: Essence removed
    B(6.0, 6.6, -3.02, -3.0, F + 0.35, F + 0.5, M["plaque"], "plinth_plaque")
    S.table(3.8, 5.6, -0.7, 0.7, h=0.95, mat=M["oak"])
    B(4.2, 4.5, -0.1, 0.2, F + 1.01, F + 1.2, M["iron"], "vise")
    B(5.0, 5.4, -0.4, 0.4, F + 1.01, F + 1.06, M["iron"], "blade_blank")

    # centre: work table with a blade blank; stools; west: coal bin, ingots, crates, barrels
    S.table(-1.5, 0.5, -2.8, -1.9, h=0.85)
    B(-1.2, 0.2, -2.45, -2.25, F + 0.91, F + 0.96, M["iron"], "sword_blank")
    S.stool(-2.2, -2.4)
    S.stool(1.2, -2.4)
    B(-7.6, -6.1, 4.0, 5.3, F, F + 0.9, M["soot"], "coal_bin")
    for i in range(8):
        B(-7.7 + 0.45 * (i % 4), -7.35 + 0.45 * (i % 4), -1.2 + 0.2 * (i // 4), -0.95 + 0.2 * (i // 4), F + 0.1 * (i // 4), F + 0.1 * (i // 4) + 0.1, M["iron"], "ingot")
    S.crate(-7.2, -4.6)
    S.crate(-7.2, -3.9, 0.5)
    S.crate(-6.6, -4.6, 0.5, z=F + 0.01)
    S.barrel(-6.0, -4.6)
    S.barrel(-5.3, -4.8, 0.3, 0.8)
    S.lantern(-5.5, -2.5, 3.0, hang=0.9)
    S.lantern(3.0, -2.5, 3.0, hang=0.9)
    S.lantern(3.5, 2.5, 3.0, hang=0.9)
    # a sign above the street door, inside: Brokka's mark
    B(-0.6, 0.6, -IY + 0.02, -IY + 0.05, F + 2.75, F + 3.15, M["plaque"], "forge_mark")
    S.finish()
