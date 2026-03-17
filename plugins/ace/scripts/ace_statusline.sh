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

# ── Read per-session metrics from JSONL (strict session_id filter via jq) ──
if [ -n "$RELEVANCE_FILE" ] && [ -f "$RELEVANCE_FILE" ] && [ -n "$session_id" ]; then
  # Single jq pass: filter by session_id, compute all metrics at once
  eval "$(jq -rs --arg sid "$session_id" '
    [ .[] | select(.session_id == $sid) ] as $events |
    [ $events[] | select(.event == "search") ] as $searches |
    [ $events[] | select(.event == "domain_shift") ] as $shifts |
    ([ $searches[].patterns_injected // 0 ] | add // 0) as $inj |
    (if ($searches | length) > 0 then
      ([ $searches[].avg_confidence // 0 ] | add) / ($searches | length) * 100 | floor
    else 0 end) as $rel |
    ([ $searches[].domains[]? ] | unique | length) as $doms |
    ($shifts | length) as $shf |
    "patterns_injected=\($inj)\navg_relevance=\($rel)\ndomains_count=\($doms)\ndomain_shifts=\($shf)"
  ' "$RELEVANCE_FILE" 2>/dev/null)" || true
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

echo -e "$OUT"
