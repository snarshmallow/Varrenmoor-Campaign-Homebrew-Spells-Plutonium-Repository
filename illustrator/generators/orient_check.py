"""Orientation check for every terrain / map preview producer: is north up and east right, the same as the Illustrator map and the world feet?

  python illustrator/generators/orient_check.py [--out DIR] [--real PLACE] [--json]

World convention (place.json "origin": "top-left, y down"; terrain_meta node_convention):
  feet x east, y SOUTH, origin at the north-west (top-left) corner; heightmap.npy h[i, j] is the node at x = j * cell_ft, y = i * cell_ft
  (row = y = south, column = x = east). Images keep that: pixel row 0 = north edge, column 0 = west edge. Illustrator's artboard is y-up,
  so only the page <-> feet step flips y (panel VB.docToFt / VB.ftToDoc); the 3D pack flips y once more (Blender Y = height_ft - y, north).

What it does: builds a SYNTHETIC place in a temp world root (never the repo's world/) with asymmetric features (a peak in the north-east,
a pit in the south-west, a ridge along the west edge, a river valley + water polygon along the east, a building in the north-east, a road
along the south edge, a foliage polygon in the north-east) on a NON-square 1600 x 1000 ft frame (a transpose cannot hide), runs each
producer and decodes the output: the dihedral transform (identity, flip_ud, flip_lr, rot180, transpose, rot90, rot270, antitranspose)
that best maps the truth onto the output is reported per producer; anything but identity is a bug.

--real PLACE also copies world/PLACE to a temp root (read only) and correlates the water (river) mask with LOW terrain in each of the 8
orientations of the Paint preview grid: the right orientation has the river in the valley (most negative correlation with height).
"""
import argparse
import json
import os
import shutil
import sys
import tempfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))

PLACE = "orient_synth"
W_FT, H_FT, CELL = 1600.0, 1000.0, 10.0
PEAK = (1400.0, 180.0)            # north-east
PIT = (220.0, 840.0)              # south-west
RIVER_X = 1100.0                  # valley + water polygon along x = 1100 (east half), north -> south
NE_BLD = [[1300, 300], [1360, 300], [1360, 340], [1300, 340]]
S_ROAD = [[100, 960], [1500, 960]]
NE_POLY = [[1150, 40], [1560, 40], [1560, 420], [1150, 420]]

TRANSFORMS = {
    "identity": lambda a: a, "flip_ud": lambda a: a[::-1], "flip_lr": lambda a: a[:, ::-1], "rot180": lambda a: a[::-1, ::-1],
    "transpose": lambda a: a.T, "rot90": lambda a: np.rot90(a, 1), "rot270": lambda a: np.rot90(a, 3), "antitranspose": lambda a: np.rot90(a, 2).T,
}


# ------------------------------------------------------------------ synthetic place
def synth_heights():
    nx, ny = int(W_FT / CELL) + 1, int(H_FT / CELL) + 1
    X, Y = np.meshgrid(np.arange(nx) * CELL, np.arange(ny) * CELL)
    h = 500.0 + 0.02 * (H_FT - Y)                                                        # gentle fall to the south
    h += 260.0 * np.exp(-((X - PEAK[0]) ** 2 + (Y - PEAK[1]) ** 2) / (2 * 120.0 ** 2))  # NE peak
    h -= 120.0 * np.exp(-((X - PIT[0]) ** 2 + (Y - PIT[1]) ** 2) / (2 * 90.0 ** 2))     # SW pit
    h += 90.0 * np.exp(-(X - 60.0) ** 2 / (2 * 50.0 ** 2)) * (Y < 700)                    # west ridge (northern 70 %)
    h -= 45.0 * np.exp(-(X - RIVER_X) ** 2 / (2 * 40.0 ** 2)) * (Y > 420)                 # river valley, south of the peak
    return h.astype(np.float32)


def _dump(p, o):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1)


