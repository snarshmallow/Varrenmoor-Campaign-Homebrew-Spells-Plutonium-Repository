// Buildings tab UI (building style presets): style gallery with previews, target picker (selected / kind / district / all), building list with the
// current style, Apply / Clear / Auto. Injects its own tab button and panel (so index.html only needs the script tags). Loaded before main.js;
// main.js calls VBStylesUI.init(ctx). Logic (jobs) lives in lib/styles.js, the style data in illustrator/presets/building_styles/*.json.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, cache = { presets: null };
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var S = function () { return ctx.state().styles; };

  var HTML = '<h4>Building styles <span class="tag" id="stylesTag"></span></h4>' +
    '<p class="note">Pick a look, choose which buildings it applies to, press Apply. The style is stored as the <code>style</code> key in each building json (no style = the old look). ' +
    'Then Foundry tab: Export world pack (3D) and Export split models to rebuild the 3D models.</p>' +
    '<div id="stylesCard" class="note"></div><div id="stylesGallery" style="display:flex;flex-wrap:wrap;gap:4px;margin:4px 0"></div>' +
    '<div class="form"><label>Style <select id="stylesSel"></select></label>' +
    '<label>Apply to <select id="stylesTarget"></select></label>' +
    '<label id="stylesKindRow">Kind <select id="stylesKind"></select></label>' +
    '<label id="stylesDistRow">District <select id="stylesDist"></select></label></div>' +
    '<div class="btns"><button data-act="styles_apply" title="Write the chosen style into the chosen buildings">Apply style</button>' +
    '<button data-act="styles_auto" title="Choose a style per building from its kind and district (consistent inside a district)">Auto by kind + district</button>' +
    '<button data-act="styles_clear" title="Remove the style key: the building goes back to the legacy look">Clear style</button>' +
    '<button data-act="styles_selection" title="Select building shapes in Illustrator first">Use Illustrator selection</button>' +
    '<button data-act="styles_all" title="Tick every building in the list">Tick all</button><button data-act="styles_none">Tick none</button></div>' +
    '<div class="note" id="stylesInfo"></div>' +
    '<label>Filter <input type="text" id="stylesFilter" placeholder="id, kind or style"></label>' +
    '<div style="max-height:220px;overflow:auto"><table id="stylesTable"></table></div>';

  function mount() {
    var nav = $("tabs"), main = document.querySelector("main");
    if (!nav || !main || $("tab-buildings")) return;
    var b = document.createElement("button"); b.setAttribute("role", "tab"); b.setAttribute("data-tab", "buildings"); b.textContent = "Buildings";
    var town = nav.querySelector('[data-tab="town"]');
    if (town && town.nextSibling) nav.insertBefore(b, town.nextSibling); else nav.appendChild(b);
    var sec = document.createElement("section"); sec.id = "tab-buildings"; sec.setAttribute("role", "tabpanel"); sec.innerHTML = HTML;
    main.appendChild(sec);
  }
  mount();

  function presets() {
    if (cache.presets) return cache.presets;
    var dir = ctx.root + "/illustrator/presets/building_styles", out = [];
    try { ctx.fs.readdirSync(dir).forEach(function (f) { if (/\.json$/.test(f)) { var j = ctx.readJson(dir + "/" + f, null); if (j && j.id) out.push(j); } }); } catch (e) { /* none */ }
    var order = { house: 0, town: 1, church: 2, other: 3 };
    out.sort(function (a, b) { return (order[a.category] || 9) - (order[b.category] || 9) || String(a.name).localeCompare(b.name); });
    cache.presets = out; return out;
  }
  function buildings() {
    var dir = ctx.dirs().world + "/buildings", out = [];
    try { ctx.fs.readdirSync(dir).forEach(function (f) { if (/\.json$/.test(f)) { var j = ctx.readJson(dir + "/" + f, null); if (j && j.id) out.push({ id: j.id, kind: j.kind || "", floors: j.floors || 1, style: j.style || "", district: j.district || "" }); } }); } catch (e) { /* none */ }
    return out;
  }
  function districts() { var j = ctx.readJson(ctx.dirs().world + "/districts.json", { districts: [] }); return (j.districts || []).map(function (e) { return e.id; }); }
  function thumb(p) { return "file:///" + (ctx.root + "/" + (p.preview || "")).replace(/\\/g, "/").replace(/^\/+/, ""); }

  function paint() {
    if (!ctx || !$("stylesSel")) return;
    var s = S(), ps = presets(), bl = buildings();
    var opts = '<option value="auto">auto (by kind + district)</option>' + ps.map(function (p) { return '<option value="' + esc(p.id) + '">' + esc(p.category + ": " + p.name) + "</option>"; }).join("");
    if ($("stylesSel").innerHTML !== opts) $("stylesSel").innerHTML = opts;
    $("stylesSel").value = s.style;
    if (!$("stylesTarget").options.length) $("stylesTarget").innerHTML = VB.STYLE_TARGETS.map(function (t) { return '<option value="' + t[0] + '">' + esc(t[1]) + "</option>"; }).join("");
    $("stylesTarget").value = s.target;
    var kinds = Array.from(new Set(bl.map(function (b) { return b.kind; }).filter(Boolean))).sort();
    $("stylesKind").innerHTML = kinds.map(function (k) { return '<option value="' + esc(k) + '">' + esc(k) + "</option>"; }).join("");
    if (kinds.indexOf(s.kind) < 0 && kinds.length) s.kind = kinds[0];
    $("stylesKind").value = s.kind;
    $("stylesDist").innerHTML = '<option value="">(pick)</option>' + districts().map(function (d) { return '<option value="' + esc(d) + '">' + esc(d) + "</option>"; }).join("");
    $("stylesDist").value = s.district || "";
    $("stylesKindRow").style.display = s.target === "kind" ? "" : "none";
    $("stylesDistRow").style.display = s.target === "district" ? "" : "none";
    var cur = ps.filter(function (p) { return p.id === s.style; })[0];
    $("stylesCard").innerHTML = cur ? "<b>" + esc(cur.name) + "</b> (" + esc(cur.culture) + ", " + esc(cur.category) + "): " + esc(cur.description)
      : "auto: each building gets a style from its kind and district (a district prefers one look).";
    $("stylesGallery").innerHTML = ps.map(function (p) {
      return '<button data-sty="' + esc(p.id) + '" title="' + esc(p.name + " - " + p.description) + '" style="padding:1px;width:76px;' + (p.id === s.style ? "outline:2px solid #6aa0ff;" : "") +
        '"><img src="' + esc(thumb(p)) + '" width="72" height="54" style="display:block;object-fit:cover"><span style="font-size:9px;display:block;overflow:hidden;white-space:nowrap">' + esc(p.name) + "</span></button>";
    }).join("");
    Array.prototype.forEach.call($("stylesGallery").querySelectorAll("img"), function (im) { im.addEventListener("error", function () { im.style.visibility = "hidden"; }); });
    var f = (s.filter || "").toLowerCase(), ticked = {};
    (s.ids || []).forEach(function (i) { ticked[i] = 1; });
    var rows = bl.filter(function (b) { return !f || (b.id + " " + b.kind + " " + b.style).toLowerCase().indexOf(f) >= 0; });
    $("stylesTable").innerHTML = "<tr><th></th><th>id</th><th>kind</th><th>fl</th><th>style</th></tr>" + rows.map(function (b) {
      return '<tr><td><input type="checkbox" data-bid="' + esc(b.id) + '"' + (ticked[b.id] ? " checked" : "") + "></td><td>" + esc(b.id) + "</td><td>" + esc(b.kind) + "</td><td>" + b.floors + "</td><td>" + esc(b.style || "(legacy)") + "</td></tr>";
    }).join("");
    var styled = bl.filter(function (b) { return b.style; }).length;
    $("stylesTag").textContent = styled + "/" + bl.length + " styled";
    $("stylesInfo").textContent = (s.target === "selected" ? s.ids.length + " ticked" + (s.ids_src ? " (" + s.ids_src + ")" : "") : s.target === "all" ? bl.length + " buildings" : "") +
      (s.last ? "   last: " + s.last.style + " x" + s.last.count : "");
  }
  function run(styleId) { return ctx.startJob(VB.jobStylesAssign(ctx.state(), ctx.dirs(), styleId), function () { paint(); }); }
  var A = {
    styles_apply: function () { return run(S().style); },
    styles_auto: function () { return run("auto"); },
    styles_clear: function () { return run("none"); },
    styles_selection: function () { return ctx.startJob(VB.jobStylesFromSelection(ctx.state(), buildings().map(function (b) { return b.id; })), paint); },
    styles_all: function () { S().ids = buildings().map(function (b) { return b.id; }); S().ids_src = "all ticked"; ctx.save(); paint(); },
    styles_none: function () { S().ids = []; S().ids_src = ""; ctx.save(); paint(); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    $("stylesSel").addEventListener("change", function () { S().style = $("stylesSel").value; ctx.save(); paint(); });
    $("stylesTarget").addEventListener("change", function () { S().target = $("stylesTarget").value; ctx.save(); paint(); });
    $("stylesKind").addEventListener("change", function () { S().kind = $("stylesKind").value; ctx.save(); });
    $("stylesDist").addEventListener("change", function () { S().district = $("stylesDist").value; ctx.save(); });
    $("stylesFilter").addEventListener("input", function () { S().filter = $("stylesFilter").value; paint(); });
    $("stylesGallery").addEventListener("click", function (ev) { var b = ev.target.closest("button[data-sty]"); if (b) { S().style = b.getAttribute("data-sty"); ctx.save(); paint(); } });
    $("stylesTable").addEventListener("change", function (ev) {
      var cb = ev.target.closest("input[data-bid]"); if (!cb) return;
      var id = cb.getAttribute("data-bid"), ids = S().ids.filter(function (x) { return x !== id; });
      if (cb.checked) ids.push(id);
      S().ids = ids; S().ids_src = ""; S().target = "selected"; ctx.save(); paint();
    });
    paint();
  }
  window.VBStylesUI = { init: init, paint: paint, actions: A, mount: mount };
})();
