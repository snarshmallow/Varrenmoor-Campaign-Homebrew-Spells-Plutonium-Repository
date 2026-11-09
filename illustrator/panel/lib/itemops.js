// Surgical map edits (no render_world, no whole-layer replace): remove / replace / rename only the Illustrator items that belong to some entity ids.
// Pure logic, no DOM: also loaded by test/test_itemops.js. Host side: jsx/host.jsx actions delete_items, replace_items, rename_items (same matching rules,
// the regex source below is mirrored by VB_itemRegex in host.jsx and the test checks both give the same string).
//
// ITEM NAMES (what render_world.py / host.jsx write; SVG ids are written with '_' as '_x5F_' (lib_svg._encode_ids), Illustrator normally decodes it back
// to '_', older imports show '_x5F_' or a space instead of '_': decodeName() undoes all three):
//   <id>                          Roads (street outline, all rings in one path), Road Centerlines, Buildings, Building Footprints, Walls (gates / rooms)
//   <id>_label                    label text (Labels - Streets / - Buildings / - Districts / - Hidden; curved: type on a path + its path <id>_label_tp)
//   <id>_label_halo|_box          halo copy / box under the text (Label Backing; curved halo: + <id>_label_halo_tp)
//   <id>_callout                  group of halo + text made by finalize_labels (on the text's layer)
//   <id>_leader, _leader_casing   leader lines (Leaders);  <id>_leader_dot anchor dot (Leader Anchors)
//   <id>_marker, <id>_marknum     numbered callout circle + number (Callout Markers)
//   <id>_name, <id>_name_halo     river names (Labels - Streets / Label Backing)
//   flat_<id>                     flat fill-only copy (ART - Fill Shapes, made by apply_fills)
//   <street>_kerb<n>              region kerbs (Details);  mk_<street>_start|end  off-map arrows (Bounds)
//   <bld>_door<n>, _roof, _chimney (Details);  <bld>_lot (DETAILS - Lots);  <bld>_fence<n> (Fences)
// NOT item-wise: the 'ART - Fill Streets' / 'ART - Fill Buildings' rasters (one PNG for the whole map: left as is, marked stale), Blocks (derived from the
// whole street network: marked stale; 'Refresh blocks only' replaces just that layer), contour masks (stale, Contours tab).
//
// INTERFACE (for lib/buildedit.js and other tabs; window.VBItemOps and VBCore.deleteItemsSteps / VBCore.itemOps):
//   VB.deleteItemsSteps(ids, preset, opts) -> [step]      ids: array, or function(run) -> array (ids known only after an edit step)
//       preset: "road" | "building" | array of layer specs {layer, names:["{id}", "{id}_label", ...], patterns:["^{id}_kerb\\d+$"]}
//       opts: {label, var (run.vars key, default "itemops"), chunk (ids per Illustrator call, default 200), timeout_ms, layers (only these layer names)}
//       One fn step: one host delete_items call per chunk; never throws on an Illustrator failure: the summary goes to run.vars[opts.var] AND run.last as
//       {ok, removed, deleted (same number), per_layer, not_found, skipped_locked, missing_layers, calls, error}. ok=false when a call failed (e.g. the panel's
//       host.jsx predates delete_items: 'unknown action'): fall back to the full refresh then. Also sets run.vars[opts.failVar || "fastFail"] = !ok
//       (the flag lib/buildedit.js gates its full-refresh fallback on). Each host request carries ids, layers (names) and targets (the precise plan).
//   VB.itemOps.replaceItemsStep(svg, layers, opts) -> step  copy the items of an SVG (written by render_items.py) into the open document, replacing the
//       items of the same name on the same layer (z-order kept), others untouched; summary in run.vars[opts.var || "replaced"].
//   Host actions: {action:"delete_items", targets:[{layer, names, patterns}] | ids+layers+match("family"|"exact"|"prefix"), max, timeout_ms}
//                 {action:"replace_items", path, layers, timeout_ms}     {action:"rename_items", renames:[{from, to, text}], layers, timeout_ms}
(function (root) {
  "use strict";
  var api = {};
  api.CHUNK = 200;
  // label / leader / marker family of an entity id: suffix (after "<id>_") of every item render_world / host.jsx makes for it
  api.FAMILY_SUFFIX = "label(?:_halo|_box)?(?:_tp)?|callout|leader(?:_casing|_dot)?|marker|marknum|name(?:_halo)?(?:_tp)?|kerb\\d+|door\\d+|roof|chimney|lot|fence\\d+|start|end";
  var LABEL_TEXT = ["{id}_label", "{id}_label_tp", "{id}_callout"], BACKING = ["{id}_label_halo", "{id}_label_halo_tp", "{id}_label_box"];
  var LEADERS = { layer: "Leaders", names: ["{id}_leader", "{id}_leader_casing"] }, ANCHORS = { layer: "Leader Anchors", names: ["{id}_leader_dot"] };
  var MARKERS = { layer: "Callout Markers", names: ["{id}_marker", "{id}_marknum"] }, FLAT = { layer: "ART - Fill Shapes", names: ["flat_{id}"] };
  api.PRESETS = {
    road: [{ layer: "Roads", names: ["{id}"] }, { layer: "Road Centerlines", names: ["{id}"] },
      { layer: "Labels - Streets", names: LABEL_TEXT }, { layer: "Labels - Hidden", names: ["{id}_label"] }, { layer: "Label Backing", names: BACKING },
      LEADERS, ANCHORS, MARKERS, FLAT,
      { layer: "Details", patterns: ["^{id}_kerb\\d+$"] }, { layer: "Bounds", patterns: ["^mk_{id}_(?:start|end)$"] }],
    building: [{ layer: "Buildings", names: ["{id}"] }, { layer: "Building Footprints", names: ["{id}"] }, { layer: "Walls", names: ["{id}"] },
      { layer: "Labels - Buildings", names: LABEL_TEXT }, { layer: "Labels - Hidden", names: ["{id}_label"] }, { layer: "Label Backing", names: BACKING },
      LEADERS, ANCHORS, MARKERS, FLAT, { layer: "DETAILS - Lots", names: ["{id}_lot"] },
      { layer: "Details", names: ["{id}_roof", "{id}_chimney"], patterns: ["^{id}_door\\d+$"] }, { layer: "Fences", patterns: ["^{id}_fence\\d+$"] }]
  };
  api.presetLayers = function (preset) { return (typeof preset === "string" ? api.PRESETS[preset] || [] : preset || []).map(function (s) { return s.layer; }); };

  // Illustrator item name -> the id-style name: '_x5F_' -> '_' (SVG id escape), trimmed. spaces: a second form with ' ' -> '_' (older imports)
  api.decodeName = function (n) { return String(n == null ? "" : n).replace(/_x5F_/g, "_").replace(/^\s+|\s+$/g, ""); };
  api.nameForms = function (n) { var a = api.decodeName(n), b = a.replace(/ /g, "_"); return a === b ? [a] : [a, b]; };
  api.escapeRe = function (s) { return String(s).replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&"); };
  // regex source for a list of ids. family (default): the id itself + every family item; exact: the id only; prefix: the id or anything after "<id>_" / "<id> ".
  // (host.jsx VB_itemRegex builds the same string: keep both in step)
  api.regexSource = function (ids, match) {
    var alt = (ids || []).map(api.escapeRe).join("|");
    if (!alt) return "^$.";
    if (match === "exact") return "^(?:" + alt + ")$";
    if (match === "prefix") return "^(?:" + alt + ")(?:[_ ].*)?$";
    return "^(?:flat_|mk_)?(?:" + alt + ")(?:_(?:" + api.FAMILY_SUFFIX + "))?$";
  };
  // -> the id an item name belongs to, or null. Longest id first, so str_02 never claims str_020's items.
  api.matchName = function (name, ids, match) {
    var forms = api.nameForms(name), byLen = (ids || []).slice().sort(function (a, b) { return b.length - a.length; });
    for (var f = 0; f < forms.length; f++) {
      for (var i = 0; i < byLen.length; i++) { if (new RegExp(api.regexSource([byLen[i]], match)).test(forms[f])) return byLen[i]; }
    }
    return null;
  };
  // precise plan: [{layer, names:[exact names], patterns:[regex sources]}] for these ids. Exact names use the host's getByName fast path; patterns walk the layer once.
  api.targets = function (ids, preset, only) {
    var specs = typeof preset === "string" ? api.PRESETS[preset] : preset;
    if (!specs) throw new Error("unknown item preset: " + preset);
    var alt = (ids || []).map(api.escapeRe).join("|");
    return specs.filter(function (s) { return !only || only.indexOf(s.layer) >= 0; }).map(function (s) {
      var names = [];
      (s.names || []).forEach(function (t) { ids.forEach(function (id) { names.push(t.split("{id}").join(id)); }); });
      var pats = (s.patterns || []).map(function (p) { return p.split("{id}").join("(?:" + alt + ")"); });
      return { layer: s.layer, names: names, patterns: pats };
    });
  };
  api.chunk = function (ids, n) { n = n || api.CHUNK; var out = []; for (var i = 0; i < ids.length; i += n) out.push(ids.slice(i, i + n)); return out; };
  api.uniq = function (a) { var s = {}, o = []; (a || []).forEach(function (x) { if (x != null && x !== "" && !s[x]) { s[x] = 1; o.push(String(x)); } }); return o; };
  // host requests for a delete (one per chunk of ids)
  api.deleteRequests = function (ids, preset, opts) {
    opts = opts || {};
    return api.chunk(api.uniq(ids), opts.chunk).map(function (part) {
      var tg = api.targets(part, preset, opts.layers);
      return { action: "delete_items", ids: part, layers: tg.map(function (t) { return t.layer; }), targets: tg, max: opts.max || 20000, timeout_ms: opts.timeout_ms || 60000 };
    });
  };
  // sum of several delete_items replies
  api.mergeResults = function (rs) {
    var o = { ok: true, removed: 0, per_layer: {}, not_found: [], skipped_locked: [], missing_layers: [], calls: rs.length, truncated: false };
    rs.forEach(function (r) {
      if (!r || !r.ok) { o.ok = false; o.error = o.error || (r && r.error) || "no reply"; return; }
      o.removed += r.removed || 0;
      Object.keys(r.per_layer || {}).forEach(function (k) { o.per_layer[k] = (o.per_layer[k] || 0) + r.per_layer[k]; });
      o.not_found = o.not_found.concat(r.not_found || []); o.skipped_locked = o.skipped_locked.concat(r.skipped_locked || []);
      (r.missing_layers || []).forEach(function (l) { if (o.missing_layers.indexOf(l) < 0) o.missing_layers.push(l); });
      if (r.truncated) o.truncated = true;
    });
    o.deleted = o.removed;
    return o;
  };
  api.describe = function (r) {
    if (!r) return "no reply";
    if (!r.ok) return "failed: " + r.error;
    var pl = Object.keys(r.per_layer || {}).map(function (k) { return k + " " + r.per_layer[k]; }).join(", ");
    return r.removed + " item(s) removed" + (pl ? " (" + pl + ")" : "") + (r.not_found && r.not_found.length ? "; nothing on the map for " + r.not_found.join(", ") : "") +
      (r.skipped_locked && r.skipped_locked.length ? "; locked, left: " + r.skipped_locked.join(", ") : "") + (r.truncated ? "; STOPPED at the item cap / time budget" : "");
  };
  function idsOf(ids, run) { return api.uniq(typeof ids === "function" ? ids(run) : ids); }
  api.deleteItemsSteps = function (ids, preset, opts) {
    opts = opts || {};
    var key = opts["var"] || "itemops";
    return [{ t: "fn", label: opts.label || "map: remove the items of the deleted " + (typeof preset === "string" ? preset : "object") + "s (delete_items)", fn: async function (run) {
      var x = idsOf(ids, run), rs = [];
      if (!x.length) { run.vars[opts.failVar || "fastFail"] = false; run.vars[key] = run.last = { ok: true, removed: 0, deleted: 0, per_layer: {}, not_found: [], skipped_locked: [], missing_layers: [], calls: 0 }; run.log("map: nothing to remove"); return; }
      var reqs = api.deleteRequests(x, preset, opts);
      for (var i = 0; i < reqs.length; i++) {
        var r;
        try { r = await run.host(reqs[i], true); } catch (e) { r = { ok: false, error: String((e && e.message) || e) }; }
        rs.push(r);
        if (!r || !r.ok) break;               // stop at the first failure: the caller falls back to the full refresh
      }
      var m = api.mergeResults(rs); m.ids = x;
      run.vars[key] = m; run.last = m; run.vars[opts.failVar || "fastFail"] = !m.ok;
      run.log("map: " + api.describe(m));
    } }];
  };
  // replace / append the items of an SVG (render_items.py) by name on the given layers. svg: path or function(run) -> path
  api.replaceItemsStep = function (svg, layers, opts) {
    opts = opts || {};
    var key = opts["var"] || "replaced";
    return { t: "fn", label: opts.label || "map: replace the changed items (" + layers.join(", ") + ")", when: opts.when, fn: async function (run) {
      var p = typeof svg === "function" ? svg(run) : svg, r;
      try { r = await run.host({ action: "replace_items", path: p, layers: layers, timeout_ms: opts.timeout_ms || 120000 }, true); } catch (e) { r = { ok: false, error: String((e && e.message) || e) }; }
      r = r || { ok: false, error: "no reply" };
      run.vars[key] = r; run.last = r;
      run.log("map: " + (r.ok ? (r.replaced || 0) + " item(s) replaced, " + (r.added || 0) + " added" + (r.missing && r.missing.length ? " (no layer in the svg: " + r.missing.join(", ") + ")" : "") : "replace_items failed: " + r.error));
    } };
  };
  // streets.json before / after an edit -> {gone, changed, added} street ids (changed = points, width, kind or status differ)
  api.diffStreets = function (before, after) {
    var key = function (s) { var g = s.geometry || {}; return JSON.stringify([g.points, g.width_ft, s.kind, s.status]); };
    var b = {}, a = {}, out = { gone: [], changed: [], added: [] };
    ((before && before.streets) || []).forEach(function (s) { b[s.id] = s; });
    ((after && after.streets) || []).forEach(function (s) { a[s.id] = s; });
    Object.keys(b).forEach(function (id) { if (!a[id]) out.gone.push(id); else if (key(a[id]) !== key(b[id])) out.changed.push(id); });
    Object.keys(a).forEach(function (id) { if (!b[id]) out.added.push(id); });
    return out;
  };

  root.VBItemOps = api;                                   // always on window (the panel loads plain <script> tags; module may exist in CEP too)
  var VB = root.VBCore || null;
  if (!VB && typeof require !== "undefined") { try { VB = require("./core.js"); } catch (e) { VB = null; } }
  if (VB) { VB.itemOps = api; VB.deleteItemsSteps = api.deleteItemsSteps; }
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
