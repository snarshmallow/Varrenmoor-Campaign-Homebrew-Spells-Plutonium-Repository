"""Painted foliage atlas v2 (leaf-spray cards with alpha, bark, rock, impostors).

Every tile is drawn 4x supersampled with PIL/numpy. Leaf sprays are a twig skeleton with individually painted leaves (dark edge, mid body,
lit half, midrib + veins, per-leaf hue/value variation, a few backlit yellow leaves) and a baked ambient-occlusion gradient (leaves nearer the
stem root are darker). Seasons: summer, autumn, winter (bare twigs + a few dead leaves). Alpha stays anti-aliased (the glTF material is
alphaMode MASK, cutoff 0.5) and colour is bled into transparent texels so mip levels do not fringe.
"""
import math
import numpy as np

SS = 4
SEASONS = ("summer", "autumn", "winter")


def _rot(pts, a, ox, oy):
    c, s = math.cos(a), math.sin(a)
    return [(ox + x * c - y * s, oy + x * s + y * c) for x, y in pts]


def _clamp(c):
    return tuple(int(max(0, min(255, v))) for v in c)


def _mul(c, k):
    return _clamp([v * k for v in c])


def _mix(a, b, t):
    return _clamp([a[i] * (1 - t) + b[i] * t for i in range(3)])


# ---- leaf outlines in local coords: x along the leaf (0 at petiole .. L), y across
def _profile_pts(fn, L, W, n=14, serr=0.0, rng=None):
    top, bot = [], []
    for i in range(n + 1):
        t = i / n
        w = fn(t) * W / 2
        if serr and 0 < i < n:
            w *= 1 + serr * (1 if i % 2 else -0.6)
        top.append((t * L, w))
        bot.append((t * L, -w))
    return top + bot[::-1][1:-1] if False else top + bot[::-1]


PROFILES = {
    "oak": lambda t: math.sin(math.pi * t ** 0.85) * (0.78 + 0.22 * math.cos(2 * math.pi * 3.2 * t)),
    "beech": lambda t: math.sin(math.pi * t ** 0.8) ** 0.85 * (1 - 0.35 * t ** 4),
    "birch": lambda t: (math.sin(math.pi * min(1, t * 1.05) ** 0.75) ** 0.8) * (1 - 0.6 * t ** 3),
    "willow": lambda t: math.sin(math.pi * t ** 0.9) ** 0.9,
    "lance": lambda t: math.sin(math.pi * t ** 0.9) ** 0.9,
    "round": lambda t: math.sin(math.pi * t ** 0.9) ** 0.7,
    "ovate": lambda t: math.sin(math.pi * t ** 0.7) ** 0.8,
}


def _star_pts(lobes, L, rng, sharp=0.5, n=60):
    """Palmate (maple) / lobed (ivy) outline, petiole at origin pointing +x."""
    pts = []
    for i in range(n):
        th = -math.pi + 2 * math.pi * i / n
        lobe = abs(math.cos(lobes * th / 2 * 1.0)) ** (1.5 / sharp)
        r = L * (0.38 + 0.62 * lobe) * (0.5 if abs(th) > 2.6 else 1.0)
        pts.append((L * 0.45 + r * math.cos(th) * 0.55, r * math.sin(th) * 0.55))
    return pts


