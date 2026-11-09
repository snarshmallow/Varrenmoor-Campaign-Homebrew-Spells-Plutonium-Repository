"""Water surface meshes prepared for the 3D Canvas water shader (foundry-bridge/water/vb_water.js).

What the shader needs, written per vertex as the custom glTF attribute _VBWATER (VEC4 float, Mesh.X["_VBWATER"]):
  x  shore   0 at the bank .. 1 at `shore_ft` (or half the width of a narrow river) from it: foam, depth tint, opacity
  y  slope   0..1, how steep the channel is here (river flow speed; 0 on still water)
  z  heading bearing (compass degrees / 360) that +v of the UVs points to: a river's flow direction, 180 (south) on lakes
  w  0.5..0.75  marker "this vertex carries water data" (a missing attribute reads as 0,0,0,1); above 0.5 = river end fade ((w - 0.5) / 0.25: 0 full water, 1 invisible)
UVs are in units of 10 ft: u across (rivers: bank to bank, left of travel = +u) and v along the flow (rivers) or plan x/y (lakes: u east, v south),
so the shader scrolls the ripple pattern in feet whatever scale Foundry gives the tile. The material is named VB_water_<preset>, which is how the shader
finds the mesh; node extras carry {"vbWater": {preset, params}} for tools and for the live tile flags.
"""
import math

import numpy as np

import worldpack_mesh as wm
import water_presets as wpz

FT = wm.FT
UV_FT = 10.0                  # one UV unit = 10 ft
SHORE_FT = 25.0               # shore factor reaches 1 this far from the bank (or at mid-channel on narrow rivers)
ACROSS = 9                    # rows across a river ribbon (bank factor needs interior rows)
SLOPE_FULL = 0.04             # 4 % surface slope = slope factor 1
SLOPE_BASE_FT = 40.0          # slope measured over +-40 ft along the channel (the pack's surface heights are stepped)
MARK = 0.5
END_FT = 150.0                # a river ribbon fades out (alpha to 0, width to END_NARROW) over this length at both ends: no polygon edge where it leaves the map / meets the bank
END_NARROW = 0.45
END_W = 0.25                  # w = MARK + END_W * end_fade (0 = full water .. 1 = invisible); the shader reads w in [MARK, MARK + END_W]


def material_record(mid):
    """pack-less material record for write_glb: a translucent plain surface (no textures; the shader is procedural). What you see without the script."""
    p = wpz.resolve(wpz.preset_of_material(mid) or "lake")
    return {"id": mid, "mean_color": p["shallow_color"], "roughness": 0.05, "metallic": 0.0, "alpha": round(1.0 - 0.55 * p["transparency"], 3)}


def _attr(shore, slope, heading_deg, end_fade=None):
    n = len(shore)
    X = np.zeros((n, 4))
    X[:, 0] = np.clip(shore, 0, 1)
    X[:, 1] = np.clip(slope, 0, 1)
    X[:, 2] = (np.asarray(heading_deg, float) % 360.0) / 360.0
    X[:, 3] = MARK if end_fade is None else MARK + END_W * np.clip(end_fade, 0, 1)
    return X


def end_fade(cum_ft, end_ft=END_FT):
    """River end fade per centreline vertex from the along-channel distance cum_ft: 1 at either end, smooth to 0 at end_ft from it (0 everywhere on a river shorter than 2 * end_ft / 2... clamped)."""
    c = np.asarray(cum_ft, float)
    total = float(c[-1])
    e = min(end_ft, total / 2.0 - 1e-6) if total > 0 else 0.0
    if e <= 0:
        return np.zeros(len(c))
    d = np.minimum(c, total - c) / e
    t = np.clip(d, 0, 1)
    return 1.0 - t * t * (3 - 2 * t)


