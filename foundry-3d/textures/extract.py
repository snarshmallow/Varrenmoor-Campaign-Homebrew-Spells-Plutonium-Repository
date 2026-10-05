"""One-off: pull the PBR textures out of the Ossuary Exchange plaza GLB so generated scenes match its look.
Usage: ai\.venv\Scripts\python.exe textures\extract.py <plaza.glb>
Writes textures/<slug>.jpg (base colour) and textures/<slug>_n.jpg (normal map).
"""
import re, sys
from pathlib import Path
import trimesh

out = Path(__file__).parent
seen = set()
for g in trimesh.load(sys.argv[1]).geometry.values():
    m = g.visual.material
    slug = re.sub(r"[^a-z0-9]+", "_", m.name.lower()).strip("_")
    if slug in seen:
        continue
    seen.add(slug)
    if getattr(m, "baseColorTexture", None) is not None:
        m.baseColorTexture.convert("RGB").save(out / f"{slug}.jpg", quality=90)
    if getattr(m, "normalTexture", None) is not None:
        m.normalTexture.convert("RGB").save(out / f"{slug}_n.jpg", quality=92)
    print(slug)
