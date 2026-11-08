# Security review: LAN pairing, encrypted handshake, signed admin calls

Branch claude/adoring-shannon-yjixst, module 0.5.1, protocol 2. Read-only review of the files listed in the brief. Two findings (F1, F2) were reproduced with throwaway relays on port 8799 (scripts were kept outside the repo). Everything else is by code reading. "Unverified" marks what I could not check.

## Summary table

| # | Severity | Finding |
|---|----------|---------|
| F1 | HIGH | Unauthenticated remote crash of the relay: a WebSocket message `null` kills the process (reproduced). Reachable through the Cloudflare quick tunnel in start.bat mode. |
| F2 | MEDIUM | Unauthenticated LAN crash: an aborted POST body to any `/pair/*` route raises an unhandled rejection, and daemon.mjs exits on it (reproduced). |
| F3 | MEDIUM | Module executes ops sent by a server before (or without) the relay proof, so the "fake relay is detected" claim does not hold for a rogue server. Combined with relay relocation by public relayId. |
| F4 | MEDIUM | Approval does not bind the human to the code: Approve is one click, and the relay window "A" key approves the oldest pending request blindly. A hostile web page or LAN host can file a lookalike request. |
| F5 | MEDIUM | CORS `*` + private-network header on all pairing endpoints: any web page open in a LAN browser can file/flood pairing requests, burn the GM browser's per-IP quota, and show its own fake code. No Origin allow-list. |
| F6 | MEDIUM | The Cloudflare quick tunnel in `start.mjs` points at the RELAY (127.0.0.1:3030), so the tunnel does reach the relay in tunnel mode; the pairing refusal rests only on a header blacklist (fails open for header-less proxies). |
| F7 | MEDIUM | API token reaches clear-text paths regardless of signed admin calls (`bridge.ps1` /rpc Bearer); token on a share; unverified share ACL. Whoever has the token owns the world. |
| F8 | LOW | An API-token-looking file `client.json.arcturus-old-2026-11-08` is untracked and NOT git-ignored (one `git add -A` commits a token). |
| F9 | LOW | Windows: `mode 0o600` is a no-op; `.env`, `run/paired-devices.json`, `client.json` inherit ACLs (here: Users read / Authenticated Users modify). Device secrets stored in clear (inherent to HMAC design). `prevSecret` is kept on disk after its 5 min grace. |
| F10 | LOW | Module: any 4005 close, from anyone at the stored host, makes the module delete its credential before the relay is authenticated. Relay-supplied strings go into `ui.notifications` (HTML escaping by Foundry unverified). |
| F11 | LOW | Pairing-request DoS: 5 committed requests (never revealed) globally block a legitimate pairing for 2 min; unauthenticated polls and cancel use a pollSecret that travels in clear. |
| F12 | LOW | Admin replay window: nonce cache is in memory, so a captured signed request can be replayed within 5 min after a relay restart. No throttling of admin auth failures (token is 192-bit, so not exploitable). |
| F13 | LOW | `/health` and close reasons leak minor info (pid, uptime, device counts; "device unknown device" vs "bad credentials" contradicts the comment that ids cannot be probed). |
| F14 | INFO | 6-digit SAS: adequate given the commitment; notes on grinding, parallel sessions and IPv6. |
| F15 | INFO | Crypto design (HKDF separation, AAD, nonces, MAC labels, reflection) reviewed: no flaw found. |
| F16 | INFO | Noble bundle versions and licence. Bundle contents unverified. |

---

## F1 HIGH: `null` WebSocket frame crashes the relay (pre-auth)

`relay/server.js` `ws.on('message')` parses JSON, then reads `m.type` on the parsed value. `JSON.parse('null')` returns `null`, so `m.type` throws a TypeError inside an EventEmitter listener, which is an uncaught exception. Nothing is authenticated at this point.

Reproduced: relay on 127.0.0.1:8799, client sends the text frame `null` to `/module`: process reports `uncaughtException: Cannot read properties of null (reading 'type')`. `daemon.mjs` installs `uncaughtException -> die()` so the managed relay exits; `start.mjs` has no handler so node exits.

