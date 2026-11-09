"""Split a world pack into placeable GLB models (with a placements manifest), re-export single models, and merge/compress them for Foundry.

  python worldpack_split.py split    --place bridgehollow [--pack DIR] [--split buildings=entity,roads=group] [--textures external|embed]
  python worldpack_split.py reexport --place bridgehollow --id bld_house_001[,bld_house_002]      # rebuild only those files, keep the rest
  python worldpack_split.py merge    --place bridgehollow --preset all|layer|district|individual [--compress none|quant|meshopt|meshopt-fallback]
  python worldpack_split.py publish  --place bridgehollow --preset layer --scene-uuid Scene.xxx [--dry-run]    # merge, then push-models

Output (inside the pack folder, default world/<place>/export/): placements.json + models/<layer>/<file>.glb + models/textures/.
Merged output goes to optimized/<preset>_vNNN/ (never over the individual sources). Format: illustrator/WORLD_PACK.md.
Pure numpy: runs without Blender. Meshes are local to a pivot (horizontal bbox centre, lowest z) so a model can be swapped without moving it.
"""
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

FT = wp.FT_M
PLACEMENTS_FORMAT = "varrenmoor-world-placements"
DEFAULT_SPLIT = {"terrain": "layer", "water": "layer", "roads": "layer", "plazas": "layer", "fields": "layer", "fences": "layer", "walls": "layer",
                 "foliage": "species", "buildings": "entity", "bridges": "entity", "lights": "none"}
SPLIT_PRESETS = {"default": {}, "layers": {k: "layer" for k in DEFAULT_SPLIT if k not in ("lights",)}, "districts": {"buildings": "group", "roads": "group", "foliage": "group"},
                 "individual": {k: "entity" for k in DEFAULT_SPLIT if k not in ("terrain", "lights")}}
GRANULARITIES = ("layer", "group", "entity", "species", "none")


def slug(t):
    return re.sub(r"[^a-z0-9_]+", "_", str(t).lower()).strip("_") or "x"


def parse_split(spec=None, preset="default", roof_mode="none"):
    sp = dict(DEFAULT_SPLIT)
    sp.update(SPLIT_PRESETS[preset])
    if roof_mode != "none":                                   # roofs are their own layer (worldpack_roofs.py): per building = one tile each, per scene = one merged tile
        import worldpack_roofs as wr
        sp["roofs"] = wr.split_granularity(roof_mode)
    for tok in (spec or "").split(","):
        if tok.strip():
            k, v = tok.split("=")
            if v not in GRANULARITIES:
                raise SystemExit(f"split granularity must be one of {GRANULARITIES}")
            sp[k.strip()] = v.strip()
    return sp


def file_for(part, split):
    """Relative GLB path (inside models/) a part is written to under `split`, or None (not a model: lights)."""
    g = split.get(part["layer"], "layer")
    l = part["layer"]
    if g == "none":
        return None
    if g == "layer":
        return f"{l}.glb"
    if g == "group":
        return f"{l}/{slug(part['group'].split(':', 1)[-1])}.glb"
    if g == "species" and part["instance"]:
        return f"{l}/{slug(part['instance']['template'])}.glb"
    return f"{l}/{part['id']}.glb"


def assign_files(parts, split):
    out = {}
    for p in parts:
        f = file_for(p, split)
        if f:
            out.setdefault(f, []).append(p)
    return dict(sorted(out.items()))


def _sha(path):
    return wp._sha(path)


def _px(fr, x_ft, y_ft):
    return [round(v, 3) for v in fr.to_foundry_px(x_ft, y_ft)]


