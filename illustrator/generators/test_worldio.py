"""worldio checks on a temp copy of the world (nothing in world/ is touched):
python illustrator/generators/test_worldio.py"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldio  # noqa: E402

REPO = worldio.REPO
tmp = tempfile.mkdtemp(prefix="worldio_")
root = os.path.join(tmp, "world")
src = os.path.join(REPO, "world", "bridgehollow", "terrain")
dst = os.path.join(root, "bridgehollow", "terrain")
os.makedirs(dst)
for f in ("heightmap.npy", "terrain_meta.json"):
    shutil.copy(os.path.join(src, f), dst)
ok = True


def check(name, cond):
    global ok
    ok &= bool(cond)
    print("PASS" if cond else "FAIL", name)


h0, m0 = worldio.load_terrain("bridgehollow", root=root)
check("no patches: source is base", m0["source"] == "base" and m0["sea_level_ft"] == 0.0)
poly = os.path.join(tmp, "poly.json"); par = os.path.join(tmp, "par.json")
json.dump([[900, 500], [1300, 500], [1300, 800], [900, 800]], open(poly, "w"))
json.dump({"terrain_type": "mountain", "max_height_ft": 1400, "avg_height_ft": 1150, "steepness": 0.5, "feather_ft": 80}, open(par, "w"))
r = subprocess.run([sys.executable, os.path.join(HERE, "terrain_patch.py"), "apply", "--place", "bridgehollow", "--root", root,
                    "--polygon", poly, "--params", par], capture_output=True, text=True)
check("patch applied on the copy", r.returncode == 0)
h1, m1 = worldio.load_terrain("bridgehollow", root=root)
check("patched heightmap is picked up (auto)", m1["source"] == "patched" and abs(h1.max() - 1400) < 1.0 and h1.max() > h0.max())
h2, m2 = worldio.load_terrain("bridgehollow", source="base", root=root)
check("source=base ignores patches", m2["source"] == "base" and np.array_equal(h2, h0))
h3, m3 = worldio.load_terrain("bridgehollow", source="carved", root=root)
check("carved falls back to patched when no carved file", m3["source"] in ("patched", "carved"))
# state toggle: water.use_carved makes auto resolve to carved
os.makedirs(os.path.join(root, "bridgehollow"), exist_ok=True)
json.dump({"water": {"use_carved": True}}, open(worldio.state_path("bridgehollow", root), "w"))
check("panel_state water.use_carved -> auto resolves to carved", worldio.resolve_source("bridgehollow", None, root) == "carved")
os.environ["VB_TERRAIN_SOURCE"] = "base"
check("env override wins", worldio.resolve_source("bridgehollow", None, root) == "base")
del os.environ["VB_TERRAIN_SOURCE"]
check("water path default is the world file", worldio.water_path("bridgehollow").endswith(os.path.join("world", "bridgehollow", "water.json")))
shutil.rmtree(tmp, ignore_errors=True)
print("ALL OK" if ok else "FAILURES")
sys.exit(0 if ok else 1)
