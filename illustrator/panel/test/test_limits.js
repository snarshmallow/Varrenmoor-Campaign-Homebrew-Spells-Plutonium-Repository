// Size and performance limits (lib/limits.js): table by scale, scene calibration, evaluate cases (Bridgehollow overview = danger reference), monotonic
// thresholds, export notes, publish on window under CEP.   node illustrator/panel/test/test_limits.js
const fs = require("fs"), path = require("path"), vm = require("vm");
const L = require("../lib/limits.js");
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x === undefined ? "" : JSON.stringify(x)); } };
const codes = (list, level) => list.filter(x => !level || x.level === level).map(x => x.code);
const by = (list, code) => list.filter(x => x.code === code)[0] || null;

// table
const T = L.table();
check("table has the 6 scales (5 ft x2, 10, 25, 50, 100 ft)", T.map(t => t.grid_ft).join(",") === "5,5,10,25,50,100", T.map(t => t.grid_ft));
check("5 ft @ 100 px = 20 px/ft, 2D max 409 ft (8192 px), hard 819 ft", T[0].ppf === 20 && T[0].rec2d_ft === 409 && T[0].hard2d_ft === 819, T[0]);
check("100 ft @ 150 px = 1.5 px/ft, 2D max 5461 ft", T[5].ppf === 1.5 && T[5].rec2d_ft === 5461, T[5]);
check("3D limits from light density: about 650 / 1000 ft", L.EXTENT3D_REC_FT === 650 && L.EXTENT3D_HARD_FT === 1000, [L.EXTENT3D_REC_FT, L.EXTENT3D_HARD_FT]);
check("3D max never above the 2D pixel limit", T.every(t => t.rec3d_ft <= t.rec2d_ft && t.hard3d_ft <= t.hard2d_ft));
check("every row: recommended <= hard", T.every(t => t.rec2d_ft <= t.hard2d_ft && t.rec3d_ft <= t.hard3d_ft && t.lights_rec <= t.lights_hard && t.buildings_rec <= t.buildings_hard && t.tiles_rec <= t.tiles_hard && t.tris_rec <= t.tris_hard && t.foliage_rec <= t.foliage_hard));
check("light limits: 64 rec / 150 hard on play maps, 16 on overview maps", T[0].lights_rec === 64 && T[0].lights_hard === 150 && T[4].lights_rec === 16 && T[5].lights_rec === 16);
check("token check: 5 ft grid = whole square, 100 ft grid = 5% and overview", T[0].token.fraction === 1 && !T[0].token.small && T[5].token.overview && Math.abs(T[5].token.fraction - 0.05) < 1e-9 && T[5].token.token_px === 7.5, T[5].token);
check("token small from 25 ft (under a quarter), overview above 25 ft", T[3].token.small && !T[3].token.overview && !T[2].token.small);
// monotonic: more px per ft -> smaller max extent; bigger grid ft at same px -> larger
{
  let mono = true, prev = Infinity;
  [0.5, 1, 2, 5, 10, 20, 40].forEach(ppf => { const t = L.limitsFor(5, 5 * ppf); if (t.rec2d_ft > prev) mono = false; prev = t.rec2d_ft; });
  let prev2 = 0, mono2 = true;
  [5, 10, 25, 50, 100].forEach(g => { const t = L.limitsFor(g, 50); if (t.rec2d_ft < prev2) mono2 = false; prev2 = t.rec2d_ft; });
  check("thresholds monotonic in px/ft and grid size", mono && mono2);
  const lv = n => L.worst(L.evaluate({ lights: n }));
  check("lights level grows with the count (ok -> warn -> danger)", lv(10) === "ok" && lv(100) === "warn" && lv(200) === "danger" && lv(64) === "ok" && lv(65) === "warn" && lv(150) === "warn" && lv(151) === "danger");
  const ev = w => L.worst(L.evaluate({ w_ft: w, h_ft: w, grid_ft: 5, grid_px: 50 }).filter(x => x.code === "extent3d"));
  check("3D extent level grows with size", ev(300) === "ok" && ev(800) === "warn" && ev(1200) === "danger");
}

