"""Perspective-correct (rectify) the painted oblique Varrenmoor map into a top-down plan view.

    python rectify_map.py fit                      # fit the camera from the field/circle constraints, print residuals
    python rectify_map.py warp  [--in X --out Y]   # fit (or use --tilt/--focal/--roll/--h-matrix) and write PNG + JSON
    python rectify_map.py compare                  # side-by-side before/after with the checks drawn

Model: a pinhole camera looking at the flat ground, tilted `tilt` degrees away from straight down (0 = plan view),
focal length `focal` px, principal point at the image centre, image roll `roll` deg.  Ground coordinates come out in
units of camera height (X right, Y far).  The fit minimises (a) right angles and a shared orientation for the five
Fenn/Thorne-style field rectangles and (b) the roundness of two circular features (churchyard wall, Hollow Oak green).
The UI furniture (compass, scale bar, title cartouche) is inpainted before the warp and a clean scale bar and north arrow
are drawn onto the result instead.  Pure numpy/OpenCV, no Foundry or Illustrator needed.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "out")
DEFAULT_IN = os.path.join(OUT_DIR, "foundry_screens", "varrenmoor_original_map.png")
DEFAULT_OUT = os.path.join(OUT_DIR, "varrenmoor_overhead_map.png")

SRC_W, SRC_H = 1448, 1086
OLD_FT_PER_PX = 7.69          # uniform scale used by varrenmoor_build.py
OLD_ORIGIN = (0.0, 160.0)     # map px that world/varrenmoor digitising treats as the origin
BAR_ROW = 163.0               # image row of the scale bar (0..1000 ft spans 130 px along x)
BAR_PX, BAR_FT = 130.0, 1000.0

# Furniture rectangles in source px (x0, y0, x1, y1): compass, scale bar, title cartouche, "To Bridgehollow" is kept (it is map text).
MASKS = [  # kept for the sidecar
    (30, 20, 180, 200), (10, 860, 430, 1030)]

# Control data read from the painting (source px).  Quads are ordered left, top, right, bottom corner.
FIELDS = {
    "fenn_A": [(774, 710), (830, 687.5), (895, 715), (847.5, 750)],
    "fenn_B": [(842.5, 817.5), (912.5, 787.5), (972.5, 822.5), (905, 852.5)],
    "fenn_C": [(942.5, 875), (1000, 846), (1112.5, 897.5), (1045, 935)],
    "fenn_D": [(1092.5, 702.5), (1160, 667.5), (1235, 710), (1180, 747.5)],
    "fenn_E": [(1182.5, 805), (1240, 757.5), (1265, 785), (1210, 835)],
}
# Ellipses (cx, cy, semi-major, semi-minor, angle deg) tracing the circular walls/greens in the painting.
CIRCLES = {
    "churchyard": (689, 334, 70.0, 38.0, -8.0),
    "hollow_oak": (490, 514, 54.0, 38.0, -5.0),
}
# Fields left out of the fit (corners uncertain: the green field is half hidden by trees) but still reported in the quality checks.
FIT_EXCLUDE = {"fenn_E"}
FOCAL_MAX = 20000.0   # beyond this the camera is effectively orthographic-oblique
CIRCLE_WEIGHT = {"churchyard": 1.0, "hollow_oak": 0.5}


# ---------------------------------------------------------------- homography maths
def apply_h(H, pts):
    """Apply a 3x3 homography to an (N,2) array / list of points."""
    p = np.asarray(pts, float).reshape(-1, 2)
    q = np.c_[p, np.ones(len(p))] @ np.asarray(H, float).T
    return q[:, :2] / q[:, 2:3]


def camera_h(tilt_deg, focal, roll_deg=0.0, cx=SRC_W / 2.0, cy=SRC_H / 2.0):
    """Source px -> ground plane (units of camera height, X right, Y far) for a tilted pinhole camera."""
    t, r = math.radians(tilt_deg), math.radians(roll_deg)
    pre = np.array([[math.cos(r), -math.sin(r), 0], [math.sin(r), math.cos(r), 0], [0, 0, 1]]) @ \
        np.array([[1, 0, -cx], [0, 1, -cy], [0, 0, 1]])
    g = np.array([[1, 0, 0], [0, -math.cos(t), focal * math.sin(t)], [0, math.sin(t), focal * math.cos(t)]])
    return g @ pre


def to_output(Hg, width, margin=0.0, src_pts=None, rotate_deg=0.0):
    """Return (H_src_to_out, (W, Hh), s) that frames the ground image of the source rectangle, with width `width` px.
    Output rows increase downward (plan Y is flipped)."""
    if rotate_deg:
        a = math.radians(rotate_deg)
        Hg = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]) @ Hg
    corners = apply_h(Hg, [(0, 0), (SRC_W, 0), (SRC_W, SRC_H), (0, SRC_H)] if src_pts is None else src_pts)
    x0, x1 = corners[:, 0].min(), corners[:, 0].max()
    y0, y1 = corners[:, 1].min(), corners[:, 1].max()
    s = (width - 2 * margin) / (x1 - x0)
    A = np.array([[s, 0, margin - s * x0], [0, -s, margin + s * y1], [0, 0, 1]])
    Hh = int(math.ceil((y1 - y0) * s + 2 * margin))
    return A @ Hg, (int(width), Hh), s


def invert(H):
    Hi = np.linalg.inv(np.asarray(H, float))
    return Hi / Hi[2, 2]


# ---------------------------------------------------------------- fit
def _edge_angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def _wrap90(x):
    return (x + math.pi / 2) % math.pi - math.pi / 2


def ellipse_pts(c, n=48):
    cx, cy, a, b, t = c
    t = math.radians(t)
    u = np.linspace(0, 2 * math.pi, n, endpoint=False)
    x, y = a * np.cos(u), b * np.sin(u)
    return np.c_[cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)]


def residuals(params, fields=FIELDS, circles=CIRCLES, reg=True):
    tilt, focal, roll, alpha = params
    Hg = camera_h(tilt, focal, roll)
    res = []
    for fname, q in fields.items():
        if fname in FIT_EXCLUDE:
            continue
        p = apply_h(Hg, q)
        for i in range(4):
            e = _edge_angle(p[i], p[(i + 1) % 4])
            # edges 0,2 (L->T, R->B) are one side, 1,3 the other; sides are 90 deg apart, all fields share alpha
            res.append(_wrap90(e - (alpha + (math.pi / 2 if i % 2 == 0 else 0.0))))
    for name, c in circles.items():
        p = apply_h(Hg, ellipse_pts(c))
        m = p.mean(0)
        r = np.hypot(*(p - m).T)
        res.extend(CIRCLE_WEIGHT.get(name, 1.0) * (r / r.mean() - 1.0))
    if reg:  # weak priors: tilt 30..60 deg from nadir, focal ~ image width, tiny roll
        res.append(0.02 * (focal / 1448.0 - 1.0))
        res.append(0.05 * math.radians(roll))
    return np.array(res)


def fit(verbose=False):
    from scipy.optimize import least_squares
    best = None
    for t0 in (35, 50, 65):
        for f0 in (900, 2400, 8000):
            r = least_squares(residuals, [t0, f0, 0.0, 0.3], bounds=([5, 400, -15, -1.6], [85, FOCAL_MAX, 15, 1.6]))
            if best is None or r.cost < best.cost:
                best = r
    # uncertainty: profile the tilt with the other parameters re-optimised, find where cost rises by 50 % over the minimum
    return best


def profile_tilt(best, tilts):
    from scipy.optimize import least_squares
    out = []
    for t in tilts:
        r = least_squares(lambda p: residuals([t, p[0], p[1], p[2]]), [best.x[1], best.x[2], best.x[3]],
                          bounds=([400, -15, -1.6], [FOCAL_MAX, 15, 1.6]))
        out.append((t, r.cost, r.x[0]))
    return out


def quality(Hg):
    """Per-feature measurements in the ground plane: corner angles, edge ratio, circle axis ratios."""
    out = {"fields": {}, "circles": {}}
    for n, q in FIELDS.items():
        p = apply_h(Hg, q)
        ang = []
        for i in range(4):
            a, b, c = p[i - 1], p[i], p[(i + 1) % 4]
            v1, v2 = a - b, c - b
            ang.append(math.degrees(math.acos(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))))
        L = [np.linalg.norm(p[(i + 1) % 4] - p[i]) for i in range(4)]
        out["fields"][n] = {"corner_angles_deg": [round(a, 1) for a in ang],
                            "max_angle_error_deg": round(max(abs(a - 90) for a in ang), 1),
                            "opposite_edge_ratio": [round(L[0] / L[2], 3), round(L[1] / L[3], 3)],
                            "side_ratio_long_short": round(max(np.mean(L[0::2]), np.mean(L[1::2])) /
                                                           min(np.mean(L[0::2]), np.mean(L[1::2])), 2),
                            "orientation_deg": round(math.degrees(_wrap90(_edge_angle(p[1], p[2]))), 1)}
    import cv2
    for n, c in CIRCLES.items():
        src = ellipse_pts(c)
        raw = cv2.fitEllipse(src.astype(np.float32))
        p = apply_h(Hg, src)
        m = p.mean(0)
        r = np.hypot(*(p - m).T)
        e = cv2.fitEllipse(p.astype(np.float32))
        out["circles"][n] = {"source_axis_ratio": round(min(raw[1]) / max(raw[1]), 3),
                             "rectified_axis_ratio": round(min(e[1]) / max(e[1]), 3),
                             "radius_rms_error_pct": round(100 * float(np.std(r) / np.mean(r)), 1)}
    return out


# ---------------------------------------------------------------- scale
def scale_from_bar(Hg, bar_row=BAR_ROW, mode="bar"):
    """Ground units (camera heights) per source px along x at `bar_row`, then ft per ground unit so that the bar's
    130 px = 1000 ft holds there.  mode 'bar': valid at the bar's own row.  mode 'centre': valid at the image centre
    (alternative reading, scale of the bar applied to the middle row).  Returns ft per ground unit."""
    row = bar_row if mode == "bar" else SRC_H / 2.0
    x = SRC_W / 2.0
    a = apply_h(Hg, [(x, row)])[0]
    b = apply_h(Hg, [(x + 1.0, row)])[0]
    unit_per_px = float(np.linalg.norm(b - a))
    return (BAR_FT / BAR_PX) / unit_per_px  # ft per ground unit


# ---------------------------------------------------------------- imaging
# (mask rect, donor offset dx, dy): the furniture is covered with a feathered copy of nearby clean map texture.
DONORS = [((30, 20, 180, 200), 170, 10), ((10, 860, 430, 1030), 0, -200)]


def remove_furniture(img):
    """Cover compass / scale bar / cartouche with feathered copies of neighbouring map texture (returns a copy)."""
    import cv2
    out = img.copy()
    H, W = img.shape[:2]
    for (x0, y0, x1, y1), dx, dy in DONORS:
        m = np.zeros((H, W), np.float32)
        m[y0:y1, x0:x1] = 1.0
        m = cv2.GaussianBlur(m, (0, 0), 5)
        donor = np.zeros_like(out)
        ys, xs = np.mgrid[0:H, 0:W]
        mx = np.clip(xs + dx, 0, W - 1).astype(np.float32)
        my = np.clip(ys + dy, 0, H - 1).astype(np.float32)
        donor = cv2.remap(img, mx, my, cv2.INTER_LINEAR)
        out = (out * (1 - m[..., None]) + donor * m[..., None]).astype(np.uint8)
    return out


def warp(img, H, size):
    import cv2
    return cv2.warpPerspective(img, H, size, flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)


def draw_furniture(canvas, ft_per_px, base_y=None):
    """Draw a clean scale bar (1000 ft) and north arrow, unwarped, bottom-left of the plan."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.fromarray(canvas[..., ::-1])
    d = ImageDraw.Draw(im, "RGBA")
    try:
        font = ImageFont.truetype("georgia.ttf", 26)
    except Exception:
        font = ImageFont.load_default()
    L = 1000.0 / ft_per_px
    base = im.height if base_y is None else base_y
    x0, y0 = 70, base - 90
    d.rectangle([x0 - 20, y0 - 60, x0 + L + 50, y0 + 45], fill=(20, 16, 8, 170))
    d.rectangle([x0, y0, x0 + L / 2, y0 + 10], fill=(230, 215, 170, 255), outline=(0, 0, 0, 255))
    d.rectangle([x0 + L / 2, y0, x0 + L, y0 + 10], fill=(40, 30, 15, 255), outline=(230, 215, 170, 255))
    for ft in (0, 500, 1000):
        d.text((x0 + ft / 1000.0 * L - 10, y0 + 14), str(ft), fill=(235, 225, 190, 255), font=font)
    d.text((x0, y0 - 40), "1000 ft", fill=(235, 225, 190, 255), font=font)
    ax, ay = x0 + L + 120, base - 70
    d.polygon([(ax, ay - 70), (ax - 16, ay), (ax, ay - 16), (ax + 16, ay)], fill=(235, 225, 190, 255), outline=(0, 0, 0, 255))
    d.text((ax - 9, ay - 108), "N", fill=(235, 225, 190, 255), font=font)
    return np.asarray(im)[..., ::-1].copy()


