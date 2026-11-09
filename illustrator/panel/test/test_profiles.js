// Profiles: allow-list schema, collect/diff/apply round trip, exclusion of geometry and identity keys, migration, validation, atomic store (injected fs), built-ins.
//   node illustrator/panel/test/test_profiles.js
const fs = require("fs"), path = require("path"), os = require("os");
const VB = require("../lib/core.js");
["townarea", "regions", "styles", "objects", "lighting", "sun3d", "streetlamps", "foliage", "skybox", "water", "heightpaint", "padding", "bridges", "places", "tools", "bridge", "exportplan", "profiles"].forEach(f => require("../lib/" + f + ".js"));
const P = require("../lib/profiles.js");
let ok = 0, fail = 0;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const clone = o => JSON.parse(JSON.stringify(o));

check("format and version", P.FORMAT === "varrenmoor-profile" && P.VERSION === 1);
const st = VB.normalize(null); st.place = "demo_place";
// geometry and identity filled in on purpose
st.town.area = [[0, 0], [10, 0], [10, 10]]; st.town.rings = [[1, 2]]; st.town.entry_x = 77; st.terrain.patch.polygon = [[1, 1]]; st.foundry.sceneUuid = "Scene.abc"; st.foundry.sceneName = "My scene";
st.foliage.polygon = [[1, 2]]; st.water.river_path = [[1, 2]]; st.lighting.lights = [{ x: 1 }]; st.bridges.items = [{ id: "b1" }]; st.padding.scene_uuid = "Scene.zzz"; st.skybox.scene_uuid = "Scene.s";
st.settings.python = "C:/py.exe"; st.bridge.node = "node.exe";
const all = P.collect(st);
const flat = Object.keys(all).reduce((a, s) => a.concat(Object.keys(all[s])), []);
check("every captured path is allow-listed", flat.every(k => P.isAllowed(k)));
const bad = ["town.area", "town.rings", "town.entry_x", "terrain.patch.polygon", "foundry.sceneUuid", "foundry.sceneName", "foliage.polygon", "water.river_path", "lighting.lights", "bridges.items", "padding.scene_uuid", "skybox.scene_uuid", "settings.python", "bridge.node", "place", "profile.name", "foundry.cache.fetched", "regions.polygon", "styles.ids", "objects.b"];
check("geometry, identity and machine keys are never captured", bad.every(k => flat.indexOf(k) < 0 && !flat.some(f => f.indexOf(k + ".") === 0)), bad.filter(k => flat.indexOf(k) >= 0).join(","));
check("deny keys are enforced at depth", !P.isAllowed("lighting.f3d.last") && !P.isAllowed("lighting.lights.0") && !P.isAllowed("foundry.models.collision.polygon") && !P.isAllowed("foliage.merge.scene_uuid") && P.isAllowed("foundry.models.collision.roofs"));
check("sections cover export, collision, lighting, streetlamps, terrain, scale, style, foliage, town", ["export", "collision", "lighting", "streetlamps", "terrain", "scale", "style", "foliage", "town"].every(s => P.section(s)));
check("export section holds the export options", all.export["foundry.models.prune"] === true && all.export["foundry.models.roofMode"] === "none" && all.export["roads.smooth"] === 0.5 && "tools.s3d.with_lights" in all.export);
check("collision section", all.collision["foundry.models.collision.roofs"] === false && all.collision["foundry.models.sight.buildings"] === true);

