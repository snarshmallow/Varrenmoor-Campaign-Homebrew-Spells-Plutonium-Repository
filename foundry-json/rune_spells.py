"""The 16 Root Runes of Runecrafting (Eirwyn, Ikkander, Vaelweyr, Mwooreth) as dnd5e 5.3.1 spell items Stellan can learn. Drag one onto his sheet when he
discovers and studies its glyph. Each has two activities:
  1. "Trace <Rune> [1 charge]": spends 1 Rune Charge from his Runecrafting feature and rolls the Runecrafting check (1d20 + proficiency + Wisdom, the stat he chose)
     against the GM's Wyrd DC.
  2. the rune's effect: heal / temp HP / save with damage and an applied active effect / utility, using his Runecrafting save DC (8 + proficiency + Wisdom).
Change `ABILITY` if a character uses Intelligence. The charge pool target is Stellan's Runecrafting feat id (a relative id, so it works once dropped on him).
Usage: python rune_spells.py  -> spells/Runes_FoundryVTT.json (+ share folder)
"""
import json
from pathlib import Path

from fvtt import ROOT, SHARE, hid

ABILITY = "wis"
POOL_ITEM = "dd7KaDt9dU3lzYkP"                      # Stellan's Runecrafting feature (shared Rune Charge pool)
CHECK = f"1d20 + @prof + @abilities.{ABILITY}.mod"
DC = f"8 + @prof + @abilities.{ABILITY}.mod"
SRC = {"custom": "Varrenmoor DM Guide, Runecrafting", "book": "", "page": "", "license": "", "rules": "2014", "revision": 1}


def para(t):
    return f"<p>{t}</p>"


