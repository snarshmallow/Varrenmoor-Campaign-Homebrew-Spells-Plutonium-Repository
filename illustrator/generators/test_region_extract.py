"""Tests for region_extract.py on a synthetic parent (below-datum terrain). Run: python illustrator/generators/test_region_extract.py"""
import glob
import hashlib
import json
import os
import shutil
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import region_extract as rx  # noqa: E402
import worldio  # noqa: E402

SANDBOX_ID = "_region_test/zz_unit_test_child"


def wj(p, d):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(d, open(p, "w"), indent=1)


def ent(id_, kind, name, pts, **k):
    return {"id": id_, "name": name, "kind": kind, "status": "proposed", "geometry": {"type": "polygon", "points": pts}, "notes": "", "links": {}, **k}


def rect(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def make_parent(root):
    p = os.path.join(root, "par")
    wj(os.path.join(p, "place.json"), {"id": "par", "name": "Parent", "kind": "town", "status": "proposed", "bounds": {"width_ft": 1000, "height_ft": 800}, "sea_level_ft": 0.0})
    wj(os.path.join(p, "districts.json"), {"place": "par", "districts": [
        ent("dis_a", "district", "Ward A", rect(300, 200, 400, 300), label_point=[500, 350]),
        ent("fld_1", "field", "Field", rect(650, 450, 200, 150))]})
    wj(os.path.join(p, "streets.json"), {"place": "par", "streets": [
        {"id": "str_main", "name": "Main", "kind": "street", "status": "proposed", "geometry": {"type": "polyline", "points": [[100, 350], [500, 340], [900, 360]], "width_ft": 20},
         "notes": "", "links": {}},
        {"id": "str_far", "name": "Far", "kind": "lane", "status": "proposed", "geometry": {"type": "polyline", "points": [[50, 700], [900, 700]], "width_ft": 12}, "notes": "", "links": {}}]})
    wj(os.path.join(p, "water.json"), {"place": "par", "water": [ent("wat_r", "river", "River", [[200, 0], [260, 0], [260, 800], [200, 800]])]})
    blds = {"bld_in": rect(400, 250, 30, 20), "bld_edge_most": rect(690, 300, 20, 20), "bld_edge_few": rect(708, 400, 40, 20), "bld_out": rect(50, 50, 20, 20),
            "bld_inn": rect(500, 400, 40, 30)}
    for k, pts in blds.items():
        wj(os.path.join(p, "buildings", k + ".json"), ent(k, "house", f"House {k}", pts, floors=1, rooms=[{"id": "r1"}] if k == "bld_inn" else [], doors=[], elevation_ft=-5.0))
    ys, xs = np.mgrid[0:81, 0:101]
    h = (-30 + 45 * np.sin(xs / 14.0) * np.cos(ys / 11.0) + 0.05 * xs).astype(np.float32)        # about -80 .. +20 ft: below datum
    os.makedirs(os.path.join(p, "terrain"), exist_ok=True)
    np.save(os.path.join(p, "terrain", "heightmap.npy"), h)
    wj(os.path.join(p, "terrain", "terrain_meta.json"), {"size_ft": [1000, 800], "cell_ft": 10.0, "nx": 101, "ny": 81, "seed": 1, "elev_min": float(h.min()), "elev_max": float(h.max()),
                                                          "relief_ft": float(h.max() - h.min()), "units": "feet", "sea_level_ft": 0.0})
    return h


class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="vbregion_")
        cls.h = make_parent(cls.tmp)
        cls.out = os.path.join(cls.tmp, "out")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        shutil.rmtree(rx.child_dir(SANDBOX_ID), ignore_errors=True)

    def ex(self, spec=None, cid="par__a", out=None, **kw):
        kw.setdefault("margin", 20.0)
        kw.setdefault("seed", 7)
        kw.setdefault("log", lambda m: None)
        return rx.extract("par", spec or {"kind": "entity", "id": "dis_a"}, name="Ward A", root=self.tmp, out_root=out or self.out, child_id=cid, **kw)

    def load(self, cid, f):
        return json.load(open(os.path.join(rx.child_dir(cid, self.out), f)))

    def test_deterministic(self):
        self.ex(cid="d1")
        self.ex(cid="d2")
        for f in ("terrain/heightmap.npy", "streets.json", "details.json", "districts.json"):
            a = open(os.path.join(rx.child_dir("d1", self.out), f), "rb").read()
            b = open(os.path.join(rx.child_dir("d2", self.out), f), "rb").read()
            if f.endswith(".json"):
                a, b = a.replace(b'"d1"', b'"X"'), b.replace(b'"d2"', b'"X"')       # the only difference is the child id in "place"
            self.assertEqual(hashlib.sha1(a).hexdigest(), hashlib.sha1(b).hexdigest(), f)
        self.ex(cid="d3", seed=8)
        a = np.load(os.path.join(rx.child_dir("d1", self.out), "terrain/heightmap.npy"))
        b = np.load(os.path.join(rx.child_dir("d3", self.out), "terrain/heightmap.npy"))
        self.assertGreater(float(np.abs(a - b).max()), 0.05)             # another seed gives other micro-relief

    def test_entities_inside_only_and_ids(self):
        self.ex(cid="e1")
        ids = {e["id"] for e in self.load("e1", "streets.json")["streets"]}
        self.assertEqual(ids, {"str_main"})                              # str_far is nowhere near the region
        b = {os.path.basename(f)[:-5] for f in glob.glob(os.path.join(rx.child_dir("e1", self.out), "buildings", "*.json"))}
        self.assertEqual(b, {"bld_in", "bld_edge_most", "bld_inn"})       # >50% inside or centroid inside; bld_edge_few and bld_out dropped
        r = self.load("e1", "region.json")
        self.assertEqual(r["id_map"]["bld_in"], ["bld_in"])
        self.assertNotIn("bld_out", r["id_map"])
        self.assertEqual(r["interiors"], {"bld_inn": "world/par/buildings/bld_inn.json"})
        self.assertEqual(r["parent"], "par")
        self.assertIn("content_sha1", r["parent_source"])
        self.assertTrue(r["extracted_at"])
        for e in self.load("e1", "districts.json")["districts"]:
            self.assertTrue(e["region"]["parent_id"])

    def test_street_clipping_markers(self):
        self.ex(cid="s1")
        s = self.load("s1", "streets.json")["streets"][0]
        self.assertTrue(s["region"]["clipped"])
        self.assertEqual(s["region"]["continues_off_map"], {"start": True, "end": True})
        xs = [p[0] for p in s["geometry"]["points"]]
        self.assertAlmostEqual(min(xs), 280, delta=1.0)                  # region x 300 minus margin 20
        self.assertAlmostEqual(max(xs), 720, delta=1.0)
        mk = self.load("s1", "markers.json")["markers"]
        self.assertEqual(len(mk), 2)
        self.assertTrue(all(m["kind"] == "continues_off_map" for m in mk))
        left = [m for m in mk if m["id"].endswith("start")][0]
        self.assertLess(left["dir"][0], -0.9)                            # points off the left edge

    def test_water_clipped(self):
        self.ex(spec={"kind": "rect", "rect": [150, 100, 400, 400]}, cid="w1")
        w = self.load("w1", "water.json")["water"]
        self.assertEqual(w[0]["id"], "wat_r")
        self.assertTrue(w[0]["region"]["clipped"])
        ys = [p[1] for p in w[0]["geometry"]["points"]]
        self.assertAlmostEqual(min(ys), 80, delta=0.1)

    def test_terrain_matches_parent(self):
        self.ex(cid="t1", flatten_pads=False, terrain_cell=2.5)
        hf = np.load(os.path.join(rx.child_dir("t1", self.out), "terrain/heightmap.npy"))
        m = self.load("t1", "terrain/terrain_meta.json")
        self.assertEqual(m["cell_ft"], 2.5)
        self.assertEqual(m["upres_factor"], 4)
        f = m["upres_factor"]
        j0, i0 = int(m["origin_ft"][0] / 10), int(m["origin_ft"][1] / 10)
        coarse = hf[::f, ::f]
        parent = self.h[i0:i0 + coarse.shape[0], j0:j0 + coarse.shape[1]]
        self.assertLess(float(np.abs(coarse - parent).max()), 0.02)       # exact at the coarse nodes (float32 rounding only)
        detail = hf - np.kron(coarse, np.ones((f, f)))[:hf.shape[0], :hf.shape[1]]
        self.assertGreater(float(np.std(detail)), 0.0)                    # there is finer relief between the nodes
        bx = hf[:(hf.shape[0] // f) * f, :(hf.shape[1] // f) * f].reshape(hf.shape[0] // f, f, hf.shape[1] // f, f).mean((1, 3))
        self.assertLess(float(np.abs(bx - parent[:bx.shape[0], :bx.shape[1]]).mean()), 1.5)   # block-mean downsample is close too
        self.assertLess(m["elev_min"], 0.0)                              # negative elevations survive
        self.assertLessEqual(m["elev_min"], float(self.h.min()) + 5)
        self.assertEqual(self.load("t1", "region.json")["terrain"]["upres_factor"], 4)

    def test_pads_flat_and_report(self):
        self.ex(cid="p1")
        m = self.load("p1", "terrain/terrain_meta.json")
        self.assertLess(m["max_node_dev_outside_pads_ft"], 0.02)
        hf = np.load(os.path.join(rx.child_dir("p1", self.out), "terrain/heightmap.npy"))
        ox, oy = m["origin_ft"]
        c = m["cell_ft"]
        sl = hf[int((255 - oy) / c):int((265 - oy) / c) + 1, int((410 - ox) / c):int((420 - ox) / c) + 1]   # inside bld_in footprint (400..430, 250..270)
        self.assertLess(float(sl.max() - sl.min()), 0.05)

    def test_worldio_pads_frame(self):
        self.ex(cid="o1", terrain_cell=5.0, flatten_pads=False)
        h, meta = worldio.load_terrain("o1", root=self.out)
        self.assertEqual(meta["cell_ft"], 5.0)
        v = h[int(300 / 5), int(500 / 5)]                                # node at feet (500, 300) is the parent height there
        self.assertAlmostEqual(float(v), float(self.h[30, 50]), delta=0.02)
        self.assertEqual(meta["size_ft"][0], (h.shape[1] - 1) * 5.0)

    def test_scale_math_page_size(self):
        r = self.ex(spec={"kind": "rect", "rect": [100, 100, 500, 400]}, cid="m1", margin=0.0, scale=20.0, grid=5.0, terrain=False, detail="none")
        self.assertEqual(r["report"]["page_in"], [21.0, 16.0])           # 400x300 ft at 20 ft/in + 0.5 in margins
        vs = self.load("m1", "view_settings.json")
        self.assertEqual(vs["presets"]["district"]["scale_ft_per_in"], 20.0)
        self.assertEqual(vs["presets"]["district"]["grid_ft"], 5.0)
        self.assertEqual(vs["presets"]["district"]["focus"], [300.0, 250.0])
        self.assertEqual(vs["default_preset"], "district")
        r2 = self.ex(spec={"kind": "rect", "rect": [100, 100, 500, 400]}, cid="m2", margin=0.0, scale=40.0, grid=10.0, terrain=False, detail="none")
        self.assertEqual(r2["report"]["page_in"], [11.0, 8.5])           # 40 ft/in halves the page
        p = self.load("m1", "place.json")
        self.assertEqual(p["parent"]["place"], "par")
        self.assertEqual(p["window_ft"], [100.0, 100.0, 500.0, 400.0])

    def test_local_origin_shift(self):
        self.ex(cid="l1", local_origin=True)
        r = self.load("l1", "region.json")
        ox, oy = r["transform"]["origin_ft"]
        self.assertEqual((ox % 10, oy % 10), (0, 0))
        self.assertGreater(ox, 0)
        s = self.load("l1", "streets.json")["streets"][0]
        self.assertAlmostEqual(min(p[0] for p in s["geometry"]["points"]) + ox, 280, delta=1.0)
        self.assertEqual(s["id"], "str_main")                            # same stable id
        m = self.load("l1", "terrain/terrain_meta.json")
        self.assertLess(m["origin_ft"][0], 20.0)                         # crop starts next to the new local origin

    def test_detail_marked_not_canon(self):
        self.ex(cid="dt1")
        d = self.load("dt1", "details.json")
        self.assertFalse(d["canon"])
        self.assertIn("generated at district scale", d["note"])
        for k in ("doors", "roofs", "chimneys", "lots", "fences", "kerbs", "trees"):
            self.assertTrue(all(i["detail"] is True for i in d[k]), k)
        self.assertEqual({x["building"] for x in d["doors"]}, {"bld_in", "bld_edge_most", "bld_inn"})
        self.ex(cid="dt2", detail="doors,trees")
        d2 = self.load("dt2", "details.json")
        self.assertTrue(d2["doors"] and d2["trees"] and not d2["fences"])
        self.assertEqual(self.load("dt1", "buildings/bld_in.json")["doors"], [])   # canon building data is not touched by the detail pass

    def test_refresh_keeps_edits_and_sync(self):
        self.ex(cid="r1")
        cdir = rx.child_dir("r1", self.out)
        bp = os.path.join(cdir, "buildings", "bld_in.json")
        b = json.load(open(bp))
        b["name"] = "Renamed in child"
        json.dump(b, open(bp, "w"))
        add = ent("bld_child_new", "shed", "Child-only shed", rect(450, 300, 8, 8))
        json.dump(add, open(os.path.join(cdir, "buildings", "bld_child_new.json"), "w"))
        before = open(os.path.join(self.tmp, "par", "buildings", "bld_in.json"), "rb").read()
        info = rx.sync_diff("r1", self.out)[0]
        names = [d for d in info["diffs"] if d.get("attr") == "name"]
        self.assertEqual(len(names), 1)
        self.assertEqual(names[0]["parent"], "House bld_in")
        self.assertTrue(any(d.get("change", "").startswith("child-only") for d in info["diffs"]))
        self.assertEqual(open(os.path.join(self.tmp, "par", "buildings", "bld_in.json"), "rb").read(), before)   # the diff writes nothing
        pp = os.path.join(self.tmp, "par", "buildings", "bld_inn.json")
        pb = json.load(open(pp))
        pb["name"] = "Parent renamed inn"
        json.dump(pb, open(pp, "w"))
        res = rx.refresh("r1", self.out, log=lambda m: None)
        self.assertEqual(res["report"]["kept_edits"], 1)
        self.assertEqual(json.load(open(bp))["name"], "Renamed in child")                               # child edit survives
        self.assertEqual(json.load(open(os.path.join(cdir, "buildings", "bld_inn.json")))["name"], "Parent renamed inn")   # parent edit arrives
        self.assertTrue(os.path.exists(os.path.join(cdir, "buildings", "bld_child_new.json")))
        out = rx.sync_apply("r1", self.out)
        self.assertIn("buildings:bld_in", out["applied"])
        self.assertEqual(json.load(open(os.path.join(self.tmp, "par", "buildings", "bld_in.json")))["name"], "Renamed in child")

    def test_render_child_smoke(self):
        """The normal pipeline renders a child: entity ids as paths, district preset, details layers present."""
        import render_world as rw
        self.ex(cid=SANDBOX_ID, out=rx.WORLD)
        model = rw.load_place(SANDBOX_ID)
        svg = os.path.join(self.tmp, "c.svg")
        rw.render(model, "region", svg, None, {"preset": None, "scale": None, "grid": None, "page": None, "major_every": None},
                  {"enabled": True, "style": "elbow", "stroke_width": 0.4, "margin_pct": 10, "max_offset_pt": 90, "dot": True})
        t = open(svg, encoding="utf-8").read().replace("_x5F_", "_")      # lib_svg encodes ids for Illustrator
        for needle in ('id="bld_in"', 'id="str_main"', 'id="bld_in_door1"', "Details", "DETAILS - Trees", "1 in = 20 ft", 'id="region_outline"'):
            self.assertIn(needle, t, needle)
        self.assertNotIn('id="bld_out"', t)
        # detail drawing flags: auto = no lots at <=20 ft/in, trees faint and on their own layer; none = no details at all; explicit 'lots' draws them
        self.assertNotIn('class="lot', t)
        self.assertIn('class="tree-faint"', t)
        self.assertNotIn('class="tree"', t)
        for spec, lots, trees in (("none", False, False), ("lots", True, False), ("all", True, True)):
            model["_details_draw"] = spec
            rw.render(model, "region", svg, None, {"preset": None, "scale": None, "grid": None, "page": None, "major_every": None},
                      {"enabled": True, "style": "elbow", "stroke_width": 0.4, "margin_pct": 10, "max_offset_pt": 90, "dot": True})
            t2 = open(svg, encoding="utf-8").read()
            self.assertEqual('class="lot-faint"' in t2, lots, spec)
            self.assertEqual('class="tree-faint"' in t2, trees, spec)
        model["_details_draw"] = None

    def test_foundry_region_flags(self):
        import foundry_push as fp
        self.ex(cid=SANDBOX_ID, out=rx.WORLD)
        rf = fp.region_flags(SANDBOX_ID)
        self.assertEqual(rf["parent"], "par")
        self.assertEqual(len(rf["polygon_parent_ft"]), 4)
        self.assertEqual(rf["transform"]["origin_ft"], [0.0, 0.0])
        self.assertIsNone(fp.region_flags("bridgehollow"))


if __name__ == "__main__":
    unittest.main()
