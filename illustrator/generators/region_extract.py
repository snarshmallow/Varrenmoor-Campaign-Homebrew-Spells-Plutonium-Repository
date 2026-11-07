"""Region / district extraction: a 'zoom-in child map' of a parent place (see illustrator/REGIONS.md).

  python illustrator/generators/region_extract.py extract --parent bridgehollow (--district dis_authority | --entity ID | --rect x0,y0,x1,y1
        | --polygon "x,y;x,y;..." | --polygon-file pts.json) [--name "Authority ward"] [--margin 40] [--terrain-cell 2.5] [--seed N]
        [--scale 20 --grid 5] [--detail doors,roofs,chimneys,lots,fences,kerbs,trees|all|none] [--clip-buildings] [--local-origin]
        [--sandbox] [--child-id ID] [--out-root DIR] [--no-terrain] [--force]
  python region_extract.py list [--parent P]               child regions of a parent (world/*/region.json)
  python region_extract.py refresh --child ID [--apply-edits keep]   re-extract from the parent, keeping the child's hand edits
  python region_extract.py sync --child ID [--apply]       diff of shared attributes child -> parent (written only with --apply)
  python region_extract.py preview --parent P (region flags) --out region.svg   region outline as an SVG path (REGIONS layer)

Every command prints log lines and ONE final JSON line on stdout.

Model of a child (world/<parent>__<region>/): same json layout as any place (place.json, districts.json, streets.json, water.json, buildings/,
terrain/, view_settings.json) plus region.json (provenance + transform + id map + snapshot hashes), details.json (generated, NOT canon),
markers.json (continues-off-map arrows, region outline). Foot coordinates and entity ids are the parent's (child = parent - origin_ft, origin
0,0 unless --local-origin). Zoom is the view scale only. Terrain is cropped to the region + margin and up-resolved (heightmap meta carries
origin_ft; worldio pads the crop back to full coordinates for every consumer).
"""
import argparse
import datetime
import glob
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys

import numpy as np
from scipy import ndimage as ndi
from scipy.interpolate import RectBivariateSpline
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box
from shapely.ops import unary_union

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import worldio  # noqa: E402

REPO = worldio.REPO
WORLD = os.path.join(REPO, "world")
SANDBOX = "_region_test"
SCHEMA = 1
DETAIL_KINDS = ("doors", "roofs", "chimneys", "lots", "fences", "kerbs", "trees")
LOG = lambda m: print(m, flush=True)  # noqa: E731


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", str(s).lower()).strip("_") or "region"


def _rj(path, dflt=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return dflt


def _wj(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
        f.write("\n")


def ehash(e):
    return hashlib.sha1(json.dumps(e, sort_keys=True).encode()).hexdigest()[:12]


# ------------------------------------------------------------------ parent model
def load_parent(parent, root=None):
    """Parent model in the render_world shape (+ raw dir). Water follows worldio (world file unless the panel's working copy is on)."""
    import render_world as rw
    pdir = worldio.world_dir(parent, root)
    if not os.path.exists(os.path.join(pdir, "place.json")):
        raise SystemExit(f"parent place not found: {pdir}")
    if not root:
        return rw.load_place(parent)
    m = {"place": _rj(os.path.join(pdir, "place.json")), "districts": _rj(os.path.join(pdir, "districts.json"))["districts"],
         "streets": _rj(os.path.join(pdir, "streets.json"))["streets"], "water": _rj(os.path.join(pdir, "water.json"), {"water": []})["water"],
         "buildings": [_rj(f) for f in sorted(glob.glob(os.path.join(pdir, "buildings", "*.json")))]}
    return m


def parent_fingerprint(parent, root=None):
    """git commit of the repo + a content hash of the parent model files (what the child was extracted from)."""
    pdir = worldio.world_dir(parent, root)
    h = hashlib.sha1()
    for f in ["place.json", "districts.json", "streets.json", "water.json"] + sorted(
            os.path.relpath(p, pdir).replace("\\", "/") for p in glob.glob(os.path.join(pdir, "buildings", "*.json"))):
        p = os.path.join(pdir, f)
        if os.path.exists(p):
            h.update(f.encode())
            h.update(open(p, "rb").read())
    for f in ("heightmap.npy", "heightmap_patched.npy"):
        p = os.path.join(pdir, "terrain", f)
        if os.path.exists(p):
            h.update(f.encode())
            h.update(open(p, "rb").read())
    commit, dirty = None, None
    try:
        if os.path.splitdrive(pdir)[0].lower() != os.path.splitdrive(REPO)[0].lower() or not os.path.abspath(pdir).startswith(REPO):
            raise OSError("parent outside the repo")
        commit = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True, timeout=20).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "-C", REPO, "status", "--porcelain", "--", os.path.relpath(pdir, REPO)], capture_output=True,
                                    text=True, timeout=20).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return {"git_commit": commit, "parent_dirty": dirty, "content_sha1": h.hexdigest()}


# ------------------------------------------------------------------ region geometry
def _poly(pts):
    g = Polygon([tuple(p) for p in pts]).buffer(0)
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda x: x.area)
    return g


def entity_points(e):
    g = e["geometry"]
    if g["type"] == "polyline":
        return LineString(g["points"]).buffer(g["width_ft"] / 2).exterior.coords[:-1]
    return g["points"]


def resolve_region(model, spec):
    """spec: {"kind": "entity", "id"} | {"kind": "rect", "rect": [x0,y0,x1,y1]} | {"kind": "polygon", "points": [[x,y],..], "source": str}
    -> (shapely Polygon, normalized spec dict with the polygon points and a default name)."""
    k = spec.get("kind")
    name = spec.get("name")
    if k == "entity":
        eid = spec["id"]
        for coll in ("districts", "buildings", "water", "streets"):
            for e in model[coll]:
                if e["id"] == eid:
                    g = _poly(entity_points(e))
                    return g, {"kind": "entity", "id": eid, "name": name or e.get("name") or eid, "points": _pts(g)}
        raise SystemExit(f"no entity with id {eid} in {model['place']['id']}")
    if k == "rect":
        x0, y0, x1, y1 = [float(v) for v in spec["rect"]]
        g = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
        return g, {"kind": "rect", "rect": [x0, y0, x1, y1], "name": name or "rect_%d_%d" % (x0, y0), "points": _pts(g)}
    if k == "polygon":
        g = _poly(spec["points"])
        if g.is_empty or g.area < 100:
            raise SystemExit("region polygon is empty or smaller than 100 ft2")
        return g, {"kind": "polygon", "source": spec.get("source", "polygon"), "name": name or "region", "points": _pts(g)}
    raise SystemExit("region needs --district/--entity, --rect, --polygon or --polygon-file")


def _pts(g):
    return [[round(x, 2), round(y, 2)] for x, y in list(g.exterior.coords)[:-1]]