class Painter:
    def __init__(self, size, rng, season="summer"):
        from PIL import Image, ImageDraw
        self.S = size
        self.K = SS
        self.img = Image.new("RGBA", (size * SS, size * SS), (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)
        self.rng = rng
        self.season = season

    def P(self, v):
        return v * self.K

    def line(self, p0, p1, col, w):
        self.d.line([p0[0] * self.K, p0[1] * self.K, p1[0] * self.K, p1[1] * self.K], fill=col + (255,), width=max(1, int(w * self.K)))

    def poly(self, pts, col):
        self.d.polygon([(x * self.K, y * self.K) for x, y in pts], fill=col + (255,))

    def leaf(self, x, y, ang, L, W, prof, base, backlit=False, serr=0.0, star=0):
        """Painted leaf with petiole at (x, y) pointing along `ang`."""
        rng = self.rng
        if star:
            pts0 = _star_pts(star, L, rng)
        else:
            pts0 = _profile_pts(PROFILES[prof], L, W, serr=serr)
        cx = np.mean([p[0] for p in pts0])
        edge = _mul(base, 0.55)
        mid = base
        lit = _mix(base, (235, 235, 120), 0.45) if backlit else _mul(base, 1.28)

        def scaled(k, sy_off=0.0):
            return [(cx + (px - cx) * k, py * k + sy_off) for px, py in pts0]
        self.poly(_rot(pts0, ang, x, y), edge)
        self.poly(_rot(scaled(0.88), ang, x, y), _mix(edge, mid, 0.6))
        self.poly(_rot(scaled(0.74), ang, x, y), mid)
        half = [(px, py) for px, py in scaled(0.6, sy_off=-W * 0.06 if W else 0) if py <= W * 0.05]
        if len(half) > 2:
            self.poly(_rot(half, ang, x, y), lit)
        # midrib + veins
        rib = _mix(lit, (240, 240, 200), 0.25)
        a0 = _rot([(0, 0)], ang, x, y)[0]
        a1 = _rot([(L * 0.95, 0)], ang, x, y)[0]
        self.line(a0, a1, rib, 0.55)
        if not star and L * SS > 60:
            for t in (0.25, 0.42, 0.6, 0.76):
                for sg in (-1, 1):
                    p0 = _rot([(L * t, 0)], ang, x, y)[0]
                    p1 = _rot([(L * (t + 0.14), sg * W * PROFILES[prof](t + 0.1) * 0.40)], ang, x, y)[0]
                    self.line(p0, p1, _mix(mid, rib, 0.45), 0.35)
        elif star:
            for k in (-2, -1, 0, 1, 2):
                p1 = _rot([(L * 0.45 + math.cos(k * 0.55) * L * 0.55, math.sin(k * 0.55) * L * 0.55)], ang, x, y)[0]
                self.line(_rot([(L * 0.45, 0)], ang, x, y)[0], p1, _mix(mid, rib, 0.4), 0.4)

    def finish(self, ao=0.30, fringe=True):
        from PIL import Image, ImageFilter
        im = self.img.resize((self.S, self.S), Image.LANCZOS)
        a = np.asarray(im).astype(float)
        if ao:                                           # baked AO: darker toward the bottom (stem root) of the card
            a[:, :, :3] *= (1.0 - ao * np.linspace(0, 1, self.S) ** 1.5)[:, None, None]
        al = a[:, :, 3] / 255.0
        if fringe:                                       # bleed opaque colour into transparent texels (no dark fringe under mip/linear filtering)
            pm = Image.fromarray(np.dstack([a[:, :, :3] * al[:, :, None], al * 255]).astype("uint8"), "RGBA")
            bl = np.asarray(pm.filter(ImageFilter.GaussianBlur(3))).astype(float)
            ba = np.maximum(bl[:, :, 3:4] / 255.0, 1e-3)
            bleed = bl[:, :, :3] / ba
            rgb = np.where(al[:, :, None] > 0.98, a[:, :, :3], np.where(al[:, :, None] > 0.02, a[:, :, :3], bleed))
            lo = al < 0.5
            rgb[lo] = bleed[lo]
        else:
            rgb = a[:, :, :3]
        return np.dstack([np.clip(rgb, 0, 255), a[:, :, 3]]).astype("uint8")


# ---- leaf spray (broadleaf) -----------------------------------------------------------------------------------------------
LEAF_SPEC = {
    # name: (profile or star, leaf length px, width px, base colours, serration, leaf count, twig length frac)
    "leaf_oak": dict(prof="oak", L=40, W=22, cols=[(70, 112, 40), (88, 128, 48), (60, 96, 38)], serr=0.0, n=46, autumn=[(176, 108, 34), (150, 70, 28), (196, 150, 40)]),
    "leaf_beech": dict(prof="beech", L=38, W=21, cols=[(86, 128, 50), (100, 140, 56), (70, 110, 44)], serr=0.0, n=52, autumn=[(190, 120, 40), (160, 90, 30), (210, 160, 50)]),
    "leaf_birch": dict(prof="birch", L=28, W=20, cols=[(120, 160, 56), (140, 176, 62), (102, 144, 50)], serr=0.09, n=70, autumn=[(214, 178, 40), (200, 150, 32), (226, 200, 70)]),
    "leaf_maple": dict(prof="oak", L=44, W=44, cols=[(78, 122, 40), (96, 138, 46), (66, 106, 36)], serr=0.0, n=30, star=5, autumn=[(200, 60, 28), (220, 110, 30), (180, 40, 26)]),
    "leaf_rowan": dict(prof="lance", L=22, W=8, cols=[(100, 142, 60), (116, 156, 66), (84, 126, 52)], serr=0.12, n=0, autumn=[(210, 90, 34), (190, 60, 30), (220, 140, 40)], compound=True),
    "bush": dict(prof="round", L=22, W=15, cols=[(76, 120, 48), (92, 136, 54), (60, 100, 40)], serr=0.0, n=90, autumn=[(170, 120, 40), (130, 130, 44), (190, 100, 36)]),
    "ivy": dict(prof="round", L=34, W=34, cols=[(48, 92, 44), (60, 108, 50), (40, 80, 38)], serr=0.0, n=40, star=3, autumn=[(120, 70, 36), (96, 90, 40), (140, 60, 34)]),
}


def _season_cols(spec, season, rng):
    if season == "autumn":
        return spec["autumn"] + spec["cols"][:1] * 0
    return spec["cols"]


def paint_leaf_spray(S, rng, name, season="summer", drooping=False):
    spec = LEAF_SPEC[name]
    pt = Painter(S, rng, season)
    cols = _season_cols(spec, season, rng)
    keep = {"summer": 1.0, "autumn": 0.9, "winter": 0.05}[season]
    twigcol = (66, 50, 38)
    twigs = []                                           # (p0, p1, width, depth)

    def twig(x, y, ang, ln, depth, w):
        pts = [(x, y)]
        a = ang
        for i in range(5):
            a += rng.uniform(-0.12, 0.12) + (0.05 if drooping else 0)
            x += math.sin(a) * ln / 5
            y -= math.cos(a) * ln / 5
            pts.append((x, y))
        twigs.append((pts, w, depth))
        if depth < 2:
            for k in range(2 + (depth == 0) * 2):
                t = rng.uniform(0.35, 0.95)
                j = min(4, int(t * 5))
                bx, by = pts[j]
                side = 1 if (k % 2 == 0) else -1
                twig(bx, by, a + side * rng.uniform(0.5, 0.95), ln * rng.uniform(0.4, 0.62), depth + 1, w * 0.6)
        return pts
    spread = 0.0 if not drooping else 0.0
    twig(S / 2, S - 2, 0.0 + rng.uniform(-0.1, 0.1), S * 0.72, 0, 2.4)
    for pts, w, depth in twigs:
        for i in range(len(pts) - 1):
            pt.line(pts[i], pts[i + 1], twigcol if depth else _mul(twigcol, 0.9), w)
    # leaf anchors: along every twig (more near the tips) and at tips
    anchors = []
    for pts, w, depth in twigs:
        for i in range(len(pts) - 1):
            for k in range(3 if depth else 1):
                t = rng.random()
                x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * t
                y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * t
                a = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
                anchors.append((x, y, a, i / 5 + depth))
        anchors.append((pts[-1][0], pts[-1][1], math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0]), 1.2 + depth))
    idx = rng.permutation(len(anchors))
    n = int((spec["n"] or 28) * 1.6)
    sel = [anchors[i] for i in idx[:max(n, 12)]]
    sel.sort(key=lambda t: -t[1])                        # base first, tips drawn last (on top)
    for (x, y, a, _) in sel:
        if rng.random() > keep:
            continue
        sc = rng.uniform(0.85, 1.3) * (0.85 + 0.35 * (1 - y / S))
        base = cols[int(rng.integers(0, len(cols)))]
        if season == "autumn" and rng.random() < 0.12:
            base = spec["cols"][0]                      # a few late green leaves
        base = _mul(base, rng.uniform(0.82, 1.18))
        base = _clamp([base[0] + rng.uniform(-8, 8), base[1] + rng.uniform(-6, 10), base[2] + rng.uniform(-8, 8)])
        if season == "winter":
            base = (110, 84, 52)
        la = a + rng.choice([-1, 1]) * rng.uniform(0.35, 1.2) if not spec.get("star") else rng.uniform(0, 2 * math.pi)
        if spec.get("compound"):                          # rowan: pinnate leaf = rachis with paired leaflets
            for k in range(6):
                for sg in (-1, 1):
                    px, py = x + math.cos(la) * k * 5, y + math.sin(la) * k * 5
                    pt.leaf(px, py, la + sg * 1.15, spec["L"] * sc * (1 - k * 0.04), spec["W"] * sc, "lance", base, backlit=rng.random() < 0.2, serr=0.1)
            pt.leaf(x + math.cos(la) * 30, y + math.sin(la) * 30, la, spec["L"] * sc, spec["W"] * sc, "lance", base)
            continue
        pt.leaf(x, y, la, spec["L"] * sc, spec["W"] * sc, spec["prof"], base, backlit=rng.random() < 0.18, serr=spec["serr"], star=spec.get("star", 0))
    return pt.finish(ao=0.28)


