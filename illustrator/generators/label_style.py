"""Label legibility: fonts, text wrapping, halo / backing box / knock-out mask.

  cfg = label_style.merge(view_settings_label_style, cli_label_style)   # {"default": {...}, "districts": {...}, ..., "backing_layer", "mask_targets"}
  st = label_style.resolve(cfg, "districts")                           # Style (default + category overrides)
  lays, off = label_style.build_layouts(text, st, size, pt_per_ft)     # wrapped candidates for label_offset.Placer.add(layouts=, offset_layout=)
  rec = label_style.Rec(...); label_style.emit(tree, rec, backing_layer)  # SVG: optional halo copy / box, then the text (tspans when wrapped)
  geom = label_style.knock_geom(rec)                                   # padded rounded box (page pt) used to cut lines under the label

Categories: districts (districts + plazas), streets, buildings, rooms, elevation.
Wrapping extras: wrap_mode (balanced|greedy), min_width / max_width (pt line width), fit_shape + fit_ratio (line width limited to a fraction of the
shape width), lines (exact line count), max_chars (per line), break_chars (break after - and /; apostrophes never break), abbrev (off|fit: use
presets/label_abbreviations.json only when the label does not otherwise fit), small_caps.
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
import os
import re
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
    "mode": "halo", "halo_color": "#ffffff", "halo_width": 2.0, "halo_opacity": 0.92,
    "box_color": "#ffffff", "box_pad": 2.0, "box_radius": 2.0, "box_opacity": 0.8,
    "knockout": False, "knockout_pad": 2.5,
    "wrap_mode": "balanced", "min_width": 0.0, "max_width": 0.0, "fit_shape": False, "fit_ratio": 0.92, "lines": 0, "max_chars": 0,
    "break_chars": True, "abbrev": "off", "small_caps": False,
}
CATEGORY_DEFAULT = {
    "districts": {"bold": True, "case": "auto", "letter_spacing": 0.6, "halo_width": 2.6},
    "streets": {"wrap": "off", "italic": True, "halo_width": 1.8},
    "buildings": {"max_lines": 2, "fit_shape": True},
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
    wrap_mode: str = "balanced"
    min_width: float = 0.0
    max_width: float = 0.0
    fit_shape: bool = False
    fit_ratio: float = 0.92
    lines: int = 0
    max_chars: int = 0
    break_chars: bool = True
    abbrev: str = "off"
    small_caps: bool = False

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
    s.wrap_mode = "greedy" if s.wrap_mode == "greedy" else "balanced"
    s.min_width, s.max_width = max(float(s.min_width or 0), 0.0), max(float(s.max_width or 0), 0.0)
    s.fit_ratio = min(max(float(s.fit_ratio or 0.92), 0.3), 1.5)
    s.lines, s.max_chars = max(int(s.lines or 0), 0), max(int(s.max_chars or 0), 0)
    s.fit_shape, s.break_chars, s.small_caps = bool(s.fit_shape), bool(s.break_chars), bool(s.small_caps)
    s.abbrev = "fit" if s.abbrev in ("fit", True, "on") else "off"
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


SMALL_CAPS_RATIO = 0.8      # small-cap letters are capitals at this fraction of the font size


def measure(s, size, st):
    """Estimated width in pt of one line."""
    s = s.replace(NOSP, "")
    if getattr(st, "small_caps", False) and any(c.islower() for c in s):
        big = "".join(c for c in s if not c.islower())
        small = "".join(c.upper() for c in s if c.islower())
        w = (lbo.text_size(big, size, st.bold)[0] - 0.5) + SMALL_CAPS_RATIO * (lbo.text_size(small, size, st.bold)[0] - 0.5) + 0.5
    else:
        w, _ = lbo.text_size(s, size, st.bold)
    return (w - 0.5) * FONTS.get(st.font, 1.0) + 0.5 + st.letter_spacing * len(s)


def line_height(size, st):
    return size * st.line_spacing


def block_height(n, size, st):
    return size * 1.1 + (n - 1) * line_height(size, st)


NOSP = "\x00"       # marks a token that is glued to the next one (a break after '-' or '/' leaves no space)


def jn(ws):
    """Join tokens: a space between words, none after a token ending in NOSP (hyphen / slash break points)."""
    s = ""
    for i, w in enumerate(ws):
        s += w[:-1] if w.endswith(NOSP) else w + (" " if i < len(ws) - 1 else "")
    return s


def tokens(text, st):
    """Words of the text; with break_chars on, a '-' or '/' inside a word is also a break point ('Sword-Smiths' -> 'Sword-', 'Smiths').
    Apostrophes never break (Warden's stays whole)."""
    words = text.split(" ")
    if not getattr(st, "break_chars", True):
        return words
    out = []
    for w in words:
        parts = re.split(r"(?<=[-–—/])(?=[^\s\-–—/])", w)
        for i, p in enumerate(parts):
            out.append(p + (NOSP if i < len(parts) - 1 else ""))
    return out


def _greedy(words, wf, W):
    lines, cur = [], []
    for w in words:
        t = cur + [w]
        if cur and wf(jn(t)) > W:
            lines.append(jn(cur))
            cur = [w]
        else:
            cur = t
    lines.append(jn(cur))
    return lines


def wrap_greedy_count(words, wf, W):
    return len(_greedy(words, wf, W))


def _narrowest(words, wf, n):
    """Narrowest width W for which greedy wrapping needs at most n lines."""
    lo = max(wf(jn([w])) for w in words)
    hi = wf(jn(words))
    for _ in range(30):
        mid = (lo + hi) / 2
        if len(_greedy(words, wf, mid)) <= n:
            hi = mid
        else:
            lo = mid
    return hi + 0.01


def greedy_n(words, wf, n):
    """At most n lines, each filled as far as it goes (ragged last line)."""
    if n <= 1 or len(words) < 2:
        return [jn(words)]
    return _greedy(words, wf, _narrowest(words, wf, n))


def balanced(words, wf, n):
    """Break `words` into at most n lines at word boundaries (no hyphenation): the narrowest block that fits n lines, then
    the breaks that make the lines most even (minimum sum of squared slack). A line does not end on a small word (of, the, and)."""
    if n <= 1 or len(words) < 2:
        return [jn(words)]
    W = _narrowest(words, wf, n)
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
                wd = wf(jn(words[i:j]))
                if wd > W and j - i > 1:
                    continue
                c = cost[li - 1][i] + (W - min(wd, W)) ** 2
                if j < m and words[j - 1].lower().rstrip(NOSP) in _SMALL and j - i > 1:
                    c += (0.35 * W) ** 2           # do not leave 'of' / 'the' dangling at the end of a line
                if c < cost[li][j]:
                    cost[li][j], prev[li][j] = c, i
    if cost[k][m] == INF:
        return _greedy(words, wf, W)
    out, j = [], m
    for li in range(k, 0, -1):
        i = prev[li][j]
        out.append(jn(words[i:j]))
        j = i
    return out[::-1]


def wrap_to_width(words, wf, W, max_lines, greedy=False):
    """Lines no wider than W (a single longer word keeps its own line), at most max_lines; if that is impossible the block is
    widened to the narrowest that fits max_lines. Balanced (or greedy)."""
    k = wrap_greedy_count(words, wf, W)
    if k <= 1:
        return [jn(words)]
    fn = greedy_n if greedy else balanced
    if k > max_lines:
        return fn(words, wf, max_lines)
    lines = fn(words, wf, k)
    return lines if max(wf(x) for x in lines) <= max(W, max(wf(jn([w])) for w in words)) + 0.01 else _greedy(words, wf, W)


def make_layout(lines, size, st):
    w = max(measure(x, size, st) for x in lines)
    return lbo.Layout(list(lines), w, block_height(len(lines), size, st))


# ------------------------------------------------------------------ abbreviations
ABBREV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "presets", "label_abbreviations.json")
_ABBR_CACHE = {}