def _rings(g):
    """Exterior rings of every polygon part of a shapely geometry."""
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type == "Polygon" and not p.is_empty and p.area > 0.5:
            out.append([[round(x, 2), round(y, 2)] for x, y in list(p.exterior.coords)[:-1]])
    return out


# ------------------------------------------------------------------ clipping
def clip_model(model, region, work, opts):
    """-> child entity collections, id_map, dropped list, markers. `region` = the polygon asked for, `work` = region + margin."""
    out = {"buildings": [], "streets": [], "water": [], "districts": []}
    idmap, dropped, markers = {}, [], []

    def tag(e, **kw):
        e = json.loads(json.dumps(e))
        e["region"] = {"parent_id": e["id"], **kw}
        return e

    for b in model["buildings"]:
        g = _poly(b["geometry"]["points"])
        if g.is_empty or g.area <= 0:
            continue
        inside = g.intersection(work).area / g.area
        in_region = g.intersection(region).area / g.area
        if work.contains(g.centroid) or inside > 0.5:
            e = tag(b, clipped=False, edge=bool(inside < 0.999), inside_frac=round(inside, 3), in_region_frac=round(in_region, 3))
            if opts.get("clip_buildings") and inside < 0.999:
                parts = _rings(g.intersection(work))
                if parts:
                    e["geometry"] = {**e["geometry"], "points": max(parts, key=lambda r: Polygon(r).area)}
                    e["region"]["clipped"] = True
            out["buildings"].append(e)
            idmap[b["id"]] = [b["id"]]
        else:
            dropped.append({"id": b["id"], "reason": "mostly outside", "inside_frac": round(inside, 3)})

    for s in model["streets"]:
        pts = s["geometry"]["points"]
        line = LineString(pts)
        res = line.intersection(work)
        parts = [g for g in getattr(res, "geoms", [res]) if g.geom_type == "LineString" and g.length > max(1.0, s["geometry"]["width_ft"] * 0.25)]
        if not parts:
            if line.distance(work) > 0:
                continue
            dropped.append({"id": s["id"], "reason": "fragment"})
            continue
        parts.sort(key=lambda g: -g.length)
        for n, g in enumerate(parts):
            cid = s["id"] if n == 0 else f"{s['id']}__p{n + 1}"
            cp = [[round(x, 2), round(y, 2)] for x, y in g.coords]
            a0, a1 = Point(pts[0]), Point(pts[-1])
            cont = {"start": Point(cp[0]).distance(a0) > 0.6 and Point(cp[0]).distance(work.boundary) < 0.6,
                    "end": Point(cp[-1]).distance(a1) > 0.6 and Point(cp[-1]).distance(work.boundary) < 0.6}
            clipped = cont["start"] or cont["end"] or len(cp) != len(pts)
            e = tag(s, clipped=bool(cont["start"] or cont["end"]), continues_off_map=cont)
            e["id"] = cid
            e["geometry"] = {**s["geometry"], "points": cp}
            e["region"]["part"] = n + 1
            out["streets"].append(e)
            idmap.setdefault(s["id"], []).append(cid)
            for end, at, nxt in (("start", cp[0], cp[1]), ("end", cp[-1], cp[-2])):
                if cont[end]:
                    d = np.array(at) - np.array(nxt)
                    d = d / (np.hypot(*d) or 1.0)
                    markers.append({"id": f"mk_{cid}_{end}", "kind": "continues_off_map", "street": cid, "parent_street": s["id"], "point": at,
                                    "dir": [round(float(d[0]), 3), round(float(d[1]), 3)], "width_ft": s["geometry"]["width_ft"],
                                    "label": f"{s['name']} continues"})

    for kind, coll in (("water", "water"), ("districts", "districts")):
        for e in model[coll]:
            g = _poly(e["geometry"]["points"])
            if g.is_empty or not g.intersects(work):
                continue
            inter = g.intersection(work)
            if inter.is_empty or inter.area < 4:
                continue
            frac = inter.area / g.area
            parts = sorted(_rings(inter), key=lambda r: -Polygon(r).area)
            lp = e.get("label_point")
            for n, r in enumerate(parts):
                if Polygon(r).area < 20:
                    continue
                c = tag(e, clipped=bool(frac < 0.999), inside_frac=round(frac, 3))
                c["id"] = e["id"] if n == 0 else f"{e['id']}__p{n + 1}"
                c["geometry"] = {**e["geometry"], "points": r}
                if lp and not Polygon(r).contains(Point(lp)):
                    c.pop("label_point", None)
                c["region"]["part"] = n + 1
                out[coll].append(c)
                idmap.setdefault(e["id"], []).append(c["id"])
    return out, idmap, dropped, markers


# ------------------------------------------------------------------ terrain: crop + up-resolve
def _smooth(t):
    t = np.clip(t, 0, 1)
    return t * t * (3 - 2 * t)


def _raster(polys, x0, y0, f, shape):
    """Boolean mask of the fine grid (node (i,j) at x0+j*f, y0+i*f) covered by the polygons (pixel centres at the nodes)."""
    from PIL import Image, ImageDraw
    ny, nx = shape
    im = Image.new("L", (nx, ny), 0)
    dr = ImageDraw.Draw(im)
    for g in polys:
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon" or p.is_empty:
                continue
            for ring, fill in [(p.exterior, 255)] + [(r, 0) for r in p.interiors]:
                dr.polygon([((x - x0) / f, (y - y0) / f) for x, y in ring.coords], fill=fill)
    return np.asarray(im) > 0


