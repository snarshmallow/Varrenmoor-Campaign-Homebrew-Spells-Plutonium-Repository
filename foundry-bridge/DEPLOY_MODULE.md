# Update 0.5.1 (one request per browser, no duplicate devices, faster panel)
Changes `module.json`, `scripts/bridge.js`, `scripts/pairing.js` (module; the other 0.5.0 files are unchanged) and, on the relay PC, `relay/pairing.js` + `relay/server.js` (restart the relay once to load them; the module and panel fixes also work against a 0.5.0 relay). The Pair button reuses the waiting request and its code, a browser keeps one record (re-pairing replaces it), the panel checks for requests every 2 s and flags duplicate devices.

---

# Redeploying module 0.5.0 (encrypted pairing, zero-config relay discovery)
0.5.0 replaces the 0.4.0 pairing (0.4.0 is not compatible: new handshake). **Six files** go to the Foundry host PC. Copy them yourself; nothing is pushed from here.

| From (this repo, `foundry-bridge/module/varrenmoor-bridge/`) | To (on the Foundry host PC, under `<Foundry Data>\modules\varrenmoor-bridge\`) |
|---|---|
| `module.json` | `module.json` |
| `scripts/bridge.js` | `scripts\bridge.js` |
| `scripts/pairing.js` | `scripts\pairing.js` |
| `scripts/seccrypto.js` (NEW) | `scripts\seccrypto.js` |
| `scripts/vendor/noble-bundle.js` (NEW, create the folder `scripts\vendor`) | `scripts\vendor\noble-bundle.js` |
| `scripts/vendor/NOBLE-LICENSE.txt` (NEW) | `scripts\vendor\NOBLE-LICENSE.txt` |

Simplest: copy the whole `module\varrenmoor-bridge` folder from this repo over `<Foundry Data>\modules\varrenmoor-bridge` (overwrite; keep `relay-url.json` there if it exists). The same six files are in `module/varrenmoor-bridge.zip` (rebuilt). Then Ctrl+F5 in the Foundry GM tab. If you had 0.4.0 installed, nothing else changes (no pairing was completed with it).

## The relay side: ONE restart on the relay PC
The relay needs the new `server.js`, `pairing.js`, `seccrypto.js`, `adminauth.js` (all in this repo's `foundry-bridge/relay/`) plus `lib/pairing-console.mjs`, `start.mjs`, `daemon.mjs`. A relay that is already running keeps the old code and has **no pairing switch**, so restart it once: on the relay PC close its window and run `start.bat` (the LAN mode `TUNNEL=off` is remembered in `.env`; pairing now starts **on** with Auto-request on). It prints `PAIRING (no token to copy): ON`. After that, pairing can be switched on and off from the Illustrator panel (Foundry tab > Pairing) with no restart.

## Steps
1. Copy the six module files (above). Ctrl+F5 the GM tab. Check the module version is 0.5.0 (Add-on Modules).
2. Restart the relay once (above). Update the repo on the relay PC first (git pull / copy) so it has the new relay files.
3. Open Foundry as `http://<foundry-pc>:30000` (the plain-http LAN address; not an https/Cloudflare address, where pairing is refused on purpose). The module looks for the relay on that same host at port 3030, so there is nothing to type; if the relay is on another PC, type its `host:3030` once in the module setting "Relay address". Pairing starts by itself (setting "Ask for pairing automatically") or press "Pair with relay" in the module settings.
4. The module shows a 6-digit code. In the Illustrator panel (Foundry tab > Pairing) the same code appears with Approve / Deny, on any PC that can reach the relay (the panel reads the API token from the `client.json` the tools already use; or press A in the relay window). Approve only if the codes match.
5. The module says "paired" and connects. No token anywhere. Revoke any time in the panel.
6. Fallback: leave it unpaired and enter Relay URL + Module token as before (the relay URL defaults to the page's own host at port 3030).
7. Roll back: copy the 0.4.0 `module.json`, `bridge.js`, `pairing.js` back from git history and delete `scripts\seccrypto.js` and `scripts\vendor`.

Security (full threat model in `README.md`, "Pairing (module 0.5.0)"): the device credential and the pairing description are encrypted (X25519 + HKDF + ChaCha20-Poly1305), the 6-digit code is derived from both public keys so a man in the middle shows a different code, later logins use an HMAC challenge-response, and pairing is refused for any proxied/Cloudflare or non-LAN request. Still unencrypted: the rest of the LAN traffic (plain http/ws) unless TLS is added.

---

# Redeploying module 0.4.0 (LAN pairing, no tokens to type)
0.4.0 adds a new file and changes two. **Three files** go to Vega this time:

| From (this repo) | To (on Vega) |
|---|---|
| `foundry-bridge/module/varrenmoor-bridge/module.json` | `<Foundry Data>\modules\varrenmoor-bridge\module.json` |
| `foundry-bridge/module/varrenmoor-bridge/scripts/bridge.js` | `<Foundry Data>\modules\varrenmoor-bridge\scripts\bridge.js` |
| `foundry-bridge/module/varrenmoor-bridge/scripts/pairing.js` (NEW) | `<Foundry Data>\modules\varrenmoor-bridge\scripts\pairing.js` |

Keep `relay-url.json` if it exists. `module/varrenmoor-bridge.zip` (all three files) was rebuilt too, for Add-on Modules > Update; use the zip route only after the branch is reachable by Foundry, otherwise copy the files. Nothing is pushed to Vega from here.

The relay side is already in this repo (`foundry-bridge/relay/pairing.js`, `server.js`, `daemon.mjs`, `bridgectl.mjs`, `relay-window.ps1`). The relay must be **restarted once** to load it (a relay started before this change has no pairing endpoints; the module keeps working with the manual token against it). In the Illustrator panel: Foundry tab > Restart (it asks first), or close the relay window and press Connect or launch.

## Steps
1. Copy the three files to Vega (above). Close all but one Foundry GM tab, then Ctrl+F5 in the remaining GM tab. Check the version: `.\bridge.ps1 version` shows `"module":"0.4.0"` (needs the manual token or a pairing to be connected already; if not, check Add-on Modules).
2. Make sure the relay PC (Arcturus) runs the new relay: Illustrator panel > Foundry > Restart (or Connect or launch if none is running). The relay window should print `pairing on`.
3. In the Foundry GM tab (open it as `http://VEGA:30000`, not an https address): Game Settings > Configure Settings > Module Settings > Varrenmoor Bridge. Set **Connect to relay** ON and **Relay address for pairing** to the relay PC's LAN address, e.g. `10.0.0.20:3030` (leave blank to let the button scan the /24). Press **Pair with relay**. A dialog shows a 6-digit code (if the button is missing, run `game.modules.get('varrenmoor-bridge').api.pair()` in the browser console, F12).
4. On the relay PC the relay window and the Illustrator panel (Foundry tab > Pair devices) show "Approve this device?" with the same code. If the codes are identical, press Approve (panel: pick an expiry; relay window: press A). If they differ, press Deny.
5. The module says "paired" and connects. From now on it connects with the device token automatically; Module token can stay empty. Revoke any time in the panel (Pair devices > Revoke).
6. Fallback if pairing is not wanted or fails: leave it unpaired and enter Relay URL + Module token as before.
7. Roll back: copy the 0.3.1 `module.json` and `bridge.js` back from git history and delete `scripts\pairing.js`; Ctrl+F5. (A paired relay file `run/paired-devices.json` is harmless.)

Security notes (details in `foundry-bridge/README.md`, "Pairing"): pairing works only from private LAN addresses and never through the Cloudflare tunnel; nothing is issued without your Approve; tokens are stored hashed on the relay; traffic is plain HTTP/WS inside your LAN, so do not pair on an untrusted network.

---

# Redeploying module 0.3.1 (4002 reconnect-loop fix)
0.3.1 changes only `scripts/bridge.js` (and the version in `module.json`): a client closed by the relay with code 4002 ("replaced by another GM tab") no longer reconnects, shows one warning, and "connected" notices are rate limited (1 per minute). The relay needs no change for this (a relay restart is only needed to pick up the new `/health` fields, optional).
1. Copy `foundry-bridge/module/varrenmoor-bridge/module.json` and `scripts/bridge.js` to `<Foundry Data>\modules\varrenmoor-bridge\` and `...\scripts\` on Vega (same two files as below; keep `relay-url.json` if present). The zip `module/varrenmoor-bridge.zip` was rebuilt too, for Add-on Modules > Update.
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
