"""Cutaway renders of a split world pack whose buildings have interiors (worldpack_interiors nodes: <id>, <id>_shell_fN, <id>_int_fN, <id>_roof, <id>_props_fN).
  blender -b --factory-startup --python foundry-3d/blender/interior_preview.py -- <pack_dir> <out_prefix> [--focus bld_house_044,bld_house_064] [--street]
Per focus house: <prefix>_<id>_cut_top.png (roof off, all storeys), <prefix>_<id>_cut_ground.png (roof + upper storeys off, only 2-storey houses), <prefix>_<id>_cut_low.png (oblique, ground).
--street: <prefix>_street_cutaway.png, every roof off, upper storeys off, high oblique view over the whole pack.
Paths must be absolute (Blender treats drive-less paths as drive-root relative).
"""
import json
import math
import os
import re
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
pack, out = a[0], a[1]
focus = a[a.index("--focus") + 1].split(",") if "--focus" in a else []
street = "--street" in a
pl = json.load(open(os.path.join(pack, "placements.json")))
bpy.ops.wm.read_factory_settings(use_empty=True)
objs = {}
for f in pl["files"]:
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(pack, f["file"]))
    new = [o for o in bpy.data.objects if o not in before]
    root = bpy.data.objects.new("root_" + f["id"], None)
    bpy.context.scene.collection.objects.link(root)
    root.location = tuple(f["pivot"]["blender_m"])
    for o in new:
        if o.parent is None:
            o.parent = root
        objs[o.name] = o
sc = bpy.context.scene
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.62, 0.74, 0.9, 1)
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN"))
sun.data.energy = 4.5
sun.rotation_euler = (math.radians(40), math.radians(8), math.radians(-35))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c"))
sc.collection.objects.link(cam)
sc.camera = cam
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1500, 1000
PAT = re.compile(r"^(?P<id>.+?)_(?P<kind>roof|shell_f(?P<s1>\d+)|int_f(?P<s2>\d+)|props_f(?P<s3>\d+))(\.\d+)?$")


def show(roof=True, max_storey=99, hide_props=False):
    for n, o in objs.items():
        m = PAT.match(n)
        if not m:
            continue
        k = m.group("kind")
        hid = False
        if k == "roof":
            hid = not roof
        else:
            s = int(m.group("s1") or m.group("s2") or m.group("s3"))
            hid = s > max_storey
            if k.startswith("props") and hide_props:
                hid = True
        o.hide_render = o.hide_viewport = hid


def bbox(pred):
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    bpy.context.view_layer.update()
    for n, o in objs.items():
        if o.type == "MESH" and pred(n):
            for c in o.bound_box:
                p = o.matrix_world @ Vector(c)
                lo, hi = Vector(map(min, lo, p)), Vector(map(max, hi, p))
    return lo, hi


def aim(loc, tgt, lens):
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def shot(name):
    sc.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)


for fid in focus:
    lo, hi = bbox(lambda n: n == fid or n.startswith(fid + "_"))
    c = (lo + hi) / 2
    ext = max(hi.x - lo.x, hi.y - lo.y)
    floors = len({int(m.group("s2")) for n in objs for m in [PAT.match(n)] if m and n.startswith(fid + "_") and m.group("s2")})
    show(roof=False)
    aim((c.x + ext * 0.5, c.y - ext * 1.2, c.z + ext * 1.9), (c.x, c.y, lo.z + 3.0), 40)
    shot(f"{fid}_cut_top")
    if floors > 1:
        show(roof=False, max_storey=0)
        shot(f"{fid}_cut_ground")
    show(roof=False, max_storey=0)
    aim((c.x + ext * 0.2, c.y - ext * 1.25, c.z + ext * 0.75), (c.x, c.y, lo.z + 1.2), 40)
    shot(f"{fid}_cut_low")
if street:
    show(roof=False, max_storey=0)
    lo, hi = bbox(lambda n: n.startswith('bld_'))
    ctr = (lo + hi) / 2
    ext = max(hi.x - lo.x, hi.y - lo.y)
    aim((ctr.x + ext * 0.25, ctr.y - ext * 0.7, hi.z + ext * 0.95), (ctr.x, ctr.y, lo.z + 4), 32)
    shot("street_cutaway")
