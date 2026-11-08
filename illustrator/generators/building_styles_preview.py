"""Preview sheet for building style presets: builds one sample building per preset (real pipeline: apply_style -> build_building_detailed -> GLB),
renders each with Blender (foundry-3d/blender/style_preview.py) and composes `sheet.png`.

  python illustrator/generators/building_styles_preview.py build  [--out illustrator/out/building_styles] [--only tudor,windmill] [--pack world/<place>/export]
  python illustrator/generators/building_styles_preview.py render [--out ...] [--only ...]        (Blender 5.x on PATH or --blender)
  python illustrator/generators/building_styles_preview.py sheet  [--out ...]                      (PNG contact sheet with labels)
"""
import argparse
import copy
import json
import math
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import building_styles as bs  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

DEFAULT_PACK = os.path.join(REPO, "world", "bridgehollow__dyers_walk_local", "export")
SAMPLE = {"house": (20.0, 14.0, 1), "town": (30.0, 18.0, 2), "church": (40.0, 20.0, 2), "other": (22.0, 14.0, 1)}
SAMPLE_OVERRIDE = {"tudor": (24, 15, 2), "town_inn": (34, 20, 2), "hanseatic_brick": (22, 15, 2), "windmill": (13, 13, 1), "chapel": (26, 14, 2), "parish_church": (44, 20, 2),
                   "stave_church": (32, 18, 1), "niedersachsen_halle": (40, 22, 1), "farm_longhouse": (42, 16, 1), "danish_longhouse": (30, 13, 1), "danish_fachwerk": (24, 14, 2),
                   "town_warehouse": (28, 18, 3), "town_guildhall": (36, 20, 2), "town_gatehouse": (20, 16, 3), "well_house": (9, 9, 1), "falu_cottage": (22, 13, 1)}


def sample_entity(pack, pid, tmpl):
    L, W, fl = SAMPLE_OVERRIDE.get(pid) or SAMPLE[bs.load_presets()[pid].get("category", "house")]
    e = copy.deepcopy(tmpl)
    for k in ("layout", "rooms", "doors", "interior"):
        e.pop(k, None)
    cx, cy = 120.0, 120.0
    poly = [[cx - L / 2, cy - W / 2], [cx + L / 2, cy - W / 2], [cx + L / 2, cy + W / 2], [cx - L / 2, cy + W / 2]]
    e.update({"id": f"sample_{pid}", "name": pid, "polygon": poly, "floors": fl, "wall_height_ft": 10.0 * fl, "skirt_depth_ft": 1.0, "base_elevation_ft": pack.frame.z_origin_ft + 10.0,
              "obb": {"center": [cx, cy], "angle_deg": 0.0, "length_ft": L, "width_ft": W}, "style": pid, "kind": "house", "district": "dis_sample"})
    e["roof"] = {"type": "gable", "pitch": 0.6, "ridge_axis_deg": 0.0, "ridge_height_ft": W / 2 * 0.6, "overhang_ft": 1.0, "surface": {"material": "mat_shingle", "tile_ft": 14}}
    e["wall"] = {"surface": {"material": "mat_plank", "tile_ft": 8}}
    dx = cx - L * 0.25
    e["openings"] = {"doors": [{"id": f"sample_{pid}_door", "point": [dx, cy + W / 2], "width_ft": 3.5, "facing": [0, 1]}], "windows": "derived", "wall_thickness_ft": 0.75, "canon": False}
    e["tags"] = dict(e.get("tags") or {}, id=e["id"])
    return e


