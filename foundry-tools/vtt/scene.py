"""Scenes: build a generator (foundry-3d/generators/<name>.py) and create a ready-to-play 3D Canvas scene, with folder, playlist, door sounds and vision set."""
import re
import subprocess

from .common import G3D, ROOT, bridge, find, folder_id, uuid_id

DOOR_SOUNDS = ["woodBasic", "woodCreaky", "stoneBasic", "jail", "metal", "industrial", "industrialCreaky"]   # core keys; unknown keys are silent


def create(generator, name, folder="The Ossuary Exchange", playlist=None, door_sound="woodCreaky", vision=False, rebuild=True, pad=4, rotation=0, log=print):
    """generator = file stem in foundry-3d/generators (e.g. 'ossuary_forge'). Returns the new scene uuid. Existing scenes are never touched; delete old ones by hand."""
    if rebuild:
        log(f"building {generator} ...")
        subprocess.run(["powershell", "-NoProfile", "-File", str(G3D / "make.ps1"), generator], check=True, cwd=str(G3D), capture_output=True)
    glb = next((G3D / "out").rglob(f"{generator}.glb"))
    r = subprocess.run(["powershell", "-NoProfile", "-File", str(ROOT / "foundry-bridge" / "make-scene.ps1"), "-Model", str(glb), "-Name", name, "-Pad", str(pad),
                        "-Rotation", str(rotation), "-DisableAnim"], capture_output=True, cwd=str(ROOT / "foundry-bridge"))
    out = r.stdout.decode("utf-8", "ignore")
    log(out.strip())
    m = re.search(r"(Scene\.[A-Za-z0-9]{16})", out)
    if r.returncode != 0 or not m:
        raise RuntimeError("make-scene failed: " + r.stderr.decode("utf-8", "ignore")[-300:])
    uuid = m.group(1)
    data = {"folder": folder_id(folder, "Scene"), "tokenVision": bool(vision)}
    if not vision:                                                    # clear visibility across the whole scene
        data.update({"environment.globalLight.enabled": True, "environment.globalLight.bright": True, "environment.darknessLevel": 0, "environment.darknessLock": True})
    if playlist:
        data["playlist"] = uuid_id(find("Playlist", playlist)["uuid"])
    bridge("update", uuid=uuid, data=data)
    sc = bridge("get", uuid=uuid)
    for t in sc.get("tiles", []):
        f = t.get("flags", {}).get("levels-3d-preview", {})
        if f.get("model3d", "").endswith(f"{generator}.glb"):
            bridge("update", uuid=f"{uuid}.Tile.{t['_id']}", data={"flags.levels-3d-preview.doorSound": door_sound})
    log(f"scene ready: {uuid} ({name}) in folder '{folder}'")
    return uuid