// round trip
const doc = P.make("Round trip", st, null, { description: "d" });
check("make: format, version, scope", doc.format === P.FORMAT && doc.version === 1 && doc.scope.length === P.SECTIONS.length && doc.name === "Round trip");
check("no diff against own state", P.diff(st, doc).length === 0 && !P.isModified(st, doc));
const st2 = clone(st); st2.foundry.models.roofMode = "per_scene"; st2.lighting.sun3d.preset = "night"; st2.foundry.models.collision.roofs = true; st2.labels.styles["default"].size = 99;
check("diff finds the changes in the right sections", (() => { const d = P.diff(st2, doc); return d.length >= 3 && d.some(x => x.section === "export" && x.path === "foundry.models.roofMode" && x.to === "none") && d.some(x => x.section === "lighting") && d.some(x => x.section === "collision"); })());
check("isModified", P.isModified(st2, doc));
const r = P.apply(st2, doc);
check("apply restores every setting", P.diff(r.state, doc).length === 0 && r.applied >= 3 && r.state.foundry.models.roofMode === "none");
check("apply does not mutate the input", st2.foundry.models.roofMode === "per_scene");
check("apply keeps geometry and identity", JSON.stringify(r.state.town.area) === JSON.stringify(st.town.area) && r.state.foundry.sceneUuid === "Scene.abc" && r.state.place === "demo_place" && r.state.foundry.sceneName === "My scene" && r.state.lighting.lights.length === 1);
// a hostile profile cannot reach geometry or identity
const evil = { format: P.FORMAT, version: 1, name: "Evil", sections: { export: { "foundry.sceneUuid": "Scene.HACK", "place": "other", "foundry.models.prune": false }, town: { "town.area": [[9, 9]], "town.rings": [], "town.seed": 5 }, nosuch: { a: 1 } } };
const ev = P.validate(evil);
check("validate drops non-settings with warnings", ev.ok && ev.warnings.length >= 4 && !("foundry.sceneUuid" in ev.doc.sections.export) && !("town.area" in ev.doc.sections.town) && ev.doc.sections.town["town.seed"] === 5 && !ev.doc.sections.nosuch, JSON.stringify(ev));
const ea = P.apply(st, ev.doc).state;
check("applying a hostile profile leaves identity and geometry untouched", ea.foundry.sceneUuid === "Scene.abc" && ea.place === "demo_place" && JSON.stringify(ea.town.area) === JSON.stringify(st.town.area) && ea.town.seed === 5 && ea.foundry.models.prune === false);
const raw = { sections: { export: { "foundry.sceneUuid": "Scene.HACK" } } };
check("diff/apply ignore paths outside the allow-list even without validate", P.diff(st, raw).length === 0 && P.apply(st, raw).state.foundry.sceneUuid === "Scene.abc");
// type safety
const ty = { format: P.FORMAT, version: 1, name: "T", sections: { export: { "foundry.models.prune": "yes", "foundry.models.lod": 2 } } };
const tr = P.apply(st, P.validate(ty).doc);
check("type mismatch skipped, rest applied", tr.skipped.length === 1 && tr.state.foundry.models.prune === true && tr.state.foundry.models.lod === 2, JSON.stringify(tr.skipped));
const only = P.apply(st2, doc, ["collision"]);
check("per-section apply touches only that section", only.state.foundry.models.collision.roofs === false && only.state.foundry.models.roofMode === "per_scene");
check("summarize groups by section", P.summarize(P.diff(st2, doc)).every(s => s.count > 0 && s.title));
const dd = P.fromDefaults(VB.defaults(), ["export", "collision"]);
check("reset to defaults = diff against VB.defaults", P.diff(st2, dd, ["collision"]).length === 1 && P.apply(st2, dd, ["export"]).state.foundry.models.roofMode === "none");

// validation
const V = d => P.validate(d);
check("validate: not an object", !V(null).ok && !V("x").ok && !V([]).ok);
check("validate: wrong format", !V({ format: "other", version: 1, name: "a", sections: {} }).ok);
check("validate: bad version", !V({ format: P.FORMAT, version: "1", name: "a", sections: {} }).ok && !V({ format: P.FORMAT, version: 0, name: "a", sections: {} }).ok);
check("validate: missing sections / name", !V({ format: P.FORMAT, version: 1, name: "a" }).ok && !V({ format: P.FORMAT, version: 1, sections: {} }).ok && !V({ format: P.FORMAT, version: 1, name: "///", sections: {} }).ok);
check("validate: newer version tolerated with warning", (() => { const v = V({ format: P.FORMAT, version: 9, name: "a", sections: { export: { "foundry.models.lod": 1 } }, futureKey: 1 }); return v.ok && v.warnings.some(w => /newer/.test(w)) && v.doc.version === 1 && v.doc.futureKey === undefined; })());
check("validate: unknown top-level keys are dropped, known kept", (() => { const v = V({ format: P.FORMAT, version: 1, name: "a", description: "x", extra: { a: 1 }, sections: {} }); return v.ok && !("extra" in v.doc) && v.doc.description === "x"; })());
const old = { name: "Old", settings: { "foundry.models.lod": 2, "town.area": [[1, 1]], "bogus.key": 1 } };
const mg = P.validate(old);
check("migrate v0 flat settings", mg.ok && mg.doc.sections.export["foundry.models.lod"] === 2 && !mg.doc.sections.town && mg.warnings.some(w => /version 0/.test(w)) && mg.warnings.some(w => /bogus/.test(w)), JSON.stringify(mg));
check("sanitizeName", P.sanitizeName("  My profile: night/2  ") === "My profile_ night_2" && P.sanitizeName("../..\\x") === "x" && P.sanitizeName("") === "" && P.sanitizeName("CON") === "CON_" && P.sanitizeName("a".repeat(200)).length <= 60 && P.sanitizeName("...") === "", P.sanitizeName("  My profile: night/2  ") + "|" + P.sanitizeName("../..\\x"));