def make_synth(root):
    """Write the synthetic place under root/<PLACE>. Returns the place folder."""
    d = os.path.join(root, PLACE)
    h = synth_heights()
    os.makedirs(os.path.join(d, "terrain"), exist_ok=True)
    np.save(os.path.join(d, "terrain", "heightmap.npy"), h)
    _dump(os.path.join(d, "terrain", "terrain_meta.json"), {"size_ft": [W_FT, H_FT], "cell_ft": CELL, "nx": int(h.shape[1]), "ny": int(h.shape[0]),
          "elev_min": float(h.min()), "elev_max": float(h.max()), "relief_ft": float(h.max() - h.min()), "units": "feet",
          "node_convention": "h[i,j] at x=j*cell_ft, y=i*cell_ft (y down)", "sea_level_ft": 0.0})
    _dump(os.path.join(d, "place.json"), {"id": PLACE, "name": "Orientation test", "kind": "hamlet", "units": "feet", "origin": "top-left, y down",
          "bounds": {"width_ft": W_FT, "height_ft": H_FT}, "sea_level_ft": 0.0})
    _dump(os.path.join(d, "buildings", "bld_ne.json"), {"id": "bld_ne", "name": "NE house", "kind": "house", "geometry": {"type": "polygon", "points": NE_BLD}})
    _dump(os.path.join(d, "streets.json"), {"place": PLACE, "streets": [{"id": "str_south", "name": "South road", "kind": "road",
          "geometry": {"type": "polyline", "points": S_ROAD, "width_ft": 20}}]})
    river = [[RIVER_X - 15, 430], [RIVER_X + 15, 430], [RIVER_X + 15, H_FT], [RIVER_X - 15, H_FT]]
    _dump(os.path.join(d, "water.json"), {"place": PLACE, "water": [{"id": "wat_river", "kind": "river", "geometry": {"type": "polygon", "points": river}}]})
    return d


# ------------------------------------------------------------------ decoding
def _resize(a, shape):
    """Nearest-neighbour resample of a 2D array to shape (rows, cols), cell centres aligned."""
    a = np.asarray(a, float)
    ri = np.clip(((np.arange(shape[0]) + 0.5) * a.shape[0] / shape[0]).astype(int), 0, a.shape[0] - 1)
    ci = np.clip(((np.arange(shape[1]) + 0.5) * a.shape[1] / shape[1]).astype(int), 0, a.shape[1] - 1)
    return a[ri][:, ci]


def _corr(a, b):
    a, b = np.asarray(a, float).ravel(), np.asarray(b, float).ravel()
    a, b = a - a.mean(), b - b.mean()
    den = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / den) if den > 0 else 0.0


def best_transform(out, truth):
    """-> (name, scores): the transform T with out ~ T(truth) (truth in map orientation: row = south, column = east)."""
    sc = {k: round(_corr(out, _resize(f(truth), out.shape)), 4) for k, f in TRANSFORMS.items()}
    return max(sc, key=sc.get), sc


def img_lum(path):
    from PIL import Image
    return np.asarray(Image.open(path).convert("RGB"), float)


def tint_level(rgb):
    """Elevation proxy for the green -> tan -> grey -> white ramp: min / max channel (greys out towards white as the ground rises; the
    hillshade multiplies all channels, so the ratio ignores it)."""
    return rgb.min(axis=-1) / np.maximum(rgb.max(axis=-1), 1.0)


def colour_mask(rgb, col, tol=12):
    return (np.abs(rgb - np.array(col, float)).max(axis=-1) <= tol).astype(float)


def quadrant(x, y, w=W_FT, h=H_FT):
    return ("N" if y < h / 2 else "S") + ("E" if x > w / 2 else "W")


def _row(name, transform, ok, detail, kind="verified"):
    return {"producer": name, "transform": transform, "ok": bool(ok), "detail": detail, "kind": kind}


