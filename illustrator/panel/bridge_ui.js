// Bridge section UI (Foundry tab): Launch / Stop / Status of the managed relay, setup values for the GM module, masked tokens with reveal + copy,
// live module-connected poll, log tail, "two GM tabs" warning. Logic: lib/bridge.js; relay manager: foundry-bridge/bridgectl.mjs.
// Uses an in-panel modal (no window.confirm/alert: JS dialogs can freeze CEP). Tokens live only in VBCore.bridgeMem (memory).
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, timer = null, shown = { reveal: false }, live = null;
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); };
  function S() { return ctx.state().bridge; }

  function modal(msg, yes, no) {
    return new Promise(function (resolve) {
      $("bgModalMsg").textContent = msg; $("bgModalYes").textContent = yes; $("bgModalNo").textContent = no; $("bgModal").hidden = false;
      var done = function (v) { $("bgModal").hidden = true; $("bgModalYes").onclick = $("bgModalNo").onclick = null; resolve(v); };
      $("bgModalYes").onclick = function () { done(true); }; $("bgModalNo").onclick = function () { done(false); };
    });
  }
  function copy(text) {
    try { if (navigator.clipboard && navigator.clipboard.writeText) { navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); }); return; } } catch (e) { /* fall through */ }
    fallbackCopy(text);
  }
  function fallbackCopy(text) {
    var t = document.createElement("textarea"); t.value = text; t.style.position = "fixed"; t.style.opacity = "0"; document.body.appendChild(t); t.select();
    try { document.execCommand("copy"); } catch (e) { /* ignore */ } document.body.removeChild(t);
  }
  function paint() {
    if (!ctx || !$("bgStatus")) return;
    var mem = VB.bridgeMem, info = mem.info, st = live || (info && info.status) || null;
    var tag = $("bgStatus");
    if (!st) { tag.textContent = "not checked"; tag.className = "tag"; }
    else if (!st.running) { tag.textContent = "relay stopped"; tag.className = "tag"; }
    else { tag.textContent = (st.moduleConnected ? "module connected" : "relay up, module NOT connected") + (st.managed === false ? " (started elsewhere)" : ""); tag.className = "tag" + (st.moduleConnected ? "" : " stale"); }
    var lines = (live && live.logLines) || (info && info.logTail) || [];
    var fight = VB.bridgeLoop4002(lines) || (st && st.replacedLastMinute >= 3);
    $("bgWarn").hidden = !fight;
    $("bgWarn").textContent = fight ? "Two GM tabs are open and fighting over the bridge (repeated close code 4002). Close one of the Foundry GM browser tabs. If it keeps happening after that, redeploy the module (foundry-bridge/DEPLOY_MODULE.md)." : "";
    var box = $("bgInfo");
    if (!info) { box.innerHTML = '<div class="note">Press Status or Launch Bridge to read the relay setup.</div>'; }
    else {
      var u = info.urls || {}, ms = info.moduleSettings || {}, sec = mem.secrets || {};
      var tokRow = function (label, key, val) {
        var shownVal = shown.reveal ? val : VB.bridgeMask(val);
        return '<div class="bgrow"><span class="bgk">' + label + '</span> <code id="bgtok_' + key + '">' + esc(val ? shownVal : "(none)") + '</code> <button data-bgcopy="' + key + '"' + (val ? "" : " disabled") + ' title="Copy to clipboard">Copy</button></div>';
      };
      box.innerHTML =
        '<div class="bgrow"><span class="bgk">Listen mode</span> ' + esc(info.listenMode || "") + (info.status && info.status.running ? " , port " + esc(info.status.port) + ", pid " + esc(info.status.pid || "?") : "") + "</div>" +
        '<div class="bgrow"><span class="bgk">Relay URL (LAN)</span> <code>' + esc(u.lan || "(not listening on LAN)") + '</code> <button data-bgcopyurl="' + esc(u.lan || "") + '"' + (u.lan ? "" : " disabled") + ">Copy</button></div>" +
        '<div class="bgrow"><span class="bgk">Relay URL (this PC)</span> <code>' + esc(u.localhost || "") + '</code> <button data-bgcopyurl="' + esc(u.localhost || "") + '">Copy</button></div>' +
        '<div class="bgrow"><span class="bgk">Foundry module settings (GM tab)</span></div><ul class="note" style="margin:2px 0 2px 14px;padding:0">' +
          Object.keys(ms).filter(function (k) { return k !== "Module token"; }).map(function (k) { return "<li>" + esc(k) + ": <b>" + esc(ms[k]) + "</b></li>"; }).join("") + "</ul>" +
        tokRow("Module token (paste into the module settings)", "module", sec.moduleToken) +
        tokRow("API token (bridge.ps1 / Claude; client.json already has it)", "api", sec.apiToken) +
        '<div class="note">' + esc(info.note || "") + "</div>";
    }
    var log = lines.slice(-12).join("\n");
    $("bgLog").textContent = log || "(no log yet: the managed relay writes foundry-bridge/run/relay.log)";
    $("bgReveal").textContent = shown.reveal ? "Hide tokens" : "Reveal tokens";
  }

  // ---- live poll: health over HTTP + log tail from file, only while the Foundry tab is showing --------------------------------------
  function logPath() { var b = S(); return b.state ? b.state.replace(/\\/g, "/") + "/relay.log" : ctx.root + "/foundry-bridge/run/relay.log"; }
  function readPort() {
    var b = S(); if (b.last && b.last.port) return b.last.port;
    try { var env = ctx.fs.readFileSync(b.env || ctx.root + "/foundry-bridge/.env", "utf8"), m = env.match(/^\s*PORT\s*=\s*(\d+)/m); if (m) return Number(m[1]); } catch (e) { /* default */ }
    return 3030;
  }
  function tailFile(file, n) {
    try {
      var fs = ctx.fs, fd = fs.openSync(file, "r"), size = fs.fstatSync(fd).size, len = Math.min(size, 32768), buf = Buffer.alloc(len);
      fs.readSync(fd, buf, 0, len, size - len); fs.closeSync(fd);
      return buf.toString("utf8").split(/\r?\n/).filter(Boolean).slice(-n);
    } catch (e) { return []; }
  }
  function poll() {
    var tab = $("tab-foundry"); if (!tab || !tab.classList.contains("on")) return;
    var port = readPort(), done = false, lines = tailFile(logPath(), 20);
    var finish = function (h) {
      if (done) return; done = true;
      live = { running: !!h, managed: !!(h && VB.bridgeMem.info && VB.bridgeMem.info.status && VB.bridgeMem.info.status.managed), port: port, moduleConnected: !!(h && h.moduleConnected), replacedLastMinute: h ? h.replacedLastMinute || 0 : 0, logLines: lines };
      paint();
    };
    try {
      var req = require("http").get({ host: "127.0.0.1", port: port, path: "/health", timeout: 1500 }, function (r) {
        var b = ""; r.on("data", function (c) { b += c; }); r.on("end", function () { try { finish(JSON.parse(b)); } catch (e) { finish(null); } });
      });
      req.on("error", function () { finish(null); }); req.on("timeout", function () { req.destroy(); finish(null); });
    } catch (e) { finish(null); }
  }

  var A = {
    bg_status: function () { return ctx.startJob(VB.jobBridgeStatus(ctx.state()), paint); },
    bg_launch: async function () {
      var res = await ctx.startJob(VB.jobBridgeStatus(ctx.state()), null);
      if (!res || !res.ok) return;
      var plan = VB.bridgeLaunchPlan(VB.bridgeMem.info && VB.bridgeMem.info.status);
      var restart = false;
      if (plan.action === "confirm-restart") {
        var yes = await modal(plan.reason + " Restart it? The Foundry module will reconnect by itself within a few seconds.", "Restart relay", "Keep it running");
        if (!yes) { paint(); return; }
        restart = true;
      }
      await ctx.startJob(VB.jobBridgeLaunch(ctx.state(), { restart: restart }), paint);
    },
    bg_stop: async function () {
      var yes = await modal("Stop the bridge relay? Claude and the Illustrator Foundry tab lose access until it is launched again.", "Stop relay", "Cancel");
      if (yes) await ctx.startJob(VB.jobBridgeStop(ctx.state()), paint);
    },
    bg_reveal: function () { shown.reveal = !shown.reveal; paint(); }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    VB.bridgeRoot = ctx.root;
    var box = $("bgInfo");
    if (box) box.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null; if (!b) return;
      var k = b.getAttribute("data-bgcopy"), u = b.getAttribute("data-bgcopyurl");
      if (k) { var s = VB.bridgeMem.secrets || {}; copy(k === "module" ? s.moduleToken : s.apiToken); }
      else if (u) copy(u);
    });
    timer = setInterval(poll, 3000); poll(); paint();
  }
  window.VBBridgeUI = { init: init, paint: paint, actions: A };
})();
