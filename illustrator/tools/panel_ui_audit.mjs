// Panel layout audit over the CEP remote-debug port (same as panel_debug.mjs, port 8088). Emulates panel sizes, visits every tab and reports problems:
// page-level horizontal scroll, controls poking out of the panel, clipped text, overlapping controls, tiny inputs, tiny fonts, sliders that are not full width.
//   node tools/panel_ui_audit.mjs [--widths 300,340,440,700,1000] [--height 720] [--shots out/panel_ui] [--tabs a,b] [--json file]
//   node tools/panel_ui_audit.mjs --real         really resize the docked/floating panel instead of emulating (clamped to the manifest sizes; restores 440x720)
//   node tools/panel_ui_audit.mjs --reload        reload the panel first (picks up edited HTML/JS)
// Screenshots: one PNG per tab per width when --shots is given (Page.captureScreenshot of the emulated viewport). Nothing in Illustrator is touched.
import fs from "node:fs";
import path from "node:path";
const PORT = process.env.PANEL_PORT || 8088;
const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const widths = arg("--widths", "300,340,440,700,1000").split(",").map(Number);
const height = +arg("--height", 720);
const shots = arg("--shots", "");
const real = process.argv.includes("--real");   // really resize the panel window (__adobe_cep__.resizeContent); clamped by manifest MinSize/MaxSize; restores 440x720
const onlyTabs = (arg("--tabs", "") || "").split(",").filter(Boolean);
const targets = await (await fetch(`http://localhost:${PORT}/json`)).json();
const t = targets.find(x => /index\.html/.test(x.url)) || targets[0];
const ws = new WebSocket(t.webSocketDebuggerUrl);
let id = 0; const pend = new Map();
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
ws.onmessage = ev => { const m = JSON.parse(ev.data); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); } };
await new Promise(r => ws.onopen = r);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ev = async expr => { const r = await send("Runtime.evaluate", { expression: expr, awaitPromise: true, returnByValue: true }); if (r.result?.exceptionDetails) throw new Error(JSON.stringify(r.result.exceptionDetails.exception?.description)); return r.result?.result?.value; };
if (process.argv.includes("--reload")) { await send("Page.reload", { ignoreCache: true }); await sleep(2500); }

