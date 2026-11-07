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

global.app = { documents: { length: 1 }, activeDocument: root, version: "mock" };
root.layers.getByName = undefined;
Object.defineProperty(app.documents, "length", { value: 1 });
root.layers.getByName = function (n) { const f = this.find(l => l.name === n); if (!f) throw new Error("no layer"); return f; };
global.ElementPlacement = {}; global.PathPointSelection = { ANCHORPOINT: 1 };
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

console.log(fails ? fails + " FAILED" : "all host reroute checks passed");
process.exit(fails ? 1 : 0);
