"""Tests for publish_batch.py (batched asset copy to the Foundry share) and its use by foundry_push push-models.   python test_publish_batch.py
Light: a few dozen small files in temp folders; a local folder stands in for the SMB share."""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import publish_batch as pb  # noqa: E402

HAS_ROBOCOPY = os.name == "nt" and shutil.which("robocopy") is not None


def old_publish_glb(src, rel, set_name, place, root):
    """The pre-batch foundry_push.publish_glb (reference for byte-identical results and for bench_publish.py)."""
    base = os.path.join(root, "art", place, "models", set_name)
    stem, ext = os.path.splitext(rel)
    d = os.path.join(base, os.path.dirname(rel))
    bn = os.path.basename(stem)
    pat = re.compile(re.escape(bn) + r"_v(\d+)" + re.escape(ext) + "$")
    have = sorted((int(m.group(1)), f) for f in (os.listdir(d) if os.path.isdir(d) else []) for m in [pat.match(f)] if m)
    with open(src, "rb") as f:
        data = f.read()
    same = False
    if have:
        with open(os.path.join(d, have[-1][1]), "rb") as f0:
            same = f0.read() == data
    if same:
        name = have[-1][1]
    else:
        name = f"{bn}_v{(have[-1][0] if have else 0) + 1:03d}{ext}"
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), "wb") as f:
            f.write(data)
    tex = os.path.join(os.path.dirname(os.path.abspath(src)), *([".."] * rel.count("/")), "textures")
    if os.path.isdir(tex):
        shutil.copytree(tex, os.path.join(base, "textures"), dirs_exist_ok=True)
    sub = os.path.dirname(rel)
    return f"assets/varrenmoor-3d/art/{place}/models/{set_name}/" + (sub + "/" if sub else "") + name


def make_pack(d, n_bld=20, n_tex=8, seed=1):
    """models/buildings/b###.glb, models/terrain.glb, models/textures/t##.png (+ a nested folder). Returns the model rels (models/...)."""
    rels = []
    for i in range(n_bld):
        rels.append(f"models/buildings/b{i:03d}.glb")
    rels.append("models/terrain.glb")
    for r in rels:
        p = os.path.join(d, *r.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"glTF" + (r * (7 + seed)).encode() + os.urandom(64))
    for i in range(n_tex):
        p = os.path.join(d, "models", "textures", f"t{i:02d}.png")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(os.urandom(2000 + 100 * i))
    os.makedirs(os.path.join(d, "models", "textures", "sub"), exist_ok=True)
    with open(os.path.join(d, "models", "textures", "sub", "n.png"), "wb") as f:
        f.write(os.urandom(500))
    return rels


def tree(root, skip_manifest=True):
    out = {}
    for r, _, files in os.walk(root):
        for fn in files:
            if skip_manifest and fn in (pb.MANIFEST,):
                continue
            p = os.path.join(r, fn)
            with open(p, "rb") as f:
                out[os.path.relpath(p, root).replace(os.sep, "/")] = f.read()
    return out


