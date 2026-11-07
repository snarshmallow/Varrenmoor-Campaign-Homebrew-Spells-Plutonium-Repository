"""Contour lines and elevation labels from a heightmap, emitted into a lib_svg.LayerTree.

  from contours import ContourParams, Frame, build, emit
  cs = build(h, cell_ft, Frame(x0, y0, x1, y1, pt_per_ft, ox_pt, oy_pt), ContourParams(...), mask_polys=[...])
  emit(tree, cs)       # LINES/Terrain/'Contours - Minor' + 'Contours - Index', LABELS/'Labels - Elevation'

Pipeline: Gaussian pre-smooth -> cubic-spline upsample (x4) -> contourpy -> drop tiny closed loops -> shapely simplify + Chaikin -> clip to the view window
-> subtract mask polygons (optional, feet) -> place labels on index contours (rotated boxes, STRtree collision)
-> cut a small gap in every contour under each label -> ids contour_<elev>_<n>.
Intervals are in the chosen `units` (ft or m); heights in the heightmap are feet.
"""
import math
from dataclasses import dataclass, field

import contourpy
import numpy as np
from scipy import ndimage as ndi
from shapely import affinity
from shapely.geometry import LineString, MultiLineString, box
from shapely.ops import linemerge, unary_union
from shapely.strtree import STRtree
from xml.sax.saxutils import escape

M_PER_FT = 0.3048

CSS = """\
.contour-minor { fill: none; stroke: #8a5a2b; stroke-width: 0.3; stroke-linejoin: round; stroke-linecap: round; }
.contour-index { fill: none; stroke: #8a5a2b; stroke-width: 0.85; stroke-linejoin: round; stroke-linecap: round; }
.contour-datum { fill: none; stroke: #1a4f8a; stroke-width: 1.1; }
.contour-label { fill: #6b4423; stroke: none; font-family: Arial, sans-serif; }"""

LAYER_MINOR, LAYER_INDEX, LAYER_LABELS = "Contours - Minor", "Contours - Index", "Labels - Elevation"


@dataclass
class ContourParams:
    minor: float = 10.0            # minor interval, in `units`
    index: float = 50.0            # index interval, in `units` (multiple of minor)
    units: str = "ft"              # "ft" or "m" (labels and intervals)
    decimals: int = 0              # decimal places in labels
    suffix: str = ""               # appended to label text, e.g. " ft"
    font_size: float = 6.0         # label size in points
    label_spacing_ft: float = 500.0  # target distance between labels along one contour
    min_len_ft: float = 120.0      # drop contour pieces shorter than this
    follow_line: bool = True       # rotate labels along the contour (False: horizontal)
    upright: bool = True           # flip labels so they never read upside down
    max_bend_deg: float = 25.0     # reject label spots where the line bends more than this under the label
    halo_pt: float = 1.5           # gap cut in contours around each label
    smooth_sigma: float = 0.8      # Gaussian sigma in heightmap cells (pre-smooth before upsampling)
    upsample: int = 4              # cubic-spline upsampling factor: contour crossings are found at sub-cell accuracy
    simplify_ft: float = 0.3
    chaikin: int = 2               # light corner cutting on the traced polyline (no stair-steps, closed loops stay closed)
    min_closed_area_ft2: float = 2500.0   # drop closed contours enclosing less than this (noise confetti); 0 = keep all
    use_mask: bool = True
    labels: bool = True
    sea_level_ft: float = 0.0      # datum (signed elevations); levels and index contours are counted from it
    emphasize_datum: bool = True   # draw the datum (0 ft / shoreline) contour with class contour-datum
    minus: str = "-"               # minus sign used in labels ("−" for a true minus)


@dataclass
class Frame:
    """Feet window that is drawn, and how feet map to page points: pt = o + (ft - x0) * k."""
    x0: float
    y0: float
    x1: float
    y1: float
    k: float
    ox: float = 0.0
    oy: float = 0.0

    def matrix(self):
        return [self.k, 0, 0, self.k, self.ox - self.x0 * self.k, self.oy - self.y0 * self.k]


@dataclass
class ContourSet:
    pieces: list = field(default_factory=list)   # {id, elev, index, pts (page pt), closed}
    labels: list = field(default_factory=list)   # {id, text, x, y, rot, size} (page pt)


def chaikin(pts, n, closed):
    pts = np.asarray(pts, float)
    for _ in range(n):
        if closed:
            a, b = pts[:-1], pts[1:]
            q, r = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
            out = np.empty((2 * len(a), 2))
            out[0::2], out[1::2] = q, r
            pts = np.vstack([out, out[:1]])
        else:
            a, b = pts[:-1], pts[1:]
            q, r = 0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b
            out = np.empty((2 * len(a), 2))
            out[0::2], out[1::2] = q, r
            pts = np.vstack([pts[:1], out, pts[-1:]])
    return pts


