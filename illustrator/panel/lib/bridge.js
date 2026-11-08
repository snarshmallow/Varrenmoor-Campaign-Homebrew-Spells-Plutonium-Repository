// Bridge section (Foundry tab): launch / stop / status of the managed Foundry relay via foundry-bridge/bridgectl.mjs (hidden detached node process,
// PID file + log file; see foundry-bridge/README.md). Pure logic, no DOM: also loaded by test/test_bridge_jobs.js.
// Secrets (module token, API token) are kept ONLY in memory (VB.bridgeMem) and are never written to panel_state.json, job logs or the panel log.
(function (root) {
  "use strict";
  var VB = root.VBCore || (typeof require !== "undefined" ? require("./core.js") : null);
  if (!VB) return;
  VB.bridgeRoot = VB.bridgeRoot || "";                 // repo root; set by bridge_ui.js (ctx.root) or the test
  VB.bridgeMem = { info: null, secrets: null, at: 0 }; // in-memory only
  // injectable for tests: (nodeExe, args, cwd) -> Promise<{code, out, err}>
  VB.bridgeExec = function (nodeExe, args, cwd) {
    return new Promise(function (resolve) {
      var cp = require("child_process");
      cp.execFile(nodeExe, args, { cwd: cwd, windowsHide: true, timeout: 60000, maxBuffer: 4 * 1024 * 1024 }, function (err, so, se) {
        resolve({ code: err ? (typeof err.code === "number" ? err.code : -1) : 0, out: String(so || ""), err: String(se || (err && err.message) || "") });
      });
    });
  };
  VB.bridgeDefaults = function () { return { node: "", env: "", state: "", cim: false, last: null }; };
  var baseDefaults = VB.defaults;
  VB.defaults = function () { var o = baseDefaults(); o.bridge = VB.bridgeDefaults(); return o; };

  VB.bridgeMask = function (t) { return t ? new Array(13).join("*") : ""; };
  // 'two GM tabs are fighting' = 3 or more "closed 4002" lines in the last 20 log lines
  VB.bridgeLoop4002 = function (lines) { return (lines || []).slice(-20).filter(function (l) { return /closed 4002\b/.test(l); }).length >= 3; };
  // pure decision for the Launch button: what to do given the current status object
  VB.bridgeLaunchPlan = function (status) {
    if (status && status.running) return { action: "confirm-restart", reason: (status.managed ? "A relay launched from here is already running" : "A relay started another way (start.bat?) is already running") + " on port " + status.port + (status.pid ? " (pid " + status.pid + ")" : "") + "." };
    return { action: "start", reason: "" };
  };
  VB.bridgeCtlArgs = function (st, cmd, extra) {
    var b = (st && st.bridge) || {}, a = ["foundry-bridge/bridgectl.mjs", cmd, "--json"];
    if (b.env) a.push("--env", b.env);
    if (b.state) a.push("--state", b.state);
    if (b.node) a.push("--node", b.node);
    if (b.cim && (cmd === "start" || cmd === "restart")) a.push("--cim");
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
  VB.bridgeStatusSummary = function (s) { return { at: new Date().toISOString(), running: !!s.running, managed: !!s.managed, port: s.port, pid: s.pid || null, moduleConnected: !!s.moduleConnected, bind: s.bind, startedAt: s.startedAt || null }; };
  VB.bridgeRemember = function (info) { VB.bridgeMem = { info: info, secrets: info.secrets || null, at: Date.now() }; };

  var infoStep = function (st) { return { t: "fn", label: "read setup info", fn: function (run) {
    return ctl(st, "info", ["--secrets"]).then(function (i) { VB.bridgeRemember(i); run.setState("bridge.last", VB.bridgeStatusSummary(i.status)); run.log("bridge: " + (i.status.running ? "running on port " + i.status.port : "not running")); }); } }; };
  VB.jobBridgeStatus = function (st) { return { kind: "bridge_status", label: "Bridge status", params: {}, steps: [infoStep(st)] }; };
  VB.jobBridgeLaunch = function (st, opts) {
    var restart = !!(opts && opts.restart);
    return { kind: "bridge_launch", label: restart ? "Restart bridge relay" : "Launch bridge relay", params: { restart: restart, bridge: { node: st.bridge.node, cim: st.bridge.cim } },
      steps: [{ t: "fn", label: restart ? "restart relay" : "start relay", fn: function (run) {
        return ctl(st, restart ? "restart" : "start").then(function (r) { run.log("bridge: " + (r.action || "ok") + ", port " + r.port + ", pid " + r.pid); });
      } }, infoStep(st)] };
  };
  VB.jobBridgeStop = function (st) {
    return { kind: "bridge_stop", label: "Stop bridge relay", params: {},
      steps: [{ t: "fn", label: "stop relay", fn: function (run) { return ctl(st, "stop").then(function (r) { run.log("bridge: " + (r.action || "ok")); }); } }, infoStep(st)] };
  };
  if (typeof module !== "undefined" && module.exports) module.exports = VB;
})(typeof window !== "undefined" ? window : this);
