// Generic "Update the map layers too" helper: after an edit of the world data (buildings, roads ...), render the place once with the same arguments as
// 'Redraw all GEN layers' (minus contours) and replace only the named layers of the open drawing, in groups (one Illustrator call per group, every host
// step optional: a failure is a warning and the rest still runs). Pure logic, no DOM: also loaded by the Node tests.
//   VB.mapRefreshSteps(st, d, { svg, groups: [[label, [layer names]], ...], labels: true, fills: "buildings" | "streets" | null, absentIds: [ids] | fn(run),
//                                tag: "map", note: "..." })
//   labels: every label layer except contour heights (Labels - Elevation) is replaced together: one declutter pass places all of them, so replacing only
//           'Labels - Buildings' would leave halos / leaders of the old pass behind.
//   fills : the textured fills (ART - Fills) of one part when the full-map fills are on (fills_raster --only <part> when flat copies are off),
//           else the flat swatch fills.
//   absentIds: after the render, object_edit.py svg-absent checks the rendered SVG no longer names these ids (deleted buildings); the job stops
//           BEFORE touching Illustrator when one is still there.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var api = {};
  // layers that show buildings (render_world): footprints, wall lines, block fills, region details (doors, roofs, chimneys, lots), lot fences
  api.BUILDING_LAYERS = ["Buildings", "Walls", "Blocks"];
  api.BUILDING_DETAIL_LAYERS = ["Details", "DETAILS - Lots", "Fences"];
  api.labelLayers = function () { return (VB.LABEL_LAYERS || []).filter(function (n) { return n !== "Labels - Elevation"; }); };
  // every layer name a refresh would replace (for tests and the UI note)
  api.layersOf = function (opts) {
    var out = [];
    (opts.groups || []).forEach(function (g) { g[1].forEach(function (n) { if (out.indexOf(n) < 0) out.push(n); }); });
    if (opts.labels !== false) api.labelLayers().forEach(function (n) { if (out.indexOf(n) < 0) out.push(n); });
    return out;
  };
  api.steps = function (st, d, opts) {
    opts = opts || {};
    var svg = opts.svg || (d.panel + "/map_refresh.svg"), labels = opts.labels !== false, fills = opts.fills && st.town && st.town.autofill;
    var groups = (opts.groups || []).filter(function (g) { return g[1] && g[1].length; });
    var n = 1 + (opts.absentIds ? 1 : 0) + groups.length + (labels ? 1 : 0) + (fills ? 1 : 0), k = 0;
    var tag = function (s) { k++; return (opts.tag || "map") + " " + k + "/" + n + ": " + s; };
    var args = ["--place", st.place].concat(VB.viewFlags(st), ["--out", svg], VB.srcFlags(st), VB.labelFlags(st));
    var steps = [VB.steps.py(GEN + "render_world.py", args, tag("render the map (render_world)"))];
    if (opts.absentIds) {
      var idsOf = function (run) { var x = typeof opts.absentIds === "function" ? opts.absentIds(run) : opts.absentIds; return (x || []).join(","); };
      steps.push(VB.steps.py(GEN + "object_edit.py", function (run) { return ["svg-absent", "--svg", svg, "--ids", idsOf(run)]; }, tag("check deleted ids are gone from the render"), { json: "absent" }),
        { t: "fn", label: "deleted ids absent?", fn: function (run) {
          var res = run.vars.absent || {};
          if (res.ok === false) throw new Error("the new map still names " + Object.keys(res.present || {}).join(", ") + ": layers NOT replaced (report this)");
          run.log("render checked: " + (res.checked || []).length + " deleted id(s) absent from the new map");
        } });
    }
    groups.forEach(function (g) {
      var s = VB.replaceSteps(svg, g[1], tag("replace " + g[0]));
      if (g[2]) s.forEach(function (x) { x.when = g[2]; });
      steps = steps.concat(s);
    });
    if (labels) steps = steps.concat(VB.replaceSteps(svg, api.labelLayers(), tag("replace labels (names, halos, leaders)")),
      [VB.steps.host({ action: "set_visible", names: ["Labels - Hidden"], visible: false }, "hide the hidden-labels sublayer", true),
        VB.steps.host({ action: "lock_leaders", locked: (st.label_offset || {}).lock_leaders !== false }, "leaders layer lock", true)]);
    if (fills) {
      var t = tag(opts.fills + " fills");
      var fs = VB.fillsOn && VB.fillsOn(st) ? VB.fullFillSteps(st, d, st.town.fills && st.town.fills.flat !== false ? {} : { only: [opts.fills] })
        : [{ t: "fn", label: "fills", fn: function (run) { return VB.fillStep(st, run); } }];
      fs[0] = Object.assign({}, fs[0], { label: t + " (" + (fs[0].label || "fills") + ")" });
      steps = steps.concat(fs);
    }
    steps.push({ t: "fn", label: "report", fn: function (run) {
      run.log("map updated: " + groups.map(function (g) { return g[0]; }).join(", ") + (labels ? ", labels" : "") + (fills ? ", " + opts.fills + " fills" : "") +
        (opts.note ? ". " + opts.note : "")); } });
    return steps;
  };
  // the Buildings tab refresh: Buildings / Walls / Blocks, region details (only when the place has details.json), labels, building fills
  api.buildingSteps = function (st, d, absentIds) {
    var region = function (run) { return run.exists ? run.exists(d.world + "/details.json") : true; };
    return api.steps(st, d, { svg: d.panel + "/buildings_map.svg", tag: "map", fills: "buildings", absentIds: absentIds,
      groups: [["Buildings, Walls, Blocks", api.BUILDING_LAYERS], ["doors, roofs, lots, fences (Details, DETAILS - Lots, Fences)", api.BUILDING_DETAIL_LAYERS, region]],
      note: "Contours are marked stale (their gaps follow the old footprints): re-render them on the Contours tab." });
  };
  VB.mapRefreshSteps = api.steps;
  VB.MapRefresh = api;
  root.VBMapRefresh = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
