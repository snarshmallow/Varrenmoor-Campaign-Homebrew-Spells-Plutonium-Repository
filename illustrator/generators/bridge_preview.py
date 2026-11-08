"""Preview renders of the bridge presets (Blender): a free-standing sample per preset over a small valley with a stream (or a road) in the bottom.

  python illustrator/generators/bridge_preview.py render [--out illustrator/out/bridges] [--only stone_arch,...] [--span-ft 60] [--views threeq,under]
  python illustrator/generators/bridge_preview.py sheet  [--out ...]      # compose sheet.png from the renders

Writes <out>/glb/<preset>.glb (+ textures/), <out>/<preset>_<view>.png, <out>/sheet.png and <out>/thumbs/<preset>.png (used by the panel).
"""
import argparse
import json
import os
import subprocess
import sys
import types

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import bridge_maker as bm  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_pbr as pbr  # noqa: E402

REPO = bm.REPO
FT = bm.FT
OUT = os.path.join(REPO, "illustrator", "out", "bridges")


def find_blender(arg=None):
    for p in (arg, os.environ.get("BLENDER"), r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe", r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe", "blender"):
        if p and (os.path.exists(p) or p == "blender"):
            return p
    return "blender"


def scene_mesh(ent, plan):
    """A small landscape around the bridge: grass valley following the ground profile, the water / road below, approach roads."""
    b = wm.Builder()
    ctx = ent["context"]
    L, W = plan["L"], plan["W"]
    gh = bm.Prof([(u * FT, g * FT) for u, g in ctx["ground_hi"]])
    ext = 45 * FT
    half = W / 2 + 40 * FT
    us = np.unique(np.concatenate([np.linspace(-ext, L + ext, 70), np.linspace(0, L, 60)]))
    vs = np.linspace(-half, half, 17)
    ids = np.zeros((len(us), len(vs)), int)
    for i, u in enumerate(us):
        z = float(gh(min(max(u, 0), L))) - (0.30 if 0 <= u <= L else 0.0)
        for j, v in enumerate(vs):
            ids[i, j] = b.vert((u, v, z), (u / (8 * FT), v / (8 * FT)))
    for i in range(len(us) - 1):
        for j in range(len(vs) - 1):
            b.quad("mat_grass", ids[i, j], ids[i + 1, j], ids[i + 1, j + 1], ids[i, j + 1])
    for o in ctx["others"]:
        if o["kind"] == "water":
            u0, u1, zs = o["u0_ft"] * FT, o["u1_ft"] * FT, o["surface_ft"] * FT
            q = [b.vert((u0, -half, zs), (0, 0)), b.vert((u1, -half, zs), (1, 0)), b.vert((u1, half, zs), (1, 8)), b.vert((u0, half, zs), (0, 8))]
            b.quad("mat_water", *q)
        else:
            uc, zr = o["u_ft"] * FT, o["z_ft"] * FT
            hw = o["width_ft"] * FT / 2
            q = [b.vert((uc - hw, -half, zr), (0, 0)), b.vert((uc + hw, -half, zr), (1, 0)), b.vert((uc + hw, half, zr), (1, 8)), b.vert((uc - hw, half, zr), (0, 8))]
            b.quad("mat_gravel", *q)
    z0, z1 = plan["deck"][0][1], plan["deck"][-1][1]
    for (ua, ub, z) in ((-ext, 0.0, z0), (L, L + ext, z1)):
        q = [b.vert((ua, -W / 2, z), (0, 0)), b.vert((ub, -W / 2, z), (1, 0)), b.vert((ub, W / 2, z), (1, 1)), b.vert((ua, W / 2, z), (0, 1))]
        b.quad(ctx["deck_material"], *q)
    return b.build()


VARIANTS = {"covered_timber_piers": ("covered_timber", {"support": "piers", "roof": "tile", "flower_boxes": False})}      # extra sheet entries: a preset with parameter overrides


