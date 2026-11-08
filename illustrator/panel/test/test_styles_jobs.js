// Buildings tab: assign / clear / auto / selection jobs against a temp COPY of a place (never touches world/). No Illustrator needed (mock host).
//   node illustrator/panel/test/test_styles_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/styles.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbsty-")), wr = (TMP + "/world").split(path.sep).join("/");
fs.mkdirSync(`${wr}/${place}/buildings`, { recursive: true });
fs.readdirSync(`${ROOT}/world/${place}/buildings`).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/buildings/${f}`, `${wr}/${place}/buildings/${f}`));
fs.copyFileSync(`${ROOT}/world/${place}/districts.json`, `${wr}/${place}/districts.json`);
process.env.VB_WORLD_ROOT = wr;
const readB = id => JSON.parse(fs.readFileSync(`${wr}/${place}/buildings/${id}.json`, "utf8"));
const d = VB.dirs(ROOT, place), st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0; const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
let mockSel = null;
const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, host: async a => (a.action === "get_selection" ? mockSel : { ok: true }), log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  check("defaults carry styles", st.styles && st.styles.target === "selected");
  check("check rejects empty selection", /no buildings chosen/.test(VB.stylesCheck(st) || ""));
  let r = await runner.run(VB.jobStylesAssign(st, d, "tudor"));
  check("empty selection job fails cleanly", !r.ok && /no buildings chosen/.test(r.error), r.error);
  st.styles.ids = ["bld_house_041", "bld_house_044"]; st.styles.style = "falu_cottage";
  r = await runner.run(VB.jobStylesAssign(st, d));
  check("assign selected ok", r.ok, r.error);
  check("styles written", readB("bld_house_041").style === "falu_cottage" && readB("bld_house_044").style === "falu_cottage");
  check("only the selected changed", readB("bld_house_052").style === "tudor", readB("bld_house_052").style);
  check("state remembers last", st.styles.last && st.styles.last.count === 2);
  st.styles.target = "kind"; st.styles.kind = "house"; r = await runner.run(VB.jobStylesAssign(st, d, "auto"));
  check("auto by kind ok", r.ok && readB("bld_house_041").style === "auto" && readB("bld_house_109").style === "auto", r.error);
  r = await runner.run(VB.jobStylesAssign(st, d, "none"));
  check("clear removes the key", r.ok && !("style" in readB("bld_house_041")), r.error);
  st.styles.target = "all"; r = await runner.run(VB.jobStylesAssign(st, d, "hanseatic_brick"));
  check("all buildings", r.ok && readB("bld_house_109").style === "hanseatic_brick");
  r = await runner.run(VB.jobStylesAssign(st, d, "no_such_style"));
  check("unknown style rejected", !r.ok && /unknown style/.test(r.error), r.error);
  mockSel = { ok: true, source: "selection", artboard: [0, 792, 1224, 0], paths: [{ name: "bld_x5F_house_x5F_052_x5F_lot", closed: true, points: [] }, { name: "bld_house_063", closed: true, points: [] }, { name: "road_1", closed: true, points: [] }] };
  r = await runner.run(VB.jobStylesFromSelection(st, ["bld_house_052", "bld_house_063", "bld_house_041"]));
  check("selection -> ids", r.ok && st.styles.ids.join() === "bld_house_052,bld_house_063" && st.styles.target === "selected", JSON.stringify(st.styles.ids));
  mockSel = { ok: true, paths: [{ name: "road_1" }] };
  r = await runner.run(VB.jobStylesFromSelection(st, ["bld_house_052"]));
  check("selection without building names fails", !r.ok && /named like a building/.test(r.error), r.error);
  const real = JSON.parse(fs.readFileSync(`${ROOT}/world/${place}/buildings/bld_house_041.json`, "utf8"));
  check("the real world was not touched", real.style === "tudor");
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
