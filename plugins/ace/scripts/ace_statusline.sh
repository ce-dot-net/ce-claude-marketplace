#!/usr/bin/env bash
# ACE Statusline — Per-task metrics, user-friendly
# Reads CC JSON stdin + ace-relevance.jsonl (local, no network calls)
set -eo pipefail

# ── Colors ──
R="\033[0m"
B="\033[1m"
D="\033[2m"
GRN="\033[32m"
YEL="\033[33m"
MAG="\033[35m"
BLU="\033[34m"
CYN="\033[36m"
WHT="\033[37m"
RED="\033[31m"

# ── Read CC JSON from stdin ──
INPUT_JSON=$(cat 2>/dev/null || echo "{}")
cwd=$(echo "$INPUT_JSON" | jq -r '.cwd // ""' 2>/dev/null || echo "")
used_pct=$(echo "$INPUT_JSON" | jq -r '.context_window.used_percentage // 0' 2>/dev/null || echo "0")
session_id=$(echo "$INPUT_JSON" | jq -r '.session_id // ""' 2>/dev/null || echo "")

# ── Context % color ──
if [ "$used_pct" -ge 80 ] 2>/dev/null; then CTX_C="$RED"
elif [ "$used_pct" -ge 50 ] 2>/dev/null; then CTX_C="$YEL"
else CTX_C="$GRN"; fi

# ── Locate relevance log ──
RELEVANCE_FILE=""
if [ -n "$cwd" ] && [ -f "${cwd}/.claude/data/logs/ace-relevance.jsonl" ]; then
  RELEVANCE_FILE="${cwd}/.claude/data/logs/ace-relevance.jsonl"
fi

# ── Defaults ──
patterns_injected=0
avg_relevance=0
domains_count=0
domain_shifts=0
helpful_pct=0
time_saved=""

# ── Read per-task metrics from JSONL ──
# Task boundary: events since last "execution" event (Stop hook writes these)
# This gives us "current task" metrics that reset after each learn cycle
if [ -n "$RELEVANCE_FILE" ] && [ -f "$RELEVANCE_FILE" ]; then
  # Use python for reliable task-boundary detection (fast, <50ms)
  eval "$(python3 -c "
import json, sys
events = []
with open('$RELEVANCE_FILE') as f:
    for line in f:
        line = line.strip()
        if line:
            try: events.append(json.loads(line))
            except: pass
# Find last execution event (= task boundary from Stop hook)
last_exec = -1
for i, e in enumerate(events):
    if e.get('event') == 'execution':
        last_exec = i
# Current task = everything after last execution
current = events[last_exec + 1:] if last_exec >= 0 else events
searches = [e for e in current if e.get('event') == 'search']
shifts = [e for e in current if e.get('event') == 'domain_shift']
inj = sum(s.get('patterns_injected', 0) for s in searches)
rel = int(sum(s.get('avg_confidence', 0) for s in searches) / len(searches) * 100) if searches else 0
doms = len(set(d for s in searches for d in s.get('domains', [])))
shf = len(shifts)

# No fake helpfulness — only real self-eval from ace-review-result.json
print(f'patterns_injected={inj}')
print(f'avg_relevance={rel}')
print(f'domains_count={doms}')
print(f'domain_shifts={shf}')
" 2>/dev/null)" || true
fi

# ── Relevance % color ──
if [ "$avg_relevance" -ge 70 ] 2>/dev/null; then REL_C="$GRN"
elif [ "$avg_relevance" -ge 40 ] 2>/dev/null; then REL_C="$YEL"
else REL_C="$RED"; fi

# ═══════════════════════════════════════
# BUILD OUTPUT — Line 1: metrics
# ═══════════════════════════════════════
OUT=""

# Context %
OUT+="${CTX_C}${B}${used_pct}%${R}"
OUT+=" ${D}⋮${R} "

# ACE badge
OUT+="${B}${MAG}◆ ACE${R}"

# Patterns injected
if [ "$patterns_injected" != "0" ]; then
  OUT+="  ${D}⋮${R} ${B}${BLU}${patterns_injected}${R}${D} injected${R}"
fi

# Relevance %
if [ "$avg_relevance" != "0" ] && [ "$avg_relevance" != "" ]; then
  OUT+=" ${REL_C}${B}${avg_relevance}%${R}"
fi

# Domains
if [ "$domains_count" != "0" ] && [ "$domains_count" != "" ]; then
  OUT+="  ${D}⋮${R} ${CYN}${B}${domains_count}${R}${D} domains${R}"
fi

# Domain shifts
if [ "$domain_shifts" != "0" ]; then
  OUT+=" ${YEL}${B}${domain_shifts}${R}${D} shifts${R}"
fi

# ── Read self-eval review result (ace-review-result.json) ──
REVIEW_FILE=""
if [ -n "$cwd" ] && [ -f "${cwd}/.claude/data/logs/ace-review-result.json" ]; then
  REVIEW_FILE="${cwd}/.claude/data/logs/ace-review-result.json"
  review_helpful_pct=$(jq -r '.helpful_pct // 0' "$REVIEW_FILE" 2>/dev/null || echo "0")
  review_time_saved=$(jq -r '.time_saved // ""' "$REVIEW_FILE" 2>/dev/null || echo "")
  if [ "$review_helpful_pct" != "0" ] && [ "$review_helpful_pct" != "" ]; then
    helpful_pct="$review_helpful_pct"
  fi
  if [ -n "$review_time_saved" ] && [ "$review_time_saved" != "null" ] && [ "$review_time_saved" != "" ]; then
    time_saved="$review_time_saved"
  fi
fi

# ── Last task: how helpful was ACE? (shows after Stop hook fires) ──
if [ "$helpful_pct" != "0" ] && [ "$helpful_pct" != "" ]; then
  if [ "$helpful_pct" -ge 70 ] 2>/dev/null; then H_C="$GRN"
  elif [ "$helpful_pct" -ge 40 ] 2>/dev/null; then H_C="$YEL"
  else H_C="$RED"; fi
  OUT+="  ${D}⋮${R} ${H_C}${B}${helpful_pct}% helpful${R}"
  if [ -n "$time_saved" ] && [ "$time_saved" != "" ]; then
    OUT+=" ${D}~${time_saved} saved${R}"
  fi
fi

echo -e "$OUT"