# ------------------------------------------------------------------ producers
def check_all(work, real=None):
    import heightmap_paint as HP
    import worldio
    rows = []
    wroot = os.path.join(work, "world")
    make_synth(wroot)
    truth = synth_heights()

    h, meta = worldio.load_terrain(PLACE, root=wroot, edits=False)
    i, j = np.unravel_index(int(np.argmax(h)), h.shape)
    q = quadrant(j * CELL, i * CELL)
    rows.append(_row("worldio.load_terrain (heightmap.npy rows/cols)", "identity" if q == "NE" else "?", q == "NE", f"max at x={j * CELL:.0f} y={i * CELL:.0f} ft ({q})"))

    # heightmap_paint export-preview: float .bin grid the Paint canvas draws + the PNG
    png, bdir = os.path.join(work, "hp.png"), os.path.join(work, "hp_bin")
    pv = HP.export_preview(PLACE, root=wroot, wdir=os.path.join(work, "hpwork"), max_px=120, png=png, bin_dir=bdir, layer="base")
    grid = np.fromfile(os.path.join(bdir, "preview_h.bin"), "<f4").reshape(pv["ph"], pv["pw"])
    t, sc = best_transform(grid, truth)
    rows.append(_row("heightmap_paint export-preview .bin (Paint canvas grid)", t, t == "identity", f"{pv['pw']}x{pv['ph']} px, factor {pv['factor']}, corr {sc[t]}"))
    t, sc = best_transform(tint_level(img_lum(png)), truth)
    rows.append(_row("heightmap_paint export-preview PNG", t, t == "identity", f"corr {sc[t]}"))

    # paint stroke: feet -> grid (a raise dab at the NE peak position must lift the NE nodes)
    hh = truth.astype(np.float64).copy()
    HP.apply_stroke(hh, CELL, {"tool": "raise", "points": [list(PEAK)], "radius_ft": 60, "strength": 1.0, "rate_ft": 10})
    dd = hh - truth
    i, j = np.unravel_index(int(np.argmax(dd)), dd.shape)
    ok = abs(j * CELL - PEAK[0]) <= CELL and abs(i * CELL - PEAK[1]) <= CELL
    rows.append(_row("heightmap_paint apply-stroke (feet -> grid)", "identity" if ok else "?", ok, f"dab at {PEAK} raised node x={j * CELL:.0f} y={i * CELL:.0f}"))

    # terrain.py preview PNG
    import terrain
    tp = os.path.join(work, "terrain_preview.png")
    terrain.save_preview(truth, {"cell_ft": CELL, "elev_min": float(truth.min()), "elev_max": float(truth.max())}, tp, zoom=1)
    t, sc = best_transform(tint_level(img_lum(tp)), truth)
    rows.append(_row("terrain.py save_preview PNG", t, t == "identity", f"corr {sc[t]}"))

    # terrain_patch: polygon (feet) -> nodes, and its preview PNG
    import terrain_patch as TP
    pm = {"cell_ft": CELL, "nx": truth.shape[1], "ny": truth.shape[0], "sea_level_ft": 0.0}
    flat = np.full(truth.shape, 500.0, np.float32)
    after = TP.apply_patch(flat, pm, NE_POLY, {"terrain_type": "rolling_hills", "max_height_ft": 700.0, "avg_height_ft": 600.0, "feather_ft": 20.0, "roughness": 0.0})
    dd = np.asarray(after) - flat
    ys, xs = np.nonzero(dd > 1.0)
    cx, cy = xs.mean() * CELL, ys.mean() * CELL
    ok = quadrant(cx, cy) == "NE" and NE_POLY[0][0] - 30 <= cx <= NE_POLY[1][0] + 30
    rows.append(_row("terrain_patch apply (lasso polygon -> grid)", "identity" if ok else "?", ok, f"raised area centre x={cx:.0f} y={cy:.0f} ({quadrant(cx, cy)})"))
    pp = os.path.join(work, "patch_preview.png")
    TP.save_preview(truth, {"cell_ft": CELL, "sea_level_ft": 0.0}, pp, polygon_ft=None, zoom=1)
    t, sc = best_transform(tint_level(img_lum(pp)), truth)
    rows.append(_row("terrain_patch save_preview PNG (patch preview)", t, t == "identity", f"corr {sc[t]}"))

    # shading.py (map terrain shading raster, windowed like place_render): hillshade-only render vs the truth hillshade
    import shading
    img, _ = shading.render(truth, {"cell_ft": CELL, "size_ft": [W_FT, H_FT]}, [], 0.1, hill={"enabled": True, "azimuth": 315, "altitude": 40}, verbose=False,
                            window=(0, 0, W_FT, H_FT))
    t, sc = best_transform(img[..., 0], shading.hillshade(truth, CELL))
    rows.append(_row("shading.py render (map shading PNG)", t, t == "identity", f"{img.shape[1]}x{img.shape[0]} px, corr {sc[t]}"))

    # contours.py: the highest closed contour (page points, y down like the SVG) sits around the NE peak
    import contours as CT
    k = 0.5
    cs = CT.build(truth, CELL, CT.Frame(0, 0, W_FT, H_FT, k))
    top = max(cs.pieces, key=lambda p: p["elev"])
    P = np.asarray(top["pts"], float)
    cx, cy = P[:, 0].mean() / k, P[:, 1].mean() / k
    rows.append(_row("contours.py build (contour SVG)", "identity" if quadrant(cx, cy) == "NE" else "?", quadrant(cx, cy) == "NE",
                     f"top contour {top['elev']:.0f} ft centred x={cx:.0f} y={cy:.0f} ft ({quadrant(cx, cy)})"))

    # sun_preview.shade: a low sun in the EAST lights the east face of the NE peak
    import sun_preview as SP
    alb = np.full(truth.shape + (3,), 0.3, np.float32)
    col, _ = SP.shade(truth, alb, np.zeros(truth.shape, np.float32), CELL, {"sun": {"azimuth": 90, "altitude": 20}, "ambient": {}, "shadows": {"on": False}})
    pi_, pj = int(PEAK[1] / CELL), int(PEAK[0] / CELL)
    east, west = float(col[pi_, pj + 8].mean()), float(col[pi_, pj - 8].mean())
    rows.append(_row("sun_preview.shade (sun preview)", "identity" if east > west else "flip_lr", east > west, f"sun az 90: east face {east:.3f} vs west face {west:.3f}"))

    # foliage: Env height lookups, scatter inside a NE polygon, by-height rule, preview PNG, 3D grounding
    import foliage as FO
    env = FO.Env.from_place(PLACE, root=os.path.join(wroot, PLACE))
    zne, zsw = float(env.z(*PEAK)), float(env.z(*PIT))
    rows.append(_row("foliage Env.z (height lookup)", "identity" if zne > zsw else "?", zne > zsw, f"z(NE peak)={zne:.0f} ft, z(SW pit)={zsw:.0f} ft"))
    lib = FO._lib()
    its = FO.scatter(env, lib, {"mix": [{"species": "spruce", "weight": 1}], "density_per_ha": 120, "seed": 3, "slope_max_deg": 89}, polygon=NE_POLY)
    if its:
        xs, ys = np.array([i["x"] for i in its]), np.array([i["y"] for i in its])
        inside = bool(np.all((xs >= NE_POLY[0][0]) & (xs <= NE_POLY[1][0]) & (ys >= NE_POLY[0][1]) & (ys <= NE_POLY[2][1])))
        rows.append(_row("foliage scatter in a NE polygon", "identity" if inside else "?", inside, f"{len(its)} trees, centre x={xs.mean():.0f} y={ys.mean():.0f} ({quadrant(xs.mean(), ys.mean())})"))
        dz = max(abs(float(env.z(i["x"], i["y"])) - float(i.get("z") or env.z(i["x"], i["y"]))) for i in its)
        rows.append(_row("foliage tree z = terrain at (x, y)", "identity" if dz < 1.0 else "?", dz < 1.0, f"max |z - terrain| {dz:.2f} ft"))
    hi_ = float(np.percentile(truth, 97))
    its2 = FO.scatter(env, lib, {"mix": [{"species": "spruce", "weight": 1}], "density_per_ha": 120, "seed": 4, "slope_max_deg": 89, "elev_min_ft": hi_},
                      polygon=[[0, 0], [W_FT, 0], [W_FT, H_FT], [0, H_FT]])
    if its2:
        q = quadrant(np.mean([i["x"] for i in its2]), np.mean([i["y"] for i in its2]))
        rows.append(_row("foliage by-height rule (elev_min = top 3 %)", "identity" if q == "NE" else "?", q == "NE", f"{len(its2)} trees, centred {q} (peak is NE)"))
    doc = FO.FoliageDoc(PLACE, path=os.path.join(work, "foliage.json"), data={})
    fp = os.path.join(work, "foliage_preview.png")
    FO.preview_png(doc, lib, env, fp, max_px=400)
    rgb = img_lum(fp)
    water = colour_mask(rgb, (120, 160, 205), 3)
    wt = np.zeros(truth.shape)
    wt[int(430 / CELL):, int((RIVER_X - 15) / CELL):int((RIVER_X + 15) / CELL) + 1] = 1
    t, sc = best_transform(water, wt)
    rows.append(_row("foliage preview PNG (water / roads / trees)", t, t == "identity", f"water mask corr {sc[t]}"))
    bld = colour_mask(rgb, (120, 108, 100), 3)
    ys, xs = np.nonzero(bld)
    s = rgb.shape[1] / W_FT
    q = quadrant(xs.mean() / s, ys.mean() / s) if len(xs) else "?"
    rows.append(_row("foliage preview PNG building", "identity" if q == "NE" else "?", q == "NE", f"building pixels centred {q}"))
    import road_grade as RG
    zm = float(RG.mesh_height(truth, CELL, *PEAK))
    rows.append(_row("3D mesh_height (pack ground for trees / buildings)", "identity" if abs(zm - zne) < 2 else "?", abs(zm - zne) < 2, f"mesh z at NE peak {zm:.0f} vs Env.z {zne:.0f}", "verified"))
    import worldpack as WP
    fr = WP.Frame(W_FT, H_FT)
    bx, by, _ = fr.to_blender(PEAK[0], PEAK[1], 0.0)
    ok = bx > W_FT / 2 * 0.3048 and by > (H_FT / 2) * 0.3048
    rows.append(_row("3D pack frame to_blender (Blender y = north)", "identity" if ok else "?", ok, f"NE peak -> Blender x={bx:.0f} m, y={by:.0f} m (north-east of the SW origin)"))

    if real:
        rows += check_real(work, real)
    return rows


