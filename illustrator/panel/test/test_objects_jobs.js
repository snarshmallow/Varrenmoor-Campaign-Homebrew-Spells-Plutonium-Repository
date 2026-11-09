// Per-object editing jobs (Buildings tab editor, Roads tab) against a temp COPY of a place (never touches world/). No Illustrator needed (mock host).
//   node illustrator/panel/test/test_objects_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/styles.js"); require("../lib/objects.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbobj-")), wr = (TMP + "/world").split(path.sep).join("/");
fs.mkdirSync(`${wr}/${place}/buildings`, { recursive: true });
fs.readdirSync(`${ROOT}/world/${place}/buildings`).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/buildings/${f}`, `${wr}/${place}/buildings/${f}`));
fs.copyFileSync(`${ROOT}/world/${place}/streets.json`, `${wr}/${place}/streets.json`);
process.env.VB_WORLD_ROOT = wr;
const readB = id => JSON.parse(fs.readFileSync(`${wr}/${place}/buildings/${id}.json`, "utf8"));
const streets = () => JSON.parse(fs.readFileSync(`${wr}/${place}/streets.json`, "utf8")).streets;
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0; const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
let mockSel = null;
const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, host: async a => (a.action === "get_selection" ? mockSel : { ok: true }), log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
const thrown = f => { try { f(); return ""; } catch (e) { return String(e.message); } };
(async () => {
  check("defaults: nothing applied", st.objects && Object.keys(st.objects.b).every(k => st.objects.b[k].on === false) && Object.keys(st.objects.r).every(k => st.objects.r[k].on === false));
  check("no buildings chosen", /no buildings chosen/.test(thrown(() => VB.objectsBuildingArgs(st))));
  st.styles.ids = ["bld_house_041", "bld_house_044"];
  check("no field ticked", /tick at least one/.test(thrown(() => VB.objectsBuildingArgs(st))));
  Object.assign(st.objects.b.roof_type, { on: true, v: "hip" }); Object.assign(st.objects.b.roof_pitch, { on: true, v: 9 });
  Object.assign(st.objects.b.roof_material, { on: true, v: "" }); Object.assign(st.objects.b.no_windows, { on: true, v: "true" }); Object.assign(st.objects.b.wall_material, { on: true, v: "stone_slab" });
  const a = VB.objectsBuildingArgs(st).join(" ");
  check("args: set + clamp + clear", /--ids bld_house_041,bld_house_044/.test(a) && /--set roof_type=hip/.test(a) && /--set roof_pitch=2\b/.test(a) && /--clear roof_material/.test(a) && /--set no_windows=true/.test(a), a);
  let r = await runner.run(VB.jobObjectsEditBuildings(st));
  check("edit buildings ok", r.ok, r.error);
  const b = readB("bld_house_041");
  check("edit block written", b.edit && b.edit.roof_type === "hip" && b.edit.no_windows === true && b.edit.wall_material === "stone_slab" && b.edit.roof_pitch === 2, JSON.stringify(b.edit));
  check("other building untouched", !readB("bld_house_052").edit);
  check("state remembers", st.objects.last && st.objects.last.count === 2);
  Object.assign(st.objects.b.wall_material, { on: true, v: "nope" });
  r = await runner.run(VB.jobObjectsEditBuildings(st));
  check("bad texture rejected", !r.ok && /unknown texture/.test(r.error), r.error);
  r = await runner.run(VB.jobObjectsReset(st, "building"));
  check("reset removes edit", r.ok && !readB("bld_house_041").edit && !readB("bld_house_044").edit, r.error);
  // roads
  check("no roads chosen", /no roads chosen/.test(thrown(() => VB.objectsRoadArgs(st))));
  const sid = streets()[0].id, w0 = streets()[0].geometry.width_ft;
  st.objects.rids = [sid];
  Object.assign(st.objects.r["class"], { on: true, v: "alley" }); Object.assign(st.objects.r.kerb, { on: true, v: "true" }); Object.assign(st.objects.r["grade.smooth"], { on: true, v: 0.9 });
  Object.assign(st.objects.r["grade.cutfill"], { on: true, v: "true" }); Object.assign(st.objects.r.width_ft, { on: true, v: 24 });
  const ra = VB.objectsRoadArgs(st).join(" ");
  check("road args", /--set class=alley/.test(ra) && /--set kerb=true/.test(ra) && /--set grade.smooth=0.9/.test(ra) && /--set width_ft=24/.test(ra), ra);
  r = await runner.run(VB.jobObjectsEditRoads(st));
  const s0 = streets()[0];
  check("road edit written", r.ok && s0.edit.class === "alley" && s0.edit.kerb === true && s0.edit.grade.smooth === 0.9 && s0.edit.grade.cutfill === true && s0.geometry.width_ft === 24, r.error + JSON.stringify(s0.edit));
  Object.assign(st.objects.r["class"], { on: false }); Object.assign(st.objects.r.kerb, { on: true, v: "" }); Object.assign(st.objects.r["grade.smooth"], { on: true, v: "" });
  Object.assign(st.objects.r.width_ft, { on: false }); Object.assign(st.objects.r["grade.cutfill"], { on: false });
  r = await runner.run(VB.jobObjectsEditRoads(st));
  check("road clear", r.ok && streets()[0].edit.class === "alley" && !("kerb" in streets()[0].edit) && !("smooth" in (streets()[0].edit.grade || {})), r.error);
  r = await runner.run(VB.jobObjectsReset(st, "road"));
  check("road reset", r.ok && !streets()[0].edit, r.error);
  mockSel = { ok: true, paths: [{ name: "str_x5F_008" }, { name: "str_008_casing" }, { name: "bld_house_041" }, { name: "str_999" }] };
  r = await runner.run(VB.jobRoadsFromSelection(st, streets().map(s => s.id)));
  check("selection -> road ids", r.ok && st.objects.rids.join() === "str_008", JSON.stringify(st.objects.rids) + r.error);
  mockSel = { ok: true, paths: [{ name: "bld_house_041" }] };
  r = await runner.run(VB.jobRoadsFromSelection(st, ["str_008"]));
  check("selection without street names fails", !r.ok && /named like a street/.test(r.error), r.error);
  // pack options (Foundry tab "More pack options", Roads (3D) cross slope / grading switch): defaults add no argument
  const d = VB.dirs(ROOT, place), sp = s => VB.jobWorldSplit(s, d).steps[0].args.join(" "), pa = s => VB.worldPushArgs(s, d, {}).join(" ");
  const st2 = VB.normalize(null); st2.place = place; st2.foundry.sceneName = "x";
  check("pack defaults unchanged", !/--split-preset|--no-carve|--no-conform|--road-cross-deg|--road-grade/.test(sp(st2)) && !/--prune|--roofs-hidden|--scene-mode|--allow-quantized/.test(pa(st2)), sp(st2) + " | " + pa(st2));
  Object.assign(st2.foundry.models, { splitPreset: "individual", carve: false, conform: false, prune: true, roofsHidden: true, sceneMode: "3d", compress: "quant", roofMode: "per_building" }); Object.assign(st2.roads, { cross_deg: 6, grade: false });
  check("pack options passed", /--split-preset individual/.test(sp(st2)) && /--no-carve/.test(sp(st2)) && /--no-conform/.test(sp(st2)) && /--road-cross-deg 6/.test(sp(st2)) && /--road-grade off/.test(sp(st2)) &&
    /--prune/.test(pa(st2)) && /--roofs-hidden/.test(pa(st2)) && /--scene-mode 3d/.test(pa(st2)) && /--allow-quantized/.test(pa(st2)), sp(st2) + " | " + pa(st2));
  check("dry run + audit + lights jobs", /--dry-run/.test(VB.jobWorldPush(st2, d, { dry: true }).steps[0].args.join(" ")) && thrown(() => VB.jobSceneAudit(st2, d)).length > 0 &&
    (st2.foundry.target = "existing", st2.foundry.sceneUuid = "Scene.abc", /scene-audit.*--scene-uuid Scene.abc/.test(VB.jobSceneAudit(st2, d).steps[0].args.join(" "))) && /push-lights.*--dry-run/.test(VB.jobPushLights(st2, d, true).steps[0].args.join(" ")));
  // collision per layer + walls (Foundry tab "Collision and walls")
  const st3 = VB.normalize(null); st3.place = place; st3.foundry.sceneName = "x"; st3.foundry.target = "existing"; st3.foundry.sceneUuid = "Scene.abc";
  check("collision default adds no argument", !/--collision/.test(VB.worldPushArgs(st3, d, {}).join(" ")) && !/--collision/.test(VB.jobSetCollision(st3, false).steps[0].args.join(" ")));
  st3.foundry.models.collision.water = true; st3.foundry.models.collision.terrain = false;
  const ca = VB.worldPushArgs(st3, d, {}), cs = ca[ca.indexOf("--collision") + 1];
  check("collision spec lists the ticked layers", cs.split(",").includes("water") && !cs.split(",").includes("terrain") && cs.split(",").includes("buildings"), cs);
  const sc1 = VB.jobSetCollision(st3, false).steps[0].args.join(" "), sc2 = VB.jobSetCollision(st3, true).steps[0].args.join(" ");
  check("set-collision dry run vs apply", /set-collision --scene-uuid Scene.abc --collision /.test(sc1) && !/--apply/.test(sc1) && /--apply$/.test(sc2), sc1 + " | " + sc2);
  Object.keys(st3.foundry.models.collision).forEach(k => { st3.foundry.models.collision[k] = false; });
  check("all collision off = none", /--collision none/.test(VB.jobSetCollision(st3, true).steps[0].args.join(" ")));
  const wa = VB.jobPushWalls(st3, true).steps[0].args.join(" ");
  check("push-walls all layers by default, apply", /push-walls --place \S+ --scene-uuid Scene.abc --wall-layers buildings,walls,fences,trees,water --apply$/.test(wa), wa);
  st3.foundry.models.wallLayers.trees = false; st3.foundry.models.wallLayers.water = false;
  const wd = VB.jobPushWalls(st3, false).steps[0].args.join(" ");
  check("push-walls layer boxes", /--wall-layers buildings,walls,fences( |$)/.test(wd) && !/--apply/.test(wd), wd);
  st3.foundry.target = "existing";
  const sd = VB.jobSyncDoors(st3, false).steps[0].args.join(" "), sa = VB.jobSyncDoors(st3, true).steps[0].args.join(" ");
  check("sync-doors dry run vs apply + install job", /^sync-doors --scene-uuid Scene.abc$/.test(sd) && /--apply$/.test(sa) && VB.jobInstallDoorSync().steps[0].args[0] === "install-door-sync", sd + " | " + sa);
  st3.foundry.target = "new"; check("walls job needs an existing scene", thrown(() => VB.jobPushWalls(st3, true)).length > 0);
  const real = JSON.parse(fs.readFileSync(`${ROOT}/world/${place}/streets.json`, "utf8")).streets[0];
  check("real world untouched", !real.edit && real.geometry.width_ft === w0);
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
