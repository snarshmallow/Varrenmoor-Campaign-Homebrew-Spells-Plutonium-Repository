"""Render the bridge preset samples (see illustrator/generators/bridge_preview.py).
  blender -b --factory-startup --python foundry-3d/blender/bridge_preview.py -- <glb_dir> <out_dir> <id,id,...> <view> [width height]
views: threeq (3/4 from the south-east, above), under (low, straight along the valley so the stream / road passes through the opening), side (elevation), top.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
gdir, out, ids, VIEW = a[0], a[1], [s for s in a[2].split(",") if s], a[3]
W, H = (int(a[4]), int(a[5])) if len(a) >= 6 else (1000, 700)


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
    sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
    sun.data.energy = 4.0
    sun.rotation_euler = (math.radians(55), math.radians(8), math.radians(-40))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.view_settings.view_transform = "Standard"
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    return sc, cam


for bid in ids:
    sc, cam = setup()
    bpy.ops.import_scene.gltf(filepath=os.path.join(gdir, bid + ".glb"))
    bpy.context.view_layer.update()
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    for o in bpy.data.objects:
        if o.type == "MESH" and "_land" not in o.name:
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    ctr = (lo + hi) / 2
    size = max(hi.x - lo.x, hi.y - lo.y) * 0.95 + 4
    # the bridge runs along +x (u); the valley (stream / road below) runs along y
    if VIEW == "under":
        loc = Vector((ctr.x + size * 0.08, ctr.y - size * 1.25, lo.z + (hi.z - lo.z) * 0.12 + 1.2))
        tgt = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * 0.35))
    elif VIEW == "side":
        loc = Vector((ctr.x, ctr.y - size * 1.6, ctr.z))
        tgt = ctr
    elif VIEW == "top":
        loc = Vector((ctr.x, ctr.y, ctr.z + size * 1.5))
        tgt = ctr
    else:
        loc = Vector((ctr.x + size * 0.55, ctr.y - size * 0.95, hi.z + size * 0.28))
        tgt = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * 0.4))
    cam.location = loc
    cam.data.lens = 32
    cam.data.clip_end = 5000
    cam.rotation_euler = (tgt - loc).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, f"{bid}_{VIEW}.png")
    bpy.ops.render.render(write_still=True)
    print("rendered", bid, VIEW, flush=True)
