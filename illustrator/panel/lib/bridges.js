// Bridges additions to VBCore (loaded after core.js): defaults, command lines and jobs for the Bridges tab (detect crossings, auto-fix, apply to one, remove, preview).
// Pure logic, no DOM: also loaded by test/test_bridges_jobs.js. Python side: generators/bridge_maker.py and bridge_preview.py (world/<place>/bridges.json).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  VB.BRIDGE_PRESETS = [
    ["stone_arch", "Stone arch"], ["brick_arch", "Brick arch"], ["wooden_truss", "Wooden truss (rough-hewn log)"], ["flat_cut_stone", "Flat cut stone"], ["plank_footbridge", "Plank footbridge"]];

  VB.bridgesDefaults = function () {
    return { float_ft: 4, level_ft: 3, selected: "", preset: "", seed: "", width_ft: "", clearance_w_ft: "", clearance_h_ft: "", parapet_h_ft: "", n_arches: "", rise_ratio: "",
      crossings: [], items: [], preview_png: "", last: null };
  };
  var opt = function (v) { return v === "" || v === null || v === undefined || !isFinite(Number(v)) ? null : Number(v); };
  // slider/number fields -> --set key=value pairs (only the ones that are filled in)
  VB.bridgeOverrides = function (st) {
    var b = st.bridges, a = [];
    ["width_ft", "clearance_w_ft", "clearance_h_ft", "parapet_h_ft", "n_arches", "rise_ratio"].forEach(function (k) { var v = opt(b[k]); if (v !== null) a.push("--set", k + "=" + v); });
    return a;
  };
  VB.bridgeArgs = function (st, d, extra) {
    var b = st.bridges, a = ["--place", st.place, "--pack", d.world + "/export"];
    if (extra && extra.thresholds) a.push("--float-ft", String(opt(b.float_ft) === null ? 4 : b.float_ft), "--level-ft", String(opt(b.level_ft) === null ? 3 : b.level_ft));
    return a;
  };
  function remember(run, det) {
    var list = (det && det.crossings) || [];
    run.setState("bridges.crossings", list);
    run.log(list.length + " crossing(s): " + list.map(function (c) { return c.id + " (" + c.type + ", " + Math.round(c.span_ft) + " ft, deck " + Number(c.deck_above_ground_ft).toFixed(1) + " ft above ground)"; }).join("; "));
  }
  function readItems(run, d) {
    var doc = run.readJson(d.world + "/bridges.json", { bridges: [], removed: [] });
    var gone = {}; (doc.removed || []).forEach(function (i) { gone[i] = true; });
    run.setState("bridges.items", (doc.bridges || []).filter(function (b) { return !gone[b.id]; }).map(function (b) {
      return { id: b.id, road: b.road, preset: b.preset, crossing: b.crossing, length_ft: b.span.length_ft, width_ft: b.span.width_ft, locked: !!b.locked, warnings: (b.provenance || {}).warnings || [], deficit_m: (b.provenance || {}).clearance_deficit_m || 0 };
    }));
  }
  VB.jobBridgesDetect = function (st, d) {
    return { kind: "bridges_detect", label: "Detect crossings", params: { bridges: st.bridges },
      steps: [py(GEN + "bridge_maker.py", function () { return ["detect"].concat(VB.bridgeArgs(st, d, { thresholds: true })); }, "bridge_maker.py detect", { json: "det" }),
        { t: "fn", label: "remember", fn: function (run) { remember(run, run.vars.det); readItems(run, d); } }] };
  };
  // auto-fix: detect every crossing, write world/<place>/bridges.json, re-export the pack with the bridges in it (hand-tuned bridges stay)
  VB.jobBridgesAutoFix = function (st, d) {
    return { kind: "bridges_autofix", label: "Auto-fix all crossings", params: { bridges: st.bridges },
      steps: [py(GEN + "bridge_maker.py", function () { return ["apply"].concat(VB.bridgeArgs(st, d, { thresholds: true })); }, "bridge_maker.py apply", { json: "ap" }),
        { t: "fn", label: "remember", fn: function (run) {
          var r = run.vars.ap; remember(run, { crossings: r.report || [] }); readItems(run, d);
          run.setState("bridges.last", { at: new Date().toISOString(), made: r.new || [], roads: r.roads_with_gaps || [] });
          run.log((r.new || []).length ? "bridges: " + r.new.join(", ") : "no crossing needs a bridge");
        } }],
      setStale: ["export"] };
  };
  VB.jobBridgesApply = function (st, d) {
    var b = st.bridges;
    return { kind: "bridges_apply", label: "Apply bridge " + b.selected, params: { bridges: b },
      steps: [{ t: "fn", label: "check", fn: function () { if (!b.selected) throw new Error("select a crossing in the list first"); } },
        py(GEN + "bridge_maker.py", function () {
          var a = ["apply", "--place", st.place, "--only", b.selected];
          if (b.preset) a.push("--preset", b.preset);
          if (opt(b.seed) !== null) a.push("--seed", String(Math.round(Number(b.seed))));
          return a.concat(VB.bridgeOverrides(st), ["--pack", d.world + "/export"]);
        }, "bridge_maker.py apply --only", { json: "ap" }),
        { t: "fn", label: "remember", fn: function (run) { readItems(run, d); run.log("applied " + b.selected + (b.preset ? " as " + b.preset : "")); } }],
      setStale: ["export"] };
  };
  VB.jobBridgesRemove = function (st, d) {
    var b = st.bridges;
    return { kind: "bridges_remove", label: "Remove bridge " + b.selected, params: { bridges: b },
      steps: [{ t: "fn", label: "check", fn: function () { if (!b.selected) throw new Error("select a bridge in the list first"); } },
        py(GEN + "bridge_maker.py", function () { return ["remove", "--place", st.place, "--id", b.selected]; }, "bridge_maker.py remove", { json: "rm" }),
        py(GEN + "bridge_maker.py", function () { return ["inject", "--place", st.place, "--pack", d.world + "/export"]; }, "bridge_maker.py inject", { json: "inj" }),
        { t: "fn", label: "remember", fn: function (run) { readItems(run, d); run.setState("bridges.selected", ""); run.log("removed " + b.selected + " (the road ribbon is back after the next split)"); } }],
      setStale: ["export"] };
  };
  VB.jobBridgesPreview = function (st, d) {
    var b = st.bridges, out = d.panel + "/bridges_preview";
    return { kind: "bridges_preview", label: "Preview render", params: { bridges: b },
      steps: [{ t: "fn", label: "check", fn: function () { if (!b.selected) throw new Error("select a crossing in the list first"); } },
        py(GEN + "bridge_preview.py", function () {
          var a = ["entity", "--place", st.place, "--id", b.selected, "--pack", d.world + "/export", "--out", out];
          if (b.preset) a.push("--preset", b.preset);
          return a.concat(VB.bridgeOverrides(st));
        }, "bridge_preview.py entity", { json: "pv" }),
        { t: "fn", label: "show", fn: function (run) {
          var r = run.vars.pv; run.setState("bridges.preview_png", r.png + "?" + Date.now());
          run.log("preview: " + r.tris + " tris, clearance violations " + r.clearance_violations + (r.ok ? "" : " (clearance NOT met: " + (r.notes || []).join("; ") + ")"));
        } }] };
  };
  // zoom Illustrator to the bridge symbol (or its road) on the open map
  VB.jobBridgesFocus = function (st) {
    var b = st.bridges, c = (b.crossings || []).concat(b.items || []).filter(function (x) { return x.id === b.selected; })[0] || {};
    return { kind: "bridges_focus", label: "Zoom to " + b.selected, params: { id: b.selected },
      steps: [VB.steps.host({ action: "focus_items", names: [b.selected + "_outline", c.road || ""].filter(Boolean) }, "focus", true)] };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.bridges = VB.bridgesDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
