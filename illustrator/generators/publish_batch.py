"""Batched, idempotent copy of assets into the shared folder Foundry serves (assets/varrenmoor-3d = an SMB share on Vega).

Why: the old per-model loop (foundry_push.publish_glb) listed the destination folder, read the newest remote version back and then
shutil.copytree'd the WHOLE shared textures folder once per model: 155 models x 65 textures = 10,075 file copies (~4.2 GB) for a 30 MB
pack, on every push, even when nothing had changed. Over SMB that is ~0.3 files/s.

How it works (one Batch per push):
  plan    one directory listing per destination folder (os.scandir: names, sizes, mtimes in one round trip), source sha256 computed locally,
          a manifest per publish folder (<manifest_dir>/.vb_publish.json: {rel: size, mtime_ns, sha256}) read once. A destination file whose
          listed size + mtime match its manifest entry and whose sha256 equals the source is identical: skipped, never read, never rewritten.
          Unknown files (no/old manifest entry) with the same size are read once and hashed, then remembered in the manifest.
          Versioned names (<stem>_vNNN<ext>) follow the same rule as before: reuse the newest version when identical, else write N+1.
  copy    only the changed/missing files, in ONE batch: robocopy /MT:16 from a local staging tree (hardlinks or local copies laid out at their
          destination paths) on Windows, else a 16-thread shutil.copy2 pool. Progress: one log line per ~10 %.
  verify  one listing per touched folder: every planned file present with the source size (no per-file reads). Then the manifest is written
          (only when it changed).
Dry run: plans (listings only, no writes) and reports the counts.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

MANIFEST = ".vb_publish.json"
WORKERS = 16


class PublishError(Exception):
    pass


def sha256_file(path, buf=1 << 20):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(buf)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


class Listing:
    """Directory listings cached per absolute folder: {name: (size, mtime_ns)} (files only). One os.scandir per folder (on Windows the size and
    mtime come with the directory enumeration, no per-file stat)."""

    def __init__(self):
        self.dirs = {}
        self.calls = 0

    def dir(self, d):
        d = os.path.normpath(d)
        got = self.dirs.get(d)
        if got is None:
            got = {}
            self.calls += 1
            try:
                with os.scandir(d) as it:
                    for e in it:
                        try:
                            if e.is_file():
                                st = e.stat()
                                got[e.name] = (st.st_size, st.st_mtime_ns)
                        except OSError:
                            pass
            except (FileNotFoundError, NotADirectoryError):
                pass
            self.dirs[d] = got
        return got

    def get(self, path):
        return self.dir(os.path.dirname(path)).get(os.path.basename(path))

    def isfile(self, path):
        return self.get(os.path.abspath(path)) is not None

    def forget(self, d=None):
        if d is None:
            self.dirs.clear()
        else:
            self.dirs.pop(os.path.normpath(d), None)


def _ver_pat(stem, ext):
    return re.compile(re.escape(stem) + r"_v(\d+)" + re.escape(ext) + "$")


def default_method(root):
    m = os.environ.get("VB_PUBLISH_METHOD", "auto").lower()
    if m in ("python", "robocopy"):
        return m
    win_path = bool(re.match(r"^([A-Za-z]:[\\/]|\\\\)", os.path.abspath(root)))
    return "robocopy" if os.name == "nt" and win_path and shutil.which("robocopy") else "python"


class Batch:
    """Plan + one batched copy into `root`. rel paths use '/' and are relative to root. manifest_dir: the publish folder whose
    .vb_publish.json records what was written (e.g. art/<place>/models/<set>)."""

    def __init__(self, root, manifest_dir="", dry=False, log=None, method=None, workers=WORKERS, listing=None):
        self.root, self.dry, self.log = root, bool(dry), log or (lambda m: None)
        self.manifest_dir = manifest_dir.strip("/")
        self.method = method or default_method(root)
        self.workers = workers
        self.listing = listing or Listing()
        self.planned = {}          # rel -> {"src", "size", "sha", "copy": bool}
        self.ensure_dirs = set()   # rel dirs to create even when empty (copytree semantics)
        self.trees = set()         # (src_dir, dest_dir_rel) already planned
        self._ver = {}             # (src, dir_rel, stem, ext) -> rel
        self._sha = {}
        self._man = None
        self._man_dirty = False
        self.remote_reads = 0
        self.t0 = time.time()

    # ---------------------------------------------------------------- helpers
    def abs(self, rel):
        return os.path.join(self.root, *[p for p in rel.split("/") if p])

    def src_sha(self, src):
        k = os.path.abspath(src)
        if k not in self._sha:
            self._sha[k] = sha256_file(k)
        return self._sha[k]

    def manifest_path(self):
        return self.abs((self.manifest_dir + "/" if self.manifest_dir else "") + MANIFEST)

    def manifest(self):
        if self._man is None:
            self._man = {}
            p = self.manifest_path()
            if self.listing.get(p) is not None:
                try:
                    with open(p, encoding="utf-8") as f:
                        self._man = (json.load(f) or {}).get("files", {}) or {}
                except (OSError, ValueError):
                    self._man = {}
        return self._man

    def _remember(self, rel, size, mtime, sha):
        ent = {"size": size, "mtime_ns": mtime, "sha256": sha}
        if self.manifest().get(rel) != ent:
            self._man[rel] = ent
            self._man_dirty = True

    def same(self, src, rel):
        """Is the destination file `rel` byte-identical to the local `src`? Listing + manifest; reads the remote file only when unknown."""
        got = self.listing.get(self.abs(rel))
        if got is None:
            return False
        size, mtime = got
        if size != os.path.getsize(src):
            return False
        sha = self.src_sha(src)
        m = self.manifest().get(rel)
        if m and m.get("size") == size and m.get("mtime_ns") == mtime:
            return m.get("sha256") == sha
        self.remote_reads += 1
        try:
            rsha = sha256_file(self.abs(rel))
        except OSError:
            return False
        if self.manifest_dir == "" or rel.startswith(self.manifest_dir + "/"):
            self._remember(rel, size, mtime, rsha)       # learnt for next time (written with the manifest, never on a dry run)
        return rsha == sha

    # ---------------------------------------------------------------- planning
    def add(self, src, rel):
        """Fixed destination name: copy when missing or different."""
        src = os.path.abspath(src)
        old = self.planned.get(rel)
        if old:
            if old["src"] != src and self.src_sha(src) != old["sha"]:
                raise PublishError(f"two different sources for {rel}: {old['src']} and {src}")
            return rel
        self.planned[rel] = {"src": src, "size": os.path.getsize(src), "sha": self.src_sha(src), "copy": not self.same(src, rel)}
        return rel

    def add_versioned(self, src, dir_rel, stem, ext):
        """<dir_rel>/<stem>_vNNN<ext>: the newest version when identical to src, else the next version number. Returns the rel path."""
        src = os.path.abspath(src)
        key = (src, dir_rel, stem, ext)
        if key in self._ver:
            return self._ver[key]
        pat = _ver_pat(stem, ext)
        names = set(self.listing.dir(self.abs(dir_rel)))
        pref = (dir_rel.strip("/") + "/") if dir_rel.strip("/") else ""
        names |= {r[len(pref):] for r in self.planned if r.startswith(pref) and "/" not in r[len(pref):]}
        have = sorted((int(m.group(1)), f) for f in names for m in [pat.match(f)] if m)
        if have and self._same_or_planned(src, pref + have[-1][1]):
            rel = pref + have[-1][1]
        else:
            rel = pref + f"{stem}_v{(have[-1][0] if have else 0) + 1:03d}{ext}"
        self.add(src, rel)
        self._ver[key] = rel
        return rel

    def _same_or_planned(self, src, rel):
        p = self.planned.get(rel)
        if p:
            return p["sha"] == self.src_sha(src)
        return self.same(src, rel)

    def add_tree(self, src_dir, dest_dir_rel):
        """Every file under src_dir -> dest_dir_rel/<same relative path> (shutil.copytree(dirs_exist_ok=True) semantics, minus rewriting identical files)."""
        dest_dir_rel = dest_dir_rel.strip("/")
        key = (os.path.normpath(os.path.abspath(src_dir)), dest_dir_rel)
        if key in self.trees:                       # every model of a set shares one textures folder: plan it once
            return
        self.trees.add(key)
        self.ensure_dirs.add(dest_dir_rel)
        for r, dirs, files in os.walk(src_dir):
            sub = os.path.relpath(r, src_dir).replace(os.sep, "/")
            sub = "" if sub == "." else sub
            drel = dest_dir_rel + ("/" + sub if sub else "")
            self.ensure_dirs.add(drel)
            for fn in sorted(files):
                self.add(os.path.join(r, fn), drel + "/" + fn)

    # ---------------------------------------------------------------- copy
    def to_copy(self):
        return [(v["src"], rel, v["size"]) for rel, v in sorted(self.planned.items()) if v["copy"]]

    def _progress(self, done, total, last):
        if not total:
            return last
        step = min(10, done * 10 // total)
        if step > last:
            self.log(f"publish: {done}/{total} files ({step * 10}%)")
        return step

    def _copy_python(self, todo):
        for d in sorted({os.path.dirname(self.abs(rel)) for _, rel, _ in todo}):
            os.makedirs(d, exist_ok=True)
        done, last = 0, 0

        def one(job):
            src, rel, _ = job
            shutil.copy2(src, self.abs(rel))          # CopyFile2 on Windows (keeps mtime, like robocopy)
            return rel
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            for _ in ex.map(one, todo):
                done += 1
                last = self._progress(done, len(todo), last)

    def _copy_robocopy(self, todo):
        stage = tempfile.mkdtemp(prefix="vbstage_")
        try:
            n = len(todo)
            chunks = max(1, min(10, -(-n // 16)))          # ~10 % per robocopy run (progress lines), >= 16 files per run for /MT
            per = -(-n // chunks)
            dst = os.path.normpath(os.path.abspath(self.root))
            dst = dst + "." if dst.endswith(("\\", "/")) else dst        # robocopy: a trailing backslash escapes the closing quote
            done, last = 0, 0
            for ci in range(chunks):
                part = todo[ci * per:(ci + 1) * per]
                if not part:
                    continue
                sroot = os.path.join(stage, str(ci))
                for src, rel, _ in part:
                    p = os.path.join(sroot, *rel.split("/"))
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    try:
                        os.link(src, p)
                    except OSError:
                        shutil.copy2(src, p)
                cmd = ["robocopy", sroot, dst, "/E", f"/MT:{self.workers}", "/R:2", "/W:1", "/IS", "/IT", "/NFL", "/NDL", "/NP", "/NJH", "/NJS"]
                r = subprocess.run(cmd, capture_output=True)
                if r.returncode >= 8:
                    out = (r.stdout.decode("utf-8", "ignore") + r.stderr.decode("utf-8", "ignore")).strip()
                    raise PublishError(f"robocopy failed (exit {r.returncode}): {out[-400:]}")
                done += len(part)
                last = self._progress(done, n, last)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def commit(self):
        """Copy the planned changes (nothing on a dry run), verify by listing, write the manifest. Returns the stats dict."""
        plan_s = time.time() - self.t0
        todo = self.to_copy()
        nbytes = sum(s for _, _, s in todo)
        st = {"files_planned": len(self.planned), "files_copied": 0 if self.dry else len(todo), "files_skipped": len(self.planned) - len(todo),
              "bytes": 0 if self.dry else nbytes, "would_copy": len(todo), "would_copy_bytes": nbytes, "method": self.method,
              "dirs_listed": self.listing.calls, "remote_reads": self.remote_reads, "plan_seconds": round(plan_s, 3), "copy_seconds": 0.0, "dry_run": self.dry}
        if self.dry:
            if todo:
                self.log(f"publish (dry run): would copy {len(todo)} of {len(self.planned)} files ({nbytes / 1e6:.1f} MB), {st['files_skipped']} unchanged")
            return st
        t = time.time()
        for d in sorted(self.ensure_dirs):          # a handful of folders (copytree also created empty ones)
            os.makedirs(self.abs(d), exist_ok=True)
        if todo:
            self.log(f"publish: copying {len(todo)} of {len(self.planned)} files ({nbytes / 1e6:.1f} MB, {self.method}), {st['files_skipped']} unchanged")
            try:
                (self._copy_robocopy if self.method == "robocopy" else self._copy_python)(todo)
            except (PublishError, OSError) as e:
                if self.method != "robocopy":
                    raise
                self.log(f"publish: robocopy failed ({e}); copying with python threads")
                st["method"] = "robocopy+python"
                self._copy_python(todo)
        st["copy_seconds"] = round(time.time() - t, 3)
        t = time.time()
        touched = {os.path.dirname(self.abs(rel)) for _, rel, _ in todo}
        for d in touched:
            self.listing.forget(d)
        bad = []
        for rel, v in sorted(self.planned.items()):
            got = self.listing.get(self.abs(rel))
            if got is None:
                bad.append(f"{rel}: missing after copy")
            elif got[0] != v["size"]:
                bad.append(f"{rel}: {got[0]} bytes, source has {v['size']}")
            elif self.manifest_dir == "" or rel.startswith(self.manifest_dir + "/"):
                self._remember(rel, got[0], got[1], v["sha"])
        if bad:
            raise PublishError(f"{len(bad)} file(s) wrong after publishing to {self.root}: " + "; ".join(bad[:10]))
        if self._man_dirty:
            self._write_manifest()
        st["verify_seconds"] = round(time.time() - t, 3)
        st["dirs_listed"] = self.listing.calls
        st["remote_reads"] = self.remote_reads
        if todo:
            self.log(f"publish: {len(todo)} files ({nbytes / 1e6:.1f} MB) in {st['copy_seconds']:.1f} s, verified")
        return st

    def _write_manifest(self):
        p = self.manifest_path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        # drop entries of files that no longer exist (only in folders we listed anyway)
        man = {}
        for rel, ent in self._man.items():
            d = os.path.normpath(os.path.dirname(self.abs(rel)))
            if d in self.listing.dirs and os.path.basename(self.abs(rel)) not in self.listing.dirs[d]:
                continue
            man[rel] = ent
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "files": man}, f, separators=(",", ":"), sort_keys=True)
        os.replace(tmp, p)
        self._man, self._man_dirty = man, False


def batch_publish(pairs, dest_root, manifest_dir="", dry=False, log=None, method=None, workers=WORKERS):
    """Copy [(src, dest_rel)] into dest_root, skipping identical files, in one batch. Returns the stats dict (files_copied, files_skipped,
    bytes, copy_seconds, ...)."""
    b = Batch(dest_root, manifest_dir, dry=dry, log=log, method=method, workers=workers)
    for src, rel in pairs:
        b.add(src, rel)
    return b.commit()
