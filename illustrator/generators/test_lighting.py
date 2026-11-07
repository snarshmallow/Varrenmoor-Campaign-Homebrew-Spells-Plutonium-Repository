"""Numeric checks for lighting.py (no world files needed):  python illustrator/generators/test_lighting.py"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lighting as lt  # noqa: E402

fails = 0


def check(name, cond, extra=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name, extra if not cond else "")
    fails += 0 if cond else 1


def flat_scene(buildings, size=400, cell=10, z=100.0, pitch=False):
    n = size // cell + 1
    return lt.Scene(np.full((n, n), z, np.float32), cell, buildings, pitch)


def box(x0, y0, x1, y1, h):
    return {"id": "b", "poly": [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], "height": h, "pitch": 0.0}


def shadow_mask(vis, win, thresh=0.5):
    return vis < thresh


CFG = lt.load_config({"shadow": {"max_length_ft": 400}})
PPF = 4.0
win = lt.Grid.window(0, 0, 400, 400, PPF)
X, Y = win.world()


def sun(az, alt, scene, soft=0.0):
    return lt.sun_visibility(scene, win, {"azimuth": az, "altitude": alt, "softness": soft}, 400.0)


# 1. shadow length of a 20 ft box at altitude 30 is 20 / tan(30) = 34.64 ft; sun in the south (180) -> shadow to the north (-y)
sc = flat_scene([box(180, 180, 220, 220, 20.0)])
v = sun(180, 30, sc)
col = int(200 * PPF)
shaded = np.flatnonzero(v[:, col] < 0.5)
y_top_shadow = Y[shaded.min(), col]
exp = 180 - 20 / math.tan(math.radians(30))
check("sun south alt 30: shadow reaches 20/tan(30) ft past the north wall", abs(y_top_shadow - exp) < 1.0, f"{y_top_shadow:.2f} vs {exp:.2f}")
check("shadow lies north of the box, none south of it", Y[shaded, col].max() <= 220.5 and not (v[int(240 * PPF):, col] < 0.5).any())
# other altitudes
for alt in (15, 45, 60):
    v = sun(180, alt, sc)
    s = np.flatnonzero(v[:, col] < 0.5)
    e = 180 - 20 / math.tan(math.radians(alt))
    check(f"shadow length alt {alt}", abs(Y[s.min(), col] - e) < 1.2, f"{Y[s.min(), col]:.2f} vs {e:.2f}")
# 2. compass convention: sun in the east (90) -> shadow falls west; sun north (0) -> shadow south; sun west (270) -> east
for az, axis, sign in ((90, "x", -1), (0, "y", 1), (270, "x", 1), (180, "y", -1)):
    v = sun(az, 30, sc)
    m = v < 0.5
    cx, cy = X[m].mean(), Y[m].mean()
    d = (cx - 200) if axis == "x" else (cy - 200)
    check(f"azimuth {az}: shadow centroid on the {'-' if sign < 0 else '+'}{axis} side", d * sign > 5, f"d={d:.1f}")
# diagonal: sun in the south-west (225) -> shadow to the north-east (+x, -y)
v = sun(225, 30, sc)
m = v < 0.5
check("azimuth 225 casts toward north-east", X[m].mean() > 200 and Y[m].mean() < 200)
# length along a diagonal ray: far tip distance
tip = np.hypot(*(np.array([X[m][np.argmax((X[m] - 200) - (Y[m] - 200))], Y[m][np.argmax((X[m] - 200) - (Y[m] - 200))]]) - 200))
check("diagonal shadow reaches at least h/tan(alt) from the wall", tip > 20 / math.tan(math.radians(30)))
# 3. deterministic
check("deterministic", np.array_equal(sun(225, 30, sc), sun(225, 30, sc)))
# 4. softness widens the penumbra with distance but keeps the umbra start
hard, soft = sun(180, 30, sc, 0.0), sun(180, 30, sc, 1.0)
check("soft shadow has more partial pixels", ((soft > 0.05) & (soft < 0.95)).sum() > 3 * ((hard > 0.05) & (hard < 0.95)).sum())
# 5. max length cuts the shadow
cfg2 = lt.load_config({"shadow": {"max_length_ft": 15}})
vcut = lt.sun_visibility(sc, win, {"azimuth": 180, "altitude": 30, "softness": 0}, 15.0)
sh = np.flatnonzero(vcut[:, col] < 0.5)
check("max shadow length respected", 180 - Y[sh.min(), col] < 15.6, f"{180 - Y[sh.min(), col]:.1f}")

# 6. slope facing away from a low sun is shadowed, slope facing it is lit
n = 41
ii, jj = np.mgrid[0:n, 0:n]
ramp_up_east = (100 + jj * 10 * math.tan(math.radians(45))).astype(np.float32)   # rises toward +x: faces west
rs = lt.Scene(ramp_up_east, 10, [], False)
ve = lt.sun_visibility(rs, win, {"azimuth": 90, "altitude": 20, "softness": 0}, 4000.0)       # sun in the east: slope faces away
vw = lt.sun_visibility(rs, win, {"azimuth": 270, "altitude": 20, "softness": 0}, 400.0)     # sun in the west: slope faces it
mid = (slice(100, 300), slice(100, 300))
check("slope facing away from the sun is shadowed", ve[mid].mean() < 0.05, f"{ve[mid].mean():.3f}")
check("slope facing the sun is lit", vw[mid].mean() > 0.95, f"{vw[mid].mean():.3f}")
vflat = lt.sun_visibility(flat_scene([]), win, {"azimuth": 90, "altitude": 20, "softness": 0}, 400.0)
check("flat ground has no shadow", vflat.min() > 0.99)
# a hill shades what lies behind it (terrain outside the view window still casts in)
hill = np.full((n, n), 100.0, np.float32)
hill[:, 30:] += 200.0                                                         # tall plateau east of x = 300
hs = lt.Scene(hill, 10, [], False)
w2 = lt.Grid.window(0, 0, 200, 200, PPF)
vh = lt.sun_visibility(hs, w2, {"azimuth": 90, "altitude": 30, "softness": 0}, 400.0)
check("a ridge outside the window shades it", vh.mean() < 0.05, f"{vh.mean():.3f}")

# 7. point light: shadow points away from the light; nothing is shadowed on the lit side
sc2 = flat_scene([box(150, 190, 160, 210, 10.0)])
L = {"x": 100.0, "y": 200.0, "height": 12.0, "radius": 150.0, "softness": 0.0}
vp, fall = lt.point_fields(sc2, win, L, CFG)
m = (vp < 0.5) & (fall > 0.05)
check("point light shadow exists", m.sum() > 50)
check("point light shadow lies on the far side of the box", X[m].min() > 150 and abs(Y[m].mean() - 200) < 6, f"x min {X[m].min():.1f}")
# similar triangles: top of box at 10 ft, 50..60 ft from a 12 ft light: shadow starts at wall x=160, ends at 100 + 60*12/(12-10) = 460 -> clipped by radius
check("point light: lit side stays lit", (vp[:, : int(140 * PPF)] > 0.95)[fall[:, : int(140 * PPF)] > 0.05].all())
L2 = dict(L, height=14.0, radius=230.0)
vp2, f2 = lt.point_fields(sc2, win, L2, CFG)
m2 = (vp2 < 0.5) & (f2 > 0.0005)
# height 14, box top 10 at distance 60 -> shadow ends at 100 + 60 * 14 / 4 = 310 ft
far = X[m2].max()
check("point light shadow tip from similar triangles (310 ft)", abs(far - 310) < 16, f"tip x={far:.1f}")
# falloff: zero beyond radius, 1 at the light
check("falloff zero outside radius", fall[(np.hypot(X - 100, Y - 200) > 150)].max() == 0.0)
# 8. illumination composition: night with only a lantern
night = lt.load_config({"ambient": 0.1, "lights": [{"type": "point", "x": 100, "y": 200, "height": 12, "radius": 100, "intensity": 1.0, "softness": 0.2}]})
f = lt.render_fields(sc2, win, night, log=lambda *_: None)
near = f["illum"][int(200 * PPF) + 12, int(110 * PPF)]
farp = f["illum"][int(20 * PPF), int(350 * PPF)]
check("lantern lights its surroundings and the rest stays dark", near > 0.8 and abs(farp - 0.1) < 0.01, f"{near:.2f} {farp:.2f}")
print("fails:", fails)
sys.exit(1 if fails else 0)