def _entry(pack, rel, parts, textures, out, tex_mode):
    """Write one GLB and return its placements entry."""
    fr = pack.frame
    inst = parts[0]["instance"]
    if inst:                                                   # one template GLB + many instances
        tm = inst["mesh"]
        pivot = (0.0, 0.0, 0.0)
        nodes = [(slug(inst["template"]), tm, {"id": slug(inst["template"]), "layer": "foliage"})]
        lo, hi = tm.bbox()
        centre = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        nodes[0] = (nodes[0][0], tm.translated([-centre[0], -centre[1], -centre[2]]), nodes[0][2])
        size_m = [float(v) for v in (hi - lo)]
    else:
        absm = [wm.part_mesh(p) for p in parts]
        merged = wm.merge_meshes(absm)
        pivot = wm._pivot(merged)
        nodes = []
        for p, m in zip(parts, absm):
            if p.get("layered_nodes"):                           # building with interior: storeys / roof / props as separate nodes (worldpack_interiors)
                nodes += [(nm, mm.translated([-pivot[0], -pivot[1], -pivot[2]]), {"id": p["id"], "layer": p["layer"], "group": p["group"], **xx}) for nm, mm, xx in p["layered_nodes"]]
            else:
                rx = {"isRoof": True, "roofMode": p["roof"]["mode"], "roofOf": p["roof"]["buildings"][:200]} if p.get("roof") else {}
                nodes.append((p["id"], m.translated([-pivot[0], -pivot[1], -pivot[2]]), {"id": p["id"], "layer": p["layer"], "group": p["group"], **rx, **(p.get("extras") or {})}))
        lo, hi = merged.bbox()
        size_m = [float(v) for v in (hi - lo)]
        for p in parts:                                          # movable door leaves: own glTF nodes, origin on the hinge
            for dn in p.get("door_nodes", []):
                hx, hy, hz = dn["hinge"]
                nodes.append((dn["id"], dn["mesh"], {**dn["extras"], "_t": (hx - pivot[0], hy - pivot[1], hz - pivot[2])}))
    full = os.path.join(out, "models", rel)
    depth = rel.count("/")
    wm.write_glb(full, nodes, pack.materials, textures=tex_mode, tex_root=os.path.join(out, "models", "textures"), tex_prefix="../" * depth + "textures/")
    for nm, m, _ in nodes:
        for mid in m.subs:
            textures.add(mid)
    pf = fr.from_blender(*pivot)
    size_ft = [round(v / FT, 3) for v in size_m]
    pid = f"model:{pack.place}:{slug(rel[:-4])}"
    tags_layers = sorted({p["layer"] for p in parts})
    e = {"id": pid, "file": f"models/{rel}", "kind": "instances" if inst else "mesh", "layer": parts[0]["layer"], "layers": tags_layers,
         "group": parts[0]["group"] if len({p["group"] for p in parts}) == 1 else None, "ids": [p["id"] for p in parts],
         "pivot": {"x_ft": round(pf[0], 3), "y_ft": round(pf[1], 3), "z_ft": round(pf[2], 3), "blender_m": [round(v, 4) for v in pivot],
                   "foundry_px": _px(fr, pf[0], pf[1]), "rel_z_ft": round(pivot[2] / FT, 3)},
         "rotation_deg": 0.0, "scale": 1.0, "size_m": [round(v, 4) for v in size_m], "size_ft": size_ft,
         "tile": {"x": _px(fr, pf[0], pf[1])[0], "y": _px(fr, pf[0], pf[1])[1], "width": round(size_ft[0] * fr.px_per_ft, 2), "height": round(size_ft[1] * fr.px_per_ft, 2),
                  "depth": round(size_ft[2] * fr.px_per_ft, 2), "elevation_ft": round(pivot[2] / FT, 3), "rotation": pack.manifest["foundry"]["tile_rotation_deg"]},
         "tris": int(sum(m.tri_count for _, m, _ in nodes)), "bytes": os.path.getsize(full), "sha256": _sha(full)}
    if any(p.get("roof") for p in parts):                         # roof tile(s): the roof-toggle macro finds them through flags.varrenmoor.roof (foundry_push.build_model_tiles)
        e["roof"] = {"mode": parts[0]["roof"]["mode"], "buildings": [b for p in parts for b in p["roof"]["buildings"]], "chunk": parts[0]["roof"].get("chunk")}
    lts = [dict(lt, foundry_px=_px(fr, lt["point"][0], lt["point"][1])) for p in parts for lt in p.get("interior_lights", [])]
    if lts:                                                      # interior light hints (hearths, window light): Foundry light docs are built from these
        e["lights"] = lts
    if inst:
        e["instances"] = [{"id": p["id"], "pivot_ft": [round(v, 3) for v in fr.from_blender(*p["pivot"])], "rotation_deg": p["instance"]["rot_deg"],
                           "scale": round(p["instance"]["scale"], 4), "tile_xy": _px(fr, *fr.from_blender(p["pivot"][0], p["pivot"][1]))} for p in parts]
        e["tris"] *= len(parts)
    else:
        e["members"] = [{"id": p["id"], "layer": p["layer"], "tags": p["tags"], "offset_m": [round(v, 4) for v in (np.array(p["pivot"]) - np.array(pivot))]} for p in parts]
    return e


