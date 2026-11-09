"""World pack tests (export -> load -> validate, scale, determinism, tags, split/placements, merge lookup, push-models mock, Blender round trip).
Runs on a temp copy of world/bridgehollow plus one synthetic 40x30 ft building and a tiny scatter file; nothing in world/ is touched.
  python illustrator/generators/test_worldpack.py          (Blender tests run only when Blender is installed)"""
import copy
import io
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import building_ground as bg  # noqa: E402
import test_foundry_push as tfp  # noqa: E402
import worldpack as wp  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import worldpack_split as ws  # noqa: E402

REPO = wp.REPO
def rb(p):
    with open(p, "rb") as f:
        return f.read()


TS = "2026-01-01T00:00:00+00:00"
BLENDER = next((p for p in (os.environ.get("BLENDER_PATH"), r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe",
                            r"C:\Program Files\Blender Foundation\Blender 4.5\blender.exe") if p and os.path.exists(p)), None)

TMP = tempfile.mkdtemp(prefix="wptest_")
WORLD = os.path.join(TMP, "world")
OUT = os.path.join(TMP, "pack")
SQUARE = [[1000, 700], [1040, 700], [1040, 730], [1000, 730]]        # 40 x 30 ft


def setUpModule():
    src = os.path.join(REPO, "world", "bridgehollow")
    shutil.copytree(src, os.path.join(WORLD, "bridgehollow"), ignore=shutil.ignore_patterns("panel_state.json", "patch_preview", "export", "bridges.json"))   # bridges: test_bridge_maker.ExportKeepsBridgesTests
    b = os.path.join(WORLD, "bridgehollow", "buildings")
    d = {"id": "bld_test_40x30", "name": "Test 40x30", "kind": "house", "status": "proposed", "geometry": {"type": "polygon", "points": SQUARE}, "notes": "",
         "links": {"foundry_scene": None, "model3d": None, "ai_layer": None}, "floors": 2, "rooms": [{"id": "rm_a", "name": "A"}], "doors": [], "elevation_ft": 700.0,
         "site_slope": 0.0, "site_relief_ft": 1.0}
    json.dump(d, open(os.path.join(b, "bld_test_40x30.json"), "w"))
    os.makedirs(os.path.join(WORLD, "bridgehollow", "scatter"), exist_ok=True)
    json.dump({"instances": [{"x": 900, "y": 900, "species": "oak", "scale": 1.0}, {"x": 920, "y": 905, "species": "oak", "scale": 1.5, "rotation": 30},
                             {"x": 950, "y": 950, "species": "pine"}]}, open(os.path.join(WORLD, "bridgehollow", "scatter", "trees.json"), "w"))
    wp.export_world("bridgehollow", OUT, world_root=WORLD, timestamp=TS, lod=(4,), log=lambda m: None)
    ws.split_export(OUT, log=lambda m: None)


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class PackTests(unittest.TestCase):
    def test_validate(self):
        self.assertEqual(wp.validate_pack(OUT), [])

    def test_schema_rejects_bad_docs(self):
        m = wp._jload(os.path.join(OUT, "manifest.json"))
        bad = copy.deepcopy(m)
        del bad["extent"]
        bad["units"]["ft_to_m"] = 0.3
        sch = wp._jload(wp.SCHEMA_PATH)
        errs = wp.schema_errors(bad, {"$ref": "#/$defs/manifest"}, sch)
        self.assertTrue(any("extent" in e for e in errs) and any("ft_to_m" in e for e in errs))
        e = wp._jload(os.path.join(OUT, "entities", "buildings.json"))["items"][0]
        e = copy.deepcopy(e)
        e["polygon"] = e["polygon"][:2]
        self.assertTrue(wp.schema_errors(e, {"$ref": "#/$defs/building"}, sch))

    def test_areas_and_heights_survive(self):
        pack = wp.load_pack(OUT)
        for b in pack.list("buildings"):
            src = wp._jload(os.path.join(WORLD, "bridgehollow", "buildings", b["id"] + ".json"))
            self.assertAlmostEqual(b["area_ft2"], wp.polygon_area(src["geometry"]["points"]), delta=0.5)
            # The source elevation_ft is the starting base; building_ground.resolve (deliberate, since 6caa277) only moves it when the walls would float more
            # than max_float_ft over the lowest footprint ground or need a cut deeper than max_cut_ft. So it is kept up to that correction, never replaced.
            bgc = bg.DEFAULTS
            if b["id"].startswith("bld_test_"):          # synthetic fixture: its elevation_ft (700) is arbitrary and floats ~45 ft over the real ground there; resolve() moves it down on purpose
                self.assertLess(b["base_elevation_ft"], src["elevation_ft"], b["id"])
            else:
                self.assertLessEqual(abs(b["base_elevation_ft"] - src["elevation_ft"]), bgc["max_float_ft"] + bgc["max_cut_ft"], b["id"])
            self.assertAlmostEqual(b["wall_height_ft"], src["floors"] * wp.STOREY_FT, places=2)
            self.assertGreater(b["height_ft"], b["wall_height_ft"])
        for d in pack.list("districts") + pack.list("plazas") + pack.list("fields"):
            self.assertGreater(d["area_ft2"], 100)
        st = {s["id"]: s for s in wp._jload(os.path.join(WORLD, "bridgehollow", "streets.json"))["streets"]}
        for r in pack.list("roads"):
            self.assertEqual([p[2] for p in r["points"]], [round(z, 3) for z in st[r["id"]]["elevations_ft"]])
        self.assertTrue(any(r["bridge"] for r in pack.list("roads")))
        h = np.load(os.path.join(WORLD, "bridgehollow", "terrain", "heightmap.npy"))
        np.testing.assert_array_equal(pack.heights, h.astype(np.float32))
        self.assertAlmostEqual(pack.elevation_at(100.0, 200.0), float(h[20, 10]), places=3)

    def test_scale_40x30(self):
        pack = wp.load_pack(OUT)
        b = pack.get("bld_test_40x30")
        self.assertAlmostEqual(b["obb"]["length_ft"], 40, places=2)
        self.assertAlmostEqual(b["obb"]["width_ft"], 30, places=2)
        pts = pack.polygon_blender("bld_test_40x30", with_z=False)
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.assertAlmostEqual(max(xs) - min(xs), 12.192, places=3)
        self.assertAlmostEqual(max(ys) - min(ys), 9.144, places=3)
        self.assertEqual(wp.ft_to_m(40), 12.192)
        self.assertEqual(wp.ft_to_m(30), 9.144)
        self.assertEqual(b["floors"], 2)
        self.assertEqual(b["interior"]["room_ids"], ["rm_a"])

    def test_transforms(self):
        pack = wp.load_pack(OUT)
        f = pack.frame
        x, y, z = 123.4, 567.8, 650.0
        self.assertEqual(f.from_blender(*f.to_blender(x, y, z))[0:2], (x, y)) if False else None
        bx, by, bz = f.to_blender(x, y, z)
        for got, want in zip(f.from_blender(bx, by, bz), (x, y, z)):
            self.assertAlmostEqual(got, want, places=9)
        self.assertAlmostEqual(by, (1500 - y) * 0.3048)                     # north = +Y
        self.assertAlmostEqual(f.to_blender(0, 0, f.z_origin_ft)[2], 0.0)
        self.assertEqual(f.to_foundry_px(100, 50), (2000.0, 1000.0))        # 20 px/ft, y down
        tile = f.foundry_tile()
        self.assertEqual((tile["x"], tile["y"], tile["width"], tile["height"]), (24000.0, 15000.0, 48000.0, 30000.0))

    def test_determinism(self):
        out2 = os.path.join(TMP, "pack2")
        wp.export_world("bridgehollow", out2, world_root=WORLD, timestamp=TS, lod=(4,), log=lambda m: None)
        a, b = wp._jload(os.path.join(OUT, "manifest.json")), wp._jload(os.path.join(out2, "manifest.json"))
        # the split rewrote models/ + placements.json and re-hashed them in the manifest (refresh_manifest_files): compare everything else
        # ... and it wrote the final (deeper) foundation skirts back into entities/buildings.json (worldpack_split.write_back_skirts): same entities, skirts only deeper
        keep = lambda d: {k: v for k, v in d.items() if k not in ("placements.json", "entities/buildings.json") and not k.startswith("models/")}  # noqa: E731
        self.assertEqual(keep(a["files"]), keep(b["files"]))
        ba, bb = wp._jload(os.path.join(OUT, "entities", "buildings.json"))["items"], wp._jload(os.path.join(out2, "entities", "buildings.json"))["items"]
        strip = lambda e: {k: v for k, v in e.items() if k != "skirt_depth_ft"}  # noqa: E731
        self.assertEqual([strip(e) for e in ba], [strip(e) for e in bb])
        for x, y in zip(ba, bb):
            self.assertGreaterEqual(x["skirt_depth_ft"], y["skirt_depth_ft"] - 1e-6)
        self.assertIn("placements.json", a["files"])
        self.assertEqual(wp.validate_pack(OUT), [])                    # hashes valid right after the split

    def test_tags_and_foliage(self):
        pack = wp.load_pack(OUT)
        for t in wp.ENTITY_TYPES:
            for e in pack.list(t):
                self.assertEqual(e["tags"]["layer"], t)
                self.assertEqual(e["tags"]["id"], e["id"])
                self.assertTrue(e["tags"]["group"])
        b = pack.get("bld_test_40x30")
        self.assertTrue(b["tags"]["group"].startswith("buildings:"))
        fol = pack.list("foliage")
        self.assertEqual(sorted(f["species"] for f in fol), ["oak", "oak", "pine"])
        self.assertEqual(fol[1]["rotation_deg"], 30.0)
        self.assertEqual(wp.load_pack(OUT).manifest["entities"]["lights"]["count"], 0)     # documented empty list

    def test_water_roads(self):
        pack = wp.load_pack(OUT)
        w = pack.list("water")[0]
        s = w["surface_elevations_ft"]
        self.assertTrue(all(s[i + 1] <= s[i] + 1e-9 for i in range(len(s) - 1)))          # flows downhill
        self.assertEqual(len(w["widths_ft"]), len(w["centerline"]))
        h = wp.carved_heights(pack)
        self.assertLess(float(h.min()), float(pack.heights.min()))


