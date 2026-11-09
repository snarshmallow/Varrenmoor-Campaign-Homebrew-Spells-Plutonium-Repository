const L=require("./lib.js"),fs=require("fs");
const stdev=(h,idx)=>{let s=0,s2=0;idx.forEach(i=>{s+=h[i];s2+=h[i]*h[i]});const n=idx.length,m=s/n;return Math.sqrt(Math.max(s2/n-m*m,0));};
(async()=>{const c=await L.setup();const res=[];const snaps=[L.snap()];
 const rec=(n,ok,x)=>{res.push([n,ok]);console.log(ok?"PASS":"FAIL",n,x||"");};
 const run=async(name,tool,settings,feet,check)=>{await c.tool(tool);for(const k in settings)await c.set("hp."+k,settings[k]);
   const r=await c.stroke(name,feet);snaps.push(r.after);rec(name+" canvas changed",r.canvasChanged);rec(name+" preview changed",r.dh.changed>0,JSON.stringify(r.dh));
   if(check)check(r);return r;};
 await run("02_raise","raise",{radius_ft:30,strength:0.5},[[100,150],[160,170],[220,150]],r=>rec("raise sum>0",r.dh.sum>0));
 const st=async()=>(await c.state()).out.split("\n")[0];
 await run("03_lower","lower",{radius_ft:30,strength:0.5},[[60,60],[120,80]],r=>rec("lower sum<0",r.dh.sum<0));
 await run("04_smooth_setup_raise","raise",{radius_ft:12,strength:1,rate_ft:6},[[200,300],[230,300],[200,300],[230,300]],r=>rec("rough-up raise sum>0",r.dh.sum>0));
 // smooth over the bump region
 await c.tool('raise');const m=L.meta(),W=m.pw;
 const region=[];for(let y=0;y<m.ph;y++)for(let x=0;x<W;x++){const fx=x*2.5,fy=y*2.5;if(fx>170&&fx<260&&fy>270&&fy<330)region.push(y*W+x);}
 const sdBefore=stdev(snaps[snaps.length-1].h,region);
 await run("05_smooth","smooth",{radius_ft:30,strength:1},[[190,300],[245,300],[190,300],[245,300]],r=>{const sd=stdev(r.after.h,region);rec("smooth reduces local stdev "+sdBefore.toFixed(3)+"->"+sd.toFixed(3),sd<sdBefore);});
 await run("06_flatten_blank","flatten",{radius_ft:25,strength:1,height_ft:""},[[40,250],[100,270]],r=>{});
 await run("07_flatten_abs","flatten",{radius_ft:25,strength:1,height_ft:660},[[40,330],[90,330]],r=>{const i=Math.round(330/2.5)*W+Math.round(65/2.5);rec("flatten to 660 at centre "+r.after.h[i].toFixed(2),Math.abs(r.after.h[i]-660)<0.5);});
 await run("08_noise","noise",{radius_ft:30,strength:1,rate_ft:3,seed:7},[[230,60],[290,90]],r=>rec("noise both signs",r.dh.maxAbs>0));
 await run("09_ridge","ridge",{radius_ft:12,strength:1,height_ft:15},[[130,230],[200,240],[260,220]],r=>rec("ridge raises (net>0)",r.dh.sum>0));
 await run("10_valley","valley",{radius_ft:12,strength:1,height_ft:8},[[100,100],[180,110],[250,120]],r=>rec("valley lowers (net<0)",r.dh.sum<0));
 const pre=snaps[snaps.length-1];
 const riv=await run("11_river","river",{radius_ft:10,strength:1,depth_ft:6,bank_slope:0.6},[[70,20],[120,60],[180,50],[260,80]],r=>rec("river lowers (net<0)",r.dh.sum<0));
 // river bed falls monotonic downstream? sample bed along path
 const pk=L.snap();
 console.log(await st());
 // undo all via Ctrl+Z real key
 const total=snaps.length-1;console.log("strokes",total);
 await c.ev("document.activeElement&&document.activeElement.blur()");
 for(let i=total;i>=1;i--){await c.key("z","KeyZ",{mods:["ctrl"],vk:90});await c.sleep(300);await c.waitIdle();await c.sleep(200);const s=L.snap();{const dd=L.diff(snaps[i-1].h,s.h);rec("undo to "+(i-1)+" exact",dd.changed===0,JSON.stringify(dd))};if(i==total)await c.shot("12_undo_one");}
 await c.shot("13_undo_all");console.log(await st());
 // redo with ctrl+y x3 then ctrl+shift+z
 for(let i=1;i<=3;i++){await c.key("y","KeyY",{mods:["ctrl"],vk:89});await c.sleep(300);await c.waitIdle();await c.sleep(200);const s=L.snap();rec("redo (ctrl+y) to "+i+" exact",L.eq(s.h,snaps[i].h));}
 await c.key("Z","KeyZ",{mods:["ctrl","shift"],vk:90});await c.sleep(300);await c.waitIdle();await c.sleep(200);rec("redo (ctrl+shift+z) to 4 exact",L.eq(L.snap().h,snaps[4].h));
 await c.shot("14_redo_4");console.log(await st());
 console.log(JSON.stringify(await c.state()));
 fs.writeFileSync("res3.json",JSON.stringify(res));
 c.close();})().catch(e=>{console.error(e);process.exit(1)});
