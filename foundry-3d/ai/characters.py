"""Concept images for the quest NPC tokens, made for the image-to-3D step: one subject, centred, full body, plain light
background, even lighting. Usage: python characters.py [name ...]  ->  ai/characters/<name>_<seed>.png + contact sheet.
"""
import sys
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline
from PIL import Image

OUT = Path(__file__).resolve().parent / "characters"
OUT.mkdir(exist_ok=True)
BG = "plain pale grey studio background, full body visible head to toe, centred, soft even lighting, no cast shadow, single character, character design sheet"
NEG = "text, watermark, signature, multiple characters, cropped, cut off, close-up, busy background, blurry, lowres, deformed hands, extra heads"
CHARS = {
    "tobias_wren": "painterly fantasy character concept art, old gaunt gentle man, former gravewright, long black frock coat to the knees, stooped shoulders, "
                   "wispy white hair, kind sad face, small round spectacles, holding a long-handled shovel, worn boots, standing upright front view",
    "dunmore_kell": "painterly fantasy character concept art, tired middle-aged night porter, flat grey cap, cream work apron over a brown shirt and trousers, "
                    "heavy boots, stubble, weary expression, holding a small lit lantern, standing upright front view",
    "gerald": "painterly fantasy creature concept art, a small soft-shelled turtle, flat leathery olive-green shell, long fleshy pointed snout, a long pink grippy tongue "
              "sticking out, six legs with sticky pink toe pads, three-quarter view from the front, cute and skittish",
}


def main():
    names = sys.argv[1:] or list(CHARS)
    pipe = StableDiffusionXLPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    made = []
    for name in names:
        for seed in (3, 17, 29):
            img = pipe(prompt=f"{CHARS[name]}, {BG}", negative_prompt=NEG, width=1024, height=1024, num_inference_steps=30, guidance_scale=6.5,
                       generator=torch.manual_seed(seed)).images[0]
            f = OUT / f"{name}_{seed}.png"
            img.save(f)
            made.append(f)
            print("made", f.name, flush=True)
    sheet = Image.new("RGB", (340 * 3, 340 * len(names)), "white")
    for r, name in enumerate(names):
        for c, seed in enumerate((3, 17, 29)):
            sheet.paste(Image.open(OUT / f"{name}_{seed}.png").convert("RGB").resize((340, 340)), (340 * c, 340 * r))
    sheet.save(OUT / "sheet.png")
    print("done")


if __name__ == "__main__":
    main()
