"""Dyers Walk demo scatter + merge (writes illustrator/out/foliage/dyers_*; never touches world/)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "generators"))
import foliage as fo, foliage_mesh as fm
lib = fm.FoliageLibrary()
place = "bridgehollow__dyers_walk_local"
env = fo.Env.from_place(place)
W, H = env.width, env.height
doc = fo.FoliageDoc(place, os.path.join(HERE, "dyers_foliage.json"))
pl = lambda x0, y0, x1, y1: [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
print(fo.run_scatter(doc, env, lib, {"zone": "wood", "polygon": pl(5, 5, W - 5, 90), "mix": [{"species": s, "weight": w} for s, w in lib.mixes["northern_mixed_forest"]], "density_per_ha": 900, "pattern": "forest_edge", "edge_ft": 30, "seed": 3}))
print(fo.run_scatter(doc, env, lib, {"zone": "yards", "polygon": pl(5, 90, W - 5, H - 5), "mix": [{"species": s, "weight": w} for s, w in lib.mixes["village_green"]], "density_per_ha": 260, "seed": 4}))
print(fo.run_scatter(doc, env, lib, {"zone": "garden", "polygon": pl(5, 90, W - 5, H - 5), "mix": [{"species": s, "weight": w} for s, w in lib.mixes["garden_edge"]], "density_per_ha": 500, "seed": 5}))
print(fo.run_scatter(doc, env, lib, {"zone": "hedge", "pattern": "hedge_line", "path": [(20, 330), (120, 335), (230, 322), (290, 300)], "mix": [{"species": "hedge", "weight": 1}], "seed": 6}))
print(fo.run_scatter(doc, env, lib, {"zone": "row", "pattern": "tree_line", "path": [(8, 120), (8, 200), (10, 280)], "mix": [{"species": "birch", "weight": 1}], "seed": 7}))
for sp, x, y in (("stump", 150, 105), ("log", 168, 112), ("boulder", 215, 40)):
    fo.add_single(doc, env, lib, sp, x, y, zone="hand")
doc.save()
print(doc.stats(lib))
ground = fo.Ground.from_pack(os.path.join(fo.REPO, "world", place, "export"))
fd, rep = fo.merge_foliage(doc, lib, ground, place, os.path.join(HERE, "dyers_merged"), chunk_ft=120, impostor_beyond_ft=None)
fo.preview_png(doc, lib, env, os.path.join(HERE, "dyers_2d_preview.png"), scale_px_per_ft=4.0)
json.dump(rep, open(os.path.join(HERE, "dyers_report.json"), "w"), indent=1)
