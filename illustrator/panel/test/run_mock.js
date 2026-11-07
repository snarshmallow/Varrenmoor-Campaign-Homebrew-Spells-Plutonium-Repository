// Drives the panel's job flow without Illustrator: real Python generators, mock ExtendScript host.
//   node illustrator/panel/test/run_mock.js [--jobs-dir DIR] [--world-copy DIR] [--only name,name] [--allow-writes]
// By default nothing tracked is modified: the base-terrain regeneration, water edits (illustrator/out/water) and town Accept
// (overwrites world/<place>) are skipped unless --allow-writes is given; restore with git checkout afterwards.
// Job logs go to --jobs-dir (default: a temp folder, never illustrator/jobs). The settings files the panel
// writes (view_settings, terrain_spec) go to --world-copy; generators still read the real world/.
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/lighting.js"); require("../lib/regions.js"); const R = require("../lib/runner.js");
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const ROOT = path.resolve(__dirname, "../../..").replace(/\\/g, "/");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbpanel-"));
const jobsDir = arg("--jobs-dir", path.join(TMP, "jobs"));
const worldCopy = arg("--world-copy", path.join(TMP, "world")).replace(/\\/g, "/");
const WRITES = process.argv.includes("--allow-writes");
const only = (arg("--only", "") || "").split(",").filter(Boolean);
const place = "bridgehollow";
fs.mkdirSync(worldCopy, { recursive: true });
["view_settings.json", "terrain_spec.json", "town_params.json"].forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/${f}`, `${worldCopy}/${f}`));

const d = Object.assign({}, VB.dirs(ROOT, place), { world: worldCopy });
d.terrain = `${ROOT}/world/${place}/terrain`;
const st = VB.normalize(null);
const readCopy = f => JSON.parse(fs.readFileSync(`${worldCopy}/${f}`, "utf8"));
VB.specToState(readCopy("terrain_spec.json"), st.terrain.spec);
VB.townFromParams(readCopy("town_params.json"), st.town);
st.settings.dpi = 40; st.settings.view = "bowl"; st.scale.preset = "bowl"; VB.viewToState(readCopy("view_settings.json"), st.scale);

let hostLog = [], mockSelection = null, fail = 0, ok = 0, hostFail = null;
const host = async a => {
  hostLog.push(a);
  if (hostFail && a.action === hostFail) return { ok: false, error: "mock failure" };
  if (a.action === "get_selection") return mockSelection || { ok: false, error: "no closed path selected" };
  if (a.action === "replace_layer") { if (!fs.existsSync(a.path)) return { ok: false, error: "file not found " + a.path }; return { ok: true, replaced: a.names, items: 10 }; }
  return { ok: true };
};
const textures = JSON.parse(cp.execFileSync("python", ["-X", "utf8", `${ROOT}/illustrator/generators/panelio.py`, "textures"], { encoding: "utf8" })).textures;
const runner = R.createRunner({
  root: ROOT, jobsDir, fs, path, spawn: cp.spawn, host, log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => textures,
  setState: (p, v) => VB.setPath(st, p, v),
  onStale: (s, c) => { s.forEach(k => st.stale[k] = true); c.forEach(k => st.stale[k] = false); }
});
const check = (name, cond, extra) => { if (cond) { ok++; console.log("PASS", name); } else { fail++; console.log("FAIL", name, extra || ""); } };
const want = n => !only.length || only.includes(n);
const run = async (job) => { hostLog = []; return runner.run(job); };
const actions = () => hostLog.map(h => h.action);

(async () => {
  // view mapping: fake a closed path in feet and convert it to document points the way Illustrator would report them
  const view = JSON.parse(cp.execFileSync("python", ["-X", "utf8", `${ROOT}/illustrator/generators/panelio.py`, "view", "--place", place].concat(VB.panelioViewFlags(st)), { encoding: "utf8" }));
  const artboard = [0, 792, 1224, 0];
  const polyFt = [[900, 500], [1300, 500], [1300, 800], [900, 800]];
  st.terrain.patch.polygon = polyFt.map(p => p.slice());
  const toPoints = ft => ft.map(f => { const p = VB.ftToDoc(view, artboard, f); return { a: p, l: p.slice(), r: p.slice() }; });
  mockSelection = { ok: true, source: "selection", artboard, paths: [{ name: "lasso", closed: true, points: toPoints(polyFt) }] };

  if (want("capture")) {
    let r = await run(VB.jobCapture(st, d, { what: "terrain polygon", layer: "TERRAIN AREA", closed: true, store: "terrain.patch.polygon", srcName: "terrain.patch.polygon_src" }));
    const got = st.terrain.patch.polygon;
    check("capture ok", r.ok, r.error);
    check("capture feet round trip", got.length === 4 && got.every((p, i) => Math.abs(p[0] - polyFt[i][0]) < 0.2 && Math.abs(p[1] - polyFt[i][1]) < 0.2), JSON.stringify(got));
    const circ = VB.flatten([{ a: [0, 0], l: [0, 0], r: [0, 10] }, { a: [10, 10], l: [0, 10], r: [10, 10] }], false, 4);
    check("bezier flatten", circ.length === 5 && circ[0][0] === 0 && circ[4][0] === 10, JSON.stringify(circ));
    const saved = mockSelection; mockSelection = { ok: false, error: "no closed path selected" };
    r = await run(VB.jobCapture(st, d, { what: "x", layer: "TERRAIN AREA", closed: true, store: "terrain.patch.polygon" }));
    check("capture with nothing selected fails visibly", !r.ok && /no closed path/.test(r.error), r.error);
    mockSelection = saved;
  }
  if (want("scale")) {
    let r = await run(VB.jobScaleApply(st, d, false));
    check("scale apply ok", r.ok, r.error);
    check("guides unlocked, replaced, relocked", JSON.stringify(actions()) === JSON.stringify(["lock_layers", "replace_layer", "lock_layers"]), actions().join());
    const vs = readCopy("view_settings.json");
    check("view_settings written", vs.presets.bowl.scale_ft_per_in === 200 && vs.page_in[0] === 17);
    check("stale set by scale change", st.stale.contours && st.stale.shading);
    r = await run(VB.jobScaleApply(st, d, true));
    check("redraw all ok", r.ok, r.error);
    check("redraw all names include contours", hostLog.find(h => h.action === "replace_layer").names.includes("Contours - Index"));
  }
  if (want("terrain")) {
    let r;
    if (WRITES) { r = await run(VB.jobTerrainGenerate(st, d)); check("terrain generate ok", r.ok, r.error); }
    else { const j = VB.jobTerrainGenerate(st, d); check("terrain generate builds spec + terrain.py + rebuild steps (not run)", j.steps.length === 3 && j.steps[1].args[0] === "--place"); }
    r = await run(VB.jobPatch(st, d, "preview"));
    check("patch preview ok", r.ok, r.error);
    const j = runner.parseJsonOut(r.out || "");
    check("patch preview reports fit", j && j.info && Math.abs(j.info.max - st.terrain.patch.max_height_ft) < 0.6, JSON.stringify(j && j.info));
    check("preview png exists", fs.existsSync(`${d.patchPreview}/preview_hillshade.png`));
    st.terrain.patch.terrain_type = "bowl";
    r = await run(VB.jobPatch(st, d, "preview"));
    check("depression preview uses min height", r.ok, r.error);
    st.terrain.patch.terrain_type = "mountain";
    const keep = st.terrain.patch.polygon; st.terrain.patch.polygon = [];
    r = await run(VB.jobPatch(st, d, "preview"));
    check("patch without polygon gives a visible error", !r.ok && /no polygon/.test(r.error), r.error);
    st.terrain.patch.polygon = keep;
    r = await run(VB.jobPatchCmd(st, d, "list"));
    check("patch list command", r.ok, r.error);
  }
  if (want("contours")) {
    let r = await run(VB.jobContours(st, d));
    check("contours ok", r.ok, r.error);
    check("contours svg replaced layers", hostLog.some(h => h.action === "replace_layer" && h.names.join() === VB.CONTOUR_LAYERS.join()));
    st.contours.labels = false; st.contours.follow_line = false; st.contours.mask = false; st.contours.decimals = 1;
    r = await run(VB.jobContours(st, d));
    check("contours with all flags ok", r.ok, r.error);
    st.contours.labels = true; st.contours.follow_line = true; st.contours.mask = true; st.contours.decimals = 0;
    check("contours stale cleared", st.stale.contours === false);
  }
  if (want("labels")) {
    const pyDef = JSON.parse(cp.execFileSync("python", ["-X", "utf8", "-c", "import sys,json;sys.path.insert(0,'" + ROOT + "/illustrator/generators');import label_style as L;print(json.dumps(L.defaults()))"], { encoding: "utf8" }));
    const jsDef = VB.labelDefaults();
    check("label defaults agree (python == panel)", JSON.stringify(Object.keys(jsDef).sort()) === JSON.stringify(Object.keys(pyDef).filter(k => k in jsDef).sort())
      && Object.keys(pyDef.default).every(k => jsDef.default[k] === pyDef.default[k]) && VB.LABEL_CATS.every(c => JSON.stringify(jsDef[c]) === JSON.stringify(pyDef[c])), JSON.stringify([jsDef, pyDef]));
    let r = await run(VB.jobLabels(st, d));
    check("labels job ok", r.ok, r.error);
    const rl = hostLog.find(h => h.action === "replace_layer");
    check("labels job replaces label + backing + cut linework layers", rl && ["Label Backing", "Leaders", "Labels - Districts", "Roads", "Contours - Minor", "Grid"].every(n => rl.names.includes(n)), JSON.stringify(rl && rl.names));
    st.labels.styles.default.mode = "mask"; st.labels.styles.districts.size = 12; st.labels.styles.default.font = "Georgia"; st.labels.mask_targets.water = true; st.labels.backing_layer = false;
    const js = JSON.parse(Buffer.from(VB.labelStyleFlags(st)[1], "base64").toString("utf8"));
    check("label flags carry style, targets and backing option", js.default.font === "Georgia" && js.districts.size === 12 && js.mask_targets.includes("water") && js.backing_layer === false);
    r = await run(VB.jobLabels(st, d));
    check("labels job with mask/font/size/no backing layer renders", r.ok, r.error);
    st.labels.styles.default.mode = "halo"; st.labels.styles.districts = VB.labelDefaults().districts; st.labels.styles.default.font = "Arial"; st.labels.mask_targets.water = false; st.labels.backing_layer = true;
  }
  if (want("shading")) {
    st.stale.shading = true;
    let r = await run(VB.jobShading(st, d));
    check("shading ok", r.ok, r.error);
    const pi = hostLog.find(h => h.action === "place_image");
    check("place_image on ART - Shading below LINES, locked", pi && pi.layer === "ART - Shading" && Array.isArray(pi.below) && pi.below[pi.below.length - 1] === "LINES" && pi.lock === true, JSON.stringify(pi));
    check("shading rect registers with the map", pi && Math.abs((pi.rect[2] - pi.rect[0]) - 2400 * view.k) < 0.01 && Math.abs((pi.rect[3] - pi.rect[1]) - 1500 * view.k) < 0.01, JSON.stringify(pi && pi.rect));
    check("shading stale cleared", st.stale.shading === false);
    check("phases file has panel hillshade", JSON.parse(fs.readFileSync(`${d.panel}/phases.json`, "utf8")).hillshade.azimuth === 315);
    hostFail = "place_image"; r = await run(VB.jobShading(st, d)); hostFail = null;
    check("host failure on place is a warning, not a failure", r.ok && r.warnings.length === 1, JSON.stringify(r));
  }
  if (want("lighting")) {
    const L = st.lighting;
    check("lighting defaults present", L && L.sun.azimuth === 225 && VB.normalize({}).lighting.ambient === 0.35);
    VB.applyLightingPreset(st, "night"); L.lights = [VB.newLight("lantern", 1)]; L.lights[0].x = 1150; L.lights[0].y = 745; L.vector = true;
    const cfg = VB.lightingConfig(st);
    check("night config has moon sun + lantern", cfg.lights.length === 2 && cfg.lights[0].type === "sun" && cfg.lights[1].type === "point" && cfg.lights[1].x === 1150 && cfg.ambient === 0.14, JSON.stringify(cfg.lights));
    st.scale.scale_ft_per_in = 100; st.scale.preset = "town"; st.settings.view = "town";
    let r = await run(VB.jobLighting(st, d, { preview: true }));
    check("lighting preview ok", r.ok, r.error);
    const pis = hostLog.filter(h => h.action === "place_image"), v = JSON.parse(fs.readFileSync(`${d.panel}/lighting/lighting.json`, "utf8"));
    check("shadows and glow placed below LINES, above the fills", pis.length === 2 && pis[0].layer === "ART - Shadows" && pis[1].layer === "ART - Light Glow" && pis.every(p => p.below[p.below.length - 1] === "LINES" && p.lock === true), JSON.stringify(pis.map(p => [p.layer, p.below])));
    check("shadows go above every fill layer", ["ART - Fill Buildings", "ART - Fill Streets", "ART - Shading"].every(n => VB.FILL_ORDER.indexOf(n) < VB.FILL_ORDER.indexOf("ART - Shadows")) && !pis[0].below.includes("ART - Fill Buildings"));
    const tv = JSON.parse(cp.execFileSync("python", ["-X", "utf8", `${ROOT}/illustrator/generators/panelio.py`, "view", "--place", place].concat(VB.panelioViewFlags(st)), { encoding: "utf8" }));
    check("shadow rect registers with the map window", Math.abs((pis[0].rect[2] - pis[0].rect[0]) - (v.bounds_ft.x_max - v.bounds_ft.x_min) * tv.k) < 0.01 && Math.abs(pis[0].rect[0] - (tv.margin_in * 72)) < 0.01, JSON.stringify(pis[0].rect));
    const rl = hostLog.find(h => h.action === "replace_layer");
    check("vector shadows replace LINES/Shadows", rl && rl.names[0] === "Shadows" && v.vector && v.vector.polygons > 0, JSON.stringify(rl));
    L.mode = "sun"; L.vector = false;
    r = await run(VB.jobLighting(st, d, { preview: true }));
    check("sun-only render removes the stale glow", r.ok && hostLog.some(h => h.action === "remove_item" && h.layer === "ART - Light Glow") && !hostLog.some(h => h.action === "replace_layer"), r.error);
    mockSelection = { ok: true, source: "selection", artboard, paths: [{ name: "pt", closed: false, points: [VB.ftToDoc(tv, artboard, [1000, 700])].map(q => ({ a: q, l: q.slice(), r: q.slice() })), selected: [0] }] };
    r = await run(VB.jobLightCapture(st, d));
    check("capture point gives feet", r.ok && Math.abs(L.capture[0] - 1000) < 0.2 && Math.abs(L.capture[1] - 700) < 0.2, JSON.stringify(L.capture) + (r.error || ""));
  }
  if (want("water") && !WRITES) {
    for (const [n, j] of [["analyze", VB.jobWaterAnalyze(st, d)], ["carve", VB.jobWaterCarve(st, d)], ["crossings", VB.jobWaterCrossings(st, d)]]) check("water " + n + " command line (not run)", j.steps[0].args[0] === n || j.steps[0].args[0] === "crossings", JSON.stringify(j.steps[0].args));
    st.water.river_path = [[100, 100], [300, 200]]; st.water.lake_polygon = polyFt;
    check("add-river args", VB.jobWaterRiver(st, d).steps[1].args.includes("100,100;300,200"));
    check("add-lake args", VB.jobWaterLake(st, d).steps[1].args.includes("900,500;1300,500;1300,800;900,800"));
    st.water.river_path = []; const r2 = await run(VB.jobWaterRiver(st, d));
    check("river without path is a visible error", !r2.ok && /no river path/.test(r2.error), r2.error);
  }
  if (want("water") && WRITES) {
    for (const [n, j] of [["analyze", VB.jobWaterAnalyze(st, d)], ["carve", VB.jobWaterCarve(st, d)], ["crossings", VB.jobWaterCrossings(st, d)]]) {
      const r = await run(j); check("water " + n + " ok", r.ok, r.error);
    }
    st.water.river_path = [[100, 100], [300, 200], [500, 260]];
    st.water.lake_polygon = polyFt;
    let r = await run(VB.jobWaterRiver(st, d)); check("water add-river ok", r.ok, r.error);
    r = await run(VB.jobWaterLake(st, d)); check("water add-lake ok", r.ok, r.error);
    check("water redraw replaced Water layer", hostLog.some(h => h.action === "replace_layer" && h.names[0] === "Water"));
    st.water.river_path = [];
    r = await run(VB.jobWaterRiver(st, d)); check("river without path is a visible error", !r.ok && /no river path/.test(r.error), r.error);
  }
  if (want("town")) {
    st.town.area = JSON.parse(fs.readFileSync(`${ROOT}/world/${place}/town_params.json`, "utf8")).area_ft; // same lasso as the saved model
    st.town.style.streets = "parch_light"; st.town.style.buildings = "red_rock"; st.town.style.water = "water_blue"; st.town.style.stroke = "#4a3320";
    st.town.fills.full = false;      // legacy flat fills path first
    let r = await run(VB.jobTown(st, d));
    check("town generate ok", r.ok, r.error);
    check("candidate written and flagged", fs.existsSync(`${d.candidate}/streets.json`) && st.town.candidate === true);
    const fills = hostLog.find(h => h.action === "apply_fills");
    check("apply_fills after drawing, on named layers", fills && fills.assignments.some(a => a.layer === "Roads" && a.exclude === "^sqr_" && a.fill) && fills.assignments.some(a => a.layer === "Buildings" && a.stroke), JSON.stringify(fills));
    hostLog.length = 0; st.town.fills.full = true;
    r = await run(VB.jobFullFills(st, d));
    check("full fills job ok", r.ok, r.error);
    const pl = hostLog.filter(h => h.action === "place_image" && /ART - Fill /.test(h.layer));
    check("four fill rasters placed below LINES, each aligned to the view window", pl.length === 4 && pl.every(h => h.below[h.below.length - 1] === "LINES" && h.rect.every(Number.isFinite)) && pl[0].rect.join() === pl[3].rect.join(), JSON.stringify(pl.map(h => h.layer)));
    check("PNGs exist at the placed paths", pl.every(h => fs.existsSync(h.path)));
    const ff = hostLog.find(h => h.action === "apply_fills" && h.clear);
    check("flat copies go to ART - Fill Shapes with ids and swatches", ff && ff.assignments.length > 3 && ff.assignments.every(a => a.copy_to === "ART - Fill Shapes" && a.ids.length && a.fill.length === 3), JSON.stringify(ff).slice(0, 300));
    check("autofill after drawing uses the textured pipeline by default", VB.autoFillSteps(st, d).some(x => /fills_raster/.test(x.label || "")) );
    r = await run(VB.jobTownReject(st, d));
    check("town reject ok, candidate gone, flag cleared", r.ok && !fs.existsSync(d.candidate) && st.town.candidate === false, r.error);
    if (WRITES) {
      r = await run(VB.jobTown(st, d));
      r = await run(VB.jobTownAccept(st, d));
      check("town accept ok (candidate copied over world, then removed)", r.ok && !fs.existsSync(d.candidate) && st.town.candidate === false, r.error);
    }
    st.town.area = []; r = await run(VB.jobTown(st, d));
    check("town without lasso gives a visible error", !r.ok && /no lasso/.test(r.error), r.error);
    r = await run(VB.jobFills(st, d)); check("fills job ok", r.ok, r.error);
  }
  if (want("layers")) {
    for (const a of ["lock_guides", "unlock_guides", "show_labels", "hide_labels"]) { const r = await run(VB.jobLayers(a, st)); check("layers " + a, r.ok, r.error); }
  }
  if (want("runner")) {
    const sleeper = path.join(TMP, "sleep.py").replace(/\\/g, "/"); fs.writeFileSync(sleeper, "import time\nprint('start', flush=True)\ntime.sleep(30)\n");
    const job = { kind: "sleep", label: "sleeper", params: {}, steps: [VB.steps.py(sleeper, [], "sleep")] };
    const p1 = runner.run(job);
    await new Promise(r => setTimeout(r, 700));
    const second = await runner.run(job);
    check("second job refused while one runs", !second.ok && /another job/.test(second.error), second.error);
    check("cancel returns true", runner.cancel() === true);
    const res = await p1;
    check("cancelled job reports cancelled", !res.ok && res.cancelled, JSON.stringify(res));
    check("runner idle after cancel", runner.isBusy() === false);
    const bad = R.createRunner({ root: ROOT, jobsDir, fs, path, spawn: cp.spawn, host, getPython: () => "python_does_not_exist_xyz", setState() {}, onStale() {} });
    const rb = await bad.run({ kind: "nopy", label: "no python", params: {}, steps: [VB.steps.py("illustrator/generators/panelio.py", ["textures"], "panelio")] });
    check("missing python gives a clear error", !rb.ok && /python not found/.test(rb.error), rb.error);
    const rf = await runner.run({ kind: "bad", label: "bad", params: {}, steps: [VB.steps.py("illustrator/generators/terrain_patch.py", ["preview", "--place", "no_such_place", "--polygon", "x", "--params", "y"], "tp")] });
    check("generator failure shows message", !rf.ok && /exited with code/.test(rf.error), rf.error);
    const rm = await runner.run({ kind: "bad2", label: "bad2", params: {}, steps: [VB.steps.py("illustrator/generators/render_world.py", ["--place", "nope"], "rw")] });
    check("missing world files give a visible error", !rm.ok, rm.error);
  }
  { // Foundry tab helpers + the Python tool through the runner
    const st = VB.normalize(null); st.foundry.sceneName = " ZZ Test "; st.foundry.drawRoads = true; st.foundry.drawWater = true;
    const args = VB.foundryPushSceneArgs(st, { image: "x.png", tileImage: "t.png" });
    check("push args: new scene by name", args.includes("--scene-name") && args[args.indexOf("--scene-name") + 1] === "ZZ Test" && args.includes("--walls"), args.join(" "));
    check("push args: drawings + tile", args[args.indexOf("--drawings") + 1] === "roads,water" && args.includes("--tile-image"));
    st.foundry.target = "existing";
    let msg = ""; try { VB.foundryPushSceneArgs(st, { image: "x.png" }); } catch (e) { msg = e.message; }
    check("existing target needs a picked scene", /pick an existing scene/.test(msg), msg);
    st.foundry.sceneUuid = "Scene.abc"; check("existing target uses uuid", VB.foundryPushSceneArgs(st, { image: "x.png" }).includes("Scene.abc"));
    check("cache age", VB.cacheAgeMin({ fetched: new Date(Date.now() - 125 * 60000).toISOString() }) === 125 && VB.cacheAgeMin({}) === null);
    check("picker filter+sort", VB.pickerRows([{ name: "Zed" }, { name: "Abe" }, { name: "abel" }], "ab").map(r => r.name).join() === "Abe,abel");
    const runner2 = R.createRunner({ root: ROOT, jobsDir, fs, path, spawn: cp.spawn, host, getPython: () => "python", setState() {}, onStale() {} });
    const r = await runner2.execPy(VB.FOUNDRY_PY, ["places"]), j = runner2.parseJsonOut(r.out);
    check("foundry_push places through the runner", j && j.ok && j.places.includes("bridgehollow"), r.out + r.err);
    const e = await runner2.execPy(VB.FOUNDRY_PY, ["export-info", "--place", "bridgehollow"].concat(VB.viewFlags(VB.normalize(null)))), ej = runner2.parseJsonOut(e.out);
    check("export-info gives window in feet", ej && ej.ok && ej.window_ft[2] === 1600, e.out + e.err);
  }
  if (want("worldpack")) { // world pack export + split + merge jobs and the push-models arguments (exports into the temp folder, never world/)
    const st = VB.normalize(null), out = path.join(TMP, "pack").replace(/\\/g, "/");
    let r = await run(VB.jobWorldPack(st, d, out));
    check("world pack export job ok", r.ok && fs.existsSync(`${out}/manifest.json`), r.error);
    r = await run(VB.jobWorldSplit(st, d, out)); check("split models job ok", r.ok && fs.existsSync(`${out}/placements.json`), r.error);
    st.foundry.models.preset = "all"; r = await run(VB.jobWorldMerge(st, d, out)); check("merge models job ok", r.ok && fs.existsSync(`${out}/optimized`), r.error);
    st.foundry.sceneName = "ZZ Model Push Test"; st.foundry.models.layers = "buildings"; st.foundry.models.lod = "1";
    const a = VB.worldPushArgs(st, d, { dry: true, placements: `${out}/placements.json` });
    check("push-models args", a.includes("--scene-name") && a.includes("--layers") && a.includes("--lod") && a.includes("--dry-run"), a.join(" "));
    const runner3 = R.createRunner({ root: ROOT, jobsDir, fs, path, spawn: cp.spawn, host, getPython: () => "python", setState() {}, onStale() {} });
    const pr = await runner3.execPy(VB.FOUNDRY_PY, a.concat(["--assets-dir", path.join(TMP, "assets")])), pj = runner3.parseJsonOut(pr.out);
    check("push-models dry run through the runner", pj && pj.ok && pj.dry_run && pj.tiles > 0, pr.out + pr.err);
    st.town.exportPack = true; check("accept job adds the export step when the toggle is on", VB.jobTownAccept(st, d).steps.length === 2);
    st.town.exportPack = false; check("accept job unchanged when the toggle is off", VB.jobTownAccept(st, d).steps.length === 1);
  }
  if (want("regions")) { // zoom-in child maps: command lines, extract + render through the real generators into world/_region_test (git-ignored), host actions, sync diff
    const S = VB.normalize(null), r = S.regions;
    check("regions defaults present", r && r.mode === "district" && r.scale_ft_per_in === 20 && r.grid_ft === 5 && r.margin_ft === 40);
    check("no district picked is an error", /pick a district/.test(VB.regionCheck(S)));
    r.district = "dis_authority"; r.name = "Mock Ward"; r.sandbox = true; r.margin_ft = 30; r.fills = false; r.shading = "none"; r.contour_minor = 2;
    check("child id derives from place and name", VB.regionChildId(S) === "_region_test/bridgehollow__mock_ward", VB.regionChildId(S));
    check("scale presets", (VB.regionApplyPreset(r, "block40"), r.scale_ft_per_in === 40 && r.grid_ft === 10) && (VB.regionApplyPreset(r, "street20"), r.scale_ft_per_in === 20 && r.grid_ft === 5));
    check("export dpi gives the asked grid px", VB.regionDpi(r) === 320, String(VB.regionDpi(r)));
    const ea = VB.regionExtractArgs(S, d);
    check("extract args", ea[0] === "extract" && ea.includes("--district") && ea.includes("--sandbox") && ea.includes("--force") && ea[ea.indexOf("--detail") + 1] === "all", ea.join(" "));
    r.detail.trees = false; check("detail toggles", VB.regionDetailArg(r) === "doors,roofs,chimneys,lots,fences,kerbs"); r.detail.trees = true;
    r.mode = "lasso"; r.polygon = []; check("lasso mode needs a captured polygon", /Capture lasso/.test(VB.regionCheck(S)));
    r.polygon = polyFt.map(p => p.slice()); check("lasso args use the polygon file", VB.regionSpecArgs(S, d)[0] === "--polygon-file");
    r.mode = "rect"; r.rect = [900, 500, 1300, 800]; check("rect args", VB.regionSpecArgs(S, d).join() === "--rect,900,500,1300,800");
    // preview: py preview + replace_layer REGIONS
    let res = await run(VB.jobRegionPreview(S, d));
    check("preview job ok", res.ok, res.error);
    const rl0 = hostLog.find(h => h.action === "replace_layer");
    check("preview draws the REGIONS layer", rl0 && rl0.names[0] === "REGIONS", JSON.stringify(rl0));
    // create from a rectangle (no fills: fast) through the real generators
    r.mode = "rect"; r.rect = [900, 600, 1200, 800]; r.name = "Mock Ward"; r.margin_ft = 20;
    const childDir = `${ROOT}/world/_region_test/bridgehollow__mock_ward`;
    res = await run(VB.jobRegionCreate(S, d));
    check("create job ok", res.ok, res.error);
    const acts_ = actions();
    check("create opens the svg, saves, exports", acts_[0] === "place_svg" && hostLog[0].mode === "open" && acts_.includes("save_ai") && acts_.includes("export_png"), acts_.join());
    check("child written", fs.existsSync(`${childDir}/region.json`) && fs.existsSync(`${childDir}/terrain/heightmap.npy`));
    check("child list and selection stored", st.regions.sel === "_region_test/bridgehollow__mock_ward" && st.regions.children.some(c => c.child === st.regions.sel), JSON.stringify(st.regions.children));
    const ai = hostLog.find(h => h.action === "save_ai");
    check("an existing .ai is never overwritten (free name picked)", ai && !fs.existsSync(path.resolve(ROOT, ai.path)), ai && ai.path);
    // sync diff (writes nothing), then refresh keeps a child edit
    const bf = fs.readdirSync(`${childDir}/buildings`)[0], bp = `${childDir}/buildings/${bf}`, b = JSON.parse(fs.readFileSync(bp, "utf8"));
    b.name = "Panel test name"; fs.writeFileSync(bp, JSON.stringify(b));
    res = await run(VB.jobRegionSync(S, d, st.regions.sel, false));
    check("sync diff job shows the rename and writes nothing", res.ok && st.regions.diff.n >= 1 && /Panel test name/.test(st.regions.diff.text) && !st.regions.diff.applied, res.error || JSON.stringify(st.regions.diff));
    res = await run(VB.jobRegionCreate(S, d, { refresh: true, child: st.regions.sel }));
    check("refresh job ok and keeps the edit", res.ok && JSON.parse(fs.readFileSync(bp, "utf8")).name === "Panel test name", res.error);
    // Foundry (dry run only: the module is not touched)
    const fj = VB.jobRegionFoundry(S, d, st.regions.sel, { dry: true });
    check("foundry job exports the child at the grid dpi", fj.steps[1].action.dpi === 320 && fj.steps[2].args.includes("--dry-run") && fj.steps[2].args.includes("region"), JSON.stringify(fj.steps[2].args));
    S.regions.parent_scene_name = "Bridgehollow town"; const lj = VB.jobRegionLink(S, d, st.regions.sel);
    check("link is a dry run unless confirmed", !lj.steps[1].args.includes("--apply") && lj.steps[1].args.includes("link-region"));
    S.regions.link_apply = true; check("link apply needs the checkbox", VB.jobRegionLink(S, d, st.regions.sel).steps[1].args.includes("--apply"));
    fs.rmSync(childDir, { recursive: true, force: true });
  }
  if (want("links")) {
    check("embed is the default for placed rasters", VB.embedOn(st) === true && st.settings.link_images === false);
    let r = await run(VB.jobFullFills(st, d));
    const pe = hostLog.filter(h => h.action === "place_image");
    check("fills placed with embed true", r.ok && pe.length > 0 && pe.every(h => h.embed === true), r.error);
    check("fills job ends with check_links", actions()[actions().length - 1] === "check_links");
    st.settings.link_images = true;
    await run(VB.jobFullFills(st, d));
    check("link toggle places linked images", hostLog.filter(h => h.action === "place_image").every(h => h.embed === false));
    st.settings.link_images = false;
    r = await run(VB.jobCheckLinks(st, d, true));
    const rl2 = hostLog.find(h => h.action === "relink");
    check("relink job searches the render folders and embeds", r.ok && rl2 && rl2.embed === true && rl2.folders.some(f => /panel\/bridgehollow\/fills$/.test(f)), JSON.stringify(rl2));
    r = await run(VB.jobCheckLinks(st, d, false));
    check("check_links job ok", r.ok && actions().join() === "check_links", r.error);
  }
  const logs = fs.existsSync(path.join(jobsDir, "done")) ? fs.readdirSync(path.join(jobsDir, "done")) : [];
  check("each run logged exact params to jobs/done", logs.length > 3 && logs.every(f => /^panel_\d{8}_\d{6}_.+\.json$/.test(f)), logs.length + " files");
  if (logs.length) { const j = JSON.parse(fs.readFileSync(path.join(jobsDir, "done", logs[0]), "utf8")); check("log has params + steps", j.params !== undefined && Array.isArray(j.steps)); }
  console.log(`\n${ok} passed, ${fail} failed; job logs in ${jobsDir}`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error("test crashed:", e); process.exit(2); });
