// Buildings tab "Edit buildings" block: list with search / filters and tick boxes, delete / add / move / rotate / resize / duplicate / rename / properties /
// front door / Illustrator footprint sync / undo, map refresh switch. Injects its markup into the Buildings tab (after the Building styles block, before the
// 'Edit selected buildings' overrides block of objects_ui.js), so index.html only needs the script tags (after objects_ui.js, before main.js).
// Logic and jobs: lib/buildedit.js (+ lib/maprefresh.js); Python: generators/object_edit.py building commands -> building_edit.py.
// No window.confirm / alert / prompt (CEP breaks them): deleting needs the 'Yes, delete' tick box.
(function () {
  "use strict";
  var VB = window.VBCore, BE = window.VBBuildEdit, ctx = null, cache = {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var num = function (s, label, step, extra) { return '<label>' + label + ' <input type="number" ' + s + (step ? ' step="' + step + '"' : "") + (extra || "") + "></label>"; };
  var txt = function (s, label, ph, tip) { return '<label title="' + esc(tip || "") + '">' + label + ' <input type="text" ' + s + ' placeholder="' + esc(ph || "") + '"></label>'; };
  var chk = function (s, label, tip) { return '<label class="chk" title="' + esc(tip || "") + '"><input type="checkbox" ' + s + '> ' + label + "</label>"; };
  var KOPTS = (BE ? BE.KINDS : []).map(function (k) { return "<option>" + k + "</option>"; }).join("");

  var HTML = '<h4>Edit buildings <span class="tag" id="beTag"></span></h4>' +
    '<p class="note">Tick buildings (or <b>Tick from Illustrator selection</b>), then use a block below. Every change is backed up first (<code>buildings_backups/</code>): ' +
    '<b>Undo last building change</b> goes back one step per press. With <b>Update the map layers too</b> on, the drawing follows at once (Buildings, Walls, Blocks, doors / roofs / lots, labels, building fills); ' +
    'a delete removes just the deleted buildings&#39; items from the drawing (fast); Blocks, fills and contours are marked stale (Redraw buildings on the map (full) makes them exact). 3D: Foundry tab, Export world pack (3D) and Export split models.</p>' +
    '<div class="btns">' + chk('data-s="bedit.map"', "Update the map layers too (Buildings, Blocks, labels)", "Delete: only the deleted buildings' items are removed from the drawing (fast, no re-render; Blocks / fills / contours marked stale). Other changes: render the place once and replace Buildings, Walls, Blocks, Details, DETAILS - Lots, Fences, the label layers (not contour heights) and the building fills. Off = only the json files change.") +
    chk('data-s="bedit.footprints"', "Keep the Building Footprints layer in step", "After every change: redraw the helper layer 'Building Footprints' (one closed path per building, named by id). Keep on when you edit shapes in Illustrator: a stale layer read back would undo your change.") +
    chk('data-s="bedit.dry"', "Dry run (check only, write nothing)", "Run every check and report what would change; no file is written and the map is not touched") + "</div>" +
    '<div class="grid">' + txt('data-s="bedit.filter"', "Search", "name, id, kind, notes, tags") + '<label>Kind <select id="beFKind" data-s="bedit.fkind"></select></label>' +
    '<label>District <select id="beFDist" data-s="bedit.fdist"></select></label><label>Style <select id="beFStyle" data-s="bedit.fstyle"></select></label>' +
    '<label>Floors <select id="beFFloors" data-s="bedit.ffloors"><option value="">(any)</option>' + [1, 2, 3, 4, 5, 6].map(function (n) { return "<option>" + n + "</option>"; }).join("") + "</select></label></div>" +
    '<div class="btns"><button data-act="be_tick_shown" title="Tick every building the filter shows">Tick shown</button><button data-act="be_tick_none">Tick none</button>' +
    '<button data-act="be_tick_sel" title="Select building shapes (or footprint paths) in Illustrator first; their names are building ids">Tick from Illustrator selection</button>' +
    '<button data-act="be_select_ai" title="Select the ticked buildings in the open drawing and zoom to them">Select in Illustrator</button>' +
    '<button data-act="be_load" title="Fill the Rename, Properties, Move and Resize boxes from the first ticked building">Load ticked into the forms</button></div>' +
    '<div style="max-height:220px;overflow:auto"><table id="beTable"></table></div><div class="note" id="beInfo"></div>' +
    '<div class="btns"><button data-act="be_undo" title="Put back the files of the newest building backup (one step per press)">Undo last building change</button>' +
    '<button data-act="be_map" title="Slow path: render the place and replace Buildings, Walls, Blocks, details, labels and building fills (makes Blocks / fills exact after fast deletes)">Redraw buildings on the map (full)</button></div>' +
    // delete
    '<h4>Delete</h4><div class="btns">' + chk('data-s="bedit.confirmDelete"', "Yes, delete the ticked buildings", "Safety catch: deleting needs this tick. Undo last building change restores them.") +
    '<button data-act="be_del" title="Delete the ticked buildings (json, their doors / roofs / lots / fences in details.json, their label position). Backed up first.">Delete ticked</button></div>' +
    // move / rotate / resize / duplicate
    '<h4>Move, rotate, resize, duplicate</h4>' +
    '<div class="grid">' + num('data-s="bedit.dx"', "Move dx (ft, east +)", "1") + num('data-s="bedit.dy"', "Move dy (ft, south +)", "1") + num('data-s="bedit.toX"', "or to centre x", "0.5") + num('data-s="bedit.toY"', "centre y", "0.5") + "</div>" +
    '<div class="btns">' + chk('data-s="bedit.withLot"', "Lot and fences move too", "Move / rotate also the lot outline and fences of details.json") + '<button data-act="be_move" title="Shift the ticked buildings by dx / dy, or one building to the centre x / y. Interior, doors and roof lines move with it">Move</button></div>' +
    '<div class="grid">' + num('data-s="bedit.deg"', "Rotate (deg, clockwise)", "1", ' min="-360" max="360"') + '</div><div class="btns"><button data-act="be_rotate" title="Turn each ticked building about its own centre">Rotate</button></div>' +
    '<div class="grid">' + num('data-s="bedit.width"', "Width = long side (ft)", "0.5", ' min="6" max="400"') + num('data-s="bedit.depth"', "Depth = short side (ft)", "0.5", ' min="6" max="400"') + num('data-s="bedit.scale"', "or scale", "0.05", ' min="0.1" max="10"') + "</div>" +
    '<div class="btns"><button data-act="be_resize" title="Stretch along the building\'s own axes. The stored interior and details.json doors / roofs are dropped (regenerated at export)">Resize</button></div>' +
    '<div class="grid">' + num('data-s="bedit.dupDx"', "Copy offset x (ft)", "1") + num('data-s="bedit.dupDy"', "Copy offset y (ft)", "1") + '</div><div class="btns"><button data-act="be_dup" title="Copy each ticked building (new id, name + (copy)); the copy gets its interior at export">Duplicate</button></div>' +
    // rename
    '<h4>Rename</h4><div class="grid">' + txt('data-s="bedit.newName"', "New name", "Dyers Hall") + txt('data-s="bedit.newId"', "New id (optional)", "bld_dyers_hall", "Changes the file name and every reference (details.json, label positions, region map). Lower-case, digits, single underscores.") + "</div>" +
    '<div class="btns"><button data-act="be_rename" title="Rename the one ticked building (name and / or id)">Rename</button></div>' +
    // properties
    '<h4>Properties</h4><p class="note">Tick the fields to write (others stay). District <code>auto</code> = the district the footprint lies in, empty = none. Tags: comma list.</p>' +
    '<div id="beProps"></div><div class="btns"><button class="primary" data-act="be_props" title="Write the ticked fields into the ticked buildings">Apply properties</button></div>' +
    // front door
    '<h4>Front door</h4><div class="grid">' + num('data-s="bedit.door.edge"', "Side (0 = first side)", "1", ' min="0"') + num('data-s="bedit.door.pos"', "Position 0..1 along it", "0.05", ' min="0" max="1"') + num('data-s="bedit.door.width"', "Door width (ft, empty = default)", "0.5", ' min="2" max="16"') + "</div>" +
    '<div class="btns"><button data-act="be_door" title="Put the front door of the one ticked building on that side (details.json). The stored interior is dropped and regenerated at export">Set front door</button></div>' +
    // add
    '<h4>Add</h4><div class="grid">' + txt('data-s="bedit.add.name"', "Name", "empty = Kind N") + '<label>Kind <select data-s="bedit.add.kind">' + KOPTS + "</select></label>" + num('data-s="bedit.add.floors"', "Floors", "1", ' min="1" max="12"') +
    num('data-s="bedit.add.cx"', "Centre x (ft)", "0.5") + num('data-s="bedit.add.cy"', "Centre y (ft)", "0.5") + num('data-s="bedit.add.width"', "Width (ft)", "0.5", ' min="6" max="400"') + num('data-s="bedit.add.depth"', "Depth (ft)", "0.5", ' min="6" max="400"') + num('data-s="bedit.add.rotation"', "Rotation (deg)", "1") + "</div>" +
    '<div class="btns"><button data-act="be_add" title="Add a rectangle building with the values above (district by containment)">Add rectangle</button>' +
    '<button data-act="be_add_here" title="Put the centre boxes on the centre of the first ticked building, offset by the copy offset">Centre from ticked</button>' +
    '<button data-act="be_add_sel" title="Each selected CLOSED path in Illustrator becomes a new building (name, kind, floors above)">Add from Illustrator selection</button></div>' +
    // Illustrator sync
    '<h4>Shapes in Illustrator</h4><p class="note"><b>Redraw buildings in Illustrator</b> puts one closed path per building (named by its id) on the layer <code>Building Footprints</code> (replaces only that layer). ' +
    'Edit anchors there, or draw new closed paths, then read them back. Reshaping drops the stored interior (regenerated at export).</p>' +
    '<div class="btns"><button data-act="be_redraw_fp" title="Draw every footprint on the layer Building Footprints (replaces that layer only; cheap)">Redraw buildings in Illustrator</button>' +
    '<button data-act="be_reshape_sel" title="Selected closed paths named by a building id replace that building\'s footprint">Reshape from selection</button>' +
    '<button class="primary" data-act="be_read_all" title="Selected closed paths (or, with nothing selected, every closed path on Building Footprints): named by an id = reshape, others = new buildings">Read buildings from Illustrator</button></div>';

  // [key, label, kind, tick-box attribute, field attribute] (attributes written out so the command-parity test finds every control)
  var PROPS = [["name", "Name", "text", 'data-s="bedit.propsOn.name"', 'data-s="bedit.props.name"'],
    ["kind", "Kind", "kind", 'data-s="bedit.propsOn.kind"', 'data-s="bedit.props.kind"'],
    ["floors", "Floors", "int", 'data-s="bedit.propsOn.floors"', 'data-s="bedit.props.floors"'],
    ["district", "District", "district", 'data-s="bedit.propsOn.district"', 'data-s="bedit.props.district"'],
    ["status", "Status", "status", 'data-s="bedit.propsOn.status"', 'data-s="bedit.props.status"'],
    ["owner", "Owner", "text", 'data-s="bedit.propsOn.owner"', 'data-s="bedit.props.owner"'],
    ["tags", "Tags", "text", 'data-s="bedit.propsOn.tags"', 'data-s="bedit.props.tags"'],
    ["notes", "Notes", "text", 'data-s="bedit.propsOn.notes"', 'data-s="bedit.props.notes"'],
    ["description", "Description", "text", 'data-s="bedit.propsOn.description"', 'data-s="bedit.props.description"']];
  function propsHtml() {
    return '<div class="grid">' + PROPS.map(function (p) {
      var k = p[0], c = '<label class="chk"><input type="checkbox" ' + p[3] + '> ' + p[1] + "</label>", f;
      if (p[2] === "kind") f = '<select data-s="bedit.props.kind">' + KOPTS + "</select>";
      else if (p[2] === "district") f = '<select id="bePDist" data-s="bedit.props.district"></select>';
      else if (p[2] === "status") f = '<select data-s="bedit.props.status"><option>proposed</option><option>canon</option><option>built</option><option>ruined</option></select>';
      else if (p[2] === "int") f = '<input type="number" min="1" max="12" step="1" data-s="bedit.props.floors">';
      else f = '<input type="text" ' + p[4] + '>';
      return '<div>' + c + f + "</div>";
    }).join("") + "</div>";
  }
  function mount() {
    var sec = $("tab-buildings");
    if (!sec || $("beWrap")) return;
    var d = document.createElement("div"); d.id = "beWrap"; d.innerHTML = HTML;
    var before = $("objBWrap");
    if (before && before.parentNode === sec) sec.insertBefore(d, before); else sec.appendChild(d);
    $("beProps").innerHTML = propsHtml();
  }
  mount();

  function B() { return ctx.state().bedit; }
  function buildings() {
    if (cache.rows) return cache.rows;
    var dir = ctx.dirs().world + "/buildings", out = [];
    try {
      ctx.fs.readdirSync(dir).forEach(function (f) {
        if (!/\.json$/.test(f)) return;
        var j = ctx.readJson(dir + "/" + f, null); if (!j || !j.id) return;
        var p = (j.geometry && j.geometry.points) || [], cx = 0, cy = 0;
        p.forEach(function (q) { cx += q[0]; cy += q[1]; });
        out.push({ id: j.id, name: j.name || "", kind: j.kind || "", floors: j.floors || 1, district: j.district || "", style: j.style || "", notes: j.notes || "", owner: j.owner || "",
          description: j.description || "", tags: j.tags || [], status: j.status || "", area: p.length > 2 && VB.polyArea ? Math.round(VB.polyArea(p)) : 0,
          center: p.length ? [Math.round(cx / p.length * 10) / 10, Math.round(cy / p.length * 10) / 10] : null });
      });
    } catch (e) { /* no buildings folder */ }
    out.sort(function (a, b) { return a.id < b.id ? -1 : 1; });
    cache.rows = out; return out;
  }
  function districts() { var j = ctx.readJson(ctx.dirs().world + "/districts.json", { districts: [] }); return (j.districts || []).map(function (e) { return e.id; }); }
  function backups() { try { return ctx.fs.readdirSync(ctx.dirs().world + "/buildings_backups").length; } catch (e) { return 0; } }
  function setOpts(el, opts, val) {
    if (!el) return;
    var html = opts.map(function (o) { return '<option value="' + esc(o[0]) + '">' + esc(o[1]) + "</option>"; }).join("");
    if (el.getAttribute("data-built") !== html) { el.innerHTML = html; el.setAttribute("data-built", html); }
    el.value = val == null ? "" : String(val);
  }
  function paint() {
    if (!ctx || !$("beTable")) return;
    var b = B(); if (!b) return;
    var rows = buildings(), ds = districts(), ticked = {};
    ((ctx.state().styles || {}).ids || []).forEach(function (i) { ticked[i] = 1; });
    var uniq = function (f) { return Array.from(new Set(rows.map(f).filter(function (x) { return x !== ""; }))).sort(); };
    setOpts($("beFKind"), [["", "(any)"]].concat(uniq(function (r) { return r.kind; }).map(function (k) { return [k, k]; })), b.fkind);
    setOpts($("beFDist"), [["", "(any)"], ["(none)", "(none)"]].concat(ds.map(function (k) { return [k, k]; })), b.fdist);
    setOpts($("beFStyle"), [["", "(any)"]].concat(uniq(function (r) { return r.style || "(legacy)"; }).map(function (k) { return [k, k]; })), b.fstyle);
    setOpts($("bePDist"), [["auto", "auto (by containment)"], ["", "(none: clear)"]].concat(ds.map(function (k) { return [k, k]; })), b.props.district);
    var shown = BE.filterRows(rows, b);
    $("beTable").innerHTML = "<tr><th></th><th>id</th><th>name</th><th>kind</th><th>fl</th><th>district</th><th>style</th><th>sq ft</th></tr>" + shown.map(function (r) {
      return '<tr title="' + esc((r.notes ? "notes: " + r.notes + "  " : "") + (r.tags.length ? "tags: " + r.tags.join(", ") : "") + (r.center ? "  centre " + r.center.join(", ") : "")) + '"><td><input type="checkbox" data-beid="' + esc(r.id) + '"' + (ticked[r.id] ? " checked" : "") + "></td><td>" + esc(r.id) + "</td><td>" + esc(r.name) +
        "</td><td>" + esc(r.kind) + "</td><td>" + r.floors + "</td><td>" + esc(r.district) + "</td><td>" + esc(r.style || "(legacy)") + "</td><td>" + r.area + "</td></tr>";
    }).join("");
    $("beTag").textContent = rows.length + " buildings";
    var last = b.last ? "   last: " + b.last.kind + (b.last.dry ? " (dry run)" : "") + (b.last.warnings ? ", " + b.last.warnings + " warning(s) in the log" : "") : "";
    $("beInfo").textContent = BE.summary(rows, (ctx.state().styles || {}).ids) + "; " + shown.length + " shown; " + backups() + " backup(s) to undo" + last;
  }
  function repaintAll() { cache = {}; paint(); if (window.VBStylesUI) window.VBStylesUI.paint(); if (window.VBObjectsUI) window.VBObjectsUI.paint(); }
  function go(make) {
    try { if (ctx.showError) ctx.showError(""); return ctx.startJob(make(), repaintAll); } catch (e) { if (ctx.showError) ctx.showError(String(e.message || e)); }
  }
  function op(name) { return function () { return go(function () { return BE.job(name, ctx.state(), ctx.dirs()); }); }; }
  function setIds(x, src) { var s = ctx.state().styles; s.ids = x; s.ids_src = src; s.target = "selected"; ctx.save(); repaintAll(); }
  function load() {
    var id = ((ctx.state().styles || {}).ids || [])[0], b = B();
    var r = buildings().filter(function (x) { return x.id === id; })[0];
    if (!r) { if (ctx.showError) ctx.showError("tick a building first"); return; }
    b.newName = r.name; b.newId = r.id; b.toX = r.center ? r.center[0] : ""; b.toY = r.center ? r.center[1] : "";
    b.props = { name: r.name, kind: r.kind, floors: r.floors, district: r.district || "auto", notes: r.notes, description: r.description, owner: r.owner, tags: r.tags.join(", "), status: r.status || "proposed" };
    ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); else syncInputs(); paint();
  }
  function syncInputs() {
    var host = $("beWrap"); if (!host) return;
    Array.prototype.forEach.call(host.querySelectorAll("[data-s]"), function (el) {
      if (document.activeElement === el) return;
      var v = VB.getPath(ctx.state(), el.getAttribute("data-s"));
      if (el.type === "checkbox") el.checked = !!v; else el.value = v == null ? "" : v;
    });
  }
  var A = {
    be_del: op("delete"), be_add: op("add"), be_move: op("move"), be_rotate: op("rotate"), be_resize: op("resize"), be_dup: op("duplicate"),
    be_rename: op("rename"), be_props: op("props"), be_door: op("door"), be_undo: op("undo"),
    be_add_sel: function () { return go(function () { return BE.jobFromPaths(ctx.state(), ctx.dirs(), "add"); }); },
    be_reshape_sel: function () { return go(function () { return BE.jobFromPaths(ctx.state(), ctx.dirs(), "reshape"); }); },
    be_read_all: function () { return go(function () { return BE.jobFromPaths(ctx.state(), ctx.dirs(), "sync"); }); },
    be_redraw_fp: function () { return go(function () { return BE.jobRedrawFootprints(ctx.state(), ctx.dirs()); }); },
    be_map: function () { return go(function () { return BE.jobRefreshMap(ctx.state(), ctx.dirs()); }); },
    be_select_ai: function () { return go(function () { return BE.jobSelectInIllustrator(ctx.state()); }); },
    be_tick_sel: function () { return go(function () { return BE.jobFromSelection(ctx.state(), buildings().map(function (r) { return r.id; })); }); },
    be_tick_shown: function () { setIds(BE.filterRows(buildings(), B()).map(function (r) { return r.id; }), "filter (" + BE.filterRows(buildings(), B()).length + ")"); },
    be_tick_none: function () { setIds([], ""); },
    be_load: load,
    be_add_here: function () {
      var id = ((ctx.state().styles || {}).ids || [])[0], r = buildings().filter(function (x) { return x.id === id; })[0], b = B();
      if (!r || !r.center) { if (ctx.showError) ctx.showError("tick a building first"); return; }
      b.add.cx = Math.round((r.center[0] + (+b.dupDx || 0)) * 10) / 10; b.add.cy = Math.round((r.center[1] + (+b.dupDy || 0)) * 10) / 10;
      ctx.save(); syncInputs();
    }
  };
  function init(c) {
    ctx = c;
    if (!BE || !$("beWrap")) return;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var host = $("beWrap");
    host.addEventListener("input", function (ev) { if (ev.target.closest('[data-s^="bedit.f"]')) paint(); });
    host.addEventListener("change", function (ev) { if (ev.target.closest('[data-s^="bedit.f"]')) paint(); });
    $("beTable").addEventListener("change", function (ev) {
      var cb = ev.target.closest("input[data-beid]"); if (!cb) return;
      var id = cb.getAttribute("data-beid"), x = ((ctx.state().styles || {}).ids || []).filter(function (i) { return i !== id; });
      if (cb.checked) x.push(id);
      setIds(x, "");
    });
    paint();
  }
  window.VBBuildEditUI = { init: init, paint: function () { cache = {}; paint(); }, actions: A, mount: mount };
})();
