const fs=require("fs"),{connect}=require("./cdp.js");
const PLACE=process.env.VB_PLACE||"bridgehollow__dyers_walk_local",TMP=(process.env.PAINT_TMP||require("os").tmpdir()+"/vb_paint_test").split(String.fromCharCode(92)).join("/");
const PV=TMP+"/out/panel/"+PLACE+"/heightmap_paint/preview";
const WK=TMP+"/out/panel/"+PLACE+"/heightmap_paint";
const rb=f=>{const b=fs.readFileSync(f);const a=new Float32Array(b.length/4);for(let i=0;i<a.length;i++)a[i]=b.readFloatLE(i*4);return a;};
const meta=()=>JSON.parse(fs.readFileSync(PV+"/preview.json","utf8"));
const snap=()=>({h:rb(PV+"/preview_h.bin"),d:rb(PV+"/preview_d.bin"),m:meta()});
function diff(a,b){let n=0,mx=0,sum=0;for(let i=0;i<a.length;i++){const e=b[i]-a[i];if(Math.abs(e)>1e-5){n++;mx=Math.max(mx,Math.abs(e));sum+=e;}}return {changed:n,maxAbs:+mx.toFixed(3),sum:+sum.toFixed(2)};}
function eq(a,b){for(let i=0;i<a.length;i++)if(a[i]!==b[i])return false;return true;}
async function setup(){const c=await connect();
 // navigate: Terrain tab -> expand the "Paint heightmap" section (click the real tab button and the summary), wait for the canvas to size and the preview to load
 await c.ev(`(function(){var b=document.querySelector('#tabs button[data-tab="terrain"]');b.click();var d=document.getElementById('hpDetails');if(!d.open)d.querySelector('summary').click();return d.open})()`);
 for(let i=0;i<100;i++){const ok=await c.ev(`(function(){var v=document.getElementById('hpCanvas');return v.clientWidth>0&&!/No heightmap/.test(document.getElementById('hpStatus').textContent)&&document.getElementById('hpOut').textContent.length>0})()`);if(ok)break;await c.sleep(200);}
 await c.waitIdle();
 await c.ev(`document.querySelector('[data-act="hp_fit"]').click()`);await c.sleep(400);
 await c.ev(`(function(){var e=document.querySelector('[data-s="hp.auto_apply"]');if(!e.checked){e.checked=true;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}})()`);
 // every scenario starts from the generated terrain (reset arms on the first click, confirms on the second)
 await c.ev(`document.querySelector('[data-act="hp_reset"]').click()`);await c.sleep(300);await c.ev(`document.querySelector('[data-act="hp_reset"]').click()`);await c.sleep(500);await c.waitIdle();await c.sleep(300);
 c.set=async(key,val)=>c.ev(`(function(){var e=document.querySelector('[data-s="${key}"]');if(e.type==='checkbox'){e.checked=${JSON.stringify(val)};}else e.value=${JSON.stringify(String(val))};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return e.value})()`);
 c.tool=async(id)=>{const p=await c.ev(`(function(){var e=document.querySelector('[data-hp-tool="${id}"]');e.scrollIntoView({block:'center',behavior:'instant'});var r=e.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);await c.sleep(250);const p2=await c.ev(`(function(){var r=document.querySelector('[data-hp-tool="${id}"]').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);await c.click(p2[0],p2[1]);await c.sleep(100);return c.ev(`document.querySelector('[data-s="hp.tool"]').value`);};
 c.btn=async(act)=>{await c.ev(`document.querySelector('[data-act="${act}"]').scrollIntoView({block:'center',behavior:'instant'})`);await c.sleep(300);const p=await c.ev(`(function(){var e=document.querySelector('[data-act="${act}"]');var r=e.getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);await c.click(p[0],p[1]);};
 c.view=async()=>{await c.sleep(500);const s=JSON.parse(fs.readFileSync(TMP+"/world/"+PLACE+"/panel_state.json","utf8"));return s.hp.view;};
 // feet -> canvas css px using saved view
 c.f2c=async(pts)=>{const v=await c.view(),m=meta(),r=await c.rect(),k=r.w/r.cw,s=m.cell_ft*m.factor;return pts.map(p=>[(p[0]/s*v.zoom+v.ox)*k,(p[1]/s*v.zoom+v.oy)*k]);};
 c.stroke=async(name,feet,o={})=>{await c.waitIdle();const before=snap(),h0=await c.hash();const pts=await c.f2c(feet);
   const dense=[];for(let i=0;i<pts.length-1;i++){for(let t=0;t<1;t+=0.1)dense.push([pts[i][0]+(pts[i+1][0]-pts[i][0])*t,pts[i][1]+(pts[i+1][1]-pts[i][1])*t]);}dense.push(pts[pts.length-1]);
   await c.drag(dense,o);await c.sleep(200);await c.waitIdle();await c.sleep(300);
   const after=snap(),h1=await c.hash();await c.shot(name);
   return {before,after,canvasChanged:h0!==h1,dh:diff(before.h,after.h),dd:{maxAbs:Math.max(...after.d.map(Math.abs))}};};
 c.settle=async()=>{let last=-1,stable=0;for(let i=0;i<150;i++){const n=(await c.ev(`window.__rpcLog().length`));const busy=await c.ev(`(document.getElementById('hpStatus').textContent+'|'+document.getElementById('status').textContent)`);if(n===last&&/\|idle$/.test(busy)&&!/\.\.\./.test(busy)){if(++stable>=5)return;}else stable=0;last=n;await c.sleep(200);}throw new Error('settle timeout');};
 return c;}
module.exports={setup,snap,diff,eq,meta,PV,WK,TMP,PLACE,rb};
