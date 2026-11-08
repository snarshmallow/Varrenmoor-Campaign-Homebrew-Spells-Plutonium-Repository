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
  return t;
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
function VB_finalizeLabels(doc, m) {
  var n = 0, id, undo = [], i;
  for (id in m.texts) {
    if (!m.texts.hasOwnProperty(id) || m.groups[id]) continue;
    var tx = m.texts[id], hal = m.backing[id];
    if (!hal) continue;
    if (!n) for (i = 0; i < m.layers.length; i++) VB_unlockChain(m.layers[i], undo);
    try {
      var lay = tx.layer, g = lay.groupItems.add();
      g.name = id + "_callout";
      hal.move(g, ElementPlacement.PLACEATEND);
      tx.move(g, ElementPlacement.PLACEATEND);
      m.groups[id] = g; n++;
    } catch (e) {}
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
var VB_fontCache = {};
function VB_font(family, bold, italic) {
  var key = family + "|" + bold + "|" + italic;
  if (VB_fontCache.hasOwnProperty(key)) return VB_fontCache[key];
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
function VB_applyCurved(doc, svgPath) {
  var res = { made: 0, skipped: 0, ids: [] };
  var jf = new File(String(svgPath) + ".curved.json");
  if (!jf.exists) return res;
  jf.encoding = "UTF-8"; jf.open("r"); var txt = jf.read(); jf.close();
  var data = eval("(" + txt + ")"), items = data.items || [];
  for (var i = 0; i < items.length; i++) {
    var c = items[i], fb = VB_findItem(doc, c.id);
    if (!fb || !c.points || c.points.length < 2) { res.skipped++; continue; }
    var undo = [], lyr = fb.layer, hb = VB_findItem(doc, c.id + "_halo");
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
      if (hb) { try { hb.remove(); } catch (e) {} }
      fb.remove();
      res.made++; res.ids.push(c.id);
    } catch (e) { res.skipped++; res.error = String(e); }
    for (var u = 0; u < undo.length; u++) { try { undo[u].locked = true; } catch (e) {} }
  }
  return res;
}
// app.open with alerts off ("Text on Path will be Flattened", missing fonts ...): a modal dialog blocks the whole ExtendScript queue.
function VB_openQuiet(f) {
  var old = app.userInteractionLevel;
  try { app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS; } catch (e) {}
  try { return app.open(f); } finally { try { app.userInteractionLevel = old; } catch (e) {} }
}
function VB_run(json) {
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
        if (!a.path) throw new Error("path required");
        var names = a.names || [];
        if (!names.length) throw new Error("names required");
        for (var ni = 0; ni < names.length; ni++) if (VB_isArt(names[ni])) throw new Error("refusing to replace ART layer: " + names[ni]);
        if (app.documents.length === 0) throw new Error("no open document");
        var rf = new File(a.path);
        if (!rf.exists) throw new Error("file not found: " + a.path);
        var tdoc = app.activeDocument;
        var rsvg = VB_openQuiet(rf);
        var replaced = [], missing = [], moved = 0;
        for (var ri = 0; ri < names.length; ri++) {
          var sl2 = VB_find(rsvg, names[ri]);
          if (!sl2) { missing.push(names[ri]); continue; }
          var tl2 = VB_ensureLike(tdoc, sl2);
          var wasLocked = tl2.locked, wasVisible = tl2.visible;
          tl2.locked = false; tl2.visible = true;
          var old = VB_direct(tl2);
          for (var oi = old.length - 1; oi >= 0; oi--) {
            try { old[oi].locked = false; old[oi].hidden = false; } catch (e) {}
            old[oi].remove();
          }
          var srcItems = VB_direct(sl2);
          for (var si = srcItems.length - 1; si >= 0; si--) {
            srcItems[si].duplicate(tl2, ElementPlacement.PLACEATBEGINNING); moved++;
          }
          tl2.locked = (a.restore_lock === false) ? false : wasLocked;
          tl2.visible = wasVisible;
          replaced.push(names[ri]);
        }
        rsvg.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = tdoc;
        out.curved = VB_applyCurved(tdoc, rf.fsName);
        out.replaced = replaced; out.missing = missing; out.items = moved;
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
        var selItems = []; for (var si3 = 0; si3 < sd.selection.length; si3++) selItems.push(sd.selection[si3]);
        VB_collectPaths(selItems, found);
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
        if (a.embed) {
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
        out.grouped = VB_finalizeLabels(fdoc, fm);
        var fc = 0, fk; for (fk in fm.groups) if (fm.groups.hasOwnProperty(fk)) fc++;
        out.callouts = fc; out.texts = 0; for (fk in fm.texts) if (fm.texts.hasOwnProperty(fk)) out.texts++;
        out.unnamed_fallback = fm.unnamed; break;
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
      case "lock_leaders": {
        // lock / unlock the Leaders layer (lines only; the Leader Anchors layer stays editable so anchors can be dragged)
        if (app.documents.length === 0) throw new Error("no open document");
        var kl = VB_find(app.activeDocument, "Leaders");
        if (kl) kl.locked = (a.locked !== false);
        out.locked = (a.locked !== false); out.found = !!kl; break;
      }
      default: throw new Error("unknown action: " + a.action);
    }
    return VB_str(out);
  } catch (e) {
    return VB_str({ ok: false, error: String(e), line: e.line });
  }
}
