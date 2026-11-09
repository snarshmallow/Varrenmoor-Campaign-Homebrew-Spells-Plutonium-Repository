"""Tiny settlements (population 0-19), blank places (create-blank) and the keyword parser's tiny words. Everything runs in a temp world root.
Run: python illustrator/generators/test_place_blank.py           (about 30 s: creates places, exports and validates 3D packs)
     python illustrator/generators/test_place_blank.py --quick   (no 3D export)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import place_create as pc  # noqa: E402
import place_text as ptx  # noqa: E402

QUIET = lambda *a, **k: None  # noqa: E731


def _files_ok(d, expect_buildings=None):
    """Every model file exists, parses and has the town_gen shapes; geometry inside the place bounds."""
    pj = json.load(open(os.path.join(d, "place.json"), encoding="utf-8"))
    W, H = pj["bounds"]["width_ft"], pj["bounds"]["height_ft"]
    st = json.load(open(os.path.join(d, "streets.json"), encoding="utf-8"))["streets"]
    ds = json.load(open(os.path.join(d, "districts.json"), encoding="utf-8"))["districts"]
    json.load(open(os.path.join(d, "water.json"), encoding="utf-8"))["water"]
    bl = [json.load(open(os.path.join(d, "buildings", f), encoding="utf-8")) for f in sorted(os.listdir(os.path.join(d, "buildings"))) if f.endswith(".json")]
    for e in st:
        assert e["geometry"]["type"] == "polyline" and len(e["geometry"]["points"]) >= 2 and e["geometry"]["width_ft"] > 0, e["id"]
        assert all(-1 <= p[0] <= W + 1 and -1 <= p[1] <= H + 1 for p in e["geometry"]["points"]), e["id"]
    for e in ds + bl:
        pts = e["geometry"]["points"]
        assert e["geometry"]["type"] == "polygon" and len(pts) >= 3, e["id"]
        assert all(0 <= p[0] <= W and 0 <= p[1] <= H for p in pts), (e["id"], pts)
    ids = [e["id"] for e in st + ds + bl]
    assert len(ids) == len(set(ids)), "duplicate ids"
    if expect_buildings is not None:
        assert expect_buildings(len(bl)), len(bl)
    return pj, st, ds, bl


def test_schema_tiny():
    e, w = pc.validate({"name": "x", "town": {"population": 0}})
    assert not e, e
    e, w = pc.validate({"name": "x", "town": {"population": 12}, "size_ft": [700, 500]})
    assert not e and not any("small for" in x for x in w), (e, w)       # the town-size warning must not misfire for tiny populations
    e, w = pc.validate({"name": "x", "town": {"population": 3, "layout": "walled", "wall": True}})
    assert not e and any("tiny-settlement" in x for x in w), w
    e, _ = pc.validate({"name": "x", "town": {"population": 3, "settlement": "castle"}})
    assert e, "unknown settlement kind must be an error"
    e, w = pc.validate({"name": "x", "town": {"population": 600}, "size_ft": [800, 800]})
    assert any("small for 600" in x for x in w), w                      # still fires for real towns
    s, _ = pc.normalise({})
    assert s["name"] and s["id"] and s["town"]["population"] == 600, s   # empty spec: generated name, default town
    for pop, size in ((0, [600, 400]), (1, [600, 450]), (12, [800, 600])):
        s, _ = pc.normalise({"name": "x", "town": {"population": pop}})
        assert s["size_ft"] == size and not pc.check_caps(s, False), (pop, s["size_ft"])
    s, _ = pc.normalise({"name": "x", "town": {"population": 2, "settlement": "cabin"}})
    assert s["size_ft"] == [400, 300] and s["_derived"]["category"] == "cabin"
    print("ok schema: population 0-19, settlement kinds, size warning, empty spec")


def test_tiny_pops(root):
    for pop, rec, check in ((0, "rolling", lambda n: n == 0), (1, "rolling", lambda n: 2 <= n <= 4), (5, "hills", lambda n: 2 <= n <= 6),
                            (12, "flat", lambda n: 3 <= n <= 7), (19, "valley", lambda n: 3 <= n <= 7)):
        spec = {"name": f"ZZ Tiny {pop}", "id": f"zz_tiny_{pop}", "terrain": {"recipe": rec}, "town": {"population": pop}}
        r = pc.create(spec, out_root=root)
        d = r["dir"]
        pj, st, ds, bl = _files_ok(d, check)
        if pop == 0:
            assert not st and not ds and not bl and "town" not in r["report"], r["report"]
            assert pj["kind"] == "wilderness"
        else:
            assert len(st) == 1 and st[0]["kind"] in ("lane", "road"), st
            assert any(x["kind"] == "district" for x in ds) and not os.path.exists(os.path.join(d, "town_params.json")) and not os.path.exists(os.path.join(d, "walls.json"))
            assert not any(x["kind"] == "square" and "market" in x["name"].lower() for x in ds), "no market at a farmstead"
            assert r["report"]["town"]["settlement"] in ("farmstead", "hamlet")
        assert max(pj["bounds"]["width_ft"], pj["bounds"]["height_ft"]) <= 800
        e, _ = pc.validate(json.load(open(os.path.join(d, "place_spec.json"), encoding="utf-8")))
        assert not e, e
    for kind, want in (("cabin", "house"), ("lodge", "stable"), ("inn", "inn")):
        r = pc.create({"name": f"ZZ {kind}", "id": f"zz_k_{kind}", "town": {"population": 3 if kind != "inn" else 8, "settlement": kind}}, out_root=root)
        pj, st, ds, bl = _files_ok(r["dir"], lambda n: n >= 1)
        assert any(b["kind"] == want for b in bl), (kind, [b["kind"] for b in bl])
        if kind == "inn":
            assert st[0]["kind"] == "road"
    # same spec + seed => same output
    a = pc.create({"name": "ZZ Rep", "id": "zz_rep", "seed": 5, "town": {"population": 4}}, out_root=root)
    b1 = open(os.path.join(a["dir"], "streets.json"), encoding="utf-8").read()
    pc.create({"name": "ZZ Rep", "id": "zz_rep", "seed": 5, "town": {"population": 4}}, out_root=root, force=True)
    assert open(os.path.join(a["dir"], "streets.json"), encoding="utf-8").read() == b1, "not deterministic"
    # a bigger place regenerated as a tiny one drops town_gen leftovers
    open(os.path.join(a["dir"], "walls.json"), "w").write("{}")
    pc.create({"name": "ZZ Rep", "id": "zz_rep", "seed": 5, "town": {"population": 0}}, out_root=root, force=True)
    assert not os.path.exists(os.path.join(a["dir"], "walls.json")) and not os.listdir(os.path.join(a["dir"], "buildings"))
    print("ok tiny populations 0, 1, 5, 12, 19 + cabin / lodge / inn: valid files, deterministic, no leftovers")


def test_blank(root):
    r = pc.create_blank("ZZ Blank", None, (600, 400), "flat", out_root=root)
    d = r["dir"]
    pj, st, ds, bl = _files_ok(d, lambda n: n == 0)
    assert not st and not ds and pj["kind"] == "blank" and pj["bounds"] == {"width_ft": 600, "height_ft": 400}
    meta = json.load(open(os.path.join(d, "terrain", "terrain_meta.json")))
    assert meta["pipeline"] == "flat_stub" and abs((meta["nx"] - 1) * meta["cell_ft"] - 600) < 1e-6 and abs((meta["ny"] - 1) * meta["cell_ft"] - 400) < 1e-6, meta
    try:
        pc.create_blank("ZZ Blank", None, (600, 400), "flat", out_root=root)
        raise AssertionError("second create without force must refuse")
    except ValueError:
        pass
    for bad in (dict(recipe="volcano"), dict(size_ft=(50, 50)), dict(pid="Bad Id!")):
        a = dict(name="ZZ B2", pid=None, size_ft=(600, 400), recipe="flat", out_root=root)
        a.update(bad)
        try:
            pc.create_blank(**a)
            raise AssertionError(f"bad input must raise: {bad}")
        except ValueError:
            pass
    dry = pc.create_blank("ZZ Dry", None, (1000, 800), "valley", dry_run=True, out_root=root)
    assert dry["dry_run"] and not os.path.exists(os.path.join(root, "zz_dry"))
    r2 = pc.create_blank("ZZ Ridge", "zz_ridge", (1200, 900), "highland_ridge", seed=3, relief_ft=120, out_root=root)
    assert r2["terrain"]["elev_max"] - r2["terrain"]["elev_min"] > 40, r2["terrain"]
    from PIL import Image
    img = os.path.join(root, "u.png")
    Image.new("RGB", (60, 40), (90, 120, 60)).save(img)
    r3 = pc.create_blank("ZZ Under", None, (600, 400), "flat", underlay=img, scale_ft_per_in=20, grid_ft=5, out_root=root)
    pj3 = json.load(open(os.path.join(r3["dir"], "place.json")))
    vs3 = json.load(open(os.path.join(r3["dir"], "view_settings.json")))
    assert pj3["import"]["underlay"] == "underlay/background.png" and os.path.exists(os.path.join(r3["dir"], "underlay", "background.png"))
    assert vs3["presets"]["town"]["scale_ft_per_in"] == 20 and vs3["presets"]["town"]["grid_ft"] == 5
    # CLI
    out = subprocess.run([sys.executable, os.path.join(HERE, "place_create.py"), "create-blank", "--name", "ZZ Cli", "--size-ft", "800", "500", "--recipe", "rolling_hills",
                          "--cell-ft", "10", "--seed", "4", "--out-root", root], capture_output=True, text=True)
    res = json.loads(out.stdout.strip().splitlines()[-1])
    assert res["ok"] and res["id"] == "zz_cli" and res["cell_ft"] == 10 and res["size_ft"] == [800, 500], out.stdout + out.stderr
    out = subprocess.run([sys.executable, os.path.join(HERE, "place_create.py"), "create-blank", "--name", "ZZ Cli", "--out-root", root], capture_output=True, text=True)
    assert out.returncode == 2 and not json.loads(out.stdout.strip().splitlines()[-1])["ok"]
    print("ok blank place (flat, ridge, underlay, scale/grid, refusals, dry run, CLI)")


def test_export(root):
    """The 3D world pack exports and validates for a blank place (0 buildings, 0 streets), a farmstead and a terrain-only place."""
    import worldpack
    for pid in ("zz_blank", "zz_tiny_5", "zz_tiny_0", "zz_k_inn"):
        out = os.path.join(root, "_pack_" + pid)
        worldpack.export_world(pid, out, lod=(1,), world_root=root, log=QUIET)
        r = subprocess.run([sys.executable, os.path.join(HERE, "worldpack.py"), "validate", "--place", pid, "--path", out], capture_output=True, text=True)
        assert r.returncode == 0 and "valid" in r.stdout, (pid, r.stdout[-600:], r.stderr[-600:])
    print("ok 3D export + validate: blank, farmstead, terrain only, inn")


def test_from_text_tiny():
    for t, pop, kind in (("a lone farmstead in the hills", 4, "farmstead"), ("hunter's lodge", 4, "lodge"), ("a single house", 3, "cabin"), ("lone cabin", 2, "cabin"),
                         ("roadside inn", 8, "inn"), ("hamlet of 12", 12, "auto"), ("a homestead with a family of five", 5, "farmstead"), ("no town, just hills", 0, None)):
        s, _ = ptx.parse(t)
        assert s["town"]["population"] == pop and s["town"].get("settlement") == kind, (t, s["town"])
        e, _ = pc.validate(s)
        assert not e, (t, e)
    s, _ = ptx.parse("market town with an inn")
    assert s["town"]["population"] >= 20, s["town"]          # an inn in a town is not a roadside inn
    print("ok from-text tiny words")


def main():
    quick = "--quick" in sys.argv
    root = tempfile.mkdtemp(prefix="vb_blank_")
    try:
        test_schema_tiny()
        test_from_text_tiny()
        test_tiny_pops(root)
        test_blank(root)
        if not quick:
            test_export(root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("all passed")


if __name__ == "__main__":
    main()
