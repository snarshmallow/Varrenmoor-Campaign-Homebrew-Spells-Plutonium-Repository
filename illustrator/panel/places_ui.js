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
          size: pj.bounds ? Math.round(pj.bounds.width_ft) + " x " + Math.round(pj.bounds.height_ft) + " ft" : "", imported: !!pj.import, image: !!(pj.import && pj.import.source === "image") });
      });
    } catch (e) { /* no world folder */ }
    return out.sort(function (a, b) { return a.id < b.id ? -1 : 1; });
  }
  function listTrash() {   // world/.trash/<id>_<stamp>/ (place_manage.py trash); read directly so the list is there without running python
    var out = [], base = ctx.root + "/world/.trash";
    try {
      ctx.fs.readdirSync(base).forEach(function (n) {
        var info = ctx.readJson(base + "/" + n + "/.trash_info.json", null) || {}, pj = ctx.readJson(base + "/" + n + "/place.json", null) || {};
        if (!info.place && !pj.id) return;
        out.push({ entry: n, place: info.place || pj.id, name: pj.name || "", trashed: info.trashed || "" });
      });
    } catch (e) { /* no trash yet */ }
    return out.sort(function (a, b) { return a.entry < b.entry ? -1 : 1; });
  }
  // two-click arming for destructive buttons (CEP breaks window.confirm): first click arms for 6 s and relabels the button, the second runs
  var armed = { key: "", until: 0, timer: null };
  function disarm() {
    armed.key = ""; clearTimeout(armed.timer);
    [["plTrashBtn", "Move selected place to trash"], ["plPurgeBtn", "Delete permanently"]].forEach(function (b) { var el = $(b[0]); if (el) el.textContent = b[1]; });
  }
  function armOrRun(key, btnId, armText, fn) {
    if (armed.key === key && Date.now() < armed.until) { disarm(); return fn(); }
    disarm(); armed.key = key; armed.until = Date.now() + 6000;
    var el = $(btnId); if (el) el.textContent = armText;
    armed.timer = setTimeout(disarm, 6000);
    return null;
  }
  // keep the place pickers (top bar, Foundry tab) in step after rename / trash / restore / duplicate (main.js only fills them at startup)
  function syncPlaceSelects(removeId, addId) {
    ["place", "fPlace"].forEach(function (id) {
      var el = $(id); if (!el) return;
      Array.prototype.slice.call(el.options).forEach(function (o) { if (removeId && o.value === removeId) el.removeChild(o); });
      if (addId && !Array.prototype.some.call(el.options, function (o) { return o.value === addId; }) && (id === "place" || el.options.length)) { var o = document.createElement("option"); o.value = addId; o.textContent = addId; el.appendChild(o); }
    });
  }
  function manageOut(t) { var el = $("plManageOut"); if (el) el.textContent = t; }
  function runManage(op, opts) {
    opts = opts || {};
    var st = ctx.state(), place = op === "restore" || op === "purge" || op === "trash_list" ? "" : sel;
    try {
      var job = VB.jobPlaceManage(st, op, place, { dry: !!opts.dry, existing: listPlaces().map(function (p) { return p.id; }) });
      return ctx.startJob(job, function (res) {
        if (res && res.ok && !opts.dry) {
          var m = job.manage, last = P().last || {};
          if (op === "rename") { syncPlaceSelects(m.place, m.newId); sel = m.newId; P().manage.new_id = ""; }
          if (op === "trash") { syncPlaceSelects(m.place, null); sel = ""; }
          if (op === "duplicate") { syncPlaceSelects(null, job.newPlace); sel = job.newPlace; P().manage.dup_id = ""; P().manage.dup_name = ""; }
          if (op === "restore") { syncPlaceSelects(null, last.place); sel = last.place || sel; P().manage.trash_entry = ""; P().manage.restore_as = ""; }
          if (op === "purge") { P().manage.trash_entry = ""; P().manage.purge_confirm = ""; }
          ctx.save(); ctx.syncInputs && ctx.syncInputs();
        }
        manageOut(res && res.ok ? JSON.stringify(P().last, null, 1).slice(0, 2500) : "FAILED: " + ((res && res.error) || ""));
        paint();
      });
    } catch (e) { manageOut("ERROR: " + (e.message || e)); ctx.showError && ctx.showError(String(e.message || e)); return null; }
  }
  function loadEditFields() {
    if (!sel) { manageOut("select a place in the list first"); return; }
    var pj = ctx.readJson(ctx.root + "/world/" + sel + "/place.json", {}) || {}, vs = ctx.readJson(ctx.root + "/world/" + sel + "/view_settings.json", {}) || {};
    var t = ((vs.presets || {}).town) || {}, f = ((pj.view_focus || {}).town) || [];
    var M = P().manage;
    M.name = pj.name || ""; M.notes = pj.notes || ""; M.kind = pj.kind || ""; M.status = pj.status || ""; M.culture = pj.culture || ""; M.season = (pj.defaults || {}).season || "";
    M.units = pj.units || ""; M.focus_x = f.length === 2 ? f[0] : ""; M.focus_y = f.length === 2 ? f[1] : ""; M.scale_ft_per_in = t.scale_ft_per_in || ""; M.grid_ft = t.grid_ft || ""; M.loaded_for = sel;
    ctx.save(); ctx.syncInputs && ctx.syncInputs(); manageOut("loaded " + sel + ": change fields, then Check changes / Save changes"); paint();
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
      return '<tr data-pl="' + esc(p.id) + '"' + (p.id === sel ? ' class="sel"' : "") + "><td>" + esc(p.id) + "</td><td>" + esc(p.name) + "</td><td>" + esc(p.kind) + (p.pop ? " " + esc(p.pop) : "") + "</td><td>" + esc(p.size) + "</td><td>" + esc(p.by + (p.image ? " (base map image)" : p.imported ? " (Foundry import)" : "")) + "</td><td>" + (p.scene ? "linked" : "") + "</td></tr>";
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
    var tb = $("plTrash");
    if (tb) {
      var T2 = listTrash(), te = P().manage.trash_entry;
      tb.innerHTML = T2.length ? T2.map(function (t) { return '<tr data-te="' + esc(t.entry) + '"' + (t.entry === te ? ' class="sel"' : "") + "><td>" + esc(t.entry) + "</td><td>" + esc(t.place) + "</td><td>" + esc(t.name || "") + "</td><td>" + esc(t.trashed || "") + "</td></tr>"; }).join("") : '<tr><td colspan="4" class="note">(trash is empty)</td></tr>';
      Array.prototype.forEach.call(tb.querySelectorAll("tr[data-te]"), function (tr) { tr.addEventListener("click", function () { P().manage.trash_entry = tr.getAttribute("data-te"); disarm(); ctx.save(); paint(); }); });
    }
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
    pl_image_browse: function () {
      try { var r = window.cep.fs.showOpenDialogEx(false, false, "Choose the base map image", "", ["png", "jpg", "jpeg", "webp", "tif", "tiff"]); if (r && r.data && r.data.length) { P().image.path = r.data[0].replace(/\\/g, "/"); ctx.save(); ctx.syncInputs(); } }
      catch (e) { if (ctx.showError) ctx.showError("file dialog unavailable: type the path instead"); }
    },
    pl_image_check: function () { return run(function () { return VB.jobImportImage(ctx.state(), true); }); },
    pl_image_import: function () { return run(function () { return VB.jobImportImage(ctx.state(), false); }); },
    pl_blank_check: function () { return run(function () { return VB.jobPlaceBlank(ctx.state(), true); }); },
    pl_blank_create: function () { return run(function () { return VB.jobPlaceBlank(ctx.state(), false); }); },
    pl_edit_load: function () { loadEditFields(); },
    pl_edit_check: function () { if (P().manage.loaded_for && P().manage.loaded_for !== sel) return manageOut("the fields were loaded from " + P().manage.loaded_for + ": select it again or Load fields for " + sel); return runManage("edit", { dry: true }); },
    pl_edit_apply: function () { if (P().manage.loaded_for && P().manage.loaded_for !== sel) return manageOut("the fields were loaded from " + P().manage.loaded_for + ": select it again or Load fields for " + sel); return runManage("edit"); },
    pl_rename_check: function () { return runManage("rename", { dry: true }); },
    pl_rename: function () { return runManage("rename"); },
    pl_dup_check: function () { return runManage("duplicate", { dry: true }); },
    pl_duplicate: function () { return runManage("duplicate"); },
    pl_trash: function () {
      if (!sel) return manageOut("select a place in the list first");
      if (sel === ctx.state().place) return manageOut(sel + " is the place open in the panel: switch to another place first");
      var s = sel; return armOrRun("trash:" + s, "plTrashBtn", "Click again to move " + s + " to trash", function () { return runManage("trash"); });
    },
    pl_trash_refresh: function () { paint(); },
    pl_restore: function () { return runManage("restore"); },
    pl_purge: function () {
      var M = P().manage; if (!M.trash_entry) return manageOut("pick a trash entry (click a row in the Trash table) first");
      if (!String(M.purge_confirm || "").trim()) return manageOut("type the place id in the box to confirm the permanent delete");
      return armOrRun("purge:" + M.trash_entry, "plPurgeBtn", "Click again: delete " + M.trash_entry + " for good", function () { return runManage("purge"); });
    },
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