def _ring_area(a):
    x, y = a[:, 0], a[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _lines(geom):
    if geom.is_empty:
        return []
    if isinstance(geom, LineString):
        return [geom]
    if isinstance(geom, MultiLineString):
        return list(geom.geoms)
    return [g for g in getattr(geom, "geoms", []) if isinstance(g, LineString)]


def _merge(geom):
    ls = _lines(geom)
    if len(ls) > 1:
        ls = _lines(linemerge(ls))
    return [g for g in ls if len(g.coords) >= 2]


def _label_text(v, p):
    t = f"{v:.{p.decimals}f}"
    if float(t) == 0:
        t = t.lstrip("-")           # never print "-0"
    return t.replace("-", p.minus) + p.suffix


def build(h, cell_ft, frame, params=None, mask_polys=None):
    p = params or ContourParams()
    f_u = M_PER_FT if p.units == "m" else 1.0           # feet -> chosen units
    ny, nx = h.shape
    hs = ndi.gaussian_filter(h.astype(float), p.smooth_sigma, mode="nearest") if p.smooth_sigma else h.astype(float)
    u = max(1, int(p.upsample))
    if u > 1:
        oy_, ox_ = (ny - 1) * u + 1, (nx - 1) * u + 1
        hs = ndi.zoom(hs, (oy_ / ny, ox_ / nx), order=3, mode="nearest")
    xs = np.linspace(0, (nx - 1) * cell_ft, hs.shape[1])
    ys = np.linspace(0, (ny - 1) * cell_ft, hs.shape[0])
    gen = contourpy.contour_generator(xs, ys, hs * f_u, line_type=contourpy.LineType.Separate)

    win = box(frame.x0, frame.y0, frame.x1, frame.y1)
    mask = None
    if p.use_mask and mask_polys:
        ms = [m.intersection(win) for m in mask_polys if not m.is_empty and m.intersects(win)]
        if ms:
            mask = unary_union([m.buffer(0) for m in ms])
    mat = frame.matrix()

    zmin, zmax = float(hs.min() * f_u), float(hs.max() * f_u)
    sea = p.sea_level_ft * f_u
    lv0 = math.ceil((zmin - sea) / p.minor - 1e-9)       # works for negative elevations (ceil/floor on signed values)
    lv1 = math.floor((zmax - sea) / p.minor + 1e-9)
    pieces = []     # {elev, index, geom (page pt), closed}
    for i in range(lv0, lv1 + 1):
        level = sea + i * p.minor
        rel = i * p.minor
        is_index = abs(rel / p.index - round(rel / p.index)) < 1e-6
        is_datum = abs(rel) < 1e-9
        for arr in gen.lines(level):
            if len(arr) < 3:
                continue
            closed = bool(np.allclose(arr[0], arr[-1]))
            if closed and p.min_closed_area_ft2 > 0 and len(arr) >= 4 and abs(_ring_area(arr)) < p.min_closed_area_ft2 :
                continue
            ls = LineString(arr)
            if p.simplify_ft:
                ls = ls.simplify(p.simplify_ft)
            c = chaikin(np.array(ls.coords), p.chaikin, closed)
            ls = LineString(c)
            if closed and not win.contains(ls):
                closed = False
            if not ls.intersects(win):
                continue
            geom = ls if win.contains(ls) else ls.intersection(win)
            if mask is not None and geom.intersects(mask):
                geom = geom.difference(mask)
                closed = False
            for seg in _merge(geom) if not (closed and isinstance(geom, LineString)) else [geom]:
                if seg.length < p.min_len_ft:
                    continue
                pieces.append({"elev": level, "index": is_index, "datum": is_datum, "closed": closed and seg is geom,
                               "geom": affinity.affine_transform(seg, mat)})

    cs = ContourSet()
    cs.emphasize_datum = p.emphasize_datum
    if p.labels:
        cs.labels = _place_labels(pieces, frame, p, mask, mat)
    halos = [lb["box"].buffer(p.halo_pt) for lb in cs.labels] if p.halo_pt > 0 else []
    if halos:
        tree = STRtree(halos)
        for pc in pieces:
            idx = tree.query(pc["geom"])
            hit = [halos[j] for j in idx if halos[j].intersects(pc["geom"])]
            if hit:
                pc["geom"] = pc["geom"].difference(unary_union(hit))
                pc["closed"] = False

    counters = {}
    for pc in sorted(pieces, key=lambda d: (d["elev"], d["geom"].bounds)):
        for seg in _merge(pc["geom"]) if not pc["closed"] else [pc["geom"]]:
            e = f"{pc['elev']:g}"
            counters[e] = counters.get(e, 0) + 1
            cs.pieces.append({"id": f"contour_{e}_{counters[e]}", "elev": pc["elev"], "index": pc["index"], "datum": pc.get("datum", False),
                              "pts": list(seg.coords), "closed": pc["closed"]})
    cl = {}
    for lb in cs.labels:
        e = f"{lb['elev']:g}"
        cl[e] = cl.get(e, 0) + 1
        lb["id"] = f"contour_label_{e}_{cl[e]}"
        del lb["box"]
    return cs


def _place_labels(pieces, frame, p, mask, mat):
    size = p.font_size
    spacing = p.label_spacing_ft * frame.k
    min_len = p.min_len_ft * frame.k
    idx_pieces = [pc for pc in pieces if pc["index"] or pc.get("datum")]
    geoms = [pc["geom"] for pc in idx_pieces]
    tree = STRtree(geoms) if geoms else None
    mask_pt = affinity.affine_transform(mask, mat) if mask is not None else None
    area = box(frame.ox + 2, frame.oy + 2, frame.ox + (frame.x1 - frame.x0) * frame.k - 2,
               frame.oy + (frame.y1 - frame.y0) * frame.k - 2)
    placed, out = [], []
    f_u = M_PER_FT if p.units == "m" else 1.0
    for pi in sorted(range(len(idx_pieces)), key=lambda i: -geoms[i].length):
        pc, g = idx_pieces[pi], geoms[pi]
        L = g.length
        text = _label_text(pc["elev"], p)
        w = len(text) * size * 0.56 + 2.0
        hh = size * 0.95
        if L < max(min_len, w * 1.6):
            continue
        nslots = max(1, int(round(L / spacing)))
        for s in range(nslots):
            centre = (s + 0.5) * L / nslots
            reach = L / nslots * 0.45
            offs = [0.0]
            step = max(w * 0.5, 2.0)
            n = int(reach / step)
            for j in range(1, n + 1):
                offs += [j * step, -j * step]
            for off in offs:
                d = centre + off
                if d - w / 2 < 0 or d + w / 2 > L:
                    continue
                cand = _candidate(g, d, w, hh, p)
                if cand is None:
                    continue
                bx, ang, (cx, cy) = cand
                if not area.contains(bx):
                    continue
                if any(bx.intersects(o) for o in placed):
                    continue
                if mask_pt is not None and bx.intersects(mask_pt):
                    continue
                if tree is not None and any(j != pi and bx.intersects(geoms[j]) for j in tree.query(bx)):
                    continue
                placed.append(bx)
                out.append({"text": text, "x": cx, "y": cy, "rot": ang, "size": size, "elev": pc["elev"], "box": bx})
                break
    return out


def _candidate(g, d, w, hh, p):
    a, m, b = g.interpolate(d - w / 2), g.interpolate(d), g.interpolate(d + w / 2)
    if p.follow_line:
        ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x))
        a1 = math.degrees(math.atan2(m.y - a.y, m.x - a.x))
        a2 = math.degrees(math.atan2(b.y - m.y, b.x - m.x))
        bend = abs((a2 - a1 + 180) % 360 - 180)
        if bend > p.max_bend_deg:
            return None
    else:
        ang = 0.0
    if p.upright and (ang > 90 or ang <= -90):
        ang = (ang + 180 + 180) % 360 - 180
    cx, cy = m.x, m.y
    bx = affinity.rotate(box(cx - w / 2, cy - hh / 2, cx + w / 2, cy + hh / 2), ang, origin=(cx, cy))
    return bx, ang, (cx, cy)


