"""Session 14 ("The Thaw") quest items: standalone world Items (loot) for the clues and craft components the session uses.

Sources: gm-guide/Session_14_Foundry_Build_Checklist.md ("Optional quest items"), gm-guide/Session_14_Cladis_Return_Conspiracy.md (T1-T6, 7.5-7.9),
gm-guide/Session_14_Scenes_Spec.md (where props sit), gm-guide/Session_14_New_NPCs_Spec.md (stock).

    python foundry-json/session14_items.py           # write the item JSON only (foundry-json/items + the Vega share)
    python foundry-json/session14_items.py --push    # also upsert the folder and items into the live world

Shape copied from the existing Part 6 quest items (quest_content.py; live 'Rune Slip Signed Q.' / 'Capsule: Drop off at the usual time.'):
type loot, system.type gear, ownership default 0, source.custom set, no activities. Items are upserted by
flags.varrenmoor.pipelineId = item:ossuary:s14:<id>; the folder by folder:ossuary:s14:items. Nothing else in the world is touched.

Descriptions: the player-facing text first, then a GM note inside a Foundry secret block (<section class="secret">). Foundry shows
secret blocks to the document's owners, so a player who holds a copy can read the GM note: the notes are kept to handling
(who gives it, which task, DCs) and leave the session's secrets in the actors' GM features and the GM guide.
"""
import json
import sys
from pathlib import Path

from fvtt import ROOT, SHARE, hid, p

sys.path.insert(0, str(ROOT))
from session14_npcs import bridge  # noqa: E402  (same pwsh/bridge.ps1 helper the actor build used)

SRC = "Varrenmoor DM Guide, Part 7 (Session 14)"
PARENT_FOLDER = "yg6qh9wrlg1txdMu"          # Item folder "Quest Items (Side Quests)" (the Part 6 Ossuary quest items)
FOLDER_NAME = "Session 14: The Thaw"
FOLDER_TAG = "folder:ossuary:s14:items"
CAPSULE_GLB = "assets/varrenmoor-3d/Act 2 Road to Bridgehollow/Ossuary Exchange/Items/item_capsule.glb"   # existing prop (Part 6 capsule)

ITEMS = []


def gm(text):
    """GM note as a Foundry secret block (visible to GM and owners only)."""
    sid = "secret-" + hid("s14-secret", text)
    return f'<section class="secret" id="{sid}"><p><strong>GM note.</strong> {text}</p></section>'


def item(key, name, player, gm_text, img, weight=0, price=0, denom="gp", qty=1, model=None):
    flags = {}
    if model:
        flags["levels-3d-preview"] = {"model3d": model}
    ITEMS.append((key, {
        "name": name, "type": "loot", "img": img,
        "system": {
            "description": {"value": p(player) + gm(gm_text), "chat": ""},
            "source": {"custom": SRC, "book": "", "page": "", "license": "", "rules": "2014", "revision": 1},
            "quantity": qty, "weight": {"value": weight, "units": "lb"}, "price": {"value": price, "denomination": denom},
            "rarity": "", "identified": True, "type": {"value": "gear", "subtype": ""}, "properties": [], "container": None,
            "unidentified": {"description": ""},
        },
        "effects": [], "sort": 0, "ownership": {"default": 0}, "flags": flags,
    }))


# ------------------------------------------------------------------------------------------------ clues and documents (checklist)
item("copied_custody_page", "Copied Custody Page",
     "A certified copy of a custody ledger page. One entry: Named. Held: the place where even time cannot leave. Tag: outstanding.",
     "Sabeline shows it at Table Seven [ASK] (Scene 3, Clue E), or Pringus finds the line during an audit. Anyone who has read the Stolen Shard sees the same words. "
     "It is the custody record for T5: the intake ledger and this page agree, the physical tag is the third record. Sabeline's sheet also carries a copy "
     "(Copied Open-Claim Page); hand out this one if the party keeps it.",
     "icons/sundries/documents/document-sealed-signatures-red.webp")
item("outstanding_intake_tag", "Outstanding Intake Tag",
     "An old intake tag stamped with a crown mark. The number is very low.",
     "T5, the third record. The party's sheets hold no Session 12 intake tags (checked in the live world when this item was built), so by the guide it is still "
     "in the passage under the Cladis memorial: History DC 12 to read the old numbering (Investigation DC 12 to pick it out if they took the tags after all). "
     "Second path: Rite of the Remaining Bone (Expose Claim, 10 minutes, a copper coin, no charges) shows the claim it belongs to. "
     "A party member with custody presents it to Pringus for a Reconciliation Audit. The audit is public: Tallis reads audits.",
     "icons/commodities/treasure/token-runed-os-grey.webp")