def split_export(pack_dir, out_dir=None, split=None, textures="external", step=1, carve=True, conform=True, only=None, log=print, road_grade=True, roof_mode=None):
    """Write per-model GLBs and placements.json. `only`: ids -> rebuild just the files containing them and keep every other entry.
    roof_mode none|per_building|per_scene (worldpack_roofs.py); None = keep the mode of the existing placements.json (reexport) else none."""
    import worldpack_roofs as wr
    pack = wp.load_pack(pack_dir)
    out = out_dir or pack_dir
    pp0 = os.path.join(out, "placements.json")
    if roof_mode is None:
        roof_mode = (wp._jload(pp0).get("roof_mode") if only and os.path.exists(pp0) else None) or pack.manifest.get("foundry", {}).get("roof_mode") or "none"
    roof_mode = wr.check_mode(roof_mode)
    split = dict(split or DEFAULT_SPLIT)
    if roof_mode != "none":
        split.setdefault("roofs", wr.split_granularity(roof_mode))
    else:
        split.pop("roofs", None)
    parts = wm.build_parts(pack, step=step, carve=carve, conform=conform, road_grade=road_grade, roof_mode=roof_mode)
    if roof_mode == "per_scene" and split.get("roofs") == "layer" and sum(1 for p in parts if p["layer"] == "roofs") > 1:
        split["roofs"] = "group"                                  # chunked per district (too many roof triangles for one tile)
    rg_report = dict(wm.LAST_ROAD_GRADE)
    for w_ in rg_report.get("warnings", []):
        log("road grade warning: " + w_)
    files = assign_files(parts, split)
    old = {}
    pp = os.path.join(out, "placements.json")
    if only and os.path.exists(pp):
        old = {e["file"]: e for e in wp._jload(pp)["files"]}
    ids = set(only or [])
    tex = wp.Textures(out)
    entries = {}
    if textures == "external":
        shutil.rmtree(os.path.join(out, "models", "textures"), ignore_errors=True) if not only else None
        os.makedirs(os.path.join(out, "models", "textures"), exist_ok=True)
        for mid, r in pack.materials.items():                                  # copy every pack texture next to the models once
            if r.get("texture") and os.path.exists(pack.path(r["texture"])):
                shutil.copyfile(pack.path(r["texture"]), os.path.join(out, "models", "textures", mid + ".png"))
        import worldpack_pbr as pbr
        pbr.install(pack, os.path.join(out, "models", "textures"))         # normal / metallicRoughness maps, new surfaces, detailed terrain albedo
    if not only:                                                  # a mode change must not leave the old roof files behind
        shutil.rmtree(os.path.join(out, "models", "roofs"), ignore_errors=True)
        if os.path.exists(os.path.join(out, "models", "roofs.glb")):
            os.remove(os.path.join(out, "models", "roofs.glb"))
    for rel, ps in files.items():
        key = f"models/{rel}"
        if only and not (ids & ({p["id"] for p in ps} | {b for p in ps for b in (p.get("roof") or {}).get("buildings", [])})):
            if key in old:
                entries[key] = old[key]
                continue
        entries[key] = _entry(pack, rel, ps, tex, out, textures)
    doc = {"format": PLACEMENTS_FORMAT, "schema_version": "1.0", "place": pack.place, "pack": {"dir": os.path.relpath(pack_dir, out).replace("\\", "/") if out != pack_dir else ".",
                                                                                              "generated": pack.manifest["generated"]["timestamp"], "git_commit": pack.manifest["generated"].get("git_commit")},
           "frame": {"px_per_ft": pack.frame.px_per_ft, "z_origin_ft": pack.frame.z_origin_ft, "height_ft": pack.frame.height_ft, "width_ft": pack.frame.width_ft,
                     "tile_rotation_deg": pack.manifest["foundry"]["tile_rotation_deg"],
                     "note": "tile.x/y = pivot px at the pack's px_per_ft; push-models rescales to the target scene's calibration"},
           "split": split, "textures": textures, "roof_mode": roof_mode, "files": [entries[k] for k in sorted(entries)]}
    if rg_report:
        doc["road_grade"] = rg_report                              # settings, stats, warnings (grade limit unmet, road raised at bridges) and cut/fill extents
    elif only and os.path.exists(pp):
        doc["road_grade"] = wp._jload(pp).get("road_grade")
    wp._jdump(pp, doc)
    if os.path.abspath(out) == os.path.abspath(pack_dir):
        wp.set_roof_mode(pack_dir, roof_mode)
        ch, ad, dr = wp.refresh_manifest_files(pack_dir)           # split rewrote GLBs + placements.json: keep manifest.files hashes valid
        log(f"manifest.files refreshed: {ch} re-hashed, {ad} added, {dr} dropped")
    log(f"split: {len(entries)} model files, {sum(e['tris'] for e in entries.values())} triangles -> {out}")
    return doc


