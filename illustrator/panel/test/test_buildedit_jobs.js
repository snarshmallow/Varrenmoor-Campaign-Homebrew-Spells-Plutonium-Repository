// Buildings tab "Edit buildings" jobs (lib/buildedit.js + lib/maprefresh.js): argument builders, refusals, step order incl. the map refresh, dry run, UI wiring.
//   node illustrator/panel/test/test_buildedit_jobs.js
const fs = require("fs"), path = require("path");
const VB = require("../lib/core.js");
["styles", "objects"].forEach(f => require("../lib/" + f + ".js"));
const MR = require("../lib/maprefresh.js"), BE = require("../lib/buildedit.js");
let pass = 0, fail = 0;
const check = (n, c, x) => { if (c) pass++; else { fail++; console.log("FAIL", n, x === undefined ? "" : JSON.stringify(x)); } };
const throws = (n, f, re) => { try { f(); check(n, false, "did not throw"); } catch (e) { check(n, !re || re.test(e.message), e.message); } };
const d = { panel: "OUT", world: "W" };
const fresh = () => { const st = VB.normalize(null); st.place = "bh"; st.styles.ids = ["bld_house_041", "bld_house_044"]; st.town.autofill = true; return st; };
const labels = j => j.steps.map(s => s.label);
const pys = j => j.steps.filter(s => s.t === "py").map(s => typeof s.args === "function" ? s.args({ vars: {} }) : s.args);
const hosts = j => j.steps.filter(s => s.t === "host").map(s => s.action);

// defaults
{ const st = fresh(); check("defaults: map refresh + footprints on, dry off, no confirm", st.bedit.map === true && st.bedit.footprints === true && st.bedit.dry === false && st.bedit.confirmDelete === false); }

