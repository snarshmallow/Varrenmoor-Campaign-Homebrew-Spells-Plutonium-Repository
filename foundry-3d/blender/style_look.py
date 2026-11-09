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
FIGURE = os.environ.get("LOOK_FIGURE", "") not in ("", "0")       # 1 = a 5 ft 9 in figure and a 5 ft bar (1 ft stripes) at the front corner, for scale


def _flat(name, rgb):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    m.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*rgb, 1)
    return m


def _box(sc, name, x0, x1, y0, y1, z0, z1, mat):
    me = bpy.data.meshes.new(name)
    v = [(x, y, zz) for zz in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    f = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    me.from_pydata(v, [], f)
    o = bpy.data.objects.new(name, me)
    o.data.materials.append(mat)
    sc.collection.objects.link(o)


def add_scale_refs(sc, lo, hi, zg):
    """Dark figure (5 ft 9 in: legs, torso, head) and a 5 ft bar striped every foot, standing 2.5 ft off the building's south-east corner."""
    x, y = hi.x + 2.5 * FT, lo.y - 2.5 * FT
    fig = _flat("fig", (0.05, 0.05, 0.06))
    _box(sc, "legs", x - 0.55 * FT, x + 0.55 * FT, y - 0.35 * FT, y + 0.35 * FT, zg, zg + 2.9 * FT, fig)
    _box(sc, "torso", x - 0.75 * FT, x + 0.75 * FT, y - 0.4 * FT, y + 0.4 * FT, zg + 2.9 * FT, zg + 4.95 * FT, fig)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.38 * FT, location=(x, y, zg + 5.37 * FT))
    bpy.context.active_object.data.materials.append(fig)
    a, b = _flat("bar_a", (0.85, 0.12, 0.08)), _flat("bar_b", (0.95, 0.95, 0.92))
    bx = x + 2.0 * FT
    for k in range(5):
        _box(sc, f"bar{k}", bx - 0.12 * FT, bx + 0.12 * FT, y - 0.12 * FT, y + 0.12 * FT, zg + k * FT, zg + (k + 1) * FT, a if k % 2 == 0 else b)


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
        if FIGURE:
            add_scale_refs(sc, lo, hi, z)
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
