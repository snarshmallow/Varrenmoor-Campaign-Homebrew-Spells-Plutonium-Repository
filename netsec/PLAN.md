# Foundry VTT access without port forwarding - PLAN

Written 2026-11-07. Target: Foundry v14 on Vega (Windows), port 30000, 4-8 mostly non-technical players.
Tags on steps: **READ-ONLY** (safe, changes nothing) or **CHANGES-SYSTEM** (modifies PC, router, cloud account or Foundry).
Items marked (verify) came from third-party sources or could not be confirmed on an official page; re-check before relying on them.
Nothing in this plan has been executed. Never paste passwords, tunnel tokens or your public IP into files in this repo.

## 0. Background

The flood on the forwarded port is normal internet background scanning: any open port gets hit within minutes. The scanning itself is not proof of compromise. The real risks are (a) Foundry's login page is directly reachable by everyone, with no lockout on guesses, and (b) the Foundry Node server is exposed as-is. Removing the forward removes both. Section 5 covers checking whether anything got in during the exposure.

## 1. Comparison

| | Cloudflare Tunnel + Access | Tailscale (tailnet) | Tailscale Funnel | ZeroTier | Plain WireGuard |
|---|---|---|---|---|---|
| Player friction | Browser only: open URL, type email, type 6-digit emailed code, then Foundry login | Install app + sign in with an identity account, join/share node (hard for non-technical) | Browser only (public URL) | Install app + join network ID + GM approves | Install app + import config file (hardest) |
| Cost / limits | Tunnel free. Access free tier "up to 50 users" (verify; third-party sources; paid beyond about 7 USD/user/mo). Domain about 10 USD/yr | Personal plan free: up to 6 users, unlimited devices, non-commercial (tailscale.com/pricing). GM + 5 players fits; 7-8 players does not without a paid plan or node-sharing rules (verify) | Free on Personal (verify on live pricing table); bandwidth limits non-configurable and unpublished | Free tier has a device cap (was 10 in recent years, verify) | Free software; needs a reachable UDP endpoint |
| WebSocket for Foundry | Yes, supported by default. Access cookie rides the upgrade request. Gotcha: an open socket survives Access session expiry, but a reconnect after expiry needs re-auth, so set a long Access session (7-30 days) | Yes (plain TCP, no proxy) | Yes via Funnel/serve proxy (verify under load) | Yes | Yes |
| Latency | Adds an edge hop, typically tens of ms; fine for a VTT | Direct peer-to-peer when NAT allows, else DERP relay (slower) | Via Tailscale relay infrastructure | P2P or relay fallback | Direct, lowest |
| ToS / large assets | Highest concern. Cloudflare's CDN terms say video and "a disproportionate percentage of pictures, audio files, or other large files" must use Cloudflare's paid media services, and Cloudflare can limit the account (cloudflare.com service-specific terms, CDN section). The page does not say whether Tunnel traffic is judged under it. A small group sharing maps and tokens is very unlikely to trigger it, but do not push hours of video or large audio libraries through it. Free-plan request body limit is 100 MB, so very large uploads fail (verify). | None for private tailnet traffic | Non-configurable bandwidth caps; not meant for heavy media | None | None |
| Domain needed | Yes, a domain on Cloudflare DNS for a stable named tunnel. (Quick "trycloudflare" tunnels need none but have random URLs and cannot sit behind Access, so unsuitable) | No | No (free ts.net name) | No | No (but needs DDNS name or fixed IP for the endpoint) |
| Public exposure | Public hostname, but Access blocks everything until the email PIN passes. Scanners hit Cloudflare, not your home IP | None | Public: anyone can reach the Foundry login page; no pre-login gate. Only removes the router forward | None | One open UDP port; silent to unauthenticated packets, but still a port forward |
| Foundry hostname / proxy settings | `hostname` = public name, `proxySSL: true`, `proxyPort: 443`, no sslCert/sslKey (TLS ends at Cloudflare; cloudflared talks plain HTTP to localhost:30000) | Defaults; players use http://<tailscale name or IP>:30000 (insecure-origin browser limits may apply) | `hostname` = ts.net name, `proxySSL: true`, `proxyPort: 443` (or the Funnel port used) | Defaults, HTTP over ZeroTier IP | Defaults, HTTP over VPN IP |
| Fit for 4-8 non-technical players | Best | Poor for players, good for the GM | Acceptable stopgap, weak security | Poor | Poor |

