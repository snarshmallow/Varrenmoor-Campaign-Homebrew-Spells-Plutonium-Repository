// Polygon adjust maths for the lasso (Select > Modify style): offset (expand/contract), smooth, feather rings, invert, border, union/subtract/intersect.
// Pure: no DOM, no Illustrator. Polygons are arrays of [x, y] in feet, single ring, no holes. Loaded as window.VBPolyOps and by Node tests.
// EXACT: smooth, feather rings (they are offsets), invert / border for the cases listed below (keyhole bridge), boolean ops for simple polygons whose edges cross transversally.
// LIMITED: offset of strongly concave shapes (loops are removed and vertices nearer than ~0.9 d to the original are dropped: corners can be slightly clipped);
//          booleans with edges that overlap exactly (collinear) or touch only at a point; results with holes or several pieces (a hole is rejected, the largest piece is kept).
(function (root) {
  "use strict";
  var L = root.VBLasso || (typeof require !== "undefined" ? require("./lasso.js") : null);
  var P = {};
  var EPS = 1e-6;

  function dist(a, b) { var dx = a[0] - b[0], dy = a[1] - b[1]; return Math.sqrt(dx * dx + dy * dy); }
  function sArea(p) { var a = 0; for (var i = 0; i < p.length; i++) { var q = p[(i + 1) % p.length]; a += p[i][0] * q[1] - q[0] * p[i][1]; } return a / 2; }
  P.ccw = function (p) { return sArea(p) >= 0 ? p.slice() : p.slice().reverse(); };
  function distToRing(pt, ring) {
    var best = Infinity;
    for (var i = 0; i < ring.length; i++) {
      var a = ring[i], b = ring[(i + 1) % ring.length], dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
      var t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((pt[0] - a[0]) * dx + (pt[1] - a[1]) * dy) / l2));
      var d = dist(pt, [a[0] + t * dx, a[1] + t * dy]); if (d < best) best = d;
    }
    return best;
  }

  // ---- offset: d > 0 grows, d < 0 shrinks. Mitre joins, limited to miterLimit * |d| (default 3), then bevelled.
  P.offset = function (poly, d, miterLimit) {
    if (!poly || poly.length < 3) return { ok: false, error: "need a polygon" };
    if (!d) return { ok: true, pts: poly.slice(), warnings: [] };
    miterLimit = miterLimit || 3;
    var p = P.ccw(L.dedupe(poly, 0.01)), n = p.length, out = [];
    for (var i = 0; i < n; i++) {
      var a = p[(i + n - 1) % n], b = p[i], c = p[(i + 1) % n];
      var e1 = [b[0] - a[0], b[1] - a[1]], e2 = [c[0] - b[0], c[1] - b[1]], l1 = Math.sqrt(e1[0] * e1[0] + e1[1] * e1[1]), l2 = Math.sqrt(e2[0] * e2[0] + e2[1] * e2[1]);
      if (l1 < EPS || l2 < EPS) continue;
      // outward normals of a CCW ring are the right-hand normals (dy, -dx)
      var n1 = [e1[1] / l1, -e1[0] / l1], n2 = [e2[1] / l2, -e2[0] / l2];
      var bx = n1[0] + n2[0], by = n1[1] + n2[1], bl2 = bx * bx + by * by;
      if (bl2 < 1e-9) { out.push([b[0] + n1[0] * d, b[1] + n1[1] * d]); out.push([b[0] + n2[0] * d, b[1] + n2[1] * d]); continue; }   // 180 degree spike: bevel
      var dot = n1[0] * n2[0] + n1[1] * n2[1], s = d / (1 + dot), mx = bx * s, my = by * s;   // mitre vector = d * (n1+n2) / (1 + n1.n2)
      if (Math.sqrt(mx * mx + my * my) > miterLimit * Math.abs(d)) { out.push([b[0] + n1[0] * d, b[1] + n1[1] * d]); out.push([b[0] + n2[0] * d, b[1] + n2[1] * d]); }
      else out.push([b[0] + mx, b[1] + my]);
    }
    var warnings = [], q = L.dedupe(out, 0.01);
    if (q.length < 3) return { ok: false, error: "the polygon collapses at " + d + " ft: use a smaller amount" };
    if (L.selfIntersects(q)) { var f = L.fixSelfIntersections(q); if (!f.ok) return { ok: false, error: "the offset polygon cannot be repaired (shape too thin or too concave for " + d + " ft)" }; q = f.pts; warnings.push("offset created loops that were removed (concave or narrow parts may be clipped)"); }
    // drop vertices that ended up nearer to the original outline than they should (loop leftovers), and check orientation
    var tol = Math.abs(d) * 0.9, keep = q.filter(function (v) { return distToRing(v, p) >= tol; });
    if (keep.length < q.length) { if (keep.length < 3) return { ok: false, error: "the polygon collapses at " + d + " ft: use a smaller amount" }; q = keep; warnings.push("dropped " + (out.length - keep.length > 0 ? "some" : "") + " vertices that fell inside the offset distance"); }
    q = L.dedupe(P.ccw(q), 0.01);
    var a0 = Math.abs(sArea(p)), a1 = Math.abs(sArea(q));
    if (q.length < 3 || a1 < 1) return { ok: false, error: "the polygon collapses at " + d + " ft: use a smaller amount" };
    if ((d > 0 && a1 < a0) || (d < 0 && a1 > a0)) return { ok: false, error: "the polygon cannot be " + (d > 0 ? "expanded" : "contracted") + " by " + Math.abs(d) + " ft (shape too concave); try a smaller amount" };
    if (L.selfIntersects(q)) return { ok: false, error: "the offset polygon crosses itself: use a smaller amount" };
    return { ok: true, pts: q, warnings: warnings };
  };

  // ---- smooth: Chaikin corner cutting (iters 1..5). Cutting at 1/4 shrinks area a little; the result is scaled about the centroid to restore the area.
  P.smooth = function (poly, iters, keepArea) {
    iters = Math.max(1, Math.min(5, Math.round(iters || 1)));
    var p = P.ccw(L.dedupe(poly, 0.01)); if (p.length < 3) return { ok: false, error: "need a polygon" };
    var a0 = Math.abs(sArea(p)), q = p;
    for (var it = 0; it < iters; it++) {
      var o = [];
      for (var i = 0; i < q.length; i++) {
        var a = q[i], b = q[(i + 1) % q.length];
        o.push([a[0] * 0.75 + b[0] * 0.25, a[1] * 0.75 + b[1] * 0.25]); o.push([a[0] * 0.25 + b[0] * 0.75, a[1] * 0.25 + b[1] * 0.75]);
      }
      q = o;
    }
    if (keepArea !== false) {
      var a1 = Math.abs(sArea(q)); if (a1 > 0) {
        var c = L.centroid(q), s = Math.sqrt(a0 / a1); q = q.map(function (v) { return [c[0] + (v[0] - c[0]) * s, c[1] + (v[1] - c[1]) * s]; });
      }
    }
    q = L.simplify(q, Math.max(0.05, L.tolFor(q) * 0.25));
    return { ok: true, pts: L.dedupe(q, 0.01), warnings: [] };
  };

  // ---- feather: soft zone of total width f ft straddling the outline: outer ring at +f/2, inner ring at -f/2 (null when it collapses)
  P.featherRings = function (poly, f) {
    if (!(f > 0)) return { outer: null, inner: null, warnings: [] };
    var o = P.offset(poly, f / 2), i = P.offset(poly, -f / 2), w = [];
    if (!i.ok) w.push("feather is wider than the shape: no inner ring");
    if (!o.ok) w.push("feather outer ring failed: " + o.error);
    return { outer: o.ok ? o.pts : null, inner: i.ok ? i.pts : null, warnings: w.concat(o.ok ? o.warnings : [], i.ok ? i.warnings : []) };
  };

  // ---- boolean ops by edge classification (simple polygons, transversal crossings)
  function intersectParam(a, b, c, d) {   // t along a->b, u along c->d for a proper crossing
    var r = [b[0] - a[0], b[1] - a[1]], s = [d[0] - c[0], d[1] - c[1]], den = r[0] * s[1] - r[1] * s[0];
    if (Math.abs(den) < 1e-12) return null;
    var t = ((c[0] - a[0]) * s[1] - (c[1] - a[1]) * s[0]) / den, u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den;
    if (t > 1e-9 && t < 1 - 1e-9 && u > 1e-9 && u < 1 - 1e-9) return [t, u];
    return null;
  }
  function splitEdges(A, B) {   // edges of A cut at every crossing with B
    var out = [];
    for (var i = 0; i < A.length; i++) {
      var a = A[i], b = A[(i + 1) % A.length], ts = [0, 1];
      for (var j = 0; j < B.length; j++) { var x = intersectParam(a, b, B[j], B[(j + 1) % B.length]); if (x) ts.push(x[0]); }
      ts.sort(function (x, y) { return x - y; });
      for (var k = 0; k + 1 < ts.length; k++) {
        if (ts[k + 1] - ts[k] < 1e-9) continue;
        out.push([[a[0] + (b[0] - a[0]) * ts[k], a[1] + (b[1] - a[1]) * ts[k]], [a[0] + (b[0] - a[0]) * ts[k + 1], a[1] + (b[1] - a[1]) * ts[k + 1]]]);
      }
    }
    return out;
  }
  function key(p) { return Math.round(p[0] * 1000) + "," + Math.round(p[1] * 1000); }
  function assemble(segs) {   // directed segments -> rings
    var from = {}, used = [], rings = [];
    segs.forEach(function (s, i) { var k = key(s[0]); (from[k] = from[k] || []).push(i); used.push(false); });
    for (var i = 0; i < segs.length; i++) {
      if (used[i]) continue;
      var ring = [segs[i][0]], cur = i, guard = 0; used[i] = true;
      while (guard++ < segs.length + 2) {
        var endK = key(segs[cur][1]), nxt = -1, cand = from[endK] || [];
        for (var c = 0; c < cand.length; c++) if (!used[cand[c]]) { nxt = cand[c]; break; }
        if (nxt < 0) break;
        ring.push(segs[nxt][0]); used[nxt] = true; cur = nxt;
      }
      if (ring.length >= 3 && key(segs[cur][1]) === key(ring[0])) rings.push(ring);
    }
    return rings;
  }
  function inside(pt, poly) { return L.pointInPolygon(pt, poly); }
  function mid(s) { return [(s[0][0] + s[1][0]) / 2, (s[0][1] + s[1][1]) / 2]; }
  // op: "union" | "intersect" | "subtract" (A minus B)
  P.boolean = function (A, B, op) {
    if (!A || A.length < 3 || !B || B.length < 3) return { ok: false, error: "need two polygons" };
    A = P.ccw(L.dedupe(A, 0.01)); B = P.ccw(L.dedupe(B, 0.01));
    var sa = splitEdges(A, B), sb = splitEdges(B, A), segs = [], warnings = [];
    var near = function (s, poly) { return distToRing(mid(s), poly) < 1e-4; };
    if (sa.some(function (s) { return near(s, B); }) || sb.some(function (s) { return near(s, A); })) warnings.push("outlines overlap along an edge: result may be approximate");
    sa.forEach(function (s) {
      var inB = inside(mid(s), B);
      if ((op === "union" || op === "subtract") && !inB) segs.push(s);
      if (op === "intersect" && inB) segs.push(s);
    });
    sb.forEach(function (s) {
      var inA = inside(mid(s), A);
      if (op === "union" && !inA) segs.push(s);
      if (op === "intersect" && inA) segs.push(s);
      if (op === "subtract" && inA) segs.push([s[1], s[0]]);
    });
    if (!segs.length) {
      if (op === "intersect") return { ok: false, error: "the two shapes do not overlap: nothing left" };
      if (op === "subtract") return { ok: false, error: "the subtracted shape covers the whole selection: nothing left" };
    }
    var rings = assemble(segs);
    if (!rings.length) {
      // no crossings at all: disjoint or nested
      var aInB = inside(A[0], B), bInA = inside(B[0], A);
      if (op === "union") return aInB ? { ok: true, pts: B, warnings: warnings } : bInA ? { ok: true, pts: A, warnings: warnings } : { ok: false, error: "the two shapes do not touch: a single polygon cannot hold both" };
      if (op === "intersect") return aInB ? { ok: true, pts: A, warnings: warnings } : bInA ? { ok: true, pts: B, warnings: warnings } : { ok: false, error: "the two shapes do not overlap: nothing left" };
      if (aInB) return { ok: false, error: "the subtracted shape covers the whole selection: nothing left" };
      if (bInA) return { ok: false, error: "subtracting would leave a hole: a polygon cannot have holes. Use Border or draw the cut so it reaches the edge" };
      return { ok: true, pts: A, warnings: ["the shapes do not overlap: unchanged"] };
    }
    var outers = [], holes = 0;
    rings.forEach(function (r) { var a = sArea(r); if (a > 1) outers.push(r); else if (a < -1) holes++; });
    if (holes) return { ok: false, error: "the result would contain a hole: a polygon cannot have holes. Use Border for a ring, or cut so the shape stays solid" };
    if (!outers.length) return { ok: false, error: "nothing left after the operation" };
    outers.sort(function (a, b) { return sArea(b) - sArea(a); });
    if (outers.length > 1 && op === "union") return { ok: false, error: "the two shapes do not touch: a single polygon cannot hold both" };
    if (outers.length > 1) warnings.push("the result has " + outers.length + " separate pieces: kept the largest");
    return { ok: true, pts: L.dedupe(outers[0], 0.01), warnings: warnings };
  };

  // ---- keyhole: outer ring with a hole, joined by a zero-width bridge so it is still ONE polygon (hole winds the other way)
  function crossesAny(a, b, ring) {
    for (var i = 0; i < ring.length; i++) { var c = ring[i], d = ring[(i + 1) % ring.length]; if (intersectParam(a, b, c, d)) return true; }
    return false;
  }
  P.keyhole = function (outer, hole) {
    var o = P.ccw(outer), h = P.ccw(hole).reverse(), best = null, bd = Infinity;
    for (var i = 0; i < o.length; i++) for (var j = 0; j < h.length; j++) {
      var d = dist(o[i], h[j]); if (d < bd && !crossesAny(o[i], h[j], h) && !crossesAny(o[i], h[j], o)) { bd = d; best = [i, j]; }
    }
    if (!best) return { ok: false, error: "cannot join the outer ring and the hole (shape too concave)" };
    var ring = []; for (var a = 0; a <= o.length; a++) ring.push(o[(best[0] + a) % o.length]);
    for (var b = 0; b <= h.length; b++) ring.push(h[(best[1] + b) % h.length]);
    return { ok: true, pts: ring, warnings: ["the result is a ring: stored as one polygon with a zero-width bridge (a 'keyhole'); consumers that reject touching edges may need the bridge removed"] };
  };
  // invert inside bounds {x0,y0,x1,y1}
  P.invert = function (poly, b) {
    var rect = [[b.x0, b.y0], [b.x1, b.y0], [b.x1, b.y1], [b.x0, b.y1]], p = P.ccw(L.dedupe(poly, 0.01));
    var allIn = p.every(function (v) { return v[0] > b.x0 + EPS && v[0] < b.x1 - EPS && v[1] > b.y0 + EPS && v[1] < b.y1 - EPS; });
    if (allIn) return P.keyhole(rect, p);
    return P.boolean(rect, p, "subtract");
  };
  // border band of width w around the outline (outside the polygon)
  P.border = function (poly, w) {
    if (!(w > 0)) return { ok: false, error: "border width must be > 0" };
    var o = P.offset(poly, w); if (!o.ok) return o;
    var k = P.keyhole(o.pts, poly); if (k.ok) k.warnings = (o.warnings || []).concat(k.warnings); return k;
  };

  if (typeof module !== "undefined" && module.exports) module.exports = P; else root.VBPolyOps = P;
})(typeof window !== "undefined" ? window : this);
