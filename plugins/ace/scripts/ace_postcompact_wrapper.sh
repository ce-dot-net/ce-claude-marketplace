#!/usr/bin/env bash
# ACE PostCompact Hook - Log compaction events for insights
# v6.0.0: Track when context compaction occurs (CC 2.1.76+)
set -eo pipefail
trap 'exit 0' ERR

# Resolve paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Read stdin JSON
INPUT_JSON=$(cat 2>/dev/null || echo "{}")

# Extract session_id
SESSION_ID=$(echo "$INPUT_JSON" | jq -r '.session_id // empty' 2>/dev/null || echo "")

if [ -z "$SESSION_ID" ]; then
  exit 0
fi

# Log compact event via Python (lightweight call)
echo "$INPUT_JSON" | python3 -c "
import sys, json
sys.path.insert(0, '${PLUGIN_ROOT}/shared-hooks/utils')
from ace_relevance_logger import log_compact_event
event = json.load(sys.stdin)
log_compact_event(session_id=event.get('session_id', ''))
" 2>/dev/null || true

# Always exit 0
exit 0
