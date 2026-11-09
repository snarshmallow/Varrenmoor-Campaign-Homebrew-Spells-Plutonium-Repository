const L=require("./lib.js");
(async()=>{const c=await L.setup();
 const rec=(n,ok,x)=>console.log(ok?"PASS":"FAIL",n,x||"");
 await c.ev("document.activeElement&&document.activeElement.blur()");
 await c.tool("raise");await c.set("hp.rate_ft",2);await c.set("hp.hardness",0.2);
 const path=[[150,120],[190,120]];
 const t=async(name,set)=>{for(const k in set)await c.set("hp."+k,set[k]);const r=await c.stroke(name,path);
   await c.ev("document.activeElement&&document.activeElement.blur()");await c.key("z","KeyZ",{mods:["ctrl"],vk:90});await c.sleep(300);await c.waitIdle();await c.sleep(200);
   const back=L.diff(r.before.h,L.snap().h);rec(name+" undo exact",back.changed===0,JSON.stringify(back));return r;};
 const base={radius_ft:20,strength:0.3,falloff:"smooth"};
 const lo=await t("30_strength_0.3",base);
 const hi=await t("31_strength_1.0",{strength:1});
 rec("higher strength raises more",hi.dh.maxAbs>lo.dh.maxAbs*2,lo.dh.maxAbs+" vs "+hi.dh.maxAbs);
 const sm=await t("32_radius_10",{strength:0.5,radius_ft:10});
 const bg=await t("33_radius_40",{radius_ft:40});
 rec("bigger radius changes more cells",bg.dh.changed>sm.dh.changed*3,sm.dh.changed+" vs "+bg.dh.changed);
 const sh=await t("34_falloff_smooth",{radius_ft:25,falloff:"smooth",hardness:0});
 const co=await t("35_falloff_constant",{falloff:"constant"});
 const sp=await t("36_falloff_sharp",{falloff:"sharp"});
 rec("constant falloff has more mass than smooth, sharp less",co.dh.sum>sh.dh.sum&&sp.dh.sum<sh.dh.sum,[sh.dh.sum,co.dh.sum,sp.dh.sum].join(" "));
 await c.set("hp.hardness",0.2);
 // stroke while zoomed+panned: wheel zoom in then paint at a known feet pos; check the edit lands there
 await c.btn("hp_fit");await c.wheel(500,300,-120);await c.wheel(500,300,-120);await c.wheel(500,300,-120);await c.sleep(600);
 await c.set("hp.radius_ft",15);await c.set("hp.falloff","smooth");
 const vv=await c.view(),r=await c.rect(),k=r.cw/r.w,m=L.meta(),s=2.5;
 const target=[[ (500*k-vv.ox)/vv.zoom*s, (300*k-vv.oy)/vv.zoom*s ]]; // feet under cursor point
 const before=L.snap();
 await c.drag([[500,300],[520,300],[540,300]]);await c.sleep(300);await c.waitIdle();await c.sleep(300);
 const af=L.snap();const d=L.diff(before.h,af.h);
 // centroid of change
 let sx=0,sy=0,sw=0;for(let i=0;i<af.h.length;i++){const e=af.h[i]-before.h[i];if(Math.abs(e)>1e-5){sx+=(i%m.pw)*s*e;sy+=Math.floor(i/m.pw)*s*e;sw+=e;}}
 const cen=[sx/sw,sy/sw],exp=[(520*k-vv.ox)/vv.zoom*s,(300*k-vv.oy)/vv.zoom*s];
 rec("zoomed stroke lands where drawn (centroid vs expected feet)",Math.hypot(cen[0]-exp[0],cen[1]-exp[1])<4,JSON.stringify([cen.map(Math.round),exp.map(Math.round)]));
 await c.shot("37_zoomed_stroke");
 c.close();})().catch(e=>{console.error(e);process.exit(1)});
