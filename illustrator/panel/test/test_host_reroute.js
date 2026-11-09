// Mock-Illustrator test of the callout actions in jsx/host.jsx (reroute_leaders, read_label_positions, move_item, read_items).
// run: node illustrator/panel/test/test_host_reroute.js
const fs = require("fs"), path = require("path"), vm = require("vm");
let fails = 0;
const check = (n, ok, d) => { console.log((ok ? "ok   " : "FAIL ") + n + (ok ? "" : "  " + (d || ""))); if (!ok) fails++; };

// ---- tiny DOM: doc coords y up, artboard [0, 792, 1224, 0]
class Layer {
  constructor(name, parent) { this.name = name; this.typename = "Layer"; this.layers = []; this.pageItems = []; this.locked = false; this.visible = true; this.parent = parent; }
}
class Item {
  constructor(layer, name, typename, gb) { this.layer = layer; this.name = name; this.typename = typename; this.gb = gb; this.note = ""; this.hidden = false; this.locked = false; this.pts = []; layer.pageItems.push(this); }
  get geometricBounds() { if (this.typename === "PathItem" && this.pts.length) { const xs = this.pts.map(p => p[0]), ys = this.pts.map(p => p[1]); return [Math.min(...xs), Math.max(...ys), Math.max(...xs), Math.min(...ys)]; } return this.gb.slice(); }
  get pathPoints() { return this.pts.map(p => ({ anchor: p.slice() })); }
  setEntirePath(a) { if (this.layer.locked) throw new Error("layer locked"); this.pts = a.map(p => p.slice()); }
  translate(dx, dy) { if (this.layer.locked) throw new Error("layer locked"); this.gb = [this.gb[0] + dx, this.gb[1] + dy, this.gb[2] + dx, this.gb[3] + dy]; this.pts = this.pts.map(p => [p[0] + dx, p[1] + dy]); }
}
class Group extends Item {
  constructor(layer) { super(layer, "", "GroupItem", [0, 0, 0, 0]); this.pageItems = []; }
  translate(dx, dy) { if (this.layer.locked) throw new Error("layer locked"); this.pageItems.forEach(c => c.translate(dx, dy)); }
  get geometricBounds() { return this.pageItems.length ? this.pageItems[0].geometricBounds : [0, 0, 0, 0]; }
}
// Illustrator z-order: pageItems[0] is the FRONT (top) item; PLACEATBEGINNING = top, PLACEATEND = bottom of the container.
Item.prototype.move = function (g, where) { this.layer.pageItems.splice(this.layer.pageItems.indexOf(this), 1); if (where === "PLACEATBEGINNING") g.pageItems.unshift(this); else g.pageItems.push(this); };
Layer.prototype.groupItems = null;
const AB = [0, 792, 1224, 0];
const root = { layers: [], artboards: [{ artboardRect: AB }], selection: [] };
const mk = (name, parent) => { const l = new Layer(name, parent || root); (parent || root).layers.push(l); return l; };
const LABELS = mk("LABELS"), Lds = mk("Leaders", LABELS), Lan = mk("Leader Anchors", LABELS), Lb = mk("Labels - Buildings", LABELS), Lback = mk("Label Backing", LABELS);
Lds.locked = true;
const page2doc = (x, y) => [x, 792 - y];
const textBox = (cx, cy, w, h) => [cx - w / 2, 792 - (cy - h / 2), cx + w / 2, 792 - (cy + h / 2)];
// label 'bld_a': anchor (200, 300), text to the right-up at centre (260, 280)
const T = new Item(Lb, "bld_a_label", "TextFrame", textBox(260, 280, 60, 8));
const H = new Item(Lback, "bld_a_label_halo", "TextFrame", textBox(260, 280, 60, 8));
const D = new Item(Lan, "bld_a_leader_dot", "PathItem", [198.5, 792 - 298.5, 201.5, 792 - 301.5]); D.pts = [];
const Lw = new Item(Lds, "bld_a_leader", "PathItem", null); Lw.pts = [page2doc(200, 300), page2doc(224, 280), page2doc(229, 280)];
const Lc = new Item(Lds, "bld_a_leader_casing", "PathItem", null); Lc.pts = Lw.pts.map(p => p.slice());

