"""Tests for the sign maker: the glTF models (geometry sanity, names, materials, origin, hashes), the style manifest the macro reads, the macro text substitution and the
install-sign-macro command against an in-memory bridge. No Foundry needed. Run: python illustrator/generators/test_signs.py"""
import base64
import gzip
import io
import contextlib
import json
import os
import struct
import sys
import tempfile
import unittest

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import signs  # noqa: E402
import worldpack_mesh as wm  # noqa: E402
import foundry_push as fp  # noqa: E402


def read_gltf_json(path):
    with open(path, "rb") as f:
        raw = f.read()
    n = struct.unpack_from("<I", raw, 12)[0]
    return json.loads(raw[20:20 + n])


class Models(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="signs_test_")
        cls.man = signs.write_all(cls.tmp)

    def test_every_style_has_a_file_a_hash_name_and_a_manifest(self):
        self.assertEqual(set(self.man), set(signs.STYLES))
        for k, v in self.man.items():
            self.assertTrue(os.path.exists(os.path.join(self.tmp, v["file"])), k)
            self.assertRegex(v["file"], r"^%s_[0-9a-f]{8}\.glb$" % k)
            self.assertEqual(len(v["size_m"]), 3)
            self.assertTrue(all(s > 0 for s in v["size_m"]))

    def test_models_are_deterministic(self):
        for k in signs.STYLES:
            self.assertEqual(signs.glb_bytes(k), signs.glb_bytes(k))

    def test_real_world_proportions(self):
        m = self.man
        w, d, h = m["street_post"]["size_m"]
        self.assertTrue(0.6 <= w <= 1.0, "street name boards are about 2-3 ft wide")
        self.assertTrue(2.0 <= h <= 3.0, "post about 8 ft")
        bw, bh = m["hanging_bracket"]["panels"]["VB_sign_f"]["w"], m["hanging_bracket"]["panels"]["VB_sign_f"]["h"]
        self.assertTrue(0.5 <= bw <= 0.75 and 0.35 <= bh <= 0.55, "hanging board about 2 ft x 1.5 ft")
        self.assertTrue(0.8 <= m["hanging_bracket"]["size_m"][0] <= 1.3, "wrought bracket projects about 1 m")
        self.assertLess(m["street_wall"]["size_m"][1], 0.1, "wall plaque is thin")

    def test_origin_is_the_anchor_and_base_is_zero(self):
        for k, v in self.man.items():
            lo, hi = v["bbox_min"], v["bbox_max"]
            self.assertAlmostEqual(lo[2], 0.0, places=4, msg=k)                      # lowest point at z = 0 (the tile elevation lifts it)
            self.assertLessEqual(lo[0], 0.0001, k)
            self.assertGreaterEqual(hi[0], -0.0001, k)
        # ground styles stand on the origin: the post straddles x = y = 0
        for k in ("street_post", "fingerpost_3", "hanging_post"):
            self.assertLess(self.man[k]["bbox_min"][1], 0)
            self.assertGreater(self.man[k]["bbox_max"][1], 0)
        # wall styles sit on the wall plane: plaque behind y = 0 faces -y, bracket at x = 0 projects +x
        self.assertAlmostEqual(self.man["street_wall"]["bbox_max"][1], 0.0, places=4)
        self.assertLess(self.man["hanging_bracket"]["bbox_min"][0], 0.0)
        self.assertGreater(self.man["hanging_bracket"]["bbox_max"][0], 0.9)

    def test_materials_and_panels_match_the_glb(self):
        for k, v in self.man.items():
            g = read_gltf_json(os.path.join(self.tmp, v["file"]))
            mats = {m["name"] for m in g["materials"]}
            for pm in v["panels"]:
                self.assertIn(pm, mats, f"{k}: lettering material {pm} is used by a face")
            self.assertTrue({"sign_wood", "sign_oak_dark"} & mats or {"sign_iron"} & mats, k)
            self.assertFalse(g.get("images"), "no textures in the GLB: the tile script applies them")
            for pm, pn in v["panels"].items():
                self.assertEqual(len(pn["safe"]), 4)
                self.assertTrue(0 <= pn["safe"][0] < pn["safe"][2] <= 1 and 0 <= pn["safe"][1] < pn["safe"][3] <= 1)
                self.assertTrue(64 <= min(pn["px"]) and max(pn["px"]) <= 1024)
                self.assertLess(abs(pn["px"][0] / pn["px"][1] - pn["w"] / pn["h"]), 0.06, "texture aspect equals the panel aspect (no stretched lettering)")

    def test_arms_have_both_directions(self):
        for n in (2, 3, 4):
            g = read_gltf_json(os.path.join(self.tmp, self.man[f"fingerpost_{n}"]["file"]))
            names = {nd["name"] for nd in g["nodes"]}
            for i in range(1, n + 1):
                self.assertIn(f"arm{i}", names)
                self.assertIn(f"arm{i}L", names)
            self.assertEqual(self.man[f"fingerpost_{n}"]["arms"], n)

    def test_faces_point_outward_front_is_minus_y(self):
        """Every lettering face (VB_sign_f / a<N>f) must have its normal along -y (towards the default camera); backs along +y."""
        for k in signs.STYLES:
            meshes, _, _ = signs.build_style(k)
            for name, m, _ in meshes:
                for mat, F in m.subs.items():
                    if not mat.startswith("VB_sign_"):
                        continue
                    want = -1.0 if mat.endswith("f") else 1.0
                    for a, b, c in F:
                        n = np.cross(m.V[b] - m.V[a], m.V[c] - m.V[a])
                        ln = np.linalg.norm(n)
                        if ln < 1e-12:
                            continue
                        self.assertGreater(want * n[1] / ln, 0.99, f"{k}/{name}/{mat}")

    def test_triangle_budget_is_small(self):
        for k in signs.STYLES:
            meshes, _, _ = signs.build_style(k)
            self.assertLess(sum(m.tri_count for _, m, _ in meshes), 2500, k)
            self.assertLess(len(signs.glb_bytes(k)), 60000, k)

    def test_lettering_texture_size(self):
        self.assertEqual(signs.lettering_texture_size(0.76, 0.2), (1024, 272))
        w, h = signs.lettering_texture_size(0.2, 0.76)
        self.assertGreater(h, w)
        self.assertGreaterEqual(min(signs.lettering_texture_size(5.0, 0.01)), 128)


