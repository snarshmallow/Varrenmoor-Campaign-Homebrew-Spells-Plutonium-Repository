// Orientation of the panel canvases: Paint heightmap (lib/heightpaint.js), waypoint lasso map (lib/waypoint.js), page <-> feet (core.js docToFt).
// World feet: x east, y SOUTH, origin north-west; heightmap row = y / cell, column = x / cell; canvases: north up, east right (like the map).
// Also runs heightmap_paint.py export-preview on the synthetic asymmetric place of generators/orient_check.py (temp world root) and checks
// that the canvas grid, the feature overlay and a stroke painted where the cursor is all land in the north-east.
//   node illustrator/panel/test/test_orient.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/heightpaint.js"); const W = require("../lib/waypoint.js");
const ROOT = path.resolve(__dirname, "../../..");
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x === undefined ? "" : x); } };
const near = (a, b, e) => Math.abs(a - b) <= (e || 1e-6);

// ---- Paint canvas maths
const meta = { cell_ft: 10, factor: 2, pw: 81, ph: 51 };     // 1600 x 1000 ft place, preview every 2nd node
const view = VB.hpFit(meta, 400, 300);
const ne = VB.hpFeetToScreen(meta, view, 1500, 100), sw = VB.hpFeetToScreen(meta, view, 100, 900);
check("paint canvas: east is right, north is up", ne[0] > sw[0] && ne[1] < sw[1], JSON.stringify([ne, sw]));
const back = VB.hpScreenToFeet(meta, view, ne[0], ne[1]);
check("paint canvas: screen <-> feet round trip", near(back[0], 1500) && near(back[1], 100), back);
// pixel i is centred on node i: the screen centre of image pixel (px, py) is the node's feet position
const R = VB.hpImageRect(meta), s = 20;
check("image rect: pixels centred on nodes", near(R.x0, -10) && near(R.y0, -10) && near(R.x1, 80.5 * s) && near(R.y1, 50.5 * s), JSON.stringify(R));
const ix = 40, iy = 7, cx = view.ox + (ix - 0.5) * view.zoom + 0.5 * view.zoom, cy = view.oy + (iy - 0.5) * view.zoom + 0.5 * view.zoom;
const f = VB.hpScreenToFeet(meta, view, cx, cy);
check("cursor over the centre of pixel (40, 7) -> node (40, 7) in feet", near(f[0], ix * s) && near(f[1], iy * s), f);
const fitR = VB.hpFitRect(meta, { x0: 672, y0: 1066, x1: 1152, y1: 1366 }, 400, 300), mid = VB.hpScreenToFeet(meta, fitR, 200, 150);
check("fit rect centres the map window", near(mid[0], 912) && near(mid[1], 1216), mid);
check("map window: valid rect / other place / garbage", VB.hpMapWindow({ place: "a", x0: 1, y0: 2, x1: 3, y1: 4 }, "a").x1 === 3 && VB.hpMapWindow({ place: "b", x0: 1, y0: 2, x1: 3, y1: 4 }, "a") === null &&
  VB.hpMapWindow({ x0: 5, y0: 2, x1: 3, y1: 4 }) === null && VB.hpMapWindow(null) === null);
// renderer: a peak in the NE corner of the grid is drawn in the NE corner of the image (lightest, least saturated)
const pw = 30, ph = 20, h = new Float32Array(pw * ph);
for (let y = 0; y < ph; y++) for (let x = 0; x < pw; x++) h[y * pw + x] = 100 * Math.exp(-((x - 26) ** 2 + (y - 3) ** 2) / 20);
const img = VB.hpRender(h, pw, ph, { cell_ft: 10, lo: 0, hi: 100 });
let best = -1, bx = 0, by = 0;
for (let y = 0; y < ph; y++) for (let x = 0; x < pw; x++) { const o = (y * pw + x) * 4, r = Math.min(img[o], img[o + 1], img[o + 2]) / Math.max(img[o], img[o + 1], img[o + 2], 1); if (r > best) { best = r; bx = x; by = y; } }
check("renderer: grid row 0 = top (north), column pw-1 = right (east)", Math.abs(bx - 26) <= 1 && Math.abs(by - 3) <= 1, [bx, by]);

// ---- waypoint lasso canvas
const rect = { x0: 0, y0: 0, x1: 1600, y1: 1000 }, wv = W.fit(rect, 400, 300);
const a = W.toScreen(rect, wv, [1500, 100]), b = W.toScreen(rect, wv, [100, 900]);
check("waypoint canvas: east right, north up", a[0] > b[0] && a[1] < b[1]);
const ab = W.toFeet(rect, wv, a); check("waypoint canvas: round trip", near(ab[0], 1500) && near(ab[1], 100), ab);

