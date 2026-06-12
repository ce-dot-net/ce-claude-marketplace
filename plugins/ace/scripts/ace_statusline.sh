#!/usr/bin/env bash
# ACE Statusline — 2-line: CC session info + per-task ACE metrics
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
model_name=$(echo "$INPUT_JSON" | jq -r '.model.display_name // ""' 2>/dev/null || echo "")

# ── Round floats to integers (CC used_percentage can be a float e.g. 28.999…) ──
# FIX B: assignment-with-cmdsubst doesn't trigger errexit; ${x:-0} fallback
#         covers empty/non-numeric input without "00" artefact from || echo 0.
used_pct=$(printf '%.0f' "${used_pct:-0}" 2>/dev/null); used_pct=${used_pct:-0}

# v6.5.0 Item #3 — newer CC stdin fields (CC 2.1.97/2.1.119/2.1.80 …).
# All empty/zero when running on older CC → conditional rendering keeps backward-compat.
effort_level=$(echo "$INPUT_JSON" | jq -r '.effort.level // ""' 2>/dev/null || echo "")
thinking_enabled=$(echo "$INPUT_JSON" | jq -r '.thinking.enabled // false' 2>/dev/null || echo "false")
git_worktree=$(echo "$INPUT_JSON" | jq -r '.workspace.git_worktree // ""' 2>/dev/null || echo "")
rl_5h_pct=$(echo "$INPUT_JSON" | jq -r '.rate_limits.five_hour.used_percentage // 0' 2>/dev/null || echo "0")
rl_5h_resets=$(echo "$INPUT_JSON" | jq -r '.rate_limits.five_hour.resets_at // ""' 2>/dev/null || echo "")
rl_7d_pct=$(echo "$INPUT_JSON" | jq -r '.rate_limits.seven_day.used_percentage // 0' 2>/dev/null || echo "0")
rl_7d_resets=$(echo "$INPUT_JSON" | jq -r '.rate_limits.seven_day.resets_at // ""' 2>/dev/null || echo "")
# Round rate-limit percentages to integers (same float-safety as used_pct above)
# FIX B: same pattern — avoids "00" artefact from non-numeric input.
rl_5h_pct=$(printf '%.0f' "${rl_5h_pct:-0}" 2>/dev/null); rl_5h_pct=${rl_5h_pct:-0}
rl_7d_pct=$(printf '%.0f' "${rl_7d_pct:-0}" 2>/dev/null); rl_7d_pct=${rl_7d_pct:-0}

# ── Format Unix epoch resets_at to human-readable local time ──
# Cross-platform: date -r (BSD/macOS) with GNU/Linux fallback; pure-integer guard.
fmt_reset() {
  local ts="$1"
  [ -z "$ts" ] || [ "$ts" = "null" ] && { echo ""; return; }
  case "$ts" in
    *[!0-9]*) echo "$ts"; return;;   # not a pure integer (e.g. already ISO) → show as-is
  esac
  date -r "$ts" '+%a %H:%M' 2>/dev/null || date -d "@$ts" '+%a %H:%M' 2>/dev/null || echo "$ts"
}
rl_5h_resets=$(fmt_reset "$rl_5h_resets")
rl_7d_resets=$(fmt_reset "$rl_7d_resets")

# ── Context % color ──
if [ "$used_pct" -ge 80 ] 2>/dev/null; then CTX_C="$RED"
elif [ "$used_pct" -ge 50 ] 2>/dev/null; then CTX_C="$YEL"
else CTX_C="$GRN"; fi

# ── Context bar (15 chars wide) ──
BAR_WIDTH=15
filled=$(( used_pct * BAR_WIDTH / 100 ))
empty=$(( BAR_WIDTH - filled ))
# Clamp
[ "$filled" -lt 0 ] 2>/dev/null && filled=0
[ "$filled" -gt "$BAR_WIDTH" ] 2>/dev/null && filled=$BAR_WIDTH
[ "$empty" -lt 0 ] 2>/dev/null && empty=0
bar_filled=""
bar_empty=""
for (( i=0; i<filled; i++ )); do bar_filled+="█"; done
for (( i=0; i<empty; i++ )); do bar_empty+="░"; done

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
quality_pct=0
time_saved=""