def upres_terrain(h, cell, work_bbox, factor, seed, detail_ft=0.45, pad_cells=2, road_polys=(), pad_polys=(), water_polys=(),
                  feather_ft=6.0, flatten_pads=True, pad_blend_ft=5.0):
    """Crop heightmap `h` (coarse `cell` ft, node (i,j) at x=j*cell) to work_bbox (+pad) and up-resolve by integer `factor`.
    Returns (h_fine float32, meta). The coarse nodes are reproduced exactly (cubic interpolating spline, zero-at-node detail),
    except under flattened building pads (disable with flatten_pads=False for an exact match). Deterministic for a given seed."""
    ny, nx = h.shape
    bx0, by0, bx1, by1 = work_bbox
    j0, i0 = max(0, int(math.floor(bx0 / cell)) - pad_cells), max(0, int(math.floor(by0 / cell)) - pad_cells)
    j1, i1 = min(nx - 1, int(math.ceil(bx1 / cell)) + pad_cells), min(ny - 1, int(math.ceil(by1 / cell)) + pad_cells)
    if j1 - j0 < 3 or i1 - i0 < 3:
        raise SystemExit("region is outside the parent heightmap (or too small)")
    crop = h[i0:i1 + 1, j0:j1 + 1].astype(np.float64)
    cy, cx = crop.shape
    f = max(1, int(factor))
    fine = cell / f
    xs_c, ys_c = np.arange(cx) * cell, np.arange(cy) * cell
    xs_f, ys_f = np.arange((cx - 1) * f + 1) * fine, np.arange((cy - 1) * f + 1) * fine
    spl = RectBivariateSpline(ys_c, xs_c, crop, kx=3, ky=3, s=0)
    base = spl(ys_f, xs_f)
    # local min/max clamp (3x3 coarse neighbourhood, widened by 15% of the local range) tames spline overshoot at sharp banks
    lo = ndi.minimum_filter(crop, 3, mode="nearest")
    hi = ndi.maximum_filter(crop, 3, mode="nearest")
    rng_ = np.maximum(hi - lo, 0.05)
    lo_f = ndi.zoom(lo - 0.15 * rng_, f, order=1, mode="nearest")[:base.shape[0], :base.shape[1]] if f > 1 else lo - 0.15 * rng_
    hi_f = ndi.zoom(hi + 0.15 * rng_, f, order=1, mode="nearest")[:base.shape[0], :base.shape[1]] if f > 1 else hi + 0.15 * rng_
    if lo_f.shape == base.shape:
        base = np.minimum(np.maximum(base, lo_f), hi_f)
    X0, Y0 = j0 * cell, i0 * cell
    shape = base.shape
    rng = np.random.default_rng([int(seed) & 0x7FFFFFFF, 7919])
    if f > 1 and detail_ft > 0:
        # band-limited multi-octave noise between ~2 coarse cells and ~4 fine cells; rougher octaves weigh less
        noise = np.zeros(shape)
        per = 2.0 * cell
        wsum = 0.0
        while per >= 4.0 * fine - 1e-9:
            n = ndi.gaussian_filter(rng.standard_normal(shape), max(per / (2.6 * fine), 0.6), mode="reflect")
            n /= (n.std() or 1.0)
            w = (per / (2.0 * cell)) ** 0.8
            noise += w * n
            wsum += w * w
            per *= 0.5
        noise /= math.sqrt(wsum) or 1.0
        # zero at the coarse nodes: subtract the spline through the noise sampled at the nodes
        samp = noise[::f, ::f][:cy, :cx]
        noise = noise - RectBivariateSpline(ys_c, xs_c, samp, kx=3, ky=3, s=0)(ys_f, xs_f)
        gy, gx = np.gradient(base, fine)
        slope = ndi.gaussian_filter(np.hypot(gx, gy), 1.5)
        amp = detail_ft * (0.35 + np.clip(slope / 0.45, 0, 1.6))
        w_keep = np.ones(shape)
        cover = [("road", road_polys, 1.0), ("pad", pad_polys, 1.0), ("water", water_polys, 0.75)]
        for _, polys, strength in cover:
            if polys:
                m = _raster(polys, X0, Y0, fine, shape)
                if m.any():
                    dist = ndi.distance_transform_edt(~m) * fine
                    w_keep = np.minimum(w_keep, 1.0 - strength * (1.0 - _smooth(dist / feather_ft)))
        base = base + noise * amp * w_keep
    nodal_dev = 0.0
    padmask = np.zeros(shape, bool)
    if flatten_pads and pad_polys:
        for g in pad_polys:
            m = _raster([g], X0, Y0, fine, shape)
            if not m.any():
                continue
            target = float(base[m].mean())
            dist = ndi.distance_transform_edt(~m) * fine
            w = 1.0 - _smooth(dist / pad_blend_ft)
            w[dist > pad_blend_ft] = 0.0
            sel = w > 0
            padmask |= sel
            base[sel] = base[sel] * (1 - w[sel]) + target * w[sel]
    nodes = base[::f, ::f][:cy, :cx]
    nodal_dev = float(np.abs(nodes - crop).max())
    pm_nodes = padmask[::f, ::f][:cy, :cx]
    dev_out = float(np.abs(nodes - crop)[~pm_nodes].max()) if (~pm_nodes).any() else 0.0
    hf = base.astype(np.float32)
    meta = {"size_ft": [round(X0 + (shape[1] - 1) * fine, 3), round(Y0 + (shape[0] - 1) * fine, 3)], "cell_ft": fine, "nx": int(shape[1]), "ny": int(shape[0]),
            "origin_ft": [X0, Y0], "seed": int(seed), "elev_min": float(hf.min()), "elev_max": float(hf.max()), "relief_ft": float(hf.max() - hf.min()),
            "units": "feet", "pipeline": "region_upres_v1", "parent_cell_ft": cell, "upres_factor": f, "detail_ft": detail_ft,
            "max_node_dev_ft": round(nodal_dev, 4), "max_node_dev_outside_pads_ft": round(dev_out, 5), "flattened_pads": bool(flatten_pads and pad_polys),
            "node_convention": "h[i,j] at x=origin_x+j*cell_ft, y=origin_y+i*cell_ft (y down); worldio pads the crop to the full frame"}
    return hf, meta


def downsample_to_parent(hf, meta):
    """Fine heightmap -> the coarse nodes it was made from (used by tests and the report)."""
    f = meta["upres_factor"]
    return hf[::f, ::f]


# ------------------------------------------------------------------ detail pass (generated at district scale; NOT canon)
BIG = {"civic", "inn", "barn", "stable", "craft"}


