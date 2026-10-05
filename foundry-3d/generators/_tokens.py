"""Token models for 3D Canvas (imported by token generators; not built on its own).

Conventions (verified in 3D Canvas token3d.js): the model is scaled so its LARGEST dimension equals the token footprint,
its own origin stays at the token centre (autoCenter off) and its lowest point sits on the floor. So: origin at the middle
of the feet, Z up, the creature facing Blender -Y (glTF +Z), and generators set KEEP_XY = True so that origin is authored,
not guessed from the bounding box. Build in real metres; set the token's D&D size so the squares match.
"""
import math

import bpy

from _parts import Skulls, bm_to_obj, flame_tongue, lathe  # noqa: F401
from _painting import _image_material


def mats(k):
    return dict(
        brass=k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4),
        iron=k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3),
        doak=k.tex("dark_oak", "dark_antique_oak", tile=1.0, rough=0.65),
        oak=k.tex("oak", "archive_oak", tile=1.0, rough=0.7),
        bone=k.tex("bone", "weathered_structural_bone", tile=0.5, rough=0.6),
        soot=k.mat("soot", (0.02, 0.02, 0.02), roughness=1.0),
        teeth=k.mat("skull_teeth", (0.88, 0.84, 0.72), roughness=0.55),
        amber=k.mat("eye_amber", (1.0, 0.35, 0.03), roughness=0.3, emission=(1.0, 0.33, 0.03)),
        gold=k.mat("gold", (0.75, 0.55, 0.12), roughness=0.35),
        red=k.mat("red", (0.45, 0.04, 0.04), roughness=0.9),
        navy=k.mat("navy", (0.05, 0.08, 0.25), roughness=0.9),
        white=k.mat("white", (0.85, 0.82, 0.74), roughness=0.9),
        straw=k.mat("straw", (0.65, 0.5, 0.15), roughness=0.95),
        yellow=k.mat("yellow", (0.8, 0.65, 0.05), roughness=0.8),
        blue=k.mat("blue", (0.1, 0.25, 0.65), roughness=0.85),
        green=k.mat("green", (0.08, 0.3, 0.12), roughness=0.9),
        brown=k.mat("brown", (0.25, 0.15, 0.08), roughness=0.9),
        skin=k.mat("skin", (0.62, 0.45, 0.35), roughness=0.85),
        pink=k.mat("pink", (0.8, 0.35, 0.4), roughness=0.7),
        olive=k.mat("olive", (0.25, 0.3, 0.12), roughness=0.8),
        cream=k.mat("cream", (0.75, 0.7, 0.5), roughness=0.85),
        grey=k.mat("grey", (0.3, 0.3, 0.32), roughness=0.9),
        plum=k.mat("plum", (0.22, 0.07, 0.25), roughness=0.9),
        black=k.mat("black_cloth", (0.04, 0.04, 0.05), roughness=0.95),
    )


def boxc(k, size, loc, mat, name="part", rot=(0, 0, 0), bevel=0.0):
    return k.box(size, loc=loc, rot=rot, material=mat, name=name, bevel=bevel)


def limb(k, a, b, r, mat, name="limb", verts=8):
    """A cylinder from point a to point b (Blender coordinates)."""
    ax, ay, az = a
    bx, by, bz = b
    d = (bx - ax, by - ay, bz - az)
    length = math.sqrt(sum(c * c for c in d))
    mid = ((ax + bx) / 2, (ay + by) / 2, (az + bz) / 2)
    ob = k.cylinder(r, length, loc=mid, material=mat, name=name, verts=verts)
    # rotate the cylinder's Z axis onto d
    from mathutils import Vector
    q = Vector((0, 0, 1)).rotation_difference(Vector(d))
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = q
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.object.transform_apply(rotation=True)
    return ob


