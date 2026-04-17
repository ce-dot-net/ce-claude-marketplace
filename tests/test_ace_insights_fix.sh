#!/usr/bin/env bash
# Verifies the v6.4.4 ace-insights fixes:
#   Fix 1: CLAUDE_PLUGIN_ROOT fallback -> analyzer resolves without env var
#   Fix 2: diagnostic empty-state when log has searches but no executions
#   Fix 3a: per-task agent badge rendered
#   Fix 3b: "By Agent" rollup table rendered when subagents present
#
# Runs against the INSTALLED CACHE copy so a plugin reload isn't required
# for the test itself — only for `/ace:ace-insights` end-to-end.

set -u
TMPDIR_ROOT="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_ROOT"' EXIT

PASS=0
FAIL=0

say_ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
say_fail() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }
section()  { printf '\n\033[1m%s\033[0m\n' "$1"; }

ANALYZER="$HOME/.claude/plugins/cache/ce-dot-net-marketplace/ace/6.4.3/shared-hooks/utils/ace_insights_analyzer.py"
[ -f "$ANALYZER" ] || { echo "Cache analyzer missing: $ANALYZER"; exit 2; }

# -----------------------------------------------------------------------
section "1. Plugin-root fallback (Fix 1)"
# -----------------------------------------------------------------------
# Simulate the exact code path used by ace-insights.md with empty env var.
unset CLAUDE_PLUGIN_ROOT
OUT="$(python3 - <<'PY'
import os, sys, glob
from pathlib import Path

def resolve():
    root = os.environ.get('CLAUDE_PLUGIN_ROOT', '')
    if root:
        cand = Path(root) / 'shared-hooks' / 'utils' / 'ace_insights_analyzer.py'
        if cand.exists():
            return cand
    home = Path.home()
    patterns = [
        str(home / '.claude/plugins/cache/*/ace/*/shared-hooks/utils/ace_insights_analyzer.py'),
        str(home / '.claude/plugins/marketplaces/*/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py'),
    ]
    m = []
    for pat in patterns:
        m.extend(glob.glob(pat))
    if not m:
        return None
    m.sort(key=os.path.getmtime, reverse=True)
    return Path(m[0])

p = resolve()
print(p if p else "NONE")
PY
)"
if [ -n "$OUT" ] && [ "$OUT" != "NONE" ] && [ -f "$OUT" ]; then
    say_ok "resolver finds analyzer without CLAUDE_PLUGIN_ROOT ($OUT)"
else
    say_fail "resolver returned: $OUT"
fi

# -----------------------------------------------------------------------
section "2. Empty-log diagnostic (Fix 2)"
# -----------------------------------------------------------------------
# Case A: zero entries -> "No relevance metrics logged yet"
HTML_A="$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$ANALYZER")')
from ace_insights_analyzer import generate_evaluated_html
html = generate_evaluated_html(
    {'tasks': [], 'metadata': {'total_entries': 0}, 'top_patterns': [], 'search_only_count': 0},
    {'evaluations': [], 'overall_helpfulness_pct': 0, 'overall_summary': ''},
)
print(html)
")"
echo "$HTML_A" | grep -q "No relevance metrics logged yet" \
    && say_ok "empty-log case renders 'No relevance metrics logged yet'" \
    || say_fail "empty-log case missing expected message"

# Case B: searches logged but no executions -> diagnostic with Stop-hook hint
HTML_B="$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$ANALYZER")')
from ace_insights_analyzer import generate_evaluated_html
html = generate_evaluated_html(
    {'tasks': [], 'metadata': {'total_entries': 7}, 'top_patterns': [], 'search_only_count': 3},
    {'evaluations': [], 'overall_helpfulness_pct': 0, 'overall_summary': ''},
)
print(html)
")"
echo "$HTML_B" | grep -q "7 log entries found" \
    && echo "$HTML_B" | grep -q "3 search-only clusters" \
    && echo "$HTML_B" | grep -q "Stop hook" \
    && say_ok "search-only case renders Stop-hook diagnostic" \
    || say_fail "search-only diagnostic missing expected phrases"