// store with an injected in-memory fs
const flag = { failWrite: false };
function memfs() {
  const files = {}, dirs = new Set(), log = [];
  const norm = p => p.replace(/\\/g, "/");
  return { files, log,
    mkdirSync: (p) => { dirs.add(norm(p)); }, existsSync: p => norm(p) in files || dirs.has(norm(p)),
    writeFileSync: (p, t) => { log.push("w " + norm(p)); if (flag.failWrite && /\.tmp-/.test(p)) { files[norm(p)] = "partial"; throw new Error("disk full"); } files[norm(p)] = String(t); },
    readFileSync: (p) => { if (!(norm(p) in files)) { const e = new Error("ENOENT " + p); e.code = "ENOENT"; throw e; } return files[norm(p)]; },
    renameSync: (a, b) => { log.push("r " + norm(a) + " -> " + norm(b)); if (!(norm(a) in files)) throw new Error("no src"); files[norm(b)] = files[norm(a)]; delete files[norm(a)]; },
    unlinkSync: p => { if (!(norm(p) in files)) throw new Error("ENOENT"); delete files[norm(p)]; },
    readdirSync: p => { const pre = norm(p).replace(/\/$/, "") + "/"; const o = Object.keys(files).filter(f => f.indexOf(pre) === 0 && f.slice(pre.length).indexOf("/") < 0).map(f => f.slice(pre.length)); if (!o.length && !dirs.has(norm(p))) throw new Error("ENOENT"); return o; } };
}
const M = memfs();
const store = P.createStore({ fs: M, userDir: "/r/presets/profiles", builtinDir: "/r/presets/profiles/builtin", placeDir: pl => "/r/world/" + pl + "/profiles", defaultFile: "/r/presets/profiles/_default.json" });
const f1 = store.write(P.make("Mine", st, ["export"]), "user", "demo_place");
check("write: atomic (temp file then rename), no temp left", f1 === "/r/presets/profiles/Mine.json" && M.log.some(l => /^w .*Mine\.json\.tmp-/.test(l)) && M.log.some(l => /^r .*\.tmp-.* -> \/r\/presets\/profiles\/Mine\.json$/.test(l)) && !Object.keys(M.files).some(f => /\.tmp-/.test(f)), M.log.join(" | "));
check("write: refuses to overwrite without the flag", (() => { try { store.write(P.make("Mine", st), "user"); return false; } catch (e) { return /already exists/.test(e.message); } })());
check("write: overwrite allowed on request", store.write(P.make("Mine", st, ["export", "collision"]), "user", "demo_place", { overwrite: true }) === f1 && store.read("user", "Mine").doc.scope.length === 2);
flag.failWrite = true; const before = M.files[f1];
check("failed write leaves the old file intact and no temp", (() => { try { store.write(P.make("Mine", st, ["scale"]), "user", "x", { overwrite: true }); return false; } catch (e) { return M.files[f1] === before && !Object.keys(M.files).some(f => /\.tmp-/.test(f)); } })());
flag.failWrite = false;
check("write: invalid doc refused", (() => { try { store.write({ format: "x" }, "user"); return false; } catch (e) { return /invalid profile/.test(e.message); } })());
check("write: built-in is read-only", (() => { try { store.write(P.make("B", st), "builtin"); return false; } catch (e) { return /read-only/.test(e.message); } })() && (() => { try { store.remove("builtin", "B"); return false; } catch (e) { return /read-only/.test(e.message); } })());
store.write(P.make("Place only", st, ["scale"]), "place", "demo_place");
const l = store.list("demo_place");
check("list: user and place scopes", l.some(e => e.where === "user" && e.name === "Mine") && l.some(e => e.where === "place" && e.name === "Place only") && !store.list(null).some(e => e.where === "place"));
store.rename("user", "Mine", "Renamed", "demo_place");
check("rename", !M.files[f1] && store.read("user", "Renamed").ok && store.read("user", "Renamed").doc.name === "Renamed");
check("rename onto an existing name refused", (() => { store.write(P.make("Other", st), "user"); try { store.rename("user", "Renamed", "Other"); return false; } catch (e) { return /already exists/.test(e.message); } })());
store.duplicate("user", "Renamed", "place", "Copy of it", "demo_place");
check("duplicate to the place scope", store.read("place", "Copy of it", "demo_place").ok);
store.remove("user", "Other");
check("remove", !store.list("demo_place").some(e => e.name === "Other"));
check("default marker set/get/clear", (() => { store.setDefault({ name: "Renamed", where: "user" }); const g = store.getDefault(); store.setDefault(null); return g.name === "Renamed" && g.where === "user" && store.getDefault() === null; })());
M.files["/in/p.json"] = JSON.stringify({ format: P.FORMAT, version: 1, name: "Imp", sections: { export: { "foundry.models.lod": 2, "foundry.sceneUuid": "x" } }, zzz: 1 });
const im = store.importFile("/in/p.json", "user", "demo_place");
check("import tolerates unknown keys", im.name === "Imp" && im.warnings.length === 1 && store.read("user", "Imp").doc.sections.export["foundry.models.lod"] === 2);
M.files["/in/bad.json"] = "{nope";
check("import bad json -> clear error", (() => { try { store.importFile("/in/bad.json", "user"); return false; } catch (e) { return /cannot read/.test(e.message); } })());
M.files["/in/wrong.json"] = JSON.stringify({ hello: 1 });
check("import wrong format -> clear error", (() => { try { store.importFile("/in/wrong.json", "user"); return false; } catch (e) { return /not a usable profile/.test(e.message); } })());
M.files["/r/presets/profiles/Broken.json"] = "{";
check("list shows a broken file as invalid, not a crash", store.list("demo_place").some(e => e.name === "Broken" && !e.ok));

