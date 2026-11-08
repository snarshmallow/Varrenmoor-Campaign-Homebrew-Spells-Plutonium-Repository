"""Checks for place_create.py / place_terrain.py / place_text.py / foundry_import.py and the Bridgehollow regression.
Run: python illustrator/generators/test_place_create.py            (about a minute; creates and deletes world/zz_test_* folders)
     python illustrator/generators/test_place_create.py --quick     (no town generation)
"""
import filecmp
import json
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_import as fi  # noqa: E402
import place_create as pc  # noqa: E402
import place_stats as ps  # noqa: E402
import place_terrain as pt  # noqa: E402
import place_text as ptx  # noqa: E402
import terrain as T  # noqa: E402

REPO = pc.REPO
WORLD = os.path.join(REPO, "world")


def test_schema_and_validation():
    assert os.path.exists(pc.SCHEMA_PATH), "run place_create.py write-schema"
    on_disk = json.load(open(pc.SCHEMA_PATH, encoding="utf-8"))
    assert on_disk == pc.SPEC_SCHEMA, "world/schema/place-spec.schema.json is stale: run place_create.py write-schema"
    e, w = pc.validate({"name": "Ok"})
    assert not e, e
    e, _ = pc.validate({})
    assert any("name" in x for x in e)
    e, _ = pc.validate({"name": "x", "terrain": {"recipe": "volcano"}})
    assert e and "volcano" in e[0], e
    e, _ = pc.validate({"name": "x", "town": {"population": 5}})
    assert e and "minimum" in e[0], e
    e, _ = pc.validate({"name": "x", "bogus": 1})
    assert e and "unknown field" in e[0], e
    e, _ = pc.validate({"name": "x", "styles": {"house": ["nope_style"]}})
    assert e and "nope_style" in e[0], e
    e, w = pc.validate({"name": "x", "town": {"layout": "walled", "wall": False}})
    assert not e and w
    print("ok schema + validation")


def test_templates_valid():
    t = pc.templates()
    assert len(t) >= 5, list(t)
    for k, spec in t.items():
        e, _ = pc.validate(spec)
        assert not e, (k, e)
        s, _ = pc.normalise(spec)
        assert not pc.check_caps(s, False), (k, pc.check_caps(s, False))
    print("ok", len(t), "templates validate and fit the caps")


def test_caps():
    s, _ = pc.normalise({"name": "Big", "town": {"population": 12000}})
    assert pc.check_caps(s, False), "12000 people must hit a cap"
    s2, _ = pc.normalise({"name": "Big", "town": {"population": 12000}, "limits": {"allow_large": True}})
    assert not pc.check_caps(s2, False)
    s3, _ = pc.normalise({"name": "Mid", "town": {"population": 2800}})
    assert any("buildings" in x for x in pc.check_caps(s3, False)) and not any("buildings" in x for x in pc.check_caps(s3, True)), "draft skips the building cap"
    print("ok caps")


def test_from_text():
    spec, notes = ptx.parse("walled coastal town of 800 people with a big river, Danish style, hilly")
    assert spec["terrain"]["recipe"] == "coastal" and spec["town"]["population"] == 800 and spec["town"]["layout"] == "walled" and spec["culture"] == "danish_german"
    assert spec["terrain"]["rivers"] == 1 and spec["terrain"]["river_width_ft"] >= 100
    assert any("ignored words" in n and "hilly" in n for n in notes), "unrecognised-by-priority words are reported, not silently used"
    s2, _ = ptx.parse("a tiny Norse fishing hamlet on the east coast, called Ulfvik, no river")
    assert s2["name"] == "Ulfvik" and s2["culture"] == "scandinavian" and s2["terrain"]["recipe"] == "coastal" and s2["terrain"]["sea_side"] == "east" and s2["terrain"]["rivers"] == 0 and s2["town"]["population"] <= 60
    s3, _ = ptx.parse("a big cold mountain city in winter with two lakes")
    assert s3["town"]["population"] >= 4500 and s3["climate"] == "cold" and s3["season"] == "winter" and s3["terrain"]["lakes"] == 2
    for t in ("walled coastal town of 800 people with a big river, Danish style", "a village", "a city on an island", "lazy river valley hamlet of 120 folk"):
        sp, _ = ptx.parse(t)
        e, _ = pc.validate(sp)
        assert not e, (t, e)
    print("ok from-text")


