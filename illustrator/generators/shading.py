"""Phase-based terrain shading (STEP 2).

heightmap (.npy from terrain.py) + ordered phase list (JSON) -> world-aligned PNG
(+ .json bounds, .pgw world file, optional per-phase vector SVG). See README_shading.md.

  python shading.py --place bridgehollow --phases alpine_steep \
      --scale-ft-per-in 100 --dpi 150 --out ../out/bridgehollow_shading.png
  python shading.py --make-textures      # (re)generate procedural tiles in presets/textures
"""
import argparse
import json
import os

import numpy as np
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
ILL = os.path.abspath(os.path.join(HERE, ".."))
REPO = os.path.abspath(os.path.join(ILL, ".."))
TEX_DIR = os.path.join(ILL, "presets", "textures")
PRESET_DIR = os.path.join(ILL, "presets", "terrain_phases")

DEFAULTS = dict(texture="#808080", elev_min=None, elev_max=None, slope_min_deg=0.0, slope_max_deg=90.0,
                elev_blend_ft=20.0, slope_blend_deg=5.0, opacity=1.0, noise_jitter=0.5,
                tile_scale_ft=40.0, enabled=True, noise_scale_ft=70.0, grain=0.06,
                below_datum=False, water_depth=None, texture_contrast=1.0, texture_brightness=1.0)
MUTED_DEFAULT = dict(saturation=1.0, contrast=1.0, tint=None, tint_strength=0.12, pivot=150.0)
DEFAULT_PRESET = "alpine_steep_calm"   # default phase preset for new renders (the older presets stay available by name)
HILL_STRENGTH = 0.35     # default hillshade strength (lighter than the old 0.55-0.6)
HILL_AMBIENT = 0.3       # default ambient fill 0..1
JITTER_ELEV_FT = 40.0     # noise_jitter 1.0 shifts elevation thresholds by up to +-this
JITTER_SLOPE_DEG = 8.0    # ... and slope thresholds by up to +-this


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def window(v, lo, hi, blend):
    """1 inside [lo,hi]; smooth falloff centred on each edge, total width `blend`. None = unbounded."""
    w = np.ones_like(v)
    b = max(float(blend), 1e-6)
    if lo is not None:
        w = w * smoothstep((v - lo) / b + 0.5)
    if hi is not None:
        w = w * smoothstep((hi - v) / b + 0.5)
    return w


def periodic_noise(shape, sigma, rng):
    n = ndi.gaussian_filter(rng.standard_normal(shape), sigma, mode="wrap")
    n -= n.mean()
    return n / (np.abs(n).max() + 1e-9)


def _smooth_grid(ny, nx, ppf, scale_ft, rng):
    gy, gx = max(2, int(ny / (scale_ft * ppf)) + 3), max(2, int(nx / (scale_ft * ppf)) + 3)
    g = rng.uniform(-1, 1, (gy, gx))
    return ndi.zoom(g, (ny / gy, nx / gx), order=3)[:ny, :nx]


def field_noise(ny, nx, ppf, scale_ft, seed):
    """Smooth noise in ~[-1,1] over the output grid, feature size ~scale_ft (two octaves)."""
    rng = np.random.default_rng(seed)
    a = _smooth_grid(ny, nx, ppf, scale_ft, rng)
    b = _smooth_grid(ny, nx, ppf, scale_ft / 2.5, rng)
    out = a + 0.5 * b
    out = np.pad(out, ((0, max(0, ny - out.shape[0])), (0, max(0, nx - out.shape[1]))), mode="edge")
    return out / 1.5


def apply_muted(rgb, m):
    """Global 'muted' control on an HxWx3 0..255 image (applied after the phases, before hillshade).
    saturation 0..1 (1 = unchanged, 0 = grey), contrast 0..1 (1 = unchanged, lower pulls toward `pivot`),
    tint = hex colour blended in luminance-preserving at tint_strength (default 0.12). No-op at the defaults."""
    if not m:
        return rgb
    m = {**MUTED_DEFAULT, **{k: v for k, v in m.items() if v is not None}}
    sat, con = float(m["saturation"]), float(m["contrast"])
    tint = m.get("tint")
    if sat >= 0.999 and con >= 0.999 and not tint:
        return rgb
    w = np.array([0.299, 0.587, 0.114])
    luma = (rgb @ w)[..., None]
    out = luma + (rgb - luma) * sat
    piv = float(m["pivot"])
    out = piv + (out - piv) * con
    if tint:
        t = parse_color(tint)
        k = float(m["tint_strength"])
        lo = (out @ w)[..., None]
        out = out * (1 - k) + t[None, None, :] * (lo / max(float(t @ w), 1.0)) * k
    return np.clip(out, 0, 255)


