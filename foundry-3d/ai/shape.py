"""Image -> untextured mesh with Hunyuan3D-2mini (shape stage only, fits 10 GB).
Usage: python shape.py <image> <out.glb>
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "repo"))
import torch
from PIL import Image
from hy3dgen.rembg import BackgroundRemover
from hy3dgen.shapegen import Hunyuan3DDiTFlowMatchingPipeline

img_path, out = sys.argv[1], sys.argv[2]
image = Image.open(img_path).convert("RGBA")
if image.getchannel("A").getextrema()[0] == 255:  # no transparency: strip background
    image = BackgroundRemover()(image.convert("RGB"))

pipe = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
    "tencent/Hunyuan3D-2mini", subfolder="hunyuan3d-dit-v2-mini", variant="fp16",
    use_safetensors=True, device="cuda")
mesh = pipe(image=image, num_inference_steps=30, octree_resolution=256,
            generator=torch.manual_seed(1))[0]
mesh.export(out)
print("[ai3d] shape written", out, len(mesh.faces), "faces")
