// Per-object editing (Buildings tab "Edit selected buildings", Roads tab) for VBCore: defaults, selection -> ids, argument builders, jobs. Pure logic, no DOM:
// also loaded by test/test_objects_jobs.js. Python side: generators/object_edit.py (writes the building json / streets.json `edit` blocks that the 3D exporter
// honours; no edit block = old behaviour).
//
// Every field is {on, v}: on = "apply this field". Number fields: an empty box with "on" ticked clears the override. Boolean/choice fields: value "" = clear.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  var F = function (v) { return { on: false, v: v }; };

  // field table: key -> [cli key, kind, min, max, step, label, tooltip]
  VB.OBJ_BUILDING_FIELDS = [
    ["floors", "floors", "int", 1, 12, 1, "Storeys", "Number of storeys (walls 10 ft each). Refused when the building already has a generated interior for another number of storeys."],
    ["interior_style", "interior_style", "interior", 0, 0, 0, "Interior style", "Furnishing and finish of the generated interior. (default) removes the override: the scene setting / kind default applies."],
    ["roof_type", "roof_type", "roof", 0, 0, 0, "Roof type", "gable or hip. (default) = from the building kind."],
    ["roof_pitch", "roof_pitch", "num", 0.05, 2, 0.05, "Roof pitch", "Rise over run of each roof slope (0.6 is about 31 degrees). Empty = default for the kind."],
    ["roof_overhang_ft", "roof_overhang_ft", "num", 0, 6, 0.25, "Roof overhang (ft)", "How far the roof sticks out past the walls. Empty = 1 ft."],
    ["roof_material", "roof_material", "texture", 0, 0, 0, "Roof material", "Texture of the roof. (default) = the town style's roof for the kind."],
    ["wall_material", "wall_material", "texture", 0, 0, 0, "Wall material", "Texture of the outer walls. (default) = by kind."],
    ["no_windows", "no_windows", "bool", 0, 0, 0, "No windows", "yes = no window holes are cut (doors stay). (default) = windows as before."],
    ["keep_individual", "keep_individual", "bool", 0, 0, 0, "Keep as its own model", "yes = Merge/compress never merges this building into a group file (stays one model, for editing or animating). (default) = merged as usual."]
  ];
  VB.OBJ_ROAD_FIELDS = [
    ["class", "class", "roadclass", 0, 0, 0, "Class", "road, street, lane or alley: picks the surface style and tile size. (default) = from the street kind and width."],
    ["width_ft", "width_ft", "num1", 2, 120, 1, "Width (ft)", "Road width. This is the street's own width key, so the 2D map follows (redraw the town fills). Cannot be cleared."],
    ["surface", "surface", "texture", 0, 0, 0, "Surface material", "Texture of the road surface. (default) = from the class."],
    ["kerb", "kerb", "bool3", 0, 0, 0, "Kerb", "yes = stone kerb bands along both edges, no = none, (default) = as the detail pass decided. Not on bridges."],
    ["grade.smooth", "grade.smooth", "num", 0, 1, 0.05, "Grading: smoothing", "0 follows the raw ground, 1 fully smoothed along the road. Empty = the Roads (3D) setting on the Foundry tab."],
    ["grade.max_grade_deg", "grade.max_grade_deg", "num", 1, 60, 1, "Grading: max grade (deg)", "Steepest slope for this road. Empty = the global value."],
    ["grade.cross_deg", "grade.cross_deg", "num", 0, 45, 1, "Grading: max cross slope (deg)", "Steepest side-to-side tilt of the road surface. Empty = the global value."],
    ["grade.cutfill", "grade.cutfill", "bool3", 0, 0, 0, "Grading: cut/fill terrain", "yes = cut/fill the ground under this road only, no = never for this road, (default) = the global Cut/fill switch."]
  ];
  VB.objectsDefaults = function () {
    var b = { floors: F(1), interior_style: F(""), roof_type: F("gable"), roof_pitch: F(0.6), roof_overhang_ft: F(1), roof_material: F(""), wall_material: F(""), no_windows: F("true"), keep_individual: F("true") };
    var r = { "class": F("lane"), width_ft: F(16), surface: F(""), kerb: F("true"), "grade.smooth": F(0.5), "grade.max_grade_deg": F(14), "grade.cross_deg": F(10), "grade.cutfill": F("true") };
    return { b: b, r: r, rids: [], rids_src: "", rfilter: "", last: null };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.objects = VB.objectsDefaults(); return s; };

  // road ids from the names of the selected Illustrator paths (render_world names road items by the street id, e.g. str_008, with suffixes such as _casing)
  VB.objectsRoadIdsFromSelection = function (sel, known) {
    var ids = [], seen = {}, kn = {};
    (known || []).forEach(function (k) { kn[k] = 1; });
    ((sel && sel.paths) || []).forEach(function (p) {
      var m = /(str_[A-Za-z0-9]+)/.exec(String(p.name || "").replace(/_x5F_/g, "_"));
      if (m && !seen[m[1]] && kn[m[1]]) { seen[m[1]] = 1; ids.push(m[1]); }
    });
    return ids;
  };
  function num(v) { return v === "" || v == null || !isFinite(+v) ? null : +v; }
  // --set / --clear arguments from the ticked fields of one table. Returns {sets, clears, n}
  VB.objectsFieldArgs = function (fields, vals) {
    var a = [], n = 0;
    fields.forEach(function (f) {
      var fl = vals[f[0]]; if (!fl || !fl.on) return;
      n++;
      var k = f[1], kind = f[2], v = fl.v;
      if (kind === "num" || kind === "int") {
        var x = num(v);
        if (x == null) { a.push("--clear", k); return; }
        x = Math.min(f[4], Math.max(f[3], x)); if (kind === "int") x = Math.round(x);
        a.push("--set", k + "=" + x);
      } else if (kind === "num1") {
        var w = num(v); if (w == null) throw new Error(f[6] + ": enter a number");
        a.push("--set", k + "=" + Math.min(f[4], Math.max(f[3], w)));
      } else if (kind === "bool" || kind === "bool3") {
        if (v === "" || v == null) a.push("--clear", k); else a.push("--set", k + "=" + (v === true || v === "true" ? "true" : "false"));
      } else {
        if (v === "" || v == null) a.push("--clear", k); else a.push("--set", k + "=" + v);
      }
    });
    return { args: a, n: n };
  };
  VB.objectsBuildingArgs = function (st) {
    var o = st.objects, ids = (st.styles && st.styles.ids) || [];
    if (!ids.length) throw new Error("no buildings chosen: tick some in the Buildings list or press 'Use Illustrator selection'");
    var r = VB.objectsFieldArgs(VB.OBJ_BUILDING_FIELDS, o.b);
    if (!r.n) throw new Error("tick at least one field to apply (the box left of its name)");
    return ["set-building", "--place", st.place, "--ids", ids.join(",")].concat(r.args);
  };
  VB.objectsRoadArgs = function (st) {
    var o = st.objects, ids = o.rids || [];
    if (!ids.length) throw new Error("no roads chosen: tick some in the list or press 'Use Illustrator selection'");
    var r = VB.objectsFieldArgs(VB.OBJ_ROAD_FIELDS, o.r);
    if (!r.n) throw new Error("tick at least one field to apply (the box left of its name)");
    return ["set-road", "--place", st.place, "--ids", ids.join(",")].concat(r.args);
  };
  function editJob(kind, label, getArgs) {
    return function (st) {
      return { kind: kind, label: label, params: {},
        steps: [{ t: "fn", label: "check fields", fn: function (run) { run.vars.args = getArgs(st); } },
          { t: "py", label: "object_edit", script: GEN + "object_edit.py", args: function (run) { return run.vars.args; }, json: "edit" },
          { t: "fn", label: "remember", fn: function (run) { var r = run.vars.edit || {}; run.setState("objects.last", { kind: kind, count: r.count, at: new Date().toISOString() }); run.log((r.count || 0) + " object(s) changed: " + JSON.stringify(r.set || {})); } }] };
    };
  }
  VB.jobObjectsEditBuildings = editJob("objects_edit_buildings", "Edit selected buildings", VB.objectsBuildingArgs);
  VB.jobObjectsEditRoads = editJob("objects_edit_roads", "Edit selected roads", VB.objectsRoadArgs);
  VB.jobObjectsReset = function (st, which) {
    var ids = which === "road" ? st.objects.rids : st.styles.ids;
    return { kind: "objects_reset_" + which, label: "Reset " + which + " overrides", params: { ids: ids },
      steps: [{ t: "fn", label: "check selection", fn: function () { if (!ids || !ids.length) throw new Error("nothing chosen"); } },
        py(GEN + "object_edit.py", ["reset-" + (which === "road" ? "road" : "building"), "--place", st.place, "--ids", ids.join(",")], "object_edit reset", { json: "edit" }),
        { t: "fn", label: "log", fn: function (run) { run.log(((run.vars.edit || {}).count || 0) + " object(s) reset"); } }] };
  };
  VB.jobRoadsFromSelection = function (st, known) {
    return { kind: "roads_selection", label: "Read roads from the Illustrator selection", params: {},
      steps: [VB.steps.host({ action: "get_selection" }, "read selection"),
        { t: "fn", label: "map to road ids", fn: function (run) {
          var ids = VB.objectsRoadIdsFromSelection(run.last, known);
          if (!ids.length) throw new Error("none of the selected items is named like a street id (str_008 ...)");
          run.setState("objects.rids", ids); run.setState("objects.rids_src", "Illustrator selection (" + ids.length + ")");
          run.log(ids.length + " road(s): " + ids.join(", ")); } }] };
  };
})(typeof window !== "undefined" ? window : globalThis);
