// Roads (3D) group: split job carries the road grading arguments.   node illustrator/panel/test/test_roads_jobs.js
const path = require("path");
const VB = require("../lib/core.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const d = VB.dirs(ROOT, place), st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const args = s => { const j = VB.jobWorldSplit(s, d); return j.steps[0].args || j.steps[0].argv || JSON.stringify(j.steps[0]); };
let a = args(st); const t = Array.isArray(a) ? a.join(" ") : a;
check("defaults present", st.roads && st.roads.smooth === 0.5 && st.roads.max_grade === 14 && st.roads.skirt === true && st.roads.cutfill === false, JSON.stringify(st.roads));
check("smooth + grade passed", /--road-smooth/.test(t) && /--road-max-grade/.test(t), t);
check("skirt on, cutfill off by default", !/--no-road-skirt/.test(t) && !/--road-cutfill/.test(t), t);
st.roads = { smooth: 9, max_grade: 0, skirt: false, cutfill: true };
a = args(st); const u = Array.isArray(a) ? a.join(" ") : a;
check("clamped and toggles", /--road-smooth,?\s*1\b/.test(u) && /--road-max-grade,?\s*14\b/.test(u) && /--no-road-skirt/.test(u) && /--road-cutfill/.test(u), u);
console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
