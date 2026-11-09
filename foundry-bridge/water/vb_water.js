// Varrenmoor 3D water for 3D Canvas (levels-3d-preview 9.x, three.js r132). VERSION 2
//
// This file is the BODY of a tile "onAnimation" function: new Function("delta", <this file>). 3D Canvas runs that function every frame for a tile that has
// the flag flags.levels-3d-preview.onAnimation (scene flag enableAnimationScripts, default on), with `this` = the first child of the tile's model once the
// model has loaded (before that `this` is the Tile3D: ignored). foundry_push.py install-water writes the body into the flag of every water tile; nothing is
// installed in Foundry itself, and players run it too because it travels in the tile document.
//
// What it does (once per tile, then one uniform write per frame): finds the meshes whose material name starts with "VB_water_" (river / pond / lake / ocean,
// exported by worldpack_water.py), gives each its own copy of the material and patches it with onBeforeCompile (the standard lit three.js material is kept: sun,
// shadows, environment reflections, fog and tone mapping all still apply). The patch adds
//   - procedural light waves (4 layers of travelling sines, analytic normals, no texture),
//   - flow: a river scrolls along its channel (UV v = downstream), faster on steeper stretches; a pond / lake / ocean drifts with the wind direction,
//   - transparency that is clearer at the banks, depth tint away from the bank, a fresnel opacity lift, shore foam (and crest foam on the ocean).
// Per-vertex data comes from the glTF attribute _VBWATER (x shore 0..1, y slope 0..1, z heading/360, w 0.5 marker).
// Parameters: tile flag flags.varrenmoor.water = {v, force, presets: {river: {...}, lake: {...}}} (edited live by foundry_push.py set-water); without it the
// node extras (userData.vbWater, written by the export) are used. Parameter names: see presets/water/presets.json.
const L = game && game.Levels3DPreview, T = L && L.THREE;
const root = this && this.isObject3D ? this.parent : null;
if (!T || !root) return;
let S = root.userData.vbWaterState;
if (S === undefined) {
  S = root.userData.vbWaterState = { meshes: [], frame: 0, key: "", t0: performance.now(), tile: null, ok: true };
  try {
    const VERT_PARS = "#include <common>\nattribute vec4 _vbwater;\nvarying vec2 vbUv;\nvarying vec4 vbData;";
    const FRAG_PARS = [
      "uniform float vbTime; uniform float vbMode; uniform vec4 vbP0; uniform vec4 vbP1; uniform vec3 vbShallow; uniform vec3 vbDeep;",
      "varying vec2 vbUv; varying vec4 vbData;",
      "float vbHash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }",
      "float vbNoise(vec2 p){ vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);",
      "  return mix(mix(vbHash(i), vbHash(i + vec2(1.0, 0.0)), f.x), mix(vbHash(i + vec2(0.0, 1.0)), vbHash(i + vec2(1.0, 1.0)), f.x), f.y); }",
      "vec2 vbRot(vec2 d, float a){ float c = cos(a); float s = sin(a); return vec2(d.x * c - d.y * s, d.x * s + d.y * c); }",
      // one travelling sine layer: returns (height, d height / du, d height / dv); amplitude is a fraction of the wavelength, so slopes do not depend on scale
      "vec3 vbLayer(vec2 p, vec2 dir, float len, float w, float ph){ float k = 6.2831853 / len; float a = dot(dir, p) * k + ph; float amp = 0.02 * len * w;",
      "  return vec3(amp * sin(a), dir * (amp * k * cos(a))); }",
      // stretch > 1 elongates the ripples along the flow (river streaks); the returned gradient is with respect to the unstretched p
      "vec3 vbPattern(vec2 p, vec2 d, float len, float t, float str){",
      "  vec2 ps = vec2(p.x, p.y / str);",
      "  vec2 q = ps + len * 0.35 * vec2(sin(ps.y / len * 1.9 + 1.3), cos(ps.x / len * 1.6 + 0.7));",
      "  vec3 s = vbLayer(q, d, len, 1.0, t * 0.9);",
      "  s += vbLayer(q, vbRot(d, 0.62), len * 0.62, 0.6, 1.7 + t * 1.2);",
      "  s += vbLayer(q, vbRot(d, -0.85), len * 0.43, 0.38, 3.1 + t * 1.5);",
      "  s += vbLayer(q, vbRot(d, 1.3), len * 0.27, 0.22, 4.9 + t * 1.9);",
      "  return vec3(s.x, s.y, s.z / str); }",
      // thin ridge lines of a noise field, stretched along the flow: they translate with the water and read as travelling streaks
      "float vbStreak(vec2 p, float len){ float n = vbNoise(vec2(p.x / (len * 0.45), p.y / (len * 3.2))); float r = 1.0 - abs(2.0 * n - 1.0); return smoothstep(0.80, 0.97, r); }",
      "vec3 vbPerturb(vec3 eye_pos, vec3 surf_norm, vec3 mapN, float faceDirection){",
      "  vec3 q0 = dFdx(eye_pos); vec3 q1 = dFdy(eye_pos); vec2 st0 = dFdx(vbUv); vec2 st1 = dFdy(vbUv); vec3 N = surf_norm;",
      "  vec3 q1perp = cross(q1, N); vec3 q0perp = cross(N, q0); vec3 T = q1perp * st0.x + q0perp * st1.x; vec3 B = q1perp * st0.y + q0perp * st1.y;",
      "  float det = max(dot(T, T), dot(B, B)); float scale = faceDirection * inversesqrt(max(det, 1e-12));",
      "  return normalize(T * (mapN.x * scale) + B * (mapN.y * scale) + N * mapN.z); }"
    ].join("\n");
    const COLOR_FRAG = [
      "vec4 vbD = abs(vbData.w - 0.5) < 0.01 ? vbData : vec4(1.0, 0.0, 0.5, 0.5);",         // no _VBWATER data: open water, no slope, heading 180
      "float vbSh = vbD.x; float vbSlope = vbD.y;",
      "float vbEnd = vbData.w > 0.49 && vbData.w < 0.76 ? clamp((vbData.w - 0.5) * 4.0, 0.0, 1.0) : 0.0;",   // river end fade: 1 = invisible
      "float vbSpd = vbP0.x * mix(1.0, 0.75 + 1.0 * vbSlope, vbP1.z);",
      "float vbLen = max(vbP0.z, 0.01); float vbWH = vbP0.y; float vbFoamAmt = vbP0.w;",
      "vec2 vbDir = vbMode < 0.5 ? vec2(0.0, 1.0) : vbRot(vec2(0.0, 1.0), vbP1.w - vbD.z * 6.2831853);",
      "vec3 vbW; float vbStrk = 0.0;",
      "if (vbMode < 0.5) {",                                                                    // river: two-phase flow; both phases are the SAME pattern, translated by speed * cycle * phase, so it travels downstream instead of cross-fading in place
      "  float cyc = 4.0; float ph0 = fract(vbTime / cyc); float ph1 = fract(vbTime / cyc + 0.5);",
      "  float w0 = 1.0 - abs(2.0 * ph0 - 1.0); float w1 = 1.0 - abs(2.0 * ph1 - 1.0);",
      "  vec2 p0 = vbUv - vbDir * vbSpd * cyc * ph0; vec2 p1 = vbUv - vbDir * vbSpd * cyc * ph1 + vec2(0.37, 0.21);",
      "  vbW = w0 * vbPattern(p0, vbDir, vbLen, vbTime * 0.3, 3.0) + w1 * vbPattern(p1, vbDir, vbLen, vbTime * 0.3, 3.0);",
      "  vbStrk = w0 * vbStreak(p0, vbLen) + w1 * vbStreak(p1 + vec2(1.7, 0.0), vbLen);",
      "} else {",
      "  vbW = vbPattern(vbUv - vbDir * vbSpd * vbTime, vbDir, vbLen, vbTime, 1.0);",
      "}",
      "vec2 vbGrad = vbW.yz * vbWH;",
      "float vbHn = clamp(vbW.x / (0.02 * vbLen * 2.2) * 0.5 + 0.5, 0.0, 1.0);",
      "float vbNz = vbNoise(vbUv / (vbLen * 0.6) + vec2(vbTime * 0.15, -vbTime * 0.1));",
      "float vbBand = 1.0 - smoothstep(0.0, 0.25 + 0.45 * vbFoamAmt, vbSh);",
      "float vbFoam = vbFoamAmt * vbBand * smoothstep(0.25, 0.75, vbNz + vbBand * 0.5);",
      "vbFoam += vbFoamAmt * smoothstep(0.7, 1.0, vbHn) * clamp(vbWH, 0.0, 1.0) * (vbMode < 0.5 ? 0.3 : 0.6) * smoothstep(0.3, 0.9, vbNz);",
      "vbFoam += vbFoamAmt * vbSlope * vbSlope * 0.6 * smoothstep(0.55, 0.85, vbNz);",
      "vbFoam = clamp(vbFoam, 0.0, 1.0);",
      "float vbShine = vbMode < 0.5 ? vbStrk * (0.5 + 0.5 * vbHn) : 0.0;",
      "vec3 vbCol = mix(vbShallow, vbDeep, vbP1.y * smoothstep(0.0, 0.9, vbSh));",
      "vbCol *= 0.88 + 0.24 * vbHn;",                                                           // crests lighter, troughs darker: visible from straight above
      "diffuseColor.rgb = mix(mix(vbCol, vec3(0.80, 0.93, 0.97), clamp(vbShine * 0.55 * (0.4 + vbWH), 0.0, 0.7)), vec3(0.93, 0.96, 0.98), vbFoam * (1.0 - vbEnd));",
      "float vbAlpha = mix(1.0 - 0.85 * vbP1.x, 1.0 - 0.55 * vbP1.x, smoothstep(0.0, 0.8, vbSh));",
      "vbAlpha = mix(max(vbAlpha, 0.12), 1.0, vbFoam);",
      "vbAlpha = mix(vbAlpha, max(vbAlpha, 0.8), vbShine * 0.5);"
    ].join("\n");
    const NORMAL_FRAG = "vec3 vbMapN = normalize(vec3(-vbGrad, 1.0));\nnormal = vbPerturb(-vViewPosition, normal, vbMapN, faceDirection);";
    const ALPHA_FRAG = "float vbFres = pow(1.0 - clamp(dot(normal, normalize(vViewPosition)), 0.0, 1.0), 4.0);\ndiffuseColor.a = clamp(mix(vbAlpha, 1.0, vbFres * 0.7), 0.0, 1.0) * (1.0 - smoothstep(0.0, 0.9, vbEnd));\n#include <output_fragment>";
    S.patch = function (mesh, uniforms) {
      const mat = (mesh.material = mesh.material.clone());
      mat.transparent = true;
      mat.depthWrite = false;
      mat.side = T.DoubleSide;
      mat.onBeforeCompile = function (sh) {
        Object.assign(sh.uniforms, uniforms);
        sh.vertexShader = sh.vertexShader.replace("#include <common>", VERT_PARS).replace("#include <begin_vertex>", "#include <begin_vertex>\nvbUv = uv; vbData = _vbwater;");
        sh.fragmentShader = sh.fragmentShader.replace("#include <normalmap_pars_fragment>", "#include <normalmap_pars_fragment>\n" + FRAG_PARS)
          .replace("#include <color_fragment>", COLOR_FRAG)
          .replace("#include <roughnessmap_fragment>", "#include <roughnessmap_fragment>\nroughnessFactor = mix(roughnessFactor, 0.6, vbFoam);")
          .replace("#include <normal_fragment_maps>", NORMAL_FRAG)
          .replace("#include <output_fragment>", ALPHA_FRAG);
      };
      mat.customProgramCacheKey = function () { return "vbwater2"; };
      mat.needsUpdate = true;
      mesh.castShadow = false;
    };
  } catch (e) { S.ok = false; console.error("vb_water: setup failed", e); }
}
if (!S.ok) return;
S.frame++;
if (!S.tile) S.tile = Object.values(L.tiles || {}).find(function (t) { return t && t.mesh === root; }) || null;
if (S.frame === 1 || S.frame % 30 === 0) {
  const doc = S.tile && S.tile.tile && S.tile.tile.document;
  const cfg = doc && doc.flags && doc.flags.varrenmoor && doc.flags.varrenmoor.water;
  if (!S.meshes.length && S.frame === 1) {
    root.traverse(function (o) {
      if (o.isMesh && o.material && /^VB_water_/.test(o.material.name || "")) {
        const U = { vbTime: { value: 0 }, vbMode: { value: 0 }, vbP0: { value: new T.Vector4() }, vbP1: { value: new T.Vector4() }, vbShallow: { value: new T.Color() }, vbDeep: { value: new T.Color() } };
        const preset = o.material.name.slice(9);
        const ex = o.userData.vbWater || (o.parent && o.parent.userData.vbWater) || {};
        S.meshes.push({ mesh: o, U: U, preset: preset, extras: ex, key: "" });
        S.patch(o, U);
      }
    });
  }
  const key = JSON.stringify(cfg || null);
  if (key !== S.key) {
    S.key = key;
    S.meshes.forEach(function (m) {
      const pr = (cfg && cfg.force) || m.preset;
      const p = Object.assign({}, m.extras, cfg && cfg.presets && cfg.presets[pr] || {});
      const n = function (v, d) { v = Number(v); return isFinite(v) ? v : d; };
      m.U.vbP0.value.set(n(p.flow_speed, 0.3) / 10, n(p.wave_height, 0.4), n(p.wave_scale, 1) * 0.4, n(p.foam, 0.1));
      m.U.vbP1.value.set(n(p.transparency, 0.5), n(p.depth_tint, 0.6), n(p.slope_speed, 0), n(p.wind_dir, 0) * Math.PI / 180);
      m.U.vbMode.value = p.mode === "flow" ? 0 : 1;
      m.U.vbShallow.value.set(p.shallow_color || "#5c9bb5").convertSRGBToLinear();                 // the renderer outputs sRGB
      m.U.vbDeep.value.set(p.deep_color || "#1a4a6e").convertSRGBToLinear();
    });
  }
}
const t = (performance.now() - S.t0) / 1000;
for (let i = 0; i < S.meshes.length; i++) S.meshes[i].U.vbTime.value = t;
