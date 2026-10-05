"""Quest content from the GM reference, Part 6 (three side quests from the inn): actors for Gerald, Dunmore Kell and Tobias Wren,
and every clue/prop as a loot item. Run:  python foundry-json/quest_content.py
"""
import copy
import json

from fvtt import SHARE, ROOT, feat, hid, npc, p, save, save_feat, utility, weapon

TOK = "assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Tokens"
PEOPLE = dict(ctype="humanoid", subtype="human")

# ------------------------------------------------------------------------------------------------ actors
ACTORS = []

A = "Gerald"
ACTORS.append(("gerald", npc(
    "Gerald", 0, "tiny", "beast", "turtle", 3, 12, (2, 14, 10, 2, 12, 3), {"walk": 20, "climb": 20, "swim": 20},
    hp_formula="1d4+1", senses={"darkvision": 30}, img="icons/svg/mystery-man.svg", token_img="icons/svg/mystery-man.svg",
    model="token_gerald.glb", tok_size="tiny", disposition=0, scale=1.0,
    bio=p("<strong>Gerald</strong> is a small soft-shelled turtle, one of Doctor Pimm's patients: leathery shell, long grippy tongue, and extra climbing toes on a bonus pair of feet. "
          "He escaped into the Exchange's conveyor shafts with Pimm's field notebook. He is skittish, harmless and very good at ducking into pipes.")
    + p("<strong>GM notes (Quest 2, 'Gerald Has the Notebook').</strong> Do not use him as a combat threat. To catch him: <strong>Animal Handling DC 12</strong> (or a calming approach) when "
        "he is cornered in the Lost Property annex, curled around the notebook. Biscuit can scout. His noise in the shafts is <em>erratic and scratchy</em>; he does not keep hours, so whatever "
        "knocks on a schedule is not Gerald (see 6.4). Pimm: <em>'Gerald is not dangerous. Gerald is annotated.'</em>"),
    items=[
        feat(A, "Annotated", p("Gerald carries a faint stamp of Doctor Pimm's clinic on his shell, and a chewed clinic tag is never far behind him."), 100000),
        feat(A, "Bonus Feet", p("Gerald has six legs. He can climb difficult surfaces, including upside down on ceilings, without needing to make an ability check. "
                                "He can squeeze through a space as narrow as 3 inches."), 200000),
        weapon(A, "Grippy Tongue", p("<em>Melee Weapon Attack:</em> reach 10 ft., one target. <em>Hit:</em> 1 bludgeoning damage. Gerald can instead use the tongue to snatch a "
                                     "loose object of 1 pound or less within 10 feet (such as a notebook)."), 300000, "dex", 0, 4, "bludgeoning", bonus="1", reach=10),
    ])))

A = "Dunmore Kell"
ACTORS.append(("dunmore_kell", npc(
    "Dunmore Kell, Night Porter", 0.125, "med", PEOPLE["ctype"], PEOPLE["subtype"], 9, 10, (12, 10, 12, 10, 10, 9), {"walk": 30},
    hp_formula="2d8", senses={}, img="icons/svg/mystery-man.svg", token_img="icons/svg/mystery-man.svg", languages=("common",),
    model="token_dunmore_kell.glb", tok_size="med", disposition=0, align="neutral",
    bio=p("<strong>Dunmore Kell</strong> is a night porter lodging in room 207. He is tired, underpaid and not malicious. He named a dead rat 'S. Rattus, Custodian (Acting)' so that an amended "
          "warehouse door in the Lower market would let him wheel unlisted small bones through at night.")
    + p("<strong>GM notes (Quest 1, 'The Rat on the Door Plate').</strong> Insight or Persuasion <strong>DC 12</strong> gets a full confession. He is a <em>petty offender</em>, not the note-leaver: he "
        "uses the door and a bone cart (wheels and boots, never tubes). If asked about the tubes: <em>'The tubes aren't mine. Something clunks down that old terminal at the same hour every night. "
        "I don't go near it.'</em> That clears him and points at the real lead (6.4). Fix options: Stellan's Trace Rune / Countermark with Quill (DC 11), a paper fix with Pringus, or report him "
        "(lenient)."),
    items=[
        feat(A, "Night Porter's Rounds", p("Kell knows the Lower market's back doors, the shaft hatches and the loading routes. He has advantage on checks to move unnoticed after dark."), 100000),
        feat(A, "Tired and Underpaid", p("If treated kindly, he confesses freely. A sympathetic remark about the pay gives advantage on any check to get the truth out of him."), 200000),
        weapon(A, "Cudgel", p("<em>Melee Weapon Attack:</em> reach 5 ft., one target. <em>Hit:</em> 1d4 + 1 bludgeoning damage. He would very much rather not."), 300000, "str", 1, 4, "bludgeoning"),
    ])))

