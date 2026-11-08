"""Pre-flight check that a GLB can be loaded by Foundry's 3D Canvas (levels-3d-preview 9.0.x, three.js GLTFLoader + three-mesh-bvh workers).
No dependencies. validate_glb(path) -> list of problem strings (empty = ok).

Rejected, because the module cannot or may not load them (a failing tile logs "File format not supported or missing" and the exception in the module's render loop
leaves the whole canvas on its clear colour, which was the red-orange flood seen on 2026-11-08):
  * not a binary glTF 2.0 container / unparsable JSON chunk / truncated BIN chunk
  * extensionsRequired the loader has no decoder for: EXT_meshopt_compression, KHR_texture_basisu (KTX2), EXT_texture_avif ...
  * KHR_mesh_quantization (gltfpack -cc/-c): three can read it, but the module's raycast worker merges geometries and builds a BVH from `position`, which breaks on
    normalized int16 attributes ("Cannot read properties of undefined (reading 'count')" in three-mesh-bvh countNodes); treat as unsafe unless allow_quantized
  * a mesh primitive without POSITION, an accessor with count 0, a buffer view outside the BIN chunk, an external uri (buffer/image) that does not exist
"""
import json
import os
import struct

SAFE_REQUIRED = {"KHR_draco_mesh_compression", "KHR_texture_transform", "KHR_materials_unlit", "KHR_materials_emissive_strength", "KHR_materials_clearcoat",
                 "KHR_materials_transmission", "KHR_materials_ior", "KHR_materials_specular", "KHR_materials_sheen", "KHR_materials_volume", "KHR_lights_punctual",
                 "KHR_materials_pbrSpecularGlossiness", "EXT_texture_webp"}
QUANT = "KHR_mesh_quantization"


def read_glb(path):
    """-> (json dict, bin bytes or None). Raises ValueError with a readable reason."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("not a binary glTF (missing 'glTF' magic)")
    ver, total = struct.unpack_from("<II", data, 4)
    if ver != 2:
        raise ValueError(f"glTF container version {ver}, need 2")
    if total > len(data):
        raise ValueError(f"truncated: header says {total} bytes, file has {len(data)}")
    off, js, bn = 12, None, None
    while off + 8 <= total:
        ln, ty = struct.unpack_from("<II", data, off)
        body = data[off + 8: off + 8 + ln]
        if len(body) < ln:
            raise ValueError("truncated chunk")
        if ty == 0x4E4F534A:
            js = body
        elif ty == 0x004E4942 and bn is None:
            bn = body
        off += 8 + ln + ((4 - ln % 4) % 4)
    if js is None:
        raise ValueError("no JSON chunk")
    try:
        return json.loads(js.decode("utf-8").rstrip("\x00 ")), bn
    except ValueError as e:
        raise ValueError(f"JSON chunk does not parse: {e}")


def validate_glb(path, allow_quantized=False):
    try:
        g, bn = read_glb(path)
    except (OSError, ValueError) as e:
        return [f"{os.path.basename(path)}: {e}"]
    name, bad = os.path.basename(path), []
    req = set(g.get("extensionsRequired", []))
    for e in sorted(req - SAFE_REQUIRED - {QUANT}):
        bad.append(f"{name}: requires {e}, which 3D Canvas cannot decode")
    used = set(g.get("extensionsUsed", [])) | req
    if QUANT in used and not allow_quantized:
        bad.append(f"{name}: uses {QUANT} (quantized attributes); the module's raycast/BVH worker mishandles it. Re-export without gltfpack -c/-cc/-cf")
    if "EXT_meshopt_compression" in used:
        bad.append(f"{name}: uses EXT_meshopt_compression, which 3D Canvas cannot decode")
    acc = g.get("accessors", [])
    views = g.get("bufferViews", [])
    for i, a in enumerate(acc):
        if a.get("count", 0) <= 0:
            bad.append(f"{name}: accessor {i} has count 0")
    for i, v in enumerate(views):
        b = g.get("buffers", [{}])[v.get("buffer", 0)] if g.get("buffers") else {}
        if "uri" not in b and bn is not None and v.get("byteOffset", 0) + v.get("byteLength", 0) > len(bn):
            bad.append(f"{name}: bufferView {i} runs past the BIN chunk")
    for mi, m in enumerate(g.get("meshes", [])):
        for pi, p in enumerate(m.get("primitives", [])):
            at = p.get("attributes", {})
            if "POSITION" not in at and "KHR_draco_mesh_compression" not in (p.get("extensions") or {}):
                bad.append(f"{name}: mesh {mi} primitive {pi} has no POSITION attribute")
            if at.get("POSITION") is not None and at["POSITION"] >= len(acc):
                bad.append(f"{name}: mesh {mi} primitive {pi} POSITION accessor out of range")
    if bn is None and any("uri" not in b for b in g.get("buffers", [])):
        bad.append(f"{name}: buffer without uri but no BIN chunk")
    base = os.path.dirname(os.path.abspath(path))
    for kind in ("buffers", "images"):
        for i, o in enumerate(g.get(kind, [])):
            u = o.get("uri")
            if u and not u.startswith("data:"):
                from urllib.parse import unquote
                if not os.path.isfile(os.path.normpath(os.path.join(base, unquote(u)))):
                    bad.append(f"{name}: {kind[:-1]} {i} uri {u} not found next to the file")
    if not g.get("meshes"):
        bad.append(f"{name}: no meshes")
    return bad
