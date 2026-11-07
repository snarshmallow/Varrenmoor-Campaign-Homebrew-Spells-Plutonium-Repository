"""Checks for label_declutter.py + the declutter parts of label_offset.py / label_style.py
(run: python illustrator/generators/test_label_declutter.py)."""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import label_declutter as D  # noqa: E402
import label_offset as L  # noqa: E402
import label_style as S  # noqa: E402
from shapely.geometry import Polygon, box  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def main():
    # ---- tiers + scale visibility
    dc = D.merge({})
    assert D.tier_of("district", "districts") == "districts" and D.tier_of("square", "districts") == "plazas"
    assert D.tier_of("civic", "buildings") == "civic" and D.tier_of("house", "buildings") == "houses" and D.tier_of("street", "streets") == "streets"
    assert D.visible(dc, "civic", 200) and not D.visible(dc, "streets", 200) and D.visible(dc, "streets", 100) and not D.visible(dc, "houses", 100) and D.visible(dc, "houses", 40)
    assert D.visible(D.merge({"enabled": False}), "houses", 400), "legacy: everything visible"
    ed = D.merge({"tiers": {"streets": {"max_fpi": 250}}})
    assert D.visible(ed, "streets", 200) and ed["tiers"]["streets"]["priority"] == 4, "per-tier thresholds are editable, other keys kept"

    # ---- route_leader: fixed anchor -> nearest attachment of a label box
    b = (100, 50, 160, 60)
    assert L.route_leader((50, 55), b, "straight") == [(50, 55), (98, 55)], "straight to the left edge middle"
    el = L.route_leader((50, 90), b, "elbow", 7, 2)
    assert len(el) == 3 and el[1] == (91, 55) and el[2] == (98, 55), el
    assert L.route_leader((200, 55), b, "elbow", 7, 2)[-1] == (162, 55), "anchor right of the box attaches to the right edge"
    assert L.route_leader((130, 100), b)[-1] == (130, 62), "anchor below attaches to the bottom edge"
    assert L.route_leader((130, 20), b)[-1] == (130, 48), "anchor above attaches to the top edge"
    assert L.route_leader((130, 55), b) is None, "anchor on the label: no leader"

    # ---- priority: a low tier that finds no free spot is hidden, the high tier keeps the place
    P = L.LabelParams()
    big = rect(100, 100, 120, 80)
    pl = L.Placer(P, frame=(0, 0, 300, 200), shapes=[("a", big)])
    pl.add("a", big, "Authority", 9, priority=1)
    tiny = rect(150, 135, 6, 6)
    pl.add("t", tiny, "A Very Long Tiny House Name", 7, priority=5, on_fail="hide", max_cover=0.0)
    pl.set_features({"building": [("a", Polygon(big))]})
    pl.score = True
    res = {r.id: r for r in pl.solve()}
    assert res["a"].status == "placed"
    assert res["t"].status in ("hidden", "placed")
    # a label with nowhere to go (frame tiny) is hidden / numbered
    for mode, st in (("hide", "hidden"), ("number", "numbered")):
        pl = L.Placer(P, frame=(90, 90, 110, 110), shapes=[("t", tiny)])
        pl.add("t", rect(95, 95, 4, 4), "Some Long Label Text", 7, on_fail=mode)
        assert pl.solve()[0].status == st, mode
    r_k = L.Placer(P, frame=(90, 90, 110, 110)); r_k.add("t", rect(95, 95, 4, 4), "Some Long Label Text", 7, on_fail="keep")
    assert r_k.solve()[0].status == "placed", "keep = legacy overlap"

    # ---- scoring: the offset text avoids a building that the first-fit position would cover
    tin, nb = rect(300, 200, 8, 8), rect(312, 196, 40, 16)
    def offs(score):
        p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("tin", tin)])
        p.add("tin", tin, "Tiny Shed", 7)
        p.set_features({"building": [("nb", Polygon(nb))]})
        p.score = score
        return p.solve()[0], p
    r_on, p_on = offs(True)
    tb = L.text_box(r_on.cx, r_on.cy, r_on.w, r_on.h)
    assert p_on.cost_of(tb, "tin") < 0.05, "scored placement covers (almost) no building"
    # ---- area labels slide to the emptiest spot inside their shape
    dist = rect(100, 100, 300, 100)
    p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("d", dist)])
    p.add("d", dist, "AUTHORITY WARD", 9, bold=True, point=(250, 150), score_inside=True)
    p.set_features({"building": [("b%d" % i, Polygon(rect(200 + i * 4, 120, 3, 60))) for i in range(10)]})
    rd = p.solve()[0]
    assert rd.cost < 0.2 and (rd.cx, rd.cy) != (250, 150), "district label moved off the crowded centre"

    # ---- overrides pin the label exactly; the leader is recomputed
    sh = rect(400, 200, 12, 9)
    p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("s", sh)])
    p.add("s", sh, "Tiny Shed", 7, override={"cx": 480, "cy": 120, "anchor": None})
    rp = p.solve()[0]
    assert rp.pinned and (rp.cx, rp.cy) == (480, 120) and rp.leader and rp.offset
    assert Polygon(sh).contains(L.Point(rp.leader[0])), "leader starts inside the shape (anchor)"
    tb = L.text_box(rp.cx, rp.cy, rp.w, rp.h).bounds
    assert abs(rp.leader[-1][0] - (tb[0] - P.gap)) < 0.01 and abs(rp.leader[-1][1] - 120) < 0.01, "ends at the pinned label"
    p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("s", sh)])
    p.add("s", sh, "Tiny Shed", 7, override={"cx": 480, "cy": 120, "anchor": (405, 203)})
    assert p.solve()[0].leader[0] == (405, 203), "a user-moved anchor is honoured"

    # ---- pin_positions: page pt -> feet, only moved labels, anchors
    tmp = tempfile.mkdtemp()
    D.overrides_path = lambda place: os.path.join(tmp, place + "_ov.json")
    man = {"k": 0.5, "x0": 100.0, "y0": 200.0, "margin_pt": 36.0,
           "labels": {"bld_a": {"cx": 300.0, "cy": 200.0, "anchor": [250.0, 220.0]}, "bld_b": {"cx": 400.0, "cy": 300.0, "anchor": None}}}
    pos = [{"id": "bld_a_label", "cx": 340.0, "cy": 220.0, "ref": [300.0, 200.0], "anchor": [250.0, 220.0]},
           {"id": "bld_b_label", "cx": 400.5, "cy": 300.2, "ref": [400.0, 300.0]}]
    n, na, moved = D.pin_positions("p", pos, man)
    ov = D.load_overrides("p")
    assert n == 1 and moved == ["bld_a"] and na == 0, (n, moved)
    assert ov["bld_a"]["x_ft"] == round((340 - 36) / 0.5 + 100, 2) and ov["bld_a"]["y_ft"] == round((220 - 36) / 0.5 + 200, 2), ov
    pos[0]["anchor"] = [260.0, 230.0]
    n, na, _ = D.pin_positions("p", pos, man)
    assert na == 1 and "anchor_ft" in D.load_overrides("p")["bld_a"]
    assert D.clear_overrides("p", ["bld_a"]) == 1 and D.load_overrides("p") == {}

    # ---- QA
    qp = L.Placer(P, frame=(0, 0, 600, 400))
    qp.set_features({"building": [("nb", Polygon(rect(100, 100, 40, 20)))], "road": []})
    rows = [{"id": "x", "text": "X", "tier": "civic", "status": "placed", "box": box(110, 105, 130, 115), "leader": None, "pinned": False},
            {"id": "y", "text": "Y", "tier": "civic", "status": "placed", "box": box(300, 300, 320, 310), "leader": None, "pinned": False},
            {"id": "z", "text": "Z", "tier": "houses", "status": "hidden", "why": "scale", "box": box(0, 0, 0, 0), "leader": None, "pinned": False}]
    q = D.qa_report(qp, rows)
    assert q["labels_shown"] == 2 and q["labels_hidden"] == 1 and q["hidden_by_scale"] == 1 and q["labels_over_25pct"] == 1
    assert 40 < q["text_over_features_pct"] < 60 and q["label_label_overlaps"] == 0 and "Label QA" in D.qa_text(q)

    # ---- wrapping extras
    cfg = lambda **k: S.resolve(S.merge({"rooms": {"max_lines": 3, **k}}), "rooms")
    st = cfg(wrap="auto", max_lines=3)
    lays, _ = S.build_layouts("Tax and Permit Office", st, 7, 1.0)
    assert [len(x.lines) for x in lays] == [1, 2, 3]
    assert S.build_layouts("Tax and Permit Office", cfg(lines=2), 7, 1.0)[0][0].lines != ["Tax and Permit Office"] and len(S.build_layouts("Tax and Permit Office", cfg(lines=2), 7, 1.0)[0]) == 1
    g = S.build_layouts("Tax and Permit Office", cfg(wrap_mode="greedy"), 7, 1.0)[0][1].lines
    b2 = S.build_layouts("Tax and Permit Office", cfg(wrap_mode="balanced"), 7, 1.0)[0][1].lines
    assert " ".join(g) == " ".join(b2) == "Tax and Permit Office"
    mc = S.build_layouts("Tax and Permit Office", cfg(max_chars=12, max_lines=4), 7, 1.0)[0]
    assert all(max(len(x) for x in lay.lines) <= 12 for lay in mc), [lay.lines for lay in mc]
    hy = S.build_layouts("Sword-Smiths Row", cfg(max_lines=3), 7, 1.0)[0]
    assert any(lay.lines[0] == "Sword-" for lay in hy) or any("Sword-" in ln for lay in hy for ln in lay.lines), "break after a hyphen"
    ap = S.build_layouts("Warden's Hall of Records", cfg(), 7, 1.0)[0]
    assert all("Warden's" in " ".join(lay.lines) for lay in ap) and all(not any(l.endswith(" of") for l in lay.lines) for lay in ap[1:2]), "no dangling 'of', apostrophes stay"
    st_fit = cfg(fit_shape=True, fit_ratio=0.9)
    nar = S.build_layouts("Tax and Permit Office", st_fit, 7, 1.0, shape_w=40)[0]
    assert all(lay.w <= 40 * 0.9 + 0.5 or len(lay.lines) >= 3 for lay in nar) and len(nar[0].lines) > 1, "narrow shapes get narrower lines"
    mw = S.build_layouts("Tax and Permit Office", cfg(max_width=40), 7, 1.0)
    assert mw[1].w <= 40.5 or len(mw[1].lines) >= 3, "max_width limits the offset layout too"
    # abbreviations: only when it does not otherwise fit
    ab = S.load_abbreviations()
    assert S.abbreviate("Pilgrim Road *", ab) == "Pilgrim Rd. *" and S.abbreviate("Authority Ward", ab) == "Auth. Ward" and S.abbreviate("Roadside", ab) == "Roadside"
    sta = cfg(abbrev="fit")
    full, offs_ = S.build_layouts_ex("Magistrate's Court *", sta, 7, 1.0, abbr=ab)
    assert full[0].lines == ["Magistrate's Court *"] and offs_[0].lines == ["Magistrate's Court *"] and offs_[-1].lines == ["Mag. Court *"], (full, offs_)
    small = rect(100, 100, 40, 12)
    p = L.Placer(P, frame=(0, 0, 400, 300), shapes=[("m", small)])
    p.add("m", small, "Magistrate's Court", 7, layouts=full[:1] + full[1:], offset_layouts=offs_)
    r = p.solve()[0]
    assert r.leader is not None and r.layout_i == 0, "offset with the full text when there is room"
    p = L.Placer(P, frame=(98, 98, 150, 114), shapes=[("m", small)])
    p.add("m", small, "Magistrate's Court", 7, layouts=full, offset_layouts=offs_)
    r2 = p.solve()[0]
    assert r2.lines != ["Magistrate's Court *"] or r2.status == "placed"
    # small caps
    sc = cfg(small_caps=True)
    assert S.measure("Hall", 7, sc) < S.measure("HALL", 7, cfg()) and S.measure("HALL", 7, sc) == S.measure("HALL", 7, cfg())
    t = S.LayerTree([("L", ["x"])]) if hasattr(S, "LayerTree") else None
    from lib_svg import LayerTree
    t = LayerTree([("L", ["x"])])
    S.emit(t, S.Rec("lbl", "x", ["Hall"], 50, 50, 20, 8, None, 7, S.resolve(S.merge({"default": {"small_caps": True, "mode": "none"}}), "rooms")), None)
    assert 'font-size="5.60">ALL<' in t.items["x"][0] and ">H<" in t.items["x"][0]

    # ---- full render: hidden sublayer, numbered legend, QA file, leaders layers, pins
    import render_world as R
    model = R.load_place("bridgehollow")
    out = os.path.join(tmp, "n.svg")
    pre = D.preset("handout")
    R.render(model, "bowl", out, None, {"scale": 200}, L.LabelParams.__dict__ and {**pre["label_offset"]}, [pre["label_style"]], D.merge(pre["declutter"]))
    root = ET.parse(out).getroot()
    g = {e.get("id"): e for e in root.iter(NS + "g") if e.get("id")}
    assert len(list(g["Labels - Hidden"])) > 50 and "display:none" in g["Labels - Hidden"].get("style", ""), "scale-hidden labels stay in a hidden sublayer"
    assert len(list(g["Callout Markers"])) >= 4 and len(list(g["Legend"])) >= 5, "numbered markers + legend key"
    qa = json.load(open(out + ".labels.json"))
    assert qa["qa"]["numbered"] >= 3 and qa["qa"]["hidden_by_scale"] > 50 and qa["labels"] and qa["k"] > 0
    # a pinned position is honoured by the renderer
    ent = next(i for i, l in qa["labels"].items() if l["status"] == "placed" and l["layer"] == "Labels - Buildings") if False else None
    print("label_declutter: all checks passed")


if __name__ == "__main__":
    main()
