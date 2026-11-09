"""Venfyura (Violet's grandmother, an Eirwitch): build out the existing live actor 'Fortune Teller' (Actor.afVUI68BonsDF1a7) in place.

The GM confirmed that the Market of Transients 'Fortune Teller' actor IS Venfyura. This script renames it and fills it with a
2024-style NPC stat block, cloned 2024 spell items, and the native reference features (no activities) the other Ossuary NPCs use.

Sources: gm-guide/Varrenmoor_NPC_Dialogue_GM_Reference.md ('VENFYURA', Parts 1.3, 1.5, 1.6, 4, 5),
Varrenmoor_Campaign_Full_Handoff.md (Session 7 row, Violet, story threads), gm-guide/Session_14_Cladis_Return_Conspiracy.md,
gm-guide/Session_14_New_NPCs_Spec.md, gm-guide/Europa_New_PC_Hook_and_Backstory.md.

    python foundry-json/venfyura_npc.py           # write foundry-json/actors/Venfyura_FoundryVTT.json only
    python foundry-json/venfyura_npc.py --push    # also update the live actor (and only that actor)

Only Actor.afVUI68BonsDF1a7 is written. Its folder, img, ownership and prototype-token art/3D flags are left as they are.
The actor gets flags.varrenmoor.pipelineId = npc:ossuary:venfyura; each item gets npc:ossuary:venfyura:<slug>, so a re-run updates
items instead of duplicating them. Spell items are cloned (read-only get) from the 2024 spell items already on the PC sheets
(Stellan, Violet): there is no compendium-list op on the bridge. Backups: foundry-3d/ai/characters/venfyura/actor_backup_before.json
(written once, never overwritten) and actor_after.json.
"""
import copy
import json
import re
import sys
from pathlib import Path

from fvtt import ROOT, hid, npc, p

sys.path.insert(0, str(ROOT))
import session14_npcs as s14  # noqa: E402
from session14_npcs import bridge, fix_53, h, ul  # noqa: E402

ACTOR = "Actor.afVUI68BonsDF1a7"
TAG = "npc:ossuary:venfyura"
NAME = "Venfyura, Witch of the Market of Transients"
SRC = "Varrenmoor DM Guide (NPC Reference: Venfyura; Part 7, Session 14)"
HABITAT = "Market of Transients (Session 7); the Eirwitch camp above Bridgehollow (Session 14-15)"
DOC = s14.DOC
BACKUP = ROOT.parent / "foundry-3d" / "ai" / "characters" / "venfyura"
A = "Venfyura"

STELLAN, VIOLET = "Actor.CMKxYYzoE9nZILWs", "Actor.PJ8bhdjjjtpnT0Pz"
# (name, source actor, item id, method, uses per day or None)
SPELLS = [
    ("Light", STELLAN, "gcUxO1Fo3XuJHWoy", "spell", None),
    ("Mending", STELLAN, "rNIp35j2BlLcdLt0", "spell", None),
    ("Starry Wisp", VIOLET, "EzHOameF0v7q1faL", "spell", None),
    ("Detect Magic", STELLAN, "nNS0ypGgkZ5zekZC", "atwill", None),
    ("Gentle Repose", STELLAN, "NVRYtqP47q8w3Jmf", "innate", 2),
    ("Lesser Restoration", STELLAN, "kLbOxUYCUKVJlYdT", "innate", 2),
    ("Sanctuary", STELLAN, "SMLJrLl6lBvllLqP", "innate", 2),
    ("Calm Emotions", STELLAN, "6804iVG2Z0QV921J", "innate", 1),
    ("Locate Object", STELLAN, "pwYO7n1HTVWT2vI1", "innate", 1),
]
SPELLCASTING = "Spellcasting"


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def gm(text):
    """GM-only text as a Foundry secret block (same pattern as session14_items.py)."""
    return f'<section class="secret" id="secret-{hid("venfyura-secret", text)}"><p><strong>GM note.</strong> {text}</p></section>'


def ref(name, html, sort):
    it = s14.feat(A, name, html, sort, img=DOC)
    it["system"]["source"]["custom"] = SRC
    return it


def trait(name, html, sort, img="icons/svg/aura.svg"):
    it = s14.feat(A, name, html, sort, img=img)
    it["system"]["source"]["custom"] = SRC
    return it


