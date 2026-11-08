"""Render one review image per species GLB (front view, sun, sky) for the foliage species sheet.
  blender -b --factory-startup --python foundry-3d/blender/foliage_species_sheet.py -- <glb_dir> <out_dir> [--size 512] [--yaw 30] [--season-tag x]
Every <glb_dir>/*.glb is imported alone, framed by its bounding box and written as <out_dir>/<name>.png. illustrator/out/foliage/species_sheet.py drives it
and montages the images."""
import glob
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
gdir, out = a[0], a[1]
size = int(a[a.index("--size") + 1]) if "--size" in a else 512
yaw = float(a[a.index("--yaw") + 1]) if "--yaw" in a else 30.0
only = a[a.index("--only") + 1].split(",") if "--only" in a else None
os.makedirs(out, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.55, 0.72, 0.92, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.1
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 3.6
sun.rotation_euler = (math.radians(52), math.radians(8), math.radians(-35))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x = sc.render.resolution_y = size
# ground disc
bpy.ops.mesh.primitive_circle_add(vertices=48, radius=1, fill_type="NGON")
gr = bpy.context.active_object
gm = bpy.data.materials.new("g")
gm.use_nodes = True
gm.node_tree.nodes["Principled BSDF"].inputs[0].default_value = (0.2, 0.3, 0.12, 1)
gr.data.materials.append(gm)

for f in sorted(glob.glob(os.path.join(gdir, "*.glb"))):
    name = os.path.splitext(os.path.basename(f))[0]
    if only and name not in only:
        continue
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=f)
    new = [o for o in bpy.data.objects if o not in before]
    bpy.context.view_layer.update()
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in new:
        if o.type == "MESH":
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    ctr = (lo + hi) / 2
    ext = max(hi.x - lo.x, hi.y - lo.y, hi.z - lo.z)
    gr.scale = (ext * 0.7,) * 3
    gr.location = (ctr.x, ctr.y, lo.z - 0.01)
    d = ext * 2.3
    cam.data.lens = 50
    cam.data.clip_end = 5000
    cam.location = (ctr.x + d * math.sin(math.radians(yaw)), ctr.y - d * math.cos(math.radians(yaw)), ctr.z + ext * 0.05)
    cam.rotation_euler = (Vector(ctr) - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, name + ".png")
    bpy.ops.render.render(write_still=True)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
print("done")
