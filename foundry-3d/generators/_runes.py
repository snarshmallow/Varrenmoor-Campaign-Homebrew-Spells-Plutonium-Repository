"""Elder Futhark runes as stroke geometry, for carvings and chalk marks (imported by generators).

Each rune is a list of line segments in a unit cell: x in 0..1, y in 0..2 (a stave runs 0..2). `place()` turns each segment into a thin
box, oriented in the plane of a wall ('n','s','e','w': the side the viewer stands on) or of the floor ('up'), so runes can be carved
(grooves or raised glow) or chalked. Strokes sit a few millimetres proud of the surface (faces never share a plane).
"""
import math

RUNES = {
    "fehu": [((0.5, 0), (0.5, 2)), ((0.5, 1.35), (0.95, 1.85)), ((0.5, 0.8), (0.95, 1.3))],
    "uruz": [((0.1, 0), (0.1, 2)), ((0.1, 2), (0.8, 1.4)), ((0.8, 1.4), (0.8, 0))],
    "thurisaz": [((0.3, 0), (0.3, 2)), ((0.3, 1.5), (0.9, 1.0)), ((0.9, 1.0), (0.3, 0.5))],
    "ansuz": [((0.3, 0), (0.3, 2)), ((0.3, 2), (0.9, 1.5)), ((0.3, 1.4), (0.9, 0.9))],
    "raidho": [((0.2, 0), (0.2, 2)), ((0.2, 2), (0.85, 1.5)), ((0.85, 1.5), (0.2, 1.0)), ((0.2, 1.0), (0.85, 0))],
    "kenaz": [((0.85, 1.7), (0.2, 1.0)), ((0.2, 1.0), (0.85, 0.3))],
    "gebo": [((0.1, 0), (0.9, 2)), ((0.1, 2), (0.9, 0))],
    "wunjo": [((0.3, 0), (0.3, 2)), ((0.3, 2), (0.9, 1.5)), ((0.9, 1.5), (0.3, 1.0))],
    "hagalaz": [((0.15, 0), (0.15, 2)), ((0.85, 0), (0.85, 2)), ((0.15, 1.3), (0.85, 0.7))],
    "nauthiz": [((0.5, 0), (0.5, 2)), ((0.15, 1.3), (0.85, 0.75))],
    "isa": [((0.5, 0), (0.5, 2))],
    "jera": [((0.5, 1.9), (0.15, 1.45)), ((0.15, 1.45), (0.5, 1.0)), ((0.5, 1.0), (0.85, 0.55)), ((0.85, 0.55), (0.5, 0.1))],
    "eihwaz": [((0.5, 0), (0.5, 2)), ((0.5, 2), (0.9, 1.6)), ((0.5, 0), (0.1, 0.4))],
    "perthro": [((0.2, 0), (0.2, 2)), ((0.2, 2), (0.8, 1.45)), ((0.8, 1.45), (0.2, 1.0)), ((0.2, 1.0), (0.8, 0.45)), ((0.8, 0.45), (0.2, 0))],
    "algiz": [((0.5, 0), (0.5, 2)), ((0.5, 1.2), (0.1, 2)), ((0.5, 1.2), (0.9, 2))],
    "sowilo": [((0.8, 2), (0.2, 1.3)), ((0.2, 1.3), (0.8, 0.7)), ((0.8, 0.7), (0.2, 0))],
    "tiwaz": [((0.5, 0), (0.5, 2)), ((0.5, 2), (0.1, 1.4)), ((0.5, 2), (0.9, 1.4))],
    "berkano": [((0.2, 0), (0.2, 2)), ((0.2, 2), (0.8, 1.5)), ((0.8, 1.5), (0.2, 1.0)), ((0.2, 1.0), (0.8, 0.5)), ((0.8, 0.5), (0.2, 0))],
    "ehwaz": [((0.1, 0), (0.1, 2)), ((0.9, 0), (0.9, 2)), ((0.1, 2), (0.5, 1.2)), ((0.9, 2), (0.5, 1.2))],
    "mannaz": [((0.1, 0), (0.1, 2)), ((0.9, 0), (0.9, 2)), ((0.1, 2), (0.9, 1.0)), ((0.9, 2), (0.1, 1.0))],
    "laguz": [((0.3, 0), (0.3, 2)), ((0.3, 2), (0.85, 1.5))],
    "ingwaz": [((0.1, 1.0), (0.5, 2.0)), ((0.5, 2.0), (0.9, 1.0)), ((0.9, 1.0), (0.5, 0.0)), ((0.5, 0.0), (0.1, 1.0))],
    "dagaz": [((0.1, 0), (0.1, 2)), ((0.9, 0), (0.9, 2)), ((0.1, 2), (0.9, 0)), ((0.1, 0), (0.9, 2))],
    "othala": [((0.1, 1.0), (0.5, 2.0)), ((0.5, 2.0), (0.9, 1.0)), ((0.1, 1.0), (0.9, 0.0)), ((0.9, 1.0), (0.1, 0.0))],
}
NAMES = list(RUNES)


