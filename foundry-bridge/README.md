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