A = "Tobias Wren"
ACTORS.append(("tobias_wren", npc(
    "Tobias Wren, Former Gravewright", 0, "med", PEOPLE["ctype"], PEOPLE["subtype"], 11, 10, (9, 8, 10, 14, 13, 12), {"walk": 25},
    hp_formula="2d8+2", senses={}, img="icons/svg/mystery-man.svg", token_img="icons/svg/mystery-man.svg", languages=("common",),
    model="token_tobias_wren.glb", tok_size="med", disposition=1, align="neutral good",
    skills={"med": 1, "rel": 1},
    bio=p("<strong>Tobias Wren</strong> has lodged in room 6 (206 on the Foundry map) for 43 years and disputes the bill because his body was replaced. He is gentle, sad, with an excellent memory "
          "for detail. He talks to a chair: the old body's favourite chair.")
    + p("<strong>GM notes (Quest 3, 'The Man in Room 6').</strong> <em>Insight DC 11:</em> he is not lying. He feels like a different man and is also the same one. "
        "<em>'The old body wore out. The new one fits badly. I remember everything. That's the problem. I remember it as someone else.'</em> A <strong>bone tag</strong> under a floorboard "
        "(Perception DC 12) is his original identity anchor. The twist: the custody ledger shows the body was at a licensed restoration house for six years, so those years are custody costs, not "
        "lodging. Reward: his <strong>stamped referral card</strong>, handed over in person, and the advice <em>'They will ask for the name three times. Bring the name.'</em> Backstory (suggested): "
        "<em>'Three graveyards. All three tended the same week. The tenders never spoke, but they left each other bread.'</em>"),
    items=[
        feat(A, "Perfect Recall", p("Wren remembers every detail of his decades in the room and of the graves he dug. He has advantage on checks to recall specifics, and anything he says about the past is accurate."), 100000),
        feat(A, "Gravewright's Eye", p("He is proficient in Medicine and Religion, and can tell at a glance how long remains have lain and who tended them."), 200000),
        feat(A, "Continuing Claimant", p("Name persists, so he is the same man. Three records must agree (intake, custody, tag). Wren notes that two out of three is a rumor."), 300000),
    ])))

# ------------------------------------------------------------------------------------------------ loot items
LOOT = []


def loot(name, player_text, gm_text, quest, img="icons/svg/book.svg"):
    it = {
        "_id": hid("quest", name, "item"), "name": name, "type": "loot", "img": img,
        "system": {
            "description": {"value": p(player_text), "chat": ""},          # player-facing only: no GM notes, so it can be dragged to a character sheet
            "source": {"custom": "Varrenmoor DM Guide, Part 6", "book": "", "page": "", "license": "", "rules": "2014", "revision": 1},
            "quantity": 1, "weight": {"value": 0, "units": "lb"}, "price": {"value": 0, "denomination": "gp"},
            "rarity": "", "identified": True, "type": {"value": "gear", "subtype": ""}, "properties": [], "container": None, "activities": {},
        },
        "effects": [], "folder": None, "sort": 0, "ownership": {"default": 0}, "flags": {},
    }
    LOOT.append(it)


loot("Rune Slip Signed 'Q.'", "A slip of paper with a rune drawn on it and one stroke crossed out, signed 'Q.'.",
     "Found at the suite, bedroom 3 desk. Stellan has not met Quill and cannot place the hand; the 'Q.' initial is the only lead (Mottle, Pringus or Lil can say it means Quill Scratch). Hook for Quest 1.", "Quest 1: Rat on the Door Plate", "icons/svg/book.svg")
loot("Chewed Clinic Tag (Pimm's Mark)", "A small metal clinic tag, chewed at one corner, stamped with Doctor Pimm's mark.",
     "Found under a bed in suite bedroom 1. Points at Gerald.", "Quest 2: Gerald Has the Notebook")
