"""Look-dev renders of REAL buildings of a place's world pack with a chosen building style (or the legacy look), one GLB per building, rendered
headless in Blender from several angles (foundry-3d/blender/style_look.py), plus a labelled contact sheet. Light on memory: one building at a time.

  python illustrator/generators/building_styles_look.py --ids bld_house_101,bld_inn --style keep|none|<preset id> --tag after [--snow-ground] [--views threeq,back,street,aerial]
       [--pack world/bridgehollow/export] [--out illustrator/out/building_styles_look] [--sheet name.png]
--style keep = the building json's own style (from world/<place>/buildings/<id>.json, else none), none = legacy look, <id> = that preset for every building.
Prints the triangle count of every building (shell + style geometry, door leaf excluded).
"""
import argparse
import copy
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

import building_styles as bs  # noqa: E402
import building_styles_preview as bsp  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_detail as wd  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

DEFAULT_PACK = os.path.join(REPO, "world", "bridgehollow", "export")
DEFAULT_OUT = os.path.join(REPO, "illustrator", "out", "building_styles_look")


def build(pack_dir, ids, style, tag, out):
    pack = wp.load_pack(pack_dir)
    pbr.prepare(pack.materials)
    cx = wm.Ctx(pack)
    gdir = os.path.join(out, "glb")
    os.makedirs(gdir, exist_ok=True)
    used, names, tris = set(), [], {}
    place = pack.manifest.get("place") or os.path.basename(os.path.dirname(os.path.abspath(pack_dir)))
    byid = {e["id"]: e for e in pack.list("buildings")}
    for bid in ids:
        e = copy.deepcopy(byid[bid])
        if style == "keep":
            p = os.path.join(REPO, "world", place, "buildings", bid + ".json")
            st = json.load(open(p, encoding="utf-8")).get("style") if os.path.exists(p) else None
        else:
            st = None if style == "none" else style
        e.pop("style", None)
        if st:
            e["style"] = st
            e = bs.apply_style(e)
            if e.get("_style"):
                bs.register_materials(pack.materials, e["_style"])
        m, dn = wd.build_building_detailed(cx, e)
        lo, hi = m.bbox()
        piv = ((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2])
        nodes = [(e["id"], m.translated([-piv[0], -piv[1], -piv[2]]), {})]
        for d in dn:
            nodes.append((d["id"], d["mesh"], {"_t": tuple(bsp.np_sub(d["hinge"], piv)), **d["extras"]}))
            used |= set(d["mesh"].subs)
        used |= set(m.subs)
        name = f"{tag}_{bid}"
        wm.write_glb(os.path.join(gdir, name + ".glb"), nodes, pack.materials, textures="external", tex_root=os.path.join(gdir, "textures"), tex_prefix="textures/")
        tris[bid] = m.tri_count
        names.append(name)
        with open(os.path.join(gdir, name + ".json"), "w") as f:                 # floor height above the pivot: the render puts its ground there
            json.dump({"floor_m": (e["base_elevation_ft"] - cx.fr.z_origin_ft) * wm.FT - piv[2]}, f)
        print(f"built {name} style={st or 'legacy'} {m.tri_count} tris", flush=True)
    tdir = os.path.join(gdir, "textures")
    os.makedirs(tdir, exist_ok=True)
    for mid in sorted(used):                                 # every texture the GLBs reference (base images too: no pack folder next to them)
        if mid in pack.materials and pack.materials[mid].get("texture"):
            pbr.write_material_textures(mid, tdir, overwrite_base=True)
    return names, tris


def render(out, names, views, snow_ground=False, size=(960, 720), blender=None):
    env = dict(os.environ, LOOK_VIEWS=",".join(views), LOOK_GROUND="snow" if snow_ground else "grass")
    cmd = [bsp.find_blender(blender), "-b", "--factory-startup", "--python", os.path.join(REPO, "foundry-3d", "blender", "style_look.py"), "--",
           os.path.join(out, "glb"), out, ",".join(names), str(size[0]), str(size[1])]
    subprocess.run(cmd, check=True, env=env, stdout=subprocess.DEVNULL)


def sheet(out, rows, path, labels=None, thumb=(480, 360)):
    """rows = [[png name, ...], ...] -> one labelled PNG."""
    from PIL import Image, ImageDraw, ImageFont
    cols = max(len(r) for r in rows)
    W, H = cols * thumb[0], len(rows) * (thumb[1] + 26)
    im = Image.new("RGB", (W, H), (28, 28, 32))
    dr = ImageDraw.Draw(im)
    try:
        f = ImageFont.truetype("arial.ttf", 15)
    except Exception:
        f = ImageFont.load_default()
    for r, row in enumerate(rows):
        for c, name in enumerate(row):
            p = os.path.join(out, name)
            if not os.path.exists(p):
                continue
            x, y = c * thumb[0], r * (thumb[1] + 26)
            im.paste(Image.open(p).convert("RGB").resize(thumb, Image.LANCZOS), (x, y + 26))
            dr.text((x + 6, y + 5), (labels or {}).get(name, name[:-4]), fill=(236, 232, 220), font=f)
    im.save(path, optimize=True)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--style", default="keep")
    ap.add_argument("--tag", default="look")
    ap.add_argument("--views", default="threeq,back,street")
    ap.add_argument("--snow-ground", action="store_true")
    ap.add_argument("--pack", default=DEFAULT_PACK)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--blender")
    a = ap.parse_args()
    names, tris = build(a.pack, a.ids.split(","), a.style, a.tag, a.out)
    if not a.no_render:
        render(a.out, names, a.views.split(","), a.snow_ground, blender=a.blender)
    print(json.dumps({"tris": tris}))


if __name__ == "__main__":
    main()
