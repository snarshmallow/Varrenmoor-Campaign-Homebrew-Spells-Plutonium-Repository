// Lighting additions to VBCore (loaded after core.js): defaults, presets, config builder and the render job.
// Pure logic, no DOM: also loaded by test/run_mock.js. Python side: generators/lighting.py.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";

  // raster layers stack above the fills, below LINES (VB.fillBelow reads FILL_ORDER at call time)
  ["ART - Shadows", "ART - Light Glow"].forEach(function (n) { if (VB.FILL_ORDER.indexOf(n) < 0) VB.FILL_ORDER.push(n); });
  VB.SHADOW_LAYER = "ART - Shadows"; VB.GLOW_LAYER = "ART - Light Glow"; VB.SHADOW_VECTOR_LAYER = "Shadows";

  VB.lightingDefaults = function () {
    return {
      enabled: true, mode: "both",            // both | sun | lights  (which light kinds are rendered)
      sun: { azimuth: 225, altitude: 30, color: "#fff1d0", intensity: 1, softness: 0.3, tint: 0 },
      lights: [], sel: -1,
      ambient: 0.35, terrain_shade: 0.5, height_scale: 1, roof_pitch: true,
      shadow: { color: "#141a2e", opacity: 0.55, blur_ft: 0.4, max_length_ft: 300, terrain: true, buildings: true },
      glow: { enabled: true, opacity: 0.6 },
      vector: false, auto: false, preview_dpi: 60, dpi: 150, embed: false, preset: "", capture: [],
      f3d: VB.f3dDefaults()
    };
  };
  VB.newLight = function (kind, n) {
    var presets = {
      lantern: { name: "Lantern", height: 8, radius: 70, color: "#ffb25a", intensity: 1, softness: 0.2 },
      torch: { name: "Torch", height: 7, radius: 60, color: "#ff9a40", intensity: 0.9, softness: 0.3 },
      bonfire: { name: "Bonfire", height: 5, radius: 100, color: "#ff8a3a", intensity: 1, softness: 0.8 },
      beacon: { name: "Tower beacon", height: 60, radius: 260, color: "#ffd890", intensity: 0.8, softness: 0.4 }
    };
    var p = presets[kind] || presets.lantern;
    return { id: "light_" + n, name: p.name + " " + n, enabled: true, x: 0, y: 0, height: p.height, radius: p.radius, color: p.color, intensity: p.intensity, softness: p.softness };
  };
  VB.LIGHTING_PRESETS = {
    morning: { label: "Morning", mode: "sun", sun: { azimuth: 95, altitude: 18, color: "#ffd9a8", intensity: 1, softness: 0.4, tint: 0.12 }, ambient: 0.42, shadow: { color: "#2a2f55", opacity: 0.5 } },
    noon: { label: "Noon", mode: "sun", sun: { azimuth: 180, altitude: 68, color: "#fffbe8", intensity: 1, softness: 0.2, tint: 0 }, ambient: 0.4, shadow: { color: "#1c2236", opacity: 0.45 } },
    afternoon: { label: "Afternoon", mode: "sun", sun: { azimuth: 250, altitude: 28, color: "#ffe0a0", intensity: 1, softness: 0.3, tint: 0.1 }, ambient: 0.38, shadow: { color: "#1c2240", opacity: 0.55 } },
    dusk: { label: "Dusk, long shadows", mode: "sun", sun: { azimuth: 285, altitude: 7, color: "#ff9c5a", intensity: 1, softness: 0.55, tint: 0.28 }, ambient: 0.3, shadow: { color: "#1a1838", opacity: 0.62, max_length_ft: 500 } },
    night: { label: "Night with torchlight", mode: "both", sun: { azimuth: 120, altitude: 40, color: "#a8b8ff", intensity: 0.25, softness: 0.5, tint: 0 }, ambient: 0.14, shadow: { color: "#0a1230", opacity: 0.8 } }
  };
  VB.applyLightingPreset = function (st, key) {
    var p = VB.LIGHTING_PRESETS[key]; if (!p) return st;
    var L = st.lighting;
    L.mode = p.mode; L.sun = Object.assign({}, L.sun, p.sun); L.ambient = p.ambient;
    L.shadow = Object.assign({}, L.shadow, { max_length_ft: 300 }, p.shadow); L.preset = key; L.enabled = true;
    return st;
  };

  // full config for lighting.py (lighting.json)
  VB.lightingConfig = function (st) {
    var L = st.lighting, n = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
    var lights = [];
    if (L.mode !== "lights") {
      var s = L.sun;
      lights.push({ id: "sun", type: "sun", enabled: true, azimuth: ((n(s.azimuth, 225) % 360) + 360) % 360, altitude: n(s.altitude, 30), color: s.color, intensity: n(s.intensity, 1), softness: n(s.softness, 0.3), tint: n(s.tint, 0) });
    }
    if (L.mode !== "sun") (L.lights || []).forEach(function (l) {
      lights.push({ id: l.id, type: "point", enabled: l.enabled !== false, x: n(l.x, 0), y: n(l.y, 0), height: n(l.height, 6), radius: Math.max(5, n(l.radius, 60)), color: l.color, intensity: n(l.intensity, 1), softness: n(l.softness, 0.3) });
    });
    var sh = L.shadow;
    return {
      enabled: L.enabled !== false, ambient: n(L.ambient, 0.35), terrain_shade: n(L.terrain_shade, 0.5), height_scale: n(L.height_scale, 1), roof_pitch: L.roof_pitch !== false,
      shadow: { color: sh.color, opacity: n(sh.opacity, 0.55), blur_ft: n(sh.blur_ft, 0.4), max_length_ft: n(sh.max_length_ft, 300), terrain: sh.terrain !== false, buildings: sh.buildings !== false },
      glow: { enabled: L.glow.enabled !== false, opacity: n(L.glow.opacity, 0.6) }, vector: !!L.vector, lights: lights
    };
  };

  // position (feet) from a get_selection result: selected anchors if any, else the one point, else the path's bounding-box centre
  VB.pickPointFt = function (view, sel) {
    var path = sel.paths[0], idx = (path.selected && path.selected.length) ? path.selected : (path.points.length === 1 ? [0] : null);
    var pts = idx ? idx.map(function (i) { return path.points[i]; }) : path.points;
    var f = pts.map(function (p) { return VB.docToFt(view, sel.artboard, p.a); });
    var xs = f.map(function (p) { return p[0]; }), ys = f.map(function (p) { return p[1]; });
    var avg = function (a) { return a.reduce(function (s, v) { return s + v; }, 0) / a.length; };
    var mid = function (a) { return (Math.min.apply(null, a) + Math.max.apply(null, a)) / 2; };
    return idx ? [VB.round1(avg(xs)), VB.round1(avg(ys))] : [VB.round1(mid(xs)), VB.round1(mid(ys))];
  };
  VB.jobLightCapture = function (st, d) {
    return {
      kind: "capture_light", label: "Capture light position", params: { view: st.settings.view },
      steps: [
        VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        VB.steps.host({ action: "get_selection" }, "read selection"),
        { t: "fn", label: "convert to feet", fn: function (run) {
          var p = VB.pickPointFt(run.vars.view, run.last);
          run.setState("lighting.capture", p); run.log("light position " + p[0] + ", " + p[1] + " ft"); } }
      ]
    };
  };

  // first layer of `list` that exists in a get_layer_tree result (top-level names), else the array itself (an older host.jsx cannot take arrays)
  VB.resolveBelow = function (list, treeRes) {
    var tree = treeRes && treeRes.tree; if (!tree) return list;
    var names = {}; tree.forEach(function (n) { names[n.name] = true; });
    for (var i = 0; i < list.length; i++) if (names[list[i]]) return list[i];
    return list[list.length - 1];
  };

  // render job. opts {preview: true} renders at lighting.preview_dpi
  VB.jobLighting = function (st, d, opts) {
    opts = opts || {};
    var L = st.lighting, out = d.panel + "/lighting", dpi = opts.preview ? (+L.preview_dpi || 60) : (+L.dpi || +st.settings.dpi || 150);
    var cfgPath = d.panel + "/lighting_cfg.json";
    var args = ["--place", st.place].concat(VB.viewFlags(st), ["--config", cfgPath, "--dpi", String(dpi), "--out-dir", out], VB.srcFlags(st));
    if (L.vector) args.push("--vector");
    return {
      kind: opts.preview ? "lighting_preview" : "lighting", label: (opts.preview ? "Preview shadows (" : "Render shadows (") + dpi + " dpi)",
      params: { lighting: L, scale: st.scale.scale_ft_per_in, dpi: dpi },
      steps: [
        { t: "write", path: cfgPath, data: VB.lightingConfig(st), label: "lighting config" },
        VB.steps.py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        VB.steps.py(GEN + "lighting.py", args, "lighting.py"),
        { t: "fn", label: "place shadow layers", fn: async function (run) {
          var info = run.readJson(out + "/lighting.json", null);
          if (!info) throw new Error("lighting.json missing");
          var rect = VB.imageRect(run.vars.view, info.bounds_ft), have = {};
          var tree = await run.host({ action: "get_layer_tree" }, true);
          for (var i = 0; i < info.layers.length; i++) {
            var l = info.layers[i]; have[l.layer] = true;
            await run.host({ action: "place_image", path: out + "/" + l.png, rect: rect, layer: l.layer, below: VB.resolveBelow(VB.fillBelow(l.layer), tree), name: l.name, lock: true, embed: VB.embedOn(st) }, true);
          }
          if (!have[VB.GLOW_LAYER]) await run.host({ action: "remove_item", layer: VB.GLOW_LAYER, name: "light_glow_png" }, true);
          if (info.vector) {
            await run.host({ action: "replace_layer", path: out + "/" + info.vector.svg, names: [VB.SHADOW_VECTOR_LAYER], restore_lock: false }, true);
            run.log("vector shadows: " + info.vector.polygons + " polygons on LINES/Shadows");
          }
        } }
      ]
    };
  };
  VB.jobLightingClear = function () {
    return { kind: "lighting_clear", label: "Remove shadow and glow images", params: {}, steps: [
      VB.steps.host({ action: "remove_item", layer: VB.SHADOW_LAYER, name: "shadows_png" }, "remove shadows", true),
      VB.steps.host({ action: "remove_item", layer: VB.GLOW_LAYER, name: "light_glow_png" }, "remove glow", true)] };
  };

  // ---------------------------------------------------------------- Foundry 3D lighting: light budget, lighting mode, sun / ambient flags (generators/foundry_lightbudget.py, `set-lighting`)
  // Constants mirror foundry_lightbudget.py (test_lighting_jobs.js checks both give the same numbers).
  VB.F3D = { HYBRID_MAX: 16, AUTO_HYBRID_ABOVE: 64, AUTO_GLOBAL_ABOVE: 150, SAFE_VISIBLE_LIGHTS: 150, COST_PER_LIGHT: 0.02, COST_PER_SHADOW_LIGHT: 0.6, GLOBAL_AMBIENT: 0.55, HYBRID_AMBIENT: 0.45 };
  VB.F3D_TIMES = { "": "keep the scene's time", dawn: "Dawn", noon: "Noon", dusk: "Dusk", night: "Night" };
  VB.f3dDefaults = function () {
    // defaults leave small scenes exactly as before: mode "auto" keeps every light up to 64 lights, no scale, no flag writes
    return { mode: "auto", maxLights: 0, radiusScale: 1, intensityScale: 1, windows: true, hearths: true, shadows: "", renderLights: "", applyFlags: false, timeOfDay: "", gi: 0.35, giColor: "#ffffff", sunStrength: 1, sunColor: "#fff1d0", last: null };
  };
  // "Performance mode": few lights + ambient fill, no windows, no light shadows
  VB.f3dPerformance = function (st) { var f = st.lighting.f3d; f.mode = "hybrid"; f.maxLights = 12; f.windows = false; f.shadows = "off"; f.radiusScale = 1; f.intensityScale = 1; return st; };
  VB.f3dReset = function (st) { st.lighting.f3d = VB.f3dDefaults(); return st; };
  VB.f3dExcluded = function (f) { var x = []; if (f.windows === false) x.push("window"); if (f.hearths === false) x.push("hearth"); return x; };
  // light budget options (push-lights, push-scene-3d): the mode is always passed, the rest only when they differ from the do-nothing value
  VB.f3dBudgetArgs = function (st) {
    var f = (st.lighting && st.lighting.f3d) || VB.f3dDefaults(), a = ["--lighting-mode", f.mode || "auto"], n = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
    if (n(f.maxLights, 0) > 0) a.push("--max-lights", String(Math.round(n(f.maxLights, 0))));
    var ex = VB.f3dExcluded(f); if (ex.length) a.push("--exclude-types", ex.join(","));
    if (n(f.radiusScale, 1) !== 1) a.push("--light-radius-scale", String(n(f.radiusScale, 1)));
    if (n(f.intensityScale, 1) !== 1) a.push("--light-intensity-scale", String(n(f.intensityScale, 1)));
    return a;
  };
  // set-lighting on the picked existing scene (dry run unless apply)
  VB.f3dSetArgs = function (st, d, apply) {
    var fo = st.foundry || {}; if (fo.target !== "existing" || !fo.sceneUuid) throw new Error("pick an existing scene on the Foundry tab first (Refresh from Foundry)");
    var f = st.lighting.f3d, n = function (v, d0) { v = Number(v); return isFinite(v) ? v : d0; };
    var a = ["set-lighting", "--scene-uuid", fo.sceneUuid, "--place", st.place, "--placements", VB.packDir(d) + "/placements.json"].concat(VB.f3dBudgetArgs(st));
    if (f.shadows) a.push("--light-shadows", f.shadows);
    if (f.renderLights) a.push("--render-scene-lights", f.renderLights);
    if (f.applyFlags) {
      if (f.timeOfDay) a.push("--time-of-day", f.timeOfDay);
      a.push("--ambient", String(n(f.gi, 0.35)), "--ambient-color", f.giColor || "#ffffff", "--sun-strength", String(n(f.sunStrength, 1)), "--sun-color", f.sunColor || "#fff1d0");
    }
    if (apply) a.push("--apply");
    return a;
  };
  // plain-language plan for n pipeline lights (same rules as foundry_lightbudget.resolve_mode / estimate_cost)
  VB.f3dPlan = function (n, f) {
    var K = VB.F3D, cap = Math.max(0, Math.round(Number(f.maxLights) || 0)), mode = f.mode || "auto", why, on;
    if (mode === "auto") {
      if (n > K.AUTO_GLOBAL_ABOVE) { mode = "global"; why = "auto: " + n + " lights is more than " + K.AUTO_GLOBAL_ABOVE + ", so global illumination is used instead of point lights"; }
      else if (n > K.AUTO_HYBRID_ABOVE) { mode = "hybrid"; cap = cap || K.HYBRID_MAX; why = "auto: " + n + " lights is more than " + K.AUTO_HYBRID_ABOVE + ", so only the " + cap + " most important are kept and ambient light fills in"; }
      else { mode = "lights"; why = "auto: " + n + " lights is at most " + K.AUTO_HYBRID_ABOVE + ", so every light is kept"; }
    } else if (mode === "global") why = "global: no point lights, ambient + sun only";
    else if (mode === "hybrid") { cap = cap || K.HYBRID_MAX; why = "hybrid: the " + cap + " most important lights + ambient"; }
    else why = "lights: " + (cap ? "capped at " + cap : "every light kept");
    on = mode === "global" ? 0 : (cap ? Math.min(cap, n) : n);
    var sh = f.shadows === "on" ? on : (/^\d+$/.test(f.shadows || "") ? Math.min(on, +f.shadows) : 0);
    var rel = 1 + K.COST_PER_LIGHT * on + K.COST_PER_SHADOW_LIGHT * sh;
    return { mode: mode, on: on, off: n - on, reason: why, shadow: sh, relative: Math.round(rel * 100) / 100, label: rel <= 1.25 ? "low" : rel <= 2 ? "medium" : rel <= 4 ? "high" : "very high",
      warn: on > K.SAFE_VISIBLE_LIGHTS ? on + " visible lights is above " + K.SAFE_VISIBLE_LIGHTS + ": on the test GPU 206 lights ran at about 28 ms and 306 drew nothing (shader limit). Lower the budget." : "" };
  };
  VB.jobSetLighting = function (st, d, apply) {
    var args = VB.f3dSetArgs(st, d, apply);
    return { kind: "set_lighting", label: "Foundry lighting" + (apply ? " (apply)" : " (dry run)"), params: { apply: !!apply }, steps: [
      VB.steps.py(VB.FOUNDRY_PY || (GEN + "foundry_push.py"), args, "set-lighting", { json: "sl" }),
      { t: "fn", label: "store result", fn: function (run) {
        var r = run.vars.sl; if (!r || r.ok === false) throw new Error((r && r.error) || "set-lighting gave no result");
        run.setState("lighting.f3d.last", { at: new Date().toISOString(), applied: !!r.applied, scene: r.scene, mode: r.mode, reason: r.reason, pipeline: r.pipeline_lights, on: r.lights_on_after, off: r.lights_off_after,
          kept: r.kept_by_kind, shadow: r.shadow_casters_after, flags: r.flag_changes, cost: r.cost_after, cost_now: r.cost_now, pack: r.pack_lights });
        run.log((r.applied ? "applied: " : "dry run: ") + r.lights_on_after + " of " + r.pipeline_lights + " lights on (" + r.mode + "), cost " + r.cost_now.label + " -> " + r.cost_after.label + ". " + r.reason);
      } }] };
  };
  // push-lights / push-scene-3d carry the same budget (core.js / tools.js build the base command; this appends the options)
  if (VB.jobPushLights) {
    var baseJPL = VB.jobPushLights;
    VB.jobPushLights = function (st, d, dry) { var j = baseJPL(st, d, dry), s = j.steps[0]; if (Array.isArray(s.args)) s.args = s.args.concat(VB.f3dBudgetArgs(st)); return j; };
  }
  // tools.js loads after this file, so the one-shot 3D scene command is wrapped once at start-up (lighting_ui.js init calls this; tests call it too)
  VB.f3dWrapLate = function () {
    if (!VB.scene3dArgs || VB.scene3dArgs.f3d) return;
    var baseS3 = VB.scene3dArgs;
    VB.scene3dArgs = function (st, d, dry) { var a = baseS3(st, d, dry); return a.indexOf("--with-lights") >= 0 ? a.concat(VB.f3dBudgetArgs(st)) : a; };
    VB.scene3dArgs.f3d = true;
  };

  // state defaults for older panel_state files
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.lighting = VB.lightingDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
