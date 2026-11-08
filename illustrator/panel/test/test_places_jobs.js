// Places tab jobs: spec building, size caps / draft, from-text and validate against the real python, create / render / import against a stub (no generation, no Foundry).
//   node illustrator/panel/test/test_places_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/places.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbpl-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0; const calls = [];
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const STUB = {
  create: { ok: true, id: "ulfvik", dir: "x/world/ulfvik", report: { seconds: 1.5, draft: true, town: { counts: { buildings: 12, streets: 5 }, warnings: [] }, warnings: [] } },
  render: { ok: true, place: "ulfvik", png: "x/ulfvik_town.png", job_file: "x/jobs/ulfvik_town.json" },
  import: { ok: true, place_id: "zz_scene", scene_uuid: "Scene.abc", size_ft: [310, 360], walls: 100, closed_loops: 25, dry_run: false, underlay: { png: "underlay/background.png" } }
};
const spawn = (py, args, o) => {
  const script = args.find(a => /\.py$/.test(a)) || "", sub = args[args.indexOf(script) + 1];
  let reply = null;
  if (/place_create\.py$/.test(script) && sub === "create") reply = STUB.create;
  else if (/place_render\.py$/.test(script)) reply = STUB.render;
  else if (/foundry_push\.py$/.test(script)) reply = STUB.import;
  if (reply) {
    calls.push(args.slice(args.indexOf(script)));
    const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
    setTimeout(() => { c.stdout.emit("data", JSON.stringify(reply) + "\n"); c.emit("close", 0); }, 5); return c;
  }
  return cp.spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  check("state carries places defaults", st.places && st.places.draft === true && st.places.form.population === 600 && st.places.import.closed_as === "lines");
  st.places.form.name = "Ulf Vik"; st.places.form.culture = "scandinavian"; st.places.form.recipe = "coastal"; st.places.form.sea_side = "east"; st.places.form.population = 260; st.places.form.layout = "linear";
  let spec = VB.placeSpecFromForm(st);
  check("form -> spec", spec.id === "ulf_vik" && spec.culture === "scandinavian" && spec.terrain.recipe === "coastal" && spec.terrain.sea_side === "east" && spec.town.population === 260 && spec.limits.draft === true, JSON.stringify(spec));
  st.places.form.recipe = "rolling"; spec = VB.placeSpecFromForm(st);
  check("sea side only for coastal / fjord", spec.terrain.sea_side === undefined);
  st.places.form.population = 12000; st.places.draft = false;
  let e = VB.placeEstimate(st);
  check("12000 people full quality is refused by the caps", e.problems.length >= 1 && e.level === "bad", JSON.stringify(e.problems));
  st.places.draft = true; e = VB.placeEstimate(st);
  check("draft lifts the building cap but not the area cap", e.problems.every(p => /ft2|cap/.test(p)) && !e.problems.some(p => /buildings/.test(p)), JSON.stringify(e.problems));
  st.places.form.population = 260; st.places.draft = false; e = VB.placeEstimate(st);
  check("small town: no problems", e.problems.length === 0 && /260 people/.test(e.text), e.text);
  st.places.form.population = 12000; st.places.draft = false;
  let job = VB.jobPlaceCreate(st, d, {}), r = await runner.run(job);
  check("create job refuses a too-big town before running python", !r.ok && /too big/.test(r.error || "") && calls.length === 0, r.error);
  st.places.allow_large = true; st.places.form.population = 260; st.places.draft = true; st.places.form.recipe = "coastal"; st.places.form.sea_side = "east";
  const specFile = path.join(ROOT, "illustrator/out/places/ulf_vik_spec.json");
  job = VB.jobPlaceCreate(st, d, {}); r = await runner.run(job);
  const cc = calls.find(a => a[1] === "create");
  check("create job runs create with --draft and the spec file", r.ok && cc && cc.indexOf("--draft") > 0 && /ulf_vik_spec\.json$/.test(cc[2]) && !cc.includes("--force"), JSON.stringify(cc) + r.error);
  check("spec file written with draft limit", fs.existsSync(specFile) && JSON.parse(fs.readFileSync(specFile, "utf8")).limits.draft === true);
  check("render step follows (--no-fills, small dpi in draft)", calls.some(a => /place_render\.py$/.test(a[0]) && a.includes("--no-fills") && a.includes("--dpi")), JSON.stringify(calls.map(a => a[0])));
  check("state remembers result and preview", st.places.last && st.places.last.id === "ulfvik" && st.places.last.counts.buildings === 12 && /ulfvik_town\.png/.test(st.places.preview_png), JSON.stringify(st.places.last));
  check("job knows the new place for the UI to switch to", job.newPlace === "ulf_vik");
  st.places.render_after = false; st.places.draft = false; calls.length = 0;
  job = VB.jobPlaceCreate(st, d, { force: true }); r = await runner.run(job);
  check("regenerate passes --force, full quality has no --draft, no render", r.ok && calls.length === 1 && calls[0].includes("--force") && !calls[0].includes("--draft"), JSON.stringify(calls));
  // from-text and validate run the real python
  st.places.from_text = "walled coastal town of 800 people with a big river, Danish style, called Havnholm";
  job = VB.jobPlaceFromText(st); r = await runner.run(job);
  check("from-text job ok and fills the form", r.ok && st.places.form.population === 800 && st.places.form.culture === "danish_german" && st.places.form.recipe === "coastal" && st.places.form.layout === "walled" && st.places.form.name === "Havnholm", r.error + JSON.stringify(st.places.form));
  check("from-text notes are kept", (st.places.notes || []).some(n => /population: 800/.test(n)), JSON.stringify(st.places.notes));
  st.places.draft = true; st.places.spec_text = "";
  job = VB.jobPlaceValidate(st); r = await runner.run(job);
  check("validate job ok", r.ok && st.places.last.validated && st.places.last.id === "havnholm", r.error + JSON.stringify(st.places.last));
  st.places.spec_text = '{"terrain": {"recipe": "volcano"}, "name": "X"}';
  job = VB.jobPlaceValidate(st); r = await runner.run(job);
  check("validate reports a bad recipe as a failure", !r.ok, JSON.stringify(r));
  st.places.spec_text = "{oops";
  check("pasted spec must be JSON", (() => { try { VB.jobPlaceValidate(st); return false; } catch (x) { return /not valid JSON/.test(x.message); } })());
  st.places.spec_text = "";
  // import
  calls.length = 0; job = VB.jobImportScene(st, d); r = await runner.run(job);
  check("import needs a scene", !r.ok && /pick a Foundry scene/.test(r.error || ""), r.error);
  st.places.import.scene_uuid = "Scene.abc"; st.places.import.place_id = "ZZ Scene"; st.places.import.lights = true; st.places.import.dry_run = true;
  job = VB.jobImportScene(st, d); r = await runner.run(job);
  const ic = calls[0] || [];
  check("import args: import-scene, uuid, include, closed-as, slug id, dry-run", r.ok && ic[1] === "import-scene" && ic.includes("Scene.abc") && ic.includes("walls,tiles,regions,lights") && ic.includes("--closed-as") && ic.includes("zz_scene") && ic.includes("--dry-run"), JSON.stringify(ic));
  check("import result remembered", st.places.last.imported === "zz_scene" && st.places.last.walls === 100 && st.places.last.dry === false /* stub says dry_run false */);
  check("a dry-run import has no place to switch to", job.newPlace === null);
  // regression: the panel flips dry_run back right after starting the job; the steps (run later) must still get --dry-run
  st.places.import.dry_run = true; calls.length = 0; job = VB.jobImportScene(st, d); st.places.import.dry_run = false; st.places.import.lights = false; r = await runner.run(job);
  check("dry-run flag is snapshotted when the job is built", (calls[0] || []).includes("--dry-run") && (calls[0] || []).join(" ").includes("walls,tiles,regions,lights"), JSON.stringify(calls[0]));
  st.places.import.dry_run = false; job = VB.jobImportScene(st, d);
  check("a real import switches to the new place", job.newPlace === "zz_scene");
  // import options: closed loops stay plain wall outlines by default; 'label rooms' sends buildings
  calls.length = 0; job = VB.jobImportScene(st, d); r = await runner.run(job);
  check("closed loops default to lines", (calls[0] || []).join(" ").includes("--closed-as lines"), JSON.stringify(calls[0]));
  st.places.import.closed_as = "buildings"; calls.length = 0; job = VB.jobImportScene(st, d); r = await runner.run(job); st.places.import.closed_as = "lines";
  check("label rooms toggle sends --closed-as buildings", (calls[0] || []).join(" ").includes("--closed-as buildings"));
  // Foundry lists are global: the fresher cache wins (place switched to after an import starts empty)
  const old = { fetched: "2026-11-08T10:00:00Z", lists: { scenes: [{ uuid: "Scene.a", name: "A" }] } }, nw = { fetched: "2026-11-08T11:00:00Z", lists: { scenes: [{ uuid: "Scene.b", name: "B" }] } }, none = { fetched: null, lists: {} };
  check("fresherCache picks the newer", VB.fresherCache(old, nw) === nw && VB.fresherCache(nw, old) === nw && VB.fresherCache(none, old) === old && VB.fresherCache(old, null) === old && VB.fresherCache(null, null).fetched === null);
  // Push scene: confirmation text names target scene/place and says it writes to Foundry; the plan text states grid/size/walls
  const st2 = VB.normalize(null); st2.place = "zz_scene"; st2.foundry.target = "existing"; st2.foundry.sceneUuid = "Scene.b"; st2.foundry.cache = nw;
  const cl = VB.foundryPushConfirmLines(st2, false).join(" | ");
  check("push confirm names scene, place and Foundry write", /WRITES to Foundry/.test(cl) && /Scene: B \(Scene\.b\)/.test(cl) && /Place: zz_scene/.test(cl) && /Plan \(dry run\)/.test(cl), cl);
  st2.foundry.target = "new"; st2.foundry.sceneName = " My Map ";
  check("push confirm for a new scene", /creates a new scene/.test(VB.foundryPushConfirmLines(st2, true).join(" | ")) && /Scene: My Map/.test(VB.foundryPushConfirmLines(st2, true).join(" | ")));
  const pt = VB.foundryPlanText({ scene_name: "B", width: 3348, height: 3888, grid: { size: 54, distance: 5 }, walls: 100, drawings: 0, dry_run: true });
  check("plan text has size, grid, walls and says nothing written", /3348x3888 px/.test(pt) && /grid 54 px = 5 ft/.test(pt) && /100 walls/.test(pt) && /nothing written/.test(pt), pt);
  // main.js wiring (static): Plan button + action, push asks the in-panel modal first, no window.confirm
  const mj = fs.readFileSync(path.join(__dirname, "../main.js"), "utf8"), ih = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
  check("panel has a Plan (dry run) button wired to f_plan_scene", /data-act="f_plan_scene"/.test(ih) && /f_plan_scene: fPlanScene/.test(mj) && /\.concat\(\["--dry-run"\]\)/.test(mj));
  check("push scene asks fAsk before fGuard and never window.confirm", mj.indexOf("await fAsk(VB.foundryPushConfirmLines") > 0 && mj.indexOf("await fAsk(VB.foundryPushConfirmLines") < mj.indexOf('fGuard(withTiles ? "push scene + tiles"') && !/window\.confirm|[^.\w]confirm\(/.test(mj));
  check("refresh repaints the Places picker", /fPaint\(\); if \(window\.VBPlacesUI\) VBPlacesUI\.paint\(\)/.test(mj));
  console.log(ok + " passed, " + fail + " failed"); try { fs.unlinkSync(specFile); } catch (x) { /* ignore */ } process.exit(fail ? 1 : 0);
})();
