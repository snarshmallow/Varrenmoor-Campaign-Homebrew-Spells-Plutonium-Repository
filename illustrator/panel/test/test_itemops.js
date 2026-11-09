// Fast map edits (lib/itemops.js + host.jsx delete_items / replace_items / rename_items + Roads tab 'Update only the changed items (fast)').
// Pure matching, host.jsx on a mock Illustrator document (locked / hidden layers, _x5F_ names, double items), job steps (no render_world / replace_layer on the
// fast path, full refresh only as a fallback) and a real run on a temp COPY of a small place with a mock host.
//   node illustrator/panel/test/test_itemops.js
const fs = require("fs"), path = require("path"), os = require("os"), vm = require("vm"), cp = require("child_process");
const IO = require("../lib/itemops.js");
const VB = require("../lib/core.js"); require("../lib/styles.js"); require("../lib/objects.js"); const R = require("../lib/runner.js");
let ok = 0, fail = 0; const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x === undefined ? "" : typeof x === "string" ? x : JSON.stringify(x)); } };

// ---- 1. pure matching
check("decodeName: _x5F_ and padding", IO.decodeName(" str_x5F_020_x5F_label ") === "str_020_label");
check("nameForms: space form for old imports", JSON.stringify(IO.nameForms("str 020 label")) === JSON.stringify(["str 020 label", "str_020_label"]));
const ids = ["str_020", "str_02"];
const M = (n, m) => IO.matchName(n, ids, m);
[["str_020", "str_020"], ["str_x5F_020", "str_020"], ["str 020", "str_020"], ["str_020_label", "str_020"], ["str_020_label_halo", "str_020"], ["str_020_label_halo_tp", "str_020"],
  ["str_020_label_box", "str_020"], ["str_020_label_tp", "str_020"], ["str_020_callout", "str_020"], ["str_020_leader", "str_020"], ["str_020_leader_casing", "str_020"],
  ["str_020_leader_dot", "str_020"], ["str_020_marker", "str_020"], ["str_020_marknum", "str_020"], ["flat_str_020", "str_020"], ["str_020_kerb3", "str_020"],
  ["mk_str_020_start", "str_020"], ["mk_str_020_end", "str_020"], ["str_02", "str_02"], ["str_02_label", "str_02"], ["flat_str_02", "str_02"],
  ["str_0201", null], ["str_020_3", null], ["str_020x", null], ["xstr_020", null], ["str_020_labelx", null], ["flat_str_0201", null], ["mk_str_020_middle", null], ["", null]]
  .forEach(([n, want]) => check("family match " + JSON.stringify(n) + " -> " + want, M(n) === want, M(n)));
check("exact match only takes the id itself", M("str_020", "exact") === "str_020" && M("str_020_label", "exact") === null);
check("prefix match takes anything after <id>_", M("str_020_whatever_9", "prefix") === "str_020" && M("str_0209", "prefix") === null);
check("regex escapes special characters in ids", new RegExp(IO.regexSource(["a.b(c)"])).test("a.b(c)_label") && !new RegExp(IO.regexSource(["a.b"])).test("axb"));
check("empty id list matches nothing", !new RegExp(IO.regexSource([])).test("") && !new RegExp(IO.regexSource([])).test("str_020"));
const tg = IO.targets(["str_020"], "road");
const T = l => tg.find(t => t.layer === l) || {};
check("road targets: outline + centreline by exact name", JSON.stringify(T("Roads").names) === '["str_020"]' && JSON.stringify(T("Road Centerlines").names) === '["str_020"]');
check("road targets: label text, curved path, callout group; halo / box on Label Backing", T("Labels - Streets").names.join() === "str_020_label,str_020_label_tp,str_020_callout" &&
  T("Label Backing").names.join() === "str_020_label_halo,str_020_label_halo_tp,str_020_label_box");
check("road targets: leaders, anchors, markers, flat fill copy", T("Leaders").names.join() === "str_020_leader,str_020_leader_casing" && T("Leader Anchors").names.join() === "str_020_leader_dot" &&
  T("ART - Fill Shapes").names.join() === "flat_str_020" && T("Callout Markers").names.length === 2);
check("road targets: kerbs and off-map arrows by pattern", new RegExp(T("Details").patterns[0]).test("str_020_kerb12") && !new RegExp(T("Details").patterns[0]).test("str_0201_kerb1") &&
  new RegExp(T("Bounds").patterns[0]).test("mk_str_020_end"));
