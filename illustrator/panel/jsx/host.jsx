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
      default: throw new Error("unknown action: " + a.action);
    }
    return VB_str(out);
  } catch (e) {
    return VB_str({ ok: false, error: String(e), line: e.line });
  }
}
