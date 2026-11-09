"""Session 14, B4: Ropewalk and Signal Loft (80 x 30 ft, two levels). Spec: gm-guide/Session_14_Scenes_Spec.md B4.
Haddo Rook's ropewalk: a long east-west rope-maker's floor with the twisting wheel at the west end, T-posts carrying strands
down the walk, a traveller sledge on rails down the middle, rope coils and tar buckets, Haddo's workbench and a bench of four
iron bars. Nan Gristle's signal loft: a timber gallery 10 ft deep along the north wall at the east end (x 50..80 ft) at 2.8 m,
reached by a ladder at (50, 10), with her chair, the signal bell on a post, a line of signal flags, a speaking trumpet, and a
window onto the trolley rails (a short length of the trolley cable runs past outside). Big double doors south at (40, 30) to the market.
Coordinates: feet from the NW corner (x east, y south) via P(); model x east, y north.
"""
import math

from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Session 14 Ropewalk. Haddo at the twisting wheel (W) or his bench; Nan in the loft (NE, ladder at 50,10). Market doors south."

FT = 0.3048
X1, Y1 = 80 * FT, -30 * FT
T, H, LZ = 0.4, 5.6, 2.8          # wall thickness, wall height, loft floor height


def P(x, y):
    return x * FT, -y * FT


