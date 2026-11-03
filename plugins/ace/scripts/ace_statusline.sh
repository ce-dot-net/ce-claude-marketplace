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

# ── ONE python3 call parses CC stdin JSON + relevance log + review file ──
# (v8: replaces 13 jq spawns + a second python3; CC debounces statusline at 300 ms.)
# Python prints shlex-quoted VAR=value lines; bash evals them. Missing python3 => defaults.
cwd=""; used_pct=0; model_name=""; effort_level=""; thinking_enabled=false; git_worktree=""
rl_5h_pct=""; rl_5h_resets=""; rl_7d_pct=""; rl_7d_resets=""; rl_sp_pct=""; used_n=""; used_m=""; ctx_state=""
patterns_injected=0; domains_count=0; domain_shifts=0; quality_pct=0; time_saved=""
INPUT_JSON=$(cat 2>/dev/null || echo "{}")
PYOUT=$(python3 -c '
import json, os, shlex, sys
def num(v):  # floor (0.4 -> 0, 99.6 -> 99); absent -> "" (a missing window is hidden, never 0%)
    try: return str(max(0, int(float(v))))
    except Exception: return ""
def get(d, *ks):
    for k in ks:
        d = d.get(k) if isinstance(d, dict) else None
    return d
try: j = json.loads(sys.stdin.read() or "{}")
except Exception: j = {}
if not isinstance(j, dict): j = {}
out = {
 "cwd": get(j, "cwd") or "", "used_pct": num(get(j, "context_window", "used_percentage")) or "0",
 "model_name": get(j, "model", "display_name") or "", "effort_level": get(j, "effort", "level") or "",
 "thinking_enabled": "true" if get(j, "thinking", "enabled") is True else "false",
 "git_worktree": get(j, "workspace", "git_worktree") or "",
 "rl_5h_pct": num(get(j, "rate_limits", "five_hour", "used_percentage")),
 "rl_5h_resets": get(j, "rate_limits", "five_hour", "resets_at") or "",
 "rl_7d_pct": num(get(j, "rate_limits", "seven_day", "used_percentage")),
 "rl_7d_resets": get(j, "rate_limits", "seven_day", "resets_at") or "",
 "rl_sp_pct": num(get(j, "rate_limits", "spend_limit", "used_percentage")),
 "used_n": "", "used_m": "", "ctx_state": "",
}
def _log_root(cwd):  # 8.1.0: the plugin core keys logs to the repo root (worktrees + subfolders share one log)
    try:
        ip = json.load(open(os.path.expanduser("~/.claude/plugins/installed_plugins.json")))["plugins"]
        p = [v[0]["installPath"] for k, v in ip.items() if k.startswith("ace@")][0]
        sys.path.insert(0, os.path.join(p, "shared-hooks", "utils"))
        import ace_project_context
        return ace_project_context.log_root(cwd)
    except Exception:
        return cwd
logs = os.path.join(_log_root(out["cwd"]), ".claude", "data", "logs") if out["cwd"] else ""
# Task boundary: events of this session since its last "execution" event (Stop hook writes these)
try:
    events = []
    # bounded tail read (last 2MB) so refresh cost stays flat as the log grows
    with open(os.path.join(logs, "ace-relevance.jsonl"), "rb") as f:
        f.seek(0, 2); size = f.tell(); start = max(0, size - 2097152); f.seek(start)
        lines = f.read().decode("utf-8", "replace").splitlines()
        if start: lines = lines[1:]  # first line may be partial
        for line in lines:
            try: events.append(json.loads(line))
            except Exception: pass
    sid = j.get("session_id")
    # this session only (rows of a parallel session, its execution rows too, would leak in); no session_id -> all
    events = [e for e in events if isinstance(e, dict) and (not sid or e.get("session_id") == sid)]
    main = lambda e: (e.get("agent_type") or "main") == "main"
    # Task boundary (8.1.0): the newest MAIN prompt search (hook UserPromptSubmit; no SubagentStart, no cache hit;
    # machine prompts never log a search). Its patterns and the domain shifts since are the current task.
    ups = [i for i, e in enumerate(events) if e.get("event") == "search" and e.get("hook") == "UserPromptSubmit"
           and main(e) and e.get("engine") != "cache"]
    cur = events[ups[-1]:] if ups else []
    s = cur[:1]
    out["patterns_injected"] = sum(e.get("patterns_injected", 0) for e in s)
    out["domains_count"] = len(set(d for e in s for d in e.get("domains", [])))  # domains of the INJECTED patterns
    out["domain_shifts"] = len([e for e in cur if e.get("event") == "domain_shift"])
    # evidenced use of the last finished main task: used N/M (never prior confidence as "relevance")
    ex = [e for e in events if e.get("event") == "execution" and main(e) and e.get("patterns_used_count")]
    if ex:
        out["used_n"], out["used_m"] = ex[-1].get("used_ids_count") or 0, ex[-1].get("patterns_used_count")
    ctx = [e for e in events if e.get("event") == "context"]
    if ctx:
        out["ctx_state"] = ctx[-1].get("state") or ""
except Exception: pass
# Self-eval review result (no fake helpfulness). jq-equivalent: .quality_pct // .helpful_pct // 0
try:
    with open(os.path.join(logs, "ace-review-result.json")) as f: r = json.load(f)
    q = r.get("quality_pct"); out["quality_pct"] = (q if q is not None else r.get("helpful_pct")) or 0
    out["time_saved"] = r.get("time_saved") or ""
except Exception: pass
for k, v in out.items(): print("%s=%s" % (k, shlex.quote(str(v))))
' <<<"$INPUT_JSON" 2>/dev/null || true)
eval "$PYOUT"
used_pct=${used_pct:-0}

# ── Format Unix epoch resets_at to human-readable local time ──
# Cross-platform: date -r (BSD/macOS) with GNU/Linux fallback (--date=@); pure-integer guard.
fmt_reset() {
  local ts="$1"
  [ -z "$ts" ] || [ "$ts" = "null" ] && { echo ""; return; }
  case "$ts" in
    *[!0-9]*) echo "$ts"; return;;   # not a pure integer (e.g. already ISO) → show as-is
  esac
  date -r "$ts" '+%a %H:%M' 2>/dev/null || date --date="@$ts" '+%a %H:%M' 2>/dev/null || echo "$ts"
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

# Evidenced use of the last finished main task
if [ -n "$used_m" ]; then
  LINE2+=" ${D}used${R} ${B}${used_n}/${used_m}${R}"
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

# 8.1.0: a problem state of this session's binding replaces the stats line (the mod's ▼, for standalone use)
if [ -n "$ctx_state" ] && [ "$ctx_state" != "ok" ]; then
  LINE2="${RED}${B}ACE ▼${R} ${D}${ctx_state}${R}"
fi

# Rate limits: each window only when the payload has it (absent != 0%), each colored by its own value.
rl_color() { if [ "$1" -ge 80 ] 2>/dev/null; then printf '%s' "$RED"; elif [ "$1" -ge 50 ] 2>/dev/null; then printf '%s' "$YEL"; else printf '%s' "$GRN"; fi; }
LINE3=""
if [ -n "$rl_5h_pct" ]; then
  LINE3+="5h:$(rl_color "$rl_5h_pct")${B}${rl_5h_pct}%${R}"
  [ -n "$rl_5h_resets" ] && [ "$rl_5h_resets" != "null" ] && LINE3+="${D} →${rl_5h_resets}${R}"
fi
if [ -n "$rl_7d_pct" ]; then
  [ -n "$LINE3" ] && LINE3+="  "
  LINE3+="7d:$(rl_color "$rl_7d_pct")${B}${rl_7d_pct}%${R}"
  [ -n "$rl_7d_resets" ] && [ "$rl_7d_resets" != "null" ] && LINE3+="${D} →${rl_7d_resets}${R}"
fi
if [ -n "$rl_sp_pct" ]; then
  [ -n "$LINE3" ] && LINE3+="  "
  LINE3+="spend:$(rl_color "$rl_sp_pct")${B}${rl_sp_pct}%${R}"
fi
[ -n "$LINE3" ] && LINE3="${D}limits${R} ${LINE3}"

echo -e "$LINE1"
echo -e "$LINE2"
if [ -n "$LINE3" ]; then
  echo -e "$LINE3"
fi
exit 0
