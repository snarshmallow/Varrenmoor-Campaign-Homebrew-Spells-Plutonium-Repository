"""Contact sheet of a token GLB: front / 3-4 / side / back / top views (Blender, Eevee).
Usage: blender -b --factory-startup --python turntable.py -- <in.glb> <out.png>
Front = Blender -Y (the token convention: the model faces -Y).
"""
import math
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
print("[turntable] bbox min", tuple(round(v, 3) for v in lo), "max", tuple(round(v, 3) for v in hi))
ctr = (lo + hi) / 2
h = hi.z - lo.z

sc = bpy.context.scene
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items] else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 400, 600
sc.render.film_transparent = False
w = bpy.data.worlds.new("w"); sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.75, 0.75, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 0.45
sc.view_settings.view_transform = "Standard"
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
sun.data.energy = 2.0; sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = h * 1.15

views = [("front", -90), ("3/4", -45), ("side", 0), ("back", 90), ("left", 180)]
files = []
for i, (nm, ang) in enumerate(views):
    r = 6.0
    t = math.radians(ang)
    cam.location = (ctr.x + r * math.cos(t), ctr.y + r * math.sin(t), ctr.z)
    d = Vector((ctr.x, ctr.y, ctr.z)) - cam.location
    cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    f = out.replace(".png", f"_{i}.png")
    sc.render.filepath = f
    bpy.ops.render.render(write_still=True)
    files.append(f)

# stitch
imgs = [bpy.data.images.load(f) for f in files]
W, H = 400, 600
sheet = bpy.data.images.new("sheet", W * len(imgs), H)
px = [0.0] * (W * len(imgs) * H * 4)
for k, im in enumerate(imgs):
    p = list(im.pixels)
    for y in range(H):
        row = p[y * W * 4:(y + 1) * W * 4]
        s = (y * W * len(imgs) + k * W) * 4
        px[s:s + W * 4] = row
sheet.pixels = px
sheet.filepath_raw = out
sheet.file_format = "PNG"
sheet.save()
import os
for f in files:
    os.remove(f)
print("[turntable] wrote", out, "height", round(h, 3))
