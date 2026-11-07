"""Checks for label_offset.py (run: python illustrator/generators/test_label_offset.py)."""
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import label_offset as L  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

FRAME = (0, 0, 600, 400)


def rect(x, y, w, h):
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]


def solve(params, items, shapes=()):
    p = L.Placer(params, frame=FRAME, shapes=shapes)
    for it in items:
        p.add(*it[:4], **(it[4] if len(it) > 4 else {}))
    return {r.id: r for r in p.solve()}


def main():
    P = L.LabelParams()
    big, small = rect(100, 100, 200, 120), rect(400, 200, 12, 9)
    res = solve(P, [("big", big, "Big Hall", 7), ("small", small, "Tiny Shed", 7)], [("big", big), ("small", small)])
    assert res["big"].leader is None and res["big"].anchor == "middle", "large shape keeps its label inside"
    sm = res["small"]
    assert sm.leader and sm.offset, "small shape gets a leader"
    w, h = L.text_size("Tiny Shed", 7)
    tb = L.text_box(sm.x + (w / 2 if sm.anchor == "start" else -w / 2), sm.y - 7 * 0.35, w, h)
    assert not tb.intersects(Polygon(small)), "offset text is outside the shape"
    assert Polygon(small).contains(L.Point(sm.leader[0])), "leader starts inside the shape"
    assert sm.dot == sm.leader[0]
    assert sm.leader[-1][1] == sm.leader[-2][1], "elbow ends in a horizontal shelf"
    assert FRAME[0] <= tb.bounds[0] and tb.bounds[2] <= FRAME[2], "stays on the page"
    # up-right preferred: the shelf end is right of and above the anchor
    assert sm.leader[1][0] > sm.leader[0][0] and sm.leader[1][1] < sm.leader[0][1]

    st = solve(L.LabelParams.from_dict({"style": "straight", "dot": False}), [("small", small, "Tiny Shed", 7)])["small"]
    assert len(st.leader) == 2 and st.dot is None, "straight style = one segment, no dot"

    off = solve(L.LabelParams.from_dict({"enabled": False}), [("small", small, "Tiny Shed", 7)])["small"]
    assert off.leader is None, "disabled: label stays put"

    # neighbours: two tiny shapes side by side must not get overlapping labels or crossing leaders
    a, b = rect(400, 200, 8, 8), rect(412, 200, 8, 8)
    r2 = solve(P, [("a", a, "Alpha House", 7), ("b", b, "Beta House", 7)], [("a", a), ("b", b)])
    boxes = []
    for r, t in ((r2["a"], "Alpha House"), (r2["b"], "Beta House")):
        w, h = L.text_size(t, 7)
        boxes.append(L.text_box(r.x + (w / 2 if r.anchor == "start" else -w / 2), r.y - 2.45, w, h))
    assert not boxes[0].intersects(boxes[1]), "labels do not overlap"
    assert not L.LineString(r2["a"].leader).crosses(L.LineString(r2["b"].leader)), "leaders do not cross"

    # a plaza label inside a district whose label sits at the same point: they must not overlap
    dist, plaza = rect(100, 100, 300, 200), rect(200, 160, 80, 80)
    r3 = solve(P, [("dist", dist, "AUTHORITY WARD", 9, {"bold": True, "point": (240, 200)}),
                   ("plaza", plaza, "Court Square", 7, {"bold": True, "point": (240, 200)})], [("plaza", plaza)])
    b3 = []
    for k, t_, sz in (("dist", "AUTHORITY WARD", 9), ("plaza", "Court Square", 7)):
        r, (w, h) = r3[k], L.text_size(t_, sz, True)
        dx = {"middle": 0, "start": w / 2, "end": -w / 2}[r.anchor]
        b3.append(L.text_box(r.x + dx, r.y - sz * 0.35, w, h))
    assert not b3[0].intersects(b3[1]), "plaza and district labels do not overlap"

    # offset text avoids a neighbouring shape's outline when there is free space
    tiny, nb = rect(300, 200, 8, 8), rect(312, 190, 40, 30)
    r4 = solve(P, [("tiny", tiny, "Tiny Shed", 7)], [("tiny", tiny), ("nb", nb)])["tiny"]
    w, h = L.text_size("Tiny Shed", 7)
    t4 = L.text_box(r4.x + (w / 2 if r4.anchor == "start" else -w / 2), r4.y - 2.45, w, h)
    assert not t4.intersects(Polygon(nb)), "offset text does not cross a neighbour"
    assert not L.LineString(r4.leader).intersects(Polygon(nb)), "leader does not cross a neighbour"

    # svg ids
    svg = "".join(L.leader_svg(sm, 0.4))
    root = ET.fromstring(f'<svg xmlns="http://www.w3.org/2000/svg">{svg}</svg>')
    ids = [e.get("id") for e in root]
    assert ids == ["small_leader", "small_leader_dot"], ids

    # full render: Leaders sublayer inside LABELS
    import render_world as R
    model = R.load_place("bridgehollow")
    out = os.path.join(tempfile.mkdtemp(), "t.svg")
    R.render(model, "town", out, None, {"scale": 40}, {"enabled": True})
    tree = ET.parse(out).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    labels = next(g for g in tree.iter(ns + "g") if g.get("id") == "LABELS")
    leaders = next(g for g in labels if g.get("id") == "Leaders")
    n = [e.get("id") for e in leaders if e.tag == ns + "path"]
    assert n and all(i.endswith("_leader") for i in n), n
    out2 = os.path.join(os.path.dirname(out), "t2.svg")
    R.render(model, "town", out2, None, {"scale": 40}, {"enabled": False})
    t2 = ET.parse(out2).getroot()
    l2 = next(g for g in next(g for g in t2.iter(ns + "g") if g.get("id") == "LABELS") if g.get("id") == "Leaders")
    assert len(list(l2)) == 0, "no leaders when disabled"
    print("label_offset: all checks passed")


if __name__ == "__main__":
    main()
