"""Offline before/after previews + numbers for the terrain-edge / apron fixes (no Foundry). Usage:
  python tools/apron_fix2_render.py <place_id> <tag> [--ease-ft N] [--out DIR] [--no-seam-normals]
place_id: a folder in world/ with an export (zz_bridge_scratch, bridgehollow__dyers_walk_local). Heights come from worldpack_mesh.final_heights (so the carve ease is in), not from the
exported terrain.glb: nothing in world/ is written. Writes <out>/<place>_<tag>_{overhead,slope,oblique}.png and prints max slope within 150 ft of the seam + seam normal discontinuity."""
import argparse, math, os, sys
import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "generators"))
import padding_heightmap as ph
import worldpack as wp
import worldpack_mesh as wm


def slope_deg_grid(h, cell):
    gy, gx = np.gradient(h, cell)
    return np.degrees(np.arctan(np.hypot(gx, gy)))


def metrics(place, V, tris, nrm):
    d = {}
    # apron slope within 150 ft of the seam: per triangle
    a, b, c = V[tris[:, 0]], V[tris[:, 1]], V[tris[:, 2]]
    fn = np.cross(b - a, c - a)
    sl = np.degrees(np.arccos(np.clip(np.abs(fn[:, 2]) / np.maximum(np.linalg.norm(fn, axis=1), 1e-12), 0, 1)))
    cen = (a + b + c) / 3
    s = place.rect_dist(cen[:, 0], cen[:, 1])[0]
    m = s <= 150
    d["apron_max_slope_deg_150ft"] = float(sl[m].max())
    d["apron_max_slope_deg_beyond_20ft"] = float(sl[(s > 20) & m].max())
    d["apron_max_slope_deg_beyond_40ft"] = float(sl[(s > 40) & m].max())
    d["apron_p99_slope_deg_150ft"] = float(np.percentile(sl[m], 99))
    sg = slope_deg_grid(place.h, place.cell)
    em = np.zeros(sg.shape, bool)
    k = int(round(150 / place.cell))
    em[:k] = em[-k:] = True; em[:, :k] = em[:, -k:] = True
    d["terrain_max_slope_deg_150ft_of_edge"] = float(sg[em].max())
    # seam normal discontinuity: terrain edge normal vs apron ring-0 normal
    info = None
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("place"); ap.add_argument("tag")
    ap.add_argument("--ease-ft", type=float, default=100.0)
    ap.add_argument("--out", default=os.path.join(HERE, "..", "out", "apron_fix2"))
    ap.add_argument("--no-seam-normals", action="store_true")
    ap.add_argument("--px", type=int, default=900)
    a = ap.parse_args()
    root = os.path.join(HERE, "..", "..", "world")
    pack = wp.load_pack(os.path.join(root, a.place, "export"))
    hfinal = wm.final_heights(pack, carve_edge_ease_ft=a.ease_ft)
    orig = ph.Place

    class P(orig):
        def __init__(self, *k, **kw):
            super().__init__(*k, **kw)
            self.h = np.asarray(hfinal, np.float64)

    ph.Place = P
    res = ph.generate(a.place, scene=None, apron_albedo_px=256, world_root=root)
    place, V, tris, info = res["place"], res["V"], res["tris"], res["ring_info"]
    r0 = np.arange(info["ring_start"][0], info["ring_start"][0] + info["ring_len"][0])
    nrm_plain = ph.vertex_normals(V, tris)
    nrm = ph.vertex_normals(V, tris, (r0, ph.terrain_edge_normals(place, V[r0, 0], V[r0, 1])))
    if a.no_seam_normals:
        nrm = nrm_plain
    m = metrics(place, V, tris, nrm)
    tn = ph.terrain_edge_normals(place, V[r0, 0], V[r0, 1])
    cosang = lambda u, v: np.degrees(np.arccos(np.clip((u * v).sum(1), -1, 1)))
    m["seam_normal_diff_deg_max_plain"] = float(cosang(nrm_plain[r0], tn).max())
    m["seam_normal_diff_deg_max"] = float(cosang(nrm[r0], tn).max())
    m["seam_normal_diff_deg_mean_plain"] = float(cosang(nrm_plain[r0], tn).mean())
    print(a.place, a.tag, m)
    os.makedirs(a.out, exist_ok=True)
    # --- scene triangles: terrain (step 2) + apron, in place coords (x east, y south, z up)
    step = 2
    h = place.h[::step, ::step]
    ny, nx = h.shape
    jj, ii = np.meshgrid(np.arange(nx) * place.cell * step, np.arange(ny) * place.cell * step)
    TV = np.column_stack([jj.ravel(), ii.ravel(), h.ravel() - place.z_origin])
    idx = np.arange(ny * nx).reshape(ny, nx)
    A, B, C, D = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    TT = np.concatenate([np.stack([A, C, B], 1), np.stack([B, C, D], 1)])
    gn = ph.grid_vertex_normals(place.h[::step, ::step], place.cell * step)         # glTF frame (x, up, south)
    allV = np.concatenate([TV, V]); allT = np.concatenate([TT, tris + len(TV)])
    allN = np.concatenate([gn.reshape(-1, 3), nrm])
    N3 = np.column_stack([allN[:, 0], allN[:, 2], allN[:, 1]])                      # back to x, y(south), z(up)
    light = np.array([-0.5, -0.6, 0.62]); light /= np.linalg.norm(light)
    shade = np.clip(N3 @ light, 0, 1) * 0.8 + 0.2
    zr = (allV[:, 2] - allV[:, 2].min()) / max(np.ptp(allV[:, 2]), 1)
    base = np.stack([0.28 + 0.2 * zr, 0.45 + 0.1 * zr, 0.2 + 0.1 * zr], 1)
    inside = (allV[:, 0] >= -1e-6) & (allV[:, 0] <= place.W + 1e-6) & (allV[:, 1] >= -1e-6) & (allV[:, 1] <= place.H + 1e-6)
    base[inside] *= np.array([1.0, 1.0, 1.0]); base[inside, 2] += 0.12              # terrain slightly bluer so the seam is visible
    col = np.clip(base * shade[:, None], 0, 1)
    slope = np.degrees(np.arccos(np.clip(N3[:, 2], 0, 1)))
    ramp = np.clip(slope / 60.0, 0, 1)
    scol = np.stack([ramp, 0.3 * (1 - ramp) + 0.2, 1 - ramp], 1)

    def render(cols, view, name):
        W_ = a.px
        cx, cy = place.W / 2, place.H / 2
        ext = max(place.W, place.H) / 2 + 220
        if view == "top":
            sx, sy = (allV[:, 0] - cx) / ext, (allV[:, 1] - cy) / ext
            depth = allV[:, 2]
        else:                                              # oblique from the south-west, looking at the north-east river end
            az, el = math.radians(215), math.radians(28)
            u = np.array([math.cos(az), math.sin(az), 0]); w = np.array([-math.sin(az) * math.cos(el), math.cos(az) * math.cos(el), math.sin(el)])
            fw = np.cross([0, 0, 1], u)
            fw = np.array([math.cos(az - math.pi / 2), math.sin(az - math.pi / 2), 0])
            rel = allV - np.array([cx, cy, 0])
            r_ = np.array([math.cos(az + math.pi / 2), math.sin(az + math.pi / 2), 0])
            f_ = np.array([-r_[1], r_[0], 0])
            sx = (rel @ r_) / ext
            sy = -((rel @ f_) * math.sin(el) * -1 + rel[:, 2] * math.cos(el)) / ext
            sy = -(rel[:, 2] * math.cos(el) - (rel @ f_) * math.sin(el)) / ext
            depth = rel @ f_
        px = np.column_stack([(sx * 0.5 + 0.5) * W_, (sy * 0.5 + 0.5) * W_ * (1 if view == "top" else 1)])
        im = Image.new("RGB", (W_, W_), (168, 198, 232))
        dr = ImageDraw.Draw(im)
        order = np.argsort(-(depth[allT].mean(1)) if view != "top" else depth[allT].mean(1))
        for t in order:
            tri = allT[t]
            c = tuple(int(255 * v) for v in cols[tri].mean(0))
            dr.polygon([tuple(px[i]) for i in tri], fill=c)
        im.save(os.path.join(a.out, f"{a.place}_{a.tag}_{name}.png"))
    render(col, "top", "overhead")
    render(scol, "top", "slope")
    render(col, "obl", "oblique")


if __name__ == "__main__":
    main()
