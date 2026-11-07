// Varrenmoor Bridge panel: tabbed control surface. Edits panel_state.json, runs the Python generators
// (child_process.spawn), draws results through the ExtendScript host (host.jsx), and still executes job files from illustrator/jobs.
(function () {
  "use strict";
  var fs = require("fs"), path = require("path"), cp = require("child_process");
  var cs = new CSInterface();
  var VB = window.VBCore, R = window.VBRunner;
  var $ = function (id) { return document.getElementById(id); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };

  var state = null, d = null, root = null, jobsDir = null, textures = [], saveTimer = null, runner = null;
  var extras = VB.EXTRA_SWATCHES;

  // ------------------------------------------------------------ small UI helpers
  function logLine(m) {
    var el = $("log"); el.textContent = (el.textContent + m + "\n").slice(-8000); el.scrollTop = el.scrollHeight;
  }
  function showError(msg, level) { var e = $("err"); e.textContent = msg || ""; e.className = level === "warn" ? "warn" : ""; }
  function setStatus(s, busy) { var e = $("status"); e.textContent = s; e.className = busy ? "busy" : ""; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }

  // ------------------------------------------------------------ locating the repo
  function findJobsDir() {
    var ext = cs.getSystemPath(SystemPath.EXTENSION), real = ext;
    try { real = fs.realpathSync(ext); } catch (e) { /* keep */ }
    try { var c = JSON.parse(fs.readFileSync(path.join(ext, "config.json"), "utf8")); if (c.jobsDir) return c.jobsDir; } catch (e) { /* none */ }
    var dd = real;
    for (var i = 0; i < 6; i++) {
      var cand = path.join(dd, "jobs");
      if (fs.existsSync(cand) && fs.existsSync(path.join(dd, "panel"))) return cand;
      dd = path.dirname(dd);
    }
    return null;
  }
  function listPlaces() {
    var out = [];
    try { fs.readdirSync(path.join(root, "world")).forEach(function (n) { if (fs.existsSync(path.join(root, "world", n, "place.json"))) out.push(n); }); } catch (e) { /* none */ }
    return out.length ? out : ["bridgehollow"];
  }

  // ------------------------------------------------------------ state persistence (world/<place>/panel_state.json)
  function loadState(place) {
    var s = null;
    var p = VB.dirs(root, place).state;
    try { s = JSON.parse(fs.readFileSync(p, "utf8")); } catch (e) { s = null; }
    s = VB.normalize(s); s.place = place; return s;
  }
  function saveNow() {
    try {
      fs.mkdirSync(path.dirname(d.state), { recursive: true });
      fs.writeFileSync(d.state, JSON.stringify(state, null, 1) + "\n");
    } catch (e) { showError("cannot write " + d.state + ": " + e.message); }
  }
  function save() { clearTimeout(saveTimer); saveTimer = setTimeout(saveNow, 250); }
  function readJson(p, dflt) { try { return JSON.parse(fs.readFileSync(p, "utf8")); } catch (e) { return dflt; } }

  // ------------------------------------------------------------ binding
  function coerce(el) {
    if (el.type === "checkbox") return el.checked;
    if (el.type === "number") return el.value === "" ? null : Number(el.value);
    return el.value;
  }
  function paintInputs() {
    $$("[data-s]").forEach(function (el) {
      var v = VB.getPath(state, el.getAttribute("data-s"));
      if (el.type === "checkbox") el.checked = !!v; else if (v !== undefined && v !== null) el.value = v; else el.value = "";
    });
  }
  function bindInputs() {
    $$("[data-s]").forEach(function (el) {
      var ev = (el.tagName === "SELECT" || el.type === "checkbox") ? "change" : "input";
      el.addEventListener(ev, function () {
        var p = el.getAttribute("data-s");
        if (p === "place") return; // handled by switchPlace
        VB.setPath(state, p, coerce(el)); save();
        var a = el.getAttribute("data-act-change"); if (a && ev === "change") act(a);
        if (p === "terrain.patch.terrain_type") paintPatchForm();
        if (p.indexOf("contours.") === 0) $$('[data-s="' + p + '"]').forEach(function (o) { if (o !== el) { if (o.type === "checkbox") o.checked = el.checked; else o.value = el.value; } });
        if (p === "settings.view" && state.stale) { /* view change: next render uses it */ }
      });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && el.tagName === "INPUT" && el.type !== "checkbox") {
          var sec = el.closest("section"); var b = sec && sec.querySelector("button.primary"); if (b && !b.disabled) b.click();
        }
      });
    });
    $("place").addEventListener("change", function () { switchPlace($("place").value); });
  }
  function setState(p, v) { VB.setPath(state, p, v); save(); refreshAll(); }

  // ------------------------------------------------------------ tabs
  function showTab(t) {
    try {
      $$("#tabs button").forEach(function (b) { b.setAttribute("aria-selected", b.getAttribute("data-tab") === t ? "true" : "false"); b.tabIndex = b.getAttribute("data-tab") === t ? 0 : -1; });
      $$("main section").forEach(function (s) { s.classList.toggle("on", s.id === "tab-" + t); });
      state.ui.tab = t; save();
      if (t === "terrain") refreshPatches();
    } catch (e) { showError("tab " + t + ": " + (e && e.stack || e)); }
  }
  function bindTabs() {
    // Delegated on the nav; pointerdown/mousedown as well as click so a swallowed CEP click still switches.
    var nav = $("tabs"), last = 0;
    var go = function (ev) {
      var b = ev.target && ev.target.closest ? ev.target.closest("button[data-tab]") : null;
      if (!b) return;
      var now = Date.now(); if (now - last < 300) return; last = now;
      showTab(b.getAttribute("data-tab"));
    };
    nav.addEventListener("pointerdown", go); nav.addEventListener("mousedown", go); nav.addEventListener("click", go);
    var btns = $$("#tabs button");
    btns.forEach(function (b, i) {
      b.addEventListener("keydown", function (e) {
        var j = e.key === "ArrowRight" ? i + 1 : e.key === "ArrowLeft" ? i - 1 : null;
        if (j === null) return; j = (j + btns.length) % btns.length; btns[j].focus(); showTab(btns[j].getAttribute("data-tab")); e.preventDefault();
      });
    });
  }
  function paintStale() {
    var map = { contours: "contours", shading: "shading", town: "town" };
    Object.keys(map).forEach(function (k) {
      var b = document.querySelector('#tabs button[data-tab="' + map[k] + '"]'); if (b) b.classList.toggle("stale", !!state.stale[k]);
      var t = $("stale-" + k); if (t) { t.textContent = state.stale[k] ? "stale: terrain/water changed, re-run" : "up to date"; t.className = "tag" + (state.stale[k] ? " stale" : ""); }
    });
  }

  // ------------------------------------------------------------ host bridge
  function evalHost(a) {
    return new Promise(function (res) {
      cs.evalScript("VB_run(" + JSON.stringify(JSON.stringify(a)) + ")", function (r) {
        var o; try { o = JSON.parse(r); } catch (e) { o = { ok: false, error: "bad host reply: " + String(r).slice(0, 200) }; }
        res(o);
      });
    });
  }

  // ------------------------------------------------------------ jobs
  function makeRunner() {
    runner = R.createRunner({
      root: root, jobsDir: jobsDir, fs: fs, path: path, spawn: cp.spawn,
      host: evalHost, log: logLine,
      getPython: function () { return (state.settings.python || "python").trim() || "python"; },
      getPlace: function () { return state.place; },
      getTextures: function () { return textures; },
      setState: setState,
      onStale: function (setL, clearL) {
        setL.forEach(function (k) { state.stale[k] = true; }); clearL.forEach(function (k) { state.stale[k] = false; });
        save(); paintStale();
      },
      onStatus: function (s) {
        if (s.busy) { setStatus(s.label + ": " + s.step, true); $("cancel").disabled = false; }
        else { setStatus("idle", false); $("cancel").disabled = true; }
      }
    });
  }
  async function startJob(job, after) {
    if (runner.isBusy()) { showError("another job is running: wait for it or press Cancel"); return null; }
    showError(""); logLine("== " + job.label);
    var res = await runner.run(job);
    if (!res.ok) showError((res.cancelled ? "Cancelled: " : "Failed: ") + job.label + ": " + res.error);
    else if (res.warnings && res.warnings.length) showError(job.label + " done with warnings: " + res.warnings.join(" | "), "warn");
    else logLine("ok: " + job.label + (res.logFile ? "  (logged " + path.basename(res.logFile) + ")" : ""));
    if (res.logError) showError("job log not written: " + res.logError, "warn");
    if (after) { try { after(res); } catch (e) { showError(String(e.message || e)); } }
    refreshAll();
    return res;
  }

  // ------------------------------------------------------------ terrain tab
  function paintPatchForm() {
    var sel = $("patchType"); if (!sel.options.length) {
      VB.RAISE.concat(VB.DEPRESS).forEach(function (t) { var o = document.createElement("option"); o.value = t; o.textContent = t + (VB.DEPRESS.indexOf(t) >= 0 ? " (depress)" : ""); sel.appendChild(o); });
      sel.value = state.terrain.patch.terrain_type;
    }
    var dep = VB.DEPRESS.indexOf(state.terrain.patch.terrain_type) >= 0;
    var mx = document.querySelector('[data-s="terrain.patch.max_height_ft"]'), mn = document.querySelector('[data-s="terrain.patch.min_height_ft"]');
    mx.disabled = dep; mn.disabled = !dep;
  }
  function patchHistory() { return readJson(d.terrain + "/patches.json", { patches: [], undone: [] }); }
  function refreshPatches() {
    var h = patchHistory(), ul = $("patchList"), list = (h.patches || []).slice().sort(function (a, b) { return a.order - b.order; });
    $("patchCount").textContent = list.length + " active, " + (h.undone || []).length + " undone";
    ul.innerHTML = "";
    if (!list.length) { ul.innerHTML = '<li class="note">no patches</li>'; return; }
    list.forEach(function (p, i) {
      var li = document.createElement("li"), q = p.params || {};
      var hv = q.max_height_ft != null ? "max " + q.max_height_ft : q.min_height_ft != null ? "min " + q.min_height_ft : "";
      li.innerHTML = '<span class="g">' + (i + 1) + ". " + esc(p.id) + " " + esc(q.terrain_type || "") + " " + hv + " ft</span>" +
        '<button data-pa="up" title="Move earlier">&#9650;</button><button data-pa="down" title="Move later">&#9660;</button><button data-pa="remove" title="Remove (can redo)">&#10005;</button>';
      li.title = "Click to load these settings into the form";
      li.addEventListener("click", function (ev) {
        var b = ev.target.closest("button");
        if (b) { patchOp(b.getAttribute("data-pa"), list, i); return; }
        Object.keys(q).forEach(function (k) { if (k in state.terrain.patch) state.terrain.patch[k] = q[k]; });
        state.terrain.patch.polygon = p.polygon_ft || []; state.terrain.patch.polygon_src = "from " + p.id;
        save(); refreshAll();
      });
      ul.appendChild(li);
    });
  }
  function patchOp(op, list, i) {
    var P = list[i], g = "illustrator/generators/terrain_patch.py";
    if (op === "remove") return startJob(VB.jobPatchCmd(state, d, "remove", ["--id", P.id]), refreshPatches);
    var j = op === "up" ? i - 1 : i + 1; if (j < 0 || j >= list.length) return;
    var Q = list[j], job = VB.jobPatchCmd(state, d, "reorder", []);
    job.label = "Reorder patches"; job.params = { move: P.id, swap_with: Q.id };
    job.steps = [VB.steps.py(g, ["reorder", "--place", state.place, "--id", P.id, "--order", String(Q.order)], "reorder 1"),
      VB.steps.py(g, ["reorder", "--place", state.place, "--id", Q.id, "--order", String(P.order)], "reorder 2")];
    return startJob(job, refreshPatches);
  }
  function showPatchPreview(res) {
    var info = $("patchInfo"), img = $("patchPrev"), j = runner.parseJsonOut(res.out);
    if (j && j.info) {
      var i = j.info, s = j.seam || {};
      info.textContent = "type " + i.type + "  max " + (+i.max).toFixed(1) + "  min " + (+i.min).toFixed(1) + "  mean " + (+i.mean).toFixed(1) + " ft" +
        (s.outside_max_change != null ? "\noutside change " + (+s.outside_max_change).toFixed(3) + " ft, seam ratio " + (+s.dgrad_ratio).toFixed(3) : "") +
        ((i.warnings || []).length ? "\nWARN: " + i.warnings.join("; ") : "");
    } else info.textContent = "";
    try { img.src = "data:image/png;base64," + fs.readFileSync(d.patchPreview + "/preview_hillshade.png").toString("base64"); img.style.display = "block"; }
    catch (e) { img.style.display = "none"; }
  }

  // ------------------------------------------------------------ shading tab
  function terrainRange() {
    var m = readJson(d.terrain + "/terrain_meta_patched.json", null) || readJson(d.terrain + "/terrain_meta.json", {});
    var lo = Math.floor((m.elev_min != null ? m.elev_min : 0) - 100), hi = Math.ceil((m.elev_max != null ? m.elev_max : 1000) + 100);
    return [lo, hi];
  }
  function listDir(p, ext) { try { return fs.readdirSync(p).filter(function (f) { return f.toLowerCase().slice(-ext.length) === ext; }).sort(); } catch (e) { return []; } }
  function fillPresetList() {
    var sel = $("shPreset"); sel.innerHTML = "";
    listDir(d.presets + "/terrain_phases", ".json").filter(function (f) { return f.charAt(0) !== "_"; }).forEach(function (f) {
      var o = document.createElement("option"); o.value = f.replace(/\.json$/, ""); o.textContent = o.value; sel.appendChild(o);
    });
    sel.value = state.shading.preset;
  }
  function loadPreset(name) {
    var doc = readJson(d.presets + "/terrain_phases/" + name + ".json", null);
    if (!doc) { showError("terrain phase preset not found: " + name); return; }
    var sh = state.shading; sh.preset = name; sh.base_color = doc.base_color || "#808080";
    if (doc.hillshade) sh.hillshade = Object.assign({ enabled: true, azimuth: 315, altitude: 40, strength: 0.55, exaggeration: 1 }, doc.hillshade);
    sh.phases = (doc.phases || (Array.isArray(doc) ? doc : [])).map(function (p) {
      var q = VB.clone(p); q.texture = VB.texName(q.texture) || "#808080"; if (q.enabled === undefined) q.enabled = true; return q;
    });
    sh.loaded = true; save(); renderPhases(); paintInputs();
  }
  var dragIdx = null;
  function renderPhases() {
    var host = $("phases"), rng = terrainRange(), lo = rng[0], hi = rng[1];
    host.innerHTML = "";
    var texNames = textures.map(function (t) { return t.file; });
    state.shading.phases.forEach(function (p, i) {
      var el = document.createElement("div"); el.className = "phase" + (p.enabled === false ? " off" : ""); el.draggable = false;
      var opts = texNames.map(function (n) { return '<option value="' + esc(n) + '"' + (n === p.texture ? " selected" : "") + ">" + esc(n.replace(/\.\w+$/, "")) + "</option>"; }).join("");
      if (texNames.indexOf(p.texture) < 0) opts = '<option value="' + esc(p.texture) + '" selected>' + esc(p.texture) + " (custom)</option>" + opts;
      var emin = p.elev_min == null ? lo : p.elev_min, emax = p.elev_max == null ? hi : p.elev_max;
      el.innerHTML =
        '<div class="hd"><span class="handle" title="Drag to reorder">&#9776;</span><input type="checkbox" data-k="enabled" title="Enabled"' + (p.enabled !== false ? " checked" : "") + '>' +
        '<input type="text" data-k="name" value="' + esc(p.name || p.id) + '"><select data-k="texture" style="width:96px">' + opts + '</select>' +
        '<button data-op="up" title="Earlier (painted first)">&#9650;</button><button data-op="down" title="Later (painted over earlier)">&#9660;</button><button data-op="del" title="Remove">&#10005;</button></div>' +
        row("Elev min", "elev_min", lo, hi, 1, emin, emin <= lo ? "-inf" : emin) + row("Elev max", "elev_max", lo, hi, 1, emax, emax >= hi ? "inf" : emax) +
        row("Slope min", "slope_min_deg", 0, 90, 1, p.slope_min_deg || 0, p.slope_min_deg || 0) + row("Slope max", "slope_max_deg", 0, 90, 1, p.slope_max_deg == null ? 90 : p.slope_max_deg, p.slope_max_deg == null ? 90 : p.slope_max_deg) +
        row("Elev blend", "elev_blend_ft", 0, 200, 5, p.elev_blend_ft == null ? 20 : p.elev_blend_ft, p.elev_blend_ft == null ? 20 : p.elev_blend_ft) +
        row("Slope blend", "slope_blend_deg", 0, 30, 1, p.slope_blend_deg == null ? 5 : p.slope_blend_deg, p.slope_blend_deg == null ? 5 : p.slope_blend_deg) +
        row("Opacity", "opacity", 0, 1, 0.05, p.opacity == null ? 1 : p.opacity, p.opacity == null ? 1 : p.opacity) +
        row("Jitter", "noise_jitter", 0, 1.5, 0.05, p.noise_jitter == null ? 0.5 : p.noise_jitter, p.noise_jitter == null ? 0.5 : p.noise_jitter);
      function row(lbl, k, a, b, st, v, shown) { return '<div class="sl"><span>' + lbl + '</span><input type="range" data-k="' + k + '" min="' + a + '" max="' + b + '" step="' + st + '" value="' + v + '"><span data-v="' + k + '">' + shown + "</span></div>"; }
      el.addEventListener("input", function (ev) {
        var t = ev.target, k = t.getAttribute("data-k"); if (!k) return;
        if (t.type === "range") {
          var v = Number(t.value);
          if (k === "elev_min") { p.elev_min = v <= lo ? null : v; el.querySelector('[data-v="elev_min"]').textContent = v <= lo ? "-inf" : v; }
          else if (k === "elev_max") { p.elev_max = v >= hi ? null : v; el.querySelector('[data-v="elev_max"]').textContent = v >= hi ? "inf" : v; }
          else { p[k] = v; el.querySelector('[data-v="' + k + '"]').textContent = v; }
        } else if (t.type === "checkbox") { p.enabled = t.checked; el.classList.toggle("off", !t.checked); }
        else p[k] = t.value;
        save();
      });
      el.addEventListener("change", function (ev) { if (ev.target.tagName === "SELECT") { p.texture = ev.target.value; save(); } });
      el.addEventListener("click", function (ev) {
        var b = ev.target.closest("button[data-op]"); if (!b) return; var op = b.getAttribute("data-op"), a = state.shading.phases;
        if (op === "del") a.splice(i, 1); else if (op === "up" && i > 0) { a.splice(i - 1, 0, a.splice(i, 1)[0]); } else if (op === "down" && i < a.length - 1) { a.splice(i + 1, 0, a.splice(i, 1)[0]); }
        save(); renderPhases();
      });
      var hd = el.querySelector(".handle");
      hd.addEventListener("mousedown", function () { el.draggable = true; });
      el.addEventListener("dragstart", function (ev) { dragIdx = i; el.classList.add("drag"); try { ev.dataTransfer.setData("text/plain", String(i)); } catch (e) { /* ok */ } });
      el.addEventListener("dragend", function () { el.draggable = false; el.classList.remove("drag"); });
      el.addEventListener("dragover", function (ev) { ev.preventDefault(); });
      el.addEventListener("drop", function (ev) {
        ev.preventDefault(); if (dragIdx === null || dragIdx === i) return;
        var a = state.shading.phases; a.splice(i, 0, a.splice(dragIdx, 1)[0]); dragIdx = null; save(); renderPhases();
      });
      host.appendChild(el);
    });
  }
  function addPhase() {
    var n = state.shading.phases.length + 1;
    state.shading.phases.push({ id: "phase_" + n + "_" + Date.now().toString(36), name: "New phase " + n, texture: textures.length ? textures[0].file : "#808080", elev_min: null, elev_max: null,
      slope_min_deg: 0, slope_max_deg: 90, elev_blend_ft: 20, slope_blend_deg: 5, opacity: 1, noise_jitter: 0.5, tile_scale_ft: 40, enabled: true });
    save(); renderPhases();
  }

  // ------------------------------------------------------------ town tab
  function paintRings() {
    var host = $("rings"); host.innerHTML = "";
    if (!state.town.rings.length) { host.innerHTML = '<div class="note">no rings loaded: press "Reload town_params.json"</div>'; return; }
    state.town.rings.forEach(function (r, i) {
      var el = document.createElement("div"); el.className = "grid"; el.style.marginBottom = "3px";
      el.innerHTML = '<label>' + esc(r.name || r.id) + ' radius<input type="number" data-r="r_max" value="' + r.r_max + '" step="any"></label>' +
        '<label>street width<input type="number" data-r="street_width" value="' + r.street_width + '" step="any"></label>' +
        '<label>lot min ft2<input type="number" data-r="lot_min" value="' + r.lot_min + '" step="100"></label>' +
        '<label>lot max ft2<input type="number" data-r="lot_max" value="' + r.lot_max + '" step="100"></label>';
      el.addEventListener("input", function (ev) { var k = ev.target.getAttribute("data-r"); if (k) { r[k] = Number(ev.target.value); save(); } });
      host.appendChild(el);
    });
  }
  function fillSelects() {
    var opts = '<option value="">(none)</option>' + textures.map(function (t) { return '<option value="' + esc(t.name) + '">' + esc(t.name) + "</option>"; }).join("") +
      extras.map(function (t) { return '<option value="' + t.name + '">' + t.name + "</option>"; }).join("");
    $$("select.fill").forEach(function (s) { s.innerHTML = opts; });
    var sp = $("stylePreset"); sp.innerHTML = '<option value="">(custom)</option>';
    listDir(d.presets + "/town_styles", ".json").forEach(function (f) {
      var j = readJson(d.presets + "/town_styles/" + f, {}), o = document.createElement("option"); o.value = f.replace(/\.json$/, ""); o.textContent = j.name || o.value; sp.appendChild(o);
    });
  }
  function applyStylePreset() {
    var n = state.town.style.preset; if (!n) return;
    var j = readJson(d.presets + "/town_styles/" + n + ".json", null);
    if (!j) { showError("style preset not found: " + n); return; }
    Object.keys(j.parts || {}).forEach(function (k) { state.town.style[k] = j.parts[k]; });
    state.town.style.stroke = j.stroke || ""; save(); paintInputs();
  }

  // ------------------------------------------------------------ loading files into state
  function loadFiles(force) {
    var s = state;
    if (force === "scale" || !s.scale.loaded) {
      var raw = readJson(d.world + "/view_settings.json", null);
      if (raw) { VB.viewToState(raw, s.scale); } else if (force === "scale") showError("view_settings.json not found for " + s.place);
    }
    if (force === "spec" || !s.terrain.spec_loaded) {
      var spec = readJson(d.world + "/terrain_spec.json", null);
      if (spec) { VB.specToState(spec, s.terrain.spec); s.terrain.spec_loaded = true; } else showError("terrain_spec.json not found for " + s.place, "warn");
    }
    if (force === "town" || !s.town.params_loaded) {
      var tp = readJson(d.world + "/town_params.json", null);
      if (tp) VB.townFromParams(tp, s.town); else showError("town_params.json not found for " + s.place, "warn");
    }
    if (!s.shading.loaded) loadPreset(s.shading.preset);
    save();
  }

  // ------------------------------------------------------------ refresh everything that depends on state
  function paintTags() {
    var t = state.terrain.patch, a = state.town.area, w = state.water;
    $("patchPoly").textContent = t.polygon && t.polygon.length ? t.polygon.length + " pts, " + Math.round(VB.polyArea(t.polygon)) + " ft2" + (t.polygon_src ? " (" + t.polygon_src + ")" : "") : "none";
    $("townArea").textContent = a && a.length ? a.length + " pts, " + Math.round(VB.polyArea(a)) + " ft2" + (state.town.area_src ? " (" + state.town.area_src + ")" : "") : "none";
    $("riverPath").textContent = w.river_path && w.river_path.length ? w.river_path.length + " pts" + (w.river_src ? " (" + w.river_src + ")" : "") : "none";
    $("lakePoly").textContent = w.lake_polygon && w.lake_polygon.length ? w.lake_polygon.length + " pts, " + Math.round(VB.polyArea(w.lake_polygon)) + " ft2" : "none";
    $("btnAccept").disabled = !state.town.candidate; $("btnReject").disabled = !state.town.candidate;
    $("candTag").textContent = state.town.candidate ? "candidate pending: Accept or Reject" : "no candidate";
    $("candTag").className = "tag" + (state.town.candidate ? " stale" : "");
    $("statePath").textContent = d.state;
  }
  function refreshAll() { paintInputs(); paintTags(); paintStale(); paintPatchForm(); paintRings(); }

  function showCrossings() {
    var j = readJson(d.water + "/crossings.json", null), el = $("crossInfo");
    if (!j) { el.textContent = "No crossings.json yet."; return; }
    var rows = Array.isArray(j) ? j : (j.crossings || []);
    if (!rows.length) { el.textContent = "No road crosses water."; return; }
    el.innerHTML = "<table><tr><th>road</th><th>water</th><th>use</th><th>span ft</th><th>deck ft</th></tr>" + rows.map(function (c) {
      return "<tr><td>" + esc(c.road || "") + "</td><td>" + esc(c.water_id || "") + "</td><td>" + esc(c.suggestion || "") + (c.existing_bridge ? " (existing)" : "") + "</td><td>" + esc(c.span_ft == null ? "" : c.span_ft) + "</td><td>" + esc(c.deck_elevation_ft == null ? "" : c.deck_elevation_ft) + "</td></tr>";
    }).join("") + "</table>";
  }

  // ------------------------------------------------------------ actions
  var NEWDOC = function () {
    var j = VB.jobScaleApply(state, d, true);
    j.kind = "new_doc"; j.label = "New document + draw everything";
    j.steps.unshift(VB.steps.host({ action: "new_document", width_in: state.scale.page_w_in, height_in: state.scale.page_h_in, landscape: true }, "new document"));
    return j;
  };
  var acts = {
    scale_apply: function () { return startJob(VB.jobScaleApply(state, d, false)); },
    redraw_all: function () { return startJob(VB.jobScaleApply(state, d, true)); },
    new_doc: function () { return startJob(NEWDOC()); },
    scale_reload: function () { state.scale.loaded = false; loadFiles("scale"); refreshAll(); },
    scale_preset: function () { var p = state.scale.preset; state.scale.loaded = false; loadFiles("scale"); state.scale.preset = p; refreshAll(); },
    terrain_load_spec: function () { loadFiles("spec"); refreshAll(); },
    terrain_generate: function () { return startJob(VB.jobTerrainGenerate(state, d), refreshPatches); },
    patch_capture: function () { return startJob(VB.jobCapture(state, d, { what: "terrain polygon", layer: "TERRAIN AREA", closed: true, store: "terrain.patch.polygon", srcName: "terrain.patch.polygon_src" })); },
    patch_preview: function () { return startJob(VB.jobPatch(state, d, "preview"), showPatchPreview); },
    patch_apply: function () { return startJob(VB.jobPatch(state, d, "apply"), function (r) { refreshPatches(); if (r.ok) { showPatchPreview(r); } }); },
    patch_undo: function () { return startJob(VB.jobPatchCmd(state, d, "undo"), refreshPatches); },
    patch_redo: function () { return startJob(VB.jobPatchCmd(state, d, "redo"), refreshPatches); },
    patch_refresh: function () { refreshPatches(); },
    contours_run: function () { return startJob(VB.jobContours(state, d)); },
    shading_load_preset: function () { loadPreset(state.shading.preset); },
    shading_add_phase: addPhase,
    shading_render: function () { return startJob(VB.jobShading(state, d)); },
    water_analyze: function () { return startJob(VB.jobWaterAnalyze(state, d)); },
    water_carve: function () { return startJob(VB.jobWaterCarve(state, d)); },
    water_crossings: function () { return startJob(VB.jobWaterCrossings(state, d), showCrossings); },
    water_capture_river: function () { return startJob(VB.jobCapture(state, d, { what: "river path", layer: "WATER DRAW", open: true, store: "water.river_path", srcName: "water.river_src" })); },
    water_add_river: function () { return startJob(VB.jobWaterRiver(state, d)); },
    water_capture_lake: function () { return startJob(VB.jobCapture(state, d, { what: "lake polygon", layer: "WATER DRAW", closed: true, store: "water.lake_polygon", srcName: "water.lake_src" })); },
    water_add_lake: function () { return startJob(VB.jobWaterLake(state, d)); },
    town_capture: function () { return startJob(VB.jobCapture(state, d, { what: "town lasso", layer: "TOWN AREA", closed: true, store: "town.area", srcName: "town.area_src" })); },
    town_load_params: function () { state.town.area = []; loadFiles("town"); refreshAll(); },
    town_generate: function () { return startJob(VB.jobTown(state, d)); },
    town_accept: function () { return startJob(VB.jobTownAccept(state, d)); },
    town_reject: function () { return startJob(VB.jobTownReject(state, d)); },
    town_fills: function () { return startJob(VB.jobFills(state, d)); },
    style_preset: applyStylePreset,
    lock_guides: function () { return startJob(VB.jobLayers("lock_guides", state)); },
    unlock_guides: function () { return startJob(VB.jobLayers("unlock_guides", state)); },
    show_labels: function () { return startJob(VB.jobLayers("show_labels", state)); },
    hide_labels: function () { return startJob(VB.jobLayers("hide_labels", state)); },
    open_out: function () { openFolder(path.join(root, "illustrator", "out")); },
    open_done: function () { openFolder(path.join(jobsDir, "done")); },
    clear_stale: function () { state.stale = { contours: false, shading: false, town: false }; save(); paintStale(); }
  };
  function act(name) { var f = acts[name]; if (!f) { showError("unknown action " + name); return; } try { var r = f(); if (r && r.catch) r.catch(function (e) { showError(String(e && e.message || e)); }); } catch (e) { showError(String(e.message || e)); } }
  function openFolder(p) {
    try { fs.mkdirSync(p, { recursive: true }); var c = cp.spawn("explorer", [p.replace(/\//g, "\\")], { detached: true, stdio: "ignore" }); c.on("error", function (e) { showError("cannot open folder: " + e.message); }); c.unref(); }
    catch (e) { showError("cannot open folder: " + e.message); }
  }

  // ------------------------------------------------------------ place switching / textures
  async function loadTextures() {
    textures = [];
    var r = await runner.execPy("illustrator/generators/panelio.py", ["textures"]);
    var j = r.code === 0 ? runner.parseJsonOut(r.out) : null;
    if (j && j.textures) textures = j.textures;
    else {
      textures = listDir(d.presets + "/textures", ".png").map(function (f) { return { name: f.replace(/\.png$/, ""), file: f, rgb: null, hex: null }; });
      showError((r.spawnError ? r.err : "textures list failed: " + (r.err || "").trim().split(/\r?\n/).pop()) + " (fills need Python)", "warn");
    }
    fillSelects(); renderPhases(); paintInputs();
  }
  async function switchPlace(place) {
    if (state) saveNow();
    d = VB.dirs(root, place); state = loadState(place);
    var sel = $("place"); sel.value = place;
    loadFiles(); fillPresetList(); fillSelects(); paintInputs(); renderPhases(); refreshAll(); showTab(state.ui.tab || "scale"); refreshPatches(); showCrossings();
  }

  // ------------------------------------------------------------ legacy job-file poller (illustrator/jobs/*.json)
  var pollBusy = false;
  async function pollJobs() {
    if (pollBusy || (runner && runner.isBusy())) return; pollBusy = true;
    try {
      var doneDir = path.join(jobsDir, "done"); fs.mkdirSync(doneDir, { recursive: true });
      var files = fs.readdirSync(jobsDir).filter(function (f) { return /\.json$/i.test(f); }).sort();
      for (var i = 0; i < files.length; i++) {
        var f = files[i], fp = path.join(jobsDir, f), id = f.replace(/\.json$/i, ""), job, res;
        setStatus("job file " + id, true);
        try { job = JSON.parse(fs.readFileSync(fp, "utf8")); job.id = job.id || id; res = await runJobFile(job); }
        catch (e) { job = { id: id }; res = { id: id, ok: false, error: "job failed: " + e, results: [] }; }
        fs.writeFileSync(path.join(doneDir, job.id + ".result.json"), JSON.stringify(res, null, 2));
        try { fs.renameSync(fp, path.join(doneDir, id + ".json")); } catch (e) { try { fs.unlinkSync(fp); } catch (e2) { /* ignore */ } }
        logLine("job file " + job.id + ": " + (res.ok ? "ok" : "FAILED"));
      }
      if (!runner.isBusy()) setStatus("idle", false);
    } catch (e) { setStatus("error", false); logLine("poll error: " + e); }
    finally { pollBusy = false; }
  }
  async function runJobFile(job) {
    var results = [], ok = true, actions = job.actions || [];
    for (var i = 0; i < actions.length; i++) {
      var a = JSON.parse(JSON.stringify(actions[i])), r;
      try {
        if (a.path) a.path = (path.isAbsolute(a.path) ? a.path : path.resolve(root, a.path)).replace(/\\/g, "/");
        if (a.path && (a.action === "save_ai" || a.action === "export_png")) fs.mkdirSync(path.dirname(a.path), { recursive: true });
        r = await evalHost(a);
      } catch (e) { r = { ok: false, error: String(e) }; }
      r.action = a.action; results.push(r);
      if (!r.ok) { ok = false; if (!job.continue_on_error) break; }
    }
    return { id: job.id, ok: ok, finished: new Date().toISOString(), results: results };
  }

  // ------------------------------------------------------------ start
  async function init() {
    jobsDir = findJobsDir();
    if (!jobsDir) { setStatus("jobs dir not found", false); showError("Cannot locate the repo (illustrator/jobs). Run illustrator/install.ps1 or fix panel/config.json."); return; }
    root = path.dirname(path.dirname(jobsDir)).replace(/\\/g, "/");
    var places = listPlaces(), sel = $("place");
    places.forEach(function (p) { var o = document.createElement("option"); o.value = p; o.textContent = p; sel.appendChild(o); });
    state = VB.normalize(null); d = VB.dirs(root, state.place);
    makeRunner(); bindTabs(); bindInputs();
    $$("[data-act]").forEach(function (b) { b.addEventListener("click", function () { act(b.getAttribute("data-act")); }); });
    $("cancel").addEventListener("click", function () { if (runner.cancel()) logLine("cancel requested"); });
    $("toggleLog").addEventListener("click", function () { var l = $("log"); l.hidden = !l.hidden; });
    window.addEventListener("error", function (e) { showError("panel error: " + e.message); });
    var cur = places.indexOf(readJson(path.join(root, "world", "panel_last_place.json"), {}).place) >= 0 ? readJson(path.join(root, "world", "panel_last_place.json"), {}).place : places[0];
    await switchPlace(cur);
    sel.addEventListener("change", function () { try { fs.writeFileSync(path.join(root, "world", "panel_last_place.json"), JSON.stringify({ place: sel.value })); } catch (e) { /* ignore */ } });
    setStatus("idle", false);
    loadTextures();
    setInterval(pollJobs, 2000); pollJobs();
  }
  init().catch(function (e) { showError("startup failed: " + (e && e.stack || e)); });
})();