def detail_pass(coll, work, region_poly, which, seed, params):
    """-> details dict. Everything carries detail=True and note 'detail: generated at district scale'."""
    rng = np.random.default_rng([int(seed) & 0x7FFFFFFF, 104729])
    which = set(DETAIL_KINDS if which == "all" else which)
    D = {"canon": False, "note": "detail: generated at district scale (not canon, safe to regenerate)", "seed": int(seed), "kinds": sorted(which),
         "doors": [], "roofs": [], "chimneys": [], "lots": [], "fences": [], "kerbs": [], "trees": []}
    blds = [(b, _poly(b["geometry"]["points"])) for b in coll["buildings"]]
    street_geoms = []
    for s in coll["streets"]:
        street_geoms.append((s, LineString(s["geometry"]["points"]).buffer(s["geometry"]["width_ft"] / 2, cap_style=2, resolution=4)))
    roads = unary_union([g for _, g in street_geoms]) if street_geoms else Polygon()
    all_b = unary_union([g for _, g in blds]) if blds else Polygon()
    water = unary_union([_poly(w["geometry"]["points"]) for w in coll["water"]]) if coll["water"] else Polygon()
    fields = [e for e in coll["districts"] if e["kind"] == "field"]
    field_u = unary_union([_poly(e["geometry"]["points"]) for e in fields]) if fields else Polygon()
    tag = {"detail": True}

    if "doors" in which or "roofs" in which or "chimneys" in which:
        for b, g in blds:
            if g.area < 40:
                continue
            coords = list(g.exterior.coords)[:-1]
            # door on the footprint edge that faces the nearest street (longest edge wins ties)
            best = None
            c = g.centroid
            near = min(street_geoms, key=lambda sg: sg[1].distance(c), default=None)
            for i in range(len(coords)):
                p, q = np.array(coords[i]), np.array(coords[(i + 1) % len(coords)])
                L = float(np.hypot(*(q - p)))
                if L < 5:
                    continue
                m = (p + q) / 2
                d = near[1].distance(Point(m)) if near else 0
                score = d - 0.02 * L
                if best is None or score < best[0]:
                    best = (score, i, p, q, m, L)
            if best and "doors" in which:
                _, i, p, q, m, L = best
                n = np.array([q[1] - p[1], -(q[0] - p[0])]) / L
                if g.contains(Point(m + n * 0.5)):
                    n = -n
                wd = 6.0 if b["kind"] in BIG else 3.5
                D["doors"].append({"id": f"{b['id']}_door1", "building": b["id"], "edge": i, "point": [round(float(m[0]), 2), round(float(m[1]), 2)],
                                   "width_ft": wd, "facing": [round(float(n[0]), 3), round(float(n[1]), 3)], **tag})
            if "roofs" in which or "chimneys" in which:
                mrr = g.minimum_rotated_rectangle
                rc = list(mrr.exterior.coords)[:-1]
                if len(rc) >= 4:
                    e0, e1 = np.array(rc[1]) - np.array(rc[0]), np.array(rc[2]) - np.array(rc[1])
                    long_ = e0 if np.hypot(*e0) >= np.hypot(*e1) else e1
                    ln = float(np.hypot(*long_)) or 1.0
                    u = long_ / ln
                    ctr = np.array([mrr.centroid.x, mrr.centroid.y])
                    kind = "hip" if (b["kind"] in ("civic", "inn") and rng.random() < 0.5) else "gable"
                    r0, r1 = ctr - u * ln * (0.38 if kind == "gable" else 0.28), ctr + u * ln * (0.38 if kind == "gable" else 0.28)
                    if "roofs" in which:
                        D["roofs"].append({"id": f"{b['id']}_roof", "building": b["id"], "type": kind, "ridge": [[round(float(v), 2) for v in r0], [round(float(v), 2) for v in r1]], **tag})
                    if "chimneys" in which and b["kind"] in ("house", "farmhouse", "inn", "civic", "craft") and rng.random() < 0.8:
                        cpos = r0 + (r1 - r0) * float(rng.choice([0.12, 0.88]))
                        nrm = np.array([-u[1], u[0]])
                        cq = [cpos + (a * u + bb * nrm) * 1.0 for a, bb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                        D["chimneys"].append({"id": f"{b['id']}_chimney", "building": b["id"], "geometry": [[round(float(v), 2) for v in p] for p in cq], **tag})

    taken = unary_union([roads, all_b]) if not (roads.is_empty and all_b.is_empty) else Polygon()
    lot_u = Polygon()
    if "lots" in which or "fences" in which:
        for b, g in sorted(blds, key=lambda t: t[0]["id"]):
            if b["kind"] not in ("house", "farmhouse", "craft", "inn", "stable") or g.area < 60:
                continue
            yard = float(params.get("yard_ft", 18.0)) * (1.6 if b["kind"] == "farmhouse" else 1.0)
            lot = g.buffer(yard, join_style=2)
            lot = lot.difference(roads.buffer(1.0)).difference(all_b.difference(g).buffer(1.0)).difference(lot_u).difference(water.buffer(2.0))
            lot = lot.intersection(work)
            if lot.geom_type != "Polygon":
                pcs = [p for p in getattr(lot, "geoms", []) if p.geom_type == "Polygon"]
                lot = max(pcs, key=lambda p: p.area) if pcs else Polygon()
            if lot.is_empty or lot.area < g.area * 1.4:
                continue
            lot = lot.simplify(0.4)
            lot_u = unary_union([lot_u, lot])
            if "lots" in which:
                D["lots"].append({"id": f"{b['id']}_lot", "building": b["id"], "geometry": _rings(lot)[0], **tag})
            if "fences" in which and rng.random() < float(params.get("fence_frac", 0.75)):
                ring = list(lot.exterior.coords)
                # open the fence where the lot meets the street (gate side) by dropping segments hugging the road
                seg = []
                cur = []
                for a, bq in zip(ring[:-1], ring[1:]):
                    m = Point((a[0] + bq[0]) / 2, (a[1] + bq[1]) / 2)
                    if roads.distance(m) < 1.8 and rng.random() < 0.45:
                        if cur:
                            seg.append(cur)
                        cur = []
                        continue
                    if not cur:
                        cur = [a]
                    cur.append(bq)
                if cur:
                    seg.append(cur)
                for n, s in enumerate(seg):
                    if len(s) >= 2 and LineString(s).length > 6:
                        D["fences"].append({"id": f"{b['id']}_fence{n + 1}", "building": b["id"], "points": [[round(x, 2), round(y, 2)] for x, y in s], **tag})

    if "kerbs" in which:
        for s, g in street_geoms:
            if s["kind"] == "bridge" or s["geometry"]["width_ft"] < 14:
                continue
            w = 3.0 if s["kind"] != "road" else 0.0
            if w <= 0:
                continue
            ring = g.buffer(w, cap_style=2, join_style=2).difference(g).difference(all_b.buffer(0.5)).difference(water)
            ring = ring.intersection(work)
            for n, r in enumerate(_rings(ring)):
                if Polygon(r).area > 30:
                    D["kerbs"].append({"id": f"{s['id']}_kerb{n + 1}", "street": s["id"], "geometry": r, **tag})

    if "trees" in which:
        density = float(params.get("tree_per_1000ft2", 0.35))
        spacing = float(params.get("tree_spacing_ft", 14.0))
        minx, miny, maxx, maxy = work.bounds
        n_try = int((maxx - minx) * (maxy - miny) / 1000.0 * density * 6)
        keep = []
        avoid = unary_union([roads.buffer(3.0), all_b.buffer(3.0), water.buffer(4.0), field_u.buffer(-2.0)])
        for _ in range(n_try):
            x, y = rng.uniform(minx, maxx), rng.uniform(maxy * 0 + miny, maxy)
            pt = Point(x, y)
            if not work.contains(pt) or avoid.contains(pt):
                continue
            # trees favour yards and the edges of fields, thin out in the open
            p_acc = 0.9 if lot_u.contains(pt) else (0.55 if field_u.distance(pt) < 12 else 0.3)
            if rng.random() > p_acc:
                continue
            if any((x - kx) ** 2 + (y - ky) ** 2 < spacing ** 2 for kx, ky, _ in keep):
                continue
            keep.append((x, y, float(rng.uniform(3.5, 8.0))))
            if len(keep) >= int(params.get("max_trees", 400)):
                break
        for n, (x, y, r) in enumerate(keep):
            D["trees"].append({"id": f"tree_{n + 1:03d}", "x": round(x, 2), "y": round(y, 2), "r_ft": round(r, 2), "kind": "oak" if r > 5.2 else "birch", **tag})
    return D


# ------------------------------------------------------------------ writing the child
def child_dir(child_id, root=None):
    return os.path.join(root or WORLD, *child_id.split("/"))


def default_child_id(parent, name, sandbox):
    base = f"{parent}__{slug(name)}"
    return f"{SANDBOX}/{base}" if sandbox else base


def build_view_settings(parent_vs, window, fpi, grid, margin_in=0.5, major=4):
    x0, y0, x1, y1 = window
    w_in = math.ceil(((x1 - x0) / fpi + 2 * margin_in) * 2) / 2
    h_in = math.ceil(((y1 - y0) / fpi + 2 * margin_in) * 2) / 2
    cx, cy = round((x0 + x1) / 2, 1), round((y0 + y1) / 2, 1)
    vs = json.loads(json.dumps(parent_vs)) if parent_vs else {}
    vs["_note"] = "District child map: preset 'district' is the zoomed-in view (scale, grid, page fit to the region). Overrides: --scale/--grid/--page."
    vs["page_in"] = [max(w_in, 4), max(h_in, 4)]
    vs["margin_in"] = margin_in
    vs["default_preset"] = "district"
    presets = vs.setdefault("presets", {})
    for k, p in list(presets.items()):
        if p.get("focus") in ("center", None) or isinstance(p.get("focus"), list):
            p["focus"] = [cx, cy]
    presets["district"] = {"scale_ft_per_in": fpi, "grid_ft": grid, "grid_major_every": major, "focus": [cx, cy],
                           "scale_bar_ft": _nice(5 * fpi), "page_in": vs["page_in"]}
    return vs


def _nice(v):
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 2, 2.5, 5, 10):
        if v <= m * e * 1.0001:
            return m * e
    return v


