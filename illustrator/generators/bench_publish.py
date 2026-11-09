"""Benchmark: old per-model publish loop vs the batched publish (publish_batch.py).

  python bench_publish.py                         synthetic pack (300 small files: 235 models + 65 textures) into a temp folder
  python bench_publish.py --share <folder>        same, into <folder>/vb_bench_<pid> (e.g. a folder on the Vega share); removed afterwards
  python bench_publish.py --placements <placements.json> [--share <folder>]   the real pack instead of the synthetic one
  --skip-old                                      only time the batch (the old loop over SMB can take many minutes)

Prints one JSON line: seconds and files written per phase (old first push, old re-push, batch first push, batch re-push) and the method used.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import foundry_push as fp  # noqa: E402
import publish_batch as pb  # noqa: E402
from test_publish_batch import old_publish_glb  # noqa: E402


def synthetic(d, n_models=235, n_tex=65):
    rels = []
    for i in range(n_models):
        r = f"models/buildings/bld_{i:03d}.glb"
        p = os.path.join(d, *r.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(b"glTF" + os.urandom(4000 + 300 * (i % 50)))         # 4-19 KB
        rels.append(r)
    os.makedirs(os.path.join(d, "models", "textures"), exist_ok=True)
    for i in range(n_tex):
        with open(os.path.join(d, "models", "textures", f"mat_{i:02d}.png"), "wb") as f:
            f.write(os.urandom(20000 + 1000 * i))                          # 20-84 KB
    return d, rels


def real(pp):
    with open(pp, encoding="utf-8") as f:
        doc = json.load(f)
    return os.path.dirname(pp), sorted({e["file"] for e in doc["files"]})


def run_old(base, rels, root):
    t = time.time()
    for r in rels:
        old_publish_glb(os.path.join(base, r), r[len("models/"):], "split", "bench", root)
    return round(time.time() - t, 3)


def run_new(base, rels, root, method):
    t = time.time()
    b = fp.model_batch(root, "bench", "split")
    b.log = lambda m: None
    if method:
        b.method = method
    for r in rels:
        fp.publish_glb(os.path.join(base, r), r[len("models/"):], "split", "bench", root, batch=b)
    st = b.commit()
    return round(time.time() - t, 3), st


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--share")
    ap.add_argument("--placements")
    ap.add_argument("--skip-old", action="store_true")
    ap.add_argument("--method", choices=["robocopy", "python"])
    a = ap.parse_args(argv)
    work = tempfile.mkdtemp(prefix="vbbench_")
    dest_parent = a.share or work
    old_root, new_root = os.path.join(dest_parent, f"vb_bench_{os.getpid()}_old"), os.path.join(dest_parent, f"vb_bench_{os.getpid()}_new")
    try:
        base, rels = real(a.placements) if a.placements else synthetic(os.path.join(work, "pack"))
        ntex = len(os.listdir(os.path.join(base, "models", "textures"))) if os.path.isdir(os.path.join(base, "models", "textures")) else 0
        res = {"models": len(rels), "textures": ntex, "dest": dest_parent}
        if not a.skip_old:
            res["old_first_s"] = run_old(base, rels, old_root)
            res["old_repush_s"] = run_old(base, rels, old_root)
            res["old_files_written_per_push"] = len(rels) + len(rels) * ntex
        s1, st1 = run_new(base, rels, new_root, a.method)
        s2, st2 = run_new(base, rels, new_root, a.method)
        res.update(batch_first_s=s1, batch_first_copied=st1["files_copied"], batch_copy_s=st1["copy_seconds"], method=st1["method"],
                   batch_repush_s=s2, batch_repush_copied=st2["files_copied"], batch_repush_remote_reads=st2["remote_reads"])
        print(json.dumps(res))
    finally:
        shutil.rmtree(old_root, ignore_errors=True)
        shutil.rmtree(new_root, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
