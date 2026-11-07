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

Declutter extensions (all optional; with defaults the behaviour is the original first-fit placement):
  pl.set_features({"building": [(id, geom)], "plaza": .., "road": .., "water": ..}, junctions=[(x, y)], weights={...})
      -> candidate positions are SCORED by how much of the text box covers map features (and road junctions); the cheapest wins.
         Area labels (districts, plazas: score_inside=True) slide to the emptiest spot inside their shape or move outside with a leader.
  pl.add(..., priority=n, on_fail="hide"|"number"|"keep", score_inside=True, max_cover=0.4, override={"cx", "cy", "anchor"}, number=True)
      -> placed tier by tier (low priority number first); a label that finds no free spot is hidden / numbered; overrides are pinned.
  pl.add_line(id, [(cx, cy, rot), ...], w, h, text, size, priority=n)    # street names: best free candidate position
  route_leader(anchor, (l, t, r, b), style, shelf, gap)                   # leader from a FIXED anchor to a label box (also used by the panel)
  leader_svg(res, params) -> [(layer, svg)]: <id>_leader_casing, <id>_leader (Leaders), <id>_leader_dot (Leader Anchors)
"""
import math
from dataclasses import dataclass, field

from shapely import affinity
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polylabel
from shapely.strtree import STRtree

DEFAULTS = {"enabled": True, "style": "elbow", "stroke_width": 0.8, "margin_pct": 10.0, "max_offset_pt": 90.0, "dot": True,
            "color": "#ffffff", "casing": True, "casing_color": "#1a1a1a", "casing_width": 1.7, "dot_ring": True, "dot_radius": 1.6,
            "match_text": False, "dash": "", "shelf": 7.0, "gap": 2.0}

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
    color: str = "#ffffff"        # leader colour (white so it reads over streets and dark fills; the casing makes it read on light fills)
    casing: bool = True           # dark path (named <id>_leader_casing) drawn under the leader
    casing_color: str = "#1a1a1a"
    casing_width: float = 1.7     # total width of the casing stroke (pt); wider than stroke_width
    dot_ring: bool = True         # anchor dot gets a dark ring
    dot_radius: float = 1.6
    match_text: bool = False      # leader colour = the label's text colour instead
    dash: str = ""                # svg dasharray, e.g. "1 1.6" (dotted: quiet mode)
    shelf: float = 7.0            # elbow shelf length (pt)
    gap: float = 2.0              # space between the leader end and the text (pt)

    @classmethod
    def from_dict(cls, d):
        d = {**DEFAULTS, **{k: v for k, v in (d or {}).items() if v is not None}}
        return cls(bool(d["enabled"]), "straight" if d["style"] == "straight" else "elbow", float(d["stroke_width"]),
                   max(float(d["margin_pct"]), 0.0), max(float(d["max_offset_pt"]), 0.0), bool(d["dot"]),
                   str(d["color"]), bool(d["casing"]), str(d["casing_color"]), max(float(d["casing_width"]), 0.0), bool(d["dot_ring"]),
                   max(float(d["dot_radius"]), 0.3), bool(d["match_text"]), str(d["dash"] or ""), max(float(d["shelf"]), 0.0),
                   max(float(d["gap"]), 0.0))


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
    status: str = "placed"        # placed | hidden (no free spot) | numbered (marker + legend entry)
    marker: tuple = None          # numbered: centre of the marker
    pinned: bool = False          # placed from label_overrides.json
    layout_i: int = 0             # which offset layout was used (>0 = the abbreviated one)
    cand_i: int = 0               # street labels: which candidate position
    cost: float = 0.0


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
    offset_layouts: list = None   # layouts tried (in order) when the text moves outside
    lines: list = None
    priority: int = 0
    on_fail: str = "keep"
    score_inside: bool = False
    max_cover: float = None
    override: dict = None
    number: bool = False
    leader: bool = True            # False: a label that does not fit inside its shape is hidden instead of moved out with a leader

    def use(self, lay):
        self.w, self.h, self.lines = lay.w, lay.h, lay.lines


@dataclass
class _Line:
    id: str
    cands: list
    w: float
    h: float
    text: str
    size: float
    priority: int = 0
    on_fail: str = "keep"
    max_cover: float = None
    override: dict = None


SCORE_W = {"building": 1.0, "plaza": 0.45, "road": 1.0, "water": 4.0, "junction": 0.5}


def route_leader(anchor, b, style="elbow", shelf=7.0, gap=2.0):
    """Leader polyline from a fixed anchor to a label box b=(l, t, r, bt) (page pt, y down: t < bt).
    Anchor beside the box: elbow = diagonal to a knee, then a horizontal shelf into the middle of the near side edge; straight = one
    segment to that point. Anchor above / below the box: a straight segment to the middle of the top / bottom edge.
    None when the anchor is on the box (no leader needed). panel/jsx/host.jsx has the same rules (reroute_leaders)."""
    l, t, r, bt = b
    ax, ay = anchor
    cx, cy = (l + r) / 2, (t + bt) / 2
    if l - 1.0 <= ax <= r + 1.0 and t - 1.0 <= ay <= bt + 1.0:
        return None
    if ax < l - gap or ax > r + gap:
        side = 1 if ax < l else -1                 # text to the right of the anchor: attach on the left edge
        end = (l - gap, cy) if side > 0 else (r + gap, cy)
        knee = (end[0] - side * shelf, cy)
        if style == "elbow" and shelf > 0 and (knee[0] - ax) * side > 1.5 and abs(ay - cy) > 1.0:
            return [anchor, knee, end]
        return [anchor, end]
    end = (cx, t - gap) if ay < t else (cx, bt + gap)
    return [anchor, end]


class Placer:
    def __init__(self, params, frame=None, shapes=()):
        """frame: (x0, y0, x1, y1) page pt box the text must stay in. shapes: [(id, pts)] closed objects to avoid (ids containing '#' are soft: text avoids them, leaders may cross)."""
        self.p = params
        self.frame = box(*frame) if frame else None
        self.items = []
        self.lines = []
        self.fixed = []
        self.shapes = [(i, Polygon(p).buffer(0)) for i, p in shapes if len(p) >= 3]
        self._tree = STRtree([g for _, g in self.shapes]) if self.shapes else None
        self._feat = {}
        self.junctions = []
        self.weights = dict(SCORE_W)
        self.score = False
        self.move_thresh = 0.30        # area labels: when the best spot inside still covers this much (weighted), try outside too
        self.out_penalty = 0.25
        self._lead = []

    def add(self, id_, poly_pts, text, size, bold=False, rot=None, point=None, layouts=None, offset_layout=None, offset_layouts=None,
            priority=0, on_fail="keep", score_inside=False, max_cover=None, override=None, number=False, leader=True):
        """layouts: [Layout, ...] wrapped variants tried in order for fitting inside (default: the one-line text);
        offset_layouts: variants tried in order when the text has to move outside (default [offset_layout or layouts[0]])."""
        if len(poly_pts) < 3:
            return
        pg = Polygon(poly_pts).buffer(0)
        if pg.is_empty or pg.geom_type not in ("Polygon", "MultiPolygon"):
            return
        if pg.geom_type == "MultiPolygon":
            pg = max(pg.geoms, key=lambda g: g.area)
        w, h = text_size(text, size, bold)
        lays = layouts or [Layout([text], w, h)]
        offs = offset_layouts or [offset_layout or lays[0]]
        it = _Item(id_, pg, text, size, bold, rot, tuple(point) if point else None, w, h, lays, offs, None, priority, on_fail, score_inside,
                   max_cover, override, number, leader)
        it.use(lays[0])
        self.items.append(it)

    def add_line(self, id_, cands, w, h, text, size, priority=0, on_fail="keep", max_cover=None, override=None):
        self.lines.append(_Line(id_, list(cands), w, h, text, size, priority, on_fail, max_cover, override))

    def add_fixed_box(self, b):
        self.fixed.append(b)

    def set_features(self, feats, junctions=(), weights=None):
        """feats: {kind: [(id, shapely geometry in page pt)]}; enables occupancy scoring."""
        self._feat = {}
        for kind, lst_ in feats.items():
            gs = [(i, g) for i, g in lst_ if g is not None and not g.is_empty]
            self._feat[kind] = ([i for i, _ in gs], [g for _, g in gs], STRtree([g for _, g in gs]) if gs else None)
        self.junctions = list(junctions)
        if weights:
            self.weights.update(weights)
        self.score = True

    # -------------------------------------------------------------- occupancy
    def cover(self, b, skip_id=None):
        """{kind: fraction of the box area over that kind of feature} (junction: 1.0 when a road junction is within 3 pt)."""
        out = {}
        a = b.area or 1.0
        for kind, (ids, geoms, tree) in self._feat.items():
            if tree is None:
                continue
            tot = 0.0
            for i in tree.query(b):
                if skip_id is not None and ids[int(i)] == skip_id:
                    continue
                tot += geoms[int(i)].intersection(b).area
            if tot > 0:
                out[kind] = min(tot / a, 1.0)
        if self.junctions:
            bb = b.buffer(3.0)
            if any(bb.contains(Point(j)) for j in self.junctions):
                out["junction"] = 1.0
        return out

    def cost_of(self, b, skip_id=None):
        return sum(self.weights.get(k, 1.0) * f for k, f in self.cover(b, skip_id).items())

    # -------------------------------------------------------------- fit
    def _fits(self, it, c):
        k = 1.0 + self.p.margin_pct / 100.0
        return it.poly.contains(text_box(c[0], c[1], it.w * k, it.h * k, it.rot))

    def _collides(self, it, c, placed):
        b = text_box(c[0], c[1], it.w, it.h, it.rot)
        b = b.buffer(1.5, join_style=2)
        return any(b.intersects(o) for o in placed)

    def _grid(self, it, n=9):
        x0, y0, x1, y1 = it.poly.bounds
        return [(x0 + (x1 - x0) * (i + 0.5) / n, y0 + (y1 - y0) * (j + 0.5) / n) for i in range(n) for j in range(n)]

    def _shifted(self, it, c0, placed):
        pts = self._grid(it)
        pts.sort(key=lambda q: math.hypot(q[0] - c0[0], q[1] - c0[1]))
        return next((q for q in pts if self._fits(it, q) and not self._collides(it, q, placed)), None)

    def _best_inside(self, it, cands, placed):
        """Scoring mode: the spot inside the shape where the text covers the least map (ties: nearest the preferred point)."""
        pts = list(cands) + self._grid(it, 15)
        best = None
        for q in pts:
            if not self._fits(it, q) or self._collides(it, q, placed):
                continue
            tb = text_box(q[0], q[1], it.w, it.h, it.rot)
            c = self.cost_of(tb, it.id) + 0.0015 * math.hypot(q[0] - cands[0][0], q[1] - cands[0][1])
            if best is None or c < best[0]:
                best = (c, q)
                if c < 0.004:
                    break
        return best

    def _free_point(self, it, cands, placed):
        """Leader anchor: a point inside the shape that no placed label sits on (nearest to the label point)."""
        free = lambda q: not any(o.contains(Point(q)) or o.distance(Point(q)) < 1.0 for o in placed)
        for c in cands:
            if free(c):
                return c
        pts = [q for q in self._grid(it) if it.poly.contains(Point(q))]
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
    def _res_inside(self, it, hit, cost=0.0):
        return Result(it.id, hit[0], hit[1] + it.size * 0.35, "middle", it.rot, cx=hit[0], cy=hit[1], w=it.w, h=it.h, lines=it.lines, cost=cost)

    def solve(self):
        results, placed = [], list(self.fixed)
        self._lead = []
        # pinned labels first: they stay exactly where the user put them
        for it in [i for i in self.items if i.override]:
            results.append(self._pin(it, placed))
        for ln in [x for x in self.lines if x.override]:
            ov = ln.override
            rot = ov.get("rot", ln.cands[0][2] if ln.cands else None)
            placed.append(text_box(ov["cx"], ov["cy"], ln.w, ln.h, rot))
            results.append(Result(ln.id, ov["cx"], ov["cy"], "middle", rot, cx=ov["cx"], cy=ov["cy"], w=ln.w, h=ln.h, lines=[ln.text], pinned=True))
        items = [it for it in self.items if not it.override]
        lines = [ln for ln in self.lines if not ln.override]
        # numbered markers claim their spot first
        for it in [i for i in items if i.number]:
            results.append(self._numbered(it, placed))
        items = [i for i in items if not i.number]
        for pr in sorted({i.priority for i in items} | {ln.priority for ln in lines}):
            todo = []
            for it in sorted([i for i in items if i.priority == pr], key=lambda i: i.poly.area):
                r = self._inside(it, placed)
                if r is None:
                    todo.append(it)
                else:
                    results.append(r)
            for ln in [x for x in lines if x.priority == pr]:
                results.append(self._line(ln, placed))
            # smallest shapes first: they have the least room
            for it in todo:
                results.append(self._place_outside(it, placed))
        return results

    def _inside(self, it, placed):
        cands = self._inside_candidates(it)
        if it.score_inside and self.score and self.p.enabled:
            for lay in it.layouts:
                it.use(lay)
                b = self._best_inside(it, cands, placed)
                if b is None:
                    continue
                if b[0] > self.move_thresh:
                    # still busy here: compare with the best spot outside (with a leader)
                    alt = self._offset(it, self._free_point(it, cands, placed), placed, self._lead)
                    it.use(lay)
                    if alt is not None and alt[3] + self.out_penalty < b[0]:
                        return None
                placed.append(text_box(b[1][0], b[1][1], it.w, it.h, it.rot))
                return self._res_inside(it, b[1], b[0])
            return None
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
            it.use(it.offset_layouts[0])
            if not self.p.enabled:
                hit = cands[0]
        if hit is None:
            return None
        placed.append(text_box(hit[0], hit[1], it.w, it.h, it.rot))
        return self._res_inside(it, hit)

    def _place_outside(self, it, placed):
        cands = self._inside_candidates(it)
        if not it.leader and self.p.enabled:
            it.use(it.offset_layouts[0])
            return Result(it.id, cands[0][0], cands[0][1], "middle", it.rot, cx=cands[0][0], cy=cands[0][1], w=it.w, h=it.h, lines=it.lines, status="hidden")
        anchor = self._free_point(it, cands, placed)
        out = self._offset(it, anchor, placed, self._lead)
        if out is not None:
            r, tb, ln, cost = out
            placed.append(tb)
            self._lead.append(ln)
            r.cost = cost
            return r
        it.use(it.offset_layouts[0])
        if it.on_fail == "hide":
            return Result(it.id, cands[0][0], cands[0][1], "middle", it.rot, cx=cands[0][0], cy=cands[0][1], w=it.w, h=it.h, lines=it.lines, status="hidden")
        if it.on_fail == "number":
            return self._numbered(it, placed)
        c = cands[0]                      # nowhere to put it: leave it centred (overflowing)
        placed.append(text_box(c[0], c[1], it.w, it.h, it.rot))
        return self._res_inside(it, c)

    def _numbered(self, it, placed):
        cands = self._inside_candidates(it)
        q = self._free_point(it, cands, placed)
        r_ = max(it.size * 0.62, 3.4)
        placed.append(box(q[0] - r_, q[1] - r_, q[0] + r_, q[1] + r_))
        return Result(it.id, q[0], q[1], "middle", None, cx=q[0], cy=q[1], w=2 * r_, h=2 * r_, lines=[it.text], status="numbered", marker=q)

    def _pin(self, it, placed):
        ov = it.override
        it.use(it.offset_layouts[0])
        cx, cy = ov["cx"], ov["cy"]
        tb = text_box(cx, cy, it.w, it.h, it.rot)
        placed.append(tb)
        r = Result(it.id, cx, cy + it.size * 0.35, "middle", it.rot, cx=cx, cy=cy, w=it.w, h=it.h, lines=it.lines, pinned=True)
        if it.poly.contains(tb):
            return r
        cands = self._inside_candidates(it)
        anchor = tuple(ov["anchor"]) if ov.get("anchor") else min(cands, key=lambda q: math.hypot(q[0] - cx, q[1] - cy))
        pts = route_leader(anchor, tb.bounds, self.p.style, self.p.shelf, self.p.gap)
        if pts:
            r.leader, r.offset = pts, True
            r.dot = anchor if self.p.dot else None
            self._lead.append(LineString(pts))
        return r

    def _line(self, ln, placed):
        best = None
        for i, (cx, cy, rot) in enumerate(ln.cands):
            b = text_box(cx, cy, ln.w, ln.h, rot)
            if any(b.buffer(1.0, join_style=2).intersects(o) for o in placed):
                continue
            if self.frame is not None and not self.frame.contains(b):
                continue
            c = self.cost_of(b, ln.id[:-6] if ln.id.endswith("_label") else ln.id) if self.score else 0.0
            if ln.max_cover is not None and self.score and c > ln.max_cover:
                continue
            c += 0.002 * i
            if best is None or c < best[0]:
                best = (c, i, b, (cx, cy, rot))
                if c < 0.004 or not self.score:
                    break
        if best is None:
            cx, cy, rot = ln.cands[0]
            if ln.on_fail == "hide":
                return Result(ln.id, cx, cy, "middle", rot, cx=cx, cy=cy, w=ln.w, h=ln.h, lines=[ln.text], status="hidden")
            placed.append(text_box(cx, cy, ln.w, ln.h, rot))
            return Result(ln.id, cx, cy, "middle", rot, cx=cx, cy=cy, w=ln.w, h=ln.h, lines=[ln.text])
        placed.append(best[2])
        cx, cy, rot = best[3]
        return Result(ln.id, cx, cy, "middle", rot, cx=cx, cy=cy, w=ln.w, h=ln.h, lines=[ln.text], cand_i=best[1], cost=best[0])

    def _others_hit(self, it, g, skip_soft=False):
        if not self._tree:
            return False
        for i in self._tree.query(g):
            sid, sg = self.shapes[int(i)]
            if sid != it.id and not (skip_soft and "#" in sid) and sg.intersects(g):
                return True
        return False

    def _offset(self, it, anchor, placed, leaders):
        """-> (Result, text box, leader line, cost) or None. Tries the offset layouts in order (full text, then the abbreviated one)."""
        for li, lay in enumerate(it.offset_layouts):
            it.use(lay)
            r = self._offset_one(it, anchor, placed, leaders)
            if r is not None:
                r[0].layout_i = li
                return r
        it.use(it.offset_layouts[0])
        return None

    def _offset_one(self, it, anchor, placed, leaders):
        p = self.p
        pad = 1.5
        gap = p.gap
        shelf = p.shelf if p.style == "elbow" else 0.0
        far = it.poly.bounds
        ray_len = 2 * (max(far[2] - far[0], far[3] - far[1]) + p.max_offset_pt + 50)
        exits = []
        for dx, dy in DIRS:
            n = math.hypot(dx, dy)
            u = (dx / n, dy / n)
            inter = LineString([anchor, (anchor[0] + u[0] * ray_len, anchor[1] + u[1] * ray_len)]).intersection(it.poly)
            re_ = 0.0 if inter.is_empty else max(math.hypot(x - anchor[0], y - anchor[1]) for x, y in _coords(inter))
            exits.append((u, re_))
        step = 2.5 if not self.score else 3.5
        nsteps = int(p.max_offset_pt / step) + 1
        for strict in (3, 2, 1, 0):
            best = None
            for i in range(nsteps):
                for u, r_exit in exits:
                    r = r_exit + 3.0 + i * step
                    k = (anchor[0] + u[0] * r, anchor[1] + u[1] * r)
                    res = self._try(it, anchor, k, u[0], shelf, gap, pad, placed, leaders, strict)
                    if res is None:
                        continue
                    if not self.score:
                        return (*res, 0.0)
                    cd = self.cover(res[1], it.id)
                    if strict >= 1 and cd.get("water", 0) > 0.0:
                        continue                      # never on water (river / lake) unless there is no alternative at all
                    cov = sum(self.weights.get(k_, 1.0) * f_ for k_, f_ in cd.items())
                    if it.max_cover is not None and cov > it.max_cover:
                        continue
                    lead_pen = 0.0
                    ln = res[2]
                    if ln.length > 0:
                        for kind, wk in (("building", 0.3), ("plaza", 0.3), ("water", 1.2), ("road", 0.2)):
                            ids, geoms, tree = self._feat.get(kind, (None, None, None))
                            if tree is not None:
                                for j in tree.query(ln):
                                    if ids[int(j)] != it.id:
                                        lead_pen += geoms[int(j)].intersection(ln).length / ln.length * wk
                    c = cov + lead_pen + 0.004 * r
                    if best is None or c < best[0]:
                        best = (c, res)
                if best is not None and best[0] < 0.004 * (r_exit + 3.0 + i * step) + 0.01:
                    break
            if best is not None:
                return (*best[1], best[0])
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


LAYER_LEADERS, LAYER_ANCHORS = "Leaders", "Leader Anchors"


def leader_svg(res, p, text_color=None):
    """Leader, its casing and the anchor dot of one offset label -> list of (layer, svg).
    Items (names are what the panel's re-route action looks up): <id>_leader_casing (dark, under), <id>_leader (white),
    both open paths from the anchor to the label; <id>_leader_dot on the Leader Anchors layer (drag it to move the anchor).
    p is a LabelParams (a plain number is accepted as the stroke width for old callers)."""
    out = []
    if not res.leader:
        return out
    if not isinstance(p, LabelParams):
        p = LabelParams(stroke_width=float(p), color="#000000", casing=False, dot_ring=False)
    col = (text_color or "#111111") if p.match_text else p.color
    d = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in res.leader)
    dash = f' stroke-dasharray="{p.dash}"' if p.dash else ""
    if p.casing:
        out.append((LAYER_LEADERS, f'<path id="{res.id}_leader_casing" class="leader-casing" fill="none" stroke="{p.casing_color}" '
                                   f'stroke-width="{max(p.casing_width, p.stroke_width + 0.4):g}" stroke-linecap="round" stroke-linejoin="round"{dash} d="{d}"/>'))
    out.append((LAYER_LEADERS, f'<path id="{res.id}_leader" class="leader" fill="none" stroke="{col}" stroke-width="{p.stroke_width:g}" '
                               f'stroke-linecap="round" stroke-linejoin="round"{dash} d="{d}"/>'))
    if res.dot:
        r = p.dot_radius
        ring = f'stroke="{p.casing_color}" stroke-width="0.7"' if p.dot_ring else 'stroke="none"'
        out.append((LAYER_ANCHORS, f'<circle id="{res.id}_leader_dot" class="leader-dot" cx="{res.dot[0]:.2f}" cy="{res.dot[1]:.2f}" r="{r:.2f}" '
                                   f'fill="{col}" {ring}/>'))
    return out
