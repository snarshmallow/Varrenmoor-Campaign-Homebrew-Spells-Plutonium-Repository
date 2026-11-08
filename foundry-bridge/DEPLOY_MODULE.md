# Redeploying module 0.3.1 (4002 reconnect-loop fix)
0.3.1 changes only `scripts/bridge.js` (and the version in `module.json`): a client closed by the relay with code 4002 ("replaced by another GM tab") no longer reconnects, shows one warning, and "connected" notices are rate limited (1 per minute). The relay needs no change for this (a relay restart is only needed to pick up the new `/health` fields, optional).
1. Copy `foundry-bridge/module/varrenmoor-bridge/module.json` and `scripts/bridge.js` to `<Foundry Data>\modulesarrenmoor-bridge\` and `...\scripts\` on Vega (same two files as below; keep `relay-url.json` if present). The zip `module/varrenmoor-bridge.zip` was rebuilt too, for Add-on Modules > Update.
2. Close all but one Foundry GM browser tab, then Ctrl+F5 in the remaining GM tab. Check the module version shows 0.3.1 (`bridge.ps1 version`).
3. Test: open a second GM tab with the module connected. The first tab should show one warning and stay disconnected (the relay log shows a single `closed 4002`, no repeats). F5 in the first tab takes the connection back.
4. Roll back: copy the 0.3.0 files from git history.

# Deploying Varrenmoor Bridge module 0.3.0 on Vega

The Foundry server and its module files live on Vega, so the new module cannot be pushed from Arcturus. Until it is copied over, everything else keeps working (ping, list, get, create, update, world_info); the Illustrator "Foundry" tab and `illustrator/generators/foundry_push.py` stop with the message "module older than 0.3.0" for push actions.

## What changed (0.2.0 -> 0.3.0, backwards compatible)
All old ops behave as before. New ops, all guarded by the world setting **Allow writes** where they write:
`version` (module version + protocol 3 + op list), `find_by_flag`, `upsert_by_flag`, `upsert_many` (bulk, with prune), `delete_by_flag`, `delete` (refuses anything without the pipeline flag), `set_scene_background` (v14: updates the scene Level background), `set_scene_grid`. `create` also accepts `Drawing` and `Note`.
Pipeline flag: `flags.varrenmoor.pipelineId` (string key). Scenes also get `flags.varrenmoor.worldId` and `flags.varrenmoor.calib` (feet to pixel calibration used to place tokens).

## Copy (2 files)
From this repo (branch `claude/adoring-shannon-yjixst`, or `main` after merge), on Vega:

| From | To |
|---|---|
| `foundry-bridge/module/varrenmoor-bridge/module.json` | `<Foundry Data>\modules\varrenmoor-bridge\module.json` |
| `foundry-bridge/module/varrenmoor-bridge/scripts/bridge.js` | `<Foundry Data>\modules\varrenmoor-bridge\scripts\bridge.js` |

(`Data` = the Foundry user data folder that holds `modules`. Keep `relay-url.json` if it exists there. Alternative: in Foundry, Add-on Modules, Varrenmoor Bridge, Update, which reads the manifest URL on the branch; `module/varrenmoor-bridge.zip` was rebuilt for that.)

## Refresh
1. Restart nothing on the server. In the GM browser on Arcturus press **Ctrl+F5** (hard reload) so the new `bridge.js` is fetched; the module reconnects to the relay by itself.
2. Do not touch the relay window (port 3030).

## Verify (from Arcturus, in `foundry-bridge`)
```
.\bridge.ps1 world_info          # modules list shows varrenmoor-bridge 0.3.0
.\bridge.ps1 version             # {"module":"0.3.0","protocol":3,"ops":[... upsert_many ...]}
python ..\illustrator\generators\foundry_push.py status     # pipeline_ops: true
```
Then in the panel Foundry tab: Check connection (should say "connected, module 0.3.0"), Refresh from Foundry, push to a new scene named e.g. "ZZ Illustrator Push Test", push again (walls: updated, none created), and remove it with
`python illustrator\generators\foundry_push.py delete-scene --scene-uuid <uuid>` (the module only deletes documents that carry the pipeline flag).

## Leftover from testing before deployment
A scratch scene "ZZ Illustrator Push Test" (`Scene.SLPM8ihlgzcIzRaM`, flag `scratch:zz-illustrator-push-test`, one test wall) was created while the old module had no delete op. After deploying, remove it: `foundry_push.py delete-scene --scene-uuid Scene.SLPM8ihlgzcIzRaM`.

## Roll back
Copy the previous `module.json` and `bridge.js` back (git history) and Ctrl+F5. Pipeline-flagged documents stay in the world and are harmless.
