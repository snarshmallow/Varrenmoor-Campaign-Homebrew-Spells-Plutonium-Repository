// Bridge section UI (Foundry tab, top). Everyday view: status summary (relay reachable, module connected, pairing on/off, this PC's relay URL), Connect / Find relay, pairing on/off + auto-request toggles,
// pending pairing requests (code, Approve / Deny) and paired devices (Revoke / Rotate); the local-relay guard (Close bridge) only shows when a relay runs on this PC.
// Everything else lives in the collapsed Advanced block: Launch/Restart local relay, window options, node/env/state, masked tokens with reveal + copy, manual tokens (memory only), client.json diagnostics, relay log.
// Logic: lib/bridge.js; relay manager: foundry-bridge/bridgectl.mjs.
// Uses an in-panel modal (no window.confirm/alert: JS dialogs can freeze CEP). Tokens live only in VBCore.bridgeMem (memory).
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null, timer = null, pairTimer = null, shown = { reveal: false }, live = null, localLive = null, lastLocalUp = null, pairMsg = "", pairBusy = false, detectBusy = false;
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

  // Status summary: relay reachable, module connected, pairing on/off (+ toggle), auto-request (+ toggle), the relay URL this PC's tools use
  function paintSummary() {
    var box = $("bgSummary"); if (!box) return;
    var info = VB.bridgeMem.info, st = live || (info && info.status) || null, p = VB.bridgeMem.pair, hp = (live && live.pairing) || (info && info.status && info.status.pairing) || null;
    var a = attachAddr(), where = a.host + ":" + a.port, c = VB.bridgeMem.client, hasTok = !!VB.bridgeApiToken();
    var pOn = p ? !!p.enabled : (hp ? !!hp.enabled : null), auto = p ? !!p.autoRequest : (hp && hp.autoRequest !== undefined ? !!hp.autoRequest : null), canEnable = p ? p.canEnable !== false : (hp ? hp.canEnable !== false : true);
    var row = function (k, v) { return '<span class="bgk">' + k + "</span><span>" + v + "</span>"; };
    var h = "";
    h += row("Relay", !st ? "not checked yet" : st.running ? '<b class="bgon">reachable</b> at ' + esc(where) + (attachIsLocal() ? " (this PC)" : "") : '<b class="bgoff">not reachable</b> at ' + esc(where));
    h += row("Foundry module", !st || !st.running ? "-" : st.moduleConnected ? '<b class="bgon">connected</b>' : '<b class="bgoff">not connected</b> (open Foundry as http://&lt;foundry PC&gt;:30000; it pairs by itself)');
    var tgl;
    if (!st || !st.running) tgl = "-";
    else if (pOn === null) tgl = "unknown (older relay: restart it once with the current start.bat)";
    else if (!canEnable) tgl = '<b class="bgoff">off</b>, and this relay cannot switch it on live: close its window and run start.bat once';
    else tgl = (pOn ? '<b class="bgon">ON</b>' : '<b class="bgoff">OFF</b>') + ' <button data-bgpairing="' + (pOn ? "off" : "on") + '"' + (hasTok ? "" : " disabled") + ">" + (pOn ? "Turn off" : "Turn on") + "</button>" + (hasTok ? "" : ' <span class="bgk">(needs the API token: see Advanced)</span>');
    h += row("Pairing", tgl);
    if (st && st.running && pOn && canEnable) h += row("Auto-request", (auto ? "<b>on</b>" : "<b>off</b>") + ' <button data-bgauto="' + (auto ? "off" : "on") + '"' + (hasTok ? "" : " disabled") + ">" + (auto ? "Turn off" : "Turn on") + '</button> <span class="bgk">a GM browser asks as soon as Foundry loads</span>');
    var chk = c ? VB.bridgeClientCheck(c.url, attachAddr().text) : null;
    h += row("This PC's tools use", c ? (c.url ? "<code>" + esc(c.url) + "</code> <span class=\"bgk\">from " + esc(c.source) + "</span>" : '<span class="bgoff">no relay URL found</span>') + (chk && !chk.ok ? ' <b class="bgbad">' + esc(chk.text) + "</b>" : "") : "reading...");
    box.innerHTML = h;
  }

  function paintPair() {
    var box = $("bgPair"); if (!box) return;
    var p = VB.bridgeMem.pair, info = VB.bridgeMem.info, running = !!(live ? live.running : info && info.status && info.status.running);
    var h = "";
    if (!running) h = '<div class="note">Pairing needs a reachable relay.</div>';
    else if (!VB.bridgeApiToken()) h = '<div class="note">The API token is not known to this PC yet. It is read automatically from client.json (foundry-bridge/client.json, or the file on the relay PC); see Advanced > Diagnostics, or type it under Advanced > Tokens.</div>';
    else if (!p) h = '<div class="note">Reading the pairing list...</div>';
    else {
      if (!p.enabled) h += '<div class="note">Pairing is switched off, so no device can ask. Turn it on above.</div>';
      h += (p.pending || []).map(function (r) {
        return '<div class="bgpend"><b>Approve this device?</b> ' + esc(r.name) + '<br><span class="bgk">from</span> ' + esc(r.ip) + ' <span class="bgk">origin</span> ' + esc(r.origin || "(none)") +
          (r.warnings && r.warnings.length ? r.warnings.map(function (w) { return '<br><b class="bgbad">WARNING: ' + esc(w) + '</b>'; }).join("") : (r.originMismatch ? ' <b class="bgbad">origin does not match what the device claims</b>' : "")) + '<br><span class="bgk">confirmation code</span> <b class="bgcode">' + esc(String(r.code).replace(/(\d{3})(\d{3})/, "$1 $2")) + '</b><br><span class="bgk">Approve only if the Foundry screen shows exactly this code; otherwise press Deny.</span><br>' +
          '<select data-bgdays="' + esc(r.id) + '"><option value="30">30 days</option><option value="90" selected>90 days</option><option value="365">1 year</option><option value="0">no expiry</option></select> ' +
          '<button class="primary" data-bgapprove="' + esc(r.id) + '">Approve</button> <button data-bgdeny="' + esc(r.id) + '">Deny</button></div>';
      }).join("");
      if (p.enabled && !(p.pending || []).length) h += '<div class="note">Waiting for a request... (checked every 2 s). A GM browser that opens Foundry as http://&lt;foundry PC&gt;:30000 asks by itself (Auto-request), or press "Pair with relay" in the module settings.</div>';
      var devs = p.devices || [], key = function (d) { return d.clientId || (d.name + "|" + (d.origin || "") + "|" + (d.userName || "")); }, cnt = {};
      devs.forEach(function (d) { cnt[key(d)] = (cnt[key(d)] || 0) + 1; });
      h += '<div class="note">Paired devices (' + devs.length + ')</div>' + (devs.map(function (d) {
        var dup = cnt[key(d)] > 1;
        return '<div class="bgrow"><b>' + esc(d.name) + '</b> <span class="bgk">' + esc(d.userName || "") + " " + esc(d.origin || "") + " " + esc(d.ip || "") + ' , last seen ' + esc(when(d.lastSeen)) + ', expires ' + esc(d.expiresAt ? when(d.expiresAt) : "never") + (d.rotationPending ? ", new secret on next connect" : "") + '</span>' +
          (dup ? ' <b class="bgbad">same browser listed twice: Revoke the one that was never seen / seen least recently</b>' : "") + ' ' +
          '<button data-bgrotate="' + esc(d.id) + '" title="Gives the device a fresh secret the next time it connects">Rotate</button> <button data-bgrevoke="' + esc(d.id) + '" title="Disconnects it now and invalidates its secret">Revoke</button></div>';
      }).join("") || '<div class="note">No device is paired yet.</div>');
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
    else if (!st.running) { tag.textContent = "no relay at " + attachAddr().host + ":" + attachAddr().port; tag.className = "tag stale"; }
    else { tag.textContent = (attachIsLocal() ? "this PC" : "attached " + attachAddr().host + ":" + attachAddr().port) + (st.moduleConnected ? ", module connected" : ", module NOT connected"); tag.className = "tag" + (st.moduleConnected ? "" : " stale"); }
    var lines = (live && live.logLines) || (info && info.logTail) || [];
    var fight = VB.bridgeLoop4002(lines) || (st && st.replacedLastMinute >= 3);
    $("bgWarn").hidden = !fight;
    $("bgWarn").textContent = fight ? "Two GM tabs are open and fighting over the bridge (repeated close code 4002). Close one of the Foundry GM browser tabs. If it keeps happening after that, redeploy the module (foundry-bridge/DEPLOY_MODULE.md)." : "";
    var box = $("bgInfo");
    if (!info) { box.innerHTML = '<div class="note">Press Connect (attaches to the relay at the address above; nothing is started or restarted) or Status.</div>'; }
    else {
      var u = info.urls || {}, remote = !!(full && full.remote);
      var tokRow = function (label, key, kind) {
        var src = VB.bridgeTokenSource(kind), val = src.token, shownVal = shown.reveal ? val : VB.bridgeMask(val);
        return '<div class="bgrow"><span class="bgk">' + label + '</span> <code id="bgtok_' + key + '">' + esc(val ? shownVal : "(none)") + '</code> <button data-bgcopy="' + key + '"' + (val ? "" : " disabled") + ' title="Copy to clipboard">Copy</button>' + (val ? ' <span class="bgk">from ' + esc(src.source) + "</span>" : "") + "</div>";
      };
      box.innerHTML =
        '<div class="bgrow"><span class="bgk">Mode</span> <b>' + esc(mode || (full && full.running ? "" : "stopped")) + "</b> " + esc(info.listenMode || "") + (full && full.running ? " , " + esc(full.host || "127.0.0.1") + ":" + esc(full.port) + ", pid " + esc(full.pid || "?") : "") + "</div>" +
        (u.lan ? '<div class="bgrow"><span class="bgk">Relay URL (LAN)</span> <code>' + esc(u.lan) + '</code> <button data-bgcopyurl="' + esc(u.lan) + '">Copy</button></div>' : "") +
        tokRow("Module token (manual fallback)", "module", "module") +
        tokRow("API token (tools / admin calls)", "api", "api") +
        '<div class="note">' + (remote ? "This relay runs on another PC: its tokens come from the client.json the tools use, or from what you type here (never from this PC's .env). " : "") + esc(info.note || "") + "</div>";
    }
    var found = mem.found || [];
    $("bgFound").innerHTML = found.length ? found.map(function (x) {
      return '<div class="bgrow">' + (x.running ? "RELAY" : "nothing") + " at " + esc(x.host) + ":" + esc(x.port) + (x.local ? " (this PC)" : " (LAN)") + (x.running ? ' <button data-bguse="' + esc(x.host + ":" + x.port) + '">Use this</button>' : "") + "</div>";
    }).join("") : "";
    var log = lines.slice(-12).join("\n");
    $("bgLog").textContent = log || "(no log yet: the managed relay writes foundry-bridge/run/relay.log)";
    $("bgReveal").textContent = shown.reveal ? "Hide tokens" : "Reveal tokens";
    paintSummary(); paintPair(); paintAttach(); paintLocal(); paintClient();
  }

  // ---- Attach / Close bridge / client.json blocks ---------------------------------------------------------------------------------------
  function attachAddr() { var t = VB.bridgeParseTarget(VB.bridgeAttachTarget(ctx.state())); return { host: t.host || "127.0.0.1", port: t.port || 3030, text: VB.bridgeAttachTarget(ctx.state()) }; }
  function attachIsLocal() { return VB.bridgeIsLoopback(attachAddr().host); }
  function paintAttach() {
    var el = $("bgAttachSt"); if (!el) return; var a = attachAddr(), where = a.host + ":" + a.port;
    if (!live) { el.textContent = "Not checked yet. Press Connect."; el.className = "note"; }
    else if (live.running) {
      el.textContent = (attachIsLocal() ? "Attached to the relay on this PC at " : "Attached to remote relay at ") + where + "; module connected: " + (live.moduleConnected ? "yes" : "no (open the Foundry GM tab / pair the module)");
      el.className = "note " + (live.moduleConnected ? "ok" : "no");
    } else { el.textContent = "No relay answers at " + where + ". Is the relay running on that PC? (Nothing is started from here.)"; el.className = "note no"; }
    var tg = $("bgTwo"), two = VB.bridgeTwoRelays(!!localLive, !!(live && live.running), attachIsLocal());
    if (tg) { tg.hidden = !two; tg.textContent = two ? "Two relays are up: one on this PC and one at " + where + ". Close the local one (Close bridge below). Only one relay should run." : ""; }
  }
  // the guard box (Close bridge) is only in view when a relay is detected on THIS PC; otherwise the plain "none running" text sits in Advanced
  function paintLocal() {
    var box = $("bgLocalBox"), el = $("bgLocal"), adv = $("bgLocalAdv"), b1 = $("bgCloseBtn"), b2 = $("bgCloseBtn2"); if (!el || !b1) return;
    var l = VB.bridgeMem.local, plan = VB.bridgeClosePlan(l), txt;
    if (!l) txt = "Checking this PC for a bridge relay...";
    else if (!l.found) txt = "No local bridge running." + ((l.otherListeners || []).length ? " (Something else listens on port " + l.otherListeners.map(function (o) { return o.port + ": pid " + o.pid + " " + (o.imageName || "?"); }).join(", ") + "; it is not a bridge relay and will not be touched.)" : "");
    else txt = "Found a relay on this PC: pid " + (l.pid || "?") + " (" + (l.imageName || "?") + "), port " + l.port + ", " + (l.how || "") + "; module connected: " + (l.moduleConnected ? "yes" : "no") + "." + (l.isNode ? "" : " This is not node.exe, so it will not be touched.");
    el.textContent = txt; if (adv) adv.textContent = l && l.found ? "" : txt;
    if (box) box.hidden = !(l && l.found);
    [b1, b2].forEach(function (b) { if (b) { b.textContent = plan.label; b.disabled = !plan.enabled; } });
  }
  function paintClient() {
    var el = $("bgClient"); if (!el) return; var c = VB.bridgeMem.client, cs = VB.bridgeMem.clientSecrets;
    var head = "The Illustrator tools (foundry_push.py via bridge.ps1) get the relay URL and API token from client.json: first foundry-bridge/client.json on this PC, then the file on the relay PC's share (host from the attached address, FOUNDRY_BRIDGE_HOST or foundry-3d/.env), or the file chosen above. ";
    if (!c) { el.textContent = head + "Reading..."; el.className = "note"; return; }
    var chk = VB.bridgeClientCheck(c.url, attachAddr().text);
    el.textContent = head + "Right now: " + (c.url || "(no URL)") + " from " + c.source + "." + (cs && cs.api ? " API token: found in that file (not shown)." : " No API token found in it.") + (chk.ok ? "" : " WARNING: " + chk.text);
    el.className = "note" + (chk.ok ? "" : " bad");
  }
  function readShare(f) {
    return new Promise(function (res) {
      var done = false, t = setTimeout(function () { if (!done) { done = true; res(null); } }, 4000);
      try { ctx.fs.readFile(f, "utf8", function (e, d) { if (done) return; done = true; clearTimeout(t); res(e ? null : d); }); } catch (e) { clearTimeout(t); res(null); }
    });
  }
  function loadClient() {
    var env = {}; try { env = process.env || {}; } catch (e) { /* none */ }
    var t = VB.bridgeParseTarget(S().target || "");
    return VB.bridgeClientInfo({ fs: ctx.fs, env: env, root: ctx.root, readShare: readShare, attachHost: t.host, clientFile: S().clientFile || "" }).then(function (c) { VB.bridgeMem.client = c; paint(); return c; }, function () { return null; });
  }
  // detects a relay on THIS PC (not a job: read-only; runs on load and whenever local health changes)
  function detectLocal() {
    if (detectBusy) return Promise.resolve(); detectBusy = true;
    return VB.bridgeLocalDetect(ctx.state()).catch(function (e) { VB.bridgeMem.local = null; pairMsg = e.message; }).then(function () { detectBusy = false; paint(); });
  }

  // ---- live poll: health over HTTP + log tail from file, only while the Foundry tab is showing --------------------------------------
  function logPath() { var b = S(); return b.state ? b.state.replace(/\\/g, "/") + "/relay.log" : ctx.root + "/foundry-bridge/run/relay.log"; }
  function readPort() {   // port of the relay on THIS PC (from its .env; default 3030)
    var b = S();
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
  function healthGet(host, port, cb) {
    var done = false, fin = function (h) { if (!done) { done = true; cb(h); } };
    try {
      var req = require("http").get({ host: host, port: port, path: "/health", timeout: 1500 }, function (r) {
        var b = ""; r.on("data", function (c) { b += c; }); r.on("end", function () { try { var j = JSON.parse(b); fin(j && j.ok === true ? j : null); } catch (e) { fin(null); } });
      });
      req.on("error", function () { fin(null); }); req.on("timeout", function () { req.destroy(); fin(null); });
    } catch (e) { fin(null); }
  }
  // every 3 s: health of the attached relay (the saved address) and of anything on this PC (read-only); a change on this PC re-runs the local detection
  function poll() {
    var tab = $("tab-foundry"); if (!tab || !tab.classList.contains("on")) return;
    var a = attachAddr(), lp = readPort(), got = {}, left = 3, lines = tailFile(logPath(), 20);
    var finish = function () {
      if (--left > 0) return;
      var h = got.remote, lh = got.local || got.local3030;
      live = { running: !!h, managed: false, port: a.port, moduleConnected: !!(h && h.moduleConnected), replacedLastMinute: h ? h.replacedLastMinute || 0 : 0, pairing: (h && h.pairing) || null, logLines: lines };
      localLive = lh || null;
      if (lastLocalUp === null || lastLocalUp !== !!lh) { lastLocalUp = !!lh; detectLocal(); }
      if (h && VB.bridgeApiToken() && !pairBusy) { pairBusy = true; VB.bridgePairRefresh().then(function () { pairMsg = ""; }, function (e) { if (/not running/.test(e.message) === false) pairMsg = e.message; }).then(function () { pairBusy = false; paintPair(); }); }
      paint();
    };
    healthGet(a.host, a.port, function (h) { got.remote = h; finish(); });
    healthGet("127.0.0.1", lp, function (h) { got.local = h; finish(); });
    healthGet("127.0.0.1", 3030, function (h) { got.local3030 = h; finish(); });
  }

  // fills the address box with the first relay a probe found (this PC first, then the LAN), unless an address is already set (force: replace it)
  function useFirstFound(force) {
    var f = (VB.bridgeMem.found || []).filter(function (x) { return x.running; })[0];
    if (!f || (!force && String(S().target || "").trim())) return false;
    S().target = f.host + ":" + f.port; if (ctx.save) ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); return true;
  }
  function pairAct(fn, okMsg) {
    return fn().then(function () { pairMsg = okMsg || ""; return VB.bridgePairRefresh(); }).catch(function (e) { pairMsg = e.message; }).then(paint);
  }

  var A = {
    // Attach is read-only: it checks the relay at the saved address and attaches this panel to it. It never starts, stops or restarts anything.
    bg_attach: async function () {
      var res = await ctx.startJob(VB.jobBridgeStatus(ctx.state()), null);
      loadClient(); poll();
      if (!res || !res.ok) { pairMsg = "Could not reach a relay at " + attachAddr().text + "."; paint(); return; }
      var st = VB.bridgeMem.info && VB.bridgeMem.info.status;
      pairMsg = st && st.running ? "Attached to " + (st.remote ? "remote relay at " + st.host + ":" + st.port : "the relay on this PC") + "; module " + (st.moduleConnected ? "connected" : "not connected") + ". Nothing was started or restarted." : "No relay answers at " + attachAddr().text + ".";
      paint();
    },
    bg_status: function () { loadClient(); detectLocal(); return ctx.startJob(VB.jobBridgeStatus(ctx.state()), paint); },
    // Find relay: looks on this PC and the LAN (read-only) and fills in the address of the first relay that answers
    bg_probe: function () { return ctx.startJob(VB.jobBridgeProbe(ctx.state()), function () { useFirstFound(true); paint(); }); },
    // Close bridge: detects a relay on THIS PC again, asks in the panel, stops only that (node.exe only; never a remote relay).
    bg_close: async function () {
      var l = await VB.bridgeLocalDetect(ctx.state()).catch(function (e) { pairMsg = e.message; return null; });
      var plan = VB.bridgeClosePlan(l); paint();
      if (!plan.enabled) { pairMsg = plan.text || "No local bridge running."; paint(); return; }
      if (!(await modal(plan.text, "Close bridge", "Cancel"))) return;
      await ctx.startJob(VB.jobBridgeClose(ctx.state()), null);
      lastLocalUp = null; await detectLocal(); poll();
    },
    bg_stop: function () { return A.bg_close(); },
    // Launch local bridge (secondary): only starts a relay on THIS PC; attaches to a local one that is already running; never restarts.
    bg_launch: async function () {
      if (live && live.running && !attachIsLocal() && !(await modal("A relay is already up at " + attachAddr().text + ". Starting a second one on this PC means two relays. Start a local one anyway?", "Start local relay", "Cancel"))) return;
      await ctx.startJob(VB.jobBridgeLaunch(ctx.state(), { restart: false }), null);
      lastLocalUp = null; await detectLocal(); poll();
    },
    bg_restart: async function () {
      var l = await VB.bridgeLocalDetect(ctx.state()).catch(function () { return null; });
      if (!l || !l.found) { pairMsg = "No local bridge running, nothing to restart."; paint(); return; }
      if (!VB.bridgeClosePlan(l).enabled) { pairMsg = VB.bridgeClosePlan(l).text; paint(); return; }
      if (!(await modal("Restart the relay on THIS PC (pid " + l.pid + ", port " + l.port + ")? The Foundry module reconnects by itself within a few seconds.", "Restart relay", "Keep it running"))) return;
      await ctx.startJob(VB.jobBridgeLaunch(ctx.state(), { restart: true }), null);
      lastLocalUp = null; await detectLocal(); poll();
    },
    bg_reveal: function () { shown.reveal = !shown.reveal; paint(); },
    bg_tokens: function () {   // manual entries for a relay on another PC; never stored
      VB.bridgeMem.manual = { api: ($("bgManApi").value || "").trim(), module: ($("bgManMod").value || "").trim() };
      $("bgManApi").value = ""; $("bgManMod").value = "";
      pairMsg = VB.bridgeMem.manual.api ? "Token kept in memory only." : "";
      VB.bridgePairRefresh().catch(function (e) { pairMsg = e.message; }).then(paint);
    }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    VB.bridgeRoot = ctx.root;
    VB.bridgeAttachNow = function () { return VB.bridgeAttachTarget(ctx.state()); };
    if (ctx.syncInputs) ctx.syncInputs();
    loadClient().then(function () {   // the address is prefilled from client.json (what the tools use), else discovered by a read-only probe; both editable and remembered
      if (String(S().target || "").trim()) return;
      var c = VB.bridgeMem.client; if (c && c.url) { S().target = c.url; if (ctx.save) ctx.save(); if (ctx.syncInputs) ctx.syncInputs(); paint(); return; }
      return (ctx.startJobQueued || ctx.startJob)(VB.jobBridgeProbe(ctx.state()), null).then(function () { useFirstFound(false); paint(); });
    });
    var cf = $("bgClientFile"); if (cf) cf.addEventListener("change", function () { setTimeout(loadClient, 50); });
    var sm = $("bgSummary");
    if (sm) sm.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("button") : null; if (!b) return;
      var po = b.getAttribute("data-bgpairing"), au = b.getAttribute("data-bgauto");
      if (po) pairAct(function () { return VB.bridgePairConfig({ enabled: po === "on" }); }, po === "on" ? "Pairing is on." : "Pairing is off.");
      else if (au) pairAct(function () { return VB.bridgePairConfig({ autoRequest: au === "on" }); }, au === "on" ? "Auto-request is on." : "Auto-request is off.");
    });
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
      if (ap) {
        var sel = pb.querySelector('select[data-bgdays="' + ap + '"]'), req = ((VB.bridgeMem.pair && VB.bridgeMem.pair.pending) || []).filter(function (x) { return x.id === ap; })[0];
        if (!req) { pairMsg = "That request is gone (expired or handled)."; paint(); return; }
        // the code of THIS request goes with the approval; the relay refuses it if the request on its side is a different one. A request with origin warnings needs a second, explicit confirmation.
        var go = function () { return pairAct(function () { return VB.bridgePairApprove(ap, Number(sel ? sel.value : 90), req.code); }, "Approved."); };
        if (req.warnings && req.warnings.length) modal("Warning: " + req.warnings.join("; ") + ". Approve anyway only if the code " + String(req.code).replace(/(\d{3})(\d{3})/, "$1 $2") + " is the one on the Foundry screen.", "Approve anyway", "Cancel").then(function (y) { if (y) go(); });
        else go();
      }
      else if (dn) pairAct(function () { return VB.bridgePairDeny(dn); }, "Denied.");
      else if (rv) modal("Revoke this device? It is disconnected now and must be paired again.", "Revoke", "Cancel").then(function (y) { if (y) pairAct(function () { return VB.bridgePairRevoke(rv); }, "Revoked."); });
      else if (ro) pairAct(function () { return VB.bridgePairRotate(ro); }, "The device gets a new token on its next connect.");
    });
    pairTimer = setInterval(function () {   // cheap read-only list refresh, so a new request/code shows within ~2 s
      var tab = $("tab-foundry"); if (!tab || !tab.classList.contains("on") || pairBusy || !VB.bridgeApiToken()) return;
      var a = attachAddr(); if (!a.host) return;
      pairBusy = true; VB.bridgePairRefresh().then(function () { pairMsg = ""; }, function (e) { if (/not running/.test(e.message) === false) pairMsg = e.message; }).then(function () { pairBusy = false; paintPair(); paintSummary(); });
    }, 2000);
    timer = setInterval(poll, 3000); detectLocal(); poll(); paint();
  }
  window.VBBridgeUI = { init: init, paint: paint, actions: A };
})();
