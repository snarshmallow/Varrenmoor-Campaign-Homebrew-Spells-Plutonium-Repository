// Streetlamps tab: defaults, config, jobs (plan/apply/push/scene), readout + budget warning, kelvin colour (same as streetlamps.py), road override fields.
//   node illustrator/panel/test/test_streetlamps_jobs.js
const path = require("path"), fs = require("fs"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/lighting.js"); require("../lib/objects.js"); require("../lib/streetlamps.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, "bridgehollow"), { world: "/w/bridgehollow", panel: "/w/panel" });
const st = VB.normalize(null); st.place = "bridgehollow";
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const s = st.streetlamps;
check("defaults: off, 60 ft alternating, all classes, shadows off", s && s.enabled === false && s.spacing_ft === 60 && s.side === "alternating" && s.classes.main && s.classes.side && s.classes.dirt && s.light.shadows === false && s.light.flicker === true);
check("older state gets the block", !!VB.normalize({ lighting: {} }).streetlamps);
let c = VB.streetlampsConfig(st);
check("config classes list + numbers", JSON.stringify(c.classes) === '["main","side","dirt"]' && c.spacing_ft === 60 && c.light.kelvin === 0);
s.classes.side = false; s.spacing_ft = "45"; s.light.color = "bad"; s.light.kelvin = 2700;
c = VB.streetlampsConfig(st);
check("config follows controls, bad colour dropped", JSON.stringify(c.classes) === '["main","dirt"]' && c.spacing_ft === 45 && c.light.color === "" && c.light.kelvin === 2700);
const plan = VB.jobStreetlampsPlan(st, d), pa = plan.steps[1].args;
check("plan job writes the config then runs plan with pack + config", plan.steps[0].t === "write" && /streetlamps_cfg\.json$/.test(plan.steps[0].path) && JSON.stringify(typeof pa === "function" ? pa() : pa).includes('"plan"'), JSON.stringify(pa));
s.extra = "/x/opt/placements.json\n\n/x/opt/placements.json";
check("targets: export + extra, de-duplicated", JSON.stringify(VB.streetlampsTargets(st, d)) === JSON.stringify([d.world + "/export/placements.json", "/x/opt/placements.json"]));
const ap = VB.jobStreetlampsApply(st, d); const aa = ap.steps[1].args; const al = typeof aa === "function" ? aa() : aa;
check("apply passes every placements file", al.filter(a => a === "--placements").length === 2 && al[0] === "apply");
check("apply label says removal when off", /remove/.test(ap.label) && /generate/i.test((s.enabled = true, VB.jobStreetlampsApply(st, d).label)));
let err = ""; try { VB.jobStreetlampsPush(st, d); } catch (e) { err = e.message; }
check("push needs a scene", /pick an existing scene/.test(err));
st.foundry.target = "existing"; st.foundry.sceneUuid = "Scene.abc";
const push = VB.jobStreetlampsPush(st, d), pa2 = push.steps[0].args, pl = typeof pa2 === "function" ? pa2() : pa2;
check("push = streetlamps layer then lights (with the light budget)", pl.includes("--layers") && pl[pl.indexOf("--layers") + 1] === "streetlamps" && push.steps.length === 2 && JSON.stringify(push.steps[1].args).includes("push-lights"));
check("scene on / off / lights args", VB.streetlampsSceneArgs(st, d, "on", false).join(" ") === "set-streetlamps --scene-uuid Scene.abc --on"
  && VB.streetlampsSceneArgs(st, d, "off", true).join(" ") === "set-streetlamps --scene-uuid Scene.abc --off --apply" && /--light-config .*streetlamps_cfg\.json$/.test(VB.streetlampsSceneArgs(st, d, "lights", false).join(" ")));
// readout
check("readout before a count", /Not counted yet/.test(VB.streetlampsReadout(st)));
s.last = { at: "2026-11-09T00:00:00", lamps: 90, lights: 90, roads: 6, by_class: { main: 80, dirt: 10 }, skipped: { junction: 8 }, other: { hearth: 19, window: 53 }, tris: 5000 };
let r = VB.streetlampsReadout(st);
check("readout counts lamps + pack lights and the budget", /90 lamps on 6 road/.test(r) && /162 \(90 lamps \+ 72/.test(r) && /global/.test(r), r);
st.lighting.f3d.mode = "lights";
check("warns above 150 visible lights", /WARNING: 162 visible lights/.test(VB.streetlampsReadout(st)));
s.last.lights = 10; check("small count: no warning", !/WARNING/.test(VB.streetlampsReadout(st)));
check("config carries centre_short", VB.streetlampsConfig(st).centre_short === false && (s.centre_short = true, VB.streetlampsConfig(st).centre_short === true));
s.last.empty_roads = ["str_014 on (too short: 0 lamps), 98.8 ft"];
check("readout lists on-but-empty roads", /Roads switched on but with no lamp: str_014 on \(too short: 0 lamps\)/.test(VB.streetlampsReadout(st)));
s.light.shadows = true; check("shadow warning", /light shadows on/.test(VB.streetlampsReadout(st)));
// kelvin: same value as python
const py = cp.spawnSync("python", ["-c", "import sys;sys.path.insert(0,'" + ROOT + "/illustrator/generators');import streetlamps as s;print(s.kelvin_to_hex(1800),s.kelvin_to_hex(2700),s.kelvin_to_hex(6500))"], { encoding: "utf-8" });
check("kelvin matches python", py.stdout.trim() === [1800, 2700, 6500].map(VB.kelvinToHex).join(" "), py.stdout + py.stderr);
// per-road override fields
const keys = VB.OBJ_ROAD_FIELDS.map(f => f[0]);
check("road editor has lamp fields", ["lamps.on", "lamps.style", "lamps.spacing_ft"].every(k => keys.includes(k)) && !!st.objects.r["lamps.on"]);
st.objects.rids = ["str_008"]; st.objects.r["lamps.on"].on = true; st.objects.r["lamps.on"].v = "false"; st.objects.r["lamps.style"].on = true; st.objects.r["lamps.style"].v = "torch_post";
const ra = VB.objectsRoadArgs(st).join(" ");
check("road edit args set lamps.*", /--set lamps\.on=false/.test(ra) && /--set lamps\.style=torch_post/.test(ra), ra);
console.log("\n" + ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
