"""The Exchange's conveyor shafts and the Lost Property annex (Quest 2, "Gerald Has the Notebook"). Open-top corridors, 1.6 m wide:
  west   ENTRANCE: the cellar chamber under the bar. The brass drop-tube comes down here and the hanging rail starts under it,
         with a low basket the party climbs into. A feeder track from the bar side joins the tube over the north wall and a bright lantern marks the way in.
  main   shaft east (hanging rail, brass pipes, fungus lining; Violet can read where it was crushed)
  north  a long dead-end branch with two corners, ending at a grate
  south  a dogleg (two corners) to the dusty old terminal (the "note lead", regular single clunk; never Gerald)
  east   the annex: a caged lost-and-found, shelves of unclaimed remains with expired tags; Gerald nests on the far shelf
Gate to the annex is a real swinging door. The rail hangs from cross-beams, nothing runs on the floor. x east, y north.
"""
import math
import random

import bpy

from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Shafts. Enter at the west cellar (feeder track and hanging basket on the rail). Gerald's noise is erratic; the terminal clunks once, on schedule, and is NOT him."

H, T, CW = 2.6, 0.4, 0.8          # wall height, wall thickness, corridor half-width
RAIL_Z = 2.0                       # centre height of the hanging rail

LIGHTS = [
    dict(x=-9.9, y=2.8, z=2.2, dim=40, bright=16, color="#ffd18a"),          # ENTRANCE lantern
    dict(x=-9.5, y=0, z=1.8, dim=25, bright=8, color="#7fffa0"),            # cellar chamber (fungus glow)
    dict(x=0, y=0, z=1.6, dim=18, bright=5, color="#7fffa0"),
    dict(x=8, y=0, z=1.6, dim=18, bright=5, color="#7fffa0"),
    dict(x=4, y=5, z=1.6, dim=14, bright=4, color="#7fffa0"),
    dict(x=8, y=8, z=1.6, dim=14, bright=4, color="#7fffa0"),
    dict(x=11, y=11.5, z=1.6, dim=14, bright=4, color="#7fffa0"),
    dict(x=-1, y=-5, z=1.6, dim=14, bright=4, color="#9ac4ff"),
    dict(x=-5, y=-9.5, z=1.8, dim=22, bright=7, color="#a8b8d0"),           # the dusty terminal
    dict(x=17.5, y=3.6, z=2.2, dim=40, bright=14, color="#ffc78a"),           # annex lantern
    dict(x=21.2, y=-2.0, z=1.9, dim=16, bright=5, color="#ffa24d"),          # Gerald's shelf
]


MARKET_GLB = "D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository/foundry-3d/out/orig_market.glb"


