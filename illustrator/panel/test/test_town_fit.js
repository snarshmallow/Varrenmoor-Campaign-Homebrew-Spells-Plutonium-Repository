// Town tab: Fit page job (panelio fit -> view_settings preset scale/grid/focus) and area_scale in the area params. No Illustrator needed.
//   node illustrator/panel/test/test_town_fit.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/townarea.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbfit-")), worldCopy = (TMP + "/world").split(path.sep).join("/");
fs.mkdirSync(worldCopy, { recursive: true });
["view_settings.json", "town_params.json"].forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/${f}`, `${worldCopy}/${f}`));
const d = Object.assign({}, VB.dirs(ROOT, place), { world: worldCopy });
const st = VB.normalize(null); VB.viewToState(JSON.parse(fs.readFileSync(`${worldCopy}/view_settings.json`, "utf8")), st.scale);
VB.townFromParams(JSON.parse(fs.readFileSync(`${worldCopy}/town_params.json`, "utf8")), st.town);
let ok = 0, fail = 0; const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, host: async () => ({ ok: true }), log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  check("defaults carry area_scale and fit", st.town.aa.area_scale === 1 && st.town.fit === "buildings");
  st.town.aa.area_scale = 2.5; check("area_scale reaches the area params", VB.areaParams(st.town).area_scale === 2.5);
  st.scale.preset = "town"; st.town.fit = "buildings"; st.town.fit_margin_ft = 40;
  const r = await runner.run(VB.jobTownFit(st, d));
  check("fit job ok", r.ok, r.error);
  const vs = JSON.parse(fs.readFileSync(`${worldCopy}/view_settings.json`, "utf8")), pr = vs.presets.town;
  check("preset focus written", Array.isArray(pr.focus) && pr.focus.length === 2 && pr.focus[0] > 500 && pr.focus[0] < 2000, JSON.stringify(pr.focus));
  check("preset scale is a nice number and state follows", pr.scale_ft_per_in > 0 && st.scale.scale_ft_per_in === pr.scale_ft_per_in, JSON.stringify([pr.scale_ft_per_in, st.scale.scale_ft_per_in]));
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
