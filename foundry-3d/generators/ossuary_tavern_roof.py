"""Roof and overhead fittings for ossuary_tavern.py: slate gable roof, gable ends, chimney stack, tie beams and
trusses, chandeliers, and the Exchange-style hanging conveyor loop with bone baskets and a drop-tube to the bar.
Separate file so the GM can hide it (top-down play) or show it (outside shots). Z is kept (KEEP_Z), and the XY
footprint is symmetric about the room, so it lines up with the main model when both tiles share a position.
Keep IX, IY, T, WALL_H, hx in sync with ossuary_tavern.py.
"""
import math

import bpy

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
KEEP_Z = True

IX, IY, T, WALL_H = 14.0, 10.0, 0.7, 5.4
HX = -3.0                      # hearth x
PITCH = 28.0
TAN, COS = math.tan(math.radians(PITCH)), math.cos(math.radians(PITCH))
OVER = 0.8                     # eave overhang
EXT_X, EXT_Y = IX + T, IY + T  # outer wall faces
HALF = EXT_Y + OVER            # eave half-width (y)


def z_under(y):
    """Underside height of the roof slab above the wall plate line (y measured from the ridge)."""
    return WALL_H + (EXT_Y - abs(y)) * TAN


def build(k):
    slate = k.tex("slate", "hand_cut_charcoal_ossuary_slate", tile=1.0, rough=0.85)
    ashlar = k.tex("ashlar", "ancient_irregular_ossuary_ashlar", tile=1.6, rough=0.9)
    granite = k.tex("granite", "ossuary_gold_flecked_charcoal_granite", tile=1.2, rough=0.4)
    coak = k.tex("charred", "charred_oak_reinforced_with_bone_straps", tile=1.2, rough=0.8)
    doak = k.tex("dark_oak", "dark_antique_oak", tile=1.2, rough=0.65)
    brass = k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4)
    iron = k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3)
    ibone = k.tex("dry_bone", "dry_indexed_bone", tile=0.8, rough=0.6)
    candle = k.mat("candle", (0.95, 0.85, 0.6), roughness=0.5, emission=(1.0, 0.65, 0.25))

    def B(x0, x1, y0, y1, z0, z1, mat, name="box", bevel=0.0, rot=(0, 0, 0)):
        return k.box((x1 - x0, y1 - y0, z1 - z0), loc=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2),
                     rot=rot, material=mat, name=name, bevel=bevel)

    # Four 2 cm pegs at floor level under the eave corners: they put the model's bounding box on the ground, so a
    # Foundry tile for this file grounds and scales exactly like any other model (the lowest real part hangs at 1.75 m).
    for sx in (-1, 1):
        for sy in (-1, 1):
            B(sx * 15.4 - 0.01, sx * 15.4 + 0.01, sy * 11.4 - 0.01, sy * 11.4 + 0.01, 0, 0.02, iron, "ground_peg")

    # ----------------------------------------------------------- roof slabs
    slab_len = HALF / COS + 0.1
    roof_len_x = 2 * (EXT_X + OVER)
    for side in (-1, 1):                      # -1 south slope, +1 north slope
        yc = side * HALF / 2
        zc = z_under(yc) + 0.125 / COS
        B(-roof_len_x / 2, roof_len_x / 2, yc - slab_len / 2, yc + slab_len / 2, zc - 0.125, zc + 0.125, slate,
          "roof_slab", rot=(-side * PITCH, 0, 0))
    ridge_z = z_under(0)
    B(-roof_len_x / 2, roof_len_x / 2, -0.3, 0.3, ridge_z + 0.15, ridge_z + 0.45, iron, "ridge_cap", bevel=0.02)

    # gable-end walls (triangular prisms)
    def gable(xc):
        pts = [(-EXT_Y, WALL_H), (EXT_Y, WALL_H), (0.0, ridge_z)]
        verts = [(xc - T / 2, y, z) for y, z in pts] + [(xc + T / 2, y, z) for y, z in pts]
        faces = [(0, 2, 1), (3, 4, 5), (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5)]
        me = bpy.data.meshes.new("gable")
        me.from_pydata(verts, [], faces)
        ob = bpy.data.objects.new("gable", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(ashlar)
        return ob
    for xc in (-(IX + T / 2), IX + T / 2):
        gable(xc)

    # ----------------------------------------------------------- chimney stack above the hearth
    B(HX - 1.3, HX + 1.3, 8.5, IY + 0.1, WALL_H, 9.2, ashlar, "chimney")
    B(HX - 1.45, HX + 1.45, 8.4, IY + 0.1, 9.2, 9.5, granite, "chimney_cap", bevel=0.02)

    # ----------------------------------------------------------- trusses
    xs = [-13.5 + i * 3.375 for i in range(9)]
    ang_strut = math.degrees(math.atan2(1.8, 3.4))
    for x in xs:
        B(x - 0.17, x + 0.17, -EXT_Y + 0.5, EXT_Y - 0.5, WALL_H, WALL_H + 0.4, coak, "tie_beam", bevel=0.02)  # ends stay under the slab
        B(x - 0.14, x + 0.14, -0.14, 0.14, WALL_H + 0.4, ridge_z - 0.5, coak, "king_post", bevel=0.01)
        for side in (-1, 1):
            yc = side * (EXT_Y / 2)
            zc = z_under(yc) - 0.17 / COS
            B(x - 0.1, x + 0.1, yc - (EXT_Y / COS) / 2, yc + (EXT_Y / COS) / 2, zc - 0.15, zc + 0.15, coak, "rafter",
              rot=(-PITCH if side > 0 else PITCH, 0, 0))
            B(x - 0.08, x + 0.08, side * 1.7 - 1.92, side * 1.7 + 1.92, 6.7 - 0.1, 6.7 + 0.1, coak, "strut",
              rot=(-ang_strut if side > 0 else ang_strut, 0, 0))
    B(-EXT_X, EXT_X, -0.2, 0.2, ridge_z - 0.5, ridge_z - 0.05, coak, "ridge_beam", bevel=0.02)

    # ----------------------------------------------------------- chandeliers
    def torus(major, minor, loc, mat, name):
        bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=24, minor_segments=8, location=loc)
        return k._finish(bpy.context.active_object, name, mat, 0)

    for cx, cy in ((-6.75, 0.0), (0.0, 0.0), (-3.375, 6.0)):
        ring_z = 4.0
        B(cx - 0.02, cx + 0.02, cy - 0.02, cy + 0.02, ring_z, WALL_H, iron, "chandelier_chain")
        torus(0.8, 0.03, (cx, cy, ring_z), iron, "chandelier_ring")
        torus(0.35, 0.025, (cx, cy, ring_z + 0.25), iron, "chandelier_hub")
        for i in range(8):
            a = math.radians(i * 45)
            k.cylinder(0.035, 0.18, loc=(cx + 0.8 * math.cos(a), cy + 0.8 * math.sin(a), ring_z + 0.12), material=candle, name="chandelier_candle", verts=6)

    # ----------------------------------------------------------- hanging conveyor loop over the bar side
    rx0, rx1, ry0, ry1, rz = 3.375, 10.125, -5.5, 7.0, 4.7
    for y in (ry0, ry1):
        B(rx0, rx1, y - 0.06, y + 0.06, rz - 0.06, rz + 0.06, iron, "rail")
    for x in (rx0, rx1):
        B(x - 0.06, x + 0.06, ry0, ry1, rz - 0.06, rz + 0.06, iron, "rail")
    for x in (rx0, 6.75, rx1):                 # chains up to the tie beams
        for y in (ry0, ry1):
            B(x - 0.015, x + 0.015, y - 0.015, y + 0.015, rz + 0.06, WALL_H, iron, "rail_chain")
    for y in (-2.0, 2.0):
        for x in (rx0, rx1):
            B(x - 0.015, x + 0.015, y - 0.015, y + 0.015, rz + 0.06, WALL_H, iron, "rail_chain")
    per = 2 * ((rx1 - rx0) + (ry1 - ry0))
    n = 14
    for i in range(n):                         # bone baskets riding the loop
        t = (i + 0.5) * per / n
        if t < rx1 - rx0:
            bx, by = rx0 + t, ry0
        elif t < (rx1 - rx0) + (ry1 - ry0):
            bx, by = rx1, ry0 + (t - (rx1 - rx0))
        elif t < 2 * (rx1 - rx0) + (ry1 - ry0):
            bx, by = rx1 - (t - (rx1 - rx0) - (ry1 - ry0)), ry1
        else:
            bx, by = rx0, ry1 - (t - 2 * (rx1 - rx0) - (ry1 - ry0))
        B(bx - 0.01, bx + 0.01, by - 0.01, by + 0.01, rz - 0.5, rz - 0.06, iron, "basket_hanger")
        B(bx - 0.24, bx + 0.24, by - 0.17, by + 0.17, rz - 0.78, rz - 0.5, ibone, "bone_basket", bevel=0.01)
        B(bx - 0.26, bx + 0.26, by - 0.19, by + 0.19, rz - 0.56, rz - 0.45, iron, "basket_rim")   # rim stands proud of the basket top (no shared plane)
    # brass drop-tube from the loop to the bar-top stub (stub is at 9.8, -4.0 in the main model)
    B(9.8 - 0.35, 10.125 + 0.1, -4.0 - 0.09, -4.0 + 0.09, rz - 0.09, rz + 0.09, brass, "tube_branch", bevel=0.01)
    k.cylinder(0.1, rz - 1.75, loc=(9.8, -4.0, 1.75 + (rz - 1.75) / 2), material=brass, name="drop_tube", verts=12)
    for z in (2.4, 3.3, 4.2):
        k.cylinder(0.13, 0.06, loc=(9.8, -4.0, z), material=brass, name="tube_collar", verts=12)