class FakeBridge:
    def __init__(self):
        self.calls = []

    def call(self, op, **a):
        self.calls.append((op, a))
        if op == "version":
            return {"protocol": 9, "module": "0.5.2"}
        if op == "upsert_by_flag":
            return {"uuid": "Macro.abc123"}
        raise AssertionError(op)


class Installer(unittest.TestCase):
    def test_macro_source_has_data_and_is_small_enough(self):
        src = signs.macro_source()
        self.assertNotIn("/*__VB_SIGN_DATA__*/null", src)
        self.assertLess(len(src), 400000)
        marker = "const DATA = "
        i = src.index(marker) + len(marker)
        data, _ = json.JSONDecoder().raw_decode(src[i:])
        self.assertEqual(set(data["styles"]), set(signs.STYLES))
        self.assertEqual(set(data["models"]), set(signs.STYLES))
        for k, b in data["models"].items():
            self.assertEqual(gzip.decompress(base64.b64decode(b))[:4], b"glTF", k)
        self.assertEqual(set(data["textures"]), {"wood", "dark", "iron"})
        for b in data["textures"].values():
            self.assertEqual(base64.b64decode(b)[:2], b"\xff\xd8")
        self.assertIn("schemes", data["presets"])

    def run_cmd(self, br, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = fp.main(list(args), br)
        return rc, json.loads(out.getvalue().strip().splitlines()[-1])

    def test_install_is_idempotent_by_stable_id(self):
        br = FakeBridge()
        rc, r = self.run_cmd(br, "install-sign-macro")
        self.assertEqual(rc, 0, r)
        rc2, r2 = self.run_cmd(br, "install-sign-macro")
        ups = [c for c in br.calls if c[0] == "upsert_by_flag"]
        self.assertEqual(len(ups), 2)
        for _, a in ups:
            self.assertEqual(a["documentName"], "Macro")
            self.assertEqual(a["id"], "macro:sign_maker")                             # same id each time: updates in place
            self.assertEqual(a["data"]["type"], "script")
            self.assertEqual(a["data"]["scope"], "global")
            self.assertIn("isGM", a["data"]["command"])                                # GM only guard
        self.assertEqual(ups[0][1]["data"]["command"], ups[1][1]["data"]["command"])

    def test_dry_run_writes_nothing(self):
        br = FakeBridge()
        rc, r = self.run_cmd(br, "install-sign-macro", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertTrue(r["dry_run"])
        self.assertFalse([c for c in br.calls if c[0] == "upsert_by_flag"])

    def test_write_sign_models_command(self):
        with tempfile.TemporaryDirectory() as d:
            rc, r = self.run_cmd(FakeBridge(), "write-sign-models", "--out", d)
            self.assertEqual(rc, 0)
            self.assertEqual(len([f for f in os.listdir(d) if f.endswith(".glb")]), len(signs.STYLES))

    def test_styles_json_is_consistent(self):
        p = signs.load_styles_json()
        for kind, d in p["defaults"].items():
            self.assertIn(d["scheme"], p["schemes"])
            self.assertIn(d["icon"], p["icons"])
        for s in p["schemes"].values():
            for key in ("paint", "ink", "trim"):
                self.assertRegex(s[key], r"^(#[0-9a-fA-F]{6})?$")
        self.assertIn("serif", [f["name"] for f in p["fonts"]])                        # a font that always exists


if __name__ == "__main__":
    unittest.main(verbosity=1)
