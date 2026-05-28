# upwork-mcp

Upwork MCP server — Claude tools for contracts, messages, earnings, offers,
and job search. stdio for local Claude Desktop / Cursor; HTTP + WorkOS
AuthKit for remote Railway deploy.

The Domo ETL pipeline lives in a separate repo:
[`DataDisciples/upwork-pipeline`](https://github.com/DataDisciples/upwork-pipeline).
Both repos share the same `upwork_client.py` OAuth2 pattern.

## Status

The Upwork developer application is **pending Upwork approval**. Credentials
are not yet active. Once approved:

1. Complete the OAuth2 authorization-code flow once to obtain access +
   refresh tokens.
2. Set Railway env vars (see Deploy section below).
3. Mount a Railway Volume at `/data` — Upwork rotates the refresh token on
   every refresh; persistence prevents lockout on container restart.
4. Run the smoke test: `python scripts/upwork_smoke_test.py`.

## Tools

| Tool | Description |
|------|-------------|
| `get_user` | Current user profile + organization |
| `list_contracts` | Active/closed engagements |
| `get_contract` | Single contract deep-dive |
| `list_rooms` | Message threads |
| `get_messages` | Read messages in a thread |
| `send_message` | Send message (gated: `UPWORK_ALLOW_DESTRUCTIVE=true`) |
| `get_earnings` | Financial overview + recent transactions |
| `list_offers` | Incoming client offers |
| `respond_to_offer` | Accept/decline offer (gated: `UPWORK_ALLOW_DESTRUCTIVE=true`) |
| `search_jobs` | Read-only job-posting search |

> All GraphQL field names are unverified against the live Upwork schema.
> Reconcile against the Explorer on first credential activation:
> https://www.upwork.com/developer/explorer/

## Hard limitations (Upwork TOS)

- Cannot submit proposals or apply to jobs via API.
- No sandbox — all calls hit production.
- REST API is deprecated — GraphQL only.
- Rate limits: 300 req/min, 40K req/day.

## Local stdio setup

```bash
cp .env.example .env   # fill in UPWORK_* vars
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Add to Claude Desktop / Claude Code:
claude mcp add upwork \
  -e UPWORK_CLIENT_ID=... \
  -e UPWORK_CLIENT_SECRET=... \
  -e UPWORK_REFRESH_TOKEN=... \
  -- python /abs/path/upwork-mcp/src/main.py
```

## Deploy (Railway)

Mirrors `utilities/RAILWAY-DEPLOY.md`. Required env vars on the service:

| Variable | Required | Notes |
|---|---|---|
| `UPWORK_CLIENT_ID` | yes | From Upwork developer portal |
| `UPWORK_CLIENT_SECRET` | yes | |
| `UPWORK_REFRESH_TOKEN` | yes | From OAuth2 auth-code flow |
| `UPWORK_ACCESS_TOKEN` | optional | Pipeline refreshes automatically |
| `UPWORK_ORG_UID` | optional | Needed for org-scoped GraphQL queries |
| `UPWORK_TOKEN_FILE` | optional | Default `/data/upwork_tokens.json` |
| `UPWORK_ALLOW_DESTRUCTIVE` | optional | `true` to enable send_message / respond_to_offer |
| `MCP_TRANSPORT` | yes | Set to `http` (Dockerfile default) |
| `AUTHKIT_DOMAIN` | yes (http) | WorkOS AuthKit URL |
| `MCP_BASE_URL` | yes (http) | This service's public Railway URL |

**Mount a Railway Volume at `/data`** so token rotation is durable.

MCP endpoint: `https://<your-domain>.up.railway.app/mcp/`
Health: `https://<your-domain>.up.railway.app/health`

## Layout

```
upwork-mcp/
├── src/
│   ├── main.py               # FastMCP entry point (stdio | http)
│   ├── server_http.py        # /health + Mount(/) for Railway
│   ├── upwork_client.py      # OAuth2 + token persistence + gql()
│   └── tools/                # One module per domain
│       ├── user.py
│       ├── contracts.py
│       ├── messages.py
│       ├── earnings.py
│       ├── offers.py
│       └── jobs.py
├── Dockerfile                # Railway-ready, http on :8000
├── requirements.txt
└── .env.example
```