def write_child(cid, out_root, parent, model, coll, idmap, dropped, markers, details, terrain, rspec, region, work, opts, fp):
    cdir = child_dir(cid, out_root)
    keep_art = {}
    if os.path.isdir(cdir):
        for f in ("panel_state.json",):
            if os.path.exists(os.path.join(cdir, f)):
                keep_art[f] = open(os.path.join(cdir, f), "rb").read()
        for sub in ("buildings", "terrain"):
            shutil.rmtree(os.path.join(cdir, sub), ignore_errors=True)
    os.makedirs(os.path.join(cdir, "buildings"), exist_ok=True)
    pplace = model["place"]
    x0, y0, x1, y1 = work.bounds
    ox, oy = opts["origin"]
    shift = lambda p: [round(p[0] - ox, 2), round(p[1] - oy, 2)]  # noqa: E731
    if ox or oy:
        for coll_name in ("buildings", "streets", "water", "districts"):
            for e in coll[coll_name]:
                g = e["geometry"]
                g["points"] = [shift(p) for p in g["points"]]
                if "label_point" in e:
                    e["label_point"] = shift(e["label_point"])
        for m in markers:
            m["point"] = shift(m["point"])
        if details:
            for d_ in details.get("doors", []):
                d_["point"] = shift(d_["point"])
            for d_ in details.get("roofs", []):
                d_["ridge"] = [shift(q) for q in d_["ridge"]]
            for sec in ("chimneys", "lots", "kerbs"):
                for d_ in details.get(sec, []):
                    d_["geometry"] = [shift(q) for q in d_["geometry"]]
            for d_ in details.get("fences", []):
                d_["points"] = [shift(q) for q in d_["points"]]
            for d_ in details.get("trees", []):
                d_["x"], d_["y"] = shift([d_["x"], d_["y"]])
        if terrain:
            m_ = terrain["meta"]
            m_["origin_ft"] = [m_["origin_ft"][0] - ox, m_["origin_ft"][1] - oy]
            m_["size_ft"] = [m_["size_ft"][0] - ox, m_["size_ft"][1] - oy]
            terrain["report"]["origin_ft"] = m_["origin_ft"]
    win = [x0 - ox, y0 - oy, x1 - ox, y1 - oy]
    snapshot = {}
    for e in coll["buildings"]:
        _wj(os.path.join(cdir, "buildings", e["id"] + ".json"), e)
    for coll_name, fn, key in (("districts", "districts.json", "districts"), ("streets", "streets.json", "streets"), ("water", "water.json", "water")):
        _wj(os.path.join(cdir, fn), {"place": cid, key: coll[coll_name]})
    for coll_name in coll:
        for e in coll[coll_name]:
            snapshot[e["id"]] = ehash(e)
    fpi, grid = opts["scale"], opts["grid"]
    vs = build_view_settings(_rj(os.path.join(worldio.world_dir(pplace["id"]), "view_settings.json"), {}), win, fpi, grid)
    _wj(os.path.join(cdir, "view_settings.json"), vs)
    place = {
        "id": cid, "name": f"{pplace.get('name', pplace['id'])} - {rspec['name']}", "kind": "district", "status": pplace.get("status", "proposed"),
        "units": "feet", "origin": "top-left, y down",
        "bounds": {"width_ft": round(max(win[2], 1), 2), "height_ft": round(max(win[3], 1), 2)}, "window_ft": [round(v, 2) for v in win],
        "parent": {"place": pplace["id"], "region": "region.json"},
        "notes": f"Zoom-in child of {pplace['id']} (region {rspec['name']}). Same ids and foot coordinates as the parent"
                 + (f" shifted by origin_ft {ox},{oy}" if ox or oy else "") + ". See region.json; details.json is generated, not canon.",
        "files": {"districts": "districts.json", "streets": "streets.json", "water": "water.json", "buildings": "buildings/",
                  "view_settings": "view_settings.json", "terrain": "terrain/", "region": "region.json", "details": "details.json", "markers": "markers.json"},
        "view_focus": {"district": [round((win[0] + win[2]) / 2, 1), round((win[1] + win[3]) / 2, 1)]},
        "links": {"foundry_scene": None, "model3d": None, "ai_layer": None, "parent_place": pplace["id"]},
        "generated_by": "region_extract.py", "sea_level_ft": pplace.get("sea_level_ft", 0.0),
    }
    _wj(os.path.join(cdir, "place.json"), place)
    outline = [shift(p) for p in rspec["points"]]
    _wj(os.path.join(cdir, "markers.json"), {"region_outline": outline, "markers": markers})
    _wj(os.path.join(cdir, "details.json"), details if details else {"canon": False, "kinds": []})
    reg = {
        "schema": SCHEMA, "child": cid, "parent": pplace["id"], "name": rspec["name"],
        "region": {**{k: v for k, v in rspec.items() if k != "points"}, "polygon_parent_ft": rspec["points"], "area_ft2": round(region.area, 1)},
        "work_area_polygon_parent_ft": _rings(work)[0], "margin_ft": opts["margin"],
        "transform": {"type": "translate", "origin_ft": [ox, oy], "scale": 1.0, "note": "child = parent - origin_ft (feet, y down); zoom is the view scale only"},
        "window_parent_ft": [round(v, 2) for v in work.bounds],
        "parent_source": fp, "extracted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "params": {k: v for k, v in opts.items() if k not in ("origin",)}, "id_map": idmap, "dropped": dropped,
        "counts": {k: len(v) for k, v in coll.items()}, "snapshot": snapshot,
        "interiors": {e["id"]: f"world/{pplace['id']}/buildings/{e['id']}.json" for e in coll["buildings"] if e.get("rooms")},
        "terrain": terrain.get("report") if terrain else None,
        "sync": {"shared_attrs": ["name", "kind", "status", "notes", "floors", "links", "geometry (unclipped, unshifted-aware)"],
                 "rule": "child -> parent only through `region_extract.py sync --child ID --apply` (diff first)"},
    }
    _wj(os.path.join(cdir, "region.json"), reg)
    if terrain:
        from terrain import save as tsave
        tsave(terrain["h"], terrain["meta"], os.path.join(cdir, "terrain"))
    for f, data in keep_art.items():
        open(os.path.join(cdir, f), "wb").write(data)
    return cdir, reg


