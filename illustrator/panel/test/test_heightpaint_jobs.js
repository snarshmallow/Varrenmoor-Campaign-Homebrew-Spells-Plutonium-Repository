// Paint tab: stroke building, job argument lists, the renderer, view maths, and the real python round trip (apply, undo, redo, save, discard, reset)
// against a throw-away world folder.   node illustrator/panel/test/test_heightpaint_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/heightpaint.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "pl";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbhp-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world/pl", panel: tmp + "/panel" });
fs.mkdirSync(d.panel, { recursive: true });
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const st = VB.normalize(null); st.place = place;

// ---- pure parts
check("state carries paint defaults", st.hp && st.hp.tool === "raise" && st.hp.radius_ft === 30 && st.hp.auto_apply === true && Array.isArray(st.hp.redo));
check("older state gets the block", !!VB.normalize({ lighting: {} }).hp);
let s = VB.hpStroke(st, [[10.123, 20.456], [30, 40]]);
check("raise stroke: rounded points, rate, no height", s.tool === "raise" && s.points[0][0] === 10.12 && s.rate_ft === 2 && s.height_ft === undefined && s.falloff === "smooth", JSON.stringify(s));
st.hp.tool = "set"; st.hp.height_ft = "";
let err = ""; try { VB.hpStroke(st, [[1, 1]]); } catch (e) { err = e.message; }
check("set height without a height is refused", /needs a height/.test(err), err);
st.hp.height_ft = 0; check("height 0 is a real height", VB.hpStroke(st, [[1, 1]]).height_ft === 0);
st.hp.height_ft = null; st.hp.tool = "flatten"; check("flatten with a blank height leaves it to python", VB.hpStroke(st, [[1, 1]]).height_ft === undefined);
st.hp.tool = "river"; st.hp.depth_ft = 8; check("river carries depth and bank slope", (s = VB.hpStroke(st, [[1, 1], [9, 9]])).depth_ft === 8 && s.bank_slope === 0.6);
st.hp.tool = "valley"; st.hp.height_ft = -12; check("valley depth is positive", VB.hpStroke(st, [[1, 1]]).height_ft === 12);
st.hp.tool = "noise"; st.hp.noise_scale_ft = 25; check("noise carries seed and scale", (s = VB.hpStroke(st, [[1, 1]])).seed === 7 && s.noise_scale_ft === 25);
st.hp.tool = "raise"; st.hp.strength = 7; st.hp.hardness = -2; st.hp.radius_ft = "abc"; s = VB.hpStroke(st, [[0, 0]]);
check("strength / hardness clamped, bad radius falls back", s.strength === 1 && s.hardness === 0 && s.radius_ft === 30, JSON.stringify(s));
st.hp.strength = 0.5; st.hp.hardness = 0.2; st.hp.radius_ft = 30;
err = ""; try { VB.hpStroke(st, []); } catch (e) { err = e.message; }
check("empty stroke refused", /at least one point/.test(err));
check("preview args", VB.hpPreviewArgs(st, d).join(" ") === "export-preview --place pl --layer work --max-px 640 --bin-dir " + d.panel + "/heightmap_paint/preview", VB.hpPreviewArgs(st, d).join(" "));

// view maths
const meta = { cell_ft: 2, factor: 3, pw: 100, ph: 80 };
const fit = VB.hpFit(meta, 400, 300);
check("fit centres the preview", fit.zoom > 0 && Math.abs(fit.ox - (400 - 100 * fit.zoom) / 2) < 1e-9);
const f1 = VB.hpScreenToFeet(meta, fit, fit.ox + 10 * fit.zoom, fit.oy + 5 * fit.zoom);
check("screen -> feet uses cell x factor", Math.abs(f1[0] - 60) < 1e-6 && Math.abs(f1[1] - 30) < 1e-6, f1);
const z = VB.hpZoomAt(fit, 150, 120, 2), a = VB.hpScreenToFeet(meta, fit, 150, 120), b = VB.hpScreenToFeet(meta, z, 150, 120);
check("zoom keeps the point under the cursor", Math.abs(a[0] - b[0]) < 1e-6 && Math.abs(a[1] - b[1]) < 1e-6 && Math.abs(z.zoom - fit.zoom * 2) < 1e-9);
check("zoom is clamped", VB.hpZoomAt({ zoom: 79, ox: 0, oy: 0 }, 0, 0, 5).zoom === 80);
check("feet -> px round trip", (q => Math.abs(VB.hpPxToFeet(meta, q[0], q[1])[0] - 123) < 1e-9)(VB.hpFeetToPx(meta, 123, 45)));
check("bilinear", Math.abs(VB.hpBilinear([0, 10, 20, 30], 2, 2, 0.5, 0.5) - 15) < 1e-9 && VB.hpBilinear([0, 10, 20, 30], 2, 2, 9, 9) === 30);

