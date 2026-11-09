// Heightmap paint additions to VBCore (loaded after core.js): defaults, stroke building, jobs and the shaded-relief renderer for the Paint tab.
// Pure logic, no DOM: also loaded by test/test_heightpaint_jobs.js. Python side: generators/heightmap_paint.py (the brush maths and the edit layer live there;
// the panel only records strokes, runs the commands and draws the downsampled preview they write).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;

  VB.HP_TOOLS = [
    { id: "raise", label: "Raise" }, { id: "lower", label: "Lower" }, { id: "smooth", label: "Smooth" }, { id: "flatten", label: "Flatten" },
    { id: "set", label: "Set height" }, { id: "noise", label: "Roughen" }, { id: "ridge", label: "Ridge" }, { id: "valley", label: "Valley" }, { id: "river", label: "River carve" }
  ];
  VB.HP_FALLOFFS = ["smooth", "linear", "sharp", "round", "constant"];
  VB.HP_MAX_UNDO = 200;

  VB.hpDefaults = function () {
    return { tool: "raise", radius_ft: 30, strength: 0.5, falloff: "smooth", hardness: 0.2, rate_ft: 2, height_ft: "", depth_ft: 6, bank_slope: 0.6, noise_scale_ft: "", seed: 7,
      contour_ft: 0, exag: 1, light_az: 315, show_delta: true, max_px: 640, auto_apply: true, rebuild_pack: false,
      view: { zoom: 1, ox: 0, oy: 0 }, meta: null, stats: null, strokes: 0, redo: [], unsaved: false, last: null,
      check: null, chk_delta_ft: 3, chk_cross_deg: 10, conform_extra_ft: 2, conform_falloff_ft: 12, conform_smooth_ft: 40 };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.hp = VB.hpDefaults(); return o; };

  var num = function (v, dd) { if (v === null || v === undefined || String(v).trim() === "") return dd; v = Number(v); return isFinite(v) ? v : dd; };
  VB.hpWorkDir = function (d) { return d.panel + "/heightmap_paint"; };
  VB.hpPreviewDir = function (d) { return VB.hpWorkDir(d) + "/preview"; };
  VB.hpStrokesPath = function (d) { return d.panel + "/heightmap_paint_strokes.json"; };

  // brush settings + the path (feet) -> one stroke object for heightmap_paint.py (only the fields the tool uses)
  VB.hpStroke = function (st, points) {
    var p = st.hp, tool = p.tool;
    if (!VB.HP_TOOLS.some(function (t) { return t.id === tool; })) throw new Error("unknown brush " + tool);
    if (!points || !points.length) throw new Error("a stroke needs at least one point");
    var s = { tool: tool, points: points.map(function (q) { return [Math.round(q[0] * 100) / 100, Math.round(q[1] * 100) / 100]; }),
      radius_ft: Math.max(num(p.radius_ft, 30), 0.5), strength: Math.min(Math.max(num(p.strength, 0.5), 0), 1),
      falloff: VB.HP_FALLOFFS.indexOf(p.falloff) >= 0 ? p.falloff : "smooth", hardness: Math.min(Math.max(num(p.hardness, 0), 0), 1) };
    if (tool === "raise" || tool === "lower" || tool === "noise") s.rate_ft = num(p.rate_ft, 2);
    if (tool === "set") { var h = num(p.height_ft, null); if (h === null) throw new Error("Set height needs a height (ft)"); s.height_ft = h; }
    if (tool === "flatten" && num(p.height_ft, null) !== null) s.height_ft = num(p.height_ft, 0);
    if (tool === "ridge" || tool === "valley") s.height_ft = Math.abs(num(p.height_ft, 15));
    if (tool === "river") { s.depth_ft = Math.max(num(p.depth_ft, 6), 0); s.bank_slope = Math.max(num(p.bank_slope, 0.6), 0); }
    if (tool === "noise") { s.seed = Math.round(num(p.seed, 7)); var ns = num(p.noise_scale_ft, null); if (ns) s.noise_scale_ft = ns; }
    return s;
  };

  VB.hpBase = function (st) { return ["--place", st.place]; };
  VB.hpPreviewArgs = function (st, d, layer) {
    var p = st.hp;
    return ["export-preview"].concat(VB.hpBase(st), ["--layer", layer || "work", "--max-px", String(Math.round(Math.min(Math.max(num(p.max_px, 640), 64), 2048))), "--bin-dir", VB.hpPreviewDir(d)]);
  };
  function remember(run) {
    var pv = run.vars.pv, ss = run.vars.hs;
    if (pv) run.setState("hp.meta", pv);
    if (ss) { run.setState("hp.stats", ss); run.setState("hp.strokes", ss.strokes); run.setState("hp.unsaved", !!ss.unsaved); }
    if (run.vars.hc) run.setState("hp.check", { warnings: run.vars.hc.warnings || [], flagged_roads: run.vars.hc.flagged_roads || [], n_roads_changed: run.vars.hc.n_roads_changed || 0,
      buildings: (run.vars.hc.buildings || []).filter(function (b) { return b.flagged; }).map(function (b) { return b.id; }) });
    run.setState("hp.stamp", Date.now());
  }
  var statsStep = function (st) { return py(GEN + "heightmap_paint.py", function () { return ["stats"].concat(VB.hpBase(st)); }, "heightmap_paint.py stats", { json: "hs" }); };
  // what the edit layer does to roads, bridges and buildings (heightmap_paint.py check): warnings list under the canvas
  VB.hpCheckArgs = function (st) {
    var p = st.hp;
    return ["check"].concat(VB.hpBase(st), ["--layer", "work", "--delta-ft", String(Math.max(num(p.chk_delta_ft, 3), 0.1)), "--cross-deg", String(Math.max(num(p.chk_cross_deg, 10), 1))]);
  };
  var checkStep = function (st) { return py(GEN + "heightmap_paint.py", function () { return VB.hpCheckArgs(st); }, "heightmap_paint.py check", { json: "hc" }); };
  var previewStep = function (st, d, layer) { return py(GEN + "heightmap_paint.py", function () { return VB.hpPreviewArgs(st, d, layer); }, "heightmap_paint.py export-preview", { json: "pv" }); };

  // mode: append (strokes on top of the working layer) | undo-last | replay | replace. quiet jobs are not written to the jobs log (one per brush stroke would flood it).
  VB.jobHpApply = function (st, d, strokes, mode) {
    mode = mode || "append"; strokes = strokes || [];
    var steps = [];
    if (mode === "append" || mode === "replace") {
      steps.push({ t: "fn", label: "check", fn: function () { if (!strokes.length) throw new Error("no strokes to apply"); strokes.forEach(function (s) { if (!s || !s.tool) throw new Error("bad stroke"); }); } });
      steps.push({ t: "write", path: VB.hpStrokesPath(d), data: { strokes: strokes }, label: "strokes" });
    }
    steps.push(py(GEN + "heightmap_paint.py", function () {
      var a = ["apply-strokes"].concat(VB.hpBase(st), ["--mode", mode]);
      if (mode === "append" || mode === "replace") a.push("--strokes", VB.hpStrokesPath(d));
      return a;
    }, "heightmap_paint.py apply-strokes", { json: "ap" }));
    steps.push(previewStep(st, d), statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: remember });
    return { kind: "hp_" + mode.replace("-", "_"), label: "Paint: " + mode + (strokes.length ? " (" + strokes.length + " stroke" + (strokes.length > 1 ? "s" : "") + ")" : ""), noLog: true, params: { mode: mode, n: strokes.length }, steps: steps };
  };
  VB.jobHpRefresh = function (st, d, layer) {
    return { kind: "hp_preview", label: "Paint: refresh preview", noLog: true, steps: [previewStep(st, d, layer), statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: remember }] };
  };
  // flatten the edit layer across road footprints (heightmap_paint.py conform-roads): the roads check flags (ids empty) or the given road ids. One undoable stroke.
  VB.hpConformArgs = function (st, ids) {
    var p = st.hp, a = ["conform-roads"].concat(VB.hpBase(st));
    if (ids && ids.length) a.push("--roads", ids.join(","));
    return a.concat(["--extra-ft", String(Math.max(num(p.conform_extra_ft, 2), 0)), "--falloff-ft", String(Math.max(num(p.conform_falloff_ft, 12), 0.5)), "--smooth-ft", String(Math.max(num(p.conform_smooth_ft, 40), 0))]);
  };
  VB.jobHpConform = function (st, d, ids) {
    return { kind: "hp_conform", label: "Paint: flatten under roads", noLog: true, params: { roads: ids || "flagged" }, steps: [
      py(GEN + "heightmap_paint.py", function () { return VB.hpConformArgs(st, ids); }, "heightmap_paint.py conform-roads", { json: "cf" }),
      previewStep(st, d), statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: function (run) { remember(run); run.setState("hp.redo", []); run.setState("hp.unsaved", true); } }] };
  };
  VB.jobHpCheck = function (st, d) { return { kind: "hp_check", label: "Paint: check roads", noLog: true, steps: [statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: remember }] }; };
  VB.jobHpSave = function (st, d) {
    var steps = [py(GEN + "heightmap_paint.py", function () { return ["save"].concat(VB.hpBase(st)); }, "heightmap_paint.py save", { json: "sv" }), previewStep(st, d), statsStep(st), checkStep(st),
      { t: "fn", label: "remember", fn: function (run) { remember(run); run.setState("hp.last", { at: new Date().toISOString(), saved: !!(run.vars.sv && run.vars.sv.saved), path: run.vars.sv && run.vars.sv.path }); run.setState("hp.redo", []); } }];
    if (st.hp.rebuild_pack) steps.push.apply(steps, VB.jobWorldPack(st, d).steps);
    return { kind: "hp_save", label: st.hp.rebuild_pack ? "Heightmap: save edits and export the world pack" : "Heightmap: save edits", params: { rebuild_pack: !!st.hp.rebuild_pack }, steps: steps };
  };
  VB.jobHpDiscard = function (st, d) {
    return { kind: "hp_discard", label: "Heightmap: discard unsaved edits", noLog: true, steps: [py(GEN + "heightmap_paint.py", function () { return ["discard"].concat(VB.hpBase(st)); }, "heightmap_paint.py discard"),
      previewStep(st, d), statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: function (run) { remember(run); run.setState("hp.redo", []); } }] };
  };
  VB.jobHpReset = function (st, d) {   // empties both the working copy and the saved layer: the generated terrain shows again
    return { kind: "hp_reset", label: "Heightmap: reset (remove all edits)", steps: [py(GEN + "heightmap_paint.py", function () { return ["reset"].concat(VB.hpBase(st), ["--layer", "both"]); }, "heightmap_paint.py reset"),
      previewStep(st, d), statsStep(st), checkStep(st), { t: "fn", label: "remember", fn: function (run) { remember(run); run.setState("hp.redo", []); } }] };
  };
  VB.jobHpStats = function (st, d) { return { kind: "hp_stats", label: "Heightmap: statistics", noLog: true, steps: [statsStep(st), { t: "fn", label: "remember", fn: remember }] }; };

  // ---- view maths: preview pixel <-> feet <-> screen
  VB.hpFeetToPx = function (meta, x, y) { var s = meta.cell_ft * meta.factor; return [x / s, y / s]; };
  VB.hpPxToFeet = function (meta, px, py_) { var s = meta.cell_ft * meta.factor; return [px * s, py_ * s]; };
  VB.hpScreenToFeet = function (meta, view, sx, sy) { return VB.hpPxToFeet(meta, (sx - view.ox) / view.zoom, (sy - view.oy) / view.zoom); };
  VB.hpFit = function (meta, w, h) {          // zoom + offset that centre the whole preview in a w x h canvas
    var z = Math.min(w / meta.pw, h / meta.ph) * 0.96; return { zoom: z, ox: (w - meta.pw * z) / 2, oy: (h - meta.ph * z) / 2 };
  };
  // zoom about a screen point (wheel): the feet under the cursor stay under it
  VB.hpZoomAt = function (view, sx, sy, factor) {
    var z = Math.min(Math.max(view.zoom * factor, 0.05), 80), k = z / view.zoom;
    return { zoom: z, ox: sx - (sx - view.ox) * k, oy: sy - (sy - view.oy) * k };
  };
  VB.hpBilinear = function (h, pw, ph, fx, fy) {   // fx, fy in preview pixels
    var x = Math.min(Math.max(fx, 0), pw - 1), y = Math.min(Math.max(fy, 0), ph - 1), x0 = Math.floor(x), y0 = Math.floor(y), x1 = Math.min(x0 + 1, pw - 1), y1 = Math.min(y0 + 1, ph - 1), tx = x - x0, ty = y - y0;
    return (h[y0 * pw + x0] * (1 - tx) + h[y0 * pw + x1] * tx) * (1 - ty) + (h[y1 * pw + x0] * (1 - tx) + h[y1 * pw + x1] * tx) * ty;
  };

  // ---- shaded relief like generators/heightmap_paint.render_rgb (same tint, hillshade, contour rule): returns RGBA bytes (Uint8ClampedArray / Array)
  var STOPS = [0, 0.12, 0.45, 0.75, 1], COLS = [[70, 125, 70], [140, 170, 90], [170, 150, 105], [150, 140, 135], [250, 250, 250]];
  function tint(t) {
    t = Math.min(Math.max(t, 0), 1); var i = 0; while (i < 3 && t > STOPS[i + 1]) i++;
    var f = (t - STOPS[i]) / (STOPS[i + 1] - STOPS[i]); return [0, 1, 2].map(function (k) { return COLS[i][k] + (COLS[i + 1][k] - COLS[i][k]) * f; });
  }
  VB.hpRender = function (h, pw, ph, o) {
    o = o || {}; var cell = o.cell_ft || 1, lo = o.lo, hi = o.hi, ex = o.exag || 1, contour = o.contour_ft || 0, d = o.delta || null, az = (o.azimuth === undefined ? 315 : o.azimuth) * Math.PI / 180, alt = 40 * Math.PI / 180;
    var lx = Math.sin(az) * Math.cos(alt), ly = -Math.cos(az) * Math.cos(alt), lz = Math.sin(alt), sal = Math.sin(alt);
    var out = (typeof Uint8ClampedArray !== "undefined") ? new Uint8ClampedArray(pw * ph * 4) : new Array(pw * ph * 4), dmax = 0, i, x, y;
    if (d) for (i = 0; i < d.length; i++) dmax = Math.max(dmax, Math.abs(d[i]));
    var at = function (xx, yy) { return h[Math.min(Math.max(yy, 0), ph - 1) * pw + Math.min(Math.max(xx, 0), pw - 1)]; };
    for (y = 0; y < ph; y++) for (x = 0; x < pw; x++) {
      var gx = (at(x + 1, y) - at(x - 1, y)) / ((x > 0 && x < pw - 1 ? 2 : 1) * cell) * ex, gy = (at(x, y + 1) - at(x, y - 1)) / ((y > 0 && y < ph - 1 ? 2 : 1) * cell) * ex;
      var hs = Math.min(Math.max((-gx * lx - gy * ly + lz) / Math.sqrt(gx * gx + gy * gy + 1), 0), 1);
      var sh = Math.min(Math.max(0.9 + (hs - sal) * 0.55, 0.55), 1.1), v = h[y * pw + x], c = tint((v - lo) / Math.max(hi - lo, 1e-6));
      if (d && dmax > 1e-6 && Math.abs(d[y * pw + x]) > 1e-4) {
        var m = Math.min(Math.abs(d[y * pw + x]) / dmax, 1) * 0.55, tc = d[y * pw + x] >= 0 ? [230, 60, 40] : [40, 90, 230];
        c = [0, 1, 2].map(function (k) { return c[k] * sh * (1 - m) + tc[k] * m; });
      } else c = c.map(function (u) { return u * sh; });
      if (contour > 0) {
        var q = Math.floor(v / contour), e = (x < pw - 1 && Math.floor(h[y * pw + x + 1] / contour) !== q) || (y < ph - 1 && Math.floor(h[(y + 1) * pw + x] / contour) !== q);
        if (e) { var k2 = (((q % 5) + 5) % 5 === 0) ? 0.434 : 0.62; c = c.map(function (u) { return u * k2; }); }
      }
      var o4 = (y * pw + x) * 4; out[o4] = c[0]; out[o4 + 1] = c[1]; out[o4 + 2] = c[2]; out[o4 + 3] = 255;
    }
    return out;
  };
  // preview.bin (float32 little endian) -> Float32Array (copies out of the Node Buffer so alignment never matters)
  VB.hpReadBin = function (buf) { var n = Math.floor(buf.length / 4), a = new Float32Array(n), dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength); for (var i = 0; i < n; i++) a[i] = dv.getFloat32(i * 4, true); return a; };
})(typeof window !== "undefined" ? window : this);