Object.defineProperty(Layer.prototype, "groupItems", { get() { const l = this; return { add() { return new Group(l); } }; } });
global.app = { documents: { length: 1 }, activeDocument: root, version: "mock" };
root.layers.getByName = undefined;
Object.defineProperty(app.documents, "length", { value: 1 });
root.layers.getByName = function (n) { const f = this.find(l => l.name === n); if (!f) throw new Error("no layer"); return f; };
global.ElementPlacement = { PLACEATBEGINNING: "PLACEATBEGINNING", PLACEATEND: "PLACEATEND", PLACEBEFORE: "PLACEBEFORE", PLACEAFTER: "PLACEAFTER" }; global.PathPointSelection = { ANCHORPOINT: 1 };
global.RGBColor = function () {}; global.File = function () {}; global.DocumentColorSpace = {}; global.SaveOptions = {}; global.IllustratorSaveOptions = function () {};
global.ExportOptionsPNG24 = function () {}; global.ExportType = {};
vm.runInThisContext(fs.readFileSync(path.join(__dirname, "..", "jsx", "host.jsx"), "utf8"));
const run = a => JSON.parse(VB_run(JSON.stringify(a)));
const pg = (p) => [p[0], 792 - p[1]];

let r = run({ action: "read_label_positions" });
check("read_label_positions finds the callout", r.ok && r.labels.length === 1 && r.labels[0].id === "bld_a_label" && Math.abs(r.labels[0].cx - 260) < 0.01, JSON.stringify(r));
check("anchor from the dot, ref from the halo", Math.abs(r.labels[0].anchor[0] - 200) < 0.01 && Math.abs(r.labels[0].ref[0] - 260) < 0.01, JSON.stringify(r.labels[0]));

// nothing moved: poll mode records state, changes nothing
r = run({ action: "reroute_leaders", changed_only: true });
check("poll with nothing moved reroutes nothing", r.ok && r.rerouted === 0, JSON.stringify(r));
check("generated position remembered in the item note", /^vb_orig=260\.00,280\.00/.test(T.note), T.note);
check("leader layer lock restored", Lds.locked === true);

// drag the label 80 pt down-left of the anchor; anchor stays
r = run({ action: "move_item", name: "bld_a_label", dx: -150, dy: 60 });
check("move_item moves the text", r.ok && Math.abs(r.bounds[0] - (230 - 150)) < 0.01, JSON.stringify(r));
r = run({ action: "reroute_leaders", changed_only: true });
check("poll re-routes the moved callout", r.ok && r.rerouted === 1 && r.ids[0] === "bld_a", JSON.stringify(r));
const ri = run({ action: "read_items", names: ["bld_a_leader", "bld_a_leader_casing", "bld_a_label_halo", "bld_a_leader_dot"] }).items;
const tb = [80, 340 - 4, 140, 340 + 4];   // new text box (page pt)
check("leader starts at the unchanged anchor", Math.abs(ri.bld_a_leader.points[0][0] - 200) < 0.01 && Math.abs(ri.bld_a_leader.points[0][1] - 300) < 0.01, JSON.stringify(ri.bld_a_leader));
const end = ri.bld_a_leader.points[ri.bld_a_leader.points.length - 1];
check("leader ends at the right edge of the new label position (+gap)", Math.abs(end[0] - (140 + 2)) < 0.01 && Math.abs(end[1] - 340) < 0.01, JSON.stringify(end));
check("elbow keeps a horizontal shelf", ri.bld_a_leader.points.length === 3 && Math.abs(ri.bld_a_leader.points[1][1] - end[1]) < 0.01);
check("casing follows the leader", JSON.stringify(ri.bld_a_leader_casing.points) === JSON.stringify(ri.bld_a_leader.points));
check("halo follows its text", Math.abs((ri.bld_a_label_halo.bounds[0] + ri.bld_a_label_halo.bounds[2]) / 2 - 110) < 0.01, JSON.stringify(ri.bld_a_label_halo));
check("anchor dot did not move", Math.abs((ri.bld_a_leader_dot.bounds[0] + ri.bld_a_leader_dot.bounds[2]) / 2 - 200) < 0.01);
check("locked layer is locked again", Lds.locked === true);
r = run({ action: "reroute_leaders", changed_only: true });
check("a second poll finds nothing new", r.ok && r.rerouted === 0, JSON.stringify(r));

