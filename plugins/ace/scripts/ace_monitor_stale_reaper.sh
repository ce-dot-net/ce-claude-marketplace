#!/usr/bin/env bash
# ACE Monitor — Stale File Reaper (v6.5.0 Item #10)
#
# Runs every 30 minutes via plugin.json experimental.monitors[].
# Removes /tmp ACE session state files older than 7 days.
# Previously these were swept only at SessionStart — long-running CC instances
# accumulated cruft over weeks. Monitor handles this independently.
#
# Targets:
#   /tmp/ace-session-*.txt        — session pin pointers
#   /tmp/ace-domains-*.json       — domain summary snapshots
#   /tmp/ace-domain-*.txt         — domain flag markers
#   /tmp/ace-patterns-precompact-*.json  — pre-compact pattern snapshots
#   /tmp/ace-disabled-*.flag      — disable flags
#   /tmp/ace-denials-*            — debounce timestamps from PermissionDenied hook
#
# Idempotent + silent. Never fails noisily.

set -uo pipefail

source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/scripts/_ace_env.sh"

MAX_AGE_DAYS=7

# Match patterns and reap files older than MAX_AGE_DAYS days
PATTERNS=(
  "ace-session-*.txt"
  "ace-domains-*.json"
  "ace-domain-*.txt"
  "ace-patterns-precompact-*.json"
  "ace-disabled-*.flag"
  "ace-eval-requested-*.flag"
  "ace-update-check-*.txt"
)

for pat in "${PATTERNS[@]}"; do
  find /tmp -maxdepth 1 -name "$pat" -type f -mtime "+${MAX_AGE_DAYS}" -delete 2>/dev/null || true
done

# Recursively reap debounce dirs older than 7 days
find /tmp -maxdepth 1 -name "ace-denials-*" -type d -mtime "+${MAX_AGE_DAYS}" -exec rm -rf {} + 2>/dev/null || true

exit 0
