# netsec/

Network-security project for the self-hosted Foundry VTT on Vega (Windows, Foundry v14, port 30000).
Goal: players reach Foundry without a router port forward, after the forwarded port was seen flooded by hostile IPs.

- `PLAN.md` - research, comparison, recommendation, setup steps, hardening, breakage list, rollback.
- `BOARD.md` - task board (todo / doing / done) with owners.
- `AUDIT_2026-11-07.md` - read-only local inspection of the PC this session ran on. No secrets or public IPs.

Rules for this folder: never commit passwords, tokens, tunnel credentials JSON, or public IP addresses.