# ------------------------------------------------------------------ extract (library entry)
def extract(parent, rspec, name=None, root=None, out_root=None, margin=40.0, terrain_cell=2.5, seed=None, scale=20.0, grid=5.0, detail="all",
            detail_params=None, clip_buildings=False, local_origin=False, sandbox=False, child_id=None, terrain=True, detail_ft=0.45,
            flatten_pads=True, edits=None, log=LOG):
    """Extract the child. Returns {child, dir, report}. `edits` (from refresh): {"keep": {id: child entity}, "child_only": {kind: [entities]}}."""
    model = load_parent(parent, root)
    region, rspec = resolve_region(model, {**rspec, **({"name": name} if name else {})})
    work = region.buffer(margin, join_style=1) if margin > 0 else region
    x0, y0, x1, y1 = work.bounds
    seed = int(seed if seed is not None else int(hashlib.sha1((parent + rspec["name"]).encode()).hexdigest()[:6], 16))
    cid = child_id or default_child_id(parent, rspec["name"], sandbox)
    origin = (math.floor(x0 / 10) * 10.0, math.floor(y0 / 10) * 10.0) if local_origin else (0.0, 0.0)
    coll, idmap, dropped, markers = clip_model(model, region, work, {"clip_buildings": clip_buildings})
    log(f"region {rspec['name']!r}: {region.area:.0f} ft2 (+{margin:g} ft margin); kept {len(coll['buildings'])} buildings, {len(coll['streets'])} street parts, "
        f"{len(coll['water'])} water, {len(coll['districts'])} districts; dropped {len(dropped)}; {len(markers)} continue-off-map markers")
    if edits:
        for kind, d in edits.get("keep", {}).items():
            for e in coll[kind]:
                if e["id"] in d:
                    log(f"  kept child edit: {e['id']}")
                    eid, new = e["id"], d[e["id"]]
                    e.clear()
                    e.update(new)
        for kind, lst in edits.get("child_only", {}).items():
            coll[kind] += lst
    details = None
    if detail and detail != "none":
        which = "all" if detail == "all" else [k for k in (detail if isinstance(detail, (list, tuple)) else str(detail).split(",")) if k in DETAIL_KINDS]
        details = detail_pass(coll, work, region, which, seed, detail_params or {})
        log("detail pass: " + ", ".join(f"{k} {len(details[k])}" for k in DETAIL_KINDS if details.get(k)))
    tout = None
    if terrain:
        h, meta = worldio.load_terrain(parent, root=root)
        o = meta.get("origin_ft")
        if o and (o[0] or o[1]):
            raise SystemExit("parent terrain has an origin_ft crop (a child of a child is not supported yet)")
        cell = float(meta["cell_ft"])
        factor = max(1, int(round(cell / float(terrain_cell))))
        roads = [LineString(s["geometry"]["points"]).buffer(s["geometry"]["width_ft"] / 2, cap_style=2) for s in coll["streets"]]
        pads = [_poly(b["geometry"]["points"]).buffer(1.0) for b in coll["buildings"]]
        waters = [_poly(w["geometry"]["points"]) for w in coll["water"]]
        hf, tm = upres_terrain(h, cell, work.bounds, factor, seed, detail_ft, road_polys=roads, pad_polys=pads, water_polys=waters,
                               flatten_pads=flatten_pads)
        for k in ("sea_level_ft",):
            tm[k] = meta.get(k, 0.0)
        tm["parent_source"] = meta.get("source")
        shapeok = hf.shape
        tout = {"h": hf, "meta": tm, "report": {k: tm[k] for k in ("cell_ft", "parent_cell_ft", "upres_factor", "nx", "ny", "elev_min", "elev_max",
                                                                   "max_node_dev_ft", "max_node_dev_outside_pads_ft", "origin_ft", "detail_ft", "seed")}}
        log(f"terrain: {cell:g} ft -> {tm['cell_ft']:g} ft cells ({shapeok[1]}x{shapeok[0]}), elev {tm['elev_min']:.1f}..{tm['elev_max']:.1f}, "
            f"max deviation from parent nodes {tm['max_node_dev_ft']:.3f} ft ({tm['max_node_dev_outside_pads_ft']:.4f} ft away from building pads)")
    opts = {"margin": margin, "terrain_cell_ft": terrain_cell, "seed": seed, "scale": scale, "grid": grid, "detail": detail if isinstance(detail, str) else ",".join(detail),
            "detail_params": detail_params or {}, "clip_buildings": clip_buildings, "local_origin": local_origin, "origin": origin, "detail_ft": detail_ft,
            "flatten_pads": flatten_pads, "terrain": bool(terrain), "parent_root": root}
    fp = parent_fingerprint(parent, root)
    cdir, reg = write_child(cid, out_root, parent, model, coll, idmap, dropped, markers, details, tout, rspec, region, work, opts, fp)
    log(f"wrote child {cid} -> {cdir}")
    return {"child": cid, "dir": cdir, "report": {"counts": reg["counts"], "dropped": len(dropped), "markers": len(markers), "terrain": reg["terrain"],
                                                    "window_ft": reg["window_parent_ft"], "origin_ft": list(origin), "page_in": _rj(os.path.join(cdir, "view_settings.json"))["page_in"]}}


# ------------------------------------------------------------------ list / refresh / sync
def list_children(parent=None, root=None):  # root = world root holding the children
    out = []
    base = root or WORLD
    for rp in glob.glob(os.path.join(base, "*", "region.json")) + glob.glob(os.path.join(base, SANDBOX, "*", "region.json")):
        r = _rj(rp, {})
        if parent and r.get("parent") != parent:
            continue
        cid = r.get("child")
        out.append({"child": cid, "name": r.get("name"), "parent": r.get("parent"), "extracted_at": r.get("extracted_at"), "counts": r.get("counts"),
                    "sandbox": SANDBOX in rp.replace("\\", "/").split("/")})
    return sorted(out, key=lambda r: (r["parent"] or "", r["child"] or ""))


