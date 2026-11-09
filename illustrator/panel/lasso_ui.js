// Plugin lasso UI: one shared helper that adds the Lasso rows (draw, select inside, clear, adjust: feather / expand / contract / smooth / invert / border / add / subtract / intersect)
// under every polygon Capture button. Logic in lib/lasso.js + lib/polyops.js, jobs in lib/lasso.js, host actions lasso_* in jsx/host.jsx.
// Loaded before main.js; main.js calls VBLassoUI.init(ctx) once and VBLassoUI.paint() from refreshAll.
(function () {
  "use strict";
  var VB = window.VBCore, L = window.VBLasso, O = window.VBPolyOps, W = window.VBWaypoint, ctx = null;
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
    draw: function (act) { return ctx.startJob(L.jobStart({ selectTool: !!(rows[act] && rows[act].autoTool && rows[act].autoTool.checked) })); },
    inside: function (act) {
      var pts = cur(act); if (!pts) { say("no polygon yet: capture one first, then select what is inside", "warn"); return null; }
      var r = rows[act]; return ctx.startJob(L.jobInside(ctx.state(), ctx.dirs(), { poly: pts, mode: r.mode.value, filter: (r.filter.value || "").split(",").map(function (s) { return s.trim(); }).filter(Boolean) }));
    },
    clear: function (act) { work[act] = null; return ctx.startJob(L.jobClear({ removeLayer: !!(rows[act] && rows[act].rmLayer && rows[act].rmLayer.checked) }), paint); },
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
  function hostBlocked() {   // a lasso host call is still pending in Illustrator (or a job runs): never queue another one behind it
    var hp = ctx.hostPending && ctx.hostPending(); if (hp) return "Illustrator is still busy with " + hp.action + " (" + Math.round((Date.now() - hp.since) / 1000) + " s). The lasso buttons that talk to Illustrator are disabled until it answers; the waypoint map keeps working.";
    return ctx.isBusy && ctx.isBusy() ? "another job is running: wait for it or press Cancel" : "";
  }
  function gate() {
    var msg = hostBlocked(), btns = document.querySelectorAll(".lassoRow button.needsHost, .wpBox button.needsHost");
    Array.prototype.forEach.call(btns, function (b) { b.disabled = !!msg; });
    Array.prototype.forEach.call(document.querySelectorAll(".lassoBusy"), function (e) { e.textContent = msg; e.hidden = !msg; });
  }
  function btn(label, title, fn, cls, nohost) { var b = document.createElement("button"); b.textContent = label; b.title = title; if (cls) b.className = cls; if (!nohost) b.classList.add("needsHost"); b.addEventListener("click", function () { var bm = nohost ? "" : hostBlocked(); if (bm) { say(bm, "warn"); return; } try { var r = fn(); if (r && r.catch) r.catch(function (e) { say(String(e && e.message || e)); }); } catch (e) { say(String(e && e.message || e)); } }); return b; }
  function lab(text, input) { var l = document.createElement("label"); l.appendChild(document.createTextNode(text + " ")); l.appendChild(input); return l; }
  function inp(val, w, min) { var i = document.createElement("input"); i.type = "number"; i.step = "any"; i.value = val; i.style.width = w || "64px"; if (min != null) i.min = min; return i; }
  // ================= Waypoint lasso (click on map): Photoshop Polygonal Lasso on an in-panel map canvas; never touches Illustrator until Preview / Capture(+draw) =================
  var wps = {};           // act -> {wp: {pts, closed}, view, rect, bg, el: {...}, cursor, drag, pan}
  var bgCache = { key: null, bg: null };
  var HIT_PX = 9;
  function rectFt() { var b = boundsFt(); return b.x1 > b.x0 && b.y1 > b.y0 ? b : { x0: 0, y0: 0, x1: 2400, y1: 1500 }; }
  // background: the place underlay PNG when present, else the shaded relief of the Paint tab's preview, else a plain grid. Returns {src, rect, label} or null
  function loadBackground(done) {
    var d = ctx.dirs(), key = d.world, fs = ctx.fs;
    if (bgCache.key === key && bgCache.bg) return done(bgCache.bg);
    var finish = function (bg) { bgCache = { key: key, bg: bg }; done(bg); };
    var tryRelief = function () {
      try {
        var dir = VB.hpPreviewDir(d), m = ctx.readJson(dir + "/preview.json", null); if (!m || !fs) return finish(null);
        var H = VB.hpReadBin(fs.readFileSync(dir + "/preview_h.bin")); if (H.length !== m.pw * m.ph) return finish(null);
        var px = VB.hpRender(H, m.pw, m.ph, { cell_ft: m.cell_ft * m.factor, lo: m.elev_min, hi: m.elev_max, exag: 1, contour_ft: 0, delta: null, azimuth: 315 });
        var c = document.createElement("canvas"); c.width = m.pw; c.height = m.ph; c.getContext("2d").putImageData(new ImageData(new Uint8ClampedArray(px), m.pw, m.ph), 0, 0);
        finish({ src: c, rect: VB.hpImageRect(m), label: "terrain relief" });   // pixels centred on the heightmap nodes (north up, east right, like the map)
      } catch (e) { finish(null); }
    };
    try {
      var f = d.world + "/underlay/background.png";
      if (fs && fs.existsSync(f) && fs.statSync(f).size < 24 * 1024 * 1024) {
        var img = new Image(); img.onload = function () { finish({ src: img, rect: rectFt(), label: "underlay" }); }; img.onerror = tryRelief;
        img.src = "data:image/png;base64," + fs.readFileSync(f).toString("base64"); return;
      }
    } catch (e) { /* fall through */ }
    tryRelief();
  }
  // water / roads / buildings outlines (Paint preview's preview_features.json, world feet) so the map canvas lines up with the Illustrator map
  var featCache = { key: null, f: null };
  function wpFeatures(g, r, v) {
    var d = ctx.dirs(), p = VB.hpFeaturesPath(d), fs = ctx.fs, key = null;
    try { key = fs && fs.existsSync(p) ? p + ":" + fs.statSync(p).mtimeMs : null; } catch (e) { key = null; }
    if (!key) return;
    if (featCache.key !== key) featCache = { key: key, f: ctx.readJson(p, null) };
    var f = featCache.f; if (!f) return;
    var line = function (pts, closed) { g.beginPath(); pts.forEach(function (q, i) { var s = W.toScreen(r, v, q); if (i) g.lineTo(s[0], s[1]); else g.moveTo(s[0], s[1]); }); if (closed) g.closePath(); };
    g.lineWidth = 1;
    (f.water || []).forEach(function (w) { line(w.points, w.closed); g.strokeStyle = "rgba(70,150,255,.9)"; g.stroke(); });
    (f.roads || []).concat(f.bridges || []).forEach(function (w) { line(w.points, false); g.strokeStyle = "rgba(235,205,150,.9)"; g.stroke(); });
    (f.buildings || []).forEach(function (b) { line(b.polygon, true); g.fillStyle = "rgba(255,255,255,.55)"; g.fill(); });
  }
  function wpEntry(act) { return wps[act] || (wps[act] = { wp: W.create(), view: null, rect: null, bg: null, el: {}, cursor: null, drag: null, pan: null }); }
  function wpDraw(act) {
    var e = wpEntry(act), cv = e.el.cv; if (!cv || !cv.clientWidth) return;
    var w = Math.max(cv.parentNode.clientWidth - 2, 200); if (cv.width !== w) { cv.width = w; cv.height = Math.round(Math.min(w * 0.7, 420)); e.view = null; }
    e.rect = e.rect || rectFt(); if (!e.view) e.view = W.fit(e.rect, cv.width, cv.height);
    var g = cv.getContext("2d"), v = e.view, r = e.rect, tl = W.toScreen(r, v, [r.x0, r.y0]), br = W.toScreen(r, v, [r.x1, r.y1]);
    g.fillStyle = "#202020"; g.fillRect(0, 0, cv.width, cv.height); g.fillStyle = "#2c3a2c"; g.fillRect(tl[0], tl[1], br[0] - tl[0], br[1] - tl[1]);
    if (e.bg && e.bg.src) { var a = W.toScreen(r, v, [e.bg.rect.x0, e.bg.rect.y0]), b = W.toScreen(r, v, [e.bg.rect.x1, e.bg.rect.y1]); g.imageSmoothingEnabled = true; try { g.drawImage(e.bg.src, a[0], a[1], b[0] - a[0], b[1] - a[1]); } catch (er) { /* bad image */ } }
    wpFeatures(g, r, v);
    var step = v.zoom * 100 < 14 ? 500 : 100; g.strokeStyle = "rgba(255,255,255,.12)"; g.lineWidth = 1; g.beginPath();
    for (var x = Math.ceil(r.x0 / step) * step; x <= r.x1; x += step) { var sx = W.toScreen(r, v, [x, 0])[0]; g.moveTo(sx, tl[1]); g.lineTo(sx, br[1]); }
    for (var y = Math.ceil(r.y0 / step) * step; y <= r.y1; y += step) { var sy = W.toScreen(r, v, [0, y])[1]; g.moveTo(tl[0], sy); g.lineTo(br[0], sy); }
    g.stroke(); g.strokeStyle = "#000"; g.strokeRect(tl[0] - 0.5, tl[1] - 0.5, br[0] - tl[0] + 1, br[1] - tl[1] + 1);
    var pts = e.wp.pts, sp = pts.map(function (p) { return W.toScreen(r, v, p); });
    if (sp.length) {
      if (e.wp.closed && sp.length >= 3) { g.beginPath(); sp.forEach(function (q, i) { if (i) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); }); g.closePath(); g.fillStyle = "rgba(255,0,170,.16)"; g.fill(); }
      g.strokeStyle = "#ff00aa"; g.lineWidth = 1.5; g.setLineDash([6, 4]); g.beginPath(); sp.forEach(function (q, i) { if (i) g.lineTo(q[0], q[1]); else g.moveTo(q[0], q[1]); });
      if (e.wp.closed) g.closePath(); g.stroke();
      if (!e.wp.closed && e.cursor && !e.drag && !e.pan) { var c = W.toScreen(r, v, e.cursor), l = sp[sp.length - 1]; g.strokeStyle = "rgba(255,0,170,.6)"; g.beginPath(); g.moveTo(l[0], l[1]); g.lineTo(c[0], c[1]); g.stroke(); }
      g.setLineDash([]); g.font = "11px sans-serif"; g.textBaseline = "middle";
      sp.forEach(function (q, i) {
        g.beginPath(); g.arc(q[0], q[1], i === 0 ? 5.5 : 4, 0, 6.2832); g.fillStyle = i === 0 ? "#fff" : "#ff00aa"; g.fill(); g.strokeStyle = "#000"; g.lineWidth = 1; g.stroke();
        g.fillStyle = "#fff"; g.strokeStyle = "#000"; g.lineWidth = 3; g.strokeText(String(i + 1), q[0] + 7, q[1] - 7); g.fillText(String(i + 1), q[0] + 7, q[1] - 7);
      });
    }
    wpReadout(act);
  }
  function wpReadout(act) {
    var e = wpEntry(act), n = e.wp.pts.length, t = n + " waypoint" + (n === 1 ? "" : "s") + (e.wp.closed ? ", closed" : (n >= 3 ? ", open (click the first point or press Enter to close)" : ""));
    if (n >= 3) { var a = W.area(e.wp); t += "  |  " + (a / 43560 >= 0.1 ? (a / 43560).toFixed(2) + " acres" : Math.round(a) + " ft2") + (e.wp.closed ? "" : " if closed"); }
    if (e.cursor) t += "  |  x " + e.cursor[0].toFixed(0) + ", y " + e.cursor[1].toFixed(0) + " ft";
    if (e.el.stat) e.el.stat.textContent = t;
    if (e.el.list && document.activeElement !== e.el.list) e.el.list.value = W.formatList(e.wp);
    wpRows(act);
  }
  function wpRows(act) {
    var e = wpEntry(act), box = e.el.rows; if (!box) return; var sig = JSON.stringify(e.wp.pts); if (box.dataset.sig === sig) return; box.dataset.sig = sig;
    while (box.firstChild) box.removeChild(box.firstChild);
    e.wp.pts.forEach(function (p, i) {
      var row = document.createElement("div"); row.className = "wpRow"; row.appendChild(document.createTextNode((i + 1) + ": " + p[0].toFixed(1) + ", " + p[1].toFixed(1) + " ft "));
      var mk = function (t, ti, fn) { var b = document.createElement("button"); b.textContent = t; b.title = ti; b.addEventListener("click", function () { fn(); wpDraw(act); }); row.appendChild(b); };
      mk("up", "Move earlier", function () { W.reorder(e.wp, i, -1); }); mk("down", "Move later", function () { W.reorder(e.wp, i, 1); }); mk("x", "Delete this waypoint", function () { W.remove(e.wp, i); });
      box.appendChild(row);
    });
  }
  function wpSize(cv, ev) { var r = cv.getBoundingClientRect(); return [(ev.clientX - r.left) * cv.width / r.width, (ev.clientY - r.top) * cv.height / r.height]; }
  function wpBind(act) {
    var e = wpEntry(act), cv = e.el.cv, spaceDown = false;
    var feet = function (ev) { var s = wpSize(cv, ev); return { s: s, f: W.toFeet(e.rect, e.view, s) }; };
    cv.addEventListener("contextmenu", function (ev) { ev.preventDefault(); });
    cv.addEventListener("pointerdown", function (ev) {
      cv.focus(); if (!e.view) return; var q = feet(ev); cv.setPointerCapture && cv.setPointerCapture(ev.pointerId);
      if (ev.button === 1 || spaceDown) { e.pan = { sx: q.s[0], sy: q.s[1], ox: e.view.ox, oy: e.view.oy }; return; }
      if (ev.button === 2) { W.removeLast(e.wp); wpDraw(act); return; }
      if (ev.button !== 0) return;
      var tol = HIT_PX / e.view.zoom;
      if (ev.shiftKey) { var ix = W.insertOnEdge(e.wp, q.f, tol * 1.5); if (ix >= 0) e.drag = { i: ix, moved: true }; wpDraw(act); return; }
      var h = W.hit(e.wp, q.f, tol);
      if (h >= 0) { e.drag = { i: h, moved: false, sx: q.s[0], sy: q.s[1], closeOnUp: h === 0 && !e.wp.closed && e.wp.pts.length >= 3 }; return; }
      if (!e.wp.closed) { W.add(e.wp, q.f, tol); wpDraw(act); }
    });
    cv.addEventListener("pointermove", function (ev) {
      if (!e.view) return; var q = feet(ev); e.cursor = q.f;
      if (e.pan) { e.view.ox = e.pan.ox + q.s[0] - e.pan.sx; e.view.oy = e.pan.oy + q.s[1] - e.pan.sy; }
      else if (e.drag) { var d = e.drag; if (!d.moved && Math.abs(q.s[0] - d.sx) + Math.abs(q.s[1] - d.sy) > 3) { d.moved = true; d.closeOnUp = false; } if (d.moved) W.move(e.wp, d.i, q.f); }
      wpDraw(act);
    });
    var up = function () { var d = e.drag; e.drag = null; e.pan = null; if (d && d.closeOnUp && !d.moved) W.close(e.wp); wpDraw(act); };
    cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", function () { e.drag = null; e.pan = null; wpDraw(act); });
    cv.addEventListener("pointerleave", function () { e.cursor = null; wpDraw(act); });
    cv.addEventListener("wheel", function (ev) { if (!e.view) return; ev.preventDefault(); var s = wpSize(cv, ev); e.view = W.zoomAt(e.view, s[0], s[1], ev.deltaY < 0 ? 1.2 : 1 / 1.2); wpDraw(act); }, { passive: false });
    cv.addEventListener("keydown", function (ev) {
      if (ev.code === "Space") { spaceDown = true; ev.preventDefault(); return; }
      if (ev.key === "Enter") { W.close(e.wp); ev.preventDefault(); }
      else if (ev.key === "Backspace" || ev.key === "Delete") { W.removeLast(e.wp); ev.preventDefault(); }
      else if (ev.key === "Escape") { W.clear(e.wp); ev.preventDefault(); }
      else return;
      wpDraw(act);
    });
    cv.addEventListener("keyup", function (ev) { if (ev.code === "Space") spaceDown = false; });
  }
  function wpPolygon(act) {   // cleaned feet polygon of the editor, or null (message already shown)
    var e = wpEntry(act); if (e.wp.pts.length < 3) { say("Waypoint lasso: place at least 3 waypoints", "warn"); return null; }
    var c = L.clean(e.wp.pts, { closed: true }); if (!c.ok) { say("Waypoint lasso: " + c.error, "warn"); return null; }
    (c.warnings || []).forEach(function (m) { if (ctx.logLine) ctx.logLine("note: " + m); });
    return c;
  }
  function wpCapture(act) {
    var e = wpEntry(act), c = wpPolygon(act); if (!c) return null; var cfg = CAPTURES[act], st = ctx.state();
    VB.setPath(st, cfg.store, c.pts.map(function (q) { return [VB.round1(q[0]), VB.round1(q[1])]; }));
    VB.setPath(st, cfg.src, "waypoint lasso (" + e.wp.pts.length + " waypoints, " + L.statusText(c.pts, true) + ")");
    work[act] = null; ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); paint();
    if (ctx.logLine) ctx.logLine("waypoint lasso captured: " + L.describe(c.stats) + " -> " + cfg.store);
    if (e.el.draw && e.el.draw.checked) return ctx.startJob(L.jobDraw(st, ctx.dirs(), { core: c.pts, feather: num(rows[act] && rows[act].feather, 0), dots: e.wp.pts }));
    return null;
  }
  function buildWaypoint(act) {
    var e = wpEntry(act), box = document.createElement("details"); box.className = "wpBox";
    var sum = document.createElement("summary"); sum.innerHTML = "<b>Waypoint lasso (click on map)</b> <span class=\"note\">Photoshop Polygonal Lasso: Illustrator is not touched until you press Preview</span>"; box.appendChild(sum);
    var help = document.createElement("div"); help.className = "note"; help.textContent = "Click = add waypoint (straight segments). Click the first point or Enter = close. Right-click / Backspace = remove last. Drag = move a waypoint. Shift+click = insert on an edge. Esc = cancel. Wheel = zoom, middle-drag or Space+drag = pan.";
    var cv = document.createElement("canvas"); cv.width = 320; cv.height = 220; cv.tabIndex = 0; cv.style.cssText = "width:100%;display:block;border:1px solid var(--line,#444);background:#202020;cursor:crosshair;touch-action:none"; cv.setAttribute("aria-label", "Waypoint lasso map");
    var stat = document.createElement("div"); stat.className = "tag"; stat.style.whiteSpace = "pre-wrap";
    var bar = document.createElement("div"); bar.className = "btns";
    bar.appendChild(btn("Undo last", "Remove the last waypoint (or re-open a closed polygon)", function () { W.removeLast(e.wp); wpDraw(act); }, "", true));
    bar.appendChild(btn("Close polygon", "Join the last waypoint to the first", function () { if (!W.close(e.wp)) say("need at least 3 waypoints to close", "warn"); wpDraw(act); }, "", true));
    bar.appendChild(btn("Clear", "Remove all waypoints", function () { W.clear(e.wp); wpDraw(act); }, "", true));
    bar.appendChild(btn("Fit", "Show the whole map", function () { e.view = null; wpDraw(act); }, "", true));
    bar.appendChild(btn("Load stored polygon", "Copy the captured polygon into the editor to adjust its corners", function () { var v = VB.getPath(ctx.state(), CAPTURES[act].store); if (!v || !v.length) return say("nothing captured yet", "warn"); e.wp = W.create(v, true); wpDraw(act); }, "", true));
    var bar2 = document.createElement("div"); bar2.className = "btns";
    e.el.draw = document.createElement("input"); e.el.draw.type = "checkbox"; e.el.draw.checked = false;
    bar2.appendChild(btn("Capture waypoints", "Store the polygon like any other capture (same state keys); Illustrator is only touched when 'also draw in Illustrator' is ticked", function () { return wpCapture(act); }, "primary", true));
    bar2.appendChild(lab("also draw in Illustrator", e.el.draw));
    bar2.appendChild(btn("Preview in Illustrator", "Draw numbered-order dots and the dashed polygon on layer VB LASSO (one call)", function () {
      var c = wpPolygon(act); if (!c) return null; return ctx.startJob(L.jobDraw(ctx.state(), ctx.dirs(), { core: c.pts, feather: num(rows[act] && rows[act].feather, 0), dots: e.wp.pts }));
    }));
    bar2.appendChild(btn("Add waypoint from selected anchor", "Read the one anchor point selected in Illustrator (Direct Selection tool) and append it", function () {
      var holder = { out: {} };
      return ctx.startJob(L.jobAnchor(ctx.state(), ctx.dirs(), holder), function (res) { if (res && res.ok && holder.out.pt) { W.add(e.wp, holder.out.pt, 0); wpDraw(act); } });
    }));
    var busy = document.createElement("div"); busy.className = "note lassoBusy"; busy.hidden = true; busy.style.color = "var(--warn,#c60)";
    var lst = document.createElement("textarea"); lst.rows = 4; lst.style.width = "100%"; lst.placeholder = "x, y (feet) per line; paste coordinates here"; e.el.list = lst;
    var bar3 = document.createElement("div"); bar3.className = "btns";
    bar3.appendChild(btn("Apply list", "Replace the waypoints by the coordinates in the box", function () {
      var r = W.parseList(lst.value); if (r.errors.length) return say(r.errors[0], "warn"); if (!r.pts.length) return say("no coordinates in the list", "warn"); e.wp = W.create(r.pts, false); wpDraw(act);
    }, "", true));
    var rowsEl = document.createElement("div"); rowsEl.className = "wpRows"; e.el.rows = rowsEl;
    e.el.cv = cv; e.el.stat = stat;
    [help, cv, stat, bar, bar2, busy, lst, bar3, rowsEl].forEach(function (n) { box.appendChild(n); });
    wpBind(act);
    box.addEventListener("toggle", function () { if (!box.open) return; e.rect = rectFt(); e.view = null; loadBackground(function (bg) { e.bg = bg; wpDraw(act); }); setTimeout(function () { wpDraw(act); }, 30); });
    return box;
  }
  window.addEventListener("resize", function () { Object.keys(wps).forEach(function (a) { var e = wps[a]; if (e.el.cv && e.el.cv.clientWidth) { e.view = null; wpDraw(a); } }); });

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
    row1.appendChild(btn("Draw lasso", "Prepares the helper layer VB LASSO. Then press P (Pen tool) in Illustrator: " + L.POLY_HINT + ". Then press Capture", function () { return A.draw(act); }));
    row1.appendChild(btn("Select inside", "Select the objects inside the lasso on the chosen layers", function () { return A.inside(act); }));
    row1.appendChild(r.mode); row1.appendChild(r.filter);
    row1.appendChild(btn("Clear lasso", "Remove the lasso paths on VB LASSO (the layer stays unless the box is ticked) and any unapplied adjustment", function () { return A.clear(act); }));
    r.rmLayer = document.createElement("input"); r.rmLayer.type = "checkbox"; row1.appendChild(lab("also delete layer", r.rmLayer));
    row1.appendChild(r.stat);
    r.autoTool = document.createElement("input"); r.autoTool.type = "checkbox"; r.autoTool.title = "Off by default: selecting a tool from a script has been seen to hang Illustrator. Press P yourself.";
    var hint = document.createElement("div"); hint.className = "note"; hint.textContent = "Polygonal lasso: press P for the Pen tool, then " + L.POLY_HINT.replace(/^Pen tool \(P\): /, "") + ".";
    var busy = document.createElement("div"); busy.className = "note lassoBusy"; busy.hidden = true; busy.style.color = "var(--warn,#c60)";
    row1.appendChild(lab("auto-select Pen tool", r.autoTool)); row1.appendChild(hint); row1.appendChild(busy);
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
    if (W) { var box = buildWaypoint(act); if (box) host.parentNode.insertBefore(box, row3.nextSibling); }
  }
  function init(c) {
    ctx = c;
    if (!L || !O || !VB) return;
    Object.keys(CAPTURES).forEach(build);
    paint(); gate(); setInterval(gate, 1000);
  }
  window.VBLassoUI = { init: init, paint: paint, gate: gate, _work: work, _wp: wps };
})();
