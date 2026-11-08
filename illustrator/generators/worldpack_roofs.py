"""Roof modes of the world pack (toggle-able roofs in Foundry 3D Canvas).

  none          roofs stay merged into each building mesh (default, cheapest; nothing to toggle)
  per_building  every building's roof is its own model tile `models/roofs/<building>_roof.glb` (layer "roofs"), flagged flags.varrenmoor.roof so the
                roof-toggle macro (foundry_macros/roofs_toggle.js) can hide one roof at a time. The building tile keeps walls, storeys, interior, doors.
  per_scene     all roofs of the scene merged into ONE mesh/tile `models/roofs.glb` (chunked per district into roofs/<district>.glb only when the
                total exceeds CHUNK_TRIS triangles). One tile.hidden toggle shows/hides every roof. Buildings are exported without roofs.

Hiding a roof is a plain Foundry tile `hidden` toggle (persistent, every client, no module code): see foundry_push.py install-roof-macros.
The split rule matches worldpack_interiors.add_interior: a face is "roof" when it uses the roof material or rises above the wall top (gables,
chimneys, towers above the eaves, roof trim). Buildings with an interior layout already carry a `<id>_roof` node (roof + top ceiling plate + beams);
that node becomes the roof part, so the cut-away building shows its open top storey.
"""
import numpy as np

import worldpack_mesh as wm

ROOF_MODES = ("none", "per_building", "per_scene")
DEFAULT_MODE = "none"
CHUNK_TRIS = 300_000          # per_scene: split into per-district tiles above this many roof triangles
FT = wm.FT


def check_mode(mode):
    mode = mode or DEFAULT_MODE
    if mode not in ROOF_MODES:
        raise ValueError(f"roof mode must be one of {ROOF_MODES}, got {mode!r}")
    return mode


def compact(mesh):
    """Mesh with only the vertices its faces use (bbox / pivot / file size then describe just those faces)."""
    if not mesh.tri_count:
        return mesh
    used = np.unique(np.concatenate([f.ravel() for f in mesh.subs.values()]))
    if len(used) == len(mesh.V):
        return mesh
    remap = np.full(len(mesh.V), -1, np.int64)
    remap[used] = np.arange(len(used))
    return wm.Mesh(mesh.V[used], mesh.UV[used], {k: remap[f] for k, f in mesh.subs.items()}, mesh.smooth,
                   None if mesh.N is None else mesh.N[used], None if mesh.C is None else mesh.C[used])


def split_mesh(mesh, roof_mat, zt):
    """-> (body, roof) meshes (compacted). roof = faces of the roof material or with any vertex above the wall top zt (Blender m)."""
    body, roof = {}, {}
    for k, F in mesh.subs.items():
        zmax = mesh.V[F][:, :, 2].max(axis=1) if len(F) else np.zeros(0)
        isr = np.full(len(F), k == roof_mat) | (zmax > zt + 1e-6)
        if isr.any():
            roof[k] = F[isr]
        if (~isr).any():
            body[k] = F[~isr]
    mk = lambda s: compact(wm.Mesh(mesh.V, mesh.UV, s, mesh.smooth, mesh.N, mesh.C))
    return mk(body), mk(roof)


def separate(cx, e, mesh, extra):
    """Take the roof out of a building. -> (body mesh, extra with the roof node removed, roof mesh or None).
    extra: the add_interior fields ({layered_nodes, interior_lights}) or {}."""
    rid = f"{e['id']}_roof"
    nodes = extra.get("layered_nodes")
    if nodes:
        rn = [n for n in nodes if n[0] == rid]
        if not rn:
            return mesh, extra, None
        rest = [(n, compact(m), x) for n, m, x in nodes if n != rid]        # add_interior nodes share the whole building's vertex array: compact so bbox / pivot / file size are per node
        body = wm.merge_meshes([m for _, m, _ in rest]) if rest else mesh
        return body, {**extra, "layered_nodes": rest}, compact(rn[0][1])
    zt = (e["base_elevation_ft"] - cx.fr.z_origin_ft + e["wall_height_ft"]) * FT
    body, roof = split_mesh(mesh, e["roof"]["surface"]["material"], zt)
    return body, extra, (roof if roof.tri_count else None)


def roof_part(e, mesh, ptype="roof", pid=None, members=None, tags=None):
    pid = pid or f"{e['id']}_roof"
    t = dict(tags or e.get("tags") or {})
    t.update({"layer": "roofs", "subtype": ptype, "id": pid, "building": e["id"]})
    t.setdefault("district", None)
    t.setdefault("ring", None)
    t["group"] = "roofs"
    return {"id": pid, "layer": "roofs", "type": "roofs", "group": "roofs", "tags": t, "mesh": mesh, "pivot": wm._pivot(mesh), "members": members or [pid],
            "instance": None, "foundry": {"pipelineId": f"world:roof:{pid}"}, "entity": {"id": pid, "kind": "roof", "building": e["id"], "tags": t},
            "roof": {"building": e["id"]}}


def _chunk_key(e):
    d = (e.get("tags") or {}).get("district")
    return str(d) if d else "all"


def make_parts(roofs, mode):
    """roofs: [(building entity, absolute roof mesh)] -> Parts of layer "roofs" ("per_building": one per building; "per_scene": one merged per chunk)."""
    if not roofs:
        return []
    if mode == "per_building":
        out = []
        for e, m in roofs:
            p = roof_part(e, m, "roof")
            p["roof"] = {"mode": mode, "buildings": [e["id"]]}
            out.append(p)
        return out
    total = sum(m.tri_count for _, m in roofs)
    chunks = {}
    for e, m in roofs:
        chunks.setdefault(_chunk_key(e) if total > CHUNK_TRIS else "all", []).append((e, m))
    out = []
    for k, items in sorted(chunks.items()):
        merged = wm.merge_meshes([m for _, m in items])
        pid = "roofs" if k == "all" else f"roofs_{k}"
        p = roof_part(items[0][0], merged, "roofs", pid=pid, members=[e["id"] for e, _ in items])
        p["group"] = f"roofs:{pid}" if len(chunks) > 1 else "roofs"
        p["tags"]["group"] = p["group"]
        p["tags"]["building"] = None
        p["roof"] = {"mode": mode, "buildings": [e["id"] for e, _ in items], "chunk": None if k == "all" else k}
        out.append(p)
    return out


def split_granularity(mode):
    """DEFAULT_SPLIT entry of the "roofs" layer for a mode (per_scene chunked files are switched to "group" by split_export)."""
    return "entity" if mode == "per_building" else "layer"