def paint_willow(S, rng, season="summer"):
    """Tile of hanging strands: long narrow leaves along drooping twigs, attached at the top."""
    pt = Painter(S, rng, season)
    keep = {"summer": 1.0, "autumn": 0.9, "winter": 0.04}[season]
    n = 11
    for k in range(n):
        x0 = (k + 0.5) * S / n + rng.uniform(-4, 4)
        ln = rng.uniform(0.62, 0.97) * S
        pts = [(x0, 2)]
        x = x0
        for i in range(1, 9):
            x += rng.uniform(-3, 3) + math.sin(i * 0.8 + k) * 1.6
            pts.append((x, 2 + ln * i / 8))
        for i in range(8):
            pt.line(pts[i], pts[i + 1], (86, 78, 44), 1.6)
        for i in range(1, 9):
            for sg in (-1, 1):
                if rng.random() > keep:
                    continue
                c = _mul(((128, 164, 70) if season != "autumn" else (210, 176, 60)), rng.uniform(0.8, 1.15))
                if season == "winter":
                    c = (130, 110, 60)
                pt.leaf(pts[i][0], pts[i][1], math.pi / 2 + sg * rng.uniform(0.35, 0.8), rng.uniform(26, 38), rng.uniform(5.5, 8), "willow", c, backlit=rng.random() < 0.2)
    return pt.finish(ao=0.12)


