"""svg_sanity.py (Illustrator safety check) and label_guard.py (NaN, off-page, duplicates, curved baselines, label budget).
Run: python illustrator/generators/test_svg_sanity.py      (a second or two, no renders)
"""
import json
import math
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import svg_sanity as S  # noqa: E402
import label_guard as G  # noqa: E402
import label_style as LS  # noqa: E402

HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
        'xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/" xmlns:xlink="http://www.w3.org/1999/xlink" width="1224pt" height="792pt" viewBox="0 0 1224 792">')


def layer(name, body):
    return f'<g id="{name}" inkscape:groupmode="layer" i:layer="yes" inkscape:label="{name}">{body}</g>'


def labels_svg(backing_first=True, halo_after=False, extra=""):
    halo = '<text id="a_x5F_label_x5F_halo" x="100" y="100" font-size="9" style="fill:#fff;stroke:#fff;stroke-width:3">Alpha</text>'
    txt = '<text id="a_x5F_label" x="100" y="100" font-size="9" style="fill:#111">Alpha</text>'
    bk = layer("Label Backing", halo if not halo_after else "")
    tl = layer("Labels - Buildings", (txt + halo) if halo_after else txt)
    inner = (bk + tl) if backing_first else (tl + bk)
    return HEAD + layer("LINES", '<path id="p1" d="M10,10 L200,200 L300,50"/>') + layer("LABELS", inner) + extra + "</svg>"


def test_good():
    r = S.check(labels_svg())
    assert r["ok"] and not r["errors"], r["errors"]
    assert r["layers"]["Label Backing"]["text"] == 1 and r["layers"]["Labels - Buildings"]["text"] == 1
    assert r["totals"]["halo"] == 1 and r["totals"]["points_max"] == 3 and r["fonts"] == []
    assert "OK" in S.summary(r)
    print("ok good svg")


def test_bad():
    bad = {
        "invalid xml": HEAD + "<g><text>x</g></svg>",
        "NaN": labels_svg(extra='<path id="n" d="M10,10 Lnan,20"/>'),
        "far": labels_svg(extra='<text id="far" x="1e9" y="10" font-size="9">far</text>'),
        "dup id": labels_svg(extra='<path id="p1" d="M1,1 L2,2"/>'),
        "textPath": labels_svg(extra='<path id="tp" d="M1,1 L50,50"/><text id="c" font-size="9"><textPath href="#tp">curved</textPath></text>'),
        "font size": labels_svg(extra='<text id="z" x="5" y="5" font-size="0">zero</text>'),
        "backing above text": labels_svg(backing_first=False),
        "halo after text": labels_svg(halo_after=True),
        "clip nest": labels_svg(extra='<g clip-path="url(#a)"><g clip-path="url(#b)"><g mask="url(#c)"><g clip-path="url(#d)"><path d="M1,1 L2,2"/></g></g></g></g>'),
    }
    for why, svg in bad.items():
        r = S.check(svg)
        assert not r["ok"] and r["errors"], (why, r["warnings"])
    big = HEAD + layer("LABELS", layer("Labels - Buildings", "".join(f'<text id="t{i}" x="10" y="10" font-size="5">x</text>' for i in range(3100)))) + "</svg>"
    r = S.check(big)
    assert not r["ok"] and any("text elements" in e for e in r["errors"]), r["errors"]
    pts = " L".join(f"{i % 1000}.5,{(i * 7) % 700}.25" for i in range(70000))
    r = S.check(HEAD + f'<path id="huge" d="M0,0 L{pts}"/></svg>')
    assert any("points" in e for e in r["errors"]), r["errors"]
    r = S.check(labels_svg(extra='<path id="off" d="M-3000,10 L20,20"/>'))
    assert r["ok"] and any("outside" in w for w in r["warnings"]), "a page outside is a warning only"
    # curved.json next to the SVG: NaN / too many points
    d = tempfile.mkdtemp()
    p = os.path.join(d, "x.svg")
    open(p, "w", encoding="utf-8").write(labels_svg())
    json.dump({"items": [{"id": "s", "points": [[0, 0], [float("nan"), 1]]}, {"id": "t", "points": [[i, i] for i in range(500)]}]}, open(p + ".curved.json", "w"))
    r = S.check(p)
    assert not r["ok"] and len([e for e in r["errors"] if "curved label" in e]) == 2, r["errors"]
    assert S.main([p]) == 1
    print("ok bad svgs: invalid xml, NaN, 1e9, duplicate id, textPath, font size 0, backing above text, halo after text, clip nesting, 3100 texts, 70k-point path, curved.json")


