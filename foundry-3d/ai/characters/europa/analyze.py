"""Diagnostics for build_v2: per-face colour/position stats of the v1 model to find the SF3D cape sheet and the head pose.
Usage: blender -b --factory-startup --python analyze.py -- <in.glb>
"""
import sys

import bpy
import numpy as np

src = sys.argv[sys.argv.index("--") + 1:][0]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
o = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
me = o.data
mw = o.matrix_world
img = [n.image for m in me.materials for n in m.node_tree.nodes if n.type == "TEX_IMAGE" and n.outputs[0].links and
       any(l.to_socket.name == "Base Color" for l in n.outputs[0].links)][0]
W, H = img.size
px = np.empty(W * H * 4, np.float32); img.pixels.foreach_get(px); px = px.reshape(H, W, 4)
uvl = me.uv_layers.active.data
P, C, N = [], [], []
for p in me.polygons:
    uv = np.mean([uvl[i].uv[:] for i in p.loop_indices], axis=0)
    c = px[min(H - 1, int(uv[1] * H)), min(W - 1, int(uv[0] * W)), :3]
    P.append(mw @ p.center); C.append(c); N.append((mw.to_3x3() @ p.normal).normalized())
P = np.array([list(v) for v in P]); C = np.array(C); N = np.array([list(v) for v in N])
print("faces", len(P), "bbox", P.min(0).round(3), P.max(0).round(3))
for z0 in np.arange(0.2, 1.7, 0.1):
    s = (P[:, 2] >= z0) & (P[:, 2] < z0 + 0.1)
    xs = P[s, 0]
    print(f"z {z0:.1f}: x {xs.min():.3f}..{xs.max():.3f}  y {P[s,1].min():.3f}..{P[s,1].max():.3f}  n={s.sum()}")
gr = (C[:, 1] > C[:, 0] * 1.08) & (C[:, 1] >= C[:, 2] * 0.9)
for xb in np.arange(0.1, 0.46, 0.04):
    s = (P[:, 0] >= xb) & (P[:, 0] < xb + 0.04) & (P[:, 2] > 0.3) & (P[:, 2] < 1.4)
    print(f"x {xb:.2f}: faces {s.sum()} green {(s & gr).sum()} y {P[s,1].min() if s.any() else 0:.3f}..{P[s,1].max() if s.any() else 0:.3f}")
top = P[:, 2].max()
f = (P[:, 2] > top - 0.25) & (N[:, 1] < -0.6)
print("head-front faces", f.sum(), "mean normal", N[f].mean(0).round(3), "centre", P[f].mean(0).round(3))
hd = P[:, 2] > top - 0.28
print("head verts centre", P[hd].mean(0).round(3), "x", P[hd, 0].min().round(3), P[hd, 0].max().round(3), "y", P[hd, 1].min().round(3), P[hd, 1].max().round(3))
for z0 in np.arange(top - 0.4, top, 0.04):
    s = (P[:, 2] >= z0) & (P[:, 2] < z0 + 0.04)
    print(f"  z {z0:.2f}: x {P[s,0].min():.3f}..{P[s,0].max():.3f} xc {P[s,0].mean():.3f} y {P[s,1].min():.3f}..{P[s,1].max():.3f}")