# ------------------------------------------------------------------------------------------------ spellcasting text
def spell_list_html(links=None):
    L = links or {}
    nm = lambda n: L.get(n, f"<em>{n}</em>")  # noqa: E731
    return (p("Venfyura casts one of the following spells, requiring no Material components and using <strong>Wisdom</strong> as the spellcasting ability "
              "(<strong>spell save DC 14</strong>, <strong>+6</strong> to hit with spell attacks):")
            + ul(f"<strong>At will:</strong> {nm('Detect Magic')}, {nm('Light')}, {nm('Mending')}, {nm('Starry Wisp')}",
                 f"<strong>2/day each:</strong> {nm('Gentle Repose')}, {nm('Lesser Restoration')}, {nm('Sanctuary')}",
                 f"<strong>1/day each:</strong> {nm('Calm Emotions')}, {nm('Locate Object')}")
            + p("<em>Theme (Eirwyn: water, ice, light; weaving, healing, preservation. Root runes Preserve, Mend, Reveal, Threshold):</em> light and mending, "
                "keeping the dead whole (Gentle Repose), healing, finding what is lost, and a guarded threshold (Sanctuary). The list is a build choice, not canon.")
            + gm("Spells are real dnd5e 2024 spell items on this sheet (method at will / innate with per-day uses). Her one damaging option is Starry Wisp "
                 "(1d8 radiant, +6, 60 ft). She is not a combatant: she shields, calms, mends and leaves."))


