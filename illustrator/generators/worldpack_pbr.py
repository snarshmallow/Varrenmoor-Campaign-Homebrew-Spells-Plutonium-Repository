"""PBR materials and procedural textures for world-pack GLBs (exteriors).

* `prepare(materials)` (called by worldpack.load_pack) upgrades the in-memory material records: roughness/metallic/alpha, a `normal` flag
  (normal map `<mat>_n.png` next to the base colour) and `mr` (glTF metallicRoughness texture `<mat>_mr.png`, G = roughness, B = metallic).
  It also adds the extra surface materials (plaster, stone/timber-frame/batten walls, door wood, trim, glass, kerb stone...). Nothing in
  materials.json on disk changes, so exported packs stay valid and old packs pick the upgrade up at split/merge time.
* `install(pack, tex_dir)` writes the generated PNGs (base colour, normal, metallicRoughness) into models/textures (called by worldpack_split)
  and replaces the baked terrain albedo with a higher-resolution copy with ground detail when the place is small enough.
* `restyle_building(e)` picks a wall material per building (kind + seeded variety): plank, plaster, timber frame, rubble stone, board and batten.
* `TILE_FT` is the world size (feet) one texture repeat covers, so texel density is the same on every face (UVs come from worldpack_mesh.world_uv).

Textures are tileable by construction (periodic FFT noise, wrapped stamping). Pure numpy + PIL. Orientation convention of every texture:
rows/courses run horizontally in the image (planks, shingle courses, stone courses), thatch strands and board-and-batten run vertically; the mesh
UVs put the image's up direction on the up-slope direction of the face.
"""
import hashlib
import math
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
TEXTURE_DIR = os.path.join(HERE, "..", "presets", "textures")

# id -> properties. src: preset texture to start from (default: the id itself), gen: procedural generator name, tile: feet per repeat,
# n: normal strength (0 = none), mr: write a metallicRoughness map (crevices rougher), rough/metal/alpha: glTF factors.
CATALOG = {
    "mat_plank": dict(tile=5.0, rough=0.82, n=2.2),
    "mat_w_plank": dict(src="w_plank", tile=5.0, rough=0.8, n=2.2),
    "mat_plaster": dict(gen="plaster", tile=6.0, rough=0.93, n=1.4),
    "mat_wall_stone": dict(gen="rubble", tile=7.0, rough=0.85, n=4.0, mr=True),
    "mat_wall_frame": dict(gen="timberframe", tile=10.0, rough=0.9, n=2.4),
    "mat_wall_batten": dict(gen="batten", tile=6.0, rough=0.88, n=2.6),
    "mat_stone_slab": dict(tile=6.0, rough=0.8, n=3.0, mr=True),
    "mat_door_wood": dict(gen="door", tile=3.5, rough=0.75, n=2.4),
    "mat_trim": dict(gen="trim", tile=3.0, rough=0.7, n=1.6),
    "mat_interior_floor": dict(src="plank", tile=4.0, rough=0.8, n=1.5),
    "mat_kerb": dict(src="stone_slab", tile=4.0, rough=0.72, n=3.0, mr=True),
    "mat_cobble": dict(tile=7.0, rough=0.58, n=4.0, mr=True),
    "mat_w_cobble": dict(src="w_cobble", tile=7.0, rough=0.5, n=4.0, mr=True),
    "mat_gravel": dict(tile=6.0, rough=0.92, n=3.0),
    "mat_dirt": dict(tile=8.0, rough=0.96, n=1.2),
    "mat_packed_earth": dict(tile=8.0, rough=0.95, n=1.5),
    "mat_grass": dict(tile=8.0, rough=0.97, n=0.9),
    "mat_shingle": dict(tile=9.0, rough=0.85, n=3.5),
    "mat_thatch": dict(tile=9.0, rough=0.97, n=3.0),
    "mat_slate": dict(tile=9.0, rough=0.5, n=3.5, mr=True),
    "mat_red_tile": dict(tile=9.0, rough=0.55, n=3.5, mr=True),
    "mat_timber_roof": dict(tile=9.0, rough=0.85, n=2.8),
    "mat_w_roof_snow": dict(tile=9.0, rough=0.75, n=2.0),
    "mat_w_roof_thatch": dict(tile=9.0, rough=0.95, n=2.5),
    "mat_w_roof_timber": dict(tile=9.0, rough=0.85, n=2.5),
    "mat_w_roof_slate": dict(tile=9.0, rough=0.55, n=3.0, mr=True),
    "mat_w_roof_red": dict(tile=9.0, rough=0.6, n=3.0, mr=True),
    "mat_water": dict(tile=12.0, rough=0.06, n=1.2, alpha=0.82),
    "mat_w_water": dict(src="w_water", tile=12.0, rough=0.06, n=1.0, alpha=0.82),
    "mat_w_ice": dict(tile=10.0, rough=0.12, n=0.8),
    "mat_snow": dict(tile=8.0, rough=0.7, n=0.8),
    "mat_w_snow": dict(src="w_snow", tile=8.0, rough=0.7, n=0.8),
    "mat_rock": dict(tile=10.0, rough=0.9, n=4.0),
    "mat_w_rock": dict(src="w_rock", tile=10.0, rough=0.9, n=4.0),
    "mat_tree_bark": dict(rough=0.95),
    "mat_glass": dict(rough=0.04, metal=0.25, alpha=0.32, color="#a9cbd9"),
    "mat_iron": dict(rough=0.5, metal=0.85, color="#3a3a3d"),
}
GENERIC = dict(tile=8.0, rough=0.9, n=1.5)
WALL_MATS = ("mat_plank", "mat_plaster", "mat_wall_frame", "mat_wall_stone", "mat_wall_batten")
TILE_FT = {k: v["tile"] for k, v in CATALOG.items() if "tile" in v}
ROOF_TEXEL_SCALE = 0.65        # existing styles ask for 14 ft per repeat (map look); in 3D a shingle course should be ~0.6 ft


