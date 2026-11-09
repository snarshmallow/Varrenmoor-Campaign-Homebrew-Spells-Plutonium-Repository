// Export section (top of the Foundry tab): a guided export checklist (check -> pack -> split -> merge -> push) and a PUSH group with one item per thing that is pushed to
// Foundry. Logic (step order, defaults, refusal reasons, jobs) lives in lib/exportplan.js; this file draws the checklists, runs the ticked steps one after another through the
// existing job runner, and records the result per step. Loaded before main.js; main.js calls VBExportUI.init(ctx) and VBExportUI.paint() from refreshAll.
(function () {
  "use strict";
  var VB = window.VBCore, X = window.VBExportPlan, ctx = null, running = false, msgs = { export: "", push: "" }, lastCount = { at: 0, n: 0 };
  var $ = function (id) { return document.getElementById(id); };
  function S() { return ctx.state(); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  // group table: ids of the DOM pieces and the planner for each group
  var G = {
    export: { list: "exList", run: "exRun", dryAll: "exDryAll", resume: "exResume", block: "exBlock", sum: "exSummary", attr: "data-exstep", selKey: "sel", plan: function (d, a) { return X.plan(VB, S(), ctx.dirs(), facts(), { dry: d, armed: a }); }, noun: "Export" },
    push: { list: "exPushList", run: "exPushRun", dryAll: "exPushDry", resume: "exPushResume", block: "exPushBlock", sum: "exPushSummary", attr: "data-expush", selKey: "psel", plan: function (d, a) { return X.pushPlan(VB, S(), ctx.dirs(), facts(), { dry: d, armed: a }); }, noun: "Push" }
  };

  function facts() {
    var st = S(), d = ctx.dirs(), fs = ctx.fs, f = { hasTerrain: false, buildingCount: 0, packExists: false, splitExists: false, connected: null };
    try { f.hasTerrain = fs.existsSync(d.terrain + "/heightmap.npy") || fs.existsSync(d.terrain + "/terrain_meta.json"); } catch (e) { /* none */ }
    var now = Date.now();
    if (now - lastCount.at > 4000) {   // directory listing is cached a few seconds (paint runs often)
      try { lastCount.n = fs.readdirSync(d.world + "/buildings").filter(function (n) { return /\.json$/i.test(n); }).length; } catch (e) { lastCount.n = 0; }
      lastCount.at = now;
    }
    f.buildingCount = lastCount.n;
    try { f.packExists = fs.existsSync(VB.packDir(d) + "/placements.json"); f.splitExists = fs.existsSync(VB.packDir(d) + "/models"); } catch (e) { /* none */ }
    f.lights = f.packExists && X.readPackLights ? X.readPackLights(fs, VB.packDir(d) + "/placements.json") : null;   // lights precheck (cached by mtime)
    var c = $("fConn"), t = c ? String(c.textContent || "") : "";
    f.connected = /^connected/.test(t) ? true : /offline/.test(t) ? false : null;
    var lc = window.VBLimitsUI && window.VBLimitsUI.check ? window.VBLimitsUI.check() : null;   // size and performance check (lib/limits.js): notes only, never blocks
    f.limits = lc ? lc.list : null;
    return f;
  }
  function armed() { var a = $("exArm"); return !!(a && a.checked); }
  function dryNow() { return S().exp.dry !== false; }
  function ago(iso) { if (!iso) return ""; var s = Math.round((Date.now() - Date.parse(iso)) / 1000); return s < 90 ? s + " s ago" : s < 5400 ? Math.round(s / 60) + " min ago" : String(iso).replace("T", " ").slice(0, 16); }

  function statusTag(st, s) {
    var r = (st.exp.last || {})[s.id];
    if (running && r && r.status === "running") return '<span class="tag stale">running...</span>';
    if (!r) return '<span class="tag">not run</span>';
    if (r.status === "failed") return '<span class="tag stale" title="' + esc(r.error) + '">failed ' + esc(ago(r.at)) + "</span>";
    if (r.status === "skipped") return '<span class="tag" title="' + esc(r.error) + '">skipped ' + esc(ago(r.at)) + '</span> <span class="note">' + esc(r.error) + "</span>";
    return '<span class="tag" title="' + esc(r.info || "") + '">' + (r.status === "dry" ? "dry run ok " : "done ") + esc(ago(r.at)) + "</span>" + (r.info ? ' <span class="note">' + esc(r.info) + "</span>" : "");
  }

  function paintGroup(key) {
    var g = G[key], box = $(g.list); if (!box) return;
    var st = S(), dry = dryNow(), plan = g.plan(dry, armed()), html = "", failed = null;
    plan.steps.forEach(function (s) {
      var r = (st.exp.last || {})[s.id]; if (r && r.status === "failed" && !failed) failed = s;
      html += '<div class="exrow' + (s.enabled ? "" : " off") + '"><label class="chk"><input type="checkbox" ' + g.attr + '="' + s.id + '"' + (s.checked ? " checked" : "") + (running ? " disabled" : "") + "> " +
        '<b>' + esc(s.label) + "</b></label>" + (s.write ? ' <span class="tag exw" title="writes to Foundry' + (dry ? " (dry run only while Dry run is on)" : "") + '">Foundry' + (dry ? " (dry)" : " WRITE") + "</span>" : "") +
        (s.heavy ? ' <span class="tag" title="slow / memory heavy on big places">heavy</span>' : "") + " " + statusTag(st, s) +
        '<div class="note">' + esc(s.enabled ? s.note : (s.precheck ? s.precheck + " " : "") + "Disabled: " + s.reason) + "</div>" +
        (s.offerApply && !running ? '<button class="tiny" data-exslapply="1" title="Ticks Street lamps enabled on the Streetlamps tab and runs Generate with its current settings (writes the pack, not Foundry)">Apply streetlamps now (switch on with the current settings)</button>' : "") + "</div>";
    });
    box.innerHTML = html;
    var rl = X.runList(plan, ""), block = "", wr = plan.steps.filter(function (s) { return s.checked && s.write; });
    if (!dry && wr.length && !armed()) block = "Real push selected: tick \"I understand this writes to Foundry\" first, or tick Dry run.";
    else if (!rl.run.length) block = rl.skipped.length ? "Nothing can run: " + rl.skipped[0].reason : "Nothing is ticked.";
    var run = $(g.run); run.disabled = running || !!block;
    run.textContent = (key === "push" ? "Push selected" : "Run selected steps") + (dry ? " (dry run for Foundry)" : " (writes to Foundry)");
    run.className = dry ? "primary" : "primary danger";
    var sizeNote = "";   // real push with size warnings: shown before the run; the "I understand this writes to Foundry" tick is the confirmation (not blocking)
    if (!block && !dry && wr.length && window.VBLimits) { var ln = window.VBLimits.notes((facts() || {}).limits); if (ln.length) sizeNote = ln.join(" ") + " The confirmation tick above covers this; the push is not blocked."; }
    $(g.block).textContent = running ? "Running..." : (block || sizeNote);
    $(g.dryAll).disabled = running || !X.runList(g.plan(true, false), "").run.length;
    var rs = $(g.resume); rs.hidden = !failed || running; rs.textContent = failed ? "Resume from here: " + failed.label : ""; rs.setAttribute("data-from", failed ? failed.id : "");
    $(g.sum).textContent = msgs[key];
    return plan;
  }

  function paint() {
    if (!$("exList") || !ctx || !X || !S().exp) return;
    var st = S(), dry = dryNow(), plan = paintGroup("export"); paintGroup("push");
    $("exArmRow").style.display = dry ? "none" : "";
    $("exPack").disabled = running; $("exPrev").disabled = running;
    var rec = X.recommendRoofMode(lastCount.n), cur = VB.roofMode(st);
    $("exRoofHint").innerHTML = lastCount.n ? "Roof mode now <b>" + cur + "</b>. For " + lastCount.n + " buildings the docs suggest <b>" + rec + "</b>" + (cur === rec ? " (set)." : ' <button id="exRoofUse" class="tiny">Use ' + rec + "</button>") : "";
    var ru = $("exRoofUse"); if (ru) ru.onclick = function () { S().foundry.models.roofMode = rec; ctx.save(); ctx.refreshAll(); };
    $("exPreview").textContent = X.preview(VB, st, plan, facts(), "");
    // shared target: the scene list is the Foundry tab's one
    var src = $("fScene"), dst = $("exScene");
    if (src && dst && dst.getAttribute("data-h") !== src.innerHTML) { dst.innerHTML = src.innerHTML; dst.setAttribute("data-h", src.innerHTML); }
    if (dst) dst.value = st.foundry.sceneUuid || "";
    var nSc = (((st.foundry.cache || {}).lists || {}).scenes || []).length, tg = $("exSceneTag"); if (tg) { tg.textContent = nSc ? nSc + " scenes loaded" : "no scenes loaded: press Refresh"; tg.className = "tag" + (nSc ? "" : " stale"); }
    var lastS = (st.foundry.last || {}).scene_uuid; $("exLast").disabled = !lastS; $("exLast").title = lastS ? "Use " + (st.foundry.last.scene_name || "") + " (" + lastS + ")" : "No scene pushed from this panel yet";
  }

  // push-models batch-copy numbers (copy_seconds, files_copied ...) shown with the step
  function infoOf(res) { try { return X.copySummary((res && res.out) || ""); } catch (e) { return ""; } }

  async function runSteps(key, dry, from) {
    if (running) return;
    var g = G[key], st = S(), plan = g.plan(dry, !dry && armed()), rl = X.runList(plan, from || ""), i, id, step, job, res;
    if (!rl.run.length) { msgs[key] = rl.skipped.length ? "Nothing to run. " + rl.skipped[0].reason : "Nothing to run."; paint(); return; }
    running = true; st.exp.dry = dry; msgs[key] = ""; ctx.showError("");
    var done = [], t0 = Date.now(), failedId = "", infos = [];
    try {
      for (i = 0; i < rl.run.length; i++) {
        id = rl.run[i]; step = X.step(plan, id);
        X.record(st, id, "running"); $(g.sum).textContent = "Step " + (i + 1) + " of " + rl.run.length + ": " + step.label + (done.length ? "  (done: " + done.join(", ") + ")" : "");
        paint();
        var info = "", why = "";
        try {
          job = step.build();
          if (job.act) {   // 2D scene pushes live in main.js (they export the view picture first and ask their own in-panel confirm)
            var fn = ctx.acts && ctx.acts[job.act]; if (!fn) throw new Error("action " + job.act + " is not available");
            res = await fn(); if (res === null || res === undefined) { if (!dry) throw new Error("cancelled or failed: see the message above"); } res = { ok: true };
          } else res = await ctx.startJob(job);
        } catch (e) { res = { ok: false, error: String(e.message || e) }; }
        if (X.retryWithoutLights(id, res)) {   // push-scene-3d refused --with-lights on a 0-light pack before writing anything: same push without lights
          try { res = await ctx.startJob(X.dropLights(step.build())); } catch (e) { res = { ok: false, error: String(e.message || e) }; }
          if (res && res.ok) { info = "lights skipped: the pack has no lights (re-export so buildings get interior lights; the scene's lights were kept)"; }
        }
        var skipWhy = X.softSkip(id, res);
        if (skipWhy) {   // a lights step with 0 lights in the pack: skipped, not failed; nothing was written and no scene light was pruned; the run goes on
          X.record(st, id, "skipped", skipWhy); infos.push(step.id + ": " + skipWhy); ctx.showError("");
          continue;
        }
        if (!res || !res.ok) {
          why = !res ? "another job is running (wait for it, then resume)" : String(res.error || "failed");
          X.record(st, id, "failed", why); failedId = id;
          msgs[key] = "Stopped at \"" + step.label + "\" (" + (res && res.cancelled ? "cancelled" : "failed") + "): " + why + "\nEarlier steps are kept. Fix the problem and press Resume from here.";
          break;
        }
        info = info || infoOf(res); X.record(st, id, step.write && dry ? "dry" : "done"); if (info) { st.exp.last[id].info = info; infos.push(step.id + ": " + info); }
        done.push(step.id);
        if (step.write && !dry) { var a = $("exArm"); if (a) a.checked = false; }
      }
      if (!failedId) msgs[key] = (dry ? "Dry run finished" : g.noun + " finished") + ": " + done.length + " step(s) ok in " + Math.round((Date.now() - t0) / 1000) + " s (" + done.join(", ") + ")." +
        (infos.length ? "\n" + infos.join("\n") : "") +
        (rl.skipped.length ? "\nNot run: " + rl.skipped.map(function (x) { return x.id + " (" + x.reason + ")"; }).join("; ") : "") +
        (dry ? "\nNothing was written to Foundry. Untick Dry run, tick the confirmation and run again to push for real." : "\nIn Foundry press Ctrl+F5 and check the scene (PLUGIN_GUIDE: post-push tests).");
    } finally { running = false; ctx.save(); paint(); }
  }

  function setSel(key, sel) { S().exp[G[key].selKey] = sel; ctx.save(); }
  function bind() {
    ["export", "push"].forEach(function (key) {
      var g = G[key];
      $(g.list).addEventListener("change", function (e) {
        var id = e.target && e.target.getAttribute && e.target.getAttribute(g.attr); if (!id) return;
        S().exp[g.selKey][id] = !!e.target.checked; ctx.save(); paint();
      });
      $(g.list).addEventListener("click", function (e) {   // "Apply streetlamps now": an explicit click switches lamps on and runs the Streetlamps tab Generate (pack only, no Foundry)
        var b = e.target && e.target.closest && e.target.closest("[data-exslapply]"); if (!b || running) return;
        var st = S(); st.streetlamps.enabled = true; ctx.save(); if (ctx.syncInputs) ctx.syncInputs();
        if (ctx.acts && ctx.acts.sl_apply) Promise.resolve(ctx.acts.sl_apply()).then(function () { paint(); });
      });
      $(g.run).addEventListener("click", function () { runSteps(key, dryNow(), ""); });
      $(g.dryAll).addEventListener("click", function () { runSteps(key, true, ""); });
      $(g.resume).addEventListener("click", function () { runSteps(key, dryNow(), $(g.resume).getAttribute("data-from") || ""); });
    });
    $("exArm").addEventListener("change", paint);
    $("exDry").addEventListener("change", function () { $("exArm").checked = false; paint(); });
    $("exReset").addEventListener("click", function () { S().exp.sel = X.defaultSel(); S().exp.psel = X.pushDefaultSel(); S().exp.last = {}; msgs.export = ""; msgs.push = ""; ctx.save(); paint(); });
    $("exPack").addEventListener("click", function () {   // world pack only: check, export, validate (no models, no Foundry)
      if (running) return; var st = S(), keep = Object.assign({}, st.exp.sel);
      X.STEP_IDS.forEach(function (k) { st.exp.sel[k] = X.PACK_ONLY.indexOf(k) >= 0; });
      runSteps("export", true, "").then(function () { st.exp.sel = keep; ctx.save(); paint(); });
    });
    $("exPrev").addEventListener("click", function () { if (ctx.acts && ctx.acts.f_export) ctx.acts.f_export(); });   // Export view (the 2D map picture used for the Illustrator preview), no Foundry
    $("exPushAll").addEventListener("click", function () {   // everything, in the verified order; the same dry-run-first and confirmation rules apply
      if (running) return; var st = S(), keep = Object.assign({}, st.exp.psel), every = {};
      X.PUSH_IDS.forEach(function (k) { every[k] = X.PUSH_EVERYTHING.indexOf(k) >= 0; });
      if (!(st.foundry.models || {}).alsoWalls) every.walls = false;   // the walls fallback would REMOVE walls when it is off: only part of "everything" when switched on
      st.exp.psel = every;
      runSteps("push", dryNow(), "").then(function () { st.exp.psel = keep; ctx.save(); paint(); });
    });
    $("exPushEvery").addEventListener("click", function () { var every = {}; X.PUSH_IDS.forEach(function (k) { every[k] = X.PUSH_EVERYTHING.indexOf(k) >= 0; }); setSel("push", every); paint(); });
    $("exPushNone").addEventListener("click", function () { var none = {}; X.PUSH_IDS.forEach(function (k) { none[k] = false; }); setSel("push", none); paint(); });
    $("exLast").addEventListener("click", function () {
      var st = S(), l = st.foundry.last || {}; if (!l.scene_uuid) return;
      st.foundry.target = "existing"; st.foundry.sceneUuid = l.scene_uuid; ctx.save(); ctx.refreshAll();
    });
  }

  window.VBExportUI = {
    init: function (c) { ctx = c; if (!$("exList")) return; bind(); paint(); },
    paint: function () { if (ctx && !running) paint(); }
  };
  if (typeof module !== "undefined" && module.exports) module.exports = window.VBExportUI;
})();
