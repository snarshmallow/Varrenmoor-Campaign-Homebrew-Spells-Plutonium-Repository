"""Ossuary Exchange market, exterior v3 ("old city" ring). A 150-ft circular plaza (paving radius 22.86 m, clear below 2.2 m inside
15.24 m) ringed by 36 wedge-shaped plots of party-wall buildings: neighbours share exact radial walls, so no gaps show between
them. Buildings vary in width (1 to 3 plots), height (3 to 5 floors), roof (gable to the plaza or ridge along it), tint and depth.
Signed storefronts for the Exchange's shops and the inn: Mottle's inn (skull and tankard), Brokka's forge (anvil), Pimm's clinic
(bone and paw), Quill's rune shop (glyph board), the post office (horn), the Lower-market warehouse, the Exchange guildhall,
plus the eastern gate (to Mavis's road) and the south arrival portal (Exchange hallway). Overhead conveyor is a light hub-and-spoke.
Cheaper than the 178k-triangle v2: about 40k triangles, 8 or so materials. Shop doors are real swinging nodes. x east, y north.
"""
import math
import random

import bmesh
import bpy
from _parts import Skulls, bm_to_obj
from _props import materials
from _runes import RUNES

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Market exterior v3. Plan angles (CCW from east): gate 0, forge 30-50, guildhall 70-100, clinic 120-140, rune shop 170-190, post 210-230, arrival 270, inn 280-300, warehouse 330-350."

F = 0.1
R0 = 22.9             # facade tangent radius (paving radius 22.86)
UNIT = 10.0           # degrees per plot unit

# (first unit, number of units, kind). Units run CCW from east; 36 units.
PLAN = [
    (0, 1, "gate"), (1, 2, "house"), (3, 2, "forge"), (5, 2, "house"), (7, 3, "guild"), (10, 2, "house"), (12, 2, "clinic"),
    (14, 3, "house"), (17, 2, "rune"), (19, 2, "house"), (21, 2, "post"), (23, 3, "house"), (26, 1, "house"), (27, 1, "arrival"),
    (28, 2, "inn"), (30, 3, "house"), (33, 2, "warehouse"), (35, 1, "house"),
]

LIGHTS = []