const AUDIT = `(function(){
  var out = [], main = document.querySelector("main"), vw = document.documentElement.clientWidth;
  var vis = function(e){ var r = e.getBoundingClientRect(); var cs = getComputedStyle(e); return r.width > 0 && r.height > 0 && cs.visibility !== "hidden" && cs.display !== "none"; };
  var name = function(e){ return e.tagName.toLowerCase() + (e.id ? "#" + e.id : "") + (e.getAttribute("data-act") ? "[" + e.getAttribute("data-act") + "]" : "") + (e.getAttribute("data-s") ? "[" + e.getAttribute("data-s") + "]" : "") + ((e.textContent||"").trim() ? " '" + e.textContent.trim().slice(0,28) + "'" : (e.id || e.getAttribute("data-s") || e.getAttribute("data-act") ? "" : " " + e.outerHTML.slice(0, 90))); };
  var sec = document.querySelector("section.on"); if (!sec) return {problems:["no active tab"]};
  if (document.documentElement.scrollWidth > vw + 1) out.push("PAGE scrolls horizontally: scrollWidth " + document.documentElement.scrollWidth + " > " + vw);
  if (main.scrollWidth > main.clientWidth + 1) out.push("MAIN scrolls horizontally: " + main.scrollWidth + " > " + main.clientWidth);
  var mr = main.getBoundingClientRect();
  // find an ancestor (below main) that scrolls/clips horizontally
  var clipper = function(e){ for (var p = e.parentElement; p && p !== main; p = p.parentElement) { var o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") return p; } return null; };
  var leaf = [].slice.call(sec.querySelectorAll("button,input,select,textarea,label,img,table,canvas,svg,ul.list,.sl,.note,code,span.tag")).filter(vis);
  leaf.forEach(function(e){
    var r = e.getBoundingClientRect();
    if (r.right > mr.right + 1 && !clipper(e)) out.push("pokes out right by " + Math.round(r.right - mr.right) + "px: " + name(e));
    if (r.left < mr.left - 1) out.push("pokes out left: " + name(e));
    var cs = getComputedStyle(e);
    if ((cs.overflowX === "hidden" || cs.textOverflow === "ellipsis") && e.scrollWidth > e.clientWidth + 1 && /^(BUTTON|LABEL|SPAN|SELECT)$/.test(e.tagName)) out.push("text clipped (" + e.scrollWidth + ">" + e.clientWidth + "): " + name(e));
    if (e.tagName === "BUTTON" && e.scrollWidth > e.clientWidth + 1) out.push("button text overflows its box: " + name(e));
    if (/^(INPUT|SELECT)$/.test(e.tagName) && e.type !== "checkbox" && e.type !== "radio" && e.type !== "color" && r.width < 44) out.push("tiny control " + Math.round(r.width) + "px: " + name(e));
    if (e.type === "range" && r.width < 80) out.push("slider only " + Math.round(r.width) + "px wide: " + name(e));
    var fs = parseFloat(cs.fontSize); if (fs < 9.5 && (e.textContent||"").trim() && e.children.length === 0) out.push("font " + fs + "px: " + name(e));
  });
  // overlapping interactive controls
  var ctl = leaf.filter(function(e){ return /^(BUTTON|INPUT|SELECT|TEXTAREA)$/.test(e.tagName) && e.type !== "hidden"; });
  for (var i = 0; i < ctl.length; i++) for (var j = i + 1; j < ctl.length; j++) {
    var a = ctl[i].getBoundingClientRect(), b = ctl[j].getBoundingClientRect();
    var ox = Math.min(a.right, b.right) - Math.max(a.left, b.left), oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
    if (ox > 3 && oy > 3 && !ctl[i].contains(ctl[j]) && !ctl[j].contains(ctl[i])) { out.push("controls overlap: " + name(ctl[i]) + " / " + name(ctl[j])); if (out.length > 40) break; }
  }
  // tables: should scroll inside their own box, never widen the page
  [].slice.call(sec.querySelectorAll("table")).filter(vis).forEach(function(tb){ var r = tb.getBoundingClientRect(); if (r.right > mr.right + 1) out.push("table wider than panel: " + name(tb)); });
  // nav tabs
  var nav = document.querySelector("nav"); if (nav.scrollWidth > nav.clientWidth + 1) out.push("NAV overflows horizontally");
  // top bar
  var top = document.querySelector("#top .row"); if (top.scrollWidth > top.clientWidth + 1) out.push("TOP row clipped: " + top.scrollWidth + ">" + top.clientWidth);
  var seen = {}; out = out.filter(function(s){ if (seen[s]) return false; seen[s] = 1; return true; });
  return { problems: out.slice(0, 60), mainH: main.clientHeight, contentH: main.scrollHeight };
})()`;

const tabs = await ev(`[].map.call(document.querySelectorAll("#tabs button"), b => b.getAttribute("data-tab"))`);
const report = {};
if (shots) fs.mkdirSync(shots, { recursive: true });
for (const w of widths) {
  if (real) { await ev(`__adobe_cep__.resizeContent(${w}, ${height}); 0`); await sleep(1500); const got = await ev("innerWidth + 'x' + innerHeight"); if (+got.split("x")[0] !== w) console.log(`(asked ${w}px, panel is ${got}: manifest Min/MaxSize clamps it)`); }
  else { await send("Emulation.setDeviceMetricsOverride", { width: w, height, deviceScaleFactor: 1, mobile: false }); await sleep(250); }
  for (const tab of tabs) {
    if (onlyTabs.length && !onlyTabs.includes(tab)) continue;
    await ev(`document.querySelector('#tabs button[data-tab="${tab}"]').click()`);
    await sleep(150);
    const r = await ev(AUDIT);
    (report[w] ||= {})[tab] = r.problems;
    if (shots) {
      const s = await send("Page.captureScreenshot", { format: "png" });
      fs.writeFileSync(path.join(shots, `${tab}_${w}.png`), Buffer.from(s.result.data, "base64"));
    }
  }
}
if (real) { await ev("__adobe_cep__.resizeContent(440, 720); 0"); } else await send("Emulation.clearDeviceMetricsOverride");
await ev(`document.querySelector('#tabs button[data-tab="${tabs[0]}"]').click()`);
let n = 0;
for (const w of widths) for (const [tab, ps] of Object.entries(report[w] || {})) { if (ps.length) { n += ps.length; console.log(`--- ${w}px  ${tab} (${ps.length})`); ps.slice(0, +arg("--max", 8)).forEach(p => console.log("   " + p)); } }
console.log(n ? `${n} findings` : "no findings");
if (arg("--json", "")) { fs.mkdirSync(path.dirname(arg("--json")), { recursive: true }); fs.writeFileSync(arg("--json"), JSON.stringify(report, null, 1)); }
process.exit(0);
