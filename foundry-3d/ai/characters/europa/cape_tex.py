"""Cape texture for build_v2 (u across the cape, v up): portrait green sampled from europa_ref.png, fold shading matching the
5 folds of the cape mesh, gold trim along both sides and the hem with a dark piping line inside it.
  python cape_tex.py  ->  europa_cape_tex.png (512 x 1024)
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HERE = Path(__file__).resolve().parent
W, H, NF = 512, 1024, 5
ref = np.asarray(Image.open(HERE / "europa_ref.png").convert("RGB")).astype(float)
patch = ref[330:700, 650:690].reshape(-1, 3)
patch = patch[(patch[:, 1] > patch[:, 0] + 8)]                 # cape green only
green = np.median(patch, axis=0) * 1.7                         # the sampled strip is in shadow; portrait cape reads lighter
gold = np.array([196.0, 150.0, 52.0])
print("cape green", green.round())

u = (np.arange(W) + 0.5) / W
v = (np.arange(H) + 0.5) / H                                    # image row 0 = top of the image = v 1 (top of cape)
U, Vv = np.meshgrid(u, 1 - v)
p = U * NF * 2 * np.pi
shade = 0.86 + 0.16 * np.sin(p + 0.9) - 0.06 * (1 - Vv)        # crests lit, a little darker toward the hem
rng = np.random.default_rng(3)
grain = rng.normal(0, 4, (H, W, 1))
img = green[None, None, :] * shade[..., None] + grain
tw, th = 0.022, 0.014                                           # trim widths (fraction of u, v)
edge = np.minimum(np.minimum(U, 1 - U) / tw, Vv / th)
img = np.where((edge < 1)[..., None], gold * (0.92 + 0.12 * np.sin(Vv * 400))[..., None] * np.ones(3), img)
img = np.where(((edge >= 1) & (edge < 1.35))[..., None], img * 0.45, img)
out = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.7))
out.save(HERE / "europa_cape_tex.png")
print("wrote europa_cape_tex.png")