LIGHTS = [
    dict(x=20 * FT, y=-15 * FT, z=4.2, dim=34, bright=12, color="#ffc78a"),
    dict(x=55 * FT, y=-18 * FT, z=4.2, dim=34, bright=12, color="#ffc78a"),
    dict(x=74 * FT, y=-3 * FT, z=LZ + 1.8, dim=20, bright=7, color="#ffe6b8"),     # by Nan's window
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    rope = k.mat("rope_hemp", (0.55, 0.45, 0.28), roughness=0.95)
    tar = k.mat("tar", (0.03, 0.025, 0.02), roughness=0.3)
    flag_cols = (M["red"], k.mat("flag_yellow", (0.75, 0.6, 0.1), roughness=0.9), M["navy"], M["linen"], M["green"])

    def sep(o, name):
        o.name = name
        o["separate"] = 1
        return o

    B(0, X1, Y1, 0, 0, F, M["floor_oak"], "floor")
    dx, _ = P(40, 0)
    W.wall("x", -T / 2, 0, X1, T, H, [(P(75, 0)[0], 1.4, LZ + 1.0, LZ + 2.2), (P(20, 0)[0], 1.4, 2.4, 3.6)], M["ashlar"], name="wall_n")
    W.window("x", -T / 2, T, P(75, 0)[0], w=1.4, sill=LZ + 1.0, head=LZ + 2.2)
    W.window("x", -T / 2, T, P(20, 0)[0], w=1.4, sill=2.4, head=3.6)
    W.wall("x", Y1 + T / 2, 0, X1, T, H, [(dx, 2.6, 0, 3.0), (P(12, 0)[0], 1.2, 1.4, 2.6), (P(66, 0)[0], 1.2, 1.4, 2.6)], M["ashlar"], name="wall_s")
    W.frame("x", Y1 + T / 2, T, dx, 2.6, 0, 3.0)
    for x in (12, 66):
        W.window("x", Y1 + T / 2, T, P(x, 0)[0], w=1.2, sill=1.4, head=2.6)
    W.wall("y", T / 2, Y1 + T, -T, T, H, [], M["ashlar"], name="wall_w")
    W.wall("y", X1 - T / 2, Y1 + T, -T, T, H, [], M["ashlar"], name="wall_e")
    for x in range(5, 80, 10):                                              # roof tie beams
        px, _ = P(x, 0)
        B(px - 0.15, px + 0.15, Y1 + T, -T, H - 0.4, H - 0.1, M["coak"], "tie_beam", 0.01)
    # market doors (double, 2.6 m)
    S.door("market_left", "x", Y1 + T / 2, dx - 0.65, swing=(0, 1), w=1.3, h=2.9)
    S.door("market_right", "x", Y1 + T / 2, dx + 0.65, swing=(0, 1), w=1.3, h=2.9, hinge_low=False)
    sep(B(dx - 1.3, dx + 1.3, Y1 + T + 0.02, Y1 + T + 0.04, 3.05, 3.25, M["oak"], "doors_sign"), "Market_Doors")

    # TWISTING WHEEL at (5, 15): a big upright wheel with hooks, on an A-frame
    wx, wy = P(5, 15)
    sep(k.cylinder(1.0, 0.12, loc=(wx, wy, F + 1.35), rot=(0, 90, 0), material=M["doak"], name="wheel", verts=24), "Twisting_Wheel")
    k.cylinder(0.16, 0.5, loc=(wx, wy, F + 1.35), rot=(0, 90, 0), material=M["iron"], name="wheel_hub", verts=10)
    for i in range(6):
        a = math.radians(30 + 60 * i)
        k.cylinder(0.025, 0.25, loc=(wx + 0.18, wy + 0.65 * math.cos(a), F + 1.35 + 0.65 * math.sin(a)), rot=(0, 90, 0), material=M["iron"], name="wheel_hook", verts=6)
    for dy in (-0.7, 0.7):
        B(wx - 0.35, wx - 0.2, wy + dy - 0.07, wy + dy + 0.07, F, F + 1.5, M["doak"], "wheel_frame", rot=(0, 0, 0))
    B(wx - 0.35, wx - 0.2, wy - 0.77, wy + 0.77, F + 1.42, F + 1.52, M["doak"], "wheel_axle_beam")
    k.cylinder(0.04, 0.9, loc=(wx - 0.3, wy + 0.95, F + 1.35), rot=(0, 90, 0), material=M["doak"], name="wheel_crank", verts=6)

    # rails down the middle and the TRAVELLER SLEDGE
    r0, _ = P(9, 0)
    r1, _ = P(72, 0)
    for dy in (-0.45, 0.45):
        B(r0, r1, wy + dy - 0.04, wy + dy + 0.04, F, F + 0.06, M["iron"], "sledge_rail")
    sx, _ = P(36, 0)
    sep(B(sx - 0.6, sx + 0.6, wy - 0.6, wy + 0.6, F + 0.06, F + 0.4, M["coak"], "sledge", 0.02), "Traveller_Sledge")
    B(sx - 0.65, sx - 0.55, wy - 0.4, wy + 0.4, F + 0.4, F + 1.3, M["doak"], "sledge_upright")
    for i in range(3):
        k.cylinder(0.025, 0.2, loc=(sx - 0.7, wy - 0.25 + 0.25 * i, F + 1.2), rot=(0, 90, 0), material=M["iron"], name="sledge_hook", verts=6)
    # rope strands from the wheel to the sledge, carried on T-posts every 10 ft
    for i in range(3):
        y = wy - 0.25 + 0.25 * i
        k.cylinder(0.018, sx - 0.7 - wx - 0.2, loc=((wx + 0.2 + sx - 0.7) / 2, y, F + 1.25), rot=(0, 90, 0), material=rope, name="strand", verts=6)
    for x in range(15, 75, 10):
        px, _ = P(x, 0)
        B(px - 0.06, px + 0.06, wy + 1.0 - 0.06, wy + 1.0 + 0.06, F, F + 1.3, M["doak"], "t_post")
        B(px - 0.05, px + 0.05, wy - 0.5, wy + 1.06, F + 1.3, F + 1.38, M["doak"], "t_post_arm")
        for j in range(4):
            k.cylinder(0.015, 0.1, loc=(px, wy - 0.4 + 0.3 * j, F + 1.42), material=M["iron"], name="t_post_peg", verts=6)

    # rope coils, tar buckets, a tar kettle
    for (x, y, r) in ((3, 4, 0.45), (6, 4, 0.35), (3, 26, 0.5), (20, 27, 0.4), (30, 27, 0.4), (45, 4, 0.45)):
        px, py = P(x, y)
        for j in range(3):
            k.cylinder(r - 0.06 * j, 0.09, loc=(px, py, F + 0.045 + 0.09 * j), material=rope, name="rope_coil", verts=16)
    for (x, y) in ((10, 27), (11.5, 27.5), (25, 3)):
        px, py = P(x, y)
        k.cylinder(0.2, 0.35, loc=(px, py, F + 0.175), material=M["oak"], name="tar_bucket", verts=12)
        k.cylinder(0.18, 0.02, loc=(px, py, F + 0.34), material=tar, name="tar", verts=12)
    S.barrel(*P(14, 27), r=0.35, h=0.9)

    # HADDO'S WORKBENCH at (60, 8) and the IRON BAR BENCH at (70, 22)
    hx, hy = P(60, 8)
    S.table(hx - 1.2, hx + 1.2, hy - 0.4, hy + 0.4, h=0.9, mat=M["doak"])
    sep(B(hx - 1.22, hx + 1.22, hy - 0.42, hy + 0.42, F + 0.96, F + 0.99, M["oak"], "hw_top"), "Haddo_Workbench")
    for j in range(2):
        k.cylinder(0.22 - 0.05 * j, 0.08, loc=(hx - 0.6, hy, F + 1.03 + 0.08 * j), material=rope, name="braid_coil", verts=14)
    B(hx + 0.2, hx + 0.8, hy - 0.05, hy + 0.05, F + 0.99, F + 1.02, rope, "braid_in_progress")
    S.stool(hx, hy - 0.8)
    bx, by = P(70, 22)
    S.bench(bx - 1.0, bx + 1.0, by - 0.3, by + 0.3, h=0.7)
    for i in range(4):
        sep(B(bx - 0.6, bx + 0.6, by - 0.22 + 0.14 * i, by - 0.16 + 0.14 * i, F + 0.75, F + 0.81, M["iron"], "bar"), f"Iron_Bar_{i + 1}")
    sep(B(bx - 1.0, bx + 1.0, by - 0.31, by - 0.29, F + 0.5, F + 0.7, M["doak"], "bench_apron"), "Iron_Bar_Bench")

    # THE SIGNAL LOFT: x 50..80 ft, y 0..10 ft, floor at LZ
    l0, _ = P(50, 0)
    _, ly = P(0, 10)
    B(l0, X1 - T, ly, -T, LZ - 0.12, LZ, M["floor_oak"], "loft_floor")
    for x in (50, 60, 70, 79):
        px, _ = P(x, 0)
        px = min(px, X1 - T - 0.1)
        B(px - 0.1, px + 0.1, ly - 0.1, ly + 0.1, F, LZ - 0.12, M["doak"], "loft_post")
    B(l0, X1 - T, ly - 0.05, ly + 0.05, LZ + 0.95, LZ + 1.02, M["doak"], "loft_rail")
    for i in range(16):
        px = l0 + 0.3 + i * (X1 - T - l0 - 0.6) / 15
        if abs(px - l0 - 0.6) < 0.5:
            continue                                                     # gap at the ladder head
        B(px - 0.025, px + 0.025, ly - 0.025, ly + 0.025, LZ, LZ + 0.95, M["doak"], "loft_baluster")
    # ladder at (50, 10), leaning from the floor up to the loft edge
    lx = l0 + 0.6
    lad = []
    for ddx in (-0.25, 0.25):
        lad.append(B(lx + ddx - 0.03, lx + ddx + 0.03, ly - 0.06, ly + 0.06, F, LZ + 0.9, M["oak"], "ladder_rail", rot=(-12, 0, 0)))
    sep(B(lx - 0.25, lx + 0.25, ly - 0.45, ly - 0.42, F + 0.2, F + 0.24, M["oak"], "ladder_foot"), "Loft_Ladder")
    for j in range(9):
        z = F + 0.3 * (j + 1)
        B(lx - 0.25, lx + 0.25, ly - 0.42 + 0.064 * (j + 1) * 1.0, ly - 0.39 + 0.064 * (j + 1) * 1.0, z - 0.02, z + 0.02, M["oak"], "ladder_rung")
    # Nan's chair, the signal bell on a post at (72, 4), flags, trumpet
    nx, ny = P(74, 3)
    B(nx - 0.25, nx + 0.25, ny - 0.25, ny + 0.25, LZ + 0.42, LZ + 0.48, M["oak"], "nan_chair_seat", 0.01)
    B(nx - 0.25, nx + 0.25, ny - 0.3, ny - 0.25, LZ + 0.48, LZ + 1.05, M["oak"], "nan_chair_back", 0.01)
    for lx2 in (-0.21, 0.21):
        for ly2 in (-0.21, 0.21):
            B(nx + lx2 - 0.025, nx + lx2 + 0.025, ny + ly2 - 0.025, ny + ly2 + 0.025, LZ, LZ + 0.42, M["doak"], "nan_chair_leg")
    bx2, by2 = P(72, 4)
    B(bx2 - 0.06, bx2 + 0.06, by2 - 0.06, by2 + 0.06, LZ, LZ + 1.6, M["doak"], "bell_post")
    B(bx2 - 0.06, bx2 + 0.35, by2 - 0.04, by2 + 0.04, LZ + 1.55, LZ + 1.62, M["doak"], "bell_arm")
    sep(k.cone(0.2, 0.08, 0.3, loc=(bx2 + 0.28, by2, LZ + 1.37), material=M["brass"], name="bell", verts=16), "Signal_Bell")
    k.cone(0.12, 0.03, 0.5, loc=(nx + 0.5, ny + 0.2, LZ + 0.85), rot=(0, 90, 0), material=M["brass"], name="speaking_trumpet", verts=12)
    for i in range(7):                                                   # signal flags on a line along the loft
        fx = l0 + 1.0 + i * 0.9
        B(fx - 0.2, fx + 0.2, -T - 0.08, -T - 0.06, LZ + 1.7, LZ + 2.05, flag_cols[i % 5], "signal_flag")
    B(l0 + 0.8, l0 + 7.2, -T - 0.08, -T - 0.06, LZ + 2.06, LZ + 2.08, rope, "flag_line")
    # mark the chair as part of the loft: lift it (chair() builds at floor F, so add a seat block at loft height instead)
    wnx, _ = P(75, 0)
    sep(B(wnx - 0.75, wnx + 0.75, -T - 0.04, -T - 0.02, LZ + 0.95, LZ + 1.0, M["oak"], "window_sill"), "Signal_Window")
    # the trolley cable outside the loft window (a short visible run)
    k.cylinder(0.03, 4.0, loc=(wnx, 0.5, LZ + 2.4), rot=(0, 90, 0), material=M["iron"], name="trolley_cable", verts=6)
    S.finish()
