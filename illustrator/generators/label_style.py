"""Label legibility: fonts, text wrapping, halo / backing box / knock-out mask.

  cfg = label_style.merge(view_settings_label_style, cli_label_style)   # {"default": {...}, "districts": {...}, ..., "backing_layer", "mask_targets"}
  st = label_style.resolve(cfg, "districts")                           # Style (default + category overrides)
  lays, off = label_style.build_layouts(text, st, size, pt_per_ft)     # wrapped candidates for label_offset.Placer.add(layouts=, offset_layout=)
  rec = label_style.Rec(...); label_style.emit(tree, rec, backing_layer)  # SVG: optional halo copy / box, then the text (tspans when wrapped)
  geom = label_style.knock_geom(rec)                                   # padded rounded box (page pt) used to cut lines under the label

Categories: districts (districts + plazas), streets, buildings, rooms, elevation.
Style keys (all in `default`, overridable per category):
  font, size (pt, null = follows the scale), bold, italic, letter_spacing (pt), case (auto|asis|upper|title), color, auto_contrast,
  wrap (off|auto|width), wrap_width, wrap_unit (ft|pt), max_lines, line_spacing (x font size), align (left|center|right),
  mode (none|halo|box|mask), halo_color, halo_width (pt), halo_opacity, box_color, box_pad, box_radius, box_opacity,
  knockout (cut lines under the label), knockout_pad (pt radius around the text box).
mode "mask" = knock-out only (invisible); any other mode can also set knockout. Global: backing_layer (backing in LABELS/Label Backing), mask_targets.
Widths are estimates (Arial metrics x a per-family factor + letter spacing); Illustrator's real metrics differ slightly.
"""
import base64
import json
import math
from dataclasses import dataclass
from xml.sax.saxutils import escape

from shapely import affinity
from shapely.geometry import box as _box

import label_offset as lbo

CATEGORIES = ["districts", "streets", "buildings", "rooms", "elevation"]
LAYER_BACKING = "Label Backing"
LAYER_OF = {"districts": "Labels - Districts", "streets": "Labels - Streets", "buildings": "Labels - Buildings",
            "rooms": "Labels - Rooms", "elevation": "Labels - Elevation"}
MASK_TARGETS = ["contours", "streets", "buildings", "blocks", "water", "fences", "grid"]

# family -> width factor vs Arial (estimate only). Names are the family names Illustrator matches on SVG import.
FONTS = {"Arial": 1.0, "Georgia": 1.08, "Times New Roman": 0.92, "Garamond": 0.86, "Palatino Linotype": 1.02,
         "Trebuchet MS": 0.98, "Verdana": 1.2, "Cambria": 0.98, "Constantia": 0.99, "Calibri": 0.9, "Tahoma": 0.98,
         "Candara": 0.93, "Baskerville": 0.96}
FALLBACK_STACK = {"Garamond": "Garamond, 'Times New Roman', serif", "Baskerville": "Baskerville, Georgia, serif",
                  "Palatino Linotype": "'Palatino Linotype', Palatino, serif", "Georgia": "Georgia, serif",
                  "Times New Roman": "'Times New Roman', Times, serif"}

DEFAULT = {
    "font": "Arial", "size": None, "bold": False, "italic": False, "letter_spacing": 0.0, "case": "asis",
    "color": "#111111", "auto_contrast": False,
    "wrap": "auto", "wrap_width": 120.0, "wrap_unit": "pt", "max_lines": 3, "line_spacing": 1.1, "align": "center",
    "mode": "halo", "halo_color": "#ffffff", "halo_width": 1.6, "halo_opacity": 0.9,
    "box_color": "#ffffff", "box_pad": 2.0, "box_radius": 2.0, "box_opacity": 0.8,
    "knockout": False, "knockout_pad": 2.5,
}
CATEGORY_DEFAULT = {
    "districts": {"bold": True, "case": "auto", "letter_spacing": 0.6, "halo_width": 2.0},
    "streets": {"wrap": "off", "italic": True, "halo_width": 1.4},
    "buildings": {"max_lines": 2},
    "rooms": {"max_lines": 2},
    "elevation": {"wrap": "off", "color": "#6b4423", "mode": "none", "knockout": True, "knockout_pad": 1.5},
}
GLOBAL_DEFAULT = {"backing_layer": True, "mask_targets": ["contours", "streets", "buildings", "blocks", "grid"]}
CASES = ("auto", "asis", "upper", "title")
MODES = ("none", "halo", "box", "mask")