# ------------------------------------------------------------------ merge / compress
def _png_size(p):
    try:
        with open(p, "rb") as f:
            h = f.read(24)
        return struct.unpack(">II", h[16:24])
    except OSError:
        return (0, 0)


def _glb_json(p):
    with open(p, "rb") as f:
        raw = f.read()
    return json.loads(raw[20:20 + struct.unpack_from("<I", raw, 12)[0]])


def _stats(placements, root, tex_dir):
    files = placements["files"]
    tris = draw = nbytes = 0
    mats = set()
    for e in files:
        p = os.path.join(root, e["file"])
        nbytes += os.path.getsize(p) if os.path.exists(p) else 0
        n = len(e.get("instances", [])) or 1
        g = _glb_json(p)                       # JSON chunk only: also works for quantized / meshopt files that read_glb cannot decode
        for nd in g["nodes"]:
            if "mesh" not in nd:
                continue
            for pr in g["meshes"][nd["mesh"]]["primitives"]:
                tris += g["accessors"][pr["indices"]]["count"] // 3 * n
                draw += n
                mats.add(g["materials"][pr["material"]]["name"])
    tm = 0
    for mid in mats:
        w, h = _png_size(os.path.join(tex_dir, mid + ".png"))
        tm += w * h * 4 * 4 // 3
    return {"files": len(files), "triangles": int(tris), "draw_calls_est": int(draw), "texture_mb": round(tm / 1e6, 2), "glb_mb": round(nbytes / 1e6, 2), "materials": len(mats)}


def next_version_dir(base, name):
    n = 1
    while os.path.exists(os.path.join(base, f"{name}_v{n:03d}")):
        n += 1
    return os.path.join(base, f"{name}_v{n:03d}")


# gltfpack flags per --compress mode. -kn/-km keep node and material names (members lookup, picking); -tr keeps the shared relative
# texture URIs instead of embedding every image into every GLB; -vp 16 keeps terrain heights precise. All three modes need a glTF
# extension (quantization and/or meshopt) that the 3D Canvas module may not load: see WORLD_PACK.md, Foundry/3D Canvas compatibility.
GLTFPACK_FLAGS = {
    "quant": ["-kn", "-km", "-ke", "-tr", "-vp", "16", "-vt", "16"],                       # KHR_mesh_quantization only (+ KHR_texture_transform), no meshopt
    "meshopt": ["-cc", "-kn", "-km", "-ke", "-tr", "-vp", "16", "-vt", "16"],              # EXT_meshopt_compression required
    "meshopt-fallback": ["-cf", "-kn", "-km", "-ke", "-tr", "-vp", "16", "-vt", "16"],     # meshopt plus an uncompressed fallback buffer (larger files)
}


