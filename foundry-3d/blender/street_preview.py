"""Render review shots of a split world pack (placements.json + models/*.glb) at true placement.
  blender -b --factory-startup --python foundry-3d/blender/street_preview.py -- <pack_dir> <out_prefix> [--focus bld_house_078] [--only buildings,roads]
Shots: <prefix>_aerial.png (3/4 view of the whole pack), <prefix>_street.png (eye level along the street), <prefix>_door.png (close on --focus building's door side),
<prefix>_open.png (same, door leaf rotated open 90 degrees about its hinge, to prove the leaf is a separate movable node).
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
pack, out = a[0], a[1]
focus = a[a.index("--focus") + 1] if "--focus" in a else None
sky = a[a.index("--sky") + 1] if "--sky" in a else None      # equirect image (illustrator/generators/skybox.py): centre = east = Blender +X, so no rotation is needed
pl = json.load(open(os.path.join(pack, "placements.json")))
bpy.ops.wm.read_factory_settings(use_empty=True)
objs = {}
for f in pl["files"]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(pack, f["file"]))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("root_" + f["id"], None)
    bpy.context.scene.collection.objects.link(root)
    px, py, pz = f["pivot"]["blender_m"]
    root.location = (px, py, pz)
    for o in new:
        if o.parent is None:
            o.parent = root
        objs[o.name] = o
sc = bpy.context.scene
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
if sky:
    env = w.node_tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(sky)
    w.node_tree.links.new(env.outputs["Color"], w.node_tree.nodes["Background"].inputs[0])
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 4.0
sun.rotation_euler = (math.radians(50), math.radians(8), math.radians(-35))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
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


def aim(loc, tgt, lens):
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def shot(name):
    sc.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)


aim((ctr.x + ext * 0.55, ctr.y - ext * 0.85, hi.z + ext * 0.75), (ctr.x, ctr.y, lo.z + 8), 28)
shot("aerial")
if focus:
    fo = next(o for o in bpy.data.objects if o.name == focus)
    door = next((o for o in bpy.data.objects if o.name.startswith(focus + "_") and o.get("isDoor")), None)
    bpy.context.view_layer.update()
    fc = fo.matrix_world.translation
    if door:
        dp = door.matrix_world.translation
        # out of the door along the horizontal direction from the building centre to the door
        d = (dp - Vector((fc.x, fc.y, dp.z)))
        d.z = 0
        d.normalize()
        aim(dp + d * 7 + Vector((0, 0, 0.5)), dp + Vector((0, 0, 1.0)), 24)
        shot("door")
        door.rotation_mode = "XYZ"; door.rotation_euler = (0, 0, math.radians(100))
        bpy.context.view_layer.update()
        shot("open")
        door.rotation_euler = (0, 0, 0)
        aim(dp + d * 16 + Vector((d.y, -d.x, 0)) * 10 + Vector((0, 0, 2.0)), dp + Vector((0, 0, 1.5)), 26)
        shot("street")
