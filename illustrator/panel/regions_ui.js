// Regions tab UI (district picker, lasso/rectangle, child list, diff view). Loaded before main.js; main.js calls VBRegionUI.init(ctx) / paint().
// Logic (command lines, jobs) lives in lib/regions.js.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, applyArmed = false, armTimer = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  var R = function () { return ctx.state().regions; };

  function districts() {
    var j = ctx.readJson(ctx.dirs().world + "/districts.json", { districts: [] });
    return (j.districts || []).filter(function (e) { return e.geometry && e.geometry.type === "polygon"; });
  }
  function childPlaces() { // child regions of the current place, read from disk (region.json), so the list is right after a restart too
    var fs = ctx.fs, path = ctx.path, base = ctx.root + "/world", out = [];
    var scan = function (dir, prefix) {
      var names = []; try { names = fs.readdirSync(dir); } catch (e) { return; }
      names.forEach(function (n) {
        var rj = ctx.readJson(dir + "/" + n + "/region.json", null);
        if (rj && rj.parent === ctx.state().place) out.push({ child: rj.child || (prefix + n), name: rj.name, extracted_at: rj.extracted_at, counts: rj.counts, sandbox: !!prefix });
      });
    };
    scan(base, ""); scan(base + "/_region_test", "_region_test/");
    return out;
  }
  function paint() {
    if (!ctx || !$("regDistrict")) return;
    var r = R(), ds = districts(), st = ctx.state();
    var sel = $("regDistrict"), cur = r.district;
    sel.innerHTML = '<option value="">(pick)</option>' + ds.map(function (e) { return '<option value="' + esc(e.id) + '">' + esc(e.name || e.id) + " [" + esc(e.kind) + "] " + esc(e.id) + "</option>"; }).join("");
    sel.value = cur || "";
    var sc = $("regScalePreset");
    if (!sc.options.length) sc.innerHTML = VB.REGION_SCALES.map(function (p) { return '<option value="' + p.id + '">' + esc(p.label) + "</option>"; }).join("");
    sc.value = r.preset;
    ["lasso", "district", "rect"].forEach(function (m) { var el = $("regMode_" + m); if (el) el.checked = r.mode === m; });
    $("regPolyTag").textContent = r.polygon && r.polygon.length ? r.polygon_src || r.polygon.length + " pts" : "none";
    $("regChildId").textContent = VB.regionChildId(st);
    $("regDpi").textContent = VB.regionDpi(r) + " dpi";
    var kids = childPlaces(), ul = $("regChildren");
    ul.innerHTML = kids.length ? kids.map(function (k) {
      return '<li class="' + (r.sel === k.child ? "sel" : "") + '" data-child="' + esc(k.child) + '"><span class="g">' + esc(k.name || k.child) + (k.sandbox ? " (test)" : "") + "</span> " +
        '<span class="note">' + esc(k.child) + (k.counts ? " - " + k.counts.buildings + " bld, " + k.counts.streets + " str" : "") + "</span>" +
        '<button data-rg="open" title="Render at district scale and open as a new Illustrator document">Open</button><button data-rg="refresh" title="Re-extract from the parent, keeping the child edits">Refresh</button>' +
        '<button data-rg="switch" title="Make this child the panel place">Place</button></li>';
    }).join("") : '<li class="note">no child regions of ' + esc(st.place) + " yet</li>";
    var df = r.diff;
    $("regDiff").textContent = df ? "Diff for " + df.child + " (" + df.n + (df.applied ? ", applied: " + df.applied.join(", ") : "") + "):\n" + df.text : "";
    var ap = $("regApply"); if (ap) { ap.disabled = !(df && df.n > 0 && !df.applied); ap.textContent = applyArmed ? "Really write " + df.n + " change(s) to the parent? Click again" : "Apply diff to parent..."; }
  }
  function curChild() {
    var r = R(); return r.sel || VB.regionChildId(ctx.state());
  }
  function arm(f) {
    if (!applyArmed) { applyArmed = true; clearTimeout(armTimer); armTimer = setTimeout(function () { applyArmed = false; paint(); }, 6000); paint(); return; }
    applyArmed = false; clearTimeout(armTimer); paint(); f();
  }
  var A = {
    reg_capture: function () {
      var st = ctx.state(), d = ctx.dirs();
      return ctx.startJob(VB.jobCapture(st, d, { what: "region lasso", layer: VB.REGION_LAYER, closed: true, store: "regions.polygon", srcName: "regions.polygon_src" }), function () { R().mode = "lasso"; ctx.save(); paint(); });
    },
    reg_preview: function () { return ctx.startJob(VB.jobRegionPreview(ctx.state(), ctx.dirs())); },
    reg_create: function () { return ctx.startJob(VB.jobRegionCreate(ctx.state(), ctx.dirs()), paint); },
    reg_list: function () { return ctx.startJob(VB.jobRegionList(ctx.state()), paint); },
    reg_refresh_sel: function () { return ctx.startJob(VB.jobRegionCreate(ctx.state(), ctx.dirs(), { refresh: true, child: curChild() }), paint); },
    reg_foundry: function () { return ctx.startJob(VB.jobRegionFoundry(ctx.state(), ctx.dirs(), curChild(), {}), paint); },
    reg_foundry_dry: function () { return ctx.startJob(VB.jobRegionFoundry(ctx.state(), ctx.dirs(), curChild(), { dry: true }), paint); },
    reg_link: function () { return ctx.startJob(VB.jobRegionLink(ctx.state(), ctx.dirs(), curChild()), paint); },
    reg_sync: function () { return ctx.startJob(VB.jobRegionSync(ctx.state(), ctx.dirs(), curChild(), false), paint); },
    reg_sync_apply: function () { var c = curChild(); arm(function () { ctx.startJob(VB.jobRegionSync(ctx.state(), ctx.dirs(), c, true), paint); }); },
    reg_scale_preset: function () { VB.regionApplyPreset(R(), $("regScalePreset").value); ctx.save(); ctx.syncInputs(); paint(); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var ul = $("regChildren");
    if (ul) ul.addEventListener("click", function (ev) {
      var li = ev.target.closest("li[data-child]"); if (!li) return;
      var child = li.getAttribute("data-child"), b = ev.target.closest("button[data-rg]");
      R().sel = child; ctx.save();
      if (b) {
        var what = b.getAttribute("data-rg"), st = ctx.state(), d = ctx.dirs();
        if (what === "open") ctx.startJob(VB.jobRegionOpen(st, d, child), paint);
        else if (what === "refresh") ctx.startJob(VB.jobRegionCreate(st, d, { refresh: true, child: child }), paint);
        else if (what === "switch") ctx.switchPlace(child.indexOf("/") >= 0 ? st.place : child);
      }
      paint();
    });
    ["regMode_district", "regMode_lasso", "regMode_rect"].forEach(function (id) {
      var el = $(id); if (el) el.addEventListener("change", function () { if (el.checked) { R().mode = el.value; ctx.save(); paint(); } });
    });
    var sp = $("regScalePreset"); if (sp) sp.addEventListener("change", A.reg_scale_preset);
    ["regDistrict"].forEach(function (id) { var el = $(id); if (el) el.addEventListener("change", function () { R().district = el.value; R().mode = "district"; ctx.save(); paint(); ctx.syncInputs(); }); });
  }
  window.VBRegionUI = { init: init, paint: paint, actions: A };
})();
