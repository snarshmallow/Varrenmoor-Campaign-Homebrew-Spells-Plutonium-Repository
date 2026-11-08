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
        climate: "temperate", season: "summer", central_feature: "market", wall: false, seed: "", width_ft: "", height_ft: "", relief_ft: "" },
      import: { scene_uuid: "", place_id: "", walls: true, lights: false, tokens: false, notes: false, closed_as: "lines", dry_run: false },
      last: null, notes: [], estimate: null
    };
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
    var tw = spec.town; tw.population = Math.round(Number(f.population) || 600); tw.layout = f.layout || "organic"; tw.central_feature = f.central_feature || "market";
    if (f.wall || tw.layout === "walled") tw.wall = true;
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
    set("population", tw.population); set("layout", tw.layout); set("central_feature", tw.central_feature || "market"); set("wall", !!tw.wall);
    set("climate", spec.climate || "temperate"); set("season", spec.season || "summer");
    if (spec.size_ft) { f.width_ft = spec.size_ft[0]; f.height_ft = spec.size_ft[1]; } else { f.width_ft = ""; f.height_ft = ""; }
    if (spec.limits && spec.limits.draft !== undefined) st.places.draft = !!spec.limits.draft;
  };
  // rough size and building estimate (same formulas as place_create.normalise) with the safety caps; { text, level: "" | "warn" | "bad", problems: [] }
  VB.placeEstimate = function (st) {
    var P = st.places, f = P.form, pop = Math.max(20, Math.round(Number(f.population) || 600));
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
    var id = spec.id || VB.PLACE_SLUG(spec.name); if (!id) throw new Error("give the place a name or id");
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
          if (dry) a.push("--dry-run");
          return a;
        }, "foundry_push.py import-scene", { json: "imp" }),
        { t: "fn", label: "remember", fn: function (run) { var r = run.vars.imp; run.setState("places.last", { imported: r.place_id, scene_uuid: r.scene_uuid, size_ft: r.size_ft, walls: r.walls, closed_loops: r.closed_loops, underlay: r.underlay && (r.underlay.png || r.underlay.error), dry: !!r.dry_run, tiles: r.tiles, regions: r.regions, scene_3d: !!r.scene_3d, warnings: r.warnings, at: new Date().toISOString() });
          run.log((r.dry_run ? "would import " : "imported ") + r.place_id + ": " + r.size_ft.join(" x ") + " ft, " + r.walls + " walls, " + r.closed_loops + " closed loops, " + (r.tiles || 0) + " tiles" + (r.scene_3d ? ", 3D settings" : "") + (r.underlay ? ", underlay " + (r.underlay.png || r.underlay.error) : "")); } }],
      newPlace: dry ? null : (VB.PLACE_SLUG(snap.place_id) || null) };
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
