# WhatsApp MCP — Railway Setup

Connects Claude Desktop to WhatsApp via the [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) bridge.

## Architecture

```
WhatsApp ←→ [Go Bridge on Railway] ←→ [Python MCP Server, local] ←→ Claude Desktop
                    ↑
             Persistent volume
             (session + messages DB)
```

Only the **Go bridge** runs on Railway (always-on). The **Python MCP server** runs locally on your machine and is launched by Claude Desktop on demand.

---

## Part 1: Deploy the Go Bridge to Railway

### Step 1 — Fork the source repo

Fork [lharries/whatsapp-mcp](https://github.com/lharries/whatsapp-mcp) into the datadisciples GitHub org (or your personal account).

### Step 2 — Add Railway config files to the fork

Copy these two files from this directory into the root of your fork:

```
whatsapp-mcp/railway.toml        →  repo-root/railway.toml
whatsapp-mcp/whatsapp-bridge/Dockerfile  →  repo-root/whatsapp-bridge/Dockerfile
```

Commit and push to your fork.

### Step 3 — Create Railway project

1. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
2. Select your fork of whatsapp-mcp
3. Railway will detect `railway.toml` and use the Dockerfile automatically

### Step 4 — Add a persistent volume

In the Railway dashboard for your service:
- Settings → Volumes → Add Volume
- Mount path: `/app/store`
- This keeps your WhatsApp session alive across redeploys

### Step 5 — Initial QR code scan (one-time)

The bridge can't authenticate without a QR scan. On first deploy:

```bash
# Install Railway CLI
npm install -g @railway/cli

# Open a shell into the running container
railway login
railway link          # select your project
railway shell         # drops you into the container

# Inside the container, restart the bridge interactively
./whatsapp-bridge
# → QR code prints to the terminal
# → Open WhatsApp on your phone → Settings → Linked Devices → Link a Device → scan
# → Session saved to /app/store/whatsapp.db
# Ctrl+C — Railway will restart the bridge automatically
```

After the scan, the session persists in the volume. You won't need to re-scan unless the session expires (~20 days) or you delete the volume.

### Step 6 — Note your Railway URL

In the Railway dashboard → your service → Settings → Networking → Generate Domain.
You'll get a URL like `https://whatsapp-bridge-production-xxxx.railway.app`.

---

## Part 2: Local Python MCP Server

This runs on your machine and is what Claude Desktop actually talks to.

### Prerequisites

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the whatsapp-mcp repo (same fork you deployed)
git clone https://github.com/YOUR-ORG/whatsapp-mcp
cd whatsapp-mcp/whatsapp-mcp-server
```

### Test the MCP server locally

```bash
# Point the Python server at your Railway bridge
export WHATSAPP_API_BASE_URL=https://YOUR-APP.railway.app

uv run main.py
# Should start without errors
```

---

## Part 3: Claude Desktop Config

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
or `~/.config/Claude/claude_desktop_config.json` (Linux):

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
        "WHATSAPP_API_BASE_URL": "https://YOUR-APP.railway.app"
      }
    }
  }
}
```

Find your `uv` path with `which uv`. Restart Claude Desktop after saving.

---

## Available Tools in Claude

Once connected, Claude can:

| Tool | What it does |
|---|---|
| `search_contacts` | Find contacts by name or phone |
| `list_chats` | Recent chats with timestamps |
| `list_messages` | Read messages from a chat |
| `get_last_interaction` | Most recent message from a contact |
| `get_message_context` | Messages around a specific message |
| `send_message` | Send a text message |
| `send_file` | Send a file or image |
| `download_media` | Download media from a message |

---

## Troubleshooting

**Session expired / QR needed again**
Delete `/app/store/whatsapp.db` from the Railway volume (or via `railway shell`) and repeat Step 5.

**Bridge not connecting**
Check Railway logs. The `/health` endpoint should return `{"status":"connected"}`.

**Python server can't reach bridge**
Make sure `WHATSAPP_API_BASE_URL` is set and the Railway domain is active (check Networking settings).

**Message history missing**
History syncs on first connection — for large accounts this can take 10–30 minutes. Check bridge logs.

---

## Important Notes

- **ToS risk:** `whatsmeow` uses an unofficial WhatsApp Web protocol. Keep message volume low, avoid bulk sends.
- **Session longevity:** Sessions typically last ~20 days before requiring re-scan.
- **Media:** Only metadata is stored by default. Use `download_media` to fetch actual files.
- **Re-auth cadence:** Plan to re-scan the QR roughly once a month.
