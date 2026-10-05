"""The Exchange's conveyor shafts and the Lost Property annex (Quest 2, "Gerald Has the Notebook"). Open-top corridors, 1.6 m wide:
  west   cellar chamber under the bar: the brass drop-tube comes down here into a basket carrier
  main   shaft east (rails, brass pipes, fungus lining; Violet can read where it was crushed)
  north  a dead-end branch (grate)
  south  the dusty old terminal (the "note lead", regular single clunk; never Gerald): a side chamber with the old terminal
  east   the annex: a caged lost-and-found, shelves of unclaimed remains with expired tags; Gerald nests on the far shelf with the notebook
Gate to the annex is a real swinging door. x east, y north.
"""
import math
import random

from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Shafts. Gerald's noise is erratic; the terminal south clunks once, on schedule, and is NOT him."

H, T = 2.6, 0.4

LIGHTS = [
    dict(x=-9.5, y=0, z=1.8, dim=25, bright=8, color="#7fffa0"),            # cellar chamber (fungus glow)
    dict(x=0, y=0, z=1.6, dim=18, bright=5, color="#7fffa0"),
    dict(x=8, y=0, z=1.6, dim=18, bright=5, color="#7fffa0"),
    dict(x=4, y=5, z=1.6, dim=14, bright=4, color="#7fffa0"),
    dict(x=4, y=-6, z=1.6, dim=14, bright=4, color="#9ac4ff"),
    dict(x=4, y=-9.5, z=1.8, dim=22, bright=7, color="#a8b8d0"),            # the dusty terminal
    dict(x=17.5, y=0, z=2.2, dim=40, bright=14, color="#ffc78a"),           # annex lantern
    dict(x=20.5, y=2.5, z=1.6, dim=16, bright=5, color="#ffa24d"),          # Gerald's shelf
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    rng = random.Random(11)
    wall_mat = M["ashlar"]

    def floor(x0, x1, y0, y1):
        B(x0, x1, y0, y1, 0, F, M["paving"], "floor")

    # floors
    floor(-12.2, -7.0, -3.2, 3.2)          # cellar chamber
    floor(-7.0, 13.0, -0.8, 0.8)           # main shaft
    floor(3.2, 4.8, 0.8, 9.2)              # north branch
    floor(3.2, 4.8, -8.2, -0.8)            # south branch
    floor(1.2, 6.8, -11.4, -8.2)           # terminal chamber
    floor(13.0, 22.2, -4.4, 4.4)           # annex

    # walls (open top)
    W.wall("y", -12.4, -3.4, 3.4, T, H, [], wall_mat, name="wall")                      # chamber west
    W.wall("x", 3.4, -12.4, -6.8, T, H, [], wall_mat, name="wall")                     # chamber north
    W.wall("x", -3.4, -12.4, -6.8, T, H, [], wall_mat, name="wall")                    # chamber south
    W.wall("y", -6.9, -3.4, 3.4, T, H, [(0, 1.6, 0, 2.2)], wall_mat, name="wall")      # chamber east, opening into the shaft
    W.wall("x", 1.0, -6.8, 13.0, T, H, [(4, 1.6, 0, H)], wall_mat, name="wall")         # shaft north wall, branch opening
    W.wall("x", -1.0, -6.8, 13.0, T, H, [(4, 1.6, 0, H)], wall_mat, name="wall")        # shaft south wall, branch opening
    W.wall("y", 3.0, 1.0, 9.4, T, H, [], wall_mat, name="wall")                         # north branch walls
    W.wall("y", 5.0, 1.0, 9.4, T, H, [], wall_mat, name="wall")
    W.wall("x", 9.4, 2.8, 5.2, T, H, [], wall_mat, name="wall")                         # north branch end
    W.wall("y", 3.0, -8.0, -1.0, T, H, [], wall_mat, name="wall")                       # south branch walls
    W.wall("y", 5.0, -8.0, -1.0, T, H, [], wall_mat, name="wall")
    W.wall("y", 1.0, -11.6, -8.0, T, H, [], wall_mat, name="wall")                      # terminal chamber walls
    W.wall("y", 7.0, -11.6, -8.0, T, H, [], wall_mat, name="wall")
    W.wall("x", -11.6, 0.8, 7.2, T, H, [], wall_mat, name="wall")
    W.wall("x", -8.0, 0.8, 3.0, T, H, [], wall_mat, name="wall")
    W.wall("x", -8.0, 5.0, 7.2, T, H, [], wall_mat, name="wall")
    W.wall("x", 4.6, 12.8, 22.4, T, H, [], wall_mat, name="wall")                       # annex north / south / east
    W.wall("x", -4.6, 12.8, 22.4, T, H, [], wall_mat, name="wall")
    W.wall("y", 22.4, -4.8, 4.8, T, H, [], wall_mat, name="wall")

    # the cage between the shaft and the annex (x = 13), a door in it
    for y in [-4.4 + 0.13 * i for i in range(67)]:
        if abs(y) < 0.55:
            continue
        B(13.0 - 0.012, 13.0 + 0.012, y - 0.012, y + 0.012, F, H - 0.2, M["iron"], "cage_bar")
    B(12.97, 13.03, -4.4, 4.4, H - 0.25, H - 0.2, M["iron"], "cage_top_rail")
    B(12.97, 13.03, -4.4, 4.4, F + 0.7, F + 0.75, M["iron"], "cage_mid_rail")
    B(12.97, 13.03, -0.55, 0.55, H - 0.45, H - 0.4, M["iron"], "gate_lintel")
    S.door("annex_gate", "y", 13.0, 0, swing=(1, 0), w=1.1, h=2.15)

    # cellar chamber: the drop-tube comes down into a basket carrier
    S.k.cylinder(0.2, 2.4, loc=(-9.5, 0, F + 1.4), material=M["brass"], name="drop_tube", verts=14)
    S.k.cylinder(0.32, 0.12, loc=(-9.5, 0, F + 0.3), material=M["brass"], name="tube_flare", verts=14)
    B(-10.0, -9.0, -0.35, 0.35, F + 0.04, F + 0.3, M["dbone"], "basket_carrier", 0.01)
    B(-10.05, -8.95, -0.4, 0.4, F + 0.28, F + 0.34, M["iron"], "basket_rim")
    S.crate(-11.4, 2.3)
    S.crate(-11.4, -2.3, 0.5)
    S.barrel(-11.2, 0.8)
    # rails, sleepers and brass pipes along the main shaft
    for sy in (-0.3, 0.3):
        B(-7.0, 13.0, sy - 0.03, sy + 0.03, F, F + 0.07, M["iron"], "rail")
    for x in [-6.8 + 0.5 * i for i in range(40)]:
        B(x - 0.06, x + 0.06, -0.55, 0.55, F, F + 0.03, M["doak"], "sleeper")
    for sy in (-0.7, 0.7):
        S.k.cylinder(0.08, 19.6, loc=(3, sy, H - 0.45), rot=(0, 90, 0), material=M["brass"], name="pipe", verts=10)
        for x in [-6 + 2.5 * i for i in range(8)]:
            B(x - 0.03, x + 0.03, sy - 0.1 if sy < 0 else sy - 0.0, sy + 0.0 if sy < 0 else sy + 0.1, H - 0.55, H - 0.2, M["iron"], "pipe_clamp")
    # fungus lining (emissive patches on the inner wall faces); a few crushed (dark) near the floor where something small passed
    for i in range(46):
        x = rng.uniform(-6.5, 12.5)
        north = rng.random() < 0.5
        z = rng.uniform(0.6, 2.0)
        if abs(x - 4) < 1.0:
            continue
        S.k.sphere(rng.uniform(0.08, 0.2), loc=(x, 0.8 if north else -0.8, F + z), scale=(1.2, 0.35, 0.8), material=M["fungus"], name="fungus", segments=7)
    for i in range(6):
        S.k.sphere(0.12, loc=(-3 + 1.9 * i, 0.8 if i % 2 else -0.8, F + 0.25), scale=(1.4, 0.3, 0.5), material=M["soot"], name="crushed_fungus", segments=7)
    # a few wet small footprints along the south wall (Gerald)
    for i in range(10):
        B(-5 + 1.1 * i, -4.9 + 1.1 * i, -0.55 - 0.05 * (i % 2), -0.5 - 0.05 * (i % 2), F + 0.004, F + 0.009, M["water"], "wet_print")
    # north branch: a grate at the dead end
    for x in [3.15 + 0.12 * i for i in range(14)]:
        B(x - 0.012, x + 0.012, 9.2, 9.32, F, H - 0.4, M["iron"], "grate_bar")
    B(3.1, 4.9, 9.2, 9.32, F + 1.0, F + 1.05, M["iron"], "grate_rail")

    # the dusty old terminal (the note lead): a capsule terminal under cobwebs, on no active route
    B(3.3, 4.7, -11.2, -10.4, F, F + 0.6, M["granite"], "terminal_plinth", 0.02)
    S.k.cylinder(0.22, 0.9, loc=(4.0, -10.8, F + 1.05), material=M["brass"], name="terminal_barrel", verts=14)
    S.k.cylinder(0.26, 0.08, loc=(4.0, -10.8, F + 1.55), material=M["brass"], name="terminal_cap", verts=14)
    B(3.8, 4.2, -10.55, -10.45, F + 0.8, F + 1.1, M["iron"], "capsule_slot")
    B(3.85, 4.15, -10.5, -10.4, F + 0.82, F + 1.05, M["dbone"], "capsule")
    for i in range(14):
        B(1.2 + 0.4 * i, 1.22 + 0.4 * i, -11.38, -8.3, F + 0.001, F + 0.004, M["paper"], "dust_streak") if False else None
    for sx in (-1, 1):
        S.k.sphere(0.5, loc=(4.0 + sx * 0.5, -10.9, F + 1.9), scale=(1, 0.5, 0.6), material=M["linen"], name="cobweb", segments=6)

    # annex: shelves of unclaimed remains with expired tags, a ledger table, Gerald's nest on the far shelf with the notebook
    for y in (-3.2, 3.0):
        S.shelf_unit(14.2, 21.0, y - 0.2, y + 0.2, 2.4, "s" if y > 0 else "n", rows=4, items="boxes")
    for x in (14.6, 16.3, 18.0, 19.7):
        for y, f in ((-3.25, "n"), (3.05, "s")):
            for i in range(3):
                B(x + 0.05 * i, x + 0.05 * i + 0.04, y + (0.28 if f == "n" else -0.28) - 0.0, y + (0.3 if f == "n" else -0.3), F + 1.1 + 0.4 * i, F + 1.3 + 0.4 * i, M["paper"], "notice_tag")
    S.table(15.5, 17.5, -0.6, 0.6, h=0.9, mat=M["doak"])
    B(15.8, 16.4, -0.3, 0.3, F + 0.96, F + 1.0, M["paper"], "annex_ledger")
    B(16.7, 17.3, -0.2, 0.2, F + 0.96, F + 0.99, M["red"], "annex_stamp")
    B(21.4, 22.2, 1.4, 3.6, F, F + 1.0, M["doak"], "nest_shelf", 0.01)                   # Gerald's nest shelf (east wall)
    for i in range(6):
        B(21.5 + 0.1 * (i % 2), 21.9 + 0.1 * (i % 2), 1.6 + 0.3 * i, 1.85 + 0.3 * i, F + 1.0, F + 1.06, M["linen"], "straw")
    B(21.7, 21.95, 2.4, 2.75, F + 1.06, F + 1.12, M["red"], "pimm_notebook")             # the field notebook
    B(21.45, 21.5, 0.8, 1.2, F + 1.7, F + 1.95, M["plaque"], "notice_board_plate")       # 'NOTICE EXPIRES' board
    for i in range(10):
        S.skulls.add(15.0 + 0.6 * i, 3.0, F + 2.4, face_to=(17.5, 0), s=0.06) if False else None
    S.lantern(17.5, 0, 2.2, hang=0.3)
    S.lantern(20.5, 2.5, 1.7)
    S.finish()
