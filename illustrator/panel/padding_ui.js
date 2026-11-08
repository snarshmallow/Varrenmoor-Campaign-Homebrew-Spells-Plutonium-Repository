// Padding tab UI: preset pickers, scene picker, generate / push / save. Loaded before main.js; main.js calls VBPaddingUI.init(ctx) / paint().
// Logic (command lines, jobs) lives in lib/padding.js; python in generators/padding_heightmap.py.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function P() { return ctx.state().padding; }
  function listJson(dir) { // [{name, description}] of every *.json in dir (built-in and user presets)
    var out = [], fs = ctx.fs;
    try { fs.readdirSync(dir).forEach(function (f) { if (/\.json$/.test(f)) { var j = ctx.readJson(dir + "/" + f, null); if (j) out.push({ name: j.name || f.replace(/\.json$/, ""), description: j.description || "" }); } }); } catch (e) { /* dir missing */ }
    return out;
  }
  function heightPresets() { var b = ctx.root + "/illustrator/presets/padding"; return listJson(b).concat(listJson(b + "/user")); }
  function texturePresets() { return listJson(ctx.root + "/illustrator/presets/padding/textures"); }
  function paint() {
    if (!ctx || !$("padPreset")) return;
    var p = P(), hp = heightPresets(), tp = texturePresets();
    $("padPreset").innerHTML = hp.map(function (e) { return '<option value="' + esc(e.name) + '" title="' + esc(e.description) + '">' + esc(e.name) + (e.description ? " - " + esc(e.description) : "") + "</option>"; }).join("");
    $("padPreset").value = p.preset;
    $("padTexture").innerHTML = '<option value="">(preset default)</option>' + tp.map(function (e) { return '<option value="' + esc(e.name) + '">' + esc(e.name) + (e.description ? " - " + esc(e.description) : "") + "</option>"; }).join("");
    $("padTexture").value = p.texture || "";
    var st = ctx.state(), L = (((st.foundry || {}).cache || {}).lists || {}).scenes || [];
    $("padScene").innerHTML = '<option value="">(pick a scene, or paste a uuid below)</option>' + L.map(function (r) { return '<option value="' + esc(r.uuid) + '">' + esc(r.name) + "  " + esc(String(r.uuid).split(".").pop().slice(0, 6)) + "</option>"; }).join("");
    $("padScene").value = p.scene_uuid || "";
    var img = $("padPreview"); if (img) { if (p.preview_png) { img.hidden = false; img.src = "file:///" + p.preview_png.replace(/\\/g, "/"); } else img.hidden = true; }
    var l = p.last, out = $("padOut");
    if (out) {
      var lines = [];
      if (l) {
        var s = l.seam || {};
        lines.push("tableHeightmapScale " + l.scale + (l.heightmap_used ? "" : " (flat: no heightmap pushed)") + ", table plane at " + Number(l.base_level_ft).toFixed(1) + " ft, pixel 255 = " + Number(l.pixel255_ft).toFixed(0) + " ft, 8-bit step " + Number(l.quant_ft).toFixed(2) + " ft");
        if (s.max_step_terrain_edge_m !== undefined) lines.push("seam: terrain edge -> apron " + s.max_step_terrain_edge_m.toFixed(3) + " m, apron -> table " + s.max_step_table_m.toFixed(3) + " m (limit 0.05 m); without the apron the edge would be " + Number(s.table_only_step_ft).toFixed(1) + " ft off the table");
        lines.push("files: " + l.out_dir);
      }
      var r = p.push_report;
      if (r) lines.push((r.dry ? "DRY RUN for " : "pushed to ") + r.scene + ": " + JSON.stringify(r.flags) + "; level elevation.bottom " + r.level_bottom_ft + " ft");
      out.textContent = lines.join("\n");
    }
  }
  var A = {
    pad_generate: function () { return ctx.startJob(VB.jobPaddingGenerate(ctx.state(), ctx.dirs()), paint); },
    pad_push: function () { return ctx.startJob(VB.jobPaddingPush(ctx.state(), ctx.dirs()), paint); },
    pad_push_dry: function () { return ctx.startJob(VB.jobPaddingPush(ctx.state(), ctx.dirs(), { dry: true }), paint); },
    pad_save: function () { return ctx.startJob(VB.jobPaddingSavePreset(ctx.state()), paint); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var bind = function (id, key) { var el = $(id); if (el) el.addEventListener("change", function () { P()[key] = el.value; ctx.save(); paint(); }); };
    bind("padPreset", "preset"); bind("padTexture", "texture"); bind("padScene", "scene_uuid");
    paint();
  }
  window.VBPaddingUI = { init: init, paint: paint, actions: A };
})();
