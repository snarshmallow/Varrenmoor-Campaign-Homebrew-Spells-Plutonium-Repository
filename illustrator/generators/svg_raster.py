"""Headless rasteriser for our layered SVGs (PIL only, no Illustrator, no cairo).

  python illustrator/generators/svg_raster.py in.svg out.png [--dpi 120] [--ss 2] [--bg "#faf7ee"|none]
        [--base img.png@x0,y0,x1,y1 ...] [--hide-layers "Labels - Hidden,Grid"] [--px-per-ft N --feet-per-pt F]

Draws what our generators emit: paths (M/L/Z), polygons, circles, text with tspans / rotate() / halo stroke / textPath, CSS classes from
the <style> block, presentation attributes and inline style, stroke-dasharray, stroke/fill-opacity. Raster base layers (shading, fills)
go underneath (rect in page points). Output size = page pt * dpi / 72. Not a general SVG renderer: curves (C/Q/A) are not supported.
"""
import argparse
import math
import os
import re
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

NS = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
SKIP_LAYERS = {"Labels - Hidden"}
FONT_DIRS = ["C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation"]
FONTS = {(False, False): ["arial.ttf", "LiberationSans-Regular.ttf", "DejaVuSans.ttf"],
         (True, False): ["arialbd.ttf", "LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf"],
         (False, True): ["ariali.ttf", "LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf"],
         (True, True): ["arialbi.ttf", "LiberationSans-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf"]}
_fc = {}


def font(px, bold=False, ital=False):
    key = (round(px * 2) / 2, bold, ital)
    if key not in _fc:
        f = None
        for n in FONTS[(bold, ital)]:
            for dr in FONT_DIRS:
                try:
                    f = ImageFont.truetype(os.path.join(dr, n), max(int(round(px)), 2))
                    break
                except OSError:
                    pass
            if f:
                break
        _fc[key] = f or ImageFont.load_default()
    return _fc[key]


def parse_css(root):
    css = {}
    for st in root.iter(NS + "style"):
        for m in re.finditer(r"([^{}]+)\{([^}]*)\}", st.text or ""):
            props = dict((k.strip(), v.strip()) for k, v in (p.split(":", 1) for p in m.group(2).split(";") if ":" in p))
            for sel in m.group(1).split(","):
                sel = sel.strip()
                css.setdefault(sel, {}).update(props)
    return css


def style_of(el, css, inherited=None):
    s = dict(inherited or {})
    s.update(css.get(el.tag.replace(NS, ""), {}))
    for c in (el.get("class") or "").split():
        s.update(css.get("." + c, {}))
    for k in ("fill", "stroke", "stroke-width", "stroke-opacity", "fill-opacity", "stroke-dasharray", "font-size", "font-weight", "font-style",
              "font-family", "text-anchor", "stroke-linejoin", "letter-spacing", "opacity"):
        if el.get(k) is not None:
            s[k] = el.get(k)
    for p in (el.get("style") or "").split(";"):
        if ":" in p:
            k, v = p.split(":", 1)
            s[k.strip()] = v.strip()
    return s


def color(c, op=1.0):
    if not c or c == "none":
        return None
    c = c.strip()
    if c.startswith("#"):
        if len(c) == 4:
            c = "#" + "".join(ch * 2 for ch in c[1:])
        return (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), int(round(255 * op)))
    m = re.match(r"rgb\(([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)\)", c)
    if m:
        return tuple(int(float(x)) for x in m.groups()) + (int(round(255 * op)),)
    named = {"black": (0, 0, 0), "white": (255, 255, 255), "red": (255, 0, 0)}
    return named.get(c, (0, 0, 0)) + (int(round(255 * op)),)


def fnum(v, d=0.0):
    try:
        return float(re.sub(r"[a-z%]+$", "", str(v)))
    except (TypeError, ValueError):
        return d


