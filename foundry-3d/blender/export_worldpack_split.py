"""Write edited world-pack objects from the open .blend back to their placement GLBs (same file names, ids and pivots: idempotent).

  blender -b scene.blend --factory-startup --python foundry-3d/blender/export_worldpack_split.py -- <pack_dir> [--ids a,b] [--layers buildings]

Objects made by import_worldpack.py carry wp_file (the model file they belong to). The pivot comes from the entry recorded in placements.json.
All objects sharing one wp_file are written into that GLB as separate nodes named by entity id, localised to the entry pivot, so a model you
edited (or swapped) stays exactly where placements.json puts it. placements.json keeps the entry id/pipelineId and pivot and is updated only
for size, triangle count, bytes and sha256. Materials named like the pack ones (mat_*) keep their textures; others export their base colour.
"""
import os
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "illustrator", "generators")))
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402


def mesh_of(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(dg)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    M = np.array(obj.matrix_world)
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3) @ M[:3, :3].T + M[:3, 3]
    uv = np.zeros((len(me.loops), 2))
    if me.uv_layers.active:
        buf = np.empty(len(me.loops) * 2)
        me.uv_layers.active.data.foreach_get("uv", buf)
        uv = buf.reshape(-1, 2)
        uv[:, 1] = 1.0 - uv[:, 1]
    lv = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", lv)
    V, UV, subs, off = [], [], {}, 0
    names = [s.material.name if s.material else "mat_unassigned" for s in obj.material_slots] or ["mat_unassigned"]
    for tri in me.loop_triangles:
        for l in tri.loops:
            V.append(co[lv[l]])
            UV.append(uv[l])
        subs.setdefault(names[min(tri.material_index, len(names) - 1)], []).append((off, off + 1, off + 2))
        off += 3
    ev.to_mesh_clear()
    return wm.Mesh(np.array(V).reshape(-1, 3), np.array(UV).reshape(-1, 2), subs, "mat_terrain_albedo" in subs)


def main():
    a = sys.argv[sys.argv.index("--") + 1:]
    pack_dir = a[0]
    ids = set(a[a.index("--ids") + 1].split(",")) if "--ids" in a else None
    layers = set(a[a.index("--layers") + 1].split(",")) if "--layers" in a else None
    pack = wp.load_pack(pack_dir)
    pp = os.path.join(pack_dir, "placements.json")
    doc = wp._jload(pp)
    entries = {e["file"]: e for e in doc["files"]}
    by_file = {}
    for obj in bpy.data.objects:
        f = obj.get("wp_file")
        if not f or obj.type != "MESH":
            continue
        if (ids and obj["wp_id"] not in ids) or (layers and obj["wp_layer"] not in layers):
            continue
        by_file.setdefault("models/" + f, []).append(obj)
    done = 0
    fr = pack.frame
    for key, objs in sorted(by_file.items()):
        e = entries.get(key)
        if not e or e["kind"] != "mesh":
            continue
        pv = np.array(e["pivot"]["blender_m"])
        nodes = []
        for obj in sorted(objs, key=lambda o: o["wp_id"]):
            nodes.append((obj["wp_id"], mesh_of(obj).translated(-pv), {"id": obj["wp_id"], "layer": obj["wp_layer"], "group": obj["wp_group"]}))
        full = os.path.join(pack_dir, key)
        rel = key[len("models/"):]
        mats = dict(pack.materials)
        for _, m, _ in nodes:
            for mid in m.subs:
                if mid not in mats and mid in bpy.data.materials:
                    c = bpy.data.materials[mid].diffuse_color
                    mats[mid] = {"id": mid, "mean_color": "#%02x%02x%02x" % tuple(int(max(0, min(1, v)) * 255) for v in c[:3]), "texture": None}
        wm.write_glb(full, nodes, mats, textures=doc.get("textures", "external"), tex_root=os.path.join(pack_dir, "models", "textures"),
                     tex_prefix="../" * rel.count("/") + "textures/")
        vs = [m.V for _, m, _ in nodes if len(m.V)]
        lo, hi = np.min([v.min(0) for v in vs], 0), np.max([v.max(0) for v in vs], 0)
        size_m = hi - lo
        e["size_m"] = [round(float(v), 4) for v in size_m]
        e["size_ft"] = [round(float(v) / wp.FT_M, 3) for v in size_m]
        e["tile"].update(width=round(e["size_ft"][0] * fr.px_per_ft, 2), height=round(e["size_ft"][1] * fr.px_per_ft, 2), depth=round(e["size_ft"][2] * fr.px_per_ft, 2))
        e["tris"] = int(sum(m.tri_count for _, m, _ in nodes))
        e["bytes"], e["sha256"] = os.path.getsize(full), wp._sha(full)
        done += 1
        print("exported", key, e["tris"], "tris")
    wp._jdump(pp, doc)
    print(f"export_worldpack_split: {done} model files updated")


main()