Foundry options (foundryvtt.com/article/configuration): `hostname` replaces the public IP in invite/session addresses; `proxySSL` (boolean) says Foundry sits behind an SSL-terminating proxy so invite links and A/V behave as if SSL were on; `proxyPort` (integer) is the proxy's external port for invite links; `upnp` (default true) lets Foundry ask the router to open ports by itself; `routePrefix`, `sslKey`/`sslCert` also exist. Any value can be `null`. Malformed JSON stops Foundry starting, so back up `Config\options.json` first. The docs page does not list a "disable admin" key; the admin access key is stored encrypted in `Config\admin.txt`.

## 2. Recommendation

**Primary: Cloudflare Tunnel + Cloudflare Access with One-time PIN for the players. Tailscale (free Personal plan, GM only) for admin: RDP, SMB share, off-site file access.**

Reasons:
- Players need nothing installed. They bookmark https://foundry.yourdomain and enter an email code. For 4-8 non-technical people this is the only option with no support burden.
- Nothing is opened on the router. Hostile scanners reach Cloudflare's edge, and Access rejects them before any request touches Foundry. That also covers Foundry's missing brute-force lockout.
- Tailscale for players fails on friction and on the free 6-user cap. Funnel only moves the exposure; Foundry's login stays reachable by anyone and bandwidth caps are opaque. ZeroTier/WireGuard add friction without beating Cloudflare for this audience.
- Keep the GM off the tunnel: the GM plays from Vega or the LAN at http://localhost:30000 or http://<lan-ip>:30000, which keeps the Varrenmoor bridge module on its local path (Section 6).

Costs and risks accepted: a domain (about 10 USD/yr), Access login every 7-30 days, no Foundry built-in A/V through the tunnel (use Discord), uploads over 100 MB done locally, and residual ToS risk on heavy media (mitigation: Foundry supports S3-compatible storage through `awsConfig`, and Cloudflare R2 is a permitted place for large files; only needed if you start serving lots of audio/video).

Fallback if no domain: Tailscale tailnet for everyone (6-user cap on free) or Funnel (public, Foundry password strength as the only gate).

**Questions the user must answer:**
1. Do you have, or will you buy, a domain name (Cloudflare Registrar sells at cost)?
2. How many players, and can you list their email addresses now (Access allows by email)? More than 5 players rules out free Tailscale for everyone.
3. Who hosts: Foundry stays on Vega 24/7, or does the GM sometimes run it from another PC (the tunnel and firewall steps must be done on whichever machine runs Foundry)?

## 3. Setup on Vega

Part A - baseline (on Vega itself)

A1 **READ-ONLY** Confirm Foundry is listening and where, in PowerShell:
`Get-NetTCPConnection -LocalPort 30000 -State Listen | Select LocalAddress,LocalPort,OwningProcess`
`Get-NetTCPConnection -State Listen | Sort LocalPort | Select LocalAddress,LocalPort,OwningProcess`
A2 **READ-ONLY** Note Foundry's data folder (launcher > Configuration > Data Path; default `%localappdata%\FoundryVTT`; the bridge README hints yours may be `C:\FoundryVTT resources`). Under it: `Config\options.json`, `Config\admin.txt`, `Logs\`, `Data\`.
A3 **READ-ONLY** List firewall rules touching Foundry/Node/30000:
`Get-NetFirewallRule -Enabled True -Direction Inbound -Action Allow | ?{ $_.DisplayName -match 'Foundry|Node|30000' } | Select DisplayName,Profile`
A4 **CHANGES-SYSTEM** Run Windows Update to current; update Foundry to the latest stable v14 build; restart.
A5 **CHANGES-SYSTEM** Back up `Config\options.json` and `Config\admin.txt` (copy beside them with `.bak`) and make a world backup.
A6 **READ-ONLY** Screenshot the router's current port-forward rule and UPnP page (needed for rollback).

Part B - Cloudflare account and domain

B1 **CHANGES-SYSTEM** Create a free Cloudflare account; enable two-factor auth (authenticator app).
B2 **CHANGES-SYSTEM** Register a domain at Cloudflare Registrar, or add an existing domain and switch its nameservers to Cloudflare. A dedicated cheap domain is simplest.
B3 **CHANGES-SYSTEM** Open Zero Trust (one.dash.cloudflare.com), pick the Free plan, choose a team name. (Menu names move; look for Networks > Tunnels and Access > Applications.)

