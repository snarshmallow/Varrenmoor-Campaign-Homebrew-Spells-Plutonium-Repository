// Town area ("auto lasso") panel pieces: params, jobs. Loaded after core.js; extends window.VBCore without touching it.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof module !== "undefined" && module.exports ? module.exports : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var AREA_LAYERS = ["TOWN AREA", "TOWN AREA RINGS"];
  VB.AREA_LAYERS = AREA_LAYERS;

  // defaults mirror town_area.DEFAULTS
  VB.areaDefaults = function () {
    return { slope_limit: 0.15, river_buffer_ft: 14, smoothing_ft: 55, min_width_ft: 150, noise_ft: 22, target_area_ft2: 0, area_scale: 1, seed: 1103 };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.town.aa = VB.areaDefaults(); s.town.fit = "buildings"; s.town.fit_margin_ft = 40; return s; };

  var baseFrom = VB.townFromParams;
  VB.townFromParams = function (p, t) {
    baseFrom(p, t);
    var a = p.area_auto || {}, d = VB.areaDefaults();
    t.aa = Object.assign({}, d, t.aa || {});
    Object.keys(d).forEach(function (k) { if (a[k] != null) t.aa[k] = a[k]; });
    if (a.target_area_ft2 === null) t.aa.target_area_ft2 = 0;
    return t;
  };

  // town_params for town_gen / town_area: the lasso in state is used as drawn (area_mode manual), terrain rings
  var baseMerge = VB.mergeTownParams;
  VB.areaParams = function (t) {
    var o = {}, a = t.aa || VB.areaDefaults();
    ["slope_limit", "river_buffer_ft", "smoothing_ft", "min_width_ft", "noise_ft", "area_scale", "seed"].forEach(function (k) { if (a[k] !== "" && a[k] != null) o[k] = +a[k]; });
    o.target_area_ft2 = +a.target_area_ft2 > 0 ? +a.target_area_ft2 : null;
    return o;
  };
  VB.mergeTownParams = function (base, t) {
    var p = baseMerge(base, t);
    p.area_auto = Object.assign({}, p.area_auto || {}, VB.areaParams(t));
    p.area_mode = "manual";
    return p;
  };

  // Frame the page on the buildings | the town lasso | the whole place: picks the next nice scale, writes scale/grid/focus into the preset of
  // view_settings.json (so every generator, the lighting/fills/Foundry push included, uses the same frame) and the panel scale fields.
  VB.jobTownFit = function (st, d) {
    var t = st.town, what = ["buildings", "area", "all"].indexOf(t.fit) >= 0 ? t.fit : "buildings", sc = st.scale;
    var args = ["fit", "--place", st.place, "--view", st.settings.view || "town", "--preset", sc.preset, "--page", sc.page_w_in + "x" + sc.page_h_in, "--what", what,
      "--fit-margin", String(+t.fit_margin_ft || 0)];
    return {
      kind: "town_fit", label: "Fit page to " + what,
      params: { fit: what, margin: t.fit_margin_ft },
      steps: [
        VB.steps.py(GEN + "panelio.py", args, "panelio fit", { json: "fit" }),
        { t: "fn", label: "store frame", fn: function (run) {
          var f = run.vars.fit; if (!f || !f.scale_ft_per_in) throw new Error("fit returned no scale");
          var p = d.world + "/view_settings.json", raw = run.readJson(p, {});
          raw.presets = raw.presets || {}; var pr = raw.presets[sc.preset] = Object.assign({}, raw.presets[sc.preset] || {});
          pr.scale_ft_per_in = f.scale_ft_per_in; pr.grid_ft = f.grid_ft; pr.focus = f.focus_ft; delete pr.scale_bar_ft;
          run.writeJson(p, raw);
          run.setState("scale.scale_ft_per_in", f.scale_ft_per_in); run.setState("scale.grid_ft", f.grid_ft);
          run.log("framed on " + what + ": 1 in = " + f.scale_ft_per_in + " ft, centre " + f.focus_ft.join(", ") + " (press Redraw all GEN layers to draw it)"); } }
      ],
      setStale: ["contours", "shading", "town"]
    };
  };

  // mode: "auto" (generate from terrain) | "snap" (settle the captured lasso onto the terrain)
  VB.jobTownArea = function (st, d, mode) {
    var t = st.town, params = d.panel + "/town_params_area.json", out = d.panel + "/town_area.json", svg = d.panel + "/town_area.svg";
    var py = VB.steps.py;
    var args = ["--place", st.place, "--mode", mode, "--params", params, "--out", out, "--svg", svg].concat(VB.viewFlags(st));
    return {
      kind: "town_area_" + mode, label: mode === "snap" ? "Snap lasso to terrain" : "Auto lasso from terrain", params: { aa: t.aa },
      steps: [
        { t: "fn", label: "check lasso", fn: function () {
          if (mode === "snap" && (!t.area || t.area.length < 3)) throw new Error("no lasso to snap: Capture lasso first (or Reload town_params.json)"); } },
        { t: "fn", label: "write area params", fn: function (run) {
          var p = VB.mergeTownParams(run.readJson(d.world + "/town_params.json", {}), t);
          if (mode === "auto") { delete p.area_ft; p.area_mode = "auto"; }
          p.place = st.place; run.writeJson(params, p); } },
        py(GEN + "town_area.py", args, "town_area.py (" + mode + ")", { json: "area" }),
        { t: "fn", label: "store the outline", fn: function (run) {
          var a = run.vars.area; if (!a || !a.area_ft) throw new Error("town_area returned no outline");
          run.setState("town.area", a.area_ft);
          run.setState("town.area_src", (mode === "snap" ? "snapped to terrain" : "auto lasso") + " (" + a.stats.vertices + " pts, " + a.stats.area_ft2 + " ft2, max turn " + a.stats.max_turn_deg + " deg)");
          run.log("outline: " + JSON.stringify(a.stats)); } }
      ].concat(VB.replaceSteps(svg, AREA_LAYERS, "draw TOWN AREA layer (edit it, then Capture lasso)")),
      setStale: ["town"]
    };
  };
})(typeof window !== "undefined" ? window : this);
