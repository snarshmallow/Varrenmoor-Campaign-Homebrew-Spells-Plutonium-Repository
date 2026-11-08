"""Town walls for the 3D world pack: curtain wall segments + towers from world/<place>/walls.json (place_create.make_walls writes it for walled towns).

  python illustrator/generators/worldpack_walls.py inject --place P [--pack DIR]     # write entities/walls.json into an exported pack (like bridge_maker inject)

General and parametric, nothing place specific. walls.json: {"walls": [{id, name, geometry: {points, width_ft}, height_ft}], "gates": [{id, point, width_ft, street}],
"params": {optional overrides of DEFAULTS}}. The wall polylines are already cut at the gates (place_create), so every gate is an OPENING in the data; here each opening gets a
tower on both sides and a lintel (walkway) across the gap. Further towers sit every `tower_spacing_ft` along each segment and at sharp corners.

Entities (type `walls`, layer `walls`):  kind town_wall   {points [[x, y]], width_ft, height_ft}
                                          kind wall_tower  {points [[x, y]], radius_ft, height_ft, gate: bool}
Meshes (build_wall / build_tower, called from worldpack_mesh.build_parts): the wall follows the final terrain (base 1.5 ft below the ground, top = smoothed ground + height,
slope-limited), walkway, parapets with merlons on both sides; towers are 14-sided drums with a corbelled crenellated top and a cone roof (gate towers are larger).
"""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldpack_mesh as wm  # noqa: E402

FT = wm.FT
MAT = "mat_wall_stone"
MAT_TOP = "mat_trim"
DEFAULTS = {"height_ft": 16.0, "thickness_ft": 5.0, "tower_spacing_ft": 140.0, "tower_radius_ft": 9.0, "gate_tower_radius_ft": 11.0, "tower_extra_ft": 8.0,
            "corner_deg": 40.0, "crenels": True, "merlon_ft": 2.5, "merlon_pitch_ft": 5.0, "merlon_h_ft": 3.5, "parapet_t_ft": 1.0, "sample_ft": 6.0, "base_sink_ft": 1.5,
            "max_slope_deg": 30.0, "lintel_ft": 3.0}


def _jload(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _jdump(p, o):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(o, f, indent=1)


def params(over=None):
    P = dict(DEFAULTS)
    P.update({k: v for k, v in (over or {}).items() if v is not None and k in DEFAULTS})
    return P


# ------------------------------------------------------------------ data
def _resample(pts, step):
    pts = np.asarray(pts, float)[:, :2]
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    n = max(2, int(math.ceil(s[-1] / step)) + 1)
    u = np.linspace(0.0, s[-1], n)
    return np.stack([np.interp(u, s, pts[:, 0]), np.interp(u, s, pts[:, 1])], 1), u


def plan_towers(wall_id, pts, P, gates=()):
    """Tower positions for one wall segment: both ends when a gate point is within `gate width + 12 ft` of the end (gate towers), every `tower_spacing_ft` along it
    and at corners sharper than `corner_deg`. -> [{x, y, gate}]"""
    pts = np.asarray(pts, float)[:, :2]
    s = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(pts, axis=0).T))])
    out = []
    for end in (0, -1):
        e = pts[end]
        for g in gates:
            if math.hypot(e[0] - g["point"][0], e[1] - g["point"][1]) <= g.get("width_ft", 16.0) / 2 + 12.0:
                out.append({"x": float(e[0]), "y": float(e[1]), "gate": True, "s": float(s[end])})
                break
    L = float(s[-1])
    gate_s = [t["s"] for t in out]
    sp = max(40.0, P["tower_spacing_ft"])
    n = int(L // sp)
    for k in range(1, n + 1):
        d = k * L / (n + 1)
        if any(abs(d - g) < sp * 0.4 for g in gate_s):
            continue
        out.append({"x": float(np.interp(d, s, pts[:, 0])), "y": float(np.interp(d, s, pts[:, 1])), "gate": False, "s": d})
    for k in range(1, len(pts) - 1):
        a, b, c = pts[k - 1], pts[k], pts[k + 1]
        v1, v2 = b - a, c - b
        ang = math.degrees(abs(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], float(v1 @ v2))))
        if ang > P["corner_deg"] and all(abs(s[k] - t["s"]) > 20.0 for t in out):
            out.append({"x": float(b[0]), "y": float(b[1]), "gate": False, "s": float(s[k])})
    return sorted(out, key=lambda t: t["s"])