def path_subs(dstr):
    """-> [(points, closed)] for M/L/H/V/Z (absolute and relative), curves approximated by their end points."""
    subs, cur, closed, pos = [], [], False, (0.0, 0.0)
    toks = re.findall(r"[MmLlHhVvZzCcQqSsTtAa]|-?\d*\.?\d+(?:[eE][-+]?\d+)?", dstr)
    i, cmd = 0, None

    def num():
        nonlocal i
        v = float(toks[i]); i += 1
        return v
    while i < len(toks):
        if re.match(r"[A-Za-z]", toks[i]):
            cmd = toks[i]; i += 1
            if cmd in "Zz":
                if cur:
                    subs.append((cur, True)); cur = []
                continue
        c = cmd
        rel = c.islower()
        u = c.upper()
        if u == "M" or u == "L":
            x, y = num(), num()
            if rel:
                x, y = pos[0] + x, pos[1] + y
            if u == "M":
                if cur:
                    subs.append((cur, False))
                cur = [(x, y)]
                cmd = "l" if rel else "L"
            else:
                cur.append((x, y))
            pos = (x, y)
        elif u == "H":
            x = num(); x = pos[0] + x if rel else x; pos = (x, pos[1]); cur.append(pos)
        elif u == "V":
            y = num(); y = pos[1] + y if rel else y; pos = (pos[0], y); cur.append(pos)
        elif u in "CQSTA":
            n = {"C": 6, "Q": 4, "S": 4, "T": 2, "A": 7}[u]
            v = [num() for _ in range(n)]
            x, y = v[-2], v[-1]
            if rel:
                x, y = pos[0] + x, pos[1] + y
            pos = (x, y); cur.append(pos)
        else:
            i += 1
    if cur:
        subs.append((cur, False))
    return subs


