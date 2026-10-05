"""Additions layered over the ORIGINAL Ossuary Exchange market model (kept untouched as its own tile): party-wall tower houses in the gaps between
the ring houses, and varied storefronts on the ring houses (awnings, goods, text shop signs). The overhead conveyors stay as they are in the original.

The original's bounding box is pinned with two tiny corner markers, so this model gets the same placement and scale as the original tile.
Original frame: ring houses stand at r ~ 22.9 (origin at each house's front-centre, front facing the plaza), 18 degrees apart from 9 degrees.
"""
import math
import random

import bmesh
import bpy
from _parts import bm_to_obj

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Overlay for the original market model: party-wall houses and shop storefronts."
KEEP_XY = True
KEEP_Z = True
LIGHTS = []

ORIG = "D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository/foundry-3d/out/orig_market.glb"
R0 = 22.9
# ring house angle (degrees) -> shop kind. House k stands at 9 + 18*k degrees.
SHOPS = {-45: "forge", -81: "clinic", -117: "inn", -171: "rune"}              # the four real shops (full signs)
UTILITY = {-9: "tube", -153: "dock"}                                          # utility plates on the post and warehouse houses
PLATES = ["lodge", "cart", "tallow", "resid", "trolley", "notice", "intake", "wash", "ledger"]


