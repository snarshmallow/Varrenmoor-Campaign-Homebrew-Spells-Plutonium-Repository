"""Step 3: SDXL (base 1.0, the only SD weights on this PC) repaints the masked parts of the paste-up so the edits blend in;
everything outside the mask is pasted back from the paste-up untouched (face, hood, costume stay identical).
  python inpaint.py [--seeds 3,17,29] [--strength 0.62] [--seq-offload]
Writes europa_cand_<seed>.png (grey background) and europa_cands.png (contact sheet).
"""
import argparse
from pathlib import Path

import torch
from diffusers import StableDiffusionXLInpaintPipeline
from PIL import Image

HERE = Path(__file__).resolve().parent
PROMPT = ("stylised 3D game character render, half-drow sorceress standing upright facing the viewer, relaxed open hands at her sides in "
          "dark fingerless leather gloves, long hooded cloak with gold geometric pattern, dark green cape hanging straight down behind her, "
          "green dress with gold trim, striped dark olive trousers, both feet planted, brown leather lace-up boots with teal cuffs, "
          "plain pale grey studio background, soft even lighting")
NEG = ("staff, stick, pole, weapon, animal, pangolin, armadillo, scales, wind, flowing cape, billowing, walking, extra hands, extra fingers, "
       "extra legs, deformed hands, fist, blurry, lowres, text, watermark, landscape, scenery")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="3,17,29,41")
    ap.add_argument("--strength", type=float, default=0.62)
    ap.add_argument("--steps", type=int, default=30)
    ap.add_argument("--seq-offload", action="store_true")
    a = ap.parse_args()
    init = Image.open(HERE / "europa_pasteup.png").convert("RGB")
    mask = Image.open(HERE / "europa_mask.png").convert("L")
    pipe = StableDiffusionXLInpaintPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16,
                                                            variant="fp16", use_safetensors=True)
    if a.seq_offload:
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    outs = []
    for seed in [int(s) for s in a.seeds.split(",")]:
        img = pipe(prompt=PROMPT, negative_prompt=NEG, image=init, mask_image=mask, width=init.width, height=init.height,
                   strength=a.strength, num_inference_steps=a.steps, guidance_scale=6.5, generator=torch.manual_seed(seed)).images[0]
        img = Image.composite(img.resize(init.size), init, mask)    # untouched outside the mask
        f = HERE / f"europa_cand_{seed}.png"
        img.save(f)
        outs.append(img)
        print("made", f.name, flush=True)
    sheet = Image.new("RGB", (384 * len(outs), 576), "white")
    for i, im in enumerate(outs):
        sheet.paste(im.resize((384, 576)), (384 * i, 0))
    sheet.save(HERE / "europa_cands.png")


if __name__ == "__main__":
    main()