def publish_all(pack, rels, root, method="python", dry=False):
    b = fp.model_batch(root, "pl", "split", dry)
    b.method = method
    paths = [fp.publish_glb(os.path.join(pack, r), r[len("models/"):], "split", "pl", root, dry, batch=b) for r in rels]
    return paths, b.commit()


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="vbpub_")
        self.pack = os.path.join(self.tmp, "pack")
        self.rels = make_pack(self.pack)
        self.share = os.path.join(self.tmp, "share")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_same_result_as_old_per_file_loop(self):
        old_root = os.path.join(self.tmp, "old")
        old = [old_publish_glb(os.path.join(self.pack, r), r[len("models/"):], "split", "pl", old_root) for r in self.rels]
        new, st = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(old, new)
        self.assertEqual(tree(old_root), tree(self.share))
        self.assertEqual(st["files_copied"], len(self.rels) + 9)        # models + 8 textures + the nested one
        self.assertTrue(os.path.isfile(os.path.join(self.share, "art", "pl", "models", "split", pb.MANIFEST)))

    def test_second_run_copies_nothing_reads_nothing_writes_nothing(self):
        publish_all(self.pack, self.rels, self.share)
        before = {p: os.stat(os.path.join(self.share, p)).st_mtime_ns for p in tree(self.share, False)}
        t = time.time()
        paths, st = publish_all(self.pack, self.rels, self.share)
        dt = time.time() - t
        self.assertEqual((st["files_copied"], st["bytes"], st["remote_reads"]), (0, 0, 0))
        self.assertEqual(st["files_skipped"], len(self.rels) + 9)
        self.assertTrue(all(p.endswith("_v001.glb") for p in paths))
        self.assertEqual(before, {p: os.stat(os.path.join(self.share, p)).st_mtime_ns for p in tree(self.share, False)})   # manifest untouched too
        self.assertLess(dt, 2.0)

    def test_only_changed_files_are_copied(self):
        publish_all(self.pack, self.rels, self.share)
        with open(os.path.join(self.pack, "models", "buildings", "b003.glb"), "ab") as f:
            f.write(b"edit")
        with open(os.path.join(self.pack, "models", "textures", "t02.png"), "wb") as f:
            f.write(os.urandom(2200))                                # same size as before, other bytes
        paths, st = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(st["files_copied"], 2)
        self.assertIn("assets/varrenmoor-3d/art/pl/models/split/buildings/b003_v002.glb", paths)
        self.assertEqual(sum(p.endswith("_v002.glb") for p in paths), 1)
        with open(os.path.join(self.pack, "models", "textures", "t02.png"), "rb") as a, \
                open(os.path.join(self.share, "art", "pl", "models", "split", "textures", "t02.png"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        _, st3 = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(st3["files_copied"], 0)

    def test_partial_destination_is_completed(self):
        old_root = os.path.join(self.tmp, "old")
        for r in self.rels:
            old_publish_glb(os.path.join(self.pack, r), r[len("models/"):], "split", "pl", old_root)
        publish_all(self.pack, self.rels, self.share)
        base = os.path.join(self.share, "art", "pl", "models", "split")
        os.remove(os.path.join(base, "textures", "t05.png"))
        os.remove(os.path.join(base, "textures", "sub", "n.png"))
        os.remove(os.path.join(base, "buildings", "b007_v001.glb"))
        _, st = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(st["files_copied"], 3)
        self.assertEqual(tree(old_root), tree(self.share))

    def test_files_from_the_old_code_are_adopted_without_rewrite(self):
        """A share filled by the old per-file loop (no manifest): read once to learn the hashes, nothing re-copied, then no more reads."""
        for r in self.rels:
            old_publish_glb(os.path.join(self.pack, r), r[len("models/"):], "split", "pl", self.share)
        _, st = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(st["files_copied"], 0)
        self.assertEqual(st["remote_reads"], len(self.rels) + 9)
        _, st2 = publish_all(self.pack, self.rels, self.share)
        self.assertEqual((st2["files_copied"], st2["remote_reads"]), (0, 0))

    def test_same_size_tamper_on_the_share_is_detected(self):
        publish_all(self.pack, self.rels, self.share)
        p = os.path.join(self.share, "art", "pl", "models", "split", "textures", "t01.png")
        size = os.path.getsize(p)
        with open(p, "wb") as f:
            f.write(b"x" * size)
        os.utime(p, ns=(time.time_ns(), time.time_ns() + 5_000_000_000))      # mtime differs from the manifest
        _, st = publish_all(self.pack, self.rels, self.share)
        self.assertEqual(st["files_copied"], 1)
        with open(p, "rb") as f, open(os.path.join(self.pack, "models", "textures", "t01.png"), "rb") as s:
            self.assertEqual(f.read(), s.read())

    def test_dry_run_copies_nothing(self):
        paths, st = publish_all(self.pack, self.rels, self.share, dry=True)
        self.assertFalse(os.path.exists(self.share))
        self.assertEqual((st["files_copied"], st["bytes"], st["would_copy"]), (0, 0, len(self.rels) + 9))
        self.assertTrue(all(p.endswith("_v001.glb") for p in paths))
        publish_all(self.pack, self.rels, self.share)
        with open(os.path.join(self.pack, "models", "terrain.glb"), "ab") as f:
            f.write(b"!")
        before = tree(self.share, False)
        paths, st = publish_all(self.pack, self.rels, self.share, dry=True)
        self.assertEqual(before, tree(self.share, False))
        self.assertEqual(st["would_copy"], 1)
        self.assertIn("assets/varrenmoor-3d/art/pl/models/split/terrain_v002.glb", paths)

    @unittest.skipUnless(HAS_ROBOCOPY, "robocopy needs Windows")
    def test_robocopy_and_python_give_identical_results(self):
        a, b = os.path.join(self.tmp, "a"), os.path.join(self.tmp, "b")
        pa, sa = publish_all(self.pack, self.rels, a, "python")
        pr, sr = publish_all(self.pack, self.rels, b, "robocopy")
        self.assertEqual(sr["method"], "robocopy")
        self.assertEqual(pa, pr)
        self.assertEqual(tree(a), tree(b))
        self.assertEqual(sa["files_copied"], sr["files_copied"])
        with open(os.path.join(self.pack, "models", "buildings", "b001.glb"), "ab") as f:
            f.write(b"v2")
        _, sr2 = publish_all(self.pack, self.rels, b, "robocopy")
        self.assertEqual(sr2["files_copied"], 1)
        _, sr3 = publish_all(self.pack, self.rels, b, "robocopy")
        self.assertEqual(sr3["files_copied"], 0)

    def test_progress_lines(self):
        lines = []
        b = pb.Batch(self.share, "x", log=lines.append, method="python")
        for i in range(40):
            p = os.path.join(self.tmp, f"f{i}.bin")
            with open(p, "wb") as f:
                f.write(os.urandom(10))
            b.add(p, f"x/f{i}.bin")
        b.commit()
        prog = [ln for ln in lines if "%)" in ln]
        self.assertEqual(len(prog), 10)
        self.assertTrue(prog[-1].endswith("(100%)"))

    def test_batch_publish_helper(self):
        pairs = [(os.path.join(self.pack, *r.split("/")), "flat/" + r) for r in self.rels]
        st = pb.batch_publish(pairs, self.share, "flat", method="python")
        self.assertEqual(st["files_copied"], len(pairs))
        self.assertEqual(pb.batch_publish(pairs, self.share, "flat", method="python")["files_copied"], 0)


class PushModelsBatchTests(unittest.TestCase):
    def run_cmd(self, br, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = fp.main(list(args), bridge=br)
        return json.loads(buf.getvalue().strip().splitlines()[-1]), buf.getvalue()

    def test_push_models_reports_timing_and_second_push_copies_nothing(self):
        import test_foundry_push as tfp
        import tile_rotation_inspect as tri
        tri.build()
        pl = os.path.join(tri.OUT, "placements.json")
        tmp = tempfile.mkdtemp(prefix="vbpub_")
        try:
            assets = os.path.join(tmp, "assets")
            base = ["push-models", "--placements", pl, "--set-name", "t", "--assets-dir", assets]
            br = tfp.FakeBridge()
            d, _ = self.run_cmd(br, *base, "--scene-name", "ZZ Batch", "--dry-run")
            self.assertTrue(d["ok"], d)
            self.assertFalse(os.path.exists(assets))
            self.assertGreater(d["publish"]["would_copy"], 0)
            r1, log = self.run_cmd(br, *base, "--scene-name", "ZZ Batch")
            self.assertTrue(r1["ok"], r1)
            for k in ("copy_seconds", "files_copied", "files_skipped", "bytes"):
                self.assertIn(k, r1)
            self.assertEqual(r1["files_copied"], d["publish"]["would_copy"])
            self.assertIn("(100%)", log)
            r2, _ = self.run_cmd(br, *base, "--scene-uuid", r1["scene_uuid"])
            self.assertTrue(r2["ok"], r2)
            self.assertEqual((r2["files_copied"], r2["publish"]["remote_reads"]), (0, 0))
            self.assertEqual(r2["tile_ops"]["created"], 0)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
