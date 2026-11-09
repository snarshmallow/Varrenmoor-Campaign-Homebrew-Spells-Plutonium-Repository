"""Head close-ups of a token GLB (front, 3/4, side), for checking the face.
Usage: blender -b --factory-startup --python closeup.py -- <in.glb> <out.png> [emit]
'emit' renders the base colour flat (no lighting), used to grab the current front view of the head texture.
"""
import math
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, out = a[0], a[1]
body = "body" in a                                  # body: side/back views of the torso (cape check) instead of the head
flat = "emit" in a
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
pts = [o.matrix_world @ v.co for o in objs for v in o.data.vertices]
top = max(p.z for p in pts)
head = [p for p in pts if p.z > top - 0.26]
cx = sum(p.x for p in head) / len(head)
cz = top - 0.13
sc = bpy.context.scene
sc.render.engine = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items if "EEVEE" in e.identifier][0]
sc.render.resolution_x = sc.render.resolution_y = 1024 if flat else 512
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w"); sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.75, 0.75, 0.75, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0 if flat else 0.45
if flat:
    for m in bpy.data.materials:
        nt = m.node_tree
        b = nt.nodes.get("Principled BSDF")
        if b and b.inputs["Base Color"].links:
            em = nt.nodes.new("ShaderNodeEmission")
            nt.links.new(b.inputs["Base Color"].links[0].from_socket, em.inputs["Color"])
            outn = [n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"][0]
            nt.links.new(em.outputs[0], outn.inputs["Surface"])
else:
    sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN")); sc.collection.objects.link(sun)
    sun.data.energy = 2.0; sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.type = "ORTHO"; cam.data.ortho_scale = 0.32
if body:
    cam.data.ortho_scale, cz, cx = 1.2, 0.9, 0.0
views = [("front", -90)] if flat else ([("side", 0), ("back3/4", 45), ("back", 90)] if body else [("front", -90), ("3/4", -45), ("side", 0)])
files = []
for i, (nm, ang) in enumerate(views):
    t = math.radians(ang)
    cam.location = (cx + 3 * math.cos(t), 3 * math.sin(t), cz)
    cam.rotation_euler = (Vector((cx, 0, cz)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    f = out if flat else out.replace(".png", f"_{i}.png")
    sc.render.filepath = f
    bpy.ops.render.render(write_still=True)
    files.append(f)
print("[closeup] window centre x", round(cx, 4), "z", round(cz, 4), "ortho 0.32", files)
