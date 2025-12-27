---
description: Manage ACE log files and event logging toggle
argument-hint: "[--days N] [--status] [--enable-logging] [--disable-logging]"
---

# ACE Log Cleanup & Event Logging Toggle

```bash
#!/usr/bin/env bash
set -euo pipefail

# Parse arguments
DAYS=7
SHOW_STATUS=false
ENABLE_LOGGING=""

while [[ $# -gt 0 ]]; do
  case $1 in
    --days)
      DAYS="$2"
      shift 2
      ;;
    --status)
      SHOW_STATUS=true
      shift
      ;;
    --enable-logging)
      ENABLE_LOGGING="enable"
      shift
      ;;
    --disable-logging)
      ENABLE_LOGGING="disable"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

LOG_DIR=".claude/data/logs"

# Handle logging toggle
if [ -n "$ENABLE_LOGGING" ]; then
  if [ "$ENABLE_LOGGING" = "enable" ]; then
    echo "To enable event logging, add to your shell profile:"
    echo ""
    echo "  export ACE_EVENT_LOGGING=1"
    echo ""
    echo "Or run Claude Code with:"
    echo ""
    echo "  ACE_EVENT_LOGGING=1 claude"
    echo ""
    echo "Note: Event logging writes full tool responses to .claude/data/logs/"
    echo "This can cause 42GB+ log growth over time. Only enable for debugging."
  else
    echo "To disable event logging, remove from your shell profile:"
    echo ""
    echo "  unset ACE_EVENT_LOGGING"
    echo ""
    echo "Or simply don't set the variable (disabled by default since v5.4.5)."
  fi
  exit 0
fi

# Show status
if [ "$SHOW_STATUS" = true ]; then
  echo "ACE Log Status"
  echo ""

  # Check event logging status
  if [ "${ACE_EVENT_LOGGING:-0}" = "1" ]; then
    echo "Event Logging: ENABLED (ACE_EVENT_LOGGING=1)"
    echo "  Warning: Full tool responses are being logged!"
  else
    echo "Event Logging: DISABLED (default since v5.4.5)"
  fi
  echo ""

  # Show log sizes
  if [ -d "$LOG_DIR" ]; then
    echo "Log Directory: $LOG_DIR"
    echo ""
    TOTAL=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)
    echo "Total Size: $TOTAL"
    echo ""
    echo "Files:"
    ls -lhS "$LOG_DIR" 2>/dev/null | grep -E "\.jsonl|\.db" | while read line; do
      echo "  $line"
    done
  else
    echo "Log directory does not exist: $LOG_DIR"
  fi
  exit 0
fi

# Cleanup old logs
if [ ! -d "$LOG_DIR" ]; then
  echo "Log directory does not exist: $LOG_DIR"
  exit 0
fi

echo "ACE Log Cleanup"
echo ""
echo "Deleting logs older than $DAYS days..."
echo ""

# Calculate size before
BEFORE=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

# Find and delete old log files
# Note: We keep ace-relevance.jsonl (metrics) but delete event logs
DELETED=0

# Delete old event logs (the 42GB culprits)
for pattern in "ace-posttooluse*.jsonl" "ace-stop*.jsonl" "ace-pretooluse*.jsonl" "ace-precompact*.jsonl"; do
  for file in "$LOG_DIR"/$pattern; do
    if [ -f "$file" ]; then
      # Check if file is older than N days
      if [ "$(find "$file" -mtime +$DAYS 2>/dev/null)" ]; then
        SIZE=$(ls -lh "$file" | awk '{print $5}')
        echo "  Deleting: $(basename "$file") ($SIZE)"
        rm -f "$file"
        DELETED=$((DELETED + 1))
      fi
    fi
  done
done

# Delete old error logs
for file in "$LOG_DIR"/ace-errors*.jsonl; do
  if [ -f "$file" ]; then
    if [ "$(find "$file" -mtime +$DAYS 2>/dev/null)" ]; then
      SIZE=$(ls -lh "$file" | awk '{print $5}')
      echo "  Deleting: $(basename "$file") ($SIZE)"
      rm -f "$file"
      DELETED=$((DELETED + 1))
    fi
  fi
done

# Calculate size after
AFTER=$(du -sh "$LOG_DIR" 2>/dev/null | cut -f1)

echo ""
if [ $DELETED -eq 0 ]; then
  echo "No logs older than $DAYS days found."
else
  echo "Deleted $DELETED file(s)"
  echo "Space: $BEFORE -> $AFTER"
fi

echo ""
echo "Remaining files:"
ls -lhS "$LOG_DIR" 2>/dev/null | grep -E "\.jsonl|\.db" | head -10 | while read line; do
  echo "  $line"
done
```

## Usage

```bash
# Show log status and sizes
/ace:ace-cleanup --status

# Delete logs older than 7 days (default)
/ace:ace-cleanup

# Delete logs older than 30 days
/ace:ace-cleanup --days 30

# Show how to enable event logging (for debugging)
/ace:ace-cleanup --enable-logging

# Show how to disable event logging
/ace:ace-cleanup --disable-logging
```

## What Gets Cleaned

**Deleted** (event logs - the 42GB culprits):
- `ace-posttooluse*.jsonl` - Full tool input/output logs
- `ace-stop*.jsonl` - Stop hook event logs
- `ace-pretooluse*.jsonl` - PreToolUse hook event logs
- `ace-precompact*.jsonl` - PreCompact hook event logs
- `ace-errors*.jsonl` - Error logs

**Preserved** (useful for analysis):
- `ace-relevance.jsonl` - Pattern metrics (has rotation)
- `ace-tools.db` - SQLite (auto-cleaned after each task)

## Event Logging

Since v5.4.5, event logging is **disabled by default** to prevent 42GB log growth.

To enable for debugging:
```bash
export ACE_EVENT_LOGGING=1
```

To disable (default):
```bash
unset ACE_EVENT_LOGGING
```
