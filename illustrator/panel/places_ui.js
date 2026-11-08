// Places tab UI: list places, new-place wizard (form / template / plain words / pasted spec), size warning + draft toggle, generate, render preview,
// import a Foundry scene as a place. Loaded before main.js; main.js calls VBPlacesUI.init(ctx) / paint(). Logic: lib/places.js; python: place_create.py,
// place_render.py, foundry_push.py import-scene.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, sel = "";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function P() { return ctx.state().places; }
  function listPlaces() {
    var out = [], fs = ctx.fs, base = ctx.root + "/world";
    try {
      fs.readdirSync(base).forEach(function (n) {
        var pj = ctx.readJson(base + "/" + n + "/place.json", null); if (!pj) return;
        out.push({ id: n, name: pj.name || n, kind: pj.kind || "", pop: pj.population_estimate || "", by: pj.generated_by || (pj.parent ? "region" : "hand"), scene: (pj.links || {}).foundry_scene || "",
          size: pj.bounds ? Math.round(pj.bounds.width_ft) + " x " + Math.round(pj.bounds.height_ft) + " ft" : "", imported: !!pj.import });
      });
    } catch (e) { /* no world folder */ }
    return out.sort(function (a, b) { return a.id < b.id ? -1 : 1; });
  }
  function templates() {
    var out = [], dir = ctx.root + "/illustrator/presets/places";
    try { ctx.fs.readdirSync(dir).forEach(function (f) { if (/\.json$/.test(f)) { var j = ctx.readJson(dir + "/" + f, null); if (j) out.push({ key: f.replace(/\.json$/, ""), note: j._note || "", spec: j }); } }); } catch (e) { /* none */ }
    return out;
  }
  function paint() {
    if (!ctx || !$("plList")) return;
    var st = ctx.state(), L = listPlaces();
    $("plList").innerHTML = L.map(function (p) {
      return '<tr data-pl="' + esc(p.id) + '"' + (p.id === sel ? ' class="sel"' : "") + "><td>" + esc(p.id) + "</td><td>" + esc(p.name) + "</td><td>" + esc(p.kind) + (p.pop ? " " + esc(p.pop) : "") + "</td><td>" + esc(p.size) + "</td><td>" + esc(p.by + (p.imported ? " (Foundry import)" : "")) + "</td><td>" + (p.scene ? "linked" : "") + "</td></tr>";
    }).join("");
    Array.prototype.forEach.call($("plList").querySelectorAll("tr"), function (tr) { tr.addEventListener("click", function () { sel = tr.getAttribute("data-pl"); paint(); }); });
    if (!sel && L.length) sel = st.place;
    $("plSel").textContent = sel ? "Selected: " + sel + (sel === st.place ? " (current)" : "") : "Click a row to select a place";
    var T = templates();
    $("plTemplate").innerHTML = '<option value="">(choose a template)</option>' + T.map(function (t) { return '<option value="' + esc(t.key) + '" title="' + esc(t.note) + '">' + esc(t.key) + "</option>"; }).join("");
    $("plTemplate").value = P().template || "";
    var sc = ((st.foundry || {}).cache || {}).lists; sc = (sc && sc.scenes) || [];
    $("plScene").innerHTML = '<option value="">(pick a scene: Foundry tab > Refresh from Foundry)</option>' + sc.map(function (r) { return '<option value="' + esc(r.uuid) + '">' + esc(r.name) + "  " + esc(String(r.uuid).split(".").pop().slice(0, 6)) + "</option>"; }).join("");
    $("plScene").value = P().import.scene_uuid || "";
    var e = VB.placeEstimate(st); P().estimate = e;
    var el = $("plEstimate"); el.textContent = e.text + (e.problems.length ? "  PROBLEM: " + e.problems.join("; ") : ""); el.className = "note" + (e.level === "bad" ? " err" : e.level === "warn" ? " warn" : "");
    var notes = $("plNotes"); if (notes) notes.textContent = (P().notes || []).join("\n");
    var l = P().last, out = $("plOut");
    if (out) out.textContent = l ? JSON.stringify(l, null, 1).slice(0, 1500) : "";
    var img = $("plPreview"); if (img) { if (P().preview_png) { img.hidden = false; img.src = "file:///" + String(P().preview_png).replace(/\\/g, "/") + "?" + Date.now(); } else img.hidden = true; }
  }
  function after(job) {
    return function (res) {
      if (res && res.ok && job.newPlace) {
        if (ctx.switchPlace) ctx.switchPlace(job.newPlace);
        sel = job.newPlace;
      }
      paint();
    };
  }
  function run(make, opts) {
    try { var job = make(); return ctx.startJob(job, after(job)); } catch (e) { var el = $("plOut"); if (el) el.textContent = "ERROR: " + (e.message || e); ctx.showError && ctx.showError(String(e.message || e)); return null; }
  }
  var A = {
    pl_refresh: function () { paint(); },
    pl_switch: function () { if (sel && ctx.switchPlace) ctx.switchPlace(sel); },
    pl_load_template: function () {
      var T = templates().filter(function (t) { return t.key === P().template; })[0]; if (!T) return;
      VB.placeFormFromSpec(ctx.state(), T.spec); P().spec_text = ""; ctx.save(); ctx.syncInputs(); paint();
    },
    pl_from_text: function () { return run(function () { return VB.jobPlaceFromText(ctx.state()); }); },
    pl_use_pasted: function () {
      try { var o = JSON.parse(P().spec_text); VB.placeFormFromSpec(ctx.state(), o); ctx.save(); ctx.syncInputs(); paint(); } catch (e) { $("plOut").textContent = "pasted spec: " + e.message; }
    },
    pl_clear_pasted: function () { P().spec_text = ""; ctx.save(); ctx.syncInputs(); paint(); },
    pl_validate: function () { return run(function () { return VB.jobPlaceValidate(ctx.state()); }); },
    pl_generate: function () { return run(function () { return VB.jobPlaceCreate(ctx.state(), ctx.dirs(), {}); }); },
    pl_regenerate: function () { return run(function () { return VB.jobPlaceCreate(ctx.state(), ctx.dirs(), { force: true }); }); },
    pl_render: function () { if (!sel) return; return run(function () { return VB.jobPlaceRender(ctx.state(), sel, { draft: P().draft }); }); },
    pl_open_ai: function () { if (!sel) return; return run(function () { return VB.jobPlaceRender(ctx.state(), sel, { draft: P().draft, job: true }); }); },
    pl_import_scene: function () { return run(function () { return VB.jobImportScene(ctx.state(), ctx.dirs()); }); },
    pl_import_check: function () { var I = P().import; var was = I.dry_run; I.dry_run = true; var r = run(function () { return VB.jobImportScene(ctx.state(), ctx.dirs()); }); I.dry_run = was; return r; },
    pl_import_from_foundry_tab: function () {   // button in the Foundry tab: uses that tab's scene picker
      var f = ctx.state().foundry; P().import.scene_uuid = f.sceneUuid || P().import.scene_uuid; ctx.save(); ctx.syncInputs();
      return run(function () { return VB.jobImportScene(ctx.state(), ctx.dirs()); });
    }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var bind = function (id, getset) { var el = $(id); if (el) el.addEventListener("change", function () { getset(el.value); ctx.save(); paint(); }); };
    bind("plTemplate", function (v) { P().template = v; });
    bind("plScene", function (v) { P().import.scene_uuid = v; });
    ["plForm"].forEach(function (id) { var el = $(id); if (el) el.addEventListener("input", function () { setTimeout(paint, 0); }); });
    paint();
  }
  window.VBPlacesUI = { init: init, paint: paint, actions: A, listPlaces: listPlaces };
})();