# ----------------------------------------------------------------------------------------------- painting creature
def painting_creature(k, stem, canvas_w, canvas_h, accessory, frame_key="brass", leg_h=0.32, arm_len=0.45):
    """A framed portrait that walks: claw feet, skeletal arms hanging from the frame, a skull crest and an accessory."""
    M = mats(k)
    frame = M[frame_key]
    fr = 0.12 * (canvas_h / 1.4) ** 0.5
    z0 = leg_h + fr                       # canvas bottom
    z1 = z0 + canvas_h
    hw = canvas_w / 2
    bz = leg_h                            # frame bottom

    def B(x0, x1, y0, y1, za, zb, m, name="part", bevel=0.0):
        return boxc(k, (x1 - x0, y1 - y0, zb - za), ((x0 + x1) / 2, (y0 + y1) / 2, (za + zb) / 2), m, name, bevel=bevel)

    # canvas facing -Y (viewer at -Y sees x to the right, z up)
    mat = _image_material(k, f"painting_{stem}", f"painting_{stem}.jpg")
    me = bpy.data.meshes.new("canvas")
    me.from_pydata([(-hw, -0.045, z0), (hw, -0.045, z0), (hw, -0.045, z1), (-hw, -0.045, z1)], [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = (u, v)
    me.update()
    ob = bpy.data.objects.new("canvas", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    B(-hw - fr, hw + fr, 0.0, 0.03, bz, z1 + fr, M["doak"], "back")
    B(-hw - fr, hw + fr, -0.075, 0.03, bz, bz + fr, frame, "frame_b", 0.012)
    B(-hw - fr, hw + fr, -0.075, 0.03, z1, z1 + fr, frame, "frame_t", 0.012)
    B(-hw - fr, -hw, -0.075, 0.03, bz + fr, z1, frame, "frame_l", 0.012)
    B(hw, hw + fr, -0.075, 0.03, bz + fr, z1, frame, "frame_r", 0.012)
    for sx in (-1, 1):
        for zz in (bz + fr / 2, z1 + fr / 2):
            k.sphere(0.045, loc=(sx * (hw + fr / 2), -0.08, zz), material=M["iron"], name="boss", segments=8)

    # claw feet: brass legs with a ball and three toes, set back a little so the frame stays the front
    for sx in (-1, 1):
        x = sx * (hw * 0.55)
        k.cylinder(0.035, leg_h - 0.05, loc=(x, 0.0, (leg_h - 0.05) / 2 + 0.05), material=M["brass"], name="leg", verts=8)
        k.sphere(0.055, loc=(x, -0.03, 0.055), scale=(1, 1.3, 0.7), material=M["brass"], name="foot", segments=8)
        for t in (-0.045, 0.0, 0.045):
            k.cone(0.02, 0.0, 0.07, loc=(x + t, -0.13, 0.03), rot=(-90, 0, 0), material=M["brass"], name="claw", verts=6)

    # skeletal arms hanging from the frame's upper sides, elbow forward, hands open
    for sx in (-1, 1):
        sh = (sx * (hw + fr + 0.03), 0.02, z1 - 0.1)
        el = (sx * (hw + fr + 0.09), -0.06, z1 - 0.1 - arm_len)
        wr = (sx * (hw + fr + 0.16), -0.2, z1 - 0.1 - arm_len - 0.32)
        limb(k, sh, el, 0.025, M["bone"], "upper_arm")
        k.sphere(0.035, loc=el, material=M["bone"], name="elbow", segments=8)
        limb(k, el, wr, 0.02, M["bone"], "forearm")
        boxc(k, (0.07, 0.025, 0.09), (wr[0], wr[1] - 0.02, wr[2] - 0.045), M["bone"], "palm")
        for f in (-0.025, -0.008, 0.009, 0.026):
            limb(k, (wr[0] + f, wr[1] - 0.02, wr[2] - 0.09), (wr[0] + f * 1.4, wr[1] - 0.05, wr[2] - 0.17), 0.007, M["bone"], "finger", verts=6)

    sk = Skulls()
    sk.add(0, -0.02, z1 + fr, face_to=(0, -10), s=0.07)
    sk.finish(M["bone"], M["soot"], M["teeth"], name="crest_skull")

    top = z1 + fr + 0.15                                 # above the crest skull
    cx = 0.0
    if accessory == "veil":                              # Mona Lisa: dark veil over the top corners
        B(-hw - fr, hw + fr, -0.04, 0.04, top - 0.1, top - 0.02, M["black"], "veil_top")
        for sx in (-1, 1):
            B(sx * (hw + fr) - 0.025, sx * (hw + fr) + 0.025, -0.05, 0.05, z1 - 0.5, top - 0.1, M["black"], "veil_side")
    elif accessory == "turban":                          # Pearl: blue and yellow turban + hanging pearl
        k.sphere(0.34, loc=(0, 0.02, top + 0.1), scale=(1.3, 0.9, 0.6), material=M["blue"], name="turban")
        k.sphere(0.2, loc=(0.12, 0.02, top + 0.32), scale=(1, 0.9, 0.8), material=M["yellow"], name="turban_knot")
        limb(k, (-hw - fr + 0.05, -0.1, bz + 0.1), (-hw - fr + 0.05, -0.1, bz - 0.1), 0.004, M["brass"], "pearl_chain", 6)
        k.sphere(0.05, loc=(-hw - fr + 0.05, -0.1, bz - 0.15), material=M["white"], name="pearl", segments=10)
    elif accessory == "bicorne":                         # Napoleon: black bicorne with a cockade
        k.sphere(0.4, loc=(0, 0, top + 0.06), scale=(1.4, 0.5, 0.45), material=M["black"], name="bicorne")
        k.sphere(0.05, loc=(0, -0.2, top + 0.1), material=M["red"], name="cockade", segments=8)
    elif accessory == "strawhat":                        # Van Gogh: straw hat and a sunflower
        k.cylinder(0.38, 0.03, loc=(0, 0, top + 0.02), material=M["straw"], name="brim", verts=14)
        k.cylinder(0.2, 0.18, loc=(0, 0, top + 0.12), material=M["straw"], name="crown", verts=12)
        k.cylinder(0.1, 0.03, loc=(hw + fr + 0.05, -0.1, z1 - 0.1), rot=(90, 0, 0), material=M["yellow"], name="sunflower", verts=10)
        k.cylinder(0.045, 0.04, loc=(hw + fr + 0.05, -0.12, z1 - 0.1), rot=(90, 0, 0), material=M["brown"], name="sunflower_eye", verts=8)
    elif accessory == "crown":                           # Henry: crown and a turkey leg
        k.cylinder(0.22, 0.1, loc=(0, 0, top + 0.05), material=M["gold"], name="crown_band", verts=12)
        for a in range(0, 360, 60):
            r = math.radians(a)
            k.cone(0.035, 0.0, 0.12, loc=(0.2 * math.cos(r), 0.2 * math.sin(r), top + 0.16), material=M["gold"], name="crown_spike", verts=6)
        k.sphere(0.04, loc=(0, -0.2, top + 0.05), material=M["red"], name="crown_gem", segments=8)
        k.cylinder(0.05, 0.22, loc=(-hw - fr - 0.2, -0.3, bz + 0.45), rot=(35, 0, 20), material=M["brown"], name="turkey_leg", verts=8)
        k.sphere(0.07, loc=(-hw - fr - 0.24, -0.38, bz + 0.58), scale=(1, 1, 1.2), material=M["brown"], name="turkey_meat", segments=8)
    elif accessory == "plume":                           # Blue Boy: wide black hat and a white plume
        k.cylinder(0.42, 0.03, loc=(0, 0, top + 0.02), material=M["black"], name="brim", verts=14)
        k.cylinder(0.2, 0.16, loc=(0, 0, top + 0.1), material=M["black"], name="crown", verts=12)
        k.cone(0.05, 0.0, 0.5, loc=(0.2, 0, top + 0.36), rot=(0, 25, 0), material=M["white"], name="plume", verts=6)


# ----------------------------------------------------------------------------------------------- turtle (Gerald)
def turtle(k):
    """Gerald: a cartoony soft-shelled turtle about 0.6 m long with a long grippy tongue and SIX stubby legs (three a side), each ending in sticky pink
    toe pads. Rounded shell with raised scutes, bulging eyes, long fleshy snout. Origin at the middle of the body footprint; head toward -Y."""
    import math
    M = mats(k)
    dark = k.mat("shell_dark", (0.17, 0.22, 0.08), roughness=0.75)
    z0 = 0.13                                                   # body height above the ground
    # shell: low dome, pale rim, plastron underneath
    k.sphere(0.25, loc=(0, 0.02, z0 + 0.03), scale=(0.95, 1.2, 0.5), material=M["olive"], name="shell", segments=16)
    k.sphere(0.265, loc=(0, 0.02, z0 - 0.02), scale=(0.97, 1.22, 0.16), material=M["cream"], name="shell_rim", segments=16)
    k.sphere(0.22, loc=(0, 0.02, z0 - 0.05), scale=(0.9, 1.15, 0.2), material=M["cream"], name="plastron", segments=12)
    # raised scutes: a centre plate, a ring of six around it, a ridge of marginals
    def scute(x, y, z, r, tilt):
        k.cylinder(r, 0.012, loc=(x, y, z), rot=tilt, material=dark, name="scute", verts=6)
    top = z0 + 0.03 + 0.25 * 0.5
    scute(0, 0.02, top - 0.006, 0.09, (0, 0, 0))
    for i in range(6):
        a_ = math.radians(60 * i + 30)
        x, y = 0.15 * math.cos(a_) * 0.95, 0.02 + 0.15 * math.sin(a_) * 1.2
        scute(x, y, top - 0.04, 0.07, (math.degrees(math.sin(a_)) * 0.0 + (-14 * math.sin(a_)), 14 * math.cos(a_), 0))
    # neck, head with a long snout, bulging eyes, nostrils, long pink tongue
    limb(k, (0, -0.24, z0 + 0.02), (0, -0.36, z0 + 0.08), 0.055, M["olive"], "neck", 10)
    k.sphere(0.075, loc=(0, -0.4, z0 + 0.1), scale=(1, 1.15, 0.9), material=M["olive"], name="head", segments=12)
    k.sphere(0.045, loc=(0, -0.49, z0 + 0.085), scale=(0.85, 1.5, 0.75), material=M["olive"], name="snout", segments=10)
    for sx in (-1, 1):
        k.sphere(0.03, loc=(sx * 0.055, -0.41, z0 + 0.16), material=M["white"], name="eye_white", segments=10)
        k.sphere(0.017, loc=(sx * 0.06, -0.435, z0 + 0.165), material=M["soot"], name="eye", segments=8)
        k.sphere(0.006, loc=(sx * 0.016, -0.545, z0 + 0.1), material=M["soot"], name="nostril", segments=6)
    limb(k, (0, -0.53, z0 + 0.065), (0, -0.66, z0 + 0.045), 0.014, M["pink"], "tongue", 8)
    k.sphere(0.03, loc=(0, -0.665, z0 + 0.045), scale=(1.3, 1.0, 0.6), material=M["pink"], name="tongue_tip", segments=8)
    # six legs: three a side, stubby, bent out and down, each with four sticky pink toe pads
    for y in (-0.15, 0.04, 0.23):
        for sx in (-1, 1):
            hip = (sx * 0.2, y, z0 - 0.01)
            knee = (sx * 0.3, y - 0.01, z0 - 0.02)
            foot = (sx * 0.33, y - 0.02, 0.03)
            limb(k, hip, knee, 0.042, M["olive"], "thigh", 8)
            limb(k, knee, foot, 0.034, M["olive"], "shin", 8)
            k.sphere(0.04, loc=foot, scale=(1.3, 1.5, 0.45), material=M["pink"], name="foot", segments=8)
            for t in (-1.5, -0.5, 0.5, 1.5):
                k.sphere(0.014, loc=(foot[0] + sx * 0.012, foot[1] - 0.045 + t * 0.012, 0.018), scale=(1, 1.4, 0.6), material=M["pink"], name="toe_pad", segments=6)
    k.cone(0.05, 0.0, 0.14, loc=(0, 0.36, z0 - 0.01), rot=(-90, 0, 0), material=M["olive"], name="tail", verts=8)


# ----------------------------------------------------------------------------------------------- humanoid
def humanoid(k, height=1.75, coat="brown", trousers="grey", hat=None, hair=None, apron=None, stoop=0.0, long_coat=False,
             held=None, build=1.0):
    """A stylised person (about 400 triangles). Origin between the feet, facing -Y."""
    M = mats(k)
    h = height
    s = h / 1.75
    w = 0.23 * build * s                        # half shoulder width
    hip_z, sh_z = 0.92 * s, 1.45 * s
    # legs
    for sx in (-1, 1):
        x = sx * 0.09 * build * s
        limb(k, (x, 0, 0.1 * s), (x, 0, hip_z), 0.055 * s * build, M[trousers], "leg", 8)
        boxc(k, (0.11 * s, 0.24 * s, 0.1 * s), (x, -0.05 * s, 0.05 * s), M["black"], "boot")
    # torso (coat), optional long skirt
    tz = (hip_z + sh_z) / 2
    boxc(k, (2 * w * 0.9, 0.22 * s * build, sh_z - hip_z + 0.05), (0, -stoop * 0.5, tz), M[coat], "torso", bevel=0.02)
    if long_coat:
        boxc(k, (2 * w * 1.0, 0.25 * s * build, 0.55 * s), (0, -stoop * 0.3, hip_z - 0.25 * s), M[coat], "coat_skirt", bevel=0.02)
    if apron:
        boxc(k, (2 * w * 0.7, 0.03, 0.7 * s), (0, -0.125 * s * build - stoop * 0.5, hip_z + 0.12 * s), M[apron], "apron")
    boxc(k, (2 * w * 0.95, 0.24 * s * build, 0.05), (0, -stoop * 0.5, hip_z + 0.02), M["brown"], "belt")
    # arms and hands
    for sx in (-1, 1):
        shoulder = (sx * (w + 0.02 * s), -stoop * 0.5, sh_z - 0.05 * s)
        wrist = (sx * (w + 0.06 * s), -0.12 * s - stoop * 0.3, hip_z + 0.02 * s)
        limb(k, shoulder, wrist, 0.045 * s * build, M[coat], "arm", 8)
        k.sphere(0.05 * s, loc=wrist, material=M["skin"], name="hand", segments=8)
    # neck, head, face
    hz = sh_z + 0.19 * s
    hy = -stoop
    k.cylinder(0.05 * s, 0.1 * s, loc=(0, hy * 0.7, sh_z + 0.04 * s), material=M["skin"], name="neck", verts=8)
    k.sphere(0.115 * s, loc=(0, hy, hz), scale=(0.9, 1.0, 1.1), material=M["skin"], name="head", segments=12)
    boxc(k, (0.03 * s, 0.05 * s, 0.05 * s), (0, hy - 0.12 * s, hz - 0.01 * s), M["skin"], "nose")
    for sx in (-1, 1):
        k.sphere(0.014 * s, loc=(sx * 0.04 * s, hy - 0.1 * s, hz + 0.02 * s), material=M["soot"], name="eye", segments=6)
    if hair:
        k.sphere(0.12 * s, loc=(0, hy + 0.02 * s, hz + 0.02 * s), scale=(0.95, 1.0, 1.0), material=M[hair], name="hair", segments=10)
    if hat == "cap":
        k.sphere(0.125 * s, loc=(0, hy, hz + 0.04 * s), scale=(1, 1.05, 0.7), material=M["grey"], name="cap", segments=10)
        boxc(k, (0.16 * s, 0.1 * s, 0.015 * s), (0, hy - 0.13 * s, hz + 0.03 * s), M["grey"], "cap_peak")
    elif hat == "wide":
        k.cylinder(0.2 * s, 0.015, loc=(0, hy, hz + 0.08 * s), material=M["black"], name="hat_brim", verts=14)
        k.cylinder(0.11 * s, 0.14 * s, loc=(0, hy, hz + 0.15 * s), material=M["black"], name="hat_crown", verts=12)
    if held == "shovel":
        limb(k, (0.3 * s * build, -0.16 * s, 0.0), (0.3 * s * build, -0.16 * s, 1.5 * s), 0.018 * s, M["brown"], "shovel_shaft", 6)
        boxc(k, (0.2 * s, 0.03, 0.28 * s), (0.3 * s * build, -0.16 * s, 0.14 * s), M["iron"], "shovel_blade")
    elif held == "lamp":
        k.sphere(0.07 * s, loc=(0.3 * s, -0.2 * s, 0.9 * s), material=M["yellow"], name="lamp", segments=8)
