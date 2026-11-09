// Varrenmoor: Sign maker - street signs and hanging (tavern / shop) signs as 3D Canvas tiles whose TEXT you can edit in Foundry.
// Install: python illustrator/generators/foundry_push.py install-sign-macro   (or the panel: Tools tab, "Install Sign maker macro"). GM only. Needs a scene in 3D Canvas mode for placing.
// Run the macro: pick a style (thumbnails), type the text (one line per row, first line biggest), choose font / colours / size / mount height / rotation, then
//   Place (click in the scene)   click on the ground (post styles) or on a WALL (wall plaque, wall bracket: the sign turns to face out of the wall and takes the click height)
//   Place at selected token      puts the sign at the controlled token (or the view centre)
//   Apply to chosen sign         re-reads the form and redraws the lettering of the sign picked in the top list (Edit selected sign: controlled tiles are offered first)
// How it works: each sign is ONE tile whose glTF (post, bracket, chains, frame, board) comes from `assets/varrenmoor-signs/models/<style>_v1.glb` (this macro uploads it the first
// time). The lettering is painted with canvas 2D (weathered wood, border, icon, text) here in the GM browser, saved as `assets/varrenmoor-signs/letters/s_<id>_<panel>.webp`, and
// applied to the board materials VB_sign_f / VB_sign_b (fingerpost arms VB_sign_a<N>f / b) by the tile's own `onAnimation` flag script on EVERY client (no module change; players see it).
// Everything about a sign is in the tile flag flags.varrenmoor.sign {v,style,text,arms,font,scheme,paint,ink,trim,finish,weather,spacing,icon,iconPos,back,backText,size,mountFt,seed,tex}
// so editing = this macro on that tile. Collision and sight are off (thin props), sunlight shadows are on (tile flag castShadow).
// Limits: GM only (players cannot upload or create tiles). Uploading needs the FILES_UPLOAD permission, which every GM has.
const DATA = /*__VB_SIGN_DATA__*/null;
const root = (typeof window !== "undefined" ? window : globalThis);
const FLAG = "varrenmoor", L3D = "levels-3d-preview";
const DIR = "assets/varrenmoor-signs";
const SCHEMA_V = 1;

