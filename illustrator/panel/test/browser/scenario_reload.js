// Reload / version button: version text, cache-busted scripts, stale badge after a panel file changes, refusal during a drag, hard reload that restores tab / Paint section / scroll and reports "reloaded to <version>".
// Touches the mtime of lib/townarea.js (restored at the end); needs run_all-style setup (server.js + Edge on :9333).
const fs=require("fs"),cp=require("child_process"),{connect}=require("./cdp.js");
const REPO=(process.env.VB_REPO||"D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository");
const F=REPO+"/illustrator/panel/lib/townarea.js";
(async()=>{const c=await connect();const rec=(n,ok,x)=>console.log(ok?"PASS":"FAIL",n,x===undefined?"":x);
 const head=cp.execSync("git rev-parse --short HEAD",{cwd:REPO}).toString().trim();
 for(let i=0;i<50&&!(await c.ev(`!!window.VBVersionUI&&document.getElementById('status').textContent==='idle'`));i++)await c.sleep(200);
 const t0=await c.ev(`document.getElementById('verText').textContent`);
 rec("version text shows git hash and load time",new RegExp("^(reloaded to )?v "+head+" [0-9][0-9]:[0-9][0-9]$").test(t0),t0);
 rec("every script tag carries ?v=",await c.ev("Array.prototype.every.call(document.querySelectorAll('script[src]'),function(s){var u=s.getAttribute('src');return u.indexOf('__stub')>=0||u.indexOf('?v=')>0})"));
 rec("no stale badge at start",await c.ev(`document.getElementById('verDot').hidden`));
 // state to be restored: Terrain tab, Paint section open, scrolled
 await c.ev(`(function(){document.querySelector('#tabs button[data-tab="terrain"]').click();var d=document.getElementById('hpDetails');d.open=true;d.dispatchEvent(new Event('toggle'));})()`);await c.sleep(1500);
 await c.ev(`document.querySelector('main').scrollTop=300`);await c.sleep(300);
 const sc0=await c.ev(`document.querySelector('main').scrollTop`);
 // refusal while the mouse is down elsewhere
 await c.ev(`document.body.dispatchEvent(new MouseEvent('mousedown',{bubbles:true}))`);
 await c.ev(`document.getElementById('reloadPanel').click()`);
 rec("refused during a drag",/Reload refused: a drag/.test(await c.ev(`document.getElementById('err').textContent`)));
 await c.ev(`document.body.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}))`);
 await c.ev(`document.getElementById('err').textContent=''`);
 // newer file on disk -> badge
 const st=fs.statSync(F);fs.utimesSync(F,new Date(),new Date(Date.now()+60000));
 try{
 for(let i=0;i<30&&await c.ev(`document.getElementById('verDot').hidden`);i++)await c.sleep(1000);
 rec("badge appears when a panel file is newer",!(await c.ev(`document.getElementById('verDot').hidden`)));
 rec("tooltip says update available",/Update available: click to reload/.test(await c.ev(`document.getElementById('reloadPanel').title`)));
 // real click on the button (pointer events) -> reload
 const p=await c.ev(`(function(){var r=document.getElementById('reloadPanel').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);
 await c.click(p[0],p[1]);
 await c.sleep(3500);
 for(let i=0;i<60&&!(await c.ev(`!!window.VBVersionUI&&document.getElementById('status').textContent==='idle'&&/reloaded to/.test(document.getElementById('log').textContent)`).catch(()=>false));i++)await c.sleep(300);
 rec("log says reloaded to <version>",/reloaded to v /.test(await c.ev(`document.getElementById('log').textContent`)));
 rec("badge cleared after reload",await c.ev(`document.getElementById('verDot').hidden`));
 rec("Terrain tab restored",await c.ev(`document.querySelector('#tabs button[aria-selected="true"]').getAttribute('data-tab')`)==="terrain");
 rec("Paint section restored open",await c.ev(`document.getElementById('hpDetails').open`));
 await c.sleep(800);
 const sc1=await c.ev(`document.querySelector('main').scrollTop`);
 rec("scroll position restored",Math.abs(sc1-sc0)<=2&&sc0>0,sc0+" -> "+sc1);
 }finally{fs.utimesSync(F,st.atime,st.mtime);}
 process.exit(0);})().catch(e=>{console.log("FAIL exception",e.message);process.exit(1);});
