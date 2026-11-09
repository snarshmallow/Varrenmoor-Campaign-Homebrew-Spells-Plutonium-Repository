"""SF3D bakes pale, washed-out colours (her grey drow skin came out near white). Darken and re-saturate the base-colour texture
pixels in place (turn180.py's tint= adds a shader node that glTF export drops, so it has no effect on the GLB).
Usage: blender -b --factory-startup --python darken.py -- <in.glb> <out.glb> [gain=0.72] [sat=1.25] [gamma=1.0]
"""
import sys

import bpy
import numpy as np

a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], a[1]
gain = float(a[2]) if len(a) > 2 else 0.72
sat = float(a[3]) if len(a) > 3 else 1.25
gamma = float(a[4]) if len(a) > 4 else 1.0
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
done = set()
for m in bpy.data.materials:
    b = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
    if not b or not b.inputs["Base Color"].links:
        continue
    node = b.inputs["Base Color"].links[0].from_node
    if node.type != "TEX_IMAGE" or node.image.name in done:
        continue
    img = node.image
    px = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(px)
    p = px.reshape(-1, 4)
    rgb = p[:, :3]
    grey = rgb.mean(axis=1, keepdims=True)
    rgb = np.clip(grey + (rgb - grey) * sat, 0, 1) ** gamma * gain
    p[:, :3] = rgb
    img.pixels.foreach_set(p.ravel())
    import os, tempfile                      # write the edited pixels to a file and reload, or export re-uses the original bytes
    tmp = os.path.join(tempfile.gettempdir(), f"darken_{len(done)}.png")
    img.filepath_raw = tmp
    img.file_format = "PNG"
    img.save()
    img.unpack(method="REMOVE") if img.packed_file else None
    img.filepath = tmp
    img.reload()
    img.pack()
    done.add(img.name)
    print("[darken]", img.name, img.size[:], "gain", gain, "sat", sat, "gamma", gamma)
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_image_format="JPEG")
print("[darken] wrote", dst)
