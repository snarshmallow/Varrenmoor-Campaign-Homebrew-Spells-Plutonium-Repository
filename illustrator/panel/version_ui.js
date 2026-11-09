// Reload / version button (top right of the header). CEP keeps the page it first loaded until the engine restarts, so closing and reopening the panel can still show old code.
// This button reloads the page itself, bypassing the cache (scripts are loaded with a ?v=<time> query by the bootstrap in index.html), and shows which version is loaded.
// Loaded before main.js; main.js calls VBVersionUI.init(ctx) at startup and VBVersionUI.afterInit() once the place is loaded.
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var KEY = "vb_reload";
  var ctx = null, ver = null, held = false, armTimer = null, armed = false, staleNow = false, escTimer = null;

  function ls(op, k, v) { try { if (op === "get") return window.localStorage.getItem(k); if (op === "set") window.localStorage.setItem(k, v); else window.localStorage.removeItem(k); } catch (e) { /* storage blocked */ } return null; }

  function pageBase() { return String(location.href).split("#")[0].split("?")[0]; }

  function status() {
    var r = ctx.runner(), hp = r && r.hostPending && r.hostPending();
    return { held: held, busy: !!(r && r.isBusy()) || (ctx.rawBusy ? ctx.rawBusy() : false), label: ctx.statusText ? ctx.statusText() : "", hostPending: hp ? hp.action : "" };
  }
  function paintBadge(chk) {
    var dot = $("verDot"), b = $("reloadPanel"), t = $("verText");
    staleNow = !!(chk && chk.stale);
    if (dot) dot.hidden = !staleNow;
    if (b) { b.classList.toggle("stale", staleNow); b.title = staleNow ? "Update available: click to reload (loaded " + ver.label() + ")" : "Reload panel: picks up pushed code, replaces close/reopen (" + ver.label() + ")"; }
    if (t) { t.textContent = ver.short(); t.title = ver.label() + (staleNow ? "  |  newer file on disk: " + chk.current.newest : ""); }
  }
  function poll() { try { paintBadge(ver.check()); } catch (e) { /* ignore */ } }

  function disarm() { armed = false; clearTimeout(armTimer); var b = $("reloadPanel"); if (b) b.classList.remove("armed"); }

  function click() {
    var why = window.VBVersion.refusal(status());
    if (why) {
      if (armed) {   // second click within 6 s: cancel the running job; the user then clicks reload again once it is idle
        disarm(); var r = ctx.runner(); var did = r && r.cancel && r.cancel();
        ctx.logLine(did ? "Reload: job cancel requested. Click reload again when the status shows idle." : "Reload still refused (" + why + "): nothing to cancel, wait.");
        return;
      }
      armed = true; $("reloadPanel").classList.add("armed"); clearTimeout(armTimer); armTimer = setTimeout(disarm, 6000);
      ctx.showError("Reload refused: " + why + ". Click the reload button again within 6 s to cancel the running job first, or wait.", "warn");
      return;
    }
    disarm(); reload(0, !!staleNow);
  }

  // level 0 location.reload(true); 1 navigation to the same file with ?r=<now>. NEVER close the extension (a close/reopen from inside the page left the panel blank when the reopen did not run). A slow reload is given 12 s before level 1 is tried.
  function reload(level, wasStale) {
    try { ctx.saveNow(); } catch (e) { /* ignore */ }
    var det = $("hpDetails"), m = document.querySelector("main"), st = ctx.state();
    var blob = { t: Date.now(), level: level, wasStale: !!wasStale, fromHash: ver.loaded.hash, fromMtime: ver.loaded.mtime, place: st && st.place, tab: st && st.ui && st.ui.tab,
      hpOpen: !!(det && det.open), scroll: m ? m.scrollTop : 0, winScroll: window.pageYOffset || 0 };
    ls("set", KEY, JSON.stringify(blob));
    ctx.logLine("Reloading panel (method " + (level + 1) + "/2)...");
    try {
      if (st && st.place) ctx.writeLastPlace(st.place);
      if (level === 0) location.reload(true);
      else location.href = pageBase() + "?r=" + Date.now();
    } catch (e) { ctx.logLine("Reload step failed: " + (e && e.message || e)); }
    clearTimeout(escTimer);
    if (level < 1) escTimer = setTimeout(function () { ctx.logLine("Page did not reload within 12 s, trying the next method"); reload(level + 1, wasStale); }, 12000);   // still running = the reload had no effect; the new page cancels this timer by replacing the old one
  }

  function init(c) {
    ctx = c; ver = window.VBVersion.createVersion({ fs: c.fs, path: c.path, panelDir: c.panelDir, repoRoot: c.root });
    var b = $("reloadPanel"); if (!b) return;
    b.addEventListener("click", click);
    ["pointerdown", "mousedown"].forEach(function (n) { document.addEventListener(n, function (e) { if (e.target !== b && !(b.contains && b.contains(e.target))) held = true; }, true); });
    ["pointerup", "mouseup", "pointercancel", "dragend", "blur"].forEach(function (n) { (n === "blur" ? window : document).addEventListener(n, function () { held = false; }, true); });
    paintBadge(null); setInterval(poll, 12000);
  }

  // After the place and tab are loaded: restore the view from a reload and report; escalate when a stale panel reloaded to the same old version.
  function afterInit() {
    if (!ver) return;
    var raw = ls("get", KEY), blob = null; ls("del", KEY);
    try { blob = raw ? JSON.parse(raw) : null; } catch (e) { blob = null; }
    paintBadge(null);
    if (!blob || Date.now() - blob.t > 90000) return;
    var st = ctx.state(), same = blob.fromMtime === ver.loaded.mtime && blob.fromHash === ver.loaded.hash;
    try {
      if (blob.tab && blob.place === (st && st.place) && ctx.showTab) ctx.showTab(blob.tab);
      var det = $("hpDetails"); if (det && blob.hpOpen && !det.open) det.open = true;
      setTimeout(function () { var m = document.querySelector("main"); if (m) m.scrollTop = blob.scroll || 0; window.scrollTo(0, blob.winScroll || 0); }, 400);
    } catch (e) { /* best effort */ }
    ctx.logLine("reloaded to " + ver.label() + (same ? " (no newer files than before)" : ""));
    var t = $("verText"); if (t) { t.textContent = "reloaded to " + ver.short(); setTimeout(function () { paintBadge(null); }, 8000); }
    if (same && blob.wasStale && blob.level < 1) {   // disk was newer, yet the same code came back: try the navigation method (never close the extension)
      ctx.logLine("Reload brought no newer version although files changed: escalating");
      setTimeout(function () { reload(blob.level + 1, true); }, 500);
    }
  }
  window.VBVersionUI = { init: init, afterInit: afterInit, click: click };
})();
