"""Foliage tests: scatter rules, determinism, ids round trip, merge counts, budget thinning, GLB validity.   python illustrator/generators/test_foliage.py"""
import json
import os
import shutil
import sys
import tempfile

import numpy as np
import shapely

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foliage as fo  # noqa: E402
import foliage_mesh as fm  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        fails.append(name)


lib = fm.FoliageLibrary()
# synthetic place 600 x 400 ft: steep ground on the east side, a building, a road, a river on the west
cell = 5.0
ny, nx = 82, 122
X, Y = np.meshgrid(np.arange(nx) * cell, np.arange(ny) * cell)
H = 100 + np.where(X > 450, (X - 450) * 0.9, 0.0)
BLD = [[(250, 150), (290, 150), (290, 190), (250, 190)]]
ROAD = [([(0, 300), (600, 300)], 16.0)]
WATER = [[(40, 0), (90, 0), (90, 400), (40, 400)]]
env = fo.Env(600, 400, H, cell, BLD, ROAD, WATER)
POLY = [(20, 20), (580, 20), (580, 380), (20, 380)]
base = {"polygon": POLY, "mix": [{"species": "spruce", "weight": 3}, {"species": "birch", "weight": 2}, {"species": "grass", "weight": 1}], "density_per_ha": 300, "seed": 7, "zone": "t1"}

a = fo.scatter(env, lib, base)
b = fo.scatter(env, lib, base)
check("scatter makes instances", len(a) > 100, len(a))
check("deterministic for a seed", a == b)
check("seed changes the layout", a != fo.scatter(env, lib, {**base, "seed": 8}))
xs, ys = np.array([i["x"] for i in a]), np.array([i["y"] for i in a])
check("avoid buildings", env.d_buildings(xs, ys).min() >= 2.0, env.d_buildings(xs, ys).min())
check("avoid roads", env.d_roads(xs, ys).min() >= 1.0, env.d_roads(xs, ys).min())
check("avoid water", not shapely.contains_xy(env.water, xs, ys).any())
sl = fo._bilin(env.slope, cell, xs, ys)
check("slope limit", sl.max() <= 38.0 + 1e-6, sl.max())
check("inside polygon", xs.min() >= 20 and xs.max() <= 580 and ys.min() >= 20 and ys.max() <= 380)
tr = np.array([(i["x"], i["y"]) for i in a if i["species"] == "spruce"])
dm = np.hypot(tr[:, None, 0] - tr[None, :, 0], tr[:, None, 1] - tr[None, :, 1]) + np.eye(len(tr)) * 1e9
check("spacing respected", dm.min() >= 8.9, dm.min())
a2 = fo.scatter(env, lib, {**base, "density_per_ha": 100})
check("density scales", 0.2 < len(a2) / len(a) < 0.5, (len(a2), len(a)))
hi = fo.scatter(env, lib, {**base, "elev_min_ft": 100.0, "elev_max_ft": 110.0, "slope_max_deg": 80})
check("elevation window", all(100.0 <= i["z"] <= 110.5 for i in hi) and len(hi) > 0)
wet = fo.scatter(env, lib, {**base, "mix": [{"species": "alder", "weight": 1}, {"species": "reeds", "weight": 1}], "density_per_ha": 400})
alder = [i for i in wet if i["species"] == "alder"]
reeds = [i for i in wet if i["species"] == "reeds"]
check("alder only on moist ground", len(alder) > 0 and all(env.moisture(np.array([i["x"]]), np.array([i["y"]]))[0] >= 0.3 - 1e-6 for i in alder), len(alder))
check("reeds only on the shore band", len(reeds) > 0 and all(-2.0 <= env.d_water_signed(np.array([i["x"]]), np.array([i["y"]]))[0] <= 6.0 for i in reeds), len(reeds))
cl = fo.scatter(env, lib, {**base, "pattern": "cluster", "cluster_radius_ft": 30, "cluster_size": 20, "mix": [{"species": "birch", "weight": 1}], "density_per_ha": 120})
check("cluster pattern", len(cl) > 20, len(cl))
SQ = [(100, 40), (240, 40), (240, 120), (100, 120)]
ed = fo.scatter(env, lib, {**base, "pattern": "forest_edge", "polygon": SQ, "mix": [{"species": "birch", "weight": 1}], "density_per_ha": 400, "edge_ft": 15})
dd = [min(i["x"] - 100, 240 - i["x"], i["y"] - 40, 120 - i["y"]) for i in ed]
check("forest edge favours the border", len(ed) > 10 and np.mean(dd) < 30.0, np.mean(dd) if dd else None)
orc = fo.scatter(env, lib, {**base, "pattern": "orchard", "polygon": SQ, "mix": [{"species": "rowan", "weight": 1}], "row_spacing_ft": 20, "density_per_ha": 1000})
check("orchard grid", 20 < len(orc) <= 40, len(orc))
hed = fo.scatter(env, lib, {"pattern": "hedge_line", "path": [(120, 220), (220, 220), (260, 250)], "mix": [{"species": "hedge", "weight": 1}], "seed": 3})
check("hedge along path", len(hed) >= 15 and all(abs(i["y"] - 220) < 40 for i in hed), len(hed))

