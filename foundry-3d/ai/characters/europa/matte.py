"""Step 1: cut Europa out of the portrait background with rembg (BRIA RMBG weights already on this PC).
Usage: python matte.py  ->  europa_matte.png (RGBA, same 1024x1024 frame as europa_source.png)
"""
import os
from pathlib import Path

os.environ.setdefault("U2NET_HOME", str(Path.home() / ".rembg" / "models" / "bria-rmbg"))
from PIL import Image
from rembg import new_session, remove

HERE = Path(__file__).resolve().parent
src = Image.open(HERE / "europa_source.png").convert("RGB")
out = remove(src, session=new_session("bria-rmbg"))
out.save(HERE / "europa_matte.png")
print("wrote europa_matte.png", out.size)
