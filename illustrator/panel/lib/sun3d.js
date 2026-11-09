// Sun, shadows and fog for 3D Canvas scenes (Lighting tab block). Pure logic, no DOM: also loaded by test/test_sun3d_jobs.js.
// Python side: generators/foundry_sun.py (`set-sun`, routed through foundry_push.py) and generators/sun_preview.py (`render`, the offline approximate lit preview).
// Presets are editable JSON files in illustrator/presets/lighting/*.json (loaded by sun3d_ui.js; VB.sunLoadPresets reads them with an injected fs).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  var num = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };

  VB.SUN_FALLBACK_ORDER = ["dawn", "morning", "noon", "afternoon", "dusk", "night", "foggy_morning", "warm_sunset"];
  VB.SHADOW_QUALITIES = { 0: "Off", 2: "Low (2048 map)", 4: "Medium (4096 map)", 8: "High (8192 map)" };
  VB.sunDefaults = function () {
    return { preset: "afternoon", hour: 15, azimuth: 235, altitude: 38, strength: 1.3, color: "#fff0cf", ambient: 0.08, ambientColor: "#e8f0ff",
      shadows: "on", shadowQuality: 4, bias: -0.0003, fog: "off", fogColor: "#c9dcee", fogFar: 30000, sky: "preset", makeSky: false, groundCast: "leave", onPush: false, last: null, previewAt: "" };
  };
  // read every preset JSON in presets/lighting (fs = node fs, dir = d.presets + "/lighting") -> ordered list
  VB.sunLoadPresets = function (fs, dir) {
    var out = [];
    try {
      fs.readdirSync(dir).filter(function (f) { return /\.json$/.test(f); }).forEach(function (f) {
        try { var p = JSON.parse(fs.readFileSync(dir + "/" + f, "utf8")); p.id = p.id || f.replace(/\.json$/, ""); out.push(p); } catch (e) { /* skip a broken file */ }
      });
    } catch (e) { /* no folder */ }
    out.sort(function (a, b) { var i = VB.SUN_FALLBACK_ORDER.indexOf(a.id), j = VB.SUN_FALLBACK_ORDER.indexOf(b.id); return (i < 0 ? 99 : i) - (j < 0 ? 99 : j); });
    return out;
  };
  // copy a preset's values into the panel state (one click sets everything)
  VB.sunApplyPreset = function (st, p) {
    var s = st.lighting.sun3d = Object.assign(VB.sunDefaults(), { last: (st.lighting.sun3d || {}).last });
    s.preset = p.id; if (p.hour != null) s.hour = p.hour;
    s.azimuth = p.sun.azimuth; s.altitude = p.sun.altitude; s.strength = p.sun.strength; s.color = p.sun.color;
    s.ambient = p.ambient.intensity; s.ambientColor = p.ambient.color;
    s.shadows = (p.shadows || {}).on === false ? "off" : "on"; s.shadowQuality = (p.shadows || {}).quality != null ? p.shadows.quality : 4; s.bias = (p.shadows || {}).bias != null ? p.shadows.bias : -0.0003;
    s.fog = (p.fog || {}).enabled ? "on" : "off"; s.fogColor = (p.fog || {}).color || "#c9dcee"; s.fogFar = (p.fog || {}).far_px || 30000;
    return st;
  };
  var hex = function (c) { c = String(c || "#ffffff").replace("#", ""); return [0, 2, 4].map(function (i) { return parseInt(c.substr(i, 2), 16) || 0; }); };
  var toHex = function (a) { return "#" + a.map(function (v) { v = Math.max(0, Math.min(255, Math.round(v))); return (v < 16 ? "0" : "") + v.toString(16); }).join(""); };
  // time-of-day slider: interpolate the presets that have an "hour" (dawn 6 ... night 23.5); wraps night -> dawn. Returns sun / ambient values for that hour.
  VB.sunFromHour = function (presets, hour) {
    var k = presets.filter(function (p) { return p.hour != null; }).sort(function (a, b) { return a.hour - b.hour; });
    if (!k.length) return null;
    hour = ((Number(hour) % 24) + 24) % 24;
    var a = k[k.length - 1], b = k[0], ha = a.hour - 24, hb = b.hour, i;
    for (i = 0; i < k.length; i++) { if (k[i].hour <= hour) { a = k[i]; ha = a.hour; b = k[(i + 1) % k.length]; hb = b.hour + (i + 1 >= k.length ? 24 : 0); } }
    var t = hb === ha ? 0 : (hour - ha) / (hb - ha);
    var l = function (x, y) { return x + (y - x) * t; }, lc = function (x, y) { var p = hex(x), q = hex(y); return toHex([l(p[0], q[0]), l(p[1], q[1]), l(p[2], q[2])]); };
    var az = a.sun.azimuth, bz = b.sun.azimuth; if (bz - az > 180) bz -= 360; if (az - bz > 180) bz += 360;
    return { azimuth: Math.round(((l(az, bz) % 360) + 360) % 360), altitude: Math.round(l(a.sun.altitude, b.sun.altitude)), strength: Math.round(l(a.sun.strength, b.sun.strength) * 100) / 100,
      color: lc(a.sun.color, b.sun.color), ambient: Math.round(l(a.ambient.intensity, b.ambient.intensity) * 1000) / 1000, ambientColor: lc(a.ambient.color, b.ambient.color) };
  };
  // options shared by set-sun and the offline preview: every value is passed explicitly so the panel state (not the preset file) decides
  VB.sunOptionArgs = function (st) {
    var s = (st.lighting && st.lighting.sun3d) || VB.sunDefaults();
    var a = ["--preset", s.preset || "afternoon", "--sun-azimuth", String(num(s.azimuth, 235)), "--sun-altitude", String(num(s.altitude, 38)), "--sun-strength", String(num(s.strength, 1.3)),
      "--sun-color", s.color || "#fff0cf", "--ambient", String(num(s.ambient, 0.08)), "--ambient-color", s.ambientColor || "#ffffff", "--shadows", s.shadows === "off" ? "off" : "on",
      "--shadow-quality", String(Math.round(num(s.shadowQuality, 4))), "--shadow-bias", String(num(s.bias, -0.0003)), "--fog", s.fog === "on" ? "on" : "off",
      "--fog-color", s.fogColor || "#c9dcee", "--fog-far", String(Math.round(num(s.fogFar, 30000)))];
    return a;
  };
  VB.sunSetArgs = function (st, d, apply, restore) {
    var fo = st.foundry || {}, s = st.lighting.sun3d;
    if (fo.target !== "existing" || !fo.sceneUuid) throw new Error("pick an existing scene on the Foundry tab first (Refresh from Foundry)");
    var a = ["set-sun", "--scene-uuid", fo.sceneUuid, "--place", st.place];
    if (restore) { a.push("--restore"); }
    else {
      a = a.concat(VB.sunOptionArgs(st));
      if (s.sky === "off") a.push("--sky", "off"); else if (s.makeSky) a.push("--make-sky");
      if (s.groundCast && s.groundCast !== "leave") a.push("--ground-cast", s.groundCast);
    }
    if (apply) a.push("--apply");
    return a;
  };
  VB.sunPreviewArgs = function (st, d) {
    return ["render", "--place", st.place].concat(VB.sunOptionArgs(st), ["--out", d.root + "/illustrator/out/sun_preview/live_" + st.place + ".png"]);
  };
  VB.sunPreviewPath = function (st, d) { return d.root + "/illustrator/out/sun_preview/live_" + st.place + ".png"; };
  VB.jobSunPreview = function (st, d) {
    return { kind: "sun_preview", label: "Sun preview (offline approximation)", params: {}, steps: [
      py(GEN + "sun_preview.py", VB.sunPreviewArgs(st, d), "sun preview", { json: "sp" }),
      { t: "fn", label: "store preview", fn: function (run) {
        var r = run.vars.sp; if (!r || r.ok === false) throw new Error((r && r.error) || "preview gave no result");
        run.setState("lighting.sun3d.previewAt", new Date().toISOString());
        run.log("preview ready: " + Math.round((r.shadow_fraction || 0) * 100) + "% of the ground in shadow");
      } }] };
  };
  // apply (or restore) on the picked scene; dry run unless apply. "Preview in Foundry (temporary)" is an apply with the backup kept: Reset to saved = restore.
  VB.jobSetSun = function (st, d, apply, restore) {
    var args = VB.sunSetArgs(st, d, apply, restore);
    return { kind: "set_sun", label: (restore ? "Reset sun / fog to saved" : "Sun, shadows and fog") + (apply ? " (apply)" : " (dry run)"), params: { apply: !!apply, restore: !!restore }, steps: [
      py(VB.FOUNDRY_PY || (GEN + "foundry_push.py"), args, "set-sun", { json: "ss" }),
      { t: "fn", label: "store result", fn: function (run) {
        var r = run.vars.ss; if (!r || r.ok === false) throw new Error((r && r.error) || "set-sun gave no result");
        run.setState("lighting.sun3d.last", { at: new Date().toISOString(), applied: !!r.applied, restore: !!r.restore, scene: r.scene, preset: r.preset, changes: r.flag_changes, shadows: r.shadows, cost: r.cost, sky: r.sky, note_fog: r.note_fog });
        run.log((r.applied ? "applied: " : "dry run: ") + Object.keys(r.flag_changes || {}).length + " scene flag(s) " + (r.restore ? "restored" : "change") + (r.shadows ? ". " + r.shadows.instruction : ""));
      } }] };
  };

  // push-scene-3d carries the preset when the box "also write this preset on push" is ticked (tools.js loads after this file, so it is wrapped once at start-up)
  VB.sunWrapLate = function () {
    if (!VB.scene3dArgs || VB.scene3dArgs.sun3d) return;
    var base = VB.scene3dArgs;
    VB.scene3dArgs = function (st, d, dry) { var a = base(st, d, dry), s = st.lighting && st.lighting.sun3d; return a.indexOf("push-scene-3d") >= 0 && s && s.onPush ? a.concat(["--sun-preset", s.preset || "afternoon"]) : a; };
    VB.scene3dArgs.sun3d = true; VB.scene3dArgs.f3d = base.f3d;
  };

  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); if (o.lighting) o.lighting.sun3d = VB.sunDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