const bt = IO.targets(["bld_house_041"], "building"), B = l => bt.find(t => t.layer === l) || {};
check("building targets: Buildings, Building Footprints, lots, details, fences, labels", B("Buildings").names[0] === "bld_house_041" && B("Building Footprints").names[0] === "bld_house_041" &&
  B("DETAILS - Lots").names[0] === "bld_house_041_lot" && B("Details").names.indexOf("bld_house_041_roof") >= 0 && new RegExp(B("Details").patterns[0]).test("bld_house_041_door1") &&
  new RegExp(B("Fences").patterns[0]).test("bld_house_041_fence2") && B("Labels - Buildings").names[0] === "bld_house_041_label");
check("targets(only): limited to the named layers", IO.targets(["a"], "road", ["Roads"]).length === 1);
let threw = false; try { IO.targets(["a"], "nope"); } catch (e) { threw = true; } check("unknown preset refused", threw);
const many = Array.from({ length: 450 }, (_, i) => "str_" + i);
const reqs = IO.deleteRequests(many.concat(["str_1", ""]), "road");
check("chunking: 450 ids (+ a duplicate and an empty one) -> 3 calls of <= 200", reqs.length === 3 && reqs[0].ids.length === 200 && reqs[2].ids.length === 50 && reqs.every(r => r.action === "delete_items" && r.timeout_ms > 0 && r.targets.length && r.layers.length === r.targets.length));
const mr = IO.mergeResults([{ ok: true, removed: 3, per_layer: { Roads: 1, Details: 2 }, not_found: ["a"] }, { ok: true, removed: 2, per_layer: { Roads: 2 }, not_found: [] }]);
check("mergeResults sums per layer", mr.ok && mr.removed === 5 && mr.deleted === 5 && mr.per_layer.Roads === 3 && mr.not_found.join() === "a" && mr.calls === 2);
check("mergeResults: one failed call -> ok false + error", IO.mergeResults([{ ok: true, removed: 1 }, { ok: false, error: "unknown action: delete_items" }]).ok === false);
const S = (id, pts, w) => ({ id, kind: "lane", geometry: { points: pts, width_ft: w || 14 } });
const df = IO.diffStreets({ streets: [S("a", [[0, 0], [1, 1]]), S("b", [[0, 0], [2, 2]]), S("c", [[5, 5], [6, 6]])] }, { streets: [S("a", [[0, 0], [1, 1]]), S("b", [[0, 0], [3, 3]]), S("d", [[1, 1], [2, 2]])] });
check("diffStreets: gone / changed / added", df.gone.join() === "c" && df.changed.join() === "b" && df.added.join() === "d", df);
check("diffStreets: width change counts as changed", IO.diffStreets({ streets: [S("a", [[0, 0], [1, 1]], 10)] }, { streets: [S("a", [[0, 0], [1, 1]], 12)] }).changed.join() === "a");
check("VBCore gets deleteItemsSteps + itemOps", VB.deleteItemsSteps === IO.deleteItemsSteps && VB.itemOps === IO);

