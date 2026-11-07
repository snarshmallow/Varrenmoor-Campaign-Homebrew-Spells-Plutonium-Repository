"""Load a Varrenmoor world pack into Blender as ONE scene: a Collection per layer (sub-collections per district / road class / species),
every object named by its entity id, true placement and scale (1 Blender unit = 1 m, x east, y north, z up, origin at the place SW corner).

  blender -b --factory-startup --python foundry-3d/blender/import_worldpack.py -- <pack_dir> [--blend out.blend] [--glb out.glb]
          [--layers terrain,buildings,...] [--split buildings=entity,...] [--step 1] [--no-carve] [--no-conform]

Each object origin is its pivot (horizontal bbox centre, lowest z), so object.location equals the placement the split exporter records.
Custom properties on every object: wp_id, wp_layer, wp_type, wp_subtype, wp_group, wp_district, wp_pipelineId, wp_file, wp_origin_ft,
wp_origin_m, wp_scale_m_per_ft. Edit objects freely, then run export_worldpack_split.py to write them back to GLB files.
Needs only the Python bundled with Blender + numpy; worldpack*.py are imported from illustrator/generators (no scipy/PIL).
"""
import math
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "illustrator", "generators")))
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_split as ws  # noqa: E402


def cli():
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    o = {"pack": None, "blend": None, "glb": None, "layers": None, "split": None, "step": 1, "carve": True, "conform": True}
    i = 0
    while i < len(a):
        t = a[i]
        if t in ("--blend", "--glb", "--layers", "--split", "--step"):
            o[t[2:]] = a[i + 1]
            i += 2
            continue
        if t == "--no-carve":
            o["carve"] = False
        elif t == "--no-conform":
            o["conform"] = False
        else:
            o["pack"] = t
        i += 1
    if not o["pack"]:
        raise SystemExit("usage: ... -- <pack_dir> [--blend out.blend] [--glb out.glb]")
    o["step"] = int(o["step"])
    return o