# ---------------------------------------------------------------- textures
def parse_color(s):
    s = s.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], float)


def _is_color(s):
    t = s.lstrip("#")
    return s.startswith("#") or (len(t) in (3, 6) and all(c in "0123456789abcdefABCDEF" for c in t)
                                 and not os.path.splitext(s)[1])


def load_texture(spec, base_dir):
    """Returns (float array HxWx3 0..255 tile or None, flat_rgb or None)."""
    from PIL import Image
    if _is_color(spec):
        return None, parse_color(spec)
    for d in (base_dir, TEX_DIR, ILL, REPO):
        p = spec if os.path.isabs(spec) else os.path.join(d, spec)
        if os.path.exists(p):
            return np.asarray(Image.open(p).convert("RGB"), float), None
    raise FileNotFoundError("texture not found: " + spec)


def sample_tile(tile, X, Y, tile_ft):
    """Bilinear sample of a tiling texture at world coords (feet)."""
    h, w = tile.shape[:2]
    u, v = (X / tile_ft) * w, (Y / tile_ft) * h
    u0, v0 = np.floor(u), np.floor(v)
    fu, fv = (u - u0)[..., None], (v - v0)[..., None]
    i0, j0 = (v0.astype(int)) % h, (u0.astype(int)) % w
    i1, j1 = (i0 + 1) % h, (j0 + 1) % w
    return ((tile[i0, j0] * (1 - fu) + tile[i0, j1] * fu) * (1 - fv) +
            (tile[i1, j0] * (1 - fu) + tile[i1, j1] * fu) * fv)


def sample_tile_nt(tile, X, Y, tile_ft, ppf, seed):
    """Non-repeating sampling of a tileable texture: domain-warp the coordinates with low-frequency noise and
    blend two copies (different scale/rotation/offset) with a noise weight, so no regular grid shows.
    Blend is variance-compensated so texture contrast is kept."""
    ny, nx = X.shape
    wscale = tile_ft * 2.7
    wx = field_noise(ny, nx, ppf, wscale, seed + 101) * tile_ft * 0.6
    wy = field_noise(ny, nx, ppf, wscale, seed + 102) * tile_ft * 0.6
    a = sample_tile(tile, X + wx, Y + wy, tile_ft)
    th = np.radians(31.0)
    c, s_ = np.cos(th), np.sin(th)
    X2, Y2 = (c * X - s_ * Y) + 0.37 * tile_ft, (s_ * X + c * Y) + 0.61 * tile_ft
    b = sample_tile(tile, X2 + wy, Y2 - wx, tile_ft * 1.31)
    t = field_noise(ny, nx, ppf, tile_ft * 3.3, seed + 103)
    w = smoothstep(t * 1.4 * 0.5 + 0.5)[..., None]
    m = tile.reshape(-1, 3).mean(0)
    return m + ((a - m) * (1 - w) + (b - m) * w) / np.sqrt((1 - w) ** 2 + w ** 2)


