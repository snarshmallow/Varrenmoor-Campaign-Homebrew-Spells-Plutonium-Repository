"""Label placement with offset + leader lines for objects too small to hold their label.

All geometry here is in page points (y down), the same space the SVG is written in.

  p = LabelParams()                         # see defaults below; viewcfg.label_offset() merges view_settings + CLI
  pl = Placer(p, obstacles=[box, ...], shapes=[(id, polygon_pts), ...])
  pl.add(id, poly_pts, text, size, bold=False, rot=None, point=None)     # queue a closed-shape label
  pl.add_fixed_box(box)                     # street / contour labels already placed: only avoided
  for r in pl.solve(): ...                  # -> Result(id, x, y, anchor, rot, leader=[pts]|None, dot=(x,y)|None)

Fit test: the text rectangle (estimated width/height at the font size, rotated) grown by `margin_pct` must lie inside the
polygon at the label point or at the pole of inaccessibility. Otherwise the text is moved outside: candidates in 8
directions (up-right preferred) at growing distance, rejecting boxes that hit the shape, other labels, or the leader of
another label; shapes of other objects are avoided when possible. The leader runs from the anchor (inside the shape) to the
text: one straight segment, or an elbow (diagonal, then a short horizontal shelf).
"""
import math
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel
from shapely.strtree import STRtree

DEFAULTS = {"enabled": True, "style": "elbow", "stroke_width": 0.4, "margin_pct": 10.0, "max_offset_pt": 90.0, "dot": True}

# direction preference, y down: up-right first
DIRS = [(1, -1), (1, 0), (0, -1), (1, 1), (-1, -1), (-1, 0), (0, 1), (-1, 1)]


@dataclass
class LabelParams:
    enabled: bool = True
    style: str = "elbow"          # "straight" | "elbow"
    stroke_width: float = 0.4     # pt
    margin_pct: float = 10.0      # text must fit with this much spare (percent of text size) to stay inside
    max_offset_pt: float = 90.0   # how far outside the shape (page pt) the text may be moved
    dot: bool = True              # small dot at the anchor

    @classmethod
    def from_dict(cls, d):
        d = {**DEFAULTS, **{k: v for k, v in (d or {}).items() if v is not None}}
        return cls(bool(d["enabled"]), "straight" if d["style"] == "straight" else "elbow", float(d["stroke_width"]),
                   max(float(d["margin_pct"]), 0.0), max(float(d["max_offset_pt"]), 0.0), bool(d["dot"]))


def text_size(s, size, bold=False):
    """Estimated (width, height) in pt of an Arial string; height is the cap/ascender box."""
    w = 0.0
    for ch in s:
        w += 0.28 if ch == " " else 0.70 if ch.isupper() else 0.55 if ch.isdigit() else 0.34 if ch in "ilIjt.,'*!|" else 0.52
    return w * size * (1.12 if bold else 1.05) + 0.5, size * 1.1


def text_box(cx, cy, w, h, rot=None):
    b = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    return affinity.rotate(b, rot, origin=(cx, cy)) if rot else b


@dataclass
class Layout:
    """One way to set a label's text: wrapped lines and the size of the text block (page pt)."""
    lines: list
    w: float
    h: float


@dataclass
class Result:
    id: str
    x: float                      # text anchor position (baseline centre of the text box, see anchor)
    y: float
    anchor: str                   # svg text-anchor
    rot: float = None
    leader: list = None           # polyline pts in page pt, from anchor point to the text
    dot: tuple = None
    offset: bool = False
    cx: float = 0.0               # centre of the text block
    cy: float = 0.0
    w: float = 0.0
    h: float = 0.0
    lines: list = None


@dataclass
class _Item:
    id: str
    poly: Polygon
    text: str
    size: float
    bold: bool
    rot: float
    point: tuple
    w: float = 0.0
    h: float = 0.0
    layouts: list = None          # layouts tried (in order) to fit inside the shape
    offset_layout: Layout = None  # layout used when the text moves outside
    lines: list = None

    def use(self, lay):
        self.w, self.h, self.lines = lay.w, lay.h, lay.lines


