#!/usr/bin/env bash
# ACE Monitor — Log Reaper (v6.5.0 Item #10)
#
# Runs every 5 minutes via plugin.json experimental.monitors[].
# Rotates ace-relevance.jsonl when it exceeds 10 MB (10485760 bytes).
# Previously, log rotation only fired during SessionStart — long-running sessions
# never rotated. Monitor decouples rotation from session lifecycle.
#
# Idempotent: silent no-op on missing file, on under-threshold size,
# or on permission errors. Hook MUST NOT fail noisily — monitors run forever.

set -uo pipefail

source "${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}/scripts/_ace_env.sh"

MAX_SIZE=10485760   # 10 MB in bytes
KEEP_BACKUPS=2

reap_one() {
  local path="$1"
  [ -f "$path" ] || return 0
  # Cross-platform size (BSD stat vs GNU stat)
  local size
  size=$(stat -f%z "$path" 2>/dev/null || stat -c%s "$path" 2>/dev/null || echo 0)
  if [ "$size" -lt "$MAX_SIZE" ] 2>/dev/null; then
    return 0
  fi
  # Rotate: ace-relevance.jsonl → ace-relevance.jsonl.1 (oldest dropped)
  local ts
  ts=$(date +%Y%m%d-%H%M%S)
  local backup="${path}.${ts}"
  mv "$path" "$backup" 2>/dev/null || return 0
  : > "$path" 2>/dev/null || true
  # Prune older backups beyond KEEP_BACKUPS
  ls -t "${path}".* 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs -r rm -f 2>/dev/null || true
}

# Search both possible roots (new and legacy)
ROOTS=()
if [ -n "${CLAUDE_PLUGIN_DATA:-}" ]; then
  ROOTS+=("${CLAUDE_PLUGIN_DATA}/projects")
fi
ROOTS+=("${HOME}/.claude/data/logs")
ROOTS+=("$(pwd)/.claude/data/logs")

for root in "${ROOTS[@]}"; do
  [ -d "$root" ] || continue
  while IFS= read -r -d '' f; do
    reap_one "$f"
  done < <(find "$root" -maxdepth 4 -name "ace-relevance.jsonl" -type f -print0 2>/dev/null)
done

exit 0