def test_terrain_recipes():
    """Every recipe makes a finite heightmap, water entities and a plausible centre; the sea recipes have a sea."""
    for rec in pt.RECIPES:
        spec, info = pt.build_terrain_spec({"recipe": rec, "cell_ft": 20}, 2000, 1300, 11)
        h, meta = T.generate(spec)
        assert np.isfinite(h).all(), rec
        assert h.max() - h.min() > 3, rec
        w = pt.build_water(spec, info, h, meta, "x", {"river_names": ["R"]})
        kinds = [e["kind"] for e in w]
        if rec in ("coastal", "island", "fjord"):
            assert "sea" in kinds, (rec, kinds)
        if rec in ("rolling", "valley", "bowl", "hills", "flat"):
            assert "river" in kinds, (rec, kinds)
    # high ground (the old exp() underflow produced NaN above about 2200 ft)
    spec, info = pt.build_terrain_spec({"recipe": "mountain", "base_elevation_ft": 3000, "cell_ft": 20}, 2000, 1300, 3)
    h, _ = T.generate(spec)
    assert np.isfinite(h).all() and h.max() > 3000
    # rotation: the sea moves with sea_side
    for side, test in (("east", lambda h: h[:, -1].mean() < h[:, 0].mean()), ("west", lambda h: h[:, 0].mean() < h[:, -1].mean()),
                       ("north", lambda h: h[0].mean() < h[-1].mean()), ("south", lambda h: h[-1].mean() < h[0].mean())):
        spec, info = pt.build_terrain_spec({"recipe": "coastal", "sea_side": side, "cell_ft": 20, "rivers": 0}, 2000, 1300, 5)
        h, _ = T.generate(spec)
        assert test(h), side
    print("ok", len(pt.RECIPES), "terrain recipes")


def test_elevation_adapt():
    ref = np.linspace(625, 1002, 1000)
    info = ps.adapt_info(ref, 0.0)
    assert abs(ps.remap(700, info) - 700) < 20, "same range: thresholds barely move"
    low = np.linspace(2, 60, 1000)                                   # a flat coast
    li = ps.adapt_info(low, 0.0)
    assert li["hi"] - li["lo"] >= ps.MIN_RANGE_FT
    assert ps.remap(2, li) == 2 and ps.remap(-4, li) == -4, "shore bands stay datum-relative"
    assert ps.remap(980, li) < 250, "an alpine snow line cannot sit at 980 ft on a coast"
    phases = [{"id": "s", "elev_min": 740, "elev_max": None, "elev_blend_ft": 100}]
    a = ps.adapt_phases(phases, li)
    assert a[0]["elev_max"] is None and a[0]["elev_min"] < 200 and phases[0]["elev_min"] == 740, "input not mutated"
    print("ok elevation adaptation")


def test_naming_sets():
    import town_gen as tg
    for c in pc.CULTURES + ("bridgehollow_legacy",):
        nm = json.load(open(os.path.join(tg.NAMING_DIR, c + ".json"), encoding="utf-8"))
        for k in ("civic", "residential", "farm"):
            assert len(nm["streets"][k]) >= 6 and nm["district_notes"][k], (c, k)
        for k in ("hall", "court", "tax", "lockup", "inn", "stables", "meeting", "smithy", "gate", "mill"):
            assert nm["buildings"][k]["id"].startswith("bld_") and nm["buildings"][k]["name"], (c, k)
    assert tg.load_naming({"place": "bridgehollow_big"})["id"] == "bridgehollow_legacy"
    assert tg.load_naming({"place": "anything"})["id"] == "fantasy_generic"
    assert tg.load_naming({"place": "x", "naming_set": "scandinavian", "naming": {"buildings": {"inn": {"name": "Salted Cod"}}}})["buildings"]["inn"]["name"] == "Salted Cod"
    print("ok naming sets")


def test_bridgehollow_regression():
    """Regenerating Bridgehollow with its committed params (default seed) gives byte-identical streets, districts, report and buildings; the heightmap too."""
    import town_gen
    out = tempfile.mkdtemp(prefix="vb_bh_")
    try:
        g = town_gen.generate(os.path.join(WORLD, "bridgehollow", "town_params.json"), {}, verbose=False, place_dir=os.path.join(WORLD, "bridgehollow"), out_dir=out)
        g.write()
        ref = os.path.join(WORLD, "bridgehollow")
        for f in ("streets.json", "districts.json", "town_gen_report.json"):
            assert filecmp.cmp(os.path.join(out, f), os.path.join(ref, f), shallow=False), f + " differs from the committed Bridgehollow data"
        names = sorted(os.listdir(os.path.join(out, "buildings")))
        assert names == sorted(os.listdir(os.path.join(ref, "buildings"))), "building set differs"
        bad = [n for n in names if not filecmp.cmp(os.path.join(out, "buildings", n), os.path.join(ref, "buildings", n), shallow=False)]
        assert not bad, bad[:5]
        spec = json.load(open(os.path.join(ref, "terrain_spec.json"), encoding="utf-8"))
        h, _ = T.generate(spec)
        assert np.array_equal(h, np.load(os.path.join(ref, "terrain", "heightmap.npy"))), "Bridgehollow heightmap changed"
    finally:
        shutil.rmtree(out, ignore_errors=True)
    print("ok Bridgehollow regression: streets, districts, report, 148 buildings and the heightmap are byte-identical")


