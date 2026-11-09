"""Sign maker: glTF models of street signs and hanging (tavern/shop) signs, and the installer for the 'Sign maker' Foundry macro (command `install-sign-macro`).

Design (see FOUNDRY_3D_CANVAS_NOTES.md section 12): a sign is ONE 3D Canvas tile whose glTF has plain wood / iron materials and one or more named LETTERING materials
(VB_sign_f, VB_sign_b = front/back face of a board; VB_sign_a<N>f / a<N>b = the two faces of fingerpost arm N). The lettering is painted onto a canvas by the macro in the
browser, uploaded as a PNG, and applied to those materials by the tile's own `onAnimation` flag script on every client (no module change, players see it). Editing the text
re-runs the macro on the selected tile, which redraws the PNG and updates the flags.

Model frame (Blender, metres, z up): the ORIGIN is the sign's anchor (post foot, or the wall contact point), z = 0 is its lowest point (the base the tile elevation lifts).
Boards face -Y (south, toward the default top-down camera). Wall plaques have the wall at y = 0 and project to -Y; hanging brackets have the wall at x = 0 and project to +X
(the board hangs in the XZ plane, faces -Y / +Y). The tile is placed so the model origin sits on the click point (autoCenter false).
"""
import argparse
import base64
import gzip
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.dirname(HERE)                       # illustrator/
PRESETS = os.path.join(ROOT, "presets", "signs")
MODELS_DIR = os.path.join(PRESETS, "models")
MACRO_ID = "macro:sign_maker"
MACRO_NAME = "Sign maker: street and hanging signs (editable text)"

import worldpack_mesh as wm                        # noqa: E402

M_WOOD, M_DARK, M_IRON = "sign_wood", "sign_oak_dark", "sign_iron"
PANELS_FACE = ("VB_sign_f", "VB_sign_b")

MATERIALS = {
    M_WOOD: {"mean_color": "#7a5a3a", "roughness": 0.85},
    M_DARK: {"mean_color": "#3d2a1a", "roughness": 0.8},
    M_IRON: {"mean_color": "#2b2b2e", "roughness": 0.55, "metallic": 0.35},
    "VB_sign_f": {"mean_color": "#7a5a3a", "roughness": 0.85},
    "VB_sign_b": {"mean_color": "#7a5a3a", "roughness": 0.85},
}
for _i in range(1, 5):
    for _s in "fb":
        MATERIALS[f"VB_sign_a{_i}{_s}"] = {"mean_color": "#7a5a3a", "roughness": 0.85}


# ------------------------------------------------------------------ geometry helpers (Blender frame)
def _uv(w, h, s):
    return [(0, h / s), (w / s, h / s), (w / s, 0), (0, 0)]


def box(b, mat, x0, x1, y0, y1, z0, z1, faces=None, s=0.6, full_uv=()):
    """Axis aligned box, every face its own 4 vertices, CCW seen from outside. faces: {'-y': mat, ...} overrides. full_uv: faces ('-y','+y') that get the 0..1 UV of the whole face
    (lettering boards); the back face (+y) is laid out as seen from behind so the picture reads correctly from both sides."""
    f = faces or {}
    X, Y, Z = x1 - x0, y1 - y0, z1 - z0
    spec = {
        "-y": ([(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)], X, Z),
        "+y": ([(x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1)], X, Z),
        "+x": ([(x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)], Y, Z),
        "-x": ([(x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1)], Y, Z),
        "+z": ([(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)], X, Y),
        "-z": ([(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)], X, Y),
    }
    for k, (pts, w, h) in spec.items():
        uv = [(0, 1), (1, 1), (1, 0), (0, 0)] if k in full_uv else _uv(w, h, s)
        b.face(f.get(k, mat), pts, uv)


