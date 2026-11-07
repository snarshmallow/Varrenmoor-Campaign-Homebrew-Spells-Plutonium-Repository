"""Checks for label_style.py wrapping / halo / knock-out (run: python illustrator/generators/test_label_style.py)."""
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import label_offset as L  # noqa: E402
import label_style as S  # noqa: E402
from shapely.geometry import LineString, Polygon  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def main():
    cfg = S.merge({})
    d = S.resolve(cfg, "districts")
    # defaults: halo on for area labels, elevation has no halo but cuts its contour
    assert S.resolve(cfg, "buildings").mode == "halo" and S.resolve(cfg, "rooms").mode == "halo" and d.mode == "halo"
    assert S.resolve(cfg, "elevation").mode == "none" and S.resolve(cfg, "elevation").knock
    assert not S.resolve(cfg, "buildings").knock, "knock-out is opt-in for area labels"
    assert S.apply_case("Court Square", d, auto_upper=True) == "COURT SQUARE" and S.apply_case("a b", S.resolve(cfg, "rooms")) == "a b"
    assert S.apply_case("tax and permit office", S.resolve(S.merge({"default": {"case": "title"}}), "rooms")) == "Tax and Permit Office"

    # wrapping: balanced, word boundaries only, max lines, widths
    st = S.resolve(S.merge({"default": {"wrap": "width", "wrap_width": 60, "wrap_unit": "pt", "max_lines": 3}}), "buildings")
    lays, off = S.build_layouts("Tax and Permit Office", st, 7, 1.0)
    lay = lays[0]
    assert len(lay.lines) >= 2 and " ".join(lay.lines) == "Tax and Permit Office", lay.lines
    wf = lambda s: S.measure(s, 7, st)
    assert max(wf(x) for x in lay.lines) <= 60 + 0.5, "lines fit the max width"
    assert abs(wf(lay.lines[0]) - wf(lay.lines[-1])) < 0.6 * max(wf(x) for x in lay.lines), "balanced, not greedy-ragged"
    st2 = S.resolve(S.merge({"default": {"wrap": "width", "wrap_width": 10, "max_lines": 2}}), "buildings")
    l2 = S.build_layouts("Tax and Permit Office", st2, 7, 1.0)[0][0]
    assert len(l2.lines) == 2, "max_lines wins over a too-narrow width"
    l3 = S.build_layouts("Extraordinarily long", S.resolve(S.merge({"default": {"wrap": "width", "wrap_width": 5}}), "rooms"), 7, 1.0)[0][0]
    assert l3.lines == ["Extraordinarily", "long"], "no hyphenation: long words stay whole"
    # feet width
    stf = S.resolve(S.merge({"default": {"wrap": "width", "wrap_width": 10, "wrap_unit": "ft", "max_lines": 4}}), "districts")
    lf = S.build_layouts("Tax and Permit Office", stf, 7, 2.0)[0][0]    # 10 ft at 2 pt/ft = 20 pt
    assert len(lf.lines) >= 3
    # off: one line
    assert len(S.build_layouts("Tax and Permit Office", S.resolve(S.merge({"default": {"wrap": "off"}}), "rooms"), 7, 1)[0][0].lines) == 1
    # auto candidates grow in line count, the offset layout is the one-liner
    au = S.resolve(cfg, "buildings")
    alays, aoff = S.build_layouts("Tax and Permit Office", au, 7, 1.0)
    assert len(alays[0].lines) == 1 and len(alays) == 2 and len(aoff.lines) == 1   # buildings max_lines 2
    assert alays[1].w < alays[0].w and alays[1].h > alays[0].h

    # integration with the placer: wrapped label fits where the one-liner does not (no leader)
    P = L.LabelParams()
    sh = rect(100, 100, 52, 40)
    p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("s", sh)])
    p.add("s", sh, "Tax and Permit Office", 7, layouts=alays, offset_layout=aoff)
    r = p.solve()[0]
    assert r.leader is None and len(r.lines) == 2, (r.leader, r.lines)
    p = L.Placer(P, frame=(0, 0, 600, 400), shapes=[("s", sh)])
    p.add("s", sh, "Tax and Permit Office", 7)
    r1 = p.solve()[0]
    assert r1.leader is not None, "the one-liner needs a leader in the same shape"
    # block geometry of a wrapped label stays inside the shape
    assert Polygon(sh).contains(L.text_box(r.cx, r.cy, r.w, r.h))

    # knock-out geometry and cutting
    stm = S.resolve(S.merge({"default": {"mode": "mask", "knockout_pad": 3}}), "buildings")
    rec = S.Rec("lbl_x", "Labels - Buildings", ["Hall"], 100, 100, 20, 8, None, 7, stm)
    kg = S.knock_geom(rec)
    assert kg.contains(L.text_box(100, 100, 20, 8)) and abs(kg.bounds[0] - (90 - 3)) < 0.01
    assert kg.area < L.text_box(100, 100, 26, 14).area, "rounded corners"
    import render_world as R
    d_, changed = R.cut_d([[(0, 100), (200, 100)]], kg, closed=False)
    assert changed and d_.count("M") == 2, d_
    d2, ch2 = R.cut_d([[(0, 150), (200, 150)]], kg, closed=False)
    assert not ch2 and d2.count("M") == 1
    import contours as ct
    cs = ct.ContourSet()
    cs.pieces = [{"id": "contour_650_1", "elev": 650.0, "index": False, "datum": False, "pts": [(0, 100), (200, 100)], "closed": False}]
    assert ct.cut_pieces(cs, kg) == 1 and len(cs.pieces) == 2 and cs.pieces[0]["id"] == "contour_650_1" and cs.pieces[1]["id"] == "contour_650_2"
    assert all(not LineString(pc["pts"]).intersects(kg) or LineString(pc["pts"]).intersection(kg).length < 1e-6 for pc in cs.pieces)

    # svg: tspans for wrapped text, halo copy, box, auto-contrast
    sth = S.resolve(S.merge({"default": {"mode": "halo", "align": "left"}}), "buildings")
    t = R.LayerTree([("LABELS", ["Labels - Buildings", S.LAYER_BACKING])])
    rec2 = S.Rec("lbl_b1", "Labels - Buildings", ["Tax and", "Permit Office"], 100, 100, 50, 18.3, 20, 7, sth)
    S.emit(t, rec2, S.LAYER_BACKING)
    assert len(t.items["Label Backing"]) == 1 and "lbl_b1_halo" in t.items["Label Backing"][0]
    el = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{t.items["Labels - Buildings"][0]}</svg>')[0]
    assert [x.text for x in el.iter(NS + "tspan")] == ["Tax and", "Permit Office"] and el.get("text-anchor") == "start"
    assert "rotate(20.00 100.00 100.00)" in el.get("transform")
    stb = S.resolve(S.merge({"default": {"mode": "box", "box_color": "#000000", "auto_contrast": True, "box_pad": 3, "box_radius": 4, "box_opacity": 0.5}}), "rooms")
    assert S.text_color(stb) == "#f7f4ea" and S.text_color(S.resolve(S.merge({"default": {"mode": "box", "auto_contrast": True}}), "rooms")) == "#1a1a1a"
    t.add("Label Backing", "")
    S.emit(t, S.Rec("lbl_r", "Labels - Buildings", ["Cellar"], 50, 50, 20, 7.7, None, 7, stb), None)
    assert any('id="lbl_r_box"' in i and 'rx="4.00"' in i and "fill-opacity:0.50" in i for i in t.items["Labels - Buildings"]), "box goes in the label layer when backing_layer is off"

    # cli parsing (base64 as sent by the panel)
    import base64
    js = base64.b64encode(json.dumps({"default": {"mode": "box"}, "mask_targets": ["grid"]}).encode()).decode()
    c2 = S.merge(S.decode_b64(js))
    assert c2["default"]["mode"] == "box" and c2["mask_targets"] == ["grid"] and c2["default"]["font"] == "Arial"

    # full render: default has halo copies in Label Backing; mask mode cuts the Roads/Buildings paths; wrapped label uses tspans
    model = R.load_place("bridgehollow")
    tmp = tempfile.mkdtemp()

    def render(name, ls, scale=40):
        out = os.path.join(tmp, name + ".svg")
        R.render(model, "town", out, None, {"scale": scale}, {"enabled": True}, ls)
        root = ET.parse(out).getroot()
        return {g.get("id"): g for g in root.iter(NS + "g") if g.get("id")}, out

    g, _ = render("a", None)
    back = list(g["Label Backing"])
    assert back and all(e.get("id").endswith("_halo") for e in back), "default: halo copies in the backing sublayer"
    gw, _ = render("w", {"default": {"wrap": "width", "wrap_width": 25, "wrap_unit": "pt"}})
    assert any(len(list(e.iter(NS + "tspan"))) > 1 for e in list(gw["Labels - Buildings"]) + list(gw["Labels - Districts"])), "wrapped labels use tspans"
    g2, _ = render("b", {"default": {"mode": "none"}, "elevation": {"mode": "none"}})
    assert len(list(g2["Label Backing"])) == 0
    g3, _ = render("c", {"default": {"mode": "box"}, "backing_layer": False})
    assert len(list(g3["Label Backing"])) == 0 and any(e.get("id", "").endswith("_box") for e in g3["Labels - Buildings"])
    g4, _ = render("d", {"default": {"mode": "mask", "knockout_pad": 6}, "mask_targets": ["streets", "buildings", "grid"]})
    assert len(list(g4["Label Backing"])) == 0
    n_open = lambda gg: sum(1 for e in gg["Roads"] if (e.get("d") or "").count("Z") < (e.get("d") or "").count("M"))
    assert n_open(g4) > n_open(g), "mask mode cuts road outlines under labels"
    print("label_style: all checks passed")


if __name__ == "__main__":
    main()
