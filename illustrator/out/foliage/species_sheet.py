"""Species review sheet: python builds one GLB per species (+atlas), Blender renders each, PIL montages them.
  python illustrator/out/foliage/species_sheet.py [--season summer|autumn|winter] [--lod 0] [--only id,id] [--no-render]
Writes illustrator/out/foliage/v2_species/<season>/{glb,png}/ and v2_species_sheet_<season>[_lodN].png."""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "illustrator", "generators"))
import foliage_mesh as fm  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import numpy as np  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--season", default="summer")
ap.add_argument("--lod", type=int, default=0)
ap.add_argument("--only")
ap.add_argument("--no-render", action="store_true")
ap.add_argument("--size", type=int, default=420)
ap.add_argument("--yaw", type=float, default=30)
a = ap.parse_args()
base = os.path.join(HERE, "v2_species", a.season + (f"_lod{a.lod}" if a.lod else ""))
gdir, pdir = os.path.join(base, "glb"), os.path.join(base, "png")
os.makedirs(os.path.join(gdir, "textures"), exist_ok=True)
fm.write_atlas(os.path.join(gdir, "textures", "fol_atlas.png"), season=a.season)
lib = fm.FoliageLibrary()
ids = a.only.split(",") if a.only else list(lib.species)
for sid in ids:
    t = lib.mesh(sid, 0, a.lod)
    if not t.V.size:
        continue
    m = fm.merge_instances([(t, 1.0, 0.0, (0, 0, 0), 1.0)])
    p = os.path.join(gdir, sid + ".glb")
    wm.write_glb(p, [(sid, m, {})], fm.atlas_material(), textures="external", tex_root=gdir)
    fm.patch_glb_alpha_mask(p)
if not a.no_render:
    subprocess.run(["D:/Blender/blender.exe", "-b", "--factory-startup", "--python", os.path.join(REPO, "foundry-3d", "blender", "foliage_species_sheet.py"), "--",
                    gdir, pdir, "--size", str(a.size), "--yaw", str(a.yaw)] + (["--only", a.only] if a.only else []), check=True, stdout=subprocess.DEVNULL)
from PIL import Image, ImageDraw
pngs = [i for i in ids if os.path.exists(os.path.join(pdir, i + ".png"))]
cols = 5
rows = (len(pngs) + cols - 1) // cols
sz = a.size
sheet = Image.new("RGB", (cols * sz, rows * sz), (30, 30, 30))
d = ImageDraw.Draw(sheet)
for k, sid in enumerate(pngs):
    im = Image.open(os.path.join(pdir, sid + ".png")).convert("RGB")
    sheet.paste(im, ((k % cols) * sz, (k // cols) * sz))
    d.text(((k % cols) * sz + 6, (k // cols) * sz + 4), f"{sid}  {lib.tris(sid, a.lod)} tris", fill=(255, 255, 255))
out = os.path.join(HERE, f"v2_species_sheet_{a.season}" + (f"_lod{a.lod}" if a.lod else "") + ".png")
sheet.save(out)
print(out)
