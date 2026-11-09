// Version stamp / staleness / reload-refusal logic with an injected fake fs (no real disk, no git).
const path = require("path");
const { createVersion, refusal } = require("../lib/version.js");
let pass = 0, fail = 0;
const check = (n, ok, d) => { if (ok) { pass++; console.log("PASS " + n); } else { fail++; console.log("FAIL " + n + (d ? ": " + d : "")); } };
const H = "362d8b4aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", H2 = "5959636bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
function fakeFs(files) {   // files: { path: { text, mtimeMs } }
  return {
    readFileSync: p => { if (!files[p] || files[p].text === undefined) throw new Error("ENOENT " + p); return files[p].text; },
    statSync: p => { if (!files[p]) throw new Error("ENOENT " + p); return { mtimeMs: files[p].mtimeMs }; },
    readdirSync: d => { const out = Object.keys(files).filter(f => f.startsWith(d + "/") && !f.slice(d.length + 1).includes("/")).map(f => f.slice(d.length + 1)); if (!out.length) throw new Error("ENOENT " + d); return out; }
  };
}
const P = "/r/illustrator/panel";
const base = () => ({
  [P + "/index.html"]: { mtimeMs: 1000000 }, [P + "/main.js"]: { mtimeMs: 2000000 }, [P + "/lib/core.js"]: { mtimeMs: 3000000 }, [P + "/jsx/host.jsx"]: { mtimeMs: 1500000 },
  [P + "/notes.txt"]: { mtimeMs: 9999999 },
  "/r/.git": { text: "gitdir-placeholder" }
});
function mk(files, extra) { return createVersion(Object.assign({ fs: fakeFs(files), path: path.posix, panelDir: P, repoRoot: "/r", now: () => new Date(2026, 10, 9, 14, 51) }, extra || {})); }

// 1. plain repo: .git directory, HEAD -> loose ref
let f = base(); delete f["/r/.git"]; f["/r/.git/HEAD"] = { text: "ref: refs/heads/main\n" }; f["/r/.git/refs/heads/main"] = { text: H + "\n" };
f["/r/.git/x"] = { mtimeMs: 1 };   // makes /r/.git a readable path for the stub: readFileSync(.git) must fail for a directory
f["/r/.git"] = { mtimeMs: 1 };
let v = mk(f);
check("git short hash from HEAD + loose ref", v.loaded.hash === "362d8b4", v.loaded.hash);
check("newest panel file mtime, non-panel files ignored", v.loaded.mtime === 3000000 && v.loaded.newest === "lib/core.js" && v.loaded.count === 4, JSON.stringify(v.loaded));
check("label and short text", v.short() === "v 362d8b4 14:51" && /^v 362d8b4 \(files \d\d:\d\d\) loaded 14:51$/.test(v.label()), v.short() + " | " + v.label());
check("unchanged disk is not stale", v.check().stale === false);

// 2. staleness
f[P + "/main.js"].mtimeMs = 3500000;
check("newer panel file on disk is stale, names the file", v.check().stale === true && v.check().current.newest === "main.js", JSON.stringify(v.check().current));
f[P + "/main.js"].mtimeMs = 2000000; f[P + "/lib/core.js"].mtimeMs = 3000500;
check("sub-second mtime jitter is not stale", v.check().stale === false);
f[P + "/lib/new.js"] = { mtimeMs: 10 };
check("a new panel file counts as stale", v.check().stale === true);
delete f[P + "/lib/new.js"];
f["/r/.git/refs/heads/main"].text = H2;
check("a commit that touches no panel file is not stale", v.check().stale === false && v.check().current.hash === "5959636");
f[P + "/notes.txt"].mtimeMs = 99999999;
check("non-panel file change is ignored", v.check().stale === false);

// 3. packed refs, detached HEAD, worktree .git file
f = base(); f["/r/.git"] = { mtimeMs: 1 }; f["/r/.git/HEAD"] = { text: "ref: refs/heads/feat\n" }; f["/r/.git/packed-refs"] = { text: "# pack-refs\n" + H2 + " refs/heads/feat\n" + H + " refs/heads/main\n" };
check("hash from packed-refs", mk(f).loaded.hash === "5959636");
f["/r/.git/HEAD"].text = H + "\n"; check("detached HEAD hash", mk(f).loaded.hash === "362d8b4");
f = base(); f["/r/.git"] = { text: "gitdir: /r/.git/worktrees/w\n" }; f["/r/.git/worktrees/w/HEAD"] = { text: "ref: refs/heads/wt\n" }; f["/r/.git/worktrees/w/commondir"] = { text: "../..\n" }; f["/r/.git/refs/heads/wt"] = { text: H2 };
check("worktree .git file + commondir", mk(f).loaded.hash === "5959636", mk(f).loaded.hash);
f = base(); delete f["/r/.git"]; check("no git: still works, label says nogit", mk(f).loaded.hash === "" && /^v nogit/.test(mk(f).short()));
check("missing panel dir gives mtime 0 without throwing", createVersion({ fs: fakeFs({}), path: path.posix, panelDir: P, repoRoot: null }).loaded.mtime === 0);

// 4. refusal
check("idle: allowed", refusal({ held: false, busy: false, hostPending: "" }) === "");
check("job running: refused with label", /job is running \(Draw labels\)/.test(refusal({ busy: true, label: "Draw labels" })));
check("pending Illustrator call: refused", /still answering a request \(replace_layer\)/.test(refusal({ hostPending: "replace_layer" })));
check("drag in progress: refused first", /drag or paint stroke/.test(refusal({ held: true, busy: true })));
console.log(pass + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
