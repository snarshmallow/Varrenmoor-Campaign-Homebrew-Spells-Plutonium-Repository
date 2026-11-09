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
  // ---- Redraw labels: chunked host calls, progress tags, per-call time limits, a stuck chunk ends the job, Cancel between chunks, document check
  {
    const sl = VB.normalize(null); sl.place = "mountain_pass_fort_town";
    const dl = Object.assign({}, VB.dirs(root.split(path.sep).join("/"), sl.place), { world: "W", panel: "P" });
    const jl = VB.jobLabels(sl, dl), lh = jl.steps.filter(s => s.t === "host").map(s => s.action), la = lh.map(a => a.action);
    const reps = lh.filter(a => a.action === "replace_layer");
    check("labels job: one replace_layer per layer group (labels first), each with a time limit, curved names deferred",
      reps.length >= 4 && reps[0].names.includes("Label Backing") && !reps[0].names.includes("Roads") && reps.every(a => a.timeout_ms > 0 && a.curved === false), JSON.stringify(reps.map(a => a.names)));
    check("labels job: preflight first, then replaces, curved, grouping, layer order", la[0] === "label_preflight" && la.indexOf("apply_curved") > la.lastIndexOf("replace_layer") &&
      la.indexOf("finalize_labels") > la.indexOf("apply_curved") && la.indexOf("order_layers") > la.indexOf("finalize_labels"), la.join());
    const ol = lh.find(a => a.action === "order_layers").groups[0];
    check("layer order list: Label Backing last (bottom) of the label layers, under every text layer", ol[ol.length - 1] === "Label Backing" && ol.indexOf("Labels - Streets") < ol.indexOf("Label Backing"), ol.join());
    check("progress tags count up: labels 1/N .. N/N", /^labels 1\/(\d+): render_world/.test(jl.steps[0].label) && jl.steps.some(s => /^labels (\d+)\/\1: /.test(s.label || "")), jl.steps.map(s => s.label).join(" | "));
    const noCut = VB.jobLabels(Object.assign(VB.normalize(null), { place: "x", labels: Object.assign(VB.normalize(null).labels, { redraw_lines: false }) }), dl);
    check("'Redraw the cut linework too' off: only the label layers are replaced", noCut.steps.filter(s => s.t === "host" && s.action.action === "replace_layer").length === 1);
    // run it without the python step against a mock host: chunk 2 never answers
    const seen = [], st2 = [];
    let n = 0;
    const rn2 = R.createRunner({ root, fs, path, spawn: () => { throw new Error("no spawn"); }, hostTimeoutMs: 60000, log() {}, setState() {}, onStatus: s => st2.push(s.step || ""),
      host: (a) => { seen.push(a.action); if (a.action === "label_preflight") return Promise.resolve({ ok: true, doc: "mountain_pass_fort_town_town.ai", items: 40, text_frames: 12 });
        if (a.action === "replace_layer" && ++n === 2) return new Promise(() => {});  // stuck forever
        return Promise.resolve({ ok: true, replaced: a.names, items: 1 }); } });
    const job2 = Object.assign({}, jl, { steps: jl.steps.slice(1).map(s => s.t === "host" && s.action.action === "replace_layer" ? Object.assign({}, s, { action: Object.assign({}, s.action, { timeout_ms: 80 }) }) : s) });
    let r2 = await rn2.run(job2);
    check("a stuck label chunk ends the job by its own time limit with a clear message", !r2.ok && /did not answer within/.test(r2.error), r2.error);
    check("nothing after the stuck chunk was sent to Illustrator", seen.filter(x => x === "replace_layer").length === 2 && !seen.includes("apply_curved") && !seen.includes("finalize_labels"), seen.join());
    check("status showed which chunk it was on", st2.some(s => /^labels \d+\/\d+: replace /.test(s)), st2.join(" | "));
    // Cancel between chunks: pressed while chunk 1 runs, the next chunk is never sent
    const seen3 = []; let rel = null;
    const rn3 = R.createRunner({ root, fs, path, spawn: () => { throw new Error("no spawn"); }, hostTimeoutMs: 60000, log() {}, setState() {},
      host: (a) => { seen3.push(a.action); if (a.action === "label_preflight") return Promise.resolve({ ok: true, doc: "m.ai", items: 1 });
        if (a.action === "replace_layer") return new Promise(res => { rel = () => res({ ok: true, replaced: a.names, items: 1 }); }); return Promise.resolve({ ok: true }); } });
    const p3 = rn3.run(Object.assign({}, jl, { steps: jl.steps.slice(1) })); await sleep(30); rn3.cancel(); rel(); const r3 = await p3;
    check("Cancel during a chunk stops the job before the next chunk", !r3.ok && r3.cancelled && seen3.filter(x => x === "replace_layer").length === 1, seen3.join());
    // document check
    check("doc check: the place's own document passes", VB.labelDocCheck("mountain_pass_fort_town", { doc: "mountain_pass_fort_town_town.ai", items: 90000 }, true).ok);
    check("doc check: sub-place matched by its last segment", VB.labelDocCheck("bridgehollow__commoners_ring", { doc: "commoners_ring.ai", items: 90000 }, true).ok);
    check("doc check: a big foreign document is refused (Redraw labels would rewrite its linework)", !VB.labelDocCheck("mountain_pass_fort_town", { doc: "bridgehollow_winter_town.ai", items: 90000 }, true).ok);
    check("doc check: small foreign doc or label-only redraw is allowed", VB.labelDocCheck("x", { doc: "y.ai", items: 100 }, true).ok && VB.labelDocCheck("x", { doc: "y.ai", items: 90000 }, false).ok);
    // the panel's label layer order == the SVG writer's (render_world.SPEC, LABELS sublayers top to bottom)
    try {
      const gen = path.join(__dirname, "../../generators").split(path.sep).join("/");
      const spec = JSON.parse(require("child_process").execFileSync("python", ["-X", "utf8", "-c", "import sys,json;sys.path.insert(0,'" + gen + "');import render_world as r;print(json.dumps([[k,[x if isinstance(x,str) else x[0] for x in v]] for k,v in r.SPEC]))"], { encoding: "utf8" }).trim().split(/\r?\n/).pop());
      const lab = spec.find(e => e[0] === "LABELS")[1];
      check("panel LABEL_LAYERS order == render_world SPEC LABELS order (backing at the bottom)", JSON.stringify(lab) === JSON.stringify(VB.LABEL_LAYERS) && lab[lab.length - 1] === "Label Backing", JSON.stringify([lab, VB.LABEL_LAYERS]));
      const top = spec.map(e => e[0]);
      check("SVG writer stacks LABELS above LINES", top.indexOf("LABELS") < top.indexOf("LINES"), top.join());
    } catch (e) { check("render_world SPEC readable from python", false, String(e.message || e).slice(0, 300)); }
    const keepOrder = VB.LAYER_ORDER;
    check("layer_order.json preset is used when it is sane", VB.applyLayerOrderPreset({ groups: [["Legend", "Labels - Streets", "Label Backing"]] }) && VB.LAYER_ORDER[0][2] === "Label Backing");
    check("a preset putting the backing above label text is refused", !VB.applyLayerOrderPreset({ x: ["Label Backing", "Labels - Streets"] }) && VB.LAYER_ORDER[0][2] === "Label Backing");
    VB.LAYER_ORDER = keepOrder;
    const hsx = fs.readFileSync(path.join(__dirname, "../jsx/host.jsx"), "utf8");
    check("host: every call runs with alerts off and restores them (no invisible modal dialog)", /function VB_run\(json\) \{\s*var vbQuiet = VB_quietBegin\(\);\s*try \{ return VB_runInner\(json\); \} finally \{ VB_quietEnd\(vbQuiet\); \}/.test(hsx));
    check("host: font lookup tries getByName before walking app.textFonts, cache survives a reload", /textFonts\.getByName\(cand\[c\]\)/.test(hsx) && /typeof VB_fontCache === "object"/.test(hsx));
    check("host: curved labels index the text frames once (no per-label rescans)", /var tidx = VB_textIndex\(doc\)/.test(hsx));
    check("host: label actions present", ["label_preflight", "apply_curved", "order_layers"].every(a => hsx.indexOf('case "' + a + '"') >= 0));
  }
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
