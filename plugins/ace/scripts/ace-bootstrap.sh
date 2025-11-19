#!/usr/bin/env bash
set -euo pipefail

if ! command -v ce-ace >/dev/null 2>&1; then
  echo "❌ ce-ace not found - Install: npm install -g @ce-dot-net/ce-ace-cli"
  exit 1
fi

export ACE_ORG_ID=$(jq -r '.orgId // .env.ACE_ORG_ID // empty' .claude/settings.json 2>/dev/null || echo "")
export ACE_PROJECT_ID=$(jq -r '.projectId // .env.ACE_PROJECT_ID // empty' .claude/settings.json 2>/dev/null || echo "")

if [ -z "$ACE_ORG_ID" ] || [ -z "$ACE_PROJECT_ID" ]; then
  echo "❌ Run /ace-configure first"
  exit 1
fi

# Parse arguments
MODE="${1:-hybrid}"  # Default: hybrid mode
THOROUGHNESS="${2:-medium}"  # Default: medium

echo "🔄 Bootstrapping ACE playbook (mode=$MODE, thoroughness=$THOROUGHNESS)..."
echo "This may take 10-30 seconds..."

# CLI reads org/project from env vars automatically
ce-ace bootstrap \
  --mode "$MODE" \
  --thoroughness "$THOROUGHNESS"
