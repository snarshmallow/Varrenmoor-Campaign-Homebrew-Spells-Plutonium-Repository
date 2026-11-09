// Pure logic for the Varrenmoor panel: default state, geometry conversion, job builders.
// No DOM, no Node APIs: loaded by the panel (window.VBCore) and by Node tests (require).
(function (root) {
  "use strict";
  var VB = {};
  var GEN_LAYERS = ["Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", "Labels - Elevation", "Label Backing", "Leaders", "Leader Anchors", "Callout Markers", "Legend", "Labels - Hidden", "NOTES",
    "Walls", "Buildings", "Blocks", "Roads", "Water", "Contours - Minor", "Contours - Index", "Fences",
    "Grid", "Scale bar", "North arrow", "Bounds"];
  var GUIDE_LAYERS = ["GUIDES", "Grid", "Scale bar", "North arrow", "Bounds"];
  var CONTOUR_LAYERS = ["Contours - Minor", "Contours - Index", "Labels - Elevation"];
  var TOWN_LAYERS = ["Buildings", "Blocks", "Roads", "Water", "Fences", "Labels - Districts", "Labels - Streets", "Labels - Buildings", "Label Backing", "Leaders", "Leader Anchors", "Callout Markers", "Legend", "Labels - Hidden", "NOTES"];
  // label styling (mirrors generators/label_style.py; run_mock.js checks both agree)
  var LABEL_CATS = ["districts", "streets", "buildings", "rooms", "elevation"];
  var LABEL_LAYERS = ["Legend", "Callout Markers", "Leader Anchors", "Leaders", "Labels - Hidden", "Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms", "Labels - Elevation", "Label Backing"];
  var LABEL_TARGETS = { contours: ["Contours - Minor", "Contours - Index"], streets: ["Roads"], buildings: ["Buildings", "Walls"], blocks: ["Blocks"],
    water: ["Water"], fences: ["Fences"], grid: ["Grid"] };
  var LABEL_DEFAULT = { font: "Arial", size: null, bold: false, italic: false, letter_spacing: 0, case: "asis", color: "#111111", auto_contrast: false,
    wrap: "auto", wrap_width: 120, wrap_unit: "pt", max_lines: 3, line_spacing: 1.1, align: "center",
    mode: "halo", halo_color: "#ffffff", halo_width: 2, halo_opacity: 0.92, box_color: "#ffffff", box_pad: 2, box_radius: 2, box_opacity: 0.8,
    knockout: false, knockout_pad: 2.5,
    wrap_mode: "balanced", min_width: 0, max_width: 0, fit_shape: false, fit_ratio: 0.92, lines: 0, max_chars: 0, break_chars: true, abbrev: "off", small_caps: false };
  var LABEL_CAT_DEFAULT = {
    districts: { bold: true, "case": "auto", letter_spacing: 0.6, halo_width: 2.6 }, streets: { wrap: "off", italic: true, halo_width: 1.8 },
    buildings: { max_lines: 2, fit_shape: true }, rooms: { max_lines: 2 }, elevation: { wrap: "off", color: "#6b4423", mode: "none", knockout: true, knockout_pad: 1.5 } };
  VB.LABEL_CATS = LABEL_CATS; VB.LABEL_LAYERS = LABEL_LAYERS; VB.LABEL_TARGETS = LABEL_TARGETS;
  VB.FONTS = ["Arial", "Georgia", "Times New Roman", "Garamond", "Palatino Linotype", "Trebuchet MS", "Verdana", "Cambria", "Constantia", "Calibri", "Tahoma", "Candara", "Baskerville"];
  // declutter + leader options (mirrors generators/label_declutter.py DEFAULT and label_offset.DEFAULTS)
  VB.DECLUTTER_DEFAULT = { enabled: true, scale_visibility: true, collision: "hide", score: true, legend: true, legend_title: "Key", overrides: true, quiet: false, qa: true,
    tiers: { districts: { max_fpi: 1000, size: 1, number: false }, plazas: { max_fpi: 1000, size: 1, number: false }, civic: { max_fpi: 250, size: 1, number: false },
      streets: { max_fpi: 150, size: 0.95, number: false }, houses: { max_fpi: 45, size: 0.9, number: false, leader: false } } };
  VB.LEADER_DEFAULT = { enabled: true, style: "elbow", stroke_width: 0.8, margin_pct: 10, max_offset_pt: 90, dot: true, color: "#ffffff", casing: true, casing_color: "#1a1a1a",
    casing_width: 1.7, dot_ring: true, match_text: false, dash: "", lock_leaders: true };
  VB.labelDefaults = function () {
    var o = { "default": JSON.parse(JSON.stringify(LABEL_DEFAULT)) };
    LABEL_CATS.forEach(function (c) { o[c] = JSON.parse(JSON.stringify(LABEL_CAT_DEFAULT[c] || {})); });
    return o;
  };
  var RAISE = ["mountain", "rolling_hills", "mesa", "plateau", "dunes", "rocky_crags", "ridge_line"];
  var DEPRESS = ["bowl", "valley", "trench", "sinkhole", "seabed_shelf"];
  var EXTRA_SWATCHES = [
    { name: "paper", rgb: [243, 234, 210] }, { name: "white", rgb: [255, 255, 255] }, { name: "black", rgb: [20, 20, 20] },
    { name: "water_pale", rgb: [185, 207, 224] }, { name: "water_blue", rgb: [127, 166, 200] }, { name: "water_deep", rgb: [59, 106, 151] },
    { name: "water_dark", rgb: [40, 62, 84] }];
  VB.GEN_LAYERS = GEN_LAYERS; VB.GUIDE_LAYERS = GUIDE_LAYERS; VB.CONTOUR_LAYERS = CONTOUR_LAYERS; VB.TOWN_LAYERS = TOWN_LAYERS;
  VB.RAISE = RAISE; VB.DEPRESS = DEPRESS; VB.EXTRA_SWATCHES = EXTRA_SWATCHES;
  VB.PARTS = { // town fill parts -> named layer + item-name filter
    streets: { layer: "Roads", match: null, exclude: "^sqr_", label: "Streets" },
    plazas: { layer: "Roads", match: "^sqr_", label: "Plazas" },
    buildings: { layer: "Buildings", match: null, label: "Buildings" },
    fields: { layer: "Fences", match: "^fld_", label: "Fields" },
    water: { layer: "Water", match: null, label: "Water" }
  };

  var clone = function (o) { return JSON.parse(JSON.stringify(o)); };
  VB.clone = clone;
  VB.deepMerge = function (a, b) {
    if (b === undefined) return clone(a);
    if (Array.isArray(a) || Array.isArray(b) || typeof a !== "object" || typeof b !== "object" || !a || !b) return clone(b);
    var o = clone(a);
    Object.keys(b).forEach(function (k) { o[k] = (k in o) ? VB.deepMerge(o[k], b[k]) : clone(b[k]); });
    return o;
  };
  VB.getPath = function (o, p) { return p.split(".").reduce(function (c, k) { return c == null ? undefined : c[k]; }, o); };
  VB.setPath = function (o, p, v) {
    var ks = p.split("."), c = o;
    for (var i = 0; i < ks.length - 1; i++) { if (typeof c[ks[i]] !== "object" || c[ks[i]] === null) c[ks[i]] = {}; c = c[ks[i]]; }
    c[ks[ks.length - 1]] = v;
  };

  VB.defaults = function () {
    return {
      v: 1, place: "bridgehollow",
      settings: { python: "python", dpi: 150, view: "town", link_images: false },
      scale: { preset: "town", scale_ft_per_in: 100, grid_ft: 100, grid_major_every: 5, page_w_in: 17, page_h_in: 11, units: "ft", grid_full_page: false, grid_show: true, loaded: false },
      terrain: {
        spec: { seed: 1103, cell_ft: 10, base_elevation_ft: 660, ridged_amp_ft: 110, noise_scale_ft: 420, thermal_iterations: 60, smooth_sigma_cells: 1,
          recipe: "rolling_hills", relief_ft: 0, image_blend: 0 },
        spec_loaded: false,
        patch: { terrain_type: "mountain", max_height_ft: 900, min_height_ft: 600, avg_height_ft: 800, steepness: 0.5, feather_ft: 80,
          roughness: 0.4, seed: 1, angle_deg: 0, polygon: [], polygon_src: "" },
        selected_patch: null
      },
      contours: { minor: 10, index: 50, units: "ft", label_size: 6, decimals: 0, label_spacing_ft: 500, min_len_ft: 120,
        follow_line: true, upright: true, labels: true, datum: true, mask: true, halo: true },
      labels: { cat: "default", backing_layer: true, redraw_lines: true, live_reroute: true, preset: "working", qa: null,
        declutter: JSON.parse(JSON.stringify(VB.DECLUTTER_DEFAULT)),
        mask_targets: { contours: true, streets: true, buildings: true, blocks: true, water: false, fences: false, grid: true }, styles: VB.labelDefaults() },
      label_offset: JSON.parse(JSON.stringify(VB.LEADER_DEFAULT)),
      shading: { preset: "alpine_steep_calm", base_color: "#8aa066", phases: [], loaded: false, slope_smooth_ft: 12,
        muted: { saturation: 0.62, contrast: 0.86, tint: "#d9cba3", tint_strength: 0.12 },
        hillshade: { enabled: true, azimuth: 315, altitude: 40, strength: 0.36, ambient: 0.38, exaggeration: 1 } },
      water: { sea_level_ft: 0, threshold_cells: 150, outlet_width: 60, inflow: "", delta: false, meander: true, bank_ft: 12,
        use_working: false, use_carved: false, redraw: true,
        rivergen: { preset: "gentle", amplitude_ft: "", wavelength_ft: "", width_var: "", seed: "", bars: true },
        river: { name: "", width: 10, width_end: 0, depth: 1.5, flow: 8, meander: 0, join: "", carve: false },
        lake: { name: "", level: 0, depth: 8, kind: "pond", auto_level: true },
        river_path: [], lake_polygon: [], river_src: "", lake_src: "" },
      town: {
        seed: 1103, detail: 2, plazas_enabled: true, plazas_min_area_ft2: 150000, blocks: false, buildings: true, fields: true,
        max_street_grade: 0.08, max_main_grade: 0.05, max_build_slope: 0.19, max_build_relief_ft: 6, max_field_slope: 0.13,
        entry_x: 1290, entry_y: 1480, area: [], area_src: "", rings: [], params_loaded: false, candidate: false,
        redraw_contours: true, autofill: true, exportPack: false,
        fills: { full: true, style: "full_map", flat: true, dpi: 200, embed: false },
        style: { preset: "", streets: "", plazas: "", buildings: "", fields: "", water: "", stroke: "" }
      },
      foundry: { target: "new", sceneName: "", sceneUuid: "", dpi: 150, ftPerGrid: null, hideGrid: false, walls: true, drawRoads: false, drawWater: false,
        tileLayers: "Labels - Districts,Labels - Streets,Labels - Buildings", actorUuid: "", itemUuid: "", spec: "", image: "", at: "", itemName: "", itemDesc: "",
        models: { split: "", preset: "layer", layers: "", lod: 0, compress: "none", roofMode: "none", interiorStyle: "auto", splitPreset: "default", carve: true, conform: true, prune: true, roofsHidden: true, sceneMode: "3d",
          collision: { terrain: true, roads: true, plazas: true, fields: true, fences: true, walls: true, bridges: true, buildings: true, props: true, roofs: false, foliage: false, water: false },   // = foundry_collision.COLLISION_DEFAULT
          sight: { buildings: true, walls: true, foliage: true, terrain: false, roads: false, plazas: false, fields: false, fences: false, bridges: false, props: false, roofs: false, water: false },   // = foundry_collision.SIGHT_DEFAULT
          alsoWalls: false }, sizeFt: 5, autoPush: false, filter: { actors: "", items: "" }, cache: { fetched: null, lists: {} }, last: null },
      roads: { smooth: 0.5, max_grade: 14, skirt: true, cutfill: false, cross_deg: 10, grade: true },   // ROAD GRADING (generators/road_grade.py), passed to worldpack_split.py split
      stale: { contours: false, shading: false, town: false },
      ui: { tab: "scale" }
    };
  };
  // fill in keys missing from a state loaded from an older file
  VB.normalize = function (s) { return VB.deepMerge(VB.defaults(), s || {}); };

  // Placed rasters are embedded unless the Scale tab's "Link instead of embed" is on (linked PNGs under out/panel go missing when scratch files are cleaned).
  VB.embedOn = function (st) { return !((st.settings || {}).link_images); };
  VB.RENDER_FOLDERS = function (d) { return [d.panel + "/fills", d.panel + "/lighting", d.panel, d.root + "/illustrator/out"]; };
  // host step: list missing links after a build and log the result (never fails the job)
  VB.checkLinksStep = function (st, d) {
    return { t: "fn", label: "check linked images", fn: async function (run) {
      var r = await run.host({ action: "check_links" }, true);
      run.log(r && r.missing && r.missing.length ? "WARNING: " + r.missing.length + " missing link(s): " + r.missing.map(function (m) { return m.name + " -> " + m.path; }).join("; ") : "linked images: all present (" + ((r && r.total) || 0) + " linked)");
    } };
  };
  VB.jobEmbedAll = function (st, d) {
    return { kind: "embed_all", label: "Embed all linked images", params: {},
      steps: [{ t: "fn", label: "embed_all", fn: async function (run) { var r = await run.host({ action: "embed_all" }, true); run.log("embedded " + r.embedded + ", missing: " + ((r.missing || []).join(", ") || "none")); } }] };
  };
  VB.jobCheckLinks = function (st, d, relink) {
    return { kind: relink ? "relink" : "check_links", label: relink ? "Relink images" : "Check linked images", params: {},
      steps: [{ t: "fn", label: relink ? "relink" : "check_links", fn: async function (run) {
        var r = await run.host(relink ? { action: "relink", folders: VB.RENDER_FOLDERS(d), embed: VB.embedOn(st) } : { action: "check_links" }, true);
        if (relink) run.log("relinked " + ((r.relinked || []).length));
        run.log(r.missing && r.missing.length ? "missing: " + r.missing.map(function (m) { return m.name + " (" + m.layer + ") " + m.path; }).join("; ") : "no missing links (" + (r.total || 0) + " linked)");
      } }] };
  };

  // ---------------------------------------------------------------- paths
  VB.dirs = function (rootDir, place) {
    var r = rootDir.replace(/\\/g, "/").replace(/\/+$/, "");
    var panel = r + "/illustrator/out/panel/" + place;
    return {
      root: r, gen: r + "/illustrator/generators", world: r + "/world/" + place, terrain: r + "/world/" + place + "/terrain",
      panel: panel, candidate: panel + "/town_candidate", water: r + "/illustrator/out/water/" + place,
      presets: r + "/illustrator/presets", state: r + "/world/" + place + "/panel_state.json",
      patchPreview: r + "/world/" + place + "/terrain/patch_preview"
    };
  };

  // ---------------------------------------------------------------- geometry: page points <-> feet
  // view = panelio.py view output; artboard = [left, top, right, bottom] from Illustrator (y up). Points are document coords.
  VB.flatten = function (points, closed, samples) {
    samples = samples || 6;
    var out = [], n = points.length;
    var seg = function (p, q) {
      var straight = (p.r[0] === p.a[0] && p.r[1] === p.a[1]) && (q.l[0] === q.a[0] && q.l[1] === q.a[1]);
      out.push(p.a.slice());
      if (!straight) for (var i = 1; i < samples; i++) {
        var t = i / samples, u = 1 - t;
        out.push([u * u * u * p.a[0] + 3 * u * u * t * p.r[0] + 3 * u * t * t * q.l[0] + t * t * t * q.a[0],
                  u * u * u * p.a[1] + 3 * u * u * t * p.r[1] + 3 * u * t * t * q.l[1] + t * t * t * q.a[1]]);
      }
    };
    for (var i = 0; i < n - 1; i++) seg(points[i], points[i + 1]);
    if (closed && n > 1) seg(points[n - 1], points[0]); else if (n) out.push(points[n - 1].a.slice());
    return out;
  };
  VB.docToFt = function (view, artboard, pt) {
    var px = pt[0] - artboard[0], py = artboard[1] - pt[1], m = view.margin_in * 72;
    return [view.x0 + (px - m) / view.k, view.y0 + (py - m) / view.k];
  };
  VB.ftToDoc = function (view, artboard, ft) {
    var m = view.margin_in * 72;
    return [artboard[0] + m + (ft[0] - view.x0) * view.k, artboard[1] - (m + (ft[1] - view.y0) * view.k)];
  };
  VB.round1 = function (v) { return Math.round(v * 10) / 10; };
  VB.pathToFt = function (view, artboard, pathInfo) {
    return VB.flatten(pathInfo.points, pathInfo.closed).map(function (p) {
      var f = VB.docToFt(view, artboard, p); return [VB.round1(f[0]), VB.round1(f[1])];
    });
  };
  VB.polyArea = function (pts) {
    var a = 0; for (var i = 0; i < pts.length; i++) { var p = pts[i], q = pts[(i + 1) % pts.length]; a += p[0] * q[1] - q[0] * p[1]; }
    return Math.abs(a) / 2;
  };
  // page rectangle [l,t,r,b] (points from artboard top-left, y down) of a world-aligned image with bounds_ft
  VB.imageRect = function (view, b) {
    var m = view.margin_in * 72;
    return [m + (b.x_min - view.x0) * view.k, m + (b.y_min - view.y0) * view.k, m + (b.x_max - view.x0) * view.k, m + (b.y_max - view.y0) * view.k];
  };
  VB.ptsArg = function (pts) { return pts.map(function (p) { return p[0] + "," + p[1]; }).join(";"); };

  // ---------------------------------------------------------------- town params / settings merges
  VB.mergeTownParams = function (base, t) {
    var p = clone(base);
    p.seed = Number(t.seed); p.detail = Number(t.detail);
    if (t.area && t.area.length >= 3) { p.area_ft = t.area; delete p.area_file; }
    p.output = Object.assign({}, p.output, { blocks: !!t.blocks, buildings: !!t.buildings, fields: !!t.fields });
    p.limits = Object.assign({}, p.limits, { max_street_grade: +t.max_street_grade, max_main_grade: +t.max_main_grade,
      max_build_slope: +t.max_build_slope, max_build_relief_ft: +t.max_build_relief_ft, max_field_slope: +t.max_field_slope });
    p.plazas = Object.assign({}, p.plazas, { enabled: !!t.plazas_enabled, min_area_ft2: +t.plazas_min_area_ft2 });
    p.entry = Object.assign({}, p.entry, { point: [+t.entry_x, +t.entry_y] });
    if (t.rings && t.rings.length) {
      p.ring_spec = p.ring_spec || {};
      var byId = {}; (p.ring_spec.rings || []).forEach(function (r) { byId[r.id] = r; });
      p.ring_spec.rings = t.rings.map(function (r) {
        var o = Object.assign({}, byId[r.id] || {}, r);
        o.lot_area = [+r.lot_min, +r.lot_max]; delete o.lot_min; delete o.lot_max; return o;
      });
    }
    return p;
  };
  VB.ringsFromParams = function (p) {
    return ((p.ring_spec || {}).rings || []).map(function (r) {
      return { id: r.id, name: r.name, r_max: r.r_max, street_width: r.street_width, lot_min: (r.lot_area || [0, 0])[0], lot_max: (r.lot_area || [0, 0])[1] };
    });
  };
  VB.townFromParams = function (p, t) {
    t.seed = p.seed != null ? p.seed : t.seed; t.detail = p.detail != null ? p.detail : t.detail;
    var o = p.output || {}; t.blocks = !!o.blocks; t.buildings = o.buildings !== false; t.fields = o.fields !== false;
    var l = p.limits || {};
    ["max_street_grade", "max_main_grade", "max_build_slope", "max_build_relief_ft", "max_field_slope"].forEach(function (k) { if (l[k] != null) t[k] = l[k]; });
    if (p.plazas) { t.plazas_enabled = p.plazas.enabled !== false; if (p.plazas.min_area_ft2 != null) t.plazas_min_area_ft2 = p.plazas.min_area_ft2; }
    if (p.entry && p.entry.point) { t.entry_x = p.entry.point[0]; t.entry_y = p.entry.point[1]; }
    t.rings = VB.ringsFromParams(p);
    if ((!t.area || !t.area.length) && p.area_ft) { t.area = p.area_ft; t.area_src = "town_params.json"; }
    t.params_loaded = true; return t;
  };
  VB.applySpec = function (spec, s) {
    var o = clone(spec); o.seed = +s.seed; o.cell_ft = +s.cell_ft; o.base_elevation_ft = +s.base_elevation_ft;
    o.noise = Object.assign({}, o.noise, { ridged_amp_ft: +s.ridged_amp_ft, scale_ft: +s.noise_scale_ft });
    o.erosion = Object.assign({}, o.erosion, { thermal_iterations: Math.round(+s.thermal_iterations), smooth_sigma_cells: +s.smooth_sigma_cells });
    // base-map recipe keys (terrain_basemap.py; only used by specs without ridges/peaks/valleys, ignored by the others): relief 0 = automatic
    o.recipe = s.recipe || "rolling_hills";
    if (+s.relief_ft > 0) o.relief_ft = +s.relief_ft; else delete o.relief_ft;
    if (+s.image_blend > 0) o.image_blend = Math.min(1, +s.image_blend); else delete o.image_blend;
    return o;
  };
  VB.specToState = function (spec, s) {
    s.seed = spec.seed; s.cell_ft = spec.cell_ft; s.base_elevation_ft = spec.base_elevation_ft;
    var n = spec.noise || {}, e = spec.erosion || {};
    if (n.ridged_amp_ft != null) s.ridged_amp_ft = n.ridged_amp_ft;
    if (n.scale_ft != null) s.noise_scale_ft = n.scale_ft;
    if (e.thermal_iterations != null) s.thermal_iterations = e.thermal_iterations;
    if (e.smooth_sigma_cells != null) s.smooth_sigma_cells = e.smooth_sigma_cells;
    s.recipe = spec.recipe || "rolling_hills"; s.relief_ft = spec.relief_ft || 0; s.image_blend = spec.image_blend || 0;
    return s;
  };
  VB.applyViewSettings = function (raw, sc) {
    var o = clone(raw); o.presets = o.presets || {};
    var pr = o.presets[sc.preset] = Object.assign({}, o.presets[sc.preset] || {});
    pr.scale_ft_per_in = +sc.scale_ft_per_in; pr.grid_ft = +sc.grid_ft; pr.grid_major_every = Math.max(1, Math.round(+sc.grid_major_every));
    delete pr.scale_bar_ft;           // recomputed from the scale (5 paper inches of ground)
    o.page_in = [+sc.page_w_in, +sc.page_h_in]; o.units = sc.units;
    o.grid_show = sc.grid_show !== false;          // false = no grid drawn at all (guides, previews, open jobs); file level, applies to every preset
    return o;
  };
  VB.viewToState = function (raw, sc) {
    var pr = (raw.presets || {})[sc.preset];
    if (pr) { sc.scale_ft_per_in = pr.scale_ft_per_in; sc.grid_ft = pr.grid_ft; sc.grid_major_every = pr.grid_major_every || 5; }
    if (raw.page_in) { sc.page_w_in = raw.page_in[0]; sc.page_h_in = raw.page_in[1]; }
    if (raw.units) sc.units = raw.units;
    sc.grid_show = raw.grid_show !== false;
    sc.loaded = true; return sc;
  };

  // ---------------------------------------------------------------- shading phase file
  // global 'muted' control (shading.py apply_muted): saturation / contrast 0..1 (1 = unchanged), tint colour (blank = none)
  VB.mutedOf = function (sh) {
    var m = sh.muted || {}, n = function (v, d) { return v === undefined || v === "" || isNaN(+v) ? d : Math.min(1, Math.max(0, +v)); };
    return { saturation: n(m.saturation, 1), contrast: n(m.contrast, 1), tint: /^#[0-9a-fA-F]{6}$/.test(m.tint || "") ? m.tint : null, tint_strength: n(m.tint_strength, 0.12) };
  };
  VB.phaseFile = function (sh) {
    var h = sh.hillshade;
    return {
      name: "panel", base_color: sh.base_color, slope_smooth_ft: +(sh.slope_smooth_ft || 0),
      muted: VB.mutedOf(sh),
      hillshade: { enabled: !!h.enabled, azimuth: +h.azimuth, altitude: +h.altitude, strength: +h.strength, ambient: +(h.ambient === undefined || h.ambient === "" ? 0.3 : h.ambient), exaggeration: +h.exaggeration },
      phases: sh.phases.map(function (p) {
        var q = clone(p);
        ["elev_min", "elev_max"].forEach(function (k) { if (q[k] === "" || q[k] === undefined) q[k] = null; });
        q.enabled = p.enabled !== false; return q;
      })
    };
  };
  VB.texName = function (t) { return String(t || "").replace(/^.*[\/\\]/, ""); };

  // ---------------------------------------------------------------- command line pieces
  VB.srcFlags = function (st) {
    return ["--terrain-source", st.water.use_carved ? "carved" : "patched", "--water-source", st.water.use_working ? "working" : "world"];
  };
  VB.viewFlags = function (st) {
    var sc = st.scale;
    return ["--view", st.settings.view || "town", "--preset", sc.preset, "--scale", String(sc.scale_ft_per_in), "--grid", String(sc.grid_ft),
      "--grid-major", String(+sc.grid_major_every >= 1 ? Math.round(+sc.grid_major_every) : 5), "--page", sc.page_w_in + "x" + sc.page_h_in].concat(sc.grid_full_page ? ["--grid-full-page"] : []);
  };
  // panelio.py view takes --major instead of --grid-major
  VB.panelioViewFlags = function (st) {
    return VB.viewFlags(st).filter(function (x) { return x !== "--grid-full-page"; }).map(function (x) { return x === "--grid-major" ? "--major" : x; });
  };
  // label style as the JSON the generators read (default = full, categories = overrides), base64 so it survives any shell quoting
  VB.labelStyleJson = function (st) {
    var l = st.labels || {}, o = JSON.parse(JSON.stringify(l.styles || VB.labelDefaults()));
    o.backing_layer = l.backing_layer !== false;
    o.mask_targets = Object.keys(l.mask_targets || {}).filter(function (k) { return l.mask_targets[k]; });
    return o;
  };
  VB.b64 = function (str) {
    var u = unescape(encodeURIComponent(str));
    if (typeof btoa === "function") return btoa(u);
    return Buffer.from(u, "binary").toString("base64");
  };
  VB.labelStyleFlags = function (st) { return ["--label-style-b64", VB.b64(JSON.stringify(VB.labelStyleJson(st)))]; };
  VB.declutterJson = function (st) { var l = st.labels || {}; return JSON.parse(JSON.stringify(l.declutter || VB.DECLUTTER_DEFAULT)); };
  VB.labelFlags = function (st) {
    var o = st.label_offset || {}, sf = VB.labelStyleFlags(st).concat(["--declutter-b64", VB.b64(JSON.stringify(VB.declutterJson(st)))]);
    if (o.enabled === false) return ["--no-label-offset"].concat(sf);
    var lj = { color: o.color, casing: o.casing !== false, casing_color: o.casing_color, casing_width: o.casing_width, dot_ring: o.dot_ring !== false, match_text: !!o.match_text,
      dash: o.dash || "", lock_leaders: o.lock_leaders !== false };
    return sf.concat(["--label-offset", "--leader-style", o.style || "elbow", "--leader-width", String(o.stroke_width), "--label-fit-margin", String(o.margin_pct),
      "--label-max-offset", String(o.max_offset_pt), o.dot === false ? "--no-leader-dot" : "--leader-dot", "--leader-b64", VB.b64(JSON.stringify(lj))]);
  };
  // apply a preset (presets/label_presets.json entry) to the panel state: label_style layers over the current styles, leader look, declutter options
  VB.applyLabelPreset = function (st, pre) {
    var clone = function (x) { return JSON.parse(JSON.stringify(x)); };
    var L = st.labels;
    Object.keys(pre.label_style || {}).forEach(function (cat) { L.styles[cat] = Object.assign(L.styles[cat] || {}, clone(pre.label_style[cat])); });
    st.label_offset = Object.assign(st.label_offset || {}, clone(pre.label_offset || {}));
    var dc = pre.declutter || {};
    Object.keys(dc).forEach(function (k) {
      if (k === "tiers") Object.keys(dc.tiers).forEach(function (t) { L.declutter.tiers[t] = Object.assign(L.declutter.tiers[t] || {}, clone(dc.tiers[t])); });
      else L.declutter[k] = clone(dc[k]);
    });
    return st;
  };
  VB.contourFlags = function (st) {
    var c = st.contours, f = ["--contours", c.mask ? "--contour-mask" : "--no-contour-mask", "--contour-interval", String(c.minor), "--index-interval", String(c.index),
      "--label-size", String(c.label_size), "--units", c.units, "--label-decimals", String(c.decimals), "--label-spacing", String(c.label_spacing_ft),
      "--min-contour-len", String(c.min_len_ft)];
    if (!c.follow_line) f.push("--no-follow-line");
    if (!c.upright) f.push("--no-upright");
    if (!c.labels) f.push("--no-labels");
    if (!c.datum) f.push("--no-datum");
    if (c.halo === false) f.push("--no-contour-halo");
    return f;
  };

  // ---------------------------------------------------------------- job builders
  // job = {kind, label, params, steps[], setStale[], clearStale[], setState[[path,value]]}
  // step types: write {path,data}, py {script,args,json?}, host {action,optional}, fn {fn(run), when?(run)}
  var py = function (script, args, label, extra) { return Object.assign({ t: "py", script: script, args: args, label: label || script }, extra || {}); };
  var host = function (action, label, opt) { return { t: "host", action: action, label: label || action.action, optional: !!opt }; };
  var GEN = "illustrator/generators/";
  VB.steps = { py: py, host: host };

  // replace layers from an SVG, with the GUIDES parent layer unlocked and restored when guide layers are involved
  VB.replaceSteps = function (svgAbs, names, label) {
    var steps = [];
    var guides = names.some(function (n) { return GUIDE_LAYERS.indexOf(n) >= 0; });
    if (guides) steps.push(host({ action: "lock_layers", names: GUIDE_LAYERS, locked: false }, "unlock GUIDES", true));
    steps.push(host({ action: "replace_layer", path: svgAbs, names: names, restore_lock: !guides }, label || "replace layers", true));
    if (guides) steps.push(host({ action: "lock_layers", names: GUIDE_LAYERS, locked: true }, "lock GUIDES", true));
    if (names.indexOf("Label Backing") >= 0) steps.push(host({ action: "finalize_labels" }, "group labels (halo + text = one item)", true));
    return steps;
  };
  VB.fillAssignments = function (st, textures) {
    var tex = {}; (textures || []).forEach(function (t) { tex[t.name] = t.rgb; });
    EXTRA_SWATCHES.forEach(function (t) { tex[t.name] = t.rgb; });
    var hex = function (h) { var m = /^#?([0-9a-f]{6})$/i.exec(h || ""); return m ? [0, 2, 4].map(function (i) { return parseInt(m[1].substr(i, 2), 16); }) : null; };
    var out = [];
    Object.keys(VB.PARTS).forEach(function (k) {
      var part = VB.PARTS[k], choice = st.town.style[k];
      var a = { layer: part.layer, swatch: "VB " + part.label + (choice ? " - " + choice : ""), fill: choice ? (tex[choice] || null) : null };
      if (part.match) a.match = part.match;
      if (part.exclude) a.exclude = part.exclude;
      var sk = hex(st.town.style.stroke);
      if (sk) { a.stroke = sk; a.stroke_w = 0.75; }
      if (choice && !a.fill) return;      // unknown swatch name: leave the part alone
      out.push(a);
    });
    return out;
  };

  VB.jobScaleApply = function (st, d, all) {
    var svg = d.panel + "/view.svg";
    var names = all ? GEN_LAYERS : ["Grid", "Scale bar", "North arrow", "Bounds", "NOTES"];
    var args = ["--place", st.place].concat(VB.viewFlags(st), ["--out", svg], VB.srcFlags(st), VB.labelFlags(st), all ? VB.contourFlags(st) : []);
    return {
      kind: all ? "redraw_all" : "scale_apply", label: all ? "Redraw all GEN layers" : "Apply scale and regenerate guides",
      params: { scale: st.scale, view: st.settings.view },
      steps: [
        { t: "fn", label: "write view_settings.json", fn: function (run) {
          var p = d.world + "/view_settings.json", raw = run.readJson(p, {});
          run.writeJson(p, VB.applyViewSettings(raw, st.scale)); } },
        py(GEN + "render_world.py", args, "render_world (view)")
      ].concat(VB.replaceSteps(svg, names, "replace layers"), all ? VB.autoFillSteps(st, d) : []),
      setStale: all ? [] : ["contours", "shading"], clearStale: all ? ["contours"] : []
    };
  };
  VB.jobContours = function (st, d) {
    var svg = d.panel + "/contours.svg";
    return {
      kind: "contours", label: "Render contours", params: { contours: st.contours, source: VB.srcFlags(st) },
      steps: [py(GEN + "render_world.py", ["--place", st.place].concat(VB.viewFlags(st), VB.contourFlags(st), VB.labelFlags(st), VB.srcFlags(st), ["--out", svg]), "render_world --contours")]
        .concat(VB.replaceSteps(svg, CONTOUR_LAYERS, "replace contour layers")),
      clearStale: ["contours"]
    };
  };
  // re-render only the labels (text, backing, leaders) and, when asked, the linework they cut (contours, roads, buildings ...)
  VB.jobLabels = function (st, d) {
    var svg = d.panel + "/labels.svg", l = st.labels || {}, names = LABEL_LAYERS.slice();
    var cut = l.redraw_lines !== false;
    if (cut) Object.keys(LABEL_TARGETS).forEach(function (k) { names = names.concat(LABEL_TARGETS[k]); });
    var args = ["--place", st.place].concat(VB.viewFlags(st), VB.labelFlags(st), VB.srcFlags(st), VB.contourFlags(st), ["--out", svg]);
    return {
      kind: "labels", label: "Redraw labels", params: { labels: st.labels, offset: st.label_offset },
      steps: [py(GEN + "render_world.py", args, "render_world (labels)")].concat(VB.replaceSteps(svg, names, "replace label layers"), VB.labelAfterSteps(st, d))
    };
  };
  // after labels are drawn: the hidden-labels sublayer stays hidden, leaders locked unless asked otherwise, QA numbers read back
  VB.labelAfterSteps = function (st, d) {
    return [host({ action: "set_visible", names: ["Labels - Hidden"], visible: false }, "hide the hidden-labels sublayer", true),
      host({ action: "lock_leaders", locked: (st.label_offset || {}).lock_leaders !== false }, "leaders layer lock", true),
      { t: "fn", label: "label QA", fn: async function (run) {
        var f = d.panel + "/label_manifest.json", m = run.readJson ? run.readJson(f) : null;
        if (m && m.qa) { run.setState("labels.qa", m.qa); run.log("Label QA: " + m.qa.labels_shown + " shown, " + m.qa.labels_hidden + " hidden, " + m.qa.numbered + " numbered; text over features " + m.qa.text_over_features_pct + "%, overlaps " + m.qa.label_label_overlaps); }
      } }];
  };
  // re-route every leader to its (moved) label. only_changed = the live poll. Style options come from the Labels tab.
  VB.rerouteAction = function (st, only_changed) {
    var o = st.label_offset || {};
    return { action: "reroute_leaders", changed_only: !!only_changed, group: true, style: { style: o.style || "elbow", color: o.match_text ? undefined : o.color, casing_color: o.casing_color,
      width: o.stroke_width, casing_width: o.casing_width } };
  };
  VB.jobReroute = function (st, d) {
    return { kind: "labels_reroute", label: "Re-route leaders", params: {}, steps: [host(VB.rerouteAction(st, false), "re-route leaders")] };
  };
  // write the labels the user moved (and moved anchor dots) into world/<place>/label_overrides.json, so regeneration keeps them
  VB.jobPinLabels = function (st, d) {
    var pos = d.panel + "/label_positions.json";
    return { kind: "labels_pin", label: "Pin label positions", params: {},
      steps: [host(VB.rerouteAction(st, false), "re-route + sync backing"), host({ action: "read_label_positions" }, "read label positions"),
        { t: "fn", label: "write positions", fn: async function (run) { await run.writeJson(pos, { labels: (run.last && run.last.labels) || [] }); } },
        py(GEN + "label_declutter.py", ["pin", "--place", st.place, "--positions", pos, "--manifest", d.panel + "/label_manifest.json"], "pin label positions", { json: "pinned" }),
        { t: "fn", label: "report", fn: async function (run) { var r = run.vars.pinned || {}; run.log("pinned " + r.pinned + " label(s) (" + (r.anchors || 0) + " anchors) -> label_overrides.json; " + r.total + " in total. Redraw labels to regenerate with them."); } }]
    };
  };
  VB.jobClearOverrides = function (st, d, ids) {
    return { kind: "labels_clear_overrides", label: "Clear pinned label positions", params: { ids: ids || [] },
      steps: [py(GEN + "label_declutter.py", ["clear", "--place", st.place].concat(ids && ids.length ? ["--ids", ids.join(",")] : []), "clear overrides", { json: "cleared" })] };
  };
  VB.jobTerrainGenerate = function (st, d) {
    return {
      kind: "terrain_generate", label: "Generate base terrain", params: { spec: st.terrain.spec },
      steps: [
        { t: "fn", label: "write terrain_spec.json", fn: function (run) {
          var p = d.world + "/terrain_spec.json"; run.writeJson(p, VB.applySpec(run.readJson(p, {}), st.terrain.spec)); } },
        py(GEN + "terrain.py", ["--place", st.place], "terrain.py"),
        py(GEN + "terrain_patch.py", ["rebuild", "--place", st.place], "replay patches onto the new base",
          { when: function (run) { return run.exists(d.terrain + "/patches.json"); } })
      ],
      setStale: ["contours", "shading", "town"]
    };
  };
  // capture the selected path -> state value. opts: {what, layer, closed, open, store, srcName}
  var LS = function () { return root.VBLasso || (typeof require !== "undefined" ? (function () { try { return require("./lasso.js"); } catch (e) { return null; } })() : null); };
  VB.jobCapture = function (st, d, opts) {
    return {
      kind: "capture_" + opts.store.replace(/\./g, "_"), label: "Capture " + opts.what, params: { opts: opts, view: st.settings.view },
      steps: [
        py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        host(LS() ? { action: "get_selection", layer: opts.layer, lasso: true } : { action: "get_selection", layer: opts.layer, closed_only: !!opts.closed, open_only: !!opts.open }, "read selection"),
        { t: "fn", label: "convert to feet", fn: function (run) {
          var sel = run.last, view = run.vars.view, lasso = LS(), pts, path, note;
          if (lasso) {   // lib/lasso.js: closed / open / anchor / lasso-layer selections, simplified, repaired, with notes
            var r = lasso.fromSelection(view, sel, { closed: !!opts.closed, open: !!opts.open });
            if (!r.ok) throw new Error(r.error);
            pts = r.pts; note = r.note; (r.warnings || []).forEach(function (w) { run.log("note: " + w); });
            path = { name: note }; run.vars.captured = { pts: pts, closed: !!opts.closed, via: r.via, ab: sel.artboard };
          } else { path = sel.paths[0]; pts = VB.pathToFt(view, sel.artboard, path);
            if (opts.closed && pts.length > 1 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1]) pts.pop();
            run.vars.captured = { pts: pts, closed: !!opts.closed }; }
          run.setState(opts.store, pts);
          if (opts.srcName) run.setState(opts.srcName, sel.source + " (" + (path.name || "unnamed") + ", " + pts.length + " pts" +
            (opts.closed ? ", " + Math.round(VB.polyArea(pts)) + " ft2" : "") + ")");
          run.log((lasso && opts.closed ? "polygon: " + lasso.describe(lasso.stats(pts)) + " (" + note + ")" : pts.length + " points from " + sel.source) + (sel.paths.length > 1 && !lasso ? " (first of " + sel.paths.length + " paths)" : "")); } },
        // leave the captured shape selected in Illustrator on the VB LASSO layer (Photoshop-style); never fails the capture
        { t: "host", label: "show lasso in Illustrator", optional: true,
          when: function (run) { var c = run.vars.captured; return !!(c && c.closed && c.ab && LS()); },
          action: function (run) { var c = run.vars.captured; return { action: "lasso_draw", select: true, rings: [{ role: "core", pts: c.pts.map(function (p) { return VB.ftToDoc(run.vars.view, c.ab, p); }) }] }; } }
      ]
    };
  };
  VB.patchParams = function (p) {
    var o = { terrain_type: p.terrain_type, avg_height_ft: +p.avg_height_ft, steepness: +p.steepness, feather_ft: +p.feather_ft,
      roughness: +p.roughness, seed: Math.round(+p.seed), angle_deg: +p.angle_deg };
    if (VB.DEPRESS.indexOf(p.terrain_type) >= 0) o.min_height_ft = +p.min_height_ft; else o.max_height_ft = +p.max_height_ft;
    return o;
  };
  VB.jobPatch = function (st, d, mode) { // preview | apply
    var p = st.terrain.patch, pol = d.panel + "/patch_polygon.json", par = d.panel + "/patch_params.json";
    var params = VB.patchParams(p);
    return {
      kind: "patch_" + mode, label: (mode === "apply" ? "Apply" : "Preview") + " terrain patch",
      params: { params: params, polygon: p.polygon },
      steps: [
        { t: "fn", label: "check polygon", fn: function () { if (!p.polygon || p.polygon.length < 3) throw new Error("no polygon: select a closed path (or draw on a TERRAIN AREA layer) and press Capture polygon"); } },
        { t: "write", path: pol, data: p.polygon, label: "polygon.json" },
        { t: "write", path: par, data: params, label: "params.json" },
        py(GEN + "terrain_patch.py", [mode, "--place", st.place, "--polygon", pol, "--params", par], "terrain_patch " + mode)
      ],
      setStale: mode === "apply" ? ["contours", "shading", "town"] : []
    };
  };
  VB.jobPatchCmd = function (st, d, cmd, extra) {
    return { kind: "patch_" + cmd, label: "Terrain patch: " + cmd, params: { cmd: cmd, extra: extra || [] },
      steps: [py(GEN + "terrain_patch.py", [cmd, "--place", st.place].concat(extra || []), "terrain_patch " + cmd)], setStale: ["contours", "shading", "town"] };
  };
  VB.jobShading = function (st, d) {
    var phases = d.panel + "/phases.json", png = d.panel + "/shading.png", h = st.shading.hillshade;
    var args = ["--place", st.place, "--phases", phases, "--scale-ft-per-in", String(st.scale.scale_ft_per_in), "--dpi", String(st.settings.dpi), "--out", png,
      "--terrain-source", st.water.use_carved ? "carved" : "patched"];
    if (h.enabled) args = args.concat(["--hillshade", "--azimuth", String(h.azimuth), "--altitude", String(h.altitude), "--strength", String(h.strength), "--ambient", String(h.ambient === undefined || h.ambient === "" ? 0.3 : h.ambient), "--exaggeration", String(h.exaggeration)]);
    else args.push("--no-hillshade");
    return {
      kind: "shading", label: "Render shading", params: { shading: st.shading, scale: st.scale.scale_ft_per_in, dpi: st.settings.dpi },
      steps: [
        { t: "write", path: phases, data: VB.phaseFile(st.shading), label: "phases.json" },
        py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
        py(GEN + "shading.py", args, "shading.py"),
        { t: "fn", label: "place PNG", fn: function (run) {
          var side = run.readJson(png.replace(/\.png$/, ".json"), null);
          if (!side) throw new Error("shading sidecar .json missing");
          return run.host({ action: "place_image", path: png, rect: VB.imageRect(run.vars.view, side.bounds_ft), layer: "ART - Shading", below: VB.fillBelow("ART - Shading"), name: "shading_png", lock: true, embed: VB.embedOn(st) }, true);
        } }
      ],
      clearStale: ["shading"]
    };
  };
  VB.waterBase = function (st) { return ["--place", st.place]; };
  VB.waterRedraw = function (st, d) {
    if (!st.water.redraw) return [];
    var svg = d.panel + "/water.svg";
    return [py(GEN + "render_world.py", ["--place", st.place].concat(VB.viewFlags(st), ["--out", svg], VB.srcFlags(st), VB.labelFlags(st)), "render_world (water)")]
      .concat(VB.replaceSteps(svg, ["Water"], "replace Water layer"), VB.autoFillSteps(st, d));
  };
  VB.jobWaterAnalyze = function (st, d) {
    var w = st.water, a = ["analyze"].concat(VB.waterBase(st), ["--threshold-cells", String(w.threshold_cells), "--sea-level", String(w.sea_level_ft)]);
    if (+w.outlet_width > 0) a.push("--outlet-width", String(w.outlet_width));
    String(w.inflow || "").split(/[\n;]+/).map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (s) { a.push("--inflow", s); });
    if (w.delta) a.push("--delta");
    if (!w.meander) a.push("--no-meander");
    return { kind: "water_analyze", label: "Derive rivers (analyze)", params: { water: w },
      steps: [py(GEN + "water.py", a, "water analyze")].concat(VB.waterRedraw(st, d)), setStale: ["contours", "shading", "town"] };
  };
  VB.jobWaterRiver = function (st, d) {
    var r = st.water.river;
    var a = ["add-river"].concat(VB.waterBase(st), ["--points", VB.ptsArg(st.water.river_path), "--width", String(r.width), "--depth", String(r.depth), "--flow", String(r.flow)],
      +r.width_end > 0 ? ["--width-end", String(r.width_end)] : [], r.name ? ["--name", r.name] : [], r.join ? ["--join", r.join] : [],
      +r.meander > 0 ? ["--meander", String(r.meander)] : [], r.carve ? ["--carve"] : []);
    return { kind: "water_add_river", label: "Add river", params: { river: r, points: st.water.river_path },
      steps: [
        { t: "fn", label: "check path", fn: function () { if (!st.water.river_path || st.water.river_path.length < 2) throw new Error("no river path: select an open path (or draw on a WATER DRAW layer) and press Capture path"); } },
        py(GEN + "water.py", a, "water add-river")
      ].concat(VB.waterRedraw(st, d)), setStale: ["contours", "shading", "town"] };
  };
  VB.jobWaterLake = function (st, d) {
    var l = st.water.lake;
    var a = ["add-lake"].concat(VB.waterBase(st), ["--polygon", VB.ptsArg(st.water.lake_polygon), "--depth", String(l.depth), "--kind", l.kind],
      l.auto_level ? [] : ["--level", String(l.level)], l.name ? ["--name", l.name] : []);
    return { kind: "water_add_lake", label: "Add lake", params: { lake: l, polygon: st.water.lake_polygon },
      steps: [
        { t: "fn", label: "check polygon", fn: function () { if (!st.water.lake_polygon || st.water.lake_polygon.length < 3) throw new Error("no lake polygon: select a closed path (or draw on a WATER DRAW layer) and press Capture polygon"); } },
        py(GEN + "water.py", a, "water add-lake")
      ].concat(VB.waterRedraw(st, d)), setStale: ["contours", "shading", "town"] };
  };
  // regenerate the river meander (spec -> terrain -> water.json); town is re-run separately from the Town tab.
  // Bridgehollow keeps its own script; every other place goes through place_create.py regen (same flags).
  VB.jobRiverMeander = function (st, d) {
    var g = st.water.rivergen, a = (st.place === "bridgehollow" ? ["world/gen_bridgehollow.py"] : [GEN + "place_create.py", "regen", "--place", st.place]).concat(["--terrain", "--no-town", "--meander", g.preset || "gentle"]);
    [["amplitude_ft", "--meander-amplitude"], ["wavelength_ft", "--meander-wavelength"], ["width_var", "--width-var"], ["seed", "--meander-seed"]].forEach(function (k) {
      if (g[k[0]] !== "" && g[k[0]] != null) a.push(k[1], String(g[k[0]]));
    });
    if (g.bars === false) a.push("--no-bars");
    return { kind: "water_river_meander", label: "Regenerate river meander", params: { rivergen: g },
      steps: [py(a[0], a.slice(1), "river meander + terrain")].concat(VB.waterRedraw(st, d)), setStale: ["contours", "shading", "town"] };
  };
  VB.jobWaterCarve = function (st, d) {
    return { kind: "water_carve", label: "Carve rivers into heightmap", params: { bank_ft: st.water.bank_ft },
      steps: [py(GEN + "water.py", ["carve"].concat(VB.waterBase(st), ["--bank-ft", String(st.water.bank_ft)]), "water carve")], setStale: ["contours", "shading", "town"] };
  };
  VB.jobWaterCrossings = function (st, d) {
    return { kind: "water_crossings", label: "Bridges report", params: {},
      steps: [py(GEN + "water.py", ["crossings"].concat(VB.waterBase(st)), "water crossings")] };
  };
  // ---------------------------------------------------------------- textured 'full map' fills (fills_raster.py)
  // Stacking order of the raster layers, bottom to top; each is placed directly beneath the first existing layer above it, else beneath LINES.
  VB.FILL_ORDER = ["ART - Shading", "ART - Fill Shapes", "ART - Fill Fields", "ART - Fill Water", "ART - Fill Streets", "ART - Fill Buildings"];
  VB.FILL_SHAPES = "ART - Fill Shapes";
  VB.fillBelow = function (name) {
    var i = VB.FILL_ORDER.indexOf(name);
    return (i < 0 ? [] : VB.FILL_ORDER.slice(i + 1)).concat(["LINES"]);
  };
  VB.fillsOn = function (st) { var f = (st.town || {}).fills; return !!(f && f.full); };
  // steps: py panelio view, py fills_raster, place each PNG below LINES, flat swatch copies. opts {modelDir}
  VB.fullFillSteps = function (st, d, opts) {
    opts = opts || {}; var f = st.town.fills, out = d.panel + "/fills", style = f.style || "full_map";
    var args = ["--place", st.place].concat(VB.viewFlags(st), ["--out-dir", out, "--style", style, "--dpi", String(f.dpi || 200)], VB.srcFlags(st));
    if (opts.modelDir) args.push("--model-dir", opts.modelDir);
    return [
      py(GEN + "panelio.py", ["view", "--place", st.place].concat(VB.panelioViewFlags(st)), "page <-> feet mapping", { json: "view" }),
      py(GEN + "fills_raster.py", args, "fills_raster (" + style + ")"),
      { t: "fn", label: "place fill layers", fn: async function (run) {
        var info = run.readJson(out + "/fills.json"), rect = VB.imageRect(run.vars.view, info.bounds_ft);
        for (var i = 0; i < info.layers.length; i++) {
          var L = info.layers[i];
          await run.host({ action: "place_image", path: out + "/" + L.png, rect: rect, layer: L.layer, below: VB.fillBelow(L.layer), name: L.name, lock: true, embed: VB.embedOn(st) }, true);
        }
        if (f.flat !== false) {
          var as = info.flat.map(function (g) {
            return { layer: g.layer, ids: g.ids, swatch: g.swatch, fill: g.rgb, copy_to: VB.FILL_SHAPES, copy_below: VB.fillBelow(VB.FILL_SHAPES) };
          });
          await run.host({ action: "apply_fills", clear: [VB.FILL_SHAPES], assignments: as }, true);
        }
        run.log("fills: " + info.layers.length + " raster layers, " + info.flat.length + " flat swatch groups");
      } },
      VB.checkLinksStep(st, d)
    ];
  };
  // fills after a drawing job: textured full map when on (needs a style with a 'types' map), else the flat per-part swatches
  VB.autoFillSteps = function (st, d, opts) {
    if (!st.town.autofill) return [];
    if (VB.fillsOn(st)) return VB.fullFillSteps(st, d, opts);
    return [{ t: "fn", label: "fills", fn: function (run) { return VB.fillStep(st, run); } }];
  };
  VB.fillStep = function (st, run) {
    var as = VB.fillAssignments(st, run.textures);
    if (!as.length) { run.log("fills: nothing chosen"); return null; }
    return run.host({ action: "apply_fills", assignments: as }, true);
  };
  VB.jobTown = function (st, d) {
    var params = d.panel + "/town_params_run.json", svg = d.panel + "/town_candidate.svg", t = st.town;
    var names = TOWN_LAYERS.concat(t.redraw_contours ? CONTOUR_LAYERS : []);
    var rargs = ["--place", st.place].concat(VB.viewFlags(st), ["--model-dir", d.candidate, "--out", svg], VB.srcFlags(st), VB.labelFlags(st), t.redraw_contours ? VB.contourFlags(st) : []);
    return {
      kind: "town_generate", label: "Generate town (candidate)", params: { town: t },
      steps: [
        { t: "fn", label: "check area", fn: function () { if (!t.area || t.area.length < 3) throw new Error("no lasso area: select a closed path (or draw on a TOWN AREA layer) and press Capture lasso"); } },
        { t: "fn", label: "write run params", fn: function (run) {
          var base = run.readJson(d.world + "/town_params.json", {});
          var p = VB.mergeTownParams(base, t); p.place = st.place;
          p.view_preset = st.scale.preset; p.scale_ft_per_in = +st.scale.scale_ft_per_in;
          run.writeJson(params, p); } },
        py(GEN + "town_gen.py", ["--place", st.place, "--params", params, "--out-dir", d.candidate].concat(VB.srcFlags(st)), "town_gen.py (candidate)"),
        py(GEN + "render_world.py", rargs, "render_world (candidate)")
      ].concat(VB.replaceSteps(svg, names, "draw candidate"), VB.autoFillSteps(st, d, { modelDir: d.candidate })),
      setState: [["town.candidate", true]], clearStale: ["town"]
    };
  };
  VB.jobFullFills = function (st, d) {
    return { kind: "fills_render", label: "Render map with fills", params: { fills: st.town.fills },
      steps: VB.fullFillSteps(st, d, { modelDir: st.town.candidate ? d.candidate : null }) };
  };
  VB.jobFills = function (st, d) {
    return { kind: "town_fills", label: "Apply fills", params: { style: st.town.style },
      steps: [{ t: "fn", label: "apply_fills", fn: function (run) { return VB.fillStep(st, run); } }] };
  };
  VB.jobTownAccept = function (st, d) {
    return { kind: "town_accept", label: "Accept town", params: {}, steps: [py(GEN + "panelio.py", ["town-accept", "--place", st.place], "town-accept")]
        .concat(st.town.exportPack ? [py(GEN + "worldpack.py", ["export", "--place", st.place], "world pack export")] : []),
      setState: [["town.candidate", false]], setStale: ["contours"] };
  };
  VB.jobTownReject = function (st, d) {
    var svg = d.panel + "/town_restore.svg", names = TOWN_LAYERS.concat(st.town.redraw_contours ? CONTOUR_LAYERS : []);
    return { kind: "town_reject", label: "Reject town (restore previous)", params: {},
      steps: [py(GEN + "panelio.py", ["town-reject", "--place", st.place], "town-reject"),
        py(GEN + "render_world.py", ["--place", st.place].concat(VB.viewFlags(st), ["--out", svg], VB.srcFlags(st), VB.labelFlags(st), st.town.redraw_contours ? VB.contourFlags(st) : []), "render_world (previous model)")]
        .concat(VB.replaceSteps(svg, names, "restore previous"), VB.autoFillSteps(st, d)),
      setState: [["town.candidate", false]] };
  };
  VB.jobLayers = function (act, st) {
    var m = {
      group_labels: host({ action: "finalize_labels" }, "group labels"),
      lock_leaders: host({ action: "lock_leaders", locked: true }, "lock leaders"),
      unlock_leaders: host({ action: "lock_leaders", locked: false }, "unlock leaders"),
      lock_guides: host({ action: "lock_layers", names: GUIDE_LAYERS, locked: true }, "lock GUIDES"),
      unlock_guides: host({ action: "lock_layers", names: GUIDE_LAYERS, locked: false }, "unlock GUIDES"),
      show_labels: host({ action: "set_visible", names: ["LABELS"], visible: true }, "show LABELS"),
      hide_labels: host({ action: "set_visible", names: ["LABELS"], visible: false }, "hide LABELS")
    };
    return { kind: "layers_" + act, label: act.replace("_", " "), params: {}, steps: [m[act]] };
  };

  // ---------------------------------------------------------------- world pack for the 3D pipeline (worldpack.py, worldpack_split.py, foundry_push.py push-models)
  VB.packDir = function (d) { return d.world + "/export"; };
  // Roof mode (generators/worldpack_roofs.py): none = roofs merged into each building; per_building = one hideable roof tile per building; per_scene = one roof tile for the whole scene.
  VB.ROOF_MODES = ["none", "per_building", "per_scene"];
  VB.roofMode = function (st) { var m = st && st.foundry && st.foundry.models && st.foundry.models.roofMode; return VB.ROOF_MODES.indexOf(m) >= 0 ? m : "none"; };
  // Home interior style (generators/interior_styles.py, presets/interiors/presets.json): auto = by building kind (houses rustic_cottage, farmhouse, townhouses burgher_townhouse,
  // tenements poor_hovel, everything else plain); a building JSON key interior_style overrides it per building.
  VB.INTERIOR_STYLES = ["auto", "plain", "rustic_cottage", "farmhouse", "burgher_townhouse", "poor_hovel"];
  VB.interiorStyle = function (st) { var m = st && st.foundry && st.foundry.models && st.foundry.models.interiorStyle; return VB.INTERIOR_STYLES.indexOf(m) >= 0 ? m : "auto"; };
  VB.jobWorldPack = function (st, d, out) {
    return { kind: "worldpack_export", label: "Export world pack (3D)", params: { out: out || null, roof_mode: VB.roofMode(st), interior_style: VB.interiorStyle(st) },
      steps: [py(GEN + "worldpack.py", ["export", "--place", st.place].concat(out ? ["--out", out] : []).concat(["--roof-mode", VB.roofMode(st), "--interior-style", VB.interiorStyle(st)], (VB.extraArgs ? VB.extraArgs(st, "worldpack-export") : [])), "world pack export")] };
  };
  VB.jobWorldSplit = function (st, d, pack) {
    var m = st.foundry.models, a = ["split", "--place", st.place, "--pack", pack || VB.packDir(d), "--roof-mode", VB.roofMode(st), "--interior-style", VB.interiorStyle(st)]; if (m.split) a.push("--split", m.split);
    var rd = st.roads || {}; a.push("--road-smooth", String(isFinite(+rd.smooth) ? Math.min(1, Math.max(0, +rd.smooth)) : 0.5), "--road-max-grade", String(+rd.max_grade > 0 ? Math.min(60, Math.max(1, +rd.max_grade)) : 14));
    if (rd.skirt === false) a.push("--no-road-skirt"); if (rd.cutfill) a.push("--road-cutfill");
    if (isFinite(+rd.cross_deg) && +rd.cross_deg !== 10 && rd.cross_deg !== "") a.push("--road-cross-deg", String(Math.min(45, Math.max(0, +rd.cross_deg))));
    if (rd.grade === false) a.push("--road-grade", "off");
    if (m.splitPreset && m.splitPreset !== "default") a.push("--split-preset", m.splitPreset);
    if (m.carve === false) a.push("--no-carve");
    if (m.conform === false) a.push("--no-conform");
    a = a.concat((VB.extraArgs ? VB.extraArgs(st, "worldpack-split") : []));   // TOOLS TAB: --textures, --step
    return { kind: "worldpack_split", label: "Export split models", params: { split: m.split, roads: rd, roof_mode: VB.roofMode(st), interior_style: VB.interiorStyle(st) }, steps: [py(GEN + "worldpack_split.py", a, "split models")] };
  };
  VB.jobWorldMerge = function (st, d, pack) {
    var m = st.foundry.models;
    return { kind: "worldpack_merge", label: "Merge/compress (" + m.preset + ")", params: { preset: m.preset },
      steps: [py(GEN + "worldpack_split.py", ["merge", "--place", st.place, "--pack", pack || VB.packDir(d), "--preset", m.preset, "--compress", m.compress || "none"].concat((VB.extraArgs ? VB.extraArgs(st, "worldpack-merge") : [])), "merge models")] };
  };
  // push-models argument list (target scene as in the scene push: new by name, or the picked existing one); o = { dry, placements }
  VB.worldPushArgs = function (st, d, o) {
    o = o || {}; var f = st.foundry, m = f.models, a = ["push-models", "--place", st.place, "--placements", o.placements || (VB.packDir(d) + "/placements.json")];
    if (f.target === "existing") { if (!f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)"); a.push("--scene-uuid", f.sceneUuid); }
    else { if (!String(f.sceneName || "").trim()) throw new Error("type a name for the new scene"); a.push("--scene-name", String(f.sceneName).trim()); }
    if (m.layers) a.push("--layers", m.layers);
    if (+m.lod) a.push("--lod", String(+m.lod));
    if (m.prune) a.push("--prune");
    if (m.roofsHidden && VB.roofMode(st) !== "none") a.push("--roofs-hidden");
    if (m.sceneMode === "flat" || m.sceneMode === "3d") a.push("--scene-mode", m.sceneMode);
    if (m.compress === "quant") a.push("--allow-quantized");
    var cs = VB.collisionSpec(m); if (cs) a.push("--collision", cs);
    var ss = VB.sightSpec(m); if (ss) a.push("--sight", ss);
    a = a.concat((VB.extraArgs ? VB.extraArgs(st, "push-models") : []));   // TOOLS TAB: advanced push options
    if (o.dry) a.push("--dry-run");
    return a;
  };
  // Collision tile flag per layer (foundry_collision.py): "" = the tool default, else the explicit list of layers (or "none")
  VB.COLLISION_LAYERS = ["terrain", "roads", "plazas", "fields", "fences", "walls", "bridges", "buildings", "props", "roofs", "foliage", "water"];
  VB.collisionSpec = function (m) {
    var on = VB.COLLISION_LAYERS.filter(function (k) { return (m.collision || {})[k]; }), def = VB.defaults().foundry.models.collision;
    if (VB.COLLISION_LAYERS.every(function (k) { return !!(m.collision || {})[k] === !!def[k]; })) return "";
    return on.length ? on.join(",") : "none";
  };
  // Sight tile flag per layer (blocks token vision, light and sound polygons; foundry_collision.SIGHT_DEFAULT): "" = the tool default
  VB.sightSpec = function (m) {
    var s = m.sight || {}, def = VB.defaults().foundry.models.sight, on = VB.COLLISION_LAYERS.filter(function (k) { return s[k]; });
    if (VB.COLLISION_LAYERS.every(function (k) { return !!s[k] === !!def[k]; })) return "";
    return on.length ? on.join(",") : "none";
  };
  // Foundry wall documents are an opt-in fallback (clients with multithreading off, flat scenes): buildings + town walls when ticked, else none (removes the pipeline's walls)
  VB.wallLayers = function (m) { return m.alsoWalls ? "buildings,walls" : "none"; };
  // set-collision / push-walls on the picked existing scene; apply = false gives the dry run (the commands write only with --apply)
  VB.jobSetCollision = function (st, apply) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    var a = ["set-collision", "--scene-uuid", f.sceneUuid], cs = VB.collisionSpec(f.models), ss = VB.sightSpec(f.models); if (cs) a.push("--collision", cs); if (ss) a.push("--sight", ss); a = a.concat((VB.extraArgs ? VB.extraArgs(st, "set-collision") : [])); if (apply) a.push("--apply");
    return { kind: "set_collision", label: "Set collision on scene tiles" + (apply ? "" : " (dry run)"), params: { apply: !!apply }, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", a, "set collision")] };
  };
  VB.jobInstallDoorSync = function () {
    return { kind: "door_sync_macro", label: "Install Door sync macro", params: {}, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["install-door-sync"], "install door sync")] };
  };
  VB.jobInstallSignMaker = function () {
    return { kind: "sign_maker_macro", label: "Install Sign maker macro", params: {}, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["install-sign-macro"], "install sign maker")] };
  };
  VB.jobSyncDoors = function (st, apply) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    var a = ["sync-doors", "--scene-uuid", f.sceneUuid]; if (apply) a.push("--apply");
    return { kind: "sync_doors", label: "Sync wall doors with model doors" + (apply ? "" : " (dry run)"), params: { apply: !!apply }, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", a, "sync doors")] };
  };
  VB.jobPushWalls = function (st, apply) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    var a = ["push-walls", "--place", st.place, "--scene-uuid", f.sceneUuid, "--wall-layers", VB.wallLayers(f.models)].concat((VB.extraArgs ? VB.extraArgs(st, "push-walls") : [])); if (apply) a.push("--apply");
    return { kind: "push_walls", label: (st.foundry.models.alsoWalls ? "Push Foundry walls (fallback)" : "Remove Foundry walls") + (apply ? "" : " (dry run)"), params: { apply: !!apply }, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", a, "push walls")] };
  };
  VB.jobWorldPush = function (st, d, o) {
    return { kind: "worldpack_push", label: "Push models", params: {}, steps: [py("illustrator/generators/foundry_push.py", VB.worldPushArgs(st, d, o), "push models")] };
  };
  // Roof toggle helpers (foundry_push.py install-roof-macros / roofs): macros in the world, or hide/show every roof tile of the target scene from the panel.
  VB.jobRoofMacros = function () {
    return { kind: "roof_macros", label: "Install roof macros", params: {}, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["install-roof-macros"], "install roof macros")] };
  };
  VB.jobClickMacros = function () {
    return { kind: "click_macros", label: "Install click macros", params: {}, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["install-click-macros"], "install click macros")] };
  };
  VB.jobRoofs = function (st, state) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    return { kind: "roofs_" + state, label: "Roofs: " + state, params: { state: state },
      steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["roofs", "--scene-uuid", f.sceneUuid, "--roof-state", state], "roofs " + state)] };
  };
  // read-only: duplicate / stale pipeline tiles on the target scene against the placements (foundry_push.py scene-audit)
  VB.jobSceneAudit = function (st, d) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    return { kind: "scene_audit", label: "Audit scene tiles (read-only)", params: {}, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", ["scene-audit", "--scene-uuid", f.sceneUuid, "--placements", VB.packDir(d) + "/placements.json"], "scene audit")] };
  };
  VB.jobPushLights = function (st, d, dry) {
    var f = st.foundry; if (f.target !== "existing" || !f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)");
    var a = ["push-lights", "--place", st.place, "--scene-uuid", f.sceneUuid, "--placements", VB.packDir(d) + "/placements.json"].concat((VB.extraArgs ? VB.extraArgs(st, "push-lights") : [])); if (dry) a.push("--dry-run");
    return { kind: "push_lights", label: "Push interior lights" + (dry ? " (dry run)" : ""), params: { dry: !!dry }, steps: [py(VB.FOUNDRY_PY || "illustrator/generators/foundry_push.py", a, "push lights")] };
  };
  VB.jobWorldPublish = function (st, d) {
    var f = st.foundry, m = f.models, a = ["publish", "--place", st.place, "--pack", VB.packDir(d), "--preset", m.preset, "--compress", m.compress || "none", "--lod", String(+m.lod || 0)];
    if (f.target === "existing") { if (!f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)"); a.push("--scene-uuid", f.sceneUuid); }
    else { if (!String(f.sceneName || "").trim()) throw new Error("type a name for the new scene"); a.push("--scene-name", String(f.sceneName).trim()); }
    if (VB.extraArgs) a = a.concat(VB.extraArgs(st, "publish"));   // TOOLS TAB: --yes
    return { kind: "worldpack_publish", label: "Publish models (merge + push)", params: { preset: m.preset }, steps: [py(GEN + "worldpack_split.py", a, "merge + push models")] };
  };

  // ---------------------------------------------------------------- Foundry push (everything runs in illustrator/generators/foundry_push.py)
  VB.FOUNDRY_PY = "illustrator/generators/foundry_push.py";
  VB.foundryOut = function (d, name) { return d.root + "/illustrator/out/foundry/" + d.world.replace(/^.*\//, "") + "/" + name; };
  VB.foundryDrawings = function (f) {
    var k = []; if (f.drawRoads) k.push("roads"); if (f.drawWater) k.push("water");
    return k.join(",");
  };
  VB.foundryTileLayers = function (f) {
    return String(f.tileLayers || "").split(",").map(function (x) { return x.trim(); }).filter(Boolean);
  };
  // push-scene argument list. o = { image, tileImage, uuid (existing scene) }; target "new" uses the name field, "existing" the picked uuid.
  VB.foundryPushSceneArgs = function (st, o) {
    var f = st.foundry, a = ["push-scene", "--place", st.place].concat(VB.viewFlags(st), ["--image", o.image]);
    if (f.target === "existing") { if (!f.sceneUuid) throw new Error("pick an existing scene (Refresh from Foundry first)"); a.push("--scene-uuid", f.sceneUuid); }
    else { if (!String(f.sceneName || "").trim()) throw new Error("type a name for the new scene"); a.push("--scene-name", String(f.sceneName).trim()); }
    a.push(f.walls ? "--walls" : "--no-walls");
    var dr = VB.foundryDrawings(f); a.push("--drawings", dr);
    if (f.ftPerGrid) a.push("--ft-per-grid", String(f.ftPerGrid));
    if (f.hideGrid) a.push("--hide-grid");
    if (o.tileImage) a.push("--tile-image", o.tileImage, "--tile-id", "labels");
    return a.concat((VB.extraArgs ? VB.extraArgs(st, "push-scene") : []));   // TOOLS TAB: --upscale --padding --max-px --format --link
  };
  // Name of the scene a push goes to: the picked existing scene (name from the cached list), or the new scene's name.
  VB.foundryPushTarget = function (st) {
    var f = st.foundry;
    if (f.target === "existing") {
      var row = (((f.cache || {}).lists || {}).scenes || []).filter(function (r) { return r.uuid === f.sceneUuid; })[0];
      return { mode: "existing", name: row ? row.name : (f.sceneUuid || "(no scene picked)"), uuid: f.sceneUuid || "" };
    }
    return { mode: "new", name: String(f.sceneName || "").trim() || "(no name)", uuid: "" };
  };
  // Lines for the in-panel confirmation before Push scene / Push tiles writes to Foundry.
  VB.foundryPushConfirmLines = function (st, withTiles) {
    var t = VB.foundryPushTarget(st);
    return ["This WRITES to Foundry" + (t.mode === "existing" ? " and changes the existing scene" : " and creates a new scene") + ".",
      "Scene: " + t.name + (t.uuid ? " (" + t.uuid + ")" : ""),
      "Place: " + st.place + (withTiles ? "  (scene + overlay tile)" : ""),
      "Background image, grid" + (st.foundry.walls ? ", walls" : "") + " are replaced. Press 'Plan (dry run)' first to preview without writing.",
      "Continue?"];
  };
  // Plain text of a push-scene --dry-run result (nothing was written).
  VB.foundryPlanText = function (r) {
    return "PLAN (dry run, nothing written to Foundry): scene \"" + r.scene_name + "\", " + r.width + "x" + r.height + " px, grid " + r.grid.size + " px = " + r.grid.distance + " ft, " + (r.walls || 0) + " walls, " + (r.drawings || 0) + " drawings.";
  };
  // age of the cached Foundry lists in minutes (null if never fetched)
  VB.cacheAgeMin = function (cache, now) {
    if (!cache || !cache.fetched) return null;
    return Math.max(0, Math.round(((now || Date.now()) - Date.parse(cache.fetched)) / 60000));
  };
  // The Foundry lists (scenes, actors, items) are the same for every place: of two caches keep the one fetched later (a place switched to after an import starts with an empty one).
  VB.fresherCache = function (a, b) {
    var ta = a && a.fetched ? Date.parse(a.fetched) : -1, tb = b && b.fetched ? Date.parse(b.fetched) : -1;
    return tb > ta ? b : (a || { fetched: null, lists: {} });
  };
  VB.pickerRows = function (rows, filter) {
    var q = String(filter || "").toLowerCase();
    return (rows || []).filter(function (r) { return !q || String(r.name).toLowerCase().indexOf(q) >= 0; })
      .sort(function (a, b) { return String(a.name).localeCompare(String(b.name)); });
  };

  if (typeof module !== "undefined" && module.exports) module.exports = VB;
  if (typeof window !== "undefined") window.VBCore = VB;
})(this);
