(function(){
function rpc(o){var x=new XMLHttpRequest();x.open("POST","/rpc",false);x.send(JSON.stringify(o));return JSON.parse(x.responseText);}
function rpcA(o){return fetch("/rpc",{method:"POST",body:JSON.stringify(o)}).then(function(r){return r.json();});}
function b64ToBuf(b){var s=atob(b),a=new Uint8Array(s.length);for(var i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return a;}
function mkBuf(u8){u8.toString=function(enc){if(enc==="base64"){var s="";for(var i=0;i<this.length;i++)s+=String.fromCharCode(this[i]);return btoa(s);}return new TextDecoder().decode(this);};return u8;}
function err(r,p){var e=new Error((r.code||"ERR")+": "+(r.err||p));e.code=r.code||"EIO";return e;}
var fs={
 readFileSync:function(p,enc){var r=rpc({op:"read",p:p});if(!r.ok)throw err(r,p);if(r.text!==undefined)return enc?r.text:mkBuf(new TextEncoder().encode(r.text));var u=b64ToBuf(r.b64);return enc?new TextDecoder().decode(u):mkBuf(u);},
 writeFileSync:function(p,d){var u8=typeof d==="string"?new TextEncoder().encode(d):d;var s="";for(var i=0;i<u8.length;i++)s+=String.fromCharCode(u8[i]);var r=rpc({op:"write",p:p,b64:btoa(s)});if(!r.ok)throw err(r,p);},
 existsSync:function(p){return rpc({op:"exists",p:p}).v;},
 mkdirSync:function(p){var r=rpc({op:"mkdir",p:p});if(!r.ok)throw err(r,p);},
 readdirSync:function(p){var r=rpc({op:"readdir",p:p});if(!r.ok)throw err(r,p);return r.v;},
 statSync:function(p){var r=rpc({op:"stat",p:p});if(!r.ok)throw err(r,p);return r;},
 realpathSync:function(p){return p;},unlinkSync:function(){},renameSync:function(){}
};
var path={isAbsolute:function(p){return /^\//.test(p)||/^[A-Za-z]:/.test(p);},
 normalize:function(p){var a=[];p.split("/").forEach(function(s){if(s===".."&&a.length>1)a.pop();else if(s!=="."&&!(s===""&&a.length))a.push(s);});return a.join("/")||"/";},
 join:function(){return path.normalize(Array.prototype.join.call(arguments,"/").split(String.fromCharCode(92)).join("/"));},
 resolve:function(){var a=Array.prototype.slice.call(arguments),r="";for(var i=a.length-1;i>=0;i--){r=a[i]+(r?"/"+r:"");if(path.isAbsolute(a[i]))break;}return path.normalize(r.split(String.fromCharCode(92)).join("/"));},
 dirname:function(p){var i=p.split(String.fromCharCode(92)).join("/").replace(/\/+$/,"").lastIndexOf("/");return i<=0?"/":p.slice(0,i);},
 basename:function(p){return p.split(String.fromCharCode(92)).join("/").split("/").pop();}};
function spawn(cmd,args){var h={};var c={stdout:{on:function(e,f){h.so=f;}},stderr:{on:function(e,f){h.se=f;}},on:function(e,f){h[e]=f;},pid:1,kill:function(){}};
 setTimeout(function(){rpcA({op:"spawn",cmd:cmd,args:args}).then(function(r){h.so&&r.out&&h.so(r.out);h.se&&r.err&&h.se(r.err);h.close&&h.close(r.code);});},0);return c;}
window.require=function(n){if(n==="fs")return fs;if(n==="path")return path;if(n==="child_process")return {spawn:spawn};throw new Error("no module "+n);};
window.process={env:{},platform:"win32"};
window.__rpcLog=function(){return rpc({op:"log"}).v;};
window.__adobe_cep__={getSystemPath:function(t){return "/vroot/illustrator/panel";},evalScript:function(s,cb){setTimeout(function(){cb(JSON.stringify({ok:true}));},0);},
 addEventListener:function(){},dispatchEvent:function(){}};
window.cep={fs:{}};
})();
