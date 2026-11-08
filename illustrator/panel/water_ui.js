// "3D water in Foundry" group of the Water tab: preset dropdown (river / pond / lake / ocean), sliders with live value boxes, colours, install / push to a scene.
// Loaded before main.js; main.js calls VBWaterUI.init(ctx) / paint(). Logic and jobs: lib/water.js; python: generators/water_presets.py, foundry_water.py.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, built = false;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function W() { return ctx.state().water3d; }
  function sceneOptions(sel) {
    var L = (((ctx.state().foundry || {}).cache || {}).lists || {}).scenes || [];
    return '<option value="">(pick a scene; Refresh scenes reads Foundry)</option>' + L.map(function (r) {
      return '<option value="' + esc(r.uuid) + '"' + (r.uuid === sel ? " selected" : "") + ">" + esc(r.name) + "  " + esc(String(r.uuid).split(".").pop().slice(0, 6)) + "</option>";
    }).join("");
  }
  function buildSliders() {
    $("w3Sliders").innerHTML = VB.WATER3D_KEYS.map(function (k) {
      var p = VB.WATER3D.params[k];
      return '<div class="sl" title="' + esc(p.hint) + '"><span>' + esc(p.label) + '</span><input type="range" data-w3="' + k + '" min="' + p.min + '" max="' + p.max + '" step="' + p.step + '">' +
        '<span class="nb"><input type="number" data-w3="' + k + '" min="' + p.min + '" max="' + p.max + '" step="' + p.step + '">' + (p.unit ? '<span class="un">' + esc(p.unit) + "</span>" : "") + "</span></div>";
    }).join("") + '<div class="sl" title="How strongly a steeper channel speeds up the flow (rivers)"><span>Slope speed-up</span><input type="range" data-w3="slope_speed" min="0" max="1" step="0.05">' +
      '<span class="nb"><input type="number" data-w3="slope_speed" min="0" max="1" step="0.05"></span></div>';
    $("w3Sliders").addEventListener("input", function (e) {
      var k = e.target.getAttribute && e.target.getAttribute("data-w3"); if (!k) return;
      var v = Number(e.target.value); if (!isFinite(v)) return;
      VB.water3dSetValue(ctx.state(), W().preset, k, v);
      Array.prototype.forEach.call($("w3Sliders").querySelectorAll('[data-w3="' + k + '"]'), function (o) { if (o !== e.target) o.value = e.target.value; });
      ctx.save();
    });
    built = true;
  }
  function paint() {
    if (!ctx || !$("w3Preset")) return;
    if (!built) buildSliders();
    var w = W(), T = VB.WATER3D;
    $("w3Preset").innerHTML = Object.keys(T.presets).map(function (k) { return '<option value="' + k + '">' + esc(T.presets[k].label) + "</option>"; }).join("");
    if (!T.presets[w.preset]) w.preset = "river";
    $("w3Preset").value = w.preset;
    var v = VB.water3dValues(ctx.state(), w.preset);
    $("w3Note").textContent = T.presets[w.preset].note + (w.force ? ". Used for ALL water bodies of this place." : ". Used by water bodies of this kind (rivers and streams = River, ponds = Pond, lakes = Lake, sea = Ocean).");
    Array.prototype.forEach.call($("w3Sliders").querySelectorAll("[data-w3]"), function (el) { el.value = v[el.getAttribute("data-w3")]; });
    $("w3Shallow").value = v.shallow_color; $("w3Deep").value = v.deep_color;
    $("w3Scene").innerHTML = sceneOptions(w.scene_uuid);
    var l = w.last, out = $("w3Out");
    if (out) out.textContent = l ? (l.dry ? "Dry run " : "") + l.cmd + " " + String(l.at).slice(0, 19) + ": tiles " + (l.tiles.join(", ") || "none") + (l.warnings.length ? "  WARNING: " + l.warnings.join("; ") : "") : "";
  }
  var A = {
    w3_scenes: function () { return VB.jobSkyScenes ? ctx.startJob(VB.jobSkyScenes(ctx.state()), function () { ctx.refreshAll ? ctx.refreshAll() : paint(); }) : null; },
    w3_install: function () { return ctx.startJob(VB.jobWaterInstall(ctx.state()), paint); },
    w3_apply: function () { return ctx.startJob(VB.jobWaterApply(ctx.state()), paint); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    $("w3Preset").addEventListener("change", function () { W().preset = $("w3Preset").value; ctx.save(); paint(); });
    $("w3Scene").addEventListener("change", function () { W().scene_uuid = $("w3Scene").value; ctx.save(); ctx.syncInputs && ctx.syncInputs(); });
    $("w3Reset").addEventListener("click", function () { VB.water3dResetPreset(ctx.state(), W().preset); ctx.save(); paint(); });
    [["w3Shallow", "shallow_color"], ["w3Deep", "deep_color"]].forEach(function (p) { $(p[0]).addEventListener("input", function () { VB.water3dSetValue(ctx.state(), W().preset, p[1], $(p[0]).value); ctx.save(); }); });
    paint();
  }
  window.VBWaterUI = { init: init, paint: paint, actions: A };
})();
