"""Documentation: append an entry for each generated NPC / item / scene / encounter to the GM guide and (optionally) commit and push to GitHub.

Entries go to gm-guide/Varrenmoor_Generated_Content.md (one section per kind, newest last). A single pointer line is added to the end of the main guide the first
time, so the main guide stays hand-edited. Player-facing text and GM notes are kept separate, so nothing secret is copied onto a character sheet.
"""
import datetime
import subprocess

from .common import GUIDE, ROOT

GEN_FILE = GUIDE / "Varrenmoor_Generated_Content.md"
MAIN = GUIDE / "Varrenmoor_NPC_Dialogue_GM_Reference.md"
HEAD = ("# Varrenmoor: generated content\n\nEntries written by `foundry-tools` (`vtt.py ... --doc`). Each says what was made, where it sits in Foundry, and the "
        "GM-only notes. Items' descriptions in Foundry are player-facing only; the secrets live here.\n")
POINTER = "\n\n---\n*Content made with the Foundry tools is documented in [Varrenmoor_Generated_Content.md](Varrenmoor_Generated_Content.md).*\n"


def _ensure():
    if not GEN_FILE.exists():
        GEN_FILE.write_text(HEAD, encoding="utf-8")
    t = MAIN.read_text(encoding="utf-8")
    if "Varrenmoor_Generated_Content.md" not in t:
        MAIN.write_text(t.rstrip("\n") + POINTER, encoding="utf-8")


def entry(kind, title, lines, gm_notes=None):
    """kind: NPC | Item | Scene | Encounter. lines: list of 'label: value' strings (stats, where placed, Foundry ids)."""
    _ensure()
    stamp = datetime.date.today().isoformat()
    body = f"\n\n## {kind}: {title}\n*Added {stamp}.*\n\n" + "".join(f"- {l}\n" for l in lines)
    if gm_notes:
        body += f"\n**GM notes.** {gm_notes}\n"
    with GEN_FILE.open("a", encoding="utf-8") as f:
        f.write(body)
    return GEN_FILE


def npc_entry(spec, uuid=None, placed=None):
    a = spec.get("art") or {}
    lines = [f"CR {spec.get('cr', 0)}, {spec.get('size', 'med')} {spec.get('type', 'humanoid')} {spec.get('subtype', '')}".strip(),
             f"HP {spec['hp']}, AC {spec['ac']}, abilities {spec.get('abilities')}",
             "Features: " + "; ".join(f["name"] for f in spec.get("features", [])) if spec.get("features") else "Features: none",
             "Attacks: " + "; ".join(f"{x['name']} ({x['dice']} {x.get('dtype', '')})" for x in spec.get("attacks", [])) if spec.get("attacks") else "Attacks: none",
             f"Foundry: actor `{uuid}`, folder '{spec.get('folder')}'" if uuid else "Foundry: not imported",
             f"3D token: generated from {'image ' + str(a.get('image')) if a.get('image') else 'prompt'}" if (a.get("image") or a.get("prompt")) else "3D token: none"]
    if placed:
        lines.append("Placed: " + placed)
    return entry("NPC", spec["name"], lines, spec.get("gm_notes"))


def item_entry(spec, uuid=None, placed=None):
    lines = [f"Player-facing text: {spec.get('description', '')}", f"Prop: {spec.get('shape', 'custom')} {spec.get('w', '')}x{spec.get('d', '')} m",
             f"Foundry: item `{uuid}`, folder '{spec.get('folder')}'" if uuid else "Foundry: not imported"]
    if placed:
        lines.append("Found: " + placed)
    return entry("Item", spec["name"], lines, spec.get("gm_notes"))


def scene_entry(name, generator, uuid, extra=None):
    return entry("Scene", name, [f"Generator: `foundry-3d/generators/{generator}.py`", f"Foundry: scene `{uuid}`"] + (extra or []))


def encounter_entry(spec, uuid=None):
    foes = ", ".join(f"{f.get('count', 1)} x {f['actor']}" for f in spec["foes"])
    return entry("Encounter", spec["name"], [f"Scene: {spec['scene']}", f"Foes: {foes}", f"Summary: {spec.get('summary', '')}", f"Tactics: {spec.get('tactics', '')}",
                                              f"Rewards: {spec.get('rewards', '')}", f"Journal: `{uuid}`" if uuid else "Journal: not created"], spec.get("gm_notes"))


def commit(message, push=True, log=print):
    """git add the guide, tools, generators and textures; commit; push. Never force."""
    subprocess.run(["git", "add", "gm-guide", "foundry-tools", "foundry-3d/generators", "foundry-3d/textures", "foundry-3d/ai/concept.py"], cwd=str(ROOT), check=True)
    r = subprocess.run(["git", "commit", "-m", message], cwd=str(ROOT), capture_output=True, text=True)
    log((r.stdout or r.stderr).strip().splitlines()[0] if (r.stdout or r.stderr) else "nothing to commit")
    if push and r.returncode == 0:
        subprocess.run(["git", "push"], cwd=str(ROOT), check=True)
        log("pushed")
