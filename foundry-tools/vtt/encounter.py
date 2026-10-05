"""Encounters: place groups of existing actors as tokens in a scene and write a GM-only journal entry with the setup, tactics and rewards.

spec = {"name": ..., "scene": "<scene name or id>", "summary": "...", "tactics": "...", "rewards": "...", "gm_notes": "...",
        "foes": [{"actor": "<actor name>", "count": 3, "at": [x, y], "spread": 1.2, "hidden": false}, ...]}
`at` is in generator/model metres (same coordinates as the generator file); `spread` is the spacing in metres between copies (rows of 3).
"""
import math

from .common import bridge, find, folder_id, uuid_id
from .npc import place_token

TEMPLATE = {
    "name": "Example Ambush", "scene": "Ossuary Exchange Tavern", "summary": "What the players see and why it happens.",
    "tactics": "How the foes fight and when they flee.", "rewards": "Loot, XP, leads.", "gm_notes": "Secrets, DCs, scaling for a bigger party.",
    "foes": [{"actor": "Gerald", "count": 2, "at": [5.0, 3.0], "spread": 1.2, "hidden": False}],
}


def journal_html(spec, placed):
    esc = lambda s: (s or "").replace("<", "&lt;")
    h = f"<h2>{esc(spec['name'])}</h2><p>{esc(spec.get('summary'))}</p>"
    h += "<h3>Foes</h3><ul>" + "".join(f"<li>{f.get('count', 1)} x {esc(f['actor'])}</li>" for f in spec["foes"]) + "</ul>"
    for k, t in (("tactics", "Tactics"), ("rewards", "Rewards"), ("gm_notes", "GM notes")):
        if spec.get(k):
            h += f"<h3>{t}</h3><p>{esc(spec[k])}</p>"
    return h


def create(spec, dry=False, log=print):
    scene = find("Scene", spec["scene"])["uuid"] if not dry else spec["scene"]
    placed = []
    for f in spec["foes"]:
        n = int(f.get("count", 1))
        x0, y0 = f["at"][:2]
        sp = float(f.get("spread", 1.2))
        for i in range(n):
            x, y = x0 + (i % 3) * sp, y0 - (i // 3) * sp
            if dry:
                log(f"[dry] {f['actor']} #{i + 1} at ({x:.2f}, {y:.2f})")
                continue
            actor = find("Actor", f["actor"])["uuid"]
            placed.append(place_token(actor, scene, x, y, f["at"][2] if len(f["at"]) > 2 else 0.1, hidden=f.get("hidden", False),
                                      name=f"{f['actor']} {i + 1}" if n > 1 else None, link=False if n > 1 else None, log=log))
    html = journal_html(spec, placed)
    if dry:
        log(html)
        return None
    entry = {"name": spec["name"], "folder": folder_id("Encounters", "JournalEntry"), "ownership": {"default": 0},
             "pages": [{"name": spec["name"], "type": "text", "text": {"content": html, "format": 1}}]}
    uuid = bridge("create", documentName="JournalEntry", data=entry)["uuid"]
    log(f"encounter journal: {uuid}; {len(placed)} tokens placed")
    return uuid