# ---- needles --------------------------------------------------------------------------------------------------------------
def paint_spruce(S, rng, season="summer", dark=True, juniper=False):
    pt = Painter(S, rng, season)
    base = (36, 74, 52) if dark else (56, 98, 62)
    if juniper:
        base = (66, 100, 84)
    x0, y0 = S / 2, S - 2
    stem = []
    for i in range(0, 9):
        t = i / 8
        stem.append((x0 + math.sin(t * 2.2) * 6 * rng.choice([-1, 1]) * 0 + (t - 0.0) * rng.uniform(-3, 3), y0 - t * S * 0.94))
    twigs = [(stem, 2.0)]
    for i in range(1, 9):
        t = i / 8
        for sg in (-1, 1):
            ln = S * 0.5 * (1 - t * 0.78) * rng.uniform(0.85, 1.1)
            bx, by = stem[i]
            pts = [(bx, by)]
            x, y = bx, by
            a = sg * (1.25 - 0.15 * t) + rng.uniform(-0.1, 0.1)
            for j in range(4):
                a += sg * 0.06                      # droop
                x += math.sin(a) * ln / 4
                y -= math.cos(a) * ln / 4 * (0.45 if a else 1) * 1.0 - 0.0
                y += ln / 4 * 0.38 * (j + 1) / 4           # droop downwards
                pts.append((x, y))
            twigs.append((pts, 1.3))
            for j in (1, 2, 3):                    # secondary twigs
                if rng.random() < 0.8:
                    sx, sy = pts[j]
                    ln2 = ln * 0.32
                    tip = (sx + math.sin(a + sg * -0.9) * ln2, sy - math.cos(a + sg * -0.9) * ln2 * 0.4 + ln2 * 0.25)
                    twigs.append(([(sx, sy), tip], 0.9))
    for pts, w in twigs:
        for i in range(len(pts) - 1):
            pt.line(pts[i], pts[i + 1], (62, 46, 34), w)
    for pts, w in twigs[1:]:
        for i in range(len(pts) - 1):
            (ax, ay), (bx, by) = pts[i], pts[i + 1]
            seg = math.hypot(bx - ax, by - ay)
            ang = math.atan2(by - ay, bx - ax)
            m = max(3, int(seg / (0.9 if not juniper else 2.4)))
            for k in range(m):
                t = (k + rng.random()) / m
                px, py = ax + (bx - ax) * t, ay + (by - ay) * t
                for sg in (-1, 1):
                    la = ang + sg * rng.uniform(0.9, 1.5)
                    nl = rng.uniform(10, 17) * (1 if not juniper else 0.7)
                    c = _mul(base, rng.uniform(0.75, 1.3))
                    if season == "winter" and not dark:
                        c = _mul(c, 0.9)
                    q = (px + math.cos(la) * nl, py + math.sin(la) * nl)
                    pt.line((px, py), q, c, 1.25 if not juniper else 1.8)
    if season == "autumn":
        pass
    return pt.finish(ao=0.34)


