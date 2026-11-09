// Draw-grid option: scale.grid_show state/normalize, view_settings.json round trip, the Scale Apply job (writes grid_show, still replaces the Grid layer so
// an existing grid is emptied), Places import-image flags, Foundry --hide-grid (separate option), static panel wiring. Python is not run.
//   node illustrator/panel/test/test_grid_jobs.js
const fs = require("fs"), path = require("path");
const VB = require("../lib/core.js"); require("../lib/places.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, "bridgehollow"), { world: "W", panel: "P" });
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };

const st = VB.normalize(null); st.place = "bridgehollow";
check("default: grid drawn (existing places unchanged)", st.scale.grid_show === true);
const raw0 = { page_in: [17, 11], units: "ft", presets: { town: { scale_ft_per_in: 100, grid_ft: 100, grid_major_every: 5 } } };
check("view_settings without grid_show reads as shown", VB.viewToState(raw0, VB.normalize(null).scale).grid_show === true);
check("applyViewSettings writes grid_show true by default", VB.applyViewSettings(raw0, st.scale).grid_show === true);
st.scale.grid_show = false;
const out = VB.applyViewSettings(raw0, st.scale);
check("applyViewSettings writes grid_show false", out.grid_show === false && out.presets.town.grid_ft === 100);
check("grid_show false round-trips through viewToState", VB.viewToState(out, VB.normalize(null).scale).grid_show === false);
check("view flags unchanged (other tools take no --no-grid)", !VB.viewFlags(st).includes("--no-grid"));

// Scale Apply job: first step writes view_settings, the guides replace still names Grid
const job = VB.jobScaleApply(st, d, false);
let written = null;
const fn = job.steps.find(s => s.t === "fn");
fn.fn({ readJson: () => JSON.parse(JSON.stringify(raw0)), writeJson: (p, v) => { written = { p, v }; } });
check("Apply job writes world/view_settings.json with grid_show false", written && /view_settings\.json$/.test(written.p) && written.v.grid_show === false);
const rep = job.steps.find(s => s.action === "replace_layer" || (s.args && s.args.action === "replace_layer") || (s.host && s.host.action === "replace_layer") || JSON.stringify(s).includes('"replace_layer"'));
check("Apply job still replaces the Grid layer (an empty Grid layer clears the old grid)", rep && JSON.stringify(rep).includes('"Grid"'), JSON.stringify(rep));
const py = job.steps.find(s => JSON.stringify(s).includes("render_world.py"));
check("Apply job runs render_world with the usual view flags", py && JSON.stringify(py).includes("--grid-major"));

// Places: base-map import
const stp = VB.normalize(null); stp.place = "bridgehollow";
const argsOf = (img) => {
  stp.places.image = Object.assign({ path: "C:/m/a.png", name: "ZZ Base", id: "", ft_per_px: "5", rotate: "", grid_ft: "", no_grid: false }, img);
  const j = VB.jobImportImage(stp, true), s = j.steps.find(x => x.args || x.t === "py") || j.steps[1];
  const a = typeof s.args === "function" ? s.args() : s.args; return a;
};
let a = argsOf({});
check("import default: no grid flag (CLI default 100 ft guide grid, as before)", !a.includes("--no-grid") && !a.includes("--grid-ft"), a.join(" "));
a = argsOf({ no_grid: true });
check("import 'No guide grid' sends --no-grid", a.includes("--no-grid") && !a.includes("--grid-ft"), a.join(" "));
a = argsOf({ grid_ft: "0" });
check("import guide grid 0 means no grid", a.includes("--no-grid") && !a.includes("--grid-ft"), a.join(" "));
a = argsOf({ grid_ft: "50" });
check("import guide grid 50 still passes --grid-ft", a.includes("--grid-ft") && a.includes("50") && !a.includes("--no-grid"), a.join(" "));

// Foundry: separate explicit option
const sf = VB.normalize(null); sf.foundry.sceneName = "Z";
check("Foundry hide-grid default off: no flag", sf.foundry.hideGrid === false && !VB.foundryPushSceneArgs(sf, { image: "x.png" }).includes("--hide-grid"));
sf.scale.grid_show = false;
check("Draw grid off does NOT hide the Foundry grid", !VB.foundryPushSceneArgs(sf, { image: "x.png" }).includes("--hide-grid"));
sf.foundry.hideGrid = true;
check("Foundry hide-grid on sends --hide-grid", VB.foundryPushSceneArgs(sf, { image: "x.png" }).includes("--hide-grid"));

// static wiring
const ih = fs.readFileSync(path.join(__dirname, "../index.html"), "utf8");
check("Scale block has the Draw grid checkbox", /data-s="scale\.grid_show"[^>]*>\s*Draw grid \(off = no grid at all\)/.test(ih));
check("Foundry tab has a separate Hide Foundry grid checkbox", /data-s="foundry\.hideGrid"/.test(ih));
check("Places image form has a no-grid checkbox", /data-s="places\.image\.no_grid"/.test(ih));
console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