def _d(pts, closed):
    s = "M" + " L".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    return s + (" Z" if closed else "")


def cut_pieces(cs, geom, min_len=1.5):
    """Remove the parts of every contour piece under `geom` (page pt), splitting pieces into open paths; ids are renumbered."""
    if geom is None or geom.is_empty or not cs.pieces:
        return 0
    tree = STRtree([geom])
    out, n_cut, counters = [], 0, {}
    for pc in cs.pieces:
        ls = LineString(pc["pts"])
        if not tree.query(ls).size or not ls.intersects(geom):
            out.append(pc)
            continue
        n_cut += 1
        for seg in _merge(ls.difference(geom)):
            if seg.length >= min_len:
                out.append({**pc, "pts": list(seg.coords), "closed": False})
    if n_cut:
        for pc in out:
            e = f"{pc['elev']:g}"
            counters[e] = counters.get(e, 0) + 1
            pc["id"] = f"contour_{e}_{counters[e]}"
    cs.pieces = out
    return n_cut


def emit(tree, cs, layer_minor=LAYER_MINOR, layer_index=LAYER_INDEX, layer_labels=LAYER_LABELS, labels=True):
    for pc in cs.pieces:
        cls = "contour-index" if pc["index"] else "contour-minor"
        if pc.get("datum") and getattr(cs, "emphasize_datum", True):
            cls = "contour-datum"
        pts = pc["pts"][:-1] if pc["closed"] else pc["pts"]
        tree.add(layer_index if pc["index"] else layer_minor,
                 f'<path id="{pc["id"]}" class="{cls}" fill="none" d="{_d(pts, pc["closed"])}"/>')
    for lb in (cs.labels if labels else []):
        tr = f' transform="rotate({lb["rot"]:.2f} {lb["x"]:.2f} {lb["y"]:.2f})"' if abs(lb["rot"]) > 0.01 else ""
        tree.add(layer_labels,
                 f'<text id="{lb["id"]}" class="contour-label" x="{lb["x"]:.2f}" y="{lb["y"] + lb["size"] * 0.35:.2f}" '
                 f'font-size="{lb["size"]:g}" text-anchor="middle"{tr}>{escape(lb["text"])}</text>')