// scene calibration = foundry_push.calibrate
const bh = L.sceneCalib({ w_ft: 2400, h_ft: 1500, dpi: 150, scale_ft_per_in: 100, grid_ft: 100, upscale: 1, max_px: 8192 });
check("Bridgehollow calibration: 1.5 px/ft, grid 150 px = 100 ft, 3600 x 2250 px", bh.ppf === 1.5 && bh.grid_px === 150 && bh.width === 3600 && bh.height === 2250 && !bh.error, bh);
const tiny = L.sceneCalib({ w_ft: 2400, h_ft: 1500, dpi: 150, scale_ft_per_in: 100, grid_ft: 5 });
check("5 ft grid at 1.5 px/ft = 8 px: calibration error (pipeline 50 px minimum)", tiny.grid_px === 8 && /minimum is 50/.test(tiny.error), tiny);
const capped = L.sceneCalib({ w_ft: 2400, h_ft: 1500, dpi: 300, scale_ft_per_in: 10, grid_ft: 5, max_px: 8192 });
check("max_px scales the scene down to 8192 px like calibrate()", capped.width <= 8192 + 50 && capped.grid_px === Math.round(30 * (8192 / 72000) * 5), capped);

// Bridgehollow overview (the live push): danger reference
const BH = { w_ft: 2400, h_ft: 1500, grid_ft: 100, grid_px: 150, mode: "3d", buildings: 148, lights: 514, lighting: null, tiles: 302, triangles: 320498, roofMode: "per_building" };
let r = L.evaluate(BH);
check("Bridgehollow: worst level is danger", L.worst(r) === "danger", r.map(x => x.level + ":" + x.code));
check("Bridgehollow: token warning (overview map, 5% of a square, 100 ft wide in 3D)", by(r, "token") && by(r, "token").level === "warn" && /overview map/.test(by(r, "token").message) && /street scene/.test(by(r, "token").suggestion), by(r, "token"));
check("Bridgehollow: 514 lights with every light on = danger", by(r, "lights").level === "danger" && /514/.test(by(r, "lights").message), by(r, "lights"));
check("Bridgehollow: 2400 ft over the 3D hard size = danger with split advice", by(r, "extent3d").level === "danger" && /split/i.test(by(r, "extent3d").suggestion), by(r, "extent3d"));
check("Bridgehollow: 302 tiles noted, 148 buildings info, scene pixels fine", by(r, "tiles").level === "info" && by(r, "buildings").level === "info" && by(r, "scene_px").level === "ok", r);
r = L.evaluate(Object.assign({}, BH, { lighting: { mode: "auto", maxLights: 0 } }));
check("514 lights with the auto budget: warning (pack has 514, 0 visible)", by(r, "lights").level === "warn" && /514/.test(by(r, "lights").message) && /keeps 0 visible/.test(by(r, "lights").message), by(r, "lights"));
check("visibleLights follows foundry_lightbudget rules", L.visibleLights(514, { mode: "auto" }) === 0 && L.visibleLights(100, { mode: "auto" }) === 16 && L.visibleLights(50, { mode: "auto" }) === 50 && L.visibleLights(514, { mode: "lights", maxLights: 40 }) === 40 && L.visibleLights(514, null) === 514);

// ok cases
r = L.evaluate({ w_ft: 300, h_ft: 360, grid_ft: 5, grid_px: 100, buildings: 25, lights: 60, tiles: 28, triangles: 62000, foliage: 500, roofMode: "per_building" });
check("Dyers-size street at 5 ft / 100 px: no warnings (only the fog-resolution note at 7200 px)", L.RANK[L.worst(r)] <= L.RANK.info && codes(r, "info").join() === "scene_px", r.filter(x => x.level !== "ok"));
r = L.evaluate({ w_ft: 300, h_ft: 300, grid_ft: 5, grid_px: 50, lights: 0 });
check("small battle map: no warnings", codes(r, "warn").length === 0 && codes(r, "danger").length === 0);
r = L.evaluate({});
check("no facts: empty list, worst ok", r.length === 0 && L.worst(r) === "ok");

