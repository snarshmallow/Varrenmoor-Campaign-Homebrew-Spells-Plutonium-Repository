// Bridge section (Foundry tab): connect to (attach) or launch the Foundry relay via foundry-bridge/bridgectl.mjs, status, stop/restart, and the device
// pairing list (approve / deny / revoke / rotate). Pure logic, no DOM: also loaded by test/test_bridge_jobs.js.
// Secrets (module token, API token, manual entries) are kept ONLY in memory (VB.bridgeMem) and are never written to panel_state.json, job logs or the panel log.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  VB.bridgeRoot = VB.bridgeRoot || "";                 // repo root; set by bridge_ui.js (ctx.root) or the test
  VB.bridgeMem = { info: null, secrets: null, at: 0, manual: { api: "", module: "" }, found: [], pair: null, local: null, client: null }; // in-memory only
  // injectable for tests: (nodeExe, args, cwd) -> Promise<{code, out, err}>
  VB.bridgeExec = function (nodeExe, args, cwd) {
    return new Promise(function (resolve) {
      var cp = require("child_process");
      cp.execFile(nodeExe, args, { cwd: cwd, windowsHide: true, timeout: 60000, maxBuffer: 4 * 1024 * 1024 }, function (err, so, se) {
        resolve({ code: err ? (typeof err.code === "number" ? err.code : -1) : 0, out: String(so || ""), err: String(se || (err && err.message) || "") });
      });
    });
  };
  // injectable for tests: ({method, host, port, path, token, body}) -> Promise<{status, body}>. The token goes in the Authorization header only.
  VB.bridgeHttp = function (o) {
    return new Promise(function (resolve, reject) {
      var data = o.body ? JSON.stringify(o.body) : "";
      var headers = { "content-type": "application/json", "content-length": Buffer.byteLength(data) };
      if (o.token) headers.authorization = "Bearer " + o.token;
      var req = require("http").request({ method: o.method || "POST", host: o.host, port: o.port, path: o.path, headers: headers, timeout: 4000 }, function (r) {
        var b = ""; r.on("data", function (c) { b += c; });
        r.on("end", function () { var j = {}; try { j = JSON.parse(b); } catch (e) { /* empty */ } resolve({ status: r.statusCode, body: j }); });
      });
      req.on("error", reject); req.on("timeout", function () { req.destroy(new Error("timeout")); });
      req.end(data);
    });
  };
  // Attach is the primary mode: the relay normally runs on the always-on PC (Vega). target = where to attach (editable, remembered; not a secret).
  VB.BRIDGE_ATTACH_DEFAULT = "http://10.0.0.15:3030";
  VB.bridgeDefaults = function () { return { node: "", env: "", state: "", cim: false, hidden: false, terminal: "auto", target: VB.BRIDGE_ATTACH_DEFAULT, mode: "attach", last: null }; };
  // "http://10.0.0.15:3030" / "10.0.0.15" / "localhost:3030" -> { host, port } (port null when not given); blank -> {host:"",port:null}
  VB.bridgeParseTarget = function (s) {
    s = String(s || "").trim(); if (!s) return { host: "", port: null };
    var m = s.replace(/^[a-z]+:\/\//i, "").split("/")[0].match(/^(\[[^\]]+\]|[^:]+)(?::(\d+))?$/);
    return m ? { host: m[1].replace(/^\[|\]$/g, ""), port: m[2] ? Number(m[2]) : null } : { host: "", port: null };
  };
  VB.bridgeIsLoopback = function (host) { host = String(host || "").toLowerCase(); return !host || host === "localhost" || host === "::1" || /^127\./.test(host); };
  // the address attach mode talks to: the saved one, else the default; "local" mode (Launch local bridge) has none
  VB.bridgeAttachTarget = function (st) { var b = (st && st.bridge) || {}; return b.mode === "local" ? "" : (String(b.target || "").trim() || VB.BRIDGE_ATTACH_DEFAULT); };
  var sameRelay = function (a, b) {
    var x = VB.bridgeParseTarget(a), y = VB.bridgeParseTarget(b); if (!x.host || !y.host) return false;
    var lo = function (h) { return VB.bridgeIsLoopback(h) ? "loopback" : h.toLowerCase(); };
    return lo(x.host) === lo(y.host) && (x.port || 80) === (y.port || 80);
  };
  // Where foundry_push.py (via foundry-bridge/bridge.ps1) gets its relay URL, in bridge.ps1's order: env FOUNDRY_BRIDGE_URL, FOUNDRY_BRIDGE_CONFIG, foundry-bridge/client.json,
  // then \\<host>\C\FoundryVTT resources\bridge\client.json (host from foundry-3d/.env FOUNDRY_ASSETS_DIR, default VEGA). Only the url is read; the token is never kept.
  // io = { fs, env, root, readShare(path) -> Promise<string|null> } (injectable for tests)
  VB.bridgeClientInfo = function (io) {
    var fs = io.fs, env = io.env || {}, root = String(io.root || "").replace(/\\/g, "/");
    var urlOf = function (txt) { try { var j = JSON.parse(String(txt).replace(/^\uFEFF/, "")); return j && j.url ? String(j.url) : ""; } catch (e) { return ""; } };
    var readLocal = function (f) { try { return fs.readFileSync(f, "utf8"); } catch (e) { return null; } };
    if (env.FOUNDRY_BRIDGE_URL && env.FOUNDRY_BRIDGE_TOKEN) return Promise.resolve({ url: env.FOUNDRY_BRIDGE_URL, source: "environment FOUNDRY_BRIDGE_URL", localFile: false });
    var cfg = env.FOUNDRY_BRIDGE_CONFIG; if (cfg) { var t0 = readLocal(cfg); if (t0 !== null) return Promise.resolve({ url: urlOf(t0), source: cfg, localFile: false }); }
    var local = root + "/foundry-bridge/client.json", t1 = readLocal(local);
    if (t1 !== null) return Promise.resolve({ url: urlOf(t1), source: "foundry-bridge/client.json on this PC", localFile: true });
    var host = "VEGA", e = readLocal(root + "/foundry-3d/.env"), m = e && e.match(/^\s*FOUNDRY_ASSETS_DIR\s*=\s*\\\\([^\\]+)\\/m); if (m) host = m[1];
    var share = "\\\\" + host + "\\C\\FoundryVTT resources\\bridge\\client.json";
    return Promise.resolve(io.readShare ? io.readShare(share) : null).then(function (txt) {
      return txt === null || txt === undefined ? { url: "", source: "none found (no foundry-bridge/client.json here, and " + share + " is unreachable)", localFile: false, share: share }
        : { url: urlOf(txt), source: share, localFile: false, share: share };
    });
  };
  // compares the URL foundry_push would use with the relay this panel is attached to; { ok, text }
  VB.bridgeClientCheck = function (clientUrl, attach) {
    if (!clientUrl) return { ok: false, text: "foundry_push.py has no relay URL to use right now." };
    if (!attach || sameRelay(clientUrl, attach)) return { ok: true, text: "" };
    var loop = VB.bridgeIsLoopback(VB.bridgeParseTarget(clientUrl).host) && !VB.bridgeIsLoopback(VB.bridgeParseTarget(attach).host);
    return { ok: false, text: "foundry_push.py will call " + clientUrl + ", but this panel is attached to " + attach + "." + (loop ? " 127.0.0.1 on this PC is NOT the relay on the other PC (probably an old client.json)." : "") + " Fix: remove or edit foundry-bridge/client.json on this PC, or fix the file on the share." };
  };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.bridge = VB.bridgeDefaults(); return o; };

  VB.bridgeMask = function (t) { return t ? new Array(13).join("*") : ""; };
  // 'two GM tabs are fighting' = 3 or more "closed 4002" lines in the last 20 log lines
  VB.bridgeLoop4002 = function (lines) { return (lines || []).slice(-20).filter(function (l) { return /closed 4002\b/.test(l); }).length >= 3; };
  // pure decision for the Connect/Launch button: something already running is ATTACHED to (never restarted); only a stopped relay is launched
  VB.bridgeLaunchPlan = function (status) {
    if (status && status.running) return { action: "attach", reason: (status.managed ? "Connected to the relay launched from here" : "Attached to a relay that was started another way") + " on " + (status.host || "127.0.0.1") + ":" + status.port + (status.pid ? " (pid " + status.pid + ")" : "") + "." };
    return { action: "start", reason: "" };
  };
  // wording for the confirmation modals (Restart / Stop); remote relays cannot be controlled from here
  VB.bridgeRestartPlan = function (status) {
    if (!status || !status.running) return { allowed: true, ask: false, text: "" };
    if (status.remote) return { allowed: false, ask: false, text: "That relay runs on another PC (" + status.host + "); restart it there." };
    return { allowed: true, ask: true, text: (status.managed ? "Restart the relay launched from here" : "Restart the relay that was started another way (start.bat?)") + " on port " + status.port + (status.pid ? " (pid " + status.pid + ")" : "") + "? The Foundry module reconnects by itself within a few seconds." };
  };
  VB.bridgeStopPlan = function (status) {
    if (!status || !status.running) return { allowed: true, ask: false, text: "" };
    if (status.remote) return { allowed: false, ask: false, text: "That relay runs on another PC (" + status.host + "); stop it there." };
    return { allowed: true, ask: true, text: "Stop the bridge relay" + (status.managed ? "" : " (it was NOT started from here)") + "? Claude and the Illustrator Foundry tab lose access until it is launched again." };
  };
  // local / closelocal never get --target: they only ever look at, and stop, a relay on this PC
  VB.bridgeCtlArgs = function (st, cmd, extra) {
    var b = (st && st.bridge) || {}, a = ["foundry-bridge/bridgectl.mjs", cmd, "--json"], tgt = VB.bridgeAttachTarget(st);
    if (b.env) a.push("--env", b.env);
    if (b.state) a.push("--state", b.state);
    if (b.node) a.push("--node", b.node);
    if (tgt && cmd !== "local" && cmd !== "closelocal") a.push("--target", tgt);
    if (b.hidden && (cmd === "start" || cmd === "restart")) a.push("--hidden");
    if (b.cim && (cmd === "start" || cmd === "restart")) a.push("--cim");
    if (b.terminal && b.terminal !== "auto" && (cmd === "start" || cmd === "restart")) a.push("--terminal", b.terminal);
    return a.concat(extra || []);
  };
  VB.bridgeNode = function (st) { return (st && st.bridge && st.bridge.node) || "node"; };
  function parse(r, what) {
    var t = String(r.out || "").trim(), j = null, lines = t.split(/\r?\n/);
    for (var i = lines.length - 1; i >= 0 && !j; i--) { if (lines[i].charAt(0) === "{") { try { j = JSON.parse(lines[i]); } catch (e) { /* next */ } } }
    if (!j) throw new Error(what + ": " + (r.code === -1 || /ENOENT/.test(r.err) ? "cannot run node (install Node 20+ or set the Node path under Bridge options)" : "no JSON from bridgectl: " + (r.err || t).slice(0, 200)));
    if (j.error) throw new Error(what + ": " + j.error);
    return j;
  }
  function ctl(st, cmd, extra) { return VB.bridgeExec(VB.bridgeNode(st), VB.bridgeCtlArgs(st, cmd, extra), VB.bridgeRoot).then(function (r) { return parse(r, "bridge " + cmd); }); }
  // state for "Launch local bridge": same settings, but never an attach address
  VB.bridgeLocalState = function (st) { return { bridge: Object.assign({}, (st && st.bridge) || {}, { mode: "local", target: "" }) }; };
  // detects a relay on THIS PC (PID file, netstat, /health on localhost); stored in VB.bridgeMem.local
  VB.bridgeLocalDetect = function (st) { return ctl(st, "local").then(function (r) { VB.bridgeMem.local = r; return r; }); };
  VB.bridgeLocalClose = function (st) { return ctl(st, "closelocal").then(function (r) { if (r.local) VB.bridgeMem.local = r.local; return r; }); };
  // wording + enabled state for the Close bridge button
  VB.bridgeClosePlan = function (l) {
    if (!l || !l.found) return { enabled: false, label: "No local bridge running", text: "" };
    var what = "pid " + (l.pid || "?") + " (" + (l.imageName || "unknown process") + ") on port " + l.port + ", " + (l.how || "");
    if (!l.isNode) return { enabled: false, label: "Cannot close: not node.exe", text: "The process found is " + (l.imageName || "unknown") + ", not node.exe, so it will not be touched." };
    return { enabled: true, label: "Close bridge", text: "Close the bridge relay running on THIS PC (" + what + ")? Only this PC's relay is stopped; a relay on another PC is not touched." };
  };
  // two relays at once: the local one should go
  VB.bridgeTwoRelays = function (localUp, remoteUp, attachIsLocal) { return !!(localUp && remoteUp && !attachIsLocal); };
  VB.bridgeStatusSummary =function (s) { return { at: new Date().toISOString(), running: !!s.running, managed: !!s.managed, mode: s.mode || null, port: s.port, host: s.host || null, pid: s.pid || null, moduleConnected: !!s.moduleConnected, bind: s.bind, startedAt: s.startedAt || null }; };
  // keeps the manual token entries across refreshes
  VB.bridgeRemember = function (info) { var m = VB.bridgeMem.manual || { api: "", module: "" }; VB.bridgeMem = { info: info, secrets: info.secrets || null, at: Date.now(), manual: m, found: VB.bridgeMem.found || [], pair: VB.bridgeMem.pair, local: VB.bridgeMem.local, client: VB.bridgeMem.client }; };
  // the API token pairing admin calls need: the relay's own .env on this PC, else the manual entry
  VB.bridgeApiToken = function () { var s = VB.bridgeMem.secrets; return (s && s.apiToken) || VB.bridgeMem.manual.api || ""; };
  VB.bridgeModuleToken = function () { var s = VB.bridgeMem.secrets; return (s && s.moduleToken) || VB.bridgeMem.manual.module || ""; };

  // ---- pairing admin (HTTP to the relay; LAN/loopback only on the relay side) --------------------------------------------------------
  function relayAddr() {
    var i = VB.bridgeMem.info, s = i && i.status; if (!s || !s.running) throw new Error("the relay is not running");
    return { host: s.remote ? s.host : "127.0.0.1", port: s.port };
  }
  VB.bridgePairCall = function (p, body) {
    var tok = VB.bridgeApiToken(); if (!tok) return Promise.reject(new Error("no API token: it is read from foundry-bridge/.env on this PC, or type it under Tokens for another PC"));
    var a = relayAddr();
    return VB.bridgeHttp({ method: "POST", host: a.host, port: a.port, path: p, token: tok, body: body || {} }).then(function (r) {
      if (r.status === 401) throw new Error("the relay rejected the API token");
      if (r.status === 403) throw new Error("the relay refuses pairing admin from this address (LAN/loopback only)");
      if (r.status >= 400) throw new Error((r.body && r.body.error) || "relay answered " + r.status);
      return r.body;
    });
  };
  VB.bridgePairRefresh = function () { return VB.bridgePairCall("/pair/list").then(function (l) { VB.bridgeMem.pair = l; return l; }); };
  VB.bridgePairApprove = function (id, days) { return VB.bridgePairCall("/pair/approve", { id: id, days: days }); };
  VB.bridgePairDeny = function (id) { return VB.bridgePairCall("/pair/deny", { id: id }); };
  VB.bridgePairRevoke = function (deviceId) { return VB.bridgePairCall("/pair/revoke", { deviceId: deviceId }); };
  VB.bridgePairRotate = function (deviceId) { return VB.bridgePairCall("/pair/rotate", { deviceId: deviceId }); };

  var infoStep = function (st) { return { t: "fn", label: "read setup info", fn: function (run) {
    return ctl(st, "info", ["--secrets"]).then(function (i) { VB.bridgeRemember(i); run.setState("bridge.last", VB.bridgeStatusSummary(i.status)); run.log("bridge: " + (i.status.running ? (i.status.mode || "running") + " on " + (i.status.host || "127.0.0.1") + ":" + i.status.port : "not running")); }); } }; };
  VB.jobBridgeStatus = function (st) { return { kind: "bridge_status", label: "Bridge status", params: {}, steps: [infoStep(st)] }; };
  VB.jobBridgeProbe = function (st) {
    return { kind: "bridge_probe", label: "Find relays", params: {}, steps: [{ t: "fn", label: "look for relays", fn: function (run) {
      return ctl(st, "probe").then(function (r) { VB.bridgeMem.found = r.found || []; run.log("bridge: " + VB.bridgeMem.found.filter(function (x) { return x.running; }).length + " relay(s) found"); }); } }] };
  };
  VB.jobBridgeLaunch = function (st0, opts) {
    var st = VB.bridgeLocalState(st0), restart = !!(opts && opts.restart);   // launching is always about THIS PC
    return { kind: "bridge_launch", label: restart ? "Restart bridge relay" : "Connect or launch bridge relay", params: { restart: restart, bridge: { node: st.bridge.node, cim: st.bridge.cim, hidden: st.bridge.hidden, terminal: st.bridge.terminal, target: st.bridge.target } },
      steps: [{ t: "fn", label: restart ? "restart relay" : "start relay (attaches when one is already running)", fn: function (run) {
        return ctl(st, restart ? "restart" : "start").then(function (r) { run.log("bridge: " + (r.action || "ok") + ", port " + r.port + ", pid " + r.pid + (r.how ? ", " + r.how : "")); });
      } }, infoStep(st)] };
  };
  // closes ONLY a relay on this PC (bridgectl closelocal: node.exe only, never a remote relay)
  VB.jobBridgeClose = function (st) {
    return { kind: "bridge_close_local", label: "Close local bridge", params: {},
      steps: [{ t: "fn", label: "close the relay on this PC", fn: function (run) { return VB.bridgeLocalClose(st).then(function (r) { run.log("bridge: local " + (r.action || "ok") + (r.pid ? ", pid " + r.pid : "")); }); } }] };
  };
  VB.jobBridgeStop = function (st) {
    return { kind: "bridge_stop", label: "Stop bridge relay", params: {},
      steps: [{ t: "fn", label: "stop relay", fn: function (run) { return ctl(st, "stop").then(function (r) { run.log("bridge: " + (r.action || "ok")); }); } }, infoStep(st)] };
  };
  if (typeof module !== "undefined" && module.exports) module.exports = VB;
})(typeof window !== "undefined" ? window : this);
