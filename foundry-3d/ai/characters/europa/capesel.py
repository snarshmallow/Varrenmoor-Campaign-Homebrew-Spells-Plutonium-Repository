"""Diagnostic: paint the faces build_v2 would delete as the SF3D cape sheet in red, then render views.
Usage: blender -b --factory-startup --python capesel.py -- <in.glb> <out_prefix> X0 Y0
"""
import math
import sys

import bpy
import numpy as np
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, outp, X0, Y0 = a[0], a[1], float(a[2]), float(a[3])
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
me = o.data
sel = [p.index for p in me.polygons if (o.matrix_world @ p.center).x > X0 and (o.matrix_world @ p.center).y > Y0 and 0.25 < (o.matrix_world @ p.center).z < 1.42]
red = bpy.data.materials.new("red"); red.use_nodes = True
red.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (1, 0, 0, 1)
me.materials.append(red)
for i in sel:
    me.polygons[i].material_index = len(me.materials) - 1
print("[capesel] selected", len(sel))
sc = bpy.context.scene
sc.render.engine = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items if "EEVEE" in e.identifier][0]
sc.render.resolution_x, sc.render.resolution_y = 400, 600
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 1.9
for i, ang in enumerate((-90, 0, 90, 180)):
    t = math.radians(ang)
    cam.location = (3 * math.cos(t), 3 * math.sin(t), 0.85)
    cam.rotation_euler = (Vector((0, 0, 0.85)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{outp}_{i}.png"
    bpy.ops.render.render(write_still=True)
