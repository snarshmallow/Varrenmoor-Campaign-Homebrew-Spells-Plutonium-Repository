"""Build and push the 'ZZ Tile Rotation Inspect' scene: one asymmetric L-shaped marker model in 4 tiles at rotation 0/90/180/270, a known-coordinate tile, a 10 ft cube
at the scene centre and text Drawings naming each rotation. Settles which tile rotation makes model +Y (Blender north) point up on the 3D Canvas map.

  python tile_rotation_inspect.py build            # write the GLBs + placements.json to illustrator/out/tile_rotation_inspect/
  python tile_rotation_inspect.py push [--dry-run] # build, push-models into a fresh pipeline scene, add label drawings, read the tiles back

Model (Blender frame, metres, x east / y north / z up): L-shaped building, arms run east (9 m) and north (9 m) from the SW elbow. North-facing walls are RED, east BLUE,
south WHITE, west GREEN, roof grey, a yellow roof arrow points +Y and a magenta post stands on the north end. Delete the scene with:
  python foundry_push.py delete-scene --scene-uuid <uuid>
"""
import argparse
import hashlib
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack_mesh as wm  # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(REPO, "illustrator", "out", "tile_rotation_inspect")
PLACE = "zz_tile_rotation_inspect"
SCENE = "ZZ Tile Rotation Inspect"
PPF = 20.0                      # px per ft (100 px = 5 ft grid square)
W_FT, H_FT = 300.0, 200.0       # 60 x 40 grid squares
FT = 0.3048
COLORS = dict(north="#d62828", east="#2a6fdb", south="#f2f2f2", west="#2fa84f", roof="#8a8a8a", arrow="#ffd60a", post="#c026d3", cube="#ff7a00")
MATS = {k: {"mean_color": c, "roughness": 0.9, "metallic": 0.0} for k, c in COLORS.items()}
ROT = [(0, 1000, 800), (90, 2200, 800), (180, 3400, 800), (270, 4600, 800)]     # rotation, x px, y px
KNOWN_FT = (100.0, 150.0)       # world coordinate (ft) of the known-position tile centre = px (2000, 3000)
CENTRE_PX = (W_FT * PPF / 2, H_FT * PPF / 2)
UV4 = [(0, 0), (1, 0), (1, 1), (0, 1)]


def box(b, mat, x0, y0, x1, y1, z0, z1):
    P = lambda x, y, z: (x, y, z)
    for pts in ([P(x0, y0, z0), P(x1, y0, z0), P(x1, y0, z1), P(x0, y0, z1)], [P(x1, y0, z0), P(x1, y1, z0), P(x1, y1, z1), P(x1, y0, z1)],
                [P(x1, y1, z0), P(x0, y1, z0), P(x0, y1, z1), P(x1, y1, z1)], [P(x0, y1, z0), P(x0, y0, z0), P(x0, y0, z1), P(x0, y1, z1)],
                [P(x0, y0, z1), P(x1, y0, z1), P(x1, y1, z1), P(x0, y1, z1)]):
        b.face(mat, pts, UV4)


def _centre(mesh):
    lo, hi = mesh.V.min(0), mesh.V.max(0)
    return mesh.translated(-np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])), hi - lo


def build_l():
    b = wm.Builder()
    foot = [(0, 0), (9, 0), (9, 3), (3, 3), (3, 9), (0, 9)]
    h = 4.0
    for (ax, ay), (bx, by) in zip(foot, foot[1:] + foot[:1]):
        nx, ny = by - ay, -(bx - ax)                    # outward normal of a CCW polygon
        m = "north" if ny > 0 else "south" if ny < 0 else "east" if nx > 0 else "west"
        b.face(m, [(ax, ay, 0), (bx, by, 0), (bx, by, h), (ax, ay, h)], UV4)
    for r in ((3, 0, 9, 3), (0, 0, 3, 9)):               # roof as two non-overlapping rectangles
        b.face("roof", [(r[0], r[1], h), (r[2], r[1], h), (r[2], r[3], h), (r[0], r[3], h)], UV4)
    top = h + 0.3                                        # arrow raised so nothing is coplanar with the roof
    box(b, "arrow", 1.0, 1.0, 2.0, 6.0, h, top)
    head = [(0.2, 6.0), (2.8, 6.0), (1.5, 8.2)]
    b.face("arrow", [(x, y, top) for x, y in head], [(0, 0), (1, 0), (0.5, 1)])
    for (ax, ay), (bx, by) in zip(head, head[1:] + head[:1]):
        b.face("arrow", [(ax, ay, h), (bx, by, h), (bx, by, top), (ax, ay, top)], UV4)
    box(b, "post", 2.2, 8.2, 2.9, 8.9, h, 7.0)           # north post, taller than the roof
    return _centre(b.build())


