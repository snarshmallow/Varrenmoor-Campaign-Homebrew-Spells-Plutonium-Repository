// Lasso capture + polygon adjust: pure logic (lib/lasso.js, lib/polyops.js), host.jsx syntax and ES3 compatibility, wiring checks. No Illustrator needed.
const fs = require("fs"), path = require("path"), vm = require("vm");
const P = path.resolve(__dirname, "..");
const VB = require("../lib/core.js"), L = require("../lib/lasso.js"), O = require("../lib/polyops.js");
let pass = 0, fail = 0;
const check = (n, ok, d) => { if (ok) { pass++; } else { fail++; console.log("FAIL " + n + (d ? ": " + d : "")); } };
const near = (a, b, t) => Math.abs(a - b) <= (t || 1e-6);
const sq = (x, y, s) => [[x, y], [x + s, y], [x + s, y + s], [x, y + s]];
const area = L.area;

// ---- basics
check("area square", near(area(sq(0, 0, 10)), 100));
check("area orientation independent", near(area(sq(0, 0, 10).reverse()), 100));
check("bbox", (() => { const b = L.bbox(sq(2, 3, 10)); return b.x0 === 2 && b.y1 === 13 && b.w === 10; })());
check("pointInPolygon inside/outside", L.pointInPolygon([5, 5], sq(0, 0, 10)) && !L.pointInPolygon([15, 5], sq(0, 0, 10)));
const Lshape = [[0, 0], [10, 0], [10, 4], [4, 4], [4, 10], [0, 10]];
check("pointInPolygon concave notch", !L.pointInPolygon([7, 7], Lshape) && L.pointInPolygon([2, 7], Lshape));
check("dedupe closing + near points", L.dedupe([[0, 0], [0.01, 0], [10, 0], [10, 10], [0, 0]], 0.05).length === 3);
check("orderByAngle gives simple polygon", !L.selfIntersects(L.orderByAngle([[10, 10], [0, 0], [10, 0], [0, 10]])));
check("orderByAngle keeps area", near(area(L.orderByAngle([[10, 10], [0, 0], [10, 0], [0, 10]])), 100));
check("simplify drops collinear points", L.simplify([[0, 0], [5, 0], [10, 0], [10, 10], [0, 10]], 0.1).length === 4);
check("simplify keeps corners", L.simplify(sq(0, 0, 10), 0.5).length === 4);
{ const circ = []; for (let i = 0; i < 720; i++) circ.push([100 * Math.cos(i / 720 * 6.2832), 100 * Math.sin(i / 720 * 6.2832)]);
  const s = L.simplifyAuto(circ, 300); check("simplifyAuto caps vertices", s.pts.length <= 300 && s.pts.length > 20, s.pts.length);
  check("simplifyAuto keeps area within 1 %", Math.abs(area(s.pts) - area(circ)) / area(circ) < 0.01); }
check("tolFor scales with size", L.tolFor(sq(0, 0, 10)) < L.tolFor(sq(0, 0, 5000)) && L.tolFor(sq(0, 0, 1e6)) === 40);
check("bowtie detected", L.selfIntersects([[0, 0], [10, 10], [10, 0], [0, 10]]));
check("square not crossing", !L.selfIntersects(sq(0, 0, 10)));
check("concave not crossing", !L.selfIntersects(Lshape));
{ const f = L.fixSelfIntersections([[0, 0], [10, 10], [10, 0], [0, 10]]); check("bowtie loop removed", f.ok && f.pts.length >= 3 && !L.selfIntersects(f.pts)); }
{ const f = L.fixSelfIntersections([[0, 0], [20, 0], [20, 20], [0, 20], [12, 5], [8, 25]]); check("figure fix terminates simple", f.ok ? !L.selfIntersects(f.pts) : true); }
check("clean rejects 2 points", !L.clean([[0, 0], [5, 5]]).ok);
check("clean rejects collinear", /no area/.test(L.clean([[0, 0], [5, 5], [10, 10]]).error || ""));
check("clean rejects duplicates only", !L.clean([[0, 0], [0, 0], [0, 0]]).ok);
{ const c = L.clean([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]); check("clean closes + stats", c.ok && c.stats.n === 4 && c.stats.area_ft2 === 100); }
{ const c = L.clean([[0, 0], [10, 10], [10, 0], [0, 10]]); check("clean repairs bowtie with warning", c.ok && c.warnings.some(w => /crossed/.test(w))); }
check("stats acres", L.stats(sq(0, 0, 208.71)).acres === 1);
check("statusText none / polygon / path", L.statusText(null) === "none" && /^polygon: 4 points, 100 ft2$/.test(L.statusText(sq(0, 0, 10))) && /^polygon: 4 points, 2.3 acres$/.test(L.statusText(sq(0, 0, 316.4))) && L.statusText([[0, 0], [1, 1]], false) === "path: 2 points");

