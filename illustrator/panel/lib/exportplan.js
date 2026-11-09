// Export planner: pure function that turns the panel state + a few facts about the machine/place into the ORDERED list of export steps
// (check -> export pack -> validate -> split -> merge -> audit scene -> push -> collision/sight flags), each with a default check mark, a
// "writes Foundry" marker, a refusal reason when it cannot run, and a lazy job builder over the existing VBCore job functions.
// The order is the verified pipeline order (PLUGIN_GUIDE sections 4 and 16): push-scene-3d / push-models reset padding and skybox, so on an existing
// scene the one-shot push-scene-3d does models, padding, skybox, lights in that order; a NEW scene gets push-models only (padding/skybox follow once
// it exists). No DOM, no fs. UI: export_ui.js. Published on window even when Node's module exists (CEP).
(function (root) {
  "use strict";
  var X = {};
  X.HEAVY_BUILDINGS = 400;      // split/merge on a place with more buildings than this: RAM warning
  X.ROOF_PER_BUILDING_MAX = 150; // recommendRoofMode: up to this many buildings one hideable roof tile each, above it one roof tile per scene

  // the roof mode the docs recommend by size (per_building adds one tile per building, per_scene adds one tile in total)
  X.recommendRoofMode = function (buildingCount) { return +buildingCount > X.ROOF_PER_BUILDING_MAX ? "per_scene" : "per_building"; };

  var ORDER = ["check", "export", "validate", "split", "merge", "audit", "push", "collision"];
  X.STEP_IDS = ORDER.slice();
  X.DEFAULT_SEL = { check: true, export: true, validate: true, split: true, merge: true, audit: true, push: true, collision: true };
  X.defaultSel = function () { var o = {}; ORDER.forEach(function (k) { o[k] = X.DEFAULT_SEL[k]; }); return o; };

  function existing(st) { var f = st.foundry || {}; return f.target === "existing"; }
  function targetProblem(st) {
    var f = st.foundry || {};
    if (existing(st)) return f.sceneUuid ? "" : "pick an existing scene on this tab (Refresh from Foundry first)";
    return String(f.sceneName || "").trim() ? "" : "type a name for the new scene";
  }

  // facts: { hasTerrain, hasBuildings, buildingCount, packExists, splitExists, connected (true|false|null = not checked), sceneName }
  // opts: { dry (bool, default true), armed (bool: user ticked "I understand this writes to Foundry") }
  X.plan = function (VB, st, d, facts, opts) {
    facts = facts || {}; opts = opts || {};
    var dry = opts.dry !== false, armed = !!opts.armed, sel = Object.assign(X.defaultSel(), (st.exp && st.exp.sel) || {});
    var m = (st.foundry && st.foundry.models) || {}, tp = targetProblem(st), ex = existing(st), heavy = (+facts.buildingCount || 0) >= X.HEAVY_BUILDINGS;
    var packPlanned = function () { return !!facts.packExists || (sel.export && !!facts.hasTerrain); };
    var steps = [];
    function add(s) {
      s.checked = !!sel[s.id]; if (s.needs) { s.reason = s.needs() || ""; } else s.reason = ""; s.enabled = !s.reason;
      s.dryOnly = !!(s.write && dry);
      steps.push(s);
    }
    add({ id: "check", label: "Check terrain (read-only)", group: "local", write: false, heavy: false, note: "Contour and slope sanity check on the place's terrain. Reads only.",
      needs: function () { return facts.hasTerrain ? "" : "this place has no terrain yet (Terrain tab: Generate base terrain)"; },
      build: function () { return VB.jobToolsTerrainCheck(st); } });
    add({ id: "export", label: "Export world pack (3D)", group: "local", write: false, heavy: false,
      note: "Writes world/" + st.place + "/export (roof mode " + VB.roofMode(st) + ", interior " + VB.interiorStyle(st) + "). Local files only.",
      needs: function () { return facts.hasTerrain ? "" : "this place has no terrain yet (Terrain tab: Generate base terrain)"; },
      build: function () { return VB.jobWorldPack(st, d); } });
    add({ id: "validate", label: "Validate the pack (read-only)", group: "local", write: false, heavy: false, note: "worldpack.py validate on the export folder.",
      needs: function () { return packPlanned() ? "" : "no world pack yet: tick Export world pack"; },
      build: function () { return VB.jobToolsPackValidate(st, d); } });
    add({ id: "split", label: "Export split models", group: "local", write: false, heavy: true,
      note: "Writes the glb models (roads " + ((st.roads || {}).smooth) + " smoothing, " + ((st.roads || {}).max_grade) + " deg max grade). Slow and memory hungry on big places." + (heavy ? " This place has about " + facts.buildingCount + " buildings: close other heavy apps." : ""),
      needs: function () { return packPlanned() ? "" : "no world pack yet: tick Export world pack"; },
      build: function () { return VB.jobWorldSplit(st, d); } });
    add({ id: "merge", label: "Merge / compress (" + (m.preset || "layer") + ")", group: "local", write: false, heavy: true,
      note: "Merges the split models (" + (m.preset || "layer") + ", compression " + (m.compress || "none") + "). Keep compression none while you use doors." + (m.preset === "individual" ? " Preset is keep individual: nothing to merge." : ""),
      needs: function () { return (facts.splitExists || sel.split) ? (m.preset === "individual" ? "preset is keep individual (nothing to merge)" : "") : "no split models yet: tick Export split models"; },
      build: function () { return VB.jobWorldMerge(st, d); } });
    add({ id: "audit", label: "Audit scene tiles (read-only)", group: "foundry-read", write: false, heavy: false,
      note: "Looks for duplicate or stale pipeline tiles on the existing scene (reads Foundry, changes nothing).",
      needs: function () { return !ex ? "only for an existing scene" : tp || (facts.connected === false ? "no connection to the bridge relay" : ""); },
      build: function () { return VB.jobSceneAudit(st, d); } });
    var pushLabel = ex ? "Push 3D scene (models, padding, skybox, lights)" : "Push models (new scene)";
    add({ id: "push", label: pushLabel, group: "foundry", write: true, heavy: false,
      note: ex ? "push-scene-3d on the picked scene: models, then padding, skybox, interior lights, collision, in the order that survives the reset." +
                 (facts.lights && !facts.lights.total ? " The current pack has no lights: if it still has none after the export, the push runs without lights (the scene's lights are kept)." : "")
               : "push-models creates the scene " + JSON.stringify(String((st.foundry || {}).sceneName || "")) + ". Padding, skybox and lights follow once it exists (Refresh from Foundry, pick it, Existing, run again).",
      needs: function () {
        if (tp) return tp;
        if (facts.connected === false) return "no connection to the bridge relay (Foundry tab: Connect, then Check connection)";
        if (!packPlanned()) return "no world pack yet";
        if (!dry && !armed) return "tick \"I understand this writes to Foundry\" to push for real";
        return "";
      },
      build: function () { return ex ? VB.jobToolsScene3d(st, d, dry) : VB.jobWorldPush(st, d, { dry: dry }); } });
    add({ id: "collision", label: "Collision and sight flags on the scene tiles", group: "foundry", write: true, heavy: false,
      note: "set-collision with the Collision/sight table (sight is not part of push-scene-3d). Existing scene only; idempotent.",
      needs: function () {
        if (!ex) return "only for an existing scene (a new scene gets the flags from Push models)";
        if (tp) return tp;
        if (facts.connected === false) return "no connection to the bridge relay";
        if (!dry && !armed) return "tick \"I understand this writes to Foundry\" to write for real";
        return "";
      },
      build: function () { return VB.jobSetCollision(st, !dry); } });
    return { steps: steps, dry: dry, armed: armed, place: st.place, existing: ex, heavy: heavy, warnings: X.warnings(VB, st, facts, dry) };
  };

  // ------------------------------------------------------------------ PUSH group: one item per thing that is pushed to Foundry (all reuse existing jobs)
  // Order = the verified order (section 4): models first (they reset padding and sky), then padding, sky, scene flags, lights, collision, doors, foliage.
  var PUSH_ORDER = ["scene2d", "tiles2d", "models", "l_terrain", "l_buildings", "l_roofs", "l_roads", "l_bridges", "l_walls", "l_fences", "l_props", "l_water", "l_foliage", "l_streetlamps", "l_signs",
    "walls", "padding", "skybox", "sun", "lighting", "lights", "lights_interior", "lights_lamps", "streetlamps", "collision", "doors", "foliage", "m_click", "m_roofs", "m_door", "m_sign"];
  X.PUSH_IDS = PUSH_ORDER.slice();
  // what "Push everything" ticks (scene 2D, overlay tiles, the walls fallback (it REMOVES walls when switched off), per-layer and per-light-type subsets and the one-time macro installs are separate on purpose)
  X.PUSH_EVERYTHING = ["models", "padding", "skybox", "sun", "lighting", "lights", "collision", "doors", "foliage"];
  X.pushDefaultSel = function () { var o = {}; PUSH_ORDER.forEach(function (k) { o[k] = X.PUSH_EVERYTHING.indexOf(k) >= 0; }); return o; };
  X.PUSH_LAYERS = { l_terrain: "terrain", l_buildings: "buildings", l_roofs: "roofs", l_roads: "roads", l_bridges: "bridges", l_walls: "walls", l_fences: "fences", l_props: "props", l_water: "water", l_foliage: "foliage", l_streetlamps: "streetlamps", l_signs: "signs" };

  // ------------------------------------------------------------------ lights / streetlamps precheck (what the pack placements.json carries) and soft skips
  // counts of a placements doc: interior light hints sit on file entries (worldpack_split), lamp lights + the streetlamps tile on the doc (streetlamps.py apply)
  X.packLightCounts = function (doc) {
    var c = { total: 0, hearth: 0, window: 0, lamp: 0, other: 0, lampTiles: 0, lamps: 0 };
    if (!doc || typeof doc !== "object") return null;
    function one(l) { var t = (l && l.type) || "other"; c.total++; if (t === "hearth" || t === "window" || t === "lamp") c[t]++; else c.other++; }
    (doc.lights || []).forEach(one);
    (doc.files || []).forEach(function (e) { (e.lights || []).forEach(one); if (e.layer === "streetlamps") c.lampTiles++; });
    c.lamps = +((doc.streetlamps || {}).lamps) || 0;
    return c;
  };
  var lcCache = { p: "", m: 0, c: null };
  // cheap cached read (re-parsed only when the file's mtime changes); null when there is no pack
  X.readPackLights = function (fs, p) {
    try {
      var m = fs.statSync(p).mtimeMs; if (lcCache.p === p && lcCache.m === m) return lcCache.c;
      lcCache = { p: p, m: m, c: X.packLightCounts(JSON.parse(fs.readFileSync(p, "utf8"))) }; return lcCache.c;
    } catch (e) { return null; }
  };
  X.NO_LIGHTS = "No lights in this pack: re-export first (Export world pack + Export split models: buildings get doors, windows, interiors and their hearth/window lights; check the interior style). The scene's existing lights are kept.";
  X.NO_INTERIOR = "No interior lights (hearth, window) in this pack: re-export first (Export world pack + Export split models). The scene's existing lights are kept.";
  X.NO_LAMPS = "No streetlamps in this pack: switch Streetlamps on and press Generate (Streetlamps tab) first, then push. A fresh export also removes them: Generate again after each export. The scene's lamp lights are kept.";
  // precheck per lights item: { line: what the pack has, reason: "" or why it cannot run }
  X.lightsPrecheck = function (id, c) {
    if (!c) return { line: "", reason: "" };
    var line = "Pack: " + c.total + " light(s) (" + c.hearth + " hearth, " + c.window + " window, " + c.lamp + " lamp" + (c.other ? ", " + c.other + " other" : "") + ")" + (id === "streetlamps" ? ", " + c.lampTiles + " lamp tile(s)" : "") + ".";
    var r = "";
    if (id === "lights" && !c.total) r = X.NO_LIGHTS;
    else if (id === "lights_interior" && !(c.hearth + c.window)) r = X.NO_INTERIOR;
    else if ((id === "lights_lamps" && !c.lamp) || (id === "streetlamps" && !c.lamp && !c.lampTiles)) r = X.NO_LAMPS;
    return { line: line, reason: r };
  };
  X.LIGHT_STEPS = ["lights", "lights_interior", "lights_lamps", "streetlamps"];
  // a lights step that failed only because the plan had 0 lights is SKIPPED, not failed: -> the plain reason, else ""
  X.softSkip = function (id, res) {
    if (!res || res.ok || X.LIGHT_STEPS.indexOf(id) < 0) return "";
    if (!/the plan has 0 lights/.test(String(res.error || ""))) return "";
    return "skipped: " + (id === "streetlamps" || id === "lights_lamps" ? X.NO_LAMPS : id === "lights_interior" ? X.NO_INTERIOR : X.NO_LIGHTS);
  };
  // push-scene-3d --with-lights refuses (before any write) when the pack has 0 lights: rerun once without lights instead of stopping the run
  X.retryWithoutLights = function (id, res) { return id === "push" && !!res && !res.ok && /--with-lights: the plan has 0 lights/.test(String(res.error || "")); };
  X.dropLights = function (job) {
    job.steps.forEach(function (s) { if (Array.isArray(s.args)) s.args = s.args.filter(function (a) { return a !== "--with-lights" && a !== "--prune-lights"; }); });
    job.label += " (lights skipped: the pack has none)"; return job;
  };
  // the same check for the Streetlamps tab's Push layer + lights button
  X.streetlampsPushCheck = function (c) { var p = X.lightsPrecheck("streetlamps", c); return { line: p.line, reason: p.reason, offerApply: !!p.reason }; };

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  // one shared target: padding, skybox and foliage keep their own scene uuid fields, so a copy of the state carries the Foundry tab's scene into all of them
  X.scopedState = function (st, layers) {
    var c = clone(st), u = (st.foundry || {}).sceneUuid || "";
    if ((st.foundry || {}).target === "existing" && u) { c.padding.scene_uuid = u; c.skybox.scene_uuid = u; if (c.foliage && c.foliage.merge) c.foliage.merge.scene_uuid = u; }
    if (layers) c.foundry.models.layers = layers;
    return c;
  };
  function dryify(job) { job.steps.forEach(function (s) { if (Array.isArray(s.args) && s.args.indexOf("--dry-run") < 0) s.args.push("--dry-run"); }); job.label += " (dry run)"; return job; }
  function lightsJob(VB, st, d, dry, types) { var j = VB.jobPushLights(st, d, dry); if (types) { j.steps[0].args.push("--layers", types); j.label += " [" + types + "]"; } return j; }

  X.pushPlan = function (VB, st, d, facts, opts) {
    facts = facts || {}; opts = opts || {};
    var dry = opts.dry !== false, armed = !!opts.armed, sel = Object.assign(X.pushDefaultSel(), (st.exp && st.exp.psel) || {}), ex = existing(st), tp = targetProblem(st), steps = [];
    function reasonCommon(needsExisting, needsPack, noDry, noTarget) {
      if (noDry && dry) return "no dry run exists for this step: it runs only in a real push";
      if (!noTarget) {
        if (needsExisting && !ex) return "needs an existing scene (a new scene is created by Models; then Refresh from Foundry and pick it)";
        if (tp) return tp;
      }
      if (facts.connected === false) return "no connection to the bridge relay (Foundry tab: Connect, then Check connection)";
      if (needsPack && !facts.packExists) return "no world pack yet (run the export steps above)";
      if (!dry && !armed) return "tick \"I understand this writes to Foundry\" to push for real";
      return "";
    }
    function add(id, label, o) {
      var s = { id: id, label: label, group: "push", write: true, heavy: false, note: o.note || "", checked: !!sel[id], dryOnly: dry && !o.noDry, noDry: !!o.noDry };
      s.reason = reasonCommon(!!o.existing, !!o.pack, !!o.noDry, !!o.noTarget);
      if (X.LIGHT_STEPS.indexOf(id) >= 0 && facts.packExists) {   // precheck: count the pack's lights before running; 0 = disabled with the plain reason
        var pc = X.lightsPrecheck(id, facts.lights);
        s.precheck = pc.line; if (pc.line) s.note = pc.line + " " + s.note;
        if (pc.reason) { s.reason = pc.reason; s.noLights = true; s.offerApply = pc.reason === X.NO_LAMPS; }
      }
      s.enabled = !s.reason;
      s.build = o.build; steps.push(s);
    }
    var sc = function (layers) { return X.scopedState(st, layers); };
    add("scene2d", "Scene 2D: flat map background, grid, walls", { note: "Push scene: exports the view picture and writes a FLAT 2D scene (background, calibrated grid, walls). Dry run = Plan (writes nothing). Asks its own in-panel confirm.", build: function () { return { act: dry ? "f_plan_scene" : "f_push_scene", label: "Scene 2D" + (dry ? " (plan)" : "") }; } });
    add("tiles2d", "Label overlay tiles (2D)", { note: "Push tiles: the scene plus a transparent overlay tile of the Foundry tab's tile layers.", build: function () { return { act: dry ? "f_plan_scene" : "f_push_tiles", label: "Overlay tiles" + (dry ? " (plan)" : "") }; } });
    add("models", "Models / tiles: all layers (push-models, 3D scene flags)", { pack: true, note: "One 3D Canvas tile per model; creates the scene when the target is New. Resets padding and sky: run those after.", build: function () { return VB.jobWorldPush(sc(), d, { dry: dry }); } });
    Object.keys(X.PUSH_LAYERS).forEach(function (id) {
      var layer = X.PUSH_LAYERS[id];
      add(id, "Models / tiles: " + layer + " only", { pack: true, note: "push-models --layers " + layer + " (a layer-limited push deletes nothing).", build: function () { return VB.jobWorldPush(sc(layer), d, { dry: dry }); } });
    });
    add("walls", "Foundry walls (fallback)", { existing: true, pack: true, note: ((st.foundry.models || {}).alsoWalls ? "Writes building and town-wall door walls." : "Walls fallback is OFF: this REMOVES the pipeline's walls from the scene.") + " push-walls.", build: function () { return VB.jobPushWalls(sc(), !dry); } });
    add("padding", "Padding apron (table, heightmap, apron)", { existing: true, note: "push-padding with the Padding tab settings. Run after models.", build: function () { return VB.jobPaddingPush(sc(), d, { dry: dry }); } });
    add("skybox", "Skybox", { existing: true, note: "Applies the Skybox tab's sky to the scene (regenerate it first if it has no image). Run after models.", build: function () { return VB.jobSkyApply(sc(), { dry: dry }); } });
    add("sun", "Sun, shadows and fog flags (set-sun)", { existing: true, note: "Lighting tab sun/fog block: scene flags only.", build: function () { return VB.jobSetSun(sc(), d, !dry, false); } });
    add("lighting", "3D lighting and light budget flags (set-lighting)", { existing: true, pack: true, note: "Lighting tab 3D lighting block.", build: function () { return VB.jobSetLighting(sc(), d, !dry); } });
    add("lights", "Lights: all pipeline lights (push-lights)", { existing: true, pack: true, note: "Interior, window, hearth and lamp lights of the pack (upsert by flag).", build: function () { return lightsJob(VB, sc(), d, dry, ""); } });
    add("lights_interior", "Lights: interior only (hearth, window)", { existing: true, pack: true, note: "push-lights --layers hearth,window: type-scoped, other light types are kept.", build: function () { return lightsJob(VB, sc(), d, dry, "hearth,window"); } });
    add("lights_lamps", "Lights: street lamps only (lamp)", { existing: true, pack: true, note: "push-lights --layers lamp: type-scoped, other light types are kept.", build: function () { return lightsJob(VB, sc(), d, dry, "lamp"); } });
    add("streetlamps", "Streetlamps: lamp tile layer + lamp lights", { existing: true, pack: true, note: "Same as the Streetlamps tab Push layer + lights (Generate there after each fresh export).", build: function () { var j = VB.jobStreetlampsPush(sc(), d); return dry ? dryify(j) : j; } });
    add("collision", "Collision and sight flags", { existing: true, note: "set-collision with the Collision/sight table.", build: function () { return VB.jobSetCollision(sc(), !dry); } });
    add("doors", "Door sync (wall doors follow model doors)", { existing: true, note: "sync-doors.", build: function () { return VB.jobSyncDoors(sc(), !dry); } });
    add("foliage", "Foliage / scatter: publish merged foliage", { existing: true, note: "Foliage tab Publish to Foundry (merge the foliage there first).", build: function () { return VB.jobFoliageMerge(sc(), d, { publish: true, dry: dry }); } });
    add("m_click", "Install Click mode macro (roofs, doors)", { noDry: true, noTarget: true, note: "Creates or refreshes the macro in the Foundry world.", build: function () { return VB.jobClickMacros(); } });
    add("m_roofs", "Install roof macros", { noDry: true, noTarget: true, note: "Roofs: toggle all / selected.", build: function () { return VB.jobRoofMacros(); } });
    add("m_door", "Install Door sync macro", { noDry: true, noTarget: true, note: "Creates or updates the macro in the Foundry world.", build: function () { return VB.jobInstallDoorSync(); } });
    add("m_sign", "Install Sign maker macro", { noDry: true, noTarget: true, note: "Creates or updates the macro in the Foundry world.", build: function () { return VB.jobInstallSignMaker(); } });
    steps.sort(function (a, b) { return PUSH_ORDER.indexOf(a.id) - PUSH_ORDER.indexOf(b.id); });
    return { steps: steps, dry: dry, armed: armed, place: st.place, existing: ex, group: "push", warnings: [] };
  };

  // push-models batch-copy numbers (copy_seconds, files_copied, files_skipped, bytes) found anywhere in a job's JSON output; "" when absent
  X.copySummary = function (out) {
    var j = null, t = String(out || "").trim(), lines = t.split(/\r?\n/), i;
    try { j = JSON.parse(t); } catch (e) { for (i = lines.length - 1; i >= 0 && !j; i--) { if (lines[i].charAt(0) === "{") { try { j = JSON.parse(lines[i]); } catch (e2) { /* next */ } } } }
    function find(o, depth) { if (!o || typeof o !== "object" || depth > 4) return null; if ("files_copied" in o || "copy_seconds" in o) return o; var k, r; for (k in o) { r = find(o[k], depth + 1); if (r) return r; } return null; }
    var c = find(j, 0); if (!c) return "";
    var mb = c.bytes != null ? (c.bytes / 1048576).toFixed(1) + " MB" : "";
    return "copied " + (c.files_copied != null ? c.files_copied : "?") + " file(s)" + (c.files_skipped != null ? ", " + c.files_skipped + " unchanged" : "") + (mb ? ", " + mb : "") + (c.copy_seconds != null ? " in " + c.copy_seconds + " s" : "");
  };

  X.warnings = function (VB, st, facts, dry) {
    var w = [], m = (st.foundry && st.foundry.models) || {};
    if (m.compress === "quant") w.push("Compression is quantized: doors and Click mode may not work on quantized models.");
    if (m.prune && !dry) w.push("Prune is on: pipeline model tiles that are not in this push will be DELETED from the scene (only tiles the pipeline made).");
    if (facts.buildingCount && VB.roofMode(st) === "per_building" && facts.buildingCount > X.ROOF_PER_BUILDING_MAX) w.push("Roof mode per building adds one tile per building (" + facts.buildingCount + "): consider Per scene (recommended above " + X.ROOF_PER_BUILDING_MAX + ").");
    if (facts.buildingCount >= X.HEAVY_BUILDINGS) w.push("Big place (" + facts.buildingCount + " buildings): split and merge need a lot of RAM and minutes; this PC may stall. Running them on Vega is a manual choice, never automatic.");
    if (facts.connected === null && !dry) w.push("The bridge connection has not been checked: press Check connection first.");
    var LM = (typeof window !== "undefined" && window.VBLimits) || null;   // size and performance check (lib/limits.js): warn/danger lines only
    if (facts.limits && LM) LM.notes(facts.limits).forEach(function (x) { w.push(x); });
    if ((st.foundry || {}).target === "new" && !dry) w.push("New scene: padding, skybox and lights are not part of this push. Run again with Existing scene after Refresh from Foundry.");
    return w;
  };

  // ids to run, in pipeline order: selected + enabled steps from `fromId` on (resume). Disabled selected steps are reported, not run.
  X.runList = function (plan, fromId) {
    var started = !fromId, run = [], skipped = [];
    plan.steps.forEach(function (s) {
      if (!started && s.id === fromId) started = true;
      if (!started || !s.checked) return;
      if (s.enabled) run.push(s.id); else skipped.push({ id: s.id, reason: s.reason });
    });
    return { run: run, skipped: skipped };
  };
  X.step = function (plan, id) { for (var i = 0; i < plan.steps.length; i++) if (plan.steps[i].id === id) return plan.steps[i]; return null; };

  // what the buttons do ("shortcuts"): selections for the pack-only run
  X.PACK_ONLY = ["check", "export", "validate"];

  // "What will happen" text
  X.preview = function (VB, st, plan, facts, fromId) {
    var rl = X.runList(plan, fromId), L = [], local = [], reads = [], writes = [];
    rl.run.forEach(function (id) { var s = X.step(plan, id); (s.write ? writes : s.group === "foundry-read" ? reads : local).push(s); });
    L.push("Place: " + st.place + "   Mode: " + (plan.dry ? "DRY RUN (no Foundry writes)" : "REAL (Foundry will be changed)"));
    var f = st.foundry || {}, row = VB.deleteSceneRow ? VB.deleteSceneRow(st) : null;
    L.push("Target: " + (plan.existing ? "existing scene " + (row ? (row.name || "(unnamed)") + " [" + row.uuid + "]" : "(none picked)") : "new scene " + JSON.stringify(String(f.sceneName || "")) + " (created on push)"));
    L.push("");
    L.push("On this PC (local files, no Foundry change):");
    local.forEach(function (s) { L.push("  - " + s.label + (s.heavy ? "  [heavy]" : "")); }); if (!local.length) L.push("  (nothing)");
    if (reads.length) { L.push("Reads Foundry (no change):"); reads.forEach(function (s) { L.push("  - " + s.label); }); }
    L.push(plan.dry ? "Foundry writes (dry run: previewed only, nothing is written):" : "FOUNDRY WRITES (real):");
    writes.forEach(function (s) { L.push("  - " + s.label); }); if (!writes.length) L.push("  (none)");
    if (rl.skipped.length) { L.push(""); L.push("Selected but cannot run:"); rl.skipped.forEach(function (x) { var s = X.step(plan, x.id); L.push("  - " + s.label + ": " + x.reason); }); }
    if (plan.warnings.length) { L.push(""); plan.warnings.forEach(function (w) { L.push("Note: " + w); }); }
    return L.join("\n");
  };

  // state: st.exp = { sel: the full checklist selection, dry: true, last: { stepId: { status, at, error } }, resume: stepId|"" }
  X.stateDefaults = function () { return { sel: X.defaultSel(), psel: X.pushDefaultSel(), dry: true, last: {}, resume: "" }; };
  X.record = function (st, id, status, error) {
    st.exp = st.exp || X.stateDefaults(); st.exp.last = st.exp.last || {}; st.exp.last[id] = { status: status, at: new Date().toISOString(), error: error || "" };
  };

  if (typeof module !== "undefined" && module.exports) module.exports = X;
  if (typeof window !== "undefined") window.VBExportPlan = X;   // always, even when Node's module exists (CEP)
  // extend the state defaults once (loaded after core.js)
  var VBc = (typeof window !== "undefined" && window.VBCore) || (typeof module !== "undefined" && module.exports && (function () { try { return require("./core.js"); } catch (e) { return null; } })());
  if (VBc && VBc.defaults && !VBc.defaults.exportplan) {
    var baseD = VBc.defaults;
    VBc.defaults = function () { var o = baseD(); o.exp = X.stateDefaults(); return o; };
    VBc.defaults.exportplan = true;
  }
})(typeof self !== "undefined" ? self : this);
