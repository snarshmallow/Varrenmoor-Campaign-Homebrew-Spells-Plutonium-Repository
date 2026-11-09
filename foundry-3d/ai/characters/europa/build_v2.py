"""Europa token v2, built on the v1 SF3D mesh in Blender.
  geo  stage: delete the SF3D cape sheet, level the head (pitch/yaw from the face normal, smooth falloff over the neck), add a
              procedural cape hanging down her back (folds, gold-trimmed texture), scale to 1.676 m, centre, base Z=0.
  face stage: front-facing head faces get their own material + planar front UVs on the composited face texture.
Usage:
  blender -b --factory-startup --python build_v2.py -- geo  <sf3d.glb> <geo.glb> <cape_tex.png> [nocut] [nolevel]
  blender -b --factory-startup --python build_v2.py -- face <geo.glb> <out.glb> <face_tex.png>
The face window (centre cx, cz; 0.32 m square) is computed the same way as closeup.py, so a flat front render of geo.glb
from closeup.py lines up with the UVs.
"""
import math
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

a = sys.argv[sys.argv.index("--") + 1:]
stage, src, dst, tex = a[0], a[1], a[2], a[3]
CUT = "nocut" not in a          # nocut: the input mesh has no SF3D side cape (v2 reference), skip the sheet deletion
LEVEL = "nolevel" not in a      # nolevel: skip the head pitch/yaw correction
HEIGHT = 1.676
WIN = 0.32


