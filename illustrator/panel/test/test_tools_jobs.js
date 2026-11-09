// Tools tab: argument building for audits, bake-texture, delete-scene (typed-name gate), push-scene-3d and the advanced-option hooks into the Foundry tab jobs.
// Python is stubbed (no Foundry, no writes).   node illustrator/panel/test/test_tools_jobs.js
const fs = require("fs"), path = require("path"), os = require("os");
const VB = require("../lib/core.js"); require("../lib/padding.js"); require("../lib/tools.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbtools-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
fs.mkdirSync(d.panel, { recursive: true });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, calls = [];
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const throws = (f) => { try { f(); return false; } catch (e) { return true; } };
const spawn = (py, args) => {
  calls.push(args);
  const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
  setTimeout(() => { c.stdout.emit("data", JSON.stringify({ ok: true, window_ft: [100, 200, 2400, 1800] }) + "\n"); c.emit("close", 0); }, 5);
  return c;
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
const has = (a, ...x) => x.every(v => a.indexOf(v) >= 0);
(async () => {
  check("state carries tools defaults", st.tools && st.tools.audits.bga_top === 12 && st.tools.s3d.dry_run === true && st.tools.scene.upscale === 1);
  // defaults add nothing to the existing jobs
  st.foundry.target = "existing"; st.foundry.sceneUuid = "Scene.abc";
  const base = VB.worldPushArgs(st, d, {}).join(" ");
  check("push-models: defaults add no advanced flags", !/--ids|--serve-url|--assets-dir|--set-name|--table-texture|--scene-flag|--collision-lod|--yes/.test(base), base);
  st.tools.push.ids = "bld_a,bld_b"; st.tools.push.serve_url = "http://x:30000"; st.tools.push.table_texture = "art/p/ground.webp"; st.tools.push.scene_flags = 'a=1\nb="x"'; st.tools.push.yes = true; st.tools.push.collision_lod = "terrain=0.5";
  const pa = VB.worldPushArgs(st, d, { dry: true });
  check("push-models: advanced flags passed", has(pa, "--ids", "bld_a,bld_b", "--serve-url", "http://x:30000", "--table-texture", "art/p/ground.webp", "--collision-lod", "terrain=0.5", "--yes", "--dry-run") && pa.filter(x => x === "--scene-flag").length === 2, pa.join(" "));
  check("set-collision passes collision-lod", has(VB.jobSetCollision(st, false).steps[0].args, "--collision-lod", "terrain=0.5"));
  st.tools.walls.profile = "water:sight=10\nfences:sound=0"; st.tools.walls.foliage_json = "f.json";
  const wa = VB.jobPushWalls(st, false).steps[0].args;
  check("push-walls passes profiles and foliage json", wa.filter(x => x === "--wall-profile").length === 2 && has(wa, "--foliage-json", "f.json"), wa.join(" "));
  // push-scene options
  st.foundry.target = "new"; st.foundry.sceneName = "S";
  check("push-scene defaults add nothing", !/--upscale|--padding|--max-px|--format|--link/.test(VB.foundryPushSceneArgs(st, { image: "x.png" }).join(" ")));
  Object.assign(st.tools.scene, { upscale: 2, padding: 0.25, max_px: 4096, format: "png", link: true });
  check("push-scene options passed", has(VB.foundryPushSceneArgs(st, { image: "x.png" }), "--upscale", "2", "--padding", "0.25", "--max-px", "4096", "--format", "png", "--link"));
  // lights, import, token, actor, export, split, merge, publish
  Object.assign(st.tools.lights, { animation: "pulse", prune: true, placements: "p.json", lighting: "bh" });
  st.foundry.target = "existing";
  check("push-lights options", has(VB.jobPushLights(st, d, true).steps[0].args, "--light-animation", "pulse", "--prune-lights", "--lights-placements", "p.json", "--lighting", "bh", "--dry-run"));
  Object.assign(st.tools.imp, { no_image: true, force: true, scene_json: "s.json" });
  check("import-scene options", has(VB.extraArgs(st, "import-scene"), "--no-image", "--force", "--scene-json", "s.json"));
  Object.assign(st.tools.tok, { hidden: true, key: "k", px: "10,20", portrait: "a.png", token: "b.png" });
  check("token / actor options", has(VB.extraArgs(st, "push-token"), "--hidden", "--key", "k", "--px", "10,20") && has(VB.extraArgs(st, "push-actor"), "--portrait", "a.png", "--token", "b.png"));
  Object.assign(st.tools.exp, { terrain_source: "carved", lod: "1,2", px_per_ft: 10, z_origin_ft: -5, no_textures: true, textures: "embed", step: 2, no_hidden_removal: true });
  const ex = VB.jobWorldPack(st, d).steps[0].args;
  check("worldpack export options", has(ex, "--terrain-source", "carved", "--lod", "1,2", "--px-per-ft", "10", "--z-origin-ft", "-5", "--no-textures"), ex.join(" "));
  check("split / merge options", has(VB.jobWorldSplit(st, d).steps[0].args, "--textures", "embed", "--step", "2") && has(VB.jobWorldMerge(st, d).steps[0].args, "--no-hidden-removal"));
  check("publish --yes", has(VB.jobWorldPublish(st, d).steps[0].args, "--yes"));
  check("object edit --dry only when ticked", VB.extraArgs(st, "object-edit").length === 0 && (st.tools.objdry = true) && has(VB.extraArgs(st, "object-edit"), "--dry"));
  // audits
  Object.assign(st.tools.audits, { bga_top: 5, bga_nomesh: true, rha_mesh: "graded", rha_smooth: 0.3, rha_cutfill: true, ta_padding: true, ta_raw: true, ta_tag: "t1" });
  check("building ground audit args", has(VB.jobToolsBuildingGround(st, d).steps[0].args(), "--place", place, "--top", "5", "--no-mesh", "--pack", d.world + "/export"));
  check("road height audit args", has(VB.jobToolsRoadHeight(st, d).steps[0].args(), "--mesh", "graded", "--smooth", "0.3", "--cutfill", "--step-ft", "4"));
  check("textures audit args", has(VB.jobToolsTexturesAudit(st).steps[0].args(), "--tag", "t1", "--padding", "--raw"));
  check("terrain check args", has(VB.jobToolsTerrainCheck(st).steps[0].args(), "--minor", "10", "--index", "50"));
  check("scene audit needs a picked scene", (st.foundry.target = "new", throws(() => VB.jobToolsSceneAudit(st, d))));
  st.foundry.target = "existing";
  check("scene audit args", has(VB.jobToolsSceneAudit(st, d).steps[0].args, "scene-audit", "--scene-uuid", "Scene.abc"));
  // bake
  check("bake refuses without image / window", throws(() => VB.bakeArgs(st, d, false)));
  st.tools.bake.image = "m.png"; check("bake refuses without window or px/ft", throws(() => VB.bakeArgs(st, d, false)));
  st.tools.bake.window = "0,0,2400,1800"; st.tools.bake.crop_margin_pt = 36;
  check("bake crop margin needs dpi", throws(() => VB.bakeArgs(st, d, false)));
  st.tools.bake.dpi = 120;
  const ba = VB.bakeArgs(st, d, true);
  check("bake args", has(ba, "bake-texture", "--image", "m.png", "--window", "0,0,2400,1800", "--crop-margin-pt", "36", "--dpi", "120", "--publish", "--out-dir", d.world + "/export/baked"), ba.join(" "));
  check("bake local has no --publish", VB.bakeArgs(st, d, false).indexOf("--publish") < 0);
  st.tools.bake.window = "1,2,3"; check("bake rejects a malformed window", throws(() => VB.bakeArgs(st, d, false)));
  check("window from export-info", VB.windowFromInfo({ window_ft: [100, 200, 2400, 1800] }) === "100,200,2500,2000");
  calls = []; let r = await runner.run(VB.jobToolsBakeWindow(st, d));
  check("fill window job sets window and image", r.ok && st.tools.bake.window === "100,200,2500,2000" && /view_export\.png$/.test(st.tools.bake.image), r.error);
  // delete scene gate
  st.foundry.cache = { fetched: "x", lists: { scenes: [{ uuid: "Scene.abc", name: "Dyer's Walk" }, { uuid: "Scene.zzz", name: "Keep" }] } };
  st.tools.del.typed = "";
  check("delete refused without typed name", throws(() => VB.jobToolsDeleteScene(st)) && !VB.deleteSceneOk(st));
  st.tools.del.typed = "dyer's walk"; check("delete refused on wrong case", throws(() => VB.jobToolsDeleteScene(st)));
  st.tools.del.typed = "Dyer's Walk"; check("delete armed by exact name", VB.deleteSceneOk(st));
  st.foundry.target = "new"; check("delete refused for a new-scene target", throws(() => VB.jobToolsDeleteScene(st)));
  st.foundry.target = "existing";
  calls = []; r = await runner.run(VB.jobToolsDeleteScene(st));
  check("delete runs delete-scene with the uuid", r.ok && calls.some(a => has(a, "delete-scene", "--scene-uuid", "Scene.abc")), r.error);
  check("delete forgets the scene and clears the box", st.foundry.sceneUuid === "" && st.tools.del.typed === "" && st.foundry.cache.lists.scenes.length === 1);
  // scene 3d
  st.foundry.sceneUuid = "Scene.zzz";
  const s3 = VB.scene3dArgs(st, d, true);
  check("scene-3d args: scene, placements, padding from the Padding tab, dry run", has(s3, "push-scene-3d", "--scene-uuid", "Scene.zzz", "--dry-run") && s3.some(x => x === "--padding-arg=--preset") && s3.some(x => x === "--padding-arg=bowl-ridge") && !s3.some(x => /^--padding-arg=--(place|out)$/.test(x)), s3.join(" "));
  Object.assign(st.tools.s3d, { no_padding: true, no_skybox: true, with_lights: true, prune_lights: true, foliage_placements: "f.json", layers: "terrain,roads", skybox_preset: "dusk" });
  const s4 = VB.scene3dArgs(st, d, false);
  check("scene-3d switches", has(s4, "--no-padding", "--no-skybox", "--with-lights", "--prune-lights", "--foliage-placements", "f.json", "--layers", "terrain,roads") && s4.indexOf("--dry-run") < 0 && !s4.some(x => /padding-arg/.test(x)), s4.join(" "));
  st.foundry.target = "new"; check("scene-3d needs an existing scene", throws(() => VB.scene3dArgs(st, d, true)));
  const sj = VB.jobInstallSignMaker(); check("Install Sign maker job runs install-sign-macro with no extra arguments", sj.kind === "sign_maker_macro" && sj.steps.length === 1 && sj.steps[0].args[0] === "install-sign-macro" && sj.steps[0].args.length === 1, JSON.stringify(sj.steps));
  console.log("\n" + ok + " passed, " + fail + " failed");
  process.exit(fail ? 1 : 0);
})();
