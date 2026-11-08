// Buildings tab (building style presets) pieces for VBCore: defaults, selection -> building ids, jobs. Pure logic, no DOM: also loaded by test/test_styles_jobs.js.
// Python side: generators/building_styles.py (assign / summary / list). A style is stored as the `style` key of world/<place>/buildings/<id>.json;
// the 3D world pack picks it up the next time it is exported (Foundry tab: Export world pack, Export split models).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  VB.STYLE_TARGETS = [["selected", "Selected buildings (ticked below or from the Illustrator selection)"], ["kind", "Every building of a kind"],
    ["district", "Every building in a district"], ["all", "All buildings of the place"]];
  VB.stylesDefaults = function () { return { style: "tudor", target: "selected", kind: "house", district: "", ids: [], ids_src: "", filter: "", last: null }; };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.styles = VB.stylesDefaults(); return s; };

  // building ids from the names of the selected Illustrator paths (render_world names items bld_<kind>_<n>, with suffixes such as _lot, _roof)
  VB.stylesIdsFromSelection = function (sel, known) {
    var ids = [], seen = {}, kn = known ? {} : null;
    (known || []).forEach(function (k) { kn[k] = 1; });
    ((sel && sel.paths) || []).forEach(function (p) {
      var m = /(bld_[A-Za-z0-9]+_\d+)/.exec(String(p.name || "").replace(/_x5F_/g, "_"));
      if (m && !seen[m[1]] && (!kn || kn[m[1]])) { seen[m[1]] = 1; ids.push(m[1]); }
    });
    return ids;
  };
  VB.stylesCheck = function (st) {
    var s = st.styles;
    if (s.style !== "none" && s.style !== "auto" && !s.style) return "pick a style";
    if (s.target === "selected" && !(s.ids && s.ids.length)) return "no buildings chosen: tick some in the list or press 'Use Illustrator selection'";
    if (s.target === "kind" && !s.kind) return "pick a building kind";
    if (s.target === "district" && !s.district) return "pick a district";
    return null;
  };
  VB.stylesAssignArgs = function (st, styleId) {
    var s = st.styles, a = ["assign", "--place", st.place, "--style", styleId || s.style];
    if (s.target === "selected") a.push("--ids", s.ids.join(","));
    else if (s.target === "kind") a.push("--kind", s.kind);
    else if (s.target === "district") a.push("--district", s.district);
    else a.push("--all");
    return a;
  };
  // Apply (or clear with styleId "none") to the chosen buildings
  VB.jobStylesAssign = function (st, d, styleId, extra) {
    var s = st.styles, sid = styleId || s.style, ex = extra || [];
    return { kind: "styles_assign", label: (sid === "none" ? "Clear building style" : "Set building style " + sid) + " (" + s.target + ")", params: { styles: { style: sid, target: s.target, kind: s.kind, district: s.district, ids: s.ids } },
      steps: [{ t: "fn", label: "check selection", fn: function () { var e = VB.stylesCheck(st); if (e) throw new Error(e); } },
        py(GEN + "building_styles.py", ex.concat(VB.stylesAssignArgs(st, sid)), "building_styles assign", { json: "assign" }),
        { t: "fn", label: "remember", fn: function (run) { var r = run.vars.assign || {}; run.setState("styles.last", { style: r.style, count: r.count, at: new Date().toISOString() }); run.log((r.count || 0) + " building(s) changed"); } }] };
  };
  VB.jobStylesFromSelection = function (st, known) {
    return { kind: "styles_selection", label: "Read buildings from the Illustrator selection", params: {},
      steps: [VB.steps.host({ action: "get_selection" }, "read selection"),
        { t: "fn", label: "map to building ids", fn: function (run) {
          var ids = VB.stylesIdsFromSelection(run.last, known);
          if (!ids.length) throw new Error("none of the selected items is named like a building id (bld_house_041 ...)");
          run.setState("styles.ids", ids); run.setState("styles.target", "selected"); run.setState("styles.ids_src", "Illustrator selection (" + ids.length + ")");
          run.log(ids.length + " building(s): " + ids.join(", ")); } }] };
  };
})(typeof window !== "undefined" ? window : globalThis);
