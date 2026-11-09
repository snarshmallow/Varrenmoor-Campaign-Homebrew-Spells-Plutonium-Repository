// Host watchdog: a hung Illustrator call ends the job with a clear message (timeout or Cancel), keeps refusing new requests until it really answers, and
// the Scale Apply job's step list is host-light (one replace_layer, guides unlocked/relocked around it).   node illustrator/panel/test/test_host_watchdog.js
const fs = require("fs"), path = require("path"), os = require("os");
const R = require("../lib/runner.js"), VB = require("../lib/core.js");
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const root = fs.mkdtempSync(path.join(os.tmpdir(), "vbwd-")), logs = [], statuses = [];
let release = null, calls = [];
const mk = (timeout) => R.createRunner({ root, fs, path, spawn: () => { throw new Error("no spawn"); }, hostTimeoutMs: timeout,
  host: (a) => { calls.push(a.action); return new Promise(res => { if (a.action === "fast") return res({ ok: true }); release = () => res({ ok: true, replaced: [], items: 0 }); }); },
  log: m => logs.push(m), setState() {}, onStatus: s => statuses.push(s) });
const job = (action) => ({ kind: "t", label: "t", params: {}, steps: [{ t: "host", action: { action: action }, label: "host step" }] });
(async () => {
  let rn = mk(80), r = await rn.run(job("replace_layer"));
  check("a host call that never answers ends the job with a timeout message", !r.ok && /did not answer within/.test(r.error) && /no restart is needed/.test(r.error), r.error);
  check("job is not busy but the host is still pending", !rn.isBusy() && rn.hostPending() && rn.hostPending().action === "replace_layer");
  calls = []; r = await rn.run(job("fast"));
  check("a new job is refused while Illustrator has not answered (nothing queued behind it)", !r.ok && /still busy/.test(r.error) && calls.length === 0, r.error);
  release(); await sleep(10);
  check("when Illustrator finally answers the guard clears", rn.hostPending() === null);
  r = await rn.run(job("fast")); check("the next job works without any restart", r.ok, r.error);
  rn = mk(60000); const p = rn.run(job("replace_layer")); await sleep(30);
  check("Cancel while waiting for Illustrator frees the job", rn.cancel() === true);
  r = await p; check("cancelled job reports cancel and the pending call", !r.ok && r.cancelled && /cancelled while waiting for Illustrator/.test(r.error) && !!rn.hostPending(), r.error);
  release(); await sleep(10);
  // Scale Apply job step list
  const st = VB.normalize(null); st.place = "bridgehollow"; st.scale.grid_show = false;
  const d = Object.assign({}, VB.dirs(root.split(path.sep).join("/"), "bridgehollow"), { world: "W", panel: "P" });
  const steps = VB.jobScaleApply(st, d, false).steps, hostSteps = steps.filter(s => s.t === "host");
  const acts = hostSteps.map(s => (typeof s.action === "function" ? s.action({}) : s.action).action);
  check("Scale Apply sends exactly unlock, ONE replace_layer, lock to Illustrator", JSON.stringify(acts) === '["lock_layers","replace_layer","lock_layers"]', acts.join());
  const rl = hostSteps[1].action; const names = (typeof rl === "function" ? rl({}) : rl).names;
  check("replace_layer names are only the guide layers + NOTES (never the underlay or ART layers)", names.join() === "Grid,Scale bar,North arrow,Bounds,NOTES", names.join());
  const hs = fs.readFileSync(path.join(__dirname, "../jsx/host.jsx"), "utf8"), i0 = hs.indexOf('case "replace_layer"');
  const blk = hs.slice(i0, hs.indexOf('case "lock_layers"')).split(String.fromCharCode(10)).filter(l => l.trim().indexOf("//") !== 0).join(" ");
  check("host replace_layer hides raster-heavy layers once, closes the SVG before touching the target again, no clipboard",
    /VB_hideHeavy\(/.test(blk) && /VB_restoreHeavy\(/.test(blk) && blk.indexOf("rsvg.close") < blk.indexOf("app.activeDocument = tdoc") && !/clipboard|\.copy\(|\.paste\(|selectAll|app\.redraw/.test(blk));
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
