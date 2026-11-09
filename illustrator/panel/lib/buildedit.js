// Buildings tab "Edit buildings" block for VBCore: defaults, list filter, argument builders and jobs (delete / add / move / rotate / resize / duplicate / rename /
// properties / front door / Illustrator footprint sync / undo), each followed by the map refresh (lib/maprefresh.js) when 'Update the map layers too' is on.
// Pure logic, no DOM: also loaded by test/test_buildedit_jobs.js. Python: generators/object_edit.py building commands (logic in building_edit.py).
// The ticked buildings are st.styles.ids (the same ticks as the Building styles list).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var MR = root.VBMapRefresh || (typeof require !== "undefined" ? require("./maprefresh.js") : null);
  var GEN = "illustrator/generators/", OE = GEN + "object_edit.py";
  var api = {};
  api.LAYER = "Building Footprints";
  api.KINDS = ["house", "farmhouse", "shop", "inn", "tavern", "barn", "shed", "stable", "craft", "workshop", "smithy", "mill", "warehouse", "civic", "hall", "temple", "church", "tower", "gatehouse"];
  api.PROPS = ["name", "kind", "floors", "district", "notes", "description", "owner", "tags", "status"];
  api.defaults = function () {
    var on = {}; api.PROPS.forEach(function (k) { on[k] = false; });
    return { filter: "", fkind: "", fdist: "", fstyle: "", ffloors: "", dx: 0, dy: 0, toX: "", toY: "", deg: 15, width: "", depth: "", scale: "", withLot: false,
      dupDx: 20, dupDy: 20, newId: "", newName: "", props: { name: "", kind: "house", floors: 1, district: "auto", notes: "", description: "", owner: "", tags: "", status: "proposed" },
      propsOn: on, add: { name: "", kind: "house", cx: "", cy: "", width: 20, depth: 16, rotation: 0, floors: 1 }, door: { edge: 0, pos: 0.5, width: "" },
      map: true, footprints: true, confirmDelete: false, dry: false, last: null };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var s = baseDefaults(); s.bedit = api.defaults(); return s; };

  // ---- list filter (pure): rows = building-info rows; f = st.bedit
  api.filterRows = function (rows, f) {
    var q = String(f.filter || "").toLowerCase().trim();
    return (rows || []).filter(function (b) {
      if (f.fkind && b.kind !== f.fkind) return false;
      if (f.fdist && (b.district || "") !== (f.fdist === "(none)" ? "" : f.fdist)) return false;
      if (f.fstyle && (b.style || "(legacy)") !== f.fstyle) return false;
      if (f.ffloors !== "" && f.ffloors != null && +b.floors !== +f.ffloors) return false;
      if (!q) return true;
      return [b.id, b.name, b.kind, b.district, b.style, b.notes, b.owner, (b.tags || []).join(" ")].join(" ").toLowerCase().indexOf(q) >= 0;
    });
  };
  api.summary = function (rows, ticked) {
    var k = {}; (rows || []).forEach(function (b) { k[b.kind || "?"] = (k[b.kind || "?"] || 0) + 1; });
    return (rows || []).length + " buildings (" + Object.keys(k).sort().map(function (x) { return k[x] + " " + x; }).join(", ") + "), " + (ticked || []).length + " ticked";
  };

  function ids(st, min, max, what) {
    var x = ((st.styles && st.styles.ids) || []).slice();
    if (x.length < min) throw new Error(what + ": tick " + (min > 1 ? "at least " + min + " buildings" : "a building") + " in the Edit buildings list first");
    if (max && x.length > max) throw new Error(what + ": tick exactly " + (max === 1 ? "one building" : max + " buildings") + " (" + x.length + " ticked)");
    return x;
  }
  function num(v, what, lo, hi) {
    if (v === "" || v == null || !isFinite(+v)) throw new Error(what + ": enter a number");
    v = +v; if ((lo != null && v < lo) || (hi != null && v > hi)) throw new Error(what + " must be " + lo + ".." + hi);
    return v;
  }
  function has(v) { return v !== "" && v != null; }
  function base(cmd, st) { var a = [cmd, "--place", st.place]; if (st.bedit.dry) a.push("--dry"); return a; }

  // ---- argument builders (throw a plain message on a bad form; nothing runs then)
  api.args = {
    "delete": function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Delete");
      if (!b.confirmDelete && !b.dry) throw new Error("tick 'Yes, delete the ticked buildings' first (Undo last building change restores them)");
      return base("delete-building", st).concat(["--ids", x.join(",")]);
    },
    add: function (st) {
      var a = st.bedit.add, r = base("add-building", st);
      if (a.name && String(a.name).trim()) r.push("--name", String(a.name).trim());
      if (api.KINDS.indexOf(a.kind) < 0) throw new Error("kind must be one of " + api.KINDS.join(", "));
      return r.concat(["--kind", a.kind, "--floors", String(num(a.floors, "Floors", 1, 12) | 0), "--center", num(a.cx, "Centre x") + "," + num(a.cy, "Centre y"),
        "--width", String(num(a.width, "Width", 6, 400)), "--depth", String(num(a.depth, "Depth", 6, 400)), "--rotation", String(num(a.rotation || 0, "Rotation", -360, 360))]);
    },
    move: function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Move"), r = base("move-building", st).concat(["--ids", x.join(",")]);
      if (has(b.toX) && has(b.toY)) {
        if (x.length !== 1) throw new Error("Move to a centre: tick exactly one building (or clear the 'to' boxes and use dx / dy)");
        r.push("--to", num(b.toX, "to x") + "," + num(b.toY, "to y"));
      } else {
        var dx = num(b.dx || 0, "dx", -5000, 5000), dy = num(b.dy || 0, "dy", -5000, 5000);
        if (!dx && !dy) throw new Error("Move: enter dx and / or dy (feet), or a new centre");
        r.push("--dx", String(dx), "--dy", String(dy));
      }
      if (b.withLot) r.push("--with-lot");
      return r;
    },
    rotate: function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Rotate"), deg = num(b.deg, "Degrees", -360, 360);
      if (!deg) throw new Error("Rotate: enter degrees (not 0)");
      return base("rotate-building", st).concat(["--ids", x.join(","), "--deg", String(deg)], b.withLot ? ["--with-lot"] : []);
    },
    resize: function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Resize"), r = base("resize-building", st).concat(["--ids", x.join(",")]);
      if (has(b.scale)) {
        if (has(b.width) || has(b.depth)) throw new Error("Resize: use the scale box OR width / depth (clear the others)");
        return r.concat(["--scale", String(num(b.scale, "Scale", 0.1, 10))]);
      }
      if (!has(b.width) && !has(b.depth)) throw new Error("Resize: enter a width and / or depth (ft), or a scale");
      if (has(b.width)) r.push("--width", String(num(b.width, "Width", 6, 400)));
      if (has(b.depth)) r.push("--depth", String(num(b.depth, "Depth", 6, 400)));
      return r;
    },
    duplicate: function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Duplicate");
      return base("duplicate-building", st).concat(["--ids", x.join(","), "--dx", String(num(b.dupDx, "Offset x", -5000, 5000)), "--dy", String(num(b.dupDy, "Offset y", -5000, 5000))]);
    },
    rename: function (st) {
      var b = st.bedit, x = ids(st, 1, 1, "Rename"), r = base("rename-building", st).concat(["--ids", x[0]]);
      var nid = String(b.newId || "").trim(), nm = String(b.newName || "").trim();
      if (!nid && !nm) throw new Error("Rename: enter a new name and / or a new id");
      if (nid && !/^bld_[a-z0-9]+(_[a-z0-9]+)*$/.test(nid)) throw new Error("new id must look like bld_dyers_hall (lower-case letters, digits, single underscores)");
      if (nid === x[0] && !nm) throw new Error("Rename: the new id is the current id; nothing changes");
      if (nid && nid !== x[0]) r.push("--new-id", nid);
      if (nm) r.push("--name", nm);
      return r;
    },
    props: function (st) {
      var b = st.bedit, x = ids(st, 1, 0, "Properties"), r = base("set-building-props", st).concat(["--ids", x.join(",")]), n = 0;
      api.PROPS.forEach(function (k) {
        if (!b.propsOn[k]) return;
        var v = b.props[k];
        if (k === "name" && x.length > 1) throw new Error("Properties: a name is for one building (tick one, or untick Name)");
        if (k === "floors") v = String(num(v, "Floors", 1, 12) | 0);
        if (k === "kind" && api.KINDS.indexOf(v) < 0) throw new Error("kind must be one of " + api.KINDS.join(", "));
        r.push("--" + k, v == null ? "" : String(v)); n++;
      });
      if (!n) throw new Error("Properties: tick at least one field (the box left of its name)");
      return r;
    },
    door: function (st) {
      var b = st.bedit.door, x = ids(st, 1, 1, "Front door"), r = base("set-door", st).concat(["--ids", x[0], "--edge", String(num(b.edge, "Side", 0, 199) | 0),
        "--pos", String(num(b.pos, "Position", 0, 1))]);
      if (has(b.width)) r.push("--door-width", String(num(b.width, "Door width", 2, 16)));
      return r;
    },
    undo: function (st) { return ["restore-buildings", "--place", st.place].concat(st.bedit.dry ? ["--dry"] : []); }
  };

  // ---- jobs
  function report(kind) {
    return { t: "fn", label: "report", fn: function (run) {
      var r = run.vars.edit || {};
      (r.warnings || []).forEach(function (w) { run.log("WARN " + w); });
      run.log((r.dry ? "DRY RUN (nothing written): " : "") + kind + ": " + JSON.stringify({ changed: r.changed, added: r.added, deleted: r.deleted, renamed: r.renamed, restored: r.restored, files: r.files, backup: r.backup }));
      run.setState("bedit.last", { kind: kind, dry: !!r.dry, count: r.count || (r.files || []).length || 0, warnings: (r.warnings || []).length, at: new Date().toISOString() });
    } };
  }
  // footprints helper layer: draw-buildings -> replace that layer only (cheap)
  api.footprintSteps = function (st, d, label) {
    var svg = d.panel + "/building_footprints.svg", view = d.panel + "/building_view.json";
    return [VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
      { t: "fn", label: "write view", fn: async function (run) { await run.writeJson(view, run.vars.view); } },
      VB.steps.py(OE, ["draw-buildings", "--place", st.place, "--view-file", view, "--out", svg], "draw-buildings", { json: "drawn" })]
      .concat(VB.replaceSteps(svg, [api.LAYER], label || "draw footprints"));
  };
  // append the refresh (map layers + footprints layer) to a writing job; nothing is refreshed on a dry run
  function finish(job, st, d, absentIds) {
    var b = st.bedit;
    if (b.dry) { job.steps.push({ t: "fn", label: "note", fn: function (run) { run.log("dry run: nothing written, map not touched"); } }); return job; }
    if (b.map !== false && d) {
      job.steps = job.steps.concat(MR.buildingSteps(st, d, absentIds));
      job.setStale = (job.setStale || []).concat(["contours"]);
      job.params = Object.assign({}, job.params, { map: true });
    } else job.steps.push({ t: "fn", label: "note", fn: function (run) { run.log("map layers NOT updated ('Update the map layers too' is off): Generate town / Redraw all GEN layers shows the change"); } });
    if (b.footprints !== false && d) job.steps = job.steps.concat(api.footprintSteps(st, d, "update the Building Footprints layer"));
    return job;
  }
  // ---- fast delete: remove only the deleted buildings' items from the drawing (no render, no whole-layer replace). Uses lib/itemops.js
  // VB.deleteItemsSteps(ids, "building") when loaded; else the host action delete_items {ids, layers}. When that action is missing / fails, the full
  // map refresh runs instead (slow path). Blocks, fills and contours are marked stale, not redrawn.
  api.DELETE_LAYERS = ["Buildings", "Walls", "Labels - Buildings", "Labels - Hidden", "Label Backing", "Leaders", "Leader Anchors", "DETAILS - Lots", "Details", "Fences", "ART - Fill Shapes", api.LAYER];
  function fastDelete(job, st, d, x) {
    var steps = [];
    if (VB.deleteItemsSteps) {
      steps = VB.deleteItemsSteps(x, "building").map(function (s) { return Object.assign({}, s, { optional: true }); });
      steps.push({ t: "fn", label: "fast delete result", fn: function (run) { var r = run.last || {}; run.vars.fastFail = r.ok === false; } });
    } else {
      steps.push({ t: "fn", label: "map: delete the buildings' items (delete_items)", fn: async function (run) {
        var r = null;
        try { r = await run.host({ action: "delete_items", ids: x, layers: api.DELETE_LAYERS, timeout_ms: 60000 }, true); } catch (e) { r = { ok: false, error: String(e.message || e) }; }
        run.vars.fastFail = !r || !r.ok;
        if (run.vars.fastFail) run.log("fast delete not available (" + ((r && r.error) || "no reply") + "): full map refresh instead");
        else run.log("map: " + (r.deleted != null ? r.deleted : "?") + " item(s) of " + x.length + " building(s) removed from the drawing");
      } });
    }
    var full = MR.buildingSteps(st, d, x).concat(st.bedit.footprints !== false ? api.footprintSteps(st, d, "update the Building Footprints layer") : []).map(function (s) {
      var w = s.when; return Object.assign({}, s, { when: function (run) { return !!run.vars.fastFail && (!w || w(run)); } });
    });
    job.steps = job.steps.concat(steps, full, [{ t: "fn", label: "note", fn: function (run) {
      if (!run.vars.fastFail) run.log("Blocks, fills and contours were not redrawn (marked stale): 'Redraw buildings on the map (full)' when you want them exact"); } }]);
    job.setStale = (job.setStale || []).concat(["contours"]);
    job.params = Object.assign({}, job.params, { map: "fast" });
    return job;
  }
  var LABELS = { "delete": "Delete buildings", add: "Add building", move: "Move buildings", rotate: "Rotate buildings", resize: "Resize buildings", duplicate: "Duplicate buildings",
    rename: "Rename building", props: "Building properties", door: "Set front door", undo: "Undo last building change" };
  api.job = function (op, st, d) {
    var args = api.args[op](st);                 // throws before anything runs
    var steps = [VB.steps.py(OE, args, args[0], { json: "edit" }), report(op)];
    if (op === "delete") steps.push({ t: "fn", label: "untick", fn: function (run) { if (!(run.vars.edit || {}).dry) { run.setState("styles.ids", []); run.setState("bedit.confirmDelete", false); } } });
    if (op === "rename") steps.push({ t: "fn", label: "tick the new id", fn: function (run) { var m = (run.vars.edit || {}).renamed || {}; var k = Object.keys(m)[0]; if (k && !(run.vars.edit || {}).dry) run.setState("styles.ids", [m[k]]); } });
    if (op === "add" || op === "duplicate") steps.push({ t: "fn", label: "tick the new building(s)", fn: function (run) { var r = run.vars.edit || {}; if (!r.dry && r.added) run.setState("styles.ids", r.added); } });
    var absent = op === "delete" ? function (run) { var r = run.vars.edit || {}; return r.deleted || []; } : null;
    var job0 = { kind: "bedit_" + op, label: LABELS[op] + (st.bedit.dry ? " (dry run)" : ""), params: { op: op, args: args }, steps: steps };
    if (op === "delete" && !st.bedit.dry && st.bedit.map !== false && d) return fastDelete(job0, st, d, args[args.indexOf("--ids") + 1].split(","));
    // TODO(itemops): move / rotate / resize / add / rename should update or append only the changed items once lib/itemops.js offers update / append steps
    return finish({ kind: "bedit_" + op, label: LABELS[op] + (st.bedit.dry ? " (dry run)" : ""), params: { op: op, args: args }, steps: steps }, st, d, absent);
  };
  // Illustrator closed paths -> buildings. mode add (every selected closed path becomes a new building: name / kind / floors of the Add form),
  // reshape (paths named by a building id replace its footprint), sync (both; nothing selected = every closed path on the Building Footprints layer)
  api.jobFromPaths = function (st, d, mode) {
    var a = st.bedit.add, file = d.panel + "/building_paths.json";
    if (api.KINDS.indexOf(a.kind) < 0) throw new Error("kind must be one of " + api.KINDS.join(", "));
    var args = ["apply-building-paths", "--place", st.place, "--file", file, "--mode", mode, "--kind", a.kind, "--floors", String(num(a.floors, "Floors", 1, 12) | 0)];
    if (a.name && String(a.name).trim()) args.push("--name", String(a.name).trim());
    if (st.bedit.dry) args.push("--dry");
    var label = { add: "Add buildings from the Illustrator selection", reshape: "Reshape buildings from the Illustrator selection", sync: "Read buildings from Illustrator" }[mode];
    var steps = [VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
      VB.steps.host({ action: "get_selection", layer: api.LAYER, closed_only: true }, "read selection"),
      { t: "fn", label: "convert to feet + write", fn: async function (run) {
        var sel = run.last, view = run.vars.view;
        var paths = (sel.paths || []).map(function (p) { return { name: p.name || "", closed: !!p.closed, points: VB.pathToFt(view, sel.artboard, p) }; });
        if (!paths.length) throw new Error("no closed path selected (or on the layer " + api.LAYER + ")");
        run.log(paths.length + " closed path(s) from " + sel.source);
        await run.writeJson(file, { paths: paths }); } },
      VB.steps.py(OE, args, "apply-building-paths", { json: "edit" }), report("paths_" + mode),
      { t: "fn", label: "tick", fn: function (run) { var r = run.vars.edit || {}; if (!r.dry) run.setState("styles.ids", (r.changed || []).concat(r.added || [])); } }];
    return finish({ kind: "bedit_paths_" + mode, label: label, params: { mode: mode }, steps: steps }, st, d, null);
  };
  api.jobRedrawFootprints = function (st, d) {
    return { kind: "bedit_footprints", label: "Redraw buildings in Illustrator", params: {},
      steps: api.footprintSteps(st, d).concat([{ t: "fn", label: "report", fn: function (run) { run.log(((run.vars.drawn || {}).buildings || 0) + " footprint(s) drawn on layer '" + api.LAYER + "'"); } }]) };
  };
  api.jobRefreshMap = function (st, d) {
    return { kind: "bedit_map", label: "Update the map layers (buildings)", params: {}, steps: MR.buildingSteps(st, d, null), setStale: ["contours"] };
  };
  api.jobSelectInIllustrator = function (st) {
    var x = ids(st, 1, 0, "Select in Illustrator");
    return { kind: "bedit_select", label: "Select buildings in Illustrator", params: { ids: x },
      steps: [VB.steps.host({ action: "focus_items", names: x }, "select + zoom"), { t: "fn", label: "report", fn: function (run) { run.log(((run.last || {}).found || 0) + " of " + x.length + " found"); } }] };
  };
  api.jobFromSelection = function (st, known) {
    return { kind: "bedit_tick_selection", label: "Tick buildings from the Illustrator selection", params: {},
      steps: [VB.steps.host({ action: "get_selection" }, "read selection"),
        { t: "fn", label: "map to building ids", fn: function (run) {
          var x = VB.objectsRoadIdsFromSelection ? VB.objectsRoadIdsFromSelection(run.last, known) : [];
          if (!x.length) throw new Error("none of the selected items is named like a building id (bld_house_041 ...)");
          run.setState("styles.ids", x); run.setState("styles.target", "selected"); run.setState("styles.ids_src", "Illustrator selection (" + x.length + ")");
          run.log(x.length + " building(s): " + x.join(", ")); } }] };
  };
  VB.BuildEdit = api;
  root.VBBuildEdit = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