def cyl_z(b, mat, cx, cy, r, z0, z1, n=10, cap=True, s=0.6):
    """Vertical cylinder (axis z)."""
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        p0, p1 = (cx + r * math.cos(a0), cy + r * math.sin(a0)), (cx + r * math.cos(a1), cy + r * math.sin(a1))
        b.face(mat, [(p0[0], p0[1], z0), (p1[0], p1[1], z0), (p1[0], p1[1], z1), (p0[0], p0[1], z1)], [(i / n, 1), ((i + 1) / n, 1), ((i + 1) / n, 0), (i / n, 0)])
    if cap:
        top = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n), z1) for i in range(n)]
        b.face(mat, top, [(0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 + 0.5 * math.sin(2 * math.pi * i / n)) for i in range(n)])


def cyl_y(b, mat, cx, cz, r, y0, y1, n=8):
    """Cylinder with the axis along y (nail heads, rivets, eyes) - a stub seen face on from -y; faces -y (cap at y0) and the side."""
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        p0, p1 = (cx + r * math.cos(a0), cz + r * math.sin(a0)), (cx + r * math.cos(a1), cz + r * math.sin(a1))
        b.face(mat, [(p0[0], y1, p0[1]), (p1[0], y1, p1[1]), (p1[0], y0, p1[1]), (p0[0], y0, p0[1])], [(0, 1), (1, 1), (1, 0), (0, 0)])
    cap = [(cx + r * math.cos(2 * math.pi * i / n), y0, cz + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    b.face(mat, cap[::-1], [(0.5 + 0.5 * math.cos(2 * math.pi * i / n), 0.5 - 0.5 * math.sin(2 * math.pi * i / n)) for i in range(n)][::-1])


def pyramid(b, mat, cx, cy, hw, z0, z1):
    """Square pyramid, base half width hw at z0, apex at z1."""
    c = [(cx - hw, cy - hw, z0), (cx + hw, cy - hw, z0), (cx + hw, cy + hw, z0), (cx - hw, cy + hw, z0)]
    ap = (cx, cy, z1)
    for i in range(4):
        b.face(mat, [c[i], c[(i + 1) % 4], ap], [(0, 1), (1, 1), (0.5, 0)])


def prism_xz(b, front, back, edge, poly, y0, y1):
    """Polygon in the XZ plane (CCW seen from -y, x right z up) extruded from y0 (front, faces -y) to y1 (back, faces +y). front/back get 0..1 UV of the bbox; the back is
    laid out as seen from behind. Returns nothing."""
    xs, zs = [p[0] for p in poly], [p[1] for p in poly]
    xa, xb, za, zb = min(xs), max(xs), min(zs), max(zs)
    uvf = [((x - xa) / (xb - xa), (zb - z) / (zb - za)) for x, z in poly]
    b.face(front, [(x, y0, z) for x, z in poly], uvf)
    b.face(back, [(x, y1, z) for x, z in poly][::-1], [((xb - x) / (xb - xa), (zb - z) / (zb - za)) for x, z in poly][::-1])
    n = len(poly)
    for i in range(n):
        (xa_, za_), (xb_, zb_) = poly[i], poly[(i + 1) % n]
        ln = math.hypot(xb_ - xa_, zb_ - za_)
        b.face(edge, [(xa_, y0, za_), (xb_, y0, zb_), (xb_, y1, zb_), (xa_, y1, za_)], [(0, 1), (ln / 0.6, 1), (ln / 0.6, 0), (0, 0)])


def bar_xz(b, mat, x0, z0, x1, z1, w, y0, y1):
    """Straight bar (rectangle of width w in the XZ plane, extruded y0..y1) from (x0, z0) to (x1, z1): braces and scrolls."""
    dx, dz = x1 - x0, z1 - z0
    ln = math.hypot(dx, dz)
    nx, nz = -dz / ln * w / 2, dx / ln * w / 2
    poly = [(x0 - nx, z0 - nz), (x1 - nx, z1 - nz), (x1 + nx, z1 + nz), (x0 + nx, z0 + nz)]
    area = sum(poly[i][0] * poly[(i + 1) % 4][1] - poly[(i + 1) % 4][0] * poly[i][1] for i in range(4))
    prism_xz(b, mat, mat, mat, poly if area > 0 else poly[::-1], y0, y1)


def frame(b, mat, x0, x1, z0, z1, y0, y1, w=0.022, over=0.006):
    """Four bars around a board that spans x0..x1, z0..z1 and y0..y1 (the frame sticks out `over` on every side and is as deep as the board plus 12 mm in front)."""
    yf0, yf1 = y0 - 0.012, y1 - 0.003
    box(b, mat, x0 - over, x1 + over, yf0, yf1, z0 - over, z0 + w)
    box(b, mat, x0 - over, x1 + over, yf0, yf1, z1 - w, z1 + over)
    box(b, mat, x0 - over, x0 + w, yf0, yf1, z0 + w, z1 - w)
    box(b, mat, x1 - w, x1 + over, yf0, yf1, z0 + w, z1 - w)


def nails(b, mat, pts, y, r=0.011):
    for x, z in pts:
        cyl_y(b, mat, x, z, r, y - 0.009, y + 0.002, 8)


def chain(b, mat, x, y, z_top, z_bot, link=0.045, bar=0.007):
    """Vertical chain of alternating flat links (rectangular loops) between z_top and z_bot."""
    n = max(2, int((z_top - z_bot) / (link * 0.78)))
    for i in range(n):
        zc = z_top - (i + 0.5) * (z_top - z_bot) / n
        h = link / 2
        if i % 2 == 0:       # loop in the XZ plane
            box(b, mat, x - 0.011, x + 0.011, y - bar / 2, y + bar / 2, zc - h, zc - h + bar)
            box(b, mat, x - 0.011, x + 0.011, y - bar / 2, y + bar / 2, zc + h - bar, zc + h)
            box(b, mat, x - 0.011, x - 0.011 + bar, y - bar / 2, y + bar / 2, zc - h + bar, zc + h - bar)
            box(b, mat, x + 0.011 - bar, x + 0.011, y - bar / 2, y + bar / 2, zc - h + bar, zc + h - bar)
        else:                # loop in the YZ plane
            box(b, mat, x - bar / 2, x + bar / 2, y - 0.011, y + 0.011, zc - h, zc - h + bar)
            box(b, mat, x - bar / 2, x + bar / 2, y - 0.011, y + 0.011, zc + h - bar, zc + h)
            box(b, mat, x - bar / 2, x + bar / 2, y - 0.011, y - 0.011 + bar, zc - h + bar, zc + h - bar)
            box(b, mat, x - bar / 2, x + bar / 2, y + 0.011 - bar, y + 0.011, zc - h + bar, zc + h - bar)


def post(b, x=0.0, y=0.0, hw=0.055, h=2.5, cap=True):
    box(b, M_DARK, x - hw, x + hw, y - hw, y + hw, 0.0, h, s=0.5)
    if cap:
        box(b, M_DARK, x - hw - 0.012, x + hw + 0.012, y - hw - 0.012, y + hw + 0.012, h, h + 0.03, s=0.5)
        pyramid(b, M_DARK, x, y, hw + 0.004, h + 0.03, h + 0.03 + hw * 1.2)


# ------------------------------------------------------------------ styles
def pan(w, h, m):
    """Lettering panel: the UV spans the whole w x h metre face; `safe` = fraction rectangle [x0, y0, x1, y1] that stays visible (frame / post / arrow tip excluded)."""
    return {"w": round(w, 4), "h": round(h, 4), "safe": [round(m / w, 4), round(m / h, 4), round(1 - m / w, 4), round(1 - m / h, 4)]}


# every builder returns (Builder list [(node name, Builder)], panels list). Panels are the lettering materials with their pixel aspect.
def build_street_post():
    b, d = wm.Builder(), wm.Builder()
    post(b, h=2.5)
    W, H, T = 0.76, 0.20, 0.035
    zc = 2.2
    yb0, yb1 = -0.060 - T, -0.060                          # 5 mm standoff: the board back never shares a plane with the post front
    box(b, M_WOOD, -W / 2, W / 2, yb0, yb1, zc - H / 2, zc + H / 2, faces={"-y": "VB_sign_f", "+y": "VB_sign_b"}, full_uv=("-y", "+y"))
    frame(b, M_DARK, -W / 2, W / 2, zc - H / 2, zc + H / 2, yb0, yb1)
    for z in (zc - 0.07, zc + 0.07):                      # iron spacer blocks between post and board
        box(b, M_IRON, -0.03, 0.03, -0.0605, -0.054, z - 0.012, z + 0.012)
    nails(b, M_IRON, [(sx * 0.055, zc + sz * (H / 2 - 0.011)) for sx in (-1, 1) for sz in (-1, 1)], yb0 - 0.012)      # four nails through the frame bars into the post
    return [("street_post", b)], {"panels": {"VB_sign_f": pan(W, H, 0.03), "VB_sign_b": pan(W, H, 0.03)}}


def build_street_wall():
    b = wm.Builder()
    W, H, T = 0.70, 0.24, 0.03
    zc = H / 2
    box(b, M_WOOD, -W / 2, W / 2, -T, 0.0, 0.0, H, faces={"-y": "VB_sign_f"}, full_uv=("-y",))
    frame(b, M_DARK, -W / 2, W / 2, 0.0, H, -T, 0.0, w=0.024, over=0.008)
    nails(b, M_IRON, [(-W / 2 + 0.035, zc), (W / 2 - 0.035, zc)], -T - 0.012, r=0.013)
    return [("street_wall", b)], {"panels": {"VB_sign_f": pan(W, H, 0.034)}}


def arm_poly(length, h, tip):
    """Arm outline in XZ: starts inside the post (x 0), pointed tip at +x."""
    return [(0.0, -h / 2), (length - tip, -h / 2), (length, 0.0), (length - tip, h / 2), (0.0, h / 2)]


def build_fingerpost(n):
    b = wm.Builder()
    post(b, hw=0.07, h=3.1)
    nodes = [("post", b)]
    L, H, T, TIP = 0.95, 0.20, 0.034, 0.10
    zs = [2.78, 2.50, 2.22, 1.94][:n]
    panels = {}
    for i, z in enumerate(zs, 1):
        a = wm.Builder()
        poly = [(x, zc + z) for x, zc in arm_poly(L, H, TIP)]
        prism_xz(a, f"VB_sign_a{i}f", f"VB_sign_a{i}b", M_WOOD, poly, -T / 2, T / 2)
        # iron collar where the arm leaves the post, and a nail
        nodes.append((f"arm{i}", a))
        al = wm.Builder()                                    # the same arm pointing to -x (shown instead of arm<i> when the arm points left; no mirrored geometry)
        prism_xz(al, f"VB_sign_a{i}f", f"VB_sign_a{i}b", M_WOOD, [(-x, z) for x, z in poly][::-1], -T / 2, T / 2)
        nodes.append((f"arm{i}L", al))
        for sd in "fb":
            pn = pan(L, H, 0.0)
            pn["safe"] = [round(0.115 / L, 4), 0.10, round(1 - 0.03 / L - 0.0, 4), 0.90] if sd == "f" else [round(0.03 / L, 4), 0.10, round(1 - 0.115 / L, 4), 0.90]
            panels[f"VB_sign_a{i}{sd}"] = pn
    c = wm.Builder()
    for z in zs:
        box(c, M_IRON, -0.082, 0.082, -0.082, 0.082, z - 0.016, z - 0.004)
    nodes.append(("collars", c))
    return nodes, {"panels": panels, "arms": n}


def build_hanging_bracket():
    """Wrought-iron bracket from a wall at x = 0 projecting to +x, board hangs from two chains (board faces -y / +y)."""
    b, br = wm.Builder(), wm.Builder()
    Z = 0.0                                               # arm height above the base (lowest point of the board)
    BW, BH, BT = 0.62, 0.46, 0.04                         # about 2 ft x 1.5 ft
    LEN = 0.95
    chain_len = 0.16
    zb0 = 0.0
    zb1 = BH
    za = zb1 + chain_len + 0.02                           # arm centre height
    # back plate on the wall and the bracket arm with a scroll brace
    box(br, M_IRON, -0.014, 0.0, -0.05, 0.05, za - 0.34, za + 0.07)
    box(br, M_IRON, 0.0, LEN, -0.014, 0.014, za - 0.014, za + 0.014)
    bar_xz(br, M_IRON, 0.015, za - 0.30, 0.52, za - 0.014, 0.022, -0.011, 0.011)             # diagonal brace from the plate to the arm
    box(br, M_IRON, LEN - 0.02, LEN + 0.03, -0.02, 0.02, za - 0.02, za + 0.02)                   # finial block
    pyramid(br, M_IRON, LEN + 0.03, 0.0, 0.02, za + 0.02, za + 0.07)
    nails(br, M_IRON, [(0.0, za - 0.28), (0.0, za + 0.02)], -0.05 + 0.02, r=0.012)
    bx0 = 0.16
    bx1 = bx0 + BW
    for cx in (bx0 + 0.07, bx1 - 0.07):
        chain(br, M_IRON, cx, 0.0, za - 0.014, zb1 - 0.005, link=0.05)
        box(br, M_IRON, cx - 0.009, cx + 0.009, -0.009, 0.009, za - 0.028, za - 0.014)
    yb0, yb1 = -BT / 2, BT / 2
    box(b, M_WOOD, bx0, bx1, yb0, yb1, zb0, zb1, faces={"-y": "VB_sign_f", "+y": "VB_sign_b"}, full_uv=("-y", "+y"))
    frame(b, M_DARK, bx0, bx1, zb0, zb1, yb0, yb1, w=0.026, over=0.007)
    for cx in (bx0 + 0.07, bx1 - 0.07):                   # eye screws in the top edge
        box(b, M_IRON, cx - 0.008, cx + 0.008, -0.008, 0.008, zb1 + 0.006, zb1 + 0.03)
    pan_ = pan(BW, BH, 0.034)
    return [("bracket", br), ("board", b)], {"panels": {"VB_sign_f": pan_, "VB_sign_b": pan_}}


def build_hanging_post():
    """Free standing post with a projecting arm (to +x) and a board on two chains; origin at the post foot."""
    b, br = wm.Builder(), wm.Builder()
    BW, BH, BT = 0.62, 0.46, 0.04
    LEN = 1.05
    zp = 2.55
    post(b, hw=0.065, h=zp + 0.1)
    za = zp - 0.04
    box(b, M_DARK, 0.0, LEN, -0.04, 0.04, za - 0.045, za + 0.045)                       # wooden arm
    bar_xz(b, M_DARK, 0.065, za - 0.55, 0.60, za - 0.045, 0.07, -0.025, 0.025)             # diagonal wooden brace
    chain_len = 0.18
    zb1 = za - 0.045 - chain_len
    zb0 = zb1 - BH
    bx0 = LEN - 0.05 - BW
    bx1 = bx0 + BW
    for cx in (bx0 + 0.07, bx1 - 0.07):
        chain(br, M_IRON, cx, 0.0, za - 0.045, zb1 - 0.005, link=0.05)
        box(br, M_IRON, cx - 0.012, cx + 0.012, -0.012, 0.012, za - 0.056, za - 0.045)
    box(br, M_IRON, 0.0, 0.0 + 0.02, -0.085, 0.085, za - 0.03, za + 0.03)              # strap plate on the post face
    yb0, yb1 = -BT / 2, BT / 2
    brd = wm.Builder()
    box(brd, M_WOOD, bx0, bx1, yb0, yb1, zb0, zb1, faces={"-y": "VB_sign_f", "+y": "VB_sign_b"}, full_uv=("-y", "+y"))
    frame(brd, M_DARK, bx0, bx1, zb0, zb1, yb0, yb1, w=0.026, over=0.007)
    for cx in (bx0 + 0.07, bx1 - 0.07):
        box(br, M_IRON, cx - 0.008, cx + 0.008, -0.008, 0.008, zb1 + 0.006, zb1 + 0.03)
    pan_ = pan(BW, BH, 0.034)
    # lowest point is the post foot (z = 0): shift nothing, the board sits at about 1.5 m
    return [("post", b), ("bracket", br), ("board", brd)], {"panels": {"VB_sign_f": pan_, "VB_sign_b": pan_}}


STYLES = {
    "street_post": {"label": "Street name board on a post", "kind": "street", "build": build_street_post, "mount": "ground"},
    "street_wall": {"label": "Street plaque on a wall", "kind": "street", "build": build_street_wall, "mount": "wall", "outward": [0, 1], "mount_ft": 7.0},
    "fingerpost_2": {"label": "Fingerpost, 2 arms", "kind": "street", "build": lambda: build_fingerpost(2), "mount": "ground"},
    "fingerpost_3": {"label": "Fingerpost, 3 arms", "kind": "street", "build": lambda: build_fingerpost(3), "mount": "ground"},
    "fingerpost_4": {"label": "Fingerpost, 4 arms", "kind": "street", "build": lambda: build_fingerpost(4), "mount": "ground"},
    "hanging_bracket": {"label": "Hanging sign on a wall bracket", "kind": "hanging", "build": build_hanging_bracket, "mount": "wall", "outward": [1, 0], "mount_ft": 7.0},
    "hanging_post": {"label": "Hanging sign on a roadside post", "kind": "hanging", "build": build_hanging_post, "mount": "ground"},
}


# ------------------------------------------------------------------ writing
def build_style(key):
    """-> (nodes [(name, Mesh, extras)], meta) with meta size_m [x, y, z] of the bounding box and the panels (pixel aspect source)."""
    nodes, meta = STYLES[key]["build"]()
    meshes = [(n, bld.build(), {}) for n, bld in nodes]
    zmin = float(np.min([m.V[:, 2].min() for _, m, _ in meshes]))
    if abs(zmin) > 1e-9:                                  # frame bars stick out below the board: lowest point of the whole model is exactly z = 0
        meshes = [(n, m.translated((0, 0, -zmin)), e) for n, m, e in meshes]
    lo = np.min([m.V.min(0) for _, m, _ in meshes], 0)
    hi = np.max([m.V.max(0) for _, m, _ in meshes], 0)
    meta = dict(meta)
    meta.update({"bbox_min": [round(float(v), 4) for v in lo], "bbox_max": [round(float(v), 4) for v in hi], "size_m": [round(float(v), 4) for v in hi - lo]})
    used = set()
    for _, m, _ in meshes:
        used |= set(m.subs)
    return meshes, meta, used


def write_style(key, path):
    meshes, meta, used = build_style(key)
    wm.write_glb(path, meshes, {k: v for k, v in MATERIALS.items() if k in used}, textures="none", extras={"varrenmoorSign": key})
    return meta


def lettering_texture_size(w_m, h_m, long_px=1024, min_px=128):
    """Pixel size of a lettering texture for a panel w_m x h_m metres (long side long_px, power-of-two friendly rounding to a multiple of 8)."""
    ar = w_m / h_m
    if ar >= 1:
        w, h = long_px, long_px / ar
    else:
        w, h = long_px * ar, long_px
    r8 = lambda v: max(min_px, int(round(v / 8.0)) * 8)
    return r8(w), r8(h)


_HASH = {}


def glb_bytes(key):
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".glb")
    os.close(fd)
    try:
        write_style(key, tmp)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.remove(tmp)


def model_hash(key):
    """8 hex chars of the GLB content: the file name changes with the model, so the macro never reuses a stale upload."""
    import hashlib
    if key not in _HASH:
        _HASH[key] = hashlib.sha1(glb_bytes(key)).hexdigest()[:8]
    return _HASH[key]


def style_manifest():
    """{style: {label, kind, mount, size_m, panels{mat: [w_m,h_m, w_px, h_px]}, bbox...}} built from the real geometry; the macro reads this."""
    out = {}
    for k, st in STYLES.items():
        _, meta, _ = build_style(k)
        pan = {mat: {**pn, "px": list(lettering_texture_size(pn["w"], pn["h"]))} for mat, pn in meta["panels"].items()}
        out[k] = {"label": st["label"], "kind": st["kind"], "mount": st["mount"], "file": f"{k}_{model_hash(k)}.glb", "size_m": meta["size_m"], "bbox_min": meta["bbox_min"],
                  "bbox_max": meta["bbox_max"], "panels": pan, "arms": meta.get("arms", 0), "outward": st.get("outward"), "mount_ft": st.get("mount_ft", 0.0)}
    return out


def write_all(out_dir=MODELS_DIR):
    os.makedirs(out_dir, exist_ok=True)
    man = style_manifest()
    for k in STYLES:
        write_style(k, os.path.join(out_dir, man[k]["file"]))
    return man


# ------------------------------------------------------------------ macro install
MACRO_JS = os.path.join(ROOT, "foundry_macros", "sign_maker.js")
TEX_SRC = {"wood": "archive_oak", "dark": "dark_antique_oak", "iron": "aged_wrought_iron"}
FOUNDRY3D_TEX = os.path.join(os.path.dirname(ROOT), "foundry-3d", "textures")


def texture_bundle(size=384, quality=72):
    """{name: base64 jpeg} of the three shared sign textures (wood, dark wood, iron), downsized so the macro stays small."""
    from PIL import Image
    import io
    out = {}
    for name, src in TEX_SRC.items():
        p = os.path.join(PRESETS, "textures", f"{name}.jpg")
        if os.path.exists(p):
            with open(p, "rb") as f:
                out[name] = base64.b64encode(f.read()).decode()
            continue
        im = Image.open(os.path.join(FOUNDRY3D_TEX, src + ".jpg")).convert("RGB").resize((size, size), Image.LANCZOS)
        bio = io.BytesIO()
        im.save(bio, "JPEG", quality=quality, optimize=True)
        out[name] = base64.b64encode(bio.getvalue()).decode()
    return out


def load_styles_json():
    with open(os.path.join(PRESETS, "styles.json"), encoding="utf-8") as f:
        return json.load(f)


def macro_source():
    """The macro text with the data block (style manifest, GLBs, textures, presets) substituted for the placeholder."""
    import tempfile
    tmp = tempfile.mkdtemp(prefix="vbsigns_")
    man = write_all(tmp)
    models = {}
    for k, v in man.items():
        with open(os.path.join(tmp, v["file"]), "rb") as f:
            models[k] = base64.b64encode(gzip.compress(f.read(), 9, mtime=0)).decode()          # gzip + base64: the macro text stays small (the macro gunzips with DecompressionStream)
    data = {"version": 1, "styles": man, "models": models, "textures": texture_bundle(), "presets": load_styles_json()}
    with open(MACRO_JS, encoding="utf-8") as f:
        src = f.read()
    marker = "/*__VB_SIGN_DATA__*/null"
    if marker not in src:
        raise RuntimeError("sign_maker.js has no data placeholder " + marker)
    return src.replace(marker, json.dumps(data, separators=(",", ":")))


def macro_doc():
    return {"name": MACRO_NAME, "type": "script", "img": "icons/svg/sign.svg", "scope": "global", "command": macro_source()}


def cmd_install(br, a):
    import foundry_push as fp
    d = macro_doc()
    if a.dry_run:
        return {"ok": True, "dry_run": True, "macros": [MACRO_ID], "bytes": len(d["command"])}
    fp.require_module(br)
    r = br.call("upsert_by_flag", documentName="Macro", id=MACRO_ID, data=d)
    return {"ok": True, "macros": [r.get("uuid")], "bytes": len(d["command"])}


def parser():
    ap = argparse.ArgumentParser(prog="foundry_push.py")
    ap.add_argument("cmd", choices=["install-sign-macro", "write-sign-models"])
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", help="write-sign-models: output folder (default presets/signs/models)")
    return ap


def main(argv=None, bridge=None):
    import foundry_push as fp
    a = parser().parse_args(argv)
    try:
        if a.cmd == "write-sign-models":
            man = write_all(a.out or MODELS_DIR)
            res = {"ok": True, "styles": {k: v["size_m"] for k, v in man.items()}}
        else:
            res = cmd_install(bridge or fp.PsBridge(), a)
    except fp.NeedsModule as e:
        res = {"ok": False, "error": str(e), "needs_module": True}
    except fp.PushError as e:
        res = {"ok": False, "error": str(e)}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
