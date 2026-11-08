"""Foliage: climate species mixes with the imported (third-party) species, LOD sanity and the triangle budget report (python test_foliage_mix.py)."""
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import foliage as fo  # noqa: E402
import foliage_mesh as fm  # noqa: E402
import worldpack as wp  # noqa: E402

lib = fm.FoliageLibrary()


class ClimateMix(unittest.TestCase):
    def test_temperate_gets_broadleaf_imports_cold_does_not(self):
        t = dict(lib.climate_mix("temperate"))
        self.assertIn("beech_bw", t)
        self.assertIn("ash_bw", t)
        self.assertIn("bush_bw1", t)
        c = dict(lib.climate_mix("cold"))
        self.assertFalse(any(k.endswith("_bw") or k.endswith("_bw1") or k.endswith("_bw3") for k in c))
        d = dict(lib.climate_mix("dry"))
        self.assertIn("bush_bw1", d)
        self.assertNotIn("beech_bw", d)
        self.assertNotIn("ash_bw", d)

    def test_base_mix_is_kept_and_shares_are_small(self):
        base = lib.mixes["oak_beech_wood"]
        mix = lib.climate_mix("temperate")
        for sp, w in base:
            self.assertIn((sp, w), [tuple(m) for m in mix])
        tot = sum(w for _, w in base)
        extra = sum(w for s, w in mix if s.endswith(("_bw", "_bw1", "_bw3")))
        self.assertLess(extra / tot, 0.4)
        self.assertGreater(extra / tot, 0.05)
        beech = dict(mix)["beech_bw"]
        self.assertLess(beech / tot, 0.05)                                   # the 30k-triangle hero stays rare

    def test_without_third_party_files_the_mix_is_the_procedural_one(self):
        orig = lib.imported_available
        try:
            lib.imported_available = lambda sid: False if sid.endswith(("_bw", "_bw1", "_bw3")) else True
            self.assertEqual(lib.climate_mix("temperate"), [tuple(m) for m in lib.mixes["oak_beech_wood"]])
        finally:
            lib.imported_available = orig
        self.assertEqual(lib.climate_mix("temperate", imported=False), [tuple(m) for m in lib.mixes["oak_beech_wood"]])

    def test_custom_base_and_scatter_accepts_the_mix(self):
        mix = lib.climate_mix("temperate", base=[("oak", 2), ("grass", 1)])
        self.assertEqual(mix[0], ("oak", 2))
        env = fo.Env(300, 300, np.full((62, 62), 100.0), 5.0)
        items = fo.scatter(env, lib, {"polygon": [(10, 10), (290, 10), (290, 290), (10, 290)], "mix": [{"species": s, "weight": w} for s, w in mix], "density_per_ha": 200, "seed": 3})
        self.assertTrue(items)
        self.assertTrue(any(i["species"] in dict(mix) for i in items))


class LodAndBudget(unittest.TestCase):
    def test_lod_sanity_flags_heros_and_bad_chains(self):
        w = fo.lod_sanity(lib, ["beech_bw", "oak", "spruce"])
        self.assertTrue(any("beech_bw" in x and "hero" in x for x in w), w)

        class Fake:
            species = {"x": {}}

            def tris(self, sid, lod):
                return [1000, 1200, 1300][lod]
        w2 = fo.lod_sanity(Fake(), ["x"])
        self.assertTrue(any("LOD1" in x for x in w2) and any("LOD2" in x for x in w2), w2)

    def test_procedural_lod_chains_are_monotonic(self):
        procedural = [s for s in lib.species if lib.species[s].get("gen", {}).get("type") != "glb"]
        bad = [x for x in fo.lod_sanity(lib, procedural) if "hero" not in x]
        self.assertEqual(bad, [])

    def test_triangle_report_and_merge_report(self):
        items = [{"id": f"i{k}", "species": s, "x": 20.0 + 25 * k, "y": 40.0, "z": 0, "scale": 1.0, "rot": 0.0, "variant": 0, "zone": "z", "src": "generated"}
                 for k, s in enumerate(["oak", "oak", "spruce", "beech_bw"])]
        r = fo.triangle_report(items, lib)
        self.assertEqual(r["total_tris"], 2 * lib.tris("oak") + lib.tris("spruce") + lib.tris("beech_bw"))
        self.assertEqual(r["heaviest"][0]["species"], "beech_bw")
        self.assertAlmostEqual(sum(v["share"] for v in r["per_species"].values()), 1.0, places=2)
        tmp = tempfile.mkdtemp()
        try:
            doc = fo.FoliageDoc("t", path=os.path.join(tmp, "f.json"), data={})
            for i in items:
                doc.items[i["id"]] = i
            g = fo.Ground(wp.Frame(300, 100, 90.0), np.full((22, 62), 100.0), 5.0)
            fdoc, rep = fo.merge_foliage(doc, lib, g, "t", os.path.join(tmp, "o"), chunk_ft=150, log=lambda *_: None)
            self.assertEqual(rep["triangle_report"]["total_tris"], rep["after"]["triangles"])
            self.assertTrue(any("beech_bw" in w for w in rep["lod_warnings"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