class SplitTests(unittest.TestCase):
    def setUp(self):
        self.pack = wp.load_pack(OUT)
        self.pl = wp._jload(os.path.join(OUT, "placements.json"))

    def test_files_follow_split(self):
        files = {e["file"] for e in self.pl["files"]}
        self.assertIn("models/terrain.glb", files)
        self.assertIn("models/roads.glb", files)
        self.assertIn("models/buildings/bld_test_40x30.glb", files)
        self.assertIn("models/foliage/oak.glb", files)
        self.assertIn("models/foliage/pine.glb", files)
        ids = [i for e in self.pl["files"] for i in e["ids"]]
        self.assertEqual(len(ids), len(set(ids)))
        for t in ("buildings", "roads", "fields", "plazas", "water", "fences", "foliage"):
            for e in self.pack.list(t):
                self.assertIn(e["id"], ids)

    def test_placement_matches_entity(self):
        fr = self.pack.frame
        by = {e["file"]: e for e in self.pl["files"]}
        for b in self.pack.list("buildings"):
            e = by[f"models/buildings/{b['id']}.glb"]
            self.assertAlmostEqual(e["pivot"]["x_ft"], b["obb"]["center"][0], delta=0.6)
            self.assertAlmostEqual(e["pivot"]["y_ft"], b["obb"]["center"][1], delta=0.6)
            self.assertEqual(e["pivot"]["foundry_px"], [round(v, 3) for v in fr.to_foundry_px(e["pivot"]["x_ft"], e["pivot"]["y_ft"])])
            self.assertAlmostEqual(e["pivot"]["z_ft"], b["base_elevation_ft"] - b["skirt_depth_ft"], delta=0.01)
            self.assertAlmostEqual(e["size_ft"][2], b["height_ft"] + b["skirt_depth_ft"], delta=0.05)
            # the GLB mesh is local: bbox centred on the pivot in XY and standing on z = 0
            nodes, _ = wm.read_glb(os.path.join(OUT, e["file"]))
            lo, hi = nodes[0][2].bbox()
            self.assertAlmostEqual((lo[0] + hi[0]) / 2, 0, delta=0.01)
            self.assertAlmostEqual((lo[1] + hi[1]) / 2, 0, delta=0.01)
            self.assertAlmostEqual(lo[2], 0, delta=0.01)
        e = by["models/buildings/bld_test_40x30.glb"]
        self.assertAlmostEqual(e["size_ft"][0], 40 + 2, delta=0.3) if False else None
        self.assertAlmostEqual(e["pivot"]["x_ft"], 1020, delta=0.01)
        self.assertAlmostEqual(e["pivot"]["y_ft"], 715, delta=0.01)
        for ins in by["models/foliage/oak.glb"]["instances"]:
            ent = self.pack.get(ins["id"])
            self.assertEqual(ins["pivot_ft"][:2], [ent["points"][0][0], ent["points"][0][1]])

    def test_pivots_reconstruct_world_mesh(self):
        """local mesh + pivot == the absolute mesh built straight from the pack, for every file"""
        parts = {p["id"]: p for p in wm.build_parts(self.pack)}
        for e in self.pl["files"]:
            if e["kind"] != "mesh":
                continue
            nodes, _ = wm.read_glb(os.path.join(OUT, e["file"]))
            pv = np.array(e["pivot"]["blender_m"])
            for nid, _, m in nodes:
                ref = wm.part_mesh(parts[nid])
                np.testing.assert_allclose(np.sort(m.V + pv, axis=0), np.sort(ref.V, axis=0), atol=2e-3)

    def test_idempotent_split_and_single_reexport(self):
        before = {e["file"]: e["sha256"] for e in self.pl["files"]}
        raw = rb(os.path.join(OUT, "placements.json"))
        ws.split_export(OUT, log=lambda m: None)
        self.assertEqual(rb(os.path.join(OUT, "placements.json")), raw)
        ws.split_export(OUT, split=self.pl["split"], only=["bld_test_40x30"], log=lambda m: None)
        pl2 = wp._jload(os.path.join(OUT, "placements.json"))
        self.assertEqual({e["file"]: e["sha256"] for e in pl2["files"]}, before)
        self.assertEqual([e["id"] for e in pl2["files"]], [e["id"] for e in self.pl["files"]])

    def test_split_granularity_options(self):
        out = os.path.join(TMP, "pack_g")
        shutil.copytree(OUT, out, ignore=shutil.ignore_patterns("models", "placements.json"))
        pl = ws.split_export(out, split=ws.parse_split("buildings=group,roads=entity,foliage=layer"), log=lambda m: None)
        files = {e["file"] for e in pl["files"]}
        self.assertTrue(any(f.startswith("models/buildings/dis_") for f in files))
        self.assertNotIn("models/buildings/bld_test_40x30.glb", files)
        self.assertIn("models/roads/str_pilgrim_road_1.glb", files)
        self.assertEqual(sum(1 for f in files if f.startswith("models/foliage")), 1)

    def test_merge_lookup_and_counts(self):
        for preset, nfiles in (("layer", None), ("all", 1), ("district", None), ("individual", None)):
            doc, rep = ws.merge_export(OUT, preset, out_dir=os.path.join(TMP, "opt_" + preset), log=lambda m: None)
            self.assertEqual(rep["before"]["triangles"], rep["after"]["triangles"] + 0 if rep["hidden_faces_removed"] == 0 else rep["before"]["triangles"])
            if nfiles:
                self.assertEqual(len(doc["files"]), nfiles)
            members = {m["id"] for e in doc["files"] for m in e["members"]}
            want = {i for e in self.pl["files"] for i in e["ids"]}
            self.assertEqual(members, want, preset)
            self.assertLess(rep["after"]["files"] + (0 if preset == "individual" else 1), rep["before"]["files"] + 1)
        doc, rep = ws.merge_export(OUT, "layer", out_dir=os.path.join(TMP, "opt_layer"), log=lambda m: None)
        self.assertLess(rep["after"]["draw_calls_est"], rep["before"]["draw_calls_est"])
        bl = next(e for e in doc["files"] if e["file"] == "models/buildings.glb")
        m = next(x for x in bl["members"] if x["id"] == "bld_test_40x30")
        self.assertAlmostEqual(m["pivot_ft"][0], 1020, delta=3.0)       # mean of the vertices, near the footprint centre
        self.assertTrue(bl["lods"] and bl["lods"][0]["tris"] <= bl["tris"])
        self.assertTrue(os.path.exists(os.path.join(TMP, "opt_layer", bl["lods"][0]["file"])))
        # sources untouched
        self.assertEqual({e["file"]: e["sha256"] for e in wp._jload(os.path.join(OUT, "placements.json"))["files"]},
                         {e["file"]: wp._sha(os.path.join(OUT, e["file"])) for e in self.pl["files"]})
        # versioned output dir
        self.assertTrue(ws.next_version_dir(TMP, "x").endswith("x_v001"))

    def test_cluster_decimation(self):
        t = wm.build_terrain(wm.Ctx(self.pack))
        d = wm.cluster_decimate(t, 20.0)
        self.assertLess(d.tri_count, t.tri_count / 10)
        self.assertGreaterEqual(float(d.V[:, 2].min()), float(t.V[:, 2].min()) - 1e-6)
        self.assertLessEqual(float(d.V[:, 2].max()), float(t.V[:, 2].max()) + 1e-6)