// ---- 2. host.jsx on a mock document
const hostSrc = fs.readFileSync(path.join(__dirname, "../jsx/host.jsx"), "utf8");
const strip = t => t.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/.*$/gm, "").replace(/"(?:[^"\\\n]|\\.)*"/g, '""').replace(/'(?:[^'\\\n]|\\.)*'/g, "''");
const blk = (() => { const a = hostSrc.indexOf("// ---- surgical item edits"), b = hostSrc.indexOf("function VB_openQuiet"); return strip(hostSrc.slice(a, b)); })();
check("host item helpers are ES3 (no let/const, arrows, template literals)", blk.length > 2000 && !/(^|[^\w.$])(let|const)\s+[\w$\[{]/m.test(blk) && !/=>/.test(blk) && !/`/.test(blk));
const caseBlk = strip(hostSrc.slice(hostSrc.indexOf('case "delete_items"'), hostSrc.indexOf("default: throw new Error(\"unknown action")));
check("host item actions are ES3 and present", !/=>|`/.test(caseBlk) && ["delete_items", "replace_items", "rename_items"].every(a => hostSrc.indexOf('case "' + a + '"') >= 0));
check("replace_items closes the SVG and re-activates the target in finally, hides raster-heavy layers", /finally \{[\s\S]*qsvg\.close[\s\S]*app\.activeDocument = qdoc[\s\S]*VB_restoreHeavy\(qhid\)/.test(hostSrc.slice(hostSrc.indexOf('case "replace_items"'), hostSrc.indexOf('case "rename_items"'))));

let docs = [];
class Coll extends Array {
  getByName(n) { const f = this.find(x => x.name === n); if (!f) throw new Error("No such element"); return f; }
}
function editable(l) { for (let p = l; p && p.typename === "Layer"; p = p.parent) { if (p.locked || !p.visible) return false; } return true; }
class Layer {
  constructor(name, parent, doc) { this.name = name; this.typename = "Layer"; this.layers = new Coll(); this.pageItems = new Coll(); this._locked = false; this._visible = true; this.parent = parent; this.doc = doc; this.toggles = 0; }
  get locked() { return this._locked; } set locked(v) { if (v !== this._locked) this.toggles++; this._locked = v; }
  get visible() { return this._visible; } set visible(v) { if (v !== this._visible) this.toggles++; this._visible = v; }
}
let seq = 0;
class Item {
  constructor(layer, name, typename) { this.layer = layer; this.name = name; this.typename = typename || "PathItem"; this.locked = false; this.hidden = false; this.uid = ++seq; this.contents = ""; if (layer) layer.pageItems.push(this); }
  remove() { if (!editable(this.layer)) throw new Error("Target layer cannot be modified"); if (this.locked) throw new Error("item locked"); this.layer.pageItems.splice(this.layer.pageItems.indexOf(this), 1); this.removed = true; }
  duplicate(rel, where) {
    const tl = rel.typename === "Layer" ? rel : rel.layer;
    if (!editable(tl)) throw new Error("Target layer cannot be modified");
    const d = new Item(null, this.name, this.typename); d.src = this.uid; d.layer = tl;
    if (where === "PLACEBEFORE") tl.pageItems.splice(tl.pageItems.indexOf(rel), 0, d); else if (where === "PLACEATBEGINNING") tl.pageItems.unshift(d); else tl.pageItems.push(d);
    return d;
  }
}
function mkDoc(name) {
  const doc = { name, layers: new Coll(), artboards: [{ artboardRect: [0, 792, 1224, 0] }], typename: "Document" };
  doc.mk = (n, parent) => { const p = parent || doc, l = new Layer(n, parent || doc, doc); p.layers.push(l); return l; };
  doc.close = () => { docs = docs.filter(d => d !== doc); doc.closed = true; };
  return doc;
}
const D = mkDoc("map.ai");
const LABELS = D.mk("LABELS"), Lst = D.mk("Labels - Streets", LABELS), Lhid = D.mk("Labels - Hidden", LABELS), Lbk = D.mk("Label Backing", LABELS), Lld = D.mk("Leaders", LABELS), Lan = D.mk("Leader Anchors", LABELS);
const LINES = D.mk("LINES"), Roads = D.mk("Roads", LINES), Det = D.mk("Details", LINES), Cl = D.mk("Road Centerlines");
const GUIDES = D.mk("GUIDES"), Grid = D.mk("Grid", GUIDES), Bounds = D.mk("Bounds", GUIDES), FS = D.mk("ART - Fill Shapes");
Lhid.visible = false; Lld.locked = true; GUIDES.locked = true; Grid.locked = true; Bounds.locked = true;
[Lhid, Lld, GUIDES, Grid, Bounds].forEach(l => { l.toggles = 0; });
new Item(Grid, "grid_10ft");
const keepers = [new Item(Roads, "str_0201"), new Item(Roads, "str_02x"), new Item(Roads, "str_020_3"), new Item(Lst, "str_0201_label", "TextFrame"), new Item(Det, "str_0201_kerb1")];
const r1 = new Item(Roads, "str_x5F_020", "CompoundPathItem"), r1dup = new Item(Roads, "str_020"), c1 = new Item(Cl, "str_020"), lab = new Item(Lst, "str_020_callout", "GroupItem");
const hid = new Item(Lhid, "str_020_label", "TextFrame"), halo = new Item(Lbk, "str_020_label_halo", "TextFrame"), ld1 = new Item(Lld, "str_020_leader"), ld2 = new Item(Lld, "str_020_leader_casing");
const dot = new Item(Lan, "str_020_leader_dot"), k1 = new Item(Det, "str_020_kerb1"), k2 = new Item(Det, "str 020 kerb2"), mk1 = new Item(Bounds, "mk_str_020_start"), fl = new Item(FS, "flat_str_020");
k1.locked = true; fl.hidden = true;
docs = [D];
global.app = { get documents() { return { length: docs.length }; }, activeDocument: D, version: "mock", userInteractionLevel: 0, open: f => { const d = f._doc; docs.push(d); app.activeDocument = d; return d; } };
global.UserInteractionLevel = { DONTDISPLAYALERTS: 1 }; global.SaveOptions = { DONOTSAVECHANGES: 0 };
global.ElementPlacement = { PLACEATBEGINNING: "PLACEATBEGINNING", PLACEATEND: "PLACEATEND", PLACEBEFORE: "PLACEBEFORE", PLACEAFTER: "PLACEAFTER" };
global.PathPointSelection = { ANCHORPOINT: 1 }; global.RGBColor = function () {}; global.DocumentColorSpace = {}; global.IllustratorSaveOptions = function () {};
global.ExportOptionsPNG24 = function () {}; global.ExportType = {}; global.$ = { level: 0 };
const files = {};
global.File = function (p) { this.fsName = p; this.exists = !!files[p]; this._doc = files[p]; };
vm.runInThisContext(hostSrc);
const run = a => JSON.parse(VB_run(JSON.stringify(a)));
// mirror: host regex == itemops regex
const sample = [["str_020"], ["str_020", "bld_a.b", "x-y/z"], [], ["a(b)", "c|d"]];
check("host VB_itemRegex mirrors itemops.regexSource (family / exact / prefix)", sample.every(s => ["family", "exact", "prefix", undefined].every(m => VB_itemRegex(s, m) === IO.regexSource(s, m))));
check("host VB_ITEM_FAMILY == itemops FAMILY_SUFFIX", VB_ITEM_FAMILY === IO.FAMILY_SUFFIX);

let r = run(IO.deleteRequests(["str_020", "str_999"], "road")[0]);
const alive = it => !it.removed;
check("delete_items ok", r.ok, r);
check("removed every item of str_020 (outline incl. _x5F_ name and a double, centreline, callout, hidden label, halo, leaders, dot, kerbs incl. a locked one and a space name, off-map arrow, flat copy)",
  [r1, r1dup, c1, lab, hid, halo, ld1, ld2, dot, k1, k2, mk1, fl].every(it => it.removed), [r1, r1dup, c1, lab, hid, halo, ld1, ld2, dot, k1, k2, mk1, fl].filter(alive).map(i => i.name));
check("items of other roads untouched (str_0201, str_02x, str_020_3 ...)", keepers.every(alive));
check("count + per layer", r.removed === 13 && r.deleted === 13 && r.per_layer.Roads === 2 && r.per_layer.Details === 2 && r.per_layer.Bounds === 1, r);
check("not_found lists ids with nothing on the map", r.not_found.join() === "str_999", r.not_found);
check("missing layers reported, not an error", r.missing_layers.indexOf("Callout Markers") >= 0);
check("locked / hidden layers restored (Leaders locked, Labels - Hidden hidden, GUIDES + Bounds locked)", Lld.locked && !Lhid.visible && GUIDES.locked && Bounds.locked);
check("a locked layer without a match is never touched (Grid)", Grid.toggles === 0 && Grid.locked);
// generic mode (what lib/buildedit.js sends without targets): ids + layers, family match
const g1 = new Item(Roads, "str_030"), g2 = new Item(Lbk, "str_x5F_030_label_halo"), g3 = new Item(Roads, "str_0301");
r = run({ action: "delete_items", ids: ["str_030"], layers: ["Roads", "Label Backing", "Nope"] });
check("generic ids + layers: family items removed, near names kept", r.ok && g1.removed && g2.removed && !g3.removed && r.removed === 2 && r.missing_layers.join() === "Nope", r);
const g4 = new Item(Det, "str_031_kerb1"), g5 = new Item(Bounds, "mk_str_031_end");
r = run({ action: "delete_items", ids: ["str_031"] });
check("generic ids, no layers: every layer walked (incl. locked GUIDES > Bounds), locks restored", r.ok && g4.removed && g5.removed && Bounds.locked && GUIDES.locked, r);
r = run({ action: "delete_items", ids: [] });
check("delete_items without ids is refused", !r.ok && /needs ids/.test(r.error));
const cap = Array.from({ length: 5 }, (_, i) => new Item(Det, "str_040_kerb" + i));
r = run({ action: "delete_items", ids: ["str_040"], layers: ["Details"], max: 3 });
check("item cap stops the walk and says so", r.ok && r.truncated === true && cap.filter(it => it.removed).length === 3, r);
// replace_items: SVG items replace same-named items in place
const S1 = mkDoc("roads_items.svg"), sR = S1.mk("Roads", S1.mk("LINES")), sC = S1.mk("Road Centerlines");
new Item(sR, "str_0201"); new Item(sR, "str_new"); new Item(sC, "str_0201");
files["C:/tmp/roads_items.svg"] = S1;
const before = Roads.pageItems.map(i => i.name), pos = Roads.pageItems.findIndex(i => i.name === "str_0201"), oldUid = Roads.pageItems[pos].uid;
Roads.locked = true;
r = run({ action: "replace_items", path: "C:/tmp/roads_items.svg", layers: ["Roads", "Road Centerlines"] });
const nowR = Roads.pageItems;
check("replace_items ok: outline replaced; new road + first centreline added", r.ok && r.replaced === 1 && r.added === 2, r);
check("replaced outline sits where the old one was (one below the new top item) and the old one is gone", nowR.findIndex(i => i.name === "str_0201") === pos + 1 && !nowR.some(i => i.uid === oldUid) && nowR.filter(i => i.name === "str_0201").length === 1, nowR.map(i => i.name));
check("new road added on top of its layer", nowR[0].name === "str_new");
check("other items untouched", ["str_02x", "str_020_3"].every(n => nowR.some(i => i.name === n)));
check("centreline appended (none before)", Cl.pageItems.some(i => i.name === "str_0201" && i.src));
check("layer lock restored, svg closed, target active again", Roads.locked === true && S1.closed && app.activeDocument === D);
Roads.locked = false;
r = run({ action: "replace_items", path: "C:/tmp/roads_items.svg", layers: ["ART - Fill Streets"] });
check("replace_items refuses ART layers", !r.ok && /ART/.test(r.error));
// rename_items
const n1 = new Item(Roads, "str_050"), n2 = new Item(Lst, "str_050_label", "TextFrame"), n3 = new Item(FS, "flat_str_050"), n4 = new Item(Roads, "str_0501");
r = run({ action: "rename_items", renames: [{ from: "str_050", to: "str_mill", text: "Mill Lane" }] });
check("rename_items renames the family and sets the label text", r.ok && n1.name === "str_mill" && n2.name === "str_mill_label" && n2.contents === "Mill Lane" && n3.name === "flat_str_mill" && n4.name === "str_0501", [n1.name, n2.name, n3.name, n4.name, r]);

// ---- 3. Roads tab jobs (fast path) + a real run on a temp copy with a mock host
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local", GONE = "str_020";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbitemops-")).split(path.sep).join("/"), wr = TMP + "/world", wd = `${wr}/${place}`;
fs.mkdirSync(`${wd}/buildings`, { recursive: true });
fs.readdirSync(`${ROOT}/world/${place}`).filter(f => /\.json$/.test(f)).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/${f}`, `${wd}/${f}`));
fs.readdirSync(`${ROOT}/world/${place}/buildings`).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/buildings/${f}`, `${wd}/buildings/${f}`));
process.env.VB_WORLD_ROOT = wr;
const st = VB.normalize(null); st.place = place;
const d = Object.assign({}, VB.dirs(ROOT, place), { panel: TMP + "/panel", world: wd });
let hostCalls = [], hostReply = a => ({ ok: true, removed: 4, per_layer: { Roads: 1 }, not_found: [], replaced: 3, added: 0, items: 0, replaced_layers: a.names || [] });
const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, host: async a => { hostCalls.push(a); return hostReply(a); }, log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: (s) => { s.forEach(k => { st.stale[k] = true; }); } });
(async () => {
  check("default mode: fast item update", st.objects.nr.mapMode === "items" && VB.roadMapMode(st) === "items");
  st.objects.rids = [GONE]; st.objects.nr.confirmDelete = true;
  const j = VB.jobRoadsDelete(st, d);
  const lab = j.steps.map(s => s.label || s.script || "");
  check("delete job: snapshot, delete-road, diff, delete_items, render_items, replace_items, then the gated fallback", /note the roads before/.test(lab[0]) && j.steps[1].t === "py" && /delete-road/.test(j.steps[1].args.join(" ")) &&
    lab.findIndex(l => /delete_items/.test(l)) < lab.findIndex(l => /render_items/.test(l)) && lab.findIndex(l => /render_items/.test(l)) < lab.findIndex(l => /replace_items/.test(l)), lab);
  const okRun = { vars: { roadDiff: { gone: [GONE], changed: [], added: [] }, roadDel: { ok: true }, roadRep: { ok: true }, roadItems: { drawn: ["str_008"] } }, exists: () => true };
  check("fast path: no render_world and no replace_layer step runs when the host calls succeed", j.steps.filter(s => (s.t === "py" && /render_world/.test(s.script)) || (s.t === "host" && /replace_layer/.test(JSON.stringify(s.action))))
    .every(s => s.when && !s.when(okRun)));
  const badRun = { vars: { roadDiff: { gone: [GONE], changed: [], added: [] }, roadDel: { ok: false, error: "unknown action: delete_items" } }, exists: () => true };
  check("fallback: the full refresh runs when delete_items failed", j.steps.filter(s => s.t === "py" && /render_world/.test(s.script)).every(s => s.when(badRun)) &&
    j.steps.filter(s => s.t === "py" && /render_items/.test(s.script)).every(s => !s.when(badRun)));
  check("contours marked stale, params.map = items", (j.setStale || []).includes("contours") && j.params.map === "items");
  st.objects.nr.mapMode = "full";
  check("mode 'full': the old refresh (render_world first, no snapshot)", VB.jobRoadsDelete(st, d).steps.some(s => /render_world/.test(s.script || "") && !s.when) && !/note the roads/.test(VB.jobRoadsDelete(st, d).steps[0].label || ""));
  st.objects.nr.mapMode = "items"; st.objects.nr.map = false;
  check("map off: no fast steps either", !VB.jobRoadsDelete(st, d).steps.some(s => /delete_items|render_items/.test(s.label || s.script || "")));
  st.objects.nr.map = true;
  st.objects.rids = ["str_008"]; st.objects.nr.simplify = 1;
  ["Shape", "Split", "Undo"].forEach(k => check(k + " job uses the fast path", VB["jobRoads" + k](st, d).steps.some(s => /render_items/.test(s.script || ""))));
  ["add", "reshape", "sync"].forEach(m => check("from paths (" + m + ") uses the fast path", VB.jobRoadsFromPaths(st, d, m).steps.some(s => /render_items/.test(s.script || ""))));
  check("Redraw roads on the map (full) stays the full refresh", VB.jobRoadsMap(st, d).label === "Redraw roads on the map (full)" && VB.jobRoadsMap(st, d).steps.some(s => /render_world/.test(s.script || "") && !s.when));
  const jb = VB.jobRoadsBlocks(st, d);
  check("Refresh blocks only: one render, only Blocks replaced", jb.steps.filter(s => s.t === "host" && s.action.action === "replace_layer").map(s => s.action.names.join()).join("|") === "Blocks");
  // building preset steps for lib/buildedit.js: chunked, run.last + fastFail
  const bsteps = VB.deleteItemsSteps(many, "building"), calls = [], fr = { vars: {}, log: () => {}, host: async a => { calls.push(a); return { ok: true, removed: 1, per_layer: { Buildings: 1 } }; } };
  await bsteps[0].fn(fr);
  check("deleteItemsSteps: one fn step, 3 host calls for 450 ids, summary in run.last / run.vars", bsteps.length === 1 && calls.length === 3 && fr.last.ok && fr.last.removed === 3 && fr.vars.itemops === fr.last && fr.vars.fastFail === false);
  const fr2 = { vars: {}, log: () => {}, host: async () => ({ ok: false, error: "unknown action: delete_items" }) }, calls2 = [];
  await VB.deleteItemsSteps(function () { return ["bld_a", "bld_b"]; }, "building")[0].fn(fr2);
  check("deleteItemsSteps: ids from a function; a failed call -> ok false, fastFail true, never throws", fr2.last.ok === false && fr2.vars.fastFail === true && /unknown action/.test(fr2.last.error));
  const fr3 = { vars: {}, log: () => {}, host: async () => { throw new Error("Illustrator did not answer within 60 s"); } };
  await VB.deleteItemsSteps(["bld_a"], "building")[0].fn(fr3);
  check("deleteItemsSteps: a host timeout is caught", fr3.last.ok === false && /did not answer/.test(fr3.last.error));

  // real run: delete str_020 on a temp copy, mock Illustrator
  const orig = fs.readFileSync(`${wd}/streets.json`, "utf8");
  st.objects.rids = [GONE]; st.objects.nr.confirmDelete = true; hostCalls = [];
  let rr = await runner.run(VB.jobRoadsDelete(st, d));
  check("fast delete runs", rr.ok, rr.error);
  const acts = hostCalls.map(a => a.action);
  check("Illustrator got exactly delete_items + replace_items (no replace_layer, no render)", acts.join() === "delete_items,replace_items", acts);
  const dc = hostCalls[0];
  check("delete_items: the deleted id, road targets incl. Roads / Road Centerlines / Labels - Streets / Details / Bounds", dc.ids.join() === GONE && ["Roads", "Road Centerlines", "Labels - Streets", "Label Backing", "Leaders", "Details", "Bounds", "ART - Fill Shapes"].every(l => dc.layers.includes(l)));
  const svg = d.panel + "/roads_items.svg", t = fs.existsSync(svg) ? fs.readFileSync(svg, "utf8").replace(/_x5F_/g, "_") : "";
  check("render_items svg: neighbours redrawn, the deleted road absent", /id="str_014"/.test(t) && !new RegExp('id="' + GONE + '"').test(t), t.slice(0, 200));
  check("replace_items gets that svg and only Roads + Road Centerlines", hostCalls[1].path.replace(/\\/g, "/").endsWith("/roads_items.svg") && hostCalls[1].layers.join() === "Roads,Road Centerlines");
  check("stale note set (Blocks, fills, contours)", /Blocks/.test(st.objects.nr.stale) && /contours/.test(st.objects.nr.stale) && st.stale.contours === true, st.objects.nr.stale);
  // undo: the road comes back: drawn by render_items, no delete_items call (nothing gone)
  hostCalls = [];
  rr = await runner.run(VB.jobRoadsUndo(st, d));
  const t2 = fs.readFileSync(svg, "utf8").replace(/_x5F_/g, "_");
  check("undo: streets.json back byte for byte", rr.ok && fs.readFileSync(`${wd}/streets.json`, "utf8") === orig, rr.error);
  check("undo: only replace_items (the restored road + neighbours), the road is in the svg", hostCalls.map(a => a.action).join() === "replace_items" && new RegExp('id="' + GONE + '"').test(t2), hostCalls.map(a => a.action));
  // fallback when the panel's host.jsx is old (unknown action): full refresh
  hostReply = a => a.action === "delete_items" ? { ok: false, error: "unknown action: delete_items" } : { ok: true, replaced: [], items: 0 };
  hostCalls = []; st.objects.rids = [GONE]; st.objects.nr.confirmDelete = true; st.objects.nr.mapFills = false;
  rr = await runner.run(VB.jobRoadsDelete(st, d));
  const acts3 = hostCalls.map(a => a.action);
  check("old host.jsx: delete_items fails -> full refresh (render + replace_layer), job still ok", rr.ok && acts3[0] === "delete_items" && acts3.includes("replace_layer") && !acts3.includes("replace_items"), acts3);
  await runner.run(VB.jobRoadsUndo(st, d));
  const real = JSON.parse(fs.readFileSync(`${ROOT}/world/${place}/streets.json`, "utf8")).streets;
  check("real world untouched", real.some(s => s.id === GONE));
  // loader + publishing
  const html = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8"), list = /var files = \[([^\]]*)\]/.exec(html)[1];
  check("index.html loader lists lib/itemops.js before lib/objects.js", list.indexOf('"lib/itemops.js"') > 0 && list.indexOf('"lib/itemops.js"') < list.indexOf('"lib/objects.js"'));
  const src = fs.readFileSync(path.join(__dirname, "../lib/itemops.js"), "utf8");
  check("itemops.js publishes window.VBItemOps even when module exists", /root\.VBItemOps = api;/.test(src) && src.indexOf("root.VBItemOps = api") < src.indexOf("module.exports = api"));
  check("itemops.js is ES5 safe apart from async step functions (no arrow / let / const / template)", !/=>|`|(^|[^\w.$])(let|const)\s+[\w$]/m.test(strip(src)));
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})().catch(e => { console.log("FAIL threw", e.stack); process.exit(1); });
