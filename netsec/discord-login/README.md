# Discord login for foundry.varrenmoor.com (Cloudflare Access)

Players sign in to Foundry with Discord. Access lets in members of the **Akcobs52 D&D** server who have the **Varrenmoor Campaign** role.

This is a Cloudflare Worker (from [Erisa/discord-oidc-worker](https://github.com/Erisa/discord-oidc-worker), MIT) that makes Discord look like an OpenID Connect provider to Cloudflare Access.

| Item | Value |
|---|---|
| Worker | `varrenmoor-discord-oidc`, custom domain `https://discord-auth.varrenmoor.com` |
| KV namespace | `discord-oidc-KV` (`de1da4eb2d534428a7e77c398ae29c3d`), holds the signing key |
| Discord app | **Sgt. Bones - DnD bot**, Application/Client ID `1538145703463755877` |
| OAuth2 redirect (set in Discord) | `https://dubcity.cloudflareaccess.com/cdn-cgi/access/callback` |
| Server (guild) | Akcobs52 D&D, `866777784982175745` |
| Player role | `Varrenmoor Campaign` |

## Local changes vs upstream
- `client_secret` comes from the Worker secret `DISCORD_CLIENT_SECRET` (encrypted), not `config.json`. `config.json` holds no secrets.
- Adds claim `role_names:866777784982175745` (role names), so the Access policy can match the role by name.
- Deployed to a custom domain because the account has no workers.dev subdomain.

## Secrets (never commit, never paste into chat)
Run these on the PC that has `wrangler login` (Vega, from `D:\dnd campagin 2026\discord-oidc-worker`). Each command asks for the value:
```
npx wrangler secret put DISCORD_CLIENT_SECRET   # Discord app > OAuth2 > Client Secret
npx wrangler secret put DISCORD_TOKEN           # Discord app > Bot > Token (the bot must be in the server)
```

## Cloudflare Access setup
1. Zero Trust > Settings > Authentication > Login methods > Add new > **OpenID Connect**:
   - Name `Discord`
   - App ID `1538145703463755877`
   - Client secret: any long random string. The worker does not check it, so don't spread the real Discord secret.
   - Auth URL `https://discord-auth.varrenmoor.com/authorize/guilds`
   - Token URL `https://discord-auth.varrenmoor.com/token`
   - Certificate URL `https://discord-auth.varrenmoor.com/jwks.json`
   - PKCE on
   - OIDC claims: `id`, `preferred_username`, `role_names:866777784982175745`
2. Application `foundry`: add the Discord login method.
3. Policy `Foundry players`: Include **OIDC Claim** `role_names:866777784982175745` = `Varrenmoor Campaign`. Keep the email rule for the GM's Gmail as a fallback.

## Deploy
`npm install`, then `npx wrangler deploy` from the Vega working copy, or copy these files to a folder with `node_modules`.
