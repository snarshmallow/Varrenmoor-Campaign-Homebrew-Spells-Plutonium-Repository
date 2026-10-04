"""Ossuary Market stall: weathered timber frame, sagging canopy, bone trim, wares on the counter.
Footprint about 2 x 1 grid squares (3.0 m x 1.5 m), about 2.6 m tall.
"""


def build(k):
    wood = k.mat("weathered_wood", (0.23, 0.16, 0.10), roughness=0.9)
    dark = k.mat("dark_wood", (0.12, 0.08, 0.05), roughness=0.85)
    bone = k.mat("bone", (0.82, 0.77, 0.63), roughness=0.6)
    canvas = k.mat("canopy", (0.30, 0.09, 0.08), roughness=0.95)
    candle = k.mat("candle", (0.95, 0.85, 0.6), roughness=0.5, emission=(1.0, 0.6, 0.25))

    w, d = 3.0, 1.5

    # Counter: body and top.
    k.box((w, 0.6, 0.95), loc=(0, -0.35, 0.475), material=wood, name="counter", bevel=0.01)
    k.box((w + 0.1, 0.75, 0.06), loc=(0, -0.35, 0.98), material=dark, name="counter_top", bevel=0.01)

    # Four posts: the front two are shorter so the canopy slopes.
    for x in (-w / 2 + 0.08, w / 2 - 0.08):
        k.box((0.1, 0.1, 2.3), loc=(x, -d / 2 + 0.08, 1.15), material=dark, name="post_front", bevel=0.005)
        k.box((0.1, 0.1, 2.6), loc=(x, d / 2 - 0.08, 1.30), material=dark, name="post_back", bevel=0.005)
        # A skull capping each front post.
        k.sphere(0.09, loc=(x, -d / 2 + 0.08, 2.38), scale=(1, 1.15, 1), material=bone, name="skull")

    # Sloped, sagging canopy.
    canopy = k.cloth((w + 0.3, d + 0.3), loc=(0, 0, 2.45), sag=0.18, material=canvas, name="canopy")
    canopy.rotation_euler = (0.2, 0, 0)

    # Bone garland along the front edge of the canopy.
    n = 11
    for i in range(n):
        x = -w / 2 + 0.15 + i * (w - 0.3) / (n - 1)
        k.cylinder(0.02, 0.22, loc=(x, -d / 2 - 0.05, 2.12 + k.jitter(0.03)), rot=(0, 90, k.jitter(25)),
                   material=bone, name="garland_bone", verts=8)

    # Wares: bone stacks, jars and a candle on the counter.
    for i in range(5):
        x = -1.1 + i * 0.5 + k.jitter(0.05)
        if i % 2 == 0:
            for j in range(3):
                k.cylinder(0.025, 0.35, loc=(x + k.jitter(0.04), -0.35 + j * 0.06, 1.04 + j * 0.03),
                           rot=(0, 90, k.jitter(30)), material=bone, name="ware_bone", verts=8)
        else:
            k.cylinder(0.08, 0.2, loc=(x, -0.3, 1.11), material=dark, name="ware_jar", verts=12)
    k.cylinder(0.025, 0.12, loc=(1.3, -0.5, 1.07), material=candle, name="candle", verts=8)