def info(mid):
    if mid.startswith("mat_s_"):                              # dynamic style materials (building_styles.py)
        import building_styles as bs
        d = bs.info(mid)
        if d:
            return dict(GENERIC, **d)
    d = dict(GENERIC)
    if mid.startswith("mat_w_") and mid not in CATALOG:
        d.update(CATALOG.get("mat_" + mid[6:], {}))
    d.update(CATALOG.get(mid, {}))
    return d


def tile_ft(mid, default=8.0):
    if mid.startswith("mat_s_") and mid not in TILE_FT:
        d = info(mid)
        return d.get("tile", default) if d else default
    return TILE_FT.get(mid, default)


def prepare(materials):
    """Upgrade `materials` ({id: record}) in place; returns it. Idempotent."""
    for mid, r in list(materials.items()):
        if r.get("_pbr"):
            continue
        c = CATALOG.get(mid)
        if c is None:
            if r.get("texture") and mid != "mat_terrain_albedo" and "water" not in mid:
                c = info(mid)
            else:
                continue
        else:
            c = info(mid)
        r["roughness"] = c["rough"]
        r["metallic"] = c.get("metal", 0.0)
        if c.get("alpha") is not None:
            r["alpha"] = c["alpha"]
        if c.get("color"):
            r["mean_color"] = c["color"]
        if r.get("texture") or c.get("gen") or c.get("src"):
            r["texture"] = r.get("texture") or f"textures/{mid[4:]}.png"
            r["_generated"] = bool(c.get("gen") or c.get("src"))
            if c.get("n", 0) > 0:
                r["normal"] = True
            if c.get("mr"):
                r["mr"] = True
        r["_pbr"] = True
    for mid in ("mat_wall_stone", "mat_wall_frame", "mat_wall_batten", "mat_kerb", "mat_plaster", "mat_door_wood", "mat_trim", "mat_glass", "mat_iron", "mat_interior_floor"):
        if mid not in materials or not materials[mid].get("_pbr"):
            c = info(mid)
            rec = {"id": mid, "name": mid[4:], "kind": "image" if (c.get("gen") or c.get("src")) else "flat", "texture": None, "source": None, "sha256": None,
                   "mean_color": c.get("color", "#a8a090"), "roughness": c["rough"], "metallic": c.get("metal", 0.0), "_pbr": True}
            if c.get("alpha") is not None:
                rec["alpha"] = c["alpha"]
            if c.get("gen") or c.get("src"):
                rec["texture"] = f"textures/{mid[4:]}.png"
                rec["_generated"] = True
                if c.get("n", 0) > 0:
                    rec["normal"] = True
                if c.get("mr"):
                    rec["mr"] = True
            materials[mid] = rec
    return materials