def draw_checks(img, H, scale=1.0):
    """Draw field quads, circle outlines on an image (source if H is None, else mapped through H)."""
    import cv2
    out = img.copy()
    t = lambda pts: (np.asarray(pts, float) if H is None else apply_h(H, pts)) * scale
    for q in FIELDS.values():
        cv2.polylines(out, [t(q).astype(np.int32)], True, (0, 0, 255), 2, cv2.LINE_AA)
    for n, c in CIRCLES.items():
        cv2.polylines(out, [t(ellipse_pts(c, 90)).astype(np.int32)], True, (255, 255, 0), 2, cv2.LINE_AA)
    return out


# ---------------------------------------------------------------- orchestration
def build(args):
    import cv2
    img = cv2.imread(args.inp, cv2.IMREAD_COLOR)
    if img is None:
        sys.exit("cannot read " + args.inp)
    global SRC_W, SRC_H
    SRC_H, SRC_W = img.shape[:2]
    info = {}
    if args.tilt is not None:
        tilt, focal, roll, alpha = args.tilt, args.focal or 1450.0, args.roll or 0.0, 0.0
        info["fit"] = "manual"
    else:
        best = fit()
        tilt, focal, roll, alpha = best.x
        if args.focal:
            focal = args.focal
        info["fit_cost"] = float(best.cost)
        info["fit"] = "least_squares"
    Hg = camera_h(tilt, focal, roll)
    srcpts = [(0, args.crop_top), (SRC_W, args.crop_top), (SRC_W, SRC_H), (0, SRC_H)]
    if args.h_matrix:
        with open(args.h_matrix, encoding="utf-8") as f:
            data = json.load(f)
        Ho = np.array(data["H_src_to_out"] if isinstance(data, dict) else data, float)
        size = tuple(data.get("output_size", [args.width, args.width])) if isinstance(data, dict) else (args.width, args.width)
        s = None
    else:
        Ho, size, s = to_output(Hg, args.width, 0, srcpts, args.rotate)
    return img, Hg, Ho, size, s, (tilt, focal, roll, alpha), info