# ── Read per-task metrics from JSONL ──
# Task boundary: events since last "execution" event (Stop hook writes these)
# This gives us "current task" metrics that reset after each learn cycle
if [ -n "$RELEVANCE_FILE" ] && [ -f "$RELEVANCE_FILE" ]; then
  # Use python for reliable task-boundary detection (fast, <50ms)
  METRICS=$(python3 -c "
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
" 2>/dev/null || echo "")
  patterns_injected=$(echo "$METRICS" | grep '^patterns_injected=' | cut -d= -f2)
  avg_relevance=$(echo "$METRICS" | grep '^avg_relevance=' | cut -d= -f2)
  domains_count=$(echo "$METRICS" | grep '^domains_count=' | cut -d= -f2)
  domain_shifts=$(echo "$METRICS" | grep '^domain_shifts=' | cut -d= -f2)
  # Ensure defaults if parsing failed
  patterns_injected="${patterns_injected:-0}"
  avg_relevance="${avg_relevance:-0}"
  domains_count="${domains_count:-0}"
  domain_shifts="${domain_shifts:-0}"
fi

# ── Relevance % color ──
if [ "$avg_relevance" -ge 70 ] 2>/dev/null; then REL_C="$GRN"
elif [ "$avg_relevance" -ge 40 ] 2>/dev/null; then REL_C="$YEL"
else REL_C="$RED"; fi

# ── Read self-eval review result (ace-review-result.json) ──
REVIEW_FILE=""
if [ -n "$cwd" ] && [ -f "${cwd}/.claude/data/logs/ace-review-result.json" ]; then
  REVIEW_FILE="${cwd}/.claude/data/logs/ace-review-result.json"
  review_quality_pct=$(jq -r '.quality_pct // .helpful_pct // 0' "$REVIEW_FILE" 2>/dev/null || echo "0")
  review_time_saved=$(jq -r '.time_saved // ""' "$REVIEW_FILE" 2>/dev/null || echo "")
  if [ "$review_quality_pct" != "0" ] && [ "$review_quality_pct" != "" ]; then
    quality_pct="$review_quality_pct"
  fi
  if [ -n "$review_time_saved" ] && [ "$review_time_saved" != "null" ] && [ "$review_time_saved" != "" ]; then
    time_saved="$review_time_saved"
  fi
fi

# ═══════════════════════════════════════
# BUILD OUTPUT — Line 1: Model · context bar · context%
# ═══════════════════════════════════════
LINE1=""
if [ -n "$model_name" ] && [ "$model_name" != "null" ]; then
  LINE1+="${CYN}${B}${model_name}${R}"
else
  LINE1+="${CYN}${B}Claude${R}"
fi
LINE1+=" ${D}·${R} ${CTX_C}${bar_filled}${D}${bar_empty}${R} ${CTX_C}${B}${used_pct}%${R}"

# v6.5.0 Item #3: append effort/thinking/worktree indicators (suppress when empty)
if [ "$thinking_enabled" = "true" ]; then
  LINE1+=" ${YEL}${B}[thinking]${R}"
fi
case "$effort_level" in
  high|xhigh|max)
    LINE1+=" ${MAG}${B}[${effort_level}]${R}"
    ;;
esac
if [ -n "$git_worktree" ] && [ "$git_worktree" != "null" ]; then
  LINE1+=" ${CYN}${D}[wt:$(basename "$git_worktree")]${R}"
fi

# ═══════════════════════════════════════
# BUILD OUTPUT — Line 2: ACE metrics
# ═══════════════════════════════════════
LINE2=""

# ACE badge
LINE2+="${B}${MAG}◆ ACE${R}"

# Patterns injected
if [ "$patterns_injected" != "0" ]; then
  LINE2+="  ${D}⋮${R} ${B}${BLU}${patterns_injected}${R}${D} injected${R}"
fi

# Relevance %
if [ "$avg_relevance" != "0" ] && [ "$avg_relevance" != "" ]; then
  LINE2+=" ${REL_C}${B}${avg_relevance}%${R}"
fi

# Domains
if [ "$domains_count" != "0" ] && [ "$domains_count" != "" ]; then
  LINE2+="  ${D}⋮${R} ${CYN}${B}${domains_count}${R}${D} domains${R}"
fi

# Domain shifts
if [ "$domain_shifts" != "0" ]; then
  LINE2+=" ${YEL}${B}${domain_shifts}${R}${D} shifts${R}"
fi

# Quality % + time saved
if [ "$quality_pct" != "0" ] && [ "$quality_pct" != "" ]; then
  if [ "$quality_pct" -ge 70 ] 2>/dev/null; then H_C="$GRN"
  elif [ "$quality_pct" -ge 40 ] 2>/dev/null; then H_C="$YEL"
  else H_C="$RED"; fi
  LINE2+="  ${D}⋮${R} ${H_C}${B}${quality_pct}% quality${R}"
  if [ -n "$time_saved" ] && [ "$time_saved" != "" ]; then
    LINE2+=" ${D}~${time_saved}${R}"
  fi
fi

# v6.5.0 Item #3: rate-limit LINE3 (suppressed when both percentages are 0 — backward-compat).
LINE3=""
if [ "$rl_5h_pct" != "0" ] || [ "$rl_7d_pct" != "0" ]; then
  RL_C="$GRN"
  if [ "$rl_5h_pct" -ge 80 ] 2>/dev/null || [ "$rl_7d_pct" -ge 80 ] 2>/dev/null; then
    RL_C="$RED"
  elif [ "$rl_5h_pct" -ge 50 ] 2>/dev/null || [ "$rl_7d_pct" -ge 50 ] 2>/dev/null; then
    RL_C="$YEL"
  fi
  LINE3="${D}limits${R} 5h:${RL_C}${B}${rl_5h_pct}%${R}"
  if [ -n "$rl_5h_resets" ] && [ "$rl_5h_resets" != "null" ]; then
    LINE3+="${D} →${rl_5h_resets}${R}"
  fi
  LINE3+="  7d:${RL_C}${B}${rl_7d_pct}%${R}"
  if [ -n "$rl_7d_resets" ] && [ "$rl_7d_resets" != "null" ]; then
    LINE3+="${D} →${rl_7d_resets}${R}"
  fi
fi

echo -e "$LINE1"
echo -e "$LINE2"
if [ -n "$LINE3" ]; then
  echo -e "$LINE3"
fi
exit 0
