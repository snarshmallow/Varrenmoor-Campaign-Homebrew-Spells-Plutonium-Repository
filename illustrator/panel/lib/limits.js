// Size and performance limits: recommended and hard maximum map sizes by play scale (grid square in ft + grid px), plus a check of the current
// place / pack / Foundry scene calibration against them. Pure (no DOM, no fs), ES5. UI: limits_ui.js (Scale tab block), export_ui.js (Export badge,
// "What will happen" notes, real-push notes). Every number carries where it comes from: "measured" (live test in this repo), "source" (read in
// Foundry / 3D Canvas source), "repo" (a rule already used by the pipeline) or "estimate" (reasoned, not measured). Sources:
//   FOUNDRY_3D_CANVAS_NOTES.md section 11 (lights: 72 lights = 2.5x GPU time of an empty scene, 156 visible ran 54-57 fps, 206 = 28 ms/33 fps and
//   materials failing, 306 = scene draws nothing; 4 shadow-casting lights halve fps, 5.6 M triangles/frame), section 10 (collision measured cheap),
//   generators/foundry_lightbudget.py (AUTO_HYBRID_ABOVE 64, SAFE_VISIBLE_LIGHTS 150), lib/exportplan.js ROOF_PER_BUILDING_MAX 150 / HEAVY_BUILDINGS 400,
//   generators/foundry_push.py calibrate() (max_px 8192 default, grid under 50 px refused), Foundry 11 source on this PC (CONST.GRID_MIN_SIZE = 50,
//   fog/visibility texture capped at 4096 px, performance mode chosen from the GPU MAX_TEXTURE_SIZE 4096/8192/16384), PLUGIN_GUIDE 6.2/6.3
//   (3,145 foliage instances ~1.1 M triangles uncapped, ~300k triangles / 150 draw calls in view as a starting budget, 600k triangle warning).
(function (root) {
  "use strict";
  var L = {};

  // ------------------------------------------------------------------ constants (with the kind of evidence behind each)
  L.K = {
    GRID_MIN_PX: 50,          // repo: foundry_push.calibrate refuses a grid under 50 px (Foundry 11 GRID_MIN_SIZE was 50)
    FOUNDRY_GRID_MIN_PX: 20,  // source: Foundry 14 GRID_MIN_SIZE = 20 (Vega install; the scene dialog clamps 20..300)
    REC_SCENE_PX: 8192,       // repo: push-scene --max-px default 8192; Foundry picks MEDIUM performance mode on GPUs whose texture limit is 8192 (source)
    HARD_SCENE_PX: 16384,     // source: the usual GPU MAX_TEXTURE_SIZE; a background bigger than it cannot be one texture on that GPU
    FOG_TEX_PX: 4096,         // source: Foundry 11 CanvasVisibility max texture 4096: above it fog of war / vision get coarser
    LIGHTS_REC: 64,           // measured: 72 lights = 2.5x the GPU time of an empty scene; foundry_lightbudget AUTO_HYBRID_ABOVE = 64
    LIGHTS_HARD: 150,         // measured: 156 visible ran, 206 = 28 ms (33 fps) with materials failing, 306 = nothing drawn; SAFE_VISIBLE_LIGHTS = 150
    LIGHTS_OVERVIEW_REC: 16,  // repo: hybrid keeps 16 lights + ambient (HYBRID_MAX); an overview needs no per-window light
    BUILDINGS_REC: 80,        // estimate: Dyers (25 houses) measured smooth; about 3x that before tiles, walls and lights add up
    BUILDINGS_HARD: 150,      // repo: ROOF_PER_BUILDING_MAX (one roof tile per building above this is too many tiles)
    TILES_REC: 150,           // estimate: PLUGIN_GUIDE 6.3 starting budget of ~150 draw calls in view (merged tiles: one draw call per material)
    TILES_HARD: 400,          // estimate: same order as HEAVY_BUILDINGS 400 (split/merge RAM warning); each tile is one more BVH + collision ray target
    TRIS_REC: 600000,         // repo: the foliage merge report warns above 600k triangles; measured: 0.5 M triangles/frame ran at 59 fps on Dyers
    TRIS_HARD: 5000000,       // measured: 5.6 M triangles/frame (shadow test) dropped Dyers to 30 fps
    FOLIAGE_REC: 3000,        // repo: 3,145 instances = ~1.1 M triangles uncapped (merge + Performance preset needed)
    FOLIAGE_HARD: 10000,      // estimate: about 3x the benchmark forest even with merge and a triangle cap
    TOKEN_MIN_FRACTION: 0.25, // a 5 ft creature smaller than 1/4 of a square looks wrong (task rule)
    OVERVIEW_GRID_FT: 25      // grid squares bigger than this are an overview map, not a play map
  };
  var K = L.K;
  // lights per square foot of a generated town (Bridgehollow pack: 514 lights on 2400 x 1500 ft, measured from the pack) -> the side of a square
  // town area that reaches the light limits: sqrt(64 / d) ~ 650 ft, sqrt(150 / d) ~ 1000 ft (estimate; a denser street reaches them sooner)
  L.TOWN_LIGHT_DENSITY = 514 / (2400 * 1500);
  function round50(x) { return Math.max(50, Math.round(x / 50) * 50); }
  L.EXTENT3D_REC_FT = round50(Math.sqrt(K.LIGHTS_REC / L.TOWN_LIGHT_DENSITY));
  L.EXTENT3D_HARD_FT = round50(Math.sqrt(K.LIGHTS_HARD / L.TOWN_LIGHT_DENSITY));

  L.SOURCES = {
    scene_px: "Recommended 8192 px: the pipeline's push-scene limit (--max-px) and the texture size of mid-range GPUs (Foundry switches them to Medium performance). Hard 16384 px: the usual GPU texture limit. Above 4096 px Foundry's fog of war texture gets coarser (Foundry 11 source).",
    grid_px: "Foundry 14 refuses a grid square under 20 px (source, Vega install: GRID_MIN_SIZE = 20); the pipeline's push-scene refuses under 50 px (Foundry 11 used 50).",
    extent3d: "3D size limit comes from the lights a generated town carries (Bridgehollow: 514 lights on 2400 x 1500 ft): about " + L.EXTENT3D_REC_FT + " ft square reaches 64 lights, about " + L.EXTENT3D_HARD_FT + " ft square reaches 150 (estimate from measured light limits).",
    lights: "Measured on the Dyers test scene (3D Canvas 9.0.29): 72 lights cost 2.5x an empty scene, 156 visible lights still ran, 206 ran at 33 fps with some materials failing, 306 drew nothing (GPU shader limit). The light budget (Lighting tab) hides lights above its cap.",
    buildings: "Up to 150 buildings the docs allow one hideable roof tile per building (repo rule); 80 is an estimate for a smooth play scene.",
    tiles: "Every model tile is draw calls plus one collision mesh. 150 is the docs' starting budget, 400 an estimate (not measured).",
    tris: "0.5 M triangles per frame ran at 59 fps; 5.6 M dropped to 30 fps (measured). The foliage merge report warns above 600k.",
    foliage: "3,145 trees is about 1.1 M triangles without a cap (repo benchmark): merge foliage and use the Performance preset above 3000.",
    token: "A 5 ft creature covers grid px x 5 / grid ft pixels. 3D Canvas draws a token model one grid square wide per token size (source: token size = width x grid px / 1000 units), so with 100 ft squares a 1x1 token is 100 ft wide next to true-size buildings. Below a quarter of a square, or with squares over 25 ft, use a street scene at 5 ft per square for play."
  };

  // ------------------------------------------------------------------ the play scales of the table
  L.SCALES = [
    { id: "5ft_100", grid_ft: 5, grid_px: 100, label: "5 ft squares, 100 px (battle map, pack default 20 px/ft)" },
    { id: "5ft_50", grid_ft: 5, grid_px: 50, label: "5 ft squares, 50 px (battle map, small)" },
    { id: "10ft_50", grid_ft: 10, grid_px: 50, label: "10 ft squares, 50 px (street / village)" },
    { id: "25ft_50", grid_ft: 25, grid_px: 50, label: "25 ft squares, 50 px (town district)" },
    { id: "50ft_50", grid_ft: 50, grid_px: 50, label: "50 ft squares, 50 px (town overview)" },
    { id: "100ft_150", grid_ft: 100, grid_px: 150, label: "100 ft squares, 150 px (overview, 1.5 px/ft)" }
  ];

  L.tokenCheck = function (grid_ft, grid_px) {
    grid_ft = +grid_ft || 0; grid_px = +grid_px || 0;
    if (!(grid_ft > 0) || !(grid_px > 0)) return null;
    var frac = Math.min(1, 5 / grid_ft), px = grid_px * 5 / grid_ft;
    return { fraction: frac, token_px: px, small: frac < K.TOKEN_MIN_FRACTION, overview: grid_ft > K.OVERVIEW_GRID_FT };
  };

  // limits for one scale: { ppf, rec/hard extent for a 2D scene (pixel limits) and for a 3D scene (pixel + content limits), content caps, token }
  L.limitsFor = function (grid_ft, grid_px) {
    grid_ft = +grid_ft; grid_px = +grid_px;
    var ppf = grid_px / grid_ft, overview = grid_ft > K.OVERVIEW_GRID_FT;
    var rec2 = Math.floor(K.REC_SCENE_PX / ppf), hard2 = Math.floor(K.HARD_SCENE_PX / ppf);
    return {
      grid_ft: grid_ft, grid_px: grid_px, ppf: ppf, overview: overview,
      rec2d_ft: rec2, hard2d_ft: hard2, rec2d_px: K.REC_SCENE_PX, hard2d_px: K.HARD_SCENE_PX,
      rec3d_ft: Math.min(rec2, L.EXTENT3D_REC_FT), hard3d_ft: Math.min(hard2, L.EXTENT3D_HARD_FT),
      fog_ft: Math.floor(K.FOG_TEX_PX / ppf),
      buildings_rec: K.BUILDINGS_REC, buildings_hard: K.BUILDINGS_HARD,
      tiles_rec: K.TILES_REC, tiles_hard: K.TILES_HARD,
      lights_rec: overview ? K.LIGHTS_OVERVIEW_REC : K.LIGHTS_REC, lights_hard: K.LIGHTS_HARD,
      tris_rec: K.TRIS_REC, tris_hard: K.TRIS_HARD, foliage_rec: K.FOLIAGE_REC, foliage_hard: K.FOLIAGE_HARD,
      grid_ok: grid_px >= K.GRID_MIN_PX, token: L.tokenCheck(grid_ft, grid_px)
    };
  };
  L.table = function () { return L.SCALES.map(function (s) { var o = L.limitsFor(s.grid_ft, s.grid_px); o.id = s.id; o.label = s.label; return o; }); };

  // mirror of generators/foundry_push.calibrate(): the 2D scene the panel's push-scene would make
  // p = { w_ft, h_ft, dpi, scale_ft_per_in, grid_ft, upscale, max_px } -> { ppf, grid_px, grid_ft, width, height, error }
  L.sceneCalib = function (p) {
    var native = (+p.dpi || 150) / (+p.scale_ft_per_in || 100) * (+p.upscale || 1), gft = +p.grid_ft || 5, maxPx = +p.max_px || K.REC_SCENE_PX;
    var big = Math.max(+p.w_ft || 0, +p.h_ft || 0), f = big > 0 ? Math.min(1, maxPx / (big * native)) : 1, gp = Math.round(native * f * gft);
    var ppf = gp / gft, r = { ppf: ppf, grid_px: gp, grid_ft: gft, width: Math.round((+p.w_ft || 0) * ppf), height: Math.round((+p.h_ft || 0) * ppf), error: "" };
    if (gp < K.GRID_MIN_PX) r.error = "grid would be " + gp + " px per square (Foundry minimum is " + K.GRID_MIN_PX + "): export at a higher dpi or use bigger grid squares";
    return r;
  };

  function fmt(n) { n = Math.round(+n || 0); return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  L.fmt = fmt;

  // the visible point lights a budget leaves (same rules as foundry_lightbudget.resolve_mode; f = st.lighting.f3d or null = every light on)
  L.visibleLights = function (n, f) {
    n = +n || 0; if (!f) return n;
    var mode = f.mode || "auto", cap = Math.max(0, Math.round(+f.maxLights || 0));
    if (mode === "auto") mode = n > 150 ? "global" : n > 64 ? "hybrid" : "lights";
    if (mode === "global") return 0;
    if (mode === "hybrid") return Math.min(n, cap || 16);
    return cap ? Math.min(cap, n) : n;
  };

  // recommend: plain advice for an extent at a scale
  L.recommend = function (w_ft, h_ft, grid_ft, grid_px) {
    var l = L.limitsFor(grid_ft, grid_px), big = Math.max(+w_ft || 0, +h_ft || 0), out = [];
    out.push("At " + grid_ft + " ft per square (" + grid_px + " px, " + (Math.round(l.ppf * 100) / 100) + " px/ft) keep a 2D scene under " + fmt(l.rec2d_ft) + " ft (" + fmt(l.rec2d_px) + " px; hard " + fmt(l.hard2d_ft) + " ft) and a 3D scene under " + fmt(l.rec3d_ft) + " ft (hard " + fmt(l.hard3d_ft) + " ft).");
    if (big > l.rec3d_ft) out.push("This place is " + fmt(w_ft) + " x " + fmt(h_ft) + " ft: for 3D play split it into street scenes or region extracts (Regions tab) of about " + fmt(Math.min(l.rec3d_ft, L.EXTENT3D_REC_FT)) + " ft, at 5 ft per square.");
    if (l.token && (l.token.small || l.token.overview)) out.push("At this grid a 5 ft token is " + (Math.round(l.token.fraction * 100)) + "% of a square: use this scene as an overview only.");
    return out;
  };

  // ------------------------------------------------------------------ evaluate
  // facts: { w_ft, h_ft (place extent), grid_ft, grid_px (Foundry scene grid), ppf (optional, else grid_px / grid_ft), mode "3d"|"2d" (default 3d),
  //          buildings, lights (pack lights), lighting (st.lighting.f3d or null), tiles, triangles, foliage, roofMode }
  // -> [{ level: ok|info|warn|danger, code, message, suggestion, source }]
  var RANK = { ok: 0, info: 1, warn: 2, danger: 3 };
  L.RANK = RANK;
  L.evaluate = function (facts) {
    facts = facts || {};
    var out = [], gft = +facts.grid_ft || 0, gpx = +facts.grid_px || 0, ppf = +facts.ppf || (gft > 0 ? gpx / gft : 0), three = facts.mode !== "2d";
    function add(level, code, message, suggestion, src) { out.push({ level: level, code: code, message: message, suggestion: suggestion || "", source: L.SOURCES[src || code] || "" }); }
    var w = +facts.w_ft || 0, h = +facts.h_ft || 0, big = Math.max(w, h);
    var l = gft > 0 && gpx > 0 ? L.limitsFor(gft, gpx) : null;
    // grid and token scale
    if (l) {
      if (gpx < K.FOUNDRY_GRID_MIN_PX) add("danger", "grid_px", "Grid square is " + Math.round(gpx) + " px: Foundry refuses less than " + K.FOUNDRY_GRID_MIN_PX + " px.", "Export at a higher dpi (Foundry tab) or use bigger grid squares.");
      else if (!l.grid_ok) add("warn", "grid_px", "Grid square is " + Math.round(gpx) + " px: the pipeline's push-scene refuses less than " + K.GRID_MIN_PX + " px.", "Export at a higher dpi (Foundry tab) or use bigger grid squares.");
      var t = l.token;
      if (t.overview) add("warn", "token", "This is an overview map: one square is " + gft + " ft, so a 5 ft creature is " + Math.round(t.fraction * 100) + "% of a square (" + Math.round(t.token_px) + " px), and in 3D a 1x1 token is drawn " + gft + " ft wide. Tokens will look wrong.", "Use a street scene at 5 ft per square for play (Regions tab: extract a region, or a smaller view).");
      else if (t.small) add("warn", "token", "A 5 ft token is only " + Math.round(t.fraction * 100) + "% of a " + gft + " ft square (" + Math.round(t.token_px) + " px).", "For play use 5 or 10 ft squares.");
      else add("ok", "token", "Token scale: a 5 ft token is " + Math.round(t.fraction * 100) + "% of a square (" + Math.round(t.token_px) + " px).");
    }
    // scene pixels
    if (big > 0 && ppf > 0) {
      var px = Math.round(big * ppf), dims = fmt(w * ppf) + " x " + fmt(h * ppf) + " px";
      if (px > K.HARD_SCENE_PX) add("danger", "scene_px", "Scene would be " + dims + ": over " + fmt(K.HARD_SCENE_PX) + " px, the texture limit of most GPUs.", "Use bigger grid squares, a lower dpi or a smaller region.");
      else if (px > K.REC_SCENE_PX) add("warn", "scene_px", "Scene would be " + dims + ": over the recommended " + fmt(K.REC_SCENE_PX) + " px (the push lowers the resolution to fit --max-px).", "Use bigger squares for an overview, or split into smaller scenes.");
      else if (px > K.FOG_TEX_PX) add("info", "scene_px", "Scene " + dims + ": above " + fmt(K.FOG_TEX_PX) + " px Foundry draws fog of war at a lower resolution.", "", "scene_px");
      else add("ok", "scene_px", "Scene " + dims + " is within the pixel limits.");
    }
    // 3D extent
    if (three && big > 0) {
      var r3 = l ? l.rec3d_ft : L.EXTENT3D_REC_FT, h3 = l ? l.hard3d_ft : L.EXTENT3D_HARD_FT, dimft = fmt(w) + " x " + fmt(h) + " ft";
      if (big > h3) add("danger", "extent3d", "Place is " + dimft + ": over the 3D hard limit of about " + fmt(h3) + " ft at this scale. Expect a slow scene for everyone.", "Split into street scenes or region extracts of about " + fmt(L.EXTENT3D_REC_FT) + " ft; keep this one as a 2D overview.");
      else if (big > r3) add("warn", "extent3d", "Place is " + dimft + ": over the recommended 3D size of about " + fmt(r3) + " ft at this scale.", "Use the light budget (Lighting tab: auto or hybrid), merge models by layer, or split into street scenes.");
      else add("ok", "extent3d", "Place " + dimft + " is within the recommended 3D size (" + fmt(r3) + " ft).");
    }
    // lights
    if (facts.lights != null) {
      var n = +facts.lights || 0, vis = L.visibleLights(n, facts.lighting || null), lr = l ? l.lights_rec : K.LIGHTS_REC, budget = facts.lighting ? " (light budget " + (facts.lighting.mode || "auto") + (facts.lighting.maxLights ? ", max " + facts.lighting.maxLights : "") + " keeps " + vis + " visible)" : "";
      if (vis > K.LIGHTS_HARD) add("danger", "lights", fmt(vis) + " visible lights: above " + K.LIGHTS_HARD + " the 3D view slows hard and above about 300 it draws nothing.", "Lighting tab: light budget auto or hybrid, or exclude window lights.");
      else if (n > K.LIGHTS_HARD) add("warn", "lights", "The pack has " + fmt(n) + " lights" + budget + ". Pushing them all visible would break the 3D view (306 lights drew nothing in the test).", "Keep the light budget on (auto / hybrid), or push interior lights only for street scenes.");
      else if (vis > lr) add("warn", "lights", fmt(vis) + " visible lights" + budget + ": over the recommended " + lr + (l && l.overview ? " for an overview map" : "") + ".", "Lighting tab: hybrid keeps the 16 most important lights plus ambient light.");
      else add("ok", "lights", fmt(n) + " pack light(s), " + fmt(vis) + " visible" + budget + ".");
    }
    if (facts.buildings != null) {
      var b = +facts.buildings || 0;
      if (b > K.BUILDINGS_HARD) add("warn", "buildings", fmt(b) + " buildings: above " + K.BUILDINGS_HARD + " for one 3D scene.", "Merge buildings by layer or district, roof mode merged (per scene), or split the town.");
      else if (b > K.BUILDINGS_REC) add("info", "buildings", fmt(b) + " buildings: above the " + K.BUILDINGS_REC + " estimated for a smooth play scene.", "Merge buildings by layer (Export: merge preset layer).");
      if (String(facts.roofMode || "") === "per_building" && b > K.BUILDINGS_HARD) add("warn", "roofs", "Individual roofs add one tile per building (" + fmt(b) + ").", "Use merged roofs (per scene) above " + K.BUILDINGS_HARD + " buildings.", "buildings");
    }
    if (facts.tiles != null) {
      var tl = +facts.tiles || 0;
      if (tl > K.TILES_HARD) add("warn", "tiles", fmt(tl) + " model tiles planned: above " + K.TILES_HARD + ".", "Merge (preset layer or district) before pushing.");
      else if (tl > K.TILES_REC) add("info", "tiles", fmt(tl) + " model tiles planned (before merge): above " + K.TILES_REC + ".", "The merge step (preset layer) brings this down to about one tile per layer.");
    }
    if (facts.triangles != null) {
      var tr = +facts.triangles || 0;
      if (tr > K.TRIS_HARD) add("danger", "tris", fmt(tr) + " triangles in the models: above " + fmt(K.TRIS_HARD) + " (measured: 5.6 M per frame = 30 fps).", "Lower the LOD (push-models --lod), cap foliage triangles, or split the place.");
      else if (tr > K.TRIS_REC) add("warn", "tris", fmt(tr) + " triangles in the models: above " + fmt(K.TRIS_REC) + ".", "Foliage merge Performance preset, or a smaller scene.");
    }
    if (facts.foliage != null) {
      var fo = +facts.foliage || 0;
      if (fo > K.FOLIAGE_HARD) add("warn", "foliage", fmt(fo) + " foliage items: above " + fmt(K.FOLIAGE_HARD) + ".", "Merge foliage with the Performance or Low-end preset, or thin the scatter.");
      else if (fo > K.FOLIAGE_REC) add("info", "foliage", fmt(fo) + " foliage items: merge them (Foliage tab) before pushing.", "Performance preset caps the triangles.");
    }
    return out;
  };
  L.worst = function (list) { var w = "ok"; (list || []).forEach(function (x) { if (RANK[x.level] > RANK[w]) w = x.level; }); return w; };
  // lines for the "What will happen" preview and the push notes (warn and danger only)
  L.notes = function (list) { return (list || []).filter(function (x) { return RANK[x.level] >= RANK.warn; }).map(function (x) { return (x.level === "danger" ? "SIZE PROBLEM: " : "Size warning: ") + x.message + (x.suggestion ? " " + x.suggestion : ""); }); };

  if (typeof module !== "undefined" && module.exports) module.exports = L;
  if (typeof window !== "undefined") window.VBLimits = L;   // always, even when Node's module exists (CEP)
})(typeof self !== "undefined" ? self : this);
