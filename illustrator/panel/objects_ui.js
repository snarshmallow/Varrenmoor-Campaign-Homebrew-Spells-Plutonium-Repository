// Per-object editors UI: "Edit selected buildings" block inside the Buildings tab and the new Roads tab. Injects its own markup (index.html only needs the script
// tags, after styles_ui.js). Logic and jobs: lib/objects.js; Python: generators/object_edit.py. Each field has a tick box ("apply this field"); only ticked fields are written.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, cache = {};
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var O = function () { return ctx.state().objects; };
  var CLASSES = ["road", "street", "lane", "alley"];

  function fieldRow(scope, f) {
    var k = f[0], kind = f[2], id = "of_" + scope + "_" + k.replace(/\./g, "_"), tip = esc(f[7]);
    var chk = '<label class="chk" title="' + tip + '"><input type="checkbox" data-of="' + scope + '" data-k="' + esc(k) + '" data-p="on"> ' + esc(f[6]) + "</label>";
    if (kind === "num" || kind === "num1" || kind === "int") {
      return '<div class="sl" data-row="' + scope + ":" + esc(k) + '">' + chk + '<input type="range" data-of="' + scope + '" data-k="' + esc(k) + '" data-p="v" min="' + f[3] + '" max="' + f[4] + '" step="' + f[5] + '" title="' + tip + '">' +
        '<span class="nb"><input type="number" data-of="' + scope + '" data-k="' + esc(k) + '" data-p="v" min="' + f[3] + '" max="' + f[4] + '" step="' + f[5] + '" title="' + tip + (kind === "num" ? " Empty box = clear (default)." : "") + '"></span></div>';
    }
    return '<div class="sl" data-row="' + scope + ":" + esc(k) + '">' + chk + '<select style="grid-column:2 / 4;min-width:0" data-of="' + scope + '" data-k="' + esc(k) + '" data-p="v" id="' + id + '" title="' + tip + '"></select></div>';
  }
  function fieldsHtml(scope, fields) { return fields.map(function (f) { return fieldRow(scope, f); }).join(""); }

  var BHTML = '<h4>Edit selected buildings <span class="tag" id="objBTag"></span></h4>' +
    '<p class="note">Choose buildings with the tick boxes in the list above (or Use Illustrator selection), tick the fields you want to change, press Apply edits. Only ticked fields are written; ' +
    'the building json gets an <code>edit</code> block (floors and interior style are top-level keys). Then Foundry tab: Export world pack (3D) and Export split models. Reset removes every override of the chosen buildings.</p>' +
    '<div id="objBFields"></div><div class="btns"><button class="primary" data-act="obj_apply_b" title="Write the ticked fields into the chosen buildings">Apply edits</button>' +
    '<button data-act="obj_reset_b" title="Remove every per-building override (edit block and interior style) from the chosen buildings">Reset overrides</button>' +
    '<button data-act="obj_load_b" title="Fill the fields from the first chosen building">Load values of first chosen</button></div><div class="note" id="objBInfo"></div>';
  var RHTML = '<h4>Roads <span class="tag" id="objRTag"></span></h4>' +
    '<p class="note">Edit single roads: choose roads (tick, or Use Illustrator selection after selecting road lines named like str_008), tick the fields to change, Apply. Written to <code>streets.json</code> (width as the street width, the rest in an <code>edit</code> block). ' +
    'Grading overrides replace the global Roads (3D) values (Foundry tab) for these roads only. Then Foundry tab: Export world pack (3D) and Export split models.</p>' +
    '<div class="btns"><button data-act="obj_r_sel" title="Select road lines in Illustrator first">Use Illustrator selection</button><button data-act="obj_r_all">Tick all</button><button data-act="obj_r_none">Tick none</button></div>' +
    '<label>Filter <input type="text" id="objRFilter" placeholder="id, name or class"></label>' +
    '<div style="max-height:200px;overflow:auto"><table id="objRTable"></table></div><div class="note" id="objRInfo"></div>' +
    '<h4>Road shape: add, reshape, delete <span class="tag" id="objGTag"></span></h4>' +
    '<p class="note">Roads are edited as centrelines. <b>Redraw roads</b> puts one open path per road (named by its id, e.g. str_oak_ring) on the Illustrator layer <code>Road Centerlines</code>; move its anchors or draw a new open path there ' +
    '(any name), then press a button below. Every change keeps a backup: <b>Undo last road change</b> restores it. Bridges are not touched here (Bridges tab). Redraw replaces the layer, so read your edits first. ' +
    'After changes: Foundry tab, Export world pack (3D); the town drawing (Roads layer outlines) updates with Generate town / redraw.</p>' +
    '<div class="btns"><button data-act="obj_r_redraw" title="Draw every road centreline from streets.json onto the layer Road Centerlines (replaces that layer)">Redraw roads in Illustrator</button>' +
    '<button class="primary" data-act="obj_r_readall" title="Read the selected open paths (or, with nothing selected, every open path on Road Centerlines): paths named like a road reshape it, others are added as new roads">Read roads from Illustrator</button>' +
    '<button data-act="obj_r_undo" title="Restore streets.json from the newest backup (one step per press)">Undo last road change</button></div>' +
    '<div class="btns"><label>New road name <input type="text" data-nr="name" data-s="objects.nr.name" placeholder="empty = the path name" title="Name of a road added from the selection (several paths get 1, 2 ...)"></label></div>' +
    '<div class="btns"><label>Class <select data-nr="kind" data-s="objects.nr.kind" title="Class of a new road"><option>lane</option><option>road</option><option>street</option><option>alley</option></select></label>' +
    '<label>Width (ft) <input type="number" data-nr="width" data-s="objects.nr.width" min="2" max="120" step="1" title="Width of a new road"></label></div>' +
    '<div class="btns"><label>Simplify (ft) <input type="number" data-nr="simplify" data-s="objects.nr.simplify" min="0" max="200" step="0.5" title="Douglas-Peucker tolerance: drops points closer than this to the line. 0 = keep every point"></label>' +
    '<label>Smooth passes <input type="number" data-nr="smooth" data-s="objects.nr.smooth" min="0" max="50" step="1" title="Smoothing iterations (endpoints stay)"></label></div>' +
    '<div class="btns"><button data-act="obj_r_add" title="Select open paths in Illustrator, then add each as a new road (name, class and width above)">Add from Illustrator selection</button>' +
    '<button data-act="obj_r_reshape" title="Select open paths named like roads (str_...) and replace the lines of those roads with the paths. Width, class and overrides stay">Reshape from Illustrator selection</button>' +
    '<button data-act="obj_r_shape" title="Simplify and / or smooth the existing line of every ticked road (uses the two boxes above)">Simplify / smooth ticked</button></div>' +
    '<div class="btns"><label>Split at vertex <input type="number" data-nr="splitAt" data-s="objects.nr.splitAt" min="1" step="1" title="Index of the vertex (first = 0) where the ticked road is cut in two"></label>' +
    '<button data-act="obj_r_split" title="Cut the ticked road at that vertex into two roads">Split</button><button data-act="obj_r_join" title="Join the two ticked roads end to end (same class, ends within 25 ft)">Join two</button></div>' +
    '<div class="btns"><label class="chk"><input type="checkbox" data-nr="confirmDelete" data-s="objects.nr.confirmDelete"> Yes, delete the ticked roads</label>' +
    '<button data-act="obj_r_del" title="Delete the ticked roads from streets.json (backed up; refused for bridges and roads named in bridges.json)">Delete ticked roads</button></div>' +
    '<div id="objRFields"></div><div class="btns"><button class="primary" data-act="obj_apply_r" title="Write the ticked fields into the chosen roads">Apply edits</button>' +
    '<button data-act="obj_reset_r" title="Remove the edit block of the chosen roads (width stays)">Reset overrides</button><button data-act="obj_load_r" title="Fill the fields from the first chosen road">Load values of first chosen</button></div>';

  function mount() {
    var nav = $("tabs"), main = document.querySelector("main");
    if (!nav || !main) return;
    var sb = $("tab-buildings");
    if (sb && !$("objBFields")) { var d = document.createElement("div"); d.id = "objBWrap"; d.innerHTML = BHTML; sb.appendChild(d); }
    if (!$("tab-roads")) {
      var b = document.createElement("button"); b.setAttribute("role", "tab"); b.setAttribute("data-tab", "roads"); b.textContent = "Roads";
      var anchor = nav.querySelector('[data-tab="buildings"]') || nav.querySelector('[data-tab="town"]');
      if (anchor && anchor.nextSibling) nav.insertBefore(b, anchor.nextSibling); else nav.appendChild(b);
      var sec = document.createElement("section"); sec.id = "tab-roads"; sec.setAttribute("role", "tabpanel"); sec.innerHTML = RHTML; main.appendChild(sec);
    }
    if ($("objBFields") && !$("objBFields").innerHTML) $("objBFields").innerHTML = fieldsHtml("b", VB.OBJ_BUILDING_FIELDS);
    if ($("objRFields") && !$("objRFields").innerHTML) $("objRFields").innerHTML = fieldsHtml("r", VB.OBJ_ROAD_FIELDS);
  }
  mount();

  function textures() {
    if (cache.tx) return cache.tx;
    var out = []; try { ctx.fs.readdirSync(ctx.root + "/illustrator/presets/textures").forEach(function (f) { if (/\.png$/i.test(f)) out.push(f.replace(/\.png$/i, "")); }); } catch (e) { /* none */ }
    cache.tx = out.sort(); return cache.tx;
  }
  function interiorStyles() {
    if (cache.is) return cache.is;
    var j = ctx.readJson(ctx.root + "/illustrator/presets/interiors/presets.json", { styles: {} });
    cache.is = ["auto"].concat(Object.keys(j.styles || {})); return cache.is;
  }
  function lampStyles() {      // [[id, name]] from presets/streetlamps/styles.json
    if (cache.ls) return cache.ls;
    var j = ctx.readJson(ctx.root + "/illustrator/presets/streetlamps/styles.json", { styles: {} });
    cache.ls = Object.keys(j.styles || {}).map(function (k) { return [k, j.styles[k].name || k]; }); return cache.ls;
  }
  function options(kind) {
    var leave = '<option value="">(default: clear the override)</option>';
    if (kind === "interior") return leave + interiorStyles().map(function (x) { return '<option value="' + x + '">' + esc(x) + "</option>"; }).join("");
    if (kind === "roof") return leave + ["gable", "hip"].map(function (x) { return '<option value="' + x + '">' + x + "</option>"; }).join("");
    if (kind === "texture") return leave + textures().map(function (x) { return '<option value="' + esc(x) + '">' + esc(x) + "</option>"; }).join("");
    if (kind === "lampstyle") return leave + lampStyles().map(function (x) { return '<option value="' + esc(x[0]) + '">' + esc(x[1]) + "</option>"; }).join("");
    if (kind === "roadclass") return leave + CLASSES.map(function (x) { return '<option value="' + x + '">' + x + "</option>"; }).join("");
    if (kind === "bool") return leave + '<option value="true">yes</option>';
    return leave + '<option value="true">yes</option><option value="false">no</option>';
  }
  function allFields(scope) { return scope === "b" ? VB.OBJ_BUILDING_FIELDS : VB.OBJ_ROAD_FIELDS; }
  function paintFields(scope) {
    var host = $(scope === "b" ? "objBFields" : "objRFields"); if (!host) return;
    allFields(scope).forEach(function (f) {
      var fl = O()[scope][f[0]], row = host.querySelector('[data-row="' + scope + ":" + f[0] + '"]'); if (!row) return;
      var ck = row.querySelector('input[data-p="on"]'); ck.checked = !!fl.on;
      var sel = row.querySelector("select");
      if (sel) { var html = options(f[2]); if (sel.getAttribute("data-built") !== f[2] + textures().length) { sel.innerHTML = html; sel.setAttribute("data-built", f[2] + textures().length); } sel.value = fl.v == null ? "" : String(fl.v); sel.disabled = !fl.on; }
      Array.prototype.forEach.call(row.querySelectorAll('input[data-p="v"]'), function (inp) { if (document.activeElement !== inp) inp.value = fl.v == null ? "" : fl.v; inp.disabled = !fl.on; });
    });
  }
  function buildings() {
    var dir = ctx.dirs().world + "/buildings", out = [];
    try { ctx.fs.readdirSync(dir).forEach(function (f) { if (/\.json$/.test(f)) { var j = ctx.readJson(dir + "/" + f, null); if (j && j.id) out.push(j); } }); } catch (e) { /* none */ }
    return out;
  }
  function roads() {
    var j = ctx.readJson(ctx.dirs().world + "/streets.json", { streets: [] }), st = ctx.readJson(ctx.root + "/illustrator/presets/town_styles/full_map.json", { types: { streets: {} } });
    return (j.streets || []).map(function (s) { return { id: s.id, name: s.name || "", kind: s.kind || "", width: (s.geometry || {}).width_ft, edit: s.edit || null, raw: s, bridge: s.kind === "bridge" }; });
  }
  function summary(e) {
    if (!e) return "";
    var p = []; Object.keys(e).forEach(function (k) { if (e[k] && typeof e[k] === "object") Object.keys(e[k]).forEach(function (g) { p.push(k + "." + g + "=" + e[k][g]); }); else p.push(k + "=" + e[k]); });
    return p.join(", ");
  }
  function paint() {
    if (!ctx || !$("objRFields")) return;
    var o = O(); if (!o) return;
    if ($("objBFields")) {
      paintFields("b");
      var n = (ctx.state().styles.ids || []).length, bl = buildings(), ed = bl.filter(function (b) { return b.edit || b.interior_style; }).length;
      if ($("objBTag")) $("objBTag").textContent = ed + "/" + bl.length + " with overrides";
      if ($("objBInfo")) $("objBInfo").textContent = n + " building(s) chosen" + (o.last && /buildings/.test(o.last.kind) ? "   last: " + o.last.count + " changed" : "");
    }
    paintFields("r"); paintGeo();
    var rl = roads(), f = (o.rfilter || "").toLowerCase(), tk = {}; (o.rids || []).forEach(function (i) { tk[i] = 1; });
    $("objRTable").innerHTML = "<tr><th></th><th>id</th><th>name</th><th>kind</th><th>ft</th><th>overrides</th></tr>" + rl.filter(function (r) { return !f || (r.id + " " + r.name + " " + r.kind + " " + summary(r.edit)).toLowerCase().indexOf(f) >= 0; }).map(function (r) {
      return '<tr><td><input type="checkbox" data-rid="' + esc(r.id) + '"' + (tk[r.id] ? " checked" : "") + (r.bridge ? " disabled" : "") + "></td><td>" + esc(r.id) + "</td><td>" + esc(r.name) + "</td><td>" + esc(r.kind) + "</td><td>" + (r.width == null ? "" : r.width) + "</td><td>" + esc(summary(r.edit)) + "</td></tr>";
    }).join("");
    $("objRTag").textContent = rl.filter(function (r) { return r.edit; }).length + "/" + rl.length + " with overrides";
    $("objRInfo").textContent = (o.rids || []).length + " chosen" + (o.rids_src ? " (" + o.rids_src + ")" : "") + (o.last && /roads/.test(o.last.kind) ? "   last: " + o.last.count + " changed" : "");
  }
  // fill the form from one object (existing overrides, else the object's current value)
  function load(scope) {
    var o = O(), first = scope === "b" ? (ctx.state().styles.ids || [])[0] : (o.rids || [])[0];
    if (!first) { ctx.showError && ctx.showError("choose an object first"); return; }
    if (scope === "b") {
      var b = buildings().filter(function (x) { return x.id === first; })[0] || {}, e = b.edit || {};
      o.b.floors.v = b.floors || 1; o.b.interior_style.v = b.interior_style || "";
      ["roof_type", "roof_pitch", "roof_overhang_ft", "roof_material", "wall_material"].forEach(function (k) { o.b[k].v = e[k] == null ? (k === "roof_type" ? "gable" : (typeof o.b[k].v === "number" ? o.b[k].v : "")) : e[k]; });
      o.b.no_windows.v = e.no_windows ? "true" : ""; o.b.keep_individual.v = e.keep_individual ? "true" : "";
    } else {
      var r = roads().filter(function (x) { return x.id === first; })[0] || {}, d = r.edit || {}, g = d.grade || {};
      var lp = d.lamps || {}; o.r["lamps.on"].v = lp.on == null ? "" : String(lp.on); o.r["lamps.style"].v = lp.style || ""; o.r["lamps.spacing_ft"].v = lp.spacing_ft == null ? "" : lp.spacing_ft;
      o.r.width_ft.v = r.width || 16; o.r["class"].v = d["class"] || ""; o.r.surface.v = d.surface || ""; o.r.kerb.v = d.kerb == null ? "" : String(d.kerb);
      ["smooth", "max_grade_deg", "cross_deg"].forEach(function (k) { o.r["grade." + k].v = g[k] == null ? "" : g[k]; });
      o.r["grade.cutfill"].v = g.cutfill == null ? "" : String(g.cutfill);
    }
    ctx.save(); paint();
  }
  function go(make) { try { return ctx.startJob(make(), function () { cache = {}; paint(); }); } catch (e) { if (ctx.showError) ctx.showError(String(e.message || e)); } }
  var A = {
    obj_apply_b: function () { return go(function () { return VB.jobObjectsEditBuildings(ctx.state()); }); },
    obj_reset_b: function () { return go(function () { return VB.jobObjectsReset(ctx.state(), "building"); }); },
    obj_load_b: function () { load("b"); },
    obj_apply_r: function () { return go(function () { return VB.jobObjectsEditRoads(ctx.state()); }); },
    obj_reset_r: function () { return go(function () { return VB.jobObjectsReset(ctx.state(), "road"); }); },
    obj_load_r: function () { load("r"); },
    obj_r_del: function () { return go(function () { return VB.jobRoadsDelete(ctx.state()); }); },
    obj_r_undo: function () { return go(function () { return VB.jobRoadsUndo(ctx.state()); }); },
    obj_r_redraw: function () { return go(function () { return VB.jobRoadsRedraw(ctx.state(), ctx.dirs()); }); },
    obj_r_add: function () { return go(function () { return VB.jobRoadsFromPaths(ctx.state(), ctx.dirs(), "add"); }); },
    obj_r_reshape: function () { return go(function () { return VB.jobRoadsFromPaths(ctx.state(), ctx.dirs(), "reshape"); }); },
    obj_r_readall: function () { return go(function () { return VB.jobRoadsFromPaths(ctx.state(), ctx.dirs(), "sync"); }); },
    obj_r_shape: function () { return go(function () { return VB.jobRoadsShape(ctx.state()); }); },
    obj_r_split: function () { return go(function () { return VB.jobRoadsSplit(ctx.state()); }); },
    obj_r_join: function () { return go(function () { return VB.jobRoadsJoin(ctx.state()); }); },
    obj_r_sel: function () { return go(function () { return VB.jobRoadsFromSelection(ctx.state(), roads().filter(function (r) { return !r.bridge; }).map(function (r) { return r.id; })); }); },
    obj_r_all: function () { O().rids = roads().filter(function (r) { return !r.bridge; }).map(function (r) { return r.id; }); O().rids_src = "all ticked"; ctx.save(); paint(); },
    obj_r_none: function () { O().rids = []; O().rids_src = ""; ctx.save(); paint(); }
  };
  function paintGeo() {
    var nr = O() && O().nr, host = $("tab-roads"); if (!nr || !host) return;
    Array.prototype.forEach.call(host.querySelectorAll("[data-nr]"), function (el) {
      var k = el.getAttribute("data-nr"); if (document.activeElement === el) return;
      if (el.type === "checkbox") el.checked = !!nr[k]; else el.value = nr[k] == null ? "" : nr[k];
    });
  }
  function onGeo(ev) {
    var el = ev.target.closest("[data-nr]"); if (!el || !O().nr) return;
    var k = el.getAttribute("data-nr");
    O().nr[k] = el.type === "checkbox" ? el.checked : (el.type === "number" ? (el.value === "" ? "" : +el.value) : el.value);
    ctx.save();
  }
  function onField(ev) {
    var el = ev.target.closest("[data-of]"); if (!el) return;
    var scope = el.getAttribute("data-of"), k = el.getAttribute("data-k"), p = el.getAttribute("data-p"), fl = O()[scope][k]; if (!fl) return;
    if (p === "on") fl.on = el.checked; else fl.v = el.type === "range" || el.type === "number" ? (el.value === "" ? "" : +el.value) : el.value;
    ctx.save(); paintFields(scope);
  }
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    ["objBFields", "objRFields"].forEach(function (id) { var h = $(id); if (h) { h.addEventListener("input", onField); h.addEventListener("change", onField); } });
    if ($("tab-roads")) { $("tab-roads").addEventListener("input", onGeo); $("tab-roads").addEventListener("change", onGeo); }
    if ($("objRFilter")) $("objRFilter").addEventListener("input", function () { O().rfilter = $("objRFilter").value; paint(); });
    if ($("objRTable")) $("objRTable").addEventListener("change", function (ev) {
      var cb = ev.target.closest("input[data-rid]"); if (!cb) return;
      var id = cb.getAttribute("data-rid"), ids = (O().rids || []).filter(function (x) { return x !== id; });
      if (cb.checked) ids.push(id);
      O().rids = ids; O().rids_src = ""; ctx.save(); paint();
    });
    paint();
  }
  window.VBObjectsUI = { init: init, paint: paint, actions: A, mount: mount };
})();