def cmd_fit(args):
    best = fit()
    tilt, focal, roll, alpha = best.x
    Hg = camera_h(tilt, focal, roll)
    print("tilt from nadir %.1f deg, focal %.0f px (fov_h %.0f deg), roll %.2f deg, field orientation %.1f deg"
          % (tilt, focal, 2 * math.degrees(math.atan(724 / focal)), roll, math.degrees(alpha)))
    print(json.dumps(quality(Hg), indent=1))
    prof = profile_tilt(best, np.arange(20, 76, 5))
    for t, c, f in prof:
        print("tilt %2d cost %.4f (focal %.0f)" % (t, c, f))


def cmd_warp(args):
    import cv2
    img, Hg, Ho, size, s, (tilt, focal, roll, alpha), info = build(args)
    clean = remove_furniture(img)
    plan = warp(clean, Ho, size)
    kg = scale_from_bar(Hg, mode="bar")
    kc = scale_from_bar(Hg, mode="centre")
    if s is None:  # custom matrix: measure px per ground unit from the matrix
        a = apply_h(Ho @ np.linalg.inv(Hg), [(0, 0), (1, 0)])
        s = float(np.linalg.norm(a[1] - a[0]))
    ft_per_px = kg / s
    _bp = apply_h(Ho, [(0, SRC_H), (SRC_W, SRC_H)])
    plan = draw_furniture(plan, ft_per_px, int(min(_bp[0][1], _bp[1][1])) - 40)
    cv2.imwrite(args.out, plan)
    # boundary overlay
    bounds_src = [(0, 0), (SRC_W, 0), (SRC_W, SRC_H), (0, SRC_H)]
    bpoly = apply_h(Ho, bounds_src)
    ov = plan.copy()
    cv2.polylines(ov, [bpoly.astype(np.int32)], True, (0, 255, 255), 4, cv2.LINE_AA)
    cv2.imwrite(os.path.splitext(args.out)[0] + "_bounds.png", ov)
    Hi = invert(Ho)
    old = apply_h(Ho, [OLD_ORIGIN])[0]
    q = quality(Hg)
    sidecar = {
        "description": "Plan-view (orthographic overhead) rectification of illustrator/out/foundry_screens/varrenmoor_original_map.png",
        "source": os.path.relpath(args.inp, os.path.join(HERE, "..", "..")).replace("\\", "/"),
        "source_size": [SRC_W, SRC_H],
        "output_size": [size[0], size[1]],
        "H_src_to_out": Ho.tolist(),
        "H_out_to_src": Hi.tolist(),
        "camera": {"tilt_from_nadir_deg": round(float(tilt), 2), "focal_px": round(float(focal), 1),
                   "roll_deg": round(float(roll), 3), "principal_point": [SRC_W / 2.0, SRC_H / 2.0],
                   "field_orientation_deg": round(math.degrees(alpha), 1), **info},
        "ft_per_px": {"x": round(ft_per_px, 4), "y": round(ft_per_px, 4), "note": "uniform after rectification; scale bar "
                      "(1000 ft = 130 px) assumed valid along x at its own image row (y=%d)" % BAR_ROW},
        "ft_per_px_if_bar_valid_at_image_centre": round(kc / s, 4),
        "old_uniform_ft_per_px": OLD_FT_PER_PX,
        "old_origin_map_px": list(OLD_ORIGIN),
        "old_origin_in_new_px": [round(float(old[0]), 2), round(float(old[1]), 2)],
        "original_image_boundary_in_output_px": bpoly.round(1).tolist(),
        "masked_furniture_src_rects": MASKS,
        "furniture": "compass, scale bar and title cartouche inpainted before warping; clean unwarped 1000 ft scale bar and north arrow drawn bottom-left",
        "quality": q,
        "convert": {
            "map_px_to_new_px": "p = H_src_to_out @ [x, y, 1]; new = (p0/p2, p1/p2), x,y = the same original-map px that varrenmoor_build.py uses",
            "new_px_to_map_px": "same with H_out_to_src",
            "new_px_to_feet": "dx_ft = (nx - old_origin_in_new_px[0]) * ft_per_px.x ; dy_ft(north up) = -(ny - old_origin_in_new_px[1]) * ft_per_px.y",
            "python": "import numpy as np; H=np.array(H_src_to_out); p=H@[x,y,1]; nx,ny=p[:2]/p[2]",
        },
    }
    with open(os.path.splitext(args.out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=1)
    print("wrote", args.out, size, "ft/px %.3f (centre reading %.3f)" % (ft_per_px, kc / s))
    print(json.dumps(q["circles"]))
    print("tilt %.1f focal %.0f roll %.2f" % (tilt, focal, roll))
    if args.compare:
        make_compare(img, plan, Ho, os.path.splitext(args.out)[0] + "_compare.png")


def make_compare(src, plan, Ho, path):
    import cv2
    h = 1000
    a = draw_checks(src, None)
    b = draw_checks(plan, Ho)
    a = cv2.resize(a, (int(a.shape[1] * h / a.shape[0]), h), interpolation=cv2.INTER_AREA)
    b = cv2.resize(b, (int(b.shape[1] * h / b.shape[0]), h), interpolation=cv2.INTER_AREA)
    cv2.putText(a, "BEFORE (oblique) - fields red, rings cyan", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(b, "AFTER (plan view)", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.imwrite(path, np.hstack([a, np.full((h, 8, 3), 255, np.uint8), b]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fit", "warp"], nargs="?", default="warp")
    ap.add_argument("--in", dest="inp", default=DEFAULT_IN)
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--tilt", type=float, help="camera tilt from straight down in degrees (skips the fit)")
    ap.add_argument("--focal", type=float, help="focal length in px (default fitted, or 1450 with --tilt)")
    ap.add_argument("--roll", type=float, help="image roll in degrees (with --tilt)")
    ap.add_argument("--h-matrix", help="JSON file with a 3x3 (or {'H_src_to_out':..., 'output_size':[w,h]}) matrix, overrides the camera model")
    ap.add_argument("--rotate", type=float, default=0.0, help="rotate the plan by this many degrees (ccw); default 0 keeps image-up as north")
    ap.add_argument("--width", type=int, default=2400, help="output width in px")
    ap.add_argument("--crop-top", type=float, default=0.0, help="ignore source rows above this y when framing the output")
    ap.add_argument("--compare", action="store_true", help="also write <out>_compare.png")
    args = ap.parse_args(argv)
    {"fit": cmd_fit, "warp": cmd_warp}[args.cmd](args)


if __name__ == "__main__":
    main()
