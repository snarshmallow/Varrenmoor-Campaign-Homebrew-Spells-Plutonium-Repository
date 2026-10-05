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
NEG = "horns, beard, muscular, dwarf, human, tall, yoda, big flat ears, white coat, lab coat, text, watermark, signature, multiple characters, cropped, cut off, close-up, busy background, blurry, lowres, deformed hands, extra heads"
CHARS = {
    "tobias_wren": "painterly fantasy character concept art, old gaunt gentle man, former gravewright, long black frock coat to the knees, stooped shoulders, "
                   "wispy white hair, kind sad face, small round spectacles, holding a long-handled shovel, worn boots, standing upright front view",
    "dunmore_kell": "painterly fantasy character concept art, tired middle-aged night porter, flat grey cap, cream work apron over a brown shirt and trousers, "
                    "heavy boots, stubble, weary expression, holding a small lit lantern, standing upright front view",
    "gerald": "painterly fantasy creature concept art, a small soft-shelled turtle, flat leathery olive-green shell, long fleshy pointed snout, a long pink grippy tongue "
              "sticking out, six legs with sticky pink toe pads, three-quarter view from the front, cute and skittish",
    "brokka": "painterly fantasy character concept art, stout dwarf smith, bald head with a thick braided grey-red beard, heavy leather apron over a "
              "rolled-sleeve shirt, muscular forearms, left hand missing two fingers, holding a smith's hammer, sooty boots, standing upright front view",
    "pimm": "painterly fantasy character concept art, a small skinny goblin surgeon the height of a child, yellow-green skin, bald head with a few wisps of hair, "
            "very long pointed nose, big round yellow eyes behind round brass spectacles, narrow pointed ears, thin arms, patched leather apron over a striped shirt, "
            "bandolier of syringes and tools, holding a small clipboard, standing upright, wide shot of the whole figure from head to boots, small in the frame, front view",
    "mottle": "painterly fantasy character concept art, a skeleton innkeeper, bare yellowed bones, empty eye sockets with a faint glow, wearing a stained white apron "
              "and rolled shirt sleeves, a bar towel over one shoulder, holding a pewter tankard, standing upright front view",
    "quill": "painterly fantasy character concept art, a skeleton runecrafter, bare ivory bones, dark ink-stained hooded scholar's robe with chalk dust, "
             "a satchel of chalk sticks, holding a stick of chalk and a slate, spectacles on the skull, standing upright front view",
}


def main():
    names = sys.argv[1:] or list(CHARS)
    pipe = StableDiffusionXLPipeline.from_pretrained("stabilityai/stable-diffusion-xl-base-1.0", torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    import os
    if os.environ.get("SEQ_OFFLOAD"):
        pipe.enable_sequential_cpu_offload()      # lowest RAM: weights stream from the memory-mapped files layer by layer (slow)
    else:
        pipe.enable_model_cpu_offload()
    pipe.vae.enable_tiling()
    made = []
    for name in names:
        for seed in [int(x) for x in os.environ.get("SEEDS", "3,17,29").split(",")]:
            img = pipe(prompt=f"{CHARS[name]}, {BG}", negative_prompt=NEG, width=1024, height=1024, num_inference_steps=30, guidance_scale=6.5,
                       generator=torch.manual_seed(seed)).images[0]
            f = OUT / f"{name}_{seed}.png"
            img.save(f)
            made.append(f)
            print("made", f.name, flush=True)
    sheet = Image.new("RGB", (340 * 3, 340 * len(names)), "white")
    for r, name in enumerate(names):
        for c, seed in enumerate((3, 17, 29)):
            if not (OUT / f"{name}_{seed}.png").exists():
                continue
            sheet.paste(Image.open(OUT / f"{name}_{seed}.png").convert("RGB").resize((340, 340)), (340 * c, 340 * r))
    sheet.save(OUT / "sheet.png")
    print("done")


if __name__ == "__main__":
    main()
