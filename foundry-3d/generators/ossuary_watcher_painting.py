"""An ornate framed painting of the Ossuary clerk whose eyes follow you ("always watching").

The eyeballs are separate glTF nodes named watcher_eye_L / watcher_eye_R (custom properties exported as extras:
watcher=1, maxAngle=45). They are NOT merged into the model, so the varrenmoor-watchers module can rotate them toward
the nearest player token every few frames. Rest pose: the pupil slit looks straight out of the front of the painting.
Front of the painting = Blender -Y (glTF +Z); it hangs on a wall behind it (+Y). Size about 2.8 x 0.2 x 2.0 m.
"""
import math

import bpy
from _parts import Skulls

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"

CW, CH = 2.4, 1.6                  # canvas size, metres (image is 3:2)
FR = 0.2                           # frame width
EYES_PX = {"L": (537, 189), "R": (617, 166)}   # eye centres in the 1536 x 1024 source art
EYE_R = 0.03


def build(k):
    brass = k.tex("brass", "tarnished_antique_brass", tile=0.6, rough=0.4, metal=0.4)
    doak = k.tex("dark_oak", "dark_antique_oak", tile=1.2, rough=0.65)
    iron = k.tex("iron", "aged_wrought_iron", tile=0.6, rough=0.6, metal=0.3)
    bone = k.tex("bone", "weathered_structural_bone", tile=0.8, rough=0.6)
    soot = k.mat("soot", (0.02, 0.02, 0.02), roughness=1.0)
    teeth = k.mat("skull_teeth", (0.88, 0.84, 0.72), roughness=0.55)
    amber = k.mat("eye_amber", (1.0, 0.35, 0.03), roughness=0.3, emission=(1.0, 0.33, 0.03))

    # canvas: image material with explicit 0..1 UVs (the plane's own), a little emission so it reads in dark rooms
    from pathlib import Path
    tex_path = Path(__file__).resolve().parent.parent / "textures" / "painting_clerk.jpg"
    img = bpy.data.images.load(str(tex_path))
    canvas_mat = bpy.data.materials.new("painting_clerk")
    if canvas_mat.node_tree is None:
        canvas_mat.use_nodes = True
    nt = canvas_mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    t = nt.nodes.new("ShaderNodeTexImage"); t.image = img
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    em = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    nt.links.new(t.outputs["Color"], em)
    bsdf.inputs["Emission Strength"].default_value = 0.25
    canvas_mat.use_backface_culling = True

    zc = FR + CH / 2                 # canvas centre height
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))   # built at the origin: apply scale + rotation, then lift
    cv = bpy.context.active_object
    cv.scale = (CW, CH, 1)
    bpy.ops.object.transform_apply(scale=True)
    cv.rotation_euler = (math.radians(90), 0, 0)      # normal toward -Y
    bpy.ops.object.transform_apply(rotation=True)
    cv.location = (0, 0, zc)
    cv.name = "canvas"
    cv.data.materials.append(canvas_mat)

    def B(x0, x1, y0, y1, z0, z1, mat, name="part", bevel=0.0):
        return k.box((x1 - x0, y1 - y0, z1 - z0), loc=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), material=mat, name=name, bevel=bevel)

    # back panel and ornate frame (outer brass moulding, inner dark liner, corner bosses)
    B(-CW / 2 - FR, CW / 2 + FR, 0.02, 0.1, 0, CH + 2 * FR, doak, "back")
    ow, oh = CW / 2 + FR, CH + 2 * FR
    B(-ow, ow, -0.06, 0.02, 0, FR, brass, "frame_bottom", 0.015)
    B(-ow, ow, -0.06, 0.02, oh - FR, oh, brass, "frame_top", 0.015)
    B(-ow, -CW / 2, -0.06, 0.02, FR, oh - FR, brass, "frame_left", 0.015)
    B(CW / 2, ow, -0.06, 0.02, FR, oh - FR, brass, "frame_right", 0.015)
    B(-CW / 2 - 0.03, CW / 2 + 0.03, -0.075, -0.06, FR - 0.03, FR + 0.03, doak, "liner_bottom")
    B(-CW / 2 - 0.03, CW / 2 + 0.03, -0.075, -0.06, oh - FR - 0.03, oh - FR + 0.03, doak, "liner_top")
    B(-CW / 2 - 0.03, -CW / 2 + 0.03, -0.075, -0.06, FR + 0.03, oh - FR - 0.03, doak, "liner_left")
    B(CW / 2 - 0.03, CW / 2 + 0.03, -0.075, -0.06, FR + 0.03, oh - FR - 0.03, doak, "liner_right")
    for sx in (-1, 1):
        for z in (FR / 2, oh - FR / 2):
            k.sphere(0.09, loc=(sx * (CW / 2 + FR / 2 + 0.0), -0.07, z), material=iron, name="corner_boss", segments=8)
    # crest: a small skull above the frame, looking out at the viewer
    sk = Skulls()
    sk.add(0, -0.02, oh, face_to=(0, -10), s=0.12)
    sk.finish(bone, soot, teeth, name="crest_skull")

    # the eyes: amber ball + vertical black pupil slit, origin at the eyeball centre, kept as their own nodes
    for side, (px, py) in EYES_PX.items():
        ex = (px - 768) / 1536 * CW
        ez = zc + (512 - py) / 1024 * CH
        eye = k.sphere(EYE_R, loc=(ex, -0.03, ez), material=amber, name=f"watcher_eye_{side}", segments=12)
        pupil = k.sphere(EYE_R * 0.62, loc=(ex, -0.03 - EYE_R * 0.97, ez), scale=(0.2, 0.4, 1.0), material=soot, name="pupil", segments=8)
        bpy.ops.object.select_all(action="DESELECT")
        eye.select_set(True); pupil.select_set(True)
        bpy.context.view_layer.objects.active = eye
        bpy.ops.object.join()
        eye["separate"] = 1
        eye["watcher"] = 1
        eye["maxAngle"] = 45
        eye["eyeSide"] = side
