"""Render review shots of a foliage scatter on a pack's terrain (merged chunk GLBs from illustrator/generators/foliage.py merge).
  blender -b --factory-startup --python foundry-3d/blender/foliage_preview.py -- <pack_dir> <foliage_dir> <out_prefix> [--lod 0|1|2] [--no-foliage] [--samples N]
Imports the pack's non-foliage placements (terrain, roads, buildings...) and every foliage chunk of <foliage_dir>/placements.json at its pivot.
Shots: <prefix>_aerial.png, <prefix>_street.png (eye level), <prefix>_close.png."""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
pack, fdir, out = a[0], a[1], a[2]
lod = int(a[a.index("--lod") + 1]) if "--lod" in a else None
no_fol = "--no-foliage" in a
bpy.ops.wm.read_factory_settings(use_empty=True)
n_fol = 0


def load(base, entries):
    global n_fol
    for f in entries:
        path = os.path.join(base, f["file"])
        if lod is not None and f.get("lods"):
            alt = next((l for l in f["lods"] if l["lod"] == lod), None)
            if alt:
                path = os.path.join(base, alt["file"])
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        new = [o for o in bpy.data.objects if o not in before]
        root = bpy.data.objects.new("root_" + f["id"], None)
        bpy.context.scene.collection.objects.link(root)
        root.location = tuple(f["pivot"]["blender_m"])
        for o in new:
            if o.parent is None:
                o.parent = root


pl = json.load(open(os.path.join(pack, "placements.json")))
load(pack, [f for f in pl["files"] if f.get("layer") != "foliage" and f["kind"] != "instances"])
if not no_fol:
    fp = json.load(open(os.path.join(fdir, "placements.json")))
    ents = [f for f in fp["files"] if f.get("layer") == "foliage"]
    load(fdir, ents)
    n_fol = len(ents)
sc = bpy.context.scene
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
eng = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
sc.render.engine = "BLENDER_EEVEE" if "BLENDER_EEVEE" in eng else "BLENDER_EEVEE_NEXT"
sc.render.resolution_x, sc.render.resolution_y = 1600, 1000
bpy.context.view_layer.update()
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in bpy.data.objects:
    if o.type == "MESH" and "terrain" in (o.parent.name if o.parent else o.name).lower():
        for c in o.bound_box:
            p = o.matrix_world @ Vector(c)
            lo = Vector(map(min, lo, p))
            hi = Vector(map(max, hi, p))
ctr = (lo + hi) / 2
ext = max(hi.x - lo.x, hi.y - lo.y)
print("foliage chunks imported:", n_fol, "mesh objects:", sum(1 for o in bpy.data.objects if o.type == "MESH"))


def aim(loc, tgt, lens):
    cam.location = loc
    cam.data.lens = lens
    cam.data.clip_end = 5000
    cam.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


def shot(name):
    sc.render.filepath = f"{out}_{name}.png"
    bpy.ops.render.render(write_still=True)


aim((ctr.x + ext * 0.5, ctr.y - ext * 0.85, hi.z + ext * 0.8), (ctr.x, ctr.y, lo.z + 4), 30)
shot("aerial")
aim((ctr.x - ext * 0.25, ctr.y - ext * 0.46, lo.z + 6.0), (ctr.x + ext * 0.1, ctr.y + ext * 0.1, lo.z + 5), 24)
shot("street")
aim((ctr.x + ext * 0.1, ctr.y + ext * 0.12, hi.z + ext * 0.25), (ctr.x + ext * 0.12, ctr.y + ext * 0.38, lo.z + 3), 32)
shot("close")
