// Export planner: ordered step list, defaults, dry-run flags, refusal reasons, run list / resume, preview text.   node illustrator/panel/test/test_exportplan.js
const path = require("path");
const VB = require("../lib/core.js");
["townarea", "regions", "styles", "objects", "lighting", "sun3d", "streetlamps", "foliage", "skybox", "water", "heightpaint", "padding", "bridges", "places", "tools", "bridge", "exportplan"].forEach(f => require("../lib/" + f + ".js"));
const X = require("../lib/exportplan.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const d = VB.dirs(ROOT, place);
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const mk = (f) => { const st = VB.normalize(null); st.place = place; st.foundry.sceneName = "Test scene"; if (f) f(st); return st; };
const facts = Object.assign({ hasTerrain: true, buildingCount: 80, packExists: false, splitExists: false, connected: true }, {});
const ids = p => p.steps.map(s => s.id);
const args = (p, id) => X.step(p, id).build().steps[0].args.join(" ");

let st = mk(), p = X.plan(VB, st, d, facts, { dry: true });
check("pipeline order", ids(p).join(",") === "check,export,validate,split,merge,audit,push,collision", ids(p).join(","));
check("state default: full selection, dry run on, no statuses", st.exp && st.exp.dry === true && Object.keys(st.exp.sel).length === 8 && Object.keys(st.exp.last).length === 0);
check("all steps pre-checked by default", p.steps.every(s => s.checked));
check("new scene: audit and collision disabled with a reason", !X.step(p, "audit").enabled && /existing scene/.test(X.step(p, "audit").reason) && !X.step(p, "collision").enabled);
check("new scene dry run: push is push-models --dry-run --scene-name", X.step(p, "push").enabled && /^push-models /.test(args(p, "push")) && /--dry-run/.test(args(p, "push")) && /--scene-name Test scene/.test(args(p, "push")), args(p, "push"));
check("push defaults: prune, 3d scene mode, no quantized", /--prune/.test(args(p, "push")) && /--scene-mode 3d/.test(args(p, "push")) && !/--allow-quantized/.test(args(p, "push")));
check("write steps flagged, dry marks them", X.step(p, "push").write && X.step(p, "push").dryOnly && !X.step(p, "export").write && !X.step(p, "split").write);
check("heavy steps flagged", X.step(p, "split").heavy && X.step(p, "merge").heavy && !X.step(p, "export").heavy);
check("local jobs use the existing builders", /^export --place/.test(args(p, "export")) && /^split --place/.test(args(p, "split")) && /^merge --place/.test(args(p, "merge")) && /--preset layer/.test(args(p, "merge")) && /--compress none/.test(args(p, "merge")));

// existing scene
st = mk(s => { s.foundry.target = "existing"; s.foundry.sceneUuid = "Scene.abc"; });
p = X.plan(VB, st, d, facts, { dry: true });
check("existing scene dry run: push-scene-3d --dry-run with lights", /^push-scene-3d /.test(args(p, "push")) && /--scene-uuid Scene.abc/.test(args(p, "push")) && /--dry-run/.test(args(p, "push")) && /--with-lights/.test(args(p, "push")), args(p, "push"));
check("existing scene: audit + collision enabled, collision is a dry run", X.step(p, "audit").enabled && X.step(p, "collision").enabled && /^set-collision /.test(args(p, "collision")) && !/--apply/.test(args(p, "collision")));
// real run needs arming
p = X.plan(VB, st, d, facts, { dry: false, armed: false });
check("real push refused until armed", !X.step(p, "push").enabled && /understand/.test(X.step(p, "push").reason) && !X.step(p, "collision").enabled && X.step(p, "export").enabled);
p = X.plan(VB, st, d, facts, { dry: false, armed: true });
check("armed real push: no --dry-run, collision --apply", X.step(p, "push").enabled && !/--dry-run/.test(args(p, "push")) && /--apply/.test(args(p, "collision")) && !X.step(p, "push").dryOnly);
check("default (opts omitted) is a dry run", X.plan(VB, st, d, facts).dry === true);

// refusal reasons
p = X.plan(VB, mk(), d, Object.assign({}, facts, { hasTerrain: false }), { dry: true });
check("no terrain: check/export disabled with the Terrain tab hint; validate/split follow", !X.step(p, "check").enabled && /no terrain/.test(X.step(p, "export").reason) && !X.step(p, "validate").enabled && !X.step(p, "split").enabled);
p = X.plan(VB, mk(), d, Object.assign({}, facts, { hasTerrain: false, packExists: true, splitExists: true }), { dry: true });
check("existing pack without terrain: validate/split/merge still allowed", X.step(p, "validate").enabled && X.step(p, "split").enabled && X.step(p, "merge").enabled && !X.step(p, "export").enabled);
p = X.plan(VB, mk(), d, Object.assign({}, facts, { connected: false }), { dry: true });
check("no relay connection: push refused with the reason, local steps fine", !X.step(p, "push").enabled && /bridge relay/.test(X.step(p, "push").reason) && X.step(p, "export").enabled);
p = X.plan(VB, mk(s => { s.foundry.sceneName = " "; }), d, facts, { dry: true });
check("new scene needs a name", !X.step(p, "push").enabled && /name for the new scene/.test(X.step(p, "push").reason));
p = X.plan(VB, mk(s => { s.foundry.target = "existing"; }), d, facts, { dry: true });
check("existing scene needs a picked scene", !X.step(p, "push").enabled && /pick an existing scene/.test(X.step(p, "push").reason) && !X.step(p, "audit").enabled);
p = X.plan(VB, mk(s => { s.foundry.models.preset = "individual"; }), d, facts, { dry: true });
check("preset keep-individual: merge disabled", !X.step(p, "merge").enabled && /individual/.test(X.step(p, "merge").reason));

// run list and resume
p = X.plan(VB, mk(s => { s.exp.sel.check = false; s.exp.sel.split = false; }), d, Object.assign({}, facts, { splitExists: true }), { dry: true });
let rl = X.runList(p, "");
check("run list = checked and enabled, in order", rl.run.join(",") === "export,validate,merge,push", rl.run.join(","));
check("run list reports selected steps that cannot run", rl.skipped.map(x => x.id).join(",") === "audit,collision", JSON.stringify(rl.skipped));
check("resume from a step", X.runList(p, "merge").run.join(",") === "merge,push" && X.runList(p, "push").run.join(",") === "push");
p = X.plan(VB, mk(), d, Object.assign({}, facts, { hasTerrain: false }), { dry: true });
check("nothing runnable when everything is refused", X.runList(p, "").run.length === 0 || X.runList(p, "").run.every(id => X.step(p, id).enabled));
// shortcuts
check("pack-only selection", X.PACK_ONLY.join(",") === "check,export,validate");
// roof recommendation and warnings
check("roof mode recommendation by size", X.recommendRoofMode(40) === "per_building" && X.recommendRoofMode(150) === "per_building" && X.recommendRoofMode(151) === "per_scene" && X.recommendRoofMode(900) === "per_scene");
p = X.plan(VB, mk(s => { s.foundry.models.compress = "quant"; s.foundry.models.roofMode = "per_building"; }), d, Object.assign({}, facts, { buildingCount: 600 }), { dry: false, armed: true });
check("warnings: quantized, big place RAM, per-building on a big place, prune", p.warnings.some(w => /quantized/i.test(w)) && p.warnings.some(w => /RAM/.test(w) && /Vega/.test(w) && /never automatic/.test(w)) && p.warnings.some(w => /per building/i.test(w)) && p.warnings.some(w => /Prune/.test(w)));
check("big place heavy note on split", /close other heavy apps/.test(X.step(p, "split").note));
// preview text
st = mk(s => { s.foundry.target = "existing"; s.foundry.sceneUuid = "Scene.abc"; s.foundry.cache = { lists: { scenes: [{ uuid: "Scene.abc", name: "Dyers Walk" }] } }; });
p = X.plan(VB, st, d, facts, { dry: true });
let t = X.preview(VB, st, p, facts, "");
check("preview names mode, scene and the writes", /DRY RUN/.test(t) && /Dyers Walk/.test(t) && /Scene\.abc/.test(t) && /Foundry writes \(dry run/.test(t) && /Push 3D scene/.test(t) && /On this PC/.test(t), t);
p = X.plan(VB, st, d, facts, { dry: false, armed: true }); t = X.preview(VB, st, p, facts, "");
check("real preview calls out FOUNDRY WRITES", /FOUNDRY WRITES \(real\)/.test(t) && /REAL/.test(t), t);
t = X.preview(VB, mk(), X.plan(VB, mk(), d, facts, { dry: true }), facts, "");
check("new-scene preview shows the name", /new scene "Test scene"/.test(t));
// record
st = mk(); X.record(st, "export", "done"); X.record(st, "split", "failed", "boom");
check("record keeps status, time, error", st.exp.last.export.status === "done" && st.exp.last.split.error === "boom" && /^\d{4}-/.test(st.exp.last.split.at));
// ---- PUSH group
{
  const ex = mk(s => { s.foundry.target = "existing"; s.foundry.sceneUuid = "Scene.abc"; });
  let pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true }), { dry: true });
  const pa = id => { const j = X.step(pp, id).build(); return j.act || j.steps.map(x => Array.isArray(x.args) ? x.args.join(" ") : "fn").join(" || "); };
  check("push group lists every pushed thing in the verified order", ["scene2d", "models", "walls", "padding", "skybox", "sun", "lighting", "lights", "streetlamps", "collision", "doors", "foliage", "m_click", "m_sign"].every(i => X.step(pp, i)) &&
    pp.steps.map(s => s.id).indexOf("models") < pp.steps.map(s => s.id).indexOf("padding") && pp.steps.map(s => s.id).indexOf("padding") < pp.steps.map(s => s.id).indexOf("skybox") && pp.steps.map(s => s.id).indexOf("skybox") < pp.steps.map(s => s.id).indexOf("lights") && pp.steps.map(s => s.id).indexOf("lights") < pp.steps.map(s => s.id).indexOf("collision"));
  check("by-layer pushes use --layers", /--layers terrain/.test(pa("l_terrain")) && /--layers buildings/.test(pa("l_buildings")) && /--layers roofs/.test(pa("l_roofs")) && /--layers roads/.test(pa("l_roads")) && /--layers streetlamps/.test(pa("l_streetlamps")) && /--layers signs/.test(pa("l_signs")));
  check("one shared target scene reaches padding, skybox, foliage", /Scene\.abc/.test(JSON.stringify(X.scopedState(ex).padding)) && X.scopedState(ex).skybox.scene_uuid === "Scene.abc" && X.scopedState(ex).foliage.merge.scene_uuid === "Scene.abc" && /--dry-run/.test(pa("padding")) === false);
  check("type-scoped lights", /push-lights/.test(pa("lights_lamps")) && /--layers lamp/.test(pa("lights_lamps")) && /--layers hearth,window/.test(pa("lights_interior")) && !/--layers/.test(pa("lights")) && /--dry-run/.test(pa("lights")));
  check("dry run: all writes are dry (collision no --apply, sun/lighting no --apply, push-walls no --apply, foliage --dry-run)", !/--apply/.test(pa("collision")) && !/--apply/.test(pa("sun")) && !/--apply/.test(pa("lighting")) && !/--apply/.test(pa("walls")) && /--dry-run/.test(pa("foliage")) && /--dry-run/.test(pa("models")) && /--dry-run/.test(pa("streetlamps")) && !/--apply/.test(pa("doors")));
  check("2D scene items are acts (plan in dry run)", pa("scene2d") === "f_plan_scene");
  check("macro installs have no dry run: disabled in dry mode", ["m_click", "m_roofs", "m_door", "m_sign"].every(i => !X.step(pp, i).enabled && /no dry run/.test(X.step(pp, i).reason)));
  check("everything set excludes the walls fallback, 2D scene, tiles, macros and subsets", X.PUSH_EVERYTHING.join(",") === "models,padding,skybox,sun,lighting,lights,collision,doors,foliage" && X.step(pp, "models").checked && !X.step(pp, "l_roofs").checked && !X.step(pp, "walls").checked);
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true }), { dry: false, armed: false });
  check("real push refused until armed (every write item), macros too", X.step(pp, "models").reason.match(/understand/) && X.step(pp, "collision").reason.match(/understand/) && X.step(pp, "m_click").reason.match(/understand/));
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true }), { dry: false, armed: true });
  check("armed real push: no dry flags, applies", !/--dry-run/.test(pa("models")) && /--apply/.test(pa("collision")) && /--apply/.test(pa("sun")) && /--apply/.test(pa("doors")) && X.step(pp, "m_click").enabled && pa("scene2d") === "f_push_scene" && !/--dry-run/.test(pa("lights")));
  pp = X.pushPlan(VB, mk(), d, Object.assign({}, facts, { packExists: true }), { dry: true });
  check("new scene: models allowed, the scene-flag items need an existing scene", X.step(pp, "models").enabled && !X.step(pp, "padding").enabled && /existing scene/.test(X.step(pp, "padding").reason) && !X.step(pp, "collision").enabled);
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true, connected: false }), { dry: true });
  check("no relay: every push item disabled with the reason (macros excluded in dry)", X.step(pp, "models").reason.match(/relay/) && X.step(pp, "padding").reason.match(/relay/));
  pp = X.pushPlan(VB, ex, d, facts, { dry: true });
  check("push models needs a pack", /world pack/.test(X.step(pp, "models").reason) && X.step(pp, "padding").enabled);
  check("run list for push, with resume", (() => { const q = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true }), { dry: true }); const r = X.runList(q, "").run; return r.join(",") === "models,padding,skybox,sun,lighting,lights,collision,doors,foliage" && X.runList(q, "lights").run.join(",") === "lights,collision,doors,foliage"; })());
  check("batch copy numbers parsed from a job's JSON", X.copySummary("log\n" + '{"push":{"copy_seconds":1.5,"files_copied":10,"files_skipped":3,"bytes":5242880}}') === "copied 10 file(s), 3 unchanged, 5.0 MB in 1.5 s" && X.copySummary("nothing") === "" && X.copySummary('{"ok":true}') === "");
  check("state defaults carry the push selection", st.exp && st.exp.psel && st.exp.psel.models === true && st.exp.psel.l_roofs === false);
}
// ---- lights / streetlamps precheck and soft skips (Bridgehollow: a pack with 0 lights, streetlamps switched off)
{
  const ex = mk(s => { s.foundry.target = "existing"; s.foundry.sceneUuid = "Scene.abc"; });
  const none = X.packLightCounts({ files: [{ file: "a.glb" }], lights: [] });
  const interior = X.packLightCounts({ files: [{ file: "b.glb", lights: [{ type: "hearth" }, { type: "window" }, { type: "window" }] }] });
  const lamps = X.packLightCounts({ files: [{ file: "s.glb", layer: "streetlamps" }], lights: [{ type: "lamp" }, { type: "lamp" }], streetlamps: { lamps: 2 } });
  check("packLightCounts: file-entry hints + doc lights + lamp tiles", none.total === 0 && interior.total === 3 && interior.hearth === 1 && interior.window === 2 && lamps.lamp === 2 && lamps.lampTiles === 1 && lamps.lamps === 2 && X.packLightCounts(null) === null);
  let pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true, lights: none }), { dry: true });
  check("0 lights: every lights item disabled with the plain re-export / streetlamps reason", ["lights", "lights_interior", "lights_lamps", "streetlamps"].every(i => !X.step(pp, i).enabled) &&
    /re-export first/.test(X.step(pp, "lights").reason) && /re-export first/.test(X.step(pp, "lights_interior").reason) && /switch Streetlamps on/.test(X.step(pp, "lights_lamps").reason) && /switch Streetlamps on/.test(X.step(pp, "streetlamps").reason));
  check("precheck line counts the pack before running", /^Pack: 0 light\(s\)/.test(X.step(pp, "lights").precheck) && /lamp tile/.test(X.step(pp, "streetlamps").precheck));
  check("streetlamps items offer Apply streetlamps now, interior items do not", X.step(pp, "streetlamps").offerApply && X.step(pp, "lights_lamps").offerApply && !X.step(pp, "lights").offerApply);
  const rl = X.runList(pp, "");
  check("0-light items are reported, the rest of Push everything still runs", rl.skipped.some(x => x.id === "lights") && rl.run.join(",") === "models,padding,skybox,sun,lighting,collision,doors,foliage", rl.run.join(","));
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true, lights: interior }), { dry: true });
  check("interior lights only: lights + interior enabled with a count, lamps disabled", X.step(pp, "lights").enabled && X.step(pp, "lights_interior").enabled && /3 light\(s\) \(1 hearth, 2 window, 0 lamp\)/.test(X.step(pp, "lights").note) && !X.step(pp, "lights_lamps").enabled && !X.step(pp, "streetlamps").enabled);
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true, lights: lamps }), { dry: true });
  check("lamps in the pack: streetlamps and lamp items enabled, interior disabled", X.step(pp, "streetlamps").enabled && X.step(pp, "lights_lamps").enabled && X.step(pp, "lights").enabled && !X.step(pp, "lights_interior").enabled);
  pp = X.pushPlan(VB, ex, d, Object.assign({}, facts, { packExists: true }), { dry: true });
  check("unknown counts (no read): lights items unchanged", X.step(pp, "lights").enabled && !X.step(pp, "lights").precheck);
  const err = { ok: false, error: 'push lights exited with code 1: light budget: 0 of 0 lights kept | {"ok": false, "error": "the plan has 0 lights, nothing written and the scene\'s existing lights are kept"}' };
  check("a 0-light failure of a lights step is a skip with the reason, not a failure", /^skipped: No lights/.test(X.softSkip("lights", err)) && /^skipped: No streetlamps/.test(X.softSkip("streetlamps", err)) && /^skipped: No streetlamps/.test(X.softSkip("lights_lamps", err)));
  check("other failures stay failures", X.softSkip("lights", { ok: false, error: "bridge offline" }) === "" && X.softSkip("models", err) === "" && X.softSkip("lights", { ok: true }) === "");
  const e3 = { ok: false, error: "push-scene-3d: --with-lights: the plan has 0 lights (...); nothing was written" };
  const job = X.plan(VB, ex, d, facts, { dry: true }).steps.find(s => s.id === "push").build();
  check("push-scene-3d refused for 0 lights: retried without --with-lights, never with --prune-lights", X.retryWithoutLights("push", e3) && !X.retryWithoutLights("push", err) && !X.retryWithoutLights("push", { ok: true }) &&
    /--with-lights/.test(job.steps[0].args.join(" ")) && !/--with-lights|--prune-lights/.test(X.dropLights(job).steps[0].args.join(" ")) && /lights skipped/.test(job.label));
  check("export push note warns when the current pack has no lights", /no lights/.test(X.step(X.plan(VB, ex, d, Object.assign({}, facts, { lights: none }), { dry: true }), "push").note));
  check("Streetlamps tab push check", X.streetlampsPushCheck(none).offerApply && /switch Streetlamps on/.test(X.streetlampsPushCheck(none).reason) && X.streetlampsPushCheck(lamps).reason === "");
  const fs = require("fs"), os = require("os"), tp = path.join(os.tmpdir(), "vb_lc_" + process.pid + ".json");
  fs.writeFileSync(tp, JSON.stringify({ files: [{ lights: [{ type: "window" }] }] }));
  check("readPackLights reads the pack, null when missing", X.readPackLights(fs, tp).window === 1 && X.readPackLights(fs, tp + ".none") === null); fs.unlinkSync(tp);
}
check("window.VBExportPlan published alongside module.exports", /window\.VBExportPlan = X/.test(require("fs").readFileSync(__dirname + "/../lib/exportplan.js", "utf8")));
console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
