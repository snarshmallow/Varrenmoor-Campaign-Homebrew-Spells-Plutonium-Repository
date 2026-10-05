"""Hang an ornate framed painting on a wall, inside a scene generator, with eyes that can follow players.

Baked into the scene model so the painting can never be misplaced by tile placement. The two eyeballs are separate
glTF nodes named watcher_eye_* with extras: watcher=1, maxAngle (degrees) and lookDir (glTF-space direction the pupil
faces at rest). The varrenmoor-watchers module turns them toward the nearest player token.
"""
import json
import math
from pathlib import Path

import bpy

TEX = Path(__file__).resolve().parent.parent / "textures"
_MATS = {}


def _image_material(k, name, image_file):
    """Painting material: the image with explicit 0..1 UVs, plus a little emission so it reads in dark rooms."""
    if name in _MATS:
        return _MATS[name]
    img = bpy.data.images.load(str(TEX / image_file))
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = img
    nt.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    em = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    nt.links.new(t.outputs["Color"], em)
    bsdf.inputs["Emission Strength"].default_value = 0.25
    m.use_backface_culling = True
    _MATS[name] = m
    return m


def eyes_for(image_stem):
    data = json.loads((TEX / "eyes.json").read_text())[image_stem]
    return data["size"], data["eyes"]


def hang_painting(k, mats, skulls, image_stem, wall_point, facing, bottom_z, canvas_w, canvas_h, idx):
    """wall_point: (x, y) on the wall face; facing: outward unit axis vector (fx, fy) the painting looks toward;
    bottom_z: height of the frame's bottom edge; canvas_w/h in metres. mats: dict with brass, doak, iron, amber, soot."""
    fx, fy = facing
    rx, ry = -fy, fx                                   # right-hand vector for a viewer facing the painting
    cx, cy = wall_point
    fr = 0.12 * (canvas_h / 1.4) ** 0.5                # frame width scales a little with the painting

    def P(u, v, h):
        return cx + rx * u + fx * v, cy + ry * u + fy * v, h

    def LB(u0, u1, v0, v1, h0, h1, mat, name, bevel=0.0):
        (xa, ya, _), (xb, yb, _) = P(u0, v0, h0), P(u1, v1, h1)
        return k.box((abs(xb - xa), abs(yb - ya), h1 - h0), loc=((xa + xb) / 2, (ya + yb) / 2, (h0 + h1) / 2),
                     material=mat, name=name, bevel=bevel)

    z0 = bottom_z + fr                                 # canvas bottom
    z1 = z0 + canvas_h
    hw = canvas_w / 2
    brass, doak, iron = mats["brass"], mats["doak"], mats["iron"]
    LB(-hw - fr, hw + fr, 0.0, 0.03, bottom_z, z1 + fr, doak, f"pt{idx}_back")
    LB(-hw - fr, hw + fr, 0.03, 0.10, bottom_z, bottom_z + fr, brass, f"pt{idx}_frame_b", 0.012)
    LB(-hw - fr, hw + fr, 0.03, 0.10, z1, z1 + fr, brass, f"pt{idx}_frame_t", 0.012)
    LB(-hw - fr, -hw, 0.03, 0.10, bottom_z + fr, z1, brass, f"pt{idx}_frame_l", 0.012)
    LB(hw, hw + fr, 0.03, 0.10, bottom_z + fr, z1, brass, f"pt{idx}_frame_r", 0.012)
    for u in (-hw - fr / 2, hw + fr / 2):
        for h in (bottom_z + fr / 2, z1 + fr / 2):
            x, y, z = P(u, 0.105, h)
            k.sphere(0.045, loc=(x, y, z), material=iron, name=f"pt{idx}_boss", segments=8)
    sx, sy, _ = P(0, 0.05, z1 + fr)
    skulls.add(sx, sy, z1 + fr, face_to=(sx + fx * 10, sy + fy * 10), s=0.07)       # little crest skull

    # canvas: one quad with explicit UVs, normal toward the viewer
    mat = _image_material(k, f"painting_{image_stem}", f"painting_{image_stem}.jpg")
    me = bpy.data.meshes.new(f"pt{idx}_canvas")
    verts = [P(-hw, 0.045, z0), P(hw, 0.045, z0), P(hw, 0.045, z1), P(-hw, 0.045, z1)]
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="UVMap")
    for li, (u, v) in zip(me.polygons[0].loop_indices, ((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[li].uv = (u, v)
    me.update()
    ob = bpy.data.objects.new(f"pt{idx}_canvas", me)
    bpy.context.scene.collection.objects.link(ob)
    ob.data.materials.append(mat)

    # eyes: separate nodes at the glowing sockets (positions measured from the generated image)
    (iw, ih), eyes = eyes_for(image_stem)
    er = 0.026 * (canvas_w / 0.95) ** 0.5
    depth_axis_x = abs(fx) > 0.5                       # the facing axis is X for east/west walls, otherwise Y
    flat = 0.4                                         # eyeballs are flattened along the facing axis: they sit in the canvas, not on it
    for side, e in zip(("L", "R"), eyes):
        px, py = e[0], e[1]
        er_i = (e[2] / iw * canvas_w) if len(e) > 2 else er          # per-eye radius measured from the socket (px -> m)
        u = (px / iw - 0.5) * canvas_w
        h = z0 + (1 - py / ih) * canvas_h
        x, y, z = P(u, 0.040, h)                       # centre just behind the canvas plane (v = 0.045): only a shallow cap shows
        eye = k.sphere(er_i, loc=(x, y, z), scale=((flat, 1, 1) if depth_axis_x else (1, flat, 1)), material=mats["amber"],
                       name=f"watcher_eye_{idx}{side}", segments=12)
        px_, py_, pz_ = P(u, 0.040 + er_i * flat * 0.9, h)
        pupil = k.sphere(er_i * 0.6, loc=(px_, py_, pz_), scale=((0.25, 0.2, 1.0) if depth_axis_x else (0.2, 0.25, 1.0)),
                         material=mats["soot"], name="pupil", segments=8)
        bpy.ops.object.select_all(action="DESELECT")
        eye.select_set(True)
        pupil.select_set(True)
        bpy.context.view_layer.objects.active = eye
        bpy.ops.object.join()
        eye["separate"] = 1
        eye["watcher"] = 1
        eye["maxAngle"] = 45
        eye["lookDir"] = [float(fx), 0.0, float(-fy)]       # Blender (x, y, z) -> glTF (x, z, -y)