// ---------------------------------------------------------------- pure helpers (unit tested in sign_maker.test.mjs; plain objects only)
const core = {
  hash(str) { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; } return h.toString(36); },
  rng(seed) { let a = typeof seed === "number" ? seed >>> 0 : parseInt(core.hash(String(seed)), 36) >>> 0; return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; },
  clamp: (v, a, b) => Math.min(b, Math.max(a, Number.isFinite(+v) ? +v : a)),
  uid(rand = Math.random) { let s = ""; for (let i = 0; i < 8; i++) s += "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(rand() * 36)]; return s; },

  // Greedy word wrap. measure(text) -> width. Explicit newlines are kept. A single word wider than maxW is split by characters.
  wrapText(measure, text, maxW) {
    const out = [];
    for (const raw of String(text).split("\n")) {
      const words = raw.split(/\s+/).filter((w) => w.length);
      if (!words.length) { out.push(""); continue; }
      let cur = "";
      for (let w of words) {
        while (measure(w) > maxW && w.length > 1) {                    // hard split a word that cannot fit on a line of its own
          let n = w.length - 1; while (n > 1 && measure(w.slice(0, n)) > maxW) n--;
          if (cur) { out.push(cur); cur = ""; }
          out.push(w.slice(0, n)); w = w.slice(n);
        }
        const t = cur ? cur + " " + w : w;
        if (cur && measure(t) > maxW) { out.push(cur); cur = w; } else cur = t;
      }
      out.push(cur);
    }
    return out;
  },
  // Lines of the sign: first line weight 1, others `rel` when lineStyle is subtitle. -> [{text, rel}]
  lineSpecs(text, lineStyle) {
    const raw = String(text || "").split("\n").map((s) => s.replace(/\s+$/g, "")).filter((s, i, a) => s.length || (i > 0 && i < a.length - 1));
    return raw.map((t, i) => ({ text: t, rel: lineStyle === "subtitle" && i > 0 ? 0.6 : 1 }));
  },
  // Largest font size (px, <= maxSize) at which every wrapped line fits boxW and the stack fits boxH. measure(text, size) -> width.
  fitText(measure, specs, boxW, boxH, o = {}) {
    const lh = o.lineHeight || 1.12, maxSize = o.maxSize || boxH, minSize = o.minSize || 6;
    const layout = (s) => {
      const lines = []; let h = 0;
      for (const sp of specs) {
        const size = s * sp.rel;
        for (const ln of core.wrapText((t) => measure(t, size), sp.text, boxW)) { lines.push({ text: ln, size }); h += size * lh; }
      }
      const w = Math.max(0, ...lines.map((l) => measure(l.text, l.size)));
      return { size: s, lines, w, h, fits: w <= boxW + 0.5 && h <= boxH + 0.5 };
    };
    let lo = minSize, hi = maxSize, best = layout(lo);
    if (layout(hi).fits) return layout(hi);
    for (let i = 0; i < 22; i++) { const mid = (lo + hi) / 2, r = layout(mid); if (r.fits) { best = r; lo = mid; } else hi = mid; }
    return best;
  },
  textureSize(px, quality) {                                          // [w,h] from the manifest size scaled to the quality (long side px)
    const k = quality / Math.max(px[0], px[1]);
    const r8 = (v) => Math.max(64, Math.round((v * k) / 8) * 8);
    return [r8(px[0]), r8(px[1])];
  },
  panelRect(w, h, safe, tipRight) {                                   // safe fractions [x0,y0,x1,y1] (given for tip-right) -> pixel rect, mirrored for tip-left
    const s = tipRight === false ? [1 - safe[2], safe[1], 1 - safe[0], safe[3]] : safe;
    return { x: s[0] * w, y: s[1] * h, w: (s[2] - s[0]) * w, h: (s[3] - s[1]) * h };
  },
  // Normalise any input (a form read, a stored flag, a partial object) to the flag schema; never throws.
  normalize(input, data) {
    const i = input || {}, P = data.presets, st = data.styles[i.style] ? i.style : Object.keys(data.styles)[0], style = data.styles[st];
    const def = P.defaults[style.kind] || {}, L = P.limits;
    const scheme = P.schemes[i.scheme] ? i.scheme : (def.scheme || "green"), sc = P.schemes[scheme];
    const hex = (v, d) => (/^#[0-9a-f]{6}$/i.test(v || "") ? v : d);
    const out = {
      v: SCHEMA_V, style: st,
      text: String(i.text !== undefined ? i.text : def.lines || "").slice(0, L.maxText).split("\n").slice(0, L.maxLines).join("\n"),
      lineStyle: i.lineStyle === "subtitle" ? "subtitle" : "equal",
      font: String(i.font || def.font || "serif").slice(0, 80), scheme,
      paint: scheme === "custom" ? hex(i.paint, sc.paint) : sc.paint, ink: scheme === "custom" ? hex(i.ink, sc.ink) : sc.ink, trim: scheme === "custom" ? hex(i.trim, sc.trim) : sc.trim,
      finish: ["painted", "carved", "gilt"].includes(i.finish) ? i.finish : def.finish || "painted",
      weather: core.clamp(i.weather ?? def.weather ?? 0.4, 0, L.weatherMax), spacing: core.clamp(i.spacing ?? def.spacing ?? 0.03, 0, 0.3),
      icon: P.icons.includes(i.icon) ? i.icon : def.icon || "none", iconPos: ["none", "top", "left"].includes(i.iconPos) ? i.iconPos : def.iconPos || "none",
      back: ["same", "blank", "text"].includes(i.back) ? i.back : def.back || "same", backText: String(i.backText || "").slice(0, L.maxText),
      size: core.clamp(i.size ?? 1, L.sizeMin, L.sizeMax), mountFt: core.clamp(i.mountFt ?? style.mount_ft ?? 0, 0, 200),
      seed: String(i.seed || ""), quality: [512, 1024, 2048].includes(+i.quality) ? +i.quality : 1024,
    };
    if (out.icon === "none") out.iconPos = "none"; else if (out.iconPos === "none") out.iconPos = style.kind === "hanging" ? "top" : "left";
    if (style.arms) {
      const arms = Array.isArray(i.arms) ? i.arms : [];
      out.arms = Array.from({ length: style.arms }, (_, n) => { const a = arms[n] || {}; return { text: String(a.text !== undefined ? a.text : ["Dyers Walk", "Market Square", "Bridgehollow", "The Old Mill"][n] || "").slice(0, 120), dir: a.dir === -1 || a.dir === "-1" ? -1 : 1, yaw: core.clamp(a.yaw ?? 0, -60, 60) }; });
    }
    if (i.tex && typeof i.tex === "object") out.tex = i.tex;
    if (i.base && typeof i.base === "object") out.base = i.base;
    return out;
  },
  // The lettering panels of a sign: [{id, mat, w, h (px), safe rect (px), text, tipRight|null, role, armIndex}]
  panels(sign, style) {
    const out = [];
    const mk = (mat, id, text, tipRight, role, armIndex) => {
      const m = style.panels[mat]; if (!m) return;
      const [w, h] = core.textureSize(m.px, sign.quality);
      out.push({ id, mat, w, h, safe: core.panelRect(w, h, m.safe, tipRight), text, tipRight, role, armIndex });
    };
    if (style.arms) {
      sign.arms.forEach((a, n) => { const k = n + 1; mk(`VB_sign_a${k}f`, `a${k}f`, a.text, a.dir === 1, "arm", k); mk(`VB_sign_a${k}b`, `a${k}b`, a.text, a.dir !== 1, "arm", k); });
    } else {
      mk("VB_sign_f", "f", sign.text, null, "face");
      mk("VB_sign_b", "b", sign.back === "same" ? sign.text : sign.back === "text" ? sign.backText : "", null, "face");
    }
    return out;
  },
  // Rotation (degrees, tile rotation) that turns a style's outward direction (model frame, scene px axes: x east, y SOUTH) onto the wall normal (px axes).
  rotationFor(outward, normal) {
    const a = Math.atan2(normal.y, normal.x) - Math.atan2(outward[1], outward[0]);
    return ((Math.round((a * 180) / Math.PI * 10) / 10) % 360 + 360) % 360;
  },
  ftToUnits: (units) => (/^m(eter)?s?$/i.test(String(units || "").trim()) ? 0.3048 : 1),
  letterPath: (uid, id, ext = "webp") => `${DIR}/letters/s_${uid}_${id}.${ext}`,
  modelPath: (style) => `${DIR}/models/${style.file}`,
  basePaths: () => ({ wood: `${DIR}/tex/wood.jpg`, dark: `${DIR}/tex/dark.jpg`, iron: `${DIR}/tex/iron.jpg` }),
  // Tile document data for a new sign. pos {x,y} scene px, ppm = scene px per metre, unitsPerFt = elevation units per foot, rotation degrees.
  tileData(sign, style, pos, ppm, o = {}) {
    const k = sign.size, s = style.size_m, ground = style.mount === "ground";
    const w = s[0] * ppm * k, h = s[1] * ppm * k, d = s[2] * ppm * k;
    const elevation = ground ? 0 : Math.round(sign.mountFt * (o.unitsPerFt ?? 1) * 100) / 100;
    return {
      x: pos.x, y: pos.y, width: w, height: h, rotation: o.rotation || 0, elevation, hidden: false,
      texture: { src: "modules/levels-3d-preview/assets/blank.webp" },
      flags: {
        [L3D]: { model3d: core.modelPath(style), autoGround: ground, autoCenter: false, collision: false, sight: false, depth: d, castShadow: true, enableAnimationScripts: true, onAnimation: core.animationScript() },
        [FLAG]: { pipelineId: `sign:${sign.seed}`, sign },
      },
    };
  },
  // Updates for an existing tile when the size / mount height / style data changed (a resize keeps the origin: the model origin is the anchor).
  resizeData(sign, style, ppm, unitsPerFt) {
    const k = sign.size, s = style.size_m, ground = style.mount === "ground";
    return { width: s[0] * ppm * k, height: s[1] * ppm * k, [`flags.${L3D}.depth`]: s[2] * ppm * k, elevation: ground ? 0 : Math.round(sign.mountFt * unitsPerFt * 100) / 100 };
  },
  // The text of the flag `onAnimation` (a function BODY run every frame on every client; `this` = first child of the tile model, the Tile3D is found through userData.entity3D). First frame: clone the sign materials, put the wood / iron / lettering textures on them,
  // show arm<N> or arm<N>L (the left pointing copy) and apply the arm yaw. Later frames return at once.
  animationScript() {
    return [
      "let o=this,t=null; while(o){ if(o.userData&&o.userData.entity3D){t=o.userData.entity3D;break;} o=o.parent; }",
      "if(!t||!t.mesh||t.__vbs) return; t.__vbs=1;",
      "const s=t.tile.document.flags&&t.tile.document.flags.varrenmoor&&t.tile.document.flags.varrenmoor.sign; if(!s) return;",
      "const L=game.Levels3DPreview,T=L.THREE,ld=new T.TextureLoader(),C=(L.__vbSignTex=L.__vbSignTex||{}),tx=s.tex||{},bs=s.base||{};",
      "const mk=(u,base,flip)=>{ if(base&&C[u]) return C[u]; const x=ld.load(u); x.flipY=false; x.encoding=T.sRGBEncoding; x.anisotropy=8;",
      " if(base){x.wrapS=x.wrapT=T.RepeatWrapping; C[u]=x;} return x; };",
      "const BN={sign_wood:'wood',sign_oak_dark:'dark',sign_iron:'iron'};",
      "t.mesh.traverse(o=>{ if(!o.isMesh||!o.material) return; const n=o.material.name; let u=null,base=false,flip=false;",
      " if(tx[n]){u=tx[n].src+'?v='+(tx[n].v||''); flip=!!tx[n].flip;} else if(BN[n]&&bs[BN[n]]){u=bs[BN[n]]; base=true;}",
      " o.castShadow=true; o.receiveShadow=true; if(!u) return; o.material=o.material.clone(); o.material.map=mk(u,base,flip); o.material.color.set(0xffffff); o.material.needsUpdate=true; });",
      "const ar=s.arms||[]; t.mesh.traverse(o=>{ const m=/^arm(\\d)(L?)$/.exec(o.name||''); const a=m&&ar[m[1]-1]; if(a){ o.visible=(a.dir<0)===!!m[2]; o.rotation.y=-(a.yaw||0)*Math.PI/180; }});",
    ].join("\n");
  },
  armTransform: (a) => ({ node: a.dir < 0 ? "L" : "", yawRad: (-(a.yaw || 0) * Math.PI) / 180 }),
  // Per-style summary for lists: "High Street" / "Dyers Walk | Market Square".
  summary(sign) { return (sign.arms ? sign.arms.map((a) => a.text.split("\n")[0]).join(" | ") : String(sign.text || "").split("\n")[0]) || "(blank)"; },
};

if (root.__VB_SIGN_TEST) { root.__vbSignCore = core; return; }
if (!DATA) return ui.notifications.error("Sign maker: this macro text has no data block. Run: python illustrator/generators/foundry_push.py install-sign-macro");
if (!game.user.isGM) return ui.notifications.warn("Sign maker is for the GM (it uploads files and creates tiles).");
if (root.__vbSignDialog?.rendered) { try { root.__vbSignDialog.bringToFront?.(); } catch (e) { /* ignore */ } return; }

const FP = foundry.applications.apps.FilePicker.implementation;
const L = game.Levels3DPreview;
const styles = DATA.styles, presets = DATA.presets;

// ---------------------------------------------------------------- files
async function ensureDirs() {
  for (const d of [DIR, `${DIR}/models`, `${DIR}/tex`, `${DIR}/letters`]) { try { await FP.createDirectory("data", d); } catch (e) { /* exists */ } }
}
async function gunzipB64(b64, type) {
  const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
  const out = await new Response(new Blob([u]).stream().pipeThrough(new DecompressionStream("gzip"))).arrayBuffer();
  return new Blob([out], { type });
}
const b64Blob = (b64, type) => { const bin = atob(b64), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new Blob([u], { type }); };
async function exists(path) { try { const r = await fetch(path, { method: "HEAD", cache: "no-store" }); return r.ok; } catch (e) { return false; } }
async function upload(blob, path) {
  const name = path.split("/").pop(), dir = path.slice(0, path.length - name.length - 1);
  const r = await FP.upload("data", dir, new File([blob], name, { type: blob.type }), {}, { notify: false });
  if (!r || r.status === "error") throw new Error(`upload failed: ${path} ${r?.message || ""}`);
  return r.path || path;
}
async function ensureAssets(styleKey) {                                // shared textures once, the model of this style once (a new model version = a new file name)
  await ensureDirs();
  const bp = core.basePaths(), tn = { wood: "wood", dark: "dark", iron: "iron" };
  for (const k of Object.keys(tn)) if (!(await exists(bp[k]))) await upload(b64Blob(DATA.textures[k], "image/jpeg"), bp[k]);
  const mp = core.modelPath(styles[styleKey]);
  if (!(await exists(mp))) await upload(await gunzipB64(DATA.models[styleKey], "model/gltf-binary"), mp);
}

// ---------------------------------------------------------------- fonts
const fontStack = (f) => `"${f}", Georgia, serif`;
let _fc;
function fontAvailable(name) {
  if (/^(serif|sans-serif|monospace)$/i.test(name)) return true;
  _fc = _fc || document.createElement("canvas").getContext("2d");
  const t = "mmmmmmmmmmlliWWW@#", w = (f) => { _fc.font = `40px ${f}`; return _fc.measureText(t).width; };
  return w(`"${name}", monospace`) !== w("monospace") || w(`"${name}", serif`) !== w("serif") || w(`"${name}", sans-serif`) !== w("sans-serif");
}
function fontList() {
  const seen = new Set(), out = [];
  for (const f of presets.fonts) if (!seen.has(f.name) && fontAvailable(f.name)) { seen.add(f.name); out.push(f); }
  for (const name of Object.keys(CONFIG.fontDefinitions || {})) if (!seen.has(name)) { seen.add(name); out.push({ name, note: "Foundry" }); }
  return out;
}

// ---------------------------------------------------------------- painting
const mk = (w, h) => { const c = document.createElement("canvas"); c.width = w; c.height = h; return c; };
const imgCache = {};
async function loadImg(src) { if (imgCache[src]) return imgCache[src]; const im = new Image(); im.crossOrigin = "anonymous"; im.src = src; await im.decode(); return (imgCache[src] = im); }
async function baseImages() { const o = {}, bp = core.basePaths(); for (const k of Object.keys(bp)) o[k] = await loadImg(DATA.textures[k] ? `data:image/jpeg;base64,${DATA.textures[k]}` : bp[k]); return o; }

// icons: drawn in a [-1,1] box, ink colour fill, detail colour `d` (the board colour) for cut-outs
const ICONS = {
  mug(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.roundRect(-0.55, -0.55, 0.95, 1.2, 0.08); c.fill(); c.lineWidth = 0.17; c.strokeStyle = ink; c.beginPath(); c.arc(0.43, 0.0, 0.3, -1.2, 1.2); c.stroke();
    c.fillStyle = d; c.fillRect(-0.45, -0.18, 0.75, 0.07); c.fillStyle = ink; c.beginPath(); c.ellipse(-0.08, -0.62, 0.55, 0.2, 0, 0, 7); c.fill(); c.fillStyle = d; c.globalAlpha = 0.5; c.beginPath(); c.ellipse(-0.08, -0.62, 0.42, 0.1, 0, 0, 7); c.fill(); c.globalAlpha = 1; },
  anvil(c, ink) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.95, -0.35); c.lineTo(0.5, -0.35); c.quadraticCurveTo(0.95, -0.3, 1, -0.05); c.quadraticCurveTo(0.6, -0.02, 0.45, 0.08); c.lineTo(0.3, 0.3); c.lineTo(0.55, 0.62); c.lineTo(-0.55, 0.62); c.lineTo(-0.3, 0.3); c.lineTo(-0.35, 0.05); c.quadraticCurveTo(-0.8, 0.0, -0.95, -0.35); c.fill(); },
  bread(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.ellipse(0, 0.1, 0.95, 0.55, 0, 0, 7); c.fill(); c.strokeStyle = d; c.lineWidth = 0.09; c.lineCap = "round"; for (const x of [-0.45, 0, 0.45]) { c.beginPath(); c.moveTo(x - 0.12, -0.2); c.lineTo(x + 0.12, 0.35); c.stroke(); } },
  key(c, ink, d) { c.strokeStyle = ink; c.fillStyle = ink; c.lineWidth = 0.2; c.beginPath(); c.arc(-0.55, 0, 0.36, 0, 7); c.stroke(); c.fillRect(-0.2, -0.1, 1.15, 0.2); c.fillRect(0.55, 0.05, 0.18, 0.45); c.fillRect(0.82, 0.05, 0.16, 0.34); },
  boot(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.45, -0.95); c.lineTo(0.2, -0.95); c.lineTo(0.2, 0.1); c.quadraticCurveTo(0.85, 0.2, 0.95, 0.5); c.lineTo(0.95, 0.75); c.lineTo(-0.55, 0.75); c.lineTo(-0.55, 0.45); c.lineTo(-0.45, 0.45); c.closePath(); c.fill(); c.fillStyle = d; c.fillRect(-0.55, 0.62, 1.5, 0.09); },
  barrel(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.6, -0.85); c.quadraticCurveTo(-0.95, 0, -0.6, 0.85); c.lineTo(0.6, 0.85); c.quadraticCurveTo(0.95, 0, 0.6, -0.85); c.closePath(); c.fill(); c.strokeStyle = d; c.lineWidth = 0.08; for (const y of [-0.5, 0.5]) { c.beginPath(); c.moveTo(-0.85, y); c.quadraticCurveTo(0, y + 0.18, 0.85, y); c.stroke(); } c.lineWidth = 0.05; c.beginPath(); c.moveTo(0, -0.85); c.lineTo(0, 0.85); c.stroke(); },
  horseshoe(c, ink, d) { c.strokeStyle = ink; c.lineWidth = 0.3; c.lineCap = "butt"; c.beginPath(); c.arc(0, 0.05, 0.62, Math.PI * 0.8 - 0.05, Math.PI * 0.2 + 0.05 + Math.PI * 2 - 0.0, false); c.stroke(); c.fillStyle = d; for (const a of [-0.35, -0.1, 0.1, 0.35]) { c.beginPath(); c.arc(Math.sin(a * 6) * 0.62, 0.05 - Math.cos(a * 6) * 0.62, 0.045, 0, 7); c.fill(); } },
  bell(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.18, -0.85); c.lineTo(0.18, -0.85); c.lineTo(0.2, -0.6); c.quadraticCurveTo(0.7, -0.3, 0.6, 0.35); c.lineTo(0.95, 0.6); c.lineTo(-0.95, 0.6); c.lineTo(-0.6, 0.35); c.quadraticCurveTo(-0.7, -0.3, -0.2, -0.6); c.closePath(); c.fill(); c.beginPath(); c.arc(0, 0.82, 0.16, 0, 7); c.fill(); },
  flask(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.18, -0.9); c.lineTo(0.18, -0.9); c.lineTo(0.18, -0.3); c.lineTo(0.72, 0.62); c.quadraticCurveTo(0.8, 0.85, 0.55, 0.85); c.lineTo(-0.55, 0.85); c.quadraticCurveTo(-0.8, 0.85, -0.72, 0.62); c.lineTo(-0.18, -0.3); c.closePath(); c.fill(); c.fillStyle = d; c.globalAlpha = 0.55; c.beginPath(); c.moveTo(-0.5, 0.35); c.lineTo(0.5, 0.35); c.lineTo(0.62, 0.62); c.lineTo(-0.62, 0.62); c.fill(); c.globalAlpha = 1; },
  sword(c, ink, d) { c.save(); c.rotate(-0.78); c.fillStyle = ink; c.beginPath(); c.moveTo(0, -1.0); c.lineTo(0.1, -0.7); c.lineTo(0.1, 0.35); c.lineTo(-0.1, 0.35); c.lineTo(-0.1, -0.7); c.closePath(); c.fill(); c.fillRect(-0.4, 0.35, 0.8, 0.12); c.fillRect(-0.06, 0.47, 0.12, 0.35); c.beginPath(); c.arc(0, 0.88, 0.1, 0, 7); c.fill(); c.restore(); },
  fish(c, ink, d) { c.fillStyle = ink; c.beginPath(); c.moveTo(-0.95, 0); c.quadraticCurveTo(-0.3, -0.7, 0.45, -0.1); c.lineTo(0.95, -0.5); c.lineTo(0.95, 0.5); c.lineTo(0.45, 0.1); c.quadraticCurveTo(-0.3, 0.7, -0.95, 0); c.fill(); c.fillStyle = d; c.beginPath(); c.arc(-0.55, -0.05, 0.07, 0, 7); c.fill(); },
  sun(c, ink, d) { c.fillStyle = ink; c.strokeStyle = ink; c.beginPath(); c.arc(0, 0, 0.45, 0, 7); c.fill(); c.lineWidth = 0.13; c.lineCap = "round"; for (let i = 0; i < 12; i++) { const a = (i * Math.PI) / 6, r1 = 0.62, r2 = i % 2 ? 0.85 : 0.98; c.beginPath(); c.moveTo(Math.cos(a) * r1, Math.sin(a) * r1); c.lineTo(Math.cos(a) * r2, Math.sin(a) * r2); c.stroke(); } },
};