tmp = tempfile.mkdtemp()
doc = fo.FoliageDoc("t", os.path.join(tmp, "foliage.json"))
fo.run_scatter(doc, env, lib, base)
ids1 = sorted(doc.items)
check("ids are fol_<zone>_nnnn", ids1[0] == "fol_t1_0001" and all(i.startswith("fol_t1_") for i in ids1))
doc.save()
d2 = fo.FoliageDoc("t", os.path.join(tmp, "foliage.json"))
check("round trip keeps ids and values", sorted(d2.items) == ids1 and d2.items[ids1[5]] == doc.items[ids1[5]])
hand = fo.add_single(d2, env, lib, "oak", 200.0, 60.0, zone="hand")
check("hand placed flagged", hand["src"] == "hand" and hand["id"] == "fol_hand_0001")
rr = fo.run_scatter(d2, env, lib, {**base, "seed": 9})
check("regenerate replaces generated only", hand["id"] in d2.items and rr["replaced"] == len(ids1))
check("ids are never reused", d2.counters["t1"] > len(ids1) and not (set(ids1) & set(d2.items)))
nclr = d2.clear([(0, 0), (600, 0), (600, 200), (0, 200)])
check("clear region leaves hand-placed", nclr > 0 and hand["id"] in d2.items and all(i["y"] > 200 or i["src"] == "hand" for i in d2.items.values()))
pp, n = fo.export_pack_scatter(d2, lib, root=tmp)
exp = json.load(open(pp))["instances"]
check("pack scatter keeps ids", [e["id"] for e in exp] == sorted(d2.items))
check("library has the northern set", {"scots_pine", "spruce", "birch", "oak", "beech", "alder", "willow", "rowan", "juniper", "bush", "hedge", "reeds", "fern", "grass", "flowers", "stump", "log", "boulder"} <= set(lib.species))
check("LOD triangles decrease", all(lib.tris(s, 0) >= lib.tris(s, 1) >= lib.tris(s, 2) for s in lib.species))
HERO = {"beech_bw", "ash_bw"}                      # imported Baileywiki hero trees are allowed to be heavy (low density)
check("v2 LOD0 budget: procedural <= 800 tris, imported heroes <= 32k", all(lib.tris(s, 0) <= (32000 if s in HERO else 800) for s in lib.species),
      {s: lib.tris(s, 0) for s in lib.species if lib.tris(s, 0) > 800})
check("v2 LOD1 about half or less of LOD0 for crowns", all(lib.tris(s, 1) <= lib.tris(s, 0) * 0.8 for s in ("oak", "spruce", "birch", "willow", "scots_pine", "beech_bw")))
_big = [s for s in lib.species if lib.species[s]["kind"] in ("tree", "shrub", "hedge")]
check("crowns carry normals + vertex colour", all(lib.mesh(s).N is not None and lib.mesh(s).C is not None and lib.mesh(s).N.shape == lib.mesh(s).V.shape for s in _big))
check("crown cards use alpha-cut leaf tiles only (no BLEND)", all(t in fm.TILES for s in lib.species.values() for t in s["tiles"].values()))
_ao = lib.mesh("oak").C[:, :3].mean(1)
check("baked AO varies across the crown", float(_ao.max() - _ao.min()) > 0.3, float(_ao.max() - _ao.min()))
import tempfile as _tf
_a = os.path.join(_tf.mkdtemp(), "a.png")
from PIL import Image as _I
_ims = {}
for _se in ("summer", "autumn", "winter"):
    fm.write_atlas(_a, season=_se)
    _im = _I.open(_a)
    _ims[_se] = _im.size, float(__import__("numpy").asarray(_im)[:, :, 3].mean())
