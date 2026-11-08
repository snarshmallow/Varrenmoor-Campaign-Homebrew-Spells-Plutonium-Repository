// Padding tab jobs: argument building, the generate job against the real python generator (output into a temp dir), and the push job against a stubbed
// foundry_push.py (no Foundry connection).   node illustrator/panel/test/test_padding_jobs.js
const fs = require("fs"), path = require("path"), os = require("os"), cp = require("child_process");
const VB = require("../lib/core.js"); require("../lib/padding.js"); const R = require("../lib/runner.js");
const ROOT = path.resolve(__dirname, "../../..").split(path.sep).join("/"), place = "bridgehollow__dyers_walk_local";
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "vbpad-")), tmp = TMP.split(path.sep).join("/");
const d = Object.assign({}, VB.dirs(ROOT, place), { world: tmp + "/world", panel: tmp + "/panel" });
fs.mkdirSync(d.panel, { recursive: true });
const st = VB.normalize(null); st.place = place;
let ok = 0, fail = 0, stubArgs = null;
const check = (n, c, x) => { if (c) { ok++; console.log("PASS", n); } else { fail++; console.log("FAIL", n, x || ""); } };
const spawn = (py, args, o) => {   // push-padding is answered by a stub; everything else runs for real
  if (args.some(a => /foundry_push\.py$/.test(a))) {
    stubArgs = args;
    const { EventEmitter } = require("events"), c = new EventEmitter(); c.stdout = new EventEmitter(); c.stderr = new EventEmitter();
    setTimeout(() => { c.stdout.emit("data", JSON.stringify({ ok: true, tableHeightmapScale: 1.5, base_level_ft: -2, pixel255_ft: 750, quantisation_ft: 2.9, heightmap_used: true, out_dir: "x", files: { preview: "p.png" }, seam: { max_step_terrain_edge_m: 0, max_step_table_m: 0.006, table_only_step_ft: 60 },
      push: { scene: "Scene.abc", dry_run: true, assets: { heightmap: "assets/h.png" }, flags: { "levels-3d-preview": { tableHeightmapScale: 1.5 } }, level_elevation_bottom_ft: -2 } }) + "\n"); c.emit("close", 0); }, 10);
    return c;
  }
  return cp.spawn(py, args, o);
};
const runner = R.createRunner({ root: ROOT, jobsDir: tmp + "/jobs", fs, path, spawn, host: async () => ({ ok: true }), log: m => process.env.VERBOSE && console.log("   " + m),
  getPython: () => "python", getPlace: () => place, getTextures: () => [], setState: (p, v) => VB.setPath(st, p, v), onStale: () => {} });
(async () => {
  check("state carries padding defaults", st.padding && st.padding.preset === "bowl-ridge" && st.padding.dry_run === true && st.padding.blend_ft === 200);
  st.padding.overrides = '{"ridge_amp_ft": 150, "name2": "x"}';
  const a = VB.paddingArgs(st, d).join(" ");
  check("args: place, preset, blend, overrides, out", /--place bridgehollow__dyers_walk_local --preset bowl-ridge --blend 200/.test(a) && /--set ridge_amp_ft=150/.test(a) && /--set name2="x"/.test(a) && a.indexOf("--out " + d.world + "/export/padding") > 0, a);
  st.padding.overrides = "{bad";
  let r = await runner.run(VB.jobPaddingGenerate(st, d));
  check("bad overrides fail cleanly", !r.ok && /JSON object/.test(r.error || ""), r.error);
  st.padding.overrides = ""; st.padding.texture = "winter"; st.padding.base_ft = 5; st.padding.apron = false;
  const a2 = VB.paddingArgs(st, d).join(" ");
  check("texture, base and no-apron flags", /--texture winter/.test(a2) && /--base 5/.test(a2) && /--no-apron/.test(a2), a2);
  st.padding.apron = true; st.padding.base_ft = ""; st.padding.texture = ""; st.padding.preset = "rolling-hills"; st.padding.blend_ft = 120;
  r = await runner.run(VB.jobPaddingGenerate(st, d));
  check("generate job ok", r.ok, r.error);
  check("outputs written", ["padding_heightmap.png", "padding_apron.glb", "padding_preview.png", "padding_meta.json", "padding_table_tile.webp"].every(f => fs.existsSync(d.world + "/export/padding/" + f)));
  check("state remembers scale and seam", st.padding.last && st.padding.last.scale > 0 && st.padding.last.seam.max_step_table_m < 0.05 && /padding_preview\.png/.test(st.padding.preview_png), JSON.stringify(st.padding.last));
  r = await runner.run(VB.jobPaddingPush(st, d));
  check("push without a scene fails cleanly", !r.ok && /pick a Foundry scene/.test(r.error || ""), r.error);
  st.padding.scene_uuid = "Scene.abc"; st.padding.scene_padding = 0.5;
  r = await runner.run(VB.jobPaddingPush(st, d));
  check("push job ok (stub)", r.ok, r.error);
  check("push args: push-padding, scene, dry-run default, scene padding", stubArgs && stubArgs.indexOf("push-padding") >= 0 && stubArgs.join(" ").indexOf("--scene-uuid Scene.abc") > 0 && stubArgs.indexOf("--dry-run") > 0 && stubArgs.join(" ").indexOf("--scene-padding 0.5") > 0, stubArgs && stubArgs.join(" "));
  check("push report stored", st.padding.push_report && st.padding.push_report.dry === true && st.padding.push_report.assets.heightmap === "assets/h.png");
  st.padding.dry_run = false; r = await runner.run(VB.jobPaddingPush(st, d));
  check("real push has no --dry-run", r.ok && stubArgs.indexOf("--dry-run") < 0, stubArgs.join(" "));
  st.padding.save_name = ""; r = await runner.run(VB.jobPaddingSavePreset(st));
  check("save preset needs a name", !r.ok && /name/.test(r.error || ""), r.error);
  console.log(ok + " passed, " + fail + " failed"); process.exit(fail ? 1 : 0);
})();