item("mottles_receipt_room_208", "Mottle's Receipt (Room 208)",
     "Paid in advance. Three nights. Instead of a signature, someone drew a bell.",
     "Scene 1, Clue B: Mottle's ledger entry for Europa's room (\"He did not sign. He drew a bell. I have not agreed to that.\"). The man who paid was tall, "
     "with frost in his hair. Put to Pell together with Europa's frost: Insight DC 13 and he admits the far end is up at the camp.",
     "icons/sundries/documents/document-writing-brown.webp")
item("capsule_bell_silent", "Capsule: Bell Silent",
     "A capsule with a bone-style tag. The letter reads: Bell silent. Clapper taken to the Customs House. Bailiffs on the road. V. keeps the fire.",
     "Scene 7, Clue H: drops into the dusty terminal when the cold door opens (T6 success), same single clunk as the Part 6 notes. If the party refuses the Thaw, "
     "Pell brings it to them anyway (\"You should know anyway\"). Nobody in the Thaw explains who V. is this session.",
     "icons/commodities/tech/pipe-tube-glass-brass.webp", model=CAPSULE_GLB)

# ------------------------------------------------------------------------------------------------ the line and its parts (T2, T3, T6)
item("iron_bars_haddos_stock", "Iron Bars (Haddo's Stock)",
     "Four bars of old iron, bought off a salvage cart. They look alike.",
     "T2 at Brokka's forge (Scenes spec: on the anvil bench). Analyze, free, one careful 10 minutes covers all four, DC 12 sorts them; the results are in "
     "Session 14 T2 and in Haddo's Lore Reference: Three Strands. Do not say which bar is which before the roll. Haddo sells bar stock at 5 sp each.",
     "icons/commodities/metal/ingot-worn-iron.webp", weight=2, price=5, denom="sp", qty=4)
item("iron_rune_wire", "Iron Rune-Wire",
     "A coil of fine iron wire, freshly drawn from a single bar at Brokka's forge.",
     "T2 product: draw the clean bar into wire, smith's tools DC 12 (Dale or anyone; Brokka's help gives advantage). Counts as suitable material for Stellan's "
     "Repair Line on the anchor (T1); with the old wire T1 is at disadvantage. The rest is the wire strand of the braid (T6). "
     "If the wrong bar was drawn, it looks the same: T1 is at disadvantage until someone notices.",
     "icons/commodities/tech/wire-spool-steel.webp", weight=1)
item("jar_of_gorge_frost", "Jar of Gorge Frost",
     "A stoppered jar of frost that never fully melts.",
     "Pell's jar (his sheet carries one too: use either, not both). T2 frost match: Analyze this and the frost on the Stolen Shard, DC 14. "
     "Extract one Rime dose (Stable, automatic, 10 minutes; free at rest, otherwise 1 charge); then the jar is empty. It can also be the slow sinker on the real night.",
     "icons/consumables/potions/potion-jar-capped-teal.webp", weight=1)
item("rime_dose", "Rime Dose (Gorge Frost)",
     "A prepared dose of rime drawn from the gorge frost. It is cold to hold and never fully melts.",
     "Created by Dale's Extract Dose from the Jar of Gorge Frost (T2). Use Dale's Essencecrafting sheet for it: Apply Essence (1 charge plus this dose) to the braid "
     "preserves organic matter for 24 hours, so the linen and the fungal strand survive the cold. Without it the fungal strand freezes within an hour (T3). "
     "7.9 lets Dale keep one extra Rime dose as a reward; the jar's yield is finite. No time essence.",
     "icons/consumables/potions/vial-cork-blue.webp")
item("burial_linen_strand", "Burial Linen Strand (30 ft)",
     "Clean white burial linen, cut and twisted into a thirty-foot strand for braiding.",
     "From Harrowgate's Counter (burial linen, 5 sp per yard; this is ten yards). The linen strand of the braid: it holds shape and carries nothing. "
     "Needs the Rime dose applied (T2) to last in the cold.",
     "icons/commodities/cloth/thread-spindle-white.webp", weight=1, price=5)
