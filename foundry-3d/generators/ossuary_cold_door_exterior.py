"""Session 14, B3 exterior strip: 10 x 30 ft beyond the cold door (x 45..55 ft of the terminal scene). Packed snow against the
outside of the wall, the edge of a dark pine road, a few pines and rocks. Its own tile so the GM can hide it until the door opens.
Corner markers pin the bounding box to (13.716, 0.1) .. (16.864, -9.244) m in the terminal scene's model frame.
"""
import math

from _props import F, Shop

FOLDER = "Act 2 Road to Bridgehollow/Ossuary Exchange"
SCENE_NOTE = "Cold door exterior strip (hide until the door opens)."

FT = 0.3048
X0, X1, Y1 = 45 * FT, 55 * FT, -30 * FT

LIGHTS = [dict(x=50 * FT, y=-15 * FT, z=6.0, dim=30, bright=8, color="#a8c4ff")]   # cold blue moonlight, strip only


def build(k):
    S = Shop(k)
    M, B = S.M, S.B
    rng = k.rng
    snow = k.mat("snow", (0.86, 0.89, 0.94), roughness=0.9)
    road = k.mat("frozen_road", (0.18, 0.16, 0.15), roughness=0.95)
    pine = k.mat("pine_needles", (0.05, 0.13, 0.08), roughness=0.95)
    bark = k.mat("pine_bark", (0.16, 0.10, 0.06), roughness=0.95)
    rock = k.mat("rock", (0.28, 0.28, 0.30), roughness=0.9)
    B(X0, X0 + 0.01, 0.09, 0.1, 0, 0.01, M["soot"], "bbox_marker")
    B(X1 + 0.09, X1 + 0.1, Y1 - 0.1, Y1 - 0.09, 0, 0.01, M["soot"], "bbox_marker")

    B(X0, X1, Y1, 0, 0, F, snow, "packed_snow")
    B(X0 + 1.6, X1, Y1, 0, F, F + 0.02, road, "road_edge")                  # dark road along the east of the strip
    for i in range(6):                                                       # snow drifts against the wall
        y = -0.8 - i * 1.5
        k.sphere(0.7, loc=(X0 + 0.55, y, 0.32), scale=(0.7, 1.4, 0.45), material=snow, name="drift", segments=10)
    ey = -15 * FT
    B(X0 + 0.05, X0 + 1.4, ey - 0.8, ey + 0.8, F, F + 0.03, snow, "threshold_snow")
    for (x, y, h) in ((53.5, 3, 7.0), (52.0, 9, 5.5), (54.0, 24, 6.5), (51.5, 28, 5.0)):
        px, py = x * FT, -y * FT
        k.cylinder(0.12, 1.2, loc=(px, py, F + 0.6), material=bark, name="pine_trunk", verts=8)
        for j, f in enumerate((0.0, 0.3, 0.55)):
            r = 1.0 - 0.28 * j
            k.cone(r, 0.05, h * 0.45, loc=(px, py, F + 1.0 + h * f + h * 0.22), material=pine, name="pine_tier", verts=10)
            k.cone(r * 0.9, 0.04, 0.12, loc=(px, py, F + 1.0 + h * f + 0.1), material=snow, name="pine_snow", verts=10)
    for i in range(5):
        k.sphere(rng.uniform(0.2, 0.4), loc=(X0 + rng.uniform(0.8, 2.6), -rng.uniform(1.0, 8.0), 0.25), scale=(1.3, 1.0, 0.6), material=rock, name="rock", segments=8)
    S.finish()