// ---- Illustrator page (y up) <-> feet (y down)
const pv = { x0: 672, y0: 1066, k: 2.4, margin_in: 0.5 }, art = [0, 792];
const top = VB.docToFt(pv, art, [100, 700]), low = VB.docToFt(pv, art, [100, 300]);
check("page -> feet: higher on the artboard = further north (smaller y ft)", top[1] < low[1], [top, low]);
const rt = VB.docToFt(pv, art, VB.ftToDoc(pv, art, [900, 1200])); check("page <-> feet round trip", near(rt[0], 900) && near(rt[1], 1200), rt);
const right = VB.docToFt(pv, art, [500, 500]), left = VB.docToFt(pv, art, [100, 500]); check("page -> feet: right = east", right[0] > left[0]);

// ---- real python on the synthetic place (temp world root): grid, features, stroke under the cursor
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vborient-"));
const py = (code, args) => cp.spawnSync("python", ["-X", "utf8", "-c", code].concat(args || []), { cwd: path.join(ROOT, "illustrator", "generators"), encoding: "utf8" });
const mk = py("import sys, orient_check as O; O.make_synth(sys.argv[1])", [path.join(TMP, "world")]);
if (mk.status !== 0) { console.log("cannot build the synthetic place", mk.stderr); process.exit(1); }
const hp = path.join(ROOT, "illustrator", "generators", "heightmap_paint.py"), bin = path.join(TMP, "bin");
const common = ["--place", "orient_synth", "--world-root", path.join(TMP, "world"), "--work-dir", path.join(TMP, "work")];
let r = cp.spawnSync("python", ["-X", "utf8", hp, "export-preview"].concat(common, ["--layer", "work", "--max-px", "120", "--bin-dir", bin]), { encoding: "utf8" });
check("export-preview runs", r.status === 0, r.stderr);
const m = JSON.parse(fs.readFileSync(path.join(bin, "preview.json"), "utf8")), H = VB.hpReadBin(fs.readFileSync(path.join(bin, "preview_h.bin")));
let im = 0; for (let i = 1; i < H.length; i++) if (H[i] > H[im]) im = i;
const pk = VB.hpPxToFeet(m, im % m.pw, Math.floor(im / m.pw));
check("canvas grid: the NE peak (1400, 180 ft) is where the canvas maps it", Math.abs(pk[0] - 1400) <= 20 && Math.abs(pk[1] - 180) <= 20, pk);
const ft = JSON.parse(fs.readFileSync(path.join(bin, "preview_features.json"), "utf8"));
const bld = ft.buildings[0].polygon, bcx = bld.reduce((t, q) => t + q[0], 0) / bld.length, bcy = bld.reduce((t, q) => t + q[1], 0) / bld.length;
check("overlay features: NE building, south road, river in the east", bcx > 800 && bcy < 500 && ft.roads[0].points[0][1] > 900 && ft.water[0].points[0][0] > 1000, JSON.stringify([bcx, bcy]));
// a click over the screen position of feet (400, 700) (south-west quadrant) -> stroke -> python raises the SW nodes
const v2 = VB.hpFit(m, 500, 320), sp = VB.hpFeetToScreen(m, v2, 400, 700), fpt = VB.hpScreenToFeet(m, v2, sp[0], sp[1]);
const st = VB.normalize(null); st.place = "orient_synth"; st.hp.tool = "raise"; st.hp.radius_ft = 40; st.hp.rate_ft = 20; st.hp.strength = 1;
fs.writeFileSync(path.join(TMP, "strokes.json"), JSON.stringify({ strokes: [VB.hpStroke(st, [fpt])] }));
r = cp.spawnSync("python", ["-X", "utf8", hp, "apply-strokes"].concat(common, ["--strokes", path.join(TMP, "strokes.json")]), { encoding: "utf8" });
check("apply-strokes runs", r.status === 0, r.stderr);
r = cp.spawnSync("python", ["-X", "utf8", hp, "export-preview"].concat(common, ["--layer", "work", "--max-px", "120", "--bin-dir", bin]), { encoding: "utf8" });
const D = VB.hpReadBin(fs.readFileSync(path.join(bin, "preview_d.bin"))); let id = 0; for (let i = 1; i < D.length; i++) if (D[i] > D[id]) id = i;
const dp = VB.hpPxToFeet(m, id % m.pw, Math.floor(id / m.pw));
check("paint lands under the cursor (400, 700 ft)", Math.abs(dp[0] - 400) <= 20 && Math.abs(dp[1] - 700) <= 20, dp);
try { fs.rmSync(TMP, { recursive: true, force: true }); } catch (e) { /* scratch */ }
console.log("\n" + ok + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
