"""Render a world pack's split models (terrain, roads, bridges, buildings...) from a fixed camera, to compare before/after versions of a pack.
  blender -b --factory-startup --python foundry-3d/blender/pack_view.py -- <pack_dir> <out.png> <cam_x_ft> <cam_y_ft> <cam_z_ft> <tgt_x_ft> <tgt_y_ft> <tgt_z_ft> [width height] [--no-buildings]
Camera and target are in world feet (x east, y south, z elevation). Models come from <pack_dir>/placements.json (pivot + file), so what you see is
what the split put in the Foundry scene.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
pack, out = a[0], a[1]
cam_ft = [float(v) for v in a[2:5]]
tgt_ft = [float(v) for v in a[5:8]]
W, H = (int(a[8]), int(a[9])) if len(a) >= 10 and a[8].isdigit() else (1280, 800)
NOB = "--no-buildings" in a
FT = 0.3048

pl = json.load(open(os.path.join(pack, "placements.json"), encoding="utf-8"))
man = json.load(open(os.path.join(pack, "manifest.json"), encoding="utf-8"))
frame_h = man["extent"]["height_ft"]
z0 = man["frame"]["z_origin_ft"] if "frame" in man and "z_origin_ft" in man["frame"] else man.get("z_origin_ft", 0.0)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
for m in pl["files"]:
    if NOB and m.get("layer") == "buildings":
        continue
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(pack, m["file"]))
    new = [o for o in bpy.data.objects if o not in before]
    px, py, pz = m["pivot"]["blender_m"]
    for o in new:
        if o.parent is None:
            o.location = Vector((px, py, pz)) + o.location - Vector((0, 0, 0)) if False else o.location
    # glTF nodes were exported localised (mesh - pivot); move the root nodes to the pivot (Blender frame: x east, y north, z up)
    roots = [o for o in new if o.parent is None]
    for o in roots:
        o.location = Vector((px, py, pz - 0.0))
bpy.context.view_layer.update()
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(50), math.radians(8), math.radians(-35))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
tb = lambda p: Vector((p[0] * FT, (frame_h - p[1]) * FT, (p[2] - z0) * FT))
cam.location = tb(cam_ft)
cam.data.lens = 28
cam.data.clip_end = 5000
cam.rotation_euler = (tb(tgt_ft) - tb(cam_ft)).to_track_quat("-Z", "Y").to_euler()
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.view_settings.view_transform = "Standard"
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = W, H
sc.render.filepath = os.path.abspath(out)
bpy.ops.render.render(write_still=True)
print("rendered", out)