function noiseWear(P, w, h, weather, rnd, safe) {                         // erase paint: speckles, grain scratches, edge flaking (destination-out)
  if (weather <= 0) return;
  P.save(); P.globalCompositeOperation = "destination-out";
  const n = Math.round(((w * h) / 520) * weather);
  for (let i = 0; i < n; i++) {
    const x = rnd() * w, y = rnd() * h, edge = Math.min(x, w - x, y, h - y) / Math.min(w, h);
    if (rnd() > 0.25 + 1.6 * Math.max(0, 0.2 - edge) * 5) continue;
    const r = 0.8 + rnd() * rnd() * 5 * (w / 1024 + 0.4);
    P.globalAlpha = 0.25 + rnd() * 0.7; P.beginPath(); P.ellipse(x, y, r * (1 + rnd() * 2), r, 0, 0, 7); P.fill();
  }
  P.lineCap = "round";
  for (let i = 0; i < 40 * weather; i++) {                                // long thin scratches along the grain (horizontal)
    const x = rnd() * w, y = rnd() * h, l = 20 + rnd() * w * 0.35; P.globalAlpha = 0.2 + rnd() * 0.5; P.lineWidth = 0.6 + rnd() * 1.6;
    P.beginPath(); P.moveTo(x, y); P.lineTo(x + l, y + (rnd() - 0.5) * 6); P.stroke();
  }
  for (let i = 0; i < 14 * weather; i++) {                                // flaked patches near the edges
    const side = Math.floor(rnd() * 4), t = rnd(), r = (0.02 + rnd() * 0.05) * Math.min(w, h);
    const x = side < 2 ? t * w : side === 2 ? 0 : w, y = side >= 2 ? t * h : side === 0 ? 0 : h;
    const g = P.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, "rgba(0,0,0,0.95)"); g.addColorStop(1, "rgba(0,0,0,0)"); P.globalAlpha = 0.35 + 0.5 * weather; P.fillStyle = g;
    P.beginPath(); P.ellipse(x, y, r * 1.6, r, rnd() * 3, 0, 7); P.fill();
  }
  P.restore();
}

