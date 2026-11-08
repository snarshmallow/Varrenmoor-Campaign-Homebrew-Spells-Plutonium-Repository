"""Import glTF/GLB files (Draco allowed) in Blender and dump per-material geometry to .npz for illustrator/generators/foliage_import.py.
  blender -b --factory-startup --python foundry-3d/blender/dump_gltf_npz.py -- <out_dir> <file.gltf> [<file2.gltf> ...]
npz keys: for every material index i: V<i> (n,3 metres, Blender z-up), UV<i> (n,2 glTF top-down), F<i> (m,3), N<i> normals, plus names (material names) and stats.
Vertices are de-indexed per loop-triangle and merged back per unique (pos, uv, normal)."""
import os
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
out, files = a[0], a[1:]
os.makedirs(out, exist_ok=True)
for f in files:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=f)
    bpy.context.view_layer.update()
    data = {}
    mats = []
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        me = o.data
        me.calc_loop_triangles()
        uvl = me.uv_layers.active
        M = np.array(o.matrix_world)
        for k, ms in enumerate(me.materials):
            name = ms.name if ms else f"mat{k}"
            if name not in mats:
                mats.append(name)
            i = mats.index(name)
            tris = [t for t in me.loop_triangles if t.material_index == k]
            V, UV, N, F = [], [], [], []
            for t in tris:
                ids = []
                for li, vi in zip(t.loops, t.vertices):
                    p = np.array(me.vertices[vi].co)
                    p = (M @ np.append(p, 1.0))[:3]
                    uv = uvl.data[li].uv if uvl else (0, 0)
                    nrm = np.array(t.split_normals[list(t.loops).index(li)]) if hasattr(t, "split_normals") else np.array(me.vertices[vi].normal)
                    V.append(p)
                    UV.append((uv[0], 1.0 - uv[1]))
                    N.append(nrm)
                    ids.append(len(V) - 1)
                F.append(ids)
            if V:
                V, UV, N, F = np.array(V), np.array(UV), np.array(N), np.array(F)
                key = np.round(np.hstack([V, UV, N]), 5)
                _, idx, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
                inv = inv.reshape(-1)
                data[f"V{i}"], data[f"UV{i}"], data[f"N{i}"] = V[idx], UV[idx], N[idx]
                data[f"F{i}"] = inv[F]
    name = os.path.splitext(os.path.basename(f))[0]
    np.savez(os.path.join(out, name + ".npz"), names=np.array(mats), **data)
    print("dumped", name, mats, {k: v.shape for k, v in data.items() if k[0] in "VF"})