Failure scenario: anyone who can open a TCP connection to port 3030 stops the bridge. On the LAN that is any guest device when bound to 0.0.0.0 (TUNNEL=off). In start.bat tunnel mode the trycloudflare URL reaches `/module` from the internet (see F6), so any stranger who learns or guesses the hostname can do it. The same pattern exists after auth (`pending.get(m.id)` with a null `m`), but only the authenticated module can reach it.

Fix: after parse, `if (!m || typeof m !== 'object') return;` (also in the authed branch). Add a process-level safety net that logs and continues for non-fatal errors rather than `die()`. Add a test that sends `null`, `[]`, `"x"`, `5`.

## F2 MEDIUM: aborted request body crashes the relay (LAN, pre-auth)

`readJson` does `for await (const chunk of req)`. If the client resets the connection mid-body, the iteration rejects ("aborted"). The `http.createServer(async ...)` handler has no catch, so it becomes an unhandled rejection; `daemon.mjs` handles it with `die()`.

Reproduced: raw socket sends `POST /pair/request` with `Content-Length: 500` and a partial body, then closes: `unhandledRejection -> aborted`. The source-address and proxy checks happen before `readJson`, so this needs a private source address (LAN host, or loopback behind a header-less proxy). The `/rpc` handler has the same shape but is behind the bearer token.

Fix: wrap the whole request handler in try/catch (and attach `req.on('error', ...)`), return 400 on read errors. Do not exit the daemon on `unhandledRejection` for a single request.

## F3 MEDIUM: module processes ops before the relay has proved itself

`module/.../bridge.js` `ws.onmessage`: only `challenge` and `welcome` are gated on `auth`. Any other message with an `id` falls through to `handle(m.op, ...)` regardless of whether a `welcome` with a valid proof was received (`welcomed` is never checked). A server that does not know the device secret simply sends `{id, op:'get', args:{uuid}}` right after the socket opens and the module answers with Foundry documents (`get`, `list`, `world_info`, `find_by_flag`); with "Allow writes" on it also executes writes. The README claim "the relay proves it knows the secret too, so a fake relay is detected and the module refuses to talk to it" is therefore only true for the welcome message, not for the data path.

How a rogue server gets in: (a) ARP/DNS tricks or taking over the relay PC's old IP; (b) the relocation logic: after 3 failed connects the module scans its /24 and adopts any host whose `/discover` shows the same `relayId` (`saveDevice({...dev, host: f.host})`). `relayId` is public (`/discover`, no secret), so a LAN host copies it and is adopted. (c) the manual-token mode (no `auth`) has the same behaviour, and sends the module token in clear to whatever URL is configured (pre-existing).

Fix: in `onmessage`, drop everything until `welcomed` is true (for paired mode) and close the socket on any pre-welcome op message. Make relocation require the candidate to pass the HMAC challenge before the host is saved (do a hello/challenge/proof round trip first, close, then save). Consider a relay public key pin instead of a bare relayId.

## F4 MEDIUM: nothing forces the human to actually compare the code

The 6-digit code only protects if the human compares it with a code shown by a legitimate device. Weaknesses in the approval side:
- The panel's Approve button and the relay window's `A` key do not require entering or confirming the code. `attachPairingConsole` approves `pairing.list().pending[0]`, the oldest request, whatever is on the screen. A hostile request filed seconds earlier is approved by an eager `A`.
- A request from a lookalike origin shows only as text (name is chosen by the requester; `deviceName` like "Foundry GM Trent (Windows browser)"). The `originMismatch` warning only appears when the requester's claimed origin differs from its real `Origin`; an honest malicious page (origin https://evil.example) shows no warning. Nothing flags "origin is not the Foundry host".
- A hostile page can display its own "code" dialog (it computes the same SAS), so "both screens show the same code" can be satisfied against an attacker's page if the human does not check which window the code came from.