def load_abbreviations(path=None, extra=None):
    """Word -> abbreviation map from presets/label_abbreviations.json (the user edits it), merged with `extra` (cfg 'abbreviations')."""
    p = os.path.abspath(path or ABBREV_FILE)
    if p not in _ABBR_CACHE:
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            _ABBR_CACHE[p] = {k: v for k, v in d.items() if not k.startswith("_") and isinstance(v, str)}
        except (OSError, ValueError):
            _ABBR_CACHE[p] = {}
    out = dict(_ABBR_CACHE[p])
    out.update({k: v for k, v in (extra or {}).items() if isinstance(v, str)})
    return out


def abbreviate(text, abbr):
    """Whole-phrase and whole-word replacement (case-insensitive, keeps a trailing '*'). Longest keys first so 'Magistrate's Court' beats 'Court'."""
    if not abbr:
        return text
    out = text
    for k in sorted(abbr, key=len, reverse=True):
        out = re.sub(r"(?<![\w'])" + re.escape(k) + r"(?![\w'])", lambda m_, v=abbr[k]: v, out, flags=re.I)
    return out


# ------------------------------------------------------------------ layouts
def _width_limit(st, shape_w, pt_per_ft):
    """Line width limit in pt from min_width / max_width / fit_shape (None = no limit)."""
    W = None
    if st.fit_shape and shape_w:
        W = shape_w * st.fit_ratio
    if st.max_width:
        W = st.max_width if W is None else min(W, st.max_width)
    if W is not None and st.min_width:
        W = max(W, st.min_width)
    return W