function drawText(c, layout, rect, sign, rnd) {
  const sp = sign.spacing, cy0 = rect.y + (rect.h - layout.h) / 2, lh = 1.12;
  let y = cy0;
  for (const ln of layout.lines) {
    const size = ln.size; c.font = `${sign.fontWeight || "bold"} ${size}px ${fontStack(sign.font)}`; try { c.letterSpacing = `${size * sp}px`; } catch (e) { /* old engine */ }
    c.textAlign = "center"; c.textBaseline = "alphabetic"; try { c.fontKerning = "normal"; c.textRendering = "optimizeLegibility"; } catch (e) { /* ignore */ }
    const cx = rect.x + rect.w / 2 + (size * sp) / 2, by = y + size * (lh * 0.5 + 0.33);
    if (sign.finish === "carved") {
      c.fillStyle = "rgba(255,240,200,0.35)"; c.fillText(ln.text, cx + size * 0.015, by + size * 0.025);
      c.fillStyle = "rgba(10,5,0,0.55)"; c.fillText(ln.text, cx - size * 0.012, by - size * 0.02);
      c.fillStyle = sign.ink; c.globalAlpha = 0.9; c.fillText(ln.text, cx, by); c.globalAlpha = 1;
    } else if (sign.finish === "gilt") {
      c.lineJoin = "round"; c.strokeStyle = "rgba(0,0,0,0.65)"; c.lineWidth = Math.max(1, size * 0.045); c.strokeText(ln.text, cx + size * 0.01, by + size * 0.018);
      const g = c.createLinearGradient(0, by - size * 0.7, 0, by); g.addColorStop(0, "#f2d77a"); g.addColorStop(0.5, sign.ink); g.addColorStop(1, "#8a6420"); c.fillStyle = g; c.fillText(ln.text, cx, by);
    } else {
      c.fillStyle = sign.ink;                                              // painted: two slightly offset passes give a brush edge
      c.globalAlpha = 0.55; c.fillText(ln.text, cx + (rnd() - 0.5) * size * 0.012, by + (rnd() - 0.5) * size * 0.012);
      c.globalAlpha = 1; c.fillText(ln.text, cx, by);
    }
    y += size * lh;
  }
}

