// Skybox tab UI: preset list, regenerate, apply to the place's scene, preview thumbnail, import the sky of an existing Foundry scene.
// Loaded before main.js; main.js calls VBSkyUI.init(ctx) / paint(). Logic: lib/skybox.js; python: generators/skybox.py.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function S() { return ctx.state().skybox; }
  function sceneOptions(sel) {
    var L = (((ctx.state().foundry || {}).cache || {}).lists || {}).scenes || [];
    return '<option value="">(pick a scene; Refresh scenes reads Foundry)</option>' + L.map(function (r) {
      return '<option value="' + esc(r.uuid) + '"' + (r.uuid === sel ? " selected" : "") + ">" + esc(r.name) + "  " + esc(String(r.uuid).split(".").pop().slice(0, 6)) + "</option>";
    }).join("");
  }
  function paint() {
    if (!ctx || !$("skyPreset")) return;
    var s = S(), rows = s.list || [], byName = {};
    rows.forEach(function (r) { byName[r.name] = r; });
    var items = VB.SKY_PRESETS.map(function (p) { return { key: p.key, label: p.label, note: p.note }; });
    rows.forEach(function (r) { if (!r.builtin) items.push({ key: r.name, label: "Imported: " + r.name, note: r.source ? "from scene " + (r.source.scene_name || r.source.scene_uuid) : "" }); });
    $("skyPreset").innerHTML = items.map(function (p) {
      var r = byName[p.key], has = r && r.exists;
      return '<option value="' + esc(p.key) + '" title="' + esc(p.note) + '">' + esc(p.label) + (has ? "" : " (no image)") + "</option>";
    }).join("");
    $("skyPreset").value = s.preset;
    var cur = items.filter(function (p) { return p.key === s.preset; })[0], row = byName[s.preset];
    $("skyNote").textContent = cur ? cur.note + (row && row.exists ? "" : "  No image yet: press Regenerate.") : "";
    var imp = !!(row && !row.builtin);
    $("skyRegen").disabled = imp;
    var lf = (row && row.lighting_flags) || {}, lk = Object.keys(lf);
    $("skyLightRow").hidden = !lk.length;
    $("skyLightTxt").textContent = lk.length ? "Also apply this sky's sun / lighting flags" : "";
    $("skyLightRow").title = lk.map(function (k) { return k + " = " + lf[k]; }).join("
");
    $("skyLightNote").textContent = lk.length ? "Flags: " + lk.map(function (k) { return k + " " + lf[k]; }).join(", ") : ""; $("skyLightNote").hidden = !lk.length;
    $("skyScene").innerHTML = sceneOptions(s.scene_uuid);
    $("skyImpScene").innerHTML = sceneOptions(s.import_scene);
    var img = $("skyPreview");
    var src = s.preview_png || (row && row.preview) || "";
    if (src && !s.preview_png && row && row.preview) src = row.preview;
    if (img) { if (src) { img.hidden = false; img.src = "file:///" + String(src).replace(/\\/g, "/").replace(/^file:\/+/, ""); } else img.hidden = true; }
    var l = s.last, out = $("skyOut");
    if (out) {
      var t = [];
      if (l && l.kind === "import") t.push("Imported '" + l.name + "' from " + (l.scene_name || l.scene) + " (" + l.how + ")." + (l.warnings && l.warnings.length ? " " + l.warnings.join("; ") : ""));
      if (l && l.kind === "apply") t.push((l.dry ? "Dry run for " : "Applied to ") + l.scene + ": " + JSON.stringify(l.flags));
      out.textContent = t.join("\n");
    }
  }
  function previewFor(name) { var r = (S().list || []).filter(function (x) { return x.name === name; })[0]; return r && r.preview ? r.preview : ""; }
  var A = {
    sky_list: function () { return ctx.startJob(VB.jobSkyList(ctx.state()), paint); },
    sky_scenes: function () { return ctx.startJob(VB.jobSkyScenes(ctx.state()), function () { ctx.refreshAll ? ctx.refreshAll() : paint(); }); },
    sky_generate: function () { return ctx.startJob(VB.jobSkyGenerate(ctx.state()), paint); },
    sky_apply: function () { return ctx.startJob(VB.jobSkyApply(ctx.state()), paint); },
    sky_import: function () { return ctx.startJob(VB.jobSkyImport(ctx.state()), paint); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var bind = function (id, key) { var el = $(id); if (el) el.addEventListener("change", function () { S()[key] = el.value; if (key === "preset") S().preview_png = previewFor(el.value) || ""; ctx.save(); paint(); }); };
    bind("skyPreset", "preset"); bind("skyScene", "scene_uuid"); bind("skyImpScene", "import_scene");
    A.sky_list();
    paint();
  }
  window.VBSkyUI = { init: init, paint: paint, actions: A };
})();
