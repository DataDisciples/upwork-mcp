# WhatsApp MCP — Agent Handoff Document

**Date:** 2026-05-28  
**Session:** claude/setup-whatsapp-mcp-POXnT  
**Status:** In Progress — Railway staged, QR scan pending

---

## Current State

### What's Done
- [x] Full technical scope researched (lharries/whatsapp-mcp architecture)
- [x] Railway deployment files created in this repo (`whatsapp-mcp/` directory)
  - `whatsapp-bridge/Dockerfile` — multi-stage Go build with CGO/gcc
  - `railway.toml` — Railway service config
  - `.env.example` — env var reference
  - `claude_desktop_config.template.json` — Claude Desktop config template
  - `README.md` — full setup guide
- [x] PR #2 open: `datadisciples/upwork-mcp` → `claude/setup-whatsapp-mcp-POXnT`
- [x] Railway service `whatsapp-bridge` STAGED in project `exciting-embrace`
  - Service ID: `e0eec7e2-fb51-4002-a330-d0862fd73f15`
  - Source: `lharries/whatsapp-mcp`, root dir: `whatsapp-bridge`
  - Persistent volume `whatsapp-store` mounted at `/app/store`
  - **STAGED BUT NOT YET DEPLOYED** — user must click Deploy in Railway dashboard

### What's NOT Done (Next Agent Picks Up Here)
- [ ] User needs to click **Deploy** in Railway dashboard for `exciting-embrace` project to apply staged changes
- [ ] Confirm build succeeds (Go + CGO build ~3-4 min)
- [ ] Add public domain to `whatsapp-bridge` service (Railway → Settings → Networking → Generate Domain)
- [ ] **QR code scan** — one-time WhatsApp auth via `railway shell`
- [ ] Set up local Python MCP server on user's machine
- [ ] Configure Claude Desktop config with Railway URL
- [ ] Smoke test all 12 MCP tools
- [ ] Delete `agile-spirit` Railway project (wrong template, should be cleaned up)

---

## Railway Projects Map

| Project | ID | Purpose |
|---|---|---|
| `exciting-embrace` | `e4afe560-f9cd-46e1-a588-ac915c03df80` | **MCP Hub** — all MCP services live here |
| `agile-spirit` | `b648b62c-3665-487c-8149-25b13ab0e81a` | Wrong WhatsApp template (hawkaii/annapurna) — DELETE THIS |

### exciting-embrace Services

| Service | Status |
|---|---|
| github-mcp | Online |
| quickbooks-mcp | Online |
| upwork-mcp | Online |
| teamwork-mcp | Online |
| domo-mcp | Online |
| **whatsapp-bridge** | **STAGED — needs Deploy click** |

### agile-spirit Services (DELETE)
- `Postgres` — Online (wrong project)
- `mcp-server` (hawkaii/annapurna) — Crashed (fastmcp version bug)

---

## QR Code Scan Instructions (One-Time Setup)

This is the only step requiring interactive terminal access:

```bash
# Install Railway CLI if needed
npm install -g @railway/cli

railway login
railway link    # select exciting-embrace project
railway shell   # choose whatsapp-bridge service

# Inside container:
./whatsapp-bridge
# QR code prints in terminal
# On phone: WhatsApp → Settings → Linked Devices → Link a Device → scan
# Wait for "Connected" message → Ctrl+C
# Railway auto-restarts, session persists in /app/store volume
```

Session lasts ~20 days. To re-auth: `railway shell` → delete `/app/store/whatsapp.db` → restart → re-scan.

---

## Claude Desktop Config (User's Machine)

File: `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)

```json
{
  "mcpServers": {
    "whatsapp": {
      "command": "/Users/YOU/.local/bin/uv",
      "args": [
        "--directory",
        "/path/to/whatsapp-mcp/whatsapp-mcp-server",
        "run",
        "main.py"
      ],
      "env": {
        "WHATSAPP_API_BASE_URL": "https://YOUR-BRIDGE.railway.app"
      }
    }
  }
}
```

Local Python server setup:
```bash
git clone https://github.com/lharries/whatsapp-mcp
cd whatsapp-mcp/whatsapp-mcp-server
# uv is required: curl -LsSf https://astral.sh/uv/install.sh | sh
```

---

## Architecture

```
WhatsApp ←→ [Go Bridge on Railway/exciting-embrace]
                    ↕ HTTP REST API
          [Python MCP Server — runs locally]
                    ↕ stdio
              [Claude Desktop]