def sample_for(pid, span_ft=60.0, seed=7):
    if pid in VARIANTS:
        base, ov = VARIANTS[pid]
        e = sample_for(base, span_ft, seed)
        e["params"] = dict(ov)
        e["id"] = f"brg_{pid}_1"
        return e
    fam = bm.load_preset(pid)["family"]
    if pid == "rough_log":
        return bm.sample_entity(pid, span_ft=min(span_ft, 20.0), drop_ft=5.0, water=True, seed=seed, name=pid, wall_slope=1.0)
    if pid == "covered_timber":
        return bm.sample_entity(pid, span_ft=max(span_ft, 70.0), drop_ft=14.0, water=True, seed=seed, name=pid, wall_slope=0.5)
    if pid == "rope_plank":
        return bm.sample_entity(pid, span_ft=min(max(span_ft, 50.0), 70.0), drop_ft=22.0, water=True, seed=seed, name=pid, wall_slope=0.35)
    if pid == "flat_cut_stone":
        return bm.sample_entity(pid, span_ft=min(span_ft, 34.0), drop_ft=9.0, water=False, seed=seed, name=pid)
    if pid == "plank_footbridge":
        return bm.sample_entity(pid, span_ft=min(span_ft, 36.0), drop_ft=8.0, water=True, seed=seed, name=pid)
    return bm.sample_entity(pid, span_ft=span_ft, drop_ft=14.0, water=(fam != "arch" or pid != "brick_arch"), seed=seed, name=pid)


def build_entity(ent, out, name=None):
    """GLB (+ textures) of one real or detected entity with its landscape; returns the glb id."""
    import types
    gdir = os.path.join(out, "glb")
    os.makedirs(os.path.join(gdir, "textures"), exist_ok=True)
    pid = name or ent["id"]
    mesh, plan = bm.build_local(ent)
    land = scene_mesh(ent, plan)
    mats = {}
    for mid in set(list(mesh.subs) + list(land.subs)):
        if mid.startswith("mat_s_"):
            import building_styles as bs
            r = bs.material_record(mid)
        else:
            r = {"id": mid, "name": mid[4:], "kind": "image", "texture": f"textures/{mid[4:]}.png", "source": None, "sha256": None, "mean_color": "#808080"}
        mats[mid] = r
    pbr.prepare(mats)
    for mid in mats:
        pbr.write_material_textures(mid, os.path.join(gdir, "textures"), overwrite_base=True)
    wm.write_glb(os.path.join(gdir, pid + ".glb"), [(pid, mesh, {}), (pid + "_land", land, {})], mats, textures="external", tex_root=os.path.join(gdir, "textures"), tex_prefix="textures/")
    return {"id": pid, "tris": mesh.tri_count, "ok": plan["ok"], "notes": plan["notes"], "clearance_violations": bm.check_clearance(mesh, plan)}


def build(out, only=None, span_ft=60.0, seed=7):
    os.makedirs(out, exist_ok=True)
    gdir = os.path.join(out, "glb")
    os.makedirs(os.path.join(gdir, "textures"), exist_ok=True)
    names = []
    for pid in [pr["id"] for pr in bm.list_presets()] + list(VARIANTS):
        if only and pid not in only:
            continue
        ent = sample_for(pid, span_ft, seed)
        mesh, plan = bm.build_local(ent)
        bad = bm.check_clearance(mesh, plan)
        land = scene_mesh(ent, plan)
        mats = {}
        for mid in set(list(mesh.subs) + list(land.subs)):
            if mid.startswith("mat_s_"):
                import building_styles as bs
                r = bs.material_record(mid)
            else:
                r = {"id": mid, "name": mid[4:], "kind": "image", "texture": f"textures/{mid[4:]}.png", "source": None, "sha256": None, "mean_color": "#808080"}
            mats[mid] = r
        pbr.prepare(mats)
        for mid in mats:
            pbr.write_material_textures(mid, os.path.join(gdir, "textures"), overwrite_base=True)
        wm.write_glb(os.path.join(gdir, pid + ".glb"), [(pid, mesh, {}), (pid + "_land", land, {})], mats, textures="external", tex_root=os.path.join(gdir, "textures"), tex_prefix="textures/")
        print(f"built {pid}: {mesh.tri_count} tris, clearance violations {bad}, ok={plan['ok']} {plan['notes']}", flush=True)
        names.append(pid)
    return names


