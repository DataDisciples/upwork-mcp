# CLAUDE.md — upwork-mcp

User-global rules live in **`ThomasPepperz/utilities/CLAUDE.md`** (mirrored
from `~/.claude/CLAUDE.md` on the workstation). That file is the single
source of truth for cross-repo conventions:

- Pushing files via the GitHub MCP — size discipline
- Workflow-cascade pattern + anti-recursion gotcha
- Decision-tracking convention
- Trust tier system
- GitHub ↔ Teamwork linking
- Task lifecycle & successor-task discipline
- Recommendation-tracking discipline + capture-first refinement
- PM discipline & critical-path analysis
- Workflow & tooling gotchas
- Async work & polling discipline — ScheduleWakeup vs auto-notifications

## upwork-mcp-specific notes

- This repo is a **FastMCP server** for the Upwork freelancer API (contracts, messages, earnings, job search) via GraphQL.
- **Deployment**: Railway via `railway up` CLI. No `railway.toml`; service configured in Railway dashboard.
- **Auth**: Upwork OAuth2 + refresh token. Env vars: `UPWORK_CLIENT_ID`, `UPWORK_CLIENT_SECRET`, `UPWORK_ACCESS_TOKEN`, `UPWORK_REFRESH_TOKEN`, `UPWORK_ORG_UID`.
- Most actively developed of the 4 migrated MCP repos (3 branches at transfer time; open WhatsApp scaffolding draft PR #2).
- **Refactor candidate**: apply utilities patterns (modular tools, FastMCP + WorkOS AuthKit, gates for destructive ops). Tracked as tw#39854906.
- Transferred from `DataDisciples/upwork-mcp` on 2026-05-13 (see `utilities/docs/decisions/2026-05-13-datadisciples-migration-COMPLETED.md`).

> **CI mirror:** this file is read by `claude-code-action` running in GitHub Actions on this repo. The agent's session also loads `utilities/CLAUDE.md` for the canonical global rules.