Part C - Tunnel

C1 **READ-ONLY** Check cloudflared: `cloudflared --version`. (The dev PC has 2026.9.3 installed but unconfigured; Vega is separate.) If missing: `winget install Cloudflare.cloudflared` (**CHANGES-SYSTEM**).
C2 **CHANGES-SYSTEM** Zero Trust > Networks > Tunnels > Create a tunnel > Cloudflared, name `vega-foundry`, Windows. The page shows an install command containing a long secret token. Run it in an Administrator PowerShell on Vega (`cloudflared.exe service install <token>`). Treat the token like a password; do not paste it into chat, files or git.
C3 **CHANGES-SYSTEM** Add a public hostname: subdomain `foundry`, your domain, service type HTTP, URL `localhost:30000`. Save (this also creates the DNS record). Do not use HTTPS here.
C4 **READ-ONLY** `Get-Service cloudflared` shows Running; the tunnel shows Healthy in the dashboard.

Part D - Access gate (do before telling anyone the URL)

D1 **CHANGES-SYSTEM** Access > Applications > Add > Self-hosted. Application domain `foundry.yourdomain`. Session duration 7 to 30 days (long, so websocket reconnects do not hit re-auth).
D2 **CHANGES-SYSTEM** Policy "Players": Action Allow, Include > Emails > each player's exact email plus yours. (Group rules do not work with One-time PIN; use emails.) Login method: One-time PIN only.
D3 **CHANGES-SYSTEM** Second application, same host, path `/setup*` (and `/license*`), policy Allow only your own email, keeping Foundry's admin Setup GM-only at the edge. Confirm in testing that the more specific path wins (verify).
D4 **CHANGES-SYSTEM** Cloudflare dashboard > Security > WAF > Rate limiting: limit POSTs to `/join` (Foundry login) to roughly 10 per minute per IP (free plan allows few rules; verify).

Part E - Foundry config

E1 **CHANGES-SYSTEM** Close Foundry. Edit `Config\options.json` (keep valid JSON and other keys):
```
"hostname": "foundry.yourdomain",
"proxySSL": true,
"proxyPort": 443,
"sslCert": null,
"sslKey": null,
"upnp": false,
"port": 30000
```
Foundry's own articles vary the casing (`proxySSL` vs `ProxySSL`); match what the configuration article and your existing file use (verify).
E2 **CHANGES-SYSTEM** Start Foundry; confirm http://localhost:30000 still works for the GM.

Part F - Test while the old forward is still on

F1 **READ-ONLY** On a phone with wifi OFF, open https://foundry.yourdomain: expect the Access email prompt, not Foundry. An email not on the list gets no code.
F2 **READ-ONLY** Enter your email and code, join as a test player, load a scene, idle 10 minutes, lock/unlock the phone, confirm reconnect.
F3 Have one real player try, then run one real session through the tunnel.

Part G - Cut over

G1 **CHANGES-SYSTEM** Delete the router port forward for 30000. Turn off router UPnP.
G2 **CHANGES-SYSTEM** Tighten Windows Firewall (4.2).
G3 **READ-ONLY** Verify closed from outside (4.6).

Part H - Optional GM Tailscale

H1 **CHANGES-SYSTEM** Install Tailscale on Vega and the GM laptop (same account). Use it for RDP and `\\VEGA\...` off-site. Do not enable Funnel.
H2 **CHANGES-SYSTEM** Then restrict RDP to the Tailscale interface / LAN rather than all networks.

## 4. Hardening checklist