// renderer: a ramp rising to the east: tint follows height, contours darken edge pixels, delta tints red / blue
const pw = 20, ph = 10, h = new Float32Array(pw * ph); for (let y = 0; y < ph; y++) for (let x = 0; x < pw; x++) h[y * pw + x] = x * 2;
const img = VB.hpRender(h, pw, ph, { cell_ft: 5, lo: 0, hi: 38 }), px = (i, x, y) => [i[(y * pw + x) * 4], i[(y * pw + x) * 4 + 1], i[(y * pw + x) * 4 + 2], i[(y * pw + x) * 4 + 3]];
check("render: opaque RGBA, high ground lighter than low", img.length === pw * ph * 4 && px(img, 18, 5)[3] === 255 && px(img, 18, 5)[0] > px(img, 1, 5)[0]);
const ic = VB.hpRender(h, pw, ph, { cell_ft: 5, lo: 0, hi: 38, contour_ft: 4 });
let dark = 0; for (let x = 1; x < pw - 1; x++) { if (px(ic, x, 5)[1] < px(img, x, 5)[1] * 0.8) dark++; }
check("render: contours darken pixels beside a level change", dark >= 8, dark);
const dl = new Float32Array(pw * ph); dl[5 * pw + 5] = 4; dl[5 * pw + 6] = -4;
const idl = VB.hpRender(h, pw, ph, { cell_ft: 5, lo: 0, hi: 38, delta: dl });
check("render: raised cell tinted red, lowered blue", px(idl, 5, 5)[0] > px(img, 5, 5)[0] && px(idl, 6, 5)[2] > px(img, 6, 5)[2]);
const flatImg = VB.hpRender(new Float32Array(9).fill(5), 3, 3, { cell_ft: 1, lo: 5, hi: 5 });
check("render: flat terrain does not produce NaN", Array.from(flatImg).every(v => v >= 0 && v <= 255));
check("readBin reads little-endian float32", (bb => VB.hpReadBin(bb)[1] === 2.5)(Buffer.from(new Float32Array([1, 2.5]).buffer)));

// job shapes
let j = VB.jobHpApply(st, d, [s], "append");
check("apply job: check, write, apply, preview, stats, remember; quiet", j.noLog === true && j.steps.map(x => x.t).join() === "fn,write,py,py,py,py,fn" && /strokes\.json$/.test(j.steps[1].path), j.steps.map(x => x.t).join());
const ap = j.steps[2].args(); check("apply args", ap.join(" ") === "apply-strokes --place pl --mode append --strokes " + d.panel + "/heightmap_paint_strokes.json", ap.join(" "));
check("undo job has no strokes file", (u => u.steps.map(x => x.t).join() === "py,py,py,py,fn" && u.steps[0].args().join(" ") === "apply-strokes --place pl --mode undo-last")(VB.jobHpApply(st, d, [], "undo-last")));
st.hp.rebuild_pack = true; const sv = VB.jobHpSave(st, d);
check("save + pack appends the pack export", sv.steps.some(x => x.script && /worldpack\.py$/.test(x.script)) && /export the world pack/.test(sv.label));
st.hp.rebuild_pack = false; check("plain save does not", !VB.jobHpSave(st, d).steps.some(x => x.script && /worldpack\.py$/.test(x.script)));

