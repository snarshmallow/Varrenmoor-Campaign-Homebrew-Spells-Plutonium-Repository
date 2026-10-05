"""Lower Ossuary market warehouse, with the amended door (Quest 1, "The Rat on the Door Plate"). 22 x 14 m interior, 5.5 m high.
North wall: the Custodian Door, a big double door whose rune surround glows; its custodian plate reads S. RATTUS (ACTING) and the
"custodian" glyph in the surround is drawn out of order (it means two things). South wall: loading doors and a man door. Props:
crate stacks, bone carts (Dunmore Kell's route is chalked on the floor), shelves of bone boxes, the night porter's tally desk with a
rat tin. Doors are real swinging nodes. x east, y north.
"""
import math
import random

from _props import F, Shop
from _runes import NAMES, chevron, put

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Warehouse. Quest 1: read the Custodian Door (Stellan, Read Inscription DC 11). Kell's chalked route runs from the south doors to it."

IX, IY, T, H = 11.0, 7.0, 0.6, 5.5

LIGHTS = [
    dict(x=0, y=5.8, z=3.0, dim=40, bright=14, color="#7fc8ff"),             # the amended door's rune glow
    dict(x=-6, y=0, z=4.2, dim=45, bright=16, color="#ffc78a"),
    dict(x=6, y=0, z=4.2, dim=45, bright=16, color="#ffc78a"),
    dict(x=0, y=-4, z=3.6, dim=40, bright=14, color="#ffb066"),
    dict(x=8.5, y=-3.5, z=2.2, dim=20, bright=7, color="#ffd18a"),          # tally desk
]