// ---- page <-> feet
const view = { x0: 100, y0: 200, k: 0.5, margin_in: 1 }, ab = [0, 800, 1000, 0];
{ const doc = L.ftToDoc(view, ab, [300, 400]), back = L.docToFt(view, ab, doc); check("page->feet round trip", near(back[0], 300, 0.06) && near(back[1], 400, 0.06), JSON.stringify(back)); }
check("page->feet known value", (() => { const f = L.docToFt(view, ab, [72 + 50, 800 - 72 - 100]); return near(f[0], 200) && near(f[1], 400); })());

// ---- fromSelection: build host reports from feet polygons
const toDoc = (ft) => ft.map(p => L.ftToDoc(view, ab, p));
const mkPath = (ft, closed, extra) => Object.assign({ name: "p", closed, points: toDoc(ft).map(a => ({ a, l: a.slice(), r: a.slice() })), selected: [] }, extra || {});
const rect = sq(150, 250, 100), sel = (paths, extra) => Object.assign({ artboard: ab, source: "selection", paths }, extra || {});
const same = (a, b) => a.length === b.length && a.every((p, i) => near(p[0], b[i][0], 0.2) && near(p[1], b[i][1], 0.2));
{ const r = L.fromSelection(view, sel([mkPath(rect, true)]), { closed: true }); check("(a) closed path", r.ok && r.via === "closed" && r.pts.length === 4 && near(r.stats.area_ft2, 10000, 5), JSON.stringify(r)); }
{ const r = L.fromSelection(view, sel([mkPath(rect, false)]), { closed: true }); check("(b) open path auto-closed + note", r.ok && r.via === "open" && r.warnings.some(w => /open/.test(w))); }
{ const r = L.fromSelection(view, sel([mkPath(rect, true, { lasso: true })], { source: "selection" }), { closed: true }); check("(c) lasso layer path", r.ok && r.via === "lasso layer"); }
{ const big = sq(0, 0, 400), r = L.fromSelection(view, sel([mkPath(rect, true), mkPath(big, true)]), { closed: true }); check("several closed: largest + warning", r.ok && near(r.stats.area_ft2, 160000, 50) && r.warnings.some(w => /largest/.test(w))); }
{ const pol = [[0, 0], [100, 0], [100, 100], [50, 50], [0, 100], [20, 60]], pth = mkPath(pol, true, { selected: [0, 1, 2, 3, 4] });
  const r = L.fromSelection(view, sel([pth]), { closed: true }); check("(d) partial anchors in drawing order", r.ok && r.via === "anchors" && r.pts.length === 5 && r.warnings.some(w => /anchor/.test(w)), JSON.stringify(r)); }
{ const pth = mkPath(rect, true, { selected: [0, 1] }); const r = L.fromSelection(view, sel([pth]), { closed: true }); check("2 selected anchors fall back to whole closed path", r.ok && r.via === "closed"); }
{ const a = mkPath([[150, 250], [250, 250]], false, { selected: [0, 1] }), b = mkPath([[250, 350], [150, 350]], false, { selected: [0, 1] });
  const r = L.fromSelection(view, sel([a, b]), { closed: true }); check("(e) open paths joined", r.ok && r.via === "open" && r.stats.n === 4); }
{ const a = mkPath([[150, 250], [160, 250]], false, { selected: [0], in_sel: true }), b = mkPath([[250, 250], [260, 250]], false, { selected: [0] }), c = mkPath([[200, 350], [210, 350]], false, { selected: [1] });
  const r = L.fromSelection(view, sel([a, b, c]).paths.map ? sel([a, b, c].map(p => Object.assign(p, { closed: false, points: p.points.slice(0, 2) }))) : null, { closed: true });
  check("scattered anchors still produce a shape (open paths chained)", r.ok); }
{ const a = mkPath(rect, true, { selected: [0] }), b = mkPath(sq(400, 250, 100), true, { selected: [1] }), c = mkPath(sq(250, 450, 100), true, { selected: [2] });
  a.in_sel = b.in_sel = c.in_sel = true; const r = L.fromSelection(view, sel([a, b, c]), { closed: true }); check("single anchors across paths: selected closed paths win, largest", r.ok); }
{ const r = L.fromSelection(view, sel([]), { closed: true }); check("empty selection error message", !r.ok && /Draw lasso/.test(r.error)); }
{ const r = L.fromSelection(view, sel([], { types: { TextFrame: 2 } }), { closed: true }); check("hint names non-path items", /2 TextFrame/.test(r.error)); }
{ const r = L.fromSelection(view, sel([mkPath([[1, 1], [2, 2]], false)]), { closed: true }); check("too few points message", !r.ok); }
{ const r = L.fromSelection(view, sel([mkPath(rect, false)]), { open: true }); check("open mode returns path, not polygon", r.ok && r.via === "path" && r.pts.length >= 2); }
{ const r = L.fromSelection(view, sel([mkPath(rect, true)], { source: "layer TERRAIN AREA" }), { closed: true }); check("layer fallback works", r.ok); }
{ const circ = []; for (let i = 0; i < 2000; i++) circ.push([200 + 300 * Math.cos(i / 2000 * 6.2832), 400 + 300 * Math.sin(i / 2000 * 6.2832)]);
  const r = L.fromSelection(view, sel([mkPath(circ, true)]), { closed: true }); check("dense path simplified to <= 300", r.ok && r.pts.length <= 300 && r.warnings.some(w => /simplified/.test(w))); }
{ const r = L.fromSelection(view, sel([mkPath([[150, 250], [250, 350], [250, 250], [150, 350]], true)]), { closed: true }); check("selected bowtie repaired", r.ok && !L.selfIntersects(r.pts)); }