# ------------------------------------------------------------------------------------------------ items
ITEMS = [
    trait("Fey Ancestry", p("Venfyura has advantage on saving throws she makes to avoid or end the <strong>charmed</strong> condition."), 100000),
    trait("Trance", p("She doesn't need to sleep, and magic can't put her to sleep. She can finish a long rest in 4 hours in a meditative trance, during which she stays conscious."), 200000),
    trait("Old Hands (tool feature)", p("<strong>Herbalism kit and weaver's tools (proficient).</strong> The working tools of an Eirwyn witch: preparing, preserving and binding. "
                                       "Narrative use: she can identify, prepare and tie off the materials the party carries (restoration materials; the line's far end)."),
          300000, img="icons/svg/book.svg"),
    ref(SPELLCASTING, spell_list_html(), 400000),
    ref("GM Reference: Venfyura, Voice and Barks",
        h("Venfyura, Eirwitch (Violet's grandmother)") + p("<em>\"Names are the only thing I carry that cannot be taken.\"</em>")
        + p("<strong>Snapshot.</strong> An Eirwitch who travels the Wyrd. Knows the four lost crafts, the true nature of Mwooreth, Violet's grandmother's story, "
            "and how to preserve names and souls. Watches the egg closely.")
        + p("<strong>Voice.</strong> Quiet, patient, deliberate. Speaks like someone <em>choosing which truth to say today</em>. Says \"little one\" to Violet and rarely uses a name.")
        + p("<strong>Wants / fears.</strong> Wants the four crafts rediscovered and the egg safe. Fears what she withdrew from.")
        + "<h3>Barks</h3>" + ul(
            "\"Slowly. Truths keep.\"",
            "\"You are all carrying pieces of something unfinished.\"",
            "\"That one is important. Do not lose it.\"",
            "\"Ask the question you actually mean.\"",
            "<em>(to Stellan)</em> \"The egg has a use for you. It does not say what.\"")
        + p("<strong>At the table:</strong> she is not a combatant. Her value is knowledge and craft. If a fight starts she shields (Sanctuary), calms (Calm Emotions) or simply is not there.")
        + p("<strong>What others say about her:</strong> Mavis [ASK] <em>\"I recognize the line. Violet's line. Her contempt is about desertion, not skill. Do not mistake the two.\"</em> "
            "(Mavis's contempt concerns desertion and moral choices, not Venfyura's magical skill.)"),
        500000),
    ref("GM Reference: Venfyura, Questions and Answers",
        h("Questions and Answers (by tag)")
        + ul("<strong>Are you Violet's grandmother?</strong> [ASK] \"Yes. It is not the whole truth. It is <em>true</em>.\"",
             "<strong>What are the four crafts?</strong> [ASK] Lists them simply (see <em>Lore Reference: The Four Lost Crafts</em>).",
             "<strong>What is Mwooreth, really?</strong> [ASK] \"Severance. It is a craft. The cutting was not the sin. The <em>using</em> was.\"",
             "<strong>What's the Seam-Wheel?</strong> [ASK] \"A diagram. Not a door. It is a key for reading the Wyrd.\"",
             "<strong>Can Bones be restored?</strong> [ASK] \"Yes, if his name and some of him survive. Linen, water, a seed of life, a rune of boundary, needle, anchors. I can list them again.\"",
             "<strong>What's the egg?</strong> [EARN] \"It will have a use for 'the son of Håkon.' I will not say more until he asks me properly.\"",
             "<strong>The war, the Old Ways</strong> [EARN] She was <em>there for the truth of the Old Ways</em>. She knows the four lost crafts and the true nature of Mwooreth: "
             "<strong>severance is a craft, not a sin.</strong>",
             "<strong>Why did you leave?</strong> [EARN] <strong>[UNSETTLED]</strong> Mavis's contempt concerns <em>desertion</em>. Decide Venfyura's reason before she answers.",
             "<strong>Is Violet a Spring Queen?</strong> [SECRET] A <strong>later plan</strong> and not settled. Don't assert it.")
        + p("<strong>Quick finder:</strong> Who restores a skeleton? Pringus, Venfyura (ASK). What is Mwooreth? Venfyura, Quill (ASK). What is the egg? Venfyura (EARN).")
        + p("<strong>Not hers to answer:</strong> who hanged the Allfather, who cut the missing sentence, Stellan's family's role, the Great Tangle (SECRET; never told directly)."),
        600000),
    ref("Lore Reference: The Four Lost Crafts",
        h("The Four Lost Crafts (Part 1.6)") + p("Each craft is a blend of two relationships. <strong>Venfyura knows all four</strong>; the trainers know their own and only recognize the others.")
        + ul("<strong>Stellan: Runecraft</strong> (Mwooreth + Ikkander). <em>Mwooreth makes the cut. Ikkander gives the order.</em> A carved rune can influence the Wyrd.",
             "<strong>Betsy: Splicing</strong> (Ikkander + Vaelweyr). It chooses a viable biological continuation drawn from adjacent strands.",
             "<strong>Violet: Starweaving / Lifeweaving</strong> (Vaelweyr + Eirwyn). It guides life-force through plants and fungi only.",
             "<strong>Dale: Essencecraft</strong> (Eirwyn + Mwooreth). It separates, preserves and recombines the essence a thing actually has.")
        + p("[ASK] She lists them simply. <strong>Rule:</strong> trainers teach what the PC's sheet already has and grant no extra charges; Venfyura explains, she does not grant.")
        + p("<strong>Eirwyn</strong> (her own relationship): water, ice, light; weaving, healing, preservation (identity and preservation). Root runes: Preserve, Mend, Reveal, Threshold."),
        700000),
    ref("Lore Reference: Mwooreth and the Old Ways",
        h("Mwooreth and the Old Ways") + p("[ASK] <em>\"Severance. It is a craft. The cutting was not the sin. The using was.\"</em>")
        + p("[EARN] She was <em>there for the truth of the Old Ways</em>. Where villagers repeat the cover story literally (\"Old church stuff. Bad times.\") and Pringus has only custody records, "
            "she knows the four lost crafts and the true nature of Mwooreth: <strong>severance is a craft, not a sin.</strong>")
        + p("<strong>Graveyards (Part 1.5):</strong> all three traditions were active at the same time; they were <em>concealed</em>, not replaced.")
        + gm("Cladis's war against Nior is not placed on the history chart [UNSETTLED]. Who made the Mwooreth cut, why, and Stellan's family's role are SECRET and not defined: "
             "she does not answer them."),
        800000),
    ref("Lore Reference: Restoring Bones",
        h("Restoring Private / Sergeant Bones") + p("[ASK] <em>\"Yes, if his name and some of him survive. Linen, water, a seed of life, a rune of boundary, needle, anchors. I can list them again.\"</em>")
        + ul("Burial linen", "Water (distilled)", "A seed of life", "A rune of boundary", "Needle (and thread)", "Anchors (identity anchors)")
        + p("<strong>Session 7 (Market of Transients):</strong> she discussed Bones and the restoration materials. Bones was counted and inventoried, including marrow and name; "
            "at least one toe/remnant serves the claim. Kenko holds a recovered remnant as evidence and anchor, not ownership.")
        + p("<strong>Who restores a skeleton?</strong> Pringus, Venfyura (ASK). The Exchange's claim process (Pringus) stays separate from restoration; "
            "Ysolde Harrowgate takes Bones's restoration at cost once the Thaw's operation is done (Session 14)."),
        900000),
    ref("Lore Reference: The Seam-Wheel",
        h("The Seam-Wheel") + p("[ASK] <em>\"A diagram. Not a door. It is a key for reading the Wyrd.\"</em>")
        + p("A carving that diagrams how the four relationships and the four crafts relate. It is a <em>key to the Wyrd</em>, <strong>not</strong> the entrance to the Ragged Mile (Part 1.5).")
        + gm("The Great Tangle is a multi-plane mystery and the PCs hold four inherited pieces of an unfinished solution. Never tell them this directly. "
             "Her bark \"You are all carrying pieces of something unfinished\" is as close as she goes."),
        1000000),
    ref("Lore Reference: The Egg and the Son of Håkon",
        h("The Egg") + p("[EARN] <em>\"It will have a use for 'the son of Håkon.' I will not say more until he asks me properly.\"</em>")
        + p("<em>(to Stellan)</em> \"The egg has a use for you. It does not say what.\"")
        + p("The unknown warm egg came from the marble/brass chest (Session 5) with Maerwyn's Diary and a map fragment. In Session 7 she discussed its significance for the \"son of Håkon\" "
            "(Stellan Håkonsson) and <strong>watches the egg closely</strong>. She wants the egg safe. Mavis wants it (leverage).")
        + gm("The egg's nature and use are unresolved story threads. \"Asks me properly\" is the gate; what she says then is not written yet."),
        1100000),
    ref("Lore Reference: Violet, the Amulet and the Chart",
        h("Violet, the Amulet and the Chart") + p("[ASK] <em>\"Yes. It is not the whole truth. It is true.\"</em> She calls Violet \"little one\".")
        + ul("Violet's breadcrumbs: her <strong>grandmother's amulet and chart</strong>, ancestral stars (Session 5: touching Kenko and the amulet, Violet alone saw a nighttime meadow and ancestral stars).",
             "Session 7: Venfyura discussed <strong>Violet's chart</strong>.",
             "Mavis knew the family and the wedding, and recognizes Venfyura's line (Session 13).",
             "Violet's craft, Starweaving / Lifeweaving, is half Eirwyn: her grandmother's relationship.")
        + gm("Venfyura is Violet's grandmother and an Eirwitch (later correction; older 'separate from grandmother' notes are superseded). "
             "Possible Spring office and the consequences of her withdrawal are a later plan, not settled. <strong>Is Violet a Spring Queen?</strong> [SECRET] Don't assert it. "
             "<strong>Why did she leave?</strong> [UNSETTLED] Mavis's contempt concerns desertion. Decide the reason before she answers."),
        1200000),
    ref("GM Reference: The Woman at the Fire (Sessions 14-15)",
        h("The Woman at the Fire (Sessions 14-15)")
        + p("<strong>SETTLED:</strong> she is the \"lone ancient Eirwitch\" at the Eirwitch camp above Bridgehollow: a single campfire in a mountain clearing by a tall, narrow stave church, "
            "beside a deep river gorge where some frost never melts. She keeps the <strong>fire</strong> and the <strong>bell</strong>, and is the Thaw's partner on the far side. "
            "She keeps the fire burning by the stave church because a fire is the opposite of the palace: it is always changing.")
        + ul("<strong>Session 14 (off stage).</strong> The Thaw call her \"V.\" in writing and \"the woman at the fire\" aloud. Pell Ostry's old loyalty is to her; she uses his cold door. "
             "She grew the fungal culture Violet works with (Pell: \"the woman at the fire\"). Her word via Pell: the Goddess has noticed (\"She's looking\").",
             "<strong>Not revealed in Session 14.</strong> Pell and Quill never name her. Clues: Europa's memory (\"Not yet, little one\"), and Violet's Read Green Pattern on the culture "
             "(the same careful hand as her grandmother's chart, if Violet has met Venfyura). Revealed at the camp (Session 15).",
             "<strong>The far knot (Session 15).</strong> The party carries the far end out, recovers the bell's clapper (seized by the Bridgehollow authorities; Customs House), "
             "gets Venfyura's help, rings the Bell knock (four slow), lowers the line on its sinker, and ties it off at the gorge, <strong>with Venfyura</strong>.",
             "<strong>Settled canon around her:</strong> Cladis, the ancient Eirwitch Winter Queen, was banished outside the Wyrd, broke and shredded her own thread and re-tied it at the "
             "Rhime Goddess's Ice Palace. The Rhime Goddess has noticed; her name is <strong>Lakkar, Lady of Eternal Hunger</strong> (the Goddess writes it on the Stolen Shard in Session 14, Scene 7).")
        + gm("[SUGGESTED, not settled] Venfyura put Europa to sleep at the camp (\"Not yet, little one\") and Europa's brother carried her through the cold door. Why Venfyura did it is the GM's call. "
             "\"Little one\" is her canon address: don't confirm it early; Violet's player may recognize it. "
             "[UNSETTLED] How her role at the camp fits her canon withdrawal (Mavis: desertion). Don't resolve it at the camp unless decided. "
             "Whether the re-tie works and what Lakkar asks in return: Session 15 or later."),
        1300000),
    ref("GM Reference: Session 7, the Market of Transients",
        h("Session 7: the Market of Transients") + p("Where the party met her (as the market's \"Fortune Teller\"). In the same session: Gfefk Kfefg, <em>The Lantern Lad and the Road of Teeth</em>, "
                                                     "and Betsy's animal-holding music box and iron-bell trade (not Venfyura's).")
        + ul("She discussed <strong>Bones</strong> and the <strong>restoration materials</strong>.", "The <strong>four lost crafts</strong>.", "<strong>Violet's chart</strong>.",
             "The <strong>Seam-Wheel</strong>.", "The <strong>egg's significance for the \"son of Håkon\"</strong>; she watches the egg closely.",
             "Full moon in two nights; Bones counted and inventoried, including marrow and name.")
        + gm("No stock list for her is recorded in canon, so this actor has no Merchant Reference and no shop loot. Add one if she sold anything at the table."),
        1400000),
]


