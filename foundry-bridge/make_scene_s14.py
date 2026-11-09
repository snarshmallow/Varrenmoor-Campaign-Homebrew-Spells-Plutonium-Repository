"""Create a Foundry 3D Canvas scene from one or more foundry-3d generator GLBs that share one model frame (Session 14 Ossuary scenes).

  python foundry-bridge/make_scene_s14.py --name "The Dusty Terminal and the Cold Door" \
      --model "foundry-3d/out/Act 2 Road to Bridgehollow/Ossuary Exchange/ossuary_dusty_terminal.glb" \
      --model "foundry-3d/out/.../ossuary_cold_door_exterior.glb" --hide ossuary_cold_door_exterior

Like make-scene.ps1 (empty scene first, then tiles and lights one by one with parentUuid; rotation 0; tile x,y = centre;
100 px = 1.524 m), but: several tiles placed by each model's pre-centring centre (-shift in <model>.scene.json), lights may
carry hidden: true, settings are cloned from Quill's Rune Workshop, and the scene goes into the scene folder
Act 2 > The Ossuary Exchange > Session 14 (created if missing). Takes the shared push lock swarm/locks/foundry_push.lock
(mkdir; waits up to 10 min) around all writes. Refuses if a scene with the same name already exists. Never activates.
"""
import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "foundry-bridge" / "bridge.ps1"
LOCK = ROOT / "swarm" / "locks" / "foundry_push.lock"
TEMPLATE = "Scene.is4fru586eHliLJ4"        # Quill's Rune Workshop (3D Canvas GLB interior)
OSSUARY_FOLDER = "wrDAkoirBs08znu8"        # Scene folder "The Ossuary Exchange"
SUB = "Session 14"
K = 100 / 1.524
FT = 3.281


def call(op, obj):
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(BRIDGE), "-Op", op, "-Args", json.dumps(obj)],
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        raise RuntimeError(f"bridge {op} failed: {r.stderr.strip()[:500]}")
    return json.loads(r.stdout)


def lock():
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    while True:
        try:
            os.mkdir(LOCK)
            return
        except FileExistsError:
            if time.time() - t0 > 600:
                raise SystemExit("push lock busy for 10 min; giving up")
            print("lock busy, waiting 20 s"); sys.stdout.flush()
            time.sleep(20)


def ensure_folder():
    for f in call("list", {"collection": "Folder"}):
        if f.get("name") == SUB and f.get("type") == "Scene":
            d = call("get", {"uuid": f["uuid"]})
            if d.get("folder") == OSSUARY_FOLDER:
                return d["_id"]
    d = call("create", {"documentName": "Folder", "data": {"name": SUB, "type": "Scene", "folder": OSSUARY_FOLDER, "sorting": "a"}})
    print("created folder", d.get("uuid"))
    return d["uuid"].split(".")[-1]


def strip(o):
    o = json.loads(json.dumps(o))
    o.pop("_id", None)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--model", action="append", required=True)
    ap.add_argument("--hide", action="append", default=[], help="model stem whose tile (and lights) start hidden")
    ap.add_argument("--pad", type=int, default=3)
    a = ap.parse_args()

    metas = []
    for m in a.model:
        p = Path(m).resolve()
        meta = json.loads(p.with_suffix(".scene.json").read_text())
        sx, sy, sz = meta["size_m"]
        cx, cy = -meta["shift"][0], -meta["shift"][1]
        metas.append((meta, cx, cy, sx, sy, sz))
    x0 = min(c - s / 2 for _, c, _, s, _, _ in metas); x1 = max(c + s / 2 for _, c, _, s, _, _ in metas)
    y0 = min(c - s / 2 for _, _, c, _, s, _ in metas); y1 = max(c + s / 2 for _, _, c, _, s, _ in metas)
    ux, uy = (x0 + x1) / 2, (y0 + y1) / 2
    W = int(math.ceil((x1 - x0) / 1.524 + 2 * a.pad) * 100)
    H = int(math.ceil((y1 - y0) / 1.524 + 2 * a.pad) * 100)
    sceneX = math.ceil(W * 0.25 / 100) * 100
    sceneY = math.ceil(H * 0.25 / 100) * 100
    CX, CY = sceneX + W / 2, sceneY + H / 2

    tpl = call("get", {"uuid": TEMPLATE})
    if any(s["name"] == a.name for s in call("list", {"collection": "Scene"})):
        raise SystemExit(f"scene '{a.name}' already exists; not creating a duplicate")
    tpl_tile = tpl["tiles"][0]
    tpl_light = tpl["lights"][0]

    lock()
    try:
        folder = ensure_folder()
        scene = {k: tpl[k] for k in ("padding", "grid", "tokenVision", "fog", "environment", "levels", "initialLevel", "flags") if k in tpl}
        scene.update(name=a.name, folder=folder, width=W, height=H, shiftX=0, shiftY=0, navigation=False)
        uuid = call("create", {"documentName": "Scene", "data": scene})["uuid"]
        print(f"scene {a.name} = {uuid} ({W}x{H})")
        for meta, cx, cy, sx, sy, sz in metas:
            hidden = meta["name"] in a.hide
            tx, ty = round(CX + (cx - ux) * K), round(CY - (cy - uy) * K)
            t = strip(tpl_tile)
            t.update(x=tx, y=ty, width=round(sx * K), height=round(sy * K), rotation=0, elevation=0.0995, hidden=hidden)
            f = t["flags"]["levels-3d-preview"]
            f["model3d"] = f"assets/varrenmoor-3d/{meta['folder']}/{meta['name']}.glb"
            f["depth"] = round(sz * K)
            f["randomSeed"] = "".join(ch for ch in meta["name"] if ch.isalnum())[:7]
            f["autoGround"] = True; f["collision"] = True; f["sight"] = True
            call("create", {"documentName": "Tile", "parentUuid": uuid, "data": t})
            print(f"  tile {meta['name']} at {tx},{ty} {t['width']}x{t['height']} depth {f['depth']} hidden={hidden}")
            for l in meta["lights"]:
                d = strip(tpl_light)
                d["x"] = round(tx + l["x"] * K); d["y"] = round(ty - l["y"] * K)
                d["elevation"] = round((l["z"] - 0.1) * FT, 1)
                d["hidden"] = bool(l.get("hidden") or hidden)
                d["config"].update(dim=l["dim"], bright=l["bright"], color=l["color"])
                call("create", {"documentName": "AmbientLight", "parentUuid": uuid, "data": d})
                print(f"  light {l['color']} at {d['x']},{d['y']} hidden={d['hidden']}")
        print(uuid)
    finally:
        os.rmdir(LOCK)


if __name__ == "__main__":
    main()
