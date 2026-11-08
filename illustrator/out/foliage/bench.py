"""Benchmark: ~2000-tree scatter on the Bridgehollow pack, merged vs unmerged.  python illustrator/out/foliage/bench.py"""
import json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "generators"))
import foliage as fo, foliage_mesh as fm
lib = fm.FoliageLibrary()
env = fo.Env.from_place("bridgehollow")
print("bounds", env.width, env.height)
doc = fo.FoliageDoc("bridgehollow", os.path.join(HERE, "bench_foliage.json"))
poly = [(300, 300), (env.width - 300, 300), (env.width - 300, env.height - 300), (300, env.height - 300)]
t = time.time()
r = fo.run_scatter(doc, env, lib, {"zone": "bench", "polygon": poly, "mix": lib.mixes["northern_mixed_forest"], "density_per_ha": 0, "seed": 5})
# calibrate density to ~2000 trees
area_ha = 1.0
free = fo.Polygon if False else None
import shapely.geometry as sg
ha = sg.Polygon(poly).area / fo.HA_FT2
dens = 2000 / ha * 1.9
doc = fo.FoliageDoc("bridgehollow", os.path.join(HERE, "bench_foliage.json"))
r = fo.run_scatter(doc, env, lib, {"zone": "bench", "polygon": poly, "mix": [{"species": s, "weight": w} for s, w in lib.mixes["northern_mixed_forest"]], "density_per_ha": dens, "seed": 5})
print("scatter", r["added"], "in %.1fs" % (time.time() - t), r["per_species"])
doc.save()
pack = os.path.join(fo.REPO, "world", "bridgehollow", "export")
t = time.time()
ground = fo.Ground.from_pack(pack)
print("ground %.1fs" % (time.time() - t))
res = {}
for name, kw in (("plain", {}), ("budget", {"budget": 120000}), ("impostor", {"impostor_beyond_ft": 900, "lod1_beyond_ft": 450}), ("quant", {"compress": "quant"})):
    t = time.time()
    fd, rep = fo.merge_foliage(doc, lib, ground, "bridgehollow", os.path.join(HERE, "bench_" + name), chunk_ft=200, **kw)
    res[name] = {"after": rep["after"], "chunks": rep["chunks"], "secs": round(time.time() - t, 1)}
    res["before"] = rep["before"]
json.dump(res, open(os.path.join(HERE, "bench_report.json"), "w"), indent=1)
print(json.dumps(res, indent=1))