def _h(s):
    return int(hashlib.md5(str(s).encode()).hexdigest()[:8], 16)


def restyle_building(e):
    """Shallow copy of building entity `e` with a wall material chosen by kind and a seeded roll (stable per building id)."""
    kind = e.get("kind") or (e.get("tags") or {}).get("subtype") or ""
    cur = e["wall"]["surface"]["material"]
    if cur.startswith("mat_w_"):
        return e                                          # winter styles keep their weathered boards
    roll = (_h(e["id"]) % 1000) / 1000.0
    table = {"house": (("mat_plank", .40), ("mat_plaster", .30), ("mat_wall_frame", .30)),
             "farmhouse": (("mat_plank", .35), ("mat_plaster", .35), ("mat_wall_stone", .30)),
             "shed": (("mat_wall_batten", .6), ("mat_plank", .4)), "barn": (("mat_wall_batten", 1.0),), "stable": (("mat_wall_batten", .7), ("mat_plank", .3)),
             "craft": (("mat_plank", .3), ("mat_plaster", .3), ("mat_wall_frame", .4)), "mill": (("mat_wall_stone", .7), ("mat_plank", .3)),
             "inn": (("mat_wall_frame", .5), ("mat_plaster", .3), ("mat_wall_stone", .2)), "tavern": (("mat_wall_frame", .5), ("mat_plaster", .3), ("mat_wall_stone", .2)),
             "civic": (("mat_wall_stone", 1.0),)}.get(kind, (("mat_plank", .5), ("mat_plaster", .3), ("mat_wall_frame", .2)))
    acc, pick = 0.0, table[-1][0]
    for m, p in table:
        acc += p
        if roll < acc:
            pick = m
            break
    if pick == cur:
        return e
    out = dict(e)
    out["wall"] = dict(e["wall"])
    out["wall"]["surface"] = dict(e["wall"]["surface"], material=pick, tile_ft=tile_ft(pick))
    return out


# ------------------------------------------------------------------ noise and maps
def fbm(n, seed, beta=2.2, kmin=1, shape=None):
    """Periodic (tileable) noise in 0..1; shape=(h, w) allows non-square. Power spectrum ~ r^-beta."""
    h, w = shape or (n, n)
    rng = np.random.RandomState(seed)
    F = np.fft.fft2(rng.randn(h, w))
    fy = np.fft.fftfreq(h)[:, None] * h
    fx = np.fft.fftfreq(w)[None, :] * w
    r = np.hypot(fx, fy)
    r[0, 0] = 1
    A = np.where(r >= kmin, r ** (-beta / 2), 0)
    A[0, 0] = 0
    f = np.real(np.fft.ifft2(F * A))
    f -= f.min()
    return f / max(f.max(), 1e-9)


def blur(a, px):
    """Periodic Gaussian blur (FFT)."""
    if px <= 0:
        return a
    h, w = a.shape
    fy = np.fft.fftfreq(h)[:, None]
    fx = np.fft.fftfreq(w)[None, :]
    k = np.exp(-2 * (math.pi * px) ** 2 * (fx ** 2 + fy ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * k))


def lerp(a, b, t):
    return a + (b - a) * t[..., None]


def hexrgb(s):
    return np.array([int(s[i:i + 2], 16) for i in (1, 3, 5)], float)


def to_u8(rgb):
    return np.clip(rgb, 0, 255).astype(np.uint8)


def normal_map(height, strength):
    """Tangent-space glTF normal map (+Y = image up) from a periodic height field 0..1 (strength ~ slope per unit height at 256 px)."""
    h = height * strength * (height.shape[0] / 256.0) * 0.25
    dx = (np.roll(h, -1, 1) - np.roll(h, 1, 1)) / 2
    dy = (np.roll(h, -1, 0) - np.roll(h, 1, 0)) / 2           # towards image bottom
    n = np.stack([-dx, dy, np.ones_like(h)], -1)
    n /= np.linalg.norm(n, axis=-1, keepdims=True)
    return to_u8((n * 0.5 + 0.5) * 255)


