// 3D water additions to VBCore (loaded after core.js): the "3D water (Foundry)" group of the Water tab. Presets river / pond / lake / ocean with sliders; the values are
// stored per place in panel_state.json (water3d) and read by the exporter (worldpack_water.py: material + node extras) and by foundry_water.py (tile script and
// parameters). Jobs: install the shader on the scene's water tiles, push the current values live. Pure logic, no DOM: also loaded by test/test_water_jobs.js.
// The table below is a copy of presets/water/presets.json (test_water_jobs.js fails if they differ). Python side: generators/water_presets.py, foundry_water.py.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  VB.WATER3D = {
   "params": {
    "flow_speed": {
     "label": "Flow speed",
     "min": 0,
     "max": 4,
     "step": 0.05,
     "unit": "ft/s",
     "hint": "How fast the ripple pattern drifts (river: along the channel, slope-scaled; lake/pond/ocean: along the wind)"
    },
    "wave_height": {
     "label": "Wave height",
     "min": 0,
     "max": 2,
     "step": 0.05,
     "unit": "",
     "hint": "Strength of the light waves (how much they tilt the surface and the sun glints)"
    },
    "wave_scale": {
     "label": "Wave scale",
     "min": 0.25,
     "max": 10,
     "step": 0.25,
     "unit": "x4 ft",
     "hint": "Ripple wavelength (1 = about 4 ft from crest to crest)"
    },
    "transparency": {
     "label": "Transparency",
     "min": 0,
     "max": 1,
     "step": 0.05,
     "unit": "",
     "hint": "0 = nearly opaque, 1 = clear (the bed shows through, most at the banks)"
    },
    "depth_tint": {
     "label": "Depth tint",
     "min": 0,
     "max": 1,
     "step": 0.05,
     "unit": "",
     "hint": "How much darker and bluer the water is away from the bank"
    },
    "foam": {
     "label": "Foam",
     "min": 0,
     "max": 1,
     "step": 0.05,
     "unit": "",
     "hint": "White foam at the shore (and crests on the ocean)"
    },
    "wind_dir": {
     "label": "Wind direction",
     "min": 0,
     "max": 360,
     "step": 5,
     "unit": "deg",
     "hint": "Compass bearing the wind blows toward, 0 = north, 90 = east (lake, pond, ocean; a river flows along its channel)"
    }
   },
   "presets": {
    "river": {
     "label": "River",
     "mode": "flow",
     "note": "Directional flow along the centreline, faster where the bed is steeper, foam at the banks",
     "flow_speed": 1.6,
     "wave_height": 0.6,
     "wave_scale": 1.0,
     "transparency": 0.55,
     "depth_tint": 0.5,
     "foam": 0.35,
     "wind_dir": 0,
     "slope_speed": 0.8,
     "shallow_color": "#5f9fb0",
     "deep_color": "#1f5670"
    },
    "pond": {
     "label": "Pond",
     "mode": "wind",
     "note": "Calm, small ripples, clear and still",
     "flow_speed": 0.08,
     "wave_height": 0.2,
     "wave_scale": 0.6,
     "transparency": 0.7,
     "depth_tint": 0.55,
     "foam": 0.0,
     "wind_dir": 45,
     "slope_speed": 0.0,
     "shallow_color": "#6aa89a",
     "deep_color": "#26566a"
    },
    "lake": {
     "label": "Lake",
     "mode": "wind",
     "note": "Broader gentle waves driven by the wind, a little shore foam",
     "flow_speed": 0.3,
     "wave_height": 0.4,
     "wave_scale": 3.0,
     "transparency": 0.5,
     "depth_tint": 0.65,
     "foam": 0.12,
     "wind_dir": 225,
     "slope_speed": 0.0,
     "shallow_color": "#5c9bb5",
     "deep_color": "#1a4a6e"
    },
    "ocean": {
     "label": "Ocean",
     "mode": "wind",
     "note": "Long swells, whitecaps and shore foam, wind driven",
     "flow_speed": 0.7,
     "wave_height": 1.0,
     "wave_scale": 8.0,
     "transparency": 0.35,
     "depth_tint": 0.8,
     "foam": 0.6,
     "wind_dir": 270,
     "slope_speed": 0.0,
     "shallow_color": "#4f9bb0",
     "deep_color": "#0f3a63"
    }
   },
   "kind_map": {
    "river": "river",
    "stream": "river",
    "brook": "river",
    "spring": "pond",
    "pond": "pond",
    "pool": "pond",
    "lake": "lake",
    "mere": "lake",
    "sea": "ocean",
    "ocean": "ocean",
    "coast": "ocean"
   },
   "default_preset": "lake"
  };
  VB.WATER3D_KEYS = Object.keys(VB.WATER3D.params);
  VB.water3dDefaults = function () { return { preset: "river", force: false, values: {}, scene_uuid: "", dry_run: true, last: null }; };
  var num = function (v, lo, hi, d) { v = Number(v); if (!isFinite(v)) return d; return Math.max(lo, Math.min(hi, v)); };
  // effective values of a preset: preset defaults overridden by what the user saved for it (clamped like water_presets.resolve)
  VB.water3dValues = function (st, preset) {
    var T = VB.WATER3D, base = T.presets[preset] || T.presets[T.default_preset], sv = ((st.water3d || {}).values || {})[preset] || {}, out = {};
    VB.WATER3D_KEYS.forEach(function (k) { var p = T.params[k]; out[k] = num(sv[k] !== undefined ? sv[k] : base[k], p.min, p.max, base[k]); });
    out.slope_speed = num(sv.slope_speed !== undefined ? sv.slope_speed : base.slope_speed, 0, 1, base.slope_speed);
    out.shallow_color = /^#[0-9a-fA-F]{6}$/.test(sv.shallow_color || "") ? sv.shallow_color : base.shallow_color;
    out.deep_color = /^#[0-9a-fA-F]{6}$/.test(sv.deep_color || "") ? sv.deep_color : base.deep_color;
    return out;
  };
  VB.water3dSetValue = function (st, preset, key, val) {
    var w = st.water3d; w.values = w.values || {}; w.values[preset] = w.values[preset] || {}; w.values[preset][key] = val;
  };
  VB.water3dResetPreset = function (st, preset) { if (st.water3d && st.water3d.values) delete st.water3d.values[preset]; };
  VB.water3dKindPreset = function (kind) { var T = VB.WATER3D; return T.kind_map[String(kind || "").toLowerCase()] || T.default_preset; };
  // command line of foundry_water.py (set-water pushes the CURRENT values of the shown preset, the other presets come from the saved panel_state.json)
  VB.water3dArgs = function (st, cmd, dry) {
    var w = st.water3d, a = [cmd, "--scene-uuid", w.scene_uuid || "", "--place", st.place];
    if (cmd === "set-water") {
      a.push("--preset", w.preset); if (w.force) a.push("--force");
      var v = VB.water3dValues(st, w.preset);
      Object.keys(v).forEach(function (k) { a.push("--set", k + "=" + v[k]); });
    } else a.push("--enable-scripts");
    if (dry) a.push("--dry-run");
    return a;
  };
  function job(kind, label, cmd) {
    return function (st, opts) {
      opts = opts || {}; var w = st.water3d, dry = opts.dry !== undefined ? opts.dry : w.dry_run !== false;
      return { kind: kind, label: label + (dry ? " (dry run)" : ""), params: { water3d: w, dry: dry },
        steps: [{ t: "fn", label: "check", fn: function () { if (!/^Scene\./.test(w.scene_uuid || "")) throw new Error("pick the Foundry scene (or paste its Scene.xxxx uuid)"); } },
          py(GEN + "foundry_water.py", function () { return VB.water3dArgs(st, cmd, dry); }, "foundry_water.py " + cmd, { json: "res" }),
          { t: "fn", label: "report", fn: function (run) {
            var r = run.vars.res || {};
            run.setState("water3d.last", { at: new Date().toISOString(), cmd: cmd, dry: dry, scene: r.scene, tiles: (r.tiles || []).map(function (t) { return t.status; }), warnings: r.warnings || [] });
            run.log(cmd + (dry ? " (dry run)" : "") + ": " + (r.tiles || []).map(function (t) { return t.id + " " + t.status; }).join(", ") + ((r.warnings || []).length ? "  WARNING: " + r.warnings.join("; ") : ""));
          } }] };
    };
  }
  VB.jobWaterInstall = job("water3d_install", "Install water shader", "install-water");
  VB.jobWaterApply = job("water3d_apply", "Push water settings", "set-water");
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.water3d = VB.water3dDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
