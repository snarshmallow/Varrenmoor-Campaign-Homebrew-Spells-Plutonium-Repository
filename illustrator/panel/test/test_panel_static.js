// Static load-safety audit: every panel script and host.jsx parses, index.html script tags resolve, ids are unique,
// no blocking dialogs (CEP confirm/alert are unreliable), static getElementById targets exist.
const fs = require("fs"), path = require("path"), vm = require("vm");
const P = path.resolve(__dirname, "..");
let pass = 0, fail = 0;
const check = (n, ok, d) => { if (ok) { pass++; console.log("PASS " + n); } else { fail++; console.log("FAIL " + n + (d ? ": " + d : "")); } };
const files = [];
for (const dir of [P, P + "/lib"]) fs.readdirSync(dir).filter(f => f.endsWith(".js")).forEach(f => files.push(path.join(dir, f)));
files.push(P + "/jsx/host.jsx");
for (const f of files) { try { new vm.Script(fs.readFileSync(f, "utf8"), { filename: f }); check("parses " + path.relative(P, f), true); } catch (e) { check("parses " + path.relative(P, f), false, e.message); } }
const html = fs.readFileSync(P + "/index.html", "utf8");
// scripts are written by the loader at the top of the script block (cache-busting ?v= query), from one list
const loader = /var files = \[([^\]]*)\];[\s\S]*?document\.write\('<script src="' \+ files\[i\] \+ '\?v=' \+ v/.exec(html);
check("index.html has the cache-busting script loader", !!loader);
const srcs = loader ? [...loader[1].matchAll(/"([^"]+)"/g)].map(m => m[1]) : [];
check("no plain <script src> tags bypass the loader", !/^\s*<script src=/m.test(html));
check("loader lists version.js and version_ui.js before main.js, main.js last", srcs.indexOf("lib/version.js") > 0 && srcs.indexOf("version_ui.js") > srcs.indexOf("lib/version.js") && srcs[srcs.length - 1] === "main.js" && srcs.indexOf("version_ui.js") < srcs.length - 1);
const allJs = fs.readdirSync(P).filter(f => f.endsWith("_ui.js") || f === "main.js").concat(fs.readdirSync(P + "/lib").filter(f => f.endsWith(".js")).map(f => "lib/" + f));
check("every panel script is in the loader list", allJs.every(f => srcs.includes(f)), allJs.filter(f => !srcs.includes(f)).join(", "));
check("reload button, version text and badge exist", ["reloadPanel", "verText", "verDot"].every(i => html.includes('id="' + i + '"')));
check("main.js wires VBVersionUI init and afterInit", /VBVersionUI\.init\(/.test(fs.readFileSync(P + "/main.js", "utf8")) && /VBVersionUI\.afterInit\(\)/.test(fs.readFileSync(P + "/main.js", "utf8")));
check("script tags resolve", srcs.every(s => fs.existsSync(path.join(P, s))), srcs.filter(s => !fs.existsSync(path.join(P, s))).join(", "));
const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(m => m[1]);
check("no duplicate element ids", new Set(ids).size === ids.length, ids.filter((x, i) => ids.indexOf(x) !== i).join(", "));
for (const f of ["heightpaint_ui.js", "main.js"]) {
  const t = fs.readFileSync(P + "/" + f, "utf8");
  const miss = [...t.matchAll(/\$\("([A-Za-z0-9_-]+)"\)/g)].map(m => m[1]).filter(i => !ids.includes(i));
  check(f + ": static $(id) targets exist in index.html", !miss.length, [...new Set(miss)].join(", "));
}
for (const f of files.filter(f => f.endsWith(".js"))) {
  const t = fs.readFileSync(f, "utf8").replace(/\/\/.*$/gm, "");
  check("no confirm/alert/prompt in " + path.relative(P, f), !/\b(window\.)?(confirm|alert|prompt)\(/.test(t));
}
// Paint heightmap lives inside the Terrain tab (no tab of its own)
check("no standalone Paint tab button or section", !/data-tab="hpaint"|id="tab-hpaint"/.test(html));
const terr = html.slice(html.indexOf('<section id="tab-terrain"'), html.indexOf("</section>", html.indexOf('<section id="tab-terrain"')));
check("Paint heightmap is a <details id=hpDetails> inside the Terrain tab", /<details id="hpDetails"/.test(terr) && /id="hpCanvas"/.test(terr) && /data-act="hp_save"/.test(terr));
const hu = fs.readFileSync(P + "/heightpaint_ui.js", "utf8"), mj = fs.readFileSync(P + "/main.js", "utf8");
check("paint shortcuts require Terrain tab on and section open", /code === "Space" && tabOn\(\) && isOpen\(\)/.test(hu) && /ctrlKey \|\| e\.metaKey\) && !e\.altKey && tabOn\(\) && isOpen\(\)/.test(hu));
check("main.js showTab notifies the paint UI and maps the old hpaint tab", /VBHeightPaintUI\.shown\(\)/.test(mj) && /t === "hpaint"/.test(mj));
check("startup jobs are queued", /startJobQueued/.test(fs.readFileSync(P + "/skybox_ui.js", "utf8")) && /function startJobQueued/.test(mj));
// Export section + Profiles (export_ui.js, profiles_ui.js, lib/exportplan.js, lib/profiles.js)
for (const f of ["lib/profiles.js", "lib/exportplan.js", "export_ui.js", "profiles_ui.js"]) {
  check(f + " is in the loader after core.js and before main.js", srcs.indexOf(f) > srcs.indexOf("lib/core.js") && srcs.indexOf(f) < srcs.indexOf("main.js"));
}
check("profiles.js and exportplan.js publish on window even when module exists (CEP)", /window\.VBProfiles = P/.test(fs.readFileSync(P + "/lib/profiles.js", "utf8")) && /window\.VBExportPlan = X/.test(fs.readFileSync(P + "/lib/exportplan.js", "utf8")));
for (const [f, g] of [["export_ui.js", "VBExportUI"], ["profiles_ui.js", "VBProfilesUI"]]) check(f + " publishes window." + g, new RegExp("window\." + g + " = ").test(fs.readFileSync(P + "/" + f, "utf8")));
const exIds = ["exList", "exRun", "exDryAll", "exResume", "exPack", "exPrev", "exArm", "exDry", "exPreview", "exSummary", "exBlock", "exReset", "exRoofHint", "exArmRow", "exPushList", "exPushRun", "exPushAll", "exPushDry", "exPushResume", "exPushBlock", "exPushSummary", "exPushEvery", "exPushNone", "exLast", "exScene"];
check("export section ids exist", exIds.every(i => ids.includes(i)), exIds.filter(i => !ids.includes(i)).join(", "));
const pfIds = ["profQuick", "profInd", "pfList", "pfName", "pfDesc", "pfWhere", "pfScope", "pfLoad", "pfApply", "pfSaveAs", "pfUpdate", "pfRename", "pfDup", "pfDelete", "pfDefault", "pfReset", "pfDiff", "pfFile", "pfBrowse", "pfImport", "pfExport", "pfCopy", "pfMsg", "pfActive", "pfDefLine"];
check("profile ids exist", pfIds.every(i => ids.includes(i)), pfIds.filter(i => !ids.includes(i)).join(", "));
for (const f of ["export_ui.js", "profiles_ui.js"]) {
  const t = fs.readFileSync(P + "/" + f, "utf8"), miss = [...t.matchAll(/\$\("([A-Za-z0-9_-]+)"\)/g)].map(m => m[1]).filter(i => !ids.includes(i) && i !== "exRoofUse");
  check(f + ": static $(id) targets exist in index.html", !miss.length, [...new Set(miss)].join(", "));
}
check("export section is at the top of the Foundry tab (before the bridge section)", html.indexOf('id="exBox"') > html.indexOf('id="tab-foundry"') && html.indexOf('id="exBox"') < html.indexOf("<!-- BRIDGE SECTION"));
check("profile indicator sits in the header next to the version label", html.indexOf('id="profInd"') > 0 && html.indexOf('id="profInd"') < html.indexOf('id="verText"') && html.indexOf('id="profInd"') < html.indexOf('id="err"'));
check("Profiles manager lives in the Tools tab (still 18 static tab buttons; Buildings and Roads are added by script: 20 tabs)", html.indexOf('id="pfBox"') > html.indexOf('id="tab-tools"') && (html.match(/role="tab" data-tab=/g) || []).length === 18);
check("main.js wires VBProfilesUI (before first place) and VBExportUI, default profile for fresh places", /VBProfilesUI\.init\(/.test(mj) && /VBExportUI\.init\(/.test(mj) && /applyDefaultToNew/.test(mj) && mj.indexOf("VBProfilesUI.init(") < mj.indexOf("await switchPlace(cur)") && /VBExportUI\.paint\(\)/.test(mj));
check("real Foundry writes need an explicit arm (checkbox), default dry run", /id="exDry"/.test(html) && /data-s="exp\.dry"/.test(html) && !/id="exArm"[^>]*checked/.test(html));
// defaults audit (what a normal export wants on by default)
{
  const VBc = require("../lib/core.js");
  ["townarea", "regions", "styles", "objects", "lighting", "sun3d", "streetlamps", "foliage", "skybox", "water", "heightpaint", "padding", "bridges", "places", "tools", "bridge", "exportplan", "profiles"].forEach(f => require("../lib/" + f + ".js"));
  const dd = VBc.defaults(), m = dd.foundry.models;
  check("export defaults: prune on, roofs created hidden, scene mode 3d, no compression, merge by layer, lights with the 3D push", m.prune === true && m.roofsHidden === true && m.sceneMode === "3d" && m.compress === "none" && m.preset === "layer" && dd.tools.s3d.with_lights === true && dd.tools.s3d.dry_run === true);
  check("collision on for ground/roads/buildings/fences/bridges, off for roofs/foliage/water; sight on for buildings/walls/foliage", ["terrain", "roads", "buildings", "fences", "bridges"].every(k => m.collision[k]) && !m.collision.roofs && !m.collision.foliage && !m.collision.water && m.sight.buildings && m.sight.walls && m.sight.foliage && !m.sight.roofs);
  check("export checklist default: dry run on, all steps ticked", dd.exp && dd.exp.dry === true && Object.values(dd.exp.sel).every(Boolean) && dd.profile && dd.profile.name === "");
}
console.log(pass + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