def build_cube():
    b = wm.Builder()
    s = 10 * FT / 2
    box(b, "cube", -s, -s, s, s, 0, 2 * s)
    return _centre(b.build())


def _entry(eid, rel, size_m, x, y, rot, label):
    return {"id": f"model:{PLACE}:{eid}", "file": rel, "kind": "mesh", "layer": "inspect", "layers": ["inspect"], "ids": [eid], "label": label,
            "pivot": {"x_ft": x / PPF, "y_ft": y / PPF, "z_ft": 0.0, "rel_z_ft": 0.0}, "rotation_deg": 0.0, "scale": 1.0,
            "size_ft": [round(float(v) / FT, 3) for v in size_m], "tile": {"rotation": rot}, "tris": 0, "bytes": 0, "sha256": ""}


def build():
    os.makedirs(os.path.join(OUT, "models"), exist_ok=True)
    files = {}
    for name, (mesh, size) in {"lmarker": build_l(), "cube10": build_cube()}.items():
        rel = f"models/{name}.glb"
        wm.write_glb(os.path.join(OUT, rel), [(name, mesh, {})], MATS, textures="none")
        data = open(os.path.join(OUT, rel), "rb").read()
        files[name] = (rel, size, len(data), hashlib.sha256(data).hexdigest(), mesh.tri_count)
    ents = [_entry(f"rot{rot:03d}", files["lmarker"][0], files["lmarker"][1], x, y, rot, f"rotation {rot}") for rot, x, y in ROT]
    ents.append(_entry("known_pos", files["lmarker"][0], files["lmarker"][1], KNOWN_FT[0] * PPF, KNOWN_FT[1] * PPF, 0, "known position (100, 150) ft, rotation 0"))
    ents.append(_entry("centre_cube", files["cube10"][0], files["cube10"][1], CENTRE_PX[0], CENTRE_PX[1], 0, "10 ft cube at scene centre (150, 100) ft"))
    for e in ents:
        f = files["cube10" if "cube" in e["id"] else "lmarker"]
        e["bytes"], e["sha256"], e["tris"] = f[2], f[3], f[4]
    doc = {"format": "varrenmoor-world-placements", "schema_version": "1.0", "place": PLACE, "pack": {"dir": "."},
           "frame": {"px_per_ft": PPF, "z_origin_ft": 0.0, "width_ft": W_FT, "height_ft": H_FT, "tile_rotation_deg": 0}, "files": ents}
    with open(os.path.join(OUT, "placements.json"), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=1)
    return doc


def labels(doc):
    def text(i, x, y, w, h, t, size, col):
        return {"id": f"draw:label:{i}", "data": {"x": round(x), "y": round(y), "elevation": 0, "hidden": False, "locked": True,
                "shape": {"type": "r", "width": w, "height": h, "radius": None, "points": []}, "fillType": 0, "strokeWidth": 0, "strokeAlpha": 0,
                "text": t, "fontSize": size, "textColor": col, "textAlpha": 1.0}}
    out = [text(e["ids"][0], e["pivot"]["x_ft"] * PPF - 450, e["pivot"]["y_ft"] * PPF + e["size_ft"][1] * PPF / 2 + 40, 900, 120, e["label"], 48, "#ffffff")
           for e in doc["files"]]
    out.append(text("legend", 200, 3500, 5600, 300, "RED walls face model +Y (north); YELLOW arrow + MAGENTA post = north end. Which way does RED point on screen at each rotation?", 44, "#ffff00"))
    return out


def push(dry):
    import foundry_push as fp
    doc = build()
    argv = ["push-models", "--placements", os.path.join(OUT, "placements.json"), "--scene-name", SCENE, "--set-name", "inspect", "--scene-mode", "3d"] + (["--dry-run"] if dry else [])
    a = fp.parser().parse_args(argv)
    br = fp.PsBridge()
    res = fp.cmd_push_models(br, a)
    print(json.dumps(res, indent=1)[:1500])
    if dry:
        return
    uuid = res["scene_uuid"]
    print("drawings:", br.call("upsert_many", documentName="Drawing", parentUuid=uuid, items=labels(doc), prefix="draw:", prune=False))
    sc = br.call("get", uuid=uuid)
    print("scene", sc["name"], sc["width"], sc["height"], sc["grid"])
    for t in sc.get("tiles", []):
        print(json.dumps({k: t.get(k) for k in ("x", "y", "width", "height", "rotation", "elevation")}), t["flags"]["levels-3d-preview"]["model3d"], t["flags"]["levels-3d-preview"].get("depth"))
    print("scene_uuid", uuid)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "push"])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        print(len(build()["files"]), "tiles ->", OUT)
    else:
        push(a.dry_run)
