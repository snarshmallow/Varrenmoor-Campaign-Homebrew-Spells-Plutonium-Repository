"""Varrenmoor world pack v1: a versioned, deterministic export of a place for the 3D pipeline (Blender, GLB, AI image-to-3D, Foundry).

  python illustrator/generators/worldpack.py export   --place bridgehollow [--out DIR] [--lod 1,4] [--terrain-source auto|base|patched|carved]
  python illustrator/generators/worldpack.py validate --place bridgehollow | --path DIR
  python illustrator/generators/worldpack.py info     --place bridgehollow | --path DIR

  import worldpack
  worldpack.export_world("bridgehollow", out_dir)          # -> world/bridgehollow/export/ by default
  pack = worldpack.load_pack(out_dir)                       # plain dicts + numpy heights
  pack.list("buildings"), pack.get("bld_house_001"), pack.elevation_at(x, y)
  pack.to_blender(x_ft, y_ft, z_ft) -> (x_m, y_m, z_m)      # Blender Z-up metres, see WORLD_PACK.md

The loader half needs only numpy + the stdlib, so it runs inside Blender's Python. The exporter also needs scipy, Pillow and shapely
(already required by the Illustrator generators). Full format description: illustrator/WORLD_PACK.md; JSON Schema:
world/schema/world-pack.schema.json. The pack is read-only with respect to world/: it never changes world data.
"""
import argparse
import datetime
import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
FORMAT = "varrenmoor-world-pack"
SCHEMA_VERSION = "1.0"
FT_M = 0.3048
SCHEMA_PATH = os.path.join(REPO, "world", "schema", "world-pack.schema.json")
TEXTURE_DIR = os.path.join(REPO, "illustrator", "presets", "textures")
ENTITY_TYPES = ("roads", "buildings", "plazas", "fields", "districts", "water", "fences", "foliage", "props", "lights", "labels")

# Derived 3D defaults (the world JSON has no roof or wall data yet). Everything here is flagged "derived" in the pack.
STOREY_FT = 10.0
ROOFS = {  # kind -> (roof type, pitch = rise/run of each slope)
    "house": ("gable", 0.6), "farmhouse": ("gable", 0.6), "shed": ("gable", 0.4), "barn": ("gable", 0.5), "stable": ("gable", 0.5),
    "inn": ("gable", 0.65), "tavern": ("gable", 0.65), "craft": ("gable", 0.55), "mill": ("gable", 0.5), "civic": ("hip", 0.5),
    "default": ("gable", 0.55)}
WALLS = {  # kind -> (texture, tile_ft)
    "house": ("plank", 8), "farmhouse": ("plank", 8), "shed": ("plank", 8), "barn": ("plank", 10), "stable": ("plank", 10),
    "craft": ("plank", 8), "mill": ("stone_slab", 8), "inn": ("stone_slab", 8), "tavern": ("stone_slab", 8),
    "civic": ("stone_slab", 8), "default": ("plank", 8)}
FENCE_HEIGHT_FT = 3.5
SPLAT_CELL_FT = 5.0
ALBEDO_PX_PER_FT = 0.5


# ======================================================================================= small helpers (loader side)
def ft_to_m(v):
    return v * FT_M


def m_to_ft(v):
    return v / FT_M


class Frame:
    """The pack's coordinate frames. World = repo frame (feet; x east, y SOUTH/down, origin top-left, z up).
    Blender = metres, x east, y NORTH (= H - y), z up, origin at the place's south-west corner, z measured from z_origin_ft."""

    def __init__(self, width_ft, height_ft, z_origin_ft=0.0, foundry_px_per_ft=20.0, foundry_x0=0.0, foundry_y0=0.0):
        self.width_ft, self.height_ft, self.z_origin_ft = float(width_ft), float(height_ft), float(z_origin_ft)
        self.px_per_ft, self.x0, self.y0 = float(foundry_px_per_ft), float(foundry_x0), float(foundry_y0)

    @classmethod
    def from_manifest(cls, m):
        f = m["foundry"]
        return cls(m["extent"]["width_ft"], m["extent"]["height_ft"], m["z_origin_ft"], f["px_per_ft"], f["x0_ft"], f["y0_ft"])

    def to_blender(self, x, y, z=None):
        bx, by = x * FT_M, (self.height_ft - y) * FT_M
        return (bx, by) if z is None else (bx, by, (z - self.z_origin_ft) * FT_M)

    def from_blender(self, bx, by, bz=None):
        x, y = bx / FT_M, self.height_ft - by / FT_M
        return (x, y) if bz is None else (x, y, bz / FT_M + self.z_origin_ft)

    def to_gltf(self, x, y, z):
        """glTF is Y-up: (east_m, up_m, south_m - H_m); Blender's importer maps it back to to_blender()."""
        bx, by, bz = self.to_blender(x, y, z)
        return bx, bz, -by

    def to_foundry_px(self, x, y, scene_x=0.0, scene_y=0.0):
        """Scene pixels (y down, like the world frame): scene_x + (x - x0) * px_per_ft."""
        return scene_x + (x - self.x0) * self.px_per_ft, scene_y + (y - self.y0) * self.px_per_ft

    def foundry_tile(self, bounds=None):
        """3D Canvas tile (centre x,y; width, height in px; rotation 0: Blender north = canvas up per make-scene.ps1/item.py; verify with generators/orientation_test.py) for a model that spans
        `bounds` = (xmin, ymin, xmax, ymax) feet (default the whole place)."""
        x0, y0, x1, y1 = bounds or (0, 0, self.width_ft, self.height_ft)
        cx, cy = self.to_foundry_px((x0 + x1) / 2, (y0 + y1) / 2)
        return {"x": cx, "y": cy, "width": (x1 - x0) * self.px_per_ft, "height": (y1 - y0) * self.px_per_ft, "rotation": 0}


def polygon_area(pts):
    """Shoelace area of [[x,y],...] (absolute value, feet^2 if the points are feet)."""
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]
        a += x0 * y1 - x1 * y0
    return abs(a) / 2.0


def bilinear(h, cell_ft, x, y):
    """Heights at (x, y) feet; node h[i,j] at x=j*cell, y=i*cell (y down). Scalars or arrays. Clamped to the grid."""
    ny, nx = h.shape
    fx = np.clip(np.asarray(x, float) / cell_ft, 0, nx - 1)
    fy = np.clip(np.asarray(y, float) / cell_ft, 0, ny - 1)
    j0, i0 = np.minimum(fx.astype(int), nx - 2), np.minimum(fy.astype(int), ny - 2)
    tx, ty = fx - j0, fy - i0
    v = (h[i0, j0] * (1 - tx) * (1 - ty) + h[i0, j0 + 1] * tx * (1 - ty) + h[i0 + 1, j0] * (1 - tx) * ty + h[i0 + 1, j0 + 1] * tx * ty)
    return float(v) if np.ndim(v) == 0 else v


def slug_id(t):
    import re
    return re.sub(r"[^a-z0-9]+", "_", str(t).lower()).strip("_") or "x"


def r3(v):
    return round(float(v), 3)


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _jdump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)
        f.write("\n")


def files_sha(root, rel):
    return _sha(os.path.join(root, rel))


