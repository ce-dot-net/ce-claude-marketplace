---
description: Generate LLM-evaluated HTML insights report — per-task helpfulness with reasoning
argument-hint: "[--hours N]"
---

# ACE Insights

Generate a shareable interactive HTML report where Claude evaluates how helpful ACE patterns were for each task.

## Instructions for Claude

When the user runs `/ace:ace-insights`, follow these three steps sequentially.

### Step 1: Extract Task Data

Run this bash script to extract structured per-task data as JSON:

```bash
#!/usr/bin/env bash
set -euo pipefail

HOURS="${1:-24}"
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
ANALYZER=""
for candidate in \
  "plugins/ace/shared-hooks/utils/ace_insights_analyzer.py" \
  "${HOME}/.claude/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py" \
  "$(git rev-parse --show-toplevel 2>/dev/null)/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py"; do
  if [ -f "$candidate" ]; then
    ANALYZER="$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")"
    break
  fi
done

if [ -z "$ANALYZER" ]; then
  echo "ACE insights analyzer not found. Re-install the ACE plugin."
  exit 1
fi

# Extract task data as JSON
python3 -c "
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path('${ANALYZER}').parent))
from ace_insights_analyzer import extract_task_data_for_evaluation

entries = []
log_path = Path('${LOG_FILE}')
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
task_data = extract_task_data_for_evaluation(entries, hours=hours)
print(json.dumps(task_data, indent=2))
"
```

### Step 2: Evaluate Helpfulness

Read the JSON output from Step 1. **You are the LLM — evaluate each task's ACE helpfulness.**

For each task in the `tasks` array, assess:
- **Was ACE helpful?** Look at the `user_prompt` and the `pattern_details` (domain, section, confidence). Were the injected patterns relevant to what the user was trying to do?
- **Helpfulness percentage (0-100)**: How much did ACE likely help this task? Consider:
  - Domain match: Do the pattern domains relate to the user's request?
  - Confidence: Higher server confidence = better semantic match
  - Pattern count: More relevant patterns = more guidance available
  - 0% = patterns were completely irrelevant to the task
  - 50% = some patterns were marginally relevant
  - 80%+ = patterns directly matched the task domain and provided clear value
- **Reasoning**: One sentence explaining your judgment

For tasks with `searches: 0` (no ACE involvement), score 0% with reasoning "No ACE patterns were searched or injected for this task."

Produce your evaluation as a JSON object with this exact structure:
```json
{
  "evaluations": [
    {
      "task_id": 1,
      "helpfulness_pct": 85,
      "reasoning": "Auth strategy patterns directly matched the authentication bug fix task."
    }
  ],
  "overall_helpfulness_pct": 72,
  "overall_summary": "ACE provided relevant patterns for 7 of 10 tasks. Auth and testing patterns were consistently well-matched."
}
```

### Step 3: Generate HTML Report

Using your evaluation JSON from Step 2 and the task data JSON from Step 1, run this bash script. Replace `EVALUATION_JSON` with your actual evaluation JSON (properly escaped for Python):

```bash
#!/usr/bin/env bash
set -euo pipefail

HOURS="${1:-24}"
LOG_FILE=".claude/data/logs/ace-relevance.jsonl"

# Find the analyzer module
ANALYZER=""
for candidate in \
  "plugins/ace/shared-hooks/utils/ace_insights_analyzer.py" \
  "${HOME}/.claude/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py" \
  "$(git rev-parse --show-toplevel 2>/dev/null)/plugins/ace/shared-hooks/utils/ace_insights_analyzer.py"; do
  if [ -f "$candidate" ]; then
    ANALYZER="$(cd "$(dirname "$candidate")" && pwd)/$(basename "$candidate")"
    break
  fi
done

REPORT_DIR="${HOME}/.claude/usage-data"
mkdir -p "$REPORT_DIR"
REPORT_FILE="${REPORT_DIR}/ace-insights.html"

python3 -c "
import json, sys
from pathlib import Path

sys.path.insert(0, str(Path('${ANALYZER}').parent))
from ace_insights_analyzer import extract_task_data_for_evaluation, generate_evaluated_html

# Re-extract task data
entries = []
log_path = Path('${LOG_FILE}')
for line in log_path.read_text().splitlines():
    line = line.strip()
    if line:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

hours = int('${HOURS}')
task_data = extract_task_data_for_evaluation(entries, hours=hours)

# Claude's evaluation (injected by the LLM)
evaluations = json.loads('''EVALUATION_JSON''')

# Generate HTML with evaluations baked in
html = generate_evaluated_html(task_data, evaluations, hours=hours)
report_path = Path('${REPORT_FILE}')
report_path.write_text(html)

print(f'Tasks analyzed: {len(task_data.get(\"tasks\", []))}')
print(f'Overall ACE helpfulness: {evaluations.get(\"overall_helpfulness_pct\", \"N/A\")}%')
print(f'Summary: {evaluations.get(\"overall_summary\", \"\")}')
print(f'Report saved to: ${REPORT_FILE}')
"

echo ""
echo "Your LLM-evaluated insights report is ready:"
echo "  file://${REPORT_FILE}"

# Auto-open in browser on macOS
if command -v open &>/dev/null; then
  open "${REPORT_FILE}"
fi
```

**Important**: In Step 3, replace the literal string `EVALUATION_JSON` with your actual JSON evaluation from Step 2. Ensure the JSON is valid and properly escaped (no unescaped single quotes inside the JSON string).

After the script completes, summarize the key findings for the user: overall helpfulness %, which tasks ACE helped most/least, and any patterns that stood out.

## What You'll See

**LLM-Evaluated HTML Report** (saved to `~/.claude/usage-data/ace-insights.html`):
- Per-task helpfulness scores with colored gauges (green/yellow/red)
- Claude's reasoning for each task's helpfulness score
- Overall ACE helpfulness percentage
- Top patterns bar chart
- All evaluations baked into a self-contained, shareable HTML file

**Terminal Summary** (printed inline):
- Overall helpfulness percentage
- Task count and key findings

## Usage

```
# Last 24 hours (default)
/ace:ace-insights

# Last 1 hour
/ace:ace-insights --hours 1

# Last 7 days
/ace:ace-insights --hours 168
```

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-doctor` - Run diagnostics
- `/ace:ace-patterns` - View learned patterns
