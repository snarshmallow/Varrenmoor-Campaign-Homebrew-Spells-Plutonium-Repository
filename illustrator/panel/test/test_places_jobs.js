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
  image: { ok: true, place_id: "zz_base", size_ft: [1000, 2000], ft_per_px: 5, image_px: [200, 400], rotate_deg: 0, dry_run: false, underlay: { png: "underlay/background.png" } },
  blank: { ok: true, id: "zz_blank", name: "ZZ Blank", size_ft: [600, 400], recipe: "flat", cell_ft: 5, heightmap_nodes: [121, 81], scale_ft_per_in: 50, grid_ft: 50 },
  manage: { ok: true, old: "zz_a", new: "zz_b", plan: { json_files: [{ file: "place.json", references: 1 }], left_behind: ["Foundry scene Scene.x"] } },
  import: { ok: true, place_id: "zz_scene", scene_uuid: "Scene.abc", size_ft: [310, 360], walls: 100, closed_loops: 25, dry_run: false, underlay: { png: "underlay/background.png" } }
};
const spawn = (py, args, o) => {
  const script = args.find(a => /\.py$/.test(a)) || "", sub = args[args.indexOf(script) + 1];
  let reply = null;
  if (/place_create\.py$/.test(script) && sub === "create") reply = STUB.create;
  else if (/place_create\.py$/.test(script) && sub === "import-image") reply = STUB.image;
  else if (/place_create\.py$/.test(script) && sub === "create-blank") reply = Object.assign({}, STUB.blank, args.includes("--dry-run") ? { dry_run: true } : {});
  else if (/place_manage\.py$/.test(script)) reply = sub === "trash-list" ? { ok: true, trash: [{ entry: "zz_x_20261109-120000", place: "zz_x" }] } : Object.assign({}, STUB.manage, args.includes("--dry-run") ? { dry_run: true } : {});
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
  // import base map image (no Foundry)
  calls.length = 0; st.places.image = { path: "", name: "ZZ Base", id: "", ft_per_px: "5", rotate: "", grid_ft: "" };
  r = await runner.run(VB.jobImportImage(st, false));
  check("image import needs a path", !r.ok && /path of the base map image/.test(r.error || ""), r.error);
  st.places.image.path = "C:/maps/a.png"; st.places.image.ft_per_px = "";
  r = await runner.run(VB.jobImportImage(st, false));
  check("image import needs ft per pixel", !r.ok && /ft per pixel/.test(r.error || ""), r.error);
  st.places.image.ft_per_px = "4.669"; st.places.image.rotate = "12"; st.places.image.grid_ft = "50"; calls.length = 0;
  job = VB.jobImportImage(st, true); r = await runner.run(job); const ii = calls[0] || [];
  check("image import args: import-image, path, --ft-per-px, --name, slug --id, --rotate, --grid-ft, --dry-run", r.ok && ii[1] === "import-image" && ii[2] === "C:/maps/a.png" && ii.includes("--ft-per-px") && ii.includes("4.669") && ii.includes("--name") && ii.includes("ZZ Base") && ii.includes("zz_base") && ii.includes("--rotate") && ii.includes("12") && ii.includes("--grid-ft") && ii.includes("50") && ii.includes("--dry-run"), JSON.stringify(ii));
  check("image dry run has no place to switch to; a real one does", job.newPlace === null && VB.jobImportImage(st, false).newPlace === "zz_base");
  check("image import result remembered", st.places.last.imported === "zz_base" && st.places.last.ft_per_px === 5);
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
  // ---- tiny settlements (population 0-19)
  const st3 = VB.normalize(null); st3.place = "bridgehollow";
  st3.places.form.name = "Ash Farm"; st3.places.form.population = 4; st3.places.form.layout = "walled"; st3.places.form.wall = true;
  let ts = VB.placeSpecFromForm(st3);
  check("tiny: population 4 kept, settlement auto, no layout / wall / centre feature", ts.town.population === 4 && ts.town.settlement === "auto" && ts.town.layout === undefined && !ts.town.wall && ts.town.central_feature === undefined, JSON.stringify(ts.town));
  st3.places.form.population = 0; ts = VB.placeSpecFromForm(st3);
  check("tiny: population 0 is kept (not replaced by the 600 default)", ts.town.population === 0 && ts.town.settlement === undefined, JSON.stringify(ts.town));
  st3.places.form.population = ""; check("empty population falls back to 600", VB.placeSpecFromForm(st3).town.population === 600);
  st3.places.form.population = 2; st3.places.form.settlement = "cabin"; let te = VB.placeEstimate(st3);
  check("tiny estimate: cabin, small place, no problems, no misfiring size warning", te.problems.length === 0 && te.level === "" && te.tiny === "cabin" && te.size[0] === 400 && /cabin/.test(te.text), JSON.stringify(te));
  st3.places.form.population = 0; te = VB.placeEstimate(st3);
  check("population 0 estimate says terrain only", /no settlement/.test(te.text) && te.est === 0, te.text);
  st3.places.form.population = 12; st3.places.form.settlement = "auto"; te = VB.placeEstimate(st3);
  check("12 people estimate: hamlet 800 x 600", te.tiny === "hamlet" && te.size.join() === "800,600", JSON.stringify(te));
  VB.placeFormFromSpec(st3, { name: "Inn", town: { population: 8, settlement: "inn" } });
  check("spec -> form keeps the settlement", st3.places.form.settlement === "inn" && st3.places.form.population === 8);
  st3.places.form = VB.placesDefaults().form; st3.places.form.name = ""; st3.places.form.id = "";
  const ej = VB.jobPlaceCreate(st3, d, {});
  check("Generate with an empty form does not throw: an id is made, python names the place", /^new_place_\d{8}_\d{4}$/.test(ej.newPlace) && !ej.params.spec.name, ej.newPlace);
  // from-text with tiny words (real python)
  st3.places.from_text = "a lone farmstead in the hills"; r = await runner.run(VB.jobPlaceFromText(st3));
  check("from-text 'a lone farmstead' -> 4 people farmstead", r.ok && st3.places.form.population === 4 && st3.places.form.settlement === "farmstead", r.error + JSON.stringify(st3.places.form));
  // ---- blank place
  st3.places.blank = Object.assign(VB.placesDefaults().blank, { name: "ZZ Blank", width_ft: 600, height_ft: 400 });
  check("blank args: create-blank, name, slug id, size, recipe flat", JSON.stringify(VB.placeBlankArgs(st3.places.blank).args) === JSON.stringify(["create-blank", "--name", "ZZ Blank", "--id", "zz_blank", "--size-ft", "600", "400", "--recipe", "flat"]), JSON.stringify(VB.placeBlankArgs(st3.places.blank).args));
  Object.assign(st3.places.blank, { recipe: "valley", relief_ft: 120, cell_ft: 10, seed: 7, scale_ft_per_in: 40, grid_ft: 10, underlay: "C:/m/a.png", force: true });
  const ba = VB.placeBlankArgs(st3.places.blank).args.join(" ");
  check("blank args map every field", /--recipe valley/.test(ba) && /--relief-ft 120/.test(ba) && /--cell-ft 10/.test(ba) && /--seed 7/.test(ba) && /--scale-ft-per-in 40/.test(ba) && /--grid-ft 10/.test(ba) && /--underlay C:\/m\/a\.png/.test(ba) && /--force/.test(ba), ba);
  st3.places.blank.recipe = "flat"; check("relief is not sent for flat", !/--relief-ft/.test(VB.placeBlankArgs(st3.places.blank).args.join(" ")));
  check("blank problems: no name, bad size, bad cell", /name/.test(VB.placeBlankProblem({ width_ft: 600, height_ft: 400 })) && /100-18000/.test(VB.placeBlankProblem({ name: "x y", width_ft: 50, height_ft: 400 })) && /cell/.test(VB.placeBlankProblem({ name: "xy", width_ft: 600, height_ft: 400, recipe: "flat", cell_ft: 90 })));
  calls.length = 0; st3.places.blank = Object.assign(VB.placesDefaults().blank, { name: "ZZ Blank", width_ft: 600, height_ft: 400 });
  let bj = VB.jobPlaceBlank(st3, true); r = await runner.run(bj);
  check("blank dry run: --dry-run sent, no place to switch to, result remembered", r.ok && calls[0].includes("--dry-run") && bj.newPlace === null && st.places.last.blank === "zz_blank" && st.places.last.dry === true, r.error + JSON.stringify(calls));
  bj = VB.jobPlaceBlank(st3, false); calls.length = 0; r = await runner.run(bj);
  check("blank create: no --dry-run, switches to the new place", r.ok && !calls[0].includes("--dry-run") && bj.newPlace === "zz_blank");
  st3.places.blank.width_ft = 20; r = await runner.run(VB.jobPlaceBlank(st3, false));
  check("blank create refuses a bad size before python", !r.ok && /100-18000/.test(r.error || ""), r.error);
  // ---- manage places
  const st4 = VB.normalize(null); st4.place = "zz_cur";
  Object.assign(st4.places.manage, { name: "New", kind: "dungeon", focus_x: 10, focus_y: 20, scale_ft_per_in: 20, grid_ft: 5, notes: "n" });
  const ea = VB.placeManageArgs(st4, "edit", "zz_a", true).join(" ");
  check("edit args map the fields + dry run", ea === "edit --place zz_a --name New --notes n --kind dungeon --focus 10 20 --scale-ft-per-in 20 --grid-ft 5 --dry-run", ea);
  check("edit with nothing filled is refused", (() => { try { VB.placeManageArgs({ places: { manage: {} } }, "edit", "zz_a"); return false; } catch (x) { return /nothing to change/.test(x.message); } })());
  st4.places.manage.new_id = "zz_b";
  check("rename args", VB.placeManageArgs(st4, "rename", "zz_a").join(" ") === "rename --place zz_a --new-id zz_b");
  st4.places.manage.include_export = true; check("rename --include-export", VB.placeManageArgs(st4, "rename", "zz_a").includes("--include-export")); st4.places.manage.include_export = false;
  const refuse = (op, place, o, re) => { try { VB.jobPlaceManage(st4, op, place, o || {}); return false; } catch (x) { return re.test(x.message); } };
  check("rename / trash of the open place are refused", refuse("rename", "zz_cur", {}, /switch to another place/) && refuse("trash", "zz_cur", {}, /switch to another place/));
  check("rename needs a selected place", refuse("rename", "", {}, /select a place/));
  st4.places.manage.new_id = "zz_taken"; check("rename refuses an existing id", refuse("rename", "zz_a", { existing: ["zz_taken"] }, /already exists/));
  st4.places.manage.new_id = "schema"; check("rename refuses a reserved id", refuse("rename", "zz_a", {}, /reserved/));
  st4.places.manage.new_id = "zz_b"; calls.length = 0;
  let mjob = VB.jobPlaceManage(st4, "rename", "zz_a", { dry: true }); r = await runner.run(mjob);
  check("rename check runs place_manage rename --dry-run and records the plan", r.ok && /place_manage\.py$/.test(calls[0][0]) && calls[0].slice(1).join(" ") === "rename --place zz_a --new-id zz_b --dry-run" && st.places.last.manage === "rename", JSON.stringify(calls));
  check("rename job carries the new id for the place pickers", VB.jobPlaceManage(st4, "rename", "zz_a").manage.newId === "zz_b");
  st4.places.manage.dup_id = "zz_copy"; st4.places.manage.dup_name = "Copy";
  check("duplicate args + switches to the copy", VB.placeManageArgs(st4, "duplicate", "zz_a").join(" ") === "duplicate --place zz_a --new-id zz_copy --name Copy" && VB.jobPlaceManage(st4, "duplicate", "zz_a").newPlace === "zz_copy");
  check("purge needs a trash entry", refuse("purge", "", {}, /trash entry/));
  st4.places.manage.trash_entry = "zz_x_1";
  check("purge needs the typed id", refuse("purge", "", {}, /type the place id/));
  st4.places.manage.purge_confirm = "zz_x";
  check("purge args", VB.placeManageArgs(st4, "purge", "").join(" ") === "purge --entry zz_x_1 --confirm zz_x");
  st4.places.manage.restore_as = "zz_back"; check("restore --as", VB.placeManageArgs(st4, "restore", "").join(" ") === "restore --entry zz_x_1 --as zz_back");
  r = await runner.run(VB.jobPlaceManage(st4, "trash_list", ""));
  check("trash list fills state", r.ok && st.places.trash.length === 1 && st.places.trash[0].place === "zz_x");
  check("id rules mirror python", VB.placeIdProblem("ok_id") === "" && !!VB.placeIdProblem("A") && !!VB.placeIdProblem("com3") && !!VB.placeIdProblem("x") && !!VB.placeIdProblem("zz", ["zz"]));
  // static: controls exist, no blocking dialogs in the Places UI, population accepts 0
  const pu = fs.readFileSync(path.join(__dirname, "../places_ui.js"), "utf8");
  ["pl_blank_create", "pl_blank_check", "pl_edit_load", "pl_edit_apply", "pl_rename", "pl_rename_check", "pl_duplicate", "pl_trash", "pl_restore", "pl_purge"].forEach(a => check("index.html has " + a + " and places_ui wires it", ih.includes('data-act="' + a + '"') && pu.includes(a + ":")));
  check("population field accepts 0", /data-s="places\.form\.population" min="0"/.test(ih));
  check("places_ui uses no window.confirm / alert / prompt", !/\b(window\.)?(confirm|alert|prompt)\(/.test(pu));
  check("destructive buttons are two-click armed", /armOrRun\("trash:/.test(pu) && /armOrRun\("purge:/.test(pu));
  console.log(ok + " passed, " + fail + " failed"); try { fs.unlinkSync(specFile); } catch (x) { /* ignore */ } process.exit(fail ? 1 : 0);
})();