def _jload(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ======================================================================================= loader
class WorldPack:
    """A loaded pack: `manifest`, `entities` {type: [dict]}, `materials` {id: dict}, `frame`, lazily `heights`."""

    def __init__(self, root, manifest, entities, materials):
        self.root, self.manifest, self.entities, self.materials = root, manifest, entities, materials
        self.frame = Frame.from_manifest(manifest)
        self.place = manifest["place"]["id"]
        self._h = None
        self._index = {e["id"]: (t, e) for t, items in entities.items() for e in items}

    # ---- terrain
    @property
    def cell_ft(self):
        return self.manifest["terrain"]["cell_ft"]

    @property
    def heights(self):
        """float32 [ny, nx] signed elevations in feet (row 0 = y 0 = north edge)."""
        if self._h is None:
            t = self.manifest["terrain"]
            self._h = np.fromfile(os.path.join(self.root, t["heights_bin"]), dtype="<f4").reshape(t["ny"], t["nx"])
        return self._h

    def elevation_at(self, x, y):
        """Terrain elevation in feet at world (x, y) feet (bilinear)."""
        return bilinear(self.heights, self.cell_ft, x, y)

    # ---- entities
    def list(self, type_=None):
        return list(self._index_all()) if type_ is None else self.entities.get(type_, [])

    def _index_all(self):
        for t in ENTITY_TYPES:
            yield from self.entities.get(t, [])

    def get(self, id_):
        return self._index[id_][1]

    def type_of(self, id_):
        return self._index[id_][0]

    def polygon(self, id_, with_z=False):
        """Footprint / area polygon as [[x, y(, z)], ...] in world feet (z = base elevation when requested)."""
        e = self.get(id_)
        pts = e.get("polygon") or e.get("outline") or e["points"]
        if with_z:
            z = e.get("base_elevation_ft", e.get("elevation_ft", 0.0))
            return [[p[0], p[1], p[2] if len(p) > 2 else z] for p in pts]
        return [[p[0], p[1]] for p in pts]

    # ---- transforms (see Frame)
    def to_blender(self, x, y, z=None):
        return self.frame.to_blender(x, y, z)

    def from_blender(self, bx, by, bz=None):
        return self.frame.from_blender(bx, by, bz)

    def to_foundry_px(self, x, y, **kw):
        return self.frame.to_foundry_px(x, y, **kw)

    def polygon_blender(self, id_, with_z=True):
        return [self.to_blender(*p) for p in self.polygon(id_, with_z=with_z)]

    def path(self, rel):
        return os.path.join(self.root, rel)


def load_pack(path):
    """path: the pack folder (or its manifest.json). Returns WorldPack."""
    root = os.path.abspath(os.path.dirname(path) if os.path.basename(path) == "manifest.json" else path)
    m = _jload(os.path.join(root, "manifest.json"))
    if m.get("format") != FORMAT:
        raise ValueError(f"{root}: not a {FORMAT}")
    if int(str(m["schema_version"]).split(".")[0]) != int(SCHEMA_VERSION.split(".")[0]):
        raise ValueError(f"{root}: schema {m['schema_version']} is not supported by this loader ({SCHEMA_VERSION})")
    ents = {t: (_jload(os.path.join(root, info["file"]))["items"] if info.get("file") else []) for t, info in m["entities"].items()}
    mats = {x["id"]: x for x in _jload(os.path.join(root, m["materials_file"]))["materials"]}
    try:
        import worldpack_pbr
        worldpack_pbr.prepare(mats)       # PBR factors, normal/metallicRoughness flags, extra surface materials (in memory only)
    except ImportError:
        pass
    return WorldPack(root, m, ents, mats)


def _conform(h, cell, lines, falloff_ft, mode):
    """Blend heights toward polylines. lines: [(pts[n,2], z[n] feet, half_width[n] feet)]; mode 'min' only lowers (river beds), 'set' pulls
    terrain to the line's z (road beds). Weight is 1 within the half width and falls off smoothly over falloff_ft."""
    ny, nx = h.shape
    X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
    h = h.copy()
    for pts, zs, hw in lines:
        best = np.full(h.shape, np.inf)
        z = np.zeros(h.shape)
        halfw = np.zeros(h.shape)
        for a in range(len(pts) - 1):
            p, q = pts[a], pts[a + 1]
            d = q - p
            t = np.clip(((X - p[0]) * d[0] + (Y - p[1]) * d[1]) / (float(d @ d) or 1e-9), 0, 1)
            dist = np.hypot(X - (p[0] + t * d[0]), Y - (p[1] + t * d[1]))
            upd = dist < best
            best = np.where(upd, dist, best)
            z = np.where(upd, zs[a] * (1 - t) + zs[a + 1] * t, z)
            halfw = np.where(upd, hw[a] * (1 - t) + hw[a + 1] * t, halfw)
        k = np.clip((halfw + falloff_ft - best) / falloff_ft, 0, 1)
        k = k * k * (3 - 2 * k)
        new = h * (1 - k) + z * k
        h = np.where(k > 0, np.minimum(h, new) if mode == "min" else new, h)
    return h.astype(np.float32)


def carved_heights(pack, falloff_ft=12.0):
    """Terrain with the river bed cut in (water surface - depth along the centreline, blended into the banks). The exported heightmap
    is left as authored; the carve is optional and done by the consumer."""
    lines = []
    for w in pack.list("water"):
        if w.get("kind") == "river" and w.get("centerline"):
            lines.append((np.array(w["centerline"], float), np.array(w["bed_elevations_ft"], float), np.array(w["widths_ft"], float) / 2))
    return _conform(pack.heights, pack.cell_ft, lines, falloff_ft, "min")


def road_conformed_heights(pack, h=None, falloff_ft=10.0, classes=None):
    """Terrain pulled to the graded road centrelines (bridges excluded) so ribbons sit on the ground instead of cutting through it."""
    lines = [(np.array([p[:2] for p in r["points"]], float), np.array([p[2] for p in r["points"]], float), np.full(len(r["points"]), r["width_ft"] / 2))
             for r in pack.list("roads") if not r.get("bridge") and (classes is None or r["class"] in classes)]
    return _conform(pack.heights if h is None else h, pack.cell_ft, lines, falloff_ft, "set")


# ======================================================================================= exporter
def _git():
    try:
        c = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True, stderr=subprocess.DEVNULL).strip()
        d = bool(subprocess.check_output(["git", "status", "--porcelain", "--", "world", "illustrator/presets"], cwd=REPO, text=True,
                                         stderr=subprocess.DEVNULL).strip())
        return c, d
    except Exception:
        return None, None


def _strip_closed(pts):
    pts = [list(p) for p in pts]
    if len(pts) > 1 and pts[0][:2] == pts[-1][:2]:
        pts = pts[:-1]
    return pts


def _links(e):
    return e.get("links") or {"foundry_scene": None, "model3d": None, "ai_layer": None}


def _common(e, place, type_, src):
    return {"id": e["id"], "name": e.get("name", e["id"]), "kind": e.get("kind", ""), "status": e.get("status", "proposed"),
            "notes": e.get("notes", ""), "links": _links(e), "source": src,
            "foundry": {"pipelineId": f"world:{place}:{e['id']}"}}


KERB_W_FT = 0.7


def _road_kerbs(roads, street_ids):
    """Region children: kerb bands along the edge of every street that has a detail-pass kerb, trimmed where other roads cross (feet, simple polygons).
    Stored as road['kerbs'] = [ring, ...]; worldpack_mesh.build_road raises them above the road surface."""
    if not street_ids:
        return
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    polys = {r["id"]: Polygon(r["outline"]).buffer(0) for r in roads if r.get("outline") and len(r["outline"]) >= 3}
    for r in roads:
        if r["id"] not in street_ids or r["id"] not in polys or r.get("bridge"):
            continue
        p = polys[r["id"]]
        band = p.buffer(KERB_W_FT, join_style=2).difference(p)
        others = [q for k, q in polys.items() if k != r["id"]]
        if others:
            band = band.difference(unary_union(others).buffer(0.5))
        rings = []
        for g in ([band] if band.geom_type == "Polygon" else list(getattr(band, "geoms", []))):
            if g.geom_type == "Polygon" and g.area > 1.0:
                g = g.simplify(0.05)
                rings.append([[r3(x), r3(y)] for x, y in list(g.exterior.coords)[:-1]])
        if rings:
            r["kerbs"] = rings
            r.setdefault("derived", []).append("kerbs")


def _detail_mats():
    import worldpack_detail
    return worldpack_detail.DETAIL_MATS


def _load_model(place, world_root):
    import worldio
    root = os.path.join(world_root or os.path.join(REPO, "world"), place)
    rd = lambda f: _jload(os.path.join(root, f))
    m = {"root": root, "place": rd("place.json"), "districts": rd("districts.json")["districts"], "streets": rd("streets.json")["streets"],
         "water": _jload(worldio.water_path(place, root=world_root))["water"], "buildings": [], "state": worldio.load_state(place, world_root)}
    bd = os.path.join(root, "buildings")
    for f in sorted(os.listdir(bd)) if os.path.isdir(bd) else []:
        if f.endswith(".json"):
            b = _jload(os.path.join(bd, f))
            b["_file"] = f
            m["buildings"].append(b)
    vs = os.path.join(root, "view_settings.json")
    m["view"] = _jload(vs) if os.path.exists(vs) else {}
    dp = os.path.join(root, "details.json")                      # region children: generated doors etc. (not canon) -> building openings
    m["details"] = _jload(dp) if os.path.exists(dp) else {}
    return m


