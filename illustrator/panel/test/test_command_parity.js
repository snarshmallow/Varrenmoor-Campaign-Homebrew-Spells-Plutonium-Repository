// Command parity: every CLI command and flag of the Foundry/world-pack tools must be in lib/command_manifest.json, either with the panel control(s) that cover it
// or with an explicit "cli_only" reason. Fails when a command or flag appears in the Python argparse code but not in the manifest (so parity cannot silently regress),
// when a manifest control does not exist in index.html, or when a manifest entry names something the Python no longer has.
//   node illustrator/panel/test/test_command_parity.js          (--list prints the extracted commands and flags)
const fs = require("fs"), path = require("path");
const ROOT = path.resolve(__dirname, "../../..");
const GEN = path.join(ROOT, "illustrator/generators"), BRIDGE = path.join(ROOT, "foundry-bridge");
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, "../lib/command_manifest.json"), "utf8"));
const PANEL = path.join(__dirname, "..");   // controls live in index.html or are built by a *_ui.js file
const html = [fs.readFileSync(path.join(PANEL, "index.html"), "utf8")].concat(fs.readdirSync(PANEL).filter(f => /_ui\.js$/.test(f)).map(f => fs.readFileSync(path.join(PANEL, f), "utf8"))).join("\n");
let ok = 0, fail = 0; const pendingList = [];
const check = (n, c, x) => { if (c) { ok++; if (process.env.VERBOSE) console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };

// ---- extraction from the Python / mjs sources
function flagsOf(src) {
  const out = new Set(), re = /add_argument\(\s*((?:"-{1,2}[\w-]+"\s*,\s*)*"-{1,2}[\w-]+")/g; let m;
  while ((m = re.exec(src))) (m[1].match(/"(-{1,2}[\w-]+)"/g) || []).forEach(s => { if (!/^"-[^-]/.test(s)) out.add(s.slice(1, -1)); });
  return [...out].sort();
}
function commandsOf(src) {
  const out = new Set(); let m;
  const ch = /add_argument\(\s*"cmd"\s*,\s*choices=\[([^\]]*)\]/g;
  while ((m = ch.exec(src))) (m[1].match(/"([\w-]+)"/g) || []).forEach(s => out.add(s.slice(1, -1)));
  const ap = /add_parser\(\s*"([\w-]+)"/g; while ((m = ap.exec(src))) out.add(m[1]);
  const tup = /for n in \(([^)]*)\)/g; while ((m = tup.exec(src))) (m[1].match(/"([\w-]+)"/g) || []).forEach(s => out.add(s.slice(1, -1)));
  const ic = /_av\[0\]\s*(?:==\s*"([\w-]+)"|in\s*\(([^)]*)\))/g;       // commands foundry_push.main hands to another module before argparse
  while ((m = ic.exec(src))) { if (m[1]) out.add(m[1]); else (m[2].match(/"([\w-]+)"/g) || []).forEach(s => out.add(s.slice(1, -1))); }
  const sp = /for n in \(([^)]*)\):\s*\n\s*s = sub\.add_parser\(n\)/g; while ((m = sp.exec(src))) (m[1].match(/"([\w-]+)"/g) || []).forEach(s => out.add(s.slice(1, -1)));
  return [...out].sort();
}
function bridgectlCommands(src) {
  const m = /node bridgectl\.mjs <([^>]*)>/.exec(src); return m ? m[1].split("|").sort() : [];
}
function bridgectlFlags(src) { const out = new Set(); let m; const re = /\[(--[\w-]+)[\s\]]/g; while ((m = re.exec(src.split("import fs")[0]))) out.add(m[1]); return [...out].sort(); }

const sources = {
  "foundry_push.py": GEN + "/foundry_push.py", "foundry_collision.py": GEN + "/foundry_collision.py", "foundry_water.py": GEN + "/foundry_water.py",
  "worldpack.py": GEN + "/worldpack.py", "worldpack_split.py": GEN + "/worldpack_split.py", "object_edit.py": GEN + "/object_edit.py",
  "scene_audit.py": GEN + "/scene_audit.py", "textures_audit.py": GEN + "/textures_audit.py", "building_ground_audit.py": GEN + "/building_ground_audit.py",
  "road_height_audit.py": GEN + "/road_height_audit.py", "terrain_check.py": GEN + "/terrain_check.py", "tile_rotation_inspect.py": GEN + "/tile_rotation_inspect.py",
  "padding_heightmap.py": GEN + "/padding_heightmap.py", "foundry_lightbudget.py": GEN + "/foundry_lightbudget.py", "signs.py": GEN + "/signs.py",
  "streetlamps.py": GEN + "/streetlamps.py", "heightmap_paint.py": GEN + "/heightmap_paint.py", "streetlamps_scene.py": GEN + "/streetlamps_scene.py",
  "foundry_sun.py": GEN + "/foundry_sun.py", "sun_preview.py": GEN + "/sun_preview.py", "place_create.py": GEN + "/place_create.py", "place_manage.py": GEN + "/place_manage.py"
};
const extracted = {};
Object.keys(sources).forEach(k => { let s = ""; try { s = fs.readFileSync(sources[k], "utf8"); } catch (e) { return; } extracted[k] = { commands: commandsOf(s), flags: flagsOf(s) }; });
const bc = fs.readFileSync(path.join(BRIDGE, "bridgectl.mjs"), "utf8");
extracted["bridgectl.mjs"] = { commands: bridgectlCommands(bc), flags: bridgectlFlags(bc) };

if (process.argv.includes("--list")) { console.log(JSON.stringify(extracted, null, 1)); process.exit(0); }

// ---- control references: "act:NAME" (data-act), "s:PATH" (data-s), "id:ID", "tab:NAME", "bridge:..." (bridge section, checked by id/act too)
function controlExists(ref) {
  const m = /^(act|s|id|tab):(.+)$/.exec(ref); if (!m) return false;
  if (m[1] === "act") return html.includes('data-act="' + m[2] + '"');
  if (m[1] === "s") return html.includes('data-s="' + m[2] + '"');
  if (m[1] === "id") return html.includes('id="' + m[2] + '"');
  return html.includes('data-tab="' + m[2] + '"');
}
function entryOk(name, e) {
  if (!e || typeof e !== "object") { check(name + ": entry is an object", false); return; }
  if (e.pending !== undefined) { check(name + ": pending has a reason", typeof e.pending === "string" && e.pending.length >= 12); pendingList.push(name + " (" + e.pending + ")"); return; }
  if (e.cli_only !== undefined) { check(name + ": cli_only has a reason", typeof e.cli_only === "string" && e.cli_only.trim().length >= 12, "give a real reason"); return; }
  const c = e.controls;
  check(name + ": lists controls or cli_only", Array.isArray(c) && c.length > 0, JSON.stringify(e));
  (c || []).forEach(ref => check(name + ": control " + ref + " exists in index.html", controlExists(ref)));
}

check("manifest has a version and scripts", manifest.version === 1 && manifest.scripts && typeof manifest.scripts === "object");
Object.keys(extracted).forEach(script => {
  const m = manifest.scripts[script];
  check(script + ": present in the manifest", !!m);
  if (!m) return;
  const X = extracted[script];
  X.commands.forEach(c => { check(script + ": command '" + c + "' is in the manifest", !!(m.commands || {})[c]); entryOk(script + " " + c, (m.commands || {})[c]); });
  X.flags.forEach(f => { check(script + ": flag " + f + " is in the manifest", !!(m.flags || {})[f]); entryOk(script + " " + f, (m.flags || {})[f]); });
  Object.keys(m.commands || {}).forEach(c => check(script + ": manifest command '" + c + "' still exists in the code", X.commands.indexOf(c) >= 0));
  Object.keys(m.flags || {}).forEach(f => check(script + ": manifest flag " + f + " still exists in the code", X.flags.indexOf(f) >= 0));
});
Object.keys(manifest.scripts).forEach(s => check("manifest script " + s + " is checked by this test", !!extracted[s]));
// scripts without an argparse (libraries, one-offs) are listed with a reason so a reader knows they were looked at
Object.keys(manifest.other || {}).forEach(k => entryOk("other " + k, manifest.other[k]));
// every other script/tool file that could be mistaken for a missing command must be accounted for
["glb_check.py", "scene_audit.py", "foundry_import.py", "start.mjs", "bridge.ps1", "make-scene.ps1", "publish-client.mjs", "survival-job.ps1", "relay-window.ps1", "git"].forEach(k => check("other: " + k + " is accounted for", !!(manifest.other || {})[k]));
if (pendingList.length) console.log("\nPENDING (not yet a panel control, tracked on purpose):\n  " + pendingList.join("\n  "));

console.log("\n" + ok + " passed, " + fail + " failed");
process.exit(fail ? 1 : 0);
