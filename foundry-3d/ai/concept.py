"""One concept image for the image-to-3D step (SDXL): a single subject, full body, plain background.
  python concept.py --name pimm --prompt "a scrappy goblin surgeon ..." [--seed 29] [--seq-offload]
Writes ai/characters/<name>_<seed>.png. --seq-offload streams weights layer by layer (about 10 min, but needs little RAM; use it when the PC is short on memory).
"""
import argparse
from pathlib import Path

import torch
from diffusers import StableDiffusionXLPipeline

OUT = Path(__file__).resolve().parent / "characters"
BG = "plain pale grey studio background, full body visible head to toe, centred, soft even lighting, no cast shadow, single character, character design sheet"
NEG = ("horns, beard, text, watermark, signature, multiple characters, cropped, cut off, close-up, portrait, headshot, busy background, blurry, lowres, deformed hands, extra heads")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--seed", type=int, default=29)
    ap.add_argument("--neg", default="")
    ap.add_argument("--seq-offload", action="store_true")
    ap.add_argument("--no-bg", action="store_true", help="do not append the plain-background clause (for props)")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    pipe = StableDiffusionXLPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    if a.seq_offload:
        pipe.enable_sequential_cpu_offload()
    else:
        pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    prompt = a.prompt if a.no_bg else f"{a.prompt}, wide shot of the whole figure from head to boots, small in the frame, front view, {BG}"
    img = pipe(prompt=prompt, negative_prompt=(NEG + ", " + a.neg).strip(", "), width=1024, height=1024, num_inference_steps=30, guidance_scale=6.5,
               generator=torch.manual_seed(a.seed)).images[0]
    f = OUT / f"{a.name}_{a.seed}.png"
    img.save(f)
    print("made", f)


if __name__ == "__main__":
    main()
