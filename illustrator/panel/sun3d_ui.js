// "Sun, shadows and fog" block of the Lighting tab: presets (one click sets everything), time-of-day slider, sun / ambient / shadow / fog controls, an offline approximate preview image
// (sun_preview.py, debounced) and Apply / Preview-in-Foundry / Reset buttons. Logic: lib/sun3d.js. Python: foundry_sun.py (set-sun), sun_preview.py (render).
// Loaded after lighting_ui.js and before main.js; it builds itself when the panel starts (window.VBSunUI.init(ctx), called from VBLightUI.init's host).
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, timer = null, presets = [], again = false;
  var $ = function (id) { return document.getElementById(id); };
  var $$ = function (sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var S = function () { var l = ctx.state().lighting; if (!l.sun3d) l.sun3d = VB.sunDefaults(); return l.sun3d; };
  function sl(path, label, mn, mx, step, tip) {
    var a = " " + path + ' min="' + mn + '" max="' + mx + '" step="' + step + '"';
    return '<div class="sl"><span title="' + esc(tip) + '">' + label + '</span><input type="range"' + a + ' title="' + esc(tip) + '"><span class="nb"><input type="number"' + a + ' title="' + esc(tip) + '"></span></div>';
  }
  function opts(map) { return Object.keys(map).map(function (k) { return '<option value="' + esc(k) + '">' + esc(map[k]) + "</option>"; }).join(""); }
  function html() {
    return '<details open id="sunBlock"><summary><b>Sun, shadows and fog (Foundry 3D)</b></summary>' +
      '<div id="sunNotice" style="border:1px solid #e6b450;background:rgba(230,180,80,.12);padding:6px;margin:4px 0"><b>Shadow Quality needed.</b> Sun shadows only appear for a person whose Foundry setting <b>Configure Settings &gt; 3D Canvas &gt; Shadow Quality</b> is <b>4</b> (Medium). 3D Canvas reads it per browser, so every player and the GM must set it once; no scene flag or world setting can do it for them. <button data-act="sun_macro" title="Creates the world macro Set my shadow quality (everyone can run it; players need the Use Script Macros permission). Each person runs it once on their own browser.">Install the one-click macro</button></div>' +
      '<p class="note">One click on a preset sets every value below. Dry run first: Check shows the scene flags that would change. Needs an existing scene picked on the Foundry tab (Refresh from Foundry). Presets are editable JSON files in illustrator/presets/lighting.</p>' +
      '<div id="sunPresets" class="btns"></div><p class="note" id="sunPresetNote"></p>' +
      sl('data-s="lighting.sun3d.hour"', "Time of day (h)", 0, 24, 0.25, "Blends the presets that have an hour (dawn 6, morning 9, noon 12, afternoon 15, dusk 19, night 23.5): sun direction, colour, strength and ambient.") +
      sl('data-s="lighting.sun3d.azimuth"', "Sun azimuth", 0, 360, 1, "Compass bearing of the sun: 0 north, 90 east, 180 south, 270 west. Shadows fall the opposite way.") +
      sl('data-s="lighting.sun3d.altitude"', "Sun elevation", 1, 89, 1, "Degrees above the horizon: low = long shadows, 90 = straight overhead.") +
      sl('data-s="lighting.sun3d.strength"', "Sun strength", 0, 3, 0.05, "Scene flag exposure: strength of the sun AND the tone-mapping exposure. About 1.2 to 1.5 reads well by day; the sky image lights the scene too.") +
      sl('data-s="lighting.sun3d.ambient"', "Ambient balance", 0, 0.5, 0.01, "Scene flag ambientLightIntensity. Keep low (0.05 to 0.15): the skybox already adds fill light, a high ambient flattens the sun's shadows.") +
      '<div class="grid"><label>Sun colour <input type="color" data-s="lighting.sun3d.color"></label><label>Ambient colour <input type="color" data-s="lighting.sun3d.ambientColor"></label>' +
      '<label title="The shadow map of the sun is a client setting (per browser). It is NOT stored in the scene: each player sets 3D Canvas Shadow Quality. This only records what to recommend. Measured cost on the Dyers scene: within the noise (0 to 1 ms GPU).">Shadows <select data-s="lighting.sun3d.shadows">' + opts({ on: "on", off: "off" }) + "</select></label>" +
      '<label>Shadow quality (client) <select data-s="lighting.sun3d.shadowQuality">' + opts(VB.SHADOW_QUALITIES) + "</select></label></div>" +
      sl('data-s="lighting.sun3d.bias"', "Shadow bias", -0.002, 0, 0.00005, "Scene flag shadowBias. More negative removes striping (acne) on slopes but detaches shadows from their objects.") +
      '<div class="grid"><label title="Scene flag enableFog. While on, 3D Canvas shows the flat fog colour instead of the sky image, so use the sky horizon colour.">Fog <select data-s="lighting.sun3d.fog">' + opts({ off: "off", on: "on" }) + "</select></label>" +
      '<label>Fog colour <input type="color" data-s="lighting.sun3d.fogColor"></label></div>' +
      sl('data-s="lighting.sun3d.fogFar"', "Fog far (scene px)", 4000, 60000, 500, "Scene flag fogDistance: fog starts at 1000 px and is full at this distance (linear). 7000 dense, 22000 haze, 30000+ faint. Also the camera far plane.") +
      '<div class="grid"><label title="Write the sky image of the preset (night = starry, dusk/sunset = orange) as the scene sky. Off leaves the sky alone.">Sky <select data-s="lighting.sun3d.sky">' + opts({ preset: "use the preset sky", off: "leave the sky alone" }) + "</select></label>" +
      '<div class="grid"><label title="Sky look. The sun (or the moon for Night) is drawn in the sky at the sun azimuth and elevation set above, so the shadows 3D Canvas casts point away from it. Fog on replaces the sky with the flat fog colour.">Sky look <select data-s="lighting.sun3d.skyPreset">' + opts(VB.SKY_PRESETS) + "</select></label></div>" +
      '<label class="chk" title="Build the preset\'s sky image first with skybox.py (about 1 minute)"><input type="checkbox" data-s="lighting.sun3d.makeSky"> Build the sky image if missing</label>' +
      '<label title="Tile flag castShadow of terrain, roads, plazas and padding. Default is on for every tile.">Ground tiles cast shadows <select data-s="lighting.sun3d.groundCast">' + opts({ leave: "leave as is", on: "on", off: "off" }) + "</select></label></div>" +
      '<label class="chk" title="push-scene-3d (Tools tab) also writes this preset: sun direction, strength, ambient, shadow bias and fog flags"><input type="checkbox" data-s="lighting.sun3d.onPush"> Also write this preset when pushing a 3D scene</label>' +
      '<div class="btns"><button data-act="sun_dry" title="Reads the scene and shows what would change. Writes nothing.">Check (dry run)</button>' +
      '<button class="primary" data-act="sun_apply" title="Writes sun, ambient, shadow bias, fog and sky flags to the scene. The previous values are stored once on the scene for Reset.">Apply to scene</button>' +
      '<button data-act="sun_temp" title="Applies to the picked scene exactly like Apply. Use it on a test scene; Reset to saved puts the previous flags back. A screenshot cannot be taken from this panel.">Preview in Foundry (temporary)</button>' +
      '<button data-act="sun_reset" title="Puts the scene flags back to what they were before the first Apply (keys that did not exist are removed).">Reset to saved</button></div>' +
      '<div id="sunReadout" class="note" style="white-space:pre-wrap"></div>' +
      '<div class="note"><b>Offline preview (approximation)</b>: plan view of the pack\'s terrain and building roofs, lit with the sun and fog above. Not Foundry\'s renderer, no trees. The strip under it is the sky; the red circle is the sun / moon at the light direction.</div>' +
      '<img id="sunPrev" alt="approximate sun preview" style="max-width:100%;image-rendering:auto;background:#1c1e24;min-height:40px"><div id="sunPrevNote" class="note"></div>' +
      '<p class="note">Players: shadows only show when each player has 3D Canvas Settings > Shadow Quality above 0 (Medium = 4). It is a per-browser setting; no scene flag can force it.</p></details>';
  }
  function swatch(p) { var c = p.swatch || []; return "linear-gradient(90deg," + (c[0] || "#888") + "," + (c[1] || "#aaa") + "," + (c[2] || "#444") + ")"; }
  function paint() {
    var host = $("sunBlock"); if (!host) return;
    var s = S(), fo = ctx.state().foundry || {};
    $$("[data-s^='lighting.sun3d.']", host).forEach(function (el) {
      var v = VB.getPath(ctx.state(), el.getAttribute("data-s"));
      if (el.type === "checkbox") el.checked = !!v; else if (v !== undefined && v !== null && document.activeElement !== el) el.value = v;
    });
    $("sunPresets").innerHTML = presets.map(function (p) {
      return '<button data-sun-preset="' + esc(p.id) + '" title="' + esc(p.description || "") + '" style="border-left:12px solid transparent;border-image:' + swatch(p) + ' 1;' + (p.id === s.preset ? "outline:2px solid #e6b450;" : "") + '">' + esc(p.label || p.id) + "</button>";
    }).join("");
    var cur = presets.filter(function (p) { return p.id === s.preset; })[0];
    $("sunPresetNote").textContent = cur ? cur.label + ": " + (cur.description || "") : "";
    var last = s.last, lines = [];
    lines.push("Target scene: " + (fo.target === "existing" && fo.sceneUuid ? fo.sceneUuid : "none (pick one on the Foundry tab)"));
    if (last) {
      lines.push("Last " + (last.restore ? "reset" : last.applied ? "apply" : "check") + " (" + String(last.at || "").replace("T", " ").slice(0, 19) + "): " + (last.scene || "") + ", " + Object.keys(last.changes || {}).length + " scene flag(s) " + (last.applied ? "written" : "would change") + ".");
      if (last.shadows) lines.push("Each player: " + last.shadows.instruction);
      if (last.cost) lines.push("Sun shadow cost: about +" + last.cost.extra_gpu_ms + " ms GPU (" + last.cost.label + ").");
      if (last.sky && last.sky.sky) lines.push("Sky: " + last.sky.sky);
      if (last.note_fog) lines.push(last.note_fog);
    }
    $("sunReadout").textContent = lines.join("\n");
  }
  function showPreview() {
    var img = $("sunPrev"); if (!img) return;
    try {
      var fs = require("fs"), p = VB.sunPreviewPath(ctx.state(), ctx.dirs());
      img.src = "data:image/png;base64," + fs.readFileSync(p).toString("base64"); img.style.display = "block"; $("sunPrevNote").textContent = "Approximation, updated " + new Date().toLocaleTimeString() + ".";
    } catch (e) { img.style.display = "none"; }
  }
  function schedulePreview() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      if (ctx.isBusy && ctx.isBusy()) { again = true; schedulePreview(); return; }   // never queue behind a running job: retry shortly
      try { ctx.startJob(VB.jobSunPreview(ctx.state(), ctx.dirs()), showPreview); } catch (e) { $("sunPrevNote").textContent = String((e && e.message) || e); }
    }, 700);
  }
  function runSet(apply, restore) {
    try { return ctx.startJob(VB.jobSetSun(ctx.state(), ctx.dirs(), apply, restore), function () { paint(); }); }
    catch (e) { if (ctx.showError) ctx.showError(String((e && e.message) || e)); else $("sunReadout").textContent = String((e && e.message) || e); }
  }
  var acts = {
    sun_dry: function () { return runSet(false, false); },
    sun_apply: function () { return runSet(true, false); },
    sun_temp: function () { return runSet(true, false); },
    sun_reset: function () { return runSet(true, true); },
    sun_macro: function () { return ctx.startJob(VB.jobClickMacros()); }
  };
  function init(c) {
    ctx = c;
    var sec = $("tab-lighting"); if (!sec || $("sunBlock")) return;
    if (VB.sunWrapLate) VB.sunWrapLate();
    try { presets = VB.sunLoadPresets(require("fs"), ctx.dirs().presets + "/lighting"); } catch (e) { presets = []; }
    var wrap = document.createElement("div"); wrap.innerHTML = html(); sec.insertBefore(wrap.firstChild, $("f3dBlock") || null);
    var host = $("sunBlock");
    var coerce = function (el) { return el.type === "checkbox" ? el.checked : (el.type === "number" || el.type === "range") ? (el.value === "" ? 0 : Number(el.value)) : el.value; };
    var onChange = function (ev) {
      var el = ev.target, p = el.getAttribute && el.getAttribute("data-s"); if (!p) return;
      ev.stopPropagation();
      var v = coerce(el); if (el.tagName === "SELECT" && /shadowQuality$/.test(p)) v = Number(v);
      VB.setPath(ctx.state(), p, v);
      if (p === "lighting.sun3d.hour") { var h = VB.sunFromHour(presets, v), s = S(); if (h) { Object.keys(h).forEach(function (k) { s[k] = h[k]; }); s.preset = (s.preset || "afternoon"); } }
      ctx.save();
      $$('[data-s="' + p + '"]', host).forEach(function (o) { if (o !== el && o.type !== "checkbox") o.value = el.value; });
      paint(); schedulePreview();
    };
    host.addEventListener("input", onChange); host.addEventListener("change", onChange);
    host.addEventListener("click", function (ev) {
      var pb = ev.target.closest("[data-sun-preset]"), b = ev.target.closest("[data-act]");
      if (pb) { ev.stopPropagation(); var p = presets.filter(function (x) { return x.id === pb.getAttribute("data-sun-preset"); })[0]; if (p) { VB.sunApplyPreset(ctx.state(), p); ctx.save(); paint(); schedulePreview(); } return; }
      if (b && acts[b.getAttribute("data-act")]) { ev.stopPropagation(); acts[b.getAttribute("data-act")](); }
    });
    paint(); showPreview();
  }
  window.VBSunUI = { init: init, paint: paint, acts: acts };
})();
