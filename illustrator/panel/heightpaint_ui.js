// Paint heightmap UI (a collapsible section at the end of the Terrain tab, #hpDetails): shaded-relief canvas of the place's heightmap with pan / zoom, brushes, undo / redo, save / reset. Loaded before main.js; main.js calls
// VBHeightPaintUI.init(ctx) / paint(). Logic (stroke building, jobs, renderer) is in lib/heightpaint.js; the brush maths and the edit layer are python
// (generators/heightmap_paint.py): the canvas shows the downsampled preview python writes after every stroke.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null;
  var $ = function (id) { return document.getElementById(id); };
  var cv = null, g = null, off = document.createElement("canvas"), loaded = { place: null, stamp: null }, H = null, D = null, meta = null;
  var hover = null, drag = null, pan = null, pending = [], queue = Promise.resolve(), spaceDown = false, renderTimer = null, dirtyImage = true;
  var resetArmed = false, resetTimer = null;
  function disarmReset() {
    resetArmed = false; clearTimeout(resetTimer);
    var b = document.querySelector('[data-act="hp_reset"]'); if (b && b.dataset.label) b.textContent = b.dataset.label;
  }
  function P() { return ctx.state().hp; }
  // the canvas can only be measured / drawn while the Terrain tab is shown and the Paint section is open
  function tabOn() { var t = $("tab-terrain"); return !!(t && t.classList.contains("on")); }
  function isOpen() { var d = $("hpDetails"); return !!(d && d.open); }
  function visible() { return !!(cv && cv.parentNode && cv.parentNode.clientWidth > 0 && tabOn() && isOpen()); }
  function ensureView() {
    var st = ctx.state(); if (!meta) return;
    if (!P().view || !(P().view.zoom > 0) || P().view.fitFor !== st.place) P().view = Object.assign(VB.hpFit(meta, cv.width, cv.height), { fitFor: st.place });
  }
  function busyMsg(t) { var el = $("hpStatus"); if (el) el.textContent = t || ""; }

  function readPreview() {
    var d = ctx.dirs(), dir = VB.hpPreviewDir(d), st = ctx.state();
    var m = ctx.readJson(dir + "/preview.json", null);
    if (!m || m.place !== st.place) { H = D = meta = null; loaded.place = null; dirtyImage = true; return false; }
    try {
      H = VB.hpReadBin(ctx.fs.readFileSync(dir + "/preview_h.bin")); D = VB.hpReadBin(ctx.fs.readFileSync(dir + "/preview_d.bin"));
    } catch (e) { H = D = meta = null; return false; }
    if (H.length !== m.pw * m.ph) { H = D = meta = null; return false; }
    meta = m; loaded.place = st.place; loaded.stamp = P().stamp; dirtyImage = true;
    if (visible()) { size(); ensureView(); }   // hidden: fit later, when the canvas has a real size (draw)
    return true;
  }
  function renderImage() {
    if (!meta || !H) return;
    var p = P(); off.width = meta.pw; off.height = meta.ph;
    var px = VB.hpRender(H, meta.pw, meta.ph, { cell_ft: meta.cell_ft * meta.factor, lo: meta.elev_min, hi: meta.elev_max, exag: Number(p.exag) || 1, contour_ft: Number(p.contour_ft) || 0,
      delta: p.show_delta ? D : null, azimuth: Number(p.light_az) });
    var id = new ImageData(new Uint8ClampedArray(px), meta.pw, meta.ph); off.getContext("2d").putImageData(id, 0, 0); dirtyImage = false;
  }
  function size() {
    if (!cv || !cv.parentNode.clientWidth) return; var w = Math.max(cv.parentNode.clientWidth - 2, 200);
    if (cv.width !== w) { cv.width = w; cv.height = Math.round(Math.min(w * 0.85, 520)); }
  }
  function toScreen(x, y) { var v = P().view, q = VB.hpFeetToPx(meta, x, y); return [q[0] * v.zoom + v.ox, q[1] * v.zoom + v.oy]; }
  function draw() {
    if (!cv || !visible()) return; size(); g = cv.getContext("2d"); g.fillStyle = "#202020"; g.fillRect(0, 0, cv.width, cv.height);
    if (!meta || !H) { g.fillStyle = "#aaa"; g.font = "12px sans-serif"; g.fillText("No heightmap loaded: press Load / refresh.", 10, 20); return; }
    ensureView(); if (dirtyImage) renderImage();
    var v = P().view; g.imageSmoothingEnabled = v.zoom < 3; g.setTransform(v.zoom, 0, 0, v.zoom, v.ox, v.oy); g.drawImage(off, 0, 0); g.setTransform(1, 0, 0, 1, 0, 0);
    g.strokeStyle = "#000"; g.lineWidth = 1; g.strokeRect(v.ox - 0.5, v.oy - 0.5, meta.pw * v.zoom + 1, meta.ph * v.zoom + 1);
    var p = P(), rpx = (Number(p.radius_ft) || 30) / (meta.cell_ft * meta.factor) * v.zoom;
    var drawPath = function (pts, col) {
      if (!pts.length) return; g.strokeStyle = col; g.lineWidth = 2; g.beginPath();
      pts.forEach(function (q, i) { var s = toScreen(q[0], q[1]); if (i) g.lineTo(s[0], s[1]); else g.moveTo(s[0], s[1]); }); if (pts.length === 1) { var s0 = toScreen(pts[0][0], pts[0][1]); g.lineTo(s0[0] + 0.1, s0[1]); } g.stroke();
    };
    pending.forEach(function (s) { drawPath(s.points, "rgba(255,200,0,.9)"); });
    if (drag) drawPath(drag.pts, "rgba(255,255,255,.95)");
    if (hover && !pan) {
      var s = toScreen(hover[0], hover[1]); g.lineWidth = 1; g.strokeStyle = "#fff"; g.beginPath(); g.arc(s[0], s[1], Math.max(rpx, 1.5), 0, 6.2832); g.stroke();
      var hr = Math.max(rpx * (Number(p.hardness) || 0), 0); if (hr > 1) { g.strokeStyle = "rgba(255,255,255,.5)"; g.beginPath(); g.arc(s[0], s[1], hr, 0, 6.2832); g.stroke(); }
    }
  }
  function schedule(full) { if (full) dirtyImage = true; if (renderTimer) return; renderTimer = setTimeout(function () { renderTimer = null; draw(); }, 30); }
  function readout() {
    var el = $("hpReadout"); if (!el) return; var lines = [];
    if (meta && hover) {
      var q = VB.hpFeetToPx(meta, hover[0], hover[1]), ok = q[0] >= 0 && q[1] >= 0 && q[0] <= meta.pw - 1 && q[1] <= meta.ph - 1;
      if (ok) {
        var hh = VB.hpBilinear(H, meta.pw, meta.ph, q[0], q[1]), dd = VB.hpBilinear(D, meta.pw, meta.ph, q[0], q[1]);
        lines.push("x " + hover[0].toFixed(0) + " ft, y " + hover[1].toFixed(0) + " ft: height " + hh.toFixed(1) + " ft" + (Math.abs(dd) > 0.005 ? " (edit " + (dd >= 0 ? "+" : "") + dd.toFixed(2) + " ft)" : ""));
      } else lines.push("x " + hover[0].toFixed(0) + " ft, y " + hover[1].toFixed(0) + " ft: outside the terrain");
    }
    el.textContent = lines.join("\n");
  }
  function summary() {
    var s = P().stats, el = $("hpOut"); if (!el) return;
    if (!s) { el.textContent = ""; return; }
    var m = s.summary || {}, t = [];
    t.push("Strokes in the edit layer: " + s.strokes + (s.unsaved ? "  (UNSAVED: the pipeline does not see them yet)" : (s.has_saved ? "  (saved)" : "")));
    t.push("Edited cells: " + m.changed_cells + ", max raise " + m.max_raise_ft + " ft, max cut " + m.max_lower_ft + " ft");
    t.push("Terrain " + s.shape[1] + " x " + s.shape[0] + " nodes, " + s.cell_ft + " ft cells, source " + s.source + "; generated " + s.base_min_ft + " .. " + s.base_max_ft + " ft, with edits " + s.final_min_ft + " .. " + s.final_max_ft + " ft");
    if (meta) t.push("Preview 1:" + meta.factor + " (" + meta.pw + " x " + meta.ph + " px). Edits are computed at full resolution in python.");
    var l = P().last; if (l && l.saved !== undefined) t.push((l.saved ? "Saved " : "Saved (layer was empty, removed) ") + l.at);
    el.textContent = t.join("\n");
    warnings();
    var u = $("hpUndo"), r = $("hpRedo"); if (u) u.disabled = !(s.strokes > 0); if (r) r.disabled = !((P().redo || []).length);
  }
  // roads / bridges / buildings the edit layer endangers (heightmap_paint.py check, run after every job): one line each, plus the Flatten under roads button
  function warnings() {
    var box = $("hpWarn"), c = P().check, btn = document.querySelector('[data-act="hp_conform"]'); if (!box) return;
    var w = (c && c.warnings) || []; while (box.firstChild) box.removeChild(box.firstChild);
    w.forEach(function (m) { var li = document.createElement("li"); li.textContent = m; box.appendChild(li); });
    box.hidden = !w.length;
    var n = (c && c.flagged_roads || []).length;
    if (btn) { btn.disabled = !n; btn.title = n ? "Flatten the edit layer across " + c.flagged_roads.join(", ") + " so the ground matches the road bed (one undoable step)" : "No road is endangered by the current edits"; }
  }
  function paintTools() {
    var box = $("hpTools"); if (!box) return;
    if (!box.children.length) VB.HP_TOOLS.forEach(function (t) {
      var b = document.createElement("button"); b.textContent = t.label; b.setAttribute("data-hp-tool", t.id); b.title = toolHelp[t.id];
      b.addEventListener("click", function () { P().tool = t.id; ctx.save(); ctx.syncInputs(); paintTools(); draw(); }); box.appendChild(b);
    });
    Array.prototype.forEach.call(box.children, function (b) { b.style.outline = b.getAttribute("data-hp-tool") === P().tool ? "2px solid var(--acc,#6af)" : ""; });
    var t = P().tool, show = function (id, on) { var e = $(id); if (e) e.hidden = !on; };
    show("hpRowRate", t === "raise" || t === "lower" || t === "noise"); show("hpRowHeight", t === "set" || t === "flatten" || t === "ridge" || t === "valley");
    show("hpRowRiver", t === "river"); show("hpRowNoise", t === "noise");
    var lab = $("hpHeightLabel"); if (lab) lab.textContent = t === "set" ? "Height to set (ft, absolute)" : t === "flatten" ? "Flatten to (ft, blank = height under the first point)" : t === "ridge" ? "Ridge crest height (ft)" : "Valley depth (ft)";
  }
  var toolHelp = { raise: "Add height under the brush (rate x strength per dab)", lower: "Remove height", smooth: "Blend towards the local average",
    flatten: "Level to one height (blank = the height where you start the stroke)", set: "Pull the ground to an absolute height", noise: "Add repeatable rough noise",
    ridge: "Raise a crest along the path; the radius is its half width", valley: "Cut a trough along the path", river: "Carve a channel along the path: draw it from upstream to downstream; the bed only falls and banks rise away from it" };

  // ---- stroke queue: one python round trip at a time, quiet (no jobs-folder entries, no log spam)
  function runJob(job) {
    return ctx.run(job).then(function (r) {
      if (!r.ok) { ctx.showError("Paint: " + job.label + ": " + r.error); busyMsg(""); return r; }
      ctx.showError(""); readPreview(); busyMsg(""); summary(); draw(); ctx.save(); return r;
    });
  }
  function enqueue(job) {
    queue = queue.then(function () { busyMsg(job.label + " ..."); return waitIdle().then(function () { return runJob(job); }); }).catch(function (e) { ctx.showError(String(e && e.message || e)); busyMsg(""); });
    return queue;
  }
  function waitIdle() { return new Promise(function (res) { var t = function () { if (!ctx.isBusy()) res(); else setTimeout(t, 120); }; t(); }); }
  function commit(strokes) {
    if (!strokes.length) return Promise.resolve();
    P().redo = []; P().unsaved = true;
    var job = VB.jobHpApply(ctx.state(), ctx.dirs(), strokes, "append");
    return enqueue(job).then(function () { pending = pending.filter(function (q) { return strokes.indexOf(q) < 0; }); applyN(); draw(); });   // the outline stays until the new preview is in
  }
  function applyN() { var e = $("hpApplyN"); if (e) e.textContent = pending.length ? " (" + pending.length + ")" : ""; }
  function finishStroke(pts) {
    var s; try { s = VB.hpStroke(ctx.state(), pts); } catch (e) { ctx.showError(e.message); return; }
    pending.push(s); if (P().auto_apply) commit([s]); else applyN();
    draw();
  }

  // ---- pointer handling
  function evFeet(ev) { var r = cv.getBoundingClientRect(), sx = (ev.clientX - r.left) * cv.width / r.width, sy = (ev.clientY - r.top) * cv.height / r.height; return { sx: sx, sy: sy, f: meta ? VB.hpScreenToFeet(meta, P().view, sx, sy) : [0, 0] }; }
  function bind() {
    cv.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    cv.addEventListener("pointerdown", function (ev) {
      if (!meta) return; var e = evFeet(ev); cv.setPointerCapture && cv.setPointerCapture(ev.pointerId);
      if (ev.button === 1 || ev.button === 2 || spaceDown || ev.shiftKey) { pan = { sx: e.sx, sy: e.sy, ox: P().view.ox, oy: P().view.oy }; cv.style.cursor = "grabbing"; return; }
      if (ev.button !== 0) return;
      drag = { pts: [e.f], last: e.f }; draw();
    });
    cv.addEventListener("pointermove", function (ev) {
      if (!meta) return; var e = evFeet(ev); hover = e.f;
      if (pan) { P().view.ox = pan.ox + (e.sx - pan.sx); P().view.oy = pan.oy + (e.sy - pan.sy); schedule(false); return; }
      if (drag) { var minD = Math.max((Number(P().radius_ft) || 30) * 0.08, meta.cell_ft * meta.factor * 0.5), dx = e.f[0] - drag.last[0], dy = e.f[1] - drag.last[1]; if (dx * dx + dy * dy >= minD * minD) { drag.pts.push(e.f); drag.last = e.f; } }
      readout(); schedule(false);
    });
    var up = function (ev) {
      if (pan) { pan = null; cv.style.cursor = "crosshair"; ctx.save(); return; }
      if (drag) { var pts = drag.pts; drag = null; finishStroke(pts); }
    };
    cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", function () { pan = null; drag = null; draw(); });
    cv.addEventListener("pointerleave", function () { hover = null; readout(); schedule(false); });
    cv.addEventListener("wheel", function (ev) {
      if (!meta) return; ev.preventDefault(); var e = evFeet(ev); if (ev.altKey) { var r = Math.min(Math.max((Number(P().radius_ft) || 30) * (ev.deltaY < 0 ? 1.12 : 1 / 1.12), 1), 2000); P().radius_ft = Math.round(r * 10) / 10; ctx.syncInputs(); }
      else P().view = Object.assign({}, P().view, VB.hpZoomAt(P().view, e.sx, e.sy, ev.deltaY < 0 ? 1.2 : 1 / 1.2));
      schedule(false); clearTimeout(bind.t); bind.t = setTimeout(ctx.save, 400);
    }, { passive: false });
    window.addEventListener("keydown", function (e) {
      var tag = (e.target && e.target.tagName) || ""; if (/INPUT|SELECT|TEXTAREA/.test(tag)) return;
      if (e.code === "Space" && tabOn() && isOpen()) { spaceDown = true; e.preventDefault(); }
      if ((e.ctrlKey || e.metaKey) && !e.altKey && tabOn() && isOpen()) {
        if (e.key === "z" || e.key === "Z") { e.preventDefault(); (e.shiftKey ? A.hp_redo : A.hp_undo)(); }
        else if (e.key === "y") { e.preventDefault(); A.hp_redo(); }
      }
    });
    window.addEventListener("keyup", function (e) { if (e.code === "Space") spaceDown = false; });
  }

  var A = {
    hp_tool_changed: function () { paintTools(); draw(); },
    hp_refresh: function () { return enqueue(VB.jobHpRefresh(ctx.state(), ctx.dirs())); },
    hp_fit: function () { if (!meta) return; P().view = Object.assign(VB.hpFit(meta, cv.width, cv.height), { fitFor: ctx.state().place }); ctx.save(); draw(); },
    hp_apply: function () { return commit(pending.slice()); },
    hp_undo: function () {
      var s = P().stats; if (!s || !(s.strokes > 0)) return;
      var d = ctx.dirs(), info = ctx.readJson(VB.hpWorkDir(d) + "/heightmap_edits.json", null), last = info && info.strokes && info.strokes[info.strokes.length - 1];
      if (last) { P().redo = (P().redo || []).concat([last]).slice(-50); }
      P().unsaved = true; return enqueue(VB.jobHpApply(ctx.state(), d, [], "undo-last"));
    },
    hp_redo: function () {
      var r = P().redo || []; if (!r.length) return; var s = r.pop(); P().redo = r; P().unsaved = true;
      return enqueue(VB.jobHpApply(ctx.state(), ctx.dirs(), [s], "append"));
    },
    hp_save: function () { P().rebuild_pack = false; return enqueue(VB.jobHpSave(ctx.state(), ctx.dirs())).then(function () { ctx.showError("Saved. Re-run the map / pack exports to see the edits there.", "warn"); }); },
    hp_save_pack: function () { var p = P(), was = p.rebuild_pack; p.rebuild_pack = true; var j = VB.jobHpSave(ctx.state(), ctx.dirs()); p.rebuild_pack = was; return ctx.startJob(j, function () { readPreview(); summary(); draw(); }); },
    hp_discard: function () { pending = []; applyN(); return enqueue(VB.jobHpDiscard(ctx.state(), ctx.dirs())); },
    hp_reset: function () {
      // window.confirm is unreliable in CEP panels (can return false at once or block), so arm with a first click and confirm with a second one within 6 s
      var b = document.querySelector('[data-act="hp_reset"]');
      if (!resetArmed) {
        resetArmed = true; if (b) { b.dataset.label = b.textContent; b.textContent = "Click again to remove ALL edits"; }
        ctx.showError("Reset removes ALL heightmap edits for this place (working copy and saved layer); the generated terrain is not touched. Click the button again within 6 s to confirm.", "warn");
        clearTimeout(resetTimer); resetTimer = setTimeout(disarmReset, 6000); return;
      }
      disarmReset(); ctx.showError("");
      pending = []; return enqueue(VB.jobHpReset(ctx.state(), ctx.dirs()));
    },
    hp_stats: function () { return enqueue(VB.jobHpStats(ctx.state(), ctx.dirs())); },
    hp_check: function () { return enqueue(VB.jobHpCheck(ctx.state(), ctx.dirs())); },
    hp_conform: function () {
      var c = P().check; if (!c || !(c.flagged_roads || []).length) return;
      P().redo = []; P().unsaved = true; return enqueue(VB.jobHpConform(ctx.state(), ctx.dirs(), null));
    }
  };

  // the Terrain tab was shown or the Paint section was opened: size the canvas, draw, and load the preview the first time
  function shown() {
    if (!ctx || !visible()) return;
    setTimeout(function () { if (!visible()) return; paint(); if (!meta && !ctx.isBusy()) A.hp_refresh(); }, 30);
  }
  function paint() {
    if (!ctx || !$("hpCanvas")) return;
    cv = $("hpCanvas"); var st = ctx.state(); paintTools(); summary();
    if (meta && loaded.place !== st.place) { H = D = meta = null; pending = []; }
    if (!meta || loaded.stamp !== P().stamp) { readPreview(); }
    draw(); readout();
  }
  function init(c) {
    ctx = c; cv = $("hpCanvas"); if (!cv) return;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    bind(); cv.style.cursor = "crosshair"; cv.style.touchAction = "none";
    ["hpContour", "hpExag", "hpShowDelta", "hpAz"].forEach(function (id) { var e = $(id); if (e) e.addEventListener("input", function () { schedule(true); }); });
    var det = $("hpDetails"); if (det) det.addEventListener("toggle", function () { if (det.open) shown(); else { spaceDown = false; disarmReset(); } });
    window.addEventListener("resize", function () { schedule(false); });
    paint();
  }
  window.VBHeightPaintUI = { init: init, paint: paint, shown: shown, actions: A };
})();
