"""Procedural skyboxes for Foundry 3D Canvas (equirectangular 2:1 images), with the mountain ring taken from the real terrain.

  python illustrator/generators/skybox.py generate [--place bridgehollow] [--presets clear_day,overcast,dusk,winter,night] [--viewer X,Y] [--width 2048]
  python illustrator/generators/skybox.py set-flag --scene-uuid Scene.xxx --preset clear_day [--apply]      # dry run unless --apply (writes scene flags via the bridge)

How it works. The viewer (default: the middle of the place, eye 6 ft above ground) casts one ray per image column through the place's heightmap
(world/<place>/terrain/heightmap.npy): the running maximum of the elevation angle along each ray is the true horizon, and the first sample whose angle
reaches a pixel's elevation is the terrain point that pixel sees, so every real peak, saddle and shoulder of the bowl is where it is on the map (colour by
height/slope: meadow, conifer, bare rock, snow line; sun lighting; haze with distance). Where a ray leaves the map without being blocked, up to three
procedural far ranges (ridged noise, never lower than 4 degrees so the bowl stays closed) sit behind the rim, progressively hazier. Sky: gradient,
sun/moon disc and glow, periodic fbm clouds, stars at night. Presets: clear_day, overcast, dusk, winter (snow cover), night.

Format (verified against the user's world): 3D Canvas takes a 2:1 equirect webp/png/jpg in scene flag flags.levels-3d-preview.exr (live scenes use
assets/skybox_church.png 1774x887, assets/ossuary-exchange-skybox3.webp, canvas3dcompendium Beautiful-Sky/2K/*.webp); `skybox` is the six-file cube alternative.
Image centre = world east, u growing clockwise from above (east -> south -> west -> north), the three.js equirect convention with scene x -> x, scene y -> z.
That mapping is UNVERIFIED in Foundry: use --yaw to rotate (positive turns the picture clockwise as seen from above).

Outputs: world/<place>/export/skybox/<preset>.webp (+ .png preview 1024 px) and skybox_manifest.json; previews copied by the caller to illustrator/out/skybox/.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
import worldpack_pbr as pbr  # noqa: E402  (fbm, blur)

H_SEA_FT = 0.0
EYE_FT = 6.0

# colours are sRGB 0..255; sun_el/sun_az in degrees (az from east, clockwise from above, like the image)
PRESETS = {
    "clear_day": dict(zenith="#2f6fc4", horizon="#b9d6ee", haze="#c6dcee", sun_el=42, sun_az=-40, sun_col="#fff4d8", sun_pow=1.0, cloud=0.48, cloud_col="#ffffff", cloud_shade="#aab8cc",
                      fog_ft=14000, snow_ft=1000, snow_all=False, light=1.0, ambient=0.42, tint="#ffffff", stars=0.0, moon=False),
    "overcast": dict(zenith="#7d8794", horizon="#b8bfc6", haze="#b4bbc2", sun_el=45, sun_az=-40, sun_col="#d8dde2", sun_pow=0.0, cloud=0.92, cloud_col="#c9ced4", cloud_shade="#6e7783",
                     fog_ft=6000, snow_ft=1040, snow_all=False, light=0.55, ambient=0.62, tint="#dfe4ea", stars=0.0, moon=False),
    "dusk": dict(zenith="#26305e", horizon="#f08a4b", haze="#d98a6a", sun_el=3, sun_az=-120, sun_col="#ffb061", sun_pow=1.0, cloud=0.45, cloud_col="#ffc38c", cloud_shade="#4a3a5e",
                 fog_ft=9000, snow_ft=1000, snow_all=False, light=0.8, ambient=0.28, tint="#ffd2b0", stars=0.15, moon=False),
    "winter": dict(zenith="#8fa6c0", horizon="#dfe6ee", haze="#d5dde7", sun_el=17, sun_az=-60, sun_col="#fff0dc", sun_pow=0.6, cloud=0.75, cloud_col="#eef2f6", cloud_shade="#9aa7b8",
                   fog_ft=5200, snow_ft=0, snow_all=True, light=0.8, ambient=0.55, tint="#eaf0f8", stars=0.0, moon=False),
    "night": dict(zenith="#03060f", horizon="#16233a", haze="#16233a", sun_el=-30, sun_az=-40, sun_col="#bcd0ff", sun_pow=0.0, cloud=0.25, cloud_col="#2c3a55", cloud_shade="#0b1220",
                  fog_ft=8000, snow_ft=1000, snow_all=False, light=0.18, ambient=0.16, tint="#7f97c8", stars=1.0, moon=True, moon_el=32, moon_az=-70),
}


def hexrgb(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float) / 255.0


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


# ------------------------------------------------------------------ terrain horizon
def load_heights(place, world_root=None):
    root = os.path.join(world_root or os.path.join(REPO, "world"), place, "terrain")
    h = np.load(os.path.join(root, "heightmap.npy")).astype(float)
    meta = json.load(open(os.path.join(root, "terrain_meta.json")))
    return h, float(meta["cell_ft"])


def bilinear(h, cell, x, y):
    fx = np.clip(x / cell, 0, h.shape[1] - 1.001)
    fy = np.clip(y / cell, 0, h.shape[0] - 1.001)
    j, i = fx.astype(int), fy.astype(int)
    tx, ty = fx - j, fy - i
    return (h[i, j] * (1 - tx) * (1 - ty) + h[i, j + 1] * tx * (1 - ty) + h[i + 1, j] * (1 - tx) * ty + h[i + 1, j + 1] * tx * ty)


def march_columns(h, cell, vx, vy, W, yaw_deg=0.0, d0=6.0, dmax=None, steps=520):
    """Per image column: sample distance d[k], elevation angle a[k] (radians) of the terrain point and the running maximum M[k]. Returns dict."""
    ny, nx = h.shape
    size_x, size_y = (nx - 1) * cell, (ny - 1) * cell
    dmax = dmax or math.hypot(max(vx, size_x - vx), max(vy, size_y - vy)) * 1.02
    k = np.arange(steps)
    d = d0 + (dmax - d0) * (k / (steps - 1.0)) ** 1.6            # denser near the viewer, where silhouettes change fastest
    u = (np.arange(W) + 0.5) / W
    az = (u - 0.5) * 2 * np.pi + math.radians(yaw_deg) * -1      # world azimuth of each column (from east, clockwise on the map)
    dx, dy = np.cos(az), np.sin(az)
    X = vx + dx[:, None] * d[None, :]
    Y = vy + dy[:, None] * d[None, :]
    inside = (X >= 0) & (X <= size_x) & (Y >= 0) & (Y <= size_y)
    Z = bilinear(h, cell, X, Y)
    zeye = float(bilinear(h, cell, np.array([vx]), np.array([vy]))[0]) + EYE_FT
    ang = np.arctan2(Z - zeye, d[None, :])
    ang = np.where(inside, ang, -np.pi / 2)
    M = np.maximum.accumulate(ang, axis=1)
    return dict(d=d, az=az, X=X, Y=Y, Z=Z, ang=ang, M=M, inside=inside, zeye=zeye, size=(size_x, size_y))


def terrain_normal(h, cell, X, Y):
    e = cell
    zx = (bilinear(h, cell, X + e, Y) - bilinear(h, cell, X - e, Y)) / (2 * e)
    zy = (bilinear(h, cell, X, Y + e) - bilinear(h, cell, X, Y - e)) / (2 * e)
    n = np.stack([-zx, -zy, np.ones_like(zx)], -1)          # world frame x east, y south, z up
    return n / np.linalg.norm(n, axis=-1, keepdims=True), np.degrees(np.arctan(np.hypot(zx, zy)))


# ------------------------------------------------------------------ rendering
def ridged_1d(W, seed, octaves=5, base_freq=3):
    rng = np.random.RandomState(seed)
    x = np.arange(W) / W
    out = np.zeros(W)
    amp = 1.0
    for o in range(octaves):
        f = base_freq * 2 ** o
        ph = rng.rand(3) * 2 * np.pi
        v = np.sin(2 * np.pi * f * x + ph[0]) + 0.6 * np.sin(2 * np.pi * (f * 1.7 + 0.3) * x + ph[1]) + 0.4 * np.sin(2 * np.pi * (f * 2.9) * x + ph[2])
        out += amp * (1 - np.abs(v / 2.0))
        amp *= 0.52
    out -= out.min()
    return out / max(out.max(), 1e-9)


def render(place, preset, viewer=None, W=2048, yaw_deg=0.0, seed=7, world_root=None, h=None, cell=None, sun=None):
    P = dict(PRESETS[preset], **(sun or {}))
    if h is None:
        h, cell = load_heights(place, world_root)
    ny, nx = h.shape
    size_x, size_y = (nx - 1) * cell, (ny - 1) * cell
    import place_stats
    ad = place_stats.place_adapt(place, h, 0.0, world_root)         # percentile-based snow / tree lines for places other than Bridgehollow
    rm = (lambda v: place_stats.remap(v, ad)) if ad else (lambda v: v)
    vx, vy = viewer or (size_x / 2, size_y / 2)
    Hh = W // 2
    mc = march_columns(h, cell, vx, vy, W, yaw_deg)
    el_deg = 90 - (np.arange(Hh) + 0.5) / Hh * 180            # row 0 = zenith
    el = np.radians(el_deg)
    cs = lambda c: srgb_to_lin(hexrgb(c))
    zen, hor, haze = cs(P["zenith"]), cs(P["horizon"]), cs(P["haze"])
    sun_el, sun_az = math.radians(P["sun_el"]), math.radians(P["sun_az"])
    sundir = np.array([math.cos(sun_el) * math.cos(sun_az), math.cos(sun_el) * math.sin(sun_az), math.sin(sun_el)])
    u = (np.arange(W) + 0.5) / W
    azc = (u - 0.5) * 2 * np.pi
    # ---- sky
    t = np.clip(el_deg / 90.0, 0, 1)[:, None, None]
    tt = t ** 0.55
    sky = hor[None, None, :] * (1 - tt) + zen[None, None, :] * tt
    sky = np.broadcast_to(sky, (Hh, W, 3)).copy()
    below = el_deg < 0
    sky[below] = haze * 0.9
    dirs = np.stack([np.cos(el)[:, None] * np.cos(azc)[None, :], np.cos(el)[:, None] * np.sin(azc)[None, :], np.broadcast_to(np.sin(el)[:, None], (Hh, W))], -1)
    cosang = np.clip(dirs @ sundir, -1, 1)
    if P["sun_el"] > -5:
        glow = np.exp((cosang - 1) * 90) * 0.55 + np.exp((cosang - 1) * 1500) * 0.6
        disc = np.clip((cosang - math.cos(math.radians(0.9))) * 4000, 0, 1) * 40
        sky += (glow * P["sun_pow"] + disc * (P["sun_pow"] > 0.2))[..., None] * cs(P["sun_col"])[None, None, :]
        if P["sun_el"] < 12:                                            # dusk: warm band along the horizon on the sun's side
            band = np.exp(-(el_deg / 9.0) ** 2)[:, None] * (0.5 + 0.5 * cosang)
            sky += band[..., None] * cs(P["sun_col"]) * 0.5
    if P.get("moon"):
        md = np.array([math.cos(math.radians(P["moon_el"])) * math.cos(math.radians(P["moon_az"])), math.cos(math.radians(P["moon_el"])) * math.sin(math.radians(P["moon_az"])),
                       math.sin(math.radians(P["moon_el"]))])
        cm = np.clip(dirs @ md, -1, 1)
        sky += (np.clip((cm - math.cos(math.radians(1.6))) * 2500, 0, 1) * 1.4 + np.exp((cm - 1) * 220) * 0.18)[..., None] * cs("#cfd8ff")[None, None, :]
    if P["stars"] > 0:
        rng = np.random.RandomState(seed + 5)
        n = int(2600 * P["stars"])
        yy = np.clip(((rng.rand(n) ** 0.7) * 0.5 * Hh).astype(int), 0, Hh - 1)
        xx = rng.randint(0, W, n)
        mag = rng.rand(n) ** 3
        for dy_, dx_ in ((0, 0), (0, 1), (1, 0)):
            np.add.at(sky, (np.clip(yy + dy_, 0, Hh - 1), (xx + dx_) % W), (0.15 + 1.2 * mag * (1 - 0.5 * (dy_ + dx_)))[:, None] * np.array([0.9, 0.95, 1.0]) * P["stars"])
    # ---- clouds (periodic in azimuth; compressed toward the horizon so they read as a layer)
    if P["cloud"] > 0:
        ys = np.clip(el_deg, 1.5, 90)
        n1 = pbr.fbm(0, seed + 1, 2.8, 2, shape=(Hh, W))
        n2 = pbr.fbm(0, seed + 2, 2.0, 6, shape=(Hh, W))
        cl = 0.68 * n1 + 0.32 * n2
        thr = 1.0 - P["cloud"] * 0.62
        dens = np.clip((cl - thr + 0.12) / 0.22, 0, 1)
        dens *= np.clip(el_deg / 6.0, 0, 1)[:, None] * np.clip((70 - ys) / 40, 0.35, 1)[:, None]
        if P["cloud"] > 0.85:
            dens = np.clip(dens * 1.5 + 0.18, 0, 1) * np.clip(el_deg / 4.0, 0, 1)[:, None]
        lit = np.clip(0.55 + 0.45 * pbr.blur(cl, 6) * 2 - 0.5, 0, 1)
        ccol = cs(P["cloud_col"])[None, None, :] * lit[..., None] + cs(P["cloud_shade"])[None, None, :] * (1 - lit[..., None])
        if P["sun_el"] > -5:
            ccol = ccol * (0.75 + 0.25 * np.clip(cosang, 0, 1)[..., None] ** 2 * 3)
        if P["stars"] > 0.5:
            ccol = ccol * 0.5
        sky = sky * (1 - dens[..., None] * 0.92) + ccol * dens[..., None] * 0.92
    # ---- far ranges beyond the map rim (three layers, ridged noise)
    # place.json "skybox": {"rim_min_deg": 4 (floor of the far horizon; 0 = open sea / plain), "far_scale": 1 (0 = no far ranges)}; default = closed bowl
    sk = place_stats.place_json(place, world_root).get("skybox", {})
    far_scale = float(sk.get("far_scale", 1.0))
    rim = np.maximum(mc["M"][:, -1], math.radians(float(sk.get("rim_min_deg", 4.0))))
    far = np.zeros((Hh, W, 3))
    farmask = np.zeros((Hh, W))
    layers = [(0.085, 2.0, 0.30, 5), (0.150, 4.0, 0.50, 11), (0.235, 7.0, 0.68, 23)]       # (extra angle rad, 2nd amplitude deg, haze, seed) near -> far
    for li, (extra, _, hz, sd) in enumerate(reversed(layers) if far_scale > 0 else []):
        extra = extra * far_scale
        prof = rim + extra * (0.30 + 0.70 * ridged_1d(W, seed + sd)) + math.radians(0.8) * li
        mask = el[:, None] < prof[None, :]
        depth = np.clip((prof[None, :] - el[:, None]) / max(extra * 0.9, 1e-3), 0, 1)       # 0 at the ridge line, 1 deep inside
        base = cs("#7c8a9a") * (1 - depth[..., None]) + cs("#4a5a52") * depth[..., None]
        snowfrac = np.clip((0.38 - depth) * 3.0, 0, 1) * np.clip(li / 1.0, 0.45, 1.0)
        if P["snow_all"]:
            snowfrac = np.clip(snowfrac * 1.6 + 0.35, 0, 1) * (depth < 0.95)
        base = base * (1 - snowfrac[..., None]) + cs("#eef2f7") * snowfrac[..., None]
        shade = P["ambient"] + P["light"] * 0.55
        col = base * shade * cs(P["tint"])
        col = col * (1 - hz) + (haze * 1.0) * hz
        far = np.where(mask[..., None], col, far)
        farmask = np.maximum(farmask, mask)
    comp = np.where(farmask[..., None] > 0, far, sky)
    # ---- real terrain
    M = mc["M"]
    hit_rows = el_deg > -50
    rows = np.where(hit_rows)[0]
    elr = el[rows]
    K = np.empty((len(rows), W), np.int64)
    for c in range(W):
        K[:, c] = np.searchsorted(M[c], elr, side="left")
    seen = K < M.shape[1]
    Kc = np.minimum(K, M.shape[1] - 1)
    cols = np.broadcast_to(np.arange(W)[None, :], K.shape)
    X, Y, Z, D = mc["X"][cols, Kc], mc["Y"][cols, Kc], mc["Z"][cols, Kc], mc["d"][Kc]
    N, slope = terrain_normal(h, cell, X, Y)
    nv = (N @ sundir)
    lam = np.clip(nv, 0, 1)
    jit = pbr.fbm(0, seed + 9, 1.6, 40, shape=(Hh, W))[rows]
    jit2 = pbr.fbm(0, seed + 10, 2.2, 8, shape=(Hh, W))[rows]
    elev = Z + (jit - 0.5) * 18
    treeline = rm(910) - slope * 3.0 + (jit2 - 0.5) * 80
    meadow, conifer, rock, rock2, snowc = cs("#6f8a46"), cs("#2f4a2c"), cs("#7c766d"), cs("#5b5750"), cs("#f3f6fa")
    forest = np.clip((treeline - elev) / 120.0, 0, 1) * np.clip((44 - slope) / 14.0, 0, 1)
    low = np.clip((rm(760) - elev) / 220.0, 0, 1) * np.clip((22 - slope) / 14.0, 0, 1)
    col = rock[None, None, :] * (1 - jit2[..., None] * 0.5) + rock2[None, None, :] * (jit2[..., None] * 0.5)
    col = np.where(True, col, col)
    col = col * (1 - forest[..., None]) + (conifer * (0.7 + 0.6 * jit[..., None]) * (1 - 0.25 * low[..., None]) + meadow * low[..., None] * 0.5) * forest[..., None]
    snowline = rm(P["snow_ft"]) - slope * 4.0 + (jit2 - 0.5) * 70
    snow = np.clip((elev - snowline) / 45.0, 0, 1) * np.clip((62 - slope) / 14.0, 0, 1)
    if P["snow_all"]:
        snow = np.clip(0.55 + (1 - np.clip(slope / 55.0, 0, 1)) * 0.5 + (jit2 - 0.5) * 0.35, 0, 1) * (slope < 70)
    col = col * (1 - snow[..., None]) + snowc * snow[..., None]
    light = P["ambient"] + P["light"] * lam[..., None] * cs(P["sun_col"])[None, None, :] * 0.9
    if P["sun_el"] < 0:
        light = P["ambient"] * 0.9 + 0.0 * lam[..., None]
    col = col * light * cs(P["tint"])
    fog = 1 - np.exp(-D / P["fog_ft"])
    col = col * (1 - fog[..., None]) + haze * fog[..., None]
    # sky rows for hits at the very horizon remain sky; terrain wins where a sample was hit
    tmask = seen[..., None]
    sub = comp[rows]
    sub = np.where(tmask, col, sub)
    comp[rows] = sub
    # below -50 degrees: copy the last row (ground right under the viewer is hidden by the table/terrain mesh anyway)
    comp[~hit_rows] = comp[rows[-1]][None, :, :]
    # exposure / tone: soft clip so the sun disc does not clip hard
    out = lin_to_srgb(comp / (1 + 0.15 * comp))
    out = np.clip(out * 1.06, 0, 1)
    return (out * 255 + 0.5).astype(np.uint8), dict(viewer=[vx, vy], eye_ft=EYE_FT, horizon_max_deg=float(np.degrees(mc["M"][:, -1].max())),
                                                     horizon_mean_deg=float(np.degrees(mc["M"][:, -1].mean())), yaw_deg=yaw_deg)


def save(img, out_dir, preset, quality=90, preview=True):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    im = Image.fromarray(img)
    p = os.path.join(out_dir, f"{preset}.webp")
    im.save(p, "WEBP", quality=quality, method=4)
    if preview:
        im.resize((1024, 512), Image.LANCZOS).save(os.path.join(out_dir, f"{preset}_preview.png"), optimize=True)
    return p


def cmd_generate(a):
    h, cell = load_heights(a.place)
    vx, vy = [float(v) for v in a.viewer.split(",")] if a.viewer else (None, None)
    viewer = (vx, vy) if vx is not None else None
    out_dir = a.out or os.path.join(REPO, "world", a.place, "export", "skybox")
    man = {"place": a.place, "format": "equirect 2:1", "width": a.width, "convention": "image centre = east, u clockwise from above; flag levels-3d-preview.exr", "skyboxes": {}}
    for name in a.presets.split(","):
        sun = None
        if a.lighting:                                              # sun from the Illustrator lighting config (same sun as the 2D shadows and the 3D scene)
            import foundry_lighting as fl
            s = fl.load_lighting(a.lighting)["sun"]
            sun = fl.sun_for_skybox(float(s["azimuth"]), float(s["altitude"]))
        img, info = render(a.place, name, viewer, a.width, a.yaw, h=h, cell=cell, sun=sun)
        p = save(img, out_dir, name)
        man["skyboxes"][name] = {"file": os.path.basename(p), "bytes": os.path.getsize(p), **info}
        print(f"{name}: {p} ({os.path.getsize(p) // 1024} KB), horizon max {info['horizon_max_deg']:.1f} deg", flush=True)
    json.dump(man, open(os.path.join(out_dir, "skybox_manifest.json"), "w"), indent=1)
    return 0


def cmd_set_flag(a):
    """Copy the preset's image to the Foundry assets share (versioned) and set flags.levels-3d-preview.exr on the scene. Dry run unless --apply."""
    import foundry_push as fp
    src = a.image or os.path.join(REPO, "world", a.place, "export", "skybox", f"{a.preset}.webp")
    if not os.path.exists(src):
        raise SystemExit(f"{src} not found; run generate first")
    ver, path = fp.publish_file(src, f"art/{a.place}/skybox", a.preset, fp.assets_dir(), dry=not a.apply)
    flags = {fp.L3D: {"exr": path, "skybox": ""}}
    for o in a.scene_flag or []:
        k, _, v = o.partition("=")
        try:
            flags[fp.L3D][k] = json.loads(v)
        except ValueError:
            flags[fp.L3D][k] = v
    print(json.dumps({"scene": a.scene_uuid, "asset": path, "version": ver, "flags": flags, "applied": bool(a.apply)}))
    if a.apply:
        fp.PsBridge().call("update", uuid=a.scene_uuid, data={"flags": flags})
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sp = ap.add_subparsers(dest="cmd", required=True)
    g = sp.add_parser("generate")
    g.add_argument("--place", default="bridgehollow")
    g.add_argument("--presets", default=",".join(PRESETS))
    g.add_argument("--viewer", help="X,Y feet in the place's frame (default: middle of the map)")
    g.add_argument("--width", type=int, default=2048)
    g.add_argument("--yaw", type=float, default=0.0)
    g.add_argument("--lighting", help="place id or lighting JSON: use its sun azimuth/altitude for the sun in the sky")
    g.add_argument("--out")
    s = sp.add_parser("set-flag")
    s.add_argument("--place", default="bridgehollow")
    s.add_argument("--scene-uuid", required=True)
    s.add_argument("--preset", default="clear_day")
    s.add_argument("--image")
    s.add_argument("--scene-flag", action="append", default=[], metavar="KEY=VALUE", help="extra levels-3d-preview flags, e.g. sunPosition=60")
    s.add_argument("--apply", action="store_true", help="really copy the image and write the scene flag (default: print what would happen)")
    a = ap.parse_args(argv)
    return {"generate": cmd_generate, "set-flag": cmd_set_flag}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