def wall_entities(doc, over=None, ground=None):
    """The `walls` entity items for a walls.json document. ground(x, y) -> elevation ft for the stored z (optional)."""
    P = params({**(doc.get("params") or {}), **(over or {})})
    gates = doc.get("gates") or []
    items = []
    z = (lambda x, y: round(float(ground(x, y)), 3)) if ground else (lambda x, y: 0.0)
    for w in doc.get("walls", []):
        g = w["geometry"]
        pts = [p[:2] for p in g["points"]]
        if len(pts) < 2:
            continue
        hgt = float(w.get("height_ft") or P["height_ft"])
        th = float(g.get("width_ft") or P["thickness_ft"])
        tags = {"layer": "walls", "subtype": "town_wall", "district": None, "ring": None, "group": "walls", "id": w["id"]}
        items.append({"id": w["id"], "name": w.get("name", "Town wall"), "kind": "town_wall", "status": w.get("status", "proposed"), "notes": "", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
                      "source": "walls.json", "points": [[round(x, 2), round(y, 2), z(x, y)] for x, y in pts], "width_ft": th, "height_ft": hgt,
                      "params": {k: P[k] for k in ("crenels", "merlon_ft", "merlon_pitch_ft", "merlon_h_ft", "parapet_t_ft", "base_sink_ft")},
                      "tags": tags, "foundry": {"pipelineId": f"world:{doc.get('place', 'place')}:{w['id']}"}})
        for k, t in enumerate(plan_towers(w["id"], pts, P, gates)):
            tid = f"{w['id']}_tower_{k + 1:02d}"
            r = P["gate_tower_radius_ft"] if t["gate"] else P["tower_radius_ft"]
            tg = {"layer": "walls", "subtype": "wall_tower", "district": None, "ring": None, "group": "walls", "id": tid}
            items.append({"id": tid, "name": "Gate tower" if t["gate"] else "Wall tower", "kind": "wall_tower", "status": "proposed", "notes": "", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
                          "source": "walls.json", "points": [[round(t["x"], 2), round(t["y"], 2), z(t["x"], t["y"])]], "radius_ft": r, "height_ft": hgt + P["tower_extra_ft"] * (1.4 if t["gate"] else 1.0),
                          "gate": bool(t["gate"]), "wall": w["id"], "tags": tg, "foundry": {"pipelineId": f"world:{doc.get('place', 'place')}:{tid}"}})
    # gate lintels: a walkway across every opening between the two wall ends nearest the gate
    for g in gates:
        ends = []
        for w in doc.get("walls", []):
            pts = w["geometry"]["points"]
            for e in (pts[0], pts[-1]):
                d = math.hypot(e[0] - g["point"][0], e[1] - g["point"][1])
                if d <= g.get("width_ft", 16.0) / 2 + 12.0:
                    ends.append((d, e))
        ends.sort(key=lambda t: t[0])
        if len(ends) >= 2 and math.hypot(ends[0][1][0] - ends[1][1][0], ends[0][1][1] - ends[1][1][1]) > 4.0:
            a, b = ends[0][1], ends[1][1]
            hgt = float((doc["walls"][0].get("height_ft")) or P["height_ft"])
            tg = {"layer": "walls", "subtype": "gate_lintel", "district": None, "ring": None, "group": "walls", "id": f"{g['id']}_lintel"}
            items.append({"id": f"{g['id']}_lintel", "name": f"{g.get('name', 'Gate')} lintel", "kind": "gate_lintel", "status": "proposed", "notes": "", "links": {"foundry_scene": None, "model3d": None, "ai_layer": None},
                          "source": "walls.json", "points": [[round(a[0], 2), round(a[1], 2), z(*a[:2])], [round(b[0], 2), round(b[1], 2), z(*b[:2])]], "width_ft": P["thickness_ft"], "height_ft": hgt,
                          "clear_ft": max(12.0, hgt - P["lintel_ft"] - 1.0), "gate": g["id"], "tags": tg, "foundry": {"pipelineId": f"world:{doc.get('place', 'place')}:{g['id']}_lintel"}})
    return items