def rune_surround(S, cx, y_face, r):
    """Carved, glowing Elder Futhark runes in an arch around the door. The 'custodian' glyph is drawn as two runes overlaid in gold:
    it means two things, which is why a rat qualifies."""
    M, k = S.M, S.k
    seq = ["fehu", "uruz", "thurisaz", "ansuz", "raidho", "kenaz", "gebo", "wunjo", "hagalaz", "nauthiz", "isa", "jera", "eihwaz", "perthro", "algiz", "sowilo", "tiwaz"]
    for i, name in enumerate(seq):
        a = math.pi * (0.06 + 0.88 * i / (len(seq) - 1))
        px = cx + 2.9 * math.cos(a)
        pz = F + 0.5 + 3.3 * math.sin(a)
        put(k, M["rune"], name, (px, y_face, pz), "s", h=0.5, width=0.04, thick=0.014, rot_deg=math.degrees(a) - 90)
    # the amended glyph above the lintel: Ansuz and Algiz drawn over each other, in gold
    put(k, M["plaque"], "ansuz", (cx, y_face, F + 4.15), "s", h=0.6, width=0.045, thick=0.016)
    put(k, M["plaque"], "algiz", (cx, y_face, F + 4.15), "s", h=0.6, width=0.045, thick=0.016, offset=0.012)


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    B(-IX, IX, -IY, IY, 0, F, M["paving"], "floor")
    south = [(-6, 3.0, 0, 3.6), (7, 1.2, 0, 2.5)] + [(x, 1.4, 3.2, 4.4) for x in (-10, -2, 2, 10)]
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, south, M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, -6, 3.0, 0, 3.6)
    W.frame("x", -IY - T / 2, T, 7, 1.2, 0, 2.5)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [(0, 3.0, 0, 3.4)], M["ashlar"], name="ext")
    W.frame("x", IY + T / 2, T, 0, 3.0, 0, 3.4)
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [(0, 1.6, 3.2, 4.4)], M["ashlar"], name="ext")
    W.wall("y", IX + T / 2, -IY, IY, T, H, [(0, 1.6, 3.2, 4.4)], M["ashlar"], name="ext")
    for x in (-8, -4, 0, 4, 8):                                           # roof beams and king posts
        B(x - 0.2, x + 0.2, -IY, IY, H - 0.6, H - 0.1, M["coak"], "beam", 0.01)
    for x in (-7.5, 7.5):
        for y in (-3.5, 3.5):
            B(x - 0.25, x + 0.25, y - 0.25, y + 0.25, F, H - 0.6, M["coak"], "post", 0.02)
    for x in (-10, -2, 2, 10):
        pass

    S.door("loading_left", "x", -IY - T / 2, -6.75, swing=(0, 1), w=1.5, h=3.4)
    S.door("loading_right", "x", -IY - T / 2, -5.25, swing=(0, 1), w=1.5, h=3.4, hinge_low=False)
    S.door("man", "x", -IY - T / 2, 7, swing=(0, 1), w=1.2, h=2.4)
    S.door("custodian_left", "x", IY + T / 2, -0.75, swing=(0, -1), w=1.5, h=3.2)
    S.door("custodian_right", "x", IY + T / 2, 0.75, swing=(0, -1), w=1.5, h=3.2, hinge_low=False)
    B(-2.6, 2.6, IY - 0.03, IY - 0.0, F + 3.55, F + 3.75, M["iron"], "door_header")
    rune_surround(S, 0.0, IY, 3.0)
    B(-0.7, 0.7, IY - 0.04, IY - 0.01, F + 1.2, F + 1.5, M["plaque"], "custodian_plate")       # S. RATTUS (ACTING)
    S.skulls.add(-3.2, IY - 0.3, F + 3.2, face_to=(0, 0), s=0.09)
    S.skulls.add(3.2, IY - 0.3, F + 3.2, face_to=(0, 0), s=0.09)
    B(-3.5, -2.9, IY - 0.5, IY, F, F + 3.1, M["granite"], "door_pier", 0.02)
    B(2.9, 3.5, IY - 0.5, IY, F, F + 3.1, M["granite"], "door_pier", 0.02)

    # crate stacks along the west and east walls, shelves of bone boxes
    for j, (y, n) in enumerate(((-5.5, 3), (-3.0, 4), (-0.5, 2), (2.0, 3), (4.3, 4))):
        for i in range(n):
            S.crate(-IX + 0.7 + (i % 2) * 0.65, y + 0.3 * (i // 2), 0.6 + 0.05 * (i % 3), z=F + 0.6 * (i // 3))
    S.shelf_unit(IX - 0.7, IX, -5.5, -1.5, 3.2, "w", rows=5, items="boxes")
    S.shelf_unit(IX - 0.7, IX, 1.5, 5.5, 3.2, "w", rows=5, items="bones")
    for i in range(6):
        S.barrel(-3.0 + 0.7 * (i % 3), 5.4 - 0.7 * (i // 3))
    # bone carts: box, two wheels, handle, a load of bones
    for cx, cy in ((-2.0, -2.0), (4.5, 2.0)):
        B(cx - 0.7, cx + 0.7, cy - 0.4, cy + 0.4, F + 0.35, F + 0.4, M["oak"], "cart_bed", 0.01)
        for sx in (-1, 1):
            B(cx + sx * 0.7 - 0.03, cx + sx * 0.7 + 0.03, cy - 0.4, cy + 0.4, F + 0.4, F + 0.75, M["doak"], "cart_side")
            S.k.cylinder(0.3, 0.06, loc=(cx + sx * 0.78, cy, F + 0.3), rot=(0, 90, 0), material=M["iron"], name="cart_wheel", verts=14)
        B(cx - 0.7, cx + 0.7, cy + 0.4, cy + 0.44, F + 0.4, F + 0.75, M["doak"], "cart_end")
        B(cx - 0.05, cx + 0.05, cy - 1.2, cy - 0.4, F + 0.6, F + 0.66, M["oak"], "cart_handle")
        for i in range(8):
            B(cx - 0.55 + 0.15 * i, cx - 0.45 + 0.15 * i, cy - 0.3 + 0.1 * (i % 3), cy + 0.2 + 0.1 * (i % 3), F + 0.4, F + 0.46 + 0.04 * (i % 3), M["bone"], "cart_bone")
    # the night porter's tally desk with the rat tin
    S.table(7.2, 9.2, -4.4, -3.4, h=0.95, mat=M["doak"])
    B(7.4, 7.9, -4.1, -3.7, F + 1.01, F + 1.1, M["coak"], "rat_tin")
    B(7.45, 7.85, -4.08, -3.72, F + 1.1, F + 1.12, M["plaque"], "rat_tin_tag")
    B(8.2, 8.9, -4.2, -3.6, F + 1.01, F + 1.03, M["paper"], "tally_sheets")
    S.stool(8.2, -2.8)
    # Kell's route: pale chalk chevrons on the floor, from the south doors north toward the custodian door
    for i in range(7):
        chevron(k, M["chalk"], (-6.0 + 0.04 * i, -5.0 + i * 1.7, F + 0.004), 90, size=0.55, width=0.07)
    S.lantern(-6, 0, 4.2, hang=0.9)
    S.lantern(6, 0, 4.2, hang=0.9)
    S.lantern(0, -4, 3.6, hang=0.9)
    S.finish()