4.1 **CHANGES-SYSTEM** Router: remove the 30000 forward (and any 445, 3389, 5900, 22, 139 forwards). Disable UPnP/NAT-PMP. Change the router admin password, update firmware, disable remote (WAN) administration. Foundry's own `upnp` defaults to true and can re-open the port by itself, so E1 sets it false.
4.2 **CHANGES-SYSTEM** Windows Firewall on Vega. The existing "Foundry Virtual Tabletop" rules allow the Foundry exe on Private and Public, any remote address, any port. Replace them: disable those rules; add one inbound TCP 30000 rule, profile Private only, remote address `LocalSubnet`. Loopback traffic (cloudflared to localhost) is not blocked by the firewall, so the tunnel keeps working while the Internet cannot reach 30000. Disable the UDP Foundry rule (only used for A/V you do not need here). Set the home network profile to Private. Display-only check first: `Get-NetFirewallRule -DisplayName 'Foundry*' | Get-NetFirewallPortFilter` (**READ-ONLY**).
4.3 Foundry admin: set an Administrator Access Key (Foundry Setup screen) that is 16+ characters, unique, in a password manager. It lives encrypted in `Config\admin.txt`. The `--adminPassword` flag only sets a key if none exists. Never expose Setup without D3.
4.4 Player/GM policy (Setup > world > Configure Players): GM password 16+ chars and unique. Every player has a password (no blank), unique, not reused from email; players change it on first login. Keep players on the Player role; do not grant Trusted/Assistant unless needed (Game Settings > Configure Permissions: keep script-macro creation, file upload and file browsing off for Player). Delete unused users. Rotate everyone's passwords after the incident review.
4.5 Brute-force protection (fail2ban equivalents): Foundry has no built-in lockout and logs failed logins to its own log, not the Windows event log, so tools like IPBan (reads Windows Security events) will not see them. Practical equivalents: Cloudflare Access (nothing reaches Foundry unauthenticated), the D4 WAF rate limit, and the `/setup` policy. For Windows logons (RDP/SMB) enable failed-logon auditing (`auditpol /set /subcategory:"Logon" /failure:enable`, **CHANGES-SYSTEM**) and consider IPBan only if RDP is ever reachable; simplest is to keep RDP off the Internet.
4.6 Verify the port is closed from outside **READ-ONLY but sends one probe**: from a phone on cellular (wifi off) open `http://<your-public-ip>:30000`; it must time out. Look up your public IP yourself and do not store it in the repo. Or use a third-party scanner for TCP 30000, 3389, 445, 5900 (for example GRC ShieldsUP custom ports). Also confirm the router's UPnP mapping table is empty. Re-test after any router or Foundry update.
4.7 Update posture: Windows Update on, restart weekly; Foundry stable updates before each campaign season; keep cloudflared current (`cloudflared update` or winget; the service does not auto-update on Windows, verify); minimal modules from the official package manager; router firmware quarterly.
4.8 Router logging: before cutover enable firewall/WAN logging and export the flood log (count distinct source IPs and destination ports) to see whether 30000 was the only target. After cutover, scans should hit nothing. Keep the log out of the repo (it holds IPs).
4.9 Follow-ups from the audit: see AUDIT_2026-11-07.md (RDP enabled, Chrome Remote Desktop/TightVNC/HudSight allow rules on all profiles, Trent PasswordRequired false, Minecraft rule). Repeat that audit on Vega itself.

## 5. Compromise check (before and after cutover; on Vega)