def make_textures(outdir=TEX_DIR, size=192):
    """Procedural tileable PNG tiles (flat colour + multi-scale wrapped noise)."""
    from PIL import Image
    os.makedirs(outdir, exist_ok=True)
    # name: (base colour, contrast, fine grain, speckle colour or None)
    defs = {
        "grass": ("#6f9a48", .16, .07, "#4f7a34"), "meadow": ("#9bb55c", .15, .08, "#d8cf6a"),
        "farmland": ("#b3a860", .12, .05, "#8d9a4c"), "dirt": ("#8d6e4b", .14, .09, "#6b5238"),
        "forest_floor": ("#4c5d37", .18, .10, "#33401f"), "scree": ("#8c8780", .20, .16, "#5f5b56"),
        "rock": ("#6d6a68", .22, .12, "#46433f"), "snow": ("#f2f5f8", .05, .03, "#cfdbe6"),
        "dry_grass": ("#b2a35f", .14, .08, "#8a7a3f"), "sand": ("#d7c08a", .08, .06, "#bba36d"),
        "scrub": ("#8c8a52", .16, .10, "#5e6238"), "red_rock": ("#9b5f41", .20, .10, "#6b3d2a"),
        "ink_light": ("#e6e6e6", .04, .03, None), "ink_mid": ("#b4b4b4", .08, .05, "#9a9a9a"),
        "ink_dark": ("#7a7a7a", .10, .07, "#5a5a5a"), "ink_black": ("#444444", .08, .05, "#2c2c2c"),
        "parch_light": ("#efe0bb", .05, .04, "#e0cc9c"), "parch_mid": ("#d8bf8c", .08, .05, "#bfa06a"),
        "parch_dark": ("#b08d5b", .10, .06, "#8c6a3c"), "parch_deep": ("#7b5b36", .10, .06, "#5c4025"),
    }
    for k, (name, (base, contrast, grain, speck)) in enumerate(defs.items()):
        rng = np.random.default_rng(100 + k)
        s = (size, size)
        n = periodic_noise(s, size / 10, rng) * .6 + periodic_noise(s, size / 40, rng) * .3
        f = rng.standard_normal(s) * grain
        img = parse_color(base)[None, None, :] * (1 + contrast * n[..., None] + f[..., None] * .5)
        if speck:
            m = smoothstep((periodic_noise(s, size / 25, rng) - .35) / .2)[..., None]
            img = img * (1 - .5 * m) + parse_color(speck) * .5 * m
        Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(os.path.join(outdir, name + ".png"))
    return list(defs)


# ---------------------------------------------------------------- core
def load_phase_file(path):
    d = json.load(open(path, encoding="utf-8"))
    if isinstance(d, list):
        d = {"phases": d}
    return d