def put(k, mat, name, center, face, h=0.5, width=0.035, thick=0.012, offset=0.0, rot_deg=0.0, mirror=False):
    """Place one rune. center = (x, y, z) world point on the surface; face 'n'/'s'/'e'/'w' = side the viewer stands on (wall), or
    'up' for the floor. h = rune height in metres (width of the cell is h/2). offset moves it off the surface (rune is proud by thick/2).
    rot_deg turns it in its own plane (positive = counter-clockwise as the viewer sees it)."""
    cx, cy, cz = center
    s = h / 2.0                                   # unit cell is 1 wide x 2 tall
    ca, sa = math.cos(math.radians(rot_deg)), math.sin(math.radians(rot_deg))
    for (x1, y1), (x2, y2) in RUNES[name]:
        # local plane coords (a right, b up), centred on the cell
        pts = []
        for (x, y) in ((x1, y1), (x2, y2)):
            a, b = (x - 0.5) * s * (-1 if mirror else 1), (y - 1.0) * s
            pts.append((a * ca - b * sa, a * sa + b * ca))
        (a1, b1), (a2, b2) = pts
        am, bm = (a1 + a2) / 2, (b1 + b2) / 2
        length = math.hypot(a2 - a1, b2 - b1) + width * 0.9
        ang = math.degrees(math.atan2(b2 - b1, a2 - a1))
        n_off = offset + thick / 2
        if face == "s":        # wall faces south; viewer looks north: right = +x
            loc = (cx + am, cy - n_off, cz + bm)
            k.box((length, thick, width), loc=loc, rot=(0, -ang, 0), material=mat, name=f"rune_{name}")
        elif face == "n":      # wall faces north; viewer looks south: right = -x
            loc = (cx - am, cy + n_off, cz + bm)
            k.box((length, thick, width), loc=loc, rot=(0, ang, 0), material=mat, name=f"rune_{name}")
        elif face == "e":      # wall faces east; viewer looks west: right = +y
            loc = (cx + n_off, cy + am, cz + bm)
            k.box((thick, length, width), loc=loc, rot=(ang, 0, 0), material=mat, name=f"rune_{name}")
        elif face == "w":      # wall faces west; viewer looks east: right = -y
            loc = (cx - n_off, cy - am, cz + bm)
            k.box((thick, length, width), loc=loc, rot=(-ang, 0, 0), material=mat, name=f"rune_{name}")
        else:                  # floor, viewed from above with north up
            loc = (cx + am, cy + bm, cz + n_off)
            k.box((length, width, thick), loc=loc, rot=(0, 0, ang), material=mat, name=f"rune_{name}")


def chevron(k, mat, center, heading_deg, size=0.6, width=0.07, thick=0.01):
    """A flat floor arrow (a chevron: two strokes) pointing along heading_deg (0 = east, 90 = north)."""
    cx, cy, cz = center
    for sgn in (-1, 1):
        a = math.radians(heading_deg + 180 + sgn * 35)
        ex, ey = cx + math.cos(math.radians(heading_deg)) * size * 0.5, cy + math.sin(math.radians(heading_deg)) * size * 0.5
        mx, my = ex + math.cos(a) * size * 0.5, ey + math.sin(a) * size * 0.5
        k.box((size, width, thick), loc=(mx, my, cz + thick / 2), rot=(0, 0, math.degrees(a) + 0.0), material=mat, name="route_chevron")
