"""Doctor Pimm's veterinary clinic, Lower Ossuary market (anatomist and Splicer). 18 x 12 m interior, three zones:
  west  waiting room: reception desk and ledger, benches, notice board; street door south at x=-6
  centre exam room: examination table under a lamp, instrument cabinet, specimen lab with Pimm's field desk (north), back door south
  east  ward: cages along the north and east walls; Gerald's cage (NE) stands open and empty, bars chewed; his clinic tag is missing
Doors are real swinging nodes. x east, y north.
"""
from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Doctor Pimm's clinic. Gerald's cage (north-east of the ward) is open; the field notebook's slot on Pimm's desk is empty."

IX, IY, T, H = 9.0, 6.0, 0.5, 3.6

LIGHTS = [
    dict(x=-6, y=0, z=2.8, dim=30, bright=10, color="#ffd9a0"),
    dict(x=0, y=-1, z=3.0, dim=40, bright=18, color="#fff0d0"),        # over the exam table
    dict(x=0, y=4, z=2.6, dim=28, bright=9, color="#b6ffd0"),          # specimen lab, pale green
    dict(x=6, y=-2, z=2.8, dim=30, bright=10, color="#ffd9a0"),
    dict(x=6, y=4, z=2.4, dim=25, bright=8, color="#ffb066"),
]


