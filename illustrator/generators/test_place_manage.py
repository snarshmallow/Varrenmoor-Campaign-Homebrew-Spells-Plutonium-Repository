"""place_manage.py on temp worlds: id validation, edit, rename (every reference, nothing left under the old id, rollback on an injected failure),
duplicate, trash / restore / purge, guards (current place, path escapes, typed confirmation).
Run: python illustrator/generators/test_place_manage.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import place_manage as pm  # noqa: E402


def jw(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w", encoding="utf-8"))


def jr(p):
    return json.load(open(p, encoding="utf-8"))


def make_world():
    root = tempfile.mkdtemp(prefix="vb_pm_")
    w, o = os.path.join(root, "world"), os.path.join(root, "illustrator", "out")
    d = os.path.join(w, "zz_old")
    jw(os.path.join(d, "place.json"), {"id": "zz_old", "name": "Old", "kind": "town", "status": "proposed", "links": {"foundry_scene": "Scene.abc"},
                                        "files": {"streets": "streets.json"}, "notes": "see world/zz_old/streets.json"})
    jw(os.path.join(d, "panel_state.json"), {"v": 1, "place": "zz_old", "foliage": {"path": "world/zz_old/foliage.json"}, "other": "zz_old is a word"})
    jw(os.path.join(d, "streets.json"), {"place": "zz_old", "streets": [{"id": "str_a", "name": "A"}]})
    jw(os.path.join(d, "view_settings.json"), {"presets": {"town": {"scale_ft_per_in": 50, "grid_ft": 50}}})
    jw(os.path.join(d, "profiles", "p.json"), {"place": "zz_old"})
    jw(os.path.join(d, "export", "manifest.json"), {"place": "zz_old", "id": "world:zz_old:x"})
    os.makedirs(os.path.join(d, "buildings"))
    jw(os.path.join(d, "buildings", "bld_1.json"), {"id": "bld_1", "name": "B"})
    jw(os.path.join(w, "zz_old__child", "place.json"), {"id": "zz_old__child", "parent": "zz_old"})
    jw(os.path.join(w, "zz_other", "place.json"), {"id": "zz_other", "name": "Other"})
    jw(os.path.join(w, "panel_last_place.json"), {"place": "zz_other"})
    jw(os.path.join(o, "panel", "zz_old", "x.json"), {})
    jw(os.path.join(o, "places", "zz_old_spec.json"), {"id": "zz_old"})
    os.makedirs(os.path.join(o, "zz_old_town_files"))
    return root, w, o


def test_check_id():
    root, w, _ = make_world()
    try:
        assert pm.check_id(w, "good_id") == []
        for bad in ("A", "x", "has space", "UPPER", "zz_other", "schema", "con", "a/b", "../x", "_lead"):
            assert pm.check_id(w, bad), bad
        for bad in ("..", ".", "", ".trash", "a/b"):
            try:
                pm.place_dir(w, bad)
                raise AssertionError(bad)
            except pm.ManageError:
                pass
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("ok id validation and path checks")


def test_edit():
    root, w, _ = make_world()
    try:
        r = pm.edit("zz_old", w, dry_run=True, name="New Name")
        assert r["dry_run"] and jr(os.path.join(w, "zz_old", "place.json"))["name"] == "Old"
        pm.edit("zz_old", w, name="New Name", notes="n", kind="dungeon", status="canon", culture="english", season="winter", units="feet", focus=[10, 20], scale_ft_per_in=20, grid_ft=5)
        pj = jr(os.path.join(w, "zz_old", "place.json"))
        vs = jr(os.path.join(w, "zz_old", "view_settings.json"))
        assert pj["name"] == "New Name" and pj["kind"] == "dungeon" and pj["defaults"]["season"] == "winter" and pj["view_focus"]["town"] == [10, 20]
        assert vs["presets"]["town"]["scale_ft_per_in"] == 20 and vs["presets"]["town"]["grid_ft"] == 5
        for bad in ({"name": " "}, {}, {"scale_ft_per_in": 0}):
            try:
                pm.edit("zz_old", w, **bad)
                raise AssertionError(bad)
            except pm.ManageError:
                pass
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("ok edit (name, notes, kind, status, culture, season, units, focus, scale, grid; dry run; refusals)")


def _grep_old(base, old):
    hits = []
    for dp, _, fns in os.walk(base):
        for fn in fns:
            if fn.endswith(".json"):
                p = os.path.join(dp, fn)
                if f'"{old}"' in open(p, encoding="utf-8").read() or f"world/{old}/" in open(p, encoding="utf-8").read():
                    hits.append(p)
    return hits


def test_rename():
    root, w, o = make_world()
    try:
        dry = pm.rename("zz_old", "zz_new", w, dry_run=True)
        assert dry["dry_run"] and os.path.isdir(os.path.join(w, "zz_old")) and not os.path.exists(os.path.join(w, "zz_new"))
        files = {x["file"] for x in dry["plan"]["json_files"]}
        assert {"place.json", "panel_state.json", "streets.json", "profiles/p.json"} <= files and "export/manifest.json" not in files, files
        assert any("Scene.abc" in x for x in dry["plan"]["left_behind"]) and any("export" in x for x in dry["plan"]["left_behind"])
        # refusals
        for args in (("zz_old", "zz_other"), ("zz_old", "Bad"), ("nope", "zz_x")):
            try:
                pm.rename(*args, world=w)
                raise AssertionError(args)
            except pm.ManageError:
                pass
        jw(os.path.join(w, "panel_last_place.json"), {"place": "zz_old"})
        try:
            pm.rename("zz_old", "zz_new", w)
            raise AssertionError("current place must be refused")
        except pm.ManageError as e:
            assert "switch" in str(e)
        # injected failure -> rollback leaves everything as it was
        before = {p: open(p, encoding="utf-8").read() for p in [os.path.join(dp, f) for dp, _, fns in os.walk(root) for f in fns]}
        for k in (1, 3, 6):
            try:
                pm.rename("zz_old", "zz_new", w, allow_current=True, _fail_at=k)
                raise AssertionError("injected failure must raise")
            except pm.ManageError as e:
                assert "rolled back" in str(e)
            after = {p: open(p, encoding="utf-8").read() for p in [os.path.join(dp, f) for dp, _, fns in os.walk(root) for f in fns]}
            assert after == before, (k, set(after) ^ set(before))
        # the real rename (current place, allowed)
        r = pm.rename("zz_old", "zz_new", w, allow_current=True)
        nd = os.path.join(w, "zz_new")
        assert not os.path.exists(os.path.join(w, "zz_old")) and os.path.isdir(nd)
        assert jr(os.path.join(nd, "place.json"))["id"] == "zz_new" and jr(os.path.join(nd, "panel_state.json"))["place"] == "zz_new"
        assert jr(os.path.join(nd, "panel_state.json"))["foliage"]["path"] == "world/zz_new/foliage.json"
        assert jr(os.path.join(nd, "panel_state.json"))["other"] == "zz_old is a word", "free text is not rewritten"
        assert jr(os.path.join(nd, "streets.json"))["streets"][0]["id"] == "str_a", "entity ids unchanged"
        assert jr(os.path.join(w, "zz_old__child", "place.json"))["parent"] == "zz_new"
        assert jr(os.path.join(w, "panel_last_place.json"))["place"] == "zz_new"
        assert os.path.isdir(os.path.join(o, "panel", "zz_new")) and not os.path.exists(os.path.join(o, "panel", "zz_old"))
        assert os.path.exists(os.path.join(o, "places", "zz_new_spec.json")) and os.path.isdir(os.path.join(o, "zz_new_town_files"))
        assert jr(os.path.join(nd, "export", "manifest.json"))["place"] == "zz_old", "export is left alone by default"
        hits = [h for h in _grep_old(nd, "zz_old") if "export" not in h]
        assert not hits, hits
        # with --include-export
        jw(os.path.join(nd, "export", "manifest.json"), {"place": "zz_new", "id": "world:zz_new:x"})
        pm.rename("zz_new", "zz_third", w, include_export=True, allow_current=True)
        m = jr(os.path.join(w, "zz_third", "export", "manifest.json"))
        assert m == {"place": "zz_third", "id": "world:zz_third:x"}, m
        assert r["ok"]
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("ok rename (references, children, last place, out folders, export left alone, rollback at 3 points, refusals)")


def test_duplicate_trash_restore_purge():
    root, w, _ = make_world()
    try:
        r = pm.duplicate("zz_old", "zz_copy", w)
        cd = os.path.join(w, "zz_copy")
        pj = jr(os.path.join(cd, "place.json"))
        assert pj["id"] == "zz_copy" and pj["name"] == "Old (copy)" and pj["links"]["foundry_scene"] is None and not os.path.exists(os.path.join(cd, "export"))
        assert jr(os.path.join(cd, "panel_state.json"))["place"] == "zz_copy" and os.path.isdir(os.path.join(w, "zz_old")), r
        r2 = pm.duplicate("zz_old", "zz_copy2", w, name="Second", include_export=True)
        assert os.path.exists(os.path.join(w, "zz_copy2", "export", "manifest.json")) and r2["name"] == "Second"
        try:
            pm.duplicate("zz_old", "zz_copy", w)
            raise AssertionError("existing target must be refused")
        except pm.ManageError:
            pass
        # trash
        try:
            pm.trash("zz_other", w)
            raise AssertionError("current place must be refused")
        except pm.ManageError:
            pass
        t = pm.trash("zz_copy", w)
        assert not os.path.exists(cd) and os.path.isdir(os.path.join(w, ".trash", t["entry"]))
        lst = pm.trash_list(w)
        assert [x["place"] for x in lst] == ["zz_copy"], lst
        # restore while the id is free; a second trash + restore --as when taken
        pm.restore(t["entry"], w)
        assert os.path.isdir(cd) and not pm.trash_list(w)
        t2 = pm.trash("zz_copy", w)
        pm.duplicate("zz_old", "zz_copy", w)
        try:
            pm.restore(t2["entry"], w)
            raise AssertionError("restore onto an existing id must be refused")
        except pm.ManageError as e:
            assert "--as" in str(e)
        pm.restore(t2["entry"], w, as_id="zz_back")
        assert jr(os.path.join(w, "zz_back", "panel_state.json"))["place"] == "zz_back"
        # purge: typed confirmation, only inside .trash
        t3 = pm.trash("zz_back", w)
        for bad in ("wrong", ""):
            try:
                pm.purge(t3["entry"], bad, w)
                raise AssertionError("purge needs the typed id")
            except pm.ManageError:
                pass
        for bad in ("..", "../zz_old", ".", ""):
            try:
                pm.purge(bad, "zz_old", w)
                raise AssertionError(bad)
            except pm.ManageError:
                pass
        pm.purge(t3["entry"], "zz_back", w)
        assert not pm.trash_list(w) and os.path.isdir(os.path.join(w, "zz_old")) and os.path.isdir(w)
        # CLI
        out = subprocess.run([sys.executable, os.path.join(HERE, "place_manage.py"), "check-id", "--id", "zz_old", "--world-root", w], capture_output=True, text=True)
        res = json.loads(out.stdout.strip().splitlines()[-1])
        assert out.returncode == 2 and not res["ok"] and res["problems"], out.stdout
        out = subprocess.run([sys.executable, os.path.join(HERE, "place_manage.py"), "rename", "--place", "zz_old", "--new-id", "zz_cli", "--dry-run", "--world-root", w], capture_output=True, text=True)
        assert json.loads(out.stdout.strip().splitlines()[-1])["plan"]["rename_folder"] == ["world/zz_old", "world/zz_cli"], out.stdout + out.stderr
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("ok duplicate, trash, restore (--as), purge (typed confirm, path checks), CLI")


if __name__ == "__main__":
    test_check_id()
    test_edit()
    test_rename()
    test_duplicate_trash_restore_purge()
    print("all passed")
