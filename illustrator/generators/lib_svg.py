"""Layered SVG writer for Illustrator line-art guides.

Units: user units are points (1/72 in) so the SVG opens at true size in Illustrator.
Each layer is <g id="Name" inkscape:groupmode="layer" inkscape:label="Name">.
"""
from xml.sax.saxutils import escape, quoteattr

DEFAULT_LAYERS = ["Grid", "Roads", "Walls", "Buildings", "Water", "Labels", "Notes"]


class LayeredSVG:
    def __init__(self, width_in=17, height_in=11, layers=None, stroke=0.5):
        self.w, self.h = width_in * 72.0, height_in * 72.0
        self.stroke = stroke
        self.layers = {n: [] for n in (layers or DEFAULT_LAYERS)}

    def _add(self, layer, s):
        self.layers.setdefault(layer, []).append(s)

    def _style(self, stroke_w=None, dash=None):
        sw = stroke_w or self.stroke
        d = f' stroke-dasharray="{dash}"' if dash else ""
        return f'fill="none" stroke="#000000" stroke-width="{sw}"{d}'

    def line(self, layer, x1, y1, x2, y2, **kw):
        self._add(layer, f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" {self._style(**kw)}/>')

    def rect(self, layer, x, y, w, h, **kw):
        self._add(layer, f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" {self._style(**kw)}/>')

    def polyline(self, layer, pts, closed=False, **kw):
        tag = "polygon" if closed else "polyline"
        p = " ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
        self._add(layer, f'<{tag} points="{p}" {self._style(**kw)}/>')

    def circle(self, layer, cx, cy, r, **kw):
        self._add(layer, f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" {self._style(**kw)}/>')

    def text(self, layer, x, y, s, size=9):
        self._add(layer, f'<text x="{x:.2f}" y="{y:.2f}" font-family="Arial" font-size="{size}" fill="#000000">{escape(s)}</text>')

    def scale_bar(self, x, y, feet_per_inch, total_feet, ticks=5, layer="Notes"):
        """Bar of total_feet length at the given scale (feet per paper inch)."""
        length = total_feet / feet_per_inch * 72.0
        self.line(layer, x, y, x + length, y, stroke_w=1)
        for i in range(ticks + 1):
            tx = x + length * i / ticks
            self.line(layer, tx, y - 4, tx, y + 4)
            self.text(layer, tx - 4, y + 15, f"{total_feet * i / ticks:g}", size=7)
        self.text(layer, x + length + 8, y + 3, f"ft  (1 in = {feet_per_inch:g} ft)", size=8)

    def write(self, path):
        out = [f'<?xml version="1.0" encoding="UTF-8"?>',
               f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
               f'width="{self.w:g}pt" height="{self.h:g}pt" viewBox="0 0 {self.w:g} {self.h:g}">']
        for name, items in self.layers.items():
            a = quoteattr(name)
            out.append(f'<g id={a} inkscape:groupmode="layer" inkscape:label={a}>')
            out.extend("  " + i for i in items)
            out.append("</g>")
        out.append("</svg>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


class LayerTree:
    """Nested layered SVG (layer groups may contain sublayer groups, to any depth).

    `spec` lists layers TOP to BOTTOM as Illustrator's Layers panel shows them:
    [("NOTES", []), ("LABELS", ["Labels - Districts", ...]), ("LINES", ["Walls", ("Terrain", ["Contours - Minor"])])].
    A sublayer is either a name or a (name, sublayers) tuple. The SVG is written
    bottom-first (later groups paint on top), so the panel order matches `spec`.
    Items are raw SVG strings added to a layer by name (names must be unique).
    A parent layer's own items are written after (on top of) its sublayers.
    """

    def __init__(self, spec, width_in=17, height_in=11, css="", locked=()):
        self.w, self.h = width_in * 72.0, height_in * 72.0
        self.spec, self.css, self.locked = spec, css, set(locked)
        self.items = {}
        self._register(spec)

    def _register(self, nodes):
        for node in nodes:
            name, subs = self._split(node)
            if name in self.items:
                raise ValueError(f"duplicate layer name: {name}")
            self.items[name] = []
            self._register(subs)

    @staticmethod
    def _split(node):
        return (node, []) if isinstance(node, str) else (node[0], node[1])

    def add(self, layer, svg):
        self.items[layer].append(svg)

    def _group(self, name, body, out, indent):
        a = quoteattr(name)
        lock = ' sodipodi:insensitive="true"' if name in self.locked else ""
        out.append(f'{indent}<g id={a} inkscape:groupmode="layer" inkscape:label={a}{lock}>')
        out.extend(body)
        out.append(f"{indent}</g>")

    def _emit(self, node, out, depth):
        name, subs = self._split(node)
        ind = "  " * depth
        body = []
        for s in reversed(subs):
            self._emit(s, body, depth + 1)
        body.extend(ind + "  " + i for i in self.items[name])
        self._group(name, body, out, ind)

    def write(self, path):
        out = ['<?xml version="1.0" encoding="UTF-8"?>',
               f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
               f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" '
               f'width="{self.w:g}pt" height="{self.h:g}pt" viewBox="0 0 {self.w:g} {self.h:g}">']
        if self.css:
            out.append(f"<style><![CDATA[\n{self.css}\n]]></style>")
        for node in reversed(self.spec):
            self._emit(node, out, 0)
        out.append("</svg>")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")