def render(out, only=None, blender=None, views=("threeq", "under"), size=(1000, 700), span_ft=60.0):
    out = os.path.abspath(out)
    ids = build(out, only, span_ft)
    for v in views:
        cmd = [find_blender(blender), "-b", "--factory-startup", "--python", os.path.join(REPO, "foundry-3d", "blender", "bridge_preview.py"), "--", os.path.join(out, "glb"), out, ",".join(ids), v,
               str(size[0]), str(size[1])]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-1500:], r.stderr[-1500:])
    return ids


def sheet(out, ids=None, view="threeq", cols=3, w=600, name=None):
    from PIL import Image, ImageDraw
    ids = ids or [p["id"] for p in bm.list_presets()] + list(VARIANTS)
    ims = []
    for pid in ids:
        f = os.path.join(out, f"{pid}_{view}.png")
        if os.path.exists(f):
            ims.append((pid, Image.open(f).convert("RGB")))
    if not ims:
        return None
    h = int(ims[0][1].height * w / ims[0][1].width)
    rows = (len(ims) + cols - 1) // cols
    S = Image.new("RGB", (cols * w, rows * h), (30, 30, 30))
    d = ImageDraw.Draw(S)
    for k, (pid, im) in enumerate(ims):
        S.paste(im.resize((w, h)), ((k % cols) * w, (k // cols) * h))
        d.text(((k % cols) * w + 8, (k // cols) * h + 6), pid, fill=(255, 255, 255))
    p = os.path.join(out, name or ("sheet.png" if view == "threeq" else f"sheet_{view}.png"))
    S.save(p)
    return p


def thumbs(out):
    from PIL import Image
    os.makedirs(os.path.join(out, "thumbs"), exist_ok=True)
    for pr in bm.list_presets():
        f = os.path.join(out, f"{pr['id']}_threeq.png")
        if os.path.exists(f):
            im = Image.open(f).convert("RGB")
            im.thumbnail((160, 110))
            im.save(os.path.join(out, "thumbs", pr["id"] + ".png"))


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "sheet", "build", "entity"])
    ap.add_argument("--place")
    ap.add_argument("--pack")
    ap.add_argument("--id")
    ap.add_argument("--preset")
    ap.add_argument("--set", action="append", default=[])
    ap.add_argument("--view", default="threeq")
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--only")
    ap.add_argument("--span-ft", type=float, default=60.0)
    ap.add_argument("--views", default="threeq,under")
    ap.add_argument("--blender")
    ap.add_argument("--sheet-name", help="file name of the sheet (e.g. sheet_v2.png); the under view gets an _under suffix")
    a = ap.parse_args(argv)
    only = a.only.split(",") if a.only else None
    if a.cmd == "entity":
        ent = bm.entity_for(a.place, a.id, a.pack, a.preset, bm._overrides(a.set))
        out = os.path.abspath(a.out)
        info = build_entity(ent, out, "preview_entity")
        cmd = [find_blender(a.blender), "-b", "--factory-startup", "--python", os.path.join(REPO, "foundry-3d", "blender", "bridge_preview.py"), "--", os.path.join(out, "glb"), out, "preview_entity", a.view, "900", "620"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        png = os.path.join(out, f"preview_entity_{a.view}.png")
        print(json.dumps({"ok": r.returncode == 0 and os.path.exists(png), "png": png, **info}))
    elif a.cmd == "build":
        print(json.dumps(build(a.out, only, a.span_ft)))
    elif a.cmd == "render":
        ids = render(a.out, only, a.blender, tuple(a.views.split(",")), span_ft=a.span_ft)
        for v in a.views.split(","):
            sheet(a.out, ids, v, name=(a.sheet_name if v == "threeq" else a.sheet_name.replace(".png", "_under.png")) if a.sheet_name else None)
        thumbs(a.out)
        print(json.dumps({"ok": True, "ids": ids, "sheet": os.path.join(a.out, "sheet.png")}))
    else:
        print(json.dumps({"sheet": sheet(a.out)}))


if __name__ == "__main__":
    main()
