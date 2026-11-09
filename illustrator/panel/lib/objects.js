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
    ["lamps.on", "lamps.on", "bool3", 0, 0, 0, "Street lamps on this road", "yes = lamps on this road even when its class is not ticked on the Streetlamps tab, no = never on this road, (default) = the Streetlamps tab decides."],
    ["lamps.style", "lamps.style", "lampstyle", 0, 0, 0, "Street lamps: style", "Lamp style for this road only. (default) = the Streetlamps tab style."],
    ["lamps.spacing_ft", "lamps.spacing_ft", "num", 8, 400, 5, "Street lamps: spacing (ft)", "Distance between lamps along this road. Empty = the Streetlamps tab spacing."],
    ["grade.cutfill", "grade.cutfill", "bool3", 0, 0, 0, "Grading: cut/fill terrain", "yes = cut/fill the ground under this road only, no = never for this road, (default) = the global Cut/fill switch."]
  ];
  VB.objectsDefaults = function () {
    var b = { floors: F(1), interior_style: F(""), roof_type: F("gable"), roof_pitch: F(0.6), roof_overhang_ft: F(1), roof_material: F(""), wall_material: F(""), no_windows: F("true"), keep_individual: F("true") };
    var r = { "class": F("lane"), width_ft: F(16), surface: F(""), kerb: F("true"), "grade.smooth": F(0.5), "grade.max_grade_deg": F(14), "grade.cross_deg": F(10), "grade.cutfill": F("true"), "lamps.on": F("true"), "lamps.style": F(""), "lamps.spacing_ft": F(60) };
    // nr: Roads tab geometry block (Add / Reshape / Redraw): name, class and width for NEW roads, simplify tolerance and smoothing for reshape, split vertex
    // map / mapLabels / mapFills: Road shape block 'Update the map layers too' (after every road change, and on Redraw roads in Illustrator)
    return { b: b, r: r, rids: [], rids_src: "", rfilter: "", last: null, nr: { name: "", kind: "lane", width: 14, simplify: 1, smooth: 0, splitAt: 1, confirmDelete: false,
      map: true, mapLabels: true, mapFills: true } };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.objects = VB.objectsDefaults(); return s; };

  // road ids from the names of the selected Illustrator paths (render_world names road items by the street id, e.g. str_008, with suffixes such as _casing)
  VB.objectsRoadIdsFromSelection = function (sel, known) {
    var ids = [], seen = {}, byLen = (known || []).slice().sort(function (x, y) { return y.length - x.length; });
    ((sel && sel.paths) || []).forEach(function (p) {      // same rule as road_edit.road_id_from_name: longest id that is the whole name or followed by _ / space / -
      var n = String(p.name || "").replace(/_x5F_/g, "_").trim(), hit = null;
      for (var i = 0; i < byLen.length && !hit; i++) { var k = byLen[i]; if (n === k || (n.indexOf(k) === 0 && "_ -".indexOf(n.charAt(k.length)) >= 0)) hit = k; }
      if (hit && !seen[hit]) { seen[hit] = 1; ids.push(hit); }
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
          { t: "py", label: "object_edit", script: GEN + "object_edit.py", args: function (run) { return run.vars.args.concat(VB.extraArgs ? VB.extraArgs(st, "object-edit") : []); }, json: "edit" },
          { t: "fn", label: "remember", fn: function (run) { var r = run.vars.edit || {}; run.setState("objects.last", { kind: kind, count: r.count, at: new Date().toISOString() }); run.log((r.count || 0) + " object(s) changed: " + JSON.stringify(r.set || {})); } }] };
    };
  }
  VB.jobObjectsEditBuildings = editJob("objects_edit_buildings", "Edit selected buildings", VB.objectsBuildingArgs);
  var editRoads = editJob("objects_edit_roads", "Edit selected roads", VB.objectsRoadArgs);
  // a width change moves the 2D road outlines: same map refresh as the Road shape buttons (other fields are 3D only)
  VB.jobObjectsEditRoads = function (st, d) { var j = editRoads(st); return st.objects.r.width_ft && st.objects.r.width_ft.on ? withMap(j, st, d) : j; };
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
  // ---- road geometry (Roads tab): delete / add / reshape from Illustrator paths / simplify / split / join / undo / redraw. Python: road_edit.py via object_edit.py.
  VB.ROAD_LAYER = "Road Centerlines";
  VB.ROAD_KINDS = ["road", "street", "lane", "alley"];
  var OE = GEN + "object_edit.py";
  function roadIds(st, min, what) {
    var ids = (st.objects.rids || []);
    if (ids.length < min) throw new Error(what + ": tick " + (min > 1 ? "at least " + min + " roads" : "a road") + " in the list first");
    return ids.slice();
  }
  function remember(kind) {
    return { t: "fn", label: "remember", fn: function (run) {
      var r = run.vars.edit || {}; run.setState("objects.last", { kind: kind, count: r.count || 0, at: new Date().toISOString() });
      run.log(kind + ": " + JSON.stringify({ changed: r.changed, added: r.added, deleted: r.deleted, backup: r.backup })); } };
  }
  // ---- map refresh: streets.json -> render_world -> the road-dependent layers of the open drawing. Without it only streets.json changes and the drawing keeps the
  // old road outlines (Roads), fills, street names and centrelines. Same render_world arguments as 'Redraw all GEN layers' minus contours (the contour layers are not
  // redrawn here: they are marked stale, re-render them on the Contours tab). Cheapest first, one Illustrator call per group, every host step optional (a failure
  // is a warning, the rest still runs): 1 render, 2 Roads + Blocks, 3 region kerbs / off-map markers (Details, Bounds; region places only), 4 Road Centerlines,
  // 5 labels (all label layers except contour heights, they come from one declutter pass), 6 street fills. replace_layer keeps each layer where it is in the
  // stack and restores its lock (GUIDES parent unlocked / relocked around Bounds).
  VB.ROAD_MAP_LAYERS = ["Roads", "Blocks"];
  VB.ROAD_DETAIL_LAYERS = ["Details", "Bounds"];
  VB.roadMapLabelLayers = function () { return VB.LABEL_LAYERS.filter(function (n) { return n !== "Labels - Elevation"; }); };
  VB.roadMapOn = function (st, d) { return !!d && st.objects.nr.map !== false; };
  VB.roadCenterlineSteps = function (st, d, tag) {
    var svg = d.panel + "/road_centerlines.svg", view = d.panel + "/road_view.json";
    return [VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
      { t: "fn", label: "write view", fn: async function (run) { await run.writeJson(view, run.vars.view); } },
      VB.steps.py(OE, ["draw-roads", "--place", st.place, "--view-file", view, "--out", svg], "draw-roads", { json: "drawn" })]
      .concat(VB.replaceSteps(svg, [VB.ROAD_LAYER], tag || "draw centrelines"));
  };
  VB.roadMapSteps = function (st, d) {
    var nr = st.objects.nr, svg = d.panel + "/roads_map.svg", labels = nr.mapLabels !== false, fills = nr.mapFills !== false && !!st.town.autofill;
    var n = 4 + (labels ? 1 : 0) + (fills ? 1 : 0), k = 0, tag = function (s) { k++; return "map " + k + "/" + n + ": " + s; };
    var region = function (run) { return run.exists(d.world + "/details.json") || run.exists(d.world + "/markers.json"); };
    var args = ["--place", st.place].concat(VB.viewFlags(st), ["--out", svg], VB.srcFlags(st), VB.labelFlags(st));
    var steps = [VB.steps.py(GEN + "render_world.py", args, tag("render roads, blocks and labels (render_world)"))]
      .concat(VB.replaceSteps(svg, VB.ROAD_MAP_LAYERS, tag("replace Roads, Blocks")),
        VB.replaceSteps(svg, VB.ROAD_DETAIL_LAYERS, tag("replace kerbs and off-map markers (Details, Bounds)")).map(function (s) { s.when = region; return s; }),
        VB.roadCenterlineSteps(st, d, tag("replace Road Centerlines")));
    if (labels) steps = steps.concat(VB.replaceSteps(svg, VB.roadMapLabelLayers(), tag("replace street names and the other labels")),
      [VB.steps.host({ action: "set_visible", names: ["Labels - Hidden"], visible: false }, "hide the hidden-labels sublayer", true),
        VB.steps.host({ action: "lock_leaders", locked: (st.label_offset || {}).lock_leaders !== false }, "leaders layer lock", true)]);
    if (fills) {
      var t = tag("road fills"), fs = VB.fillsOn(st) ? VB.fullFillSteps(st, d, st.town.fills.flat !== false ? {} : { only: ["streets"] })
        : [{ t: "fn", label: "fills", fn: function (run) { return VB.fillStep(st, run); } }];
      fs[0] = Object.assign({}, fs[0], { label: t + " (" + (fs[0].label || "fills") + ")" });
      steps = steps.concat(fs);
    }
    steps.push({ t: "fn", label: "report", fn: function (run) {
      run.log("map updated from streets.json: Roads, Blocks, Road Centerlines (" + ((run.vars.drawn || {}).roads || 0) + " roads)" + (labels ? ", labels" : "") + (fills ? ", road fills" : "") +
        ". Contours are marked stale (their street gaps follow the old roads): re-render them on the Contours tab."); } });
    return steps;
  };
  // append the map refresh to a road-changing job when 'Update the map layers too' is on (needs the place folders d)
  function withMap(job, st, d) {
    if (!VB.roadMapOn(st, d)) { job.steps.push({ t: "fn", label: "note", fn: function (run) { run.log("map layers NOT updated ('Update the map layers too' is off): press 'Redraw roads on the map' to remove the old roads from the drawing"); } }); return job; }
    job.steps = job.steps.concat(VB.roadMapSteps(st, d));
    job.setStale = (job.setStale || []).concat(["contours"]);
    job.params = Object.assign({}, job.params, { map: true });
    return job;
  }
  VB.jobRoadsDelete = function (st, d) {
    if (!st.objects.nr.confirmDelete) throw new Error("tick 'Yes, delete the ticked roads' first (Undo last road change restores them)");
    var ids = roadIds(st, 1, "Delete");
    return withMap({ kind: "roads_delete", label: "Delete roads", params: { ids: ids },
      steps: [VB.steps.py(OE, ["delete-road", "--place", st.place, "--ids", ids.join(",")], "delete-road", { json: "edit" }),
        { t: "fn", label: "untick", fn: function (run) { run.setState("objects.rids", []); run.setState("objects.nr.confirmDelete", false); } },
        remember("roads_delete")] }, st, d);
  };
  VB.jobRoadsUndo = function (st, d) {
    return withMap({ kind: "roads_undo", label: "Undo last road change", params: {},
      steps: [VB.steps.py(OE, ["restore-streets", "--place", st.place], "restore-streets", { json: "edit" }),
        { t: "fn", label: "report", fn: function (run) { var r = run.vars.edit || {}; run.log("restored " + r.restored + " (" + (r.restored_files || ["streets.json"]).join(", ") + "); " + r.remaining + " older backup(s) left"); } }] }, st, d);
  };
  // simplify / smooth the existing line of each ticked road
  VB.jobRoadsShape = function (st, d) {
    var nr = st.objects.nr, ids = roadIds(st, 1, "Simplify / smooth");
    if (!(+nr.simplify > 0) && !(+nr.smooth > 0)) throw new Error("set a simplify tolerance (ft) and / or smoothing passes above 0");
    var steps = ids.map(function (id, i) {
      var args = ["set-road-points", "--place", st.place, "--ids", id];
      if (+nr.simplify > 0) args.push("--simplify", String(+nr.simplify));
      if (+nr.smooth > 0) args.push("--smooth", String(Math.round(+nr.smooth)));
      return VB.steps.py(OE, args, "reshape " + id, { json: "edit" + i });
    });
    steps.push({ t: "fn", label: "report", fn: function (run) {
      run.log(ids.map(function (id, i) { var r = run.vars["edit" + i] || {}; return id + " " + r.points_before + " -> " + r.points_after + " pts"; }).join("; "));
      run.setState("objects.last", { kind: "roads_shape", count: ids.length, at: new Date().toISOString() }); } });
    return withMap({ kind: "roads_shape", label: "Simplify / smooth roads", params: { nr: nr, ids: ids }, steps: steps }, st, d);
  };
  VB.jobRoadsSplit = function (st, d) {
    var ids = roadIds(st, 1, "Split");
    if (ids.length !== 1) throw new Error("Split: tick exactly one road");
    return withMap({ kind: "roads_split", label: "Split road", params: { at: st.objects.nr.splitAt },
      steps: [VB.steps.py(OE, ["split-road", "--place", st.place, "--ids", ids[0], "--at", String(Math.round(+st.objects.nr.splitAt))], "split-road", { json: "edit" }), remember("roads_split")] }, st, d);
  };
  VB.jobRoadsJoin = function (st, d) {
    var ids = roadIds(st, 1, "Join");
    if (ids.length !== 2) throw new Error("Join: tick exactly two roads");
    return withMap({ kind: "roads_join", label: "Join two roads", params: { ids: ids },
      steps: [VB.steps.py(OE, ["join-roads", "--place", st.place, "--ids", ids.join(",")], "join-roads", { json: "edit" }),
        { t: "fn", label: "untick", fn: function (run) { run.setState("objects.rids", []); } }, remember("roads_join")] }, st, d);
  };
  // Illustrator paths -> streets.json. mode: "add" (selected open paths become new roads), "reshape" (selected paths named by a road id replace that road's line),
  // "sync" (both; with nothing selected, every open path on the Road Centerlines layer). Page points -> feet with the same mapping as every other capture (panelio view).
  VB.jobRoadsFromPaths = function (st, d, mode) {
    var nr = st.objects.nr, file = d.panel + "/road_paths.json";
    if (VB.ROAD_KINDS.indexOf(nr.kind) < 0) throw new Error("class must be one of " + VB.ROAD_KINDS.join(", "));
    if (!(+nr.width >= 2 && +nr.width <= 120)) throw new Error("width must be 2..120 ft");
    var a = ["apply-paths", "--place", st.place, "--file", file, "--mode", mode, "--kind", nr.kind, "--width", String(+nr.width)];
    if (nr.name && String(nr.name).trim()) a.push("--name", String(nr.name).trim());
    if (+nr.simplify > 0) a.push("--simplify", String(+nr.simplify));
    if (+nr.smooth > 0) a.push("--smooth", String(Math.round(+nr.smooth)));
    return withMap({ kind: "roads_from_paths_" + mode, label: ({ add: "Add roads from the Illustrator selection", reshape: "Reshape roads from the Illustrator selection", sync: "Read road centrelines from Illustrator" })[mode],
      params: { mode: mode, nr: nr },
      steps: [VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        VB.steps.host({ action: "get_selection", layer: VB.ROAD_LAYER, open_only: true }, "read selection"),
        { t: "fn", label: "convert to feet + write", fn: async function (run) {
          var sel = run.last, view = run.vars.view;
          var paths = (sel.paths || []).map(function (p) { return { name: p.name || "", closed: !!p.closed, points: VB.pathToFt(view, sel.artboard, p) }; });
          run.log(paths.length + " open path(s) from " + sel.source);
          await run.writeJson(file, { paths: paths }); } },
        VB.steps.py(OE, a, "apply-paths", { json: "edit" }),
        remember("roads_" + mode)] }, st, d);
  };
  // 'Redraw roads in Illustrator': streets.json -> the helper layer "Road Centerlines" (replaces that layer; read first if you edited it) and, with
  // 'Update the map layers too' on (default), the whole map refresh above, so deleted roads also leave Roads, Blocks, labels and fills.
  VB.jobRoadsRedraw = function (st, d) {
    var map = VB.roadMapOn(st, d);
    return { kind: "roads_redraw", label: map ? "Redraw roads (centrelines + map layers)" : "Redraw road centrelines", params: { map: map },
      steps: map ? VB.roadMapSteps(st, d) : VB.roadCenterlineSteps(st, d).concat([{ t: "fn", label: "report", fn: function (run) {
        run.log(((run.vars.drawn || {}).roads || 0) + " road centreline(s) drawn on layer '" + VB.ROAD_LAYER + "'. The map layers (Roads, Blocks, labels, fills) were NOT updated: tick 'Update the map layers too' or press 'Redraw roads on the map'."); } }]),
      setStale: map ? ["contours"] : [] };
  };
  // 'Redraw roads on the map': the map refresh without any road edit (always, whatever the checkbox says)
  VB.jobRoadsMap = function (st, d) {
    return { kind: "roads_map", label: "Redraw roads on the map", params: { labels: st.objects.nr.mapLabels !== false, fills: st.objects.nr.mapFills !== false },
      steps: VB.roadMapSteps(st, d), setStale: ["contours"] };
  };
})(typeof window !== "undefined" ? window : globalThis);