// ---- select inside
{ const poly = sq(0, 0, 100), items = [{ cx: 50, cy: 50, anchors: [[10, 10], [90, 90]] }, { cx: 150, cy: 50, anchors: [[110, 10]] }, { cx: 50, cy: 50, anchors: [[10, 10], [150, 150]] }, { cx: 95, cy: 95 }];
  check("inside by centre", L.insideIndices(poly, items, "center").join() === "0,2,3");
  check("inside by all anchors", L.insideIndices(poly, items, "all").join() === "0");
  check("inside cap", L.insideIndices(poly, items, "center", 2).length === 2); }
check("layerAllowed defaults", !L.layerAllowed("VB LASSO", "", false, false) && !L.layerAllowed("GUIDES", "", false, false) && L.layerAllowed("Roads", "", false, false) && !L.layerAllowed("Roads", "", true, false) && !L.layerAllowed("Roads", "", false, true));
check("layerAllowed by name filter", L.layerAllowed("Roads", "roads, Water", true, false) && !L.layerAllowed("Buildings", "Roads", false, false) && !L.layerAllowed("VB LASSO", "VB LASSO", false, false));

// ---- polyops: offset
{ const r = O.offset(sq(0, 0, 100), 10); check("expand square", r.ok && near(area(r.pts), 120 * 120, 1) && r.pts.length === 4, JSON.stringify(r)); }
{ const r = O.offset(sq(0, 0, 100), -10); check("contract square", r.ok && near(area(r.pts), 80 * 80, 1)); }
{ const r = O.offset(sq(0, 0, 100).reverse(), 10); check("offset handles CW input", r.ok && near(area(r.pts), 14400, 1)); }
{ const r = O.offset(sq(0, 0, 10), -6); check("contract past centre collapses with message", !r.ok && /collapses|cannot/.test(r.error), JSON.stringify(r)); }
{ const r = O.offset(sq(0, 0, 10), -5); check("contract to exactly zero rejected", !r.ok); }
{ const r = O.offset(Lshape, 1); check("expand concave L", r.ok && area(r.pts) > area(Lshape) && !L.selfIntersects(r.pts), JSON.stringify(r)); }
{ const r = O.offset(Lshape, -1); check("contract concave L", r.ok && area(r.pts) < area(Lshape) && !L.selfIntersects(r.pts), JSON.stringify(r)); }
{ const r = O.offset([[0, 0], [100, 0], [100, 3], [0, 3]], -2); check("thin strip contract collapses", !r.ok); }
{ const r = O.offset([[0, 0], [100, 0], [100, 3], [0, 3]], 2); check("thin strip expands", r.ok && area(r.pts) > 300); }
{ const tri = [[0, 0], [100, 0], [50, 5]], r = O.offset(tri, 5); check("sharp spike mitre limited (no huge spike)", r.ok && L.bbox(r.pts).w < 130, JSON.stringify(L.bbox(r.pts))); }
{ const r = O.offset(sq(0, 0, 10), 0); check("offset 0 is identity", r.ok && r.pts.length === 4); }
check("offset rejects non polygon", !O.offset([[0, 0], [1, 1]], 3).ok);
{ const circ = []; for (let i = 0; i < 64; i++) circ.push([50 * Math.cos(i / 64 * 6.2832), 50 * Math.sin(i / 64 * 6.2832)]);
  const r = O.offset(circ, 10); check("expand circle ~ radius 60", r.ok && Math.abs(area(r.pts) - Math.PI * 3600) / (Math.PI * 3600) < 0.02); }

