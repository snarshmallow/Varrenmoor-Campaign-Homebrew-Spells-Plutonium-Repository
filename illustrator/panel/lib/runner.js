// Job runner: executes the steps of a job (VBCore.job*) one job at a time.
// Node side (CEP with --enable-nodejs, or plain Node for tests); every outside dependency is injectable so a mock host can drive it.
(function () {
  "use strict";

  function createRunner(o) {
    var fs = o.fs, path = o.path, spawn = o.spawn, root = o.root.replace(/\\/g, "/").replace(/\/+$/, "");
    var state = { busy: false, cancelled: false, child: null, label: "", step: "" };
    var log = o.log || function () {};
    var absPath = function (p) { return (path.isAbsolute(p) ? p : path.resolve(root, p)).replace(/\\/g, "/"); };
    var now = o.now || function () { return new Date(); };

    function parseJsonOut(text) {
      var t = String(text || "").trim();
      try { return JSON.parse(t); } catch (e) { /* fall through */ }
      var lines = t.split(/\r?\n/);
      for (var i = lines.length - 1; i >= 0; i--) { if (lines[i].charAt(0) === "{") { try { return JSON.parse(lines[i]); } catch (e2) { /* keep looking */ } } }
      var a = t.indexOf("{"), b = t.lastIndexOf("}");
      if (a >= 0 && b > a) { try { return JSON.parse(t.slice(a, b + 1)); } catch (e3) { /* none */ } }
      return null;
    }

    function execPy(script, args, onLine) {
      return new Promise(function (resolve) {
        var py = (o.getPython && o.getPython()) || "python";
        var full = ["-X", "utf8", script].concat(args);
        var out = "", err = "", child;
        try { child = spawn(py, full, { cwd: root, windowsHide: true, env: Object.assign({}, process.env, { PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" }) }); }
        catch (e) { return resolve({ code: -1, out: "", err: "cannot start " + py + ": " + e.message, spawnError: true, cmd: py, args: full }); }
        state.child = child;
        var feed = function (buf, isErr) {
          var s = String(buf);
          if (isErr) err += s; else out += s;
          if (onLine) s.split(/\r?\n/).forEach(function (l) { if (l.trim()) onLine(l, isErr); });
        };
        child.stdout && child.stdout.on("data", function (b) { feed(b, false); });
        child.stderr && child.stderr.on("data", function (b) { feed(b, true); });
        child.on("error", function (e) {
          state.child = null;
          resolve({ code: -1, out: out, err: e.code === "ENOENT" ? "python not found (" + py + "): install Python or set Settings > Python executable" : String(e.message || e), spawnError: true, cmd: py, args: full });
        });
        child.on("close", function (code) { state.child = null; resolve({ code: code, out: out, err: err, cmd: py, args: full }); });
      });
    }

    function killChild() {
      var c = state.child; if (!c) return;
      try {
        if (process.platform === "win32" && c.pid) spawn("taskkill", ["/pid", String(c.pid), "/T", "/F"], { windowsHide: true });
        else c.kill("SIGTERM");
      } catch (e) { try { c.kill(); } catch (e2) { /* gone */ } }
    }

    async function run(job) {
      if (state.busy) return { ok: false, error: "another job is running: wait or press Cancel" };
      state.busy = true; state.cancelled = false; state.label = job.label; state.step = "";
      var started = now(), rec = { kind: job.kind, label: job.label, place: o.getPlace ? o.getPlace() : null, started: started.toISOString(), params: job.params, steps: [], ok: false };
      var warnings = [], res = { ok: true };
      var ctx = {
        last: null, vars: {}, textures: o.getTextures ? o.getTextures() : [],
        readJson: function (p, dflt) { try { return JSON.parse(fs.readFileSync(absPath(p), "utf8")); } catch (e) { if (dflt !== undefined) return dflt; throw e; } },
        writeJson: function (p, data) { var a = absPath(p); fs.mkdirSync(path.dirname(a), { recursive: true }); fs.writeFileSync(a, JSON.stringify(data, null, 1) + "\n"); },
        exists: function (p) { return fs.existsSync(absPath(p)); },
        setState: function (p, v) { o.setState(p, v); },
        log: function (m) { log(m); },
        runPy: function (script, args) { return execPy(script, args, function (l) { log(l); }); },
        host: async function (action, optional) {
          var a = JSON.parse(JSON.stringify(action));
          if (a.path) a.path = absPath(a.path);
          var r = await o.host(a);
          rec.steps.push({ t: "host", action: a, result: r });
          if (!r || !r.ok) {
            var msg = "Illustrator: " + a.action + " failed: " + ((r && r.error) || "no reply");
            if (optional) { warnings.push(msg); log("WARN " + msg); return r; }
            throw new Error(msg);
          }
          if (r.warn) { warnings.push(r.warn); log("WARN " + r.warn); }
          if (a.action === "replace_layer") log("replace_layer: " + (r.replaced || []).join(", ") + " (" + r.items + " items)");
          ctx.last = r; return r;
        }
      };
      try {
        for (var i = 0; i < job.steps.length; i++) {
          var s = job.steps[i];
          if (state.cancelled) throw new Error("cancelled");
          state.step = s.label || s.t; if (o.onStatus) o.onStatus({ busy: true, label: job.label, step: state.step });
          if (s.when && !s.when(ctx)) { log("skip: " + state.step); continue; }
          if (s.t === "write") {
            ctx.writeJson(s.path, s.data); rec.steps.push({ t: "write", path: s.path, data: s.data });
          } else if (s.t === "py") {
            var args = typeof s.args === "function" ? s.args(ctx) : s.args;
            log("> python " + s.script.replace(/^.*\//, "") + " " + args.join(" "));
            var r = await execPy(s.script, args, function (l, isErr) { log((isErr ? "! " : "  ") + l); });
            rec.steps.push({ t: "py", cmd: r.cmd, args: r.args, code: r.code, stdout: r.out.slice(-4000), stderr: r.err.slice(-4000) });
            if (state.cancelled) throw new Error("cancelled");
            if (r.code !== 0) {
              var tail = (r.err || r.out).trim().split(/\r?\n/).slice(-3).join(" | ");
              throw new Error((r.spawnError ? "" : s.label + " exited with code " + r.code + ": ") + tail);
            }
            var parsed = parseJsonOut(r.out); ctx.last = parsed || r.out; ctx.lastOut = r.out;
            if (s.json) { if (!parsed) throw new Error(s.label + ": no JSON in output"); ctx.vars[s.json] = parsed; }
          } else if (s.t === "host") {
            await ctx.host(typeof s.action === "function" ? s.action(ctx) : s.action, s.optional);
          } else if (s.t === "fn") {
            await s.fn(ctx);
          } else throw new Error("unknown step type " + s.t);
        }
        (job.setState || []).forEach(function (kv) { o.setState(kv[0], kv[1]); });
        if (o.onStale) o.onStale(job.setStale || [], job.clearStale || []);
        res = { ok: true, warnings: warnings, out: ctx.lastOut || "", vars: ctx.vars };
      } catch (e) {
        res = { ok: false, error: String(e.message || e), cancelled: state.cancelled, warnings: warnings };
      }
      rec.ok = res.ok; rec.error = res.error; rec.warnings = warnings; rec.cancelled = !!res.cancelled; rec.finished = now().toISOString();
      try {
        if (o.jobsDir && !job.noLog) {   // noLog: high-frequency quiet jobs (Paint tab strokes) are not written to the jobs folder
          var dd = path.join(o.jobsDir, "done"); fs.mkdirSync(dd, { recursive: true });
          var stamp = rec.started.replace(/[-:]/g, "").replace(/\..*$/, "").replace("T", "_");
          var file = path.join(dd, "panel_" + stamp + "_" + job.kind + ".json");
          fs.writeFileSync(file, JSON.stringify(rec, null, 1) + "\n"); res.logFile = file;
        }
      } catch (e) { res.logError = String(e); }
      state.busy = false; state.child = null; state.label = "";
      if (o.onStatus) o.onStatus({ busy: false, result: res });
      return res;
    }
    return {
      run: run, execPy: execPy, parseJsonOut: parseJsonOut,
      isBusy: function () { return state.busy; },
      cancel: function () { if (!state.busy) return false; state.cancelled = true; killChild(); return true; }
    };
  }
  var api = { createRunner: createRunner };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") window.VBRunner = api;
})();
