// Tools tab UI: audits with a results viewer, texture baking, delete scene (typed-name confirm), one-shot 3D scene push, macro installers.
// Loaded before main.js; main.js calls VBToolsUI.init(ctx). Logic (command lines, jobs) lives in lib/tools.js; the command-to-control map is lib/command_manifest.json.
(function () {
  "use strict";
  var VB = window.VBCore, ctx = null;
  var $ = function (id) { return document.getElementById(id); };
  function S() { return ctx.state(); }
  function err(e) { if (ctx.showError) ctx.showError(String((e && e.message) || e)); else { var o = $("tlOut"); if (o) o.textContent = String((e && e.message) || e); } }
  function run(make) { try { return ctx.startJob(make(), paint); } catch (e) { err(e); return null; } }
  function ask(lines) {   // in-panel confirm (CEP dialogs are unreliable)
    return new Promise(function (res) {
      $("tlConfirmText").textContent = lines.join("\n"); $("tlConfirm").hidden = false;
      var done = function (v) { $("tlConfirm").hidden = true; $("tlYes").onclick = null; $("tlNo").onclick = null; res(v); };
      $("tlYes").onclick = function () { done(true); }; $("tlNo").onclick = function () { done(false); };
    });
  }
  function sceneLabel() {
    var r = VB.deleteSceneRow(S());
    return r ? (r.name || "(unnamed)") + "  [" + r.uuid + "]" : "(no existing scene picked on the Foundry tab)";
  }
  function paint() {
    if (!ctx || !$("tlOut")) return;
    var t = S().tools || {}, o = t.out || {};
    $("tlOutHead").textContent = o.label ? o.label + "  (" + String(o.at || "").replace("T", " ").slice(0, 19) + ")" : "no result yet";
    $("tlOut").textContent = o.text || "";
    $("tlScene").textContent = sceneLabel();
    var r = VB.deleteSceneRow(S()), ok = VB.deleteSceneOk(S());
    $("tlDelWant").textContent = r && r.name ? r.name : "";
    $("tlDelete").disabled = !ok;
    $("tlDelHint").textContent = !r ? "Pick an existing scene on the Foundry tab first." : ok ? "Name matches. Delete is armed." : "Type the scene name above exactly (it is case sensitive) to arm the button.";
  }
  var A = {
    tl_scene_audit: function () { return run(function () { return VB.jobToolsSceneAudit(S(), ctx.dirs()); }); },
    tl_rescale_dry: function () { return run(function () { return VB.jobToolsRescale(S(), false); }); },
    tl_rescale: function () {
      return ask(["Rescale the picked scene to a playable grid?", sceneLabel(), "Every tile, light, token, sound, note and drawing keeps its position in feet; the scene becomes the whole place at the chosen px/ft with 5 ft squares.",
        "Pipeline walls are deleted (3D Canvas tile collision and sight replace them) unless unticked; the 2D background is cleared. Run the dry run first."]).then(function (ok) { if (ok) run(function () { return VB.jobToolsRescale(S(), true); }); });
    },
    tl_bga: function () { return run(function () { return VB.jobToolsBuildingGround(S(), ctx.dirs()); }); },
    tl_rha: function () { return run(function () { return VB.jobToolsRoadHeight(S(), ctx.dirs()); }); },
    tl_terrain_check: function () { return run(function () { return VB.jobToolsTerrainCheck(S()); }); },
    tl_textures_audit: function () { return run(function () { return VB.jobToolsTexturesAudit(S()); }); },
    tl_pack_validate: function () { return run(function () { return VB.jobToolsPackValidate(S(), ctx.dirs()); }); },
    tl_pack_info: function () { return run(function () { return VB.jobToolsPackInfo(S(), ctx.dirs()); }); },
    tl_split_info: function () { return run(function () { return VB.jobToolsSplitInfo(S(), ctx.dirs()); }); },
    tl_places: function () { return run(function () { return VB.jobToolsFoundryRead(S(), "places"); }); },
    tl_export_info: function () { return run(function () { return VB.jobToolsFoundryRead(S(), "export-info"); }); },
    tl_obj_buildings: function () { return run(function () { return VB.jobToolsObjectList(S(), "list-buildings"); }); },
    tl_obj_roads: function () { return run(function () { return VB.jobToolsObjectList(S(), "list-roads"); }); },
    tl_obj_choices: function () { return run(function () { return VB.jobToolsObjectList(S(), "choices"); }); },
    tl_reexport: function () { return run(function () { return VB.jobToolsReexport(S(), ctx.dirs()); }); },
    tl_bake_window: function () { return run(function () { return VB.jobToolsBakeWindow(S(), ctx.dirs()); }); },
    tl_bake: function () { return run(function () { return VB.jobToolsBake(S(), ctx.dirs(), false); }); },
    tl_bake_publish: async function () {
      try { VB.bakeArgs(S(), ctx.dirs(), true); } catch (e) { return err(e); }
      if (!(await ask(["Publish copies the baked image into the shared assets folder that Foundry serves (a new versioned file; nothing is overwritten).", "Continue?"]))) return null;
      return run(function () { return VB.jobToolsBake(S(), ctx.dirs(), true); });
    },
    tl_delete_scene: async function () {
      var j; try { j = VB.jobToolsDeleteScene(S()); } catch (e) { return err(e); }
      if (!(await ask(["DELETE SCENE " + j.label.replace("Delete scene ", "") + " (" + j.params.uuid + ") from Foundry?", "This cannot be undone: its tiles, walls, lights and notes go with it. Tokens' actors stay.", "Continue?"]))) return null;
      return ctx.startJob(j, function () { if (ctx.refreshAll) ctx.refreshAll(); paint(); });
    },
    tl_s3d_dry: function () { return run(function () { return VB.jobToolsScene3d(S(), ctx.dirs(), true); }); },
    tl_s3d_push: async function () {
      var j; try { j = VB.jobToolsScene3d(S(), ctx.dirs(), false); } catch (e) { return err(e); }
      if (!(await ask(["This WRITES to Foundry: models, foliage, padding, lights, skybox and flags of the picked existing scene " + sceneLabel() + ".", "Run 'Push 3D scene (dry run)' first to preview. Continue?"]))) return null;
      return ctx.startJob(j, paint);
    }
  };
  function init(c) {
    ctx = c;
    Object.keys(A).forEach(function (k) { if (ctx.acts) ctx.acts[k] = A[k]; });
    var del = document.querySelector('[data-s="tools.del.typed"]'); if (del) del.addEventListener("input", function () { setTimeout(paint, 0); });
    paint();
  }
  window.VBToolsUI = { init: init, paint: paint, actions: A };
})();