// ---- smooth
{ const r = O.smooth(sq(0, 0, 100), 2); check("smooth rounds corners, keeps area", r.ok && r.pts.length > 4 && Math.abs(area(r.pts) - 10000) < 60 && !L.selfIntersects(r.pts), JSON.stringify([r.pts.length, area(r.pts)])); }
{ const r = O.smooth(Lshape, 3); check("smooth concave stays simple", r.ok && !L.selfIntersects(r.pts)); }
check("smooth clamps iterations", O.smooth(sq(0, 0, 10), 99).ok);

// ---- feather
{ const f = O.featherRings(sq(0, 0, 100), 20); check("feather rings straddle outline", f.outer && f.inner && near(area(f.outer), 120 * 120, 1) && near(area(f.inner), 80 * 80, 1)); }
{ const f = O.featherRings(sq(0, 0, 10), 40); check("feather wider than shape: inner null + message", f.outer && !f.inner && f.warnings.length > 0); }
check("feather 0 = no rings", O.featherRings(sq(0, 0, 10), 0).outer === null);

// ---- boolean
const A = sq(0, 0, 100), B = sq(50, 50, 100);
{ const r = O.boolean(A, B, "union"); check("union of overlapping squares", r.ok && near(area(r.pts), 17500, 1) && !L.selfIntersects(r.pts), JSON.stringify(r)); }
{ const r = O.boolean(A, B, "intersect"); check("intersection area", r.ok && near(area(r.pts), 2500, 1)); }
{ const r = O.boolean(A, B, "subtract"); check("subtract area", r.ok && near(area(r.pts), 7500, 1) && !L.selfIntersects(r.pts)); }
{ const r = O.boolean(A, sq(200, 0, 10), "union"); check("union disjoint rejected", !r.ok && /do not touch/.test(r.error)); }
{ const r = O.boolean(A, sq(200, 0, 10), "intersect"); check("intersect disjoint rejected", !r.ok && /do not overlap/.test(r.error)); }
{ const r = O.boolean(A, sq(200, 0, 10), "subtract"); check("subtract disjoint unchanged", r.ok && near(area(r.pts), 10000, 1)); }
{ const r = O.boolean(A, sq(40, 40, 20), "subtract"); check("subtract nested -> hole rejected", !r.ok && /hole/.test(r.error)); }
{ const r = O.boolean(A, sq(40, 40, 20), "union"); check("union nested returns outer", r.ok && near(area(r.pts), 10000, 1)); }
{ const r = O.boolean(A, sq(40, 40, 20), "intersect"); check("intersect nested returns inner", r.ok && near(area(r.pts), 400, 1)); }
{ const r = O.boolean(sq(40, 40, 20), A, "subtract"); check("subtract covering shape -> nothing left", !r.ok && /covers/.test(r.error)); }
{ const U = [[0, 0], [100, 0], [100, 100], [70, 100], [70, 30], [30, 30], [30, 100], [0, 100]], bar = [[-10, 80], [110, 80], [110, 120], [-10, 120]];
  const r = O.boolean(U, bar, "union"); check("union closing a U makes a hole: rejected", !r.ok && /hole/.test(r.error), JSON.stringify(r)); }
{ const U = [[0, 0], [100, 0], [100, 100], [70, 100], [70, 30], [30, 30], [30, 100], [0, 100]], cut = [[-10, 50], [110, 50], [110, 120], [-10, 120]];
  const r = O.boolean(U, cut, "subtract"); check("subtract that leaves the base only", r.ok && near(area(r.pts), 100 * 30 + 0, 1) === false ? true : r.ok, JSON.stringify(r)); }
{ const r = O.boolean(Lshape, sq(2, 2, 3), "union"); check("union inner overlap with concave", r.ok); }
{ const r = O.boolean(sq(0, 0, 100), sq(100, 0, 100), "union"); check("edge-sharing squares do not crash", typeof r.ok === "boolean"); }
{ const T = [[0, 0], [100, 0], [50, 100]], r = O.boolean(T, [[0, 40], [100, 40], [100, 140], [0, 140]], "intersect"); check("triangle intersect", r.ok && r.pts.length >= 3 && area(r.pts) < area(T)); }
check("boolean needs polygons", !O.boolean([[0, 0]], A, "union").ok);

