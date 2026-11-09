// ExtendScript host. VB_run(jsonString) -> JSON string {ok, ...}
function VB_inArr(a, v) { for (var i = 0; i < a.length; i++) if (a[i] === v) return true; return false; }
function VB_str(v) {
  if (v === null || v === undefined) return "null";
  var t = typeof v;
  if (t === "number" || t === "boolean") return String(v);
  if (v instanceof Array) { var a = []; for (var i = 0; i < v.length; i++) a.push(VB_str(v[i])); return "[" + a.join(",") + "]"; }
  if (t === "object") { var o = []; for (var k in v) if (v.hasOwnProperty(k)) o.push(VB_str(String(k)) + ":" + VB_str(v[k])); return "{" + o.join(",") + "}"; }
  return '"' + String(v).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t") + '"';
}
function VB_layer(doc, name) {
  try { return doc.layers.getByName(name); } catch (e) {}
  var l = doc.layers.add(); l.name = name; return l;
}
// Recursive lookup of a (sub)layer by name; returns null if absent.
function VB_find(container, name) {
  for (var i = 0; i < container.layers.length; i++) {
    var l = container.layers[i];
    if (l.name === name) return l;
    var r = VB_find(l, name);
    if (r) return r;
  }
  return null;
}
// Direct children of a layer only (pageItems of a layer can include sublayer items).
function VB_direct(layer) {
  var items = [];
  for (var i = 0; i < layer.pageItems.length; i++) {
    var it = layer.pageItems[i], ok = true;
    try { ok = (it.layer.name === layer.name); } catch (e) { ok = true; }
    if (ok) items.push(it);
  }
  return items;
}
function VB_isArt(name) { return /^ART(\s|$|-)/i.test(name); }
// Return the target layer for a source layer, creating it (and its parent) when missing.
function VB_ensureLike(doc, src) {
  var t = VB_find(doc, src.name);
  if (t) return t;
  var par = null;
  try { if (src.parent && src.parent.typename === "Layer") par = VB_ensureLike(doc, src.parent); } catch (e) {}
  t = par ? par.layers.add() : doc.layers.add();
  t.name = src.name;
  // layers.add() puts the new layer on TOP of its parent: a missing 'Label Backing' then landed above every label text layer.
  // Put it where the SVG has it instead: below the nearest sibling above it in the source, else above the nearest one below it.
  try {
    var sp = src.parent, sibs = sp.layers, si = -1, k, ref;
    for (k = 0; k < sibs.length; k++) if (sibs[k].name === src.name) { si = k; break; }
    var tc = par ? par.layers : doc.layers, done = false;
    for (k = si - 1; k >= 0 && !done; k--) { ref = VB_childLayer(tc, sibs[k].name); if (ref && ref !== t) { t.move(ref, ElementPlacement.PLACEAFTER); done = true; } }
    for (k = si + 1; k < sibs.length && !done && si >= 0; k++) { ref = VB_childLayer(tc, sibs[k].name); if (ref && ref !== t) { t.move(ref, ElementPlacement.PLACEBEFORE); done = true; } }
  } catch (e2) {}
  return t;
}
function VB_sameParent(a, b) { if (a === b) return true; try { return a.typename === b.typename && String(a.name) === String(b.name); } catch (e) { return false; } }
function VB_childLayer(layers, name) { try { return layers.getByName(name); } catch (e) { return null; } }
// Canonical stacking, top to bottom, one list per parent (mirrors render_world.SPEC; panel lib/core.js VB.LAYER_ORDER sends the same lists).
// Only layers found under the same parent as the list's first found layer are ordered; nothing moves when the order is already right.
function VB_orderLayers(doc, groups) {
  var res = { moved: 0, checked: 0, errors: [] };
  var buckets = [], g, b, i;
  for (g = 0; g < groups.length; g++) {                  // a list may mix parents (a flat top-to-bottom list): each parent's layers are ordered among themselves
    var names = groups[g];
    for (i = 0; i < names.length; i++) {
      var l = VB_find(doc, names[i]); if (!l) continue;
      var p = null; try { p = l.parent; } catch (e) {}
      if (!p) continue;
      for (b = 0; b < buckets.length; b++) if (VB_sameParent(buckets[b].par, p)) break;
      if (b === buckets.length) buckets.push({ par: p, found: [], seen: {} });
      if (buckets[b].seen[l.name]) continue;
      buckets[b].seen[l.name] = true; buckets[b].found.push(l);
    }
  }
  for (b = 0; b < buckets.length; b++) {
    var par = buckets[b].par, found = buckets[b].found;
    res.checked += found.length;
    if (found.length < 2) continue;
    var sibs = par.layers, pos = {}, inOrder = true, last = -1;
    for (i = 0; i < sibs.length; i++) pos[sibs[i].name] = i;
    for (i = 0; i < found.length; i++) { var ix = pos[found[i].name]; if (ix < last) { inOrder = false; break; } last = ix; }
    if (inOrder) continue;
    var undo = [];
    try { if (par.typename === "Layer") VB_unlockChain(par, undo); } catch (e) {}
    for (i = 1; i < found.length; i++) {
      var lay = found[i], wl = false;
      try { wl = lay.locked; if (wl) lay.locked = false; } catch (e) {}
      try { lay.move(found[i - 1], ElementPlacement.PLACEAFTER); res.moved++; } catch (e) { res.errors.push(lay.name + ": " + e); }
      try { if (wl) lay.locked = true; } catch (e) {}
    }
    for (i = 0; i < undo.length; i++) { try { undo[i].locked = true; } catch (e) {} }
  }
  return res;
}
// Layer `name` (created if missing), stacked directly beneath the first existing layer of `below` (string or array of names).
function VB_orderLayer(doc, name, below) {
  var pl = VB_find(doc, name);
  if (!pl) { pl = doc.layers.add(); pl.name = name; }
  var list = (typeof below === "string") ? [below] : (below && below.length !== undefined ? below : []);   // arrays from eval are not always instanceof Array
  for (var i = 0; i < list.length; i++) {
    var ref = VB_find(doc, list[i]);
    if (ref && ref !== pl) { try { pl.move(ref, ElementPlacement.PLACEAFTER); } catch (e) {} break; }
  }
  return pl;
}
function VB_rgb(c) { var r = new RGBColor(); r.red = c[0]; r.green = c[1]; r.blue = c[2]; return r; }
// Named swatch: create it or update its colour (swatches are the only fill style a script can create).
function VB_swatch(doc, name, rgb) {
  var sw = null;
  try { sw = doc.swatches.getByName(name); } catch (e) { sw = null; }
  if (!sw) { sw = doc.swatches.add(); sw.name = name; }
  sw.color = VB_rgb(rgb);
  return sw;
}
// Flatten a PathItem to {name, closed, points:[{a,l,r}]} (document coordinates, y up).
function VB_pathInfo(pi) {
  var pts = [];
  for (var i = 0; i < pi.pathPoints.length; i++) {
    var p = pi.pathPoints[i];
    pts.push({ a: [p.anchor[0], p.anchor[1]], l: [p.leftDirection[0], p.leftDirection[1]], r: [p.rightDirection[0], p.rightDirection[1]] });
  }
  var sel = [];
  try { for (var k = 0; k < pi.pathPoints.length; k++) { if (pi.pathPoints[k].selected === PathPointSelection.ANCHORPOINT) sel.push(k); } } catch (e) {}
  return { name: pi.name, closed: pi.closed, points: pts, selected: sel };
}
function VB_collectPaths(items, outList) {
  for (var i = 0; i < items.length; i++) {
    var it = items[i], t = it.typename;
    if (t === "PathItem") outList.push(it);
    else if (t === "CompoundPathItem") { for (var j = 0; j < it.pathItems.length; j++) outList.push(it.pathItems[j]); }
    else if (t === "GroupItem") VB_collectPaths(it.pageItems, outList);
  }
}
// ---- plugin lasso (see lib/lasso.js): helper layer "VB LASSO", drawing the captured polygon back as a selection, selecting items inside it ----
var VB_LASSO_LAYER = "VB LASSO";
function VB_lassoLayer(doc, clear) {
  var ll = VB_find(doc, VB_LASSO_LAYER);
  if (!ll) { ll = doc.layers.add(); ll.name = VB_LASSO_LAYER; }
  try { ll.locked = false; ll.visible = true; } catch (e) {}
  try { if (doc.layers.length > 1 && doc.layers[0].name !== VB_LASSO_LAYER) ll.move(doc, ElementPlacement.PLACEATBEGINNING); } catch (e) {}   // keep it on top (only when it is not already: no needless reordering)
  if (clear) {
    for (var i = ll.pageItems.length - 1; i >= 0; i--) { var it = ll.pageItems[i]; try { it.locked = false; it.hidden = false; } catch (e) {} try { it.remove(); } catch (e2) {} }
  }
  return ll;
}
// Quiet mode for the lasso calls: no alert/dialog may ever block the single ExtendScript thread ("Not Responding" with 0 % CPU is a modal waiting for a click).
function VB_quietBegin() {
  var st = { ui: null, lvl: null };
  try { st.ui = app.userInteractionLevel; app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}
  try { st.lvl = $.level; $.level = 0; } catch (e2) {}
  return st;
}
function VB_quietEnd(st) {
  try { if (st.ui !== null) app.userInteractionLevel = st.ui; } catch (e) {}
  try { if (st.lvl !== null) $.level = st.lvl; } catch (e2) {}
}
function VB_pip(x, y, poly) {   // even-odd point in polygon, poly = [[x,y],...]
  var inside = false, n = poly.length;
  for (var i = 0, j = n - 1; i < n; j = i++) {
    var xi = poly[i][0], yi = poly[i][1], xj = poly[j][0], yj = poly[j][1];
    if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) inside = !inside;
  }
  return inside;
}
function VB_lassoLayerOk(l, filter) {   // default: unlocked + visible layers except the lasso layer and guides; a name list overrides lock/visibility
  var nm = l.name;
  if (nm === VB_LASSO_LAYER || /^guides?$/i.test(nm)) return false;
  if (filter && filter.length) { for (var i = 0; i < filter.length; i++) if (String(filter[i]).toLowerCase() === nm.toLowerCase()) return true; return false; }
  return !l.locked && l.visible;
}
function VB_lassoScan(container, a, st) {
  for (var li = 0; li < container.layers.length; li++) {
    var l = container.layers[li];
    VB_lassoScan(l, a, st);
    if (!VB_lassoLayerOk(l, a.filter)) { if (l.name !== VB_LASSO_LAYER) st.skipped++; continue; }
    var items = VB_direct(l), cnt = 0;
    for (var k = 0; k < items.length; k++) {
      if (st.scanned >= st.cap) { st.truncated = true; return; }
      if (st.hits.length >= a.max) { st.truncated = true; return; }
      var it = items[k]; st.scanned++;
      try { if (it.locked || it.hidden) continue; } catch (e) {}
      var b; try { b = it.geometricBounds; } catch (e3) { continue; }   // [left, top, right, bottom]
      var ok;
      if (a.mode === "all") {
        var pts = [];
        if (it.typename === "PathItem" && it.pathPoints.length <= 2000) { for (var p = 0; p < it.pathPoints.length; p++) pts.push(it.pathPoints[p].anchor); }
        else pts = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]];
        ok = pts.length > 0; for (var q = 0; ok && q < pts.length; q++) if (!VB_pip(pts[q][0], pts[q][1], a.poly)) ok = false;
      } else ok = VB_pip((b[0] + b[2]) / 2, (b[1] + b[3]) / 2, a.poly);
      if (ok) { st.hits.push(it); cnt++; }
    }
    if (cnt) st.layers.push({ name: l.name, count: cnt });
  }
}
// Visibility snapshot of every (sub)layer: [{l, v}]; used by export_view to show only some layers and restore afterwards.
function VB_snapshot(container, list) {
  for (var i = 0; i < container.layers.length; i++) { var l = container.layers[i]; list.push({ l: l, v: l.visible }); VB_snapshot(l, list); }
  return list;
}
function VB_showTree(l) { l.visible = true; for (var i = 0; i < l.layers.length; i++) VB_showTree(l.layers[i]); }
// ---- label callouts: re-route leaders after labels are dragged ---------------------------------------------------------------
// Items (made by render_world.py): text <id>_label on LABELS/Labels - *, its halo or box <id>_label_halo|_box on Label Backing,
// leader <id>_leader + casing <id>_leader_casing on Leaders (open paths anchor -> label), anchor dot <id>_leader_dot on Leader Anchors.
// Page coordinates below = points from the artboard's top-left, y down (the same space the SVG was written in).
var VB_LABEL_LAYERS = ["Labels - Districts", "Labels - Streets", "Labels - Buildings", "Labels - Rooms"];
var VB_lc = {};   // id -> signature of the last seen label bounds + anchor (poll: only changed callouts are re-routed)
// leader from a fixed anchor to a label box b=[l, t, r, bt]; same rules as label_offset.route_leader (python)
function VB_route(anchor, b, style, shelf, gap) {
  var l = b[0], t = b[1], r = b[2], bt = b[3], ax = anchor[0], ay = anchor[1], cx = (l + r) / 2, cy = (t + bt) / 2;
  if (l - 1 <= ax && ax <= r + 1 && t - 1 <= ay && ay <= bt + 1) return null;
  if (ax < l - gap || ax > r + gap) {
    var side = ax < l ? 1 : -1, end = side > 0 ? [l - gap, cy] : [r + gap, cy], knee = [end[0] - side * shelf, cy];
    if (style === "elbow" && shelf > 0 && (knee[0] - ax) * side > 1.5 && Math.abs(ay - cy) > 1) return [anchor, knee, end];
    return [anchor, end];
  }
  return [anchor, ay < t ? [cx, t - gap] : [cx, bt + gap]];
}
function VB_walkItems(container, fn) {
  for (var i = 0; i < container.pageItems.length; i++) fn(container.pageItems[i]);
}
// name -> item for one layer (direct children only)
function VB_nameMap(layer, map, suffixes) {
  var items = VB_direct(layer);
  for (var i = 0; i < items.length; i++) {
    var n = String(items[i].name);
    for (var s = 0; s < suffixes.length; s++) {
      var sf = suffixes[s];
      if (n.length > sf.length && n.substr(n.length - sf.length) === sf) { map[n] = items[i]; break; }
    }
  }
}
function VB_unlockChain(layer, undo) {
  var l = layer;
  while (l && l.typename === "Layer") {
    if (l.locked) { undo.push(l); l.locked = false; }
    try { l = l.parent; } catch (e) { break; }
  }
}
function VB_page(doc, p) { var ab = doc.artboards[0].artboardRect; return [p[0] - ab[0], ab[1] - p[1]]; }
function VB_doc(pt, doc) { var ab = doc.artboards[0].artboardRect; return [ab[0] + pt[0], ab[1] - pt[1]]; }
function VB_pageBounds(doc, it) {
  var g = it.geometricBounds, ab = doc.artboards[0].artboardRect;
  return [g[0] - ab[0], ab[1] - g[1], g[2] - ab[0], ab[1] - g[3]];
}
function VB_rgbOf(hex) {
  var h = String(hex).replace("#", ""); if (h.length === 3) h = h.charAt(0) + h.charAt(0) + h.charAt(1) + h.charAt(1) + h.charAt(2) + h.charAt(2);
  return [parseInt(h.substr(0, 2), 16), parseInt(h.substr(2, 2), 16), parseInt(h.substr(4, 2), 16)];
}
// Collect callout parts of the document: {texts:{id:item}, groups:{id:group}, leaders, casings, dots, backing}
// A label is either loose (text on its label layer, halo/box on Label Backing) or grouped as <id>_callout (halo + text inside one group,
// created by finalize_labels): one Selection-tool drag moves both. Text found by name <id>_label; if Illustrator did not keep the names, by
// position: the text frame nearest the end of each leader.
function VB_callouts(doc) {
  var m = { texts: {}, groups: {}, leaders: {}, casings: {}, dots: {}, backing: {}, layers: [], unnamed: 0 }, i, j, k;
  var ll = VB_find(doc, "Leaders"), al = VB_find(doc, "Leader Anchors"), bl = VB_find(doc, "Label Backing"), loose = [];
  for (i = 0; i < VB_LABEL_LAYERS.length; i++) {
    var lay = VB_find(doc, VB_LABEL_LAYERS[i]);
    if (!lay) continue;
    m.layers.push(lay);
    var items = VB_direct(lay);
    for (j = 0; j < items.length; j++) {
      var it = items[j], n = String(it.name), id;
      if (it.typename === "GroupItem" && /_callout$/.test(n)) {
        id = n.substr(0, n.length - 8); m.groups[id] = it;
        for (k = 0; k < it.pageItems.length; k++) {
          var ch = String(it.pageItems[k].name);
          if (/_label$/.test(ch)) m.texts[id] = it.pageItems[k];
          else if (/_label_(halo|box)$/.test(ch)) m.backing[id] = it.pageItems[k];
          else if (it.pageItems[k].typename === "TextFrame") m.texts[id] = it.pageItems[k];
        }
      } else if (/_label$/.test(n) && n.length > 6) m.texts[n.substr(0, n.length - 6)] = it;
      else if (it.typename === "TextFrame" && n.indexOf("hidden") < 0) loose.push(it);
    }
  }
  var t2 = {}, t3 = {}, t4 = {};
  if (ll) { VB_nameMap(ll, t2, ["_leader", "_leader_casing"]); m.layers.push(ll); }
  for (k in t2) if (t2.hasOwnProperty(k)) { if (/_leader_casing$/.test(k)) m.casings[k.substr(0, k.length - 14)] = t2[k]; else m.leaders[k.substr(0, k.length - 7)] = t2[k]; }
  if (al) { VB_nameMap(al, t3, ["_leader_dot"]); m.layers.push(al); }
  for (k in t3) if (t3.hasOwnProperty(k)) m.dots[k.substr(0, k.length - 11)] = t3[k];
  if (bl) { VB_nameMap(bl, t4, ["_label_halo", "_label_box"]); m.layers.push(bl); }
  for (k in t4) if (t4.hasOwnProperty(k)) m.backing[k.replace(/_label_(halo|box)$/, "")] = t4[k];
  // fallback when text frames carry no usable name: leader end -> nearest loose text frame
  for (k in m.leaders) {
    if (!m.leaders.hasOwnProperty(k) || m.texts[k] || !loose.length) continue;
    var lp = m.leaders[k].pathPoints; if (!lp.length) continue;
    var e = VB_page(doc, lp[lp.length - 1].anchor), best = null, bd = 1e9;
    for (j = 0; j < loose.length; j++) {
      var b2 = VB_pageBounds(doc, loose[j]), dx = Math.max(b2[0] - e[0], 0, e[0] - b2[2]), dy = Math.max(b2[1] - e[1], 0, e[1] - b2[3]), d = Math.sqrt(dx * dx + dy * dy);
      if (d < bd) { bd = d; best = loose[j]; }
    }
    if (best && bd < 14) { m.texts[k] = best; m.unnamed++; try { best.name = k + "_label"; } catch (e2) {} }
  }
  return m;
}
// Group halo/box + text of every label that is not yet grouped into <id>_callout (on the text's layer). -> number grouped
function VB_finalizeLabels(doc, m, repair) {
  var n = 0, id, undo = [], i;
  for (id in m.texts) {
    if (!m.texts.hasOwnProperty(id) || m.groups[id]) continue;
    var tx = m.texts[id], hal = m.backing[id];
    if (!hal) continue;
    if (!n) for (i = 0; i < m.layers.length; i++) VB_unlockChain(m.layers[i], undo);
    try {
      var lay = tx.layer, g = lay.groupItems.add();
      g.name = id + "_callout";
      // z-order inside the group: PLACEATEND = bottom of the stack. The text goes in first, then the halo/box goes under it.
      // (Was halo first, then text at the end: the text ended up BELOW its own halo, hidden by it.)
      tx.move(g, ElementPlacement.PLACEATEND);
      hal.move(g, ElementPlacement.PLACEATEND);
      m.groups[id] = g; n++;
    } catch (e) {}
  }
  // repair callouts grouped by the old code (halo on top of its text): the text goes back to the front of its group
  m.fixed = 0;
  for (id in m.groups) {
    if (!repair) break;                                              // the live reroute poll skips this pass (cost: 2 reads per callout)
    if (!m.groups.hasOwnProperty(id)) continue;
    try {
      var gg = m.groups[id], tt = m.texts[id];
      if (!tt || gg.pageItems.length < 2) continue;
      var tn = String(tt.name), top = String(gg.pageItems[0].name);
      if (tn === "" || top === tn) continue;                       // text already in front (or cannot be told apart from its halo)
      if (!undo.length) for (i = 0; i < m.layers.length; i++) VB_unlockChain(m.layers[i], undo);
      tt.move(gg, ElementPlacement.PLACEATBEGINNING); m.fixed++;
    } catch (e2) {}
  }
  for (i = 0; i < undo.length; i++) { try { undo[i].locked = true; } catch (e) {} }
  return n;
}
function VB_rerouteLeaders(doc, a) {
  var m = VB_callouts(doc), out = { callouts: 0, rerouted: 0, hidden_leaders: 0, synced_backing: 0, unchanged: 0, ids: [], grouped: 0 };
  if (a.group) { out.grouped = VB_finalizeLabels(doc, m); }
  var st = a.style || {}, styleName = st.style || "elbow", shelf = st.shelf === undefined ? 7 : st.shelf, gap = st.gap === undefined ? 2 : st.gap;
  var only = null, i, id;
  if (a.ids && a.ids.length) { only = {}; for (i = 0; i < a.ids.length; i++) only[a.ids[i]] = true; }
  var undo = [], opened = false;
  for (id in m.texts) {
    if (!m.texts.hasOwnProperty(id)) continue;
    if (only && !only[id]) continue;
    var tx = m.texts[id], ld = m.leaders[id], dot = m.dots[id], hal = m.backing[id];
    var tb = VB_pageBounds(doc, tx), tcx = (tb[0] + tb[2]) / 2, tcy = (tb[1] + tb[3]) / 2;
    var anchor = null;
    if (dot) { var db = VB_pageBounds(doc, dot); anchor = [(db[0] + db[2]) / 2, (db[1] + db[3]) / 2]; }
    else if (ld && ld.pathPoints.length) { anchor = VB_page(doc, ld.pathPoints[0].anchor); }
    var sig = Math.round(tb[0] * 10) + "," + Math.round(tb[1] * 10) + "," + Math.round(tb[2] * 10) + "," + Math.round(tb[3] * 10) + "|" + (anchor ? Math.round(anchor[0] * 10) + "," + Math.round(anchor[1] * 10) : "-");
    out.callouts++;
    var note = ""; try { note = String(tx.note); } catch (e) {}
    var needNote = (note.indexOf("vb_orig=") !== 0);
    var changed = (VB_lc[id] !== undefined && VB_lc[id] !== sig);
    if (a.changed_only && !changed && !needNote) { if (VB_lc[id] === undefined) VB_lc[id] = sig; out.unchanged++; continue; }
    if (a.changed_only && VB_lc[id] === undefined && !needNote) { VB_lc[id] = sig; continue; }
    if (!opened) { for (i = 0; i < m.layers.length; i++) VB_unlockChain(m.layers[i], undo); opened = true; }
    if (needNote) {   // remember where the generator put the label: the backing copy still sits there; else the current position
      var oc = [tcx, tcy];
      if (hal) { var hb = VB_pageBounds(doc, hal); oc = [(hb[0] + hb[2]) / 2, (hb[1] + hb[3]) / 2]; }
      try { tx.note = "vb_orig=" + oc[0].toFixed(2) + "," + oc[1].toFixed(2); } catch (e) {}
      if (a.changed_only && VB_lc[id] === undefined) { VB_lc[id] = sig; if (!(hal && (Math.abs(oc[0] - tcx) > 0.3 || Math.abs(oc[1] - tcy) > 0.3))) continue; }
    }
    // the halo / box copy follows its text (it is a separate item on Label Backing)
    if (hal && !m.groups[id] && a.sync_backing !== false) {
      var hb2 = VB_pageBounds(doc, hal), dx = tcx - (hb2[0] + hb2[2]) / 2, dy = tcy - (hb2[1] + hb2[3]) / 2;
      if (Math.abs(dx) > 0.25 || Math.abs(dy) > 0.25) { try { hal.translate(dx, -dy); out.synced_backing++; } catch (e) {} }
    }
    if (ld && anchor) {
      var pts = VB_route(anchor, tb, styleName, shelf, gap), parts = [ld, m.casings[id]];
      for (i = 0; i < parts.length; i++) {
        var pi = parts[i]; if (!pi) continue;
        if (!pts) { pi.hidden = true; continue; }
        pi.hidden = false;
        var dp = []; for (var q = 0; q < pts.length; q++) dp.push(VB_doc(pts[q], doc));
        pi.setEntirePath(dp);
        if (i === 0 && st.color) { pi.strokeColor = VB_rgb(VB_rgbOf(st.color)); }
        if (i === 0 && st.width) pi.strokeWidth = st.width;
        if (i === 1 && st.casing_color) pi.strokeColor = VB_rgb(VB_rgbOf(st.casing_color));
        if (i === 1 && st.casing_width) pi.strokeWidth = st.casing_width;
      }
      if (!pts) out.hidden_leaders++;
      out.rerouted++; out.ids.push(id);
    }
    VB_lc[id] = sig;
  }
  for (i = 0; i < undo.length; i++) { try { undo[i].locked = true; } catch (e) {} }
  return out;
}
// positions of every label (page pt) + where it was generated (item note) + its anchor dot, for the panel's 'Pin label positions'
function VB_readLabels(doc) {
  var m = VB_callouts(doc), res = [], id;
  for (id in m.texts) {
    if (!m.texts.hasOwnProperty(id)) continue;
    var tx = m.texts[id], b = VB_pageBounds(doc, tx), o = { id: id + "_label", cx: (b[0] + b[2]) / 2, cy: (b[1] + b[3]) / 2, w: b[2] - b[0], h: b[3] - b[1] };
    var note = ""; try { note = String(tx.note); } catch (e) {}
    if (note.indexOf("vb_orig=") === 0) { var pp = note.substr(8).split(","); o.ref = [parseFloat(pp[0]), parseFloat(pp[1])]; }
    else if (m.backing[id]) { var hb = VB_pageBounds(doc, m.backing[id]); o.ref = [(hb[0] + hb[2]) / 2, (hb[1] + hb[3]) / 2]; }
    if (m.dots[id]) { var db = VB_pageBounds(doc, m.dots[id]); o.anchor = [(db[0] + db[2]) / 2, (db[1] + db[3]) / 2]; }
    res.push(o);
  }
  return res;
}
// first item named `name` in any layer (recursive)
function VB_findItem(container, name) {
  var i;
  for (i = 0; i < container.layers.length; i++) {
    var l = container.layers[i], items = VB_direct(l);
    for (var j = 0; j < items.length; j++) if (String(items[j].name) === name) return items[j];
    var r = VB_findItem(l, name); if (r) return r;
  }
  return null;
}
// ---- curved labels: real type on a path -------------------------------------------------------------------------------------------
// Illustrator flattens SVG <textPath> on import (and blocks on a dialog), so render_world writes <svg>.curved.json and leaves a straight
// fallback label per entry. Here each fallback (and its halo copy) is replaced by path type that follows the street / river centreline.
// Entry: {id, layer, text, points[[x,y] page pt], size, font, bold, italic, small_caps, color, letter_spacing, halo{color,width,opacity}|null}.
// Kept across a host.jsx reload ($.evalFile re-runs this file; `var` keeps the existing global's value when it is set).
var VB_fontCache = (typeof VB_fontCache === "object" && VB_fontCache) ? VB_fontCache : {};
var VB_fontScans = (typeof VB_fontScans === "number") ? VB_fontScans : 0;   // how often the slow app.textFonts walk ran (reported by label_preflight)
// PostScript names to try with app.textFonts.getByName before walking every installed font (that walk reads 3 properties per font and takes
// seconds to minutes with a big font library). Never shows a missing-font dialog: a miss is a caught exception.
function VB_fontNames(family, bold, italic) {
  var f = String(family).replace(/\s+/g, ""), out = [];
  var suf = bold && italic ? ["-BoldItalicMT", "-BoldItalic", "-BoldOblique", "-BoldIt"] : bold ? ["-BoldMT", "-Bold"] : italic ? ["-ItalicMT", "-Italic", "-Oblique", "-It"] : ["MT", "", "-Regular", "-Roman", "-Book"];
  for (var i = 0; i < suf.length; i++) out.push(f + suf[i]);
  return out;
}
function VB_font(family, bold, italic) {
  var key = family + "|" + bold + "|" + italic;
  if (VB_fontCache.hasOwnProperty(key)) return VB_fontCache[key];
  var cand = VB_fontNames(family, bold, italic);
  for (var c = 0; c < cand.length; c++) {
    try { var g = app.textFonts.getByName(cand[c]); if (g) { VB_fontCache[key] = g; return g; } } catch (e) {}
  }
  VB_fontScans++;
  var best = null, bs = -1;
  for (var i = 0; i < app.textFonts.length; i++) {
    var f = app.textFonts[i];
    if (String(f.family).toLowerCase() !== String(family).toLowerCase()) continue;
    var nm = String(f.name), st = String(f.style), sc = 0;
    var isB = /bold|black|heavy/i.test(st + nm), isI = /italic|oblique/i.test(st + nm);
    if (isB === !!bold) sc += 2; if (isI === !!italic) sc += 2;
    if (/regular|roman|book|normal/i.test(st)) sc += 1;
    if (/cond|narrow|light|thin|semi|medium|extra|ultra/i.test(st + nm)) sc -= 1;
    if (sc > bs) { bs = sc; best = f; }
  }
  VB_fontCache[key] = best; return best;
}
// Text frame called `name` anywhere (inside the callout groups Illustrator makes on SVG import too). The halo copies lose their names on import,
// so for "<id>_halo" an unnamed text frame with the same contents whose centre is nearest the label wins.
// One pass over doc.textFrames -> {named: {name: frame}, unnamed: [frame]} (each DOM read is slow; the old per-label rescans of every text frame
// in the document were O(labels x frames) and took minutes on a big map).
function VB_textIndex(doc) {
  var idx = { named: {}, unnamed: [] }, tfs = doc.textFrames, n = tfs.length;
  for (var i = 0; i < n; i++) {
    var t = tfs[i], nm = "";
    try { nm = String(t.name); } catch (e) { continue; }
    if (nm === "") idx.unnamed.push(t);
    else if (!idx.named.hasOwnProperty(nm)) idx.named[nm] = t;
  }
  return idx;
}
function VB_textNamed(doc, name, c, idx) {
  if (!idx) idx = VB_textIndex(doc);
  if (idx.named.hasOwnProperty(name)) return idx.named[name];
  if (!c) return null;
  var base = idx.named.hasOwnProperty(c.id) ? idx.named[c.id] : null; if (!base) return null;
  var bb = base.geometricBounds, cx = (bb[0] + bb[2]) / 2, cy = (bb[1] + bb[3]) / 2, bd = 1e9, best = null, bc = base.contents;
  for (var i = 0; i < idx.unnamed.length; i++) {
    var t = idx.unnamed[i]; if (!t || t === base) continue;
    try { if (t.contents !== bc) continue; } catch (e) { continue; }
    var g = t.geometricBounds, d = Math.abs((g[0] + g[2]) / 2 - cx) + Math.abs((g[1] + g[3]) / 2 - cy);
    if (d < bd && d < 20) { bd = d; best = t; }
  }
  return best;
}
function VB_applyCurved(doc, svgPath) {
  var res = { made: 0, skipped: 0, ids: [] };
  var jf = new File(String(svgPath) + ".curved.json");
  if (!jf.exists) return res;
  jf.encoding = "UTF-8"; jf.open("r"); var txt = jf.read(); jf.close();
  var data = eval("(" + txt + ")"), items = data.items || [];
  if (!items.length) return res;
  var tidx = VB_textIndex(doc);
  for (var i = 0; i < items.length; i++) {
    var c = items[i], fb = VB_textNamed(doc, c.id, null, tidx);
    if (!fb || !c.points || c.points.length < 2) { res.skipped++; continue; }
    var undo = [], lyr = fb.layer, hb = VB_textNamed(doc, c.id + "_halo", c, tidx);
    try {
      VB_unlockChain(lyr, undo);
      var hl = null;
      if (hb) { hl = hb.layer; VB_unlockChain(hl, undo); }
      var pts = [];
      for (var k = 0; k < c.points.length; k++) pts.push(VB_doc(c.points[k], doc));
      var fnt = VB_font(c.font, c.bold, c.italic);
      var body = c.small_caps ? String(c.text).toUpperCase() : String(c.text);
      var mk = function (layer, name, fill, stroke, sw, op) {
        var pp = layer.pathItems.add(); pp.setEntirePath(pts); pp.filled = false; pp.stroked = false; pp.name = name + "_tp";
        var tf = layer.textFrames.pathText(pp); tf.contents = body; tf.name = name;
        var ca = tf.textRange.characterAttributes;
        ca.size = c.size; if (fnt) ca.textFont = fnt;
        if (c.letter_spacing) ca.tracking = Math.round(c.letter_spacing / c.size * 1000);
        var col = VB_rgbOf(fill); ca.fillColor = VB_rgb(col);
        if (stroke) { ca.strokeColor = VB_rgb(VB_rgbOf(stroke)); ca.strokeWeight = sw; } else { ca.strokeColor = new NoColor(); }
        tf.textRange.paragraphAttributes.justification = Justification.CENTER;
        try { tf.opacity = op; } catch (e) {}
        return tf;
      };
      // z-order: halo first (below), then the label; each goes where the fallback of that kind was
      if (c.halo && hb) { var h2 = mk(hl, c.id + "_halo", c.halo.color, c.halo.color, c.halo.width, (c.halo.opacity || 1) * 100); h2.move(hb, ElementPlacement.PLACEBEFORE); }
      var t2 = mk(lyr, c.id, c.color, null, 0, 100); t2.move(fb, ElementPlacement.PLACEBEFORE);
      if (hb) { for (var ui = 0; ui < tidx.unnamed.length; ui++) if (tidx.unnamed[ui] === hb) tidx.unnamed[ui] = null; try { hb.remove(); } catch (e) {} }
      fb.remove(); tidx.named[c.id] = t2;
      res.made++; res.ids.push(c.id);
    } catch (e) { res.skipped++; res.error = String(e); }
    for (var u = 0; u < undo.length; u++) { try { undo[u].locked = true; } catch (e) {} }
  }
  return res;
}
// Top-level raster-heavy layers (UNDERLAY, ART *) that are visible and not an ancestor of one of the target layers: hidden while a layer replace runs so
// Illustrator does not redraw a big embedded image after every single edit. Returns [{l, v}] for VB_restoreHeavy.
function VB_hideHeavy(doc, targetNames) {
  var out = [];
  for (var i = 0; i < doc.layers.length; i++) {
    var l = doc.layers[i];
    if (!(/^UNDERLAY$/i.test(l.name) || /^ART(\s|$|-)/i.test(l.name))) continue;
    var anc = false;
    for (var t = 0; t < targetNames.length; t++) { if (l.name === targetNames[t] || VB_find(l, targetNames[t])) { anc = true; break; } }
    if (anc || !l.visible) continue;
    try { l.visible = false; out.push({ l: l, v: true }); } catch (e) {}
  }
  return out;
}
function VB_restoreHeavy(list) { for (var i = 0; i < list.length; i++) { try { list[i].l.visible = list[i].v; } catch (e) {} } }
// ---- surgical item edits (panel lib/itemops.js): delete / replace / rename the items of some entity ids, no render, no whole-layer replace ----------
// Names: <id>, <id>_label(_halo|_box)(_tp), <id>_callout, <id>_leader(_casing|_dot), <id>_marker|_marknum, <id>_name(_halo), flat_<id>, <id>_kerb<n>,
// mk_<id>_start|end, <id>_door<n>|_roof|_chimney|_lot|_fence<n>. Illustrator shows '_' of an SVG id as '_', '_x5F_' or (old imports) a space.
// VB_itemRegex must build the same string as itemops.regexSource (test/test_itemops.js compares them).
var VB_ITEM_FAMILY = "label(?:_halo|_box)?(?:_tp)?|callout|leader(?:_casing|_dot)?|marker|marknum|name(?:_halo)?(?:_tp)?|kerb\\d+|door\\d+|roof|chimney|lot|fence\\d+|start|end";
function VB_escRe(s) { return String(s).replace(/[.*+?^${}()|[\]\\\/-]/g, "\\$&"); }
function VB_itemRegex(ids, match) {
  var a = [];
  for (var i = 0; i < ids.length; i++) a.push(VB_escRe(ids[i]));
  var alt = a.join("|");
  if (!alt) return "^$.";
  if (match === "exact") return "^(?:" + alt + ")$";
  if (match === "prefix") return "^(?:" + alt + ")(?:[_ ].*)?$";
  return "^(?:flat_|mk_)?(?:" + alt + ")(?:_(?:" + VB_ITEM_FAMILY + "))?$";
}
function VB_decName(n) { return String(n === null || n === undefined ? "" : n).replace(/_x5F_/g, "_").replace(/^\s+|\s+$/g, ""); }
function VB_nameHit(n, res) {
  var a = VB_decName(n), b = a.replace(/ /g, "_");
  for (var i = 0; i < res.length; i++) { if (res[i].test(a) || (b !== a && res[i].test(b))) return true; }
  return false;
}
// entity id of an item name (for the not_found report): the name itself when it is an id, else without flat_ / mk_ and the family suffix
function VB_baseId(n, set) {
  var a = VB_decName(n).replace(/ /g, "_");
  if (set[a]) return a;
  return a.replace(/^(?:flat_|mk_)/, "").replace(new RegExp("_(?:" + VB_ITEM_FAMILY + ")$"), "");
}
// make a layer editable: unlock it and its locked parents, show it and its hidden parents (Illustrator refuses edits on locked or hidden layers). -> undo
function VB_layerOpen(l) {
  var u = { locked: [], hidden: [] }, p = l;
  while (p && p.typename === "Layer") {
    try { if (p.locked) { p.locked = false; u.locked.push(p); } } catch (e) {}
    try { if (!p.visible) { p.visible = true; u.hidden.push(p); } } catch (e2) {}
    try { p = p.parent; } catch (e3) { break; }
  }
  return u;
}
function VB_layerClose(u) {
  var i;
  for (i = 0; i < u.hidden.length; i++) { try { u.hidden[i].visible = false; } catch (e) {} }
  for (i = 0; i < u.locked.length; i++) { try { u.locked[i].locked = true; } catch (e2) {} }
}
function VB_removeItem(it) { try { it.locked = false; } catch (e) {} try { it.hidden = false; } catch (e2) {} it.remove(); }
// first item called `name` (or its _x5F_ form) directly on the layer, via the collection's getByName (no walk over every item); null when absent
function VB_named(lay, name) {
  var forms = [name];
  if (name.indexOf("_") >= 0) forms.push(name.replace(/_/g, "_x5F_"));
  for (var i = 0; i < forms.length; i++) { try { var it = lay.pageItems.getByName(forms[i]); if (it) return it; } catch (e) {} }
  return null;
}
function VB_allLayerNames(container, out) {
  for (var i = 0; i < container.layers.length; i++) { var l = container.layers[i]; if (l.name !== VB_LASSO_LAYER) out.push(l.name); VB_allLayerNames(l, out); }
  return out;
}
// a: {targets:[{layer, names:[exact], patterns:[regex src]}]} or {ids, layers, match}; max (item cap), budget_ms (default 80 % of timeout_ms)
function VB_deleteItems(doc, a) {
  var res = { removed: 0, per_layer: {}, not_found: [], skipped_locked: [], missing_layers: [], truncated: false }, ids = a.ids || [], set = {}, hit = {}, i, j, k;
  for (i = 0; i < ids.length; i++) set[String(ids[i])] = true;
  var max = a.max || 20000, t0 = new Date().getTime(), budget = a.budget_ms || Math.max(5000, (a.timeout_ms || 60000) * 0.8);
  var targets = a.targets;
  if (!targets) {
    var src = VB_itemRegex(ids, a.match || "family"), ln = (a.layers && a.layers.length) ? a.layers : VB_allLayerNames(doc, []);
    targets = [];
    for (i = 0; i < ln.length; i++) targets.push({ layer: ln[i], names: [], patterns: [src] });
  }
  for (i = 0; i < targets.length && !res.truncated; i++) {
    var t = targets[i], lay = VB_find(doc, t.layer), cnt = 0, undo = null, names = t.names || [], pats = t.patterns || [];
    if (!lay) { res.missing_layers.push(t.layer); continue; }
    try {
      for (j = 0; j < names.length; j++) {
        for (k = 0; k < 50; k++) {                     // more than one item of the same name (a double import) are all removed
          var it = VB_named(lay, names[j]);
          if (!it) break;
          if (!undo) undo = VB_layerOpen(lay);
          try { VB_removeItem(it); cnt++; hit[VB_baseId(names[j], set)] = true; } catch (e) { res.skipped_locked.push(t.layer + ": " + names[j]); break; }
        }
      }
      if (pats.length) {
        var rx = [];
        for (j = 0; j < pats.length; j++) rx.push(new RegExp(pats[j]));
        var items = VB_direct(lay);
        for (j = items.length - 1; j >= 0; j--) {
          if (cnt + res.removed >= max) { res.truncated = true; break; }
          var nm = "";
          try { nm = String(items[j].name); } catch (e4) { continue; }
          if (!nm || !VB_nameHit(nm, rx)) continue;
          if (!undo) undo = VB_layerOpen(lay);
          try { VB_removeItem(items[j]); cnt++; hit[VB_baseId(nm, set)] = true; } catch (e5) { res.skipped_locked.push(t.layer + ": " + VB_decName(nm)); }
        }
      }
    } finally { if (undo) VB_layerClose(undo); }
    if (cnt) res.per_layer[t.layer] = (res.per_layer[t.layer] || 0) + cnt;
    res.removed += cnt;
    if (res.removed >= max || new Date().getTime() - t0 > budget) res.truncated = true;
  }
  for (i = 0; i < ids.length; i++) if (!hit[String(ids[i])]) res.not_found.push(String(ids[i]));
  res.deleted = res.removed;
  return res;
}
// copy every item of the named layers of an SVG into the active document: an item with the same name on the same layer is replaced in place (z-order kept),
// a new name is added on top of its layer. Nothing else is touched (vs replace_layer, which empties the layer first).
function VB_replaceItems(tdoc, sdoc, names, out) {
  for (var i = 0; i < names.length; i++) {
    var sl = VB_find(sdoc, names[i]);
    if (!sl) { out.missing.push(names[i]); continue; }
    var tl = VB_ensureLike(tdoc, sl), u = VB_layerOpen(tl);
    try {
      var src = VB_direct(sl);
      for (var k = src.length - 1; k >= 0; k--) {
        var nm = VB_decName(src[k].name), old = nm ? VB_named(tl, nm) : null, dup;
        if (old) {
          try { dup = src[k].duplicate(old, ElementPlacement.PLACEBEFORE); } catch (e) { dup = src[k].duplicate(tl, ElementPlacement.PLACEATBEGINNING); try { dup.move(old, ElementPlacement.PLACEBEFORE); } catch (e2) {} }
          try { dup.name = "__vb_new__"; } catch (e3) {}
          for (var g = 0; g < 50 && old; g++) { VB_removeItem(old); old = VB_named(tl, nm); }
          out.replaced++;
        } else { dup = src[k].duplicate(tl, ElementPlacement.PLACEATBEGINNING); out.added++; }
        try { dup.name = nm; } catch (e4) {}
      }
    } finally { VB_layerClose(u); }
  }
}
// rename the items of entity `from` to `to` (same family suffixes), optional new label text on <to>_label / <to>_label_halo text frames
function VB_renameItems(doc, renames, layers, out) {
  var ln = (layers && layers.length) ? layers : VB_allLayerNames(doc, []), rx = [], i, j, r;
  for (i = 0; i < renames.length; i++) rx.push(new RegExp(VB_itemRegex([renames[i].from], "family")));
  for (i = 0; i < ln.length; i++) {
    var lay = VB_find(doc, ln[i]);
    if (!lay) continue;
    var items = VB_direct(lay), undo = null;
    try {
      for (j = 0; j < items.length; j++) {
        var nm = VB_decName(items[j].name).replace(/ /g, "_");
        for (r = 0; r < renames.length; r++) {
          if (!rx[r].test(nm)) continue;
          var f = String(renames[r].from), to = String(renames[r].to), pre = "";
          if (nm.indexOf("flat_" + f) === 0 && nm !== f) pre = "flat_"; else if (nm.indexOf("mk_" + f) === 0 && nm !== f) pre = "mk_";
          var nn = pre + to + nm.substr(pre.length + f.length);
          if (!undo) undo = VB_layerOpen(lay);
          try {
            items[j].name = nn; out.renamed++;
            if (renames[r].text !== undefined && renames[r].text !== null && items[j].typename === "TextFrame" && /_label(_halo)?$/.test(nn)) { items[j].contents = String(renames[r].text); out.texts++; }
          } catch (e) { out.failed.push(ln[i] + ": " + nm); }
          break;
        }
      }
    } finally { if (undo) VB_layerClose(undo); }
  }
}
// app.open with alerts off ("Text on Path will be Flattened", missing fonts ...): a modal dialog blocks the whole ExtendScript queue.
function VB_openQuiet(f) {
  var old = app.userInteractionLevel;
  try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}
  try { return app.open(f); } finally { try { app.userInteractionLevel = old; } catch (e) {} }
}
// Every host call runs with alerts off (restored after): a modal dialog Illustrator opens while a script runs (Swatch / Font conflict when items are
// duplicated from the SVG document, missing fonts, 'Text on Path will be flattened' ...) is often behind the main window, waits for a click that never
// comes, and Illustrator shows 'Not Responding' at 0 % CPU.
function VB_run(json) {
  var vbQuiet = VB_quietBegin();
  try { return VB_runInner(json); } finally { VB_quietEnd(vbQuiet); }
}
function VB_runInner(json) {
  try {
    var a = eval("(" + json + ")");
    var out = { ok: true };
    switch (a.action) {
      case "ping":
        out.version = app.version; out.docs = app.documents.length; break;
      case "new_document": {
        var w = (a.width_in || 17), h = (a.height_in || 11);
        if (a.landscape !== false && h > w) { var t = w; w = h; h = t; }
        app.documents.add(DocumentColorSpace.RGB, w * 72, h * 72);
        out.width_in = w; out.height_in = h; break;
      }
      case "ensure_layers": {
        if (app.documents.length === 0) throw new Error("no open document");
        var d = app.activeDocument, names = a.names || [];
        for (var i = 0; i < names.length; i++) VB_layer(d, names[i]);
        out.layers = names; break;
      }
      case "place_svg": {
        if (!a.path) throw new Error("path required");
        var f = new File(a.path);
        if (!f.exists) throw new Error("file not found: " + a.path);
        var target = app.documents.length ? app.activeDocument : null;
        var svg = VB_openQuiet(f);  // SVG <g id> groups become layers; import warnings must not open a modal dialog (it hangs the job queue)
        if (!target || a.mode === "open") { out.mode = "opened"; out.curved = VB_applyCurved(svg, f.fsName); break; }
        var n = 0;
        for (var li = svg.layers.length - 1; li >= 0; li--) {
          var sl = svg.layers[li], tl = VB_layer(target, sl.name);
          for (var pi = sl.pageItems.length - 1; pi >= 0; pi--) {
            sl.pageItems[pi].duplicate(tl, ElementPlacement.PLACEATBEGINNING); n++;
          }
        }
        svg.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = target;
        out.items = n; out.curved = VB_applyCurved(target, f.fsName); break;
      }
      case "replace_layer": {
        // Clear and redraw only the named GEN layers from an SVG; ART layers are never touched.
        // Built to stay fast on a document with a big embedded underlay / raster ART layers (a screen redraw of the raster after EVERY edit froze Illustrator
        // for minutes): raster-heavy top layers (UNDERLAY, ART *) are hidden once for the whole replace and restored, no layer is unlocked / shown / hidden
        // unless it has to be, the old items go in one removeAll() call, the new ones are copied first and the SVG document is closed before the target
        // document is touched again, and no clipboard is used.
        if (!a.path) throw new Error("path required");
        var names = a.names || [];
        if (!names.length) throw new Error("names required");
        for (var ni = 0; ni < names.length; ni++) if (VB_isArt(names[ni])) throw new Error("refusing to replace ART layer: " + names[ni]);
        if (app.documents.length === 0) throw new Error("no open document");
        var rf = new File(a.path);
        if (!rf.exists) throw new Error("file not found: " + a.path);
        var tdoc = app.activeDocument;
        var hidden = VB_hideHeavy(tdoc, names);          // [{l, v}] layers hidden for the duration
        var rsvg = null, replaced = [], missing = [], moved = 0;
        try {
          rsvg = VB_openQuiet(rf);
          var plan = [];                                  // per name: target layer, its previous lock/visible state, new items already copied in
          for (var ri = 0; ri < names.length; ri++) {
            var sl2 = VB_find(rsvg, names[ri]);
            if (!sl2) { missing.push(names[ri]); continue; }
            var tl2 = VB_ensureLike(tdoc, sl2);
            var wasLocked = tl2.locked, wasVisible = tl2.visible;
            if (wasLocked) tl2.locked = false;
            if (!wasVisible) tl2.visible = true;
            var oldCount = tl2.pageItems.length, srcItems = VB_direct(sl2);
            for (var si = srcItems.length - 1; si >= 0; si--) { srcItems[si].duplicate(tl2, ElementPlacement.PLACEATBEGINNING); moved++; }
            plan.push({ l: tl2, name: names[ri], locked: wasLocked, visible: wasVisible, oldCount: oldCount, added: srcItems.length });
          }
          try { rsvg.close(SaveOptions.DONOTSAVECHANGES); } catch (e) {}
          rsvg = null;
          app.activeDocument = tdoc;
          for (var pi2 = 0; pi2 < plan.length; pi2++) {   // the old items are the ones after the freshly added ones (PLACEATBEGINNING)
            var pl2 = plan[pi2], l2 = pl2.l;
            if (l2.layers.length === 0 && l2.pageItems.length >= pl2.added) {
              var tot = l2.pageItems.length, keep = pl2.added;
              for (var ki = tot - 1; ki >= keep; ki--) { var it2 = l2.pageItems[ki]; try { it2.locked = false; it2.hidden = false; } catch (e) {} it2.remove(); }
            } else {
              var old = VB_direct(l2);                    // layer with sublayers: only its own items, skipping the new ones at the front
              for (var oi = old.length - 1; oi >= pl2.added; oi--) { try { old[oi].locked = false; old[oi].hidden = false; } catch (e) {} old[oi].remove(); }
            }
            l2.locked = (a.restore_lock === false) ? false : pl2.locked;
            if (!pl2.visible) l2.visible = false;
            replaced.push(pl2.name);
          }
        } finally {
          if (rsvg) { try { rsvg.close(SaveOptions.DONOTSAVECHANGES); } catch (e) {} try { app.activeDocument = tdoc; } catch (e) {} }
          VB_restoreHeavy(hidden);
        }
        out.curved = (a.curved === false) ? { made: 0, skipped: 0, ids: [], deferred: true } : VB_applyCurved(tdoc, rf.fsName);   // curved:false = a separate apply_curved step
        out.replaced = replaced; out.missing = missing; out.items = moved; out.hidden_heavy = hidden.length;
        if (missing.length && a.strict !== false) out.ok = false, out.error = "layers not in SVG: " + missing.join(", ");
        break;
      }
      case "lock_layers": {
        if (app.documents.length === 0) throw new Error("no open document");
        var ld = app.activeDocument, lnames = a.names || [], lk = (a.locked !== false), done = [], nf = [];
        for (var li2 = 0; li2 < lnames.length; li2++) {
          var ll = VB_find(ld, lnames[li2]);
          if (!ll) { nf.push(lnames[li2]); continue; }
          ll.locked = lk; done.push(lnames[li2]);
        }
        out.locked = lk; out.layers = done; out.not_found = nf;
        if (nf.length) out.ok = false, out.error = "layers not found: " + nf.join(", ");
        break;
      }
      case "get_doc_info": {
        if (app.documents.length === 0) throw new Error("no open document");
        var gd = app.activeDocument;
        out.name = gd.name; out.artboard = gd.artboards[0].artboardRect; out.layers = [];
        for (var gi = 0; gi < gd.layers.length; gi++) out.layers.push(gd.layers[gi].name);
        try { out.path = gd.fullName.fsName; } catch (e) { out.path = ""; }
        out.selection = gd.selection.length; break;
      }
      case "list_fonts": {
        // installed font families (optionally only those matching a.names) with their PostScript names, to check the Labels tab font list
        var fams = {}, want = a.names || null;
        for (var fi = 0; fi < app.textFonts.length; fi++) {
          var tf = app.textFonts[fi];
          if (!fams[tf.family]) fams[tf.family] = [];
          fams[tf.family].push(tf.name);
        }
        out.families = []; out.missing = [];
        for (var k in fams) if (fams.hasOwnProperty(k) && (!want || VB_inArr(want, k))) out.families.push({ family: k, fonts: fams[k] });
        if (want) for (var wi = 0; wi < want.length; wi++) if (!fams[want[wi]]) out.missing.push(want[wi]);
        break;
      }
      case "get_layer_tree": {
        if (app.documents.length === 0) throw new Error("no open document");
        var walk = function (c) {
          var r = [];
          for (var i = 0; i < c.layers.length; i++) {
            var l = c.layers[i];
            r.push({ name: l.name, visible: l.visible, locked: l.locked, items: l.pageItems.length, children: walk(l) });
          }
          return r;
        };
        out.doc = app.activeDocument.name; out.tree = walk(app.activeDocument); break;
      }
      case "get_selection": {
        // Paths of the current selection; if nothing is selected and `layer` is given, the paths on that layer.
        if (app.documents.length === 0) throw new Error("no open document");
        var sd = app.activeDocument, found = [], src = "selection";
        var selItems = []; for (var si3 = 0; si3 < sd.selection.length && si3 < 5000; si3++) selItems.push(sd.selection[si3]);
        VB_collectPaths(selItems, found);
        if (a.lasso) {
          // lasso mode (capture buttons): report every path (selected ones flagged in_sel, paths of the VB LASSO layer flagged lasso, newest first) and
          // let lib/lasso.js choose; also report what kinds of objects are selected so a useless selection can be explained.
          out.source = "selection"; out.artboard = sd.artboards[0].artboardRect; out.paths = []; out.types = {}; out.sel_count = sd.selection.length;
          for (var ti = 0; ti < selItems.length; ti++) { var tn = selItems[ti].typename; out.types[tn] = (out.types[tn] || 0) + 1; }
          var seen = {};
          for (var lp = 0; lp < found.length && lp < 200; lp++) {
            var li0 = VB_pathInfo(found[lp]), isL = false;
            try { isL = (found[lp].layer.name === VB_LASSO_LAYER); } catch (e) {}
            li0.in_sel = true; li0.lasso = isL; out.paths.push(li0);
            seen[li0.points.length + ":" + (li0.points.length ? li0.points[0].a[0] + "," + li0.points[0].a[1] : "")] = true;
          }
          try {
            var lyr = VB_find(sd, VB_LASSO_LAYER), lfound = [];
            if (lyr) VB_collectPaths(VB_direct(lyr), lfound);
            for (var lq = 0; lq < lfound.length && lq < 20; lq++) {
              var li1 = VB_pathInfo(lfound[lq]), sg = li1.points.length + ":" + (li1.points.length ? li1.points[0].a[0] + "," + li1.points[0].a[1] : "");
              if (seen[sg]) continue;
              li1.in_sel = false; li1.lasso = true; out.paths.push(li1);
            }
          } catch (e4) {}
          if (!out.paths.length && a.layer) {
            var fl = VB_find(sd, a.layer);
            if (fl) {
              var ff = []; VB_collectPaths(VB_direct(fl), ff);
              for (var fq = 0; fq < ff.length && fq < 20; fq++) { var li2 = VB_pathInfo(ff[fq]); li2.in_sel = false; li2.lasso = false; out.paths.push(li2); }
              out.source = "layer " + a.layer;
            }
          }
          break;
        }
        if (!found.length && a.layer) {
          var sl3 = VB_find(sd, a.layer);
          if (!sl3) throw new Error("layer not found: " + a.layer);
          VB_collectPaths(VB_direct(sl3), found); src = "layer " + a.layer;
        }
        out.source = src; out.artboard = sd.artboards[0].artboardRect; out.paths = [];
        for (var pi3 = 0; pi3 < found.length; pi3++) {
          var inf = VB_pathInfo(found[pi3]);
          if (a.closed_only && !inf.closed) continue;
          if (a.open_only && inf.closed) continue;
          out.paths.push(inf);
        }
        if (!out.paths.length) out.ok = false, out.error = "no " + (a.closed_only ? "closed " : a.open_only ? "open " : "") + "path selected" + (a.layer ? " (or on layer " + a.layer + ")" : "");
        break;
      }
      case "lasso_start": {
        // Prepare the helper layer: reuse "VB LASSO" (found by name each call, items cleared, never deleted/recreated), make it active. NO tool switching unless
        // a.select_tool === true (opt-in): app.selectTool is the prime suspect for a hang (ILST 28.2, 2nd call never returned), so by default the user presses P.
        if (app.documents.length === 0) throw new Error("no open document");
        var lsq = VB_quietBegin();
        try {
          var ls0 = app.activeDocument;
          var ll0 = VB_lassoLayer(ls0, true);
          try { ls0.selection = null; } catch (e) {}
          try { ls0.activeLayer = ll0; } catch (e) { out.warn = "could not make layer " + VB_LASSO_LAYER + " active: select it in the Layers panel"; }
          out.layer = VB_LASSO_LAYER; out.tool = "none";
          if (a.select_tool === true && typeof app.selectTool === "function") {
            try { app.selectTool("Adobe Pen Tool"); out.tool = "Adobe Pen Tool"; } catch (e) {}
          }
        } catch (le) { throw new Error("could not prepare the lasso layer: " + le.message); }
        finally { VB_quietEnd(lsq); }
        break;
      }
      case "lasso_draw": {
        // a.rings = [{role: "core"|"outer"|"inner", pts: [[x, y], ...] in document points}]; core is selected afterwards (the Photoshop-style lasso selection)
        if (app.documents.length === 0) throw new Error("no open document");
        var ld0 = app.activeDocument, rings = a.rings || [], drawn = 0, corePath = null, ldq = VB_quietBegin();
        try {
          var ll1 = VB_lassoLayer(ld0, a.keep !== true);
          for (var ri0 = 0; ri0 < rings.length; ri0++) {
            var rg = rings[ri0]; if (!rg.pts || rg.pts.length < 3) continue;
            var core = (rg.role === "core"), np = ll1.pathItems.add();
            np.setEntirePath(rg.pts); np.closed = true; np.filled = false; np.stroked = true;
            try {
              var sc = new RGBColor(); if (core) { sc.red = 255; sc.green = 0; sc.blue = 170; } else { sc.red = 255; sc.green = 150; sc.blue = 220; }
              np.strokeColor = sc; np.strokeWidth = core ? 1.5 : 1; np.strokeDashes = core ? [6, 4] : [3, 5];
              if (!core) np.opacity = 70;
              np.name = core ? "VB Lasso" : ("VB Lasso feather " + rg.role);
            } catch (se) {}
            if (core) corePath = np;
            drawn++;
          }
          var dots = a.dots || [];   // waypoint markers: small magenta dots (no text frames: no font dialogs), capped
          for (var dk = 0; dk < dots.length && dk < 200; dk++) {
            try { var dp = ll1.pathItems.ellipse(dots[dk][1] + 3, dots[dk][0] - 3, 6, 6); var dc = new RGBColor(); dc.red = 255; dc.green = 0; dc.blue = 170; dp.filled = true; dp.fillColor = dc; dp.stroked = false; dp.name = "VB Lasso waypoint " + (dk + 1); } catch (e) {}
          }
          try { ld0.activeLayer = ll1; } catch (e) {}
          out.drawn = drawn; out.selected = false;
          if (corePath && a.select !== false) { try { ld0.selection = [corePath]; out.selected = true; } catch (e) { out.warn = "polygon drawn but could not be selected: " + e.message; } }
        } catch (de) { throw new Error("could not draw the lasso: " + de.message); }
        finally { VB_quietEnd(ldq); }
        break;
      }
      case "lasso_select": {
        // select every item whose bounds centre (mode "center") or all anchors (mode "all") lie inside a.poly (document points)
        if (app.documents.length === 0) throw new Error("no open document");
        if (!a.poly || a.poly.length < 3) throw new Error("no lasso polygon");
        var lsd = app.activeDocument, sst = { hits: [], scanned: 0, skipped: 0, layers: [], truncated: false, cap: 20000 }, lsel = VB_quietBegin();
        try {
          VB_lassoScan(lsd, { poly: a.poly, mode: a.mode === "all" ? "all" : "center", filter: a.filter || null, max: a.max || 5000 }, sst);
          lsd.selection = sst.hits.length ? sst.hits : null;
        } catch (se2) { throw new Error("select inside failed: " + se2.message); }
        finally { VB_quietEnd(lsel); }
        out.selected = sst.hits.length; out.scanned = sst.scanned; out.skipped_layers = sst.skipped; out.layers = sst.layers; out.truncated = sst.truncated;
        if (!sst.hits.length) { out.ok = false; out.error = "no objects inside the lasso on the chosen layers (" + sst.scanned + " scanned, " + sst.skipped + " locked/hidden layers skipped)"; }
        break;
      }
      case "lasso_clear": {
        // default: remove the helper items only (the layer stays, so the next Draw lasso never recreates it); a.remove_layer === true deletes the layer too
        if (app.documents.length === 0) throw new Error("no open document");
        var lcq = VB_quietBegin();
        try {
          var lcd = app.activeDocument, lcl = VB_find(lcd, VB_LASSO_LAYER);
          out.removed = false; out.cleared = 0;
          if (lcl) {
            try { lcd.selection = null; } catch (e) {}
            try {
              lcl.locked = false; lcl.visible = true;
              for (var ci = lcl.pageItems.length - 1; ci >= 0; ci--) { try { var cit = lcl.pageItems[ci]; cit.locked = false; cit.hidden = false; cit.remove(); out.cleared++; } catch (e) {} }
              if (a.remove_layer === true) { lcl.remove(); out.removed = true; }
            } catch (ce) { throw new Error("could not clear layer " + VB_LASSO_LAYER + ": " + ce.message); }
          }
        } finally { VB_quietEnd(lcq); }
        break;
      }
      case "place_image": {
        // rect = [left, top, right, bottom] in page points measured from the artboard's top-left (y down).
        if (app.documents.length === 0) throw new Error("no open document");
        if (!a.path || !a.rect) throw new Error("path and rect required");
        var pf = new File(a.path);
        if (!pf.exists) throw new Error("file not found: " + a.path);
        var pd = app.activeDocument, ab = pd.artboards[0].artboardRect;
        var lname = a.layer || "ART - Shading", pl = VB_orderLayer(pd, lname, a.below);
        pl.locked = false; pl.visible = true;
        var iname = a.name || "shading_png", old2 = VB_direct(pl);
        for (var oi2 = old2.length - 1; oi2 >= 0; oi2--) {
          if (old2[oi2].name === iname) { try { old2[oi2].locked = false; } catch (e) {} old2[oi2].remove(); }
        }
        // Illustrator places into the ACTIVE layer: if that is a locked layer (e.g. the previous glow layer) setting .file fails with
        // "Target layer cannot be modified", so make the target active first, and never leave an empty placed item behind on failure.
        try { pd.activeLayer = pl; } catch (e) {}
        var pim = pl.placedItems.add();
        var w2 = a.rect[2] - a.rect[0], h2 = a.rect[3] - a.rect[1];
        try {
          pim.file = pf; pim.name = iname;
          pim.width = w2; pim.height = h2;
          pim.position = [ab[0] + a.rect[0], ab[1] - a.rect[1]];
        } catch (pe) { try { pim.remove(); } catch (e) {} throw pe; }
        if (a.embed !== false) {   // embed by default: a linked PNG makes Illustrator ask "Update now?" on every reopen
          try { if (pf.length > 300 * 1024 * 1024) out.warn = "embedding a very large image (" + Math.round(pf.length / 1048576) + " MB); consider a lower dpi or 'Link instead of embed'"; } catch (e) {}
          pim.embed(); out.embedded = true;
        }
        pl.locked = (a.lock !== false);
        out.layer = lname; out.width = w2; out.height = h2; break;
      }
      case "check_links": case "relink": {
        // check_links: placed (linked) items whose file is missing -> out.missing [{name, layer, path}].
        // relink: a.mapping {itemName: path} and/or a.folders [dir]: a missing item is relinked to mapping[name] or to a file of the same
        // name found in a folder; a.embed embeds it afterwards. Embedded images are RasterItems and never listed.
        if (app.documents.length === 0) throw new Error("no open document");
        var kd = app.activeDocument, miss = [], fixed = [], total = kd.placedItems.length;
        for (var ki = 0; ki < kd.placedItems.length; ki++) {
          var kp = kd.placedItems[ki], kpath = "", kok = true;
          try { kpath = kp.file.fsName; kok = kp.file.exists; } catch (e) { kok = false; }
          if (kok) continue;
          var klay = ""; try { klay = kp.layer.name; } catch (e) {}
          var kinfo = { name: kp.name, layer: klay, path: kpath };
          if (a.action === "relink") {
            var cand = [];
            if (a.mapping && a.mapping[kp.name]) cand.push(a.mapping[kp.name]);
            var base = kpath ? kpath.replace(/^.*[\\\/]/, "") : "";
            var fl = a.folders || [];
            // a missing link often reports no path: fall back to the item's name with common image extensions
            var bases = base ? [base] : [kp.name + ".png", kp.name + ".jpg", kp.name + ".jpeg", kp.name + ".tif", kp.name + ".psd"];
            for (var fi2 = 0; fi2 < fl.length; fi2++) for (var bi2 = 0; bi2 < bases.length; bi2++) cand.push(fl[fi2] + "/" + bases[bi2]);
            var nf2 = null;
            for (var ci2 = 0; ci2 < cand.length; ci2++) { var cf = new File(cand[ci2]); if (cf.exists) { nf2 = cf; break; } }
            if (nf2) {
              var kl = null, kwas = false; try { kl = kp.layer; kwas = kl.locked; kl.locked = false; } catch (e) {}
              try { kp.locked = false; } catch (e) {}
              kp.file = nf2; if (a.embed) kp.embed();
              if (kl) { try { kl.locked = kwas; } catch (e) {} }
              kinfo.relinked = nf2.fsName; fixed.push(kinfo); ki--; continue;
            }
          }
          miss.push(kinfo);
        }
        out.total = total; out.missing = miss; out.relinked = fixed;
        if (miss.length) { var mnames = []; for (var mi2 = 0; mi2 < miss.length; mi2++) mnames.push(miss[mi2].name + " (" + miss[mi2].layer + ")"); out.warn = miss.length + " linked image(s) missing: " + mnames.join(", "); }
        break;
      }
      case "embed_all": {
        // embed every still-linked placed image that exists on disk (repairs a doc so it no longer depends on scratch PNGs); missing ones are listed
        if (app.documents.length === 0) throw new Error("no open document");
        var ed2 = app.activeDocument, emb = 0, emiss = [];
        for (var ei = ed2.placedItems.length - 1; ei >= 0; ei--) {
          var ep = ed2.placedItems[ei], eok = false;
          try { eok = ep.file.exists; } catch (e) {}
          if (!eok) { emiss.push(ep.name); continue; }
          var el = null, ewas = false; try { el = ep.layer; ewas = el.locked; el.locked = false; ep.locked = false; } catch (e) {}
          ep.embed(); emb++;
          if (el) { try { el.locked = ewas; } catch (e) {} }
        }
        out.embedded = emb; out.missing = emiss; break;
      }
      case "apply_fills": {
        // assignments: [{layer, match (regex on item name), swatch, fill [r,g,b]|null, stroke [r,g,b]|null, stroke_w}]
        if (app.documents.length === 0) throw new Error("no open document");
        var fd = app.activeDocument, as2 = a.assignments || [], applied = [], skipped = [];
        // a.clear: layers whose items are removed first (flat copies from the previous run)
        var clr = a.clear || [];
        for (var ci = 0; ci < clr.length; ci++) {
          var cl = VB_find(fd, clr[ci]);
          if (!cl) continue;
          cl.locked = false; cl.visible = true;
          var co = VB_direct(cl);
          for (var cj = co.length - 1; cj >= 0; cj--) { try { co[cj].locked = false; co[cj].hidden = false; } catch (e) {} co[cj].remove(); }
        }
        var cpLayers = {};
        for (var ai = 0; ai < as2.length; ai++) {
          var asg = as2[ai], fl = VB_find(fd, asg.layer);
          if (!fl) { skipped.push(asg.layer); continue; }
          var re = asg.match ? new RegExp(asg.match) : null;
          var idset = null;
          if (asg.ids) { idset = {}; for (var di = 0; di < asg.ids.length; di++) { idset[asg.ids[di]] = true; idset[String(asg.ids[di]).replace(/_/g, " ")] = true; } }
          var cpl = null;
          if (asg.copy_to) {
            if (!cpLayers[asg.copy_to]) { cpLayers[asg.copy_to] = VB_orderLayer(fd, asg.copy_to, asg.copy_below); cpLayers[asg.copy_to].locked = false; cpLayers[asg.copy_to].visible = true; }
            cpl = cpLayers[asg.copy_to];
          }
          var wl = fl.locked, wv = fl.visible; fl.locked = false; fl.visible = true;
          var sw2 = asg.fill ? VB_swatch(fd, asg.swatch || ("VB " + asg.layer), asg.fill) : null;
          var cnt = 0, its = VB_direct(fl);
          for (var ii = 0; ii < its.length; ii++) {
            var itm = its[ii];
            var nm = String(itm.name), nm2 = nm.replace(/ /g, "_");  // older SVGs: Illustrator imports "_" in ids as a space
            if (idset && !idset[nm] && !idset[nm2]) continue;
            if (re && !re.test(nm) && !re.test(nm2)) continue;
            if (asg.exclude && (new RegExp(asg.exclude).test(nm) || new RegExp(asg.exclude).test(nm2))) continue;
            try { itm.locked = false; } catch (e) {}
            if (cpl) {   // flat fill-only copy on its own layer (editable, usable as a mask); the original keeps its line
              var dup = itm.duplicate(cpl, ElementPlacement.PLACEATEND);
              dup.name = "flat_" + nm2;
              var dt = dup.typename === "CompoundPathItem" ? dup.pathItems[0] : dup;
              if (sw2 && dt && ("filled" in dt)) { dt.filled = true; dt.fillColor = sw2.color; dt.stroked = false; }
              cnt++; continue;
            }
            var tgt = itm.typename === "CompoundPathItem" ? itm.pathItems[0] : itm;
            if (!tgt || !("filled" in tgt)) continue;
            if (sw2) { tgt.filled = true; tgt.fillColor = sw2.color; } else tgt.filled = false;
            if (asg.stroke) { tgt.stroked = true; tgt.strokeColor = VB_rgb(asg.stroke); if (asg.stroke_w) tgt.strokeWidth = asg.stroke_w; }
            cnt++;
          }
          fl.locked = wl; fl.visible = wv;
          applied.push(asg.layer + ":" + cnt);
        }
        for (var ck in cpLayers) { if (cpLayers.hasOwnProperty(ck)) cpLayers[ck].locked = true; }
        out.applied = applied; out.skipped = skipped;
        if (skipped.length) out.warn = "layers not found: " + skipped.join(", ");
        break;
      }
      case "remove_item": {
        // delete the named item(s) on a layer (e.g. a stale light glow PNG); a missing layer or item is not an error
        if (app.documents.length === 0) throw new Error("no open document");
        var rd = app.activeDocument, rl = VB_find(rd, a.layer), removed = 0;
        if (rl) {
          var wl = rl.locked; rl.locked = false;
          var ri2 = VB_direct(rl);
          for (var rj = ri2.length - 1; rj >= 0; rj--) { if (ri2[rj].name === a.name) { try { ri2[rj].locked = false; } catch (e) {} ri2[rj].remove(); removed++; } }
          rl.locked = wl;
        }
        out.removed = removed; break;
      }
      case "set_visible": {
        if (app.documents.length === 0) throw new Error("no open document");
        var vd = app.activeDocument, vn = a.names || [], vdone = [], vnf = [];
        for (var vi = 0; vi < vn.length; vi++) {
          var vl = VB_find(vd, vn[vi]);
          if (!vl) { vnf.push(vn[vi]); continue; }
          vl.visible = (a.visible !== false); vdone.push(vn[vi]);
        }
        out.layers = vdone; out.not_found = vnf;
        if (vnf.length) out.ok = false, out.error = "layers not found: " + vnf.join(", ");
        break;
      }
      case "close_docs": {
        // Close named open documents (a.names = exact file names; nothing else is ever touched). Safety: names are required, and a document
        // with unsaved changes is SKIPPED (reported in out.skipped) unless a.discard === true; nothing is ever saved here.
        var cn = a.names || [], closed = [], keep = [], skipped = [];
        if (!cn.length) throw new Error("close_docs needs names: [file names]");
        for (var ci = app.documents.length - 1; ci >= 0; ci--) {
          var cdoc = app.documents[ci], hit = false;
          for (var cj = 0; cj < cn.length; cj++) if (cdoc.name === cn[cj]) hit = true;
          if (!hit) continue;
          if (!cdoc.saved && a.discard !== true) { skipped.push(cdoc.name); continue; }
          closed.push(cdoc.name); cdoc.close(SaveOptions.DONOTSAVECHANGES);
        }
        for (var ck = 0; ck < app.documents.length; ck++) keep.push(app.documents[ck].name);
        out.closed = closed; out.skipped = skipped; out.open = keep; break;
      }
      case "save_ai": {
        if (app.documents.length === 0) throw new Error("no open document");
        app.activeDocument.saveAs(new File(a.path), new IllustratorSaveOptions()); break;
      }
      case "export_png": {
        if (app.documents.length === 0) throw new Error("no open document");
        var o = new ExportOptionsPNG24();
        o.artBoardClipping = true; o.transparency = false;
        var s = a.scale || 100; o.horizontalScale = s; o.verticalScale = s;
        app.activeDocument.exportFile(new File(a.path), ExportType.PNG24, o); break;
      }
      case "export_view": {
        // Whole artboard as PNG at a given dpi (so px per ft = dpi / scale_ft_per_in); a.only = layer names to show (others hidden, restored after);
        // a.transparent = no paper background. Reports the exact pixel size for the Foundry push calibration.
        if (app.documents.length === 0) throw new Error("no open document");
        var ed = app.activeDocument, edpi = a.dpi || 150, snap = [], enf = [];
        if (a.only && a.only.length) {
          snap = VB_snapshot(ed, []);
          for (var si = 0; si < snap.length; si++) snap[si].l.visible = false;
          for (var oi = 0; oi < a.only.length; oi++) {
            var ol = VB_find(ed, a.only[oi]);
            if (!ol) enf.push(a.only[oi]); else { VB_showTree(ol); var op = ol; try { while (op.parent && op.parent.typename === "Layer") { op = op.parent; op.visible = true; } } catch (e) {} }
          }
        }
        try {
          if (enf.length) throw new Error("layers not found: " + enf.join(", "));
          var eo = new ExportOptionsPNG24();
          eo.artBoardClipping = true; eo.transparency = !!a.transparent; eo.antiAliasing = true;
          eo.horizontalScale = edpi / 72 * 100; eo.verticalScale = eo.horizontalScale;
          ed.exportFile(new File(a.path), ExportType.PNG24, eo);
        } finally {
          for (var ri = 0; ri < snap.length; ri++) { try { snap[ri].l.visible = snap[ri].v; } catch (e) {} }
        }
        var er = ed.artboards[ed.artboards.getActiveArtboardIndex()].artboardRect;
        out.dpi = edpi; out.width_pt = er[2] - er[0]; out.height_pt = er[1] - er[3];
        out.width_px = Math.round(out.width_pt * edpi / 72); out.height_px = Math.round(out.height_pt * edpi / 72);
        break;
      }
      case "reroute_leaders": {
        // Rebuild the leader (and its casing) of every callout from the FIXED anchor dot to the label's current bounds.
        // a.changed_only: only callouts whose label/anchor moved since the last call (the panel's live mode polls with it).
        // a.ids: limit to these entity ids. a.style {style: elbow|straight, shelf, gap, color, casing_color, width, casing_width}.
        if (app.documents.length === 0) throw new Error("no open document");
        var rdoc = app.activeDocument;
        if (!VB_find(rdoc, "Leaders")) { out.skipped = "no Leaders layer (not a map generated here)"; break; }
        var rr = VB_rerouteLeaders(rdoc, a);
        for (var rk in rr) if (rr.hasOwnProperty(rk)) out[rk] = rr[rk];
        break;
      }
      case "finalize_labels": {
        // group each label's halo/box and text as <id>_callout so one drag moves both (run after placing an SVG from render_world)
        if (app.documents.length === 0) throw new Error("no open document");
        var fdoc = app.activeDocument;
        if (!VB_find(fdoc, "Leaders") && !VB_find(fdoc, "Label Backing")) { out.skipped = "not a generated map"; break; }
        var fm = VB_callouts(fdoc);
        out.grouped = VB_finalizeLabels(fdoc, fm, a.repair !== false); out.reordered = fm.fixed || 0;
        var fc = 0, fk; for (fk in fm.groups) if (fm.groups.hasOwnProperty(fk)) fc++;
        out.callouts = fc; out.texts = 0; for (fk in fm.texts) if (fm.texts.hasOwnProperty(fk)) out.texts++;
        out.unnamed_fallback = fm.unnamed; break;
      }
      case "apply_curved": {
        // street / river names as type on a path, from <svg>.curved.json (split out of replace_layer so Redraw labels shows it as its own step)
        if (app.documents.length === 0) throw new Error("no open document");
        if (!a.path) throw new Error("path required");
        var cdoc = app.activeDocument, ch = VB_hideHeavy(cdoc, []);
        try { out.curved = VB_applyCurved(cdoc, new File(a.path).fsName); } finally { VB_restoreHeavy(ch); }
        out.font_scans = VB_fontScans; break;
      }
      case "order_layers": {
        // a.groups: [[name, ...] top to bottom, ...]; moves layers only when out of order (labels: backing under every text layer)
        if (app.documents.length === 0) throw new Error("no open document");
        var ores = VB_orderLayers(app.activeDocument, a.groups || []);
        out.moved = ores.moved; out.checked = ores.checked; if (ores.errors.length) out.warn = "layer order: " + ores.errors.join("; ");
        break;
      }
      case "label_preflight": {
        // cheap look at the active document before a label redraw: which document, how many items the replace will remove, heavy layers
        if (app.documents.length === 0) throw new Error("no open document");
        var qd = app.activeDocument, qn = a.names || [], qc = {}, qt = 0;
        out.doc = String(qd.name); try { out.path = qd.fullName.fsName; } catch (e) { out.path = ""; }
        for (var qi = 0; qi < qn.length; qi++) { var ql = VB_find(qd, qn[qi]); var cnt = ql ? ql.pageItems.length : -1; qc[qn[qi]] = cnt; if (cnt > 0) qt += cnt; }
        out.counts = qc; out.items = qt; out.text_frames = qd.textFrames.length;
        var qh = 0; for (var qj = 0; qj < qd.layers.length; qj++) { var qln = qd.layers[qj].name; if (/^UNDERLAY$/i.test(qln) || /^ART(\s|$|-)/i.test(qln)) { if (qd.layers[qj].rasterItems.length || qd.layers[qj].placedItems.length) qh++; } }
        out.heavy_layers = qh; out.docs_open = app.documents.length; out.font_scans = VB_fontScans; break;
      }
      case "read_label_positions": {
        if (app.documents.length === 0) throw new Error("no open document");
        out.labels = VB_readLabels(app.activeDocument); out.artboard = app.activeDocument.artboards[0].artboardRect; break;
      }
      case "move_item": {
        // move the first item called a.name by (dx, dy) page points (y down); used to test dragging and by scripted edits
        if (app.documents.length === 0) throw new Error("no open document");
        var mdoc = app.activeDocument, mit = VB_findItem(mdoc, a.name);
        if (!mit) throw new Error("item not found: " + a.name);
        var mundo = []; try { VB_unlockChain(mit.layer, mundo); } catch (e) {}
        var wasL = false; try { wasL = mit.locked; mit.locked = false; } catch (e) {}
        mit.translate(a.dx || 0, -(a.dy || 0));
        try { mit.locked = wasL; } catch (e) {}
        for (var mu = 0; mu < mundo.length; mu++) mundo[mu].locked = true;
        out.bounds = VB_pageBounds(mdoc, mit); break;
      }
      case "read_items": {
        // page-point bounds (and path points) of items by name, to check where things ended up
        if (app.documents.length === 0) throw new Error("no open document");
        var idoc = app.activeDocument, inames = a.names || [], items = {};
        for (var ix = 0; ix < inames.length; ix++) {
          var iit = VB_findItem(idoc, inames[ix]);
          if (!iit) { items[inames[ix]] = null; continue; }
          var rec = { bounds: VB_pageBounds(idoc, iit), hidden: !!iit.hidden };
          if (iit.typename === "PathItem") { rec.points = []; for (var ip = 0; ip < iit.pathPoints.length; ip++) rec.points.push(VB_page(idoc, iit.pathPoints[ip].anchor)); }
          items[inames[ix]] = rec;
        }
        out.items = items; break;
      }
      case "focus_items": {   // BRIDGES: select the named items (first found) and zoom the view to them
        if (app.documents.length === 0) throw new Error("no open document");
        var fdoc = app.activeDocument, fnames = a.names || [], fit = [], fb = null;
        for (var fi = 0; fi < fnames.length; fi++) { var fo = VB_findItem(fdoc, fnames[fi]); if (fo) { fit.push(fo); var gb = fo.geometricBounds; fb = fb ? [Math.min(fb[0], gb[0]), Math.max(fb[1], gb[1]), Math.max(fb[2], gb[2]), Math.min(fb[3], gb[3])] : gb.slice(0); } }
        if (!fit.length) throw new Error("nothing found: " + fnames.join(", "));
        fdoc.selection = null; for (var fk = 0; fk < fit.length; fk++) { try { fit[fk].selected = true; } catch (e) { /* locked layer */ } }
        var fv = fdoc.views[0]; fv.centerPoint = [(fb[0] + fb[2]) / 2, (fb[1] + fb[3]) / 2];
        var fw = Math.max(fb[2] - fb[0], 1), fh = Math.max(fb[1] - fb[3], 1); fv.zoom = Math.max(0.05, Math.min(8, Math.min(900 / fw, 600 / fh) * 0.5));
        out.found = fit.length; out.bounds = fb; break;
      }
      case "lock_leaders": {
        // lock / unlock the Leaders layer (lines only; the Leader Anchors layer stays editable so anchors can be dragged)
        if (app.documents.length === 0) throw new Error("no open document");
        var kl = VB_find(app.activeDocument, "Leaders");
        if (kl) kl.locked = (a.locked !== false);
        out.locked = (a.locked !== false); out.found = !!kl; break;
      }
      case "delete_items": {
        // remove only the items of some entity ids (roads / buildings deleted in the data): no render, no layer replace. See lib/itemops.js for the input.
        if (app.documents.length === 0) throw new Error("no open document");
        if (!a.targets && !(a.ids && a.ids.length)) throw new Error("delete_items needs ids or targets");
        var dres = VB_deleteItems(app.activeDocument, a);
        for (var dk in dres) if (dres.hasOwnProperty(dk)) out[dk] = dres[dk];
        break;
      }
      case "replace_items": {
        // items of the named layers of an SVG (render_items.py: a few roads / buildings) replace the same-named items of the open document, in place
        if (!a.path) throw new Error("path required");
        var qnames = a.layers || a.names || [];
        if (!qnames.length) throw new Error("layers required");
        for (var qx = 0; qx < qnames.length; qx++) if (VB_isArt(qnames[qx])) throw new Error("refusing to replace items on ART layer: " + qnames[qx]);
        if (app.documents.length === 0) throw new Error("no open document");
        var qf = new File(a.path);
        if (!qf.exists) throw new Error("file not found: " + a.path);
        var qdoc = app.activeDocument, qhid = VB_hideHeavy(qdoc, qnames), qsvg = null, qout = { replaced: 0, added: 0, missing: [] };
        try {
          qsvg = VB_openQuiet(qf);
          VB_replaceItems(qdoc, qsvg, qnames, qout);
        } finally {
          if (qsvg) { try { qsvg.close(SaveOptions.DONOTSAVECHANGES); } catch (e) {} }
          try { app.activeDocument = qdoc; } catch (e2) {}
          VB_restoreHeavy(qhid);
        }
        out.replaced = qout.replaced; out.added = qout.added; out.missing = qout.missing; break;
      }
      case "rename_items": {
        // a.renames [{from, to, text?}]: item names of `from` (and its label / leader / fill family) become `to`; a.layers limits the walk (default every layer)
        if (app.documents.length === 0) throw new Error("no open document");
        var rn = { renamed: 0, texts: 0, failed: [] };
        VB_renameItems(app.activeDocument, a.renames || [], a.layers, rn);
        out.renamed = rn.renamed; out.texts = rn.texts; out.failed = rn.failed; break;
      }
      default: throw new Error("unknown action: " + a.action);
    }
    return VB_str(out);
  } catch (e) {
    return VB_str({ ok: false, error: String(e), line: e.line });
  }
}
