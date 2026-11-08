// Bridges tab UI: crossing list (click = select + zoom), preset picker with thumbnails, parameter fields, auto-fix / apply / remove / preview.
// Loaded before main.js; main.js calls VBBridgesUI.init(ctx) / paint(). Logic and jobs: lib/bridges.js.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function B() { return ctx.state().bridges; }
  function thumb(id) { return "file:///" + (ctx.root + "/illustrator/out/bridges/thumbs/" + id + ".png").replace(/\\/g, "/"); }
  function paint() {
    if (!ctx || !$("brList")) return;
    var b = B(), have = {}; (b.items || []).forEach(function (i) { have[i.id] = i; });
    var rows = (b.crossings || []).map(function (c) { return { id: c.id, road: c.road, type: c.type, span: c.span_ft, above: c.deck_above_ground_ft, bridge: have[c.id] }; });
    (b.items || []).forEach(function (i) { if (!rows.some(function (r) { return r.id === i.id; })) rows.push({ id: i.id, road: i.road, type: i.crossing, span: i.length_ft, above: null, bridge: i }); });
    $("brList").innerHTML = rows.length ? rows.map(function (r) {
      var tag = r.bridge ? '<span class="tag" title="' + esc((r.bridge.warnings || []).join(" | ")) + '">' + esc(r.bridge.preset) + (r.bridge.deficit_m > 0 ? " !" : "") + (r.bridge.locked ? " (hand)" : "") + "</span>" : '<span class="tag">no bridge yet</span>';
      return '<li data-id="' + esc(r.id) + '"' + (r.id === b.selected ? ' class="sel"' : "") + "><b>" + esc(r.id) + "</b> " + esc(r.type) + ", " + Math.round(r.span) + " ft" + (r.above != null ? ", deck +" + Number(r.above).toFixed(1) + " ft" : "") + " " + tag + "</li>";
    }).join("") : '<li class="note">No crossings listed. Press Detect.</li>';
    $("brPreset").innerHTML = '<option value="">(auto: by road class and context)</option>' + VB.BRIDGE_PRESETS.map(function (p) { return '<option value="' + p[0] + '">' + esc(p[1]) + "</option>"; }).join("");
    $("brPreset").value = b.preset || "";
    $("brThumbs").innerHTML = VB.BRIDGE_PRESETS.map(function (p) { return '<img data-p="' + p[0] + '" title="' + esc(p[1]) + '" src="' + thumb(p[0]) + '"' + (p[0] === b.preset ? ' class="sel"' : "") + ' alt="' + esc(p[1]) + '">'; }).join("");
    var img = $("brPreview"); if (img) { if (b.preview_png) { img.hidden = false; img.src = "file:///" + b.preview_png.replace(/\\/g, "/"); } else img.hidden = true; }
    var l = b.last, out = $("brOut"); if (out) out.textContent = l ? "Last auto-fix " + l.at + ": " + (l.made.length ? l.made.join(", ") : "no bridges needed") + (l.roads.length ? "; ribbons trimmed on " + l.roads.join(", ") : "") : "";
  }
  var A = {
    br_detect: function () { return ctx.startJob(VB.jobBridgesDetect(ctx.state(), ctx.dirs()), paint); },
    br_autofix: function () { return ctx.startJob(VB.jobBridgesAutoFix(ctx.state(), ctx.dirs()), paint); },
    br_apply: function () { return ctx.startJob(VB.jobBridgesApply(ctx.state(), ctx.dirs()), paint); },
    br_remove: function () { return ctx.startJob(VB.jobBridgesRemove(ctx.state(), ctx.dirs()), paint); },
    br_preview: function () { return ctx.startJob(VB.jobBridgesPreview(ctx.state(), ctx.dirs()), paint); },
    br_focus: function () { return ctx.startJob(VB.jobBridgesFocus(ctx.state()), paint); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    $("brList").addEventListener("click", function (e) { var li = e.target.closest("li[data-id]"); if (!li) return; B().selected = li.getAttribute("data-id"); ctx.save(); paint(); A.br_focus(); });
    $("brPreset").addEventListener("change", function () { B().preset = $("brPreset").value; ctx.save(); paint(); });
    $("brThumbs").addEventListener("click", function (e) { var p = e.target.getAttribute && e.target.getAttribute("data-p"); if (!p) return; B().preset = B().preset === p ? "" : p; ctx.save(); paint(); });
    paint();
  }
  window.VBBridgesUI = { init: init, paint: paint, actions: A };
})();