// other warnings
r = L.evaluate({ w_ft: 2000, h_ft: 2000, grid_ft: 5, grid_px: 100, mode: "2d" });
check("2D scene 40000 px: scene_px danger, no 3D extent check in 2D", by(r, "scene_px").level === "danger" && !by(r, "extent3d"), r);
r = L.evaluate({ w_ft: 500, h_ft: 300, grid_ft: 5, grid_px: 100, mode: "2d" });
check("10000 px scene: warning; 5000 px: fog info", by(r, "scene_px").level === "warn" && by(L.evaluate({ w_ft: 250, h_ft: 100, grid_ft: 5, grid_px: 100, mode: "2d" }), "scene_px").level === "info");
check("grid 30 px = warn (pipeline 50), 10 px = danger (Foundry 14 minimum 20)", by(L.evaluate({ grid_ft: 5, grid_px: 30 }), "grid_px").level === "warn" && by(L.evaluate({ grid_ft: 5, grid_px: 10 }), "grid_px").level === "danger");
check("per-building roofs above 150 buildings warned", by(L.evaluate({ buildings: 200, roofMode: "per_building" }), "roofs") && !by(L.evaluate({ buildings: 200, roofMode: "per_scene" }), "roofs"));
check("triangles and foliage thresholds", by(L.evaluate({ triangles: 6e6 }), "tris").level === "danger" && by(L.evaluate({ triangles: 1e6 }), "tris").level === "warn" && !by(L.evaluate({ triangles: 3e5 }), "tris") && by(L.evaluate({ foliage: 12000 }), "foliage").level === "warn" && by(L.evaluate({ foliage: 4000 }), "foliage").level === "info");
check("every finding has a source text for the tooltip", L.evaluate(BH).every(x => typeof x.source === "string" && x.source.length > 20));
check("notes(): warn and danger only, plain prefixes", L.notes(L.evaluate(BH)).length === L.evaluate(BH).filter(x => x.level === "warn" || x.level === "danger").length && L.notes(L.evaluate(BH)).every(s => /^(SIZE PROBLEM|Size warning): /.test(s)));
const rec = L.recommend(2400, 1500, 100, 150);
check("recommend: limits sentence, split advice and overview note for Bridgehollow", /keep a 2D scene under 5,461 ft/.test(rec[0]) && rec.some(s => /street scenes or region extracts/.test(s)) && rec.some(s => /overview only/.test(s)), rec);
check("recommend: small map gets just the limits sentence", L.recommend(300, 300, 5, 100).length === 1);

// exportplan picks the notes up as warnings
{
  const VB = require("../lib/core.js");
  ["townarea", "regions", "styles", "objects", "lighting", "sun3d", "streetlamps", "foliage", "skybox", "water", "heightpaint", "padding", "bridges", "places", "tools", "bridge", "exportplan"].forEach(f => require("../lib/" + f + ".js"));
  const X = require("../lib/exportplan.js");
  global.window = { VBLimits: L };
  const st = VB.normalize(null); st.place = "bridgehollow"; st.foundry.sceneName = "T";
  const w = X.warnings(VB, st, { connected: true, limits: L.evaluate(BH) }, true);
  delete global.window;
  check("exportplan.warnings carries the size notes into What will happen", w.some(s => /^SIZE PROBLEM: /.test(s)) && w.some(s => /overview map/.test(s)), w);
}

// CEP: window AND module exist -> still published on window
{
  const win = {}; win.window = win;
  const ctxv = vm.createContext(Object.assign(win, { module: { exports: {} }, require: require }));
  vm.runInContext(fs.readFileSync(path.join(__dirname, "..", "lib", "limits.js"), "utf8"), ctxv, { filename: "lib/limits.js" });
  check("lib/limits.js publishes window.VBLimits when module also exists (CEP)", typeof win.VBLimits === "object" && typeof win.VBLimits.evaluate === "function");
}
console.log((fail ? "FAIL" : "PASS") + " test_limits: " + ok + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