// ---- real python against a scratch world
const mk = cp.spawnSync("python", ["-X", "utf8", "-c", [
  "import numpy as np, json, os, sys",
  "r = sys.argv[1]; T = os.path.join(r, 'world', 'pl', 'terrain'); os.makedirs(T)",
  "h = (100 + np.add.outer(np.linspace(0, 10, 61), np.linspace(0, 20, 71))).astype(np.float32)",
  "np.save(os.path.join(T, 'heightmap.npy'), h)",
  "json.dump({'cell_ft': 2.0, 'nx': 71, 'ny': 61, 'elev_min': float(h.min()), 'elev_max': float(h.max()), 'size_ft': [140, 120], 'origin_ft': [0, 0]}, open(os.path.join(T, 'terrain_meta.json'), 'w'))"
].join("\n"), tmp]);
if (mk.status !== 0) { console.log("cannot build scratch world", String(mk.stderr)); process.exit(1); }
const spawn = (py, args, o) => {
  if (args.some(a => /heightmap_paint\.py$/.test(a))) args = args.concat(["--world-root", tmp + "/world", "--work-dir", tmp + "/work"]);
  return cp.spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  st.hp.tool = "raise"; st.hp.radius_ft = 15; st.hp.rate_ft = 5; st.hp.strength = 1; st.hp.max_px = 128;
  const stroke = VB.hpStroke(st, [[70, 60]]);
  let r = await runner.run(VB.jobHpApply(st, d, [stroke], "append"));
  check("apply job runs", r.ok, r.error);
  check("quiet job writes no jobs-folder entry", !fs.existsSync(tmp + "/jobs/done"));
  const pj = JSON.parse(fs.readFileSync(d.panel + "/heightmap_paint/preview/preview.json", "utf8"));
  check("preview written with place, grid and edit flag", pj.place === "pl" && pj.pw === 71 && pj.ph === 61 && pj.factor === 1 && pj.edited === true, JSON.stringify(pj));
  const H = VB.hpReadBin(fs.readFileSync(d.panel + "/heightmap_paint/preview/preview_h.bin")), D = VB.hpReadBin(fs.readFileSync(d.panel + "/heightmap_paint/preview/preview_d.bin"));
  check("bins match the grid and hold the edit", H.length === 71 * 61 && D.length === H.length && Math.abs(D[30 * 71 + 35] - 5) < 1e-3, D[30 * 71 + 35]);
  check("state remembers stats (1 stroke, unsaved)", st.hp.strokes === 1 && st.hp.unsaved === true && st.hp.stats.summary.changed_cells > 10 && st.hp.meta.place === "pl");
  check("nothing in the world folder yet", !fs.existsSync(tmp + "/world/pl/heightmap_edits.npz"));
  const info = () => JSON.parse(fs.readFileSync(tmp + "/work/heightmap_edits.json", "utf8"));
  const s2 = VB.hpStroke(Object.assign({}, st, { hp: Object.assign({}, st.hp, { tool: "lower" }) }), [[70, 60]]);
  r = await runner.run(VB.jobHpApply(st, d, [s2], "append")); check("second stroke appended", r.ok && st.hp.strokes === 2 && info().strokes.length === 2, r.error);
  r = await runner.run(VB.jobHpApply(st, d, [], "undo-last")); check("undo removes the last stroke", r.ok && st.hp.strokes === 1 && info().strokes[0].tool === "raise", r.error);
  r = await runner.run(VB.jobHpApply(st, d, [s2], "append")); check("redo (append again) restores it", r.ok && st.hp.strokes === 2, r.error);
  r = await runner.run(VB.jobHpSave(st, d));
  check("save copies the layer into the world folder", r.ok && fs.existsSync(tmp + "/world/pl/heightmap_edits.npz") && fs.existsSync(tmp + "/world/pl/heightmap_edits.json") && st.hp.unsaved === false && st.hp.last.saved === true, r.error);
  r = await runner.run(VB.jobHpApply(st, d, [stroke], "append")); r = await runner.run(VB.jobHpDiscard(st, d));
  check("discard goes back to the saved layer", r.ok && st.hp.stats.strokes === 2 && st.hp.unsaved === false, JSON.stringify(st.hp.stats));
  r = await runner.run(VB.jobHpReset(st, d));
  check("reset removes working and saved layers", r.ok && !fs.existsSync(tmp + "/world/pl/heightmap_edits.npz") && !fs.existsSync(tmp + "/work/heightmap_edits.npz") && st.hp.stats.summary.changed_cells === 0, r.error);
  r = await runner.run(VB.jobHpApply(st, d, [], "undo-last")); check("undo with nothing to undo fails cleanly", !r.ok && /nothing to undo/.test(r.error), r.error);
  r = await runner.run(VB.jobHpApply(st, d, [], "append")); check("empty apply refused before python", !r.ok && /no strokes/.test(r.error), r.error);
  // road check + Flatten under roads
  check("check args", VB.hpCheckArgs(st).join(" ") === "check --place pl --layer work --delta-ft 3 --cross-deg 10", VB.hpCheckArgs(st).join(" "));
  check("conform args: flagged roads by default, ids when given", VB.hpConformArgs(st).join(" ") === "conform-roads --place pl --extra-ft 2 --falloff-ft 12 --smooth-ft 40" && VB.hpConformArgs(st, ["a", "b"]).join(" ").indexOf("--roads a,b") > 0);
  fs.writeFileSync(tmp + "/world/pl/streets.json", JSON.stringify({ streets: [{ id: "r1", name: "Near", geometry: { points: [[20, 60], [70, 60], [120, 60]], width_ft: 12 } }] }));
  r = await runner.run(VB.jobHpApply(st, d, [Object.assign({}, stroke, { points: [[70, 52]], radius_ft: 8, rate_ft: 12 })], "append"));
  check("check runs after a stroke and flags the endangered road", r.ok && st.hp.check && st.hp.check.flagged_roads.join() === "r1" && /Road r1/.test(st.hp.check.warnings[0]) && /skirt/.test(st.hp.check.warnings[0]), JSON.stringify(st.hp.check));
  r = await runner.run(VB.jobHpConform(st, d, null));
  check("Flatten under roads is one more stroke and clears the warning", r.ok && st.hp.strokes === 2 && info().strokes[1].tool === "conform-roads" && st.hp.check.flagged_roads.length === 0 && st.hp.unsaved === true, r.error + JSON.stringify(st.hp.check));
  r = await runner.run(VB.jobHpApply(st, d, [], "undo-last"));
  check("undo takes the conform step back (road flagged again)", r.ok && st.hp.strokes === 1 && st.hp.check.flagged_roads.join() === "r1", r.error);
  r = await runner.run(VB.jobHpCheck(st, d)); check("Check roads job", r.ok && st.hp.check.n_roads_changed >= 1, r.error);
  try { fs.rmSync(TMP, { recursive: true, force: true }); } catch (e) { /* scratch */ }
  console.log("\n" + ok + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
