// Skybox additions to VBCore (loaded after core.js): defaults, preset list and jobs for the Skybox tab (generate a sky from the place's terrain, apply it to the
// place's own Foundry scene, import the sky/sun of an existing scene). Pure logic, no DOM: also loaded by test/test_skybox_jobs.js.
// Python side: generators/skybox.py (generate, list, import-scene, set-flag); scene list: foundry_push.py list (read-only).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;

  // same names as skybox.py PRESETS; the mountain ring is always the place's real terrain
  VB.SKY_PRESETS = [
    { key: "clear_day", label: "Clear day", note: "blue sky, scattered cloud, sun high in the south-east" },
    { key: "overcast", label: "Overcast", note: "grey cloud deck, no sun disc, soft light" },
    { key: "dusk", label: "Dusk / sunset", note: "sun on the horizon, orange glow, first stars" },
    { key: "winter", label: "Winter (snow on the peaks)", note: "pale sky, low sun, snow cover to the valley floor" },
    { key: "night", label: "Night (moon and stars)", note: "dark sky, moon, full stars" }
  ];
  VB.skyDefaults = function () {
    return { preset: "clear_day", width: 2048, yaw: 0, viewer: "", use_lighting_sun: false, scene_uuid: "", import_scene: "", import_name: "", apply_lighting: false, dry_run: true,
      list: [], last: null, preview_png: "" };
  };
  VB.skyNum = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
  VB.skyGenerateArgs = function (st) {
    var s = st.skybox, a = ["generate", "--place", st.place, "--presets", s.preset || "clear_day", "--width", String(Math.round(VB.skyNum(s.width, 2048))), "--yaw", String(VB.skyNum(s.yaw, 0))];
    if (/^\s*-?[\d.]+\s*,\s*-?[\d.]+\s*$/.test(String(s.viewer || ""))) a.push("--viewer", String(s.viewer).replace(/\s+/g, ""));
    if (s.use_lighting_sun) a.push("--lighting", st.place);
    return a;
  };
  // lighting flags remembered from the chosen sky's import (list row), as --scene-flag key=json pairs; only when the user ticked "also apply sun / lighting"
  VB.skyLightFlagArgs = function (st) {
    var s = st.skybox, row = (s.list || []).filter(function (r) { return r.name === s.preset; })[0], a = [];
    if (!s.apply_lighting || !row || !row.lighting_flags) return a;
    Object.keys(row.lighting_flags).forEach(function (k) { a.push("--scene-flag", k + "=" + JSON.stringify(row.lighting_flags[k])); });
    return a;
  };
  VB.skyApplyArgs = function (st, dry) {
    var s = st.skybox, a = ["set-flag", "--place", st.place, "--scene-uuid", s.scene_uuid || "", "--preset", s.preset || "clear_day"].concat(VB.skyLightFlagArgs(st));
    if (!dry) a.push("--apply");
    return a;
  };
  function remember(run, key) {
    var r = run.vars[key]; if (!r) return;
    run.setState("skybox.list", r.skyboxes || []);
  }
  var listStep = function (st) { return py(GEN + "skybox.py", function () { return ["list", "--place", st.place]; }, "skybox.py list", { json: "list" }); };
  var rememberList = { t: "fn", label: "remember list", fn: function (run) { remember(run, "list"); } };
  VB.jobSkyList = function (st) { return { kind: "sky_list", label: "Read skies", params: {}, steps: [listStep(st), rememberList] }; };
  VB.jobSkyGenerate = function (st) {
    return { kind: "sky_generate", label: "Generate sky (" + st.skybox.preset + ")", params: { skybox: st.skybox },
      steps: [{ t: "fn", label: "check", fn: function () { if (!VB.SKY_PRESETS.some(function (p) { return p.key === st.skybox.preset; })) throw new Error("only the built-in presets can be regenerated; an imported sky is a fixed image"); } },
        py(GEN + "skybox.py", function () { return VB.skyGenerateArgs(st); }, "skybox.py generate", { json: "gen" }), listStep(st), rememberList,
        { t: "fn", label: "preview", fn: function (run) { var g = run.vars.gen; if (g && g.out_dir) run.setState("skybox.preview_png", g.out_dir + "/" + st.skybox.preset + "_preview.png?" + Date.now()); run.log("sky written to " + (g && g.out_dir)); } }] };
  };
  VB.jobSkyApply = function (st, opts) {
    opts = opts || {}; var s = st.skybox, dry = opts.dry !== undefined ? opts.dry : s.dry_run !== false;
    return { kind: "sky_apply", label: dry ? "Apply sky (dry run)" : "Apply sky to scene", params: { skybox: s, dry: dry },
      steps: [{ t: "fn", label: "check", fn: function () {
        if (!/^Scene\./.test(s.scene_uuid || "")) throw new Error("pick the Foundry scene to apply the sky to (or paste its Scene.xxxx uuid)");
        var row = (s.list || []).filter(function (r) { return r.name === s.preset; })[0]; if (row && !row.exists) throw new Error("the sky '" + s.preset + "' has no image yet: Regenerate it first");
      } },
        py(GEN + "skybox.py", function () { return VB.skyApplyArgs(st, dry); }, "skybox.py set-flag", { json: "apply" }),
        { t: "fn", label: "report", fn: function (run) { var r = run.vars.apply; run.setState("skybox.last", { at: new Date().toISOString(), kind: "apply", dry: !r.applied, scene: r.scene, asset: r.asset, flags: r.flags }); run.log((r.applied ? "applied to " : "dry run, would set on ") + r.scene + ": " + JSON.stringify(r.flags)); } }] };
  };
  VB.jobSkyScenes = function (st) {   // read-only list of scenes, stored in the same cache the Foundry tab uses
    return { kind: "sky_scenes", label: "Read Foundry scenes", params: {},
      steps: [py(GEN + "foundry_push.py", ["list", "--kinds", "scenes"], "foundry_push.py list (scenes)", { json: "scenes" }),
        { t: "fn", label: "store", fn: function (run) {
          var r = run.vars.scenes; if (!r || r.ok === false) throw new Error((r && r.error) || "cannot read Foundry");
          var c = (st.foundry && st.foundry.cache) || { lists: {} }; var lists = Object.assign({}, c.lists || {}, { scenes: r.lists.scenes || [] });
          run.setState("foundry.cache", { fetched: r.fetched, lists: lists }); run.log("read " + (r.lists.scenes || []).length + " scenes");
        } }] };
  };
  VB.jobSkyImport = function (st) {
    var s = st.skybox;
    return { kind: "sky_import", label: "Import sky from scene", params: { scene: s.import_scene },
      steps: [{ t: "fn", label: "check", fn: function () { if (!/^Scene\./.test(s.import_scene || "")) throw new Error("pick the Foundry scene to copy the sky from"); } },
        py(GEN + "skybox.py", function () { var a = ["import-scene", "--place", st.place, "--scene-uuid", s.import_scene]; if (String(s.import_name || "").trim()) a.push("--name", String(s.import_name).trim()); return a; }, "skybox.py import-scene (read-only)", { json: "imp" }),
        listStep(st), rememberList,
        { t: "fn", label: "select", fn: function (run) {
          var r = run.vars.imp; run.setState("skybox.preset", r.name); if (r.preview) run.setState("skybox.preview_png", r.preview + "?" + Date.now());
          run.setState("skybox.last", { at: new Date().toISOString(), kind: "import", scene: r.scene, scene_name: r.scene_name, name: r.name, how: r.how, lighting_flags: r.lighting_flags, warnings: r.warnings });
          run.log("imported '" + r.name + "' from " + r.scene_name + " (" + r.how + "); lighting flags found: " + Object.keys(r.lighting_flags || {}).join(", "));
        } }] };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.skybox = VB.skyDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
