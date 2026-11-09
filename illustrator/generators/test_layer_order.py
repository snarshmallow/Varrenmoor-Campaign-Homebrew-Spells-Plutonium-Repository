"""Label z-order (halos / backing strictly under label text) and small / empty places in render_world.
  - layer_order.py, presets/layer_order.json, render_world.SPEC and panel/lib/core.js LABEL_LAYERS agree; Label Backing is the bottom label layer
  - a render puts 'Label Backing' first (= under) in the SVG and every <id>_halo before its text (svg_sanity order check)
  - the headless preview (svg_raster) paints the glyph over its halo
  - empty place (blank: no districts / streets / buildings / water) renders without a crash; missing names fall back to ids;
    few labels -> no collisions; default label sizes grow with the sheet (34 x 22 = 2x)
Run: python illustrator/generators/test_layer_order.py      (a few seconds, synthetic models only)
"""
import json
import os
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layer_order as LO  # noqa: E402
import render_world as R  # noqa: E402
import svg_sanity as S  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
PID = "zz_layer_order_test"           # no world/<PID>: viewcfg falls back to its defaults


def test_sources_agree():
    js = json.load(open(LO.JSON_PATH, encoding="utf-8"))
    assert js == json.loads(json.dumps(LO.as_json())), "presets/layer_order.json is stale: python illustrator/generators/layer_order.py --write"
    spec = dict((n if isinstance(n, str) else n[0], [] if isinstance(n, str) else n[1]) for n in R.SPEC)
    assert [n if isinstance(n, str) else n[0] for n in R.SPEC] == LO.TOP_LAYERS, "render_world.SPEC top layers"
    assert spec["LABELS"] == LO.LABEL_LAYERS and LO.LABEL_LAYERS[-1] == LO.BACKING
    assert LO.backing_below_text(spec["LABELS"])
    core = open(os.path.join(HERE, "..", "panel", "lib", "core.js"), encoding="utf-8").read()
    m = re.search(r"var LABEL_LAYERS = (\[[^\]]*\]);", core)
    if m:
        panel = json.loads(m.group(1))
        assert panel == LO.LABEL_LAYERS, f"panel/lib/core.js LABEL_LAYERS {panel} != layer_order.LABEL_LAYERS {LO.LABEL_LAYERS}"
    print("ok layer order: layer_order.py == presets/layer_order.json == render_world.SPEC == panel core.js; Label Backing at the bottom")


def model(n_bld=3, names=True):
    poly = lambda x, y, w, h: {"type": "polygon", "points": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]}
    pl = {"id": PID, "name": "ZZ Layer Test", "bounds": {"width_ft": 600, "height_ft": 400}}
    ds = [{"id": "dis_core", "kind": "district", "geometry": poly(50, 50, 500, 300), **({"name": "Core Ward"} if names else {})}]
    st = [{"id": "str_main", "kind": "street", "geometry": {"type": "polyline", "points": [[40, 200], [560, 210]], "width_ft": 16}, **({"name": "Main Street"} if names else {})}]
    bl = [{"id": f"bld_{i}", "kind": "inn" if i == 0 else "smithy", "geometry": poly(100 + i * 140, 90, 90, 60), **({"name": f"House {i}"} if names else {"name": ""})}
          for i in range(n_bld)]
    return {"place": pl, "districts": ds, "streets": st, "water": [], "buildings": bl}


def render(m, tmp, name, page=None):
    out = os.path.join(tmp, name)
    R.render(m, "town", out, None, {"scale": 30, **({"page": page} if page else {})}, {"enabled": True})
    return out, ET.parse(out).getroot()


def texts(root, layer):
    g = next(e for e in root.iter(NS + "g") if e.get("id") == layer)
    return [(e.get("id").replace("_x5F_", "_"), float(e.get("font-size")), "".join(e.itertext())) for e in g if e.tag == NS + "text"]


def test_render_order(tmp):
    out, root = render(model(), tmp, "a.svg")
    lab = next(e for e in root if e.get("id") == "LABELS")
    kids = [e.get("id") for e in lab if e.tag == NS + "g"]
    assert kids[0] == LO.BACKING, kids                        # first in the file = painted first = bottom
    assert kids == list(reversed(LO.LABEL_LAYERS)), kids
    rep = S.check(out)
    assert rep["ok"], rep["errors"]
    halos = texts(root, LO.BACKING)
    assert halos and all(i.endswith("_halo") for i, _, _ in halos), halos
    # backing in the label's own layer (backing_layer off): the halo copy still comes first
    out2 = os.path.join(tmp, "b.svg")
    R.render(model(), "town", out2, None, {"scale": 30}, {"enabled": True}, [{"backing_layer": False}])
    r2 = ET.parse(out2).getroot()
    assert not texts(r2, LO.BACKING)
    b = texts(r2, "Labels - Buildings")
    ids = [i for i, _, _ in b]
    assert any(i.endswith("_halo") for i in ids) and all(ids.index(i) < ids.index(i[:-5]) for i in ids if i.endswith("_halo")), ids
    assert S.check(out2)["ok"]
    print("ok render: Label Backing first in LABELS (under all text), halo copies before their text, also without the backing layer")
    return out


