// Paint heightmap lives in the Terrain tab: collapsed -> open sizing, shortcut gating (closed section / other tab), tab button gone.
const L=require("./lib.js");
(async()=>{const c=await L.setup();const rec=(n,ok,x)=>console.log(ok?"PASS":"FAIL",n,x||"");
 rec("no Paint tab button",await c.ev(`!document.querySelector('#tabs button[data-tab="hpaint"]')`));
 const n=async()=>+(await c.state()).out.match(/layer: (\d+)/)[1];
 await c.tool("raise");await c.set("hp.radius_ft",30);await c.set("hp.strength",0.6);await c.stroke("50_layout_stroke",[[100,150],[220,160]]);
 const n1=await n();rec("one stroke drawn",n1>=1,n1);
 await c.ev("document.activeElement&&document.activeElement.blur()");
 // collapse the section: Ctrl+Z must not undo
 await c.ev(`document.getElementById('hpDetails').open=false`);await c.sleep(300);
 await c.key("z","KeyZ",{mods:["ctrl"],vk:90});await c.sleep(1500);rec("Ctrl+Z ignored while section is collapsed",(await c.ev(`document.querySelector('#hpOut').textContent`)).match(/layer: (\d+)/)[1]==String(n1));
 // switch to another tab with the section open
 await c.ev(`document.getElementById('hpDetails').open=true`);await c.sleep(300);
 await c.ev(`document.querySelector('#tabs button[data-tab="contours"]').click()`);await c.sleep(300);
 await c.key("z","KeyZ",{mods:["ctrl"],vk:90});await c.sleep(1500);
 await c.ev(`document.querySelector('#tabs button[data-tab="terrain"]').click()`);await c.sleep(800);
 rec("Ctrl+Z ignored on another tab",await n()===n1,await n());
 // reload with the section collapsed, then open it: canvas must size to the panel width and show the terrain
 await c.send("Page.reload");await c.sleep(6000);
 await c.ev(`document.querySelector('#tabs button[data-tab="terrain"]').click()`);await c.sleep(500);
 rec("section collapsed by default",await c.ev(`!document.getElementById('hpDetails').open`));
 await c.ev(`document.querySelector('#hpDetails summary').click()`);
 for(let i=0;i<60&&!(await c.ev(`/Strokes in the edit layer/.test(document.getElementById('hpOut').textContent)`));i++)await c.sleep(250);
 await c.sleep(600);const dims=await c.ev(`(function(){var v=document.getElementById('hpCanvas');return {w:v.width,cw:v.parentNode.clientWidth,h:v.height}})()`);
 rec("canvas sized to the section width when opened",Math.abs(dims.w-(dims.cw-2))<=2&&dims.w>300,JSON.stringify(dims));
 rec("preview loads on first open",await c.ev(`!/No heightmap loaded/.test(document.getElementById('hpStatus').textContent)`));
 const nz=await c.ev(`(function(){var v=document.getElementById('hpCanvas'),d=v.getContext('2d').getImageData(0,0,v.width,v.height).data,k=0;for(var i=0;i<d.length;i+=40){if(d[i]!==32||d[i+1]!==32)k++}return k})()`);rec("canvas shows relief (not blank)",nz>500,nz);
 await c.shot("51_opened_after_reload");
 c.close();})().catch(e=>{console.error(e);process.exit(1)});
