// "Size and performance check" (Scale tab, under Scale and grid) and the shared facts for the Export section badge / notes.
// Logic and numbers: lib/limits.js. Facts: place.json bounds, building files, pack placements (files, triangles, lights), foliage.json items, the
// Foundry scene calibration the push would use (Foundry tab dpi + grid, Tools tab upscale / max px) and the Lighting tab light budget.
// Loaded before main.js; main.js calls VBLimitsUI.init(ctx) and VBLimitsUI.paint() from refreshAll.
(function () {
  "use strict";
  var Lm = window.VBLimits, ctx = null, cache = { at: 0, key: "", v: null };
  var $ = function (id) { return document.getElementById(id); };
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function rj(p) { try { return JSON.parse(ctx.fs.readFileSync(p, "utf8")); } catch (e) { return null; } }

  // file facts, cached a few seconds (paint runs often)
  function fileFacts() {
    var st = ctx.state(), d = ctx.dirs(), now = Date.now(), key = st.place;
    if (cache.v && cache.key === key && now - cache.at < 5000) return cache.v;
    var v = { w_ft: 0, h_ft: 0, buildings: null, tiles: null, triangles: null, lights: null, lightCounts: null, foliage: null };
    var p = rj(d.world + "/place.json") || {}, b = p.bounds || {};
    v.w_ft = +b.width_ft || 0; v.h_ft = +b.height_ft || 0;
    try { v.buildings = ctx.fs.readdirSync(d.world + "/buildings").filter(function (n) { return /\.json$/i.test(n); }).length; } catch (e) { /* none */ }
    var VB = window.VBCore, pl = VB && VB.packDir ? rj(VB.packDir(d) + "/placements.json") : null;
    if (pl && pl.files) {
      v.tiles = pl.files.length; v.triangles = pl.files.reduce(function (a, e) { return a + (+e.tris || 0); }, 0);
      var X = window.VBExportPlan, c = X && X.packLightCounts ? X.packLightCounts(pl) : null; if (c) { v.lights = c.total; v.lightCounts = c; }
    }
    var fo = rj(d.world + "/foliage.json"); if (fo && fo.items) v.foliage = fo.items.length;
    cache = { at: now, key: key, v: v };
    return v;
  }
  // the scene the push would make (same rule as foundry_push.calibrate)
  function calib(v) {
    var st = ctx.state(), f = st.foundry || {}, sc = st.scale || {}, ts = ((st.tools || {}).scene) || {};
    return Lm.sceneCalib({ w_ft: v.w_ft, h_ft: v.h_ft, dpi: f.dpi || 150, scale_ft_per_in: sc.scale_ft_per_in || 100, grid_ft: f.ftPerGrid || sc.grid_ft || 5, upscale: ts.upscale || 1, max_px: ts.max_px || 8192 });
  }
  function facts() {
    if (!ctx || !Lm) return null;
    var st = ctx.state(), v = fileFacts(), c = calib(v), f3d = (st.lighting || {}).f3d || null;
    return { w_ft: v.w_ft, h_ft: v.h_ft, grid_ft: c.grid_ft, grid_px: c.grid_px, ppf: c.ppf, mode: "3d", buildings: v.buildings, lights: v.lights, lighting: f3d,
      tiles: v.tiles, triangles: v.triangles, foliage: v.foliage, roofMode: ((st.foundry || {}).models || {}).roofMode, calib: c };
  }
  function check() { var fx = facts(); return fx ? { facts: fx, list: Lm.evaluate(fx) } : null; }

  var COL = { ok: "var(--ok,#5a5)", info: "var(--dim,#999)", warn: "var(--warn,#d90)", danger: "var(--bad,#d44)" };
  var WORD = { ok: "OK", info: "note", warn: "warning", danger: "too big" };
  function badge(level) { return '<span class="tag" style="border-color:' + COL[level] + ";color:" + COL[level] + '">' + WORD[level] + "</span>"; }

  function paint() {
    var box = $("limBox"); if (!box || !ctx || !Lm) return;
    var r = check(); if (!r) return;
    var fx = r.facts, c = fx.calib, worst = Lm.worst(r.list), n = Lm.fmt, html = "";
    html += '<div class="note">Place ' + n(fx.w_ft) + " x " + n(fx.h_ft) + " ft. Foundry scene from this panel: " + n(c.width) + " x " + n(c.height) + " px, grid " + c.grid_px + " px = " + c.grid_ft + " ft (" + (Math.round(c.ppf * 100) / 100) + " px/ft) " + badge(worst) + "</div>";
    if (c.error) html += '<div class="note" style="color:' + COL.danger + '">' + esc(c.error) + "</div>";
    html += "<ul style=\"margin:2px 0 4px 16px;padding:0\">" + r.list.map(function (x) {
      return '<li title="' + esc(x.source) + '"><span style="color:' + COL[x.level] + '">' + esc(WORD[x.level]) + ":</span> " + esc(x.message) + (x.suggestion && x.level !== "ok" ? ' <span class="note">' + esc(x.suggestion) + "</span>" : "") + "</li>";
    }).join("") + "</ul>";
    var rec = Lm.recommend(fx.w_ft, fx.h_ft, c.grid_ft, c.grid_px); if (rec.length) html += '<div class="note">' + rec.map(esc).join("<br>") + "</div>";
    var big = Math.max(fx.w_ft, fx.h_ft);
    html += '<details><summary class="note">Recommended maximum map sizes by scale (hover a heading for where the number comes from)</summary><table class="limtab"><tr>' +
      '<th>Scale</th><th title="' + esc(Lm.SOURCES.scene_px) + '">2D max ft (px)</th><th title="' + esc(Lm.SOURCES.scene_px) + '">2D hard ft</th><th title="' + esc(Lm.SOURCES.extent3d) + '">3D max ft</th><th title="' + esc(Lm.SOURCES.extent3d) + '">3D hard ft</th>' +
      '<th title="' + esc(Lm.SOURCES.lights) + '">lights rec / hard</th><th title="' + esc(Lm.SOURCES.buildings) + '">buildings</th><th title="' + esc(Lm.SOURCES.tiles) + '">tiles</th><th title="' + esc(Lm.SOURCES.tris) + '">triangles</th><th title="' + esc(Lm.SOURCES.foliage) + '">foliage</th><th title="' + esc(Lm.SOURCES.token) + '">5 ft token</th></tr>' +
      Lm.table().map(function (t) {
        var lv = big > t.hard3d_ft ? "danger" : big > t.rec3d_ft ? "warn" : "ok";
        return "<tr><td>" + esc(t.label) + "</td><td>" + n(t.rec2d_ft) + " (" + n(t.rec2d_px) + ")</td><td>" + n(t.hard2d_ft) + '</td><td style="color:' + COL[lv] + '">' + n(t.rec3d_ft) + "</td><td>" + n(t.hard3d_ft) + "</td><td>" + t.lights_rec + " / " + t.lights_hard +
          "</td><td>" + t.buildings_rec + " / " + t.buildings_hard + "</td><td>" + t.tiles_rec + " / " + t.tiles_hard + "</td><td>" + n(t.tris_rec / 1000) + "k / " + n(t.tris_hard / 1e6) + "M</td><td>" + n(t.foliage_rec) + " / " + n(t.foliage_hard) +
          '</td><td style="color:' + COL[t.token.small || t.token.overview ? "warn" : "ok"] + '">' + Math.round(t.token.fraction * 100) + "% (" + Math.round(t.token.token_px) + " px)</td></tr>";
      }).join("") + "</table><div class=\"note\">Measured: lights, triangles, grid and pixel limits (live tests, Foundry and 3D Canvas source). Estimates: 3D extent (from the town's light density), buildings 80, tiles, foliage 10,000. 3D max = recommended for a smooth table; hard = expect trouble.</div></details>";
    box.innerHTML = html;
    paintHints(r);
  }
  // Foundry tab scene scale hint + Export section badge
  function paintHints(r) {
    var c = r.facts.calib, tok = r.list.filter(function (x) { return x.code === "token"; })[0], hint = $("fScaleHint");
    if (hint) {
      var s = "Scene scale: grid " + c.grid_px + " px = " + c.grid_ft + " ft (" + (Math.round(c.ppf * 100) / 100) + " px/ft), scene " + Lm.fmt(c.width) + " x " + Lm.fmt(c.height) + " px.";
      var lv = tok ? tok.level : "ok";
      hint.innerHTML = esc(s) + (tok && tok.level !== "ok" ? ' <span style="color:' + COL[lv] + '">' + esc(tok.message + " " + tok.suggestion) + "</span>" : "") + (c.error ? ' <span style="color:' + COL.danger + '">' + esc(c.error) + "</span>" : "");
    }
    var ex = $("exLimits");
    if (ex) {
      var bad = r.list.filter(function (x) { return Lm.RANK[x.level] >= Lm.RANK.warn; }), worst = Lm.worst(r.list);
      ex.innerHTML = bad.length ? badge(worst) + " <b>Size and performance:</b> " + esc(bad.map(function (x) { return x.message; }).join(" ")) + ' <span class="note">(details: Scale tab, Size and performance check; warnings do not block)</span>'
        : badge("ok") + " Size and performance: within the recommended limits.";
    }
  }

  window.VBLimitsUI = {
    init: function (c) { ctx = c; paint(); },
    paint: function () { if (ctx) paint(); },
    check: function () { try { return check(); } catch (e) { return null; } },
    badge: badge, COL: COL, WORD: WORD,
    invalidate: function () { cache.at = 0; }
  };
})();