# name, tradition, glyph char, rune name, school, range, effect spec, text
RUNES = [
    ("Preserve", "Eirwyn", "ᛁ", "Isa", "abj", "touch", dict(kind="temphp", dice=(1, 8)),
     "Hold something as it is. A creature you touch gains temporary hit points, or a dying creature is stabilized; food, remains, or a mended seam stop changing for 1 hour."),
    ("Mend", "Eirwyn", "ᛒ", "Berkano", "abj", "touch", dict(kind="heal", dice=(1, 8)),
     "Draw a broken pattern back together. A creature you touch regains hit points, or a damaged object or inscription line is restored to its last whole form."),
    ("Reveal", "Eirwyn", "ᚲ", "Kenaz", "div", "30 ft", dict(kind="save", save="dex", effect=dict(name="Revealed", changes=[("system.attributes.ac.bonus", "-2")], rounds=10, desc="Revealed: its cover, disguise and hiding are stripped (-2 AC)."), dmg=None),
     "Throw light on what is hidden. A hidden, disguised, or invisible creature or object in range must succeed on a Dexterity save or be revealed for 1 minute. You also learn what a mark, door, or object is hiding from you."),
    ("Threshold", "Eirwyn", "ᛞ", "Dagaz", "abj", "30 ft", dict(kind="utility"),
     "Define an edge. Open, seal, or mark a doorway, window, or boundary within range for 1 hour. A creature crossing a sealed threshold without your leave needs a successful Runecrafting check (GM sets the Wyrd DC) to do so."),
    ("Bind", "Ikkander", "ᚾ", "Nauthiz", "abj", "30 ft", dict(kind="save", save="str", effect=dict(name="Bound", status="restrained", rounds=2, desc="Bound: restrained until the end of its next turn."), dmg=None),
     "Tie two things together. A creature or object you can see must succeed on a Strength save or be bound in place (restrained) until the end of its next turn."),
    ("Measure", "Ikkander", "ᛗ", "Mannaz", "div", "touch", dict(kind="utility"),
     "Learn the true size of a thing. You learn exact distance, weight, capacity, or fit of one object or space, and whether something has been altered from its recorded measure. Your next attack against a measured target this turn has +1d4."),
    ("Weight", "Ikkander", "ᚦ", "Thurisaz", "trs", "30 ft", dict(kind="save", save="str", effect=dict(name="Weighted", changes=[("system.attributes.movement.walk", "0.5", 1)], rounds=10, desc="Weighted: speed halved."), dmg=None),
     "Make a thing heavier or lighter. A creature or object in range that fails a Strength save is weighed down: its speed is halved for 1 minute. You may instead halve an object's weight for 1 hour."),
    ("Turn", "Ikkander", "ᛃ", "Jera", "trs", "30 ft", dict(kind="save", save="str", effect=None, dmg=None, note="On a failure the target is turned 90 degrees and moved up to 10 feet, or one missile or inscription's next target is redirected."),
     "Turn the cycle. A creature or object that fails a Strength save is pushed up to 10 feet and turned, or the next use of a rune or missile aimed at it is redirected to another valid target."),
    ("Root", "Vaelweyr", "ᛟ", "Othala", "trs", "30 ft", dict(kind="save", save="str", effect=dict(name="Rooted", changes=[("system.attributes.movement.walk", "0", 5)], rounds=2, desc="Rooted: speed 0 until the end of its next turn."), dmg=None),
     "Anchor something to the ground. A creature that fails a Strength save has its feet held fast: speed 0 until the end of its next turn. Alternatively, anchor a door, cart, or object so it cannot be moved for 1 hour."),
    ("Breath", "Vaelweyr", "ᚨ", "Ansuz", "trs", "touch", dict(kind="effect", effect=dict(name="Clean Breath", changes=[], rounds=600, desc="Clean Breath: can breathe normally in smoke, dust, gas or underwater (GM adjudicates exotic hazards).")),
     "Give a creature you touch good air for 1 hour: it can breathe in smoke, dust, gas, or underwater. The same rune can also clear stale air from a 10-foot space."),
    ("Track", "Vaelweyr", "ᚱ", "Raidho", "div", "touch", dict(kind="effect", effect=dict(name="On the Trail", changes=[("system.skills.sur.bonuses.check", "+1d4", 2), ("system.skills.prc.bonuses.check", "+1d4", 2)], rounds=600, desc="On the Trail: +1d4 to Survival and Perception checks to follow the marked trail.")),
     "Mark a trail. For 1 hour a creature you touch adds 1d4 to Survival and Perception checks to follow one chosen quarry, scent, or route you can describe."),
    ("Bloom", "Vaelweyr", "ᚠ", "Fehu", "trs", "touch", dict(kind="heal", dice=(1, 4), extra=" Plants and fungus sprout quickly around the touch."),
     "Coax growth. A creature you touch regains hit points as fungus, moss, or seedlings spring up around the wound or seam; or grow a patch of plants in a 5-foot area."),
    ("Sever", "Mwooreth", "ᚺ", "Hagalaz", "evo", "30 ft", dict(kind="save", save="dex", effect=None, dmg=dict(dice=(2, 6), type="force", on_save="half"), note="Cuts cords, locks, ties and links as readily as flesh."),
     "Cut one thing from another. A creature or object in range makes a Dexterity save, taking 2d6 force damage on a failure and half as much on a success. The same rune can sever one rope, chain, or inscription link."),
    ("Hunger", "Mwooreth", "ᚢ", "Uruz", "nec", "30 ft", dict(kind="save", save="con", effect=None, dmg=dict(dice=(1, 8), type="necrotic", on_save="half")),
     "Make a thing hunger. A creature in range makes a Constitution save, taking 1d8 necrotic damage on a failure and half as much on a success. Food, fuel, or rations in range may be consumed instead."),
    ("Silence", "Mwooreth", "ᛈ", "Perthro", "ill", "30 ft", dict(kind="save", save="con", effect=dict(name="Silenced", changes=[], rounds=10, desc="Silenced: cannot speak or cast spells with a verbal component; makes no sound for 1 minute."), dmg=None),
     "Take the sound out of something. A creature in range that fails a Constitution save is silenced for 1 minute. A door, object, or 10-foot space can be silenced for 1 hour."),
    ("False Hearth", "Mwooreth", "ᛊ", "Sowilo", "enc", "30 ft", dict(kind="save", save="wis", effect=dict(name="Drawn to the False Hearth", status="charmed", rounds=2, desc="Charmed: drawn toward a false warmth until the end of its next turn."), dmg=None),
     "Offer a warmth that is not there. A creature in range that fails a Wisdom save is charmed by a false sense of shelter and belonging until the end of its next turn, and is drawn toward the rune."),
]


