// Browser harness for the Paint tab (NOT part of the node test run; needs Edge/Chrome). It serves illustrator/panel/index.html over http://127.0.0.1:8765 with CEP stubbed
// (stub.js: require/fs via sync XHR, child_process.spawn -> real python), redirecting world/ and illustrator/out/ to a TEMP copy so real data is never touched.
// Setup: copy world/<place> (without export/) to $PAINT_TMP/world/<place>; node server.js $PAINT_TMP 8765; start Edge with --remote-debugging-port=9333
// --remote-allow-origins=* and open the page; then node scenario_*.js. cdp.js sends real mouse/key/wheel events over CDP (Input.dispatchMouseEvent, pointer capture needs button:"left" on moves).
const fs=require("fs");
async function connect(){
  const list=await (await fetch("http://127.0.0.1:9333/json")).json();
  const t=list.find(x=>x.type==="page"&&x.url.startsWith("http://127.0.0.1:8765"));
  const ws=new WebSocket(t.webSocketDebuggerUrl); await new Promise(r=>ws.onopen=r);
  let id=0; const pend={};
  ws.onmessage=m=>{const d=JSON.parse(m.data); if(d.id&&pend[d.id]){pend[d.id](d);delete pend[d.id];}};
  const send=(method,params={})=>new Promise((res,rej)=>{const i=++id;pend[i]=d=>d.error?rej(new Error(JSON.stringify(d.error))):res(d.result);ws.send(JSON.stringify({id:i,method,params}));});
  const sleep=ms=>new Promise(r=>setTimeout(r,ms));
  const ev=async(expr)=>{const r=await send("Runtime.evaluate",{expression:expr,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw new Error(JSON.stringify(r.exceptionDetails).slice(0,400));return r.result.value;};
  const MOD={alt:1,ctrl:2,shift:8};
  const mod=a=>(a||[]).reduce((s,k)=>s|MOD[k],0);
  const mouse=(type,x,y,o={})=>send("Input.dispatchMouseEvent",Object.assign({type,x,y,button:"none",buttons:0,modifiers:mod(o.mods)},o.extra||{}));
  // canvas-relative -> page coords
  const rect=async()=>{await ev(`(function(){var e=document.getElementById('hpCanvas'),r=e.getBoundingClientRect();if(r.top<0||r.bottom>innerHeight)e.scrollIntoView({block:'center',behavior:'instant'})})()`);await sleep(60);return rect0();};
  const rect0=()=>ev(`(function(){var r=document.getElementById('hpCanvas').getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height,cw:document.getElementById('hpCanvas').width}})()`);
  const drag=async(pts,o={})=>{ // pts in canvas css px
    const r=await rect(); const P=pts.map(p=>[r.x+p[0],r.y+p[1]]);
    const btn=o.button||"left", bits={left:1,right:2,middle:4}[btn];
    await mouse("mouseMoved",P[0][0],P[0][1],o);
    await mouse("mousePressed",P[0][0],P[0][1],{mods:o.mods,extra:{button:btn,buttons:bits,clickCount:1}});
    for(let i=1;i<P.length;i++){await mouse("mouseMoved",P[i][0],P[i][1],{mods:o.mods,extra:{button:btn,buttons:bits}});await sleep(8);}
    const L=P[P.length-1];
    await mouse("mouseReleased",L[0],L[1],{mods:o.mods,extra:{button:btn,buttons:0,clickCount:1}});
  };
  const wheel=async(x,y,dy,o={})=>{const r=await rect();await send("Input.dispatchMouseEvent",{type:"mouseWheel",x:r.x+x,y:r.y+y,deltaX:0,deltaY:dy,modifiers:mod(o.mods)});};
  const key=async(k,code,o={})=>{const m=mod(o.mods);await send("Input.dispatchKeyEvent",{type:"keyDown",key:k,code,modifiers:m,windowsVirtualKeyCode:o.vk||0,text:o.text});await send("Input.dispatchKeyEvent",{type:"keyUp",key:k,code,modifiers:m,windowsVirtualKeyCode:o.vk||0});};
  const click=async(x,y)=>{await mouse("mouseMoved",x,y);await mouse("mousePressed",x,y,{extra:{button:"left",buttons:1,clickCount:1}});await mouse("mouseReleased",x,y,{extra:{button:"left",buttons:0,clickCount:1}});};
  const shot=async(name,clipEl)=>{const dir=(process.env.VB_SHOT_DIR||(process.env.VB_REPO||"D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository")+"/illustrator/out/paint_tab_test");fs.mkdirSync(dir,{recursive:true});
    let params={format:"png"}; if(clipEl!==false){const r=await ev(`(function(){var e=document.getElementById('hpCanvas');e.scrollIntoView({block:'center'});var r=e.getBoundingClientRect();return {x:r.left+scrollX,y:r.top+scrollY,width:r.width,height:r.height}})()`);params.clip=Object.assign({scale:1},r);}
    const d=await send("Page.captureScreenshot",params);name=name.startsWith("terrain_")?name:"terrain_"+name;fs.writeFileSync(dir+"/"+name+".png",Buffer.from(d.data,"base64"));return dir+"/"+name+".png";};
  const hash=()=>ev(`(function(){var c=document.getElementById('hpCanvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data,h=0;for(var i=0;i<d.length;i+=4){h=(h*31+d[i]+d[i+1]*3+d[i+2]*7)|0}return h})()`);
  const state=()=>ev(`(function(){var s=document.querySelector('#hpOut').textContent;return {out:s,status:document.getElementById('hpStatus').textContent,err:document.getElementById('err').textContent}})()`);
  const waitIdle=async()=>{for(let i=0;i<200;i++){const s=await ev(`document.getElementById('hpStatus').textContent+'|'+document.getElementById('status').textContent`);if(/\|idle$/.test(s)&&!/\.\.\./.test(s))return;await sleep(100);}throw new Error("busy timeout");};
  return {send,ev,sleep,mouse,drag,wheel,key,click,shot,hash,state,waitIdle,rect,close:()=>ws.close()};
}
module.exports={connect};