def _obb(poly):
    """(centre, long-axis angle deg from +x toward +y, length, width) of the minimum rotated rectangle (same as fills_raster.long_axis)."""
    from shapely.geometry import Polygon
    pg = Polygon(poly).buffer(0)
    r = pg.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return list(pg.centroid.coords)[0], 0.0, 1.0, 1.0
    c = list(r.exterior.coords)[:4]
    e = [(c[(i + 1) % 4][0] - c[i][0], c[(i + 1) % 4][1] - c[i][1]) for i in range(2)]
    l0, l1 = math.hypot(*e[0]), math.hypot(*e[1])
    d = e[0] if l0 >= l1 else e[1]
    ang = math.degrees(math.atan2(d[1], d[0])) % 180.0
    return (r.centroid.x, r.centroid.y), ang, max(l0, l1), min(l0, l1)


def _write_glb(path, positions, normals, uvs, indices, name, extras):
    """Minimal glTF 2.0 binary: one mesh, one node, one default material. positions/normals float32 [n,3] (glTF axes), uvs [n,2]."""
    pos = np.ascontiguousarray(positions, "<f4")
    nrm = np.ascontiguousarray(normals, "<f4")
    uv = np.ascontiguousarray(uvs, "<f4")
    idx = np.ascontiguousarray(indices, "<u4").reshape(-1)
    blobs = [pos.tobytes(), nrm.tobytes(), uv.tobytes(), idx.tobytes()]
    offs, o = [], 0
    for b in blobs:
        offs.append(o)
        o += len(b)
    views = [{"buffer": 0, "byteOffset": offs[i], "byteLength": len(blobs[i]), "target": 34963 if i == 3 else 34962} for i in range(4)]
    acc = [{"bufferView": 0, "componentType": 5126, "count": len(pos), "type": "VEC3", "min": pos.min(0).tolist(), "max": pos.max(0).tolist()},
           {"bufferView": 1, "componentType": 5126, "count": len(nrm), "type": "VEC3"},
           {"bufferView": 2, "componentType": 5126, "count": len(uv), "type": "VEC2"},
           {"bufferView": 3, "componentType": 5125, "count": len(idx), "type": "SCALAR"}]
    g = {"asset": {"version": "2.0", "generator": "varrenmoor worldpack.py"}, "scene": 0, "scenes": [{"nodes": [0]}],
         "nodes": [{"mesh": 0, "name": name, "extras": extras}],
         "meshes": [{"name": name, "primitives": [{"attributes": {"POSITION": 0, "NORMAL": 1, "TEXCOORD_0": 2}, "indices": 3, "material": 0}]}],
         "materials": [{"name": "terrain", "pbrMetallicRoughness": {"metallicFactor": 0.0, "roughnessFactor": 0.95}, "doubleSided": True}],
         "accessors": acc, "bufferViews": views, "buffers": [{"byteLength": o}]}
    js = json.dumps(g, separators=(",", ":"), sort_keys=True).encode()
    js += b" " * (-len(js) % 4)
    bin_ = b"".join(blobs)
    bin_ += b"\0" * (-len(bin_) % 4)
    total = 12 + 8 + len(js) + 8 + len(bin_)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sII", b"glTF", 2, total))
        f.write(struct.pack("<I4s", len(js), b"JSON") + js)
        f.write(struct.pack("<I4s", len(bin_), b"BIN\0") + bin_)


def _terrain_mesh(h, cell, frame, step):
    ny, nx = h.shape
    ii = np.unique(np.append(np.arange(0, ny, step), ny - 1))
    jj = np.unique(np.append(np.arange(0, nx, step), nx - 1))
    gy, gx = np.gradient(h.astype(float), cell, cell)           # d/dy (south), d/dx (east), feet per foot
    nxv, nyv = -gx, gy                                             # normal in world axes (x east, y south, z up) = (-dh/dx, -dh/dy, 1); flip y below
    X, Y = np.meshgrid(jj * cell, ii * cell)
    Z = h[np.ix_(ii, jj)].astype(float)
    W, H = frame.width_ft, frame.height_ft
    pos = np.stack([X * FT_M, (Z - frame.z_origin_ft) * FT_M, (Y - H) * FT_M], -1).reshape(-1, 3)          # glTF: x east, y up, z south
    n_east, n_south = (-gx)[np.ix_(ii, jj)], (-gy)[np.ix_(ii, jj)]
    nor = np.stack([n_east, np.ones_like(n_east), n_south], -1)
    nor = (nor / np.linalg.norm(nor, axis=-1, keepdims=True)).reshape(-1, 3)
    uv = np.stack([X / W, Y / H], -1).reshape(-1, 2)
    ni, nj = len(ii), len(jj)
    a = (np.arange(ni - 1)[:, None] * nj + np.arange(nj - 1)[None, :]).reshape(-1)
    b, c, d = a + 1, a + nj, a + nj + 1
    # counter-clockwise seen from above (+y up in glTF): with z pointing south, going east then south is clockwise, so reverse
    tri = np.stack([a, b, c, b, d, c], -1).reshape(-1, 3)[:, ::-1]
    return pos, nor, uv, tri


def _save_png(arr, path, mode=None):
    from PIL import Image
    im = Image.fromarray(arr) if mode is None else Image.fromarray(arr, mode)
    im.save(path, optimize=False, compress_level=6)


def _phases(model, phases_path):
    import shading
    st = model["state"].get("shading") or {}
    if phases_path:
        doc = shading.load_phase_file(phases_path)
        return doc["phases"], doc.get("base_color", "#808080"), doc.get("name", os.path.basename(phases_path)), os.path.dirname(os.path.abspath(phases_path)), None
    if st.get("phases"):
        return st["phases"], st.get("base_color", "#808080"), st.get("preset", "panel_state"), TEXTURE_DIR, st.get("hillshade")
    p = os.path.join(shading.PRESET_DIR, "alpine_steep.json")
    doc = shading.load_phase_file(p)
    return doc["phases"], doc.get("base_color", "#808080"), "alpine_steep", os.path.dirname(p), None


