"""Quillibus "Quill" Scratch's rune workshop, Lower Ossuary market: a rune repairer. 14 x 10 m interior, 3.8 m ceiling.
Slate-board walls covered in chalk glyphs, a door on trestles with its runes half-redrawn, tracing desks, chalk sticks, glyph tablets on
shelves (the COPY incident is on the east wall: a crooked row of identical chalk sticks), a work lamp. Street door south at x=0.
x east, y north.
"""
import math

from _props import F, Shop
from _runes import NAMES, put

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Quill's rune workshop. The door on the trestles is a repair job; the board east shows the COPY chalk."

IX, IY, T, H = 7.0, 5.0, 0.5, 3.8

LIGHTS = [
    dict(x=0, y=0, z=3.0, dim=40, bright=16, color="#ffe3b0"),
    dict(x=-4.5, y=2.5, z=2.6, dim=26, bright=9, color="#cfe3ff"),       # chalk-board side, cooler
    dict(x=4.5, y=2.0, z=2.6, dim=26, bright=9, color="#ffd18a"),
    dict(x=-0.5, y=-1.8, z=1.6, dim=18, bright=6, color="#6fc3ff"),      # the repair glows faintly blue
]


def glyph(S, x, y, face, seed, mat=None, size=0.45, z=F + 1.6):
    """A real Elder Futhark rune, chalked on a board. face = 'n','s','e','w' (the side the viewer stands on)."""
    mat = mat or S.M["chalk"]
    put(S.k, mat, NAMES[seed % len(NAMES)], (x, y, z), face, h=size * 1.3, width=0.03, thick=0.012)


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    B(-IX, IX, -IY, IY, 0, F, M["paving"], "floor")
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, [(0, 1.6, 0, 2.5), (-4.5, 1.2, 1.3, 2.7), (4.5, 1.2, 1.3, 2.7)], M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, 0, 1.6, 0, 2.5)
    for x in (-4.5, 4.5):
        W.window("x", -IY - T / 2, T, x, w=1.2, sill=1.3, head=2.7)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [(0, 1.0, 0, 2.3)], M["ashlar"], name="ext")
    W.frame("x", IY + T / 2, T, 0, 1.0, 0, 2.3)
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [], M["ashlar"], name="ext")
    W.wall("y", IX + T / 2, -IY, IY, T, H, [(-1.5, 1.2, 1.3, 2.7)], M["ashlar"], name="ext")
    W.window("y", IX + T / 2, T, -1.5, w=1.2, sill=1.3, head=2.7)
    for x in (-5, -2.5, 0, 2.5, 5):
        B(x - 0.14, x + 0.14, -IY, IY, H - 0.4, H - 0.05, M["coak"], "beam", 0.01)
    S.door("street_left", "x", -IY - T / 2, -0.4, swing=(0, 1), w=0.8)
    S.door("street_right", "x", -IY - T / 2, 0.4, swing=(0, 1), w=0.8, hinge_low=False)
    S.door("back", "x", IY + T / 2, 0, swing=(0, -1), w=1.0)

    # slate boards along the north and west walls, covered in glyphs
    B(-IX, IX, IY - 0.04, IY - 0.01, F + 0.9, F + 3.0, M["board"], "board_n")
    B(-IX + 0.01, -IX + 0.04, -IY + 0.5, IY - 0.2, F + 0.9, F + 3.0, M["board"], "board_w")
    for i in range(14):
        glyph(S, -6.4 + i * 0.9, IY - 0.04, "s", i, z=F + 1.4 + 0.5 * (i % 3))
    for i in range(7):
        glyph(S, -IX + 0.04, -3.5 + i * 1.0, "e", 100 + i, z=F + 1.5 + 0.5 * (i % 3))
    B(-IX, IX, IY - 0.12, IY - 0.04, F + 0.85, F + 0.9, M["oak"], "board_ledge")
    for i in range(12):                                                   # chalk sticks on the ledge
        B(-6.0 + i * 1.0, -5.92 + i * 1.0, IY - 0.2, IY - 0.04, F + 0.9, F + 0.93, M["chalk"], "chalk_stick")

    # the door on trestles (a repair job), glyphs half redrawn along its face
    for sx in (-1.8, 1.8):
        B(-0.3 + sx - 0.1, -0.3 + sx + 0.1, -2.6, -1.0, F, F + 0.75, M["doak"], "trestle")
        B(-0.3 + sx - 0.3, -0.3 + sx + 0.3, -2.1, -1.5, F + 0.72, F + 0.78, M["doak"], "trestle_top")
    B(-2.3, 1.7, -2.4, -1.2, F + 0.78, F + 0.9, M["coak"], "door_on_trestles", 0.01)
    for i in range(7):                                                    # runes laid along the door: the first four redrawn (glowing), three still chalk
        put(S.k, M["rune"] if i < 4 else M["chalk"], ("algiz", "tiwaz", "ansuz", "othala", "wunjo", "kenaz", "isa")[i], (-1.9 + i * 0.55, -1.8, F + 0.9), "up", h=0.5, width=0.035, thick=0.012)
    B(1.7, 2.1, -1.9, -1.7, F + 0.78, F + 0.84, M["iron"], "door_hinge_plate")

    # tracing desks with lamps; a stool each
    for (x0, x1, y0, y1) in ((-5.4, -3.2, 1.3, 2.3), (3.2, 5.4, 1.0, 2.0)):
        S.table(x0, x1, y0, y1, h=0.95, mat=M["oak"])
        B(x0 + 0.2, x1 - 0.2, y0 + 0.2, y1 - 0.2, F + 1.01, F + 1.03, M["paper"], "tracing_paper")
        S.k.cylinder(0.05, 0.3, loc=((x0 + x1) / 2 + 0.7, y1 - 0.2, F + 1.17), material=M["brass"], name="desk_lamp", verts=8)
        S.k.sphere(0.07, loc=((x0 + x1) / 2 + 0.7, y1 - 0.2, F + 1.4), material=M["candle"], name="desk_lamp_flame", segments=8)
        S.stool((x0 + x1) / 2, y0 - 0.6)

    # glyph tablets on shelves (east wall) and the COPY chalk row
    S.shelf_unit(IX - 0.6, IX, 0.5, 4.0, 2.4, "w", rows=4, items="boxes")
    for i in range(10):
        B(IX - 0.07, IX - 0.05, -4.5 + i * 0.19 + 0.02 * (i % 2), -4.36 + i * 0.19 + 0.02 * (i % 2), F + 1.0 + 0.06 * (i % 2), F + 1.5 + 0.06 * (i % 2), M["chalk"], "copy_chalk")
    S.table(-0.6, 0.6, 2.6, 3.4, h=0.85, mat=M["doak"])
    B(-0.4, 0.4, 2.8, 3.2, F + 0.91, F + 0.94, M["paper"], "worn_plan")
    S.crate(-6.2, -3.8)
    S.crate(-6.2, -3.1, 0.5)
    S.barrel(-5.4, -4.4, 0.3, 0.8)
    S.barrel(6.2, -4.0, 0.3, 0.8)
    S.k.cylinder(0.3, 0.05, loc=(0, 0.0, F + 0.03), material=M["chalk"], name="chalk_circle", verts=24)   # a practice circle
    S.k.cylinder(0.26, 0.052, loc=(0, 0.0, F + 0.03), material=M["floor_oak"] if False else M["paving"], name="chalk_circle_inner", verts=24)
    S.lantern(-4.5, 2.5, 3.0, hang=0.8)
    S.lantern(4.5, 2.0, 3.0, hang=0.8)
    S.finish()
