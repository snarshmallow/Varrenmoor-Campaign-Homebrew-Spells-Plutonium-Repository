"""Session 14 ("The Thaw") NPC actors: six new Ossuary NPCs, plus the one added feature on Quill.

Sources: gm-guide/Session_14_New_NPCs_Spec.md (content), gm-guide/Session_14_Foundry_Build_Checklist.md (fields),
gm-guide/Session_14_Cladis_Return_Conspiracy.md (DCs, what each NPC knows).

    python foundry-json/session14_npcs.py            # write the actor JSONs only (foundry-json/actors + the Vega share)
    python foundry-json/session14_npcs.py --push     # also upsert them into the live world (Ossuary Exchange actor folder)
    python foundry-json/session14_npcs.py --quill    # add 'Lore Reference: Cladis's Trail' to Quill (only if missing; backups first)

Actors are upserted by flags.varrenmoor.pipelineId = npc:ossuary:s14:<id>, so a re-run updates them instead of duplicating.
The base actor comes from fvtt.npc() (Mottle template, dnd5e 4.0 export); fix_53() rewrites the few fields whose shape changed in
dnd5e 5.3 (senses.ranges, details.habitat) so the document matches what the live world stores (compared against the live Mottle doc).
"""
import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path

from fvtt import ROOT, feat, hid, npc, p, save, utility, weapon

REPO = ROOT.parent
PS1 = REPO / "foundry-bridge" / "bridge.ps1"
FOLDER = "ae9wu7eMHFRxi43Q"                     # Actor folder "Ossuary Exchange" (Quill, Mottle, Brokka, Pimm, Pringus, Mavis live here)
QUILL = "Actor.PsjbmI1M64DINQmV"
SRC = "Varrenmoor DM Guide, Part 7 (Session 14)"
HABITAT = "Ossuary Exchange — Lower Ring"
DOC = "icons/sundries/documents/document-sealed-red-yellow.webp"   # same icon as Quill's native reference features
BACKUP = REPO / "foundry-3d" / "ai" / "characters" / "session14"
PLACEHOLDER = "icons/svg/mystery-man.svg"

SKELETON = dict(ctype="undead", dv=("bludgeoning",), di=("poison",), ci=("exhaustion", "poisoned"), senses={"darkvision": 60})


# ------------------------------------------------------------------------------------------------ helpers
def ref(actor, name, html, sort):
    """Native 'GM Reference / Lore Reference / Side Quest / Merchant Reference' feature: a feat with no activities."""
    it = feat(actor, name, html, sort, img=DOC)
    it["system"]["source"]["custom"] = SRC
    return it


def trait(actor, name, html, sort, img="icons/svg/aura.svg"):
    it = feat(actor, name, html, sort, img=img)
    it["system"]["source"]["custom"] = SRC
    return it


def act(it):
    it["system"]["source"]["custom"] = SRC
    return it


def flat_weapon(it, formula):
    """Flat damage (e.g. 1): custom formula instead of a die."""
    it["system"]["damage"]["base"]["custom"] = {"enabled": True, "formula": str(formula)}
    it["system"]["damage"]["base"]["number"] = None
    it["system"]["damage"]["base"]["denomination"] = None
    return it


def loot(actor, name, text, sort, qty=1, price=0, denom="gp", img="icons/svg/item-bag.svg"):
    return {
        "_id": hid(actor, name, "loot"), "name": name, "type": "loot", "img": img,
        "system": {
            "description": {"value": p(text), "chat": ""},
            "source": {"custom": SRC, "book": "", "page": "", "license": "", "rules": "2014", "revision": 1},
            "quantity": qty, "weight": {"value": 0, "units": "lb"}, "price": {"value": price, "denomination": denom},
            "rarity": "", "identified": True, "type": {"value": "gear", "subtype": ""}, "properties": [], "container": None, "activities": {},
        },
        "effects": [], "folder": None, "sort": sort, "ownership": {"default": 0}, "flags": {},
    }


def ul(*rows):
    return "<ul>" + "".join(f"<li>{r}</li>" for r in rows) + "</ul>"


def h(title):
    return f"<h2>{title}</h2>"


def fix_53(a, *, ideal, bond, flaw, saves=(), tools=None, lang_custom="", darkvision=0, skills=None):
    """Bring the 4.0-template actor in line with the dnd5e 5.3 document shape used by this world."""
    s = a["system"]
    want_skills = skills or {}
    sn = s["attributes"]["senses"]
    s["attributes"]["senses"] = {"units": "ft", "special": sn.get("special", ""),
                                 "ranges": {k: sn.get(k, 0) or 0 for k in ("darkvision", "blindsight", "tremorsense", "truesight")}}
    d = s["details"]
    d.pop("environment", None)
    d.pop("spellLevel", None)
    d["habitat"] = {"custom": HABITAT, "value": []}
    d["treasure"] = {"value": []}
    d["ideal"], d["bond"], d["flaw"] = ideal, bond, flaw
    for ab in saves:
        s["abilities"][ab]["proficient"] = 1
    for sk, v in s["skills"].items():                         # the Mottle template carries Mottle's own proficiencies: keep only the spec's
        v["value"] = want_skills.get(sk, 0)
    s["tools"] = {k: {"value": v, "ability": ab, "bonuses": {"check": ""}} for k, (v, ab) in (tools or {}).items()}
    s["traits"]["languages"]["custom"] = lang_custom
    s["source"]["custom"] = SRC
    pt = a["prototypeToken"]
    pt["flags"] = {}                                           # 3D token model: TODO (no token_<id>.glb exists yet)
    pt["sight"]["enabled"] = True                              # same as the native Ossuary NPCs (Mottle, Quill, Gerald)
    if darkvision:
        pt["sight"].update(range=darkvision, visionMode="darkvision")
    else:
        pt["sight"].update(range=0, visionMode="basic")
    a["folder"] = FOLDER
    return a


ACTORS = []

