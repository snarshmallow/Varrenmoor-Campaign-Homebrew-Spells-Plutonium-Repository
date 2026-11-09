// Streetlamps tab UI: style thumbnails, readout, buttons. Loaded before main.js; main.js calls VBStreetlampsUI.init(ctx) / paint().
// Controls (data-s / data-act) are static HTML in index.html section tab-streetlamps; logic and jobs live in lib/streetlamps.js.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, styles = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var S = function () { return ctx.state().streetlamps; };
  function loadStyles() { if (!styles) styles = (ctx.readJson(ctx.root + "/illustrator/presets/streetlamps/styles.json", { styles: {} }) || {}).styles || {}; return styles; }
  function go(make) { try { return ctx.startJob(make(), function () { paint(); }); } catch (e) { if (ctx.showError) ctx.showError(String((e && e.message) || e)); else if ($("slReadout")) $("slReadout").textContent = String((e && e.message) || e); } }
  var A = {
    sl_plan: function () { return go(function () { return VB.jobStreetlampsPlan(ctx.state(), ctx.dirs()); }); },
    sl_apply: function () { return go(function () { return VB.jobStreetlampsApply(ctx.state(), ctx.dirs()); }); },
    sl_push: function () {   // precheck: 0 lamps in the pack = nothing to push (never a failed run, never prunes scene lights)
      var c = packCheck(); if (c && c.reason) { paint(); if (ctx.showError) ctx.showError("Streetlamps push skipped: " + c.reason, "warn"); return null; }
      return go(function () { return VB.jobStreetlampsPush(ctx.state(), ctx.dirs()); });
    },
    sl_apply_on: function () { S().enabled = true; ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); return A.sl_apply(); },
    sl_thumbs: function () { return go(function () { return VB.jobStreetlampsThumbs(); }); },
    sl_scene_on: function () { return go(function () { return VB.jobStreetlampsScene(ctx.state(), ctx.dirs(), "on", !S().dry); }); },
    sl_scene_off: function () { return go(function () { return VB.jobStreetlampsScene(ctx.state(), ctx.dirs(), "off", !S().dry); }); },
    sl_scene_lights: function () { return go(function () { return VB.jobStreetlampsScene(ctx.state(), ctx.dirs(), "lights", !S().dry); }); }
  };
  // lamps / lamp lights in the pack placements.json (lib/exportplan.js readPackLights: cached by mtime); null = no pack or no planner
  function packCheck() {
    var X = window.VBExportPlan; if (!X || !X.readPackLights || !ctx.fs) return null;
    var c = X.readPackLights(ctx.fs, VB.packDir(ctx.dirs()) + "/placements.json"); if (!c) return null;
    return X.streetlampsPushCheck(c);
  }
  function paintGrid() {
    var g = $("slStyleGrid"); if (!g) return;
    var st = loadStyles(), cur = S().style;
    g.innerHTML = VB.SL_STYLES.map(function (k) {
      var s = st[k] || {}, src = "file:///" + (ctx.root + "/illustrator/presets/streetlamps/thumbs/" + k + ".png").replace(/\\/g, "/");
      return '<div data-slstyle="' + k + '" title="' + esc(s.description || "") + '" style="cursor:pointer;border:2px solid ' + (k === cur ? "#e0a030" : "#444") + ';border-radius:4px;padding:2px;text-align:center">' +
        '<img src="' + esc(src) + '" alt="' + esc(k) + '" style="width:100%;display:block" onerror="this.style.display=\'none\'"><div style="font-size:11px">' + esc(s.name || k) + "</div></div>";
    }).join("");
    var d = (st[cur] || {}).description; if ($("slStyleNote")) $("slStyleNote").textContent = d ? d + " Default height " + st[cur].height_ft + " ft." : "";
  }
  function paint() {
    if (!ctx || !$("slReadout")) return;
    paintGrid();
    $("slReadout").textContent = VB.streetlampsReadout(ctx.state());
    var pc = packCheck(), pb = $("slPushBtn"), pk = $("slPushCheck"), ar = $("slApplyOnRow");
    if (pk) pk.textContent = pc ? pc.line + (pc.reason ? " Push disabled: " + pc.reason : "") : "";
    if (pb) { pb.disabled = !!(pc && pc.reason); pb.title = pc && pc.reason ? pc.reason : "Pushes the streetlamps tile and the pack lights to the scene picked on the Foundry tab"; }
    if (ar) ar.hidden = !(pc && pc.offerApply);
    var L = S().light || {}, sw = $("slSwatch"); if (sw) sw.style.background = /^#[0-9a-f]{6}$/i.test(L.color || "") ? L.color : VB.kelvinToHex(L.kelvin || (loadStyles()[S().style] || { light: {} }).light.kelvin || 2000);
    var f = ctx.state().foundry || {}, sel = ((f.cache || {}).lists || {}).scenes || [], nm = "none (pick an existing scene on the Foundry tab)";
    sel.forEach(function (r) { if (r.uuid === f.sceneUuid) nm = r.name; });
    if ($("slScene")) $("slScene").textContent = f.target === "existing" && f.sceneUuid ? nm : nm;
    var sc = S().scene; if ($("slSceneOut")) $("slSceneOut").textContent = sc ? (sc.applied ? "Applied" : "Dry run") + " (" + sc.mode + ") " + String(sc.at || "").replace("T", " ").slice(0, 19) + ": " + sc.tile_changes + " tile and " + sc.light_changes + " light change(s) of " + sc.lights + " lamp lights. " + (sc.warning || "") : "";
  }
  function init(c) {
    ctx = c;
    var sec = $("tab-streetlamps"); if (!sec) return;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    sec.addEventListener("click", function (ev) {
      var t = ev.target.closest("[data-slstyle]"); if (!t) return;
      S().style = t.getAttribute("data-slstyle"); ctx.save(); ctx.syncInputs(); paint();
    });
    sec.addEventListener("change", function () { setTimeout(paint, 0); });
    sec.addEventListener("input", function () { setTimeout(paint, 0); });
    paint();
  }
  window.VBStreetlampsUI = { init: init, paint: paint, actions: A };
})();
