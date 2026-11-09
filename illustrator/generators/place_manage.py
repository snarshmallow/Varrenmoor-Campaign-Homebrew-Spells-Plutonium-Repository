"""Manage places: edit place.json metadata, rename a place id, duplicate, move to the trash, restore, delete permanently from the trash.

  python illustrator/generators/place_manage.py check-id  --id NEW
  python illustrator/generators/place_manage.py edit      --place ID [--name N] [--notes T] [--kind K] [--status S] [--culture C] [--season S] [--units U]
                                                           [--focus X Y] [--scale-ft-per-in F] [--grid-ft G] [--dry-run]
  python illustrator/generators/place_manage.py rename    --place OLD --new-id NEW [--include-export] [--allow-current] [--dry-run]
  python illustrator/generators/place_manage.py duplicate --place ID --new-id NEW [--name N] [--include-export] [--dry-run]
  python illustrator/generators/place_manage.py trash     --place ID [--allow-current] [--dry-run]
  python illustrator/generators/place_manage.py trash-list
  python illustrator/generators/place_manage.py restore   --entry TRASH_ENTRY [--as NEW] [--dry-run]
  python illustrator/generators/place_manage.py purge     --entry TRASH_ENTRY --confirm ID [--dry-run]

Rules
  * ids: lower-case letters, digits, underscore, 2-41 characters, starting with a letter or digit (the place spec pattern); not reserved
    (schema, export, trash, world, panel, places, con, nul, aux, prn, com1-9, lpt1-9) and not an existing place.
  * rename moves world/<old> to world/<new> (one atomic folder rename) and rewrites every reference: place.json id, "place" / "place_id" / "parent"
    fields equal to the old id and "world/<old>/" paths in the place's JSON files (panel_state.json, streets, buildings, water, profiles ...), the region
    children's place.json "parent", world/panel_last_place.json, and the per-place output folders illustrator/out/{panel,water,foundry,heightmap_paint}/<old>
    and illustrator/out/places/<old>_* / illustrator/out/<old>_* . world/<old>/export/ (the 3D pack: manifest place fields, pipeline ids, placements.json)
    is NOT rewritten unless --include-export (re-exporting is the clean way). Foundry is never contacted: the linked scene, the asset folder art/<old>/
    on the Foundry share and scene flags keep the old name and are listed under left_behind. Entity ids (streets, buildings) never change.
    Every step is recorded and undone in reverse order if a later step fails (rollback).
  * trash moves world/<id> to world/.trash/<id>_<YYYYmmdd-HHMMSS>/ (reversible; restore moves it back). purge deletes a trash entry for good and needs
    --confirm with the place id typed again. Nothing outside world/.trash is ever deleted; world/ itself and other places are refused by path checks.
  * the current panel place (world/panel_last_place.json) is refused for rename / trash unless --allow-current: switch the panel to another place first
    (the panel keeps saving panel_state.json of the place it has open).
Last stdout line is a JSON result for the panel's runner.
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_]{1,40}$")
RESERVED = {"schema", "export", "trash", "world", "panel", "places", "con", "nul", "aux", "prn"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
OUT_DIRS = ("panel", "water", "foundry", "heightmap_paint")
KINDS = ("town", "city", "village", "hamlet", "homestead", "farmstead", "wilderness", "blank", "building", "dungeon", "basemap", "scene", "region", "other")
STATUSES = ("proposed", "draft", "canon", "imported", "base map", "blank", "archived")
SKIP_COPY = ("export", "__pycache__", "optimized", "cache", ".cache")
MAX_JSON_BYTES = 30 * 1024 * 1024


class ManageError(Exception):
    pass


def roots(world=None, out=None):
    w = os.path.abspath(world or os.path.join(REPO, "world"))
    o = os.path.abspath(out or os.path.join(os.path.dirname(w), "illustrator", "out"))   # <root>/illustrator/out next to <root>/world (tests use a temp root)
    return w, o


def _jload(p, default=None):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _jsave(p, d):
    tmp = p + ".tmp_pm"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, p)


def _inside(child, parent):
    c, p = os.path.realpath(child), os.path.realpath(parent)
    return os.path.commonpath([c, p]) == p and c != p


def place_dir(world, pid):
    """world/<pid> with path checks: a plain id, directly inside world/, never world/ itself."""
    if not pid or not isinstance(pid, str) or pid in (".", "..") or "/" in pid or "\\" in pid or pid.startswith("."):
        raise ManageError(f"not a place id: {pid!r}")
    d = os.path.join(world, pid)
    if not _inside(d, world) or os.path.dirname(os.path.realpath(d)) != os.path.realpath(world):
        raise ManageError(f"refused: {d} is not a place folder directly inside {world}")
    return d


def check_id(world, new_id, existing_ok=False):
    """-> list of problems (empty = ok)."""
    p = []
    if not isinstance(new_id, str) or not ID_RE.match(new_id or ""):
        p.append(f"id {new_id!r} must be 2-41 characters: lower-case letters, digits and underscore, starting with a letter or digit")
    elif new_id in RESERVED:
        p.append(f"id {new_id!r} is reserved")
    elif not existing_ok and os.path.exists(os.path.join(world, new_id)):
        p.append(f"world/{new_id} already exists")
    return p


def current_place(world):
    return (_jload(os.path.join(world, "panel_last_place.json"), {}) or {}).get("place")


def _need_place(world, pid):
    d = place_dir(world, pid)
    if not os.path.isfile(os.path.join(d, "place.json")):
        raise ManageError(f"world/{pid} is not a place (no place.json)")
    return d


# ------------------------------------------------------------------ reference rewriting
def _rewrite(obj, old, new):
    """Recursively replace place references: values of keys place / place_id / parent equal to old, and 'world/<old>/' / 'world\\<old>\\' path prefixes. -> (obj, n)."""
    n = 0
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in ("place", "place_id", "parent", "id_place") and v == old:
                out[k] = new
                n += 1
            else:
                out[k], m = _rewrite(v, old, new)
                n += m
        return out, n
    if isinstance(obj, list):
        out = []
        for v in obj:
            vv, m = _rewrite(v, old, new)
            out.append(vv)
            n += m
        return out, n
    if isinstance(obj, str):
        s = obj
        for a, b in ((f"world/{old}/", f"world/{new}/"), (f"world\\{old}\\", f"world\\{new}\\"), (f"world:{old}:", f"world:{new}:")):
            if a in s:
                s = s.replace(a, b)
        if s.endswith(f"world/{old}"):
            s = s[: -len(old)] + new
        if s != obj:
            n += 1
        return s, n
    return obj, n


def _json_files(d, include_export):
    for dp, dns, fns in os.walk(d):
        rel = os.path.relpath(dp, d).replace("\\", "/")
        if not include_export and (rel == "export" or rel.startswith("export/")):
            dns[:] = []
            continue
        for fn in fns:
            if fn.endswith(".json"):
                yield os.path.join(dp, fn)


def plan_refs(d, old, new, include_export):
    """-> list of (path, new_obj, count) for JSON files under d that mention the old id."""
    out = []
    for p in _json_files(d, include_export):
        try:
            if os.path.getsize(p) > MAX_JSON_BYTES:
                continue
            raw = open(p, encoding="utf-8").read()
        except OSError:
            continue
        if old not in raw:
            continue
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        nobj, n = _rewrite(obj, old, new)
        if os.path.basename(p) == "place.json" and os.path.dirname(p) == d and isinstance(nobj, dict) and nobj.get("id") == old:
            nobj["id"] = new
            n += 1
        if n:
            out.append((p, nobj, n))
    return out


def _out_targets(out_root, old, new):
    """Per-place output folders / files under illustrator/out that are named after the place. -> [(src, dst)]."""
    t = []
    for sub in OUT_DIRS:
        s = os.path.join(out_root, sub, old)
        if os.path.isdir(s):
            t.append((s, os.path.join(out_root, sub, new)))
    for base in (os.path.join(out_root, "places"), out_root):
        if os.path.isdir(base):
            for fn in sorted(os.listdir(base)):
                if fn.startswith(old + "_") and not fn.startswith(old + "__"):
                    t.append((os.path.join(base, fn), os.path.join(base, new + fn[len(old):])))
    return t


def left_behind(world, d, pid):
    """Things named after the place that this tool does not change (Foundry, the 3D pack)."""
    out = []
    pj = _jload(os.path.join(d, "place.json"), {}) or {}
    sc = (pj.get("links") or {}).get("foundry_scene")
    if sc:
        out.append(f"Foundry scene {sc} (linked in place.json; its name and flags in Foundry are unchanged)")
    if os.path.isdir(os.path.join(d, "export")):
        out.append(f"world/{pid}/export/ (3D pack: manifest place, pipeline ids world:{pid}:..., placements.json): re-export after renaming, or use --include-export")
        out.append(f"Foundry asset folder art/{pid}/ on the Foundry share (models pushed earlier keep that folder; a new push writes the new one)")
    for n in sorted(os.listdir(world)):
        cpj = _jload(os.path.join(world, n, "place.json"), None)
        if isinstance(cpj, dict) and cpj.get("parent") == pid and n.startswith(pid + "__"):
            out.append(f"region child folder world/{n} keeps its name (its place.json parent is updated)")
    return out


# ------------------------------------------------------------------ operations
class Tx:
    """Undo log: each step registers its inverse; rollback() runs them in reverse."""

    def __init__(self, fail_at=None):
        self.undo, self.steps, self.fail_at = [], [], fail_at

    def step(self, label, do, undo):
        if self.fail_at is not None and len(self.steps) == self.fail_at:
            raise ManageError(f"injected failure before step {len(self.steps)}: {label}")
        do()
        self.steps.append(label)
        self.undo.append((label, undo))

    def rollback(self):
        errs = []
        for label, u in reversed(self.undo):
            try:
                u()
            except Exception as e:  # noqa: BLE001
                errs.append(f"{label}: {e}")
        return errs


def _write_json_step(tx, p, nobj, label):
    old_raw = open(p, encoding="utf-8").read()

    def undo():
        with open(p, "w", encoding="utf-8") as f:
            f.write(old_raw)
    tx.step(label, lambda: _jsave(p, nobj), undo)


def rename(old, new, world=None, out=None, include_export=False, allow_current=False, dry_run=False, _fail_at=None):
    world, out = roots(world, out)
    d = _need_place(world, old)
    probs = check_id(world, new)
    if probs:
        raise ManageError("; ".join(probs))
    if not allow_current and current_place(world) == old:
        raise ManageError(f"{old} is the place open in the panel: switch to another place first")
    nd = place_dir(world, new)
    refs = plan_refs(d, old, new, include_export)
    children = []
    for n in sorted(os.listdir(world)):
        cp = os.path.join(world, n, "place.json")
        cpj = _jload(cp, None) if n != old else None
        if isinstance(cpj, dict) and cpj.get("parent") == old:
            children.append(cp)
    outs = [(s, t) for s, t in _out_targets(out, old, new) if not os.path.exists(t)]
    last = current_place(world) == old
    plan = {"rename_folder": [f"world/{old}", f"world/{new}"],
            "json_files": [{"file": os.path.relpath(p, d).replace("\\", "/"), "references": n} for p, _, n in refs],
            "children_parent": [os.path.relpath(c, world).replace("\\", "/") for c in children],
            "output_folders": [[os.path.relpath(s, os.path.dirname(world)).replace("\\", "/"), os.path.relpath(t, os.path.dirname(world)).replace("\\", "/")] for s, t in outs],
            "panel_last_place": last, "left_behind": left_behind(world, d, old), "include_export": include_export}
    if dry_run:
        return {"ok": True, "dry_run": True, "old": old, "new": new, "plan": plan}
    tx = Tx(_fail_at)
    try:
        tx.step("rename folder", lambda: os.rename(d, nd), lambda: os.rename(nd, d))
        for p, nobj, _ in refs:
            np_ = os.path.join(nd, os.path.relpath(p, d))
            _write_json_step(tx, np_, nobj, "rewrite " + os.path.relpath(p, d))
        for cp in children:
            cpj = _jload(cp, {})
            cpj["parent"] = new
            _write_json_step(tx, cp, cpj, "child parent " + cp)
        for s, t in outs:
            tx.step("move " + s, (lambda s=s, t=t: os.rename(s, t)), (lambda s=s, t=t: os.rename(t, s)))
        if last:
            lp = os.path.join(world, "panel_last_place.json")
            _write_json_step(tx, lp, {"place": new}, "panel_last_place")
    except Exception as e:
        errs = tx.rollback()
        raise ManageError(f"rename failed ({e}); rolled back {len(tx.undo)} step(s)" + (f"; rollback problems: {errs}" if errs else ""))
    return {"ok": True, "old": old, "new": new, "steps": len(tx.steps), "plan": plan}


def duplicate(src, new, world=None, name=None, include_export=False, dry_run=False):
    world, _ = roots(world)
    d = _need_place(world, src)
    probs = check_id(world, new)
    if probs:
        raise ManageError("; ".join(probs))
    nd = place_dir(world, new)
    skip = () if include_export else SKIP_COPY
    size = 0
    for dp, dns, fns in os.walk(d):
        rel = os.path.relpath(dp, d).replace("\\", "/")
        if rel.split("/")[0] in skip:
            dns[:] = []
            continue
        size += sum(os.path.getsize(os.path.join(dp, f)) for f in fns)
    plan = {"copy": [f"world/{src}", f"world/{new}"], "bytes": size, "excluded": list(skip), "name": name}
    if dry_run:
        return {"ok": True, "dry_run": True, "src": src, "new": new, "plan": plan}
    try:
        shutil.copytree(d, nd, ignore=lambda dp, names: [n for n in names if os.path.normpath(dp) == os.path.normpath(d) and n in skip])
        for p, nobj, _ in plan_refs(nd, src, new, include_export):
            _jsave(p, nobj)
        pj = _jload(os.path.join(nd, "place.json"), {})
        pj["id"] = new
        pj["name"] = name or ((pj.get("name") or src) + " (copy)")
        pj.setdefault("links", {})["foundry_scene"] = None          # the copy is not linked to the original's Foundry scene
        pj["duplicated_from"] = src
        _jsave(os.path.join(nd, "place.json"), pj)
    except Exception as e:
        shutil.rmtree(nd, ignore_errors=True)
        raise ManageError(f"duplicate failed ({e}); removed the partial copy")
    return {"ok": True, "src": src, "new": new, "name": pj["name"], "plan": plan}


def trash_dir(world):
    return os.path.join(world, ".trash")


def trash(pid, world=None, allow_current=False, dry_run=False):
    world, _ = roots(world)
    d = _need_place(world, pid)
    if not allow_current and current_place(world) == pid:
        raise ManageError(f"{pid} is the place open in the panel: switch to another place first")
    entry = f"{pid}_{time.strftime('%Y%m%d-%H%M%S')}"
    td = os.path.join(trash_dir(world), entry)
    k = 1
    while os.path.exists(td):
        k += 1
        td = os.path.join(trash_dir(world), f"{entry}_{k}")
    res = {"ok": True, "place": pid, "entry": os.path.basename(td), "to": os.path.relpath(td, world).replace("\\", "/"), "left_behind": left_behind(world, d, pid)}
    if dry_run:
        res["dry_run"] = True
        return res
    os.makedirs(trash_dir(world), exist_ok=True)
    os.rename(d, td)
    _jsave(os.path.join(td, ".trash_info.json"), {"place": pid, "trashed": time.strftime("%Y-%m-%dT%H:%M:%S"), "from": f"world/{pid}"})
    return res


def trash_list(world=None):
    world, _ = roots(world)
    out = []
    td = trash_dir(world)
    if os.path.isdir(td):
        for n in sorted(os.listdir(td)):
            p = os.path.join(td, n)
            if not os.path.isdir(p):
                continue
            info = _jload(os.path.join(p, ".trash_info.json"), {}) or {}
            pj = _jload(os.path.join(p, "place.json"), {}) or {}
            out.append({"entry": n, "place": info.get("place") or pj.get("id") or n.rsplit("_", 2)[0], "name": pj.get("name"), "trashed": info.get("trashed")})
    return out


def _trash_entry(world, entry):
    td = trash_dir(world)
    if not entry or "/" in entry or "\\" in entry or entry in (".", "..") or entry.startswith("."):
        raise ManageError(f"not a trash entry: {entry!r}")
    p = os.path.join(td, entry)
    if not _inside(p, td) or not os.path.isdir(p):
        raise ManageError(f"no trash entry {entry!r} in world/.trash")
    return p


def restore(entry, world=None, as_id=None, dry_run=False):
    world, _ = roots(world)
    p = _trash_entry(world, entry)
    info = _jload(os.path.join(p, ".trash_info.json"), {}) or {}
    pid = info.get("place") or (_jload(os.path.join(p, "place.json"), {}) or {}).get("id")
    if not pid:
        raise ManageError("cannot tell which place this trash entry holds (no .trash_info.json / place.json id)")
    target = as_id or pid
    probs = check_id(world, target)
    if probs:
        raise ManageError("; ".join(probs) + ("" if as_id else " (restore it under another id with --as NEW)"))
    res = {"ok": True, "entry": entry, "place": target, "original": pid}
    if dry_run:
        res["dry_run"] = True
        return res
    dst = place_dir(world, target)
    os.rename(p, dst)
    try:
        os.remove(os.path.join(dst, ".trash_info.json"))
    except OSError:
        pass
    if as_id and as_id != pid:
        for q, nobj, _ in plan_refs(dst, pid, as_id, False):
            _jsave(q, nobj)
    return res


def purge(entry, confirm, world=None, dry_run=False):
    world, _ = roots(world)
    p = _trash_entry(world, entry)
    info = _jload(os.path.join(p, ".trash_info.json"), {}) or {}
    pid = info.get("place") or (_jload(os.path.join(p, "place.json"), {}) or {}).get("id") or entry
    if confirm != pid:
        raise ManageError(f"type the place id {pid!r} to confirm the permanent delete")
    if not _inside(p, trash_dir(world)):
        raise ManageError("refused: path outside world/.trash")
    res = {"ok": True, "entry": entry, "place": pid, "deleted": os.path.relpath(p, world).replace("\\", "/")}
    if dry_run:
        res["dry_run"] = True
        return res
    shutil.rmtree(p)
    return res


def edit(pid, world=None, dry_run=False, **f):
    world, _ = roots(world)
    d = _need_place(world, pid)
    pj = _jload(os.path.join(d, "place.json"), {})
    before = json.loads(json.dumps(pj))
    ch = {}
    for k in ("name", "notes", "kind", "status", "culture", "units"):
        v = f.get(k)
        if v is not None:
            if k == "name" and not str(v).strip():
                raise ManageError("name cannot be empty")
            pj[k] = v
            ch[k] = v
    if f.get("season") is not None:
        pj.setdefault("defaults", {})["season"] = f["season"]
        ch["season"] = f["season"]
    if f.get("focus") is not None:
        x, y = [float(v) for v in f["focus"]]
        pj.setdefault("view_focus", {})["town"] = [round(x), round(y)]
        ch["focus"] = [round(x), round(y)]
    vs_ch = {}
    if f.get("scale_ft_per_in") is not None or f.get("grid_ft") is not None:
        vp = os.path.join(d, "view_settings.json")
        vs = _jload(vp, {}) or {}
        t = vs.setdefault("presets", {}).setdefault("town", {"grid_major_every": 5, "focus": "center"})
        if f.get("scale_ft_per_in") is not None:
            if not float(f["scale_ft_per_in"]) > 0:
                raise ManageError("scale (ft per inch) must be above 0")
            t["scale_ft_per_in"] = float(f["scale_ft_per_in"])
            t["scale_bar_ft"] = 5 * float(f["scale_ft_per_in"])
            vs_ch["scale_ft_per_in"] = t["scale_ft_per_in"]
        if f.get("grid_ft") is not None:
            if not float(f["grid_ft"]) > 0:
                raise ManageError("grid (ft) must be above 0")
            t["grid_ft"] = float(f["grid_ft"])
            vs_ch["grid_ft"] = t["grid_ft"]
        ch.update(vs_ch)
    if not ch:
        raise ManageError("nothing to change: give at least one field")
    res = {"ok": True, "place": pid, "changes": ch, "before": {k: before.get(k) for k in ("name", "notes", "kind", "status", "culture", "units")}}
    if dry_run:
        res["dry_run"] = True
        return res
    _jsave(os.path.join(d, "place.json"), pj)
    if vs_ch:
        _jsave(vp, vs)
    return res


# ------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    c = sp.add_parser("check-id")
    c.add_argument("--id", required=True)
    e = sp.add_parser("edit")
    e.add_argument("--place", required=True)
    e.add_argument("--name")
    e.add_argument("--notes")
    e.add_argument("--kind")
    e.add_argument("--status")
    e.add_argument("--culture")
    e.add_argument("--season")
    e.add_argument("--units")
    e.add_argument("--focus", nargs=2, type=float, metavar=("X", "Y"))
    e.add_argument("--scale-ft-per-in", type=float)
    e.add_argument("--grid-ft", type=float)
    r = sp.add_parser("rename")
    r.add_argument("--place", required=True)
    r.add_argument("--new-id", required=True)
    r.add_argument("--include-export", action="store_true", help="also rewrite world/<id>/export (manifest, pipeline ids, placements); default off: re-export instead")
    r.add_argument("--allow-current", action="store_true", help="allow the place open in the panel (the panel must not be saving it)")
    du = sp.add_parser("duplicate")
    du.add_argument("--place", required=True)
    du.add_argument("--new-id", required=True)
    du.add_argument("--name")
    du.add_argument("--include-export", action="store_true")
    t = sp.add_parser("trash")
    t.add_argument("--place", required=True)
    t.add_argument("--allow-current", action="store_true")
    sp.add_parser("trash-list")
    rs = sp.add_parser("restore")
    rs.add_argument("--entry", required=True)
    rs.add_argument("--as", dest="as_id")
    pu = sp.add_parser("purge")
    pu.add_argument("--entry", required=True)
    pu.add_argument("--confirm", required=True, help="the place id typed again")
    for s in (e, r, du, t, rs, pu):
        s.add_argument("--dry-run", action="store_true")
    for s in (c, e, r, du, t, rs, pu, sp.choices["trash-list"]):
        s.add_argument("--world-root", help="world folder (default <repo>/world; tests)")
    a = ap.parse_args(argv)
    W = getattr(a, "world_root", None)
    try:
        if a.cmd == "check-id":
            p = check_id(roots(W)[0], a.id)
            res = {"ok": not p, "id": a.id, "problems": p}
        elif a.cmd == "edit":
            res = edit(a.place, W, a.dry_run, name=a.name, notes=a.notes, kind=a.kind, status=a.status, culture=a.culture, season=a.season, units=a.units,
                       focus=a.focus, scale_ft_per_in=a.scale_ft_per_in, grid_ft=a.grid_ft)
        elif a.cmd == "rename":
            res = rename(a.place, a.new_id, W, None, a.include_export, a.allow_current, a.dry_run)
        elif a.cmd == "duplicate":
            res = duplicate(a.place, a.new_id, W, a.name, a.include_export, a.dry_run)
        elif a.cmd == "trash":
            res = trash(a.place, W, a.allow_current, a.dry_run)
        elif a.cmd == "trash-list":
            res = {"ok": True, "trash": trash_list(W)}
        elif a.cmd == "restore":
            res = restore(a.entry, W, a.as_id, a.dry_run)
        else:
            res = purge(a.entry, a.confirm, W, a.dry_run)
    except ManageError as ex:
        print(json.dumps({"ok": False, "error": str(ex)}))
        return 2
    print(json.dumps(res))
    return 0 if res.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
