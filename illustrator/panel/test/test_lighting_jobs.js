// Foundry 3D lighting block: defaults, argument building, plan/cost numbers (must equal foundry_lightbudget.py), set-lighting job against a stub.
//   node illustrator/panel/test/test_lighting_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/lighting.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vblight-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, last = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const STUB = { ok: true, applied: false, scene: "ZZ", mode: "hybrid", reason: "auto: 72 lights is more than 64, so only the 16 most important are kept and ambient light fills in", pipeline_lights: 72, lights_on_after: 16, lights_off_after: 56,
  kept_by_kind: { hearth: 16 }, shadow_casters_after: 0, flag_changes: { ambientLightIntensity: 0.45 }, cost_after: { relative: 1.32, label: "medium" }, cost_now: { relative: 2.44, label: "high" }, pack_lights: { hearth: 19, window: 53 } };
const spawn = (py, args, o) => {
  if (args.some(a => /foundry_push\.py$/.test(a))) {
    last = args; const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
    setTimeout(() => { c.stdout.emit("data", JSON.stringify(STUB) + "\n"); c.emit("close", 0); }, 10); return c;
  }
  return cp.spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  const f = st.lighting.f3d;
  check("defaults leave small scenes unchanged", f.mode === "auto" && f.maxLights === 0 && f.radiusScale === 1 && f.intensityScale === 1 && f.windows && f.hearths && f.shadows === "" && f.applyFlags === false && f.renderLights === "");
  check("older state without f3d gets the defaults", VB.normalize({ lighting: { ambient: 0.2 } }).lighting.f3d.mode === "auto");
  check("default budget args = mode only", JSON.stringify(VB.f3dBudgetArgs(st)) === '["--lighting-mode","auto"]');
  // same numbers as foundry_lightbudget.py (test_lightbudget.py)
  const m = (n, over) => VB.f3dPlan(n, Object.assign({}, VB.f3dDefaults(), over || {}));
  check("auto: 64 lights = all", m(64).mode === "lights" && m(64).on === 64);
  check("auto: 65 lights = hybrid 16", m(65).mode === "hybrid" && m(65).on === 16 && /65 lights is more than 64/.test(m(65).reason));
  check("auto: 150 hybrid, 151 global", m(150).mode === "hybrid" && m(151).mode === "global" && m(151).on === 0);
  check("warns above 150 visible lights", m(300, { mode: "lights" }).warn && !m(100, { mode: "lights" }).warn);
  check("cost 72 lights = 2.44 high (same as python)", m(72, { mode: "lights" }).relative === 2.44 && m(72, { mode: "lights" }).label === "high");
  check("cost global = 1.0 low", m(300, { mode: "global" }).relative === 1 && m(300, { mode: "global" }).label === "low");
  check("4 shadow lights are very high", m(10, { mode: "lights", shadows: "4" }).relative === 3.6 && m(10, { mode: "lights", shadows: "4" }).label === "high");
  check("max lights caps", m(100, { mode: "lights", maxLights: 30 }).on === 30);
  // performance mode and reset
  VB.f3dPerformance(st);
  check("performance mode: hybrid, 12, no windows, no light shadows", f.mode === "hybrid" && f.maxLights === 12 && f.windows === false && f.shadows === "off");
  const a = VB.f3dBudgetArgs(st).join(" ");
  check("budget args", a === "--lighting-mode hybrid --max-lights 12 --exclude-types window", a);
  f.radiusScale = 0.75; f.intensityScale = 1.5; f.hearths = false;
  check("scale and exclusion args", VB.f3dBudgetArgs(st).join(" ") === "--lighting-mode hybrid --max-lights 12 --exclude-types window,hearth --light-radius-scale 0.75 --light-intensity-scale 1.5");
  VB.f3dReset(st); check("reset", st.lighting.f3d.mode === "auto" && st.lighting.f3d.windows === true);
  // set-lighting needs a picked scene
  let err = ""; try { VB.f3dSetArgs(st, d, false); } catch (e) { err = e.message; }
  check("no scene picked is a clear error", /pick an existing scene/.test(err), err);
  st.foundry.target = "existing"; st.foundry.sceneUuid = "Scene.abc";
  let s = VB.f3dSetArgs(st, d, false).join(" ");
  check("dry run args (no --apply)", /^set-lighting --scene-uuid Scene\.abc --place bridgehollow --placements .*placements\.json --lighting-mode auto$/.test(s), s);
  st.lighting.f3d.applyFlags = true; st.lighting.f3d.timeOfDay = "dusk"; st.lighting.f3d.gi = 0.5; st.lighting.f3d.shadows = "4"; st.lighting.f3d.renderLights = "off";
  s = VB.f3dSetArgs(st, d, true).join(" ");
  check("flag args + apply", /--light-shadows 4 --render-scene-lights off --time-of-day dusk --ambient 0.5 --ambient-color #ffffff --sun-strength 1 --sun-color #fff1d0 --apply$/.test(s), s);
  st.lighting.f3d.applyFlags = false;
  s = VB.f3dSetArgs(st, d, false).join(" "); check("flags are not sent unless ticked", s.indexOf("--ambient") < 0 && s.indexOf("--time-of-day") < 0);
  // job against the stub
  let r = await runner.run(VB.jobSetLighting(st, d, false));
  check("job ok", r.ok, r.error);
  const L = st.lighting.f3d.last;
  check("result stored for the readout", L && L.on === 16 && L.pipeline === 72 && L.cost.label === "medium" && L.pack.window === 53 && L.applied === false, JSON.stringify(L));
  check("job spawned set-lighting without --apply", last.indexOf("set-lighting") >= 0 && last.indexOf("--apply") < 0);
  r = await runner.run(VB.jobSetLighting(st, d, true)); check("apply passes --apply", r.ok && last.indexOf("--apply") >= 0, r.error);
  // push-lights carries the budget; the one-shot scene wrapper too
  st.lighting.f3d.maxLights = 20; st.lighting.f3d.mode = "lights";
  const pl = VB.jobPushLights(st, d, true), pa = pl.steps[0].args.join(" ");
  check("push-lights gets the budget", /push-lights/.test(pa) && /--lighting-mode lights --max-lights 20$/.test(pa), pa);
  VB.scene3dArgs = function (s2, d2, dry) { return ["push-scene-3d", "--with-lights"]; }; VB.f3dWrapLate(); VB.f3dWrapLate();
  check("push-scene-3d with lights gets the budget once", VB.scene3dArgs(st, d, false).join(" ") === "push-scene-3d --with-lights --lighting-mode lights --max-lights 20", VB.scene3dArgs(st, d, false).join(" "));
  VB.scene3dArgs = function () { return ["push-scene-3d"]; }; delete VB.scene3dArgs.f3d; VB.f3dWrapLate();
  check("no lights, no budget args", VB.scene3dArgs(st, d, false).join(" ") === "push-scene-3d");
  // the 2D lighting config is not disturbed by the extra state
  check("lightingConfig ignores f3d", !("f3d" in VB.lightingConfig(st)));
  fs.rmSync(TMP, { recursive: true, force: true });
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
