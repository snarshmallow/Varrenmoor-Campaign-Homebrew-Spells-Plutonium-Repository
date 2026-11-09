// Lasso / polygon capture, pure logic (no DOM, no Illustrator, no Node APIs): loaded by the panel (window.VBLasso) and by Node tests.
// Turns what the host reports about the user's Illustrator selection into one clean polygon in feet:
// priority  (1) partial anchor selection (>= 3 selected anchors of one path = a native Lasso/Direct Selection pick)  -> anchors in drawing order
//           (2) one or more selected closed paths (the largest wins)   (3) selected open path(s) (auto-closed)
//           (4) the newest path on the VB LASSO layer                  (5) anchors picked across several paths (ordered by angle, with a warning)
//           (6) the fallback layer (e.g. TERRAIN AREA) the host read when nothing was selected.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  var L = {};
  L.LAYER = "VB LASSO";
  L.ACRE_FT2 = 43560;
  L.MAX_VERTS = 300;

  function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1]; return Math.sqrt(dx * dx + dy * dy); }
  function signedArea(p) { var a = 0; for (var i = 0; i < p.length; i++) { var q = p[(i + 1) % p.length]; a += p[i][0] * q[1] - q[0] * p[i][1]; } return a / 2; }
  L.area = function (p) { return Math.abs(signedArea(p)); };
  L.bbox = function (p) {
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (var i = 0; i < p.length; i++) { x0 = Math.min(x0, p[i][0]); y0 = Math.min(y0, p[i][1]); x1 = Math.max(x1, p[i][0]); y1 = Math.max(y1, p[i][1]); }
    return { x0: x0, y0: y0, x1: x1, y1: y1, w: x1 - x0, h: y1 - y0 };
  };
  L.centroid = function (p) { var x = 0, y = 0; for (var i = 0; i < p.length; i++) { x += p[i][0]; y += p[i][1]; } return [x / p.length, y / p.length]; };
  // even-odd point in polygon (boundary counts as inside only by luck: callers use centres / vertices)
  L.pointInPolygon = function (pt, poly) {
    var inside = false, x = pt[0], y = pt[1];
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
      if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
    }
    return inside;
  };
  // drop a repeated closing vertex and consecutive points closer than tol
  L.dedupe = function (p, tol) {
    tol = tol || 0.05; var out = [];
    for (var i = 0; i < p.length; i++) if (!out.length || dist(out[out.length - 1], p[i]) > tol) out.push(p[i]);
    while (out.length > 1 && dist(out[0], out[out.length - 1]) <= tol) out.pop();
    return out;
  };
  // order points counter-clockwise by angle around their centroid (anchors from a native Lasso have no meaningful order)
  L.orderByAngle = function (p) {
    var c = L.centroid(p);
    return p.slice().sort(function (a, b) { return Math.atan2(a[1] - c[1], a[0] - c[0]) - Math.atan2(b[1] - c[1], b[0] - c[0]); });
  };
  function perpDist(p, a, b) {
    var dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    if (l2 === 0) return dist(p, a);
    var t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2));
    return dist(p, [a[0] + t * dx, a[1] + t * dy]);
  }
  function dpOpen(pts, tol) {   // iterative Douglas-Peucker on an open chain, keeps both ends
    var n = pts.length; if (n < 3) return pts.slice();
    var keep = []; for (var i = 0; i < n; i++) keep.push(false);
    keep[0] = keep[n - 1] = true;
    var stack = [[0, n - 1]];
    while (stack.length) {
      var seg = stack.pop(), s = seg[0], e = seg[1], md = -1, mi = -1;
      for (var k = s + 1; k < e; k++) { var d = perpDist(pts[k], pts[s], pts[e]); if (d > md) { md = d; mi = k; } }
      if (md > tol && mi > 0) { keep[mi] = true; stack.push([s, mi]); stack.push([mi, e]); }
    }
    var out = []; for (var j = 0; j < n; j++) if (keep[j]) out.push(pts[j]);
    return out;
  }
  // closed ring: split at vertex 0 and the vertex farthest from it, simplify both halves
  L.simplify = function (p, tol) {
    if (p.length < 4 || !(tol > 0)) return p.slice();
    var fi = 0, fd = -1; for (var i = 1; i < p.length; i++) { var d = dist(p[0], p[i]); if (d > fd) { fd = d; fi = i; } }
    var a = dpOpen(p.slice(0, fi + 1), tol), b = dpOpen(p.slice(fi).concat([p[0]]), tol);
    return a.concat(b.slice(1, b.length - 1));
  };
  // tolerance in feet scales with the polygon size (about 0.2 % of the bounding diagonal, 0.3 .. 40 ft)
  L.tolFor = function (p) { var b = L.bbox(p), diag = Math.sqrt(b.w * b.w + b.h * b.h); return Math.max(0.3, Math.min(40, diag * 0.002)); };
  L.simplifyAuto = function (p, maxVerts) {
    maxVerts = maxVerts || L.MAX_VERTS;
    var tol = L.tolFor(p), q = L.simplify(p, tol), guard = 0;
    while (q.length > maxVerts && guard++ < 40) { tol *= 1.5; q = L.simplify(p, tol); }
    return { pts: q, tol: tol };
  };
  // proper segment crossing (shared endpoints of neighbouring segments do not count)
  function cross(o, a, b) { return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]); }
  function segX(p1, p2, p3, p4) {
    var d1 = cross(p3, p4, p1), d2 = cross(p3, p4, p2), d3 = cross(p1, p2, p3), d4 = cross(p1, p2, p4);
    if (((d1 > 0 && d2 < 0) || (d1 < 0 && d2 > 0)) && ((d3 > 0 && d4 < 0) || (d3 < 0 && d4 > 0))) {
      var t = d3 / (d3 - d4); return [p3[0] + t * (p4[0] - p3[0]), p3[1] + t * (p4[1] - p3[1])];
    }
    return null;
  }
  // first crossing: {i, j, pt} (segments i->i+1 and j->j+1, i < j) or null
  L.findCrossing = function (p) {
    var n = p.length;
    for (var i = 0; i < n; i++) {
      var a = p[i], b = p[(i + 1) % n];
      for (var j = i + 2; j < n; j++) {
        if (i === 0 && j === n - 1) continue;
        var x = segX(a, b, p[j], p[(j + 1) % n]); if (x) return { i: i, j: j, pt: x };
      }
    }
    return null;
  };
  L.selfIntersects = function (p) { return !!L.findCrossing(p); };
  // loop removal: at a crossing the ring splits in two loops, keep the larger; repeat. Returns {pts, fixed, ok}
  L.fixSelfIntersections = function (p) {
    var q = p.slice(), fixed = 0;
    for (var g = 0; g < 30; g++) {
      var c = L.findCrossing(q); if (!c) return { pts: q, fixed: fixed, ok: true };
      var loopA = [c.pt].concat(q.slice(c.i + 1, c.j + 1));
      var loopB = [c.pt].concat(q.slice(c.j + 1), q.slice(0, c.i + 1));
      q = L.area(loopA) >= L.area(loopB) ? loopA : loopB; q = L.dedupe(q, 0.01); fixed++;
      if (q.length < 3) return { pts: q, fixed: fixed, ok: false };
    }
    return { pts: q, fixed: fixed, ok: !L.findCrossing(q) };
  };

  // ---- page (Illustrator document points) <-> feet; the same mapping every other capture uses
  L.docToFt = function (view, artboard, pt) { var f = VB.docToFt(view, artboard, pt); return [VB.round1(f[0]), VB.round1(f[1])]; };
  L.ftToDoc = function (view, artboard, ft) { return VB.ftToDoc(view, artboard, ft); };

  // ---- finishing: dedupe, simplify, fix, validate. opts: {closed:true, maxVerts}. Returns {ok, pts, warnings, stats} | {ok:false, error}
  L.clean = function (raw, opts) {
    opts = opts || {}; var warnings = [], p = L.dedupe(raw, 0.05);
    if (p.length < 3) return { ok: false, error: "need at least 3 distinct points, got " + p.length };
    var repair = function (q) {
      if (!L.selfIntersects(q)) return { ok: true, pts: q };
      var f = L.fixSelfIntersections(q);
      if (!f.ok || f.pts.length < 3 || L.area(f.pts) < 1) return { ok: false, error: "the outline crosses itself and cannot be repaired automatically: redraw it without crossing lines" };
      warnings.push("the outline crossed itself: removed " + f.fixed + " loop(s), kept the larger part"); return { ok: true, pts: f.pts };
    };
    var r = repair(p); if (!r.ok) return r; p = r.pts;
    if (L.area(p) < 1) return { ok: false, error: "the polygon has no area (points are collinear or on top of each other)" };
    var before = p.length, s = L.simplifyAuto(p, opts.maxVerts);
    p = L.dedupe(s.pts, 0.05);
    if (p.length < before) warnings.push("simplified " + before + " -> " + p.length + " vertices (tolerance " + (Math.round(s.tol * 10) / 10) + " ft)");
    if (p.length < 3 || L.area(p) < 1) return { ok: false, error: "after simplifying the polygon has no area" };
    r = repair(p); if (!r.ok) return r; p = r.pts;
    return { ok: true, pts: p, warnings: warnings, stats: L.stats(p) };
  };
  L.stats = function (p) {
    var a = L.area(p), b = L.bbox(p);
    return { n: p.length, area_ft2: Math.round(a), acres: Math.round(a / L.ACRE_FT2 * 100) / 100, w_ft: Math.round(b.w), h_ft: Math.round(b.h) };
  };
  L.describe = function (st) { return st.n + " points, " + (st.acres >= 0.1 ? st.acres + " acres" : st.area_ft2 + " ft2") + ", " + st.w_ft + " x " + st.h_ft + " ft"; };
  // status line next to every Capture button: "polygon: 12 points, 1.4 acres"
  L.statusText = function (pts, closed) {
    if (!pts || !pts.length) return "none";
    if (closed === false) return "path: " + pts.length + " points";
    var s = L.stats(pts); return "polygon: " + s.n + " points, " + (s.acres >= 0.1 ? s.acres + " acres" : s.area_ft2 + " ft2");
  };

  // ---- build from the host's selection report. sel: {artboard, source, paths:[{name, closed, points:[{a,l,r}], selected:[idx], lasso:bool, in_sel:bool}], types, sel_count}
  // opts: {closed: true (polygon wanted) | open: true (path wanted)}. Returns {ok, pts, note, warnings, stats, via} | {ok:false, error}
  function toFt(view, ab, doc) { return doc.map(function (q) { return L.docToFt(view, ab, q); }); }
  function pathFt(view, ab, p) { return VB.pathToFt(view, ab, p); }
  function anchorsOf(p, idx) { var out = []; for (var i = 0; i < idx.length; i++) if (p.points[idx[i]]) out.push(p.points[idx[i]].a); return out; }
  L.hint = function (sel) {
    var t = sel && sel.types, parts = [];
    if (t) for (var k in t) if (t.hasOwnProperty(k) && k !== "PathItem") parts.push(t[k] + " " + k);
    return parts.length ? " (the selection holds " + parts.join(", ") + ", which have no outline to read)" : "";
  };
  L.fromSelection = function (view, sel, opts) {
    opts = opts || {}; var ab = sel.artboard, paths = sel.paths || [], res;
    if (!paths.length) return { ok: false, error: "nothing to capture: select a closed path (or draw one with 'Draw lasso') and press Capture again" + L.hint(sel) };
    var inSel = paths.filter(function (p) { return p.in_sel !== false && !p.lasso; });
    var onLasso = paths.filter(function (p) { return p.lasso; });
    var finish = function (raw, note, via, extraWarn) {
      var c = L.clean(raw, opts); if (!c.ok) return { ok: false, error: c.error };
      var w = (extraWarn || []).concat(c.warnings);
      return { ok: true, pts: c.pts, note: note, via: via, warnings: w, stats: c.stats };
    };
    if (opts.open) {   // open path wanted (rivers, hedge rows): the first selected path, closed or not
      var pick = inSel[0] || onLasso[0] || paths[0], pts = L.dedupe(pathFt(view, ab, pick), 0.05);
      if (pick.closed && pts.length > 1) pts.push(pts[0]);
      if (pts.length < 2) return { ok: false, error: "the path has fewer than 2 points" };
      var warn = []; if (pts.length > 600) { var s = dpOpen(pts, L.tolFor(pts)); warn.push("simplified " + pts.length + " -> " + s.length + " points"); pts = s; }
      return { ok: true, pts: pts, via: "path", note: "path " + (pick.name || "unnamed"), warnings: warn, stats: { n: pts.length } };
    }
    // (1) partial anchor selection of one path: >= 3 anchors, fewer than the path has (a native Lasso / Direct Selection pick)
    var partial = inSel.filter(function (p) { return p.selected && p.selected.length >= 3 && p.selected.length < p.points.length; });
    if (partial.length === 1) {
      return finish(anchorsOf(partial[0], partial[0].selected).map(function (a) { return L.docToFt(view, ab, a); }),
        partial[0].selected.length + " selected anchors of " + (partial[0].name || "a path") + " in drawing order", "anchors",
        ["built from selected anchor points (drawing order): check the outline is the shape you meant"]);
    }
    // (2) selected closed paths: the largest
    var closedSel = inSel.filter(function (p) { return p.closed && p.points.length >= 3; });
    if (closedSel.length) {
      var best = null, bestA = -1, fts = closedSel.map(function (p) { return pathFt(view, ab, p); });
      fts.forEach(function (f, i) { var a = L.area(f); if (a > bestA) { bestA = a; best = i; } });
      return finish(fts[best], closedSel.length > 1 ? "largest of " + closedSel.length + " selected closed paths" : "selected closed path", "closed",
        closedSel.length > 1 ? ["several closed paths selected: used the largest (" + (closedSel[best].name || "unnamed") + ")"] : []);
    }
    // (3) selected open paths: one -> auto-closed, several -> chained in selection order
    var openSel = inSel.filter(function (p) { return !p.closed && p.points.length >= 2; });
    if (openSel.length) {
      var chain = []; openSel.forEach(function (p) { chain = chain.concat(pathFt(view, ab, p)); });
      return finish(chain, openSel.length > 1 ? openSel.length + " open paths joined and closed" : "open path, closed automatically", "open",
        [openSel.length > 1 ? "joined " + openSel.length + " open paths end to end and closed the shape" : "the selected path was open: closed it with a straight line from its last point to its first"]);
    }
    // (4) the newest path on the VB LASSO layer (host lists it first)
    var lp = onLasso.filter(function (p) { return p.points.length >= 3 || (p.points.length === 2 && false); })[0];
    if (lp) return finish(pathFt(view, ab, lp), "path on layer " + L.LAYER, "lasso layer", lp.closed ? [] : ["the lasso path was open: closed it automatically"]);
    // (5) anchors picked on several paths (or 3+ single anchors): unordered, so order by angle
    var anch = []; inSel.forEach(function (p) { if (p.selected && p.selected.length) anch = anch.concat(anchorsOf(p, p.selected)); });
    if (anch.length >= 3) {
      return finish(L.orderByAngle(anch.map(function (a) { return L.docToFt(view, ab, a); })), anch.length + " selected anchors from several paths ordered by angle", "anchors-angle",
        ["anchors from several paths have no drawing order: ordered by angle around their centre, so concave shapes may come out wrong. Draw a lasso with 'Draw lasso' for exact shapes"]);
    }
    // (6) the fallback layer the host read (only when nothing usable was selected)
    var any = paths.filter(function (p) { return p.points.length >= 3; })[0];
    if (any) return finish(pathFt(view, ab, any), "path on layer " + (sel.source || "?"), "layer", any.closed ? [] : ["the path was open: closed it automatically"]);
    return { ok: false, error: "no usable outline: the selection has " + paths.length + " path(s) with too few points. Select a closed path or draw one with 'Draw lasso'" + L.hint(sel) };
  };

  // ---- 'Select objects inside the lasso': decide for items reported by the host. items: [{id, layer, cx, cy (doc pts), anchors:[[x,y]...]}]
  // mode "center" (bounds centre inside) | "all" (every anchor inside). Returns indices; capped to maxN.
  L.insideIndices = function (polyDoc, items, mode, maxN) {
    var out = [], n = 0; maxN = maxN || 5000;
    for (var i = 0; i < items.length && n < maxN; i++) {
      var it = items[i], ok;
      if (mode === "all") { ok = !!(it.anchors && it.anchors.length); for (var k = 0; ok && k < it.anchors.length; k++) if (!L.pointInPolygon(it.anchors[k], polyDoc)) ok = false; }
      else ok = L.pointInPolygon([it.cx, it.cy], polyDoc);
      if (ok) { out.push(i); n++; }
    }
    return out;
  };
  // layer filter: comma separated names (or "*" / empty = every default layer); default excludes the lasso layer and guides
  L.layerAllowed = function (name, filter, locked, hidden) {
    if (name === L.LAYER || /^guides?$/i.test(name) || /^GUIDES$/.test(name)) return false;
    if (filter && filter !== "*") { var want = filter.split(",").map(function (s) { return s.replace(/^\s+|\s+$/g, "").toLowerCase(); }).filter(Boolean); return want.indexOf(String(name).toLowerCase()) >= 0; }
    return !locked && !hidden;
  };

  // ---- jobs (panel actions). All host calls are defensive on the host side and return clear errors.
  var GEN = "illustrator/generators/";
  var viewStep = function (st) { return VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }); };
  L.jobStart = function () {
    return { kind: "lasso_start", label: "Draw lasso", params: {}, steps: [VB.steps.host({ action: "lasso_start" }, "prepare VB LASSO layer"),
      { t: "fn", label: "tool hint", fn: function (run) { var r = run.last || {};
        run.log(r.tool && r.tool !== "none" ? "Layer " + L.LAYER + " is active and the " + r.tool.replace("Adobe ", "") + " is selected: draw around the area, then press Capture polygon."
          : "Layer " + L.LAYER + " is active. Choose the Pencil or Pen tool and draw around the area (close the shape), then press Capture polygon."); if (r.warn) run.log("note: " + r.warn); } }] };
  };
  L.jobClear = function () { return { kind: "lasso_clear", label: "Clear lasso", params: {}, steps: [VB.steps.host({ action: "lasso_clear" }, "remove VB LASSO layer")] }; };
  // draw the working polygon + feather rings (preview) and select the core. o: {core, feather}
  L.jobDraw = function (st, d, o) {
    return { kind: "lasso_draw", label: "Show lasso", params: { feather: o.feather || 0 }, steps: [viewStep(st),
      VB.steps.host({ action: "get_doc_info" }, "read artboard"),
      { t: "fn", label: "build rings", fn: function (run) {
        var ab = (run.last && run.last.artboard) || (run.last && run.last.ab); if (!ab) throw new Error("artboard unknown: is a document open?");
        run.vars.ab = ab; var view = run.vars.view, rings = [{ role: "core", pts: o.core.map(function (p) { return L.ftToDoc(view, ab, p); }) }];
        if (o.feather > 0 && L.ops()) { var f = L.ops().featherRings(o.core, o.feather);
          if (f.outer) rings.push({ role: "outer", pts: f.outer.map(function (p) { return L.ftToDoc(view, ab, p); }) });
          if (f.inner) rings.push({ role: "inner", pts: f.inner.map(function (p) { return L.ftToDoc(view, ab, p); }) });
          f.warnings.forEach(function (w) { run.log("note: " + w); }); }
        run.vars.rings = rings; } },
      { t: "host", label: "draw on VB LASSO", action: function (run) { return { action: "lasso_draw", rings: run.vars.rings, select: true }; } }] };
  };
  // read the current Illustrator selection / lasso as a polygon into o.out.pts (for Add / Subtract / Intersect)
  L.jobRead = function (st, d, o) {
    return { kind: "lasso_read", label: "Read lasso", params: {}, steps: [viewStep(st), VB.steps.host({ action: "get_selection", lasso: true }, "read selection"),
      { t: "fn", label: "build polygon", fn: function (run) { var r = L.fromSelection(run.vars.view, run.last, { closed: true }); if (!r.ok) throw new Error(r.error);
        o.out.pts = r.pts; o.out.note = r.note; o.out.warnings = r.warnings; run.log("second shape: " + L.describe(r.stats)); } }] };
  };
  // select the objects inside polygon o.poly (feet)
  L.jobInside = function (st, d, o) {
    return { kind: "lasso_select", label: "Select objects inside the lasso", params: { mode: o.mode, filter: o.filter }, steps: [viewStep(st), VB.steps.host({ action: "get_doc_info" }, "read artboard"),
      { t: "fn", label: "map polygon", fn: function (run) { var ab = run.last && run.last.artboard; if (!ab) throw new Error("artboard unknown: is a document open?");
        run.vars.polyDoc = o.poly.map(function (p) { return L.ftToDoc(run.vars.view, ab, p); }); } },
      { t: "host", label: "select inside", action: function (run) { return { action: "lasso_select", poly: run.vars.polyDoc, mode: o.mode || "center", filter: o.filter || null, max: 5000 }; } },
      { t: "fn", label: "report", fn: function (run) { var r = run.last || {};
        run.log("selected " + r.selected + " object(s) inside the lasso (" + r.scanned + " scanned" + (r.truncated ? ", limit reached: narrow the layers" : "") + ")" + (r.layers && r.layers.length ? ": " + r.layers.map(function (l) { return l.name + " " + l.count; }).join(", ") : "")); } }] };
  };

  L.ops = function () { return root.VBPolyOps || (typeof require !== "undefined" ? require("./polyops.js") : null); };   // lazy: polyops.js requires this file
  if (typeof module !== "undefined" && module.exports) module.exports = L; else root.VBLasso = L;
})(typeof window !== "undefined" ? window : this);
