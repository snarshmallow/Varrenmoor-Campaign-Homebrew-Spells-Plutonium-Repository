// Foliage tab jobs against the real python generators and a mock Illustrator host (no Illustrator, nothing under world/ is written:
// VB_FOLIAGE_JSON points foliage.py at a scratch file).   node illustrator/panel/test/test_foliage_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/lighting.js"); require("../lib/foliage.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbfol-")), tmp = TMP.split(path.sep).join("/");
process.env.VB_FOLIAGE_JSON = tmp + "/foliage.json";
const d = Object.assign({}, VB.dirs(ROOT, place), { panel: tmp + "/panel" });
fs.mkdirSync(d.panel, { recursive: true });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, hostLog = [], selection = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const host = async a => { hostLog.push(a); if (a.action === "get_selection") return selection || { ok: false, error: "nothing selected" }; if (a.action === "replace_layer" && !fs.existsSync(a.path)) return { ok: false, error: "no file " + a.path }; return { ok: true, replaced: a.names, items: 1 }; };
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn: cp.spawn, host, log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
const run = async job => { hostLog = []; return runner.run(job); };
(async () => {
  check("state carries foliage defaults", st.foliage && st.foliage.mix.length > 0 && st.foliage.merge.chunk_ft === 150);
  check("params: ids, optional numbers", (function () { var p = VB.foliageParams(st); return p.zone === "z1" && p.elev_min_ft === null && p.mix.length === 5 && p.density_per_ha === 200; })());
  VB.foliageApplyMergePreset(st, "performance");
  check("merge preset applies", st.foliage.merge.budget === 150000 && st.foliage.merge.compress === "quant");
  check("merge args", VB.foliageMergeArgs(st).join(" ").indexOf("--budget 150000") >= 0 && VB.foliageMergeArgs(st).join(" ").indexOf("--impostor-beyond-ft 600") >= 0);
  VB.foliageApplyMergePreset(st, "balanced");
  // scatter in the whole place
  st.foliage.target = "place"; st.foliage.density_per_ha = 600; st.foliage.zone = "T1";
  let r = await run(VB.jobFoliageScatter(st, d));
  check("scatter job ok", r.ok, r.error);
  check("zone id normalised and stats stored", st.foliage.stats && st.foliage.stats.items > 20 && st.foliage.stats.zones.t1 === st.foliage.stats.items, JSON.stringify(st.foliage.stats));
  check("2D layer replaced", hostLog.some(h => h.action === "replace_layer" && h.names[0] === VB.FOLIAGE_LAYER), JSON.stringify(hostLog.map(h => h.action)));
  const svg = fs.readFileSync(d.panel + "/foliage/foliage.svg", "utf8");
  check("svg carries entity ids", svg.indexOf("fol_x5F_t1_x5F_0001") >= 0 && svg.indexOf("DETAILS - Foliage") >= 0);
  const doc = JSON.parse(fs.readFileSync(tmp + "/foliage.json", "utf8"));
  check("foliage.json written (scratch)", doc.format === "varrenmoor-foliage" && doc.items.length === st.foliage.stats.items && doc.items[0].src === "generated");
  // lasso polygon + single add + clear
  st.foliage.target = "lasso"; st.foliage.polygon = [[150, 150], [260, 150], [260, 260], [150, 260]]; st.foliage.zone = "t2"; st.foliage.density_per_ha = 800;
  r = await run(VB.jobFoliageScatter(st, d));
  check("lasso scatter ok", r.ok, r.error);
  const view = JSON.parse(cp.execFileSync("python", ["-X", "utf8", `${ROOT}/illustrator/generators/panelio.py`, "view", "--place", place].concat(VB.panelioViewFlags(st)), { encoding: "utf8" }));
  const artboard = [0, 792, 1224, 0], p = VB.ftToDoc(view, artboard, [100, 100]);
  selection = { ok: true, source: "selection", artboard, paths: [{ name: "pt", closed: false, points: [{ a: p, l: p.slice(), r: p.slice() }] }] };
  st.foliage.single_species = "oak";
  r = await run(VB.jobFoliageAdd(st, d));
  check("add at selection ok", r.ok, r.error);
  const doc2 = JSON.parse(fs.readFileSync(tmp + "/foliage.json", "utf8")), hand = doc2.items.filter(i => i.src === "hand");
  check("hand-placed oak near 100,100", hand.length === 1 && hand[0].species === "oak" && Math.abs(hand[0].x - 100) < 0.5 && Math.abs(hand[0].y - 100) < 0.5 && hand[0].id === "fol_hand_0001", JSON.stringify(hand));
  st.foliage.polygon = [[140, 140], [270, 140], [270, 270], [140, 270]];
  const before = doc2.items.length;
  r = await run(VB.jobFoliageClear(st, d));
  const doc3 = JSON.parse(fs.readFileSync(tmp + "/foliage.json", "utf8"));
  check("clear removes generated in the area", r.ok && doc3.items.length < before && doc3.items.every(i => !(i.zone === "t2")), r.error);
  // merge into a scratch folder (pack frame from the real dyers pack, nothing written under world/)
  st.foliage.merge.out_dir = tmp + "/merged"; st.foliage.merge.chunk_ft = 120;
  r = await run(VB.jobFoliageMerge(st, d, {}));
  check("merge job ok", r.ok, r.error);
  const rep = st.foliage.merge.report;
  check("report: draw calls fall to chunk count", rep && rep.after.draw_calls < rep.before.draw_calls / 3 && rep.after.triangles === rep.before.triangles, JSON.stringify(rep));
  const pl = JSON.parse(fs.readFileSync(tmp + "/merged/placements.json", "utf8"));
  check("placements ready for push-models", pl.files.length === rep.after.files && pl.files.every(f => f.layer === "foliage" && fs.existsSync(tmp + "/merged/" + f.file)));
  r = await run(VB.jobFoliageMerge(st, d, { publish: true, dry: true }));
  check("publish without scene uuid is refused", !r.ok && /scene uuid/.test(r.error), r.error);
  r = await run(VB.jobFoliagePreview(st, d));
  check("preview png written", r.ok && fs.existsSync(d.panel + "/foliage_preview.png"), r.error);
  r = await run(VB.jobFoliageStats(st, d));
  check("stats job ok", r.ok && st.foliage.stats.items > 0, r.error);
  st.foliage.target = "district"; st.foliage.district = "";
  r = await run(VB.jobFoliageScatter(st, d));
  check("district target without a pick fails visibly", !r.ok && /district/.test(r.error), r.error);
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
