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
python3 -c "
import json, sys, os
from pathlib import Path

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
log_path = Path('.claude/data/logs/ace-relevance.jsonl')

if not log_path.exists():
    print('No relevance metrics found yet.')
    print('')
    print('Metrics will be recorded after:')
    print('  1. Pattern searches (UserPromptSubmit hook)')
    print('  2. Domain shifts (PreToolUse hook)')
    print('  3. Task completions (Stop hook)')
    print('')
    print('Try running a few tasks with ACE enabled first!')
    sys.exit(0)

analyzer_path = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', '')) / 'shared-hooks' / 'utils' / 'ace_insights_analyzer.py'
if not analyzer_path.exists():
    print('ACE insights analyzer not found. Re-install the ACE plugin.')
    sys.exit(1)

sys.path.insert(0, str(analyzer_path.parent))
from ace_insights_analyzer import extract_task_data_for_evaluation

entries = []
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

task_data = extract_task_data_for_evaluation(entries, hours=hours)
print(json.dumps(task_data, indent=2))
" ${1:-24}
```

**IMPORTANT**: Do NOT run additional bash commands to read or inspect the JSON output.
Evaluate the task data directly from the output above.

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
python3 -c "
import json, sys, os, subprocess, platform
from pathlib import Path

hours = int(sys.argv[1]) if len(sys.argv) > 1 else 24
log_path = Path('.claude/data/logs/ace-relevance.jsonl')

analyzer_path = Path(os.environ.get('CLAUDE_PLUGIN_ROOT', '')) / 'shared-hooks' / 'utils' / 'ace_insights_analyzer.py'
if not analyzer_path.exists():
    print('ACE insights analyzer not found. Re-install the ACE plugin.')
    sys.exit(1)

report_dir = Path.home() / '.claude' / 'usage-data'
report_dir.mkdir(parents=True, exist_ok=True)
report_file = report_dir / 'ace-insights.html'

sys.path.insert(0, str(analyzer_path.parent))
from ace_insights_analyzer import extract_task_data_for_evaluation, generate_evaluated_html

entries = []
for line in log_path.read_text().splitlines():
    line = line.strip()
    if line:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue

task_data = extract_task_data_for_evaluation(entries, hours=hours)
evaluations = json.loads('''EVALUATION_JSON''')
html = generate_evaluated_html(task_data, evaluations, hours=hours)
report_file.write_text(html)

print(f'Tasks analyzed: {len(task_data.get(\"tasks\", []))}')
print(f'Overall ACE helpfulness: {evaluations.get(\"overall_helpfulness_pct\", \"N/A\")}%')
print(f'Summary: {evaluations.get(\"overall_summary\", \"\")}')
print(f'Report saved to: {report_file}')
print('')
print('Your LLM-evaluated insights report is ready:')
print(f'  file://{report_file}')

if platform.system() == 'Darwin':
    subprocess.run(['open', str(report_file)], check=False)
" ${1:-24}
```

**IMPORTANT**: In Step 3, replace the literal string `EVALUATION_JSON` with your actual JSON evaluation from Step 2. Ensure the JSON is valid and properly escaped (no unescaped single quotes inside the JSON string). Do NOT run any additional bash commands beyond Steps 1 and 3.

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