def test_create_end_to_end():
    """A hamlet and a (draft) walled coastal town through create -> files -> town_gen -> styles -> walls, then not Bridgehollow-like."""
    made = []
    try:
        spec = pc.templates()["farming_hamlet"]
        r = pc.create(dict(spec, id="zz_test_hamlet"), force=True)
        made.append(r["dir"])
        d = r["dir"]
        for f in ("place.json", "terrain_spec.json", "water.json", "town_params.json", "streets.json", "districts.json", "view_settings.json", "place_spec.json", "create_report.json", "town_gen_report.json",
                  "terrain/heightmap.npy", "terrain/terrain_meta.json"):
            assert os.path.exists(os.path.join(d, f)), f
        pj = json.load(open(os.path.join(d, "place.json"), encoding="utf-8"))
        assert pj["id"] == "zz_test_hamlet" and pj["phase_elevation"] == "percentile" and pj["bounds"]["width_ft"] >= 1600 and pj["population_estimate"] == 90
        names = " ".join(e["name"] for e in json.load(open(os.path.join(d, "streets.json"), encoding="utf-8"))["streets"]) + " " + " ".join(
            e["name"] for e in json.load(open(os.path.join(d, "districts.json"), encoding="utf-8"))["districts"])
        for banned in ("Authority", "Commoners", "Pilgrim", "Warden", "Court Row", "Bridgehollow"):
            assert banned not in names, (banned, names)
        blds = [json.load(open(os.path.join(d, "buildings", f), encoding="utf-8")) for f in os.listdir(os.path.join(d, "buildings"))]
        assert blds and all(b.get("style") for b in blds), "every building gets a culture style"
        assert not any("Warden" in b["name"] or "Magistrate" in b["name"] for b in blds)
        pr = pc.create(dict(spec, id="zz_test_hamlet"), force=False, dry_run=True)
        assert pr["dry_run"]
        try:
            pc.create(dict(spec, id="zz_test_hamlet"))
            raise AssertionError("existing place must not be overwritten without force")
        except SystemExit as e:
            assert "already exists" in str(e)
        # same spec + seed = same place
        a = open(os.path.join(d, "streets.json"), "rb").read()
        pc.create(dict(spec, id="zz_test_hamlet"), force=True)
        assert open(os.path.join(d, "streets.json"), "rb").read() == a, "deterministic"
        # walled draft coastal town with another culture
        spec2 = dict(pc.templates()["walled_hill_town"], id="zz_test_walled", terrain={"recipe": "coastal", "sea_side": "east", "rivers": 1}, culture="scandinavian")
        spec2["town"] = dict(spec2["town"], population=420, central_feature="temple")
        r2 = pc.create(spec2, force=True, draft=True)
        made.append(r2["dir"])
        assert r2["report"]["draft"] and os.path.exists(os.path.join(r2["dir"], "walls.json"))
        w = json.load(open(os.path.join(r2["dir"], "walls.json"), encoding="utf-8"))
        assert w["walls"] and w["gates"], "wall with gates"
        wat = json.load(open(os.path.join(r2["dir"], "water.json"), encoding="utf-8"))["water"]
        assert any(e["kind"] == "sea" for e in wat)
        # the existing tools take --place <id>
        import render_world as rw
        out = os.path.join(tempfile.gettempdir(), "zz_test_walled.svg")
        rw.render(rw.load_place("zz_test_walled"), "town", out, None)
        assert os.path.getsize(out) > 1000 and "Walls" in open(out, encoding="utf-8").read()
        os.remove(out)
        import worldpack
        man = worldpack.export_world("zz_test_hamlet", os.path.join(tempfile.gettempdir(), "zz_test_pack"), lod=(1,), log=lambda *a: None)
        assert man and man.get("place", {}).get("id") == "zz_test_hamlet", "world pack export works on a generated place"
    finally:
        for p in made:
            shutil.rmtree(p, ignore_errors=True)
        shutil.rmtree(os.path.join(tempfile.gettempdir(), "zz_test_pack"), ignore_errors=True)
    print("ok create end to end (hamlet, walled draft coast): files, names, styles, determinism, render_world")