def _load_child_entities(cdir):
    c = {"buildings": [], "streets": [], "water": [], "districts": []}
    for f in sorted(glob.glob(os.path.join(cdir, "buildings", "*.json"))):
        c["buildings"].append(_rj(f))
    c["streets"] = _rj(os.path.join(cdir, "streets.json"), {}).get("streets", [])
    c["water"] = _rj(os.path.join(cdir, "water.json"), {}).get("water", [])
    c["districts"] = _rj(os.path.join(cdir, "districts.json"), {}).get("districts", [])
    return c


def refresh(child, out_root=None, log=LOG, **over):
    """Re-extract from the parent with the stored parameters, keeping what the child changed: entities whose json differs from the extraction
    snapshot are kept as edited, entities that exist only in the child are kept. ART layers live in the Illustrator document and are never touched."""
    cdir = child_dir(child, out_root)
    reg = _rj(os.path.join(cdir, "region.json"))
    if not reg:
        raise SystemExit(f"{child} has no region.json")
    root = reg["params"].get("parent_root")
    cur = _load_child_entities(cdir)
    snap = reg.get("snapshot", {})
    keep, only = {}, {}
    for kind, lst in cur.items():
        for e in lst:
            if e["id"] not in snap:
                only.setdefault(kind, []).append(e)
            elif ehash(e) != snap[e["id"]]:
                keep.setdefault(kind, {})[e["id"]] = e
    p = reg["params"]
    rspec = {"kind": "polygon", "points": reg["region"]["polygon_parent_ft"], "source": "refresh", "name": reg["name"]}
    if reg["region"].get("kind") == "entity":
        rspec = {"kind": "entity", "id": reg["region"]["id"], "name": reg["name"]}
    if p.get("local_origin") is False and any(p.get("origin", (0, 0))):
        pass
    kw = dict(margin=p["margin"], terrain_cell=p["terrain_cell_ft"], seed=p["seed"], scale=p["scale"], grid=p["grid"], detail=p["detail"],
              detail_params=p.get("detail_params"), clip_buildings=p["clip_buildings"], local_origin=p["local_origin"], terrain=p.get("terrain", True),
              detail_ft=p.get("detail_ft", 0.45), flatten_pads=p.get("flatten_pads", True))
    kw.update(over)
    n_keep = sum(len(v) for v in keep.values())
    log(f"refresh {child}: {n_keep} edited entities kept, {sum(len(v) for v in only.values())} child-only entities kept")
    res = extract(reg["parent"], rspec, root=root, out_root=out_root, child_id=child, edits={"keep": keep, "child_only": only}, log=log, **kw)
    res["report"]["kept_edits"] = n_keep
    return res


def sync_diff(child, out_root=None):
    """Shared attributes that differ between the child and its parent (never written here)."""
    cdir = child_dir(child, out_root)
    reg = _rj(os.path.join(cdir, "region.json"))
    parent = reg["parent"]
    root = reg["params"].get("parent_root")
    pdir = worldio.world_dir(parent, root)
    ox, oy = reg["transform"]["origin_ft"]
    cur = _load_child_entities(cdir)
    pm = {"buildings": {}, "streets": {}, "water": {}, "districts": {}}
    for f in glob.glob(os.path.join(pdir, "buildings", "*.json")):
        e = _rj(f)
        pm["buildings"][e["id"]] = e
    pm["streets"] = {e["id"]: e for e in _rj(os.path.join(pdir, "streets.json"), {}).get("streets", [])}
    pm["districts"] = {e["id"]: e for e in _rj(os.path.join(pdir, "districts.json"), {}).get("districts", [])}
    pm["water"] = {e["id"]: e for e in _rj(os.path.join(pdir, "water.json"), {}).get("water", [])}
    diffs = []
    for kind, lst in cur.items():
        for e in lst:
            pid = (e.get("region") or {}).get("parent_id")
            if not pid:
                diffs.append({"id": e["id"], "kind": kind, "change": "child-only entity (not synced: add it to the parent by hand)"})
                continue
            pe = pm[kind].get(pid)
            if not pe:
                diffs.append({"id": e["id"], "parent_id": pid, "kind": kind, "change": "missing in parent"})
                continue
            for k in ("name", "kind", "status", "notes", "floors", "links"):
                if k in e and e.get(k) != pe.get(k):
                    diffs.append({"id": e["id"], "parent_id": pid, "kind": kind, "attr": k, "parent": pe.get(k), "child": e.get(k)})
            part = (e.get("region") or {}).get("part", 1)
            if part == 1 and not (e["region"].get("clipped") or e["region"].get("edge")):
                a = [[round(p[0] + ox, 1), round(p[1] + oy, 1)] for p in e["geometry"]["points"]]
                b = [[round(p[0], 1), round(p[1], 1)] for p in pe["geometry"]["points"]]
                if a != b and e["geometry"]["type"] == pe["geometry"]["type"]:
                    mv = max((abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(a, b)), default=0) if len(a) == len(b) else None
                    diffs.append({"id": e["id"], "parent_id": pid, "kind": kind, "attr": "geometry.points", "moved_ft": mv, "child": a[:3] + (["..."] if len(a) > 3 else []),
                                  "parent": b[:3] + (["..."] if len(b) > 3 else [])})
    return {"child": child, "parent": parent, "diffs": diffs}, pm, cur, (ox, oy), pdir


def sync_apply(child, out_root=None):
    info, pm, cur, (ox, oy), pdir = sync_diff(child, out_root)
    changed = []
    for d in info["diffs"]:
        if "attr" not in d:
            continue
        kind, pid = d["kind"], d["parent_id"]
        ce = next(e for e in cur[kind] if e["id"] == d["id"])
        pe = pm[kind][pid]
        if d["attr"] == "geometry.points":
            pe["geometry"]["points"] = [[round(p[0] + ox, 2), round(p[1] + oy, 2)] for p in ce["geometry"]["points"]]
        else:
            pe[d["attr"]] = ce[d["attr"]]
        changed.append((kind, pid))
    done = set()
    for kind, pid in changed:
        if (kind, pid) in done:
            continue
        done.add((kind, pid))
        if kind == "buildings":
            _wj(os.path.join(pdir, "buildings", pid + ".json"), pm["buildings"][pid])
    for kind, fn, key in (("streets", "streets.json", "streets"), ("districts", "districts.json", "districts"), ("water", "water.json", "water")):
        if any(k == kind for k, _ in done):
            doc = _rj(os.path.join(pdir, fn))
            doc[key] = [pm[kind].get(e["id"], e) for e in doc[key]]
            _wj(os.path.join(pdir, fn), doc)
    info["applied"] = sorted(f"{k}:{p}" for k, p in done)
    return info