def densify_ends(pts_m, widths_m, zs_m, end_ft=END_FT, step_ft=10.0):
    """Insert centreline points every step_ft within end_ft of both ends (linear interpolation of position, width and height) so the end taper / fade is smooth,
    not a few big facets. Returns (pts, widths, zs) as arrays."""
    P = np.array(pts_m, float)
    Wd = np.asarray(widths_m, float)
    Z = np.asarray(zs_m, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = float(cum[-1])
    if total <= 0 or len(P) < 2:
        return P, Wd, Z
    e = min(end_ft * FT, total / 2.0)
    st = step_ft * FT
    extra = list(np.arange(0.0, e, st)) + list(total - np.arange(0.0, e, st))
    s = np.unique(np.round(np.concatenate([cum, extra]), 6))
    return (np.stack([np.interp(s, cum, P[:, 0]), np.interp(s, cum, P[:, 1])], 1), np.interp(s, cum, Wd), np.interp(s, cum, Z))


def build_ribbon(pts_m, widths_m, zs_m, mat, shore_ft=SHORE_FT, rows=ACROSS):
    """River surface: centreline pts_m [(x, y)] (Blender frame, metres, flow = first -> last), full widths, surface heights. Returns a wm.Mesh."""
    P, widths_m, zs_m = densify_ends(pts_m, widths_m, zs_m)
    n = len(P)
    d = np.diff(P, axis=0)
    ln = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    t = d / ln[:, None]
    tv = np.zeros((n, 2))
    tv[0], tv[-1] = t[0], t[-1]
    for i in range(1, n - 1):
        m = t[i - 1] + t[i]
        nm = np.linalg.norm(m)
        tv[i] = m / nm if nm > 1e-9 else t[i]
    nrm = np.stack([-tv[:, 1], tv[:, 0]], 1)                               # left of travel
    cosk = np.ones(n)
    for i in range(1, n - 1):
        cosk[i] = max(float(np.dot(tv[i], t[i])), 0.5)
    cum_m = np.concatenate([[0.0], np.cumsum(ln)])
    ef = end_fade(cum_m / FT)
    hw = np.asarray(widths_m, float) / 2 / cosk * (1.0 - (1.0 - END_NARROW) * ef)          # narrows towards both ends
    zs = np.asarray(zs_m, float)
    # slope along the channel (surface never rises downstream), over a +-SLOPE_BASE window so the stepped surface gives a usable value
    w = SLOPE_BASE_FT * FT
    za = np.interp(np.clip(cum_m - w, 0, cum_m[-1]), cum_m, zs)
    zb = np.interp(np.clip(cum_m + w, 0, cum_m[-1]), cum_m, zs)
    span = np.maximum(np.clip(cum_m + w, 0, cum_m[-1]) - np.clip(cum_m - w, 0, cum_m[-1]), 1e-6)
    slope = np.clip((za - zb) / span / SLOPE_FULL, 0, 1)
    heading = np.degrees(np.arctan2(tv[:, 0], tv[:, 1])) % 360.0           # bearing: x east, y north
    ts = np.linspace(-1.0, 1.0, rows)
    V, UV, SH, SL, HD, EF = [], [], [], [], [], []
    for i in range(n):
        half_ft = float(widths_m[i]) / 2 / FT
        dmax = max(min(shore_ft, half_ft), 1e-3)
        for tt in ts:
            V.append((P[i, 0] + nrm[i, 0] * hw[i] * tt, P[i, 1] + nrm[i, 1] * hw[i] * tt, zs[i]))
            UV.append(((tt + 1) / 2 * (float(widths_m[i]) / FT) / UV_FT, cum_m[i] / FT / UV_FT))
            SH.append((1.0 - abs(tt)) * half_ft / dmax)
            SL.append(slope[i])
            HD.append(heading[i])
            EF.append(ef[i])
    tris = []
    for i in range(n - 1):
        for j in range(rows - 1):
            a, b, c, e = i * rows + j, (i + 1) * rows + j, (i + 1) * rows + j + 1, i * rows + j + 1
            tris += [(a, b, c), (a, c, e)]
    return wm.Mesh(np.array(V), np.array(UV), {mat: np.array(tris)}, smooth=False, X={"_VBWATER": _attr(SH, SL, HD, EF)})


def _edge_distance(Q, ring):
    """Distance of points Q (n,2) to the closed polygon `ring` (m,2) boundary."""
    A = np.asarray(ring, float)
    B = np.roll(A, -1, axis=0)
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    out = np.full(len(Q), np.inf)
    for s in range(0, len(Q), 4096):
        q = Q[s:s + 4096][:, None, :]
        tt = np.clip(((q - A[None]) * AB[None]).sum(2) / L2[None], 0, 1)
        proj = A[None] + tt[..., None] * AB[None]
        out[s:s + 4096] = np.sqrt(((q - proj) ** 2).sum(2)).min(1)
    return out


def build_polygon(P_ft, z_m, mat, height_ft, shore_ft=SHORE_FT, max_edge_ft=None):
    """Lake / pond / sea surface: polygon P_ft [(x, y)] in map feet (y down), flat at z_m. Subdivided so the shore factor has interior vertices."""
    Bp = [(x, height_ft - y) for x, y in P_ft]                                # Blender frame, feet (as build_drape)
    area = abs(sum(Bp[i][0] * Bp[(i + 1) % len(Bp)][1] - Bp[(i + 1) % len(Bp)][0] * Bp[i][1] for i in range(len(Bp)))) / 2
    me = max_edge_ft or max(30.0, math.sqrt(area / 2500.0))
    T = wm.earclip(Bp)
    Q, T = wm.subdivide(Bp, T, me)
    Q = np.array(Q, float)
    dist = _edge_distance(Q, Bp)
    V = np.stack([Q[:, 0] * FT, Q[:, 1] * FT, np.full(len(Q), float(z_m))], 1)
    UV = np.stack([Q[:, 0] / UV_FT, (height_ft - Q[:, 1]) / UV_FT], 1)        # u east, v south (plan y)
    X = _attr(dist / max(shore_ft, 1e-3), np.zeros(len(Q)), np.full(len(Q), 180.0))
    return wm.Mesh(V, UV, {mat: np.array(T)}, smooth=False, X={"_VBWATER": X})


def build(cx, e, settings=None):
    """The mesh and node extras for one water entity: (Mesh, {"vbWater": {...}}). settings = the place's water3d block (None = defaults)."""
    params = wpz.settings_for(e.get("kind"), settings)
    mat = wpz.material_name(params["preset"])
    if e.get("centerline"):
        pts = [cx.B(p[0], p[1]) for p in e["centerline"]]
        zs = [(z - cx.fr.z_origin_ft) * FT for z in e["surface_elevations_ft"]]
        m = build_ribbon(pts, [w * FT for w in e["widths_ft"]], zs, mat)
    else:
        z = (e["level_ft"] - cx.fr.z_origin_ft) * FT
        m = build_polygon([tuple(p[:2]) for p in e["polygon"]], z, mat, cx.fr.height_ft)
    return m, {"vbWater": {"v": 1, "kind": e.get("kind"), **params}}
