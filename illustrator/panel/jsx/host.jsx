// ExtendScript host. VB_run(jsonString) -> JSON string {ok, ...}
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
        var svg = app.open(f);  // SVG <g id> groups become layers
        if (!target || a.mode === "open") { out.mode = "opened"; break; }
        var n = 0;
        for (var li = svg.layers.length - 1; li >= 0; li--) {
          var sl = svg.layers[li], tl = VB_layer(target, sl.name);
          for (var pi = sl.pageItems.length - 1; pi >= 0; pi--) {
            sl.pageItems[pi].duplicate(tl, ElementPlacement.PLACEATBEGINNING); n++;
          }
        }
        svg.close(SaveOptions.DONOTSAVECHANGES);
        app.activeDocument = target;
        out.items = n; break;
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
        var rsvg = app.open(rf);
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
        for (var k in fams) if (fams.hasOwnProperty(k) && (!want || want.indexOf(k) >= 0)) out.families.push({ family: k, fonts: fams[k] });
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
        var pim = pl.placedItems.add();
        pim.file = pf; pim.name = iname;
        var w2 = a.rect[2] - a.rect[0], h2 = a.rect[3] - a.rect[1];
        pim.width = w2; pim.height = h2;
        pim.position = [ab[0] + a.rect[0], ab[1] - a.rect[1]];
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
            for (var fi2 = 0; fi2 < fl.length && base; fi2++) cand.push(fl[fi2] + "/" + base);
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
        if (miss.length) out.warn = miss.length + " linked image(s) missing: " + miss.map(function (m) { return m.name + " (" + m.layer + ")"; }).join(", ");
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
      default: throw new Error("unknown action: " + a.action);
    }
    return VB_str(out);
  } catch (e) {
    return VB_str({ ok: false, error: String(e), line: e.line });
  }
}