def _export_terrain(out, h, meta, frame, model, lods, splat_cell_ft, albedo_ppf, phases_path, copy_tex, textures):
    import shading
    T = os.path.join(out, "terrain")
    os.makedirs(T, exist_ok=True)
    h = np.ascontiguousarray(h, "<f4")
    ny, nx = h.shape
    cell = float(meta["cell_ft"])
    np.save(os.path.join(T, "heightmap_f32.npy"), h)
    h.tofile(os.path.join(T, "heightmap_f32.bin"))
    lo, hi = float(h.min()), float(h.max())
    u16 = np.round((h - lo) / max(hi - lo, 1e-9) * 65535).astype(np.uint16)
    _save_png(u16, os.path.join(T, "heightmap_16.png"))
    gy, gx = np.gradient(h.astype(float), cell, cell)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    _save_png(np.round(np.clip(slope, 0, 90) / 90 * 255).astype(np.uint8), os.path.join(T, "slope.png"))
    n = np.stack([-gx, gy, np.ones_like(gx)], -1)
    n = n / np.linalg.norm(n, axis=-1, keepdims=True)
    _save_png(np.round((n * 0.5 + 0.5) * 255).astype(np.uint8), os.path.join(T, "normal.png"))
    files = {"heights_npy": "terrain/heightmap_f32.npy", "heights_bin": "terrain/heightmap_f32.bin", "heights_png16": "terrain/heightmap_16.png",
             "slope_png": "terrain/slope.png", "normal_png": "terrain/normal.png"}
    meshes = []
    for step in lods:
        pos, nor, uv, tri = _terrain_mesh(h, cell, frame, int(step))
        rel = f"terrain/terrain_lod{int(step)}.glb"
        _write_glb(os.path.join(out, rel), pos, nor, uv, tri, "terrain", {"varrenmoor": {"place": model["place"]["id"], "frame": "blender-metres-yup-gltf",
                                                                                         "z_origin_ft": frame.z_origin_ft, "step_cells": int(step)}})
        meshes.append({"file": rel, "step_cells": int(step), "vertices": int(len(pos)), "triangles": int(len(tri))})
    # splat weights + baked albedo from the shading phases (the same ones the 2D map is drawn with)
    phases, base_color, preset, base_dir, hill = _phases(model, phases_path)
    sea = float(meta.get("sea_level_ft", 0.0))
    seed = int(meta.get("seed", 0))
    ppf = 1.0 / splat_cell_ft
    sx, sy = int(round(frame.width_ft * ppf)), int(round(frame.height_ft * ppf))
    X, Y = np.meshgrid((np.arange(sx) + .5) / ppf, (np.arange(sy) + .5) / ppf)
    elev = shading.resample(h, X, Y, cell)
    slp = shading.resample(shading.slope_deg_native(h, cell), X, Y, cell)
    chans, ids, remaining = [], [], np.ones_like(elev)
    raw = []
    for i, p in enumerate(phases):
        w = shading.phase_weight(p, i, elev, slp, ppf, seed, sea)
        if w is not None:
            raw.append((p, np.clip(w, 0, 1)))
    eff = []
    acc = np.ones_like(elev)
    for p, w in reversed(raw):                                   # painter's order: later phases cover earlier ones
        eff.append((p, w * acc))
        acc = acc * (1 - w)
    eff.reverse()
    base_w = acc
    ids = ["base"] + [str(p.get("id", i)) for i, (p, _) in enumerate(eff)]
    chans = [base_w] + [w for _, w in eff]
    while len(chans) % 4:
        chans.append(np.zeros_like(base_w))
    splat_files = []
    for k in range(0, len(chans), 4):
        rel = f"terrain/splat_{k // 4}.png"
        arr = np.round(np.clip(np.stack(chans[k:k + 4], -1), 0, 1) * 255).astype(np.uint8)
        _save_png(arr, os.path.join(out, rel))
        splat_files.append({"file": rel, "channels": ids[k:k + 4] + [None] * (4 - len(ids[k:k + 4]))})
    phase_info = []
    for (p, _w) in eff:
        t = p.get("texture", "")
        tex = None
        if isinstance(t, str) and not t.startswith("#") and t:
            tex = textures.add(os.path.normpath(os.path.join(base_dir, t)) if not os.path.isabs(t) else t, copy_tex)
        phase_info.append({"id": str(p.get("id")), "name": p.get("name", ""), "material": tex, "tile_ft": p.get("tile_scale_ft"),
                           "elev_min_ft": p.get("elev_min"), "elev_max_ft": p.get("elev_max"), "slope_min_deg": p.get("slope_min_deg"),
                           "slope_max_deg": p.get("slope_max_deg"), "water": bool(p.get("water_depth") or p.get("below_datum"))})
    ap = float(albedo_ppf)
    img, _ = shading.render(h, meta, [p for p, _ in raw], ap, base_dir, None, seed, base_color, verbose=False)
    _save_png(img, os.path.join(T, "albedo.png"))
    files["albedo_png"] = "terrain/albedo.png"
    return {"cell_ft": cell, "nx": nx, "ny": ny, "size_ft": [float(meta["size_ft"][0]), float(meta["size_ft"][1])], "elev_min_ft": r3(lo), "elev_max_ft": r3(hi),
            "heights_dtype": "float32-le", "heights_layout": "row-major [ny][nx]; h[i][j] at x=j*cell_ft, y=i*cell_ft (y south); row 0 is the north edge",
            "png16": {"min_ft": lo, "max_ft": hi, "decode": "elev_ft = min_ft + value / 65535 * (max_ft - min_ft)"},
            "source": meta.get("source", "base"), "pipeline": meta.get("pipeline"), "seed": meta.get("seed"), "meshes": meshes,
            "slope_png": {"decode": "slope_deg = value / 255 * 90"}, "normal_png": {"decode": "n = value / 255 * 2 - 1 as (east, north, up)"},
            "albedo": {"file": "terrain/albedo.png", "px_per_ft": ap, "size_px": [int(img.shape[1]), int(img.shape[0])],
                       "note": "baked shading phases, no hillshade; UV = (x / width_ft, y / height_ft), row 0 north"},
            "splat": {"cell_ft": splat_cell_ft, "size_px": [sx, sy], "preset": preset, "files": splat_files, "phases": phase_info,
                      "note": "weights sum to 1 per pixel (base + phases, painter-order composited as the 2D shading does); RGBA 8-bit, row 0 north"},
            "files": files}


class Textures:
    """Collects the textures an export references: copies PNGs into export/textures/ and returns material ids."""

    def __init__(self, out):
        self.out, self.mats = out, {}

    def add(self, src, copy=True):
        name = os.path.splitext(os.path.basename(src))[0]
        if name.startswith("mat_"):
            name = name[4:]
        mid = "mat_" + name
        if mid not in self.mats:
            self.mats[mid] = {"id": mid, "src": src, "name": name}
        return mid

    def name_to_src(self, tex_name):
        return os.path.join(TEXTURE_DIR, tex_name if tex_name.endswith(".png") else tex_name + ".png")

    def tex(self, tex_name):
        return self.add(self.name_to_src(tex_name))

    def write(self, place, copy=True):
        from PIL import Image
        res = []
        for mid in sorted(self.mats):
            m = self.mats[mid]
            rec = {"id": mid, "name": m["name"], "kind": "image", "texture": None, "source": None, "sha256": None, "mean_color": None,
                   "roughness": 0.9, "metallic": 0.0, "foundry": {"pipelineId": f"mat:{place}:{m['name']}"}}
            if os.path.exists(m["src"]):
                rel = f"textures/{m['name']}.png"
                if copy:
                    os.makedirs(os.path.join(self.out, "textures"), exist_ok=True)
                    shutil.copyfile(m["src"], os.path.join(self.out, rel))
                    rec["texture"] = rel
                    rec["sha256"] = _sha(os.path.join(self.out, rel))
                else:
                    rec["sha256"] = _sha(m["src"])
                rec["source"] = os.path.relpath(m["src"], REPO).replace("\\", "/") if m["src"].startswith(REPO) else m["src"]
                im = Image.open(m["src"]).convert("RGB")
                rec["mean_color"] = "#%02x%02x%02x" % tuple(int(round(v)) for v in np.asarray(im.resize((16, 16))).reshape(-1, 3).mean(0))
            res.append(rec)
        return res


def _entity_z(h, cell, pts):
    return [r3(bilinear(h, cell, p[0], p[1])) for p in pts]


def _surface(mid, tile_ft):
    return {"material": mid, "tile_ft": tile_ft}


