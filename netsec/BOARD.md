# Netsec board (updated 2026-11-07)

Owners: User = Trent. Agent = Netsec agent (Claude).

## Doing
- [ ] (Agent) Await answers to the 3 questions in PLAN.md section 2 (domain? player count? who hosts?).

## Todo (in order)
1. (User) Answer the 3 questions. Decide: Cloudflare domain yes/no.
2. (User) Run the read-only audit on Vega itself (PLAN.md section 5, Part A). The audit already done ran on DESKTOP-ARCTURU, not Vega.
3. (User) Windows Update on Vega; change any weak/blank Windows passwords; confirm Foundry admin key is set.
4. (User) Back up Foundry `Config\options.json` and `Data\` (rollback safety).
5. (User) Create free Cloudflare account; add domain (or buy ~10 USD/yr via Cloudflare Registrar).
6. (Agent) Draft exact options.json edit + cloudflared config for the chosen hostname.
7. (User) Install/update cloudflared as a service on Vega; create tunnel to http://localhost:30000.
8. (User) Create Cloudflare Access app + One-time PIN policy with player emails; set session 7-30 days.
9. (User) Edit options.json (hostname, proxySSL, proxyPort, upnp false), restart Foundry.
10. (User + 1 player) Test from a phone on cellular: login, scene load, 5 min of play, reconnect after sleep.
11. (User) Tell players the new URL; run one real session through the tunnel while the port forward is still in place.
12. (User) Remove router port forward; disable router UPnP; narrow Windows firewall rule.
13. (User) Verify port closed from outside (PLAN.md section 6).
14. (User) Compromise review (PLAN.md section 6.8).
15. (Agent) Optional: Tailscale on GM PC + Vega for admin/SMB/RDP access instead of any exposure.

## Done
- [x] (Agent) Research and PLAN.md written 2026-11-07.
- [x] (Agent) Read-only local audit of this PC (AUDIT_2026-11-07.md).