def height_from_albedo(rgb):
    lum = rgb @ np.array([0.3, 0.59, 0.11]) / 255.0
    lum = blur(lum, 0.8)
    lo, hi = np.percentile(lum, 2), np.percentile(lum, 98)
    return np.clip((lum - lo) / max(hi - lo, 1e-6), 0, 1)


def mr_map(height, rough, var=0.25, metal=0.0):
    r = np.clip(rough + var * (0.5 - height), 0.05, 1.0)
    out = np.zeros(height.shape + (3,), np.uint8)
    out[..., 0] = 255
    out[..., 1] = to_u8(r * 255)
    out[..., 2] = int(metal * 255)
    return out


# ------------------------------------------------------------------ generators -> (albedo float HxWx3, height 0..1)
def _blocks(n, seed, rows, lens, gap, bevel, base_cols, jitter=0.12, rowjit=0.35):
    """Masonry: rows of blocks that tile in both directions. Returns albedo, height."""
    rng = np.random.RandomState(seed)
    hs = rng.uniform(1 - rowjit, 1 + rowjit, rows)
    hs = np.round(hs / hs.sum() * n).astype(int)
    hs[-1] += n - hs.sum()
    alb = np.zeros((n, n, 3))
    hgt = np.zeros((n, n))
    y0 = 0
    yy, xx = np.mgrid[0:n, 0:n]
    for ri, rh in enumerate(hs):
        cnt = max(2, int(round(n / lens * rng.uniform(0.85, 1.15))))
        ws = rng.uniform(0.7, 1.3, cnt)
        ws = np.round(ws / ws.sum() * n).astype(int)
        ws[-1] += n - ws.sum()
        x0 = int(rng.randint(0, n))
        for w in ws:
            col = base_cols[rng.randint(len(base_cols))] * (1 + rng.uniform(-jitter, jitter))
            ys = (np.arange(y0, y0 + rh)) % n
            xs = (np.arange(x0, x0 + w)) % n
            ly, lx = np.mgrid[0:rh, 0:w]
            d = np.minimum.reduce([ly, rh - 1 - ly, lx, w - 1 - lx]).astype(float)
            m = d >= gap
            e = np.clip((d - gap) / max(bevel, 1), 0, 1)
            blk = np.where(m, 0.55 + 0.45 * np.sqrt(e), 0.0) * (0.9 + 0.1 * rng.rand())
            alb[np.ix_(ys, xs)] = np.where(m[..., None], col, col * 0.35)
            hgt[np.ix_(ys, xs)] = blk
            x0 += w
        y0 += rh
    return alb, hgt


def gen_rubble(n=512):
    cols = [hexrgb(c) for c in ("#9a948a", "#8a8378", "#a39a88", "#7d776d", "#b0a690")]
    alb, h = _blocks(n, 11, 7, 120, 3, 8, cols, 0.14, 0.45)
    grain = fbm(n, 3, 1.6, 4)
    alb *= (0.88 + 0.24 * grain)[..., None]
    h = h * (0.85 + 0.15 * grain)
    return alb, h


def gen_plaster(n=512):
    base = hexrgb("#d8cdb4")
    low, mid, fine = fbm(n, 21, 3.0, 1), fbm(n, 22, 2.0, 4), fbm(n, 23, 1.0, 16)
    streak = fbm(n, 26, 3.0, 1)
    col = base * (0.93 + 0.1 * low[..., None] + 0.04 * (mid[..., None] - 0.5)) * (1 - 0.1 * np.clip(streak - 0.55, 0, 1)[..., None] * 2)
    col = lerp(col, hexrgb("#b9a98a"), 0.25 * np.clip(low - 0.6, 0, 1))
    h = 0.5 * mid + 0.5 * fine
    return col * (0.96 + 0.08 * fine[..., None]), h


def gen_timberframe(n=512):
    """Whitewashed panel in a dark oak frame: post on the left edge, rail at the bottom (floor line), diagonal brace."""
    plaster, hp = gen_plaster(n)
    oak = hexrgb("#4a3624")
    yy, xx = np.mgrid[0:n, 0:n].astype(float)
    bw = n * 0.055
    post = xx < 2 * bw
    rail = yy > n - 2 * bw
    diag = np.abs(xx - yy) < bw * 0.9                   # diagonal brace, top-left to bottom-right
    mask = post | rail | diag
    grain = fbm(n, 31, 2.0, 2, shape=(n, n))
    streak = blur(fbm(n, 32, 1.2, 1), 0)
    wood = oak * (0.78 + 0.5 * streak[..., None] * 0.6 + 0.3 * grain[..., None] * 0.4)
    alb = np.where(mask[..., None], wood, plaster)
    h = np.where(mask, 0.8 + 0.2 * streak, 0.45 * hp)
    h = blur(h, 0.7)
    return alb, h


