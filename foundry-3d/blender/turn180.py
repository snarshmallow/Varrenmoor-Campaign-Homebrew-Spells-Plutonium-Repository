"""Turn a character GLB 180 degrees about the vertical axis (SF3D output faces +Y; tokens must face Blender -Y). Usage: blender -b --python turn180.py -- in.glb [out.glb]"""
import math, sys
import bpy
a = sys.argv[sys.argv.index("--") + 1:]
src, dst = a[0], (a[1] if len(a) > 1 and not a[1].startswith("tint=") else a[0])
tint = next((float(x[5:]) for x in a if x.startswith("tint=")), 1.0)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
roots = [o for o in bpy.context.scene.objects if o.parent is None]
for o in roots:
    o.rotation_mode = "XYZ"
    o.rotation_euler[2] += math.pi
bpy.ops.object.select_all(action="SELECT")
bpy.context.view_layer.objects.active = [o for o in bpy.context.scene.objects if o.type == "MESH"][0]
bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
if tint != 1.0:                                   # darken a washed-out texture (multiply the base colour)
    for m in bpy.data.materials:
        nt = m.node_tree
        b = nt.nodes.get("Principled BSDF")
        if not b or not b.inputs["Base Color"].links:
            continue
        src_sock = b.inputs["Base Color"].links[0].from_socket
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"; mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 1.0
        mix.inputs[7].default_value = (tint, tint, tint, 1.0)
        nt.links.new(src_sock, mix.inputs[6])
        nt.links.new(mix.outputs[2], b.inputs["Base Color"])
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_apply=True)
print("turned", dst)