def paint_pine(S, rng, season="summer"):
    pt = Painter(S, rng, season)
    twigs = []
    for k in range(5):
        a = rng.uniform(-0.5, 0.5) + (k - 2) * 0.35
        x, y = S / 2, S - 2
        pts = [(x, y)]
        ln = S * rng.uniform(0.45, 0.8)
        for i in range(5):
            x += math.sin(a) * ln / 5
            y -= math.cos(a) * ln / 5
            a += rng.uniform(-0.1, 0.1)
            pts.append((x, y))
        twigs.append(pts)
        for i in range(len(pts) - 1):
            pt.line(pts[i], pts[i + 1], (92, 62, 40), 2.2)
    for pts in twigs:
        for i in range(2, 6):
            tx, ty = pts[i]
            for k in range(14):                     # fan of long needle pairs at each node
                la = -math.pi / 2 + rng.uniform(-1.3, 1.3)
                nl = rng.uniform(26, 44)
                c = _mul((66, 106, 62), rng.uniform(0.8, 1.25))
                q = (tx + math.cos(la) * nl, ty + math.sin(la) * nl * 0.9)
                pt.line((tx, ty), q, c, 1.0)
                pt.line((tx + 1, ty), (q[0] + 2, q[1]), _mul(c, 1.15), 0.8)
    return pt.finish(ao=0.3)


# ---- ground cover -----------------------------------------------------------------------------------------------------------
def paint_grass(S, rng, season="summer", reed=False):
    pt = Painter(S, rng, season)
    n = 26 if not reed else 14
    for _ in range(n):
        bx = rng.uniform(14, S - 14)
        h = rng.uniform(0.45, 0.98) * S if not reed else rng.uniform(0.6, 0.98) * S
        lean = rng.uniform(-0.3, 0.3) * h
        w = rng.uniform(3, 5.5) if not reed else rng.uniform(2.5, 4)
        dark = (46, 88, 34) if season != "autumn" else (108, 100, 40)
        tip = (136, 176, 66) if season != "autumn" else (196, 170, 80)
        if season == "winter":
            dark, tip = (92, 82, 56), (150, 134, 96)
        steps = 8
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            def at(t):
                return (bx + lean * t * t, S - 1 - h * t)
            c = _mix(dark, tip, t0 ** 0.8)
            c = _mul(c, rng.uniform(0.95, 1.05))
            a0, a1 = at(t0), at(t1)
            w0, w1 = w * (1 - t0), w * (1 - t1) + 0.3
            pt.poly([(a0[0] - w0, a0[1]), (a0[0] + w0, a0[1]), (a1[0] + w1, a1[1]), (a1[0] - w1, a1[1])], c)
    if reed:
        for cx in (S * 0.38, S * 0.64):
            ytop = S * rng.uniform(0.08, 0.2)
            pt.line((cx, S - 1), (cx + 2, ytop + 30), (112, 128, 64), 2.0)
            pt.poly([(cx - 4, ytop + 30), (cx + 4, ytop + 30), (cx + 5, ytop + 8), (cx, ytop), (cx - 5, ytop + 8)], (92, 56, 34))
    return pt.finish(ao=0.22)