def import_market_parts():
    """Pull one conveyor straight and one bone-basket carrier out of the original market model; everything else imported is discarded."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=MARKET_GLB)
    new = [o for o in bpy.data.objects if o not in before]
    straight = next(o for o in new if o.name.startswith("Conveyor_Grid_Row_01_Straight"))
    carrier = next(o for o in new if o.name.startswith("Carrier_Grid_Bone_Basket"))
    parts = {}
    for key, src in (("straight", straight), ("carrier", carrier)):
        o = src.copy()
        o.data = src.data
        o.name = f"tpl_{key}"
        o.matrix_world = src.matrix_world.copy()
        parts[key] = o
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in parts.values():                      # templates only; copies are linked by the caller
        o.parent = None
        o.matrix_parent_inverse.identity()
    return parts


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    rng = random.Random(11)
    wall_mat = M["ashlar"]

    def floor(x0, x1, y0, y1):
        B(x0, x1, y0, y1, 0, F, M["paving"], "floor")

    def sg(v):
        return (v > 0) - (v < 0)

    def corridor(pts, wall_start=0.4, end_cap=True, end_trim=0.0):
        """Axis-aligned corridor through the waypoints, with corners. Floors and walls never overlap each other.
        wall_start: the side walls begin this far past the first point (it sits on the parent shaft's inner wall face)."""
        w = CW
        n = len(pts) - 1
        ds = [(sg(pts[i + 1][0] - pts[i][0]), sg(pts[i + 1][1] - pts[i][1])) for i in range(n)]

        def rect(c, di, do, u0, u1, v0, v1, mat, name, z0=0.0, z1=H):
            xs = [c[0] + di[0] * u + do[0] * v for u in (u0, u1) for v in (v0, v1)]
            ys = [c[1] + di[1] * u + do[1] * v for u in (u0, u1) for v in (v0, v1)]
            B(min(xs), max(xs), min(ys), max(ys), z0, z1, mat, name)

        for i in range(n):
            d = ds[i]
            nrm = (-d[1], d[0])
            s, e = pts[i], pts[i + 1]
            L = abs(e[0] - s[0]) + abs(e[1] - s[1])
            first, last = i == 0, i == n - 1
            rect(s, d, nrm, 0 if first else w, L if last else L - w, -w, w, M["paving"], "floor", 0, F)
            turn = 0 if last else sg(d[0] * ds[i + 1][1] - d[1] * ds[i + 1][0])
            for sig in (-1, 1):
                a = wall_start if first else w
                if last:
                    b = L - end_trim
                else:
                    b = L - (w + T if sig == turn else w)
                v0, v1 = (w, w + T) if sig > 0 else (-w - T, -w)
                if b > a:
                    rect(s, d, nrm, a, b, v0, v1, wall_mat, "wall")
            if last and end_cap:
                rect(s, d, nrm, L, L + T, -w - T, w + T, wall_mat, "wall")
        for i in range(1, n):
            c, di, do = pts[i], ds[i - 1], ds[i]
            rect(c, di, do, -w, w, -w, w, M["paving"], "floor", 0, F)
            rect(c, di, do, -w, w + T, -w - T, -w, wall_mat, "wall")
            rect(c, di, do, w, w + T, -w, w, wall_mat, "wall")

    def wall_lantern(x, y, z, wx, wy):
        """A lantern on a short bracket arm reaching to the wall point (wx, wy)."""
        S.lantern(x, y, z)
        B(min(x, wx) - 0.015, max(x, wx) + 0.015, min(y, wy) - 0.015, max(y, wy) + 0.015, z - 0.1, z - 0.07, M["iron"], "lantern_bracket")

    # floors: cellar chamber (the entrance), main shaft, annex
    floor(-12.2, -7.0, -3.2, 3.2)
    floor(-7.0, 13.0, -0.8, 0.8)
    floor(13.0, 22.2, -4.4, 4.4)
    floor(-7.8, -2.2, -11.4, -8.2)          # terminal chamber

    # walls (open top)
    W.wall("y", -12.4, -3.4, 3.4, T, H, [], wall_mat, name="wall")                      # chamber west
    W.wall("x", 3.4, -12.4, -6.8, T, H, [], wall_mat, name="wall")                     # chamber north
    W.wall("x", -3.4, -12.4, -6.8, T, H, [], wall_mat, name="wall")                    # chamber south
    W.wall("y", -6.9, -3.4, 3.4, T, H, [(0, 1.6, 0, 2.2)], wall_mat, name="wall")      # chamber east, opening into the shaft
    W.wall("x", 1.0, -6.8, 13.0, T, H, [(4, 1.6, 0, H)], wall_mat, name="wall")         # shaft north wall, branch opening
    W.wall("x", -1.0, -6.8, 13.0, T, H, [(4, 1.6, 0, H)], wall_mat, name="wall")        # shaft south wall, branch opening
    W.wall("y", -8.0, -11.6, -8.0, T, H, [], wall_mat, name="wall")                     # terminal chamber west / east / south / north
    W.wall("y", -2.0, -11.6, -8.0, T, H, [], wall_mat, name="wall")
    W.wall("x", -11.6, -8.2, -1.8, T, H, [], wall_mat, name="wall")
    W.wall("x", -8.0, -8.2, -1.8, T, H, [(-5, 1.6, 0, H)], wall_mat, name="wall")
    W.wall("x", 4.6, 12.8, 22.4, T, H, [], wall_mat, name="wall")                       # annex north / south / east
    W.wall("x", -4.6, 12.8, 22.4, T, H, [], wall_mat, name="wall")
    W.wall("y", 22.4, -4.8, 4.8, T, H, [], wall_mat, name="wall")

    # the two dead-end branches, each with corners
    corridor([(4, 0.8), (4, 8), (11, 8), (11, 14), (6, 14)], wall_start=0.4)             # north: long, ends at a grate
    corridor([(4, -0.8), (4, -5), (-5, -5), (-5, -8.2)], wall_start=0.4, end_cap=False, end_trim=0.4)   # south dogleg to the terminal

    # north dead end: a grate across the end
    for y in [13.25 + 0.12 * i for i in range(14)]:
        B(5.94, 5.98, y - 0.012, y + 0.012, F, H - 0.4, M["iron"], "grate_bar")
    B(5.92, 5.99, 13.2, 14.8, F + 1.0, F + 1.05, M["iron"], "grate_rail")

    # the cage between the shaft and the annex (x = 13), a door in it
    for y in [-4.4 + 0.13 * i for i in range(67)]:
        if abs(y) < 0.55:
            continue
        B(13.0 - 0.012, 13.0 + 0.012, y - 0.012, y + 0.012, F, H - 0.2, M["iron"], "cage_bar")
    B(12.97, 13.03, -4.4, 4.4, H - 0.25, H - 0.2, M["iron"], "cage_top_rail")
    B(12.97, 13.03, -4.4, 4.4, F + 0.7, F + 0.75, M["iron"], "cage_mid_rail")
    B(12.97, 13.03, -0.55, 0.55, H - 0.45, H - 0.4, M["iron"], "gate_lintel")
    S.door("annex_gate", "y", 13.0, 0, swing=(1, 0), w=1.1, h=2.15)

    # ENTRANCE (cellar chamber): the drop-tube ends just above the rail, a low basket hangs under it; a feeder track joins it over the north wall
    S.k.cylinder(0.2, 3.2, loc=(-9.5, 0, RAIL_Z + 1.5), material=M["brass"], name="drop_tube", verts=14)
    S.k.cylinder(0.32, 0.12, loc=(-9.5, 0, RAIL_Z - 0.1), material=M["brass"], name="tube_flare", verts=14)
    B(-10.5, -9.0, -0.5, 0.5, 2.4, 2.5, M["iron"], "tube_cradle_beam")
    # feeder track (the market's own conveyor straights and bone-basket carriers): comes in from the bar side over the north wall at 90 degrees and merges
    # into the drop tube. Track base height FZ is set so the hanging baskets (1.09 m deep) clear the wall top (2.6 m).
    FZ = 3.85
    templ = import_market_parts()

    def place(src, x, y, z, rot_deg):
        o = src.copy()
        o.data = src.data.copy()                      # one mesh per placed copy (the engine applies transforms)
        bpy.context.scene.collection.objects.link(o)
        o.rotation_mode = "XYZ"
        o.location = (x, y, z)
        o.rotation_euler = (0, 0, math.radians(rot_deg))
        return o

    for yy in (1.5, 4.5):                                                                              # two 3 m straights along y, from the tube out past the wall
        place(templ["straight"], -9.5, yy, FZ, 90)
    S.k.cylinder(0.22, 0.12, loc=(-9.5, 0, FZ + 0.2), material=M["brass"], name="tube_collar", verts=14)
    B(-9.62, -9.38, 1.7, 1.9, F, FZ - 0.02, M["iron"], "feeder_post")                                  # post inside the chamber
    B(-9.7, -9.3, 1.65, 1.95, FZ - 0.05, FZ, M["iron"], "feeder_post_cap")
    B(-9.62, -9.38, 3.3, 3.5, 2.6, FZ - 0.02, M["iron"], "feeder_wall_bracket")                        # bracket standing on the wall
    S.k.cylinder(0.12, 1.8, loc=(-9.5, 6.0, FZ + 0.9), material=M["brass"], name="feeder_riser", verts=12)   # the track continues up toward the bar
    for yy in (2.4, 4.9):                                                                              # carriers hang below the track
        place(templ["carrier"], -9.5, yy, FZ, 90)
    S.crate(-11.4, 2.3)
    S.crate(-11.4, -2.3, 0.5)
    S.barrel(-11.2, 0.8)
    wall_lantern(-9.9, 3.0, 2.2, -9.9, 3.2)

    # the hanging rail: from the tube east to the annex cage, hung from cross-beams (nothing on the floor)
    B(-9.6, 12.5, -0.05, 0.05, RAIL_Z - 0.05, RAIL_Z + 0.05, M["iron"], "rail")
    B(-8.1, -7.9, -3.3, 3.3, 2.4, H + 0.06, M["coak"], "hang_beam", 0.01)
    B(-8.02, -7.98, -0.02, 0.02, RAIL_Z, 2.45, M["iron"], "hanger")
    for x in (-4.7, -2.2, 0.3, 2.7, 5.6, 8.1, 10.6):
        B(x - 0.1, x + 0.1, -0.9, 0.9, 2.4, H + 0.06, M["coak"], "hang_beam", 0.01)
        B(x - 0.02, x + 0.02, -0.02, 0.02, RAIL_Z, 2.45, M["iron"], "hanger")

    def basket(x, zb):
        """A hanging carrier basket: slatted box on a rod from the rail."""
        B(x - 0.4, x + 0.4, -0.3, 0.3, zb, zb + 0.05, M["doak"], "basket_floor")
        for sy in (-1, 1):
            B(x - 0.4, x + 0.4, sy * 0.3 - (0.03 if sy > 0 else 0), sy * 0.3 + (0 if sy > 0 else 0.03), zb + 0.05, zb + 0.45, M["doak"], "basket_side")
        for sx in (-1, 1):
            B(x + sx * 0.4 - (0.03 if sx > 0 else 0), x + sx * 0.4 + (0 if sx > 0 else 0.03), -0.27, 0.27, zb + 0.05, zb + 0.45, M["doak"], "basket_end")
        B(x - 0.015, x + 0.015, -0.015, 0.015, zb + 0.45, RAIL_Z, M["iron"], "basket_rod")

    basket(-9.5, F + 0.45)          # the entrance basket, low enough to climb into
    basket(-3.4, 1.2)
    basket(1.7, 1.2)
    basket(7.3, 1.2)
    basket(11.2, 1.2)

    # brass pipes along the main shaft
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
    for i in range(14):                                                                  # a little fungus in the dead-end branches
        S.k.sphere(rng.uniform(0.08, 0.16), loc=(3.2 if i % 2 else 4.8, rng.uniform(2.0, 7.0), F + rng.uniform(0.6, 1.8)), scale=(0.35, 1.2, 0.8), material=M["fungus"], name="fungus", segments=7)
    for i in range(6):
        S.k.sphere(0.12, loc=(-3 + 1.9 * i, 0.8 if i % 2 else -0.8, F + 0.25), scale=(1.4, 0.3, 0.5), material=M["soot"], name="crushed_fungus", segments=7)
    # a few wet small footprints along the south wall (Gerald)
    for i in range(10):
        B(-5 + 1.1 * i, -4.9 + 1.1 * i, -0.55 - 0.05 * (i % 2), -0.5 - 0.05 * (i % 2), F + 0.004, F + 0.009, M["water"], "wet_print")

    # the dusty old terminal (the note lead): a capsule terminal on no active route, at the end of the south dogleg
    B(-5.7, -4.3, -11.2, -10.4, F, F + 0.6, M["granite"], "terminal_plinth", 0.02)
    S.k.cylinder(0.22, 0.9, loc=(-5.0, -10.8, F + 1.05), material=M["brass"], name="terminal_barrel", verts=14)
    S.k.cylinder(0.26, 0.08, loc=(-5.0, -10.8, F + 1.55), material=M["brass"], name="terminal_cap", verts=14)
    B(-5.2, -4.8, -10.55, -10.45, F + 0.8, F + 1.1, M["iron"], "capsule_slot")
    B(-5.15, -4.85, -10.5, -10.4, F + 0.82, F + 1.05, M["dbone"], "capsule")

    # annex: shelves of unclaimed remains with expired tags, a ledger table, Gerald's nest on the far shelf with the notebook
    S.shelf_unit(14.2, 21.0, 4.1, 4.4, 2.4, "s", rows=4, items="boxes")           # shelving stands against the north and south walls
    S.shelf_unit(14.2, 21.0, -4.4, -4.1, 2.4, "n", rows=4, items="boxes")
    S.table(15.5, 17.5, -0.6, 0.6, h=0.9, mat=M["doak"])
    B(15.8, 16.4, -0.3, 0.3, F + 0.96, F + 1.0, M["paper"], "annex_ledger")
    B(16.7, 17.3, -0.2, 0.2, F + 0.96, F + 0.99, M["red"], "annex_stamp")
    B(21.4, 22.2, 1.4, 3.6, F, F + 1.0, M["doak"], "nest_shelf", 0.01)                   # Gerald's nest shelf (east wall)
    for i in range(6):
        B(21.5 + 0.1 * (i % 2), 21.9 + 0.1 * (i % 2), 1.6 + 0.3 * i, 1.85 + 0.3 * i, F + 1.0, F + 1.06, M["linen"], "straw")
    B(21.7, 21.95, 2.4, 2.75, F + 1.06, F + 1.12, M["red"], "pimm_notebook")             # the field notebook
    B(22.14, 22.2, 0.6, 1.2, F + 1.7, F + 1.95, M["plaque"], "notice_board_plate")       # 'NOTICE EXPIRES' board
    wall_lantern(17.5, 4.0, 2.2, 17.5, 4.1)          # lanterns on wall brackets (the shafts are open-topped, nothing to hang from)
    wall_lantern(21.95, -2.0, 1.9, 22.2, -2.0)
    S.finish()
