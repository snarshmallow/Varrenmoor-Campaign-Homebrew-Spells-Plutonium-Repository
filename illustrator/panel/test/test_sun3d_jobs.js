// Sun, shadows and fog block: preset loading, one-click apply, time-of-day interpolation, argument building, set-sun / preview jobs against a stub.
//   node illustrator/panel/test/test_sun3d_jobs.js
const fs = require("fs"), path = require("path"), os = require("os");
const VB = require("../lib/core.js"); require("../lib/lighting.js"); require("../lib/sun3d.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbsun-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, last = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const STUBS = { "foundry_push.py": { ok: true, applied: false, scene: "ZZ", preset: "warm_sunset", flag_changes: { exposure: 1.55, enableFog: true }, shadows: { instruction: "Each player: Shadow Quality = 4" }, cost: { extra_gpu_ms: 0.6, label: "low" }, sky: { sky: "assets/x.webp" } },
  "sun_preview.py": { ok: true, shadow_fraction: 0.2 } };
const spawn = (py, args, o) => {
  const key = Object.keys(STUBS).filter(k => args.some(a => a.endsWith(k)))[0];
  if (key) { last = args; const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
    setTimeout(() => { c.stdout.emit("data", JSON.stringify(STUBS[key]) + "\n"); c.emit("close", 0); }, 10); return c; }
  return require("child_process").spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  const presets = VB.sunLoadPresets(fs, d.presets + "/lighting");
  const ids = presets.map(p => p.id);
  check("twelve presets in order", ids.join(",") === "dawn,morning,noon,afternoon,golden_hour,dusk,night,foggy_morning,warm_sunset,overcast,high_mountain,storm", ids.join(","));
  check("every preset has sun, ambient, shadows, fog, sky, swatch, description", presets.every(p => p.sun && p.ambient && p.shadows && p.fog && p.sky && p.swatch && p.swatch.length === 3 && p.description));
  check("defaults = sunny afternoon, low ambient", st.lighting.sun3d.preset === "afternoon" && st.lighting.sun3d.ambient <= 0.1 && st.lighting.sun3d.fog === "off");
  check("older state gets sun3d", VB.normalize({ lighting: { ambient: 0.2 } }).lighting.sun3d.preset === "afternoon");
  VB.sunApplyPreset(st, presets.filter(p => p.id === "warm_sunset")[0]);
  const s = st.lighting.sun3d;
  check("one click sets everything (warm sunset)", s.preset === "warm_sunset" && s.altitude <= 8 && s.fog === "on" && s.shadows === "on" && /^#ff/.test(s.color) && s.ambient > 0);
  const night = presets.filter(p => p.id === "night")[0];
  check("dramatic skies present, sky look off by default", ["high_mountain", "storm", "golden_hour", "overcast"].every(i => ids.indexOf(i) >= 0) && st.lighting.sun3d.skyPreset === "");
  check("no preset repeats a sun direction in its sky block", presets.every(p => p.sky && p.sky.sun_bearing === undefined && p.sky.sun_alt === undefined));
  check("night is dim with a night sky", night.sun.strength < 0.8 && night.sky.preset === "night");
  // time of day slider
  const noon = VB.sunFromHour(presets, 12), mid = VB.sunFromHour(presets, 13.5), late = VB.sunFromHour(presets, 1);
  check("slider at noon = noon preset", noon.altitude === 65 && noon.azimuth === 180);
  check("slider blends noon..afternoon", mid.azimuth > 180 && mid.azimuth < 235 && mid.altitude < 65 && mid.altitude > 38, JSON.stringify(mid));
  check("slider wraps night to dawn and stays dim", late.strength < 0.9, JSON.stringify(late));
  // args
  let err = ""; try { VB.sunSetArgs(st, d, false, false); } catch (e) { err = e.message; }
  check("no scene picked is a clear error", /pick an existing scene/.test(err), err);
  st.foundry.target = "existing"; st.foundry.sceneUuid = "Scene.abc";
  let a = VB.sunSetArgs(st, d, false, false).join(" ");
  check("dry run args", /^set-sun --scene-uuid Scene\.abc --place bridgehollow --preset warm_sunset --sun-azimuth 265 --sun-altitude \d+ --sun-strength [\d.]+ --sun-color #ff9a4a .*--fog on --fog-color #f5b985 --fog-far \d+$/.test(a) && a.indexOf("--apply") < 0, a);
  s.makeSky = true; s.groundCast = "off"; s.sky = "preset";
  a = VB.sunSetArgs(st, d, true, false).join(" "); check("make-sky, ground-cast and apply args", /--make-sky --ground-cast off --apply$/.test(a), a);
  s.skyPreset = "storm"; a = VB.sunSetArgs(st, d, false, false).join(" "); check("sky look passed after the azimuth / altitude args, preview too", /--sun-azimuth 265 .*--sky-preset storm --make-sky/.test(a) && a.split("--sky-preset").length === 2 && VB.sunPreviewArgs(st, d).join(" ").indexOf("--sky-preset storm") > 0, a);
  s.skyPreset = ""; s.makeSky = true; s.groundCast = "off"; s.sky = "off"; a = VB.sunSetArgs(st, d, false, false).join(" "); check("sky off", /--sky off/.test(a) && a.indexOf("--make-sky") < 0, a);
  a = VB.sunSetArgs(st, d, true, true).join(" "); check("restore args", a === "set-sun --scene-uuid Scene.abc --place bridgehollow --restore --apply", a);
  // jobs
  let r = await runner.run(VB.jobSetSun(st, d, false, false)); check("set-sun job ok", r.ok, r.error);
  check("result stored", st.lighting.sun3d.last && st.lighting.sun3d.last.preset === "warm_sunset" && st.lighting.sun3d.last.applied === false && st.lighting.sun3d.last.cost.label === "low", JSON.stringify(st.lighting.sun3d.last));
  r = await runner.run(VB.jobSunPreview(st, d)); check("preview job ok", r.ok, r.error);
  check("preview args", last.indexOf("render") >= 0 && last.indexOf("--out") >= 0 && /live_bridgehollow\.png$/.test(last[last.length - 1]), last.join(" "));
  // push-scene-3d carries the preset only when ticked
  VB.scene3dArgs = function () { return ["push-scene-3d", "--place", "x"]; }; VB.sunWrapLate(); VB.sunWrapLate();
  check("off by default on push", VB.scene3dArgs(st, d, false).join(" ") === "push-scene-3d --place x");
  s.onPush = true; check("--sun-preset on push when ticked", VB.scene3dArgs(st, d, false).join(" ") === "push-scene-3d --place x --sun-preset warm_sunset");
  check("2D lightingConfig ignores sun3d", !("sun3d" in VB.lightingConfig(st)));
  VB.sunApplyPreset(st, presets.filter(p => p.id === "warm_sunset")[0]); check("applying a preset resets the sky look", st.lighting.sun3d.skyPreset === "");
  fs.rmSync(TMP, { recursive: true, force: true });
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