def build_actor():
    a = npc(NAME, 2, "med", "humanoid", "elf (Eirwyn)", 45, 12, (8, 14, 10, 16, 18, 13), {"walk": 30},
            hp_formula="10d8", senses={"darkvision": 60}, languages=("common", "elvish", "sylvan"),
            skills={"arc": 1, "his": 1, "ins": 2, "med": 1, "per": 1}, img="", token_img="", model="", tok_size="med", disposition=1, align="neutral",
            bio=p("<strong>Venfyura</strong> is an ancient Eirwitch who travels the Wyrd: quiet, patient and deliberate, she speaks like someone choosing which truth to say today. "
                  "The party met her at the Market of Transients, where she spoke of Bones, the four lost crafts, Violet's chart, the Seam-Wheel and the egg. "
                  "She is Violet's grandmother, and calls her \"little one\".")
            + p("<em>Appearance:</em> old (\"ancient\"); no further description is recorded in canon.")
            + gm("Built from the GM Reference 'VENFYURA' section and Part 7. Not a combatant: knowledge and craft. SETTLED: she is the woman at the fire at the Eirwitch camp "
                 "above Bridgehollow, the Thaw's far-side partner (\"V.\"); revealed at the camp in Session 15, never named by Pell or Quill in Session 14. "
                 "[UNSETTLED] her reason for withdrawing/leaving (Mavis: desertion). [SECRET] Spring Queen is a later plan only. "
                 "[SUGGESTED] she put Europa to sleep (\"Not yet, little one\")."),
            items=[])
    fix_53(a, ideal="Names are the only thing that cannot be taken; keep them.", bond="Violet (\"little one\"), the four crafts, and the egg's safety.",
           flaw="Withholds truths until she judges the question is asked properly.", saves=("int", "wis"),
           tools={"herb": (1, "wis"), "weaver": (1, "dex")}, lang_custom="Old Eirwyn script", darkvision=60,
           skills={"arc": 1, "his": 1, "ins": 2, "med": 1, "per": 1})
    a["folder"] = "OLuefHiZMZYoeS5z"                       # her existing folder (fix_53 sets the Ossuary one); not sent on push
    a["img"] = a["prototypeToken"]["texture"]["src"] = "systems/dnd5e/icons/svg/actors/npc.svg"   # live art, unchanged; not sent on push
    a["prototypeToken"]["flags"] = {}                       # live token flags (existing 3D model) are kept as they are; not sent on push
    s = a["system"]
    s["details"]["habitat"] = {"custom": HABITAT, "value": []}
    s["details"]["biography"]["public"] = p("Venfyura: an ancient Eirwitch, quiet and deliberate. Met at the Market of Transients.")
    s["source"].update(custom=SRC, rules="2024")
    s["attributes"]["spellcasting"] = "wis"
    s["attributes"]["spell"] = {"level": 0}
    for it in ITEMS:
        it["flags"] = {"varrenmoor": {"pipelineId": f"{TAG}:{slug(it['name'])}"}}
    a["items"] = ITEMS
    return a