def make_material(pack, mid, cache):
    if mid in cache:
        return cache[mid]
    r = pack.materials.get(mid, {})
    m = bpy.data.materials.new(mid)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    col = r.get("mean_color") or "#a0a0a0"
    rgb = [int(col[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    bsdf.inputs["Base Color"].default_value = (*[c ** 2.2 for c in rgb], 1.0)
    bsdf.inputs["Roughness"].default_value = float(r.get("roughness", 0.9))
    tex = r.get("texture")
    if tex and os.path.exists(pack.path(tex)):
        t = m.node_tree.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(pack.path(tex), check_existing=True)
        t.extension = "EXTEND" if r.get("uv") == "unit" else "REPEAT"
        m.node_tree.links.new(t.outputs["Color"], bsdf.inputs["Base Color"])
    m.use_backface_culling = False
    m["wp_material_id"] = mid
    cache[mid] = m
    return m


def mesh_data(name, mesh, pack, cache):
    """Local-space bpy mesh from a worldpack Mesh (already localised)."""
    mids = sorted(mesh.subs)
    F = np.concatenate([mesh.subs[k] for k in mids]) if mids else np.zeros((0, 3), int)
    mi = np.concatenate([np.full(len(mesh.subs[k]), i, np.int32) for i, k in enumerate(mids)]) if mids else np.zeros(0, np.int32)
    me = bpy.data.meshes.new(name)
    me.from_pydata(mesh.V.tolist(), [], F.tolist())
    me.update()
    for k in mids:
        me.materials.append(make_material(pack, k, cache))
    me.polygons.foreach_set("material_index", mi)
    uv = me.uv_layers.new(name="UVMap")
    vi = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", vi)
    u = mesh.UV[vi].copy()
    u[:, 1] = 1.0 - u[:, 1]                       # glTF v runs down, Blender v runs up
    uv.data.foreach_set("uv", u.reshape(-1))
    me.polygons.foreach_set("use_smooth", np.full(len(me.polygons), bool(mesh.smooth)))
    return me


def set_props(obj, part, pack, file_of, origin_m):
    t = part["tags"]
    x, y, z = pack.frame.from_blender(*origin_m)
    obj["wp_id"], obj["wp_layer"], obj["wp_type"] = part["id"], part["layer"], part["type"]
    obj["wp_subtype"], obj["wp_group"], obj["wp_district"] = t.get("subtype") or "", t.get("group") or "", t.get("district") or ""
    obj["wp_pipelineId"] = (part.get("foundry") or {}).get("pipelineId", "")
    obj["wp_file"] = file_of.get(part["id"], "")
    obj["wp_origin_ft"] = [x, y, z]
    obj["wp_origin_m"] = list(origin_m)
    obj["wp_scale_m_per_ft"] = wp.FT_M
    obj["wp_pack"] = pack.root


def build_scene(o):
    pack = wp.load_pack(o["pack"])
    pp = os.path.join(o["pack"], "placements.json")
    split = ws.parse_split(o["split"]) if o["split"] else (wp._jload(pp)["split"] if os.path.exists(pp) else ws.parse_split())
    layers = set(o["layers"].split(",")) if o["layers"] else None
    parts = wm.build_parts(pack, step=o["step"], carve=o["carve"], conform=o["conform"], layers=layers)
    file_of = {p["id"]: ws.file_for(p, split) or "" for p in parts}
    sc = bpy.context.scene
    sc.unit_settings.system, sc.unit_settings.scale_length, sc.unit_settings.length_unit = "METRIC", 1.0, "METERS"
    for k, v in (("wp_place", pack.place), ("wp_z_origin_ft", pack.frame.z_origin_ft), ("wp_width_ft", pack.frame.width_ft), ("wp_height_ft", pack.frame.height_ft),
                 ("wp_px_per_ft", pack.frame.px_per_ft), ("wp_axes", "x east, y north, z up, metres; origin = south-west corner at z_origin_ft"), ("wp_pack", pack.root)):
        sc[k] = v
    root = bpy.data.collections.new(pack.place)
    sc.collection.children.link(root)
    colls = {}

    def coll(*path):
        parent = root
        for i in range(len(path)):
            key = path[:i + 1]
            if key not in colls:
                c = bpy.data.collections.new("/".join(key))
                parent.children.link(c)
                colls[key] = c
            parent = colls[key]
        return parent
    cache, tmpl, n = {}, {}, 0
    for p in parts:
        t = p["tags"]
        sub = {"buildings": t.get("district") or "none", "roads": t.get("subtype"), "foliage": (p["instance"] or {}).get("template") if p["instance"] else None}.get(p["layer"])
        c = coll(p["layer"], sub) if sub else coll(p["layer"])
        if p["layer"] == "lights":
            ld = bpy.data.lights.new(p["id"], "POINT")
            ld.energy = float(p["entity"].get("config", {}).get("energy_w", 500.0))
            obj = bpy.data.objects.new(p["id"], ld)
            obj.location = p["pivot"]
        elif p["instance"]:
            i = p["instance"]
            if i["template"] not in tmpl:
                tmpl[i["template"]] = mesh_data("tmpl_" + i["template"], i["mesh"], pack, cache)
            obj = bpy.data.objects.new(p["id"], tmpl[i["template"]])
            obj.location = p["pivot"]
            obj.scale = (i["scale"],) * 3
            obj.rotation_euler = (0, 0, math.radians(i["rot_deg"]))
        else:
            piv = p["pivot"]
            local = p["mesh"].translated([-piv[0], -piv[1], -piv[2]])
            obj = bpy.data.objects.new(p["id"], mesh_data(p["id"], local, pack, cache))
            obj.location = piv
        set_props(obj, p, pack, file_of, tuple(p["pivot"]))
        c.objects.link(obj)
        n += 1
    return pack, parts, n


def main():
    o = cli()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    pack, parts, n = build_scene(o)
    tris = sum((p["mesh"].tri_count if p["mesh"] else 0) for p in parts)
    print(f"worldpack: {pack.place}: {n} objects, {tris} triangles, {len(bpy.data.collections)} collections")
    if o["blend"]:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(o["blend"]))
        print("saved", o["blend"])
    if o["glb"]:
        bpy.ops.export_scene.gltf(filepath=os.path.abspath(o["glb"]), export_format="GLB", export_apply=True, export_extras=True)
        print("exported", o["glb"], os.path.getsize(o["glb"]), "bytes")


main()