def merge_export(pack_dir, preset="layer", out_dir=None, lods=(1, 2), compress="none", remove_hidden=True, log=print):
    """Merge the individual models (placements.json in pack_dir) per preset into optimized/<preset>_vNNN/. Sources are read only."""
    pack = wp.load_pack(pack_dir)
    src = wp._jload(os.path.join(pack_dir, "placements.json"))
    tex_src = os.path.join(pack_dir, "models", "textures")
    out = out_dir or next_version_dir(os.path.join(pack_dir, "optimized"), preset)
    os.makedirs(out, exist_ok=True)
    before = _stats(src, pack_dir, tex_src)
    fr = pack.frame
    items = []                                              # (entry, node id, abs mesh, tags, district)
    doors = []                                              # (node id, extras, hinge-local mesh, absolute hinge (blender m), entry): never merged
    roofex = {}                                             # roof node id -> glTF extras (isRoof, roofOf ...); roof files (layer "roofs") are never merged with anything else
    for e in src["files"]:
        nodes, _ = wm.read_glb(os.path.join(pack_dir, e["file"]))
        pv = np.array(e["pivot"]["blender_m"])
        if e["kind"] == "instances":
            tm = nodes[0][2]
            for inst in e["instances"]:
                px, py, pz = fr.to_blender(inst["pivot_ft"][0], inst["pivot_ft"][1], inst["pivot_ft"][2])
                items.append((e, inst["id"], tm.transformed(inst["scale"], inst["rotation_deg"], (px, py, pz)), "foliage", None))
            continue
        mem = {m["id"]: m for m in e["members"]}
        for nid, ex, m in nodes:
            if ex.get("isDoor"):                            # door leaf: keep as its own node, hinge position = node translation + source pivot
                t = ex.get("_t") or (0.0, 0.0, 0.0)
                doors.append((nid, {k: v for k, v in ex.items() if k != "_t"}, m, np.array(t) + pv, e))
                continue
            if e["layer"] == "roofs":
                roofex[nid] = {k: v for k, v in ex.items() if k not in ("_t",)}
            tg = (mem.get(nid) or {}).get("tags", {})
            items.append((e, nid, m.translated(pv), e["layer"], tg.get("district")))
    groups, keyof = {}, {}
    for it in items:
        e = it[0]
        if preset == "individual" or it[3] == "roofs":      # roof tiles keep their own file whatever the preset: that is what the toggle hides
            k = e["file"][len("models/"):-4]
        elif preset == "all":
            k = "scene"
        elif preset == "district":
            k = f"{it[3]}__{slug(it[4] or 'none')}"
        else:
            k = it[3]
        groups.setdefault(k, []).append(it)
        keyof[it[1]] = k
    entries = []
    removed = 0
    n_doors = 0
    tex_out = os.path.join(out, "models", "textures")
    if os.path.isdir(tex_src):
        shutil.copytree(tex_src, tex_out, dirs_exist_ok=True)
    for k, its in sorted(groups.items()):
        meshes = []
        for e, nid, m, layer, dist in its:
            if remove_hidden and layer == "buildings":
                keep = {}
                for mid, F in m.subs.items():
                    c = m.V[F].mean(1)
                    zmax = m.V[F][:, :, 2].max(1)
                    x, y = fr.from_blender(c[:, 0], c[:, 1])
                    g = (wp.bilinear(pack.heights, pack.cell_ft, x, y) - fr.z_origin_ft) * FT
                    ok = zmax > g - 0.02
                    removed += int((~ok).sum())
                    keep[mid] = F[ok]
                m = wm.Mesh(m.V, m.UV, keep, m.smooth)
            meshes.append((nid, m, e, layer))
        merged = wm.merge_meshes([m for _, m, _, _ in meshes])
        pivot = wm._pivot(merged)
        rel = f"{k}.glb"
        nodes = [(k, merged.translated([-pivot[0], -pivot[1], -pivot[2]]), {"merged": [n for n, *_ in meshes]})]
        if preset == "individual" or its[0][3] == "roofs":
            nodes = [(n, m.translated([-pivot[0], -pivot[1], -pivot[2]]), {**roofex.get(n, {}), "id": n}) for n, m, _, _ in meshes]
        n_doors_k = 0
        for did, dex, dm_, dabs, _e in doors:                # door leaves stay separate nodes (hinge at node origin, extras kept) in their building's file
            if keyof.get(dex.get("building")) == k:
                nodes.append((did, dm_, {**dex, "_t": tuple(dabs - np.array(pivot))}))
                n_doors += 1
                n_doors_k += 1
        full = os.path.join(out, "models", rel)
        depth = rel.count("/")
        wm.write_glb(full, nodes, pack.materials, textures=src.get("textures", "external"), tex_root=tex_out, tex_prefix="../" * depth + "textures/")
        lo, hi = merged.bbox()
        ext = float(max(hi - lo))
        lodinfo = []
        for li in lods:
            cell = max(ext * (0.01 if li == 1 else 0.03), 0.5 if li == 1 else 1.5)
            dm = wm.cluster_decimate(merged, cell)
            lrel = f"{k}.lod{li}.glb"
            wm.write_glb(os.path.join(out, "models", lrel), [(k, dm.translated([-pivot[0], -pivot[1], -pivot[2]]), {})], pack.materials,
                         textures=src.get("textures", "external"), tex_root=tex_out, tex_prefix="../" * depth + "textures/")
            lodinfo.append({"lod": li, "file": f"models/{lrel}", "tris": dm.tri_count, "cell_m": round(cell, 3), "suggested_distance_m": [0, 150, 400][li] if li < 3 else None})
        pf = fr.from_blender(*pivot)
        sz = [float(v) for v in (hi - lo)]
        size_ft = [round(v / FT, 3) for v in sz]
        layers = sorted({l for *_, l in meshes})
        entries.append({
            "id": f"model:{pack.place}:{slug(k)}", "file": f"models/{rel}", "kind": "mesh", "layer": layers[0] if len(layers) == 1 else "mixed", "layers": layers,
            "group": k, "ids": [n for n, *_ in meshes],
            "pivot": {"x_ft": round(pf[0], 3), "y_ft": round(pf[1], 3), "z_ft": round(pf[2], 3), "blender_m": [round(v, 4) for v in pivot], "foundry_px": _px(fr, pf[0], pf[1]),
                      "rel_z_ft": round(pivot[2] / FT, 3)},
            "rotation_deg": 0.0, "scale": 1.0, "size_m": [round(v, 4) for v in sz], "size_ft": size_ft,
            "tile": {"x": _px(fr, pf[0], pf[1])[0], "y": _px(fr, pf[0], pf[1])[1], "width": round(size_ft[0] * fr.px_per_ft, 2), "height": round(size_ft[1] * fr.px_per_ft, 2),
                     "depth": round(size_ft[2] * fr.px_per_ft, 2), "elevation_ft": round(pivot[2] / FT, 3), "rotation": src["frame"]["tile_rotation_deg"]},
            **({"roof": its[0][0]["roof"]} if its[0][3] == "roofs" and its[0][0].get("roof") else {}),
            "doors": n_doors_k, "tris": merged.tri_count, "bytes": os.path.getsize(full), "sha256": _sha(full), "lods": lodinfo,
            "members": [{"id": n, "layer": l, "source_file": e["file"], "offset_m": [round(v, 4) for v in (m.V.mean(0) - np.array(pivot))] if len(m.V) else [0, 0, 0],
                         "pivot_ft": [round(v, 3) for v in fr.from_blender(*(m.V.mean(0) if len(m.V) else pivot))]} for n, m, e, l in meshes]})
    if compress != "none":
        exe = shutil.which("gltfpack")
        if not exe:
            log("compress: gltfpack is not installed; skipping (recommendation: npm i -g gltfpack, or use gltf-transform). Files are uncompressed.")
        else:
            for e in entries:
                if e.get("doors"):                      # gltfpack moves a door mesh into a child of its hinge node, so `isDoor` ends up on the parent and 3D Canvas
                    e["compression"] = "none (has doors)"      # (child.isMesh && userData.isDoor) no longer finds a door: files with doors stay uncompressed
                    continue
                p = os.path.normpath(os.path.join(out, e["file"]))      # normalised: mixed / and \ separators upset gltfpack.cmd on Windows
                tmp = p + ".tmp.glb"
                for attempt in range(3):                # the npm gltfpack sometimes dies on exit (libuv assertion, 0xC0000409) after writing a good file: retry, else accept a valid output
                    r = subprocess.run([exe, "-i", p, "-o", tmp] + GLTFPACK_FLAGS[compress], capture_output=True)    # gltfpack picks the format from the extension
                    if r.returncode == 0:
                        break
                    if os.path.exists(tmp) and os.path.getsize(tmp) > 20 and open(tmp, "rb").read(4) == b"glTF" and attempt == 2:
                        log(f"compress: gltfpack exited {r.returncode} on {e['file']} but wrote a valid file; using it")
                        break
                else:
                    raise RuntimeError(f"gltfpack failed on {e['file']} ({r.returncode}): {r.stderr[-300:].decode(errors='replace')}")
                os.replace(tmp, p)
                e["bytes"], e["sha256"], e["compression"] = os.path.getsize(p), _sha(p), compress
    doc = {**{k: v for k, v in src.items() if k != "files"}, "merge": {"preset": preset, "source": os.path.join(pack_dir, "placements.json"), "lods": list(lods), "compress": compress,
                                                                    "hidden_faces_removed": removed},
           "files": sorted(entries, key=lambda e: e["file"])}
    doc["pack"] = {**src["pack"], "dir": os.path.relpath(pack_dir, out).replace("\\", "/")}
    wp._jdump(os.path.join(out, "placements.json"), doc)
    after = _stats(doc, out, tex_out)
    rep = {"preset": preset, "before": before, "after": after, "hidden_faces_removed": removed, "door_nodes": n_doors, "out": out}
    wp._jdump(os.path.join(out, "merge_report.json"), rep)
    log(f"merge[{preset}]: files {before['files']}->{after['files']}, triangles {before['triangles']}->{after['triangles']}, draw calls {before['draw_calls_est']}->{after['draw_calls_est']}, "
        f"GLB {before['glb_mb']}->{after['glb_mb']} MB, textures {before['texture_mb']}->{after['texture_mb']} MB; {removed} hidden faces removed -> {out}")
    return doc, rep