def clone_spell(name, src_actor, src_id, method, per_day, sort):
    doc = bridge("get", uuid=f"{src_actor}.Item.{src_id}")
    assert doc["name"] == name and doc["type"] == "spell", (name, doc["name"])
    it = copy.deepcopy(doc)
    for k in ("_id", "_stats", "folder"):
        it.pop(k, None)
    it["ownership"] = {"default": 0}
    it["sort"] = sort
    it["flags"] = {"varrenmoor": {"pipelineId": f"{TAG}:spell:{slug(name)}"}}
    sy = it["system"]
    sy.pop("sourceItem", None)
    sy["method"] = method
    sy["prepared"] = 1
    sy["ability"] = "wis"
    sy["properties"] = [x for x in sy.get("properties", []) if x != "material"]
    sy["materials"] = {"value": "", "consumed": False, "cost": 0, "supply": 0}
    if per_day:
        sy["uses"] = {"max": str(per_day), "recovery": [{"period": "day", "type": "recoverAll"}], "spent": 0}
        for act in sy["activities"].values():
            c = act.setdefault("consumption", {"scaling": {"allowed": False}, "spellSlot": True, "targets": []})
            if not any(t.get("type") == "itemUses" for t in c.get("targets", [])):
                c.setdefault("targets", []).append({"target": "", "value": "1", "type": "itemUses", "scaling": {}})
    else:
        sy["uses"] = {"max": "", "spent": 0, "recovery": []}
    return it


