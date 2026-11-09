// Streetlamps additions to VBCore (loaded after core.js, lighting.js): defaults, config builder, jobs and the lamp/light count readout.
// Pure logic, no DOM: also loaded by test/test_streetlamps_jobs.js. Python side: generators/streetlamps.py (plan / apply / preview), generators/streetlamps_scene.py (set-streetlamps).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  var n = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };

  VB.SL_STYLES = ["wrought_iron", "wooden_oil", "stone_pillar", "bracket_wall", "torch_post", "shepherd_crook"];
  VB.SL_SIDES = { alternating: "Alternating (one lamp per station, switching sides)", left: "Left of travel", right: "Right of travel", both: "Both sides (a pair per station)" };

  VB.streetlampsDefaults = function () {
    // enabled false: an untouched place exports exactly as before. Light numbers of 0 mean "the style's own value" (kelvin, radius, strength)
    return { enabled: false, style: "wooden_oil", spacing_ft: 60, side: "alternating", offset_ft: 1.5, height_ft: 0, classes: { main: true, side: true, dirt: true },
      skip_junction_ft: 20, skip_doors_ft: 8, skip_bridges: true, jitter_ft: 0, seed: 7, min_lamps: 2, extra: "", dry: true,
      light: { enabled: true, kelvin: 0, color: "", dim_ft: 0, bright_ft: 0, intensity: 0, flicker: true, shadows: false },
      last: null, scene: null };
  };
  VB.streetlampsConfig = function (st) {
    var s = st.streetlamps || VB.streetlampsDefaults(), L = s.light || {};
    return { enabled: !!s.enabled, style: s.style, spacing_ft: n(s.spacing_ft, 60), side: s.side, offset_ft: n(s.offset_ft, 1.5), height_ft: n(s.height_ft, 0),
      classes: ["main", "side", "dirt"].filter(function (k) { return (s.classes || {})[k]; }), skip_junction_ft: n(s.skip_junction_ft, 20), skip_doors_ft: n(s.skip_doors_ft, 8),
      skip_bridges: s.skip_bridges !== false, jitter_ft: n(s.jitter_ft, 0), seed: Math.round(n(s.seed, 7)), min_lamps: Math.round(n(s.min_lamps, 2)),
      light: { enabled: L.enabled !== false, kelvin: n(L.kelvin, 0), color: /^#[0-9a-f]{6}$/i.test(L.color || "") ? L.color : "", dim_ft: n(L.dim_ft, 0), bright_ft: n(L.bright_ft, 0),
        intensity: n(L.intensity, 0), flicker: L.flicker !== false, shadows: !!L.shadows } };
  };
  VB.streetlampsCfgPath = function (d) { return d.panel + "/streetlamps_cfg.json"; };
  VB.streetlampsBase = function (st, d) { return ["--place", st.place, "--pack", VB.packDir(d), "--config", VB.streetlampsCfgPath(d)]; };
  // placements.json files the lamps are written into: the full export (always) + one path per line of the "also write into" box (the merged optimized set)
  VB.streetlampsTargets = function (st, d) {
    var a = [VB.packDir(d) + "/placements.json"]; String((st.streetlamps || {}).extra || "").split(/\r?\n/).forEach(function (l) { l = l.trim(); if (l && a.indexOf(l) < 0) a.push(l); });
    return a;
  };
  function remember(run) {
    var r = run.vars.sl; if (!r || r.ok === false) throw new Error((r && r.error) || "streetlamps.py gave no result");
    run.setState("streetlamps.last", { at: new Date().toISOString(), lamps: r.lamps, lights: r.lights, by_class: r.by_class, by_style: r.by_style, skipped: r.skipped, other: r.other_lights,
      total_lights: r.total_lights, written: !!r.written, enabled: r.config && r.config.enabled, tris: r.written && r.written[0] && r.written[0].tris, roads: Object.keys(r.roads || {}).length });
    return r;
  }
  VB.jobStreetlampsPlan = function (st, d) {
    return { kind: "streetlamps_plan", label: "Streetlamps: preview (dry run)", params: { streetlamps: st.streetlamps }, steps: [
      { t: "write", path: VB.streetlampsCfgPath(d), data: VB.streetlampsConfig(st), label: "streetlamps config" },
      py(GEN + "streetlamps.py", ["plan"].concat(VB.streetlampsBase(st, d)), "streetlamps.py plan", { json: "sl" }),
      { t: "fn", label: "store counts", fn: function (run) {
        var r = remember(run), sk = r.skipped || {};
        run.log("dry run: " + r.lamps + " lamps, " + r.lights + " lights (" + JSON.stringify(r.by_class) + "); skipped: " + Object.keys(sk).map(function (k) { return sk[k] + " " + k; }).join(", "));
      } }] };
  };
  VB.jobStreetlampsApply = function (st, d) {
    var s = st.streetlamps;
    var args = ["apply"].concat(VB.streetlampsBase(st, d)); VB.streetlampsTargets(st, d).forEach(function (p) { args.push("--placements", p); });
    return { kind: "streetlamps_apply", label: s.enabled ? "Streetlamps: generate" : "Streetlamps: remove from the pack (switched off)", params: { streetlamps: s }, steps: [
      { t: "write", path: VB.streetlampsCfgPath(d), data: VB.streetlampsConfig(st), label: "streetlamps config" },
      py(GEN + "streetlamps.py", args, "streetlamps.py apply", { json: "sl" }),
      { t: "fn", label: "store counts", fn: function (run) {
        var r = remember(run), w = (r.written || [])[0] || {};
        run.log((s.enabled ? r.lamps + " lamps, " + r.lights + " lights written (" + (w.tris || 0) + " triangles, " + Math.round((w.bytes || 0) / 1024) + " KB)" : "lamp layer and lamp lights removed") + " in " + (r.written || []).length + " placements file(s)");
      } }] };
  };
  VB.jobStreetlampsThumbs = function () {
    return { kind: "streetlamps_thumbs", label: "Streetlamps: render style thumbnails", params: {}, steps: [py(GEN + "streetlamps.py", ["preview"], "streetlamps.py preview", { json: "th" })] };
  };
  // push the lamp layer (tile) + the pack's lights to the picked existing scene; the push prunes lamp lights that are no longer in the pack (switch-off flow)
  VB.jobStreetlampsPush = function (st, d) {
    var f = st.foundry || {}; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene on the Foundry tab first (Refresh from Foundry)");
    var a = ["push-models", "--place", st.place, "--placements", VB.packDir(d) + "/placements.json", "--scene-uuid", f.sceneUuid, "--layers", "streetlamps"].concat(VB.extraArgs ? VB.extraArgs(st, "push-models") : []);
    var lights = VB.jobPushLights(st, d, false).steps[0];
    return { kind: "streetlamps_push", label: "Streetlamps: push layer + lights", params: {}, steps: [py(VB.FOUNDRY_PY || (GEN + "foundry_push.py"), a, "push streetlamp tile"), lights] };
  };
  // set-streetlamps: on / off / retune on the picked scene (dry run unless apply)
  VB.streetlampsSceneArgs = function (st, d, mode, apply) {
    var f = st.foundry || {}; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene on the Foundry tab first (Refresh from Foundry)");
    var a = ["set-streetlamps", "--scene-uuid", f.sceneUuid];
    if (mode === "on") a.push("--on"); else if (mode === "off") a.push("--off"); else a.push("--light-config", VB.streetlampsCfgPath(d));
    if (apply) a.push("--apply");
    return a;
  };
  VB.jobStreetlampsScene = function (st, d, mode, apply) {
    var args = VB.streetlampsSceneArgs(st, d, mode, apply), steps = [];
    if (mode === "lights") steps.push({ t: "write", path: VB.streetlampsCfgPath(d), data: VB.streetlampsConfig(st), label: "streetlamps config" });
    steps.push(py(VB.FOUNDRY_PY || (GEN + "foundry_push.py"), args, "set-streetlamps", { json: "ss" }));
    steps.push({ t: "fn", label: "store result", fn: function (run) {
      var r = run.vars.ss; if (!r || r.ok === false) throw new Error((r && r.error) || "set-streetlamps gave no result");
      run.setState("streetlamps.scene", { at: new Date().toISOString(), applied: !!r.applied, scene: r.scene, tiles: r.lamp_tiles, lights: r.lamp_lights, tile_changes: r.tile_changes, light_changes: r.light_changes, mode: mode, warning: r.warning || "" });
      run.log((r.applied ? "applied: " : "dry run: ") + r.tile_changes + " tile change(s), " + r.light_changes + " light change(s) of " + r.lamp_lights + " lamp lights in " + r.scene + (r.warning ? ". " + r.warning : ""));
    } });
    return { kind: "streetlamps_scene_" + mode, label: "Streetlamps in scene: " + (mode === "lights" ? "retune lights" : mode) + (apply ? "" : " (dry run)"), params: { mode: mode, apply: !!apply }, steps: steps };
  };
  // plain-language lamp / light count with the light budget warning (same rules as VB.f3dPlan)
  VB.streetlampsReadout = function (st) {
    var s = st.streetlamps, l = s.last, lines = [];
    if (!l) return "Not counted yet: press Preview (dry run) to count the lamps this setup would place on the roads of the exported pack.";
    lines.push("Dry run " + String(l.at || "").replace("T", " ").slice(0, 19) + ": " + l.lamps + " lamps on " + l.roads + " road(s) -> " + l.lights + " lamp light(s)" + (s.light && s.light.enabled === false ? " (lights switched off: none will be made)" : "") + ".");
    if (l.by_class && Object.keys(l.by_class).length) lines.push("By class: " + Object.keys(l.by_class).map(function (k) { return l.by_class[k] + " " + k; }).join(", ") + ".");
    var sk = l.skipped || {}, sks = Object.keys(sk).filter(function (k) { return sk[k]; });
    if (sks.length) lines.push("Skipped positions: " + sks.map(function (k) { return sk[k] + " " + k.replace("_", " "); }).join(", ") + ".");
    var other = l.other ? Object.keys(l.other).reduce(function (a, k) { return a + l.other[k]; }, 0) : 0, lamps = (s.light && s.light.enabled === false) ? 0 : l.lights, total = other + lamps;
    var f = (st.lighting && st.lighting.f3d) || VB.f3dDefaults(), p = VB.f3dPlan(total, f);
    lines.push("Lights in the scene after the push: " + total + " (" + lamps + " lamps + " + other + " in the pack). Budget: " + p.on + " on (" + p.mode + "), cost " + p.relative + "x an empty scene (" + p.label + ").");
    if (p.warn) lines.push("WARNING: " + p.warn);
    else if (total > VB.F3D.AUTO_HYBRID_ABOVE) lines.push("Note: more than " + VB.F3D.AUTO_HYBRID_ABOVE + " lights: the Lighting tab budget (auto) will thin them; lamps keep priority 80 (above doors, hearths and windows).");
    if (s.light && s.light.shadows) lines.push("WARNING: light shadows on: each shadow-casting lamp renders the scene 6 more times per frame. Keep this off unless you only have a few lamps.");
    if (l.tris) lines.push("Lamp mesh: " + l.tris + " triangles in one tile.");
    return lines.join("\n");
  };
  // kelvin -> hex (same formula as streetlamps.py kelvin_to_hex), used for the colour swatch
  VB.kelvinToHex = function (k) {
    var t = Math.max(1000, Math.min(10000, n(k, 2000))) / 100, r, g, b;
    r = t <= 66 ? 255 : 329.698727446 * Math.pow(t - 60, -0.1332047592);
    g = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * Math.pow(t - 60, -0.0755148492);
    b = t >= 66 ? 255 : (t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307);
    return "#" + [r, g, b].map(function (v) { v = Math.round(Math.max(0, Math.min(255, v))); return (v < 16 ? "0" : "") + v.toString(16); }).join("");
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.streetlamps = VB.streetlampsDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
