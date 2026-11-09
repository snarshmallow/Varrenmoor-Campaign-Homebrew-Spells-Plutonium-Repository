// Waypoint (Photoshop Polygonal Lasso style) polygon editing, pure logic (no DOM, no Illustrator): window.VBWaypoint and Node tests.
// A waypoint polygon is {pts: [[x_ft, y_ft], ...], closed: bool}. The mini-map canvas in lasso_ui.js drives it with mouse clicks; the list mode edits the same object.
// View mapping: feet <-> canvas pixels with a {zoom, ox, oy} view over a map rectangle {x0, y0, x1, y1} in feet (feet y grows downward, exactly like the page mapping
// in VBCore.docToFt, so what is clicked on the canvas lands on the same feet the Illustrator captures use).
(function (root) {
  "use strict";
  var W = {};
  function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1]; return Math.sqrt(dx * dx + dy * dy); }
  function r1(v) { return Math.round(v * 10) / 10; }
  W.create = function (pts, closed) { return { pts: (pts || []).map(function (p) { return [p[0], p[1]]; }), closed: !!closed }; };
  W.clone = function (wp) { return W.create(wp.pts, wp.closed); };
  W.clear = function (wp) { wp.pts = []; wp.closed = false; return wp; };
  // index of the waypoint within tolFt of pt (nearest), or -1
  W.hit = function (wp, pt, tolFt) {
    var best = -1, bd = tolFt; for (var i = 0; i < wp.pts.length; i++) { var d = dist(wp.pts[i], pt); if (d <= bd) { bd = d; best = i; } } return best;
  };
  // click: add a waypoint; clicking the first point (>= 3 points) closes the polygon instead. Returns {action: "add"|"close"|"ignored", index}
  W.add = function (wp, pt, tolFt) {
    if (wp.closed) return { action: "ignored" };
    if (wp.pts.length >= 3 && dist(wp.pts[0], pt) <= tolFt) { wp.closed = true; return { action: "close", index: 0 }; }
    var last = wp.pts[wp.pts.length - 1]; if (last && dist(last, pt) < 1e-6) return { action: "ignored" };
    wp.pts.push([pt[0], pt[1]]); return { action: "add", index: wp.pts.length - 1 };
  };
  W.close = function (wp) { if (wp.pts.length < 3) return false; wp.closed = true; return true; };
  W.reopen = function (wp) { wp.closed = false; };
  W.move = function (wp, i, pt) { if (i < 0 || i >= wp.pts.length) return false; wp.pts[i] = [pt[0], pt[1]]; return true; };
  // remove the last waypoint (an unclosed polygon) or re-open a closed one
  W.removeLast = function (wp) { if (wp.closed) { wp.closed = false; return true; } if (!wp.pts.length) return false; wp.pts.pop(); return true; };
  W.remove = function (wp, i) { if (i < 0 || i >= wp.pts.length) return false; wp.pts.splice(i, 1); if (wp.pts.length < 3) wp.closed = false; return true; };
  W.reorder = function (wp, i, dir) { var j = i + dir; if (i < 0 || j < 0 || i >= wp.pts.length || j >= wp.pts.length) return false; var t = wp.pts[i]; wp.pts[i] = wp.pts[j]; wp.pts[j] = t; return true; };
  // distance from p to segment a-b
  W.segDist = function (p, a, b) {
    var dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy; if (l2 === 0) return dist(p, a);
    var t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2)); return dist(p, [a[0] + t * dx, a[1] + t * dy]);
  };
  // Shift+click: insert pt on the nearest edge (including the closing edge when closed) when within tolFt. Returns the new index or -1.
  W.insertOnEdge = function (wp, pt, tolFt) {
    var n = wp.pts.length; if (n < 2) return -1; var best = -1, bd = tolFt, m = wp.closed ? n : n - 1;
    for (var i = 0; i < m; i++) { var d = W.segDist(pt, wp.pts[i], wp.pts[(i + 1) % n]); if (d <= bd) { bd = d; best = i; } }
    if (best < 0) return -1; wp.pts.splice(best + 1, 0, [pt[0], pt[1]]); return best + 1;
  };
  W.area = function (wp) {
    if (wp.pts.length < 3) return 0; var a = 0, n = wp.pts.length;
    for (var i = 0; i < n; i++) { var p = wp.pts[i], q = wp.pts[(i + 1) % n]; a += p[0] * q[1] - q[0] * p[1]; } return Math.abs(a) / 2;
  };
  W.acres = function (wp) { return W.area(wp) / 43560; };
  W.length = function (wp) { var s = 0, n = wp.pts.length, m = wp.closed ? n : n - 1; for (var i = 0; i < m; i++) s += dist(wp.pts[i], wp.pts[(i + 1) % n]); return s; };
  // "12.5, 40" / "12.5 40" / "(12.5;40)", one waypoint per line -> {pts, errors}
  W.parseList = function (text) {
    var pts = [], errors = [], lines = String(text || "").split(/\r?\n/);
    lines.forEach(function (ln, i) {
      ln = ln.replace(/[()\[\]]/g, " ").replace(/^\s+|\s+$/g, ""); if (!ln) return;
      var m = ln.split(/[\s,;]+/).filter(Boolean).map(Number);
      if (m.length !== 2 || !isFinite(m[0]) || !isFinite(m[1])) errors.push("line " + (i + 1) + ": expected \"x, y\" but got \"" + ln + "\""); else pts.push([m[0], m[1]]);
    });
    return { pts: pts, errors: errors };
  };
  W.formatList = function (wp) { return wp.pts.map(function (p) { return r1(p[0]) + ", " + r1(p[1]); }).join("\n"); };
  // ---- view mapping. rect {x0,y0,x1,y1} in feet; view {zoom, ox, oy}: canvas px = (feet - rect.x0) * pxPerFt * zoom + ox; zoom is pixels per foot
  W.fit = function (rect, cw, ch, pad) {
    pad = pad == null ? 8 : pad; var w = Math.max(rect.x1 - rect.x0, 1), h = Math.max(rect.y1 - rect.y0, 1);
    var z = Math.min((cw - 2 * pad) / w, (ch - 2 * pad) / h); if (!(z > 0)) z = 1;
    return { zoom: z, ox: (cw - w * z) / 2, oy: (ch - h * z) / 2 };
  };
  W.toScreen = function (rect, view, ft) { return [(ft[0] - rect.x0) * view.zoom + view.ox, (ft[1] - rect.y0) * view.zoom + view.oy]; };
  W.toFeet = function (rect, view, s) { return [rect.x0 + (s[0] - view.ox) / view.zoom, rect.y0 + (s[1] - view.oy) / view.zoom]; };
  W.zoomAt = function (view, sx, sy, factor, minZ, maxZ) {
    var z = Math.min(Math.max(view.zoom * factor, minZ || 0.001), maxZ || 1000), k = z / view.zoom;
    return { zoom: z, ox: sx - (sx - view.ox) * k, oy: sy - (sy - view.oy) * k };
  };
  // the single anchor selected in Illustrator (host get_selection report) as feet; fn maps document points to feet. {ok, pt} | {ok:false, error}
  W.anchorFromSelection = function (sel, docToFt) {
    var paths = (sel && sel.paths) || [], found = [];
    paths.forEach(function (p) {
      if (p.in_sel === false || p.lasso) return;
      (p.selected || []).forEach(function (k) { if (p.points[k]) found.push(p.points[k].a); });
      if (!(p.selected || []).length && p.points.length === 1) found.push(p.points[0].a);
    });
    if (found.length !== 1) return { ok: false, error: found.length ? "select exactly ONE anchor point (" + found.length + " selected)" : "no anchor point selected: pick one with the Direct Selection tool (A)" };
    var f = docToFt(found[0]); return { ok: true, pt: [r1(f[0]), r1(f[1])] };
  };
  root.VBWaypoint = W;
  if (typeof module !== "undefined" && module.exports) module.exports = W;
})(typeof window !== "undefined" ? window : this);