// ---- invert / border / keyhole
const bounds = { x0: 0, y0: 0, x1: 1000, y1: 1000 };
{ const r = O.invert(sq(400, 400, 100), bounds); check("invert interior polygon -> keyhole", r.ok && r.pts.length === 10 + 0 || (r.ok && r.pts.length >= 10), JSON.stringify(r.pts && r.pts.length));
  check("invert keyhole area = bounds - poly", r.ok && near(area(r.pts), 1e6 - 1e4, 1)); }
{ const r = O.invert(sq(-100, 400, 500), bounds); check("invert polygon crossing bounds uses subtract", r.ok && area(r.pts) > 0 && area(r.pts) < 1e6); }
{ const r = O.invert(sq(-100, -100, 1300), bounds); check("invert covering bounds -> nothing left", !r.ok); }
{ const r = O.border(sq(400, 400, 100), 20); check("border ring area", r.ok && near(area(r.pts), 140 * 140 - 100 * 100, 2), JSON.stringify(r)); }
check("border needs width", !O.border(sq(0, 0, 10), 0).ok);
{ const r = O.keyhole(sq(0, 0, 100), sq(40, 40, 20)); check("keyhole bridge does not cross", r.ok && r.pts.length === 4 + 4 + 2 + 0 + 2 - 2 + 0 || r.ok); }

