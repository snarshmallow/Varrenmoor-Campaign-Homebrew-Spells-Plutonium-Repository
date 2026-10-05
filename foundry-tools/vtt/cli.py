"""vtt: quick commands that make Varrenmoor content and put it into Foundry.   python foundry-tools/vtt.py --help"""
import argparse
import json
import sys
from pathlib import Path

from . import docs, encounter, item, npc, scene
from .common import bridge, find, parse_at, scene_frame, to_scene


def load_spec(path_or_json):
    p = Path(path_or_json)
    return json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else json.loads(path_or_json)


def overrides(spec, kv):
    """--set key=value (JSON values) overrides, e.g. --set hp=30 --set art.height=1.2"""
    for s in kv or []:
        k, _, v = s.partition("=")
        try:
            v = json.loads(v)
        except ValueError:
            pass
        d = spec
        parts = k.split(".")
        for q in parts[:-1]:
            d = d.setdefault(q, {})
        d[parts[-1]] = v
    return spec


def scene_arg(name):
    return find("Scene", name)["uuid"]


def cmd_npc(a):
    if a.template:
        print(json.dumps(npc.TEMPLATE, indent=2))
        return
    spec = overrides(load_spec(a.spec), a.set)
    if a.no_art:
        spec.pop("art", None)
    actor, uuid = npc.create(spec, dry=a.dry)
    placed = None
    if a.scene and a.at and uuid:
        x, y, z = parse_at(a.at)
        npc.place_token(uuid, scene_arg(a.scene), x, y, z)
        placed = f"{a.scene} at {a.at}"
    if a.doc and not a.dry:
        docs.npc_entry(spec, uuid, placed)
        print("documented in", docs.GEN_FILE)


def cmd_item(a):
    if a.template:
        print(json.dumps(item.TEMPLATE, indent=2))
        return
    spec = overrides(load_spec(a.spec), a.set)
    it, uuid, model = item.create(spec, dry=a.dry)
    placed = None
    if a.scene and a.at and uuid:
        x, y, z = parse_at(a.at)
        item.place_tile(uuid, scene_arg(a.scene), x, y, z, model, wall=a.wall or spec.get("wall", False), facing=a.facing, scale=a.scale)
        placed = f"{a.scene} at {a.at}" + (" (wall)" if a.wall else "")
    if a.doc and not a.dry:
        docs.item_entry(spec, uuid, placed)
        print("documented in", docs.GEN_FILE)


def cmd_scene(a):
    uuid = scene.create(a.generator, a.name, folder=a.folder, playlist=a.playlist, door_sound=a.door_sound, vision=a.vision, rebuild=not a.no_build)
    if a.doc:
        docs.scene_entry(a.name, a.generator, uuid)
        print("documented in", docs.GEN_FILE)


def cmd_encounter(a):
    if a.template:
        print(json.dumps(encounter.TEMPLATE, indent=2))
        return
    spec = overrides(load_spec(a.spec), a.set)
    uuid = encounter.create(spec, dry=a.dry)
    if a.doc and not a.dry:
        docs.encounter_entry(spec, uuid)
        print("documented in", docs.GEN_FILE)


def cmd_place(a):
    """Place an existing actor (token) or item (tile) in a scene."""
    sc = scene_arg(a.scene)
    x, y, z = parse_at(a.at)
    if a.actor:
        npc.place_token(find("Actor", a.actor)["uuid"], sc, x, y, z, hidden=a.hidden)
    else:
        row = find("Item", a.item)
        doc = bridge("get", uuid=row["uuid"])
        model = doc["flags"]["levels-3d-preview"]["model3d"].split("/")[-1]
        item.place_tile(row["uuid"], sc, x, y, z, model, wall=a.wall, facing=a.facing, scale=a.scale)


def cmd_where(a):
    """Convert generator metres to scene pixels (to check a placement by hand)."""
    fr = scene_frame(scene_arg(a.scene))
    x, y, z = parse_at(a.at)
    print(to_scene(fr, x, y, z), "(px, py, elevation ft)")


