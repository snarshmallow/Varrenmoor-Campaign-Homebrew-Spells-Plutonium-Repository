// Bridge section (Foundry tab): connect to (attach) or launch the Foundry relay via foundry-bridge/bridgectl.mjs, status, stop/restart, pairing on/off and the device
// pairing list (approve / deny / revoke / rotate; encrypted handshake, protocol 2). Pure logic, no DOM: also loaded by test/test_bridge_jobs.js.
// Secrets (module token, API token, manual entries) are kept ONLY in memory (VB.bridgeMem) and are never written to panel_state.json, job logs or the panel log.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  VB.bridgeRoot = VB.bridgeRoot || "";                 // repo root; set by bridge_ui.js (ctx.root) or the test
  VB.bridgeMem = { info: null, secrets: null, at: 0, manual: { api: "", module: "" }, found: [], pair: null, local: null, client: null, clientSecrets: null }; // in-memory only
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
  // Admin calls are SIGNED (X-VB-Auth: HMAC of the request keyed by the API token): the token itself never travels over the plain-http LAN. Same format as foundry-bridge/relay/adminauth.js.
  VB.bridgeSign = function (token, method, url, body, ts, nonce) {
    var c = require("crypto"); ts = ts || Date.now(); nonce = nonce || c.randomBytes(12).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    var sig = c.createHmac("sha256", token).update(["vb-admin-v1", String(method).toUpperCase(), url, String(ts), nonce, c.createHash("sha256").update(body || "").digest("hex")].join("\n")).digest("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    return "v1 ts=" + ts + " n=" + nonce + " sig=" + sig;
  };
  VB.bridgeHttp = function (o) {
    return new Promise(function (resolve, reject) {
      var data = o.body ? JSON.stringify(o.body) : "";
      var headers = { "content-type": "application/json", "content-length": Buffer.byteLength(data) };
      if (o.token && o.sign) headers["x-vb-auth"] = VB.bridgeSign(o.token, o.method || "POST", o.path, data);
      else if (o.token) headers.authorization = "Bearer " + o.token;
      var req = require("http").request({ method: o.method || "POST", host: o.host, port: o.port, path: o.path, headers: headers, timeout: 4000 }, function (r) {
        var b = ""; r.on("data", function (c) { b += c; });
        r.on("end", function () { var j = {}; try { j = JSON.parse(b); } catch (e) { /* empty */ } resolve({ status: r.statusCode, body: j }); });
      });
      req.on("error", reject); req.on("timeout", function () { req.destroy(new Error("timeout")); });
      req.end(data);
    });
  };
  // Attach is the primary mode: the relay normally runs on an always-on PC. target = where to attach (editable, remembered; not a secret). No address is built in: it comes from the
  // saved setting, else from the relay URL in the client.json the tools already use (VB.bridgeMem.client.url), else it stays blank until "Find relays" / typing.
  VB.BRIDGE_ATTACH_DEFAULT = "";
  VB.bridgeDefaults = function () { return { node: "", env: "", state: "", cim: false, hidden: false, terminal: "auto", target: VB.BRIDGE_ATTACH_DEFAULT, mode: "attach", clientFile: "", last: null }; };
  // "http://10.0.0.15:3030" / "10.0.0.15" / "localhost:3030" -> { host, port } (port null when not given); blank -> {host:"",port:null}
  VB.bridgeParseTarget = function (s) {
    s = String(s || "").trim(); if (!s) return { host: "", port: null };
    var m = s.replace(/^[a-z]+:\/\//i, "").split("/")[0].match(/^(\[[^\]]+\]|[^:]+)(?::(\d+))?$/);
    return m ? { host: m[1].replace(/^\[|\]$/g, ""), port: m[2] ? Number(m[2]) : null } : { host: "", port: null };
  };
  VB.bridgeIsLoopback = function (host) { host = String(host || "").toLowerCase(); return !host || host === "localhost" || host === "::1" || /^127\./.test(host); };
  // the address attach mode talks to: the saved one, else the default; "local" mode (Launch local bridge) has none
  VB.bridgeAttachTarget = function (st) { var b = (st && st.bridge) || {}; if (b.mode === "local") return ""; var c = VB.bridgeMem && VB.bridgeMem.client; return String(b.target || "").trim() || (c && c.url) || VB.BRIDGE_ATTACH_DEFAULT; };
  var sameRelay = function (a, b) {
    var x = VB.bridgeParseTarget(a), y = VB.bridgeParseTarget(b); if (!x.host || !y.host) return false;
    var lo = function (h) { return VB.bridgeIsLoopback(h) ? "loopback" : h.toLowerCase(); };
    return lo(x.host) === lo(y.host) && (x.port || 80) === (y.port || 80);
  };
  // Where foundry_push.py (via foundry-bridge/bridge.ps1) gets its relay URL AND token, in bridge.ps1's order: env FOUNDRY_BRIDGE_URL+TOKEN, a file chosen in Advanced (bridge.clientFile),
  // env FOUNDRY_BRIDGE_CONFIG, foundry-bridge/client.json, then \\<host>\...\client.json on the PC that runs the relay. Nothing is hard-coded: <host> is env FOUNDRY_BRIDGE_HOST, the host of
  // foundry-3d/.env FOUNDRY_ASSETS_DIR, or the host the panel is attached to; the path under the share is env FOUNDRY_BRIDGE_SHARE ({host} is replaced) or the default guess
  // "\\{host}\C\FoundryVTT resources\bridge\client.json" (the file start.bat writes next to Foundry's data folder).
  // io = { fs, env, root, readShare(path) -> Promise<string|null>, attachHost, clientFile } (injectable for tests). Returns { url, source, localFile, share, tried }; the url only: the tokens
  // found in the file go to VB.bridgeMem.clientSecrets (memory only) and are never part of the result, a log line or panel_state.json.
  VB.bridgeClientInfo = function (io) {
    var fs = io.fs, env = io.env || {}, root = String(io.root || "").replace(/\\/g, "/");
    var parse = function (txt) { try { var j = JSON.parse(String(txt).replace(/^\uFEFF/, "")); return j && typeof j === "object" ? j : null; } catch (e) { return null; } };
    var readLocal = function (f) { try { return fs.readFileSync(f, "utf8"); } catch (e) { return null; } };
    var isUnc = function (f) { return /^\\\\/.test(f) || /^\/\//.test(f); };
    var done = function (txt, source, extra) {
      var j = parse(txt) || {}; VB.bridgeMem.clientSecrets = { api: j.token ? String(j.token) : "", module: j.moduleToken ? String(j.moduleToken) : "", url: j.url ? String(j.url) : "", source: source };
      return Object.assign({ url: j.url ? String(j.url) : "", source: source, localFile: false }, extra || {});
    };
    VB.bridgeMem.clientSecrets = null;
    if (env.FOUNDRY_BRIDGE_URL && env.FOUNDRY_BRIDGE_TOKEN) { VB.bridgeMem.clientSecrets = { api: String(env.FOUNDRY_BRIDGE_TOKEN), module: "", url: String(env.FOUNDRY_BRIDGE_URL), source: "environment" }; return Promise.resolve({ url: env.FOUNDRY_BRIDGE_URL, source: "environment FOUNDRY_BRIDGE_URL", localFile: false }); }
    var explicit = []; if (io.clientFile) explicit.push(io.clientFile); if (env.FOUNDRY_BRIDGE_CONFIG) explicit.push(env.FOUNDRY_BRIDGE_CONFIG);
    var local = root + "/foundry-bridge/client.json";
    var hosts = [], addHost = function (h) { h = String(h || "").trim(); if (h && !VB.bridgeIsLoopback(h) && hosts.indexOf(h) < 0) hosts.push(h); };
    addHost(env.FOUNDRY_BRIDGE_HOST);
    var e = readLocal(root + "/foundry-3d/.env"), m = e && e.match(/^\s*FOUNDRY_ASSETS_DIR\s*=\s*\\\\([^\\]+)\\/m); if (m) addHost(m[1]);
    addHost(io.attachHost);
    var tmpl = env.FOUNDRY_BRIDGE_SHARE || "\\\\{host}\\C\\FoundryVTT resources\\bridge\\client.json";
    var shares = hosts.map(function (h) { return tmpl.replace(/\{host\}/g, h); });
    var tried = [], i, t;
    for (i = 0; i < explicit.length; i++) {   // a file chosen on purpose: a local path or a share
      if (isUnc(explicit[i]) && io.readShare) continue;
      t = readLocal(explicit[i]); tried.push(explicit[i]); if (t !== null) return Promise.resolve(done(t, explicit[i], { localFile: false }));
    }
    t = readLocal(local); tried.push(local);
    if (t !== null) return Promise.resolve(done(t, "foundry-bridge/client.json on this PC", { localFile: true }));
    var remote = explicit.filter(function (f) { return isUnc(f); }).concat(shares), idx = 0;
    var next = function () {
      if (idx >= remote.length) {
        var why = remote.length ? "none found (no foundry-bridge/client.json here, and nothing readable at " + remote.join(" or ") + ")" : "none found (no foundry-bridge/client.json here, and no relay PC known to look on: attach to a relay first, set FOUNDRY_BRIDGE_HOST, or choose the file under Advanced)";
        return { url: "", source: why, localFile: false, share: remote[0] || "", tried: tried.concat(remote) };
      }
      var f = remote[idx++]; tried.push(f);
      return Promise.resolve(io.readShare ? io.readShare(f) : null).then(function (txt) { return txt === null || txt === undefined ? next() : done(txt, f, { share: f }); });
    };
    return Promise.resolve(next());
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
  VB.bridgeRemember = function (info) { var m = VB.bridgeMem.manual || { api: "", module: "" }; VB.bridgeMem = { info: info, secrets: info.secrets || null, at: Date.now(), manual: m, found: VB.bridgeMem.found || [], pair: VB.bridgeMem.pair, local: VB.bridgeMem.local, client: VB.bridgeMem.client, clientSecrets: VB.bridgeMem.clientSecrets }; };
  // Where the admin (API) token comes from, in order: (1) the relay's own .env, ONLY when the attached relay runs on this PC; (2) the client.json the tools already use
  // (foundry-bridge/client.json or the share), when it names the relay this panel is attached to; (3) a password typed in Advanced (memory only). Returns { token, source }.
  VB.bridgeTokenSource = function (kind) {   // kind: "api" | "module"
    var m = VB.bridgeMem, info = m.info, remote = !!(info && info.status && info.status.remote), key = kind === "module" ? "moduleToken" : "apiToken";
    if (m.secrets && m.secrets[key] && !remote) return { token: m.secrets[key], source: "the relay's .env on this PC" };
    var cs = m.clientSecrets, att = (typeof VB.bridgeAttachNow === "function" && VB.bridgeAttachNow()) || "";
    if (cs && cs[kind] && (!att || !cs.url || sameRelay(cs.url, att))) return { token: cs[kind], source: "client.json (" + (cs.source || "found by the tools") + ")" };
    var man = kind === "module" ? m.manual.module : m.manual.api;
    return man ? { token: man, source: "typed (memory only)" } : { token: "", source: "" };
  };
  VB.bridgeApiToken = function () { return VB.bridgeTokenSource("api").token; };
  VB.bridgeModuleToken = function () { return VB.bridgeTokenSource("module").token; };

  // ---- pairing admin (HTTP to the relay; LAN/loopback only on the relay side) --------------------------------------------------------
  function relayAddr() {   // the relay a status job found running; else the attached address (so pairing works right after the panel opens, before any job ran)
    var i = VB.bridgeMem.info, s = i && i.status; if (s && s.running) return { host: s.remote ? s.host : "127.0.0.1", port: s.port };
    var t = VB.bridgeParseTarget(typeof VB.bridgeAttachNow === "function" ? VB.bridgeAttachNow() : ""); if (t.host) return { host: t.host, port: t.port || 3030 };
    throw new Error("the relay is not running");
  }
  VB.bridgePairCall = function (p, body) {
    var tok = VB.bridgeApiToken(); if (!tok) return Promise.reject(new Error("no API token yet: it is read from client.json (the file the tools use) or the relay's .env; otherwise type it under Advanced"));
    var a = relayAddr();
    return VB.bridgeHttp({ method: "POST", host: a.host, port: a.port, path: p, token: tok, sign: true, body: body || {} }).then(function (r) {
      if (r.status === 401) throw new Error(r.body && /older than/.test(r.body.error || "") ? "the relay was restarted a moment ago and this signed call predates it; it is retried automatically" : r.body && /clock/.test(r.body.error || "") ? "the PCs' clocks differ by more than 5 minutes (fix the time on one of them)" : "the relay rejected the API token (wrong token, or the relay is older than 0.5: restart it once with the current start.bat)");
      if (r.status === 404 && r.body && r.body.error === "not found") throw new Error("this relay is older than 0.5 and has no pairing admin: close its window and run start.bat once on that PC (nothing else to do)");
      if (r.status === 403) throw new Error((r.body && r.body.error) || "the relay refuses pairing admin from this address (LAN/loopback only; off while the relay runs in tunnel mode)");
      if (r.status >= 400) throw new Error((r.body && r.body.error) || "relay answered " + r.status);
      return r.body;
    });
  };
  VB.bridgePairRefresh = function () { return VB.bridgePairCall("/pair/list").then(function (l) { VB.bridgeMem.pair = l; return l; }); };
  // code: the confirmation code of the request that was on screen when Approve was pressed; the relay refuses the approval unless it matches THAT request (never "whatever is oldest")
  VB.bridgePairApprove = function (id, days, code) { return VB.bridgePairCall("/pair/approve", { id: id, days: days, code: String(code == null ? "" : code) }); };
  VB.bridgePairDeny = function (id) { return VB.bridgePairCall("/pair/deny", { id: id }); };
  VB.bridgePairRevoke = function (deviceId) { return VB.bridgePairCall("/pair/revoke", { deviceId: deviceId }); };
  VB.bridgePairRotate = function (deviceId) { return VB.bridgePairCall("/pair/rotate", { deviceId: deviceId }); };
  // switch pairing on/off (and auto-request) on the running relay, no restart. enabled/autoRequest are booleans; omit to leave unchanged.
  VB.bridgePairConfig = function (cfg) { return VB.bridgePairCall("/pair/config", cfg || {}); };

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
