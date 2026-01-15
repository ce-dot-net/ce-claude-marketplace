---
description: Analyze ACE pattern relevance metrics from hook logs
argument-hint: "[--hours N]"
---

# ACE Relevance Report

Analyze pattern relevance metrics to understand how well injected patterns match actual tasks.

```bash
#!/usr/bin/env bash
set -euo pipefail

# Parse arguments
HOURS="${1:-24}"  # Default to last 24 hours

# Check for jq
if ! command -v jq >/dev/null 2>&1; then
  echo "jq not found - Install: brew install jq (macOS) or apt-get install jq (Linux)"
  exit 1
fi

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

# Calculate time threshold
if [[ "$OSTYPE" == "darwin"* ]]; then
  THRESHOLD=$(date -v-${HOURS}H +%Y-%m-%dT%H:%M:%S)
else
  THRESHOLD=$(date -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%S)
fi

echo "ACE Pattern Relevance Report"
echo ""
echo "Time Range: Last ${HOURS} hours (since $THRESHOLD)"
echo ""

# Use jq to filter by event type (handles both "event":"search" and "event": "search")
# Count events by type using jq filter (not grep)
SEARCH_COUNT=$(jq -r --arg th "$THRESHOLD" 'select(.event == "search" and .timestamp >= $th)' "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
DOMAIN_SHIFT_COUNT=$(jq -r --arg th "$THRESHOLD" 'select(.event == "domain_shift" and .timestamp >= $th)' "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')
EXECUTION_COUNT=$(jq -r --arg th "$THRESHOLD" 'select(.event == "execution" and .timestamp >= $th)' "$LOG_FILE" 2>/dev/null | wc -l | tr -d ' ')

echo "Events Recorded"
echo "  Search queries: $SEARCH_COUNT"
echo "  Domain shifts: $DOMAIN_SHIFT_COUNT"
echo "  Task completions: $EXECUTION_COUNT"
echo ""

# Search metrics analysis
if [ "$SEARCH_COUNT" -gt 0 ]; then
  echo "Pattern Search Metrics"

  # Use jq -s with filter (not grep)
  STATS=$(jq -s --arg th "$THRESHOLD" '
    [.[] | select(.event == "search" and .timestamp >= $th)] |
    {
      total_returned: ([.[].patterns_returned] | add // 0),
      total_injected: ([.[].patterns_injected] | add // 0),
      total_filtered: ([.[].patterns_filtered] | add // 0),
      avg_confidence: (if length > 0 then (([.[].avg_confidence // 0] | add) / length) else 0 end),
      search_count: length
    }
  ' "$LOG_FILE" 2>/dev/null)

  TOTAL_RETURNED=$(echo "$STATS" | jq -r '.total_returned // 0')
  TOTAL_INJECTED=$(echo "$STATS" | jq -r '.total_injected // 0')
  TOTAL_FILTERED=$(echo "$STATS" | jq -r '.total_filtered // 0')
  AVG_CONF=$(echo "$STATS" | jq -r '(.avg_confidence * 100 | floor) // 0')

  echo "  Patterns returned: $TOTAL_RETURNED"
  echo "  Patterns injected: $TOTAL_INJECTED"
  echo "  Patterns filtered: $TOTAL_FILTERED (low quality)"
  echo "  Avg confidence: ${AVG_CONF}%"

  if [ "$TOTAL_RETURNED" -gt 0 ]; then
    INJECT_RATE=$((TOTAL_INJECTED * 100 / TOTAL_RETURNED))
    echo "  Injection rate: ${INJECT_RATE}%"
  fi
  echo ""

  # Top domains matched
  echo "Top Domains Matched"
  jq -r --arg th "$THRESHOLD" 'select(.event == "search" and .timestamp >= $th) | .domains[]?' "$LOG_FILE" 2>/dev/null | \
    sort | uniq -c | sort -rn | head -5 | \
    while read count domain; do
      echo "  $domain: $count searches"
    done
  echo ""
fi

# Domain shift analysis
if [ "$DOMAIN_SHIFT_COUNT" -gt 0 ]; then
  echo "Domain Shift Metrics"

  SHIFT_STATS=$(jq -s --arg th "$THRESHOLD" '
    [.[] | select(.event == "domain_shift" and .timestamp >= $th)] |
    {
      success_count: ([.[] | select(.search_succeeded == true)] | length),
      fail_count: ([.[] | select(.search_succeeded == false)] | length),
      total_patterns: ([.[].patterns_found] | add // 0)
    }
  ' "$LOG_FILE" 2>/dev/null)

  SUCCESS_COUNT=$(echo "$SHIFT_STATS" | jq -r '.success_count // 0')
  FAIL_COUNT=$(echo "$SHIFT_STATS" | jq -r '.fail_count // 0')
  TOTAL_PATTERNS=$(echo "$SHIFT_STATS" | jq -r '.total_patterns // 0')

  echo "  Successful auto-searches: $SUCCESS_COUNT"
  echo "  Failed auto-searches: $FAIL_COUNT"
  echo "  Total patterns loaded: $TOTAL_PATTERNS"

  if [ "$DOMAIN_SHIFT_COUNT" -gt 0 ]; then
    SUCCESS_RATE=$((SUCCESS_COUNT * 100 / DOMAIN_SHIFT_COUNT))
    echo "  Success rate: ${SUCCESS_RATE}%"
  fi
  echo ""

  # Most common domain shifts
  echo "Common Domain Transitions"
  jq -r --arg th "$THRESHOLD" 'select(.event == "domain_shift" and .timestamp >= $th) | "\(.from_domain) -> \(.to_domain)"' "$LOG_FILE" 2>/dev/null | \
    sort | uniq -c | sort -rn | head -5 | \
    while read count transition; do
      echo "  $transition ($count times)"
    done
  echo ""
fi

# Execution metrics analysis
if [ "$EXECUTION_COUNT" -gt 0 ]; then
  echo "Task Execution Metrics"

  EXEC_STATS=$(jq -s --arg th "$THRESHOLD" '
    [.[] | select(.event == "execution" and .timestamp >= $th)] |
    {
      total_patterns_used: ([.[].patterns_used_count] | add // 0),
      total_tools: ([.[].tools_executed] | add // 0),
      total_state_changing: ([.[].state_changing_tools] | add // 0),
      success_count: ([.[] | select(.success == true)] | length),
      learning_sent_count: ([.[] | select(.learning_sent == true)] | length),
      avg_execution_time: (if length > 0 then (([.[].execution_time_seconds // 0] | add) / length) else 0 end),
      task_count: length
    }
  ' "$LOG_FILE" 2>/dev/null)

  PATTERNS_USED=$(echo "$EXEC_STATS" | jq -r '.total_patterns_used // 0')
  TOTAL_TOOLS=$(echo "$EXEC_STATS" | jq -r '.total_tools // 0')
  STATE_CHANGING=$(echo "$EXEC_STATS" | jq -r '.total_state_changing // 0')
  SUCCESS=$(echo "$EXEC_STATS" | jq -r '.success_count // 0')
  LEARNING_SENT=$(echo "$EXEC_STATS" | jq -r '.learning_sent_count // 0')
  AVG_TIME=$(echo "$EXEC_STATS" | jq -r '(.avg_execution_time | floor) // 0')
  TASK_COUNT=$(echo "$EXEC_STATS" | jq -r '.task_count // 0')

  echo "  Tasks completed: $TASK_COUNT"
  echo "  Successful: $SUCCESS"
  echo "  Patterns referenced: $PATTERNS_USED"
  echo "  Tools executed: $TOTAL_TOOLS"
  echo "  State-changing tools: $STATE_CHANGING"
  echo "  Learning sent: $LEARNING_SENT"
  echo "  Avg execution time: ${AVG_TIME}s"

  if [ "$TASK_COUNT" -gt 0 ] && [ "$PATTERNS_USED" -gt 0 ]; then
    AVG_PATTERNS=$((PATTERNS_USED / TASK_COUNT))
    echo "  Avg patterns/task: $AVG_PATTERNS"
  fi
  echo ""
fi

# Summary insights
echo "Insights"

if [ "$SEARCH_COUNT" -gt 0 ] && [ "$TOTAL_RETURNED" -gt 0 ]; then
  FILTER_PCT=$((TOTAL_FILTERED * 100 / TOTAL_RETURNED))
  if [ "$FILTER_PCT" -gt 50 ]; then
    echo "  ⚠️  High filter rate (${FILTER_PCT}%): Many low-quality patterns being returned"
  else
    echo "  ✅ Filter rate: ${FILTER_PCT}% (healthy)"
  fi
fi

if [ "$DOMAIN_SHIFT_COUNT" -gt 0 ]; then
  if [ "$SUCCESS_COUNT" -lt "$((DOMAIN_SHIFT_COUNT / 2))" ]; then
    echo "  ⚠️  Low domain shift success rate: Server may need more domain-specific patterns"
  else
    echo "  ✅ Domain shift success rate: ${SUCCESS_RATE}%"
  fi
fi

if [ "$EXECUTION_COUNT" -gt 0 ]; then
  if [ "$PATTERNS_USED" -eq 0 ]; then
    echo "  ⚠️  No patterns referenced: Check if UserPromptSubmit hook is triggering"
  fi
  if [ "$LEARNING_SENT" -gt 0 ]; then
    LEARN_RATE=$((LEARNING_SENT * 100 / EXECUTION_COUNT))
    echo "  ✅ Learning capture rate: ${LEARN_RATE}%"
  fi
fi

echo ""
echo "Log file: $LOG_FILE"
echo "Total entries: $(wc -l < "$LOG_FILE" | tr -d ' ')"
```

