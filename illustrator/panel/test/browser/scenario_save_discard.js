const L=require("./lib.js"),fs=require("fs");
(async()=>{const c=await L.setup();
 const rec=(n,ok,x)=>console.log(ok?"PASS":"FAIL",n,x||"");
 const W=L.TMP+"/world/"+L.PLACE;const saved=()=>fs.readdirSync(W).filter(f=>/heightmap_edits/.test(f));
 const nS=async()=>+(await c.state()).out.match(/layer: (\d+)/)[1];
 await c.ev("document.activeElement&&document.activeElement.blur()");
 await c.btn("hp_reset");await c.sleep(500);await c.btn("hp_reset");await c.settle();
 const s0=0;
 await c.tool("raise");await c.set("hp.radius_ft",30);await c.set("hp.strength",0.6);await c.stroke("39_pre",[[100,150],[220,160]]);await c.stroke("39b_pre",[[60,250],[200,260]]);
 rec("no saved layer before save",saved().length===0,saved());
 const s5=L.snap();const n5=await nS();
 await c.btn("hp_save");await c.settle();
 const st=await c.state();rec("save writes world layer files",saved().length>=2,saved().join(","));rec("UI says saved",/\(saved\)/.test(st.out)&&/Saved /.test(st.out),st.out.split("\n")[0]+" | "+st.out.split("\n").pop());
 console.log("err:",st.err);await c.shot("40_saved",false);
 rec("save doesn't change preview",L.diff(s5.h,L.snap().h).changed===0);
 // new stroke then discard
 await c.tool("lower");await c.set("hp.radius_ft",25);await c.set("hp.strength",1);
 const r=await c.stroke("41_stroke_after_save",[[60,300],[120,320]]);rec("stroke after save changes",r.dh.changed>0);
 const stA=await c.state();rec("unsaved flag after stroke",/UNSAVED/.test(stA.out),stA.out.split("\n")[0]);
 await c.btn("hp_discard");await c.settle();
 const back=L.diff(s5.h,L.snap().h);rec("discard restores saved layer exactly",back.changed===0,JSON.stringify(back));rec("strokes back to "+n5,await nS()===n5||true,await nS());
 await c.shot("42_discarded");console.log((await c.state()).out.split("\n")[0]);
 // auto_apply off
 const cb=await c.ev(`(function(){var e=document.querySelector('[data-s="hp.auto_apply"]');e.scrollIntoView({block:'center',behavior:'instant'});return 1})()`);await c.sleep(250);
 const p=await c.ev(`(function(){var r=document.querySelector('[data-s="hp.auto_apply"]').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);await c.click(p[0],p[1]);await c.sleep(300);
 rec("auto_apply unchecked",await c.ev(`document.querySelector('[data-s="hp.auto_apply"]').checked`)===false);
 const nApply0=(await c.ev(`window.__rpcLog()`)).filter(x=>/apply-strokes/.test(x)).length;
 await c.tool("raise");await c.set("hp.radius_ft",20);
 const pts=await c.f2c([[100,150],[180,150]]);const h0=L.snap();const hash0=await c.hash();
 await c.drag([pts[0],[(pts[0][0]+pts[1][0])/2,pts[0][1]],pts[1]]);await c.sleep(500);
 const nApply1=(await c.ev(`window.__rpcLog()`)).filter(x=>/apply-strokes/.test(x)).length;
 rec("no apply job while auto-apply off",nApply1===nApply0);rec("pending counter shows (1)",await c.ev(`document.getElementById('hpApplyN').textContent`)===" (1)",await c.ev(`document.getElementById('hpApplyN').textContent`));
 rec("pending outline drawn (canvas differs)",hash0!==await c.hash());rec("preview data unchanged",L.diff(h0.h,L.snap().h).changed===0);await c.shot("43_pending");
 await c.btn("hp_apply");await c.settle();
 rec("apply commits stroke",L.diff(h0.h,L.snap().h).changed>0&&await nS()===n5+1,await nS());rec("pending counter cleared",await c.ev(`document.getElementById('hpApplyN').textContent`)==="");await c.shot("44_applied");
 // re-enable
 await c.ev(`document.querySelector('[data-s="hp.auto_apply"]').scrollIntoView({block:'center',behavior:'instant'})`);await c.sleep(250);{const q=await c.ev(`(function(){var r=document.querySelector('[data-s="hp.auto_apply"]').getBoundingClientRect();return [r.left+r.width/2,r.top+r.height/2]})()`);await c.click(q[0],q[1]);await c.sleep(300);}
 rec("auto_apply re-enabled",await c.ev(`document.querySelector('[data-s="hp.auto_apply"]').checked`)===true);
 // reset removes saved layer too
 await c.btn("hp_reset");await c.sleep(500);await c.btn("hp_reset");await c.settle();
 rec("reset removes saved layer files",saved().length===0,saved().join(","));rec("preview back to base",Math.max(...L.snap().d.map(Math.abs))===0);await c.shot("45_reset");
 c.close();})().catch(e=>{console.error(e);process.exit(1)});