# ------------------------------------------------------------------ meshes
def _away(b, mat, pts, inside, tile=8.0):
    """Emit a planar polygon with its normal pointing away from the point `inside` (a point inside the solid it bounds)."""
    P = np.asarray(pts, float)
    n = np.zeros(3)
    for k in range(1, len(P) - 1):
        n += np.cross(P[k] - P[0], P[k + 1] - P[0])
    if float(n @ (P[0] - np.asarray(inside, float))) < 0:
        P = P[::-1]
    pts = [tuple(p) for p in P]
    b.face(mat, pts, wm.world_uv(pts, tile, (0.0, 0.0), 0.0))


def _ground_profile(cx, xy, P):
    g = np.array([cx.ground_m(x, y) for x, y in xy])
    return g


def _smooth(z, window):
    if len(z) < 3:
        return z
    k = max(1, int(window))
    pad = np.pad(z, k, mode="edge")
    return np.convolve(pad, np.ones(2 * k + 1) / (2 * k + 1), mode="valid")


def build_wall(cx, e):
    """Curtain wall segment with walkway, parapets and merlons. Blender frame (metres), world UVs at 8 ft per texture repeat."""
    P = params(e.get("params"))
    b = wm.Builder()
    xy, s_ft = _resample([p[:2] for p in e["points"]], P["sample_ft"])
    hgt = float(e.get("height_ft", P["height_ft"])) * FT
    half = float(e.get("width_ft", P["thickness_ft"])) * FT / 2.0
    pt = P["parapet_t_ft"] * FT
    mh = P["merlon_h_ft"] * FT
    sink = P["base_sink_ft"] * FT
    BP = np.array([cx.B(x, y)[:2] for x, y in xy])
    G = _ground_profile(cx, xy, P)
    tan = math.tan(math.radians(P["max_slope_deg"]))
    top = _smooth(G, 4) + hgt                                            # smoothed ground + height, so the wall top does not copy every bump
    top = np.maximum(top, G + hgt * 0.6)
    ds = np.maximum(np.diff(s_ft) * FT, 1e-6)
    for i in range(1, len(top)):                                         # slope limit forward / backward (raise only)
        top[i] = max(top[i], top[i - 1] - tan * ds[i - 1])
    for i in range(len(top) - 2, -1, -1):
        top[i] = max(top[i], top[i + 1] - tan * ds[i])
    d = np.gradient(BP, axis=0)
    d /= np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9)
    nrm = np.stack([-d[:, 1], d[:, 0]], 1)
    Lp, Rp = BP + nrm * half, BP - nrm * half
    uv = lambda pts: wm.world_uv(pts, 8.0, (0.0, 0.0), 0.0)

    def face(mat, pts):
        b.face(mat, pts, uv(pts))
    for i in range(len(BP) - 1):
        j = i + 1
        ctr = ((BP[i][0] + BP[j][0]) / 2, (BP[i][1] + BP[j][1]) / 2, (G[i] + top[i]) / 2)
        for S_ in (Lp, Rp):
            a_, c_ = S_[i], S_[j]
            _away(b, MAT, [(a_[0], a_[1], G[i] - sink), (c_[0], c_[1], G[j] - sink), (c_[0], c_[1], top[j]), (a_[0], a_[1], top[i])], ctr)
        _away(b, MAT_TOP, [(Lp[i][0], Lp[i][1], top[i]), (Lp[j][0], Lp[j][1], top[j]), (Rp[j][0], Rp[j][1], top[j]), (Rp[i][0], Rp[i][1], top[i])], ctr)
    for i, ee in ((0, 0), (len(BP) - 1, 1)):                                  # end caps
        a_, c_ = Lp[i], Rp[i]
        ctr = (BP[i][0] - d[i][0] * (1 if ee == 0 else -1), BP[i][1] - d[i][1] * (1 if ee == 0 else -1), (G[i] + top[i]) / 2)
        _away(b, MAT, [(a_[0], a_[1], G[i] - sink), (c_[0], c_[1], G[i] - sink), (c_[0], c_[1], top[i]), (a_[0], a_[1], top[i])],
              (BP[i][0] + d[i][0] * (1 if ee == 0 else -1), BP[i][1] + d[i][1] * (1 if ee == 0 else -1), (G[i] + top[i]) / 2))
    if P["crenels"]:
        pitch = P["merlon_pitch_ft"] * FT
        wid = P["merlon_ft"] * FT
        total = s_ft[-1] * FT
        n = int(total // pitch)
        for k in range(n):
            sc = (k + 0.5) * pitch
            sf = sc / FT
            i = int(np.searchsorted(s_ft, sf, side="right") - 1)
            i = min(max(i, 0), len(BP) - 2)
            t = (sf - s_ft[i]) / max(s_ft[i + 1] - s_ft[i], 1e-9)
            c = BP[i] * (1 - t) + BP[i + 1] * t
            zt = top[i] * (1 - t) + top[i + 1] * t
            tdir = d[i]
            nn = nrm[i]
            for sgn in (1, -1):
                o = c + nn * sgn * (half - pt / 2)
                _merlon(b, o, tdir, nn, wid, pt, zt, mh)
    return b.build()


def _merlon(b, c, t, n, w, th, z0, h):
    """A box merlon: centre c (xy), tangent t, normal n, width w (along t), thickness th (along n), from z0 up by h. Five faces (no bottom), normals outward."""
    def corner(a, bb, z):
        return (c[0] + t[0] * a * w / 2 + n[0] * bb * th / 2, c[1] + t[1] * a * w / 2 + n[1] * bb * th / 2, z)
    z1 = z0 + h
    q = lambda *ks: [corner(a, bb, z) for a, bb, z in ks]
    ins = (c[0], c[1], z0 + h / 2)
    for pts in (q((-1, -1, z0), (1, -1, z0), (1, -1, z1), (-1, -1, z1)), q((1, 1, z0), (-1, 1, z0), (-1, 1, z1), (1, 1, z1)),
                q((-1, 1, z0), (-1, -1, z0), (-1, -1, z1), (-1, 1, z1)), q((1, -1, z0), (1, 1, z0), (1, 1, z1), (1, -1, z1)),
                q((-1, -1, z1), (1, -1, z1), (1, 1, z1), (-1, 1, z1))):
        _away(b, MAT, pts, ins)


def build_tower(cx, e):
    """Round tower: 14-sided drum from 1.5 ft below the ground, a corbelled top ring, crenellated parapet (every other facet) and a cone roof."""
    P = params(e.get("params"))
    b = wm.Builder()
    x, y = e["points"][0][:2]
    r = float(e["radius_ft"]) * FT
    n = 14
    gz = cx.ground_m(x, y)
    gmin = min(cx.ground_m(x + r / FT * math.cos(a), y + r / FT * math.sin(a)) for a in np.linspace(0, 2 * math.pi, 8, endpoint=False))
    z0 = min(gz, gmin) - P["base_sink_ft"] * FT
    z1 = gz + float(e["height_ft"]) * FT
    cb = cx.B(x, y)
    ring = lambda rad, z: [(cb[0] + rad * math.cos(2 * math.pi * k / n), cb[1] + rad * math.sin(2 * math.pi * k / n), z) for k in range(n)]
    axis = lambda z: (cb[0], cb[1], z)
    lo, hi = ring(r, z0), ring(r, z1 - 1.5 * FT)
    for k in range(n):
        j = (k + 1) % n
        _away(b, MAT, [lo[k], lo[j], hi[j], hi[k]], axis((z0 + z1) / 2))
    rc = r + 0.9 * FT
    c0, c1 = ring(r, z1 - 1.5 * FT), ring(rc, z1)
    for k in range(n):
        j = (k + 1) % n
        _away(b, MAT, [c0[k], c0[j], c1[j], c1[k]], axis(z1 - 2.5 * FT))
    rp = rc - 0.9 * FT
    mh = P["merlon_h_ft"] * FT
    top_o, top_i = ring(rc, z1), ring(rp, z1)
    for k in range(n):
        j = (k + 1) % n
        _away(b, MAT_TOP, [top_o[k], top_o[j], top_i[j], top_i[k]], axis(z1 - 1.0))                 # walkway
        if k % 2 == 0:                                                                                # a merlon facet: outer, inner, top
            po, pi_ = ring(rc, z1 + mh), ring(rp, z1 + mh)
            ins = axis(z1 + mh / 2)
            ins = (cb[0] + (rc + rp) / 2 * math.cos(2 * math.pi * (k + 0.5) / n), cb[1] + (rc + rp) / 2 * math.sin(2 * math.pi * (k + 0.5) / n), z1 + mh / 2)
            _away(b, MAT, [top_o[k], top_o[j], po[j], po[k]], ins)
            _away(b, MAT, [top_i[k], top_i[j], pi_[j], pi_[k]], ins)
            _away(b, MAT, [po[k], po[j], pi_[j], pi_[k]], ins)
            for kk, side in ((k, 0), (j, 1)):                                                           # the two ends of the merlon
                _away(b, MAT, [top_o[kk], top_i[kk], pi_[kk], po[kk]], ins)
    rr = rp * 0.95
    base = ring(rr, z1 + 0.1 * FT)
    apex = (cb[0], cb[1], z1 + 0.1 * FT + rr * 1.4)
    for k in range(n):
        j = (k + 1) % n
        _away(b, MAT_TOP, [base[k], base[j], apex], axis(z1 + 0.1 * FT + 0.2))
    return b.build()


def build_lintel(cx, e):
    """Walkway across a gate opening: a box between the two wall ends, from `clear_ft` above the ground up to the wall top (arched underside is not modelled)."""
    P = params(e.get("params"))
    b = wm.Builder()
    (ax, ay), (bx, by) = e["points"][0][:2], e["points"][1][:2]
    A, B_ = np.array(cx.B(ax, ay)[:2]), np.array(cx.B(bx, by)[:2])
    d = (B_ - A) / max(np.linalg.norm(B_ - A), 1e-9)
    nrm = np.array([-d[1], d[0]])
    half = e.get("width_ft", P["thickness_ft"]) * FT / 2
    gz = min(cx.ground_m(ax, ay), cx.ground_m(bx, by))
    zb = gz + e["clear_ft"] * FT
    zt = gz + e["height_ft"] * FT
    c = [A + nrm * half, B_ + nrm * half, B_ - nrm * half, A - nrm * half]
    mid = ((A + B_) / 2)
    ins = (mid[0], mid[1], (zb + zt) / 2)
    for k in range(4):
        a_, c_ = c[k], c[(k + 1) % 4]
        _away(b, MAT, [(a_[0], a_[1], zb), (c_[0], c_[1], zb), (c_[0], c_[1], zt), (a_[0], a_[1], zt)], ins)
    _away(b, MAT_TOP, [(c[k][0], c[k][1], zt) for k in range(4)], ins)
    _away(b, MAT, [(c[k][0], c[k][1], zb) for k in range(4)], ins)
    return b.build()


# ------------------------------------------------------------------ pack injection
def inject(pack_dir, place, world_root=None, doc=None, over=None):
    """Write world/<place>/walls.json into an exported pack as entities/walls.json (+ manifest entry). No-op when the place has no walls.json."""
    import worldpack as wp
    root = world_root or wp.REPO + "/world"
    path = os.path.join(root, place, "walls.json")
    if doc is None:
        if not os.path.exists(path):
            return {"walls": 0, "towers": 0}
        doc = _jload(path)
    doc.setdefault("place", place)
    pack = wp.load_pack(pack_dir)
    items = wall_entities(doc, over, ground=lambda x, y: wp.bilinear(pack.heights, pack.cell_ft, x, y))
    ent_dir = os.path.join(pack_dir, "entities")
    mp = os.path.join(pack_dir, "manifest.json")
    man = _jload(mp)
    fn = os.path.join(ent_dir, "walls.json")
    roads = _jload(os.path.join(ent_dir, "roads.json"))
    _jdump(fn, {"format": roads.get("format"), "schema_version": roads.get("schema_version"), "type": "walls", "units": roads.get("units", "feet"), "items": items})
    rel = "entities/walls.json"
    with open(fn, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    man.setdefault("entities", {})["walls"] = {"file": rel, "count": len(items), "sha256": sha}
    man.setdefault("files", {})[rel] = "pending"
    _jdump(mp, man)
    wp.refresh_manifest_files(pack_dir)
    return {"walls": sum(1 for i in items if i["kind"] == "town_wall"), "towers": sum(1 for i in items if i["kind"] == "wall_tower"), "lintels": sum(1 for i in items if i["kind"] == "gate_lintel")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["inject"])
    ap.add_argument("--place", required=True)
    ap.add_argument("--pack")
    a = ap.parse_args(argv)
    import worldpack as wp
    pack = a.pack or os.path.join(wp.REPO, "world", a.place, "export")
    print(json.dumps(inject(pack, a.place), indent=1))


if __name__ == "__main__":
    main()
