# upwork-mcp

Two interoperating runtimes against the Upwork GraphQL API:

- **MCP server** (`src/`) — Claude tools for contracts, messages, earnings,
  offers, and job-search. stdio for local Claude Desktop / Cursor; HTTP +
  WorkOS AuthKit for remote Railway deploy.
- **Domo pipeline** (`pipeline/`) — daily ETL extracting Upwork data into
  Domo datasets, registered in `datasets.json`.

Both share `src/upwork_client.py` (auth + token persistence + GraphQL).

## Status

The Upwork developer application is pending Upwork approval. Until the keys
are activated, the smoke test and ETL workflows will skip silently (they
short-circuit on missing `UPWORK_REFRESH_TOKEN`). Once approved:

1. Complete the OAuth2 authorization-code flow once to obtain access +
   refresh tokens.
2. Set the GitHub repo secrets (`UPWORK_CLIENT_ID`, `UPWORK_CLIENT_SECRET`,
   `UPWORK_ACCESS_TOKEN`, `UPWORK_REFRESH_TOKEN`, `UPWORK_ORG_UID`).
3. Set the same five vars on the Railway service (plus `AUTHKIT_DOMAIN` and
   `MCP_BASE_URL` for the MCP transport).
4. Mount a Railway Volume at `/data` so refreshed tokens persist across
   container restarts (Upwork rotates the refresh token on every refresh).
5. Run `Actions → upwork-smoke-test → Run workflow` to verify, then enable
   the daily `upwork-to-domo` cron.

## Tools (MCP)

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

> All GraphQL field names in the tool modules and pipeline extractors are
> unverified against the live Upwork schema. Reconcile against the Explorer
> on first credential activation: https://www.upwork.com/developer/explorer/

## Pipeline

Run locally:

```bash
cp .env.example .env   # fill in UPWORK_* and DOMO_* once available
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Verify Upwork creds
python scripts/upwork_smoke_test.py

# 2. Extract-only (no Domo writes)
python -m pipeline.upwork_to_domo --dry-run

# 3. Full run (after populating Domo dataset GUIDs in datasets.json)
python -m pipeline.upwork_to_domo
```

`datasets.json` is the single source of truth for Domo dataset GUIDs.
Empty strings are treated as "not yet provisioned" and silently skipped.

## Hard limitations (Upwork TOS)

- Cannot submit proposals via API — would spend Connects + violate TOS.
- Cannot automate job applications — account-suspension risk.
- No sandbox; all calls hit production.
- REST API is deprecated — GraphQL only.
- Rate limits: 300 req/min, 40K req/day.

## Layout

```
upwork-mcp/
├── src/
│   ├── main.py               # FastMCP entry point (stdio | http)
│   ├── server_http.py        # /health + Mount(/) for Railway
│   ├── upwork_client.py      # OAuth2 + token persistence + gql()
│   └── tools/                # MCP tool modules (one per domain)
├── pipeline/
│   ├── extractors.py         # Cursor-paginated GraphQL drains
│   └── upwork_to_domo.py     # Orchestrator (snapshot vs append per dataset)
├── scripts/
│   └── upwork_smoke_test.py
├── .github/workflows/
│   ├── upwork-smoke-test.yml
│   └── upwork-to-domo.yml    # Daily ETL cron
├── datasets.json             # Friendly name -> Domo dataset GUID
├── Dockerfile                # Railway-ready (http transport on :8000)
├── requirements.txt
└── .env.example
```

## Deploy (Railway)

Mirrors `utilities/RAILWAY-DEPLOY.md`. Required env on the service:

- `UPWORK_CLIENT_ID`, `UPWORK_CLIENT_SECRET`, `UPWORK_REFRESH_TOKEN`,
  `UPWORK_ACCESS_TOKEN` (optional), `UPWORK_ORG_UID` (optional).
- `MCP_TRANSPORT=http`
- `AUTHKIT_DOMAIN`, `MCP_BASE_URL`
- Volume mounted at `/data` (so token rotation persists).
