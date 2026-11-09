"""Preview + geometry stats of the home interior styles (interior_styles.py): builds one sample house per style through the real pipeline
(interiors.generate_layout -> worldpack_detail.build_building_detailed -> worldpack_interiors.add_interior), prints / writes triangle counts per node and
material, and renders a cutaway sheet (roof removed, top-down oblique, textured per triangle) with a small numpy / PIL painter's-algorithm rasteriser.
No Blender and little memory (a few thousand triangles per house).

  python illustrator/generators/interior_styles_preview.py [--out illustrator/out/interior_styles] [--floors 1] [--only rustic_cottage,plain] [--kind house]
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import interior_styles as ist  # noqa: E402
import interiors as I  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_interiors as wi  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

FT = wi.FT


def make_ctx():
    import types
    import worldpack as wp
    import worldpack_mesh as wm
    fr = wp.Frame(100, 80, 0.0)
    pack = types.SimpleNamespace(frame=fr, heights=np.zeros((9, 11), np.float32), cell_ft=10.0, manifest={"foundry": {}})
    return wm.Ctx(pack)


def sample_entity(floors=1, kind="house", style=None, poly=None, door=None, bid="bld_sample"):
    poly = poly or [[30, 20], [58, 20], [58, 38], [30, 38]]
    door = door or [44, 38]
    cxy = [sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly)]
    b = {"id": bid, "kind": kind, "floors": floors, "polygon": poly, "obb": {"center": cxy, "angle_deg": 0.0}}
    d = [{"id": bid + "_door1", "point": list(door), "width_ft": 3.5, "facing": [0, 1]}]
    L = I.generate_layout(b, d)
    e = {"id": bid, "kind": kind, "polygon": poly, "base_elevation_ft": 0.0, "skirt_depth_ft": 1.0, "floors": floors, "wall_height_ft": 10.0 * floors, "height_ft": 10.0 * floors + 4,
         "obb": {"center": cxy, "angle_deg": 0.0, "length_ft": poly[1][0] - poly[0][0], "width_ft": poly[2][1] - poly[1][1]},
         "roof": {"type": "gable", "pitch": 0.6, "ridge_height_ft": 4.2, "overhang_ft": 1.0, "surface": {"material": "mat_shingle", "tile_ft": 14}},
         "wall": {"surface": {"material": "mat_plank", "tile_ft": 8}}, "openings": {"doors": d}, "rooms": L["rooms"], "doors": L["doors"],
         "layout": {k: v for k, v in L.items() if k not in ("rooms", "doors")}}
    if style:
        e["interior_style"] = style
    return e


def build_sample(style, floors=1, kind="house", **kw):
    """-> (nodes [(name, Mesh, extras)], entity). Style is set per building (interior_style key)."""
    cx = make_ctx()
    e = sample_entity(floors, kind, style, **kw)
    m, dn = wd.build_building_detailed(cx, e)
    full, doors, extra = wi.add_interior(cx, e, m, dn)
    return extra["layered_nodes"], e


def stats(nodes):
    per_node = {n: mm.tri_count for n, mm, _ in nodes}
    mats = {}
    for _, mm, _ in nodes:
        for k, F in mm.subs.items():
            mats[k] = mats.get(k, 0) + len(F)
    interior = sum(c for n, c in per_node.items() if "_int_" in n or "_props_" in n)
    return {"total_tris": sum(per_node.values()), "interior_tris": interior, "nodes": per_node, "materials": dict(sorted(mats.items(), key=lambda kv: -kv[1]))}


# ------------------------------------------------------------------ preview rasteriser
_TEX = {}


def _tex(mid):
    if mid not in _TEX:
        try:
            bt = pbr.base_texture(mid)
        except Exception:
            bt = None
        if bt is not None:
            _TEX[mid] = np.clip(bt[0], 0, 255).reshape(-1, 3).mean(0).reshape(1, 1, 3)      # mean colour: per-triangle texture sampling is too noisy at this scale
        else:
            col = wd.DETAIL_MATS.get(mid, ("#a8a090",))[0]
            _TEX[mid] = np.array([[[int(col[i:i + 2], 16) for i in (1, 3, 5)]]], float)
    return _TEX[mid]


def render(nodes, path, size=(900, 620), yaw=28.0, pitch=58.0, hide=("roof",), title=""):
    from PIL import Image, ImageDraw
    tris, cols = [], []
    for name, mm, ex in nodes:
        if any(h in (ex.get("tags") or []) for h in hide):
            continue
        for mid, F in mm.subs.items():
            tex = _tex(mid)
            th, tw = tex.shape[:2]
            for f in F:
                P = mm.V[f]
                uv = mm.UV[f].mean(0)
                c = tex[int((uv[1] % 1.0) * th) % th, int((uv[0] % 1.0) * tw) % tw]
                tris.append(P)
                cols.append((c, mid))
    T = np.array(tris)
    a, b = math.radians(yaw), math.radians(pitch)
    cam = np.array([math.cos(b) * math.sin(a), -math.cos(b) * math.cos(a), math.sin(b)])     # direction from the scene toward the camera (Blender frame, z up)
    right = np.cross([0, 0, 1.0], cam)
    right /= np.linalg.norm(right)
    up = np.cross(cam, right)
    Q = T.reshape(-1, 3) @ np.stack([right, up, cam], 1)                 # x right, y up on screen, z toward the viewer
    Q = Q.reshape(-1, 3, 3)
    ctr = Q.reshape(-1, 3).mean(0)
    Q = Q - ctr
    n = np.cross(Q[:, 1] - Q[:, 0], Q[:, 2] - Q[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    n = n * np.sign(n[:, 2:3] + 1e-9)                              # two-sided: face the viewer
    light = np.array([-0.35, 0.45, 0.82])
    shade = 0.45 + 0.55 * np.clip(n @ light / np.linalg.norm(light), 0, 1)
    order = np.argsort(Q[:, :, 2].mean(1))
    ext = np.abs(Q[:, :, :2]).max()
    sc = min(size[0], size[1]) * 0.47 / ext
    im = Image.new("RGB", size, (58, 62, 70))
    dr = ImageDraw.Draw(im)
    for i in order:
        c = cols[i][0] * shade[i]
        pts = [(size[0] / 2 + p[0] * sc, size[1] / 2 - p[1] * sc) for p in Q[i]]
        dr.polygon(pts, fill=tuple(int(max(0, min(255, v))) for v in c))
    if title:
        dr.text((10, 8), title, fill=(240, 240, 240))
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    im.save(path)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=os.path.join(REPO, "illustrator", "out", "interior_styles"))
    ap.add_argument("--floors", type=int, default=1)
    ap.add_argument("--kind", default="house")
    ap.add_argument("--only")
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args(argv)
    names = a.only.split(",") if a.only else ist.names()
    os.makedirs(a.out, exist_ok=True)
    res, shots = {}, []
    for nm in names:
        nodes, e = build_sample(nm, a.floors, a.kind)
        st = stats(nodes)
        res[nm] = st
        print(f"{nm:20s} total {st['total_tris']:6d} tris, interior {st['interior_tris']:6d}")
        if not a.no_render:
            p = os.path.join(a.out, f"{nm}_f{a.floors}.png")
            render(nodes, p, title=f"{nm} ({ist.get(nm)['label']}) {st['total_tris']} tris")
            shots.append(p)
    json.dump(res, open(os.path.join(a.out, f"stats_f{a.floors}.json"), "w"), indent=1)
    if shots and len(shots) > 1:
        from PIL import Image
        ims = [Image.open(p) for p in shots]
        w, h = ims[0].size
        cols = 2
        rows = (len(ims) + 1) // 2
        sheet = Image.new("RGB", (w * cols, h * rows))
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet.save(os.path.join(a.out, f"sheet_f{a.floors}.png"))


if __name__ == "__main__":
    main()
