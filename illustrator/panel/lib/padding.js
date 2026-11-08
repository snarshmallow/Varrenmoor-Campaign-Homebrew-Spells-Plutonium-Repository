// Padding additions to VBCore (loaded after core.js): defaults and jobs for the Padding tab (heightmap + apron + ground textures for the distant surroundings).
// Pure logic, no DOM: also loaded by test/test_padding_jobs.js. Python side: generators/padding_heightmap.py (foundry_push.py push-padding).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;

  VB.paddingDefaults = function () {
    return { preset: "bowl-ridge", texture: "", blend_ft: 200, taper_ft: 500, height_scale: 1, seed: 7, base_ft: "", scene_padding: "", scene_uuid: "", dry_run: true,
      apron: true, overrides: "", save_name: "", preview_png: "", last: null };
  };
  // overrides box: JSON object of preset fields ({"ridge_amp_ft": 200}) -> --set key=value pairs
  VB.paddingOverrides = function (st) {
    var t = String((st.padding || {}).overrides || "").trim();
    if (!t) return [];
    var o; try { o = JSON.parse(t); } catch (e) { throw new Error("preset overrides must be a JSON object, e.g. {\"ridge_amp_ft\": 200}: " + e.message); }
    if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error("preset overrides must be a JSON object");
    var a = []; Object.keys(o).forEach(function (k) { a.push("--set", k + "=" + JSON.stringify(o[k])); });
    return a;
  };
  VB.paddingArgs = function (st, d) {
    var p = st.padding, num = function (v, dd) { v = Number(v); return isFinite(v) ? v : dd; };
    var a = ["--place", st.place, "--preset", p.preset || "bowl-ridge", "--blend", String(num(p.blend_ft, 200)), "--taper", String(num(p.taper_ft, 500)),
      "--seed", String(Math.round(num(p.seed, 7))), "--height-scale", String(num(p.height_scale, 1))];
    if (p.texture) a.push("--texture", p.texture);
    if (String(p.base_ft).trim() !== "" && isFinite(Number(p.base_ft))) a.push("--base", String(Number(p.base_ft)));
    if (p.apron === false) a.push("--no-apron");
    return a.concat(VB.paddingOverrides(st), ["--out", d.world + "/export/padding"]);
  };
  function remember(run, key) {
    var r = run.vars[key]; if (!r) return;
    run.setState("padding.last", { at: new Date().toISOString(), scale: r.tableHeightmapScale, base_level_ft: r.base_level_ft, pixel255_ft: r.pixel255_ft, quant_ft: r.quantisation_ft, heightmap_used: r.heightmap_used, seam: r.seam, out_dir: r.out_dir });
    if (r.files && r.files.preview) run.setState("padding.preview_png", r.files.preview + "?" + Date.now());
    var s = r.seam || {};
    run.log("tableHeightmapScale " + r.tableHeightmapScale + ", base " + Number(r.base_level_ft).toFixed(1) + " ft, 8-bit step " + Number(r.quantisation_ft).toFixed(2) + " ft; seam step terrain " + (s.max_step_terrain_edge_m != null ? s.max_step_terrain_edge_m.toFixed(3) : "-") + " m, table " + (s.max_step_table_m != null ? s.max_step_table_m.toFixed(3) : "-") + " m");
  }
  VB.jobPaddingGenerate = function (st, d) {
    return { kind: "padding_generate", label: "Generate padding (" + st.padding.preset + ")", params: { padding: st.padding },
      steps: [{ t: "fn", label: "check", fn: function () { VB.paddingOverrides(st); } },
        py(GEN + "padding_heightmap.py", function () { return ["generate"].concat(VB.paddingArgs(st, d)); }, "padding_heightmap.py generate", { json: "gen" }),
        { t: "fn", label: "remember", fn: function (run) { remember(run, "gen"); } }] };
  };
  VB.jobPaddingPush = function (st, d, opts) {
    opts = opts || {}; var p = st.padding, dry = opts.dry !== undefined ? opts.dry : p.dry_run !== false;
    var args = function () {
      var a = ["push-padding"].concat(VB.paddingArgs(st, d), ["--scene-uuid", p.scene_uuid || ""]);
      if (String(p.scene_padding).trim() !== "" && isFinite(Number(p.scene_padding))) a.push("--scene-padding", String(Number(p.scene_padding)));
      if (dry) a.push("--dry-run");
      return a;
    };
    return { kind: "padding_push", label: dry ? "Push padding (dry run)" : "Push padding to Foundry", params: { padding: p, dry: dry },
      steps: [{ t: "fn", label: "check scene", fn: function () { if (!/^Scene\./.test(p.scene_uuid || "")) throw new Error("pick a Foundry scene (or paste its Scene.xxxx uuid) first"); } },
        py(GEN + "foundry_push.py", args, "foundry_push.py push-padding", { json: "push" }),
        { t: "fn", label: "report", fn: function (run) {
          var r = run.vars.push; remember(run, "push"); var pl = (r && r.push) || {};
          run.setState("padding.push_report", { dry: !!pl.dry_run, scene: pl.scene, assets: pl.assets, flags: pl.flags && pl.flags["levels-3d-preview"], level_bottom_ft: pl.level_elevation_bottom_ft });
          run.log((pl.dry_run ? "dry run: would publish " : "published ") + Object.keys(pl.assets || {}).map(function (k) { return pl.assets[k]; }).join(", "));
        } }] };
  };
  VB.jobPaddingSavePreset = function (st) {
    var p = st.padding;
    return { kind: "padding_save_preset", label: "Save padding preset", params: { name: p.save_name },
      steps: [{ t: "fn", label: "check", fn: function () { if (!String(p.save_name || "").trim()) throw new Error("type a name for the preset"); VB.paddingOverrides(st); } },
        py(GEN + "padding_heightmap.py", function () { return ["save-preset", "--from", p.preset || "bowl-ridge", "--name", String(p.save_name).trim()].concat(VB.paddingOverrides(st)); }, "padding_heightmap.py save-preset", { json: "saved" }),
        { t: "fn", label: "log", fn: function (run) { run.log("saved " + run.vars.saved.saved); run.setState("padding.preset", String(p.save_name).trim()); } }] };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.padding = VB.paddingDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
