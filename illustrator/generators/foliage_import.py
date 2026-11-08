"""Imported third-party tree meshes (Baileywiki 3D models from our Foundry data) as foliage species.

Source: http://VEGA:30000/baileywiki-content/assets/modules/baileywiki-3d/models/... (Draco glTF; dumped with foundry-3d/blender/dump_gltf_npz.py into
presets/foliage/imported/*.npz, textures resized into the shared atlas by foliage_mesh.write_atlas). Private use only (never distributed).

A species with gen {"type": "glb", "file": "<name>.npz", "parts": [{"mat": i, "tile": "<atlas tile>", "kind": "leaf"|"bark"|"skip", "uv": "direct"|"wrap"}]}
loads the dump, re-scales it to the species' nominal height (mean height_ft), puts the pivot at the trunk base (z = 0 at the ground, xy = mean xy of the
lowest bark vertices), drops triangles below the ground, gives leaf cards spherical normals + AO vertex colour, and builds LODs:
  LOD0 full, LOD1 ~40% of the leaf cards + flat bark colour, LOD2 handled by foliage_mesh (crossed impostor).
Bark UVs of the originals tile many times (wrap): they are folded per triangle into the single bark tile of the atlas (clamped).
"""
import math
import os
import zlib

import numpy as np

import worldpack_mesh as wm

HERE = os.path.dirname(os.path.abspath(__file__))
IMPORTED = os.path.join(HERE, "..", "presets", "foliage", "imported")
FT = 0.3048
_cache = {}


def _load(name):
    if name not in _cache:
        _cache[name] = np.load(os.path.join(IMPORTED, name), allow_pickle=False)
    return _cache[name]


def load_imported(sp, lod):
    import foliage_mesh as fm
    g = sp["gen"]
    d = _load(g["file"])
    nominal = float(np.mean(sp["height_ft"])) * FT
    parts = g["parts"]
    bark_parts = [p for p in parts if p["kind"] == "bark"]
    allv = np.concatenate([d[f"V{p['mat']}"] for p in parts if p["kind"] != "skip"])
    zmin = max(float(allv[:, 2].min()), 0.0) if g.get("ground_z0", True) else float(allv[:, 2].min())
    zmax = float(allv[:, 2].max())
    scale = nominal / max(zmax - zmin, 1e-3)
    if bark_parts:
        bv = np.concatenate([d[f"V{p['mat']}"] for p in bark_parts])
        low = bv[bv[:, 2] <= bv[:, 2].min() + 0.4]
        ox, oy = float(low[:, 0].mean()), float(low[:, 1].mean())
    else:
        ox, oy = float(allv[:, 0].mean()), float(allv[:, 1].mean())
    rng = np.random.default_rng(zlib.crc32(sp["id"].encode()))
    Vs, UVs, Ns, Cs, Fs, off = [], [], [], [], [], 0
    cx, cy = 0.0, 0.0
    cz_mid = (zmax - zmin) * scale * 0.6
    crown_r = max(float(np.ptp(allv[:, 0])), float(np.ptp(allv[:, 1]))) * scale * 0.5
    crown = fm._Crown((0, 0, cz_mid), crown_r, (zmax - zmin) * scale * 0.4, zmin * scale, (zmax) * scale, ao_min=0.5)
    for p in parts:
        if p["kind"] == "skip":
            continue
        i = p["mat"]
        V = (d[f"V{i}"] - np.array([ox, oy, zmin])) * scale
        UV = d[f"UV{i}"].copy()
        N = d[f"N{i}"].copy()
        F = d[f"F{i}"].copy()
        keep = np.ones(len(F), bool)
        if p["kind"] == "leaf" and lod >= 1:
            pairs = np.arange(len(F)) // 2
            h = ((pairs * 2654435761) % 1000) / 1000.0
            keep = h < float(g.get("lod1_keep", 0.4))
        below = (V[F][:, :, 2] < -0.05).all(axis=1)
        keep &= ~below
        F = F[keep]
        if not len(F):
            continue
        if p["kind"] == "bark":
            if lod >= 1:
                UV = np.full_like(UV, 0.5)
            elif p.get("uv", "wrap") == "wrap":
                tri_uv = UV[F]
                fl = np.floor(tri_uv.min(axis=1))                      # fold each triangle into [0,1] using its own offset
                UVf = np.zeros_like(UV)
                # vertices are shared between triangles; accumulate the folded value of the first triangle that uses them
                seen = np.zeros(len(UV), bool)
                for t in range(len(F)):
                    for k in range(3):
                        v = F[t, k]
                        if not seen[v]:
                            UVf[v] = tri_uv[t, k] - fl[t]
                            seen[v] = True
                UV = np.clip(UVf, 0.0, 1.0)
        else:
            UV = np.clip(UV, 0.0, 1.0)
        # remap into the atlas tile
        UVa = np.array([fm.tile_uv(p["tile"], u, v) for u, v in UV]) if len(UV) else UV
        used = np.unique(F)
        remap = -np.ones(len(V), np.int64)
        remap[used] = np.arange(len(used))
        Vk, UVk, Nk = V[used], UVa[used], N[used]
        Fk = remap[F]
        if p["kind"] == "bark" and lod >= 1:                          # far bark: vertex-cluster the 17k-triangle branch mesh
            m = wm.cluster_decimate(wm.Mesh(Vk, UVk, {"b": Fk}, True), float(g.get("bark_cell_m", 0.45)))
            Vk, UVk, Fk = m.V, m.UV, m.subs["b"] if m.subs else np.zeros((0, 3), np.int64)
            Nk = wm._smooth_normals(Vk, Fk) if len(Fk) else np.zeros_like(Vk)
        if p["kind"] == "leaf":
            sph = np.array([crown.nrm(v) for v in Vk])
            Nk = 0.65 * sph + 0.35 * Nk
            C = np.array([crown.col(v) for v in Vk])
            C = C * (0.9 + 0.2 * rng.random((len(Vk), 1)))
            C = np.hstack([C, np.ones((len(C), 1))])
        else:
            hz = np.clip(Vk[:, 2] / max(nominal * 0.4, 1e-3), 0, 1)
            C = np.hstack([np.repeat((0.55 + 0.45 * hz)[:, None], 3, 1), np.ones((len(Vk), 1))])
        Vs.append(Vk)
        UVs.append(UVk)
        Ns.append(Nk)
        Cs.append(C)
        Fs.append(Fk + off)
        off += len(Vk)
    V = np.concatenate(Vs)
    sub = {"leaf": np.concatenate(Fs)}
    return wm.Mesh(V, np.concatenate(UVs), sub, True, np.concatenate(Ns), np.concatenate(Cs))