```

- **Go bridge** (Railway): always-on, connects to WhatsApp via whatsmeow, stores messages in SQLite at `/app/store/messages.db`, exposes REST on port 8080
- **Python MCP server** (local): reads SQLite directly + calls Go bridge for writes, exposes 12 MCP tools to Claude via stdio transport

---

## Available MCP Tools (12 total)

| Tool | Description |
|---|---|
| `search_contacts` | Find contacts by name or phone |
| `list_chats` | Recent chats with timestamps |
| `list_messages` | Paginated message retrieval |
| `get_chat` | Chat metadata by JID |
| `get_direct_chat_by_contact` | Find chat by phone number |
| `get_contact_chats` | All chats for a contact |
| `get_last_interaction` | Most recent message from contact |
| `get_message_context` | Messages around a specific message |
| `send_message` | Send text message |
| `send_file` | Send image/video/document |
| `send_audio_message` | Send voice note (needs FFmpeg) |
| `download_media` | Download media from message |

---

## Lessons Learned

### 1. Railway Template Marketplace Is Misleading
`railway.com/deploy/whatsapp-mcp` deploys `hawkaii/annapurna` — NOT lharries/whatsapp-mcp. The hawkaii template:
- Uses Postgres (not SQLite)
- Requires Gemini API key + Vision API
- Has bearer token auth
- Is currently broken (fastmcp module `server.auth.providers.bearer` missing)
- Is much more complex than needed for personal use

**Protocol:** Always deploy whatsapp-mcp from GitHub directly → `lharries/whatsapp-mcp` root dir `whatsapp-bridge`. Never use the Railway template marketplace for this.

### 2. CGO Requirement for Go Bridge
The Go bridge uses `go-sqlite3` which requires CGO and gcc. Railway's auto-detect fails. Must use a custom Dockerfile with:
```dockerfile
RUN apk add --no-cache gcc musl-dev
```
And build with `CGO_ENABLED=1`. Our Dockerfile in this repo handles this correctly.

### 3. Railway MCP Tool Is Unreliable
The Railway MCP server disconnected multiple times during this session. Don't rely on it for critical deploy steps. Have the user confirm deployments in the Railway dashboard as backup.

### 4. Two-Process Architecture Requires Manual Bridge Start
The Go bridge and Python MCP server are separate processes. The bridge must be deployed and running on Railway BEFORE the Python server can function. The Python server on the client machine connects to the bridge via `WHATSAPP_API_BASE_URL`.

### 5. Session Expiry Is Operational Overhead
WhatsApp sessions expire ~every 20 days. Build a calendar reminder or monitoring alert for re-auth. The re-auth requires `railway shell` access — plan for this.

### 6. Railway Project Organization
One Railway project per logical product (not one per service). The `exciting-embrace` project correctly consolidates all MCP tools. Don't create separate projects per MCP.

---

## Known Weaknesses / Future Feature Requests

### WhatsApp MCP
- **No team sharing**: Python MCP server runs locally per user. If multiple team members need access, the Python server needs SSE/HTTP transport and auth added.
- **20-day re-auth**: Operational burden. Consider building a QR-serving HTTP endpoint in the Go bridge so re-auth can happen without `railway shell`.
- **Media not auto-downloaded**: Only metadata stored. `download_media` must be called explicitly.
- **No proactive notifications**: Claude can't receive incoming WhatsApp messages proactively — polling only.
- **Ban risk**: whatsmeow uses unofficial WhatsApp Web protocol. Low volume + read-mostly is safest. Avoid sending >5 messages quickly.

### Railway MCP Connector
- **Frequent disconnects**: The Railway MCP server is unstable in long sessions. Needs investigation.
- **Can't deploy staged changes**: The MCP agent can stage changes but requires dashboard confirmation — can't fully automate deployment without the user clicking Deploy.

### General MCP Hub (exciting-embrace)
- No health monitoring dashboard across all services
- No shared auth/secrets management (each service manages its own env vars)
- Consider adding a Postgres service to the project for any MCPs that need persistent storage

---

## Related Resources

- **GitHub PR**: `datadisciples/upwork-mcp#2` (draft)
- **Teamwork Task**: datadisciples consulting.teamwork.com/app/tasks/39827863
- **Source Repo**: github.com/lharries/whatsapp-mcp
- **Railway Project**: exciting-embrace (`e4afe560-f9cd-46e1-a588-ac915c03df80`)
- **Railway Service**: whatsapp-bridge (`e0eec7e2-fb51-4002-a330-d0862fd73f15`)
- **Volume**: whatsapp-store, mounted at `/app/store`
