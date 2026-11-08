// 3D water group of the Water tab: preset table equals presets/water/presets.json, value clamping, command lines, install / push jobs against a stubbed python (no Foundry, no writes).
//   node illustrator/panel/test/test_water_jobs.js
const fs = require("fs"), path = require("path"), os = require("os");
const VB = require("../lib/core.js"); require("../lib/water.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbwater-")), tmp = TMP.split(path.sep).join("/");
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, last = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const spawn = (py, args) => {
  last = args;
  const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
  const body = { ok: true, scene: "Scene.ours", tiles: [{ id: "model:bridgehollow:water", uuid: "Scene.ours.Tile.w", status: args.indexOf("--dry-run") >= 0 ? "would update" : "updated" }], warnings: [] };
  setTimeout(() => { c.stdout.emit("data", JSON.stringify(body) + "\n"); c.emit("close", 0); }, 5);
  return c;
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  const file = JSON.parse(fs.readFileSync(ROOT + "/illustrator/presets/water/presets.json", "utf8"));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  check("panel table equals presets.json (params, presets, kind_map)", same(VB.WATER3D.params, file.params) && same(VB.WATER3D.presets, file.presets) && same(VB.WATER3D.kind_map, file.kind_map) && VB.WATER3D.default_preset === file.default_preset);
  check("four presets", same(Object.keys(VB.WATER3D.presets), ["river", "pond", "lake", "ocean"]));
  check("defaults: river, not forced, dry run on", st.water3d.preset === "river" && st.water3d.force === false && st.water3d.dry_run === true && same(st.water3d.values, {}));
  check("kind -> preset", VB.water3dKindPreset("stream") === "river" && VB.water3dKindPreset("sea") === "ocean" && VB.water3dKindPreset("x") === "lake");
  let v = VB.water3dValues(st, "river");
  check("values = preset defaults", v.flow_speed === 1.6 && v.wave_scale === 1 && v.shallow_color === "#5f9fb0");
  VB.water3dSetValue(st, "river", "flow_speed", 99); VB.water3dSetValue(st, "river", "foam", -2); VB.water3dSetValue(st, "river", "deep_color", "nope");
  v = VB.water3dValues(st, "river");
  check("saved values are clamped, bad colour ignored", v.flow_speed === 4 && v.foam === 0 && v.deep_color === "#1f5670" && VB.water3dValues(st, "lake").flow_speed === 0.3);
  VB.water3dSetValue(st, "river", "flow_speed", 2.5);
  VB.water3dResetPreset(st, "river"); check("reset drops the saved values", VB.water3dValues(st, "river").flow_speed === 1.6);
  VB.water3dSetValue(st, "lake", "wind_dir", 90); st.water3d.preset = "lake"; st.water3d.scene_uuid = "Scene.ours";
  let a = VB.water3dArgs(st, "set-water", true).join(" ");
  check("set-water args carry the shown preset's values", /^set-water --scene-uuid Scene.ours --place bridgehollow --preset lake --set flow_speed=0.3 /.test(a) && /--set wind_dir=90 /.test(a) && /--dry-run$/.test(a) && a.indexOf("--force") < 0, a);
  st.water3d.force = true; check("force flag", VB.water3dArgs(st, "set-water", false).indexOf("--force") > 0);
  check("install args enable scripts", /^install-water .* --enable-scripts$/.test(VB.water3dArgs(st, "install-water", false).join(" ")));
  st.water3d.scene_uuid = ""; let r = await runner.run(VB.jobWaterInstall(st));
  check("install needs a scene", !r.ok && /pick the Foundry scene/.test(r.error || ""), r.error);
  st.water3d.scene_uuid = "Scene.ours"; r = await runner.run(VB.jobWaterInstall(st));
  check("install is a dry run by default and reports", r.ok && last.join(" ").indexOf("--dry-run") > 0 && /foundry_water\.py$/.test(last.filter(x => /foundry_water/.test(x))[0] || "") && st.water3d.last.tiles[0] === "would update", r.error + " " + (last || []).join(" "));
  st.water3d.dry_run = false; r = await runner.run(VB.jobWaterApply(st));
  check("real push has no --dry-run", r.ok && last.join(" ").indexOf("--dry-run") < 0 && st.water3d.last.tiles[0] === "updated" && st.water3d.last.dry === false, r.error);
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