def export_world(place, out_dir=None, lod=(1, 4), world_root=None, terrain_source=None, style=None, phases_path=None, splat_cell_ft=SPLAT_CELL_FT,
                 albedo_px_per_ft=ALBEDO_PX_PER_FT, foundry_px_per_ft=20.0, z_origin_ft=None, timestamp=None, copy_textures=True, log=print):
    """Write the world pack for `place`. Deterministic for identical inputs (the manifest's `generated` block is the only part that
    differs between runs; pass timestamp= to pin it). Returns the manifest dict."""
    sys.path.insert(0, HERE)
    import fills_raster as fr
    import worldio
    if terrain_source:
        worldio.set_source(source=terrain_source)
    model = _load_model(place, world_root)
    out = os.path.abspath(out_dir or os.path.join(model["root"], "export"))
    if os.path.exists(out) and os.listdir(out) and not os.path.exists(os.path.join(out, "manifest.json")):
        raise SystemExit(f"{out} exists and is not a world pack; refusing to overwrite")
    for sub in ("terrain", "entities", "textures"):
        shutil.rmtree(os.path.join(out, sub), ignore_errors=True)
    os.makedirs(out, exist_ok=True)
    lods = [lod] if isinstance(lod, int) else list(lod)
    h, meta = worldio.load_terrain(place, source=terrain_source, root=world_root)
    h = np.asarray(h, np.float32)
    cell = float(meta["cell_ft"])
    pl = model["place"]
    W, H = float(pl["bounds"]["width_ft"]), float(pl["bounds"]["height_ft"])
    sea = float(pl.get("sea_level_ft", meta.get("sea_level_ft", 0.0)))
    z0 = float(z_origin_ft) if z_origin_ft is not None else math.floor(float(h.min()) / 10.0) * 10.0
    frame = Frame(W, H, z0, foundry_px_per_ft, 0.0, 0.0)
    st_name = style or (model["state"].get("town", {}).get("fills", {}) or {}).get("style") or "full_map"
    sty = fr.load_style(st_name)
    types = sty["types"]
    sseed = int(sty.get("seed", 1))
    rng = lambda *a: np.random.default_rng(fr.seed_of(sseed, *a))
    tex = Textures(out)
    log(f"world pack: {place} -> {out}")
    terrain = _export_terrain(out, h, meta, frame, model, lods, splat_cell_ft, albedo_px_per_ft, phases_path, copy_textures, tex)
    srcp = lambda sub, f: f"world/{place}/{sub}{f}"
    from shapely.geometry import LineString, Point, Polygon
    import render_world as rw
    ents = {t: [] for t in ENTITY_TYPES}
    # ---- water first (roads need it for fords/bridges)
    river_polys = []
    for w in sorted(model["water"], key=lambda e: e["id"]):
        e = _common(w, place, "water", srcp("", "water.json"))
        poly = _strip_closed(w["geometry"]["points"])
        e["polygon"] = [[r3(p[0]), r3(p[1])] for p in poly]
        e["area_ft2"] = r3(polygon_area(poly))
        e["width_ft"], e["depth_ft"], e["flow"] = w.get("width_ft"), w.get("depth_ft", 0.0), w.get("flow")
        pg = Polygon(poly).buffer(0)
        if w.get("centerline"):
            cl = [[r3(p[0]), r3(p[1])] for p in w["centerline"]]
            terr = np.array(_entity_z(h, cell, cl))
            surf = np.minimum.accumulate(terr)                        # flows downstream (first to last vertex): never rises
            wid = [r3(2 * pg.exterior.distance(Point(p))) if pg.contains(Point(p)) else r3(w.get("width_ft") or 0) for p in cl]
            e["centerline"] = cl
            e["widths_ft"] = wid
            e["surface_elevations_ft"] = [r3(v) for v in surf]
            e["bed_elevations_ft"] = [r3(v - e["depth_ft"]) for v in surf]
            e["surface_note"] = "derived: terrain along the centreline, never rising downstream; consumers may carve the bed (worldpack.carved_heights)"
        else:
            bz = _entity_z(h, cell, poly)
            e["level_ft"] = r3(w.get("level_ft", min(bz)))
        e["surface"] = _surface(tex.tex(types.get("water", {}).get(w.get("kind", "river"), types.get("water", {}).get("default", {"texture": "water"}))["texture"]),
                                types.get("water", {}).get(w.get("kind", "river"), {}).get("tile_ft", 50))
        ents["water"].append(e)
        river_polys.append(pg)
    # ---- roads
    sc = types.get("streets", {})
    for s in sorted(model["streets"], key=lambda e: e["id"]):
        e = _common(s, place, "roads", srcp("", "streets.json"))
        pts = [[p[0], p[1]] for p in s["geometry"]["points"]]
        z = s.get("elevations_ft") or _entity_z(h, cell, pts)
        cls = fr.classify_street(s, sc)
        tc = sc.get(cls, sc.get("street", {"texture": "gravel", "tile_ft": 26}))
        e.update({"class": cls, "width_ft": s["geometry"]["width_ft"], "points": [[r3(p[0]), r3(p[1]), r3(zz)] for p, zz in zip(pts, z)],
                  "ring": s.get("ring"), "grade_max": s.get("grade_max"), "grade_raw_max": s.get("grade_raw_max"), "cut_fill_ft": s.get("cut_fill_ft"),
                  "length_ft": r3(sum(math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]) for i in range(len(pts) - 1))),
                  "material_hint": s.get("material"), "surface": _surface(tex.tex(tc["texture"]), tc.get("tile_ft")),
                  "outline": [[r3(a), r3(b)] for a, b in rw.entity_polygon(s)]})
        ls = LineString(pts)
        bridge = s.get("kind") == "bridge"
        e["bridge"] = None
        e["fords"] = []
        if bridge:
            inter = ls.intersection(river_polys[0]) if river_polys else None
            wsurf = None
            for w in ents["water"]:
                if w.get("surface_elevations_ft"):
                    cl = w["centerline"]
                    mid = ls.interpolate(0.5, normalized=True)
                    k = int(np.argmin([math.hypot(c[0] - mid.x, c[1] - mid.y) for c in cl]))
                    wsurf = w["surface_elevations_ft"][k]
            e["bridge"] = {"deck_elevations_ft": [r3(v) for v in z], "water_surface_ft": wsurf,
                           "clearance_ft": r3(min(z) - wsurf) if wsurf is not None else None, "span_ft": e["length_ft"],
                           "crosses": [w["id"] for w in ents["water"]]}
        else:
            for pg, w in zip(river_polys, ents["water"]):
                it = ls.intersection(pg)
                if not it.is_empty and it.length > 1.0:
                    segs = [it] if it.geom_type == "LineString" else list(getattr(it, "geoms", []))
                    for sg in segs:
                        if sg.geom_type == "LineString" and sg.length > 1.0:
                            e["fords"].append({"water": w["id"], "length_ft": r3(sg.length), "points": [[r3(a), r3(b)] for a, b in sg.coords]})
        ents["roads"].append(e)
    _road_kerbs(ents["roads"], {k["street"] for k in model.get("details", {}).get("kerbs", [])})
    # ---- buildings
    bc = types.get("buildings", {})
    for b in sorted(model["buildings"], key=lambda e: e["id"]):
        e = _common(b, place, "buildings", srcp("buildings/", b["_file"]))
        poly = _strip_closed(b["geometry"]["points"])
        (cx, cy), ang, L, Wd = _obb([tuple(p) for p in poly])
        kind = b.get("kind", "")
        floors = int(b.get("floors", 1) or 1)
        wall_h = floors * STOREY_FT
        rtype, pitch = ROOFS.get(kind, ROOFS["default"])
        ridge_h = Wd / 2 * pitch
        tc = bc.get(kind, bc.get("default", {"texture": "shingle"}))
        rtex = fr.pick(tc, rng(b["id"]))
        wtex, wtile = WALLS.get(kind, WALLS["default"])
        floor_z = float(b.get("elevation_ft", bilinear(h, cell, cx, cy)))
        e.update({"polygon": [[r3(p[0]), r3(p[1])] for p in poly], "area_ft2": r3(polygon_area(poly)), "floors": floors,
                  "base_elevation_ft": r3(floor_z), "skirt_depth_ft": r3(float(b.get("site_relief_ft", 0.0)) + 1.0),
                  "wall_height_ft": r3(wall_h), "height_ft": r3(wall_h + ridge_h),
                  "obb": {"center": [r3(cx), r3(cy)], "angle_deg": r3(ang), "length_ft": r3(L), "width_ft": r3(Wd)},
                  "roof": {"type": rtype, "pitch": pitch, "ridge_axis_deg": r3(ang), "ridge_height_ft": r3(ridge_h), "overhang_ft": 1.0,
                           "surface": _surface(tex.tex(rtex), tc.get("tile_ft", 14))},
                  "wall": {"surface": _surface(tex.tex(wtex), wtile)},
                  "site_slope": b.get("site_slope"), "site_relief_ft": b.get("site_relief_ft"),
                  "district": None, "interior": {"json": e["source"], "room_ids": [r.get("id") for r in b.get("rooms", [])],
                                                 "door_ids": [d.get("id") for d in b.get("doors", [])]},
                  "rooms": b.get("rooms", []), "doors": b.get("doors", []),
                  "derived": ["wall_height_ft", "height_ft", "roof", "wall", "skirt_depth_ft", "obb"]})
        dr = [d for d in model.get("details", {}).get("doors", []) if d.get("building") == b["id"]]
        if dr:
            e["openings"] = {"doors": [{"id": d["id"], "point": d["point"], "width_ft": d.get("width_ft"), "facing": d.get("facing")} for d in dr],
                             "windows": "derived at mesh time (worldpack_detail.py)", "wall_thickness_ft": 0.75, "canon": False}
            e["derived"].append("openings")
        ents["buildings"].append(e)
    # ---- districts, plazas, fields, fences
    dists = []
    for d in sorted(model["districts"], key=lambda e: e["id"]):
        poly = _strip_closed(d["geometry"]["points"])
        e = _common(d, place, "districts", srcp("", "districts.json"))
        e.update({"polygon": [[r3(p[0]), r3(p[1])] for p in poly], "area_ft2": r3(polygon_area(poly)), "ring": d.get("ring"),
                  "elevation_ft": d.get("elevation_ft"), "label_point": d.get("label_point")})
        if d.get("kind") == "square":
            pc = types.get("plazas", {}).get("default", {"texture": "cobble", "tile_ft": 14})
            e["base_elevation_ft"] = r3(d.get("elevation_ft", bilinear(h, cell, *np.mean(poly, 0))))
            e["surface"] = _surface(tex.tex(pc["texture"]), pc.get("tile_ft"))
            ents["plazas"].append(e)
        elif d.get("kind") == "field":
            fc = types.get("fields", {})
            crop = d.get("crop") or fr.pick({"textures": fc.get("choose", [["tilled", 1]])}, rng(d["id"]))
            cc = (fc.get("crops") or {}).get(crop, {"texture": crop})
            spec = fr.pick(cc, rng(d["id"]))
            e["crop"] = crop
            e["base_elevation_ft"] = r3(d.get("elevation_ft", bilinear(h, cell, *np.mean(poly, 0))))
            e["surface"] = _surface(tex.tex(spec), cc.get("tile_ft", 40))
            ents["fields"].append(e)
            f = {"id": "fnc_" + d["id"], "name": "Fence of " + d.get("name", d["id"]), "kind": "field_fence", "status": d.get("status", "proposed"),
                 "notes": "derived from the field boundary", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "source": e["source"],
                 "foundry": {"pipelineId": f"world:{place}:fnc_{d['id']}"}, "field": d["id"], "closed": True, "height_ft": FENCE_HEIGHT_FT,
                 "points": [[r3(p[0]), r3(p[1]), r3(bilinear(h, cell, p[0], p[1]))] for p in poly], "derived": ["height_ft", "points"]}
            ents["fences"].append(f)
        else:
            e["surface"] = None
            ents["districts"].append(e)
            dists.append((e, Polygon(poly).buffer(0)))
    for b in ents["buildings"]:
        for d, pg in dists:
            if pg.contains(Point(b["obb"]["center"])):
                b["district"] = d["id"]
                break
    # ---- props (scatter files), lights (lighting config, if one exists)
    sd = os.path.join(model["root"], "scatter")
    for f in sorted(os.listdir(sd)) if os.path.isdir(sd) else []:
        if not f.endswith(".json"):
            continue
        area = os.path.splitext(f)[0]
        doc = _jload(os.path.join(sd, f))
        lst = doc if isinstance(doc, list) else next((doc[k] for k in ("instances", "placements", "items", "points") if isinstance(doc.get(k), list)), [])
        for n, it in enumerate(lst):
            if isinstance(it, (list, tuple)):
                it = {"x": it[0], "y": it[1]}
            x, y = (it["x"], it["y"]) if "x" in it else (it.get("point") or it.get("pos") or [None, None])[:2]
            if x is None:
                continue
            sp = str(it.get("symbol") or it.get("species") or it.get("name") or "tree")
            fid = f"fol_{area}_{n + 1:04d}"
            ents["foliage"].append({"id": fid, "name": sp, "kind": "tree" if "tree" in sp or "oak" in sp or "pine" in sp else "plant", "status": "proposed", "notes": "",
                                    "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "source": srcp("scatter/", f),
                                    "foundry": {"pipelineId": f"world:{place}:{fid}"}, "area": area, "species": slug_id(sp),
                                    "points": [[r3(x), r3(y), r3(it.get("z", bilinear(h, cell, x, y)))]], "scale": float(it.get("scale", 1.0)),
                                    "rotation_deg": float(it.get("rotation", it.get("rot", 0.0))), "height_ft": float(it.get("height_ft", 25.0 * float(it.get("scale", 1.0))))})
    lights_cfg, lsrc = None, None
    for cand in ("lighting.json", "lights.json"):
        p = os.path.join(model["root"], cand)
        if os.path.exists(p):
            lights_cfg, lsrc = _jload(p), srcp("", cand)
            break
    if lights_cfg is None and model["state"].get("lighting"):
        lights_cfg, lsrc = model["state"]["lighting"], f"world/{place}/panel_state.json#lighting"
    if lights_cfg is not None:
        items = lights_cfg.get("lights", []) if isinstance(lights_cfg, dict) else lights_cfg
        for i, l in enumerate(items if isinstance(items, list) else []):
            if not isinstance(l, dict):
                continue
            lid = l.get("id") or f"light_{i + 1:03d}"
            x, y = (l.get("x"), l.get("y")) if "x" in l else (l.get("point") or [None, None])[:2]
            ents["lights"].append({"id": lid, "name": l.get("name", lid), "kind": l.get("kind", "point"), "status": l.get("status", "proposed"), "notes": "",
                                   "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "source": lsrc,
                                   "foundry": {"pipelineId": f"world:{place}:{lid}"},
                                   "position": None if x is None else [r3(x), r3(y), r3(l.get("z", bilinear(h, cell, x, y)))], "config": l})
    # ---- labels (3D tags): one anchor per named entity
    def lab(e, typ, anchor):
        ents["labels"].append({"id": "lbl_" + e["id"], "name": e.get("name", e["id"]), "kind": "label", "status": e.get("status", "proposed"), "notes": "",
                               "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "source": e["source"], "foundry": {"pipelineId": f"world:{place}:lbl_{e['id']}"},
                               "text": e.get("name", e["id"]), "entity": e["id"], "entity_type": typ, "anchor": [r3(v) for v in anchor], "tag_height_ft": 0.0})
    for e in ents["districts"] + ents["plazas"]:
        p = e.get("label_point") or [float(np.mean([q[0] for q in e["polygon"]])), float(np.mean([q[1] for q in e["polygon"]]))]
        lab(e, "districts" if e in ents["districts"] else "plazas", [p[0], p[1], e.get("elevation_ft") or bilinear(h, cell, p[0], p[1])])
    for e in ents["roads"]:
        k = len(e["points"]) // 2
        lab(e, "roads", e["points"][k])
    for e in ents["buildings"]:
        lab(e, "buildings", [e["obb"]["center"][0], e["obb"]["center"][1], e["base_elevation_ft"] + e["height_ft"]])
    for e in ents["water"]:
        pts = e.get("centerline")
        if pts:
            k = len(pts) // 2
            lab(e, "water", [pts[k][0], pts[k][1], e["surface_elevations_ft"][k]])
    # ---- tags: layer / subtype / district / ring / group on every entity
    from shapely.geometry import Point as _P
    def _dist_of(x, y):
        for d, pg in dists:
            if pg.contains(_P(x, y)):
                return d["id"], d.get("ring")
        return None, None
    for t in ENTITY_TYPES:
        for e in ents[t]:
            if t == "buildings":
                x, y = e["obb"]["center"]
            elif "polygon" in e:
                x, y = np.mean(e["polygon"], 0)[:2]
            elif e.get("points"):
                x, y = e["points"][len(e["points"]) // 2][:2]
            elif e.get("position"):
                x, y = e["position"][:2]
            elif e.get("anchor"):
                x, y = e["anchor"][:2]
            else:
                x = y = None
            dist, ring = _dist_of(x, y) if x is not None else (None, None)
            if t == "roads":
                ring = e.get("ring") or ring
            sub = e.get("class") or e.get("kind") or t
            grp = {"buildings": f"buildings:{dist or 'none'}", "roads": f"roads:{sub}", "foliage": f"foliage:{e.get('species', sub)}", "fields": "fields",
                   "labels": "labels"}.get(t, t)
            e["tags"] = {"layer": t, "subtype": sub, "district": dist, "ring": ring, "group": grp, "id": e["id"]}
    # ---- write entity files, materials, manifest
    index = {}
    for t in ENTITY_TYPES:
        rel = f"entities/{t}.json"
        _jdump(os.path.join(out, rel), {"format": FORMAT, "schema_version": SCHEMA_VERSION, "type": t, "units": "feet", "items": ents[t]})
        index[t] = {"file": rel, "count": len(ents[t])}
    mats = tex.write(place, copy_textures)
    mats.append({"id": "mat_terrain_albedo", "name": "terrain_albedo", "kind": "image", "texture": "terrain/albedo.png", "source": None,
                 "sha256": files_sha(out, "terrain/albedo.png"), "mean_color": "#6f9a48", "roughness": 0.95, "metallic": 0.0, "uv": "unit",
                 "foundry": {"pipelineId": f"mat:{place}:terrain_albedo"}})
    for nm, col in (("tree_bark", "#5a4632"), ("tree_leaf", "#3f6b35")) + (tuple((k[4:], v[0]) for k, v in _detail_mats().items()) if any(e.get("openings") for e in ents["buildings"]) else ()):
        mats.append({"id": "mat_" + nm, "name": nm, "kind": "flat", "texture": None, "source": None, "sha256": None, "mean_color": col, "roughness": 0.95,
                     "metallic": 0.0, "foundry": {"pipelineId": f"mat:{place}:{nm}"}})
    dm = _detail_mats()
    for m_ in mats:
        if m_["id"] in dm:
            m_["roughness"] = dm[m_["id"]][1]
            if dm[m_["id"]][2] is not None:
                m_["alpha"] = dm[m_["id"]][2]
    _jdump(os.path.join(out, "materials.json"), {"format": FORMAT, "schema_version": SCHEMA_VERSION, "type": "materials", "materials": mats,
                                                 "note": "texture paths are relative to the pack; 'source' is the repo path they were copied from"})
    vs = model["view"]
    commit, dirty = _git()
    allz = [h.min(), h.max()]
    manifest = {
        "format": FORMAT, "schema_version": SCHEMA_VERSION,
        "place": {"id": pl["id"], "name": pl.get("name", pl["id"]), "kind": pl.get("kind"), "status": pl.get("status")},
        "generated": {"timestamp": timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "git_commit": commit,
                      "git_dirty_inputs": dirty, "tool": "illustrator/generators/worldpack.py", "style": st_name},
        "units": {"length": "feet", "elevation": "feet above the datum (sea_level_ft is the datum's water level)", "ft_to_m": FT_M,
                  "metric_view": "Blender metres, see axes.blender"},
        "axes": {
            "world": {"x": "east, feet", "y": "south (down the page), feet", "z": "up, feet", "origin": "top-left (north-west) corner of the place",
                      "note": "this is the frame of every coordinate in entities/*.json and of terrain pixel rows (row 0 = y 0)"},
            "blender": {"x": "east, metres", "y": "north, metres", "z": "up, metres", "origin": "south-west corner of the place at z_origin_ft",
                        "formula": "X = x_ft * 0.3048; Y = (height_ft - y_ft) * 0.3048; Z = (z_ft - z_origin_ft) * 0.3048"},
            "gltf": {"formula": "(X, Y, Z)_gltf = (X_blender, Z_blender, -Y_blender): Y-up; Blender's importer undoes this",
                     "note": "terrain_lod*.glb already use this frame"},
            "foundry": {"formula": "px = scene_offset + (x_ft - x0_ft) * px_per_ft; py likewise with y (y down, same sense as the world frame)",
                        "tile": "3D Canvas tile centre = centre of the model's footprint in px; model metres: 100 px = 1.524 m; rotation 0 puts Blender north at the canvas top (make-scene.ps1 and item.py, 'verified'; foundry-3d/README says 180: confirm with orientation_test.glb, then change manifest foundry.tile_rotation_deg)"}},
        "origin": {"corner": "north-west", "x_ft": 0.0, "y_ft": 0.0},
        "extent": {"width_ft": W, "height_ft": H, "min": [0.0, 0.0], "max": [W, H], "width_m": r3(W * FT_M), "height_m": r3(H * FT_M)},
        "sea_level_ft": sea, "z_origin_ft": z0,
        "elevation_range_ft": [r3(allz[0]), r3(allz[1])],
        "scale_presets": {"default": vs.get("default_preset"), "page_in": vs.get("page_in"), "presets": vs.get("presets", {})},
        "grid": {"foundry_grid_ft": 5.0, "foundry_grid_px": 5.0 * foundry_px_per_ft, "view_grid_ft": (vs.get("presets", {}).get(vs.get("default_preset", "town"), {}) or {}).get("grid_ft")},
        "foundry": {"px_per_ft": foundry_px_per_ft, "x0_ft": 0.0, "y0_ft": 0.0, "grid_ft": 5.0, "tile_rotation_deg": 0,
                    "pipeline_id_pattern": "world:<place>:<entity id>", "px_per_m": r3(foundry_px_per_ft / FT_M)},
        "terrain": {**{k: v for k, v in terrain.items() if k != "files"}, **terrain["files"]},
        "entities": index, "materials_file": "materials.json",
        "sources": {"style": f"illustrator/presets/town_styles/{st_name}.json", "terrain_source": meta.get("source", "base"),
                    "world_dir": f"world/{place}/", "town_params": f"world/{place}/town_params.json" if os.path.exists(os.path.join(model["root"], "town_params.json")) else None},
    }
    files = {}
    for dp, dn, fn in os.walk(out):
        for f in fn:
            rel = os.path.relpath(os.path.join(dp, f), out).replace("\\", "/")
            if rel != "manifest.json":
                files[rel] = _sha(os.path.join(dp, f))
    manifest["files"] = dict(sorted(files.items()))
    _jdump(os.path.join(out, "manifest.json"), manifest)
    counts = ", ".join(f"{t}={index[t]['count']}" for t in ENTITY_TYPES if index[t]["count"])
    tot = sum(os.path.getsize(os.path.join(out, k)) for k in files)
    log(f"  entities: {counts}; {len(files)} files, {tot / 1e6:.1f} MB")
    return manifest


# ======================================================================================= validation
def _vtype(v, t):
    return {"object": isinstance(v, dict), "array": isinstance(v, list), "string": isinstance(v, str), "boolean": isinstance(v, bool),
            "integer": isinstance(v, int) and not isinstance(v, bool), "null": v is None,
            "number": isinstance(v, (int, float)) and not isinstance(v, bool)}[t]


def schema_errors(doc, schema, root=None, path="$"):
    """Small JSON Schema subset validator (type, enum, const, required, properties, additionalProperties, items, min/maxItems, minimum,
    maximum, pattern, $ref to #/$defs/..., oneOf, anyOf). Used when `jsonschema` is not installed."""
    import re
    root = root or schema
    errs = []
    if "$ref" in schema:
        node = root
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        return schema_errors(doc, node, root, path)
    if "type" in schema:
        ts = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_vtype(doc, t) for t in ts):
            return [f"{path}: expected {'/'.join(ts)}, got {type(doc).__name__}"]
    if "enum" in schema and doc not in schema["enum"]:
        errs.append(f"{path}: {doc!r} not in {schema['enum']}")
    if "const" in schema and doc != schema["const"]:
        errs.append(f"{path}: expected {schema['const']!r}, got {doc!r}")
    if "pattern" in schema and isinstance(doc, str) and not re.search(schema["pattern"], doc):
        errs.append(f"{path}: {doc!r} does not match {schema['pattern']}")
    if isinstance(doc, (int, float)) and not isinstance(doc, bool):
        if "minimum" in schema and doc < schema["minimum"]:
            errs.append(f"{path}: {doc} < minimum {schema['minimum']}")
        if "maximum" in schema and doc > schema["maximum"]:
            errs.append(f"{path}: {doc} > maximum {schema['maximum']}")
    if "oneOf" in schema:
        ok = [s for s in schema["oneOf"] if not schema_errors(doc, s, root, path)]
        if len(ok) != 1:
            errs.append(f"{path}: matches {len(ok)} of oneOf")
    if "anyOf" in schema and all(schema_errors(doc, s, root, path) for s in schema["anyOf"]):
        errs.append(f"{path}: matches none of anyOf")
    if isinstance(doc, dict):
        for k in schema.get("required", []):
            if k not in doc:
                errs.append(f"{path}: missing required '{k}'")
        props = schema.get("properties", {})
        for k, v in doc.items():
            if k in props:
                errs += schema_errors(v, props[k], root, f"{path}.{k}")
            elif schema.get("additionalProperties") is False:
                errs.append(f"{path}: unexpected '{k}'")
            elif isinstance(schema.get("additionalProperties"), dict):
                errs += schema_errors(v, schema["additionalProperties"], root, f"{path}.{k}")
    if isinstance(doc, list):
        if "minItems" in schema and len(doc) < schema["minItems"]:
            errs.append(f"{path}: fewer than {schema['minItems']} items")
        if "maxItems" in schema and len(doc) > schema["maxItems"]:
            errs.append(f"{path}: more than {schema['maxItems']} items")
        if "items" in schema:
            for i, v in enumerate(doc):
                errs += schema_errors(v, schema["items"], root, f"{path}[{i}]")
    return errs