// One lettering canvas for a panel. imgs = {wood, dark}. rnd = seeded random.
function renderPanel(sign, panel, imgs, rnd) {
  const { w, h } = panel, C = mk(w, h), c = C.getContext("2d");
  const style = styles[sign.style];
  // 1. wood underneath (grain runs along the long side)
  const wood = imgs.wood, pat = c.createPattern(wood, "repeat"), ps = Math.max(w, h) / 1100;
  c.save(); c.scale(ps * 1.6, ps * 1.0); c.fillStyle = pat; c.fillRect(0, 0, w / (ps * 1.6), h / ps); c.restore();
  c.globalCompositeOperation = "multiply"; c.fillStyle = "rgba(120,86,48,0.55)"; c.fillRect(0, 0, w, h); c.globalCompositeOperation = "source-over";
  // 2. paint layer: colour, borders, icon, lettering - then worn away
  const P = mk(w, h), p = P.getContext("2d");
  const stain = !sign.paint;
  if (!stain) {
    p.fillStyle = sign.paint; p.fillRect(0, 0, w, h);
    for (let i = 0; i < 28; i++) { const bx = rnd() * w, by = rnd() * h, br = w * (0.04 + rnd() * 0.16), gg = p.createRadialGradient(bx, by, 0, bx, by, br), col = rnd() > 0.5 ? "0,0,0" : "255,255,255"; gg.addColorStop(0, `rgba(${col},${0.05 + rnd() * 0.05})`); gg.addColorStop(1, `rgba(${col},0)`); p.fillStyle = gg; p.fillRect(bx - br, by - br, br * 2, br * 2); }
    p.globalAlpha = 1;
  }
  const s = panel.safe, m = Math.min(s.w, s.h);
  if (panel.role === "face" || panel.role === "arm") {
    const bw = Math.max(2, m * 0.035);
    p.strokeStyle = sign.trim; p.lineWidth = bw; p.strokeRect(s.x + bw, s.y + bw, s.w - bw * 2, s.h - bw * 2);
    p.lineWidth = bw * 0.4; p.strokeRect(s.x + bw * 2.6, s.y + bw * 2.6, s.w - bw * 5.2, s.h - bw * 5.2);
  }
  const pad = m * 0.12;
  let box = { x: s.x + pad, y: s.y + pad, w: s.w - pad * 2, h: s.h - pad * 2 };
  if (sign.icon !== "none" && sign.iconPos !== "none" && panel.text !== undefined) {
    const side = sign.iconPos === "left" ? Math.min(box.h, box.w * 0.34) : Math.min(box.w, box.h * 0.58);
    const ic = sign.iconPos === "left" ? { x: box.x + side / 2, y: box.y + box.h / 2 } : { x: box.x + box.w / 2, y: box.y + side / 2 };
    p.save(); p.translate(ic.x, ic.y); p.scale(side / 2 * 0.92, side / 2 * 0.92); p.fillStyle = sign.ink; p.strokeStyle = sign.ink; (ICONS[sign.icon] || (() => {}))(p, sign.ink, stain ? "#c9a46a" : sign.paint); p.restore();
    if (sign.iconPos === "left") box = { x: box.x + side * 1.08, y: box.y, w: box.w - side * 1.08, h: box.h }; else box = { x: box.x, y: box.y + side * 1.04, w: box.w, h: box.h - side * 1.04 };
  }
  const specs = core.lineSpecs(panel.text, sign.lineStyle);
  if (specs.length) {
    const meas = (t, size) => { p.font = `bold ${size}px ${fontStack(sign.font)}`; try { p.letterSpacing = `${size * sign.spacing}px`; } catch (e) { /* ignore */ } return p.measureText(t).width; };
    const layout = core.fitText(meas, specs, box.w, box.h, { maxSize: box.h * (specs.length === 1 && panel.role === "arm" ? 0.8 : 0.7) });
    drawText(p, layout, box, sign, rnd);
  }
  if (stain) { p.globalCompositeOperation = "source-over"; }
  else noiseWear(p, w, h, sign.weather, rnd, s);
  c.drawImage(P, 0, 0);
  // 3. grime: darker at the bottom and the edges, vertical rain streaks, a little uneven tone
  c.globalCompositeOperation = "multiply";
  let g = c.createLinearGradient(0, 0, 0, h); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.7, `rgba(${255 - 40 * sign.weather},${255 - 44 * sign.weather},${255 - 52 * sign.weather},1)`); g.addColorStop(1, `rgba(${255 - 95 * sign.weather},${255 - 100 * sign.weather},${255 - 110 * sign.weather},1)`);
  c.fillStyle = g; c.fillRect(0, 0, w, h);
  g = c.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.3, w / 2, h / 2, Math.max(w, h) * 0.7); g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(1, `rgba(${255 - 120 * sign.weather},${255 - 125 * sign.weather},${255 - 135 * sign.weather},1)`);
  c.fillStyle = g; c.fillRect(0, 0, w, h);
  c.globalCompositeOperation = "source-over";
  for (let i = 0; i < 26 * sign.weather; i++) { const x = rnd() * w, l = h * (0.2 + rnd() * 0.6); const gg = c.createLinearGradient(0, 0, 0, l); gg.addColorStop(0, "rgba(30,20,10,0.16)"); gg.addColorStop(1, "rgba(30,20,10,0)"); c.fillStyle = gg; c.save(); c.translate(x, 0); c.fillRect(0, 0, 1 + rnd() * 3, l); c.restore(); }
  return C;
}
const toBlob = (cv) => new Promise((res) => cv.toBlob((b) => (b && b.type === "image/webp" ? res(b) : cv.toBlob((p) => res(p), "image/png")), "image/webp", 0.88));

// ---------------------------------------------------------------- sign operations
const ppmOf = () => canvas.scene.grid.size / (canvas.scene.grid.distance * 0.3048);
const unitsPerFt = () => core.ftToUnits(canvas.scene.grid.units);
const signOf = (doc) => doc?.flags?.[FLAG]?.sign;
const signTiles = () => canvas.scene.tiles.contents.filter((t) => signOf(t));

async function paintAll(sign) {                                           // render + upload every panel; -> tex flag map
  const imgs = await baseImages(), rnd = core.rng(sign.seed + "|" + core.hash(JSON.stringify([sign.text, sign.arms, sign.font])));
  await Promise.all(Object.keys(sign.fontsToLoad || { [sign.font]: 1 }).map((f) => document.fonts.load(`48px ${fontStack(f)}`).catch(() => {})));
  const style = styles[sign.style], tex = {};
  const v = core.hash(JSON.stringify(sign) + Date.now());
  for (const pn of core.panels(sign, style)) {
    const cv = renderPanel(sign, pn, imgs, rnd), blob = await toBlob(cv), ext = blob.type === "image/png" ? "png" : "webp";
    const src = await upload(blob, core.letterPath(sign.seed, pn.id, ext));
    tex[pn.mat] = { src, v };
  }
  return tex;
}
function withBase(sign) { return { ...sign, base: core.basePaths() }; }

async function createSign(raw, pos, opts = {}) {
  const sign = core.normalize({ ...raw, seed: raw.seed || core.uid() }, DATA), style = styles[sign.style];
  await ensureAssets(sign.style);
  sign.tex = await paintAll(sign);
  const full = withBase(sign);
  const data = core.tileData(full, style, pos, ppmOf(), { rotation: opts.rotation || 0, unitsPerFt: unitsPerFt() });
  if (opts.elevation !== undefined) data.elevation = opts.elevation;
  const [t] = await canvas.scene.createEmbeddedDocuments("Tile", [data]);
  ui.notifications.info(`Sign placed: ${core.summary(sign)}`);
  return t;
}
async function updateSign(tile, raw, opts = {}) {                         // edit text/look; keeps seed, position, rotation
  const old = signOf(tile) || {}, style0 = styles[old.style];
  const sign = core.normalize({ ...raw, seed: old.seed || core.uid(), style: raw.style || old.style }, DATA), style = styles[sign.style];
  if (sign.style !== old.style) ui.notifications.warn("A different style needs a new sign: place it again and delete the old one. Updating text and look only.");
  const keep = sign.style === old.style ? sign : { ...sign, style: old.style, arms: old.arms };
  const ks = core.normalize(keep, DATA);
  await ensureAssets(ks.style);
  ks.tex = await paintAll(ks);
  const full = withBase(ks), st = styles[ks.style];
  const upd = { _id: tile.id, [`flags.${FLAG}.sign`]: full, ...core.resizeData(full, st, ppmOf(), unitsPerFt()) };
  if (opts.rotation !== undefined) upd.rotation = opts.rotation;
  if (opts.elevation !== undefined) upd.elevation = opts.elevation;
  upd[`flags.${L3D}.onAnimation`] = core.animationScript();                // also upgrades the script of older signs
  await canvas.scene.updateEmbeddedDocuments("Tile", [upd]);
  ui.notifications.info(`Sign updated: ${core.summary(ks)}`);
}

