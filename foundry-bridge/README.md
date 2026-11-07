# Varrenmoor Foundry Bridge (v0.1, untested against a live world)

```
Claude (HTTPS) --POST /rpc, Bearer API token--> relay --WebSocket--> Foundry module (GM browser tab)
```

Foundry modules run inside a GM's browser, so **a GM client must be open** (a dedicated browser window on the Foundry PC works). The module connects *outward* to the relay; nothing new is opened on the Foundry server itself.

## Ops
Read: `ping`, `world_info`, `list {collection,type?,nameContains?}`, `get {uuid}`, `audit_activities` (flags Activity IDs that are not 16 alphanumeric chars), `scene_stats`, `perf_sample {ms}` (FPS/long-frame sample; run it while moving a token with vision on).
Write (off unless the world setting **Allow writes** is on): `create`, `update`. There is no delete op, and no arbitrary code execution.

## Quick start (recommended)
Install Node 20+ and `cloudflared`, then run `start.bat` (Windows) or `./start.sh`. It installs deps, generates tokens into a git-ignored `.env`, starts the relay on 127.0.0.1, opens a Cloudflare quick tunnel, self-tests it, and prints exactly what to enter in Foundry and in the Claude environment.

## Current topology: GM and relay on Arcturus (LAN, no tunnel)
Foundry (the server) stays on VEGA. The GM plays in a browser on ARCTURUS at `http://VEGA:30000` (or Vega's LAN IP), and the relay runs on ARCTURUS next to Claude and Illustrator. Players will later reach Foundry through the netsec Cloudflare tunnel (`netsec/PLAN.md`); the GM keeps using the LAN address.
1. On Arcturus: `start.bat --local` (remembered as `TUNNEL=off` in `.env`). No tunnel; the relay listens on all interfaces at port 3030, because a page served from `http://VEGA:30000` may not open `ws://127.0.0.1`. Allow Node.js on **Private** networks if Windows Firewall asks.
2. In the Arcturus GM browser, Varrenmoor Bridge settings: Connect ON, **Use launcher relay URL OFF** (that file lives on Vega and would point at a Vega relay), Relay URL = the `ws://<arcturus-lan-ip>:3030/module` the launcher prints, Module token = `BRIDGE_MODULE_TOKEN` from Arcturus's `.env`. Then F5.
3. `.\bridge.ps1 list -Args '{"collection":"Scene"}'` on Arcturus: it reads `foundry-bridge\client.json` (written by the launcher, git-ignored) and calls `http://127.0.0.1:3030`.
4. Run only one relay. On Vega remove `Startup\Varrenmoor Bridge.lnk`, stop its `node start.mjs` and `cloudflared`, and delete `Data\modules\varrenmoor-bridge\relay-url.json` and `<dataPath>\bridge\client.json`.
5. No URL changes across reboots in local mode. Only re-enter the module token when you rotate it. If Arcturus's LAN IP changes, update the Relay URL (a DHCP reservation avoids this).
6. Asset writes from Arcturus go to `\\VEGA\varrenmoor-3d` (Vega's `Data\assets\varrenmoor-3d`, seen by Foundry as `assets/varrenmoor-3d/...`).

`BIND_HOST` in `.env` overrides the listen address (default: `127.0.0.1` with a tunnel, `0.0.0.0` with `--local`). Local mode sends tokens in plain text over the home LAN; keep it off untrusted networks.

## Manual install
1. In Foundry: Add-on Modules > Install Module > Manifest URL: `https://raw.githubusercontent.com/snarshmallow/Varrenmoor-Campaign-Homebrew-Spells-Plutonium-Repository/claude/adoring-shannon-yjixst/foundry-bridge/module/varrenmoor-bridge/module.json` (change `claude/adoring-shannon-yjixst` to `main` after merging; rebuild `module/varrenmoor-bridge.zip` whenever the module changes). Then enable it in the world.
2. On a machine that can run Node 20+: `cd relay && npm install`, then set two different random tokens (24+ chars) and run:
   `BRIDGE_API_TOKEN=... BRIDGE_MODULE_TOKEN=... HOST=0.0.0.0 PORT=3030 node server.js`
3. Put TLS in front of the relay (Caddy/nginx/Cloudflare Tunnel) before exposing it to the internet. Do not expose plain HTTP; tokens travel in headers.
4. In Foundry (GM client): Module Settings > Varrenmoor Bridge: enable, set relay URL (`wss://your-host/module`) and the **module** token.
5. Give Claude the HTTPS URL and the **API** token via the environment's secrets, and add the host to the environment's allowed domains.

## Security notes
- Two separate tokens; compare in constant time; module auth times out after 5 s; one module connection at a time.
- Use a dedicated GM user for the bridge tab if you want it distinguishable in logs.
- Rotate tokens if the tab is ever left open on a shared machine.

## Auto-config for Claude Code on another PC (no secrets to paste)
`start.bat` (and `node publish-client.mjs`, if the relay is already running) writes `<Foundry dataPath>\bridge\client.json` with the live tunnel URL and API token. It sits outside `Data/`, which Foundry serves to players. On the other PC, `foundry-bridge\bridge.ps1 <op> [-Args '<json>']` finds it at `\\<host>\C\FoundryVTT resources\bridge\client.json` by itself (host guessed from `foundry-3d\.env`, default VEGA). Quick-tunnel URLs change on restart; `start.bat` rewrites the file each time. Overrides: `-Config <file>`, or env `FOUNDRY_BRIDGE_URL` + `FOUNDRY_BRIDGE_TOKEN`. The Claude environment secrets screen is for cloud sessions only; a local CLI session does not read it.
