"""Blender clean-up for AI meshes: import GLB, project source image as texture, decimate, base at Z=0, export.
Usage: blender --background --factory-startup --python ai/cleanup.py -- <in.glb> <image|-> <out.glb> <out.blend> [tris] [height_m]
"""
import sys
import bpy
import bmesh
from mathutils import Vector

a = sys.argv[sys.argv.index("--") + 1:]
src, image, out, blend = a[:4]
tris = int(a[4]) if len(a) > 4 else 30000
height = float(a[5]) if len(a) > 5 else 1.8

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=src)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
bpy.ops.object.select_all(action="DESELECT")
for o in meshes:
    o.select_set(True)
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
obj = bpy.context.view_layer.objects.active
bpy.ops.object.shade_smooth()

# decimate
n = sum(len(p.vertices) - 2 for p in obj.data.polygons)
if n > tris:
    m = obj.modifiers.new("dec", "DECIMATE")
    m.ratio = tris / n
    bpy.ops.object.modifier_apply(modifier=m.name)

# orient: Hunyuan is Y-up in glTF, importer converts to Z-up. Scale to target height, centre, base on Z=0.
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
dims = obj.dimensions
obj.scale = (height / dims.z,) * 3
bpy.ops.object.transform_apply(scale=True)
bb = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
cx = (min(v.x for v in bb) + max(v.x for v in bb)) / 2
cy = (min(v.y for v in bb) + max(v.y for v in bb)) / 2
obj.location = (-cx, -cy, -min(v.z for v in bb))
bpy.ops.object.transform_apply(location=True)

if image != "-":  # "-" keeps the source GLB's own texture (Stable Fast 3D)
    # front projection of the concept image (viewed along +Y from -Y), simple and untextured-back tinted
    img = bpy.data.images.load(image)
    mat = bpy.data.materials.new("ai_tex")
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 0.85
    tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = img
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    d = obj.dimensions
    w = max(d.x, 1e-6)
    mp.inputs["Scale"].default_value = (1 / w, 1, 1 / d.z)
    mp.inputs["Location"].default_value = (0.5, 0, 0)
    obj.data.materials.clear()
    obj.data.materials.append(mat)

    # bake the projection into a real UV texture so it survives GLB export
    bpy.ops.object.select_all(action="DESELECT"); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=1.1, island_margin=0.003)
    bpy.ops.object.mode_set(mode="OBJECT")
    bake = bpy.data.images.new("ai_bake", 2048, 2048)
    bn = nt.nodes.new("ShaderNodeTexImage"); bn.image = bake
    nt.nodes.active = bn
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"; sc.cycles.device = "CPU"; sc.cycles.samples = 1
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=8)
    nt.links.new(bn.outputs["Color"], bsdf.inputs["Base Color"])
    bake.pack()

bpy.ops.wm.save_as_mainfile(filepath=blend)
bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_selection=False)
print("[foundry-3d] wrote", out, sum(len(p.vertices) - 2 for p in obj.data.polygons), "tris")
