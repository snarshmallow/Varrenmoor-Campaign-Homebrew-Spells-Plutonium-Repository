"""Upstairs of The Last Respite Before Further Administrative Action: landing, corridor, 8 small guest rooms and the
party's suite (ornate living room with a hearth, three bedrooms) at the far end. Every door is a real swinging door node.
Open top (no ceiling) for top-down play; ceiling height 3.2 m. Plan (x east, y north, metres):

    landing x[-19.5,-16.25] y[-3,3]   door to the tavern stair in its west wall
    corridor x[-16,2] y[-1.5,1.5]     rooms 201-204 north (y 1.75..6), 205-208 south (y -6..-1.75), 4.25 m wide each
    suite   x[2.5,19.5] y[-8,8]       double door at x=2.25; living room x[2.5,13] (hearth in the north wall);
                                      bedrooms x[13.4,19.5], three bands, doors in the partition at x=13.25
"""
import math

import bpy
from _parts import Skulls, Walls, flame_tongue

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"

H = 3.2           # ceiling
F = 0.1           # floor top
TP, TE = 0.25, 0.5   # partition and exterior wall thickness
DOOR_H = 2.2


def build(k):
    # ----------------------------------------------------------- materials
    plaster = k.tex("plaster", "calcified_ancient_lime_and_bone_mortar", tile=1.5, rough=0.95)
    ashlar = k.tex("ashlar", "ancient_irregular_ossuary_ashlar", tile=1.6, rough=0.9)
    floor_oak = k.tex("floor_oak", "archive_oak", tile=1.4, rough=0.7)
    oak = k.tex("oak", "archive_oak", tile=1.2, rough=0.7)
    doak = k.tex("dark_oak", "dark_antique_oak", tile=1.2, rough=0.65)
    coak = k.tex("charred", "charred_oak_reinforced_with_bone_straps", tile=1.2, rough=0.8)
    granite = k.tex("granite", "ossuary_gold_flecked_charcoal_granite", tile=1.2, rough=0.4)
    brass = k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4)
    iron = k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3)
    bone = k.tex("bone", "weathered_structural_bone", tile=0.8, rough=0.6)
    red = k.mat("fabric_red", (0.32, 0.05, 0.05), roughness=0.95)
    gold = k.mat("fabric_gold", (0.55, 0.42, 0.12), roughness=0.6)
    navy = k.mat("fabric_navy", (0.06, 0.09, 0.22), roughness=0.95)
    green = k.mat("fabric_green", (0.05, 0.20, 0.12), roughness=0.95)
    plum = k.mat("fabric_plum", (0.22, 0.07, 0.25), roughness=0.95)
    linen = k.mat("linen", (0.58, 0.54, 0.44), roughness=0.95)
    parchment = k.mat("parchment", (0.62, 0.58, 0.45), roughness=0.9)
    soot = k.mat("soot", (0.02, 0.02, 0.02), roughness=1.0)
    ember = k.mat("ember", (1.0, 0.30, 0.06), roughness=0.7, emission=(1.0, 0.35, 0.08))
    flame = k.mat("flame", (1.0, 0.12, 0.0), roughness=0.5, emission=(1.0, 0.12, 0.0))
    flame_core = k.mat("flame_core", (1.0, 0.65, 0.12), roughness=0.5, emission=(1.0, 0.65, 0.12))
    candle = k.mat("candle", (0.95, 0.85, 0.6), roughness=0.5, emission=(1.0, 0.65, 0.25))
    plaque = k.mat("plaque", (0.7, 0.55, 0.2), roughness=0.4, emission=(0.9, 0.6, 0.15))
    book_mats = [k.mat(f"book{i}", c, roughness=0.8) for i, c in enumerate(
        [(0.35, 0.08, 0.06), (0.10, 0.16, 0.30), (0.08, 0.24, 0.14), (0.30, 0.22, 0.08), (0.20, 0.10, 0.22), (0.12, 0.10, 0.08)])]

    W = Walls(k, plaster, doak, iron)
    B = W.B

    def door(door_id, axis, wall_pos, c, swing, w=1.0, yaw=None, hinge_at_low=True):
        """Swinging door in a wall run. axis 'x': wall along x at y=wall_pos; 'y': along y at x=wall_pos."""
        lw = w - 0.02
        if axis == "x":
            hinge = (c - w / 2 + 0.01, wall_pos, F) if hinge_at_low else (c + w / 2 - 0.01, wall_pos, F)
            yy = 0 if hinge_at_low else 180
        else:
            hinge = (wall_pos, c - w / 2 + 0.01, F) if hinge_at_low else (wall_pos, c + w / 2 - 0.01, F)
            yy = 90 if hinge_at_low else -90
        return k.door(lw, DOOR_H - 0.05, hinge=hinge, yaw_deg=yy, swing=swing, leaf_mat=coak, trim_mat=iron, door_id=door_id)

    # ----------------------------------------------------------- floors
    B(-19.5, -16.25, -3.0, 3.0, 0, F, floor_oak, "floor")
    B(-16.25, 2.0, -6.0, 6.0, 0, F, floor_oak, "floor")
    B(2.5, 19.5, -8.0, 8.0, 0, F, floor_oak, "floor")

    # ----------------------------------------------------------- exterior walls
    ext = []
    W.wall("y", -19.75, -3.5, 3.5, TE, H, [(0, 1.1, 0, DOOR_H)], ashlar, name="ext")          # landing west + door
    W.frame("y", -19.75, TE, 0, 1.1, 0, DOOR_H)
    W.wall("x", 3.25, -19.5, -16.25, TE, H, [], ashlar, name="ext")                            # landing north / south
    W.wall("x", -3.25, -19.5, -16.25, TE, H, [], ashlar, name="ext")
    room_c = [-16 + 4.5 * i + 2.125 for i in range(4)]                                         # room centres along x
    wins = [(c, 1.2, 0.95, 2.4) for c in room_c]
    W.wall("x", 6.25, -16.25, 2.0, TE, H, wins, ashlar, name="ext")                            # corridor wing north / south
    W.wall("x", -6.25, -16.25, 2.0, TE, H, wins, ashlar, name="ext")
    for c in room_c:
        W.window("x", 6.25, TE, c)
        W.window("x", -6.25, TE, c)
    # suite: west (with double door), north, south, east
    W.wall("y", 2.25, -8.5, 8.5, TE, H, [(0, 2.0, 0, DOOR_H)], ashlar, name="ext")
    W.frame("y", 2.25, TE, 0, 2.0, 0, DOOR_H)
    n_w = [(4.2, 1.4, 0.95, 2.4), (11.5, 1.4, 0.95, 2.4), (16.4, 1.2, 0.95, 2.4)]
    s_w = [(4.2, 1.4, 0.95, 2.4), (7.75, 1.4, 0.95, 2.4), (11.5, 1.4, 0.95, 2.4), (16.4, 1.2, 0.95, 2.4)]
    W.wall("x", 8.25, 2.5, 20.0, TE, H, n_w, ashlar, name="ext")
    W.wall("x", -8.25, 2.5, 20.0, TE, H, s_w, ashlar, name="ext")
    for c, w, _, _ in n_w:
        W.window("x", 8.25, TE, c, w=w)
    for c, w, _, _ in s_w:
        W.window("x", -8.25, TE, c, w=w)
    e_w = [(y, 1.2, 0.95, 2.4) for y in (-5.4, 0, 5.4)]
    W.wall("y", 19.75, -8.0, 8.0, TE, H, e_w, ashlar, name="ext")
    for y, w, _, _ in e_w:
        W.window("y", 19.75, TE, y, w=w)

    # ----------------------------------------------------------- partitions
    xs = [-16 + 4.5 * i for i in range(4)]
    doors_n = [(c, 1.0, 0, DOOR_H) for c in room_c]
    W.wall("x", 1.625, -16.0, 2.0, TP, H, doors_n, plaster)                                    # corridor north wall
    W.wall("x", -1.625, -16.0, 2.0, TP, H, doors_n, plaster)                                   # corridor south wall
    for c in room_c:
        W.frame("x", 1.625, TP, c, 1.0, 0, DOOR_H)
        W.frame("x", -1.625, TP, c, 1.0, 0, DOOR_H)
    for i in range(4):                                                                          # room dividers and end walls
        px = xs[i] + 4.375
        W.wall("y", px, 1.75, 6.0, TP, H, [], plaster)
        W.wall("y", px, -6.0, -1.75, TP, H, [], plaster)
    W.wall("y", -16.125, 1.75, 6.0, TP, H, [], plaster)
    W.wall("y", -16.125, -6.0, -1.75, TP, H, [], plaster)
    # suite: living room / bedrooms partition with three doors, and the two bedroom dividers
    bed_c = [-5.4, 0.0, 5.4]
    W.wall("y", 13.25, -8.0, 8.0, TP, H, [(c, 1.0, 0, DOOR_H) for c in bed_c], plaster)
    for c in bed_c:
        W.frame("y", 13.25, TP, c, 1.0, 0, DOOR_H)
    for y in (-2.7, 2.7):
        W.wall("x", y, 13.375, 19.5, TP, H, [], plaster)

    # ----------------------------------------------------------- doors (swinging nodes)
    for i, c in enumerate(room_c):
        door(f"room{201 + i}", "x", 1.625, c, swing=(0, 1))
        door(f"room{205 + i}", "x", -1.625, c, swing=(0, -1))
    door("landing", "y", -19.75, 0, swing=(1, 0), w=1.1)
    door("suite_left", "y", 2.25, -0.5, swing=(1, 0), w=1.0)                                    # double door, two leaves
    door("suite_right", "y", 2.25, 0.5, swing=(1, 0), w=1.0, hinge_at_low=False)
    for i, c in enumerate(bed_c):
        door(f"bedroom{i + 1}", "y", 13.25, c, swing=(1, 0))

    # door plates (brass) above the corridor-side of each room door
    for i, c in enumerate(room_c):
        B(c - 0.2, c + 0.2, 1.47, 1.5, 2.55, 2.7, plaque, "plate")
        B(c - 0.2, c + 0.2, -1.5, -1.47, 2.55, 2.7, plaque, "plate")

    # ----------------------------------------------------------- helpers: furniture
    def BL(hx, hy, d, u0, u1, v0, v1, z0, z1, mat, name="part", bevel=0.0):
        """Box in a local frame: u runs from the head (hx,hy) along unit direction d, v is to d's left."""
        dx, dy = d
        def P(u, v):
            return hx + dx * u - dy * v, hy + dy * u + dx * v
        (xa, ya), (xb, yb) = P(u0, v0), P(u1, v1)
        return B(min(xa, xb), max(xa, xb), min(ya, yb), max(ya, yb), z0, z1, mat, name, bevel=bevel)

    def bed(hx, hy, d, double=False, canopy=False, linen_mat=None, blanket=None):
        L, Wd = 2.0, (1.5 if double else 0.95)
        v0, v1 = -Wd / 2, Wd / 2
        BL(hx, hy, d, 0, L, v0, v1, F, F + 0.4, doak, "bed_frame", 0.01)
        BL(hx, hy, d, 0.04, L - 0.04, v0 + 0.04, v1 - 0.04, F + 0.4, F + 0.52, linen_mat or linen, "mattress", 0.02)
        BL(hx, hy, d, 0.9, L - 0.04, v0 + 0.04, v1 - 0.04, F + 0.52, F + 0.57, blanket or red, "blanket")
        for s in ((-1, 1) if double else (0,)):
            vv = s * Wd * 0.22
            BL(hx, hy, d, 0.12, 0.5, vv - 0.3, vv + 0.3, F + 0.52, F + 0.62, parchment, "pillow", 0.03)
        BL(hx, hy, d, -0.08, 0.02, v0 - 0.02, v1 + 0.02, F, F + 1.2, doak, "headboard", 0.01)
        BL(hx, hy, d, L - 0.02, L + 0.06, v0 - 0.02, v1 + 0.02, F, F + 0.7, doak, "footboard", 0.01)
        if canopy:
            for u in (-0.06, L + 0.04):
                for v in (v0 - 0.02, v1 + 0.02):
                    BL(hx, hy, d, u - 0.04, u + 0.04, v - 0.04, v + 0.04, F, F + 2.1, doak, "bedpost", 0.01)
            BL(hx, hy, d, -0.1, L + 0.1, v0 - 0.06, v1 + 0.06, F + 2.1, F + 2.16, doak, "canopy_frame")
            BL(hx, hy, d, -0.08, L + 0.08, v0 - 0.04, v1 + 0.04, F + 2.16, F + 2.19, (blanket or red), "canopy")

    def nightstand(x, y):
        B(x - 0.22, x + 0.22, y - 0.2, y + 0.2, F, F + 0.5, doak, "nightstand", 0.01)
        B(x - 0.25, x + 0.25, y - 0.23, y + 0.23, F + 0.5, F + 0.54, oak, "nightstand_top")
        k.cylinder(0.025, 0.12, loc=(x, y, F + 0.6), material=candle, name="night_candle", verts=6)

    def wardrobe(x0, x1, y0, y1, h=2.0, face="s"):
        B(x0, x1, y0, y1, F, F + h, doak, "wardrobe", 0.01)
        B(x0 - 0.03, x1 + 0.03, y0 - 0.03, y1 + 0.03, F + h, F + h + 0.06, oak, "wardrobe_cornice")
        mid = (x0 + x1) / 2 if face in "sn" else (y0 + y1) / 2
        if face == "s":
            B(mid - 0.015, mid + 0.015, y0 - 0.02, y0, F + 0.1, F + h - 0.1, iron, "wardrobe_seam")
        elif face == "n":
            B(mid - 0.015, mid + 0.015, y1, y1 + 0.02, F + 0.1, F + h - 0.1, iron, "wardrobe_seam")
        elif face == "e":
            B(x1, x1 + 0.02, mid - 0.015, mid + 0.015, F + 0.1, F + h - 0.1, iron, "wardrobe_seam")
        else:
            B(x0 - 0.02, x0, mid - 0.015, mid + 0.015, F + 0.1, F + h - 0.1, iron, "wardrobe_seam")

    def chair(x, y, d):
        BL(x, y, d, -0.2, 0.2, -0.2, 0.2, F + 0.42, F + 0.47, oak, "chair_seat", 0.01)
        BL(x, y, d, -0.2, -0.15, -0.2, 0.2, F + 0.47, F + 0.95, oak, "chair_back", 0.01)
        for u in (-0.17, 0.17):
            for v in (-0.17, 0.17):
                BL(x, y, d, u - 0.025, u + 0.025, v - 0.025, v + 0.025, F, F + 0.42, doak, "chair_leg")

    def table(x0, x1, y0, y1, h=0.75, mat=None):
        B(x0, x1, y0, y1, F + h, F + h + 0.05, mat or oak, "table_top", 0.01)
        for lx in (x0 + 0.06, x1 - 0.06):
            for ly in (y0 + 0.06, y1 - 0.06):
                B(lx - 0.03, lx + 0.03, ly - 0.03, ly + 0.03, F, F + h, doak, "table_leg")

    def rug(x0, x1, y0, y1, base, edge):
        B(x0, x1, y0, y1, F, F + 0.012, base, "rug")
        b = 0.12
        B(x0 + b, x1 - b, y0 + b, y0 + b + 0.04, F + 0.012, F + 0.018, edge, "rug_border")
        B(x0 + b, x1 - b, y1 - b - 0.04, y1 - b, F + 0.012, F + 0.018, edge, "rug_border")
        B(x0 + b, x0 + b + 0.04, y0 + b + 0.04, y1 - b - 0.04, F + 0.012, F + 0.018, edge, "rug_border")
        B(x1 - b - 0.04, x1 - b, y0 + b + 0.04, y1 - b - 0.04, F + 0.012, F + 0.018, edge, "rug_border")

    def chest(x, y, d):
        BL(x, y, d, -0.4, 0.4, -0.25, 0.25, F, F + 0.45, coak, "chest", 0.02)
        BL(x, y, d, -0.42, 0.42, -0.27, 0.27, F + 0.45, F + 0.5, iron, "chest_lid")

    def bookcase(x0, x1, y0, y1, h, face):
        """Open-front bookcase: the long side facing `face` ('n','s','e','w') carries three shelves of books."""
        B(x0, x1, y0, y1, F, F + h, doak, "bookcase", 0.01)
        horiz = face in "ns"
        n = 3
        for s in range(n):
            z = F + 0.35 + s * ((h - 0.5) / n)
            span = (x1 - x0) if horiz else (y1 - y0)
            cnt = int(span / 0.09)
            for b in range(cnt):
                m = book_mats[(b * 5 + s) % len(book_mats)]
                bh = 0.24 + 0.06 * ((b * 3 + s) % 3)
                p0 = (x0 if horiz else y0) + 0.06 + b * ((span - 0.12) / cnt)
                bw = (span - 0.12) / cnt * 0.85
                if face == "s":
                    B(p0, p0 + bw, y0 - 0.12, y0 - 0.005, z, z + bh, m, "book")
                elif face == "n":
                    B(p0, p0 + bw, y1 + 0.005, y1 + 0.12, z, z + bh, m, "book")
                elif face == "e":
                    B(x1 + 0.005, x1 + 0.12, p0, p0 + bw, z, z + bh, m, "book")
                else:
                    B(x0 - 0.12, x0 - 0.005, p0, p0 + bw, z, z + bh, m, "book")
            if face == "s":
                B(x0, x1, y0 - 0.13, y0 - 0.005, z - 0.03, z, oak, "shelf")
            elif face == "n":
                B(x0, x1, y1 + 0.005, y1 + 0.13, z - 0.03, z, oak, "shelf")
            elif face == "e":
                B(x1 + 0.005, x1 + 0.13, y0, y1, z - 0.03, z, oak, "shelf")
            else:
                B(x0 - 0.13, x0 - 0.005, y0, y1, z - 0.03, z, oak, "shelf")

    def settee(x, y, d, length=2.0, mat=None):
        mat = mat or red
        BL(x, y, d, -0.4, 0.4, -length / 2, length / 2, F + 0.18, F + 0.45, mat, "settee_seat", 0.04)
        BL(x, y, d, -0.5, -0.32, -length / 2, length / 2, F + 0.18, F + 0.95, mat, "settee_back", 0.04)
        for s in (-1, 1):
            BL(x, y, d, -0.5, 0.42, s * (length / 2) - 0.08 + (0.0 if s > 0 else 0.0), s * (length / 2) + 0.08, F + 0.18, F + 0.6, doak, "settee_arm", 0.02)
        for s in (-1, 1):
            for u in (-0.42, 0.34):
                BL(x, y, d, u - 0.04, u + 0.04, s * (length / 2 - 0.1) - 0.04, s * (length / 2 - 0.1) + 0.04, F, F + 0.18, doak, "settee_foot")

    def armchair(x, y, d, mat=None):
        mat = mat or navy
        BL(x, y, d, -0.4, 0.4, -0.4, 0.4, F + 0.18, F + 0.45, mat, "chair_seat", 0.04)
        BL(x, y, d, -0.45, -0.3, -0.4, 0.4, F + 0.18, F + 1.0, mat, "chair_back", 0.04)
        for s in (-1, 1):
            BL(x, y, d, -0.45, 0.4, s * 0.4 - 0.06, s * 0.4 + 0.06, F + 0.18, F + 0.62, doak, "chair_arm", 0.02)

    def lamp_stand(x, y, hgt=1.4):
        k.cylinder(0.03, hgt, loc=(x, y, F + hgt / 2), material=brass, name="lamp_pole", verts=8)
        k.cylinder(0.14, 0.04, loc=(x, y, F + 0.02), material=brass, name="lamp_base", verts=10)
        k.sphere(0.09, loc=(x, y, F + hgt + 0.08), material=candle, name="lamp", segments=8)

    def sconce(x, y, face, z=1.9):
        """Wall sconce on a wall whose room-side face normal is `face` (dx, dy)."""
        dx, dy = face
        B(x - 0.04 + dx * 0.05, x + 0.04 + dx * 0.05, y - 0.04 + dy * 0.05, y + 0.04 + dy * 0.05, z - 0.2, z + 0.2, brass, "sconce_arm")
        k.sphere(0.09, loc=(x + dx * 0.12, y + dy * 0.12, z + 0.3), material=candle, name="sconce_lamp", segments=8)

    skulls = Skulls()

    # ----------------------------------------------------------- landing
    B(-19.4, -19.15, -2.9, -1.7, F + 0.9, F + 0.95, doak, "landing_shelf")
    for i in range(3):
        skulls.add(-19.3, -2.6 + i * 0.4, F + 0.95, face_to=(-14, 0), s=0.06)
    sconce(-19.45, 1.6, (1, 0))
    sconce(-19.45, -1.6, (1, 0))
    chair(-17.6, 2.4, (0, -1))
    table(-18.4, -17.4, 2.15, 2.8)
    rug(-19.0, -16.6, -1.0, 1.0, red, gold)

    # ----------------------------------------------------------- corridor
    rug(-15.8, 1.8, -0.7, 0.7, red, gold)                                  # runner
    for px in (xs[0] + 4.375, xs[1] + 4.375, xs[2] + 4.375):
        sconce(px, 1.5, (0, -1))
    for bx in (-13.0, -6.0):                                               # ceiling beams across the corridor
        B(bx - 0.12, bx + 0.12, -1.5, 1.5, H - 0.3, H - 0.02, coak, "beam")
    table(0.0, 1.2, -1.45, -0.95)
    chair(0.6, -0.7, (0, 1))

    # ----------------------------------------------------------- small guest rooms
    for i, c in enumerate(room_c):
        x0, x1 = xs[i], xs[i] + 4.25
        for north in (True, False):
            y_in = 1.75 if north else -1.75           # side next to the corridor
            y_out = 6.0 if north else -6.0            # exterior wall side
            sgn = 1 if north else -1
            left = (i % 2 == 0)
            if north:
                # bed head against the exterior wall, to one side
                bx = x0 + 0.65 if left else x1 - 0.65
                bed(bx, y_out, (0, -1), double=(i % 2 == 1), blanket=(red, navy, green, plum)[i])
                nightstand(x0 + 1.5 if left else x1 - 1.5, y_out - 0.25)
                wardrobe(x1 - 1.0 if left else x0 + 0.1, x1 - 0.1 if left else x0 + 1.0, y_in + 0.1, y_in + 0.6, face="n")
            else:
                bx = x1 - 0.65 if left else x0 + 0.65
                bed(bx, y_out, (0, 1), double=(i % 2 == 0), blanket=(green, plum, red, navy)[i])
                nightstand(x1 - 1.5 if left else x0 + 1.5, y_out + 0.25)
                wardrobe(x0 + 0.1 if left else x1 - 1.0, x0 + 1.0 if left else x1 - 0.1, y_in - 0.6, y_in - 0.1, face="s")
            # small table + chair under the window, rug at the foot of the bed
            wx = c
            table(wx - 0.4, wx + 0.4, y_out - sgn * 0.45 - 0.2 if False else (y_out - 0.75 if north else y_out + 0.15), (y_out - 0.15 if north else y_out + 0.75), h=0.72)
            chair(wx, (y_out - 1.15 if north else y_out + 1.15), (0, 1 if north else -1))
            rug(x0 + 0.9, x1 - 0.9, (y_in + 0.8 if north else y_in - 2.4), (y_in + 2.4 if north else y_in - 0.8), plum if i % 2 else navy, gold)

    # ----------------------------------------------------------- suite: living room
    rug(4.2, 11.4, -4.4, 4.4, red, gold)
    # hearth on the north wall (inner face y = 8.0), centred x = 7.75
    hx = 7.75
    B(hx - 2.6, hx - 1.3, 6.7, 8.0, F, H, granite, "hearth_jamb", 0.01)
    B(hx + 1.3, hx + 2.6, 6.7, 8.0, F, H, granite, "hearth_jamb", 0.01)
    B(hx - 1.3, hx + 1.3, 6.7, 8.0, F + 1.5, H, granite, "hearth_breast", 0.01)
    B(hx - 2.9, hx + 2.9, 5.6, 6.7, F, F + 0.18, granite, "hearth_apron", 0.01)
    B(hx - 1.3, hx + 1.3, 6.7, 8.0, F, F + 0.25, granite, "firebox_floor")
    B(hx - 1.3, hx + 1.3, 7.94, 7.99, F + 0.25, F + 1.5, soot, "soot")
    B(hx - 3.0, hx + 3.0, 6.55, 6.95, F + 1.65, F + 1.8, doak, "mantel", 0.015)
    for i in range(3):
        skulls.add(hx - 1.6 + i * 1.6, 6.78, F + 1.8, face_to=(hx, 0), s=0.1)
    for fx, fy, fh, sw in ((-0.7, 0.0, 0.6, -0.1), (-0.3, 0.1, 0.85, 0.12), (0.1, -0.05, 1.0, -0.09), (0.45, 0.1, 0.8, 0.13), (0.8, 0.0, 0.55, -0.1)):
        flame_tongue(hx + fx, 7.4 + fy, F + 0.3, fh, 0.18, sw, flame, "flame")
        flame_tongue(hx + fx, 7.4 + fy, F + 0.3, fh * 0.6, 0.11, sw * 0.6, flame_core, "flame_core")
    B(hx - 1.0, hx + 1.0, 7.0, 7.8, F + 0.25, F + 0.31, ember, "embers")
    for dy in (-0.3, 0.1):
        k.cylinder(0.11, 1.5, loc=(hx, 7.4 + dy, F + 0.42), rot=(0, 90, 6 * dy * 10), material=coak, name="log", verts=10)
    for sx in (-1, 1):                                                       # fluted pilasters either side
        B(hx + sx * 3.3 - 0.2, hx + sx * 3.3 + 0.2, 7.6, 8.0, F, H - 0.2, oak, "pilaster", 0.01)
        B(hx + sx * 3.3 - 0.26, hx + sx * 3.3 + 0.26, 7.55, 8.0, H - 0.2, H - 0.1, brass, "pilaster_cap")
    # seating around the fire
    settee(hx - 1.9, 3.4, (0, 1), 2.0, red)
    settee(hx + 1.9, 3.4, (0, 1), 2.0, red)
    armchair(4.2, 4.6, (1, 0), navy)
    armchair(11.2, 4.6, (-1, 0), navy)
    table(hx - 0.7, hx + 0.7, 1.8, 2.6, h=0.45, mat=granite)                 # low table
    settee(hx, -3.2, (0, -1), 2.6, green)
    armchair(4.2, -1.2, (1, 0), plum)
    armchair(11.2, -1.2, (-1, 0), plum)
    table(3.0, 3.6, -3.6, -2.6, h=0.7)                                       # side tables with lamps
    lamp_stand(3.3, -3.1, 0.0 + 0.8)
    table(11.9, 12.5, -3.6, -2.6, h=0.7)
    lamp_stand(12.2, -3.1, 0.8)
    for lx, ly in ((3.2, 7.4), (12.3, 7.4)):
        lamp_stand(lx, ly, 1.5)
    # bookcases on the south wall and the west wall around the double door
    bookcase(2.6, 5.4, -7.9, -7.5, 2.4, "n")
    bookcase(10.1, 12.9, -7.9, -7.5, 2.4, "n")
    bookcase(2.6, 3.0, 3.2, 6.2, 2.4, "e")
    bookcase(2.6, 3.0, -6.2, -3.4, 2.4, "e")
    # dark wood wainscot (proud of the plaster) on the living room's long walls
    B(5.45, 10.05, -7.99, -7.95, F, F + 1.1, doak, "wainscot")
    B(5.45, 10.05, -7.99, -7.93, F + 1.1, F + 1.16, oak, "wainscot_cap")
    # chandelier over the rug, hung from a ceiling beam
    for bx in (4.5, 7.75, 11.0):
        B(bx - 0.14, bx + 0.14, -8.0, 8.0, H - 0.34, H - 0.02, coak, "beam", 0.01)
    k.cylinder(0.02, 0.9, loc=(7.75, 0.0, H - 0.34 - 0.45), material=iron, name="chandelier_chain", verts=6)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.9, minor_radius=0.03, major_segments=24, minor_segments=8, location=(7.75, 0, H - 1.0))
    k._finish(bpy.context.active_object, "chandelier_ring", brass, 0)
    for i in range(10):
        a = math.radians(i * 36)
        k.cylinder(0.035, 0.18, loc=(7.75 + 0.9 * math.cos(a), 0.9 * math.sin(a), H - 0.9), material=candle, name="chandelier_candle", verts=6)

    # ----------------------------------------------------------- suite: three bedrooms
    xb0, xb1 = 13.375, 19.5
    # bedroom 1 (south band y -8..-2.825): two single beds
    bed(19.45, -6.6, (-1, 0), blanket=navy)
    bed(19.45, -4.3, (-1, 0), blanket=navy)
    nightstand(19.1, -5.45)
    wardrobe(14.2, 15.8, -7.9, -7.35, face="n")
    chest(15.2, -3.4, (1, 0))
    rug(14.2, 17.4, -6.4, -3.5, plum, gold)
    # bedroom 2 (middle, y -2.575..2.575): the large four-poster
    bed(19.45, 0.0, (-1, 0), double=True, canopy=True, blanket=red)
    nightstand(19.1, -1.3)
    nightstand(19.1, 1.3)
    wardrobe(14.2, 15.8, 1.9, 2.5, face="s")
    chest(16.6, 0.0, (1, 0))
    rug(14.2, 16.8, -1.6, 1.6, green, gold)
    # bedroom 3 (north band y 2.825..8): two single beds and a desk
    bed(19.45, 4.3, (-1, 0), blanket=green)
    bed(19.45, 6.6, (-1, 0), blanket=green)
    nightstand(19.1, 5.45)
    table(14.3, 15.5, 7.2, 7.8, h=0.75)
    chair(14.9, 6.7, (0, 1))
    rug(14.2, 17.4, 3.5, 6.4, navy, gold)

    skulls.finish(bone, soot, k.mat("skull_teeth", (0.88, 0.84, 0.72), roughness=0.55), name="skulls")