# -----------------------------------------------------------------------
section "3. Per-agent rendering (Fix 3a + 3b)"
# -----------------------------------------------------------------------
HTML_C="$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$ANALYZER")')
from ace_insights_analyzer import generate_evaluated_html
task_data = {
    'metadata': {'total_entries': 10},
    'search_only_count': 0,
    'top_patterns': [],
    'tasks': [
        {'task_id': 1, 'user_prompt': 'fix bug', 'start_time': '2026-04-17T08:00:00Z',
         'duration_seconds': 30, 'agent_type': 'main', 'patterns_injected': 5,
         'patterns_used': 3, 'pattern_ids': [], 'pattern_names': {}, 'domains': ['a'],
         'tools_executed': 8, 'success': True, 'avg_confidence': 0.8,
         'searches': 1, 'executions': 1, 'pattern_details': []},
        {'task_id': 2, 'user_prompt': 'explore repo', 'start_time': '2026-04-17T08:05:00Z',
         'duration_seconds': 15, 'agent_type': 'Explore', 'patterns_injected': 3,
         'patterns_used': 2, 'pattern_ids': [], 'pattern_names': {}, 'domains': ['b'],
         'tools_executed': 5, 'success': True, 'avg_confidence': 0.9,
         'searches': 1, 'executions': 1, 'pattern_details': []},
        {'task_id': 3, 'user_prompt': 'review code', 'start_time': '2026-04-17T08:10:00Z',
         'duration_seconds': 20, 'agent_type': 'code-reviewer', 'patterns_injected': 2,
         'patterns_used': 1, 'pattern_ids': [], 'pattern_names': {}, 'domains': ['c'],
         'tools_executed': 3, 'success': True, 'avg_confidence': 0.5,
         'searches': 1, 'executions': 1, 'pattern_details': []},
    ],
}
evals = {'evaluations': [
    {'task_id': 1, 'helpfulness_pct': 80, 'reasoning': 'good'},
    {'task_id': 2, 'helpfulness_pct': 90, 'reasoning': 'very good'},
    {'task_id': 3, 'helpfulness_pct': 30, 'reasoning': 'mismatched'},
], 'overall_helpfulness_pct': 67, 'overall_summary': 'mixed'}
print(generate_evaluated_html(task_data, evals))
")"

echo "$HTML_C" | grep -q '<h2>By Agent</h2>' \
    && say_ok "3b: 'By Agent' section rendered when subagents present" \
    || say_fail "3b: 'By Agent' section missing"

echo "$HTML_C" | grep -q 'class="agent-badge agent-main">main<' \
    && say_ok "3a: main agent badge rendered on task card" \
    || say_fail "3a: main agent badge missing"

echo "$HTML_C" | grep -q '>Explore<' \
    && say_ok "3a: Explore agent badge rendered" \
    || say_fail "3a: Explore badge missing"

echo "$HTML_C" | grep -q '>code-reviewer<' \
    && say_ok "3a: code-reviewer badge rendered" \
    || say_fail "3a: code-reviewer badge missing"

# code-reviewer scored 30% -> should get a warning marker
echo "$HTML_C" | grep -q 'class="warn">⚠' \
    && say_ok "3b: low-helpfulness agent flagged with warning" \
    || say_fail "3b: warning marker missing for <50% agent"

# -----------------------------------------------------------------------
section "4. Main-only case (no 'By Agent' table)"
# -----------------------------------------------------------------------
# When only main agent ran, the per-agent table should be suppressed
# (otherwise it's just noise).
HTML_D="$(python3 -c "
import sys
sys.path.insert(0, '$(dirname "$ANALYZER")')
from ace_insights_analyzer import generate_evaluated_html
task_data = {
    'metadata': {'total_entries': 2},
    'search_only_count': 0,
    'top_patterns': [],
    'tasks': [
        {'task_id': 1, 'user_prompt': 'fix bug', 'start_time': '2026-04-17T08:00:00Z',
         'duration_seconds': 30, 'agent_type': 'main', 'patterns_injected': 5,
         'patterns_used': 3, 'pattern_ids': [], 'pattern_names': {}, 'domains': [],
         'tools_executed': 8, 'success': True, 'avg_confidence': 0.8,
         'searches': 1, 'executions': 1, 'pattern_details': []},
    ],
}
print(generate_evaluated_html(task_data, {'evaluations': [], 'overall_helpfulness_pct': 0, 'overall_summary': ''}))
")"
echo "$HTML_D" | grep -q '<h2>By Agent</h2>' \
    && say_fail "main-only case should NOT render 'By Agent' table" \
    || say_ok "main-only case suppresses 'By Agent' table"

# -----------------------------------------------------------------------
printf '\n\033[1mResults: %d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