def water_mask(points, shape, cell):
    from PIL import Image, ImageDraw
    m = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(m).polygon([(x / cell, y / cell) for x, y in points], fill=1)
    return np.asarray(m, float)


def check_real(work, place):
    """Copy world/<place> to a temp root (read only) and find the orientation of the Paint preview grid that puts the river in the valley."""
    import heightmap_paint as HP
    src = os.path.join(REPO, "world", place)
    wroot = os.path.join(work, "real")
    dst = os.path.join(wroot, place)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("export", "streets_backups", "*.glb"), dirs_exist_ok=True)
    bdir = os.path.join(work, "real_bin")
    pv = HP.export_preview(place, root=wroot, wdir=os.path.join(work, "real_hpwork"), max_px=10_000, bin_dir=bdir, layer="base")
    grid = np.fromfile(os.path.join(bdir, "preview_h.bin"), "<f4").reshape(pv["ph"], pv["pw"]).astype(float)
    with open(os.path.join(dst, "water.json"), encoding="utf-8") as f:
        ws = json.load(f).get("water", [])
    cell = pv["cell_ft"] * pv["factor"]
    m = np.zeros(grid.shape)
    for w in ws:
        g = w.get("geometry") or {}
        if g.get("type") == "polygon" and len(g.get("points", [])) > 2:
            m = np.maximum(m, water_mask(g["points"], grid.shape, cell))
    if not m.any():
        return [_row(f"REAL {place}: river vs valley", "n/a", True, "no water polygon", "inferred")]
    sc = {}
    for k, f in TRANSFORMS.items():
        a = f(grid)
        if a.shape != m.shape:
            a = _resize(a, m.shape)
        rank = np.argsort(np.argsort(a, axis=1), axis=1) / max(a.shape[1] - 1, 1)   # 0 = lowest node of its row (west-east profile)
        sc[k] = round(float((rank * m).sum() / m.sum()), 4)
    best = min(sc, key=sc.get)       # the river runs along the valley floor: the lowest mean height rank across its rows
    rows = []
    try:                              # where the river sits in the map's town window (what the Illustrator page shows)
        with open(os.path.join(dst, "view_settings.json"), encoding="utf-8") as f:
            vs = json.load(f)
        pr = vs["presets"]["town"]
        fx, fy = pr["focus"]
        hw = (vs["page_in"][0] - 2 * vs["margin_in"]) * pr["scale_ft_per_in"] / 2
        hh = (vs["page_in"][1] - 2 * vs["margin_in"]) * pr["scale_ft_per_in"] / 2
        ys, xs = np.nonzero(m)
        sel = (xs * cell >= fx - hw) & (xs * cell <= fx + hw) & (ys * cell >= fy - hh) & (ys * cell <= fy + hh)
        if sel.any():
            u = (xs[sel].mean() * cell - (fx - hw)) / (2 * hw)
            rows.append(_row(f"REAL {place}: river inside the town map window", "info", True,
                             f"window x {fx - hw:.0f}..{fx + hw:.0f}, y {fy - hh:.0f}..{fy + hh:.0f} ft (= {2 * hw * 2 * hh / (cell * cell * grid.size) * 100:.1f} % of the "
                             f"place); river at {u * 100:.0f} % of the window width from the west edge", "verified"))
    except (OSError, KeyError, ValueError, TypeError):
        pass
    return rows + [_row(f"REAL {place}: river mask vs Paint preview heights", best, best == "identity",
                 "mean height rank of the water nodes in their row, per orientation of the preview grid (0 = valley floor; lowest wins): "
                 + ", ".join(f"{k} {v}" for k, v in sc.items()))]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", help="keep the outputs here (default: a temp folder, removed afterwards)")
    ap.add_argument("--real", help="also check a real place (copied to a temp root, read only), e.g. mountain_pass_fort_town")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    work = a.out or tempfile.mkdtemp(prefix="orient_")
    os.makedirs(work, exist_ok=True)
    try:
        rows = check_all(work, a.real)
    finally:
        if not a.out:
            shutil.rmtree(work, ignore_errors=True)
    if a.json:
        print(json.dumps({"ok": all(r["ok"] for r in rows), "rows": rows}, indent=1))
    else:
        for r in rows:
            print(f"{'OK ' if r['ok'] else 'BAD'}  {r['producer']:<58} {r['transform']:<12} {r['detail']}")
        print("ALL OK" if all(r["ok"] for r in rows) else "ORIENTATION PROBLEMS FOUND")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
