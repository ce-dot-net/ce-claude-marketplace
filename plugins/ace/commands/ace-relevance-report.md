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

# Calculate time threshold (Unix timestamp)
if [[ "$OSTYPE" == "darwin"* ]]; then
  THRESHOLD=$(date -v-${HOURS}H +%Y-%m-%dT%H:%M:%S)
else
  THRESHOLD=$(date -d "-${HOURS} hours" +%Y-%m-%dT%H:%M:%S)
fi

echo "ACE Pattern Relevance Report"
echo ""
echo "Time Range: Last ${HOURS} hours (since $THRESHOLD)"
echo ""

# Count events by type
SEARCH_COUNT=$(grep '"event":"search"' "$LOG_FILE" 2>/dev/null | \
  jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)' 2>/dev/null | wc -l | tr -d ' ')
DOMAIN_SHIFT_COUNT=$(grep '"event":"domain_shift"' "$LOG_FILE" 2>/dev/null | \
  jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)' 2>/dev/null | wc -l | tr -d ' ')
EXECUTION_COUNT=$(grep '"event":"execution"' "$LOG_FILE" 2>/dev/null | \
  jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)' 2>/dev/null | wc -l | tr -d ' ')

echo "Events Recorded"
echo "  Search queries: $SEARCH_COUNT"
echo "  Domain shifts: $DOMAIN_SHIFT_COUNT"
echo "  Task completions: $EXECUTION_COUNT"
echo ""

# Search metrics analysis
if [ "$SEARCH_COUNT" -gt 0 ]; then
  echo "Pattern Search Metrics"

  # Calculate averages from search events
  SEARCH_DATA=$(grep '"event":"search"' "$LOG_FILE" 2>/dev/null | \
    jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)')

  if [ -n "$SEARCH_DATA" ]; then
    STATS=$(echo "$SEARCH_DATA" | jq -s '
      {
        total_returned: ([.[].patterns_returned] | add),
        total_injected: ([.[].patterns_injected] | add),
        total_filtered: ([.[].patterns_filtered] | add),
        avg_confidence: (([.[].avg_confidence] | add) / length),
        search_count: length
      }
    ')

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
    echo "$SEARCH_DATA" | jq -r '.domains[]?' | sort | uniq -c | sort -rn | head -5 | \
      while read count domain; do
        echo "  $domain: $count searches"
      done
    echo ""
  fi
fi

# Domain shift analysis
if [ "$DOMAIN_SHIFT_COUNT" -gt 0 ]; then
  echo "Domain Shift Metrics"

  SHIFT_DATA=$(grep '"event":"domain_shift"' "$LOG_FILE" 2>/dev/null | \
    jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)')

  if [ -n "$SHIFT_DATA" ]; then
    SUCCESS_COUNT=$(echo "$SHIFT_DATA" | jq -r 'select(.search_succeeded == true)' | wc -l | tr -d ' ')
    FAIL_COUNT=$(echo "$SHIFT_DATA" | jq -r 'select(.search_succeeded == false)' | wc -l | tr -d ' ')
    TOTAL_PATTERNS=$(echo "$SHIFT_DATA" | jq -s '[.[].patterns_found] | add // 0')

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
    echo "$SHIFT_DATA" | jq -r '"\(.from_domain) -> \(.to_domain)"' | sort | uniq -c | sort -rn | head -5 | \
      while read count transition; do
        echo "  $transition ($count times)"
      done
    echo ""
  fi
fi

# Execution metrics analysis
if [ "$EXECUTION_COUNT" -gt 0 ]; then
  echo "Task Execution Metrics"

  EXEC_DATA=$(grep '"event":"execution"' "$LOG_FILE" 2>/dev/null | \
    jq -r --arg th "$THRESHOLD" 'select(.timestamp >= $th)')

  if [ -n "$EXEC_DATA" ]; then
    STATS=$(echo "$EXEC_DATA" | jq -s '
      {
        total_patterns_used: ([.[].patterns_used_count] | add),
        total_tools: ([.[].tools_executed] | add),
        total_state_changing: ([.[].state_changing_tools] | add),
        success_count: ([.[] | select(.success == true)] | length),
        learning_sent_count: ([.[] | select(.learning_sent == true)] | length),
        avg_execution_time: (([.[].execution_time_seconds] | add) / length),
        task_count: length
      }
    ')

    PATTERNS_USED=$(echo "$STATS" | jq -r '.total_patterns_used // 0')
    TOTAL_TOOLS=$(echo "$STATS" | jq -r '.total_tools // 0')
    STATE_CHANGING=$(echo "$STATS" | jq -r '.total_state_changing // 0')
    SUCCESS=$(echo "$STATS" | jq -r '.success_count // 0')
    LEARNING_SENT=$(echo "$STATS" | jq -r '.learning_sent_count // 0')
    AVG_TIME=$(echo "$STATS" | jq -r '(.avg_execution_time | floor) // 0')
    TASK_COUNT=$(echo "$STATS" | jq -r '.task_count // 0')

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
fi

# Summary insights
echo "Insights"

if [ "$SEARCH_COUNT" -gt 0 ]; then
  # Check if patterns are being filtered heavily
  FILTER_RATE=$(grep '"event":"search"' "$LOG_FILE" 2>/dev/null | \
    jq -s --arg th "$THRESHOLD" '[.[] | select(.timestamp >= $th) | .patterns_filtered] | add // 0')
  RETURN_RATE=$(grep '"event":"search"' "$LOG_FILE" 2>/dev/null | \
    jq -s --arg th "$THRESHOLD" '[.[] | select(.timestamp >= $th) | .patterns_returned] | add // 0')

  if [ "$RETURN_RATE" -gt 0 ]; then
    FILTER_PCT=$((FILTER_RATE * 100 / RETURN_RATE))
    if [ "$FILTER_PCT" -gt 50 ]; then
      echo "  High filter rate (${FILTER_PCT}%): Many low-quality patterns being returned"
    fi
  fi
fi

if [ "$DOMAIN_SHIFT_COUNT" -gt 0 ] && [ "$SUCCESS_COUNT" -lt "$((DOMAIN_SHIFT_COUNT / 2))" ]; then
  echo "  Low domain shift success rate: Server may need more domain-specific patterns"
fi

if [ "$EXECUTION_COUNT" -gt 0 ] && [ "$PATTERNS_USED" -eq 0 ]; then
  echo "  No patterns referenced: UserPromptSubmit hook may not be triggering"
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