def _variants(words, wf, st, size, W, pt_per_ft):
    """Wrapped candidates for one text, fewest lines first."""
    one = make_layout([jn(words)], size, st)
    if len(words) < 2 or st.max_lines < 2 and not st.lines:
        return [one]
    fn = greedy_n if st.wrap_mode == "greedy" else balanced
    if st.wrap == "width":
        Ww = st.wrap_width * (pt_per_ft if st.wrap_unit == "ft" else 1.0)
        return [make_layout(wrap_to_width(words, wf, Ww, st.max_lines, st.wrap_mode == "greedy"), size, st)]
    if st.lines:                                   # an exact number of lines
        return [make_layout(fn(words, wf, min(st.lines, len(words))), size, st)]
    lays = [one]
    for n in range(2, st.max_lines + 1):
        lines = fn(words, wf, n)
        if len(lines) > len(lays[-1].lines):
            lays.append(make_layout(lines, size, st))
    if st.max_chars:                               # keep only layouts whose lines are short enough; widen the line count when needed
        ok = [lay for lay in lays if max(len(x) for x in lay.lines) <= st.max_chars]
        if not ok:
            lines = wrap_to_width(words, lambda s: len(s), st.max_chars, st.max_lines, st.wrap_mode == "greedy")
            ok = [make_layout(lines, size, st)]
        lays = ok
    if W is not None:
        ok = [lay for lay in lays if lay.w <= W + 0.01]
        if not ok:
            ok = [make_layout(wrap_to_width(words, wf, W, max(st.max_lines, 2), st.wrap_mode == "greedy"), size, st)]
        lays = ok
    return lays


def build_layouts_ex(text, st, size, pt_per_ft, shape_w=None, abbr=None):
    """-> (layouts to try in order for fitting inside the shape, offset layouts to try in order when the label moves outside).
    wrap off: one line. wrap width: one fixed wrapped layout (max width in ft or pt). wrap auto: 1 line, then 2..max_lines
    lines (balanced or greedy; `lines` forces a count; max_chars / min_width / max_width / fit_shape limit the line length);
    the first that fits inside the shape wins, an offset label uses the one-liner (wrapped only when max_width / max_chars ask).
    With abbrev 'fit' the abbreviated text's layouts follow the full ones: used only when the full text does not fit."""
    text = " ".join(text.split())
    words = tokens(text, st)
    wf = lambda s: measure(s, size, st)
    one = make_layout([text], size, st)
    if st.wrap == "off" or len(words) < 2:
        lays, offs = [one], [one]
    else:
        W = _width_limit(st, shape_w, pt_per_ft)
        lays = _variants(words, wf, st, size, W, pt_per_ft)
        if st.wrap == "width":
            offs = [lays[0]]
        else:
            ow = [x for x in (st.max_width or None,) if x]
            lim = ow[0] if ow else None
            off1 = _variants(words, wf, st, size, lim, pt_per_ft)
            offs = [off1[0]] if (lim or st.max_chars) else [one]
    if getattr(st, "abbrev", "off") == "fit" and abbr:
        short = abbreviate(text, abbr)
        if short != text:
            sw = tokens(short, st)
            s_one = make_layout([short], size, st)
            if st.wrap == "off" or len(sw) < 2:
                lays = lays + [s_one]
            else:
                lays = lays + _variants(sw, wf, st, size, _width_limit(st, shape_w, pt_per_ft), pt_per_ft)
            offs = offs + [s_one]
    return lays, offs


def build_layouts(text, st, size, pt_per_ft, shape_w=None, abbr=None):
    """-> (layouts, the layout used when the label has to be moved outside its shape); see build_layouts_ex."""
    lays, offs = build_layouts_ex(text, st, size, pt_per_ft, shape_w, abbr)
    return lays, offs[0]


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


def style_font_css(st):
    """font-family / style declarations of a Style (for texts written outside emit(): legend, numbered markers)."""
    fam = FALLBACK_STACK.get(st.font, f"'{st.font}'" if " " in st.font else st.font)
    return f"font-family:{fam};font-style:{'italic' if st.italic else 'normal'}"


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


def _small_caps_runs(t, size):
    """Text with lowercase letters set as smaller capitals (tspans with a reduced font size); no OpenType small-caps needed."""
    out, i = [], 0
    while i < len(t):
        low = t[i].islower()
        j = i
        while j < len(t) and t[j].islower() == low:
            j += 1
        seg = t[i:j]
        out.append(f'<tspan font-size="{size * SMALL_CAPS_RATIO:.2f}">{escape(seg.upper())}</tspan>' if low else escape(seg))
        i = j
    return "".join(out)


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
    body = (lambda t: _small_caps_runs(t, rec.size)) if st.small_caps else escape
    if n == 1:
        return head + body(rec.lines[0]) + "</text>"
    spans = "".join(f'<tspan x="{x:.2f}" dy="{0 if i == 0 else lh:.2f}">{body(t)}</tspan>' for i, t in enumerate(rec.lines))
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