// ---------------------------------------------------------------- click picking (ground or wall hit in the 3D view)
function pickPoint(wantWall) {
  return new Promise((resolve) => {
    if (!L?.renderer) { ui.notifications.warn("Sign maker: open a scene in 3D Canvas mode to click-place."); return resolve(null); }
    const dom = L.renderer.domElement, T = L.THREE; let down = null;
    ui.notifications.info("Sign maker: click where the sign goes (ground, or a wall for wall styles). Esc cancels.");
    const done = (v) => { dom.removeEventListener("pointerdown", onDown, true); dom.removeEventListener("pointerup", onUp, true); window.removeEventListener("keydown", onKey, true); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    const onDown = (e) => { down = e.button === 0 ? { x: e.clientX, y: e.clientY } : null; };
    const onUp = (e) => {
      const d = down; down = null; if (e.button !== 0 || !d || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) return;
      e.preventDefault(); e.stopPropagation();
      const r = dom.getBoundingClientRect(), ndc = new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      const rc = new T.Raycaster(); rc.setFromCamera(ndc, L.camera);
      const hit = rc.intersectObjects(L.scene.children, true).find((h) => h.object.isMesh && h.object.visible && h.face && !h.object.userData?.vbSignPreview);
      if (!hit) return done(null);
      const n = hit.face.normal.clone().transformDirection(hit.object.matrixWorld);
      const f = L.factor || 1000, pxPerFt = canvas.dimensions.distancePixels;
      done({ x: hit.point.x * f, y: hit.point.z * f, heightFt: (hit.point.y * f) / pxPerFt, normal: { x: n.x, y: n.z }, ny: n.y });
    };
    dom.addEventListener("pointerdown", onDown, true); dom.addEventListener("pointerup", onUp, true); window.addEventListener("keydown", onKey, true);
  });
}
function pickSignTile() {
  return new Promise((resolve) => {
    const dom = L?.renderer?.domElement; if (!dom) return resolve(null);
    const T = L.THREE; let down = null; ui.notifications.info("Sign maker: click a sign. Esc cancels.");
    const done = (v) => { dom.removeEventListener("pointerdown", onDown, true); dom.removeEventListener("pointerup", onUp, true); window.removeEventListener("keydown", onKey, true); resolve(v); };
    const onKey = (e) => { if (e.key === "Escape") done(null); };
    const onDown = (e) => { down = e.button === 0 ? { x: e.clientX, y: e.clientY } : null; };
    const onUp = (e) => {
      const d = down; down = null; if (e.button !== 0 || !d || Math.hypot(e.clientX - d.x, e.clientY - d.y) > 5) return; e.preventDefault(); e.stopPropagation();
      const r = dom.getBoundingClientRect(), rc = new T.Raycaster(); rc.setFromCamera(new T.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), L.camera);
      const meshes = signTiles().map((t) => L.tiles[t.id]?.mesh).filter(Boolean), h = rc.intersectObjects(meshes, true)[0];
      if (!h) return done(null);
      const id = Object.keys(L.tiles).find((k) => { let o = h.object; while (o) { if (o === L.tiles[k].mesh) return true; o = o.parent; } return false; });
      done(id ? canvas.scene.tiles.get(id) : null);
    };
    dom.addEventListener("pointerdown", onDown, true); dom.addEventListener("pointerup", onUp, true); window.addEventListener("keydown", onKey, true);
  });
}

async function placeClick(raw) {
  const sign = core.normalize(raw, DATA), style = styles[sign.style], hit = await pickPoint(style.mount === "wall");
  if (!hit) return null;
  if (style.mount === "wall") {
    if (Math.abs(hit.ny) > 0.6) { ui.notifications.warn("That is the ground or a roof: click a WALL for this style."); return null; }
    const nl = Math.hypot(hit.normal.x, hit.normal.y) || 1, nrm = { x: hit.normal.x / nl, y: hit.normal.y / nl };
    const rot = core.rotationFor(style.outward, nrm), off = 0.4;                               // 0.4 px: just proud of the wall
    const mountFt = Math.max(0, Math.round((hit.heightFt - styles[sign.style].size_m[2] * sign.size * 3.2808 * 0.5) * 10) / 10);
    return createSign({ ...raw, mountFt }, { x: hit.x + nrm.x * off, y: hit.y + nrm.y * off }, { rotation: rot });
  }
  return createSign(raw, { x: Math.round(hit.x), y: Math.round(hit.y) }, { rotation: Number(raw.rotation) || 0 });
}
async function placeAtToken(raw) {
  const tk = canvas.tokens?.controlled?.[0], c = canvas.dimensions;
  const pos = tk ? { x: tk.document.x + (tk.document.width * canvas.grid.size) / 2, y: tk.document.y + (tk.document.height * canvas.grid.size) / 2 } : { x: c.sceneRect.x + c.sceneRect.width / 2, y: c.sceneRect.y + c.sceneRect.height / 2 };
  return createSign(raw, pos, { rotation: Number(raw.rotation) || 0 });
}

// ---------------------------------------------------------------- dialog
function thumb(c, key, W) {
  const k = key, ink = "#2b2b2e", wood = "#8a6a44", dark = "#4a3422", paint = "#2a5a3c";
  c.clearRect(0, 0, W, W); c.save(); c.translate(W / 2, W / 2); const u = W / 100; c.scale(u, u); c.translate(-50, -50);
  const rect = (x, y, w, h, f) => { c.fillStyle = f; c.fillRect(x, y, w, h); };
  if (k === "street_post") { rect(46, 12, 8, 84, dark); rect(30, 28, 40, 14, paint); c.strokeStyle = "#d8c88a"; c.strokeRect(31.5, 29.5, 37, 11); rect(44, 8, 12, 5, dark); }
  else if (k === "street_wall") { rect(10, 8, 80, 84, "#9d9a8e"); rect(18, 40, 64, 20, paint); c.strokeStyle = "#d8c88a"; c.strokeRect(19.5, 41.5, 61, 17); rect(22, 49, 2, 2, ink); rect(76, 49, 2, 2, ink); }
  else if (k.startsWith("fingerpost")) { const n = +k.slice(-1); rect(46, 6, 8, 90, dark); for (let i = 0; i < n; i++) { const y = 14 + i * 16, d = i % 2 ? -1 : 1; c.fillStyle = paint; c.beginPath(); if (d > 0) { c.moveTo(50, y); c.lineTo(78, y); c.lineTo(88, y + 6); c.lineTo(78, y + 12); c.lineTo(50, y + 12); } else { c.moveTo(50, y); c.lineTo(22, y); c.lineTo(12, y + 6); c.lineTo(22, y + 12); c.lineTo(50, y + 12); } c.closePath(); c.fill(); } }
  else if (k === "hanging_bracket") { rect(8, 8, 5, 52, "#777"); rect(13, 14, 74, 3, ink); c.strokeStyle = ink; c.beginPath(); c.moveTo(13, 52); c.lineTo(52, 17); c.lineWidth = 2; c.stroke(); c.lineWidth = 1; for (const x of [34, 70]) { c.strokeStyle = ink; c.beginPath(); c.moveTo(x, 17); c.lineTo(x, 34); c.stroke(); } rect(28, 34, 48, 40, paint); c.strokeStyle = "#d8c88a"; c.strokeRect(30, 36, 44, 36); c.save(); c.translate(52, 55); c.scale(11, 11); ICONS.mug(c, "#d8c88a", paint); c.restore(); }
  else if (k === "hanging_post") { rect(14, 8, 7, 88, dark); rect(21, 14, 62, 6, dark); c.strokeStyle = dark; c.lineWidth = 3; c.beginPath(); c.moveTo(21, 46); c.lineTo(48, 20); c.stroke(); c.lineWidth = 1; for (const x of [48, 76]) { c.strokeStyle = ink; c.beginPath(); c.moveTo(x, 20); c.lineTo(x, 32); c.stroke(); } rect(40, 32, 44, 38, paint); c.strokeStyle = "#d8c88a"; c.strokeRect(42, 34, 40, 34); }
  c.restore();
}