// pinning data: ref (generated) stays the old position, current differs
r = run({ action: "read_label_positions" });
check("moved label: current vs generated position", Math.abs(r.labels[0].cx - 110) < 0.01 && Math.abs(r.labels[0].ref[0] - 260) < 0.01, JSON.stringify(r.labels[0]));

// drag the ANCHOR dot: the leader follows it
run({ action: "move_item", name: "bld_a_leader_dot", dx: 30, dy: -20 });
r = run({ action: "reroute_leaders", changed_only: true });
const ri2 = run({ action: "read_items", names: ["bld_a_leader"] }).items.bld_a_leader;
check("moving the anchor dot re-routes from the new anchor", r.rerouted === 1 && Math.abs(ri2.points[0][0] - 230) < 0.01 && Math.abs(ri2.points[0][1] - 280) < 0.01, JSON.stringify(ri2.points));

// straight style + style change, anchor above the box -> top edge
run({ action: "move_item", name: "bld_a_label", dx: 130, dy: 0 });
r = run({ action: "reroute_leaders", style: { style: "straight", color: "#ffffff", casing_color: "#000000", width: 1, casing_width: 2 } });
const ri3 = run({ action: "read_items", names: ["bld_a_leader"] }).items.bld_a_leader;
check("full re-route with straight style: two points", r.ok && r.rerouted === 1 && ri3.points.length === 2, JSON.stringify(ri3.points));
// label dropped onto the anchor: leader hidden
run({ action: "move_item", name: "bld_a_label", dx: 0, dy: -60 });
r = run({ action: "reroute_leaders" });
const ri4 = run({ action: "read_items", names: ["bld_a_leader"] }).items.bld_a_leader;
check("label on top of its anchor hides the leader", r.hidden_leaders === 1 && ri4.hidden === true, JSON.stringify(r));
r = run({ action: "reroute_leaders", ids: ["nope"] });
check("ids filter", r.ok && r.callouts === 0);
r = run({ action: "lock_leaders", locked: false });
check("lock_leaders action", r.ok && Lds.locked === false);

// ---- grouping: halo + text become one <id>_callout; moving the group moves both and the leader follows
let r2 = run({ action: "finalize_labels" });
check("finalize_labels groups halo + text", r2.ok && r2.grouped === 1 && r2.callouts === 1, JSON.stringify(r2));
const grp = Lb.pageItems.find(i => i.name === "bld_a_callout");
check("group holds both items, halo UNDER text (text is pageItems[0] = front)", grp && grp.pageItems.length === 2 && grp.pageItems[0].name === "bld_a_label" && grp.pageItems[1].name === "bld_a_label_halo", grp && grp.pageItems.map(i => i.name).join());
r2 = run({ action: "finalize_labels" });
check("finalize is idempotent", r2.grouped === 0 && r2.callouts === 1, JSON.stringify(r2));
run({ action: "reroute_leaders", changed_only: true, group: true }); // record state
run({ action: "lock_leaders", locked: true });
run({ action: "move_item", name: "bld_a_callout", dx: 200, dy: 50 });
const gb = grp.pageItems.map(c => (c.geometricBounds[0] + c.geometricBounds[2]) / 2);
check("one drag of the group moves text and halo together", Math.abs(gb[0] - gb[1]) < 0.01, JSON.stringify(gb));
r2 = run({ action: "reroute_leaders", changed_only: true, group: true });
const li = run({ action: "read_items", names: ["bld_a_leader"] }).items.bld_a_leader;
const tt = grp.pageItems.find(i => i.name === "bld_a_label").geometricBounds;
check("leader follows the moved group (ends beside the text, anchor unchanged)", r2.rerouted === 1 && Math.abs(li.points[0][0] - 230) < 0.01 && Math.abs(li.points[0][1] - 280) < 0.01 &&
  Math.abs(li.points[li.points.length - 1][1] - (792 - (tt[1] + tt[3]) / 2)) < 0.5, JSON.stringify([li.points, tt]));