## What You'll See

**Events Recorded**:
- Search queries from UserPromptSubmit hook
- Domain shifts from PreToolUse hook
- Task completions from Stop hook

**Pattern Search Metrics**:
- How many patterns are returned vs injected
- Client-side filtering effectiveness
- Average confidence scores
- Top matched domains

**Domain Shift Metrics**:
- Auto-search success rate
- Common domain transitions
- Patterns loaded per shift

**Task Execution Metrics**:
- Patterns referenced per task
- Success rates
- Learning capture rate

## Usage

```bash
# Last 24 hours (default)
/ace:ace-relevance-report

# Last 1 hour
/ace:ace-relevance-report --hours 1

# Last 7 days
/ace:ace-relevance-report --hours 168
```

## Interpreting Results

**High filter rate (>50%)**:
- Many patterns being filtered as low-quality
- Server may need retraining or pruning

**Low domain shift success**:
- Domain-specific patterns may be missing
- Consider running `/ace:ace-bootstrap` to populate domains

**No patterns referenced**:
- Check if ACE hooks are enabled
- Verify project configuration with `/ace:ace-doctor`

## See Also

- `/ace:ace-status` - View playbook statistics
- `/ace:ace-doctor` - Run diagnostics
- `/ace:ace-patterns` - View learned patterns
