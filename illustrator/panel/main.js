// Polls <repo>/illustrator/jobs/*.json, runs actions via ExtendScript, writes done/<id>.result.json
var fs = require("fs"), path = require("path");
var cs = new CSInterface();
var POLL_MS = 2000, busy = false, jobsDir = null;

function log(m) {
  var el = document.getElementById("log");
  el.textContent = (new Date().toLocaleTimeString() + " " + m + "\n" + el.textContent).slice(0, 4000);
}
function setStatus(s) { document.getElementById("st").textContent = s; }

function findJobsDir() {
  var ext = cs.getSystemPath(SystemPath.EXTENSION), real = ext;
  try { real = fs.realpathSync(ext); } catch (e) {}
  try { // config.json written by install.ps1: {"jobsDir": "..."}
    var c = JSON.parse(fs.readFileSync(path.join(ext, "config.json"), "utf8"));
    if (c.jobsDir) return c.jobsDir;
  } catch (e) {}
  var d = real; // symlink install: walk up to find illustrator/jobs next to panel/
  for (var i = 0; i < 6; i++) {
    var cand = path.join(d, "jobs");
    if (fs.existsSync(cand) && fs.existsSync(path.join(d, "panel"))) return cand;
    d = path.dirname(d);
  }
  return null;
}
function evalHost(fn, arg) {
  return new Promise(function (res) {
    cs.evalScript(fn + "(" + JSON.stringify(JSON.stringify(arg)) + ")", function (r) { res(r); });
  });
}
function absPath(p, root) {
  var a = path.isAbsolute(p) ? p : path.resolve(root, p);
  return a.replace(/\\/g, "/");
}
async function runJob(job, root) {
  var results = [], ok = true, actions = job.actions || [];
  for (var i = 0; i < actions.length; i++) {
    var a = JSON.parse(JSON.stringify(actions[i])), r;
    try {
      if (a.path) a.path = absPath(a.path, root);
      if (a.path && (a.action === "save_ai" || a.action === "export_png")) {
        fs.mkdirSync(path.dirname(a.path), { recursive: true });
      }
      var raw = await evalHost("VB_run", a);
      try { r = JSON.parse(raw); } catch (e) { r = { ok: false, error: "bad host reply: " + raw }; }
    } catch (e) { r = { ok: false, error: String(e) }; }
    r.action = a.action; results.push(r);
    if (!r.ok) { ok = false; if (!job.continue_on_error) break; }
  }
  return { id: job.id, ok: ok, finished: new Date().toISOString(), results: results };
}
async function tick() {
  if (busy) return;
  busy = true;
  try {
    if (!jobsDir) jobsDir = findJobsDir();
    if (!jobsDir) { setStatus("jobs dir not found"); return; }
    document.getElementById("dir").textContent = jobsDir;
    var root = path.dirname(path.dirname(jobsDir)); // jobs -> illustrator -> repo root
    var doneDir = path.join(jobsDir, "done");
    fs.mkdirSync(doneDir, { recursive: true });
    var files = fs.readdirSync(jobsDir).filter(function (f) { return /\.json$/i.test(f); }).sort();
    if (files.length) setStatus("working");
    for (var i = 0; i < files.length; i++) {
      var f = files[i], fp = path.join(jobsDir, f), id = f.replace(/\.json$/i, ""), job, res;
      try { job = JSON.parse(fs.readFileSync(fp, "utf8")); job.id = job.id || id; res = await runJob(job, root); }
      catch (e) { job = { id: id }; res = { id: id, ok: false, error: "job failed: " + e, results: [] }; }
      fs.writeFileSync(path.join(doneDir, job.id + ".result.json"), JSON.stringify(res, null, 2));
      try { fs.renameSync(fp, path.join(doneDir, id + ".json")); } catch (e) { try { fs.unlinkSync(fp); } catch (e2) {} }
      log(job.id + ": " + (res.ok ? "ok" : "FAILED"));
    }
    setStatus("idle");
  } catch (e) { setStatus("error"); log("poll error: " + e); }
  finally { busy = false; }
}
setInterval(tick, POLL_MS);
tick();