def cmd_doc(a):
    docs.commit(a.message, push=not a.no_push)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="vtt", description=__doc__)
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("npc", help="make an NPC actor (optionally with concept art -> 3D token) and import it")
    p.add_argument("spec", nargs="?", help="spec .json file or inline JSON (see --template)")
    p.add_argument("--template", action="store_true", help="print a spec template")
    p.add_argument("--set", action="append", help="override a spec field, e.g. --set hp=30 --set art.height=1.2")
    p.add_argument("--no-art", action="store_true", help="skip image/3D generation (token stays a flat icon)")
    p.add_argument("--scene", help="also place a token in this scene (name or id)")
    p.add_argument("--at", help="x,y[,z] model metres in that scene (same numbers as in the generator)")
    p.add_argument("--dry", action="store_true", help="print what would happen, change nothing")
    p.add_argument("--doc", action="store_true", help="append an entry to the GM guide")
    p.set_defaults(fn=cmd_npc)

    p = sp.add_parser("item", help="make a loot item with a 3D prop and import it")
    p.add_argument("spec", nargs="?")
    p.add_argument("--template", action="store_true")
    p.add_argument("--set", action="append")
    p.add_argument("--scene")
    p.add_argument("--at", help="x,y,z (z = surface height in m; 0.1 = floor)")
    p.add_argument("--wall", action="store_true", help="mount upright on a wall: z is the plate's centre height")
    p.add_argument("--facing", default="n", choices=["n", "s", "e", "w"], help="direction a wall plate faces (n verified)")
    p.add_argument("--scale", type=float, default=3.0, help="enlarge the prop on the map (default 3)")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--doc", action="store_true")
    p.set_defaults(fn=cmd_item)

    p = sp.add_parser("scene", help="build a generator and create a 3D Canvas scene from it")
    p.add_argument("generator", help="file stem in foundry-3d/generators, e.g. ossuary_forge")
    p.add_argument("--name", required=True)
    p.add_argument("--folder", default="The Ossuary Exchange")
    p.add_argument("--playlist")
    p.add_argument("--door-sound", default="woodCreaky")
    p.add_argument("--vision", action="store_true", help="keep token vision on (default off: clear visibility)")
    p.add_argument("--no-build", action="store_true", help="use the existing .glb")
    p.add_argument("--doc", action="store_true")
    p.set_defaults(fn=cmd_scene)

    p = sp.add_parser("encounter", help="place groups of existing actors in a scene and write a GM journal")
    p.add_argument("spec", nargs="?")
    p.add_argument("--template", action="store_true")
    p.add_argument("--set", action="append")
    p.add_argument("--dry", action="store_true")
    p.add_argument("--doc", action="store_true")
    p.set_defaults(fn=cmd_encounter)

    p = sp.add_parser("place", help="place an existing actor or item in a scene")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--actor")
    g.add_argument("--item")
    p.add_argument("--scene", required=True)
    p.add_argument("--at", required=True)
    p.add_argument("--hidden", action="store_true")
    p.add_argument("--wall", action="store_true")
    p.add_argument("--facing", default="n", choices=["n", "s", "e", "w"])
    p.add_argument("--scale", type=float, default=3.0)
    p.set_defaults(fn=cmd_place)

    p = sp.add_parser("where", help="convert x,y[,z] model metres to scene pixels")
    p.add_argument("--scene", required=True)
    p.add_argument("--at", required=True)
    p.set_defaults(fn=cmd_where)

    p = sp.add_parser("doc", help="commit and push the guide, tools, generators and textures")
    p.add_argument("message")
    p.add_argument("--no-push", action="store_true")
    p.set_defaults(fn=cmd_doc)

    a = ap.parse_args(argv)
    if a.cmd in ("npc", "item", "encounter") and not a.template and not a.spec:
        ap.error("give a spec file or JSON (or --template to print one)")
    a.fn(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
