"""The Last Respite Before Further Administrative Action: Mottle's tavern in the Ossuary Exchange.
Large interior scene, 28 x 20 m clear (about 18 x 13 grid squares), floor at Z=0.1. Roof, tie beams and the hanging
conveyor are in ossuary_tavern_roof.py so the GM can hide them (they are positioned to line up; keep W/D/WALL_H in sync).
Materials reuse the Exchange plaza's textures (textures/extract.py).

Layout (x east, y north; the south wall is the street/plaza side):
  south  : double entrance at x=0, queue-and-notices desk with pigeonholes (east of the door), windows
  north  : big hearth at x=-3, kitchen door at x=11, windows
  east   : long bar (x~10), back-bar shelves and kegs on the wall, service door to the cellar stair
  west   : mezzanine gallery with beds, stair up along the south end, door to the Exchange hallway under it
  centre : bone-inlay ring, brazier, long and round tables with stools and benches
"""
import math

import bpy
from _parts import BOTTLE_PROFILES, Skulls, bm_to_obj, flame_tongue, lathe

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"

IX, IY = 14.0, 10.0      # half-extents of the clear interior
T = 0.7                  # wall thickness
WALL_H = 6.0              # tall enough for a 2.3 m door on the mezzanine (deck at 3.3)
F = 0.1                  # floor top
MEZ = 3.3                # mezzanine deck top


