"""Render review shots of one or more GLBs (e.g. a scene plus its roof).
Usage: blender -b --factory-startup --python blender/preview.py -- <a.glb> [b.glb ...] <out_prefix>
Writes <out_prefix>_top / _high / _door / _mezz / _bar .png (tuned for the tavern; edit SHOTS for other scenes).
"""
import math
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
srcs, out = args[:-1], args[-1]

bpy.ops.wm.read_factory_settings(use_empty=True)
for s in srcs:
    bpy.ops.import_scene.gltf(filepath=s)
sc = bpy.context.scene
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs[1].default_value = 0.9
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN")); sun.data.energy = 3.5
sun.rotation_euler = (math.radians(35), math.radians(10), math.radians(25)); sc.collection.objects.link(sun)
for p in ((0, 0, 4), (-7, -4, 3.5), (7, -4, 3.5), (7, 5, 3.5), (-7, 5, 3.5), (11, 2, 2.5), (-3, 8, 1.5)):
    l = bpy.data.objects.new("p", bpy.data.lights.new("p", "POINT")); l.data.energy = 600
    l.data.color = (1, 0.7, 0.4); l.data.use_shadow = False; l.location = p; sc.collection.objects.link(l)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1400, 900

SHOTS = [  # name, camera location, target, lens, ortho scale
    ("top", (0, 0, 60), (0, 0, 0), 24, 33),
    ("high", (0, -17, 22), (0, 2, 1), 22, None),
    ("door", (0, -9.3, 1.7), (2, 4, 1.6), 17, None),
    ("mezz", (-13.2, -6, 4.8), (6, 2, 1.3), 18, None),
    ("bar", (5, -8, 2.2), (11, 3, 1.3), 20, None),
    ("outside", (34, -38, 20), (0, 0, 5), 30, None),
    ("under", (-9, 7, 1.7), (6, -4, 4.2), 18, None),
    ("skulls", (-4.0, 6.2, 2.6), (-4.0, 8.35, 2.5), 45, None),
    ("upstairs", (-9.5, 3.0, 5.0), (-14.0, -2.0, 4.4), 24, None),
    ("stair", (-8.0, -9.0, 2.0), (-13.0, -5.5, 2.0), 20, None),
    ("hearth", (-3, 5.6, 1.5), (-3, 9.4, 0.9), 30, None),
    ("backbar", (9.0, -1.0, 2.0), (13.8, 0.5, 2.1), 24, None),
    ("brazier", (0.0, -2.2, 1.6), (0.0, 0.0, 1.2), 28, None),
]
for name, loc, target, lens, ortho in SHOTS:
    if ortho:
        cam.data.type = "ORTHO"; cam.data.ortho_scale = ortho
    else:
        cam.data.type = "PERSP"; cam.data.lens = lens
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)