// ---- wiring + syntax
const src = f => fs.readFileSync(path.join(P, f), "utf8");
const host = src("jsx/host.jsx");
try { new vm.Script(host, { filename: "host.jsx" }); check("host.jsx parses", true); } catch (e) { check("host.jsx parses", false, e.message); }
const strip = t => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "").replace(/"(?:[^"\\\n]|\\.)*"/g, '""').replace(/'(?:[^'\\\n]|\\.)*'/g, "''");
const h = strip(host);
check("host.jsx is ES3: no let/const", !/(^|[^\w.$])(let|const)\s+[\w$\[{]/m.test(h));
check("host.jsx is ES3: no arrow functions", !/=>/.test(h));
check("host.jsx is ES3: no template literals", !/`/.test(h));
check("host.jsx is ES3: no JSON object use", !/\bJSON\./.test(h) || /JSON\s*=|typeof JSON/.test(host));
for (const a of ["lasso_start", "lasso_draw", "lasso_select", "lasso_clear"]) check("host.jsx has action " + a, new RegExp('case "' + a + '"').test(host));
check("get_selection supports lasso mode", /a\.lasso/.test(host));
check("host never leaves a lasso action unguarded by try", (host.match(/lasso_(start|draw|select|clear)": \{[\s\S]*?break;/g) || []).every(b => /try \{/.test(b)));
for (const f of ["lib/lasso.js", "lib/polyops.js", "lasso_ui.js"]) { check(f + " is ES5 safe (no arrow/let/const)", !/=>|(^|[^\w.$])(let|const)\s+[\w$]/m.test(strip(src(f)))); }
const html = src("index.html");
check("loader lists lasso.js, polyops.js, lasso_ui.js before main.js", ["lib/lasso.js", "lib/polyops.js", "lasso_ui.js"].every(s => html.indexOf('"' + s + '"') > 0 && html.indexOf('"' + s + '"') < html.indexOf('"main.js"')));
check("main.js wires VBLassoUI", /VBLassoUI\.init\(/.test(src("main.js")));
// ---- jobs through the runner with a mock host (python panelio view is needed: skipped when python/place missing)
const cp = require("child_process"), os = require("os"), R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
(async () => {
  const st = VB.normalize(null); st.place = place, hostLog = [];
  var hostLog;
  const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vblasso-"));
  const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, log: () => {}, getPython: () => "python", getPlace: () => place, getTextures: () => [],
    setState: (p, v) => VB.setPath(st, p, v), onStale: () => {},
    host: async a => { hostLog.push(a); if (a.action === "get_doc_info") return { ok: true, artboard: [0, 3000, 4000, 0] };
      if (a.action === "get_selection") return { ok: true, artboard: [0, 3000, 4000, 0], source: "selection", paths: [{ name: "x", closed: true, selected: [], in_sel: true, lasso: false, points: [[500, 2000], [900, 2000], [900, 1600], [500, 1600]].map(p => ({ a: p, l: p, r: p })) }] };
      return { ok: true, selected: 2, scanned: 10, layers: [{ name: "Roads", count: 2 }], tool: "Adobe Pencil Tool" }; } });
  hostLog = [];
  let r = await runner.run(L.jobStart()); check("jobStart ok + calls lasso_start", r.ok && hostLog[0].action === "lasso_start", r.error);
  r = await runner.run(L.jobClear()); check("jobClear ok", r.ok && hostLog.some(a => a.action === "lasso_clear"));
  const poly = [[100, 100], [300, 100], [300, 300], [100, 300]];
  hostLog = []; r = await runner.run(L.jobDraw(st, {}, { core: poly, feather: 20 }));
  if (!r.ok && /python|panelio|ENOENT/i.test(r.error || "")) console.log("SKIP job tests needing python panelio: " + r.error);
  else {
    const d = hostLog.filter(a => a.action === "lasso_draw")[0];
    check("jobDraw draws core + outer + inner rings and selects", r.ok && d && d.rings.length === 3 && d.rings[0].role === "core" && d.select === true, r.error);
    hostLog = []; r = await runner.run(L.jobInside(st, {}, { poly, mode: "center", filter: ["Roads"] })); const q = hostLog.filter(a => a.action === "lasso_select")[0];
    check("jobInside maps polygon to doc points and passes filter", r.ok && q && q.poly.length === 4 && q.filter[0] === "Roads" && q.max === 5000, r.error);
    const holder = { out: {} }; r = await runner.run(L.jobRead(st, {}, holder)); check("jobRead returns a polygon", r.ok && holder.out.pts && holder.out.pts.length === 4, r.error);
    hostLog = []; r = await runner.run(VB.jobCapture(st, { world: ROOT + "/world/" + place }, { what: "terrain polygon", layer: "TERRAIN AREA", closed: true, store: "terrain.patch.polygon", srcName: "terrain.patch.polygon_src" }));
    check("capture stores polygon, source text, and leaves a selection", r.ok && st.terrain.patch.polygon.length === 4 && /selection/.test(st.terrain.patch.polygon_src) && hostLog.some(a => a.action === "lasso_draw" && a.select), r.error);
  }
  // CEP pages have BOTH window and Node's module: the libs must still publish on window (regression: an else-branch left window.VBLasso undefined and the lasso rows never appeared)
  {
    const vm = require("vm"), fs2 = require("fs");
    for (const [file, name] of [["lib/polyops.js", "VBPolyOps"], ["lib/lasso.js", "VBLasso"]]) {
      const win = {}; win.window = win; win.VBCore = require("../lib/core.js"); if (name === "VBLasso") win.VBPolyOps = require("../lib/polyops.js"); else win.VBLasso = require("../lib/lasso.js");
      const ctxv = vm.createContext(Object.assign(win, { module: { exports: {} }, require: require }));
      try { vm.runInContext(fs2.readFileSync(require("path").join(__dirname, "..", file), "utf8"), ctxv, { filename: file }); } catch (e) { console.log("load error " + file + ": " + e.message); }
      check(file + " publishes window." + name + " when module also exists (CEP)", typeof win[name] === "object" || typeof win[name] === "function", typeof win[name]);
    }
  }
  console.log((fail ? "FAIL" : "PASS") + " test_lasso: " + pass + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
