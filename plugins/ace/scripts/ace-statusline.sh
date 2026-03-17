#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# ACE Status Line — working-buddy
# ═══════════════════════════════════════════════════════════════════════════════
#
# Visualizes ACE (Agentic Context Engineering) session effectiveness metrics
# in Claude Code's status bar.
#
# Responsive display modes based on terminal width:
#   - nano   (<40 cols):  QPT only
#   - micro  (40-59):     QPT + focus + confidence
#   - mini   (60-99):     QPT + metrics + playbook health
#   - normal (100+):      Full dashboard with sparkline activity charts
#
# Data sources:
#   - ace-relevance.jsonl (local, <10ms) — session metrics + sparklines
#   - ace-cli status --json (60s cache) — playbook health
#
# Dependencies: jq, date, ace-cli (optional)
# ═══════════════════════════════════════════════════════════════════════════════
set -o pipefail

# Allow sourcing for tests without executing main
if [ "${1:-}" = "--source-only" ]; then
  _SOURCE_ONLY=true
fi

# ─── CONFIGURATION ───────────────────────────────────────────────────────────

ACE_RELEVANCE=".claude/data/logs/ace-relevance.jsonl"
ACE_CACHE="/tmp/ace-statusline-cache${ACE_PROJECT_ID:+-$ACE_PROJECT_ID}.json"
ACE_CACHE_TTL=60

# ─── COLOR PALETTE (ACE brand: #2CF1BE primary, #212126 dark) ────────────────

RESET='\033[0m'
DIM='\033[2;37m'
BOLD='\033[1;37m'
# ACE brand teal #2CF1BE
ACE_PRIMARY='\033[38;2;44;241;190m'
ACE_PRIMARY_DIM='\033[38;2;30;170;134m'
# Status colors
GREEN='\033[38;2;74;222;128m'
YELLOW='\033[38;2;250;204;21m'
RED='\033[38;2;239;68;68m'
CYAN='\033[38;2;44;241;190m'
BOLD_CYAN='\033[1;38;2;44;241;190m'

# ─── COLOR HELPERS ──────────────────────────────────────────────────────────

qpt_color() {
  local score="$1"
  if [ "$score" -ge 70 ]; then
    printf '%s' "$GREEN"
  elif [ "$score" -ge 40 ]; then
    printf '%s' "$YELLOW"
  else
    printf '%s' "$RED"
  fi
}

terrain_color() {
  case "$1" in
    familiar) printf '%s' "$GREEN" ;;
    exploring) printf '%s' "$YELLOW" ;;
    *) printf '%s' "$RED" ;;
  esac
}

# ─── USAGE BAR (PAI-style ⛁ with green→yellow→orange→red gradient) ─────────

# Color gradient for usage bar position: green→yellow→orange→red
get_usage_bucket_color() {
  local pos=$1 max=$2
  local pct=$((pos * 100 / max))
  local r g b
  if [ "$pct" -le 33 ]; then
    r=$((74 + (250 - 74) * pct / 33))
    g=$((222 + (204 - 222) * pct / 33))
    b=$((128 + (21 - 128) * pct / 33))
  elif [ "$pct" -le 66 ]; then
    local t=$((pct - 33))
    r=$((250 + (251 - 250) * t / 33))
    g=$((204 + (146 - 204) * t / 33))
    b=$((21 + (60 - 21) * t / 33))
  else
    local t=$((pct - 66))
    r=$((251 + (239 - 251) * t / 34))
    g=$((146 + (68 - 146) * t / 34))
    b=$((60 + (68 - 60) * t / 34))
  fi
  printf '\033[38;2;%d;%d;%dm' "$r" "$g" "$b"
}

USAGE_BUCKET_EMPTY='\033[38;2;45;50;60m'

render_usage_bar() {
  local width=$1 pct=$2
  local output=""
  [ "$pct" -gt 100 ] && pct=100
  local filled=$((pct * width / 100))
  [ "$filled" -lt 0 ] && filled=0
  local i
  for ((i = 1; i <= width; i++)); do
    if [ "$i" -le "$filled" ]; then
      local color
      color=$(get_usage_bucket_color "$i" "$width")
      output="${output}${color}⛁${RESET}"
    else
      output="${output}${USAGE_BUCKET_EMPTY}⛁${RESET}"
    fi
  done
  echo -e "$output"
}

# ─── CROSS-PLATFORM HELPERS ─────────────────────────────────────────────────

# get_mtime(filepath) — file modification time in seconds since epoch
get_mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}

# ─── SESSION AGGREGATION ────────────────────────────────────────────────────