# ------------------------------------------------------------------------------------------------ push (this actor only)
def push(a):
    BACKUP.mkdir(parents=True, exist_ok=True)
    before = BACKUP / "actor_backup_before.json"
    live = bridge("get", uuid=ACTOR)
    if not before.exists():
        before.write_text(json.dumps(live, indent=2, ensure_ascii=False), encoding="utf-8")
    assert live["type"] == "npc"

    upd = {
        "name": NAME,
        "system": a["system"],
        "prototypeToken": {"name": "Venfyura", "disposition": 1, "displayName": 20,
                           "sight": {"enabled": True, "range": 60, "visionMode": "darkvision"}},
        "flags": {"varrenmoor": {"pipelineId": TAG}},
    }   # folder, img, ownership, token texture and token flags (existing 3D model) are deliberately not sent
    print("actor:", bridge("update", uuid=ACTOR, data=upd))

    def by_tag():
        doc = bridge("get", uuid=ACTOR)
        return {((i.get("flags") or {}).get("varrenmoor") or {}).get("pipelineId"): i for i in doc["items"]}

    def put(it):
        ex = by_tag().get(it["flags"]["varrenmoor"]["pipelineId"])
        data = json.loads(json.dumps(it))
        data.pop("_id", None)
        if ex:
            return bridge("update", uuid=f"{ACTOR}.Item.{ex['_id']}", data=data)
        return bridge("create", documentName="Item", parentUuid=ACTOR, data=data)

    for it in a["items"]:
        print(" ", it["name"], put(it))
    for n, (name, src, sid, method, per_day) in enumerate(SPELLS):
        print("  spell", name, put(clone_spell(name, src, sid, method, per_day, 2000000 + n * 1000)))

    # link the Spellcasting feature's list to the spell items now that their ids exist
    cur = by_tag()
    links = {}
    for name, *_ in SPELLS:
        sp = cur[f"{TAG}:spell:{slug(name)}"]
        links[name] = f"@UUID[{ACTOR}.Item.{sp['_id']}]{{{name}}}"
    sc = cur[f"{TAG}:{slug(SPELLCASTING)}"]
    bridge("update", uuid=f"{ACTOR}.Item.{sc['_id']}", data={"system": {"description": {"value": spell_list_html(links)}}})

    after = bridge("get", uuid=ACTOR)
    (BACKUP / "actor_after.json").write_text(json.dumps(after, indent=2, ensure_ascii=False), encoding="utf-8")
    pt = after["prototypeToken"]
    print("READBACK name:", after["name"], "| folder:", after["folder"], "| CR:", after["system"]["details"]["cr"],
          "| token:", pt["name"], pt["disposition"], pt["texture"]["src"], ((pt.get("flags") or {}).get("levels-3d-preview") or {}).get("model3d"))
    print("READBACK items:", len(after["items"]), [f"{i['type']}:{i['name']}" for i in after["items"]])


if __name__ == "__main__":
    actor = build_actor()
    out = ROOT / "actors" / "Venfyura_FoundryVTT.json"
    out.write_text(json.dumps(actor, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", out, len(actor["items"]), "items (+", len(SPELLS), "cloned spells on push)")
    if "--push" in sys.argv:
        push(actor)
