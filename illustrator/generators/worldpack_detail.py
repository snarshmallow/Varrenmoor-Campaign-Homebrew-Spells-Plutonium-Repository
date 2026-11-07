"""Detailed building meshes for world packs: walls of real thickness, door and window openings with reveals, trim frames, glass, a floor, and door leaves
as separate movable glTF nodes (origin on the hinge, extras isDoor / doorId / doorStyle / doorAnimateAngle as in foundry-3d/README.md).

Used by worldpack_mesh.build_parts for buildings whose pack entity carries `openings` (worldpack.export_world adds them when the place has a
details.json, i.e. region children: door positions come from the region detail pass). Windows are derived here: one per ~8 ft of free wall on every
storey, 3 x 3.5 ft, sill 3.5 ft. Not a floor plan: there are no interior rooms behind the door, only the one hollow shell (floor + open rafters).
"""
import math

import numpy as np

import worldpack_mesh as wm
from worldpack_pbr import tile_ft as pbr_tile

FT = wm.FT
Builder, Mesh = wm.Builder, wm.Mesh
WALL_T_FT = 0.75
DOOR_H_FT, DOOR_W_FT = 7.0, 3.5
WIN_W_FT, WIN_H_FT, WIN_SILL_FT, WIN_SPACING_FT = 3.0, 3.5, 3.5, 8.0
TRIM_W_FT, TRIM_OUT_FT = 0.4, 0.15
LEAF_T_FT = 0.15
END_MARGIN_FT = 1.5
DETAIL_MATS = {"mat_door_wood": ("#6b4a2b", 0.8, None), "mat_trim": ("#d8d0bc", 0.8, None), "mat_glass": ("#9fc4d6", 0.2, 0.45),
               "mat_plaster": ("#cbbfa6", 0.95, None), "mat_interior_floor": ("#7a5f40", 0.9, None), "mat_iron": ("#3a3a3d", 0.6, None)}


def door_hits(P, openings, cx):
    """Door points (feet) -> {edge index: [(u_m, width_m, door dict)]} for the CCW Blender-frame polygon P (nearest edge within 0.6 m)."""
    out = {}
    for d in (openings or {}).get("doors", []):
        pb = cx.B(d["point"][0], d["point"][1])
        best = None
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            L = math.dist(a, b)
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            u = (pb[0] - a[0]) * ux + (pb[1] - a[1]) * uy
            v = -(pb[0] - a[0]) * uy + (pb[1] - a[1]) * ux
            if -0.2 <= u <= L + 0.2 and (best is None or abs(v) < best[0]):
                best = (abs(v), i, u)
        if best and best[0] < 0.6:
            out.setdefault(best[1], []).append((best[2], min(float(d.get("width_ft", DOOR_W_FT)), 6.0) * FT, d))
    return out


def wall_geometry(P):
    """CCW polygon P -> (edge directions, inward normals, inner polygon Q at wall thickness, mitred)."""
    n = len(P)
    t = WALL_T_FT * FT
    D, N = [], []
    for i in range(n):
        a, c = P[i], P[(i + 1) % n]
        L = math.dist(a, c)
        d = ((c[0] - a[0]) / L, (c[1] - a[1]) / L)
        D.append(d)
        N.append((-d[1], d[0]))
    Q = []
    for i in range(n):
        n0, n1 = N[i - 1], N[i]
        k = t / (1.0 + n0[0] * n1[0] + n0[1] * n1[1])
        Q.append((P[i][0] + k * (n0[0] + n1[0]), P[i][1] + k * (n0[1] + n1[1])))
    return D, N, Q


def plan_holes(P, doors, storeys, zf):
    """Per edge: sorted list of holes {u0,u1,z0,z1,kind[,door]} (u along the edge in metres from P[i]). Doors first, windows in the free wall."""
    n = len(P)
    out = []
    for i in range(n):
        L = math.dist(P[i], P[(i + 1) % n])
        holes = []
        for (u, w, d) in doors.get(i, []):
            u = min(max(u, w / 2 + END_MARGIN_FT * FT), L - w / 2 - END_MARGIN_FT * FT)
            holes.append({"u0": u - w / 2, "u1": u + w / 2, "z0": zf, "z1": zf + DOOR_H_FT * FT, "kind": "door", "door": d})
        free = [(END_MARGIN_FT * FT, L - END_MARGIN_FT * FT)]
        for h in sorted(holes, key=lambda h: h["u0"]):
            nf = []
            for lo, hi in free:
                for seg in ((lo, min(hi, h["u0"] - END_MARGIN_FT * FT)), (max(lo, h["u1"] + END_MARGIN_FT * FT), hi)):
                    if seg[1] - seg[0] > 0:
                        nf.append(seg)
            free = nf
        for lo, hi in free:
            span = hi - lo
            cnt = int(span / (WIN_SPACING_FT * FT))
            for k in range(cnt):
                uc = lo + span * (k + 0.5) / cnt
                for s in range(storeys):
                    zs = zf + (s * 10.0 + WIN_SILL_FT) * FT
                    holes.append({"u0": uc - WIN_W_FT * FT / 2, "u1": uc + WIN_W_FT * FT / 2, "z0": zs, "z1": zs + WIN_H_FT * FT, "kind": "window"})
        out.append(sorted(holes, key=lambda h: (h["u0"], h["z0"])))
    return out