def build(k):
    rng = random.Random(23)
    M = materials(k)
    tints = [None, (1.0, 0.9, 0.75), (0.8, 0.86, 0.94), (0.82, 0.88, 0.7), (0.95, 0.8, 0.72)]
    plasters = [k.tex(f"plaster_t{i}", "calcified_ancient_lime_and_bone_mortar", tile=1.5, rough=0.95, tint=t) if t else M["plaster"] for i, t in enumerate(tints)]
    ashlar, slate, oak, doak, coak, iron, brass, bone = M["ashlar"], M["slate"], M["oak"], M["doak"], M["coak"], M["iron"], M["brass"], M["bone"]
    glass = k.mat("dark_glass", (0.03, 0.05, 0.07), roughness=0.15)
    cloths = [k.mat(f"awning{i}", c, roughness=0.95) for i, c in enumerate(((0.3, 0.06, 0.05), (0.06, 0.1, 0.22), (0.07, 0.2, 0.12), (0.4, 0.3, 0.1)))]
    skulls = Skulls()

    def box(cx, cy, cz, sx, sy, sz, mat, name, rotz=0.0, rotx=0.0, roty=0.0):
        return k.box((sx, sy, sz), loc=(cx, cy, cz), rot=(rotx, roty, rotz), material=mat, name=name)

    def _ccw(pts):
        """Return the points in counter-clockwise order (seen from above) so extruded side faces point outward."""
        area = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
        return pts if area > 0 else pts[::-1]

    def prism(pts, z0, z1, mat, name):
        pts = _ccw(pts)
        bm = bmesh.new()
        lo = [bm.verts.new((x, y, z0)) for x, y in pts]
        hi = [bm.verts.new((x, y, z1)) for x, y in pts]
        n = len(pts)
        bm.faces.new(hi)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        return bm_to_obj(bm, name, mat)

    def poly(pts, mat, name, want=(0, 0, 1)):
        """A single face whose normal is forced toward `want` (winding varies with the plot frame)."""
        bm = bmesh.new()
        f = bm.faces.new([bm.verts.new(p) for p in pts])
        f.normal_update()
        n = f.normal
        if n.x * want[0] + n.y * want[1] + n.z * want[2] < 0:
            f.normal_flip()
        return bm_to_obj(bm, name, mat)

    # ------------------------------------------------------------------ plaza
    k.cylinder(R0 - 0.04, F, loc=(0, 0, F / 2), material=M["paving"], name="plaza", verts=96)
    k.cylinder(15.3, 0.012, loc=(0, 0, F + 0.006), material=M["bone"], name="ring_edge", verts=96)
    k.cylinder(15.1, 0.012, loc=(0, 0, F + 0.012), material=k.tex("inlay", "dark_flagstone_with_structural_bone_inlay", tile=2.4, rough=0.85), name="ring_disc", verts=96)
    k.cylinder(R0 + 14.0, 0.06, loc=(0, 0, 0.03), material=M["slate"], name="ground_under", verts=96)

    # ------------------------------------------------------------------ one building plot
    class Plot:
        def __init__(self, a0, a1, depth):
            self.a0, self.a1 = math.radians(a0), math.radians(a1)
            self.am = (self.a0 + self.a1) / 2
            self.half = (self.a1 - self.a0) / 2
            self.depth = depth
            self.w0 = 2 * R0 * math.tan(self.half)
            self.w1 = 2 * (R0 + depth) * math.tan(self.half)
            self.deg = math.degrees(self.am)

        def P(self, u, v, z):
            c, s = math.cos(self.am), math.sin(self.am)
            return ((R0 + v) * c - u * s, (R0 + v) * s + u * c, z)

        def LB(self, u0, u1, v0, v1, z0, z1, mat, name, tilt=0.0, tilty=0.0):
            x, y, z = self.P((u0 + u1) / 2, (v0 + v1) / 2, (z0 + z1) / 2)
            return box(x, y, z, v1 - v0, u1 - u0, z1 - z0, mat, name, rotz=self.deg, rotx=tilt, roty=tilty)

        def footprint(self):
            return [self.P(-self.w0 / 2, 0, 0)[:2], self.P(self.w0 / 2, 0, 0)[:2], self.P(self.w1 / 2, self.depth, 0)[:2], self.P(-self.w1 / 2, self.depth, 0)[:2]]

    def roof(pl, H, hr, style, mat, wall=None):
        w0, w1, d = pl.w0, pl.w1, pl.depth
        if style == "gable":            # ridge along v (gable to the plaza)
            A, B_, C, D = pl.P(-w0 / 2, 0, H), pl.P(w0 / 2, 0, H), pl.P(w1 / 2, d, H), pl.P(-w1 / 2, d, H)
            RF, RB = pl.P(0, 0, H + hr), pl.P(0, d, H + hr)
            poly([A, RF, RB, D], mat, "roof_l")
            poly([B_, C, RB, RF], mat, "roof_r")
            if wall:
                fx, fy, _ = pl.P(0, -1, 0)
                ox, oy, _ = pl.P(0, 0, 0)
                poly([A, B_, RF], wall, "gable_front", (fx - ox, fy - oy, 0))
                poly([D, C, RB], wall, "gable_back", (ox - fx, oy - fy, 0))
            return
        # ridge along u: slopes toward the plaza and away
        A, B_, C, D = pl.P(-w0 / 2, 0, H), pl.P(w0 / 2, 0, H), pl.P(w1 / 2, d, H), pl.P(-w1 / 2, d, H)
        vm = d / 2
        RL, RR = pl.P(-(w0 + w1) / 4, vm, H + hr), pl.P((w0 + w1) / 4, vm, H + hr)
        poly([A, B_, RR, RL], mat, "roof_front")
        poly([C, D, RL, RR], mat, "roof_back")
        if wall:
            lx, ly, _ = pl.P(-1, 0, 0)
            ox, oy, _ = pl.P(0, 0, 0)
            poly([A, D, RL], wall, "gable_left", (lx - ox, ly - oy, 0))
            poly([B_, C, RR], wall, "gable_right", (ox - lx, oy - ly, 0))

    def window(pl, u, z, w=0.95, h=1.35, shutters=True, tint=0):
        pl.LB(u - w / 2 - 0.08, u + w / 2 + 0.08, -0.11, -0.01, z - 0.08, z + h + 0.08, doak, "win_frame")
        pl.LB(u - w / 2, u + w / 2, -0.06, -0.03, z, z + h, glass, "win_glass")
        pl.LB(u - w / 2 - 0.12, u + w / 2 + 0.12, -0.2, -0.05, z - 0.14, z - 0.06, ashlar, "win_sill")
        if shutters:
            for sx in (-1, 1):
                pl.LB(u + sx * (w / 2 + 0.2) - 0.18, u + sx * (w / 2 + 0.2) + 0.18, -0.09, -0.04, z, z + h, doak, "shutter")

    def facade(pl, floors, plaster, kind="house", door_id=None):
        """Ground-floor ashlar with a shop opening, timber-framed upper floors, windows, awning, chimney."""
        G, FL = 3.6, 3.0
        H = G + FL * (floors - 1)
        pl.LB(-pl.w0 / 2, pl.w0 / 2, -0.02, 0.0 + 0.01, 0.0, G, ashlar, "ground_face") if False else None
        # ground floor face (ashlar slab proud 6 cm) and upper timber frame lines
        pl.LB(-pl.w0 / 2 + 0.05, pl.w0 / 2 - 0.05, -0.06, 0.0, F, G, ashlar, "ground_face")
        for f in range(1, floors):
            z0 = G + FL * (f - 1)
            pl.LB(-pl.w0 / 2 + 0.03, pl.w0 / 2 - 0.03, -0.25, -0.02, z0 - 0.12, z0 + 0.12, coak, "floor_beam")        # jetty ledge / floor beam
            n = max(2, int(pl.w0 / 1.5))
            for i in range(n + 1):
                u = -pl.w0 / 2 + 0.08 + i * (pl.w0 - 0.16) / n
                pl.LB(u - 0.07, u + 0.07, -0.09, 0.0, z0 + 0.12, z0 + FL - 0.12, coak, "post")
            for i in range(n):
                u0 = -pl.w0 / 2 + 0.08 + i * (pl.w0 - 0.16) / n
                um = u0 + (pl.w0 - 0.16) / n / 2
                window(pl, um, z0 + 0.8, w=min(0.95, (pl.w0 - 0.16) / n - 0.5), shutters=(i + f) % 2 == 0)
                if rng.random() < 0.3:                                             # diagonal brace
                    pl.LB(um - 0.5, um + 0.5, -0.09, 0.0, z0 + 2.0, z0 + 2.08, coak, "brace", tilt=0.0)
        pl.LB(-pl.w0 / 2 + 0.03, pl.w0 / 2 - 0.03, -0.25, -0.02, H - 0.15, H + 0.1, coak, "eave_beam")
        return H

    def storefront(pl, kind, door_id=None, wide=2.2):
        """Shop opening in the ground floor: framed double door, big shop window(s), awning."""
        G = 3.6
        u0 = 0.0
        pl.LB(u0 - wide / 2 - 0.15, u0 + wide / 2 + 0.15, -0.14, -0.04, F, 2.9, doak, "door_frame")
        pl.LB(u0 - wide / 2, u0 + wide / 2, -0.08, -0.05, F, 2.75, doak, "door_recess")
        # shop windows either side
        for sx in (-1, 1):
            cu = sx * (wide / 2 + 0.2 + 1.1)
            if abs(cu) + 0.8 < pl.w0 / 2:
                pl.LB(cu - 0.9, cu + 0.9, -0.12, -0.03, 0.9, 2.5, brass, "shop_frame")
                pl.LB(cu - 0.8, cu + 0.8, -0.09, -0.06, 1.0, 2.4, glass, "shop_glass")
        # awning
        cloth = cloths[rng.randrange(4)]
        x, y, z = pl.P(0, -0.6, 2.95)                        # low and short, so it never hides the shop sign above
        wdt = min(pl.w0 - 0.6, 4.2)
        box(x, y, z, 1.2, wdt, 0.05, cloth, "awning", rotz=pl.deg, roty=-14.0)
        return u0

    def shop_door(pl, door_id, width=1.0):
        hx, hy, _ = pl.P(-width / 2, -0.065, 0)
        k.door(width - 0.02, 2.55, hinge=(hx, hy, F), yaw_deg=pl.deg + 90, swing=(math.cos(pl.am), math.sin(pl.am)), leaf_mat=coak, trim_mat=iron, door_id=door_id)

    def lantern(pl, u, z, color_key="candle", v=-0.35):
        x, y, zz = pl.P(u, v, z)
        k.sphere(0.1, loc=(x, y, zz), material=M[color_key], name="lantern", segments=8)
        box(*pl.P(u, v / 2, z + 0.12)[:3], -v + 0.04 if v < 0 else v, 0.05, 0.05, iron, "lantern_arm", rotz=pl.deg)

    # ------------------------------------------------------------------ signs
    def sign(pl, kind, z=3.55, u=0.0):
        """Flush shop-name board (text texture, optional icon) above the awning, plus a lit bracket lantern at its side."""
        hw, hh = 1.4, 0.49
        z0, z1 = z - hh, z + hh
        pl.LB(u - hw - 0.06, u + hw + 0.06, -0.34, -0.02, z0 - 0.06, z1 + 0.06, oak, "sign_board")     # backing, clear of the floor beam
        mat = _image_material(k, f"sign_{kind}", f"sign_{kind}.png")
        verts = [pl.P(u - hw, -0.345, z0), pl.P(u + hw, -0.345, z0), pl.P(u + hw, -0.345, z1), pl.P(u - hw, -0.345, z1)]
        me = bpy.data.meshes.new(f"sign_{kind}")
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for li, uvc in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[li].uv = uvc
        me.update()
        ob = bpy.data.objects.new(f"sign_{kind}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        # lantern on a short bracket beside the board
        pl.LB(u + hw + 0.1, u + hw + 0.14, -0.9, -0.02, z + 0.3, z + 0.34, iron, "bracket_arm")
        x, y, zz = pl.P(u + hw + 0.12, -0.9, z + 0.18)
        k.sphere(0.12, loc=(x, y, zz), material=M["candle"], name="bracket_lantern", segments=8)
        LIGHTS.append(dict(x=x, y=y, z=zz, dim=30, bright=10, color={"inn": "#ffb066", "forge": "#ff8a2a", "clinic": "#d6ffe0", "rune": "#7fc8ff",
                                                                      "post": "#ffd9a0", "guild": "#ffe6b0", "warehouse": "#ffc78a"}.get(kind, "#ffb066")))

    # ------------------------------------------------------------------ gate and arrival portal (tunnels through the ring)
    def tunnel(pl, name, door_ids=None):
        G = 5.0
        w = 3.6
        d = pl.depth
        pl.LB(-pl.w0 / 2, -w / 2, 0, d, 0, 11, ashlar, f"{name}_pier_l")
        pl.LB(w / 2, pl.w0 / 2, 0, d, 0, 11, ashlar, f"{name}_pier_r")
        pl.LB(-w / 2, w / 2, 0, d, G, 11, ashlar, f"{name}_lintel")
        pl.LB(-w / 2 - 0.2, w / 2 + 0.2, -0.3, 0.0, G - 0.5, G + 0.2, coak, f"{name}_arch_beam")
        for sx in (-1, 1):
            pl.LB(sx * (w / 2 + 0.1) - 0.12, sx * (w / 2 + 0.1) + 0.12, -0.3, 0.0, F, G - 0.5, granite_ := M["granite"], f"{name}_jamb")
        # lanterns either side
        for sx in (-1, 1):
            x, y, zz = pl.P(sx * (w / 2 + 0.6), -0.4, 3.0)
            k.sphere(0.12, loc=(x, y, zz), material=M["candle"], name="gate_lantern", segments=8)
        x, y, zz = pl.P(0, -1.0, 3.2)
        LIGHTS.append(dict(x=x, y=y, z=zz, dim=40, bright=14, color="#ffb066"))
        roof(pl, 11, 2.6, "gable", slate)
        prism(pl.footprint(), 11 - 0.01, 11, slate, f"{name}_top") if False else None

    # ------------------------------------------------------------------ build the ring
    for (u0, n, kind) in PLAN:
        a0, a1 = u0 * UNIT, (u0 + n) * UNIT
        depth = rng.uniform(9.0, 12.5)
        pl = Plot(a0, a1, depth)
        if kind in ("gate", "arrival"):
            tunnel(pl, kind)
            if kind == "arrival":
                for i, (c_, sgn) in enumerate(((-0.9, 1), (0.9, -1))):
                    hx, hy, _ = pl.P(c_ * 1.0, -0.2, 0)
                    k.door(1.7, 4.2, hinge=pl.P(c_ * 1.8 if False else (-1.8 if i == 0 else 1.8), 0.5, F)[:2] + (F,), yaw_deg=pl.deg + (90 if i == 0 else -90) if False else pl.deg + (-90 if i == 0 else 90),
                           swing=(math.cos(pl.am), math.sin(pl.am)), leaf_mat=coak, trim_mat=iron, door_id=("arrival_left", "arrival_right")[i]) if False else None
            continue
        floors = {"guild": 4, "inn": 4, "house": rng.choice((3, 3, 4, 4, 5)), "forge": 3, "clinic": 4, "rune": 3, "post": 3, "warehouse": 3}[kind]
        plaster = plasters[rng.randrange(len(plasters))] if kind == "house" else {"inn": plasters[1], "guild": plasters[0], "forge": plasters[2], "clinic": plasters[3],
                                                                                    "rune": plasters[2], "post": plasters[4], "warehouse": plasters[0]}[kind]
        H = facade(pl, floors, plaster, kind)
        # the solid body (plaster) and its left radial party wall are the prism; one prism per plot, sharing exact side planes
        prism(pl.footprint(), 0.0, H + 0.0, plaster, f"{kind}_body")
        style = "gable" if (kind in ("house", "inn", "guild") and rng.random() < 0.65) or kind == "guild" else "ridge"
        roof(pl, H, rng.uniform(2.6, 4.2) if style == "gable" else rng.uniform(2.2, 3.4), style, slate, plaster)
        if rng.random() < 0.6 or kind != "house":                                   # chimney
            cu = rng.uniform(-pl.w0 / 4, pl.w0 / 4)
            pl.LB(cu - 0.35, cu + 0.35, pl.depth * 0.6 - 0.35, pl.depth * 0.6 + 0.35, H, H + 4.3, ashlar, "chimney")
            pl.LB(cu - 0.45, cu + 0.45, pl.depth * 0.6 - 0.45, pl.depth * 0.6 + 0.45, H + 4.3, H + 4.5, M["granite"], "chimney_cap")
        if kind != "house":
            storefront(pl, kind)
            sign(pl, kind, z=3.55 if kind != "guild" else 5.9)
            if kind in ("forge", "inn", "clinic", "rune", "warehouse"):
                shop_door(pl, f"{kind}_door", 1.0)
        elif rng.random() < 0.7:
            storefront(pl, "house", wide=1.6)
            if rng.random() < 0.5:
                lantern(pl, rng.choice((-1.6, 1.6)) if pl.w0 > 4.6 else 1.0, 2.7)
        if kind == "warehouse":                                                    # the big loading door with the custodian glyph
            pl.LB(-1.8, 1.8, -0.12, -0.04, F, 3.4, coak, "custodian_door")
            pl.LB(-0.7, 0.7, -0.16, -0.12, 1.5, 1.8, M["plaque"], "custodian_plate")
        if kind == "guild":                                                         # restrained guildhall: columns and a plaque
            for u in (-3.4, -1.2, 1.2, 3.4):
                pl.LB(u - 0.28, u + 0.28, -0.5, -0.02, F, 5.0, M["granite"], "column")
                pl.LB(u - 0.36, u + 0.36, -0.56, -0.02, 5.0, 5.2, brass, "column_cap")
            pl.LB(-4.2, 4.2, -0.6, -0.02, 5.2, 5.6, M["granite"], "entablature")
        if kind == "inn":                                                           # a brass pneumatic tube from the conveyor into the inn wall
            x, y, zz = pl.P(1.6, -0.2, 8.0)
            k.cylinder(0.1, 6.0, loc=(x, y, zz), material=brass, name="inn_tube", verts=10)
            for tz in (5.5, 7.0, 8.5):
                x, y, zz = pl.P(1.6, -0.2, tz)
                k.cylinder(0.15, 0.06, loc=(x, y, zz), material=brass, name="tube_collar", verts=10)
            lantern(pl, -1.4, 2.8)
            lantern(pl, 1.4, 2.8)

    # ------------------------------------------------------------------ light overhead conveyor: hub, 8 spokes, a ring rail, baskets
    zc = 8.6
    k.cylinder(1.6, 0.5, loc=(0, 0, zc), material=brass, name="hub", verts=24)
    k.cylinder(0.9, 1.2, loc=(0, 0, zc + 0.8), material=iron, name="hub_top", verts=16)
    for i in range(8):
        a = math.radians(i * 45)
        r_mid = (1.6 + 20.4) / 2
        box(r_mid * math.cos(a), r_mid * math.sin(a), zc, 18.8, 0.3, 0.3, iron, "spoke", rotz=math.degrees(a))
        px, py = 20.6 * math.cos(a + math.radians(22.5)), 20.6 * math.sin(a + math.radians(22.5))
        k.cylinder(0.25, zc + 0.6, loc=(px, py, (zc + 0.6) / 2), material=M["granite"], name="pylon", verts=10)
        k.sphere(0.45, loc=(px, py, zc + 0.6), material=brass, name="pylon_cap", segments=8)
        for rb in (6.0, 10.5, 15.0):
            bx, by = rb * math.cos(a), rb * math.sin(a)
            box(bx, by, zc - 0.55, 0.12, 0.12, 0.7, iron, "basket_hanger", rotz=0)
            box(bx, by, zc - 1.1, 0.55, 0.4, 0.4, M["dbone"], "basket", rotz=math.degrees(a))
    for i in range(24):                                                            # ring rail (24 straight segments)
        a = math.radians(i * 15 + 7.5)
        rr = 12.0
        box(rr * math.cos(a), rr * math.sin(a), zc, 2 * rr * math.tan(math.radians(7.5)), 0.25, 0.25, iron, "ring_rail", rotz=math.degrees(a) + 90)
    for i in range(8):
        a = math.radians(i * 45 + 22.5)
        x, y = 20.6 * math.cos(a), 20.6 * math.sin(a)
        LIGHTS.append(dict(x=x, y=y, z=5.0, dim=40, bright=14, color="#ffc58a"))

    skulls.finish(M["bone"], M["soot"], M["teeth"], name="skulls")
