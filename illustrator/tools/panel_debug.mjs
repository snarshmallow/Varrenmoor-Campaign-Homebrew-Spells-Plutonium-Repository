// Debug the Varrenmoor Bridge panel over the CEP remote-debug port (panel/.debug, port 8088). No user interaction needed once the panel is open.
//   node tools/panel_debug.mjs targets
//   node tools/panel_debug.mjs eval "document.title"                   run JS inside the panel (has require/CSInterface)
//   node tools/panel_debug.mjs jsx  "app.documents.length"           run ExtendScript in Illustrator via the panel
//   node tools/panel_debug.mjs console [seconds]                     stream console output / exceptions
//   node tools/panel_debug.mjs log                                   print the panel's on-screen log lines (#log)
const PORT = process.env.PANEL_PORT || 8088;
const [cmd, ...rest] = process.argv.slice(2);
const targets = await (await fetch(`http://localhost:${PORT}/json`)).json();
if (cmd === "targets" || !cmd) { console.log(targets.map(t => `${t.title}  ${t.url}`).join("\n")); process.exit(0); }
const t = targets.find(x => /index\.html/.test(x.url)) || targets[0];
if (!t) { console.error("no panel target (open the panel; panel/.debug must be loaded)"); process.exit(2); }
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pend = new Map();
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
ws.onmessage = ev => {
  const m = JSON.parse(ev.data);
  if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); return; }
  if (m.method === "Runtime.consoleAPICalled") console.log(`[${m.params.type}]`, m.params.args.map(a => a.value ?? a.description ?? "").join(" "));
  if (m.method === "Runtime.exceptionThrown") console.log("[exception]", m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
};
await new Promise(r => ws.onopen = r);
const ev = async expr => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); const v = r.result?.result; console.log(r.result?.exceptionDetails ? "ERR " + JSON.stringify(r.result.exceptionDetails.exception?.description) : (typeof v?.value === "string" ? v.value : JSON.stringify(v?.value))); };
if (cmd === "eval") { await ev(rest.join(" ")); process.exit(0); }
if (cmd === "jsx") { await ev(`new Promise(r=>new CSInterface().evalScript(${JSON.stringify(rest.join(" "))}, r))`); process.exit(0); }
if (cmd === "log") { await ev(`(document.querySelector('#log')||document.body).innerText.slice(-4000)`); process.exit(0); }
if (cmd === "console") { await send("Runtime.enable"); await new Promise(r => setTimeout(r, (+rest[0] || 10) * 1000)); process.exit(0); }
console.error("unknown command"); process.exit(1);
