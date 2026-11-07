// Regions tab pieces for VBCore (loaded after core.js): defaults, scale presets, command lines and the jobs that make a zoom-in child map of
// a district. Pure logic, no DOM: also loaded by test/run_mock.js. Python side: generators/region_extract.py, region_render.py, foundry_push.py.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py, host = VB.steps.host;
  var REGION_LAYER = "REGIONS";
  VB.REGION_LAYER = REGION_LAYER;
  VB.REGION_DETAILS = ["doors", "roofs", "chimneys", "lots", "fences", "kerbs", "trees"];
  VB.REGION_SCALES = [
    { id: "street20", label: "Street 20 ft/in, 5 ft grid", scale: 20, grid: 5 },
    { id: "block40", label: "Block 40 ft/in, 10 ft grid", scale: 40, grid: 10 },
    { id: "room5", label: "Room/battle map 5 ft/in, 5 ft grid", scale: 5, grid: 5 },
    { id: "custom", label: "Custom", scale: null, grid: null }];

  VB.regionDefaults = function () {
    var det = {}; VB.REGION_DETAILS.forEach(function (k) { det[k] = true; });
    return { mode: "district", district: "", polygon: [], polygon_src: "", rect: [0, 0, 0, 0], margin_ft: 40, name: "",
      preset: "street20", scale_ft_per_in: 20, grid_ft: 5, terrain_cell_ft: 2.5, contour_minor: 2, contour_index: 10, detail_ft: 0.45,
      detail: det, detail_on: true, draw: { doors: true, roofs: true, chimneys: true, lots: false, fences: true, kerbs: true, trees: true }, draw_auto: true, headless_png: true, seed: "", fills: true, fills_dpi: 120, shading: "temperate_valley_calm", flatten_pads: true, clip_buildings: false,
      local_origin: false, sandbox: false, px_per_grid: 80, scene_name: "", parent_scene_name: "", link_apply: false,
      sel: "", children: [], diff: null, last: null };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.regions = VB.regionDefaults(); return s; };

  // keep in step with region_extract.slug / default_child_id
  VB.regionSlug = function (s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "region"; };
  VB.regionName = function (st) {
    var r = st.regions;
    if (r.name && String(r.name).trim()) return String(r.name).trim();
    if (r.mode === "district" && r.district) return r.district.replace(/^(dis|sqr|fld)_/, "");
    return "region";
  };
  VB.regionChildId = function (st) {
    var r = st.regions, id = st.place + "__" + VB.regionSlug(VB.regionName(st));
    return r.sandbox ? "_region_test/" + id : id;
  };
  VB.regionApplyPreset = function (r, id) {
    var p = VB.REGION_SCALES.filter(function (x) { return x.id === id; })[0];
    r.preset = id; if (p && p.scale) { r.scale_ft_per_in = p.scale; r.grid_ft = p.grid; }
  };
  VB.regionPolyFile = function (d) { return d.panel + "/region_polygon.json"; };

  // checks before anything runs; returns an error text or null
  VB.regionCheck = function (st) {
    var r = st.regions;
    if (r.mode === "district" && !r.district) return "pick a district (or another entity) from the list";
    if (r.mode === "lasso" && (!r.polygon || r.polygon.length < 3)) return "no lasso: select a closed path (or edit the REGIONS path) and press Capture lasso";
    if (r.mode === "rect" && !(+r.rect[2] > +r.rect[0] && +r.rect[3] > +r.rect[1])) return "rectangle needs x0, y0 < x1, y1 (feet)";
    if (!(+r.scale_ft_per_in > 0) || !(+r.grid_ft > 0)) return "scale and grid must be positive";
    return null;
  };
  VB.regionSpecArgs = function (st, d) {
    var r = st.regions;
    if (r.mode === "district") return ["--district", r.district];
    if (r.mode === "rect") return ["--rect", r.rect.map(Number).join(",")];
    return ["--polygon-file", VB.regionPolyFile(d)];
  };
  VB.regionDetailArg = function (r) {
    if (!r.detail_on) return "none";
    var on = VB.REGION_DETAILS.filter(function (k) { return r.detail[k]; });
    return on.length === VB.REGION_DETAILS.length ? "all" : (on.join(",") || "none");
  };
  // which generated details the 2D map DRAWS (render_world --details): trees (DETAILS - Trees) and lots (DETAILS - Lots) are separate layers; lots are off by default
  VB.regionDrawArg = function (r) {
    if (r.draw_auto !== false) return "auto";
    var d = r.draw || {}, on = VB.REGION_DETAILS.filter(function (k) { return d[k]; });
    return on.length === VB.REGION_DETAILS.length ? "all" : (on.join(",") || "none");
  };
  VB.regionExtractArgs = function (st, d) {
    var r = st.regions, a = ["extract", "--parent", st.place].concat(VB.regionSpecArgs(st, d),
      ["--name", VB.regionName(st), "--margin", String(r.margin_ft), "--terrain-cell", String(r.terrain_cell_ft), "--scale", String(r.scale_ft_per_in), "--grid", String(r.grid_ft),
        "--detail", VB.regionDetailArg(r), "--detail-ft", String(r.detail_ft), "--force"]);
    if (String(r.seed).trim() !== "") a.push("--seed", String(parseInt(r.seed, 10)));
    if (!r.flatten_pads) a.push("--no-flatten-pads");
    if (r.clip_buildings) a.push("--clip-buildings");
    if (r.local_origin) a.push("--local-origin");
    if (r.sandbox) a.push("--sandbox");
    return a;
  };
  VB.regionRenderArgs = function (st, child) {
    var r = st.regions, a = ["--child", child, "--scale", String(r.scale_ft_per_in), "--grid", String(r.grid_ft), "--contour-interval", String(r.contour_minor),
      "--index-interval", String(r.contour_index), "--dpi", String(r.fills_dpi), "--shading", r.shading || "none"];
    if (!r.fills) a.push("--no-fills");
    var dr = r.draw_auto === false ? VB.regionDrawArg(r) : null; if (dr) a.push("--details", dr);
    if (r.headless_png === false) a.push("--no-headless-png");
    return a.concat(VB.labelStyleFlags(st));
  };
  var childFlag = function (c) { return ["--child", c]; };

  // the Illustrator part of a render: open the SVG as a new document, place the raster layers, save (never over an existing .ai) and export a PNG
  var hostSteps = function () {
    return { t: "fn", label: "open the child map in Illustrator", fn: async function (run) {
      var rr = run.vars.rr; if (!rr || !rr.job) throw new Error("region_render gave no job");
      for (var i = 0; i < rr.job.actions.length; i++) await run.host(rr.job.actions[i], rr.job.actions[i].action === "export_png");
      run.log("child map: " + rr.ai);
    } };
  };
  var listStep = function (st) {
    return [py(GEN + "region_extract.py", ["list", "--parent", st.place], "list child regions", { json: "list" }),
      { t: "fn", label: "store child list", fn: function (run) { run.setState("regions.children", (run.vars.list && run.vars.list.children) || []); } }];
  };

  // outline of the region on the parent document: a named, editable closed path on layer REGIONS (Capture lasso reads it back)
  VB.jobRegionPreview = function (st, d) {
    var r = st.regions, svg = d.panel + "/region_preview.svg";
    var args = ["preview", "--parent", st.place].concat(VB.regionSpecArgs(st, d), ["--name", VB.regionName(st), "--margin", String(r.margin_ft), "--out", svg,
      "--view", st.settings.view || "town", "--preset", st.scale.preset, "--scale", String(st.scale.scale_ft_per_in), "--page", st.scale.page_w_in + "x" + st.scale.page_h_in]);
    return { kind: "region_preview", label: "Preview region extent", params: { regions: r },
      steps: [{ t: "fn", label: "check region", fn: function () { var e = VB.regionCheck(st); if (e) throw new Error(e); } },
        { t: "fn", label: "write polygon", fn: function (run) { if (r.mode === "lasso") run.writeJson(VB.regionPolyFile(d), r.polygon); } },
        py(GEN + "region_extract.py", args, "region_extract preview", { json: "pv" })]
        .concat(VB.replaceSteps(svg, [REGION_LAYER], "draw REGIONS layer (editable path)")) };
  };

  // extract (or refresh) + render + open as a new Illustrator document
  VB.jobRegionCreate = function (st, d, o) {
    o = o || {}; var r = st.regions, child = o.child || VB.regionChildId(st);
    var first = o.refresh
      ? py(GEN + "region_extract.py", ["refresh", "--child", child], "region_extract refresh (keeps child edits)", { json: "ext" })
      : py(GEN + "region_extract.py", VB.regionExtractArgs(st, d), "region_extract", { json: "ext" });
    return { kind: o.refresh ? "region_refresh" : "region_create", label: (o.refresh ? "Refresh region from parent: " : "Create region map: ") + child, params: { regions: r, child: child },
      steps: [{ t: "fn", label: "check region", fn: function () { var e = o.refresh ? null : VB.regionCheck(st); if (e) throw new Error(e); } },
        { t: "fn", label: "write polygon", fn: function (run) { if (!o.refresh && r.mode === "lasso") run.writeJson(VB.regionPolyFile(d), r.polygon); } },
        first,
        py(GEN + "region_render.py", VB.regionRenderArgs(st, child), "region_render (district scale)", { json: "rr" }),
        hostSteps()].concat(listStep(st), [{ t: "fn", label: "remember child", fn: function (run) {
          run.setState("regions.sel", child); run.setState("regions.last", { child: child, ai: run.vars.rr && run.vars.rr.ai, at: new Date().toISOString() }); } }]) };
  };
  // render + open only (no extract): the Open button of a listed child
  VB.jobRegionOpen = function (st, d, child) {
    return { kind: "region_open", label: "Open region map: " + child, params: { child: child },
      steps: [py(GEN + "region_render.py", VB.regionRenderArgs(st, child), "region_render (district scale)", { json: "rr" }), hostSteps()] };
  };
  VB.jobRegionList = function (st) {
    return { kind: "region_list", label: "List child regions", params: {}, steps: listStep(st) };
  };
  VB.regionDiffText = function (info) {
    var diffs = (info && info.diffs) || [];
    return diffs.length ? diffs.map(function (x) {
      return x.change ? x.id + ": " + x.change : x.id + "." + x.attr + ": parent " + JSON.stringify(x.parent) + " -> child " + JSON.stringify(x.child);
    }).join("\n") : "no differences in shared attributes";
  };
  // diff child -> parent; `apply` writes the parent (the panel asks twice before it does)
  VB.jobRegionSync = function (st, d, child, apply) {
    return { kind: apply ? "region_sync_apply" : "region_sync_diff", label: (apply ? "Apply child edits to parent: " : "Diff child vs parent: ") + child, params: { child: child, apply: !!apply },
      steps: [py(GEN + "region_extract.py", ["sync"].concat(childFlag(child), apply ? ["--apply"] : []), "region_extract sync", { json: "sync" }),
        { t: "fn", label: "show diff", fn: function (run) {
          var s = run.vars.sync; run.setState("regions.diff", { child: child, n: (s.diffs || []).length, text: VB.regionDiffText(s), applied: s.applied || null });
          run.log(VB.regionDiffText(s)); } }] };
  };
  // child scene on Foundry: export the open child document at grid px = px_per_grid per grid square, push (walls from building edges, pipelineId scene:<child>:<name>)
  VB.regionDpi = function (r) { return Math.round((+r.px_per_grid) * (+r.scale_ft_per_in) / (+r.grid_ft) * 10) / 10; };
  VB.regionPushArgs = function (st, child, image, o) {
    var r = st.regions, a = ["push-scene", "--place", child, "--view", "region", "--image", image];
    var nm = String(r.scene_name || "").trim(); if (nm) a.push("--scene-name", nm);
    if (o && o.dry) a.push("--dry-run");
    return a;
  };
  VB.jobRegionFoundry = function (st, d, child, o) {
    o = o || {}; var r = st.regions, png = VB.foundryOut(d, "region_" + VB.regionSlug(child) + ".png"), dpi = VB.regionDpi(r);
    return { kind: "region_foundry", label: (o.dry ? "Dry run: " : "Push ") + "region scene: " + child, params: { child: child, dpi: dpi, px_per_grid: r.px_per_grid },
      steps: [{ t: "fn", label: "check", fn: function () { if (!(dpi >= 20)) throw new Error("grid px too small"); } },
        host({ action: "export_view", path: png, dpi: dpi, only: [], transparent: false }, "export the open child document (" + dpi + " dpi)"),
        py(VB.FOUNDRY_PY, VB.regionPushArgs(st, child, png, o), "foundry_push push-scene", { json: "push" }),
        { t: "fn", label: "remember scene", fn: function (run) {
          var p = run.vars.push; if (!p || !p.ok) throw new Error((p && p.error) || "push failed");
          run.setState("regions.last", { child: child, scene_uuid: p.scene_uuid || null, scene_name: p.scene_name, grid: p.grid, dry_run: !!p.dry_run, at: new Date().toISOString() });
          run.log((p.dry_run ? "dry run: " : "") + "scene \"" + p.scene_name + "\" " + p.width + "x" + p.height + " px, grid " + p.grid.size + " px = " + p.grid.distance + " ft, " + p.walls + " walls"); } }] };
  };
  // outline of the region on the parent's Foundry scene: dry run unless link_apply
  VB.jobRegionLink = function (st, d, child) {
    var r = st.regions, a = ["link-region", "--place", child];
    if (r.parent_scene_name) a.push("--parent-scene-name", r.parent_scene_name);
    if (r.last && r.last.scene_uuid) a.push("--child-scene-uuid", r.last.scene_uuid);
    if (r.link_apply) a.push("--apply");
    return { kind: "region_link", label: (r.link_apply ? "Link " : "Dry run link ") + child + " on the parent scene", params: { child: child, apply: !!r.link_apply },
      steps: [{ t: "fn", label: "check", fn: function () { if (!r.parent_scene_name) throw new Error("type the parent scene name (the pipeline scene the region sits on)"); } },
        py(VB.FOUNDRY_PY, a, "foundry_push link-region", { json: "link" })] };
  };
})(typeof window !== "undefined" ? window : this);