// built-ins shipped in the repo (real fs)
const BI = path.resolve(__dirname, "../../presets/profiles/builtin");
const real = P.createStore({ fs, userDir: os.tmpdir() + "/vbprof_u", builtinDir: BI, placeDir: p => os.tmpdir() + "/vbprof_p/" + p, defaultFile: os.tmpdir() + "/vbprof_u/_default.json" });
const bl = real.list(null).filter(e => e.where === "builtin");
check("five built-in profiles, all valid and flagged builtin", bl.length === 5 && bl.every(e => e.ok && e.doc.builtin === true), bl.map(e => e.name + ":" + e.ok).join(","));
check("built-in names", ["Standard Foundry export", "Fast preview (low detail)", "Night village", "Big map (heavy)", "Dungeon / interior"].every(n => bl.some(e => e.name === n)));
check("built-ins carry no warnings and apply cleanly to a fresh state", bl.every(e => { const s = VB.normalize(null); const r = P.apply(s, e.doc); return P.validate(JSON.parse(fs.readFileSync(e.file, "utf8"))).warnings.length === 0 && P.diff(r.state, e.doc).length === 0 && r.skipped.length === 0; }));
const std = bl.filter(e => e.name === "Standard Foundry export")[0].doc, fresh = VB.normalize(null);
check("Standard Foundry export agrees with the new-place defaults except roofs per building", P.diff(fresh, std).length === 1 && P.diff(fresh, std)[0].path === "foundry.models.roofMode", JSON.stringify(P.diff(fresh, std)));
check("built-in write refused on the real store", (() => { try { real.write(std, "builtin"); return false; } catch (e) { return /read-only/.test(e.message); } })());
const src = fs.readFileSync(__dirname + "/../lib/profiles.js", "utf8");
check("window.VBProfiles published alongside module.exports", /window\.VBProfiles = P/.test(src) && /module\.exports = P/.test(src));