def validate_pack(path, check_files=True):
    """Returns a list of error strings (empty = valid): JSON Schema for manifest / entity files / materials, then integrity checks
    (files and checksums, heightmap size, unique ids, material references, polygon and elevation sanity)."""
    root = os.path.dirname(path) if os.path.basename(path) == "manifest.json" else path
    errs = []
    schema = _jload(SCHEMA_PATH)

    def chk(doc, name, where):
        try:
            import jsonschema
            v = jsonschema.Draft202012Validator({"$ref": f"#/$defs/{name}", "$defs": schema["$defs"]})
            errs.extend(f"{where}: {'/'.join(map(str, e.absolute_path))}: {e.message}" for e in v.iter_errors(doc))
        except ImportError:
            errs.extend(f"{where}: {e}" for e in schema_errors(doc, {"$ref": f"#/$defs/{name}"}, schema))
    mp = os.path.join(root, "manifest.json")
    if not os.path.exists(mp):
        return [f"{mp} missing"]
    m = _jload(mp)
    chk(m, "manifest", "manifest.json")
    if errs:
        return errs
    if check_files:
        for rel, sha in m["files"].items():
            p = os.path.join(root, rel)
            if not os.path.exists(p):
                errs.append(f"{rel}: listed in manifest but missing")
            elif _sha(p) != sha:
                errs.append(f"{rel}: checksum mismatch (edited after export?)")
    t = m["terrain"]
    bp = os.path.join(root, t["heights_bin"])
    if os.path.exists(bp) and os.path.getsize(bp) != t["nx"] * t["ny"] * 4:
        errs.append(f"{t['heights_bin']}: size {os.path.getsize(bp)} != nx*ny*4")
    if abs((t["nx"] - 1) * t["cell_ft"] - t["size_ft"][0]) > 1e-6 or abs((t["ny"] - 1) * t["cell_ft"] - t["size_ft"][1]) > 1e-6:
        errs.append("terrain: (n-1)*cell_ft does not equal size_ft")
    mats = {}
    mf = os.path.join(root, m["materials_file"])
    if os.path.exists(mf):
        md = _jload(mf)
        chk(md, "materialsFile", m["materials_file"])
        mats = {x["id"]: x for x in md.get("materials", [])}
        for mid, x in mats.items():
            if x.get("texture") and not os.path.exists(os.path.join(root, x["texture"])):
                errs.append(f"{mid}: texture {x['texture']} missing")
    seen = {}
    for typ, info in m["entities"].items():
        p = os.path.join(root, info["file"])
        if not os.path.exists(p):
            errs.append(f"{info['file']} missing")
            continue
        doc = _jload(p)
        chk(doc, "entityFile", info["file"])
        chk_item = {"roads": "road", "buildings": "building", "plazas": "areaEntity", "fields": "areaEntity", "districts": "areaEntity", "water": "waterEntity",
                    "fences": "fence", "labels": "label", "foliage": "foliage"}.get(typ)
        if len(doc["items"]) != info["count"]:
            errs.append(f"{info['file']}: count {len(doc['items'])} != manifest {info['count']}")
        for e in doc["items"]:
            where = f"{typ}:{e.get('id')}"
            if chk_item:
                chk(e, chk_item, where)
            if e.get("id") in seen:
                errs.append(f"{where}: duplicate id (also in {seen[e['id']]})")
            seen[e.get("id")] = typ
            for sfc in [e.get("surface"), (e.get("roof") or {}).get("surface"), (e.get("wall") or {}).get("surface")]:
                if sfc and sfc["material"] not in mats:
                    errs.append(f"{where}: material {sfc['material']} not in materials.json")
            for key in ("polygon", "outline"):
                if key in e and polygon_area(e[key]) <= 0:
                    errs.append(f"{where}: {key} has zero area")
            if typ == "roads" and len(e["points"]) < 2:
                errs.append(f"{where}: fewer than 2 points")
            if typ == "buildings" and e["height_ft"] < e["wall_height_ft"]:
                errs.append(f"{where}: height_ft below wall_height_ft")
            if typ in ("roads", "fences", "labels"):
                zs = [p[2] for p in e.get("points", e.get("anchor") and [e["anchor"]] or [])]
                for z in zs:
                    if not (-1e5 < z < 1e5):
                        errs.append(f"{where}: elevation {z} out of range")
    return errs