class Placer:
    def __init__(self, params, frame=None, shapes=()):
        """frame: (x0, y0, x1, y1) page pt box the text must stay in. shapes: [(id, pts)] closed objects to avoid (ids containing '#' are soft: text avoids them, leaders may cross)."""
        self.p = params
        self.frame = box(*frame) if frame else None
        self.items = []
        self.fixed = []
        self.shapes = [(i, Polygon(p).buffer(0)) for i, p in shapes if len(p) >= 3]
        self._tree = STRtree([g for _, g in self.shapes]) if self.shapes else None

    def add(self, id_, poly_pts, text, size, bold=False, rot=None, point=None, layouts=None, offset_layout=None):
        """layouts: [Layout, ...] wrapped variants tried in order for fitting inside (default: the one-line text);
        offset_layout: the one used when the text has to move outside (default: layouts[0])."""
        if len(poly_pts) < 3:
            return
        pg = Polygon(poly_pts).buffer(0)
        if pg.is_empty or pg.geom_type not in ("Polygon", "MultiPolygon"):
            return
        if pg.geom_type == "MultiPolygon":
            pg = max(pg.geoms, key=lambda g: g.area)
        w, h = text_size(text, size, bold)
        lays = layouts or [Layout([text], w, h)]
        it = _Item(id_, pg, text, size, bold, rot, tuple(point) if point else None, w, h, lays, offset_layout or lays[0])
        it.use(lays[0])
        self.items.append(it)

    def add_fixed_box(self, b):
        self.fixed.append(b)

    # -------------------------------------------------------------- fit
    def _fits(self, it, c):
        k = 1.0 + self.p.margin_pct / 100.0
        return it.poly.contains(text_box(c[0], c[1], it.w * k, it.h * k, it.rot))

    def _collides(self, it, c, placed):
        b = text_box(c[0], c[1], it.w, it.h, it.rot)
        b = b.buffer(1.5, join_style=2)
        return any(b.intersects(o) for o in placed)

    def _shifted(self, it, c0, placed):
        x0, y0, x1, y1 = it.poly.bounds
        n = 9
        pts = [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]
        pts.sort(key=lambda q: math.hypot(q[0] - c0[0], q[1] - c0[1]))
        return next((q for q in pts if self._fits(it, q) and not self._collides(it, q, placed)), None)

    def _free_point(self, it, cands, placed):
        """Leader anchor: a point inside the shape that no placed label sits on (nearest to the label point)."""
        free = lambda q: not any(o.contains(Point(q)) or o.distance(Point(q)) < 1.0 for o in placed)
        for c in cands:
            if free(c):
                return c
        x0, y0, x1, y1 = it.poly.bounds
        n = 9
        pts = [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]
        pts = [q for q in pts if it.poly.contains(Point(q))]
        pts.sort(key=lambda q: math.hypot(q[0] - cands[0][0], q[1] - cands[0][1]))
        return next((q for q in pts if free(q)), cands[0])

    def _inside_candidates(self, it):
        cs = []
        if it.point and it.poly.contains(Point(it.point)):
            cs.append(it.point)
        try:
            pl = polylabel(it.poly, tolerance=0.2)
            cs.append((pl.x, pl.y))
        except Exception:
            pass
        rp = it.poly.representative_point()
        cs.append((rp.x, rp.y))
        return cs

    # -------------------------------------------------------------- solve
    def solve(self):
        results, placed = [], list(self.fixed)
        todo = []
        for it in self.items:
            cands = self._inside_candidates(it)
            hit = None
            for lay in it.layouts:
                it.use(lay)
                if self.p.enabled:
                    hit = next((c for c in cands if self._fits(it, c) and not self._collides(it, c, placed)), None)
                    if hit is None and any(self._fits(it, c) for c in cands):
                        hit = self._shifted(it, cands[0], placed)       # fits, but another label sits on it: slide within the shape
                else:
                    hit = next((c for c in cands if self._fits(it, c)), None)
                if hit is not None:
                    break
            if hit is None:
                it.use(it.offset_layout)
                if not self.p.enabled:
                    hit = cands[0]
            if hit is not None:
                b = text_box(hit[0], hit[1], it.w, it.h, it.rot)
                placed.append(b)
                results.append(Result(it.id, hit[0], hit[1] + it.size * 0.35, "middle", it.rot, cx=hit[0], cy=hit[1], w=it.w, h=it.h, lines=it.lines))
            else:
                todo.append((it, cands))
        leaders = []
        # smallest shapes first: they have the least room
        for it, cands in sorted(todo, key=lambda t: t[0].poly.area):
            r = self._offset(it, self._free_point(it, cands, placed), placed, leaders)
            if r is None:                     # nowhere to put it: leave it centred (overflowing)
                c = cands[0]
                placed.append(text_box(c[0], c[1], it.w, it.h, it.rot))
                r = Result(it.id, c[0], c[1] + it.size * 0.35, "middle", it.rot, cx=c[0], cy=c[1], w=it.w, h=it.h, lines=it.lines)
            results.append(r)
        return results

    def _others_hit(self, it, g, skip_soft=False):
        if not self._tree:
            return False
        for i in self._tree.query(g):
            sid, sg = self.shapes[int(i)]
            if sid != it.id and not (skip_soft and "#" in sid) and sg.intersects(g):
                return True
        return False

    def _offset(self, it, anchor, placed, leaders):
        p = self.p
        pad = 1.5
        gap = 2.0
        shelf = 7.0 if p.style == "elbow" else 0.0
        far = it.poly.bounds
        ray_len = 2 * (max(far[2] - far[0], far[3] - far[1]) + p.max_offset_pt + 50)
        exits = []
        for dx, dy in DIRS:
            n = math.hypot(dx, dy)
            u = (dx / n, dy / n)
            inter = LineString([anchor, (anchor[0] + u[0] * ray_len, anchor[1] + u[1] * ray_len)]).intersection(it.poly)
            re_ = 0.0 if inter.is_empty else max(math.hypot(x - anchor[0], y - anchor[1]) for x, y in _coords(inter))
            exits.append((u, re_))
        nsteps = int(p.max_offset_pt / 2.5) + 1
        for strict in (3, 2, 1, 0):
            for i in range(nsteps):
                for u, r_exit in exits:
                    r = r_exit + 3.0 + i * 2.5
                    k = (anchor[0] + u[0] * r, anchor[1] + u[1] * r)
                    res = self._try(it, anchor, k, u[0], shelf, gap, pad, placed, leaders, strict)
                    if res is not None:
                        placed.append(res[1])
                        leaders.append(res[2])
                        return res[0]
        return None

    def _try(self, it, anchor, k, ux, shelf, gap, pad, placed, leaders, strict):
        side = 1 if ux >= -0.01 else -1          # text to the right of the knee unless the direction points left
        sx = k[0] + side * shelf                 # end of the shelf
        tx0 = sx + side * gap
        cx = tx0 + side * it.w / 2
        cy = k[1]
        tb = text_box(cx, cy, it.w, it.h)
        tb_pad = tb.buffer(pad, join_style=2)
        if self.frame is not None and not self.frame.contains(tb):
            return None
        if tb_pad.intersects(it.poly):
            return None
        if any(tb_pad.intersects(o) for o in placed) or any(tb_pad.intersects(o) for o in leaders):
            return None
        pts = [anchor, k] + ([(sx, k[1])] if shelf else [])
        ln = LineString(pts)
        if any(ln.intersects(o) for o in placed):
            return None
        if any(ln.crosses(o) for o in leaders):
            return None
        if strict and self._others_hit(it, tb_pad, skip_soft=strict < 3):
            return None
        if strict >= 2 and self._others_hit(it, ln, skip_soft=True):
            return None
        # keep the leader inside the frame too
        if self.frame is not None and not self.frame.contains(ln):
            return None
        anc = "start" if side > 0 else "end"
        r = Result(it.id, tx0, cy + it.size * 0.35, anc, None, pts, anchor if self.p.dot else None, True, cx, cy, it.w, it.h, it.lines)
        return r, tb, ln


def _coords(g):
    if g.geom_type in ("Point",):
        return [(g.x, g.y)]
    if hasattr(g, "geoms"):
        out = []
        for s in g.geoms:
            out += _coords(s)
        return out
    return list(g.coords)


def leader_svg(res, stroke_width, dot_r=None):
    """-> list of svg strings for the Leaders layer."""
    out = []
    if not res.leader:
        return out
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in res.leader)
    out.append(f'<path id="{res.id}_leader" class="leader" fill="none" stroke="#000000" stroke-width="{stroke_width:g}" d="{d}"/>')
    if res.dot:
        r = dot_r or max(stroke_width * 1.6, 0.8)
        out.append(f'<circle id="{res.id}_leader_dot" class="leader-dot" cx="{res.dot[0]:.2f}" cy="{res.dot[1]:.2f}" r="{r:.2f}" '
                   f'fill="#000000" stroke="none"/>')
    return out
