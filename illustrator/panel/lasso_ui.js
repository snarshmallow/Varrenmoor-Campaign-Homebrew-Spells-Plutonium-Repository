// Plugin lasso UI: one shared helper that adds the Lasso rows (draw, select inside, clear, adjust: feather / expand / contract / smooth / invert / border / add / subtract / intersect)
// under every polygon Capture button. Logic in lib/lasso.js + lib/polyops.js, jobs in lib/lasso.js, host actions lasso_* in jsx/host.jsx.
// Loaded before main.js; main.js calls VBLassoUI.init(ctx) once and VBLassoUI.paint() from refreshAll.
(function () {
  "use strict";
  var VB = window.VBCore, L = window.VBLasso, O = window.VBPolyOps, ctx = null;
  // act of the Capture button -> where its polygon lives. feather: state key of the feather (ft). patch/terrain already has a Feather field.
  var CAPTURES = {
    patch_capture: { store: "terrain.patch.polygon", src: "terrain.patch.polygon_src", feather: "terrain.patch.feather_ft", name: "patch" },
    water_capture_lake: { store: "water.lake_polygon", src: "water.lake_src", feather: "water.lake_feather_ft", name: "lake" },
    town_capture: { store: "town.area", src: "town.area_src", feather: "town.area_feather_ft", name: "town" },
    reg_capture: { store: "regions.polygon", src: "regions.polygon_src", feather: "regions.feather_ft", name: "region" },
    fol_capture_area: { store: "foliage.polygon", src: "foliage.polygon_src", feather: "foliage.feather_ft", name: "foliage" }
  };
  var work = {};          // act -> working polygon (feet) not yet applied
  var base = {};          // act -> stored polygon the working copy came from (a new capture drops the working copy)
  var rows = {};          // act -> {stat, feather, amount, iters, mode, filter}
  var $ = function (id) { return document.getElementById(id); };
  var num = function (el, d) { var v = parseFloat(el && el.value); return isFinite(v) ? v : d; };

  function cur(act) { var c = CAPTURES[act], v = VB.getPath(ctx.state(), c.store); return work[act] || (v && v.length ? v : null); }
  function say(msg, kind) { if (ctx.showError) ctx.showError(msg, kind); }
  function paint() {
    if (!ctx) return;
    Object.keys(CAPTURES).forEach(function (act) {
      var r = rows[act]; if (!r) return; var c = CAPTURES[act], stored = VB.getPath(ctx.state(), c.store);
      if (work[act] && base[act] !== stored) work[act] = null;
      var w = work[act];
      var txt = L.statusText(stored, true);
      if (w) txt += "  |  working copy: " + L.statusText(w, true) + " (press Apply adjust)";
      var f = VB.getPath(ctx.state(), c.feather); if (f > 0) txt += "  |  feather " + f + " ft";
      r.stat.textContent = txt; r.stat.className = "tag" + (w ? " stale" : "");
      if (r.feather && document.activeElement !== r.feather && !r.feather.dataset.touched) r.feather.value = f > 0 ? f : 0;
    });
  }
  function show(act, extra) {   // draw the working polygon + feather rings and select the core in Illustrator
    var pts = cur(act); if (!pts) { say("no polygon yet: press Capture first", "warn"); return null; }
    var f = num(rows[act].feather, 0);
    return ctx.startJob(L.jobDraw(ctx.state(), ctx.dirs(), { core: pts, feather: f }), function () { if (extra) extra(); paint(); });
  }
  function commit(act, res, what) {
    if (!res.ok) { say(what + ": " + res.error, "warn"); return null; }
    (res.warnings || []).forEach(function (w) { ctx.logLine && ctx.logLine("note: " + w); });
    var c = L.clean(res.pts, { closed: true });
    if (!c.ok) { say(what + ": " + c.error, "warn"); return null; }
    if (!work[act]) base[act] = VB.getPath(ctx.state(), CAPTURES[act].store);
    work[act] = c.pts; paint(); return show(act);
  }
  function boundsFt() {
    var p = ctx.readJson(ctx.dirs().world + "/place.json", {}), b = p.bounds || {};
    var x0 = b.x_min != null ? b.x_min : 0, y0 = b.y_min != null ? b.y_min : 0;
    return { x0: x0, y0: y0, x1: b.x_max != null ? b.x_max : x0 + (b.width_ft || 0), y1: b.y_max != null ? b.y_max : y0 + (b.height_ft || 0) };
  }
  var A = {
    draw: function (act) { return ctx.startJob(L.jobStart()); },
    inside: function (act) {
      var pts = cur(act); if (!pts) { say("no polygon yet: capture one first, then select what is inside", "warn"); return null; }
      var r = rows[act]; return ctx.startJob(L.jobInside(ctx.state(), ctx.dirs(), { poly: pts, mode: r.mode.value, filter: (r.filter.value || "").split(",").map(function (s) { return s.trim(); }).filter(Boolean) }));
    },
    clear: function (act) { work[act] = null; return ctx.startJob(L.jobClear(), paint); },
    expand: function (act) { var p = cur(act), d = num(rows[act].amount, 0); if (!p) return say("capture a polygon first", "warn"); if (!(d > 0)) return say("set Amount (ft) above 0", "warn"); return commit(act, O.offset(p, d), "Expand"); },
    contract: function (act) { var p = cur(act), d = num(rows[act].amount, 0); if (!p) return say("capture a polygon first", "warn"); if (!(d > 0)) return say("set Amount (ft) above 0", "warn"); return commit(act, O.offset(p, -d), "Contract"); },
    smooth: function (act) { var p = cur(act); if (!p) return say("capture a polygon first", "warn"); return commit(act, O.smooth(p, num(rows[act].iters, 2)), "Smooth"); },
    invert: function (act) { var p = cur(act); if (!p) return say("capture a polygon first", "warn"); var b = boundsFt(); if (!(b.x1 > b.x0)) return say("map bounds unknown (place.json)", "warn"); return commit(act, O.invert(p, b), "Invert"); },
    border: function (act) { var p = cur(act), d = num(rows[act].amount, 0); if (!p) return say("capture a polygon first", "warn"); if (!(d > 0)) return say("set Amount (ft) above 0 for the border width", "warn"); return commit(act, O.border(p, d), "Border"); },
    boolean: function (act, op) {   // the second shape is whatever is now selected / drawn on VB LASSO; the first is the working or stored polygon
      var p = cur(act); if (!p) return say("capture a polygon first", "warn");
      var holder = { out: {} };
      return ctx.startJob(L.jobRead(ctx.state(), ctx.dirs(), holder), function (res) {
        if (!res.ok) return; commit(act, O.boolean(p, holder.out.pts, op), op === "union" ? "Add" : op === "subtract" ? "Subtract" : "Intersect");
      });
    },
    preview: function (act) { return show(act); },
    apply: function (act) {
      var c = CAPTURES[act], w = work[act], f = num(rows[act].feather, 0), st = ctx.state();
      if (!w && !(f >= 0)) return say("nothing to apply", "warn");
      if (w) { VB.setPath(st, c.store, w.map(function (q) { return [VB.round1(q[0]), VB.round1(q[1])]; })); VB.setPath(st, c.src, "adjusted lasso (" + L.statusText(w, true) + ")"); }
      VB.setPath(st, c.feather, Math.max(0, f)); work[act] = null; rows[act].feather.dataset.touched = "";
      ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); paint();
      if (ctx.logLine) ctx.logLine("lasso: applied" + (w ? " polygon (" + L.describe(L.stats(VB.getPath(st, c.store))) + ")" : "") + ", feather " + f + " ft -> " + c.feather +
        (act === "patch_capture" ? " (the Terrain patch Feather field)" : " (stored; used where a feather / soft-edge setting exists)"));
      return show(act);
    }
  };
  function btn(label, title, fn, cls) { var b = document.createElement("button"); b.textContent = label; b.title = title; if (cls) b.className = cls; b.addEventListener("click", function () { try { var r = fn(); if (r && r.catch) r.catch(function (e) { say(String(e && e.message || e)); }); } catch (e) { say(String(e && e.message || e)); } }); return b; }
  function lab(text, input) { var l = document.createElement("label"); l.appendChild(document.createTextNode(text + " ")); l.appendChild(input); return l; }
  function inp(val, w, min) { var i = document.createElement("input"); i.type = "number"; i.step = "any"; i.value = val; i.style.width = w || "64px"; if (min != null) i.min = min; return i; }
  function build(act) {
    var b = document.querySelector('[data-act="' + act + '"]'); if (!b) return;
    var host = b.parentNode, r = {}, row1 = document.createElement("div"), row2 = document.createElement("div"), row3 = document.createElement("div");
    row1.className = row2.className = row3.className = "btns lassoRow";
    r.mode = document.createElement("select"); r.mode.innerHTML = '<option value="center">centre inside</option><option value="all">all anchors inside</option>'; r.mode.title = "Select objects whose bounds centre, or every anchor, lies inside the lasso";
    r.filter = document.createElement("input"); r.filter.type = "text"; r.filter.placeholder = "layers (blank = all unlocked)"; r.filter.style.width = "150px"; r.filter.title = "Comma separated layer names; blank = every unlocked visible layer except VB LASSO and guides";
    r.stat = document.createElement("span"); r.stat.className = "tag"; r.stat.textContent = "none";
    r.feather = inp(0, "56px", 0); r.feather.title = "Soft edge width in feet, centred on the outline (half inside, half outside). Shown as lighter dashed rings on layer VB LASSO"; r.feather.addEventListener("input", function () { r.feather.dataset.touched = "1"; });
    r.amount = inp(10, "56px", 0); r.amount.title = "Distance in feet for Expand, Contract and Border";
    r.iters = inp(2, "40px", 1); r.iters.title = "Smooth passes (1-5)"; r.iters.step = "1";
    row1.appendChild(btn("Draw lasso", "Creates the dashed VB LASSO layer and selects the Pencil/Pen tool when Illustrator allows it; draw around the area, then press Capture", function () { return A.draw(act); }));
    row1.appendChild(btn("Select inside", "Select the objects inside the lasso on the chosen layers", function () { return A.inside(act); }));
    row1.appendChild(r.mode); row1.appendChild(r.filter);
    row1.appendChild(btn("Clear lasso", "Remove the VB LASSO layer and any unapplied adjustment", function () { return A.clear(act); }));
    row1.appendChild(r.stat);
    row2.appendChild(lab("Feather ft", r.feather)); row2.appendChild(lab("Amount ft", r.amount));
    row2.appendChild(btn("Expand", "Grow the outline by Amount feet", function () { return A.expand(act); }));
    row2.appendChild(btn("Contract", "Shrink the outline by Amount feet", function () { return A.contract(act); }));
    row2.appendChild(btn("Border", "Replace the shape by a ring of width Amount outside the outline (stored as one polygon with a zero-width bridge)", function () { return A.border(act); }));
    row2.appendChild(lab("Smooth", r.iters)); row2.appendChild(btn("Smooth", "Round the corners (Chaikin), area kept", function () { return A.smooth(act); }));
    row2.appendChild(btn("Invert", "Everything inside the map bounds except the shape", function () { return A.invert(act); }));
    row3.appendChild(btn("Add", "Union with the shape now selected / drawn on VB LASSO", function () { return A.boolean(act, "union"); }));
    row3.appendChild(btn("Subtract", "Cut the shape now selected / drawn on VB LASSO out of the polygon", function () { return A.boolean(act, "subtract"); }));
    row3.appendChild(btn("Intersect", "Keep only the part shared with the shape now selected / drawn on VB LASSO", function () { return A.boolean(act, "intersect"); }));
    row3.appendChild(btn("Preview", "Redraw the polygon and its feather rings in Illustrator", function () { return A.preview(act); }));
    row3.appendChild(btn("Apply adjust", "Write the adjusted polygon and the feather into the panel state", function () { return A.apply(act); }, "primary"));
    host.parentNode.insertBefore(row1, host.nextSibling); host.parentNode.insertBefore(row2, row1.nextSibling); host.parentNode.insertBefore(row3, row2.nextSibling);
    rows[act] = r;
  }
  function init(c) {
    ctx = c;
    if (!L || !O || !VB) return;
    Object.keys(CAPTURES).forEach(build);
    paint();
  }
  window.VBLassoUI = { init: init, paint: paint, _work: work };
})();
