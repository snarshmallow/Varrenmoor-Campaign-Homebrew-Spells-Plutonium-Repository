"""Run a generator inside Blender and export a Foundry-ready GLB.

Usage (from make.ps1):
  blender --background --factory-startup --python blender/run.py -- <generator.py> <out.glb>

Conventions for 3D Canvas: 1 Blender unit = 1 metre (1 Foundry grid square = 5 ft = 1.524 m),
model sits on Z=0 with its footprint centred on the origin, glTF Y-up is handled by the exporter.
"""
import importlib.util
import math
import sys
from pathlib import Path

import bpy
import bmesh

GRID = 1.524  # metres per 5 ft square


# ---------------------------------------------------------------- helpers ---
class Kit:
    """Small toolbox handed to every generator's build(kit)."""

    grid = GRID

    def __init__(self, seed=0):
        import random
        self.rng = random.Random(seed)
        self._mats = {}

    def mat(self, name, color, roughness=0.8, metallic=0.0, emission=None):
        if name in self._mats:
            return self._mats[name]
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        r, g, b = color
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission:
            sock = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
            sock.default_value = (*emission, 1.0)
            bsdf.inputs["Emission Strength"].default_value = 2.0
        self._mats[name] = m
        return m

    def _finish(self, obj, name, material, bevel):
        obj.name = name or obj.name
        if material is not None:
            obj.data.materials.append(material)
        if bevel:
            mod = obj.modifiers.new("bevel", "BEVEL")
            mod.width = bevel
            mod.segments = 2
            mod.limit_method = "ANGLE"
        return obj

    def box(self, size, loc=(0, 0, 0), rot=(0, 0, 0), material=None, name=None, bevel=0.0):
        """size=(x,y,z) in metres; loc is the box CENTRE."""
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=[math.radians(a) for a in rot])
        obj = bpy.context.active_object
        obj.scale = size
        bpy.ops.object.transform_apply(scale=True)
        return self._finish(obj, name, material, bevel)

    def cylinder(self, radius, depth, loc=(0, 0, 0), rot=(0, 0, 0), material=None, name=None, verts=16, bevel=0.0):
        bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth, location=loc,
                                            rotation=[math.radians(a) for a in rot])
        return self._finish(bpy.context.active_object, name, material, bevel)

    def cone(self, r1, r2, depth, loc=(0, 0, 0), rot=(0, 0, 0), material=None, name=None, verts=16):
        bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=loc,
                                        rotation=[math.radians(a) for a in rot])
        return self._finish(bpy.context.active_object, name, material, 0)

    def sphere(self, radius, loc=(0, 0, 0), scale=(1, 1, 1), material=None, name=None, segments=16):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=max(6, segments // 2), radius=radius, location=loc)
        obj = bpy.context.active_object
        obj.scale = scale
        bpy.ops.object.transform_apply(scale=True)
        return self._finish(obj, name, material, 0)

    def cloth(self, size, loc, sag=0.15, material=None, name=None, cuts=12):
        """A draped rectangular canopy: plane subdivided and sagged in the middle."""
        bpy.ops.mesh.primitive_plane_add(size=1, location=loc)
        obj = bpy.context.active_object
        obj.scale = (size[0], size[1], 1)
        bpy.ops.object.transform_apply(scale=True)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
        hx, hy = size[0] / 2, size[1] / 2
        for v in bm.verts:
            u, w = v.co.x / hx, v.co.y / hy
            v.co.z -= sag * (1 - u * u) * (1 - w * w)
        bm.to_mesh(obj.data)
        bm.free()
        obj.modifiers.new("thick", "SOLIDIFY").thickness = 0.01
        return self._finish(obj, name, material, 0)

    def jitter(self, amount):
        return self.rng.uniform(-amount, amount)


# ----------------------------------------------------------------- export ---
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()
    for block in (bpy.data.meshes, bpy.data.materials):
        for item in list(block):
            block.remove(item)


def ground_and_centre():
    """Move everything so the footprint is centred on the origin and the lowest point is Z=0."""
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    deps = bpy.context.evaluated_depsgraph_get()
    xs, ys, zs = [], [], []
    for o in objs:
        ev = o.evaluated_get(deps)
        for v in ev.to_mesh().vertices:
            w = o.matrix_world @ v.co
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
        ev.to_mesh_clear()
    dx, dy, dz = -(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2, -min(zs)
    for o in objs:
        if o.parent is None:
            o.location.x += dx; o.location.y += dy; o.location.z += dz
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))


def export_glb(out_path):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(
        filepath=str(out_path),
        export_format="GLB",
        export_apply=True,       # bake modifiers (bevel, solidify)
        export_yup=True,
        use_selection=False,
        export_cameras=False,
        export_lights=False,
    )


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if len(argv) < 2:
        raise SystemExit("usage: blender -b -P run.py -- <generator.py> <out.glb> [seed]")
    gen_path, out_path = Path(argv[0]).resolve(), Path(argv[1]).resolve()
    seed = int(argv[2]) if len(argv) > 2 else 0

    spec = importlib.util.spec_from_file_location(gen_path.stem, gen_path)
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)

    clear_scene()
    gen.build(Kit(seed))
    size = ground_and_centre()
    tris = sum(len(o.data.polygons) for o in bpy.context.scene.objects if o.type == "MESH")
    export_glb(out_path)
    print(f"[foundry-3d] wrote {out_path}  size(m)={size[0]:.2f}x{size[1]:.2f}x{size[2]:.2f}  "
          f"grid={size[0]/GRID:.1f}x{size[1]/GRID:.1f} squares  faces(pre-modifier)={tris}")


if __name__ == "__main__":
    main()
