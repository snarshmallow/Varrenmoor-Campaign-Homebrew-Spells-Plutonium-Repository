"""Text on a path: street names (and the river) follow the centreline where it bends. Page-point output for render_world / label_style.

  curved_path(points_ft, centre_xy_pt, length_pt, view, offset_ft, min_curve_deg) -> (d, turn_deg) | None
      sub-polyline of the centreline of about length_pt page points around the point nearest centre_xy_pt, oriented left to right on the page
      (so the text always reads upright), shifted `offset_ft` to the upper side of the page. None when the street is straight enough
      (turn < min_curve_deg: the straight rotated label is used) or too short.
  river_path(...)  same for a centreline without the straightness test (the river label always follows the water).
SVG form (label_style._text_el): <path id="X_tp" d=...> + <text><textPath href="#X_tp" startOffset="50%">name</textPath></text>.
Illustrator imports that as type on a path; the repo rasteriser (svg_raster.py) draws it glyph by glyph.
"""
import math

from shapely.geometry import LineString, Point


def _turn(pts):
    """Total absolute heading change (deg) along a polyline (resampled to ~8 chords): ~0 for a straight run, large for a bend or an S."""
    n = len(pts)
    if n < 4:
        return 0.0
    idx = sorted({round(i * (n - 1) / 8.0) for i in range(9)})
    q = [pts[i] for i in idx]
    hs = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(q, q[1:]) if abs(b[0] - a[0]) + abs(b[1] - a[1]) > 1e-9]
    return sum(abs((h2 - h1 + 180) % 360 - 180) for h1, h2 in zip(hs, hs[1:]))


def _window(line, d_mid, length, step):
    a, b = max(d_mid - length / 2.0, 0.0), min(d_mid + length / 2.0, line.length)
    if b - a < length * 0.6:
        return None
    n = max(int((b - a) / step), 3)
    return [line.interpolate(a + (b - a) * i / n) for i in range(n + 1)], a, b


def curved_path(points_ft, centre_pt, length_pt, v, offset_ft=0.0, min_curve_deg=12.0, always=False):
    line = LineString(points_ft)
    cx_ft = (centre_pt[0] - v.margin * 72) / v.k + v.x0
    cy_ft = (centre_pt[1] - v.margin * 72) / v.k + v.y0
    d_mid = line.project(Point(cx_ft, cy_ft))
    length_ft = length_pt / v.k
    w = _window(line, d_mid, length_ft, max(length_ft / 24.0, 1.0))
    if w is None:
        return None
    pts, a, b = w
    xy = [(p.x, p.y) for p in pts]
    turn = _turn(xy)
    if not always and turn < min_curve_deg:
        return None
    if xy[-1][0] < xy[0][0]:                          # read left to right
        xy.reverse()
    out = []
    for i, p in enumerate(xy):
        q0, q1 = xy[max(i - 1, 0)], xy[min(i + 1, len(xy) - 1)]
        tx, ty = q1[0] - q0[0], q1[1] - q0[1]
        L = math.hypot(tx, ty) or 1.0
        tx, ty = tx / L, ty / L
        nx, ny = ty, -tx                              # glyph-up side of the path (page y points down)
        out.append((p[0] + nx * offset_ft, p[1] + ny * offset_ft))
    q = [v.px(p) for p in out]
    return "M" + " L".join("%.2f,%.2f" % p for p in q), turn
