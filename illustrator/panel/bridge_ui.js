// Bridge section UI (Foundry tab): Connect-or-launch / Restart / Stop / Status / Find relays, managed vs attached state, setup values for the GM module,
// masked tokens with reveal + copy, manual token entry for a relay on another PC (memory only), live module-connected poll, log tail, "two GM tabs" warning,
// and the Pair devices list (Approve / Deny / Revoke / Rotate). Logic: lib/bridge.js; relay manager: foundry-bridge/bridgectl.mjs.
// Uses an in-panel modal (no window.confirm/alert: JS dialogs can freeze CEP). Tokens live only in VBCore.bridgeMem (memory).
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, timer = null, shown = { reveal: false }, live = null, pairMsg = "", pairBusy = false;
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
  function when(iso) { if (!iso) return "never"; var d = new Date(iso); return isNaN(d) ? "?" : d.toLocaleDateString() + " " + d.toLocaleTimeString().slice(0, 5); }

  function paintPair() {
    var box = $("bgPair"); if (!box) return;
    var p = VB.bridgeMem.pair, info = VB.bridgeMem.info, running = !!(live ? live.running : info && info.status && info.status.running);
    var h = "";
    if (!running) h = '<div class="note">Pairing needs a running relay.</div>';
    else if (!VB.bridgeApiToken()) h = '<div class="note">Needs the relay API token. It is read from foundry-bridge/.env on this PC; for a relay on another PC type it under "Tokens for a relay on another PC".</div>';
    else if (!p) h = '<div class="note">Reading the pairing list...</div>';
    else {
      h += (p.pending || []).map(function (r) {
        return '<div class="bgpend"><b>Approve this device?</b> ' + esc(r.name) + '<br><span class="bgk">from</span> ' + esc(r.ip) + ' <span class="bgk">origin</span> ' + esc(r.origin || "(none)") +
          (r.originMismatch ? ' <b class="bgbad">origin does not match what the device claims</b>' : "") + '<br><span class="bgk">confirmation code</span> <b class="bgcode">' + esc(String(r.code).replace(/(\d{3})(\d{3})/, "$1 $2")) + '</b> <span class="bgk">(must match the Foundry screen)</span><br>' +
          '<select data-bgdays="' + esc(r.id) + '"><option value="30">30 days</option><option value="90" selected>90 days</option><option value="365">1 year</option><option value="0">no expiry</option></select> ' +
          '<button class="primary" data-bgapprove="' + esc(r.id) + '">Approve</button> <button data-bgdeny="' + esc(r.id) + '">Deny</button></div>';
      }).join("");
      h += '<div class="note">Paired devices (' + (p.devices || []).length + ')</div>' + ((p.devices || []).map(function (d) {
        return '<div class="bgrow"><b>' + esc(d.name) + '</b> <span class="bgk">' + esc(d.ip || "") + ' , last seen ' + esc(when(d.lastSeen)) + ', expires ' + esc(d.expiresAt ? when(d.expiresAt) : "never") + (d.rotationPending ? ", new token on next connect" : "") + '</span> ' +
          '<button data-bgrotate="' + esc(d.id) + '" title="Gives the device a fresh token the next time it connects">Rotate</button> <button data-bgrevoke="' + esc(d.id) + '" title="Disconnects it now and invalidates its token">Revoke</button></div>';
      }).join("") || '<div class="note">No device is paired yet. In Foundry module settings press "Pair with relay".</div>');
    }
    if (pairMsg) h += '<div class="note">' + esc(pairMsg) + "</div>";
    box.innerHTML = h;
  }

  function paint() {
    if (!ctx || !$("bgStatus")) return;
    var mem = VB.bridgeMem, info = mem.info, st = live || (info && info.status) || null, full = info && info.status;
    var tag = $("bgStatus");
    var mode = full && full.mode ? full.mode : (st && st.running ? (st.managed ? "managed" : "attached (unmanaged)") : "");
    if (!st) { tag.textContent = "not checked"; tag.className = "tag"; }
    else if (!st.running) { tag.textContent = "relay stopped"; tag.className = "tag"; }
    else { tag.textContent = (st.moduleConnected ? "module connected" : "relay up, module NOT connected") + " , " + (mode || ""); tag.className = "tag" + (st.moduleConnected ? "" : " stale"); }
    var lines = (live && live.logLines) || (info && info.logTail) || [];
    var fight = VB.bridgeLoop4002(lines) || (st && st.replacedLastMinute >= 3);
    $("bgWarn").hidden = !fight;
    $("bgWarn").textContent = fight ? "Two GM tabs are open and fighting over the bridge (repeated close code 4002). Close one of the Foundry GM browser tabs. If it keeps happening after that, redeploy the module (foundry-bridge/DEPLOY_MODULE.md)." : "";
    var box = $("bgInfo");
    if (!info) { box.innerHTML = '<div class="note">Press Connect or launch (attaches to a relay that is already running; starts one if none is), or Status.</div>'; }
    else {
      var u = info.urls || {}, ms = info.moduleSettings || {}, sec = { moduleToken: VB.bridgeModuleToken(), apiToken: VB.bridgeApiToken() }, remote = !!(full && full.remote);
      var tokRow = function (label, key, val) {
        var shownVal = shown.reveal ? val : VB.bridgeMask(val);
        return '<div class="bgrow"><span class="bgk">' + label + '</span> <code id="bgtok_' + key + '">' + esc(val ? shownVal : "(none)") + '</code> <button data-bgcopy="' + key + '"' + (val ? "" : " disabled") + ' title="Copy to clipboard">Copy</button></div>';
      };
      box.innerHTML =
        '<div class="bgrow"><span class="bgk">Mode</span> <b>' + esc(mode || (full && full.running ? "" : "stopped")) + "</b> " + esc(info.listenMode || "") + (full && full.running ? " , " + esc(full.host || "127.0.0.1") + ":" + esc(full.port) + ", pid " + esc(full.pid || "?") : "") + "</div>" +
        '<div class="bgrow"><span class="bgk">Relay URL (LAN)</span> <code>' + esc(u.lan || "(not listening on LAN)") + '</code> <button data-bgcopyurl="' + esc(u.lan || "") + '"' + (u.lan ? "" : " disabled") + ">Copy</button></div>" +
        (u.localhost ? '<div class="bgrow"><span class="bgk">Relay URL (this PC)</span> <code>' + esc(u.localhost) + '</code> <button data-bgcopyurl="' + esc(u.localhost) + '">Copy</button></div>' : "") +
        '<div class="bgrow"><span class="bgk">Easiest: pair the module (no token). Manual way, module settings (GM tab):</span></div><ul class="note" style="margin:2px 0 2px 14px;padding:0">' +
          Object.keys(ms).filter(function (k) { return k !== "Module token"; }).map(function (k) { return "<li>" + esc(k) + ": <b>" + esc(ms[k]) + "</b></li>"; }).join("") + "</ul>" +
        tokRow("Module token (manual path)" + (remote || !(mem.secrets && mem.secrets.moduleToken) ? " [typed]" : ""), "module", sec.moduleToken) +
        tokRow("API token (bridge.ps1 / Claude; client.json already has it)" + (remote || !(mem.secrets && mem.secrets.apiToken) ? " [typed]" : ""), "api", sec.apiToken) +
        '<div class="note">' + esc(info.note || "") + "</div>";
    }
    var found = mem.found || [];
    $("bgFound").innerHTML = found.length ? found.map(function (x) {
      return '<div class="bgrow">' + (x.running ? "RELAY" : "nothing") + " at " + esc(x.host) + ":" + esc(x.port) + (x.local ? " (this PC)" : " (LAN)") + (x.running ? ' <button data-bguse="' + esc(x.host + ":" + x.port) + '">Use this</button>' : "") + "</div>";
    }).join("") : "";
    var log = lines.slice(-12).join("\n");
    $("bgLog").textContent = log || "(no log yet: the managed relay writes foundry-bridge/run/relay.log)";
    $("bgReveal").textContent = shown.reveal ? "Hide tokens" : "Reveal tokens";
    paintPair();
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
  function targetHost() { var info = VB.bridgeMem.info, s = info && info.status; return s && s.remote ? s.host : "127.0.0.1"; }
  function poll() {
    var tab = $("tab-foundry"); if (!tab || !tab.classList.contains("on")) return;
    var port = readPort(), done = false, host = targetHost(), lines = host === "127.0.0.1" ? tailFile(logPath(), 20) : [];
    var finish = function (h) {
      if (done) return; done = true;
      var i = VB.bridgeMem.info && VB.bridgeMem.info.status;
      live = { running: !!h, managed: !!(h && i && i.managed), port: port, moduleConnected: !!(h && h.moduleConnected), replacedLastMinute: h ? h.replacedLastMinute || 0 : 0, logLines: lines };
      if (h && VB.bridgeApiToken() && !pairBusy) { pairBusy = true; VB.bridgePairRefresh().then(function () { pairMsg = ""; }, function (e) { if (/not running/.test(e.message) === false) pairMsg = e.message; }).then(function () { pairBusy = false; paintPair(); }); }
      paint();
    };
    try {
      var req = require("http").get({ host: host, port: port, path: "/health", timeout: 1500 }, function (r) {
        var b = ""; r.on("data", function (c) { b += c; }); r.on("end", function () { try { finish(JSON.parse(b)); } catch (e) { finish(null); } });
      });
      req.on("error", function () { finish(null); }); req.on("timeout", function () { req.destroy(); finish(null); });
    } catch (e) { finish(null); }
  }

  function pairAct(fn, okMsg) {
    return fn().then(function () { pairMsg = okMsg || ""; return VB.bridgePairRefresh(); }).catch(function (e) { pairMsg = e.message; }).then(paint);
  }

  var A = {
    bg_status: function () { return ctx.startJob(VB.jobBridgeStatus(ctx.state()), paint); },
    bg_probe: function () { return ctx.startJob(VB.jobBridgeProbe(ctx.state()), paint); },
    // Connect or launch: attach to whatever is running (no restart, no modal); only start a relay when none is.
    bg_launch: async function () {
      var res = await ctx.startJob(VB.jobBridgeStatus(ctx.state()), null);
      if (!res || !res.ok) return;
      var plan = VB.bridgeLaunchPlan(VB.bridgeMem.info && VB.bridgeMem.info.status);
      if (plan.action === "attach") { pairMsg = plan.reason + " Nothing was restarted."; paint(); return; }
      await ctx.startJob(VB.jobBridgeLaunch(ctx.state(), { restart: false }), paint);
    },
    bg_restart: async function () {
      var res = await ctx.startJob(VB.jobBridgeStatus(ctx.state()), null);
      if (!res || !res.ok) return;
      var plan = VB.bridgeRestartPlan(VB.bridgeMem.info && VB.bridgeMem.info.status);
      if (!plan.allowed) { pairMsg = plan.text; paint(); return; }
      if (plan.ask && !(await modal(plan.text, "Restart relay", "Keep it running"))) { paint(); return; }
      await ctx.startJob(VB.jobBridgeLaunch(ctx.state(), { restart: true }), paint);
    },
    bg_stop: async function () {
      var res = await ctx.startJob(VB.jobBridgeStatus(ctx.state()), null);
      if (!res || !res.ok) return;
      var plan = VB.bridgeStopPlan(VB.bridgeMem.info && VB.bridgeMem.info.status);
      if (!plan.allowed) { pairMsg = plan.text; paint(); return; }
      if (plan.ask && !(await modal(plan.text, "Stop relay", "Cancel"))) return;
      await ctx.startJob(VB.jobBridgeStop(ctx.state()), paint);
    },
    bg_reveal: function () { shown.reveal = !shown.reveal; paint(); },
    bg_tokens: function () {   // manual entries for a relay on another PC; never stored
      VB.bridgeMem.manual = { api: ($("bgManApi").value || "").trim(), module: ($("bgManMod").value || "").trim() };
      pairMsg = VB.bridgeMem.manual.api ? "Token kept in memory only." : "";
      VB.bridgePairRefresh().catch(function (e) { pairMsg = e.message; }).then(paint);
    }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    VB.bridgeRoot = ctx.root;
    var box = $("bgInfo");
    if (box) box.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null; if (!b) return;
      var k = b.getAttribute("data-bgcopy"), u = b.getAttribute("data-bgcopyurl");
      if (k) copy(k === "module" ? VB.bridgeModuleToken() : VB.bridgeApiToken());
      else if (u) copy(u);
    });
    var found = $("bgFound");
    if (found) found.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null, v = b && b.getAttribute("data-bguse"); if (!v) return;
      S().target = v; if (ctx.save) ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); A.bg_status();
    });
    var pb = $("bgPair");
    if (pb) pb.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null; if (!b) return;
      var ap = b.getAttribute("data-bgapprove"), dn = b.getAttribute("data-bgdeny"), rv = b.getAttribute("data-bgrevoke"), ro = b.getAttribute("data-bgrotate");
      if (ap) { var sel = pb.querySelector('select[data-bgdays="' + ap + '"]'); pairAct(function () { return VB.bridgePairApprove(ap, Number(sel ? sel.value : 90)); }, "Approved."); }
      else if (dn) pairAct(function () { return VB.bridgePairDeny(dn); }, "Denied.");
      else if (rv) modal("Revoke this device? It is disconnected now and must be paired again.", "Revoke", "Cancel").then(function (y) { if (y) pairAct(function () { return VB.bridgePairRevoke(rv); }, "Revoked."); });
      else if (ro) pairAct(function () { return VB.bridgePairRotate(ro); }, "The device gets a new token on its next connect.");
    });
    timer = setInterval(poll, 3000); poll(); paint();
  }
  window.VBBridgeUI = { init: init, paint: paint, actions: A };
})();
