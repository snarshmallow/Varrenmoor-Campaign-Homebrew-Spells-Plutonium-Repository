// Tools tab additions to VBCore (loaded after core.js): audits with a results viewer, texture baking, delete scene (typed-name confirm), one-shot 3D scene push,
// and the "advanced option" fields that complete the CLI parity of the Foundry tab (push-scene / push-models / push-lights / set-collision / push-walls / worldpack
// export, split, merge / import-scene / push-token). Pure logic, no DOM: also loaded by test/test_tools_jobs.js.
// Every CLI command and flag is listed in lib/command_manifest.json with the control that covers it; test/test_command_parity.js fails when one is missing.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;

  VB.toolsDefaults = function () {
    return {
      audits: { bga_top: 12, bga_nomesh: false, rha_step: 4, rha_mesh: "", rha_smooth: "", rha_maxgrade: "", rha_cutfill: false, tc_minor: 10, tc_index: 50, ta_tag: "current", ta_padding: false, ta_raw: false },
      bake: { image: "", window: "", crop_margin_pt: "", dpi: "", px_per_ft: "", name: "", format: "webp", out_dir: "", table_texture_path: "", publish: false },
      del: { typed: "" },
      s3d: { skybox_preset: "clear_day", no_skybox: false, no_padding: false, use_padding_tab: true, padding_arg: "", with_lights: true, prune_lights: false, foliage_placements: "", lights_placements: "", layers: "", lod: 0, dry_run: true },
      scene: { upscale: 1, padding: 0, max_px: 8192, format: "webp", link: false },
      push: { ids: "", serve_url: "", assets_dir: "", px_per_ft: "", set_name: "", table_texture: "", scene_flags: "", lighting: "", collision_lod: "", yes: false },
      lights: { animation: "", lighting: "", prune: false, placements: "" },
      walls: { profile: "", foliage_json: "" },
      exp: { terrain_source: "", lod: "", style: "", phases: "", px_per_ft: "", z_origin_ft: "", timestamp: "", splat_cell_ft: "", albedo_px_per_ft: "", no_textures: false, textures: "", step: "", no_hidden_removal: false, reexport_ids: "" },
      imp: { no_image: false, force: false, scene_json: "" },
      tok: { hidden: false, key: "", px: "", portrait: "", token: "" },
      pad: { tex_px: "", no_level: false },
      objdry: false,
      out: { label: "", at: "", ok: true, text: "" }
    };
  };
  var T = function (st) { return (st && st.tools) || VB.toolsDefaults(); };
  var has = function (v) { return String(v === undefined || v === null ? "" : v).trim() !== ""; };
  var num = function (v, dd) { v = Number(v); return isFinite(v) && has(v) ? v : dd; };
  var lines = function (s) { return String(s || "").split(/\r?\n/).map(function (x) { return x.trim(); }).filter(Boolean); };

  // Extra command-line arguments of the Tools tab for one command (defaults add nothing, so existing jobs stay byte-identical).
  VB.extraArgs = function (st, cmd) {
    var t = T(st), a = [], x;
    if (cmd === "push-scene") {
      x = t.scene;
      if (num(x.upscale, 1) !== 1) a.push("--upscale", String(num(x.upscale, 1)));
      if (num(x.padding, 0) !== 0) a.push("--padding", String(num(x.padding, 0)));
      if (num(x.max_px, 8192) !== 8192) a.push("--max-px", String(Math.round(num(x.max_px, 8192))));
      if (x.format === "png") a.push("--format", "png");
      if (x.link) a.push("--link");
    } else if (cmd === "push-models") {
      x = t.push;
      if (has(x.ids)) a.push("--ids", x.ids.trim());
      if (has(x.serve_url)) a.push("--serve-url", x.serve_url.trim());
      if (has(x.assets_dir)) a.push("--assets-dir", x.assets_dir.trim());
      if (has(x.px_per_ft)) a.push("--px-per-ft", String(num(x.px_per_ft, 20)));
      if (has(x.set_name)) a.push("--set-name", x.set_name.trim());
      if (has(x.table_texture)) a.push("--table-texture", x.table_texture.trim());
      lines(x.scene_flags).forEach(function (l) { a.push("--scene-flag", l); });
      if (has(x.lighting)) a.push("--lighting", x.lighting.trim());
      if (has(x.collision_lod)) a.push("--collision-lod", x.collision_lod.trim());
      if (x.yes) a.push("--yes");
    } else if (cmd === "publish") {
      if (t.push.yes) a.push("--yes");
    } else if (cmd === "push-lights") {
      x = t.lights;
      if (has(x.animation)) a.push("--light-animation", x.animation.trim());
      if (has(x.lighting)) a.push("--lighting", x.lighting.trim());
      if (x.prune) a.push("--prune-lights");
      if (has(x.placements)) a.push("--lights-placements", x.placements.trim());
    } else if (cmd === "set-collision") {
      if (has(t.push.collision_lod)) a.push("--collision-lod", t.push.collision_lod.trim());
    } else if (cmd === "push-walls") {
      lines(t.walls.profile).forEach(function (l) { a.push("--wall-profile", l); });
      if (has(t.walls.foliage_json)) a.push("--foliage-json", t.walls.foliage_json.trim());
    } else if (cmd === "worldpack-export") {
      x = t.exp;
      if (x.terrain_source) a.push("--terrain-source", x.terrain_source);
      if (has(x.lod)) a.push("--lod", x.lod.trim());
      if (has(x.style)) a.push("--style", x.style.trim());
      if (has(x.phases)) a.push("--phases", x.phases.trim());
      if (has(x.px_per_ft)) a.push("--px-per-ft", String(num(x.px_per_ft, 20)));
      if (has(x.z_origin_ft)) a.push("--z-origin-ft", String(num(x.z_origin_ft, 0)));
      if (has(x.timestamp)) a.push("--timestamp", x.timestamp.trim());
      if (has(x.splat_cell_ft)) a.push("--splat-cell-ft", String(num(x.splat_cell_ft, 0)));
      if (has(x.albedo_px_per_ft)) a.push("--albedo-px-per-ft", String(num(x.albedo_px_per_ft, 0)));
      if (x.no_textures) a.push("--no-textures");
    } else if (cmd === "worldpack-split") {
      x = t.exp;
      if (x.textures) a.push("--textures", x.textures);
      if (has(x.step) && num(x.step, 1) !== 1) a.push("--step", String(Math.max(1, Math.round(num(x.step, 1)))));
    } else if (cmd === "worldpack-merge") {
      if (t.exp.no_hidden_removal) a.push("--no-hidden-removal");
    } else if (cmd === "import-scene") {
      x = t.imp;
      if (x.no_image) a.push("--no-image");
      if (x.force) a.push("--force");
      if (has(x.scene_json)) a.push("--scene-json", x.scene_json.trim());
    } else if (cmd === "push-actor") {
      x = t.tok;
      if (has(x.portrait)) a.push("--portrait", x.portrait.trim());
      if (has(x.token)) a.push("--token", x.token.trim());
    } else if (cmd === "object-edit") {
      if (t.objdry) a.push("--dry");
    } else if (cmd === "push-token") {
      x = t.tok;
      if (x.hidden) a.push("--hidden");
      if (has(x.key)) a.push("--key", x.key.trim());
      if (has(x.px)) a.push("--px", x.px.trim());
    }
    return a;
  };

  // Results viewer: last run's text (stdout of the tool) kept in state tools.out and shown in the Tools tab.
  function reportStep(label) {
    return { t: "fn", label: "show result", fn: function (run) {
      var txt = String(run.lastOut || "").trim();
      if (txt.length > 9000) txt = "... (first part cut)\n" + txt.slice(-9000);
      if (/^\s*[{[]/.test(txt)) { try { txt = JSON.stringify(JSON.parse(txt.split(/\r?\n/).filter(function (l) { return /^\s*[{[]/.test(l); }).pop() || txt), null, 1); } catch (e) { /* keep raw */ } }
      run.setState("tools.out", { label: label, at: new Date().toISOString(), ok: true, text: txt || "(no output)" });
      run.log(label + ": " + (txt.split(/\r?\n/)[0] || "done"));
    } };
  }
  function sceneOf(st) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene on the Foundry tab (Refresh from Foundry first)");
    return f.sceneUuid;
  }
  function audit(kind, label, script, argsFn) {
    return { kind: kind, label: label, params: {}, steps: [py(GEN + script, argsFn, label), reportStep(label)] };
  }

  // ---- audits (read-only)
  VB.jobToolsBuildingGround = function (st, d) {
    var a = T(st).audits;
    return audit("tools_building_ground", "Building ground audit", "building_ground_audit.py", function () {
      var x = ["--place", st.place, "--pack", VB.packDir(d), "--top", String(Math.max(1, Math.round(num(a.bga_top, 12))))]; if (a.bga_nomesh) x.push("--no-mesh"); return x; });
  };
  VB.jobToolsRoadHeight = function (st, d) {
    var a = T(st).audits;
    return audit("tools_road_height", "Road height audit", "road_height_audit.py", function () {
      var x = ["--place", st.place, "--pack", VB.packDir(d), "--step-ft", String(num(a.rha_step, 4))];
      if (a.rha_mesh === "legacy" || a.rha_mesh === "graded") x.push("--mesh", a.rha_mesh);
      if (has(a.rha_smooth)) x.push("--smooth", String(num(a.rha_smooth, 0.5)));
      if (has(a.rha_maxgrade)) x.push("--max-grade", String(num(a.rha_maxgrade, 14)));
      if (a.rha_cutfill) x.push("--cutfill");
      return x; });
  };
  VB.jobToolsTerrainCheck = function (st) {
    var a = T(st).audits;
    return audit("tools_terrain_check", "Terrain check", "terrain_check.py", function () { return ["--place", st.place, "--minor", String(num(a.tc_minor, 10)), "--index", String(num(a.tc_index, 50))]; });
  };
  VB.jobToolsTexturesAudit = function (st) {
    var a = T(st).audits;
    return audit("tools_textures_audit", "Textures audit", "textures_audit.py", function () {
      var x = ["--tag", String(a.ta_tag || "current").trim() || "current"]; if (a.ta_padding) x.push("--padding"); if (a.ta_raw) x.push("--raw"); return x; });
  };
  VB.jobToolsPackValidate = function (st, d) { return audit("tools_pack_validate", "Validate world pack", "worldpack.py", function () { return ["validate", "--place", st.place, "--path", VB.packDir(d)]; }); };
  VB.jobToolsPackInfo = function (st, d) { return audit("tools_pack_info", "World pack summary", "worldpack.py", function () { return ["info", "--place", st.place, "--path", VB.packDir(d)]; }); };
  VB.jobToolsSplitInfo = function (st, d) { return audit("tools_split_info", "Split pack summary", "worldpack_split.py", function () { return ["info", "--place", st.place, "--pack", VB.packDir(d)]; }); };
  VB.jobToolsSceneAudit = function (st, d) {
    var u = sceneOf(st);
    return { kind: "tools_scene_audit", label: "Audit scene tiles (read-only)", params: {}, steps: [py(VB.FOUNDRY_PY, ["scene-audit", "--scene-uuid", u, "--placements", VB.packDir(d) + "/placements.json"], "scene audit"), reportStep("Scene tile audit")] };
  };
  VB.jobToolsFoundryRead = function (st, cmd) {   // places / export-info / list: read-only, shown in the viewer
    var a = [cmd, "--place", st.place]; if (cmd === "export-info") a.push.apply(a, VB.viewFlags ? VB.viewFlags(st) : []);
    return { kind: "tools_" + cmd, label: "foundry_push " + cmd, params: {}, steps: [py(VB.FOUNDRY_PY, a, "foundry_push " + cmd), reportStep("foundry_push " + cmd)] };
  };
  VB.jobToolsObjectList = function (st, sub) {   // object_edit.py list-buildings | list-roads | choices (read-only)
    return { kind: "tools_object_" + sub, label: "object_edit " + sub, params: {}, steps: [py(GEN + "object_edit.py", [sub, "--place", st.place], "object_edit " + sub), reportStep("object_edit " + sub)] };
  };
  VB.jobToolsReexport = function (st, d) {
    var ids = String(T(st).exp.reexport_ids || "").trim();
    return { kind: "tools_reexport", label: "Re-export entities", params: { ids: ids }, steps: [{ t: "fn", label: "check", fn: function () { if (!ids) throw new Error("type the entity id(s) first (comma separated)"); } },
      py(GEN + "worldpack_split.py", ["reexport", "--place", st.place, "--pack", VB.packDir(d), "--id", ids], "worldpack_split reexport"), reportStep("Re-export " + ids)] };
  };

  // ---- texture baking (offline; --publish copies into the shared assets folder Foundry serves)
  VB.bakeArgs = function (st, d, publish) {
    var b = T(st).bake, a = ["bake-texture", "--place", st.place];
    if (!has(b.image)) throw new Error("give the rendered map image (png)");
    if (!has(b.window) && !has(b.px_per_ft)) throw new Error("give the map window (x0,y0,x1,y1 ft: 'Fill from view') or pixels per foot");
    if (has(b.window) && !/^\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*,\s*-?[\d.]+\s*$/.test(b.window)) throw new Error("window must be four numbers x0,y0,x1,y1 in feet");
    a.push("--image", b.image.trim());
    if (has(b.window)) a.push("--window", b.window.replace(/\s+/g, ""));
    else a.push("--px-per-ft", String(num(b.px_per_ft, 20)));
    if (has(b.crop_margin_pt)) { a.push("--crop-margin-pt", String(num(b.crop_margin_pt, 0))); if (has(b.dpi)) a.push("--dpi", String(num(b.dpi, 72))); else throw new Error("cropping a paper margin needs the image dpi"); }
    if (has(b.name)) a.push("--name", b.name.trim());
    if (b.format === "png") a.push("--format", "png");
    a.push("--out-dir", has(b.out_dir) ? b.out_dir.trim() : d.world + "/export/baked");
    if (has(b.table_texture_path)) a.push("--table-texture-path", b.table_texture_path.trim());
    if (publish) a.push("--publish");
    return a;
  };
  VB.jobToolsBake = function (st, d, publish) {
    var a = VB.bakeArgs(st, d, publish);
    return { kind: "tools_bake", label: "Bake ground texture" + (publish ? " + publish" : " (local files only)"), params: { publish: !!publish }, steps: [py(VB.FOUNDRY_PY, a, "bake-texture"), reportStep("Bake texture")] };
  };
  // fills the Window box from export-info of the current view: window_ft is [x0, y0, width, height]
  VB.windowFromInfo = function (r) { var w = r && r.window_ft; return w && w.length === 4 ? [w[0], w[1], w[0] + w[2], w[1] + w[3]].map(function (v) { return Math.round(v * 100) / 100; }).join(",") : ""; };

  VB.jobToolsBakeWindow = function (st, d) {
    return { kind: "tools_bake_window", label: "Window of the current view", params: {},
      steps: [py(VB.FOUNDRY_PY, ["export-info", "--place", st.place].concat(VB.viewFlags ? VB.viewFlags(st) : []), "export-info", { json: "info" }),
        { t: "fn", label: "fill window", fn: function (run) {
          var w = VB.windowFromInfo(run.vars.info); if (!w) throw new Error("export-info gave no window");
          run.setState("tools.bake.window", w); run.setState("tools.bake.image", VB.foundryOut(d, "view_export.png"));
          run.log("window " + w + " ft; image = the last exported view (Foundry tab: Export view first if it is old)");
        } }] };
  };

  // ---- delete scene: only the picked existing scene, only after its exact name was typed
  VB.deleteSceneRow = function (st) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) return null;
    return (((f.cache || {}).lists || {}).scenes || []).filter(function (r) { return r.uuid === f.sceneUuid; })[0] || { uuid: f.sceneUuid, name: "" };
  };
  VB.deleteSceneOk = function (st) { var r = VB.deleteSceneRow(st); return !!(r && r.name && String(T(st).del.typed) === String(r.name)); };
  VB.jobToolsDeleteScene = function (st) {
    var r = VB.deleteSceneRow(st);
    if (!r) throw new Error("pick an existing scene on the Foundry tab first");
    if (!VB.deleteSceneOk(st)) throw new Error("type the scene name exactly (" + (r.name || r.uuid) + ") to confirm the deletion");
    return { kind: "tools_delete_scene", label: "Delete scene " + r.name, params: { uuid: r.uuid },
      steps: [py(VB.FOUNDRY_PY, ["delete-scene", "--scene-uuid", r.uuid], "delete-scene"),
        { t: "fn", label: "forget scene", fn: function (run) {
          var L = (((st.foundry.cache || {}).lists || {}).scenes || []).filter(function (x) { return x.uuid !== r.uuid; });
          run.setState("foundry.cache.lists.scenes", L); run.setState("foundry.sceneUuid", ""); run.setState("tools.del.typed", "");
          run.setState("tools.out", { label: "Delete scene", at: new Date().toISOString(), ok: true, text: "Deleted scene " + r.name + " (" + r.uuid + ") from Foundry. Cannot be undone." });
          run.log("deleted " + r.uuid);
        } }] };
  };

  // ---- one-shot 3D scene (push-scene-3d): models, optional foliage, padding, skybox, lights, collision in one go
  VB.paddingPushTokens = function (st, d) {   // the Padding tab settings as push-padding arguments without --place / --out
    if (!VB.paddingArgs) return [];
    var a = VB.paddingArgs(st, d), out = [], i; for (i = 0; i < a.length; i++) { if (a[i] === "--place" || a[i] === "--out") { i++; continue; } out.push(a[i]); }
    return out;
  };
  VB.scene3dArgs = function (st, d, dry) {
    var s = T(st).s3d, a = ["push-scene-3d", "--place", st.place, "--scene-uuid", sceneOf(st), "--placements", VB.packDir(d) + "/placements.json"];
    if (has(s.layers)) a.push("--layers", s.layers.trim());
    if (+s.lod) a.push("--lod", String(+s.lod));
    if (s.no_skybox) a.push("--no-skybox"); else if (has(s.skybox_preset) && s.skybox_preset !== "clear_day") a.push("--skybox-preset", s.skybox_preset.trim());
    if (s.no_padding) a.push("--no-padding");
    else {
      var tok = (s.use_padding_tab ? VB.paddingPushTokens(st, d) : []).concat(lines(s.padding_arg).join(" ").split(/\s+/).filter(Boolean));
      tok.forEach(function (x) { a.push("--padding-arg=" + x); });
    }
    if (s.with_lights) a.push("--with-lights");
    if (s.prune_lights) a.push("--prune-lights");
    if (has(s.foliage_placements)) a.push("--foliage-placements", s.foliage_placements.trim());
    if (has(s.lights_placements)) a.push("--lights-placements", s.lights_placements.trim());
    var cs = VB.collisionSpec(st.foundry.models); if (cs) a.push("--collision", cs);
    var m = st.foundry.models; if (m.prune) a.push("--prune");
    if (m.roofsHidden && VB.roofMode(st) !== "none") a.push("--roofs-hidden");
    var p = T(st).push;   // only the push options that make sense for the whole scene
    if (has(p.serve_url)) a.push("--serve-url", p.serve_url.trim());
    if (has(p.assets_dir)) a.push("--assets-dir", p.assets_dir.trim());
    if (has(p.lighting)) a.push("--lighting", p.lighting.trim());
    if (p.yes) a.push("--yes");
    if (dry) a.push("--dry-run");
    return a;
  };
  VB.jobToolsScene3d = function (st, d, dry) {
    var a = VB.scene3dArgs(st, d, dry);
    return { kind: "tools_scene3d", label: "Push 3D scene" + (dry ? " (dry run)" : ""), params: { dry: !!dry }, steps: [py(VB.FOUNDRY_PY, a, "push-scene-3d"), reportStep("Push 3D scene" + (dry ? " (dry run)" : ""))] };
  };

  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.tools = VB.toolsDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
