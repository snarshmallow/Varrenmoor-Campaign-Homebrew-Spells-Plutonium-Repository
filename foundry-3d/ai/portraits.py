"""Generate skeleton versions of famous oil portraits with Stable Diffusion XL (fits the 10 GB RTX 3080 in fp16).
Usage: python portraits.py [name ...]   (no names = all). Writes ../textures/painting_<name>.jpg and eyes.json, the
pixel centres (in the saved image) of the two glowing eye sockets, found by locating the two brightest warm blobs in
the upper half of the face area. Check the result by eye: portraits_preview.png marks them.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

OUT = Path(__file__).resolve().parent.parent / "textures"
STYLE = ("oil painting, museum masterpiece, cracked varnish, rich dark palette, a skeleton as the sitter, bare skull face "
         "with two small glowing amber lights deep in the eye sockets, ornate period clothing, looking straight at the viewer")
NEG = "photo, modern, text, watermark, signature, blurry, extra limbs, deformed, cartoon, anime, lowres, cropped face, skin, flesh, living face, human face, beard, hair on face, eyeballs"

PORTRAITS = {
    "monalisa": "portrait of a skeleton in the style of Leonardo da Vinci's Mona Lisa, enigmatic skull smile, brown renaissance gown, folded bony hands on a chair arm, hazy winding landscape behind, sfumato",
    "pearl": "portrait of a skeleton in the style of Vermeer's Girl with a Pearl Earring, blue and yellow turban, large pearl earring hanging from a skull, dark plain background, soft window light",
    "napoleon": "portrait of a skeleton in the style of Jacques-Louis David's Napoleon in His Study, blue general's uniform with white breeches, hand tucked into the waistcoat, candlelit study, gold braid",
    "vangogh": "self-portrait of a skeleton in the style of Vincent van Gogh, bandaged head, blue coat, swirling turquoise brushstroke background, thick impasto",
    "henry": "portrait of a skeleton wearing Henry VIII's costume in the style of Hans Holbein, the head is a bare yellowed human skull with empty eye sockets and exposed teeth, no skin, no beard, black feathered cap, jewelled green doublet, gold chains, bony hands, green background",
    "blueboy": "a full skeleton, human skull for a head with empty black eye sockets and bare teeth, no skin, no flesh, no hair, bony hand on hip, dressed in the shimmering blue satin suit with lace collar and large black plumed hat of Gainsborough's The Blue Boy, stormy landscape background, oil painting",
}


def find_eyes(im):
    """Two brightest warm (orange/amber) blobs in the upper 70% of the image, left-to-right."""
    a = np.asarray(im.convert("RGB")).astype(float)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    warm = (r > 190) & (r - b > 90) & (g > 90)
    warm[int(a.shape[0] * 0.7):] = False
    lab, n = ndi.label(ndi.binary_dilation(warm, iterations=3))
    blobs = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < 12:
            continue
        w = (r[ys, xs] + g[ys, xs])
        blobs.append((float(w.sum()), float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum()), len(ys)))
    blobs.sort(reverse=True)
    top = blobs[:2]
    top.sort(key=lambda t: t[1])
    return [(round(x, 1), round(y, 1), n) for _, x, y, n in top]


def main():
    names = sys.argv[1:] or list(PORTRAITS)
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-fast-3d" if False else "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    eyes_path = OUT / "eyes.json"
    eyes = json.loads(eyes_path.read_text()) if eyes_path.exists() else {}
    for name in names:
        best = None
        for seed in (int(__import__('os').environ.get('SEED', 11)),):
            img = pipe(prompt=f"{PORTRAITS[name]}, {STYLE}", negative_prompt=NEG, width=832, height=1216,
                       num_inference_steps=32, guidance_scale=6.5, generator=torch.manual_seed(seed)).images[0]
            found = find_eyes(img)
            print(name, seed, found, flush=True)
            if len(found) == 2 and abs(found[0][1] - found[1][1]) > 25:
                best = (img, found)
                break
            best = best or (img, found)
        img, found = best
        img.save(OUT / f"painting_{name}.jpg", quality=90)
        eyes[name] = {"size": list(img.size), "eyes": [[x, y] for x, y, _ in found]}
        eyes_path.write_text(json.dumps(eyes, indent=1))
    # contact sheet with the detected eyes marked, for a quick visual check
    sheet = Image.new("RGB", (416 * len(eyes), 608), "black")
    for i, (name, d) in enumerate(eyes.items()):
        im = Image.open(OUT / f"painting_{name}.jpg").convert("RGB")
        dr = ImageDraw.Draw(im)
        for x, y in d["eyes"]:
            dr.ellipse((x - 12, y - 12, x + 12, y + 12), outline=(0, 255, 0), width=3)
        sheet.paste(im.resize((416, 608)), (416 * i, 0))
    sheet.save(OUT / "portraits_preview.png")
    print("done")


if __name__ == "__main__":
    main()
