#!/usr/bin/env python3
"""Moorland ground tiles in the Varrenmoor map palette (dark olive / brown, not bright green).

The campaign map (illustrator/out/foundry_screens/varrenmoor_original_map.png) measures: canopy RGB ~ (50,46,33) (72 % of pixels), open ground ~ (90,79,55)
(village clearings (94,79,45)).  The stock grass/pasture/crop tiles are mean (109,152,71) .. (126,169,74): far too green.  This recolours the stock tiles
pointwise (per-channel gain to the target mean, detail and seamlessness kept) into presets/textures/moor_*.png, used by the `varrenmoor` town style and the
`varrenmoor_moor` terrain phase file.  Other places keep the stock tiles.

  python illustrator/generators/make_moor_textures.py            # write presets/textures/moor_*.png
  python illustrator/generators/make_moor_textures.py --check    # print the means
"""
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.abspath(os.path.join(HERE, "..", "presets", "textures"))
MAP_OPEN = (90, 79, 55)
MAP_CANOPY = (50, 46, 33)
# name -> (source tile, target mean RGB)
MOOR = {
    "moor_grass": ("grass", (86, 79, 47)),
    "moor_meadow": ("meadow", (102, 92, 56)),
    "moor_pasture": ("pasture", (94, 86, 51)),
    "moor_crop_green": ("crop_green", (78, 78, 44)),
    "moor_wheat": ("wheat", (122, 102, 56)),
    "moor_tilled": ("tilled", (88, 69, 46)),
    "moor_farmland": ("farmland", (92, 80, 50)),
    "moor_forest_floor": ("forest_floor", (56, 52, 36)),
}


def recolour(src, mean):
    from PIL import Image
    a = np.asarray(Image.open(os.path.join(TEX, src + ".png")).convert("RGB"), float)
    m = a.reshape(-1, 3).mean(0)
    out = a * (np.array(mean, float) / np.maximum(m, 1.0))
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB")


def main():
    for name, (src, mean) in MOOR.items():
        im = recolour(src, mean)
        if "--check" in sys.argv:
            print(name, np.asarray(im, float).reshape(-1, 3).mean(0).round(1))
        else:
            im.save(os.path.join(TEX, name + ".png"), optimize=True)
            print("wrote", name)


if __name__ == "__main__":
    main()
