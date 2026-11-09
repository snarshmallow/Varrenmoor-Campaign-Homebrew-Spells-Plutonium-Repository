"""Step 4: chosen candidate -> europa_ref.png (plain light grey, full body centred) + europa_ref_rgba.png (cut out, the SF3D input).
  python finalize.py 29
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("U2NET_HOME", str(Path.home() / ".rembg" / "models" / "bria-rmbg"))
from PIL import Image
from rembg import new_session, remove

HERE = Path(__file__).resolve().parent
seed = sys.argv[1] if len(sys.argv) > 1 else "29"
img = Image.open(HERE / f"europa_cand_{seed}.png").convert("RGB")
cut = remove(img, session=new_session("bria-rmbg"))
a = cut.getchannel("A").point(lambda v: 0 if v < 24 else v)    # drop faint halo
cut.putalpha(a)
bb = a.getbbox()
cut = cut.crop(bb)
S = 1024                                                         # square, figure ~90% of the height, centred
canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
k = 0.9 * S / cut.height
cut = cut.resize((round(cut.width * k), round(cut.height * k)), Image.LANCZOS)
canvas.alpha_composite(cut, ((S - cut.width) // 2, (S - cut.height) // 2))
canvas.save(HERE / "europa_ref_rgba.png")
grey = Image.new("RGBA", (S, S), (200, 200, 200, 255))
grey.alpha_composite(canvas)
grey.convert("RGB").save(HERE / "europa_ref.png")
print("wrote europa_ref.png / europa_ref_rgba.png from seed", seed, "bbox", bb)