def slope_deg_native(h, cell, smooth=1.0):
    hh = ndi.gaussian_filter(h, smooth, mode="nearest") if smooth > 0 else h
    gy, gx = np.gradient(hh, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def hillshade(h, cell, azimuth=315.0, altitude=40.0, exag=1.0):
    h = ndi.gaussian_filter(h, 1.5, mode="nearest")   # soften: no per-cell speckle
    gy, gx = np.gradient(h * exag, cell)
    az, alt = np.radians(azimuth), np.radians(altitude)
    lx, ly, lz = np.sin(az) * np.cos(alt), -np.cos(az) * np.cos(alt), np.sin(alt)
    nrm = np.sqrt(gx ** 2 + gy ** 2 + 1)
    return np.clip((-gx * lx - gy * ly + lz) / nrm, 0, 1)


def resample(a, x_ft, y_ft, cell):
    return ndi.map_coordinates(a, [y_ft / cell, x_ft / cell], order=3, mode="nearest")


def phase_weight(p, i, elev, slope, ppf, seed, sea=0.0):
    ny, nx = elev.shape
    ph = {**DEFAULTS, **p}
    if ph["water_depth"] or ph["below_datum"]:
        if ph["elev_max"] is None:
            ph["elev_max"] = sea
    if not ph.get("enabled", True):
        return None
    j = float(ph["noise_jitter"])
    if j > 0:
        en = field_noise(ny, nx, ppf, ph["noise_scale_ft"], seed * 977 + i * 31 + 1)
        sn = field_noise(ny, nx, ppf, ph["noise_scale_ft"] * .7, seed * 977 + i * 31 + 2)
        e, s = elev + en * j * JITTER_ELEV_FT, slope + sn * j * JITTER_SLOPE_DEG
    else:
        e, s = elev, slope
    w = window(e, ph["elev_min"], ph["elev_max"], ph["elev_blend_ft"])
    s_lo = ph["slope_min_deg"] if ph["slope_min_deg"] and ph["slope_min_deg"] > 0 else None
    s_hi = ph["slope_max_deg"] if ph["slope_max_deg"] is not None and ph["slope_max_deg"] < 90 else None
    w = w * window(s, s_lo, s_hi, ph["slope_blend_deg"])
    return w * float(ph["opacity"])


def render(h, meta, phases, ppf, base_dir=".", hill=None, seed=None, base_color="#808080",
           masks_dir=None, max_px=60_000_000, verbose=True, window=None, muted=None, slope_smooth_ft=0.0):
    """window = (x0, y0, x1, y1) feet: render only that part (region children: the page window, not the whole padded frame)."""
    cell = meta["cell_ft"]
    W_ft, H_ft = meta["size_ft"]
    if meta.get("elev_adapt"):         # place.json phase_elevation = percentile: map the preset's elevation bands onto this place's relief
        import place_stats
        phases = place_stats.adapt_phases(phases, meta["elev_adapt"])
    ox, oy = 0.0, 0.0
    if window:
        ox, oy, W_ft, H_ft = float(window[0]), float(window[1]), float(window[2] - window[0]), float(window[3] - window[1])
    nx, ny = int(round(W_ft * ppf)), int(round(H_ft * ppf))
    if nx * ny > max_px:
        raise SystemExit(f"{nx}x{ny} px exceeds {max_px}; lower dpi or raise scale_ft_per_in")
    seed = meta.get("seed", 0) if seed is None else seed
    sea = float(meta.get("sea_level_ft", 0.0))
    X, Y = np.meshgrid(ox + (np.arange(nx) + .5) / ppf, oy + (np.arange(ny) + .5) / ppf)
    elev = resample(h, X, Y, cell)
    sl = slope_deg_native(h, cell)
    if slope_smooth_ft and slope_smooth_ft > 0:       # calm presets: smooth the slope field so scree/rock masks are not speckled
        sl = ndi.gaussian_filter(sl, slope_smooth_ft / cell, mode="nearest")
    slope = resample(sl, X, Y, cell)
    out = np.empty((ny, nx, 3))
    out[:] = parse_color(base_color)
    weights = {}
    for i, p in enumerate(phases):
        ph = {**DEFAULTS, **p}
        w = phase_weight(p, i, elev, slope, ppf, seed, sea)
        if w is None:
            continue
        wd = ph["water_depth"]
        if wd:
            t = smoothstep((sea - elev) / max(float(wd.get("max_depth_ft", 30.0)), 1e-6))[..., None]
            col = parse_color(wd.get("shallow", "#7fc4c9")) * (1 - t) + parse_color(wd.get("deep", "#12395e")) * t
            tile, flat = None, None
        else:
            tile, flat = load_texture(ph["texture"], base_dir)
        if wd:
            pass
        elif tile is None:
            n = field_noise(ny, nx, ppf, max(ph["tile_scale_ft"] / 8, 1), seed + i * 13 + 5)
            col = flat[None, None, :] * (1 + ph["grain"] * 2 * n[..., None] * float(ph["texture_contrast"]))
        else:
            col = sample_tile_nt(tile, X, Y, ph["tile_scale_ft"], ppf, seed + i * 17 + 9)
            tc = float(ph["texture_contrast"])
            if tc != 1.0:                                  # calm: pull the texture toward its own mean colour
                mt = tile.reshape(-1, 3).mean(0)
                col = mt + (col - mt) * tc
        if float(ph["texture_brightness"]) != 1.0:
            col = col * float(ph["texture_brightness"])
        out = out * (1 - w[..., None]) + col * w[..., None]
        weights[p.get("id", str(i))] = w
        if verbose:
            print(f"  phase {p.get('id', i):>14}: mean weight {w.mean():.3f}")
    out = apply_muted(out, muted)
    if hill and hill.get("enabled", True):
        alt = hill.get("altitude", 40)
        hs = hillshade(h, cell, hill.get("azimuth", 315), alt, hill.get("exaggeration", 1.0))
        hs = resample(hs, X, Y, cell)
        k = hill.get("strength", HILL_STRENGTH)
        amb = float(hill.get("ambient", HILL_AMBIENT))   # 0 = full contrast, 1 = no shading
        flat = np.sin(np.radians(alt))
        hs = amb + (1 - amb) * hs
        out = out * np.clip(1 + (hs - (amb + (1 - amb) * flat)) * k * 2.0, 0.55, 1.3)[..., None]
    img = np.clip(out, 0, 255).astype(np.uint8)
    if masks_dir:
        from PIL import Image
        os.makedirs(masks_dir, exist_ok=True)
        for k, w in weights.items():
            Image.fromarray((np.clip(w, 0, 1) * 255).astype(np.uint8)).save(os.path.join(masks_dir, f"mask_{k}.png"))
    return img, weights


# ---------------------------------------------------------------- vector
def vector_svg(h, meta, phases, ppf, base_dir, path, cell_ft=4.0, seed=None, min_area_ft2=200.0):
    """Hard-edged polygons per phase (weight >= 0.5), painted in phase order. Coordinates in output px."""
    import contourpy
    from contourpy import FillType
    cell = meta["cell_ft"]
    W_ft, H_ft = meta["size_ft"]
    seed = meta.get("seed", 0) if seed is None else seed
    nx, ny = int(W_ft / cell_ft) + 1, int(H_ft / cell_ft) + 1
    xs, ys = np.arange(nx) * cell_ft, np.arange(ny) * cell_ft
    X, Y = np.meshgrid(xs, ys)
    elev, slope = resample(h, X, Y, cell), resample(slope_deg_native(h, cell), X, Y, cell)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W_ft * ppf:.2f}" height="{H_ft * ppf:.2f}" '
             f'viewBox="0 0 {W_ft * ppf:.2f} {H_ft * ppf:.2f}">']
    for i, p in enumerate(phases):
        ph = {**DEFAULTS, **p}
        w = phase_weight(p, i, elev, slope, 1.0 / cell_ft, seed, float(meta.get("sea_level_ft", 0.0)))
        if w is None:
            continue
        if ph["water_depth"]:
            tile, flat = None, parse_color(ph["water_depth"].get("shallow", "#7fc4c9"))
        else:
            tile, flat = load_texture(ph["texture"], base_dir)
        col = flat if tile is None else tile.reshape(-1, 3).mean(0)
        fill = "#%02x%02x%02x" % tuple(int(c) for c in col)
        pid = p.get("id", str(i))
        gen = contourpy.contour_generator(xs, ys, w, fill_type=FillType.OuterCode)
        pts_l, codes_l = gen.filled(0.5, 1e9)
        parts.append(f'<g id="phase_{pid}" fill="{fill}" stroke="none" fill-rule="evenodd">')
        n = 0
        for pts, codes in zip(pts_l, codes_l):
            starts = np.flatnonzero(codes == 1)
            r0 = pts[:(starts[1] if len(starts) > 1 else len(pts))]
            area = 0.5 * abs(np.dot(r0[:, 0], np.roll(r0[:, 1], 1)) - np.dot(r0[:, 1], np.roll(r0[:, 0], 1)))
            if area < min_area_ft2:
                continue
            d = [("M" if c == 1 else "Z" if c == 79 else "L") + ("" if c == 79 else f"{x * ppf:.2f} {y * ppf:.2f}")
                 for (x, y), c in zip(pts, codes)]
            n += 1
            parts.append(f'<path id="phase_{pid}_{n}" d="{" ".join(d)}"/>')
        parts.append("</g>")
    parts.append("</svg>")
    open(path, "w", encoding="utf-8").write("\n".join(parts))


