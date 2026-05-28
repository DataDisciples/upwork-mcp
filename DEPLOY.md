# Deploying upwork-mcp to Railway

Time to spin up: ~20 minutes (plus Upwork credential setup).

**Auth model:** OAuth 2.1 via WorkOS AuthKit (Dynamic Client Registration).
Same pattern as `utilities/domo-mcp` and `utilities/teamwork-mcp`.

---

## Prerequisites

### 1. Upwork API credentials (one-time, wait on Upwork approval)

Apply at https://www.upwork.com/developer/keys/apply. Approval takes up to
2 weeks. Once approved:

1. Log in to https://www.upwork.com/developer/keys.
2. Note your **Client ID** and **Client Secret**.
3. Complete the **OAuth2 authorization-code flow** once to get your initial
   tokens — Upwork does not issue tokens automatically:
   - Redirect your browser to:
     ```
     https://www.upwork.com/ab/account-security/oauth2/authorize
       ?response_type=code
       &client_id=YOUR_CLIENT_ID
       &redirect_uri=https://www.upwork.com/developer/keys
     ```
   - Approve the consent screen.
   - Exchange the `code` for tokens:
     ```bash
     curl -X POST https://www.upwork.com/api/v3/oauth2/token \
       -d "grant_type=authorization_code" \
       -d "code=CODE_FROM_STEP_ABOVE" \
       -d "client_id=YOUR_CLIENT_ID" \
       -d "client_secret=YOUR_CLIENT_SECRET" \
       -d "redirect_uri=https://www.upwork.com/developer/keys"
     ```
   - Save the `access_token` and `refresh_token` from the response.
4. Find your **Organization UID** (`UPWORK_ORG_UID`) by calling:
   ```bash
   curl -H "Authorization: Bearer ACCESS_TOKEN" \
        https://api.upwork.com/graphql \
        -d '{"query":"{ organization { id name } }"}'
   ```

### 2. WorkOS AuthKit (one-time, ~10 min)

If you haven't set up AuthKit yet, follow **Step 1** of
`utilities/RAILWAY-DEPLOY.md`. One AuthKit app serves all your Railway MCP
services — you don't need a new one for upwork-mcp.

---

## Step 1 — Create the Railway service

1. Open your Railway project.
2. **+ New Service → GitHub Repo** → `DataDisciples/upwork-mcp`.
3. Railway will auto-detect the Dockerfile. Let it.
4. **Settings → Source → Root Directory** = `/` (the whole repo is the service).
5. **Networking → Generate Domain**. Save the URL — you need it for `MCP_BASE_URL`.
6. **Mount a Volume at `/data`** (critical):
   - Service → **Volumes** → **+ New Volume** → Mount path: `/data`.
   - This persists the rotated refresh token across container restarts.
   - Without it, a restart after any token refresh will lock the service out.

---

## Step 2 — Set environment variables

Service → **Variables** → add:

```
# Upwork credentials
UPWORK_CLIENT_ID=your_client_id
UPWORK_CLIENT_SECRET=your_client_secret
UPWORK_REFRESH_TOKEN=your_refresh_token
UPWORK_ACCESS_TOKEN=your_access_token        # optional, will be refreshed
UPWORK_ORG_UID=your_org_uid                  # optional, needed for org queries
UPWORK_TOKEN_FILE=/data/upwork_tokens.json   # already set by Dockerfile default

# Transport
MCP_TRANSPORT=http                           # already set by Dockerfile

# WorkOS AuthKit
AUTHKIT_DOMAIN=https://your-authkit-domain.authkit.app
MCP_BASE_URL=https://your-railway-domain.up.railway.app

# Optional — set true ONLY if you want to enable send_message / respond_to_offer
# UPWORK_ALLOW_DESTRUCTIVE=true
```

**Railway already has `UPWORK_CLIENT_ID` and `UPWORK_CLIENT_SECRET`** from
the initial setup. You need to add the token vars once Upwork approves.

---

## Step 3 — Deploy and verify

1. **Deploy** the service (or it auto-deploys on push to main).
2. Check health:
   ```bash
   curl https://your-railway-domain.up.railway.app/health
   # Expected: {"status":"ok","service":"upwork"}
   ```
3. Check OAuth discovery:
   ```bash
   curl https://your-railway-domain.up.railway.app/.well-known/oauth-protected-resource
   # Expected: JSON with "authorization_servers" pointing at your AuthKit domain
   ```

---

## Step 4 — Add to Claude Desktop or Claude.ai

**Claude Desktop:** Settings → Connectors → Add custom connector
- Name: `Upwork`
- Remote MCP server URL: `https://your-railway-domain.up.railway.app/mcp/`
- Leave OAuth fields blank — Dynamic Client Registration handles it.
- Sign in via AuthKit popup.

**Claude.ai web:** Settings → Connectors → Add custom integration → same URL.

You should see 10 tools appear.

---

## Step 5 — Run the smoke test

Once credentials are activated:

```bash
# Local
python scripts/upwork_smoke_test.py

# Or trigger via GitHub Actions
# Actions → upwork-smoke-test → Run workflow
```

The smoke test forces a token refresh (proves client_id/secret/refresh_token
are valid) then issues a `{ user { id name email } }` query.

---

## Token rotation — what happens on restart

Upwork rotates the refresh token on every refresh. The sequence:

1. Container starts → `upwork_client.py` reads `/data/upwork_tokens.json`
   (the last persisted pair).
2. If `access_token` is missing/expired → calls the refresh endpoint.
3. New `access_token` + rotated `refresh_token` → written back to
   `/data/upwork_tokens.json`.
4. Next restart repeats from step 1 with the latest pair.

**If `/data` Volume is missing:** the file write silently fails (logged as a
warning). The first request each cold start will 401 → auto-refresh → succeed.
But because the new refresh token is never persisted, the second cold start
will try the original (now-invalid) refresh token and get locked out.

**TL;DR: Mount the Volume.**

---

## Rotating credentials manually

1. Update the Railway env var (`UPWORK_REFRESH_TOKEN` etc.).
2. Delete `/data/upwork_tokens.json` if it exists (or it will override the
   env var until the next refresh cycle):
   - Railway → Service → Volumes → browse to `/data` → delete the file.
3. Redeploy.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `/health` returns 404 | Dockerfile CMD is wrong or service didn't build. Check deploy logs. |
| Boot crash: `Missing required env vars: UPWORK_REFRESH_TOKEN` | Add `UPWORK_REFRESH_TOKEN` to Railway variables. |
| All tool calls return 401 after a restart | Volume not mounted — refresh token rotation lost. Mount `/data` Volume. |
| Token refresh returns 400 | `UPWORK_CLIENT_ID` / `UPWORK_CLIENT_SECRET` wrong, or the Upwork app is still pending approval. |
| GraphQL tools return `{"errors": [...]}` | Schema field names are unverified. Check `https://www.upwork.com/developer/explorer/` and update the relevant tool in `src/tools/`. |
| Claude UI: 0 tools after connecting | URL must end with `/mcp/` (trailing slash). |
| Claude UI: `Failed to register OAuth client` | DCR off in WorkOS or redirect URIs not allowlisted. See `utilities/RAILWAY-DEPLOY.md` Step 1. |
