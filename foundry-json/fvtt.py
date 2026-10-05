"""Helpers to build dnd5e 5.x NPC actor and item JSON by cloning structures from real exports in the campaign folder.

Templates come from the Ossuary Exchange exports (Mottle for the NPC shell, Mavis for a weapon attack, a save feat and a
utility feat), so the output has the exact shape this world's dnd5e version imports. Activity ids must be 16 alphanumeric
characters (the bridge's audit_activities checks that), so ids are derived from a hash.
"""
import copy
import hashlib
import json
from pathlib import Path

SHARE = Path(r"\\vega\C\FoundryVTT resources\2026 Campaign\Act 2 Road to Bridgehollow\Ossuary Exchange")
ROOT = Path(__file__).resolve().parent
SRC = "Varrenmoor DM Guide"
MODELS = "assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"


def _load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


_mottle = _load(SHARE / "Mottle_Innkeeper_Ossuary_Exchange_FoundryVTT.json")
_mavis = _load(SHARE / "Mavis_Bracken_Witch_Queen_FoundryVTT.json")
T_ATTACK = next(i for i in _mavis["items"] if i["name"] == "Vine Lash")
T_SAVE = next(i for i in _mavis["items"] if i["name"].startswith("Grasping"))
T_UTIL = next(i for i in _mavis["items"] if i["name"] == "Multiattack")
T_FEAT = _mottle["items"][0]


def hid(*parts, n=16):
    """Stable 16-character alphanumeric id from any parts."""
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:n]


def mod(score):
    return (score - 10) // 2


def p(text):
    return "".join(f"<p>{t}</p>" for t in text.split("\n\n"))


def _base_item(tpl, actor, name, desc, img, ident, sort):
    it = copy.deepcopy(tpl)
    it["_id"] = hid(actor, name, "item")
    it["name"] = name
    it["img"] = img
    it["system"]["description"] = {"value": desc, "chat": ""}
    it["system"]["source"] = {"custom": SRC, "book": "", "page": "", "license": "", "rules": "2014", "revision": 1}
    it["system"]["identifier"] = ident
    it["sort"] = sort
    it["flags"] = {}
    return it


def _act(it, actor, name, act_type_key=None):
    """Re-key the template's single activity with a hash-derived 16-char id."""
    old_key, act = next(iter(it["system"]["activities"].items()))
    new_id = hid(actor, name, "act")
    act["_id"] = new_id
    act["name"] = name
    it["system"]["activities"] = {new_id: act}
    return act


def feat(actor, name, html, sort, img="icons/svg/aura.svg", requirements=""):
    it = _base_item(T_FEAT, actor, name, html, img, hid(name)[:10], sort)
    it["system"]["activities"] = {}
    it["system"]["requirements"] = requirements
    return it


def utility(actor, name, html, sort, activation="action", img="icons/svg/aura.svg", uses=None, recharge=None, chat="", duration=None):
    it = _base_item(T_UTIL, actor, name, html, img, hid(name)[:10], sort)
    a = _act(it, actor, name)
    a["activation"] = {"type": activation, "value": 1 if activation in ("action", "bonus", "reaction") else None, "condition": "", "override": False}
    a["description"] = {"chatFlavor": chat}
    if duration:
        a["duration"]["value"], a["duration"]["units"] = duration
    _uses(it, a, uses, recharge)
    return it


def _uses(it, a, uses, recharge):
    if recharge:
        u = {"max": "1", "recovery": [{"period": "recharge", "type": "recoverAll", "formula": str(recharge)}], "spent": 0}
        it["system"]["uses"] = u
        a["uses"] = copy.deepcopy(u)
    elif uses:
        n, period = uses
        u = {"max": str(n), "recovery": [{"period": period, "type": "recoverAll"}], "spent": 0}
        it["system"]["uses"] = u
        a["uses"] = copy.deepcopy(u)


def save_feat(actor, name, html, sort, ability, dc, dmg=None, on_save="none", target=None, rng=None, activation="action",
              recharge=None, uses=None, duration=None, img="icons/svg/lightning.svg", chat=""):
    """dmg = (number, denomination, type) or None. target = (shape, size) e.g. ('cone', 30) or ('radius', 20)."""
    it = _base_item(T_SAVE, actor, name, html, img, hid(name)[:10], sort)
    a = _act(it, actor, name)
    a["activation"] = {"type": activation, "value": 1, "condition": "", "override": False}
    a["description"] = {"chatFlavor": chat}
    a["save"] = {"ability": ability, "dc": {"calculation": "", "formula": str(dc)}}
    parts = []
    if dmg:
        n, d, t = dmg
        parts = [{"custom": {"enabled": False, "formula": ""}, "number": n, "denomination": d, "bonus": "", "types": [t],
                  "scaling": {"mode": "", "number": 1, "formula": ""}}]
    a["damage"] = {"onSave": on_save, "parts": parts}
    a["range"] = {"value": str(rng or ""), "units": "ft" if rng else "", "special": "", "override": False}
    shape, size = target or ("", "")
    a["target"] = {"template": {"count": "", "contiguous": False, "type": shape, "size": str(size), "width": "", "height": "", "units": "ft" if shape else ""},
                   "affects": {"count": "", "type": "creature", "choice": False, "special": ""}, "prompt": True, "override": False}
    if duration:
        a["duration"]["value"], a["duration"]["units"] = duration
    _uses(it, a, uses, recharge)
    it["system"]["requirements"] = ""
    return it