def defaults():
    """Full default config (same shape the panel keeps in its state)."""
    return {"default": dict(DEFAULT), **{c: dict(CATEGORY_DEFAULT.get(c, {})) for c in CATEGORIES}, **GLOBAL_DEFAULT,
            "mask_targets": list(GLOBAL_DEFAULT["mask_targets"])}


def merge(*layers):
    """Merge config dicts left to right on top of the defaults (None / missing keys ignored)."""
    out = defaults()
    for lay in layers:
        for k, v in (lay or {}).items():
            if k in ("backing_layer", "mask_targets"):
                if v is not None:
                    out[k] = v
            elif k == "default" or k in CATEGORIES:
                out[k] = {**out[k], **{a: b for a, b in (v or {}).items() if b is not None or a == "size"}}
    return out


def parse_cli(text):
    """--label-style value: JSON text, '@file' (JSON file) or base64 JSON (--label-style-b64)."""
    if not text:
        return {}
    if text.startswith("@"):
        with open(text[1:], encoding="utf-8") as f:
            return json.load(f)
    return json.loads(text)


def decode_b64(s):
    return json.loads(base64.b64decode(s).decode("utf-8")) if s else {}


@dataclass
class Style:
    font: str = "Arial"
    size: float = None
    bold: bool = False
    italic: bool = False
    letter_spacing: float = 0.0
    case: str = "asis"
    color: str = "#111111"
    auto_contrast: bool = False
    wrap: str = "auto"
    wrap_width: float = 120.0
    wrap_unit: str = "pt"
    max_lines: int = 3
    line_spacing: float = 1.1
    align: str = "center"
    mode: str = "halo"
    halo_color: str = "#ffffff"
    halo_width: float = 1.6
    halo_opacity: float = 0.9
    box_color: str = "#ffffff"
    box_pad: float = 2.0
    box_radius: float = 2.0
    box_opacity: float = 0.8
    knockout: bool = False
    knockout_pad: float = 2.5

    @property
    def knock(self):
        return self.mode == "mask" or bool(self.knockout)


def resolve(cfg, cat):
    d = {**DEFAULT, **(cfg.get("default") or {}), **(cfg.get(cat) or {})}
    kw = {}
    for k in Style.__dataclass_fields__:
        kw[k] = d[k]
    s = Style(**kw)
    s.size = float(s.size) if s.size not in (None, "", 0) else None
    s.letter_spacing = float(s.letter_spacing or 0)
    s.wrap_width = max(float(s.wrap_width or 0), 1.0)
    s.max_lines = max(int(s.max_lines or 1), 1)
    s.line_spacing = max(float(s.line_spacing or 1.0), 0.5)
    s.halo_width = max(float(s.halo_width or 0), 0.0)
    s.knockout_pad = max(float(s.knockout_pad or 0), 0.0)
    s.box_pad = max(float(s.box_pad or 0), 0.0)
    s.box_radius = max(float(s.box_radius or 0), 0.0)
    for k, lo in (("halo_opacity", 0), ("box_opacity", 0)):
        setattr(s, k, min(max(float(getattr(s, k)), 0.0), 1.0))
    if s.mode not in MODES:
        s.mode = "none"
    if s.align not in ("left", "center", "right"):
        s.align = "center"
    if s.case not in CASES:
        s.case = "asis"
    if s.wrap not in ("off", "auto", "width"):
        s.wrap = "off"
    s.bold, s.italic, s.auto_contrast = bool(s.bold), bool(s.italic), bool(s.auto_contrast)
    return s


# ------------------------------------------------------------------ text
_SMALL = {"of", "the", "and", "a", "an", "in", "on", "at", "to", "for", "by", "de", "la", "le"}


def apply_case(text, st, auto_upper=False):
    c = "upper" if (st.case == "auto" and auto_upper) else st.case
    if c == "upper":
        return text.upper()
    if c == "title":
        words, out = text.split(" "), []
        for i, w in enumerate(words):
            lw = w.lower()
            out.append(lw if (0 < i and lw in _SMALL) else lw[:1].upper() + lw[1:] if w else w)
        return " ".join(out)
    return text


