"""NPC actors: spec -> dnd5e actor JSON (via foundry-json/fvtt.py) -> optional concept art + 3D token -> Foundry -> optional placement."""
import json
import sys

from .common import DEFAULT_FOLDER, MODELS, ROOT, bridge, find, folder_id, scene_frame, slug, to_scene, uuid_id
from . import art

sys.path.insert(0, str(ROOT / "foundry-json"))
import fvtt  # noqa: E402

SIZES = {"tiny": "tiny", "sm": "sm", "small": "sm", "med": "med", "medium": "med", "lg": "lg", "large": "lg", "huge": "huge"}
TEMPLATE = {
    "name": "Example Person", "cr": 0.5, "size": "med", "type": "humanoid", "subtype": "human", "alignment": "neutral",
    "hp": 22, "hp_formula": "4d8+4", "ac": 12, "abilities": [10, 12, 12, 10, 12, 10], "speed": {"walk": 30}, "senses": {}, "languages": ["common"],
    "bio": "Player-facing description of who they are.", "gm_notes": "GM-only notes: what they know, DCs, how they react.",
    "features": [{"name": "Trait name", "text": "What it does."}],
    "attacks": [{"name": "Club", "ability": "str", "dice": "1d4", "dtype": "bludgeoning", "bonus": 0, "reach": 5}],
    "disposition": 0, "named": True, "folder": "Quest NPCs (Side Quests)",
    "art": {"prompt": "painterly fantasy character concept art, ...", "image": None, "height": 1.75, "seed": 29, "tris": 9000, "seq_offload": True, "scale": 1.0},
}


def build_actor(spec, model_file=None):
    nm = spec["name"]
    items, sort = [], 100000
    for f in spec.get("features", []):
        items.append(fvtt.feat(nm, f["name"], fvtt.p(f["text"]), sort)); sort += 100000
    for a in spec.get("attacks", []):
        n, d = a["dice"].lower().split("d")
        d, _, bonus = d.partition("+")
        items.append(fvtt.weapon(nm, a["name"], fvtt.p(a.get("text", "")), sort, a.get("ability", "str"), int(n), int(d), a.get("dtype", "bludgeoning"),
                                 bonus=str(a.get("bonus", bonus or 0)), reach=a.get("reach", 5), rng=a.get("range"), melee=a.get("melee", True))); sort += 100000
    bio = fvtt.p(spec.get("bio", ""))
    if spec.get("gm_notes"):
        bio += fvtt.p("<strong>GM notes.</strong> " + spec["gm_notes"])
    size = SIZES[spec.get("size", "med")]
    actor = fvtt.npc(nm, spec.get("cr", 0), size if size != "sm" else "sm", spec.get("type", "humanoid"), spec.get("subtype", ""), spec["hp"], spec["ac"],
                     tuple(spec.get("abilities", [10] * 6)), spec.get("speed", {"walk": 30}), items=items, bio=bio, img="icons/svg/mystery-man.svg",
                     token_img="icons/svg/mystery-man.svg", model=model_file or "", tok_size={"sm": "med"}.get(size, size), hp_formula=spec.get("hp_formula", ""),
                     senses=spec.get("senses"), languages=tuple(spec.get("languages", ())), disposition=spec.get("disposition", 0),
                     scale=spec.get("art", {}).get("scale", 1.0), align=spec.get("alignment", "neutral"))
    if not model_file:
        actor["prototypeToken"]["flags"] = {}
    actor["prototypeToken"]["actorLink"] = bool(spec.get("named", True))
    return actor


def create(spec, dry=False, log=print):
    art_spec = spec.get("art") or {}
    model_file = None
    if art_spec.get("model"):                                              # an existing model file name
        model_file = art_spec["model"]
    elif art_spec.get("image") or art_spec.get("prompt"):
        if dry:
            log(f"[dry] would generate art/model for {spec['name']}")
            model_file = f"token_{slug(spec['name'])}_ai.glb"
        else:
            img = art_spec.get("image") or art.concept(spec["name"], art_spec["prompt"], art_spec.get("seed", 29), art_spec.get("seq_offload", True))
            log(f"concept image: {img}")
            model_file = art.model_from_image(img, spec["name"], art_spec.get("height", 1.75), art_spec.get("tris", 9000))
            log(f"3D token model: {model_file}")
    actor = build_actor(spec, model_file)
    if model_file:
        actor["prototypeToken"]["flags"]["levels-3d-preview"]["model3d"] = art.model_path(model_file)
    actor.pop("_id", None)
    if dry:
        log(json.dumps({"name": actor["name"], "hp": actor["system"]["attributes"]["hp"], "items": [i["name"] for i in actor["items"]],
                        "token": actor["prototypeToken"]["flags"], "folder": spec.get("folder")}, indent=1))
        return actor, None
    actor["folder"] = folder_id(spec.get("folder", "Quest NPCs (Side Quests)"), "Actor")
    uuid = bridge("create", documentName="Actor", data=actor)["uuid"]
    log(f"actor created: {uuid}")
    return actor, uuid


def place_token(actor_uuid, scene_uuid, x, y, z=0.1, hidden=False, name=None, link=None, log=print):
    """Place a token for an actor at model coordinates (x, y metres)."""
    a = bridge("get", uuid=actor_uuid)
    fr = scene_frame(scene_uuid)
    px, py, el = to_scene(fr, x, y, z)
    pt = json.loads(json.dumps(a["prototypeToken"]))
    pt.update(name=name or pt.get("name") or a["name"], actorId=a["_id"], hidden=hidden, elevation=el if z > 0.15 else 0)
    if link is not None:
        pt["actorLink"] = link
    pt["x"], pt["y"] = round(px - 50 * pt.get("width", 1)), round(py - 50 * pt.get("height", 1))
    r = bridge("create", documentName="Token", parentUuid=scene_uuid, data=pt)
    log(f"token placed: {r['uuid']} at ({px},{py})")
    return r["uuid"]