def load(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    ms = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    bpy.ops.object.select_all(action="DESELECT")
    for o in ms:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ms[0]
    if len(ms) > 1:
        bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def mat(name, img_path, double=False):
    m = bpy.data.materials.new(name)
    if m.node_tree is None:
        m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Metallic"].default_value = 0.0
    b.inputs["Roughness"].default_value = 0.85
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(img_path)
    t.image.pack()
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    m.use_backface_culling = not double
    return m


def geo():
    o = load(src)
    me = o.data
    # 1. SF3D cape sheet (left side, behind; see capesel.py)
    bm = bmesh.new(); bm.from_mesh(me)
    kill = [] if not CUT else [f for f in bm.faces if (lambda c: (c.x > 0.22 and c.y > 0.03 and 0.25 < c.z < 1.42) or
            (c.x > 0.05 and c.y > 0.19 and 0.45 < c.z < 1.3) or (c.x > 0.15 and c.y > 0.06 and 0.4 < c.z < 0.95) or (c.x > 0.38 and c.z < 0.6))(f.calc_center_median())]   # sheet + its root on her back
    bmesh.ops.delete(bm, geom=kill, context="FACES")
    # drop small loose islands left behind
    bm.faces.ensure_lookup_table()
    seen, islands = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, isl = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop(); isl.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        islands.append(isl)
    small = [] if not CUT else [f for isl in islands if (len(isl) < 12 and sum(g.calc_center_median().x for g in isl) / len(isl) > 0.15) or len(isl) < 4 for f in isl]
    bmesh.ops.delete(bm, geom=small, context="FACES")
    print("[v2] deleted cape faces", len(kill), "loose", len(small))

    # 2. level the head: face-front normal -> -Y
    top = max(v.co.z for v in bm.verts)
    bm.normal_update()
    fn = [f for f in bm.faces if f.calc_center_median().z > top - 0.25 and f.normal.y < -0.6]
    hx = sum(f.calc_center_median().x for f in fn) / len(fn)
    fn = [f for f in fn if abs(f.calc_center_median().x - hx) < 0.07]          # the face opening only, not the hood rim
    n = sum((f.normal * f.calc_area() for f in fn), Vector()).normalized()
    pitch = math.atan2(n.z, -n.y)                  # rotate about +X by this to bring n.z to 0
    yaw = math.atan2(-n.x, -n.y)                   # rotate about +Z by this to bring n.x to 0
    hv = [v for v in bm.verts if v.co.z > top - 0.28]
    piv = Vector((sum(v.co.x for v in hv) / len(hv), sum(v.co.y for v in hv) / len(hv), top - 0.33))
    for v in bm.verts:
        w = smoothstep(piv.z - 0.03, piv.z + 0.08, v.co.z) if LEVEL else 0
        if w <= 0:
            continue
        R = Matrix.Rotation(yaw * w, 3, "Z") @ Matrix.Rotation(pitch * w, 3, "X")
        v.co = piv + R @ (v.co - piv)
    bm.normal_update()
    fn = [f for f in bm.faces if f.calc_center_median().z > top - 0.25 and f.normal.y < -0.6]
    n2 = sum((f.normal * f.calc_area() for f in fn), Vector()).normalized()
    print("[v2] head normal", tuple(round(x, 3) for x in n), "-> pitch", round(math.degrees(pitch), 2), "yaw", round(math.degrees(yaw), 2),
          "after", tuple(round(x, 3) for x in n2), "pivot", tuple(round(x, 3) for x in piv))
    bm.to_mesh(me); bm.free()

    # 3. back profile for the cape: max y of the body per (x, z), widened and smoothed so it clears arms
    V = np.array([v.co[:] for v in me.vertices])
    legs = V[(V[:, 2] > 0.35) & (V[:, 2] < 0.6)]
    cxb = float(np.median(legs[:, 0]))
    zt, zb = top - 0.30, 0.36
    rows, cols = 44, 26
    us = np.linspace(-1, 1, cols)
    ts = np.linspace(0, 1, rows)
    hw = lambda t: 0.19 + 0.14 * t ** 0.8
    zs = zt - (zt - zb) * ts

    def back(x, z):
        s = (np.abs(V[:, 0] - x) < 0.08) & (V[:, 2] > z - 0.08) & (V[:, 2] < z + 0.04)
        return V[s, 1].max() if s.any() else None

    prof = np.zeros((rows, cols))
    for i, t in enumerate(ts):
        for j, u in enumerate(us):
            b = back(cxb + u * hw(t), zs[i])
            prof[i, j] = b if b is not None else np.nan
    for i in range(rows):                                   # fill gaps from neighbours
        r = prof[i]
        if np.isnan(r).all():
            prof[i] = prof[i - 1]
        else:
            r[np.isnan(r)] = np.nanmax(r)
    env = prof.copy()
    for i in range(rows):                                   # cape falls: never tucks in below a bulge above it
        env[i] = np.maximum(env[i], env[max(0, i - 1)] - 0.004)
    k = np.ones(5) / 5
    for i in range(rows):
        env[i] = np.convolve(np.pad(env[i], 2, mode="edge"), k, mode="valid")
    for j in range(cols):
        env[:, j] = np.convolve(np.pad(env[:, j], 2, mode="edge"), k, mode="valid")
    NF = 5
    verts, faces, uvs = [], [], []
    rng = np.random.default_rng(7)
    noise = rng.normal(0, 0.002, (rows, cols))
    for i, t in enumerate(ts):
        A = 0.006 + 0.04 * t
        for j, u in enumerate(us):
            p = (u + 1) / 2 * NF * 2 * math.pi
            fold = A * (0.5 + 0.5 * math.sin(p) + 0.25 * math.sin(2.3 * p + 1.7))
            y = env[i, j] + 0.02 + fold + noise[i, j] * t + 0.035 * t ** 1.5      # hem swings a little away from the legs
            if i == 0:
                y -= 0.03                                     # tuck the top edge under the hood
            x = cxb + u * hw(t) + 0.25 * A * math.cos(p)
            z = zs[i] - (0.03 * (1 - u * u) + 0.012 * math.sin(p)) * t ** 3
            verts.append((x, y, z))
            uvs.append(((u + 1) / 2, 1 - t))
    for i in range(rows - 1):
        for j in range(cols - 1):
            faces.append((i * cols + j, i * cols + j + 1, (i + 1) * cols + j + 1, (i + 1) * cols + j))
    cm = bpy.data.meshes.new("cape")
    cm.from_pydata(verts, [], faces)
    uvl = cm.uv_layers.new(name="UVMap")
    for poly in cm.polygons:
        for li in poly.loop_indices:
            uvl.data[li].uv = uvs[cm.loops[li].vertex_index]
    cape = bpy.data.objects.new("cape", cm)
    bpy.context.collection.objects.link(cape)
    cm.materials.append(mat("cape", tex, double=True))
    for p in cm.polygons:
        p.use_smooth = True
    print("[v2] cape", len(faces), "quads, body centre x", round(cxb, 3), "top z", round(zt, 3), "bottom", zb)

    # 4. join, normalise size / position (same as cleanup.py)
    bpy.ops.object.select_all(action="DESELECT")
    cape.select_set(True); o.select_set(True)
    bpy.context.view_layer.objects.active = o
    # uv layer names must match to join cleanly
    cm.uv_layers[0].name = o.data.uv_layers[0].name
    bpy.ops.object.join()
    o = bpy.context.view_layer.objects.active
    finish(o)


def finish(o):
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    h = max(v.z for v in bb) - min(v.z for v in bb)
    o.scale = (HEIGHT / h,) * 3
    bpy.ops.object.transform_apply(scale=True)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    o.location = (-(min(v.x for v in bb) + max(v.x for v in bb)) / 2, -(min(v.y for v in bb) + max(v.y for v in bb)) / 2, -min(v.z for v in bb))
    bpy.ops.object.transform_apply(location=True)
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_image_format="JPEG")
    tris = sum(len(p.vertices) - 2 for p in o.data.polygons)
    bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    print("[v2] wrote", dst, tris, "tris; bbox", tuple(round(min(v[i] for v in bb), 3) for i in range(3)), tuple(round(max(v[i] for v in bb), 3) for i in range(3)))


def face():
    o = load(src)
    me = o.data
    V = [o.matrix_world @ v.co for v in me.vertices]
    top = max(v.z for v in V)
    head = [v for v in V if v.z > top - 0.26]
    cx = sum(v.x for v in head) / len(head)
    cz = top - 0.13
    m = mat("face", tex)
    me.materials.append(m)
    mi = len(me.materials) - 1
    uvl = me.uv_layers.active.data
    nsel = 0
    for p in me.polygons:
        c = p.center
        if c.z > top - 0.30 and p.normal.y < -0.45 and abs(c.x - cx) < WIN / 2 - 0.005 and c.z - cz < WIN / 2 - 0.005:
            p.material_index = mi
            nsel += 1
            for li in p.loop_indices:
                co = me.vertices[me.loops[li].vertex_index].co
                uvl[li].uv = ((co.x - cx) / WIN + 0.5, (co.z - cz) / WIN + 0.5)
    print("[v2] face faces", nsel, "window", round(cx, 4), round(cz, 4))
    bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_image_format="JPEG")
    print("[v2] wrote", dst)


geo() if stage == "geo" else face()
