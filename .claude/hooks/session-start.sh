#!/bin/bash
# SessionStart hook (mirrored from ThomasPepperz/utilities)
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  echo '{}'
  exit 0
fi

REPO_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$REPO_DIR"

CONTEXT_FILE="$(mktemp)"

{
  echo "## Trust tier reminder (per CLAUDE.md)"
  echo ""
  echo "Default tier this session: **GREEN** (branch -> PR -> ready, user merges)."
  echo "User keyword overrides:"
  echo "- yolo / auto / just do it     -> YOLO (auto-merge via tier:yolo label)"
  echo "- draft / review first         -> YELLOW (stays draft)"
  echo "- dry-run / propose only       -> RED (no code written)"
  echo "- ask first / confirm / hold   -> STOP (plan + confirm)"
  echo ""
  echo "**Always-pause** regardless of tier: force-push, branch delete on unmerged work, prod dataflows (SpotSee DF 76), external sends (Slack/email/3rd-party), public<->private flips, CI secrets."
  echo ""
  echo "**Always-do** regardless of tier: read audits, draft PRs, tests/lint/typecheck, typos, patch-bumps."
  echo ""

  echo "## Active claude/* branches (cross-session visibility)"
  echo "_What other Claude sessions have been doing. Each is potentially someone's parallel work - read before assuming a clean slate._"
  echo ""
  if command -v gh >/dev/null 2>&1 && [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    branch_data=$(gh api -X GET "repos/{owner}/{repo}/branches?per_page=100" \
      --jq '[.[] | select(.name | startswith("claude/")) | {name, sha: .commit.sha}]' 2>/dev/null || echo '[]')
    branch_count=$(echo "$branch_data" | python3 -c "import sys, json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
    if [ "$branch_count" = "0" ]; then
      echo "_No claude/* branches present._"
    else
      echo "_Found $branch_count claude/* branch(es). Showing up to 8 most recent:_"
      echo ""
      echo "$branch_data" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for entry in data[:8]:
    print(entry['name'] + '\t' + entry['sha'])
" | while IFS=$'\t' read -r branch sha; do
        commit_info=$(gh api "repos/{owner}/{repo}/commits/$sha" \
          --jq '"  date: \(.commit.author.date)\n  author: \(.commit.author.name)\n  msg: " + (.commit.message | split("\n") | .[0])' \
          2>/dev/null || echo "  (commit fetch failed)")
        echo "- \`$branch\` (sha: ${sha:0:7})"
        echo "$commit_info"
      done
    fi
  else
    echo "_gh CLI or GH_TOKEN not available - cross-session visibility limited._"
  fi
  echo ""
} >> "$CONTEXT_FILE"

{
  echo "## Dependency install"
  echo ""
  if [ -f "requirements.txt" ]; then
    echo "- Installing top-level requirements.txt"
    pip install --quiet -r requirements.txt 2>&1 | tail -3 || echo "  (pip install failed; see logs)"
  fi
  while IFS= read -r req; do
    subdir=$(dirname "$req")
    echo "- Installing $req"
    pip install --quiet -r "$req" 2>&1 | tail -3 || echo "  (pip install failed in $subdir)"
  done < <(find . -mindepth 2 -maxdepth 3 -name "requirements.txt" -not -path "./.git/*" -not -path "./node_modules/*" 2>/dev/null)
  echo ""
} >> "$CONTEXT_FILE"

{
  echo "## Open tasks for me (Teamwork)"
  echo ""
  if [ -z "${TEAMWORK_DOMAIN:-}" ] || [ -z "${TEAMWORK_API_KEY:-}" ]; then
    echo "_TEAMWORK_DOMAIN or TEAMWORK_API_KEY not set - skipping Teamwork lookup._"
    echo ""
  else
    response=$(curl -s -u "${TEAMWORK_API_KEY}:x" \
      "https://${TEAMWORK_DOMAIN}.teamwork.com/projects/api/v3/tasks.json?searchTerm=%5Bclaude%5D&include=tasklists,projects&pageSize=20" \
      2>/dev/null || echo '{}')
    if echo "$response" | python3 -c "import sys,json; d=json.load(sys.stdin); tasks=d.get('tasks',[]); print('Found',len(tasks),'tasks'); [print(f\"- [#{t['id']}] {t.get('name','(no name)')}  ·  status={t.get('status','?')}\") for t in tasks]" 2>/dev/null; then
      :
    else
      echo "_Teamwork API call failed or returned unexpected shape._"
    fi
    echo ""
  fi
} >> "$CONTEXT_FILE"

{
  echo "## CLAUDE.md (top-level)"
  echo ""
  if [ -f "CLAUDE.md" ]; then
    head -100 CLAUDE.md
    md_lines=$(wc -l < CLAUDE.md)
    if [ "$md_lines" -gt 100 ]; then
      echo ""
      echo "_...truncated; CLAUDE.md is $md_lines lines total. Read in full if needed._"
    fi
  else
    echo "_No CLAUDE.md at repo root._"
  fi
  echo ""
  echo "## Handoff docs"
  echo ""
  handoffs=$(find . -maxdepth 4 -type f \( -iname "HANDOFF.md" -o -iname "HANDOFF*.md" \) -not -path "./.git/*" 2>/dev/null | head -10)
  if [ -n "$handoffs" ]; then
    echo "$handoffs" | while read -r f; do
      echo "- \`$f\` ($(wc -l < "$f") lines)"
    done
  else
    echo "_No HANDOFF*.md files found._"
  fi
  echo ""
  echo "## Recent decision docs"
  echo ""
  if [ -d "docs/decisions" ]; then
    docs=$(ls -t docs/decisions/*.md 2>/dev/null | head -5)
    if [ -n "$docs" ]; then
      echo "$docs" | while read -r f; do
        title=$(head -1 "$f" | sed 's/^#* *//')
        echo "- \`$f\` - $title"
      done
    else
      echo "_docs/decisions/ exists but is empty._"
    fi
  else
    echo "_No docs/decisions/ directory._"
  fi
  echo ""
} >> "$CONTEXT_FILE"

{
  echo "## Open PRs"
  echo ""
  if command -v gh >/dev/null 2>&1 && [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    gh pr list --state open --limit 30 --json number,title,isDraft,headRefName \
      --jq '.[] | "- #\(.number) [\(if .isDraft then \"draft\" else \"ready\" end)] \(.title)  ·  branch: `\(.headRefName)`"' \
      2>/dev/null || echo "_gh pr list failed._"
  else
    echo "_gh CLI or GH_TOKEN not available._"
  fi
  echo ""
  echo "## Stale branches"
  echo ""
  if command -v gh >/dev/null 2>&1 && [ -n "${GH_TOKEN:-}${GITHUB_TOKEN:-}" ]; then
    open_pr_branches=$(gh pr list --state open --limit 200 --json headRefName --jq '.[].headRefName' 2>/dev/null | sort -u)
    all_branches=$(gh api -X GET "repos/{owner}/{repo}/branches" --paginate --jq '.[].name' 2>/dev/null | sort -u)
    if [ -n "$all_branches" ]; then
      stale_count=0
      while IFS= read -r b; do
        if [ "$b" = "main" ] || [ "$b" = "master" ]; then continue; fi
        if echo "$open_pr_branches" | grep -qx "$b"; then continue; fi
        stale_count=$((stale_count + 1))
        if [ "$stale_count" -le 20 ]; then echo "- \`$b\`"; fi
      done <<< "$all_branches"
      if [ "$stale_count" -gt 20 ]; then echo "- _...and $((stale_count - 20)) more_"; fi
      if [ "$stale_count" -eq 0 ]; then echo "_None - repo is clean._"; fi
    fi
  fi
  echo ""
} >> "$CONTEXT_FILE"

python3 -c "
import json, sys
with open('$CONTEXT_FILE') as f:
    ctx = f.read()
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'SessionStart',
        'additionalContext': ctx,
    }
}))
"

rm -f "$CONTEXT_FILE"
