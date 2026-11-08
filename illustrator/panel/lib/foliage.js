// Foliage additions to VBCore (loaded after core.js): defaults, mixes, scatter / clear / add / draw / preview / merge jobs.
// Pure logic, no DOM: also loaded by test/test_foliage_jobs.js. Python side: generators/foliage.py (world/<place>/foliage.json).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var LAYER = "DETAILS - Foliage";
  VB.FOLIAGE_LAYER = LAYER;

  VB.foliageDefaults = function () {
    return {
      mix: [{ species: "spruce", weight: 3 }, { species: "scots_pine", weight: 3 }, { species: "birch", weight: 2 }, { species: "fern", weight: 2 }, { species: "grass", weight: 2 }],
      mix_preset: "northern_mixed_forest", density_per_ha: 200, size_var: 0.5, seed: 1, pattern: "uniform", zone: "z1",
      cluster_radius_ft: 45, cluster_size: 12, edge_ft: 40, row_spacing_ft: 0, row_angle_deg: 0, line_spacing_ft: 0,
      avoid_buildings: true, avoid_roads: true, avoid_water: true, slope_max_deg: 38, elev_min_ft: "", elev_max_ft: "", moisture_bias: 0,
      target: "lasso", district: "", polygon: [], polygon_src: "", path: [], path_src: "", single_species: "birch",
      clear_hand: false, clear_zone: "", draw: true, stats: null, preview_png: "",
      merge: { chunk_ft: 150, budget: 0, impostor_beyond_ft: 0, lod1_beyond_ft: 0, compress: "none", preset: "balanced", scene_uuid: "", out_dir: "", report: null }
    };
  };
  VB.FOLIAGE_PATTERNS = [["uniform", "Uniform (random, spaced)"], ["cluster", "Clusters / groves"], ["forest_edge", "Forest edge (denser at the border)"],
    ["orchard", "Orchard rows"], ["tree_line", "Tree line along a path"], ["hedge_line", "Hedge along a path"]];
  VB.FOLIAGE_MERGE_PRESETS = {
    balanced: { label: "Balanced (150 ft chunks, LOD files)", chunk_ft: 150, budget: 0, impostor_beyond_ft: 0, lod1_beyond_ft: 0, compress: "none" },
    performance: { label: "Performance (200 ft chunks, 150k tri cap, impostors past 600 ft)", chunk_ft: 200, budget: 150000, impostor_beyond_ft: 600, lod1_beyond_ft: 300, compress: "quant" },
    lowend: { label: "Low-end GPU (250 ft chunks, 60k tri cap, impostors past 300 ft)", chunk_ft: 250, budget: 60000, impostor_beyond_ft: 300, lod1_beyond_ft: 150, compress: "quant" },
    quality: { label: "Quality (100 ft chunks, no cap, uncompressed)", chunk_ft: 100, budget: 0, impostor_beyond_ft: 0, lod1_beyond_ft: 0, compress: "none" }
  };
  VB.foliageApplyMergePreset = function (st, key) {
    var p = VB.FOLIAGE_MERGE_PRESETS[key]; if (!p) return st;
    var m = st.foliage.merge; ["chunk_ft", "budget", "impostor_beyond_ft", "lod1_beyond_ft", "compress"].forEach(function (k) { m[k] = p[k]; }); m.preset = key; return st;
  };
  var num = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
  var opt = function (v) { return v === "" || v === null || v === undefined || !isFinite(Number(v)) ? null : Number(v); };

  // request for foliage.py scatter (everything the python rules read). polygon/path are filled by the job from the chosen target.
  VB.foliageParams = function (st) {
    var f = st.foliage;
    return {
      zone: String(f.zone || "z1").toLowerCase().replace(/[^a-z0-9_]+/g, "_") || "z1",
      mix: (f.mix || []).filter(function (m) { return m.weight > 0 && m.species; }).map(function (m) { return { species: m.species, weight: num(m.weight, 1) }; }),
      density_per_ha: num(f.density_per_ha, 200), size_var: num(f.size_var, 0.5), seed: Math.round(num(f.seed, 1)), pattern: f.pattern || "uniform",
      cluster_radius_ft: num(f.cluster_radius_ft, 45), cluster_size: num(f.cluster_size, 12), edge_ft: num(f.edge_ft, 40), row_spacing_ft: num(f.row_spacing_ft, 0), row_angle_deg: num(f.row_angle_deg, 0),
      line_spacing_ft: num(f.line_spacing_ft, 0), avoid_buildings: f.avoid_buildings !== false, avoid_roads: f.avoid_roads !== false, avoid_water: f.avoid_water !== false,
      slope_max_deg: num(f.slope_max_deg, 38), elev_min_ft: opt(f.elev_min_ft), elev_max_ft: opt(f.elev_max_ft), moisture_bias: num(f.moisture_bias, 0)
    };
  };
  VB.foliageIsLine = function (st) { return st.foliage.pattern === "tree_line" || st.foliage.pattern === "hedge_line"; };

  // count / triangle estimate from the preset table lib {species: {tris: [lod0, lod1, lod2]}} for an area in hectares
  VB.foliageEstimate = function (st, lib, areaHa) {
    var f = st.foliage, mix = f.mix.filter(function (m) { return m.weight > 0; }), ws = mix.reduce(function (s, m) { return s + m.weight; }, 0) || 1;
    var n = Math.round(num(f.density_per_ha, 0) * areaHa), tris = 0, per = {};
    mix.forEach(function (m) { var c = Math.round(n * m.weight / ws), t = ((lib[m.species] || {}).tris || [0])[0]; per[m.species] = c; tris += c * t; });
    return { count: n, triangles: tris, per_species: per };
  };

  VB.foliageViewArgs = function (st) { return ["--view", st.settings.view || "town", "--preset", st.scale.preset, "--scale", String(st.scale.scale_ft_per_in), "--page", st.scale.page_w_in + "x" + st.scale.page_h_in]; };
  var py = VB.steps.py;
  var drawSteps = function (st, d) {
    var dir = d.panel + "/foliage";
    return [py(GEN + "foliage.py", ["draw", "--place", st.place].concat(VB.foliageViewArgs(st), ["--out-dir", dir]), "foliage symbols (2D)", { json: "draw" })]
      .concat(VB.replaceSteps(dir + "/foliage.svg", [LAYER], "draw DETAILS - Foliage layer"));
  };
  // resolve the area of a scatter / clear: lasso (captured polygon) | district | place | town (Town tab area) | path (open path)
  var areaStep = function (st, d, file, needLine) {
    return { t: "fn", label: "resolve area", fn: function (run) {
      var f = st.foliage, out = {};
      if (needLine) {
        if (!f.path || f.path.length < 2) throw new Error("no path: select an open path and press Capture path");
        out.path = f.path;
      } else if (f.target === "lasso") {
        if (!f.polygon || f.polygon.length < 3) throw new Error("no area: select a closed path and press Capture area");
        out.polygon = f.polygon;
      } else if (f.target === "town") {
        if (!st.town.area || st.town.area.length < 3) throw new Error("the Town tab has no area polygon");
        out.polygon = st.town.area;
      } else if (f.target === "district") {
        var ds = run.readJson(d.world + "/districts.json", { districts: [] }).districts || [], e = ds.filter(function (x) { return x.id === f.district; })[0];
        if (!e || !e.geometry || !e.geometry.points) throw new Error("pick a district with a polygon");
        out.polygon = e.geometry.points;
      } else {
        var b = run.readJson(d.world + "/place.json", {}).bounds || {}, w = b.width_ft || 1000, h = b.height_ft || 1000;
        out.polygon = [[0, 0], [w, 0], [w, h], [0, h]];
      }
      run.writeJson(file, out); run.log("area: " + (out.polygon ? out.polygon.length + "-point polygon" : out.path.length + "-point path"));
    } };
  };

  VB.jobFoliageScatter = function (st, d) {
    var pf = d.panel + "/foliage_params.json", f = st.foliage, line = VB.foliageIsLine(st), area = d.panel + "/foliage_area.json";
    return { kind: "foliage_scatter", label: "Scatter foliage (" + (f.zone || "z1") + ")", params: { foliage: f },
      steps: [
        { t: "fn", label: "check mix", fn: function () { if (!VB.foliageParams(st).mix.length) throw new Error("pick at least one species"); } },
        areaStep(st, d, area, line),
        { t: "fn", label: "write params", fn: function (run) { var a = run.readJson(area), p = VB.foliageParams(st); if (a.polygon) p.polygon = a.polygon; if (a.path) p.path = a.path; run.writeJson(pf, p); } },
        py(GEN + "foliage.py", ["scatter", "--place", st.place, "--params", pf].concat(VB.srcFlags(st)), "foliage.py scatter", { json: "scatter" }),
        { t: "fn", label: "remember stats", fn: function (run) { var r = run.vars.scatter; run.setState("foliage.stats", r.stats); run.log("zone " + r.zone + ": +" + r.added + " (replaced " + r.replaced + "), total " + r.total_items + ", " + r.stats.triangles + " triangles unmerged"); } }
      ].concat(f.draw ? drawSteps(st, d) : []) };
  };
  VB.jobFoliageClear = function (st, d) {
    var area = d.panel + "/foliage_area.json", f = st.foliage, pf = d.panel + "/foliage_clear_poly.json";
    return { kind: "foliage_clear", label: "Clear foliage in area", params: { foliage: f },
      steps: [areaStep(st, d, area, false),
        { t: "fn", label: "write polygon", fn: function (run) { run.writeJson(pf, run.readJson(area).polygon); } },
        py(GEN + "foliage.py", ["clear", "--place", st.place, "--polygon", pf].concat(f.clear_hand ? ["--all"] : [], f.clear_zone ? ["--zone", f.clear_zone] : []), "foliage.py clear", { json: "clear" }),
        { t: "fn", label: "log", fn: function (run) { run.log("removed " + run.vars.clear.removed + ", " + run.vars.clear.total_items + " left"); } }
      ].concat(drawSteps(st, d)) };
  };
  VB.jobFoliageAdd = function (st, d) {
    return { kind: "foliage_add", label: "Add " + st.foliage.single_species + " at selection", params: { species: st.foliage.single_species },
      steps: [py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        VB.steps.host({ action: "get_selection" }, "read selection"),
        { t: "fn", label: "position (ft)", fn: function (run) { run.vars.pt = VB.pickPointFt(run.vars.view, run.last); } },
        py(GEN + "foliage.py", function (run) { return ["add", "--place", st.place, "--species", st.foliage.single_species, "--x", String(run.vars.pt[0]), "--y", String(run.vars.pt[1])]; }, "foliage.py add", { json: "added" }),
        { t: "fn", label: "log", fn: function (run) { run.log("added " + run.vars.added.added.id + " at " + run.vars.pt.join(", ") + " ft"); } }
      ].concat(drawSteps(st, d)) };
  };
  VB.jobFoliageDraw = function (st, d) { return { kind: "foliage_draw", label: "Draw foliage symbols", params: {}, steps: drawSteps(st, d) }; };
  VB.jobFoliageStats = function (st) {
    return { kind: "foliage_stats", label: "Foliage counts", params: {}, steps: [py(GEN + "foliage.py", ["stats", "--place", st.place], "foliage.py stats", { json: "stats" }),
      { t: "fn", label: "remember", fn: function (run) { run.setState("foliage.stats", run.vars.stats); } }] };
  };
  VB.jobFoliagePreview = function (st, d) {
    var png = d.panel + "/foliage_preview.png";
    return { kind: "foliage_preview", label: "Preview foliage", params: {}, steps: [py(GEN + "foliage.py", ["preview", "--place", st.place, "--out", png].concat(VB.srcFlags(st)), "foliage.py preview", { json: "pv" }),
      { t: "fn", label: "remember", fn: function (run) { run.setState("foliage.preview_png", run.vars.pv.png + "?" + Date.now()); } }] };
  };
  VB.foliageMergeArgs = function (st) {
    var m = st.foliage.merge, a = ["--chunk-ft", String(num(m.chunk_ft, 150)), "--compress", m.compress || "none"];
    if (num(m.budget, 0) > 0) a.push("--budget", String(Math.round(num(m.budget, 0))));
    if (num(m.impostor_beyond_ft, 0) > 0) a.push("--impostor-beyond-ft", String(num(m.impostor_beyond_ft, 0)));
    if (num(m.lod1_beyond_ft, 0) > 0) a.push("--lod1-beyond-ft", String(num(m.lod1_beyond_ft, 0)));
    if (m.out_dir) a.push("--out-dir", m.out_dir);
    return a;
  };
  // merge (and optionally publish to a Foundry scene). opts {publish, dry}
  VB.jobFoliageMerge = function (st, d, opts) {
    opts = opts || {}; var m = st.foliage.merge;
    var args = [opts.publish ? "publish" : "merge", "--place", st.place].concat(VB.foliageMergeArgs(st));
    if (opts.publish) { args.push("--scene-uuid", m.scene_uuid); if (opts.dry) args.push("--dry-run"); else args.push("--yes"); }
    return { kind: opts.publish ? "foliage_publish" : "foliage_merge", label: opts.publish ? (opts.dry ? "Publish foliage (dry run)" : "Publish merged foliage to Foundry") : "Merge foliage for performance", params: { merge: m },
      steps: [{ t: "fn", label: "check", fn: function () { if (opts.publish && !/^Scene\./.test(m.scene_uuid || "")) throw new Error("set the Foundry scene uuid (Scene.xxxx) first"); } },
        py(GEN + "foliage.py", args, "foliage.py " + args[0], { json: "merge" }),
        { t: "fn", label: "remember report", fn: function (run) { var r = run.vars.merge; if (r && r.before) { run.setState("foliage.merge.report", { before: r.before, after: r.after, out: r.out }); run.log("draw calls " + r.before.draw_calls + " -> " + r.after.draw_calls + ", triangles " + r.before.triangles + " -> " + r.after.triangles + ", chunks " + r.chunks); } } }] };
  };

  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.foliage = VB.foliageDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
