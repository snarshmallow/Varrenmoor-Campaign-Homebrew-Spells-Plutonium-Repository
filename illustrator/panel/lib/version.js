// Panel version stamp and staleness check. CEP keeps the page it loaded until the engine restarts, so the panel records what was on disk when it loaded
// and compares that with the disk now. Pure logic: fs and path are injected (Node fs in CEP / tests, an stub in the browser harness).
(function () {
  "use strict";

  function createVersion(o) {
    var fs = o.fs, path = o.path, panelDir = String(o.panelDir).split("\\").join("/").replace(/\/+$/, ""), repoRoot = o.repoRoot ? String(o.repoRoot).split("\\").join("/").replace(/\/+$/, "") : null;
    var now = o.now || function () { return new Date(); };

    // Files whose change means "pushed code the running panel does not have": index.html, panel/*.js, lib/*.js, jsx/host.jsx, lib/command_manifest.json.
    function listFiles() {
      var out = [];
      function add(dir, re) { var names = []; try { names = fs.readdirSync(dir); } catch (e) { return; } names.forEach(function (n) { if (re.test(n)) out.push(dir + "/" + n); }); }
      add(panelDir, /^(index\.html|[^/]+\.js)$/); add(panelDir + "/lib", /\.(js|json)$/); add(panelDir + "/jsx", /\.jsx$/);
      return out;
    }
    function mtimeOf(p) { try { var s = fs.statSync(p); return s.mtimeMs !== undefined ? s.mtimeMs : (s.mtime ? +new Date(s.mtime) : 0); } catch (e) { return 0; } }
    function readText(p) { try { return String(fs.readFileSync(p, "utf8")); } catch (e) { return null; } }

    // git short hash from .git (HEAD -> loose ref -> packed-refs); handles a worktree ".git" file (gitdir: ...) and commondir. Returns "" when unknown.
    function gitHash() {
      if (!repoRoot) return "";
      var g = repoRoot + "/.git", t = readText(g);
      if (t === null && !mtimeOf(g)) return "";   // null text but present = a normal .git directory
      var gitDir = g, common = g;
      var m = t === null ? null : /^gitdir:\s*(.+)$/m.exec(t);
      if (m) {
        gitDir = m[1].trim().split("\\").join("/"); if (!path.isAbsolute(gitDir)) gitDir = path.resolve(repoRoot, gitDir).split("\\").join("/");
        var cd = readText(gitDir + "/commondir"); common = cd ? path.resolve(gitDir, cd.trim()).split("\\").join("/") : gitDir;
      }
      var head = readText(gitDir + "/HEAD"); if (head === null) return "";
      head = head.trim();
      var hex = /^[0-9a-f]{40}$/i;
      if (hex.test(head)) return head.slice(0, 7);
      var rm = /^ref:\s*(\S+)/.exec(head); if (!rm) return "";
      var ref = rm[1], v = readText(gitDir + "/" + ref) || readText(common + "/" + ref);
      if (v && hex.test(v.trim())) return v.trim().slice(0, 7);
      var packed = readText(common + "/packed-refs");
      if (packed) { var lines = packed.split(/\r?\n/); for (var i = 0; i < lines.length; i++) { var pm = /^([0-9a-f]{40})\s+(\S+)$/i.exec(lines[i]); if (pm && pm[2] === ref) return pm[1].slice(0, 7); } }
      return "";
    }

    function snapshot() {
      var files = listFiles(), max = 0, newest = "";
      files.forEach(function (f) { var t = mtimeOf(f); if (t > max) { max = t; newest = f.slice(panelDir.length + 1); } });
      return { hash: gitHash(), mtime: max, newest: newest, count: files.length };
    }
    function hhmm(d) { var p = function (n) { return (n < 10 ? "0" : "") + n; }; return p(d.getHours()) + ":" + p(d.getMinutes()); }
    var loaded = snapshot(); loaded.loadedAt = now().getTime();
    function label(s) { s = s || loaded; return "v " + (s.hash || "nogit") + (s.mtime ? " (files " + hhmm(new Date(s.mtime)) + ")" : "") + " loaded " + hhmm(new Date(loaded.loadedAt)); }
    function short(s) { s = s || loaded; return "v " + (s.hash || "nogit") + " " + hhmm(new Date(loaded.loadedAt)); }
    // stale = a panel file on disk is newer than the newest file seen at load (1 s slack for coarse mtimes). A new commit alone (other files) is not stale.
    function check() {
      var cur = snapshot();
      return { stale: cur.mtime > loaded.mtime + 1000 || cur.count !== loaded.count, loaded: loaded, current: cur };
    }
    return { loaded: loaded, snapshot: snapshot, check: check, label: label, short: short, listFiles: listFiles };
  }

  // Why a reload must not happen right now ("" = fine). s = { held, busy, label, hostPending }.
  function refusal(s) {
    if (s.held) return "a drag or paint stroke is in progress: finish it first";
    if (s.busy) return "a job is running (" + (s.label || "busy") + ")";
    if (s.hostPending) return "Illustrator is still answering a request (" + s.hostPending + ")";
    return "";
  }
  var api = { createVersion: createVersion, refusal: refusal };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.VBVersion = api;
})();