// text frames without usable names: matched to the leader by position
T.name = ""; 
r2 = run({ action: "read_label_positions" });
check("name fallback keeps the callout findable (text nearest the leader end)", r2.labels.length === 1, JSON.stringify(r2.labels));
// callouts grouped by the old code (halo in FRONT of its text) are repaired by finalize_labels
{
  T.name = "bld_a_label";
  const g2 = new Group(Lb); g2.name = "bld_b_callout";
  const hb = new Item(Lb, "bld_b_label_halo", "TextFrame", textBox(500, 500, 40, 8)), tb2 = new Item(Lb, "bld_b_label", "TextFrame", textBox(500, 500, 40, 8));
  [hb, tb2].forEach(i => { Lb.pageItems.splice(Lb.pageItems.indexOf(i), 1); g2.pageItems.push(i); i.layer = Lb; });   // [halo, text] = halo on top (the bug)
  const rr = run({ action: "finalize_labels" });
  check("finalize_labels repairs an old callout with the halo on top", rr.ok && rr.reordered >= 1 && g2.pageItems[0].name === "bld_b_label", JSON.stringify(rr) + " " + g2.pageItems.map(i => i.name).join());
  const rr2 = run({ action: "finalize_labels" });
  check("repair is idempotent", rr2.ok && rr2.reordered === 0, JSON.stringify(rr2));
  const rp = run({ action: "reroute_leaders", changed_only: true, group: true });
  check("live reroute poll does not run the repair pass", rp.ok);
}
// order_layers: backing strictly under every label text layer, moves only when out of order
{
  Layer.prototype.move = function (ref, where) {
    const sib = this.parent.layers; sib.splice(sib.indexOf(this), 1);
    const at = sib.indexOf(ref); sib.splice(where === "PLACEAFTER" ? at + 1 : at, 0, this);
  };
  const Ls = mk("Labels - Streets", LABELS);
  LABELS.layers.splice(LABELS.layers.indexOf(Lback), 1); LABELS.layers.unshift(Lback);  // backing on top: the reported bug
  Lback.locked = true;
  const ORDER = ["Legend", "Callout Markers", "Leader Anchors", "Leaders", "Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", "Labels - Hidden", "Labels - Elevation", "Label Backing"];
  let ro = run({ action: "order_layers", groups: [ORDER] });
  const names = LABELS.layers.map(l => l.name);
  check("order_layers puts Label Backing below every label layer", ro.ok && names[names.length - 1] === "Label Backing" && names.indexOf("Labels - Streets") < names.indexOf("Label Backing"), names.join(" | ") + " " + JSON.stringify(ro));
  check("order_layers keeps the canonical order of the rest", names.indexOf("Leader Anchors") < names.indexOf("Leaders") && names.indexOf("Leaders") < names.indexOf("Labels - Streets") && names.indexOf("Labels - Streets") < names.indexOf("Labels - Buildings"), names.join(" | "));
  check("a locked layer is locked again after the move", Lback.locked === true);
  ro = run({ action: "order_layers", groups: [ORDER] });
  check("order_layers moves nothing when the order is right", ro.ok && ro.moved === 0, JSON.stringify(ro));
}
// close_docs: names required, only exact names, unsaved documents skipped unless discard:true, never saves
{
  const closedLog = [], mkDoc = (name, saved) => ({ name, saved, close(opt) { closedLog.push(name + ":" + (opt === global.SaveOptions.DONOTSAVECHANGES ? "nosave" : "?")); const i = app.documents.indexOf(this); app.documents.splice(i, 1); } });
  global.SaveOptions = { DONOTSAVECHANGES: "no" };
  const docs = [mkDoc("keep.ai", true), mkDoc("test_a.ai", true), mkDoc("test_b.ai", false), mkDoc("other.ai", true)];
  app.documents = docs; docs.getByName = undefined;
  let rc = run({ action: "close_docs", names: [] });
  check("close_docs without names is refused", rc.ok === false && /needs names/.test(rc.error || ""), JSON.stringify(rc));
  rc = run({ action: "close_docs", names: ["test_a.ai", "test_b.ai", "missing.ai"] });
  check("close_docs closes saved named docs, skips unsaved", rc.ok && rc.closed.join() === "test_a.ai" && rc.skipped.join() === "test_b.ai" && rc.open.join() === "keep.ai,test_b.ai,other.ai", JSON.stringify(rc));
  check("closed without saving", closedLog.join() === "test_a.ai:nosave", closedLog.join());
  rc = run({ action: "close_docs", names: ["test_b.ai"], discard: true });
  check("discard:true closes an unsaved doc too", rc.closed.join() === "test_b.ai" && rc.open.join() === "keep.ai,other.ai", JSON.stringify(rc));
}
console.log(fails ? fails + " FAILED" : "all host reroute checks passed");
process.exit(fails ? 1 : 0);
