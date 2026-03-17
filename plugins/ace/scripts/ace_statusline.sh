#!/usr/bin/env bash
# ACE Statusline — Per-task helpfulness from ACE hook chain
#
# Data flow:
#   SessionStart → ace-cli status/usage → ace-statusline-state.json (cached)
#   UserPromptSubmit → ace_before_task.py → ace-relevance.jsonl (searches, injections)
#   PreToolUse → ace-relevance.jsonl (domain_shift events)
#   Stop → ace_after_task.py → ace-statusline-state.json (learning results, task outcome)
#
# Shows: context% │ ACE playbook │ this-task metrics │ last learn result
set -eo pipefail

# ── Colors ──
R="\033[0m"       # reset
B="\033[1m"       # bold
D="\033[2m"       # dim
CYAN="\033[36m"
GRN="\033[32m"
YEL="\033[33m"
MAG="\033[35m"
BLU="\033[34m"
WHT="\033[37m"
RED="\033[31m"
BGMAG="\033[45m"  # magenta background

# ── Read CC JSON from stdin ──
INPUT_JSON=$(cat 2>/dev/null || echo "{}")
cwd=$(echo "$INPUT_JSON" | jq -r '.cwd // ""' 2>/dev/null || echo "")
used_pct=$(echo "$INPUT_JSON" | jq -r '.context_window.used_percentage // 0' 2>/dev/null || echo "0")

# ── Locate ACE data files ──
STATE_FILE=""
RELEVANCE_FILE=""
if [ -n "$cwd" ]; then
  [ -f "${cwd}/.claude/data/logs/ace-statusline-state.json" ] && STATE_FILE="${cwd}/.claude/data/logs/ace-statusline-state.json"
  [ -f "${cwd}/.claude/data/logs/ace-relevance.jsonl" ] && RELEVANCE_FILE="${cwd}/.claude/data/logs/ace-relevance.jsonl"
fi

# ── Defaults ──
patterns_total=0
last_learn=""
last_learn_timestamp=""
patterns_injected=0
avg_relevance=0
domains_count=0
domain_shifts=0
searches=0

# ── State file (SessionStart + Stop hooks write this) ──
if [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ]; then
  patterns_total=$(jq -r '.patterns_total // 0' "$STATE_FILE" 2>/dev/null || echo "0")
  last_learn=$(jq -r '.last_learn_result // ""' "$STATE_FILE" 2>/dev/null || echo "")
  last_learn_timestamp=$(jq -r '.last_learn_timestamp // ""' "$STATE_FILE" 2>/dev/null || echo "")
fi

# ── Relevance log (UserPromptSubmit + PreToolUse hooks write this) ──
# Get current session_id from state file (written by SessionStart)
CURRENT_SESSION=""
if [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ]; then
  CURRENT_SESSION=$(jq -r '.session_id // ""' "$STATE_FILE" 2>/dev/null || echo "")
fi

if [ -n "$RELEVANCE_FILE" ] && [ -f "$RELEVANCE_FILE" ]; then
  # Filter to current session only (not cumulative across all sessions)
  if [ -n "$CURRENT_SESSION" ]; then
    RECENT=$(grep "$CURRENT_SESSION" "$RELEVANCE_FILE" 2>/dev/null || true)
  else
    # Fallback: last 20 lines (roughly current task)
    RECENT=$(tail -20 "$RELEVANCE_FILE" 2>/dev/null || true)
  fi

  if [ -n "$RECENT" ]; then
    # Searches + injections + confidence
    SEARCHES=$(echo "$RECENT" | grep '"event": "search"' || true)
    if [ -n "$SEARCHES" ]; then
      searches=$(echo "$SEARCHES" | wc -l | tr -d ' ')
      patterns_injected=$(echo "$SEARCHES" | jq -r '.patterns_injected // 0' 2>/dev/null | awk '{s+=$1} END {print s+0}')
      avg_relevance=$(echo "$SEARCHES" | jq -r '.avg_confidence // 0' 2>/dev/null | awk '{s+=$1; n++} END {if(n>0) printf "%.0f", (s/n)*100; else print "0"}')
      domains_count=$(echo "$SEARCHES" | jq -r '.domains[]?' 2>/dev/null | sort -u | wc -l | tr -d ' ')
    fi
    # Domain shifts
    SHIFTS=$(echo "$RECENT" | grep '"event": "domain_shift"' || true)
    if [ -n "$SHIFTS" ]; then
      domain_shifts=$(echo "$SHIFTS" | wc -l | tr -d ' ')
    fi
  fi
fi

# ── Context % color ──
if [ "$used_pct" -ge 80 ] 2>/dev/null; then
  CTX_C="$RED"
elif [ "$used_pct" -ge 50 ] 2>/dev/null; then
  CTX_C="$YEL"
else
  CTX_C="$GRN"
fi

# ── Relevance % color ──
if [ "$avg_relevance" -ge 70 ] 2>/dev/null; then
  REL_C="$GRN"
elif [ "$avg_relevance" -ge 40 ] 2>/dev/null; then
  REL_C="$YEL"
else
  REL_C="$RED"
fi

# ═══════════════════════════════════════════
# BUILD OUTPUT
# ═══════════════════════════════════════════

OUT=""

# ── Context % (compact, from CC default) ──
OUT+="${CTX_C}${B}${used_pct}%${R}"

# ── Separator ──
OUT+=" ${D}⋮${R} "

# ── ACE badge + playbook ──
OUT+="${B}${MAG}◆ ACE${R}"
if [ "$patterns_total" != "0" ]; then
  OUT+=" ${WHT}${patterns_total}${R}${D}p${R}"
fi

# ── This task: injections ──
if [ "$patterns_injected" != "0" ]; then
  OUT+=" ${D}⋮${R} ${B}${BLU}${patterns_injected}${R}${D} injected${R}"
fi

# ── This task: relevance % ──
if [ "$avg_relevance" != "0" ] && [ "$avg_relevance" != "" ]; then
  OUT+=" ${REL_C}${B}${avg_relevance}%${R}"
fi

# ── This task: domains ──
if [ "$domains_count" != "0" ] && [ "$domains_count" != "" ]; then
  OUT+=" ${D}⋮${R} ${CYAN}${domains_count}${R}${D} domains${R}"
fi

# ── This task: domain shifts ──
if [ "$domain_shifts" != "0" ]; then
  OUT+=" ${YEL}${domain_shifts}${R}${D} shifts${R}"
fi

# ── Last learn result ──
if [ -n "$last_learn" ] && [ "$last_learn" != "null" ] && [ "$last_learn" != "" ]; then
  OUT+=" ${D}⋮${R} ${GRN}✓${R} ${D}${last_learn}${R}"
fi

echo -e "$OUT"