def dashed(pts, dash, closed):
    if not dash:
        return [pts + ([pts[0]] if closed else [])]
    q = pts + ([pts[0]] if closed else [])
    out, on, idx, left, run = [], True, 0, dash[0], [q[0]]
    for a, b in zip(q, q[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg < 1e-9:
            continue
        t0 = 0.0
        while seg - t0 > left:
            t0 += left
            p = (a[0] + (b[0] - a[0]) * t0 / seg, a[1] + (b[1] - a[1]) * t0 / seg)
            if on:
                run.append(p); out.append(run); run = []
            else:
                run = [p]
            on = not on
            idx = (idx + 1) % len(dash)
            left = dash[idx]
        left -= seg - t0
        if on:
            run.append(b)
    if on and len(run) > 1:
        out.append(run)
    return out


class Raster:
    def __init__(self, svg, dpi=120.0, ss=2, bg="#faf7ee", bases=(), hide=()):
        self.root = ET.parse(svg).getroot()
        vb = [float(x) for x in self.root.get("viewBox").split()]
        self.vb = vb
        self.css = parse_css(self.root)
        self.s = dpi / 72.0 * ss
        self.ss, self.dpi = ss, dpi
        self.W, self.H = int(round(vb[2] * self.s)), int(round(vb[3] * self.s))
        col = color(bg if bg and bg != "none" else "#ffffff")[:3]
        self.img = Image.new("RGB", (self.W, self.H), col)          # RGB: ImageDraw "RGBA" colours then blend (stroke-opacity)
        self.hide = set(hide) | SKIP_LAYERS
        self.ids = {el.get("id"): el for el in self.root.iter() if el.get("id")}
        for path, rect in bases:
            self.base(path, rect)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def base(self, path, rect):
        im = Image.open(path).convert("RGBA")
        x0, y0, x1, y1 = [v * self.s for v in rect]
        w, h = max(int(round(x1 - x0)), 1), max(int(round(y1 - y0)), 1)
        im = im.resize((w, h), Image.LANCZOS)
        self.img.paste(im, (int(round(x0)), int(round(y0))), im)

    def P(self, p):
        return (p[0] * self.s, p[1] * self.s)

    def stroke(self, pts, closed, st):
        col = color(st.get("stroke"), fnum(st.get("stroke-opacity"), 1.0) * fnum(st.get("opacity"), 1.0))
        if not col or len(pts) < 2:
            return
        w = max(fnum(st.get("stroke-width"), 1.0) * self.s, 1.0)
        dash = [fnum(x) * self.s for x in re.split(r"[ ,]+", st["stroke-dasharray"].strip())] if st.get("stroke-dasharray", "none") != "none" else None
        for run in dashed([self.P(p) for p in pts], dash, closed):
            if len(run) > 1:
                self.d.line(run, fill=col, width=int(round(w)), joint="curve")

    def draw_shape(self, el, st):
        tag = el.tag.replace(NS, "")
        if tag == "path":
            subs = path_subs(el.get("d") or "")
        elif tag in ("polygon", "polyline"):
            nums = [float(x) for x in re.findall(r"-?\d*\.?\d+", el.get("points") or "")]
            subs = [(list(zip(nums[0::2], nums[1::2])), tag == "polygon")]
        elif tag == "line":
            subs = [([(fnum(el.get("x1")), fnum(el.get("y1"))), (fnum(el.get("x2")), fnum(el.get("y2")))], False)]
        elif tag == "rect":
            x, y, w, h = (fnum(el.get(k)) for k in ("x", "y", "width", "height"))
            subs = [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        elif tag == "circle":
            cx, cy, r = fnum(el.get("cx")), fnum(el.get("cy")), fnum(el.get("r"))
            subs = [([(cx + r * math.cos(a * math.pi / 12), cy + r * math.sin(a * math.pi / 12)) for a in range(24)], True)]
        else:
            return
        fill = color(st.get("fill"), fnum(st.get("fill-opacity"), 1.0)) if tag != "polyline" else None
        for pts, closed in subs:
            if fill and len(pts) >= 3:
                self.d.polygon([self.P(p) for p in pts], fill=fill)
            self.stroke(pts, closed, st)

    # ---------------------------------------------------------------- text
    def text_img(self, txt, st, size_pt):
        px = size_pt * self.s
        f = font(px, st.get("font-weight", "normal") in ("bold", "700"), st.get("font-style") == "italic")
        ls = fnum(st.get("letter-spacing"), 0.0) * self.s
        sw = fnum(st.get("stroke-width"), 0.0) * self.s if st.get("stroke", "none") != "none" else 0.0
        fill = color(st.get("fill", "#000000"), fnum(st.get("fill-opacity"), 1.0))
        stc = color(st.get("stroke"), fnum(st.get("stroke-opacity"), 1.0))
        return f, ls, sw, fill, stc

    def width(self, txt, f, ls):
        return f.getlength(txt) + ls * max(len(txt) - 1, 0)

    def put_text(self, txt, x, y, st, size_pt, anchor="start", rot=0.0, rot_c=None):
        """x,y in page pt (baseline); optional rotation (deg, clockwise like SVG) about rot_c (page pt)."""
        f, ls, sw, fill, stc = self.text_img(txt, st, size_pt)
        w = self.width(txt, f, ls)
        pad = int(sw) + 4
        asc, desc = f.getmetrics()
        tw, th = int(w) + 2 * pad + 2, asc + desc + 2 * pad
        tile = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
        td = ImageDraw.Draw(tile, "RGBA")
        ox = {"middle": w / 2, "end": w}.get(anchor, 0.0)

        def paint(fill_, stroke_w, stroke_c):
            cx = pad
            for ch in txt if ls else [txt]:
                td.text((cx, pad), ch, font=f, fill=fill_, stroke_width=int(round(stroke_w)), stroke_fill=stroke_c)
                cx += (f.getlength(ch) + ls) if ls else 0
        if sw > 0 and stc:
            paint(stc, sw / 2.0, stc)
        if fill:
            paint(fill, 0, None)
        X, Y = x * self.s - ox, y * self.s - asc - pad    # tile origin (unrotated) so the baseline sits on y
        if rot:
            cx, cy = (rot_c[0] * self.s, rot_c[1] * self.s) if rot_c else (x * self.s, y * self.s)
            # rotate about (cx,cy): tile placed unrotated, rotated about that point -> compute via affine on a canvas-size layer is heavy;
            # rotate the tile about its own centre then place its centre at the rotated centre
            tc = (X + tw / 2.0, Y + th / 2.0)
            a = math.radians(rot)
            dx, dy = tc[0] - cx, tc[1] - cy
            nc = (cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a))
            tile = tile.rotate(-rot, resample=Image.BICUBIC, expand=True)
            X, Y = nc[0] - tile.width / 2.0, nc[1] - tile.height / 2.0
        self.img.paste(tile, (int(round(X)), int(round(Y))), tile)

    def draw_text(self, el, st):
        size = fnum(st.get("font-size"), 10.0)
        anchor = st.get("text-anchor", "start")
        rot, rc = 0.0, None
        m = re.search(r"rotate\(([-\d.]+)[ ,]+([-\d.]+)[ ,]+([-\d.]+)\)", el.get("transform") or "")
        if m:
            rot, rc = float(m.group(1)), (float(m.group(2)), float(m.group(3)))
        tp = el.find(NS + "textPath")
        if tp is not None:
            return self.text_on_path(tp, st, size)
        x, y = fnum(el.get("x")), fnum(el.get("y"))
        tsp = el.findall(NS + "tspan")
        if not tsp:
            self.put_text("".join(el.itertext()), x, y, st, size, anchor, rot, rc)
            return
        for t in tsp:
            ts = style_of(t, self.css, st)
            if t.get("x") is not None:
                x = fnum(t.get("x"))
            y += fnum(t.get("dy"), 0.0)
            self.put_text("".join(t.itertext()), x, y, ts, fnum(ts.get("font-size"), size), ts.get("text-anchor", anchor), rot, rc)

    def text_on_path(self, tp, st, size):
        ref = (tp.get("href") or tp.get(XLINK) or "").lstrip("#")
        pe = self.ids.get(ref)
        if pe is None:
            return
        subs = path_subs(pe.get("d") or "")
        if not subs:
            return
        pts = subs[0][0]
        seg = [(a, b, math.hypot(b[0] - a[0], b[1] - a[1])) for a, b in zip(pts, pts[1:])]
        total = sum(s[2] for s in seg)
        txt = "".join(tp.itertext())
        f, ls, sw, fill, stc = self.text_img(txt, st, size)
        wpt = self.width(txt, f, ls) / self.s
        off = tp.get("startOffset") or "0"
        start = total * float(off[:-1]) / 100.0 if off.endswith("%") else fnum(off)
        if st.get("text-anchor") == "middle":
            start -= wpt / 2.0
        elif st.get("text-anchor") == "end":
            start -= wpt
        pos = start
        for ch in txt:
            cw = f.getlength(ch) / self.s
            mid = pos + cw / 2.0
            if 0 <= mid <= total:
                acc = 0.0
                for a, b, L in seg:
                    if acc + L >= mid and L > 0:
                        t = (mid - acc) / L
                        px, py = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
                        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
                        # glyph is centred on (px,py): baseline point = centre shifted by half the x-height perpendicular
                        nx, ny = -math.sin(math.radians(ang)), math.cos(math.radians(ang))
                        bx, by = px - nx * size * 0.35, py - ny * size * 0.35
                        self.put_text(ch, bx, by, st, size, "middle", ang, (bx, by))
                        break
                    acc += L
            pos += cw + ls / self.s

    # ---------------------------------------------------------------- walk
    def walk(self, g, inh, layer):
        for el in g:
            tag = el.tag.replace(NS, "")
            if tag in ("style", "defs", "title", "desc", "tspan", "textPath"):
                continue
            st = style_of(el, self.css, inh if tag in ("g", "text") else {k: v for k, v in inh.items() if k in ("opacity",)})
            if tag == "g":
                name = el.get("id") or ""
                if name in self.hide or st.get("display") == "none":
                    continue
                self.walk(el, st, name or layer)
                continue
            if "hidden-label" in (el.get("class") or "") or st.get("display") == "none":
                continue
            if tag == "text":
                self.draw_text(el, st)
            else:
                self.draw_shape(el, st)

    def render(self):
        self.walk(self.root, {}, "")
        if self.ss != 1:
            self.img = self.img.resize((int(round(self.vb[2] * self.dpi / 72.0)), int(round(self.vb[3] * self.dpi / 72.0))), Image.LANCZOS)
        return self.img


def rasterise(svg, png, dpi=120.0, ss=2, bg="#faf7ee", bases=(), hide=()):
    """bases: [(png_path, [x0,y0,x1,y1] page pt)] drawn first. Returns (png, size)."""
    im = Raster(svg, dpi, ss, bg, bases, hide).render()
    os.makedirs(os.path.dirname(os.path.abspath(png)), exist_ok=True)
    im.save(png)
    return png, im.size


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("svg")
    ap.add_argument("png")
    ap.add_argument("--dpi", type=float, default=120.0)
    ap.add_argument("--ss", type=int, default=2)
    ap.add_argument("--bg", default="#faf7ee")
    ap.add_argument("--base", action="append", default=[], help="img.png@x0,y0,x1,y1 (page pt)")
    ap.add_argument("--hide-layers", default="")
    a = ap.parse_args(argv)
    bases = []
    for b in a.base:
        p, r = b.rsplit("@", 1)
        bases.append((p, [float(x) for x in r.split(",")]))
    png, size = rasterise(a.svg, a.png, a.dpi, a.ss, a.bg, bases, [x for x in a.hide_layers.split(",") if x])
    print("wrote", png, size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