# ------------------------------------------------------------------ preview svg (region outline for the REGIONS layer)
def preview_svg(model, rspec, margin, out, view_args):
    import render_world as rw
    region, rspec = resolve_region(model, rspec)
    work = region.buffer(margin, join_style=1) if margin > 0 else region
    v, cfg, title, kind, ident = rw.compute_view(model, view_args.get("view", "town"), view_args.get("cfg"))
    from lib_svg import LayerTree
    t = LayerTree([("REGIONS", [])], cfg["page_in"][0], cfg["page_in"][1], css="path{fill:none}")
    d = lambda pts: "M" + " L".join("%.2f,%.2f" % v.px(p) for p in pts) + " Z"  # noqa: E731
    nm = "region_" + slug(rspec["name"])
    t.add("REGIONS", f'<path id="{nm}" d="{d(rspec["points"])}" style="fill:none;stroke:#d4202a;stroke-width:1.5"/>')
    if margin > 0:
        t.add("REGIONS", f'<path id="{nm}_margin" d="{d(_rings(work)[0])}" style="fill:none;stroke:#d4202a;stroke-width:0.6;stroke-dasharray:4 3"/>')
    os.makedirs(os.path.dirname(out), exist_ok=True)
    t.write(out)
    return {"svg": out, "region": rspec, "area_ft2": round(region.area, 1), "window_ft": [round(b, 1) for b in work.bounds]}


# ------------------------------------------------------------------ CLI
def _region_args(ap):
    ap.add_argument("--parent", default="bridgehollow")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--district", help="district / square / field / any entity id of the parent")
    g.add_argument("--entity")
    g.add_argument("--rect", help="x0,y0,x1,y1 feet")
    g.add_argument("--polygon", help='"x,y;x,y;..." feet')
    g.add_argument("--polygon-file", help="json list of [x,y] or {points: [...]}")
    ap.add_argument("--name")
    ap.add_argument("--margin", type=float, default=40.0, help="ft of context around the region (default 40)")


def _spec(a):
    if a.district or a.entity:
        return {"kind": "entity", "id": a.district or a.entity}
    if a.rect:
        return {"kind": "rect", "rect": [float(v) for v in a.rect.split(",")]}
    if a.polygon:
        return {"kind": "polygon", "points": [[float(v) for v in p.split(",")] for p in a.polygon.split(";") if p.strip()], "source": "cli"}
    if a.polygon_file:
        d = _rj(a.polygon_file)
        return {"kind": "polygon", "points": d["points"] if isinstance(d, dict) else d, "source": os.path.basename(a.polygon_file)}
    raise SystemExit("choose a region: --district ID | --rect | --polygon | --polygon-file")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    e = sp.add_parser("extract")
    _region_args(e)
    e.add_argument("--terrain-cell", type=float, default=2.5)
    e.add_argument("--seed", type=int)
    e.add_argument("--scale", type=float, default=20.0)
    e.add_argument("--grid", type=float, default=5.0)
    e.add_argument("--detail", default="all", help="comma list of " + ",".join(DETAIL_KINDS) + " | all | none")
    e.add_argument("--detail-ft", type=float, default=0.45, help="terrain micro-relief amplitude (ft, std)")
    e.add_argument("--yard-ft", type=float)
    e.add_argument("--clip-buildings", action="store_true")
    e.add_argument("--local-origin", action="store_true", help="child coordinates = parent - region bbox corner (default: keep parent feet)")
    e.add_argument("--sandbox", action="store_true", help=f"write under world/{SANDBOX}/ (git-ignored)")
    e.add_argument("--child-id")
    e.add_argument("--parent-root", help="world root that holds the parent place (default: repo world/); tests use a frozen snapshot")
    e.add_argument("--out-root", help="world root to write the child into (default: repo world/)")
    e.add_argument("--no-terrain", action="store_true")
    e.add_argument("--no-flatten-pads", action="store_true")
    e.add_argument("--force", action="store_true", help="overwrite an existing child")
    for c in ("list", "refresh", "sync", "preview"):
        s = sp.add_parser(c)
        if c != "preview":
            s.add_argument("--out-root")
        if c == "list":
            s.add_argument("--parent")
        elif c == "preview":
            _region_args(s)
            s.add_argument("--out", required=True)
            s.add_argument("--view", default="town")
            s.add_argument("--scale", type=float)
            s.add_argument("--preset")
            s.add_argument("--page")
        else:
            s.add_argument("--child", required=True)
            if c == "sync":
                s.add_argument("--apply", action="store_true")
            else:
                s.add_argument("--terrain-cell", type=float)
    a = ap.parse_args(argv)
    try:
        if a.cmd == "extract":
            cid = a.child_id or default_child_id(a.parent, a.name or (a.district or a.entity or "region"), a.sandbox)
            if os.path.exists(os.path.join(child_dir(cid, a.out_root), "region.json")) and not a.force:
                raise SystemExit(f"child {cid} already exists: use --force (replaces the data, keeps panel_state) or the refresh command")
            dp = {"yard_ft": a.yard_ft} if a.yard_ft else {}
            r = extract(a.parent, _spec(a), a.name, root=a.parent_root, out_root=a.out_root, margin=a.margin, terrain_cell=a.terrain_cell, seed=a.seed, scale=a.scale, grid=a.grid, detail=a.detail,
                        detail_params=dp, clip_buildings=a.clip_buildings, local_origin=a.local_origin, sandbox=a.sandbox, child_id=cid, terrain=not a.no_terrain,
                        detail_ft=a.detail_ft, flatten_pads=not a.no_flatten_pads)
            out = {"ok": True, **r}
        elif a.cmd == "list":
            out = {"ok": True, "children": list_children(a.parent, a.out_root)}
        elif a.cmd == "refresh":
            over = {"terrain_cell": a.terrain_cell} if a.terrain_cell else {}
            out = {"ok": True, **refresh(a.child, a.out_root, **over)}
        elif a.cmd == "sync":
            if a.apply:
                out = {"ok": True, **sync_apply(a.child, a.out_root)}
            else:
                info = sync_diff(a.child, a.out_root)[0]
                out = {"ok": True, **info, "applied": None, "note": "diff only: nothing written; add --apply to write the parent"}
                for d in info["diffs"]:
                    LOG("  " + json.dumps(d))
        elif a.cmd == "preview":
            model = load_parent(a.parent)
            out = {"ok": True, **preview_svg(model, {**_spec(a), **({"name": a.name} if a.name else {})}, a.margin, a.out,
                                            {"view": a.view, "cfg": {"preset": a.preset, "scale": a.scale, "page": a.page}})}
    except SystemExit as ex:
        if ex.code not in (0, None):
            print(json.dumps({"ok": False, "error": str(ex.code)}))
            return 1
        raise
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