def weapon(actor, name, html, sort, ability, number, denom, dtype, bonus="", reach=5, rng=None, melee=True, extra_dtype=None,
           img="icons/svg/sword.svg", chat="", props=None):
    it = _base_item(T_ATTACK, actor, name, html, img, hid(name)[:10], sort)
    s = it["system"]
    s["range"] = {"value": rng[0] if rng else None, "long": rng[1] if rng else None, "units": "ft", "reach": reach if melee else None}
    s["damage"]["base"] = {"number": number, "denomination": denom, "bonus": str(bonus), "types": [dtype] + ([extra_dtype] if extra_dtype else []),
                           "custom": {"enabled": False, "formula": ""}, "scaling": {"mode": "", "number": None, "formula": ""}}
    s["properties"] = props or []
    s["type"] = {"value": "natural", "baseItem": ""}
    s["proficient"] = 1
    s["identified"] = True
    s["equipped"] = True
    a = _act(it, actor, name)
    a["attack"] = {"ability": ability, "bonus": "", "critical": {"threshold": None}, "flat": False,
                   "type": {"value": "melee" if melee else "ranged", "classification": "weapon"}}
    a["range"] = {"value": str(rng[0]) if rng else "", "units": "ft", "special": "", "override": False}
    if melee:
        a["range"] = {"value": str(reach), "units": "ft", "special": "", "override": False}
    a["description"] = {"chatFlavor": chat}
    a["target"]["affects"] = {"count": "1", "type": "creature", "choice": False, "special": ""}
    return it


def npc(name, cr, size, ctype, subtype, hp, ac, abilities, speed, *, items, bio, img, token_img, model, tok_size, hp_formula="",
        senses=None, di=(), dr=(), dv=(), ci=(), languages=(), skills=None, disposition=-1, scale=1.0, align="neutral", prof_note=""):
    a = copy.deepcopy(_mottle)
    a.pop("_id", None)
    a.pop("_stats", None)
    a["name"] = name
    a["img"] = img
    a["folder"] = None
    a["ownership"] = {"default": 0}
    a["flags"] = {}
    a["effects"] = []
    s = a["system"]
    for k, v in zip(("str", "dex", "con", "int", "wis", "cha"), abilities):
        s["abilities"][k]["value"] = v
        s["abilities"][k]["proficient"] = 0
    s["attributes"]["hp"] = {"value": hp, "max": hp, "temp": 0, "tempmax": 0, "formula": hp_formula}
    s["attributes"]["ac"] = {"flat": ac, "calc": "natural", "formula": ""}
    mv = {"burrow": 0, "climb": 0, "fly": 0, "swim": 0, "walk": 0, "units": "ft", "hover": False}
    mv.update(speed)
    s["attributes"]["movement"] = mv
    sn = {"darkvision": 0, "blindsight": 0, "tremorsense": 0, "truesight": 0, "units": "ft", "special": ""}
    sn.update(senses or {})
    s["attributes"]["senses"] = sn
    d = s["details"]
    d["cr"] = cr
    d["type"] = {"value": ctype, "subtype": subtype, "swarm": "", "custom": ""}
    d["alignment"] = align
    d["biography"] = {"value": bio, "public": ""}
    d["race"] = None
    tr = s["traits"]
    tr["size"] = size
    tr["di"] = {"value": list(di), "bypasses": [], "custom": ""}
    tr["dr"] = {"value": list(dr), "bypasses": [], "custom": ""}
    tr["dv"] = {"value": list(dv), "bypasses": [], "custom": ""}
    tr["ci"] = {"value": list(ci), "custom": ""}
    tr["languages"] = {"value": list(languages), "custom": ""}
    for sk, v in (skills or {}).items():
        s["skills"][sk]["value"] = v
    s["source"] = {"custom": SRC, "book": "", "page": "", "license": "", "rules": "2014", "revision": 1}
    a["items"] = items
    w = 0.5 if tok_size == "tiny" else {"med": 1, "lg": 2, "huge": 3}[tok_size]
    pt = a["prototypeToken"]
    pt["name"] = name.split(",")[0]
    pt["width"] = pt["height"] = w
    pt["disposition"] = disposition
    pt["actorLink"] = False
    pt["displayName"] = 30
    pt["texture"]["src"] = token_img
    pt["flags"] = {"levels-3d-preview": {"model3d": f"{MODELS}/{model}", "scale": scale, "autoCenter": False,
                                         "offsetX": 0, "offsetY": 0, "offsetZ": 0, "enableAnim": False}}
    return a


def save(actor, subdir, filename):
    for base in (ROOT / subdir, SHARE / "Foundry JSON"):
        base.mkdir(parents=True, exist_ok=True)
        (base / filename).write_text(json.dumps(actor, indent=2, ensure_ascii=False), encoding="utf-8")