def _act_base(aid, atype, name, **extra):
    a = {"_id": aid, "type": atype, "name": name, "img": None, "sort": 0,
         "activation": {"type": "action", "value": 1, "condition": "", "override": False},
         "consumption": {"scaling": {"allowed": False}, "spellSlot": False, "targets": []},
         "description": {"chatFlavor": ""}, "duration": {"units": "inst", "concentration": False, "override": False},
         "range": {"units": "self", "override": False},
         "target": {"template": {"contiguous": False, "stationary": False, "units": "ft"}, "affects": {"choice": False}, "prompt": True, "override": False},
         "uses": {"spent": 0, "recovery": []}, "effects": [], "flags": {},
         "visibility": {"level": {}, "requireAttunement": False, "requireIdentification": False, "requireMagic": False}}
    a.update(extra)
    return a


def build_rune(name, trad, glyph, rname, school, rng, spec, text):
    ident = "rune-" + name.lower().replace(" ", "-")
    a_trace, a_fx, e_id = hid("rune", name, "trace"), hid("rune", name, "fx"), hid("rune", name, "effect")
    trace = _act_base(a_trace, "utility", f"Trace {name} [1 charge]",
                      consumption={"scaling": {"allowed": False}, "spellSlot": False,
                                   "targets": [{"type": "itemUses", "target": POOL_ITEM, "value": "1", "scaling": {"mode": "", "formula": ""}}]},
                      roll={"formula": CHECK, "name": f"Runecrafting check ({name}) vs Wyrd DC", "prompt": False, "visible": False},
                      description={"chatFlavor": f"Spend 1 Rune Charge and make the Runecrafting check against the Wyrd DC (set by the GM) to trace {glyph} {rname}. On a success, use the effect activity."})
    effects, acts = [], {a_trace: trace}
    kind = spec["kind"]
    fx = None
    eff = spec.get("effect")
    if eff:
        ch = [{"key": c[0], "mode": c[2] if len(c) > 2 else 2, "value": c[1], "priority": None} for c in eff.get("changes", [])]
        effects.append({"_id": e_id, "name": eff["name"], "img": "icons/svg/aura.svg", "type": "base", "transfer": False, "disabled": False, "origin": None,
                        "duration": {"rounds": eff["rounds"], "seconds": None, "startRound": None, "startTime": None, "turns": None, "startTurn": None},
                        "changes": ch, "statuses": [eff["status"]] if eff.get("status") else [], "description": f"<p>{eff['desc']}</p>", "tint": "#ffffff", "flags": {}})
    rngd = {"units": "ft", "value": "30", "override": False} if rng == "30 ft" else {"units": "touch", "override": False}
    if kind in ("heal", "temphp"):
        n, d = spec["dice"]
        fx = _act_base(a_fx, "heal", f"{name}: {'temporary hit points' if kind == 'temphp' else 'restore hit points'}", range=rngd,
                       healing={"types": ["temphp" if kind == "temphp" else "healing"], "number": n, "denomination": d, "bonus": f"@abilities.{ABILITY}.mod",
                                "scaling": {"mode": "", "number": 1}, "custom": {"enabled": False}},
                       description={"chatFlavor": f"{glyph} {rname}: {name}." + spec.get("extra", "")})
        acts[a_fx] = fx
    elif kind == "save":
        dmg = spec.get("dmg")
        parts = []
        if dmg:
            n, d = dmg["dice"]
            parts = [{"number": n, "denomination": d, "bonus": "", "types": [dmg["type"]], "custom": {"enabled": False}, "scaling": {"mode": "", "number": 1}}]
        fx = _act_base(a_fx, "save", f"{name}: effect", range=rngd, save={"ability": [spec["save"]], "dc": {"calculation": "", "formula": DC}},
                       damage={"onSave": (dmg or {}).get("on_save", "none"), "parts": parts},
                       effects=[{"_id": e_id, "onSave": False}] if eff else [],
                       description={"chatFlavor": f"{glyph} {rname}: Runecrafting save DC (8 + proficiency + Wisdom)." + (" " + spec["note"] if spec.get("note") else "")})
        acts[a_fx] = fx
    elif kind == "effect":
        fx = _act_base(a_fx, "utility", f"{name}: apply effect", range=rngd, effects=[{"_id": e_id}], description={"chatFlavor": f"{glyph} {rname}: {eff['desc']}"})
        acts[a_fx] = fx
    else:
        fx = _act_base(a_fx, "utility", f"{name}: use", range=rngd, description={"chatFlavor": f"{glyph} {rname}: {text}"})
        acts[a_fx] = fx
    desc = (para(f"<strong>{glyph} {rname}</strong> &mdash; Root Rune of <strong>{trad}</strong>. Tier I.") + para(text) +
            para("<em>Learned only after Stellan discovers and studies this glyph. Use the first activity (1 Rune Charge) to trace the rune and roll the Runecrafting check against the GM's Wyrd DC; "
                 "on a success, use the effect activity. The save DC is 8 + proficiency + Wisdom.</em>"))
    return {
        "_id": hid("rune", name, "item"), "name": f"Rune: {name} ({trad})", "type": "spell", "img": "icons/svg/aura.svg",
        "system": {"source": SRC, "description": {"value": desc, "chat": ""}, "level": 0, "school": school, "properties": ["somatic", "material"],
                   "materials": {"value": "chalk, ink, or a carving tool", "consumed": False, "cost": 0, "supply": 0},
                   "target": {"template": {"count": "", "contiguous": False, "type": "", "size": "", "width": "", "height": "", "units": "ft", "stationary": False},
                              "affects": {"count": "1", "type": "", "choice": False, "special": ""}},
                   "range": {"value": "30" if rng == "30 ft" else "0", "units": "ft" if rng == "30 ft" else "touch"},
                   "activation": {"type": "action", "value": 1, "condition": ""}, "duration": {"value": "", "units": "inst"},
                   "uses": {"max": "", "spent": 0, "recovery": []}, "method": "spell", "prepared": 1, "sourceItem": "", "activities": acts, "identifier": ident},
        "effects": effects, "folder": None, "sort": 0, "ownership": {"default": 0}, "flags": {"varrenmoor": {"tradition": trad, "glyph": rname}},
    }


