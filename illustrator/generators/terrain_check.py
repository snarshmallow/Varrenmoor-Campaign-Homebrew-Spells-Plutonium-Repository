"""Visual + numeric checks for a generated terrain: hillshade, contour preview, N-S / E-W profiles, metrics.

  python illustrator/generators/terrain_check.py [--place bridgehollow] [--out DIR] [--minor 10 --index 50]
"""
import argparse
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import terrain as T  # noqa: E402
import contours as C  # noqa: E402
import terrain_smooth as TS  # noqa: E402

REPO = T.REPO


def contour_image(h, meta, path, minor=10, index=50, scale=0.5, hill=True, params=None):
    from PIL import Image, ImageDraw
    cell = meta["cell_ft"]
    W, H = meta["size_ft"]
    fr = C.Frame(0, 0, W, H, scale, 0, 0)
    p = params or C.ContourParams(minor=minor, index=index, labels=True, font_size=7)
    cs = C.build(h, cell, fr, p)
    w, hh = int(W * scale), int(H * scale)
    if hill:
        hs = T.hillshade(h, cell)
        g = np.clip(205 + (hs - np.sin(np.radians(40))) * 70, 150, 245).astype(np.uint8)
        img = Image.fromarray(g).resize((w, hh), Image.BILINEAR).convert("RGB")
    else:
        img = Image.new("RGB", (w, hh), "white")
    d = ImageDraw.Draw(img)
    for pc in cs.pieces:
        d.line([tuple(q) for q in pc["pts"]], fill=(110, 60, 20) if pc["index"] else (160, 110, 70), width=2 if pc["index"] else 1)
    for lb in cs.labels:
        d.text((lb["x"] - 8, lb["y"] - 5), lb["text"], fill=(60, 30, 10))
    img.save(path)
    return cs


def profiles(h, meta, path, river_xy=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cell = meta["cell_ft"]
    ny, nx = h.shape
    fig, ax = plt.subplots(2, 3, figsize=(18, 7))
    for a, x in zip(ax[0], [400, 1200, 1900]):
        j = int(x / cell)
        a.plot(np.arange(ny) * cell, h[:, j]); a.set_title(f"N-S profile x={x} ft"); a.grid(alpha=.3)
    for a, y in zip(ax[1], [150, 500, 900]):
        i = int(y / cell)
        a.plot(np.arange(nx) * cell, h[i, :]); a.set_title(f"E-W profile y={y} ft"); a.grid(alpha=.3)
    for a in ax.ravel():
        a.set_ylabel("ft")
    plt.tight_layout(); plt.savefig(path, dpi=70); plt.close()


def relief(h, meta, path, exag=2.2):
    """Colour-hypsometric hillshade at 4x for eyeballing."""
    from scipy import ndimage as ndi
    from PIL import Image
    cell = meta["cell_ft"]
    hh = ndi.zoom(h.astype(float), 4, order=3)
    hs = T.hillshade(hh, cell / 4, exag=exag)
    t = (hh - hh.min()) / (hh.max() - hh.min())
    stops = np.array([0, .12, .35, .6, .85, 1.0])
    cols = np.array([[60, 120, 70], [140, 175, 95], [185, 170, 115], [160, 130, 100], [150, 140, 135], [245, 245, 245]], float)
    rgb = np.stack([np.interp(t, stops, cols[:, k]) for k in range(3)], -1)
    shade = np.clip(0.55 + 0.75 * hs, 0.35, 1.2)
    Image.fromarray(np.clip(rgb * shade[..., None], 0, 255).astype(np.uint8)).save(path)


def metrics(h, meta, water_json=None):
    cell = meta["cell_ft"]
    ny, nx = h.shape
    yy, xx = np.mgrid[0:ny, 0:nx] * cell
    gy, gx = np.gradient(h.astype(float), cell)
    s = np.hypot(gx, gy)
    out = {"elev_min": float(h.min()), "elev_max": float(h.max()), "relief": float(h.max() - h.min())}
    basin = (yy > 450) & (yy < 1250) & (xx > 750) & (xx < 1650)
    out["basin_elev_p5_p50_p95"] = [float(np.percentile(h[basin], q)) for q in (5, 50, 95)]
    out["basin_relief_ft"] = out["basin_elev_p5_p50_p95"][2] - out["basin_elev_p5_p50_p95"][0]
    rise = np.hypot(xx - 1200, yy - 700) < 250
    if water_json and os.path.exists(water_json):
        w = json.load(open(water_json, encoding="utf-8"))["water"][0]["centerline"]
        c = np.array(w)
        dm = np.min(np.hypot(xx[..., None] - c[:, 0], yy[..., None] - c[:, 1]), axis=-1) if False else None
        # bed profile
        from scipy import ndimage as ndi
        c = c[(c[:, 1] >= 0) & (c[:, 1] <= (ny - 1) * cell)]
        z = ndi.map_coordinates(h.astype(float), [c[:, 1] / cell, c[:, 0] / cell], order=1)
        dz = np.diff(z)
        out["river_bed_start_end"] = [float(z[0]), float(z[-1])]
        out["river_max_climb_ft"] = float(max(dz.max(), 0))
        out["river_total_climb_ft"] = float(dz[dz > 0].sum())
        out["river_min_gradient_ft_per_100ft"] = float(-dz.max() / 50 * 100 if dz.max() < 0 else 0)
        near = np.min(np.hypot(xx[..., None] - c[::2, 0], yy[..., None] - c[::2, 1]), axis=-1) if False else None
        from scipy.spatial import cKDTree
        d, _ = cKDTree(c).query(np.c_[xx.ravel(), yy.ravel()])
        d = d.reshape(h.shape)
        rise_nr = rise & (d > 70)
    else:
        rise_nr = rise
    out["rise_slope_mean_p95_max"] = [float(s[rise_nr].mean()), float(np.percentile(s[rise_nr], 95)), float(s[rise_nr].max())]
    out["terracing"] = TS.terrace_metrics(h, cell)
    out["wall_slope_p50_p95"] = [float(np.percentile(s[yy < 300], 50)), float(np.percentile(s[yy < 300], 95))]
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", default="bridgehollow")
    ap.add_argument("--out", default=os.path.join(REPO, "illustrator", "out", "terrain_check"))
    ap.add_argument("--minor", type=float, default=10)
    ap.add_argument("--index", type=float, default=50)
    ap.add_argument("--heightmap")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    d = os.path.join(REPO, "world", a.place, "terrain")
    h = np.load(a.heightmap or os.path.join(d, "heightmap.npy"))
    meta = json.load(open(os.path.join(d, "terrain_meta.json"), encoding="utf-8"))
    T.save_preview(h, meta, os.path.join(a.out, "hillshade.png"), zoom=3)
    contour_image(h, meta, os.path.join(a.out, "contours.png"), a.minor, a.index)
    profiles(h, meta, os.path.join(a.out, "profiles.png"))
    relief(h, meta, os.path.join(a.out, "relief.png"))
    m = metrics(h, meta, os.path.join(REPO, "world", a.place, "water.json"))
    print(json.dumps(m, indent=1))
    if not m["terracing"]["terrace_ok"]:
        print("FAIL: terracing / stair-step score above the limits", TS.TERRACE_LIMITS)
        sys.exit(1)
