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

  function init(c) {
    ctx = c;
    var sec = $("tab-lighting"); if (!sec) return;
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
  function paint() { if (!ctx) return; paintDial(); paintLights(); }

  window.VBLightUI = { init: init, paint: paint, actions: actions };
})();
