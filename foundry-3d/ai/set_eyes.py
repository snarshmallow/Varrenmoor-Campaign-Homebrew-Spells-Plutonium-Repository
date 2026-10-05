"""Hand-measured eye-socket centres (pixels in each saved painting_*.jpg) for the skeleton portraits.
The SDXL portraits have no glowing eyes, so the automatic detector in portraits.py cannot find them; read them off the images.
Run after portraits.py:  python ai/set_eyes.py
"""
import json
from pathlib import Path
from PIL import Image

T = Path(__file__).resolve().parent.parent / "textures"
EYES = {                       # name: [[leftx, lefty], [rightx, righty]]
    "monalisa": [[443, 222], [492, 222]],
    "pearl": [[57, 410], [153, 429]],          # profile view, after the frame was cropped away
    "napoleon": [[410, 241], [436, 239]],
    "vangogh": [[352, 178], [428, 198]],
    "henry": [[388, 254], [478, 248]],
    "blueboy": [[336, 384], [386, 364]],
}
data = json.loads((T / "eyes.json").read_text()) if (T / "eyes.json").exists() else {}
for name, e in EYES.items():
    f = T / f"painting_{name}.jpg"
    if f.exists() and e[0] != [0, 0]:
        data[name] = {"size": list(Image.open(f).size), "eyes": e}
(T / "eyes.json").write_text(json.dumps(data, indent=1))
print({k: v["eyes"] for k, v in data.items()})