def test_preview_order(tmp):
    """svg_raster paints in document order: a black glyph over a red halo stays black where the glyph is."""
    import svg_raster
    from PIL import Image
    halo = '<text id="g_x5F_halo" x="100" y="250" font-size="200" text-anchor="middle" style="font-family:Arial;fill:#ff0000;stroke:#ff0000;stroke-width:6">I</text>'
    txt = '<text id="g" x="100" y="250" font-size="200" text-anchor="middle" style="font-family:Arial;fill:#000000">I</text>'
    head = '<svg xmlns="http://www.w3.org/2000/svg" width="200pt" height="300pt" viewBox="0 0 200 300">'
    res = {}
    for nm, body in (("good", halo + txt), ("bad", txt + halo)):
        p = os.path.join(tmp, nm + ".svg")
        open(p, "w", encoding="utf-8").write(head + body + "</svg>")
        png, _ = svg_raster.rasterise(p, os.path.join(tmp, nm + ".png"), 72, 1, "#ffffff")
        res[nm] = Image.open(png).convert("RGB").getpixel((100, 180))
    assert res["good"][0] < 80 and res["good"][1] < 80, res          # glyph (black) on top
    assert res["bad"][0] > 180 and res["bad"][1] < 80, res           # the check can tell: halo drawn last covers the glyph
    print(f"ok preview: glyph over halo {res['good']} (halo-last would give {res['bad']})")


def test_render_preview_real(tmp, svg):
    """the real render's preview: at a building label's centre the text colour wins over the white halo somewhere in the box."""
    import svg_raster
    from PIL import Image
    png, _ = svg_raster.rasterise(svg, os.path.join(tmp, "a.png"), 144, 1, "#faf7ee")
    im = Image.open(png).convert("L")
    root = ET.parse(svg).getroot()
    g = next(e for e in root.iter(NS + "g") if e.get("id") == "Labels - Buildings")
    t = next(e for e in g if e.tag == NS + "text")
    x, y, fs = float(t.get("x")), float(t.get("y")), float(t.get("font-size"))
    box = (int((x - fs) * 2), int((y - fs * 0.8) * 2), int((x + fs) * 2), int(y * 2))
    dark = im.crop(box).getextrema()[0]
    assert dark < 90, f"no dark glyph pixels at the label: halo painted over the text? (min luma {dark})"
    print(f"ok preview of a real render: label glyphs visible over their halos (min luma {dark})")


def test_empty_and_names(tmp):
    m = model(0)
    m["districts"], m["streets"] = [], []
    out, root = render(m, tmp, "empty.svg")
    assert S.check(out)["ok"]
    assert all(not texts(root, n) for n in ("Labels - Districts", "Labels - Streets", "Labels - Buildings", LO.BACKING))
    m = {"place": model()["place"]}            # bare model: only place.json
    out, root = render(m, tmp, "bare.svg")
    assert S.check(out)["ok"]
    out, root = render(model(names=False), tmp, "noname.svg")
    allt = [t for n in ("Labels - Districts", "Labels - Buildings", "Labels - Streets", "Labels - Hidden") for t in texts(root, n)]
    words = " ".join(t for _, _, t in allt)
    assert "bld_0" in words or "bld 0" in words.replace("_", " "), words
    print("ok empty place (no entities, and a bare place.json-only model) renders; missing / blank names fall back to ids")


def test_few_labels_and_sheet(tmp):
    import label_offset as lbo
    out, root = render(model(), tmp, "few.svg")
    man = json.load(open(out + ".labels.json", encoding="utf-8")) if os.path.exists(out + ".labels.json") else None
    shown = [(i, s, t) for n in ("Labels - Districts", "Labels - Buildings", "Labels - Streets") for (i, s, t) in texts(root, n)]
    assert len(shown) >= 3, shown
    if man:          # declutter QA on (the default): a small place must place its few labels without collisions
        q = man["qa"]
        assert q["label_label_overlaps"] == 0 and q["hidden_by_collision"] == 0 and q["leaders_crossing_other_labels"] == 0, q
    out2, root2 = render(model(), tmp, "big.svg", page="34x22")
    s1 = {i: s for i, s, _ in texts(root, "Labels - Buildings")}
    s2 = {i: s for i, s, _ in texts(root2, "Labels - Buildings")}
    common = set(s1) & set(s2)
    assert common and all(abs(s2[i] / s1[i] - 2.0) < 0.05 for i in common), (s1, s2)
    print(f"ok few labels: {len(shown)} shown; default sizes follow the sheet (17x11 {sorted(s1.values())[:1]} -> 34x22 {sorted(s2.values())[:1]})")


if __name__ == "__main__":
    tmp = tempfile.mkdtemp()
    try:
        test_sources_agree()
        svg = test_render_order(tmp)
        test_preview_order(tmp)
        test_render_preview_real(tmp, svg)
        test_empty_and_names(tmp)
        test_few_labels_and_sheet(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("layer_order: all checks passed")