def measure(s, size, st):
    """Estimated width in pt of one line."""
    w, _ = lbo.text_size(s, size, st.bold)
    return (w - 0.5) * FONTS.get(st.font, 1.0) + 0.5 + st.letter_spacing * len(s)


def line_height(size, st):
    return size * st.line_spacing


def block_height(n, size, st):
    return size * 1.1 + (n - 1) * line_height(size, st)


def _greedy(words, wf, W):
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w) if cur else w
        if cur and wf(t) > W:
            lines.append(cur)
            cur = w
        else:
            cur = t
    lines.append(cur)
    return lines


def wrap_greedy_count(words, wf, W):
    return len(_greedy(words, wf, W))


def balanced(words, wf, n):
    """Break `words` into at most n lines at word boundaries (no hyphenation): the narrowest block that fits n lines, then
    the breaks that make the lines most even (minimum sum of squared slack)."""
    if n <= 1 or len(words) < 2:
        return [" ".join(words)]
    lo = max(wf(w) for w in words)
    hi = wf(" ".join(words))
    for _ in range(30):
        mid = (lo + hi) / 2
        if len(_greedy(words, wf, mid)) <= n:
            hi = mid
        else:
            lo = mid
    W = hi + 0.01
    k = len(_greedy(words, wf, W))
    m = len(words)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(k + 1)]
    prev = [[0] * (m + 1) for _ in range(k + 1)]
    cost[0][0] = 0.0
    for li in range(1, k + 1):
        for j in range(1, m + 1):
            for i in range(j):
                if cost[li - 1][i] == INF:
                    continue
                wd = wf(" ".join(words[i:j]))
                if wd > W and j - i > 1:
                    continue
                c = cost[li - 1][i] + (W - min(wd, W)) ** 2
                if c < cost[li][j]:
                    cost[li][j], prev[li][j] = c, i
    if cost[k][m] == INF:
        return _greedy(words, wf, W)
    out, j = [], m
    for li in range(k, 0, -1):
        i = prev[li][j]
        out.append(" ".join(words[i:j]))
        j = i
    return out[::-1]


def wrap_to_width(words, wf, W, max_lines):
    """Lines no wider than W (a single longer word keeps its own line), at most max_lines; if that is impossible the block is
    widened to the narrowest that fits max_lines. Balanced."""
    k = wrap_greedy_count(words, wf, W)
    if k <= 1:
        return [" ".join(words)]
    if k > max_lines:
        return balanced(words, wf, max_lines)
    lines = balanced(words, wf, k)
    return lines if max(wf(x) for x in lines) <= max(W, max(wf(w) for w in words)) + 0.01 else _greedy(words, wf, W)


def make_layout(lines, size, st):
    w = max(measure(x, size, st) for x in lines)
    return lbo.Layout(list(lines), w, block_height(len(lines), size, st))


def build_layouts(text, st, size, pt_per_ft):
    """-> (layouts to try in order, layout used when the label has to be moved outside its shape).
    wrap off: one line. wrap width: one fixed wrapped layout (max width in ft or pt). wrap auto: 1 line, then 2..max_lines
    balanced lines; the first that fits inside the shape wins, an offset label uses the one-liner."""
    text = " ".join(text.split())
    one = make_layout([text], size, st)
    words = text.split(" ")
    if st.wrap == "off" or len(words) < 2 or st.max_lines < 2:
        return [one], one
    wf = lambda s: measure(s, size, st)
    if st.wrap == "width":
        W = st.wrap_width * (pt_per_ft if st.wrap_unit == "ft" else 1.0)
        lay = make_layout(wrap_to_width(words, wf, W, st.max_lines), size, st)
        return [lay], lay
    lays = [one]
    for n in range(2, st.max_lines + 1):
        lines = balanced(words, wf, n)
        if len(lines) > len(lays[-1].lines):
            lays.append(make_layout(lines, size, st))
    return lays, one


# ------------------------------------------------------------------ colours / records
def _lum(hexc):
    h = (hexc or "#ffffff").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 1.0
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def text_color(st, paper="#f3ead2"):
    """Fill colour of the text: the chosen colour, or with auto_contrast dark text on a light backing / light text on a dark one."""
    if not st.auto_contrast:
        return st.color
    bg = st.box_color if st.mode == "box" else st.halo_color if st.mode == "halo" else paper
    return "#1a1a1a" if _lum(bg) > 0.4 else "#f7f4ea"