// secrets deny-list, nested smuggling, legacy format, the 'target' section
check("secret-like keys are never allowed", ["foundry.relay_token", "foundry.models.collision.password", "lighting.api_key", "streetlamps.secret", "padding.pairing_code", "foundry.authToken", "labels.key", "scale.session_id"].every(k => !P.isAllowed(k)) && P.isAllowed("foundry.models.collision.roofs"));
const stS = clone(st); stS.streetlamps.relay_token = "TOKEN123"; stS.padding.secret = "s"; stS.labels.styles["default"].api_key = "k";
check("collect never captures secrets", !JSON.stringify(P.collect(stS)).match(/TOKEN123|api_key|"s"/));
const smug = P.validate({ format: P.FORMAT, version: 1, name: "S", sections: { foliage: { padding: { polygon: [[1, 1]], scene_uuid: "Scene.x", token: "t", feather_ft: 7 } } } });
check("object values are flattened and checked leaf by leaf (no geometry/secret smuggling)", smug.ok && JSON.stringify(smug.doc.sections.foliage) === JSON.stringify({ "padding.feather_ft": 7 }), JSON.stringify(smug.doc && smug.doc.sections));
const rawSmug = { sections: { foliage: { padding: { polygon: [[5, 5]] } } } };
check("diff/apply flatten object values too", P.apply(st, rawSmug).state.padding.polygon === st.padding.polygon || JSON.stringify(P.apply(st, rawSmug).state.padding.polygon) === JSON.stringify(st.padding.polygon));
const legacy = P.validate({ format: "varrenmoor.plugin.profile", version: 1, name: "Old", sections: { export: { "foundry.models.lod": 1 } }, futureKey: 1 });
check("legacy draft format migrates (with a warning), unknown top-level keys tolerated", legacy.ok && legacy.doc.format === "varrenmoor-profile" && legacy.warnings.some(w => /early-draft/.test(w)) && !("futureKey" in legacy.doc));
check("validate error messages are clear", /format is "nope"/.test(P.validate({ format: "nope", version: 1, name: "a", sections: {} }).errors.join()) && /usable name/.test(P.validate({ format: P.FORMAT, version: 1, name: "///", sections: {} }).errors.join()));
check("target section captures foundry.target only", JSON.stringify(P.collect(st, ["target"]).target) === JSON.stringify({ "foundry.target": st.foundry.target }));

// default profile for NEW places: applied once, recorded
const defDoc = bl.filter(e => e.name === "Night village")[0].doc;
const once = P.applyDefaultOnce(VB.normalize(null), defDoc, { name: "Night village", where: "builtin" });
check("default profile applied to a new place and recorded", once.done && once.applied > 0 && once.state.profile_applied.name === "Night village" && once.state.profile.name === "Night village" && P.diff(once.state, defDoc).length === 0);
const st3 = clone(once.state); st3.streetlamps = VB.normalize(null).streetlamps;
const twice = P.applyDefaultOnce(st3, defDoc, { name: "Night village", where: "builtin" });
check("default profile is never applied twice", !twice.done && twice.state === st3);
check("profile_applied is not a profile setting", !P.isAllowed("profile_applied.name") && !P.isAllowed("profile.name"));

// CEP regression: window AND module both present -> both get the api (test_lasso pattern)
const vm = require("vm");
const ctxW = { window: {}, module: { exports: {} }, require, process, console };
ctxW.self = ctxW.window; vm.createContext(ctxW); vm.runInContext(src, ctxW);
check("CEP (window + module): VBProfiles on window and module.exports", ctxW.window.VBProfiles && ctxW.module.exports && ctxW.window.VBProfiles.FORMAT === P.FORMAT && ctxW.module.exports.FORMAT === P.FORMAT);
const ctxB = { window: {}, console }; ctxB.self = ctxB.window; vm.createContext(ctxB); vm.runInContext(src, ctxB);
check("browser (no module): VBProfiles on window", ctxB.window.VBProfiles && ctxB.window.VBProfiles.FORMAT === P.FORMAT);

