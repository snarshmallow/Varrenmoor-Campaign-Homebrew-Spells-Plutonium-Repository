"""Face texture for build_v2's face stage: the flat front render of the head (closeup.py emit, 0.32 m window, 1024 px) with
the levelled portrait face (europa_face_<seed>.png) laid over the face opening through a soft ellipse.
  python facecomp.py [seed=11] [sx sy ax ay]   (sx, sy: scale of the 1024 face image; ax, ay: where its eye midpoint lands)
Writes europa_face_tex.png.
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
seed = sys.argv[1] if len(sys.argv) > 1 else "11"
sx, sy, ax, ay = (float(x) for x in (sys.argv[2:6] if len(sys.argv) > 5 else (0.72, 0.89, 535, 545)))
base = Image.open(HERE / "europa_head_front_flat.png").convert("RGB")
# render background (224 grey) -> dark hood-shadow colour: under-chin faces map outside the silhouette and showed as a white band
import numpy as np
b = np.asarray(base).copy()
bg = (np.abs(b.astype(int) - 224).max(axis=2) <= 3)
b[bg] = (14, 11, 8)
base = Image.fromarray(b)
face = Image.open(HERE / f"europa_face_{seed}.png").convert("RGB")
fw, fh = round(1024 * sx), round(1024 * sy)
face = face.resize((fw, fh), Image.LANCZOS)
ox, oy = round(ax - 512 * sx), round(ay - 425 * sy)          # face2d puts the eye midpoint at (512, 425)
layer = base.copy()
layer.paste(face, (ox, oy))
m = Image.new("L", base.size, 0)
cx, cy = ax, ay + 0.30 * 300 * sy / 0.89
rx, ry = 0.62 * 300 * sx / 0.72, 300 * sy / 0.89
ImageDraw.Draw(m).ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
m = m.filter(ImageFilter.GaussianBlur(22))
out = Image.composite(layer, base, m)
out.save(HERE / "europa_face_tex.png")
print("wrote europa_face_tex.png", dict(seed=seed, sx=sx, sy=sy, ax=ax, ay=ay))