def build(k):
    S = Shop(k)
    M, W, B = S.M, S.W, S.B
    B(-IX, IX, -IY, IY, 0, F, M["floor_oak"], "floor")
    # exterior
    W.wall("x", -IY - T / 2, -IX - T, IX + T, T, H, [(-6, 1.6, 0, 2.5), (0, 1.0, 0, 2.3), (4, 1.2, 1.2, 2.5)], M["ashlar"], name="ext")
    W.frame("x", -IY - T / 2, T, -6, 1.6, 0, 2.5)
    W.frame("x", -IY - T / 2, T, 0, 1.0, 0, 2.3)
    W.window("x", -IY - T / 2, T, 4, w=1.2, sill=1.2, head=2.5)
    W.wall("x", IY + T / 2, -IX - T, IX + T, T, H, [(-6, 1.2, 1.2, 2.5), (6, 1.2, 1.2, 2.5)], M["ashlar"], name="ext")
    for x in (-6, 6):
        W.window("x", IY + T / 2, T, x, w=1.2, sill=1.2, head=2.5)
    W.wall("y", -IX - T / 2, -IY, IY, T, H, [(2, 1.2, 1.2, 2.5)], M["ashlar"], name="ext")
    W.window("y", -IX - T / 2, T, 2, w=1.2, sill=1.2, head=2.5)
    W.wall("y", IX + T / 2, -IY, IY, T, H, [(0, 1.2, 1.2, 2.5)], M["ashlar"], name="ext")
    W.window("y", IX + T / 2, T, 0, w=1.2, sill=1.2, head=2.5)
    for x in (-6, -2, 2, 6):
        B(x - 0.15, x + 0.15, -IY, IY, H - 0.4, H - 0.05, M["coak"], "beam", 0.01)
    # partitions (plaster)
    P = 0.25
    W.wall("y", -3.0, -IY, IY, P, H, [(-2.0, 1.0, 0, 2.2), (3.5, 1.0, 0, 2.2)], M["plaster"], name="part")
    W.wall("y", 3.0, -IY, IY, P, H, [(-2.0, 1.0, 0, 2.2)], M["plaster"], name="part")
    for y in (-2.0, 3.5):
        W.frame("y", -3.0, P, y, 1.0, 0, 2.2)
    W.frame("y", 3.0, P, -2.0, 1.0, 0, 2.2)
    S.door("street", "x", -IY - T / 2, -6, swing=(0, 1), w=1.6)
    S.door("back", "x", -IY - T / 2, 0, swing=(0, 1), w=1.0)
    S.door("waiting_exam", "y", -3.0, -2.0, swing=(1, 0), w=1.0)
    S.door("exam_lab", "y", -3.0, 3.5, swing=(1, 0), w=1.0)
    S.door("exam_ward", "y", 3.0, -2.0, swing=(1, 0), w=1.0)

    # waiting room (west)
    S.table(-7.8, -4.6, 3.2, 4.0, h=1.05, mat=M["doak"])                           # reception desk
    B(-7.6, -7.0, 3.35, 3.85, F + 1.11, F + 1.14, M["paper"], "ledger")
    B(-7.55, -7.05, 3.4, 3.8, F + 1.14, F + 1.17, M["red"], "ledger_cover")
    S.chair(-6.2, 4.7, face="s")
    S.bench(-8.8, -8.4, -4.5, -0.5)
    S.bench(-8.8, -8.4, 0.2, 2.0)
    S.bench(-6.5, -3.6, -5.6, -5.2)
    B(-8.9, -8.8, 4.5, 5.9, F + 1.2, F + 2.4, M["oak"], "notice_board")
    for i in range(5):
        B(-8.8, -8.78, 4.6 + 0.25 * i, 4.78 + 0.25 * i, F + 1.5 + 0.1 * (i % 3), F + 1.9 + 0.1 * (i % 3), M["paper"], "notice")
    S.rug(-7.5, -4.5, -3.0, -0.5, M["green"])
    S.k.cylinder(0.2, 0.1, loc=(-8.4, -5.5, F + 0.05), material=M["clay"], name="pot", verts=10)

    # exam room (centre): table under a lamp, instrument cabinet, sink basin
    B(-1.0, 1.0, -2.0, 0.2, F + 0.82, F + 0.9, M["granite"], "exam_table_top", 0.01)
    for lx in (-0.8, 0.8):
        for ly in (-1.8, 0.0):
            B(lx - 0.07, lx + 0.07, ly - 0.07, ly + 0.07, F, F + 0.82, M["iron"], "exam_leg")
    for y in (-1.5, -0.7):                                                          # restraint straps
        B(-1.02, 1.02, y - 0.04, y + 0.04, F + 0.9, F + 0.93, M["coak"], "strap")
    B(-0.6, 0.6, -2.4, -2.2, F + 0.95, F + 1.0, M["iron"], "tray")
    for i in range(6):
        B(-0.5 + i * 0.2, -0.46 + i * 0.2, -2.35, -2.25, F + 1.0, F + 1.04, M["iron"], "instrument")
    S.k.cylinder(0.02, 1.2, loc=(0, -0.9, H - 0.7), material=M["iron"], name="lamp_stem", verts=6)
    S.k.cylinder(0.35, 0.12, loc=(0, -0.9, H - 1.4), material=M["brass"], name="lamp_shade", verts=14)
    S.k.sphere(0.1, loc=(0, -0.9, H - 1.5), material=M["candle"], name="lamp_bulb", segments=8)
    S.cabinet(-2.8, -1.8, -5.8, -5.4, 2.0, face="n")
    B(1.8, 2.8, -5.8, -5.0, F + 0.8, F + 0.88, M["granite"], "sink_top")
    B(1.9, 2.7, -5.7, -5.1, F + 0.5, F + 0.8, M["water"], "sink_water")
    B(1.8, 2.8, -5.8, -5.0, F, F + 0.8, M["doak"], "sink_base")

    # specimen lab (north of the exam room): jars of specimens, charts, Pimm's field desk with the empty notebook slot
    S.shelf_unit(-2.9, -1.5, 5.4, 5.8, 2.4, "s", rows=4, items="jars", colors=("glass_a", "glass_g", "clay"))
    S.shelf_unit(0.5, 2.9, 5.4, 5.8, 2.4, "s", rows=4, items="jars", colors=("glass_a", "glass_b", "glass_g"))
    S.table(-1.2, 0.4, 3.6, 4.6, h=0.9, mat=M["oak"])                               # Pimm's desk
    B(-0.9, -0.3, 3.8, 4.4, F + 0.96, F + 0.99, M["paper"], "desk_papers")
    B(0.0, 0.3, 3.9, 4.2, F + 0.96, F + 0.97, M["soot"], "notebook_slot")           # the empty spot where the notebook sat
    S.chair(-0.4, 3.0, face="n")
    S.k.cylinder(0.12, 0.04, loc=(0.2, 4.4, F + 0.98), material=M["brass"], name="scale_base", verts=10)
    B(0.0, 0.4, 4.38, 4.42, F + 1.15, F + 1.17, M["brass"], "scale_beam")
    for i, (cx, cy) in enumerate(((-2.6, 2.3), (-2.6, 3.3))):                       # wall charts on the partition (x = -3 face)
        B(-2.87, -2.85, cy, cy + 0.9, F + 1.2, F + 2.4, M["paper"], "chart")
        for r in range(4):
            B(-2.85, -2.83, cy + 0.25, cy + 0.65, F + 1.4 + 0.2 * r, F + 1.46 + 0.2 * r, M["bone"], "chart_rib")
        B(-2.85, -2.83, cy + 0.43, cy + 0.47, F + 1.4, F + 2.2, M["bone"], "chart_spine")
    S.skulls.add(-2.2, 5.5, F + 2.4, face_to=(0, 0), s=0.08)
    S.skulls.add(1.4, 5.5, F + 2.4, face_to=(0, 0), s=0.08)

    # ward (east): cages on the north and east walls, Gerald's open cage in the north-east corner
    for i, (x0, x1) in enumerate(((3.4, 4.8), (5.0, 6.4), (6.6, 8.0))):
        S.cage(x0, x1, 4.4, 5.8, h=0.9, open_front=("s" if i == 2 else None))
        B(x0 + 0.2, x1 - 0.2, 4.6, 5.6, F + 0.08, F + 0.1, M["linen"] if i != 2 else M["paper"], "straw")
    for i, (y0, y1) in enumerate(((-1.2, 0.2), (0.4, 1.8), (2.0, 3.4))):
        S.cage(7.2, 8.7, y0, y1, h=0.9)
        B(7.4, 8.5, y0 + 0.2, y1 - 0.2, F + 0.08, F + 0.1, M["linen"], "straw")
    B(7.2, 7.6, 4.15, 4.4, F + 0.95, F + 1.05, M["plaque"], "tag_gerald")             # 'GERALD' card on the open cage
    S.table(4.0, 6.0, -1.0, -0.3, h=0.85, mat=M["oak"])                              # feed table
    S.crate(4.8, -2.5, 0.6)
    S.barrel(3.8, -3.2)
    S.barrel(8.2, -5.0)
    S.crate(8.0, -4.2, 0.5)
    S.lantern(6, -2, 3.0, hang=0.6)
    S.lantern(-6, 0, 3.0, hang=0.6)
    S.finish()