def _rg(a):
    if a.road_grade == "off":
        return False
    return {"smooth": a.road_smooth, "max_grade_deg": a.road_max_grade, "cross_deg": a.road_cross_deg, "skirt": not a.no_road_skirt, "cutfill": a.road_cutfill}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for n in ("split", "reexport", "merge", "publish", "info"):
        s = sub.add_parser(n)
        s.add_argument("--place", default="bridgehollow")
        s.add_argument("--pack")
        if n in ("split", "reexport"):
            s.add_argument("--split", help="comma list layer=granularity (layer|group|entity|species|none), e.g. buildings=group,roads=entity")
            s.add_argument("--split-preset", choices=list(SPLIT_PRESETS), default="default")
            s.add_argument("--textures", choices=["external", "embed", "none"], default="external")
            s.add_argument("--roof-mode", dest="roof_mode", choices=["none", "per_building", "per_scene"], help="roofs: none = merged into each building (default), per_building = one toggle-able roof tile per building, "
                           "per_scene = one merged roof tile for the whole scene (worldpack_roofs.py); reexport keeps the mode of the existing pack unless given")
            s.add_argument("--interior-style", dest="interior_style", choices=["auto", "plain", "rustic_cottage", "farmhouse", "burgher_townhouse", "poor_hovel"],
                           help="home interior style for buildings with a generated interior (interior_styles.py); recorded in the manifest. Omitted = the manifest value (export --interior-style), else auto = by building kind")
            s.add_argument("--step", type=int, default=1, help="terrain mesh step in heightmap cells")
            s.add_argument("--no-carve", action="store_true")
            s.add_argument("--no-conform", action="store_true")
            g = s.add_argument_group("road grading (road_grade.py)")
            g.add_argument("--road-grade", choices=["on", "off"], default="on", help="off = old behaviour (roads at the authored heights, terrain pulled to the centreline)")
            g.add_argument("--road-smooth", type=float, default=0.5, help="0..1: blend of raw ground height and a moving-average longitudinal profile")
            g.add_argument("--road-max-grade", type=float, default=14.0, help="maximum road grade, degrees")
            g.add_argument("--road-cross-deg", type=float, default=10.0, help="maximum cross slope of the road surface, degrees")
            g.add_argument("--no-road-skirt", action="store_true", help="no flared apron under roads standing above the ground")
            g.add_argument("--road-cutfill", action="store_true", help="cut/fill the terrain under and beside the roads, blended back to natural ground")
        if n == "reexport":
            s.add_argument("--id", required=True, help="entity id(s), comma separated")
        if n in ("merge", "publish"):
            s.add_argument("--preset", choices=["all", "layer", "district", "individual"], default="layer")
            s.add_argument("--compress", choices=["none", "quant", "meshopt", "meshopt-fallback"], default="none")
            s.add_argument("--no-hidden-removal", action="store_true")
            s.add_argument("--foliage", action="store_true", help="replace the per-tree foliage tiles with merged foliage chunks from world/<place>/foliage.json (foliage.py)")
            s.add_argument("--foliage-chunk-ft", type=float, default=150.0)
            s.add_argument("--foliage-budget", type=int)
            s.add_argument("--foliage-impostor-ft", type=float)
        if n == "publish":
            s.add_argument("--scene-uuid")
            s.add_argument("--scene-name")
            s.add_argument("--lod", type=int, default=0)
            s.add_argument("--dry-run", action="store_true")
            s.add_argument("--yes", action="store_true")
    a = ap.parse_args(argv)
    pack = a.pack or os.path.join(wp.REPO, "world", a.place, "export")
    if a.cmd == "split":
        if a.interior_style:
            wp.set_interior_style(pack, a.interior_style)
        rm = a.roof_mode or wp.load_pack(pack).manifest.get("foundry", {}).get("roof_mode") or "none"       # the mode recorded by `worldpack.py export --roof-mode`
        split_export(pack, split=parse_split(a.split, a.split_preset, rm), roof_mode=rm, textures=a.textures, step=a.step, carve=not a.no_carve, conform=not a.no_conform, road_grade=_rg(a))
    elif a.cmd == "reexport":
        if a.interior_style:
            wp.set_interior_style(pack, a.interior_style)
        split_export(pack, split=wp._jload(os.path.join(pack, "placements.json"))["split"] if os.path.exists(os.path.join(pack, "placements.json")) else None,
                     textures=a.textures, step=a.step, carve=not a.no_carve, conform=not a.no_conform, only=a.id.split(","), road_grade=_rg(a), roof_mode=a.roof_mode)
    elif a.cmd in ("merge", "publish"):
        doc, rep = merge_export(pack, a.preset, compress=a.compress, remove_hidden=not a.no_hidden_removal)
        if a.foliage:                                                    # foliage.py: merged per-chunk foliage instead of one tile per tree (buildings/doors untouched)
            import foliage
            comp = "none" if a.compress == "none" else "quant"
            foliage.attach_to_optimized(a.place, pack, rep["out"], a.foliage_chunk_ft, a.foliage_budget, a.foliage_impostor_ft, None, comp)
            if comp != "none" and foliage.validate_chunks(rep["out"]):     # 3D Canvas cannot load quantized chunks: fall back to plain GLBs
                print("foliage: quantized chunks fail the 3D Canvas load check, re-merging uncompressed")
                foliage.attach_to_optimized(a.place, pack, rep["out"], a.foliage_chunk_ft, a.foliage_budget, a.foliage_impostor_ft, None, "none")
        if a.cmd == "publish":
            import foundry_push
            args = ["push-models", "--place", a.place, "--placements", os.path.join(rep["out"], "placements.json"), "--lod", str(a.lod)]
            if a.scene_uuid:
                args += ["--scene-uuid", a.scene_uuid]
            elif a.scene_name:
                args += ["--scene-name", a.scene_name]
            if a.dry_run:
                args.append("--dry-run")
            if a.yes:
                args.append("--yes")
            return foundry_push.main(args)
    else:
        d = wp._jload(os.path.join(pack, "placements.json"))
        print(json.dumps({"files": len(d["files"]), "triangles": sum(e["tris"] for e in d["files"]), "split": d["split"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