All steps READ-ONLY unless noted.
- Foundry user list: Setup > world > Configure Players. Look for unknown users, unexpected GM-role accounts, players with Trusted/Assistant/GM role.
- Foundry logs: `%localappdata%\FoundryVTT\Logs` (or your data path's `Logs`). `Select-String -Path "<Logs>\*.log" -Pattern 'fail|invalid|admin|unauthor'`. Look for admin-key use at odd hours and unfamiliar sources.
- Foundry content: new or modified scripts/executables in Data: `Get-ChildItem "<Data>" -Recurse -Include *.js,*.html,*.exe,*.ps1,*.bat | Sort LastWriteTime -Desc | Select -First 30 FullName,LastWriteTime`. Check `Data\modules` and `Data\systems` for packages you did not install and world macros with script bodies.
- Scheduled tasks outside Microsoft: `Get-ScheduledTask | ?{ $_.TaskPath -notmatch '^\\Microsoft\\' } | Select TaskPath,TaskName,State`. Investigate unknown names, especially those launching PowerShell/cmd or files in Temp/AppData.
- Local users and admins: `Get-LocalUser`, `Get-LocalGroupMember Administrators`. Any account you did not create is a red flag.
- Persistence: Run keys (`HKLM` and `HKCU` `...\Windows\CurrentVersion\Run`), automatic services, Startup folders.
- Network: `Get-NetTCPConnection -State Established | Select RemoteAddress,RemotePort,OwningProcess` and map to process names; `Get-NetTCPConnection -State Listen`. Unknown listeners or outbound sessions need investigating.
- Logons: Event Viewer > Security events 4624 (type 10 is RDP, 3 is network) and 4625; Terminal Services RemoteConnectionManager event 1149 for RDP connections.
- Run a full Microsoft Defender scan (**CHANGES-SYSTEM**, light) and, if suspicious, a second-opinion scanner.
- If anything looks wrong: take Vega off the network; change the Windows account password, Foundry admin key, all Foundry passwords, router admin password and any reused passwords; rotate the tunnel token; consider a clean Windows reinstall. Regenerate bridge `.env` tokens by rerunning `start.bat`.

## 6. What will break or change

Fact-check of this repo (from foundry-bridge/README.md, bridge.js, foundry-3d/.env):
- The bridge module connects outward from the GM's browser to the relay, not to Foundry's port. Default relay URL is `ws://127.0.0.1:3030/module`; with `autoUrl` it reads `relay-url.json` written by `start.bat`, which is a Cloudflare QUICK tunnel (`wss://...trycloudflare.com/module`) to the relay on 127.0.0.1:3030. I found no code in the repo connecting to `localhost:30000`; if you know of one elsewhere, it is a loopback connection and the Foundry tunnel does not touch it. The new named tunnel is separate from the quick tunnel and does not interact with it.
- The module websocket stays local as long as the GM loads Foundry from Vega or LAN over `http://localhost:30000` or `http://<lan-ip>:30000`. Recommendation: the GM does not use the public URL. If the GM does use the public https URL from another machine, the page tries `ws://127.0.0.1:3030` on THAT machine (the relay is on Vega) and fails, and recent Chrome versions may also prompt about local-network access from an https page (verify). The quick-tunnel `wss` path works from anywhere but is a separate public relay protected only by tokens; run `start.bat` only when needed.
- SMB share `\\VEGA\varrenmoor-3d` (`FOUNDRY_ASSETS_DIR`) and `\\VEGA\C\FoundryVTT resources\bridge\client.json`: LAN SMB on port 445, unrelated to Cloudflare Tunnel and port 30000. Unaffected; the firewall change in 4.2 only scopes port 30000. Never forward 445; use Tailscale for off-site SMB.
- Foundry `hostname` change only affects displayed/invite addresses. `localhost:30000` keeps working. Old bookmarks to the public IP stop working (intended); send players the new https link.
- Built-in A/V (WebRTC) does not pass through the tunnel. Use Discord or similar.
- Uploads over about 100 MB through the tunnel fail on the free plan (verify); the GM uploads big files locally.
- Players log in twice: Access email code, then Foundry password. By design.
- If Vega is off, cloudflared is down and the site is down. The service auto-starts with Windows.
- Players on school/corporate networks that block new domains may fail; test them.

## 7. Rollback

Each step is reversible; earlier steps leave the other path working.
1. **CHANGES-SYSTEM** Pause the Access application (disable it) or delete the tunnel's public hostname. Players lose the tunnel path only.
2. **CHANGES-SYSTEM** Restore `Config\options.json` from the `.bak` made in A5 (or revert hostname/proxySSL/proxyPort/upnp) and restart Foundry.
3. **CHANGES-SYSTEM** Stop the tunnel: `cloudflared service uninstall` (admin PowerShell). Delete the tunnel in the dashboard (invalidates the token).
4. For an urgent return to the old model: re-add the router forward from the A6 screenshot, re-enable the old Foundry firewall rule, and accept the exposure temporarily with 4.3 and 4.4 in place.
5. Remove the DNS record and Access apps in Cloudflare if abandoning permanently.
Nothing here modifies Foundry world data; the A5 backup covers mistakes.

## 8. Sources (checked 2026-11-07)

- Foundry configuration options: https://foundryvtt.com/article/configuration/ (also /article/nginx/, /article/apache)
- Cloudflare service-specific terms, CDN section: https://www.cloudflare.com/service-specific-terms-application-services/ ; https://blog.cloudflare.com/updated-tos/
- Tailscale pricing (Personal: 6 users, non-commercial): https://tailscale.com/pricing ; Funnel ports 443/8443/10000 and non-configurable bandwidth limits: https://tailscale.com/kb/1223/funnel
- Third-party only (verify against Cloudflare docs): Access free up to 50 users, OTP counts one user per email, WebSocket cookie behaviour, 100 MB free request limit.
