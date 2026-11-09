// Node tests for lib/waypoint.js: waypoint editing (add / move / insert / remove / close), area, parse, view mapping round trip, anchor reading.
const W = require("../lib/waypoint.js"), L = require("../lib/lasso.js"), vm = require("vm"), fs = require("fs"), path = require("path");
let pass = 0, fail = 0;
const check = (n, ok, x) => { if (ok) pass++; else { fail++; console.log("FAIL " + n + (x ? " " + x : "")); } };
const sq = () => { const w = W.create(); [[0, 0], [100, 0], [100, 100], [0, 100]].forEach(p => W.add(w, p, 5)); return w; };
let w = sq();
check("add 4 points", w.pts.length === 4 && !w.closed);
check("click near first point closes (no new point)", W.add(w, [2, 3], 5).action === "close" && w.closed && w.pts.length === 4);
check("closed polygon ignores further clicks", W.add(w, [50, 50], 5).action === "ignored" && w.pts.length === 4);
check("area 10000 ft2", Math.abs(W.area(w) - 10000) < 1e-9 && Math.abs(W.acres(w) - 10000 / 43560) < 1e-12);
check("perimeter closed 400", Math.abs(W.length(w) - 400) < 1e-9);
check("close needs 3 points", !W.close(W.create([[0, 0], [1, 1]])));
check("first-point click with <3 points just adds", (() => { const a = W.create([[0, 0], [50, 0]]); return W.add(a, [1, 1], 5).action === "add" && a.pts.length === 3; })());
check("hit finds nearest within tol", W.hit(w, [98, 3], 5) === 1 && W.hit(w, [50, 50], 5) === -1);
W.move(w, 2, [150, 120]); check("move waypoint", w.pts[2][0] === 150 && w.pts[2][1] === 120 && !W.move(w, 9, [0, 0]));
w = sq(); w.closed = true;
check("insertOnEdge picks the nearest edge", W.insertOnEdge(w, [50, 2], 6) === 1 && w.pts[1][0] === 50 && w.pts.length === 5);
check("insertOnEdge on the closing edge", W.insertOnEdge(w, [2, 50], 6) === 5 && w.pts.length === 6 && w.pts[5][1] === 50);
check("insertOnEdge too far returns -1", W.insertOnEdge(w, [50, 50], 6) === -1);
w = sq(); w.closed = true;
check("removeLast re-opens a closed polygon first", W.removeLast(w) && !w.closed && w.pts.length === 4);
W.removeLast(w); check("removeLast then pops the last point", w.pts.length === 3);
check("remove below 3 points re-opens", (() => { const a = sq(); a.closed = true; W.remove(a, 0); W.remove(a, 0); return a.pts.length === 2 && !a.closed; })());
check("reorder swaps", (() => { const a = sq(); W.reorder(a, 0, 1); return a.pts[0][0] === 100 && a.pts[1][0] === 0 && !W.reorder(a, 0, -1); })());
const p = W.parseList("10, 20\n(30;40)\n 50 60 \nbad line\n");
check("parseList reads comma / paren / space forms and reports bad lines", p.pts.length === 3 && p.pts[1][0] === 30 && p.pts[1][1] === 40 && p.errors.length === 1 && /line 4/.test(p.errors[0]), JSON.stringify(p));
check("formatList round trips", W.parseList(W.formatList(W.create(p.pts))).pts.length === 3);
// view mapping round trip + zoom keeps the point under the cursor
const rect = { x0: 0, y0: 0, x1: 2400, y1: 1500 }, v = W.fit(rect, 400, 260);
check("fit keeps the map inside the canvas", W.toScreen(rect, v, [0, 0])[0] >= 8 - 1e-9 && W.toScreen(rect, v, [2400, 1500])[1] <= 260 - 8 + 1e-9);
let maxErr = 0; for (const f of [[0, 0], [1200, 750], [2400, 1500], [333.3, 912.7]]) { const b = W.toFeet(rect, v, W.toScreen(rect, v, f)); maxErr = Math.max(maxErr, Math.abs(b[0] - f[0]), Math.abs(b[1] - f[1])); }
check("feet -> screen -> feet round trip", maxErr < 1e-9, maxErr);
const f0 = W.toFeet(rect, v, [150, 90]), v2 = W.zoomAt(v, 150, 90, 3), f1 = W.toFeet(rect, v2, [150, 90]);
check("zoomAt keeps the feet under the cursor", Math.hypot(f0[0] - f1[0], f0[1] - f1[1]) < 1e-9 && Math.abs(v2.zoom / v.zoom - 3) < 1e-9);
// waypoint feet survive the Illustrator page mapping used by every capture
const view = { x0: 0, y0: 0, k: 0.25, margin_in: 0.5 }, ab = [0, 3000, 4000, 0];
const wp = [1234.5, 678.9], back = L.docToFt(view, ab, L.ftToDoc(view, ab, wp));
check("waypoint feet survive the Illustrator page mapping", Math.abs(back[0] - wp[0]) < 0.06 && Math.abs(back[1] - wp[1]) < 0.06, JSON.stringify(back));
check("L.clean accepts a waypoint square", L.clean(sq().pts, { closed: true }).ok);
check("L.clean repairs a crossing waypoint polygon with a warning", (() => { const c = L.clean([[0, 0], [100, 100], [100, 0], [0, 100]], { closed: true }); return c.ok && c.warnings.length > 0; })());
const sel = { paths: [{ in_sel: true, lasso: false, selected: [1], points: [{ a: [0, 0] }, { a: [500, 2000] }] }] }, id = q => [q[0] / 4, q[1] / 4];
check("anchorFromSelection reads exactly one selected anchor", (() => { const r = W.anchorFromSelection(sel, id); return r.ok && r.pt[0] === 125 && r.pt[1] === 500; })());
check("anchorFromSelection refuses 0 or 2 anchors", !W.anchorFromSelection({ paths: [] }, id).ok && !W.anchorFromSelection({ paths: [{ selected: [0, 1], points: [{ a: [0, 0] }, { a: [1, 1] }] }] }, id).ok);
{ const win = {}; win.window = win; const c = vm.createContext(Object.assign(win, { module: { exports: {} } })); vm.runInContext(fs.readFileSync(path.join(__dirname, "../lib/waypoint.js"), "utf8"), c);
  check("waypoint.js publishes window.VBWaypoint when module also exists (CEP)", typeof win.VBWaypoint === "object" && typeof win.VBWaypoint.add === "function"); }
console.log((fail ? "FAIL" : "PASS") + " test_waypoint: " + pass + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