// DELETE
{
  const st = fresh();
  throws("delete refused without the confirm tick", () => BE.job("delete", st, d), /Yes, delete/);
  st.styles.ids = []; st.bedit.confirmDelete = true;
  throws("delete refused with nothing ticked", () => BE.job("delete", st, d), /tick a building/);
  st.styles.ids = ["bld_house_041", "bld_house_044"];
  const j = BE.job("delete", st, d), p = pys(j), L = labels(j), H = hosts(j);
  check("delete: first step is delete-building with both ids", p[0].join(" ") === "delete-building --place bh --ids bld_house_041,bld_house_044", p[0]);
  // fast path: delete_items with exactly the deleted ids, before any render; the full refresh only runs when the fast step failed
  { const calls = [], fast = j.steps.find(s => /delete_items/.test(s.label || ""));
    check("delete: fast delete_items step right after the data edit", !!fast && j.steps.indexOf(fast) < j.steps.findIndex(s => s.t === "py" && /render_world/.test(s.script)), L);
    const run = { vars: {}, log: () => {}, host: async (a) => { calls.push(a); return { ok: true, deleted: 7 }; } };
    fast.fn(run).then(() => {
      check("delete: delete_items gets the ids and the building layers incl. Building Footprints", calls[0].action === "delete_items" && calls[0].ids.join() === "bld_house_041,bld_house_044" &&
        ["Buildings", "Labels - Buildings", "Label Backing", "Leaders", "DETAILS - Lots", "Details", "Building Footprints"].every(n => calls[0].layers.indexOf(n) >= 0), calls[0]);
      check("delete: fast ok -> render / replace steps skipped", j.steps.filter(s => s.t !== "fn" && s.when).every(s => !s.when(run)) && !run.vars.fastFail);
      const run2 = { vars: {}, log: () => {}, exists: () => true, host: async () => ({ ok: false, error: "unknown action delete_items" }) };
      return fast.fn(run2).then(() => check("delete: fast failed -> full refresh runs (render + replace)", run2.vars.fastFail === true && j.steps.filter(s => s.t !== "fn").slice(1).every(s => !s.when || s.when(run2))));
    }).catch(e => check("delete fast step threw", false, e.message)); }
  check("delete: render_world (fallback) after the delete", /render_world/.test(j.steps.find(s => s.t === "py" && s.args === p[1]).script));
  const iAbs = j.steps.findIndex(s => s.t === "py" && /svg-absent/.test(JSON.stringify(typeof s.args === "function" ? s.args({ vars: { edit: { deleted: ["bld_house_041"] } } }) : s.args)));
  const iRep = j.steps.findIndex(s => s.t === "host" && s.action.action === "replace_layer");
  check("delete: svg-absent check comes before the first replace_layer", iAbs > 0 && iRep > iAbs, [iAbs, iRep]);
  const absArgs = j.steps[iAbs].args({ vars: { edit: { deleted: ["bld_house_041", "bld_house_044"] } } });
  check("delete: svg-absent gets the deleted ids from the delete result", absArgs.join(" ").indexOf("--ids bld_house_041,bld_house_044") > 0, absArgs);
  const reps = H.filter(a => a.action === "replace_layer").map(a => a.names).reduce((a, b) => a.concat(b), []);
  ["Buildings", "Walls", "Blocks", "Details", "DETAILS - Lots", "Fences", "Labels - Buildings", "Label Backing", "Leaders", "Labels - Hidden"].forEach(n => check("delete: refresh replaces " + n, reps.indexOf(n) >= 0, reps));
  check("delete: contour heights are not replaced", reps.indexOf("Labels - Elevation") < 0 && reps.indexOf("Contours - Minor") < 0);
  check("delete: footprints layer redrawn last", H.filter(a => a.action === "replace_layer").pop().names.join() === BE.LAYER);
  check("delete: building fills step present", L.some(l => /buildings fills/.test(l)), L);
  check("delete: marks contours stale", (j.setStale || []).indexOf("contours") >= 0);
  // untick runs only after a real delete
  const set = {}; const un = j.steps.find(s => s.label === "untick");
  un.fn({ vars: { edit: { deleted: ["x"] } }, setState: (k, v) => { set[k] = v; } });
  check("delete: unticks and clears the confirm after the run", Array.isArray(set["styles.ids"]) && set["styles.ids"].length === 0 && set["bedit.confirmDelete"] === false, set);
  // map off
  st.bedit.map = false; st.bedit.footprints = false;
  const j2 = BE.job("delete", st, d);
  check("delete, map off: no render, no Illustrator call", pys(j2).length === 1 && hosts(j2).length === 0, labels(j2));
  // dry
  st.bedit.map = true; st.bedit.dry = true; st.bedit.confirmDelete = false;
  const j3 = BE.job("delete", st, d);
  check("delete dry run: allowed without confirm, --dry passed, map untouched", pys(j3)[0].indexOf("--dry") > 0 && pys(j3).length === 1 && hosts(j3).length === 0, pys(j3));
}
// other ops: arguments and refusals
{
  const st = fresh();
  st.bedit.dx = 5; st.bedit.dy = -3;
  check("move dx/dy", pys(BE.job("move", st, d))[0].join(" ") === "move-building --place bh --ids bld_house_041,bld_house_044 --dx 5 --dy -3");
  st.bedit.toX = 10; st.bedit.toY = 20;
  throws("move to centre needs one building", () => BE.job("move", st, d), /exactly one/);
  st.styles.ids = ["bld_house_041"];
  check("move --to", pys(BE.job("move", st, d))[0].indexOf("--to") > 0);
  st.bedit.deg = 0; throws("rotate 0 refused", () => BE.job("rotate", st, d), /degrees/);
  st.bedit.deg = 30; check("rotate", pys(BE.job("rotate", st, d))[0].join(" ").indexOf("--deg 30") > 0);
  st.bedit.width = null; st.bedit.depth = null; st.bedit.scale = null;
  throws("resize needs a size", () => BE.job("resize", st, d), /width/);
  st.bedit.width = 3; throws("resize below 6 ft refused", () => BE.job("resize", st, d), /6\.\.400/);
  st.bedit.width = 30; check("resize width", pys(BE.job("resize", st, d))[0].join(" ").indexOf("--width 30") > 0);
  st.bedit.scale = 2; throws("resize scale and width together refused", () => BE.job("resize", st, d), /OR/);
  st.bedit.newId = "Bad Id"; throws("rename bad id refused", () => BE.job("rename", st, d), /bld_/);
  st.bedit.newId = "bld_dyers_hall"; st.bedit.newName = "Dyers Hall";
  check("rename", pys(BE.job("rename", st, d))[0].join(" ") === "rename-building --place bh --ids bld_house_041 --new-id bld_dyers_hall --name Dyers Hall");
  st.styles.ids = ["a", "b"]; throws("rename needs exactly one", () => BE.job("rename", st, d), /exactly one/);
  throws("properties need a ticked field", () => BE.job("props", st, d), /tick at least one/);
  st.bedit.propsOn.tags = true; st.bedit.props.tags = "guild, dyers"; st.bedit.propsOn.district = true; st.bedit.props.district = "";
  check("properties: tags + clear district", pys(BE.job("props", st, d))[0].join("|") === "set-building-props|--place|bh|--ids|a,b|--district||--tags|guild, dyers", pys(BE.job("props", st, d))[0]);
  st.bedit.propsOn.name = true; throws("properties: name with two ticked refused", () => BE.job("props", st, d), /one building/);
  st.styles.ids = ["a"]; st.bedit.add = { name: "", kind: "castle", cx: 1, cy: 2, width: 20, depth: 16, rotation: 0, floors: 1 };
  throws("add: unknown kind refused", () => BE.job("add", st, d), /kind/);
  st.bedit.add.kind = "shop"; st.bedit.add.cx = null; throws("add: centre needed", () => BE.job("add", st, d), /Centre/);
  st.bedit.add.cx = 100; st.bedit.add.cy = 120;
  check("add rectangle", pys(BE.job("add", st, d))[0].join(" ") === "add-building --place bh --kind shop --floors 1 --center 100,120 --width 20 --depth 16 --rotation 0");
  check("undo + map refresh, no absent check", pys(BE.job("undo", st, d))[0][0] === "restore-buildings" && !BE.job("undo", st, d).steps.some(s => /deleted ids/.test(s.label || "")));
  const fp = BE.jobFromPaths(st, d, "sync");
  check("read from Illustrator: view, closed paths of Building Footprints, apply-building-paths sync", hosts(fp)[0].action === "get_selection" && hosts(fp)[0].closed_only && hosts(fp)[0].layer === BE.LAYER &&
    pys(fp)[1].join(" ").indexOf("apply-building-paths --place bh --file OUT/building_paths.json --mode sync") === 0, pys(fp));
  const rd = BE.jobRedrawFootprints(st, d);
  check("redraw footprints replaces only that layer", hosts(rd).filter(a => a.action === "replace_layer").every(a => a.names.join() === BE.LAYER));
  check("select in Illustrator uses focus_items", hosts(BE.jobSelectInIllustrator(st))[0].action === "focus_items");
}
// filter
{
  const rows = [{ id: "bld_house_1", name: "Mill House", kind: "house", district: "d1", style: "", floors: 1, tags: ["x"] }, { id: "bld_shop_1", name: "Shop", kind: "shop", district: "", style: "tudor", floors: 2, tags: [] }];
  const f = Object.assign(BE.defaults(), {});
  check("filter: all", BE.filterRows(rows, f).length === 2);
  check("filter: text on name", BE.filterRows(rows, Object.assign({}, f, { filter: "mill" })).length === 1);
  check("filter: kind / (none) district / style / floors", BE.filterRows(rows, Object.assign({}, f, { fkind: "shop" }))[0].id === "bld_shop_1" &&
    BE.filterRows(rows, Object.assign({}, f, { fdist: "(none)" }))[0].id === "bld_shop_1" && BE.filterRows(rows, Object.assign({}, f, { fstyle: "(legacy)" }))[0].id === "bld_house_1" &&
    BE.filterRows(rows, Object.assign({}, f, { ffloors: 2 })).length === 1);
}
// static wiring
{
  const P = path.join(__dirname, ".."), html = fs.readFileSync(P + "/index.html", "utf8"), ui = fs.readFileSync(P + "/buildedit_ui.js", "utf8");
  const order = ["lib/objects.js", "objects_ui.js", "lib/maprefresh.js", "lib/buildedit.js", "buildedit_ui.js", "main.js"].map(f => html.indexOf('"' + f + '"'));
  check("loader: maprefresh, buildedit, buildedit_ui after objects_ui and before main.js", order.every((x, i) => x > 0 && (i === 0 || x > order[i - 1])), order);
  check("libs publish on window even with module (CEP)", /root\.VBMapRefresh = api/.test(fs.readFileSync(P + "/lib/maprefresh.js", "utf8")) && /root\.VBBuildEdit = api/.test(fs.readFileSync(P + "/lib/buildedit.js", "utf8")));
  check("main.js inits and paints VBBuildEditUI", /VBBuildEditUI\.init\(/.test(fs.readFileSync(P + "/main.js", "utf8")) && /VBBuildEditUI\.paint\(\)/.test(fs.readFileSync(P + "/main.js", "utf8")));
  check("no window.confirm / alert / prompt", !/\b(confirm|alert|prompt)\s*\(/.test(ui.split("\n").filter(l => !/^\s*\/\//.test(l)).join("\n").replace(/confirmDelete/g, "")));
  ["be_del", "be_undo", "be_add", "be_move", "be_rotate", "be_resize", "be_dup", "be_rename", "be_props", "be_door", "be_read_all", "be_add_sel", "be_reshape_sel", "be_redraw_fp", "be_select_ai", "be_tick_sel", "be_map"].forEach(a =>
    check("button " + a + " exists and has an action", ui.indexOf('data-act="' + a + '"') > 0 && new RegExp("\\b" + a + ":").test(ui)));
  check("delete confirm tick box present", ui.indexOf('data-s="bedit.confirmDelete"') > 0);
  check("map refresh tick box present", ui.indexOf('data-s="bedit.map"') > 0 && /Update the map layers too/.test(ui));
}
setTimeout(() => { console.log(pass + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0); }, 50);
