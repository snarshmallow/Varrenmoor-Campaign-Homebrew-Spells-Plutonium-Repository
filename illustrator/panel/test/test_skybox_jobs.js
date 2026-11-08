// Skybox tab jobs: argument building, list against the real python, scenes/import/apply against stubs (no Foundry, no writes to world/).
//   node illustrator/panel/test/test_skybox_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/skybox.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbsky-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, last = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const STUB = {
  list: { ok: true, fetched: "2026-01-01T00:00:00", lists: { scenes: [{ uuid: "Scene.src1", name: "Tavern" }, { uuid: "Scene.ours", name: "Ours" }] } },
  "import-scene": { ok: true, scene: "Scene.src1", scene_name: "Tavern", name: "imported_tavern", how: "mock", warnings: [], lighting_flags: { sunPosition: 9 }, preview: "x/imported_tavern_preview.png" },
  "set-flag": { ok: true, scene: "Scene.ours", asset: "assets/a.webp", flags: { "levels-3d-preview": { exr: "assets/a.webp" } }, applied: false }
};
const spawn = (py, args, o) => {
  const sub = args.find(a => /^(import-scene|set-flag|list)$/.test(a));
  const isScenes = args.some(a => /foundry_push\.py$/.test(a));
  if (sub === "import-scene" || sub === "set-flag" || isScenes) {
    last = args;
    const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
    const body = STUB[isScenes ? "list" : sub];
    setTimeout(() => { c.stdout.emit("data", JSON.stringify(body) + "\n"); c.emit("close", 0); }, 10);
    return c;
  }
  return cp.spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  check("defaults: clear_day, dry run on, no scene", st.skybox.preset === "clear_day" && st.skybox.dry_run === true && st.skybox.scene_uuid === "");
  st.skybox.preset = "dusk"; st.skybox.yaw = 30; st.skybox.viewer = "100, 200"; st.skybox.use_lighting_sun = true; st.skybox.width = "1024";
  const g = VB.skyGenerateArgs(st).join(" ");
  check("generate args", g === "generate --place bridgehollow --presets dusk --width 1024 --yaw 30 --viewer 100,200 --lighting bridgehollow", g);
  st.skybox.viewer = "garbage"; check("bad viewer is ignored", VB.skyGenerateArgs(st).indexOf("--viewer") < 0);
  let r = await runner.run(VB.jobSkyList(st));
  check("list job (real python) ok and has 5 presets", r.ok && st.skybox.list.length >= 5 && st.skybox.list[0].name === "clear_day", r.error);
  r = await runner.run(VB.jobSkyApply(st));
  check("apply without a scene fails cleanly", !r.ok && /pick the Foundry scene/.test(r.error || ""), r.error);
  r = await runner.run(VB.jobSkyScenes(st));
  check("scenes job stores the read-only list in the foundry cache", r.ok && st.foundry.cache.lists.scenes.length === 2, r.error);
  check("scenes job only lists", last.indexOf("list") >= 0 && last.indexOf("--kinds") >= 0 && last.indexOf("scenes") >= 0 && last.indexOf("--apply") < 0);
  st.skybox.import_scene = "bad"; r = await runner.run(VB.jobSkyImport(st));
  check("import needs a scene", !r.ok && /pick the Foundry scene/.test(r.error || ""), r.error);
  st.skybox.import_scene = "Scene.src1"; st.skybox.import_name = "imported_tavern";
  r = await runner.run(VB.jobSkyImport(st));
  const impArgs = last ? last.join(" ") : "";
  check("import job ok, selects the imported sky, keeps the report", r.ok && st.skybox.preset === "imported_tavern" && st.skybox.last.kind === "import" && st.skybox.last.lighting_flags.sunPosition === 9, r.error);
  check("import is invoked with import-scene only (read-only command, no --apply)", /import-scene --place bridgehollow --scene-uuid Scene.src1 --name imported_tavern/.test(impArgs) && impArgs.indexOf("--apply") < 0, impArgs);
  st.skybox.preset = "dusk"; st.skybox.scene_uuid = "Scene.ours"; st.skybox.apply_lighting = true;
  st.skybox.list = [{ name: "dusk", exists: true, lighting_flags: { sunPosition: 9, timeSync: "darkness" } }];
  r = await runner.run(VB.jobSkyApply(st));
  let a = last.join(" ");
  check("apply is a dry run by default (no --apply) and carries the lighting flags", r.ok && a.indexOf("--apply") < 0 && /--scene-flag sunPosition=9 --scene-flag timeSync="darkness"/.test(a) && /--scene-uuid Scene.ours/.test(a), a);
  st.skybox.dry_run = false; r = await runner.run(VB.jobSkyApply(st)); a = last.join(" ");
  check("real apply adds --apply and names the one scene", r.ok && a.indexOf("--apply") > 0 && a.split("--scene-uuid").length === 2, a);
  st.skybox.apply_lighting = false; check("lighting flags only when ticked", VB.skyApplyArgs(st, true).indexOf("--scene-flag") < 0);
  st.skybox.preset = "imported_tavern"; r = await runner.run(VB.jobSkyGenerate(st));
  check("imported skies cannot be regenerated", !r.ok && /fixed image/.test(r.error || ""), r.error);
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
