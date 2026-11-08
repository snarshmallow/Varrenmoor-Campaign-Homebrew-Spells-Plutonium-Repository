"""Street layout templates for town_gen: genuinely different street networks, not parameter biases of the tensor-field tracer.

  radial_market   a market town: a market square at the centre, 5-9 spokes out to the edge (one of them is the entry road's direction), one or two ring lanes.
  linear_river    a linear / river village: the entry road is the high street, parallel back lanes either side, short cross lanes every 80-130 ft, and a lane along the river.

Both return the same list town_gen.trace_streams returns ([{pts, fam, w}], fam 0 = major, 1 = minor) so plazas, cutting, clean-up, blocks, lots and buildings run unchanged.
Driven by place params only (population / area radius, rings, entry, river): nothing here is specific to a place. Select with town_params["streets"]["template"].
"""
import math
import random

from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import unary_union

TEMPLATES = ("radial_market", "linear_river")


def _lines(g):
    if g.is_empty:
        return []
    if g.geom_type == "LineString":
        return [g]
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "LineString"]


def _emit(out, ln, fam, width, min_len):
    for part in _lines(ln):
        if part.length >= min_len:
            pts = list(part.segmentize(8.0).coords)
            out.append({"pts": [(float(x), float(y)) for x, y in pts], "fam": fam, "w": float(width)})


def _width_at(g, x, y, fam):
    rp = g.ring_params(g.r_at(x, y))
    return rp["street_width"] * (1.0 if fam == 0 else 0.85)


def radial_market(g, seed_off=11):
    """Spokes + ring lanes around the centre (a market town)."""
    rng = random.Random(int(g.seed) * 7919 + seed_off)
    cx, cy = g.P["ring_spec"]["centre"]
    area = g.area
    minx, miny, maxx, maxy = area.bounds
    R = max(math.hypot(cx - x, cy - y) for x in (minx, maxx) for y in (miny, maxy))
    Ravg = math.sqrt(max(area.area, 1.0) / math.pi)
    n = int(min(9, max(5, round(Ravg / 105.0))))
    start = g.main_line.coords[0]
    a0 = math.atan2(start[1] - cy, start[0] - cx)                          # one spoke is the entry road's bearing
    out = []
    inner = area.buffer(-4)
    for k in range(n):
        a = a0 + 2 * math.pi * k / n + rng.uniform(-0.12, 0.12) * (0 if k == 0 else 1)
        pts = []
        L = 0.0
        while L < R:
            wob = 1.0 + 0.0
            pts.append((cx + math.cos(a + 0.05 * math.sin(L / 90.0 + k)) * L, cy + math.sin(a + 0.05 * math.sin(L / 90.0 + k)) * L))
            L += 12.0
        ln = LineString(pts).intersection(inner)
        _emit(out, ln, 0, _width_at(g, cx + math.cos(a) * 150, cy + math.sin(a) * 150, 0), 40.0)
    rr = [0.36, 0.68] if Ravg > 330 else [0.5]
    for f in rr:
        r0 = Ravg * f
        w = _width_at(g, cx + r0, cy, 1)
        pts = []
        for i in range(97):
            t = 2 * math.pi * i / 96
            r = r0 * (1 + 0.05 * math.sin(3 * t + rng.uniform(0, 1)) + 0.03 * math.sin(5 * t))
            pts.append((cx + r * math.cos(t), cy + r * math.sin(t)))
        _emit(out, LineString(pts).intersection(inner), 1, w, 40.0)
    return out


def linear_river(g, seed_off=23):
    """High street (the entry road) + back lanes + cross lanes + a river lane (a linear village strung along a road / river)."""
    rng = random.Random(int(g.seed) * 6151 + seed_off)
    area = g.area
    inner = area.buffer(-4)
    spine = g.main_line
    out = []
    # the high street runs THROUGH the village: continue the entry road past the centre in the same direction to the far edge of the area
    c0 = g.P["ring_spec"]["centre"]
    pts = list(spine.coords)
    Ravg0 = math.sqrt(max(area.area, 1.0) / math.pi)
    a_, b_ = pts[-2], pts[-1]
    t_ = (b_[0] - a_[0], b_[1] - a_[1])
    tl = math.hypot(*t_) or 1.0
    ext = LineString([b_, (b_[0] + t_[0] / tl * Ravg0 * 1.15, b_[1] + t_[1] / tl * Ravg0 * 1.15)]).intersection(inner)
    ext_parts = [x for x in _lines(ext) if x.length > 30]
    if ext_parts:
        _emit(out, ext_parts[0], 0, _width_at(g, b_[0], b_[1], 0), 30.0)
        spine = LineString(pts + list(ext_parts[0].coords)[1:])
    w_minor = _width_at(g, *spine.interpolate(spine.length / 2).coords[0], 1)
    Ravg = math.sqrt(max(area.area, 1.0) / math.pi)
    offs = [95.0, -95.0] + ([190.0, -190.0] if Ravg > 360 else [])
    for d in offs:
        try:
            oc = spine.offset_curve(d, join_style=2)
        except Exception:
            continue
        for part in _lines(oc):
            _emit(out, part.simplify(2.0).intersection(inner), 1 if abs(d) > 100 else 0, w_minor, 60.0)
    sp = 95.0
    s = 40.0
    side = 1
    while s < spine.length - 30:
        p = spine.interpolate(s)
        q = spine.interpolate(min(spine.length, s + 6))
        dx, dy = q.x - p.x, q.y - p.y
        ln_ = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / ln_, dx / ln_
        depth = rng.uniform(75.0, 150.0) * (1.0 if abs(offs[0]) < 100 else 1.0)
        for sg in ((side,) if rng.random() < 0.6 else (1, -1)):
            seg = LineString([(p.x, p.y), (p.x + nx * sg * depth, p.y + ny * sg * depth)])
            _emit(out, seg.intersection(inner), 1, w_minor * 0.9, 30.0)
        side = -side
        s += sp + rng.uniform(-22.0, 28.0)
    riv = g.water.river_polygon if hasattr(g.water, "river_polygon") else None
    if riv is not None and not riv.is_empty:
        lane = riv.buffer(g.L["bank_margin_ft"] + 24.0).exterior
        _emit(out, lane.difference(riv.buffer(g.L["bank_margin_ft"] + 8.0)).intersection(inner), 1, w_minor, 60.0)
    return out


def generate(name, g):
    if name == "radial_market":
        return radial_market(g)
    if name == "linear_river":
        return linear_river(g)
    raise ValueError(f"unknown layout template {name!r}; have {TEMPLATES}")
