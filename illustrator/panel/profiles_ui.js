// Profiles UI: header indicator + quick picker, and the full manager (Tools tab, section "Profiles"). Logic is in lib/profiles.js (allow-list schema,
// diff/apply/validate/migrate, file store with atomic writes). Loaded before main.js; main.js calls VBProfilesUI.init(ctx) BEFORE the first place loads
// (so a brand-new place can get the default profile) and VBProfilesUI.paint() from refreshAll.
(function () {
  "use strict";
  var VB = window.VBCore, P = window.VBProfiles, ctx = null, store = null, pending = null, delArm = null, delTimer = null, cache = { key: "", doc: null }, listCache = null;
  var $ = function (id) { return document.getElementById(id); };
  function S() { return ctx.state(); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function msg(t, bad) { var m = $("pfMsg"); if (m) { m.textContent = t || ""; m.style.color = bad ? "var(--bad)" : "var(--dim)"; } }
  var WHERE = { builtin: "built-in", user: "global", place: "this place" };

  function makeStore() {
    var base = ctx.root + "/illustrator/presets/profiles";
    return P.createStore({ fs: ctx.fs, userDir: base, builtinDir: base + "/builtin", placeDir: function (pl) { return ctx.root + "/world/" + pl + "/profiles"; }, defaultFile: base + "/_default.json" });
  }
  function place() { return S().place; }
  function entries() { if (!listCache) listCache = store.list(place()); return listCache; }
  function invalidate() { listCache = null; cache.key = ""; }
  function find(where, name) { var l = entries(); for (var i = 0; i < l.length; i++) if (l[i].where === where && l[i].name === name) return l[i]; return null; }
  function selected() { var v = $("pfList") ? $("pfList").value : ""; if (!v) return null; var i = v.indexOf(":"); return find(v.slice(0, i), v.slice(i + 1)); }
  function activeRef() { var p = S().profile || {}; return p.name ? p : null; }
  function activeDoc() {
    var a = activeRef(); if (!a) return null;
    var k = a.where + ":" + a.name + ":" + place(); if (cache.key === k) return cache.doc;
    var e = find(a.where, a.name); cache.key = k; cache.doc = e && e.ok ? e.doc : null; return cache.doc;
  }
  function sectionBoxes(id, ids, checked) {
    return P.SECTIONS.map(function (s) {
      var on = ids ? ids.indexOf(s.id) >= 0 : false; if (ids && !on) return "";
      return '<label class="chk"><input type="checkbox" data-pfsec="' + s.id + '" ' + (checked ? "checked" : "") + "> " + esc(s.title) + "</label>";
    }).join("");
  }
  function scopeIds(container) { return Array.prototype.slice.call(document.querySelectorAll("#" + container + " input[data-pfsec]")).filter(function (c) { return c.checked; }).map(function (c) { return c.getAttribute("data-pfsec"); }); }

  // ---- header indicator + manager state
  function paintIndicator() {
    if (!ctx || !store) return; var el = $("profInd"); if (!el) return;
    var a = activeRef(), doc = a ? activeDoc() : null;
    if (!a) { el.textContent = "Profile: none"; el.className = "tag"; el.title = "No profile loaded for this place. Tools tab > Profiles."; }
    else if (!doc) { el.textContent = "Profile: " + a.name + " (missing)"; el.className = "tag stale"; el.title = "The profile file is gone; settings stay as they are."; }
    else { var n = P.diff(S(), doc).length; el.textContent = "Profile: " + a.name + (n ? " (modified)" : ""); el.className = "tag" + (n ? " stale" : ""); el.title = n ? n + " setting(s) differ from the saved profile. Tools tab > Profiles: Update current or Load." : "Settings match the profile."; }
  }
  function paintQuick() {
    var q = $("profQuick"); if (!q) return; var cur = q.value, l = entries(), html = '<option value="">Profiles...</option>';
    l.forEach(function (e) { if (e.ok) html += '<option value="' + esc(e.where + ":" + e.name) + '">' + esc(e.name + " [" + WHERE[e.where] + "]") + "</option>"; });
    if (q.getAttribute("data-h") !== html) { q.innerHTML = html; q.setAttribute("data-h", html); q.value = cur; }
  }
  function paintList() {
    var sel = $("pfList"); if (!sel) return; var cur = sel.value, def = store.getDefault(), html = "";
    var groups = { builtin: "Built-in (read-only)", user: "Global (all places)", place: "This place" };
    ["builtin", "user", "place"].forEach(function (w) {
      var rows = entries().filter(function (e) { return e.where === w; }); if (!rows.length) return;
      html += '<optgroup label="' + groups[w] + '">' + rows.map(function (e) {
        var isDef = def && def.name === e.name && def.where === w;
        return '<option value="' + esc(w + ":" + e.name) + '">' + esc(e.name + (e.ok ? "" : " (invalid)") + (isDef ? "  [default for new places]" : "")) + "</option>";
      }).join("") + "</optgroup>";
    });
    if (sel.getAttribute("data-h") !== html) { sel.innerHTML = html; sel.setAttribute("data-h", html); if (cur) sel.value = cur; }
    var e = selected(), b = e && e.where === "builtin";
    ["pfUpdate", "pfRename", "pfDelete"].forEach(function (id) { var x = $(id); if (x) x.disabled = !e || b || (id === "pfUpdate" && !activeRef()); });
    ["pfLoad", "pfDup", "pfDefault", "pfExport", "pfCopy"].forEach(function (id) { var x = $(id); if (x) x.disabled = !e || !e.ok; });
    var a = activeRef(); $("pfActive").textContent = a ? "Loaded: " + a.name + " [" + (WHERE[a.where] || a.where) + "]" : "No profile loaded for this place.";
    $("pfDefLine").textContent = def ? "Default for new places: " + def.name + " [" + WHERE[def.where] + "]" : "Default for new places: none (built-in defaults).";
    if (e && !e.ok) msg("Invalid profile: " + e.errors.join("; "), true);
  }
  function paint() { if (!ctx || !store) return; try { paintQuick(); paintList(); paintIndicator(); } catch (e) { msg("profiles: " + (e.message || e), true); } }

  // ---- load preview (diff) and apply
  function showPreview(doc, label, isDefaultsReset) {
    var diff = P.diff(S(), doc), box = $("pfDiff");
    pending = { doc: doc, label: label, reset: !!isDefaultsReset };
    if (!diff.length) { box.innerHTML = '<div class="note">' + esc(label) + ": nothing would change (settings already match).</div>"; $("pfApply").hidden = true; return; }
    var sum = P.summarize(diff), html = '<div class="note">' + esc(label) + ": " + diff.length + " setting(s) would change. Untick a section to leave it alone.</div>";
    sum.forEach(function (s) {
      var rows = diff.filter(function (x) { return x.section === s.section; }).slice(0, 6).map(function (x) { return esc(x.path) + ": " + esc(JSON.stringify(x.from)).slice(0, 40) + " -> " + esc(JSON.stringify(x.to)).slice(0, 40); });
      html += '<div class="exrow"><label class="chk"><input type="checkbox" data-pfsec="' + s.section + '" checked> <b>' + esc(s.title) + "</b> (" + s.count + ")</label><div class=\"note\" style=\"white-space:pre-wrap\">" + rows.join("\n") + (s.count > 6 ? "\n..." : "") + "</div></div>";
    });
    box.innerHTML = html; $("pfApply").hidden = false;
  }
  function applyPending() {
    if (!pending) return; var ids = scopeIds("pfDiff");
    if (!ids.length) { msg("No section ticked: nothing applied.", true); return; }
    var r = P.apply(S(), pending.doc, ids), st = S();
    Object.keys(r.state).forEach(function (k) { st[k] = r.state[k]; });
    if (!pending.reset) st.profile = { name: pending.doc.name, where: pending.where || "user", at: new Date().toISOString() };
    ctx.save(); invalidate(); if (ctx.syncInputs) ctx.syncInputs();
    msg((pending.reset ? "Reset to defaults" : "Applied " + pending.doc.name) + ": " + r.applied + " setting(s) changed" + (r.skipped.length ? "; skipped " + r.skipped.length + " (" + r.skipped[0] + ")" : "") + ". Place data (shapes, paths, ids, scene uuids) was not touched.");
    pending = null; $("pfDiff").innerHTML = ""; $("pfApply").hidden = true; if (ctx.refreshAll) ctx.refreshAll(); else paint();
  }

  function whereChoice() { var w = $("pfWhere") ? $("pfWhere").value : "user"; return w === "place" ? "place" : "user"; }
  function nameChoice() { var n = P.sanitizeName($("pfName").value); if (!n) throw new Error("type a profile name (letters, digits, space, - _ ( ))"); return n; }
  function guard(fn) { return function () { try { fn(); } catch (e) { msg(String((e && e.message) || e), true); } }; }

  function copyText(t) {
    try { if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(t).catch(function () { fallbackCopy(t); }); return; } } catch (e) { /* fall through */ }
    fallbackCopy(t);
  }
  function fallbackCopy(t) { var a = document.createElement("textarea"); a.value = t; document.body.appendChild(a); a.select(); try { document.execCommand("copy"); } catch (e) { /* ignore */ } document.body.removeChild(a); }

  var A = {
    pfLoad: function () { var e = selected(); if (!e || !e.ok) throw new Error("pick a profile"); showPreview(e.doc, "Load " + e.name); pending.where = e.where; },
    pfApply: function () { applyPending(); },
    pfSaveAs: function () {
      var n = nameChoice(), w = whereChoice(), ids = scopeIds("pfScope"); if (!ids.length) throw new Error("tick at least one section to capture");
      var doc = P.make(n, S(), ids, { description: $("pfDesc").value || "" }), f = store.write(doc, w, place(), { overwrite: false });
      invalidate(); S().profile = { name: n, where: w, at: new Date().toISOString() }; ctx.save(); msg("Saved " + f + " (" + ids.length + " section(s)). Geometry and ids are never captured."); paint();
    },
    pfUpdate: function () {
      var a = activeRef(); if (!a || a.where === "builtin") throw new Error("load a global or place profile first (built-in profiles are read-only)");
      var old = activeDoc(), ids = scopeIds("pfScope"); if (!ids.length) ids = old ? old.scope : P.sectionIds();
      var doc = P.make(a.name, S(), ids, { description: old ? old.description : "", created: old ? old.created : "" });
      store.write(doc, a.where, place(), { overwrite: true }); invalidate(); msg("Updated " + a.name + " from the current settings (" + ids.length + " section(s))."); paint();
    },
    pfRename: function () {
      var e = selected(); if (!e || e.where === "builtin") throw new Error("pick a global or place profile"); var n = nameChoice();
      store.rename(e.where, e.name, n, place()); var a = activeRef(); if (a && a.name === e.name && a.where === e.where) S().profile.name = n;
      var d = store.getDefault(); if (d && d.name === e.name && d.where === e.where) store.setDefault({ name: n, where: e.where });
      invalidate(); ctx.save(); msg("Renamed to " + n + "."); paint();
    },
    pfDup: function () {
      var e = selected(); if (!e || !e.ok) throw new Error("pick a profile"); var n = nameChoice(), w = whereChoice();
      store.duplicate(e.where, e.name, w, n, place()); invalidate(); msg("Duplicated as " + n + " [" + WHERE[w] + "]."); paint();
    },
    pfDelete: function () {
      var e = selected(); if (!e || e.where === "builtin") throw new Error("pick a global or place profile");
      var k = e.where + ":" + e.name, b = $("pfDelete");
      if (delArm !== k) { delArm = k; b.textContent = "Click again to delete"; clearTimeout(delTimer); delTimer = setTimeout(function () { delArm = null; b.textContent = "Delete"; }, 4000); msg("Click Delete again within 4 s to delete " + e.name + " (cannot be undone)."); return; }
      delArm = null; clearTimeout(delTimer); b.textContent = "Delete"; store.remove(e.where, e.name, place());
      var d = store.getDefault(); if (d && d.name === e.name && d.where === e.where) store.setDefault(null);
      var a = activeRef(); if (a && a.name === e.name && a.where === e.where) S().profile = { name: "", where: "" };
      invalidate(); ctx.save(); msg("Deleted " + e.name + "."); paint();
    },
    pfDefault: function () {
      var e = selected(); if (!e || !e.ok) throw new Error("pick a profile");
      if (e.where === "place") throw new Error("the default for new places must be a global or built-in profile");
      var d = store.getDefault();
      if (d && d.name === e.name && d.where === e.where) { store.setDefault(null); msg("Default for new places cleared."); } else { store.setDefault({ name: e.name, where: e.where }); msg(e.name + " will be applied to every NEW place."); }
      invalidate(); paint();
    },
    pfReset: function () { showPreview(P.fromDefaults(VB.defaults(), scopeIds("pfScope").length ? scopeIds("pfScope") : P.sectionIds()), "Reset to built-in defaults", true); },
    pfExport: function () {
      var e = selected(); if (!e || !e.ok) throw new Error("pick a profile"); var f = $("pfFile").value.trim().replace(/\\/g, "/"); if (!f) throw new Error("type or browse a target file or folder");
      if (!/\.json$/i.test(f)) f = f.replace(/\/+$/, "") + "/" + P.sanitizeName(e.name) + ".json";
      store.atomicWrite(f, JSON.stringify(e.doc, null, 1) + "\n"); msg("Exported to " + f);
    },
    pfImport: function () {
      var f = $("pfFile").value.trim().replace(/\\/g, "/"); if (!f) throw new Error("type or browse the profile file to import");
      var r = store.importFile(f, whereChoice(), place()); invalidate(); msg("Imported " + r.name + (r.warnings.length ? " (" + r.warnings.length + " warning(s): " + r.warnings[0] + ")" : "") + "."); paint();
    },
    pfBrowse: function () {
      try { var r = window.cep.fs.showOpenDialogEx(false, false, "Choose a profile file", "", ["json"]); if (r && r.data && r.data.length) $("pfFile").value = r.data[0].replace(/\\/g, "/"); }
      catch (e) { msg("file dialog unavailable: type the path instead", true); }
    },
    pfCopy: function () { var e = selected(); if (!e) throw new Error("pick a profile"); copyText(e.file); msg("Copied: " + e.file); }
  };

  function bind() {
    Object.keys(A).forEach(function (id) { var b = $(id); if (b) b.addEventListener("click", guard(A[id])); });
    $("pfList").addEventListener("change", function () { var e = selected(); if (e && e.ok) { $("pfName").value = e.name; $("pfDesc").value = e.doc.description || ""; } paint(); });
    $("profQuick").addEventListener("change", function () {
      var v = $("profQuick").value; if (!v) return; $("pfList").value = v; $("profQuick").value = "";
      if (ctx.showTab) ctx.showTab("tools"); guard(A.pfLoad)();
    });
    $("pfScope").innerHTML = sectionBoxes("pfScope", null, true).replace(/<label/g, "<label");
    setInterval(function () { if (ctx && store) { try { paintIndicator(); } catch (e) { /* ignore */ } } }, 1500);
  }

  window.VBProfilesUI = {
    init: function (c) {
      ctx = c; if (!P) return;
      try { store = makeStore(); } catch (e) { return; }
      if ($("pfList")) bind(); paint();
    },
    paint: paint,
    // called by main.js when a place has no panel_state.json yet: apply the default profile (global/built-in) to the fresh state
    applyDefaultToNew: function (st, root) {
      if (!store) return st;
      try {
        var d = store.getDefault(); if (!d) return st; var r = store.read(d.where, d.name, st.place); if (!r.ok) return st;
        return P.applyDefaultOnce(st, r.doc, d).state;   // records profile_applied; never re-applied to the same place
      } catch (e) { return st; }
    },
    invalidate: invalidate
  };
  if (typeof module !== "undefined" && module.exports) module.exports = window.VBProfilesUI;
})();
