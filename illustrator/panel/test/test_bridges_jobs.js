// Bridges tab jobs: argument building and the detect / auto-fix / apply / remove / preview jobs against a stubbed python (no world files are touched).
//   node illustrator/panel/test/test_bridges_jobs.js
const fs = require("fs"), path = require("path"), os = require("os");
const VB = require("../lib/core.js"); require("../lib/bridges.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbbr-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world/" + place, panel: tmp + "/panel" });
fs.mkdirSync(d.world, { recursive: true }); fs.mkdirSync(d.panel, { recursive: true });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, calls = [];
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const CROSS = { id: "brg_str_014_1", type: "gully", road: "str_014", s0_ft: 0, s1_ft: 98.8, span_ft: 98.8, deck_above_ground_ft: 13.4, road_class: "street" };
const reply = args => {
  const sub = args.filter(a => /^(detect|apply|remove|inject|entity)$/.test(a))[0];
  if (sub === "detect") return { ok: true, crossings: [CROSS] };
  if (sub === "apply") {
    fs.writeFileSync(d.world + "/bridges.json", JSON.stringify({ place, bridges: [{ id: CROSS.id, road: "str_014", preset: args.includes("--preset") ? args[args.indexOf("--preset") + 1] : "stone_arch", crossing: "gully", span: { length_ft: 98.8, width_ft: 24 }, locked: args.includes("--only"), provenance: {} }], removed: [] }));
    return { ok: true, bridges: 1, roads_with_gaps: ["str_014"], found: 1, new: [CROSS.id], report: [CROSS] };
  }
  if (sub === "remove") { const j = JSON.parse(fs.readFileSync(d.world + "/bridges.json")); j.removed = [CROSS.id]; fs.writeFileSync(d.world + "/bridges.json", JSON.stringify(j)); return { ok: true }; }
  if (sub === "inject") return { ok: true, bridges: 0 };
  if (sub === "entity") return { ok: true, png: tmp + "/panel/bridges_preview/preview_entity_threeq.png", tris: 1234, clearance_violations: 0, notes: [] };
  return { ok: true };
};
const spawn = (py, args) => {
  calls.push(args.slice());
  const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
  setTimeout(() => { c.stdout.emit("data", JSON.stringify(reply(args)) + "\n"); c.emit("close", 0); }, 5);
  return c;
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async a => { calls.push(["host", a.action, (a.names || []).join(",")]); return { ok: true }; }, log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
const last = () => calls[calls.length - 1].join(" ");
(async () => {
  check("state carries bridge defaults", st.bridges && st.bridges.float_ft === 4 && st.bridges.level_ft === 3 && st.bridges.selected === "");
  let r = await runner.run(VB.jobBridgesDetect(st, d));
  check("detect job ok", r.ok, r.error);
  check("detect args: place, pack, thresholds", /detect --place bridgehollow__dyers_walk_local --pack .*\/export --float-ft 4 --level-ft 3/.test(last()), last());
  check("crossings stored", st.bridges.crossings.length === 1 && st.bridges.crossings[0].id === "brg_str_014_1");
  r = await runner.run(VB.jobBridgesAutoFix(st, d));
  check("auto-fix job ok", r.ok, r.error);
  check("auto-fix runs apply for the whole place", /apply --place .* --pack .*\/export --float-ft/.test(last()) && last().indexOf("--only") < 0, last());
  check("items read back from bridges.json", st.bridges.items.length === 1 && st.bridges.items[0].preset === "stone_arch" && st.bridges.last.made[0] === "brg_str_014_1");
  r = await runner.run(VB.jobBridgesApply(st, d));
  check("apply without a selection fails cleanly", !r.ok && /select a crossing/.test(r.error || ""), r.error);
  st.bridges.selected = "brg_str_014_1"; st.bridges.preset = "brick_arch"; st.bridges.width_ft = 20; st.bridges.clearance_h_ft = 10; st.bridges.n_arches = 3; st.bridges.seed = 5;
  r = await runner.run(VB.jobBridgesApply(st, d));
  const a = last();
  check("apply selected: only, preset, seed, overrides", r.ok && /--only brg_str_014_1 --preset brick_arch --seed 5 --set width_ft=20 --set clearance_h_ft=10 --set n_arches=3/.test(a), a);
  check("hand-tuned bridge is flagged locked", st.bridges.items[0].locked === true);
  r = await runner.run(VB.jobBridgesPreview(st, d));
  check("preview: entity command with the same overrides", r.ok && /bridge_preview\.py/.test(calls[calls.length - 1].join(" ") + calls[calls.length - 1][0]) || /entity --place .* --id brg_str_014_1 .* --preset brick_arch --set width_ft=20/.test(last()), last());
  check("preview png stored", /preview_entity_threeq\.png\?/.test(st.bridges.preview_png), st.bridges.preview_png);
  r = await runner.run(VB.jobBridgesFocus(st));
  check("focus asks Illustrator for the symbol and the road", r.ok && last() === "host focus_items brg_str_014_1_outline,str_014", last());
  r = await runner.run(VB.jobBridgesRemove(st, d));
  check("remove removes then re-injects", r.ok && calls.some(c => c.includes("remove")) && /inject --place/.test(last()), last());
  check("removed bridge leaves the list and the selection", st.bridges.items.length === 0 && st.bridges.selected === "");
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
