// Foliage tab UI (species picker with weights, area target, rules, tools, merge for performance). Loaded before main.js;
// main.js calls VBFoliageUI.init(ctx) / paint(). Logic (params, jobs) lives in lib/foliage.js; python in generators/foliage.py.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, LIB = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var F = function () { return ctx.state().foliage; };

  function loadLib() { // species + mixes straight from illustrator/presets/foliage (tris were written there by `foliage.py presets-sync`)
    if (LIB) return LIB;
    var dir = ctx.root + "/illustrator/presets/foliage", lib = { species: {}, order: [], mixes: {} };
    try {
      ctx.fs.readdirSync(dir).sort().forEach(function (f) {
        if (!/\.json$/.test(f)) return;
        var j = ctx.readJson(dir + "/" + f, {});
        (j.species || []).forEach(function (s) { lib.species[s.id] = s; lib.order.push(s.id); });
        Object.keys(j.mixes || {}).forEach(function (k) { lib.mixes[k] = j.mixes[k]; });
      });
    } catch (e) { /* presets folder missing: the picker stays empty */ }
    return (LIB = lib);
  }
  function areaHa() {
    var f = F(), st = ctx.state(), pts = null;
    if (f.target === "lasso") pts = f.polygon; else if (f.target === "town") pts = st.town.area;
    else if (f.target === "district") { var ds = ctx.readJson(ctx.dirs().world + "/districts.json", { districts: [] }).districts || []; var e = ds.filter(function (x) { return x.id === f.district; })[0]; pts = e && e.geometry && e.geometry.points; }
    else { var b = ctx.readJson(ctx.dirs().world + "/place.json", {}).bounds || {}; return (b.width_ft || 0) * (b.height_ft || 0) / 107639.1; }
    return pts && pts.length > 2 ? VB.polyArea(pts) / 107639.1 : 0;
  }
  function paint() {
    if (!ctx || !$("folMix")) return;
    var f = F(), lib = loadLib(), st = ctx.state();
    var wrap = $("folMix");
    wrap.innerHTML = lib.order.map(function (id) {
      var s = lib.species[id], m = f.mix.filter(function (x) { return x.species === id; })[0], w = m ? m.weight : 0;
      return '<label class="folsp" title="' + esc(s.name + ": " + s.height_ft[0] + "-" + s.height_ft[1] + " ft, " + (s.tris || []).join("/") + ' triangles (LOD 0/1/2), spacing ' + s.spacing_ft + ' ft') + '">' +
        '<span class="sw" style="background:' + esc(s.symbol.color) + '"></span><span class="g">' + esc(s.name) + '</span><input type="number" min="0" step="0.5" data-fw="' + id + '" value="' + w + '"></label>';
    }).join("");
    var mp = $("folMixPreset");
    if (!mp.options.length) mp.innerHTML = '<option value="">(custom mix)</option>' + Object.keys(lib.mixes).map(function (k) { return '<option value="' + k + '">' + esc(k.replace(/_/g, " ")) + "</option>"; }).join("");
    mp.value = f.mix_preset || "";
    var pt = $("folPattern"); if (!pt.options.length) pt.innerHTML = VB.FOLIAGE_PATTERNS.map(function (p) { return '<option value="' + p[0] + '">' + esc(p[1]) + "</option>"; }).join(""); pt.value = f.pattern;
    var ss = $("folSingle"); if (!ss.options.length) ss.innerHTML = lib.order.map(function (id) { return '<option value="' + id + '">' + esc(lib.species[id].name) + "</option>"; }).join(""); ss.value = f.single_species;
    var ds = ctx.readJson(ctx.dirs().world + "/districts.json", { districts: [] }).districts || [];
    var dsel = $("folDistrict"); dsel.innerHTML = '<option value="">(pick)</option>' + ds.filter(function (e) { return e.geometry && e.geometry.type === "polygon"; }).map(function (e) { return '<option value="' + esc(e.id) + '">' + esc(e.name || e.id) + "</option>"; }).join(""); dsel.value = f.district || "";
    var ms = $("folMergePreset"); if (!ms.options.length) ms.innerHTML = Object.keys(VB.FOLIAGE_MERGE_PRESETS).map(function (k) { return '<option value="' + k + '">' + esc(VB.FOLIAGE_MERGE_PRESETS[k].label) + "</option>"; }).join(""); ms.value = f.merge.preset;
    $("folPolyTag").textContent = f.polygon && f.polygon.length ? f.polygon_src || f.polygon.length + " pts" : "none";
    $("folPathTag").textContent = f.path && f.path.length ? f.path_src || f.path.length + " pts" : "none";
    var ha = areaHa(), est = VB.foliageEstimate(st, lib.species, ha);
    $("folEst").textContent = (ha ? ha.toFixed(2) + " ha, " : "area not set, ") + "about " + est.count + " instances, " + est.triangles.toLocaleString() + " triangles unmerged (before obstacles and spacing)";
    var s = f.stats;
    $("folStats").textContent = s ? s.items + " instances (" + s.hand_placed + " hand-placed), " + s.triangles.toLocaleString() + " triangles, " + s.draw_calls_unmerged + " draw calls unmerged\n" +
      Object.keys(s.per_species).map(function (k) { return k + " " + s.per_species[k]; }).join(", ") : "no counts yet: press Counts";
    var r = f.merge.report;
    $("folReport").textContent = r ? "Merge: draw calls " + r.before.draw_calls + " -> " + r.after.draw_calls + ", triangles " + r.before.triangles.toLocaleString() + " -> " + r.after.triangles.toLocaleString() +
      ", files " + r.before.files + " templates + " + r.before.tiles + " tiles -> " + r.after.files + " chunk files, GLB " + Math.round(r.after.glb_bytes_primary / 1024) + " KB (+LODs " + Math.round(r.after.glb_bytes_with_lods / 1024) + " KB)\n" + r.out : "";
    var img = $("folPreview"); if (img) { if (f.preview_png) { img.hidden = false; img.src = "file:///" + f.preview_png.replace(/\\/g, "/"); } else img.hidden = true; }
    ["folAreaLasso", "folAreaPath"].forEach(function (id) { var el = $(id); if (el) el.hidden = (id === "folAreaPath") !== VB.foliageIsLine(st); });
  }
  var acts = {
    fol_capture_area: function () { return ctx.startJob(VB.jobCapture(ctx.state(), ctx.dirs(), { what: "foliage area", closed: true, store: "foliage.polygon", srcName: "foliage.polygon_src" }), function () { F().target = "lasso"; ctx.save(); ctx.syncInputs(); paint(); }); },
    fol_capture_path: function () { return ctx.startJob(VB.jobCapture(ctx.state(), ctx.dirs(), { what: "foliage path", open: true, store: "foliage.path", srcName: "foliage.path_src" }), paint); },
    fol_scatter: function () { return ctx.startJob(VB.jobFoliageScatter(ctx.state(), ctx.dirs()), paint); },
    fol_clear: function () { return ctx.startJob(VB.jobFoliageClear(ctx.state(), ctx.dirs()), paint); },
    fol_add: function () { return ctx.startJob(VB.jobFoliageAdd(ctx.state(), ctx.dirs()), paint); },
    fol_draw: function () { return ctx.startJob(VB.jobFoliageDraw(ctx.state(), ctx.dirs())); },
    fol_stats: function () { return ctx.startJob(VB.jobFoliageStats(ctx.state(), ctx.dirs()), paint); },
    fol_preview: function () { return ctx.startJob(VB.jobFoliagePreview(ctx.state(), ctx.dirs()), paint); },
    fol_merge: function () { return ctx.startJob(VB.jobFoliageMerge(ctx.state(), ctx.dirs(), {}), paint); },
    fol_publish_dry: function () { return ctx.startJob(VB.jobFoliageMerge(ctx.state(), ctx.dirs(), { publish: true, dry: true }), paint); },
    fol_publish: function () { return ctx.startJob(VB.jobFoliageMerge(ctx.state(), ctx.dirs(), { publish: true }), paint); },
    fol_use_town: function () { var st = ctx.state(); F().polygon = (st.town.area || []).slice(); F().polygon_src = "Town tab area"; F().target = "lasso"; ctx.save(); ctx.syncInputs(); paint(); }
  };
  function init(c) {
    ctx = c;
    Object.keys(acts).forEach(function (k) { if (ctx.acts) ctx.acts[k] = acts[k]; });
    var sec = $("tab-foliage"); if (!sec) return;
    sec.addEventListener("input", function (ev) {
      var t = ev.target, id = t.getAttribute && t.getAttribute("data-fw");
      if (id) {
        var f = F(), m = f.mix.filter(function (x) { return x.species === id; })[0], w = Number(t.value) || 0;
        if (m) m.weight = w; else if (w > 0) f.mix.push({ species: id, weight: w });
        f.mix = f.mix.filter(function (x) { return x.weight > 0; }); f.mix_preset = ""; $("folMixPreset").value = ""; ctx.save();
      }
      paint();
    });
    sec.addEventListener("change", function (ev) {
      var t = ev.target;
      if (t.id === "folMixPreset") {
        var lib = loadLib(), k = t.value; if (!k) return;
        F().mix = lib.mixes[k].map(function (m) { return { species: m[0], weight: m[1] }; }); F().mix_preset = k; ctx.save(); paint();
      } else if (t.id === "folMergePreset") { VB.foliageApplyMergePreset(ctx.state(), t.value); ctx.save(); ctx.syncInputs(); paint(); }
      else if (t.getAttribute("data-s") && t.getAttribute("data-s").indexOf("foliage.merge.") === 0 && t.getAttribute("data-s") !== "foliage.merge.preset" && t.getAttribute("data-s") !== "foliage.merge.scene_uuid") { F().merge.preset = ""; }
      paint();
    });
    paint();
  }
  window.VBFoliageUI = { init: init, paint: paint, actions: acts };
})();
