---
description: Generate interactive HTML insights report - per-session helpfulness, trends, top patterns
argument-hint: "[--hours N]"
---

# ACE Insights

Generate a shareable interactive HTML report analyzing how helpful ACE patterns were across your Claude sessions.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Parse arguments
HOURS="${1:-24}"

# Log file location
LOG_FILE=".claude/data/logs/ace-relevance.jsonl"

if [ ! -f "$LOG_FILE" ]; then
  echo "No relevance metrics found yet."
  echo ""
  echo "Metrics will be recorded after:"
  echo "  1. Pattern searches (UserPromptSubmit hook)"
  echo "  2. Domain shifts (PreToolUse hook)"
  echo "  3. Task completions (Stop hook)"
  echo ""
  echo "Try running a few tasks with ACE enabled first!"
  exit 0
fi

# Find the analyzer module
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ANALYZER=""
for candidate in \
  "${SCRIPT_DIR}/../shared-hooks/utils/ace_insights_analyzer.py" \
  "plugins/ace/shared-hooks/utils/ace_insights_analyzer.py" \
  "${HOME}/.claude/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py"; do
  if [ -f "$candidate" ]; then
    ANALYZER="$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")"
    break
  fi
done

if [ -z "$ANALYZER" ]; then
  echo "ACE insights analyzer not found. Re-install the ACE plugin."
  exit 1
fi

# Output location (same pattern as Claude Code's /insights)
REPORT_DIR="${HOME}/.claude/usage-data"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/ace-insights.html"

# Run Python analyzer and generate HTML report
python3 -c "
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path('${ANALYZER}').parent))

from ace_insights_analyzer import (
    analyze_sessions, calculate_helpfulness,
    get_top_patterns, calculate_trends,
    format_insights_report, format_insights_html
)

# Read JSONL entries
entries = []
log_path = Path('${LOG_FILE}')
if log_path.exists():
    for line in log_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

if not entries:
    print('No valid log entries found.')
    sys.exit(0)

hours = int('${HOURS}')

# Run all analyses
sessions = analyze_sessions(entries, hours=hours)
helpfulness = calculate_helpfulness(entries)
top_patterns = get_top_patterns(entries, limit=10)
trends = calculate_trends(entries, current_hours=hours, previous_hours=hours)

# Generate HTML report
html = format_insights_html(sessions, helpfulness, top_patterns, trends, hours=hours)
report_path = Path('${REPORT_FILE}')
report_path.write_text(html)

# Print text summary to terminal
report = format_insights_report(sessions, helpfulness, top_patterns, trends)
print(report)
print(f'Log file: ${LOG_FILE}')
total = sum(1 for l in log_path.read_text().splitlines() if l.strip())
print(f'Total entries: {total}')
print(f'Time window: Last {hours} hours')
"

echo ""
echo "Your shareable insights report is ready:"
echo "  file://${REPORT_FILE}"
```

## What You'll See

**Interactive HTML Report** (saved to `~/.claude/usage-data/ace-insights.html`):
- Per-session breakdown with status, duration, patterns used
- Pattern helpfulness advantage card (success with vs without patterns)
- Top patterns bar chart
- Trend comparison cards with up/down indicators

**Terminal Summary** (printed inline):
- Quick text overview of all metrics

## Usage

```bash
# Last 24 hours (default)
/ace:ace-insights

# Last 1 hour
/ace:ace-insights --hours 1

# Last 7 days
/ace:ace-insights --hours 168
```

## Interpreting Results

**High pattern advantage (>20pp)**:
- ACE patterns are significantly improving task success
- Keep learning and growing the playbook

**Low/negative pattern advantage**:
- Patterns may not be relevant to current tasks
- Consider running `/ace:ace-bootstrap` to refresh

**No active sessions**:
- Sessions without task execution don't count as "active"
- Check if Stop hook is firing (run `/ace:ace-doctor`)

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-doctor` - Run diagnostics
- `/ace:ace-patterns` - View learned patterns
