"""v2 reference for SF3D: seed-29 candidate with (a) the side cape removed (a procedural cape is added in Blender instead) and
(b) the levelled, eyes-forward face (europa_face_<seed>.png from face2d.py) pasted into the hood opening.
  python ref_v2.py [face_seed=11]  ->  europa_ref_v2.png (grey) + europa_ref_v2_rgba.png (SF3D input), same framing as finalize.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("U2NET_HOME", str(Path.home() / ".rembg" / "models" / "bria-rmbg"))
from PIL import Image, ImageDraw, ImageFilter
from rembg import new_session, remove

HERE = Path(__file__).resolve().parent
fseed = sys.argv[1] if len(sys.argv) > 1 else "11"
img = Image.open(HERE / "europa_cand_29.png").convert("RGB")      # 768x1152 canvas = source shifted (-136, +24)
DX, DY = -136, 24

# (b) face: face2d crop is 176 source px square, eye midpoint at (88, 0.42*176) of the crop, scaled to 1024
face = Image.open(HERE / f"europa_face_{fseed}.png").convert("RGB").resize((176, 176), Image.LANCZOS)
emx, emy = (436.7 + 483.3) / 2 + DX, (120 + 127.3) / 2 + DY
ox, oy = round(emx - 88), round(emy - 0.42 * 176)
m = Image.new("L", img.size, 0)
cx, cy = emx, emy + 16
ImageDraw.Draw(m).ellipse((cx - 44, cy - 52, cx + 44, cy + 58), fill=255)
m = m.filter(ImageFilter.GaussianBlur(6))
layer = img.copy()
layer.paste(face, (ox, oy))
img = Image.composite(layer, img, m)

cut = remove(img, session=new_session("bria-rmbg"))
a = cut.getchannel("A").point(lambda v: 0 if v < 24 else v)
# (a) side cape: polygon right of the mantle trim / sleeve / hand / skirt (crop coords + (400, 250))
P = [(110, 60), (300, 60), (300, 650), (120, 650), (130, 520), (140, 420), (175, 390), (170, 290), (130, 240), (110, 150)]
ImageDraw.Draw(a).polygon([(x + 400, y + 250) for x, y in P], fill=0)
cut.putalpha(a)
bb = a.getbbox()
cut = cut.crop(bb)
S = 1024
canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
k = 0.9 * S / cut.height
cut = cut.resize((round(cut.width * k), round(cut.height * k)), Image.LANCZOS)
canvas.alpha_composite(cut, ((S - cut.width) // 2, (S - cut.height) // 2))
canvas.save(HERE / "europa_ref_v2_rgba.png")
grey = Image.new("RGBA", (S, S), (200, 200, 200, 255))
grey.alpha_composite(canvas)
grey.convert("RGB").save(HERE / "europa_ref_v2.png")
print("wrote europa_ref_v2(.png/_rgba.png), face seed", fseed, "bbox", bb)
