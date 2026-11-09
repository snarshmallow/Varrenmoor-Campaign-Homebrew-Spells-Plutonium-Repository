"""Offline APPROXIMATE lit preview of a pack under a sun/shadow/fog preset (the panel's "live preview image"). Not Foundry's renderer.

Plan view of the pack's terrain (albedo + height map) and building footprints extruded to their heights, lit with Lambert shading from the sun's compass bearing and
altitude, hard cast shadows by marching the height field toward the sun, ambient + a constant sky-fill term (3D Canvas also lights from the skybox), ACES tone mapping
at the sun-strength exposure, and the fog blended by distance from a camera at the south edge (linear: starts 1000 px, ends at fogDistance px, like THREE.Fog).
Fast (about 1 s) and small (stays under ~100 MB: arrays of about 360 x 310 floats). Trees and the module's own shadow filtering are NOT modelled, so shadows are a guide
to direction and length, not a copy of Foundry.
Where a live OpenGL fly-through panel would plug in later: replace render() with a call into that viewer and keep the same args (preset dict in, RGB image out).

  python illustrator/generators/sun_preview.py render --place bridgehollow__dyers_walk_local --preset warm_sunset --out out.png [--sun-azimuth 250 ...]
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_sun as fs  # noqa: E402

REPO = fs.REPO
PX_PER_FT = 20.0               # 100 px per 5 ft grid square
SKY_FILL = 0.28                # stand-in for the skybox image light that 3D Canvas adds to every surface
MAX_SHADOW_FT = 260.0
W, H = 640, 520
PLAN_H = 400                    # plan view area; the sky strip sits below it
SKY_STRIP_H = 112


def hex_rgb(s):
    s = s.lstrip("#")
    return np.array([int(s[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def aces(x):
    return np.clip((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0, 1)


def load_pack(place, step_ft=1.0):
    """-> terrain height (ft) and albedo (linear rgb) at step_ft, building height field (ft above terrain), roof mask. All [ny][nx], y south."""
    from PIL import Image, ImageDraw
    pack = os.path.join(REPO, "world", place, "export")
    man = json.load(open(os.path.join(pack, "manifest.json"), encoding="utf-8"))
    t = man["terrain"]
    ext = man["extent"]
    wft, hft = float(ext["width_ft"]), float(ext["height_ft"])
    nx, ny = int(wft / step_ft), int(hft / step_ft)
    hm = np.load(os.path.join(pack, "terrain", "heightmap_f32.npy")).astype(np.float32)
    cell = float(t["cell_ft"])
    ys, xs = (np.arange(ny) * step_ft / cell), (np.arange(nx) * step_ft / cell)
    ys, xs = np.clip(ys, 0, hm.shape[0] - 1.001), np.clip(xs, 0, hm.shape[1] - 1.001)
    i0, j0 = ys.astype(int), xs.astype(int)
    fy, fx = (ys - i0)[:, None], (xs - j0)[None, :]
    ter = (hm[i0][:, j0] * (1 - fy) * (1 - fx) + hm[i0 + 1][:, j0] * fy * (1 - fx) + hm[i0][:, j0 + 1] * (1 - fy) * fx + hm[i0 + 1][:, j0 + 1] * fy * fx)
    try:
        al = Image.open(os.path.join(pack, "terrain", "albedo.png")).convert("RGB").resize((nx, ny), Image.BILINEAR)
        alb = srgb_to_lin(np.asarray(al, dtype=np.float32) / 255.0)
    except OSError:
        alb = np.empty((ny, nx, 3), np.float32)
        alb[:] = srgb_to_lin(hex_rgb("#6f8f4a"))
    bh = np.zeros((ny, nx), np.float32)
    try:
        b = json.load(open(os.path.join(pack, "entities", "buildings.json"), encoding="utf-8"))["items"]
    except (OSError, ValueError, KeyError):
        b = []
    for it in b:
        poly = it.get("polygon") or []
        if len(poly) < 3:
            continue
        m = Image.new("L", (nx, ny), 0)
        ImageDraw.Draw(m).polygon([(x / step_ft, y / step_ft) for x, y in poly], fill=255)
        mk = np.asarray(m) > 0
        bh[mk] = np.maximum(bh[mk], float(it.get("height_ft", 12.0)))
    return ter.astype(np.float32), alb, bh, step_ft, (wft, hft)


def shade(ter, alb, bh, step_ft, p):
    sun, am, fg = p["sun"], p["ambient"], p.get("fog") or {}
    az, alt = math.radians(float(sun["azimuth"])), math.radians(max(0.5, float(sun["altitude"])))
    surf = ter + bh                                              # roofs sit on top of the terrain
    # normals from the terrain gradient (buildings read as flat roofs)
    gy, gx = np.gradient(ter, step_ft)
    n = np.stack([-gx, -gy, np.ones_like(gx)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    # to-sun vector in map axes (x east, y south, z up)
    L = np.array([math.sin(az) * math.cos(alt), -math.cos(az) * math.cos(alt), math.sin(alt)])
    lam = np.clip((n * L).sum(-1), 0, 1)
    # hard shadows: march toward the sun, stop at the first sample that rises above the ray
    ny, nx = surf.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    shadow = np.zeros((ny, nx), bool)
    d = np.array([L[0], L[1]]) / max(1e-6, math.hypot(L[0], L[1]))
    tan_alt = math.tan(alt)
    for k in range(1, int(MAX_SHADOW_FT / step_ft)):
        sx, sy = np.round(xx + d[0] * k).astype(int), np.round(yy + d[1] * k).astype(int)
        ok = (sx >= 0) & (sx < nx) & (sy >= 0) & (sy < ny)
        h = surf[np.clip(sy, 0, ny - 1), np.clip(sx, 0, nx - 1)]
        shadow |= ok & (h > surf + k * step_ft * tan_alt + 0.3)
    sun_rgb = srgb_to_lin(hex_rgb(sun.get("color", "#ffffff"))) * float(sun.get("strength", 1.2))
    amb_rgb = srgb_to_lin(hex_rgb(am.get("color", "#ffffff"))) * (float(am.get("intensity", 0.1)) + SKY_FILL)
    roof = srgb_to_lin(hex_rgb("#8c6e58"))
    base = np.where((bh > 0)[..., None], roof[None, None, :], alb)
    sh_on = bool((p.get("shadows") or {}).get("on", True))
    sunterm = (lam * (~shadow if sh_on else 1))[..., None] * sun_rgb[None, None, :]
    col = base * (amb_rgb[None, None, :] + sunterm)
    col = aces(col * float(sun.get("strength", 1.2)) ** 0.5)
    col = lin_to_srgb(col)
    if fg.get("enabled"):                                        # camera at the south edge, looking north: distance = rows from the bottom
        far = float(fg.get("far_px", 30000))
        dist_px = (ny - yy) * step_ft * PX_PER_FT
        f = np.clip((dist_px - 1000.0) / max(1.0, far - 1000.0), 0, 1)[..., None]
        col = col * (1 - f) + hex_rgb(fg.get("color", "#c9dcee")) * f
    return col, float(shadow.mean())


def sky_strip(p, w=W - 20, rows=SKY_STRIP_H):
    """RGB strip of the sky the scene gets (skybox.sky_dome at the preset's sun/moon bearing + altitude), elevation -5..60 deg, azimuth 0..360 compass, with the
    light body marked: shadows on the ground point away from this spot. Returns (image, (x, y) of the body in the strip or None)."""
    import skybox
    from PIL import Image
    sp = (p.get("sky") or {}).get("preset")
    if not sp or sp not in skybox.PRESETS:
        return None, None
    az, alt = float(p["sun"]["azimuth"]), float(p["sun"]["altitude"])
    P = skybox.sky_params(sp, {"sun_az": az - 90.0, "sun_el": alt})
    d = skybox.sky_dome(P, 720)
    lin = d["sky"]
    img = skybox.lin_to_srgb(lin / (1 + 0.15 * lin))
    Hh = d["Hh"]
    r0, r1 = int((90 - 60) / 180 * Hh), int((90 + 5) / 180 * Hh)
    strip = img[r0:r1]
    # columns: image centre = east (compass 90); roll so compass 0 (north) is the left edge
    strip = np.roll(strip, -int(round((0.5 - 90 / 360.0) * 720)), axis=1)       # source column c has compass bearing (c/720 - 0.5)*360 + 90
    pic = Image.fromarray((np.clip(strip * 1.06, 0, 1) * 255).astype(np.uint8)).resize((w, rows), Image.BILINEAR)
    x = (az % 360) / 360.0 * w
    y = (60 - max(-5.0, min(60.0, alt))) / 65.0 * rows
    return pic, (x, y)


def render(place, p, out, w=W, h=H):
    from PIL import Image, ImageDraw
    ter, alb, bh, step, (wft, hft) = load_pack(place)
    col, frac = shade(ter, alb, bh, step, p)
    img = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8))
    s = min((w - 20) / img.width, (PLAN_H - 56) / img.height)
    img = img.resize((int(img.width * s), int(img.height * s)), Image.BILINEAR)
    sun, fg = p["sun"], p.get("fog") or {}
    sky_top = hex_rgb((p.get("sky_preview") or {}).get("top", "#3a6fb5")) if False else None
    canvas = Image.new("RGB", (w, h), (28, 30, 36))
    canvas.paste(img, (10, 10))
    d = ImageDraw.Draw(canvas)
    x0 = 10 + img.width + 14
    d.text((x0, 12), "APPROXIMATE preview", fill=(255, 210, 120))
    d.text((x0, 26), "not Foundry's renderer", fill=(180, 180, 190))
    d.text((x0, 52), f"sun {sun['azimuth']:.0f} deg bearing", fill=(220, 220, 230))
    d.text((x0, 66), f"altitude {sun['altitude']:.0f} deg", fill=(220, 220, 230))
    d.text((x0, 80), f"strength {sun['strength']:.2f}", fill=(220, 220, 230))
    d.text((x0, 94), f"ambient {p['ambient']['intensity']:.2f}", fill=(220, 220, 230))
    d.text((x0, 108), f"shadow area {frac * 100:.0f}%", fill=(220, 220, 230))
    d.text((x0, 122), "fog " + (f"on, far {int(fg.get('far_px', 0))} px" if fg.get("enabled") else "off"), fill=(220, 220, 230))
    for i, (c, lab) in enumerate(((sun.get("color", "#fff"), "sun"), (p["ambient"].get("color", "#fff"), "ambient"), (fg.get("color", "#ccc"), "fog"))):
        d.rectangle([x0, 144 + i * 26, x0 + 30, 164 + i * 26], fill=c, outline=(90, 90, 100))
        d.text((x0 + 38, 148 + i * 26), lab, fill=(200, 200, 210))
    d.text((10, PLAN_H - 36), "plan view, north up, terrain + building roofs; trees are not drawn", fill=(150, 150, 160))
    d.text((10, PLAN_H - 22), f"{p.get('label', p.get('id', ''))}: shadows fall away from the sun", fill=(150, 150, 160))
    strip, mark = sky_strip(p, w - 20)
    if strip is not None:                                          # sky strip: where the sun / moon is drawn in the skybox (same bearing + altitude as the light)
        d.text((10, PLAN_H - 4), "sky (compass 0..360 left to right, 5 below to 60 above the horizon); the light body is circled", fill=(150, 150, 160))
        canvas.paste(strip, (10, PLAN_H + 10))
        mx, my = 10 + mark[0], PLAN_H + 10 + mark[1]
        d.ellipse([mx - 9, my - 9, mx + 9, my + 9], outline=(255, 80, 80), width=2)
        for tx, lab in ((0, "N"), (0.25, "E"), (0.5, "S"), (0.75, "W")):
            d.text((12 + tx * (w - 20), PLAN_H + 12), lab, fill=(255, 255, 255))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    canvas.save(out)
    return {"ok": True, "out": out, "shadow_fraction": round(frac, 3), "size": [w, h]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render"])
    fs.add_sun_args(ap)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    try:
        p = fs.apply_overrides(fs.get_preset(a.preset or fs.DEFAULT_PRESET), a)
        res = render(a.place, p, a.out)
    except (ValueError, OSError, KeyError) as e:
        res = {"ok": False, "error": f"{e.__class__.__name__}: {e}"}
    print(json.dumps(res), flush=True)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