item("living_fungal_strand", "Living Fungal Strand (30 ft)",
     "A thirty-foot strand of pale, living fungal thread, grown from a culture kept in a glass case. It is faintly cool to the touch.",
     "T3 at Ysolde's: Read Green Pattern (free, DC 12), then Quickening (1 charge) DC 13 grows the 30-ft strand (failure: 10 ft; a second Quickening finishes it). "
     "Tie Green Thread (1 charge, 10 minutes) links it to the culture case, which stays at the near knot: that is the signal. It freezes within an hour without "
     "the Rime dose. Violet's craft reads the fungus only.",
     "icons/commodities/cloth/thread-spindle-grey-green.webp", weight=1)
item("braided_line_30ft", "Braided Line (30 ft)",
     "Three strands braided together: white linen, fine iron wire, and a pale living fungal thread.",
     "T6 at Haddo's ropewalk: needs T1, T2 and T3. Someone holds tension while Haddo braids: Dexterity (weaver's tools or Sleight of Hand) DC 12; failure is a kink "
     "and 20 minutes lost. Then the test pull at the cold door (the Bell knock, Performance or Wisdom DC 12). The party carries the far end out through the cold door. "
     "Narrative object: it is rope, with no other property.",
     "icons/sundries/survival/rope-coil-white.webp", weight=5)

# ------------------------------------------------------------------------------------------------ fixtures and later-session items
item("anchor_rune_stone", "Anchor Rune-Stone (Cold Door)",
     "A palm-wide stone set in the right-hand jamb of an old iron service door, cut with two worn runes. It looks like ordinary masonry until you look closely.",
     "Not portable: a fixture of the cold door (Scene 7 map object Anchor_Stone). This item is a reference card for T1; do not give it to a player sheet. "
     "Perception DC 13 or Read Inscription (free, DC 13) to notice and read it; properties in the order given in Session 14 T1. Repair Line twice (1 charge, 1 minute, DC 14 each): "
     "Fraying, Strained, Stable. Clean wire from T2 or disadvantage. Success: it hums faintly when anyone taps four slow near it.",
     "icons/commodities/stone/engraved-symbol-water-grey.webp")
item("seized_bell_clapper", "Seized Bell Clapper",
     "A heavy iron bell clapper, wrapped in sacking and tied with a Customs House seizure tag.",
     "Session 15, not Session 14. The camp bell's clapper, held by the Iron Bailiffs at Bridgehollow's Customs House (the capsule's \"Clapper taken to the Customs House\"). "
     "The far knot needs the camp bell rung in the Bell knock, so the party has to recover it. The reason for the seizure is only what the Thaw thinks (an unlicensed signal).",
     "icons/tools/instruments/bell-brass-brown.webp", weight=8)
item("irregular_transfer_permit", "Irregular-Transfer Permit",
     "An Exchange permit, sealed and countersigned, for one irregular transfer through a named threshold. Valid once.",
     "Scene 5 only, and only if won: Persuasion DC 17 with the T5 audit done, or Pringus speaks for the records. It makes the later return fully legal. "
     "A delay (DC 15) or a lie (DC 16) does not earn it.",
     "icons/sundries/documents/document-official-capital.webp")


def folder_data():
    return {"name": FOLDER_NAME, "type": "Item", "folder": PARENT_FOLDER, "sorting": "a", "color": None, "description": ""}


def write_json():
    out = json.dumps([{"pipelineId": f"item:ossuary:s14:{k}", **d} for k, d in ITEMS], indent=2, ensure_ascii=False)
    for base in (ROOT / "items", SHARE / "Foundry JSON"):
        try:
            base.mkdir(parents=True, exist_ok=True)
            (base / "Session14_Quest_Items_FoundryVTT.json").write_text(out, encoding="utf-8")
            print("wrote", base / "Session14_Quest_Items_FoundryVTT.json")
        except OSError as e:
            print("skip", base, e)


def push():
    f = bridge("upsert_by_flag", documentName="Folder", id=FOLDER_TAG, data=folder_data())
    fid = f["uuid"].split(".")[-1]
    print("folder", f)
    res = {}
    for key, d in ITEMS:
        data = json.loads(json.dumps(d))
        data["folder"] = fid
        r = bridge("upsert_by_flag", documentName="Item", id=f"item:ossuary:s14:{key}", data=data)
        res[key] = r
        print(key, r)
    return f, res


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    write_json()
    if "--push" in sys.argv:
        push()