@dataclass
class Rec:
    id: str
    layer: str
    lines: list
    cx: float          # centre of the text block (page pt)
    cy: float
    w: float
    h: float
    rot: float
    size: float
    st: Style
    cls: str = ""


def rec_box(rec):
    return lbo.text_box(rec.cx, rec.cy, rec.w, rec.h, rec.rot)


def knock_geom(rec):
    """Padded rounded rectangle (page pt) cut out of the lines beneath the label."""
    return rec_box(rec).buffer(rec.st.knockout_pad, join_style=1, resolution=6)


def _style_attr(st, rec, fill, stroke=None, sw=None, op=None):
    fam = FALLBACK_STACK.get(st.font, f"'{st.font}'" if " " in st.font else st.font)
    parts = [f"font-family:{fam}", f"font-weight:{'bold' if st.bold else 'normal'}", f"font-style:{'italic' if st.italic else 'normal'}"]
    if st.letter_spacing:
        parts.append(f"letter-spacing:{st.letter_spacing:g}")
    parts.append(f"fill:{fill}")
    if stroke:
        parts += [f"stroke:{stroke}", f"stroke-width:{sw:.2f}", "stroke-linejoin:round", "stroke-linecap:round"]
        if op is not None and op < 0.999:
            parts += [f"stroke-opacity:{op:.2f}", f"fill-opacity:{op:.2f}"]
    return ";".join(parts)


def _text_el(rec, id_, style, with_class=True):
    st, n = rec.st, len(rec.lines)
    lh = line_height(rec.size, st)
    top = rec.cy - rec.h / 2
    y0 = top + 0.9 * rec.size
    if st.align == "left":
        x, anchor = rec.cx - rec.w / 2, "start"
    elif st.align == "right":
        x, anchor = rec.cx + rec.w / 2, "end"
    else:
        x, anchor = rec.cx, "middle"
    tr = f' transform="rotate({rec.rot:.2f} {rec.cx:.2f} {rec.cy:.2f})"' if rec.rot and abs(rec.rot) > 0.01 else ""
    cls = f' class="{rec.cls}"' if rec.cls and with_class else ""
    head = (f'<text id="{id_}"{cls} x="{x:.2f}" y="{y0:.2f}" font-size="{rec.size:g}" text-anchor="{anchor}" '
            f'style="{style}"{tr}>')
    if n == 1:
        return head + escape(rec.lines[0]) + "</text>"
    spans = "".join(f'<tspan x="{x:.2f}" dy="{0 if i == 0 else lh:.2f}">{escape(t)}</tspan>' for i, t in enumerate(rec.lines))
    return head + spans + "</text>"


def emit(tree, rec, backing_layer=None):
    """Add one label to the tree. Backing (halo copy / box) goes to `backing_layer` when given, else just under the text in
    the label's own layer."""
    st = rec.st
    bl = backing_layer or rec.layer
    if st.mode == "halo" and st.halo_width > 0:
        tree.add(bl, _text_el(rec, rec.id + "_halo", _style_attr(st, rec, st.halo_color, st.halo_color, st.halo_width * 2, st.halo_opacity),
                              with_class=False))
    elif st.mode == "box":
        pad = st.box_pad
        x, y, w, h = rec.cx - rec.w / 2 - pad, rec.cy - rec.h / 2 - pad, rec.w + 2 * pad, rec.h + 2 * pad
        r = min(st.box_radius, w / 2, h / 2)
        tr = f' transform="rotate({rec.rot:.2f} {rec.cx:.2f} {rec.cy:.2f})"' if rec.rot and abs(rec.rot) > 0.01 else ""
        rr = f' rx="{r:.2f}" ry="{r:.2f}"' if r > 0 else ""
        tree.add(bl, f'<rect id="{rec.id}_box" x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}"{rr} '
                     f'style="fill:{st.box_color};fill-opacity:{st.box_opacity:.2f};stroke:none"{tr}/>')
    tree.add(rec.layer, _text_el(rec, rec.id, _style_attr(st, rec, text_color(st))))