def build(k):
    rng = random.Random(41)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=ORIG)
    mats = {m.name: m for m in bpy.data.materials}
    for o in [o for o in bpy.data.objects if o not in before]:
        bpy.data.objects.remove(o, do_unlink=True)
    for nm in ("Archive oak", "Charred oak reinforced with bone straps", "Aged wrought iron", "Ancient irregular ossuary ashlar", "Hand-cut charcoal ossuary slate",
               "Calcified ancient lime and bone mortar"):
        if nm in mats:
            mats[nm]["tile_m"] = 2.0                       # lets the engine box-project world UVs onto these (they came from the original model)
    oak = mats["Archive oak"]
    coak = mats["Charred oak reinforced with bone straps"]
    iron = mats["Aged wrought iron"]
    ashlar = mats["Ancient irregular ossuary ashlar"]
    slate = mats["Hand-cut charcoal ossuary slate"]
    mortar = mats.get("Calcified ancient lime and bone mortar", ashlar)
    cloths = [k.mat(f"mk_awning{i}", c, roughness=0.95) for i, c in enumerate(((0.32, 0.07, 0.06), (0.07, 0.12, 0.25), (0.08, 0.22, 0.13), (0.42, 0.32, 0.1), (0.25, 0.1, 0.3)))]
    brass = k.mat("mk_brass", (0.55, 0.4, 0.12), roughness=0.4, metallic=0.9)
    lamp = k.mat("mk_lamp", (1.0, 0.7, 0.35), roughness=0.5, emission=(1.0, 0.65, 0.3))
    glass = k.mat("mk_glass", (0.03, 0.05, 0.07), roughness=0.15)
    doak = mats.get("Dark antique oak", oak)
    sack = k.mat("mk_sack", (0.45, 0.38, 0.26), roughness=1.0)

    def box(cx, cy, cz, sx, sy, sz, mat, name, rotz=0.0, rotx=0.0, roty=0.0):
        return k.box((sx, sy, sz), loc=(cx, cy, cz), rot=(rotx, roty, rotz), material=mat, name=name)

    def poly(pts, mat, name, want=(0, 0, 1)):
        bm = bmesh.new()
        f = bm.faces.new([bm.verts.new(p) for p in pts])
        f.normal_update()
        n = f.normal
        if n.x * want[0] + n.y * want[1] + n.z * want[2] < 0:
            f.normal_flip()
        return bm_to_obj(bm, name, mat)

    # ---- corner markers pin the bounding box to the original model's
    box(-28.41, -28.41, -0.34, 0.002, 0.002, 0.002, ashlar, "bbox_min")
    box(28.41, 29.9, 18.38, 0.002, 0.002, 0.002, ashlar, "bbox_max")

    # ---- party-wall tower houses in the gaps between ring houses
    def tower(g_deg, idx):
        g = math.radians(g_deg)
        c, s = math.cos(g), math.sin(g)
        rc, length, w = 25.5, 4.2, 1.75
        cx, cy = rc * c, rc * s
        h_total = rng.choice((9.8, 10.6, 11.4, 10.2))
        base = 3.4
        deg = g_deg
        box(cx, cy, base / 2, length, w, base, ashlar, "tw_base", rotz=deg)
        floors = 2 if h_total < 10.5 else 3
        fh = (h_total - base) / floors
        for f in range(floors):
            z0 = base + f * fh
            box(cx, cy, z0 + fh / 2, length - 0.1, w - 0.1, fh, (mortar if (f + idx) % 3 == 0 else coak if f % 2 else oak), "tw_floor", rotz=deg)
            box(cx, cy, z0 + 0.06, length + 0.1, w + 0.1, 0.12, coak, "tw_beam", rotz=deg)          # jetty beam
            # a window on the plaza-facing end
            px, py = (rc - length / 2 - 0.03) * c, (rc - length / 2 - 0.03) * s
            box(px, py, z0 + fh * 0.55, 0.05, 0.6, 0.9, coak, "tw_window", rotz=deg)
        # gable roof, ridge radial, slopes tangential
        z = h_total
        hr = 1.7
        def P(dr, dt, zz):
            return (cx + dr * c - dt * s, cy + dr * s + dt * c, zz)
        ov = 0.28
        A, B, Cc, D = P(-length / 2 - ov, -w / 2 - ov, z), P(length / 2 + ov, -w / 2 - ov, z), P(length / 2 + ov, w / 2 + ov, z), P(-length / 2 - ov, w / 2 + ov, z)
        RF, RB = P(-length / 2 - ov, 0, z + hr), P(length / 2 + ov, 0, z + hr)
        poly([A, B, RB, RF], slate, "tw_roof_a")
        poly([D, RF, RB, Cc], slate, "tw_roof_b")
        poly([A, RF, D], mortar, "tw_gable_in", (-c, -s, 0))
        poly([B, Cc, RB], mortar, "tw_gable_out", (c, s, 0))
        if idx % 3 == 0:                                                         # chimney
            box(*P(0.6, 0, z + hr + 0.5), 0.5, 0.5, 2.0, ashlar, "tw_chimney", rotz=deg)

    for i in range(20):
        tower(18 * i, i)

    # ---- storefronts on ring houses
    def frame(angle_deg):
        a = math.radians(angle_deg)
        p = (R0 * math.cos(a), R0 * math.sin(a))
        f = (-math.cos(a), -math.sin(a))
        t = (-f[1], f[0])
        return p, f, t, angle_deg + 180.0

    def front(angle_deg):
        p, f, t, rz = frame(angle_deg)

        def P(u, v, z):
            return (p[0] + t[0] * u + f[0] * v, p[1] + t[1] * u + f[1] * v, z)

        def LB(u0, u1, v0, v1, z0, z1, mat, name, rotx=0.0, roty=0.0):
            x, y, z = P((u0 + u1) / 2, (v0 + v1) / 2, (z0 + z1) / 2)
            return box(x, y, z, v1 - v0, u1 - u0, z1 - z0, mat, name, rotz=rz, rotx=rotx, roty=roty)

        return p, P, LB

    def sign(P, LB, kind, z=3.8):
        hw, hh = 1.35, 0.47
        z0, z1 = z - hh, z + hh
        vv = 0.42
        mat = _sign_material(f"sign_{kind}")
        verts = [P(-hw, vv, z0), P(hw, vv, z0), P(hw, vv, z1), P(-hw, vv, z1)]
        me = bpy.data.meshes.new(f"sign_{kind}")
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for li, uvc in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[li].uv = uvc
        me.update()
        ob = bpy.data.objects.new(f"sign_{kind}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        LB(-hw - 0.06, hw + 0.06, 0.34, 0.41, z0 - 0.06, z1 + 0.06, oak, "sign_board")                  # backing, behind the lettering
        for su in (-0.9, 0.9):                                                                          # two iron arms back to the wall
            LB(su - 0.04, su + 0.04, -0.7, 0.36, z + 0.15, z + 0.2, iron, "sign_arm")
        x, y, zz = P(hw + 0.3, 0.7, z)
        k.sphere(0.11, loc=(x, y, zz), material=lamp, name="sign_lantern", segments=8)
        LB(hw + 0.28, hw + 0.32, -0.7, 0.7, z + 0.12, z + 0.16, iron, "lantern_arm")

    _sm = {}

    def _sign_material(name):
        if name not in _sm:
            img = bpy.data.images.load(f"D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository/foundry-3d/textures/{name}.png")
            m = bpy.data.materials.new(name)
            m.use_nodes = True
            nt = m.node_tree
            b = nt.nodes["Principled BSDF"]
            b.inputs["Roughness"].default_value = 0.8
            t = nt.nodes.new("ShaderNodeTexImage")
            t.image = img
            nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
            em = b.inputs.get("Emission Color") or b.inputs.get("Emission")
            nt.links.new(t.outputs["Color"], em)
            b.inputs["Emission Strength"].default_value = 0.3
            m.use_backface_culling = True
            _sm[name] = m
        return _sm[name]

    def plate(P, LB, key):
        """A small iron utility plate over the door, on two short arms."""
        hw, hh, z = 0.6, 0.18, 2.95
        mat = _sign_material(f"plate_{key}")
        verts = [P(-hw, 0.2, z - hh), P(hw, 0.2, z - hh), P(hw, 0.2, z + hh), P(-hw, 0.2, z + hh)]
        me = bpy.data.meshes.new(f"plate_{key}")
        me.from_pydata(verts, [], [(0, 1, 2, 3)])
        uv = me.uv_layers.new(name="UVMap")
        for li, uvc in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
            uv.data[li].uv = uvc
        me.update()
        ob = bpy.data.objects.new(f"plate_{key}", me)
        bpy.context.scene.collection.objects.link(ob)
        ob.data.materials.append(mat)
        LB(-hw - 0.03, hw + 0.03, 0.16, 0.19, z - hh - 0.03, z + hh + 0.03, iron, "plate_back")
        for su in (-0.45, 0.45):
            LB(su - 0.02, su + 0.02, -0.65, 0.17, z + 0.05, z + 0.09, iron, "plate_arm")

    def awning(P, LB, cloth, width=3.4):
        x, y, z = P(0, 0.55, 2.2)
        box(x, y, z, 1.15, width, 0.05, cloth, "awning", rotz=frame_rz[0], roty=-14.0 if True else 0)
        for su in (-width / 2 + 0.1, width / 2 - 0.1):
            LB(su - 0.04, su + 0.04, 1.05, 1.13, 0.0, 1.98, iron, "awning_post")

    frame_rz = [0.0]

    def goods(kind, P, LB, rr):
        if kind == "forge":
            LB(-0.6, 0.6, 0.3, 0.9, 0.0, 0.5, iron, "anvil_base")
            LB(-0.75, 0.75, 0.25, 0.95, 0.5, 0.72, iron, "anvil_top")
            for su in (-1.6, 1.6):
                x, y, z = P(su, 0.55, 0.45)
                k.cylinder(0.32, 0.9, loc=(x, y, z), material=oak, name="barrel", verts=12)
        elif kind == "clinic":
            for i in range(3):
                LB(-1.4 + i * 0.95, -0.55 + i * 0.95, 0.35, 0.95, 0.0 + 0.0, 0.55, iron, "cage")
                LB(-1.35 + i * 0.95, -0.6 + i * 0.95, 0.4, 0.9, 0.55, 0.62, oak, "cage_lid")
            LB(0.6, 1.9, 0.3, 0.8, 0.0, 0.7, oak, "clinic_bench")
        elif kind == "rune":
            for i in range(3):
                LB(-1.5 + i * 1.1, -0.7 + i * 1.1, 0.4 + 0.05 * i, 0.5 + 0.05 * i, 0.05, 1.4, slate, "slate_board", rotx=0.0, roty=-8.0)
        elif kind == "inn":
            for su in (-1.6, 1.4):
                LB(su - 0.5, su + 0.5, 0.3, 0.9, 0.7, 0.76, oak, "table_top")
                LB(su - 0.45, su - 0.35, 0.35, 0.45, 0.0, 0.7, oak, "table_leg")
                LB(su + 0.35, su + 0.45, 0.75, 0.85, 0.0, 0.7, oak, "table_leg")
                x, y, z = P(su, 1.3, 0.2)
                k.cylinder(0.2, 0.4, loc=(x, y, z), material=oak, name="stool", verts=10)
            for i in range(3):
                x, y, z = P(0.1 + 0.55 * (i % 2), 0.55, 0.4 + 0.8 * (i // 2))
                k.cylinder(0.3, 0.8, loc=(x, y, z), material=oak, name="barrel", verts=12)
        elif kind == "post":
            x, y, z = P(0.0, 0.9, 1.1)
            k.cylinder(0.16, 2.2, loc=(x, y, z), material=brass, name="post_tube", verts=12)
            LB(-0.5, 0.5, 0.5, 1.3, 0.0, 0.3, ashlar, "post_plinth")
            LB(1.0, 1.7, 0.3, 0.9, 0.0, 0.5, oak, "parcel_crate")
        elif kind == "warehouse":
            for i, (u, z) in enumerate(((-1.4, 0.0), (-0.6, 0.0), (-1.0, 0.7), (1.3, 0.0))):
                LB(u - 0.38, u + 0.38, 0.3, 1.0, z, z + 0.7, coak, "crate")
            LB(0.2, 0.9, 0.3, 0.8, 0.0, 0.5, oak, "cart_bed")
            for su in (0.15, 0.95):
                x, y, z = P(su, 0.8, 0.3)
                k.cylinder(0.3, 0.06, loc=(x, y, z), rot=(0, 0, rr), material=iron, name="cart_wheel", verts=12)
        else:                                                                   # general store goods, varied by the dice
            n = rng.randint(2, 4)
            for i in range(n):
                u = -1.5 + i * 1.0 + rng.uniform(-0.2, 0.2)
                t = rng.choice(("crate", "sack", "barrel"))
                if t == "crate":
                    LB(u - 0.3, u + 0.3, 0.3, 0.9, 0.0, 0.6, oak, "crate")
                elif t == "barrel":
                    x, y, z = P(u, 0.6, 0.4)
                    k.cylinder(0.3, 0.8, loc=(x, y, z), material=oak, name="barrel", verts=12)
                else:
                    x, y, z = P(u, 0.6, 0.3)
                    k.sphere(0.32, loc=(x, y, z), scale=(1, 0.8, 1.0), material=sack, name="sack", segments=8)

    def door_and_windows(P, LB, idx, kind):
        """Non-functional door and shop windows set into a stone porch block proud of the house front."""
        LB(-0.85, 0.85, -0.5, 0.12, 0.0, 2.65, ashlar, "porch_block")
        LB(-0.62, 0.62, 0.12, 0.17, 0.0, 2.35, coak, "door_frame")
        LB(-0.52, 0.52, 0.17, 0.21, 0.0, 2.25, doak, "door_leaf")
        LB(-0.52, 0.52, 0.21, 0.23, 0.9, 0.97, iron, "door_strap_a")
        LB(-0.52, 0.52, 0.21, 0.23, 1.6, 1.67, iron, "door_strap_b")
        x, y, z = P(0.38, 0.27, 1.1)
        k.sphere(0.05, loc=(x, y, z), material=brass, name="door_handle", segments=8)
        for sx in (-1, 1):
            if kind == "general" and (idx + (sx > 0)) % 3 == 0:
                continue
            u0 = sx * 2.0
            LB(u0 - 0.65, u0 + 0.65, -0.5, 0.1, 0.55, 1.95, ashlar, "window_block")
            LB(u0 - 0.6, u0 + 0.6, 0.1, 0.15, 0.62, 1.85, coak, "window_frame")
            LB(u0 - 0.5, u0 + 0.5, 0.1, 0.17, 0.72, 1.75, glass, "window_glass")
            LB(u0 - 0.04, u0 + 0.04, 0.15, 0.18, 0.72, 1.75, coak, "window_mullion")
            LB(u0 - 0.5, u0 + 0.5, 0.15, 0.18, 1.2, 1.26, coak, "window_transom")
            LB(u0 - 0.7, u0 + 0.7, 0.1, 0.3, 0.5, 0.57, ashlar, "window_sill")
            if (idx + sx) % 2 == 0:
                for ss in (-1, 1):
                    LB(u0 + ss * 0.72 - 0.12, u0 + ss * 0.72 + 0.12, 0.1, 0.14, 0.62, 1.85, doak, "shutter")

    for i in range(20):
        ang = 9 + 18 * i
        if ang > 180:
            ang -= 360
        kind = SHOPS.get(ang, "general")
        if ang in UTILITY:
            kind = "general"
        p, P, LB = front(ang)
        frame_rz[0] = ang + 180.0
        if kind != "general" or i % 3 != 1:
            awning(P, LB, cloths[(i * 2 + 1) % len(cloths)])
        door_and_windows(P, LB, i, kind)
        goods(kind, P, LB, ang + 180.0)
        if kind != "general":
            sign(P, LB, kind)
        elif ang in UTILITY:
            plate(P, LB, UTILITY[ang])
        elif i % 3 != 2:
            plate(P, LB, PLATES[i % len(PLATES)])

    # ---- four lamp posts: these are the scene's four lights
    for sx, sy in ((12, 12), (-12, 12), (12, -12), (-12, -12)):
        k.cylinder(0.11, 3.6, loc=(sx, sy, 1.8), material=iron, name="lamp_post", verts=10)
        k.cylinder(0.28, 0.12, loc=(sx, sy, 0.06), material=ashlar, name="lamp_base", verts=10)
        k.cylinder(0.22, 0.5, loc=(sx, sy, 3.85), material=lamp, name="lamp_lantern", verts=10)
        k.cone(0.34, 0.04, 0.35, loc=(sx, sy, 4.28), material=iron, name="lamp_cap", verts=10)
        LIGHTS.append(dict(x=sx, y=sy, z=3.85, dim=95, bright=45, color="#ffb066"))

    # ---- ring of party walls behind the storefronts, closing the see-through gaps at the 2nd and 3rd storeys
    n = 36
    rr, th, wh = 27.7, 0.7, 10.8
    for i in range(n):
        a = math.radians(i * 10 + 5)
        cx, cy = rr * math.cos(a), rr * math.sin(a)
        ch = 2 * rr * math.tan(math.radians(5)) + 0.02
        deg = i * 10 + 5
        box(cx, cy, wh / 2, th, ch, wh, ashlar if i % 3 else coak, "ring_wall", rotz=deg)
        ix, iy = (rr - th / 2 - 0.03) * math.cos(a), (rr - th / 2 - 0.03) * math.sin(a)
        for z in (6.8, 9.3):
            box(ix, iy, z, 0.05, 1.0, 1.4, glass, "ring_window", rotz=deg)
            box(ix, iy, z, 0.04, 1.2, 1.6, coak, "ring_window_frame", rotz=deg)
        box(ix, iy, wh - 0.1, 0.12, ch, 0.2, coak, "ring_cornice", rotz=deg)