check("atlas 2048x1536, three seasons differ (winter has fewer opaque texels)", _ims["summer"][0] == (2048, 1536) and _ims["winter"][1] < _ims["summer"][1] - 3, _ims)
check("imported species load (beech/ash/bush) and stand on the ground", all(abs(lib.mesh(s).V[:, 2].min()) < 0.6 for s in ("beech_bw", "ash_bw", "bush_bw1")))

fr = wp.Frame(600, 400, 90.0, 20.0)
ground = fo.Ground(fr, H, cell)
out = os.path.join(tmp, "opt")
fdoc, rep = fo.merge_foliage(d2, lib, ground, "t", out, chunk_ft=150, log=lambda *_: None)
nitems = len(d2.items)
check("merge: draw calls = chunks", rep["after"]["draw_calls"] == rep["chunks"] and rep["chunks"] <= 12, rep["chunks"])
check("merge: far fewer draw calls", rep["after"]["draw_calls"] * 5 < rep["before"]["draw_calls"], (rep["after"], rep["before"]))
check("merge keeps all instances", rep["after"]["instances"] == nitems)
check("merge triangles equal the sum", rep["after"]["triangles"] == rep["before"]["triangles"])
ids_in_files = sorted(i for e in fdoc["files"] for i in e["ids"])
check("every id lands in exactly one chunk", ids_in_files == sorted(d2.items))
e0 = fdoc["files"][0]
nodes, g = wm.read_glb(os.path.join(out, e0["file"]))
check("chunk GLB is one mesh one primitive", len(g["meshes"]) == 1 and len(g["meshes"][0]["primitives"]) == 1)
check("atlas material is alpha-cut", g["materials"][0].get("alphaMode") == "MASK")
check("texture uri resolves", os.path.exists(os.path.normpath(os.path.join(out, "models", "foliage", g["images"][0]["uri"]))))
check("placements entries are push-ready", all(e["tile"]["width"] > 0 and e["sha256"] and e["lods"][0]["lod"] == 0 for e in fdoc["files"]) and fdoc["format"] == "varrenmoor-world-placements")
V = nodes[0][2].V
check("chunk vertices are metres in the pack frame", V[:, 2].min() > -5 and V[:, 2].max() < 60)
fdoc2, rep2 = fo.merge_foliage(d2, lib, ground, "t", os.path.join(tmp, "opt2"), chunk_ft=150, budget=rep["after"]["triangles"] // 3, log=lambda *_: None)
check("budget thins to the cap", rep2["after"]["triangles"] <= rep["after"]["triangles"] // 3 and rep2["after"]["dropped_by_budget"] > 0, rep2["after"])
check("hand-placed survive thinning", any(hand["id"] in e["ids"] for e in fdoc2["files"]))
fdoc3, rep3 = fo.merge_foliage(d2, lib, ground, "t", os.path.join(tmp, "opt3"), chunk_ft=150, impostor_beyond_ft=120, focus=(0, 0), log=lambda *_: None)
check("impostor ring cuts triangles", rep3["after"]["triangles"] < rep["after"]["triangles"] * 0.8, (rep3["after"]["triangles"], rep["after"]["triangles"]))
check("lod files exist", all(os.path.exists(os.path.join(out, l["file"])) for e in fdoc["files"] for l in e["lods"]))


class V2:
    page, x0, y0, x1, y1, k = (17, 11), 0, 0, 600, 400, 0.5

    def px(self, p):
        return (36 + p[0] * 0.5, 36 + p[1] * 0.5)


n = fo.draw_svg(d2, lib, os.path.join(tmp, "f.svg"), V2())
svg = open(os.path.join(tmp, "f.svg"), encoding="utf-8").read()
check("2D symbols carry entity ids on the DETAILS - Foliage layer", n == len(d2.items) and "DETAILS - Foliage" in svg and sorted(d2.items)[0].replace("_", "_x5F_") in svg)
png = fo.preview_png(d2, lib, env, os.path.join(tmp, "p.png"), max_px=300)
check("preview png written", os.path.getsize(png) > 1000)
import glob
stale = [sp["id"] for f in glob.glob(os.path.join(fm.PRESETS, "*.json")) for sp in json.load(open(f)).get("species", []) if sp.get("tris") != [lib.tris(sp["id"], l) for l in (0, 1, 2)]]
check("preset tris tables match the generators (run foliage.py presets-sync)", not stale, stale)
shutil.rmtree(tmp, ignore_errors=True)
print("\n%d failed" % len(fails) if fails else "\nall foliage tests passed")
sys.exit(1 if fails else 0)