def build(k):
    # ----------------------------------------------------------- materials
    ashlar = k.tex("ashlar", "ancient_irregular_ossuary_ashlar", tile=1.6, rough=0.9)
    mortar = k.tex("mortar", "calcified_ancient_lime_and_bone_mortar", tile=1.5, rough=0.95)
    floor = k.tex("floor", "exchange_worn_flagstone_paving", tile=2.4, rough=0.85)
    inlay = k.tex("inlay", "dark_flagstone_with_structural_bone_inlay", tile=2.4, rough=0.85)
    granite = k.tex("granite", "ossuary_gold_flecked_charcoal_granite", tile=1.2, rough=0.4)
    oak = k.tex("oak", "archive_oak", tile=1.2, rough=0.7)
    doak = k.tex("dark_oak", "dark_antique_oak", tile=1.2, rough=0.65)
    coak = k.tex("charred", "charred_oak_reinforced_with_bone_straps", tile=1.2, rough=0.8)
    bone = k.tex("bone", "weathered_structural_bone", tile=0.8, rough=0.6)
    brass = k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4)
    iron = k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3)
    cloth_red = k.mat("banner_red", (0.30, 0.06, 0.05), roughness=0.95)
    cloth_ochre = k.mat("banner_ochre", (0.42, 0.28, 0.08), roughness=0.95)
    linen = k.mat("linen", (0.55, 0.50, 0.40), roughness=0.95)
    paper = k.mat("paper", (0.62, 0.58, 0.45), roughness=0.9)
    soot = k.mat("soot", (0.02, 0.02, 0.02), roughness=1.0)
    glass_g = k.mat("bottle_green", (0.08, 0.22, 0.12), roughness=0.2)
    glass_a = k.mat("bottle_amber", (0.40, 0.18, 0.04), roughness=0.2)
    glass_b = k.mat("bottle_blue", (0.06, 0.12, 0.28), roughness=0.2)
    ember = k.mat("ember", (1.0, 0.30, 0.06), roughness=0.7, emission=(1.0, 0.35, 0.08))
    flame = k.mat("flame", (1.0, 0.12, 0.0), roughness=0.5, emission=(1.0, 0.12, 0.0))
    flame_core = k.mat("flame_core", (1.0, 0.65, 0.12), roughness=0.5, emission=(1.0, 0.65, 0.12))
    clay = k.mat("clay_jug", (0.30, 0.17, 0.09), roughness=0.8)
    candle = k.mat("candle", (0.95, 0.85, 0.6), roughness=0.5, emission=(1.0, 0.65, 0.25))
    plaque = k.mat("plaque", (0.7, 0.55, 0.2), roughness=0.4, emission=(0.9, 0.6, 0.15))

    skulls = Skulls()
    skull_teeth = k.mat("skull_teeth", (0.88, 0.84, 0.72), roughness=0.55)

    def B(x0, x1, y0, y1, z0, z1, mat, name="box", bevel=0.0, rot=(0, 0, 0)):
        return k.box((x1 - x0, y1 - y0, z1 - z0), loc=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                     rot=rot, material=mat, name=name, bevel=bevel)

    def torus(major, minor, loc, rot=(0, 0, 0), mat=None, name="ring"):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=8,
                                         location=loc, rotation=[math.radians(a) for a in rot])
        return k._finish(bpy.context.active_object, name, mat, 0)

    # ------------------------------------------------------------- walls
    def wall(axis, pos, a0, a1, mat, openings=(), z0=0.0, z1=WALL_H, name="wall"):
        """Wall of thickness T centred on `pos`, running a0..a1 along `axis` ('x' or 'y'), with openings
        [(centre, width, sill, head)] cut out as piers + sill + lintel pieces."""
        def seg(u0, u1, za, zb):
            if u1 - u0 < 0.02 or zb - za < 0.02:
                return
            if axis == "x":
                B(u0, u1, pos - T / 2, pos + T / 2, za, zb, mat, name)
            else:
                B(pos - T / 2, pos + T / 2, u0, u1, za, zb, mat, name)
        cur = a0
        for c, w, sill, head in sorted(openings):
            seg(cur, c - w / 2, z0, z1)
            seg(c - w / 2, c + w / 2, z0, sill)
            seg(c - w / 2, c + w / 2, head, z1)
            cur = c + w / 2
        seg(cur, a1, z0, z1)

    def frame(axis, pos, c, w, sill, head, mat=doak):
        """Timber jambs, lintel and sill around an opening."""
        d = T + 0.12
        j = 0.16
        def blk(u0, u1, za, zb):
            if axis == "x":
                B(u0, u1, pos - d / 2, pos + d / 2, za, zb, mat, "frame", bevel=0.01)
            else:
                B(pos - d / 2, pos + d / 2, u0, u1, za, zb, mat, "frame", bevel=0.01)
        e = 0.02   # inset into the opening so frame faces never share a plane with the wall's opening faces
        blk(c - w / 2 - j, c - w / 2 + e, sill, head + j)
        blk(c + w / 2 - e, c + w / 2 + j, sill, head + j)
        blk(c - w / 2 - j, c + w / 2 + j, head - e, head + j + 0.1)
        if sill > 0.5:
            blk(c - w / 2 - j, c + w / 2 + j, sill - 0.1, sill + e)

    def window(axis, pos, c, w=1.4, sill=1.3, head=3.6):
        frame(axis, pos, c, w, sill, head, iron)
        d = T + 0.04
        # mullion and transom in iron
        if axis == "x":
            B(c - 0.03, c + 0.03, pos - d / 2, pos + d / 2, sill, head, iron, "mullion")
            B(c - w / 2, c + w / 2, pos - d / 2, pos + d / 2, (sill + head) / 2 - 0.03, (sill + head) / 2 + 0.03, iron, "transom")
        else:
            B(pos - d / 2, pos + d / 2, c - 0.03, c + 0.03, sill, head, iron, "mullion")
            B(pos - d / 2, pos + d / 2, c - w / 2, c + w / 2, (sill + head) / 2 - 0.03, (sill + head) / 2 + 0.03, iron, "transom")

    ys, yn = -(IY + T / 2), IY + T / 2     # wall centre lines, south and north
    xw, xe = -(IX + T / 2), IX + T / 2     # west and east
    EXT = IX + T

    # south wall: entrance + 4 windows
    s_open = [(0, 3.2, 0, 3.7)] + [(x, 1.4, 1.3, 3.6) for x in (-12, -7.5, 7.5, 12)]
    wall("x", ys, -EXT, EXT, ashlar, s_open)
    frame("x", ys, 0, 3.2, 0, 3.7)
    for x in (-12, -7.5, 7.5, 12):
        window("x", ys, x)
    # north wall: hearth sits in front of it, kitchen door, 2 windows
    n_open = [(11, 1.4, 0, 2.7), (-9, 1.4, 1.3, 3.6), (5, 1.4, 1.3, 3.6)]
    wall("x", yn, -EXT, EXT, ashlar, n_open)
    frame("x", yn, 11, 1.4, 0, 2.7)
    for x in (-9, 5):
        window("x", yn, x)
    # west wall: hallway door under the mezzanine, 3 high windows above it
    UP_Y = -1.0                       # the upstairs door, at the top of the stair
    UP_H = 2.3
    w_open = [(1.5, 1.6, 0, 2.7), (UP_Y, 1.4, MEZ, MEZ + UP_H)] + [(y, 1.2, MEZ + 0.9, MEZ + 2.2) for y in (-6.5, 4, 7.5)]
    wall("y", xw, -IY, IY, ashlar, w_open)
    frame("y", xw, 1.5, 1.6, 0, 2.7)
    frame("y", xw, UP_Y, 1.4, MEZ, MEZ + UP_H)
    for y in (-6.5, 4, 7.5):
        window("y", xw, y, w=1.2, sill=MEZ + 0.9, head=MEZ + 2.2)
    # east wall: cellar/service door
    wall("y", xe, -IY, IY, ashlar, [(-8.5, 1.4, 0, 2.7)])
    frame("y", xe, -8.5, 1.4, 0, 2.7)

    # wall plates and buttress pilasters (break up the long walls)
    B(-IX, IX, -IY, -IY + 0.25, WALL_H - 0.3, WALL_H - 0.02, coak, "plate")
    B(-IX, IX, IY - 0.25, IY, WALL_H - 0.3, WALL_H - 0.02, coak, "plate")
    B(-IX, -IX + 0.25, -IY, IY, WALL_H - 0.3, WALL_H - 0.02, coak, "plate")
    B(IX - 0.25, IX, -IY, IY, WALL_H - 0.3, WALL_H - 0.02, coak, "plate")
    for x in (-10, -3.75, 3.75, 10):
        B(x - 0.25, x + 0.25, -IY, -IY + 0.35, 0, WALL_H - 0.3, mortar, "pilaster")
    for x in (-12.5, -6.5, 8, 13):
        B(x - 0.25, x + 0.25, IY - 0.35, IY, 0, WALL_H - 0.3, mortar, "pilaster")

    # ------------------------------------------------------------- floor
    B(-IX, IX, -IY, IY, 0, F, floor, "floor")
    k.cylinder(3.62, 0.012, loc=(0, 0, F + 0.006), material=bone, name="inlay_edge", verts=48)
    k.cylinder(3.5, 0.012, loc=(0, 0, F + 0.012), material=inlay, name="inlay_disc", verts=48)
    B(-1.1, 1.1, -IY, -3.3, F, F + 0.016, inlay, "inlay_runner")      # entrance runner, door to ring

    # ------------------------------------------------------------ pillars + arcade beams
    px = (-6.5, 6.5)
    py = (-3.5, 4.0)
    for x in px:
        for y in py:
            shaft = WALL_H - 0.35 - (F + 0.35)           # base 0.35 tall, cap 0.3 tall, 5 cm under the wall top
            B(x - 0.5, x + 0.5, y - 0.5, y + 0.5, F, F + 0.35, granite, "pillar_base", bevel=0.03)
            k.cylinder(0.38, shaft, loc=(x, y, F + 0.35 + shaft / 2), material=ashlar, name="pillar", verts=14)
            k.cylinder(0.43, 0.12, loc=(x, y, F + 1.6), material=brass, name="pillar_band", verts=14)
            B(x - 0.5, x + 0.5, y - 0.5, y + 0.5, WALL_H - 0.35, WALL_H - 0.05, granite, "pillar_cap", bevel=0.03)
    for x in px:
        B(x - 0.2, x + 0.2, -IY, IY, WALL_H - 0.55, WALL_H - 0.07, coak, "arcade_beam", bevel=0.02)

    # ------------------------------------------------------------- hearth (north wall, x=-3)
    hx = -3.0
    B(hx - 2.6, hx - 1.2, 8.3, IY, F, WALL_H, ashlar, "hearth_jamb")
    B(hx + 1.2, hx + 2.6, 8.3, IY, F, WALL_H, ashlar, "hearth_jamb")
    B(hx - 1.2, hx + 1.2, 8.3, IY, F + 1.9, WALL_H, ashlar, "hearth_breast")
    B(hx - 2.9, hx + 2.9, 7.2, 8.3, F, F + 0.22, granite, "hearth_apron", bevel=0.02)
    B(hx - 1.2, hx + 1.2, 8.3, IY, F, F + 0.3, granite, "firebox_floor")
    B(hx - 1.2, hx + 1.2, IY - 0.06, IY - 0.01, F + 0.3, F + 1.9, soot, "soot")
    B(hx - 3.0, hx + 3.0, 8.0, 8.55, F + 2.05, F + 2.25, doak, "mantel", bevel=0.02)   # protrudes 0.3 m from the breast face (y 8.3)
    for i in range(5):     # mantel top is at F + 2.25
        skulls.add(hx - 2.2 + i * 1.1, 8.15, F + 2.25, face_to=(0, 0), s=0.1)
    for dy in (-0.45, 0.0, 0.45):
        k.cylinder(0.12, 1.5, loc=(hx + dy * 0.4, 9.3 + dy * 0.7, F + 0.45), rot=(0, 90, 8 * dy * 10), material=coak, name="log", verts=10)
    B(hx - 0.9, hx + 0.9, 8.9, 9.7, F + 0.3, F + 0.36, ember, "embers")
    # hearth fire: swaying flame tongues (red-orange) with smaller yellow cores
    for fx, fy, fh, sw in ((-0.8, 0.0, 0.7, -0.12), (-0.45, 0.1, 0.95, 0.15), (-0.1, -0.05, 1.2, -0.10), (0.25, 0.1, 1.0, 0.16),
                           (0.6, 0.0, 0.8, -0.13), (0.85, 0.1, 0.55, 0.10), (0.05, 0.2, 0.7, 0.12)):
        flame_tongue(hx + fx, 9.3 + fy, F + 0.34, fh, 0.2, sw, flame, "flame")
        flame_tongue(hx + fx, 9.3 + fy, F + 0.34, fh * 0.6, 0.12, sw * 0.6, flame_core, "flame_core")
    for fx in (-0.8, 0.8):
        B(hx + fx - 0.04, hx + fx + 0.04, 8.8, 9.8, F + 0.3, F + 0.75, iron, "andiron")
    k.sphere(0.4, loc=(hx + 1.0, 8.95, F + 0.62), scale=(1, 1, 0.8), material=iron, name="cauldron")
    for sx, sy in ((-4.2, 6.2), (-1.8, 6.2)):   # high-back settles facing the fire
        B(sx - 1.0, sx + 1.0, sy - 0.3, sy + 0.3, F + 0.35, F + 0.5, oak, "settle_seat", bevel=0.01)
        B(sx - 1.0, sx + 1.0, sy + 0.3, sy + 0.4, F + 0.35, F + 1.5, doak, "settle_back", bevel=0.01)
        for lx in (-0.9, 0.9):
            B(sx + lx - 0.05, sx + lx + 0.05, sy - 0.25, sy + 0.25, F, F + 0.35, doak, "settle_leg")

    # ------------------------------------------------------------- bar (east)
    bx0, bx1, by0, by1 = 9.2, 10.4, -6.5, 8.5
    B(bx0, bx1, by0, by1, F, 1.1, oak, "bar_body", bevel=0.01)
    B(bx0 - 0.15, bx1 + 0.2, by0 - 0.1, by1 + 0.1, 1.1, 1.18, granite, "bar_top", bevel=0.015)
    y = by0 + 0.4
    while y < by1:
        B(bx0 - 0.04, bx0, y - 0.07, y + 0.07, F, 1.08, doak, "bar_post")
        y += 1.25
    k.cylinder(0.03, by1 - by0, loc=(bx0 - 0.3, (by0 + by1) / 2, 0.3), rot=(90, 0, 0), material=brass, name="foot_rail", verts=8)
    y = by0 + 0.5
    while y < by1:
        B(bx0 - 0.3 - 0.015, bx0 - 0.285 + 0.015, y - 0.015, y + 0.015, F, 0.3, brass, "rail_bracket")
        y += 2.0
    for i in range(10):    # bar stools
        sy = by0 + 0.8 + i * 1.5
        k.cylinder(0.22, 0.07, loc=(8.5, sy, 0.76), material=doak, name="stool_seat", verts=12)
        k.cylinder(0.04, 0.68, loc=(8.5, sy, 0.4), material=iron, name="stool_stem", verts=8)
        k.cylinder(0.16, 0.03, loc=(8.5, sy, 0.3), material=iron, name="stool_ring", verts=10)
    # taps and the pneumatic drop-tube stub
    B(9.5, 10.1, -1.0, 4.2, 1.18, 1.3, brass, "tap_bar", bevel=0.01)
    for i in range(5):
        ty = -0.5 + i * 0.9
        k.cylinder(0.025, 0.35, loc=(9.8, ty, 1.47), material=brass, name="tap", verts=8)
        k.sphere(0.05, loc=(9.8, ty, 1.66), material=bone, name="tap_handle", segments=8)
    k.cylinder(0.1, 0.55, loc=(9.8, -4.0, 1.46), material=brass, name="tube_stub", verts=12)
    k.cylinder(0.15, 0.05, loc=(9.8, -4.0, 1.2), material=brass, name="tube_flange", verts=12)
    # back-bar: cabinet, three shelves of bottles, skulls on top
    B(13.3, IX, -6.0, 8.2, F, 1.0, doak, "backbar", bevel=0.01)
    B(13.25, IX, -6.1, 8.3, 1.0, 1.06, granite, "backbar_top")
    for sy in range(-6, 9, 3):
        B(13.55, 13.65, sy - 0.05, sy + 0.05, 1.06, 3.1, doak, "shelf_post")
    import bmesh as _bm
    glass = {i: _bm.new() for i in range(4)}   # one mesh per glass colour
    profiles = BOTTLE_PROFILES
    for zi, zs in enumerate((1.6, 2.25, 2.9)):
        B(13.5, IX, -6.0, 8.2, zs, zs + 0.05, oak, "shelf", bevel=0.005)
        y = -5.8 + (zi % 2) * 0.2
        i = 0
        while y < 8.0:
            H, prof = profiles[(i + zi) % 3]
            lathe(glass[(i * 2 + zi) % 4], [(r, f * H * (1 + 0.1 * ((i * 7 + zi) % 3) / 2)) for r, f in prof], 13.72, y, zs + 0.05, seg=7)
            y += 0.5
            i += 1
    for idx, mat in enumerate((glass_g, glass_a, glass_b, clay)):
        bm_to_obj(glass[idx], "bottles", mat)
    for i in range(10):    # skulls sit ON the top shelf (board top is at 2.95), faces toward the room centre
        skulls.add(13.7, -5.4 + i * 1.5, 2.95, face_to=(0, 0), s=0.1)
    for kx, kz in ((12.0, 0.55), (13.0, 0.55), (12.5, 1.4)):    # kegs, NE corner (staff side)
        k.cylinder(0.42, 0.85, loc=(kx, 9.2, F + kz - 0.1), rot=(90, 0, 0), material=oak, name="keg", verts=14)
        k.cylinder(0.43, 0.06, loc=(kx, 9.2 - 0.2, F + kz - 0.1), rot=(90, 0, 0), material=iron, name="keg_hoop", verts=14)
        k.cylinder(0.43, 0.06, loc=(kx, 9.2 + 0.2, F + kz - 0.1), rot=(90, 0, 0), material=iron, name="keg_hoop", verts=14)
    B(11.6, 13.5, 8.6, 9.8, F, F + 0.1, doak, "keg_rack")
    B(12.1, 13.3, -3.6, -2.4, F, F + 0.05, iron, "cellar_hatch")   # cellar trapdoor behind the bar
    torus(0.12, 0.015, (12.7, -3.0, F + 0.07), mat=iron, name="hatch_ring")

    # ------------------------------------------------------------- mezzanine (west)
    B(-IX, -IX + 4.0, -4.0, IY, MEZ - 0.2, MEZ, oak, "mezz_deck")
    y = -3.6
    while y < IY:
        B(-IX, -IX + 4.0, y - 0.1, y + 0.1, MEZ - 0.5, MEZ - 0.2, coak, "mezz_joist")
        y += 1.3
    B(-10.35, -10.0, -4.0, IY, MEZ - 0.6, MEZ - 0.2, coak, "mezz_beam", bevel=0.01)
    for y in (-4.0, 0.5, 5.0, 9.6):
        B(-10.3, -10.0, y - 0.15, y + 0.15, F, MEZ - 0.2, doak, "mezz_post", bevel=0.01)
        B(-10.35, -9.95, y - 0.2, y + 0.2, 1.4, 1.5, brass, "mezz_post_band")
    B(-10.12, -10.0, -4.0, IY, MEZ + 1.0, MEZ + 1.1, doak, "mezz_rail", bevel=0.01)
    B(-10.1, -10.02, -4.0, IY, MEZ + 0.05, MEZ + 0.12, doak, "mezz_rail_low")
    y = -3.85
    while y < IY - 0.1:
        B(-10.08, -10.04, y - 0.025, y + 0.025, MEZ + 0.12, MEZ + 1.0, iron, "baluster")
        y += 0.3
    # stair along the west wall, rising north from the south end to the deck
    n_steps, x0, x1 = 16, -IX + 0.1, -IX + 1.6
    y_start, run = -9.7, 5.7 / 16
    for i in range(n_steps):
        B(x0, x1, y_start + i * run, y_start + (i + 1) * run, F, F + 0.2 * (i + 1), oak, "stair_step", bevel=0.005)
    ang = math.degrees(math.atan2(0.2 * n_steps, run * n_steps))
    zmid = F + 0.1 * n_steps + 0.95
    B(x1, x1 + 0.08, -6.85 - 3.25, -6.85 + 3.25, zmid - 0.04, zmid + 0.04, doak, "stair_handrail", rot=(ang, 0, 0))
    for i in range(0, n_steps, 3):
        zt = F + 0.2 * (i + 1)
        B(x1 + 0.01, x1 + 0.05, y_start + (i + 0.5) * run - 0.025, y_start + (i + 0.5) * run + 0.025, zt, zt + 0.95, iron, "stair_baluster")
    # landing at the top of the stair: a lantern bracket either side of the upstairs door and a brass room-plate
    for dy in (-1.0, 1.0):
        B(-IX, -IX + 0.1, UP_Y + dy * 1.15 - 0.04, UP_Y + dy * 1.15 + 0.04, MEZ + 1.6, MEZ + 2.0, brass, "landing_arm")
        k.sphere(0.1, loc=(-IX + 0.18, UP_Y + dy * 1.15, MEZ + 2.05), material=candle, name="landing_lamp", segments=8)
    B(-IX, -IX + 0.03, UP_Y - 0.3, UP_Y + 0.3, MEZ + 2.45, MEZ + 2.65, plaque, "upstairs_plate")

    # ------------------------------------------------------------- doors (closed leaves)
    for sx in (-1, 1):   # main entrance
        cx = sx * 0.78
        B(cx - 0.76, cx + 0.76, ys - 0.07, ys + 0.07, 0, 3.6, coak, "door_leaf", bevel=0.01)
        for zb in (0.6, 1.8, 3.0):
            B(cx - 0.74, cx + 0.74, ys - 0.1, ys - 0.07, zb, zb + 0.12, iron, "door_band")
        torus(0.1, 0.014, (sx * 0.2, ys + 0.1, 1.6), rot=(90, 0, 0), mat=brass, name="door_ring")
    for i in range(9):
        B(-1.5 + i * 0.375 - 0.04, -1.5 + i * 0.375 + 0.04, ys - 0.45, ys - 0.40, 3.78, 3.88, bone, "lintel_stud")
    B(xw - 0.07, xw + 0.07, 1.5 - 0.76, 1.5 + 0.76, 0, 2.6, coak, "hall_door", bevel=0.01)
    # upstairs door: a real swinging door node (hinge on the south jamb, opens into the gallery)
    k.door(1.3, UP_H - 0.05, hinge=(xw, UP_Y - 0.65, MEZ), yaw_deg=90, swing=(1, 0), leaf_mat=coak, trim_mat=iron, door_id="upstairs")
    B(xe - 0.07, xe + 0.07, -8.5 - 0.66, -8.5 + 0.66, 0, 2.6, coak, "service_door", bevel=0.01)
    B(11 - 0.66, 11 + 0.66, yn - 0.07, yn + 0.07, 0, 2.6, coak, "kitchen_door", bevel=0.01)

    # ------------------------------------------------------------- queue-and-notices desk (south wall, east of door)
    B(2.4, 6.4, -9.9, -9.1, F, 1.0, oak, "desk", bevel=0.01)
    B(2.3, 6.5, -10.0, -9.0, 1.0, 1.07, granite, "desk_top")
    for c in range(8):
        for r in range(4):
            B(2.55 + c * 0.47, 2.55 + c * 0.47 + 0.42, -9.95, -9.65, 1.5 + r * 0.45, 1.5 + r * 0.45 + 0.4, doak, "pigeonhole", bevel=0.005)
            if (c * 3 + r) % 3 == 0:
                B(2.6 + c * 0.47, 2.6 + c * 0.47 + 0.3, -9.7, -9.62, 1.55 + r * 0.45, 1.55 + r * 0.45 + 0.3, paper, "scroll")
    B(3.8, 5.0, -9.99, -9.9, 3.5, 3.7, plaque, "ticket_plate")     # "now serving" plate
    for x in (3.4, 5.4):
        k.cylinder(0.05, 0.25, loc=(x, -9.5, 1.2), material=candle, name="desk_candle", verts=8)
    # notice board west of the door
    B(-6.0, -2.4, -IY, -IY + 0.1, 1.2, 3.6, oak, "notice_board", bevel=0.01)
    for i in range(7):
        B(-5.7 + (i % 4) * 0.85, -5.7 + (i % 4) * 0.85 + 0.45, -IY + 0.1, -IY + 0.12, 1.5 + (i // 4) * 1.0 + (i % 3) * 0.1, 1.5 + (i // 4) * 1.0 + 0.6, paper, "notice")

    # ------------------------------------------------------------- furniture
    def mug(x, y, z):
        k.cylinder(0.05, 0.1, loc=(x, y, z + 0.05), material=brass, name="mug", verts=8)

    def round_table(x, y, stools=4):
        k.cylinder(0.78, 0.07, loc=(x, y, 0.78), material=oak, name="rt_top", verts=20)
        k.cylinder(0.12, 0.7, loc=(x, y, 0.4), material=doak, name="rt_stem", verts=8)
        B(x - 0.45, x + 0.45, y - 0.06, y + 0.06, F, F + 0.08, doak, "rt_foot")
        B(x - 0.06, x + 0.06, y - 0.45, y + 0.45, F, F + 0.08, doak, "rt_foot")
        for i in range(stools):
            a = math.radians(i * 360 / stools + 20)
            sx, sy = x + 1.15 * math.cos(a), y + 1.15 * math.sin(a)
            k.cylinder(0.21, 0.06, loc=(sx, sy, 0.46), material=doak, name="stool", verts=10)
            k.cylinder(0.05, 0.4, loc=(sx, sy, 0.24), material=doak, name="stool_leg", verts=6)
        mug(x + 0.3, y + 0.1, 0.815)
        mug(x - 0.25, y - 0.2, 0.815)
        k.cylinder(0.03, 0.12, loc=(x, y, 0.88), material=candle, name="table_candle", verts=6)

    def long_table(x, y, length=3.6):
        B(x - length / 2, x + length / 2, y - 0.45, y + 0.45, 0.76, 0.84, oak, "lt_top", bevel=0.01)
        for lx in (-length / 2 + 0.4, length / 2 - 0.4):
            B(x + lx - 0.06, x + lx + 0.06, y - 0.4, y + 0.4, F, 0.76, doak, "lt_trestle")
            B(x + lx - 0.3, x + lx + 0.3, y - 0.08, y + 0.08, F, F + 0.1, doak, "lt_foot")
        B(x - length / 2 + 0.4, x + length / 2 - 0.4, y - 0.04, y + 0.04, 0.3, 0.36, doak, "lt_stretcher")
        for side in (-1, 1):
            by = y + side * 0.75
            B(x - length / 2 + 0.1, x + length / 2 - 0.1, by - 0.17, by + 0.17, 0.43, 0.49, oak, "bench", bevel=0.01)
            for lx in (-length / 2 + 0.5, length / 2 - 0.5):
                B(x + lx - 0.05, x + lx + 0.05, by - 0.14, by + 0.14, F, 0.43, doak, "bench_leg")
        for i in range(5):
            mug(x - length / 2 + 0.5 + i * (length - 1) / 4, y + (0.15 if i % 2 else -0.15), 0.84)
        for cx in (-0.8, 0.8):
            k.cylinder(0.03, 0.14, loc=(x + cx, y, 0.91), material=candle, name="table_candle", verts=6)

    for rx, ry in ((-8.0, -7.0), (-8.0, -0.8), (-4.4, -7.2), (4.6, -6.6), (-8.2, 5.2), (-0.2, 6.0)):
        round_table(rx, ry)
    for lx, ly in ((-2.6, -2.2), (3.4, -2.0), (3.4, 2.6)):
        long_table(lx, ly)
    # brazier at the centre of the inlay ring
    for a in (0, 120, 240):
        ar = math.radians(a)
        k.cylinder(0.04, 0.9, loc=(0.35 * math.cos(ar), 0.35 * math.sin(ar), F + 0.4), rot=(15 * math.sin(ar), -15 * math.cos(ar), 0), material=iron, name="brazier_leg", verts=6)
    k.cylinder(0.5, 0.2, loc=(0, 0, F + 0.95), material=iron, name="brazier_bowl", verts=16)
    k.cylinder(0.42, 0.04, loc=(0, 0, F + 1.06), material=ember, name="brazier_coals", verts=16)
    for fx, fy, fh, sw in ((-0.15, 0.0, 0.5, 0.08), (0.12, 0.08, 0.7, -0.10), (0.05, -0.12, 0.45, 0.07)):
        flame_tongue(fx, fy, F + 1.06, fh, 0.13, sw, flame, "brazier_flame")
        flame_tongue(fx, fy, F + 1.06, fh * 0.6, 0.075, sw * 0.6, flame_core, "brazier_flame_core")

    # ------------------------------------------------------------- wall dressing
    for x in (-2.4, 2.4):
        B(x - 0.04, x + 0.04, -IY, -IY + 0.1, 2.5, 2.9, brass, "sconce_arm")
        k.sphere(0.1, loc=(x, -IY + 0.18, 2.95), material=candle, name="sconce_lamp", segments=8)
    for x in (-12, -9, -3.5, 4.5, 9.5, 12.5):
        B(x - 0.04, x + 0.04, IY - 0.1, IY, 2.5, 2.9, brass, "sconce_arm")
        k.sphere(0.1, loc=(x, IY - 0.18, 2.95), material=candle, name="sconce_lamp", segments=8)
    for y in (-8, -2.5, 3.5, 8.5):
        B(IX - 0.1, IX, y - 0.04, y + 0.04, 3.3, 3.7, brass, "sconce_arm")
        k.sphere(0.1, loc=(IX - 0.18, y, 3.75), material=candle, name="sconce_lamp", segments=8)
    for x, mat in ((-9.75, cloth_red), (9.75, cloth_ochre)):    # banners, south wall (between windows)
        B(x - 0.5, x + 0.5, -IY, -IY + 0.04, 2.4, 4.9, mat, "banner")
        B(x - 0.55, x + 0.55, -IY, -IY + 0.08, 4.9, 5.0, bone, "banner_rod")
    for x, mat in ((-6.5, cloth_ochre), (1.8, cloth_red), (8.0, cloth_ochre)):   # banners, north wall (clear of the hearth)
        if abs(x - hx) < 3.3:
            continue
        B(x - 0.5, x + 0.5, IY - 0.04, IY, 2.4, 4.9, mat, "banner")
        B(x - 0.55, x + 0.55, IY - 0.08, IY, 4.9, 5.0, bone, "banner_rod")
    for i in range(7):      # skulls on little shelves along the north wall above the windows
        sx = -13 + i * 1.4
        B(sx - 0.14, sx + 0.14, IY - 0.22, IY, 4.62, 4.66, doak, "skull_bracket")
        skulls.add(sx, IY - 0.12, 4.66, face_to=(0, 0), s=0.09)
    # crates and a barrel by the hallway door
    B(-13.4, -12.4, 3.4, 4.2, F, F + 0.7, coak, "crate", bevel=0.02)
    B(-13.2, -12.5, 3.5, 4.1, F + 0.7, F + 1.3, coak, "crate", bevel=0.02)
    k.cylinder(0.35, 0.8, loc=(-13.4, -2.5, F + 0.4), material=oak, name="barrel", verts=12)

    skulls.finish(bone, soot, skull_teeth, name="skulls")
