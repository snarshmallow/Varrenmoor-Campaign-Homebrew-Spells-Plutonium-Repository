"""Render one review picture per building-style sample GLB (see illustrator/generators/building_styles_preview.py).
  blender -b --factory-startup --python foundry-3d/blender/style_preview.py -- <glb_dir> <out_dir> <id,id,...> [width height]
Writes <out_dir>/<id>.png : a 3/4 view from the door side (south-east), flat green ground, warm sun, sky-blue world.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
gdir, out, ids = a[0], a[1], [s for s in a[2].split(",") if s]
VIEW = os.environ.get("STYLE_VIEW", "")      # "" = standard 3/4 view; "front" = straight at the door wall (close), "threeq_close" = closer 3/4
W, H = (int(a[3]), int(a[4])) if len(a) >= 5 else (900, 680)


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
    sun.rotation_euler = (math.radians(52), math.radians(8), math.radians(-38))
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
    path = os.path.join(gdir, bid + ".glb")
    if not os.path.exists(path):
        print("missing", path)
        continue
    bpy.ops.import_scene.gltf(filepath=path)
    bpy.context.view_layer.update()
    lo = Vector((1e9,) * 3)
    hi = Vector((-1e9,) * 3)
    for o in bpy.data.objects:
        if o.type == "MESH":
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    ctr = (lo + hi) / 2
    ext = max(hi.x - lo.x, hi.y - lo.y)
    # ground
    mesh = bpy.data.meshes.new("g")
    r = ext * 4
    z = lo.z + 0.05
    mesh.from_pydata([(ctr.x - r, ctr.y - r, z), (ctr.x + r, ctr.y - r, z), (ctr.x + r, ctr.y + r, z), (ctr.x - r, ctr.y + r, z)], [], [(0, 1, 2, 3)])
    go = bpy.data.objects.new("ground", mesh)
    sc.collection.objects.link(go)
    mat = bpy.data.materials.new("gm")
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.10, 0.20, 0.06, 1)
    mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 1.0
    go.data.materials.append(mat)
    size = ((hi.x - lo.x) ** 2 + (hi.y - lo.y) ** 2 + (hi.z - lo.z) ** 2) ** 0.5 * 0.85
    loc = Vector((ctr.x + size * 0.85, ctr.y - size * 1.45, lo.z + (hi.z - lo.z) * 0.5 + size * 0.25))
    if VIEW == "front":
        loc = Vector((ctr.x, ctr.y - size * 1.0, lo.z + (hi.z - lo.z) * 0.22))
    elif VIEW == "gable":            # from the -x end (the end opposite a west tower), slightly raised
        loc = Vector((ctr.x - size * 0.95, ctr.y - size * 0.25, lo.z + (hi.z - lo.z) * 0.3))
    elif VIEW == "threeq_close":
        loc = Vector((ctr.x + size * 0.55, ctr.y - size * 0.8, lo.z + (hi.z - lo.z) * 0.3))
    cam.location = loc
    cam.data.lens = 34
    cam.data.clip_end = 5000
    tgt = Vector((ctr.x, ctr.y, lo.z + (hi.z - lo.z) * (0.3 if VIEW else 0.42)))
    cam.rotation_euler = (tgt - loc).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = os.path.join(out, bid + (("_" + VIEW) if VIEW else "") + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", bid, flush=True)
