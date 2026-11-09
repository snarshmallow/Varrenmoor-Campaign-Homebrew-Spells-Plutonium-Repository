// Browser harness for the Paint heightmap section (Terrain tab) (NOT part of the node test run; needs Edge/Chrome). It serves illustrator/panel/index.html over http://127.0.0.1:8765 with CEP stubbed
// (stub.js: require/fs via sync XHR, child_process.spawn -> real python), redirecting world/ and illustrator/out/ to a TEMP copy so real data is never touched.
// Setup: copy world/<place> (without export/) to $PAINT_TMP/world/<place>; node server.js $PAINT_TMP 8765; start Edge with --remote-debugging-port=9333
// --remote-allow-origins=* and open the page; then node scenario_*.js. cdp.js sends real mouse/key/wheel events over CDP (Input.dispatchMouseEvent, pointer capture needs button:"left" on moves).
const http=require("http"),fs=require("fs"),path=require("path"),cp=require("child_process");
const REPO=(process.env.VB_REPO||"D:/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository").split(String.fromCharCode(92)).join("/");
const TMP=process.argv[2].split(String.fromCharCode(92)).join("/"), PORT=+process.argv[3]||8765;
const PLACE=process.env.VB_PLACE||"bridgehollow__dyers_walk_local";
function map(p){p=p.split(String.fromCharCode(92)).join("/");
 if(!p.startsWith("/vroot")) return p;
 let r=p.slice(6);
 if(r==="/world"||r.startsWith("/world/")) return TMP+r;
 if(r.startsWith("/illustrator/out")) return TMP+"/out"+r.slice(16);
 if(r.startsWith("/illustrator/jobs")) return TMP+"/jobs"+r.slice(17);
 return REPO+r;}
function writable(m){return m.startsWith(TMP+"/");}
function body(req){return new Promise(r=>{let b=[];req.on("data",c=>b.push(c));req.on("end",()=>r(Buffer.concat(b)));});}
http.createServer(async(req,res)=>{
 const u=new URL(req.url,"http://x");
 try{
 if(u.pathname==="/"||u.pathname==="/index.html"){let h=fs.readFileSync(REPO+"/illustrator/panel/index.html","utf8");h=h.replace("<head>",'<head><script src="/__stub.js"></script>');res.setHeader("content-type","text/html");return res.end(h);}
 if(u.pathname==="/__stub.js"){res.setHeader("content-type","text/javascript");return res.end(fs.readFileSync(__dirname+"/stub.js"));}
 if(u.pathname==="/rpc"){
  const q=JSON.parse((await body(req)).toString()||"{}"); const op=q.op; const m=q.p!==undefined?map(q.p):null; let out;
  if(op==="read"){ if(/\/illustrator\/panel\/config\.json$/.test(q.p)){out={ok:true,text:JSON.stringify({jobsDir:"/vroot/illustrator/jobs"})};} else if(!fs.existsSync(m)||fs.statSync(m).isDirectory()) out={ok:false,code:"ENOENT"}; else out={ok:true,b64:fs.readFileSync(m).toString("base64")};}
  else if(op==="exists"){out={ok:true,v:/\/illustrator\/jobs$/.test(q.p)||fs.existsSync(m)||/\/illustrator\/panel$/.test(q.p)};}
  else if(op==="write"){ if(!writable(m)) out={ok:false,err:"write denied "+m}; else {fs.mkdirSync(path.dirname(m),{recursive:true});fs.writeFileSync(m,Buffer.from(q.b64,"base64"));out={ok:true};}}
  else if(op==="mkdir"){ if(!writable(m)) out={ok:false,err:"denied"}; else {fs.mkdirSync(m,{recursive:true});out={ok:true};}}
  else if(op==="readdir"){ out=fs.existsSync(m)?{ok:true,v:fs.readdirSync(m)}:{ok:false,code:"ENOENT"};}
  else if(op==="stat"){ out=fs.existsSync(m)?{ok:true,mtimeMs:fs.statSync(m).mtimeMs,size:fs.statSync(m).size}:{ok:false,code:"ENOENT"};}
  else if(op==="unlink"||op==="rename"){out={ok:true};}
  else if(op==="spawn"){
    let args=q.args.map(a=>typeof a==="string"?a.replace(/(^|=)(\/vroot[^\s]*)/,(s,a1,a2)=>a1+map(a2)):a);
    if(/heightmap_paint\.py$/.test(args.find(a=>/\.py$/.test(a))||"")){args=args.concat(["--world-root",TMP+"/world","--work-dir",TMP+"/out/panel/"+PLACE+"/heightmap_paint"]);}
    const log=args.join(" "); (global.LOG=global.LOG||[]).push(log);
    const r=cp.spawnSync(q.cmd,args,{cwd:REPO,encoding:"utf8",maxBuffer:1<<28,env:Object.assign({},process.env,{PYTHONIOENCODING:"utf-8"})});
    out={ok:true,code:r.status,out:r.stdout,err:r.stderr};}
  else if(op==="log"){out={ok:true,v:global.LOG||[]};}
  else out={ok:false,err:"bad op"};
  res.setHeader("content-type","application/json");return res.end(JSON.stringify(out));}
 // static
 let f=path.join(REPO,"illustrator/panel",decodeURIComponent(u.pathname));
 if(fs.existsSync(f)&&fs.statSync(f).isFile()){res.setHeader("content-type",f.endsWith(".js")?"text/javascript":f.endsWith(".css")?"text/css":f.endsWith(".json")?"application/json":"application/octet-stream");return res.end(fs.readFileSync(f));}
 res.statusCode=404;res.end("nf");
 }catch(e){res.statusCode=500;res.end(String(e));}
}).listen(PORT,"127.0.0.1",()=>console.log("up",PORT));