def _planks_vertical(n, seed, count, cols, gap=3, nails=False, wear=0.2):
    rng = np.random.RandomState(seed)
    ws = rng.uniform(0.85, 1.15, count)
    ws = np.round(ws / ws.sum() * n).astype(int)
    ws[-1] += n - ws.sum()
    alb = np.zeros((n, n, 3))
    h = np.zeros((n, n))
    x0 = 0
    yy = np.arange(n)[:, None]
    for w in ws:
        col = cols[rng.randint(len(cols))] * rng.uniform(0.88, 1.1)
        grain = fbm(n, int(rng.randint(1 << 20)), 1.4, 1, shape=(n, max(w, 4)))
        g = grain
        seg = col * (0.85 + 0.3 * g[..., None])
        alb[:, x0:x0 + w] = seg[:, :w]
        xs = np.arange(w)[None, :]
        edge = np.minimum(xs, w - 1 - xs)
        hh = np.clip(edge / 5.0, 0, 1) * (0.85 + 0.15 * g[:, :w])
        h[:, x0:x0 + w] = hh
        alb[:, x0:x0 + w] *= np.where(edge < gap, 0.35, 1.0)[..., None]
        x0 += w
    return alb, h


def gen_batten(n=512):
    cols = [hexrgb(c) for c in ("#7a5a38", "#6b4e30", "#876543", "#5f4529")]
    alb, h = _planks_vertical(n, 41, 8, cols)
    bw = n // 40
    for x in range(0, n, n // 4):                                    # battens over the joints every 1.5 ft
        xs = np.arange(x - bw, x + bw) % n
        alb[:, xs] = alb[:, xs] * 0.82 + hexrgb("#4d3a24") * 0.18
        h[:, xs] = np.maximum(h[:, xs], 1.0)
    return alb, blur(h, 0.6)


def gen_door(n=256):
    cols = [hexrgb(c) for c in ("#6b4a2b", "#5e4125", "#73512f")]
    alb, h = _planks_vertical(n, 51, 5, cols, 3)
    iron = hexrgb("#2c2c30")
    for y0, hh in ((int(n * 0.18), 14), (int(n * 0.72), 14)):         # strap hinges
        alb[y0:y0 + hh] = alb[y0:y0 + hh] * 0.25 + iron * 0.75
        h[y0:y0 + hh] = np.maximum(h[y0:y0 + hh], 1.0)
        for x in range(12, n, n // 5):
            alb[y0 + 5:y0 + 9, x:x + 5] = hexrgb("#55555a")
            h[y0 + 5:y0 + 9, x:x + 5] = 1.2
    return alb, blur(h, 0.5)


def gen_trim(n=256):
    base = hexrgb("#d6cdb8")
    grain = fbm(n, 61, 2.0, 2)
    streak = fbm(n, 62, 1.1, 1)
    wear = fbm(n, 63, 2.6, 1)
    col = base * (0.88 + 0.12 * grain[..., None]) * (1 - 0.18 * np.clip(wear - 0.6, 0, 1)[..., None] * 2)
    col = lerp(col, hexrgb("#6a5a44"), 0.35 * np.clip(wear - 0.7, 0, 1) * 3)       # worn paint to bare wood
    return col, 0.6 * streak + 0.4 * grain


GENERATORS = {"rubble": gen_rubble, "plaster": gen_plaster, "timberframe": gen_timberframe, "batten": gen_batten, "door": gen_door, "trim": gen_trim}


def base_texture(mid):
    """(albedo float, height 0..1) for a catalogue material, or None when there is neither generator nor preset image."""
    from PIL import Image
    c = info(mid)
    if c.get("gen") == "style":
        import building_styles as bs
        return bs.gen_texture(mid)
    if c.get("gen"):
        return GENERATORS[c["gen"]]()
    src = c.get("src") or mid[4:]
    p = os.path.join(TEXTURE_DIR, src + ".png")
    if not os.path.exists(p):
        return None
    rgb = np.asarray(Image.open(p).convert("RGB"), float)
    return rgb, height_from_albedo(rgb)


# ------------------------------------------------------------------ installation
def _save(path, arr):
    from PIL import Image
    Image.fromarray(arr).save(path, optimize=True)


def write_material_textures(mid, tex_dir, base_dir=None, overwrite_base=True):
    """Write <name>.png (generated materials, or when overwrite_base), <name>_n.png and <name>_mr.png. Returns the list of files written."""
    from PIL import Image
    c = info(mid)
    name = mid                                   # files are <mat_id>.png, <mat_id>_n.png (what write_glb references)
    bt = base_texture(mid)
    if bt is None:
        return []
    alb, h = bt
    out = []
    if c.get("gen") or c.get("src") or overwrite_base:
        _save(os.path.join(tex_dir, name + ".png"), to_u8(alb))
        out.append(name + ".png")
    if c.get("n", 0) > 0:
        _save(os.path.join(tex_dir, name + "_n.png"), normal_map(h, c["n"]))
        out.append(name + "_n.png")
    if c.get("mr"):
        _save(os.path.join(tex_dir, name + "_mr.png"), mr_map(h, c["rough"], 0.3, c.get("metal", 0.0)))
        out.append(name + "_mr.png")
    return out


def detail_terrain(albedo_png, out_png, width_ft, height_ft, seed=5, max_px=4096, max_ppf=4.0):
    """Re-sample the baked terrain albedo to up to max_ppf px/ft (only when that is at least 1.5x the baked density) and add ground detail:
    grass blades/clods, soil mottling, fine grain. Returns the new px/ft or None when left alone."""
    from PIL import Image
    im = Image.open(albedo_png).convert("RGB")
    ppf0 = im.size[0] / float(width_ft)
    ppf = min(max_ppf, max_px / float(max(width_ft, height_ft)))
    if ppf < ppf0 * 1.5:
        return None
    W, H = int(round(width_ft * ppf)), int(round(height_ft * ppf))
    base = np.asarray(im.resize((W, H), Image.BICUBIC), float)

    def noise(period_ft, s, beta=2.0):
        # a small periodic field resampled bicubically up to the texture size
        small = fbm(0, s, beta, 1, shape=(max(4, int(height_ft / period_ft * 4)), max(4, int(width_ft / period_ft * 4))))
        return np.asarray(Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC), float) / 255.0
    d_low = noise(40.0, seed + 1)
    d_mid = noise(9.0, seed + 2)
    d_fine = noise(1.8, seed + 3, 1.2)
    d_blade = noise(0.6, seed + 4, 0.8)
    field = 0.6 * (d_low - 0.5) + 0.7 * (d_mid - 0.5) + 0.8 * (d_fine - 0.5) + 0.7 * (d_blade - 0.5)
    hue = (d_mid - 0.5)
    out = base * (1.0 + 0.9 * field[..., None])
    out[..., 0] *= 1 + 0.10 * hue                                     # warm patches (dry grass / soil) against green
    out[..., 2] *= 1 - 0.10 * hue
    Image.fromarray(to_u8(out)).save(out_png, optimize=True)
    return ppf


def install(pack, tex_dir):
    """Write every generated/derived PNG the pack's (prepared) materials ask for into tex_dir. Returns {"files": [...], "terrain_ppf": ...}."""
    os.makedirs(tex_dir, exist_ok=True)
    prepare(pack.materials)
    files = []
    for mid, r in sorted(pack.materials.items()):
        if not r.get("_pbr") or not (r.get("normal") or r.get("mr") or r.get("_generated")):
            continue
        files += write_material_textures(mid, tex_dir, overwrite_base=bool(r.get("_generated")))
    res = {"files": files, "terrain_ppf": None}
    alb = pack.path("terrain/albedo.png") if hasattr(pack, "path") else None
    if alb and os.path.exists(alb) and "mat_terrain_albedo" in pack.materials:
        ex = pack.manifest.get("extent", {})
        res["terrain_ppf"] = detail_terrain(alb, os.path.join(tex_dir, "mat_terrain_albedo.png"), ex["width_ft"], ex["height_ft"])
    return res