function injectCss() {
  let st = document.getElementById("vbs-css"); if (!st) { st = document.createElement("style"); st.id = "vbs-css"; document.head.appendChild(st); }
  st.textContent = `.vbs{display:grid;grid-template-columns:230px 1fr;gap:10px;font-size:13px;max-height:74vh;overflow:auto}
  .vbs h4{margin:6px 0 3px;border-bottom:1px solid #8886}
  .vbs .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:6px}
  .vbs .st{border:2px solid #8886;border-radius:6px;padding:3px;text-align:center;cursor:pointer;font-size:11px;line-height:1.1;background:#0002}
  .vbs .st.on{border-color:#e0a030;background:#e0a03033}
  .vbs .st canvas,.vbs .th canvas{width:84px;height:84px;display:block;margin:0 auto 2px}
  .vbs label{display:flex !important;flex-direction:row !important;gap:6px;align-items:center;margin:2px 0}.vbs label>span{flex:0 0 96px}
  .vbs input[type=text],.vbs input[type=range],.vbs select,.vbs textarea,.vbs input[type=number]{flex:1;min-width:0}
  .vbs textarea{height:70px;font-family:inherit}
  .vbs .arm{border:1px dashed #8886;padding:3px;margin:3px 0}.vbs .arm textarea{height:42px}
  .vbs canvas.prev{width:100%;max-height:230px;object-fit:contain;background:#222;border:1px solid #8886;margin-top:4px}
  .vbs .note{font-size:11px;opacity:.75}`;
}

function dialogHTML(state, fonts) {
  const sk = Object.keys(styles), sc = presets.schemes;
  const opt = (arr, sel) => arr.map(([v, l]) => `<option value="${v}"${String(v) === String(sel) ? " selected" : ""}>${foundry.utils.escapeHTML ? foundry.utils.escapeHTML(l) : l}</option>`).join("");
  const sg = signTiles().map((t) => [t.id, `${core.summary(signOf(t))}  (${styles[signOf(t).style]?.label || "?"})`]);
  const ctrl = canvas.tiles?.controlled?.find((t) => signOf(t.document))?.document.id;
  injectCss();
  return `<div class="vbs">
  <div><h4>Style</h4><div class="grid" id="vbs-styles">${sk.map((k) => `<div class="st" data-style="${k}"><div class="th" data-thumb="${k}"></div>${styles[k].label}</div>`).join("")}</div>
  <h4>Preview</h4><div id="vbs-prevhost"></div>
  <div class="note">Street boards and plaques have a back (same text, blank, or its own). Wall styles: click a wall to place.</div></div>
  <div>
   <label><span>Sign in scene</span><select name="existing"><option value="">New sign</option>${opt(sg, ctrl || "")}</select><button type="button" data-act="pick" title="Click a sign in the 3D view">Pick</button></label>
   <h4>Text</h4>
   <label><span>Text</span><textarea name="text" maxlength="${presets.limits.maxText}" placeholder="One line per row"></textarea></label>
   <div id="vbs-arms"></div>
   <label><span>Line sizes</span><select name="lineStyle">${opt([["equal", "All lines equal"], ["subtitle", "First line big, others smaller"]], state.lineStyle)}</select></label>
   <label><span>Font</span><select name="font">${fonts.map((f) => `<option value="${f.name}"${f.name === state.font ? " selected" : ""}>${f.name} (${f.note})</option>`).join("")}</select></label>
   <label><span>Own font</span><input type="text" name="fontCustom" placeholder="any installed / Foundry font family"></label>
   <label><span>Finish</span><select name="finish">${opt([["painted", "Painted"], ["carved", "Carved"], ["gilt", "Gilt"]], state.finish)}</select></label>
   <label><span>Colours</span><select name="scheme">${opt(Object.entries(sc).map(([k, v]) => [k, v.label]), state.scheme)}</select></label>
   <label><span>Custom</span>board <input type="color" name="paint" value="${state.paint || "#254a33"}"> ink <input type="color" name="ink" value="${state.ink}"> trim <input type="color" name="trim" value="${state.trim}"></label>
   <label><span>Icon</span><select name="icon">${presets.icons.map((i) => `<option value="${i}"${i === state.icon ? " selected" : ""}>${i}</option>`).join("")}</select>
     <select name="iconPos">${opt([["top", "above text"], ["left", "left of text"]], state.iconPos === "left" ? "left" : "top")}</select></label>
   <label><span>Back side</span><select name="back">${opt([["same", "same as front"], ["blank", "blank board"], ["text", "own text"]], state.back)}</select><input type="text" name="backText" placeholder="back text"></label>
   <h4>Size and place</h4>
   <label><span>Size x</span><input type="range" name="size" min="${presets.limits.sizeMin}" max="${presets.limits.sizeMax}" step="0.05" value="${state.size}"><output name="sizeOut">${state.size}</output></label>
   <label><span>Letter spacing</span><input type="range" name="spacing" min="0" max="0.2" step="0.005" value="${state.spacing}"></label>
   <label><span>Weathering</span><input type="range" name="weather" min="0" max="1" step="0.05" value="${state.weather}"></label>
   <label><span>Mount height ft</span><input type="number" name="mountFt" min="0" max="200" step="0.5" value="${state.mountFt}"><span class="note">wall styles; wall clicks use the click height</span></label>
   <label><span>Rotation deg</span><input type="number" name="rotation" min="0" max="359" step="5" value="0"><span class="note">ground styles; wall clicks set it</span></label>
   <label><span>Texture px</span><select name="quality">${opt([[512, "512 (small)"], [1024, "1024"], [2048, "2048 (sharp close-ups)"]], state.quality)}</select></label>
  </div></div>`;
}

