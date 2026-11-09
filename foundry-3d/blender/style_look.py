"""Several review pictures per building GLB (illustrator/generators/building_styles_look.py).
  blender -b --factory-startup --python foundry-3d/blender/style_look.py -- <glb_dir> <out_dir> <name,name,...> [width height]
env LOOK_VIEWS = comma list of threeq (3/4 from the south-east), back (3/4 from the north-west), street (eye level, 5.5 ft), aerial (steep, from above),
    gable (from the +x end); LOOK_GROUND = grass | snow (snow also lowers and cools the sun: a winter afternoon).
Writes <out_dir>/<name>_<view>.png.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
gdir, out, names = a[0], a[1], [s for s in a[2].split(",") if s]
W, H = (int(a[3]), int(a[4])) if len(a) >= 5 else (960, 720)
VIEWS = [v for v in os.environ.get("LOOK_VIEWS", "threeq").split(",") if v]
SNOW = os.environ.get("LOOK_GROUND", "grass") == "snow"
FT = 0.3048


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    w = bpy.data.worlds.new("w")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.70, 0.76, 0.84, 1) if SNOW else (0.62, 0.74, 0.9, 1)
    bg.inputs[1].default_value = 0.9 if SNOW else 1.0
    sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
    sun.data.energy = 3.2 if SNOW else 4.0
    sun.data.color = (1.0, 0.93, 0.85) if SNOW else (1.0, 0.98, 0.94)
    sun.data.angle = math.radians(2.0)
    sun.rotation_euler = (math.radians(62 if SNOW else 52), math.radians(8), math.radians(-38))
    sc.collection.objects.link(sun)
    cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
    sc.collection.objects.link(cam)
    sc.camera = cam
    eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
    sc.view_settings.view_transform = "Standard"
    sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = W, H
    return sc, cam


for name in names:
    path = os.path.join(gdir, name + ".glb")
    if not os.path.exists(path):
        print("missing", path)
        continue
    for view in VIEWS:
        sc, cam = setup()
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
        mesh = bpy.data.meshes.new("g")
        r = ext * 6
        z = lo.z + 0.55                                    # the pivot is the lowest vertex (bottom of the buried foundation skirt): ground at the floor (sidecar json) - 2 in
        side = os.path.join(gdir, name + ".json")
        if os.path.exists(side):
            import json
            z = lo.z + json.load(open(side))["floor_m"] - 0.05
        mesh.from_pydata([(ctr.x - r, ctr.y - r, z), (ctr.x + r, ctr.y - r, z), (ctr.x + r, ctr.y + r, z), (ctr.x - r, ctr.y + r, z)], [], [(0, 1, 2, 3)])
        go = bpy.data.objects.new("ground", mesh)
        sc.collection.objects.link(go)
        mat = bpy.data.materials.new("gm")
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Base Color"].default_value = (0.78, 0.80, 0.84, 1) if SNOW else (0.10, 0.20, 0.06, 1)
        bsdf.inputs["Roughness"].default_value = 0.9 if SNOW else 1.0
        go.data.materials.append(mat)
        size = ((hi.x - lo.x) ** 2 + (hi.y - lo.y) ** 2 + (hi.z - lo.z) ** 2) ** 0.5 * 0.85
        hz = hi.z - lo.z
        if view == "back":
            loc = Vector((ctr.x - size * 0.9, ctr.y + size * 1.4, lo.z + hz * 0.5 + size * 0.25))
            tz = 0.42
        elif view == "street":
            loc = Vector((ctr.x + size * 0.55, ctr.y - size * 1.05, z + 5.5 * FT))
            tz = 0.45
        elif view == "aerial":
            loc = Vector((ctr.x + size * 0.6, ctr.y - size * 0.8, lo.z + hz + size * 1.3))
            tz = 0.3
        elif view == "gable":
            loc = Vector((ctr.x + size * 1.55, ctr.y - size * 0.35, lo.z + hz * 0.45))
            tz = 0.45
        else:
            loc = Vector((ctr.x + size * 0.85, ctr.y - size * 1.45, lo.z + hz * 0.5 + size * 0.25))
            tz = 0.42
        cam.location = loc
        cam.data.lens = 34
        cam.data.clip_end = 5000
        tgt = Vector((ctr.x, ctr.y, lo.z + hz * tz))
        cam.rotation_euler = (tgt - loc).to_track_quat("-Z", "Y").to_euler()
        sc.render.filepath = os.path.join(out, f"{name}_{view}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", name, view, flush=True)