# ======================================================================================= CLI
def _resolve_dir(a):
    if a.path:
        return a.path
    return os.path.join(REPO, "world", a.place, "export")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export", help="write the pack")
    e.add_argument("--place", default="bridgehollow")
    e.add_argument("--out", help="output folder (default world/<place>/export)")
    e.add_argument("--world-root", help="read world data from this folder instead of <repo>/world")
    e.add_argument("--lod", default="1,4", help="terrain mesh steps in heightmap cells, comma list (1 = full resolution)")
    e.add_argument("--terrain-source", choices=list(("auto", "base", "patched", "carved")))
    e.add_argument("--style", help="town style json (default: panel_state town.fills.style or full_map)")
    e.add_argument("--phases", help="terrain phase file for splat/albedo (default: panel_state shading, else alpine_steep)")
    e.add_argument("--splat-cell-ft", type=float, default=SPLAT_CELL_FT)
    e.add_argument("--albedo-px-per-ft", type=float, default=ALBEDO_PX_PER_FT)
    e.add_argument("--px-per-ft", type=float, default=20.0, help="Foundry px per foot (100 px grid / 5 ft = 20)")
    e.add_argument("--z-origin-ft", type=float, help="elevation mapped to Blender Z = 0 (default: terrain minimum floored to 10 ft)")
    e.add_argument("--timestamp", help="pin manifest generated.timestamp (for byte-identical exports)")
    e.add_argument("--no-textures", action="store_true", help="reference repo textures instead of copying them")
    v = sub.add_parser("validate", help="schema + integrity check")
    v.add_argument("--place", default="bridgehollow")
    v.add_argument("--path")
    i = sub.add_parser("info", help="print a pack summary")
    i.add_argument("--place", default="bridgehollow")
    i.add_argument("--path")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        m = export_world(a.place, a.out, lod=[int(x) for x in a.lod.split(",") if x], world_root=a.world_root, terrain_source=a.terrain_source, style=a.style,
                         phases_path=a.phases, splat_cell_ft=a.splat_cell_ft, albedo_px_per_ft=a.albedo_px_per_ft, foundry_px_per_ft=a.px_per_ft,
                         z_origin_ft=a.z_origin_ft, timestamp=a.timestamp, copy_textures=not a.no_textures)
        out = a.out or os.path.join(a.world_root or os.path.join(REPO, "world"), a.place, "export")
        errs = validate_pack(out)
        print("validate:", "OK" if not errs else f"{len(errs)} problem(s)")
        for x in errs[:20]:
            print("  ", x)
        return 1 if errs else 0
    d = _resolve_dir(a)
    if a.cmd == "validate":
        errs = validate_pack(d)
        print(f"{d}: " + ("valid" if not errs else f"{len(errs)} problem(s)"))
        for x in errs[:50]:
            print("  ", x)
        return 1 if errs else 0
    p = load_pack(d)
    print(json.dumps({"place": p.place, "schema": p.manifest["schema_version"], "extent_ft": [p.frame.width_ft, p.frame.height_ft],
                      "entities": {t: len(v) for t, v in p.entities.items()}, "generated": p.manifest["generated"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