# aggregate_session(session_id, relevance_file)
# Reads ace-relevance.jsonl and sets global variables for the given session.
# Uses a single jq -rs invocation to compute all metrics at once.
aggregate_session() {
  local sid="$1"
  local rfile="$2"

  # Defaults — used when file missing, session absent, or jq fails
  SESSION_FOCUS_PCT=0
  SESSION_CONFIDENCE="0"
  SESSION_LEARN_SENT=0
  SESSION_LEARN_TOTAL=0
  SESSION_SUCCESS_RATE=0
  SESSION_DOMAINS=""
  SESSION_INJ_TOTAL=0
  SESSION_INJ_USED=0

  if [ ! -f "$rfile" ]; then
    return 0
  fi

  eval "$(jq -rs --arg sid "$sid" '
    [ .[] | select(.session_id == $sid) ] as $events |
    if ($events | length) == 0 then
      "SESSION_FOCUS_PCT=0\nSESSION_CONFIDENCE='\''0'\''\nSESSION_LEARN_SENT=0\nSESSION_LEARN_TOTAL=0\nSESSION_SUCCESS_RATE=0\nSESSION_DOMAINS='\'\''\nSESSION_INJ_TOTAL=0\nSESSION_INJ_USED=0"
    else
      # Execution events
      [ $events[] | select(.event == "execution") ] as $execs |
      # Search events
      [ $events[] | select(.event == "search") ] as $searches |

      # Focus: state_changing / tools_executed * 100
      (if ($execs | length) > 0 then
        ([ $execs[].state_changing_tools ] | add) as $sc |
        ([ $execs[].tools_executed ] | add) as $te |
        if $te > 0 then (($sc * 100) / $te | floor) else 0 end
      else 0 end) as $focus |

      # Confidence: avg_confidence from the LAST search event (by array order)
      (if ($searches | length) > 0 then
        ($searches | last | .avg_confidence | tostring)
      else "0" end) as $conf |

      # Learning sent / total
      (if ($execs | length) > 0 then
        [ $execs[] | select(.learning_sent == true) ] | length
      else 0 end) as $lsent |
      ($execs | length) as $ltotal |

      # Success rate
      (if ($execs | length) > 0 then
        (([ $execs[] | select(.success == true) ] | length) * 100 / ($execs | length) | floor)
      else 0 end) as $srate |

      # Unique domains
      ([ $searches[].domains[]? ] | unique | join(",")) as $doms |

      # Injection: patterns_injected (search) and patterns_used_count (exec)
      ([ $searches[].patterns_injected // 0 ] | add // 0) as $inj_total |
      ([ $execs[].patterns_used_count // 0 ] | add // 0) as $inj_used |

      "SESSION_FOCUS_PCT=\($focus)\nSESSION_CONFIDENCE=\($conf | @sh)\nSESSION_LEARN_SENT=\($lsent)\nSESSION_LEARN_TOTAL=\($ltotal)\nSESSION_SUCCESS_RATE=\($srate)\nSESSION_DOMAINS=\($doms | @sh)\nSESSION_INJ_TOTAL=\($inj_total)\nSESSION_INJ_USED=\($inj_used)"
    end
  ' "$rfile" 2>/dev/null)" || {
    SESSION_FOCUS_PCT=0
    SESSION_CONFIDENCE="0"
    SESSION_LEARN_SENT=0
    SESSION_LEARN_TOTAL=0
    SESSION_SUCCESS_RATE=0
    SESSION_DOMAINS=""
    SESSION_INJ_TOTAL=0
    SESSION_INJ_USED=0
  }
}

# ─── PLAYBOOK DATA (ACE-CLI CACHE) ─────────────────────────────────────────

# fetch_playbook_data()
# Reads ace-cli data from cache, refreshes in background when stale.
# Sets: PLAYBOOK_PATTERNS, PLAYBOOK_HEALTHY_PCT, PLAYBOOK_DOMAINS, PLAYBOOK_TOP_DOMAINS,
#        ACE_ORG_NAME, ACE_PROJECT_NAME
fetch_playbook_data() {
  # Defaults
  PLAYBOOK_PATTERNS="--"
  PLAYBOOK_HEALTHY_PCT=0
  PLAYBOOK_DOMAINS=0
  PLAYBOOK_TOP_DOMAINS=""
  ACE_ORG_NAME=""
  ACE_PROJECT_NAME=""
  USAGE_PATTERNS_USED=0
  USAGE_PATTERNS_LIMIT=0
  USAGE_PATTERNS_PCT=0
  USAGE_TRACES_USED=0
  USAGE_TRACES_LIMIT=0
  USAGE_API_USED=0
  USAGE_API_LIMIT=0

  local now
  now=$(date +%s)

  _parse_playbook_cache() {
    local cache_file="$1"
    local total
    total=$(jq -r '.playbook.total_patterns // 0' "$cache_file" 2>/dev/null)
    PLAYBOOK_PATTERNS="${total:-0}"

    local helpful
    helpful=$(jq -r '.playbook.helpful_total // 0' "$cache_file" 2>/dev/null)
    helpful=${helpful%%.*}  # truncate float to integer for bash arithmetic
    local harmful
    harmful=$(jq -r '.playbook.harmful_total // 0' "$cache_file" 2>/dev/null)
    harmful=${harmful%%.*}  # truncate float to integer for bash arithmetic
    local denom=$((helpful + harmful))
    if [ "$denom" -gt 0 ]; then
      PLAYBOOK_HEALTHY_PCT=$((helpful * 100 / denom))
    else
      PLAYBOOK_HEALTHY_PCT=0
    fi

    local dom_count
    dom_count=$(jq -r '.playbook.by_domain | length // 0' "$cache_file" 2>/dev/null)
    PLAYBOOK_DOMAINS="${dom_count:-0}"

    local top
    top=$(jq -r '.top_domains // ""' "$cache_file" 2>/dev/null)
    PLAYBOOK_TOP_DOMAINS="${top:-}"

    local oname
    oname=$(jq -r '.ace_org_name // ""' "$cache_file" 2>/dev/null)
    ACE_ORG_NAME="${oname:-}"
    local pname
    pname=$(jq -r '.ace_project_name // ""' "$cache_file" 2>/dev/null)
    ACE_PROJECT_NAME="${pname:-}"

    # Usage / consumption limits
    local pat_used pat_limit traces_used traces_limit api_used api_limit
    pat_used=$(jq -r '.subscription.usage.patterns.used // 0' "$cache_file" 2>/dev/null)
    pat_limit=$(jq -r '.subscription.usage.patterns.limit // 0' "$cache_file" 2>/dev/null)
    traces_used=$(jq -r '.subscription.usage.traces_today.used // 0' "$cache_file" 2>/dev/null)
    traces_limit=$(jq -r '.subscription.usage.traces_today.limit // 0' "$cache_file" 2>/dev/null)
    api_used=$(jq -r '.subscription.usage.api_calls.used // 0' "$cache_file" 2>/dev/null)
    api_limit=$(jq -r '.subscription.usage.api_calls.limit // 0' "$cache_file" 2>/dev/null)
    USAGE_PATTERNS_USED="${pat_used:-0}"
    USAGE_PATTERNS_LIMIT="${pat_limit:-0}"
    USAGE_TRACES_USED="${traces_used:-0}"
    USAGE_TRACES_LIMIT="${traces_limit:-0}"
    USAGE_API_USED="${api_used:-0}"
    USAGE_API_LIMIT="${api_limit:-0}"
    if [ "${USAGE_PATTERNS_LIMIT:-0}" -gt 0 ] 2>/dev/null; then
      USAGE_PATTERNS_PCT=$((USAGE_PATTERNS_USED * 100 / USAGE_PATTERNS_LIMIT))
    else
      USAGE_PATTERNS_PCT=0
    fi
  }

  _bg_refresh_cache() {
    local cache_file="$1"
    (
      local status_json
      status_json=$(ace-cli status --json 2>/dev/null) || return
      local domains_json
      domains_json=$(ace-cli domains --json 2>/dev/null) || return

      local top5
      top5=$(echo "$domains_json" | jq -r '[.domains[:5][].name] | join(",")' 2>/dev/null)

      # Resolve org name from whoami
      local org_name=""
      local whoami_json
      if whoami_json=$(ace-cli whoami --json 2>/dev/null); then
        local cur_org
        cur_org=$(echo "$whoami_json" | jq -r '.current_org_id // ""' 2>/dev/null)
        if [ -n "$cur_org" ]; then
          org_name=$(echo "$whoami_json" | jq -r --arg oid "$cur_org" \
            '.user.organizations[] | select(.org_id == $oid) | .name // ""' 2>/dev/null)
        fi
      fi

      # Resolve project name from projects list
      local proj_name=""
      local proj_id="${ACE_PROJECT_ID:-}"
      if [ -n "$proj_id" ]; then
        local projects_json
        if projects_json=$(ace-cli projects --json 2>/dev/null); then
          proj_name=$(echo "$projects_json" | jq -r --arg pid "$proj_id" \
            '.projects[] | select(.project_id == $pid) | .project_name // ""' 2>/dev/null)
        fi
      fi

      echo "$status_json" | jq \
        --arg td "$top5" \
        --arg on "$org_name" \
        --arg pn "$proj_name" \
        '. + {top_domains: $td, ace_org_name: $on, ace_project_name: $pn}' \
        >"${cache_file}.tmp" 2>/dev/null &&
        mv "${cache_file}.tmp" "$cache_file"
    ) &
    disown
  }

  if [ -f "$ACE_CACHE" ]; then
    local mtime
    mtime=$(get_mtime "$ACE_CACHE")
    local age=$((now - mtime))

    _parse_playbook_cache "$ACE_CACHE"

    if [ "$age" -ge "${ACE_CACHE_TTL:-60}" ]; then
      # Stale — refresh in background
      _bg_refresh_cache "$ACE_CACHE"
    fi
  else
    # No cache at all — keep defaults, refresh in background
    _bg_refresh_cache "$ACE_CACHE"
  fi
}

# ─── ACE QPT (QUALITY PER TASK) ─────────────────────────────────────────────

compute_qpt() {
  local learn_rate=0
  if [ "${SESSION_LEARN_TOTAL:-0}" -gt 0 ]; then
    learn_rate=$(jq -n "${SESSION_LEARN_SENT} / ${SESSION_LEARN_TOTAL}")
  fi

  ACE_QPT=$(jq -n "
    (${SESSION_FOCUS_PCT:-0} / 100 * 0.35 +
     ${SESSION_CONFIDENCE:-0} * 0.30 +
     $learn_rate * 0.20 +
     ${SESSION_SUCCESS_RATE:-0} / 100 * 0.15) * 100 | round
  ")
  ACE_QPT="${ACE_QPT:-0}"
}

# ─── TERRAIN INDICATOR ─────────────────────────────────────────────────────

compute_terrain() {
  local session_domains="${SESSION_DOMAINS:-}"
  local top_domains="${PLAYBOOK_TOP_DOMAINS:-}"

  if [ -z "$session_domains" ] || [ -z "$top_domains" ]; then
    ACE_TERRAIN="unknown"
    return
  fi

  local overlap=0 session_count=0
  local IFS=','
  for domain in $session_domains; do
    session_count=$((session_count + 1))
    case ",$top_domains," in
      *,"$domain",*) overlap=$((overlap + 1)) ;;
    esac
  done

  if [ "$session_count" -eq 0 ]; then
    ACE_TERRAIN="unknown"
  elif [ $((overlap * 100 / session_count)) -ge 70 ]; then
    ACE_TERRAIN="familiar"
  elif [ $((overlap * 100 / session_count)) -ge 30 ]; then
    ACE_TERRAIN="exploring"
  else
    ACE_TERRAIN="blind spot"
  fi
}

# ─── SPARKLINE RENDERING ─────────────────────────────────────────────────────

render_sparkline() {
  local buckets_str="$1"
  local -a buckets
  read -ra buckets <<<"$buckets_str"

  local max=0
  for val in "${buckets[@]}"; do
    [ "$val" -gt "$max" ] && max="$val"
  done

  if [ "$max" -eq 0 ]; then
    local out=""
    for _ in "${buckets[@]}"; do out="${out} "; done
    echo "$out"
    return
  fi

  # PAI-style: block height encodes value level, color encodes quality band
  # 10 levels mapped to 5 block heights with distinct colors
  # High activity = tall green, low activity = short red
  local out=""
  for val in "${buckets[@]}"; do
    if [ "$val" -eq 0 ]; then
      out="${out}\033[38;2;45;50;60m \033[0m"
    else
      local level=$(((val * 10 + max - 1) / max))
      [ "$level" -gt 10 ] && level=10
      [ "$level" -lt 1 ] && level=1
      if [ "$level" -ge 9 ]; then
        out="${out}\033[38;2;34;197;94m▅\033[0m"     # bright green
      elif [ "$level" -ge 7 ]; then
        out="${out}\033[38;2;74;222;128m▄\033[0m"    # green
      elif [ "$level" -ge 5 ]; then
        out="${out}\033[38;2;59;130;246m▃\033[0m"    # blue
      elif [ "$level" -ge 3 ]; then
        out="${out}\033[38;2;253;224;71m▂\033[0m"    # yellow
      else
        out="${out}\033[38;2;248;113;113m▁\033[0m"   # light red
      fi
    fi
  done
  echo -e "$out"
}

# ─── TIME-BUCKETED EVENT COUNTING ───────────────────────────────────────────

bucket_events() {
  local relevance_file="$1"
  local num_buckets="$2"
  local bucket_seconds="$3"

  local now
  now=$(date +%s)
  local window_start=$((now - num_buckets * bucket_seconds))

  # Pre-filter: for short windows, only read recent lines to avoid parsing entire file
  local max_lines=0
  if [ "$bucket_seconds" -le 60 ]; then
    max_lines=200
  elif [ "$bucket_seconds" -le 300 ]; then
    max_lines=500
  elif [ "$bucket_seconds" -le 3600 ]; then
    max_lines=2000
  fi

  local input_file="$relevance_file"
  local tmp_file=""
  if [ "$max_lines" -gt 0 ]; then
    tmp_file="/tmp/ace-bucket-$$"
    tail -n "$max_lines" "$relevance_file" >"$tmp_file" 2>/dev/null
    input_file="$tmp_file"
  fi

  local result
  if result=$(jq -rs --argjson start "$window_start" \
    --argjson bsec "$bucket_seconds" \
    --argjson nbuckets "$num_buckets" '
    [.[] | select(type == "object" and has("timestamp")) | .timestamp |
      (sub("[.+Z].*$"; "") + "Z" | fromdateiso8601) as $ts |
      select($ts >= $start) |
      (($ts - $start) / $bsec | floor)
    ] as $indices |
    [range($nbuckets)] | map(. as $i | [$indices[] | select(. == $i)] | length) |
    map(tostring) | join(" ")
  ' "$input_file" 2>/dev/null); then
    [ -n "$tmp_file" ] && rm -f "$tmp_file"
    echo "$result"
  else
    [ -n "$tmp_file" ] && rm -f "$tmp_file"
    # Fallback: return all zeros
    local zeros=""
    for ((i = 0; i < num_buckets; i++)); do
      zeros="${zeros}0 "
    done
    echo "${zeros% }"
  fi
}

# ─── CC (CLAUDE CODE) STATUS LINE ──────────────────────────────────────────

# Colors for CC section
CC_PRIMARY='\033[38;2;129;140;248m'     # Indigo
CC_SECONDARY='\033[38;2;165;180;252m'   # Light indigo
CC_BUCKET_EMPTY='\033[38;2;75;82;95m'

get_cc_bucket_color() {
  local pos=$1 max=$2
  local pct=$((pos * 100 / max))
  local r g b
  if [ "$pct" -le 33 ]; then
    r=$((74 + (250 - 74) * pct / 33))
    g=$((222 + (204 - 222) * pct / 33))
    b=$((128 + (21 - 128) * pct / 33))
  elif [ "$pct" -le 66 ]; then
    local t=$((pct - 33))
    r=$((250 + (251 - 250) * t / 33))
    g=$((204 + (146 - 204) * t / 33))
    b=$((21 + (60 - 21) * t / 33))
  else
    local t=$((pct - 66))
    r=$((251 + (239 - 251) * t / 34))
    g=$((146 + (68 - 146) * t / 34))
    b=$((60 + (68 - 60) * t / 34))
  fi
  printf '\033[38;2;%d;%d;%dm' "$r" "$g" "$b"
}

render_cc_context_bar() {
  local width=$1 pct=$2
  local output=""
  [ "$pct" -gt 100 ] && pct=100
  local filled=$((pct * width / 100))
  [ "$filled" -lt 0 ] && filled=0
  local i
  for ((i = 1; i <= width; i++)); do
    if [ "$i" -le "$filled" ]; then
      local color
      color=$(get_cc_bucket_color "$i" "$width")
      output="${output}${color}⛁${RESET}"
    else
      output="${output}${CC_BUCKET_EMPTY}⛁${RESET}"
    fi
  done
  echo -e "$output"
}

render_cc_status() {
  local pct="${cc_context_pct:-0}"
  pct="${pct%%.*}"
  [ -z "$pct" ] && pct=0

  # Context color
  local pct_color
  if [ "$pct" -ge 80 ]; then
    pct_color='\033[38;2;251;113;133m'   # Rose
  elif [ "$pct" -ge 60 ]; then
    pct_color='\033[38;2;251;146;60m'    # Orange
  elif [ "$pct" -ge 40 ]; then
    pct_color='\033[38;2;251;191;36m'    # Yellow
  else
    pct_color="${GREEN}"                  # Green
  fi

  # Format duration
  local dur_sec=$(( ${cc_duration_ms:-0} / 1000 ))
  local time_display
  if [ "$dur_sec" -ge 3600 ]; then
    time_display="$((dur_sec / 3600))h$((dur_sec % 3600 / 60))m"
  elif [ "$dur_sec" -ge 60 ]; then
    time_display="$((dur_sec / 60))m$((dur_sec % 60))s"
  else
    time_display="${dur_sec}s"
  fi

  # Format cost
  local cost_display
  cost_display=$(printf '$%.2f' "${cc_cost:-0}")

  case "$MODE" in
    nano)
      printf "${DIM}${cc_model:-?}${RESET} ${pct_color}${pct}%%${RESET} ${DIM}${cost_display}${RESET}\n"
      ;;
    micro)
      printf "${CC_PRIMARY}◉${RESET} ${pct_color}${pct}%%${RESET}"
      printf " ${DIM}${cc_model:-?}${RESET}"
      printf " ${DIM}${cost_display}${RESET}"
      printf " ${DIM}${time_display}${RESET}\n"
      ;;
    mini)
      local bar
      bar=$(render_cc_context_bar 20 "$pct")
      printf "${CC_PRIMARY}◉${RESET} ${CC_SECONDARY}CTX:${RESET} ${bar} ${pct_color}${pct}%%${RESET}"
      printf "  ${DIM}${cc_model:-?}${RESET}"
      printf "  ${DIM}${cost_display}${RESET}"
      printf "  ${DIM}${time_display}${RESET}\n"
      ;;
    normal)
      local bar
      bar=$(render_cc_context_bar 40 "$pct")
      printf "${CC_PRIMARY}◉${RESET} ${CC_SECONDARY}CTX:${RESET} ${bar} ${pct_color}${pct}%%${RESET}\n"
      printf "${CC_PRIMARY}▸${RESET} ${DIM}Model:${RESET} ${BOLD}${cc_model:-?}${RESET}"
      printf "  ${DIM}Cost:${RESET} ${cost_display}"
      printf "  ${DIM}Time:${RESET} ${time_display}"
      printf "  ${DIM}CC-Lines:${RESET} +${cc_lines_added:-0}/-${cc_lines_removed:-0}"
      [ -n "${cc_version}" ] && printf "  ${DIM}CC:${RESET} ${cc_version}"
      printf "\n"
      ;;
  esac
}