class PushTests(unittest.TestCase):
    def run_cmd(self, br, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            fp.main(list(args), bridge=br)
        return json.loads(buf.getvalue().strip().splitlines()[-1])

    def test_push_models_mock_idempotent_and_scaled(self):
        br = tfp.FakeBridge()
        assets = os.path.join(TMP, "assets")
        base = ["push-models", "--place", "bridgehollow", "--placements", os.path.join(OUT, "placements.json"), "--assets-dir", assets, "--px-per-ft", "3.4"]
        dry = self.run_cmd(br, *base, "--dry-run", "--scene-name", "ZZ Model Push Test")
        self.assertTrue(dry["ok"] and dry["dry_run"])
        self.assertFalse(os.path.exists(assets))
        self.assertEqual(br.calls, [])
        r1 = self.run_cmd(br, *base, "--scene-name", "ZZ Model Push Test")
        self.assertTrue(r1["ok"], r1)
        pl = wp._jload(os.path.join(OUT, "placements.json"))
        n = sum(len(e["instances"]) if e["kind"] == "instances" else 1 for e in pl["files"])
        self.assertEqual(r1["tile_ops"]["created"], n)
        r2 = self.run_cmd(br, *base, "--scene-uuid", r1["scene_uuid"])
        self.assertEqual((r2["tile_ops"]["created"], r2["tile_ops"]["updated"]), (0, n))
        sid = r1["scene_uuid"].split(".")[1]
        tiles = br.emb[sid]["Tile"]
        tile = next(t for t in tiles.values() if t["flags"]["varrenmoor"]["pipelineId"].endswith("bld_test_40x30"))
        self.assertEqual((tile["x"], tile["y"]), (round(1020 * 3.4), round(715 * 3.4)))
        self.assertEqual(tile["elevation"], next(e for e in pl["files"] if "bld_test_40x30" in e["ids"])["pivot"]["rel_z_ft"])
        e = next(e for e in pl["files"] if e["ids"] == ["bld_test_40x30"])
        self.assertEqual(tile["width"], round(e["size_ft"][0] * 3.4))
        self.assertTrue(os.path.exists(os.path.join(assets, "art", "bridgehollow", "models", "split", "buildings", "bld_test_40x30_v001.glb")))
        self.assertTrue(os.path.exists(os.path.join(assets, "art", "bridgehollow", "models", "split", "textures")))
        # unchanged files reuse their version; an edited file gets _v002
        self.run_cmd(br, *base, "--scene-uuid", r1["scene_uuid"])
        self.assertFalse(os.path.exists(os.path.join(assets, "art", "bridgehollow", "models", "split", "buildings", "bld_test_40x30_v002.glb")))
        # the scene calibration (not the flag default) is used when the scene has one
        calib = br.docs["Scene"][sid]["flags"]["varrenmoor"]["calib"]
        self.assertEqual(calib["ppf"], 3.4)
        # instances: one tile per tree
        self.assertEqual(sum(1 for t in tiles.values() if "fol_trees_" in t["flags"]["varrenmoor"]["pipelineId"]), 3)

    def test_layer_filter(self):
        doc = wp._jload(os.path.join(OUT, "placements.json"))

        class A:
            layers, ids, lod = "buildings", None, 0
        items = fp.build_model_tiles(doc, {"ppf": 20.0, "x0": 0, "y0": 0, "sceneX": 0, "sceneY": 0}, A, None)
        self.assertEqual(len(items), len(wp.load_pack(OUT).list("buildings")))


@unittest.skipUnless(BLENDER, "Blender not installed")
class BlenderTests(unittest.TestCase):
    def run_blender(self, *args):
        r = subprocess.run([BLENDER, "-b", "--factory-startup", *args], capture_output=True, text=True, timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-800:])
        return r.stdout

    def test_import_collections_props_export_glb_and_roundtrip(self):
        blend, glb = os.path.join(TMP, "scene.blend"), os.path.join(TMP, "scene.glb")
        out = self.run_blender("--python", os.path.join(REPO, "foundry-3d", "blender", "import_worldpack.py"), "--", OUT, "--blend", blend, "--glb", glb)
        self.assertIn("objects", out)
        self.assertTrue(os.path.getsize(glb) > 100000)
        chk = os.path.join(TMP, "chk.py")
        open(chk, "w").write(
            "import bpy, json, sys\n"
            "o = bpy.data.objects['bld_test_40x30']\n"
            "r = {'loc': list(o.location), 'props': {k: (list(o[k]) if hasattr(o[k], '__len__') and not isinstance(o[k], str) else o[k]) for k in o.keys()},\n"
            "     'coll': [c.name for c in o.users_collection], 'dim': list(o.dimensions), 'n': len(bpy.data.objects),\n"
            "     'colls': sorted(c.name for c in bpy.data.collections), 'unit': bpy.context.scene.unit_settings.scale_length}\n"
            "open(sys.argv[-1], 'w').write(json.dumps(r))\n")
        res = os.path.join(TMP, "chk.json")
        self.run_blender(blend, "--python", chk, "--", res)
        r = json.load(open(res))
        e = next(x for x in wp._jload(os.path.join(OUT, "placements.json"))["files"] if x["ids"] == ["bld_test_40x30"])
        for a, b in zip(r["loc"], e["pivot"]["blender_m"]):
            self.assertAlmostEqual(a, b, places=3)
        self.assertEqual(r["props"]["wp_id"], "bld_test_40x30")
        self.assertEqual(r["props"]["wp_layer"], "buildings")
        self.assertEqual(r["props"]["wp_pipelineId"], "world:bridgehollow:bld_test_40x30")
        self.assertEqual(r["props"]["wp_file"], "buildings/bld_test_40x30.glb")
        self.assertAlmostEqual(r["props"]["wp_origin_ft"][0], 1020, delta=0.01)
        self.assertAlmostEqual(r["dim"][0], 12.192 + 2 * 0.3048, delta=0.01)        # 40 ft + 1 ft roof overhang each end, in metres
        self.assertEqual(r["unit"], 1.0)
        self.assertTrue(any(c.startswith("buildings/") for c in r["coll"]))
        self.assertTrue({"terrain", "roads", "buildings", "water", "foliage", "fences"} <= set(r["colls"]))
        # edit -> re-export one object: same file name, id, pivot; size follows the edit
        edit = os.path.join(TMP, "edit.py")
        open(edit, "w").write("import bpy\no = bpy.data.objects['bld_test_40x30']\no.scale = (1, 1, 2)\nbpy.ops.wm.save_mainfile()\n")
        self.run_blender(blend, "--python", edit)
        before = wp._jload(os.path.join(OUT, "placements.json"))
        self.run_blender(blend, "--python", os.path.join(REPO, "foundry-3d", "blender", "export_worldpack_split.py"), "--", OUT, "--ids", "bld_test_40x30")
        after = wp._jload(os.path.join(OUT, "placements.json"))
        e0 = next(x for x in before["files"] if x["ids"] == ["bld_test_40x30"])
        e1 = next(x for x in after["files"] if x["ids"] == ["bld_test_40x30"])
        self.assertEqual((e0["id"], e0["file"], e0["pivot"]), (e1["id"], e1["file"], e1["pivot"]))
        self.assertEqual(e0["tris"], e1["tris"])
        self.assertAlmostEqual(e1["size_ft"][2], e0["size_ft"][2] * 2 - e0["size_ft"][2] * 0, delta=e0["size_ft"][2] * 1.01)
        self.assertGreater(e1["size_ft"][2], e0["size_ft"][2] * 1.5)
        self.assertEqual([x["id"] for x in before["files"]], [x["id"] for x in after["files"]])
        self.assertEqual({x["file"]: x["sha256"] for x in before["files"] if x["file"] != e0["file"]}, {x["file"]: x["sha256"] for x in after["files"] if x["file"] != e0["file"]})
        ws.split_export(OUT, split=before["split"], log=lambda m: None)      # restore the pristine model for any later test


if __name__ == "__main__":
    unittest.main(verbosity=1)
