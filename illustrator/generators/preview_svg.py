"""Rasterise one of our layered SVGs to a PNG with PIL (no cairo needed). Preview only.

  python illustrator/generators/preview_svg.py in.svg out.png [--dpi 100] [--crop x0,y0,x1,y1 (page pt)] [--zoom 2]
Draws path/polygon outlines by class colour (buildings and squares lightly filled), skips hidden/locked layers' grid
unless --grid, and prints unrotated text.
"""
import argparse
import re
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

COL = {"wall": (20, 20, 20), "road": (60, 60, 60), "water": (26, 79, 138), "guide-line": (170, 170, 170),
       "guide-major": (140, 140, 140), "field": (110, 150, 70), "contour-minor": (200, 160, 120),
       "contour-index": (150, 100, 50), "contour-datum": (26, 79, 138), "contour-label": (110, 70, 35)}


def parse(svg, png, dpi=100, crop=None, grid=False, zoom=1.0):
    root = ET.parse(svg).getroot()
    ns = "{http://www.w3.org/2000/svg}"
    vb = [float(x) for x in root.get("viewBox").split()]
    s = dpi / 72.0 * zoom
    x0, y0, x1, y1 = crop or (0, 0, vb[2], vb[3])
    img = Image.new("RGB", (int((x1 - x0) * s), int((y1 - y0) * s)), (250, 247, 238))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()

    def pt(x, y):
        return ((x - x0) * s, (y - y0) * s)

    def walk(g, layer):
        for el in g:
            tag = el.tag.replace(ns, "")
            if tag == "g":
                walk(el, el.get("id") or layer)
                continue
            cls = (el.get("class") or "").split()
            c = next((COL[k] for k in cls if k in COL), (0, 0, 0))
            if tag == "path":
                if layer.startswith("Grid") and not grid:
                    continue
                for sub in re.findall(r"M[^M]*", el.get("d")):
                    pts = [tuple(map(float, m)) for m in re.findall(r"(-?[\d.]+),(-?[\d.]+)", sub)]
                    if len(pts) < 2:
                        continue
                    q = [pt(*p) for p in pts]
                    closed = sub.strip().endswith("Z")
                    fill = None
                    if layer == "Buildings":
                        fill = (205, 190, 170)
                    elif layer == "Roads" and "road" in cls and closed:
                        fill = (236, 228, 208)
                    elif layer == "Water":
                        fill = (190, 215, 240)
                    if closed and fill:
                        d.polygon(q, fill=fill)
                    d.line(q + ([q[0]] if closed else []), fill=c, width=1)
            elif tag == "text":
                if el.get("transform") or layer == "Labels - Elevation":
                    continue
                x, y = pt(float(el.get("x")), float(el.get("y")))
                tx = el.text or ""
                w = d.textlength(tx, font=font)
                d.text((x - w / 2 if el.get("text-anchor") == "middle" else x, y - 8), tx, fill=c, font=font)

    walk(root, "")
    img.save(png)
    print("wrote", png, img.size)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("svg")
    ap.add_argument("png")
    ap.add_argument("--dpi", type=float, default=100)
    ap.add_argument("--zoom", type=float, default=1.0)
    ap.add_argument("--crop")
    ap.add_argument("--grid", action="store_true")
    a = ap.parse_args()
    parse(a.svg, a.png, a.dpi, tuple(float(v) for v in a.crop.split(",")) if a.crop else None, a.grid, a.zoom)
