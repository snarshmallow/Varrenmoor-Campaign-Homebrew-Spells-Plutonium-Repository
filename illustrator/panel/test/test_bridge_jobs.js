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
  check("state defaults", st.bridge && st.bridge.node === "" && st.bridge.cim === false && st.bridge.last === null && st.bridge.hidden === false && st.bridge.terminal === "auto" && st.bridge.target === "http://10.0.0.15:3030" && st.bridge.mode === "attach");
  check("args: default is ATTACH to the Vega relay", VB.bridgeCtlArgs(st, "status").join(" ") === "foundry-bridge/bridgectl.mjs status --json --target http://10.0.0.15:3030");
  st.bridge.mode = "local";   // the older checks below are about the local relay (no attach address)
  st.bridge.env = "C:/t/e.env"; st.bridge.state = "C:/t/run"; st.bridge.cim = true; st.bridge.node = "C:/n/node.exe";
  check("args: env/state/node/cim only for start+restart", VB.bridgeCtlArgs(st, "start").join(" ") === "foundry-bridge/bridgectl.mjs start --json --env C:/t/e.env --state C:/t/run --node C:/n/node.exe --cim" && VB.bridgeCtlArgs(st, "info", ["--secrets"]).indexOf("--cim") < 0);
  check("launch plan: stopped -> start", VB.bridgeLaunchPlan({ running: false }).action === "start");
  const lp = VB.bridgeLaunchPlan({ running: true, managed: false, port: 3030, pid: 12 });
  check("launch plan: running -> ATTACH (no restart, no prompt)", lp.action === "attach" && /3030/.test(lp.reason) && /another way/.test(lp.reason), lp.reason);
  check("restart plan asks first; stop plan asks first", VB.bridgeRestartPlan({ running: true, managed: false, port: 3030 }).ask === true && VB.bridgeStopPlan({ running: true, managed: true, port: 3030 }).ask === true && /NOT started from here/.test(VB.bridgeStopPlan({ running: true, managed: false, port: 3030 }).text));
  check("remote relay cannot be restarted or stopped from here", VB.bridgeRestartPlan({ running: true, remote: true, host: "10.0.0.9", port: 3030 }).allowed === false && VB.bridgeStopPlan({ running: true, remote: true, host: "10.0.0.9", port: 3030 }).allowed === false);
  st.bridge.mode = "attach"; st.bridge.target = "10.0.0.9:3030"; st.bridge.hidden = true; st.bridge.terminal = "conhost";
  check("args: target on every command, hidden/terminal only on start+restart", VB.bridgeCtlArgs(st, "status").indexOf("--target") > 0 && VB.bridgeCtlArgs(st, "status").indexOf("--hidden") < 0 && VB.bridgeCtlArgs(st, "start").indexOf("--hidden") > 0 && VB.bridgeCtlArgs(st, "start").join(" ").indexOf("--terminal conhost") > 0);
  st.bridge.mode = "local"; st.bridge.target = ""; st.bridge.hidden = false; st.bridge.terminal = "auto";
  const l = (n) => new Array(n).fill("19:00:00 module socket closed 4002");
  check("4002 loop: 3 in last 20 lines", VB.bridgeLoop4002(["a", "b"].concat(l(3))) && !VB.bridgeLoop4002(l(2)) && !VB.bridgeLoop4002(l(3).concat(new Array(20).fill("x"))));
  // attach prefill + persistence (the address is a plain setting, not a secret)
  const fresh = VB.normalize(null);
  check("attach: prefilled with the Vega relay, attach is the default mode", VB.BRIDGE_ATTACH_DEFAULT === "http://10.0.0.15:3030" && fresh.bridge.target === "http://10.0.0.15:3030" && fresh.bridge.mode === "attach");
  const saved = VB.normalize(JSON.parse(JSON.stringify({ bridge: { target: "192.168.1.7:3030" } })));
  check("attach: an edited address survives save/load (normalize keeps it)", saved.bridge.target === "192.168.1.7:3030" && VB.bridgeCtlArgs(saved, "status").join(" ").indexOf("--target 192.168.1.7:3030") > 0);
  check("attach: a blank saved address falls back to the default", VB.bridgeAttachTarget({ bridge: { target: "  " } }) === "http://10.0.0.15:3030" && VB.bridgeAttachTarget({ bridge: { target: "", mode: "local" } }) === "");
  check("local/closelocal never carry --target (only this PC), even with a remote address saved", VB.bridgeCtlArgs(fresh, "local").indexOf("--target") < 0 && VB.bridgeCtlArgs(fresh, "closelocal").indexOf("--target") < 0 && VB.bridgeCtlArgs(fresh, "local").indexOf("local") === 1);
  const ls = VB.bridgeLocalState(fresh);
  check("launch local uses no attach address and does not change the saved one", ls.bridge.target === "" && VB.bridgeCtlArgs(ls, "start").indexOf("--target") < 0 && fresh.bridge.target === "http://10.0.0.15:3030");
  check("tokens are not part of saved bridge settings", Object.keys(VB.bridgeDefaults()).every(k => !/token|secret|api/i.test(k)));
  check("parse target", JSON.stringify(VB.bridgeParseTarget("http://10.0.0.15:3030")) === '{"host":"10.0.0.15","port":3030}' && VB.bridgeParseTarget("vega").port === null && VB.bridgeParseTarget("").host === "");
  // close plan + two-relays warning
  check("close plan: nothing running -> disabled 'No local bridge running'", VB.bridgeClosePlan(null).enabled === false && VB.bridgeClosePlan({ found: false }).label === "No local bridge running");
  const cp = VB.bridgeClosePlan({ found: true, pid: 4242, imageName: "node.exe", isNode: true, port: 8800, how: "managed, hidden (no window)" });
  check("close plan: node relay -> enabled, modal text names pid/port/how and says only this PC", cp.enabled && /4242/.test(cp.text) && /8800/.test(cp.text) && /hidden/.test(cp.text) && /THIS PC/.test(cp.text));
  check("close plan: non-node process is never closable", VB.bridgeClosePlan({ found: true, pid: 9, imageName: "notepad.exe", isNode: false, port: 3030, how: "" }).enabled === false);
  check("two relays: local + remote up warns; local-only / remote-only / attach-to-self do not", VB.bridgeTwoRelays(true, true, false) && !VB.bridgeTwoRelays(true, false, false) && !VB.bridgeTwoRelays(false, true, false) && !VB.bridgeTwoRelays(true, true, true));
  // client.json (where foundry_push.py gets its relay URL)
  const fakeFs = (files) => ({ readFileSync: (f) => { if (f in files) return files[f]; throw new Error("ENOENT"); } });
  let ci = await VB.bridgeClientInfo({ fs: fakeFs({ "R/foundry-bridge/client.json": JSON.stringify({ url: "http://127.0.0.1:3030", token: "x" }) }), env: {}, root: "R" });
  check("client.json on this PC is used first", ci.url === "http://127.0.0.1:3030" && ci.localFile === true);
  let asked = ""; ci = await VB.bridgeClientInfo({ fs: fakeFs({ "R/foundry-3d/.env": "FOUNDRY_ASSETS_DIR=\\\\HOST2\\share\\x\n" }), env: {}, root: "R", readShare: async (f) => { asked = f; return JSON.stringify({ url: "http://10.0.0.15:3030", token: "t" }); } });
  check("no local client.json -> the \\\\VEGA-style share (host from foundry-3d/.env), url only", ci.url === "http://10.0.0.15:3030" && asked === "\\\\HOST2\\C\\FoundryVTT resources\\bridge\\client.json" && JSON.stringify(ci).indexOf('"t"') < 0, asked);
  ci = await VB.bridgeClientInfo({ fs: fakeFs({}), env: {}, root: "R", readShare: async () => null });
  check("nothing found is reported plainly", ci.url === "" && /VEGA/.test(ci.source));
  check("client check: same relay ok; loopback vs Vega warns with a fix; other host warns", VB.bridgeClientCheck("http://10.0.0.15:3030", "10.0.0.15:3030").ok && !VB.bridgeClientCheck("http://127.0.0.1:3030", "http://10.0.0.15:3030").ok && /old client\.json/.test(VB.bridgeClientCheck("http://127.0.0.1:3030", "http://10.0.0.15:3030").text) && !VB.bridgeClientCheck("http://10.0.0.99:3030", "http://10.0.0.15:3030").ok);
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
  st.bridge.env = tmp + "/e.env"; st.bridge.state = tmp + "/run"; st.bridge.node = ""; st.bridge.cim = false; st.bridge.hidden = true;   // hidden: no window pops up during the test
  r = await runner.run(VB.jobBridgeStatus(st));
  check("real: status says stopped", r.ok && st.bridge.last.running === false, r.error);
  r = await runner.run(VB.jobBridgeLaunch(st));
  check("real: launch starts a managed relay", r.ok && st.bridge.last.running && st.bridge.last.managed && st.bridge.last.port === port, r.error);
  check("real: info carries tokens in memory and urls", VB.bridgeMem.secrets.moduleToken === MOD && /ws:\/\/127\.0\.0\.1:/.test(VB.bridgeMem.info.urls.localhost));
  r = await runner.run(VB.jobBridgeStatus(st));
  check("real: plan now attaches", VB.bridgeLaunchPlan(VB.bridgeMem.info.status).action === "attach" && /managed/.test(VB.bridgeMem.info.status.mode), VB.bridgeMem.info.status.mode);
  const pid0 = VB.bridgeMem.info.status.pid;
  r = await runner.run(VB.jobBridgeLaunch(st));
  check("real: Connect-or-launch on a running relay attaches (same pid, nothing restarted)", r.ok && st.bridge.last.pid === pid0);
  r = await runner.run(VB.jobBridgeProbe(st));
  check("real: probe finds the relay", r.ok && VB.bridgeMem.found.some(x => x.running && x.port === port), r.error);

  // local relay detection and Close bridge (throwaway relay only)
  const realLocal = await VB.bridgeLocalDetect(st);
  check("local detect: finds the relay on this PC with pid, node.exe and how it was started", realLocal.found && realLocal.port === port && realLocal.pid === VB.bridgeMem.info.status.pid && realLocal.isNode && /^node(\.exe)?$/i.test(realLocal.imageName) && realLocal.managed && /hidden/.test(realLocal.how), JSON.stringify(realLocal));
  const keepT = st.bridge.target, keepM = st.bridge.mode; st.bridge.mode = "attach"; st.bridge.target = "10.255.255.1:3030";
  const l2 = await VB.bridgeLocalDetect(st); st.bridge.mode = keepM; st.bridge.target = keepT;
  check("local detect ignores the attach address", l2.found && l2.port === port);
  // pairing admin through the panel logic: API token from .env (memory), then a typed token
  const post = (p, body, tok) => VB.bridgeHttp({ method: "POST", host: "127.0.0.1", port: port, path: p, body: body, token: tok });
  const rq = await post("/pair/request", { deviceName: "Vega GM", userName: "Trent", worldId: "w", hostOrigin: "http://vega:30000" });
  check("pair: device request accepted", rq.status === 200 && /^\d{3} \d{3}$/.test(rq.body.code));
  let pl = await VB.bridgePairRefresh();
  check("pair: panel lists the pending request with the same code", pl.pending.length === 1 && pl.pending[0].code === rq.body.code.replace(" ", "") && pl.pending[0].name === "Vega GM");
  await VB.bridgePairApprove(pl.pending[0].id, 30);
  const got = await post("/pair/poll", { requestId: rq.body.requestId, pollSecret: rq.body.pollSecret });
  check("pair: approved, device receives its token once", got.body.state === "approved" && !!got.body.token);
  pl = await VB.bridgePairRefresh();
  check("pair: device listed, no token in the list or the panel state", pl.devices.length === 1 && JSON.stringify(pl).indexOf(got.body.token) < 0 && JSON.stringify(st).indexOf(got.body.token) < 0);
  await VB.bridgePairRotate(pl.devices[0].id); pl = await VB.bridgePairRefresh();
  check("pair: rotate flags the device", pl.devices[0].rotationPending === true);
  await VB.bridgePairRevoke(pl.devices[0].id); pl = await VB.bridgePairRefresh();
  check("pair: revoke removes it", pl.devices.length === 0);
  const rq2 = await post("/pair/request", { deviceName: "Spoof" });
  await VB.bridgePairDeny((await VB.bridgePairRefresh()).pending[0].id);
  check("pair: deny works", (await post("/pair/poll", { requestId: rq2.body.requestId, pollSecret: rq2.body.pollSecret })).body.state === "denied");
  const keep = VB.bridgeMem.secrets; VB.bridgeMem.secrets = null; VB.bridgeMem.manual = { api: "wrong-token-xxxxxxxxxxxxxxxxxxxxx", module: "" };
  let bad = ""; try { await VB.bridgePairRefresh(); } catch (e) { bad = e.message; }
  check("pair: a wrong typed token is rejected with a plain message", /rejected the API token/.test(bad), bad);
  VB.bridgeMem.manual = { api: API, module: "" };
  check("pair: a typed token works when .env is not available", (await VB.bridgePairRefresh()).pending.length === 0);
  VB.bridgeMem.secrets = keep; VB.bridgeMem.manual = { api: "", module: "" };
  check("tokens never in panel state or logs after pairing", JSON.stringify(st.bridge).indexOf(API) < 0 && logs.join("\n").indexOf(API) < 0);
  r = await runner.run(VB.jobBridgeLaunch(st, { restart: true }));
  check("real: restart ok", r.ok && st.bridge.last.running, r.error);
  st.bridge.mode = "attach"; st.bridge.target = "10.255.255.1:3030";   // a remote address is saved: Close bridge must still only act locally
  r = await runner.run(VB.jobBridgeClose(st));
  st.bridge.mode = "local"; st.bridge.target = "";
  check("close job: stops the local relay (remote address ignored)", r.ok && (await VB.bridgeLocalDetect(st)).found === false && st.bridge.last === st.bridge.last, r.error);
  r = await runner.run(VB.jobBridgeStop(st));
  check("real: stop ok", r.ok && st.bridge.last.running === false, r.error);
  fs.rmSync(TMP, { recursive: true, force: true });
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
