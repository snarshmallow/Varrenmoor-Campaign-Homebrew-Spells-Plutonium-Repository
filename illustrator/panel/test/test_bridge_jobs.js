// Bridge section: job args and state (mock exec), launch plan, 4002 detection, token handling, then a real launch/stop on a throwaway port.
//   node illustrator/panel/test/test_bridge_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), net = require("net");
const VB = require("../lib/core.js"); require("../lib/bridge.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbbridge-")), tmp = TMP.split(path.sep).join("/");
const st = VB.normalize(null); VB.bridgeRoot = ROOT;
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const MOD = "throwaway-module-token-0123456789", API = "throwaway-api-token-abcdefghijklm";
const logs = [];
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn: require("child_process").spawn, host: async () => ({ ok: true }), log: m => logs.push(m),
  getPython: () => "python", getPlace: () => "x", getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
const freePort = (p) => new Promise(res => { const s = net.createServer(); s.once("error", () => res(freePort(p + 1))); s.listen(p, "0.0.0.0", () => s.close(() => res(p))); });
(async () => {
  check("state defaults", st.bridge && st.bridge.node === "" && st.bridge.cim === false && st.bridge.last === null);
  check("args: default", VB.bridgeCtlArgs(st, "status").join(" ") === "foundry-bridge/bridgectl.mjs status --json");
  st.bridge.env = "C:/t/e.env"; st.bridge.state = "C:/t/run"; st.bridge.cim = true; st.bridge.node = "C:/n/node.exe";
  check("args: env/state/node/cim only for start+restart", VB.bridgeCtlArgs(st, "start").join(" ") === "foundry-bridge/bridgectl.mjs start --json --env C:/t/e.env --state C:/t/run --node C:/n/node.exe --cim" && VB.bridgeCtlArgs(st, "info", ["--secrets"]).indexOf("--cim") < 0);
  check("launch plan: stopped -> start", VB.bridgeLaunchPlan({ running: false }).action === "start");
  const lp = VB.bridgeLaunchPlan({ running: true, managed: false, port: 3030, pid: 12 });
  check("launch plan: running -> confirm restart", lp.action === "confirm-restart" && /3030/.test(lp.reason) && /start\.bat/.test(lp.reason), lp.reason);
  const l = (n) => new Array(n).fill("19:00:00 module socket closed 4002");
  check("4002 loop: 3 in last 20 lines", VB.bridgeLoop4002(["a", "b"].concat(l(3))) && !VB.bridgeLoop4002(l(2)) && !VB.bridgeLoop4002(l(3).concat(new Array(20).fill("x"))));
  check("mask hides the token", VB.bridgeMask(MOD).indexOf("throw") < 0 && VB.bridgeMask("") === "");

  // mock exec: records args, returns canned JSON
  const calls = []; const realExec = VB.bridgeExec;
  VB.bridgeExec = async (node, args, cwd) => { calls.push({ node, args, cwd }); const cmd = args[1];
    const status = { running: true, managed: cmd !== "stop", port: 3030, pid: 5, bind: "0.0.0.0", moduleConnected: true };
    return { code: 0, out: JSON.stringify(cmd === "info" ? { status, urls: {}, moduleSettings: {}, secrets: { moduleToken: MOD, apiToken: API }, logTail: [] } : Object.assign({ action: cmd }, status)) + "\n", err: "" }; };
  st.bridge.cim = false;
  let r = await runner.run(VB.jobBridgeLaunch(st, { restart: true }));
  check("restart job: restart then info --secrets", r.ok && calls[0].args[1] === "restart" && calls[1].args[1] === "info" && calls[1].args.indexOf("--secrets") > 0 && calls[0].node === "C:/n/node.exe" && calls[0].cwd === ROOT, r.error);
  check("state.bridge.last is set and holds no tokens", st.bridge.last && st.bridge.last.running === true && JSON.stringify(st.bridge).indexOf(MOD) < 0 && JSON.stringify(st.bridge).indexOf(API) < 0);
  check("tokens held in memory only", VB.bridgeMem.secrets && VB.bridgeMem.secrets.moduleToken === MOD);
  const logFile = r.logFile ? fs.readFileSync(r.logFile, "utf8") : "";
  check("job log and panel log contain no tokens", logFile.indexOf(MOD) < 0 && logFile.indexOf(API) < 0 && logs.join("\n").indexOf(MOD) < 0 && logs.join("\n").indexOf(API) < 0);
  VB.bridgeExec = async () => ({ code: 0, out: JSON.stringify({ error: "port 3030 busy" }), err: "" });
  r = await runner.run(VB.jobBridgeStop(st));
  check("error from bridgectl surfaces", !r.ok && /port 3030 busy/.test(r.error), r.error);
  VB.bridgeExec = async () => ({ code: -1, out: "", err: "spawn node ENOENT" });
  r = await runner.run(VB.jobBridgeStatus(st));
  check("missing node gives a plain message", !r.ok && /cannot run node/.test(r.error), r.error);

  // real bridgectl against a throwaway port / env / state dir (never the real relay)
  VB.bridgeExec = realExec; const port = await freePort(8799);
  fs.writeFileSync(tmp + "/e.env", `BRIDGE_API_TOKEN=${API}\nBRIDGE_MODULE_TOKEN=${MOD}\nPORT=${port}\nBIND_HOST=127.0.0.1\nCLIENT_CONFIG_DIR=${tmp}/client\n`);
  st.bridge.env = tmp + "/e.env"; st.bridge.state = tmp + "/run"; st.bridge.node = ""; st.bridge.cim = false;
  r = await runner.run(VB.jobBridgeStatus(st));
  check("real: status says stopped", r.ok && st.bridge.last.running === false, r.error);
  r = await runner.run(VB.jobBridgeLaunch(st));
  check("real: launch starts a managed relay", r.ok && st.bridge.last.running && st.bridge.last.managed && st.bridge.last.port === port, r.error);
  check("real: info carries tokens in memory and urls", VB.bridgeMem.secrets.moduleToken === MOD && /ws:\/\/127\.0\.0\.1:/.test(VB.bridgeMem.info.urls.localhost));
  r = await runner.run(VB.jobBridgeStatus(st));
  check("real: plan now asks to restart", VB.bridgeLaunchPlan(VB.bridgeMem.info.status).action === "confirm-restart");
  r = await runner.run(VB.jobBridgeLaunch(st, { restart: true }));
  check("real: restart ok", r.ok && st.bridge.last.running, r.error);
  r = await runner.run(VB.jobBridgeStop(st));
  check("real: stop ok", r.ok && st.bridge.last.running === false, r.error);
  fs.rmSync(TMP, { recursive: true, force: true });
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