def paint_fern(S, rng, season="summer"):
    pt = Painter(S, rng, season)
    for fr in range(3):
        ang0 = (fr - 1) * 0.55 + rng.uniform(-0.1, 0.1)
        x, y = S / 2, S - 2
        ln = S * rng.uniform(0.7, 0.95)
        rach = []
        a = ang0
        for i in range(0, 13):
            rach.append((x, y))
            a += 0.05 * (1 if ang0 >= 0 else -1) + rng.uniform(-0.02, 0.02)
            x += math.sin(a) * ln / 12
            y -= math.cos(a) * ln / 12
        for i in range(len(rach) - 1):
            pt.line(rach[i], rach[i + 1], (60, 88, 38), 1.7)
        for i in range(2, 13):
            t = i / 12
            L = S * 0.30 * math.sin(math.pi * min(1, t * 0.95 + 0.05)) ** 0.8 + 6
            for sg in (-1, 1):
                c = _mul((52, 112, 44) if season != "autumn" else (150, 120, 48), rng.uniform(0.8, 1.2))
                pt.leaf(rach[i][0], rach[i][1], math.pi / 2 * -1 + ang0 * 0 + sg * 1.2 + math.sin(i) * 0.05 - math.pi / 2 + math.pi / 2, L, 9 - t * 3, "lance", c, backlit=rng.random() < 0.15, serr=0.1)
    return pt.finish(ao=0.25)


def paint_flower(S, rng, season="summer"):
    pt = Painter(S, rng, season)
    for k, col in enumerate([(216, 80, 150), (244, 218, 80), (240, 240, 240), (140, 110, 220)]):
        cx = S * (0.16 + k * 0.22) + rng.uniform(-6, 6)
        top = rng.uniform(0.12, 0.45) * S
        pt.line((cx, S - 1), (cx + rng.uniform(-6, 6), top), (60, 108, 44), 2.2)
        for sg in (-1, 1):
            pt.leaf(cx, S - rng.uniform(30, 70), -math.pi / 2 + sg * 1.0, 26, 9, "lance", (58, 112, 46))
        if season == "winter":
            continue
        for p in range(6):
            a = p * math.pi / 3
            pt.leaf(cx, top, a, 16, 9, "round", _mul(col, rng.uniform(0.9, 1.1)))
        pt.poly([(cx - 3, top - 3), (cx + 3, top - 3), (cx + 3, top + 3), (cx - 3, top + 3)], (210, 160, 40))
    return pt.finish(ao=0.2)


def paint_twig(S, rng):
    """Bare winter-style branch spray for bare trees."""
    return paint_leaf_spray(S, rng, "leaf_oak", "winter")


# ---- opaque tiles ---------------------------------------------------------------------------------------------------------
def _noise2(rng, h, w, kx, ky):
    g = rng.random((ky + 1, kx + 1))
    from PIL import Image
    im = Image.fromarray((g * 255).astype("uint8")).resize((w, h), Image.BICUBIC)
    return np.asarray(im).astype(float) / 255


def paint_bark(S, rng, kind="bark"):
    """Vertical furrowed bark: ridges stretched along v. kind: bark | bark_birch | bark_dark | core (dense leaf mass)."""
    y, x = np.mgrid[0:S, 0:S] / S
    n1 = _noise2(rng, S, S, 10, 3)
    n2 = _noise2(rng, S, S, 28, 7)
    n3 = _noise2(rng, S, S, 64, 40)
    if kind == "core":
        n = 0.5 * _noise2(rng, S, S, 12, 12) + 0.35 * _noise2(rng, S, S, 36, 36) + 0.15 * n3
        base = np.array([40, 74, 36], float)
        img = base[None, None, :] * (0.55 + 0.9 * n[:, :, None])
        return np.dstack([np.clip(img, 0, 255), np.full((S, S), 255.0)]).astype("uint8")
    ridge = np.abs(np.sin(2 * math.pi * (x * 11 + n1 * 0.6 + n2 * 0.25)))
    ridge = ridge ** 0.7
    if kind == "bark_birch":
        base = np.array([222, 218, 206], float)
        img = base[None, None, :] * (0.88 + 0.12 * n2[:, :, None]) * (0.96 + 0.06 * n3[:, :, None])
        for _ in range(26):                        # dark lenticel scars / bands
            yy = int(rng.integers(0, S))
            xx = int(rng.integers(0, S))
            ww = int(rng.integers(14, 70))
            hh = int(rng.integers(2, 6))
            sc = 0.45 + 0.3 * rng.random()
            img[yy:yy + hh, xx:xx + ww] *= sc
            img[yy + hh:yy + hh + 1, xx:xx + ww] *= 0.7
        img[S - 40:S] *= np.linspace(1, 0.55, 40)[:, None, None]      # dark rough base of trunk
        img *= (0.94 + 0.06 * ridge[:, :, None])
    else:
        base = np.array([88, 70, 54] if kind == "bark" else [62, 50, 40], float)
        fur = 0.45 + 0.75 * (ridge * 0.6 + n2 * 0.4)
        img = base[None, None, :] * fur[:, :, None] * (0.85 + 0.3 * n3[:, :, None])
        crack = (ridge < 0.12).astype(float)
        img *= (1 - 0.6 * crack)[:, :, None]
        img[:, :, 1] *= 0.97
        img[:, :, 2] *= 0.93 + 0.1 * n1
    return np.dstack([np.clip(img, 0, 255), np.full((S, S), 255.0)]).astype("uint8")