# ─── RENDER OUTPUT ──────────────────────────────────────────────────────────

render_output() {
  # ── CC status first ──
  render_cc_status

  local sc
  sc=$(qpt_color "${ACE_QPT:-0}")

  case "$MODE" in
    nano)
      printf "${ACE_PRIMARY_DIM}ACE:${RESET}${sc}${ACE_QPT:-0}${RESET}\n"
      ;;
    micro)
      printf "${ACE_PRIMARY_DIM}ACE:${RESET}${sc}${ACE_QPT:-0}${RESET}"
      printf " ${DIM}F:${RESET}${SESSION_FOCUS_PCT:-0}%%"
      printf " ${DIM}C:${RESET}${SESSION_CONFIDENCE_PCT:-0}%%\n"
      ;;
    mini)
      printf "${ACE_PRIMARY}◉${RESET} ${sc}${ACE_QPT:-0}${RESET}"
      printf "  ${DIM}F:${RESET}${SESSION_FOCUS_PCT:-0}%%"
      printf "  ${DIM}C:${RESET}${SESSION_CONFIDENCE_PCT:-0}%%"
      printf "  ${DIM}I:${RESET}${SESSION_INJ_PCT:-0}%%"
      printf "  ${ACE_PRIMARY}♦${RESET} ${PLAYBOOK_HEALTHY_PCT:-0}%%\n"
      ;;
    normal)
      local tc
      tc=$(terrain_color "${ACE_TERRAIN:-unknown}")
      local project_upper
      project_upper=$(echo "${ACE_PROJECT_NAME:-${dir_name:-project}}" | tr '[:lower:]' '[:upper:]')
      local org_display="${ACE_ORG_NAME:-}"

      # Header: org dimmed ▸ PROJECT bold
      if [ -n "$org_display" ]; then
        printf "${ACE_PRIMARY_DIM}── │${RESET} ${ACE_PRIMARY}ACE STATUSLINE${RESET} ${ACE_PRIMARY_DIM}│ ────${RESET} ${DIM}${org_display}${RESET} ${ACE_PRIMARY_DIM}▸${RESET} ${BOLD_CYAN}${project_upper}${RESET}\n"
      else
        printf "${ACE_PRIMARY_DIM}── │${RESET} ${ACE_PRIMARY}ACE STATUSLINE${RESET} ${ACE_PRIMARY_DIM}│ ────────────────────────${RESET} ${BOLD_CYAN}${project_upper}${RESET}\n"
      fi
      # Score line
      printf "${ACE_PRIMARY}◉ QPT:${RESET} ${sc}${ACE_QPT:-0}${RESET}"
      printf "  ${DIM}Focus:${RESET} ${SESSION_FOCUS_PCT:-0}%%"
      printf "  ${DIM}Conf:${RESET} ${SESSION_CONFIDENCE_PCT:-0}%%"
      printf "  ${DIM}Inj:${RESET} ${SESSION_INJ_PCT:-0}%%"
      printf "  ${DIM}Terrain:${RESET} ${tc}${ACE_TERRAIN:-unknown}${RESET}\n"
      # Separator
      printf "${ACE_PRIMARY_DIM}────────────────────────────────────────────────────────────────────${RESET}\n"
      # Playbook line
      printf "${ACE_PRIMARY}♦ PLAYBOOK:${RESET} ${PLAYBOOK_PATTERNS:-0} pts"
      printf "  ${DIM}Ratio:${RESET} ${PLAYBOOK_HEALTHY_PCT:-0}%% healthy"
      printf "  ${DIM}Domains:${RESET} ${PLAYBOOK_DOMAINS:-0}\n"
      # Usage bar (patterns consumption)
      if [ "${USAGE_PATTERNS_LIMIT:-0}" -gt 0 ] 2>/dev/null; then
        local usage_bar
        usage_bar=$(render_usage_bar 30 "${USAGE_PATTERNS_PCT:-0}")
        printf "${ACE_PRIMARY}▪ USAGE:${RESET}    ${usage_bar} ${DIM}${USAGE_PATTERNS_PCT:-0}%%${RESET}"
        printf " ${DIM}(${USAGE_PATTERNS_USED:-0}/${USAGE_PATTERNS_LIMIT:-0})${RESET}\n"
      fi
      # Separator
      printf "${ACE_PRIMARY_DIM}────────────────────────────────────────────────────────────────────${RESET}\n"
      # Sparkline header — show '-' instead of 0
      local c15m="${SPARK_COUNT_15M:-0}" c1h="${SPARK_COUNT_1H:-0}" c1d="${SPARK_COUNT_1D:-0}" c1w="${SPARK_COUNT_1W:-0}"
      [ "$c15m" -eq 0 ] 2>/dev/null && c15m="-"
      [ "$c1h" -eq 0 ] 2>/dev/null && c1h="-"
      [ "$c1d" -eq 0 ] 2>/dev/null && c1d="-"
      [ "$c1w" -eq 0 ] 2>/dev/null && c1w="-"
      printf "${ACE_PRIMARY}✿ LEARNING:${RESET}"
      printf "  ${DIM}15m:${RESET} ${c15m}"
      printf " ${DIM}│${RESET} ${DIM}60m:${RESET} ${c1h}"
      printf " ${DIM}│${RESET} ${DIM}1d:${RESET} ${c1d}"
      printf " ${DIM}│${RESET} ${DIM}1w:${RESET} ${c1w}\n"
      # Sparkline rows — tree-style prefixes, aligned labels
      printf "${ACE_PRIMARY_DIM}├─ 15m:${RESET} ${SPARKLINE_15M:-}\n"
      printf "${ACE_PRIMARY_DIM}├─ 60m:${RESET} ${SPARKLINE_1H:-}\n"
      printf "${ACE_PRIMARY_DIM}├── 1d:${RESET} ${SPARKLINE_1D:-}\n"
      printf "${ACE_PRIMARY_DIM}└── 1w:${RESET} ${SPARKLINE_1W:-}\n"
      ;;
  esac
}