# ================================================================================================ 1. SABELINE NOCK
A = "Sabeline Nock"
items = [
    trait(A, "Copied Forward", p("Sabeline has advantage on checks to recall or find any entry in the custody ledger that she has copied."), 100000),
    trait(A, "Contracted Staff", p("She cannot be bought, sold or claimed: she is a person under contract, not property. The Exchange's wards treat harm to her as an offense against the house."), 200000),
    trait(A, "Ledger Hand", p("<strong>Tool feature (calligrapher's supplies, proficient).</strong> In 10 minutes she can make an exact, certified copy of any Exchange page she has access to."), 300000, img="icons/svg/book.svg"),
    act(flat_weapon(weapon(A, "Pen Jab", p("<em>Melee Attack Roll:</em> +3 to hit, reach 5 ft. <em>Hit:</em> 1 piercing damage. (She will not.)"), 400000, "dex", 1, 4, "piercing"), 1)),
    act(utility(A, "Call the Desk", p("She rings the night desk bell; two Exchange custodians arrive in 1d4 rounds. Works only inside the Exchange's thresholds."), 500000,
                activation="action", uses=(1, "day"), chat="<p>The night desk bell rings once.</p>")),
    ref(A, "GM Reference: Sabeline Nock, Voice and Night Desk",
        h("Sabeline Nock, Night Custody Clerk") + p("<em>\"Three records must agree. One of mine never has.\"</em>")
        + p("<strong>Body:</strong> a sentient skeleton, contracted Exchange staff (a person under contract, not property). Small and upright; reading spectacles wired to her skull; "
            "a clerk's sleeve-garters on bare arm bones. Very neat.")
        + p("<strong>Job:</strong> keeps the night copy of the custody ledger: reconciles the day's entries and copies forward open claims when a volume fills.")
        + p("<strong>[SECRET] Thaw role:</strong> runs the Thaw day to day; Quill is its cause. She found Cladis's open claim while copying it forward for the fourth time and brought it to Quill, "
            "who recognized it as one mark of Cladis's trail. Keeps the custody page and the meeting times. Old colleague of Quill's; they argue about commas.")
        + p("<strong>Motivation:</strong> duty first: a claim that never closes offends her. Second, plain politics: Nior wanted authority over every settlement and road, and the Niorghast means "
            "to resurrect him; that would not leave a neutral house neutral, and her contract only exists because the Exchange is neutral.")
        + p("<strong>Where:</strong> the night custody office from the tenth hour; Table Seven at Mottle's after the evening rush.")
        + p("<strong>Voice:</strong> quiet, exact, faintly amused. Taps four slow with her pen when thinking (the Bell knock). Calls Cladis \"the claimant\" in public. Never raises her voice; she lowers it.")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] \"Night desk. If it isn't in the ledger, it hasn't happened yet.\"",
            "[COMMON] \"I don't sell anything. I write down who did.\"",
            "[ASK] \"There is an open claim in my ledger. It's been open for three hundred years. I'd like to close it properly.\"",
            "[ASK] <em>(showing the page)</em> \"Named. Held. Tag outstanding. Two out of three. Pringus would call it a rumor. I call it a job.\"",
            "[EARN] \"She isn't dead. She was put outside, and she tied herself off out there. A thread tied in the wrong place can be tied again. That's all we're doing. Knots.\"",
            "[EARN] \"Why now? Because you walked a piece of the place she's in through my intake hall. And because of the news from Bridgehollow.\"",
            "[EARN] \"No, I don't know what happened in the fortress. Nobody does. I am not going to guess at you.\"",
            "<em>(to Tallis)</em> \"Inspector. You're early. Sit. The kettle's honest.\"")
        + p("<strong>Scene 3B (if Quill's test failed):</strong> she finds the party at intake, because the custody ledger shows they hold the Stolen Shard: <em>\"You are carrying a piece of a place "
            "I have been filing for longer than you have been alive. May we talk somewhere with soup?\"</em>")
        + p("<strong>Scene 7:</strong> <em>\"We can finish this end. We cannot ring a bell that has no tongue, and we can't tie the far knot from here. After noon tomorrow, this door does not open again.\"</em>"),
        600000),
    ref(A, "Lore Reference: The Open Claim",
        h("The Open Claim") + p("[ASK] The custody line, copied forward for about three hundred years: <em>\"Cladis. Named. Held: the place where even time cannot leave. Tag: outstanding.\"</em> "
                                "The same words are cut into the Stolen Shard.")
        + p("<strong>Why it is a \"rumor\":</strong> the Exchange accepts a named person into a body only when three records agree: the intake ledger (her name), the custody ledger (the \"held\" line) "
            "and the physical tag. Intake and custody agree; the tag has been outstanding for 300 years. Two out of three is a rumor (Pringus's rule).")
        + p("[EARN] The claim is one mark of Cladis's trail, left on purpose (with the CLADIS marks on Europa's father's map and the old intake tag from the Session 12 passage).")
        + p("<strong>She knows:</strong> the open claim, the method, every Thaw member, the cold door's timetable, Tallis's interest. "
            "<strong>She does not know:</strong> who banished Cladis, what happened in Nior's fortress, who cut the sentence, or whether it will work. "
            "She knows <em>of</em> the Goddess's name but has never heard it said. [SECRET] She says \"I don't know\" about the fortress plainly.")
        + p("<strong>Secrecy:</strong> she never says \"Cladis\" in a common hall (\"the claimant\", \"her\"). The page is shown once, at Table Seven, or Pringus finds it during an audit."),
        700000),
    ref(A, "Side Quest: The Outstanding Tag",
        h("Side Quest: The Outstanding Tag (Part 7, T5)") + p("<strong>Hook:</strong> intake and custody agree; the physical tag has been \"outstanding\" for 300 years. Find it and make the three records agree.")
        + "<h3>Objectives</h3>" + ul(
            "<strong>Find the tag.</strong> It is among the old intake tags from the Session 12 chest and passage material. If the party took them: Investigation <strong>DC 12</strong> to spot a tag stamped "
            "with the Winter crown's mark and an intake number matching Sabeline's page. If not: it is still in the passage under the Cladis memorial (History <strong>DC 12</strong> to read the old numbering).",
            "<strong>Second path:</strong> the Rite of the Remaining Bone (Expose Claim, 10 minutes, a copper coin, no charges) on the tag shows the claim it belongs to.",
            "<strong>Present it.</strong> A party member with custody presents the tag to Pringus for a Reconciliation Audit: <em>\"I know this tag is real. The ledger states the claim is open. "
            "I infer it was left to be found. I do not know what is at the other end.\"</em> Once all three agree, the claim is reconciled and the threshold will accept the named person.")
        + p("<strong>Warning:</strong> an audit is a <em>public</em> record. Inspector Tallis reads audits. Doing it honestly makes the operation legal and visible; skipping it makes it invisible and impossible. "
            "A completed audit gives advantage when talking Tallis down (Scene 5).")
        + p("<strong>Reward:</strong> the records agree; Tallis can be talked down (delay DC 15, permit DC 17)."),
        800000),
    ref(A, "GM Reference: Lil' Apostrophe at the Night Desk",
        h("Lil' Apostrophe at the Night Desk") + p("Sabeline: <em>\"Please don't write on my ledger.\"</em> Lil: <em>\"I wasn't gonna. ...What's it say if I did?\"</em>")
        + p("Lil: <em>\"Is the ledger a book that's awake at night?\"</em> Sabeline: <em>\"Yes.\"</em> Lil: <em>\"Same.\"</em>"),
        900000),
    loot(A, "Night Custody Ledger (copy volume)", "A thick ledger volume in a neat night-clerk's hand.", 1000000, img="icons/svg/book.svg"),
    loot(A, "Copied Open-Claim Page", "A certified copy of a custody ledger page. One entry: Named. Held: the place where even time cannot leave. Tag: outstanding.", 1100000, img="icons/svg/book.svg"),
    loot(A, "Steel-Nib Pens", "A case of steel-nib pens and a brass knock-block.", 1200000),
    loot(A, "Wire Spectacles", "Reading spectacles wired to fit a skull.", 1300000),
    loot(A, "Tin of Tea", "A tin of plain black tea.", 1400000),
    loot(A, "Night Office Key", "A key to the night custody office (not to the vaults).", 1500000),
]
ACTORS.append(("sabeline_nock", fix_53(npc(
    "Sabeline Nock, Night Custody Clerk", 0.25, "med", SKELETON["ctype"], "sentient skeleton", 13, 12, (8, 12, 10, 16, 14, 11), {"walk": 30},
    hp_formula="3d8", senses=SKELETON["senses"], dv=SKELETON["dv"], di=SKELETON["di"], ci=SKELETON["ci"], languages=("common",),
    skills={"his": 1, "ins": 1, "inv": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER, model="token_sabeline_nock.glb", tok_size="med", disposition=0,
    align="lawful neutral",
    bio=p("<strong>Sabeline Nock</strong> is a small, very neat sentient skeleton, contracted Exchange staff, who keeps the night copy of the custody ledger in the night custody office. "
          "Quiet, exact and faintly amused, she taps four slow with her pen when she thinks and never raises her voice; she lowers it.")
    + p("<strong>GM notes (Part 7).</strong> [SECRET] She runs the Thaw day to day (Quill is its cause): she found Cladis's open claim while copying it forward. She drives T5 (The Outstanding Tag: "
        "Investigation or History DC 12, then Pringus's public audit) and approaches the party herself in Scene 3B if Quill's test fails. Reassigned to a day desk if Tallis's review goes ahead (7.6, day 2)."),
    items=items), ideal="Three records must agree.", bond="The night ledger, and the claim she has copied forward four times.", flaw="Would rather be correct than safe.",
    saves=("int", "wis"), tools={"calligrapher": (1, "int")}, lang_custom="reads old Eirwyn script", darkvision=60, skills={"his": 1, "ins": 1, "inv": 1})))

# ================================================================================================ 2. YSOLDE HARROWGATE
A = "Ysolde Harrowgate"
items = [
    trait(A, "Leased Body", p("Ysolde lives in her third leased body (lease up in spring; rent paid monthly). If reduced to 0 HP she drops unconscious as normal; if killed, her lease contract lets "
                              "the Exchange recover her name. She would be furious."), 100000),
    trait(A, "Licensed Restorer", p("She knows the restoration materials list and can tell at a glance whether a vessel or a set of remains is <strong>Stable</strong>, <strong>Strained</strong> or unusable."), 200000),
    act(utility(A, "Restorer's Kit", p("<strong>Tool feature (herbalism kit and healer's kit, proficient).</strong> As an action, she stabilizes a creature and restores <strong>1d4 + 2</strong> hit points. 3/day."),
                300000, activation="action", uses=(3, "lr"), img="icons/svg/regen.svg")),
    act(weapon(A, "Scalpel", p("<em>Melee Attack Roll:</em> +3 to hit, reach 5 ft. <em>Hit:</em> 1d4 + 1 slashing damage."), 400000, "dex", 1, 4, "slashing")),
    act(utility(A, "Steady Hands", p("<strong>Reaction.</strong> When a creature within 5 feet fails a Medicine or Splicing check on a body she is supervising, she lets it reroll once. 1/day."),
                500000, activation="reaction", uses=(1, "lr"))),
    ref(A, "GM Reference: Ysolde Harrowgate, Voice and Restoration House",
        h("Ysolde Harrowgate, Licensed Restorer") + p("<em>\"Nobody was ever in it. I checked three times. That's the law, and it's also manners.\"</em>")
        + p("<strong>Body:</strong> a woman in her third leased body (a sturdy, middle-aged human body; the lease is up in spring and she pays rent on it monthly). She is fond of it and complains about the knees.")
        + p("<strong>Job:</strong> runs <em>Harrowgate Restorations</em>, an independent licensed restoration house in the Lower market. Restoration under contract, no guarantees. "
            "[SUGGESTED] It is the house named on Tobias Wren's referral card (Part 6, Quest 3).")
        + p("<strong>[SECRET] Thaw role:</strong> prepares the vessel (a lawful construct frame with no identity, grown with tissue from a seed of life) in her back room, and keeps Violet's mycelium "
            "culture in a glass case. Quill is a customer and friend who writes her boundary runes.")
        + p("<strong>Motivation:</strong> she restores people for a living, and thinks one person is owed a body more than most. Privately, she would like to restore someone who will remember it was done well.")
        + p("<strong>Voice:</strong> brisk, warm, practical, a nurse's humor. Rubs her borrowed knees. Says \"properly\" a lot. Washes her hands before and after every sentence that matters.")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] \"Restoration's a contract, not a miracle. Sit down, you look like a claim form.\"",
            "[COMMON] \"No, I can't do it today. Nobody does it today. Today is for paperwork.\"",
            "[ASK] \"This body? Leased. Third one. Lovely, apart from the knees. Lease is up in spring.\"",
            "[ASK] <em>(the vessel)</em> \"Construct material without identity. Bought, receipted, three records. Nobody was ever in it.\" (Insight DC 11: true.)",
            "[ASK] <em>(to Betsy)</em> \"It'll arrive cold from the inside. Pick me a body that warms from the middle, not one that just survives by stopping. She's done enough stopping.\"",
            "[EARN] \"Yes, I know whose it's for. No, I won't say it out here.\"",
            "[EARN] <em>(Bones)</em> \"Bring me the name, the skull if you can get it, and the toe if you can't. After this is done, I'll take him at cost. No promises. There never are.\"",
            "<em>(to Lil)</em> \"Hands where I can see them, love.\" <em>(Lil: \"They're always where you can see them. That's the problem with hands.\")</em>"),
        600000),
    ref(A, "Lore Reference: The Vessel",
        h("The Vessel") + p("[ASK] <strong>Lawful category:</strong> construct material without identity, an Exchange category. Bought, receipted, three records. Nobody was ever in it (Insight DC 11: true). "
                            "<em>\"If she comes back in her own skin, good. This is in case she doesn't.\"</em>")
        + p("<strong>Materials:</strong> burial linen, distilled water, a seed of life, a boundary rune (Quill's), needle and thread, and identity anchors. Prepared like a restoration.")
        + p("[EARN] <strong>Why cold-from-inside matters:</strong> Cladis shredded her own thread to get out. What comes back along a mended thread may be only herself: name and mind. Whatever climbs "
            "back arrives carrying the palace's cold <em>inside</em> it, and an ordinary body would freeze from the core outward. The grown tissue needs a viable cold adaptation (T4). "
            "If her own body makes the crossing, the vessel is simply not used.")
        + p("<strong>She knows:</strong> the vessel, the restoration materials, what cold does to tissue, that it is for Cladis. <strong>She does not know:</strong> the cold door's timetable, "
            "the courier, or the Bridgehollow news beyond rumor."),
        700000),
    ref(A, "Training Reference: Choosing a Continuation",
        h("Choosing a Continuation (supports Betsy's T4)") + p("Pimm's rule: <em>a problem, a continuation, a cost.</em> Ysolde offers three continuations. Betsy judges them with Medicine or Nature "
                                                               "<strong>DC 12</strong> (free) and picks one:")
        + ul("<strong>Warm from the core</strong> (a deep layer of heat-making fat around the heart and spine, as some hibernating animals have). <strong>Viable and correct.</strong> Cost: the body is always hungry.",
             "<strong>Cold-proof blood that slows down</strong> (like a frog that freezes in winter). Viable, but the wrong problem: the body would survive the cold by stopping, which is exactly where she has been stuck. Ysolde points this out if chosen.",
             "<strong>\"Frost-proof bones.\"</strong> Not a viable continuation. Pimm: <em>\"That is not biology. That is a wish.\"</em>")
        + p("Apply the chosen continuation with Betsy's Splicing <strong>as her sheet defines it</strong> (her sheet is authoritative). Suggested DC 14, advantage with Pimm supervising "
            "(Ysolde tells Pimm it is \"a cold-climate restoration\"). Success: vessel <strong>Stable</strong>. Failure: <strong>Strained</strong> (she arrives weak and cold if it is used).")
        + p("<strong>Limits:</strong> supervision gives advantage on one check. No extra charges or actions."),
        800000),
    ref(A, "Side Quest: A Body That Warms From the Middle",
        h("Side Quest: A Body That Warms From the Middle (Part 7, T3 and T4)")
        + ul("<strong>T3, the living strand (Violet):</strong> the culture is in Ysolde's glass case. Read Green Pattern (free, DC 12): cave mycelium, Vitality Strained, cold blocking growth. "
             "Quickening (1 charge) DC 13 grows a 30-ft strand (failure: 10 ft, a second Quickening finishes it). Tie Green Thread (1 charge, 10 minutes) between the case and the strand's tip: the signal. "
             "Needs Dale's Rime dose (T2) or the strand freezes in an hour.",
             "<strong>T4, the vessel's fit (Betsy):</strong> see <em>Training Reference: Choosing a Continuation</em>.")
        + p("<strong>Reward:</strong> a Stable vessel and a calm Ysolde; Betsy gets a supervised adaptation study (no extra charges or actions). Ysolde agrees to take Bones's restoration at cost once the operation is done."),
        900000),
    ref(A, "Merchant Reference: Harrowgate's Counter",
        h("Harrowgate's Counter") + ul("Clean burial linen: 5 sp per yard", "Distilled water: 2 sp per flask", "Joining needles and bone-thread: 1 gp",
                                        "Identity tag blanks: 1 sp", "Preserving salts: 5 sp", "Restoration consultations: 5 gp (written)", "Restoration contracts: by quote, no guarantees")
        + p("<strong>Refusals:</strong> she does not sell bodies over the counter, and does not sell anything that \"was ever someone\"."),
        1000000),
    ref(A, "Lore Reference: Bones's Restoration",
        h("Bones's Restoration") + p("[EARN] <em>\"Bring me the name, the skull if you can get it, and the toe if you can't. After this is done, I'll take him at cost. No promises. There never are.\"</em>")
        + p("She takes Bones's restoration contract <strong>at cost</strong> once the Thaw's operation is done. No guaranteed success (canon). Pringus's claim process stays separate from the restoration. "
            "If the party has Wren's stamped referral card, this is the house on the card [SUGGESTED]. If the party refuses the Thaw, she still only takes Bones on after the operation (7.10)."),
        1100000),
    loot(A, "Burial Linen", "Clean white burial linen, sold by the yard.", 1200000, qty=10, price=5, denom="sp"),
    loot(A, "Distilled Water", "A stoppered flask of distilled water.", 1300000, qty=6, price=2, denom="sp"),
    loot(A, "Joining Needles and Bone-Thread", "A roll of curved joining needles and a spool of bone-thread.", 1400000, qty=4, price=1),
    loot(A, "Identity Tag Blank", "A blank identity tag, ready to be stamped.", 1500000, qty=10, price=1, denom="sp"),
    loot(A, "Preserving Salts", "A packet of preserving salts.", 1600000, qty=6, price=5, denom="sp"),
]
ACTORS.append(("ysolde_harrowgate", fix_53(npc(
    "Ysolde Harrowgate, Licensed Restorer", 0.5, "med", "humanoid", "human (leased body)", 22, 11, (11, 12, 12, 15, 15, 12), {"walk": 30},
    hp_formula="4d8+4", senses={}, languages=("common",), skills={"med": 2, "nat": 1, "ins": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER,
    model="token_ysolde_harrowgate.glb", tok_size="med", disposition=1, align="neutral good",
    bio=p("<strong>Ysolde Harrowgate</strong> runs Harrowgate Restorations, an independent licensed restoration house in the Lower market, in her third leased body (lovely, apart from the knees). "
          "Brisk, warm and practical, she washes her hands before and after every sentence that matters.")
    + p("<strong>GM notes (Part 7).</strong> [SECRET] Thaw member: she prepares the lawful vessel and keeps Violet's culture. T3 (Violet: Read Green Pattern DC 12, Quickening DC 13) and "
        "T4 (Betsy: judge DC 12, Splicing DC 14 suggested, \"warm from the core\") happen at her house. The vessel is lawful (Insight DC 11: true). Takes Bones's restoration at cost after the operation."),
    items=items), ideal="Do it properly or don't do it.", bond="Her restoration house and its receipts.", flaw="Takes on one patient too many.",
    saves=("wis",), tools={"herb": (1, "wis")}, skills={"med": 2, "nat": 1, "ins": 1})))

# ================================================================================================ 3. HADDO ROOK
A = "Haddo Rook"
lasso = act(weapon(A, "Lasso", p("<em>Ranged Attack Roll:</em> +3 to hit, range 15 ft. <em>Hit:</em> the target is <strong>restrained</strong> (escape DC 13)."), 500000,
                   "dex", 0, 4, "bludgeoning", reach=None, rng=(15, None), melee=False, img="icons/svg/net.svg"))
lasso["system"]["damage"]["base"].update(number=None, denomination=None, types=[])
items = [
    trait(A, "Two Arms, Two Opinions", p("Haddo's arms came from two different lawful donors (the left older, darker and scarred; the right younger and freckled). He has advantage on Athletics checks to climb rope or hold a load."), 100000),
    trait(A, "Ropewright", p("<strong>Tool feature (weaver's tools, proficient).</strong> In 1 hour he braids up to 60 feet of three-strand line; a creature helping him holds tension (see T6)."), 200000),
    act(utility(A, "Multiattack", p("Haddo makes two Rope Hook attacks."), 300000)),
    act(weapon(A, "Rope Hook", p("<em>Melee Attack Roll:</em> +5 to hit, reach 5 ft. <em>Hit:</em> 1d6 + 3 bludgeoning damage."), 400000, "str", 1, 6, "bludgeoning")),
    lasso,
    ref(A, "GM Reference: Haddo Rook, Voice and Ropewalk",
        h("Haddo Rook, Trolley Ropewright") + p("<em>\"Rope goes where it's tied. I tie it. That's the end of my curiosity.\"</em>")
        + p("<strong>Body:</strong> a big man whose two arms came from two different lawful donors: the left is older, darker and scarred; the right is younger and freckled. Both are excellent at rope. "
            "He talks to them separately when they disagree.")
        + p("<strong>Job:</strong> ropewright and line-splicer for the overhead bone trolleys and carriers in the Lower market. Works at the Ropewalk, under the trolley rails, below Nan Gristle's signal loft.")
        + p("<strong>[SECRET] Thaw role:</strong> braids the line; supplied the iron stock (including the Hunger-tainted bars, by mistake: T2). A paid specialist who deliberately knows only his part. "
            "Doesn't know who or what the line is for, the cold door, or Cladis; doesn't know Ysolde exists. If told, he is impressed and wants a raise.")
        + p("<strong>Quill:</strong> business. Quill once corrected the spelling on his shop sign and Haddo has never forgiven the comma.")
        + p("<strong>Voice:</strong> slow, big, cheerful, very literal. Measures everything in arm-lengths (and specifies which arm).")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] \"Mind the rail. It doesn't mind you.\"",
            "[COMMON] \"Left arm's forty years older than the right. Left arm does the knots.\"",
            "[ASK] \"I braid what I'm paid to braid. I don't ask where rope goes. Rope goes where it's tied.\"",
            "[ASK] <em>(the bars)</em> \"Bought those off a salvage cart. Old fittings. Iron's iron, isn't it?\" <em>(It isn't. See T2.)</em>",
            "[EARN] \"I don't ask where rope goes. ...Where's it going?\"",
            "<em>(to Lil)</em> \"Don't write on the rope.\" <em>(Lil: \"I was gonna write ROPE. So it knows.\" Haddo: \"It knows.\")</em>"),
        600000),
    ref(A, "Lore Reference: Three Strands",
        h("Three Strands (the braid's plain engineering)")
        + p("[ASK] <em>\"Three strands that fail different ways. That's all good rope is. Each one covers for the other two.\"</em>")
        + p("[ASK] <em>\"Linen holds shape, carries nothing. Wire carries, but cold snaps it. The fuzzy one's alive, so it rots. Braid them right and none of that matters.\"</em>")
        + p("The line is burial <strong>linen</strong>, drawn iron <strong>rune-wire</strong> (Dale's clean bar, T2) and Violet's living <strong>fungal strand</strong> (T3). Haddo knows it is for "
            "\"a long drop in the cold\", nothing more.")
        + p("<strong>T6, the braid:</strong> Haddo braids; someone holds tension and keeps count while three strands of different stiffness go together: Dexterity (weaver's tools or Sleight of Hand) "
            "<strong>DC 12</strong>. Failure: a kink; Haddo redoes it (20 minutes lost).")
        + p("<strong>The bars (T2):</strong> of the four bars from his stock, bar 1 is clean iron; bars 2 and 3 carry a <strong>Hunger</strong> trace (salvage from an old Mwooreth fitting: what has been "
            "eating the anchor); bar 4 is stone. Analyze DC 12 sorts them."),
        700000),
    ref(A, "Side Quest: The Fraying Cable",
        h("Side Quest: The Fraying Cable (optional)") + p("<strong>Hook:</strong> a trolley cable is fraying above the market. Haddo pays <strong>10 gp</strong> for a hand.")
        + ul("Go aloft on the rails and hold the cable while Haddo splices: Athletics <strong>DC 12</strong> aloft.",
             "Failure: a slip and a dangle (no fall if roped in); Haddo hauls them up and the splice takes another half hour.",
             "Nan Gristle holds the trolleys while they work, loudly.")
        + p("<strong>Reward:</strong> 10 gp, and Haddo's good opinion (useful for T6)."),
        800000),
    ref(A, "Merchant Reference: Haddo's Stock",
        h("Haddo's Stock") + ul("Hemp rope (50 ft): 1 gp", "Silk cord (50 ft): 10 gp", "Trolley cable offcuts: ask", "Iron bar stock: 5 sp each (two are Hunger-tainted; he doesn't know)",
                                 "Splicing fids", "Pulleys: 1 gp", "Harness: 2 gp")
        + p("<strong>Refusals:</strong> he will not sell a rope he has not tested, and will not say where any line he braids is going (he doesn't know)."),
        900000),
    loot(A, "Hemp Rope (50 ft)", "Fifty feet of good hemp rope.", 1000000, qty=4, price=1),
    loot(A, "Silk Cord (50 ft)", "Fifty feet of fine silk cord.", 1100000, qty=2, price=10),
    loot(A, "Trolley Cable Offcuts", "Short lengths of braided trolley cable.", 1200000, qty=6),
    loot(A, "Iron Bar Stock", "Bars of old iron bought off a salvage cart.", 1300000, qty=4, price=5, denom="sp"),
    loot(A, "Splicing Fid", "A big wooden splicing fid.", 1400000, qty=2),
    loot(A, "Pulley", "An iron pulley block.", 1500000, qty=4, price=1),
    loot(A, "Climbing Harness", "A leather climbing harness.", 1600000, qty=2, price=2),
]
ACTORS.append(("haddo_rook", fix_53(npc(
    "Haddo Rook, Trolley Ropewright", 0.5, "med", "humanoid", "human (spliced arms)", 32, 12, (16, 13, 14, 10, 11, 10), {"walk": 30, "climb": 20},
    hp_formula="5d8+10", senses={}, languages=("common",), skills={"ath": 1, "slt": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER,
    model="token_haddo_rook.glb", tok_size="med", disposition=0, align="neutral",
    bio=p("<strong>Haddo Rook</strong> is the ropewright and line-splicer for the Lower market's overhead bone trolleys: a big, slow, cheerful, very literal man whose two arms came from two different "
          "lawful donors. He measures everything in arm-lengths and says which arm.")
    + p("<strong>GM notes (Part 7).</strong> [SECRET] Paid Thaw specialist: braids the line and knows nothing else. T6 braid: Dexterity (weaver's tools or Sleight of Hand) DC 12. Two of his iron bars "
        "carry a Hunger trace (T2, Analyze DC 12). Optional job: the fraying cable, 10 gp, Athletics DC 12 aloft."),
    items=items), ideal="Rope goes where it's tied.", bond="His ropewalk and both his arms.", flaw="Buys iron off salvage carts without asking.",
    tools={"weaver": (1, "dex")}, skills={"ath": 1, "slt": 1})))

# ================================================================================================ 4. PELL OSTRY
A = "Pell Ostry"
items = [
    trait(A, "Knows the Time", p("Pell always knows the exact hour and when the next trolley passes. (He carries a pocket watch with no hands; it is for company.)"), 100000),
    trait(A, "Contracted Staff", p("He cannot be bought, sold or claimed: he is a person under contract, not property. The Exchange's wards treat harm to him as an offense against the house."), 200000),
    trait(A, "Tube Keeper", p("<strong>Tool feature (tinker's tools, proficient).</strong> He can send or receive a capsule through any working terminal and knows which terminals are listed and which are not."), 300000),
    act(weapon(A, "Lever Swing", p("<em>Melee Attack Roll:</em> +3 to hit, reach 5 ft. <em>Hit:</em> 1d4 + 1 bludgeoning damage."), 400000, "dex", 1, 4, "bludgeoning")),
    ref(A, "GM Reference: Pell Ostry, Voice and Terminal",
        h("Pell Ostry, Keeper of the Dusty Terminal") + p("<em>\"Usual time. Single clunk. Never early.\"</em>")
        + p("<strong>Body:</strong> a sentient skeleton missing both legs below the knee, who rides a counterweighted iron chair along a short rail in the terminal room. "
            "<strong>Speed 10 ft on the floor, 40 ft along his rail.</strong> Very fast on the rail, very slow on the floor.")
        + p("<strong>Job:</strong> nominal keeper of a pneumatic terminal the Exchange lists as being on no active route. Nobody remembers giving him the job; nobody has taken it away.")
        + p("<strong>[SECRET] Thaw role:</strong> keeps the cold door's timetable; receives and sends the Thaw's capsules at the usual time; lets the courier (Europa's brother [SUGGESTED], name "
            "[UNSETTLED]) through. Old loyalty to the woman at the fire on the other side of the door: <strong>Venfyura</strong> (SETTLED). He writes \"V.\" and never names her aloud; he will not confirm who she is this session.")
        + p("<strong>Quill:</strong> keeps his door's anchor running. He calls Quill \"the grammarian\" and means it fondly.")
        + p("<strong>Note lead (Part 6):</strong> Pell is who sends \"Drop off at the usual time.\" The notes are the Thaw's capsules. If you want that lead kept separate, have him use knocks instead.")
        + p("<strong>Voice:</strong> short sentences, railway-clerk precise, dry. Checks a pocket watch with no hands.")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] \"No route. No logging. No visitors. You're visiting.\"",
            "[ASK] \"Usual time is when the last trolley passes. One minute. Not two.\"",
            "[ASK] <em>(the frost jar)</em> \"From the gorge. Doesn't melt. Not all the way. That's how you know the edge is close.\"",
            "[EARN] \"Capsules come through with news. Lately it's bailiffs, black wagons, and a quiet Reave.\"",
            "[EARN, Europa only] \"The man who carried you in came through my door. Said you'd be angry. Said to tell you the time is right, and he's at the fire.\"",
            "[EARN] \"Someone's been counting my minutes. Tall fellow. Measuring chain.\"",
            "<em>(to Lil)</em> \"Don't touch the lever.\" <em>(Lil: \"What lever?\" Pell: \"Exactly.\")</em>")
        + p("<strong>Jar of gorge frost (GM):</strong> yields 1 Rime dose (Potency 1, never fully melts), then it is empty. Dale's T2 frost match (DC 14) uses it."),
        500000),
    ref(A, "Lore Reference: The Cold Door",
        h("The Cold Door") + p("[ASK] An old iron service door behind the dusty terminal. The ledger lists it as <strong>permanently sealed</strong>. Its old rune opens it for <strong>one minute</strong> "
                                "when the last trolley of the night passes: \"the usual time\". One minute. Not two.")
        + p("[EARN] On the other side: a snowy mountain road above Bridgehollow, a short walk from the Eirwitch camp. The far end of the line belongs at the gorge beside the camp, where some frost never melts "
            "(revealed after T1 is done, or when Europa's frost and Mottle's bell receipt are put to him: Insight <strong>DC 13</strong>).")
        + p("Quill keeps the door's anchor rune (Threshold + Bind) running; it is Fraying (wrong iron, Hunger trace). If T1 fails, the open minute drifts 1d6 x 5 minutes later.")
        + p("<strong>He knows:</strong> the schedule, the capsules, the Bridgehollow news, who carried Europa in, the frost. <strong>He does not know:</strong> the vessel, the records, or the method beyond \"line and bell\"."),
        600000),
    ref(A, "Lore Reference: News From Bridgehollow",
        h("News From Bridgehollow (capsule contents)") + p("[EARN] <em>\"Capsules come through with news. Lately it's bailiffs, black wagons, and a quiet Reave.\"</em>")
        + ul("The Regarder came; the Reave vanished.", "Iron Bailiffs guard a black caravan; Haywards patrol the fields.", "People whisper about Fen-Reivers near the gorge (rumor only: tracks, a missing goat, claw marks in snow).",
             "[EARN] Older capsules: \"Bailiffs took the bell's tongue.\"", "[EARN] From \"V.\": the Goddess has noticed. (\"She's looking.\")")
        + p("The Thaw reads all this as the Niorghast's people moving. Old letters from the far side are EARN to read; he will not say who \"V.\" is."),
        700000),
    ref(A, "Side Quest: The Usual Time",
        h("Side Quest: The Usual Time (Part 7, Scene 7)") + p("<strong>Hook:</strong> be at the cold door at the usual time for the test pull.")
        + ul("Needs T1 (anchor), T2 (wire and Rime dose) and T3 (strand); the braid from T6.",
             "Someone rings Nan's bell in the Bell knock (four slow) while Violet holds the strand and Stellan watches the anchor: Performance or Wisdom <strong>DC 12</strong>.",
             "Success: the door opens for its minute. A capsule drops through: <em>\"Bell silent. Clapper taken to the Customs House. Bailiffs on the road. V. keeps the fire.\"</em> Then the frost writes the name on the Stolen Shard.",
             "If they refuse the Thaw, Pell still brings them the capsule: <em>\"You should know anyway.\"</em>")
        + p("<strong>Reward:</strong> passage through the cold door onto the mountain road above Bridgehollow (saves the long road)."),
        800000),
    loot(A, "Jar of Gorge Frost", "A stoppered jar of frost that never fully melts.", 900000, img="icons/svg/frozen.svg"),
    loot(A, "Pocket Watch With No Hands", "A brass pocket watch with no hands.", 1000000),
    loot(A, "Capsule Shells", "Empty brass capsule shells for the pneumatic tubes.", 1100000, qty=6),
    loot(A, "Bone-Style Tags", "Small tags carved to look like bone.", 1200000, qty=6),
    loot(A, "Old Letters From the Far Side", "A bundle of old letters, tied with string.", 1300000, img="icons/svg/book.svg"),
]
ACTORS.append(("pell_ostry", fix_53(npc(
    "Pell Ostry, Keeper of the Dusty Terminal", 0.125, "med", SKELETON["ctype"], "sentient skeleton", 9, 11, (8, 13, 10, 12, 14, 9), {"walk": 10},
    hp_formula="2d8", senses=SKELETON["senses"], dv=SKELETON["dv"], di=SKELETON["di"], ci=SKELETON["ci"], languages=("common",),
    skills={"prc": 1, "ste": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER, model="token_pell_ostry.glb", tok_size="med", disposition=0, align="neutral",
    bio=p("<strong>Pell Ostry</strong> keeps a pneumatic terminal the Exchange lists on no active route. A sentient skeleton missing both legs below the knee, he rides a counterweighted chair along "
          "a short rail (speed 10 ft on the floor, 40 ft along his rail). Short sentences, railway-clerk precise, dry; his pocket watch has no hands.")
    + p("<strong>GM notes (Part 7).</strong> [SECRET] Thaw member: keeps the cold door's timetable and the courier post, and sends the Part 6 capsules. Loyal to \"V.\" (Venfyura; never named this "
        "session). The far end is the camp: Insight DC 13 with Europa's frost and Mottle's receipt. His frost jar feeds T2 (frost match DC 14, one Rime dose). Scene 7 is at his terminal."),
    items=items), ideal="Usual time. Never early.", bond="The woman at the fire on the other side of his door (Venfyura; GM-only).",
    flaw="Keeps other people's secrets better than his own job.", tools={"tinker": (1, "int")}, darkvision=60, skills={"prc": 1, "ste": 1})))

# ================================================================================================ 5. CORVIN TALLIS
A = "Corvin Tallis"
items = [
    trait(A, "Reads Doors", p("Tallis has advantage on checks to tell whether a door, hatch or threshold has been opened recently."), 100000),
    trait(A, "Hard to Lie To", p("Deception checks against him are made against <strong>DC 16</strong>. The wards don't stop lies; he does."), 200000),
    trait(A, "Measuring Chain (tool)", p("<strong>Tool feature (cartographer's tools, proficient).</strong> He can measure and record any doorway; his notes count as a record for a Reconciliation Audit."), 300000),
    act(utility(A, "Notice of Irregularity", p("<strong>Charter procedure, not a spell. 1/day.</strong> He posts a notice; after the stated time, the named threshold is sealed by Exchange order and "
                                                 "any account linked to it is suspended pending review."), 400000, activation="action", uses=(1, "day"), img="icons/svg/book.svg")),
    act(weapon(A, "Measuring Chain", p("<em>Melee Attack Roll:</em> +4 to hit, reach 10 ft. <em>Hit:</em> 1d4 + 2 bludgeoning damage, and the target's speed drops by 10 feet until his next turn. "
                                       "(Last resort; the wards inside will usually stop it anyway.)"), 500000, "dex", 1, 4, "bludgeoning", reach=10)),
    ref(A, "GM Reference: Corvin Tallis, Voice and Rounds",
        h("Inspector Corvin Tallis, Inspector of Thresholds") + p("<em>\"Is the door sealed? The ledger says it is. My book says it opens. One of these is wrong.\"</em>")
        + p("<strong>Body:</strong> one of the few breathing staff: a tall, thin, living human in his fifties, grey uniform coat, a brass measuring chain looped at his belt. Writes in a small black book of door openings.")
        + p("<strong>Job:</strong> inspects thresholds: that every door does what the ledger says it does. Posts notices of irregularity on the public boards. <strong>Not a villain, not hostile</strong>: pressure. "
            "He and Sabeline want the same thing, for opposite reasons.")
        + p("<strong>Quill:</strong> has hired Quill twice to repair doors and respects the work; has started to wonder why Quill's repairs are so good on doors that are \"sealed\".")
        + p("<strong>Rounds:</strong> rides the <strong>tenth-hour trolley</strong> every night now and times it with his watch (Nan finds this rude). Appears in Scene 5 (night custody office) and possibly at the cold door in Scene 7.")
        + p("<strong>Voice:</strong> polite, precise, slightly too close. Asks questions that each have exactly one answer. Measures doorways with his chain while talking.")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] \"Good evening. Which door did you come in by? There is only one correct answer.\"",
            "[COMMON] \"I don't arrest anyone. I close doors. It's usually enough.\"",
            "[ASK] \"A sealed door that opens is a lie with hinges.\"",
            "[ASK] \"Forty-one openings. One minute each. Same hour. That is not a draft.\"",
            "[EARN] <em>(after the audit, talked to a delay)</em> \"One more minute, then it's closed, and it's in my book that I waited.\"",
            "[EARN] <em>(lawful permit)</em> \"If the three records agree, then what passes is a lawful transfer, and it's my job to let it. I hate that you've made this my job.\"",
            "<em>(lied to)</em> \"Thank you. I'll be posting at noon regardless.\"",
            "<em>(to Lil)</em> \"And which door did you come in by?\" <em>(Lil: \"The front one. It was the front when I came in.\")</em>"),
        600000),
    ref(A, "Lore Reference: What Tallis Knows",
        h("What Tallis Knows") + p("[ASK] The \"sealed\" service door behind the dusty terminal has opened for one minute at the same hour <strong>forty-one times</strong>. Someone keeps its rune working. "
                                    "A bell rang where none should.")
        + p("<strong>He does not know:</strong> Cladis, the claim, the method, or the Thaw. He has no secret role. He reads audits, so a Reconciliation Audit (T5) puts the claim in front of him."),
        700000),
    ref(A, "Side Quest: Forty-One Minutes",
        h("Side Quest: Forty-One Minutes (Part 7, Scene 5)") + p("<strong>Hook:</strong> <em>\"Tomorrow at noon I post a notice and the door is sealed properly.\"</em> Delay him, persuade him, or outrun him. <strong>Never violence.</strong>")
        + ul("<strong>Talk him down to a delay:</strong> Persuasion <strong>DC 15</strong> (advantage if T5's audit is done). He files <em>after</em> one more opening.",
             "<strong>Lawful permit:</strong> Persuasion <strong>DC 17</strong> with the audit done, or Pringus speaks for the records. A one-time irregular-transfer permit; makes the later return fully legal.",
             "<strong>Lie:</strong> Deception <strong>DC 16</strong>. He goes away, but the notice still posts at noon.",
             "<strong>Nan helps:</strong> whatever they choose, she can hold the tenth-hour trolley a few minutes so he is late to the cold door.")
        + p("<strong>The clock:</strong> each night the party delays, he gets one step further (day 1 questions, day 2 Sabeline's contract under review, day 3 the notice posts regardless)."),
        800000),
    ref(A, "GM Reference: If Tallis Posts",
        h("If Tallis Posts (Part 7.6)") + ul(
            "The cold door is sealed by Exchange order. The party walks the long way (the Pilgrim Road).",
            "Sabeline's contract is reviewed: contracted staff can't be bought or harmed, but she can be reassigned to a day desk with no access to the custody ledger.",
            "The Exchange cannot arrest anyone outside its thresholds. It closes accounts and doors. That is all, and it is enough.",
            "Public notices are read by everyone with an account, including people who report to the Regarder. A notice about \"a sealed door to the mountain road\" tells them where to look.",
            "After a notice, the Haywards patrol the mountain road too. Fen-Reivers stay rumor (tracks, a missing goat, claw marks in snow): never on stage for a level-4 party."),
        900000),
    loot(A, "Black Book of Door Openings", "A small black notebook of door openings: times, durations, doors.", 1000000, img="icons/svg/book.svg"),
    loot(A, "Brass Measuring Chain", "A brass measuring chain, marked in feet.", 1100000),
    loot(A, "Pad of Notice Forms", "A pad of blank Exchange notice-of-irregularity forms.", 1200000),
    loot(A, "Exchange Seal", "An official Exchange seal.", 1300000),
    loot(A, "Thermos of Weak Tea", "A thermos of very weak tea.", 1400000),
]
ACTORS.append(("corvin_tallis", fix_53(npc(
    "Corvin Tallis, Inspector of Thresholds", 1, "med", "humanoid", "human", 27, 13, (10, 14, 12, 14, 16, 12), {"walk": 30},
    hp_formula="5d8+5", senses={}, languages=("common",), skills={"ins": 2, "inv": 1, "prc": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER,
    model="token_corvin_tallis.glb", tok_size="med", disposition=0, align="lawful neutral",
    bio=p("<strong>Inspector Corvin Tallis</strong> is one of the Exchange's few breathing staff: a tall, thin man in his fifties in a grey uniform coat, a brass measuring chain at his belt and "
          "a small black book of door openings in his hand. Polite, precise and slightly too close, he asks questions that each have exactly one answer.")
    + p("<strong>GM notes (Part 7).</strong> Pressure, not a villain: he has counted forty-one openings of a door recorded as sealed and will post a notice at noon. Delay: Persuasion DC 15 "
        "(advantage with the audit); permit: DC 17 with the audit; lie: Deception DC 16 (notice still posts). Nan can make him late. Never violence."),
    items=items), ideal="A door that lies is how neutrality ends.", bond="His black book of openings.", flaw="Cannot leave a discrepancy alone, even when it would be kinder.",
    saves=("int", "wis"), tools={"cartographer": (1, "int")}, skills={"ins": 2, "inv": 1, "prc": 1})))

# ================================================================================================ 6. NAN GRISTLE
A = "Nan Gristle"
items = [
    trait(A, "Signalwoman", p("Nan knows where every trolley in the Lower market is, and when."), 100000),
    act(utility(A, "Signal Bell and Trumpet", p("<strong>Tool feature.</strong> Her voice through the brass speaking-trumpet carries 300 feet. Once a night she can halt or delay a trolley for up to 10 minutes "
                                                  "(\"Signal fault. Happens all the time. Happens when I say it happens.\")."), 200000, activation="action", uses=(1, "lr"), img="icons/svg/sound.svg")),
    act(flat_weapon(weapon(A, "Signal Flag Swat", p("<em>Melee Attack Roll:</em> +3 to hit, reach 5 ft. <em>Hit:</em> 1 bludgeoning damage, and she is very loud about it."), 300000,
                           "str", 1, 4, "bludgeoning"), 1)),
    ref(A, "GM Reference: Nan Gristle, Voice and Signal Loft",
        h("Nan Gristle, Trolley Signalwoman") + p("<em>\"Four slow means stop and wait. Everybody knows that. Well. Everybody up here.\"</em>")
        + p("<strong>Body:</strong> a broad old half-orc woman with a brass speaking-trumpet on a strap, signal flags in her apron, and a bell on a post beside her chair. Fully her own body, and proud of it.")
        + p("<strong>Job:</strong> signals the overhead bone trolleys through the Lower market interchange from a loft above the rails (the Ropewalk and Signal Loft, above Haddo's workshop).")
        + p("<strong>Not in the Thaw.</strong> She helps because she likes the party, enjoys Lil (the ducks rode her trolleys for an afternoon), and dislikes Tallis riding her tenth-hour trolley and timing it. "
            "She barely knows Quill (\"the skinny one with the chalk\") and thinks the dusty terminal is \"Pell's hobby\".")
        + p("<strong>Voice:</strong> loud, cheerful, nosy; talks through the trumpet even when you're next to her. Taps the bell rope when nervous.")
        + "<h3>Sample dialogue</h3>" + ul(
            "[COMMON] <em>(through the trumpet)</em> \"MIND THE BASKETS. Oh, you're right there. Mind the baskets.\"",
            "[COMMON] \"Four slow on my bell means stop and wait. Two fast means go. Easy.\"",
            "[ASK] \"Inspector Tallis rides the tenth-hour trolley every night now. Times it with his watch. Rude.\"",
            "[ASK] \"Want to borrow the bell? Bring it back with its tongue in. People keep stealing tongues lately.\"",
            "[ASK] \"I can hold the tenth-hour a few minutes. Signal fault. Happens all the time. Happens when I say it happens.\"",
            "[EARN] \"I don't want to know what you're doing. I want to know if it's going to be funny.\"")
        + p("<strong>Quest hooks:</strong> lends the signal bell for the test pull (T6); can delay Tallis (Scene 5)."),
        400000),
    ref(A, "Lore Reference: Trolley Times and Tallis's Rounds",
        h("Trolley Times and Tallis's Rounds") + p("[COMMON/ASK] She knows every trolley time, every regular rider, Tallis's rounds, and which corridors carry sound.")
        + ul("The <strong>last trolley of the night</strong> is the one that sets \"the usual time\" (she doesn't know that matters).",
             "Tallis rides the <strong>tenth-hour trolley</strong> every night now and times it (Clue G: the pressure).",
             "She can hold the tenth-hour a few minutes (her Signal Bell and Trumpet, once a night): Tallis is late to the cold door.",
             "The signal bell is lendable for T6 (\"Bring it back with its tongue in\").")
        + p("<strong>She does not know:</strong> anything about the Thaw, Cladis or the cold door."),
        500000),
    ref(A, "GM Reference: Lil' Apostrophe at the Signal Loft",
        h("Lil' Apostrophe at the Signal Loft") + p("Nan: <em>\"THE DUCK BOY.\"</em> Lil: <em>\"Hi! Was I supposed to be here?\"</em> Nan: <em>\"You're always supposed to be here.\"</em>")
        + p("The duck afternoon: the ducks rode her trolleys for a whole afternoon, and she thought it was the best day in years. If Lil writes BELL on the bell (T6), roll Part 3; if the result is loud, "
            "the test still works, and Tallis hears it from two corridors away."),
        600000),
    loot(A, "Brass Speaking-Trumpet", "A dented brass speaking-trumpet on a strap.", 700000),
    loot(A, "Signal Flags", "A bundle of trolley signal flags.", 800000),
    loot(A, "Signal Bell", "A trolley signal bell on a short post. Lendable; bring it back with its tongue in.", 900000, img="icons/svg/sound.svg"),
    loot(A, "Tin of Mint Humbugs", "A tin of mint humbugs.", 1000000),
    loot(A, "Trolley Timetable", "A handwritten trolley timetable. Accurate.", 1100000, img="icons/svg/book.svg"),
]
ACTORS.append(("nan_gristle", fix_53(npc(
    "Nan Gristle, Trolley Signalwoman", 0, "med", "humanoid", "half-orc", 11, 10, (13, 9, 12, 10, 13, 12), {"walk": 25},
    hp_formula="2d8+2", senses={"darkvision": 60}, languages=("common", "orc"), skills={"prc": 1, "per": 1}, img=PLACEHOLDER, token_img=PLACEHOLDER,
    model="token_nan_gristle.glb", tok_size="med", disposition=1, align="chaotic good",
    bio=p("<strong>Nan Gristle</strong> signals the Lower market's overhead bone trolleys from a loft above the rails: a broad, loud, cheerful old half-orc with a brass speaking-trumpet, signal flags "
          "in her apron and a bell on a post by her chair.")
    + p("<strong>GM notes (Part 7).</strong> Ally, not in the Thaw. Lends the signal bell for T6; once a night she can hold the tenth-hour trolley so Tallis is late (Scene 5). Source of Clue G "
        "(Tallis rides the tenth-hour trolley)."),
    items=items), ideal="Trolleys on time.", bond="Her loft, her bell, the duck afternoon.", flaw="Cannot keep gossip in, only secrets she doesn't know.", darkvision=60, skills={"prc": 1, "per": 1})))


# ------------------------------------------------------------------------------------------------ Quill's added feature
QUILL_FEATURE_NAME = "Lore Reference: Cladis's Trail"


def quill_feature():
    it = ref("Quill Scratch", QUILL_FEATURE_NAME,
             h("Cladis's Trail (GM only)")
             + p("Quill has collected Cladis's trail marks for years: the bold <strong>Threshold-family wayfinding marks</strong> (\"a road that is also a door\", like the CLADIS marks on Europa's father's map), "
                 "the <strong>open claim</strong> in the custody ledger, and an <strong>outstanding tag</strong>.")
             + p("<strong>Quill's aim (SETTLED):</strong> bring Cladis back so she can enlist the Rhime Goddess, who needs her name carried back into the Wyrd to fight the Niorghast and stop him resurrecting Nior. "
                 "Quill knows the name from the trail but will not say it aloud; the Goddess writes it on the Stolen Shard in Scene 7.")
             + "<h3>Sample lines</h3>" + ul(
                 "[EARN] \"She left marks for whoever came after. A trail. Your map is one. We follow it.\"",
                 "[EARN] \"There is a name. It isn't ours to say in a tavern.\"",
                 "[EARN] \"A thread tied in the wrong place can be tied again. Two knots and a good line. That's all.\"",
                 "<em>(On the anchor's Hunger trace)</em> \"Hunger. Her name has that word in it. I don't like that either.\""),
             700000)
    it.pop("_id", None)
    return it


# ------------------------------------------------------------------------------------------------ bridge
def bridge(op, **args):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(args, f, ensure_ascii=False)
        fn = f.name
    try:   # pwsh (7): Windows PowerShell 5.1's Invoke-RestMethod mis-decodes UTF-8 replies (curly quotes, em dashes)
        cmd = f"[Console]::OutputEncoding=[Text.Encoding]::UTF8; & '{PS1}' -Op {op} -ArgsFile '{fn}'"
        r = subprocess.run(["pwsh", "-NoProfile", "-Command", cmd], capture_output=True)
    finally:
        os.unlink(fn)
    out = r.stdout.decode("utf-8", "replace").strip()
    if r.returncode:
        raise RuntimeError(r.stderr.decode("utf-8", "replace") + out)
    return json.loads(out) if out else []


def push():
    res = {}
    for key, a in ACTORS:
        data = json.loads(json.dumps(a))
        for it in data["items"]:
            it.pop("_id", None)
        r = bridge("upsert_by_flag", documentName="Actor", id=f"npc:ossuary:s14:{key}", data=data)
        # note: the world forces prototypeToken.displayName to 20 (owner hover) on create AND update, as on every other NPC; 30 does not stick
        res[key] = r
        print(key, r)
    return res


def add_quill():
    BACKUP.mkdir(parents=True, exist_ok=True)
    doc = bridge("get", uuid=QUILL)
    (BACKUP / "quill_before.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    if any(i["name"] == QUILL_FEATURE_NAME for i in doc["items"]):
        print("Quill already has", QUILL_FEATURE_NAME)
    else:
        print(bridge("create", documentName="Item", parentUuid=QUILL, data=quill_feature()))
    doc = bridge("get", uuid=QUILL)
    (BACKUP / "quill_after.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Quill items:", [i["name"] for i in doc["items"]])


if __name__ == "__main__":
    for key, a in ACTORS:
        save(a, "actors", f"Session14_{key}_FoundryVTT.json")
        print("wrote", key, len(a["items"]), "items")
    if "--push" in sys.argv:
        push()
    if "--quill" in sys.argv:
        add_quill()