def build_building_detailed(cx, e):
    """-> (Mesh, [door node dicts {id, hinge, mesh (hinge-local, Blender axes), extras}])."""
    b = Builder()
    t = WALL_T_FT * FT
    zf = (e["base_elevation_ft"] - cx.fr.z_origin_ft) * FT
    z0 = zf - e["skirt_depth_ft"] * FT
    zt = zf + e["wall_height_ft"] * FT
    P = [cx.B(p[0], p[1]) for p in e["polygon"]]
    if sum(P[i][0] * P[(i + 1) % len(P)][1] - P[(i + 1) % len(P)][0] * P[i][1] for i in range(len(P))) < 0:
        P.reverse()
    n = len(P)
    wmat = e["wall"]["surface"]["material"]
    wt = pbr_tile(wmat, e["wall"]["surface"]["tile_ft"])
    D, N, Q = wall_geometry(P)
    storeys = max(1, int(e.get("floors", 1)))
    edge_holes = plan_holes(P, door_hits(P, e.get("openings"), cx), storeys, zf)
    door_nodes = []

    def X(i, u, v, z):
        return (P[i][0] + D[i][0] * u + N[i][0] * v, P[i][1] + D[i][1] * u + N[i][1] * v, z)

    import worldpack_pbr as pbr
    uvo = wm.uv_offset(e["id"])

    def face(mat, pts):                  # world-scale UVs (worldpack_mesh.world_uv): level courses, constant texel density, rails on the floor line
        b.face(mat, pts, wm.world_uv(pts, wt if mat == wmat else pbr.tile_ft(mat, wt), uvo, zf))

    def rect(i, mat, v, u0, u1, zb, zc):
        if u1 - u0 > 1e-6 and zc - zb > 1e-6:
            face(mat, [X(i, u0, v, zb), X(i, u1, v, zb), X(i, u1, v, zc), X(i, u0, v, zc)])

    def box(i, mat, u0, u1, v0, v1, za, zb_, skip=()):
        c = lambda u, v, z: X(i, u, v, z)
        faces = {"v0": [c(u0, v0, za), c(u1, v0, za), c(u1, v0, zb_), c(u0, v0, zb_)], "v1": [c(u0, v1, za), c(u1, v1, za), c(u1, v1, zb_), c(u0, v1, zb_)],
                 "u0": [c(u0, v0, za), c(u0, v1, za), c(u0, v1, zb_), c(u0, v0, zb_)], "u1": [c(u1, v0, za), c(u1, v1, za), c(u1, v1, zb_), c(u1, v0, zb_)],
                 "z0": [c(u0, v0, za), c(u1, v0, za), c(u1, v1, za), c(u0, v1, za)], "z1": [c(u0, v0, zb_), c(u1, v0, zb_), c(u1, v1, zb_), c(u0, v1, zb_)]}
        for k, pts in faces.items():
            if k not in skip:
                face(mat, pts)

    for i in range(n):
        L = math.dist(P[i], P[(i + 1) % n])
        j = (i + 1) % n
        ua = (Q[i][0] - P[i][0]) * D[i][0] + (Q[i][1] - P[i][1]) * D[i][1]
        ub = (Q[j][0] - P[i][0]) * D[i][0] + (Q[j][1] - P[i][1]) * D[i][1]
        holes = edge_holes[i]
        cols = {}
        for h in holes:
            cols.setdefault((round(h["u0"], 6), round(h["u1"], 6)), []).append(h)
        keys = sorted(cols)
        for v, lo_u, hi_u, zb, mat in ((0.0, 0.0, L, z0, wmat), (t, ua, ub, zf, "mat_plaster")):
            cur = lo_u
            for (u0, u1) in keys:
                rect(i, mat, v, cur, u0, zb, zt)
                z = zb
                for h in sorted(cols[(u0, u1)], key=lambda h: h["z0"]):
                    rect(i, mat, v, u0, u1, z, h["z0"])
                    z = h["z1"]
                rect(i, mat, v, u0, u1, z, zt)
                cur = u1
            rect(i, mat, v, cur, hi_u, zb, zt)
        tw, to = TRIM_W_FT * FT, TRIM_OUT_FT * FT
        for h in holes:
            u0, u1, za, zb_ = h["u0"], h["u1"], h["z0"], h["z1"]
            if h["kind"] == "window":
                face("mat_plaster", [X(i, u0, 0, za), X(i, u1, 0, za), X(i, u1, t, za), X(i, u0, t, za)])
            face("mat_plaster", [X(i, u0, 0, zb_), X(i, u1, 0, zb_), X(i, u1, t, zb_), X(i, u0, t, zb_)])
            face("mat_plaster", [X(i, u0, 0, za), X(i, u0, t, za), X(i, u0, t, zb_), X(i, u0, 0, zb_)])
            face("mat_plaster", [X(i, u1, 0, za), X(i, u1, t, za), X(i, u1, t, zb_), X(i, u1, 0, zb_)])
            # trim frame stands proud of the wall (its wall-side face is omitted: no coplanar overlap)
            box(i, "mat_trim", u0 - tw, u0, -to, 0, za, zb_ + tw, skip=("v1",))
            box(i, "mat_trim", u1, u1 + tw, -to, 0, za, zb_ + tw, skip=("v1",))
            box(i, "mat_trim", u0, u1, -to, 0, zb_, zb_ + tw, skip=("v1",))
            if h["kind"] == "window":
                box(i, "mat_trim", u0 - tw, u1 + tw, -2 * to, 0, za - tw, za, skip=("v1",))
                pm, zm = (u0 + u1) / 2, (za + zb_) / 2
                face("mat_glass", [X(i, u0, t / 2, za), X(i, u1, t / 2, za), X(i, u1, t / 2, zb_), X(i, u0, t / 2, zb_)])
                box(i, "mat_trim", pm - 0.02, pm + 0.02, t / 2 - 0.03, t / 2 + 0.03, za, zb_)
                box(i, "mat_trim", u0, u1, t / 2 - 0.03, t / 2 + 0.03, zm - 0.02, zm + 0.02)
            else:
                lw, lh, lt = (u1 - u0) - 0.04, (zb_ - za) - 0.04, LEAF_T_FT * FT
                lb = Builder()
                for pts in ([(0, -lt / 2, 0), (lw, -lt / 2, 0), (lw, -lt / 2, lh), (0, -lt / 2, lh)], [(0, lt / 2, 0), (lw, lt / 2, 0), (lw, lt / 2, lh), (0, lt / 2, lh)],
                            [(0, -lt / 2, 0), (0, lt / 2, 0), (0, lt / 2, lh), (0, -lt / 2, lh)], [(lw, -lt / 2, 0), (lw, lt / 2, 0), (lw, lt / 2, lh), (lw, -lt / 2, lh)],
                            [(0, -lt / 2, lh), (lw, -lt / 2, lh), (lw, lt / 2, lh), (0, lt / 2, lh)]):
                    lb.face("mat_door_wood", pts, [(p[0] / FT / 4, -p[2] / FT / 4) for p in pts])
                for sgn in (-1, 1):
                    y = sgn * (lt / 2 + 0.01)
                    hz = lh * 0.45
                    lb.face("mat_door_wood", [(lw - 0.15, y, hz), (lw - 0.05, y, hz), (lw - 0.05, y, hz + 0.05), (lw - 0.15, y, hz + 0.05)], [(0, 0)] * 4)
                M = lb.build()
                V = M.V
                Vb = np.stack([V[:, 0] * D[i][0] + V[:, 1] * N[i][0], V[:, 0] * D[i][1] + V[:, 1] * N[i][1], V[:, 2]], 1)
                hx, hy, hz = X(i, u0 + 0.02, t / 2, za + 0.02)
                did = h["door"].get("id") or f"{e['id']}_door"
                door_nodes.append({"id": did, "hinge": (hx, hy, hz), "mesh": Mesh(Vb, M.UV, M.subs),
                                   "extras": {"isDoor": True, "doorId": did, "doorStyle": 1, "doorAnimateAngle": 90, "building": e["id"]}})
    for i in range(n):          # top of the wall ring and the interior floor
        j = (i + 1) % n
        face(wmat, [(P[i][0], P[i][1], zt), (P[j][0], P[j][1], zt), (Q[j][0], Q[j][1], zt), (Q[i][0], Q[i][1], zt)])
    cap = [b.vert((q[0], q[1], zf + 0.02), (q[0] / FT / 4, -q[1] / FT / 4)) for q in Q]
    for tri in wm.earclip(Q):
        b.tri("mat_interior_floor", *[cap[k] for k in tri])
    # roof and gables come from the single-skin builder (keep only what is above the wall top)
    base = wm.build_building(cx, e)
    keep = base.V[:, 2] >= zt - 1e-6
    subs = {}
    for k, F in base.subs.items():
        sel = F if k == e["roof"]["surface"]["material"] else F[np.all(keep[F], axis=1)]
        if len(sel):
            subs[k] = sel
    return wm.merge_meshes([b.build(), Mesh(base.V, base.UV, subs, False)]), door_nodes
