# upwork-mcp

Upwork MCP Server — Freelancer dashboard for Claude (contracts, messages, earnings).

## Tools

| Tool | Description |
|------|-------------|
| `get_user` | Current user profile & org info |
| `list_contracts` | Active/closed engagements |
| `get_contract` | Single contract deep-dive |
| `list_rooms` | Message threads |
| `get_messages` | Read messages in a thread |
| `send_message` | Send message (⚠️ requires explicit confirmation) |
| `search_jobs` | Search job postings (read-only) |
| `get_earnings` | Financial summary & recent transactions |
| `list_offers` | Incoming client offers |
| `respond_to_offer` | Accept/decline offer (⚠️ requires explicit confirmation) |

## Prerequisites

1. **Upwork API key** — apply at https://www.upwork.com/developer/keys/apply
   - Approval takes up to 2 weeks
   - Requires verified Upwork account with completed ID verification
   - Provide clear description of intended use
2. **OAuth2 credentials** from approved application

## Important Limitations

- ❌ **Cannot submit proposals** (blocked by Upwork, spends Connects)
- ❌ **Cannot automate job applications** (TOS violation → account suspension)
- ❌ **No sandbox** — all API calls hit production
- ❌ REST API is deprecated — GraphQL only
- Rate limits: 300 req/min, 40K req/day

## Setup

```
UPWORK_CLIENT_ID=your_client_id
UPWORK_CLIENT_SECRET=your_client_secret
UPWORK_ACCESS_TOKEN=your_access_token
UPWORK_REFRESH_TOKEN=your_refresh_token
UPWORK_ORG_UID=your_org_uid
```

## Architecture

All queries go through `https://api.upwork.com/graphql`.
Use the GraphQL Explorer to verify field names: https://www.upwork.com/developer/explorer/

## Deploy

```bash
railway up
```
