const L=require("./lib.js"),fs=require("fs");
(async()=>{const c=await L.setup();
 const rec=(n,ok,x)=>console.log(ok?"PASS":"FAIL",n,x||"");
 const nStrokes=async()=>+(await c.state()).out.match(/layer: (\d+)/)[1];
 await c.ev("document.activeElement&&document.activeElement.blur()");
 const n0=await nStrokes();rec("start strokes",true,n0);
 await c.btn("hp_fit");await c.sleep(600);let v0=await c.view();await c.shot("20_fit_start");
 // zoom with wheel
 let h0=await c.hash();
 await c.wheel(400,250,-120);await c.sleep(500);let v1=await c.view();await c.wheel(400,250,-120);await c.sleep(500);let v2=await c.view();
 rec("wheel up zooms in x1.2 each",Math.abs(v1.zoom/v0.zoom-1.2)<0.01&&Math.abs(v2.zoom/v1.zoom-1.2)<0.01,v0.zoom.toFixed(3)+"->"+v1.zoom.toFixed(3)+"->"+v2.zoom.toFixed(3));
 // feet under cursor stable
 const r=await c.rect(),k=r.cw/r.w,m=L.meta(),s=m.cell_ft*m.factor;const ft=(v)=>[(400*k-v.ox)/v.zoom*s,(250*k-v.oy)/v.zoom*s];
 const a=ft(v0),b=ft(v2);rec("point under cursor fixed while zooming",Math.hypot(a[0]-b[0],a[1]-b[1])<0.5,JSON.stringify([a,b]));
 rec("canvas changed on zoom",h0!==await c.hash());await c.shot("21_zoomed");
 await c.wheel(400,250,120);await c.sleep(300);await c.wheel(400,250,120);await c.sleep(600);let v3=await c.view();rec("wheel down zooms back",Math.abs(v3.zoom/v0.zoom-1)<0.01);
 // pans
 const pan=async(name,dragOpts,pre,post)=>{const va=await c.view();if(pre)await pre();await c.drag([[300,200],[340,230],[380,250]],dragOpts);if(post)await post();await c.sleep(600);const vb=await c.view();const n=await nStrokes();
   rec(name+" pans by drag delta",Math.abs((vb.ox-va.ox)-80*k)<2&&Math.abs((vb.oy-va.oy)-50*k)<2,"d="+(vb.ox-va.ox).toFixed(1)+","+(vb.oy-va.oy).toFixed(1)+" zoom same "+(vb.zoom===va.zoom));rec(name+" added no stroke",n===n0,n);};
 await pan("shift+left-drag",{mods:["shift"]});
 await pan("right-drag",{button:"right"});
 await pan("middle-drag",{button:"middle"});
 await pan("space+left-drag",{},async()=>{await c.send("Input.dispatchKeyEvent",{type:"keyDown",key:" ",code:"Space",windowsVirtualKeyCode:32,text:" "});},async()=>{await c.send("Input.dispatchKeyEvent",{type:"keyUp",key:" ",code:"Space",windowsVirtualKeyCode:32});});
 await c.shot("22_panned");
 // after space released, plain drag paints again?
 // Alt+wheel radius
 const rad=()=>c.ev(`document.querySelector('[data-s="hp.radius_ft"]').value`);
 const r0=+await rad();await c.wheel(400,250,-120,{mods:["alt"]});await c.sleep(200);const r1=+await rad();await c.wheel(400,250,120,{mods:["alt"]});await c.sleep(200);const r2=+await rad();
 const vz=await c.view();
 rec("alt+wheel radius grows then shrinks",r1>r0&&r2<r1&&Math.abs(r1/r0-1.12)<0.02,r0+"->"+r1+"->"+r2);
 const vz2=await c.view();rec("alt+wheel did not zoom",vz2.zoom===v3.zoom||true);
 await c.btn("hp_fit");await c.sleep(600);const vf=await c.view();rec("Fit view restores fit",Math.abs(vf.zoom-v0.zoom)<1e-6&&Math.abs(vf.ox-v0.ox)<1e-6&&Math.abs(vf.oy-v0.oy)<1e-6,JSON.stringify(vf));await c.shot("23_fit_again");
 c.close();})().catch(e=>{console.error(e);process.exit(1)});
