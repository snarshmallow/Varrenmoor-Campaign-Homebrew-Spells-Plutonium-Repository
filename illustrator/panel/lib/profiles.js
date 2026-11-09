// Plugin profiles: named, versioned bundles of SETTINGS (never geometry or place identity). Pure logic, no DOM, no direct fs:
// collect / diff / apply / validate / migrate on an explicit allow-list schema, plus a store that takes an injected fs/path (atomic writes).
// UI: profiles_ui.js. Files: illustrator/presets/profiles/<name>.json (user), world/<place>/profiles/<name>.json (per place),
// illustrator/presets/profiles/builtin/<name>.json (shipped, read-only), illustrator/presets/profiles/_default.json (default marker).
// Published on window EVEN WHEN Node's module exists (CEP has both) and exported for tests.
(function (root) {
  "use strict";
  var P = {};
  P.FORMAT = "varrenmoor-profile";
  P.LEGACY_FORMATS = ["varrenmoor.plugin.profile"];   // early drafts; migrate() lifts them
  P.VERSION = 1;

  // ---------------------------------------------------------------- the allow-list schema
  // Each section lists dotted state paths (a path may be a whole subtree). Anything NOT under one of these paths is never captured and never applied.
  // DENY_KEYS are removed at any depth inside an allowed subtree: captured geometry, lists of placed things, scene ids, results and preview caches.
  P.SECTIONS = [
    { id: "export", title: "Export options (pack, split, merge, push, roads 3D)", paths: [
      "foundry.models.split", "foundry.models.preset", "foundry.models.layers", "foundry.models.lod", "foundry.models.compress", "foundry.models.roofMode",
      "foundry.models.interiorStyle", "foundry.models.splitPreset", "foundry.models.carve", "foundry.models.conform", "foundry.models.prune", "foundry.models.roofsHidden",
      "foundry.models.sceneMode", "foundry.dpi", "foundry.ftPerGrid", "foundry.hideGrid", "foundry.walls", "foundry.drawRoads", "foundry.drawWater", "foundry.tileLayers", "foundry.sizeFt",
      "foundry.autoPush", "roads", "tools.s3d.skybox_preset", "tools.s3d.no_skybox", "tools.s3d.no_padding", "tools.s3d.use_padding_tab", "tools.s3d.with_lights", "tools.s3d.prune_lights",
      "tools.s3d.layers", "tools.s3d.lod", "exp.sel" ] },
    { id: "collision", title: "Collision, sight and wall flags", paths: ["foundry.models.collision", "foundry.models.sight", "foundry.models.alsoWalls"] },
    { id: "lighting", title: "Lighting, sky and sun (3D lighting, sun/fog, skybox, 2D light look)", paths: [
      "lighting.enabled", "lighting.mode", "lighting.sun", "lighting.ambient", "lighting.terrain_shade", "lighting.height_scale", "lighting.roof_pitch", "lighting.shadow", "lighting.glow",
      "lighting.vector", "lighting.auto", "lighting.preview_dpi", "lighting.dpi", "lighting.embed", "lighting.f3d", "lighting.sun3d",
      "skybox.preset", "skybox.width", "skybox.yaw", "skybox.use_lighting_sun", "skybox.apply_lighting", "water3d.preset", "water3d.force", "water3d.values" ] },
    { id: "streetlamps", title: "Streetlamps", paths: ["streetlamps"] },
    { id: "terrain", title: "Terrain base spec and contours", paths: ["terrain.spec", "contours"] },
    { id: "scale", title: "Scale, view and grid", paths: ["scale", "settings.dpi", "settings.view", "settings.link_images"] },
    { id: "style", title: "Labels and shading style", paths: ["labels", "label_offset", "shading"] },
    { id: "foliage", title: "Foliage and padding", paths: [
      "foliage.mix", "foliage.mix_preset", "foliage.density_per_ha", "foliage.size_var", "foliage.seed", "foliage.pattern", "foliage.zone", "foliage.cluster_radius_ft", "foliage.cluster_size",
      "foliage.edge_ft", "foliage.row_spacing_ft", "foliage.row_angle_deg", "foliage.line_spacing_ft", "foliage.avoid_buildings", "foliage.avoid_roads", "foliage.avoid_water",
      "foliage.slope_max_deg", "foliage.elev_min_ft", "foliage.elev_max_ft", "foliage.moisture_bias", "foliage.single_species", "foliage.draw", "foliage.merge", "padding" ] },
    { id: "town", title: "Roads, buildings, water and bridges defaults", paths: [
      "town.seed", "town.detail", "town.plazas_enabled", "town.plazas_min_area_ft2", "town.blocks", "town.buildings", "town.fields", "town.max_street_grade", "town.max_main_grade",
      "town.max_build_slope", "town.max_build_relief_ft", "town.max_field_slope", "town.redraw_contours", "town.autofill", "town.exportPack", "town.fills", "town.style", "town.aa", "town.fit",
      "town.fit_margin_ft", "water.sea_level_ft", "water.threshold_cells", "water.outlet_width", "water.delta", "water.meander", "water.bank_ft", "water.redraw", "water.rivergen", "water.river.width",
      "water.river.depth", "water.river.flow", "water.lake.depth", "water.lake.kind",
      "bridges.float_ft", "bridges.level_ft", "bridges.preset", "bridges.seed", "bridges.width_ft", "bridges.clearance_w_ft", "bridges.clearance_h_ft", "bridges.parapet_h_ft", "bridges.n_arches",
      "bridges.rise_ratio", "bridges.support", "bridges.roof", "bridges.flower_boxes", "bridges.sag_ratio", "bridges.decay" ] },
    { id: "target", title: "Foundry target options (new scene or existing; never the scene id)", paths: ["foundry.target"] }
  ];
  P.DENY_KEYS = /^(last|stats|qa|report|preview_png|previewAt|polygon|polygon_src|path|path_src|rings|area|area_src|sel|selected|items|crossings|lights|capture|children|list|cache|loaded|spec_loaded|params_loaded|candidate|scene|scene_uuid|sceneUuid|sceneName|uuid|out_dir|river_path|lake_polygon|river_src|lake_src|entry_x|entry_y|import_scene|import_name|save_name|ids|ids_src|id|actorUuid|itemUuid|python|node|env|clientFile|target_uuid)$/;
  // Secrets are refused at any depth regardless of section: relay tokens, pairing codes, passwords, api keys, credentials.
  P.SECRET_KEYS = /(token|passw|secret|apikey|api_key|(^|[_.-])key$|^key|pairing|pair_code|credential|auth|cookie|session|private)/i;
  // "exp.sel" is the Export checklist selection (a map of step id -> bool): its keys are step ids, so it is exempt from nothing else.
  P.sectionIds = function () { return P.SECTIONS.map(function (s) { return s.id; }); };
  P.section = function (id) { for (var i = 0; i < P.SECTIONS.length; i++) if (P.SECTIONS[i].id === id) return P.SECTIONS[i]; return null; };

  // ---------------------------------------------------------------- small helpers
  function clone(v) { return v === undefined ? undefined : JSON.parse(JSON.stringify(v)); }
  function isObj(v) { return v !== null && typeof v === "object" && !Array.isArray(v); }
  function getPath(o, p) { var ks = p.split("."), c = o; for (var i = 0; i < ks.length; i++) { if (c === null || c === undefined) return undefined; c = c[ks[i]]; } return c; }
  function setPath(o, p, v) {
    var ks = p.split("."), c = o;
    for (var i = 0; i < ks.length - 1; i++) { if (!isObj(c[ks[i]])) c[ks[i]] = {}; c = c[ks[i]]; }
    c[ks[ks.length - 1]] = v;
  }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function denied(path) { var ks = path.split("."); for (var i = 0; i < ks.length; i++) if (P.DENY_KEYS.test(ks[i])) return true; return false; }
  function secret(path) { var ks = path.split("."); for (var i = 0; i < ks.length; i++) if (P.SECRET_KEYS.test(ks[i])) return true; return false; }
  P.isSecret = secret;
  // is this dotted leaf path allowed in the given section (under one of its prefixes, no denied segment BELOW the prefix, no secret-like segment anywhere)?
  function allowedIn(sec, path) {
    if (secret(path)) return false;
    for (var i = 0; i < sec.paths.length; i++) {
      var pre = sec.paths[i];
      if (path === pre || path.indexOf(pre + ".") === 0) { var rest = path === pre ? "" : path.slice(pre.length + 1); return !rest || !denied(rest); }
    }
    return false;
  }
  P.sectionOf = function (path) { for (var i = 0; i < P.SECTIONS.length; i++) if (allowedIn(P.SECTIONS[i], path)) return P.SECTIONS[i].id; return null; };
  P.isAllowed = function (path) { return !!P.sectionOf(path); };
  // leaves under a value: primitives and arrays are leaves; objects recurse; empty objects vanish
  // array leaves may hold objects: drop denied / secret keys inside them too
  function scrub(v) {
    if (Array.isArray(v)) return v.map(scrub);
    if (isObj(v)) { var o = {}; Object.keys(v).forEach(function (k) { if (!P.DENY_KEYS.test(k) && !P.SECRET_KEYS.test(k)) o[k] = scrub(v[k]); }); return o; }
    return v;
  }
  function leaves(prefix, v, out) {
    if (isObj(v)) { Object.keys(v).forEach(function (k) { leaves(prefix + "." + k, v[k], out); }); }
    else if (v !== undefined && typeof v !== "function") out[prefix] = scrub(clone(v));
  }
  function collectSection(state, sec) {
    var out = {};
    sec.paths.forEach(function (pre) {
      var v = getPath(state, pre); if (v === undefined) return;
      var tmp = {}; leaves(pre, v, tmp);
      Object.keys(tmp).forEach(function (k) { if (allowedIn(sec, k)) out[k] = tmp[k]; });
    });
    return out;
  }

  // ---------------------------------------------------------------- names
  var RESERVED = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;
  // Safe file stem: letters, digits, space, dash, underscore, parentheses; everything else becomes "_". Returns "" when nothing usable remains.
  P.sanitizeName = function (name) {
    var s = String(name == null ? "" : name).replace(/[\u0000-\u001f]/g, "").replace(/[^A-Za-z0-9 _()\-]+/g, "_").replace(/\s+/g, " ").replace(/_{2,}/g, "_").replace(/^[ ._]+|[ ._]+$/g, "");
    if (s.length > 60) s = s.slice(0, 60).replace(/[ ._]+$/, "");
    if (RESERVED.test(s)) s = s + "_";
    return s;
  };

  // ---------------------------------------------------------------- build / collect
  P.collect = function (state, sectionIds) {
    var ids = (sectionIds && sectionIds.length) ? sectionIds : P.sectionIds(), out = {};
    ids.forEach(function (id) { var s = P.section(id); if (s) out[id] = collectSection(state, s); });
    return out;
  };
  P.make = function (name, state, sectionIds, meta) {
    meta = meta || {}; var now = (meta.now || new Date()).toISOString(), ids = (sectionIds && sectionIds.length) ? sectionIds.slice() : P.sectionIds();
    return { format: P.FORMAT, version: P.VERSION, name: String(name), description: meta.description || "", created: meta.created || now, updated: now, builtin: false, scope: ids, sections: P.collect(state, ids) };
  };

  // ---------------------------------------------------------------- migration + validation
  // Older / foreign shapes are lifted to the current one. v0 (no version) = { name, settings: { "dotted.path": value } }.
  P.migrate = function (doc) {
    var d = clone(doc), warnings = [];
    if (!isObj(d)) return { doc: null, warnings: warnings };
    if (P.LEGACY_FORMATS.indexOf(d.format) >= 0) { d.format = P.FORMAT; warnings.push("migrated an early-draft profile format"); }
    if (d.format === undefined && d.version === undefined && isObj(d.settings)) {
      var secs = {}; Object.keys(d.settings).forEach(function (k) { var sid = P.sectionOf(k); if (sid) { (secs[sid] = secs[sid] || {})[k] = d.settings[k]; } else warnings.push("ignored unknown setting " + k); });
      d = { format: P.FORMAT, version: 1, name: d.name || "", description: d.description || "", created: d.created || "", updated: d.updated || "", builtin: false, scope: Object.keys(secs), sections: secs };
      warnings.push("migrated a version 0 profile");
    }
    return { doc: d, warnings: warnings };
  };
  // validate(doc) -> { ok, errors, warnings, doc } with the document cleaned: unknown top-level keys dropped, sections/paths outside the allow-list dropped with a warning.
  P.validate = function (raw) {
    var errors = [], warnings = [], m = P.migrate(raw), d = m.doc; warnings = warnings.concat(m.warnings);
    if (!d) return { ok: false, errors: ["profile is not a JSON object"], warnings: warnings, doc: null };
    if (d.format !== P.FORMAT) errors.push("not a Varrenmoor plugin profile (format is " + JSON.stringify(d.format) + ")");
    if (typeof d.version !== "number" || !(d.version >= 1) || Math.floor(d.version) !== d.version) errors.push("missing or invalid version");
    else if (d.version > P.VERSION) warnings.push("profile version " + d.version + " is newer than this panel (" + P.VERSION + "): applying the settings it understands");
    if (!isObj(d.sections)) errors.push("sections must be an object");
    if (typeof d.name !== "string" || !P.sanitizeName(d.name)) errors.push("profile needs a usable name");
    if (errors.length) return { ok: false, errors: errors, warnings: warnings, doc: null };
    var clean = { format: P.FORMAT, version: Math.min(d.version, P.VERSION), name: d.name, description: typeof d.description === "string" ? d.description : "", created: String(d.created || ""), updated: String(d.updated || ""), builtin: false, scope: [], sections: {} };
    Object.keys(d.sections).forEach(function (sid) {
      var sec = P.section(sid), src = d.sections[sid];
      if (!sec) { warnings.push("ignored unknown section " + sid); return; }
      if (!isObj(src)) { warnings.push("section " + sid + " is not an object: ignored"); return; }
      var out = {}; Object.keys(src).forEach(function (k0) {
        // an object value is flattened to leaves and each leaf checked, so { "padding": { "polygon": [...] } } cannot smuggle geometry
        var flat = {}; leaves(k0, src[k0], flat);
        Object.keys(flat).forEach(function (k) {
          if (!allowedIn(sec, k)) { warnings.push("ignored " + k + " (not a profile setting)"); return; }
          var v = flat[k]; if (v === undefined || typeof v === "function") return; out[k] = v;
        });
      });
      clean.sections[sid] = out; clean.scope.push(sid);
    });
    return { ok: true, errors: [], warnings: warnings, doc: clean };
  };

  // ---------------------------------------------------------------- diff / apply
  function typeOk(cur, nv) {   // refuse a type change against a typed current value (number <-> string etc.); null/"" are free
    if (cur === undefined || cur === null || nv === null) return true;
    if (Array.isArray(cur)) return Array.isArray(nv);
    if (isObj(cur)) return isObj(nv);
    if (typeof cur === "number" && typeof nv === "string" && nv === "") return true;
    return typeof cur === typeof nv;
  }
  // diff(state, doc, sectionIds?) -> [{ section, path, from, to }] for settings in the doc (selected sections only) that differ from the state
  P.diff = function (state, doc, sectionIds) {
    var out = [], ids = (sectionIds && sectionIds.length) ? sectionIds : Object.keys(doc.sections || {});
    ids.forEach(function (sid) {
      var raw = (doc.sections || {})[sid]; if (!isObj(raw) || !P.section(sid)) return;
      var src = {}; Object.keys(raw).forEach(function (k0) { leaves(k0, raw[k0], src); });   // never write a whole object subtree
      Object.keys(src).forEach(function (k) {
        if (!allowedIn(P.section(sid), k)) return;
        var cur = getPath(state, k); if (!same(cur, src[k])) out.push({ section: sid, path: k, from: cur === undefined ? null : cur, to: src[k] });
      });
    });
    return out;
  };
  P.summarize = function (diff) {
    var by = {}; diff.forEach(function (x) { by[x.section] = (by[x.section] || 0) + 1; });
    return Object.keys(by).map(function (k) { return { section: k, title: (P.section(k) || {}).title || k, count: by[k] }; });
  };
  // apply(state, doc, sectionIds?) -> { state (a new object), applied: n, skipped: [reason] }. Place identity and geometry cannot be reached: only allow-listed leaf paths are written.
  P.apply = function (state, doc, sectionIds) {
    var next = clone(state), applied = 0, skipped = [];
    P.diff(state, doc, sectionIds).forEach(function (x) {
      if (!typeOk(getPath(state, x.path), x.to)) { skipped.push(x.path + ": type mismatch (kept current)"); return; }
      setPath(next, x.path, clone(x.to)); applied++;
    });
    return { state: next, applied: applied, skipped: skipped };
  };
  // modified indicator: does the state differ from the loaded profile in the profile's own sections?
  P.isModified = function (state, doc) { return !!doc && P.diff(state, doc).length > 0; };
  // "reset to defaults": a pseudo-profile built from VBCore.defaults() for the chosen sections
  P.fromDefaults = function (defaults, sectionIds) { return P.make("defaults", defaults, sectionIds); };
  // default profile for a NEW place, applied at most once: records state.profile_applied and does nothing when it is already set
  P.applyDefaultOnce = function (state, doc, ref, now) {
    if (!doc || !ref || (state && state.profile_applied && state.profile_applied.name)) return { state: state, applied: 0, done: false };
    var r = P.apply(state, doc), at = (now || new Date()).toISOString();
    r.state.profile = { name: ref.name, where: ref.where, at: at };
    r.state.profile_applied = { name: ref.name, where: ref.where, at: at };
    return { state: r.state, applied: r.applied, done: true };
  };

  // ---------------------------------------------------------------- store (files). deps: { fs, path, userDir, placeDir (fn place -> dir), builtinDir, defaultFile, now }
  P.createStore = function (deps) {
    var fs = deps.fs, tmpN = 0;
    function join(a, b) { return (a + "/" + b).replace(/\\/g, "/").replace(/\/+/g, "/"); }
    function dirFor(where, place) {
      if (where === "builtin") return deps.builtinDir;
      if (where === "place") { if (!place) throw new Error("no place selected"); return deps.placeDir(place); }
      return deps.userDir;
    }
    function fileFor(where, name, place) { var s = P.sanitizeName(name); if (!s) throw new Error("invalid profile name"); return join(dirFor(where, place), s + ".json"); }
    function atomicWrite(file, text) {
      var dir = file.replace(/\/[^\/]*$/, ""); fs.mkdirSync(dir, { recursive: true });
      var tmp = file + ".tmp-" + (typeof process !== "undefined" && process.pid ? process.pid : 0) + "-" + (++tmpN);
      try { fs.writeFileSync(tmp, text); try { fs.renameSync(tmp, file); } catch (e) { try { fs.unlinkSync(file); } catch (e2) { /* absent */ } fs.renameSync(tmp, file); } }
      catch (e3) { try { fs.unlinkSync(tmp); } catch (e4) { /* none */ } throw e3; }
    }
    function readDoc(file, where) {
      var raw; try { raw = JSON.parse(fs.readFileSync(file, "utf8")); } catch (e) { return { ok: false, errors: ["cannot read " + file + ": " + e.message], warnings: [] }; }
      var v = P.validate(raw); if (v.ok && where === "builtin") v.doc.builtin = true; return v;
    }
    var api = {
      dirFor: dirFor, fileFor: fileFor, atomicWrite: atomicWrite,
      list: function (place) {
        var out = [];
        ["builtin", "user", "place"].forEach(function (w) {
          if (w === "place" && !place) return;
          var dir; try { dir = dirFor(w, place); } catch (e) { return; }
          var names = []; try { names = fs.readdirSync(dir); } catch (e) { names = []; }
          names.filter(function (n) { return /\.json$/i.test(n) && n.charAt(0) !== "_"; }).sort().forEach(function (n) {
            var r = readDoc(join(dir, n), w);
            out.push({ where: w, file: join(dir, n), name: r.ok ? r.doc.name : n.replace(/\.json$/i, ""), ok: r.ok, errors: r.errors, doc: r.ok ? r.doc : null });
          });
        });
        return out;
      },
      read: function (where, name, place) { return readDoc(fileFor(where, name, place), where); },
      // write(doc, where, place, opts { overwrite }) -> file; builtin is never writable
      write: function (doc, where, place, opts) {
        opts = opts || {}; if (where === "builtin") throw new Error("built-in profiles are read-only");
        var v = P.validate(doc); if (!v.ok) throw new Error("invalid profile: " + v.errors.join("; "));
        var d = v.doc; d.name = P.sanitizeName(d.name) === d.name ? d.name : P.sanitizeName(d.name); d.updated = (deps.now ? deps.now() : new Date()).toISOString();
        var f = fileFor(where, d.name, place);
        if (!opts.overwrite && fs.existsSync(f)) throw new Error("a profile named " + d.name + " already exists here");
        atomicWrite(f, JSON.stringify(d, null, 1) + "\n"); return f;
      },
      remove: function (where, name, place) {
        if (where === "builtin") throw new Error("built-in profiles are read-only");
        var f = fileFor(where, name, place); fs.unlinkSync(f); return f;
      },
      rename: function (where, oldName, newName, place) {
        if (where === "builtin") throw new Error("built-in profiles are read-only");
        var r = readDoc(fileFor(where, oldName, place), where); if (!r.ok) throw new Error(r.errors.join("; "));
        var nf = fileFor(where, newName, place); if (fs.existsSync(nf)) throw new Error("a profile named " + newName + " already exists here");
        r.doc.name = P.sanitizeName(newName); api.write(r.doc, where, place, { overwrite: true }); fs.unlinkSync(fileFor(where, oldName, place)); return nf;
      },
      duplicate: function (fromWhere, name, toWhere, newName, place) {
        var r = readDoc(fileFor(fromWhere, name, place), fromWhere); if (!r.ok) throw new Error(r.errors.join("; "));
        r.doc.name = newName; r.doc.created = ""; return api.write(r.doc, toWhere, place, {});
      },
      importFile: function (srcFile, toWhere, place) {
        var raw; try { raw = JSON.parse(fs.readFileSync(srcFile, "utf8")); } catch (e) { throw new Error("cannot read " + srcFile + ": " + e.message); }
        var v = P.validate(raw); if (!v.ok) throw new Error("not a usable profile: " + v.errors.join("; "));
        var f = api.write(v.doc, toWhere, place, { overwrite: false }); return { file: f, warnings: v.warnings, name: v.doc.name };
      },
      getDefault: function () { try { var j = JSON.parse(fs.readFileSync(deps.defaultFile, "utf8")); return j && j.name ? { name: String(j.name), where: j.where === "builtin" ? "builtin" : "user" } : null; } catch (e) { return null; } },
      setDefault: function (ref) { if (!ref) { try { fs.unlinkSync(deps.defaultFile); } catch (e) { /* none */ } return; } atomicWrite(deps.defaultFile, JSON.stringify({ name: ref.name, where: ref.where }, null, 1) + "\n"); }
    };
    return api;
  };

  if (typeof module !== "undefined" && module.exports) module.exports = P;
  if (typeof window !== "undefined") window.VBProfiles = P;   // always, even when Node's module exists (CEP)
  // state.profile = which profile this place last loaded (name + where); outside the allow-list, so a profile can never carry it
  var VBc = (typeof window !== "undefined" && window.VBCore) || (typeof module !== "undefined" && module.exports && (function () { try { return require("./core.js"); } catch (e) { return null; } })());
  if (VBc && VBc.defaults && !VBc.defaults.profiles) {
    var baseD = VBc.defaults;
    VBc.defaults = function () { var o = baseD(); o.profile = { name: "", where: "" }; return o; };
    VBc.defaults.profiles = true;
  }
})(typeof self !== "undefined" ? self : this);