// stubbed-DOM smoke test of profiles_ui.js: init, save as, load preview + apply, two-click delete, header indicator
(function uiSmoke() {
  const els = {};
  function el(id) {
    if (!els[id]) els[id] = { id, value: "", textContent: "", innerHTML: "", hidden: false, disabled: false, className: "", title: "", style: {}, attrs: {}, on: {},
      addEventListener(t, f) { this.on[t] = f; }, setAttribute(k, v) { this.attrs[k] = v; }, getAttribute(k) { return this.attrs[k]; } };
    return els[id];
  }
  const doc = { getElementById: el, body: { appendChild() {}, removeChild() {} }, createElement: () => ({ select() {} }), execCommand() {},
    querySelectorAll(sel) { const m = /^#(\w+) /.exec(sel); const h = m ? el(m[1]).innerHTML : ""; const out = []; h.replace(/data-pfsec="(\w+)"/g, (_, s) => { out.push({ checked: true, getAttribute: () => s }); }); return out; } };
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "vbprof_ui_"));
  fs.mkdirSync(tmp + "/illustrator/presets/profiles/builtin", { recursive: true });
  fs.readdirSync(BI).forEach(f => fs.copyFileSync(BI + "/" + f, tmp + "/illustrator/presets/profiles/builtin/" + f));
  let state = VB.normalize(null); state.place = "demo_place"; let saves = 0, refreshed = 0;
  const w = { VBCore: VB, VBProfiles: P };
  const sb = { window: w, document: doc, navigator: {}, setInterval: () => 0, setTimeout: () => 0, clearTimeout() {}, console };
  sb.window.document = doc; vm.createContext(sb);
  vm.runInContext(fs.readFileSync(__dirname + "/../profiles_ui.js", "utf8"), sb);
  const UI = w.VBProfilesUI;
  check("profiles_ui publishes window.VBProfilesUI", !!UI && typeof UI.init === "function");
  UI.init({ state: () => state, save: () => { saves++; }, fs, root: tmp, syncInputs() {}, refreshAll: () => { refreshed++; UI.paint(); }, showTab() {} });
  check("ui: header indicator shows 'Profile: none' on a fresh place", el("profInd").textContent === "Profile: none");
  check("ui: list holds the five built-ins", (el("pfList").innerHTML.match(/<option/g) || []).length === 5 && /Night village/.test(el("profQuick").innerHTML));
  check("ui: Save as section checkboxes rendered", (el("pfScope").innerHTML.match(/data-pfsec/g) || []).length === P.SECTIONS.length);
  el("pfName").value = "My look"; el("pfWhere").value = "place"; el("pfSaveAs").on.click();
  const saved = tmp + "/world/demo_place/profiles/My look.json";
  check("ui: Save as writes the per-place file and marks it active", fs.existsSync(saved) && state.profile.name === "My look" && state.profile.where === "place" && saves === 1, el("pfMsg").textContent);
  UI.paint();
  check("ui: indicator unmodified after save", el("profInd").textContent === "Profile: My look");
  state.foundry.models.lod = 3; UI.paint();
  check("ui: indicator shows (modified) when settings drift", el("profInd").textContent === "Profile: My look (modified)");
  el("pfList").value = "builtin:Night village"; el("pfLoad").on.click();
  check("ui: Load shows a diff preview with section checkboxes, nothing applied yet", /would change/.test(el("pfDiff").innerHTML) && /data-pfsec/.test(el("pfDiff").innerHTML) && el("pfApply").hidden === false && state.profile.name === "My look");
  el("pfApply").on.click();
  check("ui: Apply loads the profile and records it", state.profile.name === "Night village" && state.profile.where === "builtin" && refreshed === 1 && P.diff(state, defDoc).length === 0, el("pfMsg").textContent);
  el("pfList").value = "place:My look"; el("pfDelete").on.click();
  check("ui: Delete needs a second click (armed, file still there)", fs.existsSync(saved) && /again/.test(el("pfDelete").textContent));
  el("pfDelete").on.click();
  check("ui: second click deletes", !fs.existsSync(saved));
  el("pfList").value = "builtin:Night village"; el("pfDefault").on.click();
  const fresh2 = UI.applyDefaultToNew(Object.assign(VB.normalize(null), { place: "brand_new" }));
  check("ui: default for new places applied once via applyDefaultToNew", fresh2.profile_applied && fresh2.profile_applied.name === "Night village" && UI.applyDefaultToNew(fresh2) === fresh2);
  fs.rmSync(tmp, { recursive: true, force: true });
})();
console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
