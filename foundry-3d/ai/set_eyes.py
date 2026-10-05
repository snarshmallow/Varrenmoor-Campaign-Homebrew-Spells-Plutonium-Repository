"""Hand-measured eye-socket centres (pixels in each saved painting_*.jpg) for the skeleton portraits.
The SDXL portraits have no glowing eyes, so the automatic detector in portraits.py cannot find them; read them off the images.
Run after portraits.py:  python ai/set_eyes.py
"""
import json
from pathlib import Path
from PIL import Image

T = Path(__file__).resolve().parent.parent / "textures"
EYES = {                       # name: [[leftx, lefty, radius_px], [rightx, righty, radius_px]], read off 4x zoomed grids
    "monalisa": [[441, 219, 11], [487, 218, 11]],
    "pearl": [[56, 410, 7], [151, 430, 15]],          # profile view (after the frame was cropped away)
    "napoleon": [[384, 231, 10], [432, 235, 10]],
    "vangogh": [[349, 175, 9], [424, 184, 11]],
    "henry": [[381, 251, 10], [470, 245, 10]],
    "blueboy": [[324, 379, 10], [383, 361, 10]],
}
data = json.loads((T / "eyes.json").read_text()) if (T / "eyes.json").exists() else {}
for name, e in EYES.items():
    f = T / f"painting_{name}.jpg"
    if f.exists():
        data[name] = {"size": list(Image.open(f).size), "eyes": e}
(T / "eyes.json").write_text(json.dumps(data, indent=1))
print({k: v["eyes"] for k, v in data.items()})
