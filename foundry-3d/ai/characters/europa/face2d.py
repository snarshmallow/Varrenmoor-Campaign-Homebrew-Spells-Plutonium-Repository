"""v2 face texture source: the portrait face, rolled level (eye line horizontal), upscaled, eyes repainted to look straight ahead.
  python face2d.py [--seeds 5,11,23] [--strength 0.75]
Writes europa_face_level.png (levelled crop, 1024), europa_face_eyemask.png, europa_face_<seed>.png (SDXL inpaint of the eyes only).
Source landmarks (europa_source.png pixels): eyes (436.7,120) and (483.3,127.3), nose ring (453.3,149.3), mouth (451.7,163.3).
"""
import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
EL, ER = (436.7, 120.0), (483.3, 127.3)
CROP = 176                         # source px around the eye midpoint (face + hood opening)
S = 1024


def level():
    src = Image.open(HERE / "europa_source.png").convert("RGB")
    mx, my = (EL[0] + ER[0]) / 2, (EL[1] + ER[1]) / 2
    ang = math.degrees(math.atan2(ER[1] - EL[1], ER[0] - EL[0]))       # 8.9 deg: right eye lower
    big = src.crop((int(mx - 200), int(my - 200), int(mx + 200), int(my + 200)))
    big = big.rotate(ang, resample=Image.BICUBIC, center=(mx - int(mx - 200), my - int(my - 200)))
    c = 200
    face = big.crop((c - CROP // 2, c - int(CROP * 0.42), c + CROP // 2, c + CROP - int(CROP * 0.42))).resize((S, S), Image.LANCZOS)
    face.save(HERE / "europa_face_level.png")
    # eye centres after rotation: both on the eye line, half the eye distance either side of the crop centre
    k = S / CROP
    half = math.dist(EL, ER) / 2 * k
    ey = int(CROP * 0.42) * k
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    for ex in (S / 2 - half, S / 2 + half):
        d.ellipse((ex - 62, ey - 38, ex + 62, ey + 38), fill=255)
    m = m.filter(ImageFilter.GaussianBlur(6))
    m.save(HERE / "europa_face_eyemask.png")
    print("levelled by", round(ang, 2), "deg; eyes at y", round(ey), "x", round(S / 2 - half), round(S / 2 + half))
    return face, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="5,11,23")
    ap.add_argument("--strength", type=float, default=0.75)
    ap.add_argument("--level-only", action="store_true")
    a = ap.parse_args()
    face, m = level()
    if a.level_only:
        return
    import torch
    from diffusers import StableDiffusionXLInpaintPipeline
    pipe = StableDiffusionXLInpaintPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16,
                                                            variant="fp16", use_safetensors=True)
    pipe.enable_sequential_cpu_offload()
    for seed in [int(s) for s in a.seeds.split(",")]:
        img = pipe(prompt="close-up stylised 3D game render of a young woman's face, pale light violet eyes looking straight at the viewer, "
                          "irises centred, calm neutral expression, grey skin with freckles",
                   negative_prompt="looking up, looking sideways, rolled eyes, closed eyes, cross-eyed, red eyes, blurry, deformed",
                   image=face, mask_image=m, width=S, height=S, strength=a.strength, num_inference_steps=30, guidance_scale=6.0,
                   generator=torch.manual_seed(seed)).images[0]
        Image.composite(img, face, m).save(HERE / f"europa_face_{seed}.png")
        print("made", seed, flush=True)


if __name__ == "__main__":
    main()
