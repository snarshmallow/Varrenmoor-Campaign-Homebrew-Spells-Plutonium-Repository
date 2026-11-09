// Places additions to VBCore (loaded after core.js): the Places tab (list places, new-place wizard from a form / template / plain words / pasted spec, size caps,
// draft quality, import a Foundry scene as a place). Pure logic, no DOM: also loaded by test/test_places_jobs.js.
// Python side: generators/place_create.py (create / validate / from-text / templates), place_render.py, foundry_push.py import-scene (foundry_import.py).
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  var GEN = "illustrator/generators/";
  var py = VB.steps.py;
  var LIM = { max_buildings: 1200, max_area_ft2: 3000000, max_place_ft: 9000 };   // mirror of place_create.LIMITS_DEFAULT (the python side is the authority)

  VB.placesDefaults = function () {
    return {
      tab: "list", template: "", from_text: "", spec_text: "", draft: true, allow_large: false, render_after: true, open_after: false,
      form: { name: "", id: "", culture: "fantasy_generic", population: 600, layout: "organic", recipe: "rolling", sea_side: "south", rivers: 1, lakes: 0, river_meander: "gentle",
        climate: "temperate", season: "summer", central_feature: "market", wall: false, seed: "", width_ft: "", height_ft: "", relief_ft: "", settlement: "auto" },
      blank: { name: "", id: "", width_ft: 1000, height_ft: 800, recipe: "flat", relief_ft: "", cell_ft: "", seed: "", scale_ft_per_in: "", grid_ft: "", underlay: "", force: false },
      manage: { name: "", notes: "", kind: "", status: "", culture: "", season: "", units: "", focus_x: "", focus_y: "", scale_ft_per_in: "", grid_ft: "",
        new_id: "", include_export: false, dup_id: "", dup_name: "", dup_include_export: false, restore_as: "", trash_entry: "", purge_confirm: "", loaded_for: "" },
      trash: [],
      import: { scene_uuid: "", place_id: "", walls: true, lights: false, tokens: false, notes: false, closed_as: "lines", dry_run: false },
      image: { path: "", name: "", id: "", ft_per_px: "", rotate: "", grid_ft: "", no_grid: false },
      last: null, notes: [], estimate: null
    };
  };
  VB.TINY_POP = 20;   // mirror of place_create.TINY_POP: below this town_tiny.py makes a farmstead / cabin / lodge / inn / hamlet; 0 = terrain only
  VB.placePop = function (v) { var n = Number(v); return String(v).trim() === "" || !isFinite(n) ? 600 : Math.max(0, Math.min(12000, Math.round(n))); };
  VB.PLACE_ID_RE = /^[a-z0-9][a-z0-9_]{1,40}$/;   // mirror of place_manage.ID_RE / the place spec id pattern
  VB.PLACE_RESERVED = ["schema", "export", "trash", "world", "panel", "places", "con", "nul", "aux", "prn"];
  VB.placeIdProblem = function (id, existing) {
    id = String(id || "");
    if (!VB.PLACE_ID_RE.test(id)) return "id must be 2-41 characters: lower-case letters, digits and underscore, starting with a letter or digit";
    if (VB.PLACE_RESERVED.indexOf(id) >= 0 || /^(com|lpt)[1-9]$/.test(id)) return "id " + id + " is reserved";
    if (existing && existing.indexOf(id) >= 0) return "world/" + id + " already exists";
    return "";
  };
  VB.PLACE_SLUG = function (s) { return String(s || "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 40); };

  // form -> spec (only non-default fields are written, so the saved spec stays readable)
  VB.placeSpecFromForm = function (st) {
    var f = st.places.form, spec = { terrain: {}, town: {} };
    var id = VB.PLACE_SLUG(f.id || f.name);
    if (f.name) spec.name = String(f.name).trim();
    if (id) spec.id = id;
    spec.culture = f.culture || "fantasy_generic";
    if (String(f.seed).trim() !== "" && isFinite(Number(f.seed))) spec.seed = Math.round(Number(f.seed));
    var t = spec.terrain; t.recipe = f.recipe || "rolling";
    if (/^(coastal|fjord)$/.test(t.recipe)) t.sea_side = f.sea_side || "south";
    t.rivers = Math.max(0, Math.min(3, Math.round(Number(f.rivers) || 0))); if (t.rivers) t.river_meander = f.river_meander || "gentle";
    if (+f.lakes) t.lakes = Math.min(4, Math.round(+f.lakes));
    if (String(f.relief_ft).trim() !== "" && isFinite(Number(f.relief_ft))) t.relief_ft = Number(f.relief_ft);
    var tw = spec.town; tw.population = VB.placePop(f.population);
    if (tw.population < VB.TINY_POP) {   // tiny settlement (town_tiny.py): layout / wall / centre feature do not apply
      if (tw.population > 0) tw.settlement = f.settlement || "auto";
    } else {
      tw.layout = f.layout || "organic"; tw.central_feature = f.central_feature || "market";
      if (f.wall || tw.layout === "walled") tw.wall = true;
    }
    spec.climate = f.climate || "temperate"; spec.season = f.season || "summer";
    if (+f.width_ft > 0 && +f.height_ft > 0) spec.size_ft = [Math.round(+f.width_ft), Math.round(+f.height_ft)];
    var P = st.places; spec.limits = { draft: !!P.draft }; if (P.allow_large) spec.limits.allow_large = true;
    return spec;
  };
  // spec -> form (loading a template / from-text result / pasted spec into the wizard)
  VB.placeFormFromSpec = function (st, spec) {
    var f = st.places.form, t = spec.terrain || {}, tw = spec.town || {};
    var set = function (k, v) { if (v !== undefined && v !== null) f[k] = v; };
    set("name", spec.name); set("id", spec.id || VB.PLACE_SLUG(spec.name)); set("culture", spec.culture); set("seed", spec.seed === undefined ? "" : spec.seed);
    set("recipe", t.recipe); set("sea_side", t.sea_side || "south"); set("rivers", t.rivers === undefined ? 1 : t.rivers); set("lakes", t.lakes || 0); set("river_meander", t.river_meander || "gentle");
    set("relief_ft", t.relief_ft === undefined ? "" : t.relief_ft);
    set("population", tw.population); set("settlement", tw.settlement || "auto"); set("layout", tw.layout); set("central_feature", tw.central_feature || "market"); set("wall", !!tw.wall);
    set("climate", spec.climate || "temperate"); set("season", spec.season || "summer");
    if (spec.size_ft) { f.width_ft = spec.size_ft[0]; f.height_ft = spec.size_ft[1]; } else { f.width_ft = ""; f.height_ft = ""; }
    if (spec.limits && spec.limits.draft !== undefined) st.places.draft = !!spec.limits.draft;
  };
  // rough size and building estimate (same formulas as place_create.normalise) with the safety caps; { text, level: "" | "warn" | "bad", problems: [] }
  VB.placeEstimate = function (st) {
    var P = st.places, f = P.form, pop = VB.placePop(f.population);
    if (pop < VB.TINY_POP) {   // tiny settlement: mirror of town_tiny.default_size / place_create.normalise; no caps can be hit
      var kind = pop <= 0 ? "none" : (f.settlement && f.settlement !== "auto" ? f.settlement : pop <= 5 ? "farmstead" : "hamlet");
      var ds = { none: [600, 400], cabin: [400, 300], lodge: [500, 400], farmstead: [600, 450], inn: [600, 450], hamlet: [800, 600] }[kind] || [600, 450];
      var tW = +f.width_ft > 0 ? +f.width_ft : ds[0], tH = +f.height_ft > 0 ? +f.height_ft : ds[1];
      var nb = { none: 0, cabin: 2, lodge: 3, farmstead: 3 + (pop >= 3 ? 1 : 0) + (pop >= 5 ? 1 : 0), inn: 4 }[kind];
      if (nb === undefined) nb = Math.min(6, Math.max(2, Math.round(pop / 5)) + (pop < 12 ? 1 : 2)) + 1;
      var tt = pop <= 0 ? "0 people: no settlement, terrain and water only, place " + tW + " x " + tH + " ft." :
        pop + " " + (pop === 1 ? "person" : "people") + ": " + kind + " (tiny settlement: about " + nb + " buildings with a track, yard" + (kind === "cabin" || kind === "lodge" ? "" : " and fenced fields") + "; no market, walls or gates), place " + tW + " x " + tH + " ft. A few seconds.";
      return { text: tt, level: "", problems: [], est: nb, area: tW * tH, size: [tW, tH], tiny: kind };
    }
    var area = Math.max(pop * 1000, 60000), est = Math.round(pop * 0.45) + 12;
    var W = +f.width_ft > 0 ? +f.width_ft : Math.max(1600, Math.round(Math.sqrt(area * 6 * 1.6) / 100) * 100), H = +f.height_ft > 0 ? +f.height_ft : Math.round(W / 1.6 / 100) * 100;
    var probs = [];
    if (!P.allow_large) {
      if (Math.max(W, H) > LIM.max_place_ft) probs.push("place " + W + " x " + H + " ft is over the " + LIM.max_place_ft + " ft cap");
      if (area > LIM.max_area_ft2) probs.push("about " + Math.round(area / 1000) + "k ft2 of town (cap " + Math.round(LIM.max_area_ft2 / 1000) + "k)");
      if (est > LIM.max_buildings && !P.draft) probs.push("about " + est + " buildings (cap " + LIM.max_buildings + "): tick Draft quality or Allow large");
    }
    var secs = P.draft ? Math.max(2, Math.round(est / 400)) : Math.round(2 + est / 90);
    var text = pop + " people: about " + est + " buildings on " + Math.round(area / 43560 * 10) / 10 + " acres, place " + W + " x " + H + " ft. " +
      (P.draft ? "Draft: civic buildings only, coarse terrain (about " + secs + " s)." : "Full quality: about " + secs + " s" + (est > 600 ? " and a lot of memory; opening the SVG in Illustrator can take minutes (use Draft first)" : "") + ".");
    return { text: text, level: probs.length ? "bad" : est > 600 && !P.draft ? "warn" : "", problems: probs, est: est, area: area, size: [W, H] };
  };

  VB.placeSpecPath = function (id) { return GEN.replace("generators/", "") + "out/places/" + id + "_spec.json"; };
  function parseSpecText(t) {
    var o; try { o = JSON.parse(t); } catch (e) { throw new Error("the pasted spec is not valid JSON: " + e.message); }
    if (!o || typeof o !== "object" || Array.isArray(o)) throw new Error("the spec must be a JSON object");
    return o;
  }
  VB.placeSpecFromState = function (st) { return st.places.spec_text && st.places.spec_text.trim() ? parseSpecText(st.places.spec_text) : VB.placeSpecFromForm(st); };

  VB.jobPlaceValidate = function (st) {
    var spec = VB.placeSpecFromState(st), id = spec.id || VB.PLACE_SLUG(spec.name) || "place", p = VB.placeSpecPath(id);
    return { kind: "place_validate", label: "Validate place spec", params: { id: id },
      steps: [{ t: "write", path: p, data: spec }, py(GEN + "place_create.py", ["validate", p], "place_create.py validate", { json: "val" }),
        { t: "fn", label: "report", fn: function (run) { var v = run.vars.val; run.setState("places.last", { validated: true, id: v.id, derived: v.derived, warnings: v.warnings, errors: v.errors, caps: v.caps }); run.log("valid: " + v.id + " (" + (v.derived && v.derived.category) + ", est. " + (v.derived && v.derived.est_buildings) + " buildings)"); (v.warnings || []).forEach(function (w) { run.log("warning: " + w); }); } }] };
  };
  VB.jobPlaceCreate = function (st, d, opts) {
    opts = opts || {}; var spec = VB.placeSpecFromState(st), P = st.places;
    spec.limits = Object.assign({}, spec.limits || {}, { draft: !!P.draft }); if (P.allow_large) spec.limits.allow_large = true;
    var id = spec.id || VB.PLACE_SLUG(spec.name);
    if (!id) { var dt = new Date(); id = "new_place_" + dt.getFullYear() + ("0" + (dt.getMonth() + 1)).slice(-2) + ("0" + dt.getDate()).slice(-2) + "_" + ("0" + dt.getHours()).slice(-2) + ("0" + dt.getMinutes()).slice(-2); }   // empty form: python generates the name
    spec.id = id; var p = VB.placeSpecPath(id);
    var steps = [
      { t: "fn", label: "size check", fn: function () { var e = VB.placeEstimate(st); if (!P.spec_text.trim() && e.problems.length) throw new Error("too big for the safe limits: " + e.problems.join("; ") + " (Allow large lifts the caps; Draft quality skips the houses)"); } },
      { t: "write", path: p, data: spec },
      py(GEN + "place_create.py", ["create", p].concat(opts.force ? ["--force"] : [], P.draft ? ["--draft"] : []), "place_create.py create", { json: "create" }),
      { t: "fn", label: "remember", fn: function (run) {
        var r = run.vars.create, rep = r.report || {};
        run.setState("places.last", { id: r.id, dir: r.dir, at: new Date().toISOString(), draft: !!rep.draft, counts: (rep.town || {}).counts, seconds: rep.seconds, wall: rep.wall, warnings: ((rep.town || {}).warnings || []).concat(rep.warnings || []) });
        run.log("created world/" + r.id + " in " + rep.seconds + " s: " + JSON.stringify((rep.town || {}).counts || {}));
      } }];
    if (opts.render !== false && P.render_after) steps.push(py(GEN + "place_render.py", function () { return ["--place", id, "--view", "town", "--no-fills"].concat(P.draft ? ["--dpi", "80", "--png-dpi", "80"] : [], P.open_after ? ["--job"] : []); }, "place_render.py", { json: "render" }),
      { t: "fn", label: "preview", fn: function (run) { var r = run.vars.render; run.setState("places.preview_png", r.png); run.log("preview " + r.png + (r.job_file ? "; Illustrator job written: " + r.job_file : "")); } });
    return { kind: "place_create", label: "Generate place " + id + (P.draft ? " (draft)" : ""), params: { spec: spec }, steps: steps, newPlace: id };
  };
  VB.jobPlaceFromText = function (st) {
    var t = String(st.places.from_text || "").trim(); if (!t) throw new Error("type a description first");
    var out = "illustrator/out/places/_from_text.json";
    return { kind: "place_from_text", label: "Parse description", params: { text: t },
      steps: [py(GEN + "place_create.py", ["from-text", t, "--out", out], "place_create.py from-text"),
        { t: "fn", label: "load into the form", fn: function (run) {
          var spec = run.readJson(out); VB.placeFormFromSpec(st, spec); run.setState("places.form", st.places.form); run.setState("places.draft", st.places.draft);
          var notes = String(run.lastOut || "").split(/\r?\n/).filter(function (l) { return /^note:/.test(l); }).map(function (l) { return l.replace(/^note:\s*/, ""); });
          run.setState("places.notes", notes); notes.forEach(function (n) { run.log("note: " + n); });
        } }] };
  };
  VB.jobImportScene = function (st, d) {
    var I = st.places.import, uuid = String(I.scene_uuid || "").trim();
    var dry = !!I.dry_run, snap = { lights: !!I.lights, tokens: !!I.tokens, notes: !!I.notes, closed_as: I.closed_as, place_id: I.place_id };   // snapshot: steps run later, the panel resets I.dry_run right after starting the job
    return { kind: "foundry_import_scene", label: (dry ? "Check scene import" : "Import Foundry scene as place"), params: { import: I },
      steps: [{ t: "fn", label: "check", fn: function () { if (!/^Scene\./.test(uuid)) throw new Error("pick a Foundry scene (or paste its Scene.xxxx uuid) first"); } },
        py(GEN + "foundry_push.py", function () {
          var inc = ["walls", "tiles", "regions"].concat(snap.lights ? ["lights"] : [], snap.tokens ? ["tokens"] : [], snap.notes ? ["notes"] : []);
          var a = ["import-scene", "--scene-uuid", uuid, "--include", inc.join(","), "--closed-as", snap.closed_as || "lines"];
          if (String(snap.place_id || "").trim()) a.push("--place-id", VB.PLACE_SLUG(snap.place_id));
          if (VB.extraArgs) a = a.concat(VB.extraArgs(st, "import-scene"));   // TOOLS TAB: --no-image, --force, --scene-json
          if (dry) a.push("--dry-run");
          return a;
        }, "foundry_push.py import-scene", { json: "imp" }),
        { t: "fn", label: "remember", fn: function (run) { var r = run.vars.imp; run.setState("places.last", { imported: r.place_id, scene_uuid: r.scene_uuid, size_ft: r.size_ft, walls: r.walls, closed_loops: r.closed_loops, underlay: r.underlay && (r.underlay.png || r.underlay.error), dry: !!r.dry_run, tiles: r.tiles, regions: r.regions, scene_3d: !!r.scene_3d, warnings: r.warnings, at: new Date().toISOString() });
          run.log((r.dry_run ? "would import " : "imported ") + r.place_id + ": " + r.size_ft.join(" x ") + " ft, " + r.walls + " walls, " + r.closed_loops + " closed loops, " + (r.tiles || 0) + " tiles" + (r.scene_3d ? ", 3D settings" : "") + (r.underlay ? ", underlay " + (r.underlay.png || r.underlay.error) : "")); } }],
      newPlace: dry ? null : (VB.PLACE_SLUG(snap.place_id) || null) };
  };
  // Import base map image: a place from a plain picture (no Foundry). python: place_create.py import-image (foundry_import.import_image).
  VB.jobImportImage = function (st, dry) {
    var I = st.places.image || {}, path = String(I.path || "").trim(), fpp = Number(I.ft_per_px), rot = String(I.rotate || "").trim(), grid = String(I.grid_ft === 0 ? "0" : I.grid_ft || "").trim();
    var name = String(I.name || "").trim(), id = VB.PLACE_SLUG(I.id || name);
    var snap = { path: path, fpp: fpp, rot: rot, grid: grid, noGrid: !!I.no_grid, name: name, id: id, dry: !!dry };   // snapshot: steps run later
    return { kind: "place_import_image", label: (dry ? "Check base map import" : "Import base map image as place"), params: { image: I },
      steps: [{ t: "fn", label: "check", fn: function () {
        if (!snap.path) throw new Error("give the path of the base map image first");
        if (!(snap.fpp > 0)) throw new Error("ft per pixel must be a number above 0 (the map's scale: feet that one image pixel covers)");
        if (snap.rot !== "" && !isFinite(Number(snap.rot))) throw new Error("rotate must be a number of degrees (clockwise) or empty");
        if (snap.grid !== "" && !(Number(snap.grid) >= 0)) throw new Error("grid ft must be a number (0 = no grid) or empty");
      } },
        py(GEN + "place_create.py", function () {
          var a = ["import-image", snap.path, "--ft-per-px", String(snap.fpp)];
          if (snap.name) a.push("--name", snap.name);
          if (snap.id) a.push("--id", snap.id);
          if (snap.rot !== "" && Number(snap.rot) !== 0) a.push("--rotate", String(Number(snap.rot)));
          if (snap.noGrid || (snap.grid !== "" && Number(snap.grid) === 0)) a.push("--no-grid");
          else if (snap.grid !== "") a.push("--grid-ft", String(Number(snap.grid)));
          if (VB.extraArgs) a = a.concat(VB.extraArgs(st, "import-image"));
          if (snap.dry) a.push("--dry-run");
          return a;
        }, "place_create.py import-image", { json: "img" }),
        { t: "fn", label: "remember", fn: function (run) { var r = run.vars.img; run.setState("places.last", { imported: r.place_id, source_image: r.source_image, size_ft: r.size_ft, ft_per_px: r.ft_per_px, image_px: r.image_px, rotate_deg: r.rotate_deg, underlay: r.underlay && (r.underlay.png || r.underlay.error), dry: !!r.dry_run, at: new Date().toISOString() });
          run.log((r.dry_run ? "would import " : "imported ") + r.place_id + ": " + r.size_ft.join(" x ") + " ft from " + r.image_px.join(" x ") + " px at " + r.ft_per_px + " ft/px" + (r.underlay ? ", underlay " + (r.underlay.png || r.underlay.error) : "")); } }],
      newPlace: dry ? null : (id || VB.PLACE_SLUG(name) || null) };
  };
  // Blank place (from scratch): terrain only, no town. python: place_create.py create-blank.
  VB.placeBlankArgs = function (B) {
    var name = String(B.name || "").trim(), id = VB.PLACE_SLUG(B.id || name), num = function (v) { return String(v === undefined || v === null ? "" : v).trim(); };
    var a = ["create-blank"];
    if (name) a.push("--name", name);
    if (id) a.push("--id", id);
    a.push("--size-ft", String(Number(B.width_ft)), String(Number(B.height_ft)), "--recipe", B.recipe || "flat");
    if (num(B.relief_ft) !== "" && B.recipe !== "flat") a.push("--relief-ft", String(Number(B.relief_ft)));
    if (num(B.cell_ft) !== "") a.push("--cell-ft", String(Number(B.cell_ft)));
    if (num(B.seed) !== "") a.push("--seed", String(Math.round(Number(B.seed))));
    if (num(B.scale_ft_per_in) !== "") a.push("--scale-ft-per-in", String(Number(B.scale_ft_per_in)));
    if (num(B.grid_ft) !== "") a.push("--grid-ft", String(Number(B.grid_ft)));
    if (num(B.underlay) !== "") a.push("--underlay", num(B.underlay));
    if (B.force) a.push("--force");
    return { args: a, id: id };
  };
  VB.placeBlankProblem = function (B) {
    var name = String(B.name || "").trim(), id = VB.PLACE_SLUG(B.id || name), W = Number(B.width_ft), H = Number(B.height_ft);
    if (!id) return "give the blank place a name (or an id)";
    var p = VB.placeIdProblem(id); if (p) return p;
    if (!(W >= 100 && H >= 100 && W <= 18000 && H <= 18000)) return "width and height must be 100-18000 ft";
    if (["flat", "rolling_hills", "valley", "highland_ridge"].indexOf(B.recipe || "flat") < 0) return "terrain recipe must be flat, rolling_hills, valley or highland_ridge";
    var bad = ["relief_ft", "cell_ft", "seed", "scale_ft_per_in", "grid_ft"].filter(function (k) { var v = String(B[k] === undefined || B[k] === null ? "" : B[k]).trim(); return v !== "" && !(isFinite(Number(v)) && (k === "seed" || Number(v) > 0)); });
    if (bad.length) return bad.join(", ") + ": numbers above 0 or empty";
    if (String(B.cell_ft || "").trim() !== "" && (Number(B.cell_ft) < 2 || Number(B.cell_ft) > 40)) return "cell size must be 2-40 ft";
    return "";
  };
  VB.jobPlaceBlank = function (st, dry) {
    var B = JSON.parse(JSON.stringify(st.places.blank || {}));   // snapshot: steps run later
    var pa = VB.placeBlankArgs(B), args = pa.args.concat(dry ? ["--dry-run"] : []);
    return { kind: "place_blank", label: (dry ? "Check blank place " : "Create blank place ") + (pa.id || "?"), params: { blank: B },
      steps: [{ t: "fn", label: "check", fn: function () { var p = VB.placeBlankProblem(B); if (p) throw new Error(p); } },
        py(GEN + "place_create.py", args, "place_create.py create-blank", { json: "blank" }),
        { t: "fn", label: "remember", fn: function (run) {
          var r = run.vars.blank; run.setState("places.last", { blank: r.id, name: r.name, size_ft: r.size_ft, recipe: r.recipe, cell_ft: r.cell_ft, scale_ft_per_in: r.scale_ft_per_in, grid_ft: r.grid_ft, dry: !!r.dry_run, warnings: r.warnings || [], at: new Date().toISOString() });
          run.log((r.dry_run ? "would create " : "created ") + "world/" + r.id + ": " + r.size_ft.join(" x ") + " ft, " + r.recipe + " terrain, cell " + r.cell_ft + " ft, heightmap " + (r.heightmap_nodes || []).join(" x ") + (r.warnings && r.warnings.length ? "; " + r.warnings.join("; ") : ""));
        } }],
      newPlace: dry ? null : pa.id };
  };
  // Manage places: python place_manage.py (edit / rename / duplicate / trash / restore / purge / trash-list). op: edit|rename|duplicate|trash|restore|purge|trash_list
  VB.placeManageArgs = function (st, op, place, dry) {
    var M = st.places.manage || {}, s = function (v) { return String(v === undefined || v === null ? "" : v).trim(); }, a;
    if (op === "edit") {
      a = ["edit", "--place", place];
      [["name", "--name"], ["notes", "--notes"], ["kind", "--kind"], ["status", "--status"], ["culture", "--culture"], ["season", "--season"], ["units", "--units"]].forEach(function (kv) { if (s(M[kv[0]]) !== "") a.push(kv[1], s(M[kv[0]])); });
      if (s(M.focus_x) !== "" && s(M.focus_y) !== "") a.push("--focus", String(Number(M.focus_x)), String(Number(M.focus_y)));
      if (s(M.scale_ft_per_in) !== "") a.push("--scale-ft-per-in", String(Number(M.scale_ft_per_in)));
      if (s(M.grid_ft) !== "") a.push("--grid-ft", String(Number(M.grid_ft)));
      if (a.length === 3) throw new Error("nothing to change: fill at least one field (Load fields from the selected place first)");
    } else if (op === "rename") {
      a = ["rename", "--place", place, "--new-id", VB.PLACE_SLUG(M.new_id)].concat(M.include_export ? ["--include-export"] : []);
    } else if (op === "duplicate") {
      a = ["duplicate", "--place", place, "--new-id", VB.PLACE_SLUG(M.dup_id)].concat(s(M.dup_name) ? ["--name", s(M.dup_name)] : [], M.dup_include_export ? ["--include-export"] : []);
    } else if (op === "trash") {
      a = ["trash", "--place", place];
    } else if (op === "restore") {
      a = ["restore", "--entry", s(M.trash_entry)].concat(s(M.restore_as) ? ["--as", VB.PLACE_SLUG(M.restore_as)] : []);
    } else if (op === "purge") {
      a = ["purge", "--entry", s(M.trash_entry), "--confirm", s(M.purge_confirm)];
    } else if (op === "trash_list") {
      return ["trash-list"];
    } else throw new Error("unknown place operation " + op);
    return dry ? a.concat(["--dry-run"]) : a;
  };
  VB.jobPlaceManage = function (st, op, place, opts) {
    opts = opts || {};
    var M = JSON.parse(JSON.stringify(st.places.manage || {})), cur = st.place, dry = !!opts.dry, existing = opts.existing || [];
    var needPlace = ["edit", "rename", "duplicate", "trash"].indexOf(op) >= 0;
    var check = function () {
      if (needPlace && !place) throw new Error("select a place in the list first");
      if ((op === "rename" || op === "trash") && place === cur) throw new Error(place + " is the place open in the panel: switch to another place first (Switch to selected on another row)");
      if (op === "rename") { var p = VB.placeIdProblem(VB.PLACE_SLUG(M.new_id), existing); if (!String(M.new_id || "").trim()) p = "type the new id"; if (p) throw new Error(p); }
      if (op === "duplicate") { var q = VB.placeIdProblem(VB.PLACE_SLUG(M.dup_id), existing); if (!String(M.dup_id || "").trim()) q = "type the id of the copy"; if (q) throw new Error(q); }
      if ((op === "restore" || op === "purge") && !String(M.trash_entry || "").trim()) throw new Error("pick a trash entry first");
      if (op === "purge" && !String(M.purge_confirm || "").trim()) throw new Error("type the place id to confirm the permanent delete");
    };
    check();
    var args = VB.placeManageArgs({ places: { manage: M } }, op, place, dry);
    var labels = { edit: "Edit place", rename: "Rename place", duplicate: "Duplicate place", trash: "Move place to trash", restore: "Restore place from trash", purge: "Delete place permanently", trash_list: "List trash" };
    var newPlace = null;
    if (!dry && op === "duplicate") newPlace = VB.PLACE_SLUG(M.dup_id);
    return { kind: "place_manage", label: (dry ? "Check: " : "") + labels[op] + (place ? " " + place : ""), params: { op: op, place: place, dry: dry },
      steps: [py(GEN + "place_manage.py", args, "place_manage.py " + args[0], { json: "pm" }),
        { t: "fn", label: "report", fn: function (run) {
          var r = run.vars.pm; if (op === "trash_list") { run.setState("places.trash", r.trash || []); run.log((r.trash || []).length + " place(s) in the trash"); return; }
          run.setState("places.last", Object.assign({ manage: op, at: new Date().toISOString() }, r));
          var pl = r.plan || {};
          run.log((r.dry_run ? "would " : "") + op + " " + (place || r.entry || "") + (r.new ? " -> " + r.new : "") + (pl.json_files ? ": " + pl.json_files.length + " file(s) with references" : "") + (r.changes ? ": " + JSON.stringify(r.changes) : ""));
          (pl.left_behind || r.left_behind || []).forEach(function (x) { run.log("not changed: " + x); });
        } }],
      newPlace: newPlace, manage: { op: op, place: place, dry: dry, newId: op === "rename" ? VB.PLACE_SLUG(M.new_id) : op === "restore" ? (VB.PLACE_SLUG(M.restore_as) || null) : null } };
  };
  VB.jobPlaceRender = function (st, id, opts) {
    opts = opts || {};
    return { kind: "place_render", label: "Render " + id + " (headless" + (opts.job ? " + Illustrator job" : "") + ")", params: { id: id },
      steps: [py(GEN + "place_render.py", ["--place", id, "--view", "town"].concat(opts.draft ? ["--no-fills", "--dpi", "80", "--png-dpi", "80"] : [], opts.job ? ["--job"] : []), "place_render.py", { json: "render" }),
        { t: "fn", label: "preview", fn: function (run) { var r = run.vars.render; run.setState("places.preview_png", r.png); run.log("preview " + r.png + (r.job_file ? "; job " + r.job_file : "")); } }] };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.places = VB.placesDefaults(); return o; };
})(typeof window !== "undefined" ? window : this);