loot("Tin: 'S. RATTUS, CUSTODIAN (ACTING)'", "A small tin containing a dead rat with a tiny tag reading 'S. RATTUS, CUSTODIAN (ACTING).'",
     "Under the bed in room 207. The tag is real; the intake ledger lists the rat as 'unclaimed after notice, vermin, 1'; the custody ledger lists a named custodian. Two of three records disagree.",
     "Quest 1", "icons/svg/skull.svg")
loot("Notice: Confirm Authorization (Warehouse Door)", "A notice pinned at the notices desk asking custodians to 'confirm their authorization' at a warehouse door.",
     "Clue for Quest 1; the door now believes a dead rat is its authorized custodian. Quill won't remove a clause they can't read.", "Quest 1")
loot("Overdue Lodging Bill (43 Years)", "An overdue lodging bill for a room, 43 years deep.", "The bill for room 6 (206). Hook for Quest 3.", "Quest 3: The Man in Room 6")
loot("Suite Guest Book", "A guest book of past suite occupants. One old entry mentions 'the man down the hall in six.'",
     "Found in the suite living room bookcases. Hook for Quest 3.", "Quest 3")
loot("Brass Plate '6'", "A brass '6' door plate, scratched and older than the rest.", "Room 6 / 206 door plate; pigeonhole bills pile up outside.", "Quest 3")
loot("Bone Tag (Wren's Identity Anchor)", "A small bone tag, worn smooth, hidden under a floorboard.",
     "Perception DC 12 in Wren's room. His original identity anchor. A Witness memory (Rite of the Remaining Bone, one copper) confirms a continuous mind.", "Quest 3", "icons/svg/skull.svg")
loot("Wren's Stamped Referral Card", "A printed card bearing a seal and the name of a licensed restoration house. Present it at the front desk.",
     "Reward from Quest 3. Handed over in person, never loose or anonymous, so it cannot be confused with the notes in the Ossuary. Sets up Bones's restoration without guaranteeing success. "
     "'They will ask for the name three times. Bring the name.'", "Quest 3")
loot("Doctor Pimm's Field Notebook", "A well-used field notebook of adaptation notes: rules for a viable adaptation, and a list of rejected adaptations with reasons.",
     "Gerald took it. Contains: (1) rules for a viable adaptation (body health, anatomy, scale, environmental need); (2) rejected adaptations; (3) the loose page below. Lesson: splicing chooses "
     "among viable continuations; it does not invent.", "Quest 2")
loot("Loose Page: Animal-Holding Box", "A very old drawing of an animal-holding box with a music mechanism, close to Betsy's own. Pimm: 'Not mine. Older than the licensing. I never found whose.'",
     "[UNSETTLED] Betsy's genealogy is not yet recovered. A breadcrumb, not an answer. Betsy keeps it.", "Quest 2")
loot("Capsule: 'Drop off at the usual time.'", "A capsule with a bone-style tag and a short letter reading: 'Drop off at the usual time.'",
     "The note lead (6.4). Never put it near Gerald, Kell or Wren and never resolve who sends it. Always arrives at the same hour at the dusty terminal, a single regular clunk.", "6.4 The note lead")
loot("Lost Property Tag: Unclaimed After Notice", "A tag on a shelf of unclaimed remains, with a date and 'notice expires' long past.",
     "Lost Property annex at the end of the shafts. Every tag is long past its notice date; it shows what 'unclaimed after notice' means. Add a recent date only if you design that thread for Bones.",
     "Quest 2")
loot("Pringus's Ledger Excerpt: The Rat", "An excerpt: the intake ledger lists the rat as 'unclaimed after notice, vermin, 1'; the custody ledger lists it as 'named custodian'. The tag is real.",
     "'A transfer requires all three to agree. Two is a rumor.'", "Quest 1")

if __name__ == "__main__":
    for key, a in ACTORS:
        save(a, "actors", f"Quest_{key}_FoundryVTT.json")
        print("wrote actor", key, [i["name"] for i in a["items"]])
    (ROOT / "items").mkdir(exist_ok=True)
    out = json.dumps(LOOT, indent=2, ensure_ascii=False)
    (ROOT / "items" / "Quest_Items_FoundryVTT.json").write_text(out, encoding="utf-8")
    (SHARE / "Foundry JSON").mkdir(exist_ok=True)
    (SHARE / "Foundry JSON" / "Quest_Items_FoundryVTT.json").write_text(out, encoding="utf-8")
    print("wrote", len(LOOT), "loot items")
