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
const srcs = [...html.matchAll(/<script src="([^"]+)"/g)].map(m => m[1]);
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
console.log(pass + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