def build(out, only=None, pack_dir=DEFAULT_PACK, entities=None):
    pack = wp.load_pack(pack_dir)
    pbr.prepare(pack.materials)
    tmpl = pack.list("buildings")[0]
    cx = wm.Ctx(pack)
    gdir = os.path.join(out, "glb")
    os.makedirs(gdir, exist_ok=True)
    ids = only or list(bs.load_presets())
    items = entities or [sample_entity(pack, pid, tmpl) for pid in ids]
    for e in items:
        e = bs.apply_style(e)
        bs.register_materials(pack.materials, e["_style"])
        m, dn = wd.build_building_detailed(cx, e)
        lo, hi = m.bbox()
        piv = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        nodes = [(e["id"], m.translated([-piv[0], -piv[1], -piv[2]]), {})]
        for d in dn:
            nodes.append((d["id"], d["mesh"], {"_t": tuple(np_sub(d["hinge"], piv)), **d["extras"]}))
        wm.write_glb(os.path.join(gdir, e["id"] + ".glb"), nodes, pack.materials, textures="external", tex_root=os.path.join(gdir, "textures"), tex_prefix="textures/")
        print("built", e["id"], m.tri_count, "tris", flush=True)
    pbr.install(pack, os.path.join(gdir, "textures"))
    return [e["id"] for e in items]


def np_sub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def find_blender(arg=None):
    for p in (arg, os.environ.get("BLENDER"), r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe", r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe",
              r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe", r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe", "blender"):
        if p and (os.path.exists(p) or p == "blender"):
            return p
    return "blender"


def render(out, only=None, blender=None, size=(900, 680)):
    gdir = os.path.join(out, "glb")
    ids = [f"sample_{p}" for p in (only or bs.load_presets())]
    cmd = [find_blender(blender), "-b", "--factory-startup", "--python", os.path.join(REPO, "foundry-3d", "blender", "style_preview.py"), "--", gdir, out, ",".join(ids), str(size[0]), str(size[1])]
    subprocess.run(cmd, check=True)


def sheet(out, cols=5, thumb=(440, 330)):
    from PIL import Image, ImageDraw, ImageFont
    pres = bs.load_presets()
    order = {"house": 0, "town": 1, "church": 2, "other": 3}
    ids = sorted([p for p in pres if os.path.exists(os.path.join(out, f"sample_{p}.png"))], key=lambda p: (order.get(pres[p].get("category"), 9), pres[p]["name"]))
    rows = math.ceil(len(ids) / cols)
    W, H = cols * thumb[0], rows * (thumb[1] + 34)
    im = Image.new("RGB", (W, H), (30, 30, 34))
    dr = ImageDraw.Draw(im)
    try:
        f1 = ImageFont.truetype("arial.ttf", 17)
        f2 = ImageFont.truetype("arial.ttf", 12)
    except Exception:
        f1 = f2 = ImageFont.load_default()
    for k, pid in enumerate(ids):
        x, y = (k % cols) * thumb[0], (k // cols) * (thumb[1] + 34)
        t = Image.open(os.path.join(out, f"sample_{pid}.png")).convert("RGB").resize(thumb, Image.LANCZOS)
        im.paste(t, (x, y + 34))
        dr.text((x + 8, y + 4), pres[pid]["name"], fill=(240, 236, 224), font=f1)
        dr.text((x + 8, y + 22), f"{pid}  |  {pres[pid].get('category')}  |  {pres[pid].get('culture')}", fill=(160, 160, 160), font=f2)
        t.save(os.path.join(out, f"{pid}.png")) if False else None
    im.save(os.path.join(out, "sheet.png"), optimize=True)
    # per-style previews (referenced by the preset json "preview") at panel size
    for pid in ids:
        Image.open(os.path.join(out, f"sample_{pid}.png")).convert("RGB").resize((360, 272), Image.LANCZOS).save(os.path.join(out, f"{pid}.png"), optimize=True)
    return os.path.join(out, "sheet.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "render", "sheet", "all"])
    ap.add_argument("--out", default=os.path.join(REPO, "illustrator", "out", "building_styles"))
    ap.add_argument("--only")
    ap.add_argument("--pack", default=DEFAULT_PACK)
    ap.add_argument("--blender")
    a = ap.parse_args()
    only = a.only.split(",") if a.only else None
    if a.cmd in ("build", "all"):
        build(a.out, only, a.pack)
    if a.cmd in ("render", "all"):
        render(a.out, only, a.blender)
    if a.cmd in ("sheet", "all"):
        print(sheet(a.out))


if __name__ == "__main__":
    main()