Failure scenario: GM has pairing on and auto-request on (defaults). A web page the GM visits (F5) files a request at the moment the GM expects Foundry's own request; GM sees a code in the panel, looks at the fake dialog, approves. The attacker's browser now holds a device secret. Impact: it can authenticate as "the module" (receive Claude's ops and answer them with fake data, see write payloads), not read Foundry directly; combined with a Claude session writing to Foundry this leaks the content and lets the attacker lie to Claude.

Fix: make the human TYPE the code shown on the Foundry screen into the panel / window (3 attempts, then deny); in the relay window require `A <code>`; print only the request that matches. Show the real `Origin` prominently and warn unless it equals the expected Foundry origin (relay can learn it from the first approved device or a setting). Optionally auto-deny requests whose browser `Origin` is not `http://<this host or private IP>:30000`. Show "age" so a request older than the device's dialog is suspicious.

## F5 MEDIUM: open CORS and no Origin check on pairing endpoints

`pairRoutes` answers every route with `access-control-allow-origin: *` and `access-control-allow-private-network: true`, including preflights, and never examines `Origin` or `Host`. Any web page in the GM's (or any LAN) browser can therefore call `/discover`, `/pair/request`, `/pair/reveal`, `/pair/poll`, `/pair/cancel` and read the replies. Source IP is the GM's LAN address, so the "private source" gate passes. DNS rebinding is irrelevant because CORS is already open; `Host` is not checked either way.

Impact: (1) nuisance and the lookalike request in F4. (2) Quota burn: limits are per source address, 5 requests per 10 min and 2 pending per address. A page running on the GM's machine consumes the GM browser's own budget, so the real Foundry module is answered 429. (3) Information: relayId, pairing state. Admin routes still need the API token or signature, which a cross-origin page cannot produce, so there is no admin bypass here.

Fix: device endpoints: if `Origin` is present, require it to be an allow-listed Foundry origin (host = the relay's own host or its LAN address on 30000, configurable) else 403. Admin endpoints: send no CORS headers at all (the panel is Node, not a browser, and does not need them) and reject any request carrying an `Origin` header. Keep `Access-Control-Allow-Private-Network` only for the allow-listed origin.

## F6 MEDIUM: the Cloudflare tunnel does reach the relay in tunnel mode

The brief assumes the tunnel presents requests to Foundry, not to the relay. That is true for the Foundry player tunnel (not in this repo), but `start.mjs` (start.bat without `--local`) runs `cloudflared tunnel --url http://127.0.0.1:<PORT>` which is the relay itself, and `/rpc`, `/health`, `/module` are exposed on `https://<random>.trycloudflare.com`. README says the same ("a tunnelled Claude"). On this PC `.env` has `TUNNEL=off` and the daemon never starts a tunnel, so the current setup is not exposed; but `start.bat` plus removing that line would be.

In that mode every tunnelled request arrives from 127.0.0.1 (a private address). The only thing separating a tunnelled caller from the local panel is the header blacklist in `PROXY_HEADERS`: `cf-connecting-ip`, `cf-ray`, `x-forwarded-for`, `x-forwarded-host`, `forwarded`, `x-real-ip`. Cloudflare always adds `CF-Connecting-IP`/`CF-Ray`, and a client cannot remove them, so the quick tunnel is covered today. But:
- It is fail-open. Any path that reaches the relay from loopback or a private address without those headers is treated as local: another reverse proxy on the same PC that does not forward/add them (Caddy/nginx default adds `X-Forwarded-*` only if configured; many setups do), `ssh -R`, `tailscale serve`/TCP forwards, `cloudflared access tcp`, WARP private routing, a router port-forward with hairpin NAT. The README recommends "put TLS in front of the relay (Caddy/nginx/Cloudflare Tunnel)", which creates exactly this situation. Behind such a proxy, `/pair/approve`, `/pair/config` and `/pair/list` are still protected by the API token, but `/pair/request` and the whole device flow become reachable from the internet and F4's approval-by-eye is the only barrier.
- IPv4-mapped and IPv6 forms are handled safely: `isPrivateIp` fails closed for non-canonical forms (tested: `::ffff:7f00:1`, `0:0:0:0:0:0:0:1`, `::ffff:0:10.0.0.5`, `fec0::1`, CGNAT 100.64/10 all refused; `::ffff:10.0.0.5`, `fe80::1`, `fd12::1` accepted). Node reports canonical forms, so this is fine. Spoofing `X-Forwarded-For` can only make requests MORE refused.

Fix: prefer a positive signal over a blacklist. Bind a second listener (or a flag) so the pairing/admin routes exist only on a socket that is not the tunnel target, e.g. run the tunnel to a separate loopback port that serves only `/rpc` and `/module` (token paths), and serve `/discover` and `/pair/*` only on the LAN listener; or when `TUNNEL`/`PUBLIC_URL` is set, require a private non-loopback source for pairing. Also refuse when `Host` is a public name (`*.trycloudflare.com` or anything not an IP literal/`localhost`/the PC name). Also expose a startup warning in tunnel mode.

## F7 MEDIUM: the API token is the keys to the kingdom and travels in clear

- `/rpc` requires `Authorization: Bearer <API token>`; `bridge.ps1` sends it for every call to `http://<relay>:3030` over the LAN. A passive sniffer on the LAN therefore sees the token (the README acknowledges this). The same token is accepted as Bearer for every admin route, so signed admin calls add no protection against anyone who has sniffed one `/rpc`. Possession of the token = full read/write of the world through the module (when writes are on) and approval of devices.
- `client.json` (API token and also `moduleToken`) is written to `<Foundry dataPath>\bridge\client.json` and read over `\\<host>\C\FoundryVTT resources\bridge\client.json`. The share name `C` implies the whole C: drive (or a folder) shared; who can read, and importantly who can WRITE, is unverified (this PC only has the default admin shares). Anyone who can write `client.json` can replace `url` and the next `bridge.ps1` call sends the real Bearer token to the attacker's host.
- The panel does the right thing: it signs, keeps tokens in memory only, masks them (Reveal button), and uses `execFile` without a shell.

Fix: serve `/rpc` over TLS (Caddy/stunnel on the relay PC) or add an HMAC-signed variant of `/rpc` for `bridge.ps1` and drop Bearer for `/pair/*`; restrict the share to the one folder with read-only access for the single account that needs it, and make `bridge.ps1` refuse a `client.json` `url` whose host differs from the host it was read from. Rotate the tokens after the share has ever been open to others.

## F8 LOW: stray token file not ignored by git

`foundry-bridge/client.json.arcturus-old-2026-11-08` contains `"token"` (API token, key redacted here) and is untracked. `.gitignore` lists `client.json` and `bridge/client.json` only, so this renamed copy is not ignored. A `git add -A` / `git add .` stages it, and a push puts a token in GitHub (the repo is private, but anything pushed counts as shared). The file records `http://127.0.0.1:3030`, so it may be an old token; still rotate if it equals the current one.
Fix: delete or move it (routine cleanup is allowed), add `client.json*` to `foundry-bridge/.gitignore`.

## F9 LOW: secrets at rest on Windows

- `fs.writeFileSync(..., { mode: 0o600 })` and the README claim "mode 0600" have no effect on NTFS. Files get inherited ACLs. On this PC `D:\...\foundry-bridge` is inheriting `BUILTIN\Users:(RX)` and `Authenticated Users:(M)`; `.env` is therefore readable by every local account (same for the relay PC unless its ACLs differ; unverified there). `client.json` written via `writeFileSync` without a mode behaves the same way.
- `run/paired-devices.json` holds each device secret in clear (needed for HMAC verification) and `prevSecret` stays in the file after its 5-minute grace has passed (`prevUntil`), so a rotated-out secret never leaves disk until the next rotation.
- The module stores the secret in the Foundry client setting `deviceAuth` (browser localStorage for that origin); any other Foundry module or script on the same origin can read it. Inherent.

Fix: on Windows run `icacls <file> /inheritance:r /grant:r "%USERNAME%:F"` for `.env`, `run\` and the client file (or create `run/` once with that ACL); delete `prevSecret` when `prevUntil` passes; consider storing a derived verifier (e.g. HMAC key = HKDF(secret) so the stored value cannot be used for pairing impersonation elsewhere). Update the README so it does not claim 0600 on Windows.

## F10 LOW: module trusts unauthenticated close codes and relay-supplied strings

- `ws.onclose` with code 4005 calls `saveDevice(null)` when `dev` is set, before any proof from the relay. A rogue server at the stored host can send 4005 and make the module forget its credential (forces a re-pair, which also resets the SAS trust decision). 4002 sets `evicted` similarly (it disables reconnect).
- `notify('warn', 'pair-fail', 'Varrenmoor Bridge pairing: ' + res.reason)` where `res.reason` can be `rq.body.error` or `rv.body.error` from the relay, and the 4005 notice includes `ev.reason`. Foundry's `ui.notifications` message handling of HTML: unverified (older cores render it as HTML). A rogue "relay" (anything on the scanned /24 answering `/discover` as `varrenmoor-bridge-relay`) controls these strings, so if Foundry renders HTML this is script injection into the GM page (a GM page can do everything the GM can). The pairing dialog itself is safe: `showCode` escapes `host` and `code`.
Fix: pass `escapeHtml` over every relay-provided string before `notify`, or truncate to `[A-Za-z0-9 ._:-]`; only act on 4005 if the close followed a valid challenge (the relay sends it only after the MAC check, so require `challengeReceived`).

## F11 LOW: request-slot exhaustion and polling secrets

- `request()` creates a `committed` entry for any LAN caller; unrevealed ones count toward the global `maxPending` (5) for `pendingTtlMs` (120 s) and are never shown to the human. Three addresses (or one address with rotating IPv6 source addresses if the relay is ever bound to `::`) can block legitimate pairing indefinitely. Per-IP: 5 requests/10 min, so one host can hold a slot of the global 5 for about 4% of the time on its own.
- `pollSecret` and `requestId` are sent in clear. A passive sniffer who sees them can poll first when the request is approved and consume the sealed credential (`delivered`), so the real device gets "no longer valid" while a record for it exists on the relay. The sniffer cannot read it (sealed). Denial of service only. `cancel` with a sniffed secret also removes a pending request.
- Same-clientId supersede: if an attacker learns a victim's `clientId` (it is only visible to the admin and sealed on the wire), it can expire the victim's pending request. Not practically exploitable.
Fix: reveal within a short window or the slot is freed after 15 s (shorter TTL for `committed`); count only `committed` per IP towards a separate cap; bind `poll` to the same `ip` as `reveal`; show a nonce-based "device claimed these" so squatting is visible.

## F12 LOW: signed admin call replay and flood

`adminauth.js` accepts a signed request within +/-5 min and rejects a repeated nonce, but the nonce cache lives in process memory. After a relay restart (or when the daemon `die()`s from F1/F2) a captured signed request can be replayed for up to 5 minutes, e.g. `/pair/config {"enabled":true}` or `/pair/revoke`. `/pair/approve` ids are single use so replay is harmless. The signature covers method, URL (path), ts, nonce and body hash; it does not bind the host or the relay identity, so a signed request meant for one relay can be replayed to another relay that has the same API token (e.g. a rebuilt relay with the same `.env`). There is no throttle on failed admin authentications (not exploitable: token is 24 random bytes). Comparisons are timing-safe (`timingSafeEqual` on equal-length buffers; bearer compares SHA-256 digests).
Fix: persist recent nonces (or include a relay boot-id returned by `/discover` in the signed string, which also binds the relay identity); add `authFails` limiting on admin.

## F13 LOW/INFO: small leaks

- `/health` is unauthenticated and not LAN-restricted, and through a tunnel is public: pid, startedAt, `moduleConnected`, pending count, device count, `replacedLastMinute`.
- `authenticate()` is called after a `challenge` is sent for any deviceId, but the close reason differs: `device unknown device` vs `device bad credentials`, which lets a LAN caller enumerate valid device ids (48-bit random, so not practical) and contradicts the code comment "ids cannot be probed". Return the same reason and close code for both.
- Logs (`run/relay.log`, console): ip, request ids, device ids, device names, origins, the ip that switched pairing on/off. No secrets, tokens, codes-vs-secret or sealed blobs are logged (checked `server.js`, `pairing-console.mjs`, `daemon.mjs`). The approval banner logs the 6-digit code in `relay.log` (not sensitive after expiry; fine). `bridgectl.mjs info` prints tokens only with `--secrets`; `info.logTail` returns raw log lines (no secrets). Errors return fixed strings.
- WebSocket: no connection cap or Origin check before auth (5 s deadline); `maxPayload` is 5 MB pre-auth, so a LAN host can hold many 5 MB buffers. Lower `maxPayload` until authenticated (e.g. 2 KB via a per-socket check) and cap concurrent unauthenticated sockets.

## F14 INFO: SAS and commitment design

- Order: device commits `SHA-256(frame('vb-commit-v1', pk, nonce))` first, relay answers with its ephemeral key/nonce, device reveals, relay verifies the commitment. This is the right order (the party that learns the other's value last has already committed), so a man in the middle cannot grind keys on both sides: it fixes its device-side values before the real device reveals, and its relay-side values before the relay's key exists. Success chance per attempt is about 1 in 10^6 (20 bits; the modulo bias on a 32-bit value is negligible). With a 5-request window per address and 5 pending globally, the expected attacker effort is far above what a human approving one request at a time would tolerate, so brute force of the code is not a practical risk. The code is not a secret, so no timing concern.
- The code is bound to both public keys and both nonces (`frame` prevents ambiguity); the sealed device description is bound to the request id (AAD), so a rogue cannot swap descriptions between sessions.
- Limits of the design (already in the README): LAN attacker + user who does not compare wins; see F4 for making the comparison mandatory. Consider 8 digits only if you want margin against an attacker who can spread over many source addresses.
- Stale handling is sound: `pending` entries expire at 120 s, are swept on every call, `approve` rejects anything not `pending`, secrets are deleted after the single delivery (`delete p.sealed; delete p.key`). An approved request whose device never polls leaves a live device record on the relay (the secret was never delivered) until expiry or revoke; list it and revoke if "last seen" stays empty.

## F15 INFO: crypto review (no flaws found)

- Key agreement and derivation: X25519, all-zero shared secret rejected on both sides, HKDF-SHA256 with salt `frame(nonce, relayNonce)` and info `frame('vb-pair-v1', pk, relayPk)`. Rotation key uses a different label (`vb-ws-rotate-v1`) and its own salt.
- AEAD: ChaCha20-Poly1305, fresh random 12-byte nonce from CSPRNG (`crypto.randomBytes`, `crypto.getRandomValues`) for every seal; only two messages ever use the pairing key, so random-nonce collision risk is nil. Directions are not key-separated but the AAD differs per use (`vb-info|id`, `vb-dev|id|devId`, `vb-rot|devId`), and decryption failures return null.
- MACs: `vb-ws-client-v1` and `vb-ws-relay-v1` are distinct labels, so reflecting the relay's challenge or proof back to it fails; client nonce `cn` and relay nonce `rn` are both inside both MACs; `rn` is fresh per connection so a recorded login cannot be replayed. A man in the middle can still relay a full session between device and relay (no channel binding) and then holds the authenticated socket; that is the "traffic not protected" gap the README states.
- Comparisons: relay uses `crypto.timingSafeEqual` after length check; module uses a constant-time loop (`eq`). `eq(sha(pollSecret), hash)` compares digests. The commit check is a plain string compare of a public value (fine).
- `frame` prefixes 16-bit lengths; inputs are capped (8 KB JSON bodies, 64-char `cn`), no overflow.
- Prototype pollution/deserialisation: JSON is parsed with `JSON.parse` into plain objects; only whitelisted keys are read, `Map` is used for lookups; `__proto__` in JSON becomes an own property and is not merged into anything. Device/pending lists copy named fields only. No path traversal: file paths come from `.env`/CLI, never from request data; HTTP routes are an exact-match allow-list.
- XSS in the panel: `bridge_ui.js` builds HTML with `esc()` (escapes `& < > "`) for every device-controlled field (name, ip, origin, userName, ids); all attribute values are double-quoted so the missing `'` escape is harmless. Because the panel runs Node (CEP), an escaping failure would mean code execution, so keep that invariant under test. Device text is also clipped (60-120 chars) and control characters stripped on the relay.
- `isPrivateIp` is fail-closed (see F6).

## F16 INFO: vendored Noble bundle

`scripts/vendor/NOBLE-LICENSE.txt` states: @noble/curves 1.9.7, @noble/ciphers 1.3.0, @noble/hashes 1.8.0, MIT, Paul Miller, single minified esbuild bundle, no network access. I did not audit the minified file (it is a bundle I cannot map back to the packages), so "audited library" is true of the upstream versions, not verified for this file. The known-answer self-test only detects accidental breakage or a naive swap; an attacker who can modify `noble-bundle.js` can also modify the test in `seccrypto.js`. The module zip `module/varrenmoor-bridge.zip` is a committed binary that must be rebuilt to match; I did not diff it against the sources (unverified).
Fix: record the SHA-256 of the bundle and the exact build command in NOBLE-LICENSE.txt; have CI compare the zip contents with the folder.

## Other items checked, no finding

- `relay-window.ps1`: only changes console mode (QuickEdit) and launches node with fixed arguments; `ExecutionPolicy Bypass` is passed by bridgectl for that one file. `cimCreate` builds a command line with `"` quoting and does not escape embedded double quotes; inputs are local panel settings (node path, env path), so local-only.
- `bridgectl.mjs`: `stop`/`closeLocal` only kill a pid whose image name is `node(.exe)`, never act on `--target` remote hosts. The pid comes from `/health` on the local port, so a different local node process that answers `/health` could be killed; local trust only.
- `lib/publish.mjs`: writes `client.json` outside Foundry's served `Data/` (good); sets no file mode (F9).
- Origin/Host header on WebSocket: not checked but admin authority needs a token/secret, so a cross-site WebSocket cannot authenticate.
- Replay of device login: not possible (fresh `rn`).

## What I could not verify

- ACLs and sharing of `\\<host>\C\FoundryVTT resources\bridge` on the relay PC (this machine only has default admin shares).
- Whether Foundry v14's `ui.notifications` renders HTML (F10).
- Contents of the minified Noble bundle and the zip (F16).
- Behaviour of any third-party reverse proxy you may add (F6).
- The cloud-session path (`FOUNDRY_BRIDGE_URL`): not in the repo.

## Plain-language summary

Top risks, in order:
1. A single malformed message (`null`) over the WebSocket crashes the relay, from any machine that can reach port 3030, and an interrupted request does the same from the LAN. I reproduced both. In local mode (your current `TUNNEL=off`) this means any device on your LAN; in start.bat tunnel mode it means anyone on the internet who has the trycloudflare address. Needs a code fix (F1, F2).
2. The module will answer commands from a server before that server has proved it is your relay, and it will move to a new relay address by looking at a public ID. A device on your LAN could pretend to be the relay and read Foundry documents. Needs a code fix (F3).
3. Approving a pairing is a one-click action that does not make you type the code, the relay window's A key approves the oldest request blindly, and any web page open in a LAN browser can file a pairing request. The crypto is sound; the weak link is the human check. Needs a code/UI change, and until then: only press Approve while you are watching Foundry's own code dialog, and compare the origin shown (F4, F5).
4. The Cloudflare quick tunnel created by start.bat points at the relay itself; pairing is kept out only by a blacklist of proxy headers. Today you run with `TUNNEL=off`, so you are not exposed; keep it that way, or do not put any other reverse proxy in front of the relay without first fixing F6.
5. The API token sits in clear in every Claude call on the LAN and in `client.json` on a share whose permissions I could not check; it controls everything. Check who can read/write that share, and rotate tokens if in doubt (F7).

Things YOU must do now (no code needed):
- Delete or move `foundry-bridge/client.json.arcturus-old-2026-11-08` (contains an API token, not git-ignored) and rotate the token if it is still current (F8).
- Keep `TUNNEL=off`; do not enable the quick tunnel while the F1/F6 issues exist.
- Check the sharing permissions of the `\\VEGA\C` share (and who can write `client.json`).
- Tighten file permissions on `.env`, `run\paired-devices.json` and `client.json` (Windows ignores the 0600 setting) (F9).
- Pair only on a network you trust, and only press Approve when the code on Foundry's screen matches.

Code fixes for the developer: F1, F2, F3, F4, F5, F6, then F10 to F13.
