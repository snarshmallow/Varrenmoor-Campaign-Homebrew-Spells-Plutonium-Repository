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