def paint_rock(S, rng):
    n = 0.5 * _noise2(rng, S, S, 6, 6) + 0.3 * _noise2(rng, S, S, 20, 20) + 0.2 * _noise2(rng, S, S, 70, 70)
    base = np.array([140, 136, 126], float)
    img = base[None, None, :] * (0.62 + 0.7 * n[:, :, None])
    img[:, :, 1] *= 1.0 + 0.04 * _noise2(rng, S, S, 8, 8)
    mask = _noise2(rng, S, S, 9, 9) > 0.7                  # lichen / moss patches
    img[mask] = img[mask] * np.array([0.8, 1.05, 0.7])
    return np.dstack([np.clip(img, 0, 255), np.full((S, S), 255.0)]).astype("uint8")


# ---- impostors ------------------------------------------------------------------------------------------------------------
def paint_imp_broad(S, rng, season="summer", trunk=(78, 62, 48), leaf=(70, 112, 44)):
    pt = Painter(S, rng, season)
    keep = {"summer": 1.0, "autumn": 0.95, "winter": 0.1}[season]
    pt.poly([(S / 2 - 6, S - 1), (S / 2 + 6, S - 1), (S / 2 + 3, S * 0.55), (S / 2 - 3, S * 0.55)], trunk)
    for sg in (-1, 1):
        pt.line((S / 2, S * 0.62), (S / 2 + sg * S * 0.22, S * 0.4), trunk, 3)
    cols = [(70, 112, 44), (88, 128, 50), (58, 96, 38)] if season != "autumn" else [(176, 108, 34), (150, 70, 28), (196, 150, 40)]
    for i in range(520):
        ang = rng.uniform(0, 2 * math.pi)
        rr = math.sqrt(rng.random()) * 0.36 * S              # crown kept inside the tile: leaves up to 22 px must not touch the edge (tops were clipped)
        x, y = S / 2 + rr * math.cos(ang), S * 0.42 + rr * math.sin(ang) * 0.80
        if (rr / (0.36 * S)) < 0.35 and rng.random() < 0.55:
            continue                                      # holes towards the middle
        if rng.random() > keep:
            continue
        sh = 0.65 + 0.5 * (1 - (y / S - 0.0) * 0.9) + rng.uniform(-0.1, 0.1)
        c = _mul(cols[int(rng.integers(0, len(cols)))], sh)
        pt.leaf(x, y, rng.uniform(0, 6.28), rng.uniform(14, 22), rng.uniform(9, 14), "round", c)
    return pt.finish(ao=0.18)


def paint_imp_conifer(S, rng, season="summer"):
    pt = Painter(S, rng, season)
    pt.poly([(S / 2 - 4, S - 1), (S / 2 + 4, S - 1), (S / 2 + 2, S * 0.5), (S / 2 - 2, S * 0.5)], (70, 54, 42))
    n = 9
    for t in range(n):
        yb = S * 0.93 - t * S * 0.085
        w = S * (0.40 - t * 0.041)
        shade = 0.7 + 0.35 * t / n
        pts = []
        for k in range(15):
            x = S / 2 - w + 2 * w * k / 14
            pts.append((x, yb + (math.sin(k * 2.1 + t) * 4 + 6 * (1 - abs(k - 7) / 7))))
        pts += [(S / 2, yb - S * 0.2)]
        c = _mul((40, 82, 54), shade)
        pt.poly(pts, c)
        for _ in range(60):
            x = S / 2 + rng.uniform(-w, w)
            y = yb + rng.uniform(-S * 0.04, S * 0.06)
            pt.line((x, y), (x + rng.uniform(-4, 4), y + rng.uniform(4, 9)), _mul(c, rng.uniform(0.7, 1.3)), 1)
    return pt.finish(ao=0.22)
