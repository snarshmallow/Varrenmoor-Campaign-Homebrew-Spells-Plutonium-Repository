// Lighting tab UI (sun dial, placed-light list, auto re-render). Loaded before main.js; main.js calls VBLightUI.init(ctx) / paint()
// and routes the light_* data-act buttons to VBLightUI.actions. Logic (config, job) lives in lib/lighting.js.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, timer = null, pending = false;
  var $ = function (id) { return document.getElementById(id); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var L = function () { return ctx.state().lighting; };

  // ---- sun dial: sky view, centre = overhead, rim = horizon, N up, azimuth clockwise; the dot is the sun, the arrow the shadow direction
  var DIAL = 96, C = DIAL / 2, R = C - 8;
  function sunXY(az, alt) {
    var a = az * Math.PI / 180, r = (90 - Math.max(0, Math.min(90, alt))) / 90 * R;
    return [C + Math.sin(a) * r, C - Math.cos(a) * r];
  }
  function paintDial() {
    var el = $("lightDial"); if (!el) return;
    var s = L().sun, p = sunXY(+s.azimuth || 0, +s.altitude || 0), a = ((+s.azimuth || 0) + 180) * Math.PI / 180;
    var ax = C + Math.sin(a) * (R * 0.78), ay = C - Math.cos(a) * (R * 0.78);
    var rings = [30, 60].map(function (alt) { return '<circle cx="' + C + '" cy="' + C + '" r="' + ((90 - alt) / 90 * R) + '" fill="none" stroke="#4a4a4a" stroke-dasharray="2 3"/>'; }).join("");
    el.innerHTML = '<svg viewBox="0 0 ' + DIAL + " " + DIAL + '" width="' + DIAL + '" height="' + DIAL + '" style="cursor:crosshair;touch-action:none">' +
      '<circle cx="' + C + '" cy="' + C + '" r="' + R + '" fill="#242a38" stroke="#6a6a6a"/>' + rings +
      '<line x1="' + C + '" y1="8" x2="' + C + '" y2="' + (DIAL - 8) + '" stroke="#3c3c3c"/><line x1="8" y1="' + C + '" x2="' + (DIAL - 8) + '" y2="' + C + '" stroke="#3c3c3c"/>' +
      '<text x="' + C + '" y="9" fill="#ddd" font-size="8" text-anchor="middle">N</text><text x="' + (DIAL - 3) + '" y="' + (C + 3) + '" fill="#9a9a9a" font-size="7" text-anchor="end">E</text>' +
      '<text x="' + C + '" y="' + (DIAL - 2) + '" fill="#9a9a9a" font-size="7" text-anchor="middle">S</text><text x="3" y="' + (C + 3) + '" fill="#9a9a9a" font-size="7">W</text>' +
      '<line x1="' + C + '" y1="' + C + '" x2="' + ax + '" y2="' + ay + '" stroke="#7a86b0" stroke-width="2" stroke-linecap="round"/>' +
      '<circle cx="' + ax + '" cy="' + ay + '" r="2.5" fill="#7a86b0"/>' +
      '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="6" fill="' + esc(s.color || "#ffdd88") + '" stroke="#fff"/></svg>';
    var t = $("lightDialTxt"); if (t) t.textContent = "azimuth " + Math.round(s.azimuth) + " deg, altitude " + Math.round(s.altitude) + " deg (shadows fall toward " + compass(((+s.azimuth || 0) + 180) % 360) + ")";
  }
  function compass(az) { return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.round(az / 45) % 8]; }
  function setFromDial(ev, svg) {
    var r = svg.getBoundingClientRect(), x = (ev.clientX - r.left) / r.width * DIAL - C, y = (ev.clientY - r.top) / r.height * DIAL - C;
    var rad = Math.min(Math.sqrt(x * x + y * y), R);
    var az = (Math.atan2(x, -y) * 180 / Math.PI + 360) % 360, alt = Math.max(1, Math.min(89, 90 - rad / R * 90));
    var s = L().sun; s.azimuth = Math.round(az); s.altitude = Math.round(alt);
    L().preset = ""; ctx.save(); ctx.syncInputs(); paintDial(); schedule();
  }

  // ---- placed lights
  function paintLights() {
    var ul = $("lightList"), lg = L(); if (!ul) return;
    ul.innerHTML = "";
    if (!lg.lights.length) ul.innerHTML = '<li class="note">no placed lights: add one below, then Capture point or type x, y (feet)</li>';
    lg.lights.forEach(function (l, i) {
      var li = document.createElement("li"); li.className = i === lg.sel ? "sel" : "";
      li.innerHTML = '<input type="checkbox" data-en="' + i + '"' + (l.enabled !== false ? " checked" : "") + ' title="Enabled"><span class="g">' + esc(l.name || l.id) + " (" + Math.round(l.x) + ", " + Math.round(l.y) + ')</span><button data-rm="' + i + '" title="Remove">&#10005;</button>';
      li.addEventListener("click", function (ev) {
        if (ev.target.closest("[data-en]") || ev.target.closest("[data-rm]")) return;
        lg.sel = i; ctx.save(); paintLights(); paintForm();
      });
      ul.appendChild(li);
    });
    paintForm();
  }
  var FIELDS = [["name", "Name", "text"], ["x", "X (ft)", "number", 1], ["y", "Y (ft)", "number", 1], ["height", "Height (ft)", "number", 1, 0, 200], ["radius", "Radius (ft)", "number", 5, 5, 1000],
    ["intensity", "Intensity", "number", 0.05, 0, 2], ["softness", "Softness", "number", 0.05, 0, 1], ["color", "Colour", "color"]];
  function paintForm() {
    var host = $("lightForm"), lg = L(); if (!host) return;
    var l = lg.lights[lg.sel];
    if (!l) { host.innerHTML = ""; return; }
    host.innerHTML = FIELDS.map(function (f) {
      var step = f[3] != null ? ' step="' + f[3] + '"' : "", mn = f[4] != null ? ' min="' + f[4] + '"' : "", mx = f[5] != null ? ' max="' + f[5] + '"' : "";
      return '<label>' + f[1] + ' <input type="' + f[2] + '" data-lf="' + f[0] + '"' + step + mn + mx + ' value="' + esc(l[f[0]] == null ? "" : l[f[0]]) + '"></label>';
    }).join("");
  }

  // ---- debounced auto re-render at the preview dpi
  function schedule() {
    if (!ctx || !L().auto || !L().enabled) return;
    clearTimeout(timer); pending = true;
    timer = setTimeout(fire, 800);
  }
  function fire() {
    if (!pending) return;
    if (ctx.isBusy()) { timer = setTimeout(fire, 900); return; }
    pending = false; actions.light_preview();
  }

  var actions = {
    light_render: function () { pending = false; return ctx.startJob(VB.jobLighting(ctx.state(), ctx.dirs(), { preview: false })); },
    light_preview: function () { return ctx.startJob(VB.jobLighting(ctx.state(), ctx.dirs(), { preview: true })); },
    light_clear: function () { return ctx.startJob(VB.jobLightingClear()); },
    light_capture: function () {
      return ctx.startJob(VB.jobLightCapture(ctx.state(), ctx.dirs()), function (r) {
        if (!r.ok) return;
        var lg = L(), p = lg.capture;
        if (!lg.lights[lg.sel]) { lg.lights.push(VB.newLight("lantern", lg.lights.length + 1)); lg.sel = lg.lights.length - 1; }
        lg.lights[lg.sel].x = p[0]; lg.lights[lg.sel].y = p[1];
        ctx.save(); paintLights(); schedule();
      });
    },
    light_add: function (kind) {
      var lg = L(), n = lg.lights.length + 1, l = VB.newLight(kind || "lantern", n), c = ctx.placeCentre();
      l.x = c[0]; l.y = c[1]; lg.lights.push(l); lg.sel = lg.lights.length - 1; ctx.save(); paintLights(); schedule();
    }
  };

  function applyPreset(key) {
    var st = ctx.state(), lg = st.lighting;
    VB.applyLightingPreset(st, key);
    if (key === "night" && !lg.lights.length) actions.light_add("lantern");
    ctx.save(); ctx.syncInputs(); paintDial(); paintLights(); schedule();
  }


  // ---- Foundry 3D lighting block: light budget, lighting mode, sun / ambient (global illumination), cost hint. Logic: lib/lighting.js (VB.f3d*), python: foundry_lightbudget.py (set-lighting).
  // Built here (not in index.html) and bound here: it saves state under lighting.f3d.* and never triggers the 2D shadow re-render.
  var F = function () { return ctx.state().lighting.f3d; };
  function sl(path, label, mn, mx, step, unit, tip) {
    var a = " " + path + ' min="' + mn + '" max="' + mx + '" step="' + step + '"';
    return '<div class="sl"><span title="' + esc(tip) + '">' + label + '</span><input type="range"' + a + ' title="' + esc(tip) + '"><span class="nb"><input type="number"' + a + ' title="' + esc(tip) + '">' + (unit ? '<span class="un">' + unit + "</span>" : "") + "</span></div>";
  }
  function opts(map) { return Object.keys(map).map(function (k) { return '<option value="' + esc(k) + '">' + esc(map[k]) + "</option>"; }).join(""); }
  function f3dHtml() {
    return '<details open id="f3dBlock"><summary><b>Foundry 3D lighting and light budget</b></summary>' +
      '<p class="note">Applies to the Foundry scene picked on the Foundry tab. Dry run by default: Check shows what would change, Apply writes it. Only the pipeline\'s own lights are touched. Defaults leave small scenes unchanged.</p>' +
      '<p class="note">Target scene: <b id="f3dScene">none</b></p>' +
      '<div class="grid"><label title="lights = every light as a point light. hybrid = only the most important lights + ambient fill. global = no point lights, ambient + sun only. auto = lights up to 64, hybrid up to 256, global above.">Lighting mode <select data-s="lighting.f3d.mode" id="f3dMode">' +
      opts({ auto: "Auto (by light count)", lights: "Point lights (all)", hybrid: "Hybrid (few lights + ambient)", global: "Global illumination only" }) + "</select></label>" +
      '<label title="Light shadows are the most expensive light feature: every shadow-casting point light renders the scene 6 more times. They only show when the Foundry client setting 3D Canvas shadow quality is above 0.">Light shadows <select data-s="lighting.f3d.shadows" id="f3dShadows">' +
      opts({ "": "leave as is", off: "off (cheapest)", "4": "4 most important", "8": "8 most important", on: "every kept light (slow)" }) + "</select></label>" +
      '<label title="Scene flag renderSceneLights: off = Foundry lights are not drawn in 3D at all (no point lights, cheapest). Leave unless you want that.">3D point lights <select data-s="lighting.f3d.renderLights">' + opts({ "": "leave as is", on: "on", off: "off (none drawn in 3D)" }) + "</select></label>" +
      '<label class="chk"><input type="checkbox" data-s="lighting.f3d.hearths"> Interior hearth lights</label><label class="chk"><input type="checkbox" data-s="lighting.f3d.windows"> Window lights</label></div>' +
      sl('data-s="lighting.f3d.maxLights"', "Max lights", 0, 400, 1, "", "Light budget: keep at most this many lights, most important first (plazas, street lamps, doors, hearths, windows), thinned by distance so they spread out. 0 = no limit. In hybrid mode 0 means " + VB.F3D.HYBRID_MAX + ".") +
      sl('data-s="lighting.f3d.radiusScale"', "Light radius", 0.25, 2, 0.05, "x", "Multiplies every pipeline light's radius (always from the original size, never compounds).") +
      sl('data-s="lighting.f3d.intensityScale"', "Light strength", 0.25, 2, 0.05, "x", "Multiplies every pipeline light's strength (capped at full).") +
      '<label class="chk" title="Also write the 3D scene flags below: time of day, ambient (global illumination), sun strength and colour."><input type="checkbox" data-s="lighting.f3d.applyFlags" id="f3dApplyFlags"> Also set sun, ambient and time of day on the scene</label>' +
      '<div id="f3dFlags"><div class="grid"><label>Time of day <select data-s="lighting.f3d.timeOfDay">' + opts(VB.F3D_TIMES) + "</select></label>" +
      '<label>Ambient colour <input type="color" data-s="lighting.f3d.giColor"></label><label>Sun colour <input type="color" data-s="lighting.f3d.sunColor"></label></div>' +
      sl('data-s="lighting.f3d.gi"', "Ambient (global illumination)", 0, 1, 0.01, "", "Scene flag ambientLightIntensity: a flat light on everything. Constant cost, does not depend on the number of lights. Global mode raises it to at least " + VB.F3D.GLOBAL_AMBIENT + ", hybrid to at least " + VB.F3D.HYBRID_AMBIENT + ".") +
      sl('data-s="lighting.f3d.sunStrength"', "Sun strength", 0, 3, 0.05, "", "Scene flag exposure: the strength of the sun light and the tone mapping exposure.") + "</div>" +
      '<div class="btns"><button data-act="f3d_perf" title="Hybrid mode, 12 lights, no window lights, no light shadows: the cheap setup for big maps">Performance mode</button>' +
      '<button data-act="f3d_reset" title="Back to the defaults (auto mode, no limit, scale 1, flags untouched)">Reset to defaults</button>' +
      '<button data-act="f3d_dry" title="Reads the scene, shows what would change. Writes nothing.">Check (dry run)</button>' +
      '<button class="primary" data-act="f3d_apply" title="Writes the light budget and flags to the scene. Over-budget lights are hidden, not deleted: raise the budget to bring them back.">Apply to scene</button></div>' +
      '<div id="f3dReadout" class="note" style="white-space:pre-wrap"></div>' +
      '<p class="note">Cost hint: every visible point light is evaluated for every pixel, so the cost grows with the light count (measured about 0.13 ms of GPU time per extra light at 1858x937 on the test GPU, flat below about 30 lights). A light that casts shadows costs far more (about 6 extra scene renders). Ambient and sun cost the same at any light count. Over-budget lights are switched off (hidden), not deleted.</p></details>';
  }
  function sceneInfo() {
    var st = ctx.state(), fo = st.foundry || {};
    if (fo.target !== "existing" || !fo.sceneUuid) return null;
    var rows = ((fo.cache || {}).lists || {}).scenes || [], r = rows.filter(function (x) { return x.uuid === fo.sceneUuid; })[0];
    return { uuid: fo.sceneUuid, name: r ? r.name : fo.sceneUuid };
  }
  function paintF3d() {
    var host = $("f3dBlock"); if (!host) return;
    var f = F(), si = sceneInfo();
    $$("[data-s^='lighting.f3d.']", host).forEach(function (el) {
      var v = VB.getPath(ctx.state(), el.getAttribute("data-s"));
      if (el.type === "checkbox") el.checked = v !== false && !!v; else if (v !== undefined && v !== null && document.activeElement !== el) el.value = v;
    });
    $("f3dScene").textContent = si ? si.name + "  [" + si.uuid + "]" : "none: pick an existing scene on the Foundry tab (Refresh from Foundry)";
    $("f3dFlags").style.opacity = f.applyFlags ? "1" : "0.45";
    $$("input,select", $("f3dFlags")).forEach(function (e) { e.disabled = !f.applyFlags; });
    var last = f.last, n = null, pack = (last && last.pack) || {};
    if (last && last.pipeline != null) n = last.pipeline;
    else if (Object.keys(pack).length) n = Object.keys(pack).reduce(function (a, k) { return a + pack[k]; }, 0);
    var lines = [];
    if (n == null) lines.push("Lights: not counted yet. Press Check (dry run) to count the lights in the scene and in the pack.");
    else {
      var n2 = n;
      if (Object.keys(pack).length) VB.f3dExcluded(f).forEach(function (k) { n2 -= pack[k] || 0; });
      var p = VB.f3dPlan(Math.max(0, n2), f);
      lines.push("Lights: " + n + " in the pipeline" + (Object.keys(pack).length ? " (pack: " + Object.keys(pack).map(function (k) { return pack[k] + " " + k; }).join(", ") + ")" : "") + ".");
      lines.push("Plan: " + p.on + " on, " + (n - p.on) + " off, mode " + p.mode + ". " + p.reason + ".");
      lines.push("Estimated cost: " + p.relative + "x an empty scene (" + p.label + ")" + (last && last.cost_now ? "; the scene is at " + last.cost_now.relative + "x (" + last.cost_now.label + ") now" : "") + ".");
    }
    if (last) lines.push("Last " + (last.applied ? "apply" : "check") + " (" + String(last.at || "").replace("T", " ").slice(0, 19) + "): " + last.on + " of " + last.pipeline + " lights on, " + last.shadow + " casting shadows" +
      (last.flags && Object.keys(last.flags).length ? "; scene flags " + Object.keys(last.flags).join(", ") : "") + ".");
    $("f3dReadout").textContent = lines.join("\n");
  }
  function runF3d(apply) {
    try { return ctx.startJob(VB.jobSetLighting(ctx.state(), ctx.dirs(), apply), function () { paintF3d(); }); }
    catch (e) { if (ctx.showError) ctx.showError(String((e && e.message) || e)); else $("f3dReadout").textContent = String((e && e.message) || e); }
  }
  var f3dActs = {
    f3d_perf: function () { VB.f3dPerformance(ctx.state()); ctx.save(); paintF3d(); },
    f3d_reset: function () { var last = F().last; VB.f3dReset(ctx.state()); F().last = last; ctx.save(); paintF3d(); },
    f3d_dry: function () { return runF3d(false); },
    f3d_apply: function () { return runF3d(true); }
  };
  function initF3d() {
    var sec = $("tab-lighting"); if (!sec || $("f3dBlock")) return;
    if (VB.f3dWrapLate) VB.f3dWrapLate();
    var wrap = document.createElement("div"); wrap.innerHTML = f3dHtml(); sec.appendChild(wrap.firstChild);
    var host = $("f3dBlock");
    var coerce = function (el) { return el.type === "checkbox" ? el.checked : (el.type === "number" || el.type === "range") ? (el.value === "" ? 0 : Number(el.value)) : el.value; };
    var onChange = function (ev) {
      var el = ev.target, p = el.getAttribute && el.getAttribute("data-s");
      if (!p) return;
      ev.stopPropagation();                       // do not trigger the 2D shadow re-render of this tab
      VB.setPath(ctx.state(), p, coerce(el)); ctx.save();
      $$('[data-s="' + p + '"]', host).forEach(function (o) { if (o !== el && o.type !== "checkbox") o.value = el.value; });
      paintF3d();
    };
    host.addEventListener("input", onChange); host.addEventListener("change", onChange);
    host.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-act]"); if (!b) return;
      ev.stopPropagation();
      var f = f3dActs[b.getAttribute("data-act")]; if (f) f();
    });
    paintF3d();
  }

  function init(c) {
    ctx = c;
    var sec = $("tab-lighting"); if (!sec) return;
    initF3d();
    sec.addEventListener("input", function (ev) {
      var t = ev.target, lf = t.getAttribute && t.getAttribute("data-lf");
      if (lf) {
        var lg = L(), l = lg.lights[lg.sel]; if (!l) return;
        l[lf] = t.type === "number" ? (t.value === "" ? 0 : Number(t.value)) : t.value;
        if (lf === "name") { var s = $("lightList").querySelector("li.sel .g"); if (s) s.textContent = l.name + " (" + Math.round(l.x) + ", " + Math.round(l.y) + ")"; }
        ctx.save();
      }
      L().preset = L().preset; paintDial(); schedule();
    });
    sec.addEventListener("change", function (ev) {
      var t = ev.target;
      if (t.getAttribute("data-en") != null) { L().lights[+t.getAttribute("data-en")].enabled = t.checked; ctx.save(); schedule(); }
      else if (t.id === "lightMode") { schedule(); }
    });
    sec.addEventListener("click", function (ev) {
      var rm = ev.target.closest("[data-rm]"), pr = ev.target.closest("[data-light-preset]"), ad = ev.target.closest("[data-light-add]");
      if (rm) { var lg = L(); lg.lights.splice(+rm.getAttribute("data-rm"), 1); lg.sel = Math.min(lg.sel, lg.lights.length - 1); ctx.save(); paintLights(); schedule(); }
      else if (pr) applyPreset(pr.getAttribute("data-light-preset"));
      else if (ad) actions.light_add(ad.getAttribute("data-light-add"));
    });
    var drag = false, dial = $("lightDial");
    dial.addEventListener("mousedown", function (ev) { var svg = dial.querySelector("svg"); if (!svg) return; drag = true; setFromDial(ev, svg); ev.preventDefault(); });
    window.addEventListener("mousemove", function (ev) { if (drag) { var svg = dial.querySelector("svg"); if (svg) setFromDial(ev, svg); } });
    window.addEventListener("mouseup", function () { drag = false; });
    var bar = $("lightPresets");
    bar.innerHTML = Object.keys(VB.LIGHTING_PRESETS).map(function (k) { return '<button data-light-preset="' + k + '">' + esc(VB.LIGHTING_PRESETS[k].label) + "</button>"; }).join("");
    paint();
  }
  function paint() { if (!ctx) return; paintDial(); paintLights(); paintF3d(); }

  window.VBLightUI = { init: init, paint: paint, actions: actions, f3dActs: f3dActs };
})();