# ─── TERMINAL WIDTH & MODE ──────────────────────────────────────────────────

detect_terminal_width() {
  local width=""

  # Tier 1: Kitty IPC
  if [ -n "${KITTY_WINDOW_ID:-}" ] && command -v kitten >/dev/null 2>&1; then
    width=$(kitten @ ls 2>/dev/null | jq -r --argjson wid "$KITTY_WINDOW_ID" \
      '.[].tabs[].windows[] | select(.id == $wid) | .columns' 2>/dev/null)
  fi

  # Tier 2: stty
  if [ -z "$width" ] || [ "$width" = "0" ] || [ "$width" = "null" ]; then
    width=$(stty size </dev/tty 2>/dev/null | awk '{print $2}')
  fi

  # Tier 3: tput
  if [ -z "$width" ] || [ "$width" = "0" ]; then
    width=$(tput cols 2>/dev/null)
  fi

  # Tier 4: fallback
  if [ -z "$width" ] || [ "$width" = "0" ]; then
    width=${COLUMNS:-80}
  fi

  echo "$width"
}

# ─── MAIN EXECUTION ─────────────────────────────────────────────────────────

if [ "${_SOURCE_ONLY:-}" != "true" ]; then
  # ─── PARSE INPUT ───────────────────────────────────────────────────────────

  input=$(cat)

  eval "$(echo "$input" | jq -r '
    "session_id=" + (.session_id // "" | @sh) + "\n" +
    "current_dir=" + (.workspace.current_dir // .cwd // "." | @sh) + "\n" +
    "cc_model=" + (.model.display_name // "unknown" | @sh) + "\n" +
    "cc_version=" + (.version // "" | @sh) + "\n" +
    "cc_context_pct=" + (.context_window.used_percentage // 0 | tostring) + "\n" +
    "cc_context_size=" + (.context_window.context_window_size // 200000 | tostring) + "\n" +
    "cc_cost=" + (.cost.total_cost_usd // 0 | tostring) + "\n" +
    "cc_duration_ms=" + (.cost.total_duration_ms // 0 | tostring) + "\n" +
    "cc_lines_added=" + (.cost.total_lines_added // 0 | tostring) + "\n" +
    "cc_lines_removed=" + (.cost.total_lines_removed // 0 | tostring)
  ' 2>/dev/null)" || true

  session_id="${session_id:-}"
  current_dir="${current_dir:-.}"
  dir_name=$(basename "$current_dir" 2>/dev/null || echo ".")

  # If no session_id, minimal output
  if [ -z "$session_id" ]; then
    printf "${DIM}ACE: awaiting session${RESET}\n"
    exit 0
  fi

  # ─── TERMINAL WIDTH & MODE ────────────────────────────────────────────────

  term_width=$(detect_terminal_width)

  if [ "$term_width" -lt 40 ]; then
    MODE="nano"
  elif [ "$term_width" -lt 60 ]; then
    MODE="micro"
  elif [ "$term_width" -lt 100 ]; then
    MODE="mini"
  else
    MODE="normal"
  fi

  # Resolve ACE_RELEVANCE relative to project root
  if [[ "$ACE_RELEVANCE" != /* ]]; then
    ACE_RELEVANCE="${current_dir}/${ACE_RELEVANCE}"
  fi

  if [ ! -f "$ACE_RELEVANCE" ]; then
    printf "${DIM}ACE: no data${RESET}\n"
    exit 0
  fi

  # ─── GATHER DATA ───────────────────────────────────────────────────────────

  aggregate_session "$session_id" "$ACE_RELEVANCE"
  fetch_playbook_data
  compute_qpt
  compute_terrain

  # Normalize all display metrics to percentage format for visual consistency
  SESSION_CONFIDENCE_PCT=$(jq -n "${SESSION_CONFIDENCE:-0} * 100 | round")
  if [ "${SESSION_LEARN_TOTAL:-0}" -gt 0 ]; then
    SESSION_LEARN_PCT=$(jq -n "(${SESSION_LEARN_SENT} / ${SESSION_LEARN_TOTAL} * 100) | round")
  else
    SESSION_LEARN_PCT=0
  fi
  if [ "${SESSION_INJ_TOTAL:-0}" -gt 0 ]; then
    SESSION_INJ_PCT=$(jq -n "(${SESSION_INJ_USED} / ${SESSION_INJ_TOTAL} * 100) | round")
  else
    SESSION_INJ_PCT=0
  fi

  # ─── BUILD SPARKLINES (mini & normal only) ────────────────────────────────

  SPARKLINE_15M=""
  SPARKLINE_1H=""
  SPARKLINE_1D=""
  SPARKLINE_1W=""
  SPARK_COUNT_15M=0
  SPARK_COUNT_1H=0
  SPARK_COUNT_1D=0
  SPARK_COUNT_1W=0

  if [ "$MODE" = "normal" ] || [ "$MODE" = "mini" ]; then
    buckets_15m=$(bucket_events "$ACE_RELEVANCE" 15 60)
    buckets_1h=$(bucket_events "$ACE_RELEVANCE" 12 300)
    buckets_1d=$(bucket_events "$ACE_RELEVANCE" 24 3600)
    buckets_1w=$(bucket_events "$ACE_RELEVANCE" 7 86400)

    SPARKLINE_15M=$(render_sparkline "$buckets_15m")
    SPARKLINE_1H=$(render_sparkline "$buckets_1h")
    SPARKLINE_1D=$(render_sparkline "$buckets_1d")
    SPARKLINE_1W=$(render_sparkline "$buckets_1w")

    # Count total events per window
    SPARK_COUNT_15M=$(echo "$buckets_15m" | tr ' ' '\n' | awk '{s+=$1} END{print s+0}')
    SPARK_COUNT_1H=$(echo "$buckets_1h" | tr ' ' '\n' | awk '{s+=$1} END{print s+0}')
    SPARK_COUNT_1D=$(echo "$buckets_1d" | tr ' ' '\n' | awk '{s+=$1} END{print s+0}')
    SPARK_COUNT_1W=$(echo "$buckets_1w" | tr ' ' '\n' | awk '{s+=$1} END{print s+0}')
  fi

  # ─── RENDER ──────────────────────────────────────────────────────────────

  render_output
fi