if __name__ == "__main__":
    items = [build_rune(*r) for r in RUNES]
    out = json.dumps(items, indent=2, ensure_ascii=False)
    (ROOT / "spells").mkdir(exist_ok=True)
    (ROOT / "spells" / "Runes_FoundryVTT.json").write_text(out, encoding="utf-8")
    (SHARE / "Foundry JSON").mkdir(exist_ok=True)
    (SHARE / "Foundry JSON" / "Runes_FoundryVTT.json").write_text(out, encoding="utf-8")
    print("wrote", len(items), "rune spells")


# ------------------------------------------------------------------------------------------------ First Hearth Rite (greater inscription)
def build_first_hearth_rite():
    """The First Hearth Rite (VRM-S02, level 1 spell found in the chest at the old church ruins) as a Runecrafting working for Stellan.
    Level gate: 7. It protects whole thresholds for 8 hours, which is a large Tier III inscription: the progression table gives 'large or living inscriptions;
    alter Tier III rune-work' at level 7, and level 6 only allows temporary three-rune sentences lasting to the next long rest. It is also single use with no recovery."""
    a_rite, a_save, e_id = hid("rune", "first-hearth", "rite"), hid("rune", "first-hearth", "save"), hid("rune", "first-hearth", "effect")
    wyrd = 22
    rite = _act_base(a_rite, "utility", "Perform the First Hearth Rite [2 charges, single use]",
                     activation={"type": "minute", "value": 10, "condition": "", "override": False},
                     range={"units": "touch", "override": False},
                     duration={"value": "8", "units": "hour", "concentration": False, "override": False},
                     consumption={"scaling": {"allowed": False}, "spellSlot": False,
                                  "targets": [{"type": "itemUses", "target": "", "value": "1", "scaling": {"mode": "", "formula": ""}},
                                              {"type": "itemUses", "target": POOL_ITEM, "value": "2", "scaling": {"mode": "", "formula": ""}}]},
                     roll={"formula": CHECK, "name": f"Runecrafting check vs Wyrd DC {wyrd}", "prompt": False, "visible": False},
                     visibility={"level": {"min": 7, "max": None}, "requireAttunement": False, "requireIdentification": False, "requireMagic": False},
                     description={"chatFlavor": f"Ten minutes of careful work. Check against Wyrd DC {wyrd} (GM may raise it if a required glyph or material is missing). The rite is spent whether or not it takes. "
                                                "On a success, up to three connected thresholds are marked for 8 hours."})
    save = _act_base(a_save, "save", "Mimicked voice at the threshold", range={"units": "ft", "value": "60", "override": False},
                     save={"ability": ["wis"], "dc": {"calculation": "", "formula": DC}}, damage={"onSave": "none", "parts": []},
                     effects=[{"_id": e_id, "onSave": False}],
                     visibility={"level": {"min": 7, "max": None}, "requireAttunement": False, "requireIdentification": False, "requireMagic": False},
                     description={"chatFlavor": "A creature mimicking a voice across the protected threshold: its disguise falters on a failed save (shadow bends the wrong way, breath vanishes, or its answer fails a local custom)."})
    eff = {"_id": e_id, "name": "Voice Falters", "img": "icons/svg/aura.svg", "type": "base", "transfer": False, "disabled": False, "origin": None,
           "duration": {"rounds": 10, "seconds": None, "startRound": None, "startTime": None, "turns": None, "startTurn": None}, "changes": [],
           "statuses": [], "description": "<p>Its mimicry fails: the shadow bends the wrong way, the breath vanishes, or the answer fails a local custom.</p>", "tint": "#ffffff", "flags": {}}
    desc = (para("<strong>First Hearth Rite</strong> (greater inscription). Found in the chest at the old church ruins. A Runecrafting working of <strong>Eirwyn</strong>: Preserve + Threshold + Reveal.") +
            para("You mark a doorway, window, or other threshold with an older rite of preservation and naming. For 8 hours, creatures of the Nox and similar voice-stealing shadow spirits cannot enter "
                 "through a protected threshold unless a creature inside knowingly invites them by name. A creature attempting to mimic a voice across the threshold must succeed on a Wisdom saving throw "
                 "or its disguise falters. The rite does not bar ordinary villagers, beasts, or invited guests; it strengthens the truth of a threshold rather than creating a wall. "
                 "Up to three connected thresholds can be protected.") +
            para("<strong>Components.</strong> Ash from a true hearth, clean water or snowmelt, a nail or iron filing from the protected door, a living sprig of evergreen, and the spoken name of someone the household refuses to forget (all consumed).") +
            para(f"<strong>Stellan's limits.</strong> Not possible before character level 7 (a large Tier III inscription: Deep Inscription, 2 Rune Charges). He must know the Preserve, Threshold and Reveal glyphs. "
                 f"Runecrafting check against Wyrd DC {wyrd}. <strong>One use only, with no recovery</strong>: the rite is spent when attempted."))
    return {
        "_id": hid("rune", "first-hearth", "item"), "name": "First Hearth Rite (Greater Inscription)", "type": "spell", "img": "icons/svg/aura.svg",
        "system": {"source": {"custom": "Varrenmoor Session 2: The Night of the Nox", "book": "VRM-S02", "page": "", "license": "", "rules": "2014", "revision": 1},
                   "description": {"value": desc, "chat": ""}, "level": 3, "school": "abj", "properties": ["vocal", "somatic", "material"],
                   "materials": {"value": "ash from a true hearth, clean water or snowmelt, a nail or iron filing from the protected door, a living sprig of evergreen, and the spoken name of someone the household refuses to forget",
                                 "consumed": True, "cost": 0, "supply": 0},
                   "target": {"template": {"count": "", "contiguous": False, "type": "", "size": "", "width": "", "height": "", "units": "ft", "stationary": False},
                              "affects": {"count": "3", "type": "", "choice": False, "special": "connected thresholds"}},
                   "range": {"value": "0", "units": "touch"}, "activation": {"type": "minute", "value": 10, "condition": ""}, "duration": {"value": "8", "units": "hour"},
                   "uses": {"max": "1", "spent": 0, "recovery": []}, "method": "spell", "prepared": 1, "sourceItem": "",
                   "activities": {a_rite: rite, a_save: save}, "identifier": "first-hearth-rite-greater"},
        "effects": [eff], "folder": None, "sort": 0, "ownership": {"default": 0},
        "flags": {"varrenmoor": {"tradition": "Eirwyn", "minLevel": 7, "singleUse": True}},
    }


if __name__ == "__main__":
    fh = build_first_hearth_rite()
    (ROOT / "spells" / "First_Hearth_Rite_FoundryVTT.json").write_text(json.dumps(fh, indent=2, ensure_ascii=False), encoding="utf-8")
    (SHARE / "Foundry JSON" / "First_Hearth_Rite_FoundryVTT.json").write_text(json.dumps(fh, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote First Hearth Rite")
