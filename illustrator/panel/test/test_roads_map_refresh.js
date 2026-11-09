// Roads tab: a road change must also redraw the road-dependent map layers (user report: "deleting ticked roads and redrawing them doesn't remove them from the
// map in Illustrator"; before, only the helper layer Road Centerlines was redrawn). Job steps (order, layers, lock handling, options) and a real run on a temp
// COPY of a small place with a mock Illustrator: after Delete the rendered SVG holds the deleted road id in no layer, and Undo brings every file back.
//   node illustrator/panel/test/test_roads_map_refresh.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/styles.js"); require("../lib/objects.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local", GONE = "str_020";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbroadmap-")).split(path.sep).join("/"), wr = TMP + "/world", wd = `${wr}/${place}`;
fs.mkdirSync(`${wd}/buildings`, { recursive: true });
fs.readdirSync(`${ROOT}/world/${place}`).filter(f => /\.json$/.test(f)).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/${f}`, `${wd}/${f}`));
fs.readdirSync(`${ROOT}/world/${place}/buildings`).forEach(f => fs.copyFileSync(`${ROOT}/world/${place}/buildings/${f}`, `${wd}/buildings/${f}`));
process.env.VB_WORLD_ROOT = wr;
let ok = 0, fail = 0; const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const st = VB.normalize(null); st.place = place;
const d = Object.assign({}, VB.dirs(ROOT, place), { panel: TMP + "/panel", world: wd });
const hostCalls = [];
const runner = R.createRunner({ root: ROOT, jobsDir: TMP + "/jobs", fs, path, spawn: cp.spawn, host: async a => { hostCalls.push(a); return { ok: true, replaced: a.names || [], items: 0 }; }, log: () => {},
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: (s, c) => { s.forEach(k => { st.stale[k] = true; }); } });
const hostSteps = j => j.steps.filter(s => s.t === "host").map(s => s.action);
const replaced = j => hostSteps(j).filter(a => a.action === "replace_layer").map(a => a.names.join("+"));
const idx = (j, re) => j.steps.findIndex(s => re.test(s.label || "") || (s.t === "py" && re.test(s.script)) || (s.t === "host" && re.test(JSON.stringify(s.action))));
const svgIdsWith = (file, id) => { const t = fs.readFileSync(file, "utf8").replace(/_x5F_/g, "_"); return (t.match(new RegExp('id="[^"]*' + id + '[^"]*"', "g")) || []); };
(async () => {
  // ---- defaults and step structure
  const nr = st.objects.nr;
  check("defaults: map refresh, labels and fills on", nr.map === true && nr.mapLabels === true && nr.mapFills === true);
  st.objects.rids = [GONE]; nr.confirmDelete = true;
  let j = VB.jobRoadsDelete(st, d);
  const rep = replaced(j);
  check("delete: edit first, then render_world, then Roads+Blocks first", idx(j, /delete-road/) === 0 && idx(j, /render_world/) > 0 && rep[0] === "Roads+Blocks", rep.join(" | "));
  check("delete: Details+Bounds, Road Centerlines, labels replaced", rep.includes("Details+Bounds") && rep.includes("Road Centerlines") && rep.some(r => /Labels - Streets/.test(r) && /Label Backing/.test(r) && /Leaders/.test(r)), rep.join(" | "));
  check("labels keep the contour heights (no contours in this render)", !rep.some(r => /Labels - Elevation|Contours/.test(r)), rep.join(" | "));
  check("order: render < Roads < centrelines < labels < fills", idx(j, /render_world/) < idx(j, /"names":\["Roads","Blocks"\]/) && idx(j, /"names":\["Roads","Blocks"\]/) < idx(j, /draw-roads/) &&
    idx(j, /draw-roads/) < idx(j, /Labels - Streets/) && idx(j, /Labels - Streets/) < idx(j, /fills_raster/), j.steps.map(s => s.label).join(" / "));
  const ra = hostSteps(j).filter(a => a.action === "replace_layer");
  check("locked layers: replace_layer restores each lock (only the GUIDES parent is opened around Bounds)", ra.filter(a => a.names[0] !== "Details").every(a => a.restore_lock === true) &&
    (() => { const s = j.steps, i = s.findIndex(x => x.t === "host" && x.action.action === "replace_layer" && x.action.names.includes("Bounds"));
      return s[i - 1].action.action === "lock_layers" && s[i - 1].action.locked === false && s[i + 1].action.action === "lock_layers" && s[i + 1].action.locked === true && s[i].when && s[i - 1].when && s[i + 1].when; })());
  check("every Illustrator step of the refresh is optional (a failure warns, the rest still runs)", j.steps.slice(idx(j, /render_world/)).filter(s => s.t === "host").every(s => s.optional));
  check("labels grouped + layer order + leaders lock after the label replace", hostSteps(j).some(a => a.action === "finalize_labels") && hostSteps(j).some(a => a.action === "order_layers") && hostSteps(j).some(a => a.action === "lock_leaders"));
  check("contours marked stale", (j.setStale || []).includes("contours"));
  check("status tags count the map steps", j.steps.some(s => /^map 1\/6: render/.test(s.label)) && j.steps.some(s => /^map 6\/6: road fills/.test(s.label)), j.steps.map(s => s.label).join(" / "));
  const rwArgs = j.steps[idx(j, /render_world/)].args.join(" ");
  check("render_world gets view + label + source flags, no contours", /--view /.test(rwArgs) && /--label-style-b64/.test(rwArgs) && /--terrain-source/.test(rwArgs) && !/--contours/.test(rwArgs), rwArgs);
  // full fills with flat copies: every category (the flat copies layer is cleared as a whole); flat off: streets raster only
  check("fills: textured + flat copies = full fills_raster", !/--only/.test(j.steps[idx(j, /fills_raster/)].args.join(" ")));
  st.town.fills.flat = false;
  check("fills: textured without flat copies = --only streets", /--only streets/.test(VB.jobRoadsDelete(st, d).steps.find(s => /fills_raster/.test(s.script || "")).args.join(" ")));
  st.town.fills.flat = true; st.town.fills.full = false;
  check("fills: flat swatches when the textured map is off", !VB.jobRoadsDelete(st, d).steps.some(s => /fills_raster/.test(s.script || "")) && VB.jobRoadsDelete(st, d).steps.some(s => s.label === "map 6/6: road fills (fills)"));
  st.town.fills.full = true;
  nr.mapLabels = false; nr.mapFills = false;
  j = VB.jobRoadsDelete(st, d);
  check("labels / fills off: Roads, Blocks, Details, centrelines only", replaced(j).join(" | ") === "Roads+Blocks | Details+Bounds | Road Centerlines" && !j.steps.some(s => /fills_raster/.test(s.script || "")), replaced(j).join(" | "));
  nr.mapLabels = true; nr.mapFills = true; nr.map = false;
  j = VB.jobRoadsDelete(st, d);
  check("map off: only the edit, plus a note", !j.steps.some(s => /render_world/.test(s.script || "")) && j.steps.some(s => s.label === "note") && !(j.setStale || []).length);
  j = VB.jobRoadsRedraw(st, d);
  check("map off: Redraw roads in Illustrator = centrelines only", replaced(j).join() === "Road Centerlines");
  check("Redraw roads on the map ignores the checkbox", replaced(VB.jobRoadsMap(st, d))[0] === "Roads+Blocks");
  nr.map = true;
  check("Redraw roads in Illustrator = full refresh when on", replaced(VB.jobRoadsRedraw(st, d))[0] === "Roads+Blocks");
  check("no place folders: no refresh (old callers)", !VB.jobRoadsDelete(st).steps.some(s => /render_world/.test(s.script || "")));
  // every road-changing job carries it
  st.objects.rids = ["str_008"]; nr.simplify = 1;
  check("simplify / smooth refreshes", replaced(VB.jobRoadsShape(st, d))[0] === "Roads+Blocks");
  check("split refreshes", replaced(VB.jobRoadsSplit(st, d))[0] === "Roads+Blocks");
  st.objects.rids = ["str_008", "str_014"];
  check("join refreshes", replaced(VB.jobRoadsJoin(st, d))[0] === "Roads+Blocks");
  check("undo refreshes", replaced(VB.jobRoadsUndo(st, d))[0] === "Roads+Blocks");
  ["add", "reshape", "sync"].forEach(m => check("from paths (" + m + ") refreshes", replaced(VB.jobRoadsFromPaths(st, d, m))[0] === "Roads+Blocks"));
  st.objects.rids = ["str_008"]; Object.assign(st.objects.r.width_ft, { on: true, v: 20 });
  check("width edit refreshes", replaced(VB.jobObjectsEditRoads(st, d))[0] === "Roads+Blocks");
  st.objects.r.width_ft.on = false; Object.assign(st.objects.r.kerb, { on: true, v: "true" });
  check("3D-only edit does not", !replaced(VB.jobObjectsEditRoads(st, d)).length);
  st.objects.r.kerb.on = false;
  // ---- real run (python, mock Illustrator), labels on, fills off to stay quick
  const orig = {}; ["streets.json", "details.json", "markers.json"].forEach(f => { orig[f] = fs.readFileSync(`${wd}/${f}`, "utf8"); });
  st.objects.rids = [GONE]; nr.confirmDelete = true; nr.mapFills = false;
  let r = await runner.run(VB.jobRoadsDelete(st, d));
  check("delete + map refresh runs", r.ok, r.error);
  const svg = d.panel + "/roads_map.svg";
  check("rendered map has no layer item for the deleted road", fs.existsSync(svg) && svgIdsWith(svg, GONE).length === 0, fs.existsSync(svg) ? svgIdsWith(svg, GONE).join(",") : "no svg");
  check("centreline svg has no deleted road", svgIdsWith(d.panel + "/road_centerlines.svg", GONE).length === 0);
  check("other roads still drawn", svgIdsWith(svg, "str_016").length > 0);
  check("kerbs + off-map marker of the road removed from details / markers", !fs.readFileSync(`${wd}/details.json`, "utf8").includes('"' + GONE + '"') && !fs.readFileSync(`${wd}/markers.json`, "utf8").includes('"' + GONE + '"'));
  const reps = hostCalls.filter(a => a.action === "replace_layer").map(a => a.names.join("+"));
  check("Illustrator got Roads+Blocks, Details+Bounds, centrelines, labels", reps[0] === "Roads+Blocks" && reps.includes("Details+Bounds") && reps.includes("Road Centerlines") && reps.some(x => /Labels - Streets/.test(x)), reps.join(" | "));
  check("replace paths point at the rendered svgs", hostCalls.filter(a => a.action === "replace_layer").every(a => /roads_map\.svg$|road_centerlines\.svg$/.test(a.path)));
  check("stale contours flagged", st.stale.contours === true);
  hostCalls.length = 0;
  r = await runner.run(VB.jobRoadsUndo(st, d));
  check("undo restores streets, details and markers byte for byte", r.ok && Object.keys(orig).every(f => fs.readFileSync(`${wd}/${f}`, "utf8") === orig[f]), r.error);
  check("undo redraws the map: the road is back", svgIdsWith(svg, GONE).length > 0 && hostCalls.some(a => a.action === "replace_layer" && a.names[0] === "Roads"));
  const real = JSON.parse(fs.readFileSync(`${ROOT}/world/${place}/streets.json`, "utf8")).streets;
  check("real world untouched", real.some(s => s.id === GONE));
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