async function openDialog() {
  const fonts = fontList(), data = DATA;
  let styleKey = Object.keys(styles)[0];
  const ctrlTile = canvas.tiles?.controlled?.map((t) => t.document).find((d) => signOf(d));
  const initial = ctrlTile ? signOf(ctrlTile) : null;
  if (initial?.style) styleKey = initial.style;
  const state0 = core.normalize({ style: styleKey, ...(initial || {}) }, data);
  const DialogV2 = foundry.applications.api.DialogV2;
  const form = (d) => d.element.querySelector("form");
  let chosen = ctrlTile?.id || "";
  const readRaw = (el) => {
    const f = new FormData(el), g = (n) => f.get(n);
    const arms = [...el.querySelectorAll(".arm")].map((a) => ({ text: a.querySelector("textarea").value, dir: +a.querySelector("select").value, yaw: +a.querySelector("input").value || 0 }));
    return { style: el.dataset.style, text: g("text"), lineStyle: g("lineStyle"), font: (g("fontCustom") || "").trim() || g("font"), finish: g("finish"), scheme: g("scheme"), paint: g("paint"), ink: g("ink"), trim: g("trim"),
      icon: g("icon"), iconPos: g("iconPos"), back: g("back"), backText: g("backText"), size: +g("size"), spacing: +g("spacing"), weather: +g("weather"), mountFt: +g("mountFt"), rotation: +g("rotation"), quality: +g("quality"), arms };
  };
  const setForm = (el, s) => {
    const set = (n, v) => { const e = el.elements[n]; if (e && v !== undefined) e.value = v; };
    el.dataset.style = s.style; set("text", s.text); set("lineStyle", s.lineStyle); set("scheme", s.scheme); set("finish", s.finish); set("icon", s.icon); set("iconPos", s.iconPos === "none" ? "top" : s.iconPos);
    set("back", s.back); set("backText", s.backText); set("size", s.size); set("spacing", s.spacing); set("weather", s.weather); set("mountFt", s.mountFt); set("quality", s.quality);
    set("paint", s.paint || "#254a33"); set("ink", s.ink); set("trim", s.trim);
    const known = [...el.elements.font.options].some((o) => o.value === s.font); set("font", known ? s.font : el.elements.font.options[0].value); set("fontCustom", known ? "" : s.font);
    el.querySelectorAll(".st").forEach((n) => n.classList.toggle("on", n.dataset.style === s.style)); buildArms(el, s);
  };
  const buildArms = (el, s) => {
    const host = el.querySelector("#vbs-arms"), st = styles[el.dataset.style], n = st.arms || 0;
    el.elements.text.closest("label").style.display = n ? "none" : "flex"; el.elements.back.closest("label").style.display = n ? "none" : "flex"; el.elements.backText.style.display = n ? "none" : "";
    const sg = core.normalize({ ...s, style: el.dataset.style }, data);
    host.innerHTML = n ? sg.arms.map((a, i) => `<div class="arm"><b>Arm ${i + 1}</b> <textarea maxlength="120">${(a.text || "").replace(/</g, "&lt;")}</textarea><label><span>Points</span><select><option value="1"${a.dir === 1 ? " selected" : ""}>right</option><option value="-1"${a.dir === -1 ? " selected" : ""}>left</option></select> turn deg <input type="number" min="-60" max="60" step="5" value="${a.yaw}"></label></div>`).join("") : "";
  };
  let timer = null;
  const preview = async (el) => {
    const raw = readRaw(el), sign = core.normalize({ ...raw, quality: 512, seed: "preview" }, data), st = styles[sign.style];
    try {
      await document.fonts.load(`40px ${fontStack(sign.font)}`).catch(() => {});
      const imgs = await baseImages(), rnd = core.rng("preview"), pans = core.panels(sign, st).filter((p) => p.id === "f" || /^a\dF?f$/.test(p.id) || p.id.endsWith("f"));
      const cvs = pans.map((p) => renderPanel(sign, p, imgs, core.rng("preview")));
      const W = Math.max(...cvs.map((c) => c.width)), H = cvs.reduce((a, c) => a + c.height + 6, 0), out = el.querySelector("#vbs-prev"); out.width = W; out.height = H;
      const o = out.getContext("2d"); o.clearRect(0, 0, W, H); let y = 0; for (const c of cvs) { o.drawImage(c, 0, y); y += c.height + 6; }
    } catch (e) { console.warn("sign preview", e); }
  };
  const schedule = (el) => { clearTimeout(timer); timer = setTimeout(() => preview(el), 180); };
  const act = async (name, d) => {
    const el = form(d), raw = readRaw(el);
    const tile = (el.elements.existing.value ? canvas.scene.tiles.get(el.elements.existing.value) : null) || null;
    if (name === "place") { d.close(); await placeClick(raw); }
    else if (name === "token") { d.close(); await placeAtToken(raw); }
    else if (name === "apply") {
      if (!tile) return ui.notifications.warn("Choose a sign in the list (or Pick one) first; Place makes a new one.");
      d.close(); await updateSign(tile, { ...raw }, { rotation: tile.rotation });
    } else if (name === "delete") {
      if (!tile) return ui.notifications.warn("Choose a sign first.");
      await canvas.scene.deleteEmbeddedDocuments("Tile", [tile.id]); ui.notifications.info("Sign deleted."); d.close();
    } else if (name === "rebuild") {
      d.close(); let n = 0; for (const t of signTiles()) { await updateSign(t, signOf(t), { rotation: t.rotation }); n++; } ui.notifications.info(`Rebuilt ${n} sign(s).`);
    }
  };
  const dlg = new DialogV2({
    window: { title: "Sign maker", resizable: true }, position: { width: 820 },
    content: dialogHTML(state0, fonts),
    buttons: [
      { action: "place", label: "Place (click in scene)", default: true, callback: (e, b, d) => { act("place", d); return false; } },
      { action: "token", label: "Place at selected token", callback: (e, b, d) => { act("token", d); return false; } },
      { action: "apply", label: "Apply to chosen sign", callback: (e, b, d) => { act("apply", d); return false; } },
      { action: "delete", label: "Delete chosen sign", callback: (e, b, d) => { act("delete", d); return false; } },
      { action: "rebuild", label: "Rebuild all signs", callback: (e, b, d) => { act("rebuild", d); return false; } },
      { action: "close", label: "Close" },
    ],
    submit: () => {},
  });
  root.__vbSignDialog = dlg;
  dlg.addEventListener?.("close", () => { delete root.__vbSignDialog; });
  const origRender = dlg._onRender?.bind(dlg);
  dlg._onRender = async function (ctx, opts) {
    if (origRender) await origRender(ctx, opts);
    const el = this.element.querySelector("form"); if (!el || el.dataset.ready) return; el.dataset.ready = "1";
    el.querySelectorAll(".th").forEach((h) => { const c = document.createElement("canvas"); c.width = c.height = 168; h.appendChild(c); thumb(c.getContext("2d"), h.dataset.thumb, 168); });
    { const c = document.createElement("canvas"); c.className = "prev"; c.id = "vbs-prev"; el.querySelector("#vbs-prevhost").appendChild(c); }
    el.querySelectorAll(".st").forEach((n) => n.addEventListener("click", () => { const cur = readRaw(el); el.dataset.style = n.dataset.style; const s = core.normalize({ ...cur, style: n.dataset.style, mountFt: undefined, arms: undefined }, data); setForm(el, { ...s, font: cur.font }); schedule(el); }));
    el.addEventListener("input", () => { const o = el.elements.sizeOut; if (o) o.value = el.elements.size.value; schedule(el); });
    el.elements.existing.addEventListener("change", () => { const t = canvas.scene.tiles.get(el.elements.existing.value); if (t) { const s = signOf(t); setForm(el, core.normalize(s, data)); el.elements.rotation.value = Math.round(t.rotation); } schedule(el); });
    el.querySelector("[data-act=pick]").addEventListener("click", async () => { this.minimize?.(); const t = await pickSignTile(); this.maximize?.(); if (t) { el.elements.existing.value = t.id; el.elements.existing.dispatchEvent(new Event("change")); } });
    el.dataset.style = state0.style; setForm(el, state0); if (initial) { el.elements.rotation.value = Math.round(ctrlTile.rotation); el.elements.existing.value = chosen; }
    schedule(el);
  };
  dlg.render({ force: true });
}

root.__vbSignMaker = { core, createSign, updateSign, placeAtToken, placeClick, pickPoint, renderPanel, paintAll, DATA };
await openDialog();