def test_import_scene():
    """Scene document -> place: calibration from the grid, wall chaining, closed loops, links; a mocked scene (no Foundry)."""
    ppf = 10.0
    sc = {"_id": "abc", "name": "Mock Hall", "width": 2000, "height": 1000, "padding": 0.0, "grid": {"size": 50, "distance": 5, "units": "ft"},
          "background": {"src": None}, "levels": [{"background": {"src": "nowhere/x.webp"}}],
          "walls": [{"c": [100, 100, 300, 100], "door": 0}, {"c": [300, 100, 300, 300], "door": 0}, {"c": [300, 300, 100, 300], "door": 0}, {"c": [100, 300, 100, 100], "door": 0},
                    {"c": [500, 500, 900, 500], "door": 1}, {"c": [900, 500, 900, 520], "door": 0}],
          "lights": [{"x": 200, "y": 200, "config": {"bright": 20, "dim": 40, "color": "#ffaa00"}}], "tokens": [{"x": 150, "y": 150, "name": "Bob", "width": 1, "height": 1}], "notes": [{"x": 5, "y": 5, "text": "hi"}]}
    c = fi.calibration(sc)
    assert abs(c["ppf"] - ppf) < 1e-9 and abs(c["width_ft"] - 200) < 1e-9
    assert abs(fi.calibration(dict(sc, grid={"size": 100, "distance": 1, "units": "m"}))["ppf"] - 100 / 3.28084) < 1e-6
    assert fi.background_src(sc) == "nowhere/x.webp"
    root = tempfile.mkdtemp(prefix="vb_imp_")
    try:
        r = fi.import_scene(sc, "Scene.abc", "mock_hall", ("walls", "lights", "tokens", "notes"), root=root, no_image=True)
        d = os.path.join(root, "mock_hall")
        assert r["closed_loops"] == 1 and r["wall_polylines"] == 1 and r["walls"] == 6, r
        pj = json.load(open(os.path.join(d, "place.json"), encoding="utf-8"))
        assert pj["links"]["foundry_scene"] == "Scene.abc" and pj["bounds"] == {"width_ft": 200.0, "height_ft": 100.0}
        assert pj["import"]["grid"] == {"size": 50.0, "distance": 5.0, "units": "ft"}
        b = json.load(open(os.path.join(d, "buildings", "bld_imp_001.json"), encoding="utf-8"))
        assert sorted(map(tuple, b["geometry"]["points"])) == [(10.0, 10.0), (10.0, 30.0), (30.0, 10.0), (30.0, 30.0)]
        L = json.load(open(os.path.join(d, "foundry_lights.json"), encoding="utf-8"))["lights"][0]
        assert L["point"] == [20.0, 20.0] and L["bright_ft"] == 20.0
        T_ = json.load(open(os.path.join(d, "foundry_tokens.json"), encoding="utf-8"))["tokens"][0]
        assert T_["point"] == [17.5, 17.5], T_
        fw = json.load(open(os.path.join(d, "foundry_walls.json"), encoding="utf-8"))["walls"]
        assert fw[0]["kind"] == "door" and len(fw[0]["points"]) == 3
        try:
            fi.import_scene(sc, "Scene.abc", "mock_hall", root=root, no_image=True)
            raise AssertionError("exists")
        except ValueError as e:
            assert "already exists" in str(e)
        dr = fi.import_scene(sc, "Scene.abc", "other", root=root, dry_run=True)
        assert dr["dry_run"] and not os.path.exists(os.path.join(root, "other"))
        # offsets: padding moves the origin
        sc2 = dict(sc, padding=0.25)
        c2 = fi.calibration(sc2)
        assert c2["sceneX"] == round(2000 * 0.25 / 50) * 50
    finally:
        shutil.rmtree(root, ignore_errors=True)
    # push-scene defaults to the linked scene
    import foundry_push as fp
    assert fp.place_link("zz_does_not_exist") is None
    print("ok import-scene (mock)")


def main():
    quick = "--quick" in sys.argv
    for t in (test_schema_and_validation, test_templates_valid, test_caps, test_from_text, test_terrain_recipes, test_elevation_adapt, test_naming_sets, test_import_scene):
        t()
    if not quick:
        test_bridgehollow_regression()
        test_create_end_to_end()
    print("all passed")


if __name__ == "__main__":
    main()