def rec(i, layer="Labels - Buildings", cx=100.0, cy=100.0, text=None, path="", size=8.0):
    return LS.Rec(f"r{i}_label", layer, [text if text is not None else f"Name {i}"], cx, cy, 40.0, 9.0, 0.0, size, LS.resolve({}, "buildings"), path=path)


def test_guard():
    W, H = 1224.0, 792.0
    rs = [rec(0), rec(1, cx=float("nan")), rec(2, cx=1e9), rec(3, cy=-5), rec(4, text=" "), rec(5, size=0.0), rec(0, cx=300.0),
          rec(6, cx=100.0004, text="Name 0")]
    out, rep = G.guard(rs, W, H)
    assert [r.id for r in out] == ["r0_label"], [r.id for r in out]
    assert rep["dropped"] == {"NaN / inf": 1, "off the page": 2, "empty text": 1, "font size": 1, "duplicate id": 1, "duplicate label": 1}, rep["dropped"]
    # rounding
    out, _ = G.guard([rec(9, cx=100.123456, cy=50.987654)], W, H)
    assert out[0].cx == 100.12 and out[0].cy == 50.99
    # curved baseline: simplified to <= 40 points, a broken one is set straight
    pts = [(100 + i * 0.5, 300 + 40 * math.sin(i / 30.0)) for i in range(800)]
    out, rep = G.guard([rec(10, path=G.points_path(pts)), rec(11, path="M10,10 Lnan,5"), rec(12, path="M10,10 L1e9,5")], W, H)
    n = len(G.path_points(out[0].path))
    assert 2 <= n <= G.MAX_CURVE_POINTS and rep["simplified"] == 1, n
    assert out[1].path == "" and out[2].path == "" and rep["straightened"] == 2
    sp = G.simplify(pts, 40)
    assert sp[0] == pts[0] and sp[-1] == pts[-1] and len(sp) <= 40
    # budget: hidden / elevation go first, districts last
    rs = ([rec(f"d{i}", "Labels - Districts") for i in range(10)] + [rec(f"b{i}", "Labels - Buildings") for i in range(300)]
          + [rec(f"e{i}", "Labels - Elevation") for i in range(200)] + [rec(f"h{i}", "Labels - Hidden") for i in range(400)])
    rs = [LS.Rec(r.id, r.layer, [r.id], 50 + (k % 1000), 50 + (k // 1000) * 20, r.w, r.h, r.rot, r.size, r.st) for k, r in enumerate(rs)]
    out, rep = G.guard(rs, W, H, budget=300)
    cnt = {}
    for r in out:
        cnt[r.layer] = cnt.get(r.layer, 0) + 1
    assert len(out) == 300 and cnt.get("Labels - Districts") == 10 and cnt.get("Labels - Buildings") == 290 and "Labels - Hidden" not in cnt, cnt
    assert rep["cut"]["Labels - Hidden"] == 400 and any("label budget" in w for w in G.warnings(rep))
    out, rep = G.guard(rs, W, H, budget=0)          # no budget: only the hidden cap
    assert len(out) == 510 + G.HIDDEN_CAP and rep["cut"] == {"Labels - Hidden": 400 - G.HIDDEN_CAP}, rep["cut"]
    out, rep = G.guard([], W, H)
    assert out == [] and rep["kept"] == 0
    print("ok label guard: NaN / off-page / empty / font size / duplicates dropped, 0.01 pt rounding, curved baselines <= 40 pts, budget order, empty input")


def test_style_sanitised():
    st = LS.resolve({"default": {"halo_width": float("nan"), "halo_opacity": float("inf"), "size": float("nan")}, "buildings": {}}, "buildings")
    assert st.halo_width == LS.Style.halo_width and st.halo_opacity == LS.Style.halo_opacity and st.size is None, st
    st = LS.resolve({"default": {"halo_width": 60}}, "buildings")
    assert st.halo_width == LS.HALO_MAX
    print("ok label_style: NaN / inf / absurd halo values fall back or clamp")


if __name__ == "__main__":
    test_good()
    test_bad()
    test_guard()
    test_style_sanitised()
    print("svg_sanity: all checks passed")