# ---------------------------------------------------------------- CLI
def muted_from(doc, a=None):
    """The preset's `muted` block with CLI overrides (a = argparse namespace or None) -> dict or None."""
    m = dict(doc.get("muted") or {})
    if a is not None:
        if getattr(a, "no_muted", False):
            return None
        for k in ("saturation", "contrast", "tint", "tint_strength"):
            v = getattr(a, "muted_" + k, None)
            if v is not None:
                m[k] = v
    return m or None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--heightmap", help=".npy (default: current terrain via worldio: patched/carved/base)")
    ap.add_argument("--terrain-source", choices=["auto", "base", "patched", "carved"], help="which heightmap (default per panel_state / auto)")
    ap.add_argument("--meta", help="terrain_meta.json (default next to heightmap)")
    ap.add_argument("--phases", default=DEFAULT_PRESET, help=f"phase-list JSON path, or preset name (default {DEFAULT_PRESET})")
    ap.add_argument("--muted-saturation", type=float, help="0..1 global saturation (1 = unchanged); overrides the preset's muted block")
    ap.add_argument("--muted-contrast", type=float, help="0..1 global contrast about a mid grey (1 = unchanged)")
    ap.add_argument("--muted-tint", help="#rrggbb tint blended in over the whole image (luminance preserving)")
    ap.add_argument("--muted-tint-strength", type=float, help="0..1 tint amount (default 0.12)")
    ap.add_argument("--no-muted", action="store_true", help="ignore the preset's muted block (full colour)")
    ap.add_argument("--reverse", action="store_true", help="reverse the phase order (quick re-order test)")
    ap.add_argument("--order", help="comma list of phase ids giving a new order")
    ap.add_argument("--scale-ft-per-in", type=float, default=100.0)
    ap.add_argument("--dpi", type=float, default=150.0)
    ap.add_argument("--out", help="output PNG")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--sea-level", type=float, help="override datum (ft)")
    ap.add_argument("--elev-offset", type=float, default=0.0, help="add to heightmap (ft), e.g. negative to test below-datum")
    ap.add_argument("--hillshade", action="store_true", help="force hillshade on (overrides the file's block)")
    ap.add_argument("--no-hillshade", action="store_true")
    ap.add_argument("--azimuth", type=float, default=315)
    ap.add_argument("--altitude", type=float, default=40)
    ap.add_argument("--strength", type=float, default=HILL_STRENGTH)
    ap.add_argument("--ambient", type=float, default=HILL_AMBIENT)
    ap.add_argument("--exaggeration", type=float, default=1.0)
    ap.add_argument("--masks", action="store_true", help="also write per-phase mask PNGs")
    ap.add_argument("--vector", help="also write per-phase thresholded SVG here")
    ap.add_argument("--vector-cell", type=float, default=4.0)
    ap.add_argument("--make-textures", action="store_true")
    ap.add_argument("--window", help="x0,y0,x1,y1 feet: render only this window (region children)")
    a = ap.parse_args()
    if a.make_textures:
        print("textures:", ", ".join(make_textures()))
        return
    if not a.out:
        ap.error("--out is required")
    if a.heightmap:
        h = np.load(a.heightmap)
        meta = json.load(open(a.meta or os.path.join(os.path.dirname(a.heightmap), "terrain_meta.json"), encoding="utf-8"))
    else:   # the shared loader: patched / carved / base (see worldio.py)
        import sys
        sys.path.insert(0, HERE)
        import worldio
        worldio.set_source(a.terrain_source)
        h, meta = worldio.load_terrain(a.place)
        print(f"terrain source: {meta['source']}")
    h = h + a.elev_offset
    if a.sea_level is not None:
        meta["sea_level_ft"] = a.sea_level
    pp = a.phases
    if not os.path.exists(pp):
        pp = os.path.join(PRESET_DIR, pp if pp.endswith(".json") else pp + ".json")
    doc = load_phase_file(pp)
    phases = doc["phases"]
    if a.order:
        byid = {p["id"]: p for p in phases}
        phases = [byid[k] for k in a.order.split(",")]
    if a.reverse:
        phases = phases[::-1]
    muted = muted_from(doc, a)
    ppf = a.dpi / a.scale_ft_per_in
    win = [float(v) for v in a.window.split(",")] if a.window else None
    hill = doc.get("hillshade")
    if a.hillshade:
        hill = dict(azimuth=a.azimuth, altitude=a.altitude, strength=a.strength, ambient=a.ambient, exaggeration=a.exaggeration)
    if a.no_hillshade:
        hill = None
    base_dir = os.path.dirname(os.path.abspath(pp))
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    base = os.path.splitext(out)[0]
    img, _ = render(h, meta, phases, ppf, base_dir, hill, a.seed, doc.get("base_color", "#808080"),
                    masks_dir=base + "_masks" if a.masks else None, window=win, muted=muted,
                    slope_smooth_ft=float(doc.get("slope_smooth_ft") or 0.0))
    from PIL import Image
    Image.fromarray(img).save(out, dpi=(a.dpi, a.dpi))
    W_ft, H_ft = meta["size_ft"]
    x_min, y_min = 0, 0
    if win:
        x_min, y_min, W_ft, H_ft = win[0], win[1], win[2], win[3]
    info = dict(png=os.path.basename(out), width_px=img.shape[1], height_px=img.shape[0], ppf=ppf,
                dpi=a.dpi, scale_ft_per_in=a.scale_ft_per_in,
                bounds_ft=dict(x_min=x_min, y_min=y_min, x_max=W_ft, y_max=H_ft), y_axis="down",
                page_size_in=[(W_ft - x_min) / a.scale_ft_per_in, (H_ft - y_min) / a.scale_ft_per_in],
                phases=[p.get("id") for p in phases])
    json.dump(info, open(base + ".json", "w"), indent=1)
    # world file: pixel size in feet, y grows downward (positive E), origin = centre of top-left pixel
    open(base + ".pgw", "w").write("\n".join(str(v) for v in (1 / ppf, 0, 0, 1 / ppf, .5 / ppf, .5 / ppf)) + "\n")
    print(f"wrote {out} {img.shape[1]}x{img.shape[0]} px ({ppf:g} px/ft)")
    if a.vector:
        vector_svg(h, meta, phases, ppf, base_dir, a.vector, a.vector_cell, a.seed)
        print("wrote", a.vector)


if __name__ == "__main__":
    main()
